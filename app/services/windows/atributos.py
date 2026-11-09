# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Atributos y fechas de archivos en Windows (ctypes sobre Kernel32).

``os.chmod`` solo sabe de «solo lectura»; para oculto, sistema, archivo y no
indexar hacen falta ``GetFileAttributesW`` y ``SetFileAttributesW``. La fecha
de creación solo se cambia con ``SetFileTime``.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging

from app.services import formato
from app.services.vfs import base

log = logging.getLogger(__name__)

INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
# Atributos que SetFileAttributesW admite cambiar (el resto los ignora o falla).
MODIFICABLES = (
	formato.SOLO_LECTURA | formato.OCULTO | formato.SISTEMA | formato.ARCHIVO
	| formato.NO_INDEXAR | formato.TEMPORAL | formato.SIN_CONEXION
)

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if hasattr(ctypes, "WinDLL") else None
if _kernel32 is not None:
	_kernel32.GetFileAttributesW.argtypes = [wt.LPCWSTR]
	_kernel32.GetFileAttributesW.restype = wt.DWORD
	_kernel32.SetFileAttributesW.argtypes = [wt.LPCWSTR, wt.DWORD]
	_kernel32.SetFileAttributesW.restype = wt.BOOL
	_kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
	_kernel32.CreateFileW.restype = wt.HANDLE
	_kernel32.SetFileTime.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
	_kernel32.SetFileTime.restype = wt.BOOL
	_kernel32.CloseHandle.argtypes = [wt.HANDLE]


def _error(ruta: str) -> base.ErrorArchivos:
	from app.services import errores

	codigo = ctypes.get_last_error()
	return errores.convertir(OSError(None, ctypes.FormatError(codigo).strip(), ruta, codigo), ruta)


def leer_atributos(ruta: str) -> int:
	"""Bits de atributos de ``ruta``. Lanza ``ErrorArchivos`` si no se pueden leer."""
	valor = _kernel32.GetFileAttributesW(ruta)
	if valor == INVALID_FILE_ATTRIBUTES:
		raise _error(ruta)
	return int(valor)


def fijar_atributos(ruta: str, atributos: int) -> None:
	"""Sustituye los atributos modificables conservando los demás (carpeta, enlace...)."""
	actuales = leer_atributos(ruta)
	nuevos = (actuales & ~MODIFICABLES) | (atributos & MODIFICABLES)
	# Ni carpeta ni punto de análisis se pasan a SetFileAttributesW (los rechaza).
	nuevos &= ~(formato.CARPETA | formato.PUNTO_ANALISIS | formato.COMPRIMIDO | formato.CIFRADO)
	if not _kernel32.SetFileAttributesW(ruta, nuevos or formato.NORMAL):
		raise _error(ruta)


def cambiar_atributos(ruta: str, poner: int = 0, quitar: int = 0) -> int:
	"""Pone y quita bits; devuelve los atributos resultantes."""
	actuales = leer_atributos(ruta)
	nuevos = (actuales | poner) & ~quitar
	fijar_atributos(ruta, nuevos)
	return nuevos


def _a_filetime(marca: float) -> ctypes.c_ulonglong:
	# FILETIME: intervalos de 100 ns desde 1601-01-01.
	return ctypes.c_ulonglong(int((marca + 11644473600) * 10_000_000))


def fijar_fecha_creacion(ruta: str, marca: float) -> None:
	"""Cambia la fecha de creación (``SetFileTime``). Vale para archivos y carpetas."""
	GENERIC_WRITE = 0x40000000
	FILE_SHARE_ALL = 0x7
	OPEN_EXISTING = 3
	FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # imprescindible para abrir carpetas
	FILE_WRITE_ATTRIBUTES = 0x100
	manejador = _kernel32.CreateFileW(
		ruta, FILE_WRITE_ATTRIBUTES | (0 & GENERIC_WRITE), FILE_SHARE_ALL, None, OPEN_EXISTING,
		FILE_FLAG_BACKUP_SEMANTICS, None,
	)
	if manejador in (None, wt.HANDLE(-1).value, -1):
		raise _error(ruta)
	try:
		tiempo = _a_filetime(marca)
		if not _kernel32.SetFileTime(manejador, ctypes.byref(tiempo), None, None):
			raise _error(ruta)
	finally:
		_kernel32.CloseHandle(manejador)
