# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Escucha del portapapeles con ``AddClipboardFormatListener`` en una ventana oculta propia (diseño 2.0, 11.16). Sin wx.

Por qué un hilo con su propia ventana «solo de mensajes» y no la ventana de
wx: así la escucha no depende de la interfaz (se prueba sin ella) y leer el
portapapeles nunca ocupa el hilo de la interfaz.

Privacidad: si el contenido trae el formato
``ExcludeClipboardContentFromMonitorProcessing`` (o
``CanIncludeInClipboardHistory`` a 0, o ``Clipboard Viewer Ignore``), que ponen
los gestores de contraseñas, no se lee ni se guarda nada.
"""

from __future__ import annotations

import ctypes
import logging
import os
import struct
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

from . import historial

log = logging.getLogger(__name__)

WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_CLIPBOARDUPDATE = 0x031D
CF_UNICODETEXT = 13
CF_HDROP = 15
HWND_MESSAGE = -3
FORMATOS_EXCLUSION = ("ExcludeClipboardContentFromMonitorProcessing", "Clipboard Viewer Ignore")
FORMATO_HISTORIAL = "CanIncludeInClipboardHistory"

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [
		("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
		("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
		("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
	]


def _user32():
	u = ctypes.WinDLL("user32", use_last_error=True)
	u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
	u.DefWindowProcW.restype = LRESULT
	u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
	u.RegisterClassW.restype = wintypes.ATOM
	u.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
	u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
		ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
	u.CreateWindowExW.restype = wintypes.HWND
	u.DestroyWindow.argtypes = [wintypes.HWND]
	u.AddClipboardFormatListener.argtypes = [wintypes.HWND]
	u.RemoveClipboardFormatListener.argtypes = [wintypes.HWND]
	u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
	u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
	u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
	u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
	u.PostQuitMessage.argtypes = [ctypes.c_int]
	u.OpenClipboard.argtypes = [wintypes.HWND]
	u.GetClipboardData.argtypes = [wintypes.UINT]
	u.GetClipboardData.restype = wintypes.HANDLE
	u.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
	u.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
	u.RegisterClipboardFormatW.restype = wintypes.UINT
	u.GetClipboardOwner.restype = wintypes.HWND
	u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
	return u


def _kernel32():
	k = ctypes.WinDLL("kernel32", use_last_error=True)
	k.GlobalLock.argtypes = [wintypes.HGLOBAL]
	k.GlobalLock.restype = ctypes.c_void_p
	k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
	k.GlobalSize.argtypes = [wintypes.HGLOBAL]
	k.GlobalSize.restype = ctypes.c_size_t
	k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
	k.GetModuleHandleW.restype = wintypes.HMODULE
	return k


def rutas_de_hdrop(datos: bytes) -> list[str]:
	"""Rutas de un bloque ``DROPFILES`` (UTF-16 o, en programas antiguos, ANSI)."""
	cabecera = struct.Struct("<IiiII")
	if len(datos) < cabecera.size:
		return []
	desplazamiento, _x, _y, _nc, ancho = cabecera.unpack_from(datos)
	cuerpo = datos[desplazamiento:]
	texto = cuerpo.decode("utf-16-le", errors="replace") if ancho else cuerpo.decode("mbcs", errors="replace")
	rutas = []
	for parte in texto.split("\0"):
		if not parte:
			break
		rutas.append(parte)
	return rutas


Aviso = Callable[[historial.Elemento, bool], None]


class Escucha:
	"""Hilo con una ventana oculta que llama a ``al_copiar(elemento, externo)`` con cada copia.

	``externo`` es verdadero si quien escribió en el portapapeles no es este proceso.
	Solo hay una escucha viva por proceso: iniciar otra detiene la anterior (cada
	escucha abre el portapapeles con cada copia, y varias a la vez se lo quitarían
	a los demás programas).
	"""

	_viva: Escucha | None = None
	_candado_viva = threading.Lock()

	def __init__(self, al_copiar: Aviso) -> None:
		self._al_copiar = al_copiar
		self._hilo: threading.Thread | None = None
		self._hwnd = 0
		self._lista = threading.Event()
		self._u = _user32()
		self._k = _kernel32()
		self._proc = WNDPROC(self._procedimiento)
		self._clase = f"zCommanderPortapapeles{os.getpid()}_{id(self)}"
		self.error = ""
		self._parada = False

	def iniciar(self, espera_s: float = 5.0) -> bool:
		if self._hilo is not None or self._parada:
			return bool(self._hwnd)
		with Escucha._candado_viva:
			anterior, Escucha._viva = Escucha._viva, self
		if anterior is not None and anterior is not self:
			anterior.detener()
		# El hilo se arranca antes de guardarlo: un detener() desde otro hilo nunca ve uno sin arrancar.
		hilo = threading.Thread(target=self._bucle, name="zc.portapapeles-escucha", daemon=True)
		hilo.start()
		self._hilo = hilo
		self._lista.wait(espera_s)
		return bool(self._hwnd)

	def detener(self, espera_s: float = 2.0) -> None:
		self._parada = True
		with Escucha._candado_viva:
			if Escucha._viva is self:
				Escucha._viva = None
		if self._hwnd:
			self._u.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
		hilo = self._hilo
		if hilo is not None and hilo.is_alive() and hilo is not threading.current_thread():
			hilo.join(espera_s)

	@property
	def activa(self) -> bool:
		return bool(self._hwnd) and self._hilo is not None and self._hilo.is_alive()

	def _bucle(self) -> None:
		instancia = self._k.GetModuleHandleW(None)
		clase = WNDCLASSW()
		clase.lpfnWndProc = self._proc
		clase.hInstance = instancia
		clase.lpszClassName = self._clase
		try:
			if not self._u.RegisterClassW(ctypes.byref(clase)):
				raise OSError(ctypes.get_last_error(), "RegisterClassW")
			hwnd = self._u.CreateWindowExW(0, self._clase, "zCommander historial del portapapeles", 0, 0, 0, 0, 0,
				wintypes.HWND(HWND_MESSAGE), None, instancia, None)
			if not hwnd:
				raise OSError(ctypes.get_last_error(), "CreateWindowExW")
			if not self._u.AddClipboardFormatListener(hwnd):
				self._u.DestroyWindow(hwnd)
				raise OSError(ctypes.get_last_error(), "AddClipboardFormatListener")
			self._hwnd = hwnd
			if self._parada:
				# detener() llegó mientras se creaba la ventana: se cierra en cuanto empieza el bucle.
				self._u.PostMessageW(hwnd, WM_CLOSE, 0, 0)
		except OSError as error:
			self.error = str(error)
			log.warning("No se pudo escuchar el portapapeles: %s", error)
			self._lista.set()
			return
		self._lista.set()
		mensaje = wintypes.MSG()
		while self._u.GetMessageW(ctypes.byref(mensaje), None, 0, 0) > 0:
			self._u.TranslateMessage(ctypes.byref(mensaje))
			self._u.DispatchMessageW(ctypes.byref(mensaje))
		self._hwnd = 0
		self._u.UnregisterClassW(self._clase, instancia)

	def _procedimiento(self, hwnd: int, mensaje: int, wparam: int, lparam: int) -> int:
		try:
			if mensaje == WM_CLIPBOARDUPDATE:
				self._cambio(hwnd)
				return 0
			if mensaje == WM_CLOSE:
				self._u.RemoveClipboardFormatListener(hwnd)
				self._u.DestroyWindow(hwnd)
				return 0
			if mensaje == WM_DESTROY:
				self._u.PostQuitMessage(0)
				return 0
		except Exception:  # noqa: BLE001 - una excepción no puede salir de un procedimiento de ventana
			log.exception("Fallo en la escucha del portapapeles")
			return 0
		return self._u.DefWindowProcW(hwnd, mensaje, wparam, lparam)

	def _cambio(self, hwnd: int) -> None:
		externo = self._propietario_externo()
		elemento = self.leer(hwnd)
		if elemento is not None:
			self._al_copiar(elemento, externo)

	def _propietario_externo(self) -> bool:
		propietario = self._u.GetClipboardOwner()
		if not propietario:
			return True
		pid = wintypes.DWORD(0)
		self._u.GetWindowThreadProcessId(propietario, ctypes.byref(pid))
		return int(pid.value) != os.getpid()

	def excluido(self) -> bool:
		"""Contenido marcado por un gestor de contraseñas (se mira sin abrir el portapapeles, salvo el DWORD)."""
		if any(self._u.IsClipboardFormatAvailable(self._u.RegisterClipboardFormatW(f)) for f in FORMATOS_EXCLUSION):
			return True
		return False

	def leer(self, hwnd: int) -> historial.Elemento | None:
		"""Lee texto o archivos del portapapeles; ``None`` si no hay nada útil o está excluido."""
		if self.excluido():
			log.debug("Copia excluida del historial (gestor de contraseñas)")
			return None
		for _intento in range(10):
			if self._u.OpenClipboard(hwnd):
				break
			time.sleep(0.02)
		else:
			log.debug("Portapapeles ocupado: no se leyó la copia")
			return None
		try:
			formato_historial = self._u.RegisterClipboardFormatW(FORMATO_HISTORIAL)
			if self._u.IsClipboardFormatAvailable(formato_historial):
				datos = self._datos(formato_historial)
				if len(datos) >= 4 and struct.unpack_from("<I", datos)[0] == 0:
					return None
			if self._u.IsClipboardFormatAvailable(CF_HDROP):
				return historial.de_archivos(rutas_de_hdrop(self._datos(CF_HDROP)))
			if self._u.IsClipboardFormatAvailable(CF_UNICODETEXT):
				datos = self._datos(CF_UNICODETEXT)
				return historial.de_texto(datos.decode("utf-16-le", errors="replace").split("\0", 1)[0])
			return None
		finally:
			self._u.CloseClipboard()

	def _datos(self, formato: int) -> bytes:
		"""Copia la memoria de un formato (sin liberarla: es del portapapeles)."""
		asa = self._u.GetClipboardData(formato)
		if not asa:
			return b""
		puntero = self._k.GlobalLock(asa)
		if not puntero:
			return b""
		try:
			return ctypes.string_at(puntero, self._k.GlobalSize(asa))
		finally:
			self._k.GlobalUnlock(asa)
