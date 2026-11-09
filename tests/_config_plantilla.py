# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Valores de EJEMPLO de la plantilla del agente de configuración, para probar la clase genérica."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.configuracion import Regla, eliminar_clave, renombrar_clave

VERSION_ESQUEMA = 2

# ── Valores por defecto ──────────────────────────────────────────────────────
# Un diccionario por sección. Cada valor fija también el TIPO esperado: si en el
# archivo aparece otro tipo (una cadena donde va un número), se descarta y se
# usa el valor por defecto.
VALORES_POR_DEFECTO: dict[str, dict[str, Any]] = {
	"general": {
		"idioma": "es",
		"confirmar_salida": True,
		"minimizar_a_bandeja": False,
		"carpeta_descargas": "",
	},
	"apariencia": {
		"tamano_fuente": 11,
		"tema": "sistema",
	},
	"accesibilidad": {
		"anunciar_cambios": True,
		"retardo_voz_ms": 120,
		"volumen": 0.8,
	},
	"red": {
		"intervalo_actualizacion_s": 60,
		"usar_proxy": False,
		"servidor_proxy": "",
		"puerto_proxy": 8080,
	},
}


class _NoUsar:
	"""Restricciones opcionales de una clave.

	:param minimo: valor mínimo (números).
	:param maximo: valor máximo (números).
	:param opciones: valores admitidos (listas cerradas: tema, idioma...).
	:param longitud_maxima: longitud máxima (textos).
	"""

	minimo: float | None = None
	maximo: float | None = None
	opciones: tuple[Any, ...] | None = None
	longitud_maxima: int | None = None


# Reglas por clave «seccion.clave». Las claves sin regla solo comprueban el tipo.
REGLAS: dict[str, Regla] = {
	"general.idioma": Regla(opciones=("es", "en", "fr", "pt")),
	"apariencia.tamano_fuente": Regla(minimo=8, maximo=40),
	"apariencia.tema": Regla(opciones=("sistema", "claro", "oscuro")),
	"accesibilidad.retardo_voz_ms": Regla(minimo=0, maximo=2000),
	"accesibilidad.volumen": Regla(minimo=0.0, maximo=1.0),
	"red.intervalo_actualizacion_s": Regla(minimo=10, maximo=86400),
	"red.servidor_proxy": Regla(longitud_maxima=255),
	"red.puerto_proxy": Regla(minimo=1, maximo=65535),
}



def _migrar_a_2(datos: dict) -> None:
	"""v1 → v2: la fuente pasó de «general» a «apariencia» y se retiró «usar_sonidos_viejos».

	EJEMPLO: sustitúyelo por las migraciones reales del proyecto.
	"""
	renombrar_clave(datos, "general.tamano_letra", "apariencia.tamano_fuente")
	eliminar_clave(datos, "general.usar_sonidos_viejos")


# MIGRACIONES[n] lleva los datos de la versión n a la n+1. Cada función recibe
# el diccionario TAL COMO SE LEYÓ del archivo (antes de completar con los
# valores por defecto) y lo modifica en el sitio. Deben ser idempotentes.
MIGRACIONES: dict[int, Callable[[dict], None]] = {
	1: _migrar_a_2,
}


