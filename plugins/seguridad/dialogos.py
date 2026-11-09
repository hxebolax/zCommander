# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Configuración avanzada de ``zc.seguridad``: la clave de VirusTotal (diseño 2.0, 11.19). Con wx.

La clave es un secreto: se guarda con ``zc.secretos`` (``secretos.dat``,
cifrado con DPAPI), nunca en la configuración JSON. El campo nunca muestra la
clave guardada: solo dice si hay una.
"""

from __future__ import annotations

import wx

from app.plugins import api

_, _n = api.traduccion("zc_seguridad")

ID_OLVIDAR = wx.NewIdRef()


class DialogoClave(wx.Dialog):
	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, estado: str) -> None:
		super().__init__(padre, title=_("Clave de VirusTotal"))
		ui = zc.ui
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		_e, self.estado = ui.crear_campo(panel, _("&Estado:"), wx.TextCtrl, value=estado, style=wx.TE_READONLY, sizer=raiz,
			ayuda=_("Dice si ya hay una clave guardada."))
		_e, self.clave = ui.crear_campo(panel, _("&Nueva clave de la API de VirusTotal:"), wx.TextCtrl, style=wx.TE_PASSWORD,
			sizer=raiz, ayuda=_("Su clave personal (en su perfil de virustotal.com, «API key»). Déjelo vacío para no cambiarla."))
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.guardar = wx.Button(panel, wx.ID_OK, _("&Guardar"))
		self.olvidar = wx.Button(panel, ID_OLVIDAR, _("&Olvidar la clave guardada"))
		self.olvidar.SetHelpText(_("Borra la clave de este equipo; la próxima búsqueda la volverá a pedir."))
		cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cancelar"))
		for boton in (self.guardar, self.olvidar, cancelar):
			botones.Add(boton, 0, wx.ALL, 5)
		self.guardar.SetDefault()
		raiz.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		panel.SetSizer(raiz)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		ui.preparar_dialogo(self, foco_inicial=self.clave)
		self.olvidar.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(ID_OLVIDAR) if self.IsModal() else None)


def configurar_clave(zc: api.Anfitrion, padre: wx.Window | None, nombre: str) -> None:
	estado = _("Hay una clave guardada") if zc.secretos.obtener(nombre) else _("No hay ninguna clave guardada")
	dialogo = DialogoClave(padre, zc, estado)
	try:
		respuesta = zc.ui.mostrar_modal(dialogo)
		nueva = dialogo.clave.GetValue().strip()
	finally:
		dialogo.Destroy()
	if respuesta == ID_OLVIDAR:
		zc.secretos.borrar(nombre)
		zc.anunciar(_("Clave de VirusTotal olvidada"), api.RESULTADO)
	elif respuesta == wx.ID_OK and nueva:
		zc.secretos.guardar(nombre, nueva)
		zc.anunciar(_("Clave de VirusTotal guardada"), api.RESULTADO)
