# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos del conversor: «Convertir» y «Recortar» (diseño 2.0, 11.6).

Las letras de acceso no repiten ninguna en la misma pantalla (contando los
botones): la ficha del diseño daba la C a «Calidad», «Carpeta de salida»,
«Conservar las etiquetas» y «Cancelar» a la vez, así que se reparten así:
«&Perfil», «Ca&lidad», «Argu&mentos», «Carpeta de &salida», «E&xaminar»,
«&Nombre», «Conservar las e&tiquetas», «Conservar las &fechas», «Si &existe»,
«Con&vertir», «En c&ola» y «&Cancelar».
"""

from __future__ import annotations

import builtins
from typing import Any

import wx

from .. import perfiles

#: Políticas de «Si existe», en el orden del desplegable (valores de ``api.Politica``).
SI_EXISTE = (("preguntar", "Preguntar"), ("renombrar_copia", "Cambiar el nombre: «nombre (2)»"), ("omitir", "Omitir"),
	("sobrescribir", "Sobrescribir el que ya existe"))
ID_EN_COLA = wx.ID_HIGHEST + 1


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _marco(dialogo: wx.Dialog, panel: wx.Panel) -> None:
	marco = wx.BoxSizer(wx.VERTICAL)
	marco.Add(panel, 1, wx.EXPAND)
	dialogo.SetSizerAndFit(marco)


class DialogoConvertir:
	"""``self.dialogo`` termina con ``wx.ID_OK`` (Convertir), ``ID_EN_COLA`` o ``wx.ID_CANCEL``."""

	def __init__(self, ui: Any, padre: wx.Window | None, cuantos: int, perfil: str, carpeta: str, *,
			conservar_etiquetas: bool = True, mascara: str = "[N]", si_existe: str = "preguntar", argumentos: str = "",
			elegir_carpeta: Any = None) -> None:
		self._ui = ui
		self._elegir_carpeta = elegir_carpeta
		self.dialogo = wx.Dialog(padre, title=_("Convertir audio o vídeo"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		panel = wx.Panel(self.dialogo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(wx.StaticText(panel, label=_("Elementos que se convierten: {n}.").format(n=cuantos)), 0, wx.ALL, 5)
		self._ids_perfil = list(perfiles.PERFILES)
		_e, self.perfil = ui.crear_campo(panel, _("&Perfil:"), wx.Choice, choices=[perfiles.PERFILES[p].nombre for p in self._ids_perfil],
			ayuda=_("Formato al que se convierte. Personalizado usa los argumentos de FFmpeg que escriba."), sizer=sizer)
		_e, self.calidad = ui.crear_campo(panel, _("Ca&lidad:"), wx.Choice, choices=[],
			ayuda=_("Calidad o tasa de bits del perfil elegido."), sizer=sizer)
		_e, self.argumentos = ui.crear_campo(panel, _("Argu&mentos de FFmpeg (solo con Personalizado):"), wx.TextCtrl, value=argumentos,
			ayuda=_("Opciones de códec, como -c:a libmp3lame -b:a 128k. No se admiten -y, -i ni rutas fuera de la carpeta de salida."),
			sizer=sizer)
		_e, self.carpeta = ui.crear_campo(panel, _("Carpeta de &salida:"), wx.TextCtrl, value=carpeta,
			ayuda=_("Dónde se crean los archivos convertidos. Por defecto, la carpeta del otro panel."), sizer=sizer)
		self.examinar = wx.Button(panel, label=_("E&xaminar..."))
		self.examinar.SetHelpText(_("Abre un cuadro para elegir la carpeta de salida."))
		sizer.Add(self.examinar, 0, wx.LEFT | wx.BOTTOM, 5)
		_e, self.nombre = ui.crear_campo(panel, _("&Nombre:"), wx.TextCtrl, value=mascara,
			ayuda=_("Nombre de cada archivo convertido: [N] es el nombre original sin extensión, [E] su extensión y [C] un contador. "
				"La extensión del perfil se añade sola."), sizer=sizer)
		self.etiquetas = wx.CheckBox(panel, label=_("Conservar las e&tiquetas"))
		self.etiquetas.SetValue(conservar_etiquetas)
		self.etiquetas.SetHelpText(_("Copia el artista, el título y las demás etiquetas al archivo convertido."))
		sizer.Add(self.etiquetas, 0, wx.ALL, 5)
		self.fechas = wx.CheckBox(panel, label=_("Conservar las &fechas"))
		self.fechas.SetHelpText(_("El archivo convertido toma la fecha de modificación del original."))
		sizer.Add(self.fechas, 0, wx.ALL, 5)
		_e, self.si_existe = ui.crear_campo(panel, _("Si &existe:"), wx.Choice, choices=[_(t) for _v, t in SI_EXISTE],
			ayuda=_("Qué hacer si el archivo de salida ya existe. El original nunca se sobrescribe."), sizer=sizer)
		self.si_existe.SetSelection(next((i for i, (v, _t) in enumerate(SI_EXISTE) if v == si_existe), 0))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.convertir = wx.Button(panel, wx.ID_OK, _("Con&vertir"))
		self.convertir.SetHelpText(_("Empieza a convertir ahora."))
		self.en_cola = wx.Button(panel, ID_EN_COLA, _("En c&ola"))
		self.en_cola.SetHelpText(_("Pone la conversión en la cola de operaciones: empieza cuando terminen las anteriores."))
		cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cancelar"))
		cancelar.SetHelpText(_("Cierra sin convertir."))
		for boton in (self.convertir, self.en_cola, cancelar):
			fila.Add(boton, 0, wx.ALL, 4)
		sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		panel.SetSizer(sizer)
		_marco(self.dialogo, panel)
		self.convertir.SetDefault()
		identificador, calidad = perfiles.partir_perfil(perfil)
		self.perfil.SetSelection(self._ids_perfil.index(identificador))
		self._rellenar_calidades(calidad)
		self.perfil.Bind(wx.EVT_CHOICE, lambda _e: self._rellenar_calidades(""))
		self.examinar.Bind(wx.EVT_BUTTON, self._al_examinar)
		self.en_cola.Bind(wx.EVT_BUTTON, lambda _e: self.dialogo.EndModal(ID_EN_COLA))
		ui.preparar_dialogo(self.dialogo, foco_inicial=self.perfil)

	def _rellenar_calidades(self, elegida: str) -> None:
		datos = perfiles.PERFILES[self.id_perfil]
		self.calidad.Set([_(n) for _c, n in datos.calidades])
		self.calidad.Enable(bool(datos.calidades))
		if datos.calidades:
			codigos = [c for c, _n in datos.calidades]
			self.calidad.SetSelection(codigos.index(elegida) if elegida in codigos else codigos.index(datos.calidad))
		self.argumentos.Enable(self.id_perfil == "personalizado")

	def _al_examinar(self, _evento: wx.CommandEvent) -> None:
		dialogo = wx.DirDialog(self.dialogo, _("Carpeta de salida"), self.carpeta.GetValue())
		try:
			if self._ui.mostrar_modal(dialogo) == wx.ID_OK:
				self.carpeta.SetValue(dialogo.GetPath())
		finally:
			dialogo.Destroy()
		self.carpeta.SetFocus()

	@property
	def id_perfil(self) -> str:
		return self._ids_perfil[max(0, self.perfil.GetSelection())]

	@property
	def id_calidad(self) -> str:
		datos = perfiles.PERFILES[self.id_perfil]
		indice = self.calidad.GetSelection()
		return datos.calidades[indice][0] if datos.calidades and indice >= 0 else ""

	@property
	def valor_si_existe(self) -> str:
		return SI_EXISTE[max(0, self.si_existe.GetSelection())][0]


class DialogoRecortar:
	"""Inicio y fin del recorte, como «0:01:30» y «0:05:00»."""

	def __init__(self, ui: Any, padre: wx.Window | None, nombre: str, duracion: str) -> None:
		self.dialogo = wx.Dialog(padre, title=_("Recortar {n}").format(n=nombre), style=wx.DEFAULT_DIALOG_STYLE)
		panel = wx.Panel(self.dialogo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		if duracion:
			sizer.Add(wx.StaticText(panel, label=_("Duración: {d}.").format(d=duracion)), 0, wx.ALL, 5)
		_e, self.inicio = ui.crear_campo(panel, _("&Inicio:"), wx.TextCtrl, value="0:00",
			ayuda=_("Dónde empieza el recorte: horas:minutos:segundos, como 0:01:30."), sizer=sizer)
		_e, self.fin = ui.crear_campo(panel, _("&Fin:"), wx.TextCtrl, value=duracion,
			ayuda=_("Dónde termina el recorte, como 0:05:00."), sizer=sizer)
		self.recodificar = wx.CheckBox(panel, label=_("&Recodificar para cortar justo en el segundo"))
		self.recodificar.SetHelpText(_("Sin marcar, se copia sin recodificar (más rápido y sin pérdida, pero en un vídeo el corte va "
			"al fotograma clave más cercano)."))
		sizer.Add(self.recodificar, 0, wx.ALL, 5)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		_marco(self.dialogo, panel)
		ui.preparar_dialogo(self.dialogo, foco_inicial=self.inicio)
