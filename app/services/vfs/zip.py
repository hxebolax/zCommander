# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor de archivos ZIP (lectura y escritura) y la base común de los comprimidos.

La base ``ProveedorComprimido`` vive aquí porque el bloque C solo es dueño de
``zip.py``, ``tar.py`` y ``siete_z.py`` dentro de ``vfs``: los proveedores TAR
y 7z la importan de este módulo. Reúne lo que tienen en común los tres:

- **Rutas internas** con «/» y la raíz como cadena vacía (sección 9.4).
- **Índice perezoso**: no se lee nada al crear el proveedor (la fábrica no
  hace E/S); el primer ``listar``, ``info`` o ``abrir_lectura`` lee el índice
  en el hilo que llama y lo conserva mientras el panel está dentro. Si el
  archivo cambia en el disco (fecha o tamaño), se vuelve a leer.
- **Nombres seguros**: es el ÚNICO sitio donde se validan los nombres de un
  comprimido (sección 14). Una entrada con ruta absoluta, unidad, «..» o «:»
  (que escribiría un flujo alternativo de NTFS) no se lista ni se puede
  extraer; queda en ``omitidas`` y en el registro.
- **Contraseñas** pedidas con el ``Decisor`` de ``resolver.servicios()`` desde
  el hilo de trabajo.

ZIP admite escritura en una **transacción** (``transaccion()``): los cambios se
acumulan en una vista en memoria (los archivos nuevos, en temporales de
``data/temp``) y al salir sin error se reconstruye el comprimido UNA vez. Los
miembros que no cambian se copian «en crudo» (sin descomprimir ni volver a
comprimir): es mucho más rápido y conserva los miembros cifrados aunque no se
sepa su contraseña (``zipfile`` no sabe cifrar).

