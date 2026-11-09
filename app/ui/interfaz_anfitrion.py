# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Implementación de ``InterfazAnfitrion`` sobre la ventana principal (diseño 2.0, 3.7).

Es lo único por lo que la API de complementos (``app/plugins/api.py``, sin wx)
llega a la interfaz: la ventana crea un ``InterfazVentana(self)`` al
construirse y lo pasa a ``api.fijar_interfaz``; al cerrar, ``fijar_interfaz(None)``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import wx

from app.plugins import api
from app.ui import anuncios

log = logging.getLogger(__name__)


class InterfazVentana:
	"""``InterfazAnfitrion`` de la ventana principal."""

	def __init__(self, ventana: Any) -> None:
		from app.ui import api_ui

		self._ventana = ventana
		self.modulo_ui = api_ui

	def planificar(self, funcion: Callable[[], None]) -> None:
		wx.CallAfter(funcion)

	def en_hilo_interfaz(self) -> bool:
		return threading.current_thread() is threading.main_thread()

	def anunciar(self, texto: str, nivel: str, completo: str = "", interrumpir: bool | None = None, sonido: str = "") -> None:
		anuncios.anunciar(texto, nivel, completo, interrumpir, sonido=sonido)

	def ejecutar_orden(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None:
		self._ventana.ejecutar_orden(id_orden, lado, argumento=argumento)

	def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> Future[bool]:
		return self._ventana.ejecutar_orden_futuro(id_orden, lado, argumento=argumento)

	def lanzar(self, operacion: Any, en_cola: bool, al_terminar: Callable[[Any], None] | None, *, orden_origen: str) -> None:
		self._ventana.lanzar_operacion(operacion, en_cola, al_terminar, orden_origen=orden_origen)

	def abrir_ruta(self, texto: str, lado: str | None = None) -> None:
		ventana = self._ventana
		panel = ventana.lado(lado).panel_actual() if lado in ("izquierdo", "derecho") else ventana.activo
		panel.ir_a_texto(texto)

	def abrir_ayuda(self, id_complemento: str, pagina: str = "") -> None:
		from app.plugins import registro

		registrado = registro.complemento(id_complemento)
		if registrado is None:
			return
		# 2.0 (3.7): ``abrir_ayuda(pagina)`` abre ``doc/es/<pagina>.md`` si existe.
		ruta = ruta_ayuda(registrado, pagina)
		if not ruta.is_file():
			anuncios.anunciar(api._("El complemento {n} no tiene ayuda").format(n=registrado.nombre), anuncios.RESULTADO)
			return
		from app.ui import visor_ayuda

		visor_ayuda.mostrar_documento(self._ventana, registrado.nombre, ruta.read_text(encoding="utf-8"))

	def escribir_en_linea(self, texto: str) -> None:
		self._ventana.escribir_en_linea(texto)

	def registrar_deshacer(self, accion: Any) -> None:
		self._ventana.servicio("deshacer").registrar(accion)

	def registrar_dialogo_complemento(self, id: str, funcion: Callable[[Any], None]) -> None:
		from app.ui import paginas_propias

		paginas_propias.registrar_dialogo_complemento(id, funcion)

	def abrir_preferencias(self, id: str) -> None:
		from app.ui import paginas_propias

		paginas_propias.abrir_preferencias(id, self._ventana, self._ventana.config)

	def panel(self, lado: str) -> Any:
		ventana = self._ventana
		if lado == "activo":
			real = ventana.activo
		elif lado == "pasivo":
			real = ventana.pasivo
		else:
			real = ventana.lado(lado).panel_actual()
		return api.PanelVista(real)


def ruta_ayuda(registrado: Any, pagina: str = "") -> Path:
	"""Archivo de ayuda de un complemento: ``doc/es/<pagina>.md`` si existe; si no, el de ``ayuda`` del manifiesto.

	La página puede venir sin extensión («google-drive») o con ella («google-drive.md»),
	y se busca junto al archivo de ayuda principal. Nunca sale de la carpeta del complemento.
	"""
	principal = registrado.carpeta / str(registrado.manifiesto.datos.get("ayuda", "doc/es/leeme.md"))
	pagina = str(pagina or "").strip()
	if pagina:
		nombre = pagina if pagina.lower().endswith((".md", ".txt")) else f"{pagina}.md"
		candidata = (principal.parent / nombre).resolve()
		try:
			candidata.relative_to(Path(registrado.carpeta).resolve())
		except ValueError:
			log.warning("Página de ayuda fuera del complemento %s: %s", registrado.id, pagina)
			return principal
		if candidata.is_file():
			return candidata
		log.info("El complemento %s no tiene la página de ayuda %s; se abre la principal", registrado.id, pagina)
	return principal


class InterfazSinVentana:
	"""``InterfazAnfitrion`` mínima sin la ventana principal (``tools/validar_plugin.py`` y pruebas).

	Basta para que un complemento construya sus ventanas con ``zc.ui`` (los
	controles accesibles reales de ``app.ui.api_ui``) en ``ventanas_para_revisar``.
	``planificar`` llama en el acto (no hay bucle de eventos), los anuncios se
	guardan en ``anuncios`` y lo que necesita la ventana principal solo se registra.
	"""

	def __init__(self) -> None:
		from app.ui import api_ui

		self.modulo_ui = api_ui
		self.anuncios: list[str] = []
		self.ordenes: list[str] = []

	def planificar(self, funcion: Callable[[], None]) -> None:
		funcion()

	def en_hilo_interfaz(self) -> bool:
		return threading.current_thread() is threading.main_thread()

	def anunciar(self, texto: str, nivel: str, completo: str = "", interrumpir: bool | None = None, sonido: str = "") -> None:
		self.anuncios.append(texto)
		log.info("Anuncio sin ventana: %s", texto)

	def ejecutar_orden(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None:
		self.ordenes.append(id_orden)
		log.info("Orden sin ventana (no se ejecuta): %s", id_orden)

	def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> Future[bool]:
		self.ejecutar_orden(id_orden, lado, argumento=argumento)
		futuro: Future[bool] = Future()
		futuro.set_result(False)
		return futuro

	def lanzar(self, operacion: Any, en_cola: bool, al_terminar: Callable[[Any], None] | None, *, orden_origen: str) -> None:
		log.info("Operación sin ventana (no se lanza): %s", type(operacion).__name__)

	def abrir_ruta(self, texto: str, lado: str | None = None) -> None:
		log.info("Ruta sin ventana (no se abre): %s", texto)

	def abrir_ayuda(self, id_complemento: str, pagina: str = "") -> None:
		log.info("Ayuda sin ventana (no se abre): %s %s", id_complemento, pagina)

	def escribir_en_linea(self, texto: str) -> None:
		log.info("Línea de órdenes sin ventana: %s", texto)

	def registrar_deshacer(self, accion: Any) -> None:
		log.info("Deshacer sin ventana (no se guarda): %s", getattr(accion, "descripcion", ""))

	def registrar_dialogo_complemento(self, id: str, funcion: Callable[[Any], None]) -> None:
		from app.ui import paginas_propias

		paginas_propias.registrar_dialogo_complemento(id, funcion)

	def abrir_preferencias(self, id: str) -> None:
		log.info("Preferencias sin ventana (no se abren): %s", id)

	def panel(self, lado: str) -> Any:
		raise api.NoAdmitido(api._("Esta función necesita la ventana de zCommander"))
