# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Patrones de marcado y de filtro al estilo Norton y Total Commander.

Sintaxis (sección 5 del diseño):

- Comodines ``*`` y ``?``; varios patrones separados por ``;``, ``,`` o espacio.
- Exclusión con ``|``: lo que va detrás se resta (``*.* | *.bak``).
- ``*.*`` y ``*`` coinciden con todo, también con nombres sin extensión (como
  en Windows, no como en Unix, donde ``*.*`` exigiría un punto).
- Sin distinguir mayúsculas. Opcionalmente sin distinguir acentos (filtro rápido).
"""

from __future__ import annotations

import fnmatch
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

_SEPARADORES = re.compile(r"[;,\s]+")


def sin_acentos(texto: str) -> str:
	"""Quita tildes y diéresis para comparar («canción» → «cancion»); conserva la ñ."""
	descompuesto = unicodedata.normalize("NFD", texto)
	resultado = []
	for i, caracter in enumerate(descompuesto):
		if unicodedata.category(caracter) == "Mn":
			# La tilde de la ñ (U+0303 detrás de n o N) se conserva.
			if caracter == "̃" and i and descompuesto[i - 1] in "nN":
				resultado.append(caracter)
			continue
		resultado.append(caracter)
	return unicodedata.normalize("NFC", "".join(resultado))


@lru_cache(maxsize=256)
def _compilar(patron: str) -> re.Pattern[str]:
	if patron in ("*", "*.*"):
		return re.compile(r".*", re.DOTALL)
	# «nombre.*» también coincide con «nombre» (sin extensión), como en Windows.
	if patron.endswith(".*"):
		base = fnmatch.translate(patron[:-2])
		base = base[: base.rfind(r"\Z")] if r"\Z" in base else base
		return re.compile(rf"(?:{base})(?:\..*)?\Z", re.IGNORECASE | re.DOTALL)
	return re.compile(fnmatch.translate(patron), re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class Patron:
	"""Patrón ya analizado: listas de inclusión y exclusión."""

	incluir: tuple[str, ...]
	excluir: tuple[str, ...]
	ignorar_acentos: bool = False

	@classmethod
	def analizar(cls, texto: str, ignorar_acentos: bool = False) -> Patron:
		"""Convierte el texto escrito por la persona en un ``Patron``.

		Un texto vacío equivale a ``*`` (todo).
		"""
		texto = (texto or "").strip()
		incluir_txt, _, excluir_txt = texto.partition("|")
		incluir = tuple(p for p in _SEPARADORES.split(incluir_txt.strip()) if p)
		excluir = tuple(p for p in _SEPARADORES.split(excluir_txt.strip()) if p)
		return cls(incluir or ("*",), excluir, ignorar_acentos)

	def _normalizar(self, nombre: str) -> str:
		return sin_acentos(nombre) if self.ignorar_acentos else nombre

	def coincide(self, nombre: str) -> bool:
		"""``True`` si el nombre coincide con algún patrón de inclusión y con ninguno de exclusión."""
		nombre = self._normalizar(nombre)
		if not any(_compilar(self._normalizar(p)).match(nombre) for p in self.incluir):
			return False
		return not any(_compilar(self._normalizar(p)).match(nombre) for p in self.excluir)

	def es_todo(self) -> bool:
		"""``True`` si el patrón no filtra nada."""
		return not self.excluir and any(p in ("*", "*.*") for p in self.incluir)

	def texto(self) -> str:
		"""Representación canónica para mostrar en la etiqueta del panel."""
		base = ";".join(self.incluir)
		return f"{base} | {';'.join(self.excluir)}" if self.excluir else base


def coincide(nombre: str, patron: str) -> bool:
	"""Atajo: ``Patron.analizar(patron).coincide(nombre)``."""
	return Patron.analizar(patron).coincide(nombre)


def contiene(nombre: str, texto: str) -> bool:
	"""Filtro rápido: el nombre contiene el texto, sin mayúsculas ni acentos."""
	if not texto:
		return True
	return sin_acentos(texto).casefold() in sin_acentos(nombre).casefold()


def filtrar(nombres: Iterable[str], patron: str) -> list[str]:
	"""Nombres que coinciden con el patrón, en el mismo orden."""
	analizado = Patron.analizar(patron)
	return [n for n in nombres if analizado.coincide(n)]
