# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Avisos de «vuelve a leer tu archivo» tras restaurar una copia (diseño 2.0, 7.6 y 14.4). Sin wx.

Contrato ``recargar()``: cada servicio que guarda un archivo de una parte de copia
«En el momento» tiene ``recargar() -> None``, que vuelve a leer su archivo y avisa a
su interfaz. Los servicios de la 1.x (favoritos, menú de usuario, asociaciones,
plantillas de renombrado y búsquedas guardadas) leen su archivo en cada uso, así que
su ``recargar`` solo avisa a quien muestre sus datos (``al_recargar``).

``suscribir_restauracion`` engancha esas funciones al evento ``al_restaurar`` del bus
para la parte ``personalizacion``; lo llama la ventana al construirse.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

#: Servicios de la 1.x con datos de la parte «personalizacion» (14.4); los suscribe N2.
SERVICIOS_1X = ("app.services.favoritos", "app.services.menu_usuario", "app.services.asociaciones",
	"app.services.renombrado", "app.services.busqueda")
PARTE = "personalizacion"

_oyentes: dict[str, list[Callable[[], None]]] = {}


def al_recargar(servicio: str, funcion: Callable[[], None]) -> Callable[[], None]:
	"""``funcion()`` cuando ``servicio`` (nombre del módulo) vuelve a leer su archivo; devuelve la que cancela."""
	_oyentes.setdefault(servicio, []).append(funcion)
	return lambda: _oyentes.get(servicio, []).remove(funcion) if funcion in _oyentes.get(servicio, []) else None


def avisar(servicio: str) -> None:
	for funcion in list(_oyentes.get(servicio, [])):
		try:
			funcion()
		except Exception:  # noqa: BLE001 - una interfaz rota no impide avisar a las demás
			log.exception("Falló un aviso de recarga de %s", servicio)


def suscribir_restauracion(bus) -> list[Callable[[], None]]:
	"""Suscribe el ``recargar()`` de los servicios de la 1.x a ``al_restaurar`` (parte ``personalizacion``)."""
	cancelaciones = []
	for nombre in SERVICIOS_1X:
		modulo = importlib.import_module(nombre)

		def al_restaurar(partes=(), modulo=modulo, **_datos) -> None:
			if PARTE in (partes or ()):
				modulo.recargar()

		cancelaciones.append(bus.suscribir("al_restaurar", al_restaurar))
	return cancelaciones
