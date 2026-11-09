# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Crear comprimidos (sección 8.15 de la 1.x y 8.6 de la 2.0, Comprimir).

Piezas:

- ``reunir``: recorre los elementos de trabajo (de cualquier proveedor, también
  de otro comprimido) y devuelve la lista de ``Fuente`` con su nombre dentro
  del comprimido («carpeta/sub/a.txt»).
- ``crear_escritor``: un ``Escritor`` por formato con la misma interfaz
  (``agregar``, ``cerrar``). Se escribe siempre en un temporal; la operación
  lo coloca con su nombre al terminar (una cancelación no deja medio archivo).
- ``extension``, ``nombre_propuesto``, ``textos_formatos`` y ``motor`` para el diálogo.

Formatos y motores (2.0, 8.1):

- ZIP con ``zipfile`` (Deflate, Zstandard —método 93— o almacenar). La
  variante «aes» cifra con AES-256: con 7za si está; si no, con libarchive.
- 7z con 7za si está (multihilo, AES y «cifrar también los nombres»); si no,
  con py7zr.
- TAR, ``.tar.gz``, ``.tar.bz2``, ``.tar.xz`` y ``.tar.zst`` con ``tarfile``;
  ``.tar.lz4``, ``.tar.lz``, ISO, cpio y XAR con libarchive.
- ``.gz``, ``.bz2``, ``.xz`` y ``.zst`` sueltos: un archivo comprimido por
  elemento, con Python. Las carpetas no se pueden comprimir así.

Niveles: «sin» (sin compresión), «rapido», «normal» y «maximo».

