# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sumas de comprobación: calcular, escribir y leer archivos de sumas (sección 8.19).

Formatos:

- **SFV** (CRC32): una línea ``nombre CRC`` por archivo, comentarios con «;».
- **md5sum / sha*sum** y **b2sum**: ``suma *nombre`` (el asterisco indica modo
  binario, el que entienden ``sha256sum -c`` y las herramientas de Windows).
  Al leer también se aceptan ``suma  nombre`` (modo texto) y el estilo BSD
  ``SHA256 (nombre) = suma``.

Los nombres se escriben relativos a la carpeta del archivo de sumas con «\\»
(como Total Commander); al verificar se aceptan «\\» y «/».

Sin wx: lo usan las operaciones de ``operaciones/comprimir.py`` y sus pruebas.
"""

from __future__ import annotations

import builtins
import hashlib
import re
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO

from app.services.vfs import base

BLOQUE = 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Algoritmo:
	"""Un algoritmo de suma: identificador, nombre visible, extensión del archivo y longitud en hexadecimal."""

	id: str
	nombre: str
	extension: str
	longitud: int


ALGORITMOS: tuple[Algoritmo, ...] = (
	Algoritmo("crc32", "CRC32 (SFV)", ".sfv", 8),
	Algoritmo("md5", "MD5", ".md5", 32),
	Algoritmo("sha1", "SHA-1", ".sha1", 40),
	Algoritmo("sha256", "SHA-256", ".sha256", 64),
	Algoritmo("sha512", "SHA-512", ".sha512", 128),
	Algoritmo("blake2b", "BLAKE2b", ".blake2b", 128),
)
POR_ID = {a.id: a for a in ALGORITMOS}
POR_EXTENSION = {a.extension: a for a in ALGORITMOS} | {".sha": POR_ID["sha1"], ".b2": POR_ID["blake2b"]}


def algoritmo_de_archivo(nombre: str) -> Algoritmo | None:
	"""Algoritmo según la extensión del archivo de sumas («copia.sha256» → SHA-256)."""
	punto = nombre.rfind(".")
	return POR_EXTENSION.get(nombre[punto:].lower()) if punto >= 0 else None


def es_archivo_de_sumas(nombre: str) -> bool:
	return algoritmo_de_archivo(nombre) is not None


class _Crc32:
	"""Misma interfaz que ``hashlib`` para el CRC32 de ``zlib``."""

	def __init__(self) -> None:
		self._valor = 0

	def update(self, datos: bytes) -> None:
		self._valor = zlib.crc32(datos, self._valor)

	def hexdigest(self) -> str:
		return f"{self._valor & 0xFFFFFFFF:08X}"


def nuevo_calculo(algoritmo: str):
	"""Objeto con ``update`` y ``hexdigest``. ``hashlib`` y ``zlib`` liberan el GIL con bloques grandes."""
	if algoritmo == "crc32":
		return _Crc32()
	if algoritmo == "blake2b":
		return hashlib.blake2b()
	if algoritmo not in POR_ID:
		raise ValueError(f"Algoritmo desconocido: {algoritmo}")
	return hashlib.new(algoritmo)


def calcular(flujo: BinaryIO, algoritmo: str, cancelacion=None, al_avanzar: Callable[[int], None] | None = None) -> str:
	"""Suma del contenido de ``flujo`` en hexadecimal (CRC32 en mayúsculas, como en SFV; el resto en minúsculas).

	:param al_avanzar: recibe los bytes leídos en cada bloque (para el progreso).
	:raises Cancelado: si se cancela.
	"""
	calculo = nuevo_calculo(algoritmo)
	while datos := flujo.read(BLOQUE):
		base.comprobar(cancelacion)
		calculo.update(datos)
		if al_avanzar is not None:
			al_avanzar(len(datos))
	return calculo.hexdigest()


def calcular_bytes(datos: bytes, algoritmo: str) -> str:
	calculo = nuevo_calculo(algoritmo)
	calculo.update(datos)
	return calculo.hexdigest()


# ── Escribir ─────────────────────────────────────────────────────────────────


def linea(algoritmo: str, nombre: str, suma: str) -> str:
	"""Una línea del archivo de sumas (sin salto de línea)."""
	if algoritmo == "crc32":
		return f"{nombre} {suma.upper()}"
	return f"{suma.lower()} *{nombre}"


def componer(algoritmo: str, sumas: list[tuple[str, str]], cabecera: str = "") -> str:
	"""Contenido completo de un archivo de sumas con saltos CRLF (Windows) y salto final."""
	lineas = []
	if algoritmo == "crc32" and cabecera:
		lineas.append(f"; {cabecera}")
	lineas.extend(linea(algoritmo, nombre, suma) for nombre, suma in sumas)
	return "\r\n".join(lineas) + "\r\n"


# ── Leer ─────────────────────────────────────────────────────────────────────

_BSD = re.compile(r"^(?P<alg>[A-Za-z0-9-]+)\s*\((?P<nombre>.+)\)\s*=\s*(?P<suma>[0-9A-Fa-f]+)\s*$")
_GNU = re.compile(r"^\\?(?P<suma>[0-9A-Fa-f]+) (?P<modo>[ *])(?P<nombre>.+)$")
_SFV = re.compile(r"^(?P<nombre>.+?)\s+(?P<suma>[0-9A-Fa-f]{8})\s*$")


def decodificar(datos: bytes) -> str:
	"""Texto de un archivo de sumas: UTF-8 (con o sin BOM) o, si no lo es, la página ANSI de Windows."""
	if datos.startswith(b"\xef\xbb\xbf"):
		return datos[3:].decode("utf-8", errors="replace")
	try:
		return datos.decode("utf-8")
	except UnicodeDecodeError:
		return datos.decode("cp1252", errors="replace")


def leer(texto: str, algoritmo: str | None = None) -> list[tuple[str, str]]:
	"""(nombre, suma) de cada línea útil. ``algoritmo`` ayuda a distinguir SFV de los demás.

	Las líneas que no se entienden se ignoran (comentarios, cabeceras de otros programas).
	"""
	resultado: list[tuple[str, str]] = []
	for cruda in texto.splitlines():
		linea_ = cruda.strip("﻿").rstrip("\r\n")
		if not linea_.strip() or linea_.lstrip().startswith((";", "#")):
			continue
		if algoritmo == "crc32":
			coincide = _SFV.match(linea_.strip())
			if coincide:
				resultado.append((coincide["nombre"], coincide["suma"].upper()))
			continue
		coincide = _BSD.match(linea_.strip()) or _GNU.match(linea_)
		if coincide:
			resultado.append((coincide["nombre"].strip(), coincide["suma"].lower()))
			continue
		coincide = _SFV.match(linea_.strip())
		if coincide and algoritmo is None:
			resultado.append((coincide["nombre"], coincide["suma"].upper()))
	return resultado


def deducir_algoritmo(sumas: list[tuple[str, str]]) -> str | None:
	"""Algoritmo por la longitud de las sumas (si el archivo no tiene una extensión conocida)."""
	if not sumas:
		return None
	longitud = len(sumas[0][1])
	candidatos = [a.id for a in ALGORITMOS if a.longitud == longitud]
	return candidatos[0] if candidatos else None


# ── Verificar ────────────────────────────────────────────────────────────────


class Resultado(StrEnum):
	CORRECTO = "correcto"
	DISTINTO = "distinto"
	NO_ENCONTRADO = "no_encontrado"
	ERROR_LECTURA = "error_lectura"

	@property
	def texto(self) -> str:
		return {
			Resultado.CORRECTO: _("Correcto"),
			Resultado.DISTINTO: _("Distinto"),
			Resultado.NO_ENCONTRADO: _("No encontrado"),
			Resultado.ERROR_LECTURA: _("Error de lectura"),
		}[self]


@dataclass(frozen=True)
class Verificacion:
	nombre: str
	resultado: Resultado
	detalle: str = ""


def iguales(esperada: str, obtenida: str) -> bool:
	return esperada.strip().lower() == obtenida.strip().lower()


def resumen_verificacion(verificaciones: list[Verificacion]) -> str:
	"""«10 correctos, 1 distinto, 2 no encontrados» (solo los que hay)."""
	from app.services import formato

	cuentas = {r: 0 for r in Resultado}
	for verificacion in verificaciones:
		cuentas[verificacion.resultado] += 1
	partes = []
	textos = {
		Resultado.CORRECTO: (_("{n} correcto"), _("{n} correctos")),
		Resultado.DISTINTO: (_("{n} distinto"), _("{n} distintos")),
		Resultado.NO_ENCONTRADO: (_("{n} no encontrado"), _("{n} no encontrados")),
		Resultado.ERROR_LECTURA: (_("{n} error de lectura"), _("{n} errores de lectura")),
	}
	for resultado, (singular, plural) in textos.items():
		if cuentas[resultado]:
			partes.append(formato.plural(cuentas[resultado], singular, plural))
	return ", ".join(partes) if partes else _("Ningún archivo en la lista")
