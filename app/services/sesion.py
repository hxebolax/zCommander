# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sesión: pestañas, carpetas, vistas, historiales y cesta, en ``data/config/sesion.json``.

Formato (versión 1)::

	{"version": 1, "activo": "izquierdo",
	 "lados": {"izquierdo": {"pestanas": [PESTAÑA, ...], "actual": 0}, "derecho": {...}},
	 "historial_ordenes": ["dir", ...], "cesta": ["C:\\\\a.txt", ...]}

	PESTAÑA = {"ruta": "C:\\\\", "vista": "completa", "orden": "nombre", "inverso": false,
	           "filtro": "", "bloqueada": false, "columnas": [], "historial": {"elementos": [], "posicion": -1}}

``ruta`` es lo que devuelve ``Proveedor.mostrar`` (puede ser una ruta local,
una dentro de un comprimido o una dirección ftp://); al restaurar se reabre
con el resolver y, si falla, se sube hasta la primera carpeta local que exista.
"""

from __future__ import annotations

import copy
import logging
import os
from typing import Any

from app.core import almacen_json

log = logging.getLogger(__name__)

NOMBRE = "sesion.json"

PESTANA_POR_DEFECTO: dict[str, Any] = {
	"ruta": "", "vista": "completa", "orden": "nombre", "inverso": False, "filtro": "", "bloqueada": False,
	"columnas": [], "historial": {"elementos": [], "posicion": -1},
	# 2.0 (10.5): orden de lectura de las columnas de la pestaña; vacía = el de sus columnas.
	"lectura": [],
}

POR_DEFECTO: dict[str, Any] = {
	"version": 1,
	"activo": "izquierdo",
	"lados": {
		"izquierdo": {"pestanas": [], "actual": 0},
		"derecho": {"pestanas": [], "actual": 0},
	},
	"historial_ordenes": [],
	"cesta": [],
}


def pestana(**valores) -> dict[str, Any]:
	"""Pestaña con los valores por defecto completados."""
	datos = copy.deepcopy(PESTANA_POR_DEFECTO)
	datos.update(valores)
	return datos


def cargar() -> dict[str, Any]:
	"""Sesión guardada (completada y saneada) o la de por defecto."""
	datos = almacen_json.leer(NOMBRE, POR_DEFECTO)
	if datos.get("activo") not in ("izquierdo", "derecho"):
		datos["activo"] = "izquierdo"
	lados = datos.get("lados") if isinstance(datos.get("lados"), dict) else {}
	for lado in ("izquierdo", "derecho"):
		info = lados.get(lado) if isinstance(lados.get(lado), dict) else {}
		pestanas = [pestana(**p) for p in info.get("pestanas", []) if isinstance(p, dict) and isinstance(p.get("ruta"), str)]
		actual = info.get("actual", 0)
		actual = actual if isinstance(actual, int) and 0 <= actual < max(1, len(pestanas)) else 0
		lados[lado] = {"pestanas": pestanas, "actual": actual}
	datos["lados"] = lados
	for clave in ("historial_ordenes", "cesta"):
		if not isinstance(datos.get(clave), list):
			datos[clave] = []
		datos[clave] = [x for x in datos[clave] if isinstance(x, str)]
	return datos


def guardar(datos: dict[str, Any]) -> bool:
	"""Escribe la sesión; ``False`` si no se pudo (queda en el registro)."""
	try:
		almacen_json.escribir(NOMBRE, datos)
	except OSError:
		return False
	return True


def carpeta_de_respaldo(ruta: str) -> str:
	"""Primera carpeta local que existe subiendo desde ``ruta``; si ninguna, la carpeta personal."""
	actual = ruta
	while actual:
		if os.path.isdir(actual):
			return actual
		superior = os.path.dirname(actual.rstrip("\\"))
		if superior == actual or not superior:
			break
		actual = superior
	return os.path.expanduser("~")
