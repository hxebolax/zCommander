# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Vistas, orden, filtros, ocultos, lados y pestañas."""

from __future__ import annotations

import builtins
import logging

from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


_NOMBRES_VISTA = {
	"completa": "Vista completa", "breve": "Vista breve", "informacion": "Información", "arbol": "Árbol", "rapida": "Vista rápida",
}
_NOMBRES_ORDEN = {
	"nombre": "nombre", "extension": "extensión", "fecha": "fecha", "tamano": "tamaño", "tipo": "tipo", "sin_orden": "sin ordenar",
}


def _panel_vista(ctx):
	"""Información, Árbol y Vista rápida con el teclado van al lado PASIVO (como Norton)."""
	if ctx.lado_objetivo is None and ctx.param in ("informacion", "arbol", "rapida"):
		return ctx.pasivo
	return ctx.objetivo


def vista(ctx) -> None:
	panel = _panel_vista(ctx)
	destino = ctx.param
	if panel.vista == destino and destino not in ("completa", "breve"):
		panel.vista_anterior()
		anuncios.anunciar(_(_NOMBRES_VISTA.get(panel.vista, panel.vista)), anuncios.RESULTADO)
		return
	panel.aplicar_vista(destino)
	anuncios.anunciar(_(_NOMBRES_VISTA[destino]), anuncios.RESULTADO)
	if destino in ("informacion", "rapida"):
		otro = ctx.otro(panel)
		ctx.ventana.panel_cambio_cursor(otro)
	elif destino == "arbol":
		otro = ctx.otro(panel)
		vista_arbol = panel.vista_actual()
		if vista_arbol is not None and otro.ruta:
			vista_arbol.cambiar_proveedor(otro.proveedor, otro.proveedor.raiz(otro.ruta))
			vista_arbol.ir_a(otro.ruta)


def es_vista(ctx) -> bool:
	return _panel_vista(ctx).vista == ctx.param


def ordenar(ctx) -> None:
	panel = ctx.objetivo
	panel.aplicar_orden(ctx.param)
	texto = _("Orden por {c}").format(c=_(_NOMBRES_ORDEN[ctx.param]))
	if panel.orden_inverso:
		texto += _(", inverso")
	anuncios.anunciar(texto, anuncios.RESULTADO)


def _orden_visible(panel) -> tuple[str, bool]:
	"""El orden que se ve (2.0: el preferido del proveedor, como en ocupación o la papelera, si lo hay)."""
	efectivo = getattr(panel, "orden_efectivo", None)
	return efectivo() if callable(efectivo) else (panel.criterio_orden, panel.orden_inverso)


def es_orden(ctx) -> bool:
	return _orden_visible(ctx.objetivo)[0] == ctx.param


def orden_inverso(ctx) -> None:
	panel = ctx.objetivo
	criterio, inverso = _orden_visible(panel)
	panel.aplicar_orden(criterio, not inverso)
	anuncios.anunciar(_("Orden inverso") if panel.orden_inverso else _("Orden normal"), anuncios.RESULTADO)


def es_inverso(ctx) -> bool:
	return _orden_visible(ctx.objetivo)[1]


def carpetas_primero(ctx) -> None:
	nuevo = not ctx.config.obtener("paneles.carpetas_primero")
	ctx.config.establecer("paneles.carpetas_primero", nuevo)
	anuncios.anunciar(_("Carpetas al principio") if nuevo else _("Carpetas mezcladas con los archivos"), anuncios.RESULTADO)


def es_carpetas_primero(ctx) -> bool:
	return bool(ctx.config.obtener("paneles.carpetas_primero"))


def filtro(ctx) -> None:
	from app.ui.dialogos.nombre import pedir_patron

	panel = ctx.objetivo
	if getattr(ctx, "argumento", None) is not None:
		patron = str(ctx.argumento)  # 2.0 (10.1): una macro trae el patrón
	else:
		patron = pedir_patron(ctx.ventana, _("Filtro"), _("&Mostrar solo los que coinciden con:"), [panel.filtro or "*.*"])
		if patron is None:
			return
		try:
			ctx.servicio("grabador").anotar_argumento(patron)
		except (KeyError, AttributeError):
			log.debug("Sin grabador de macros (ventana de prueba)", exc_info=True)
	panel.aplicar_filtro("" if patron.strip() in ("", "*", "*.*") else patron)
	anuncios.anunciar(_("Filtro: {f}").format(f=panel.filtro) if panel.filtro else _("Sin filtro"), anuncios.RESULTADO)


