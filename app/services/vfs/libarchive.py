# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor de comprimidos con libarchive: RAR, CAB, ISO, LHA, cpio, deb, rpm, XAR, WARC, ZIPX... (diseño 2.0, 8.2).

Solo lectura. libarchive es un lector **secuencial**: para llegar al miembro N
hay que pasar por los anteriores. Por eso:

- Un **cursor** (``Lector`` abierto, en un ``Ocioso`` que se cierra solo a los
  pocos segundos) recuerda por dónde va: si el motor de copia pide los
  miembros en el orden del archivo (lo normal: el índice conserva ese orden),
  cada uno se lee a continuación del anterior, sin volver a empezar.
- En los formatos **sólidos** (RAR sólido, 7z, CAB y los TAR comprimidos),
  saltar un miembro obliga a descomprimirlo; así que al pasar por los
  anteriores que aún no se han leído se guardan en temporales de
  ``data/temp`` (hasta ``LIMITE_PREVIO``), la misma idea que ``siete_z.py``.
  En los no sólidos (ZIP, ISO, XAR, LHA...) saltar es barato y no se guardan.
- Cada miembro se entrega como flujo independiente (``materializar``), así
  dos lecturas no compiten por el cursor. ``clonar()`` crea otro proveedor con
  su propio cursor: un objeto ``archive`` por hilo.

Cifrado: libarchive solo descifra ZIP (con la contraseña que pide el
``Decisor``). Un RAR o 7z cifrado se lee con el 7-Zip de la persona si lo hay
(``siete_zip_instalado``, 8.5); si no, suena ``comprimido.cifrado_sin_motor``
y el mensaje lo explica (nunca «contraseña incorrecta»).

