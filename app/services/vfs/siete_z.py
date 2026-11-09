# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor de archivos 7z con py7zr 0.11.3, solo de lectura.

py7zr 0.11.3 es la versión que hay para Python 3.15 y su extracción en bloque
no valida bien los nombres (sección 14). Por eso aquí NUNCA se usa
``extract``/``extractall``: cada miembro se descomprime a una ruta elegida por
zCommander (un temporal de ``data/temp`` con nombre propio) registrándolo en el
``worker`` de py7zr, y los nombres del índice pasan la validación común.

Cada extracción abre el 7z de nuevo: el ``worker`` de py7zr guarda estado y
reutilizarlo tras una lectura deja colgada la siguiente (comprobado con 0.11.3).

7z sólidos: para leer un miembro hay que descomprimir su bloque desde el
principio. Al extraer uno se guardan también en temporales los anteriores del
mismo bloque que aún no se han leído (hasta ``LIMITE_PREVIO``), porque el
motor de copia recorre las carpetas en un orden distinto al del bloque (7-Zip
agrupa por extensión) y así cada bloque se descomprime casi una sola vez.

Contraseñas: si el índice o los datos van cifrados se pide con el ``Decisor``;
una contraseña incorrecta se detecta por el error de descompresión o de CRC.

2.0 (8.1): si py7zr no admite el método (BCJ2, ARM64, Zstandard...), el 7z se
lee con una **reserva**: libarchive si no está cifrado; si lo está, el 7za de
zCommander o el 7-Zip de la persona (libarchive no descifra 7z).
"""

from __future__ import annotations

import builtins
import io
import logging
import lzma
import pathlib
from collections.abc import Callable
from typing import BinaryIO

from app.services.vfs import base, resolver, rutas, temporales
from app.services.vfs.zip import Indice, ProveedorComprimido, ResultadoPrueba, UsarReserva, lectura_temporal, nombre_seguro

log = logging.getLogger(__name__)

#: Bytes de miembros anteriores del mismo bloque que se guardan de paso al extraer uno.
LIMITE_PREVIO = 256 * 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _py7zr():
	"""py7zr se importa al usarlo por primera vez (sección 13: arranque rápido)."""
	import py7zr

	return py7zr


class _Miembro:
	"""Lo que el índice recuerda de cada archivo del 7z."""

	__slots__ = ("bloque", "identificador", "tamano", "vacio")

	def __init__(self, identificador: int, bloque: int | None, tamano: int, vacio: bool) -> None:
		self.identificador = identificador
		self.bloque = bloque
		self.tamano = tamano
		self.vacio = vacio


class ProveedorSieteZ(ProveedorComprimido):
	"""Archivo 7z como carpeta de solo lectura."""

	esquema = "7z"
	tipo_visible = "Archivo 7z"

	def __init__(self, contenedor: base.Proveedor, ruta_archivo: str) -> None:
		super().__init__(contenedor, ruta_archivo)
		self.capacidades = base.Capacidades(escribir=False)
		#: Miembros ya descomprimidos de paso (identificador → temporal); se borran al leerlos o al cerrar.
		self._previos: dict[int, str] = {}

	def descripcion(self) -> str:
		return _("Archivo 7z")

	# Abrir con contraseña ---------------------------------------------------------

	def _errores_de_clave(self) -> tuple[type[BaseException], ...]:
		py7zr = _py7zr()
		return (lzma.LZMAError, py7zr.exceptions.Bad7zFile, py7zr.exceptions.CrcError, py7zr.exceptions.DecompressionError)

	def _con_7z(self, accion: Callable[[object], object]) -> object:
		"""Abre el 7z (preguntando la contraseña si hace falta) y ejecuta ``accion(archivo)``.

		Si falla por falta de contraseña o porque la dada no es correcta, la pide
		y vuelve a empezar (hasta cuatro veces).
		"""
		py7zr = _py7zr()
		ruta = rutas.con_prefijo_largo(self.archivo_local())
		incorrecta = False
		for _intento in range(4):
			try:
				with py7zr.SevenZipFile(ruta, "r", password=self._contrasena) as archivo:
					return accion(archivo)
			except py7zr.exceptions.PasswordRequired:
				self.pedir_contrasena(incorrecta)
			except self._errores_de_clave() as error:
				if self._contrasena is None:
					raise
				log.info("Fallo al descomprimir %s con contraseña: %s", ruta, error)
				incorrecta = True
				self.pedir_contrasena(True)
		raise base.ErrorAcceso(_("La contraseña de {n} no es correcta.").format(n=self.nombre("")), self.ruta_archivo)

	# Reserva (2.0, 8.1) ----------------------------------------------------------

	def _cifrado(self) -> bool:
		if self._contrasena is not None:
			return True
		try:
			with _py7zr().SevenZipFile(rutas.con_prefijo_largo(self.archivo_local()), "r") as archivo:
				return bool(archivo.needs_password())
		except Exception:  # noqa: BLE001 - si ni siquiera se abre, se trata como cifrado (lo descifra 7-Zip)
			log.debug("No se pudo saber si %s está cifrado", self.archivo_local(), exc_info=True)
			return True

	def _reserva_por_metodo(self) -> ProveedorComprimido:
		"""py7zr no admite el método: libarchive (sin cifrar) o un 7-Zip de consola (cifrado)."""
		from app.services.vfs import libarchive, siete_zip_instalado

		if self._reserva is not None:
			return self._reserva
		cifrado = self._cifrado()
		if not cifrado and libarchive.disponible():
			from app.services.vfs.libarchive import ProveedorLibarchive

			return self.usar_reserva(ProveedorLibarchive(self.contenedor[0], self.ruta_archivo, "7z"))
		motor = siete_zip_instalado.motor_lectura("7z")
		if motor is not None:
			return self.usar_reserva(siete_zip_instalado.ProveedorSieteZipExterno(self.contenedor[0], self.ruta_archivo, motor, "7z"))
		if libarchive.disponible():
			# Cifrado y sin ningún 7-Zip: libarchive lo lista y explica que no puede descifrarlo.
			from app.services.vfs.libarchive import ProveedorLibarchive

			return self.usar_reserva(ProveedorLibarchive(self.contenedor[0], self.ruta_archivo, "7z"))
		raise base.NoAdmitido(_("{n} usa un método de compresión que zCommander no admite sin 7-Zip.").format(
			n=self.nombre("")), self.ruta_archivo)

	# Índice ------------------------------------------------------------------------

	def _cargar(self, ruta: str, indice: Indice, cancelacion) -> None:
		try:
			self._cargar_py7zr(indice, cancelacion)
		except _py7zr().exceptions.UnsupportedCompressionMethodError as error:
			log.info("py7zr no admite el método de %s: %s", ruta, error)
			self._reserva_por_metodo()
			raise UsarReserva() from error

	def _cargar_py7zr(self, indice: Indice, cancelacion) -> None:
		def leer(archivo) -> None:
			bloques = []
			principal = getattr(archivo.header, "main_streams", None)
			if principal is not None:
				bloques = list(principal.unpackinfo.folders)
			for i, miembro in enumerate(archivo.files):
				if i % 256 == 0:
					base.comprobar(cancelacion)
				nombre = nombre_seguro(miembro.filename)
				if nombre is None:
					indice.omitidas.append(miembro.filename)
					continue
				if not nombre:
					continue
				fecha = miembro.lastwritetime
				modificado = float(fecha.totimestamp()) if fecha is not None else 0.0
				if miembro.is_directory:
					indice.agregar(nombre, True, modificado=modificado)
					continue
				if miembro.is_symlink or miembro.is_junction or miembro.is_socket:
					indice.omitidas.append(miembro.filename)
					continue
				bloque = next((j for j, b in enumerate(bloques) if b is miembro.folder), None)
				tamano = 0 if miembro.emptystream else int(miembro.uncompressed or 0)
				solo_lectura = 0x1 if miembro.readonly else 0
				dato = _Miembro(miembro.id, bloque, tamano, bool(miembro.emptystream))
				indice.agregar(nombre, False, tamano, modificado, solo_lectura, dato)

		self._con_7z(leer)

	# Lectura -------------------------------------------------------------------------

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		if self._reserva is not None:
			return self._reserva.abrir_lectura(ruta)
		ruta = self._limpia(ruta)
		indice = self.indice()
		if self._reserva is not None:
			return self._reserva.abrir_lectura(ruta)
		entrada = indice.entradas.get(ruta)
		if entrada is None:
			raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=ruta), ruta)
		if entrada.es_carpeta:
			raise base.ErrorAcceso(_("«{r}» es una carpeta.").format(r=ruta), ruta)
		miembro: _Miembro = indice.datos[ruta]  # type: ignore[assignment]
		if miembro.vacio or miembro.tamano == 0:
			return io.BytesIO(b"")
		with self._candado:
			previo = self._previos.pop(miembro.identificador, None)
		if previo is not None:
			return lectura_temporal(previo, ruta)
		destinos = self._destinos(indice, miembro)
		try:
			self._extraer(destinos)
		except base.Cancelado:
			self._borrar(destinos.values())
			raise
		except base.ErrorArchivos:
			self._borrar(destinos.values())
			raise
		except _py7zr().exceptions.UnsupportedCompressionMethodError as error:
			self._borrar(destinos.values())
			log.info("py7zr no admite el método de %s: %s", self.archivo_local(), error)
			return self._reserva_por_metodo().abrir_lectura(ruta)
		except Exception as error:  # noqa: BLE001 - py7zr lanza sus propios tipos
			self._borrar(destinos.values())
			log.warning("No se pudo descomprimir %s de %s", ruta, self.archivo_local(), exc_info=True)
			raise base.ErrorArchivos(_("«{n}» está dañado dentro del comprimido o usa un método no admitido.").format(n=ruta),
				ruta) from error
		propio = destinos.pop(miembro.identificador)
		with self._candado:
			self._previos.update(destinos)
		return lectura_temporal(propio, ruta)

	def _destinos(self, indice: Indice, objetivo: _Miembro) -> dict[int, str]:
		"""Temporal del miembro pedido y de los anteriores de su bloque que aún no se han leído."""
		destinos = {objetivo.identificador: temporales.ruta_temporal(f"7z-{objetivo.identificador}")}
		if objetivo.bloque is None:
			return destinos
		acumulado = 0
		with self._candado:
			ya = set(self._previos)
		for dato in indice.datos.values():
			if not isinstance(dato, _Miembro) or dato.bloque != objetivo.bloque or dato.vacio:
				continue
			if dato.identificador >= objetivo.identificador or dato.identificador in ya:
				continue
			if acumulado + dato.tamano > LIMITE_PREVIO:
				break
			acumulado += dato.tamano
			destinos[dato.identificador] = temporales.ruta_temporal(f"7z-{dato.identificador}")
		return destinos

	def _extraer(self, destinos: dict[int, str]) -> None:
		def extraer(archivo) -> None:
			for miembro in archivo.files:
				ruta = destinos.get(miembro.id)
				archivo.worker.register_filelike(miembro.id, pathlib.Path(ruta) if ruta else None)
			archivo.worker.extract(archivo.fp, parallel=False)

		self._con_7z(extraer)

	@staticmethod
	def _borrar(rutas_temporales) -> None:
		for ruta in list(rutas_temporales):
			temporales.borrar(ruta)

	# Probar --------------------------------------------------------------------------

	def probar(self, cancelacion=None, al_avanzar=None) -> ResultadoPrueba:
		"""Descomprime cada bloque comprobando los CRC, sin escribir nada."""
		if self._reserva is not None:
			return self._reserva.probar(cancelacion, al_avanzar)
		py7zr = _py7zr()
		indice = self.indice(cancelacion)
		if self._reserva is not None:
			return self._reserva.probar(cancelacion, al_avanzar)
		resultado = ResultadoPrueba()
		por_bloque: dict[int | None, list[str]] = {}
		for ruta in indice.archivos():
			por_bloque.setdefault(indice.datos[ruta].bloque, []).append(ruta)  # type: ignore[union-attr]

		def comprobar_bloques(archivo) -> None:
			principal = getattr(archivo.header, "main_streams", None)
			if principal is None:
				return
			bloques = principal.unpackinfo.folders
			posiciones = principal.packinfo.packpositions
			for i, bloque in enumerate(bloques):
				base.comprobar(cancelacion)
				miembros = por_bloque.get(i, [])
				for miembro in bloque.files or ():
					archivo.worker.register_filelike(miembro.id, None)
				try:
					archivo.worker.extract_single(archivo.fp, bloque.files, archivo.worker.src_start + posiciones[i],
						archivo.worker.src_start + posiciones[i + 1], None, skip_notarget=False)
				except (py7zr.exceptions.PasswordRequired, py7zr.exceptions.UnsupportedCompressionMethodError):
					raise
				except py7zr.exceptions.CrcError as error:
					resultado.errores.append((str(error), _("La suma CRC no coincide")))
					continue
				except Exception as error:  # noqa: BLE001 - un bloque dañado no impide probar los demás
					if self._contrasena is not None:
						raise
					log.info("Bloque %d de %s dañado: %s", i, self.archivo_local(), error)
					for ruta in miembros:
						resultado.errores.append((ruta, _("Datos dañados")))
					continue
				for ruta in miembros:
					tamano = indice.entradas[ruta].tamano
					resultado.archivos += 1
					resultado.bytes += tamano
					if al_avanzar is not None:
						al_avanzar(ruta, tamano)

		try:
			self._con_7z(comprobar_bloques)
		except base.ErrorArchivos:
			raise
		except py7zr.exceptions.UnsupportedCompressionMethodError:
			return self._reserva_por_metodo().probar(cancelacion, al_avanzar)
		except Exception as error:  # noqa: BLE001 - py7zr lanza sus propios tipos
			raise base.ErrorArchivos(_("{n} está dañado.").format(n=self.nombre("")), self.ruta_archivo) from error
		resultado.archivos += len(por_bloque.get(None, []))
		return resultado

	# Ciclo de vida ------------------------------------------------------------------------

	def cerrar(self) -> None:
		with self._candado:
			previos, self._previos = list(self._previos.values()), {}
		self._borrar(previos)
		super().cerrar()


def _fabrica(contenedor: base.Proveedor, ruta_archivo: str) -> ProveedorSieteZ:
	return ProveedorSieteZ(contenedor, ruta_archivo)


resolver.registrar_comprimido(("7z",), _fabrica)
