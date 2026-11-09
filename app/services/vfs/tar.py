# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor de archivos TAR (también .tar.gz, .tgz, .tar.bz2, .tar.xz y, desde la 2.0, .tar.zst), solo de lectura.

2.0 (8.1): ``.tar.zst`` y ``.tzst`` con el ``tarfile`` de Python 3.15 (``r:*``
reconoce Zstandard). Los ``.tar.lz``, ``.tar.lz4``, ``.tar.lzma`` y ``.tar.Z``
los abre libarchive (``vfs/libarchive.py``).

Por qué solo lectura como carpeta: un TAR comprimido no se puede modificar sin
reescribirlo entero; para añadir se usa Comprimir (sección 8.15).

Seguridad: cada miembro pasa por la validación común (``nombre_seguro``) y por
``tarfile.data_filter``, el mismo filtro que ``extract(filter='data')``:
rechaza rutas absolutas, «..», enlaces que salen del árbol y archivos de
dispositivo. Nunca se usa la extracción de ``tarfile``: se lee miembro a
miembro y lo escribe el motor de copia. Los enlaces simbólicos no se muestran
(en Windows no se podrían recrear sin privilegios y podrían apuntar fuera);
los enlaces duros se leen como el archivo al que apuntan.

Lectura: el TAR queda abierto unos segundos tras cada uso (``Ocioso``) para
que extraer muchos miembros de un ``.tar.gz`` no lo descomprima desde el
principio cada vez; el índice conserva el orden del archivo, que es el que
sigue la copia y el más rápido de leer.
"""

from __future__ import annotations

import builtins
import logging
import lzma
import os
import tarfile
import zlib
from compression import zstd
from typing import BinaryIO

from app.services import errores
from app.services.vfs import base, resolver, rutas
from app.services.vfs.zip import Indice, Ocioso, ProveedorComprimido, materializar, nombre_seguro

log = logging.getLogger(__name__)

EXTENSIONES = ("tar", "tar.gz", "tgz", "tar.bz2", "tbz2", "tbz", "tar.xz", "txz", "tar.zst", "tzst")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Carpeta ficticia para ``data_filter``: solo sirve para calcular si un nombre sale del árbol.
_DESTINO_FICTICIO = os.path.abspath(os.sep + "zcommander-filtro-tar")


def miembro_admitido(miembro: tarfile.TarInfo) -> str | None:
	"""Ruta interna del miembro, o ``None`` si se omite (peligroso o de un tipo no admitido)."""
	nombre = nombre_seguro(miembro.name)
	if not nombre:
		return None
	if not (miembro.isdir() or miembro.isreg() or miembro.islnk()):
		return None
	try:
		tarfile.data_filter(miembro, _DESTINO_FICTICIO)
	except tarfile.FilterError:
		return None
	return nombre


class ProveedorTar(ProveedorComprimido):
	"""Archivo TAR como carpeta de solo lectura."""

	esquema = "tar"
	tipo_visible = "Archivo TAR"

	def __init__(self, contenedor: base.Proveedor, ruta_archivo: str) -> None:
		super().__init__(contenedor, ruta_archivo)
		self.capacidades = base.Capacidades(escribir=False)
		self._abierto: Ocioso | None = None

	def descripcion(self) -> str:
		return _("Archivo TAR")

	def _cargar(self, ruta: str, indice: Indice, cancelacion) -> None:
		tamanos: dict[str, int] = {}
		with tarfile.open(rutas.con_prefijo_largo(ruta), "r:*") as archivo:
			for i, miembro in enumerate(archivo):
				if i % 128 == 0:
					base.comprobar(cancelacion)
				nombre = miembro_admitido(miembro)
				if nombre is None:
					if miembro.name.strip("./"):
						indice.omitidas.append(miembro.name)
					continue
				if miembro.isdir():
					indice.agregar(nombre, True, modificado=float(miembro.mtime), dato=miembro)
					continue
				tamano = miembro.size
				if miembro.islnk():
					destino = nombre_seguro(miembro.linkname)
					if not destino or destino not in tamanos:
						indice.omitidas.append(miembro.name)
						continue
					tamano = tamanos[destino]
				tamanos[nombre] = tamano
				solo_lectura = 0x1 if not (miembro.mode & 0o200) else 0
				indice.agregar(nombre, False, tamano, float(miembro.mtime), solo_lectura, miembro)

	def _archivo(self) -> Ocioso:
		with self._candado:
			if self._abierto is None:
				self._abierto = Ocioso(lambda: tarfile.open(rutas.con_prefijo_largo(self.archivo_local()), "r:*"),
					lambda t: t.close(), clave=self.archivo_local())
			return self._abierto

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		ruta = self._limpia(ruta)
		indice = self.indice()
		entrada = indice.entradas.get(ruta)
		if entrada is None:
			raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=ruta), ruta)
		if entrada.es_carpeta:
			raise base.ErrorAcceso(_("«{r}» es una carpeta.").format(r=ruta), ruta)
		miembro = indice.datos[ruta]
		try:
			with self._archivo().usar() as archivo:
				flujo = archivo.extractfile(miembro)
				if flujo is None:
					raise base.NoAdmitido(_("«{r}» no es un archivo normal.").format(r=ruta), ruta)
				with flujo:
					return materializar(flujo, ruta, entrada.tamano)
		except (base.ErrorArchivos, base.Cancelado):
			raise
		except (tarfile.TarError, EOFError, zlib.error, lzma.LZMAError, zstd.ZstdError) as error:
			raise base.ErrorArchivos(_("«{n}» está dañado dentro del comprimido.").format(n=ruta), ruta) from error
		except OSError as error:
			if error.errno is None and getattr(error, "winerror", None) is None:
				# gzip y bz2 avisan de datos dañados con un OSError sin código.
				raise base.ErrorArchivos(_("«{n}» está dañado dentro del comprimido.").format(n=ruta), ruta) from error
			raise errores.convertir(error, ruta) from error

	def cerrar(self) -> None:
		with self._candado:
			abierto, self._abierto = self._abierto, None
		if abierto is not None:
			abierto.cerrar()
		super().cerrar()


def _fabrica(contenedor: base.Proveedor, ruta_archivo: str) -> ProveedorTar:
	return ProveedorTar(contenedor, ruta_archivo)


resolver.registrar_comprimido(EXTENSIONES, _fabrica)
