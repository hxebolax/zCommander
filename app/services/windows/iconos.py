# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Iconos del sistema y descripción del tipo de archivo («Documento de texto»), por extensión.

Por qué así (secciones 4.3, 9.5 y 13 del diseño):

- ``SHGetFileInfoW`` con ``SHGFI_USEFILEATTRIBUTES`` responde solo con el
  nombre, sin tocar el disco: sirve igual para archivos de comprimidos o de
  un servidor, y no despierta unidades dormidas ni descarga archivos de la nube.
- La respuesta depende solo de la extensión, así que se guarda en caché por
  extensión (una lista de 100 000 archivos pide unas pocas decenas).
- La primera consulta de una extensión puede cargar extensiones del shell y
  tardar: quien llama lo hace desde un hilo de trabajo (la ventana con
  ``pedir_tipo`` y la lista con su gestor de iconos). El shell necesita COM
  iniciado en ese hilo; se inicia aquí la primera vez en cada hilo.
- Los iconos se devuelven como ``HICON`` (entero): la interfaz los convierte
  en ``wx.Icon`` en su hilo. Este módulo no importa wx.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

log = logging.getLogger(__name__)

FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_NORMAL = 0x80

SHGFI_ICON = 0x100
SHGFI_TYPENAME = 0x400
SHGFI_SMALLICON = 0x1
SHGFI_USEFILEATTRIBUTES = 0x10

CARPETA = "<carpeta>"
SIN_EXTENSION = ""


class _SHFILEINFOW(ctypes.Structure):
	_fields_ = [
		("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int), ("dwAttributes", wintypes.DWORD),
		("szDisplayName", wintypes.WCHAR * 260), ("szTypeName", wintypes.WCHAR * 80),
	]


_candado = threading.Lock()
_descripciones: dict[str, str | None] = {}
_por_hilo = threading.local()
_funcion = None


def _shgetfileinfo():
	global _funcion
	if _funcion is None:
		funcion = ctypes.windll.shell32.SHGetFileInfoW
		funcion.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(_SHFILEINFOW), wintypes.UINT, wintypes.UINT]
		funcion.restype = ctypes.c_size_t
		_funcion = funcion
	return _funcion


def _iniciar_com() -> None:
	"""COM en este hilo (lo pide ``SHGetFileInfo``); si ya estaba iniciado, no pasa nada."""
	if getattr(_por_hilo, "com", False):
		return
	try:
		resultado = ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
		# S_OK, S_FALSE (ya iniciado) o RPC_E_CHANGED_MODE (el hilo ya es MTA): en todos funciona.
		log.debug("CoInitializeEx en %s: %#x", threading.current_thread().name, resultado & 0xFFFFFFFF)
	except OSError:
		log.debug("No se pudo iniciar COM", exc_info=True)
	_por_hilo.com = True


def clave_extension(nombre_o_extension: str) -> str:
	"""Extensión en minúsculas y sin punto de «txt», «.txt» o «informe.txt» («» si no tiene)."""
	texto = (nombre_o_extension or "").strip()
	if not texto:
		return SIN_EXTENSION
	if "." not in texto:
		return texto.lower()
	punto = texto.rfind(".")
	if punto == 0 and texto.count(".") == 1 and len(texto) > 1:
		return texto[1:].lower()  # «.txt»
	if punto <= 0 or punto == len(texto) - 1:
		return SIN_EXTENSION
	return texto[punto + 1 :].lower()


def _consultar(clave: str, banderas: int) -> _SHFILEINFOW | None:
	_iniciar_com()
	info = _SHFILEINFOW()
	if clave == CARPETA:
		nombre, atributos = "carpeta", FILE_ATTRIBUTE_DIRECTORY
	else:
		nombre, atributos = ("archivo." + clave) if clave else "archivo", FILE_ATTRIBUTE_NORMAL
	if not _shgetfileinfo()(nombre, atributos, ctypes.byref(info), ctypes.sizeof(info), banderas | SHGFI_USEFILEATTRIBUTES):
		return None
	return info


def descripcion_tipo(nombre_o_extension: str) -> str | None:
	"""Descripción de Windows del tipo («Documento de texto»), o ``None`` si no hay extensión o no la da.

	Admite una extensión («txt», «.txt») o un nombre de archivo («nota.txt»).
	"""
	clave = clave_extension(nombre_o_extension)
	if not clave:
		return None
	with _candado:
		if clave in _descripciones:
			return _descripciones[clave]
	try:
		info = _consultar(clave, SHGFI_TYPENAME)
		texto = info.szTypeName.strip() if info is not None else ""
	except OSError:
		log.debug("SHGetFileInfo falló con .%s", clave, exc_info=True)
		texto = ""
	resultado = texto or None
	with _candado:
		_descripciones[clave] = resultado
	return resultado


def icono_pequeno(clave: str) -> int:
	"""``HICON`` del icono pequeño de una extensión (o de ``CARPETA``); 0 si no hay.

	Quien lo recibe es su dueño: lo entrega a ``wx.Icon`` o lo libera con
	``destruir_icono``.
	"""
	try:
		info = _consultar(clave, SHGFI_ICON | SHGFI_SMALLICON)
	except OSError:
		log.debug("SHGetFileInfo (icono) falló con %r", clave, exc_info=True)
		return 0
	return int(info.hIcon or 0) if info is not None else 0


def destruir_icono(hicon: int) -> None:
	if hicon:
		ctypes.windll.user32.DestroyIcon(wintypes.HICON(hicon))


def olvidar() -> None:
	"""Vacía la caché (al instalar un programa cambian las descripciones; lo usan las pruebas)."""
	with _candado:
		_descripciones.clear()
