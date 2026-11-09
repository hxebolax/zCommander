# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ayudas comunes de las pruebas de los complementos del bloque P2 (documentos, OCR, hexadecimal, tablas y texto).

- ``anfitrion(nombre)``: ``api.pruebas.anfitrion_de_prueba`` con un gestor de
  tareas que entrega las respuestas en el acto (sin ``wx.CallAfter``).
- ``modulo(zc, nombre)``: un submódulo del complemento ya activado.
- ``InterfazFalsa``: lo que la ventana inyecta con ``api.fijar_interfaz``; su
  ``modulo_ui`` es ``app.ui.api_ui`` con los diálogos sustituidos por
  respuestas preparadas, para construir las ventanas y pasarles
  ``revisar_teclado`` sin mostrar nada.
- ``ejecutar_operacion(op)``: corre una operación del motor en este hilo.
"""

from __future__ import annotations

import importlib
import time
import types
from collections.abc import Sequence
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from app.core.tareas import GestorTareas, TokenCancelacion, ejecutor_directo
from app.plugins import api
from app.plugins.api import pruebas

RAIZ = Path(__file__).resolve().parents[2]


def carpeta(nombre: str) -> Path:
	return RAIZ / "plugins" / nombre


def anfitrion(nombre: str, config: dict | None = None) -> pruebas.AnfitrionFalso:
	zc = pruebas.anfitrion_de_prueba(carpeta(nombre))
	# La configuración de los complementos vive en un registro de la sesión: cada prueba empieza de fábrica.
	zc.config.restablecer()
	for clave, valor in (config or {}).items():
		zc.config.establecer(clave, valor)
	zc._tareas = GestorTareas(1, f"prueba-{nombre}", ejecutor_interfaz=ejecutor_directo)
	return zc


def modulo(zc: pruebas.AnfitrionFalso, nombre: str):
	"""Un submódulo del complemento ya activado (``zcplugins.<id>.<nombre>``)."""
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
	limite = time.monotonic() + segundos
	while zc.tareas.tareas_activas() and time.monotonic() < limite:
		time.sleep(0.02)


def ejecutar_operacion(operacion: Any, decisor: Any = None) -> Any:
	"""Ejecuta una ``api.Operacion`` en este hilo, como lo haría el motor."""
	contexto = api.ContextoEjecucion(TokenCancelacion(), decisor or pruebas.DecisorFalso())
	contexto.operacion = operacion
	operacion.contexto = contexto
	operacion.ejecutar(contexto)
	return operacion


class InterfazFalsa:
	"""``InterfazAnfitrion`` mínima: apunta lo que se le pide y responde a los diálogos con ``respuestas``."""

	def __init__(self, respuestas: dict[str, list[Any]] | None = None) -> None:
		from app.ui import api_ui

		self.respuestas = {k: list(v) for k, v in (respuestas or {}).items()}
		self.dialogos: list[tuple[str, str]] = []
		self.anuncios: list[str] = []
		self.rutas: list[str] = []
		self.ordenes: list[tuple[str, Any]] = []
		self.lanzadas: list[Any] = []
		self.ayudas: list[str] = []
		self.textos: list[tuple[str, str]] = []
		self.documentos: list[Any] = []
		self.dialogo_preferencias: dict[str, Any] = {}
		modulo_ui = types.SimpleNamespace(**{n: getattr(api_ui, n) for n in dir(api_ui) if not n.startswith("__")})
		for nombre in ("mostrar_mensaje", "mostrar_error", "confirmar", "elegir_opcion", "pedir_texto", "mostrar_modal",
				"mostrar_resultados"):
			setattr(modulo_ui, nombre, self._dialogo(nombre))
		modulo_ui.mostrar_texto = lambda titulo, texto, padre=None: self.textos.append((titulo, texto))
		modulo_ui.mostrar_documento = lambda documento, padre=None: self.documentos.append(documento)
		modulo_ui.movimiento_silencioso = lambda ventana: None
		self.modulo_ui = modulo_ui

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
		self.lanzadas.append(operacion)

	def abrir_ruta(self, texto: str, lado: str | None = None) -> None:
		self.rutas.append(texto)

	def abrir_ayuda(self, id_complemento: str, pagina: str = "") -> None:
		self.ayudas.append(id_complemento)

	def escribir_en_linea(self, texto: str) -> None:
		pass

	def registrar_deshacer(self, accion) -> None:
		pass

	def registrar_dialogo_complemento(self, id: str, funcion) -> None:
		self.dialogo_preferencias[id] = funcion

	def abrir_preferencias(self, id: str) -> None:
		self.ordenes.append(("preferencias", id))

	def panel(self, lado: str):
		return pruebas.PanelFalso(lado=lado)


def revisar(ventana: Any, teclas_propias: Sequence[str] = ()) -> None:
	"""``revisar_teclado`` sin problemas (los avisos no cuentan)."""
	from app.ui.accesibilidad.revision_teclado import informe, revisar_teclado

	problemas = [p for p in revisar_teclado(ventana, teclas_propias=teclas_propias) if not getattr(p, "aviso", False)]
	assert not problemas, informe(problemas)
