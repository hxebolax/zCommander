# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Gestor de operaciones: carriles por volumen sobre ``GestorTareas``.

- Cada operación declara sus ``carriles`` (volúmenes de origen y destino). Una
  operación arranca cuando ninguno de sus carriles está ocupado; así dos copias
  que leen o escriben el mismo disco van en serie y las de discos distintos en
  paralelo, hasta ``max_paralelas`` (los hilos del ``GestorTareas``).
- «En cola» añade el carril único ``__cola__``: esas operaciones van de una en
  una, en orden, y además respetan los carriles de volumen.
- Las operaciones sin carriles (metadatos: crear carpeta, renombrar) no
  esperan a nadie.
- Se arranca en orden de llegada: una operación nunca adelanta a otra anterior
  que comparte carril con ella (sin inanición).
- La interfaz consulta ``operaciones()`` con un temporizador; los suscriptores
  y ``al_terminar`` reciben avisos en el hilo de la interfaz.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from app.core.tareas import GestorTareas, TokenCancelacion, ejecutar_en_interfaz
from app.services.operaciones.modelo import ContextoEjecucion, Decisor, Estado, Operacion
from app.services.vfs import base

log = logging.getLogger(__name__)

CARRIL_COLA = "__cola__"


class GestorOperaciones:
	"""Lanza, ordena y detiene operaciones.

	:param decisor: quien responde a conflictos y errores (la interfaz).
	:param max_paralelas: hilos para operaciones a la vez (se fija al crearlo).
	:param ejecutor_interfaz: para pruebas sin wx (``app.core.tareas.ejecutor_directo``).
	"""

	def __init__(self, decisor: Decisor, max_paralelas: int = 3, ejecutor_interfaz=None) -> None:
		self.decisor = decisor
		self._tareas = GestorTareas(max_hilos=max_paralelas, nombre="operaciones", ejecutor_interfaz=ejecutor_interfaz)
		self._candado = threading.RLock()
		self._todas: list[Operacion] = []
		self._pendientes: list[tuple[Operacion, frozenset[str]]] = []
		self._ocupados: set[str] = set()
		self._al_terminar: dict[int, Callable[[Operacion], None]] = {}
		self._suscriptores: list[Callable[[Operacion], None]] = []
		self._ejecutor_interfaz = ejecutor_interfaz
		self._cerrado = False

	# Suscripción ------------------------------------------------------------------

	def suscribir(self, funcion: Callable[[Operacion], None]) -> None:
		"""``funcion(operacion)`` en el hilo de la interfaz al lanzar y al terminar cada operación."""
		self._suscriptores.append(funcion)

	def _en_interfaz(self, funcion, *args) -> None:
		if self._ejecutor_interfaz is not None:
			self._ejecutor_interfaz(funcion, *args)
		else:
			ejecutar_en_interfaz(funcion, *args)

	def _avisar(self, operacion: Operacion) -> None:
		for funcion in list(self._suscriptores):
			self._en_interfaz(funcion, operacion)

	# Lanzar ---------------------------------------------------------------------------

	def lanzar(self, operacion: Operacion, en_cola: bool = False,
			al_terminar: Callable[[Operacion], None] | None = None) -> Operacion:
		"""Pone la operación a la espera de sus carriles.

		:param al_terminar: se llama en el hilo de la interfaz con la operación ya en
			estado final (después de los suscriptores, que anuncian el resumen y
			refrescan los paneles).
		"""
		if threading.current_thread().name.startswith("operaciones"):
			# Una operación que lanza otra y la espera se bloquearía con sus propios carriles:
			# las suboperaciones se ejecutan en el mismo hilo con ``sub.ejecutar(ctx)``.
			raise RuntimeError("No se puede lanzar una operación desde el hilo de otra; use sub.ejecutar(ctx)")
		carriles = frozenset(operacion.carriles | ({CARRIL_COLA} if en_cola else set()))
		operacion.contexto = ContextoEjecucion(TokenCancelacion(), self.decisor)
		operacion.contexto.operacion = operacion
		operacion.en_cola = en_cola  # type: ignore[attr-defined]
		with self._candado:
			if self._cerrado:
				raise RuntimeError("El gestor de operaciones está cerrado")
			self._todas.append(operacion)
			self._pendientes.append((operacion, carriles))
			if al_terminar is not None:
				self._al_terminar[operacion.id] = al_terminar
		self._avisar(operacion)
		self._arrancar()
		return operacion

	def _arrancar(self) -> None:
		"""Arranca, en orden de llegada, las pendientes cuyos carriles están libres."""
		listas: list[tuple[Operacion, frozenset[str]]] = []
		with self._candado:
			if self._cerrado:
				return
			reservados: set[str] = set(self._ocupados)
			quedan = []
			canceladas = []
			for operacion, carriles in self._pendientes:
				if operacion.contexto.cancelado():
					if operacion.estado == Estado.EN_COLA:
						operacion.cambiar_estado(Estado.CANCELADA)
					canceladas.append(operacion)
					continue
				if carriles & reservados:
					# Ocupado o lo espera una anterior: esta no adelanta.
					reservados |= carriles
					quedan.append((operacion, carriles))
					continue
				reservados |= carriles
				self._ocupados |= carriles
				listas.append((operacion, carriles))
			self._pendientes = quedan
		for operacion in canceladas:
			self._terminada(operacion)
		for operacion, carriles in listas:
			tarea = self._tareas.enviar(self._ejecutar, operacion, carriles, nombre=f"operacion-{operacion.tipo}")
			if tarea is None:
				log.warning("No se pudo arrancar la operación %s (gestor cerrado)", operacion.descripcion())
				with self._candado:
					self._ocupados -= carriles
				if not operacion.estado.final:
					operacion.cambiar_estado(Estado.CANCELADA)
				self._terminada(operacion)

	def _ejecutar(self, _tarea, operacion: Operacion, carriles: frozenset[str]) -> None:
		try:
			operacion.ejecutar(operacion.contexto)
			if not operacion.estado.final:
				if operacion.contexto.cancelado():
					operacion.cambiar_estado(Estado.CANCELADA)
				else:
					if operacion.estado in (Estado.EN_COLA, Estado.ANALIZANDO, Estado.ESPERANDO_DECISION, Estado.EN_PAUSA):
						# Una subclase que no pasó por EJECUTANDO (o terminó en pausa) no se queda colgada.
						operacion.cambiar_estado(Estado.EJECUTANDO)
					operacion.cambiar_estado(Estado.TERMINADA_CON_ERRORES if operacion.errores else Estado.TERMINADA)
		except base.Cancelado:
			if not operacion.estado.final:
				operacion.cambiar_estado(Estado.CANCELADA)
		except Exception as error:  # noqa: BLE001 - el fallo de una operación no tumba el gestor
			log.exception("Falló la operación %s", operacion.descripcion())
			operacion.anotar_error("", str(error))
			if not operacion.estado.final:
				try:
					if operacion.estado == Estado.EN_COLA:
						operacion.cambiar_estado(Estado.EJECUTANDO)
					operacion.cambiar_estado(Estado.FALLIDA)
				except ValueError:
					log.debug("No se pudo marcar como fallida", exc_info=True)
		finally:
			with self._candado:
				self._ocupados -= carriles
			self._terminada(operacion)
			self._arrancar()

	def _terminada(self, operacion: Operacion) -> None:
		"""Avisos de fin: suscriptores y ``al_terminar`` (una sola vez por operación)."""
		with self._candado:
			al_terminar = self._al_terminar.pop(operacion.id, None)
		self._avisar(operacion)
		if al_terminar is not None:
			self._en_interfaz(al_terminar, operacion)

	# Consultar y controlar ------------------------------------------------------------

	def operaciones(self) -> list[Operacion]:
		with self._candado:
			return list(self._todas)

	def en_marcha(self) -> list[Operacion]:
		return [o for o in self.operaciones() if not o.estado.final]

	def limpiar_terminadas(self) -> None:
		with self._candado:
			self._todas = [o for o in self._todas if not o.estado.final]

	def cancelar(self, operacion: Operacion) -> None:
		operacion.cancelar()
		with self._candado:
			en_espera = any(o is operacion for o, _c in self._pendientes)
		if en_espera:
			self._arrancar()

	def cancelar_todas(self) -> None:
		for operacion in self.en_marcha():
			self.cancelar(operacion)

	def esperar(self, segundos: float = 30.0) -> bool:
		"""Espera a que terminen todas («Esperar y salir», pruebas). ``True`` si terminaron.

		No llamar desde el hilo de la interfaz salvo en pruebas: bloquea.
		"""
		limite = time.monotonic() + segundos
		while time.monotonic() < limite:
			if not self.en_marcha():
				return True
			time.sleep(0.02)
		return not self.en_marcha()

	def apagar(self, espera: float = 3.0) -> bool:
		"""Cancela todo y espera un tiempo limitado (al salir)."""
		with self._candado:
			self._cerrado = True
		for operacion in self.en_marcha():
			operacion.cancelar()
		return self._tareas.apagar(espera)
