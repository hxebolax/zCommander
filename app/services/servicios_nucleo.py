# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Contratos de los servicios de la ventana principal (diseño 2.0, 14.8 y 14.9). Sin wx.

Por qué existe: los bloques de la 2.0 se enganchan a la ventana sin editarla.
Cada uno tiene en su módulo de acciones ``instalar(ventana: VentanaServicios)``
y, con ``registrar_servicio``, sustituye el objeto NULO de uno de los nombres de
``SERVICIOS_2``. Los nulos existen desde N2 para que el núcleo pueda llamarlos
siempre (``servicio("grabador").anotar(...)``) aunque su bloque no haya llegado.

También define ``ArranqueInfo``, lo que ``main.py`` pasa a la ventana, y su
versión nula (``ArranqueInfo.nulo()``) para construir la ventana sin arranque
(pruebas): un ``CargadorNulo`` sin complementos y el bus único.

Los tipos de otros módulos van como anotaciones en texto: este módulo no
importa ``app.plugins.cargador`` ni la interfaz.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from app.services.vistas_modelo import EfectoFila

if TYPE_CHECKING:
	from app.core.configuracion import Configuracion
	from app.core.tareas import GestorTareas
	from app.services.vfs.base import Entrada

log = logging.getLogger(__name__)

#: Nombres de ``ventana.servicio()`` que añade la 2.0 (con un nulo desde N2).
SERVICIOS_2 = ("eventos", "sonidos", "plugins", "grabador", "macros", "componentes", "confirmaciones")
#: Los que un bloque puede sustituir con ``registrar_servicio`` (los demás los pone el núcleo).
SUSTITUIBLES = ("grabador", "macros", "componentes", "sonidos", "plugins")


# ── Protocolos ───────────────────────────────────────────────────────────────


class Grabador(Protocol):
	"""Grabación de macros (PE, 10.1): la ventana anota cada orden ANTES de ejecutarla."""

	grabando: bool

	def anotar(self, id_orden: str, argumento: Any) -> None: ...
	def anotar_argumento(self, valor: Any) -> None: ...


class ServicioMacros(Protocol):
	"""Ejecución de macros (PE, 10.1)."""

	def en_curso(self) -> bool: ...
	def detener(self) -> bool: ...
	def ejecutar(self, nombre: str) -> None: ...


class ServicioComponentes(Protocol):
	"""Componentes de ``data/bin`` (CO, 3.7 y 6.3)."""

	def ruta(self, id: str) -> Path: ...
	def ejecutable(self, id: str, nombre: str) -> Path: ...
	def disponible(self, id: str) -> bool: ...
	def registrar_al_detener(self, id: str, funcion: Callable[[], bool]) -> None: ...
	def estado_de(self, id: str) -> str: ...


class VentanaServicios(Protocol):
	"""Lo único de la ventana principal que pueden usar las funciones ``instalar`` de los bloques."""

	config: Configuracion
	tareas: GestorTareas

	def registrar_servicio(self, nombre: str, objeto: Any) -> None: ...
	def servicio(self, nombre: str) -> Any: ...
	def anunciar(self, texto: str, nivel: str = "normal", completo: str = "", sonido: str = "") -> None: ...
	def llamar_mas_tarde(self, ms: int, funcion: Callable[[], None]) -> None: ...
	def esta_libre(self) -> bool: ...
	def padre(self) -> Any: ...
	def fijar_decorador_fila(self, funcion: Callable[[Entrada], EfectoFila | None] | None) -> None: ...
	def colocar_barra_botones(self, barra: Any | None) -> None: ...
	def registrar_tecla_global(self, id_orden: str, tecla: str) -> bool: ...
	def liberar_teclas_globales(self) -> None: ...


# ── Nulos ────────────────────────────────────────────────────────────────────


class GrabadorNulo:
	"""Nunca graba (hasta que PE ponga el grabador real)."""

	grabando = False

	def anotar(self, id_orden: str, argumento: Any) -> None:
		return None

	def anotar_argumento(self, valor: Any) -> None:
		return None


class MacrosNulo:
	"""Nunca hay una macro en curso (hasta que PE ponga el servicio real)."""

	def en_curso(self) -> bool:
		return False

	def detener(self) -> bool:
		return False

	def ejecutar(self, nombre: str) -> None:
		log.info("Macro «%s» no ejecutada: las macros aún no están disponibles", nombre)


class ComponentesNulo:
	"""Delegación en las funciones provisionales de ``app.services.componentes.estado`` (CO)."""

	def ruta(self, id: str) -> Path:
		from app.services.componentes import estado

		return estado.ruta(id)

	def ejecutable(self, id: str, nombre: str) -> Path:
		from app.services.componentes import estado

		return estado.ejecutable(id, nombre)

	def disponible(self, id: str) -> bool:
		from app.services.componentes import estado

		return estado.disponible(id)

	def registrar_al_detener(self, id: str, funcion: Callable[[], bool]) -> None:
		from app.services.componentes import estado

		estado.registrar_al_detener(id, funcion)

	def estado_de(self, id: str) -> str:
		from app.services.componentes import estado

		return estado.estado_de(id)


class CargadorNulo:
	"""Cargador sin complementos: lo que usa la ventana cuando no recibe ``ArranqueInfo``.

	Todos sus métodos existen y no tienen efecto, así la ventana sigue el
	cierre de 3.4 igual con o sin complementos.
	"""

	modo_seguro = False

	def congelar(self) -> None:
		return None

	def descongelar(self) -> None:
		return None

	def cerrar(self) -> None:
		return None

	def activos(self) -> list[tuple[str, Any]]:
		return []

	def ejecutar_tarea_programada(self, id: str, al_terminar: Callable[[int], None]) -> None:
		log.info("Tarea programada «%s» sin cargador de complementos: no se ejecuta", id)

	def activar_al_arrancar(self) -> None:
		return None

	def avisos_arranque(self) -> list[str]:
		return []


@dataclass(frozen=True)
class ArranqueInfo:
	"""Lo que ``main.py`` pasa a ``VentanaPrincipal`` (14.8)."""

	cargador: Any  # "Cargador": el de cargador.arrancar (paso 8)
	bus: Any  # "Bus": eventos.bus()
	modo: Literal["normal", "tarea", "sesion"] = "normal"
	tarea: str | None = None
	tras_actualizar: bool = False
	avisos: tuple[str, ...] = ()
	integracion: Any = None  # "ResumenIntegracion | None" (paso 6)
	restauracion: Any = None  # "ResultadoRestauracion | None" (paso 5)

	@classmethod
	def nulo(cls) -> ArranqueInfo:
		"""Arranque sin complementos, modo normal y el bus único (ventanas de las pruebas)."""
		from app.services import eventos

		return cls(cargador=CargadorNulo(), bus=eventos.bus())
