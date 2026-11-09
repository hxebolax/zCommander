# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Favoritas y frecuentes de la paleta de órdenes (diseño 2.0, 10.14). Sin wx.

``data/config/paleta.json``: ``{"version": 1, "favoritas": [...], "usos": {"id": número}}``.

El servicio cuenta los usos en memoria con el evento ``al_terminar_orden`` del
bus y guarda de forma diferida: 5 s después del último cambio y al cerrar,
nunca en cada orden (una macro o un dedo rápido no deben escribir el disco
cien veces).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.core import almacen_json

log = logging.getLogger(__name__)

ARCHIVO = "paleta.json"
VERSION = 1
POR_DEFECTO: dict[str, Any] = {"version": VERSION, "favoritas": [], "usos": {}}
FRECUENTES = 10
RETRASO_S = 5.0
#: Órdenes que no cuentan como uso (las de la propia paleta y las de consulta rápida).
SIN_CONTAR = frozenset({"paleta_ordenes", "cancelar", "cambiar_panel"})


class Paleta:
	def __init__(self, carpeta: Path | None = None, retraso_s: float = RETRASO_S) -> None:
		self._carpeta = carpeta
		self._retraso = retraso_s
		self._candado = threading.RLock()
		self._temporizador: threading.Timer | None = None
		datos = almacen_json.leer(ARCHIVO, POR_DEFECTO, carpeta)
		self.favoritas: list[str] = [str(f) for f in datos.get("favoritas", []) or [] if isinstance(f, str)]
		usos = datos.get("usos") if isinstance(datos.get("usos"), dict) else {}
		self.usos: dict[str, int] = {str(k): int(v) for k, v in usos.items() if isinstance(v, int) and not isinstance(v, bool) and v > 0}
		self._pendiente = False

	# Consultas -------------------------------------------------------------

	def es_favorita(self, id_orden: str) -> bool:
		return id_orden in self.favoritas

	def frecuentes(self, excluir: Iterable[str] = (), cuantas: int = FRECUENTES) -> list[str]:
		fuera = set(excluir)
		with self._candado:
			ordenadas = sorted(((n, i) for i, n in self.usos.items() if i not in fuera), key=lambda t: (-t[0], t[1]))
		return [i for _n, i in ordenadas[:cuantas]]

	def primero(self, disponibles: Iterable[str]) -> list[str]:
		"""Orden de la paleta sin búsqueda: favoritas, después las 10 más usadas (de las disponibles)."""
		existentes = set(disponibles)
		favoritas = [f for f in self.favoritas if f in existentes]
		frecuentes = [f for f in self.frecuentes(excluir=favoritas, cuantas=len(self.usos)) if f in existentes][:FRECUENTES]
		return favoritas + frecuentes

	# Cambios ---------------------------------------------------------------

	def alternar_favorita(self, id_orden: str) -> bool:
		"""Marca o desmarca; devuelve si queda como favorita."""
		with self._candado:
			if id_orden in self.favoritas:
				self.favoritas.remove(id_orden)
				queda = False
			else:
				self.favoritas.append(id_orden)
				queda = True
		self._programar()
		return queda

	def contar(self, id_orden: str) -> None:
		if not id_orden or id_orden in SIN_CONTAR:
			return
		with self._candado:
			self.usos[id_orden] = self.usos.get(id_orden, 0) + 1
		self._programar()

	def al_terminar_orden(self, id: str = "", ok: bool = True, **_datos: Any) -> None:
		"""Suscriptor de ``al_terminar_orden`` del bus."""
		if ok:
			self.contar(id)

	# Guardado diferido -------------------------------------------------------

	def _programar(self) -> None:
		with self._candado:
			self._pendiente = True
			if self._temporizador is not None:
				self._temporizador.cancel()
			if self._retraso <= 0:
				self._temporizador = None
			else:
				self._temporizador = threading.Timer(self._retraso, self.guardar)
				self._temporizador.daemon = True
				self._temporizador.name = "paleta-guardar"
				self._temporizador.start()
		if self._retraso <= 0:
			self.guardar()

	def guardar(self) -> None:
		with self._candado:
			if not self._pendiente:
				return
			datos = {"version": VERSION, "favoritas": list(self.favoritas), "usos": dict(self.usos)}
			self._pendiente = False
		try:
			almacen_json.escribir(ARCHIVO, datos, self._carpeta)
		except OSError:
			log.exception("No se pudo guardar paleta.json")

	def cerrar(self) -> None:
		with self._candado:
			if self._temporizador is not None:
				self._temporizador.cancel()
				self._temporizador = None
		self.guardar()


_actual: list[Paleta | None] = [None]


def actual() -> Paleta:
	"""La paleta de la sesión (se crea al pedirla)."""
	if _actual[0] is None:
		_actual[0] = Paleta()
	return _actual[0]


def fijar(paleta: Paleta | None) -> None:
	_actual[0] = paleta
