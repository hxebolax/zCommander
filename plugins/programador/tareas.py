# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tareas programadas, registro de ejecuciones y la operación de limpieza (diseño 2.0, 11.24). Sin wx.

Las tareas viven en ``datos/tareas.json`` y el resultado de cada ejecución en
``datos/registro.json`` (los dos en ``data/config/plugins/zc.programador/``,
que la copia de seguridad restaura junto como «Tareas del programador»).
"""

from __future__ import annotations

import datetime as _fecha
import json
import logging
import secrets
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.plugins import api

log = logging.getLogger("zcplugins.zc.programador")

ARCHIVO_TAREAS = "tareas.json"
ARCHIVO_REGISTRO = "registro.json"
MAXIMO_REGISTRO = 500

SINCRONIZACION, COPIA, REGLAS, LIMPIEZA, MACRO, MENU_USUARIO, ORDEN = (
	"sincronizacion", "copia", "reglas", "limpieza", "macro", "menu_usuario", "orden")
TIPOS = {
	SINCRONIZACION: "Ejecutar una tarea de sincronización",
	COPIA: "Copiar a una carpeta",
	REGLAS: "Aplicar las reglas del monitor a una carpeta",
	LIMPIEZA: "Limpiar: a la papelera lo antiguo de una carpeta",
	MACRO: "Ejecutar una macro",
	MENU_USUARIO: "Ejecutar una entrada del menú de usuario",
	ORDEN: "Ejecutar una orden de zCommander",
}
OBJETIVOS = {
	SINCRONIZACION: "nombre de la tarea de sincronización",
	COPIA: "carpeta o archivo que se copia",
	REGLAS: "carpeta vigilada",
	LIMPIEZA: "carpeta que se limpia",
	MACRO: "nombre de la macro",
	MENU_USUARIO: "nombre de la entrada del menú de usuario",
	ORDEN: "id de la orden, como zc.sincronizacion:ejecutar_todas",
}
UNA_VEZ, DIARIA, SEMANAL, AL_INICIAR_SESION = "una_vez", "diaria", "semanal", "al_iniciar_sesion"
FRECUENCIAS = {UNA_VEZ: "Una vez", DIARIA: "Cada día", SEMANAL: "Cada semana", AL_INICIAR_SESION: "Al iniciar sesión en Windows"}
DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
CONFLICTOS = {
	"omitir": "Omitirlo",
	"sobrescribir": "Sobrescribirlo",
	"sobrescribir_si_mas_antiguo": "Sobrescribirlo si es más antiguo",
	"renombrar_copia": "Guardar la copia con otro nombre",
}
ERRORES = {"omitir": "Omitir el elemento y seguir", "cancelar": "Cancelar la tarea"}

# Códigos de salida de ``ejecutar_tarea`` (11.0).
BIEN, CON_ERRORES, NO_EMPEZO = 0, 1, 2
TEXTO_CODIGO = {BIEN: "Bien", CON_ERRORES: "Con errores", NO_EMPEZO: "No se pudo empezar"}


@dataclass
class Tarea:
	nombre: str
	tipo: str = SINCRONIZACION
	objetivo: str = ""
	destino: str = ""
	dias: int = 30
	frecuencia: str = DIARIA
	hora: str = "09:00"
	fecha: str = ""  # AAAA-MM-DD: la de «una vez» y el primer día de las demás
	dias_semana: list[int] = field(default_factory=lambda: [0])
	conflicto: str = "omitir"
	error: str = "omitir"
	activa: bool = True
	id: str = field(default_factory=lambda: secrets.token_hex(4))
	ultima: float = 0.0
	resultado: int = -1

	@classmethod
	def desde(cls, datos: dict) -> Tarea:
		tarea = cls(**{k: v for k, v in datos.items() if k in cls.__dataclass_fields__})
		if tarea.tipo not in TIPOS or tarea.frecuencia not in FRECUENCIAS:
			raise ValueError("tipo o frecuencia desconocidos")
		return tarea

	def que_hace(self) -> str:
		return f"{TIPOS[self.tipo]}: {self.objetivo}" + (f" a {self.destino}" if self.tipo == COPIA and self.destino else "")

	def cuando(self) -> str:
		if self.frecuencia == UNA_VEZ:
			return f"Una vez, el {self.fecha or 'día de hoy'} a las {self.hora}"
		if self.frecuencia == DIARIA:
			return f"Cada día a las {self.hora}"
		if self.frecuencia == SEMANAL:
			dias = ", ".join(DIAS[d].lower() for d in sorted(set(self.dias_semana)) if 0 <= d < 7) or "ningún día"
			return f"Cada semana ({dias}) a las {self.hora}"
		return FRECUENCIAS[AL_INICIAR_SESION]

	def error_de_datos(self) -> str:
		"""Qué falta o está mal ("" si se puede guardar)."""
		if not self.nombre.strip():
			return "Escriba un nombre para la tarea."
		if not self.objetivo.strip():
			return f"Escriba el objetivo: {OBJETIVOS[self.tipo]}."
		if self.tipo == COPIA and not self.destino.strip():
			return "Escriba la carpeta de destino de la copia."
		if self.frecuencia != AL_INICIAR_SESION:
			try:
				hora_y_minutos(self.hora)
			except ValueError:
				return "La hora debe tener la forma HH:MM, por ejemplo 08:30."
		if self.frecuencia == UNA_VEZ or self.fecha:
			try:
				_fecha.date.fromisoformat(self.fecha or "")
			except ValueError:
				return "La fecha debe tener la forma AAAA-MM-DD, por ejemplo 2026-12-31."
		if self.frecuencia == SEMANAL and not self.dias_semana:
			return "Marque al menos un día de la semana."
		return ""


def hora_y_minutos(texto: str) -> tuple[int, int]:
	horas, _dos, minutos = texto.strip().partition(":")
	valor = (int(horas), int(minutos))
	if not (0 <= valor[0] < 24 and 0 <= valor[1] < 60):
		raise ValueError(texto)
	return valor


def leer_tareas(carpeta: Path) -> list[Tarea]:
	try:
		datos = json.loads((Path(carpeta) / ARCHIVO_TAREAS).read_text(encoding="utf-8"))
	except FileNotFoundError:
		return []
	except (OSError, ValueError):
		log.warning("No se pudieron leer las tareas programadas", exc_info=True)
		return []
	tareas = []
	for elemento in datos.get("tareas", []) if isinstance(datos, dict) else []:
		try:
			tareas.append(Tarea.desde(elemento))
		except (TypeError, ValueError):
			log.warning("Tarea programada no válida: %r", elemento)
	return tareas


def _escribir(ruta: Path, datos: object) -> None:
	ruta.parent.mkdir(parents=True, exist_ok=True)
	temporal = ruta.with_suffix(".tmp")
	temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
	temporal.replace(ruta)


def guardar_tareas(carpeta: Path, tareas: Iterable[Tarea]) -> None:
	_escribir(Path(carpeta) / ARCHIVO_TAREAS, {"version": 1, "tareas": [asdict(t) for t in tareas]})


def buscar(tareas: Iterable[Tarea], id_tarea: str) -> Tarea | None:
	return next((t for t in tareas if t.id == id_tarea), None)


# ── Cuándo toca (solo sin el Programador de Windows, con zCommander abierto) ─


def momento_de_hoy(tarea: Tarea, hoy: _fecha.date) -> float:
	horas, minutos = hora_y_minutos(tarea.hora)
	return _fecha.datetime(hoy.year, hoy.month, hoy.day, horas, minutos).timestamp()


def vence(tarea: Tarea, ahora: float) -> bool:
	"""Verdadero si la tarea debía ejecutarse ya y no se ha ejecutado desde entonces."""
	if not tarea.activa or tarea.frecuencia == AL_INICIAR_SESION:
		return False
	hoy = _fecha.date.fromtimestamp(ahora)
	if tarea.fecha:
		try:
			primero = _fecha.date.fromisoformat(tarea.fecha)
		except ValueError:
			return False
		if tarea.frecuencia == UNA_VEZ:
			momento = momento_de_hoy(tarea, primero)
			return momento <= ahora and tarea.ultima < momento
		if hoy < primero:
			return False
	if tarea.frecuencia == SEMANAL and hoy.weekday() not in tarea.dias_semana:
		return False
	momento = momento_de_hoy(tarea, hoy)
	return momento <= ahora and tarea.ultima < momento


# ── Registro de ejecuciones ──────────────────────────────────────────────────


@dataclass
class Ejecucion:
	id_tarea: str
	nombre: str
	inicio: float
	fin: float = 0.0
	codigo: int = -1
	resumen: str = ""
	decisiones: list[str] = field(default_factory=list)
	visto: bool = False

	def texto(self) -> str:
		return TEXTO_CODIGO.get(self.codigo, "En marcha")


class RegistroEjecuciones:
	def __init__(self, carpeta: Path) -> None:
		self.ruta = Path(carpeta) / ARCHIVO_REGISTRO
		self._candado = threading.Lock()

	def leer(self) -> list[Ejecucion]:
		try:
			datos = json.loads(self.ruta.read_text(encoding="utf-8"))
		except FileNotFoundError:
			return []
		except (OSError, ValueError):
			log.warning("No se pudo leer el registro de ejecuciones", exc_info=True)
			return []
		resultado = []
		for elemento in datos.get("ejecuciones", []) if isinstance(datos, dict) else []:
			try:
				resultado.append(Ejecucion(**{k: v for k, v in elemento.items() if k in Ejecucion.__dataclass_fields__}))
			except TypeError:
				log.warning("Ejecución no válida en el registro: %r", elemento)
		return resultado

	def _escribir(self, ejecuciones: list[Ejecucion]) -> None:
		_escribir(self.ruta, {"version": 1, "ejecuciones": [asdict(e) for e in ejecuciones[-MAXIMO_REGISTRO:]]})

	def apuntar(self, ejecucion: Ejecucion) -> None:
		with self._candado:
			ejecuciones = [e for e in self.leer() if not (e.id_tarea == ejecucion.id_tarea and e.inicio == ejecucion.inicio)]
			ejecuciones.append(ejecucion)
			self._escribir(ejecuciones)

	def sin_ver(self) -> list[Ejecucion]:
		return [e for e in self.leer() if not e.visto and e.fin]

	def marcar_vistas(self) -> None:
		with self._candado:
			ejecuciones = self.leer()
			for ejecucion in ejecuciones:
				if ejecucion.fin:
					ejecucion.visto = True
			self._escribir(ejecuciones)

	def vaciar(self) -> None:
		with self._candado:
			self._escribir([])


class CapturaDecisiones(logging.Handler):
	"""Apunta en la ejecución cada decisión automática que registra el gestor de decisiones (14.6)."""

	def __init__(self, ejecucion: Ejecucion) -> None:
		super().__init__(logging.INFO)
		self.ejecucion = ejecucion

	def emit(self, registro: logging.LogRecord) -> None:
		try:
			self.ejecucion.decisiones.append(registro.getMessage())
		except Exception:  # noqa: BLE001 - un mensaje mal formado no rompe la tarea
			self.handleError(registro)


def respuestas_automaticas(tarea: Tarea, registro: logging.Logger) -> api.RespuestasAutomaticas:
	"""Lo que se responde sin preguntar a los conflictos y errores de la operación de una tarea."""
	try:
		politica = api.Politica(tarea.conflicto)
	except ValueError:
		politica = api.Politica.OMITIR
	error = api.AccionError.CANCELAR if tarea.error == "cancelar" else api.AccionError.OMITIR
	return api.RespuestasAutomaticas(conflicto=politica, error=error, registro=registro)


def codigo_de(operacion: api.Operacion) -> int:
	if operacion.estado == api.Estado.TERMINADA and not operacion.errores:
		return BIEN
	return CON_ERRORES


# ── Limpieza ─────────────────────────────────────────────────────────────────


class OperacionLimpieza(api.Operacion):
	"""Manda a la papelera los archivos de ``carpeta`` (y subcarpetas) modificados hace más de ``dias`` días.

	El envío lo hace ``OperacionEliminar`` como suboperación (papelera del
	núcleo, errores por elemento con el ``Decisor``).
	"""

	tipo = "limpieza"

	def __init__(self, carpeta: str, dias: int, resolver: Callable[[str], tuple[api.Proveedor, str]],
			ahora: Callable[[], float] = time.time) -> None:
		super().__init__()
		self.carpeta = carpeta
		self.dias = max(0, int(dias))
		self.resolver = resolver
		self._ahora = ahora
		self.enviados: list[str] = []

	def descripcion(self) -> str:
		return f"Limpiar {self.carpeta}: a la papelera lo de más de {self.dias} días"

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [("local", self.carpeta)]

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.ANALIZANDO)
		proveedor = None
		try:
			proveedor, raiz = self.resolver(self.carpeta)
			limite = self._ahora() - self.dias * 86400
			viejos: list[api.Entrada] = []
			pendientes = [raiz]
			while pendientes:
				ctx.comprobar()
				carpeta = pendientes.pop()
				contenido = self._listar(proveedor, carpeta, ctx)
				for entrada in contenido:
					if entrada.es_superior or entrada.es_enlace:
						continue
					if entrada.es_carpeta:
						pendientes.append(entrada.ruta)
					elif entrada.modificado and entrada.modificado < limite:
						viejos.append(entrada)
			self.cambiar_estado(api.Estado.EJECUTANDO)
			if viejos:
				sub = api.OperacionEliminar(proveedor, viejos, papelera=True)
				self.ejecutar_sub(sub, ctx)
				fallidos = {e.ruta for e in getattr(sub, "fallidos", [])}
				self.enviados = [e.ruta for e in viejos if e.ruta not in fallidos]
			self.historial.append(f"{len(self.enviados)} archivos a la papelera")
			self.cambiar_estado(api.Estado.TERMINADA_CON_ERRORES if self.errores else api.Estado.TERMINADA)
		except api.Cancelado:
			self.cambiar_estado(api.Estado.CANCELADA)
			raise
		except api.ErrorArchivos as error:
			self.anotar_error(self.carpeta, str(error))
			self.cambiar_estado(api.Estado.FALLIDA)
		finally:
			if proveedor is not None and proveedor.esquema != "local":
				proveedor.cerrar()

	def _listar(self, proveedor: api.Proveedor, carpeta: str, ctx: api.ContextoEjecucion) -> list[api.Entrada]:
		"""Una carpeta que no se puede leer se pregunta (en una tarea responde la respuesta automática)."""
		while True:
			try:
				return proveedor.listar(carpeta, ctx.token)
			except api.Cancelado:
				raise
			except api.ErrorArchivos as error:
				with ctx.esperando():
					respuesta = ctx.decisor.preguntar_error(self, api.PreguntaError(carpeta, str(error), self.descripcion()))
				if respuesta == api.AccionError.REINTENTAR:
					continue
				if respuesta == api.AccionError.CANCELAR:
					raise api.Cancelado() from error
				self.anotar_error(carpeta, str(error))
				return []
