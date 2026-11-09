# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Servicio de sonidos: la función única ``sonar`` (diseño 2.0, 4.3). Sin wx.

Una sola firma en toda la aplicación (la misma en ``ContextoOrden.sonar``,
``ContextoComplemento.sonar`` y ``Anfitrion.sonidos.sonar``)::

	sonar(evento, variante="", *, sustituye=False) -> bool

Se puede llamar desde cualquier hilo. El servicio solo FILTRA (sonidos
activos y evento activo, con un diccionario que se recalcula al cambiar la
configuración, no en cada llamada) y pasa la petición al ``Reproductor``
inyectado con ``iniciar``. Verdadero quiere decir que el reproductor
**aceptó** el sonido (4.4). Sin reproductor (pruebas, ``--probar-componente``)
``sonar`` devuelve falso y no hace nada.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

from app.services.sonidos import catalogo
from app.services.sonidos.catalogo import EventoSonido

log = logging.getLogger(__name__)


class Reproductor(Protocol):
	"""Lo que hace sonar de verdad: el motor de 4.4 (``app/services/sonidos/motor.py``, que crea ``app/ui/sonidos.iniciar``)."""

	def sonar(self, evento: EventoSonido, variante: str, sustituye: bool) -> bool:
		"""Resuelve el archivo, aplica volumen y caché, decide con la cola y encola.

		Verdadero si lo aceptó (volumen mayor que 0, archivo válido y no
		descartado en el momento). Con ``sustituye=True`` la decisión es
		definitiva. Menos de 5 ms; nunca bloquea.
		"""

	def recargar(self) -> None:
		"""Cambió el paquete, el volumen o los paquetes instalados: vacía la caché."""

	def cerrar(self) -> None:
		"""Vacía la cola, para el sonido en curso y espera al hilo 0,5 s como máximo."""


class _Estado:
	def __init__(self) -> None:
		self.candado = threading.RLock()
		self.config: Any = None
		self.reproductor: Reproductor | None = None
		self.activos = False
		self.cambios: dict[str, bool] = {}
		self.cancelar_suscripcion: Any = None


_estado = _Estado()


def iniciar(config: Any, reproductor: Reproductor | None) -> None:
	"""Inyecta la configuración y el reproductor; se suscribe a los cambios de ``sonidos.*``."""
	with _estado.candado:
		cerrar()
		_estado.config = config
		_estado.reproductor = reproductor
		_recalcular()
		try:
			_estado.cancelar_suscripcion = config.suscribir(_al_cambiar_config, "sonidos.")
		except Exception:  # noqa: BLE001 - una configuración falsa sin suscripción solo pierde el recálculo automático
			log.debug("La configuración no admite suscripción; se recalcula al iniciar", exc_info=True)
			_estado.cancelar_suscripcion = None


def fijar_reproductor(reproductor: Reproductor | None) -> None:
	"""Sustituye el reproductor (lo usa SO para poner el motor real, 14.9)."""
	with _estado.candado:
		anterior = _estado.reproductor
		_estado.reproductor = reproductor
	if anterior is not None and anterior is not reproductor:
		try:
			anterior.cerrar()
		except Exception:  # noqa: BLE001 - un reproductor que falla al cerrar no impide el cambio
			log.warning("El reproductor anterior falló al cerrarse", exc_info=True)


def reproductor() -> Reproductor | None:
	return _estado.reproductor


def cerrar() -> None:
	"""Cierra el reproductor y olvida la configuración (al salir)."""
	with _estado.candado:
		cancelar, _estado.cancelar_suscripcion = _estado.cancelar_suscripcion, None
		reproductor_actual, _estado.reproductor = _estado.reproductor, None
		_estado.config = None
		_estado.activos = False
	if callable(cancelar):
		cancelar()
	if reproductor_actual is not None:
		try:
			reproductor_actual.cerrar()
		except Exception:  # noqa: BLE001 - cerrar los sonidos nunca impide salir
			log.warning("El reproductor de sonidos falló al cerrarse", exc_info=True)


def _al_cambiar_config(clave: str, _anterior: Any, _nuevo: Any) -> None:
	_recalcular()
	if clave in ("sonidos.paquete", "sonidos.volumen"):
		actual = _estado.reproductor
		if actual is not None:
			try:
				actual.recargar()
			except Exception:  # noqa: BLE001 - un fallo al recargar deja los sonidos como estaban
				log.warning("El reproductor no pudo recargar", exc_info=True)


def _recalcular() -> None:
	"""Lee ``sonidos.activos`` y ``sonidos.eventos`` una vez (no en cada ``sonar``)."""
	config = _estado.config
	if config is None:
		_estado.activos, _estado.cambios = False, {}
		return
	try:
		activos = bool(config.obtener("sonidos.activos"))
		cambios = config.obtener("sonidos.eventos")
	except Exception:  # noqa: BLE001 - sin configuración legible, sin sonidos
		log.warning("No se pudo leer la configuración de sonidos", exc_info=True)
		activos, cambios = False, {}
	_estado.activos = activos
	_estado.cambios = {str(k): bool(v) for k, v in cambios.items()} if isinstance(cambios, dict) else {}


def evento_activo(id_evento: str) -> bool:
	"""Si el evento suena: lo que diga ``sonidos.eventos`` o, si no lo dice, su valor de fábrica."""
	if id_evento in _estado.cambios:
		return _estado.cambios[id_evento]
	evento = catalogo.evento(id_evento)
	return bool(evento and evento.por_defecto)


def sonar(evento: str, variante: str = "", *, sustituye: bool = False) -> bool:
	"""Pide el sonido ``evento`` (con su ``variante``). Verdadero si el reproductor lo aceptó."""
	actual = _estado.reproductor
	if actual is None or not _estado.activos:
		return False
	descriptor = catalogo.evento(evento)
	if descriptor is None:
		log.debug("Sonido desconocido: %s", evento)
		return False
	if not evento_activo(evento):
		return False
	try:
		return bool(actual.sonar(descriptor, variante, sustituye))
	except Exception:  # noqa: BLE001 - un sonido nunca rompe la orden que lo pidió
		log.warning("Falló el sonido %s", evento, exc_info=True)
		return False


def probar(evento: str, variante: str = "") -> bool:
	"""Hace sonar un evento aunque esté desactivado (botón «Probar» y mapa de sonidos)."""
	actual = _estado.reproductor
	descriptor = catalogo.evento(evento)
	if actual is None or descriptor is None:
		return False
	try:
		return bool(actual.sonar(descriptor, variante, False))
	except Exception:  # noqa: BLE001 - probar un sonido nunca rompe el diálogo
		log.warning("Falló la prueba del sonido %s", evento, exc_info=True)
		return False
