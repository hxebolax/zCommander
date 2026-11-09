# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Reglas automáticas, registro de lo hecho y deshacer (diseño 2.0, 11.18). Sin wx.

Una regla dice «si el archivo coincide con el patrón, el tamaño y la
antigüedad, entonces mover, copiar, renombrar con máscara, extraer, etiquetar
o ejecutar una orden». Se aplica **la primera regla activa que coincide**
(en el orden de la lista): así el resultado es predecible y un archivo movido
no lo vuelve a tocar otra regla.

Todo lo que toca archivos corre en un hilo de trabajo (el del monitor o el de
la operación); la orden se devuelve aparte para que la ejecute el hilo de la
interfaz (``zc.ejecutar_orden``). Las acciones se hacen en el disco local: las
carpetas vigiladas lo son (``ReadDirectoryChangesW`` solo funciona en disco
local y carpetas compartidas de Windows).
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import shutil
import tarfile
import threading
import time
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("zcplugins.zc.monitor")

MOVER, COPIAR, RENOMBRAR, EXTRAER, ETIQUETAR, ORDEN = "mover", "copiar", "renombrar", "extraer", "etiquetar", "orden"
ACCIONES = {
	MOVER: "Mover a una carpeta",
	COPIAR: "Copiar a una carpeta",
	RENOMBRAR: "Renombrar con una máscara",
	EXTRAER: "Extraer el comprimido",
	ETIQUETAR: "Poner una etiqueta",
	ORDEN: "Ejecutar una orden o una macro",
}
EXTENSIONES_COMPRIMIDOS = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".7z")
ARCHIVO_REGISTRO = "registro.json"
MAXIMO_REGISTRO = 500


class ErrorRegla(Exception):
	"""Una acción que no se pudo hacer (mensaje en español)."""


@dataclass
class Regla:
	nombre: str
	patron: str = "*"
	carpeta: str = ""  # vacío: cualquier carpeta vigilada
	tamano_min_kb: int = 0
	tamano_max_kb: int = 0  # 0: sin límite
	antiguedad_dias: int = 0  # 0: cualquier antigüedad
	accion: str = MOVER
	destino: str = ""  # carpeta de mover, copiar y extraer (vacío al extraer: junto al comprimido)
	mascara: str = ""  # renombrar: plantilla del renombrado múltiple, como «[N]_[Y]-[M]-[D]»
	etiqueta: str = ""
	orden: str = ""  # id de la orden («macro:Fotos a la copia», «zc.reproductor:reproducir»...)
	activa: bool = True

	@classmethod
	def desde(cls, datos: dict) -> Regla:
		regla = cls(**{k: v for k, v in datos.items() if k in cls.__dataclass_fields__})
		if regla.accion not in ACCIONES:
			raise ValueError(f"Acción desconocida: {regla.accion}")
		return regla

	def condicion(self) -> str:
		partes = [f"nombre {self.patron or '*'}"]
		if self.carpeta:
			partes.append(f"en {self.carpeta}")
		if self.tamano_min_kb:
			partes.append(f"de {self.tamano_min_kb} KB o más")
		if self.tamano_max_kb:
			partes.append(f"de {self.tamano_max_kb} KB o menos")
		if self.antiguedad_dias:
			partes.append(f"con {self.antiguedad_dias} días o más")
		return ", ".join(partes)

	def efecto(self) -> str:
		if self.accion in (MOVER, COPIAR):
			return f"{ACCIONES[self.accion]}: {self.destino}"
		if self.accion == EXTRAER:
			return f"{ACCIONES[EXTRAER]} en {self.destino or 'su carpeta'}"
		if self.accion == RENOMBRAR:
			return f"{ACCIONES[RENOMBRAR]}: {self.mascara}"
		if self.accion == ETIQUETAR:
			return f"{ACCIONES[ETIQUETAR]}: {self.etiqueta}"
		return f"{ACCIONES[ORDEN]}: {self.orden}"

	def error(self) -> str:
		"""Qué le falta a la regla para poder aplicarse ("" si está completa)."""
		if not self.nombre.strip():
			return "La regla necesita un nombre."
		if self.accion in (MOVER, COPIAR) and not self.destino.strip():
			return "Escriba la carpeta de destino."
		if self.accion == RENOMBRAR and not self.mascara.strip():
			return "Escriba la máscara del nombre nuevo."
		if self.accion == ETIQUETAR and not self.etiqueta.strip():
			return "Escriba la etiqueta."
		if self.accion == ORDEN and not self.orden.strip():
			return "Escriba la orden o la macro."
		if self.tamano_max_kb and self.tamano_min_kb > self.tamano_max_kb:
			return "El tamaño mínimo es mayor que el máximo."
		return ""


