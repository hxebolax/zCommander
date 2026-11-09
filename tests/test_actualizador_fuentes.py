# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""2.0.1: origen de las actualizaciones (``actualizaciones.fuente``): mi servidor, GitHub, las dos o una dirección personalizada.

La raíz de confianza sigue siendo la firma Ed25519: con cualquier fuente, un
``version.json`` sin firma o firmado con otra clave se rechaza. El campo firmado
``espejos`` da otras direcciones del mismo ZIP (``espejos.github``).

Sin red real: ``red.abrir`` se sustituye por un Internet falso en memoria
(``_Internet``) que conoce unas cuantas direcciones https y simula caídas.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile

import pytest

pytest.importorskip("cryptography")

from tests.apoyo_actualizador import RAIZ, cargar_firmador, crear_zip  # noqa: E402

from app.core import red  # noqa: E402
from app.services import actualizador  # noqa: E402

SERVIDOR = actualizador.URL_MANIFIESTO
GITHUB = actualizador.URL_MANIFIESTO_GITHUB
PERSONALIZADA = "https://espejo.ejemplo.org/zc/version.json"
ARCHIVOS = {"ZCommander.exe": b"EXE nueva", "lib/modulo.txt": b"modulo" * 500}


def _zip_servidor(version: str) -> str:
	return f"https://xebolax.synology.me/zCommander/zCommander_v{version}.zip"


def _zip_github(version: str) -> str:
	return f"https://github.com/hxebolax/zCommander/releases/download/v{version}/zCommander_v{version}.zip"


class _Respuesta:
	"""Lo que ``descargas`` y ``_leer_manifiesto`` usan de una respuesta de ``urllib``."""

	def __init__(self, datos: bytes, url: str) -> None:
		self._cuerpo = io.BytesIO(datos)
		self._url = url
		self.status = 200
		self.headers = {"Content-Length": str(len(datos))}

	def read(self, cuantos: int = -1) -> bytes:
		return self._cuerpo.read(cuantos)

	def geturl(self) -> str:
		return self._url

	def close(self) -> None:
		return

	def __enter__(self):
		return self

	def __exit__(self, *_error) -> None:
		return


class _Internet:
	"""Direcciones https conocidas (``contenido``), caídas (``caidas``) y el resto 404. Anota cada petición."""

	def __init__(self) -> None:
		self.contenido: dict[str, bytes] = {}
		self.caidas: set[str] = set()
		self.peticiones: list[str] = []
		#: Cabeceras de cada petición, en el mismo orden que ``peticiones``.
		self.cabeceras: list[dict] = []

	def abrir(self, _config, url, *, metodo="GET", datos=None, cabeceras=None, tiempo_s=None):  # noqa: ARG002 - firma de red.abrir
		self.peticiones.append(url)
		self.cabeceras.append(dict(cabeceras or {}))
		if url in self.caidas:
			raise red.ErrorHTTP(red.CONEXION, "Sin conexión (simulada).")
		if url not in self.contenido:
			raise urllib.error.HTTPError(url, 404, "No encontrado", None, None)
		return _Respuesta(self.contenido[url], url)


@pytest.fixture
def internet(monkeypatch):
	falso = _Internet()
	monkeypatch.setattr(red, "abrir", falso.abrir)
	return falso


@pytest.fixture
def clave(tmp_path, monkeypatch):
	firmador = cargar_firmador()
	monkeypatch.delenv(firmador.VARIABLE_CONTRASENA, raising=False)
	ruta = tmp_path / "claves" / "firma.key"
	return ruta, firmador.generar(ruta)


@pytest.fixture
def config(tmp_path, clave):
	instalacion = tmp_path / "Mi App"
	(instalacion / "data" / "config").mkdir(parents=True)
	(instalacion / "ZCommander.exe").write_bytes(b"EXE 2.0.0")
	return actualizador.Configuracion(
		version_actual="2.0.0",
		carpeta_app=instalacion,
		claves_publicas=(clave[1],),
		comando=[sys.executable, str(instalacion / "main.py")],
		permitir_desde_codigo=True,
	)


