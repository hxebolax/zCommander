# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""``OperacionFFmpeg``: conversiones como operaciones del motor (diseño 2.0, 11.6). Sin wx.

- Progreso real: ``-progress pipe:1`` (``out_time_us``) frente a la duración de
  ``ffprobe``; el porcentaje global se lleva en bytes de entrada (lo ya
  convertido de cada archivo según su tiempo), así la velocidad y el tiempo
  restante tienen sentido.
- Pausa entre archivos y cancelación: cancelar termina el árbol del proceso
  (Job Object de ``zc.ejecutar_programa``) y borra el archivo a medias.
- La salida se escribe en un temporal de la carpeta de destino y se renombra al
  terminar. Nunca se sobrescribe el original: si el destino coincide con él, se
  usa «nombre (2)». Si el destino ya existe, manda la política elegida
  (preguntar, cambiar el nombre, omitir o sobrescribir).
- Errores por archivo con la última línea de ``stderr`` traducida; se pregunta
  con el ``Decisor`` (reintentar, omitir, cancelar).
"""

from __future__ import annotations

import builtins
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.plugins import api

from . import sonda

log = logging.getLogger(__name__)

#: Tope de una conversión (un vídeo largo en un equipo lento puede tardar horas).
TIEMPO_MAXIMO_S = 24 * 3600.0


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class Trabajo:
	"""Un archivo de salida.

	:param alternativas: funciones que reciben la ruta temporal y devuelven los argumentos;
		se prueban en orden hasta que una funciona (copiar el flujo y, si no se puede, convertir).
	:param preparar: opcional; se llama (con el contexto de ejecución) en el hilo de la operación antes de convertir y devuelve
		las alternativas definitivas (la primera pasada de ``loudnorm``).
	"""

	origen: str
	destino: str
	alternativas: list[Callable[[str], list[str]]]
	duracion: float = 0.0
	tamano: int = 0
	preparar: Callable[[Any], list[Callable[[str], list[str]]]] | None = None
	temporales: list[str] = field(default_factory=list)


def _borrar(ruta: str) -> None:
	try:
		if os.path.lexists(ruta):
			os.remove(ruta)
	except OSError:
		log.warning("No se pudo borrar %s", ruta, exc_info=True)


def nombre_libre(ruta: str) -> str:
	"""«nombre (2).ext», «nombre (3).ext»... el primero que no exista."""
	base, extension = os.path.splitext(ruta)
	n = 2
	while os.path.lexists(f"{base} ({n}){extension}"):
		n += 1
	return f"{base} ({n}){extension}"


class OperacionFFmpeg(api.Operacion):
	tipo = "ffmpeg"
	admite_pausa = True

	def __init__(self, descripcion: str, proveedor: Any, trabajos: list[Trabajo], *, ejecutar: Callable[..., Any],
			duracion_de: Callable[[str], float], politica: api.Politica = api.Politica.PREGUNTAR,
			conservar_fechas: bool = False) -> None:
		super().__init__()
		self._descripcion = descripcion
		self.proveedor = proveedor
		self.trabajos = list(trabajos)
		self._ejecutar = ejecutar
		self._duracion_de = duracion_de
		self.politica = api.Politica(politica)
		self.conservar_fechas = conservar_fechas
		self.creados: list[str] = []

	def descripcion(self) -> str:
		return self._descripcion

	@property
	def carriles(self) -> frozenset[str]:
		claves: set[str] = set()
		for trabajo in self.trabajos:
			claves.add(api.clave_carril(self.proveedor, trabajo.origen))
			claves.add(api.clave_carril(self.proveedor, os.path.dirname(trabajo.destino) or trabajo.destino))
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return sorted({("local", os.path.dirname(t.destino)) for t in self.trabajos})

	def resumen(self) -> str:
		texto = super().resumen()
		if len(self.creados) == 1:
			texto += ". " + _("Creado {n}").format(n=os.path.basename(self.creados[0]))
		return texto

	# ── Ejecución ────────────────────────────────────────────────────────────

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.ANALIZANDO)
		for trabajo in self.trabajos:
			ctx.comprobar()
			if not trabajo.tamano:
				try:
					trabajo.tamano = os.path.getsize(trabajo.origen)
				except OSError:
					trabajo.tamano = 0
			if trabajo.duracion == 0:
				try:
					trabajo.duracion = float(self._duracion_de(trabajo.origen) or 0)
				except Exception:  # noqa: BLE001 - sin duración solo se pierde el porcentaje
					log.debug("Sin duración para %s", trabajo.origen, exc_info=True)
		self.progresar(archivos_total=len(self.trabajos), bytes_total=sum(t.tamano for t in self.trabajos))
		self.cambiar_estado(api.Estado.EJECUTANDO)
		hechos = 0
		omitir_errores = False
		try:
			for trabajo in self.trabajos:
				ctx.comprobar()
				self.progresar(actual=os.path.basename(trabajo.origen), bytes_actual=0, total_actual=trabajo.tamano)
				destino = self._resolver_destino(ctx, trabajo)
				if destino is not None:
					ok, omitir_errores = self._convertir(ctx, trabajo, destino, hechos, omitir_errores)
					if ok:
						self.creados.append(destino)
				else:
					self.sumar(omitidos=1)
				hechos += trabajo.tamano
				self.sumar(archivos_hechos=1)
				self.progresar(bytes_hechos=hechos)
		finally:
			for trabajo in self.trabajos:
				for temporal in trabajo.temporales:
					_borrar(temporal)

	def _resolver_destino(self, ctx: api.ContextoEjecucion, trabajo: Trabajo) -> str | None:
		destino = trabajo.destino
		if os.path.normcase(os.path.abspath(destino)) == os.path.normcase(os.path.abspath(trabajo.origen)):
			destino = nombre_libre(destino)
		if not os.path.lexists(destino):
			return destino
		politica = self.politica
		if politica == api.Politica.PREGUNTAR:
			opciones = [_("&Sobrescribir"), _("Cambiar el &nombre"), _("&Omitir"), _("&Cancelar")]
			with ctx.esperando():
				eleccion = ctx.decisor.elegir(_("Ya existe"), _("Ya existe {n}. ¿Qué quiere hacer?").format(n=os.path.basename(destino)),
					opciones, predeterminada=1, escape=3, operacion=self)
			if eleccion not in (0, 1, 2):
				raise api.Cancelado()
			politica = (api.Politica.SOBRESCRIBIR, api.Politica.RENOMBRAR_COPIA, api.Politica.OMITIR)[eleccion]
		if politica == api.Politica.OMITIR:
			return None
		if politica == api.Politica.SOBRESCRIBIR:
			return destino
		return nombre_libre(destino)

	def _temporal(self, destino: str) -> str:
		carpeta, nombre = os.path.split(destino)
		base, extension = os.path.splitext(nombre)
		return os.path.join(carpeta, f"{base}.zcparcial-{uuid.uuid4().hex[:8]}{extension}")

	def _convertir(self, ctx: api.ContextoEjecucion, trabajo: Trabajo, destino: str, hechos: int,
			omitir_errores: bool) -> tuple[bool, bool]:
		os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
		while True:
			temporal = self._temporal(destino)
			try:
				alternativas = trabajo.preparar(ctx) if trabajo.preparar is not None else trabajo.alternativas
				mensaje = self._probar(ctx, trabajo, alternativas, temporal, hechos)
			except api.Cancelado:
				_borrar(temporal)
				raise
			except (ValueError, OSError, api.ErrorArchivos) as error:
				_borrar(temporal)
				mensaje = getattr(error, "strerror", None) or str(error)
			if mensaje is None:
				try:
					os.replace(temporal, destino)
					if self.conservar_fechas:
						estado = os.stat(trabajo.origen)
						os.utime(destino, ns=(estado.st_atime_ns, estado.st_mtime_ns))
				except OSError as error:
					_borrar(temporal)
					mensaje = error.strerror or str(error)
				else:
					return True, omitir_errores
			if omitir_errores:
				self.anotar_error(trabajo.origen, mensaje)
				return False, True
			pregunta = api.PreguntaError(trabajo.origen, mensaje, self.descripcion())
			with ctx.esperando():
				accion = ctx.decisor.preguntar_error(self, pregunta)
			if accion == api.AccionError.REINTENTAR:
				continue
			if accion == api.AccionError.CANCELAR:
				raise api.Cancelado()
			self.anotar_error(trabajo.origen, mensaje)
			return False, accion == api.AccionError.OMITIR_TODOS

	def _probar(self, ctx: api.ContextoEjecucion, trabajo: Trabajo, alternativas: list[Callable[[str], list[str]]],
			temporal: str, hechos: int) -> str | None:
		"""Prueba las alternativas en orden; ``None`` si una funcionó, o el mensaje de error de la última."""
		mensaje = _("No hay nada que ejecutar")
		for numero, alternativa in enumerate(alternativas):
			ctx.comprobar()
			analizador = sonda.AnalizadorProgreso(trabajo.duracion)

			def al_leer(datos: bytes, analizador: sonda.AnalizadorProgreso = analizador) -> None:
				analizador.alimentar(datos)
				parte = int(trabajo.tamano * analizador.fraccion)
				self.progresar(bytes_actual=parte, bytes_hechos=hechos + parte)

			resultado = self._ejecutar(alternativa(temporal), tiempo_s=TIEMPO_MAXIMO_S, cancelacion=ctx.cancelado, al_leer=al_leer)
			if getattr(resultado, "cancelado", False) or ctx.cancelado():
				_borrar(temporal)
				raise api.Cancelado()
			if resultado.codigo == 0 and os.path.isfile(temporal):
				return None
			_borrar(temporal)
			mensaje = sonda.traducir_error(resultado.errores)
			if numero + 1 < len(alternativas):
				log.info("FFmpeg falló con %s (%s); se prueba la siguiente forma", trabajo.origen, mensaje)
		return mensaje
