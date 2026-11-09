# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""``tools/publicar.py`` (diseño 2.0, 5.6 y 18.2) sobre un proyecto y un servidor falsos en carpetas temporales.

Nunca toca ``C:\\Users\\xebol\\SynologyDrive``, ni compila, ni usa la clave del proyecto.
"""

from __future__ import annotations

import base64
import json
import shutil
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

from tests.apoyo_actualizador import RAIZ, cargar_firmador  # noqa: E402
from tools import publicar  # noqa: E402

from app.plugins import firma  # noqa: E402
from app.services import actualizador  # noqa: E402


@pytest.fixture
def clave(tmp_path, monkeypatch):
	firmador = cargar_firmador()
	monkeypatch.delenv(firmador.VARIABLE_CONTRASENA, raising=False)
	ruta = tmp_path / "claves" / "firma.key"
	return ruta, firmador.generar(ruta)


@pytest.fixture
def proyecto(tmp_path):
	"""Un proyecto mínimo: versión, registro de cambios, compilación, complemento y una clave que no debe salir."""
	raiz = tmp_path / "proyecto"
	(raiz / "app" / "core").mkdir(parents=True)
	(raiz / "app" / "core" / "version.py").write_text('APP_VERSION = "2.0.0"\n', encoding="utf-8")
	(raiz / "data" / "docs").mkdir(parents=True)
	(raiz / "data" / "docs" / "changelog.md").write_text(
		"# Registro de cambios\n\n## Versión 2.0.0 - 2026-11-08\n\n- Complementos.\n- Sonidos.\n", encoding="utf-8")
	(raiz / "data" / "config").mkdir()
	(raiz / "data" / "config" / "settings.json").write_text("{}", encoding="utf-8")
	(raiz / "tools" / "claves").mkdir(parents=True)
	(raiz / "tools" / "claves" / "firma_ed25519.key").write_text("secreta", encoding="utf-8")
	(raiz / "adjuntos").mkdir()
	(raiz / "adjuntos" / "ajeno.pdf").write_bytes(b"%PDF")
	(raiz / "main.py").write_text("print('zCommander')\n", encoding="utf-8")
	build = raiz / "build" / "ZCommander"
	(build / "lib").mkdir(parents=True)
	(build / "ZCommander.exe").write_bytes(b"EXE 2.0.0")
	(build / "lib" / "modulo.pyc").write_bytes(b"compilado")
	(build / "data" / "docs").mkdir(parents=True)
	(build / "data" / "docs" / "manual.md").write_text("# Manual", encoding="utf-8")
	shutil.copytree(RAIZ / "tests" / "datos" / "plugins" / "ejemplo", raiz / "plugins" / "ejemplo")
	return raiz


def _servidor(tmp_path) -> Path:
	destino = tmp_path / "SynologyDrive" / "web" / "zCommander"
	destino.parent.mkdir(parents=True)
	return destino


def test_servidor_recibe_los_paquetes_antes_que_los_json(tmp_path, proyecto, clave, monkeypatch):
	destino = _servidor(tmp_path)
	copiados: list[str] = []
	original = publicar._copiar

	def anotar(origen, final):
		# Al copiar cada JSON, los paquetes a los que apunta ya están en el servidor.
		if final.suffix == ".json":
			assert (destino / "zCommander_v2.0.0.zip").is_file()
		copiados.append(final.name)
		original(origen, final)

	monkeypatch.setattr(publicar, "_copiar", anotar)
	orden = publicar.publicar(raiz=proyecto, clave=clave[0], servidor=True, destino=destino, compilar_antes=False,
		comprobar=False, complementos=["prueba.ejemplo"], claves_publicas=(clave[1],))
	assert orden == copiados == ["zCommander_v2.0.0.zip", "zCommander_v2.0.0_fuentes.zip", "prueba.ejemplo-1.0.0.zcplugin",
		"prueba.ejemplo.json", "version.json"]
	for nombre in orden:
		assert (destino / nombre).stat().st_size == (proyecto / "dist" / nombre).stat().st_size
	assert not list(destino.glob("*.subiendo"))

	# El manifiesto lo acepta la aplicación con su clave, y su ZIP coincide.
	firmador = cargar_firmador()
	assert firmador.verificar(destino / "version.json", [clave[1]]) == []
	manifiesto = json.loads((destino / "version.json").read_text(encoding="utf-8"))
	actualizador.verificar_firma(manifiesto, (clave[1],))
	assert manifiesto["app"] == "zCommander" and manifiesto["file"] == "zCommander_v2.0.0.zip"
	assert manifiesto["novedades"] == "- Complementos.\n- Sonidos."
	with zipfile.ZipFile(destino / "zCommander_v2.0.0.zip") as paquete:
		nombres = paquete.namelist()
	assert "zCommander/ZCommander.exe" in nombres and "zCommander/data/docs/manual.md" in nombres

	# Fuentes sin claves, sin adjuntos, sin compilación y sin datos personales (2.4).
	with zipfile.ZipFile(destino / "zCommander_v2.0.0_fuentes.zip") as fuentes:
		nombres = fuentes.namelist()
	assert "zCommander-2.0.0/main.py" in nombres and "zCommander-2.0.0/plugins/ejemplo/manifiesto.toml" in nombres
	for prohibido in ("tools/claves", "adjuntos/", "build/", "dist/", "data/config"):
		assert not any(prohibido in nombre for nombre in nombres), prohibido


def test_complemento_firmado_lo_acepta_verificar_complemento(tmp_path, proyecto, clave):
	dist = tmp_path / "dist"
	dist.mkdir()
	[(paquete, ruta_json)] = publicar.firmar_complementos(["prueba.ejemplo"], clave[0], dist, proyecto / "plugins",
		url_base="https://ejemplo.invalid/zc/")
	assert paquete.name == "prueba.ejemplo-1.0.0.zcplugin"
	assert not (proyecto / "plugins" / "ejemplo" / firma.NOMBRE_FIRMA).exists(), "el repositorio no se toca"
	carpeta = tmp_path / "extraido"
	with zipfile.ZipFile(paquete) as zip_:
		assert all("/" not in nombre or not nombre.startswith("ejemplo/") for nombre in zip_.namelist())  # sin carpeta contenedora
		zip_.extractall(carpeta)
	privada = publicar._privada_en_bruto(clave[0])
	resultado = firma.verificar_complemento(carpeta, [firma.clave_publica(privada)], comprobar_sumas=True)
	assert resultado.valida, resultado.motivo
	# Un byte cambiado ya no vale.
	(carpeta / "manifiesto.toml").write_bytes((carpeta / "manifiesto.toml").read_bytes() + b"\n")
	assert not firma.verificar_complemento(carpeta, [firma.clave_publica(privada)], comprobar_sumas=True).valida

	datos = json.loads(ruta_json.read_text(encoding="utf-8"))
	assert {clave_json for clave_json in datos} == {"id", "version", "url", "sha256", "tamano", "novedades", "firma_ed25519"}
	assert datos["url"] == "https://ejemplo.invalid/zc/prueba.ejemplo-1.0.0.zcplugin"
	assert datos["tamano"] == paquete.stat().st_size
	from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

	Ed25519PublicKey.from_public_bytes(bytes.fromhex(clave[1])).verify(
		base64.b64decode(datos["firma_ed25519"]), cargar_firmador().serializar_canonico(datos))


def test_clave_que_no_es_la_de_la_aplicacion_se_rechaza(tmp_path, proyecto, clave):
	otra = cargar_firmador().generar(tmp_path / "otra.key")
	with pytest.raises(publicar.ErrorPublicar, match="CLAVES_PUBLICAS_ED25519"):
		publicar.publicar(raiz=proyecto, clave=clave[0], compilar_antes=False, comprobar=False, sin_fuentes=True,
			claves_publicas=(otra,))


def test_sin_notas_de_la_version_no_se_publica(proyecto, clave):
	(proyecto / "data" / "docs" / "changelog.md").write_text("# Registro\n\n## Versión 1.0.0\n\n- Antigua\n", encoding="utf-8")
	with pytest.raises(publicar.ErrorPublicar, match="no tiene notas"):
		publicar.publicar(raiz=proyecto, clave=clave[0], compilar_antes=False, comprobar=False, claves_publicas=(clave[1],))


@pytest.mark.parametrize("personal", ["config", "plugins", "logs"])
def test_compilacion_con_datos_personales_no_se_empaqueta(proyecto, clave, personal):
	(proyecto / "build" / "ZCommander" / "data" / personal).mkdir()
	with pytest.raises(publicar.ErrorPublicar, match="datos personales"):
		publicar.publicar(raiz=proyecto, clave=clave[0], compilar_antes=False, comprobar=False, claves_publicas=(clave[1],))


def test_sin_carpeta_del_servidor_no_copia(tmp_path):
	archivo = tmp_path / "a.zip"
	archivo.write_bytes(b"x")
	with pytest.raises(publicar.ErrorPublicar):
		publicar.al_servidor([archivo], [], tmp_path / "no" / "existe" / "zCommander")


def test_por_defecto_publica_en_la_carpeta_sincronizada():
	assert publicar.SERVIDOR == Path.home() / "SynologyDrive" / "web" / "zCommander"
	assert publicar.URL_BASE + "version.json" == actualizador.URL_MANIFIESTO
	assert publicar.CLAVE == RAIZ / "tools" / "claves" / "firma_ed25519.key"
