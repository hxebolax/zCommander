# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Detección de la codificación y de los fines de línea de un archivo de texto (sin wx).

El núcleo tiene su propio detector, pero un complemento solo puede importar
``app.plugins.api``; este es independiente y además distingue OEM 850 (textos
de MS-DOS en español) de Windows-1252 y dice «ASCII» cuando no hay ningún
carácter fuera de él, que es lo que de verdad le interesa a quien convierte.

Orden de la detección:

1. BOM de UTF-8, UTF-16 o UTF-32.
2. UTF-16 sin BOM (muchos ceros en las posiciones pares o impares).
3. Solo ASCII.
4. UTF-8 válido.
5. OEM 850 si sus letras españolas (ñ, á, é...) son más probables que las de
   Windows-1252; si no, Windows-1252.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass

#: Bytes que se leen para detectar (las columnas no deben leer archivos enteros).
MUESTRA = 65536

#: Id interno → (nombre para la persona, códec de Python).
CODIFICACIONES: dict[str, tuple[str, str]] = {
	"ascii": ("ASCII", "ascii"),
	"utf-8": ("UTF-8", "utf-8"),
	"utf-8-bom": ("UTF-8 con BOM", "utf-8-sig"),
	"utf-16-le": ("UTF-16 LE", "utf-16"),
	"utf-16-be": ("UTF-16 BE", "utf-16"),
	"utf-16-le-sin-bom": ("UTF-16 LE sin BOM", "utf-16-le"),
	"utf-16-be-sin-bom": ("UTF-16 BE sin BOM", "utf-16-be"),
	"utf-32-le": ("UTF-32 LE", "utf-32"),
	"utf-32-be": ("UTF-32 BE", "utf-32"),
	"cp1252": ("Windows-1252", "cp1252"),
	"cp850": ("OEM 850", "cp850"),
}

_BOMS = (
	(codecs.BOM_UTF32_LE, "utf-32-le"),
	(codecs.BOM_UTF32_BE, "utf-32-be"),
	(codecs.BOM_UTF8, "utf-8-bom"),
	(codecs.BOM_UTF16_LE, "utf-16-le"),
	(codecs.BOM_UTF16_BE, "utf-16-be"),
)

# Letras españolas y signos frecuentes en cada página de códigos (ñ Ñ á é í ó ú ü ¿ ¡ Á É Í Ó Ú).
_LETRAS_850 = frozenset(b"\xa4\xa5\xa0\x82\xa1\xa2\xa3\x81\xa8\xad\xb5\x90\xd6\xe0\xe9")
_LETRAS_1252 = frozenset(b"\xf1\xd1\xe1\xe9\xed\xf3\xfa\xfc\xbf\xa1\xc1\xc9\xcd\xd3\xda")

FINES = ("CRLF", "LF", "CR")
SIN_FINES = "Sin fines de línea"
MEZCLADO = "Mezclado"


@dataclass(frozen=True)
class Deteccion:
	"""Lo que se sabe de un texto: codificación (id de ``CODIFICACIONES``) y fines de línea."""

	codificacion: str
	fin_linea: str
	binario: bool = False

	@property
	def nombre_codificacion(self) -> str:
		return CODIFICACIONES[self.codificacion][0]

	@property
	def codec(self) -> str:
		return CODIFICACIONES[self.codificacion][1]


def bom_de(datos: bytes) -> str | None:
	for bom, nombre in _BOMS:
		if datos.startswith(bom):
			return nombre
	return None


def _parece_utf16(datos: bytes) -> str | None:
	muestra = datos[:4096]
	if len(muestra) < 4:
		return None
	pares, impares = muestra[0::2], muestra[1::2]
	ceros_pares = pares.count(0) / max(1, len(pares))
	ceros_impares = impares.count(0) / max(1, len(impares))
	if ceros_impares > 0.3 and ceros_pares < 0.05:
		return "utf-16-le-sin-bom"
	if ceros_pares > 0.3 and ceros_impares < 0.05:
		return "utf-16-be-sin-bom"
	return None


