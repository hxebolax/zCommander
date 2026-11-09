# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tiempos del reproductor: «1:23:00» ↔ 4980 segundos y «12:30 de 45:10, 27 %». Sin wx.

Se escriben como los relojes de los reproductores (horas solo si hacen falta)
porque es lo que la persona escribe en «Ir a un tiempo» y lo que espera oír.
"""

from __future__ import annotations

import builtins
import re


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def formatear(segundos: float) -> str:
	"""4980 → «1:23:00»; 750 → «12:30»; 5 → «0:05». Los negativos cuentan como 0."""
	total = max(0, int(segundos))
	horas, resto = divmod(total, 3600)
	minutos, segundos_ = divmod(resto, 60)
	if horas:
		return f"{horas}:{minutos:02d}:{segundos_:02d}"
	return f"{minutos}:{segundos_:02d}"


_UNIDADES = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*(?:min|m))?\s*(?:(\d+)\s*s)?\s*$", re.IGNORECASE)


def interpretar(texto: str) -> float:
	"""«1:23:00» → 4980; «83:00» → 4980; «45» → 45; «1 h 5 min» → 3900.

	:raises ValueError: con un mensaje en español que se puede enseñar tal cual.
	"""
	limpio = texto.strip().replace(",", ".")
	if not limpio:
		raise ValueError(_("Escriba un tiempo, por ejemplo 1:23:00 o 12:30."))
	if ":" in limpio:
		partes = limpio.split(":")
		if len(partes) > 3 or not all(p.strip() for p in partes):
			raise ValueError(_("«{t}» no es un tiempo válido: use horas:minutos:segundos, como 1:23:00.").format(t=texto))
		try:
			numeros = [float(p) for p in partes]
		except ValueError as error:
			raise ValueError(_("«{t}» no es un tiempo válido: use horas:minutos:segundos, como 1:23:00.").format(t=texto)) from error
		if any(n < 0 for n in numeros) or any(n >= 60 for n in numeros[1:]):
			raise ValueError(_("«{t}» no es un tiempo válido: los minutos y los segundos van de 0 a 59.").format(t=texto))
		total = 0.0
		for numero in numeros:
			total = total * 60 + numero
		return total
	try:
		valor = float(limpio)
	except ValueError:
		coincidencia = _UNIDADES.match(limpio)
		if not coincidencia or not any(coincidencia.groups()):
			raise ValueError(_("«{t}» no es un tiempo válido: escriba por ejemplo 1:23:00, 12:30 o 45.").format(t=texto)) from None
		horas, minutos, segundos = (int(g or 0) for g in coincidencia.groups())
		return float(horas * 3600 + minutos * 60 + segundos)
	if valor < 0:
		raise ValueError(_("El tiempo no puede ser negativo."))
	return valor


def interpretar_destino(texto: str, duracion: float) -> float:
	"""Lo que se escribe en «Ir a»: un tiempo o un porcentaje («50 %», «50%»)."""
	limpio = texto.strip()
	if limpio.endswith("%"):
		try:
			porcentaje = float(limpio[:-1].strip().replace(",", "."))
		except ValueError as error:
			raise ValueError(_("«{t}» no es un porcentaje válido.").format(t=texto)) from error
		if not 0 <= porcentaje <= 100:
			raise ValueError(_("El porcentaje va de 0 a 100."))
		if duracion <= 0:
			raise ValueError(_("No se sabe la duración de esta pista: escriba un tiempo en lugar de un porcentaje."))
		return duracion * porcentaje / 100
	return interpretar(limpio)


def porcentaje(posicion: float, duracion: float) -> int:
	if duracion <= 0:
		return 0
	return max(0, min(100, int(posicion * 100 / duracion)))


def decir_posicion(posicion: float, duracion: float) -> str:
	"""«12:30 de 45:10, 27 %»; sin duración conocida, solo la posición."""
	if duracion <= 0:
		return _("{p}, duración desconocida").format(p=formatear(posicion))
	return _("{p} de {d}, {c} %").format(p=formatear(posicion), d=formatear(duracion), c=porcentaje(posicion, duracion))


def texto_velocidad(velocidad: float) -> str:
	"""1.25 → «1,25x»; 1.0 → «1x» (coma decimal, como se lee en español)."""
	texto = f"{velocidad:.2f}".rstrip("0").rstrip(".")
	return texto.replace(".", ",") + "x"
