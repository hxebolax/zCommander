# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Asistente de primer arranque (y desde Opciones): perfil, lector de pantalla y tema.

Páginas en un ``wx.Simplebook`` con Atrás, Siguiente y Terminar en español
(el ``wx.adv.Wizard`` pone sus botones con el idioma de wx y dibuja su propia
cabecera). Al cambiar de página el foco va al primer control de la nueva y se
anuncia «Paso 2 de 5: Perfil», porque el lector solo diría el control.

Nada se aplica hasta Terminar: cancelar a la mitad no deja la configuración a
medias. Lo elegido se escribe en un solo lote (``config.lote``).
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass

import wx

from app.services import perfiles
from app.ui import anuncios
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)

PERFILES = (perfiles.NOVATO, perfiles.INTERMEDIO, perfiles.AVANZADO)
TEMAS = ("sistema", "norton", "alto_contraste")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def nombre_tema(tema: str) -> str:
	from app.ui.dialogos.f_preferencias import nombre_opcion

	return nombre_opcion("vista.tema", tema)


@dataclass
class Eleccion:
	perfil: str = perfiles.INTERMEDIO
	lector: bool = True
	tema: str = "sistema"
	abrir_manual: bool = True


def aplicar(config, eleccion: Eleccion) -> int:
	"""Escribe lo elegido de una vez; devuelve cuántas preferencias del perfil cambiaron."""
	with config.lote():
		cambios = perfiles.aplicar_perfil(config, eleccion.perfil)
		if eleccion.lector:
			config.establecer_varias({"accesibilidad.anuncios": True, "accesibilidad.salida_voz": "automatica"})
		else:
			config.establecer("accesibilidad.anuncios", False)
		config.establecer("vista.tema", eleccion.tema)
		config.establecer("general.asistente_hecho", True)
	return cambios


