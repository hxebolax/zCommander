# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque AC, actualizador de la aplicación (diseño 2.0, 5.4 y 14.9).

- ``buscar_actualizaciones``: Ayuda, «Buscar ac&tualizaciones...». Comprobación
  manual en un hilo; «Sin novedades» suena ``act.al_dia`` y se anuncia como resultado.
- ``instalar(ventana)``: el enganche de arranque del bloque (14.9). Engancha los
  avisos de ``actualizador.al_arrancar`` (paso 10 de 14.8) y arranca la
  comprobación periódica compartida, salvo en modo tarea (11.24).
"""

from __future__ import annotations

import logging
from typing import Any

from app.services import actualizador, eventos
from app.ui import dialogo_actualizacion

log = logging.getLogger(__name__)

#: Comprobador de la ventana en marcha (lo detiene ``al_cerrar``).
_comprobador: list[dialogo_actualizacion.ComprobadorPeriodico | None] = [None]


def _configuracion() -> actualizador.Configuracion:
	return actualizador.configuracion_por_defecto()


def buscar_actualizaciones(ctx) -> None:
	"""Comprueba si hay una versión nueva de zCommander y siempre dice el resultado."""
	dialogo_actualizacion.comprobar_manualmente(ctx.ventana, _configuracion())


def comprobador() -> dialogo_actualizacion.ComprobadorPeriodico | None:
	return _comprobador[0]


def instalar(ventana: Any) -> None:
	"""Avisos del arranque y comprobación periódica (14.9); nada más."""
	config = _configuracion()
	actualizador.fijar_oyente_arranque(lambda resultado: dialogo_actualizacion.atender_arranque(ventana, config, resultado))
	anterior = _comprobador[0]
	if anterior is not None:
		anterior.detener()
		_comprobador[0] = None
	modo = getattr(getattr(ventana, "arranque", None), "modo", "normal")
	if modo == "tarea":
		return
	nuevo = dialogo_actualizacion.ComprobadorPeriodico(ventana, config, ventana.config)
	_comprobador[0] = nuevo

	def al_cerrar() -> None:
		nuevo.detener()
		if _comprobador[0] is nuevo:
			_comprobador[0] = None
		actualizador.fijar_oyente_arranque(None)

	try:
		ventana.servicio("eventos").suscribir(eventos.AL_CERRAR, al_cerrar)
	except Exception:  # noqa: BLE001 - sin bus, la comprobación se detiene cuando la ventana ya no existe
		log.debug("No se pudo suscribir el actualizador al cierre", exc_info=True)
	nuevo.iniciar()
