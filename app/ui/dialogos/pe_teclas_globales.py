# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Teclas globales (diseño 2.0, 10.15): botón «Teclas globales...» de la página Personalización.

Lista (Orden, Tecla global) de las órdenes que admiten tecla global: Traer
zCommander al frente, Ir a la carpeta, Decir las operaciones, Silenciar los
sonidos, las macros y las órdenes de complementos con ``tecla_global``.
«Cambiar» captura la tecla (se aconseja Ctrl+Alt+Mayús o Win+Alt) y «Quitar»
la borra. Se guarda al momento en ``teclado.globales``; solo funcionan con
«Activar las teclas globales» marcada (``teclado.globales_activas``).
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

import wx

from app.services import teclas_globales
from app.services.teclas import nombre_visible
from app.ui import anuncios, ordenes
from app.ui.dialogos import f_comun, pe_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _etiqueta(id_orden: str) -> str:
	from app.ui.acciones.personalizar_pe import etiqueta

	return etiqueta(id_orden)


def candidatas() -> list[str]:
	"""Órdenes que admiten tecla global, en orden: lista blanca, macros y complementos."""
	resultado = [i for i in ("traer_al_frente", "ir_a_carpeta", "decir_operaciones", "sonidos_silenciar") if i in ordenes.POR_ID]
	resultado += [o.id for o in ordenes.catalogo() if o.id.startswith("macro:")]
	resultado += [o.id for o in ordenes.catalogo() if o.tecla_global and o.id not in resultado and not o.id.startswith("macro:")]
	return resultado


def configuracion_de(padre: wx.Window | None) -> Any:
	actual = padre
	while actual is not None:
		config = getattr(actual, "config", None) or getattr(actual, "_config", None)
		if config is not None:
			return config
		actual = actual.GetParent()
	from app.core.configuracion import obtener_configuracion

	return obtener_configuracion()


class DialogoTeclasGlobales(pe_comun.DialogoListaPE):
	def __init__(self, padre: wx.Window | None, config: Any) -> None:
		super().__init__(padre, _("Teclas globales"), _("&Órdenes:"), [(_("Orden"), 280), (_("Tecla global"), 200)],
			_("Teclas que funcionan con zCommander en segundo plano. Intro cambia la tecla de la orden elegida."))
		self.config = config
		self.ids = candidatas()
		self.boton(_("Ca&mbiar..."), _("Pulse la tecla global; se aconseja Ctrl+Alt+Mayús más una letra."), self.cambiar, self.botonera)
		self.boton(_("&Quitar"), _("Quita la tecla global de la orden elegida."), self.quitar, self.botonera)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.cambiar())
		self.cerrar_lista()
		self.rellenar(0)
		if not config.obtener("teclado.globales_activas"):
			self.lista.SetHelpText(self.lista.GetHelpText() + " " + _("Ahora están desactivadas: márquelas en la página Personalización."))

	@property
	def globales(self) -> dict[str, str]:
		return dict(self.config.obtener("teclado.globales") or {})

	def filas(self) -> list[list[str]]:
		globales = self.globales
		return [[_etiqueta(i), nombre_visible(globales[i]) if globales.get(i) else _("(sin tecla)")] for i in self.ids]

	def elegida(self) -> str | None:
		i = self.indice()
		return self.ids[i] if 0 <= i < len(self.ids) else None

	def poner(self, id_orden: str, tecla: str) -> bool:
		globales = self.globales
		try:
			canonica = teclas_globales.comprobar(tecla, id_orden, globales)
		except ValueError as error:
			f_comun.avisar(self, str(error), self.titulo)
			return False
		globales[id_orden] = canonica
		self.config.establecer("teclado.globales", globales)
		self.rellenar(self.ids.index(id_orden))
		anuncios.anunciar(_("{o}: {t}").format(o=_etiqueta(id_orden), t=nombre_visible(canonica)), anuncios.RESULTADO)
		return True

	def cambiar(self) -> None:
		id_orden = self.elegida()
		if id_orden is None:
			return
		from app.ui.dialogos import f_mapa_teclas

		tecla = f_mapa_teclas.capturar_tecla(self, id_orden)
		if tecla:
			self.poner(id_orden, tecla)
		self.lista.SetFocus()

	def quitar(self) -> None:
		id_orden = self.elegida()
		if id_orden is None:
			return
		globales = self.globales
		if globales.pop(id_orden, None) is None:
			return
		self.config.establecer("teclado.globales", globales)
		self.rellenar(self.ids.index(id_orden))
		anuncios.anunciar(_("{o}: sin tecla global").format(o=_etiqueta(id_orden)), anuncios.RESULTADO)


def abrir(padre: wx.Window) -> None:
	"""Botón «Teclas globales...» de la página Personalización (``BOTONES_PAGINA``)."""
	f_comun.mostrar(DialogoTeclasGlobales(padre, configuracion_de(padre)), aceptar=(wx.ID_CLOSE, wx.ID_OK, wx.ID_CANCEL))
