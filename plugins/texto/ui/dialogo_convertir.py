# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Convertir la codificación y los fines de línea» con vista previa.

Etiqueta creada antes de cada control; letras únicas en la pantalla (D, F, T,
A, Q, B, R y los botones Con&vertir y &Cancelar); la vista previa se calcula
en un hilo cada vez que cambia una opción y se lee por columnas (Archivo,
Codificación, Fin de línea, Cambios).
"""

from __future__ import annotations

import builtins
import os
from collections.abc import Callable, Sequence
from typing import Any

import wx

from ..servicios.conversion import Opciones
from .comun import atender_f1, botonera

DESTINOS = (("utf8", "UTF-8 sin BOM"), ("utf8_bom", "UTF-8 con BOM"))
FINES = (("sin_cambio", "Sin cambio"), ("crlf", "CRLF (Windows)"), ("lf", "LF (Unix)"))
TABULADORES = (("sin_cambio", "Sin cambio"), ("a_espacios", "Tabuladores a espacios"),
	("a_tabuladores", "Espacios de la sangría a tabuladores"))


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _indice(opciones: Sequence[tuple[str, str]], valor: str) -> int:
	return next((i for i, (clave, _e) in enumerate(opciones) if clave == valor), 0)


class DialogoConvertir(wx.Dialog):
	"""Elige cómo convertir los archivos y muestra cuántos cambios habrá en cada uno.

	:param ui: el módulo de interfaz de la API (``zc.ui``): ``crear_campo``, ``ListaAccesible``, ``preparar_dialogo``.
	:param calcular: ``calcular(opciones, al_listo)`` calcula la vista previa en un hilo y
		llama a ``al_listo(filas)`` en el hilo de la interfaz; ``None`` = sin vista previa.
	"""

	def __init__(self, padre: wx.Window | None, ui: Any, rutas: Sequence[str], opciones: Opciones, copia_bak: bool,
			calcular: Callable[[Opciones, Callable[[list[tuple[str, str, str, str]]], None]], None] | None = None,
			al_ayuda: Callable[[], None] | None = None) -> None:
		titulo = _("Convertir {n} archivos").format(n=len(rutas)) if len(rutas) != 1 else \
			_("Convertir {n}").format(n=os.path.basename(rutas[0]))
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self._calcular = calcular
		self._version = 0
		panel = self
		raiz = wx.BoxSizer(wx.VERTICAL)

		_e, self.destino = ui.crear_campo(panel, _("Codificación de &destino:"), wx.Choice,
			choices=[_(e) for _c, e in DESTINOS], sizer=raiz,
			ayuda=_("Todos los archivos pasan a UTF-8; con BOM, los programas antiguos de Windows lo reconocen mejor."))
		self.destino.SetSelection(_indice(DESTINOS, opciones.destino))
		_e, self.fin = ui.crear_campo(panel, _("&Fin de línea:"), wx.Choice, choices=[_(e) for _c, e in FINES], sizer=raiz,
			ayuda=_("CRLF es el de Windows; LF, el de Linux y macOS. Sin cambio deja los que hay."))
		self.fin.SetSelection(_indice(FINES, opciones.fin_linea))
		_e, self.tabuladores = ui.crear_campo(panel, _("&Tabuladores:"), wx.Choice, choices=[_(e) for _c, e in TABULADORES],
			sizer=raiz, ayuda=_("Cambia los tabuladores por espacios, o los espacios de la sangría por tabuladores."))
		self.tabuladores.SetSelection(_indice(TABULADORES, opciones.tabuladores))
		_e, self.ancho = ui.crear_campo(panel, _("&Ancho del tabulador:"), wx.SpinCtrl, sizer=raiz, min=1, max=16,
			initial=opciones.ancho_tabulador, ayuda=_("Espacios que ocupa cada tabulador, de 1 a 16."))
		self.espacios = wx.CheckBox(panel, label=_("&Quitar los espacios al final de las líneas"))
		self.espacios.SetValue(opciones.quitar_espacios_finales)
		self.espacios.SetHelpText(_("Borra los espacios y tabuladores que sobran al final de cada línea."))
		raiz.Add(self.espacios, 0, wx.ALL, 5)
		self.copia = wx.CheckBox(panel, label=_("Guardar una copia .&bak del original"))
		self.copia.SetValue(copia_bak)
		self.copia.SetHelpText(_("Deja el archivo original junto al nuevo con la extensión .bak. "
			"Sin ella, Deshacer también recupera el original mientras zCommander siga abierto."))
		raiz.Add(self.copia, 0, wx.ALL, 5)
		etiqueta_previa = wx.StaticText(panel, label=_("Vista p&revia:"))
		self.previa = ui.ListaAccesible(panel, _("Vista previa"), columnas=[(_("Archivo"), 220), (_("Codificación"), 130),
			(_("Fin de línea"), 110), (_("Cambios"), 260)])
		self.previa.SetHelpText(_("Lo que pasará con cada archivo. Izquierda y derecha leen las columnas."))
		raiz.Add(etiqueta_previa, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		raiz.Add(self.previa, 1, wx.EXPAND | wx.ALL, 5)
		_e, self.estado = ui.crear_campo(panel, _("&Estado:"), wx.TextCtrl, sizer=raiz, horizontal=True,
			value=_("Calculando la vista previa..."), style=wx.TE_READONLY,
			ayuda=_("Cuántos archivos cambiarán con las opciones elegidas."))
		raiz.Add(botonera(panel, [(wx.ID_OK, _("Con&vertir")), (wx.ID_CANCEL, _("&Cancelar"))], wx.ID_OK), 0,
			wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(raiz)
		self.SetSize(self.FromDIP(wx.Size(720, 520)))
		ui.preparar_dialogo(self, foco_inicial=self.destino)
		atender_f1(self, al_ayuda)
		for control, evento in ((self.destino, wx.EVT_CHOICE), (self.fin, wx.EVT_CHOICE), (self.tabuladores, wx.EVT_CHOICE),
				(self.ancho, wx.EVT_SPINCTRL), (self.espacios, wx.EVT_CHECKBOX)):
			control.Bind(evento, lambda _evento: self.recalcular())
		self.recalcular()

	def opciones(self) -> Opciones:
		return Opciones(
			destino=DESTINOS[max(0, self.destino.GetSelection())][0],
			fin_linea=FINES[max(0, self.fin.GetSelection())][0],
			tabuladores=TABULADORES[max(0, self.tabuladores.GetSelection())][0],
			ancho_tabulador=int(self.ancho.GetValue()),
			quitar_espacios_finales=self.espacios.GetValue(),
		)

	def copia_bak(self) -> bool:
		return self.copia.GetValue()

	def recalcular(self) -> None:
		"""Pide la vista previa de las opciones actuales; la que llegue tarde de otras opciones se descarta."""
		if self._calcular is None:
			self.estado.SetValue(_("Sin vista previa."))
			return
		self._version += 1
		version = self._version
		self.estado.SetValue(_("Calculando la vista previa..."))

		def al_listo(filas: list[tuple[str, str, str, str]]) -> None:
			if not self or version != self._version:
				return
			self.previa.reemplazar_filas([list(f) for f in filas])
			cambian = sum(1 for f in filas if f[3] and f[3] != _("Sin cambios") and not f[3].startswith(_("Error")))
			self.estado.SetValue(_("{c} de {t} archivos cambiarán.").format(c=cambian, t=len(filas)))

		self._calcular(self.opciones(), al_listo)
