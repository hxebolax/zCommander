# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Carga de ``libarchive-13.dll`` con ``ctypes`` (diseño 2.0, 8.2 y comprimidos-y-red.md A.7). Sin wx.

Por qué así:

- **Ruta absoluta y** ``os.add_dll_directory``: las dependencias (zlib, zstd,
  xz, lz4, bzip2, iconv, b2) se buscan en la carpeta de la DLL
  (``LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR``), nunca en ``PATH``; así nadie puede
  colar otra DLL con el mismo nombre.
- **Solo funciones anchas** (``_w``) para nombres de archivo y de entrada: la
  API estrecha usa la página ANSI y pierde los nombres Unicode (A.2).
- ``argtypes`` y ``restype`` explícitos: en Windows de 64 bits los punteros y
  ``la_int64_t`` no caben en el ``int`` por defecto de ``ctypes``.
- La carpeta la da el servicio de componentes (``componentes.estado.ruta``),
  que sabe si el componente está en mantenimiento; nunca una ruta fija.

Si la DLL falta o no carga, ``cargar()`` devuelve ``None`` y la causa queda en
el registro y en ``causa()``; los formatos de libarchive no se registran.
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from ctypes import POINTER, c_char_p, c_int, c_int64, c_long, c_size_t, c_uint, c_ushort, c_void_p, c_wchar_p
from pathlib import Path

log = logging.getLogger(__name__)

NOMBRE_DLL = "libarchive-13.dll"
ID_COMPONENTE = "libarchive"

# Códigos de vuelta de libarchive (archive.h).
ARCHIVE_EOF = 1
ARCHIVE_OK = 0
ARCHIVE_RETRY = -10
ARCHIVE_WARN = -20
ARCHIVE_FAILED = -25
ARCHIVE_FATAL = -30

# Tipos de entrada (archive_entry.h).
AE_IFMT = 0o170000
AE_IFREG = 0o100000
AE_IFLNK = 0o120000
AE_IFDIR = 0o040000

# Firmas: (nombre, restype, argtypes). Solo lo que usa zCommander.
_P = c_void_p
_FIRMAS: tuple[tuple[str, object, tuple], ...] = (
	("archive_version_details", c_char_p, ()),
	("archive_version_number", c_int, ()),
	("archive_error_string", c_char_p, (_P,)),
	("archive_errno", c_int, (_P,)),
	("archive_format_name", c_char_p, (_P,)),
	("archive_filter_bytes", c_int64, (_P, c_int)),
	# Lectura
	("archive_read_new", _P, ()),
	("archive_read_support_filter_all", c_int, (_P,)),
	("archive_read_support_format_all", c_int, (_P,)),
	("archive_read_support_format_raw", c_int, (_P,)),
	("archive_read_set_options", c_int, (_P, c_char_p)),
	("archive_read_add_passphrase", c_int, (_P, c_char_p)),
	("archive_read_open_filename_w", c_int, (_P, c_wchar_p, c_size_t)),
	("archive_read_open_filenames_w", c_int, (_P, POINTER(c_wchar_p), c_size_t)),
	("archive_read_next_header", c_int, (_P, POINTER(_P))),
	("archive_read_data", c_int64, (_P, _P, c_size_t)),
	("archive_read_data_skip", c_int, (_P,)),
	("archive_read_has_encrypted_entries", c_int, (_P,)),
	("archive_read_close", c_int, (_P,)),
	("archive_read_free", c_int, (_P,)),
	# Entradas
	("archive_entry_new", _P, ()),
	("archive_entry_free", None, (_P,)),
	("archive_entry_clear", _P, (_P,)),
	("archive_entry_pathname_w", c_wchar_p, (_P,)),
	("archive_entry_pathname", c_char_p, (_P,)),
	("archive_entry_size", c_int64, (_P,)),
	("archive_entry_size_is_set", c_int, (_P,)),
	("archive_entry_mtime", c_int64, (_P,)),
	("archive_entry_mtime_is_set", c_int, (_P,)),
	("archive_entry_filetype", c_ushort, (_P,)),
	("archive_entry_perm", c_ushort, (_P,)),
	("archive_entry_is_data_encrypted", c_int, (_P,)),
	("archive_entry_is_metadata_encrypted", c_int, (_P,)),
	("archive_entry_hardlink_w", c_wchar_p, (_P,)),
	("archive_entry_copy_pathname_w", None, (_P, c_wchar_p)),
	("archive_entry_set_size", None, (_P, c_int64)),
	("archive_entry_set_filetype", None, (_P, c_uint)),
	("archive_entry_set_perm", None, (_P, c_ushort)),
	("archive_entry_set_mtime", None, (_P, c_int64, c_long)),
	# Escritura
	("archive_write_new", _P, ()),
	("archive_write_set_format_zip", c_int, (_P,)),
	("archive_write_set_format_7zip", c_int, (_P,)),
	("archive_write_set_format_iso9660", c_int, (_P,)),
	("archive_write_set_format_cpio_newc", c_int, (_P,)),
	("archive_write_set_format_xar", c_int, (_P,)),
	("archive_write_set_format_pax_restricted", c_int, (_P,)),
	("archive_write_set_format_raw", c_int, (_P,)),
	("archive_write_set_format_ar_svr4", c_int, (_P,)),
	("archive_write_set_format_warc", c_int, (_P,)),
	("archive_write_add_filter_gzip", c_int, (_P,)),
	("archive_write_add_filter_bzip2", c_int, (_P,)),
	("archive_write_add_filter_xz", c_int, (_P,)),
	("archive_write_add_filter_lzma", c_int, (_P,)),
	("archive_write_add_filter_lzip", c_int, (_P,)),
	("archive_write_add_filter_lz4", c_int, (_P,)),
	("archive_write_add_filter_zstd", c_int, (_P,)),
	("archive_write_add_filter_compress", c_int, (_P,)),
	("archive_write_set_options", c_int, (_P, c_char_p)),
	("archive_write_set_passphrase", c_int, (_P, c_char_p)),
	("archive_write_set_bytes_in_last_block", c_int, (_P, c_int)),
	("archive_write_open_filename_w", c_int, (_P, c_wchar_p)),
	("archive_write_header", c_int, (_P, _P)),
	("archive_write_data", c_int64, (_P, _P, c_size_t)),
	("archive_write_finish_entry", c_int, (_P,)),
	("archive_write_close", c_int, (_P,)),
	("archive_write_free", c_int, (_P,)),
)