def _paquete(tmp_path, version: str) -> bytes:
	ruta = crear_zip(tmp_path / f"paquete_{version}.zip", {**ARCHIVOS, "version.txt": version.encode()})
	return ruta.read_bytes()


def _manifiesto(tmp_path, version: str, datos_zip: bytes, ruta_clave=None, *, espejos: dict | None = None) -> bytes:
	"""``version.json`` como el de ``publicar.py`` (firmado si hay clave)."""
	manifiesto = {
		"app": "zCommander",
		"version": version,
		"file": f"zCommander_v{version}.zip",
		"sha256": hashlib.sha256(datos_zip).hexdigest(),
		"size": len(datos_zip),
		"date": "2026-11-09",
		"novedades": f"- Versión {version}",
	}
	if espejos is not None:
		manifiesto["espejos"] = espejos
	ruta = tmp_path / f"version_{version}_{len(list(tmp_path.glob('version_*.json')))}.json"
	ruta.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=4), encoding="utf-8")
	if ruta_clave is not None:
		cargar_firmador().firmar(ruta_clave, ruta)
	return ruta.read_bytes()


def _publicar_en(internet, tmp_path, clave, url_manifiesto: str, version: str, *, zip_en: tuple[str, ...] = (),
		espejos: dict | None = None, ruta_clave="propia") -> bytes:
	"""Publica en ``url_manifiesto`` un manifiesto de ``version`` y su ZIP en las direcciones ``zip_en``."""
	datos = _paquete(tmp_path, version)
	firma = clave[0] if ruta_clave == "propia" else ruta_clave
	internet.contenido[url_manifiesto] = _manifiesto(tmp_path, version, datos, firma, espejos=espejos)
	for url in zip_en:
		internet.contenido[url] = datos
	return datos


def _publicar_en_todas(internet, tmp_path, clave, version: str = "2.0.1") -> bytes:
	"""La publicación real: el MISMO version.json firmado (con espejos.github) en el servidor y en la release."""
	datos = _paquete(tmp_path, version)
	manifiesto = _manifiesto(tmp_path, version, datos, clave[0], espejos={"github": _zip_github(version)})
	internet.contenido.update({SERVIDOR: manifiesto, GITHUB: manifiesto, _zip_servidor(version): datos,
		_zip_github(version): datos})
	return datos


# ── Constantes y preferencias ────────────────────────────────────────────────


def test_direcciones_de_las_fuentes():
	assert actualizador.URL_MANIFIESTO == "https://xebolax.synology.me/zCommander/version.json"
	assert actualizador.URL_MANIFIESTO_GITHUB == "https://github.com/hxebolax/zCommander/releases/latest/download/version.json"
	assert actualizador.FUENTES == ("servidor", "github", "ambas", "personalizada")
	assert actualizador.Configuracion(version_actual="1", carpeta_app=RAIZ).fuente == "servidor", "de fábrica, el servidor"


def test_preferencias_de_fabrica_y_su_pagina():
	from app.core.configuracion import REGLAS, VALORES_POR_DEFECTO
	from app.core.descripciones_config import ACTUALIZACIONES, DESCRIPCIONES
	from app.ui.dialogos.f_preferencias import DEPENDENCIAS, NOMBRES_OPCIONES

	assert VALORES_POR_DEFECTO["actualizaciones"]["fuente"] == "servidor"
	assert VALORES_POR_DEFECTO["actualizaciones"]["url_personalizada"] == ""
	assert REGLAS["actualizaciones.fuente"].opciones == actualizador.FUENTES
	assert NOMBRES_OPCIONES["actualizaciones.fuente"] == {
		"servidor": "Servidor de zCommander (xebolax.synology.me)", "github": "GitHub (hxebolax/zCommander)",
		"ambas": "Las dos: la que tenga la versión más nueva", "personalizada": "Una dirección personalizada"}
	for clave_config in ("actualizaciones.fuente", "actualizaciones.url_personalizada"):
		etiqueta, ayuda, pagina = DESCRIPCIONES[clave_config]
		assert pagina == ACTUALIZACIONES and "&" in etiqueta and "firma" in ayuda
	assert DEPENDENCIAS["actualizaciones.url_personalizada"] == ("actualizaciones.fuente", ("personalizada",))


