# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ayudas comunes de las pruebas de los complementos del bloque P4 (procesos, cifrado, portapapeles, seguridad y Git).

- ``anfitrion(carpeta)``: ``api.pruebas.anfitrion_de_prueba`` con un gestor de
  tareas que entrega las respuestas en el acto (sin ``wx.CallAfter``).
- ``InterfazFalsa``: lo que la ventana inyecta con ``api.fijar_interfaz``; su
  ``modulo_ui`` es ``app.ui.api_ui`` con los diálogos sustituidos por
  respuestas preparadas, para construir las ventanas de los complementos y
  pasarles ``revisar_teclado`` sin mostrar nada.
"""

from __future__ import annotations

import types
from collections.abc import Sequence
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from app.core.tareas import GestorTareas, ejecutor_directo
from app.plugins import api
from app.plugins.api import pruebas

RAIZ = Path(__file__).resolve().parents[2]


def carpeta(nombre: str) -> Path:
	return RAIZ / "plugins" / nombre


def anfitrion(nombre: str, config: dict | None = None) -> pruebas.AnfitrionFalso:
	zc = pruebas.anfitrion_de_prueba(carpeta(nombre), config=config)
	zc._tareas = GestorTareas(1, f"prueba-{nombre}", ejecutor_interfaz=ejecutor_directo)
	return zc


def modulo(zc: pruebas.AnfitrionFalso, nombre: str):
	"""Un submódulo del complemento ya activado (``zcplugins.<id>.<nombre>``)."""
	import importlib

	zc.activar()
	return importlib.import_module(f"{type(zc.instancia).__module__}.{nombre}")


def entrada(ruta: Path | str, carpeta_: bool = False) -> api.Entrada:
	ruta = Path(ruta)
	return api.Entrada(ruta.name, str(ruta), es_carpeta=carpeta_ or ruta.is_dir(),
		tamano=ruta.stat().st_size if ruta.is_file() else -1)


def panel(rutas: Sequence[Path | str], ruta: str = "", marcadas: Sequence[str] = ()) -> pruebas.PanelFalso:
	entradas = [entrada(r) for r in rutas]
	return pruebas.PanelFalso(entradas, ruta=ruta or (str(Path(rutas[0]).parent) if rutas else ""), marcadas=marcadas)


def esperar_tareas(zc: pruebas.AnfitrionFalso, segundos: float = 30.0) -> None:
	"""Espera a que el gestor de tareas del anfitrión no tenga nada en curso."""
	import time

	limite = time.monotonic() + segundos
	while zc.tareas.tareas_activas() and time.monotonic() < limite:
		time.sleep(0.02)


class InterfazFalsa:
	"""``InterfazAnfitrion`` mínima: apunta lo que se le pide y responde a los diálogos con ``respuestas``."""

	def __init__(self, respuestas: dict[str, list[Any]] | None = None) -> None:
		from app.ui import api_ui

		self.respuestas = {k: list(v) for k, v in (respuestas or {}).items()}
		self.dialogos: list[tuple[str, str]] = []
		self.anuncios: list[str] = []
		self.rutas: list[str] = []
		self.lineas: list[str] = []
		self.ordenes: list[tuple[str, Any]] = []
		self.ayudas: list[str] = []
		self.dialogo_preferencias: dict[str, Any] = {}
		modulo = types.SimpleNamespace(**{n: getattr(api_ui, n) for n in dir(api_ui) if not n.startswith("__")})
		for nombre in ("mostrar_mensaje", "mostrar_error", "confirmar", "elegir_opcion", "pedir_texto", "mostrar_texto",
				"mostrar_modal", "mostrar_documento", "mostrar_resultados"):
			setattr(modulo, nombre, self._dialogo(nombre))
		self.modulo_ui = modulo

	def _dialogo(self, nombre: str):
		def responder(*args: Any, **kwargs: Any) -> Any:
			texto = args[0] if args and isinstance(args[0], str) else getattr(args[0], "GetTitle", lambda: "")() if args else ""
			self.dialogos.append((nombre, str(texto)))
			pendientes = self.respuestas.get(nombre, [])
			if pendientes:
				valor = pendientes.pop(0)
				return valor(*args, **kwargs) if callable(valor) else valor
			return {"confirmar": False, "mostrar_modal": 0}.get(nombre)

		return responder

	def planificar(self, funcion) -> None:
		funcion()

	def en_hilo_interfaz(self) -> bool:
		return True

	def anunciar(self, texto: str, nivel: str, completo: str = "", interrumpir: bool | None = None, sonido: str = "") -> None:
		self.anuncios.append(texto)

	def ejecutar_orden(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None:
		self.ordenes.append((id_orden, argumento))

	def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> Future:
		self.ordenes.append((id_orden, argumento))
		futuro: Future = Future()
		futuro.set_result(True)
		return futuro

	def lanzar(self, operacion, en_cola, al_terminar, *, orden_origen: str) -> None:
		self.ordenes.append(("lanzar", operacion))

	def abrir_ruta(self, texto: str, lado: str | None = None) -> None:
		self.rutas.append(texto)

	def abrir_ayuda(self, id_complemento: str, pagina: str = "") -> None:
		self.ayudas.append(id_complemento)

	def escribir_en_linea(self, texto: str) -> None:
		self.lineas.append(texto)

	def registrar_deshacer(self, accion) -> None:
		pass

	def registrar_dialogo_complemento(self, id: str, funcion) -> None:
		self.dialogo_preferencias[id] = funcion

	def abrir_preferencias(self, id: str) -> None:
		self.ordenes.append(("preferencias", id))

	def panel(self, lado: str):
		return pruebas.PanelFalso(lado=lado)
