# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Alias de la línea de órdenes (diseño 2.0, 10.8). Sin wx.

``data/config/alias.json``: ``{"version": 1, "alias": [{"nombre": "ll", "orden": "dir /a %1"}]}``.

- ``%1`` a ``%9`` son los argumentos escritos tras el alias y ``%*`` todos.
- Las variables de 1.x §8.17 (``%P``, ``%M``...) valen igual.
- **Protección contra inyección** (1.x §14): los argumentos NO se pegan en la
  orden. Cada uno va, como las variables, en una variable de entorno del
  proceso hijo (``ZC_1``...) y en la orden se escribe ``"%ZC_1%"`` entre
  comillas: un argumento ``a&calc`` no ejecuta nada. Para eso se reutiliza
  ``variables.expandir``: cada ``%n`` se convierte en una pregunta interna
  ``%?\\x01n?%`` que se contesta con el argumento.
- Un alias cuya orden empieza por ``zc `` es una orden interna: se sustituye
  como texto (no pasa por ``cmd``) y la atiende la ventana sin lanzar procesos.
"""

from __future__ import annotations

import builtins
import logging
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import almacen_json
from app.services import variables

log = logging.getLogger(__name__)

ARCHIVO = "alias.json"
VERSION = 1
POR_DEFECTO: dict[str, Any] = {"version": VERSION, "alias": []}
NOMBRE_VALIDO = re.compile(r"^[^\s\"%&|<>^]{1,40}$")
_MARCA = "\x01"
_NUMERADO = re.compile(r"%([1-9*])")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorAlias(ValueError):
	"""Un alias no válido (mensaje en español)."""


@dataclass
class Alias:
	nombre: str
	orden: str

	def como_dict(self) -> dict[str, str]:
		return {"nombre": self.nombre, "orden": self.orden}


def validar(alias: Alias, existentes: Sequence[Alias] = (), anterior: str = "") -> None:
	if not NOMBRE_VALIDO.match(alias.nombre):
		raise ErrorAlias(_("El nombre de un alias es una sola palabra, sin espacios, comillas ni & | < > ^ %"))
	if alias.nombre.lower() == "zc":
		raise ErrorAlias(_("«zc» está reservado para las órdenes internas"))
	if not alias.orden.strip():
		raise ErrorAlias(_("Escriba la orden del alias"))
	for otro in existentes:
		if otro.nombre.casefold() == alias.nombre.casefold() and otro.nombre.casefold() != anterior.casefold():
			raise ErrorAlias(_("Ya hay un alias «{n}»").format(n=alias.nombre))


def cargar(carpeta: Path | None = None) -> list[Alias]:
	datos = almacen_json.leer(ARCHIVO, POR_DEFECTO, carpeta)
	resultado: list[Alias] = []
	for elemento in datos.get("alias", []) or []:
		if isinstance(elemento, dict) and isinstance(elemento.get("nombre"), str) and isinstance(elemento.get("orden"), str):
			alias = Alias(elemento["nombre"].strip(), elemento["orden"])
			try:
				validar(alias, resultado)
			except ErrorAlias as error:
				log.warning("Alias descartado (%s): %s", alias.nombre, error)
				continue
			resultado.append(alias)
	return resultado


def guardar(lista: Sequence[Alias], carpeta: Path | None = None) -> None:
	almacen_json.escribir(ARCHIVO, {"version": VERSION, "alias": [a.como_dict() for a in lista]}, carpeta)


def buscar(lista: Sequence[Alias], nombre: str) -> Alias | None:
	clave = nombre.casefold()
	return next((a for a in lista if a.nombre.casefold() == clave), None)


def separar(texto: str) -> tuple[str, list[str]]:
	"""Primera palabra y argumentos (respeta comillas: ``"mi carpeta"`` es un solo argumento)."""
	texto = texto.strip()
	nombre, _espacio, resto = texto.partition(" ")
	try:
		argumentos = shlex.split(resto, posix=False) if resto.strip() else []
	except ValueError:
		argumentos = resto.split()
	return nombre, [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a for a in argumentos]


@dataclass(frozen=True)
class Expandido:
	"""Resultado: la orden lista y su entorno (vacío en las órdenes ``zc``)."""

	orden: str
	entorno: dict[str, str]
	interna: bool = False


def _sustituir_texto(plantilla: str, argumentos: Sequence[str]) -> str:
	def numero(m: re.Match) -> str:
		if m.group(1) == "*":
			return " ".join(argumentos)
		indice = int(m.group(1)) - 1
		return argumentos[indice] if indice < len(argumentos) else ""

	return _NUMERADO.sub(numero, plantilla).strip()


def expandir(alias: Alias, argumentos: Sequence[str], valores: variables.Valores | None = None) -> Expandido:
	"""Expande un alias con sus argumentos (protegido como las variables de 1.x §14).

	:raises ValueError: argumentos con comillas dobles, ``%M`` mal puesta o una orden demasiado larga.
	"""
	plantilla = alias.orden.strip()
	if plantilla.lower().startswith("zc "):
		return Expandido(_sustituir_texto(plantilla, argumentos), {}, interna=True)
	# %* se convierte en %1 %2 ... %n: cada argumento va en su propia variable de entorno.
	plantilla = plantilla.replace("%*", " ".join(f"%{i}" for i in range(1, min(len(argumentos), 9) + 1)))

	def a_pregunta(m: re.Match) -> str:
		return f"%?{_MARCA}{m.group(1)}?%"

	plantilla = re.sub(r"%([1-9])", a_pregunta, plantilla)

	def pedir(titulo: str, _inicial: str) -> str:
		if titulo.startswith(_MARCA):
			indice = int(titulo[1:]) - 1
			return argumentos[indice] if indice < len(argumentos) else ""
		return _inicial

	expansion = variables.expandir(plantilla, valores or variables.Valores(), pedir=pedir)
	return Expandido(expansion.orden, dict(expansion.entorno))


def expandir_linea(texto: str, lista: Sequence[Alias], valores: variables.Valores | None = None) -> Expandido | None:
	"""Si la primera palabra de ``texto`` es un alias, su expansión; si no, ``None``."""
	nombre, argumentos = separar(texto)
	alias = buscar(lista, nombre) if nombre else None
	if alias is None:
		return None
	return expandir(alias, argumentos, valores)


def vista_previa(alias: Alias, argumentos: Sequence[str], valores: variables.Valores | None = None) -> str:
	"""La orden expandida tal como la leería la persona («Probar»): las referencias, con su valor."""
	expandido = expandir(alias, argumentos, valores)
	texto = expandido.orden
	for clave, valor in expandido.entorno.items():
		texto = texto.replace(f"%{clave}%", valor)
	return texto
