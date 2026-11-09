# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Genera ``data/bin/linea_base.json`` (y ``componentes.json``) desde ``data/bin`` y las fuentes (diseño 2.0, 6.2 y 6.9).

La línea base dice lo que trae y ha probado esta versión de zCommander: para
cada componente, su ficha (origen, verificación, prueba, uso) y la lista de
archivos instalados hoy en ``data/bin/<carpeta>`` con su SHA-256 y su tamaño.
Lo que no sale del disco (de dónde se descarga cada componente y cómo se
prueba) vive en ``PLANTILLAS``, aquí abajo: es la fuente única.

Uso::

	python tools/preparar_componentes.py               # escribe linea_base.json
	python tools/preparar_componentes.py --componentes # y también componentes.json (lo instalado = la base)
	python tools/preparar_componentes.py --comprobar   # falla si alguno no está al día (no escribe nada)
	python tools/preparar_componentes.py --descargar   # vuelve a bajar los paquetes exactos y comprueba sus sumas

``--descargar`` pide permiso antes de usar la red (unos 120 MB) y descarga a
una carpeta temporal que se borra al terminar; no toca ``data/bin``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

from app.core.version import APP_VERSION  # noqa: E402
from app.services.componentes import fichas  # noqa: E402

BIN = RAIZ / "data" / "bin"
MSYS2 = "https://mirror.msys2.org/mingw/ucrt64/"


def _msys2(nombre: str, version: str, sha256: str) -> dict:
	return {"paquete": f"mingw-w64-ucrt-x86_64-{nombre}", "url": f"{MSYS2}mingw-w64-ucrt-x86_64-{nombre}-{version}-any.pkg.tar.zst",
		"sha256": sha256}


