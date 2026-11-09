# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tamaño de carpetas (sección 8.20): cálculo en un hilo y frases para el lector.

Usa ``recorrido.sumar``, que solo mira los metadatos del listado: no sigue
enlaces ni uniones y no abre archivos, así que no descarga los que están solo
en la nube. Los resultados se entregan por lotes (como mucho unas 4 veces por
segundo) para que el panel no se redibuje con cada carpeta de una lista larga.
"""

from __future__ import annotations

import builtins
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.services import formato
from app.services.recorrido import Totales, sumar
from app.services.vfs import base

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class TamanoCarpeta:
	"""Resultado de una carpeta."""

	nombre: str
	ruta: str
	totales: Totales


def carpetas_calculables(entradas: Sequence[base.Entrada]) -> list[base.Entrada]:
	"""Las carpetas de verdad (sin «..» ni enlaces o uniones, que no se siguen)."""
	return [e for e in entradas if e.es_carpeta and not e.es_superior and not e.es_enlace]


def calcular(
	proveedor: base.Proveedor,
	carpetas: Sequence[base.Entrada],
	cancelacion=None,
	al_lote: Callable[[list[TamanoCarpeta]], None] | None = None,
	al_avanzar: Callable[[int, int, str], None] | None = None,
	intervalo_s: float = 0.25,
) -> list[TamanoCarpeta]:
	"""Suma cada carpeta y devuelve todos los resultados.

	:param al_lote: recibe los resultados nuevos cada ``intervalo_s`` (y el resto al final).
	:param al_avanzar: recibe (hechas, total, nombre) al empezar cada carpeta.
	:raises Cancelado: si se cancela (los lotes ya entregados quedan entregados).
	"""
	resultados: list[TamanoCarpeta] = []
	pendientes: list[TamanoCarpeta] = []
	ultimo = time.monotonic()
	for indice, carpeta in enumerate(carpetas):
		base.comprobar(cancelacion)
		if al_avanzar is not None:
			al_avanzar(indice, len(carpetas), carpeta.nombre)
		totales = sumar(proveedor, carpeta.ruta, cancelacion)
		resultado = TamanoCarpeta(carpeta.nombre, carpeta.ruta, totales)
		resultados.append(resultado)
		pendientes.append(resultado)
		if al_lote is not None and time.monotonic() - ultimo >= intervalo_s:
			al_lote(pendientes)
			pendientes = []
			ultimo = time.monotonic()
	if al_lote is not None and pendientes:
		al_lote(pendientes)
	return resultados


def describir(nombre: str, totales: Totales) -> str:
	"""«Documentos: 1,2 GB, 3400 archivos, 210 carpetas» (y los que no se pudieron leer)."""
	partes = [
		formato.tamano_legible(totales.bytes),
		formato.plural(totales.archivos, _("{n} archivo"), _("{n} archivos")),
		formato.plural(totales.carpetas, _("{n} carpeta"), _("{n} carpetas")),
	]
	if totales.errores:
		partes.append(formato.plural(totales.errores, _("{n} carpeta sin leer"), _("{n} carpetas sin leer")))
	return f"{nombre}: " + ", ".join(partes)


def describir_varias(resultados: Sequence[TamanoCarpeta]) -> str:
	"""Una carpeta: su descripción; varias: «12 carpetas: 4,5 GB en total, 900 archivos»."""
	if len(resultados) == 1:
		return describir(resultados[0].nombre, resultados[0].totales)
	total = Totales()
	for r in resultados:
		total.bytes += r.totales.bytes
		total.archivos += r.totales.archivos
		total.carpetas += r.totales.carpetas
		total.errores += r.totales.errores
	texto = _("{c}: {t} en total, {a}").format(
		c=formato.plural(len(resultados), _("{n} carpeta"), _("{n} carpetas")),
		t=formato.tamano_legible(total.bytes),
		a=formato.plural(total.archivos, _("{n} archivo"), _("{n} archivos")),
	)
	if total.errores:
		texto += ", " + formato.plural(total.errores, _("{n} carpeta sin leer"), _("{n} carpetas sin leer"))
	return texto
