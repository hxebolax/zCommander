# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Carpetas favoritas (Ctrl+D): nombre y ruta, en ``data/config/favoritos.json``.

Formato (sección 10 del diseño)::

	{"version": 1, "favoritos": [{"nombre": "Fotos", "ruta": "D:\\Fotos"}]}

La ruta es el texto que muestra el panel (``mostrar_ruta``): una carpeta del
disco, una ruta UNC o una dirección ``ftp://``/``sftp://``. Al ir a un
favorito, el panel la resuelve en un hilo como cualquier ruta escrita.

Las funciones que cambian la lista trabajan sobre listas y devuelven el índice
afectado: así el diálogo puede dejar el cursor donde corresponde y las pruebas
no necesitan disco. Solo ``cargar`` y ``guardar`` tocan el archivo.
"""

from __future__ import annotations

import logging
import ntpath
from dataclasses import asdict, dataclass

from app.core import almacen_json

log = logging.getLogger(__name__)

NOMBRE = "favoritos.json"
VERSION = 1


@dataclass
class Favorito:
	nombre: str
	ruta: str


def _por_defecto() -> dict:
	return {"version": VERSION, "favoritos": []}


def cargar() -> list[Favorito]:
	"""Favoritos guardados; las filas mal formadas se descartan (y se registra cuántas)."""
	datos = almacen_json.leer(NOMBRE, _por_defecto())
	lista: list[Favorito] = []
	descartados = 0
	for fila in datos.get("favoritos", []) if isinstance(datos.get("favoritos"), list) else []:
		if isinstance(fila, dict) and isinstance(fila.get("ruta"), str) and fila["ruta"].strip():
			nombre = fila.get("nombre") if isinstance(fila.get("nombre"), str) else ""
			lista.append(Favorito(nombre.strip() or nombre_sugerido(fila["ruta"]), fila["ruta"].strip()))
		else:
			descartados += 1
	if descartados:
		log.warning("Se descartaron %d favoritos mal formados de %s", descartados, NOMBRE)
	return lista


def guardar(lista: list[Favorito]) -> None:
	""":raises OSError: si no se pudo escribir (quien llama avisa a la persona)."""
	almacen_json.escribir(NOMBRE, {"version": VERSION, "favoritos": [asdict(f) for f in lista]})


def _clave(ruta: str) -> str:
	"""Comparación de rutas: sin distinguir mayúsculas ni la barra final (como Windows)."""
	ruta = ruta.strip()
	if len(ruta) > 3 or "://" in ruta:
		ruta = ruta.rstrip("\\/")
	return ruta.casefold()


def nombre_sugerido(ruta: str) -> str:
	"""Nombre propuesto al añadir: el último componente («Fotos»), o la unidad («D:»)."""
	limpia = ruta.strip().rstrip("\\/")
	if "://" in limpia:
		resto = limpia.split("://", 1)[1]
		return resto.rsplit("/", 1)[-1] or resto
	# ``ntpath.basename`` de «\\servidor\recurso» es vacío (es la «unidad»): se toma el último trozo.
	nombre = ntpath.basename(limpia) or next((p for p in reversed(limpia.split("\\")) if p), "")
	return nombre or limpia or ruta


def buscar(lista: list[Favorito], ruta: str) -> int | None:
	"""Índice del favorito con esa ruta, o ``None``."""
	clave = _clave(ruta)
	return next((i for i, f in enumerate(lista) if _clave(f.ruta) == clave), None)


def agregar(lista: list[Favorito], nombre: str, ruta: str) -> int:
	"""Añade al final y devuelve su índice. Si la ruta ya estaba, la renombra y devuelve ese índice."""
	nombre = nombre.strip() or nombre_sugerido(ruta)
	existente = buscar(lista, ruta)
	if existente is not None:
		lista[existente].nombre = nombre
		return existente
	lista.append(Favorito(nombre, ruta.strip()))
	return len(lista) - 1


def renombrar(lista: list[Favorito], indice: int, nombre: str) -> None:
	if not nombre.strip():
		raise ValueError("El nombre no puede quedar vacío")
	lista[indice].nombre = nombre.strip()


def mover(lista: list[Favorito], indice: int, paso: int) -> int:
	"""Sube (-1) o baja (+1) un favorito; devuelve su nueva posición (la misma si ya está al borde)."""
	destino = indice + paso
	if not (0 <= indice < len(lista)) or not (0 <= destino < len(lista)):
		return indice
	lista[indice], lista[destino] = lista[destino], lista[indice]
	return destino


def eliminar(lista: list[Favorito], indice: int) -> Favorito:
	return lista.pop(indice)


def recargar() -> None:
	"""Vuelve a leer su archivo tras restaurar una copia (2.0, 14.4): se lee en cada uso, así que solo avisa."""
	from app.services import recarga

	recarga.avisar(__name__)
