# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Columnas y vista por carpeta (diseño 2.0, 10.4 y 10.5). Sin wx.

``data/config/vistas_carpeta.json``::

	{"version": 1,
	 "conjuntos": [ConjuntoVista...],
	 "reglas": [{"tipo": "ruta", "patron": "D:\\\\Música\\\\**", "conjunto": "Música"},
	            {"tipo": "contenido", "extensiones": ["mp3"], "proporcion": 0.6, "conjunto": "Música"}],
	 "recordadas": {"D:\\\\Fotos": {"orden": "fecha", "inverso": true, "vista": "completa", "filtro": ""}}}

Al entrar en una carpeta, la primera regla que coincide (las de ruta antes que
las de contenido; la de contenido con la lista ya leída, sin E/S extra) da el
conjunto que se aplica. Las carpetas recordadas (``vista.recordar_vista_por_carpeta``)
guardan como mucho 500, las más recientes.

``conjuntos`` y ``proponer_conjunto`` son las funciones de destino de la
fachada ``zc.vistas`` de los complementos (3.7): su firma no cambia.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import almacen_json
from app.services.vistas_modelo import MAX_COLUMNAS_LECTURA, ConjuntoVista

log = logging.getLogger(__name__)

ARCHIVO = "vistas_carpeta.json"
VERSION = 1
MAX_RECORDADAS = 500
POR_DEFECTO: dict[str, Any] = {"version": VERSION, "conjuntos": [], "reglas": [], "recordadas": {}}
TIPO_RUTA, TIPO_CONTENIDO = "ruta", "contenido"

_candado = threading.RLock()


@dataclass
class ReglaVista:
	"""Regla que elige un conjunto: por ruta (patrón con ``**``) o por contenido (proporción de extensiones)."""

	tipo: str
	conjunto: str
	patron: str = ""
	extensiones: tuple[str, ...] = ()
	proporcion: float = 0.6

	def como_dict(self) -> dict[str, Any]:
		if self.tipo == TIPO_RUTA:
			return {"tipo": TIPO_RUTA, "patron": self.patron, "conjunto": self.conjunto}
		return {"tipo": TIPO_CONTENIDO, "extensiones": list(self.extensiones), "proporcion": self.proporcion, "conjunto": self.conjunto}

	@classmethod
	def desde_dict(cls, datos: dict) -> ReglaVista | None:
		if not isinstance(datos, dict) or datos.get("tipo") not in (TIPO_RUTA, TIPO_CONTENIDO) or not datos.get("conjunto"):
			return None
		try:
			proporcion = float(datos.get("proporcion", 0.6))
		except (TypeError, ValueError):
			proporcion = 0.6
		extensiones = tuple(str(e).lower().lstrip(".") for e in datos.get("extensiones", []) or [] if str(e).strip())
		return cls(str(datos["tipo"]), str(datos["conjunto"]), str(datos.get("patron", "")), extensiones,
			min(1.0, max(0.05, proporcion)))


@dataclass
class DatosVistas:
	conjuntos: list[ConjuntoVista] = field(default_factory=list)
	reglas: list[ReglaVista] = field(default_factory=list)
	recordadas: dict[str, dict[str, Any]] = field(default_factory=dict)

	def conjunto(self, nombre: str) -> ConjuntoVista | None:
		clave = nombre.casefold()
		return next((c for c in self.conjuntos if c.nombre.casefold() == clave), None)


def cargar(carpeta: Path | None = None) -> DatosVistas:
	datos = almacen_json.leer(ARCHIVO, POR_DEFECTO, carpeta)
	resultado = DatosVistas()
	for elemento in datos.get("conjuntos", []) or []:
		if isinstance(elemento, dict) and str(elemento.get("nombre", "")).strip():
			conjunto = ConjuntoVista.desde_dict(elemento)
			if resultado.conjunto(conjunto.nombre) is None:
				resultado.conjuntos.append(conjunto)
	for elemento in datos.get("reglas", []) or []:
		regla = ReglaVista.desde_dict(elemento)
		if regla is not None:
			resultado.reglas.append(regla)
	recordadas = datos.get("recordadas") or {}
	if isinstance(recordadas, dict):
		resultado.recordadas = {str(k): dict(v) for k, v in recordadas.items() if isinstance(v, dict)}
	return resultado


def guardar(datos: DatosVistas, carpeta: Path | None = None) -> None:
	recordadas = dict(list(datos.recordadas.items())[-MAX_RECORDADAS:])
	almacen_json.escribir(ARCHIVO, {
		"version": VERSION,
		"conjuntos": [c.como_dict() for c in datos.conjuntos],
		"reglas": [r.como_dict() for r in datos.reglas],
		"recordadas": recordadas,
	}, carpeta)


# ── Elegir el conjunto de una carpeta ──────────────────────────────────────


