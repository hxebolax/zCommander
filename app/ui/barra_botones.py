# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Barra de botones configurable (diseño 2.0, 10.6).

Botones nativos con el nombre de su orden (el lector lo lee como nombre del
botón) y su tecla en la ayuda (Ctrl+H). La barra está FUERA del orden de
tabulación (Tab sigue cambiando de panel): se entra con ``ir_barra_botones``
(Alt+Mayús+F11, como en Total Commander 10). Dentro, Izquierda y Derecha
recorren los botones, Intro o Espacio ejecutan y Escape (o Tab) vuelve al panel.

Se usan ``wx.Button`` y no ``wx.ToolBar``: los botones de una barra de
herramientas no reciben el foco uno a uno en Windows y el lector no los recorre.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Sequence

import wx

from app.services.menus_personalizados import SEPARADOR
from app.services.teclas import nombre_visible

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class BotonBarra(wx.Button):
	"""Botón que solo recibe el foco a propósito (``SetFocus``), nunca con Tab."""

	def AcceptsFocusFromKeyboard(self) -> bool:  # noqa: N802 - API de wx
		return False


class BarraBotones(wx.Panel):
	"""Fila de botones de órdenes.

	:param elementos: ids de orden y ``"-"`` (separador).
	:param etiqueta_de: etiqueta visible de una orden (sin «&»).
	:param ayuda_de: ayuda de una orden.
	:param tecla_de: tecla canónica de una orden (o «»).
	:param ejecutar: ``ejecutar(id_orden)``.
	:param volver: lleva el foco al panel activo (Escape).
	"""

	def __init__(self, padre: wx.Window, elementos: Sequence[str], etiqueta_de: Callable[[str], str],
			ayuda_de: Callable[[str], str], tecla_de: Callable[[str], str], ejecutar: Callable[[str], None],
			volver: Callable[[], None]) -> None:
		super().__init__(padre, name=_("Barra de botones"))
		self._ejecutar = ejecutar
		self._volver = volver
		self.botones: list[BotonBarra] = []
		self.ordenes: list[str] = []
		sizer = wx.BoxSizer(wx.HORIZONTAL)
		for elemento in elementos:
			if elemento == SEPARADOR:
				sizer.Add(wx.StaticLine(self, style=wx.LI_VERTICAL), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, self.FromDIP(4))
				continue
			# La etiqueta del botón es su nombre accesible; «&» se duplica para que no sea letra de acceso
			# (la barra está fuera de los menús y del orden de tabulación: sus letras no deben chocar con nada).
			boton = BotonBarra(self, label=etiqueta_de(elemento).replace("&", "&&"), style=wx.BU_EXACTFIT)
			tecla = tecla_de(elemento)
			ayuda = ayuda_de(elemento)
			if tecla:
				ayuda = f"{ayuda} {_('Tecla: {t}.').format(t=nombre_visible(tecla))}".strip()
			boton.SetHelpText(ayuda)
			boton.SetToolTip(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, i=elemento: self._pulsar(i))
			boton.Bind(wx.EVT_KEY_DOWN, self._al_tecla)
			sizer.Add(boton, 0, wx.ALL, self.FromDIP(2))
			self.botones.append(boton)
			self.ordenes.append(elemento)
		self.SetSizer(sizer)

	def AcceptsFocusFromKeyboard(self) -> bool:  # noqa: N802 - API de wx
		return False

	def entrar(self) -> bool:
		"""Pone el foco en el primer botón; falso si la barra está vacía."""
		if not self.botones:
			return False
		self.botones[0].SetFocus()
		return True

	def indice_enfocado(self) -> int:
		foco = wx.Window.FindFocus()
		return self.botones.index(foco) if foco in self.botones else -1

	def mover(self, paso: int) -> None:
		if not self.botones:
			return
		actual = self.indice_enfocado()
		destino = (max(actual, 0) + paso) % len(self.botones)
		self.botones[destino].SetFocus()

	def _pulsar(self, id_orden: str) -> None:
		self._volver()
		wx.CallAfter(self._ejecutar, id_orden)

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		if codigo in (wx.WXK_RIGHT, wx.WXK_DOWN):
			self.mover(1)
		elif codigo in (wx.WXK_LEFT, wx.WXK_UP):
			self.mover(-1)
		elif codigo == wx.WXK_HOME:
			self.botones[0].SetFocus()
		elif codigo == wx.WXK_END:
			self.botones[-1].SetFocus()
		elif codigo in (wx.WXK_ESCAPE, wx.WXK_TAB):
			self._volver()
		elif codigo in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			indice = self.indice_enfocado()
			if indice >= 0:
				self._pulsar(self.ordenes[indice])
		else:
			evento.Skip()