Sin wx; la operación con progreso y carriles está en ``operaciones/comprimir.py``.
"""

from __future__ import annotations

import builtins
import bz2
import gzip
import logging
import lzma
import os
import shutil
import tarfile
import tempfile
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from app.services.recorrido import recorrer
from app.services.vfs import base, rutas, temporales
from app.services.vfs.zip import BLOQUE, info_archivo_zip, info_carpeta_zip, metodo_zip_configurado

log = logging.getLogger(__name__)

#: Formatos que se pueden crear (los de libarchive, solo si la DLL los admite).
FORMATOS: tuple[str, ...] = ("zip", "7z", "tar", "tar.gz", "tar.bz2", "tar.xz", "tar.zst", "tar.lz4", "tar.lz", "iso",
	"cpio", "xar", "gz", "bz2", "xz", "zst")
#: Un solo archivo comprimido por elemento (8.6).
FLUJOS: tuple[str, ...] = ("gz", "bz2", "xz", "zst")
#: Los que crea libarchive.
CON_LIBARCHIVE: tuple[str, ...] = ("tar.lz4", "tar.lz", "iso", "cpio", "xar")
#: Variantes del ZIP: Zstandard y cifrado AES-256.
VARIANTES_ZIP: tuple[str, ...] = ("zstd", "aes")
NIVELES: tuple[str, ...] = ("sin", "rapido", "normal", "maximo")
#: Nivel Deflate/gzip/bzip2 de cada nivel (0 = guardar sin comprimir).
_NIVEL_ZLIB = {"sin": 0, "rapido": 1, "normal": 6, "maximo": 9}
_NIVEL_XZ = {"sin": 0, "rapido": 1, "normal": 6, "maximo": 9}
_NIVEL_7Z = {"rapido": 1, "normal": 5, "maximo": 9}
_NIVEL_ZSTD = {"sin": 1, "rapido": 1, "normal": 3, "maximo": 19}
#: Extensiones que se reconocen al quitar o deducir el formato (de la más larga a la más corta en ``formato_de``).
_EQUIVALENCIAS = (("tar.gz", "tar.gz"), ("tgz", "tar.gz"), ("tar.bz2", "tar.bz2"), ("tbz2", "tar.bz2"),
	("tar.xz", "tar.xz"), ("txz", "tar.xz"), ("tar.zst", "tar.zst"), ("tzst", "tar.zst"), ("tar.lz4", "tar.lz4"),
	("tar.lz", "tar.lz"), ("tar", "tar"), ("zip", "zip"), ("7z", "7z"), ("iso", "iso"), ("cpio", "cpio"), ("xar", "xar"),
	("gz", "gz"), ("bz2", "bz2"), ("xz", "xz"), ("zst", "zst"))


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Formatos disponibles y motor ─────────────────────────────────────────────


def _libarchive_admite(formato: str) -> bool:
	try:
		from app.services.libarchive import escritura

		return escritura.admite(formato)
	except Exception:  # noqa: BLE001 - sin libarchive el formato no se ofrece
		log.debug("libarchive no disponible para %s", formato, exc_info=True)
		return False


def _ruta_7za():
	from app.services import siete_zip_externo

	return siete_zip_externo.ruta_7za()


def separar(clave: str) -> tuple[str, str]:
	"""«zip:aes» → («zip», «aes»); «7z» → («7z», «»)."""
	formato, _sep, variante = clave.partition(":")
	return formato, variante


def textos_formatos(hay_carpetas: bool = False) -> list[tuple[str, str]]:
	"""(clave, texto) de «Formato:». Los seis de la 1.x van primero y en el mismo orden.

	:param hay_carpetas: si lo que se comprime tiene carpetas, los formatos de un solo archivo no se ofrecen.
	"""
	opciones = [("zip", "ZIP"), ("7z", "7z"), ("tar", "TAR"), ("tar.gz", "TAR.GZ"), ("tar.bz2", "TAR.BZ2"), ("tar.xz", "TAR.XZ"),
		("zip:zstd", _("ZIP (Zstandard)"))]
	if _ruta_7za() is not None or _libarchive_admite("zip"):
		opciones.append(("zip:aes", _("ZIP cifrado con AES-256")))
	opciones.append(("tar.zst", "TAR.ZST"))
	for formato, texto in (("tar.lz4", "TAR.LZ4"), ("tar.lz", "TAR.LZ"), ("iso", _("ISO (imagen de disco)")), ("cpio", "cpio"),
			("xar", "XAR")):
		if _libarchive_admite(formato):
			opciones.append((formato, texto))
	if not hay_carpetas:
		opciones += [("gz", _(".gz (un archivo por elemento)")), ("bz2", _(".bz2 (un archivo por elemento)")),
			("xz", _(".xz (un archivo por elemento)")), ("zst", _(".zst (un archivo por elemento)"))]
	return opciones


def textos_niveles() -> list[tuple[str, str]]:
	return [("sin", _("Sin compresión")), ("rapido", _("Rápido")), ("normal", _("Normal")), ("maximo", _("Máximo"))]


def admite_contrasena(formato: str, variante: str = "") -> bool:
	"""7z siempre; ZIP solo con la variante «aes»."""
	return formato == "7z" or (formato == "zip" and variante == "aes")


def es_flujo(formato: str) -> bool:
	return formato in FLUJOS


def motor(formato: str, variante: str = "") -> str:
	"""Qué programa crea el formato («7za 26.06», «libarchive 3.8.11», «Python»), para el diálogo (8.6)."""
	from app.services import siete_zip_externo

	if formato == "7z" or (formato == "zip" and variante == "aes"):
		ruta = _ruta_7za()
		if ruta is not None:
			version = siete_zip_externo.version(ruta)
			return f"7za {version}".strip()
		if formato == "7z":
			return "Python (py7zr)"
		return _texto_libarchive()
	if formato in CON_LIBARCHIVE:
		return _texto_libarchive()
	return "Python"


def _texto_libarchive() -> str:
	from app.services.libarchive import ffi

	version = ffi.version()
	return f"libarchive {version}".strip() if version else _("libarchive (no disponible)")


def extension(formato: str) -> str:
	return "." + formato


def quitar_extension_comprimido(nombre: str) -> str:
	"""«copia.tar.gz» → «copia»; «informe.docx» → «informe»."""
	minusculas = nombre.lower()
	for ext in sorted((e for e, _f in _EQUIVALENCIAS), key=len, reverse=True):
		if minusculas.endswith("." + ext) and len(nombre) > len(ext) + 1:
			return nombre[: -(len(ext) + 1)]
	punto = nombre.rfind(".")
	return nombre[:punto] if punto > 0 else nombre


def nombre_propuesto(entradas: list[base.Entrada], carpeta_actual: str, formato: str) -> str:
	"""Nombre del comprimido: el del elemento si es uno solo; si no, el de la carpeta actual."""
	if len(entradas) == 1:
		entrada = entradas[0]
		if es_flujo(formato) and not entrada.es_carpeta:
			return entrada.nombre + extension(formato)
		raiz = entrada.nombre if entrada.es_carpeta else quitar_extension_comprimido(entrada.nombre)
	else:
		raiz = os.path.basename(carpeta_actual.rstrip("\\/")) or carpeta_actual.rstrip(":\\/") or "comprimido"
	return raiz + extension(formato)


def cambiar_extension(nombre: str, formato: str) -> str:
	"""Sustituye la extensión de comprimido de ``nombre`` por la de ``formato`` (al cambiar el desplegable)."""
	carpeta, archivo = os.path.split(nombre)
	nuevo = quitar_extension_comprimido(archivo) + extension(formato) if archivo else archivo
	return os.path.join(carpeta, nuevo) if carpeta else nuevo


def formato_de(nombre: str) -> str | None:
	"""Formato de un nombre de archivo («a.tgz» → «tar.gz»), o None si no se sabe crear."""
	minusculas = nombre.lower()
	for ext, formato in _EQUIVALENCIAS:
		if minusculas.endswith("." + ext):
			return formato
	return None


# ── Fuentes ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Fuente:
	"""Algo que va al comprimido.

	:param nombre: ruta dentro del comprimido con «/».
	:param proveedor, ruta: de dónde se lee.
	"""

	nombre: str
	es_carpeta: bool
	tamano: int
	modificado: float
	proveedor: base.Proveedor
	ruta: str
	atributos: int = 0


def reunir(proveedor: base.Proveedor, entradas: list[base.Entrada], cancelacion=None,
		al_error: Callable[[str, str], None] | None = None) -> list[Fuente]:
	"""Elementos y todo su contenido (sin seguir enlaces), en orden de carpeta antes que contenido."""
	fuentes: list[Fuente] = []
	for entrada in entradas:
		if entrada.es_superior:
			continue
		base.comprobar(cancelacion)
		fuentes.append(Fuente(entrada.nombre, entrada.es_carpeta, max(0, entrada.tamano), entrada.modificado, proveedor,
			entrada.ruta, entrada.atributos))
		if not entrada.es_carpeta or entrada.es_enlace:
			continue

		def anotar(ruta: str, error: base.ErrorArchivos) -> None:
			if al_error is not None:
				al_error(ruta, error.mensaje)

		for elemento in recorrer(proveedor, entrada.ruta, cancelacion, al_error=anotar):
			sub = elemento.entrada
			if sub.es_enlace:
				# Un enlace no se sigue: lo que apunta puede estar fuera o formar un bucle.
				continue
			relativo = elemento.relativo.replace("\\", "/")
			fuentes.append(Fuente(f"{entrada.nombre}/{relativo}", sub.es_carpeta, max(0, sub.tamano), sub.modificado, proveedor,
				sub.ruta, sub.atributos))
	return fuentes


# ── Escritores ───────────────────────────────────────────────────────────────


class _Progreso:
	"""Envuelve un flujo de lectura para contar bytes y comprobar la cancelación en cada bloque."""

	def __init__(self, flujo, cancelacion, al_avanzar) -> None:
		self._flujo = flujo
		self._cancelacion = cancelacion
		self._al_avanzar = al_avanzar

	def read(self, n: int = -1) -> bytes:
		base.comprobar(self._cancelacion)
		datos = self._flujo.read(n if n is not None and n >= 0 else BLOQUE)
		if datos and self._al_avanzar is not None:
			self._al_avanzar(len(datos))
		return datos


class Escritor(ABC):
	"""Crea un comprimido en ``ruta`` (un temporal que la operación coloca después).

	``diferido``: el trabajo de verdad se hace en ``cerrar`` (7za comprime todo
	de una vez); entonces ``cerrar`` recibe la cancelación y el progreso.
	"""

	diferido = False

	def __init__(self, ruta: str) -> None:
		self.ruta = ruta

	@abstractmethod
	def agregar(self, fuente: Fuente, cancelacion=None, al_avanzar: Callable[[int], None] | None = None) -> None:
		"""Añade una carpeta o un archivo (``al_avanzar`` recibe los bytes leídos)."""

	@abstractmethod
	def cerrar(self, cancelacion=None, al_avanzar: Callable[[int], None] | None = None) -> None:
		"""Termina de escribir (índice, cabeceras). Después el archivo es válido."""

	def descartar(self) -> None:
		"""Cierra sin importar el estado y borra el archivo a medias."""
		try:
			self._soltar()
		except Exception:  # noqa: BLE001 - se descarta: lo importante es borrar
			log.debug("Fallo al cerrar un comprimido que se descarta", exc_info=True)
		try:
			if os.path.exists(self.ruta):
				os.remove(self.ruta)
		except OSError:
			log.warning("No se pudo borrar el comprimido a medias %s", self.ruta, exc_info=True)

	def _soltar(self) -> None:
		"""Libera lo abierto sin terminar el trabajo (por defecto, ``cerrar``)."""
		self.cerrar()


class EscritorZip(Escritor):
	def __init__(self, ruta: str, nivel: str = "normal", metodo: str = "deflate") -> None:
		super().__init__(ruta)
		self._nivel = _NIVEL_ZLIB[nivel]
		self._metodo = metodo
		self._zip: zipfile.ZipFile | None = zipfile.ZipFile(rutas.con_prefijo_largo(ruta), "w", zipfile.ZIP_DEFLATED,
			strict_timestamps=False)

	def agregar(self, fuente: Fuente, cancelacion=None, al_avanzar=None) -> None:
		assert self._zip is not None
		if fuente.es_carpeta:
			self._zip.mkdir(info_carpeta_zip(fuente.nombre, fuente.modificado))
			return
		info = info_archivo_zip(fuente.nombre, fuente.modificado, self._nivel, fuente.atributos, self._metodo)
		info.file_size = fuente.tamano
		with fuente.proveedor.abrir_lectura(fuente.ruta) as flujo, self._zip.open(info, "w",
				force_zip64=fuente.tamano > 0x7FFFFFFF) as salida:
			lector = _Progreso(flujo, cancelacion, al_avanzar)
			while datos := lector.read(BLOQUE):
				salida.write(datos)

	def cerrar(self, cancelacion=None, al_avanzar=None) -> None:
		archivo, self._zip = self._zip, None
		if archivo is not None:
			archivo.close()


class EscritorTar(Escritor):
	def __init__(self, ruta: str, formato: str = "tar", nivel: str = "normal") -> None:
		super().__init__(ruta)
		compresion = formato.partition(".")[2]
		modo = f"w:{compresion}" if compresion else "w"
		opciones: dict = {}
		if compresion in ("gz", "bz2"):
			nivel_zlib = _NIVEL_ZLIB[nivel]
			opciones["compresslevel"] = max(1, nivel_zlib) if compresion == "bz2" else nivel_zlib
		elif compresion == "xz":
			opciones["preset"] = _NIVEL_XZ[nivel]
		elif compresion == "zst":
			opciones["level"] = _NIVEL_ZSTD[nivel]
		self._tar: tarfile.TarFile | None = tarfile.open(rutas.con_prefijo_largo(ruta), modo, format=tarfile.PAX_FORMAT,
			**opciones)

	def agregar(self, fuente: Fuente, cancelacion=None, al_avanzar=None) -> None:
		assert self._tar is not None
		info = tarfile.TarInfo(fuente.nombre)
		info.mtime = int(fuente.modificado) if fuente.modificado > 0 else 0
		if fuente.es_carpeta:
			info.type = tarfile.DIRTYPE
			info.mode = 0o755
			self._tar.addfile(info)
			return
		info.mode = 0o444 if fuente.atributos & 0x1 else 0o644
		with fuente.proveedor.abrir_lectura(fuente.ruta) as flujo:
			if fuente.tamano < 0:
				raise base.ErrorArchivos(_("No se conoce el tamaño de {n}.").format(n=fuente.nombre), fuente.ruta)
			info.size = fuente.tamano
			self._tar.addfile(info, _Progreso(flujo, cancelacion, al_avanzar))

	def cerrar(self, cancelacion=None, al_avanzar=None) -> None:
		archivo, self._tar = self._tar, None
		if archivo is not None:
			archivo.close()


class Escritor7z(Escritor):
	"""7z con py7zr 0.11.3: escribe desde rutas locales (no admite flujos), así que lo no local pasa por un temporal."""

	def __init__(self, ruta: str, nivel: str = "normal", contrasena: str | None = None, cifrar_nombres: bool = False) -> None:
		super().__init__(ruta)
		import py7zr
		from py7zr.properties import FILTER_COPY, FILTER_CRYPTO_AES256_SHA256, FILTER_LZMA2

		filtros = [{"id": FILTER_COPY}] if nivel == "sin" else [{"id": FILTER_LZMA2, "preset": _NIVEL_7Z[nivel]}]
		if contrasena:
			filtros.append({"id": FILTER_CRYPTO_AES256_SHA256})
		self._7z = py7zr.SevenZipFile(rutas.con_prefijo_largo(ruta), "w", filters=filtros, password=contrasena or None,
			header_encryption=bool(contrasena and cifrar_nombres))
		self._carpeta_vacia: str | None = None

	def _local(self, fuente: Fuente, cancelacion, al_avanzar) -> tuple[str, bool]:
		"""Ruta local de la fuente y si es un temporal que hay que borrar."""
		local = fuente.proveedor.ruta_local(fuente.ruta) if fuente.proveedor.esquema == "local" else None
		if local:
			return local, False
		temporal = temporales.ruta_temporal(fuente.nombre.rpartition("/")[2])
		with fuente.proveedor.abrir_lectura(fuente.ruta) as flujo, open(temporal, "wb") as salida:
			lector = _Progreso(flujo, cancelacion, None)
			while datos := lector.read(BLOQUE):
				salida.write(datos)
		if fuente.modificado > 0:
			os.utime(temporal, (fuente.modificado, fuente.modificado))
		return temporal, True

	def agregar(self, fuente: Fuente, cancelacion=None, al_avanzar=None) -> None:
		base.comprobar(cancelacion)
		if fuente.es_carpeta:
			local = fuente.proveedor.ruta_local(fuente.ruta) if fuente.proveedor.esquema == "local" else None
			if not local:
				if self._carpeta_vacia is None:
					self._carpeta_vacia = tempfile.mkdtemp(dir=str(temporales.carpeta_temporal()))
				local = self._carpeta_vacia
			self._7z.write(local, fuente.nombre)
			return
		local, borrar = self._local(fuente, cancelacion, al_avanzar)
		try:
			self._7z.write(local, fuente.nombre)
		finally:
			if borrar:
				temporales.borrar(local)
		if al_avanzar is not None:
			al_avanzar(fuente.tamano)

	def cerrar(self, cancelacion=None, al_avanzar=None) -> None:
		archivo, self._7z = self._7z, None
		if archivo is not None:
			archivo.close()
		if self._carpeta_vacia is not None:
			try:
				os.rmdir(self._carpeta_vacia)
			except OSError:
				log.debug("No se pudo borrar %s", self._carpeta_vacia, exc_info=True)
			self._carpeta_vacia = None


class Escritor7za(Escritor):
	"""7z o ZIP con AES-256 creados por 7za (8.4), con la contraseña por la entrada estándar.

	7za trabaja con archivos del disco: ``agregar`` solo anota las rutas de
	primer nivel (7za guarda cada una con su último componente y todo su
	contenido, que es justo el nombre que tiene en el comprimido). Lo que no
	está en el disco (un servidor, otro comprimido) se copia antes a una
	carpeta de ``data/temp`` con su nombre. El trabajo se hace en ``cerrar``,
	con el progreso real de 7za.
	"""

	diferido = True

	def __init__(self, ruta: str, formato: str = "7z", nivel: str = "normal", contrasena: str | None = None,
			cifrar_nombres: bool = False, ejecutable=None) -> None:
		super().__init__(ruta)
		self._ejecutable = ejecutable or _ruta_7za()
		if self._ejecutable is None:
			raise base.NoAdmitido(_("Falta 7za: Opciones, Componentes externos, Restaurar."), ruta)
		self._formato = formato
		self._nivel = nivel
		self._contrasena = contrasena or None
		self._cifrar_nombres = cifrar_nombres
		self._rutas: list[str] = []
		self._vistas: set[str] = set()
		self._preparada: str | None = None
		self._total = 0

	def _carpeta_preparada(self) -> str:
		if self._preparada is None:
			self._preparada = tempfile.mkdtemp(prefix="7za-", dir=str(temporales.carpeta_temporal()))
		return self._preparada

	def _anotar(self, ruta: str) -> None:
		if ruta.casefold() not in self._vistas:
			self._vistas.add(ruta.casefold())
			self._rutas.append(ruta)

	def agregar(self, fuente: Fuente, cancelacion=None, al_avanzar=None) -> None:
		base.comprobar(cancelacion)
		if not fuente.es_carpeta:
			self._total += max(0, fuente.tamano)
		local = fuente.proveedor.ruta_local(fuente.ruta) if fuente.proveedor.esquema == "local" else None
		if local and "/" not in fuente.nombre and os.path.basename(local.rstrip("\\/")) == fuente.nombre:
			self._anotar(local)
			return
		if local and "/" in fuente.nombre:
			primero = fuente.nombre.split("/", 1)[0]
			if any(os.path.basename(r).casefold() == primero.casefold() for r in self._rutas):
				# Ya va dentro de su carpeta de primer nivel: 7za la recorre entera.
				return
		# No está en el disco (o con otro nombre): se copia a la carpeta preparada con su nombre.
		destino = os.path.join(self._carpeta_preparada(), *fuente.nombre.split("/"))
		if fuente.es_carpeta:
			os.makedirs(destino, exist_ok=True)
		else:
			os.makedirs(os.path.dirname(destino), exist_ok=True)
			with fuente.proveedor.abrir_lectura(fuente.ruta) as flujo, open(rutas.con_prefijo_largo(destino), "wb") as salida:
				lector = _Progreso(flujo, cancelacion, None)
				while datos := lector.read(BLOQUE):
					salida.write(datos)
			if fuente.modificado > 0:
				os.utime(rutas.con_prefijo_largo(destino), (fuente.modificado, fuente.modificado))
		self._anotar(os.path.join(self._carpeta_preparada(), fuente.nombre.split("/", 1)[0]))

	def cerrar(self, cancelacion=None, al_avanzar=None) -> None:
		from app.services import siete_zip_externo

		try:
			if not self._rutas:
				raise base.ErrorArchivos(_("No hay nada que comprimir."), self.ruta)
			hecho = [0]

			def progreso(porcentaje: int) -> None:
				nuevo = self._total * porcentaje // 100
				if al_avanzar is not None and nuevo > hecho[0]:
					al_avanzar(nuevo - hecho[0])
				hecho[0] = max(hecho[0], nuevo)

			siete_zip_externo.crear(self._ejecutable, self.ruta, self._rutas, self._formato, self._nivel, self._contrasena,
				self._cifrar_nombres, cancelacion, progreso)
			if al_avanzar is not None and self._total > hecho[0]:
				al_avanzar(self._total - hecho[0])
		finally:
			self._soltar()

	def _soltar(self) -> None:
		preparada, self._preparada = self._preparada, None
		if preparada is not None:
			shutil.rmtree(preparada, ignore_errors=True)


class EscritorLibarchive(Escritor):
	"""ISO, cpio, XAR, ``.tar.lz``, ``.tar.lz4`` y ZIP con AES-256 (sin 7za) con libarchive."""

	def __init__(self, ruta: str, formato: str, nivel: str = "normal", contrasena: str | None = None) -> None:
		super().__init__(ruta)
		from app.services.libarchive import escritura

		self._escritor: escritura.EscritorArchive | None = escritura.EscritorArchive(rutas.con_prefijo_largo(ruta), formato, nivel,
			contrasena)

	def agregar(self, fuente: Fuente, cancelacion=None, al_avanzar=None) -> None:
		assert self._escritor is not None
		if fuente.es_carpeta:
			self._escritor.carpeta(fuente.nombre, fuente.modificado)
			return
		with fuente.proveedor.abrir_lectura(fuente.ruta) as flujo:
			self._escritor.archivo(fuente.nombre, fuente.tamano, fuente.modificado, flujo, bool(fuente.atributos & 0x1),
				lambda: base.comprobar(cancelacion), al_avanzar)

	def cerrar(self, cancelacion=None, al_avanzar=None) -> None:
		escritor, self._escritor = self._escritor, None
		if escritor is not None:
			escritor.cerrar()

	def _soltar(self) -> None:
		escritor, self._escritor = self._escritor, None
		if escritor is not None:
			try:
				escritor.cerrar()
			except base.ErrorArchivos:
				log.debug("Comprimido descartado sin terminar", exc_info=True)


class EscritorFlujo(Escritor):
	"""Un único archivo comprimido con gzip, bzip2, xz o Zstandard (``informe.pdf`` → ``informe.pdf.gz``)."""

	def __init__(self, ruta: str, formato: str, nivel: str = "normal") -> None:
		super().__init__(ruta)
		self._formato = formato
		self._nivel = nivel
		self._usado = False

	def _abrir(self):
		destino = rutas.con_prefijo_largo(self.ruta)
		if self._formato == "gz":
			return gzip.open(destino, "wb", compresslevel=max(1, _NIVEL_ZLIB[self._nivel]) if self._nivel != "sin" else 0)
		if self._formato == "bz2":
			return bz2.open(destino, "wb", compresslevel=max(1, _NIVEL_ZLIB[self._nivel]))
		if self._formato == "xz":
			return lzma.open(destino, "wb", preset=_NIVEL_XZ[self._nivel])
		from compression import zstd

		return zstd.open(destino, "wb", level=_NIVEL_ZSTD[self._nivel])

	def agregar(self, fuente: Fuente, cancelacion=None, al_avanzar=None) -> None:
		if fuente.es_carpeta:
			raise base.NoAdmitido(_("«{n}» es una carpeta: los formatos .gz, .bz2, .xz y .zst comprimen un solo archivo. "
				"Use ZIP, 7z o TAR para las carpetas.").format(n=fuente.nombre), fuente.ruta)
		if self._usado:
			raise base.NoAdmitido(_("Un archivo .{f} solo puede contener un archivo.").format(f=self._formato), fuente.ruta)
		self._usado = True
		with fuente.proveedor.abrir_lectura(fuente.ruta) as flujo, self._abrir() as salida:
			lector = _Progreso(flujo, cancelacion, al_avanzar)
			while datos := lector.read(BLOQUE):
				salida.write(datos)
		if fuente.modificado > 0:
			os.utime(rutas.con_prefijo_largo(self.ruta), (fuente.modificado, fuente.modificado))

	def cerrar(self, cancelacion=None, al_avanzar=None) -> None:
		if not self._usado:
			raise base.ErrorArchivos(_("No hay ningún archivo que comprimir."), self.ruta)


def crear_escritor(formato: str, ruta: str, nivel: str = "normal", contrasena: str | None = None, *, variante: str = "",
		cifrar_nombres: bool = False) -> Escritor:
	"""Escritor del formato pedido sobre ``ruta``.

	:param variante: solo ZIP: «zstd» (método 93) o «aes» (AES-256, necesita contraseña).
	:param cifrar_nombres: solo 7z con contraseña: cifra también el índice.
	"""
	if formato not in FORMATOS:
		raise ValueError(f"Formato desconocido: {formato}")
	if nivel not in NIVELES:
		raise ValueError(f"Nivel desconocido: {nivel}")
	if contrasena and not admite_contrasena(formato, variante):
		raise base.NoAdmitido(_("Solo los comprimidos 7z y los ZIP con AES pueden llevar contraseña."), ruta)
	if formato == "zip":
		if variante == "aes":
			if not contrasena:
				raise base.NoAdmitido(_("Un ZIP cifrado necesita una contraseña."), ruta)
			if _ruta_7za() is not None:
				return Escritor7za(ruta, "zip", nivel, contrasena)
			return EscritorLibarchive(ruta, "zip", nivel, contrasena)
		return EscritorZip(ruta, nivel, "zstd" if variante == "zstd" else metodo_zip_configurado())
	if formato == "7z":
		if _ruta_7za() is not None:
			return Escritor7za(ruta, "7z", nivel, contrasena, cifrar_nombres)
		return Escritor7z(ruta, nivel, contrasena, cifrar_nombres)
	if formato in CON_LIBARCHIVE:
		return EscritorLibarchive(ruta, formato, nivel)
	if formato in FLUJOS:
		return EscritorFlujo(ruta, formato, nivel)
	return EscritorTar(ruta, formato, nivel)
