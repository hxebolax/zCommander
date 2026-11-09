# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de la lectura en voz: «Convertir a audio» y «Voz de lectura» (configuración avanzada)."""

from __future__ import annotations

import builtins
from typing import Any

import wx

FORMATOS = (("wav", "WAV (sin comprimir)"), ("mp3", "MP3 (necesita FFmpeg)"), ("opus", "Opus (necesita FFmpeg)"))


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _marco(dialogo: wx.Dialog, panel: wx.Panel) -> None:
	marco = wx.BoxSizer(wx.VERTICAL)
	marco.Add(panel, 1, wx.EXPAND)
	dialogo.SetSizerAndFit(marco)


class DialogoExportar:
	"""Formato, carpeta de salida y dividir por capítulos."""

	def __init__(self, ui: Any, padre: wx.Window | None, cuantos: int, formato: str, carpeta: str, hay_ffmpeg: bool,
			hay_documentos: bool) -> None:
		self._ui = ui
		self.dialogo = wx.Dialog(padre, title=_("Convertir a audio"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		panel = wx.Panel(self.dialogo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(wx.StaticText(panel, label=_("Archivos que se convierten: {n}.").format(n=cuantos)), 0, wx.ALL, 5)
		self._formatos = [f for f in FORMATOS if f[0] == "wav" or hay_ffmpeg]
		_e, self.formato = ui.crear_campo(panel, _("&Formato:"), wx.Choice, choices=[_(t) for _v, t in self._formatos],
			ayuda=_("Formato del audio. MP3 y Opus ocupan mucho menos y necesitan el componente FFmpeg."), sizer=sizer)
		codigos = [v for v, _t in self._formatos]
		self.formato.SetSelection(codigos.index(formato) if formato in codigos else 0)
		_e, self.carpeta = ui.crear_campo(panel, _("Carpeta de &salida:"), wx.TextCtrl, value=carpeta,
			ayuda=_("Dónde se crean los archivos de audio. Por defecto, la carpeta del otro panel."), sizer=sizer)
		self.examinar = wx.Button(panel, label=_("E&xaminar..."))
		self.examinar.SetHelpText(_("Abre un cuadro para elegir la carpeta de salida."))
		sizer.Add(self.examinar, 0, wx.LEFT | wx.BOTTOM, 5)
		self.dividir = wx.CheckBox(panel, label=_("&Dividir por capítulos"))
		self.dividir.SetHelpText(_("Un archivo de audio por capítulo (los encabezados principales del documento). Necesita el "
			"complemento Lector de documentos.") if hay_documentos else _("Necesita el complemento Lector de documentos, que no está."))
		self.dividir.Enable(hay_documentos)
		sizer.Add(self.dividir, 0, wx.ALL, 5)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		_marco(self.dialogo, panel)
		self.examinar.Bind(wx.EVT_BUTTON, self._al_examinar)
		ui.preparar_dialogo(self.dialogo, foco_inicial=self.formato)

	def _al_examinar(self, _evento: wx.CommandEvent) -> None:
		dialogo = wx.DirDialog(self.dialogo, _("Carpeta de salida"), self.carpeta.GetValue())
		try:
			if self._ui.mostrar_modal(dialogo) == wx.ID_OK:
				self.carpeta.SetValue(dialogo.GetPath())
		finally:
			dialogo.Destroy()
		self.carpeta.SetFocus()

	@property
	def valor_formato(self) -> str:
		return self._formatos[max(0, self.formato.GetSelection())][0]


class DialogoVoz:
	"""Elegir la voz de lectura entre las instaladas (SAPI 5 y OneCore) y probarla."""

	def __init__(self, ui: Any, padre: wx.Window | None, voces: list[str], actual: str, probar: Any) -> None:
		self._probar = probar
		self.voces = list(voces)
		self.dialogo = wx.Dialog(padre, title=_("Voz de lectura"), style=wx.DEFAULT_DIALOG_STYLE)
		panel = wx.Panel(self.dialogo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		opciones = [_("La predeterminada de Windows")] + self.voces
		_e, self.lista = ui.crear_campo(panel, _("&Voz:"), wx.Choice, choices=opciones,
			ayuda=_("Voz con la que se leen los archivos y se crean los audiolibros (aparte del lector de pantalla)."), sizer=sizer)
		indice = next((i + 1 for i, v in enumerate(self.voces) if v.casefold() == actual.casefold()), 0)
		self.lista.SetSelection(indice)
		self.boton_probar = wx.Button(panel, label=_("&Probar"))
		self.boton_probar.SetHelpText(_("Lee una frase con la voz elegida."))
		sizer.Add(self.boton_probar, 0, wx.ALL, 5)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		_marco(self.dialogo, panel)
		self.boton_probar.Bind(wx.EVT_BUTTON, lambda _e: self._probar(self.elegida))
		ui.preparar_dialogo(self.dialogo, foco_inicial=self.lista)

	@property
	def elegida(self) -> str:
		indice = self.lista.GetSelection()
		return self.voces[indice - 1] if indice > 0 else ""
