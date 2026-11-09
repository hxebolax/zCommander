# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pedir usuario y contraseña de un servidor (diseño 2.0, 9.4). Bloque RD.

Lo usa ``GestorDecisiones.pedir_credenciales`` (desde un hilo, a través de la
cola de decisiones, sin que este módulo lo sepa) y lo llaman directamente las
órdenes de red en el hilo de la interfaz con ``pedir``.

- El motivo (por qué se piden: «Usuario o contraseña incorrectos», el error
  1272 de invitado bloqueado...) va en un campo de solo lectura con su
  etiqueta, para que el lector lo pueda releer con las flechas.
- «Recordar la contraseña en Windows» la guarda el Administrador de
  credenciales de Windows, no zCommander: la contraseña nunca se escribe en
  ``data/`` ni en el registro.
- Suena ``red.credenciales`` al abrirse (también se dice el título).

Letras: M (mensaje), U, O, R, A (Aceptar) y C (Cancelar).
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _sonar() -> None:
	try:
		from app.services.sonidos import servicio

		servicio.sonar("red.credenciales")
	except Exception:  # noqa: BLE001 - sin sonido el diálogo sigue
		log.debug("No sonó red.credenciales", exc_info=True)


class DialogoCredenciales(wx.Dialog):
	"""Usuario, contraseña y «Recordar»; cada etiqueta creada justo antes de su control."""

	def __init__(self, padre: wx.Window | None, titulo: str, texto: str, usuario: str = "") -> None:
		titulo = titulo or _("Credenciales")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE, name=titulo)
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		ancho = panel.FromDIP(wx.Size(360, -1))
		self.mensaje: wx.TextCtrl | None = None
		if texto:
			_e, self.mensaje = crear_campo(panel, _("&Mensaje:"), wx.TextCtrl, value=texto,
				style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP, size=panel.FromDIP(wx.Size(420, 90)),
				ayuda=_("Por qué se piden las credenciales. Puede releerlo con las flechas."), sizer=sizer)
		_e, self.usuario = crear_campo(panel, _("&Usuario:"), wx.TextCtrl, value=usuario, size=ancho,
			ayuda=_("Usuario del servidor, por ejemplo SERVIDOR\\ana, DOMINIO\\ana o ana@dominio. "
				"Vacío, se usa la cuenta con la que inició sesión en Windows."), sizer=sizer)
		_e, self.contrasena = crear_campo(panel, _("C&ontraseña:"), wx.TextCtrl, style=wx.TE_PASSWORD, size=ancho,
			ayuda=_("Contraseña de ese usuario. zCommander no la guarda: se la pasa a Windows."), sizer=sizer)
		self.recordar = wx.CheckBox(panel, label=_("&Recordar la contraseña en Windows"))
		self.recordar.SetHelpText(_("La guarda el Administrador de credenciales de Windows (no zCommander), "
			"que la usará al volver a conectar. Se borra con Contraseñas guardadas de servidores."))
		sizer.Add(self.recordar, 0, wx.ALL, 8)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		preparar_dialogo(self, foco_inicial=self.contrasena if usuario else self.usuario)
		self.CentreOnParent()
		_sonar()

	def valores(self) -> tuple[str, str, bool]:
		"""(usuario, contraseña, recordar). «Recordar» sin contraseña no tiene sentido y se da como falso."""
		contrasena = self.contrasena.GetValue()
		return self.usuario.GetValue().strip(), contrasena, bool(self.recordar.GetValue()) and bool(contrasena)


def pedir(padre: wx.Window | None, titulo: str, texto: str, usuario: str) -> tuple[str, str, bool] | None:
	"""(usuario, contraseña, recordar), o ``None`` si se cancela. Solo en el hilo de la interfaz."""
	foco = wx.Window.FindFocus()
	dialogo = DialogoCredenciales(padre, titulo, texto, usuario)
	try:
		return dialogo.valores() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()
		if foco:
			try:
				foco.SetFocus()
			except RuntimeError:
				log.debug("El control que tenía el foco ya no existe", exc_info=True)
