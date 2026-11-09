# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Reúne las fuentes exactas de los componentes LGPL y GPL de una versión (diseño 2.0, 2.4).

Uso (desde la raíz, con el entorno virtual del proyecto)::

	python tools/fuentes_terceros.py                    # solo dice qué bajaría y adónde
	python tools/fuentes_terceros.py --descargar        # pregunta y, si se acepta, descarga
	python tools/fuentes_terceros.py --descargar --si   # sin preguntar (permiso ya dado)
	python tools/fuentes_terceros.py --destino otra/carpeta

Sin ``--descargar`` no se conecta a nada. Con ``--descargar`` (y el permiso
expreso de quien publica) baja por https:

- Los sdist de PyPI de wxPython, paramiko, py7zr y mutagen, en la versión que
  lleva zCommander, comprobando la suma SHA-256 que publica PyPI.
- El paquete fuente de MSYS2 de libiconv (``.src.tar.zst``), el código de 7-Zip
  (``7z<versión>-src.7z``), el de FFmpeg del commit exacto de la compilación
  usada (lo saca de ``ffmpeg -version``), los guiones de FFmpeg-Builds y el
  código de NVDA (del que sale ``nvdaControllerClient64.dll``).

Lo deja en ``%USERPROFILE%\\SynologyDrive\\web\\zCommander\\fuentes\\<versión>\\``
(se publica como ``https://xebolax.synology.me/zCommander/fuentes/<versión>/``) con
un ``SHA256SUMS.txt``. Esas fuentes se conservan al menos tres años después de la
última versión que las use (``OFERTA-DE-FUENTES.md``).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

SERVIDOR = Path.home() / "SynologyDrive" / "web" / "zCommander" / "fuentes"
PYPI = "https://pypi.org/pypi"
MSYS2_FUENTES = "https://mirror.msys2.org/mingw/sources"
GITHUB = "https://github.com"


@dataclass(frozen=True)
class Fuente:
	"""Un archivo de fuentes que hay que guardar."""

	componente: str
	url: str
	archivo: str
	sha256: str = ""


def version_app() -> str:
	texto = (RAIZ / "app" / "core" / "version.py").read_text(encoding="utf-8")
	encontrada = re.search(r"APP_VERSION\s*=\s*[\"']([^\"']+)[\"']", texto)
	return encontrada.group(1) if encontrada else "0.0.0"


def _version_paquete(nombre: str) -> str:
	import importlib.metadata

	return importlib.metadata.version(nombre)


def _version_base(identificador: str) -> str:
	datos = json.loads((RAIZ / "data" / "bin" / "linea_base.json").read_text(encoding="utf-8"))
	return next(str(c["version"]) for c in datos["componentes"] if c["id"] == identificador)


def commit_ffmpeg(ruta: Path | None = None) -> str:
	"""Commit de FFmpeg de la compilación instalada (``n9.0.2-48-gd4070a14ce-20261108`` → ``d4070a14ce``)."""
	ruta = ruta or RAIZ / "data" / "bin" / "ffmpeg" / "ffmpeg.exe"
	salida = subprocess.run([str(ruta), "-hide_banner", "-version"], capture_output=True, text=True, timeout=30,  # noqa: S603
		check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
	encontrado = re.search(r"-g([0-9a-f]{7,40})\b", salida)
	if not encontrado:
		raise RuntimeError(f"No se encuentra el commit de FFmpeg en «{salida.splitlines()[:1]}»")
	return encontrado.group(1)


def sdist_pypi(config, proyecto: str, version: str, base: str = PYPI) -> Fuente:
	"""El sdist de PyPI de ``proyecto`` ``version`` con su SHA-256 (API JSON de PyPI)."""
	from app.core import red

	respuesta = red.obtener(config, f"{base}/{proyecto}/{version}/json")
	datos = json.loads(respuesta.cuerpo.decode("utf-8"))
	for archivo in datos.get("urls", []):
		if archivo.get("packagetype") == "sdist":
			return Fuente(proyecto, archivo["url"], archivo["filename"], archivo.get("digests", {}).get("sha256", ""))
	raise RuntimeError(f"PyPI no tiene sdist de {proyecto} {version}")


def plan(*, ffmpeg: str | None = None) -> tuple[list[tuple[str, str]], list[Fuente]]:
	"""(sdist de PyPI por pedir como (proyecto, versión), descargas directas)."""
	pypi = [("wxPython", _version_paquete("wxPython")), ("paramiko", _version_paquete("paramiko")),
		("py7zr", _version_paquete("py7zr")), ("mutagen", "1.48.1")]
	siete = _version_base("7za").replace(".", "")
	directas = [
		Fuente("libiconv (libarchive)", f"{MSYS2_FUENTES}/mingw-w64-libiconv-1.19.1-1.src.tar.zst",
			"mingw-w64-libiconv-1.19.1-1.src.tar.zst"),
		Fuente("7-Zip (7za)", f"{GITHUB}/ip7z/7zip/releases/download/{_version_base('7za')}/7z{siete}-src.7z", f"7z{siete}-src.7z"),
		Fuente("FFmpeg-Builds (guiones de la compilación)", f"{GITHUB}/FFmpeg-Builds/FFmpeg-Builds/archive/refs/heads/master.tar.gz",
			"FFmpeg-Builds-master.tar.gz"),
		Fuente("NVDA (nvdaHelper/client: nvdaControllerClient)", f"{GITHUB}/nvaccess/nvda/archive/refs/heads/master.tar.gz",
			"nvda-master.tar.gz"),
	]
	if ffmpeg:
		directas.insert(2, Fuente("FFmpeg", f"{GITHUB}/FFmpeg/FFmpeg/archive/{ffmpeg}.tar.gz", f"FFmpeg-{ffmpeg}.tar.gz"))
	return pypi, directas


def descargar_todo(destino: Path, *, config=None, base_pypi: str = PYPI, directas: list[Fuente] | None = None,
		pypi: list[tuple[str, str]] | None = None) -> list[Path]:
	"""Descarga todo a ``destino`` y escribe ``SHA256SUMS.txt``; devuelve los archivos."""
	from app.core import descargas, red

	config = config or red.ConfiguracionRed("zCommander", version_app(), tiempo_lectura=120)
	if pypi is None or directas is None:
		pypi_plan, directas_plan = plan(ffmpeg=commit_ffmpeg())
		pypi = pypi_plan if pypi is None else pypi
		directas = directas_plan if directas is None else directas
	fuentes = [sdist_pypi(config, proyecto, version, base_pypi) for proyecto, version in pypi] + list(directas)
	destino.mkdir(parents=True, exist_ok=True)
	hechos = []
	for fuente in fuentes:
		print(f"Descargando {fuente.componente}: {fuente.url}")
		hechos.append(descargas.descargar(config, fuente.url, destino / fuente.archivo, sha256=fuente.sha256))
	lineas = [f"{descargas.sha256_de(ruta)}  {ruta.name}" for ruta in hechos]
	(destino / "SHA256SUMS.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
	return hechos


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--descargar", action="store_true", help="Descargar (por defecto solo se muestra el plan).")
	analizador.add_argument("--si", action="store_true", help="No preguntar antes de descargar.")
	analizador.add_argument("--destino", type=Path, help="Carpeta de destino (por defecto, la del servidor para esta versión).")
	opciones = analizador.parse_args(argumentos)
	for flujo in (sys.stdout, sys.stderr):
		if hasattr(flujo, "reconfigure"):
			flujo.reconfigure(errors="replace")
	destino = opciones.destino or SERVIDOR / version_app()
	try:
		ffmpeg = commit_ffmpeg()
	except (OSError, RuntimeError, subprocess.SubprocessError) as error:
		print(f"AVISO: {error}")
		ffmpeg = None
	pypi, directas = plan(ffmpeg=ffmpeg)
	print(f"Destino: {destino}")
	for proyecto, version in pypi:
		print(f"- {proyecto} {version}: sdist de PyPI (con su SHA-256)")
	for fuente in directas:
		print(f"- {fuente.componente}: {fuente.url}")
	if not opciones.descargar:
		print("No se ha descargado nada. Para descargar: python tools/fuentes_terceros.py --descargar")
		return 0
	if not opciones.si:
		respuesta = input(f"¿Descargar estas {len(pypi) + len(directas)} fuentes a {destino}? (s/N): ").strip().lower()
		if respuesta not in {"s", "si", "sí"}:
			print("Cancelado: no se ha descargado nada.")
			return 1
	try:
		hechos = descargar_todo(destino, pypi=pypi, directas=directas)
	except Exception as error:  # noqa: BLE001 - herramienta de consola: se informa y se sale con 1
		print(f"ERROR: {error}")
		return 1
	print(f"Guardadas {len(hechos)} fuentes en {destino}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
