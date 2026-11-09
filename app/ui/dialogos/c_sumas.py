# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de las sumas de comprobación (sección 8.19): crear y ver el resultado de verificar.

- ``DialogoCrearSumas``: algoritmo, un archivo de sumas por archivo o uno para
  todos, dónde guardarlo y su nombre. Con un solo archivo se ofrece «Copiar la
  suma al portapapeles y anunciarla» (entonces no se guarda ningún archivo y
  los campos de guardar se desactivan).
- ``DialogoResultadosSumas``: lista Nombre y Resultado («Correcto»,
  «Distinto», «No encontrado», «Error de lectura») con el resumen en un campo
  de solo lectura. El foco empieza en la lista, con la primera fila enfocada
  (siempre hay un elemento enfocado, regla del agente de accesibilidad).
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import sumas
from app.services.vfs import rutas
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos.c_comprimir import _campo_resumen, _cuadro, terminar

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoCrearSumas(wx.Dialog):
	"""Opciones para crear sumas. No lanza la operación.

	:param un_archivo: el trabajo es un único archivo (se ofrece copiar la suma al portapapeles).
	:param nombre: nombre propuesto del archivo de sumas (sin extensión).
	"""

	def __init__(self, padre: wx.Window | None, resumen: str, carpeta: str, nombre: str, un_archivo: bool = False,
			algoritmo: str = "sha256") -> None:
		super().__init__(padre, title=_("Crear sumas de comprobación"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			name=_("Crear sumas de comprobación"))
		self._nombre_base = nombre
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.texto_resumen = _campo_resumen(panel, sizer, resumen, _("Archivos de los que se calcula la suma."))
		_etiqueta, self.lista_algoritmo = crear_campo(panel, _("&Algoritmo:"), wx.Choice, choices=[a.nombre for a in sumas.ALGORITMOS],
			ayuda=_("SHA-256 es el más usado hoy. CRC32 crea un archivo SFV; MD5 y SHA-1 sirven para comprobar descargas antiguas."),
			sizer=sizer)
		self.lista_algoritmo.SetSelection(next((i for i, a in enumerate(sumas.ALGORITMOS) if a.id == algoritmo), 3))
		self.casilla_por_archivo = wx.CheckBox(panel, label=_("Un archivo de sumas &por cada archivo"))
		self.casilla_por_archivo.SetHelpText(_("Crea «nombre.sha256» para cada archivo en lugar de un solo archivo para todos."))
		sizer.Add(self.casilla_por_archivo, 0, wx.ALL, 5)
		_etiqueta, self.campo_carpeta = crear_campo(panel, _("&Guardar en:"), wx.TextCtrl, value=carpeta,
			ayuda=_("Carpeta donde se guardan los archivos de sumas."), sizer=sizer)
		_etiqueta, self.campo_nombre = crear_campo(panel, _("Nombre del archivo de &sumas:"), wx.TextCtrl,
			value=nombre + self.algoritmo().extension, ayuda=_("Nombre del archivo con todas las sumas."), sizer=sizer)
		self.casilla_portapapeles = wx.CheckBox(panel, label=_("&Copiar la suma al portapapeles y anunciarla"))
		self.casilla_portapapeles.SetHelpText(_("Solo con un archivo: calcula la suma, la copia y la dice, sin guardar ningún archivo."))
		self.casilla_portapapeles.Enable(un_archivo)
		self.casilla_portapapeles.Show(un_archivo)
		sizer.Add(self.casilla_portapapeles, 0, wx.ALL, 5)

		self.boton_aceptar = wx.Button(panel, wx.ID_OK, label=_("Ca&lcular"))
		self.boton_aceptar.SetHelpText(_("Calcula las sumas (Intro)."))
		self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, label=_("Ca&ncelar"))
		self.boton_aceptar.SetDefault()
		_cuadro(self, panel, sizer, [self.boton_aceptar, self.boton_cancelar])

		self.lista_algoritmo.Bind(wx.EVT_CHOICE, self._al_cambiar_algoritmo)
		self.casilla_por_archivo.Bind(wx.EVT_CHECKBOX, lambda _e: self._actualizar())
		self.casilla_portapapeles.Bind(wx.EVT_CHECKBOX, lambda _e: self._actualizar())
		self.boton_aceptar.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		self._actualizar()
		preparar_dialogo(self, foco_inicial=self.lista_algoritmo)
		self.CentreOnParent()

	def algoritmo(self) -> sumas.Algoritmo:
		indice = self.lista_algoritmo.GetSelection()
		return sumas.ALGORITMOS[indice] if 0 <= indice < len(sumas.ALGORITMOS) else sumas.POR_ID["sha256"]

	def uno_por_archivo(self) -> bool:
		return self.casilla_por_archivo.GetValue()

	def al_portapapeles(self) -> bool:
		return self.casilla_portapapeles.IsEnabled() and self.casilla_portapapeles.GetValue()

	def carpeta(self) -> str:
		return self.campo_carpeta.GetValue().strip().strip('"')

	def nombre_archivo(self) -> str:
		return self.campo_nombre.GetValue().strip()

	def _al_cambiar_algoritmo(self, evento: wx.CommandEvent) -> None:
		nombre = self.nombre_archivo()
		anterior = sumas.algoritmo_de_archivo(nombre)
		if anterior is not None:
			nombre = nombre[: -len(anterior.extension)]
		self.campo_nombre.SetValue((nombre or self._nombre_base) + self.algoritmo().extension)
		evento.Skip()

	def _actualizar(self) -> None:
		guardar = not self.al_portapapeles()
		self.casilla_por_archivo.Enable(guardar)
		self.campo_carpeta.Enable(guardar)
		self.campo_nombre.Enable(guardar and not self.uno_por_archivo())

	def problema(self) -> str | None:
		if self.al_portapapeles():
			return None
		if not self.carpeta():
			return _("Escriba la carpeta donde guardar las sumas.")
		if not self.uno_por_archivo():
			return rutas.problema_en_nombre(self.nombre_archivo())
		return None

	def aceptar(self) -> bool:
		problema = self.problema()
		if problema:
			dialogos.mostrar_error(self, problema, self.GetTitle())
			return False
		terminar(self, wx.ID_OK)
		return True


