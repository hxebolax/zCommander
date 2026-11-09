# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Expansión de variables (``%P``, ``%M``...) en órdenes del menú de usuario, asociaciones y programas externos.

Variables: ``%N`` nombre con extensión, ``%B`` nombre sin extensión, ``%E``
extensión, ``%P`` ruta completa del cursor, ``%D`` carpeta del panel activo,
``%O`` carpeta del otro panel, ``%T`` ruta del cursor del otro panel, ``%M``
rutas de los elementos de trabajo, ``%L`` archivo temporal con esas rutas,
``%?Título?valor%`` pide un dato, ``%%`` un «%».

Seguridad (sección 14 del diseño): para ``cmd /c`` los valores NO se pegan
en la orden. Cada valor va en una variable de entorno del proceso hijo
(``ZC_1``, ``ZC_2``...) y en la orden se escribe ``"%ZC_1%"`` entre comillas:
``cmd`` expande una sola vez y, dentro de comillas, ``& | < > ^`` no actúan.
Así un archivo llamado ``a&calc.txt`` o ``100%PATH%.txt`` no ejecuta nada.

Las palabras con variables se entrecomillan enteras (ver ``expandir``). Las
carpetas nunca acaban en barra (la raíz se da como ``C:\\.``) porque ``\\"``
rompería las comillas.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


@dataclass
class Valores:
	"""Datos de los que salen las variables (rutas locales)."""

	cursor: str = ""
	carpeta: str = ""
	otra_carpeta: str = ""
	cursor_otro: str = ""
	trabajo: Sequence[str] = field(default_factory=list)


@dataclass
class Expansion:
	"""Resultado: la orden lista para ``cmd /c`` y las variables de entorno que necesita."""

	orden: str
	entorno: dict[str, str]
	temporales: list[str]


class Cancelada(Exception):
	"""La persona canceló un ``%?Título?%``."""


def _carpeta(ruta: str) -> str:
	ruta = ruta.rstrip("\\/")
	if len(ruta) == 2 and ruta[1] == ":":
		return ruta + "\\."
	return ruta


def _partes(ruta: str) -> tuple[str, str, str]:
	nombre = os.path.basename(ruta.rstrip("\\/"))
	punto = nombre.rfind(".")
	if punto > 0:
		return nombre, nombre[:punto], nombre[punto + 1:]
	return nombre, nombre, ""


LIMITE_CMD = 8000  # cmd.exe admite 8191 caracteres por orden; se deja margen.


class DemasiadoLarga(ValueError):
	"""La orden expandida pasa del límite de cmd (con muchos elementos, use %L)."""


def _trozos(plantilla: str) -> list[tuple[str, str]]:
	"""Parte la plantilla en («espacio», texto), («comillas», texto sin comillas) y («palabra», texto)."""
	trozos: list[tuple[str, str]] = []
	i = 0
	while i < len(plantilla):
		c = plantilla[i]
		if c.isspace():
			j = i
			while j < len(plantilla) and plantilla[j].isspace():
				j += 1
			trozos.append(("espacio", plantilla[i:j]))
			i = j
		elif c == '"':
			j = plantilla.find('"', i + 1)
			j = len(plantilla) if j < 0 else j
			trozos.append(("comillas", plantilla[i + 1:j]))
			i = j + 1
		else:
			j = i
			while j < len(plantilla) and not plantilla[j].isspace() and plantilla[j] != '"':
				j += 1
			trozos.append(("palabra", plantilla[i:j]))
			i = j
	return trozos