@pytest.mark.parametrize("url", ["http://ejemplo.org/version.json", "ftp://ejemplo.org/version.json", "https://",
	"ejemplo.org/version.json", "https://ejemplo .org/version.json"])
def test_url_personalizada_que_no_es_https_no_se_guarda(tmp_path, url):
	from app.core.configuracion import Configuracion, ErrorValidacion

	ajustes = Configuracion(ruta=tmp_path / "settings.json")
	with pytest.raises(ErrorValidacion, match="https://"):
		ajustes.establecer("actualizaciones.url_personalizada", url)
	assert ajustes.obtener("actualizaciones.url_personalizada") == ""


def test_url_personalizada_https_o_vacia_se_guarda(tmp_path):
	from app.core.configuracion import Configuracion

	ajustes = Configuracion(ruta=tmp_path / "settings.json")
	ajustes.establecer("actualizaciones.url_personalizada", PERSONALIZADA)
	assert ajustes.obtener("actualizaciones.url_personalizada") == PERSONALIZADA
	ajustes.establecer("actualizaciones.url_personalizada", "")
	ajustes.establecer("actualizaciones.fuente", "ambas")
	assert ajustes.obtener("actualizaciones.fuente") == "ambas"


def test_configuracion_por_defecto_lee_la_fuente_de_preferencias(datos_temporales):
	from app.core.configuracion import obtener_configuracion

	config = actualizador.configuracion_por_defecto("2.0.1")
	assert actualizador.fuente_elegida(config) == ("servidor", "")
	obtener_configuracion().establecer_varias({"actualizaciones.fuente": "personalizada",
		"actualizaciones.url_personalizada": PERSONALIZADA})
	# La misma configuración (la que guarda la comprobación periódica) ve el cambio sin reiniciar.
	assert actualizador.fuente_elegida(config) == ("personalizada", PERSONALIZADA)


def test_fuente_desconocida_usa_el_servidor(config):
	config.preferencias = lambda: ("otra", "")
	assert actualizador.fuente_elegida(config) == ("servidor", "")


# ── Cada fuente usa su dirección ─────────────────────────────────────────────


@pytest.mark.parametrize(("fuente", "url", "zip_esperado"), [
	("servidor", SERVIDOR, _zip_servidor("2.0.1")),
	("github", GITHUB, _zip_github("2.0.1")),
	("personalizada", PERSONALIZADA, "https://espejo.ejemplo.org/zc/zCommander_v2.0.1.zip"),
])
def test_cada_fuente_consulta_solo_su_direccion(config, internet, tmp_path, clave, fuente, url, zip_esperado):
	_publicar_en_todas(internet, tmp_path, clave)
	internet.contenido[PERSONALIZADA] = internet.contenido[SERVIDOR]
	config.fuente, config.url_personalizada = fuente, PERSONALIZADA
	info = actualizador.comprobar(config)
	assert internet.peticiones == [url]
	assert info.version == "2.0.1" and info.fuente == fuente
	assert info.url_zip == zip_esperado


def test_las_preferencias_mandan_sobre_la_configuracion(config, internet, tmp_path, clave):
	_publicar_en_todas(internet, tmp_path, clave)
	config.preferencias = lambda: ("github", "")
	assert actualizador.comprobar(config).fuente == "github"
	assert internet.peticiones == [GITHUB]


def test_registra_la_fuente_usada(config, internet, tmp_path, clave, caplog):
	_publicar_en_todas(internet, tmp_path, clave)
	config.fuente = "github"
	with caplog.at_level("INFO", logger="app.services.actualizador"):
		actualizador.comprobar(config)
	assert "fuente «github»" in caplog.text


