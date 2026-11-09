# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Cifrar» con contraseña, confirmación y medidor de fortaleza en texto (diseño 2.0, 11.13). Con wx.

El medidor es un campo de solo lectura con su etiqueta («Fortaleza:»): el
lector lo lee al llegar a él con Tab y no se anuncia solo a cada tecla, para
no interrumpir mientras se escribe la contraseña.
"""

from __future__ import annotations

from dataclasses import dataclass

import wx

from app.plugins import api

from . import zcc

_, _n = api.traduccion("zc_cifrado")

FORMATOS = (("zcc", _("Archivo .zcc de zCommander (AES-256-GCM)")), ("7z", _("7z con AES-256, compatible con 7-Zip")))


@dataclass(frozen=True)
class OpcionesCifrado:
	contrasena: str
	formato: str
	borrar_originales: bool


class DialogoCifrar(wx.Dialog):
	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, que: str) -> None:
		super().__init__(padre, title=_("Cifrar {q}").format(q=que), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		ui = zc.ui
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		aviso = wx.StaticText(panel, label=_("Si pierde la contraseña, no hay forma de recuperar lo cifrado: ni zCommander ni nadie "
			"puede hacerlo. Guárdela en un lugar seguro."))
		aviso.Wrap(460)
		raiz.Add(aviso, 0, wx.ALL, 5)
		_e, self.contrasena = ui.crear_campo(panel, _("Contra&seña:"), wx.TextCtrl, style=wx.TE_PASSWORD, sizer=raiz,
			ayuda=_("La contraseña con la que se cifra. Cuanto más larga, mejor: una frase de varias palabras es fácil de recordar."))
		_e, self.repetida = ui.crear_campo(panel, _("&Repita la contraseña:"), wx.TextCtrl, style=wx.TE_PASSWORD, sizer=raiz,
			ayuda=_("Escriba otra vez la misma contraseña para comprobar que no hay errores."))
		_e, self.medidor = ui.crear_campo(panel, _("&Fortaleza:"), wx.TextCtrl, style=wx.TE_READONLY, sizer=raiz,
			value=zcc.fortaleza("")[1], ayuda=_("Qué tan difícil sería adivinar la contraseña."))
		_e, self.formato = ui.crear_campo(panel, _("Forma&to:"), wx.Choice, choices=[t for _c, t in FORMATOS], sizer=raiz,
			ayuda=_("El .zcc solo lo abre zCommander; el 7z lo abre también 7-Zip (solo en el disco)."))
		valor = str(zc.config.obtener("formato", "zcc"))
		self.formato.SetSelection(next((i for i, (c, _t) in enumerate(FORMATOS) if c == valor), 0))
		self.borrar = wx.CheckBox(panel, label=_("&Enviar los originales a la papelera tras comprobar el cifrado"))
		self.borrar.SetValue(bool(zc.config.obtener("borrar_originales", False)))
		self.borrar.SetHelpText(_("Después de comprobar que lo cifrado se puede descifrar, los originales van a la papelera "
			"(no se borran de forma segura)."))
		raiz.Add(self.borrar, 0, wx.ALL, 5)
		raiz.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(raiz)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		ui.preparar_dialogo(self, foco_inicial=self.contrasena)
		self.contrasena.Bind(wx.EVT_TEXT, self._al_escribir)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)

	def _al_escribir(self, _evento: wx.CommandEvent) -> None:
		self.medidor.ChangeValue(zcc.fortaleza(self.contrasena.GetValue())[1])

	def problema(self) -> str:
		"""Lo que impide aceptar, o ``""``."""
		if not self.contrasena.GetValue():
			return _("Escriba una contraseña")
		if self.contrasena.GetValue() != self.repetida.GetValue():
			return _("Las dos contraseñas no coinciden")
		return ""

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		problema = self.problema()
		if problema:
			self.zc.ui.mostrar_error(problema, _("Cifrar"), self)
			(self.contrasena if not self.contrasena.GetValue() else self.repetida).SetFocus()
			return
		evento.Skip()

	def opciones(self) -> OpcionesCifrado:
		return OpcionesCifrado(self.contrasena.GetValue(), FORMATOS[max(0, self.formato.GetSelection())][0], self.borrar.GetValue())


def pedir_opciones(zc: api.Anfitrion, que: str) -> OpcionesCifrado | None:
	dialogo = DialogoCifrar(None, zc, que)
	try:
		if zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
			return None
		return dialogo.opciones()
	finally:
		dialogo.Destroy()
