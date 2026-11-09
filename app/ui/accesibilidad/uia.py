# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Notificaciones de UI Automation (``UiaRaiseNotificationEvent``) y detección del lector activo.

Por qué: accessible_output2 habla con NVDA y JAWS, pero no con Narrador. Las
notificaciones UIA (Windows 10 1709 o posterior) las leen Narrador y NVDA, y
son la forma oficial de que una aplicación diga algo sin mover el foco.

La notificación se lanza sobre el proveedor de la ventana principal
(``UiaHostProviderFromHwnd``), así el lector sabe de qué aplicación viene.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import time

log = logging.getLogger(__name__)

# NotificationKind y NotificationProcessing de UIAutomationCore.h
KIND_OTHER = 4
KIND_ACTION_COMPLETED = 2
PROCESSING_IMPORTANT_ALL = 0
PROCESSING_IMPORTANT_MOST_RECENT = 1
PROCESSING_ALL = 2
PROCESSING_MOST_RECENT = 3

_uia = None
_oleaut = None
_hwnd_principal: int = 0
# Notificaciones pedidas antes de tener ventana (anuncio de arranque): se dicen al fijarla.
_pendientes: list[tuple[str, bool, str]] = []


def _cargar() -> bool:
	global _uia, _oleaut
	if _uia is not None:
		return True
	try:
		_uia = ctypes.WinDLL("uiautomationcore.dll")
		_oleaut = ctypes.WinDLL("oleaut32.dll")
		_uia.UiaHostProviderFromHwnd.argtypes = [wt.HWND, ctypes.POINTER(ctypes.c_void_p)]
		_uia.UiaHostProviderFromHwnd.restype = ctypes.c_long
		_uia.UiaRaiseNotificationEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
		_uia.UiaRaiseNotificationEvent.restype = ctypes.c_long
		_oleaut.SysAllocString.argtypes = [wt.LPCWSTR]
		_oleaut.SysAllocString.restype = ctypes.c_void_p
		_oleaut.SysFreeString.argtypes = [ctypes.c_void_p]
		return True
	except (OSError, AttributeError):
		log.warning("Las notificaciones UIA no están disponibles en este Windows.", exc_info=True)
		_uia = None
		return False


def fijar_ventana(hwnd: int) -> None:
	"""Ventana de la que salen las notificaciones (la principal). Dice lo que estaba pendiente."""
	global _hwnd_principal
	_hwnd_principal = int(hwnd or 0)
	while _hwnd_principal and _pendientes:
		texto, interrumpir, actividad = _pendientes.pop(0)
		notificar(texto, interrumpir, actividad=actividad)


def _liberar(puntero: ctypes.c_void_p) -> None:
	"""``IUnknown::Release`` (entrada 2 de la tabla virtual)."""
	if not puntero.value:
		return
	tabla = ctypes.cast(puntero, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
	release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(tabla[2])
	release(puntero)


def notificar(texto: str, interrumpir: bool = True, hwnd: int = 0, actividad: str = "zCommander.navegacion") -> bool:
	"""Lanza una notificación UIA. Devuelve ``False`` si no se pudo.

	:param interrumpir: ``True`` para lo que sustituye a lo anterior (navegación:
		«MostRecent» de su actividad); ``False`` para lo que no se puede perder
		(errores, decisiones: «ImportantAll»).
	:param actividad: identificador por canal; el lector agrupa por actividad, así
		una notificación de navegación no borra un error pendiente.
	"""
	hwnd = hwnd or _hwnd_principal
	if not texto:
		return False
	if not hwnd:
		_pendientes.append((texto, interrumpir, actividad))
		return False
	if not _cargar():
		return False
	proveedor = ctypes.c_void_p()
	if _uia.UiaHostProviderFromHwnd(hwnd, ctypes.byref(proveedor)) != 0 or not proveedor.value:
		return False
	mostrar = _oleaut.SysAllocString(texto)
	id_actividad = _oleaut.SysAllocString(actividad)
	try:
		# «All» no interrumpe ni se descarta (esenciales); «MostRecent» sustituye a la anterior (navegación).
		procesado = PROCESSING_MOST_RECENT if interrumpir else PROCESSING_ALL
		resultado = _uia.UiaRaiseNotificationEvent(proveedor, KIND_OTHER, procesado, mostrar, id_actividad)
		return resultado == 0
	except OSError:
		log.debug("Fallo al lanzar la notificación UIA", exc_info=True)
		return False
	finally:
		_oleaut.SysFreeString(mostrar)
		_oleaut.SysFreeString(id_actividad)
		_liberar(proveedor)


# ── Qué lector hay ───────────────────────────────────────────────────────────

_cache: tuple[float, str] = (0.0, "")


def _procesos() -> set[str]:
	"""Nombres en minúsculas de los procesos en marcha (Toolhelp32)."""
	TH32CS_SNAPPROCESS = 0x2

	class PROCESSENTRY32W(ctypes.Structure):
		_fields_ = [
			("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
			("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
			("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
			("szExeFile", ctypes.c_wchar * 260),
		]

	kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
	instantanea = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	nombres: set[str] = set()
	if not instantanea or instantanea == wt.HANDLE(-1).value:
		return nombres
	try:
		entrada = PROCESSENTRY32W()
		entrada.dwSize = ctypes.sizeof(PROCESSENTRY32W)
		siguiente = kernel32.Process32FirstW(instantanea, ctypes.byref(entrada))
		while siguiente:
			nombres.add(entrada.szExeFile.lower())
			siguiente = kernel32.Process32NextW(instantanea, ctypes.byref(entrada))
	finally:
		kernel32.CloseHandle(instantanea)
	return nombres


def lector_activo(cache_s: float = 5.0) -> str:
	"""«nvda», «jaws», «narrador», «otro» (Windows dice que hay lector) o «» si no hay.

	Se guarda unos segundos: enumerar procesos en cada anuncio sería caro.
	"""
	global _cache
	ahora = time.monotonic()
	if ahora - _cache[0] < cache_s:
		return _cache[1]
	try:
		procesos = _procesos()
	except OSError:
		log.debug("No se pudieron enumerar los procesos", exc_info=True)
		procesos = set()
	if "nvda.exe" in procesos:
		lector = "nvda"
	elif "jfw.exe" in procesos:
		lector = "jaws"
	elif "narrator.exe" in procesos:
		lector = "narrador"
	else:
		activo = wt.BOOL()
		SPI_GETSCREENREADER = 0x0046
		ctypes.windll.user32.SystemParametersInfoW(SPI_GETSCREENREADER, 0, ctypes.byref(activo), 0)
		lector = "otro" if activo.value else ""
	_cache = (ahora, lector)
	return lector
