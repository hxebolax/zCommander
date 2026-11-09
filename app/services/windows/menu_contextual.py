# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Menú contextual del Explorador, propiedades y «Abrir con» de Windows para archivos locales.

Por qué así (sección 8.10 del diseño):

- El menú es el del propio Explorador (``IContextMenu`` que da la carpeta del
  shell), dibujado con ``TrackPopupMenuEx``: es un menú nativo de Windows, así
  que los lectores lo anuncian como cualquier menú contextual y no hay que
  imitarlo.
- Los submenús «Enviar a», «Abrir con» y los de las extensiones del shell se
  rellenan cuando Windows avisa con ``WM_INITMENUPOPUP``; esos avisos solo
  llegan a la ventana propietaria del menú. Por eso el menú se abre sobre una
  ventana auxiliar oculta (hija de la ventana principal, para no robarle el
  primer plano) cuyo procedimiento reenvía ``WM_INITMENUPOPUP``,
  ``WM_DRAWITEM``, ``WM_MEASUREITEM`` y ``WM_MENUCHAR`` a
  ``IContextMenu3.HandleMenuMsg2`` (o a ``IContextMenu2.HandleMenuMsg``).
- pywin32 no envuelve ``IContextMenu2`` ni ``IContextMenu3``; las interfaces
  se declaran aquí con comtypes (dependencia de la aplicación) y las funciones
  del shell se llaman con ctypes.
- Todo se usa en el hilo de la interfaz (el shell lo exige: STA) y solo con
  rutas locales; las rutas de 260 caracteres o más no las admite el shell y
  se rechazan con un mensaje claro (sección 15).