def _normalizar(ruta: str) -> str:
	return ruta.replace("/", "\\").rstrip("\\").casefold()


def coincide_ruta(patron: str, ruta: str) -> bool:
	"""``D:\\Música\\**`` vale para ``D:\\Música`` y todo lo de dentro; sin ``**``, la carpeta exacta (con ``*`` y ``?``)."""
	patron_n, ruta_n = _normalizar(patron), _normalizar(ruta)
	if patron_n.endswith("\\**"):
		base = patron_n[:-3]
		# En fnmatch, «*» también salta las barras: «base\\*» vale para cualquier profundidad.
		return fnmatch.fnmatchcase(ruta_n, base) or fnmatch.fnmatchcase(ruta_n, base + "\\*")
	return fnmatch.fnmatchcase(ruta_n, patron_n)


def proporcion_extensiones(nombres: Iterable[str], extensiones: Sequence[str]) -> float:
	"""Fracción de ARCHIVOS cuya extensión está en la lista (las carpetas no cuentan)."""
	buscadas = {e.lower().lstrip(".") for e in extensiones}
	total = coinciden = 0
	for nombre in nombres:
		total += 1
		punto = nombre.rfind(".")
		if punto > 0 and nombre[punto + 1:].lower() in buscadas:
			coinciden += 1
	return coinciden / total if total else 0.0


def elegir(datos: DatosVistas, ruta: str, archivos: Sequence[str] = ()) -> ConjuntoVista | None:
	"""Conjunto de la primera regla que coincide (ruta antes que contenido), o ``None``.

	:param archivos: nombres de los archivos ya leídos de la carpeta (sin carpetas).
	"""
	for regla in datos.reglas:
		if regla.tipo == TIPO_RUTA and regla.patron and coincide_ruta(regla.patron, ruta):
			conjunto = datos.conjunto(regla.conjunto)
			if conjunto is not None:
				return conjunto
	if archivos:
		for regla in datos.reglas:
			if regla.tipo == TIPO_CONTENIDO and regla.extensiones and \
					proporcion_extensiones(archivos, regla.extensiones) >= regla.proporcion - 1e-9:
				conjunto = datos.conjunto(regla.conjunto)
				if conjunto is not None:
					return conjunto
	return None


def recordar(datos: DatosVistas, ruta: str, orden: str, inverso: bool, vista: str, filtro: str) -> None:
	"""Recuerda el orden, la vista y el filtro de una carpeta (la más reciente, al final)."""
	clave = ruta.rstrip("\\") or ruta
	datos.recordadas.pop(clave, None)
	datos.recordadas[clave] = {"orden": orden, "inverso": bool(inverso), "vista": vista, "filtro": filtro}
	while len(datos.recordadas) > MAX_RECORDADAS:
		datos.recordadas.pop(next(iter(datos.recordadas)))


def recordada(datos: DatosVistas, ruta: str) -> dict[str, Any] | None:
	return datos.recordadas.get(ruta.rstrip("\\") or ruta)


def lectura_valida(lectura: Sequence[str]) -> list[str]:
	"""Orden de lectura sin repetidos y con 15 columnas como mucho (10.5)."""
	resultado: list[str] = []
	for columna in lectura:
		if columna and columna not in resultado:
			resultado.append(columna)
	return resultado[:MAX_COLUMNAS_LECTURA]


# ── Fachada zc.vistas (3.7) ─────────────────────────────────────────────────


def conjuntos() -> list[str]:
	"""Nombres de los conjuntos de columnas guardados."""
	with _candado:
		return [c.nombre for c in cargar().conjuntos]


def proponer_conjunto(nombre: str, columnas: list[str], lectura: list[str],
		extensiones: Sequence[str] = (), proporcion: float = 0.6) -> bool:
	"""Añade un conjunto y su regla de contenido si no existe uno con ese nombre (lo usa ``zc.metadatos``).

	:return: verdadero si se añadió; falso si ya había uno con ese nombre (no se toca).
	"""
	nombre = " ".join(str(nombre).split())
	if not nombre:
		return False
	with _candado:
		datos = cargar()
		if datos.conjunto(nombre) is not None:
			return False
		datos.conjuntos.append(ConjuntoVista(nombre, tuple(columnas), lectura=tuple(lectura_valida(lectura))))
		extensiones = tuple(str(e).lower().lstrip(".") for e in extensiones if str(e).strip())
		if extensiones:
			datos.reglas.append(ReglaVista(TIPO_CONTENIDO, nombre, extensiones=extensiones, proporcion=float(proporcion)))
		try:
			guardar(datos)
		except OSError:
			log.exception("No se pudo guardar el conjunto propuesto %s", nombre)
			return False
	log.info("Conjunto de vista propuesto y añadido: %s", nombre)
	return True
