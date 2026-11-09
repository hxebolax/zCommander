# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Recorrido recursivo único de carpetas sobre cualquier proveedor.

Lo usan el análisis de copia, el borrado definitivo, la búsqueda, la
comparación de carpetas, el tamaño de carpetas y la vista plana. Reglas comunes
que así solo se escriben una vez:

- Nunca entra en enlaces ni uniones (evita bucles y salir del árbol).
- Comprueba la cancelación en cada elemento.
- Un error en una subcarpeta no para el recorrido: se informa por ``al_error``.
- Filtro opcional por patrón (con exclusiones) y profundidad máxima.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.services.seleccion import Patron
from app.services.vfs import base


@dataclass(frozen=True)
class Elemento:
	"""Una entrada encontrada en el recorrido.

	:param entrada: la entrada.
	:param relativo: ruta relativa a la raíz del recorrido, con «\\» o «/» según el proveedor.
	:param profundidad: 0 para los hijos directos de la raíz.
	"""

	entrada: base.Entrada
	relativo: str
	profundidad: int


def _sep(proveedor: base.Proveedor) -> str:
	return "\\" if proveedor.esquema == "local" else "/"


def recorrer(
	proveedor: base.Proveedor,
	ruta: str,
	cancelacion=None,
	patron: str = "",
	profundidad_maxima: int | None = None,
	incluir_carpetas: bool = True,
	carpetas_despues: bool = False,
	filtro_carpetas: bool = False,
	al_error: Callable[[str, base.ErrorArchivos], None] | None = None,
) -> Iterator[Elemento]:
	"""Genera los elementos bajo ``ruta`` (sin incluir la propia ``ruta``).

	:param patron: si se da, solo se devuelven los ARCHIVOS que coinciden (y las
		carpetas si ``filtro_carpetas``); las carpetas se recorren siempre.
	:param profundidad_maxima: ``0`` = solo hijos directos; ``None`` = sin límite.
	:param incluir_carpetas: devolver también las carpetas.
	:param carpetas_despues: devolver cada carpeta DESPUÉS de su contenido
		(para borrar de dentro hacia fuera).
	:param al_error: recibe (ruta, error) de las carpetas que no se pudieron leer.
	:raises Cancelado: si se cancela.
	"""
	analizado = Patron.analizar(patron) if patron else None
	sep = _sep(proveedor)
	yield from _recorrer(proveedor, ruta, "", 0, cancelacion, analizado, profundidad_maxima, incluir_carpetas,
		carpetas_despues, filtro_carpetas, al_error, sep)


def _recorrer(proveedor, ruta, prefijo, nivel, cancelacion, patron, maxima, incluir_carpetas, despues, filtro_carpetas, al_error, sep):
	base.comprobar(cancelacion)
	try:
		entradas = proveedor.listar(ruta, cancelacion)
	except base.Cancelado:
		raise
	except base.ErrorArchivos as error:
		if al_error is not None:
			al_error(ruta, error)
		return
	for entrada in entradas:
		base.comprobar(cancelacion)
		relativo = f"{prefijo}{sep}{entrada.nombre}" if prefijo else entrada.nombre
		elemento = Elemento(entrada, relativo, nivel)
		if entrada.es_carpeta and not entrada.es_enlace:
			coincide = patron is None or not filtro_carpetas or patron.coincide(entrada.nombre)
			if incluir_carpetas and coincide and not despues:
				yield elemento
			if maxima is None or nivel < maxima:
				yield from _recorrer(proveedor, entrada.ruta, relativo, nivel + 1, cancelacion, patron, maxima,
					incluir_carpetas, despues, filtro_carpetas, al_error, sep)
			if incluir_carpetas and coincide and despues:
				yield elemento
		elif entrada.es_carpeta:
			# Enlace o unión a carpeta: se devuelve como elemento, nunca se recorre.
			if incluir_carpetas and (patron is None or not filtro_carpetas or patron.coincide(entrada.nombre)):
				yield elemento
		elif patron is None or patron.coincide(entrada.nombre):
			yield elemento


@dataclass
class Totales:
	carpetas: int = 0
	archivos: int = 0
	bytes: int = 0
	errores: int = 0


def sumar(proveedor: base.Proveedor, ruta: str, cancelacion=None) -> Totales:
	"""Tamaño total de una carpeta: carpetas, archivos y bytes (sin seguir enlaces).

	Solo usa los metadatos del listado: no abre archivos, así que no descarga
	los que están solo en la nube.
	"""
	totales = Totales()

	def anotar_error(_ruta: str, _error: base.ErrorArchivos) -> None:
		totales.errores += 1

	for elemento in recorrer(proveedor, ruta, cancelacion, al_error=anotar_error):
		entrada = elemento.entrada
		if entrada.es_carpeta:
			totales.carpetas += 1
		else:
			totales.archivos += 1
			if entrada.tamano > 0:
				totales.bytes += entrada.tamano
	return totales
