# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Paleta de órdenes (Ctrl+E): escribir lo que se quiere hacer y elegir la orden.

Al escribir («copiar») la lista se queda con las órdenes cuya etiqueta o
ayuda contienen todas las palabras, sin distinguir mayúsculas ni tildes; las
que lo tienen en la etiqueta van primero. Cada fila dice la orden, su tecla y
su ayuda, para aprender el atajo; al ejecutar se anuncia «Atajo: F5».

No se ofrecen las órdenes de la línea de órdenes (solo tienen sentido con el
foco en ella) ni la propia paleta.

2.0 (10.14, bloque PE): sin nada escrito, primero van las favoritas y después
las 10 más usadas (``app.services.paleta``), cada una con su tecla; Ctrl+D marca
o desmarca la orden elegida como favorita. Las macros con «En la paleta»
desmarcado no salen. ``elegir_orden(..., para_elegir=True)`` sirve para escoger
una orden sin ejecutarla (pasos de macro, Mis órdenes, barra de botones).
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Iterable

import wx

from app.services.teclas import MapaTeclas, nombre_visible
from app.ui import anuncios, ordenes
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)

EXCLUIDAS = frozenset({"paleta_ordenes"})


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def disponibles(catalogo: Iterable[ordenes.Orden] | None = None) -> list[ordenes.Orden]:
	"""Órdenes de la paleta: el catálogo VIVO (2.0, 14.1.1), con las de complementos y las macros.

	Ya no se enlaza ``ordenes.CATALOGO`` al importar: una orden de un complemento
	instalado después aparece sin reiniciar. Las de complementos con ``paleta = false``
	no salen.
	"""
	from app.plugins import registro

	if catalogo is None:
		catalogo = ordenes.catalogo()
	ocultas = {o.id for o in registro.ordenes() if not o.paleta} | _macros_fuera_de_la_paleta()
	return [o for o in catalogo if o.ambito != ordenes.LINEA and o.id not in EXCLUIDAS and o.id not in ocultas]


def _macros_fuera_de_la_paleta() -> set[str]:
	from app.ui.acciones import personalizar_pe

	pe = personalizar_pe.servicio()
	return {f"macro:{m.nombre}" for m in pe.macros if not m.paleta} if pe is not None else set()


def _paleta():
	from app.services import paleta

	return paleta.actual()


def etiqueta(orden: ordenes.Orden) -> str:
	return f_comun.texto_limpio(_(orden.etiqueta)).rstrip(".")


def filtrar_ordenes(texto: str, catalogo: Iterable[ordenes.Orden] | None = None) -> list[ordenes.Orden]:
	"""Órdenes cuya etiqueta o ayuda contienen todas las palabras de ``texto``; primero las de etiqueta."""
	candidatas = disponibles(ordenes.CATALOGO if catalogo is None else catalogo)
	palabras = f_comun.normalizar_busqueda(texto).split()
	if not palabras:
		alfabetico = sorted(candidatas, key=lambda o: f_comun.normalizar_busqueda(etiqueta(o)))
		por_id = {o.id: o for o in candidatas}
		primeras = [por_id[i] for i in _paleta().primero(por_id)]
		vistas = {o.id for o in primeras}
		return primeras + [o for o in alfabetico if o.id not in vistas]
	en_etiqueta, en_ayuda = [], []
	for orden in candidatas:
		titulo = f_comun.normalizar_busqueda(etiqueta(orden))
		completo = titulo + " " + f_comun.normalizar_busqueda(_(orden.ayuda))
		if all(p in titulo for p in palabras):
			# Las que EMPIEZAN por lo escrito, antes («Copiar...» antes que «Crear sumas de comprobación»).
			en_etiqueta.append((0 if titulo.startswith(palabras[0]) else 1, titulo, orden))
		elif all(p in completo for p in palabras):
			en_ayuda.append((titulo, orden))
	en_etiqueta.sort(key=lambda t: (t[0], t[1]))
	en_ayuda.sort(key=lambda t: t[0])
	return [o for _p, _t, o in en_etiqueta] + [o for _t, o in en_ayuda]


def texto_fila(orden: ordenes.Orden, mapa: MapaTeclas | None) -> str:
	tecla = mapa.primera_tecla(orden.id) if mapa is not None else (orden.teclas[0] if orden.teclas else "")
	partes = [etiqueta(orden)]
	if _paleta().es_favorita(orden.id):
		partes.insert(0, _("Favorita:"))
	if tecla:
		partes.append(f"({nombre_visible(tecla)})")
	return " ".join(partes) + ". " + _(orden.ayuda)


