# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Renombrar uno o muchos elementos (renombrar en el sitio y renombrado múltiple).

``OperacionRenombrar(proveedor, pares, descripcion)``: ``pares`` es una lista
de (ruta actual, nombre nuevo). Resuelve las cadenas y los ciclos (a→b y b→a)
con nombres temporales, deja los pasos para deshacer y declara su carril
(ninguno en disco local; el del contenedor en comprimidos y servidores).
El bloque E calcula los pares (``services/renombrado.py``) y hace el diálogo.
"""

from __future__ import annotations

import os

import builtins
import logging

from app.services import formato
from app.services.operaciones import nombres
from app.services.operaciones.deshacer import AccionDeshacer, Paso
from app.services.operaciones.modelo import ContextoEjecucion, Estado, Operacion, claves_carril
from app.services.vfs import base, rutas

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class OperacionRenombrar(Operacion):
	"""Renombra ``pares`` (ruta actual, nombre nuevo) dentro de su misma carpeta."""

	tipo = "renombrar"

	def __init__(self, proveedor: base.Proveedor, pares: list[tuple[str, str]], descripcion: str = "") -> None:
		super().__init__()
		self.proveedor = proveedor
		self.pares = [(r, n) for r, n in pares if proveedor.nombre(r) != n]
		self._descripcion = descripcion

	def descripcion(self) -> str:
		if self._descripcion:
			return self._descripcion
		n = len(self.pares)
		return _("Renombrar {q}").format(q=self.proveedor.nombre(self.pares[0][0]) if n == 1 else formato.plural(n, _("{n} elemento"), _("{n} elementos")))

	@property
	def carriles(self) -> frozenset[str]:
		if self.proveedor.esquema == "local" or not self.pares:
			return frozenset()
		return frozenset(claves_carril(self.proveedor, [r for r, _n in self.pares]))

	def _carpeta(self, ruta: str) -> str:
		"""Carpeta que contiene ``ruta``.

		En una lista de resultados (búsqueda, cesta, vista plana) ``padre`` es
		``None`` porque la lista no tiene carpeta superior, pero cada ruta es
		absoluta y real: su carpeta es la del disco.
		"""
		carpeta = self.proveedor.padre(ruta)
		if carpeta is None and os.path.isabs(ruta):
			return os.path.dirname(ruta)
		return carpeta or ""

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return list({(self.proveedor.esquema, self._carpeta(r)) for r, _n in self.pares})

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.pares))
		for ruta, nuevo in self.pares:
			problema = rutas.problema_en_nombre(nuevo) if self.proveedor.esquema in ("local", "resultados") else None
			if problema:
				raise base.NombreNoValido(problema, ruta)
		destinos = {}
		for ruta, nuevo in self.pares:
			destinos[ruta] = self.proveedor.unir(self._carpeta(ruta), nuevo)
		origenes = {r.casefold() for r in destinos}
		accion = AccionDeshacer(self.descripcion())
		# Paso 1: los que van a un nombre que hoy ocupa otro de la lista pasan por un temporal.
		intermedios: list[tuple[str, str, str]] = []
		directos: list[tuple[str, str]] = []
		for ruta, destino in destinos.items():
			solo_mayusculas = ruta.casefold() == destino.casefold()
			if destino.casefold() in origenes and not solo_mayusculas:
				temporal = self.proveedor.unir(self._carpeta(ruta), nombres.temporal())
				intermedios.append((ruta, temporal, destino))
			else:
				directos.append((ruta, destino))
		with self.proveedor.transaccion():
			for ruta, temporal, _destino in intermedios:
				ctx.comprobar()
				self.proveedor.renombrar(ruta, temporal)
			for ruta, destino in directos:
				ctx.comprobar()
				self.progresar(actual=self.proveedor.nombre(ruta))
				try:
					self.proveedor.renombrar(ruta, destino)
					accion.pasos.append(Paso("renombrar", destino, antes=ruta))
					self.sumar(archivos_hechos=1)
				except base.ErrorArchivos as error:
					self.anotar_error(ruta, error.mensaje)
			for ruta, temporal, destino in intermedios:
				try:
					self.proveedor.renombrar(temporal, destino)
					accion.pasos.append(Paso("renombrar", destino, antes=ruta))
					self.sumar(archivos_hechos=1)
				except base.ErrorArchivos as error:
					self.anotar_error(ruta, error.mensaje)
					try:
						self.proveedor.renombrar(temporal, ruta)
					except base.ErrorArchivos:
						log.error("El archivo %s quedó con el nombre temporal %s", ruta, temporal)
		if self.proveedor.esquema == "local" and accion.pasos:
			self.deshacer = accion