def filtro_rapido(ctx) -> None:
	ctx.activo.mostrar_filtro_rapido()


def quitar_filtro(ctx) -> None:
	panel = ctx.objetivo
	panel.aplicar_filtro("")
	if panel.filtro_rapido:
		panel.quitar_filtro_rapido()
	anuncios.anunciar(_("Sin filtro"), anuncios.RESULTADO)


def mostrar_ocultos(ctx) -> None:
	nuevo = not ctx.config.obtener("paneles.mostrar_ocultos")
	ctx.config.establecer("paneles.mostrar_ocultos", nuevo)
	anuncios.anunciar(_("Se muestran los ocultos") if nuevo else _("Ocultos escondidos"), anuncios.RESULTADO)


def es_mostrar_ocultos(ctx) -> bool:
	return bool(ctx.config.obtener("paneles.mostrar_ocultos"))


def busqueda_rapida(ctx) -> None:
	from app.ui.accesibilidad import dialogos

	texto = dialogos.pedir_texto(ctx.ventana, _("&Buscar:"), _("Búsqueda rápida"))
	if texto:
		panel = ctx.activo
		panel._busqueda = ""  # noqa: SLF001 - búsqueda explícita: empieza de cero
		for caracter in texto:
			panel.buscar_letra(caracter)


def mostrar_lado(ctx) -> None:
	lado = ctx.param or ctx.lado_objetivo or ctx.activo.lado
	ventana = ctx.ventana
	divisor = ventana.divisor
	panel_lado = ventana.lado(lado)
	otro = ventana.lado("derecho" if lado == "izquierdo" else "izquierdo")
	if divisor.IsSplit():
		divisor.Unsplit(panel_lado)
		anuncios.anunciar(_("Lado {l} oculto").format(l=_(lado)), anuncios.RESULTADO)
		otro.panel_actual().enfocar()
	else:
		panel_lado.Show()
		ventana._dividir()  # noqa: SLF001 - el reparto de los lados es de la ventana
		anuncios.anunciar(_("Lado {l} visible").format(l=_(lado)), anuncios.RESULTADO)


def mostrar_paneles(ctx) -> None:
	ctx.ventana.alternar_paneles()


def panel_pasivo(ctx) -> None:
	ctx.param = ""
	ctx.lado_objetivo = ctx.pasivo.lado
	mostrar_lado(ctx)


def pestana_nueva(ctx) -> None:
	# 2.0 (10.1): con argumento, la pestaña nueva va a esa carpeta.
	ruta = str(ctx.argumento) if getattr(ctx, "argumento", None) else None
	ctx.ventana.lado(ctx.objetivo.lado).nueva_pestana(ruta=ruta)


def pestana_cerrar(ctx) -> None:
	ctx.ventana.lado(ctx.objetivo.lado).cerrar_pestana()


def pestana_cerrar_otras(ctx) -> None:
	ctx.ventana.lado(ctx.objetivo.lado).cerrar_otras()


def pestana_mover(ctx) -> None:
	ctx.ventana.lado(ctx.objetivo.lado).mover(int(ctx.param))


def pestana_numero(ctx) -> None:
	ctx.ventana.lado(ctx.activo.lado).ir_a_numero(int(ctx.param))


def pestana_bloquear(ctx) -> None:
	panel = ctx.objetivo
	panel.bloqueada = not panel.bloqueada
	panel._actualizar_etiqueta()  # noqa: SLF001 - el título de la pestaña cambia con el bloqueo
	anuncios.anunciar(_("Pestaña bloqueada") if panel.bloqueada else _("Pestaña desbloqueada"), anuncios.RESULTADO)


def es_pestana_bloqueada(ctx) -> bool:
	return ctx.objetivo.bloqueada


def lista_pestanas(ctx) -> None:
	from app.ui.accesibilidad import dialogos

	lado = ctx.ventana.lado(ctx.objetivo.lado)
	titulos = [f"&{i + 1} {lado.cuaderno.GetPageText(i)}" if i < 9 else lado.cuaderno.GetPageText(i)
		for i in range(lado.cuaderno.GetPageCount())]
	eleccion = dialogos.elegir_opcion(ctx.ventana, _("Elija una pestaña"), _("Pestañas"), titulos)
	if eleccion is not None:
		lado.cuaderno.SetSelection(eleccion)
