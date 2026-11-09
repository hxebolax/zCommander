# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Piezas comunes de los lectores: el constructor de secciones, las tablas como texto y el ZIP seguro.

Reglas que siguen todos los formatos (diseño 2.0, 11.2):

- Cada encabezado abre una sección con su nivel; lo que hay antes del primero va
  en una sección con el título del documento.
- Las tablas se leen como texto lineal: «Tabla de 3 columnas. Fila 1: a; b; c.».
- Las notas al pie van al final de la sección en la que se citan.
- El texto alternativo de las imágenes se dice como «[Imagen: ...]» si la
  preferencia está activada.
- Los documentos que son ZIP (DOCX, ODT, EPUB) se leen en memoria: nunca se
  extrae nada al disco y una ruta interna que sale de la raíz («../..») se ignora.
"""

from __future__ import annotations

import builtins
import posixpath
import re
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.plugins import api

#: Tamaño máximo de un miembro de un ZIP que se lee (evita las «bombas ZIP»).
MAXIMO_MIEMBRO = 200 * 1024 * 1024
_ESPACIOS = re.compile(r"[ \t ]+")
_LINEAS_VACIAS = re.compile(r"\n{3,}")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorDocumento(api.ErrorArchivos):
	"""El documento no se puede leer (dañado, cifrado, formato no admitido); mensaje en español."""


@dataclass
class Opciones:
	"""Preferencias que cambian la lectura (``marcas_pagina`` y ``texto_alternativo`` del manifiesto)."""

	marcas_pagina: bool = True
	texto_alternativo: bool = True


@dataclass
class _SeccionEnCurso:
	titulo: str
	nivel: int
	pagina: int = 0
	partes: list[str] = field(default_factory=list)
	notas: list[str] = field(default_factory=list)


def limpiar(texto: str) -> str:
	"""Espacios repetidos fuera, y como mucho una línea en blanco seguida."""
	lineas = [_ESPACIOS.sub(" ", linea).strip() for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
	return _LINEAS_VACIAS.sub("\n\n", "\n".join(lineas)).strip()


def tabla_lineal(filas: Sequence[Sequence[str]]) -> str:
	"""«Tabla de 3 columnas. Fila 1: Nombre; Edad; Ciudad. Fila 2: ...» (una fila por línea)."""
	filas = [[limpiar(c).replace("\n", " ") for c in fila] for fila in filas if any(limpiar(c) for c in fila)]
	if not filas:
		return ""
	columnas = max(len(f) for f in filas)
	cabecera = _("Tabla de 1 columna.") if columnas == 1 else _("Tabla de {n} columnas.").format(n=columnas)
	lineas = [cabecera]
	for numero, fila in enumerate(filas, start=1):
		lineas.append(_("Fila {n}: {c}.").format(n=numero, c="; ".join(c or _("vacía") for c in fila)))
	lineas.append(_("Fin de la tabla."))
	return "\n".join(lineas)


class Constructor:
	"""Va juntando secciones mientras un lector recorre el documento."""

	def __init__(self, titulo: str) -> None:
		self.titulo = titulo
		self._secciones: list[_SeccionEnCurso] = []
		self._actual: _SeccionEnCurso | None = None
		self._pendiente: tuple[str, int] | None = None

	def _seccion(self) -> _SeccionEnCurso:
		if self._actual is None:
			titulo, nivel = self._pendiente or (self.titulo, 1)
			self._actual = _SeccionEnCurso(titulo, nivel)
			self._secciones.append(self._actual)
		return self._actual

	def capitulo(self, titulo: str, nivel: int = 1) -> None:
		"""Empieza una parte nueva (un capítulo de un EPUB): si su texto llega antes que un encabezado,
		va en una sección con este ``titulo``; si empieza con un encabezado, manda el encabezado."""
		self._actual = None
		self._pendiente = (limpiar(titulo).replace("\n", " ") or self.titulo, nivel)

	def encabezado(self, titulo: str, nivel: int = 1, pagina: int = 0) -> None:
		titulo = limpiar(titulo).replace("\n", " ")
		if not titulo:
			return
		self._actual = _SeccionEnCurso(titulo, max(1, min(6, int(nivel or 1))), pagina)
		self._secciones.append(self._actual)
		self._pendiente = None

	def parrafo(self, texto: str) -> None:
		texto = limpiar(texto)
		if texto:
			self._seccion().partes.append(texto)

	def tabla(self, filas: Sequence[Sequence[str]]) -> None:
		texto = tabla_lineal(filas)
		if texto:
			self._seccion().partes.append(texto)

	def nota(self, texto: str, numero: str = "") -> None:
		"""Nota al pie: va al final de la sección actual («Nota 3: ...»)."""
		texto = limpiar(texto)
		if texto:
			etiqueta = _("Nota {n}").format(n=numero) if numero else _("Nota")
			self._seccion().notas.append(f"{etiqueta}: {texto}")

	@property
	def hay_texto(self) -> bool:
		return any(s.partes or s.notas for s in self._secciones)

	def documento(self, metadatos: dict[str, str] | None = None, aviso: str = "") -> api.Documento:
		secciones = []
		for seccion in self._secciones:
			partes = list(seccion.partes)
			if seccion.notas:
				partes.append(_("Notas:") + "\n" + "\n".join(seccion.notas))
			secciones.append(api.Seccion(seccion.titulo, seccion.nivel, "\n\n".join(partes), seccion.pagina))
		if not secciones:
			secciones.append(api.Seccion(self.titulo, 1, ""))
		return api.Documento(self.titulo, tuple(secciones), dict(metadatos or {}), aviso)


# ── ZIP seguro ──────────────────────────────────────────────────────────────


def resolver_ruta(base: str, href: str) -> str | None:
	"""Ruta de un miembro a partir de la carpeta ``base`` y un ``href`` relativo; ``None`` si sale de la raíz."""
	href = href.split("#", 1)[0].split("?", 1)[0]
	if not href:
		return None
	from urllib.parse import unquote

	href = unquote(href).replace("\\", "/")
	if href.startswith("/") or re.match(r"^[a-zA-Z]:", href) or "://" in href:
		return None
	ruta = posixpath.normpath(posixpath.join(base, href)) if base else posixpath.normpath(href)
	if ruta.startswith("../") or ruta == ".." or ruta.startswith("/"):
		return None
	return ruta


class ZipSeguro:
	"""Lectura en memoria de un documento ZIP: miembros por nombre, con tope de tamaño."""

	def __init__(self, flujo) -> None:
		try:
			self._zip = zipfile.ZipFile(flujo)
		except (zipfile.BadZipFile, OSError) as error:
			raise ErrorDocumento(_("El documento está dañado: no es un archivo ZIP válido")) from error
		self._nombres = {info.filename: info for info in self._zip.infolist()}

	def __enter__(self) -> ZipSeguro:
		return self

	def __exit__(self, *_error) -> None:
		self._zip.close()

	def nombres(self) -> list[str]:
		return list(self._nombres)

	def existe(self, nombre: str) -> bool:
		return nombre in self._nombres

	def leer(self, nombre: str) -> bytes | None:
		"""Bytes del miembro ``nombre`` o ``None`` si no existe, sale de la raíz o es demasiado grande."""
		if nombre is None or nombre.startswith(("/", "../")) or "/../" in nombre:
			return None
		info = self._nombres.get(nombre)
		if info is None or info.file_size > MAXIMO_MIEMBRO:
			return None
		try:
			return self._zip.read(info)
		except (zipfile.BadZipFile, OSError, RuntimeError) as error:
			raise ErrorDocumento(_("El documento está dañado: no se puede leer {m}").format(m=nombre)) from error


def quitar_espacio_nombres(etiqueta: str) -> str:
	"""«{urn:...}p» → «p»."""
	return etiqueta.rsplit("}", 1)[-1]
