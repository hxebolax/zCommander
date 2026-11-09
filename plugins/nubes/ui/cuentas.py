# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana «Cuentas de nube» (diseño 2.0, 12.7).

Lista con Nombre, Servicio, Motor, Estado y Espacio (estado en texto, nunca un
icono: 15.2) y los botones «&Abrir» (también Intro: lleva el panel activo a la
cuenta), «A&ñadir...», «&Propiedades...», «&Reconectar...», «&Eliminar...»
(también Supr; confirmación con el foco en Cancelar), «E&spacio» y «&Cerrar».
El espacio y el estado se piden en un hilo: la ventana nunca espera a la red.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

from app.plugins import api

from ..servicio import texto_estado
from . import comun

if TYPE_CHECKING:
	from .ordenes import Ordenes

_ = api.traduccion("zc_nubes")[0]

COLUMNAS = [(_("Nombre"), 220), (_("Servicio"), 160), (_("Motor"), 80), (_("Estado"), 140), (_("Espacio"), 220)]


class DialogoCuentas(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, ordenes: Ordenes) -> None:
		super().__init__(zc, padre, _("Cuentas de nube"))
		self.ordenes = ordenes
		self.nubes = ordenes.nubes
		self._espacios: dict[str, str] = {}
		self.lista = comun.lista(zc, self.panel, _("Cuen&tas de nube:"), COLUMNAS, sizer=self.sizer,
			ayuda=_("Cada cuenta es una unidad más del panel. Intro la abre en el panel activo; Supr la elimina."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_abrir = comun.boton(self.panel, _("&Abrir"), _("Lleva el panel activo a la cuenta elegida."), self.abrir, sizer=fila)
		comun.boton(self.panel, _("A&ñadir..."), _("Abre el asistente para añadir una cuenta de nube."), self.anadir, sizer=fila)
		self.boton_propiedades = comun.boton(self.panel, _("&Propiedades..."), _("Configuración propia de la cuenta elegida."),
			self.propiedades, sizer=fila)
		self.boton_reconectar = comun.boton(self.panel, _("&Reconectar..."),
			_("Vuelve a autorizar la cuenta (o a configurarla, si se restauró de una copia sin ella)."), self.reconectar, sizer=fila)
		self.boton_eliminar = comun.boton(self.panel, _("&Eliminar..."),
			_("Desconecta la cuenta, revoca su autorización si se puede y borra sus datos de acceso."), self.eliminar, sizer=fila)
		self.boton_espacio = comun.boton(self.panel, _("E&spacio"), _("Comprueba la cuenta y dice su espacio usado y libre."),
			self.espacio, sizer=fila)
		self.sizer.Add(fila, 0, wx.ALL, 4)
		cerrar = wx.Button(self.panel, wx.ID_CLOSE, _("&Cerrar"))
		cerrar.SetHelpText(_("Cierra la ventana."))
		self.sizer.Add(cerrar, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE) if self.IsModal() else self.Close(), id=wx.ID_CLOSE)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.abrir())
		self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla_lista)
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._habilitar())
		self.refrescar()
		self.terminar(self.lista, wx.ID_CLOSE)

	# Datos -------------------------------------------------------------------

	def cuentas(self) -> list:
		return self.nubes.cuentas.lista()

	def cuenta_elegida(self) -> Any | None:
		fila = comun.fila_actual(self.lista)
		cuentas = self.cuentas()
		return cuentas[fila] if 0 <= fila < len(cuentas) else None

	def refrescar(self, seleccion: str = "") -> None:
		cuentas = self.cuentas()
		filas = []
		elegida = 0
		for indice, cuenta in enumerate(cuentas):
			motor = _("WebDAV") if cuenta.motor == "webdav" else "rclone"
			filas.append([cuenta.nombre, self.nubes.nombre_servicio(cuenta), motor, texto_estado(self.nubes.estado(cuenta)),
				self._espacios.get(cuenta.id, _("Sin comprobar"))])
			if cuenta.id == seleccion:
				elegida = indice
		actual = comun.fila_actual(self.lista)
		comun.llenar_lista(self.lista, filas, elegida if seleccion else max(0, actual))
		self._habilitar()

	def _habilitar(self) -> None:
		hay = self.cuenta_elegida() is not None
		for boton in (self.boton_abrir, self.boton_propiedades, self.boton_reconectar, self.boton_eliminar, self.boton_espacio):
			boton.Enable(hay)

	def poner_espacio(self, id_cuenta: str, texto: str) -> None:
		self._espacios[id_cuenta] = texto
		if self:
			self.refrescar()

	# Acciones ----------------------------------------------------------------

	def _tecla_lista(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.eliminar()
			return
		evento.Skip()

	def abrir(self) -> None:
		cuenta = self.cuenta_elegida()
		if cuenta is None:
			return
		self.zc.abrir_ruta(cuenta.direccion)
		if self.IsModal():
			self.EndModal(wx.ID_OK)

	def anadir(self) -> None:
		nueva = self.ordenes.asistente(self)
		self.refrescar(nueva.id if nueva is not None else "")

	def propiedades(self) -> None:
		cuenta = self.cuenta_elegida()
		if cuenta is not None:
			self.ordenes.propiedades(self, cuenta)
			self.refrescar(cuenta.id)

	def reconectar(self) -> None:
		cuenta = self.cuenta_elegida()
		if cuenta is not None:
			self.ordenes.reconectar_cuenta(self, cuenta, al_terminar=lambda: self and self.refrescar(cuenta.id))

	def eliminar(self) -> None:
		cuenta = self.cuenta_elegida()
		if cuenta is None:
			return
		if not comun.confirmar(self.zc, _("¿Eliminar la cuenta {n}? Se desconecta, se revoca su autorización si el servicio lo "
				"permite y se borran sus datos de acceso. Los archivos de la nube no se tocan.").format(n=cuenta.nombre),
				_("Eliminar la cuenta"), peligroso=True):
			return
		self.ordenes.eliminar_cuenta(cuenta, al_terminar=lambda: self and self.refrescar())

	def espacio(self) -> None:
		cuenta = self.cuenta_elegida()
		if cuenta is not None:
			self.ordenes.espacio_de(cuenta, al_terminar=lambda texto: self and self.poner_espacio(cuenta.id, texto))