def test_personalizada_vacia_dice_que_falta_la_direccion(config, internet):
	config.fuente = "personalizada"
	with pytest.raises(actualizador.ErrorActualizacion, match="no la ha escrito"):
		actualizador.comprobar(config)
	assert internet.peticiones == []


def test_personalizada_no_https_se_rechaza_sin_conectar(config, internet):
	config.fuente, config.url_personalizada = "personalizada", "http://espejo.ejemplo.org/version.json"
	with pytest.raises(actualizador.ErrorRed, match="https"):
		actualizador.comprobar(config)
	assert internet.peticiones == []


def test_el_error_dice_que_fuente_fallo(config, internet):
	internet.caidas.add(GITHUB)
	config.fuente = "github"
	with pytest.raises(actualizador.ErrorRed, match="No se pudo conectar con GitHub"):
		actualizador.comprobar(config)
	config.fuente = "servidor"
	with pytest.raises(actualizador.ErrorRed, match=r"servidor de zCommander \(xebolax\.synology\.me\).*error 404"):
		actualizador.comprobar(config)


# ── Las dos ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("caida", "queda"), [(SERVIDOR, "github"), (GITHUB, "servidor")])
def test_ambas_con_una_caida_usa_la_otra_sin_error(config, internet, tmp_path, clave, caida, queda):
	_publicar_en_todas(internet, tmp_path, clave)
	internet.caidas.add(caida)
	config.fuente = "ambas"
	info = actualizador.comprobar(config)
	assert info.version == "2.0.1" and info.fuente == queda
	assert internet.peticiones == [SERVIDOR, GITHUB], "se consultan las dos, en serie"


@pytest.mark.parametrize(("version_servidor", "version_github", "gana"), [
	("2.0.1", "2.0.2", "github"), ("2.0.3", "2.0.2", "servidor"), ("2.0.2", "2.0.2", "servidor"),
])
def test_ambas_elige_la_version_mas_nueva(config, internet, tmp_path, clave, version_servidor, version_github, gana):
	_publicar_en(internet, tmp_path, clave, SERVIDOR, version_servidor)
	_publicar_en(internet, tmp_path, clave, GITHUB, version_github)
	config.fuente = "ambas"
	info = actualizador.comprobar(config)
	assert info.fuente == gana
	assert info.version == (version_github if gana == "github" else version_servidor)


def test_ambas_caidas_da_el_error_con_las_dos_fuentes(config, internet):
	internet.caidas.update({SERVIDOR, GITHUB})
	config.fuente = "ambas"
	with pytest.raises(actualizador.ErrorRed) as error:
		actualizador.comprobar(config)
	assert "servidor de zCommander" in str(error.value) and "GitHub" in str(error.value)


def test_ambas_no_ofrece_una_version_firmada_por_otro_aunque_sea_mas_nueva(config, internet, tmp_path, clave):
	otra = tmp_path / "otra.key"
	cargar_firmador().generar(otra)
	_publicar_en(internet, tmp_path, clave, SERVIDOR, "2.0.1")
	_publicar_en(internet, tmp_path, clave, GITHUB, "9.0.0", ruta_clave=otra)
	config.fuente = "ambas"
	info = actualizador.comprobar(config)
	assert info.version == "2.0.1" and info.fuente == "servidor"


# ── La firma manda con cualquier fuente ──────────────────────────────────────


