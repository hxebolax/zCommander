# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Listas M3U y M3U8: abrir y guardar, con rutas relativas y UTF-8. Sin wx.

- Al leer, las rutas relativas se resuelven desde la carpeta de la lista; las
  direcciones de Internet se omiten (el reproductor solo reproduce archivos).
- Un ``.m3u`` antiguo puede venir en la página de códigos de Windows: si no es
  UTF-8 válido, se lee como cp1252.
- Al guardar, se escribe siempre UTF-8 (sin BOM) y las rutas relativas a la
  carpeta de la lista cuando están en la misma unidad, para que la lista siga
  valiendo si se mueve la carpeta entera (un pendrive con otra letra).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

EXTENSIONES = (".m3u", ".m3u8")


@dataclass(frozen=True)
class EntradaLista:
	ruta: str
	titulo: str = ""
	duracion: float = -1.0


def es_lista(nombre: str) -> bool:
	return nombre.lower().endswith(EXTENSIONES)


def _texto(datos: bytes) -> str:
	try:
		return datos.decode("utf-8-sig")
	except UnicodeDecodeError:
		return datos.decode("cp1252", errors="replace")


def leer(ruta: str | Path) -> list[EntradaLista]:
	"""Entradas de la lista en su orden; rutas absolutas y normalizadas."""
	archivo = Path(ruta)
	carpeta = archivo.parent
	entradas: list[EntradaLista] = []
	titulo, duracion = "", -1.0
	for linea in _texto(archivo.read_bytes()).splitlines():
		linea = linea.strip()
		if not linea:
			continue
		if linea.startswith("#"):
			if linea.upper().startswith("#EXTINF:"):
				datos = linea[8:]
				segundos, _coma, resto = datos.partition(",")
				try:
					duracion = float(segundos.strip().split(" ")[0])
				except ValueError:
					duracion = -1.0
				titulo = resto.strip()
			continue
		if "://" in linea and not linea.lower().startswith("file://"):
			log.info("Se omite una dirección de Internet de la lista %s", archivo.name)
			titulo, duracion = "", -1.0
			continue
		if linea.lower().startswith("file:///"):
			from urllib.parse import unquote

			linea = unquote(linea[8:])
		destino = Path(linea.replace("/", os.sep))
		if not destino.is_absolute():
			destino = carpeta / destino
		entradas.append(EntradaLista(os.path.normpath(str(destino)), titulo, duracion))
		titulo, duracion = "", -1.0
	return entradas


def _relativa(ruta: str, carpeta: Path) -> str:
	try:
		if os.path.splitdrive(os.path.abspath(ruta))[0].casefold() != os.path.splitdrive(str(carpeta.resolve()))[0].casefold():
			return ruta
		return os.path.relpath(ruta, carpeta)
	except ValueError:
		return ruta


def guardar(ruta: str | Path, entradas: list[EntradaLista], relativas: bool = True) -> None:
	"""Escribe la lista (atómico: temporal y sustitución)."""
	archivo = Path(ruta)
	carpeta = archivo.parent
	lineas = ["#EXTM3U"]
	for entrada in entradas:
		duracion = int(entrada.duracion) if entrada.duracion >= 0 else -1
		titulo = entrada.titulo or Path(entrada.ruta).stem
		lineas.append(f"#EXTINF:{duracion},{titulo}")
		lineas.append(_relativa(entrada.ruta, carpeta) if relativas else entrada.ruta)
	temporal = archivo.with_name(archivo.name + ".tmp")
	temporal.write_text("\r\n".join(lineas) + "\r\n", encoding="utf-8")
	os.replace(temporal, archivo)
