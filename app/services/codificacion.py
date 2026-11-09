# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Detección de codificación, decodificación de texto y volcado hexadecimal.

Lo usan la vista rápida, el visor, el editor, la búsqueda por contenido y la
comparación de archivos. Detección (en este orden):

1. BOM de UTF-8, UTF-16 LE o BE.
2. UTF-16 sin BOM: muchos ceros en posiciones pares o impares.
3. UTF-8 válido (los bytes de alto valor forman secuencias correctas).
4. Si no, Windows-1252 (lo más habitual en archivos españoles antiguos).

Un archivo es «binario» si tiene ceros fuera del patrón UTF-16 o muchos
caracteres de control.
"""

from __future__ import annotations

import codecs

#: (valor de preferencia, nombre para la persona, códec de Python).
CODIFICACIONES: tuple[tuple[str, str, str], ...] = (
	("utf-8", "UTF-8", "utf-8"),
	("utf-16-le", "UTF-16 (little endian)", "utf-16-le"),
	("utf-16-be", "UTF-16 (big endian)", "utf-16-be"),
	("cp1252", "Windows-1252 (ANSI)", "cp1252"),
	("latin-1", "ISO-8859-1 (Latin-1)", "latin-1"),
	("cp850", "OEM 850 (MS-DOS Europa)", "cp850"),
	("cp437", "OEM 437 (MS-DOS EE. UU.)", "cp437"),
)
NOMBRES = {valor: nombre for valor, nombre, _codec in CODIFICACIONES}

_BOMS = (
	(codecs.BOM_UTF8, "utf-8"),
	(codecs.BOM_UTF16_LE, "utf-16-le"),
	(codecs.BOM_UTF16_BE, "utf-16-be"),
)


def bom_de(datos: bytes) -> tuple[str | None, int]:
	"""(codificación, longitud del BOM) o (None, 0)."""
	for bom, nombre in _BOMS:
		if datos.startswith(bom):
			return nombre, len(bom)
	return None, 0


def _parece_utf16(datos: bytes) -> str | None:
	muestra = datos[:4096]
	if len(muestra) < 4:
		return None
	pares = muestra[0::2]
	impares = muestra[1::2]
	ceros_pares = pares.count(0) / max(1, len(pares))
	ceros_impares = impares.count(0) / max(1, len(impares))
	if ceros_impares > 0.3 and ceros_pares < 0.05:
		return "utf-16-le"
	if ceros_pares > 0.3 and ceros_impares < 0.05:
		return "utf-16-be"
	return None


def _utf8_valido(datos: bytes) -> bool:
	try:
		datos.decode("utf-8")
		return True
	except UnicodeDecodeError as error:
		# Un corte a mitad de carácter al final de la muestra no cuenta.
		return error.start >= len(datos) - 3


def detectar(datos: bytes) -> str:
	"""Codificación probable de ``datos`` (valor de ``CODIFICACIONES``)."""
	nombre, _ = bom_de(datos)
	if nombre:
		return nombre
	utf16 = _parece_utf16(datos)
	if utf16:
		return utf16
	if _utf8_valido(datos[:65536]):
		return "utf-8"
	return "cp1252"


def es_binario(datos: bytes) -> bool:
	"""``True`` si no parece texto (ceros sueltos o muchos caracteres de control)."""
	muestra = datos[:8192]
	if not muestra:
		return False
	if bom_de(muestra)[0] or _parece_utf16(muestra):
		return False
	if b"\x00" in muestra:
		return True
	control = sum(1 for b in muestra if b < 32 and b not in (9, 10, 12, 13, 27))
	return control / len(muestra) > 0.1


def decodificar(datos: bytes, codificacion: str = "automatica") -> tuple[str, str]:
	"""(texto, codificación usada). Nunca falla: los bytes no válidos se sustituyen."""
	if codificacion in ("", "automatica"):
		codificacion = detectar(datos)
	_, salto = bom_de(datos)
	if salto and codificacion == bom_de(datos)[0]:
		datos = datos[salto:]
	return datos.decode(codificacion, errors="replace"), codificacion


def hexadecimal(datos: bytes, desplazamiento: int = 0, ancho: int = 16) -> str:
	"""Volcado «00000010  48 6F 6C 61 ...  Hola...» por líneas."""
	lineas = []
	for inicio in range(0, len(datos), ancho):
		trozo = datos[inicio:inicio + ancho]
		bytes_hex = " ".join(f"{b:02X}" for b in trozo).ljust(ancho * 3 - 1)
		texto = "".join(chr(b) if 32 <= b < 127 else "." for b in trozo)
		lineas.append(f"{desplazamiento + inicio:08X}  {bytes_hex}  {texto}")
	return "\n".join(lineas)


def fin_de_linea(texto: str) -> str:
	"""«\\r\\n», «\\n» o «\\r» según lo que más aparezca (por defecto CRLF)."""
	crlf = texto.count("\r\n")
	lf = texto.count("\n") - crlf
	cr = texto.count("\r") - crlf
	if lf > crlf and lf >= cr:
		return "\n"
	if cr > crlf and cr > lf:
		return "\r"
	return "\r\n"
