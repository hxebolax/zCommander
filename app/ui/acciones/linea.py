# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Línea de órdenes: insertar nombres y rutas, ejecutar, historial, vaciar, volver al panel."""

from __future__ import annotations

import builtins

from app.ui import anuncios


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _entrecomillar(texto: str) -> str:
	return f'"{texto}"' if " " in texto else texto


def insertar_nombre(ctx) -> None:
	entrada = ctx.activo.cursor()
	if entrada is not None and not entrada.es_superior:
		ctx.ventana.escribir_en_linea(_entrecomillar(entrada.nombre) + " ")


def insertar_ruta(ctx) -> None:
	entrada = ctx.activo.cursor()
	if entrada is not None and not entrada.es_superior:
		ctx.ventana.escribir_en_linea(_entrecomillar(entrada.ruta) + " ")


def ejecutar(ctx) -> None:
	if getattr(ctx, "argumento", None):
		# 2.0 (10.1): una macro trae el texto de la orden.
		ctx.ventana.linea.ChangeValue(str(ctx.argumento))
	ctx.ventana.ejecutar_linea()


def ejecutar_en_consola(ctx) -> None:
	ctx.ventana.ejecutar_linea(en_consola=True)


def historial_mover(ctx) -> None:
	texto = ctx.ventana.historial_ordenes.mover(int(ctx.param))
	if texto is None:
		anuncios.anunciar(_("Historial vacío"), anuncios.RESULTADO)
		return
	ctx.ventana.linea.ChangeValue(texto)
	ctx.ventana.linea.SetInsertionPointEnd()
	anuncios.anunciar(texto or _("Línea vacía"), anuncios.RESULTADO)


def vaciar(ctx) -> None:
	"""Escape en la línea de órdenes: borra lo escrito; vacía, detiene la orden en curso o vuelve al panel.

	Con la línea ya vacía y una orden en marcha, Escape la detiene y el foco se
	queda en la línea (el anuncio «Orden detenida» llega al terminar); otro
	Escape vuelve al panel.
	"""
	linea = ctx.ventana.linea
	if linea.GetValue():
		linea.ChangeValue("")
		ctx.ventana.historial_ordenes.reiniciar_cursor()
		anuncios.anunciar(_("Línea vacía"), anuncios.RESULTADO)
		return
	detener = getattr(ctx.ventana, "detener_orden", None)
	if callable(detener) and detener():
		return
	ctx.activo.enfocar()


def al_panel(ctx) -> None:
	ctx.activo.enfocar()
