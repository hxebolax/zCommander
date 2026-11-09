# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Historiales con búsqueda: carpetas del panel (Alt+F12) y órdenes de la línea (Alt+F8).

Un campo «Buscar» filtra mientras se escribe (sin distinguir mayúsculas ni
tildes) y la lista nativa muestra lo que queda, lo más reciente primero.
Flecha abajo en el campo pasa a la lista, para no tener que tabular. Tras
filtrar se dice cuántas quedan (el lector no lo sabría sin recorrerla).

En el de órdenes, Intro pone la orden en la línea de órdenes para revisarla
(lo prudente con algo que se va a ejecutar) y «Ejecutar» la lanza ya.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Sequence

import wx

from app.ui import anuncios
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)

PONER, EJECUTAR, IR = "poner", "ejecutar", "ir"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def filtrar(elementos: Sequence[str], texto: str) -> list[str]:
	"""Elementos que contienen todas las palabras de ``texto`` (en cualquier orden)."""
	palabras = f_comun.normalizar_busqueda(texto).split()
	if not palabras:
		return list(elementos)
	return [e for e in elementos if all(p in f_comun.normalizar_busqueda(e) for p in palabras)]


class DialogoHistorial(f_comun.DialogoF):
	"""``elegido`` y ``accion`` (``ir``, ``poner`` o ``ejecutar``) quedan con la elección."""

	def __init__(self, padre: wx.Window | None, titulo: str, etiqueta_lista: str, elementos: Sequence[str],
			ordenes: bool = False) -> None:
		super().__init__(padre, titulo)
		self.elementos = list(elementos)
		self.visibles = list(elementos)
		self.ordenes = ordenes
		self.elegido: str | None = None
		self.accion = ""
		_b, self.campo = crear_campo(self.panel, _("&Buscar:"), wx.TextCtrl, size=self.FromDIP(wx.Size(460, -1)),
			ayuda=_("Escriba parte del texto para quedarse con lo que lo contiene. Flecha abajo pasa a la lista."), sizer=self.sizer)
		_l, self.lista = crear_campo(self.panel, etiqueta_lista, wx.ListBox, choices=self.visibles,
			size=self.FromDIP(wx.Size(460, 260)), sizer=self.sizer,
			ayuda=_("Intro pone la orden en la línea de órdenes.") if ordenes else _("Intro lleva el panel a esa carpeta."))
		self.sizer.GetItem(self.lista).SetProportion(1)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		if ordenes:
			self.boton_principal = self.boton(_("&Poner en la línea de órdenes"), _("Escribe la orden en la línea de órdenes sin ejecutarla."),
				lambda: self.elegir(PONER), fila)
			self.boton(_("E&jecutar ahora"), _("Ejecuta la orden elegida en la carpeta del panel activo."), lambda: self.elegir(EJECUTAR), fila)
		else:
			self.boton_principal = self.boton(_("&Ir"), _("Lleva el panel a la carpeta elegida."), lambda: self.elegir(IR), fila)
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT)
		self.campo.Bind(wx.EVT_TEXT, lambda _e: self.aplicar_filtro())
		self.campo.Bind(wx.EVT_KEY_DOWN, self._al_tecla_campo)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.elegir(PONER if ordenes else IR))
		self.terminar(wx.CANCEL, foco=self.lista if self.visibles else self.campo)
		self.boton_principal.SetDefault()
		if self.visibles:
			self.lista.SetSelection(0)

	def aplicar_filtro(self) -> None:
		self.visibles = filtrar(self.elementos, self.campo.GetValue())
		self.lista.Set(self.visibles)
		if self.visibles:
			self.lista.SetSelection(0)
		texto = _("{n} coincidencias").format(n=len(self.visibles)) if self.visibles else _("Ninguna coincidencia")
		anuncios.anunciar(texto, anuncios.DETALLE if self.visibles else anuncios.RESULTADO)

	def elegir(self, accion: str) -> None:
		indice = self.lista.GetSelection()
		if not 0 <= indice < len(self.visibles):
			anuncios.anunciar(_("No hay nada elegido"), anuncios.RESULTADO)
			return
		self.elegido = self.visibles[indice]
		self.accion = accion
		self.cerrar(wx.ID_OK)

	def _al_tecla_campo(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DOWN and evento.GetModifiers() == wx.MOD_NONE and self.visibles:
			self.lista.SetFocus()
			return
		evento.Skip()


def elegir_carpeta(padre: wx.Window | None, carpetas: Sequence[str]) -> str | None:
	dialogo = DialogoHistorial(padre, _("Historial de carpetas"), _("Carpetas &visitadas:"), carpetas)
	return f_comun.mostrar(dialogo, lambda d: d.elegido)


def elegir_orden(padre: wx.Window | None, ordenes: Sequence[str]) -> tuple[str, str] | None:
	"""(orden, acción) con acción ``poner`` o ``ejecutar``; ``None`` si se cancela."""
	dialogo = DialogoHistorial(padre, _("Historial de órdenes"), _("Ó&rdenes ejecutadas:"), ordenes, ordenes=True)
	return f_comun.mostrar(dialogo, lambda d: (d.elegido, d.accion))
