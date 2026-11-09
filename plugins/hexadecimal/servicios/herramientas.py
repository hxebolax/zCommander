# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Búsqueda, «ir a», inspector de tipos y textos del volcado y de los anuncios (sin wx)."""

from __future__ import annotations

import builtins
import codecs
import datetime as _dt
import re
import struct
import unicodedata
from typing import Any

from .piezas import BLOQUE, TablaPiezas

#: Codificaciones de la columna de texto (las del visor interno).
CODIFICACIONES: tuple[tuple[str, str], ...] = (
	("cp1252", "Windows-1252"), ("utf-8", "UTF-8"), ("utf-16-le", "UTF-16 LE"), ("utf-16-be", "UTF-16 BE"),
	("latin-1", "ISO-8859-1"), ("cp850", "OEM 850"), ("cp437", "OEM 437"),
)
_UN_BYTE = {"cp1252", "latin-1", "cp850", "cp437"}
_HEX = re.compile(r"^[0-9a-fA-F?\s]+$")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Patrones de búsqueda ─────────────────────────────────────────────────────


def patron_hexadecimal(texto: str) -> list[int | None]:
	"""«4F 6B ?? 00» (o «4F6B??00») → bytes, con ``None`` para el comodín ``??``.

	:raises ValueError: con el motivo en español.
	"""
	limpio = "".join(texto.split())
	if not limpio:
		raise ValueError(_("Escriba los bytes que buscar, por ejemplo 4F 6B ?? 00"))
	if not _HEX.match(limpio) or len(limpio) % 2:
		raise ValueError(_("Escriba pares de dígitos hexadecimales (0 a 9 y A a F) o ?? como comodín"))
	resultado: list[int | None] = []
	for i in range(0, len(limpio), 2):
		par = limpio[i:i + 2]
		if par == "??":
			resultado.append(None)
		elif "?" in par:
			raise ValueError(_("El comodín es ?? (un byte entero)"))
		else:
			resultado.append(int(par, 16))
	if all(b is None for b in resultado):
		raise ValueError(_("El patrón no puede ser solo comodines"))
	return resultado


def patron_texto(texto: str, codificacion: str) -> list[int | None]:
	if not texto:
		raise ValueError(_("Escriba el texto que buscar"))
	try:
		return list(texto.encode(codificacion))
	except UnicodeEncodeError as error:
		raise ValueError(_("El texto tiene caracteres que no existen en {c}").format(c=codificacion)) from error


def _expresion(patron: list[int | None]) -> re.Pattern[bytes]:
	return re.compile(b"".join(b"." if b is None else re.escape(bytes([b])) for b in patron), re.DOTALL)


def buscar(tabla: TablaPiezas, patron: list[int | None], desde: int, atras: bool = False, cancelacion: Any = None) -> int:
	"""Primer desplazamiento del patrón desde ``desde`` (hacia delante, o la última antes de ``desde`` hacia atrás); −1 si no está."""
	expresion = _expresion(patron)
	largo = len(patron)
	total = len(tabla)
	if not atras:
		posicion = max(0, desde)
		while posicion < total:
			if cancelacion is not None and cancelacion.is_set():
				return -1
			bloque = tabla.leer(posicion, BLOQUE + largo - 1)
			encontrado = expresion.search(bloque)
			if encontrado:
				return posicion + encontrado.start()
			posicion += BLOQUE
		return -1
	fin = min(desde, total)
	while fin > 0:
		if cancelacion is not None and cancelacion.is_set():
			return -1
		inicio = max(0, fin - BLOQUE)
		bloque = tabla.leer(inicio, fin - inicio + largo - 1)
		ultimo = -1
		for encontrado in expresion.finditer(bloque):
			if inicio + encontrado.start() < fin:
				ultimo = inicio + encontrado.start()
		if ultimo >= 0:
			return ultimo
		fin = inicio
	return -1


