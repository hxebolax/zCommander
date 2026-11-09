# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comprobar versiones nuevas (diseño 2.0, 6.2, 6.4 y 18.2): servidor local que imita GitHub y MSYS2, sin Internet."""

from __future__ import annotations

import pytest

from app.services.componentes import estado, fichas, fuentes
from tests.servicios import apoyo_co
from tests.servicios.apoyo_co import CONFIG, ServidorPrueba, sha


@pytest.fixture
def servidor(monkeypatch):
	servidor = ServidorPrueba()
	monkeypatch.setattr(fuentes, "API_GITHUB", servidor.base)
	yield servidor
	servidor.cerrar()


def _ffmpeg(digest: str = "sha256:" + "a" * 64) -> dict:
	return apoyo_co.ficha_demo("9.0.2", id="ffmpeg", nombre="FFmpeg", carpeta="ffmpeg",
		fuente={"tipo": "github", "repositorio": "prueba/builds", "etiqueta": "latest", "rama": "9.0",
			"patron_asset": "ffmpeg-n{rama}-latest-win64-gpl-shared-{rama}.zip", "version_desde": "programa",
			"extraer": {"*/bin/*.exe": "."}},
		verificacion={"tipo": "sha256sums", "asset": "checksums.sha256"},
		asset={"digest": digest, "actualizado": "2026-11-01T10:00:00Z"})


def test_github_detecta_la_version_nueva_con_su_suma(servidor):
	paquete = apoyo_co.zip_de({"demo-v1.1.0/demo.exe": "demo v1.1.0"})
	sumas = f"{sha(paquete)}  demo-v1.1.0.zip\n{'0' * 64}  otro.zip\n"
	publicacion = servidor.publicar_github("prueba/demo", "v1.1.0", {"demo-v1.1.0.zip": paquete, "SHA256SUMS": sumas.encode()})
	assert publicacion["tag_name"] == "v1.1.0"
	nueva = fuentes.comprobar(apoyo_co.ficha_demo("1.0.0"), CONFIG)
	assert nueva is not None and nueva.version == "1.1.0" and nueva.texto == "1.1.0"
	assert nueva.paquetes[0].sha256 == sha(paquete)
	assert nueva.paquetes[0].extraer == {"demo-v1.1.0/demo.exe": "demo.exe"}
	assert not nueva.cambio_grande
	assert "Arreglos varios" in nueva.novedades


def test_github_al_dia_y_cambio_grande(servidor):
	paquete = apoyo_co.zip_de({"demo-v2.0.0/demo.exe": "demo v2.0.0"})
	servidor.publicar_github("prueba/demo", "v2.0.0", {"demo-v2.0.0.zip": paquete})
	ficha = apoyo_co.ficha_demo("2.0.0", verificacion={"tipo": "digest_github"})
	assert fuentes.comprobar(ficha, CONFIG) is None
	nueva = fuentes.comprobar(dict(ficha, version="1.9.0"), CONFIG)
	assert nueva.cambio_grande and nueva.paquetes[0].sha256 == sha(paquete)


def test_github_sin_suma_publicada_no_ofrece_instalar(servidor):
	servidor.publicar_github("prueba/demo", "v1.1.0", {"demo-v1.1.0.zip": b"x"}, digest=False)
	with pytest.raises(fuentes.ErrorFuente) as error:
		fuentes.comprobar(apoyo_co.ficha_demo("1.0.0"), CONFIG)
	assert "suma" in error.value.mensaje


def test_latest_mismo_digest_no_ofrece_y_otro_si(servidor):
	paquete = b"compilacion"
	servidor.publicar_github("prueba/builds", "latest", {
		"ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip": paquete,
		"ffmpeg-n8.1-latest-win64-gpl-shared-8.1.zip": b"vieja",
		"checksums.sha256": f"{sha(paquete)}  ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip\n".encode(),
	}, latest=False)
	assert fuentes.comprobar(_ffmpeg("sha256:" + sha(paquete)), CONFIG) is None
	nueva = fuentes.comprobar(_ffmpeg(), CONFIG)
	assert nueva is not None and nueva.version == ""
	assert nueva.texto == "Compilación nueva de la rama 9.0 (1 de noviembre de 2026)"
	assert nueva.asset == {"digest": "sha256:" + sha(paquete), "actualizado": "2026-11-01T10:00:00Z"}
	assert not nueva.cambio_grande
	assert servidor.peticiones.count("/repos/prueba/builds/releases/tags/latest") == 2, "una petición a la API por comprobación"


def test_latest_con_rama_nueva_es_cambio_grande(servidor):
	paquete = b"rama nueva"
	servidor.publicar_github("prueba/builds", "latest", {
		"ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip": b"igual",
		"ffmpeg-n9.1-latest-win64-gpl-shared-9.1.zip": paquete,
		"checksums.sha256": f"{sha(paquete)}  ffmpeg-n9.1-latest-win64-gpl-shared-9.1.zip\n".encode(),
	}, latest=False)
	nueva = fuentes.comprobar(_ffmpeg("sha256:" + sha(b"igual")), CONFIG)
	assert nueva.rama == "9.1" and nueva.cambio_grande and nueva.texto.startswith("Rama 9.1")


