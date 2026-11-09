# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Crea el ZIP portable ``dist/zCommander_v<versión>.zip`` desde ``build/ZCommander`` (diseño 2.0, 17.3).

Uso (desde la raíz del proyecto, después de ``python setup_cx.py build``)::

	python tools/empaquetar.py

Nunca empaqueta datos personales ni restos de ejecución: si la copia compilada
se probó, su ``data/`` puede tener configuración, registros, complementos y
sonidos de la persona, plantillas propias o restos del actualizador de
componentes en ``data/bin`` (respaldos, pendientes, lo entrante, el diario y el
estado). Todo eso se omite y se dice en la salida. Termina con código 1 si no
hay compilación.

``tools/publicar.py`` y ``setup_cx.py`` usan estas mismas reglas (``omitir``).
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORIGEN = RAIZ / "build" / "ZCommander"
#: Carpetas de ``data`` que son de la persona (las mismas que ``DATA_PROHIBIDO`` de ``setup_cx.py``; lo comprueba una prueba).
PERSONALES = frozenset({"config", "logs", "temp", "cache", "db", "sessions", "backups", "downloads", "plugins", "sounds_usuario",
	"plantillas"})
#: Carpetas de ``data/bin`` del actualizador de componentes (6.3, 6.6): respaldos, pendientes y lo entrante de una actualización.
BIN_CARPETAS_EXCLUIDAS = frozenset({"respaldo", ".pendiente", ".entrante"})
#: Carpetas temporales de una sustitución a medias (``<id>.nueva``, ``<id>.vieja``).
BIN_SUFIJOS_EXCLUIDOS = (".nueva", ".vieja")
#: Archivos de estado del actualizador de componentes en ``data/bin`` (se crean al usar la aplicación).
BIN_ARCHIVOS_EXCLUIDOS = frozenset({"estado_componentes.json", "instalando.json", "integracion.json"})
#: Restos de ejecución en cualquier sitio.
SUFIJOS_TEMPORALES = frozenset({".log", ".tmp", ".bak", ".parcial"})
CARPETAS_TEMPORALES = frozenset({"__pycache__"})


def version() -> str:
	texto = (RAIZ / "app" / "core" / "version.py").read_text(encoding="utf-8")
	encontrada = re.search(r"APP_VERSION\s*=\s*[\"']([^\"']+)[\"']", texto)
	return encontrada.group(1) if encontrada else "0.0.0"


def omitir_de_bin(relativa: Path) -> bool:
	"""Restos del actualizador de componentes; ``relativa`` es relativa a ``data/bin``."""
	partes = relativa.parts
	if not partes:
		return False
	primera = partes[0]
	if primera in BIN_CARPETAS_EXCLUIDAS or primera.endswith(BIN_SUFIJOS_EXCLUIDOS):
		return True
	return len(partes) == 1 and primera in BIN_ARCHIVOS_EXCLUIDOS


def omitir(relativa: Path) -> bool:
	"""Carpetas personales de ``data/``, restos del actualizador de componentes y restos de ejecución.

	``relativa`` es relativa a la carpeta de la compilación (``data/...``, ``lib/...``).
	"""
	partes = relativa.parts
	if len(partes) >= 2 and partes[0] == "data":
		if partes[1] in PERSONALES:
			return True
		if partes[1] == "bin" and omitir_de_bin(Path(*partes[2:])):
			return True
	if any(parte in CARPETAS_TEMPORALES for parte in partes):
		return True
	return relativa.suffix.lower() in SUFIJOS_TEMPORALES


def empaquetar(origen: Path = ORIGEN, destino: Path | None = None) -> tuple[Path, int, int]:
	"""Devuelve (zip creado, archivos incluidos, archivos omitidos)."""
	if not (origen / "ZCommander.exe").is_file():
		raise FileNotFoundError(f"No hay compilación en {origen}: ejecute antes «python setup_cx.py build».")
	destino = destino or RAIZ / "dist" / f"zCommander_v{version()}.zip"
	destino.parent.mkdir(parents=True, exist_ok=True)
	incluidos = omitidos = 0
	temporal = destino.with_suffix(".zip.tmp")
	with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archivo:
		for ruta in sorted(origen.rglob("*")):
			if not ruta.is_file():
				continue
			relativa = ruta.relative_to(origen)
			if omitir(relativa):
				omitidos += 1
				continue
			archivo.write(ruta, Path("zCommander") / relativa)
			incluidos += 1
	temporal.replace(destino)
	return destino, incluidos, omitidos


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--origen", type=Path, default=ORIGEN)
	analizador.add_argument("--destino", type=Path)
	opciones = analizador.parse_args(argumentos)
	try:
		zip_creado, incluidos, omitidos = empaquetar(opciones.origen, opciones.destino)
	except FileNotFoundError as error:
		print(error)
		return 1
	tamano = zip_creado.stat().st_size / 1_048_576
	print(f"Creado {zip_creado} ({incluidos} archivos, {tamano:.1f} MB).")
	if omitidos:
		print(f"Omitidos {omitidos} archivos personales, temporales o restos del actualizador de la copia compilada.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
