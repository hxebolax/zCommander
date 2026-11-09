# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Conversión de un ``wx.KeyEvent`` a la tecla canónica de ``app.services.teclas``."""

from __future__ import annotations

import wx

_NOMBRES = {
	wx.WXK_RETURN: "Return", wx.WXK_NUMPAD_ENTER: "Return", wx.WXK_BACK: "Back", wx.WXK_DELETE: "Delete",
	wx.WXK_NUMPAD_DELETE: "Delete", wx.WXK_INSERT: "Insert", wx.WXK_NUMPAD_INSERT: "Insert",
	wx.WXK_SPACE: "Space", wx.WXK_NUMPAD_SPACE: "Space", wx.WXK_TAB: "Tab", wx.WXK_NUMPAD_TAB: "Tab",
	wx.WXK_ESCAPE: "Escape", wx.WXK_HOME: "Home", wx.WXK_NUMPAD_HOME: "Home", wx.WXK_END: "End",
	wx.WXK_NUMPAD_END: "End", wx.WXK_PAGEUP: "PgUp", wx.WXK_NUMPAD_PAGEUP: "PgUp", wx.WXK_PAGEDOWN: "PgDn",
	wx.WXK_NUMPAD_PAGEDOWN: "PgDn", wx.WXK_UP: "Up", wx.WXK_NUMPAD_UP: "Up", wx.WXK_DOWN: "Down",
	wx.WXK_NUMPAD_DOWN: "Down", wx.WXK_LEFT: "Left", wx.WXK_NUMPAD_LEFT: "Left", wx.WXK_RIGHT: "Right",
	wx.WXK_NUMPAD_RIGHT: "Right", wx.WXK_ADD: "KP_ADD", wx.WXK_NUMPAD_ADD: "KP_ADD",
	wx.WXK_SUBTRACT: "KP_SUBTRACT", wx.WXK_NUMPAD_SUBTRACT: "KP_SUBTRACT", wx.WXK_MULTIPLY: "KP_MULTIPLY",
	wx.WXK_NUMPAD_MULTIPLY: "KP_MULTIPLY", wx.WXK_DIVIDE: "KP_DIVIDE", wx.WXK_NUMPAD_DIVIDE: "KP_DIVIDE",
	wx.WXK_WINDOWS_MENU: "Menu", wx.WXK_MENU: "Menu",
}
_MODIFICADORES_SOLOS = {wx.WXK_SHIFT, wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_WINDOWS_LEFT, wx.WXK_WINDOWS_RIGHT, wx.WXK_CAPITAL,
	wx.WXK_NUMLOCK, wx.WXK_SCROLL, wx.WXK_RAW_CONTROL}


def tecla_de_evento(evento: wx.KeyEvent) -> str:
	"""Tecla canónica (``Ctrl+Shift+F10``) o cadena vacía si solo es un modificador o una tecla rara.

	Con ``EVT_CHAR_HOOK`` el código es el de la tecla física (``KEY_DOWN``):
	las letras llegan en mayúscula y los dígitos como su carácter.
	"""
	codigo = evento.GetKeyCode()
	if codigo in _MODIFICADORES_SOLOS:
		return ""
	if codigo in _NOMBRES:
		tecla = _NOMBRES[codigo]
	elif wx.WXK_F1 <= codigo <= wx.WXK_F24:
		tecla = f"F{codigo - wx.WXK_F1 + 1}"
	elif wx.WXK_NUMPAD0 <= codigo <= wx.WXK_NUMPAD9:
		tecla = str(codigo - wx.WXK_NUMPAD0)
	elif codigo == wx.WXK_NUMPAD_DECIMAL:
		tecla = "."
	elif 33 <= codigo < 127:
		tecla = chr(codigo).upper()
	elif 127 < codigo < 256:
		tecla = chr(codigo).upper()
	else:
		return ""
	partes = []
	if evento.ControlDown() and not evento.AltDown():
		partes.append("Ctrl")
	elif evento.ControlDown() and evento.AltDown():
		# Ctrl+Alt es AltGr en teclados europeos: no se usa como atajo.
		return ""
	if evento.AltDown():
		partes.append("Alt")
	if evento.ShiftDown():
		partes.append("Shift")
	partes.append(tecla)
	return "+".join(partes)


def es_campo_de_texto(ventana: wx.Window | None) -> bool:
	"""Controles en los que se escribe (las teclas de edición son suyas)."""
	if isinstance(ventana, wx.TextCtrl):
		# Los de solo lectura también: el lector usa flechas, Inicio y Fin para leerlos.
		return True
	return isinstance(ventana, (wx.ComboBox, wx.SpinCtrl, wx.SearchCtrl))
