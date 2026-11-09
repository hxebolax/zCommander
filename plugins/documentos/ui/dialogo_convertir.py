# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Convertir a texto»: formato, codificación y dónde se guardan los archivos.

Letras de la pantalla: &Formato (F), Co&dificación (D), &Guardar en (G),
C&onvertir (O) y &Cancelar (C).
"""

from __future__ import annotations

import builtins
import os
from collections.abc import Callable, Sequence
from typing import Any

import wx

from .comun import atender_f1, botonera

FORMATOS = (("txt", "Texto (.txt)"), ("md", "Markdown (.md)"))
CODIFICACIONES = (("utf-8", "UTF-8"), ("utf-8-sig", "UTF-8 con BOM"))


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _indice(opciones: Sequence[tuple[str, str]], valor: str) -> int:
	return next((i for i, (clave, _e) in enumerate(opciones) if clave == valor), 0)


class DialogoConvertir(wx.Dialog):
	"""Elige el formato, la codificación y la carpeta; ``carpeta_pasiva`` vacía si el otro panel no es local."""

	def __init__(self, padre: wx.Window | None, ui: Any, nombres: Sequence[str], formato: str, codificacion: str,
			carpeta_pasiva: str = "", al_ayuda: Callable[[], None] | None = None) -> None:
		titulo = _("Convertir {n} a texto").format(n=nombres[0]) if len(nombres) == 1 else \
			_("Convertir {n} documentos a texto").format(n=len(nombres))
		super().__init__(padre, title=titulo)
		self.carpeta_pasiva = carpeta_pasiva
		raiz = wx.BoxSizer(wx.VERTICAL)
		_e, self.formato = ui.crear_campo(self, _("&Formato:"), wx.Choice, choices=[_(e) for _c, e in FORMATOS], sizer=raiz,
			ayuda=_("Texto plano o Markdown, que conserva los encabezados con almohadillas."))
		self.formato.SetSelection(_indice(FORMATOS, formato))
		_e, self.codificacion = ui.crear_campo(self, _("Co&dificación:"), wx.Choice, choices=[_(e) for _c, e in CODIFICACIONES],
			sizer=raiz, ayuda=_("Con BOM, el Bloc de notas antiguo y otros programas de Windows reconocen mejor el UTF-8."))
		self.codificacion.SetSelection(_indice(CODIFICACIONES, codificacion))
		lugares = [_("Junto a cada documento")]
		if carpeta_pasiva:
			lugares.append(_("En la carpeta del otro panel: {c}").format(c=carpeta_pasiva))
		_e, self.lugar = ui.crear_campo(self, _("&Guardar en:"), wx.Choice, choices=lugares, sizer=raiz,
			ayuda=_("Dónde se crean los archivos de texto; si ya existe uno, se pregunta."))
		self.lugar.SetSelection(0)
		raiz.Add(botonera(self, [(wx.ID_OK, _("C&onvertir")), (wx.ID_CANCEL, _("&Cancelar"))], wx.ID_OK), 0,
			wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(raiz)
		ui.preparar_dialogo(self, foco_inicial=self.formato)
		atender_f1(self, al_ayuda)

	def eleccion(self) -> tuple[str, str, str]:
		"""(formato, codificación, carpeta de destino o «» para junto a cada documento)."""
		formato = FORMATOS[max(0, self.formato.GetSelection())][0]
		codificacion = CODIFICACIONES[max(0, self.codificacion.GetSelection())][0]
		carpeta = self.carpeta_pasiva if self.lugar.GetSelection() == 1 else ""
		return formato, codificacion, carpeta


def carpeta_de(ruta_local: str) -> str:
	return os.path.dirname(ruta_local)