def buscar_todos(tabla: TablaPiezas, patron: list[int | None], cancelacion: Any = None) -> list[int]:
	"""Todas las apariciones, sin solaparse."""
	resultado = []
	posicion = 0
	while True:
		encontrado = buscar(tabla, patron, posicion, cancelacion=cancelacion)
		if encontrado < 0:
			return resultado
		resultado.append(encontrado)
		posicion = encontrado + len(patron)


# ── Ir a ─────────────────────────────────────────────────────────────────────


def destino(texto: str, actual: int, total: int) -> int:
	"""«1234», «0x10», «10h», «+16», «-16» o «50%» → desplazamiento (dentro del archivo).

	:raises ValueError: con el motivo en español.
	"""
	limpio = texto.strip().replace(" ", "").lower()
	if not limpio:
		raise ValueError(_("Escriba un desplazamiento"))
	try:
		if limpio.endswith("%"):
			porcentaje = float(limpio[:-1].replace(",", "."))
			if not 0 <= porcentaje <= 100:
				raise ValueError
			valor = int(total * porcentaje / 100)
		elif limpio[0] in "+-":
			valor = actual + int(limpio, 0) if not limpio[1:].startswith("0x") else actual + int(limpio[0] + limpio[3:], 16)
		elif limpio.startswith("0x"):
			valor = int(limpio, 16)
		elif limpio.endswith("h"):
			valor = int(limpio[:-1], 16)
		else:
			valor = int(limpio)
	except ValueError as error:
		raise ValueError(_("No se entiende «{t}»: escriba un número decimal, 0x y un hexadecimal, +n, -n o un porcentaje").format(
			t=texto.strip())) from error
	if total == 0:
		return 0
	return max(0, min(valor, total - 1))


# ── Inspector ────────────────────────────────────────────────────────────────


def inspeccionar(datos: bytes, orden: str = "little") -> list[tuple[str, str]]:
	"""(tipo, valor) de los bytes del cursor: enteros, coma flotante, caracteres y fechas."""
	marca = "<" if orden == "little" else ">"
	filas: list[tuple[str, str]] = []

	def entero(nombre: str, formato: str, tamano: int) -> None:
		if len(datos) >= tamano:
			filas.append((nombre, str(struct.unpack(marca + formato, datos[:tamano])[0])))

	entero(_("Entero de 8 bits sin signo"), "B", 1)
	entero(_("Entero de 8 bits con signo"), "b", 1)
	entero(_("Entero de 16 bits sin signo"), "H", 2)
	entero(_("Entero de 16 bits con signo"), "h", 2)
	entero(_("Entero de 32 bits sin signo"), "I", 4)
	entero(_("Entero de 32 bits con signo"), "i", 4)
	entero(_("Entero de 64 bits sin signo"), "Q", 8)
	entero(_("Entero de 64 bits con signo"), "q", 8)
	if len(datos) >= 4:
		filas.append((_("Coma flotante de 32 bits"), f"{struct.unpack(marca + 'f', datos[:4])[0]:.7g}"))
	if len(datos) >= 8:
		filas.append((_("Coma flotante de 64 bits"), f"{struct.unpack(marca + 'd', datos[:8])[0]:.15g}"))
	filas.append((_("Carácter UTF-8"), _caracter_utf8(datos)))
	if len(datos) >= 2:
		try:
			filas.append((_("Carácter UTF-16"), describir_caracter(datos[:2].decode("utf-16-le" if orden == "little" else "utf-16-be"))))
		except UnicodeDecodeError:
			filas.append((_("Carácter UTF-16"), _("no válido")))
	if len(datos) >= 4:
		segundos = struct.unpack(marca + "I", datos[:4])[0]
		filas.append((_("Fecha Unix de 32 bits"), _fecha(segundos)))
	if len(datos) >= 8:
		unidades = struct.unpack(marca + "Q", datos[:8])[0]
		filas.append((_("Fecha FILETIME"), _fecha((unidades - 116444736000000000) / 10_000_000) if unidades else _("no válida")))
	return filas


def _caracter_utf8(datos: bytes) -> str:
	for largo in range(1, min(4, len(datos)) + 1):
		try:
			return describir_caracter(datos[:largo].decode("utf-8"))
		except UnicodeDecodeError:
			continue
	return _("no válido")


