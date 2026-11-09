# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Zona de salida de las órdenes (sustituye a los paneles con «Mostrar u ocultar los paneles»)."""

from __future__ import annotations

import builtins

import wx

LIMITE = 2_000_000  # caracteres; lo más antiguo se descarta


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class SalidaOrdenes(wx.Panel):
	"""Etiqueta y texto de solo lectura con todo lo escrito por las órdenes de la sesión."""

	def __init__(self, padre: wx.Window) -> None:
		super().__init__(padre)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.etiqueta = wx.StaticText(self, label=_("Salida de las órdenes:"))
		self.texto = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL)
		self.texto.SetHelpText(_("Lo que han escrito las órdenes de la sesión. Ctrl+O vuelve a los paneles."))
		sizer.Add(self.etiqueta, 0, wx.ALL, 4)
		sizer.Add(self.texto, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
		self.SetSizer(sizer)

	def escribir(self, texto: str) -> None:
		"""Añade una línea al final (sin mover el cursor si la persona está leyendo más arriba)."""
		posicion = self.texto.GetInsertionPoint()
		al_final = posicion >= self.texto.GetLastPosition()
		self.texto.AppendText(texto + "\n")
		if self.texto.GetLastPosition() > LIMITE:
			self.texto.Remove(0, self.texto.GetLastPosition() - LIMITE)
		if not al_final:
			self.texto.SetInsertionPoint(posicion)

	def enfocar_final(self) -> None:
		self.texto.SetFocus()
		self.texto.SetInsertionPointEnd()

	def mostrar(self) -> None:
		"""Servicio «salida»: muestra la zona (oculta los paneles)."""
		ventana = wx.GetTopLevelParent(self)
		if not self.IsShown() and hasattr(ventana, "alternar_paneles"):
			ventana.alternar_paneles()

	def valor(self) -> str:
		return self.texto.GetValue()
