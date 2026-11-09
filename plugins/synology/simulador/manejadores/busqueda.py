# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Universal Search (synology.md 4.18): estado del índice y búsqueda indexada sobre el árbol."""

from __future__ import annotations

from typing import Any

from ..comun import Peticion
from ..estado import Nodo


def estado_indice(pet: Peticion) -> dict[str, Any]:
	return {"status": "idle", "indexed_folders": ["/Documentos", "/Multimedia", "/photo"], "file_count": pet.estado.contar_entradas()}


def buscar(pet: Peticion) -> dict[str, Any]:
	palabra = pet.texto("keyword").casefold()
	inicio, cantidad = pet.entero("from", 0), pet.entero("size", 100)
	encontrados: list[dict[str, Any]] = []

	def recorrer(ruta: str, nodo: Nodo) -> None:
		for hijo in nodo.hijos.values():
			if hijo.nombre.startswith("#"):
				continue
			ruta_hijo = f"{ruta}/{hijo.nombre}"
			if palabra and palabra in hijo.nombre.casefold():
				encontrados.append({"path": ruta_hijo, "name": hijo.nombre, "is_dir": hijo.es_carpeta, "size": hijo.tamano,
					"mtime": int(hijo.modificado)})
			if hijo.es_carpeta:
				recorrer(ruta_hijo, hijo)

	for carpeta in ("Documentos", "Multimedia", "photo"):
		nodo = pet.estado.raiz.hijos.get(carpeta)
		if nodo is not None:
			recorrer("/" + carpeta, nodo)
	return {"hits": encontrados[inicio:inicio + cantidad], "total": len(encontrados)}


MANEJADORES = {
	("SYNO.Finder.FileIndexing.Status", "get"): estado_indice,
	("SYNO.Finder.FileIndexing.Search", "search"): buscar,
}
