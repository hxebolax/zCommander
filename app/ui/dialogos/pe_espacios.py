# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Espacios de trabajo (diseño 2.0, 10.9; órdenes ``espacios_trabajo`` y ``espacio_guardar``).

Lista de espacios con Abrir (Intro), Guardar el actual como, Sustituir con el
actual, Renombrar y Eliminar. Abrir un espacio guarda antes la disposición
actual como «Anterior» (para volver), suena ``espacio.abierto`` y se anuncia
«Espacio de trabajo Proyecto web».
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import espacios
from app.ui import anuncios
from app.ui.dialogos import f_comun, pe_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def abrir_espacio(espacio: espacios.Espacio) -> bool:
	try:
		espacios.abrir_espacio(espacio)
	except Exception as error:  # noqa: BLE001 - NoAdmitido u otro: se dice a la persona
		log.exception("No se pudo abrir el espacio %s", espacio.nombre)
		anuncios.anunciar(_("No se pudo abrir el espacio de trabajo: {e}").format(e=getattr(error, "mensaje", None) or error),
			anuncios.ESENCIAL, sonido="aviso.error")
		return False
	anuncios.anunciar(_("Espacio de trabajo {n}").format(n=espacio.nombre), anuncios.RESULTADO, sonido="espacio.abierto")
	return True


class DialogoEspacios(pe_comun.DialogoListaPE):
	def __init__(self, padre: wx.Window | None) -> None:
		super().__init__(padre, _("Espacios de trabajo"), _("Es&pacios:"), [(_("Nombre"), 220), (_("Nota"), 300)],
			_("Disposiciones de pestañas y paneles guardadas. Intro abre la elegida."))
		self.lista_espacios = espacios.cargar()
		self.al_cerrar: list = []
		self.boton(_("&Abrir"), _("Abre el espacio elegido (antes se guarda la disposición actual como «Anterior»)."), self.abrir,
			self.botonera)
		self.boton(_("&Guardar el actual como..."), _("Guarda la disposición actual con un nombre nuevo."), self.guardar_como, self.botonera)
		self.boton(_("&Sustituir con el actual"), _("El espacio elegido pasa a tener la disposición actual."), self.sustituir,
			self.botonera)
		self.boton(_("&Renombrar..."), _("Cambia el nombre del espacio elegido."), self.renombrar, self.botonera)
		self.boton(_("E&liminar"), _("Borra el espacio elegido; pide confirmación."), self.eliminar, self.botonera)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.abrir())
		self.cerrar_lista()
		self.rellenar(0)

	def filas(self) -> list[list[str]]:
		return [[e.nombre, e.nota] for e in self.lista_espacios]

	def elegido(self) -> espacios.Espacio | None:
		i = self.indice()
		return self.lista_espacios[i] if 0 <= i < len(self.lista_espacios) else None

	def _guardar(self, foco: int) -> bool:
		ok = pe_comun.guardar_con_aviso(self, lambda: espacios.guardar(self.lista_espacios), self.titulo)
		self.rellenar(foco)
		self.lista.SetFocus()
		return ok

	def abrir(self) -> None:
		espacio = self.elegido()
		if espacio is None:
			return
		self.al_cerrar.append(lambda: abrir_espacio(espacio))
		self.cerrar(wx.ID_CLOSE)

	def guardar_como(self) -> None:
		nombre = f_comun.pedir(self, _("&Nombre del espacio de trabajo:"), _("Guardar el espacio de trabajo"))
		if not nombre or not nombre.strip():
			return
		existente = espacios.buscar(self.lista_espacios, nombre)
		if existente is not None and not f_comun.preguntar(self, _("Ya hay un espacio «{n}». ¿Sustituirlo?").format(n=existente.nombre),
				self.titulo):
			return
		try:
			espacio = espacios.capturar(nombre)
		except Exception as error:  # noqa: BLE001 - NoAdmitido sin ventana
			f_comun.avisar(self, str(getattr(error, "mensaje", None) or error), self.titulo)
			return
		indice = espacios.poner(self.lista_espacios, espacio)
		if self._guardar(indice):
			anuncios.anunciar(_("Espacio de trabajo guardado: {n}").format(n=espacio.nombre), anuncios.RESULTADO)

	def sustituir(self) -> None:
		actual = self.elegido()
		if actual is None:
			return
		if not f_comun.preguntar(self, _("¿Sustituir «{n}» con la disposición actual?").format(n=actual.nombre), self.titulo):
			return
		nuevo = espacios.capturar(actual.nombre, actual.nota, actual.con_cesta)
		indice = espacios.poner(self.lista_espacios, nuevo)
		if self._guardar(indice):
			anuncios.anunciar(_("Espacio de trabajo sustituido: {n}").format(n=actual.nombre), anuncios.RESULTADO)

	def renombrar(self) -> None:
		actual = self.elegido()
		if actual is None:
			return
		nombre = f_comun.pedir(self, _("&Nombre del espacio de trabajo:"), _("Renombrar el espacio"), actual.nombre)
		if not nombre or not nombre.strip() or nombre.strip() == actual.nombre:
			return
		otro = espacios.buscar(self.lista_espacios, nombre)
		if otro is not None and otro is not actual:
			f_comun.avisar(self, _("Ya hay un espacio «{n}»").format(n=otro.nombre), self.titulo)
			return
		actual.nombre = " ".join(nombre.split())
		self._guardar(self.lista_espacios.index(actual))

	def eliminar(self) -> None:
		actual = self.elegido()
		if actual is None:
			return
		if not f_comun.preguntar(self, _("¿Eliminar el espacio «{n}»?").format(n=actual.nombre), self.titulo, peligroso=True):
			return
		indice = self.lista_espacios.index(actual)
		self.lista_espacios.remove(actual)
		if self._guardar(indice):
			anuncios.anunciar(_("Espacio eliminado: {n}").format(n=actual.nombre), anuncios.RESULTADO)


def mostrar(padre: wx.Window | None, pe, abrir: str | None = None) -> None:
	"""Lista de espacios; con ``abrir`` (argumento de una macro) abre ese espacio sin mostrar la lista."""
	if abrir:
		espacio = espacios.buscar(espacios.cargar(), abrir)
		if espacio is None:
			anuncios.anunciar(_("No existe el espacio de trabajo «{n}»").format(n=abrir), anuncios.ESENCIAL, sonido="aviso.error")
			return
		abrir_espacio(espacio)
		return
	dialogo = DialogoEspacios(padre)
	acciones = f_comun.mostrar(dialogo, lambda d: list(d.al_cerrar), aceptar=(wx.ID_CLOSE, wx.ID_OK, wx.ID_CANCEL)) or []
	for accion in acciones:
		wx.CallAfter(accion)


def guardar_actual(padre: wx.Window | None) -> bool:
	"""Orden ``espacio_guardar``: pide el nombre y guarda la disposición actual."""
	nombre = f_comun.pedir(padre, _("&Nombre del espacio de trabajo:"), _("Guardar el espacio de trabajo"))
	if not nombre or not nombre.strip():
		return False
	try:
		espacios.guardar_actual(nombre)
	except Exception as error:  # noqa: BLE001 - NoAdmitido u OSError: se dice a la persona
		log.exception("No se pudo guardar el espacio de trabajo")
		f_comun.avisar(padre, _("No se pudo guardar el espacio de trabajo: {e}").format(e=getattr(error, "mensaje", None) or error),
			_("Espacios de trabajo"))
		return False
	anuncios.anunciar(_("Espacio de trabajo guardado: {n}").format(n=" ".join(nombre.split())), anuncios.RESULTADO)
	return True
