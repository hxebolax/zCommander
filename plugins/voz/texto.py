# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Texto para leer en voz alta: codificación, párrafos y frases en español. Sin wx (diseño 2.0, 11.17).

La lectura avanza frase a frase (así «frase anterior», «párrafo siguiente» y
«continuar donde se dejó» tienen un sitio exacto), y las frases se cortan sin
romper las abreviaturas habituales del español («Sr.», «p. ej.», «etc.»): un
punto solo cierra frase si lo que sigue empieza como una frase nueva (mayúscula,
cifra, «¿», «¡» o comillas) y lo que lo precede no es una abreviatura ni una
inicial suelta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Abreviaturas (sin el punto final, en minúsculas) que no cierran frase.
ABREVIATURAS = frozenset({
	"sr", "sra", "srs", "sras", "srta", "srtas", "d", "dña", "dr", "dra", "drs", "dras", "ud", "uds", "vd", "vds", "lic", "ing",
	"prof", "profa", "arq", "mons", "pbro", "ilmo", "ilma", "excmo", "excma", "sto", "sta", "fr", "gral", "cnel", "cap", "tte",
	"ej", "etc", "pág", "págs", "pag", "pags", "núm", "nums", "num", "nº", "n", "art", "arts", "vol", "vols", "fig", "figs",
	"caps", "aprox", "admón", "avda", "av", "c", "cía", "dpto", "depto", "ed", "eds", "máx", "mín", "tel", "tlf", "telf",
	"vs", "pza", "pl", "ctra", "apdo", "izq", "izda", "dcha", "dcho", "s", "ss", "cf", "cfr", "op", "cit", "ib", "ibid",
	"vid", "a", "e", "u", "ee", "uu", "jr", "mr", "mrs", "st", "aa", "vv", "ap", "pp", "cols", "esq", "hnos", "ltda",
})
_CORTE = re.compile(r"([.!?…]+[»\"”')\]]*)(\s+)")
_INICIO_FRASE = re.compile(r"[A-ZÁÉÍÓÚÜÑ0-9¿¡«\"“(\[—–-]")


@dataclass(frozen=True)
class Frase:
	parrafo: int
	texto: str


def decodificar(datos: bytes) -> str:
	"""UTF-8 (con o sin BOM), UTF-16 con BOM o, si no, la página de códigos de Windows."""
	if datos.startswith((b"\xff\xfe", b"\xfe\xff")):
		return datos.decode("utf-16")
	try:
		return datos.decode("utf-8-sig")
	except UnicodeDecodeError:
		return datos.decode("cp1252", errors="replace")


def parrafos(texto: str) -> list[str]:
	"""Bloques separados por líneas en blanco; si no hay ninguna, cada línea es un párrafo.

	Las líneas de un mismo bloque se unen con un espacio (texto partido a mano).
	"""
	texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
	if re.search(r"\n[ \t]*\n", texto):
		bloques = re.split(r"\n[ \t]*\n+", texto)
		resultado = [" ".join(linea.strip() for linea in bloque.split("\n") if linea.strip()) for bloque in bloques]
	else:
		resultado = [linea.strip() for linea in texto.split("\n")]
	return [p for p in resultado if p]


def _palabra_antes(texto: str, posicion: int) -> str:
	inicio = posicion
	while inicio > 0 and not texto[inicio - 1].isspace() and texto[inicio - 1] not in "(«\"“":
		inicio -= 1
	return texto[inicio:posicion]


def frases_de(parrafo: str) -> list[str]:
	"""Frases de un párrafo, respetando las abreviaturas."""
	resultado: list[str] = []
	inicio = 0
	for coincidencia in _CORTE.finditer(parrafo):
		signos = coincidencia.group(1)
		siguiente = coincidencia.end()
		if siguiente >= len(parrafo) or not _INICIO_FRASE.match(parrafo[siguiente]):
			continue
		if signos.startswith(".") and not signos.startswith("..."):
			palabra = _palabra_antes(parrafo, coincidencia.start()).rstrip(".").lower()
			ultima = palabra.split(".")[-1]
			if ultima in ABREVIATURAS or (len(ultima) == 1 and ultima.isalpha()):
				continue
		frase = parrafo[inicio:coincidencia.end(1)].strip()
		if frase:
			resultado.append(frase)
		inicio = siguiente
	resto = parrafo[inicio:].strip()
	if resto:
		resultado.append(resto)
	return resultado


def dividir(texto: str) -> list[Frase]:
	"""Todas las frases del texto, cada una con su número de párrafo."""
	return [Frase(numero, frase) for numero, parrafo in enumerate(parrafos(texto)) for frase in frases_de(parrafo)]


def xml_sapi(texto: str, tono: int = 0, silencio_ms: int = 0) -> str:
	"""Texto con marcas XML de SAPI: tono (−10 a 10) y silencio al final (pausa entre párrafos)."""
	escapado = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
	if tono:
		escapado = f'<pitch absmiddle="{max(-10, min(10, int(tono)))}">{escapado}</pitch>'
	if silencio_ms > 0:
		escapado += f'<silence msec="{int(silencio_ms)}"/>'
	return escapado