def _fecha(segundos: float) -> str:
	try:
		return _dt.datetime.fromtimestamp(segundos, tz=_dt.UTC).strftime("%d/%m/%Y %H:%M:%S UTC")
	except (OverflowError, OSError, ValueError):
		return _("fuera de rango")


def texto_inspector(datos: bytes, orden: str) -> str:
	return "\n".join(f"{nombre}: {valor}" for nombre, valor in inspeccionar(datos, orden))


# ── Volcado y anuncios ───────────────────────────────────────────────────────


def describir_caracter(caracter: str) -> str:
	"""«letra O», «dígito 5», «espacio», «carácter de control», «símbolo ;»."""
	if not caracter:
		return ""
	if caracter == " ":
		return _("espacio")
	if caracter.isalpha():
		return _("letra {c}").format(c=caracter)
	if caracter.isdigit():
		return _("dígito {c}").format(c=caracter)
	if unicodedata.category(caracter).startswith("C"):
		return _("carácter de control")
	return _("símbolo {c}").format(c=caracter)


def caracter_de_byte(byte: int, codificacion: str) -> str:
	"""Carácter que se ve en la columna de texto para un byte (las codificaciones de varios bytes muestran el ASCII)."""
	if codificacion in _UN_BYTE:
		caracter = bytes([byte]).decode(codificacion, errors="replace")
	else:
		caracter = chr(byte) if byte < 128 else "."
	return caracter if caracter.isprintable() and caracter != "�" else "."


def linea_volcado(desplazamiento: int, datos: bytes, ancho: int, codificacion: str) -> str:
	"""«00000010  48 6F 6C 61 ...  Hola...»."""
	hexadecimal = " ".join(f"{b:02X}" for b in datos).ljust(ancho * 3 - 1)
	texto = "".join(caracter_de_byte(b, codificacion) for b in datos)
	return f"{desplazamiento:08X}  {hexadecimal}  {texto}"


def columna_hex(indice: int) -> int:
	"""Columna (en caracteres) del primer dígito del byte ``indice`` de la línea."""
	return 10 + indice * 3


def columna_texto(indice: int, ancho: int) -> int:
	return 10 + ancho * 3 - 1 + 2 + indice


def anuncio(desplazamiento: int, datos: bytes, codificacion: str, completo: bool) -> str:
	"""«Desplazamiento 0x1A, 4F, letra O» (con «completo», también el decimal y el binario)."""
	if not datos:
		return _("Final del archivo, desplazamiento 0x{d:X}").format(d=desplazamiento)
	byte = datos[0]
	caracter = _caracter_codificacion(datos, codificacion)
	texto = _("Desplazamiento 0x{d:X}, {b:02X}").format(d=desplazamiento, b=byte)
	if caracter:
		texto += ", " + caracter
	if completo:
		texto += ", " + _("decimal {n}, binario {b:08b}").format(n=byte, b=byte)
	return texto


def _caracter_codificacion(datos: bytes, codificacion: str) -> str:
	if codificacion in _UN_BYTE:
		return describir_caracter(datos[:1].decode(codificacion, errors="replace").replace("�", ""))
	decodificador = codecs.getincrementaldecoder(codificacion)(errors="strict")
	for i in range(min(4, len(datos))):
		try:
			resultado = decodificador.decode(datos[i:i + 1])
		except UnicodeDecodeError:
			return ""
		if resultado:
			return describir_caracter(resultado[0])
	return ""


def bytes_de_texto_pegado(texto: str, en_hexadecimal: bool, codificacion: str) -> bytes:
	"""Lo que se pega: en la columna hexadecimal, si el texto son pares hexadecimales, esos bytes; si no, el texto codificado."""
	limpio = "".join(texto.split())
	if en_hexadecimal and limpio and re.fullmatch(r"(?:[0-9a-fA-F]{2})+", limpio):
		return bytes.fromhex(limpio)
	return texto.encode(codificacion, errors="replace")
