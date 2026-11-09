# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor del buscador de duplicados (diseño 2.0, 11.7). Sin wx.

Por qué va aparte de la interfaz: el agrupado, el marcado automático, los
enlaces duros y el informe se prueban sin ventanas, y la operación del motor
(``OperacionBuscarDuplicados``) es la misma que lanza la orden.

Criterios:

- ``contenido``: primero por tamaño (gratis, sale del listado), después por un
  hash BLAKE2b de los primeros 64 KB y, solo entre los que coinciden, por el
  hash BLAKE2b completo. Así casi nunca se lee un archivo entero.
- ``nombre``: mismo nombre (sin distinguir mayúsculas).
- ``nombre_tamano``: mismo nombre y mismo tamaño.
- ``etiquetas``: mismas etiquetas de audio (artista, título y duración
  redondeada), con ``zc.metadatos`` si está.
"""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import io
import logging
import os
import stat
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.plugins import api

_ = api.traduccion("zc.duplicados")[0]
log = logging.getLogger("zcplugins.zc.duplicados")

CRITERIOS = ("contenido", "nombre", "nombre_tamano", "etiquetas")
PARCIAL = 64 * 1024
BLOQUE = 1024 * 1024


def textos_criterios() -> list[str]:
	return [_("Por contenido (tamaño y suma BLAKE2b)"), _("Por nombre"), _("Por nombre y tamaño"),
		_("Por etiquetas de audio")]


MARCADOS = ("antiguo", "reciente", "carpeta", "corta")


def textos_marcados() -> list[str]:
	return [_("Conservar el más &antiguo"), _("Conservar el más &reciente"), _("Conservar el de la carpeta &preferida"),
		_("Conservar el de ruta más c&orta")]


# ── Datos ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Archivo:
	"""Un archivo candidato (ruta local absoluta)."""

	ruta: str
	nombre: str
	tamano: int
	modificado: float

	@property
	def carpeta(self) -> str:
		return os.path.dirname(self.ruta)


@dataclass
class Grupo:
	"""Archivos iguales según el criterio. ``archivos`` en orden de ruta."""

	archivos: list[Archivo]
	clave: str = ""

	@property
	def copias(self) -> int:
		return len(self.archivos)

	@property
	def recuperable(self) -> int:
		"""Bytes que se liberan si se deja una sola copia."""
		if not self.archivos:
			return 0
		return sum(a.tamano for a in self.archivos) - max(a.tamano for a in self.archivos)


@dataclass
class Opciones:
	carpetas: list[str]
	criterio: str = "contenido"
	tamano_minimo: int = 1024
	excluir: str = ""
	incluir_ocultos: bool = False


@dataclass
class Resultado:
	grupos: list[Grupo] = field(default_factory=list)
	revisados: int = 0
	errores: list[tuple[str, str]] = field(default_factory=list)
	completo: bool = True
	aviso: str = ""


def describir_grupo(indice: int, total: int, grupo: Grupo) -> str:
	"""«Grupo 3 de 40, 2 copias, 12 MB recuperables»."""
	return _("Grupo {i} de {t}, {c}, {r} recuperables").format(
		i=indice + 1, t=total, c=api.formato.plural(grupo.copias, _("{n} copia"), _("{n} copias")),
		r=api.formato.tamano_legible(grupo.recuperable))


def resumen(resultado: Resultado) -> str:
	if not resultado.grupos:
		texto = _("No hay duplicados entre {n}").format(n=api.formato.plural(resultado.revisados, _("{n} archivo"), _("{n} archivos")))
	else:
		recuperable = sum(g.recuperable for g in resultado.grupos)
		texto = _("{g} de duplicados, {r} recuperables, entre {n}").format(
			g=api.formato.plural(len(resultado.grupos), _("{n} grupo"), _("{n} grupos")),
			r=api.formato.tamano_legible(recuperable),
			n=api.formato.plural(resultado.revisados, _("{n} archivo"), _("{n} archivos")))
	if not resultado.completo:
		texto += ". " + _("Búsqueda incompleta: se canceló")
	if resultado.errores:
		texto += ". " + api.formato.plural(len(resultado.errores), _("{n} elemento sin leer"), _("{n} elementos sin leer"))
	return texto


# ── Recorrido ────────────────────────────────────────────────────────────────


def _patrones(texto: str) -> list[str]:
	return [p.strip().casefold() for p in texto.replace(",", ";").split(";") if p.strip()]


def _excluido(nombre: str, patrones: Sequence[str]) -> bool:
	plegado = nombre.casefold()
	return any(fnmatch.fnmatch(plegado, p) for p in patrones)


def _oculto(entrada: os.DirEntry) -> bool:
	try:
		atributos = entrada.stat(follow_symlinks=False).st_file_attributes
	except (OSError, AttributeError):
		return False
	return bool(atributos & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))


def recorrer(opciones: Opciones, cancelacion=None, al_avanzar: Callable[[str], None] | None = None,
		errores: list[tuple[str, str]] | None = None) -> list[Archivo]:
	"""Archivos candidatos de las carpetas, sin seguir enlaces ni uniones y sin repetir rutas."""
	patrones = _patrones(opciones.excluir)
	vistos: set[str] = set()
	archivos: list[Archivo] = []
	pendientes = [os.path.abspath(c) for c in opciones.carpetas if c]
	while pendientes:
		api.comprobar(cancelacion)
		carpeta = pendientes.pop()
		clave = os.path.normcase(carpeta)
		if clave in vistos:
			continue
		vistos.add(clave)
		if al_avanzar is not None:
			al_avanzar(carpeta)
		try:
			with os.scandir(carpeta) as elementos:
				for elemento in elementos:
					api.comprobar(cancelacion)
					try:
						if elemento.is_symlink() or elemento.is_junction():
							continue
						if not opciones.incluir_ocultos and _oculto(elemento):
							continue
						if _excluido(elemento.name, patrones):
							continue
						if elemento.is_dir(follow_symlinks=False):
							pendientes.append(elemento.path)
							continue
						datos = elemento.stat(follow_symlinks=False)
					except OSError as error:
						if errores is not None:
							errores.append((elemento.path, str(error)))
						continue
					if datos.st_size < max(1, opciones.tamano_minimo):
						continue
					archivos.append(Archivo(elemento.path, elemento.name, datos.st_size, datos.st_mtime))
		except OSError as error:
			if errores is not None:
				errores.append((carpeta, str(error)))
	# La misma ruta puede llegar por dos carpetas de origen anidadas.
	unicos: dict[str, Archivo] = {}
	for archivo in archivos:
		unicos.setdefault(os.path.normcase(archivo.ruta), archivo)
	return sorted(unicos.values(), key=lambda a: a.ruta.casefold())


# ── Sumas ────────────────────────────────────────────────────────────────────


def suma(ruta: str, limite: int = -1, cancelacion=None, al_leer: Callable[[int], None] | None = None) -> str:
	"""BLAKE2b de los ``limite`` primeros bytes (o de todo el archivo con ``-1``)."""
	resumen_ = hashlib.blake2b(digest_size=32)
	leidos = 0
	with open(ruta, "rb") as archivo:
		while limite < 0 or leidos < limite:
			api.comprobar(cancelacion)
			cuanto = BLOQUE if limite < 0 else min(BLOQUE, limite - leidos)
			bloque = archivo.read(cuanto)
			if not bloque:
				break
			resumen_.update(bloque)
			leidos += len(bloque)
			if al_leer is not None:
				al_leer(len(bloque))
	return resumen_.hexdigest()


def _agrupar_por(archivos: Sequence[Archivo], clave: Callable[[Archivo], object]) -> list[list[Archivo]]:
	grupos: dict[object, list[Archivo]] = {}
	for archivo in archivos:
		grupos.setdefault(clave(archivo), []).append(archivo)
	return [g for g in grupos.values() if len(g) > 1]


def agrupar(archivos: Sequence[Archivo], criterio: str, cancelacion=None,
		etiquetas: Callable[[Archivo], dict[str, str] | None] | None = None,
		al_leer: Callable[[int], None] | None = None,
		errores: list[tuple[str, str]] | None = None) -> list[Grupo]:
	"""Grupos de archivos iguales según ``criterio``, de más bytes recuperables a menos."""
	if criterio == "nombre":
		crudos = _agrupar_por(archivos, lambda a: a.nombre.casefold())
	elif criterio == "nombre_tamano":
		crudos = _agrupar_por(archivos, lambda a: (a.nombre.casefold(), a.tamano))
	elif criterio == "etiquetas":
		if etiquetas is None:
			raise api.NoAdmitido(_("Para buscar por etiquetas de audio hace falta el complemento Metadatos y etiquetas de audio"))
		claves: dict[str, tuple] = {}
		for archivo in archivos:
			api.comprobar(cancelacion)
			datos = etiquetas(archivo) or {}
			artista, titulo = datos.get("artista", "").strip().casefold(), datos.get("titulo", "").strip().casefold()
			if not (artista or titulo):
				continue
			try:
				duracion = round(float(datos.get("duracion_s", 0) or 0))
			except ValueError:
				duracion = 0
			claves[archivo.ruta] = (artista, titulo, duracion)
		crudos = _agrupar_por([a for a in archivos if a.ruta in claves], lambda a: claves[a.ruta])
	else:
		crudos = _por_contenido(archivos, cancelacion, al_leer, errores)
	grupos = [Grupo(sorted(g, key=lambda a: a.ruta.casefold())) for g in crudos]
	grupos.sort(key=lambda g: (-g.recuperable, g.archivos[0].ruta.casefold()))
	return grupos


def _sumas(archivos: Sequence[Archivo], limite: int, cancelacion, al_leer, errores) -> dict[str, list[Archivo]]:
	por_suma: dict[str, list[Archivo]] = {}
	for archivo in archivos:
		api.comprobar(cancelacion)
		try:
			valor = suma(archivo.ruta, limite, cancelacion, al_leer)
		except api.Cancelado:
			raise
		except OSError as error:
			if errores is not None:
				errores.append((archivo.ruta, str(error)))
			continue
		por_suma.setdefault(valor, []).append(archivo)
	return por_suma


def _por_contenido(archivos, cancelacion, al_leer, errores) -> list[list[Archivo]]:
	resultado: list[list[Archivo]] = []
	for mismo_tamano in _agrupar_por(archivos, lambda a: a.tamano):
		api.comprobar(cancelacion)
		parciales = _sumas(mismo_tamano, PARCIAL, cancelacion, al_leer, errores)
		for candidatos in parciales.values():
			if len(candidatos) < 2:
				continue
			if candidatos[0].tamano <= PARCIAL:
				# Los 64 KB ya eran el archivo entero.
				resultado.append(candidatos)
				continue
			for iguales in _sumas(candidatos, -1, cancelacion, al_leer, errores).values():
				if len(iguales) > 1:
					resultado.append(iguales)
	return resultado


# ── Marcado automático ───────────────────────────────────────────────────────


def _dentro(ruta: str, carpeta: str) -> bool:
	if not carpeta:
		return False
	carpeta = os.path.normcase(os.path.abspath(carpeta)).rstrip("\\/") + os.sep
	return os.path.normcase(os.path.abspath(ruta)).startswith(carpeta)


def conservado(grupo: Grupo, modo: str, carpeta_preferida: str = "") -> Archivo:
	"""El archivo que se conserva en ``grupo`` según ``modo`` (los demás se marcan)."""
	archivos = grupo.archivos
	if modo == "reciente":
		return max(archivos, key=lambda a: (a.modificado, -len(a.ruta)))
	if modo == "carpeta":
		preferidos = [a for a in archivos if _dentro(a.ruta, carpeta_preferida)]
		if preferidos:
			return min(preferidos, key=lambda a: (len(a.ruta), a.ruta.casefold()))
		return min(archivos, key=lambda a: (a.modificado, len(a.ruta)))
	if modo == "corta":
		return min(archivos, key=lambda a: (len(a.ruta), a.ruta.casefold()))
	return min(archivos, key=lambda a: (a.modificado, len(a.ruta)))


def marcar_automatico(grupos: Sequence[Grupo], modo: str, carpeta_preferida: str = "") -> set[str]:
	"""Rutas marcadas: en cada grupo, todas menos la que se conserva."""
	marcadas: set[str] = set()
	for grupo in grupos:
		guardado = conservado(grupo, modo, carpeta_preferida)
		marcadas.update(a.ruta for a in grupo.archivos if a is not guardado)
	return marcadas


def resumen_marcado(grupos: Sequence[Grupo], marcadas: set[str]) -> str:
	"""«Marcados 2 archivos en 1 grupo, 24 MB» (lo que se dice tras marcar)."""
	archivos = [a for g in grupos for a in g.archivos if a.ruta in marcadas]
	con_marcas = sum(1 for g in grupos if any(a.ruta in marcadas for a in g.archivos))
	return _("Marcados {a} en {g}, {b}").format(
		a=api.formato.plural(len(archivos), _("{n} archivo"), _("{n} archivos")),
		g=api.formato.plural(con_marcas, _("{n} grupo"), _("{n} grupos")),
		b=api.formato.tamano_legible(sum(a.tamano for a in archivos)))


def grupos_sin_copia(grupos: Sequence[Grupo], marcadas: set[str]) -> list[int]:
	"""Índices de los grupos con TODAS las copias marcadas: nunca se tocan (se perdería el contenido)."""
	return [i for i, g in enumerate(grupos) if g.archivos and all(a.ruta in marcadas for a in g.archivos)]


# ── Enlaces duros ────────────────────────────────────────────────────────────


def mismo_volumen(a: str, b: str) -> bool:
	try:
		return os.stat(a).st_dev == os.stat(b).st_dev
	except OSError:
		return False


def sustituir_por_enlace(original: str, copia: str, comprobar_contenido: bool = True, cancelacion=None) -> None:
	"""Cambia ``copia`` por un enlace duro a ``original`` (misma unidad NTFS).

	Se crea el enlace con un nombre temporal y después sustituye a la copia,
	así nunca hay un momento sin el archivo.
	"""
	if os.path.normcase(os.path.abspath(original)) == os.path.normcase(os.path.abspath(copia)):
		return
	if not mismo_volumen(original, copia):
		raise api.NoAdmitido(_("«{c}» está en otra unidad: un enlace duro solo puede ir en la misma").format(
			c=os.path.basename(copia)), copia)
	datos_original, datos_copia = os.stat(original), os.stat(copia)
	if datos_original.st_ino == datos_copia.st_ino:
		return  # ya son el mismo archivo
	if datos_original.st_size != datos_copia.st_size or (
			comprobar_contenido and suma(original, -1, cancelacion) != suma(copia, -1, cancelacion)):
		raise api.ErrorArchivos(_("«{c}» ya no es igual que el que se conserva; no se toca").format(c=os.path.basename(copia)), copia)
	temporal = os.path.join(os.path.dirname(copia), f"~zcenlace{os.getpid()}{int(time.time() * 1000) % 100000}.tmp")
	try:
		os.link(original, temporal)
	except OSError as error:
		raise api.ErrorArchivos(_("No se pudo crear el enlace duro para «{c}»: {e}").format(c=os.path.basename(copia), e=error.strerror or error),
			copia) from error
	try:
		os.replace(temporal, copia)
	except OSError as error:
		try:
			os.remove(temporal)
		except OSError:
			log.debug("No se pudo quitar el temporal %s", temporal, exc_info=True)
		raise api.ErrorArchivos(_("No se pudo sustituir «{c}»: {e}").format(c=os.path.basename(copia), e=error.strerror or error),
			copia) from error


# ── Informe ──────────────────────────────────────────────────────────────────


def informe_texto(resultado: Resultado, marcadas: set[str] | None = None) -> str:
	marcadas = marcadas or set()
	lineas = [_("Informe de duplicados de zCommander"), resumen(resultado), ""]
	total = len(resultado.grupos)
	for i, grupo in enumerate(resultado.grupos):
		lineas.append(describir_grupo(i, total, grupo))
		for archivo in grupo.archivos:
			marca = _(" (marcado)") if archivo.ruta in marcadas else ""
			lineas.append(f"  {archivo.ruta}{marca}")
		lineas.append("")
	return "\n".join(lineas)


def informe_csv(resultado: Resultado, marcadas: set[str] | None = None) -> str:
	marcadas = marcadas or set()
	salida = io.StringIO()
	escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
	escritor.writerow([_("Grupo"), _("Nombre"), _("Carpeta"), _("Tamaño"), _("Fecha"), _("Marcado")])
	for i, grupo in enumerate(resultado.grupos):
		for archivo in grupo.archivos:
			escritor.writerow([i + 1, archivo.nombre, archivo.carpeta, archivo.tamano,
				api.formato.fecha(archivo.modificado, "larga"), _("Sí") if archivo.ruta in marcadas else _("No")])
	return salida.getvalue()


# ── Operaciones del motor ────────────────────────────────────────────────────


class OperacionBuscarDuplicados(api.Operacion):
	"""Busca duplicados con progreso, pausa y cancelación; el resultado queda en ``resultado``."""

	tipo = "duplicados"

	def __init__(self, opciones: Opciones, etiquetas: Callable[[Archivo], dict[str, str] | None] | None = None) -> None:
		super().__init__()
		self.opciones = opciones
		self.etiquetas = etiquetas
		self.resultado = Resultado()

	def descripcion(self) -> str:
		carpetas = self.opciones.carpetas
		donde = carpetas[0] if len(carpetas) == 1 else api.formato.plural(len(carpetas), _("{n} carpeta"), _("{n} carpetas"))
		return _("Buscar duplicados en {d}").format(d=donde)

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.ANALIZANDO)
		errores = self.resultado.errores

		def avanzar(carpeta: str) -> None:
			ctx.comprobar()
			self.progresar(actual=carpeta)

		try:
			archivos = recorrer(self.opciones, ctx.token, avanzar, errores)
			self.resultado.revisados = len(archivos)
			self.cambiar_estado(api.Estado.EJECUTANDO)
			self.progresar(archivos_total=len(archivos), bytes_total=sum(a.tamano for a in archivos))

			def leidos(n: int) -> None:
				ctx.comprobar()
				self.sumar(bytes_hechos=n)

			self.resultado.grupos = agrupar(archivos, self.opciones.criterio, ctx.token, self.etiquetas, leidos, errores)
			self.progresar(archivos_hechos=len(archivos))
		except api.Cancelado:
			self.resultado.completo = False
			self.cambiar_estado(api.Estado.CANCELADA)
			return
		for ruta, mensaje in errores:
			self.anotar_error(ruta, mensaje)
		self.cambiar_estado(api.Estado.TERMINADA_CON_ERRORES if errores else api.Estado.TERMINADA)

	def resumen(self) -> str:
		return resumen(self.resultado)


class OperacionEnlacesDuros(api.Operacion):
	"""Sustituye cada copia marcada por un enlace duro al archivo que se conserva en su grupo."""

	tipo = "enlaces_duros"

	def __init__(self, pares: Sequence[tuple[str, str]]) -> None:
		super().__init__()
		self.pares = list(pares)
		self.hechos: list[str] = []

	def descripcion(self) -> str:
		return _("Sustituir {n} por enlaces duros").format(n=api.formato.plural(len(self.pares), _("{n} copia"), _("{n} copias")))

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset("local:" + os.path.splitdrive(os.path.abspath(c))[0].casefold() + "\\" for _o, c in self.pares)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return sorted({("local", os.path.dirname(c)) for _o, c in self.pares})

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.pares))
		try:
			for original, copia in self.pares:
				ctx.comprobar()
				self.progresar(actual=copia)
				try:
					sustituir_por_enlace(original, copia, cancelacion=ctx.token)
					self.hechos.append(copia)
				except api.Cancelado:
					raise
				except (api.ErrorArchivos, OSError) as error:
					self.anotar_error(copia, getattr(error, "mensaje", str(error)))
				self.sumar(archivos_hechos=1)
		except api.Cancelado:
			self.cambiar_estado(api.Estado.CANCELADA)
			return
		self.cambiar_estado(api.Estado.TERMINADA_CON_ERRORES if self.errores else api.Estado.TERMINADA)
