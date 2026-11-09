# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Asistente «Emparejar carpetas (en los dos sentidos)» (diseño 2.0, 12.6; rclone.md 4.3).

``sync/bisync`` es una orden avanzada: la primera vez exige ``resync``; lleva un
umbral de borrados (``maxDelete``, 50 % por defecto) y una forma de resolver los
conflictos. El asistente pide las dos carpetas y esas opciones; antes de hacer
nada se muestra una simulación (``dryRun``) y una comparación de las dos
carpetas, y al final un resumen de los conflictos.
"""

from __future__ import annotations

from typing import Any

import wx

from app.plugins import api

from . import comun

_ = api.traduccion("zc_nubes")[0]

CONFLICTOS = [("none", _("Conservar las dos versiones (se renombran)")), ("newer", _("Gana la más nueva")),
	("older", _("Gana la más antigua")), ("larger", _("Gana la más grande")), ("path1", _("Gana la de la primera carpeta")),
	("path2", _("Gana la de la segunda carpeta"))]


class DialogoEmparejar(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, carpeta1: str = "", carpeta2: str = "") -> None:
		super().__init__(zc, padre, _("Emparejar carpetas en los dos sentidos"))
		comun.texto_solo_lectura(zc, self.panel, _("&Aviso:"), _("Emparejar mantiene las dos carpetas iguales copiando en los dos "
			"sentidos los cambios de cada una, también los borrados. Es una función avanzada: revise la simulación antes de seguir. "
			"La primera vez se hace una sincronización inicial (resync)."), sizer=self.sizer, alto=80)
		self.carpeta1 = comun.campo(zc, self.panel, _("&Primera carpeta:"), wx.TextCtrl, carpeta1, sizer=self.sizer,
			ayuda=_("Normalmente la carpeta local (C:\\...)."))
		self.carpeta2 = comun.campo(zc, self.panel, _("&Segunda carpeta:"), wx.TextCtrl, carpeta2, sizer=self.sizer,
			ayuda=_("Normalmente la de la nube (nube://cuenta/carpeta)."))
		self.conflictos = comun.elegir(zc, self.panel, _("Si un archivo cambió en las &dos:"), CONFLICTOS, "none", sizer=self.sizer,
			ayuda=_("Qué hacer cuando un mismo archivo cambió en las dos carpetas desde la última vez."))
		self.maximo = comun.campo(zc, self.panel, _("Parar si se va a borrar más de este p&orcentaje:"), wx.SpinCtrl, sizer=self.sizer,
			min=1, max=100, initial=50, ayuda=_("Protección: si se fuera a borrar más, no se hace nada."))
		self.inicial = comun.casilla(self.panel, _("Hacer la sincronización &inicial (resync)"),
			_("Necesaria la primera vez o tras un fallo grave; copia lo que falte en cada lado sin borrar nada."), sizer=self.sizer)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		simular = comun.boton(self.panel, _("Si&mular"), _("Muestra lo que se haría, sin cambiar nada."), sizer=fila,
			identificador=wx.ID_OK)
		comun.boton(self.panel, _("&Cancelar"), _("Cierra sin hacer nada."), sizer=fila, identificador=wx.ID_CANCEL)
		simular.SetDefault()
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.terminar(self.carpeta1)

	def datos(self) -> dict[str, Any]:
		return {"carpeta1": self.carpeta1.GetValue().strip(), "carpeta2": self.carpeta2.GetValue().strip(),
			"conflictos": comun.valor_elegido(self.conflictos), "maximo": self.maximo.GetValue(), "inicial": self.inicial.GetValue()}
