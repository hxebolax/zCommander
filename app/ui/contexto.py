# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Contrato entre la ventana principal y los manejadores de órdenes.

Cada orden del catálogo (``app/ui/ordenes.py``) tiene un manejador
``def funcion(ctx: ContextoOrden) -> None`` en ``app/ui/acciones/<modulo>.py``.
Los manejadores se ejecutan SIEMPRE en el hilo de la interfaz. Lo lento lo
mandan a ``ctx.tareas`` o a ``ctx.operaciones``.

``PanelProtocolo`` describe lo que un manejador puede pedir a un panel. La
implementación real es ``app.ui.panel_archivos.PanelArchivos``; las pruebas
de los bloques pueden usar un panel falso que cumpla este protocolo.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
	import wx

	from app.core.configuracion import Configuracion
	from app.core.tareas import GestorTareas
	from app.services.vfs.base import Entrada, Proveedor


# Vistas de un panel.
VISTAS = ("completa", "breve", "informacion", "arbol", "rapida")
LADOS = ("izquierdo", "derecho")


class PanelProtocolo(Protocol):
	"""Un panel (una pestaña de un lado). Todos los métodos son del hilo de la interfaz."""

	lado: str  # «izquierdo» o «derecho»

	# Dónde está ---------------------------------------------------------------
	@property
	def proveedor(self) -> Proveedor: ...
	@property
	def ruta(self) -> str: ...
	def mostrar_ruta(self) -> str:
		"""Ruta para la persona (``C:\\datos`` o ``ftp://servidor/carpeta``)."""
	def es_local(self) -> bool: ...
	def ruta_local(self) -> str | None:
		"""Carpeta en el disco si la hay (para consola, Explorador, órdenes)."""

	# Contenido ----------------------------------------------------------------
	def entradas(self) -> Sequence[Entrada]:
		"""Entradas visibles en orden (con filtro aplicado), incluida «..» si se muestra."""
	def cursor(self) -> Entrada | None:
		"""Entrada del cursor (puede ser «..»), o None si la lista está vacía."""
	def marcadas(self) -> list[Entrada]:
		"""Entradas marcadas (nunca «..»), en el orden de la lista."""
	def elementos_trabajo(self) -> list[Entrada]:
		"""Marcadas si las hay; si no, la del cursor salvo «..»; si no, lista vacía."""
	def describir_alcance(self) -> str:
		"""«3 marcados» o el nombre del cursor, para anunciar el alcance de una orden."""

	# Acciones -----------------------------------------------------------------
	def ir_a(self, ruta: str, proveedor: Proveedor | None = None, cursor: str | None = None,
			al_terminar: Callable[[bool], None] | None = None) -> None:
		"""Lista la carpeta en segundo plano y la muestra al terminar.

		``cursor``: nombre en el que dejar el cursor. ``al_terminar(ok)`` se llama
		en el hilo de la interfaz; con error, el panel se queda donde estaba y
		ya ha avisado a la persona. Si la pestaña está bloqueada, abre una
		pestaña nueva en su lado.
		"""
	def refrescar(self, conservar: bool = True, al_terminar: Callable[[bool], None] | None = None) -> None:
		"""Vuelve a leer la carpeta conservando cursor y marcas por nombre."""
	def enfocar(self) -> None:
		"""Pone el foco en el panel (lista o vista) y lo convierte en el activo."""
	def ir_a_nombre(self, nombre: str) -> bool:
		"""Lleva el cursor a ese nombre si está en la lista."""
	def marcar(self, predicado: Callable[[Entrada], bool], valor: bool = True) -> int:
		"""Marca (o desmarca) las entradas que cumplen; devuelve cuántas cambiaron."""
	def desmarcar_todo(self) -> None: ...
	def guardar_marcas(self) -> None:
		"""Recuerda las marcas actuales (antes de una operación) para «Restaurar marcas»."""
	def restaurar_marcas(self) -> int: ...
	def fijar_tamano(self, nombre: str, tamano: int) -> None:
		"""Muestra el tamaño calculado de una carpeta en la columna Tamaño."""
	def abrir_lista(self, titulo: str, rutas: Sequence[str]) -> None:
		"""Muestra en este panel una lista de resultados (rutas locales absolutas)."""

	def es_lista(self) -> str | None:
		"""Título de la lista de resultados que muestra (búsqueda, vista plana, cesta) o None."""
	def cerrar_lista(self) -> None:
		"""Vuelve de la lista de resultados a la carpeta en la que estaba."""
	def vincular_tarea(self, tarea: Any, descripcion: str) -> None:
		"""Asocia una tarea larga al panel: Escape en el panel la cancela («Cancelado: descripción»)."""

	# Historial y unidades ---------------------------------------------------------
	def historial(self) -> list[str]:
		"""Carpetas visitadas en este panel, la más reciente primero (texto de ``mostrar_ruta``)."""
	def ir_historial(self, ruta: str) -> None:
		"""Va a una carpeta del historial."""
	def ultima_carpeta(self, unidad: str) -> str | None:
		"""Última carpeta visitada en esa unidad («D:») desde este panel, si la hay."""

	# Estado de la vista ---------------------------------------------------------
	vista: str
	filtro: str
	criterio_orden: str
	orden_inverso: bool
	bloqueada: bool
	columnas: list[str]
	def aplicar_vista(self, vista: str) -> None: ...
	def aplicar_orden(self, criterio: str, inverso: bool | None = None) -> None: ...
	def aplicar_filtro(self, patron: str) -> None: ...
	def aplicar_columnas(self, columnas: list[str], anchos: dict[str, int] | None = None) -> None:
		"""Columnas de ESTA pestaña (identificadores de ``COLUMNAS_DISPONIBLES``) y sus anchos en píxeles DIP."""

	# Puntos de enganche para otros bloques ----------------------------------------
	def lista(self) -> Any:
		"""La ``ListaArchivos`` (para G: ``fijar_iconos``, ``al_empezar_arrastre``, ``fijar_destino_soltar``)."""


