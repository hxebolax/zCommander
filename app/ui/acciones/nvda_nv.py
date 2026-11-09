# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes y enganche de arranque del bloque NV: complemento de zCommander para NVDA (diseño 2.0, 10.16).

- ``complemento_nvda`` (menú Ayuda): explica qué hace el complemento y, si la
  persona acepta, abre el ``.nvda-addon`` para que NVDA lo instale
  (``app/ui/instalar_complemento.py``; NVDA pide su propia confirmación).
- ``instalar(ventana)`` (14.9): si NVDA está activo y el complemento no está
  instalado, lo ofrece **una sola vez** (``accesibilidad.complemento_nvda_ofrecido``),
  cuando la ventana ya se ve, está activa y no hay ningún diálogo modal abierto
  (por ejemplo, después del asistente del primer arranque). Así cubre el primer
  arranque y la primera vez tras actualizar a la 2.0.
"""

from __future__ import annotations

import logging

import wx

from app.core import paths
from app.ui import instalar_complemento

log = logging.getLogger(__name__)

#: Espera antes del primer intento: el asistente del primer arranque sale a los 600 ms.
RETRASO_INICIAL_MS = 3000
#: Cada cuánto se vuelve a mirar si es buen momento para preguntar.
ESPERA_MS = 2000
#: Intentos como mucho (unos 30 minutos): si la ventana sigue oculta, se deja para otro arranque.
MAX_INTENTOS = 900


def complemento_nvda(ctx) -> None:
	"""Instalar el complemento de zCommander para NVDA..."""
	instalar_complemento.abrir(ctx.ventana)


def instalar(ventana) -> None:
	"""Enganche de arranque (14.9): prepara el ofrecimiento único del complemento de NVDA."""
	config = getattr(ventana, "config", None)
	if config is None or config.obtener(instalar_complemento.CLAVE_OFRECIDO):
		return
	wx.CallLater(RETRASO_INICIAL_MS, _intentar, ventana, 0, None)


def _hay_modal_abierto() -> bool:
	return any(isinstance(v, wx.Dialog) and v.IsShown() and v.IsModal() for v in wx.GetTopLevelWindows())


def momento_adecuado(ventana) -> bool:
	"""La ventana se ve, no está minimizada, está activa y no hay otro diálogo modal (asistente...)."""
	return bool(ventana.IsShown() and not ventana.IsIconized() and ventana.IsActive() and not _hay_modal_abierto())


def _intentar(ventana, intentos: int, procede: bool | None) -> None:
	"""Un intento del ofrecimiento; se reprograma mientras no sea buen momento.

	``procede`` guarda la comprobación de NVDA (proceso y complemento
	instalado), que se hace una sola vez, en el primer intento.
	"""
	try:
		if not ventana:  # destruida
			return
		config = ventana.config
		if procede is None:
			procede = instalar_complemento.debe_ofrecerse(config)
		if not procede or config.obtener(instalar_complemento.CLAVE_OFRECIDO):
			return
		if not momento_adecuado(ventana):
			if intentos < MAX_INTENTOS:
				wx.CallLater(ESPERA_MS, _intentar, ventana, intentos + 1, procede)
			return
		# Se apunta antes de preguntar: pase lo que pase, solo se ofrece una vez.
		config.establecer(instalar_complemento.CLAVE_OFRECIDO, True)
		instalar_complemento.ofrecer_instalacion(
			ventana, construir=None if paths.CONGELADA else instalar_complemento.construir_desde_fuente, al_arrancar=True
		)
	except Exception:  # noqa: BLE001 - un fallo aquí nunca impide usar zCommander
		log.exception("No se pudo ofrecer el complemento de NVDA al arrancar")
