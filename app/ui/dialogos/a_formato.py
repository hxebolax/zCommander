# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de formato del visor y del editor (bloque A): codificación y «Guardar como».

Por qué están hechos así:

- La codificación se elige en una lista nativa (``wx.ListBox``) con su
  etiqueta: el lector dice el nombre completo de cada una («OEM 850 (MS-DOS
  Europa)») y la elegida queda seleccionada al abrir.
- «Guardar como» reúne en un solo diálogo la ruta, la codificación, el fin de
  línea y el BOM, porque la persona decide las cuatro cosas a la vez (sección
  8.3: «se pueden cambiar al guardar como»). La ruta se escribe o se elige
  con «Examinar...» (cuadro de Windows); se valida al aceptar (carpeta que
  existe, nombre válido) y, si el archivo ya existe, se pregunta antes.
"""

from __future__ import annotations

import builtins
import logging
import os

import wx

from app.services import codificacion
from app.services.vfs import rutas
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)

#: (valor, nombre para la persona) de los fines de línea.
FINES_DE_LINEA: tuple[tuple[str, str], ...] = (
	("\r\n", "CRLF (Windows)"),
	("\n", "LF (Unix, Linux y macOS)"),
	("\r", "CR (Mac antiguo)"),
)
NOMBRE_FIN_DE_LINEA = {valor: nombre for valor, nombre in FINES_DE_LINEA}
AUTOMATICA = "automatica"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


def _marco(dialogo: wx.Dialog, panel: wx.Panel) -> None:
	marco = wx.BoxSizer(wx.VERTICAL)
	marco.Add(panel, 1, wx.EXPAND)
	dialogo.SetSizerAndFit(marco)


# ── Codificación ─────────────────────────────────────────────────────────────


class DialogoCodificacion(wx.Dialog):
	"""Elegir la codificación con la que se lee el archivo (F8 en el visor).

	:param actual: valor de ``codificacion.CODIFICACIONES`` o «automatica».
	:param con_automatica: incluye «Automática (detectar)» como primera opción.
	"""

	def __init__(self, padre: wx.Window | None, actual: str, con_automatica: bool = True) -> None:
		titulo = _("Codificación")
		super().__init__(padre, title=titulo, name=titulo)
		self.valores = ([AUTOMATICA] if con_automatica else []) + [valor for valor, _n, _c in codificacion.CODIFICACIONES]
		nombres = ([_("Automática (detectar)")] if con_automatica else []) + [nombre for _v, nombre, _c in codificacion.CODIFICACIONES]
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.lista = crear_campo(panel, _("C&odificación:"), wx.ListBox, choices=nombres, style=wx.LB_SINGLE,
			size=panel.FromDIP(wx.Size(300, 160)), ayuda=_("Cómo se convierten los bytes del archivo en letras. Intro acepta."),
			sizer=sizer)
		self.lista.SetSelection(self.valores.index(actual) if actual in self.valores else 0)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: _terminar(self, wx.ID_OK))
		sizer.Add(dialogos.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(sizer)
		_marco(self, panel)
		dialogos.preparar_dialogo(self, foco_inicial=self.lista)
		self.CentreOnParent()

	def valor(self) -> str:
		indice = self.lista.GetSelection()
		return self.valores[indice] if indice != wx.NOT_FOUND else AUTOMATICA


def pedir_codificacion(padre: wx.Window, actual: str, con_automatica: bool = True) -> str | None:
	dialogo = DialogoCodificacion(padre, actual, con_automatica)
	try:
		return dialogo.valor() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


# ── Guardar como ─────────────────────────────────────────────────────────────


class DialogoGuardarComo(wx.Dialog):
	"""Ruta, codificación, fin de línea y BOM con que se guarda el texto del editor (Mayús+F2).

	Siempre guarda en el disco (o en una ruta de red de Windows): es el camino
	para sacar una copia editada de un comprimido.
	"""

	def __init__(self, padre: wx.Window | None, ruta: str, cod: str, fin_de_linea: str, bom: bool) -> None:
		titulo = _("Guardar como")
		super().__init__(padre, title=titulo, name=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		columna = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.campo_ruta = crear_campo(panel, _("&Ruta del archivo:"), wx.TextCtrl, value=ruta,
			size=panel.FromDIP(wx.Size(420, -1)), ayuda=_("Ruta completa del archivo que se va a guardar."), sizer=columna)
		fila.Add(columna, 1, wx.EXPAND)
		self.boton_examinar = wx.Button(panel, label=_("E&xaminar..."))
		self.boton_examinar.SetHelpText(_("Abre el cuadro de Windows para elegir la carpeta y el nombre."))
		self.boton_examinar.Bind(wx.EVT_BUTTON, self._al_examinar)
		fila.Add(self.boton_examinar, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)
		sizer.Add(fila, 0, wx.EXPAND)
		self.valores_cod = [valor for valor, _n, _c in codificacion.CODIFICACIONES]
		_etiqueta, self.lista_cod = crear_campo(panel, _("C&odificación:"), wx.Choice,
			choices=[nombre for _v, nombre, _c in codificacion.CODIFICACIONES],
			ayuda=_("Codificación con que se escribe el texto. UTF-8 admite cualquier carácter."), sizer=sizer)
		self.lista_cod.SetSelection(self.valores_cod.index(cod) if cod in self.valores_cod else 0)
		self.valores_fin = [valor for valor, _n in FINES_DE_LINEA]
		_etiqueta, self.lista_fin = crear_campo(panel, _("&Fin de línea:"), wx.Choice, choices=[_(n) for _v, n in FINES_DE_LINEA],
			ayuda=_("Caracteres que separan las líneas. Windows usa CRLF."), sizer=sizer)
		self.lista_fin.SetSelection(self.valores_fin.index(fin_de_linea) if fin_de_linea in self.valores_fin else 0)
		self.casilla_bom = wx.CheckBox(panel, label=_("Escribir la marca &BOM al principio"))
		self.casilla_bom.SetValue(bom)
		self.casilla_bom.SetHelpText(_("Marca que indica la codificación (solo en UTF-8 y UTF-16). Algunos programas la necesitan."))
		sizer.Add(self.casilla_bom, 0, wx.ALL, 5)
		sizer.Add(dialogos.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(sizer)
		_marco(self, panel)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar(), id=wx.ID_OK)
		dialogos.preparar_dialogo(self, foco_inicial=self.campo_ruta)
		self.CentreOnParent()

	def ruta(self) -> str:
		texto = self.campo_ruta.GetValue().strip().strip('"')
		return rutas.normalizar(texto) if texto else ""

	def codificacion(self) -> str:
		return self.valores_cod[max(0, self.lista_cod.GetSelection())]

	def fin_de_linea(self) -> str:
		return self.valores_fin[max(0, self.lista_fin.GetSelection())]

	def bom(self) -> bool:
		return self.casilla_bom.GetValue() and self.codificacion().startswith("utf")

	def problema(self) -> str | None:
		ruta = self.ruta()
		if not ruta or not os.path.isabs(ruta):
			return _("Escriba la ruta completa del archivo (por ejemplo C:\\Documentos\\nota.txt).")
		problema = rutas.problema_en_nombre(os.path.basename(ruta))
		if problema:
			return problema
		if not os.path.isdir(os.path.dirname(ruta)):
			return _("La carpeta «{c}» no existe.").format(c=os.path.dirname(ruta))
		if os.path.isdir(ruta):
			return _("«{r}» es una carpeta: añada el nombre del archivo.").format(r=ruta)
		return None

	def aceptar(self, confirmar_sobrescribir: bool = True) -> bool:
		problema = self.problema()
		if problema:
			dialogos.mostrar_error(self, problema)
			self.campo_ruta.SetFocus()
			self.campo_ruta.SelectAll()
			return False
		if confirmar_sobrescribir and os.path.exists(self.ruta()):
			pregunta = _("«{n}» ya existe. ¿Sustituirlo?").format(n=os.path.basename(self.ruta()))
			if dialogos.confirmar(self, pregunta, _("Guardar como"), peligroso=True) != wx.ID_YES:
				self.campo_ruta.SetFocus()
				return False
		_terminar(self, wx.ID_OK)
		return True

	def _al_examinar(self, _evento: wx.CommandEvent) -> None:
		ruta = self.ruta()
		dialogo = wx.FileDialog(self, _("Guardar como"), defaultDir=os.path.dirname(ruta) if ruta else "",
			defaultFile=os.path.basename(ruta) if ruta else "", wildcard=_("Todos los archivos (*.*)|*.*"),
			style=wx.FD_SAVE)
		try:
			if dialogo.ShowModal() == wx.ID_OK:
				self.campo_ruta.SetValue(dialogo.GetPath())
		finally:
			dialogo.Destroy()
		self.campo_ruta.SetFocus()
