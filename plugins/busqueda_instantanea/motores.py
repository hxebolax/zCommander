# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motores de búsqueda: Everything por mensajes de Windows y el índice de Windows por OLE DB.

Todo esto corre en un hilo de trabajo (nunca en el de la interfaz):

- **Everything**: se busca su ventana ``EVERYTHING_TASKBAR_NOTIFICATION``; si
  existe, se le manda la consulta con ``WM_COPYDATA`` y se espera su respuesta,
  también por ``WM_COPYDATA``, en una ventana de solo mensajes creada en este
  mismo hilo (los mensajes enviados a una ventana se atienden en el hilo que la
  creó). Solo se habla su protocolo: no se distribuye ni se carga nada de
  Everything, que la persona instala y abre si lo quiere (es.exe y el SDK no
  hacen falta).
- **Índice de Windows**: ADO sobre el proveedor ``Search.CollatorDSO`` con
  ``win32com`` (pywin32, del contrato de bibliotecas), con COM iniciado en el hilo.
"""

from __future__ import annotations

import ctypes
import itertools
import logging
import time
from ctypes import wintypes
from dataclasses import dataclass, field

from . import consulta

log = logging.getLogger("zcplugins.zc.busqueda_instantanea")

EVERYTHING, WINDOWS = "everything", "windows"
NOMBRES_MOTOR = {EVERYTHING: "Everything", WINDOWS: "el índice de búsqueda de Windows"}

WM_COPYDATA = 0x004A
HWND_MESSAGE = -3
PM_REMOVE = 0x0001
_ID_RESPUESTA = itertools.count(0x5A43_0001)

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


class SinMotor(Exception):
	"""Ningún motor responde; ``str(error)`` lo explica a la persona."""


@dataclass
class Resultado:
	motor: str
	rutas: list[str] = field(default_factory=list)


def texto_sin_motores() -> str:
	return ("No hay ningún motor de búsqueda instantánea disponible. Everything no está abierto (si lo tiene instalado, "
		"ábralo; si no, puede descargarlo gratis de voidtools.com) y el índice de búsqueda de Windows no responde "
		"(compruebe en Windows que el servicio «Windows Search» está iniciado y que la carpeta está indizada).")


def _cancelado(cancelacion) -> bool:
	token = getattr(cancelacion, "token", cancelacion)
	return token is not None and token.is_set()


# ── Everything ───────────────────────────────────────────────────────────────

if hasattr(ctypes, "WinDLL"):
	_user32 = ctypes.WinDLL("user32", use_last_error=True)
	_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	LRESULT = ctypes.c_ssize_t
	WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

	class COPYDATASTRUCT(ctypes.Structure):
		_fields_ = [("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD), ("lpData", ctypes.c_void_p)]

	class WNDCLASSW(ctypes.Structure):
		_fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
			("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
			("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
			("lpszClassName", wintypes.LPCWSTR)]

	_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
	_user32.FindWindowW.restype = wintypes.HWND
	_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
	_user32.DefWindowProcW.restype = LRESULT
	_user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
	_user32.RegisterClassW.restype = wintypes.ATOM
	_user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
		ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
	_user32.CreateWindowExW.restype = wintypes.HWND
	_user32.DestroyWindow.argtypes = [wintypes.HWND]
	_user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT,
		wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
	_user32.SendMessageTimeoutW.restype = LRESULT
	_user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
	_user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
	_user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
	_user32.DispatchMessageW.restype = LRESULT
	_user32.MsgWaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, wintypes.DWORD]
	_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
	_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
	_kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
	_kernel32.GetFileAttributesW.restype = wintypes.DWORD

_CLASE_RESPUESTA = "zCommanderRespuestaEverything"
_respuestas: dict[int, bytes] = {}
_clase_registrada: list[object] = []


def _procedimiento(hwnd, mensaje, wparam, lparam):  # noqa: ANN001 - firma de WNDPROC
	if mensaje == WM_COPYDATA and lparam:
		datos = ctypes.cast(lparam, ctypes.POINTER(COPYDATASTRUCT)).contents
		_respuestas[int(datos.dwData)] = ctypes.string_at(datos.lpData, datos.cbData) if datos.lpData else b""
		return 1
	return _user32.DefWindowProcW(hwnd, mensaje, wparam, lparam)


def _registrar_clase() -> None:
	if _clase_registrada:
		return
	procedimiento = WNDPROC(_procedimiento)
	clase = WNDCLASSW()
	clase.lpfnWndProc = procedimiento
	clase.hInstance = _kernel32.GetModuleHandleW(None)
	clase.lpszClassName = _CLASE_RESPUESTA
	if not _user32.RegisterClassW(ctypes.byref(clase)):
		error = ctypes.get_last_error()
		if error != 1410:  # ERROR_CLASS_ALREADY_EXISTS
			raise OSError(error, "RegisterClassW")
	# La función y la clase tienen que vivir mientras exista la clase de ventana.
	_clase_registrada.extend([procedimiento, clase])


def everything_disponible() -> bool:
	"""Everything está abierto (su ventana de mensajes existe)."""
	if not hasattr(ctypes, "WinDLL"):
		return False
	return bool(_user32.FindWindowW(consulta.CLASE_VENTANA_EVERYTHING, None))


def buscar_everything(texto: str, max_resultados: int, cancelacion=None, tiempo_s: float = 10.0) -> list[str]:
	"""Rutas que devuelve Everything para ``texto`` (su sintaxis). Lanza ``SinMotor`` si no está abierto."""
	if not texto.strip():
		return []
	destino = _user32.FindWindowW(consulta.CLASE_VENTANA_EVERYTHING, None) if hasattr(ctypes, "WinDLL") else None
	if not destino:
		raise SinMotor("Everything no está abierto")
	_registrar_clase()
	ventana = _user32.CreateWindowExW(0, _CLASE_RESPUESTA, "zCommander", 0, 0, 0, 0, 0, HWND_MESSAGE, None,
		_kernel32.GetModuleHandleW(None), None)
	if not ventana:
		raise OSError(ctypes.get_last_error(), "CreateWindowExW")
	identificador = next(_ID_RESPUESTA)
	try:
		datos = consulta.consulta_everything(texto, ventana, identificador, max_resultados)
		bufer = ctypes.create_string_buffer(datos, len(datos))
		copia = COPYDATASTRUCT(consulta.COPYDATA_CONSULTA_W, len(datos), ctypes.cast(bufer, ctypes.c_void_p))
		devuelto = ctypes.c_size_t(0)
		# SMTO_ABORTIFHUNG (2): un Everything colgado no cuelga este hilo.
		if not _user32.SendMessageTimeoutW(destino, WM_COPYDATA, ventana, ctypes.addressof(copia), 2, 5000,
				ctypes.byref(devuelto)) or not devuelto.value:
			raise SinMotor("Everything no aceptó la consulta")
		limite = time.monotonic() + tiempo_s
		mensaje = wintypes.MSG()
		while identificador not in _respuestas:
			if _cancelado(cancelacion):
				return []
			if time.monotonic() > limite:
				raise SinMotor("Everything no respondió a tiempo")
			_user32.MsgWaitForMultipleObjects(0, None, False, 100, 0x04FF)  # QS_ALLINPUT
			while _user32.PeekMessageW(ctypes.byref(mensaje), None, 0, 0, PM_REMOVE):
				_user32.TranslateMessage(ctypes.byref(mensaje))
				_user32.DispatchMessageW(ctypes.byref(mensaje))
		respuesta = _respuestas.pop(identificador)
	finally:
		_user32.DestroyWindow(ventana)
		_respuestas.pop(identificador, None)
	return [ruta for ruta, _carpeta in consulta.leer_respuesta_everything(respuesta)]


# ── Índice de Windows ────────────────────────────────────────────────────────

CONEXION_INDICE = "Provider=Search.CollatorDSO;Extended Properties='Application=Windows';"


def buscar_windows(sql: str, cancelacion=None) -> list[str]:
	"""Rutas del índice de búsqueda de Windows para una consulta SQL de ``consulta.a_sql_windows``."""
	try:
		import pythoncom
		import win32com.client
	except ImportError as error:
		raise SinMotor("Falta pywin32") from error
	pythoncom.CoInitialize()
	try:
		try:
			conexion = win32com.client.Dispatch("ADODB.Connection")
			conexion.Open(CONEXION_INDICE)
		except Exception as error:  # noqa: BLE001 - com_error u otro: el índice no está
			log.debug("El índice de Windows no responde", exc_info=True)
			raise SinMotor("El índice de búsqueda de Windows no responde") from error
		rutas: list[str] = []
		try:
			registros = win32com.client.Dispatch("ADODB.Recordset")
			registros.Open(sql, conexion)
			while not registros.EOF:
				if _cancelado(cancelacion):
					break
				valor = registros.Fields.Item("System.ItemPathDisplay").Value
				if valor:
					rutas.append(str(valor))
				registros.MoveNext()
			registros.Close()
		except Exception as error:  # noqa: BLE001 - consulta rechazada por el índice
			log.warning("El índice de Windows rechazó la consulta %s", sql, exc_info=True)
			raise SinMotor("El índice de búsqueda de Windows no entendió la búsqueda") from error
		finally:
			conexion.Close()
		return rutas
	finally:
		pythoncom.CoUninitialize()


def windows_disponible() -> bool:
	"""El índice responde a una consulta mínima (unas décimas de segundo: solo en un hilo)."""
	try:
		buscar_windows("SELECT TOP 1 System.ItemPathDisplay FROM SYSTEMINDEX")
		return True
	except SinMotor:
		return False


# ── Elección y filtros ───────────────────────────────────────────────────────


def motores_disponibles() -> list[str]:
	disponibles = []
	if everything_disponible():
		disponibles.append(EVERYTHING)
	if windows_disponible():
		disponibles.append(WINDOWS)
	return disponibles


def es_oculta(ruta: str) -> bool:
	if not hasattr(ctypes, "WinDLL"):
		return False
	atributos = _kernel32.GetFileAttributesW(ruta)
	return atributos != INVALID_FILE_ATTRIBUTES and bool(atributos & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


def buscar(texto: str, *, preferencia: str = "automatico", contenido: str = "", carpeta: str = "", max_resultados: int = 1000,
		incluir_ocultos: bool = False, excluidas: tuple[str, ...] = (), cancelacion=None) -> Resultado:
	"""Busca con el motor que toca y aplica los filtros comunes. Lanza ``SinMotor`` con la explicación."""
	pedir = max_resultados * 2 if (excluidas or not incluir_ocultos) else max_resultados
	usar_everything = preferencia in ("automatico", EVERYTHING) and not contenido.strip()
	if usar_everything and everything_disponible():
		rutas = buscar_everything(consulta.a_everything(texto, carpeta=carpeta), pedir, cancelacion)
		motor = EVERYTHING
	elif preferencia == EVERYTHING and not contenido.strip():
		raise SinMotor("Everything no está abierto. Ábralo, o elija otro motor en Preferencias.")
	else:
		try:
			rutas = buscar_windows(consulta.a_sql_windows(texto, carpeta=carpeta, contenido=contenido, max_resultados=pedir),
				cancelacion)
		except SinMotor as error:
			if preferencia == "automatico" and not contenido.strip():
				raise SinMotor(texto_sin_motores()) from error
			raise
		motor = WINDOWS
	filtradas = consulta.filtrar(rutas, excluidas, max_resultados, None if incluir_ocultos else es_oculta)
	return Resultado(motor, filtradas)
