# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Posiciones recordadas y marcadores con nombre, en la carpeta de datos del complemento. Sin wx.

- ``posiciones.json``: ruta → segundos, tamaño y fecha del archivo. Va en un
  archivo propio y no en la configuración porque crece con cada audiolibro (la
  clave ``posiciones`` del manifiesto es interna y solo documenta su forma).
  Solo se restaura si el archivo conserva el tamaño: si se sustituyó por otro con
  el mismo nombre, la posición ya no vale.
- ``marcadores.json``: ruta → lista de (nombre, segundos).

Escritura atómica (temporal y ``os.replace``) y un candado: el reproductor
guarda desde la interfaz y al cerrar.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Como mucho se recuerdan tantas posiciones (se olvidan las más antiguas).
MAXIMO_POSICIONES = 500


def _clave(ruta: str) -> str:
	return os.path.normcase(os.path.normpath(ruta))


def _tamano(ruta: str) -> int:
	try:
		return os.path.getsize(ruta)
	except OSError:
		return -1


class Memoria:
	def __init__(self, carpeta: Path) -> None:
		self.carpeta = Path(carpeta)
		self._candado = threading.Lock()
		self._posiciones: dict[str, dict[str, Any]] | None = None
		self._marcadores: dict[str, list[list[Any]]] | None = None

	# ── Archivos ──────────────────────────────────────────────────────────────

	def _leer(self, nombre: str) -> dict:
		ruta = self.carpeta / nombre
		try:
			datos = json.loads(ruta.read_text(encoding="utf-8"))
			return datos if isinstance(datos, dict) else {}
		except FileNotFoundError:
			return {}
		except (OSError, ValueError):
			log.warning("No se pudo leer %s; se empieza de cero", ruta, exc_info=True)
			return {}

	def _escribir(self, nombre: str, datos: dict) -> None:
		self.carpeta.mkdir(parents=True, exist_ok=True)
		ruta = self.carpeta / nombre
		temporal = ruta.with_name(ruta.name + ".tmp")
		temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
		os.replace(temporal, ruta)

	def _todas_posiciones(self) -> dict[str, dict[str, Any]]:
		if self._posiciones is None:
			self._posiciones = self._leer("posiciones.json")
		return self._posiciones

	def _todos_marcadores(self) -> dict[str, list[list[Any]]]:
		if self._marcadores is None:
			self._marcadores = self._leer("marcadores.json")
		return self._marcadores

	# ── Posiciones ────────────────────────────────────────────────────────────

	def posicion(self, ruta: str) -> float | None:
		"""Segundos donde se dejó ``ruta``, o ``None`` si no hay o el archivo cambió."""
		with self._candado:
			dato = self._todas_posiciones().get(_clave(ruta))
		if not isinstance(dato, dict):
			return None
		if int(dato.get("tamano", -1)) != _tamano(ruta):
			return None
		try:
			return float(dato.get("segundos", 0))
		except (TypeError, ValueError):
			return None

	def guardar_posicion(self, ruta: str, segundos: float) -> None:
		with self._candado:
			posiciones = self._todas_posiciones()
			posiciones[_clave(ruta)] = {"segundos": round(float(segundos), 1), "tamano": _tamano(ruta), "fecha": time.time()}
			if len(posiciones) > MAXIMO_POSICIONES:
				for clave in sorted(posiciones, key=lambda c: posiciones[c].get("fecha", 0))[:len(posiciones) - MAXIMO_POSICIONES]:
					posiciones.pop(clave, None)
			self._escribir("posiciones.json", posiciones)

	def olvidar_posicion(self, ruta: str) -> None:
		with self._candado:
			if self._todas_posiciones().pop(_clave(ruta), None) is not None:
				self._escribir("posiciones.json", self._todas_posiciones())

	# ── Marcadores ────────────────────────────────────────────────────────────

	def marcadores(self, ruta: str) -> list[tuple[str, float]]:
		with self._candado:
			lista = self._todos_marcadores().get(_clave(ruta), [])
		resultado = []
		for elemento in lista:
			try:
				resultado.append((str(elemento[0]), float(elemento[1])))
			except (TypeError, ValueError, IndexError):
				continue
		return sorted(resultado, key=lambda m: m[1])

	def anadir_marcador(self, ruta: str, nombre: str, segundos: float) -> None:
		with self._candado:
			lista = self._todos_marcadores().setdefault(_clave(ruta), [])
			lista.append([nombre, round(float(segundos), 1)])
			self._escribir("marcadores.json", self._todos_marcadores())

	def quitar_marcador(self, ruta: str, indice: int) -> None:
		with self._candado:
			lista = sorted(self._todos_marcadores().get(_clave(ruta), []), key=lambda m: float(m[1]))
			if 0 <= indice < len(lista):
				lista.pop(indice)
				self._todos_marcadores()[_clave(ruta)] = lista
				self._escribir("marcadores.json", self._todos_marcadores())
