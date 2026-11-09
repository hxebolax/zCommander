# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Nombres libres («nombre (2).ext») y temporales cortos para la copia."""

from __future__ import annotations

import secrets
from collections.abc import Callable


def partir(nombre: str) -> tuple[str, str]:
	"""(base, extensión con punto). «.gitignore» no tiene extensión."""
	punto = nombre.rfind(".")
	if punto <= 0:
		return nombre, ""
	return nombre[:punto], nombre[punto:]


def nombre_libre(nombre: str, existe: Callable[[str], bool], formato: str = "{base} ({n}){ext}") -> str:
	"""Primer «base (n).ext» con n ≥ 2 que no existe."""
	base, ext = partir(nombre)
	n = 2
	while True:
		candidato = formato.format(base=base, n=n, ext=ext)
		if not existe(candidato):
			return candidato
		n += 1


def nombre_copia(nombre: str, existe: Callable[[str], bool]) -> str:
	"""Para duplicar: «nombre (copia).ext», y si existe «nombre (copia 2).ext»..."""
	base, ext = partir(nombre)
	candidato = f"{base} (copia){ext}"
	n = 2
	while existe(candidato):
		candidato = f"{base} (copia {n}){ext}"
		n += 1
	return candidato


def temporal() -> str:
	"""«~zc1a2b3c4d.tmp»: corto (no supera el límite de nombre) y fácil de reconocer."""
	return f"~zc{secrets.token_hex(4)}.tmp"
