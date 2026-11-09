# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque SO: sonidos (diseño 2.0, 4.5, 4.7 y 4.9).

- ``sonidos_silenciar`` (Ctrl+F11, también tecla global): activa o desactiva
  todos los sonidos y lo anuncia; ``es_silenciado`` es el estado de su casilla.
- ``sonidos_volumen_subir`` y ``sonidos_volumen_bajar``: de 10 en 10, con
  anuncio y una muestra al volumen nuevo.
- ``sonidos_paquetes``: el gestor y asistente de paquetes; con una ruta como
  argumento (Intro sobre un ``.zcsonidos``) ofrece importarla.
- ``mapa_sonidos``: Ayuda → «Mapa de sonidos...».
- ``instalar``: se asegura de que el reproductor es el motor de 4.4.
"""

from __future__ import annotations

import builtins
import logging
from pathlib import Path

from app.ui import anuncios
from app.ui import sonidos as sonidos_ui

log = logging.getLogger(__name__)

PASO_VOLUMEN = 10


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def es_silenciado(ctx) -> bool:
	"""Casilla «Silenciar los sonidos»: marcada si los sonidos están desactivados."""
	return not bool(ctx.config.obtener("sonidos.activos"))


def sonidos_silenciar(ctx) -> None:
	activar = not bool(ctx.config.obtener("sonidos.activos"))
	ctx.config.establecer("sonidos.activos", activar)
	if activar:
		anuncios.anunciar(_("Sonidos activados"), anuncios.RESULTADO)
		# 4.5: al activarlos suena «Información» (aunque ese evento esté desactivado), para confirmarlo de oído.
		sonidos_ui.probar("aviso.informacion")
	else:
		anuncios.anunciar(_("Sonidos desactivados"), anuncios.RESULTADO)


def _cambiar_volumen(ctx, diferencia: int) -> None:
	anterior = int(ctx.config.obtener("sonidos.volumen"))
	nuevo = max(0, min(100, anterior + diferencia))
	if nuevo != anterior:
		ctx.config.establecer_diferido("sonidos.volumen", nuevo)
	anuncios.anunciar(_("Volumen de los sonidos: {v}").format(v=nuevo), anuncios.RESULTADO)
	if nuevo > 0 and ctx.config.obtener("sonidos.activos"):
		# Una muestra al volumen nuevo, para oír cómo queda (aunque el evento esté desactivado).
		sonidos_ui.probar("aviso.informacion", volumen=nuevo)


def sonidos_volumen_subir(ctx) -> None:
	_cambiar_volumen(ctx, PASO_VOLUMEN)


def sonidos_volumen_bajar(ctx) -> None:
	_cambiar_volumen(ctx, -PASO_VOLUMEN)


def sonidos_paquetes(ctx) -> None:
	from app.ui.dialogos import so_paquetes

	ruta = ctx.argumento
	if ruta:
		so_paquetes.importar_con_pregunta(ctx.ventana, ctx.config, Path(str(ruta)))
		return
	so_paquetes.abrir(ctx.ventana, ctx.config)


def mapa_sonidos(ctx) -> None:
	from app.ui.dialogos import so_mapa

	so_mapa.abrir(ctx.ventana, ctx.config)


def instalar(ventana) -> None:
	"""Enganche de SO al arrancar (14.9): el reproductor del servicio es el motor de 4.4.

	La ventana ya crea el motor con ``app.ui.sonidos.iniciar``; esto solo lo
	pone si otro código dejó un reproductor distinto. El aviso inicial de 4.5 lo
	da la ventana tras mostrarse (paso 11 de 14.8).
	"""
	sonidos_ui.asegurar_motor(ventana.config)
