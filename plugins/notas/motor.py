# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comentarios, notas de carpeta y etiquetas (diseño 2.0, 11.14). Sin wx.

- **Comentarios** compatibles con ``descript.ion`` (Total Commander, Double
  Commander, 4DOS): una línea por archivo, ``nombre comentario``, con el nombre
  entre comillas si tiene espacios. Los comentarios de varias líneas se guardan
  como hace Total Commander: ``\\n`` escrito y la marca ``\\x04\\xc2`` al final.
- **Nota de una carpeta**: es el comentario de la carpeta en el
  ``descript.ion`` de su carpeta superior (así la ven también los demás
  gestores); la raíz de una unidad, que no tiene superior, va a la base.
- **Base central** (``datos/notas.db``, SQLite de la biblioteca estándar): las
  etiquetas, y los comentarios de las carpetas en las que no se puede escribir
  (solo lectura, red sin permiso) o todos si ``almacen = base_central``.
"""

from __future__ import annotations

import codecs
import ctypes
import logging
import os
import sqlite3
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from app.plugins import api

_ = api.traduccion("zc.notas")[0]
log = logging.getLogger("zcplugins.zc.notas")

DESCRIPT = "descript.ion"
MARCA_MULTILINEA = "\x04\xc2"
COLORES = ("rojo", "naranja", "amarillo", "verde", "azul", "morado", "gris", "")
ETIQUETAS_DE_FABRICA = [{"nombre": "Urgente", "color": "rojo"}, {"nombre": "Importante", "color": "naranja"},
	{"nombre": "Facturas", "color": "verde"}, {"nombre": "Pendiente", "color": "azul"}]


def textos_colores() -> list[str]:
	return [_("&Rojo"), _("&Naranja"), _("&Amarillo"), _("&Verde"), _("A&zul"), _("&Morado"), _("&Gris"), _("&Sin color")]


def nombre_color(color: str) -> str:
	if color not in COLORES:
		return color
	return textos_colores()[COLORES.index(color)].replace("&", "").lower()


def clave(ruta: str) -> str:
	"""Ruta comparable (Windows no distingue mayúsculas ni separadores)."""
	return os.path.normcase(os.path.normpath(os.path.abspath(ruta)))


# ── descript.ion ─────────────────────────────────────────────────────────────


def _desescapar(comentario: str) -> str:
	if comentario.endswith(MARCA_MULTILINEA):
		return comentario[: -len(MARCA_MULTILINEA)].replace("\\n", "\n")
	return comentario


def _escapar(comentario: str) -> str:
	comentario = comentario.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
	if "\n" in comentario:
		return comentario.replace("\n", "\\n") + MARCA_MULTILINEA
	return comentario


def analizar_linea(linea: str) -> tuple[str, str] | None:
	"""``"mi archivo.txt" comentario`` o ``archivo.txt comentario`` → (nombre, comentario)."""
	linea = linea.rstrip("\r\n")
	if not linea.strip():
		return None
	if linea.startswith('"'):
		fin = linea.find('"', 1)
		if fin < 0:
			return None
		nombre, resto = linea[1:fin], linea[fin + 1:]
	else:
		partes = linea.replace("\t", " ").split(" ", 1)
		nombre, resto = partes[0], partes[1] if len(partes) > 1 else ""
	if not nombre:
		return None
	return nombre, _desescapar(resto.lstrip(" \t"))


def formar_linea(nombre: str, comentario: str) -> str:
	nombre_escrito = f'"{nombre}"' if (" " in nombre or "\t" in nombre) else nombre
	return f"{nombre_escrito} {_escapar(comentario)}"


@dataclass
class Descript:
	"""Contenido de un ``descript.ion``: nombre plegado → (nombre, comentario), en el orden del archivo."""

	entradas: dict[str, tuple[str, str]]
	codificacion: str = "utf-8-sig"


def decodificar(datos: bytes) -> tuple[str, str]:
	"""(texto, codificación): UTF-8 con BOM, UTF-8 sin BOM o, si no lo es, la página ANSI de Windows."""
	if datos.startswith(codecs.BOM_UTF8):
		return datos[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace"), "utf-8-sig"
	try:
		return datos.decode("utf-8"), "utf-8"
	except UnicodeDecodeError:
		try:
			return datos.decode("mbcs"), "mbcs"
		except (LookupError, UnicodeDecodeError):
			return datos.decode("cp1252", errors="replace"), "cp1252"


def leer_descript(carpeta: str) -> Descript:
	ruta = os.path.join(carpeta, DESCRIPT)
	try:
		with open(ruta, "rb") as archivo:
			texto, codificacion = decodificar(archivo.read())
	except FileNotFoundError:
		return Descript({})
	entradas: dict[str, tuple[str, str]] = {}
	for linea in texto.splitlines():
		par = analizar_linea(linea)
		if par is not None:
			entradas[par[0].casefold()] = par
	return Descript(entradas, codificacion)


def _ocultar(ruta: str) -> None:
	try:
		atributos = ctypes.windll.kernel32.GetFileAttributesW(ruta)
		if atributos != -1 and atributos != 0xFFFFFFFF:
			ctypes.windll.kernel32.SetFileAttributesW(ruta, atributos | 0x2)
	except (AttributeError, OSError):
		log.debug("No se pudo ocultar %s", ruta, exc_info=True)


def escribir_descript(carpeta: str, descript: Descript) -> None:
	"""Escribe el ``descript.ion`` (o lo borra si se queda vacío).

	Un archivo oculto existente no se puede abrir con «w» en Windows
	(``CREATE_ALWAYS`` falla con los ocultos): se reescribe en su sitio con «r+».
	"""
	ruta = os.path.join(carpeta, DESCRIPT)
	if not descript.entradas:
		if os.path.exists(ruta):
			os.remove(ruta)
		return
	texto = "\r\n".join(formar_linea(n, c) for n, c in descript.entradas.values()) + "\r\n"
	codificacion = descript.codificacion
	try:
		datos = texto.encode(codificacion)
	except (UnicodeEncodeError, LookupError):
		codificacion = "utf-8-sig"
		datos = texto.encode(codificacion)
	if os.path.exists(ruta):
		with open(ruta, "r+b") as archivo:
			archivo.write(datos)
			archivo.truncate()
	else:
		with open(ruta, "xb") as archivo:
			archivo.write(datos)
		_ocultar(ruta)


# ── Almacén ──────────────────────────────────────────────────────────────────


class Almacen:
	"""Comentarios y etiquetas, con ``descript.ion`` y la base central. Se puede usar desde cualquier hilo."""

	def __init__(self, base: Path | Callable[[], Path], modo: Callable[[], str] | str = "descript_ion") -> None:
		# La ruta de la base se pide al usarla: activar el complemento no crea nada en ``datos``.
		self._base_ruta = base if callable(base) else (lambda: Path(base))
		self._modo = modo if callable(modo) else (lambda: modo)
		self._candado = threading.RLock()
		self._cache: dict[str, tuple[float, int, Descript]] = {}
		self._creada = False
		#: Copia en memoria de la base (comentarios y etiquetas por clave): las columnas
		#: la consultan una vez por archivo y abrir SQLite cada vez sería lento.
		self._memoria: tuple[dict[str, str], dict[str, list[str]]] | None = None

	@property
	def base(self) -> Path:
		return Path(self._base_ruta())

	@property
	def modo(self) -> str:
		return self._modo()

	# Base ----------------------------------------------------------------------

	def _conexion(self) -> sqlite3.Connection:
		self.base.parent.mkdir(parents=True, exist_ok=True)
		conexion = sqlite3.connect(self.base, timeout=5)
		if not self._creada:
			conexion.executescript(
				"CREATE TABLE IF NOT EXISTS comentarios (clave TEXT PRIMARY KEY, ruta TEXT NOT NULL, texto TEXT NOT NULL);"
				"CREATE TABLE IF NOT EXISTS etiquetas (clave TEXT NOT NULL, ruta TEXT NOT NULL, etiqueta TEXT NOT NULL,"
				" PRIMARY KEY (clave, etiqueta));")
			self._creada = True
		return conexion

	def _consulta(self, sql: str, parametros: Iterable = ()) -> list[tuple]:
		with self._candado:
			if not sql.lstrip().upper().startswith("SELECT"):
				self._memoria = None
			conexion = self._conexion()
			try:
				with conexion:
					return list(conexion.execute(sql, tuple(parametros)))
			finally:
				conexion.close()

	def _base(self) -> tuple[dict[str, str], dict[str, list[str]]]:
		with self._candado:
			if self._memoria is None:
				comentarios = {c: t for c, t in self._consulta("SELECT clave, texto FROM comentarios")}
				etiquetas: dict[str, list[str]] = {}
				for c, e in self._consulta("SELECT clave, etiqueta FROM etiquetas ORDER BY etiqueta"):
					etiquetas.setdefault(c, []).append(e)
				self._memoria = (comentarios, etiquetas)
			return self._memoria

	# descript.ion con caché por fecha y tamaño ---------------------------------

	def _descript(self, carpeta: str) -> Descript:
		ruta = os.path.join(carpeta, DESCRIPT)
		try:
			datos = os.stat(ruta)
			firma = (datos.st_mtime, datos.st_size)
		except OSError:
			firma = (0.0, -1)
		with self._candado:
			guardado = self._cache.get(clave(carpeta))
			if guardado is not None and guardado[:2] == firma:
				return guardado[2]
		descript = leer_descript(carpeta) if firma[1] >= 0 else Descript({})
		with self._candado:
			self._cache[clave(carpeta)] = (*firma, descript)
		return descript

	def _olvidar(self, carpeta: str) -> None:
		with self._candado:
			self._cache.pop(clave(carpeta), None)

	@staticmethod
	def _partir(ruta: str) -> tuple[str, str]:
		ruta = os.path.normpath(os.path.abspath(ruta))
		carpeta, nombre = os.path.split(ruta)
		return carpeta, nombre

	# Comentarios ---------------------------------------------------------------

	def comentario(self, ruta: str) -> str:
		"""Comentario de un archivo o carpeta (la nota de una carpeta es su comentario)."""
		carpeta, nombre = self._partir(ruta)
		de_base = self._base()[0].get(clave(ruta), "")
		if self.modo == "base_central" and de_base:
			return de_base
		if nombre:
			try:
				par = self._descript(carpeta).entradas.get(nombre.casefold())
			except OSError:
				par = None
			if par is not None and par[1]:
				return par[1]
		return de_base

	def fijar_comentario(self, ruta: str, texto: str) -> str:
		"""Guarda (o borra, con texto vacío) el comentario. Devuelve dónde quedó: ``descript_ion`` o ``base_central``."""
		texto = texto.replace("\r\n", "\n").strip()
		carpeta, nombre = self._partir(ruta)
		destino = "base_central"
		if self.modo == "descript_ion" and nombre:
			try:
				self._escribir_descript(carpeta, nombre, texto)
				destino = "descript_ion"
			except OSError:
				log.info("No se puede escribir descript.ion en %s; el comentario va a la base central", carpeta, exc_info=True)
		if destino == "base_central":
			if texto:
				self._consulta("INSERT OR REPLACE INTO comentarios (clave, ruta, texto) VALUES (?, ?, ?)", (clave(ruta), ruta, texto))
			else:
				self._consulta("DELETE FROM comentarios WHERE clave = ?", (clave(ruta),))
			if nombre:
				try:
					if nombre.casefold() in self._descript(carpeta).entradas:
						self._escribir_descript(carpeta, nombre, "")
				except OSError:
					log.debug("No se pudo quitar el comentario antiguo de %s", ruta, exc_info=True)
		else:
			self._consulta("DELETE FROM comentarios WHERE clave = ?", (clave(ruta),))
		return destino

	def _escribir_descript(self, carpeta: str, nombre: str, texto: str) -> None:
		with self._candado:
			self._olvidar(carpeta)
			descript = leer_descript(carpeta)
			if texto:
				descript.entradas[nombre.casefold()] = (nombre, texto)
			elif descript.entradas.pop(nombre.casefold(), None) is None:
				return
			escribir_descript(carpeta, descript)
			self._olvidar(carpeta)

	# Etiquetas -----------------------------------------------------------------

	def etiquetas(self, ruta: str) -> list[str]:
		return list(self._base()[1].get(clave(ruta), []))

	def etiquetar(self, ruta: str, etiqueta: str) -> None:
		etiqueta = etiqueta.strip()
		if etiqueta:
			self._consulta("INSERT OR IGNORE INTO etiquetas (clave, ruta, etiqueta) VALUES (?, ?, ?)", (clave(ruta), ruta, etiqueta))

	def quitar_etiqueta(self, ruta: str, etiqueta: str) -> None:
		self._consulta("DELETE FROM etiquetas WHERE clave = ? AND etiqueta = ?", (clave(ruta), etiqueta))

	def con_etiqueta(self, etiqueta: str) -> list[str]:
		return [f[0] for f in self._consulta("SELECT ruta FROM etiquetas WHERE etiqueta = ? ORDER BY ruta", (etiqueta,))]

	# Viajar al copiar y mover --------------------------------------------------

	def copiar(self, origen: str, destino: str, mover: bool = False) -> None:
		"""El comentario y las etiquetas de ``origen`` (y de lo que tenga dentro en la base) pasan a ``destino``.

		Los comentarios de lo que hay DENTRO de una carpeta viajan solos, con su
		``descript.ion`` (es un archivo más de la carpeta).
		"""
		comentario = self.comentario(origen)
		if comentario:
			self.fijar_comentario(destino, comentario)
			if mover and os.path.normcase(os.path.dirname(os.path.abspath(origen))) != os.path.normcase(os.path.dirname(os.path.abspath(destino))):
				carpeta, nombre = self._partir(origen)
				try:
					if os.path.isdir(carpeta):
						self._escribir_descript(carpeta, nombre, "")
				except OSError:
					log.debug("No se pudo quitar el comentario de %s tras moverlo", origen, exc_info=True)
		clave_origen, clave_destino = clave(origen), clave(destino)
		prefijo = clave_origen.rstrip("\\") + "\\"
		filas = self._consulta("SELECT clave, ruta, etiqueta FROM etiquetas WHERE clave = ? OR substr(clave, 1, ?) = ?",
			(clave_origen, len(prefijo), prefijo))
		comentarios = self._consulta("SELECT clave, ruta, texto FROM comentarios WHERE substr(clave, 1, ?) = ?", (len(prefijo), prefijo))
		for clave_fila, ruta, etiqueta in filas:
			nueva_ruta = destino + ruta[len(origen):] if clave_fila != clave_origen else destino
			self._consulta("INSERT OR IGNORE INTO etiquetas (clave, ruta, etiqueta) VALUES (?, ?, ?)",
				(clave_destino + clave_fila[len(clave_origen):], nueva_ruta, etiqueta))
		for clave_fila, ruta, texto in comentarios:
			self._consulta("INSERT OR REPLACE INTO comentarios (clave, ruta, texto) VALUES (?, ?, ?)",
				(clave_destino + clave_fila[len(clave_origen):], destino + ruta[len(origen):], texto))
		if mover:
			self._consulta("DELETE FROM etiquetas WHERE clave = ? OR substr(clave, 1, ?) = ?", (clave_origen, len(prefijo), prefijo))
			self._consulta("DELETE FROM comentarios WHERE substr(clave, 1, ?) = ?", (len(prefijo), prefijo))

	# Buscar --------------------------------------------------------------------

	def buscar(self, carpeta: str, texto: str = "", etiqueta: str = "", subcarpetas: bool = True, cancelacion=None) -> list[str]:
		"""Rutas bajo ``carpeta`` con un comentario que contiene ``texto`` y con ``etiqueta`` (lo que se pida)."""
		texto = texto.casefold().strip()
		base = clave(carpeta).rstrip("\\") + "\\"
		con_etiqueta: set[str] | None = None
		if etiqueta:
			con_etiqueta = {clave(r) for r in self.con_etiqueta(etiqueta)}
		encontrados: dict[str, str] = {}
		if texto:
			for raiz, carpetas, _archivos in os.walk(carpeta):
				api.comprobar(cancelacion)
				carpetas[:] = [c for c in carpetas if not _es_enlace(os.path.join(raiz, c))] if subcarpetas else []
				try:
					descript = self._descript(raiz)
				except OSError:
					continue
				for nombre, comentario in descript.entradas.values():
					if texto in comentario.casefold():
						ruta = os.path.join(raiz, nombre)
						encontrados.setdefault(clave(ruta), ruta)
			for clave_fila, ruta, comentario in self._consulta("SELECT clave, ruta, texto FROM comentarios WHERE substr(clave, 1, ?) = ?",
					(len(base), base)):
				if texto in comentario.casefold() and (subcarpetas or os.path.dirname(clave_fila) == base.rstrip("\\")):
					encontrados.setdefault(clave_fila, ruta)
			if con_etiqueta is not None:
				encontrados = {k: v for k, v in encontrados.items() if k in con_etiqueta}
		elif con_etiqueta is not None:
			for ruta in self.con_etiqueta(etiqueta):
				clave_ruta = clave(ruta)
				if clave_ruta.startswith(base) and (subcarpetas or os.path.dirname(clave_ruta) == base.rstrip("\\")):
					encontrados.setdefault(clave_ruta, ruta)
		return sorted((r for r in encontrados.values() if os.path.exists(r)), key=str.casefold)


def _es_enlace(ruta: str) -> bool:
	return os.path.islink(ruta) or os.path.isjunction(ruta)


def texto_etiquetas(nombres: list[str], definidas: list[dict]) -> str:
	"""«Urgente (rojo), Facturas (verde)»: el color siempre en texto, nunca solo como color (15.2)."""
	colores = {str(d.get("nombre", "")).casefold(): str(d.get("color", "")) for d in definidas if isinstance(d, dict)}
	partes = []
	for nombre in nombres:
		color = nombre_color(colores.get(nombre.casefold(), ""))
		partes.append(f"{nombre} ({color})" if color and color != nombre_color("") else nombre)
	return ", ".join(partes)


def primera_linea(texto: str) -> str:
	return texto.strip().splitlines()[0] if texto.strip() else ""
