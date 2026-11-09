# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Marcar: con teclas, por patrón, por extensión, todo, invertir, guardar, cargar y restaurar."""

from __future__ import annotations

import builtins
import logging

from app.services import formato, seleccion
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


_historial_patrones: list[str] = ["*.*"]


def _anunciar_total(panel) -> None:
	marcadas = panel.marcadas()
	bytes_ = sum(e.tamano for e in marcadas if e.tamano > 0)
	if marcadas:
		texto = _("Marcados {n}, {b}").format(n=len(marcadas), b=formato.tamano_legible(bytes_))
	else:
		texto = _("Sin marcas")
	anuncios.anunciar(texto, anuncios.RESULTADO)


def marcar(ctx) -> None:
	"""Insert o Espacio: alterna, anuncia sin interrumpir y baja."""
	lista = ctx.activo.lista_archivos
	indice = lista.cursor_indice()
	entrada = lista.entrada(indice)
	if entrada is None:
		return
	estado = lista.alternar(indice)
	if estado is not None:
		anuncios.anunciar((_("Marcado: {n}") if estado else _("Desmarcado: {n}")).format(n=entrada.nombre), anuncios.NORMAL,
			interrumpir=False, sonido="marca.marcar" if estado else "marca.desmarcar")
	if ctx.config.obtener("paneles.mover_tras_marcar"):
		lista.mover_cursor(indice + 1)


def marcar_sin_mover(ctx) -> None:
	lista = ctx.activo.lista_archivos
	indice = lista.cursor_indice()
	entrada = lista.entrada(indice)
	estado = lista.alternar(indice)
	if estado is not None and entrada is not None:
		anuncios.anunciar((_("Marcado: {n}") if estado else _("Desmarcado: {n}")).format(n=entrada.nombre), anuncios.NORMAL,
			sonido="marca.marcar" if estado else "marca.desmarcar")


def marcar_rango(ctx) -> None:
	"""Mayús+flechas, Re Pág, Av Pág, Inicio y Fin: marcan desde el cursor hasta la nueva posición."""
	lista = ctx.activo.lista_archivos
	actual = max(0, lista.cursor_indice())
	total = len(lista.entradas())
	pagina = lista.filas_por_pagina()
	destino = {
		"-1": actual - 1, "1": actual + 1, "-pagina": actual - pagina, "pagina": actual + pagina, "inicio": 0, "fin": total - 1,
	}[ctx.param]
	destino = max(0, min(destino, total - 1))
	if ctx.param in ("-1", "1"):
		lista.marcar_indices([actual], True)
	else:
		lista.marcar_rango(actual, destino, True)
	lista.mover_cursor(destino)
	if ctx.param not in ("-1", "1"):
		_anunciar_total(ctx.activo)


def _patron(ctx, titulo: str) -> str | None:
	from app.ui.dialogos.nombre import pedir_patron

	if getattr(ctx, "argumento", None):
		return str(ctx.argumento)  # 2.0 (10.1): una macro trae el patrón
	patron = pedir_patron(ctx.ventana, titulo, _("&Patrón (por ejemplo *.txt;*.md, exclusiones tras |):"), list(_historial_patrones))
	if patron:
		try:
			ctx.servicio("grabador").anotar_argumento(patron)
		except (KeyError, AttributeError):
			log.debug("Sin grabador de macros (ventana de prueba)", exc_info=True)
		if patron in _historial_patrones:
			_historial_patrones.remove(patron)
		_historial_patrones.insert(0, patron)
		del _historial_patrones[20:]
	return patron


def _aplica(ctx, entrada) -> bool:
	return not entrada.es_carpeta or bool(ctx.config.obtener("paneles.patrones_en_carpetas"))


def marcar_patron(ctx) -> None:
	patron = _patron(ctx, _("Marcar por patrón"))
	if not patron:
		return
	analizado = seleccion.Patron.analizar(patron)
	ctx.activo.marcar(lambda e: _aplica(ctx, e) and analizado.coincide(e.nombre), True)
	anuncios.anunciar("", anuncios.DETALLE, sonido="marca.grupo")
	_anunciar_total(ctx.activo)


def desmarcar_patron(ctx) -> None:
	patron = _patron(ctx, _("Desmarcar por patrón"))
	if not patron:
		return
	analizado = seleccion.Patron.analizar(patron)
	ctx.activo.marcar(lambda e: analizado.coincide(e.nombre), False)
	_anunciar_total(ctx.activo)


def invertir(ctx) -> None:
	panel = ctx.activo
	lista = panel.lista_archivos
	marcadas = lista.claves_marcadas()
	from app.ui.lista_archivos import clave

	nuevas = {clave(e) for e in panel.entradas() if not e.es_superior and not e.es_carpeta and clave(e) not in marcadas}
	lista.poner_marcas(nuevas)
	_anunciar_total(panel)


def marcar_todo(ctx) -> None:
	ctx.activo.marcar(lambda e: True, True)
	_anunciar_total(ctx.activo)


def desmarcar_todo(ctx) -> None:
	ctx.activo.desmarcar_todo()
	anuncios.anunciar(_("Sin marcas"), anuncios.RESULTADO)


def extension(ctx) -> None:
	panel = ctx.activo
	entrada = panel.cursor()
	if entrada is None or entrada.es_carpeta or entrada.es_superior:
		anuncios.anunciar(_("El cursor no está en un archivo"), anuncios.RESULTADO)
		return
	ext = entrada.extension
	panel.marcar(lambda e: not e.es_carpeta and e.extension == ext, ctx.param == "marcar")
	_anunciar_total(panel)


def restaurar(ctx) -> None:
	n = ctx.activo.restaurar_marcas()
	anuncios.anunciar(_("Marcas restauradas: {n}").format(n=n), anuncios.RESULTADO)


def guardar(ctx) -> None:
	import wx

	marcadas = ctx.activo.marcadas()
	if not marcadas:
		anuncios.anunciar(_("No hay marcas"), anuncios.RESULTADO)
		return
	with wx.FileDialog(ctx.ventana, _("Guardar las marcas"), wildcard=_("Texto (*.txt)|*.txt"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
		if dialogo.ShowModal() != wx.ID_OK:
			return
		ruta = dialogo.GetPath()
	with open(ruta, "w", encoding="utf-8") as salida:
		salida.write("\n".join(e.nombre for e in marcadas) + "\n")
	anuncios.anunciar(_("Marcas guardadas"), anuncios.RESULTADO)


def cargar(ctx) -> None:
	import wx

	with wx.FileDialog(ctx.ventana, _("Cargar las marcas"), wildcard=_("Texto (*.txt)|*.txt|Todos (*.*)|*.*"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialogo:
		if dialogo.ShowModal() != wx.ID_OK:
			return
		ruta = dialogo.GetPath()
	with open(ruta, encoding="utf-8-sig", errors="replace") as entrada:
		nombres = {linea.strip().casefold() for linea in entrada if linea.strip()}
	ctx.activo.marcar(lambda e: e.nombre.casefold() in nombres, True)
	_anunciar_total(ctx.activo)
