# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ayudas comunes de las pruebas del bloque P3 (duplicados, ocupación, notas, papelera y organizador).

Cada prueba trabaja con su ``data`` temporal (``conftest.datos_temporales``): la
configuración del complemento se vuelve a abrir allí, el bus de eventos es
nuevo y las tareas del complemento devuelven sus respuestas en el mismo hilo.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

from app.core.tareas import GestorTareas, ejecutor_directo
from app.plugins import api, config_plugins, manifiesto
from app.plugins.api import pruebas
from app.services import eventos

RAIZ = Path(__file__).resolve().parents[2]
PLUGINS = RAIZ / "plugins"
CARPETAS = ("duplicados", "ocupacion", "notas", "papelera", "organizador")


def preparar(carpeta: str, config: dict | None = None) -> tuple[pruebas.AnfitrionFalso, ModuleType]:
	"""Activa el complemento de ``plugins/<carpeta>`` con un anfitrión de prueba; devuelve (zc, paquete)."""
	ruta = PLUGINS / carpeta
	datos = manifiesto.leer(ruta)
	config_plugins.registro().declarar(datos.id, datos.tabla("configuracion"))
	eventos.reiniciar()
	zc = pruebas.anfitrion_de_prueba(ruta, config=config)
	zc._tareas = GestorTareas(max_hilos=2, nombre=f"prueba-{carpeta}", ejecutor_interfaz=ejecutor_directo)
	zc.activar()
	return zc, sys.modules[type(zc.instancia).__module__]


def modulo(paquete: ModuleType, nombre: str) -> ModuleType:
	return importlib.import_module(f"{paquete.__name__}.{nombre}")


def esperar(condicion, segundos: float = 5.0) -> bool:
	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		if condicion():
			return True
		time.sleep(0.02)
	return condicion()


def contexto_operacion(decisor: Any = None, cancelado: bool = False) -> api.ContextoEjecucion:
	evento = threading.Event()
	if cancelado:
		evento.set()
	return api.ContextoEjecucion(evento, decisor or pruebas.DecisorFalso())


class InterfazFalsa:
	"""``InterfazAnfitrion`` mínima para construir las ventanas con los controles reales de ``app.ui.api_ui``."""

	def __init__(self) -> None:
		from app.ui import api_ui

		self.modulo_ui = api_ui
		self.anuncios: list[str] = []
		self.rutas: list[tuple[str, str | None]] = []

	def planificar(self, funcion) -> None:
		funcion()

	def en_hilo_interfaz(self) -> bool:
		return threading.current_thread() is threading.main_thread()

	def anunciar(self, texto: str, nivel: str, completo: str = "", interrumpir: bool | None = None, sonido: str = "") -> None:
		self.anuncios.append(texto)

	def abrir_ruta(self, texto: str, lado: str | None = None) -> None:
		self.rutas.append((texto, lado))

	def abrir_ayuda(self, id_complemento: str, pagina: str = "") -> None:
		pass
