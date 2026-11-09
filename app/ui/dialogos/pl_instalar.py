# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Resumen de un paquete ``.zcplugin`` antes de instalarlo (diseño 2.0, 3.9, 3.10 y 15.1). Bloque PL.

- Todo el resumen (nombre, versión, autor, licencia, confianza, procedencia,
  permisos, dependencias, componentes, archivos y tamaño) va en un campo de
  solo lectura: el lector lo recorre por líneas y se puede copiar.
- Botones «&Instalar» y «&Cancelar». Sin firma, el predeterminado es
  «&Cancelar» (Intro no instala por descuido) y el aviso de 3.9 encabeza los
  avisos. Si el paquete no se puede instalar, solo hay «&Cerrar».
- El foco empieza en el resumen: lo primero que oye la persona es qué va a instalar.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

import wx

from app.plugins import estado
from app.ui.accesibilidad.dialogos import devolver_foco, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoInstalar(wx.Dialog):
	"""``ShowModal`` devuelve ``wx.ID_OK`` si la persona pulsa «Instalar»."""

	def __init__(self, padre: wx.Window | None, resumen: Any) -> None:
		titulo = _("Instalar un complemento")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.resumen = resumen
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.texto = crear_campo(panel, _("&Resumen del complemento:"), wx.TextCtrl, value=resumen.texto(),
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=panel.FromDIP(wx.Size(560, 360)), sizer=sizer,
			ayuda=_("Qué se va a instalar: autor, licencia, confianza, permisos y archivos. Recórralo con las flechas."))
		botones = wx.BoxSizer(wx.HORIZONTAL)
		if resumen.instalable:
			self.boton_instalar = wx.Button(panel, wx.ID_OK, _("&Instalar"))
			self.boton_instalar.SetHelpText(_("Instala el complemento con lo que dice el resumen."))
			self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cancelar"))
			self.boton_cancelar.SetHelpText(_("No instala nada."))
			botones.Add(self.boton_instalar, 0, wx.RIGHT, 6)
			botones.Add(self.boton_cancelar, 0)
			(self.boton_cancelar if resumen.sin_firma else self.boton_instalar).SetDefault()
		else:
			self.boton_instalar = None
			self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cerrar"))
			self.boton_cancelar.SetHelpText(_("Cierra sin instalar: el paquete no se puede instalar."))
			botones.Add(self.boton_cancelar, 0)
			self.boton_cancelar.SetDefault()
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		preparar_dialogo(self, foco_inicial=self.texto)
		self.CentreOnParent()


def confirmar_instalacion(padre: wx.Window | None, resumen: Any) -> bool:
	"""Muestra el resumen; verdadero si la persona elige «Instalar» (las pruebas sustituyen esta función)."""
	dialogo = DialogoInstalar(padre, resumen)
	foco = wx.Window.FindFocus()
	try:
		with estado.pausa_modal():
			return dialogo.ShowModal() == wx.ID_OK and resumen.instalable
	finally:
		dialogo.Destroy()
		devolver_foco(foco)
