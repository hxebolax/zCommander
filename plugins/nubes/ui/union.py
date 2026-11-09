# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Unir varias cuentas en una unidad (diseño 2.0, 12.6; rclone.md 4.11).

- ``union``: mezcla las cuentas en una sola vista; los archivos nuevos van a la
  cuenta con más espacio libre (política ``mfs``) y el espacio es la suma.
- ``combine``: una carpeta por cuenta dentro de una sola unidad, cómoda para
  buscar en todas a la vez.
"""

from __future__ import annotations

from typing import Any

import wx

from app.plugins import api

from . import comun

_ = api.traduccion("zc_nubes")[0]

TIPOS = [("union", _("Mezclar en una sola vista (unión)")), ("combine", _("Una carpeta por cuenta (combinar)"))]
POLITICAS = [("mfs", _("La cuenta con más espacio libre")), ("lus", _("La cuenta menos usada")),
	("epmfs", _("La de más espacio libre que ya tenga la carpeta")), ("ff", _("La primera de la lista"))]


class DialogoUnion(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, cuentas: list[tuple[str, str]]) -> None:
		super().__init__(zc, padre, _("Unir varias cuentas en una unidad"))
		self.ids = [i for i, _n in cuentas]
		self.nombre = comun.campo(zc, self.panel, _("&Nombre visible:"), wx.TextCtrl, _("Todas mis nubes"), sizer=self.sizer,
			ayuda=_("Cómo se verá la unidad nueva en el selector."))
		self.tipo = comun.elegir(zc, self.panel, _("&Forma de unir:"), TIPOS, "union", sizer=self.sizer,
			ayuda=_("Mezclar suma el espacio de todas; combinar pone cada cuenta en su carpeta."))
		texto = wx.StaticText(self.panel, label=_("C&uentas que se unen:"))
		modulo = comun.ui(zc)
		nombres = [n for _i, n in cuentas]
		if modulo is not None:
			self.cuentas = modulo.CheckListBoxAccesible(self.panel, _("Cuentas que se unen"), nombres)
		else:
			self.cuentas = wx.CheckListBox(self.panel, choices=nombres, name=_("Cuentas que se unen"))
		self.cuentas.SetHelpText(_("Marque con Espacio las cuentas que formarán la unidad (al menos dos)."))
		self.sizer.Add(texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.sizer.Add(self.cuentas, 1, wx.EXPAND | wx.ALL, 5)
		self.politica = comun.elegir(zc, self.panel, _("&Dónde se guardan los archivos nuevos:"), POLITICAS, "mfs", sizer=self.sizer,
			ayuda=_("Solo para la unión: en qué cuenta se crea cada archivo nuevo."))
		self.botones(wx.OK | wx.CANCEL)
		self.Bind(wx.EVT_BUTTON, self._aceptar, id=wx.ID_OK)
		self.terminar(self.nombre)

	def elegidas(self) -> list[str]:
		return [self.ids[i] for i in range(self.cuentas.GetCount()) if self.cuentas.IsChecked(i)]

	def _aceptar(self, evento: wx.CommandEvent) -> None:
		if len(self.elegidas()) < 2 or not self.nombre.GetValue().strip():
			comun.error(self.zc, _("Escriba un nombre y marque al menos dos cuentas."))
			return
		evento.Skip()

	def datos(self) -> dict[str, Any]:
		return {"nombre": self.nombre.GetValue().strip(), "tipo": comun.valor_elegido(self.tipo), "cuentas": self.elegidas(),
			"politica": comun.valor_elegido(self.politica)}