@pytest.mark.parametrize("fuente", ["servidor", "github", "personalizada", "ambas"])
@pytest.mark.parametrize("firma", ["sin_firma", "otra_clave", "manipulado"])
def test_manifiesto_sin_firma_valida_se_rechaza_en_todas_las_fuentes(config, internet, tmp_path, clave, fuente, firma):
	ruta_clave = None
	if firma == "otra_clave":
		ruta_clave = tmp_path / "otra.key"
		cargar_firmador().generar(ruta_clave)
	elif firma == "manipulado":
		ruta_clave = clave[0]
	for url in (SERVIDOR, GITHUB, PERSONALIZADA):
		datos = _publicar_en(internet, tmp_path, clave, url, "2.0.1", ruta_clave=ruta_clave)
		if firma == "manipulado":
			manifiesto = json.loads(internet.contenido[url])
			manifiesto["espejos"] = {"github": "https://atacante.ejemplo/zCommander_v2.0.1.zip"}
			internet.contenido[url] = json.dumps(manifiesto).encode()
		internet.contenido["https://atacante.ejemplo/zCommander_v2.0.1.zip"] = datos
	config.fuente, config.url_personalizada = fuente, PERSONALIZADA
	with pytest.raises(actualizador.ErrorFirma) as error:
		actualizador.comprobar(config)
	if fuente == "github":
		assert str(error.value).startswith("GitHub:")
	if fuente == "personalizada":
		assert "dirección personalizada (espejo.ejemplo.org)" in str(error.value)
	assert not any("atacante" in url for url in internet.peticiones)


def test_manifiesto_con_espejos_verifica_con_la_firma(tmp_path, clave):
	datos = _paquete(tmp_path, "2.0.1")
	manifiesto = json.loads(_manifiesto(tmp_path, "2.0.1", datos, clave[0], espejos={"github": _zip_github("2.0.1")}))
	# La firma cubre todo salvo la propia firma: también «espejos».
	assert b'"espejos"' in actualizador.serializar_canonico(manifiesto)
	assert actualizador.CAMPO_FIRMA.encode() not in actualizador.serializar_canonico(manifiesto)
	assert actualizador.serializar_canonico(manifiesto) == cargar_firmador().serializar_canonico(manifiesto)
	actualizador.verificar_firma(manifiesto, (clave[1],))
	manifiesto["espejos"]["github"] = "https://otro.ejemplo/zCommander_v2.0.1.zip"
	with pytest.raises(actualizador.ErrorFirma):
		actualizador.verificar_firma(manifiesto, (clave[1],))


def test_un_cliente_2_0_0_acepta_el_manifiesto_con_espejos(config, internet, tmp_path, clave):
	"""Lo que hacía la 2.0.0: leer del servidor, verificar la firma y descargar ``url`` (o el ZIP junto al manifiesto)."""
	datos = _publicar_en_todas(internet, tmp_path, clave)
	manifiesto = json.loads(internet.contenido[SERVIDOR])
	actualizador.verificar_firma(manifiesto, (clave[1],))
	# Llamada con la firma de la 2.0.0 (sin fuente): el ZIP sigue siendo el del servidor.
	info = actualizador._info_desde_manifiesto(config, manifiesto, SERVIDOR)  # noqa: SLF001
	assert info.url_zip == _zip_servidor("2.0.1") and info.urls == (_zip_servidor("2.0.1"),)
	ruta = actualizador.descargar(config, info)
	actualizador.verificar_paquete(ruta, info)
	assert ruta.read_bytes() == datos


def test_el_actualizador_de_la_2_0_0_real_acepta_espejos(config, internet, tmp_path, clave):
	"""El ``actualizador.py`` publicado en las fuentes de la 2.0.0 (si están en dist/) lee el manifiesto nuevo."""
	fuentes = RAIZ / "dist" / "zCommander_v2.0.0_fuentes.zip"
	if not fuentes.is_file():
		pytest.skip("No están las fuentes de la 2.0.0 en dist/")
	with zipfile.ZipFile(fuentes) as paquete:
		codigo = paquete.read("zCommander-2.0.0/app/services/actualizador.py")
	ruta = tmp_path / "actualizador_200.py"
	ruta.write_bytes(codigo)
	especificacion = importlib.util.spec_from_file_location("actualizador_200", ruta)
	antiguo = importlib.util.module_from_spec(especificacion)
	especificacion.loader.exec_module(antiguo)
	assert not hasattr(antiguo, "URL_MANIFIESTO_GITHUB"), "es de verdad la 2.0.0"
	_publicar_en_todas(internet, tmp_path, clave)
	viejo = antiguo.Configuracion(version_actual="2.0.0", carpeta_app=config.carpeta_app, claves_publicas=(clave[1],))
	info = antiguo.comprobar(viejo)
	assert info.version == "2.0.1" and info.url_zip == _zip_servidor("2.0.1")
	assert internet.peticiones == [SERVIDOR]


