# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Barra de teclas F1 a F10 (para el ratón): el texto cambia con Mayús, Ctrl o Alt, como en Norton."""

from __future__ import annotations

import builtins

import wx

from app.ui import ordenes


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class BarraTeclas(wx.Panel):
	"""Diez botones que no reciben el foco con Tab: todas sus acciones tienen tecla."""

	def __init__(self, padre: wx.Window, ventana) -> None:
		super().__init__(padre)
		self.ventana = ventana
		self._modificador = None
		sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.botones: list[wx.Button] = []
		for i in range(10):
			boton = wx.Button(self, label=f"F{i + 1}", style=wx.BU_EXACTFIT)
			boton.SetCanFocus(False)
			boton.Bind(wx.EVT_BUTTON, lambda _e, n=i: self._pulsar(n))
			sizer.Add(boton, 1, wx.EXPAND)
			self.botones.append(boton)
		self.SetSizer(sizer)
		self.actualizar(forzar=True)

	def _modificador_actual(self) -> str:
		if wx.GetKeyState(wx.WXK_CONTROL):
			return "Ctrl"
		if wx.GetKeyState(wx.WXK_ALT):
			return "Alt"
		if wx.GetKeyState(wx.WXK_SHIFT):
			return "Shift"
		return ""

	def actualizar(self, forzar: bool = False) -> None:
		if not self.IsShown() and not forzar:
			return
		modificador = self._modificador_actual()
		if modificador == self._modificador and not forzar:
			return
		self._modificador = modificador
		for boton, (tecla, _orden, texto) in zip(self.botones, ordenes.barra_teclas(modificador), strict=False):
			boton.SetLabel(f"{tecla} {_(texto)}" if texto else tecla)
			boton.Enable(bool(_orden))
			boton.SetToolTip(_(ordenes.POR_ID[_orden].ayuda) if _orden else "")
		self.Layout()

	def _pulsar(self, indice: int) -> None:
		_tecla, orden, _texto = ordenes.barra_teclas(self._modificador or "")[indice]
		if orden:
			self.ventana.ejecutar_orden(orden)
			wx.CallAfter(self.ventana.activo.enfocar)
