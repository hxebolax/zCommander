# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Piezas comunes de los manejadores del simulador DSM (diseño 2.0, 13.9).

Sin wx y sin dependencias de zCommander: el simulador también se ejecuta como
programa suelto (``python -I plugins/synology/simulador/servidor.py``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any


class ErrorSim(Exception):
	"""Respuesta ``{"success": false, "error": {"code": codigo, "errors": errores}}``."""

	def __init__(self, codigo: int, errores: Any = None) -> None:
		super().__init__(f"Error DSM {codigo}")
		self.codigo = int(codigo)
		self.errores = errores


@dataclass
class RespuestaBinaria:
	"""Descarga: el servidor la envía como ``application/octet-stream`` (synology.md 1.3)."""

	nombre: str
	tamano: int
	partes: Iterable[bytes]


@dataclass
class Peticion:
	"""Lo que recibe cada manejador."""

	api: str
	version: int
	metodo: str
	params: dict[str, Any]
	estado: Any
	simulador: Any
	sesion: Any = None
	#: ``False`` en el modo ``simular``: el manejador responde con la forma real SIN cambiar el estado.
	aplicar: bool = True
	ip: str = "127.0.0.1"
	archivo: bytes | None = None
	nombre_archivo: str = ""
	extra: dict[str, Any] = field(default_factory=dict)

	# Lectura cómoda de parámetros (llegan decodificados de JSON cuando la API lo declara).

	def texto(self, nombre: str, defecto: str = "") -> str:
		valor = self.params.get(nombre, defecto)
		if valor is None:
			return defecto
		if isinstance(valor, bool):
			return "true" if valor else "false"
		return str(valor)

	def entero(self, nombre: str, defecto: int = 0) -> int:
		try:
			return int(self.params.get(nombre, defecto))
		except (TypeError, ValueError):
			return defecto

	def booleano(self, nombre: str, defecto: bool = False) -> bool:
		valor = self.params.get(nombre, defecto)
		if isinstance(valor, bool):
			return valor
		return str(valor).strip().lower() in ("true", "1", "yes", "on")

	def lista(self, nombre: str) -> list[Any]:
		"""Una lista JSON, o un texto con elementos separados por comas (como acepta DSM)."""
		valor = self.params.get(nombre)
		if valor is None or valor == "":
			return []
		if isinstance(valor, list):
			return valor
		if isinstance(valor, str):
			texto = valor.strip()
			if texto.startswith("["):
				try:
					decodificado = json.loads(texto)
				except ValueError:
					decodificado = None
				if isinstance(decodificado, list):
					return decodificado
			return [p for p in texto.split(",") if p]
		return [valor]

	def exigir(self, *nombres: str) -> None:
		"""114 si falta un parámetro obligatorio."""
		for nombre in nombres:
			if nombre not in self.params or self.params[nombre] in (None, ""):
				raise ErrorSim(114)


Manejador = Callable[[Peticion], Any]


def trozos(datos: bytes, tamano: int = 64 * 1024) -> Iterator[bytes]:
	for inicio in range(0, len(datos), tamano):
		yield datos[inicio:inicio + tamano]