def leer_reglas(lista: Iterable) -> list[Regla]:
	reglas = []
	for datos in lista or []:
		try:
			reglas.append(Regla.desde(dict(datos)))
		except (TypeError, ValueError):
			log.warning("Regla del monitor no válida: %r", datos)
	return reglas


def a_lista(reglas: Iterable[Regla]) -> list[dict]:
	return [asdict(r) for r in reglas]


def _clave(ruta: str) -> str:
	return os.path.normcase(os.path.normpath(ruta))


def coincide(regla: Regla, ruta: str, carpeta_vigilada: str, tamano: int, modificado: float, ahora: float | None = None) -> bool:
	if not regla.activa:
		return False
	if regla.carpeta and _clave(regla.carpeta) != _clave(carpeta_vigilada):
		return False
	nombre = os.path.basename(ruta).casefold()
	patrones = [p.strip().casefold() for p in (regla.patron or "*").split(";") if p.strip()] or ["*"]
	if not any(fnmatch.fnmatch(nombre, p) for p in patrones):
		return False
	if regla.tamano_min_kb and tamano < regla.tamano_min_kb * 1024:
		return False
	if regla.tamano_max_kb and tamano > regla.tamano_max_kb * 1024:
		return False
	ahora = time.time() if ahora is None else ahora
	return not (regla.antiguedad_dias and ahora - modificado < regla.antiguedad_dias * 86400)


def primera_que_coincide(reglas: Iterable[Regla], ruta: str, carpeta_vigilada: str, tamano: int, modificado: float,
		ahora: float | None = None) -> Regla | None:
	return next((r for r in reglas if coincide(r, ruta, carpeta_vigilada, tamano, modificado, ahora)), None)


# ── Acciones ─────────────────────────────────────────────────────────────────


@dataclass
class Hecho:
	"""Lo que hizo una regla con un archivo."""

	regla: str
	accion: str
	archivo: str
	texto: str
	ok: bool = True
	deshacer: dict | None = None  # {"tipo": "mover"|"renombrar"|"copiar", "origen": ..., "destino": ...}
	orden: str = ""  # para la interfaz: orden que hay que ejecutar con ``argumento`` = archivo
	nueva_ruta: str = ""


def libre(ruta: str) -> str:
	"""``ruta`` si no existe; si existe, «nombre (2).ext», «nombre (3).ext»..."""
	if not os.path.lexists(ruta):
		return ruta
	carpeta, nombre = os.path.split(ruta)
	base, extension = os.path.splitext(nombre)
	for numero in range(2, 10000):
		candidata = os.path.join(carpeta, f"{base} ({numero}){extension}")
		if not os.path.lexists(candidata):
			return candidata
	raise ErrorRegla(f"No hay un nombre libre para {nombre} en {carpeta}")


def _miembro_seguro(nombre: str) -> bool:
	partes = nombre.replace("\\", "/").split("/")
	return not (nombre.startswith(("/", "\\")) or ":" in nombre or ".." in partes)


def extraer(ruta: str, destino: str) -> str:
	"""Extrae ZIP, TAR (con gzip, bzip2 o xz) o 7z en ``destino\\<nombre sin extensión>``, sin salir de esa carpeta."""
	nombre = os.path.basename(ruta)
	minusculas = nombre.casefold()
	extension = next((e for e in sorted(EXTENSIONES_COMPRIMIDOS, key=len, reverse=True) if minusculas.endswith(e)), "")
	if not extension:
		raise ErrorRegla(f"{nombre} no es un comprimido que se pueda extraer")
	carpeta = libre(os.path.join(destino, nombre[: -len(extension)] or nombre))
	os.makedirs(carpeta)
	try:
		if extension == ".zip":
			with zipfile.ZipFile(ruta) as comprimido:
				miembros = [m for m in comprimido.namelist() if _miembro_seguro(m)]
				comprimido.extractall(carpeta, miembros)
		elif extension == ".7z":
			import py7zr

			with py7zr.SevenZipFile(ruta) as comprimido:
				miembros = [m for m in comprimido.getnames() if _miembro_seguro(m)]
				comprimido.extract(carpeta, targets=miembros)
		else:
			with tarfile.open(ruta) as comprimido:
				comprimido.extractall(carpeta, filter="data")
	except (OSError, zipfile.BadZipFile, tarfile.TarError, ValueError) as error:
		shutil.rmtree(carpeta, ignore_errors=True)
		raise ErrorRegla(f"No se pudo extraer {nombre}: {error}") from error
	except Exception as error:  # noqa: BLE001 - py7zr lanza sus propias clases
		shutil.rmtree(carpeta, ignore_errors=True)
		raise ErrorRegla(f"No se pudo extraer {nombre}: {error}") from error
	return carpeta


