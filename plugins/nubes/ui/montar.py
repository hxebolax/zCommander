# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Montar una cuenta como letra de unidad con WinFsp y ver las unidades montadas (diseño 2.0, 12.8).

Solo si WinFsp está instalado (lo instala la persona: necesita administrador).
Aviso: zCommander no debe ir elevado (la letra no se vería desde los programas
normales). La lista de montajes avisa antes de desmontar si quedan subidas
pendientes (``vfs/queue``).
"""

from __future__ import annotations

import string
from collections.abc import Callable
from typing import Any

import wx

from app.plugins import api

from . import comun

_ = api.traduccion("zc_nubes")[0]

MODOS = [("writes", _("Escrituras (recomendado para editar con cualquier programa)")), ("full", _("Completo (también lo leído)")),
	("minimal", _("Mínimo")), ("off", _("Sin caché (solo leer o escribir de corrido)"))]


def letras_libres() -> list[str]:
	import ctypes

	try:
		ocupadas = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
	except AttributeError:  # pragma: no cover - fuera de Windows
		ocupadas = 0
	return [f"{letra}:" for indice, letra in enumerate(string.ascii_uppercase) if indice >= 3 and not ocupadas & (1 << indice)]


class DialogoMontar(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, cuentas: list[tuple[str, str]], cuenta: str = "") -> None:
		super().__init__(zc, padre, _("Montar una cuenta como letra de unidad"))
		comun.texto_solo_lectura(zc, self.panel, _("A&viso:"), _("La unidad existe mientras zCommander esté abierto y se desmonta al "
			"salir. Si zCommander se ejecuta como administrador, los demás programas no verán la letra. Usa WinFsp, Windows File "
			"System Proxy, Copyright (C) Bill Zissimopoulos, https://github.com/winfsp/winfsp."), sizer=self.sizer, alto=80)
		self.cuenta = comun.elegir(zc, self.panel, _("C&uenta:"), cuentas, cuenta, sizer=self.sizer, ayuda=_("La cuenta que se monta."))
		self.letra = comun.elegir(zc, self.panel, _("&Letra:"), [("*", _("Automática"))] + [(l, l) for l in letras_libres()], "*",
			sizer=self.sizer, ayuda=_("Letra de unidad libre; automática elige la siguiente."))
		self.modo = comun.elegir(zc, self.panel, _("&Modo de caché:"), MODOS, "writes", sizer=self.sizer,
			ayuda=_("Con escrituras, lo que se guarda pasa por el disco y se sube después, con reintentos."))
		self.volumen = comun.campo(zc, self.panel, _("&Nombre del volumen:"), wx.TextCtrl, sizer=self.sizer,
			ayuda=_("Vacío: el nombre de la cuenta."))
		self.red = comun.casilla(self.panel, _("Como unidad de &red"), _("La monta como unidad de red en lugar de como disco."),
			sizer=self.sizer)
		self.botones(wx.OK | wx.CANCEL)
		self.terminar(self.cuenta)

	def datos(self) -> dict[str, Any]:
		return {"cuenta": comun.valor_elegido(self.cuenta), "letra": comun.valor_elegido(self.letra), "modo": comun.valor_elegido(self.modo),
			"volumen": self.volumen.GetValue().strip(), "red": self.red.GetValue()}


class DialogoMontajes(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, montajes: Callable[[], list[dict[str, str]]], desmontar: Callable[[str], None]) -> None:
		super().__init__(zc, padre, _("Unidades de nube montadas"))
		self._montajes = montajes
		self._desmontar = desmontar
		self.filas: list[dict[str, str]] = []
		self.lista = comun.lista(zc, self.panel, _("&Unidades montadas:"), [(_("Unidad"), 120), (_("Cuenta"), 320)], sizer=self.sizer,
			ayuda=_("Unidades de nube montadas por zCommander; Supr desmonta la elegida."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		comun.boton(self.panel, _("&Desmontar"), _("Desmonta la unidad elegida (avisa si quedan subidas pendientes)."), self.desmontar,
			sizer=fila)
		comun.boton(self.panel, _("&Actualizar"), _("Vuelve a leer la lista."), self.refrescar, sizer=fila)
		self.sizer.Add(fila, 0, wx.ALL, 4)
		cerrar = wx.Button(self.panel, wx.ID_CLOSE, _("&Cerrar"))
		cerrar.SetHelpText(_("Cierra la ventana."))
		self.sizer.Add(cerrar, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE) if self.IsModal() else self.Close(), id=wx.ID_CLOSE)
		self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla)
		self.refrescar()
		self.terminar(self.lista, wx.ID_CLOSE)

	def refrescar(self) -> None:
		self.filas = self._montajes()
		comun.llenar_lista(self.lista, [[m["punto"], m["fs"]] for m in self.filas] or [[_("Ninguna"), ""]])

	def _tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.desmontar()
			return
		evento.Skip()

	def desmontar(self) -> None:
		fila = comun.fila_actual(self.lista)
		if 0 <= fila < len(self.filas):
			self._desmontar(self.filas[fila]["punto"])
			self.refrescar()
