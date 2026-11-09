# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Configuración avanzada del OCR: elegir el idioma entre los instalados y cómo instalar más.

«&Idioma de reconocimiento:» (desplegable; la primera opción es el de Windows),
«Cómo instalar &más idiomas:» (texto de solo lectura) y Aceptar y Cancelar.
Los idiomas se piden al motor en un hilo: el diálogo se abre enseguida.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Sequence
from typing import Any

import wx

from ..servicios.motor import COMO_INSTALAR
from .comun import atender_f1


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoIdioma(wx.Dialog):
	def __init__(self, padre: wx.Window | None, ui: Any, actual: str, al_ayuda: Callable[[], None] | None = None) -> None:
		super().__init__(padre, title=_("Reconocimiento de texto: idioma"))
		self.actual = actual
		self.etiquetas: list[str] = [""]
		raiz = wx.BoxSizer(wx.VERTICAL)
		_e, self.idioma = ui.crear_campo(self, _("&Idioma de reconocimiento:"), wx.Choice,
			choices=[_("El de Windows"), _("Cargando los idiomas instalados...")], sizer=raiz,
			ayuda=_("Idioma en el que se reconoce el texto. Solo salen los que Windows tiene instalados."))
		self.idioma.SetSelection(0)
		_e, self.explicacion = ui.crear_campo(self, _("Cómo instalar &más idiomas:"), wx.TextCtrl, sizer=raiz,
			value=_(COMO_INSTALAR), style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
			ayuda=_("Pasos para añadir idiomas de reconocimiento de texto en Windows."))
		self.explicacion.SetMinSize(self.FromDIP(wx.Size(460, 90)))
		raiz.Add(ui.crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(raiz)
		ui.preparar_dialogo(self, foco_inicial=self.idioma)
		atender_f1(self, al_ayuda)

	def poner_idiomas(self, idiomas: Sequence[tuple[str, str]]) -> None:
		"""(etiqueta, nombre) de los idiomas instalados."""
		self.etiquetas = [""] + [e for e, _n in idiomas]
		self.idioma.Set([_("El de Windows")] + [f"{n} ({e})" for e, n in idiomas])
		self.idioma.SetSelection(self.etiquetas.index(self.actual) if self.actual in self.etiquetas else 0)

	def elegido(self) -> str:
		indice = self.idioma.GetSelection()
		return self.etiquetas[indice] if 0 <= indice < len(self.etiquetas) else ""
