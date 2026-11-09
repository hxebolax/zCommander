# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tablas en memoria y lectura de CSV y TSV (sin wx).

``Tabla`` es lo que muestra el visor: cabeceras, filas de texto y de dónde
salieron. El filtro y el orden no cambian la tabla: devuelven la lista de
índices de las filas visibles, así quitar el filtro no vuelve a leer nada.
"""

from __future__ import annotations

import builtins
import codecs
import csv
import io
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

#: Separadores que se prueban en la detección automática.
SEPARADORES = (",", ";", "\t", "|")
NOMBRES_SEPARADOR = {",": "coma", ";": "punto y coma", "\t": "tabulador", "|": "barra vertical"}
#: Bytes que se miran para detectar el separador.
MUESTRA = 64 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class Tabla:
	"""Datos de un CSV, una tabla o una consulta.

	:param origen: «CSV», «tabla», «vista» o «consulta».
	:param truncada: se dejaron de leer filas al llegar a ``filas_maximas``.
	:param estructura: (columna, tipo) cuando se sabe (SQLite).
	"""

	nombre: str
	cabeceras: list[str]
	filas: list[tuple[str, ...]]
	origen: str = "CSV"
	codificacion: str = ""
	separador: str = ""
	truncada: bool = False
	estructura: list[tuple[str, str]] = field(default_factory=list)

	@property
	def num_columnas(self) -> int:
		return len(self.cabeceras)


def detectar_codificacion(datos: bytes) -> str:
	"""Códec de Python: BOM de UTF-8 o UTF-16, UTF-8 válido o Windows-1252."""
	if datos.startswith(codecs.BOM_UTF8):
		return "utf-8-sig"
	if datos.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
		return "utf-16"
	try:
		datos[:MUESTRA].decode("utf-8")
		return "utf-8"
	except UnicodeDecodeError as error:
		if len(datos) > MUESTRA and error.start >= MUESTRA - 3:
			return "utf-8"
		return "cp1252"


NOMBRES_CODIFICACION = {"utf-8-sig": "UTF-8 con BOM", "utf-16": "UTF-16", "utf-8": "UTF-8", "cp1252": "Windows-1252"}


def detectar_separador(texto: str) -> str:
	"""El separador que aparece el mismo número de veces (y más de cero) en más líneas."""
	lineas = [linea for linea in texto.splitlines()[:50] if linea.strip()]
	if not lineas:
		return ","
	try:
		return csv.Sniffer().sniff("\n".join(lineas), delimiters="".join(SEPARADORES)).delimiter
	except csv.Error:
		pass
	mejor, puntos_mejor = ",", -1
	for separador in SEPARADORES:
		cuentas = [linea.count(separador) for linea in lineas]
		if not cuentas[0]:
			continue
		puntos = sum(1 for c in cuentas if c == cuentas[0])
		if puntos > puntos_mejor:
			mejor, puntos_mejor = separador, puntos
	return mejor


def leer_csv(datos: bytes, nombre: str = "", separador: str = "automatico", filas_maximas: int = 1_000_000) -> Tabla:
	"""Lee un CSV o TSV desde sus bytes. La primera fila son las cabeceras.

	:param separador: ``automatico``, ``,``, ``;`` o ``\\t`` (también ``tabulador``).
	"""
	codificacion = detectar_codificacion(datos)
	texto = datos.decode(codificacion, errors="replace")
	if separador == "tabulador":
		separador = "\t"
	if separador in ("", "automatico"):
		separador = "\t" if nombre.lower().endswith((".tsv", ".tab")) else detectar_separador(texto[:MUESTRA])
	lector = csv.reader(io.StringIO(texto, newline=""), delimiter=separador)
	cabeceras: list[str] = []
	filas: list[tuple[str, ...]] = []
	truncada = False
	for numero, fila in enumerate(lector):
		if numero == 0:
			cabeceras = [c.strip() for c in fila]
			continue
		if not any(celda.strip() for celda in fila):
			continue
		if len(filas) >= filas_maximas:
			truncada = True
			break
		filas.append(tuple(fila))
	ancho = max([len(cabeceras), *(len(f) for f in filas[:1000])], default=0)
	cabeceras = completar_cabeceras(cabeceras, ancho)
	return Tabla(nombre, cabeceras, filas, "CSV", NOMBRES_CODIFICACION.get(codificacion, codificacion), separador, truncada)


def completar_cabeceras(cabeceras: Sequence[str], ancho: int) -> list[str]:
	"""Cabeceras vacías o que faltan → «Columna 3»."""
	resultado = [c or _("Columna {n}").format(n=i + 1) for i, c in enumerate(cabeceras)]
	resultado.extend(_("Columna {n}").format(n=i + 1) for i in range(len(resultado), ancho))
	return resultado


def celda(fila: Sequence[str], columna: int) -> str:
	return fila[columna] if columna < len(fila) else ""


def filtrar(tabla: Tabla, texto: str) -> list[int]:
	"""Índices de las filas en las que alguna celda contiene ``texto`` (sin distinguir mayúsculas)."""
	if not texto:
		return list(range(len(tabla.filas)))
	buscado = texto.casefold()
	return [i for i, fila in enumerate(tabla.filas) if any(buscado in str(c).casefold() for c in fila)]


_NUMERO = re.compile(r"^-?\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?$|^-?\d+(?:[.,]\d+)?$")


def _valor_orden(texto: str) -> tuple[int, float, str]:
	"""Clave de orden: los números como números (también «1.234,5»), después el texto."""
	limpio = texto.strip()
	if limpio and _NUMERO.match(limpio):
		if "," in limpio:
			normal = limpio.replace(".", "").replace(" ", "").replace(",", ".")
		else:
			normal = limpio.replace(" ", "")
		try:
			return (0, float(normal), "")
		except ValueError:
			pass
	# Sin tildes, para que «Íñigo» vaya entre la «h» y la «j», como en un diccionario.
	sin_tildes = "".join(c for c in unicodedata.normalize("NFD", limpio.casefold()) if not unicodedata.combining(c))
	return (1, 0.0, sin_tildes)


def ordenar(tabla: Tabla, indices: Sequence[int], columna: int, descendente: bool = False) -> list[int]:
	return sorted(indices, key=lambda i: _valor_orden(celda(tabla.filas[i], columna)), reverse=descendente)


def a_csv(cabeceras: Sequence[str], filas: Sequence[Sequence[str]], separador: str = ",") -> str:
	"""Texto CSV (con fines de línea CRLF, como lo espera Excel)."""
	salida = io.StringIO(newline="")
	escritor = csv.writer(salida, delimiter=separador, lineterminator="\r\n")
	escritor.writerow(list(cabeceras))
	escritor.writerows([list(f) for f in filas])
	return salida.getvalue()