Multivolumen: ``x.part1.rar`` (o ``x.rar`` con ``x.r00``...) se abre con todas
sus partes (``archive_read_open_filenames_w``); ``x.part2.rar`` y ``x.r00``
abren el conjunto desde la primera parte.
"""

from __future__ import annotations

import builtins
import logging
import os
import re
import struct
from typing import BinaryIO

from app.services.libarchive import ffi, lectura
from app.services.vfs import base, resolver, rutas, temporales
from app.services.vfs.zip import BLOQUE, Indice, Ocioso, ProveedorComprimido, ResultadoPrueba, lectura_temporal, materializar, nombre_seguro

log = logging.getLogger(__name__)

#: Bytes de miembros anteriores que se guardan de paso en los formatos sólidos.
LIMITE_PREVIO = 256 * 1024 * 1024

#: Extensiones que abre este proveedor (8.1). Las de un solo archivo (``.lz``, ``.lz4``, ``.Z``) son de ``flujo.py``.
EXTENSIONES = ("rar", "cab", "iso", "lzh", "lha", "cpio", "deb", "rpm", "xar", "pkg", "warc", "ar", "zipx",
	"tar.lz", "tar.lz4", "tar.lzma", "tlz", "tar.z", "taz")
#: Solo si la DLL tiene ``archive_read_open_filenames_w``.
EXTENSIONES_MULTIVOLUMEN = ("r00",)

_TIPOS = {
	"rar": "Archivo RAR", "cab": "Archivo CAB", "iso": "Imagen ISO", "lzh": "Archivo LHA", "lha": "Archivo LHA",
	"cpio": "Archivo cpio", "deb": "Paquete DEB", "rpm": "Paquete RPM", "xar": "Archivo XAR", "pkg": "Archivo XAR",
	"warc": "Archivo WARC", "ar": "Archivo ar", "zipx": "Archivo ZIPX", "7z": "Archivo 7z", "zip": "Archivo ZIP",
}
#: Formatos donde saltar un miembro es barato (no se guardan los anteriores).
_NO_SOLIDOS = ("zip", "zipx", "iso", "xar", "pkg", "lzh", "lha", "cpio", "ar", "deb", "warc")

_PARTE = re.compile(r"^(?P<base>.*)\.part(?P<n>\d+)\.rar$", re.IGNORECASE)
_RNN = re.compile(r"^(?P<base>.*)\.r(?P<n>\d\d)$", re.IGNORECASE)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _pagina_ansi() -> int:
	try:
		import ctypes

		return int(ctypes.windll.kernel32.GetACP())
	except (AttributeError, OSError):  # pragma: no cover - fuera de Windows
		return 1252


def _avisar_cifrado() -> None:
	try:
		from app.services.sonidos import servicio

		servicio.sonar("comprimido.cifrado_sin_motor")
	except Exception:  # noqa: BLE001 - sin sonido el mensaje basta
		log.debug("No sonó comprimido.cifrado_sin_motor", exc_info=True)


# ── Multivolumen ─────────────────────────────────────────────────────────────


def partes_de(ruta: str) -> list[str]:
	"""Todas las partes de un RAR multivolumen en orden, empezando por la primera; ``[ruta]`` si no lo es."""
	carpeta, nombre = os.path.split(ruta)
	try:
		vecinos = os.listdir(rutas.con_prefijo_largo(carpeta or "."))
	except OSError:
		return [ruta]
	parte = _PARTE.match(nombre)
	if parte:
		raiz = parte.group("base").casefold()
		numeradas = []
		for vecino in vecinos:
			otra = _PARTE.match(vecino)
			if otra and otra.group("base").casefold() == raiz:
				numeradas.append((int(otra.group("n")), vecino))
		numeradas.sort()
		if numeradas and numeradas[0][0] == 1:
			return [os.path.join(carpeta, n) for _i, n in numeradas]
		return [ruta]
	rnn = _RNN.match(nombre)
	raiz = rnn.group("base") if rnn else (nombre[:-4] if nombre.lower().endswith(".rar") else None)
	if raiz is None:
		return [ruta]
	primera = next((v for v in vecinos if v.casefold() == (raiz + ".rar").casefold()), None)
	if primera is None:
		return [ruta]
	resto = []
	for vecino in vecinos:
		otra = _RNN.match(vecino)
		if otra and otra.group("base").casefold() == raiz.casefold():
			resto.append((int(otra.group("n")), vecino))
	if not resto:
		return [ruta]
	return [os.path.join(carpeta, primera)] + [os.path.join(carpeta, n) for _i, n in sorted(resto)]


def rar_solido(ruta: str) -> bool:
	"""¿Es un RAR sólido? Se mira la bandera de la cabecera principal (RAR 4 y RAR 5) sin descomprimir nada."""
	try:
		with open(rutas.con_prefijo_largo(ruta), "rb") as archivo:
			cabeza = archivo.read(64)
	except OSError:
		return True
	if cabeza.startswith(b"Rar!\x1a\x07\x01\x00"):
		posicion = 8 + 4
		valores = []
		for _i in range(5):
			valor, desplazamiento = 0, 0
			while posicion < len(cabeza):
				byte = cabeza[posicion]
				posicion += 1
				valor |= (byte & 0x7F) << desplazamiento
				desplazamiento += 7
				if not byte & 0x80:
					break
			valores.append(valor)
		# tamaño, tipo, banderas, [extra], [datos], banderas del archivo
		_tamano, tipo, banderas, *resto = valores
		if tipo != 1:
			return True
		resto = resto[(1 if banderas & 1 else 0) + (1 if banderas & 2 else 0):]
		return bool(resto and resto[0] & 0x0004)
	if cabeza.startswith(b"Rar!\x1a\x07\x00") and len(cabeza) >= 7 + 5:
		tipo = cabeza[7 + 2]
		banderas = struct.unpack("<H", cabeza[7 + 3:7 + 5])[0]
		return tipo != 0x73 or bool(banderas & 0x0008)
	return True


# ── Índice ───────────────────────────────────────────────────────────────────


class _Miembro:
	"""Lo que el índice recuerda de cada archivo: su posición en el comprimido."""

	__slots__ = ("cifrado", "posicion", "tamano")

	def __init__(self, posicion: int, tamano: int, cifrado: bool) -> None:
		self.posicion = posicion
		self.tamano = tamano
		self.cifrado = cifrado


class _Cursor:
	"""Un ``Lector`` abierto y la contraseña con la que se abrió."""

	def __init__(self, lector: lectura.Lector, contrasena: str | None) -> None:
		self.lector = lector
		self.contrasena = contrasena


class ProveedorLibarchive(ProveedorComprimido):
	"""Comprimido leído con libarchive, como carpeta de solo lectura.

	:param formato: extensión con la que se registró («rar», «iso»...) o la que fuerza quien lo usa como reserva.
	"""

	esquema = "libarchive"
	tipo_visible = "Comprimido"

	def __init__(self, contenedor: base.Proveedor, ruta_archivo: str, formato: str = "") -> None:
		super().__init__(contenedor, ruta_archivo)
		self.capacidades = base.Capacidades(escribir=False)
		self.formato = (formato or resolver.extension_comprimido(contenedor.nombre(ruta_archivo)) or "").lower()
		if self.formato == "r00":
			self.formato = "rar"
		self.tipo_visible = _TIPOS.get(self.formato, "Archivo TAR" if self.formato.startswith("t") else "Comprimido")
		self._cursor: Ocioso | None = None
		#: Miembros guardados de paso (posición → temporal); se borran al leerlos o al cerrar.
		self._previos: dict[int, str] = {}
		self._leidos: set[int] = set()
		self._solido: bool | None = None

	def descripcion(self) -> str:
		return _(self.tipo_visible)

	# Dónde está --------------------------------------------------------------------

	def partes(self) -> list[str]:
		"""El archivo o todas las partes del multivolumen (solo si está en el disco y la DLL lo admite)."""
		local = self.archivo_local()
		if self.formato == "rar" and self.contenedor[0].ruta_local(self.ruta_archivo) and ffi.tiene(ffi.FUNCION_MULTIVOLUMEN):
			return partes_de(local)
		return [local]

	def _opciones(self) -> str:
		# ZIP sin la marca UTF-8: página 850, como ``zipfile`` (1.x, 8.15). Los CAB los crea makecab, un
		# programa ANSI de Windows: sin la marca UTF-8, sus nombres van en la página ANSI del sistema.
		if self.formato in ("zip", "zipx"):
			return "zip:hdrcharset=CP850"
		if self.formato == "cab":
			return f"cab:hdrcharset=CP{_pagina_ansi()}"
		return ""

	def _abrir_lector(self, contrasena: str | None = None) -> lectura.Lector:
		return lectura.Lector(self.partes(), contrasenas=(contrasena,) if contrasena else (), opciones=self._opciones(),
			nombre=self.nombre(""))

	def es_solido(self) -> bool:
		if self._solido is None:
			if self.formato == "rar":
				self._solido = rar_solido(self.partes()[0])
			else:
				self._solido = self.formato not in _NO_SOLIDOS
		return self._solido

	# Cifrado ---------------------------------------------------------------------------

	def _descifra(self) -> bool:
		"""libarchive solo descifra ZIP."""
		return self.formato in ("zip", "zipx")

	def _sin_motor(self, ruta: str) -> base.ErrorArchivos:
		"""RAR o 7z cifrado: el 7-Zip de la persona si lo hay (``UsarReserva``); si no, el mensaje de 8.2."""
		from app.services.vfs import siete_zip_instalado

		ejecutable = siete_zip_instalado.motor_lectura(self.formato)
		if ejecutable is not None:
			return _PasarAReserva(ejecutable)
		_avisar_cifrado()
		return lectura.CifradoNoAdmitido(lectura.mensaje_cifrado(self.formato), ruta)

	def _activar_reserva(self, ejecutable) -> ProveedorComprimido:
		from app.services.vfs.siete_zip_instalado import ProveedorSieteZipExterno

		return self.usar_reserva(ProveedorSieteZipExterno(self.contenedor[0], self.ruta_archivo, ejecutable, self.formato))

	# Índice ------------------------------------------------------------------------------

	def _cargar(self, ruta: str, indice: Indice, cancelacion) -> None:
		from app.services.vfs.zip import UsarReserva

		try:
			with self._abrir_lector(self._contrasena) as lector:
				while True:
					cabecera = lector.siguiente()
					if cabecera is None:
						break
					if cabecera.posicion % 128 == 0:
						base.comprobar(cancelacion)
					self._anotar(indice, cabecera)
		except lectura.CifradoNoAdmitido as error:
			# Cabeceras cifradas (RAR con «cifrar también los nombres»): no se puede ni listar.
			fallo = self._sin_motor(ruta)
			if isinstance(fallo, _PasarAReserva):
				self._activar_reserva(fallo.ejecutable)
				raise UsarReserva() from error
			raise fallo from error
		with self._candado:
			self._borrar_previos()
			self._leidos.clear()

	def _anotar(self, indice: Indice, cabecera: lectura.Cabecera) -> None:
		nombre = nombre_seguro(cabecera.nombre)
		if nombre is None:
			indice.omitidas.append(cabecera.nombre)
			return
		if not nombre:
			return
		if cabecera.tipo == "carpeta":
			indice.agregar(nombre, True, modificado=cabecera.modificado)
			return
		if cabecera.tipo != "archivo":
			# Enlaces (simbólicos y duros) y dispositivos no se muestran, como en TAR y 7z.
			indice.omitidas.append(cabecera.nombre)
			return
		dato = _Miembro(cabecera.posicion, cabecera.tamano, cabecera.cifrado)
		if indice.agregar(nombre, False, cabecera.tamano, cabecera.modificado, 0x1 if cabecera.solo_lectura else 0, dato) \
				and cabecera.tamano < 0:
			indice.entradas[nombre] = indice.entradas[nombre].con(tamano=-1)

	# Lectura ------------------------------------------------------------------------------

	def _cursor_compartido(self) -> Ocioso:
		with self._candado:
			if self._cursor is None:
				self._cursor = Ocioso(lambda: _Cursor(self._abrir_lector(self._contrasena), self._contrasena),
					lambda c: c.lector.cerrar(), clave=self.archivo_local())
			return self._cursor

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
		if miembro.cifrado and not self._descifra():
			fallo = self._sin_motor(ruta)
			if isinstance(fallo, _PasarAReserva):
				return self._activar_reserva(fallo.ejecutable).abrir_lectura(ruta)
			raise fallo
		with self._candado:
			previo = self._previos.pop(miembro.posicion, None)
		if previo is not None:
			return lectura_temporal(previo, ruta)
		incorrecta = False
		for _intento in range(4):
			if miembro.cifrado and (self._contrasena is None or incorrecta):
				self.pedir_contrasena(incorrecta)
			try:
				return self._leer_miembro(miembro, ruta, indice)
			except lectura.ContrasenaNecesaria as error:
				incorrecta = error.incorrecta or self._contrasena is not None
				miembro.cifrado = True
		raise base.ErrorAcceso(_("La contraseña de {n} no es correcta.").format(n=self.nombre("")), ruta)

	def _leer_miembro(self, miembro: _Miembro, ruta: str, indice: Indice) -> BinaryIO:
		pendientes = self._pendientes_previos(indice, miembro) if self.es_solido() else {}
		cursor = self._cursor_compartido()
		try:
			with cursor.usar() as actual:
				if actual.lector.posicion >= miembro.posicion or actual.contrasena != self._contrasena:
					actual.lector.cerrar()
					actual.lector = self._abrir_lector(self._contrasena)
					actual.contrasena = self._contrasena
				lector = actual.lector
				while True:
					cabecera = lector.siguiente()
					if cabecera is None:
						raise base.ErrorArchivos(_("«{n}» no aparece al leer el comprimido: ¿ha cambiado?").format(n=ruta), ruta)
					if cabecera.posicion == miembro.posicion:
						flujo = materializar(lectura.FlujoEntrada(lector), ruta, cabecera.tamano)
						with self._candado:
							self._leidos.add(miembro.posicion)
						return flujo
					if cabecera.posicion in pendientes:
						self._guardar_previo(lector, cabecera, pendientes[cabecera.posicion])
		except BaseException:
			cursor.cerrar()
			raise

	def _pendientes_previos(self, indice: Indice, objetivo: _Miembro) -> dict[int, str]:
		"""Miembros anteriores al pedido que aún no se han leído (posición → nombre), hasta ``LIMITE_PREVIO``."""
		with self._candado:
			ya = set(self._previos) | self._leidos
		pendientes: dict[int, str] = {}
		acumulado = 0
		for ruta, dato in indice.datos.items():
			if not isinstance(dato, _Miembro) or dato.posicion >= objetivo.posicion or dato.posicion in ya or dato.cifrado:
				continue
			tamano = max(0, dato.tamano)
			if acumulado + tamano > LIMITE_PREVIO:
				break
			acumulado += tamano
			pendientes[dato.posicion] = ruta
		return pendientes

	def _guardar_previo(self, lector: lectura.Lector, cabecera: lectura.Cabecera, ruta: str) -> None:
		destino = temporales.ruta_temporal(f"la-{cabecera.posicion}")
		try:
			with open(destino, "wb") as salida:
				while datos := lector.leer(BLOQUE):
					salida.write(datos)
		except BaseException:
			temporales.borrar(destino)
			raise
		with self._candado:
			self._previos[cabecera.posicion] = destino

	def _borrar_previos(self) -> None:
		previos, self._previos = list(self._previos.values()), {}
		for ruta in previos:
			temporales.borrar(ruta)

	# Probar ----------------------------------------------------------------------------------

	def probar(self, cancelacion=None, al_avanzar=None) -> ResultadoPrueba:
		"""Lee todo el comprimido UNA vez, en orden (libarchive comprueba las sumas al leer)."""
		if self._reserva is not None:
			return self._reserva.probar(cancelacion, al_avanzar)
		indice = self.indice(cancelacion)
		if self._reserva is not None:
			return self._reserva.probar(cancelacion, al_avanzar)
		por_posicion = {dato.posicion: ruta for ruta, dato in indice.datos.items() if isinstance(dato, _Miembro)}
		if any(indice.datos[r].cifrado for r in por_posicion.values()) and not self._descifra():  # type: ignore[union-attr]
			fallo = self._sin_motor(self.ruta_archivo)
			if isinstance(fallo, _PasarAReserva):
				return self._activar_reserva(fallo.ejecutable).probar(cancelacion, al_avanzar)
		if any(indice.datos[r].cifrado for r in por_posicion.values()) and self._descifra() and self._contrasena is None:  # type: ignore[union-attr]
			self.pedir_contrasena(False)
		resultado = ResultadoPrueba()
		try:
			with self._abrir_lector(self._contrasena) as lector:
				while True:
					base.comprobar(cancelacion)
					cabecera = lector.siguiente()
					if cabecera is None:
						break
					ruta = por_posicion.get(cabecera.posicion)
					if ruta is None:
						continue
					try:
						while datos := lector.leer(BLOQUE):
							base.comprobar(cancelacion)
							resultado.bytes += len(datos)
							if al_avanzar is not None:
								al_avanzar(ruta, len(datos))
						resultado.archivos += 1
					except lectura.ContrasenaNecesaria as error:
						if error.incorrecta:
							raise base.ErrorAcceso(error.mensaje, self.ruta_archivo) from error
						resultado.errores.append((ruta, error.mensaje))
					except (base.Cancelado, lectura.CifradoNoAdmitido):
						raise
					except base.ErrorArchivos as error:
						resultado.errores.append((ruta, error.mensaje))
						# Tras un fallo de datos el lector puede no saber seguir: se intenta la siguiente entrada.
		except lectura.CifradoNoAdmitido:
			raise
		except base.Cancelado:
			raise
		except base.ErrorArchivos as error:
			if not resultado.errores:
				raise
			log.info("La prueba de %s se detuvo: %s", self.mostrar(""), error.mensaje)
		return resultado

	# Ciclo de vida -------------------------------------------------------------------------------

	def _clon(self) -> ProveedorLibarchive:
		otro = type(self)(self.contenedor[0], self.ruta_archivo, self.formato)
		otro.contenedor = self.contenedor
		with self._candado:
			otro._indice, otro._firma = self._indice, self._firma
			otro._copia_local = self._copia_local
		otro._contrasena = self._contrasena
		otro._solido = self._solido
		if self._reserva is not None:
			otro._reserva = self._reserva.clonar()
		return otro

	def cerrar(self) -> None:
		with self._candado:
			cursor, self._cursor = self._cursor, None
			self._borrar_previos()
		if cursor is not None:
			cursor.cerrar()
		super().cerrar()


class _PasarAReserva(base.ErrorArchivos):
	"""Interno: hay un 7-Zip que sabe descifrar este comprimido."""

	def __init__(self, ejecutable) -> None:
		super().__init__("")
		self.ejecutable = ejecutable


def activado() -> bool:
	"""``comprimidos.usar_libarchive`` (verdadero si no hay configuración o falta la clave)."""
	config = resolver.servicios().config
	if config is None:
		return True
	try:
		return bool(config.obtener("comprimidos.usar_libarchive"))
	except KeyError:
		log.debug("Sin la clave comprimidos.usar_libarchive", exc_info=True)
		return True


def disponible() -> bool:
	"""libarchive activada en Preferencias y con la DLL cargada (para las reservas de ZIP y 7z)."""
	return activado() and ffi.disponible()


def _fabrica(contenedor: base.Proveedor, ruta_archivo: str) -> ProveedorLibarchive:
	if not activado():
		raise base.NoAdmitido(_("La lectura con libarchive está desactivada en Preferencias, Comprimidos."), ruta_archivo)
	return ProveedorLibarchive(contenedor, ruta_archivo)


def registrar() -> bool:
	"""Registra las extensiones de libarchive si la DLL carga (8.1). Devuelve si se registraron."""
	if not ffi.disponible():
		log.warning("Formatos de libarchive sin registrar: %s", ffi.causa())
		return False
	resolver.registrar_comprimido(EXTENSIONES, _fabrica)
	if ffi.tiene(ffi.FUNCION_MULTIVOLUMEN):
		resolver.registrar_comprimido(EXTENSIONES_MULTIVOLUMEN, _fabrica)
	else:
		log.warning("libarchive sin %s: los RAR multivolumen no se registran", ffi.FUNCION_MULTIVOLUMEN)
	return True


registrar()
