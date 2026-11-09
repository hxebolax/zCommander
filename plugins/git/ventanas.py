# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de ``zc.git``: confirmar con mensaje e historial en una lista (diseño 2.0, 11.21). Con wx."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

import wx

from app.plugins import api

from . import lector

_, _n = api.traduccion("zc_git")

COLUMNAS_HISTORIAL = ((_("Fecha"), 150), (_("Autor"), 160), (_("Mensaje"), 420), (_("Identificador"), 100))


class DialogoConfirmar(wx.Dialog):
	"""Mensaje de la confirmación y, en solo lectura, la lista de lo que se confirma."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, rama: str, cambios: Sequence[str]) -> None:
		super().__init__(padre, title=_("Confirmar en la rama {r}").format(r=rama) if rama else _("Confirmar"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		ui = zc.ui
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		_e, self.mensaje = ui.crear_campo(panel, _("&Mensaje de la confirmación:"), wx.TextCtrl, style=wx.TE_MULTILINE,
			size=wx.Size(480, 120), sizer=raiz, ayuda=_("Qué cambia y por qué. La primera línea es el resumen."))
		_e, self.cambios = ui.crear_campo(panel, _("&Lo que se confirma:"), wx.TextCtrl, value="\n".join(cambios),
			style=wx.TE_MULTILINE | wx.TE_READONLY, size=wx.Size(480, 120), sizer=raiz,
			ayuda=_("Los archivos preparados con su estado."))
		raiz.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(raiz)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		ui.preparar_dialogo(self, foco_inicial=self.mensaje)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		if not self.mensaje.GetValue().strip():
			self.zc.ui.mostrar_error(_("Escriba un mensaje para la confirmación"), _("Confirmar"), self)
			self.mensaje.SetFocus()
			return
		evento.Skip()


def fecha(confirmacion: lector.Confirmacion) -> str:
	return time.strftime("%d/%m/%Y %H:%M", time.localtime(confirmacion.fecha)) if confirmacion.fecha else ""


class DialogoHistorial(wx.Dialog):
	"""Historial de un archivo o carpeta; Intro muestra los cambios de la confirmación elegida."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, titulo: str, confirmaciones: Sequence[lector.Confirmacion],
			al_ver: Callable[[lector.Confirmacion], None] | None = None) -> None:
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, size=wx.Size(860, 460))
		self.zc = zc
		self.confirmaciones = list(confirmaciones)
		self._al_ver = al_ver
		ui = zc.ui
		raiz = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label=_("&Historial:"))
		self.lista = ui.ListaAccesible(self, _("Historial"), COLUMNAS_HISTORIAL)
		self.lista.SetHelpText(_("Confirmaciones, de la más reciente a la más antigua. Intro muestra sus cambios."))
		raiz.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_ver = wx.Button(self, label=_("&Ver los cambios"))
		self.boton_ver.SetHelpText(_("Muestra el mensaje completo y los cambios de la confirmación elegida (Intro)."))
		self.boton_copiar = wx.Button(self, label=_("C&opiar el identificador"))
		self.boton_copiar.SetHelpText(_("Copia al portapapeles el identificador completo de la confirmación."))
		cerrar = wx.Button(self, wx.ID_CANCEL, _("C&errar"))
		for boton in (self.boton_ver, self.boton_copiar, cerrar):
			botones.Add(boton, 0, wx.ALL, 5)
		raiz.Add(botones, 0, wx.ALIGN_RIGHT)
		self.SetSizer(raiz)
		self.lista.reemplazar_filas([[fecha(c), c.autor, c.resumen, c.sha[:10]] for c in self.confirmaciones], conservar_foco=False)
		ui.preparar_dialogo(self, foco_inicial=self.lista)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.ver())
		self.boton_ver.Bind(wx.EVT_BUTTON, lambda _e: self.ver())
		self.boton_copiar.Bind(wx.EVT_BUTTON, lambda _e: self.copiar())
		hay = bool(self.confirmaciones)
		self.boton_ver.Enable(hay and al_ver is not None)
		self.boton_copiar.Enable(hay)

	def elegida(self) -> lector.Confirmacion | None:
		fila = self.lista.fila_actual() if self.lista.numero_filas() else -1
		return self.confirmaciones[fila] if 0 <= fila < len(self.confirmaciones) else None

	def ver(self) -> None:
		confirmacion = self.elegida()
		if confirmacion is not None and self._al_ver is not None:
			self._al_ver(confirmacion)

	def copiar(self) -> None:
		confirmacion = self.elegida()
		if confirmacion is None:
			return
		if wx.TheClipboard.Open():
			try:
				wx.TheClipboard.SetData(wx.TextDataObject(confirmacion.sha))
			finally:
				wx.TheClipboard.Close()
			self.zc.anunciar(_("Identificador copiado"), api.RESULTADO)
