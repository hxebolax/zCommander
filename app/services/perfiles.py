# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Perfiles de usuario: valores de partida para personas novatas, intermedias y avanzadas.

El perfil activo NO se guarda: ``perfil_actual`` lo calcula comparando la
configuración con cada perfil. Así no hace falta saber si un cambio vino de
aplicar un perfil o de la persona (si toca algo, pasa a «personalizado»).
"""

from __future__ import annotations

import builtins
from typing import Any


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


NOVATO, INTERMEDIO, AVANZADO, PERSONALIZADO = "novato", "intermedio", "avanzado", "personalizado"

PERFILES: dict[str, dict[str, Any]] = {
	NOVATO: {
		"paneles.teclear_en_linea_ordenes": False,
		"vista.linea_ordenes_visible": False,
		"general.confirmar_eliminar": True,
		"general.confirmar_salida": True,
		"general.confirmar_ejecutar": True,
		"paneles.mostrar_ocultos": False,
		"accesibilidad.detalle": "detallado",
		"accesibilidad.progreso_voz": "hitos",
		"accesibilidad.consejos": True,
		"paneles.columnas": ["nombre", "tipo", "tamano", "modificado"],
		# 2.0 (diseño 2.0, 14.3 y 10.11): menús según el nivel y sonidos activos en los tres.
		"vista.menus_por_nivel": True,
		"sonidos.activos": True,
	},
	INTERMEDIO: {
		"paneles.teclear_en_linea_ordenes": False,
		"vista.linea_ordenes_visible": True,
		"general.confirmar_eliminar": True,
		"general.confirmar_salida": True,
		"general.confirmar_ejecutar": False,
		"paneles.mostrar_ocultos": False,
		"accesibilidad.detalle": "normal",
		"accesibilidad.progreso_voz": "inicio_fin",
		"accesibilidad.consejos": False,
		"paneles.columnas": ["nombre", "extension", "tamano", "modificado"],
		# 2.0 (diseño 2.0, 14.3 y 10.11): menús según el nivel y sonidos activos en los tres.
		"vista.menus_por_nivel": False,
		"sonidos.activos": True,
	},
	AVANZADO: {
		"paneles.teclear_en_linea_ordenes": True,
		"vista.linea_ordenes_visible": True,
		"general.confirmar_eliminar": False,
		"general.confirmar_salida": False,
		"general.confirmar_ejecutar": False,
		"paneles.mostrar_ocultos": True,
		"accesibilidad.detalle": "breve",
		"accesibilidad.progreso_voz": "final",
		"accesibilidad.consejos": False,
		"paneles.columnas": ["nombre", "extension", "tamano", "modificado", "atributos"],
		# 2.0 (diseño 2.0, 14.3 y 10.11): menús según el nivel y sonidos activos en los tres.
		"vista.menus_por_nivel": False,
		"sonidos.activos": True,
	},
}


def nombre_visible(perfil: str) -> str:
	return {
		NOVATO: _("Novato"), INTERMEDIO: _("Intermedio"), AVANZADO: _("Avanzado"), PERSONALIZADO: _("Personalizado"),
	}.get(perfil, perfil)


def descripcion(perfil: str) -> str:
	return {
		NOVATO: _(
			"Para empezar: todo se confirma, la línea de órdenes está oculta, los anuncios son detallados, "
			"el progreso se dice cada 25 % y hay consejos al llegar a sitios nuevos."
		),
		INTERMEDIO: _(
			"Para el uso diario: se confirman eliminar y salir, la línea de órdenes está visible y los anuncios "
			"son los normales."
		),
		AVANZADO: _(
			"Como Norton Commander: teclear va a la línea de órdenes, casi sin confirmaciones, archivos ocultos "
			"visibles y anuncios breves."
		),
	}.get(perfil, "")


def perfil_actual(config) -> str:
	"""Perfil con el que coincide la configuración, o «personalizado»."""
	for nombre, valores in PERFILES.items():
		if all(config.obtener(clave) == valor for clave, valor in valores.items()):
			return nombre
	return PERSONALIZADO


def cambios_al_aplicar(config, perfil: str) -> dict[str, Any]:
	"""Claves que cambiarían al aplicar ``perfil`` (para decir cuántas antes de confirmar)."""
	return {clave: valor for clave, valor in PERFILES[perfil].items() if config.obtener(clave) != valor}


def aplicar_perfil(config, perfil: str) -> int:
	"""Escribe los valores del perfil de una vez; devuelve cuántas claves cambiaron."""
	cambios = cambios_al_aplicar(config, perfil)
	if cambios:
		config.establecer_varias(cambios)
	return len(cambios)
