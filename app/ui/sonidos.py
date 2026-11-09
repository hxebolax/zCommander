# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Puesta en marcha de los sonidos (diseño 2.0, 4.3 y 4.4): crea el motor y lo inyecta en el servicio.

La ventana principal llama a ``iniciar(config)`` al construirse y a
``cerrar()`` al salir. El reproductor es el motor de 4.4
(``app.services.sonidos.motor.Motor``); el servicio solo filtra y le pasa
las peticiones. ``probar`` y ``probar_archivo`` son para la página Sonidos,
el mapa de sonidos y el asistente de paquetes: suenan aunque el evento o los
sonidos estén desactivados.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services.sonidos import catalogo, servicio
from app.services.sonidos.motor import Motor

log = logging.getLogger(__name__)


def iniciar(config: Any) -> None:
	"""Crea el motor de sonidos y lo inyecta en ``app.services.sonidos.servicio``."""
	servicio.iniciar(config, Motor(config))


def cerrar() -> None:
	"""Cierra el motor (al salir): vacía la cola y para el sonido en curso."""
	servicio.cerrar()


def motor() -> Motor | None:
	"""El motor activo, o ``None`` si los sonidos no están iniciados (pruebas, herramientas)."""
	actual = servicio.reproductor()
	return actual if isinstance(actual, Motor) else None


def asegurar_motor(config: Any) -> Motor:
	"""El motor activo; si el reproductor no es el motor (o no hay), lo pone (``instalar`` de SO, 14.9)."""
	actual = motor()
	if actual is not None:
		return actual
	nuevo = Motor(config)
	if servicio.reproductor() is None:
		servicio.iniciar(config, nuevo)
	else:
		servicio.fijar_reproductor(nuevo)
	return nuevo


def probar(id_evento: str, variante: str = "", *, paquete: str | None = None, volumen: int | None = None) -> bool:
	"""Hace sonar un evento con ese paquete y volumen aunque esté desactivado. Verdadero si sonó."""
	evento = catalogo.evento(id_evento)
	actual = motor()
	if evento is None:
		return False
	if actual is None:
		return servicio.probar(id_evento, variante)
	return actual.reproducir(evento, variante, paquete=paquete, volumen=volumen)


def probar_archivo(ruta: Path, *, volumen: int | None = None) -> bool:
	"""Hace sonar un WAV suelto (asistente de paquetes). Verdadero si sonó."""
	actual = motor()
	return bool(actual and actual.reproducir_archivo(Path(ruta), volumen=volumen))


def recargar() -> None:
	"""Vuelve a leer los paquetes instalados (tras crear, importar o eliminar uno)."""
	actual = servicio.reproductor()
	if actual is not None:
		try:
			actual.recargar()
		except Exception:  # noqa: BLE001 - un fallo al recargar deja los sonidos como estaban
			log.warning("El reproductor no pudo recargar", exc_info=True)
