# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Esquema de teclas (diseño 2.0, 10.7; orden ``esquema_teclas``).

Lista de esquemas (Norton, Total Commander, Far, Explorador) con su
descripción y las teclas que cambiarían (Orden, Tecla actual, Tecla del
esquema). «Aplicar el esquema» pide confirmación diciendo cuántas teclas
cambian (confirmación silenciable ``esquema_cambio``, 10.12); las teclas
personalizadas de la persona se conservan.
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import esquemas_teclas
from app.services.teclas import nombre_visible
from app.ui import anuncios, ordenes
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)

ORDEN = ("norton", "total_commander", "far", "explorador")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _etiqueta(id_orden: str) -> str:
	from app.ui.acciones.personalizar_pe import etiqueta

	return etiqueta(id_orden)


def _teclas(teclas) -> str:
	return ", ".join(nombre_visible(t) for t in teclas) if teclas else _("queda sin tecla")


def diferencias(actual: str, nuevo: str) -> list[esquemas_teclas.Diferencia]:
	fabrica = {o.id: tuple(o.teclas) for o in ordenes.CATALOGO_NUCLEO}
	fabrica.update({o.id: tuple(o.teclas) for o in ordenes.catalogo()})
	return esquemas_teclas.diferencias(fabrica, actual, nuevo)


def texto_confirmacion(nuevo: str, cambios: list[esquemas_teclas.Diferencia]) -> str:
	sin_tecla = [_etiqueta(d.orden) for d in cambios if not d.nuevas]
	texto = _("¿Aplicar el esquema {e}? Cambian {n} teclas.").format(e=esquemas_teclas.nombre(nuevo), n=len(cambios))
	if sin_tecla:
		texto += " " + _("Quedan sin tecla (siguen en los menús y en la paleta): {o}.").format(o=", ".join(sin_tecla))
	return texto + " " + _("Sus teclas personalizadas se conservan.")


class DialogoEsquema(f_comun.DialogoF):
	def __init__(self, padre: wx.Window | None, config) -> None:
		super().__init__(padre, _("Esquema de teclas"))
		self.config = config
		self.actual = str(config.obtener("teclado.esquema") or "norton")
		self.aplicado: str | None = None
		_e, self.lista = crear_campo(self.panel, _("Esq&uemas:"), wx.ListBox,
			choices=[esquemas_teclas.nombre(e) + (_(" (actual)") if e == self.actual else "") for e in ORDEN],
			size=self.FromDIP(wx.Size(320, 100)), sizer=self.sizer, ayuda=_("Elija un esquema: debajo se explica y se ven las teclas que cambian."))
		_d, self.descripcion = crear_campo(self.panel, _("&Descripción:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY,
			size=self.FromDIP(wx.Size(520, 70)), sizer=self.sizer, ayuda=_("Qué hace el esquema y de dónde salen sus teclas."))
		self.etiqueta_cambios = wx.StaticText(self.panel, label=_("&Teclas que cambian:"))
		self.cambios = ListaAccesible(self.panel, _("Teclas que cambian"),
			columnas=[(_("Orden"), self.FromDIP(240)), (_("Tecla actual"), self.FromDIP(150)), (_("Tecla del esquema"), self.FromDIP(160))])
		self.cambios.SetMinSize(self.FromDIP(wx.Size(560, 180)))
		self.cambios.SetHelpText(_("Cada orden que cambia de tecla con este esquema. «Queda sin tecla»: sigue en menús y paleta."))
		self.sizer.Add(self.etiqueta_cambios, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.cambios, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_aplicar = self.boton(_("&Aplicar el esquema..."), _("Aplica el esquema elegido; pide confirmación."), self.aplicar, fila)
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT)
		self.lista.Bind(wx.EVT_LISTBOX, lambda _e: self._describir())
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.aplicar())
		self.terminar(wx.CLOSE, foco=self.lista, id_escape=wx.ID_CLOSE)
		self.FindWindow(wx.ID_CLOSE).Bind(wx.EVT_BUTTON, lambda _e: self.cerrar(wx.ID_CLOSE))
		self.lista.SetSelection(ORDEN.index(self.actual) if self.actual in ORDEN else 0)
		self._describir()

	def elegido(self) -> str:
		indice = self.lista.GetSelection()
		return ORDEN[indice] if 0 <= indice < len(ORDEN) else "norton"

	def _describir(self) -> None:
		esquema = self.elegido()
		texto = esquemas_teclas.descripcion(esquema)
		fuente = esquemas_teclas.FUENTES.get(esquema)
		if fuente:
			texto += "\n" + _("Contrastado con: {f}.").format(f=fuente)
		self.descripcion.ChangeValue(texto)
		cambios = diferencias(self.actual, esquema)
		self.cambios.reemplazar_filas([[_etiqueta(d.orden), _teclas(d.actuales), _teclas(d.nuevas)] for d in cambios], conservar_foco=False)

	def aplicar(self) -> bool:
		esquema = self.elegido()
		if esquema == self.actual:
			anuncios.anunciar(_("El esquema {e} ya está aplicado").format(e=esquemas_teclas.nombre(esquema)), anuncios.RESULTADO)
			return False
		cambios = diferencias(self.actual, esquema)
		from app.services import confirmaciones

		if confirmaciones.debe_preguntar(self.config, "esquema_cambio"):
			eleccion, silenciar = elegir_con_casilla(self, texto_confirmacion(esquema, cambios), _("Esquema de teclas"),
				[_("&Aplicar"), _("&No aplicar")])
			if eleccion != 0:
				return False
			if silenciar:
				confirmaciones.silenciar(self.config, "esquema_cambio")
		self.config.establecer("teclado.esquema", esquema)
		self.actual = self.aplicado = esquema
		self.lista.Set([esquemas_teclas.nombre(e) + (_(" (actual)") if e == self.actual else "") for e in ORDEN])
		self.lista.SetSelection(ORDEN.index(esquema))
		self._describir()
		anuncios.anunciar(_("Esquema {e} aplicado: {n} teclas cambiadas").format(e=esquemas_teclas.nombre(esquema), n=len(cambios)),
			anuncios.RESULTADO)
		return True


def elegir_con_casilla(padre, mensaje: str, titulo: str, opciones: list[str]) -> tuple[int | None, bool]:
	"""La pregunta con «No volver a preguntar» (sustituible en las pruebas)."""
	from app.ui.accesibilidad import dialogos

	return dialogos.elegir_con_casilla(padre, mensaje, titulo, opciones)


def mostrar(padre: wx.Window | None, config) -> str | None:
	return f_comun.mostrar(DialogoEsquema(padre, config), lambda d: d.aplicado, aceptar=(wx.ID_CLOSE, wx.ID_OK, wx.ID_CANCEL))