def _utf8_valido(datos: bytes, cortado: bool) -> bool:
	try:
		datos.decode("utf-8")
		return True
	except UnicodeDecodeError as error:
		# Un carácter cortado al final de la muestra no cuenta.
		return cortado and error.start >= len(datos) - 3


def es_binario(datos: bytes) -> bool:
	"""``True`` si no parece texto: ceros sueltos o muchos caracteres de control."""
	muestra = datos[:8192]
	if not muestra or bom_de(muestra) or _parece_utf16(muestra):
		return False
	if b"\x00" in muestra:
		return True
	control = sum(1 for b in muestra if b < 32 and b not in (9, 10, 12, 13, 26, 27))
	return control / len(muestra) > 0.1


def detectar_codificacion(datos: bytes, cortado: bool = False) -> str:
	"""Id de ``CODIFICACIONES`` más probable para ``datos``.

	:param cortado: ``datos`` es solo el principio del archivo (tolera un carácter partido al final).
	"""
	bom = bom_de(datos)
	if bom:
		return bom
	utf16 = _parece_utf16(datos)
	if utf16:
		return utf16
	if datos.isascii():
		return "ascii"
	if _utf8_valido(datos, cortado):
		return "utf-8"
	altos = [b for b in datos if b >= 0x80]
	puntos_850 = sum(1 for b in altos if b in _LETRAS_850)
	puntos_1252 = sum(1 for b in altos if b in _LETRAS_1252)
	# En Windows-1252 los bytes 0x80 a 0x9F son comillas y guiones poco frecuentes;
	# en OEM 850 son letras con tilde muy habituales (é, ü, â...).
	controles_1252 = sum(1 for b in altos if 0x80 <= b <= 0x9F)
	if puntos_850 > puntos_1252 or (controles_1252 > len(altos) // 2 and puntos_850 >= puntos_1252 and controles_1252 > 2):
		return "cp850"
	return "cp1252"


def detectar_fin_linea(texto: str) -> str:
	"""«CRLF», «LF», «CR», «Mezclado» o «Sin fines de línea»."""
	crlf = texto.count("\r\n")
	lf = texto.count("\n") - crlf
	cr = texto.count("\r") - crlf
	presentes = [nombre for nombre, cuenta in zip(FINES, (crlf, lf, cr), strict=True) if cuenta]
	if not presentes:
		return SIN_FINES
	return presentes[0] if len(presentes) == 1 else MEZCLADO


def decodificar(datos: bytes, codificacion: str, errores: str = "strict") -> str:
	"""Texto de ``datos`` con la codificación detectada (sin el BOM)."""
	codec = CODIFICACIONES[codificacion][1]
	if codificacion == "utf-16-be" and datos.startswith(codecs.BOM_UTF16_BE):
		return datos[2:].decode("utf-16-be", errors=errores)
	if codificacion == "utf-32-be" and datos.startswith(codecs.BOM_UTF32_BE):
		return datos[4:].decode("utf-32-be", errors=errores)
	return datos.decode(codec, errors=errores)


def detectar(datos: bytes, cortado: bool = False) -> Deteccion:
	"""Codificación y fines de línea de ``datos`` (o del principio del archivo si ``cortado``)."""
	if es_binario(datos):
		return Deteccion("ascii", SIN_FINES, binario=True)
	codificacion = detectar_codificacion(datos, cortado)
	texto = decodificar(datos, codificacion, errores="replace")
	return Deteccion(codificacion, detectar_fin_linea(texto))


def detectar_archivo(ruta: str, muestra: int = MUESTRA) -> Deteccion:
	"""Lo mismo que ``detectar`` leyendo solo el principio del archivo."""
	with open(ruta, "rb") as archivo:
		datos = archivo.read(muestra + 1)
	cortado = len(datos) > muestra
	return detectar(datos[:muestra], cortado=cortado)
