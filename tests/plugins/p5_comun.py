# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ayudas comunes de las pruebas del bloque P5 (complementos de automatización)."""

from __future__ import annotations

import importlib
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from app.plugins import api, config_plugins, manifiesto
from app.plugins.api import pruebas

RAIZ = Path(__file__).resolve().parents[2]
PLUGINS = RAIZ / "plugins"


def carpeta(nombre: str) -> Path:
	return PLUGINS / nombre


def anfitrion(nombre: str, config: dict | None = None, permisos=()) -> pruebas.AnfitrionFalso:
	"""Anfitrión de prueba ya activado, con la configuración del complemento en la ``data`` temporal de la prueba.

	``config_plugins`` guarda abierta la configuración de cada complemento; se
	vuelve a declarar para que no quede apuntando a la carpeta de otra prueba.
	"""
	datos = manifiesto.leer(carpeta(nombre))
	config_plugins.registro().declarar(datos.id, datos.tabla("configuracion"))
	zc = pruebas.anfitrion_de_prueba(carpeta(nombre), config=config, permisos=permisos)
	zc.activar()
	return zc


def modulo(nombre: str, submodulo: str) -> Any:
	"""Un submódulo del complemento ya importado como ``zcplugins.<id codificado>``."""
	datos = manifiesto.leer(carpeta(nombre))
	return importlib.import_module(f"zcplugins.{datos.codificado}.{submodulo}")


class InterfazFalsa:
	"""``InterfazAnfitrion`` mínima: ``zc.ui`` delega en el ``app.ui.api_ui`` real; lo demás se apunta."""

	def __init__(self) -> None:
		from app.ui import api_ui

		self.modulo_ui = api_ui
		self.anuncios: list[tuple[str, str]] = []
		self.rutas: list[str] = []
		self.ordenes: list[tuple[str, Any]] = []
		self.lanzadas: list[Any] = []
		self.deshacer: list[Any] = []
		self.resultado_orden = True

	def planificar(self, funcion) -> None:
		funcion()

	def en_hilo_interfaz(self) -> bool:
		return True

	def anunciar(self, texto, nivel, completo="", interrumpir=None, sonido="") -> None:
		self.anuncios.append((texto, nivel))

	def ejecutar_orden(self, id_orden, lado=None, *, argumento=None) -> None:
		self.ordenes.append((id_orden, argumento))

	def ejecutar_orden_futuro(self, id_orden, lado=None, *, argumento=None) -> Future:
		self.ordenes.append((id_orden, argumento))
		futuro: Future = Future()
		futuro.set_result(self.resultado_orden)
		return futuro

	def lanzar(self, operacion, en_cola, al_terminar, *, orden_origen) -> None:
		self.lanzadas.append((operacion, al_terminar))

	def abrir_ruta(self, texto, lado=None) -> None:
		self.rutas.append(texto)

	def abrir_ayuda(self, id_complemento, pagina="") -> None:
		pass

	def escribir_en_linea(self, texto) -> None:
		pass

	def registrar_deshacer(self, accion) -> None:
		self.deshacer.append(accion)

	def registrar_dialogo_complemento(self, id, funcion) -> None:
		pass

	def abrir_preferencias(self, id) -> None:
		pass

	def panel(self, lado) -> Any:
		return pruebas.PanelFalso(lado=lado)


def con_interfaz() -> InterfazFalsa:
	interfaz = InterfazFalsa()
	api.fijar_interfaz(interfaz)
	return interfaz


def problemas_de_teclado(ventana) -> list:
	from app.ui.accesibilidad.revision_teclado import revisar_teclado

	return [p for p in revisar_teclado(ventana) if not getattr(p, "aviso", False)]
