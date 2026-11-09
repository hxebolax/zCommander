# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lo que la API de complementos recibe de la interfaz (diseño 2.0, 3.7). Sin wx.

``api.py`` no importa wx ni ``app.ui``: todo lo de la interfaz llega por una
sola inyección, ``api.fijar_interfaz(interfaz)``, con un objeto que cumple este
protocolo. Lo implementa ``app/ui/interfaz_anfitrion.py`` sobre la ventana
principal. Las anotaciones con tipos de wx van entre comillas.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from types import ModuleType
from typing import Any, Protocol


class InterfazAnfitrion(Protocol):
	modulo_ui: ModuleType  # app.ui.api_ui, en el que delega ModuloUI

	def planificar(self, funcion: Callable[[], None]) -> None: ...  # [cualquiera] wx.CallAfter
	def en_hilo_interfaz(self) -> bool: ...  # [cualquiera]
	def anunciar(self, texto: str, nivel: str, completo: str = "", interrumpir: bool | None = None,
			sonido: str = "") -> None: ...  # [interfaz]
	def ejecutar_orden(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None: ...
	def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> Future[bool]: ...
	def lanzar(self, operacion: Any, en_cola: bool, al_terminar: Callable[[Any], None] | None,
			*, orden_origen: str) -> None: ...
	def abrir_ruta(self, texto: str, lado: str | None = None) -> None: ...
	def abrir_ayuda(self, id_complemento: str, pagina: str = "") -> None: ...
	def escribir_en_linea(self, texto: str) -> None: ...
	def registrar_deshacer(self, accion: Any) -> None: ...
	def registrar_dialogo_complemento(self, id: str, funcion: Callable[[Any], None]) -> None: ...
	def abrir_preferencias(self, id: str) -> None: ...
	def panel(self, lado: str) -> Any: ...  # «izquierdo», «derecho», «activo» o «pasivo» → PanelComplemento
