# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cesta: rutas reunidas desde varias carpetas para operar con ellas juntas."""

from __future__ import annotations

from collections.abc import Iterable


class Cesta:
	"""Lista ordenada y sin duplicados (sin distinguir mayúsculas)."""

	def __init__(self, rutas: Iterable[str] = ()) -> None:
		self._rutas: list[str] = []
		self.anadir(rutas)

	def anadir(self, rutas: Iterable[str]) -> int:
		"""Añade las que no estaban; devuelve cuántas se añadieron."""
		presentes = {r.casefold() for r in self._rutas}
		nuevas = 0
		for ruta in rutas:
			if ruta and ruta.casefold() not in presentes:
				self._rutas.append(ruta)
				presentes.add(ruta.casefold())
				nuevas += 1
		return nuevas

	def quitar(self, rutas: Iterable[str]) -> None:
		fuera = {r.casefold() for r in rutas}
		self._rutas = [r for r in self._rutas if r.casefold() not in fuera]

	def vaciar(self) -> None:
		self._rutas.clear()

	def rutas(self) -> list[str]:
		return list(self._rutas)

	def __len__(self) -> int:
		return len(self._rutas)
