# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sincronizar carpetas: ejecuta las acciones ya decididas en la lista como UNA operación del motor.

Sección 9.6: sincronizar usa suboperaciones en su mismo hilo
(``Operacion.ejecutar_sub``), nunca ``lanzar`` (se bloquearía con sus propios
carriles). Por cada carpeta de destino crea una ``OperacionCopiar`` con
política Sobrescribir (las decisiones ya se tomaron en la lista) y, para los
borrados de cada lado, una ``OperacionEliminar``. Así hereda del núcleo la
copia segura (temporal y renombrado), la verificación, el progreso, la pausa,
la cancelación y los errores por elemento.

Orden: primero las copias y después los borrados, para que un fallo a medias
nunca deje un archivo borrado sin su copia.
"""

from __future__ import annotations

import builtins
import logging
import re
from collections.abc import Sequence
from dataclasses import replace

from app.services.diferencias_carpetas import Accion, Diferencia
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar
from app.services.operaciones.eliminar import OperacionEliminar
from app.services.operaciones.modelo import ContextoEjecucion, Estado, Operacion, Politica, claves_carril
from app.services.vfs import base

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _partes(relativo: str) -> list[str]:
	return [p for p in re.split(r"[\\/]", relativo) if p]


class OperacionSincronizar(Operacion):
	"""Copia y borra entre ``izquierda`` y ``derecha`` según la acción de cada fila.

	:param filas: diferencias con su acción (las de acción Nada o Conflicto se ignoran).
	:param opciones: opciones de copia (la política se fuerza a Sobrescribir).
	:param papelera: los borrados van a la papelera si el proveedor la admite.
	"""

	tipo = "sincronizar"

	def __init__(
		self,
		izquierda: tuple[base.Proveedor, str],
		derecha: tuple[base.Proveedor, str],
		filas: Sequence[Diferencia],
		opciones: OpcionesCopia | None = None,
		papelera: bool = True,
	) -> None:
		super().__init__()
		self.izquierda = izquierda
		self.derecha = derecha
		self.filas = [f for f in filas if f.accion not in (Accion.NADA, Accion.CONFLICTO)]
		self.opciones = replace(opciones or OpcionesCopia(), politica=Politica.SOBRESCRIBIR, patron="")
		self.papelera = papelera
		#: Elementos que no se pudieron copiar (de todas las copias), para «Reintentar».
		self.fallidos: list[base.Entrada] = []

	def descripcion(self) -> str:
		(prov_i, ruta_i), (prov_d, ruta_d) = self.izquierda, self.derecha
		return _("Sincronizar {i} y {d}").format(i=prov_i.mostrar(ruta_i), d=prov_d.mostrar(ruta_d))

	@property
	def carriles(self) -> frozenset[str]:
		(prov_i, ruta_i), (prov_d, ruta_d) = self.izquierda, self.derecha
		return frozenset(claves_carril(prov_i, [ruta_i]) | claves_carril(prov_d, [ruta_d]))

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		(prov_i, ruta_i), (prov_d, ruta_d) = self.izquierda, self.derecha
		return [(prov_i.esquema, ruta_i), (prov_d.esquema, ruta_d)]

	# ── Plan ─────────────────────────────────────────────────────────────────

	def _carpeta_de(self, lado: tuple[base.Proveedor, str], relativo: str) -> str:
		proveedor, ruta = lado
		for parte in _partes(relativo)[:-1]:
			ruta = proveedor.unir(ruta, parte)
		return ruta

	def plan(self) -> tuple[list[tuple[str, str, list[base.Entrada]]], list[tuple[str, list[base.Entrada]]]]:
		"""(copias, borrados) agrupados.

		Copias: ``[(sentido, carpeta_destino, entradas)]`` con sentido «derecha» o «izquierda».
		Borrados: ``[(lado, entradas)]``.
		"""
		copias: dict[tuple[str, str], list[base.Entrada]] = {}
		borrados: dict[str, list[base.Entrada]] = {}
		for fila in self.filas:
			if fila.accion == Accion.COPIAR_DERECHA and fila.izquierda is not None:
				carpeta = self._carpeta_de(self.derecha, fila.relativo)
				copias.setdefault(("derecha", carpeta), []).append(fila.izquierda)
			elif fila.accion == Accion.COPIAR_IZQUIERDA and fila.derecha is not None:
				carpeta = self._carpeta_de(self.izquierda, fila.relativo)
				copias.setdefault(("izquierda", carpeta), []).append(fila.derecha)
			elif fila.accion == Accion.ELIMINAR_DERECHA and fila.derecha is not None:
				borrados.setdefault("derecha", []).append(fila.derecha)
			elif fila.accion == Accion.ELIMINAR_IZQUIERDA and fila.izquierda is not None:
				borrados.setdefault("izquierda", []).append(fila.izquierda)
		return ([(sentido, carpeta, entradas) for (sentido, carpeta), entradas in copias.items()],
			list(borrados.items()))

	# ── Ejecución ────────────────────────────────────────────────────────────

	def _asegurar_carpeta(self, proveedor: base.Proveedor, raiz: str, carpeta: str) -> bool:
		"""Crea la carpeta de destino (y sus superiores bajo la raíz) si falta."""
		if carpeta == raiz or proveedor.existe(carpeta):
			return True
		superior = proveedor.padre(carpeta)
		if superior and superior != carpeta and not self._asegurar_carpeta(proveedor, raiz, superior):
			return False
		try:
			proveedor.crear_carpeta(carpeta)
		except base.YaExiste:
			return True
		except base.ErrorArchivos as error:
			self.anotar_error(carpeta, error.mensaje)
			return False
		return True

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.EJECUTANDO)
		copias, borrados = self.plan()
		for sentido, carpeta, entradas in copias:
			ctx.comprobar()
			origen = self.izquierda[0] if sentido == "derecha" else self.derecha[0]
			destino, raiz = self.derecha if sentido == "derecha" else self.izquierda
			self.progresar(actual=destino.mostrar(carpeta))
			if not self._asegurar_carpeta(destino, raiz, carpeta):
				self.sumar(omitidos=len(entradas))
				continue
			self.ejecutar_sub(OperacionCopiar(origen, entradas, destino, carpeta, replace(self.opciones)), ctx)
		for lado, entradas in borrados:
			ctx.comprobar()
			proveedor = self.izquierda[0] if lado == "izquierda" else self.derecha[0]
			papelera = self.papelera and proveedor.capacidades.papelera
			self.ejecutar_sub(OperacionEliminar(proveedor, entradas, papelera=papelera), ctx)
		log.info("Sincronización terminada: %d copias, %d borrados, %d errores",
			sum(len(e) for _s, _c, e in copias), sum(len(e) for _l, e in borrados), len(self.errores))
