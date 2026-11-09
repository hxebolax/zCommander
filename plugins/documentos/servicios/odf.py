# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""ODT (OpenDocument de texto) con ``zipfile`` y ``xml.etree``.

``text:h`` con su ``text:outline-level`` abre secciones; párrafos, listas,
tablas como texto lineal, notas (``text:note``) al final de su sección y el
título o la descripción de las imágenes. Metadatos de ``meta.xml``.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET

from .comun import Constructor, ErrorDocumento, Opciones, ZipSeguro, _

TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
SVG = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}"
META = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}"
DC = "{http://purl.org/dc/elements/1.1/}"


def _xml(zip_: ZipSeguro, nombre: str) -> ET.Element | None:
	datos = zip_.leer(nombre)
	if datos is None:
		return None
	try:
		return ET.fromstring(datos)
	except ET.ParseError as error:
		raise ErrorDocumento(_("El documento está dañado: {m} no es XML válido").format(m=nombre)) from error


def metadatos_odt(zip_: ZipSeguro) -> dict[str, str]:
	datos: dict[str, str] = {}
	raiz = _xml(zip_, "meta.xml")
	if raiz is None:
		return datos
	meta = raiz.find(f"{OFFICE}meta")
	if meta is None:
		return datos
	for clave, etiqueta in (("titulo", f"{DC}title"), ("autor", f"{DC}creator"), ("autor", f"{META}initial-creator"),
			("asunto", f"{DC}subject"), ("fecha", f"{DC}date"), ("creado", f"{META}creation-date")):
		nodo = meta.find(etiqueta)
		if nodo is not None and (nodo.text or "").strip() and clave not in datos:
			datos[clave] = nodo.text.strip()
	estadisticas = meta.find(f"{META}document-statistic")
	if estadisticas is not None and (estadisticas.get(f"{META}page-count") or "").isdigit():
		datos["paginas"] = estadisticas.get(f"{META}page-count")
	return datos


class _Recorrido:
	def __init__(self, constructor: Constructor, opciones: Opciones) -> None:
		self.c = constructor
		self.opciones = opciones
		self.notas = 0

	def texto(self, elemento: ET.Element, notas: list[tuple[str, str]] | None = None) -> str:
		"""Texto de un párrafo con sus espacios (``text:s``), tabuladores y saltos; las notas se apartan."""
		partes = [elemento.text or ""]
		for hijo in elemento:
			etiqueta = hijo.tag
			if etiqueta == f"{TEXT}s":
				partes.append(" " * int(hijo.get(f"{TEXT}c", "1") or 1))
			elif etiqueta == f"{TEXT}tab":
				partes.append("\t")
			elif etiqueta == f"{TEXT}line-break":
				partes.append("\n")
			elif etiqueta == f"{TEXT}note":
				self.notas += 1
				cuerpo = hijo.find(f"{TEXT}note-body")
				if notas is not None and cuerpo is not None:
					notas.append((str(self.notas), " ".join(self.texto(p) for p in cuerpo.iter(f"{TEXT}p"))))
				partes.append(f"[{self.notas}]")
			elif etiqueta == f"{DRAW}frame":
				if self.opciones.texto_alternativo:
					alternativo = " ".join(filter(None, ((hijo.findtext(f"{SVG}title") or "").strip(),
						(hijo.findtext(f"{SVG}desc") or "").strip())))
					if alternativo:
						partes.append(" " + _("[Imagen: {t}]").format(t=alternativo) + " ")
			else:
				partes.append(self.texto(hijo, notas))
			partes.append(hijo.tail or "")
		return "".join(partes)

	def bloque(self, elemento: ET.Element) -> None:
		etiqueta = elemento.tag
		if etiqueta in (f"{TEXT}h", f"{TEXT}p"):
			notas: list[tuple[str, str]] = []
			texto = self.texto(elemento, notas)
			if etiqueta == f"{TEXT}h" and texto.strip():
				nivel = elemento.get(f"{TEXT}outline-level", "1")
				self.c.encabezado(texto, int(nivel) if nivel.isdigit() else 1)
			else:
				self.c.parrafo(texto)
			for numero, nota in notas:
				self.c.nota(nota, numero)
		elif etiqueta == f"{TEXT}list":
			for elemento_lista in elemento.iter(f"{TEXT}list-item"):
				for parrafo in elemento_lista.findall(f"{TEXT}p"):
					self.c.parrafo("• " + self.texto(parrafo))
		elif etiqueta == f"{TABLE}table":
			filas = []
			for fila in elemento.iter(f"{TABLE}table-row"):
				filas.append([" ".join(self.texto(p) for p in celda.iter(f"{TEXT}p")) for celda in fila.findall(f"{TABLE}table-cell")])
			self.c.tabla(filas)
		elif etiqueta in (f"{TEXT}section", f"{TEXT}table-of-content", f"{TEXT}index-body"):
			for hijo in elemento:
				self.bloque(hijo)


def convertir_odt(datos: bytes, nombre: str, opciones: Opciones):
	with ZipSeguro(io.BytesIO(datos)) as zip_:
		contenido = _xml(zip_, "content.xml")
		if contenido is None:
			raise ErrorDocumento(_("No es un documento OpenDocument: falta content.xml"))
		metadatos = metadatos_odt(zip_)
	constructor = Constructor(metadatos.get("titulo") or nombre)
	texto = contenido.find(f"{OFFICE}body/{OFFICE}text")
	if texto is not None:
		recorrido = _Recorrido(constructor, opciones)
		for bloque in texto:
			recorrido.bloque(bloque)
	return constructor.documento(metadatos)
