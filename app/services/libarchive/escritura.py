# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Creación de comprimidos con libarchive (diseño 2.0, 8.2 y 8.6). Sin wx.

Formatos que crea zCommander con libarchive: ZIP cifrado con AES-256 (si no
hay 7za), ISO 9660 (con Joliet y Rock Ridge), cpio («newc»), XAR y TAR con
los filtros que Python no tiene (``.tar.lz`` y ``.tar.lz4``). Cada archivo
se escribe por bloques desde un flujo; ``archive_write_disk`` nunca se usa.

Temporales: los escritores de ISO de libarchive guardan los datos en un
temporal mientras construyen la imagen y lo piden a Windows con
``GetTempPathW``. Para que no salga de ``data`` (aplicación portable), mientras
se escribe una ISO las variables ``TMP`` y ``TEMP`` del proceso apuntan a
``data/temp`` (con un cerrojo: solo una ISO a la vez cambia el entorno).
"""

from __future__ import annotations

import builtins
import ctypes
import logging
import os
import threading
from collections.abc import Callable
from typing import BinaryIO

from app.services.libarchive import ffi
from app.services.vfs import base

log = logging.getLogger(__name__)

BLOQUE = 1024 * 1024

#: formato → (función de formato, filtro, opciones fijas).
FORMATOS: dict[str, tuple[str, str | None, str]] = {
	"zip": ("archive_write_set_format_zip", None, "zip:hdrcharset=UTF-8"),
	"7z": ("archive_write_set_format_7zip", None, ""),
	"iso": ("archive_write_set_format_iso9660", None, "iso9660:joliet,iso9660:rockridge"),
	"cpio": ("archive_write_set_format_cpio_newc", None, ""),
	"xar": ("archive_write_set_format_xar", None, ""),
	"tar.lz": ("archive_write_set_format_pax_restricted", "archive_write_add_filter_lzip", ""),
	"tar.lz4": ("archive_write_set_format_pax_restricted", "archive_write_add_filter_lz4", ""),
	"tar.zst": ("archive_write_set_format_pax_restricted", "archive_write_add_filter_zstd", ""),
}

#: Nivel de zCommander → nivel de cada filtro o formato.
_NIVELES = {
	"zip": {"sin": "zip:compression=store", "rapido": "zip:compression-level=1", "normal": "zip:compression-level=6",
		"maximo": "zip:compression-level=9"},
	"7z": {"sin": "7zip:compression=store", "rapido": "7zip:compression-level=1", "normal": "7zip:compression-level=5",
		"maximo": "7zip:compression-level=9"},
	"tar.lz": {"sin": "lzip:compression-level=0", "rapido": "lzip:compression-level=1", "normal": "lzip:compression-level=6",
		"maximo": "lzip:compression-level=9"},
	"tar.lz4": {"sin": "lz4:compression-level=1", "rapido": "lz4:compression-level=1", "normal": "lz4:compression-level=1",
		"maximo": "lz4:compression-level=9"},
	"tar.zst": {"sin": "zstd:compression-level=1", "rapido": "zstd:compression-level=1", "normal": "zstd:compression-level=3",
		"maximo": "zstd:compression-level=19"},
}

_candado_entorno = threading.Lock()


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def admite(formato: str) -> bool:
	"""¿Puede crear este formato la libarchive instalada?"""
	biblioteca = ffi.cargar()
	if biblioteca is None or formato not in FORMATOS:
		return False
	funcion, filtro, _opciones = FORMATOS[formato]
	return hasattr(biblioteca, funcion) and (filtro is None or hasattr(biblioteca, filtro))


class _TemporalesEnData:
	"""Mientras existe, ``TMP`` y ``TEMP`` del proceso apuntan a ``data/temp`` (para los temporales de libarchive)."""

	def __init__(self) -> None:
		from app.services.vfs import temporales

		_candado_entorno.acquire()
		self._antes = {clave: os.environ.get(clave) for clave in ("TMP", "TEMP")}
		carpeta = str(temporales.carpeta_temporal())
		os.environ["TMP"] = carpeta
		os.environ["TEMP"] = carpeta
		self._activo = True

	def restaurar(self) -> None:
		if not self._activo:
			return
		self._activo = False
		try:
			for clave, valor in self._antes.items():
				if valor is None:
					os.environ.pop(clave, None)
				else:
					os.environ[clave] = valor
		finally:
			_candado_entorno.release()


class EscritorArchive:
	"""Un comprimido nuevo escrito con libarchive.

	:param ruta: archivo que se crea (la operación escribe en un temporal y lo coloca al terminar).
	:param formato: clave de ``FORMATOS``.
	:param nivel: «sin», «rapido», «normal» o «maximo».
	:param contrasena: solo ZIP: cifra con AES-256.
	"""

	def __init__(self, ruta: str, formato: str, nivel: str = "normal", contrasena: str | None = None) -> None:
		biblioteca = ffi.cargar()
		if biblioteca is None:
			raise base.NoAdmitido(_("Falta libarchive para crear este formato: Opciones, Componentes externos, Restaurar."), ruta)
		if formato not in FORMATOS:
			raise ValueError(f"Formato desconocido para libarchive: {formato}")
		if contrasena and formato != "zip":
			raise base.NoAdmitido(_("libarchive solo cifra los ZIP."), ruta)
		self._l = biblioteca
		self.ruta = ruta
		self.formato = formato
		self._a: int | None = None
		self._entrada: int | None = None
		self._entorno = _TemporalesEnData() if formato == "iso" else None
		try:
			self._abrir(formato, nivel, contrasena)
		except BaseException:
			self._liberar()
			raise

	def _comprobar(self, codigo: int, que: str) -> None:
		if codigo < ffi.ARCHIVE_WARN:
			ingles = ffi.texto_error(self._l, self._a)
			log.warning("libarchive no pudo %s en %s: %s", que, self.ruta, ingles)
			raise base.ErrorArchivos(_("No se pudo crear el comprimido: {e}").format(e=ingles or que), self.ruta)
		if codigo == ffi.ARCHIVE_WARN:
			log.debug("Aviso de libarchive al %s: %s", que, ffi.texto_error(self._l, self._a))

	def _abrir(self, formato: str, nivel: str, contrasena: str | None) -> None:
		l = self._l
		funcion, filtro, fijas = FORMATOS[formato]
		self._a = l.archive_write_new()
		self._comprobar(getattr(l, funcion)(self._a), "elegir el formato")
		if filtro:
			self._comprobar(getattr(l, filtro)(self._a), "elegir la compresión")
		opciones = [o for o in (fijas, _NIVELES.get(formato, {}).get(nivel, "")) if o]
		if contrasena:
			opciones.append("zip:encryption=aes256")
		for opcion in ",".join(opciones).split(","):
			if opcion:
				self._comprobar(l.archive_write_set_options(self._a, opcion.encode("utf-8")), f"aplicar {opcion}")
		if contrasena:
			self._comprobar(l.archive_write_set_passphrase(self._a, contrasena.encode("utf-8")), "fijar la contraseña")
		if formato.startswith("tar."):
			# Sin relleno al final del último bloque: el archivo ocupa lo justo.
			l.archive_write_set_bytes_in_last_block(self._a, 1)
		self._comprobar(l.archive_write_open_filename_w(self._a, self.ruta), "crear el archivo")
		self._entrada = l.archive_entry_new()

	def _cabecera(self, nombre: str, tipo: int, tamano: int, modificado: float, permisos: int) -> None:
		l = self._l
		l.archive_entry_clear(self._entrada)
		l.archive_entry_copy_pathname_w(self._entrada, nombre)
		l.archive_entry_set_filetype(self._entrada, tipo)
		l.archive_entry_set_perm(self._entrada, permisos)
		l.archive_entry_set_size(self._entrada, max(0, tamano))
		if modificado > 0:
			l.archive_entry_set_mtime(self._entrada, int(modificado), 0)
		self._comprobar(l.archive_write_header(self._a, self._entrada), f"escribir la cabecera de {nombre}")

	def carpeta(self, nombre: str, modificado: float = 0.0) -> None:
		self._cabecera(nombre.rstrip("/") + "/" if self.formato == "zip" else nombre.rstrip("/"), ffi.AE_IFDIR, 0, modificado, 0o755)

	def archivo(self, nombre: str, tamano: int, modificado: float, flujo: BinaryIO, solo_lectura: bool = False,
			comprobar: Callable[[], None] | None = None, al_avanzar: Callable[[int], None] | None = None) -> None:
		"""Escribe un archivo de ``tamano`` bytes leídos de ``flujo`` (por bloques, con cancelación)."""
		self._cabecera(nombre, ffi.AE_IFREG, tamano, modificado, 0o444 if solo_lectura else 0o644)
		escritos = 0
		while escritos < tamano:
			if comprobar is not None:
				comprobar()
			datos = flujo.read(min(BLOQUE, tamano - escritos))
			if not datos:
				raise base.ErrorArchivos(_("{n} cambió de tamaño mientras se comprimía.").format(n=nombre), nombre)
			bufer = ctypes.create_string_buffer(datos, len(datos))
			hecho = int(self._l.archive_write_data(self._a, bufer, len(datos)))
			if hecho < 0:
				self._comprobar(hecho, f"escribir {nombre}")
			escritos += len(datos)
			if al_avanzar is not None:
				al_avanzar(len(datos))
		self._comprobar(self._l.archive_write_finish_entry(self._a), f"terminar {nombre}")

	def cerrar(self) -> None:
		"""Termina el comprimido (índice, directorio central, tabla de la ISO). Después es válido."""
		try:
			if self._a:
				self._comprobar(self._l.archive_write_close(self._a), "terminar el comprimido")
		finally:
			self._liberar()

	def _liberar(self) -> None:
		entrada, self._entrada = self._entrada, None
		if entrada:
			self._l.archive_entry_free(entrada)
		a, self._a = self._a, None
		if a:
			self._l.archive_write_free(a)
		entorno, self._entorno = self._entorno, None
		if entorno is not None:
			entorno.restaurar()