class DialogoAsistente(f_comun.DialogoF):
	"""``eleccion`` queda con lo elegido al terminar."""

	def __init__(self, padre: wx.Window | None, config) -> None:
		super().__init__(padre, _("Asistente de zCommander"))
		self.config = config
		actual = perfiles.perfil_actual(config)
		self.eleccion = Eleccion(
			perfil=actual if actual in PERFILES else perfiles.INTERMEDIO,
			lector=bool(config.obtener("accesibilidad.anuncios")),
			tema=config.obtener("vista.tema"),
		)
		self.libro = wx.Simplebook(self.panel)
		self.titulos: list[str] = []
		self.primeros: list[wx.Window] = []
		self._pagina_bienvenida()
		self._pagina_perfil()
		self._pagina_lector()
		self._pagina_tema()
		self._pagina_final()
		self.sizer.Add(self.libro, 1, wx.EXPAND | wx.ALL, self.FromDIP(6))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_atras = self.boton(_("&Atrás"), _("Vuelve al paso anterior."), self.atras, fila)
		self.boton_siguiente = self.boton(_("&Siguiente"), _("Pasa al paso siguiente."), self.siguiente, fila)
		self.boton_terminar = self.boton(_("&Terminar"), _("Aplica lo elegido y cierra el asistente."), self.terminar_asistente, fila)
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT)
		self.terminar(wx.CANCEL, foco=self.primeros[0])
		self._mostrar(0, anunciar=False)

	# ── Páginas ──────────────────────────────────────────────────────────────

	def _nueva_pagina(self, titulo: str) -> tuple[wx.Panel, wx.BoxSizer]:
		pagina = wx.Panel(self.libro, name=titulo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		pagina.SetSizer(sizer)
		self.libro.AddPage(pagina, titulo)
		self.titulos.append(titulo)
		return pagina, sizer

	def _pagina_bienvenida(self) -> None:
		pagina, sizer = self._nueva_pagina(_("Bienvenida"))
		texto = _(
			"zCommander es un gestor de archivos de doble panel, como Norton Commander: a cada lado hay una carpeta "
			"y Tab cambia de lado. Copiar (F5) y mover (F6) llevan lo marcado del panel activo al otro.\n\n"
			"Este asistente le ayuda a elegir el perfil, si usa lector de pantalla y los colores. Todo se puede "
			"cambiar después en el menú Opciones. Pulse Siguiente para continuar."
		)
		_e, campo = crear_campo(pagina, _("&Qué es zCommander:"), wx.TextCtrl, value=texto, style=wx.TE_MULTILINE | wx.TE_READONLY,
			size=self.FromDIP(wx.Size(480, 160)), sizer=sizer)
		self.primeros.append(campo)

	def _pagina_perfil(self) -> None:
		pagina, sizer = self._nueva_pagina(_("Perfil"))
		_e, self.lista_perfil = crear_campo(pagina, _("&Perfil:"), wx.ListBox, choices=[perfiles.nombre_visible(p) for p in PERFILES],
			size=self.FromDIP(wx.Size(300, 80)), sizer=sizer, ayuda=_("Punto de partida de las preferencias; se cambian luego una a una."))
		self.lista_perfil.SetSelection(PERFILES.index(self.eleccion.perfil))
		_d, self.descripcion_perfil = crear_campo(pagina, _("&Descripción:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY,
			size=self.FromDIP(wx.Size(480, 90)), sizer=sizer)
		self.lista_perfil.Bind(wx.EVT_LISTBOX, lambda _e: self._describir_perfil())
		self._describir_perfil()
		self.primeros.append(self.lista_perfil)

	def _pagina_lector(self) -> None:
		pagina, sizer = self._nueva_pagina(_("Lector de pantalla"))
		self.casilla_lector = wx.CheckBox(pagina, label=_("&Uso un lector de pantalla (NVDA, JAWS o Narrador)"))
		self.casilla_lector.SetValue(self.eleccion.lector)
		self.casilla_lector.SetHelpText(_("Activa los anuncios de zCommander y la salida automática por su lector."))
		sizer.Add(self.casilla_lector, 0, wx.ALL, self.FromDIP(6))
		self.primeros.append(self.casilla_lector)

	def _pagina_tema(self) -> None:
		pagina, sizer = self._nueva_pagina(_("Colores"))
		_e, self.lista_tema = crear_campo(pagina, _("T&ema de colores:"), wx.ListBox, choices=[nombre_tema(t) for t in TEMAS],
			size=self.FromDIP(wx.Size(300, 80)), sizer=sizer, ayuda=_("Sistema usa los colores de Windows (y su alto contraste)."))
		self.lista_tema.SetSelection(TEMAS.index(self.eleccion.tema) if self.eleccion.tema in TEMAS else 0)
		self.primeros.append(self.lista_tema)

	def _pagina_final(self) -> None:
		pagina, sizer = self._nueva_pagina(_("Terminar"))
		_e, self.resumen = crear_campo(pagina, _("&Resumen:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY,
			size=self.FromDIP(wx.Size(480, 110)), sizer=sizer)
		self.casilla_manual = wx.CheckBox(pagina, label=_("Abrir el &manual al terminar"))
		self.casilla_manual.SetValue(True)
		self.casilla_manual.SetHelpText(_("Abre el manual de usuario (también con F1)."))
		sizer.Add(self.casilla_manual, 0, wx.ALL, self.FromDIP(6))
		self.primeros.append(self.resumen)

	def _describir_perfil(self) -> None:
		indice = self.lista_perfil.GetSelection()
		perfil = PERFILES[indice] if 0 <= indice < len(PERFILES) else perfiles.INTERMEDIO
		self.descripcion_perfil.SetValue(perfiles.descripcion(perfil))

	# ── Navegación ───────────────────────────────────────────────────────────

	def pagina(self) -> int:
		return self.libro.GetSelection()

	def _recoger(self) -> None:
		self.eleccion.perfil = PERFILES[max(0, self.lista_perfil.GetSelection())]
		self.eleccion.lector = self.casilla_lector.GetValue()
		self.eleccion.tema = TEMAS[max(0, self.lista_tema.GetSelection())]
		self.eleccion.abrir_manual = self.casilla_manual.GetValue()

	def _mostrar(self, indice: int, anunciar: bool = True) -> None:
		self.libro.SetSelection(indice)
		ultima = indice == self.libro.GetPageCount() - 1
		if ultima:
			self._recoger()
			lineas = [
				_("Perfil: {p}").format(p=perfiles.nombre_visible(self.eleccion.perfil)),
				_("Lector de pantalla: {r}").format(r=_("sí") if self.eleccion.lector else _("no")),
				_("Colores: {t}").format(t=nombre_tema(self.eleccion.tema)),
			]
			self.resumen.SetValue("\n".join(lineas))
		self.boton_atras.Enable(indice > 0)
		self.boton_siguiente.Enable(not ultima)
		(self.boton_terminar if ultima else self.boton_siguiente).SetDefault()
		self.primeros[indice].SetFocus()
		if anunciar:
			anuncios.anunciar(_("Paso {n} de {t}: {p}").format(n=indice + 1, t=self.libro.GetPageCount(), p=self.titulos[indice]),
				anuncios.RESULTADO)

	def siguiente(self) -> None:
		if self.pagina() < self.libro.GetPageCount() - 1:
			self._mostrar(self.pagina() + 1)

	def atras(self) -> None:
		if self.pagina() > 0:
			self._mostrar(self.pagina() - 1)

	def terminar_asistente(self) -> None:
		self._recoger()
		self.cerrar(wx.ID_OK)


def mostrar_asistente(padre: wx.Window | None, config) -> Eleccion | None:
	return f_comun.mostrar(DialogoAsistente(padre, config), lambda d: d.eleccion)
