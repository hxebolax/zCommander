# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Interfaz del complemento NAS Synology (diseño 2.0, 13.4). Solo se importa con la ventana de zCommander.

Los controles accesibles (``ListaAccesible``, ``VentanaComplemento``, diálogos
en español con Ctrl+H) llegan por ``api.interfaz().modulo_ui``, la misma vía
que ``zc.ui``: el complemento no importa nada de ``app`` salvo la API.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from app.plugins import api

_, _n = api.traduccion("zc_synology")


def modulo_ui() -> Any:
	interfaz = api.interfaz()
	if interfaz is None:
		raise api.NoAdmitido(_("Esta función necesita la ventana de zCommander"))
	return interfaz.modulo_ui


def en_interfaz(funcion: Callable[[], Any], espera_maxima: float | None = None) -> Any:
	"""Ejecuta ``funcion`` en el hilo de la interfaz y espera su resultado (desde un hilo de trabajo).

	En el propio hilo de la interfaz se llama en el acto. Es lo que hace el
	``Decisor`` de zCommander: el hilo de trabajo espera; la interfaz, nunca.
	"""
	if threading.current_thread() is threading.main_thread():
		return funcion()
	interfaz = api.interfaz()
	if interfaz is None:
		raise api.NoAdmitido(_("Esta función necesita la ventana de zCommander"))
	resultado: dict[str, Any] = {}
	listo = threading.Event()

	def correr() -> None:
		try:
			resultado["valor"] = funcion()
		except BaseException as error:  # noqa: BLE001 - se vuelve a lanzar en el hilo que esperaba
			resultado["error"] = error
		finally:
			listo.set()

	interfaz.planificar(correr)
	if not listo.wait(espera_maxima):
		raise api.Cancelado(_("La pregunta no ha recibido respuesta"))
	if "error" in resultado:
		raise resultado["error"]
	return resultado.get("valor")


def poner_letra(etiqueta: str, usadas: set[str]) -> str:
	"""Añade «&» en la primera letra libre (prefiriendo el comienzo de palabra) y la anota en ``usadas``.

	Así los botones de acciones, que cambian con cada área, nunca repiten letra
	con los controles fijos de la ventana ni entre sí (``revisar_teclado``).
	"""
	limpia = etiqueta.replace("&", "")
	candidatas = [i for i, c in enumerate(limpia) if c.isalnum() and (i == 0 or not limpia[i - 1].isalnum())]
	candidatas += [i for i, c in enumerate(limpia) if c.isalnum() and i not in candidatas]
	for indice in candidatas:
		letra = limpia[indice].casefold()
		if letra in usadas or letra not in "abcdefghijklmnopqrstuvwxyzñ0123456789":
			continue
		usadas.add(letra)
		return limpia[:indice] + "&" + limpia[indice:]
	return limpia
