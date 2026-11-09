# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo de la lista de marcadores de una pista (Ctrl+M en la ventana del reproductor)."""

from __future__ import annotations

import builtins
from collections.abc import Callable
from typing import Any

import wx

from . import tiempos


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoMarcadores:
	"""Lista de marcadores: «Ir al marcador» (Intro), «Borrar» y «Cancelar». ``self.dialogo`` es el ``wx.Dialog``."""

	def __init__(self, ui: Any, padre: wx.Window | None, pista: str, marcadores: list[tuple[str, float]],
			borrar: Callable[[int], None]) -> None:
		self._marcadores = list(marcadores)
		self._borrar = borrar
		self.elegido: float | None = None
		self.dialogo = wx.Dialog(padre, title=_("Marcadores de {p}").format(p=pista), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		panel = wx.Panel(self.dialogo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.lista = ui.crear_campo(panel, _("&Marcadores:"), wx.ListBox, choices=self._textos(),
			ayuda=_("Marcadores de esta pista por orden de tiempo. Intro va al elegido."), sizer=sizer)
		self.lista.SetMinSize(panel.FromDIP(wx.Size(380, 200)))
		if self._marcadores:
			self.lista.SetSelection(0)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.ir = wx.Button(panel, wx.ID_OK, _("&Ir al marcador"))
		self.ir.SetHelpText(_("Va al tiempo del marcador elegido y cierra la lista."))
		self.borrar = wx.Button(panel, label=_("&Borrar"))
		self.borrar.SetHelpText(_("Borra el marcador elegido."))
		cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cancelar"))
		cancelar.SetHelpText(_("Cierra la lista sin moverse."))
		for boton in (self.ir, self.borrar, cancelar):
			fila.Add(boton, 0, wx.ALL, 4)
		sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.dialogo.SetSizerAndFit(marco)
		self.ir.SetDefault()
		self.ir.Bind(wx.EVT_BUTTON, self._al_ir)
		self.borrar.Bind(wx.EVT_BUTTON, self._al_borrar)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self._al_ir)
		ui.preparar_dialogo(self.dialogo, foco_inicial=self.lista)
		self._actualizar()

	def _textos(self) -> list[str]:
		return [f"{nombre}, {tiempos.formatear(segundos)}" for nombre, segundos in self._marcadores]

	def _actualizar(self) -> None:
		hay = bool(self._marcadores)
		self.ir.Enable(hay)
		self.borrar.Enable(hay)

	def _al_ir(self, _evento: wx.CommandEvent) -> None:
		indice = self.lista.GetSelection()
		if indice == wx.NOT_FOUND:
			return
		self.elegido = self._marcadores[indice][1]
		self.dialogo.EndModal(wx.ID_OK)

	def _al_borrar(self, _evento: wx.CommandEvent) -> None:
		indice = self.lista.GetSelection()
		if indice == wx.NOT_FOUND:
			return
		self._borrar(indice)
		self._marcadores.pop(indice)
		self.lista.Set(self._textos())
		if self._marcadores:
			self.lista.SetSelection(min(indice, len(self._marcadores) - 1))
		self._actualizar()
		self.lista.SetFocus()