def test_msys2_detecta_la_version_nueva_del_principal(servidor):
	principal, otro = "mingw-w64-ucrt-x86_64-libarchive", "mingw-w64-ucrt-x86_64-zstd"
	indice = apoyo_co.indice_msys2({principal: ("3.8.12-1", "b" * 64, 2000), otro: ("1.5.7-2", "c" * 64, 300)})
	url = servidor.poner("/mingw/ucrt64/ucrt64.db", indice)
	ficha = apoyo_co.ficha_demo("3.8.11", id="libarchive", version_paquete="3.8.11-1", verificacion={"tipo": "msys2"}, fuente={
		"tipo": "msys2", "indice": url, "principal": principal,
		"paquetes": {principal: {"extraer": {"ucrt64/bin/libarchive-13.dll": "libarchive-13.dll"}}, otro: {"extraer": {"ucrt64/bin/libzstd.dll": "libzstd.dll"}}}})
	nueva = fuentes.comprobar(ficha, CONFIG)
	assert nueva.version == "3.8.12" and nueva.version_paquete == "3.8.12-1"
	assert {p.nombre: p.sha256 for p in nueva.paquetes} == {
		f"{principal}-3.8.12-1-any.pkg.tar.zst": "b" * 64, f"{otro}-1.5.7-2-any.pkg.tar.zst": "c" * 64}
	assert nueva.paquetes[0].url.startswith(servidor.base + "/mingw/ucrt64/")
	assert fuentes.comprobar(dict(ficha, version_paquete="3.8.12-1"), CONFIG) is None


def test_fuente_url_con_sumas(servidor):
	servidor.poner("/version.txt", "v2.1\n")
	servidor.poner("/sumas.txt", f"{'d' * 64} *herramienta-2.1.zip\n")
	ficha = apoyo_co.ficha_demo("2.0", verificacion={"tipo": "sha256sums", "asset": "sumas.txt"}, fuente={
		"tipo": "url", "url_version": servidor.base + "/version.txt", "formato_version": "texto",
		"url_paquete": servidor.base + "/herramienta-{version}.zip", "url_sumas": servidor.base + "/sumas.txt", "extraer": {"a": "a"}})
	nueva = fuentes.comprobar(ficha, CONFIG)
	assert nueva.version == "2.1" and nueva.paquetes[0].sha256 == "d" * 64


def test_error_del_servidor_da_mensaje_en_espanol(servidor):
	servidor.poner("/repos/prueba/demo/releases/latest", "no", estado=404)
	with pytest.raises(fuentes.ErrorFuente) as error:
		fuentes.comprobar(apoyo_co.ficha_demo(), CONFIG)
	assert "404" in error.value.mensaje


def test_gestor_guarda_lo_nuevo_y_las_omitidas(servidor, tmp_path):
	entorno = apoyo_co.crear_entorno(tmp_path)
	paquete = apoyo_co.zip_de({"demo-v1.1.0/demo.exe": "demo v1.1.0"})
	servidor.publicar_github("prueba/demo", "v1.1.0", {"demo-v1.1.0.zip": paquete, "SHA256SUMS": f"{sha(paquete)}  demo-v1.1.0.zip".encode()})
	g = apoyo_co.gestor(entorno)
	assert set(g.comprobar()) == {"demo"}
	assert g.novedades_sin_omitir() == ["demo"]
	fila = g.filas()[0]
	assert (fila.nueva, fila.origen, fila.elegible) == ("1.1.0", "Línea base", True)
	assert g.omitir("demo")
	assert g.novedades_sin_omitir() == []
	fila = g.filas()[0]
	assert fila.omitida and not fila.elegible and "omitida" in fila.nueva
	assert estado.leer_estado(entorno)["ultima_comprobacion"] > 0


def test_utilidades():
	assert fuentes.sumas_de_texto(f"{'A' * 64}  ./dir/x.zip\n# nada\n") == {"x.zip": "a" * 64}
	assert fuentes.fecha_legible("2026-11-01T12:00:00Z") == "1 de noviembre de 2026"
	assert fuentes.version_sin_revision("1~2.0-3") == "2.0"
	assert fichas.comparar_versiones("26.06", "26.6") == 0
	assert fichas.comparar_versiones("1.10.0", "1.9.9") == 1
	assert fichas.sustituir("n{rama}-{version}", version="9.0.2", rama="9.0") == "n9.0-9.0.2"
	assert fichas.sustituir("7z{version_sin_punto}-extra.7z", version="26.06") == "7z2606-extra.7z"