def anuncio_atajo(orden: ordenes.Orden, mapa: MapaTeclas | None) -> str:
	tecla = mapa.primera_tecla(orden.id) if mapa is not None else (orden.teclas[0] if orden.teclas else "")
	return _("Atajo: {t}").format(t=nombre_visible(tecla)) if tecla else _("Esta orden no tiene atajo; está en los menús y en la paleta.")


class DialogoPaleta(f_comun.DialogoF):
	"""``elegida`` queda con el id de la orden a ejecutar."""

	def __init__(self, padre: wx.Window | None, mapa: MapaTeclas | None, para_elegir: bool = False, titulo: str = "") -> None:
		super().__init__(padre, titulo or (_("Elegir una orden") if para_elegir else _("Paleta de órdenes")))
		self.mapa = mapa
		self.para_elegir = para_elegir
		self.elegida: str | None = None
		self.visibles: list[ordenes.Orden] = []
		_b, self.campo = crear_campo(self.panel, _("&Buscar:"), wx.TextCtrl, size=self.FromDIP(wx.Size(520, -1)), sizer=self.sizer,
			ayuda=_("Escriba lo que quiere hacer, por ejemplo «copiar». Flecha abajo pasa a la lista; Intro ejecuta la primera."))
		_l, self.lista = crear_campo(self.panel, _("Ó&rdenes:"), wx.ListBox, size=self.FromDIP(wx.Size(520, 280)), sizer=self.sizer,
			ayuda=_("Cada orden con su tecla y su ayuda. Intro la ejecuta. Sin nada escrito, primero van las favoritas "
				"y las más usadas. Control+D marca o desmarca la orden como favorita."))
		self.sizer.GetItem(self.lista).SetProportion(1)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		if para_elegir:
			self.boton_ejecutar = self.boton(_("&Elegir"), _("Cierra la lista con la orden elegida."), self.ejecutar, fila)
		else:
			self.boton_ejecutar = self.boton(_("&Ejecutar"), _("Cierra la paleta y ejecuta la orden elegida."), self.ejecutar, fila)
		self.boton(_("&Favorita"), _("Marca o desmarca la orden elegida como favorita (también Control+D)."), self.alternar_favorita, fila)
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT)
		self.campo.Bind(wx.EVT_TEXT, lambda _e: self.filtrar())
		self.campo.Bind(wx.EVT_KEY_DOWN, self._al_tecla_campo)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.ejecutar())
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla_dialogo)
		self.terminar(wx.CANCEL, foco=self.campo)
		self.boton_ejecutar.SetDefault()
		self.filtrar(anunciar=False)

	def filtrar(self, anunciar: bool = True) -> None:
		self.visibles = filtrar_ordenes(self.campo.GetValue())
		self.lista.Set([texto_fila(o, self.mapa) for o in self.visibles])
		if self.visibles:
			self.lista.SetSelection(0)
		if anunciar:
			if self.visibles:
				anuncios.anunciar(_("{n} órdenes; la primera: {o}").format(n=len(self.visibles), o=etiqueta(self.visibles[0])),
					anuncios.RESULTADO)
			else:
				anuncios.anunciar(_("Ninguna orden coincide"), anuncios.RESULTADO)

	def ejecutar(self) -> bool:
		indice = self.lista.GetSelection()
		if not 0 <= indice < len(self.visibles):
			anuncios.anunciar(_("Ninguna orden coincide"), anuncios.RESULTADO)
			return False
		self.elegida = self.visibles[indice].id
		self.cerrar(wx.ID_OK)
		return True

	def alternar_favorita(self) -> bool | None:
		"""Ctrl+D: marca o desmarca la orden elegida como favorita (y lo dice)."""
		indice = self.lista.GetSelection()
		if not 0 <= indice < len(self.visibles):
			return None
		orden = self.visibles[indice]
		queda = _paleta().alternar_favorita(orden.id)
		self.lista.SetString(indice, texto_fila(orden, self.mapa))
		anuncios.anunciar((_("{o}: favorita") if queda else _("{o}: ya no es favorita")).format(o=etiqueta(orden)), anuncios.RESULTADO)
		return queda

	def _al_tecla_dialogo(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (ord("D"), ord("d")) and evento.GetModifiers() == wx.MOD_CONTROL:
			self.alternar_favorita()
			return
		evento.Skip()

	def _al_tecla_campo(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DOWN and evento.GetModifiers() == wx.MOD_NONE and self.visibles:
			self.lista.SetFocus()
			return
		evento.Skip()


def elegir_orden(padre: wx.Window | None, mapa: MapaTeclas | None, para_elegir: bool = False, titulo: str = "") -> str | None:
	return f_comun.mostrar(DialogoPaleta(padre, mapa, para_elegir, titulo), lambda d: d.elegida)