# ── Descarga: el espejo correcto y el otro si falla ──────────────────────────


@pytest.mark.parametrize(("fuente", "primera"), [
	("servidor", _zip_servidor("2.0.1")), ("github", _zip_github("2.0.1")),
])
def test_la_descarga_usa_la_direccion_de_la_fuente(config, internet, tmp_path, clave, fuente, primera):
	datos = _publicar_en_todas(internet, tmp_path, clave)
	config.fuente = fuente
	info = actualizador.comprobar(config)
	assert info.urls == (primera,), "con una sola fuente no se descarga de la otra"
	internet.peticiones.clear()
	ruta = actualizador.descargar(config, info)
	assert internet.peticiones == [primera] and ruta.read_bytes() == datos


def test_github_sin_espejo_descarga_junto_al_manifiesto(config, internet, tmp_path, clave):
	"""Un manifiesto sin ``espejos`` leído de GitHub: el ZIP de la misma release («latest/download»)."""
	_publicar_en(internet, tmp_path, clave, GITHUB, "2.0.1")
	config.fuente = "github"
	info = actualizador.comprobar(config)
	assert info.url_zip == "https://github.com/hxebolax/zCommander/releases/latest/download/zCommander_v2.0.1.zip"


def test_personalizada_descarga_junto_al_manifiesto_y_los_espejos_de_respaldo(config, internet, tmp_path, clave):
	datos = _publicar_en(internet, tmp_path, clave, PERSONALIZADA, "2.0.1", zip_en=(_zip_github("2.0.1"),),
		espejos={"github": _zip_github("2.0.1")})
	config.fuente, config.url_personalizada = "personalizada", PERSONALIZADA
	info = actualizador.comprobar(config)
	assert info.urls == ("https://espejo.ejemplo.org/zc/zCommander_v2.0.1.zip", _zip_github("2.0.1"))
	ruta = actualizador.descargar(config, info)  # junto al manifiesto no está: 404 y pasa al espejo
	assert ruta.read_bytes() == datos
	assert internet.peticiones[-2:] == ["https://espejo.ejemplo.org/zc/zCommander_v2.0.1.zip", _zip_github("2.0.1")]


@pytest.mark.parametrize(("caida", "elegida", "primera", "segunda"), [
	(None, "servidor", _zip_servidor("2.0.1"), _zip_github("2.0.1")),
	(SERVIDOR, "github", _zip_github("2.0.1"), _zip_servidor("2.0.1")),
])
def test_ambas_descarga_de_la_fuente_elegida_y_cae_a_la_otra(config, internet, tmp_path, clave, caida, elegida, primera,
		segunda):
	datos = _publicar_en_todas(internet, tmp_path, clave)
	if caida:
		internet.caidas.add(caida)
	config.fuente = "ambas"
	info = actualizador.comprobar(config)
	assert info.fuente == elegida and info.urls == (primera, segunda)
	internet.caidas.add(primera)
	internet.peticiones.clear()
	ruta = actualizador.descargar(config, info)
	assert internet.peticiones == [primera, segunda] and ruta.read_bytes() == datos


def test_si_fallan_todas_las_direcciones_se_dice_el_ultimo_error(config, internet, tmp_path, clave):
	_publicar_en_todas(internet, tmp_path, clave)
	config.fuente = "ambas"
	info = actualizador.comprobar(config)
	internet.caidas.update(info.urls)
	with pytest.raises(actualizador.ErrorRed, match="La descarga desde GitHub se interrumpió"):
		actualizador.descargar(config, info)


