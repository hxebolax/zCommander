# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Editor accesible del horario de límites de velocidad (diseño 2.0, 12.9; rclone.md 4.7).

El horario se guarda en el formato de rclone (``08:00,512k:1M 23:00,off``): a
cada hora empieza un límite de subida y bajada que dura hasta la franja
siguiente. Aquí se edita como una lista de franjas (Hora, Subida, Bajada) con
campos normales, sin tener que conocer la sintaxis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import wx

from app.plugins import api

from . import comun

_ = api.traduccion("zc_nubes")[0]

_HORA = re.compile(r"^(?:(?P<dia>[A-Za-z]{3,9})-)?(?P<h>\d{1,2}):(?P<m>\d{2})$")
_UNIDADES = {"b": 1 / 1024, "k": 1, "": 1, "m": 1024, "g": 1024 * 1024, "t": 1024 * 1024 * 1024}


@dataclass
class Franja:
	hora: str            # «08:00» o «Mon-08:00»
	subida_kib: int      # 0 = sin límite
	bajada_kib: int


def a_kib(texto: str) -> int:
	"""«512k» → 512, «10M» → 10240, «off» → 0 (sin límite)."""
	texto = texto.strip().lower()
	if texto in ("", "off", "0"):
		return 0
	coincide = re.fullmatch(r"(\d+(?:\.\d+)?)([bkmgt]?)i?b?", texto)
	if coincide is None:
		raise ValueError(texto)
	return max(1, int(float(coincide.group(1)) * _UNIDADES[coincide.group(2)]))


def de_kib(kib: int) -> str:
	if kib <= 0:
		return "off"
	if kib % 1024 == 0:
		return f"{kib // 1024}M"
	return f"{kib}k"


def leer_horario(texto: str) -> list[Franja]:
	"""Franjas de un horario de rclone; lanza ``ValueError`` si no se entiende."""
	franjas = []
	for entrada in re.split(r"[\s;]+", texto.strip()):
		if not entrada:
			continue
		hora, _coma, limite = entrada.partition(",")
		if not _HORA.match(hora) or not limite:
			raise ValueError(entrada)
		subida, _dos, bajada = limite.partition(":")
		franjas.append(Franja(hora, a_kib(subida), a_kib(bajada if bajada else subida)))
	return franjas


def escribir_horario(franjas: list[Franja]) -> str:
	partes = []
	for franja in sorted(franjas, key=lambda f: f.hora):
		if franja.subida_kib == franja.bajada_kib:
			limite = de_kib(franja.subida_kib)
		else:
			limite = f"{de_kib(franja.subida_kib)}:{de_kib(franja.bajada_kib)}"
		partes.append(f"{franja.hora},{limite}")
	return " ".join(partes)


def texto_limite(kib: int) -> str:
	return _("Sin límite") if kib <= 0 else _("{n} KiB/s").format(n=kib)


class DialogoFranjas(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, horario: str = "") -> None:
		super().__init__(zc, padre, _("Horario de límites de velocidad"))
		try:
			self.franjas = leer_horario(horario)
		except ValueError:
			self.franjas = []
		comun.texto_solo_lectura(zc, self.panel, _("&Explicación:"), _("Cada franja empieza a su hora y dura hasta la siguiente. "
			"Un límite 0 quiere decir sin límite. Las horas son de 00:00 a 23:59; se puede poner un día delante, como Mon-08:00."),
			sizer=self.sizer, alto=60)
		self.lista = comun.lista(zc, self.panel, _("&Franjas:"), [(_("Hora"), 100), (_("Subida"), 140), (_("Bajada"), 140)],
			sizer=self.sizer, ayuda=_("Franjas del horario; elija una para cambiarla o quitarla."))
		self.hora = comun.campo(zc, self.panel, _("&Hora de inicio:"), wx.TextCtrl, "08:00", sizer=self.sizer,
			ayuda=_("Formato HH:MM, por ejemplo 08:00."))
		self.subida = comun.campo(zc, self.panel, _("&Subida en KiB/s (0 sin límite):"), wx.SpinCtrl, sizer=self.sizer,
			min=0, max=10_000_000, initial=0)
		self.bajada = comun.campo(zc, self.panel, _("&Bajada en KiB/s (0 sin límite):"), wx.SpinCtrl, sizer=self.sizer,
			min=0, max=10_000_000, initial=0)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		comun.boton(self.panel, _("Añadi&r la franja"), _("Añade una franja con los datos de los campos."), self.anadir, sizer=fila)
		comun.boton(self.panel, _("Ca&mbiar la franja"), _("Cambia la franja elegida por los datos de los campos."), self.cambiar, sizer=fila)
		comun.boton(self.panel, _("&Quitar la franja"), _("Quita la franja elegida."), self.quitar, sizer=fila)
		self.sizer.Add(fila, 0, wx.ALL, 4)
		self.botones(wx.OK | wx.CANCEL)
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._cargar())
		self._refrescar()
		self.terminar(self.lista)

	def _refrescar(self, seleccion: int = 0) -> None:
		self.franjas.sort(key=lambda f: f.hora)
		comun.llenar_lista(self.lista, [[f.hora, texto_limite(f.subida_kib), texto_limite(f.bajada_kib)] for f in self.franjas], seleccion)

	def _cargar(self) -> None:
		fila = comun.fila_actual(self.lista)
		if 0 <= fila < len(self.franjas):
			franja = self.franjas[fila]
			self.hora.SetValue(franja.hora)
			self.subida.SetValue(franja.subida_kib)
			self.bajada.SetValue(franja.bajada_kib)

	def _franja(self) -> Franja | None:
		hora = self.hora.GetValue().strip()
		coincide = _HORA.match(hora)
		if coincide is None or int(coincide.group("h")) > 23 or int(coincide.group("m")) > 59:
			comun.error(self.zc, _("La hora debe tener la forma HH:MM, entre 00:00 y 23:59."))
			self.hora.SetFocus()
			return None
		return Franja(hora, self.subida.GetValue(), self.bajada.GetValue())

	def anadir(self) -> None:
		franja = self._franja()
		if franja is None:
			return
		self.franjas = [f for f in self.franjas if f.hora != franja.hora] + [franja]
		self._refrescar([f.hora for f in sorted(self.franjas, key=lambda f: f.hora)].index(franja.hora))
		self.zc.anunciar(_("Franja añadida"), api.RESULTADO)

	def cambiar(self) -> None:
		fila = comun.fila_actual(self.lista)
		franja = self._franja()
		if franja is None or not 0 <= fila < len(self.franjas):
			return
		self.franjas[fila] = franja
		self._refrescar(fila)
		self.zc.anunciar(_("Franja cambiada"), api.RESULTADO)

	def quitar(self) -> None:
		fila = comun.fila_actual(self.lista)
		if 0 <= fila < len(self.franjas):
			del self.franjas[fila]
			self._refrescar(max(0, fila - 1))
			self.zc.anunciar(_("Franja quitada"), api.RESULTADO)

	def horario(self) -> str:
		return escribir_horario(self.franjas)
