# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Prueba de libarchive (``--probar-componente libarchive``, diseño 2.0, 6.2). Bloque CM.

La llama ``componentes.prueba.probar_componente`` antes y después de sustituir
el componente (6.6): carga la DLL de ``carpeta`` (o la del servicio de
componentes) en este proceso, compara su versión con la de la ficha y
comprueba de verdad que funciona: crea un ``.tar.zst`` pequeño con un nombre
Unicode en ``data/temp`` y lo vuelve a leer. 0 si todo va bien.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import uuid
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

_NOMBRE = "prueba ñ €.txt"
_DATOS = b"zCommander " * 100


def _version_esperada() -> str:
	"""Versión de la ficha de libarchive (``componentes.json`` si existe; si no, la línea base)."""
	for nombre in ("componentes.json", "linea_base.json"):
		ruta = paths.ruta_binarios() / nombre
		try:
			datos = json.loads(ruta.read_text(encoding="utf-8"))
		except FileNotFoundError:
			continue
		except (OSError, ValueError):
			log.warning("No se pudo leer %s", ruta, exc_info=True)
			continue
		for ficha in datos.get("componentes", []):
			if isinstance(ficha, dict) and ficha.get("id") == "libarchive":
				return str(ficha.get("version", ""))
	return ""


def _ida_y_vuelta(biblioteca: ctypes.CDLL, ruta: str) -> bool:
	from app.services.libarchive import ffi

	a = biblioteca.archive_write_new()
	entrada = biblioteca.archive_entry_new()
	try:
		if biblioteca.archive_write_set_format_pax_restricted(a) or biblioteca.archive_write_add_filter_zstd(a):
			return False
		if biblioteca.archive_write_open_filename_w(a, ruta):
			log.error("libarchive no pudo crear %s: %s", ruta, ffi.texto_error(biblioteca, a))
			return False
		biblioteca.archive_entry_copy_pathname_w(entrada, _NOMBRE)
		biblioteca.archive_entry_set_filetype(entrada, ffi.AE_IFREG)
		biblioteca.archive_entry_set_perm(entrada, 0o644)
		biblioteca.archive_entry_set_size(entrada, len(_DATOS))
		if biblioteca.archive_write_header(a, entrada):
			return False
		bufer = ctypes.create_string_buffer(_DATOS, len(_DATOS))
		if biblioteca.archive_write_data(a, bufer, len(_DATOS)) != len(_DATOS) or biblioteca.archive_write_close(a):
			return False
	finally:
		biblioteca.archive_entry_free(entrada)
		biblioteca.archive_write_free(a)
	r = biblioteca.archive_read_new()
	try:
		biblioteca.archive_read_support_filter_all(r)
		biblioteca.archive_read_support_format_all(r)
		if biblioteca.archive_read_open_filename_w(r, ruta, 65536):
			return False
		cabecera = ctypes.c_void_p()
		if biblioteca.archive_read_next_header(r, ctypes.byref(cabecera)) != ffi.ARCHIVE_OK:
			return False
		if biblioteca.archive_entry_pathname_w(cabecera.value) != _NOMBRE:
			log.error("libarchive devolvió otro nombre: %r", biblioteca.archive_entry_pathname_w(cabecera.value))
			return False
		bufer = ctypes.create_string_buffer(len(_DATOS) + 16)
		leidos = biblioteca.archive_read_data(r, bufer, len(bufer))
		return bufer.raw[:leidos] == _DATOS
	finally:
		biblioteca.archive_read_free(r)


def probar(carpeta: Path | None) -> int:
	"""0 si la libarchive de ``carpeta`` (o la instalada) carga, tiene la versión de su ficha y funciona; 1 si no."""
	from app.services.libarchive import ffi

	if carpeta is None:
		carpeta = ffi.carpeta_componente()
		if carpeta is None:
			log.error("Prueba de libarchive: falta el componente")
			return 1
	try:
		biblioteca = ffi.abrir_dll(Path(carpeta))
	except OSError:
		log.exception("Prueba de libarchive: no carga la DLL de %s", carpeta)
		return 1
	detalles = ffi.version_detalles(biblioteca)
	esperada = _version_esperada()
	partes = detalles.split()
	encontrada = partes[1] if len(partes) > 1 else ""
	if esperada and encontrada != esperada:
		log.error("Prueba de libarchive: versión %s y la ficha dice %s", encontrada or "?", esperada)
		return 1
	if not hasattr(biblioteca, ffi.FUNCION_MULTIVOLUMEN):
		log.warning("Esta libarchive no tiene %s: los RAR multivolumen no se abrirán", ffi.FUNCION_MULTIVOLUMEN)
	carpeta_temporal = paths.ruta_temporales()
	carpeta_temporal.mkdir(parents=True, exist_ok=True)
	ruta = str(carpeta_temporal / f"prueba-libarchive-{uuid.uuid4().hex}.tar.zst")
	try:
		correcto = _ida_y_vuelta(biblioteca, ruta)
	except OSError:
		log.exception("Prueba de libarchive: fallo de E/S")
		correcto = False
	finally:
		try:
			os.remove(ruta)
		except FileNotFoundError:
			pass
		except OSError:
			log.warning("No se pudo borrar %s", ruta, exc_info=True)
	if not correcto:
		log.error("Prueba de libarchive: no crea y lee un .tar.zst (%s)", detalles)
		return 1
	log.info("Prueba de libarchive correcta: %s", detalles)
	return 0