#: Funciones sin las que no se registra el multivolumen (8.1).
FUNCION_MULTIVOLUMEN = "archive_read_open_filenames_w"

_candado = threading.Lock()
_cargada: ctypes.CDLL | None = None
_carpeta_cargada: Path | None = None
_causa = ""
_directorios: list = []


def carpeta_componente() -> Path | None:
	"""Carpeta de libarchive según el servicio de componentes, o ``None`` si falta o está en mantenimiento."""
	try:
		from app.services.componentes import estado

		return Path(estado.ruta(ID_COMPONENTE))
	except Exception as error:  # noqa: BLE001 - sin componente no hay libarchive, y se dice por qué
		log.info("libarchive no disponible: %s", getattr(error, "mensaje", error))
		return None


def _configurar(biblioteca: ctypes.CDLL) -> list[str]:
	"""Fija las firmas; devuelve las funciones que faltan (no debería faltar ninguna con 3.8.11)."""
	faltan = []
	for nombre, restype, argtypes in _FIRMAS:
		try:
			funcion = getattr(biblioteca, nombre)
		except AttributeError:
			faltan.append(nombre)
			continue
		funcion.restype = restype
		funcion.argtypes = list(argtypes)
	return faltan


def abrir_dll(carpeta: Path) -> ctypes.CDLL:
	"""Carga la DLL de ``carpeta`` (sin caché). Lanza ``OSError`` si no puede."""
	carpeta = Path(carpeta).resolve()
	ruta = carpeta / NOMBRE_DLL
	if not ruta.is_file():
		raise OSError(f"No existe {ruta}")
	directorio = os.add_dll_directory(str(carpeta))
	_directorios.append(directorio)
	biblioteca = ctypes.CDLL(str(ruta))
	faltan = _configurar(biblioteca)
	if faltan:
		log.warning("A %s le faltan funciones: %s", ruta, ", ".join(faltan))
	return biblioteca


def cargar() -> ctypes.CDLL | None:
	"""La DLL lista para usar, o ``None`` (la causa queda en ``causa()`` y en el registro).

	Se carga una vez por carpeta: si el componente se actualiza y cambia de
	carpeta, la siguiente llamada carga la nueva.
	"""
	global _cargada, _carpeta_cargada, _causa
	carpeta = carpeta_componente()
	with _candado:
		if carpeta is None:
			_causa = "Falta el componente libarchive"
			return None
		if _cargada is not None and _carpeta_cargada == carpeta:
			return _cargada
		try:
			_cargada = abrir_dll(carpeta)
			_carpeta_cargada = carpeta
			_causa = ""
			log.info("libarchive cargada: %s", version_detalles(_cargada))
		except OSError as error:
			_cargada = None
			_causa = f"No se pudo cargar {carpeta / NOMBRE_DLL}: {error}"
			log.error("%s", _causa)
		return _cargada


def disponible() -> bool:
	return cargar() is not None


def causa() -> str:
	"""Por qué no está libarchive (vacío si está)."""
	return _causa


def version_detalles(biblioteca: ctypes.CDLL | None = None) -> str:
	"""«libarchive 3.8.11 zlib/1.4 ...» o vacío."""
	biblioteca = biblioteca or cargar()
	if biblioteca is None:
		return ""
	valor = biblioteca.archive_version_details()
	return valor.decode("utf-8", "replace") if valor else ""


def version() -> str:
	"""«3.8.11» o vacío."""
	detalles = version_detalles()
	partes = detalles.split()
	return partes[1] if len(partes) > 1 and partes[0] == "libarchive" else ""


def tiene(nombre: str) -> bool:
	biblioteca = cargar()
	return biblioteca is not None and hasattr(biblioteca, nombre)


def texto_error(biblioteca: ctypes.CDLL, archivo: int | None) -> str:
	"""Mensaje de ``archive_error_string`` (en inglés: va al registro, nunca a la persona)."""
	if not archivo:
		return ""
	valor = biblioteca.archive_error_string(archivo)
	return valor.decode("utf-8", "replace") if valor else ""
