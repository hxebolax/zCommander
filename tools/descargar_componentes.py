# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Descarga a ``data/bin`` los programas de terceros que zCommander necesita (rclone, libarchive, 7za y FFmpeg).

Los ejecutables y las DLL de ``data/bin`` no van en el repositorio de git
(alguno pasa de los 100 MB que admite GitHub); sí van sus licencias y
``data/bin/linea_base.json``, que dice exactamente qué archivo va en cada
sitio y con qué suma SHA-256. Este script los trae y comprueba cada suma, así
que lo que queda en ``data/bin`` es justo lo que se probó en esta versión.

Uso::

	python tools/descargar_componentes.py             # desde la release de GitHub de esta versión (recomendado)
	python tools/descargar_componentes.py --origen    # desde las fuentes originales (GitHub de cada proyecto y MSYS2)
	python tools/descargar_componentes.py --si        # sin preguntar antes de usar la red
	python tools/descargar_componentes.py --forzar    # vuelve a bajar aunque ya estén bien
	python tools/descargar_componentes.py --crear-paquete  # crea dist/zCommander_v<versión>_componentes.zip (para publicar)

Con ``--origen``, FFmpeg sale de una compilación «latest» que cambia con el
tiempo: si su suma ya no coincide, el script lo dice y no instala nada de
FFmpeg; en ese caso, use el modo por defecto. El paquete de 7za es un .7z que
necesita 7-Zip instalado para abrirse con ``--origen``. Al final se construye también
el complemento para NVDA (``data/bin/nvda``) con ``tools/construir_complemento.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

from app.core.version import APP_VERSION  # noqa: E402

BIN = RAIZ / "data" / "bin"
DIST = RAIZ / "dist"
REPOSITORIO = "hxebolax/zCommander"
#: Lo que no va en git y trae este script: el resto de ``data/bin`` (licencias, README) sí está versionado.
EXTENSIONES_BINARIAS = (".exe", ".dll")


def nombre_paquete(version: str = APP_VERSION) -> str:
	return f"zCommander_v{version}_componentes.zip"


def url_paquete(version: str = APP_VERSION) -> str:
	return f"https://github.com/{REPOSITORIO}/releases/download/v{version}/{nombre_paquete(version)}"


def es_binario(ruta: str) -> bool:
	return ruta.casefold().endswith(EXTENSIONES_BINARIAS)


def leer_base(bin_: Path | None = None) -> dict:
	from app.services.componentes import fichas

	return fichas.leer((bin_ or BIN) / fichas.NOMBRE_LINEA_BASE)


def binarios_esperados(base: dict) -> dict[str, dict]:
	"""``{"rclone/rclone.exe": {"sha256": ..., "tamano": ...}}`` de todos los componentes de la línea base."""
	esperados = {}
	for ficha in base["componentes"]:
		for archivo in ficha.get("archivos") or []:
			if es_binario(archivo["ruta"]):
				esperados[f"{ficha['carpeta']}/{archivo['ruta']}"] = archivo
	return esperados


def _sha256(ruta: Path) -> str:
	suma = hashlib.sha256()
	with ruta.open("rb") as archivo:
		for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
			suma.update(bloque)
	return suma.hexdigest()


def correcto(ruta: Path, esperado: dict) -> bool:
	return ruta.is_file() and ruta.stat().st_size == esperado["tamano"] and _sha256(ruta) == esperado["sha256"]


def pendientes(esperados: dict[str, dict], bin_: Path | None = None) -> list[str]:
	"""Los binarios que faltan en ``bin_`` (``data/bin``) o que no tienen la suma de la línea base."""
	bin_ = bin_ or BIN
	return [relativa for relativa, esperado in esperados.items() if not correcto(bin_ / relativa, esperado)]


def _ruta_segura(nombre: str) -> PurePosixPath:
	ruta = PurePosixPath(nombre.replace("\\", "/"))
	if ruta.is_absolute() or ".." in ruta.parts or any(":" in p for p in ruta.parts):
		raise ValueError(f"Nombre no permitido en el paquete: {nombre}")
	return ruta


