# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Modelo del motor de operaciones: estados, progreso, conflictos, respuestas y la clase base.

Una operación (copiar, mover, eliminar, comprimir, sincronizar...) es un objeto
que se ejecuta en un hilo del ``GestorOperaciones``. No toca la interfaz: para
preguntar algo usa el ``Decisor`` que recibe en su ``ContextoEjecucion`` (lo
implementa la interfaz con una cola única de decisiones), y su progreso lo lee
la interfaz cuando quiere (``instantanea()``), sin avisos en ráfaga.

Transiciones de estado válidas:

La tabla ``TRANSICIONES`` es la referencia. Reglas de hilos:

- Solo el hilo de la operación cambia su estado. La interfaz PIDE pausar,
  reanudar o cancelar (``pausar()``, ``reanudar()``, ``cancelar()``) y el hilo
  lo aplica en su siguiente ``ctx.comprobar()``: no hay carreras entre
  «pausar» y «terminar».
- En pausa, ``comprobar()`` pone EN_PAUSA y, al reanudar, vuelve al estado que
  tenía (EJECUTANDO o VERIFICANDO).
- Las esperas de decisiones van en ``with ctx.esperando():`` (estado
  ESPERANDO_DECISION y vuelta al anterior).
- El tiempo en pausa o esperando no cuenta para la velocidad ni para el
  tiempo restante.
