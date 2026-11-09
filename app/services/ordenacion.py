# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Orden de las entradas de un panel.

Claves precalculadas para que ordenar 100 000 entradas sea rápido: se hace un
único ``sorted`` con una tupla por entrada (carpetas primero, criterio, nombre).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from app.services.vfs.base import Entrada

# Criterios válidos (preferencia y sesión).
NOMBRE, EXTENSION, FECHA, TAMANO, TIPO, SIN_ORDEN = "nombre", "extension", "fecha", "tamano", "tipo", "sin_orden"
CRITERIOS = (NOMBRE, EXTENSION, FECHA, TAMANO, TIPO, SIN_ORDEN)

_TROZOS = re.compile(r"(\d+)")


def clave_natural(texto: str) -> tuple:
	"""«archivo2» antes que «archivo10» (orden natural, sin distinguir mayúsculas)."""
	return tuple(
		(0, int(trozo), "") if trozo.isdigit() else (1, 0, trozo.casefold())
		for trozo in _TROZOS.split(texto)
		if trozo
	)


def _clave_nombre(texto: str, natural: bool) -> tuple:
	return clave_natural(texto) if natural else ((1, 0, texto.casefold()),)


def ordenar(
	entradas: Sequence[Entrada],
	criterio: str = NOMBRE,
	inverso: bool = False,
	carpetas_primero: bool = True,
	natural: bool = True,
	tipo_de: dict[str, str] | None = None,
) -> list[Entrada]:
	"""Devuelve una lista nueva ordenada.

	- La fila «..» (``es_superior``) siempre va la primera, también en orden inverso.
	- Con ``carpetas_primero``, las carpetas van antes que los archivos y el orden
	  inverso se aplica dentro de cada grupo (como Total Commander).
	- ``SIN_ORDEN`` conserva el orden recibido (el del disco).
	- ``tipo_de``: descripción del tipo por extensión, para ordenar por tipo.
	"""
	superiores = [e for e in entradas if e.es_superior]
	resto = [e for e in entradas if not e.es_superior]
	if criterio == SIN_ORDEN:
		lista = list(reversed(resto)) if inverso else list(resto)
	else:
		tipos = tipo_de or {}

		def clave(e: Entrada) -> tuple:
			nombre = _clave_nombre(e.nombre, natural)
			if criterio == EXTENSION:
				return (e.extension.casefold(), nombre)
			if criterio == FECHA:
				return (e.modificado, nombre)
			if criterio == TAMANO:
				return (e.tamano, nombre)
			if criterio == TIPO:
				return (tipos.get(e.extension, e.extension).casefold(), nombre)
			return (nombre,)

		if carpetas_primero:
			carpetas = sorted((e for e in resto if e.es_carpeta), key=clave, reverse=inverso)
			archivos = sorted((e for e in resto if not e.es_carpeta), key=clave, reverse=inverso)
			lista = carpetas + archivos
		else:
			lista = sorted(resto, key=clave, reverse=inverso)
	return superiores + lista