def instalar_desde(carpeta: Path, esperados: dict[str, dict], relativas: list[str], bin_: Path | None = None) -> list[str]:
	"""Copia a ``bin_`` (``data/bin``) los archivos de ``carpeta`` cuya suma es la esperada; devuelve los que fallan."""
	bin_ = bin_ or BIN
	fallos = []
	for relativa in relativas:
		origen = carpeta / relativa
		if not correcto(origen, esperados[relativa]):
			fallos.append(relativa)
			continue
		destino = bin_ / relativa
		destino.parent.mkdir(parents=True, exist_ok=True)
		temporal = destino.with_name(destino.name + ".nuevo")
		shutil.copyfile(origen, temporal)
		try:
			temporal.replace(destino)
		except OSError:
			temporal.unlink(missing_ok=True)  # el programa está en uso: no se deja el .nuevo en data/bin
			raise
	return fallos


def _configuracion_red():
	from app.core import red

	return red.ConfiguracionRed("zCommander", APP_VERSION)


def desde_release(esperados: dict[str, dict], relativas: list[str], trabajo: Path) -> list[str]:
	"""Baja el paquete de componentes de la release de GitHub de esta versión y lo instala."""
	from app.core import descargas

	url = url_paquete()
	print(f"Descargando {url}")
	paquete = descargas.descargar(_configuracion_red(), url, trabajo)
	extraido = trabajo / "extraido"
	with zipfile.ZipFile(paquete) as zf:
		for info in zf.infolist():
			if info.is_dir():
				continue
			relativa = _ruta_segura(info.filename).as_posix()
			if relativa not in relativas:
				continue
			destino = extraido / relativa
			destino.parent.mkdir(parents=True, exist_ok=True)
			with zf.open(info) as entrada, destino.open("wb") as salida:
				shutil.copyfileobj(entrada, salida, 1024 * 1024)
	return instalar_desde(extraido, esperados, relativas)


def _paquetes_de_origen(ficha: dict) -> list[tuple[str, str, dict[str, str]]]:
	"""``[(url, sha256, mapa_extraer)]`` de un componente según su ficha de la línea base."""
	from app.services.componentes import fichas

	fuente = ficha.get("fuente") or {}
	if ficha.get("paquetes_exactos"):
		mapas = fuente.get("paquetes") or {}
		return [(p["url"], p["sha256"], (mapas.get(p["paquete"]) or {}).get("extraer") or {}) for p in ficha["paquetes_exactos"]]
	if ficha.get("url_paquete_exacta"):
		version, rama = ficha.get("version", ""), fuente.get("rama", "")
		mapa = {fichas.sustituir(k, version=version, rama=rama): fichas.sustituir(v, version=version, rama=rama)
			for k, v in (fuente.get("extraer") or {}).items()}
		return [(ficha["url_paquete_exacta"], ficha["sha256_paquete"], mapa)]
	return []


def desde_origen(base: dict, esperados: dict[str, dict], relativas: list[str], trabajo: Path) -> list[str]:
	"""Baja cada paquete de su proyecto original (comprobando su suma), extrae lo necesario y lo instala."""
	from app.core import descargas, red
	from app.services.componentes.instalar import ErrorComponente, extraer_paquete

	fallos = []
	for ficha in base["componentes"]:
		suyas = [r for r in relativas if r.startswith(ficha["carpeta"] + "/")]
		if not suyas:
			continue
		extraido = trabajo / "extraido" / ficha["carpeta"]
		try:
			for url, suma, mapa in _paquetes_de_origen(ficha):
				print(f"Descargando {url}")
				paquete = descargas.descargar(_configuracion_red(), url, trabajo, sha256=suma)
				# 7za se extrae con py7zr; si hiciera falta 7-Zip, se usa el que ya se haya instalado aquí.
				extraer_paquete(paquete, mapa, extraido, siete_zip=lambda: _siete_zip(trabajo))
		except (red.ErrorHTTP, ErrorComponente) as error:
			print(f"FALLO en {ficha['id']}: {getattr(error, 'mensaje', error)}")
			fallos += suyas
			continue
		fallos += instalar_desde(trabajo / "extraido", esperados, suyas)
	return fallos


def _siete_zip(_trabajo: Path) -> Path | None:
	"""El 7za de ``data/bin`` o el 7-Zip instalado: el paquete de 7za es un .7z que py7zr no siempre abre."""
	import os

	candidatos = [BIN / "7za" / "7za.exe"]
	candidatos += [Path(os.environ[v]) / "7-Zip" / "7z.exe" for v in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)") if os.environ.get(v)]
	return next((c for c in candidatos if c.is_file()), None)


