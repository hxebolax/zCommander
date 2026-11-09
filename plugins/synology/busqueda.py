# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Buscar archivos en el NAS (diseño 2.0, 13.7; synology.md 4.3 y 4.18).

Usa Universal Search (``SYNO.Finder.FileIndexing.Search``) si el NAS lo tiene,
que es mucho más rápido en carpetas indexadas, y si no ``SYNO.FileStation.Search``
como tarea (``start`` → ``list`` hasta ``finished`` → ``stop`` y ``clean``).
Las dos son de lectura: funcionan en modo solo lectura.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from app.plugins import api

from . import errores
from .cliente import ClienteDSM

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.busqueda")


def patrones(texto: str) -> str:
	"""«*.txt;*.md | *.bak» (sintaxis de zCommander) → «*.txt,*.md» (File Station separa con comas; la exclusión se ignora)."""
	incluir = (texto or "*").split("|", 1)[0]
	partes = [p.strip() for p in incluir.replace(";", ",").split(",") if p.strip()]
	return ",".join(partes) or "*"


def buscar_en_nas(cliente: ClienteDSM, patron: str, *, carpetas: list[str] | None = None, maximo: int = 1000,
		cancelacion: Any = None, al_encontrar: Callable[[str], None] | None = None, tiempo_maximo: float = 120) -> list[str]:
	"""[trabajo] Rutas de File Station («/Documentos/notas.txt») cuyo nombre coincide con ``patron``."""
	patron = patrones(patron)
	encontrados: list[str] = []

	def anotar(ruta: str) -> bool:
		if ruta in encontrados:
			return len(encontrados) < maximo
		encontrados.append(ruta)
		if al_encontrar is not None:
			al_encontrar(ruta)
		return len(encontrados) < maximo

	simple = patron.replace("*", "").replace("?", "")
	if cliente.disponible("SYNO.Finder.FileIndexing.Search") and simple and "," not in patron and not carpetas:
		try:
			datos = cliente.llamar("SYNO.Finder.FileIndexing.Search", "search", keyword=simple, size=maximo, **{"from": 0})
			for hit in datos.get("hits", []):
				if not anotar(str(hit.get("path", ""))):
					break
			if encontrados:
				return encontrados
		except errores.ErrorDSM as error:
			log.info("Universal Search no ha podido buscar (%s); se usa File Station", error.mensaje)
	if not carpetas:
		compartidas = cliente.llamar("SYNO.FileStation.List", "list_share", offset=0, limit=0)
		carpetas = [str(c.get("path")) for c in compartidas.get("shares", [])]
	if not carpetas:
		return encontrados
	datos = cliente.llamar("SYNO.FileStation.Search", "start", folder_path=carpetas, recursive=True, pattern=patron)
	taskid = str(datos.get("taskid", ""))
	limite = time.monotonic() + tiempo_maximo
	desplazamiento = 0
	try:
		while True:
			api.comprobar(cancelacion)
			lista = cliente.llamar("SYNO.FileStation.Search", "list", taskid=taskid, offset=desplazamiento, limit=500)
			archivos = lista.get("files", [])
			for archivo in archivos:
				if not anotar(str(archivo.get("path", ""))):
					return encontrados
			desplazamiento += len(archivos)
			if lista.get("finished") and not archivos:
				return encontrados
			if time.monotonic() > limite:
				log.info("Búsqueda en el NAS cortada por tiempo con %s resultados", len(encontrados))
				return encontrados
			if not archivos:
				time.sleep(0.3)
	finally:
		for metodo in ("stop", "clean"):
			try:
				cliente.llamar("SYNO.FileStation.Search", metodo, taskid=taskid)
			except api.ErrorArchivos:
				log.debug("No se pudo %s la búsqueda %s", metodo, taskid, exc_info=True)


def crear_motor(conexiones: Any) -> Callable[[Any, Callable[[str], None], Any], None]:
	"""Motor ``zc.synology:filestation`` del diálogo Buscar archivos: busca en todos los NAS conectados."""

	def motor(criterios: Any, entregar: Callable[[str], None], cancelacion: Any) -> None:
		activas = conexiones.activas()
		if not activas:
			raise api.NoEncontrado(_("No hay ningún NAS conectado en el que buscar."))
		patron = str(getattr(criterios, "nombres", "*") or "*")
		maximo = int(getattr(criterios, "max_resultados", 1000) or 1000)
		for conexion in activas:
			api.comprobar(cancelacion)
			buscar_en_nas(conexion.cliente, patron, maximo=maximo, cancelacion=cancelacion,
				al_encontrar=lambda ruta, c=conexion: entregar(f"synology://{c.servidor.id}{ruta}"))

	return motor