def test_un_espejo_con_el_zip_cambiado_no_pasa_el_sha_y_se_usa_el_otro(config, internet, tmp_path, clave):
	"""El SHA-256 y el tamaño del manifiesto firmado se comprueban sea cual sea el host."""
	datos = _publicar_en_todas(internet, tmp_path, clave)
	config.fuente = "ambas"
	info = actualizador.comprobar(config)
	malo = bytearray(datos)
	malo[-30] ^= 0xFF  # mismo tamaño, contenido distinto
	internet.contenido[_zip_servidor("2.0.1")] = bytes(malo)
	fases = []
	ruta_bat = actualizador.descargar_y_preparar(config, info, progreso=lambda fase, hecho, total: fases.append(fase))
	assert ruta_bat.is_file()
	assert internet.peticiones[-2:] == [_zip_servidor("2.0.1"), _zip_github("2.0.1")]
	assert (config.carpeta_trabajo / "nueva" / "programa" / "version.txt").read_bytes() == b"2.0.1"
	assert fases.count("verificacion") >= 3


def test_con_un_solo_espejo_el_sha_incorrecto_se_rechaza(config, internet, tmp_path, clave):
	datos = _publicar_en_todas(internet, tmp_path, clave)
	config.fuente = "github"
	info = actualizador.comprobar(config)
	internet.contenido[_zip_github("2.0.1")] = bytes(reversed(datos))
	with pytest.raises(actualizador.ErrorVerificacion):
		actualizador.descargar_y_preparar(config, info)
	assert _zip_servidor("2.0.1") not in internet.peticiones


def test_cancelar_no_prueba_otra_direccion(config, internet, tmp_path, clave):
	_publicar_en_todas(internet, tmp_path, clave)
	config.fuente = "ambas"
	info = actualizador.comprobar(config)
	internet.peticiones.clear()
	with pytest.raises(actualizador.ErrorCancelado):
		actualizador.descargar(config, info, cancelado=lambda: True)
	assert internet.peticiones == [info.url_zip]


def test_espejo_no_https_se_ignora(config, internet, tmp_path, clave):
	_publicar_en(internet, tmp_path, clave, SERVIDOR, "2.0.1", espejos={"github": "http://github.com/x.zip", "otro": 5})
	config.fuente = "ambas"
	internet.caidas.add(GITHUB)
	info = actualizador.comprobar(config)
	assert info.urls == (_zip_servidor("2.0.1"),)


# ── Redirecciones de GitHub ──────────────────────────────────────────────────


def test_las_redirecciones_https_se_siguen_y_las_http_no():
	"""``latest/download`` redirige a objects.githubusercontent.com: https a https se sigue; a http, nunca."""
	manejador = red._SinBajarAHttp()  # noqa: SLF001
	peticion = urllib.request.Request(GITHUB, headers={"User-Agent": "zCommander/2.0.1"})
	destino = "https://objects.githubusercontent.com/github-production-release-asset/1/version.json"
	nueva = manejador.redirect_request(peticion, None, 302, "Found", {}, destino)
	assert nueva is not None and nueva.full_url == destino
	with pytest.raises(red.ErrorHTTP):
		manejador.redirect_request(peticion, None, 302, "Found", {}, "http://objects.githubusercontent.com/version.json")
	actualizador._comprobar_url(GITHUB)  # noqa: SLF001 - no lo impide


# ── tools/publicar.py ────────────────────────────────────────────────────────


def _publicar_herramienta():
	from tools import publicar

	return publicar


def test_publicar_mete_espejos_github_firmado(tmp_path, clave):
	publicar = _publicar_herramienta()
	(tmp_path / "dist").mkdir()
	zip_ = crear_zip(tmp_path / "dist" / "zCommander_v2.0.1.zip", ARCHIVOS)
	ruta = publicar.crear_manifiesto(zip_, "2.0.1", "- Novedades", clave[0], (clave[1],))
	manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
	assert manifiesto["espejos"] == {"github": _zip_github("2.0.1")}
	assert "url" not in manifiesto, "el ZIP del servidor sigue siendo el que está junto al manifiesto (como en la 2.0.0)"
	actualizador.verificar_firma(manifiesto, (clave[1],))
	assert cargar_firmador().verificar(ruta, [clave[1]]) == []
	assert publicar.url_release_github("2.0.1") == _zip_github("2.0.1")
	assert publicar.REPOSITORIO_GITHUB == actualizador.REPOSITORIO_GITHUB


