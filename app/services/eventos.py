# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bus de eventos de la aplicación (diseño 2.0, 14.4). Sin wx.

Por qué así:

- **Un solo bus por proceso** (``bus()``): lo usan piezas que no reciben la
  ventana (``ordenes.catalogo_cambiado``, el servicio de copias, la fachada de
  los complementos) y la ventana lo da como ``servicio("eventos")``.
- **Solo informa**. ``emitir`` encola y vuelve; los suscriptores se llaman
  siempre en el hilo de la interfaz, en el orden de emisión, a través del
  planificador (``wx.CallAfter``, que ``main.py`` fija tras crear ``wx.App``).
  Sin planificador (pruebas sin interfaz) se entrega en el acto en el hilo
  que emite. Lo que debe ocurrir en un orden preciso respecto a una orden o
  a un diálogo (grabar un paso de macro) va por llamada directa, nunca por aquí.
- Cada suscriptor se llama protegido: una excepción se registra y no corta a
  los demás.
- ``cerrar`` y el planificador comparten un candado, así ninguna llamada al
  planificador se cuela después de cerrar (tras destruir ``wx.App`` daría
  ``PyNoAppError``).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

Planificador = Callable[[Callable[[], None]], None]

# Eventos del núcleo (los datos de cada uno están en el diseño, 14.4).
AL_ARRANCAR = "al_arrancar"
AL_CERRAR = "al_cerrar"
AL_CAMBIAR_CARPETA = "al_cambiar_carpeta"
AL_CAMBIAR_CURSOR = "al_cambiar_cursor"
AL_CAMBIAR_MARCAS = "al_cambiar_marcas"
AL_ACTIVAR_PANEL = "al_activar_panel"
AL_EMPEZAR_OPERACION = "al_empezar_operacion"
AL_TERMINAR_OPERACION = "al_terminar_operacion"
AL_CAMBIAR_PREFERENCIA = "al_cambiar_preferencia"
AL_CONECTAR = "al_conectar"
AL_DESCONECTAR = "al_desconectar"
AL_EJECUTAR_ORDEN = "al_ejecutar_orden"
AL_TERMINAR_ORDEN = "al_terminar_orden"
AL_COPIAR_PORTAPAPELES = "al_copiar_portapapeles"
AL_RESTAURAR = "al_restaurar"
AL_CAMBIAR_CATALOGO = "al_cambiar_catalogo"

EVENTOS_NUCLEO = (
	AL_ARRANCAR, AL_CERRAR, AL_CAMBIAR_CARPETA, AL_CAMBIAR_CURSOR, AL_CAMBIAR_MARCAS, AL_ACTIVAR_PANEL,
	AL_EMPEZAR_OPERACION, AL_TERMINAR_OPERACION, AL_CAMBIAR_PREFERENCIA, AL_CONECTAR, AL_DESCONECTAR,
	AL_EJECUTAR_ORDEN, AL_TERMINAR_ORDEN, AL_COPIAR_PORTAPAPELES, AL_RESTAURAR, AL_CAMBIAR_CATALOGO,
)


