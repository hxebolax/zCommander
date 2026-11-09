# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Prueba de un complemento desde la compilación (``--comprobar-arranque --complemento-prueba``, diseño 2.0, 14.8). Sin wx.

Bloque PL. ``main.py`` la llama con la ventana ya construida (sin mostrar) y
antes de que corra el bucle de eventos. Pasos:

1. Leer el manifiesto de ``carpeta`` y registrar sus marcadores como un
   complemento en desarrollo (la carpeta la nombra quien lanza la prueba).
2. Activarlo en este mismo hilo (``Cargador.activar_ahora``): el bucle de
   eventos aún no atiende ``wx.CallAfter``.
3. Ejecutar la orden de su campo ``prueba`` (por defecto, la primera de
   ``[[ordenes]]``) sin argumento y sin preguntar nada, con los paneles de la
   ventana.

Devuelve 0 si todo fue bien y 1 si algo falló (el motivo queda en el registro).
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.plugins import api, cargador, manifiesto, registro

log = logging.getLogger(__name__)


def comprobar_complemento(carpeta: Path) -> int:
	"""0 si el complemento de ``carpeta`` se carga y su orden de prueba se ejecuta sin fallar."""
	carpeta = Path(carpeta)
	try:
		datos = manifiesto.leer(carpeta)
	except manifiesto.ErrorManifiesto as error:
		log.error("Prueba del complemento %s: manifiesto no válido: %s", carpeta, "; ".join(error.problemas))
		return 1
	actual = cargador.actual()
	if actual is None:
		actual = cargador.Cargador(None)
		cargador.fijar_actual(actual)
	if registro.complemento(datos.id) is None or registro.complemento(datos.id).carpeta != carpeta:
		actual._registrar(carpeta, datos, "desarrollo", set())
	if not actual.activar_ahora(datos.id):
		registrado = registro.complemento(datos.id)
		log.error("Prueba del complemento %s: no se pudo activar (%s)", datos.id, registrado.motivo if registrado else "")
		return 1
	orden = datos.orden_prueba
	if not orden:
		log.info("Prueba del complemento %s: activado; no tiene órdenes que probar", datos.id)
		return 0
	contexto = _contexto(f"{datos.id}:{orden}")
	if not api.ejecutar_manejador(f"{datos.id}:{orden}", contexto):
		log.error("Prueba del complemento %s: la orden %s falló o no tiene manejador", datos.id, orden)
		return 1
	log.info("Prueba del complemento %s: la orden %s se ejecutó bien", datos.id, orden)
	return 0


def _contexto(id_orden: str) -> api.ContextoComplemento:
	interfaz = api.interfaz()
	if interfaz is not None:
		try:
			return api.ContextoComplemento(orden=id_orden, activo=interfaz.panel("activo"), pasivo=interfaz.panel("pasivo"))
		except Exception:  # noqa: BLE001 - sin paneles reales se prueba con paneles vacíos
			log.debug("Sin paneles de la ventana para la prueba", exc_info=True)
	from app.plugins.api_pruebas import PanelFalso

	return api.ContextoComplemento(orden=id_orden, activo=PanelFalso(), pasivo=PanelFalso(lado="derecho"))
