# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""HTML y XHTML (también los capítulos de un EPUB) a secciones, con ``html.parser``.

Encabezados ``h1`` a ``h6`` abren secciones; párrafos, listas y saltos de línea
dan párrafos; las tablas se leen como texto lineal; ``script``, ``style`` y la
cabecera se ignoran; el ``alt`` de las imágenes se dice si hay que decirlo; las
notas al pie de un EPUB (``epub:type="footnote"`` o ``role="doc-footnote"``) van
al final de su sección.
"""

from __future__ import annotations

import builtins
import codecs
import re
from html.parser import HTMLParser

from .comun import Constructor, Opciones

_BLOQUES = {"p", "div", "li", "dd", "dt", "blockquote", "pre", "section", "article", "header", "footer", "figcaption",
	"address", "nav", "main", "aside", "body", "ul", "ol", "dl", "figure", "hr", "caption"}
_IGNORAR = {"script", "style", "head", "template", "noscript", "svg", "math"}
_NOTAS = ("footnote", "endnote", "rearnote", "doc-footnote", "doc-endnote")
_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_\-]+)""", re.IGNORECASE)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def decodificar_html(datos: bytes) -> str:
	"""Texto de un HTML: BOM, ``<meta charset>``, UTF-8 o Windows-1252."""
	if datos.startswith(codecs.BOM_UTF8):
		return datos[3:].decode("utf-8", errors="replace")
	if datos.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
		return datos.decode("utf-16", errors="replace")
	encontrado = _CHARSET.search(datos[:4096])
	if encontrado:
		try:
			return datos.decode(encontrado.group(1).decode("ascii"), errors="replace")
		except LookupError:
			pass
	try:
		return datos.decode("utf-8")
	except UnicodeDecodeError:
		return datos.decode("cp1252", errors="replace")


class LectorHTML(HTMLParser):
	"""Recorre un HTML y lo va pasando al ``Constructor``."""

	def __init__(self, constructor: Constructor, opciones: Opciones) -> None:
		super().__init__(convert_charrefs=True)
		self.c = constructor
		self.opciones = opciones
		self.titulo_html = ""
		self._texto: list[str] = []
		self._ignorar = 0
		self._en_titulo = False
		self._encabezado: int | None = None
		self._tablas: list[list[list[str]]] = []
		self._celda: list[str] | None = None
		self._nota: list[str] | None = None
		self._profundidad_nota = 0
		self._en_pre = 0

	# Texto acumulado ----------------------------------------------------------

	def _destino(self) -> list[str]:
		if self._nota is not None:
			return self._nota
		if self._celda is not None:
			return self._celda
		return self._texto

	def _cerrar_parrafo(self) -> None:
		texto = "".join(self._texto)
		self._texto = []
		if self._encabezado is not None:
			return
		self.c.parrafo(texto)

	# Eventos del analizador ---------------------------------------------------

	def handle_starttag(self, etiqueta: str, atributos: list[tuple[str, str | None]]) -> None:
		attrs = {k.lower(): (v or "") for k, v in atributos}
		if etiqueta == "title":
			self._en_titulo = True
			return
		if etiqueta in _IGNORAR:
			self._ignorar += 1
			return
		if self._ignorar:
			return
		if self._nota is not None:
			self._profundidad_nota += 1
		tipo = (attrs.get("epub:type", "") + " " + attrs.get("role", "")).lower()
		if self._nota is None and any(n in tipo for n in _NOTAS):
			self._nota = []
			self._profundidad_nota = 1
			return
		if etiqueta in ("h1", "h2", "h3", "h4", "h5", "h6") and self._nota is None and self._celda is None:
			self._cerrar_parrafo()
			self._encabezado = int(etiqueta[1])
		elif etiqueta == "br":
			self._destino().append("\n")
		elif etiqueta == "table":
			self._cerrar_parrafo()
			self._tablas.append([])
		elif etiqueta == "tr" and self._tablas:
			self._tablas[-1].append([])
		elif etiqueta in ("td", "th") and self._tablas:
			if not self._tablas[-1]:
				self._tablas[-1].append([])
			self._celda = []
		elif etiqueta == "img" and self.opciones.texto_alternativo:
			alternativo = (attrs.get("alt") or attrs.get("title") or "").strip()
			if alternativo:
				self._destino().append(" " + _("[Imagen: {t}]").format(t=alternativo) + " ")
		elif etiqueta == "pre":
			self._en_pre += 1
		elif etiqueta in _BLOQUES and self._nota is None and self._celda is None:
			self._cerrar_parrafo()
		if etiqueta == "li" and self._nota is None and self._celda is None:
			self._texto.append("• ")

	def handle_endtag(self, etiqueta: str) -> None:
		if etiqueta == "title":
			self._en_titulo = False
			return
		if etiqueta in _IGNORAR:
			self._ignorar = max(0, self._ignorar - 1)
			return
		if self._ignorar:
			return
		if self._nota is not None:
			self._profundidad_nota -= 1
			if self._profundidad_nota <= 0:
				texto = "".join(self._nota)
				self._nota = None
				numero = re.match(r"\s*(\d+)[.)]?\s", texto)
				self.c.nota(texto[numero.end():] if numero else texto, numero.group(1) if numero else "")
			elif etiqueta in _BLOQUES:
				self._nota.append(" ")
			return
		if etiqueta in ("h1", "h2", "h3", "h4", "h5", "h6") and self._encabezado is not None:
			titulo = "".join(self._texto)
			self._texto = []
			nivel, self._encabezado = self._encabezado, None
			self.c.encabezado(titulo, nivel)
		elif etiqueta in ("td", "th") and self._celda is not None and self._tablas:
			self._tablas[-1][-1].append("".join(self._celda))
			self._celda = None
		elif etiqueta == "table" and self._tablas:
			filas = self._tablas.pop()
			if self._tablas and self._celda is not None:
				# Tabla anidada: su texto va dentro de la celda de fuera.
				self._celda.append(" ".join("; ".join(f) for f in filas))
			else:
				self.c.tabla(filas)
		elif etiqueta == "pre":
			self._en_pre = max(0, self._en_pre - 1)
			self._cerrar_parrafo()
		elif etiqueta in _BLOQUES and self._celda is None:
			self._cerrar_parrafo()

	def handle_startendtag(self, etiqueta: str, atributos: list[tuple[str, str | None]]) -> None:
		self.handle_starttag(etiqueta, atributos)
		if etiqueta not in ("br", "img", "hr", "meta", "link", "input"):
			self.handle_endtag(etiqueta)

	def handle_data(self, datos: str) -> None:
		if self._en_titulo:
			self.titulo_html += datos
			return
		if self._ignorar:
			return
		if not self._en_pre:
			datos = re.sub(r"\s+", " ", datos)
		self._destino().append(datos)

	def terminar(self) -> None:
		self.close()
		self._cerrar_parrafo()


def leer_html(texto: str, constructor: Constructor, opciones: Opciones) -> str:
	"""Pasa ``texto`` (HTML) al ``constructor``; devuelve el ``<title>`` del documento."""
	lector = LectorHTML(constructor, opciones)
	lector.feed(texto)
	lector.terminar()
	return " ".join(lector.titulo_html.split())


def convertir_html(datos: bytes, nombre: str, opciones: Opciones):
	from .comun import Constructor

	texto = decodificar_html(datos)
	previo = _TITULO.search(texto)
	constructor = Constructor(" ".join(previo.group(1).split()) if previo and previo.group(1).strip() else nombre)
	titulo = leer_html(texto, constructor, opciones)
	metadatos = {"titulo": titulo} if titulo else {}
	return constructor.documento(metadatos)
