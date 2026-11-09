# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Servidores recientes y favoritos de la raíz «Red» (diseño 2.0, 9.1), en ``data/config/red.json``.

Formato::

	{"version": 1, "recientes": ["\\\\\\\\DS220"], "favoritos": [{"nombre": "NAS", "ruta": "\\\\\\\\DS220"}]}

Solo nombres de servidor y rutas: nunca usuarios ni contraseñas (las
contraseñas, si la persona lo pide, las guarda Windows). Los recientes se
apuntan al visitar un servidor (9.3), el último primero y sin repetir, 20
como mucho. Es de la parte ``conexiones`` de las copias de seguridad (7.2).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from app.core import almacen_json, paths

log = logging.getLogger(__name__)

NOMBRE = "red.json"
VERSION = 1
MAX_RECIENTES = 20

_candado = threading.Lock()


@dataclass(frozen=True)
class FavoritoRed:
	nombre: str
	ruta: str


def _por_defecto() -> dict:
	return {"version": VERSION, "recientes": [], "favoritos": []}


def _normalizar(ruta: str) -> str:
	ruta = (ruta or "").strip().rstrip("\\")
	if ruta and not ruta.startswith("\\\\") and "://" not in ruta:
		ruta = "\\\\" + ruta.lstrip("\\")
	return ruta


def _leer() -> dict:
	# Leer no crea ``data/config`` (la raíz «Red» se lista sin haber guardado nada aún).
	datos = almacen_json.leer(NOMBRE, _por_defecto(), carpeta=paths.ruta_datos() / "config")
	recientes = [r for r in datos.get("recientes", []) if isinstance(r, str) and r.strip()] if isinstance(datos.get("recientes"), list) else []
	favoritos = []
	for fila in datos.get("favoritos", []) if isinstance(datos.get("favoritos"), list) else []:
		if isinstance(fila, dict) and isinstance(fila.get("ruta"), str) and fila["ruta"].strip():
			ruta = _normalizar(fila["ruta"])
			nombre = fila.get("nombre") if isinstance(fila.get("nombre"), str) and fila["nombre"].strip() else ruta.lstrip("\\")
			favoritos.append({"nombre": nombre.strip(), "ruta": ruta})
	return {"version": VERSION, "recientes": [_normalizar(r) for r in recientes][:MAX_RECIENTES], "favoritos": favoritos}


def recientes() -> list[str]:
	with _candado:
		return list(_leer()["recientes"])


def favoritos() -> list[FavoritoRed]:
	with _candado:
		return [FavoritoRed(f["nombre"], f["ruta"]) for f in _leer()["favoritos"]]


def anotar_reciente(servidor: str) -> None:
	"""Apunta ``\\\\servidor`` como el más reciente. Un fallo al guardar se registra y no se propaga."""
	ruta = _normalizar(servidor)
	if not ruta:
		return
	with _candado:
		datos = _leer()
		lista = [r for r in datos["recientes"] if r.casefold() != ruta.casefold()]
		if lista[:1] == [ruta] and len(lista) == len(datos["recientes"]):
			return
		datos["recientes"] = [ruta, *lista][:MAX_RECIENTES]
		try:
			almacen_json.escribir(NOMBRE, datos)
		except OSError:
			log.warning("No se pudo apuntar %s en los servidores recientes", ruta, exc_info=True)


def quitar_reciente(servidor: str) -> None:
	ruta = _normalizar(servidor)
	with _candado:
		datos = _leer()
		datos["recientes"] = [r for r in datos["recientes"] if r.casefold() != ruta.casefold()]
		almacen_json.escribir(NOMBRE, datos)


def guardar_favoritos(lista: list[FavoritoRed]) -> None:
	""":raises OSError: si no se pudo escribir (quien llama avisa a la persona)."""
	with _candado:
		datos = _leer()
		datos["favoritos"] = [{"nombre": f.nombre, "ruta": _normalizar(f.ruta)} for f in lista]
		almacen_json.escribir(NOMBRE, datos)
