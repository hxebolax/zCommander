# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pedir un nombre (renombrar, crear carpeta, duplicar) o un patrón (marcar, filtrar).

Por qué no basta con ``dialogos.pedir_texto``:

- El nombre se valida ANTES de cerrar: si no vale («CON», «a:b», acaba en
  punto), se dice qué falla y el foco vuelve al campo con el texto intacto,
  para corregirlo sin tener que volver a escribirlo todo ni volver a abrir la
  orden.
- Al renombrar se selecciona el nombre sin la extensión (sección 8.8): lo
  habitual es cambiar el nombre y conservar el tipo de archivo.
- El patrón se elige de un historial en un desplegable editable.

La validación está separada en funciones puras (``validar_nombre``,
``rango_sin_extension``) para poder probarla sin mostrar el diálogo.
"""

from __future__ import annotations

import builtins
import logging
import re
from collections.abc import Sequence

import wx

from app.services.vfs import rutas
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import crear_botonera, devolver_foco, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def validar_nombre(texto: str, permitir_ruta: bool = False) -> str | None:
	"""Motivo por el que ``texto`` no vale como nombre, o ``None`` si vale.

	:param permitir_ruta: admite varios niveles («a\\b\\c», crear carpeta).
	"""
	if permitir_ruta:
		return rutas.problema_en_ruta_relativa(texto)
	return rutas.problema_en_nombre(texto)


def rango_sin_extension(texto: str) -> tuple[int, int]:
	"""(desde, hasta) del nombre sin extensión del último componente.

	«informe.final.docx» → hasta antes de «.docx»; «.gitignore» y las carpetas
	sin punto, entero. Con ruta («a\\b.txt») solo se selecciona «b».
	"""
	inicio = max(texto.rfind("\\"), texto.rfind("/")) + 1
	punto = texto.rfind(".")
	if punto > inicio:
		return inicio, punto
	return inicio, len(texto)


def _avisar(padre: wx.Window, mensaje: str, titulo: str) -> None:
	"""Muestra el motivo del rechazo (las pruebas la sustituyen: no hay ShowModal real)."""
	dialogos.mostrar_error(padre, mensaje, titulo)


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


class DialogoNombre(wx.Dialog):
	"""Campo de nombre con validación al aceptar. ``ShowModal`` devuelve ``wx.ID_OK`` solo con un nombre válido."""

	def __init__(self, padre: wx.Window | None, titulo: str, etiqueta: str, valor: str = "",
			seleccionar_sin_extension: bool = True, permitir_ruta: bool = False,
			opciones: Sequence[str] = (), etiqueta_opciones: str = "", ayuda_opciones: str = "") -> None:
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE, name=titulo)
		self.titulo = titulo
		self.permitir_ruta = permitir_ruta
		self.seleccionar_sin_extension = seleccionar_sin_extension
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		ayuda = _("Puede escribir varios niveles separados por barras invertidas.") if permitir_ruta else \
			_("Sin los caracteres \\ / : * ? \" < > | y sin terminar en punto ni en espacio.")
		_etiqueta, self.campo = crear_campo(panel, etiqueta, wx.TextCtrl, value=valor, size=panel.FromDIP(wx.Size(420, -1)),
			ayuda=ayuda, sizer=sizer)
		#: 2.0 (10.13): lista opcional bajo el nombre (las plantillas de Mayús+F4); ``None`` sin ella.
		self.lista_opciones: wx.Choice | None = None
		if opciones:
			_etiqueta_opciones, self.lista_opciones = crear_campo(panel, etiqueta_opciones, wx.Choice, choices=list(opciones),
				ayuda=ayuda_opciones, sizer=sizer)
			self.lista_opciones.SetSelection(0)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, self._al_aceptar)
		# El foco lo pone _al_iniciar (con la selección sin extensión): preparar_dialogo lo seleccionaría todo.
		preparar_dialogo(self, foco_inicial=None)
		self.Bind(wx.EVT_INIT_DIALOG, self._al_iniciar)
		self.CentreOnParent()

	def valor(self) -> str:
		return self.campo.GetValue()

	def opcion(self) -> int:
		"""Índice elegido en la lista de opciones (0 si no hay lista)."""
		return max(0, self.lista_opciones.GetSelection()) if self.lista_opciones is not None else 0

	def comprobar(self) -> str | None:
		return validar_nombre(self.valor(), self.permitir_ruta)

	def seleccionar(self) -> None:
		"""Foco en el campo con el nombre sin extensión (o todo) seleccionado."""
		self.campo.SetFocus()
		if self.seleccionar_sin_extension:
			desde, hasta = rango_sin_extension(self.valor())
			self.campo.SetSelection(desde, hasta)
		else:
			self.campo.SelectAll()

	def aceptar(self) -> bool:
		"""Cierra con Aceptar si el nombre vale; si no, dice por qué y devuelve el foco al campo."""
		problema = self.comprobar()
		if problema:
			_avisar(self, problema, self.titulo)
			self.campo.SetFocus()
			self.campo.SelectAll()
			return False
		_terminar(self, wx.ID_OK)
		return True

	def _al_aceptar(self, _evento: wx.CommandEvent) -> None:
		self.aceptar()

	def _al_iniciar(self, evento: wx.InitDialogEvent) -> None:
		wx.CallAfter(self.seleccionar)
		evento.Skip()


def pedir_nombre(padre: wx.Window | None, titulo: str, etiqueta: str, valor: str,
		seleccionar_sin_extension: bool = True, permitir_ruta: bool = False, *,
		opciones: Sequence[str] = (), etiqueta_opciones: str = "", ayuda_opciones: str = "",
		eleccion: list[int] | None = None) -> str | None:
	"""Nombre válido escrito por la persona, o ``None`` si cancela.

	Con ``opciones`` (2.0, 10.13), el diálogo añade una lista tras el nombre y deja el índice
	elegido en ``eleccion[0]`` (la firma y la respuesta de la 1.x no cambian).
	"""
	dialogo = DialogoNombre(padre, titulo, etiqueta, valor, seleccionar_sin_extension, permitir_ruta,
		opciones, etiqueta_opciones, ayuda_opciones)
	foco_previo = wx.Window.FindFocus()
	try:
		if dialogo.ShowModal() != wx.ID_OK:
			return None
		if eleccion is not None:
			eleccion[:] = [dialogo.opcion()]
		return dialogo.valor()
	finally:
		dialogo.Destroy()
		devolver_foco(foco_previo)


class DialogoPatron(wx.Dialog):
	"""Desplegable editable con el historial de patrones («*.txt;*.md», «foto*»)."""

	def __init__(self, padre: wx.Window | None, titulo: str, etiqueta: str, historial: Sequence[str]) -> None:
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE, name=titulo)
		self.titulo = titulo
		elementos = [h for h in historial if h]
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.campo = crear_campo(
			panel, etiqueta, wx.ComboBox, value=elementos[0] if elementos else "*", choices=elementos,
			style=wx.CB_DROPDOWN, size=panel.FromDIP(wx.Size(360, -1)),
			ayuda=_("Patrón con * y ?; varios separados por punto y coma. Flecha abajo recorre los anteriores."),
			sizer=sizer)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, self._al_aceptar)
		preparar_dialogo(self, foco_inicial=self.campo)
		self.Bind(wx.EVT_INIT_DIALOG, self._al_iniciar)
		self.CentreOnParent()

	def valor(self) -> str:
		return self.campo.GetValue().strip()

	def aceptar(self) -> bool:
		if not self.valor() or not re.sub(r"[;\s]", "", self.valor()):
			_avisar(self, _("Escriba un patrón, por ejemplo *.txt"), self.titulo)
			self.campo.SetFocus()
			return False
		_terminar(self, wx.ID_OK)
		return True

	def _al_aceptar(self, _evento: wx.CommandEvent) -> None:
		self.aceptar()

	def _al_iniciar(self, evento: wx.InitDialogEvent) -> None:
		# Todo seleccionado para escribir encima del último patrón.
		wx.CallAfter(self.campo.SelectAll)
		evento.Skip()


def pedir_patron(padre: wx.Window | None, titulo: str, etiqueta: str, historial: list[str]) -> str | None:
	"""Patrón escrito o elegido del historial, o ``None`` si se cancela. No modifica ``historial``."""
	dialogo = DialogoPatron(padre, titulo, etiqueta, historial)
	foco_previo = wx.Window.FindFocus()
	try:
		return dialogo.valor() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()
		devolver_foco(foco_previo)
