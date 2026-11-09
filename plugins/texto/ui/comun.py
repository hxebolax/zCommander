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
