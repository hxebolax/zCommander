# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lectura de comprimidos con libarchive (diseño 2.0, 8.2). Sin wx.

``Lector`` envuelve UN objeto ``archive`` de lectura: se usa en un solo hilo
(libarchive no admite compartirlo) y se recorre en orden con ``siguiente()``;
los datos de la entrada actual se leen con ``leer()``. Nunca se usa
``archive_read_extract`` ni ``archive_write_disk``: la validación de nombres
es de zCommander (``nombre_seguro``) y quien escribe es el motor de copia.

Los mensajes de libarchive están en inglés: van al registro y la persona
recibe un ``ErrorArchivos`` en español (``traducir``).
"""

from __future__ import annotations

import builtins
import ctypes
import logging
from dataclasses import dataclass

from app.services.libarchive import ffi
from app.services.vfs import base

log = logging.getLogger(__name__)

#: Bloque de lectura de libarchive y de los datos (1 MiB, A.7).
BLOQUE = 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Errores ──────────────────────────────────────────────────────────────────


class ContrasenaNecesaria(base.ErrorAcceso):
	"""El ZIP necesita contraseña (``incorrecta``: la que se dio no vale)."""

	def __init__(self, mensaje: str, ruta: str = "", incorrecta: bool = False) -> None:
		super().__init__(mensaje, ruta)
		self.incorrecta = incorrecta


class CifradoNoAdmitido(base.ErrorAcceso):
	"""Entrada o cabeceras cifradas en un formato que libarchive no descifra (RAR, 7z)."""


def nombre_formato(formato: str) -> str:
	"""«RAR», «7z»... para los mensajes (``formato`` es el nombre de libarchive o la extensión)."""
	minusculas = (formato or "").lower()
	for clave, texto in (("rar", "RAR"), ("7-zip", "7z"), ("7z", "7z"), ("zip", "ZIP"), ("cab", "CAB")):
		if clave in minusculas:
			return texto
	return _("comprimido")


def mensaje_cifrado(formato: str) -> str:
	"""El mensaje de 8.2: nunca «contraseña incorrecta» cuando el problema es que no hay motor."""
	return _("Este {f} está cifrado. zCommander no puede descifrarlo sin 7-Zip instalado.").format(f=nombre_formato(formato))


def traducir(ingles: str, nombre: str, ruta: str = "", formato: str = "") -> base.ErrorArchivos:
	"""Error de libarchive (en inglés) convertido en uno en español; el original va al registro."""
	log.info("libarchive (%s): %s", ruta or nombre, ingles)
	texto = (ingles or "").lower()
	if "passphrase" in texto or "password" in texto:
		if "incorrect" in texto or "wrong" in texto or "invalid" in texto or "bad" in texto:
			return ContrasenaNecesaria(_("La contraseña de {n} no es correcta.").format(n=nombre), ruta, incorrecta=True)
		if "zip" in (formato or "zip").lower():
			return ContrasenaNecesaria(_("{n} está protegido con contraseña.").format(n=nombre), ruta)
		return CifradoNoAdmitido(mensaje_cifrado(formato), ruta)
	if "encrypt" in texto or "crypt" in texto:
		if "zip" in (formato or "").lower():
			return ContrasenaNecesaria(_("{n} está protegido con contraseña.").format(n=nombre), ruta)
		return CifradoNoAdmitido(mensaje_cifrado(formato), ruta)
	if "unrecognized archive format" in texto or "unrecognized" in texto:
		return base.ErrorArchivos(_("{n} no es un comprimido válido o está dañado.").format(n=nombre), ruta)
	if "truncated" in texto or "premature" in texto or "unexpected end" in texto or "eof" in texto:
		return base.ErrorArchivos(_("{n} está incompleto: falta una parte o se cortó al descargarlo.").format(n=nombre), ruta)
	if "crc" in texto or "checksum" in texto:
		return base.ErrorArchivos(_("«{n}» está dañado: la suma CRC no coincide.").format(n=nombre), ruta)
	if "unsupported" in texto or "not supported" in texto or "unknown compression" in texto:
		return base.NoAdmitido(_("«{n}» usa un método de compresión que zCommander no admite.").format(n=nombre), ruta)
	if "no such file" in texto or "cannot open" in texto or "failed to open" in texto:
		return base.NoEncontrado(_("No se puede abrir {n}.").format(n=nombre), ruta)
	return base.ErrorArchivos(_("{n} está dañado o no se puede leer.").format(n=nombre), ruta)


# ── Entradas ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Cabecera:
	"""Lo que libarchive dice de una entrada.

	:param posicion: orden en el comprimido (0, 1, 2...): identifica la entrada al volver a leer.
	:param nombre: nombre tal como viene (puede traer «\\» o «..»; se valida fuera con ``nombre_seguro``).
	:param tipo: «archivo», «carpeta», «enlace» u «otro».
	:param tamano: −1 si el formato no lo dice (flujos sueltos).
	"""

	posicion: int
	nombre: str
	tipo: str
	tamano: int
	modificado: float
	cifrado: bool
	solo_lectura: bool
	enlace_duro: str = ""


class Lector:
	"""Un comprimido abierto con libarchive para leerlo en orden.

	:param rutas: el archivo o, en un multivolumen, todas sus partes en orden.
	:param contrasenas: las que se prueban en los ZIP cifrados.
	:param crudo: flujo suelto (``.lz``, ``.lz4``, ``.Z``): formato ``raw`` con una sola entrada.
	:param opciones: opciones de lectura («zip:hdrcharset=CP850»).
	:param nombre: nombre para los mensajes.
	"""

	def __init__(self, rutas: list[str], *, contrasenas: tuple[str, ...] = (), crudo: bool = False, opciones: str = "",
			nombre: str = "") -> None:
		biblioteca = ffi.cargar()
		if biblioteca is None:
			raise base.NoAdmitido(_("Falta libarchive para abrir este comprimido: Opciones, Componentes externos, Restaurar."))
		self._l = biblioteca
		self.rutas = list(rutas)
		self.nombre = nombre or (rutas[0].replace("/", "\\").rpartition("\\")[2] if rutas else "")
		self._a: int | None = None
		self._entrada = ctypes.c_void_p()
		self._buffer = ctypes.create_string_buffer(BLOQUE)
		self.posicion = -1
		self.actual: Cabecera | None = None
		self._abrir(contrasenas, crudo, opciones)

	# Abrir y cerrar ---------------------------------------------------------

	def _abrir(self, contrasenas: tuple[str, ...], crudo: bool, opciones: str) -> None:
		l = self._l
		a = l.archive_read_new()
		if not a:
			raise base.ErrorArchivos(_("Sin memoria para abrir {n}.").format(n=self.nombre))
		self._a = a
		try:
			l.archive_read_support_filter_all(a)
			if crudo:
				l.archive_read_support_format_raw(a)
			else:
				l.archive_read_support_format_all(a)
			if opciones and l.archive_read_set_options(a, opciones.encode("utf-8")) < ffi.ARCHIVE_WARN:
				log.debug("Opciones de lectura no aplicadas (%s): %s", opciones, ffi.texto_error(l, a))
			for clave in contrasenas:
				if clave:
					l.archive_read_add_passphrase(a, clave.encode("utf-8"))
			if len(self.rutas) > 1:
				lista = (ctypes.c_wchar_p * (len(self.rutas) + 1))(*self.rutas, None)
				codigo = l.archive_read_open_filenames_w(a, lista, BLOQUE)
			else:
				codigo = l.archive_read_open_filename_w(a, self.rutas[0], BLOQUE)
			if codigo < ffi.ARCHIVE_WARN:
				raise traducir(ffi.texto_error(l, a), self.nombre, self.rutas[0], "")
		except BaseException:
			self.cerrar()
			raise

	def cerrar(self) -> None:
		a, self._a = self._a, None
		if a:
			self._l.archive_read_free(a)

	def __enter__(self) -> Lector:
		return self

	def __exit__(self, *_error) -> None:
		self.cerrar()

	def agregar_contrasena(self, clave: str) -> None:
		"""Contraseña para lo que queda por leer (libarchive la consulta al leer cada entrada cifrada)."""
		if self._a and clave:
			self._l.archive_read_add_passphrase(self._a, clave.encode("utf-8"))

	# Consultas ----------------------------------------------------------------

	def formato(self) -> str:
		"""Nombre del formato según libarchive («RAR5», «ZIP 2.0 (deflation)», «ISO9660»...)."""
		if not self._a:
			return ""
		valor = self._l.archive_format_name(self._a)
		return valor.decode("utf-8", "replace") if valor else ""

	def bytes_comprimidos(self) -> int:
		"""Bytes del comprimido consumidos hasta ahora (para el progreso)."""
		return int(self._l.archive_filter_bytes(self._a, -1)) if self._a else 0

	def hay_cifradas(self) -> int:
		"""1 sí, 0 no, negativo: no se sabe todavía o el formato no lo dice."""
		return int(self._l.archive_read_has_encrypted_entries(self._a)) if self._a else -1

	def _error(self) -> base.ErrorArchivos:
		return traducir(ffi.texto_error(self._l, self._a), self.nombre, self.rutas[0] if self.rutas else "", self.formato())

	# Recorrido ----------------------------------------------------------------

	def siguiente(self) -> Cabecera | None:
		"""La entrada siguiente (salta los datos que no se leyeron de la anterior), o ``None`` al final."""
		if not self._a:
			return None
		l = self._l
		while True:
			codigo = l.archive_read_next_header(self._a, ctypes.byref(self._entrada))
			if codigo == ffi.ARCHIVE_EOF:
				self.actual = None
				return None
			if codigo == ffi.ARCHIVE_RETRY:
				continue
			if codigo == ffi.ARCHIVE_WARN:
				log.debug("Aviso de libarchive en %s: %s", self.nombre, ffi.texto_error(l, self._a))
			elif codigo < ffi.ARCHIVE_WARN:
				raise self._error()
			break
		self.posicion += 1
		self.actual = self._cabecera(self._entrada.value)
		return self.actual

	def _cabecera(self, entrada: int) -> Cabecera:
		l = self._l
		nombre = l.archive_entry_pathname_w(entrada)
		if nombre is None:
			crudo = l.archive_entry_pathname(entrada)
			nombre = crudo.decode("utf-8", "replace") if crudo else ""
		tipo_bits = int(l.archive_entry_filetype(entrada)) & ffi.AE_IFMT
		enlace = l.archive_entry_hardlink_w(entrada) or ""
		if enlace:
			tipo = "enlace"
		elif tipo_bits == ffi.AE_IFDIR:
			tipo = "carpeta"
		elif tipo_bits == ffi.AE_IFREG or tipo_bits == 0:
			tipo = "archivo"
		elif tipo_bits == ffi.AE_IFLNK:
			tipo = "enlace"
		else:
			tipo = "otro"
		tamano = int(l.archive_entry_size(entrada)) if l.archive_entry_size_is_set(entrada) else -1
		modificado = float(l.archive_entry_mtime(entrada)) if l.archive_entry_mtime_is_set(entrada) else 0.0
		cifrado = bool(l.archive_entry_is_data_encrypted(entrada))
		permisos = int(l.archive_entry_perm(entrada))
		solo_lectura = bool(permisos) and not (permisos & 0o200)
		return Cabecera(self.posicion, nombre, tipo, tamano, modificado, cifrado, solo_lectura, enlace)

	def leer(self, maximo: int = BLOQUE) -> bytes:
		"""Hasta ``maximo`` bytes de la entrada actual; ``b""`` al terminarla."""
		if not self._a:
			return b""
		maximo = max(1, min(maximo, BLOQUE))
		while True:
			leidos = int(self._l.archive_read_data(self._a, self._buffer, maximo))
			if leidos == ffi.ARCHIVE_RETRY:
				continue
			if leidos < 0:
				raise self._error()
			return self._buffer.raw[:leidos]



class FlujoEntrada:
	"""Lectura de la entrada actual de un ``Lector`` con la interfaz de un flujo (para ``materializar``)."""

	def __init__(self, lector: Lector) -> None:
		self._lector = lector

	def read(self, n: int = -1) -> bytes:
		return self._lector.leer(BLOQUE if n is None or n < 0 else n)