2.0 (8.1 y 8.2): lo que se añade usa el método de ``comprimidos.metodo_zip``
(Deflate, Zstandard —método 93, el ``zipfile`` de Python 3.15 lo lee y lo
escribe— o almacenar). Si ``zipfile`` no sabe leer un miembro (AES de WinZip,
o un método como LZMA o PPMd de un ZIPX), la lectura de ese miembro pasa a
libarchive, con la contraseña que pida el ``Decisor``.
"""

from __future__ import annotations

import builtins
import copy
import io
import logging
import os
import re
import shutil
import struct
import threading
import time
import weakref
import zipfile
import zlib
from abc import abstractmethod
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import BinaryIO

from app.services import errores
from app.services.vfs import base, resolver, rutas, temporales

log = logging.getLogger(__name__)

#: Tamaño hasta el que un miembro de TAR o 7z se descomprime en memoria (más grande, a un temporal).
LIMITE_MEMORIA = 16 * 1024 * 1024
#: Segundos sin uso tras los que se cierra el comprimido abierto para leer.
SEGUNDOS_OCIOSO = 10.0
BLOQUE = 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Nombres seguros ──────────────────────────────────────────────────────────

_UNIDAD = re.compile(r"^[A-Za-z]:")


def nombre_seguro(nombre: str) -> str | None:
	"""Ruta interna normalizada («docs/a.txt»), «» si no nombra nada, o ``None`` si es peligrosa.

	Peligrosa: absoluta («/etc», «\\\\servidor»), con unidad («C:»), con «..»,
	con «:» en un componente (flujo alternativo de NTFS) o con caracteres de
	control. Las barras invertidas cuentan como separador (las escriben algunos
	compresores de Windows).
	"""
	texto = (nombre or "").replace("\\", "/")
	if texto.startswith("/") or _UNIDAD.match(texto):
		return None
	partes: list[str] = []
	for parte in texto.split("/"):
		if parte in ("", "."):
			continue
		if parte == ".." or ":" in parte or any(ord(c) < 32 for c in parte):
			return None
		partes.append(parte)
	return "/".join(partes)


def validar_nombre_nuevo(ruta: str) -> str:
	"""Ruta interna para crear algo dentro del comprimido; lanza ``NombreNoValido`` si no vale en Windows.

	Se exige un nombre válido en Windows (no solo seguro) porque lo que se
	guarda en el comprimido se acabará extrayendo en Windows.
	"""
	normal = nombre_seguro(ruta)
	if not normal:
		raise base.NombreNoValido(_("«{n}» no es un nombre válido dentro del comprimido.").format(n=ruta), ruta)
	for parte in normal.split("/"):
		problema = rutas.problema_en_nombre(parte)
		if problema:
			raise base.NombreNoValido(problema, ruta)
	return normal


# ── Índice en árbol ──────────────────────────────────────────────────────────


class Indice:
	"""Árbol de entradas de un comprimido (o de la vista de una transacción ZIP).

	``hijos`` usa diccionarios como conjuntos ordenados: se conserva el orden
	del comprimido, que es el más rápido para leer un TAR comprimido o un 7z
	sólido (el panel ordena por su cuenta).
	"""

	def __init__(self) -> None:
		self.entradas: dict[str, base.Entrada] = {}
		self.hijos: dict[str, dict[str, None]] = {"": {}}
		#: Dato propio del proveedor por ruta (``ZipInfo``, ``TarInfo``, identificador del 7z...).
		self.datos: dict[str, object] = {}
		#: Nombres originales que no se muestran (peligrosos, enlaces, duplicados imposibles).
		self.omitidas: list[str] = []

	def copia(self) -> Indice:
		otro = Indice()
		otro.entradas = dict(self.entradas)
		otro.hijos = {clave: dict(valor) for clave, valor in self.hijos.items()}
		otro.datos = dict(self.datos)
		otro.omitidas = list(self.omitidas)
		return otro

	def es_carpeta(self, ruta: str) -> bool:
		if ruta == "":
			return True
		entrada = self.entradas.get(ruta)
		return entrada is not None and entrada.es_carpeta

	def _asegurar_carpeta(self, ruta: str) -> bool:
		"""Crea las carpetas que faltan (los ZIP no siempre traen la entrada «carpeta/»)."""
		if ruta == "":
			return True
		entrada = self.entradas.get(ruta)
		if entrada is not None:
			return entrada.es_carpeta
		padre, _sep, nombre = ruta.rpartition("/")
		if not self._asegurar_carpeta(padre):
			return False
		self.entradas[ruta] = base.Entrada(nombre=nombre, ruta=ruta, es_carpeta=True)
		self.hijos[ruta] = {}
		self.hijos[padre][ruta] = None
		return True

	def agregar(self, ruta: str, es_carpeta: bool, tamano: int = -1, modificado: float = 0.0, atributos: int = 0,
			dato: object = None) -> bool:
		"""Añade o sustituye una entrada. ``False`` si choca con otra de distinto tipo (se omite)."""
		padre, _sep, nombre = ruta.rpartition("/")
		if not self._asegurar_carpeta(padre):
			self.omitidas.append(ruta)
			return False
		existente = self.entradas.get(ruta)
		if existente is not None and existente.es_carpeta != es_carpeta:
			if existente.es_carpeta:
				# Un archivo con el nombre de una carpeta que ya tiene contenido: no se puede mostrar.
				self.omitidas.append(ruta)
				return False
			self.quitar(ruta)
		if es_carpeta:
			self.hijos.setdefault(ruta, {})
		self.entradas[ruta] = base.Entrada(
			nombre=nombre, ruta=ruta, es_carpeta=es_carpeta, tamano=-1 if es_carpeta else max(0, tamano),
			modificado=modificado, atributos=atributos,
		)
		if dato is not None:
			self.datos[ruta] = dato
		else:
			self.datos.pop(ruta, None)
		self.hijos[padre][ruta] = None
		return True

	def quitar(self, ruta: str) -> None:
		"""Quita la entrada y todo lo que contiene."""
		for hijo in list(self.hijos.get(ruta, ())):
			self.quitar(hijo)
		self.hijos.pop(ruta, None)
		self.entradas.pop(ruta, None)
		self.datos.pop(ruta, None)
		self.hijos.get(ruta.rpartition("/")[0], {}).pop(ruta, None)

	def recorrer(self, ruta: str = "") -> Iterator[str]:
		"""Todas las rutas bajo ``ruta`` (sin ella), cada carpeta antes que su contenido."""
		pendientes = list(reversed(list(self.hijos.get(ruta, ()))))
		while pendientes:
			actual = pendientes.pop()
			yield actual
			pendientes.extend(reversed(list(self.hijos.get(actual, ()))))

	def archivos(self) -> Iterator[str]:
		for ruta in self.recorrer(""):
			if not self.entradas[ruta].es_carpeta:
				yield ruta


# ── Objetos abiertos que se cierran solos ─────────────────────────────────────


class Ocioso:
	"""Objeto que se abre al usarlo y se cierra tras unos segundos sin uso.

	Por qué: tener el comprimido siempre abierto impediría a Windows renombrarlo,
	borrarlo o sustituirlo (también al reconstruir un ZIP); abrirlo en cada
	lectura sería lentísimo con un ``.tar.gz`` o un ZIP de miles de entradas.
	``usar()`` lo reserva en exclusiva mientras dura el bloque ``with``.
	"""

	_por_clave: dict[str, weakref.WeakSet] = {}
	_candado_clases = threading.Lock()

	def __init__(self, abrir: Callable[[], object], cerrar: Callable[[object], None], clave: str = "",
			segundos: float = SEGUNDOS_OCIOSO) -> None:
		self._abrir = abrir
		self._cerrar = cerrar
		self._segundos = segundos
		self._objeto: object | None = None
		self._temporizador: threading.Timer | None = None
		self._ultimo_uso = 0.0
		self._candado = threading.RLock()
		if clave:
			with Ocioso._candado_clases:
				Ocioso._por_clave.setdefault(clave.casefold(), weakref.WeakSet()).add(self)

	@contextmanager
	def usar(self) -> Iterator[object]:
		with self._candado:
			if self._objeto is None:
				self._objeto = self._abrir()
			try:
				yield self._objeto
			finally:
				self._ultimo_uso = time.monotonic()
				if self._temporizador is None:
					self._programar(self._segundos)

	def _programar(self, segundos: float) -> None:
		# Un solo temporizador a la vez: al vencer, mira si hubo uso reciente y se reprograma.
		temporizador = threading.Timer(segundos, self._vencer)
		temporizador.daemon = True
		self._temporizador = temporizador
		temporizador.start()

	def _vencer(self) -> None:
		with self._candado:
			self._temporizador = None
			resto = self._segundos - (time.monotonic() - self._ultimo_uso)
			if resto > 0.05 and self._objeto is not None:
				self._programar(resto)
				return
		self.cerrar()

	def cerrar(self) -> None:
		with self._candado:
			if self._temporizador is not None:
				self._temporizador.cancel()
				self._temporizador = None
			objeto, self._objeto = self._objeto, None
		if objeto is not None:
			try:
				self._cerrar(objeto)
			except Exception:  # noqa: BLE001 - cerrar un lector nunca debe fallar hacia arriba
				log.debug("No se pudo cerrar un comprimido abierto", exc_info=True)

	@classmethod
	def cerrar_clave(cls, clave: str) -> None:
		"""Cierra todos los abiertos sobre el mismo archivo (antes de sustituirlo)."""
		with cls._candado_clases:
			abiertos = list(cls._por_clave.get(clave.casefold(), ()))
		for abierto in abiertos:
			abierto.cerrar()


# ── Flujos ───────────────────────────────────────────────────────────────────


class LecturaSegura(io.RawIOBase):
	"""Envuelve un flujo de lectura y convierte sus errores en ``ErrorArchivos``.

	Por qué: ``zipfile`` avisa de un CRC erróneo con ``BadZipFile`` al leer el
	final, y el motor de copia solo trata ``ErrorArchivos`` y ``OSError`` como
	error de un elemento; sin esto, un archivo dañado tumbaría toda la copia.
	"""

	def __init__(self, flujo: BinaryIO, nombre: str, al_cerrar: Callable[[], None] | None = None) -> None:
		super().__init__()
		self._flujo = flujo
		self._nombre = nombre
		self._al_cerrar = al_cerrar

	def _traducir(self, error: BaseException) -> base.ErrorArchivos:
		if isinstance(error, base.ErrorArchivos):
			return error
		if isinstance(error, OSError) and not isinstance(error, EOFError):
			return errores.convertir(error, self._nombre)
		return base.ErrorArchivos(_("«{n}» está dañado dentro del comprimido: {e}").format(n=self._nombre, e=error), self._nombre)

	def readable(self) -> bool:
		return True

	def seekable(self) -> bool:
		try:
			return self._flujo.seekable()
		except (OSError, ValueError):
			return False

	def read(self, n: int = -1) -> bytes:
		try:
			return self._flujo.read(n)
		except Exception as error:  # noqa: BLE001 - se traduce a un error con mensaje en español
			raise self._traducir(error) from error

	def readinto(self, destino) -> int:
		datos = self.read(len(destino))
		destino[: len(datos)] = datos
		return len(datos)

	def readall(self) -> bytes:
		return self.read(-1)

	def seek(self, posicion: int, desde: int = 0) -> int:
		try:
			return self._flujo.seek(posicion, desde)
		except Exception as error:  # noqa: BLE001 - se traduce a un error con mensaje en español
			raise self._traducir(error) from error

	def tell(self) -> int:
		return self._flujo.tell()

	def close(self) -> None:
		if self.closed:
			return
		try:
			self._flujo.close()
		except Exception:  # noqa: BLE001 - cerrar un flujo de lectura no debe tapar el resultado
			log.debug("Fallo al cerrar el flujo de %s", self._nombre, exc_info=True)
		finally:
			super().close()
			if self._al_cerrar is not None:
				self._al_cerrar()


def lectura_temporal(ruta: str, nombre: str) -> LecturaSegura:
	"""Flujo sobre un temporal de ``data/temp`` que se borra al cerrarlo."""
	return LecturaSegura(open(ruta, "rb"), nombre, al_cerrar=lambda: temporales.borrar(ruta))


def materializar(flujo: BinaryIO, nombre: str, tamano: int, cancelacion=None) -> LecturaSegura:
	"""Copia un miembro a memoria (pequeño) o a un temporal (grande) y devuelve un flujo independiente.

	Así dos lecturas del mismo TAR o 7z no compiten por el mismo archivo abierto.
	"""
	if 0 <= tamano <= LIMITE_MEMORIA:
		datos = io.BytesIO()
		while bloque := flujo.read(BLOQUE):
			base.comprobar(cancelacion)
			datos.write(bloque)
		datos.seek(0)
		return LecturaSegura(datos, nombre)
	destino = temporales.ruta_temporal(nombre.rpartition("/")[2] or "miembro")
	try:
		with open(destino, "wb") as salida:
			while bloque := flujo.read(BLOQUE):
				base.comprobar(cancelacion)
				salida.write(bloque)
	except BaseException:
		temporales.borrar(destino)
		raise
	return lectura_temporal(destino, nombre)


# ── Base común ───────────────────────────────────────────────────────────────


class UsarReserva(Exception):  # noqa: N818 - no es un error: avisa de que el índice lo da la reserva
	"""Lo lanza ``_cargar`` tras ``usar_reserva``: el índice lo lee el proveedor de reserva."""


@dataclass
class ResultadoPrueba:
	"""Resultado de probar un comprimido: archivos leídos sin error y los que fallaron."""

	archivos: int = 0
	bytes: int = 0
	errores: list[tuple[str, str]] = field(default_factory=list)

	@property
	def correcto(self) -> bool:
		return not self.errores


class ProveedorComprimido(base.Proveedor):
	"""Base de ZIP, TAR y 7z: árbol, rutas internas, índice perezoso y contraseñas.

	:param contenedor: proveedor que tiene el archivo comprimido (local, otro comprimido, FTP...).
	:param ruta_archivo: ruta del comprimido dentro de ``contenedor``.
	"""

	#: «Archivo ZIP», «Archivo TAR», «Archivo 7z» (para la persona).
	tipo_visible = ""

	def __init__(self, contenedor: base.Proveedor, ruta_archivo: str) -> None:
		super().__init__()
		self.contenedor = (contenedor, ruta_archivo)
		self.ruta_archivo = ruta_archivo
		self.capacidades = base.Capacidades(escribir=False)
		self._candado = threading.RLock()
		self._indice: Indice | None = None
		self._firma: tuple[int, int] | None = None
		self._copia_local: str | None = None
		self._contrasena: str | None = None
		#: 2.0 (8.2): otro proveedor que lee este comprimido cuando el motor propio no puede
		#: (7z con un método que py7zr no admite, RAR cifrado con el 7-Zip de la persona).
		self._reserva: ProveedorComprimido | None = None

	# Dónde está el comprimido --------------------------------------------------

	def archivo_local(self) -> str:
		"""Ruta en el disco del comprimido; si el contenedor no es local, una copia en ``data/temp``."""
		contenedor, ruta = self.contenedor
		local = contenedor.ruta_local(ruta)
		if local:
			return local
		with self._candado:
			if self._copia_local is None or not os.path.exists(self._copia_local):
				self._copia_local = contenedor.extraer_temporal(ruta)
			return self._copia_local

	@staticmethod
	def _firma_de(ruta: str) -> tuple[int, int] | None:
		try:
			st = os.stat(rutas.con_prefijo_largo(ruta))
		except OSError:
			return None
		return (st.st_mtime_ns, st.st_size)

	def indice(self, cancelacion=None) -> Indice:
		"""Índice al día (lo lee la primera vez o si el archivo cambió en el disco)."""
		if self._reserva is not None:
			return self._reserva.indice(cancelacion)
		with self._candado:
			ruta = self.archivo_local()
			firma = self._firma_de(ruta)
			if firma is None:
				self._indice = None
				raise base.NoEncontrado(_("No se encuentra el comprimido {r}").format(r=self.contenedor[0].mostrar(self.ruta_archivo)), ruta)
			if self._indice is None or firma != self._firma:
				nuevo = Indice()
				try:
					self._cargar(ruta, nuevo, cancelacion)
				except UsarReserva:
					return self._reserva.indice(cancelacion)  # type: ignore[union-attr]
				except (base.ErrorArchivos, base.Cancelado):
					raise
				except OSError as error:
					if error.errno is not None or getattr(error, "winerror", None) is not None:
						raise errores.convertir(error, ruta) from error
					# gzip y bz2 avisan de datos dañados con un OSError sin código: va al caso general.
					log.warning("Comprimido dañado: %s", ruta, exc_info=True)
					raise base.ErrorArchivos(_("{n} no es un comprimido válido o está dañado.").format(
						n=self.contenedor[0].nombre(self.ruta_archivo)), ruta) from error
				except Exception as error:  # noqa: BLE001 - cada biblioteca lanza los suyos
					log.warning("No se pudo leer el índice de %s", ruta, exc_info=True)
					raise base.ErrorArchivos(_("{n} no es un comprimido válido o está dañado.").format(
						n=self.contenedor[0].nombre(self.ruta_archivo)), ruta) from error
				if nuevo.omitidas:
					log.warning("%s: %d entradas omitidas por ruta peligrosa o no admitida: %s", ruta, len(nuevo.omitidas),
						nuevo.omitidas[:20])
				self._indice, self._firma = nuevo, firma
			return self._indice

	@abstractmethod
	def _cargar(self, ruta: str, indice: Indice, cancelacion) -> None:
		"""Lee el índice del comprimido ``ruta`` (local) y lo vuelca en ``indice``. Cada formato tiene el suyo."""

	def _vista(self, cancelacion=None) -> Indice:
		"""Lo que se muestra: el índice o, en una transacción ZIP, la vista con los cambios pendientes."""
		return self.indice(cancelacion)

	@property
	def omitidas(self) -> list[str]:
		"""Entradas que no se muestran (para avisar a la persona). Vacío si no se ha leído el índice."""
		if self._reserva is not None:
			return self._reserva.omitidas
		return list(self._indice.omitidas) if self._indice is not None else []

	# Reserva (2.0, 8.2) -----------------------------------------------------------

	def usar_reserva(self, reserva: ProveedorComprimido) -> ProveedorComprimido:
		"""Desde ahora este comprimido se lee con ``reserva`` (índice, lectura y prueba)."""
		with self._candado:
			if self._reserva is None:
				reserva.contenedor = self.contenedor
				reserva._contrasena = self._contrasena
				with reserva._candado:
					reserva._copia_local = self._copia_local
				self._reserva = reserva
				log.info("%s se lee con %s", self.mostrar(""), type(reserva).__name__)
			return self._reserva

	# Navegación ---------------------------------------------------------------

	@staticmethod
	def _limpia(ruta: str) -> str:
		return (ruta or "").replace("\\", "/").strip("/")

	def listar(self, ruta: str, cancelacion=None) -> list[base.Entrada]:
		ruta = self._limpia(ruta)
		vista = self._vista(cancelacion)
		if not vista.es_carpeta(ruta):
			raise base.NoEncontrado(_("No existe la carpeta «{r}» en el comprimido.").format(r=ruta), ruta)
		return [vista.entradas[hijo] for hijo in vista.hijos.get(ruta, ())]

	def info(self, ruta: str) -> base.Entrada:
		ruta = self._limpia(ruta)
		if ruta == "":
			return base.Entrada(nombre=self.nombre(""), ruta="", es_carpeta=True)
		entrada = self._vista().entradas.get(ruta)
		if entrada is None:
			raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=ruta), ruta)
		return entrada

	def padre(self, ruta: str) -> str | None:
		ruta = self._limpia(ruta)
		if not ruta:
			return None
		return ruta.rpartition("/")[0]

	def unir(self, carpeta: str, nombre: str) -> str:
		carpeta = self._limpia(carpeta)
		nombre = self._limpia(nombre)
		return f"{carpeta}/{nombre}" if carpeta else nombre

	def raiz(self, ruta: str) -> str:
		return ""

	def nombre(self, ruta: str) -> str:
		ruta = self._limpia(ruta)
		if ruta:
			return ruta.rpartition("/")[2]
		contenedor, archivo = self.contenedor
		return contenedor.nombre(archivo)

	def mostrar(self, ruta: str) -> str:
		contenedor, archivo = self.contenedor
		texto = contenedor.mostrar(archivo)
		ruta = self._limpia(ruta)
		if not ruta:
			return texto
		separador = "/" if "://" in texto else "\\"
		return texto + separador + ruta.replace("/", separador)

	def descripcion(self) -> str:
		return self.tipo_visible or self.esquema

	# Contraseñas --------------------------------------------------------------

	def fijar_contrasena(self, contrasena: str | None) -> None:
		"""Contraseña conocida de antemano (la del diálogo Extraer); si falla, se vuelve a pedir."""
		self._contrasena = contrasena or None
		if self._reserva is not None:
			self._reserva.fijar_contrasena(contrasena)

	def pedir_contrasena(self, incorrecta: bool = False) -> str:
		"""Pregunta la contraseña con el ``Decisor`` (bloquea este hilo, nunca el de la interfaz).

		:raises Cancelado: si la persona no la escribe (cancela la operación entera:
			seguir preguntando por cada archivo sería peor).
		"""
		decisor = resolver.servicios().decisor
		nombre = self.nombre("")
		if decisor is None:
			raise base.ErrorAcceso(_("{n} está protegido con contraseña.").format(n=nombre), self.ruta_archivo)
		texto = (_("La contraseña no es correcta. Escriba la contraseña de {n}:") if incorrecta
			else _("{n} está protegido con contraseña. Escríbala:")).format(n=nombre)
		valor = decisor.pedir_texto(_("Contraseña del comprimido"), texto, "", oculto=True)
		if valor is None:
			raise base.Cancelado(_("No se escribió la contraseña de {n}").format(n=nombre), self.ruta_archivo)
		self._contrasena = valor
		return valor

	# Probar -----------------------------------------------------------------------

	def probar(self, cancelacion=None, al_avanzar: Callable[[str, int], None] | None = None) -> ResultadoPrueba:
		"""Lee todo el contenido comprobando las sumas; los errores de cada archivo no paran la prueba.

		:param al_avanzar: recibe (ruta del archivo, bytes leídos desde la última llamada).
		"""
		if self._reserva is not None:
			return self._reserva.probar(cancelacion, al_avanzar)
		resultado = ResultadoPrueba()
		vista = self.indice(cancelacion)
		for ruta in list(vista.archivos()):
			base.comprobar(cancelacion)
			try:
				with self.abrir_lectura(ruta) as flujo:
					while datos := flujo.read(BLOQUE):
						base.comprobar(cancelacion)
						resultado.bytes += len(datos)
						if al_avanzar is not None:
							al_avanzar(ruta, len(datos))
				resultado.archivos += 1
			except base.Cancelado:
				raise
			except base.ErrorArchivos as error:
				resultado.errores.append((ruta, error.mensaje))
		return resultado

	# Ciclo de vida ------------------------------------------------------------------

	def _clon(self) -> ProveedorComprimido:
		otro = type(self)(self.contenedor[0], self.ruta_archivo)
		otro.contenedor = self.contenedor
		with self._candado:
			otro._indice, otro._firma = self._indice, self._firma
			otro._copia_local = self._copia_local
		otro._contrasena = self._contrasena
		if self._reserva is not None:
			otro._reserva = self._reserva.clonar()
		return otro

	def cerrar(self) -> None:
		reserva, self._reserva = self._reserva, None
		if reserva is not None:
			reserva.cerrar()
		super().cerrar()

	def clonar(self) -> ProveedorComprimido:
		"""Otro proveedor del mismo comprimido que comparte el índice ya leído (sin volver a leerlo)."""
		return self._clon()


# ── ZIP ──────────────────────────────────────────────────────────────────────

_ZIP_UTF8 = 0x800
_ZIP_DESCRIPTOR = 0x08
_ZIP_CIFRADO = 0x01
_ATRIBUTOS_DOS = 0x27  # solo lectura, oculto, sistema y archivo


@dataclass
class _Nuevo:
	"""Contenido nuevo de un miembro durante una transacción (temporal en ``data/temp``)."""

	local: str


def fecha_zip(marca: float) -> tuple[int, int, int, int, int, int]:
	"""Fecha DOS de un ZIP (de 1980 a 2107); sin fecha, la de ahora."""
	if not marca:
		marca = time.time()
	try:
		fecha = time.localtime(marca)[:6]
	except (OverflowError, OSError, ValueError):
		fecha = time.localtime()[:6]
	if fecha[0] < 1980:
		return (1980, 1, 1, 0, 0, 0)
	if fecha[0] > 2107:
		return (2107, 12, 31, 23, 59, 58)
	return fecha  # type: ignore[return-value]


def _marca_de(info: zipfile.ZipInfo) -> float:
	try:
		return time.mktime((*info.date_time, 0, 0, -1))
	except (OverflowError, ValueError):
		return 0.0


def _quitar_extra(extra: bytes, identificador: int) -> bytes:
	"""Quita del campo extra el bloque ``identificador`` (el ZIP64 se vuelve a calcular al escribir)."""
	resultado = bytearray()
	i = 0
	while i + 4 <= len(extra):
		cabecera, longitud = struct.unpack("<HH", extra[i:i + 4])
		fin = i + 4 + longitud
		if cabecera != identificador:
			resultado += extra[i:fin]
		i = fin
	return bytes(resultado)


def copiar_miembro_crudo(fuente: BinaryIO, info: zipfile.ZipInfo, destino: zipfile.ZipFile, nombre: str,
		fecha: tuple | None = None, cancelacion=None) -> None:
	"""Copia un miembro de un ZIP a otro sin descomprimirlo (datos comprimidos tal cual).

	Usa partes internas de ``zipfile`` (``fp``, ``_lock``, ``start_dir``,
	``filelist``) igual que ``ZipFile.mkdir``: no hay API pública para copiar
	en crudo y recomprimir sería lento y perdería el cifrado. Las pruebas de
	``tests/servicios/test_c_zip.py`` comprueban que el resultado se lee bien.

	:param fuente: el ZIP de origen abierto en binario (se mueve su posición).
	:param nombre: nombre del miembro en el destino (puede cambiar al renombrar).
	:param fecha: fecha nueva (solo si el miembro no va cifrado).
	"""
	nuevo = copy.copy(info)
	nuevo.filename = nombre
	nuevo.orig_filename = nombre
	nuevo.extra = _quitar_extra(info.extra, 0x0001)
	nuevo.flag_bits = info.flag_bits & ~_ZIP_UTF8
	if fecha is not None and not (info.flag_bits & _ZIP_CIFRADO):
		nuevo.date_time = fecha
	fuente.seek(info.header_offset)
	cabecera = fuente.read(30)
	if len(cabecera) != 30 or cabecera[:4] != b"PK\x03\x04":
		raise zipfile.BadZipFile(f"Cabecera local errónea en {info.filename!r}")
	largo_nombre, largo_extra = struct.unpack("<HH", cabecera[26:30])
	inicio = info.header_offset + 30 + largo_nombre + largo_extra
	zip64 = info.file_size > zipfile.ZIP64_LIMIT or info.compress_size > zipfile.ZIP64_LIMIT
	with destino._lock:
		if destino._seekable:
			destino.fp.seek(destino.start_dir)
		nuevo.header_offset = destino.fp.tell()
		destino._didModify = True
		destino.fp.write(nuevo.FileHeader(zip64))
		fuente.seek(inicio)
		restante = info.compress_size
		while restante > 0:
			base.comprobar(cancelacion)
			datos = fuente.read(min(BLOQUE, restante))
			if not datos:
				raise zipfile.BadZipFile(f"Faltan datos de {info.filename!r}")
			destino.fp.write(datos)
			restante -= len(datos)
		if nuevo.flag_bits & _ZIP_DESCRIPTOR:
			formato_descriptor = "<4sLQQ" if zip64 else "<4sLLL"
			destino.fp.write(struct.pack(formato_descriptor, b"PK\x07\x08", info.CRC, info.compress_size, info.file_size))
		destino.filelist.append(nuevo)
		destino.NameToInfo[nuevo.filename] = nuevo
		destino.start_dir = destino.fp.tell()


def info_carpeta_zip(ruta: str, modificado: float) -> zipfile.ZipInfo:
	info = zipfile.ZipInfo(ruta.rstrip("/") + "/", fecha_zip(modificado))
	info.external_attr = ((0o40000 | 0o775) << 16) | 0x10
	info.compress_size = 0
	info.CRC = 0
	info.file_size = 0
	return info


#: Nivel Deflate (1.x) → nivel de Zstandard: rápido, normal y máximo.
_NIVEL_ZSTD = {None: 3, 1: 1, 6: 3, 9: 19}
METODOS_ZIP = ("deflate", "zstd", "almacenar")


def metodo_zip_configurado() -> str:
	"""``comprimidos.metodo_zip`` (deflate si no hay configuración o no es válido)."""
	config = resolver.servicios().config
	if config is None:
		return "deflate"
	try:
		metodo = config.obtener("comprimidos.metodo_zip")
	except Exception:  # noqa: BLE001 - sin la clave, el método de siempre
		log.debug("Sin comprimidos.metodo_zip", exc_info=True)
		return "deflate"
	return metodo if metodo in METODOS_ZIP else "deflate"


def info_archivo_zip(ruta: str, modificado: float, nivel: int | None, atributos: int = 0,
		metodo: str = "deflate") -> zipfile.ZipInfo:
	"""``ZipInfo`` para un archivo nuevo: ``metodo`` con ``nivel`` (0 = sin compresión) y atributos DOS.

	:param metodo: «deflate», «zstd» (método 93) o «almacenar».
	"""
	info = zipfile.ZipInfo(ruta, fecha_zip(modificado))
	if nivel == 0 or metodo == "almacenar":
		info.compress_type = zipfile.ZIP_STORED
	elif metodo == "zstd":
		info.compress_type = zipfile.ZIP_ZSTANDARD
		info.compress_level = _NIVEL_ZSTD.get(nivel, nivel)
	else:
		info.compress_type = zipfile.ZIP_DEFLATED
		info.compress_level = nivel
	info.external_attr = (0o644 << 16) | (atributos & _ATRIBUTOS_DOS)
	return info


def _abrir_zip_lectura(ruta: str) -> zipfile.ZipFile:
	"""Los nombres sin la marca UTF-8 son los del Explorador antiguo y de MS-DOS: página de códigos 850."""
	return zipfile.ZipFile(rutas.con_prefijo_largo(ruta), "r", metadata_encoding="cp850")


#: Un único cerrojo de reconstrucción por archivo: dos transacciones sobre el mismo ZIP van en fila.
_candados_reconstruir: dict[str, threading.Lock] = {}
_candado_global = threading.Lock()


def _candado_de(ruta: str) -> threading.Lock:
	with _candado_global:
		return _candados_reconstruir.setdefault(ruta.casefold(), threading.Lock())


class ProveedorZip(ProveedorComprimido):
	"""Archivo ZIP como carpeta, con escritura agrupada en transacciones."""

	esquema = "zip"
	tipo_visible = "Archivo ZIP"

	def __init__(self, contenedor: base.Proveedor, ruta_archivo: str) -> None:
		super().__init__(contenedor, ruta_archivo)
		self.capacidades = base.Capacidades(escribir=contenedor.esquema == "local" or contenedor.capacidades.escribir)
		#: Nivel Deflate de lo que se añade (None = el de zlib; 0 = sin compresión). Comprimir lo cambia.
		self.nivel: int | None = None
		#: 2.0: método de lo que se añade («deflate», «zstd», «almacenar»); por defecto, el de Preferencias.
		self.metodo: str = metodo_zip_configurado()
		#: 2.0 (8.2): lector de libarchive para los miembros que ``zipfile`` no sabe leer (AES, ZIPX).
		self._libarchive: ProveedorComprimido | None = None
		self._lector: Ocioso | None = None
		self._profundidad = 0
		self._vista_tx: Indice | None = None
		self._firma_tx: tuple[int, int] | None = None
		self._cambios = False
		self._temporales_tx: list[str] = []

	def descripcion(self) -> str:
		return _("Archivo ZIP")

	# Índice -----------------------------------------------------------------

	def _cargar(self, ruta: str, indice: Indice, cancelacion) -> None:
		with _abrir_zip_lectura(ruta) as archivo:
			for i, info in enumerate(archivo.infolist()):
				if i % 256 == 0:
					base.comprobar(cancelacion)
				nombre = nombre_seguro(info.filename)
				if nombre is None:
					indice.omitidas.append(info.filename)
					continue
				if not nombre:
					continue
				atributos = info.external_attr & _ATRIBUTOS_DOS if info.create_system == 0 else 0
				if info.is_dir():
					indice.agregar(nombre, True, modificado=_marca_de(info), dato=info)
				else:
					indice.agregar(nombre, False, info.file_size, _marca_de(info), atributos, info)

	def _vista(self, cancelacion=None) -> Indice:
		with self._candado:
			if self._vista_tx is not None:
				return self._vista_tx
		return self.indice(cancelacion)

	# Lectura ------------------------------------------------------------------

	def _abrir_lector(self) -> zipfile.ZipFile:
		return _abrir_zip_lectura(self.archivo_local())

	def _lector_compartido(self) -> Ocioso:
		with self._candado:
			if self._lector is None:
				self._lector = Ocioso(self._abrir_lector, lambda z: z.close(), clave=self.archivo_local())
			return self._lector

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		ruta = self._limpia(ruta)
		vista = self._vista()
		entrada = vista.entradas.get(ruta)
		if entrada is None:
			raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=ruta), ruta)
		if entrada.es_carpeta:
			raise base.ErrorAcceso(_("«{r}» es una carpeta.").format(r=ruta), ruta)
		dato = vista.datos.get(ruta)
		if isinstance(dato, _Nuevo):
			return open(dato.local, "rb")
		if not isinstance(dato, zipfile.ZipInfo):
			raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=ruta), ruta)
		return self._abrir_miembro(dato, ruta)

	def _abrir_miembro(self, info: zipfile.ZipInfo, ruta: str) -> BinaryIO:
		cifrado = bool(info.flag_bits & _ZIP_CIFRADO)
		incorrecta = False
		for _intento in range(4):
			clave = None
			if cifrado:
				if self._contrasena is None or incorrecta:
					self.pedir_contrasena(incorrecta)
				clave = (self._contrasena or "").encode("utf-8")
			try:
				with self._lector_compartido().usar() as archivo:
					flujo = archivo.open(info, "r", pwd=clave)
				return LecturaSegura(flujo, ruta)
			except RuntimeError as error:
				if "password" in str(error).lower():
					incorrecta = True
					continue
				if type(error) is not RuntimeError:
					# zipfile avisa con una subclase de RuntimeError de un método de compresión o un cifrado (AES) que no conoce.
					reserva = self._lector_libarchive()
					if reserva is not None:
						log.info("«%s» de %s se lee con libarchive: %s", ruta, self.archivo_local(), error)
						return self._leer_con_libarchive(reserva, info)
					raise base.NoAdmitido(_("«{n}» usa un método de compresión o un cifrado (AES) que zCommander no admite.").format(
						n=ruta), ruta) from error
				raise base.ErrorArchivos(str(error), ruta) from error
			except (zipfile.BadZipFile, zlib.error, EOFError) as error:
				raise base.ErrorArchivos(_("«{n}» está dañado dentro del comprimido.").format(n=ruta), ruta) from error
			except OSError as error:
				raise errores.convertir(error, self.archivo_local()) from error
		raise base.ErrorAcceso(_("La contraseña de {n} no es correcta.").format(n=self.nombre("")), ruta)

	def _lector_libarchive(self) -> ProveedorComprimido | None:
		"""Proveedor de libarchive sobre este mismo ZIP (o ``None`` si falta la DLL)."""
		from app.services.vfs import libarchive

		with self._candado:
			if self._libarchive is None:
				if not libarchive.disponible():
					return None
				from app.services.vfs.libarchive import ProveedorLibarchive

				lector = ProveedorLibarchive(self.contenedor[0], self.ruta_archivo, "zip")
				lector.contenedor = self.contenedor
				with lector._candado:
					lector._copia_local = self._copia_local
				self._libarchive = lector
			self._libarchive._contrasena = self._contrasena
			return self._libarchive

	def _leer_con_libarchive(self, lector: ProveedorComprimido, info: zipfile.ZipInfo) -> BinaryIO:
		nombre = nombre_seguro(info.filename) or info.filename
		try:
			return lector.abrir_lectura(nombre)
		finally:
			# La contraseña que se escribió para libarchive sirve también para los demás miembros.
			if lector._contrasena is not None:
				self._contrasena = lector._contrasena

	# Transacciones -------------------------------------------------------------

	@contextmanager
	def transaccion(self):
		"""Agrupa escrituras; al salir sin error de la más externa se reconstruye el ZIP una vez."""
		with self._candado:
			self._profundidad += 1
		correcto = False
		try:
			yield self
			correcto = True
		finally:
			with self._candado:
				self._profundidad -= 1
				externa = self._profundidad == 0
			if externa:
				self._terminar_transaccion(correcto)

	def _terminar_transaccion(self, correcto: bool) -> None:
		with self._candado:
			vista, firma, cambios = self._vista_tx, self._firma_tx, self._cambios
			self._vista_tx, self._firma_tx, self._cambios = None, None, False
			temporales_tx, self._temporales_tx = self._temporales_tx, []
		try:
			if correcto and cambios and vista is not None:
				self._reconstruir(vista, firma)
			elif cambios:
				log.info("Transacción descartada en %s: no se escribe nada", self.mostrar(""))
		finally:
			for temporal in temporales_tx:
				temporales.borrar(temporal)

	def _exigir_escritura(self, ruta: str) -> None:
		if not self.capacidades.escribir:
			raise base.SoloLectura(_("No se puede escribir en este comprimido."), ruta)

	def _vista_escritura(self) -> Indice:
		"""Vista de la transacción en curso (se crea al primer cambio, a partir del índice al día)."""
		with self._candado:
			if self._profundidad <= 0:
				raise RuntimeError("Escritura en un ZIP fuera de una transacción")
			if self._vista_tx is None:
				try:
					indice = self.indice()
					self._firma_tx = self._firma
				except base.NoEncontrado:
					# Comprimido todavía inexistente: se creará al terminar.
					indice, self._firma_tx = Indice(), None
				self._vista_tx = indice.copia()
			return self._vista_tx

	@staticmethod
	def _asegurar_padre(vista: Indice, ruta: str) -> None:
		padre = ruta.rpartition("/")[0]
		if padre and not vista.es_carpeta(padre):
			if padre in vista.entradas:
				raise base.YaExiste(_("Ya existe un archivo llamado «{n}».").format(n=padre), padre)
			vista.agregar(padre, True, modificado=time.time())

	def crear_carpeta(self, ruta: str) -> None:
		self._exigir_escritura(ruta)
		ruta = validar_nombre_nuevo(ruta)
		with self.transaccion(), self._candado:
			vista = self._vista_escritura()
			if ruta in vista.entradas:
				raise base.YaExiste(_("Ya existe «{n}».").format(n=ruta), ruta)
			self._asegurar_padre(vista, ruta)
			vista.agregar(ruta, True, modificado=time.time())
			self._cambios = True

	def abrir_escritura(self, ruta: str, tamano: int = -1) -> BinaryIO:
		"""Flujo hacia un temporal; al cerrarlo sin error, el miembro queda en la transacción.

		Fuera de una transacción abre la suya, que termina (y reconstruye) al cerrar el flujo.
		"""
		self._exigir_escritura(ruta)
		ruta = validar_nombre_nuevo(ruta)
		pila = ExitStack()
		pila.enter_context(self.transaccion())
		try:
			with self._candado:
				vista = self._vista_escritura()
				if vista.es_carpeta(ruta):
					raise base.YaExiste(_("Ya existe una carpeta llamada «{n}».").format(n=ruta), ruta)
				self._asegurar_padre(vista, ruta)
				temporal = temporales.ruta_temporal(ruta.rpartition("/")[2])
				self._temporales_tx.append(temporal)
			return _FlujoEscritura(temporal, lambda: self._registrar_nuevo(ruta, temporal), pila)
		except BaseException:
			pila.close()
			raise

	def _registrar_nuevo(self, ruta: str, temporal: str) -> None:
		with self._candado:
			vista = self._vista_escritura()
			anterior = vista.entradas.get(ruta)
			vista.agregar(ruta, False, os.path.getsize(temporal), time.time(), anterior.atributos if anterior else 0, _Nuevo(temporal))
			self._cambios = True

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		self._exigir_escritura(ruta)
		ruta = self._limpia(ruta)
		with self.transaccion(), self._candado:
			vista = self._vista_escritura()
			if ruta not in vista.entradas:
				raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=ruta), ruta)
			if vista.hijos.get(ruta) and not recursivo:
				raise base.ErrorAcceso(_("La carpeta «{r}» no está vacía.").format(r=ruta), ruta)
			vista.quitar(ruta)
			self._cambios = True

	def renombrar(self, origen: str, destino: str) -> None:
		self._exigir_escritura(origen)
		origen = self._limpia(origen)
		destino = validar_nombre_nuevo(destino)
		with self.transaccion(), self._candado:
			vista = self._vista_escritura()
			if origen not in vista.entradas:
				raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=origen), origen)
			if destino in vista.entradas and destino != origen:
				raise base.YaExiste(_("Ya existe «{n}».").format(n=destino), destino)
			if destino.startswith(origen + "/"):
				raise base.ErrorArchivos(_("No se puede mover una carpeta dentro de sí misma."), origen)
			self._asegurar_padre(vista, destino)
			for ruta in [origen, *vista.recorrer(origen)]:
				entrada = vista.entradas[ruta]
				nueva = destino + ruta[len(origen):]
				vista.agregar(nueva, entrada.es_carpeta, entrada.tamano, entrada.modificado, entrada.atributos, vista.datos.get(ruta))
			vista.quitar(origen)
			self._cambios = True

	def fijar_tiempos(self, ruta: str, modificado: float, creado: float = 0.0) -> None:
		if not modificado or not self.capacidades.escribir:
			return
		ruta = self._limpia(ruta)
		with self.transaccion(), self._candado:
			vista = self._vista_escritura()
			entrada = vista.entradas.get(ruta)
			if entrada is None or abs(entrada.modificado - modificado) < 2:
				return
			vista.entradas[ruta] = entrada.con(modificado=modificado)
			self._cambios = True

	# Reconstrucción ---------------------------------------------------------------

	def _escribir(self, vista: Indice, destino: str, origen: str | None) -> int:
		"""Escribe la vista completa en ``destino``; devuelve cuántas entradas tiene."""
		escritas = 0
		with ExitStack() as pila:
			fuente = pila.enter_context(open(rutas.con_prefijo_largo(origen), "rb")) if origen else None
			salida = pila.enter_context(zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False))
			for ruta in vista.recorrer(""):
				entrada = vista.entradas[ruta]
				dato = vista.datos.get(ruta)
				if entrada.es_carpeta:
					salida.mkdir(info_carpeta_zip(ruta, entrada.modificado))
				elif isinstance(dato, zipfile.ZipInfo):
					if fuente is None:
						raise base.ErrorArchivos(_("Falta el comprimido original."), ruta)
					cambia_fecha = abs(_marca_de(dato) - entrada.modificado) >= 2
					copiar_miembro_crudo(fuente, dato, salida, ruta, fecha_zip(entrada.modificado) if cambia_fecha else None)
				elif isinstance(dato, _Nuevo):
					info = info_archivo_zip(ruta, entrada.modificado, self.nivel, entrada.atributos, self.metodo)
					tamano = os.path.getsize(dato.local)
					info.file_size = tamano
					with open(dato.local, "rb") as datos, salida.open(info, "w", force_zip64=tamano > 0x7FFFFFFF) as escritura:
						shutil.copyfileobj(datos, escritura, BLOQUE)
				else:
					continue
				escritas += 1
		return escritas

	def _reconstruir(self, vista: Indice, firma: tuple[int, int] | None) -> None:
		contenedor, ruta_archivo = self.contenedor
		local = contenedor.ruta_local(ruta_archivo)
		with _candado_de(local or ruta_archivo):
			origen = self.archivo_local() if firma is not None else None
			if origen is not None and self._firma_de(origen) != firma:
				raise base.ErrorArchivos(_("{n} cambió mientras se modificaba: no se ha escrito nada. Vuelva a intentarlo.").format(
					n=self.nombre("")), ruta_archivo)
			if local:
				from app.services.operaciones import nombres

				temporal = os.path.join(os.path.dirname(local), nombres.temporal())
			else:
				temporal = temporales.ruta_temporal(contenedor.nombre(ruta_archivo))
			try:
				escritas = self._escribir(vista, temporal, origen)
				with zipfile.ZipFile(temporal) as comprobacion:
					if len(comprobacion.infolist()) != escritas:
						raise base.ErrorArchivos(_("La reconstrucción de {n} salió incompleta: no se ha escrito nada.").format(
							n=self.nombre("")), ruta_archivo)
				self._colocar(temporal, local)
			except BaseException as error:
				try:
					if os.path.exists(temporal):
						os.remove(temporal)
				except OSError:
					log.warning("No se pudo borrar el temporal %s", temporal, exc_info=True)
				if isinstance(error, OSError):
					raise errores.convertir(error, ruta_archivo) from error
				if isinstance(error, (zipfile.BadZipFile, zlib.error)):
					raise base.ErrorArchivos(_("{n} está dañado: no se ha podido reconstruir.").format(n=self.nombre("")),
						ruta_archivo) from error
				raise
		with self._candado:
			self._indice, self._firma = None, None
		log.info("Reconstruido %s (%d entradas)", self.mostrar(""), escritas)

	def _colocar(self, temporal: str, local: str | None) -> None:
		contenedor, ruta_archivo = self.contenedor
		if local:
			from app.services.windows import copia_nativa

			for intento in range(6):
				Ocioso.cerrar_clave(local)
				try:
					if os.path.exists(rutas.con_prefijo_largo(local)):
						# ReplaceFileW conserva atributos, permisos y la marca de la Web del ZIP.
						copia_nativa.sustituir(temporal, local)
					else:
						copia_nativa.mover(temporal, local)
					return
				except base.ErrorAcceso:
					if intento == 5:
						raise
					log.debug("%s sigue en uso; se reintenta la sustitución", local, exc_info=True)
					time.sleep(0.2 * (intento + 1))
			return
		# Comprimido dentro de otro proveedor (otro comprimido, un servidor): se sube entero.
		try:
			with contenedor.transaccion():
				with open(temporal, "rb") as datos, contenedor.abrir_escritura(ruta_archivo) as salida:
					shutil.copyfileobj(datos, salida, BLOQUE)
		finally:
			temporales.borrar(temporal)
		with self._candado:
			self._copia_local = None

	# Ciclo de vida -----------------------------------------------------------------

	def _clon(self) -> ProveedorZip:
		otro = super()._clon()
		otro.nivel = self.nivel  # type: ignore[attr-defined]
		otro.metodo = self.metodo  # type: ignore[attr-defined]
		return otro  # type: ignore[return-value]

	def cerrar(self) -> None:
		with self._candado:
			lector, self._lector = self._lector, None
			libarchive, self._libarchive = self._libarchive, None
		if lector is not None:
			lector.cerrar()
		if libarchive is not None:
			libarchive.cerrar()
		super().cerrar()


class _FlujoEscritura(io.FileIO):
	"""Archivo temporal de un miembro nuevo: al cerrarlo bien, avisa y termina su transacción."""

	def __init__(self, ruta: str, al_terminar: Callable[[], None], pila: ExitStack) -> None:
		super().__init__(ruta, "wb")
		self._al_terminar = al_terminar
		self._pila: ExitStack | None = pila

	def _acabar(self, error: tuple | None) -> None:
		if self.closed and self._pila is None:
			return
		pila, self._pila = self._pila, None
		try:
			super().close()
			if error is None:
				self._al_terminar()
		except BaseException as fallo:
			if pila is not None:
				pila.__exit__(type(fallo), fallo, fallo.__traceback__)
			raise
		if pila is not None:
			if error is None:
				pila.close()
			else:
				pila.__exit__(*error)

	def close(self) -> None:
		self._acabar(None)

	def __exit__(self, tipo, valor, traza) -> None:
		self._acabar(None if tipo is None else (tipo, valor, traza))


def _fabrica(contenedor: base.Proveedor, ruta_archivo: str) -> ProveedorZip:
	return ProveedorZip(contenedor, ruta_archivo)


resolver.registrar_comprimido(("zip",), _fabrica)