def test_publicar_sin_github_no_mete_espejos(tmp_path, clave):
	publicar = _publicar_herramienta()
	(tmp_path / "dist").mkdir()
	zip_ = crear_zip(tmp_path / "dist" / "zCommander_v2.0.1.zip", ARCHIVOS)
	ruta = publicar.crear_manifiesto(zip_, "2.0.1", "- Novedades", clave[0], (clave[1],), espejo_github=False)
	manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
	assert "espejos" not in manifiesto
	actualizador.verificar_firma(manifiesto, (clave[1],))


def test_publicar_tiene_la_opcion_sin_github(monkeypatch):
	publicar = _publicar_herramienta()
	recibido = {}
	monkeypatch.setattr(publicar, "publicar", lambda **opciones: recibido.update(opciones))
	assert publicar.main(["--sin-github", "--sin-compilar", "--sin-comprobar"]) == 0
	assert recibido["espejo_github"] is False and recibido["servidor"] is False
	assert publicar.main(["--sin-compilar", "--sin-comprobar"]) == 0
	assert recibido["espejo_github"] is True


# ── 2.0.1 (revisión): reanudar solo desde la misma dirección ─────────────────

def test_al_cambiar_de_direccion_no_se_reanuda_lo_de_la_anterior(config, internet, tmp_path, clave):
	datos = _publicar_en_todas(internet, tmp_path, clave)
	config.fuente = "ambas"
	info = actualizador.comprobar(config)
	primera, segunda = info.urls
	carpeta = config.carpeta_trabajo / "descarga"
	carpeta.mkdir(parents=True, exist_ok=True)
	parcial = carpeta / (info.archivo + ".parcial")
	# Una descarga a medias que vino de la primera dirección, que ahora está caída.
	parcial.write_bytes(datos[:100])
	(carpeta / (info.archivo + ".parcial.origen")).write_text(primera, encoding="utf-8")
	internet.caidas.add(primera)
	internet.peticiones.clear()
	internet.cabeceras.clear()
	ruta = actualizador.descargar(config, info)
	assert ruta.read_bytes() == datos
	assert internet.peticiones == [primera, segunda]
	assert "Range" in internet.cabeceras[0]  # la primera sí se reanudaba (misma dirección)
	assert "Range" not in internet.cabeceras[1]  # la segunda empieza de cero
	assert not (carpeta / (info.archivo + ".parcial.origen")).exists()


def test_misma_direccion_reanuda_y_sin_origen_conocido_empieza_de_cero(tmp_path):
	final = tmp_path / "zc.zip"
	parcial = tmp_path / "zc.zip.parcial"
	parcial.write_bytes(b"abc")
	actualizador._preparar_parcial(final, "https://a.ejemplo.org/zc.zip")  # sin origen anotado: de cero
	assert not parcial.exists()
	parcial.write_bytes(b"abc")
	actualizador._preparar_parcial(final, "https://a.ejemplo.org/zc.zip")  # misma dirección: se conserva
	assert parcial.read_bytes() == b"abc"
	actualizador._preparar_parcial(final, "https://b.ejemplo.org/zc.zip")  # otra: se borra
	assert not parcial.exists()


def test_personalizada_sin_direccion_avisa_una_vez_en_el_registro(config, internet, caplog, monkeypatch):
	import logging

	monkeypatch.setattr(actualizador, "_avisado_sin_direccion", [False])
	monkeypatch.setattr(actualizador, "comprobaciones", dict)
	config.fuente, config.url_personalizada = "personalizada", ""
	with caplog.at_level(logging.INFO, logger=actualizador.log.name):
		actualizador.pasada(config)
		actualizador.pasada(config)
	avisos = [r for r in caplog.records if r.levelno == logging.WARNING and "no puede hacerse" in r.getMessage()]
	assert len(avisos) == 1
	assert "no la ha escrito" in avisos[0].getMessage()
	assert not internet.peticiones
