# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Portapapeles de Windows con el formato de archivos del Explorador (sección 8.18 del diseño).

Por qué así:

- Copiar y cortar ponen ``CF_HDROP`` (la lista de rutas que entiende el
  Explorador y cualquier programa) más «Preferred DropEffect»: 1 (copiar) o
  2 (mover). Es lo que hace el Explorador; así se puede pegar en él lo copiado
  en zCommander y al revés.
- Al leer, el Explorador pone 5 (copiar y enlazar) al copiar y 2 al cortar:
  se mueve solo si el efecto pide mover y no pide copiar.
- Se usa ``win32clipboard`` (pywin32) y no ``wx.Clipboard`` porque los
  servicios no importan wx; los dos hablan con el mismo portapapeles.
- Otro programa puede tener el portapapeles abierto un instante: se reintenta
  unas veces antes de dar error.
"""

from __future__ import annotations

import builtins
import logging
import struct
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from app.services.vfs.base import ErrorArchivos

log = logging.getLogger(__name__)

DROPEFFECT_NONE = 0
DROPEFFECT_COPY = 1
DROPEFFECT_MOVE = 2
DROPEFFECT_LINK = 4

FORMATO_EFECTO = "Preferred DropEffect"
# Cabecera DROPFILES: pFiles, pt.x, pt.y, fNC, fWide (rutas en UTF-16).
_CABECERA = struct.Struct("<IiiII")

REINTENTOS = 10
PAUSA_REINTENTO = 0.02


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorPortapapeles(ErrorArchivos):
	"""No se pudo abrir, leer o escribir el portapapeles."""


@dataclass(frozen=True)
class ArchivosPortapapeles:
	"""Archivos del portapapeles.

	:param rutas: rutas completas, en el orden en que se pusieron.
	:param mover: se cortaron (pegar debe mover).
	:param secuencia: número de secuencia del portapapeles al leerlo (para
		vaciarlo después de pegar lo cortado solo si nadie lo ha cambiado).
	"""

	rutas: tuple[str, ...]
	mover: bool
	secuencia: int


def _modulo():
	import win32clipboard

	return win32clipboard


def _formato_efecto() -> int:
	return _modulo().RegisterClipboardFormat(FORMATO_EFECTO)


_por_hilo = threading.local()


def _ventana_propietaria() -> int:
	"""Ventana oculta (solo de mensajes) de este hilo para abrir el portapapeles.

	Con ``OpenClipboard(NULL)`` el portapapeles no queda ligado a ninguna
	ventana y, justo después de escribir en él, los programas que lo vigilan
	(historial del portapapeles) lo cierran por debajo: la lectura siguiente
	falla con «El subproceso no tiene abierto un Portapapeles». Con una ventana
	propia no pasa.
	"""
	hwnd = getattr(_por_hilo, "hwnd", 0)
	if hwnd:
		return hwnd
	try:
		import win32con
		import win32gui

		hwnd = win32gui.CreateWindowEx(0, "STATIC", "zCommander portapapeles", 0, 0, 0, 0, 0, win32con.HWND_MESSAGE, 0, 0, None)
	except Exception:  # noqa: BLE001 - sin ventana propia se usa NULL, que casi siempre funciona
		log.warning("No se pudo crear la ventana del portapapeles", exc_info=True)
		hwnd = 0
	_por_hilo.hwnd = hwnd
	return hwnd


@contextmanager
def _abierto() -> Iterator[object]:
	"""Abre el portapapeles con reintentos y lo cierra siempre."""
	portapapeles = _modulo()
	propietaria = _ventana_propietaria()
	ultimo: BaseException | None = None
	for intento in range(REINTENTOS):
		try:
			portapapeles.OpenClipboard(propietaria)
			break
		except portapapeles.error as error:
			ultimo = error
			log.debug("Portapapeles ocupado (intento %d)", intento + 1)
			time.sleep(PAUSA_REINTENTO)
	else:
		raise ErrorPortapapeles(_("Otro programa está usando el portapapeles. Inténtelo de nuevo.")) from ultimo
	try:
		yield portapapeles
	finally:
		try:
			portapapeles.CloseClipboard()
		except portapapeles.error:
			log.debug("No se pudo cerrar el portapapeles", exc_info=True)


def datos_hdrop(rutas: Sequence[str]) -> bytes:
	"""Bloque ``DROPFILES`` con las rutas en UTF-16 terminadas en doble nulo."""
	lista = "".join(ruta + "\0" for ruta in rutas) + "\0"
	return _CABECERA.pack(_CABECERA.size, 0, 0, 0, 1) + lista.encode("utf-16-le")


def poner_archivos(rutas: Sequence[str], mover: bool = False) -> None:
	"""Pone las rutas como archivos (``CF_HDROP``) con el efecto copiar (1) o mover (2)."""
	if not rutas:
		raise ErrorPortapapeles(_("No hay archivos que poner en el portapapeles"))
	import win32con

	efecto = DROPEFFECT_MOVE if mover else DROPEFFECT_COPY
	try:
		with _abierto() as portapapeles:
			portapapeles.EmptyClipboard()
			portapapeles.SetClipboardData(win32con.CF_HDROP, datos_hdrop(rutas))
			portapapeles.SetClipboardData(_formato_efecto(), struct.pack("<I", efecto))
	except _modulo().error as error:
		raise ErrorPortapapeles(_("No se pudo escribir en el portapapeles: {e}").format(e=error.strerror)) from error
	log.info("Portapapeles: %d rutas (%s)", len(rutas), "cortar" if mover else "copiar")


def efecto_preferido() -> int | None:
	"""«Preferred DropEffect» del portapapeles, o ``None`` si no lo tiene."""
	with _abierto() as portapapeles:
		return _leer_efecto(portapapeles)


def _leer_efecto(portapapeles) -> int | None:
	formato = _formato_efecto()
	if not portapapeles.IsClipboardFormatAvailable(formato):
		return None
	datos = portapapeles.GetClipboardData(formato)
	if isinstance(datos, str):
		datos = datos.encode("latin-1", errors="replace")
	if not datos or len(datos) < 4:
		return None
	return struct.unpack_from("<I", datos)[0]


def rutas_de_hdrop(datos: bytes) -> list[str]:
	"""Rutas de un bloque ``DROPFILES`` (UTF-16 o, en programas antiguos, ANSI)."""
	if len(datos) < _CABECERA.size:
		return []
	desplazamiento, _x, _y, _nc, ancho = _CABECERA.unpack_from(datos)
	cuerpo = datos[desplazamiento:]
	if ancho:
		texto = cuerpo.decode("utf-16-le", errors="replace")
	else:
		texto = cuerpo.decode("mbcs", errors="replace")
	rutas = []
	for parte in texto.split("\0"):
		if not parte:
			break
		rutas.append(parte)
	return rutas


def _leer_hdrop(portapapeles) -> list[str]:
	"""Lee ``CF_HDROP`` copiando la memoria del portapapeles.

	``GetClipboardData(CF_HDROP)`` de pywin32 llama a ``DragFinish``, que libera
	la memoria que es del portapapeles: después el portapapeles queda cerrado
	y estropeado para el resto de programas. Por eso se lee el bloque a mano.
	"""
	import ctypes

	import win32con

	kernel32 = ctypes.windll.kernel32
	kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
	kernel32.GlobalLock.restype = ctypes.c_void_p
	kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
	kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
	kernel32.GlobalSize.restype = ctypes.c_size_t
	asa = int(portapapeles.GetClipboardDataHandle(win32con.CF_HDROP))
	if not asa:
		return []
	puntero = kernel32.GlobalLock(asa)
	if not puntero:
		return []
	try:
		datos = ctypes.string_at(puntero, kernel32.GlobalSize(asa))
	finally:
		kernel32.GlobalUnlock(asa)
	return rutas_de_hdrop(datos)


def hay_archivos() -> bool:
	"""El portapapeles tiene archivos (sin abrirlo: se puede llamar al pintar menús)."""
	import win32con

	try:
		return bool(_modulo().IsClipboardFormatAvailable(win32con.CF_HDROP))
	except _modulo().error:
		log.debug("No se pudo consultar el portapapeles", exc_info=True)
		return False


def leer_archivos() -> ArchivosPortapapeles | None:
	"""Archivos del portapapeles (copiados aquí o en el Explorador), o ``None`` si no hay."""
	import win32con

	try:
		with _abierto() as portapapeles:
			if not portapapeles.IsClipboardFormatAvailable(win32con.CF_HDROP):
				return None
			efecto = _leer_efecto(portapapeles)
			rutas = tuple(_leer_hdrop(portapapeles))
			secuencia = int(portapapeles.GetClipboardSequenceNumber())
	except _modulo().error as error:
		raise ErrorPortapapeles(_("No se pudo leer el portapapeles: {e}").format(e=error.strerror)) from error
	if not rutas:
		return None
	mover = efecto is not None and bool(efecto & DROPEFFECT_MOVE) and not efecto & DROPEFFECT_COPY
	return ArchivosPortapapeles(rutas, mover, secuencia)


def poner_texto(texto: str) -> None:
	import win32con

	try:
		with _abierto() as portapapeles:
			portapapeles.EmptyClipboard()
			portapapeles.SetClipboardData(win32con.CF_UNICODETEXT, texto)
	except _modulo().error as error:
		raise ErrorPortapapeles(_("No se pudo escribir en el portapapeles: {e}").format(e=error.strerror)) from error


def leer_texto() -> str | None:
	"""Texto del portapapeles, o ``None`` si no tiene."""
	import win32con

	try:
		with _abierto() as portapapeles:
			if not portapapeles.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
				return None
			return str(portapapeles.GetClipboardData(win32con.CF_UNICODETEXT))
	except _modulo().error as error:
		raise ErrorPortapapeles(_("No se pudo leer el portapapeles: {e}").format(e=error.strerror)) from error


def secuencia() -> int:
	"""Número que Windows cambia cada vez que alguien escribe en el portapapeles."""
	return int(_modulo().GetClipboardSequenceNumber())


def vaciar_si_no_cambio(secuencia_leida: int) -> bool:
	"""Vacía el portapapeles si sigue igual que cuando se leyó.

	Tras pegar lo cortado, los archivos ya no están donde dice el portapapeles
	(el Explorador hace lo mismo); si otro programa ha puesto algo después, se
	respeta.
	"""
	try:
		with _abierto() as portapapeles:
			if int(portapapeles.GetClipboardSequenceNumber()) != secuencia_leida:
				return False
			portapapeles.EmptyClipboard()
			return True
	except (ErrorPortapapeles, _modulo().error):
		log.warning("No se pudo vaciar el portapapeles tras mover", exc_info=True)
		return False
