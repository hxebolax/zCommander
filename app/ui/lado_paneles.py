# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Un lado de la ventana: cuaderno de pestañas, cada una con un ``PanelArchivos``."""

from __future__ import annotations

import builtins
import logging
from typing import Any

import wx

from app.ui import anuncios
from app.ui.panel_archivos import PanelArchivos, nombre_lado

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class LadoPaneles(wx.Panel):
	"""Lado izquierdo o derecho.

	:param pestanas: lista de pestañas de la sesión (diccionarios de ``sesion.pestana``).
	:param actual: índice de la pestaña activa.
	"""

	def __init__(self, padre: wx.Window, lado: str, ventana: Any, pestanas: list[dict], actual: int = 0) -> None:
		super().__init__(padre)
		self.lado = lado
		self.ventana = ventana
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.cuaderno = wx.Notebook(self, name=_("Pestañas del lado {l}").format(l=nombre_lado(lado).lower()))
		sizer.Add(self.cuaderno, 1, wx.EXPAND)
		self.SetSizer(sizer)
		for datos in pestanas or [{}]:
			self._anadir(datos, seleccionar=False)
		self.cuaderno.SetSelection(max(0, min(actual, self.cuaderno.GetPageCount() - 1)))
		self.cuaderno.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._al_cambiar_pestana)

	# ── Pestañas ──────────────────────────────────────────────────────────────

	def _anadir(self, datos: dict, seleccionar: bool = True, despues_de_actual: bool = True) -> PanelArchivos:
		panel = PanelArchivos(self.cuaderno, self.lado, self.ventana, datos)
		posicion = self.cuaderno.GetSelection() + 1 if despues_de_actual and self.cuaderno.GetPageCount() else self.cuaderno.GetPageCount()
		self.cuaderno.InsertPage(posicion, panel, _("Cargando"), select=seleccionar)
		self.ventana.panel_creado(panel)
		return panel

	def panel_actual(self) -> PanelArchivos:
		indice = self.cuaderno.GetSelection()
		return self.cuaderno.GetPage(max(0, indice))

	def paneles(self) -> list[PanelArchivos]:
		return [self.cuaderno.GetPage(i) for i in range(self.cuaderno.GetPageCount())]

	def iniciar(self) -> None:
		for panel in self.paneles():
			panel.iniciar()

	def nueva_pestana(self, datos: dict | None = None, ruta: str | None = None, proveedor=None, cursor: str | None = None) -> PanelArchivos:
		"""Pestaña nueva tras la actual: con ``datos`` o copiando la actual (y yendo a ``ruta`` si se da)."""
		actual = self.panel_actual()
		base = datos if datos is not None else {**actual.como_dict(), "bloqueada": False}
		if ruta is not None:
			base = {**base, "ruta": ""}
		panel = self._anadir(base)
		if ruta is not None:
			panel.ir_a(ruta, proveedor or actual.proveedor, cursor, forzar_aqui=True)
		else:
			panel.ir_a(actual.ruta, actual.proveedor, forzar_aqui=True)
		self._anunciar_pestana()
		wx.CallAfter(panel.enfocar)
		return panel

	def cerrar_pestana(self, indice: int | None = None) -> bool:
		if self.cuaderno.GetPageCount() <= 1:
			anuncios.anunciar(_("Es la única pestaña de este lado"), anuncios.RESULTADO)
			return False
		indice = self.cuaderno.GetSelection() if indice is None else indice
		panel = self.cuaderno.GetPage(indice)
		self.ventana.soltar_proveedor(panel.proveedor, nuevo=None, panel_que_cierra=panel)
		self.cuaderno.DeletePage(indice)
		self._anunciar_pestana()
		wx.CallAfter(self.panel_actual().enfocar)
		return True

	def cerrar_otras(self) -> None:
		actual = self.cuaderno.GetSelection()
		for indice in reversed(range(self.cuaderno.GetPageCount())):
			if indice != actual:
				panel = self.cuaderno.GetPage(indice)
				self.ventana.soltar_proveedor(panel.proveedor, nuevo=None, panel_que_cierra=panel)
				self.cuaderno.DeletePage(indice)
		self._anunciar_pestana()

	def mover(self, paso: int) -> None:
		total = self.cuaderno.GetPageCount()
		if total <= 1:
			anuncios.anunciar(_("Solo hay una pestaña"), anuncios.RESULTADO)
			return
		self.cuaderno.SetSelection((self.cuaderno.GetSelection() + paso) % total)

	def ir_a_numero(self, numero: int) -> None:
		if 1 <= numero <= self.cuaderno.GetPageCount():
			self.cuaderno.SetSelection(numero - 1)
		else:
			anuncios.anunciar(_("No hay pestaña {n}").format(n=numero), anuncios.RESULTADO)

	def titulo(self, panel: PanelArchivos, texto: str) -> None:
		for indice in range(self.cuaderno.GetPageCount()):
			if self.cuaderno.GetPage(indice) is panel:
				self.cuaderno.SetPageText(indice, texto + (" *" if panel.bloqueada else ""))
				return

	def es_visible(self, panel: PanelArchivos) -> bool:
		return self.cuaderno.GetCurrentPage() is panel

	def _al_cambiar_pestana(self, evento: wx.BookCtrlEvent) -> None:
		evento.Skip()
		wx.CallAfter(self._tras_cambiar)

	def _tras_cambiar(self) -> None:
		if not self:
			return
		panel = self.panel_actual()
		self._anunciar_pestana()
		panel.refrescar(conservar=True)
		panel.enfocar()
		self.ventana.panel_enfocado(panel)

	def _anunciar_pestana(self) -> None:
		total = self.cuaderno.GetPageCount()
		indice = self.cuaderno.GetSelection()
		anuncios.anunciar(
			_("Pestaña {i} de {t}, {n}").format(i=indice + 1, t=total, n=self.cuaderno.GetPageText(indice)), anuncios.RESULTADO,
		)

	def como_dict(self) -> dict:
		return {"pestanas": [p.como_dict() for p in self.paneles()], "actual": max(0, self.cuaderno.GetSelection())}
