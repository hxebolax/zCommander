# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo de crear enlace (sección 8.11).

Por qué está hecho así:

- El tipo se elige en un desplegable y el campo «Explicación» (solo lectura,
  alcanzable con Tab) dice qué es cada tipo y qué pide, incluido si ahora
  mismo falta el permiso para los simbólicos: así la persona decide antes de
  que falle, sin tener que saber de antemano las reglas de Windows.
- El nombre del enlace es una ruta completa (por defecto en la carpeta del
  otro panel); al cambiar a «Acceso directo» se le añade «.lnk» y al salir de
  ese tipo se le quita.
- Se valida al aceptar con ``enlaces.problema``: si algo falla, se dice qué y
  el foco va al campo que hay que corregir con el texto intacto.
"""

from __future__ import annotations

import builtins
import logging
import os

import wx

from app.services.windows import enlaces
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _avisar(padre: wx.Window, mensaje: str, titulo: str) -> None:
	"""Muestra un error (las pruebas la sustituyen: no hay ShowModal real)."""
	dialogos.mostrar_error(padre, mensaje, titulo)


def _elegir_ruta(padre: wx.Window, carpeta: bool, valor: str) -> str | None:
	"""Diálogo nativo para elegir el destino (las pruebas lo sustituyen)."""
	if carpeta:
		dialogo = wx.DirDialog(padre, _("Destino del enlace"), valor, style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
	else:
		dialogo = wx.FileDialog(padre, _("Destino del enlace"), os.path.dirname(valor), os.path.basename(valor),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
	try:
		return dialogo.GetPath() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


class DialogoEnlace(wx.Dialog):
	"""Tipo, destino y nombre del enlace.

	:param destino: a dónde apunta (el elemento del cursor).
	:param enlace: ruta completa propuesta para el enlace.
	"""

	def __init__(self, padre: wx.Window | None, destino: str, enlace: str, tipo: str = enlaces.SIMBOLICO) -> None:
		titulo = _("Crear enlace")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		self.titulo = titulo
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		ancho = panel.FromDIP(wx.Size(460, -1))

		_e, self.lista_tipo = crear_campo(panel, _("&Tipo de enlace:"), wx.Choice,
			choices=[enlaces.nombre_tipo(t) for t in enlaces.TIPOS], sizer=raiz,
			ayuda=_("Simbólico, unión de carpeta, enlace duro o acceso directo. La explicación de abajo dice qué pide cada uno."))
		self.lista_tipo.SetSelection(enlaces.TIPOS.index(tipo) if tipo in enlaces.TIPOS else 0)
		self._tipo_anterior = self.tipo()

		_e, self.campo_destino = crear_campo(panel, _("&Destino (a dónde apunta):"), wx.TextCtrl, value=destino, size=ancho,
			ayuda=_("Archivo o carpeta al que apunta el enlace. Puede ser relativo a la carpeta del enlace."))
		self.boton_examinar = wx.Button(panel, label=_("E&xaminar..."))
		self.boton_examinar.SetHelpText(_("Abre un cuadro para elegir el destino."))
		raiz.Add(_e, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(self.campo_destino, 1, wx.EXPAND | wx.RIGHT, 5)
		fila.Add(self.boton_examinar, 0)
		raiz.Add(fila, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

		_e, self.campo_enlace = crear_campo(panel, _("&Nombre del enlace (ruta completa):"), wx.TextCtrl, value=enlace,
			size=ancho, sizer=raiz, ayuda=_("Dónde se crea el enlace y cómo se llama. Por defecto, en la carpeta del otro panel."))
		_e, self.campo_explicacion = crear_campo(panel, _("&Explicación:"), wx.TextCtrl,
			style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP, size=panel.FromDIP(wx.Size(460, 90)), sizer=raiz,
			ayuda=_("Qué es el tipo elegido y qué necesita."))
		raiz.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(raiz)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)

		self.lista_tipo.Bind(wx.EVT_CHOICE, self._al_cambiar_tipo)
		self.boton_examinar.Bind(wx.EVT_BUTTON, self._al_examinar)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, self._al_aceptar)
		self.ajustar_al_tipo()
		preparar_dialogo(self, foco_inicial=self.lista_tipo)
		self.CentreOnParent()

	def tipo(self) -> str:
		return enlaces.TIPOS[max(0, self.lista_tipo.GetSelection())]

	def destino(self) -> str:
		return self.campo_destino.GetValue().strip()

	def enlace(self) -> str:
		return self.campo_enlace.GetValue().strip()

	def elegir_tipo(self, tipo: str) -> None:
		self.lista_tipo.SetSelection(enlaces.TIPOS.index(tipo))
		self.ajustar_al_tipo()

	def ajustar_al_tipo(self) -> None:
		"""Explicación del tipo y «.lnk» en el nombre solo para los accesos directos."""
		tipo = self.tipo()
		self.campo_explicacion.ChangeValue(enlaces.explicacion(tipo))
		enlace = self.enlace()
		if tipo == enlaces.ACCESO_DIRECTO and enlace and not enlace.lower().endswith(".lnk"):
			self.campo_enlace.ChangeValue(enlace + ".lnk")
		elif tipo != enlaces.ACCESO_DIRECTO and self._tipo_anterior == enlaces.ACCESO_DIRECTO and enlace.lower().endswith(".lnk"):
			self.campo_enlace.ChangeValue(enlace[:-4])
		self._tipo_anterior = tipo

	def _al_cambiar_tipo(self, evento: wx.CommandEvent) -> None:
		evento.Skip()
		self.ajustar_al_tipo()

	def _al_examinar(self, _evento: wx.CommandEvent) -> None:
		carpeta = self.tipo() == enlaces.UNION or os.path.isdir(self.destino())
		ruta = _elegir_ruta(self, carpeta, self.destino())
		if ruta:
			self.campo_destino.SetValue(ruta)
		self.campo_destino.SetFocus()

	def aceptar(self) -> bool:
		motivo = enlaces.problema(self.tipo(), self.enlace(), self.destino())
		if motivo:
			_avisar(self, motivo, self.titulo)
			# Los motivos que hablan del destino o de a qué apunta se corrigen en el campo Destino.
			sobre_destino = not self.destino() or "destino" in motivo.lower() or "apuntar" in motivo.lower()
			campo = self.campo_destino if sobre_destino else self.campo_enlace
			campo.SetFocus()
			campo.SelectAll()
			return False
		_terminar(self, wx.ID_OK)
		return True

	def _al_aceptar(self, _evento: wx.CommandEvent) -> None:
		self.aceptar()


def pedir_enlace(padre: wx.Window | None, destino: str, enlace: str, tipo: str = enlaces.SIMBOLICO) -> tuple[str, str, str] | None:
	"""(tipo, enlace, destino) aceptados, o ``None`` si se cancela."""
	dialogo = DialogoEnlace(padre, destino, enlace, tipo)
	foco_previo = wx.Window.FindFocus()
	try:
		return (dialogo.tipo(), dialogo.enlace(), dialogo.destino()) if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()
		if foco_previo:
			foco_previo.SetFocus()