@dataclass
class ContextoOrden:
	"""Lo que recibe cada manejador.

	:param lado_objetivo: si la orden se lanzó desde el menú Izquierdo o
		Derecho, el lado sobre el que actúa; si no, el activo.
	:param param: el ``param`` fijo de la orden en el catálogo.
	:param orden: id de la orden que se ejecuta.
	"""

	ventana: wx.Frame
	config: Configuracion
	tareas: GestorTareas
	operaciones: Any  # GestorOperaciones (app.services.operaciones.gestor)
	orden: str = ""
	param: str = ""
	lado_objetivo: str | None = None
	extra: dict[str, Any] = field(default_factory=dict)
	#: 2.0 (10.1, 14.9): el de una macro, el de ``zc <orden> <argumento>`` o la ruta de Intro sobre un archivo asociado.
	argumento: Any = None

	# Paneles (los rellena la ventana al crear el contexto) -----------------
	activo: PanelProtocolo = None  # type: ignore[assignment]
	pasivo: PanelProtocolo = None  # type: ignore[assignment]
	izquierdo: PanelProtocolo = None  # type: ignore[assignment]
	derecho: PanelProtocolo = None  # type: ignore[assignment]

	@property
	def objetivo(self) -> PanelProtocolo:
		"""Panel sobre el que actúa la orden: el del lado del menú o el activo."""
		if self.lado_objetivo == "izquierdo":
			return self.izquierdo
		if self.lado_objetivo == "derecho":
			return self.derecho
		return self.activo

	def otro(self, panel: PanelProtocolo) -> PanelProtocolo:
		return self.derecho if panel is self.izquierdo else self.izquierdo

	# Atajos a servicios de la ventana (los da VentanaPrincipal) --------------
	def anunciar(self, texto: str, nivel: str = "normal", completo: str = "", interrumpir: bool | None = None) -> None:
		"""Ver ``app.ui.anuncios.anunciar``. Niveles: esencial, resultado, normal, detalle."""
		from app.ui import anuncios

		anuncios.anunciar(texto, nivel, completo, interrumpir)

	@property
	def mapa_teclas(self) -> Any:
		"""``MapaTeclas`` vigente (solo lectura). Para cambiarlo: ``config.establecer("teclado.personalizadas", ...)``;
		la ventana se suscribe a «teclado.» y reconstruye despachador, menús y barra de teclas."""
		return self.ventana.mapa_teclas

	def ejecutar_orden(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None:
		"""Ejecuta otra orden del catálogo (la usa la paleta de órdenes); la firma única de 10.1."""
		if argumento is None:
			# Sin argumento, la llamada de la 1.x: así sirve también con ventanas falsas antiguas.
			self.ventana.ejecutar_orden(id_orden, lado)
		else:
			self.ventana.ejecutar_orden(id_orden, lado, argumento=argumento)

	def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> Future[bool]:
		"""Como ``ejecutar_orden``, con un futuro que se resuelve cuando su manejador ha terminado (3.4)."""
		return self.ventana.ejecutar_orden_futuro(id_orden, lado, argumento=argumento)

	def sonar(self, evento: str, variante: str = "", *, sustituye: bool = False) -> bool:
		"""Pide un sonido del catálogo (la firma única de 4.3); verdadero si se aceptó."""
		from app.services.sonidos import servicio

		return servicio.sonar(evento, variante, sustituye=sustituye)

	@property
	def modo_ayuda_teclado(self) -> bool:
		"""Si está activo, el despachador anuncia qué haría cada tecla sin hacerlo."""
		return self.ventana.modo_ayuda_teclado

	@modo_ayuda_teclado.setter
	def modo_ayuda_teclado(self, valor: bool) -> None:
		self.ventana.fijar_modo_ayuda_teclado(valor)

	def lanzar(self, operacion: Any, en_cola: bool = False, al_terminar: Callable[[Any], None] | None = None) -> None:
		"""Lanza una operación: guarda las marcas para «Restaurar marcas», anuncia el alcance y la pone en marcha.

		Al terminar, la ventana anuncia ``operacion.resumen()`` (esencial) y
		refresca los paneles que muestran ``operacion.rutas_afectadas()``.
		"""
		# 2.0 (10.1): la operación sabe en qué orden se lanzó (las macros esperan a su fin).
		if not getattr(operacion, "orden_origen", ""):
			operacion.orden_origen = self.orden
		self.ventana.lanzar_operacion(operacion, en_cola, al_terminar)

	def estado(self, texto: str) -> None:
		"""Mensaje en la barra de estado (no se anuncia)."""
		self.ventana.SetStatusText(texto)

	def servicio(self, nombre: str) -> Any:
		"""Servicios compartidos de la ventana: «sesion», «cesta», «deshacer», «secretos», «decisiones», «salida»,
		y los de la 2.0 (14.9): «eventos», «sonidos», «plugins», «grabador», «macros», «componentes», «confirmaciones»."""
		return self.ventana.servicio(nombre)
