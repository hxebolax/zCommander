# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Archivos comprimidos sueltos como carpeta de un solo archivo (diseño 2.0, 8.3). Sin wx.

``informe.pdf.gz`` se ve como una carpeta con ``informe.pdf`` dentro (como en
Total Commander): así se extrae, se ve o se copia con las teclas de siempre.
Si al quitar la extensión no queda nombre, el archivo se llama ``contenido``.

Motores: ``gzip``, ``bz2``, ``lzma`` (``.xz`` y ``.lzma``) y
``compression.zstd`` de Python 3.15; ``.lz``, ``.lz4`` y ``.Z`` con libarchive
(formato ``raw``). Solo lectura.

Tamaño: desconocido (−1), salvo en gzip, que lo guarda al final (ISIZE, módulo
4 GiB: si el archivo comprimido es pequeño respecto a ese tamaño se toma).

Con ``comprimidos.flujos_como_carpeta`` desactivada, la fábrica dice
``NoAdmitido`` e Intro abre el archivo con su programa (14.5).
"""

from __future__ import annotations

import builtins
import bz2
import gzip
import logging
import lzma
import os
import struct
from typing import BinaryIO

from app.services import errores
from app.services.vfs import base, resolver, rutas
from app.services.vfs.zip import BLOQUE, Indice, LecturaSegura, ProveedorComprimido, ResultadoPrueba

log = logging.getLogger(__name__)

#: Extensión → motor. Las de libarchive se registran solo si la DLL carga.
MOTORES_PYTHON = {"gz": "gzip", "bz2": "bz2", "xz": "xz", "lzma": "xz", "zst": "zstd"}
MOTORES_LIBARCHIVE = {"lz": "libarchive", "lz4": "libarchive", "z": "libarchive"}
NOMBRE_SIN_EXTENSION = "contenido"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def nombre_interior(nombre: str) -> str:
	"""«informe.pdf.gz» → «informe.pdf»; «.gz» → «contenido»."""
	raiz, punto, _extension = nombre.rpartition(".")
	return raiz if punto and raiz.strip(". ") else NOMBRE_SIN_EXTENSION


def tamano_gzip(ruta: str) -> int:
	"""ISIZE del final del gzip, o −1 si no es fiable (más de 4 GiB o varios miembros dudosos)."""
	try:
		tamano_archivo = os.path.getsize(rutas.con_prefijo_largo(ruta))
		if tamano_archivo < 18:
			return -1
		with open(rutas.con_prefijo_largo(ruta), "rb") as archivo:
			archivo.seek(-4, os.SEEK_END)
			isize = struct.unpack("<I", archivo.read(4))[0]
	except OSError:
		return -1
	# ISIZE es módulo 2^32: con un archivo comprimido de 1 GiB o más no se puede saber si dio la vuelta.
	if tamano_archivo >= 1 << 30:
		return -1
	return isize


class _FlujoLibarchive:
	"""Lectura de la única entrada de un flujo ``raw`` de libarchive (cierra el lector al cerrar)."""

	def __init__(self, ruta: str, nombre: str) -> None:
		from app.services.libarchive import lectura

		self._lector = lectura.Lector([ruta], crudo=True, nombre=nombre)
		if self._lector.siguiente() is None:
			self._lector.cerrar()
			raise base.ErrorArchivos(_("{n} está vacío o dañado.").format(n=nombre), ruta)

	def read(self, n: int = -1) -> bytes:
		if n is None or n < 0:
			partes = []
			while bloque := self._lector.leer(BLOQUE):
				partes.append(bloque)
			return b"".join(partes)
		return self._lector.leer(n) if n else b""

	def seekable(self) -> bool:
		return False

	def close(self) -> None:
		self._lector.cerrar()


class ProveedorFlujoUnico(ProveedorComprimido):
	"""Un archivo comprimido suelto visto como carpeta con un solo archivo."""

	esquema = "flujo"
	tipo_visible = "Archivo comprimido"

	def __init__(self, contenedor: base.Proveedor, ruta_archivo: str, extension: str = "") -> None:
		super().__init__(contenedor, ruta_archivo)
		self.capacidades = base.Capacidades(escribir=False)
		self.extension = (extension or resolver.extension_comprimido(contenedor.nombre(ruta_archivo)) or "").lower()
		self.motor = {**MOTORES_PYTHON, **MOTORES_LIBARCHIVE}.get(self.extension, "")
		self.interior = nombre_interior(contenedor.nombre(ruta_archivo))

	def descripcion(self) -> str:
		return _("Archivo .{e} (un solo archivo comprimido)").format(e=self.extension)

	def _cargar(self, ruta: str, indice: Indice, cancelacion) -> None:
		tamano = tamano_gzip(ruta) if self.motor == "gzip" else -1
		try:
			modificado = os.path.getmtime(rutas.con_prefijo_largo(ruta))
		except OSError:
			modificado = 0.0
		# Se comprueba que se puede empezar a descomprimir: un .gz que no lo es no se muestra como carpeta.
		with self._abrir_flujo(ruta) as flujo:
			flujo.read(1)
		indice.agregar(self.interior, False, max(0, tamano), modificado, 0, self.extension)
		if tamano < 0:
			indice.entradas[self.interior] = indice.entradas[self.interior].con(tamano=-1)

	def _abrir_flujo(self, ruta: str) -> BinaryIO:
		local = rutas.con_prefijo_largo(ruta)
		if self.motor == "gzip":
			return gzip.open(local, "rb")
		if self.motor == "bz2":
			return bz2.open(local, "rb")
		if self.motor == "xz":
			return lzma.open(local, "rb")
		if self.motor == "zstd":
			from compression import zstd

			return zstd.open(local, "rb")
		if self.motor == "libarchive":
			return _Cerrable(_FlujoLibarchive(ruta, self.nombre("")))
		raise base.NoAdmitido(_("No se puede abrir este tipo de comprimido."), ruta)

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		ruta = self._limpia(ruta)
		indice = self.indice()
		if ruta not in indice.entradas or indice.entradas[ruta].es_carpeta:
			raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=ruta), ruta)
		try:
			return LecturaSegura(self._abrir_flujo(self.archivo_local()), ruta)
		except base.ErrorArchivos:
			raise
		except OSError as error:
			raise errores.convertir(error, self.archivo_local()) from error

	def probar(self, cancelacion=None, al_avanzar=None) -> ResultadoPrueba:
		resultado = ResultadoPrueba()
		self.indice(cancelacion)
		try:
			with self.abrir_lectura(self.interior) as flujo:
				while datos := flujo.read(BLOQUE):
					base.comprobar(cancelacion)
					resultado.bytes += len(datos)
					if al_avanzar is not None:
						al_avanzar(self.interior, len(datos))
			resultado.archivos = 1
		except base.Cancelado:
			raise
		except base.ErrorArchivos as error:
			resultado.errores.append((self.interior, error.mensaje))
		return resultado

	def _clon(self) -> ProveedorFlujoUnico:
		otro = ProveedorFlujoUnico(self.contenedor[0], self.ruta_archivo, self.extension)
		otro.contenedor = self.contenedor
		with self._candado:
			otro._indice, otro._firma = self._indice, self._firma
			otro._copia_local = self._copia_local
		return otro


class _Cerrable:
	"""Da ``with`` y ``readable`` a un flujo mínimo (``LecturaSegura`` y ``_cargar`` lo usan así)."""

	def __init__(self, flujo) -> None:
		self._flujo = flujo

	def read(self, n: int = -1) -> bytes:
		return self._flujo.read(n)

	def readable(self) -> bool:
		return True

	def seekable(self) -> bool:
		return False

	def close(self) -> None:
		self._flujo.close()

	def __enter__(self):
		return self

	def __exit__(self, *_error) -> None:
		self.close()


def _fabrica(contenedor: base.Proveedor, ruta_archivo: str) -> ProveedorFlujoUnico:
	config = resolver.servicios().config
	if config is not None:
		try:
			if not config.obtener("comprimidos.flujos_como_carpeta"):
				raise base.NoAdmitido(_("Los comprimidos sueltos se abren con su programa (Preferencias, Comprimidos)."),
					ruta_archivo)
		except KeyError:
			log.debug("Sin la clave comprimidos.flujos_como_carpeta", exc_info=True)
	return ProveedorFlujoUnico(contenedor, ruta_archivo)


def registrar() -> None:
	resolver.registrar_comprimido(tuple(MOTORES_PYTHON), _fabrica)
	from app.services.libarchive import ffi

	if ffi.disponible():
		resolver.registrar_comprimido(tuple(MOTORES_LIBARCHIVE), _fabrica)
	else:
		log.info(".lz, .lz4 y .Z sueltos sin registrar: %s", ffi.causa())


registrar()
