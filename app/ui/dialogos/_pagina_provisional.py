# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Página propia de Preferencias provisional (diseño 2.0, 10.18): la base de las de N2.

Las páginas propias que N2 deja provisionales (Sonidos de SO, Confirmaciones de
PE) muestran un texto de solo lectura que dice que la página aún no está
disponible y cumplen el protocolo ``PaginaPropia`` sin escribir nada.
"""

from __future__ import annotations

import builtins

import wx


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class PaginaProvisional(wx.Panel):
	"""Cumple ``PaginaPropia`` (validar, aplicar, restablecer, control_inicial) sin tocar la configuración."""

	def __init__(self, padre: wx.Window, titulo: str) -> None:
		super().__init__(padre, name=titulo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label=_("&Estado de la página:"))
		self.texto = wx.TextCtrl(self, value=_("Esta página aún no está disponible: {t}.").format(t=titulo),
			style=wx.TE_MULTILINE | wx.TE_READONLY)
		self.texto.SetHelpText(_("Esta página de Preferencias llegará en una versión próxima."))
		sizer.Add(etiqueta, 0, wx.ALL, 5)
		sizer.Add(self.texto, 1, wx.EXPAND | wx.ALL, 5)
		self.SetSizer(sizer)

	def validar(self) -> str | None:
		return None

	def aplicar(self) -> bool:
		return True

	def restablecer(self) -> None:
		return None

	def control_inicial(self) -> wx.Window:
		return self.texto
