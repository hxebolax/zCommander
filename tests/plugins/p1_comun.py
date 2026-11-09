# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ayudas comunes de las pruebas del bloque P1 (complementos multimedia).

- ``cargar(carpeta)``: anfitrión de prueba activado y el paquete del complemento
  (``zcplugins.zc__<id>``) ya importado, para probar sus módulos.
- ``InterfazPrueba``: un ``InterfazAnfitrion`` mínimo cuyo ``modulo_ui`` es el
  real (``app.ui.api_ui``) o uno falso; así ``zc.ui`` construye las ventanas
  de verdad para ``revisar_teclado`` sin la ventana principal.
- ``config_limpia``: cada prueba empieza con la configuración de fábrica de los
  complementos de P1 (el registro de configuraciones guarda las abiertas).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CARPETAS = ("reproductor", "metadatos", "ffmpeg", "imagenes", "voz")
IDS = tuple(f"zc.{c}" for c in CARPETAS)


def carpeta(nombre: str) -> Path:
	return RAIZ / "plugins" / nombre


def cargar(nombre: str, config: dict | None = None) -> tuple[Any, Any]:
	from app.plugins.api import pruebas

	zc = pruebas.anfitrion_de_prueba(carpeta(nombre), config=config)
	zc.activar()
	return zc, importlib.import_module(f"zcplugins.zc__{nombre}")


def modulo(nombre: str, submodulo: str) -> Any:
	return importlib.import_module(f"zcplugins.zc__{nombre}.{submodulo}")


class InterfazPrueba:
	def __init__(self, modulo_ui: Any) -> None:
		self.modulo_ui = modulo_ui
		self.anuncios: list[str] = []
		self.dialogos: dict[str, Any] = {}
		self.preferencias: list[str] = []
		self.operaciones: list[Any] = []

	def planificar(self, funcion: Any) -> None:
		funcion()

	def en_hilo_interfaz(self) -> bool:
		return True

	def anunciar(self, texto: str, nivel: str, completo: str = "", interrumpir: bool | None = None, sonido: str = "") -> None:
		self.anuncios.append(texto)

	def lanzar(self, operacion: Any, en_cola: bool, al_terminar: Any, *, orden_origen: str) -> None:
		self.operaciones.append(operacion)

	def registrar_dialogo_complemento(self, id: str, funcion: Any) -> None:
		self.dialogos[id] = funcion

	def abrir_preferencias(self, id: str) -> None:
		self.preferencias.append(id)

	def abrir_ayuda(self, id_complemento: str, pagina: str = "") -> None:
		return None


@pytest.fixture(autouse=True)
def config_limpia():
	from app.plugins import config_plugins

	registro = config_plugins.registro()
	for id_complemento in IDS:
		registro.declarar(id_complemento, registro.declaraciones(id_complemento))
	yield
	for id_complemento in IDS:
		registro.declarar(id_complemento, registro.declaraciones(id_complemento))


@pytest.fixture
def interfaz_real(app_wx):
	"""``zc.ui`` con el ``app.ui.api_ui`` de verdad (ventanas reales, sin mostrarlas)."""
	from app.plugins import api
	from app.ui import api_ui

	interfaz = InterfazPrueba(api_ui)
	api.fijar_interfaz(interfaz)
	yield interfaz
	api.fijar_interfaz(None)


def revisar(ventanas: list[Any], teclas_propias: tuple[str, ...] = ()) -> None:
	"""``revisar_teclado`` sin errores en cada ventana; las destruye al terminar."""
	from app.ui.accesibilidad.revision_teclado import informe, revisar_teclado

	try:
		for ventana in ventanas:
			problemas = [p for p in revisar_teclado(ventana, teclas_propias) if not p.aviso]
			assert not problemas, f"{ventana.GetTitle()}:\n{informe(problemas)}"
	finally:
		for ventana in ventanas:
			ventana.Destroy()


def entrada(ruta: Path) -> Any:
	from app.plugins import api

	estado = ruta.stat()
	return api.Entrada(ruta.name, str(ruta), tamano=estado.st_size, modificado=estado.st_mtime)