#: Fichas sin ``archivos`` (que se calculan del disco). Orígenes y sumas: docs/investigacion/binarios-descargados.md.
PLANTILLAS: list[dict] = [
	{
		"id": "rclone", "nombre": "rclone", "version": "1.76.0", "licencia": "MIT", "dueno": "zc.nubes", "carpeta": "rclone",
		"licencias": ["LICENCIA-MIT.txt"],
		"fuente": {
			"tipo": "github", "repositorio": "rclone/rclone", "etiqueta": "", "rama": "",
			"patron_asset": "rclone-v{version}-windows-amd64.zip", "version_desde": "tag_name",
			"extraer": {"rclone-v{version}-windows-amd64/rclone.exe": "rclone.exe", "rclone-v{version}-windows-amd64/README.txt": "README.txt"},
		},
		"verificacion": {"tipo": "sha256sums", "asset": "SHA256SUMS"},
		"prueba": {"ejecutable": "rclone.exe", "argumentos": ["version"], "salida_contiene": "rclone v{version}", "tiempo_s": 20},
		"en_uso": {"procesos": ["rclone.exe"], "detener": True, "esperar_s": 0, "al_reiniciar": False},
		"opcional": False, "actualizable": True, "novedades": "https://rclone.org/changelog/",
		"url_paquete_exacta": "https://github.com/rclone/rclone/releases/download/v1.76.0/rclone-v1.76.0-windows-amd64.zip",
		"sha256_paquete": "8b4fd2737ade4e70c057ef4a49deb7cffe94b0fb9d7587c189d149823f21a1dc",
	},
	{
		"id": "libarchive", "nombre": "libarchive", "version": "3.8.11", "version_paquete": "3.8.11-1",
		"licencia": "BSD-2-Clause AND Zlib AND bzip2-1.0.6 AND 0BSD AND BSD-3-Clause AND CC0-1.0 AND LGPL-2.1-or-later",
		"dueno": "nucleo", "carpeta": "libarchive",
		"licencias": [
			"licencias/bzip2/LICENSE", "licencias/libarchive/LICENSE", "licencias/libb2/LICENSE", "licencias/libiconv/COPYING",
			"licencias/libiconv/COPYING.LIB", "licencias/libiconv/libcharset/COPYING.LIB", "licencias/libiconv/README",
			"licencias/xz/COPYING", "licencias/xz/COPYING.0BSD", "licencias/xz/COPYING.GPLv2", "licencias/xz/COPYING.GPLv3",
			"licencias/xz/COPYING.LGPLv2.1", "licencias/zlib/LICENSE", "licencias/zstd/LICENSE",
		],
		"fuente": {
			"tipo": "msys2", "indice": MSYS2 + "ucrt64.db", "principal": "mingw-w64-ucrt-x86_64-libarchive",
			"paquetes": {
				"mingw-w64-ucrt-x86_64-libarchive": {"extraer": {"ucrt64/bin/libarchive-13.dll": "libarchive-13.dll"}},
				"mingw-w64-ucrt-x86_64-zstd": {"extraer": {"ucrt64/bin/libzstd.dll": "libzstd.dll"}},
				"mingw-w64-ucrt-x86_64-zlib": {"extraer": {"ucrt64/bin/zlib1.dll": "zlib1.dll"}},
				"mingw-w64-ucrt-x86_64-xz": {"extraer": {"ucrt64/bin/liblzma-5.dll": "liblzma-5.dll"}},
				"mingw-w64-ucrt-x86_64-lz4": {"extraer": {"ucrt64/bin/liblz4.dll": "liblz4.dll"}},
				"mingw-w64-ucrt-x86_64-libiconv": {"extraer": {"ucrt64/bin/libiconv-2.dll": "libiconv-2.dll"}},
				"mingw-w64-ucrt-x86_64-bzip2": {"extraer": {"ucrt64/bin/libbz2-1.dll": "libbz2-1.dll"}},
				"mingw-w64-ucrt-x86_64-libb2": {"extraer": {"ucrt64/bin/libb2-1.dll": "libb2-1.dll"}},
			},
		},
		"verificacion": {"tipo": "msys2"},
		"prueba": {"tipo": "zcommander", "argumentos": ["--probar-componente", "libarchive"], "tiempo_s": 30},
		"en_uso": {"procesos": [], "detener": False, "esperar_s": 0, "al_reiniciar": True},
		"opcional": False, "actualizable": True, "novedades": "https://github.com/libarchive/libarchive/releases",
		"url_paquete_exacta": MSYS2 + "mingw-w64-ucrt-x86_64-libarchive-3.8.11-1-any.pkg.tar.zst",
		"sha256_paquete": "e883f65d1fd9f06a8d03f35b2668826d7fa1407a2baf1eca050f34eb0f6f0927",
		"paquetes_exactos": [
			_msys2("libarchive", "3.8.11-1", "e883f65d1fd9f06a8d03f35b2668826d7fa1407a2baf1eca050f34eb0f6f0927"),
			_msys2("zstd", "1.5.7-2", "dbdb8427280046a2b41697780aa4c52983b708082b0da4755951dc3bea96ca89"),
			_msys2("zlib", "1.4-2", "172541cf5e2391a402f092104988699b0163129d22be1d6b4b201bfb84af6fcf"),
			_msys2("xz", "5.8.4-1", "a9d771f816d8c0c5bde152ffb27a687ede91079b8e77e5b8297efa3b5a835934"),
			_msys2("lz4", "1.11.0-1", "83a8d234445f4d8b79424799d025df27a3b969415b7418fbe78fcdcb3cd98a0d"),
			_msys2("libiconv", "1.19.1-1", "8a45dc317a285a036bddd79e01505d67b79e44ff49fc3f6e7177a5ea98d098cf"),
			_msys2("bzip2", "1.0.8-4", "f03a2174034ddd2d96cecd34f617c5f8e2ef86c812b8d2bb3b8875257f2c8bfa"),
			_msys2("libb2", "0.98.1-3", "dfb554635119d3c46adb00c9d0c589bb38d1cb0781b10ecf31de07ce388bd0c0"),
		],
	},
	{
		"id": "7za", "nombre": "7-Zip Extra (7za)", "version": "26.06", "licencia": "LGPL-2.1-or-later AND BSD-3-Clause",
		"dueno": "nucleo", "carpeta": "7za", "licencias": ["LICENCIA.txt"],
		"fuente": {
			"tipo": "github", "repositorio": "ip7z/7zip", "etiqueta": "", "rama": "",
			"patron_asset": "7z{version_sin_punto}-extra.7z", "version_desde": "tag_name", "extraer": {"x64/7za.exe": "7za.exe"},
		},
		"verificacion": {"tipo": "digest_github"},
		"prueba": {"ejecutable": "7za.exe", "argumentos": ["i"], "salida_contiene": "7-Zip (a) {version}", "tiempo_s": 20},
		"en_uso": {"procesos": ["7za.exe"], "detener": False, "esperar_s": 30, "al_reiniciar": False},
		"opcional": False, "actualizable": True, "novedades": "https://www.7-zip.org/history.txt",
		"url_paquete_exacta": "https://github.com/ip7z/7zip/releases/download/26.06/7z2606-extra.7z",
		"sha256_paquete": "396c180f12d2247c24b0b1fcd482c6fc2a2700f61211ffede1061dd971f5e104",
	},
	{
		"id": "ffmpeg", "nombre": "FFmpeg", "version": "9.0.2", "licencia": "GPL-3.0-or-later", "dueno": "nucleo", "carpeta": "ffmpeg",
		"licencias": ["LICENCIA-GPL3.txt"],
		"fuente": {
			"tipo": "github", "repositorio": "FFmpeg-Builds/FFmpeg-Builds", "etiqueta": "latest", "rama": "9.0",
			"patron_asset": "ffmpeg-n{rama}-latest-win64-gpl-shared-{rama}.zip", "version_desde": "programa",
			"extraer": {"*/bin/*.exe": ".", "*/bin/*.dll": "."},
		},
		"verificacion": {"tipo": "sha256sums", "asset": "checksums.sha256"},
		"prueba": {
			"ejecutable": "ffmpeg.exe", "argumentos": ["-version"], "salida_contiene": "ffmpeg version", "tiempo_s": 20,
			"adicionales": [{"ejecutable": "ffprobe.exe", "argumentos": ["-version"], "salida_contiene": "ffprobe version"}],
		},
		"en_uso": {"procesos": ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"], "detener": False, "esperar_s": 30, "al_reiniciar": False},
		"opcional": False, "actualizable": True, "novedades": "https://ffmpeg.org/download.html#releases",
		# Compilación de la etiqueta «latest» instalada (digest y updated_at del asset en la API de GitHub, 8 de noviembre de 2026).
		"asset": {"digest": "sha256:76a77a688e6bb82c4671ad600fc4df059a7c7d689d027fe527a27f89a5def7be", "actualizado": "2026-11-08T12:54:28Z"},
		"url_paquete_exacta": "https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip",
		"sha256_paquete": "76a77a688e6bb82c4671ad600fc4df059a7c7d689d027fe527a27f89a5def7be",
	},
	{
		"id": "nvda", "nombre": "Complemento de zCommander para NVDA", "version": APP_VERSION, "licencia": "GPL-3.0-or-later",
		"dueno": "nucleo", "carpeta": "nvda", "licencias": [], "opcional": True, "actualizable": False,
	},
]

#: Orden de las claves en el JSON (lo demás va detrás, en orden alfabético).
ORDEN = ("id", "nombre", "version", "version_paquete", "licencia", "dueno", "carpeta", "fuente", "verificacion", "prueba", "en_uso",
	"opcional", "actualizable", "novedades", "asset", "url_paquete_exacta", "sha256_paquete", "paquetes_exactos", "archivos", "licencias")


def _ordenar(ficha: dict) -> dict:
	claves = [c for c in ORDEN if c in ficha] + sorted(c for c in ficha if c not in ORDEN)
	return {c: ficha[c] for c in claves}


def generar(bin_: Path = BIN) -> dict:
	"""La línea base con los archivos que hay hoy en ``bin_``."""
	componentes = []
	for plantilla in PLANTILLAS:
		ficha = json.loads(json.dumps(plantilla))
		# Lo que genera zCommander (el complemento de NVDA, bloque NV) cambia con cada compilación: no se fijan sus sumas.
		ficha["archivos"] = fichas.sumas_de_carpeta(bin_ / ficha["carpeta"]) if ficha.get("actualizable", True) else []
		componentes.append(_ordenar(ficha))
	datos = {"formato": fichas.FORMATO, "aplicacion": APP_VERSION, "componentes": componentes}
	problemas = fichas.validar(datos, linea_base=True)
	if problemas:
		raise SystemExit("La línea base no es válida:\n" + "\n".join(problemas))
	return datos


def instalados_desde(base: dict) -> dict:
	"""``componentes.json`` inicial: lo instalado es la línea base (sin sus campos exclusivos)."""
	datos = {"formato": fichas.FORMATO, "componentes": [fichas.sin_campos_de_base(f) for f in base["componentes"]]}
	problemas = fichas.validar(datos, linea_base=False)
	if problemas:
		raise SystemExit("componentes.json no es válido:\n" + "\n".join(problemas))
	return datos


def _faltan_archivos(base: dict, bin_: Path) -> list[str]:
	return [f"{f['id']}: carpeta vacía o inexistente" for f in base["componentes"] if not f["archivos"] and not f.get("opcional")
		and not (bin_ / f["carpeta"]).is_dir()]


def descargar_y_comprobar(base: dict) -> int:
	"""Vuelve a bajar los paquetes exactos de la línea base y comprueba su SHA-256 (no toca ``data/bin``)."""
	from app.core import descargas, red

	paquetes = []
	for ficha in base["componentes"]:
		if ficha.get("paquetes_exactos"):
			paquetes += [(ficha["id"], p["url"], p["sha256"]) for p in ficha["paquetes_exactos"]]
		elif ficha.get("url_paquete_exacta"):
			paquetes.append((ficha["id"], ficha["url_paquete_exacta"], ficha["sha256_paquete"]))
	print(f"Se van a descargar {len(paquetes)} paquetes (unos 120 MB) de GitHub y MSYS2 para comprobar sus sumas.")
	if input("¿Continuar? [s/N] ").strip().casefold() not in ("s", "si", "sí"):
		print("Cancelado: no se ha descargado nada.")
		return 1
	config = red.ConfiguracionRed("zCommander", APP_VERSION)
	carpeta = Path(tempfile.mkdtemp(prefix="zc-linea-base-"))
	fallos = 0
	try:
		for id, url, suma in paquetes:
			try:
				descargas.descargar(config, url, carpeta, sha256=suma)
				print(f"Correcto: {id} {url.rsplit('/', 1)[-1]}")
			except red.ErrorHTTP as error:
				fallos += 1
				print(f"FALLO: {id} {url}: {error.mensaje}")
	finally:
		shutil.rmtree(carpeta, ignore_errors=True)
	return 1 if fallos else 0


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--componentes", action="store_true", help="Escribe también componentes.json (lo instalado = la base).")
	analizador.add_argument("--comprobar", action="store_true", help="Falla si linea_base.json no coincide con data/bin.")
	analizador.add_argument("--descargar", action="store_true", help="Vuelve a bajar los paquetes exactos y comprueba sus sumas.")
	opciones = analizador.parse_args(argumentos)
	base = generar()
	faltan = _faltan_archivos(base, BIN)
	if faltan:
		print("Faltan componentes en data/bin:\n" + "\n".join(faltan))
		return 1
	if opciones.descargar:
		return descargar_y_comprobar(base)
	archivo = BIN / fichas.NOMBRE_LINEA_BASE
	if opciones.comprobar:
		actual = archivo.read_text(encoding="utf-8") if archivo.is_file() else ""
		if actual != fichas.a_texto(base):
			print("data/bin/linea_base.json no está al día: python tools/preparar_componentes.py")
			return 1
		print("linea_base.json al día.")
		return 0
	fichas.escribir(archivo, base)
	print(f"Escrito {archivo.relative_to(RAIZ)}")
	if opciones.componentes:
		fichas.escribir(BIN / fichas.NOMBRE_INSTALADOS, instalados_desde(base))
		print(f"Escrito {(BIN / fichas.NOMBRE_INSTALADOS).relative_to(RAIZ)}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
