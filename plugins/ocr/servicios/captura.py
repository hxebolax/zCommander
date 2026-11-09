# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Imágenes que no son archivos: la del portapapeles y la de la ventana en primer plano (sin wx, con ctypes).

Las dos se guardan como BMP en la caché del complemento (dentro de ``data``),
que es lo que el motor OCR sabe leer. La ventana se captura con
``PrintWindow`` (con ``PW_RENDERFULLCONTENT``), que también funciona con
ventanas tapadas por otras.
"""

from __future__ import annotations

import builtins
import ctypes
import struct
from ctypes import wintypes
from pathlib import Path

CF_DIB = 8
PW_RENDERFULLCONTENT = 0x2
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020


def _bibliotecas():
	"""Copias propias de user32, kernel32 y gdi32: fijar ``argtypes`` en ellas no cambia las de ``ctypes.windll``,
	que comparte todo el proceso."""
	usuario = ctypes.WinDLL("user32", use_last_error=True)
	kernel = ctypes.WinDLL("kernel32", use_last_error=True)
	gdi = ctypes.WinDLL("gdi32", use_last_error=True)
	usuario.GetClipboardData.restype = wintypes.HANDLE
	usuario.GetClipboardData.argtypes = [wintypes.UINT]
	usuario.OpenClipboard.argtypes = [wintypes.HWND]
	kernel.GlobalLock.restype = ctypes.c_void_p
	kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
	kernel.GlobalSize.restype = ctypes.c_size_t
	kernel.GlobalSize.argtypes = [wintypes.HGLOBAL]
	kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
	usuario.GetWindowDC.restype = wintypes.HDC
	usuario.GetWindowDC.argtypes = [wintypes.HWND]
	usuario.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
	usuario.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
	usuario.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
	usuario.GetForegroundWindow.restype = wintypes.HWND
	gdi.CreateCompatibleDC.restype = wintypes.HDC
	gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
	gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
	gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
	gdi.SelectObject.restype = wintypes.HGDIOBJ
	gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
	gdi.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int,
		ctypes.c_int, wintypes.DWORD]
	gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p,
		wintypes.UINT]
	gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
	gdi.DeleteDC.argtypes = [wintypes.HDC]
	return usuario, kernel, gdi


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorCaptura(Exception):
	"""No hay imagen que reconocer (mensaje en español)."""


def bmp_desde_dib(dib: bytes) -> bytes:
	"""Un archivo BMP a partir de un DIB del portapapeles (cabecera BITMAPINFOHEADER y píxeles)."""
	if len(dib) < 40:
		raise ErrorCaptura(_("La imagen del portapapeles está dañada"))
	tamano_cabecera, _ancho, _alto, _planos, bits, compresion, _tamano, _x, _y, colores = struct.unpack("<IiiHHIIiiI", dib[:36])
	if bits <= 8 and colores == 0:
		colores = 1 << bits
	mascaras = 12 if compresion == 3 and tamano_cabecera == 40 else 0
	desplazamiento = 14 + tamano_cabecera + mascaras + colores * 4
	return struct.pack("<2sIHHI", b"BM", 14 + len(dib), 0, 0, desplazamiento) + dib


def imagen_portapapeles(destino: Path) -> Path:
	"""Guarda en ``destino`` (BMP) la imagen del portapapeles. ``ErrorCaptura`` si no hay."""
	usuario, kernel, _gdi = _bibliotecas()
	if not usuario.IsClipboardFormatAvailable(CF_DIB):
		raise ErrorCaptura(_("No hay ninguna imagen en el portapapeles"))
	if not usuario.OpenClipboard(None):
		raise ErrorCaptura(_("El portapapeles está ocupado por otro programa; inténtelo de nuevo"))
	try:
		manejador = usuario.GetClipboardData(CF_DIB)
		if not manejador:
			raise ErrorCaptura(_("No hay ninguna imagen en el portapapeles"))
		puntero = kernel.GlobalLock(manejador)
		if not puntero:
			raise ErrorCaptura(_("No se pudo leer la imagen del portapapeles"))
		try:
			dib = ctypes.string_at(puntero, kernel.GlobalSize(manejador))
		finally:
			kernel.GlobalUnlock(manejador)
	finally:
		usuario.CloseClipboard()
	destino.parent.mkdir(parents=True, exist_ok=True)
	destino.write_bytes(bmp_desde_dib(dib))
	return destino


class _BITMAPINFOHEADER(ctypes.Structure):
	_fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
		("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
		("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
		("biClrImportant", wintypes.DWORD)]


def titulo_ventana(hwnd: int) -> str:
	usuario = ctypes.WinDLL("user32", use_last_error=True)
	largo = usuario.GetWindowTextLengthW(wintypes.HWND(hwnd))
	memoria = ctypes.create_unicode_buffer(largo + 1)
	usuario.GetWindowTextW(wintypes.HWND(hwnd), memoria, largo + 1)
	return memoria.value


def ventana_primer_plano() -> int:
	usuario, _kernel, _gdi = _bibliotecas()
	return int(usuario.GetForegroundWindow() or 0)


def capturar_ventana(hwnd: int, destino: Path) -> Path:
	"""Guarda en ``destino`` (BMP de 32 bits) la imagen de la ventana ``hwnd``."""
	usuario, _kernel, gdi = _bibliotecas()
	rectangulo = wintypes.RECT()
	if not hwnd or not usuario.GetWindowRect(hwnd, ctypes.byref(rectangulo)):
		raise ErrorCaptura(_("No hay ninguna ventana en primer plano"))
	ancho, alto = rectangulo.right - rectangulo.left, rectangulo.bottom - rectangulo.top
	if ancho <= 0 or alto <= 0:
		raise ErrorCaptura(_("La ventana en primer plano está minimizada o no se ve"))
	dc_ventana = usuario.GetWindowDC(hwnd)
	dc_memoria = gdi.CreateCompatibleDC(dc_ventana)
	mapa = gdi.CreateCompatibleBitmap(dc_ventana, ancho, alto)
	anterior = gdi.SelectObject(dc_memoria, mapa)
	try:
		if not usuario.PrintWindow(hwnd, dc_memoria, PW_RENDERFULLCONTENT):
			gdi.BitBlt(dc_memoria, 0, 0, ancho, alto, dc_ventana, 0, 0, SRCCOPY)
		cabecera = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), ancho, -alto, 1, 32, 0, 0, 0, 0, 0, 0)
		pixeles = ctypes.create_string_buffer(ancho * alto * 4)
		if not gdi.GetDIBits(dc_memoria, mapa, 0, alto, ctypes.cast(pixeles, ctypes.c_void_p), ctypes.byref(cabecera), DIB_RGB_COLORS):
			raise ErrorCaptura(_("No se pudo capturar la imagen de la ventana"))
	finally:
		gdi.SelectObject(dc_memoria, anterior)
		gdi.DeleteObject(mapa)
		gdi.DeleteDC(dc_memoria)
		usuario.ReleaseDC(hwnd, dc_ventana)
	dib = bytes(cabecera) + pixeles.raw
	destino.parent.mkdir(parents=True, exist_ok=True)
	destino.write_bytes(bmp_desde_dib(dib))
	return destino