class DialogoResultadosSumas(wx.Dialog):
	"""Resultado de verificar un archivo de sumas: lista de archivos y resumen."""

	def __init__(self, padre: wx.Window | None, titulo: str, verificaciones: list[sumas.Verificacion]) -> None:
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		self.verificaciones = list(verificaciones)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.texto_resumen = crear_campo(panel, _("&Resumen:"), wx.TextCtrl,
			value=sumas.resumen_verificacion(self.verificaciones), style=wx.TE_READONLY,
			ayuda=_("Cuántos archivos coinciden y cuántos no."), sizer=sizer)
		etiqueta = wx.StaticText(panel, label=_("&Archivos comprobados:"))
		self.lista = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=panel.FromDIP(wx.Size(520, 260)),
			name=_("Archivos comprobados"))
		self.lista.SetHelpText(_("Cada archivo del archivo de sumas y su resultado. Los distintos están dañados o han cambiado."))
		self.lista.InsertColumn(0, _("Nombre"), width=panel.FromDIP(360))
		self.lista.InsertColumn(1, _("Resultado"), width=panel.FromDIP(140))
		for indice, verificacion in enumerate(self.verificaciones):
			self.lista.InsertItem(indice, verificacion.nombre)
			self.lista.SetItem(indice, 1, verificacion.resultado.texto)
		if self.verificaciones:
			self.lista.Focus(0)
			self.lista.Select(0)
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		self.boton_cerrar = wx.Button(panel, wx.ID_CANCEL, label=_("&Cerrar"))
		self.boton_cerrar.SetDefault()
		_cuadro(self, panel, sizer, [self.boton_cerrar])
		preparar_dialogo(self, foco_inicial=self.lista if self.verificaciones else self.texto_resumen)
		self.CentreOnParent()
