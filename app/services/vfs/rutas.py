# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Rutas de Windows: normalizar, prefijo de rutas largas y nombres válidos.

Por qué existe: Windows rechaza nombres reservados (CON, NUL, COM1...), ciertos
caracteres y los nombres que acaban en espacio o punto; y muchas API fallan
con rutas de más de 259 caracteres salvo que lleven el prefijo ``\\\\?\\``.
Centralizarlo aquí evita que cada operación lo resuelva a su manera.
"""

from __future__ import annotations

import builtins
import ntpath
import os
import re

LIMITE_RUTA = 259
PREFIJO_LARGO = "\\\\?\\"
PREFIJO_UNC_LARGO = "\\\\?\\UNC\\"

CARACTERES_PROHIBIDOS = '<>:"/\\|?*'
_RESERVADOS = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)} | {
	"COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³", "CONIN$", "CONOUT$",
}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def problema_en_nombre(nombre: str) -> str | None:
	"""Explica por qué ``nombre`` no vale en Windows, o ``None`` si vale.

	Solo valida un componente (sin barras). Los mensajes dicen qué falla para
	que la persona pueda corregirlo sin adivinar.
	"""
	if not nombre or not nombre.strip():
		return _("El nombre no puede estar vacío.")
	if nombre in (".", ".."):
		return _("«{nombre}» no es un nombre válido.").format(nombre=nombre)
	for caracter in nombre:
		if caracter in CARACTERES_PROHIBIDOS:
			return _("El nombre no puede contener el carácter {c}").format(c=caracter)
		if ord(caracter) < 32:
			return _("El nombre no puede contener caracteres de control.")
	if nombre[-1] in " .":
		return _("El nombre no puede terminar en espacio ni en punto.")
	base = nombre.split(".", 1)[0].rstrip(" ").upper()
	if base in _RESERVADOS:
		return _("«{base}» es un nombre reservado de Windows.").format(base=base)
	if len(nombre) > 255:
		return _("El nombre es demasiado largo (máximo 255 caracteres).")
	return None


def nombre_valido(nombre: str) -> bool:
	return problema_en_nombre(nombre) is None


def problema_en_ruta_relativa(texto: str) -> str | None:
	"""Valida «a\\b\\c» (crear carpetas anidadas): cada componente por separado."""
	partes = [p for p in re.split(r"[\\/]", texto) if p != ""]
	if not partes:
		return _("El nombre no puede estar vacío.")
	for parte in partes:
		problema = problema_en_nombre(parte)
		if problema:
			return problema
	return None


def normalizar(ruta: str) -> str:
	"""Ruta absoluta y normalizada, sin prefijo largo y sin barra final (salvo en la raíz)."""
	ruta = quitar_prefijo(os.path.expandvars(os.path.expanduser(ruta.strip().strip('"'))))
	if re.fullmatch(r"[A-Za-z]:", ruta):
		ruta += "\\"
	ruta = ntpath.normpath(ntpath.abspath(ruta)) if not ruta.startswith("\\\\") else ntpath.normpath(ruta)
	if re.fullmatch(r"[A-Za-z]:\\", ruta):
		return ruta[0].upper() + ruta[1:]
	if len(ruta) >= 2 and ruta[1] == ":":
		ruta = ruta[0].upper() + ruta[1:]
	return ruta.rstrip("\\") if not es_raiz(ruta) else ruta


def es_raiz(ruta: str) -> bool:
	"""``C:\\`` o ``\\\\servidor\\recurso``."""
	ruta = quitar_prefijo(ruta)
	if re.fullmatch(r"[A-Za-z]:\\?", ruta):
		return True
	partes = [p for p in ruta.split("\\") if p]
	return ruta.startswith("\\\\") and len(partes) <= 2


def raiz(ruta: str) -> str:
	"""``C:\\`` de ``C:\\a\\b``; ``\\\\srv\\recurso\\`` de una ruta UNC."""
	ruta = quitar_prefijo(ruta)
	unidad, _resto = ntpath.splitdrive(ruta)
	if not unidad:
		return ruta
	return unidad + "\\" if not unidad.endswith("\\") else unidad


def padre(ruta: str) -> str | None:
	"""Carpeta superior; ``None`` en la raíz. ``\\\\servidor`` es padre de ``\\\\servidor\\recurso``."""
	ruta = normalizar(ruta)
	if ruta.startswith("\\\\"):
		partes = [p for p in ruta.split("\\") if p]
		if len(partes) <= 1:
			return None
		if len(partes) == 2:
			return "\\\\" + partes[0]
		return "\\\\" + "\\".join(partes[:-1])
	if es_raiz(ruta):
		return None
	return normalizar(ntpath.dirname(ruta))


def con_prefijo_largo(ruta: str) -> str:
	"""Añade ``\\\\?\\`` si la ruta supera el límite clásico (y solo si es absoluta)."""
	if ruta.startswith(PREFIJO_LARGO) or len(ruta) <= LIMITE_RUTA - 12:
		# Margen de 12: CreateDirectory exige dejar sitio para un nombre 8.3.
		return ruta
	ruta = ntpath.normpath(ruta)
	if ruta.startswith("\\\\"):
		return PREFIJO_UNC_LARGO + ruta[2:]
	if len(ruta) >= 2 and ruta[1] == ":":
		return PREFIJO_LARGO + ruta
	return ruta


def quitar_prefijo(ruta: str) -> str:
	if ruta.startswith(PREFIJO_UNC_LARGO):
		return "\\\\" + ruta[len(PREFIJO_UNC_LARGO):]
	if ruta.startswith(PREFIJO_LARGO):
		return ruta[len(PREFIJO_LARGO):]
	return ruta


def es_larga(ruta: str) -> bool:
	return len(quitar_prefijo(ruta)) > LIMITE_RUTA


def esta_dentro(ruta: str, carpeta: str) -> bool:
	"""``True`` si ``ruta`` es ``carpeta`` o está dentro de ella (sin distinguir mayúsculas)."""
	r = normalizar(ruta).casefold()
	c = normalizar(carpeta).casefold().rstrip("\\")
	return r == c or r.startswith(c + "\\")


def mismo_volumen(a: str, b: str) -> bool:
	"""Misma unidad o mismo recurso UNC."""
	return raiz(normalizar(a)).casefold() == raiz(normalizar(b)).casefold()


def unir(carpeta: str, nombre: str) -> str:
	return ntpath.join(carpeta, nombre)