class Bus:
	"""Publicación y suscripción con entrega en el hilo de la interfaz."""

	def __init__(self) -> None:
		self._candado = threading.RLock()
		self._suscriptores: dict[str, list[Callable[..., None]]] = {}
		self._planificador: Planificador | None = None
		self._cola: deque[tuple[int, str, dict[str, Any]]] = deque()
		self._contador = 0
		self._cerrado = False

	# ── Configuración ────────────────────────────────────────────────────────

	def fijar_planificador(self, planificador: Planificador | None) -> None:
		"""Función que lleva una llamada al hilo de la interfaz (``wx.CallAfter``)."""
		with self._candado:
			self._planificador = planificador

	@property
	def cerrado(self) -> bool:
		return self._cerrado

	# ── Suscripción ──────────────────────────────────────────────────────────

	def suscribir(self, nombre: str, funcion: Callable[..., None]) -> Callable[[], None]:
		"""Suscribe ``funcion(**datos)`` al evento ``nombre``; devuelve la función que cancela."""
		with self._candado:
			self._suscriptores.setdefault(nombre, []).append(funcion)

		def cancelar() -> None:
			with self._candado:
				lista = self._suscriptores.get(nombre, [])
				if funcion in lista:
					lista.remove(funcion)

		return cancelar

	def suscritos(self, nombre: str) -> int:
		with self._candado:
			return len(self._suscriptores.get(nombre, []))

	# ── Emisión ──────────────────────────────────────────────────────────────

	def emitir(self, nombre: str, **datos: Any) -> None:
		"""Encola la entrega de ``nombre`` (desde cualquier hilo) y vuelve."""
		with self._candado:
			if self._cerrado:
				log.debug("Evento «%s» descartado: el bus está cerrado", nombre)
				return
			planificador = self._planificador
			if planificador is None:
				entregar_ya = True
			else:
				entregar_ya = False
				self._contador += 1
				numero = self._contador
				self._cola.append((numero, nombre, datos))
				try:
					planificador(lambda n=numero: self._entregar_pendiente(n))
				except Exception:  # noqa: BLE001 - sin bucle de eventos se entrega al vaciar o se pierde con aviso
					log.warning("No se pudo planificar la entrega de «%s»", nombre, exc_info=True)
		if entregar_ya:
			self._entregar(nombre, datos)

	def emitir_sincrono(self, nombre: str, **datos: Any) -> None:
		"""Llama a los suscriptores en el acto (solo en el hilo de la interfaz; lo usa ``al_cerrar``)."""
		if self._cerrado:
			log.debug("Evento síncrono «%s» descartado: el bus está cerrado", nombre)
			return
		self._entregar(nombre, datos)

	def vaciar(self) -> None:
		"""Entrega en el acto, en orden, todo lo que estaba en la cola (no se repite después)."""
		while True:
			with self._candado:
				if not self._cola:
					return
				_numero, nombre, datos = self._cola.popleft()
			self._entregar(nombre, datos)

	def cerrar(self) -> None:
		"""Desde aquí ``emitir`` descarta y las entregas pendientes no se hacen."""
		with self._candado:
			self._cerrado = True
			pendientes = len(self._cola)
			self._cola.clear()
			self._planificador = None
		if pendientes:
			log.info("Bus cerrado con %s eventos sin entregar", pendientes)

	# ── Entrega ──────────────────────────────────────────────────────────────

	def _entregar_pendiente(self, numero: int) -> None:
		"""Entrega del planificador: solo si sigue en la cola (``vaciar`` pudo adelantarse)."""
		with self._candado:
			if self._cerrado:
				return
			elemento = None
			for indice, (n, nombre, datos) in enumerate(self._cola):
				if n == numero:
					elemento = (nombre, datos)
					del self._cola[indice]
					break
		if elemento is not None:
			self._entregar(*elemento)

	def _entregar(self, nombre: str, datos: dict[str, Any]) -> None:
		with self._candado:
			funciones = list(self._suscriptores.get(nombre, []))
		for funcion in funciones:
			try:
				funcion(**datos)
			except Exception:  # noqa: BLE001 - un suscriptor roto no corta a los demás
				log.exception("Falló un suscriptor del evento «%s»", nombre)


_bus: list[Bus | None] = [None]
_candado_global = threading.Lock()


def bus() -> Bus:
	"""El bus único del proceso (se crea la primera vez)."""
	with _candado_global:
		if _bus[0] is None:
			_bus[0] = Bus()
		return _bus[0]


def reiniciar() -> Bus:
	"""Sustituye el bus por uno nuevo (solo pruebas)."""
	with _candado_global:
		_bus[0] = Bus()
		return _bus[0]


def puentear_configuracion(config: Any) -> Callable[[], None]:
	"""Reemite cada cambio de ``config`` como ``al_cambiar_preferencia`` (clave, anterior, nuevo).

	``Configuracion.suscribir`` avisa en el hilo que hizo el cambio (también el
	temporizador de ``establecer_diferido``); ``emitir`` lo lleva al hilo de la
	interfaz. Devuelve la función que cancela el puente.
	"""

	def reemitir(clave: str, anterior: Any, nuevo: Any) -> None:
		bus().emitir(AL_CAMBIAR_PREFERENCIA, clave=clave, anterior=anterior, nuevo=nuevo)

	resultado = config.suscribir(reemitir)
	return resultado if callable(resultado) else (lambda: None)
