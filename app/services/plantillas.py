# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Plantillas de archivo nuevo (diseño 2.0, 10.13). Sin wx.

Mayús+F4 ofrece «Archivo vacío» y las plantillas de ``data/docs/plantillas/``
(de serie) y de ``data/plantillas/`` (de la persona; con el mismo nombre, gana
la de la persona). El archivo nuevo toma la extensión de la plantilla si el
nombre no tiene; dentro se sustituyen ``{{fecha}}``, ``{{hora}}``,
``{{nombre}}`` y ``{{usuario}}``.
"""

from __future__ import annotations

import builtins
import getpass
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

#: Tamaño máximo de una plantilla (son textos cortos: así no se carga un archivo enorme por error).
TAMANO_MAXIMO = 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Plantilla:
	nombre: str  # nombre del archivo de la plantilla («Texto con fecha.txt»)
	ruta: Path
	de_serie: bool

	@property
	def extension(self) -> str:
		return self.ruta.suffix

	@property
	def titulo(self) -> str:
		return self.ruta.stem


def disponibles(serie: Path | None = None, propias: Path | None = None) -> list[Plantilla]:
	"""Plantillas de serie y de la persona, por título (la de la persona tapa a la de serie con su nombre)."""
	serie = paths.ruta_plantillas_serie() if serie is None else serie
	propias = (paths.ruta_datos() / "plantillas") if propias is None else propias
	por_nombre: dict[str, Plantilla] = {}
	for carpeta, de_serie in ((serie, True), (propias, False)):
		if not carpeta.is_dir():
			continue
		for ruta in sorted(carpeta.iterdir()):
			if ruta.is_file() and not ruta.name.startswith("."):
				por_nombre[ruta.name.casefold()] = Plantilla(ruta.name, ruta, de_serie)
	return sorted(por_nombre.values(), key=lambda p: p.titulo.casefold())


def nombre_final(nombre: str, plantilla: Plantilla | None) -> str:
	"""El nombre con la extensión de la plantilla si no traía ninguna."""
	nombre = nombre.strip()
	if plantilla is None or Path(nombre).suffix:
		return nombre
	return nombre + plantilla.extension


def contenido(plantilla: Plantilla | None, nombre: str, ahora: float | None = None) -> bytes:
	"""Bytes del archivo nuevo con las variables sustituidas; vacío sin plantilla."""
	if plantilla is None:
		return b""
	datos = plantilla.ruta.read_bytes()[:TAMANO_MAXIMO]
	try:
		texto = datos.decode("utf-8-sig")
	except UnicodeDecodeError:
		return datos  # binaria (un .docx vacío, por ejemplo): se copia tal cual
	momento = time.localtime(ahora)
	try:
		usuario = getpass.getuser()
	except Exception:  # noqa: BLE001 - sin usuario de Windows se deja vacío
		usuario = ""
	valores = {
		"{{fecha}}": time.strftime("%d/%m/%Y", momento),
		"{{hora}}": time.strftime("%H:%M", momento),
		"{{nombre}}": Path(nombre).stem,
		"{{usuario}}": usuario,
	}
	for clave, valor in valores.items():
		texto = texto.replace(clave, valor)
	bom = datos.startswith(b"\xef\xbb\xbf")
	return (b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8")


def preparar_carpeta_propia(serie: Path | None = None, propias: Path | None = None) -> Path:
	"""``data/plantillas`` (la crea con una copia de las de serie si no existe) — orden ``plantillas_archivo``."""
	serie = paths.ruta_plantillas_serie() if serie is None else serie
	destino = (paths.ruta_datos() / "plantillas") if propias is None else propias
	if not destino.exists():
		destino.mkdir(parents=True, exist_ok=True)
		if serie.is_dir():
			for ruta in serie.iterdir():
				if ruta.is_file():
					try:
						shutil.copy2(ruta, destino / ruta.name)
					except OSError:
						log.warning("No se pudo copiar la plantilla %s", ruta, exc_info=True)
	return destino


def ruta_existe(ruta: str) -> bool:
	return os.path.exists(ruta)
