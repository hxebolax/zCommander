# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Piezas comunes de los diálogos del complemento: F1 y botoneras con la acción en el botón."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import wx


def atender_f1(ventana: wx.Window, al_ayuda: Callable[[], None] | None) -> None:
	"""F1 abre la ayuda del complemento (se enlaza DESPUÉS de ``preparar_dialogo``, que deja pasar F1)."""

	def al_pulsar(evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F1 and not evento.HasAnyModifiers() and al_ayuda is not None:
			al_ayuda()
			return
		evento.Skip()

	ventana.Bind(wx.EVT_CHAR_HOOK, al_pulsar)


def atender_ctrl_h(ventana: wx.Window, anunciar: Callable[[str], None]) -> None:
	"""Control+H en una ventana no modal dice el nombre y la ayuda del control enfocado (los diálogos ya lo hacen)."""

	def al_pulsar(evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == ord("H") and evento.GetModifiers() == wx.MOD_CONTROL:
			control = wx.Window.FindFocus()
			if control is not None:
				nombre = control.GetName() if not isinstance(control, wx.TextCtrl) or not control.IsEditable() else ""
				etiqueta = control.GetPrevSibling()
				if isinstance(etiqueta, wx.StaticText):
					nombre = etiqueta.GetLabelText().rstrip(":")
				ayuda = control.GetHelpText() or ""
				anunciar(". ".join(p for p in (nombre, ayuda) if p) or "Sin ayuda para este control")
			return
		evento.Skip()

	ventana.Bind(wx.EVT_CHAR_HOOK, al_pulsar)


def botonera(padre: wx.Window, botones: Sequence[tuple[int, str]], predeterminado: int) -> wx.StdDialogButtonSizer:
	"""Botonera con etiquetas propias en español («Con&vertir», «&Cancelar»); ``predeterminado`` responde a Intro."""
	sizer = wx.StdDialogButtonSizer()
	for identificador, etiqueta in botones:
		boton = wx.Button(padre, identificador, etiqueta)
		sizer.AddButton(boton)
		if identificador == predeterminado:
			boton.SetDefault()
	sizer.Realize()
	return sizer