"""

from __future__ import annotations

import builtins
import itertools
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from app.services import formato
from app.services.vfs import base


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Estado(StrEnum):
	EN_COLA = "en_cola"
	ANALIZANDO = "analizando"
	ESPERANDO_DECISION = "esperando_decision"
	EJECUTANDO = "ejecutando"
	VERIFICANDO = "verificando"
	EN_PAUSA = "en_pausa"
	TERMINADA = "terminada"
	TERMINADA_CON_ERRORES = "terminada_con_errores"
	CANCELADA = "cancelada"
	FALLIDA = "fallida"

	@property
	def texto(self) -> str:
		return {
			Estado.EN_COLA: _("En cola"),
			Estado.ANALIZANDO: _("Analizando"),
			Estado.ESPERANDO_DECISION: _("Espera su decisión"),
			Estado.EJECUTANDO: _("En marcha"),
			Estado.VERIFICANDO: _("Verificando"),
			Estado.EN_PAUSA: _("En pausa"),
			Estado.TERMINADA: _("Terminada"),
			Estado.TERMINADA_CON_ERRORES: _("Terminada con errores"),
			Estado.CANCELADA: _("Cancelada"),
			Estado.FALLIDA: _("Fallida"),
		}[self]

	@property
	def final(self) -> bool:
		return self in (Estado.TERMINADA, Estado.TERMINADA_CON_ERRORES, Estado.CANCELADA, Estado.FALLIDA)


TRANSICIONES: dict[Estado, frozenset[Estado]] = {
	Estado.EN_COLA: frozenset({
		Estado.ANALIZANDO, Estado.EJECUTANDO, Estado.ESPERANDO_DECISION, Estado.TERMINADA, Estado.TERMINADA_CON_ERRORES,
		Estado.CANCELADA, Estado.FALLIDA,
	}),
	Estado.ANALIZANDO: frozenset({
		Estado.ESPERANDO_DECISION, Estado.EJECUTANDO, Estado.EN_PAUSA, Estado.TERMINADA, Estado.TERMINADA_CON_ERRORES,
		Estado.CANCELADA, Estado.FALLIDA,
	}),
	Estado.ESPERANDO_DECISION: frozenset({Estado.EJECUTANDO, Estado.ANALIZANDO, Estado.VERIFICANDO, Estado.CANCELADA, Estado.FALLIDA}),
	Estado.EJECUTANDO: frozenset({
		Estado.EN_PAUSA, Estado.VERIFICANDO, Estado.ESPERANDO_DECISION, Estado.TERMINADA,
		Estado.TERMINADA_CON_ERRORES, Estado.CANCELADA, Estado.FALLIDA,
	}),
	Estado.VERIFICANDO: frozenset({
		Estado.EJECUTANDO, Estado.ESPERANDO_DECISION, Estado.TERMINADA, Estado.TERMINADA_CON_ERRORES,
		Estado.CANCELADA, Estado.FALLIDA, Estado.EN_PAUSA,
	}),
	Estado.EN_PAUSA: frozenset({Estado.EJECUTANDO, Estado.VERIFICANDO, Estado.ANALIZANDO, Estado.CANCELADA, Estado.FALLIDA}),
}


class Politica(StrEnum):
	"""Qué hacer cuando el destino ya existe (preferencia ``operaciones.politica_conflicto``)."""

	PREGUNTAR = "preguntar"
	SOBRESCRIBIR = "sobrescribir"
	OMITIR = "omitir"
	SOBRESCRIBIR_SI_MAS_ANTIGUO = "sobrescribir_si_mas_antiguo"
	SOBRESCRIBIR_SI_CAMBIA_TAMANO = "sobrescribir_si_cambia_tamano"
	RENOMBRAR_COPIA = "renombrar_copia"
	RENOMBRAR_EXISTENTE = "renombrar_existente"


class AccionConflicto(StrEnum):
	SOBRESCRIBIR = "sobrescribir"
	OMITIR = "omitir"
	RENOMBRAR = "renombrar"  # con el nombre de RespuestaConflicto.nombre_nuevo
	RENOMBRAR_COPIA = "renombrar_copia"  # «nombre (2).ext» para la copia
	RENOMBRAR_EXISTENTE = "renombrar_existente"  # «nombre (2).ext» para el que ya estaba
	SOBRESCRIBIR_SI_MAS_ANTIGUO = "sobrescribir_si_mas_antiguo"
	SOBRESCRIBIR_SI_CAMBIA_TAMANO = "sobrescribir_si_cambia_tamano"
	CANCELAR = "cancelar"


@dataclass(frozen=True)
class RespuestaConflicto:
	"""Respuesta a un conflicto. ``para_todos`` la convierte en la política del resto de la operación."""

	accion: AccionConflicto
	nombre_nuevo: str = ""
	para_todos: bool = False


class AccionError(StrEnum):
	REINTENTAR = "reintentar"
	OMITIR = "omitir"
	OMITIR_TODOS = "omitir_todos"
	CANCELAR = "cancelar"


@dataclass(frozen=True)
class Conflicto:
	"""Un elemento cuyo destino ya existe.

	:param relativo: ruta relativa a la raíz de la operación (para listas).
	:param origen, destino: entradas de cada lado (tamaño, fecha, atributos).
	:param ruta_destino: ruta completa del destino en su proveedor.
	"""

	relativo: str
	origen: base.Entrada
	destino: base.Entrada
	ruta_destino: str

	def descripcion(self) -> str:
		"""Texto para el lector: tamaños, fechas y cuál es más reciente."""
		o, d = self.origen, self.destino
		if o.modificado > d.modificado + 2:
			reciente = _("El origen es más reciente.")
		elif d.modificado > o.modificado + 2:
			reciente = _("El destino es más reciente.")
		else:
			reciente = _("Tienen la misma fecha.")
		return _(
			"Ya existe «{nombre}».\nOrigen: {to}, {fo}.\nDestino: {td}, {fd}.\n{reciente}"
		).format(
			nombre=self.relativo, to=formato.tamano_legible(o.tamano), fo=formato.fecha(o.modificado, "larga"),
			td=formato.tamano_legible(d.tamano), fd=formato.fecha(d.modificado, "larga"), reciente=reciente,
		)


@dataclass(frozen=True)
class PreguntaError:
	"""Error en un elemento: la persona decide reintentar, omitir o cancelar."""

	ruta: str
	mensaje: str
	operacion: str = ""
	#: 2.0 (14.6): ``winerror`` del ``OSError`` (32 o 33: archivo en uso), para que
	#: las acciones de error de los complementos decidan sin leer el mensaje.
	codigo_windows: int = 0
	excepcion: BaseException | None = None


@dataclass(frozen=True)
class RespuestasAutomaticas:
	"""Respuestas sin preguntar para las tareas programadas (14.6, 11.24).

	El gestor de decisiones normal responde con ellas, sin mostrar nada, a los
	conflictos (``conflicto``) y a los errores (``error``) de una operación que
	las lleva, y apunta cada decisión en ``registro``.
	"""

	conflicto: Politica
	error: AccionError = AccionError.OMITIR
	registro: logging.Logger | None = None


@dataclass(frozen=True)
class ErrorElemento:
	ruta: str
	mensaje: str
	momento: float = field(default_factory=time.time)


class Decisor(Protocol):
	"""Lo implementa la interfaz (cola única de decisiones). Los métodos BLOQUEAN el hilo de la operación.

	Si la persona cierra la aplicación o cancela la operación mientras se
	espera, devuelven CANCELAR. Nunca se llaman desde el hilo de la interfaz.
	"""

	def resolver_conflictos(self, operacion: Operacion, conflictos: Sequence[Conflicto]) -> list[RespuestaConflicto] | None:
		"""Lista de conflictos conocidos tras el análisis; una respuesta por conflicto, o None para cancelar."""

	def preguntar_conflicto(self, operacion: Operacion, conflicto: Conflicto) -> RespuestaConflicto:
		"""Un conflicto que aparece durante la copia."""

	def preguntar_error(self, operacion: Operacion, pregunta: PreguntaError) -> AccionError:
		"""Un error en un elemento."""

	def elegir(
		self, titulo: str, texto: str, opciones: Sequence[str], predeterminada: int = 0, escape: int = -1,
		operacion: Operacion | None = None,
	) -> int:
		"""Pregunta con botones (espacio insuficiente, unidad sin papelera, solo lectura, huella de un servidor...).

		Devuelve el índice del botón, o ``escape`` si se cierra con Escape o se cancela.
		``operacion`` es la que pregunta (se anuncia su descripción); ``None`` fuera de una operación.
		"""

	def pedir_texto(
		self, titulo: str, texto: str, valor: str = "", oculto: bool = False, operacion: Operacion | None = None,
	) -> str | None:
		"""Pide un texto (contraseña de un comprimido o de un servidor); None si se cancela."""

	def pedir_credenciales(
		self, titulo: str, texto: str, usuario: str = "", operacion: Operacion | None = None,
	) -> tuple[str, str, bool] | None:
		"""Pide usuario, contraseña y «recordar» (9.4); None si se cancela."""

	def elegir_con_casilla(
		self, titulo: str, texto: str, opciones: Sequence[str], casilla: str, predeterminada: int = 0, escape: int = -1,
		operacion: Operacion | None = None,
	) -> tuple[int, bool]:
		"""Como ``elegir``, con una casilla («No volver a preguntar», 10.12): (índice, casilla marcada)."""


@dataclass
class Progreso:
	"""Progreso consultable. La interfaz lee una copia con ``Operacion.instantanea()``."""

	archivos_total: int = 0
	archivos_hechos: int = 0
	bytes_total: int = 0
	bytes_hechos: int = 0
	actual: str = ""
	bytes_actual: int = 0
	total_actual: int = 0
	omitidos: int = 0
	velocidad: float = 0.0
	restante_s: float | None = None
	#: Reloj monótono (``time.monotonic``) al empezar a ejecutar y al terminar.
	inicio: float = 0.0
	fin: float = 0.0
	#: Segundos en pausa o esperando una decisión DESPUÉS de empezar (no cuentan para la velocidad).
	parado_s: float = 0.0

	@property
	def porcentaje(self) -> int | None:
		if self.bytes_total > 0:
			return min(100, int(self.bytes_hechos * 100 / self.bytes_total))
		if self.archivos_total > 0:
			return min(100, int(self.archivos_hechos * 100 / self.archivos_total))
		return None

	@property
	def porcentaje_actual(self) -> int | None:
		if self.total_actual > 0:
			return min(100, int(self.bytes_actual * 100 / self.total_actual))
		return None

	@property
	def duracion(self) -> float:
		"""Tiempo de trabajo (sin pausas ni esperas)."""
		if not self.inicio:
			return 0.0
		return max(0.0, (self.fin or time.monotonic()) - self.inicio - self.parado_s)


class ContextoEjecucion:
	"""Lo que una operación recibe del gestor al ejecutarse.

	:param token: cancelación (``TokenCancelacion`` de ``app.core.tareas`` o ``threading.Event``).
	:param decisor: quien responde a conflictos y errores.
	"""

	def __init__(self, token, decisor: Decisor) -> None:
		self.token = token
		self.decisor = decisor
		self.reanudar = threading.Event()
		self.reanudar.set()
		#: La operación a la que pertenece (la pone el gestor).
		self.operacion: Operacion | None = None

	def cancelado(self) -> bool:
		return self.token.is_set()

	def comprobar(self) -> None:
		"""Aplica la pausa pedida y lanza ``base.Cancelado`` si se canceló. Solo desde el hilo de la operación."""
		if not self.reanudar.is_set() and not self.token.is_set():
			operacion = self.operacion.raiz() if self.operacion is not None else None
			anterior = operacion.estado if operacion is not None else None
			inicio = time.monotonic()
			if operacion is not None and anterior in (Estado.EJECUTANDO, Estado.VERIFICANDO, Estado.ANALIZANDO):
				operacion.cambiar_estado(Estado.EN_PAUSA)
			while not self.reanudar.wait(0.2):
				if self.token.is_set():
					break
			if operacion is not None:
				operacion.sumar_parado(time.monotonic() - inicio)
				if operacion.estado == Estado.EN_PAUSA and not self.token.is_set():
					operacion.cambiar_estado(anterior)
		if self.token.is_set():
			raise base.Cancelado()

	@contextmanager
	def esperando(self) -> Iterator[None]:
		"""Marca la espera de una decisión (estado y tiempo) y devuelve el estado anterior al salir."""
		operacion = self.operacion
		anterior = operacion.estado if operacion is not None else None
		inicio = time.monotonic()
		if operacion is not None and anterior not in (None, Estado.ESPERANDO_DECISION) and not anterior.final:
			operacion.cambiar_estado(Estado.ESPERANDO_DECISION)
		try:
			yield
		finally:
			if operacion is not None:
				operacion.sumar_parado(time.monotonic() - inicio)
				if operacion.estado == Estado.ESPERANDO_DECISION and not self.token.is_set():
					operacion.cambiar_estado(Estado.EJECUTANDO if anterior in (None, Estado.EN_COLA) else anterior)


_contador = itertools.count(1)


class Operacion(ABC):
	"""Clase base. Las subclases implementan ``ejecutar`` y ``descripcion``.

	Reglas para las subclases:

	- Llaman a ``ctx.comprobar()`` entre elementos y dentro de los bucles de bytes.
	- Actualizan el progreso con ``self.progresar(...)`` (barato; la interfaz lo lee).
	- Cambian de estado con ``self.cambiar_estado(...)`` (valida la transición).
	- Registran los errores con ``self.anotar_error(ruta, mensaje)``.
	- No lanzan para errores de un elemento: preguntan con ``ctx.decisor`` o
	  los anotan. Lanzan ``base.Cancelado`` para terminar por cancelación.
	- Empiezan pasando a ANALIZANDO o EJECUTANDO (si no, el gestor lo hace por ellas al terminar).
	- Esperan decisiones dentro de ``with ctx.esperando():``.
	- Declaran ``carriles`` (volúmenes de origen y destino) y ``rutas_afectadas``.
	"""

	tipo: str = "operacion"
	admite_pausa: bool = True

	def __init__(self) -> None:
		self.id = next(_contador)
		self._candado = threading.Lock()
		self._estado = Estado.EN_COLA
		self._progreso = Progreso()
		self.errores: list[ErrorElemento] = []
		self.historial: deque[str] = deque(maxlen=200)
		self.contexto: ContextoEjecucion | None = None
		#: Lo que hay que deshacer si la operación lo admite (lo rellena la subclase;
		#: la ventana lo registra al terminar: los bloques nunca llaman a ``registrar``).
		self.deshacer: object | None = None
		#: Operación que la ejecuta como suboperación (``ejecutar_sub``), o None.
		self.padre: Operacion | None = None
		self._sub: Operacion | None = None
		#: 2.0 (10.1): id de la orden en cuyo manejador se lanzó (lo pone ContextoOrden.lanzar).
		self.orden_origen: str = ""
		#: 2.0 (14.6): respuestas sin preguntar (tareas programadas).
		self.respuestas_automaticas: RespuestasAutomaticas | None = None

	# Identidad ---------------------------------------------------------------

	@abstractmethod
	def descripcion(self) -> str:
		"""Frase corta: «Copiar 3 elementos a D:\\Copias»."""

	@property
	def carriles(self) -> frozenset[str]:
		"""Volúmenes que ocupa (origen y destino), hechos con ``clave_carril``.

		Dos operaciones que comparten alguno van en serie. Vacío: no espera a
		nadie (operaciones de metadatos en disco local, como crear carpeta o renombrar;
		en comprimidos y servidores deben declarar el carril de su contenedor).
		"""
		return frozenset()

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		"""(esquema, carpeta) que hay que refrescar al terminar en los paneles que las muestren."""
		return []

	# Estado y progreso ------------------------------------------------------

	@property
	def estado(self) -> Estado:
		return self._estado

	def cambiar_estado(self, nuevo: Estado) -> None:
		with self._candado:
			if nuevo == self._estado:
				return
			permitidos = TRANSICIONES.get(self._estado, frozenset())
			if nuevo not in permitidos:
				raise ValueError(f"Transición no válida: {self._estado} → {nuevo}")
			self._estado = nuevo
			if nuevo == Estado.EJECUTANDO and not self._progreso.inicio:
				self._progreso.inicio = time.monotonic()
			if nuevo.final:
				self._progreso.fin = time.monotonic()

	def progresar(self, **cambios) -> None:
		"""Actualiza campos del progreso y recalcula velocidad y tiempo restante."""
		with self._candado:
			for clave, valor in cambios.items():
				setattr(self._progreso, clave, valor)
			p = self._progreso
			if p.inicio and p.bytes_hechos:
				transcurrido = max(0.001, time.monotonic() - p.inicio - p.parado_s)
				p.velocidad = p.bytes_hechos / transcurrido
				if p.bytes_total > p.bytes_hechos and p.velocidad > 0:
					p.restante_s = (p.bytes_total - p.bytes_hechos) / p.velocidad
				else:
					p.restante_s = 0.0

	def sumar(self, **incrementos) -> None:
		"""Suma a contadores del progreso (``bytes_hechos=4096``)."""
		with self._candado:
			for clave, valor in incrementos.items():
				setattr(self._progreso, clave, getattr(self._progreso, clave) + valor)
		self.progresar()

	def sumar_parado(self, segundos: float) -> None:
		with self._candado:
			# Lo parado antes de empezar a ejecutar no cuenta: el reloj aún no corría.
			if self._progreso.inicio:
				self._progreso.parado_s += max(0.0, segundos)

	def instantanea(self) -> Progreso:
		"""Copia del progreso; con una suboperación en curso, se le suma la de la sub."""
		with self._candado:
			propio = replace(self._progreso)
			sub = self._sub
		if sub is None:
			return propio
		otro = sub.instantanea()
		propio.archivos_total += otro.archivos_total
		propio.archivos_hechos += otro.archivos_hechos
		propio.bytes_total += otro.bytes_total
		propio.bytes_hechos += otro.bytes_hechos
		propio.omitidos += otro.omitidos
		propio.actual = otro.actual or propio.actual
		propio.bytes_actual, propio.total_actual = otro.bytes_actual, otro.total_actual
		propio.velocidad = otro.velocidad or propio.velocidad
		propio.restante_s = otro.restante_s
		return propio

	def ejecutar_sub(self, sub: Operacion, ctx: ContextoEjecucion) -> Operacion:
		"""Ejecuta ``sub`` en este hilo como parte de esta operación.

		La sub comparte contexto (cancelación, pausa, decisor); las preguntas se
		hacen en nombre del padre (``operacion.padre or operacion``); al terminar,
		sus errores, ``fallidos``, progreso y pasos de deshacer pasan al padre.
		"""
		sub.padre = self
		sub.contexto = ctx
		with self._candado:
			self._sub = sub
		try:
			sub.ejecutar(ctx)
		finally:
			final = sub.instantanea()
			with self._candado:
				self._sub = None
				self._progreso.archivos_total += final.archivos_total
				self._progreso.archivos_hechos += final.archivos_hechos
				self._progreso.bytes_total += final.bytes_total
				self._progreso.bytes_hechos += final.bytes_hechos
				self._progreso.omitidos += final.omitidos
				self.errores.extend(sub.errores)
			if getattr(sub, "fallidos", None):
				self.fallidos = list(getattr(self, "fallidos", [])) + list(sub.fallidos)  # type: ignore[attr-defined]
			if sub.deshacer is not None:
				if self.deshacer is None:
					self.deshacer = sub.deshacer
				else:
					getattr(self.deshacer, "pasos", []).extend(getattr(sub.deshacer, "pasos", []))
		return sub

	def raiz(self) -> Operacion:
		"""La operación de nivel superior (para el decisor y la ventana de operaciones)."""
		return self.padre.raiz() if self.padre is not None else self

	def anotar_error(self, ruta: str, mensaje: str) -> None:
		with self._candado:
			self.errores.append(ErrorElemento(ruta, mensaje))

	# Control ----------------------------------------------------------------

	def pausar(self) -> None:
		"""Pide la pausa; la aplica el hilo de la operación en su siguiente comprobación."""
		if self.contexto is not None and self.admite_pausa and not self._estado.final:
			self.contexto.reanudar.clear()

	def reanudar(self) -> None:
		if self.contexto is not None:
			self.contexto.reanudar.set()

	@property
	def pausa_pedida(self) -> bool:
		return self.contexto is not None and not self.contexto.reanudar.is_set()

	def cancelar(self) -> None:
		if self.contexto is not None:
			# TokenCancelacion y threading.Event tienen los dos set().
			self.contexto.token.set()
			self.contexto.reanudar.set()

	# Ejecución --------------------------------------------------------------

	@abstractmethod
	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		"""Hace el trabajo (en un hilo). Termina dejando un estado final."""

	def resumen(self) -> str:
		"""Frase final para anunciar: «Copia terminada: 400 archivos, 2,1 GB, 2 omitidos, 1 error, 1 min 20 s»."""
		p = self.instantanea()
		partes = [self.descripcion() + ": " + self.estado.texto.lower()]
		if p.archivos_hechos:
			partes.append(formato.plural(p.archivos_hechos, _("{n} archivo"), _("{n} archivos")))
		if p.bytes_hechos:
			partes.append(formato.tamano_legible(p.bytes_hechos))
		if p.omitidos:
			partes.append(formato.plural(p.omitidos, _("{n} omitido"), _("{n} omitidos")))
		if self.errores:
			partes.append(formato.plural(len(self.errores), _("{n} error"), _("{n} errores")))
		if p.duracion >= 1:
			partes.append(formato.duracion(p.duracion))
		return ", ".join(partes)


def claves_carril(proveedor: base.Proveedor, rutas_: list[str] | tuple[str, ...]) -> set[str]:
	"""Carriles de varias rutas (listas de resultados y cesta pueden mezclar volúmenes).

	En un comprimido, el propio archivo comprimido y el volumen que lo contiene.
	"""
	claves: set[str] = set()
	for ruta in rutas_:
		claves.add(clave_carril(proveedor, ruta))
		if proveedor.contenedor is not None:
			contenedor, ruta_archivo = proveedor.contenedor
			claves.add(clave_carril(contenedor, ruta_archivo))
	return claves


def clave_carril(proveedor: base.Proveedor, ruta: str) -> str:
	"""Clave del volumen de ``ruta``: «local:c:\\», «local:\\\\servidor\\recurso\\», «ftp:servidor».

	En comprimidos, el propio archivo («comprimido:c:\\a.zip»). Dos letras del mismo disco
	físico cuentan como volúmenes distintos (limitación conocida).
	"""
	if proveedor.contenedor is not None:
		_contenedor, ruta_archivo = proveedor.contenedor
		return f"comprimido:{ruta_archivo.casefold()}"
	if proveedor.esquema in ("local", "resultados"):
		from app.services.vfs import rutas

		return "local:" + (rutas.raiz(rutas.normalizar(ruta)).casefold() if ruta else "")
	return f"{proveedor.esquema}:{getattr(proveedor, 'servidor', '')}"