@dataclass
class Herramientas:
	"""Lo que las acciones necesitan del complemento (así se prueban sin zCommander)."""

	evaluar_mascara: Callable[[str, str], str] | None = None  # (máscara, ruta) → nombre nuevo
	etiquetar: Callable[[str, str], None] | None = None  # (ruta, etiqueta); None: falta zc.notas


def aplicar(regla: Regla, ruta: str, herramientas: Herramientas | None = None, simular: bool = False) -> Hecho:
	"""Aplica ``regla`` a ``ruta``. Con ``simular`` solo describe lo que haría. Lanza ``ErrorRegla``."""
	herramientas = herramientas or Herramientas()
	nombre = os.path.basename(ruta)
	try:
		if regla.accion in (MOVER, COPIAR):
			destino = libre(os.path.join(regla.destino, nombre))
			verbo = "movido" if regla.accion == MOVER else "copiado"
			if simular:
				return Hecho(regla.nombre, regla.accion, ruta, f"Se {'movería' if regla.accion == MOVER else 'copiaría'} a {regla.destino}")
			os.makedirs(regla.destino, exist_ok=True)
			if regla.accion == MOVER:
				shutil.move(ruta, destino)
				return Hecho(regla.nombre, MOVER, ruta, f"{verbo} a {regla.destino}", deshacer={"tipo": MOVER, "origen": ruta,
					"destino": destino}, nueva_ruta=destino)
			shutil.copy2(ruta, destino)
			return Hecho(regla.nombre, COPIAR, ruta, f"{verbo} a {regla.destino}", deshacer={"tipo": COPIAR, "origen": ruta,
				"destino": destino}, nueva_ruta=ruta)
		if regla.accion == RENOMBRAR:
			if herramientas.evaluar_mascara is None:
				raise ErrorRegla("No se pueden evaluar máscaras de renombrado aquí")
			nuevo = herramientas.evaluar_mascara(regla.mascara, ruta).strip()
			if not nuevo or any(c in nuevo for c in '<>:"/\\|?*'):
				raise ErrorRegla(f"La máscara da un nombre no válido: «{nuevo}»")
			if nuevo == nombre:
				return Hecho(regla.nombre, RENOMBRAR, ruta, "ya tiene ese nombre", nueva_ruta=ruta)
			destino = libre(os.path.join(os.path.dirname(ruta), nuevo))
			if simular:
				return Hecho(regla.nombre, RENOMBRAR, ruta, f"Se renombraría a {os.path.basename(destino)}")
			os.rename(ruta, destino)
			return Hecho(regla.nombre, RENOMBRAR, ruta, f"renombrado a {os.path.basename(destino)}",
				deshacer={"tipo": RENOMBRAR, "origen": ruta, "destino": destino}, nueva_ruta=destino)
		if regla.accion == EXTRAER:
			destino = regla.destino or os.path.dirname(ruta)
			if simular:
				return Hecho(regla.nombre, EXTRAER, ruta, f"Se extraería en {destino}")
			carpeta = extraer(ruta, destino)
			return Hecho(regla.nombre, EXTRAER, ruta, f"extraído en {carpeta}", nueva_ruta=ruta)
		if regla.accion == ETIQUETAR:
			if simular:
				return Hecho(regla.nombre, ETIQUETAR, ruta, f"Se etiquetaría como {regla.etiqueta}")
			if herramientas.etiquetar is None:
				raise ErrorRegla("Para etiquetar hace falta el complemento Notas, comentarios y etiquetas")
			herramientas.etiquetar(ruta, regla.etiqueta)
			return Hecho(regla.nombre, ETIQUETAR, ruta, f"etiquetado como {regla.etiqueta}", nueva_ruta=ruta)
		if simular:
			return Hecho(regla.nombre, ORDEN, ruta, f"Se ejecutaría {regla.orden}")
		return Hecho(regla.nombre, ORDEN, ruta, f"se ejecuta {regla.orden}", orden=regla.orden, nueva_ruta=ruta)
	except OSError as error:
		raise ErrorRegla(f"{nombre}: {error.strerror or error}") from error


