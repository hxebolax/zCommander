# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Historial de carpetas de un panel (atrás, adelante, lista) y de órdenes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HistorialCarpetas:
	"""Lista de ubicaciones visitadas con un puntero, como un navegador.

	Las ubicaciones son textos (lo que devuelve ``Proveedor.mostrar``); al
	volver se reabren con el resolver de rutas.
	"""

	maximo: int = 100
	elementos: list[str] = field(default_factory=list)
	posicion: int = -1

	def visitar(self, ruta: str) -> None:
		"""Añade ``ruta`` tras la posición actual (descarta el «adelante»)."""
		if 0 <= self.posicion < len(self.elementos) and self.elementos[self.posicion] == ruta:
			return
		del self.elementos[self.posicion + 1:]
		self.elementos.append(ruta)
		if len(self.elementos) > self.maximo:
			del self.elementos[: len(self.elementos) - self.maximo]
		self.posicion = len(self.elementos) - 1

	def puede_atras(self) -> bool:
		return self.posicion > 0

	def puede_adelante(self) -> bool:
		return self.posicion < len(self.elementos) - 1

	def atras(self) -> str | None:
		if not self.puede_atras():
			return None
		self.posicion -= 1
		return self.elementos[self.posicion]

	def adelante(self) -> str | None:
		if not self.puede_adelante():
			return None
		self.posicion += 1
		return self.elementos[self.posicion]

	def recientes(self) -> list[str]:
		"""Sin repetidos, la más reciente primero (para el diálogo de historial)."""
		vistos: set[str] = set()
		resultado = []
		for ruta in reversed(self.elementos):
			clave = ruta.casefold()
			if clave not in vistos:
				vistos.add(clave)
				resultado.append(ruta)
		return resultado

	def como_dict(self) -> dict:
		return {"elementos": list(self.elementos), "posicion": self.posicion}

	@classmethod
	def desde_dict(cls, datos: dict, maximo: int = 100) -> HistorialCarpetas:
		elementos = [str(x) for x in datos.get("elementos", []) if isinstance(x, str)][-maximo:]
		posicion = int(datos.get("posicion", len(elementos) - 1))
		return cls(maximo, elementos, max(-1, min(posicion, len(elementos) - 1)))


@dataclass
class HistorialOrdenes:
	"""Órdenes de la línea de órdenes (la más reciente al final, sin duplicados seguidos)."""

	maximo: int = 200
	elementos: list[str] = field(default_factory=list)
	_cursor: int | None = None

	def anadir(self, orden: str) -> None:
		orden = orden.strip()
		if not orden:
			return
		if orden in self.elementos:
			self.elementos.remove(orden)
		self.elementos.append(orden)
		del self.elementos[: max(0, len(self.elementos) - self.maximo)]
		self._cursor = None

	def mover(self, paso: int) -> str | None:
		"""Arriba (-1) y Abajo (+1) en la línea de órdenes. ``None`` al pasar del final (línea vacía)."""
		if not self.elementos:
			return None
		if self._cursor is None:
			self._cursor = len(self.elementos)
		self._cursor = max(0, min(len(self.elementos), self._cursor + paso))
		if self._cursor == len(self.elementos):
			return ""
		return self.elementos[self._cursor]

	def reiniciar_cursor(self) -> None:
		self._cursor = None
