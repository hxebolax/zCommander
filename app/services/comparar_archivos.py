# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comparación de dos archivos por contenido (sección 8.19, bloque A).

Lógica sin wx, para probarla sin ventanas. La usa la ventana de diferencias
(``app/ui/ventanas/diferencias.py``), que la llama desde un hilo de trabajo.

Por qué está hecha así:

- Si los dos archivos parecen texto, se comparan **por líneas** con
  ``difflib`` y el resultado es una lista de diferencias que se puede leer
  una a una con el lector de pantalla («Línea 12: cambiada»). Cada archivo se
  decodifica con su propia codificación detectada: un UTF-8 y un UTF-16 con
  el mismo texto son «iguales en el texto».
- Si alguno es binario, se comparan **byte a byte** por bloques (sin cargar
  el archivo entero) y se dice dónde empiezan a ser distintos.
- Los textos muy grandes se comparan como binarios: ``difflib`` es cuadrático
  en el peor caso y la persona no podría recorrer cientos de miles de
  diferencias.
- Los números de línea son siempre de 1 en adelante y los desplazamientos de
  byte de 0 en adelante (como en el visor hexadecimal y en Ctrl+G).
"""

from __future__ import annotations

import builtins
import difflib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import BinaryIO

from app.services import codificacion, formato

log = logging.getLogger(__name__)

#: Tamaño de la muestra con la que se decide si un archivo es texto.
MUESTRA = 64 * 1024
#: Bloque de lectura para la comparación binaria.
BLOQUE = 1024 * 1024
#: Por encima de este tamaño (de cualquiera de los dos) se compara byte a byte.
LIMITE_TEXTO = 32 * 1024 * 1024

CAMBIADA, SOLO_IZQUIERDO, SOLO_DERECHO = "cambiada", "solo_izquierdo", "solo_derecho"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _comprobar(cancelacion) -> None:
	"""Lanza ``Cancelado`` si se pidió cancelar (acepta una ``Tarea``, un token o ``None``)."""
	from app.services.vfs import base

	base.comprobar(cancelacion)


# ── Diferencias de texto ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Diferencia:
	"""Un tramo distinto entre los dos textos.

	Los índices son de lista (desde 0) y el final no se incluye, como en
	``difflib``: ``izquierdo[inicio_izq:fin_izq]`` son las líneas del primero.
	"""

	tipo: str
	inicio_izq: int
	fin_izq: int
	inicio_der: int
	fin_der: int

	@property
	def lineas_izq(self) -> int:
		return self.fin_izq - self.inicio_izq

	@property
	def lineas_der(self) -> int:
		return self.fin_der - self.inicio_der


def lineas_de(texto: str) -> list[str]:
	"""Líneas del texto sin el fin de línea (CRLF, LF o CR).

	No se usa ``str.splitlines`` porque también corta en caracteres como el
	salto de página o U+2028, y los números de línea ya no coincidirían con
	los del visor y el editor. Un fin de línea al final no crea una línea vacía.
	"""
	if not texto:
		return []
	lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	if lineas and lineas[-1] == "":
		lineas.pop()
	return lineas


def comparar_lineas(izquierdo: Sequence[str], derecho: Sequence[str]) -> list[Diferencia]:
	"""Tramos distintos entre dos listas de líneas, en orden."""
	# autojunk descarta las líneas muy repetidas en textos largos: acelera
	# mucho, pero en textos cortos da diferencias raras. Solo se usa si hace falta.
	autojunk = max(len(izquierdo), len(derecho)) > 20000
	comparador = difflib.SequenceMatcher(None, izquierdo, derecho, autojunk=autojunk)
	diferencias = []
	for operacion, i1, i2, j1, j2 in comparador.get_opcodes():
		if operacion == "equal":
			continue
		tipo = {"replace": CAMBIADA, "delete": SOLO_IZQUIERDO, "insert": SOLO_DERECHO}[operacion]
		diferencias.append(Diferencia(tipo, i1, i2, j1, j2))
	return diferencias


def comparar_textos(izquierdo: str, derecho: str) -> list[Diferencia]:
	"""Atajo: compara dos textos ya decodificados por líneas."""
	return comparar_lineas(lineas_de(izquierdo), lineas_de(derecho))


def _rango(inicio: int, fin: int) -> tuple[str, bool]:
	"""«12» o «12 a 14» (números desde 1) y si es plural."""
	if fin - inicio <= 1:
		return str(inicio + 1), False
	return _("{a} a {b}").format(a=inicio + 1, b=fin), True


def describir(diferencia: Diferencia) -> str:
	"""Texto de la fila de la lista: «Línea 12: cambiada», «Líneas 3 a 5: solo en el derecho».

	El número es el de la línea en el archivo que la tiene: en las cambiadas y
	en las que solo están en el izquierdo, el del izquierdo (y, si en el
	derecho está en otro sitio, se añade entre paréntesis); en las que solo
	están en el derecho, el del derecho.
	"""
	if diferencia.tipo == SOLO_DERECHO:
		rango, plural = _rango(diferencia.inicio_der, diferencia.fin_der)
		plantilla = _("Líneas {r}: solo en el derecho") if plural else _("Línea {r}: solo en el derecho")
		return plantilla.format(r=rango)
	rango, plural = _rango(diferencia.inicio_izq, diferencia.fin_izq)
	if diferencia.tipo == SOLO_IZQUIERDO:
		plantilla = _("Líneas {r}: solo en el izquierdo") if plural else _("Línea {r}: solo en el izquierdo")
		return plantilla.format(r=rango)
	texto = (_("Líneas {r}: cambiadas") if plural else _("Línea {r}: cambiada")).format(r=rango)
	if diferencia.inicio_der != diferencia.inicio_izq or diferencia.lineas_der != diferencia.lineas_izq:
		rango_der, plural_der = _rango(diferencia.inicio_der, diferencia.fin_der)
		texto += " " + (_("(líneas {r} en el derecho)") if plural_der else _("(línea {r} en el derecho)")).format(r=rango_der)
	return texto


# ── Comparación binaria ───────────────────────────────────────────────────────


def primer_byte_distinto(flujo_a: BinaryIO, flujo_b: BinaryIO, cancelacion=None, bloque: int = BLOQUE) -> int | None:
	"""Desplazamiento (desde 0) del primer byte distinto, o ``None`` si son iguales.

	Si uno es el principio del otro, el primer byte distinto es el que sigue
	al final del más corto. Lee por bloques: sirve para archivos de cualquier
	tamaño y de cualquier proveedor.
	"""
	desplazamiento = 0
	while True:
		_comprobar(cancelacion)
		a = _leer_completo(flujo_a, bloque)
		b = _leer_completo(flujo_b, bloque)
		if a != b:
			comun = min(len(a), len(b))
			for indice in range(comun):
				if a[indice] != b[indice]:
					return desplazamiento + indice
			return desplazamiento + comun
		if not a:
			return None
		desplazamiento += len(a)


def _leer_completo(flujo: BinaryIO, cantidad: int) -> bytes:
	"""Lee ``cantidad`` bytes salvo al final (un flujo de red puede devolver menos)."""
	trozos = []
	pendiente = cantidad
	while pendiente > 0:
		trozo = flujo.read(pendiente)
		if not trozo:
			break
		trozos.append(trozo)
		pendiente -= len(trozo)
	return b"".join(trozos)


# ── Comparación completa ──────────────────────────────────────────────────────


@dataclass
class Resultado:
	"""Resultado de comparar dos archivos.

	:param es_texto: se compararon por líneas.
	:param iguales: el contenido (los bytes) es idéntico.
	:param texto_igual: en los de texto, las líneas son iguales aunque los bytes no
		(otra codificación u otros fines de línea).
	:param primer_distinto: en los binarios, desplazamiento del primer byte distinto.
	"""

	es_texto: bool
	iguales: bool
	tamano_izq: int = 0
	tamano_der: int = 0
	texto_igual: bool = False
	diferencias: list[Diferencia] = field(default_factory=list)
	lineas_izq: list[str] = field(default_factory=list)
	lineas_der: list[str] = field(default_factory=list)
	codificacion_izq: str = ""
	codificacion_der: str = ""
	primer_distinto: int | None = None
	#: Motivo por el que unos textos se compararon como binarios («demasiado grandes»).
	nota: str = ""


def es_texto(muestra: bytes) -> bool:
	"""``True`` si la muestra parece texto (la misma regla que el visor)."""
	return not codificacion.es_binario(muestra)


def comparar_datos(datos_izq: bytes, datos_der: bytes) -> Resultado:
	"""Compara dos contenidos ya leídos (archivos pequeños o pruebas)."""
	import io

	if es_texto(datos_izq[:MUESTRA]) and es_texto(datos_der[:MUESTRA]):
		return _comparar_como_texto(datos_izq, datos_der)
	return _comparar_como_binario(io.BytesIO(datos_izq), io.BytesIO(datos_der), len(datos_izq), len(datos_der), None)


def comparar(abrir_izq, abrir_der, tamano_izq: int, tamano_der: int, cancelacion=None) -> Resultado:
	"""Compara dos archivos de cualquier proveedor.

	:param abrir_izq, abrir_der: funciones sin argumentos que devuelven un flujo
		binario nuevo (``lambda: proveedor.abrir_lectura(ruta)``). Se pueden
		llamar dos veces: una para la muestra y otra para la lectura completa.
	:param tamano_izq, tamano_der: tamaños en bytes; −1 si no se saben.
	"""
	with abrir_izq() as flujo:
		muestra_izq = _leer_completo(flujo, MUESTRA)
	with abrir_der() as flujo:
		muestra_der = _leer_completo(flujo, MUESTRA)
	_comprobar(cancelacion)
	textos = es_texto(muestra_izq) and es_texto(muestra_der)
	grande = max(tamano_izq, tamano_der) > LIMITE_TEXTO
	if textos and not grande:
		with abrir_izq() as flujo:
			datos_izq = _leer_todo(flujo, cancelacion)
		with abrir_der() as flujo:
			datos_der = _leer_todo(flujo, cancelacion)
		return _comparar_como_texto(datos_izq, datos_der)
	with abrir_izq() as flujo_izq, abrir_der() as flujo_der:
		resultado = _comparar_como_binario(flujo_izq, flujo_der, tamano_izq, tamano_der, cancelacion)
	if textos and grande:
		resultado.nota = _("Son textos demasiado grandes para compararlos por líneas: se han comparado byte a byte.")
	return resultado


def _leer_todo(flujo: BinaryIO, cancelacion) -> bytes:
	trozos = []
	while True:
		_comprobar(cancelacion)
		trozo = flujo.read(BLOQUE)
		if not trozo:
			return b"".join(trozos)
		trozos.append(trozo)


def _comparar_como_texto(datos_izq: bytes, datos_der: bytes) -> Resultado:
	texto_izq, cod_izq = codificacion.decodificar(datos_izq)
	texto_der, cod_der = codificacion.decodificar(datos_der)
	lineas_izq, lineas_der = lineas_de(texto_izq), lineas_de(texto_der)
	iguales = datos_izq == datos_der
	diferencias = [] if iguales else comparar_lineas(lineas_izq, lineas_der)
	return Resultado(
		es_texto=True, iguales=iguales, tamano_izq=len(datos_izq), tamano_der=len(datos_der),
		texto_igual=not diferencias, diferencias=diferencias, lineas_izq=lineas_izq, lineas_der=lineas_der,
		codificacion_izq=cod_izq, codificacion_der=cod_der,
	)


def _comparar_como_binario(flujo_izq, flujo_der, tamano_izq: int, tamano_der: int, cancelacion) -> Resultado:
	primero = primer_byte_distinto(flujo_izq, flujo_der, cancelacion)
	return Resultado(es_texto=False, iguales=primero is None, tamano_izq=tamano_izq, tamano_der=tamano_der,
		primer_distinto=primero)


def resumen(resultado: Resultado) -> str:
	"""Frase corta que se anuncia al terminar: «Iguales», «3 diferencias», «Distintos a partir del byte 4096»."""
	if resultado.iguales:
		return _("Los archivos son iguales")
	if resultado.es_texto:
		if not resultado.diferencias:
			return _("El texto es igual; cambian la codificación o los fines de línea")
		return formato.plural(len(resultado.diferencias), _("{n} diferencia"), _("{n} diferencias"))
	texto = _("Distintos a partir del byte {n}").format(n=formato.miles(resultado.primer_distinto or 0))
	if resultado.tamano_izq >= 0 and resultado.tamano_der >= 0 and resultado.tamano_izq != resultado.tamano_der:
		texto += _(" (tamaños distintos: {a} y {b})").format(
			a=formato.tamano_legible(resultado.tamano_izq), b=formato.tamano_legible(resultado.tamano_der))
	return texto
