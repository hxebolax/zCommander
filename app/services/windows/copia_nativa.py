# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Copia y movimiento nativos de Windows con progreso, pausa y cancelación.

- ``copiar(origen, destino, progreso, cancelacion)``: ``CopyFileExW`` con una
  rutina de progreso. Conserva atributos, fechas y flujos alternativos (como el
  Explorador). Si la rutina devuelve ``PROGRESS_CANCEL``, Windows borra el
  destino a medias.
- ``sustituir(temporal, destino)``: ``ReplaceFileW`` (conserva los permisos y
  la ACL del archivo que se sustituye; los otros enlaces duros del destino
  siguen con el contenido viejo). Si falla por acceso denegado o porque el
  sistema de archivos no lo admite, ``MoveFileExW`` con reemplazo (registrado).
- ``mover(origen, destino)``: ``MoveFileExW`` (en el mismo volumen es un renombrado).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
from collections.abc import Callable

from app.services import errores
from app.services.vfs import base, rutas

log = logging.getLogger(__name__)

PROGRESS_CONTINUE = 0
PROGRESS_CANCEL = 1
COPY_FILE_FAIL_IF_EXISTS = 0x1
COPY_FILE_COPY_SYMLINK = 0x800
COPY_FILE_NO_BUFFERING = 0x1000
MOVEFILE_REPLACE_EXISTING = 0x1
MOVEFILE_COPY_ALLOWED = 0x2
MOVEFILE_WRITE_THROUGH = 0x8
REPLACEFILE_IGNORE_MERGE_ERRORS = 0x2
REPLACEFILE_IGNORE_ACL_ERRORS = 0x4
ERROR_REQUEST_ABORTED = 1235

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

RUTINA = ctypes.WINFUNCTYPE(
	wt.DWORD,
	ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong,
	wt.DWORD, wt.DWORD, wt.HANDLE, wt.HANDLE, wt.LPVOID,
)
_kernel32.CopyFileExW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, RUTINA, wt.LPVOID, ctypes.POINTER(wt.BOOL), wt.DWORD]
_kernel32.CopyFileExW.restype = wt.BOOL
_kernel32.MoveFileExW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.DWORD]
_kernel32.MoveFileExW.restype = wt.BOOL
_kernel32.ReplaceFileW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, wt.LPVOID, wt.LPVOID]
_kernel32.ReplaceFileW.restype = wt.BOOL


def _error_codigo(ruta: str, codigo: int) -> base.ErrorArchivos:
	return errores.convertir(OSError(None, ctypes.FormatError(codigo).strip(), ruta, codigo), ruta)


def _error(ruta: str) -> base.ErrorArchivos:
	codigo = ctypes.get_last_error()
	if codigo == ERROR_REQUEST_ABORTED:
		return base.Cancelado(ruta=ruta)
	return errores.convertir(OSError(None, ctypes.FormatError(codigo).strip(), ruta, codigo), ruta)


def copiar(
	origen: str,
	destino: str,
	progreso: Callable[[int, int], None] | None = None,
	cancelacion=None,
	esperar_pausa: Callable[[], None] | None = None,
	copiar_enlace: bool = False,
) -> None:
	"""Copia un archivo. ``progreso(hechos, total)`` se llama desde este mismo hilo.

	:param esperar_pausa: se llama en cada trozo; si la operación está en pausa,
		bloquea hasta reanudar (la copia queda detenida dentro del archivo).
	:raises Cancelado: si se canceló (el destino a medias lo borra Windows).
	:raises ErrorArchivos: el resto de fallos, con mensaje en español.
	"""
	o = rutas.con_prefijo_largo(rutas.normalizar(origen))
	d = rutas.con_prefijo_largo(rutas.normalizar(destino))

	def rutina(total, hechos, _flujo_total, _flujo_hecho, _flujo, _motivo, _h1, _h2, _datos):
		try:
			if esperar_pausa is not None:
				esperar_pausa()
			if cancelacion is not None and cancelacion.is_set():
				return PROGRESS_CANCEL
			if progreso is not None:
				progreso(int(hechos), int(total))
		except base.Cancelado:
			return PROGRESS_CANCEL
		except Exception:  # noqa: BLE001 - una excepción aquí no puede atravesar la llamada de Windows
			log.exception("Fallo en la rutina de progreso de la copia")
			return PROGRESS_CANCEL
		return PROGRESS_CONTINUE

	callback = RUTINA(rutina)
	cancelar = wt.BOOL(False)
	banderas = COPY_FILE_COPY_SYMLINK if copiar_enlace else 0
	if not _kernel32.CopyFileExW(o, d, callback, None, ctypes.byref(cancelar), banderas):
		error = _error(origen)
		if isinstance(error, base.Cancelado) or (cancelacion is not None and cancelacion.is_set()):
			raise base.Cancelado(ruta=origen)
		raise error


def sustituir(temporal: str, destino: str) -> None:
	"""Pone ``temporal`` en lugar de ``destino`` conservando los permisos del destino."""
	t = rutas.con_prefijo_largo(rutas.normalizar(temporal))
	d = rutas.con_prefijo_largo(rutas.normalizar(destino))
	if not os.path.exists(d):
		mover(temporal, destino, reemplazar=False)
		return
	# Con archivo de respaldo, cualquier fallo intermedio deja el original recuperable.
	respaldo = os.path.join(os.path.dirname(d), "~zc" + os.urandom(4).hex() + ".bak")
	if _kernel32.ReplaceFileW(d, t, respaldo, REPLACEFILE_IGNORE_MERGE_ERRORS | REPLACEFILE_IGNORE_ACL_ERRORS, None, None):
		_borrar_respaldo(respaldo)
		return
	codigo = ctypes.get_last_error()
	if codigo == 1176:
		# El original quedó en el respaldo y la copia no se pudo poner: se devuelve el original.
		mover(respaldo, destino, reemplazar=False)
		raise _error_codigo(destino, codigo)
	if codigo == 1177:
		# El original está en el respaldo y el temporal sigue intacto: se termina a mano.
		mover(temporal, destino, reemplazar=False)
		_borrar_respaldo(respaldo)
		return
	if codigo not in (5, 50, 1175):
		raise _error_codigo(destino, codigo)
	# 5 acceso denegado, 50 no admitido, 1175 no se pudo quitar el destino: nada cambió.
	log.warning("ReplaceFileW falló con el código %s en %s; se sustituye con MoveFileExW", codigo, destino)
	mover(temporal, destino, reemplazar=True)


def _borrar_respaldo(respaldo: str) -> None:
	try:
		if os.path.exists(respaldo):
			os.remove(respaldo)
	except OSError:
		log.warning("No se pudo borrar el respaldo %s", respaldo, exc_info=True)


def mover(origen: str, destino: str, reemplazar: bool = False) -> None:
	"""Mueve o renombra (en el mismo volumen, sin copiar datos)."""
	o = rutas.con_prefijo_largo(rutas.normalizar(origen))
	d = rutas.con_prefijo_largo(rutas.normalizar(destino))
	banderas = MOVEFILE_REPLACE_EXISTING if reemplazar else 0
	if not _kernel32.MoveFileExW(o, d, banderas):
		raise _error(origen)
