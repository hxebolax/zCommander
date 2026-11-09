# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Operaciones por lotes de imágenes: convertir, redimensionar y girar, y quitar el GPS (diseño 2.0, 11.11).

Las dos escriben en un temporal de la carpeta de destino y lo renombran al
terminar; preguntan por cada error con el ``Decisor`` y respetan la pausa y la
cancelación entre archivos. Convertir nunca sobrescribe el original.
"""

from __future__ import annotations

import builtins
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.plugins import api

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def nombre_libre(ruta: str) -> str:
	base, extension = os.path.splitext(ruta)
	n = 2
	while os.path.lexists(f"{base} ({n}){extension}"):
		n += 1
	return f"{base} ({n}){extension}"


def _borrar(ruta: str) -> None:
	try:
		if os.path.lexists(ruta):
			os.remove(ruta)
	except OSError:
		log.warning("No se pudo borrar %s", ruta, exc_info=True)


def _temporal(destino: str) -> str:
	carpeta, nombre = os.path.split(destino)
	base, extension = os.path.splitext(nombre)
	return os.path.join(carpeta, f"{base}.zcparcial-{uuid.uuid4().hex[:8]}{extension}")


@dataclass(frozen=True)
class OpcionesConversion:
	formato: str = ""            # "" = el del original
	ancho_maximo: int = 0
	alto_maximo: int = 0
	giro: int = 0                # 0, 90, 180 o 270 (270 = 90 a la izquierda)
	calidad: int = 90
	politica: str = "preguntar"


class _Base(api.Operacion):
	def __init__(self, descripcion: str, proveedor: Any, trabajos: list[tuple[str, str]]) -> None:
		super().__init__()
		self._descripcion = descripcion
		self.proveedor = proveedor
		self.trabajos = list(trabajos)
		self.creados: list[str] = []

	def descripcion(self) -> str:
		return self._descripcion

	@property
	def carriles(self) -> frozenset[str]:
		claves: set[str] = set()
		for origen, destino in self.trabajos:
			claves.add(api.clave_carril(self.proveedor, origen))
			claves.add(api.clave_carril(self.proveedor, os.path.dirname(destino) or destino))
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return sorted({("local", os.path.dirname(d)) for _o, d in self.trabajos})

	def _uno(self, ctx: api.ContextoEjecucion, origen: str, hacer: Callable[[], None], omitir: list[bool]) -> None:
		"""Hace un archivo; si falla, pregunta (reintentar, omitir, omitir todos, cancelar)."""
		while True:
			try:
				hacer()
				return
			except api.Cancelado:
				raise
			except Exception as error:  # noqa: BLE001 - cada error de un archivo se pregunta o se anota
				mensaje = getattr(error, "strerror", None) or str(error)
				if omitir[0]:
					self.anotar_error(origen, mensaje)
					self.sumar(omitidos=1)
					return
				pregunta = api.PreguntaError(origen, mensaje, self.descripcion(), int(getattr(error, "winerror", 0) or 0), error)
				with ctx.esperando():
					accion = ctx.decisor.preguntar_error(self, pregunta)
				if accion == api.AccionError.REINTENTAR:
					continue
				if accion == api.AccionError.CANCELAR:
					raise api.Cancelado() from error
				omitir[0] = accion == api.AccionError.OMITIR_TODOS
				self.anotar_error(origen, mensaje)
				self.sumar(omitidos=1)
				return


class OperacionConvertir(_Base):
	tipo = "convertir_imagenes"

	def __init__(self, descripcion: str, proveedor: Any, trabajos: list[tuple[str, str]], opciones: OpcionesConversion,
			orientacion_de: Callable[[str], int] | None = None) -> None:
		super().__init__(descripcion, proveedor, trabajos)
		self.opciones = opciones
		self._orientacion_de = orientacion_de

	def _destino(self, ctx: api.ContextoEjecucion, origen: str, destino: str) -> str | None:
		if os.path.normcase(os.path.abspath(destino)) == os.path.normcase(os.path.abspath(origen)):
			destino = nombre_libre(destino)
		if not os.path.lexists(destino):
			return destino
		politica = self.opciones.politica
		if politica == "preguntar":
			with ctx.esperando():
				eleccion = ctx.decisor.elegir(_("Ya existe"), _("Ya existe {n}. ¿Qué quiere hacer?").format(n=os.path.basename(destino)),
					[_("&Sobrescribir"), _("Cambiar el &nombre"), _("&Omitir"), _("&Cancelar")], predeterminada=1, escape=3, operacion=self)
			if eleccion not in (0, 1, 2):
				raise api.Cancelado()
			politica = ("sobrescribir", "renombrar_copia", "omitir")[eleccion]
		if politica == "omitir":
			return None
		return destino if politica == "sobrescribir" else nombre_libre(destino)

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		from . import procesado

		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.trabajos))
		omitir = [False]
		for origen, destino_pedido in self.trabajos:
			ctx.comprobar()
			self.progresar(actual=os.path.basename(origen))
			destino = self._destino(ctx, origen, destino_pedido)
			if destino is None:
				self.sumar(omitidos=1, archivos_hechos=1)
				continue

			def hacer(origen: str = origen, destino: str = destino) -> None:
				imagen = procesado.cargar(origen)
				if self._orientacion_de is not None:
					imagen = procesado.orientar(imagen, self._orientacion_de(origen))
				imagen = procesado.girar(imagen, self.opciones.giro)
				imagen = procesado.ajustar(imagen, self.opciones.ancho_maximo, self.opciones.alto_maximo)
				formato = self.opciones.formato or procesado.POR_EXTENSION.get(os.path.splitext(origen)[1].lower(), "png")
				temporal = _temporal(destino)
				try:
					procesado.guardar(imagen, temporal, formato, self.opciones.calidad)
					os.replace(temporal, destino)
				except BaseException:
					_borrar(temporal)
					raise
				self.creados.append(destino)

			self._uno(ctx, origen, hacer, omitir)
			self.sumar(archivos_hechos=1)


class OperacionQuitarGps(_Base):
	"""Quita la ubicación de las fotos JPEG en su sitio (conservando la fecha), sin recomprimirlas."""

	tipo = "quitar_gps"

	def __init__(self, descripcion: str, proveedor: Any, rutas: list[str]) -> None:
		super().__init__(descripcion, proveedor, [(r, r) for r in rutas])
		self.sin_gps = 0

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		from . import exif

		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.trabajos))
		omitir = [False]
		for ruta, _destino in self.trabajos:
			ctx.comprobar()
			self.progresar(actual=os.path.basename(ruta))

			def hacer(ruta: str = ruta) -> None:
				with open(ruta, "rb") as archivo:
					datos = archivo.read()
				nuevos = exif.quitar_gps(datos)
				if nuevos is None:
					self.sin_gps += 1
					return
				estado = os.stat(ruta)
				temporal = _temporal(ruta)
				try:
					with open(temporal, "wb") as archivo:
						archivo.write(nuevos)
					os.utime(temporal, ns=(estado.st_atime_ns, estado.st_mtime_ns))
					os.replace(temporal, ruta)
				except BaseException:
					_borrar(temporal)
					raise
				self.creados.append(ruta)

			self._uno(ctx, ruta, hacer, omitir)
			self.sumar(archivos_hechos=1)

	def resumen(self) -> str:
		texto = super().resumen()
		if self.sin_gps:
			texto += ". " + _("{n} no tenían ubicación").format(n=self.sin_gps)
		return texto
