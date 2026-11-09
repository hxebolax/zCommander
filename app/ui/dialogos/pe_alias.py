# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Alias de la línea de órdenes (diseño 2.0, 10.8; orden ``alias``).

Lista (Nombre, Orden) con Nuevo, Editar, Eliminar y Probar. «Probar» muestra
la orden expandida con unos argumentos de prueba, sin ejecutarla. Cada cambio
se guarda al momento en ``alias.json``.
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import alias as servicio
from app.services.alias import Alias
from app.ui import anuncios
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun, pe_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoAlias(f_comun.DialogoF):
	"""Crear o cambiar un alias. ``alias`` queda con el resultado."""

	def __init__(self, padre: wx.Window | None, alias: Alias, existentes: list[Alias]) -> None:
		super().__init__(padre, _("Alias"))
		self.alias = alias
		self._anterior = alias.nombre
		self._existentes = existentes
		_n, self.nombre = crear_campo(self.panel, _("&Nombre:"), wx.TextCtrl, value=alias.nombre, size=self.FromDIP(wx.Size(200, -1)),
			sizer=self.sizer, expandir=False, ayuda=_("Una palabra: lo que se escribe en la línea de órdenes, por ejemplo «ll»."))
		_o, self.orden = crear_campo(self.panel, _("&Orden:"), wx.TextCtrl, value=alias.orden, size=self.FromDIP(wx.Size(480, -1)),
			sizer=self.sizer, ayuda=_("La orden que se ejecuta. %1 a %9 son los argumentos escritos tras el alias y %* todos; "
				"valen también %P, %N, %M y las demás variables. Si empieza por «zc », es una orden interna de zCommander."))
		self.terminar(wx.OK | wx.CANCEL, foco=self.nombre)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())

	def aceptar(self) -> bool:
		alias = Alias(self.nombre.GetValue().strip(), self.orden.GetValue().strip())
		try:
			servicio.validar(alias, self._existentes, self._anterior)
		except servicio.ErrorAlias as error:
			f_comun.avisar(self, str(error), self.titulo)
			self.nombre.SetFocus()
			return False
		self.alias = alias
		self.cerrar(wx.ID_OK)
		return True


class DialogoListaAlias(pe_comun.DialogoListaPE):
	def __init__(self, padre: wx.Window | None, pe) -> None:
		super().__init__(padre, _("Alias de la línea de órdenes"), _("&Alias:"), [(_("Nombre"), 140), (_("Orden"), 380)],
			_("Nombres cortos para órdenes largas. Izquierda y Derecha leen nombre y orden."))
		self.pe = pe
		self.boton(_("&Nuevo..."), _("Crea un alias."), self.nuevo, self.botonera)
		self.boton(_("Edi&tar..."), _("Cambia el alias elegido."), self.editar, self.botonera)
		self.boton(_("E&liminar"), _("Borra el alias elegido; pide confirmación."), self.eliminar, self.botonera)
		self.boton(_("&Probar..."), _("Muestra la orden expandida con unos argumentos de prueba, sin ejecutarla."), self.probar, self.botonera)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.editar())
		self.cerrar_lista()
		self.rellenar(0)

	def filas(self) -> list[list[str]]:
		return [[a.nombre, a.orden] for a in self.pe.alias]

	def elegido(self) -> Alias | None:
		i = self.indice()
		return self.pe.alias[i] if 0 <= i < len(self.pe.alias) else None

	def _guardar(self, lista: list[Alias], foco: int) -> bool:
		ok = pe_comun.guardar_con_aviso(self, lambda: self.pe.guardar_alias(lista), self.titulo)
		self.rellenar(foco)
		self.lista.SetFocus()
		return ok

	def nuevo(self) -> None:
		alias = f_comun.mostrar(DialogoAlias(self, Alias("", ""), self.pe.alias), lambda d: d.alias)
		if alias is not None and self._guardar([*self.pe.alias, alias], len(self.pe.alias)):
			anuncios.anunciar(_("Alias creado: {n}").format(n=alias.nombre), anuncios.RESULTADO)

	def editar(self) -> None:
		actual = self.elegido()
		if actual is None:
			return
		i = self.pe.alias.index(actual)
		alias = f_comun.mostrar(DialogoAlias(self, actual, self.pe.alias), lambda d: d.alias)
		if alias is None:
			return
		lista = list(self.pe.alias)
		lista[i] = alias
		if self._guardar(lista, i):
			anuncios.anunciar(_("Alias guardado: {n}").format(n=alias.nombre), anuncios.RESULTADO)

	def eliminar(self) -> None:
		actual = self.elegido()
		if actual is None:
			return
		if not f_comun.preguntar(self, _("¿Eliminar el alias «{n}»?").format(n=actual.nombre), self.titulo, peligroso=True):
			return
		i = self.pe.alias.index(actual)
		if self._guardar([a for a in self.pe.alias if a is not actual], i):
			anuncios.anunciar(_("Alias eliminado: {n}").format(n=actual.nombre), anuncios.RESULTADO)

	def probar(self) -> str | None:
		actual = self.elegido()
		if actual is None:
			return None
		argumentos = f_comun.pedir(self, _("&Argumentos de prueba (separados por espacios):"), _("Probar el alias"), "")
		if argumentos is None:
			return None
		_nombre, partes = servicio.separar(f"{actual.nombre} {argumentos}")
		from app.ui.acciones.personalizar_pe import valores_de

		try:
			texto = servicio.vista_previa(actual, partes, valores_de(self.pe.ventana))
		except ValueError as error:
			texto = _("No se puede expandir: {e}").format(e=error)
		f_comun.avisar(self, _("Se ejecutaría: {t}").format(t=texto), _("Probar el alias"))
		return texto


def mostrar(padre: wx.Window | None, pe) -> None:
	f_comun.mostrar(DialogoListaAlias(padre, pe), aceptar=(wx.ID_CLOSE, wx.ID_OK, wx.ID_CANCEL))