def construir_complemento_nvda() -> None:
	from tools import construir_complemento

	if construir_complemento.main([]) != 0:
		print("AVISO: no se pudo construir el complemento para NVDA (data/bin/nvda).")


class ErrorPaquete(Exception):
	"""``data/bin`` no coincide con la línea base: no se puede crear el paquete de componentes."""


def crear_paquete(esperados: dict[str, dict], destino: Path | None = None, *, bin_: Path | None = None,
		version: str = APP_VERSION) -> Path:
	"""Crea el ZIP de componentes de la release con los binarios de ``bin_`` (deben estar al día).

	Lo usa también ``tools/publicar.py`` para dejarlo en ``dist`` junto al ZIP de la aplicación.
	"""
	destino = destino or DIST
	bin_ = bin_ or BIN
	malos = pendientes(esperados, bin_)
	if malos:
		raise ErrorPaquete("data/bin no coincide con linea_base.json; no se crea el paquete:\n" + "\n".join(malos))
	destino.mkdir(parents=True, exist_ok=True)
	zip_ = destino / nombre_paquete(version)
	with zipfile.ZipFile(zip_, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
		for relativa in sorted(esperados):
			zf.write(bin_ / relativa, relativa)
	print(f"Creado {zip_} ({zip_.stat().st_size / 1048576:.0f} MB, {len(esperados)} archivos)")
	return zip_


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--origen", action="store_true", help="Descarga de las fuentes originales en lugar de la release de zCommander.")
	analizador.add_argument("--si", action="store_true", help="No pregunta antes de usar la red.")
	analizador.add_argument("--forzar", action="store_true", help="Vuelve a bajar todo aunque ya esté bien.")
	analizador.add_argument("--crear-paquete", action="store_true", help="Crea dist/zCommander_v<versión>_componentes.zip.")
	analizador.add_argument("--sin-nvda", action="store_true", help="No construye el complemento para NVDA.")
	opciones = analizador.parse_args(argumentos)
	base = leer_base()
	esperados = binarios_esperados(base)
	if opciones.crear_paquete:
		try:
			crear_paquete(esperados)
		except ErrorPaquete as error:
			print(error)
			return 1
		return 0
	relativas = list(esperados) if opciones.forzar else pendientes(esperados)
	if not relativas:
		print("Los componentes de data/bin ya están completos y con las sumas correctas.")
	else:
		origen = "las fuentes originales (GitHub y MSYS2)" if opciones.origen else f"la release v{APP_VERSION} de {REPOSITORIO}"
		print(f"Faltan {len(relativas)} archivos en data/bin. Se descargarán de {origen} (unos 120 MB).")
		if not opciones.si and input("¿Continuar? [s/N] ").strip().casefold() not in ("s", "si", "sí"):
			print("Cancelado: no se ha descargado nada.")
			return 1
		trabajo = Path(tempfile.mkdtemp(prefix="zc-componentes-"))
		try:
			if opciones.origen:
				fallos = desde_origen(base, esperados, relativas, trabajo)
			else:
				from app.core import red

				try:
					fallos = desde_release(esperados, relativas, trabajo)
				except red.ErrorHTTP as error:
					print(f"No se pudo descargar el paquete de la release: {error.mensaje}")
					print("Pruebe con --origen para bajarlos de las fuentes originales.")
					return 1
				except (zipfile.BadZipFile, ValueError) as error:
					print(f"El paquete de la release no es válido; no se ha instalado nada: {error}")
					return 1
		except PermissionError as error:
			print(f"No se pudo sustituir {error.filename}: cierre zCommander (o el programa que lo use) y repita.")
			return 1
		finally:
			shutil.rmtree(trabajo, ignore_errors=True)
		if fallos:
			print("No se pudieron instalar con la suma correcta:\n" + "\n".join(f"- {f}" for f in fallos))
			if opciones.origen:
				print("Si es FFmpeg, su compilación «latest» ha cambiado: use el modo por defecto (sin --origen).")
			return 1
		print(f"Instalados {len(relativas)} archivos en data/bin con sus sumas comprobadas.")
	if not opciones.sin_nvda:
		construir_complemento_nvda()
	return 0


if __name__ == "__main__":
	sys.exit(main())
