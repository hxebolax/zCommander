# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de etiquetas: editor de uno o varios archivos y «Etiquetas desde el nombre».

Formularios con la etiqueta creada antes de cada campo (``zc.ui.crear_campo``),
Ctrl+H con la ayuda de cada control y botones en español. Con varios archivos,
cada campo empieza en «(sin cambio)»: lo que no se toca no se escribe.
"""

from __future__ import annotations

import builtins
import os
from typing import Any

import wx

from . import etiquetas


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


CAMPOS = (
	("artista", "A&rtista:", "Artista o intérprete."),
	("titulo", "&Título:", "Título de la pista."),
	("album", "Á&lbum:", "Álbum o disco."),
	("pista", "&Pista:", "Número de pista, como 3 o 3/12."),
	("anio", "A&ño:", "Año de publicación, como 2024."),
	("genero", "&Género:", "Género musical."),
)


def _marco(dialogo: wx.Dialog, panel: wx.Panel) -> None:
	marco = wx.BoxSizer(wx.VERTICAL)
	marco.Add(panel, 1, wx.EXPAND)
	dialogo.SetSizerAndFit(marco)


class DialogoEditar:
	"""Editor de etiquetas. ``valores`` son los del archivo (uno) o ``None`` (varios: «(sin cambio)»)."""

	def __init__(self, ui: Any, padre: wx.Window | None, nombres: list[str], valores: dict[str, str] | None,
			informacion: str = "") -> None:
		self._originales = dict(valores) if valores is not None else None
		titulo = (_("Etiquetas de {n}").format(n=nombres[0]) if len(nombres) == 1
			else _("Etiquetas de {n} archivos").format(n=len(nombres)))
		self.dialogo = wx.Dialog(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		panel = wx.Panel(self.dialogo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.campos: dict[str, wx.TextCtrl] = {}
		varios = valores is None
		for clave, etiqueta, ayuda in CAMPOS:
			valor = etiquetas.SIN_CAMBIO if varios else (valores or {}).get(clave, "")
			texto_ayuda = _(ayuda)
			if varios:
				texto_ayuda += " " + _("Deje «(sin cambio)» para no tocarlo en ningún archivo; bórrelo todo para quitar esta etiqueta.")
			else:
				texto_ayuda += " " + _("Vacío quita la etiqueta.")
			_etiqueta, campo = ui.crear_campo(panel, _(etiqueta), wx.TextCtrl, value=valor, ayuda=texto_ayuda, sizer=sizer,
				horizontal=True)
			self.campos[clave] = campo
		self.informacion = None
		if informacion:
			_etiqueta, self.informacion = ui.crear_campo(panel, _("&Información del archivo:"), wx.TextCtrl, value=informacion,
				style=wx.TE_MULTILINE | wx.TE_READONLY, size=panel.FromDIP(wx.Size(420, 110)),
				ayuda=_("Duración, tasa de bits, frecuencia, canales y portada (solo lectura)."), sizer=sizer)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		_marco(self.dialogo, panel)
		ui.preparar_dialogo(self.dialogo, foco_inicial=self.campos["artista"])

	def cambios(self) -> dict[str, str]:
		"""Lo que hay que escribir: con un archivo, lo que cambió; con varios, lo que dejó de decir «(sin cambio)»."""
		resultado = {}
		for clave, campo in self.campos.items():
			valor = campo.GetValue().strip()
			if self._originales is None:
				if valor != etiquetas.SIN_CAMBIO:
					resultado[clave] = valor
			elif valor != self._originales.get(clave, "").strip():
				resultado[clave] = valor
		return resultado


class DialogoDesdeNombre:
	"""Máscara con campos ``[pista]``, ``[artista]``... y vista previa de lo que saldrá de cada nombre."""

	COLUMNAS = (("archivo", "Archivo"), ("pista", "Pista"), ("artista", "Artista"), ("titulo", "Título"), ("album", "Álbum"),
		("anio", "Año"), ("genero", "Género"))

	def __init__(self, ui: Any, padre: wx.Window | None, rutas: list[str], mascara: str) -> None:
		self.rutas = list(rutas)
		self.resultados: dict[str, dict[str, str]] = {}
		self.dialogo = wx.Dialog(padre, title=_("Etiquetas desde el nombre"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		panel = wx.Panel(self.dialogo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.mascara = ui.crear_campo(panel, _("&Máscara:"), wx.TextCtrl, value=mascara, sizer=sizer,
			ayuda=_("Cómo se forman los nombres. Campos: [pista], [artista], [titulo], [album], [anio] y [genero]; "
				"[*] salta un trozo. Por ejemplo: [pista] - [artista] - [titulo]."))
		sizer.Add(wx.StaticText(panel, label=_("&Vista previa:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.vista = ui.ListaAccesible(panel, _("Vista previa"), columnas=[(_(t), 110) for _c, t in self.COLUMNAS])
		self.vista.SetHelpText(_("Lo que se escribirá en cada archivo. «No encaja» quiere decir que ese nombre no sigue la máscara "
			"y se dejará como está."))
		self.vista.SetMinSize(panel.FromDIP(wx.Size(720, 220)))
		sizer.Add(self.vista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		self.aviso = wx.StaticText(panel, label="")
		sizer.Add(self.aviso, 0, wx.ALL, 5)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		_marco(self.dialogo, panel)
		ui.preparar_dialogo(self.dialogo, foco_inicial=self.mascara)
		self.mascara.Bind(wx.EVT_TEXT, lambda _e: self.actualizar())
		self.actualizar()

	def actualizar(self) -> None:
		self.resultados = {}
		filas = []
		try:
			patron = etiquetas.compilar_mascara(self.mascara.GetValue())
			error = ""
		except etiquetas.ErrorEtiquetas as problema:
			patron, error = None, str(problema)
		for ruta in self.rutas:
			nombre = os.path.basename(ruta)
			campos = etiquetas.desde_nombre(patron, nombre) if patron is not None else None
			if campos:
				self.resultados[ruta] = campos
				filas.append([nombre] + [campos.get(c, "") for c, _t in self.COLUMNAS[1:]])
			else:
				filas.append([nombre, _("No encaja")] + [""] * (len(self.COLUMNAS) - 2))
		self.vista.reemplazar_filas(filas, conservar_foco=True)
		encajan = len(self.resultados)
		self.aviso.SetLabel(error or _("{n} de {t} nombres encajan con la máscara.").format(n=encajan, t=len(self.rutas)))