Este módulo no importa wx: recibe y devuelve identificadores de ventana
(``HWND``) como enteros.
"""

from __future__ import annotations

import builtins
import ctypes
import logging
import os
import subprocess
import warnings
from collections.abc import Callable, Sequence
from ctypes import POINTER, byref, c_int, c_uint, c_ulong, c_void_p, c_wchar_p, wintypes
from dataclasses import dataclass

from app.services.vfs.base import ErrorArchivos

log = logging.getLogger(__name__)

# El shell no admite rutas largas en estas llamadas (MAX_PATH = 260 con el nulo final).
LONGITUD_MAXIMA = 259

ID_PRIMERO = 1
ID_ULTIMO = 0x7FFF

CMF_NORMAL = 0x0
CMF_EXPLORE = 0x4
CMF_CANRENAME = 0x10
CMF_EXTENDEDVERBS = 0x100

GCS_VERBW = 0x4
GCS_HELPTEXTW = 0x5

CMIC_MASK_UNICODE = 0x4000
CMIC_MASK_PTINVOKE = 0x20000000
CMIC_MASK_SHIFT_DOWN = 0x10000000
CMIC_MASK_CONTROL_DOWN = 0x40000000
CMIC_MASK_FLAG_LOG_USAGE = 0x04000000

TPM_LEFTALIGN = 0x0
TPM_RIGHTBUTTON = 0x2
TPM_RETURNCMD = 0x100

WM_INITMENUPOPUP = 0x0117
WM_DRAWITEM = 0x002B
WM_MEASUREITEM = 0x002C
WM_MENUCHAR = 0x0120
WM_NULL = 0x0000
MENSAJES_REENVIADOS = (WM_INITMENUPOPUP, WM_DRAWITEM, WM_MEASUREITEM, WM_MENUCHAR)

SW_SHOWNORMAL = 1
SHOP_FILEPATH = 0x2

OAIF_ALLOW_REGISTRATION = 0x1
OAIF_REGISTER_EXT = 0x2
OAIF_EXEC = 0x4

ERROR_CANCELADO = ctypes.c_long(0x800704C7).value  # HRESULT_FROM_WIN32(ERROR_CANCELLED)

MIIM_STRING = 0x40
MIIM_ID = 0x2
MIIM_SUBMENU = 0x4
MIIM_FTYPE = 0x100
MFT_SEPARATOR = 0x800


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorShell(ErrorArchivos):
	"""El shell de Windows no pudo hacer lo pedido (mensaje en español para la persona)."""


# ── Interfaces COM (comtypes) ────────────────────────────────────────────────

_interfaces = None


def _cargar_interfaces():
	"""Declara las interfaces la primera vez que se usan (comtypes tarda en importarse)."""
	global _interfaces
	if _interfaces is not None:
		return _interfaces
	with warnings.catch_warnings():
		# comtypes 1.4.17 avisa de que aún no conoce Python 3.15; funciona igual.
		warnings.simplefilter("ignore", FutureWarning)
		import comtypes
		from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

	class IContextMenu(IUnknown):
		_iid_ = GUID("{000214E4-0000-0000-C000-000000000046}")
		_methods_ = [
			COMMETHOD([], HRESULT, "QueryContextMenu",
				(["in"], wintypes.HMENU, "hmenu"), (["in"], c_uint, "indexMenu"), (["in"], c_uint, "idCmdFirst"),
				(["in"], c_uint, "idCmdLast"), (["in"], c_uint, "uFlags")),
			COMMETHOD([], HRESULT, "InvokeCommand", (["in"], c_void_p, "pici")),
			COMMETHOD([], HRESULT, "GetCommandString",
				(["in"], ctypes.c_size_t, "idCmd"), (["in"], c_uint, "uType"), (["in"], c_void_p, "pReserved"),
				(["in"], c_void_p, "pszName"), (["in"], c_uint, "cchMax")),
		]

	class IContextMenu2(IContextMenu):
		_iid_ = GUID("{000214F4-0000-0000-C000-000000000046}")
		_methods_ = [
			COMMETHOD([], HRESULT, "HandleMenuMsg",
				(["in"], c_uint, "uMsg"), (["in"], wintypes.WPARAM, "wParam"), (["in"], wintypes.LPARAM, "lParam")),
		]

	class IContextMenu3(IContextMenu2):
		_iid_ = GUID("{BCFCE0A0-EC17-11D0-8D10-00A0C90F2719}")
		_methods_ = [
			COMMETHOD([], HRESULT, "HandleMenuMsg2",
				(["in"], c_uint, "uMsg"), (["in"], wintypes.WPARAM, "wParam"), (["in"], wintypes.LPARAM, "lParam"),
				(["in"], c_void_p, "plResult")),
		]

	class IShellFolder(IUnknown):
		# Solo hacen falta los métodos hasta GetUIObjectOf, pero en su orden del vtable.
		_iid_ = GUID("{000214E6-0000-0000-C000-000000000046}")
		_methods_ = [
			COMMETHOD([], HRESULT, "ParseDisplayName",
				(["in"], wintypes.HWND), (["in"], c_void_p), (["in"], c_wchar_p), (["in"], c_void_p),
				(["in"], c_void_p), (["in"], c_void_p)),
			COMMETHOD([], HRESULT, "EnumObjects", (["in"], wintypes.HWND), (["in"], wintypes.DWORD), (["in"], c_void_p)),
			COMMETHOD([], HRESULT, "BindToObject", (["in"], c_void_p), (["in"], c_void_p), (["in"], c_void_p), (["in"], c_void_p)),
			COMMETHOD([], HRESULT, "BindToStorage", (["in"], c_void_p), (["in"], c_void_p), (["in"], c_void_p), (["in"], c_void_p)),
			COMMETHOD([], HRESULT, "CompareIDs", (["in"], wintypes.LPARAM), (["in"], c_void_p), (["in"], c_void_p)),
			COMMETHOD([], HRESULT, "CreateViewObject", (["in"], wintypes.HWND), (["in"], c_void_p), (["in"], c_void_p)),
			COMMETHOD([], HRESULT, "GetAttributesOf", (["in"], c_uint), (["in"], c_void_p), (["in"], c_void_p)),
			COMMETHOD([], HRESULT, "GetUIObjectOf",
				(["in"], wintypes.HWND), (["in"], c_uint), (["in"], c_void_p), (["in"], c_void_p),
				(["in"], c_void_p), (["in"], c_void_p)),
		]

	iid_data_object = GUID("{0000010E-0000-0000-C000-000000000046}")

	shell32 = ctypes.windll.shell32
	shell32.SHParseDisplayName.argtypes = [c_wchar_p, c_void_p, POINTER(c_void_p), c_ulong, POINTER(c_ulong)]
	shell32.SHParseDisplayName.restype = HRESULT
	shell32.SHBindToParent.argtypes = [c_void_p, c_void_p, POINTER(c_void_p), POINTER(c_void_p)]
	shell32.SHBindToParent.restype = HRESULT
	shell32.SHGetDesktopFolder.argtypes = [POINTER(c_void_p)]
	shell32.SHGetDesktopFolder.restype = HRESULT
	shell32.SHObjectProperties.argtypes = [wintypes.HWND, wintypes.DWORD, c_wchar_p, c_wchar_p]
	shell32.SHObjectProperties.restype = wintypes.BOOL
	shell32.SHMultiFileProperties.argtypes = [c_void_p, wintypes.DWORD]
	shell32.SHMultiFileProperties.restype = HRESULT
	shell32.SHOpenWithDialog.argtypes = [wintypes.HWND, c_void_p]
	shell32.SHOpenWithDialog.restype = HRESULT
	ole32 = ctypes.windll.ole32
	ole32.CoTaskMemFree.argtypes = [c_void_p]
	ole32.CoTaskMemFree.restype = None

	_interfaces = {
		"comtypes": comtypes, "IUnknown": IUnknown, "IContextMenu": IContextMenu, "IContextMenu2": IContextMenu2,
		"IContextMenu3": IContextMenu3, "IShellFolder": IShellFolder, "IID_IDataObject": iid_data_object,
		"shell32": shell32, "ole32": ole32,
	}
	return _interfaces


def _como(puntero: c_void_p, interfaz):
	"""Convierte un puntero COM crudo (con su referencia) en un objeto comtypes que la liberará."""
	objeto = ctypes.cast(puntero, POINTER(interfaz))
	return objeto


class _CMINVOKECOMMANDINFOEX(ctypes.Structure):
	_fields_ = [
		("cbSize", wintypes.DWORD), ("fMask", wintypes.DWORD), ("hwnd", wintypes.HWND),
		("lpVerb", c_void_p), ("lpParameters", c_void_p), ("lpDirectory", c_void_p),
		("nShow", c_int), ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("lpTitle", c_void_p),
		("lpVerbW", c_void_p), ("lpParametersW", c_wchar_p), ("lpDirectoryW", c_wchar_p), ("lpTitleW", c_wchar_p),
		("ptInvoke", wintypes.POINT),
	]


class _OPENASINFO(ctypes.Structure):
	_fields_ = [("pcszFile", c_wchar_p), ("pcszClass", c_wchar_p), ("oaifInFlags", c_uint)]


class _MENUITEMINFOW(ctypes.Structure):
	_fields_ = [
		("cbSize", c_uint), ("fMask", c_uint), ("fType", c_uint), ("fState", c_uint), ("wID", c_uint),
		("hSubMenu", wintypes.HMENU), ("hbmpChecked", wintypes.HBITMAP), ("hbmpUnchecked", wintypes.HBITMAP),
		("dwItemData", ctypes.c_size_t), ("dwTypeData", c_void_p), ("cch", c_uint), ("hbmpItem", wintypes.HBITMAP),
	]


# ── Comprobaciones ──────────────────────────────────────────────────────────

def comprobar_rutas(rutas: Sequence[str]) -> list[str]:
	"""Rutas absolutas y normalizadas; lanza ``ErrorShell`` si no hay o alguna no vale para el shell."""
	if not rutas:
		raise ErrorShell(_("No hay elementos sobre los que actuar"))
	limpias = []
	for ruta in rutas:
		absoluta = os.path.abspath(ruta.removeprefix("\\\\?\\"))
		if len(absoluta) > LONGITUD_MAXIMA:
			raise ErrorShell(_("Windows no admite esta orden con rutas de más de 259 caracteres: {r}").format(r=absoluta), absoluta)
		limpias.append(absoluta)
	return limpias


# ── Objetos del shell ─────────────────────────────────────────────────────────

class _ObjetosShell:
	"""PIDL de cada ruta y la carpeta del shell que las contiene; libera todo al cerrar.

	Si todas las rutas están en la misma carpeta se usa esa carpeta y los PIDL
	relativos (lo normal en un panel). Si no (listas de resultados, cesta), se
	usa el escritorio con los PIDL absolutos, que el shell también acepta.
	"""

	def __init__(self, rutas: Sequence[str]) -> None:
		self._api = _cargar_interfaces()
		self._absolutos: list[c_void_p] = []
		self.carpeta = None
		self.hijos: list[c_void_p] = []
		try:
			self._preparar(rutas)
		except BaseException:
			self.cerrar()
			raise

	def _preparar(self, rutas: Sequence[str]) -> None:
		api = self._api
		shell32 = api["shell32"]
		for ruta in rutas:
			pidl = c_void_p()
			try:
				shell32.SHParseDisplayName(ruta, None, byref(pidl), 0, None)
			except OSError as error:
				raise ErrorShell(_("Windows no encuentra «{r}»").format(r=ruta), ruta) from error
			self._absolutos.append(pidl)
		padres = {os.path.dirname(r.rstrip("\\")).casefold() for r in rutas}
		if len(padres) == 1 and all(os.path.dirname(r.rstrip("\\")) for r in rutas):
			carpeta = c_void_p()
			for pidl in self._absolutos:
				hijo = c_void_p()
				if carpeta.value is None:
					shell32.SHBindToParent(pidl, ctypes.addressof(api["IShellFolder"]._iid_), byref(carpeta), byref(hijo))
				else:
					temporal = c_void_p()
					shell32.SHBindToParent(pidl, ctypes.addressof(api["IShellFolder"]._iid_), byref(temporal), byref(hijo))
					_como(temporal, api["IShellFolder"])  # se libera al perder la referencia
				self.hijos.append(hijo)
			self.carpeta = _como(carpeta, api["IShellFolder"])
		else:
			escritorio = c_void_p()
			shell32.SHGetDesktopFolder(byref(escritorio))
			self.carpeta = _como(escritorio, api["IShellFolder"])
			self.hijos = list(self._absolutos)

	def objeto(self, hwnd: int, interfaz=None, iid=None):
		"""``GetUIObjectOf`` de los elementos con la interfaz pedida (o el IID de una que no se declara)."""
		api = self._api
		matriz = (c_void_p * len(self.hijos))(*[h.value for h in self.hijos])
		puntero = c_void_p()
		guid = iid if iid is not None else interfaz._iid_
		self.carpeta.GetUIObjectOf(hwnd, len(self.hijos), matriz, ctypes.addressof(guid), None, byref(puntero))
		return _como(puntero, interfaz if interfaz is not None else api["IUnknown"])

	def cerrar(self) -> None:
		self.carpeta = None
		self.hijos = []
		ole32 = self._api["ole32"]
		for pidl in self._absolutos:
			if pidl.value:
				ole32.CoTaskMemFree(pidl)
		self._absolutos = []


# ── Menú contextual ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ElementoMenu:
	"""Un elemento del menú ya construido (para pruebas, registro y la ayuda)."""

	texto: str
	identificador: int
	verbo: str
	submenu: bool
	separador: bool


class MenuContextual:
	"""Menú contextual del Explorador para una o varias rutas locales.

	Uso::

		with MenuContextual(rutas, hwnd) as menu:
			elegido = menu.mostrar(x, y)
			if elegido:
				menu.ejecutar(elegido)

	:param hwnd: ventana principal (dueña de los diálogos que abra el shell y
		madre de la ventana auxiliar que recibe los mensajes del menú).
	:param extendido: añade los verbos extendidos (como Mayús+clic en el Explorador).
	"""

	_activo: MenuContextual | None = None
	_clase_registrada = False
	NOMBRE_CLASE = "zCommanderMenuShell"

	def __init__(self, rutas: Sequence[str], hwnd: int, extendido: bool = False) -> None:
		import win32gui

		self._win32gui = win32gui
		self.rutas = comprobar_rutas(rutas)
		self.hwnd = int(hwnd or 0)
		self._api = _cargar_interfaces()
		self._objetos = _ObjetosShell(self.rutas)
		self._menu2 = None
		self._menu3 = None
		self.hmenu = 0
		self._auxiliar = 0
		try:
			comtypes = self._api["comtypes"]
			try:
				self.menu = self._objetos.objeto(self.hwnd, self._api["IContextMenu"])
			except (OSError, comtypes.COMError) as error:
				raise ErrorShell(_("Windows no da menú contextual para estos elementos")) from error
			for nombre, destino in (("IContextMenu3", "_menu3"), ("IContextMenu2", "_menu2")):
				try:
					setattr(self, destino, self.menu.QueryInterface(self._api[nombre]))
				except comtypes.COMError:
					log.debug("El menú del shell no implementa %s", nombre, exc_info=True)
			self.hmenu = win32gui.CreatePopupMenu()
			opciones = CMF_NORMAL | CMF_EXPLORE | CMF_CANRENAME | (CMF_EXTENDEDVERBS if extendido else 0)
			try:
				self.menu.QueryContextMenu(self.hmenu, 0, ID_PRIMERO, ID_ULTIMO, opciones)
			except (OSError, comtypes.COMError) as error:
				raise ErrorShell(_("Windows no pudo construir el menú contextual")) from error
		except BaseException:
			self.cerrar()
			raise

	def __enter__(self) -> MenuContextual:
		return self

	def __exit__(self, *_exc) -> None:
		self.cerrar()

	# Consulta ----------------------------------------------------------------

	def verbo(self, identificador: int) -> str:
		"""Verbo canónico del elemento («open», «delete», «rename», «properties»...) o cadena vacía."""
		if not ID_PRIMERO <= identificador <= ID_ULTIMO:
			return ""
		bufer = ctypes.create_unicode_buffer(260)
		try:
			self.menu.GetCommandString(identificador - ID_PRIMERO, GCS_VERBW, None, ctypes.addressof(bufer), len(bufer))
		except (OSError, self._api["comtypes"].COMError):
			# Muchas extensiones del shell no tienen verbo: no es un error.
			return ""
		return bufer.value

	def elementos(self, hmenu: int | None = None) -> list[ElementoMenu]:
		"""Elementos de primer nivel (o de ``hmenu``) con su texto, identificador y verbo."""
		hmenu = self.hmenu if hmenu is None else hmenu
		user32 = ctypes.windll.user32
		resultado = []
		for posicion in range(user32.GetMenuItemCount(hmenu)):
			bufer = ctypes.create_unicode_buffer(512)
			info = _MENUITEMINFOW()
			info.cbSize = ctypes.sizeof(info)
			info.fMask = MIIM_STRING | MIIM_ID | MIIM_SUBMENU | MIIM_FTYPE
			info.dwTypeData = ctypes.cast(bufer, c_void_p)
			info.cch = len(bufer)
			if not user32.GetMenuItemInfoW(wintypes.HMENU(hmenu), posicion, True, byref(info)):
				continue
			separador = bool(info.fType & MFT_SEPARATOR)
			identificador = 0 if info.hSubMenu else int(info.wID)
			resultado.append(ElementoMenu(
				bufer.value, identificador, self.verbo(identificador) if identificador else "", bool(info.hSubMenu), separador,
			))
		return resultado

	def identificador_de(self, verbo: str) -> int:
		"""Identificador del elemento de primer nivel con ese verbo, o 0."""
		for elemento in self.elementos():
			if elemento.verbo.casefold() == verbo.casefold():
				return elemento.identificador
		return 0

	# Mostrar y ejecutar ----------------------------------------------------------

	def mostrar(self, x: int, y: int) -> int:
		"""Muestra el menú en (x, y) de pantalla y devuelve el identificador elegido (0 si se cierra sin elegir)."""
		win32gui = self._win32gui
		self._crear_auxiliar()
		MenuContextual._activo = self
		try:
			elegido = win32gui.TrackPopupMenu(
				self.hmenu, TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD, int(x), int(y), 0, self._auxiliar, None,
			)
			# Recomendación de Windows para que el menú se cierre bien al cambiar de ventana.
			win32gui.PostMessage(self._auxiliar, WM_NULL, 0, 0)
		finally:
			MenuContextual._activo = None
		return int(elegido or 0)

	def ejecutar(self, identificador: int, carpeta: str | None = None, mayusculas: bool = False, control: bool = False) -> None:
		"""Ejecuta el elemento elegido (lo hace el shell; no pasa por el motor de operaciones)."""
		if not ID_PRIMERO <= identificador <= ID_ULTIMO:
			raise ErrorShell(_("Elemento de menú no válido"))
		self._invocar(c_void_p(identificador - ID_PRIMERO), carpeta, mayusculas, control)

	def ejecutar_verbo(self, verbo: str, carpeta: str | None = None) -> None:
		"""Ejecuta un verbo canónico («properties», «delete»...) sin mostrar el menú."""
		bufer_a = ctypes.create_string_buffer(verbo.encode("ascii", errors="replace"))
		bufer_w = ctypes.create_unicode_buffer(verbo)
		self._invocar(ctypes.cast(bufer_a, c_void_p), carpeta, False, False, ctypes.cast(bufer_w, c_void_p))

	def _invocar(self, verbo_a: c_void_p, carpeta: str | None, mayusculas: bool, control: bool,
			verbo_w: c_void_p | None = None) -> None:
		info = _CMINVOKECOMMANDINFOEX()
		info.cbSize = ctypes.sizeof(info)
		info.fMask = CMIC_MASK_UNICODE | CMIC_MASK_FLAG_LOG_USAGE
		if mayusculas:
			info.fMask |= CMIC_MASK_SHIFT_DOWN
		if control:
			info.fMask |= CMIC_MASK_CONTROL_DOWN
		info.hwnd = self.hwnd
		info.lpVerb = verbo_a
		info.lpVerbW = verbo_w if verbo_w is not None else verbo_a
		directorio = carpeta or os.path.dirname(self.rutas[0])
		info.lpDirectoryW = directorio
		info.nShow = SW_SHOWNORMAL
		try:
			self.menu.InvokeCommand(ctypes.addressof(info))
		except (OSError, self._api["comtypes"].COMError) as error:
			if getattr(error, "hresult", None) == ERROR_CANCELADO or getattr(error, "winerror", None) == ERROR_CANCELADO:
				log.info("La persona canceló la orden del shell")
				return
			raise ErrorShell(_("Windows no pudo completar la orden del menú: {e}").format(e=error)) from error

	# Ventana auxiliar ----------------------------------------------------------

	@classmethod
	def _registrar_clase(cls, win32gui) -> None:
		if cls._clase_registrada:
			return
		import win32api

		clase = win32gui.WNDCLASS()
		clase.hInstance = win32api.GetModuleHandle(None)
		clase.lpszClassName = cls.NOMBRE_CLASE
		clase.lpfnWndProc = cls._procedimiento
		try:
			win32gui.RegisterClass(clase)
		except win32gui.error as error:
			# 1410: la clase ya existe (otra instancia del módulo la registró).
			if getattr(error, "winerror", None) != 1410:
				raise
		cls._clase_registrada = True

	@staticmethod
	def _procedimiento(hwnd, mensaje, wparam, lparam):
		"""Reenvía al shell los mensajes que rellenan y dibujan los submenús."""
		import win32gui

		menu = MenuContextual._activo
		if menu is not None and mensaje in MENSAJES_REENVIADOS:
			try:
				if menu._menu3 is not None:
					resultado = ctypes.c_ssize_t(0)
					menu._menu3.HandleMenuMsg2(mensaje, wparam, lparam, ctypes.addressof(resultado))
					return resultado.value
				if menu._menu2 is not None:
					menu._menu2.HandleMenuMsg(mensaje, wparam, lparam)
					return 0
			except (OSError, menu._api["comtypes"].COMError):
				# Una extensión del shell que falla al dibujar un elemento no debe cerrar el menú.
				log.debug("Una extensión del shell no atendió el mensaje %#x", mensaje, exc_info=True)
		return win32gui.DefWindowProc(hwnd, mensaje, wparam, lparam)

	def _crear_auxiliar(self) -> None:
		if self._auxiliar:
			return
		import win32api
		import win32con

		win32gui = self._win32gui
		self._registrar_clase(win32gui)
		if self.hwnd:
			estilo, padre = win32con.WS_CHILD, self.hwnd
		else:
			estilo, padre = win32con.WS_POPUP, 0
		self._auxiliar = win32gui.CreateWindowEx(
			0, self.NOMBRE_CLASE, "", estilo, 0, 0, 0, 0, padre, 0, win32api.GetModuleHandle(None), None,
		)

	def cerrar(self) -> None:
		"""Libera el menú, la ventana auxiliar y los objetos del shell (se puede llamar varias veces)."""
		win32gui = self._win32gui
		if self._auxiliar:
			try:
				win32gui.DestroyWindow(self._auxiliar)
			except win32gui.error:
				log.debug("No se pudo destruir la ventana auxiliar del menú", exc_info=True)
			self._auxiliar = 0
		if self.hmenu:
			try:
				win32gui.DestroyMenu(self.hmenu)
			except win32gui.error:
				log.debug("No se pudo destruir el menú del shell", exc_info=True)
			self.hmenu = 0
		self._menu3 = None
		self._menu2 = None
		self.menu = None
		if getattr(self, "_objetos", None) is not None:
			self._objetos.cerrar()
			self._objetos = None


def mostrar_menu(
	rutas: Sequence[str],
	hwnd: int,
	x: int,
	y: int,
	extendido: bool = False,
	propios: dict[str, Callable[[], None]] | None = None,
) -> str | None:
	"""Muestra el menú del Explorador y ejecuta lo elegido.

	:param propios: verbos que hace zCommander en lugar del shell (``{"rename": ...}``):
		el shell sin una vista del Explorador no sabe renombrar en el sitio.
	:return: el verbo elegido («» si no tiene), o ``None`` si se cerró sin elegir.
	"""
	with MenuContextual(rutas, hwnd, extendido) as menu:
		elegido = menu.mostrar(x, y)
		if not elegido:
			return None
		verbo = menu.verbo(elegido)
		log.info("Menú de Windows: «%s» (verbo «%s») sobre %d elementos", elegido, verbo, len(menu.rutas))
		funcion = (propios or {}).get(verbo.casefold())
		if funcion is not None:
			funcion()
			return verbo
		menu.ejecutar(elegido)
		return verbo


# ── Propiedades y «Abrir con» ─────────────────────────────────────────────────

def propiedades(rutas: Sequence[str], hwnd: int) -> None:
	"""Diálogo de propiedades de Windows (``SHObjectProperties``; con varios, ``SHMultiFileProperties``).

	El diálogo es no modal y lo gestiona el shell en su propio hilo.
	"""
	rutas = comprobar_rutas(rutas)
	api = _cargar_interfaces()
	if len(rutas) == 1:
		if api["shell32"].SHObjectProperties(int(hwnd or 0), SHOP_FILEPATH, rutas[0], None):
			return
		log.info("SHObjectProperties falló con %s; se prueba el verbo «properties»", rutas[0])
		with MenuContextual(rutas, hwnd) as menu:
			menu.ejecutar_verbo("properties")
		return
	objetos = _ObjetosShell(rutas)
	try:
		datos = objetos.objeto(int(hwnd or 0), iid=api["IID_IDataObject"])
		try:
			api["shell32"].SHMultiFileProperties(datos, 0)
		except OSError as error:
			raise ErrorShell(_("Windows no pudo abrir las propiedades: {e}").format(e=error)) from error
		finally:
			del datos
	except (OSError, api["comtypes"].COMError) as error:
		raise ErrorShell(_("Windows no pudo abrir las propiedades: {e}").format(e=error)) from error
	finally:
		objetos.cerrar()


def abrir_con(ruta: str, hwnd: int) -> bool:
	"""Diálogo «Abrir con» de Windows (``SHOpenWithDialog``; si no existe, ``OpenAs_RunDLL``).

	:return: ``False`` si la persona lo canceló.
	"""
	ruta = comprobar_rutas([ruta])[0]
	api = _cargar_interfaces()
	info = _OPENASINFO(ruta, None, OAIF_ALLOW_REGISTRATION | OAIF_REGISTER_EXT | OAIF_EXEC)
	try:
		api["shell32"].SHOpenWithDialog(int(hwnd or 0), byref(info))
		return True
	except OSError as error:
		if getattr(error, "winerror", None) == ERROR_CANCELADO:
			return False
		log.info("SHOpenWithDialog falló (%s); se usa OpenAs_RunDLL", error)
	except AttributeError:
		log.info("SHOpenWithDialog no existe en este Windows; se usa OpenAs_RunDLL")
	rundll = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "rundll32.exe")
	subprocess.Popen([rundll, "shell32.dll,OpenAs_RunDLL", ruta])  # noqa: S603 - ruta elegida por la persona
	return True
