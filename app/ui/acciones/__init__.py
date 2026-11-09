# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Manejadores de las órdenes del catálogo (``app/ui/ordenes.py``).

Cada función recibe un ``ContextoOrden`` y se ejecuta en el hilo de la
interfaz. Un módulo por dueño (sección 9.3 del diseño): los del núcleo
(navegacion, vista, archivos, marcas, linea, consulta, ayuda) y uno por bloque
(visor, busqueda_b, comprimidos_c, red_d, edicion_e, dialogos_f, windows_g).
"""

from __future__ import annotations

import builtins
from collections.abc import Callable

from app.ui import anuncios


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def provisional(etiqueta: str) -> Callable:
	"""Manejador provisional de un bloque aún sin programar (la prueba de provisionales lo detecta)."""

	def manejador(ctx) -> None:
		anuncios.anunciar(_("Todavía no disponible: {o}").format(o=etiqueta), anuncios.ESENCIAL)

	manejador.provisional = True  # type: ignore[attr-defined]
	return manejador


def estado_provisional(ctx) -> bool:
	return False


estado_provisional.provisional = True  # type: ignore[attr-defined]
