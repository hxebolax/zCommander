# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Teclas globales (diseño 2.0, 10.15). Sin wx.

Funcionan con zCommander en segundo plano (``RegisterHotKey`` sobre la ventana
principal), solo con ``teclado.globales_activas`` (desactivada de fábrica) y
solo para una lista blanca de órdenes: ``traer_al_frente``, ``ir_a_carpeta``,
``decir_operaciones``, ``sonidos_silenciar``, las macros (``macro:*``) y las
órdenes de complementos con ``tecla_global = true`` (campo ``tecla_global`` de
la orden en el catálogo). ``teclado.globales`` = ``{"id_orden": "Ctrl+Alt+Shift+Z"}``.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Mapping
from typing import Any

from app.services import teclas

LISTA_BLANCA = frozenset({"traer_al_frente", "ir_a_carpeta", "decir_operaciones", "sonidos_silenciar"})


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def permitida(id_orden: str, orden: Any = None) -> bool:
	"""Si la orden puede tener tecla global (lista blanca, macros o ``tecla_global`` del catálogo)."""
	if id_orden in LISTA_BLANCA or id_orden.startswith("macro:"):
		return True
	return bool(getattr(orden, "tecla_global", False))


def comprobar(tecla: str, id_orden: str, actuales: Mapping[str, str]) -> str:
	"""Tecla canónica válida para ``id_orden``, o ``ValueError`` con el motivo en español."""
	canonica = teclas.normalizar(tecla)
	partes = canonica.split("+")
	modificadores = set(partes[:-1])
	if teclas.es_reservada(canonica):
		raise ValueError(_("{t} está reservada por Windows").format(t=teclas.nombre_visible(canonica)))
	if not modificadores or modificadores <= {"Shift"}:
		raise ValueError(_("Una tecla global necesita Ctrl o Alt (se aconseja Ctrl+Alt+Mayús): sola, la usaría cualquier programa"))
	for otra, suya in actuales.items():
		if otra != id_orden and suya and teclas.normalizar(suya) == canonica:
			raise ValueError(_("{t} ya es la tecla global de otra orden").format(t=teclas.nombre_visible(canonica)))
	return canonica


def validas(globales: Mapping[str, str], orden_de: Callable[[str], Any]) -> dict[str, str]:
	"""Las de ``teclado.globales`` que se pueden registrar (orden permitida y existente, tecla válida)."""
	resultado: dict[str, str] = {}
	for id_orden, tecla in globales.items():
		orden = orden_de(id_orden)
		if not tecla or (orden is None and id_orden != "traer_al_frente") or not permitida(id_orden, orden):
			continue
		try:
			resultado[id_orden] = teclas.normalizar(str(tecla))
		except ValueError:
			continue
	return resultado
