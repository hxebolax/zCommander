# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Asociaciones por tipo de archivo: qué orden abre, ve o edita cada patrón.

Formato de ``data/config/asociaciones.json``::

	{"version": 1, "reglas": [{"patron": "*.txt;*.md", "abrir": "", "ver": "", "editar": "notepad++.exe %P"}]}

Las reglas se miran en orden; gana la primera cuyo patrón coincide y cuyo campo
para esa acción no está vacío. Las órdenes usan las variables de
``app.services.variables`` y se lanzan sin ``cmd`` (``expandir_directo``).
El editor de reglas es del bloque F; este módulo solo lee y guarda.

2.0: detrás de las reglas de la persona van unas **de fábrica** que no se guardan
(``reglas_fabrica``): «Abrir» de ``*.zcc`` descifra con ``zc.cifrado`` (11.13) y los
patrones de «Formatos que se reproducen con Intro» de ``zc.reproductor`` (11.1) se
reproducen con él. Cada una solo vale con su complemento habilitado, y una regla de
la persona para el mismo patrón siempre gana.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Literal

from app.core import almacen_json
from app.services.seleccion import Patron

log = logging.getLogger(__name__)

NOMBRE = "asociaciones.json"
Accion = Literal["abrir", "ver", "editar"]


@dataclass
class Regla:
	patron: str
	abrir: str = ""
	ver: str = ""
	editar: str = ""


def cargar() -> list[Regla]:
	datos = almacen_json.leer(NOMBRE, {"version": 1, "reglas": []})
	reglas = []
	for r in datos.get("reglas", []):
		if isinstance(r, dict) and isinstance(r.get("patron"), str):
			reglas.append(Regla(r["patron"], str(r.get("abrir", "")), str(r.get("ver", "")), str(r.get("editar", ""))))
	return reglas


def guardar(reglas: list[Regla]) -> None:
	almacen_json.escribir(NOMBRE, {"version": 1, "reglas": [asdict(r) for r in reglas]})


def _habilitado(id_complemento: str) -> bool:
	"""El complemento está registrado y se puede usar (sin activarlo)."""
	from app.plugins import registro

	return registro.usable(id_complemento)


def _formatos_intro_reproductor() -> str:
	"""Patrones de ``plugin.zc.reproductor.formatos_intro`` sin crear su archivo de configuración."""
	from app.core import paths
	from app.plugins import config_plugins

	if not (paths.ruta_config_plugins() / "zc.reproductor.json").is_file():
		return ""  # el valor de fábrica es vacío: nadie lo ha cambiado
	try:
		return str(config_plugins.registro().de("zc.reproductor").obtener("ajustes.formatos_intro") or "").strip()
	except Exception:  # noqa: BLE001 - una configuración rota no impide abrir archivos
		log.debug("No se pudo leer formatos_intro del reproductor", exc_info=True)
		return ""


def reglas_fabrica() -> list[Regla]:
	"""Reglas «Abrir» de fábrica (no se guardan): van detrás de las de la persona."""
	reglas: list[Regla] = []
	try:
		if _habilitado("zc.cifrado"):
			reglas.append(Regla("*.zcc", abrir="zc:zc.cifrado:descifrar"))
		if _habilitado("zc.reproductor"):
			patrones = _formatos_intro_reproductor()
			if patrones:
				reglas.append(Regla(patrones, abrir="zc:zc.reproductor:reproducir"))
	except Exception:  # noqa: BLE001 - sin registro de complementos, solo valen las de la persona
		log.debug("Sin reglas de fábrica de los complementos", exc_info=True)
	return reglas


def orden_para(nombre: str, accion: Accion, reglas: list[Regla] | None = None) -> str | None:
	"""Orden de la primera regla que coincide con ``nombre`` para ``accion``, o None.

	Sin ``reglas``, las de ``asociaciones.json`` y detrás las de fábrica (``reglas_fabrica``).
	"""
	for regla in reglas if reglas is not None else [*cargar(), *reglas_fabrica()]:
		orden = getattr(regla, accion, "")
		if orden and Patron.analizar(regla.patron).coincide(nombre):
			return orden
	return None


def recargar() -> None:
	"""Vuelve a leer su archivo tras restaurar una copia (2.0, 14.4): se lee en cada uso, así que solo avisa."""
	from app.services import recarga

	recarga.avisar(__name__)