def expandir(
	plantilla: str,
	valores: Valores,
	pedir: Callable[[str, str], str | None] | None = None,
	crear_lista: Callable[[Sequence[str]], str] | None = None,
) -> Expansion:
	"""Expande ``plantilla`` para ejecutarla con ``cmd.exe /d /v:off /s /c "orden"``.

	Reglas de comillas (sección 14 del diseño):

	- Una palabra con variables fuera de comillas se entrecomilla ENTERA y una
	  sola vez: ``%O\\%N.7z`` → ``"%ZC_1%\\%ZC_2%.7z"``.
	- Dentro de comillas que escribió la persona (``"%P"``), la variable va sin
	  comillas propias.
	- ``%M`` debe ir sola: da una referencia entrecomillada por elemento.
	- ``%%`` es un «%» literal.

	:param pedir: ``pedir(titulo, valor_inicial)`` para ``%?...?...%``; devuelve
		``None`` si se cancela (entonces se lanza ``Cancelada``).
	:param crear_lista: crea el archivo de ``%L`` y devuelve su ruta.
	:raises DemasiadoLarga: si la orden pasa del límite de cmd.
	:raises ValueError: si ``%M`` va pegada a otro texto.
	"""
	entorno: dict[str, str] = {}
	temporales: list[str] = []
	contador = [0]
	nombre, base_, extension = _partes(valores.cursor)
	simples = {
		"N": nombre, "B": base_, "E": extension, "P": valores.cursor,
		"D": _carpeta(valores.carpeta), "O": _carpeta(valores.otra_carpeta), "T": valores.cursor_otro,
	}

	def referencia(valor: str) -> str:
		contador[0] += 1
		clave = f"ZC_{contador[0]}"
		entorno[clave] = valor
		return f"%{clave}%"

	def trabajo() -> list[str]:
		return list(valores.trabajo) or ([valores.cursor] if valores.cursor else [])

	def sustituir(texto: str, dentro_comillas: bool) -> tuple[str, bool]:
		"""Devuelve (texto con referencias, ¿tenía variables?). ``%%`` queda como un «%»."""
		salida: list[str] = []
		hubo = False
		i = 0
		while i < len(texto):
			c = texto[i]
			if c != "%" or i + 1 >= len(texto):
				salida.append(c)
				i += 1
				continue
			letra = texto[i + 1]
			if letra == "%":
				# «%%» es un «%» para cmd: «%%PATH%%» llega como «%PATH%» y cmd lo expande
				# (así se usan las variables de entorno de Windows).
				salida.append("%")
				i += 2
			elif letra in simples:
				salida.append(referencia(simples[letra]))
				hubo = True
				i += 2
			elif letra == "L":
				if crear_lista is None:
					raise ValueError("Falta crear_lista para %L")
				ruta_lista = crear_lista(trabajo())
				temporales.append(ruta_lista)
				salida.append(referencia(ruta_lista))
				hubo = True
				i += 2
			elif letra == "?":
				fin = texto.find("%", i + 2)
				if fin < 0:
					salida.append(texto[i:])
					break
				titulo, _, inicial = texto[i + 2:fin].partition("?")
				respuesta = pedir(titulo, inicial) if pedir else inicial
				if respuesta is None:
					raise Cancelada()
				if '"' in respuesta:
					raise ValueError("El dato escrito no puede contener comillas dobles")
				salida.append(referencia(respuesta))
				hubo = True
				i = fin + 1
			elif letra == "M":
				raise ValueError("%M debe ir sola, separada por espacios")
			else:
				salida.append(c)
				i += 1
		return "".join(salida), hubo

	partes: list[str] = []
	for tipo, texto in _trozos(plantilla):
		if tipo == "espacio":
			partes.append(texto)
		elif tipo == "comillas":
			if "%M" in texto:
				raise ValueError("%M no puede ir entre comillas")
			cuerpo, _ = sustituir(texto, True)
			partes.append(f'"{cuerpo}"')
		elif texto == "%M":
			partes.append(" ".join(f'"{referencia(r)}"' for r in trabajo()))
		else:
			cuerpo, hubo = sustituir(texto, False)
			partes.append(f'"{cuerpo}"' if hubo else cuerpo)
	orden = "".join(partes)
	largo = len(orden) + sum(len(v) for v in entorno.values())
	if largo > LIMITE_CMD:
		raise DemasiadoLarga(f"La orden expandida tiene unos {largo} caracteres; con muchos elementos use %L")
	return Expansion(orden, entorno, temporales)


def linea_cmd(orden: str) -> str:
	"""Línea completa para ``CreateProcess``: sin AutoRun, sin expansión retardada (``!``) y con comillas exactas."""
	return f'cmd.exe /d /v:off /s /c "{orden}"'


def entrecomillar_argumento(valor: str) -> str:
	"""Comillas según las reglas de ``CommandLineToArgvW`` (barras antes de comillas se duplican)."""
	if valor and not any(c in valor for c in ' \t"'):
		return valor
	resultado = ['"']
	barras = 0
	for caracter in valor:
		if caracter == "\\":
			barras += 1
			continue
		if caracter == '"':
			resultado.append("\\" * (barras * 2 + 1) + '"')
		else:
			resultado.append("\\" * barras + caracter)
		barras = 0
	resultado.append("\\" * (barras * 2) + '"')
	return "".join(resultado)


def expandir_directo(plantilla: str, valores: Valores) -> str:
	"""Expansión para lanzar un programa sin ``cmd`` (visor y editor externos).

	``CreateProcess`` no interpreta ``& | %``; solo hay que entrecomillar bien
	(reglas de ``CommandLineToArgvW``). Dentro de comillas que escribió la
	persona (``"C:\\Programas\\editor.exe" "%P"``) el valor va sin comillas
	propias y con las barras finales duplicadas. ``%%`` es un «%».
	"""
	nombre, base_, extension = _partes(valores.cursor)
	simples = {
		"N": nombre, "B": base_, "E": extension, "P": valores.cursor,
		"D": _carpeta(valores.carpeta), "O": _carpeta(valores.otra_carpeta), "T": valores.cursor_otro,
	}

	def sustituir(texto: str, dentro: bool) -> tuple[str, bool]:
		salida: list[str] = []
		hubo = False
		i = 0
		while i < len(texto):
			if texto[i] == "%" and i + 1 < len(texto):
				letra = texto[i + 1]
				if letra == "%":
					salida.append("%")
					i += 2
					continue
				if letra in simples:
					salida.append(simples[letra])
					hubo = True
					i += 2
					continue
			salida.append(texto[i])
			i += 1
		return "".join(salida), hubo

	def cerrar(cuerpo: str) -> str:
		finales = len(cuerpo) - len(cuerpo.rstrip("\\"))
		return f'"{cuerpo}{"\\" * finales}"'

	partes: list[str] = []
	for tipo, texto in _trozos(plantilla):
		if tipo == "espacio":
			partes.append(texto)
		elif tipo == "comillas":
			cuerpo, _hubo = sustituir(texto, True)
			partes.append(cerrar(cuerpo))
		elif texto == "%M":
			rutas = list(valores.trabajo) or [valores.cursor]
			partes.append(" ".join(entrecomillar_argumento(r) for r in rutas))
		else:
			cuerpo, hubo = sustituir(texto, False)
			partes.append(entrecomillar_argumento(cuerpo) if hubo else cuerpo)
	return "".join(partes)
