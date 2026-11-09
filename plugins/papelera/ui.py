# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pregunta de vaciar la papelera (diseño 2.0, 11.20 y 15.1).

Vaciar no se puede deshacer: el foco inicial y el botón predeterminado
(Intro) son «Cancelar», y Escape también cancela.
"""

from __future__ import annotations

import wx

from app.plugins import api

_ = api.traduccion("zc.papelera")[0]

ID_VACIAR = wx.ID_DELETE


class DialogoVaciar(wx.Dialog):
	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, resumen: str, unidad: str = "") -> None:
		titulo = _("Vaciar la papelera de {u}").format(u=unidad) if unidad else _("Vaciar la papelera")
		super().__init__(padre, title=titulo)
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		texto = _("¿Eliminar definitivamente todo lo que hay en la papelera ({r})? No se puede deshacer.").format(r=resumen)
		self.mensaje = wx.StaticText(self, label=texto)
		self.mensaje.Wrap(self.FromDIP(420))
		sizer.Add(self.mensaje, 0, wx.ALL, 10)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_vaciar = wx.Button(self, ID_VACIAR, _("&Vaciar la papelera"))
		self.boton_vaciar.SetHelpText(_("Elimina definitivamente todo lo que hay en la papelera."))
		self.boton_cancelar = wx.Button(self, wx.ID_CANCEL, _("&Cancelar"))
		self.boton_cancelar.SetHelpText(_("Cierra sin vaciar nada."))
		self.boton_cancelar.SetDefault()
		botones.Add(self.boton_vaciar, 0, wx.ALL, 3)
		botones.Add(self.boton_cancelar, 0, wx.ALL, 3)
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(sizer)
		ui.preparar_dialogo(self, foco_inicial=self.boton_cancelar)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(ID_VACIAR), id=ID_VACIAR)

		def al_pulsar(evento: wx.KeyEvent) -> None:
			if evento.GetKeyCode() == wx.WXK_F1 and not evento.HasAnyModifiers():
				try:
					zc.abrir_ayuda()
				except api.NoAdmitido:
					zc.registro.debug("Sin ventana para abrir la ayuda", exc_info=True)
				return
			evento.Skip()

		self.Bind(wx.EVT_CHAR_HOOK, al_pulsar)