def simular(reglas: Iterable[Regla], carpeta: str, ahora: float | None = None) -> list[Hecho]:
	"""Qué harían las reglas con lo que ya hay en ``carpeta`` (sin tocar nada)."""
	reglas = list(reglas)
	resultado = []
	try:
		elementos = sorted(os.scandir(carpeta), key=lambda e: e.name.casefold())
	except OSError as error:
		raise ErrorRegla(f"No se puede leer {carpeta}: {error.strerror or error}") from error
	for elemento in elementos:
		if not elemento.is_file(follow_symlinks=False):
			continue
		info = elemento.stat()
		regla = primera_que_coincide(reglas, elemento.path, carpeta, info.st_size, info.st_mtime, ahora)
		if regla is not None:
			resultado.append(aplicar(regla, elemento.path, simular=True))
	return resultado


# ── Registro y deshacer ──────────────────────────────────────────────────────


@dataclass
class Apunte:
	fecha: float
	carpeta: str
	archivo: str
	regla: str
	texto: str
	ok: bool = True
	deshacer: dict | None = None
	deshecho: bool = False


@dataclass
class Registro:
	"""Lo que ha hecho el monitor, en ``datos/registro.json`` (los últimos 500 apuntes)."""

	carpeta_datos: Path
	apuntes: list[Apunte] = field(default_factory=list)

	def __post_init__(self) -> None:
		self._candado = threading.Lock()
		self.carpeta_datos = Path(self.carpeta_datos)
		try:
			datos = json.loads((self.carpeta_datos / ARCHIVO_REGISTRO).read_text(encoding="utf-8"))
			self.apuntes = [Apunte(**{k: v for k, v in a.items() if k in Apunte.__dataclass_fields__}) for a in datos.get("apuntes", [])]
		except FileNotFoundError:
			self.apuntes = []
		except (OSError, ValueError, TypeError, AttributeError):
			log.warning("No se pudo leer el registro del monitor", exc_info=True)
			self.apuntes = []

	def _guardar(self) -> None:
		self.carpeta_datos.mkdir(parents=True, exist_ok=True)
		ruta = self.carpeta_datos / ARCHIVO_REGISTRO
		temporal = ruta.with_suffix(".tmp")
		temporal.write_text(json.dumps({"version": 1, "apuntes": [asdict(a) for a in self.apuntes]}, ensure_ascii=False, indent=1),
			encoding="utf-8")
		temporal.replace(ruta)

	def apuntar(self, carpeta: str, hecho: Hecho) -> Apunte:
		apunte = Apunte(time.time(), carpeta, hecho.archivo, hecho.regla, hecho.texto, hecho.ok, hecho.deshacer)
		with self._candado:
			self.apuntes.append(apunte)
			del self.apuntes[:-MAXIMO_REGISTRO]
			self._guardar()
		return apunte

	def vaciar(self) -> None:
		with self._candado:
			self.apuntes = []
			self._guardar()

	def ultimo_deshacible(self) -> Apunte | None:
		with self._candado:
			return next((a for a in reversed(self.apuntes) if a.deshacer and not a.deshecho), None)

	def deshacer_ultimo(self) -> str:
		"""Deshace la última acción que se puede deshacer y dice qué pasó. Lanza ``ErrorRegla`` si no se puede."""
		apunte = self.ultimo_deshacible()
		if apunte is None:
			raise ErrorRegla("No hay nada que deshacer")
		datos = apunte.deshacer or {}
		origen, destino = datos.get("origen", ""), datos.get("destino", "")
		try:
			if datos.get("tipo") in (MOVER, RENOMBRAR):
				if not os.path.lexists(destino):
					raise ErrorRegla(f"{os.path.basename(destino)} ya no está donde lo dejó el monitor")
				if os.path.lexists(origen):
					raise ErrorRegla(f"Ya hay otro {os.path.basename(origen)} en su sitio original")
				os.makedirs(os.path.dirname(origen), exist_ok=True)
				shutil.move(destino, origen)
				texto = f"Deshecho: {os.path.basename(origen)} vuelve a {os.path.dirname(origen)}"
			elif datos.get("tipo") == COPIAR:
				if not os.path.lexists(destino):
					raise ErrorRegla(f"La copia {os.path.basename(destino)} ya no existe")
				_a_la_papelera(destino)
				texto = f"Deshecho: la copia {os.path.basename(destino)} va a la papelera"
			else:
				raise ErrorRegla("Esa acción no se puede deshacer")
		except OSError as error:
			raise ErrorRegla(f"No se pudo deshacer: {error.strerror or error}") from error
		with self._candado:
			apunte.deshecho = True
			self._guardar()
		return texto


def _a_la_papelera(ruta: str) -> None:
	try:
		from send2trash import send2trash
	except ImportError:
		os.remove(ruta)
		return
	send2trash(ruta)
