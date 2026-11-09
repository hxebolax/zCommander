# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Operación por lotes que cambia etiquetas, con deshacer (diseño 2.0, 11.4). Sin wx.

Deshacer (API 1.1): antes de tocar un archivo se guarda una copia en
``datos/deshacer/`` del complemento (nunca en la carpeta de la persona), y la
acción de deshacer es un paso ``restaurar`` por archivo: el núcleo vuelve a poner
la copia sobre el archivo si este no ha cambiado desde entonces. Las copias solo
sirven durante la sesión (la pila de deshacer vive en memoria): se borran al
cerrar zCommander y, si quedó alguna de un cierre brusco, al activarse el
complemento. Su lista va en ``datos/deshacer/copias.json`` (también borra las
copias ocultas «.zc-deshacer-…» que dejaban las versiones anteriores). Un archivo
de más de 512 MB se cambia sin copia (no se puede deshacer) para no llenar el disco.
"""

from __future__ import annotations

import builtins
import ctypes
import json
import logging
import os
import shutil
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.plugins import api

log = logging.getLogger(__name__)

TAMANO_MAXIMO_COPIA = 512 * 1024 * 1024
#: Prefijo de las copias ocultas que dejaban las versiones anteriores en la carpeta del archivo
#: (solo para borrarlas si quedó alguna de un cierre brusco).
PREFIJO_COPIA = ".zc-deshacer-"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _nombre_libre(carpeta: str, prefijo: str, nombre: str) -> str:
	while True:
		candidato = os.path.join(carpeta, f"{prefijo}{uuid.uuid4().hex[:8]}-{nombre}")
		if not os.path.lexists(candidato):
			return candidato


class Copias:
	"""Copias de seguridad de la sesión, para deshacer, y su limpieza."""

	def __init__(self, carpeta_datos: Path) -> None:
		self._carpeta = Path(carpeta_datos) / "deshacer"
		self._archivo = self._carpeta / "copias.json"
		self._candado = threading.Lock()

	def _es_copia(self, ruta: str) -> bool:
		"""Solo se borra lo que es una copia de deshacer (las de ahora o las ocultas de antes)."""
		if os.path.basename(ruta).startswith(PREFIJO_COPIA):
			return True
		try:
			return Path(ruta).resolve().parent == self._carpeta.resolve()
		except OSError:
			return False

	def _leer(self) -> list[str]:
		try:
			datos = json.loads(self._archivo.read_text(encoding="utf-8"))
			return [str(r) for r in datos] if isinstance(datos, list) else []
		except FileNotFoundError:
			return []
		except (OSError, ValueError):
			log.warning("No se pudo leer %s", self._archivo, exc_info=True)
			return []

	def _escribir(self, rutas: list[str]) -> None:
		self._archivo.parent.mkdir(parents=True, exist_ok=True)
		temporal = self._archivo.with_name(self._archivo.name + ".tmp")
		temporal.write_text(json.dumps(rutas, ensure_ascii=False), encoding="utf-8")
		os.replace(temporal, self._archivo)

	def _anotar(self, ruta: str) -> None:
		with self._candado:
			rutas = self._leer()
			rutas.append(ruta)
			self._escribir(rutas)

	def limpiar(self) -> int:
		"""Borra las copias que queden (al cerrar o tras un cierre brusco). Devuelve cuántas borró."""
		with self._candado:
			rutas = self._leer()
			borradas = 0
			quedan = []
			for ruta in rutas:
				try:
					if os.path.lexists(ruta) and self._es_copia(ruta):
						ctypes.windll.kernel32.SetFileAttributesW(ruta, 0x80)
						os.remove(ruta)
						borradas += 1
				except OSError:
					log.warning("No se pudo borrar la copia %s", ruta, exc_info=True)
					quedan.append(ruta)
			if rutas:
				self._escribir(quedan)
			return borradas

	def aplicar(self, ruta: str, funcion: Callable[[str], None], conservar_fechas: bool) -> list[Any]:
		"""Cambia ``ruta`` con ``funcion`` y devuelve los pasos para deshacerlo (vacío si no hay copia)."""
		estado = os.stat(ruta)
		nombre = os.path.basename(ruta)
		copia = ""
		if estado.st_size <= TAMANO_MAXIMO_COPIA:
			self._carpeta.mkdir(parents=True, exist_ok=True)
			copia = _nombre_libre(str(self._carpeta), "", nombre)
			shutil.copy2(ruta, copia)
			self._anotar(copia)
		try:
			funcion(ruta)
			if conservar_fechas:
				os.utime(ruta, ns=(estado.st_atime_ns, estado.st_mtime_ns))
		except BaseException:
			if copia:
				try:
					shutil.copy2(copia, ruta)  # la copia puede estar en otra unidad: se copia, no se mueve
				except OSError:
					log.error("No se pudo devolver %s desde su copia %s", ruta, copia, exc_info=True)
			raise
		if not copia:
			log.info("%s es demasiado grande para guardar una copia: el cambio no se podrá deshacer", ruta)
			return []
		final = os.stat(ruta)
		return [api.Paso("restaurar", despues=ruta, antes=copia, tamano=final.st_size, modificado=final.st_mtime)]


class OperacionEtiquetas(api.Operacion):
	"""Aplica ``trabajos`` (ruta y función que la cambia) uno a uno, con progreso, pausa y errores por archivo."""

	tipo = "etiquetas"

	def __init__(self, descripcion: str, proveedor: Any, trabajos: list[tuple[str, Callable[[str], None]]], copias: Copias,
			conservar_fechas: bool = True, al_cambiar: Callable[[str], None] | None = None) -> None:
		super().__init__()
		self._descripcion = descripcion
		self.proveedor = proveedor
		self.trabajos = list(trabajos)
		self.copias = copias
		self.conservar_fechas = conservar_fechas
		self._al_cambiar = al_cambiar
		self.hechos: list[str] = []

	def descripcion(self) -> str:
		return self._descripcion

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset(api.clave_carril(self.proveedor, ruta) for ruta, _f in self.trabajos)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return sorted({("local", os.path.dirname(ruta)) for ruta, _f in self.trabajos})

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.trabajos))
		pasos: list[Any] = []
		omitir_todos = False
		for ruta, funcion in self.trabajos:
			ctx.comprobar()
			self.progresar(actual=os.path.basename(ruta))
			while True:
				try:
					pasos.extend(self.copias.aplicar(ruta, funcion, self.conservar_fechas))
					self.hechos.append(ruta)
					if self._al_cambiar is not None:
						self._al_cambiar(ruta)
					break
				except api.Cancelado:
					raise
				except Exception as error:  # noqa: BLE001 - cada error de un archivo se pregunta o se anota
					mensaje = getattr(error, "strerror", None) or str(error)
					if omitir_todos:
						self.anotar_error(ruta, mensaje)
						self.sumar(omitidos=1)
						break
					pregunta = api.PreguntaError(ruta, mensaje, self.descripcion(), int(getattr(error, "winerror", 0) or 0), error)
					with ctx.esperando():
						accion = ctx.decisor.preguntar_error(self, pregunta)
					if accion == api.AccionError.REINTENTAR:
						continue
					if accion == api.AccionError.CANCELAR:
						raise api.Cancelado() from error
					omitir_todos = accion == api.AccionError.OMITIR_TODOS
					self.anotar_error(ruta, mensaje)
					self.sumar(omitidos=1)
					break
			self.sumar(archivos_hechos=1)
		if pasos:
			self.deshacer = api.AccionDeshacer(self.descripcion(), pasos)


class OperacionExportar(api.Operacion):
	"""Lee las etiquetas de los archivos y escribe la lista de pistas (texto o CSV)."""

	tipo = "exportar_pistas"

	def __init__(self, proveedor: Any, rutas: list[str], destino: str, leer: Callable[[str], dict[str, str]]) -> None:
		super().__init__()
		self.proveedor = proveedor
		self.rutas = list(rutas)
		self.destino = destino
		self._leer = leer

	def descripcion(self) -> str:
		return _("Exportar la lista de pistas a {n}").format(n=os.path.basename(self.destino))

	@property
	def carriles(self) -> frozenset[str]:
		claves = {api.clave_carril(self.proveedor, r) for r in self.rutas}
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [("local", os.path.dirname(self.destino))]

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		from . import etiquetas

		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.rutas))
		filas: list[tuple[str, dict[str, str]]] = []
		for ruta in self.rutas:
			ctx.comprobar()
			self.progresar(actual=os.path.basename(ruta))
			try:
				filas.append((ruta, self._leer(ruta)))
			except Exception as error:  # noqa: BLE001 - un archivo ilegible no corta la lista
				self.anotar_error(ruta, str(error))
				filas.append((ruta, {}))
			self.sumar(archivos_hechos=1)
		texto = componer_lista(filas, csv=self.destino.lower().endswith(".csv"), duracion=etiquetas.texto_duracion)
		temporal = self.destino + ".tmp"
		with open(temporal, "w", encoding="utf-8-sig" if self.destino.lower().endswith(".csv") else "utf-8", newline="") as archivo:
			archivo.write(texto)
		os.replace(temporal, self.destino)


def componer_lista(filas: list[tuple[str, dict[str, str]]], csv: bool, duracion: Callable[[str], str]) -> str:
	"""Texto de la lista de pistas: una línea por pista o CSV con punto y coma (lo abre Excel en español)."""
	if csv:
		import csv as modulo_csv
		import io

		salida = io.StringIO()
		escritor = modulo_csv.writer(salida, delimiter=";", lineterminator="\r\n")
		escritor.writerow([_("Archivo"), _("Pista"), _("Artista"), _("Título"), _("Álbum"), _("Año"), _("Género"), _("Duración")])
		for ruta, datos in filas:
			escritor.writerow([os.path.basename(ruta), datos.get("pista", ""), datos.get("artista", ""), datos.get("titulo", ""),
				datos.get("album", ""), datos.get("anio", ""), datos.get("genero", ""), duracion(datos.get("duracion_s", ""))])
		return salida.getvalue()
	lineas = []
	for numero, (ruta, datos) in enumerate(filas, start=1):
		titulo = datos.get("titulo") or os.path.splitext(os.path.basename(ruta))[0]
		if datos.get("artista"):
			titulo = f"{datos['artista']} - {titulo}"
		tiempo = duracion(datos.get("duracion_s", ""))
		lineas.append(f"{numero}. {titulo}" + (f" ({tiempo})" if tiempo else ""))
	return "\r\n".join(lineas) + "\r\n"
