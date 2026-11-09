# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Operación «Convertir la codificación y los fines de línea» con deshacer (sin wx).

Cada archivo se convierte así, sin dejar nunca un archivo a medias:

1. Se calcula el contenido nuevo en memoria (``conversion.convertir``).
2. Se escribe en un temporal de la misma carpeta.
3. El original pasa a su copia de respaldo (``nombre.bak`` en la misma carpeta si
   ``copia_bak``; si no, ``datos/deshacer/`` cuando está en el mismo volumen, o un
   archivo oculto junto al original cuando no lo está, porque deshacer solo
   puede renombrar dentro de un volumen).
4. El temporal toma el nombre del original.

Deshacer intercambia los dos nombres (dos pasos «renombrar», que el núcleo
deshace por un temporal) y manda a la papelera la copia que queda con el
contenido convertido, solo si nadie la ha tocado.
"""

from __future__ import annotations

import builtins
import ctypes
import logging
import os
import uuid
from collections.abc import Sequence
from pathlib import Path

from app.plugins import api

from . import conversion

log = logging.getLogger("zcplugins.zc.texto")

_OCULTO = 0x2


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _ruta_libre(ruta: str) -> str:
	"""``ruta`` si no existe; si no, «nombre.1.bak», «nombre.2.bak»..."""
	if not os.path.lexists(ruta):
		return ruta
	base, extension = os.path.splitext(ruta)
	n = 1
	while os.path.lexists(f"{base}.{n}{extension}"):
		n += 1
	return f"{base}.{n}{extension}"


def _mismo_volumen(a: str, b: str) -> bool:
	return os.path.splitdrive(os.path.abspath(a))[0].casefold() == os.path.splitdrive(os.path.abspath(b))[0].casefold()


class Respaldos:
	"""Dónde van las copias del original y cuáles hay que borrar al cerrar zCommander.

	Las de ``datos/deshacer`` y las ocultas solo sirven para deshacer en esta sesión
	(la pila de deshacer del núcleo vive en memoria), así que se borran en ``desactivar``.
	Las ``.bak`` son de la persona y se quedan.
	"""

	def __init__(self, carpeta_deshacer: Path | None) -> None:
		self.carpeta = carpeta_deshacer
		self.temporales: list[str] = []

	def ruta_para(self, original: str, copia_bak: bool) -> str:
		if copia_bak:
			return _ruta_libre(original + ".bak")
		if self.carpeta is not None and _mismo_volumen(str(self.carpeta), original):
			carpeta = self.carpeta / uuid.uuid4().hex[:12]
			carpeta.mkdir(parents=True, exist_ok=True)
			ruta = str(carpeta / os.path.basename(original))
		else:
			carpeta_original, nombre = os.path.split(original)
			ruta = _ruta_libre(os.path.join(carpeta_original, f"~{nombre}.zcdeshacer"))
		self.temporales.append(ruta)
		return ruta

	def limpiar(self) -> None:
		"""Borra las copias de esta sesión (las que deshacer ya no usará)."""
		for ruta in self.temporales:
			try:
				if os.path.lexists(ruta):
					os.chmod(ruta, 0o666)
					os.remove(ruta)
				carpeta = os.path.dirname(ruta)
				if self.carpeta is not None and Path(carpeta).parent == self.carpeta and not os.listdir(carpeta):
					os.rmdir(carpeta)
			except OSError:
				log.debug("No se pudo borrar la copia para deshacer %s", ruta, exc_info=True)
		self.temporales.clear()


def _ocultar(ruta: str) -> None:
	try:
		atributos = ctypes.windll.kernel32.GetFileAttributesW(ruta)
		if atributos != -1:
			ctypes.windll.kernel32.SetFileAttributesW(ruta, atributos | _OCULTO)
	except (AttributeError, OSError):
		log.debug("No se pudo ocultar %s", ruta, exc_info=True)


def aplicar(ruta: str, opciones: conversion.Opciones, copia_bak: bool, respaldos: Respaldos) -> list[api.Paso] | None:
	"""Convierte un archivo en disco. Devuelve los pasos para deshacer, o ``None`` si no cambia nada.

	:raises conversion.ErrorConversion: si no se puede convertir sin perder información.
	:raises OSError: si falla el disco (el original queda intacto).
	"""
	tamano = os.path.getsize(ruta)
	if tamano > conversion.TAMANO_MAXIMO:
		raise conversion.ErrorConversion(_("Es demasiado grande para convertirlo como texto"))
	with open(ruta, "rb") as archivo:
		datos = archivo.read()
	resultado = conversion.convertir(datos, opciones)
	if not resultado.hay_cambios or resultado.datos == datos:
		return None
	carpeta, nombre = os.path.split(ruta)
	temporal = os.path.join(carpeta, f"~{nombre}.{uuid.uuid4().hex[:8]}.zctmp")
	with open(temporal, "wb") as salida:
		salida.write(resultado.datos)
	respaldo = respaldos.ruta_para(ruta, copia_bak)
	try:
		os.rename(ruta, respaldo)
	except OSError:
		os.remove(temporal)
		raise
	try:
		os.rename(temporal, ruta)
	except OSError:
		# El original vuelve a su sitio: nunca queda la carpeta sin el archivo.
		os.rename(respaldo, ruta)
		os.remove(temporal)
		raise
	if not copia_bak and os.path.dirname(respaldo) == carpeta:
		_ocultar(respaldo)
	estado = os.stat(ruta)
	return [
		api.Paso("renombrar", despues=respaldo, antes=ruta),
		api.Paso("renombrar", despues=ruta, antes=respaldo),
		api.Paso("a_papelera", despues=respaldo, tamano=estado.st_size, modificado=estado.st_mtime),
	]


class OperacionConvertirTexto(api.Operacion):
	"""Convierte varios archivos de texto locales; los errores de uno no paran los demás."""

	tipo = "convertir_texto"

	def __init__(self, proveedor: api.Proveedor, rutas: Sequence[str], opciones: conversion.Opciones, copia_bak: bool,
			respaldos: Respaldos) -> None:
		super().__init__()
		self.proveedor = proveedor
		self.rutas = list(rutas)
		self.opciones = opciones
		self.copia_bak = copia_bak
		self.respaldos = respaldos
		self.convertidos = 0

	def descripcion(self) -> str:
		if len(self.rutas) == 1:
			return _("Convertir {n} a UTF-8").format(n=os.path.basename(self.rutas[0]))
		return _("Convertir {n} archivos a UTF-8").format(n=len(self.rutas))

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset(api.clave_carril(self.proveedor, ruta) for ruta in self.rutas)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return sorted({("local", os.path.dirname(r)) for r in self.rutas})

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.rutas))
		pasos: list[api.Paso] = []
		for ruta in self.rutas:
			ctx.comprobar()
			self.progresar(actual=ruta)
			try:
				nuevos = aplicar(ruta, self.opciones, self.copia_bak, self.respaldos)
			except conversion.ErrorConversion as error:
				self.anotar_error(ruta, str(error))
			except OSError as error:
				log.warning("No se pudo convertir %s", ruta, exc_info=True)
				self.anotar_error(ruta, _("No se pudo escribir: {e}").format(e=error.strerror or error))
			else:
				if nuevos is None:
					self.sumar(omitidos=1)
				else:
					pasos.extend(nuevos)
					self.convertidos += 1
			self.sumar(archivos_hechos=1)
		if pasos:
			self.deshacer = api.AccionDeshacer(self.descripcion(), pasos)
		self.cambiar_estado(api.Estado.TERMINADA_CON_ERRORES if self.errores else api.Estado.TERMINADA)

