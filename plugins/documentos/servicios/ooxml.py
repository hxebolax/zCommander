# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""DOCX (Office Open XML) con ``zipfile`` y ``xml.etree``.

Encabezados: el nivel de esquema del estilo del párrafo (``w:outlineLvl``) o
el nombre del estilo («heading 2», «Título 2»...). Tablas como texto lineal,
notas al pie al final de su sección, texto alternativo de las imágenes
(``wp:docPr/@descr``). Metadatos de ``docProps/core.xml`` y ``app.xml``.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET

from .comun import Constructor, ErrorDocumento, Opciones, ZipSeguro, _

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_TITULO_ESTILO = re.compile(r"^(heading|título|titulo|encabezado|titre|überschrift|kop)\s*(\d)$", re.IGNORECASE)
_CORE = {
	"titulo": "{http://purl.org/dc/elements/1.1/}title",
	"autor": "{http://purl.org/dc/elements/1.1/}creator",
	"asunto": "{http://purl.org/dc/elements/1.1/}subject",
	"fecha": "{http://purl.org/dc/terms/}modified",
	"creado": "{http://purl.org/dc/terms/}created",
}


def _xml(zip_: ZipSeguro, nombre: str) -> ET.Element | None:
	datos = zip_.leer(nombre)
	if datos is None:
		return None
	try:
		return ET.fromstring(datos)
	except ET.ParseError as error:
		raise ErrorDocumento(_("El documento está dañado: {m} no es XML válido").format(m=nombre)) from error


def _niveles_estilos(zip_: ZipSeguro) -> dict[str, int]:
	"""Id de estilo → nivel de encabezado (1 a 6), por su nivel de esquema o su nombre."""
	raiz = _xml(zip_, "word/styles.xml")
	niveles: dict[str, int] = {}
	if raiz is None:
		return niveles
	for estilo in raiz.iter(f"{W}style"):
		identificador = estilo.get(f"{W}styleId", "")
		nivel = None
		esquema = estilo.find(f"{W}pPr/{W}outlineLvl")
		if esquema is not None and esquema.get(f"{W}val", "").isdigit():
			nivel = int(esquema.get(f"{W}val")) + 1
		nombre = estilo.find(f"{W}name")
		if nivel is None and nombre is not None:
			coincide = _TITULO_ESTILO.match(nombre.get(f"{W}val", "").strip())
			if coincide:
				nivel = int(coincide.group(2))
		if nivel is None:
			coincide = _TITULO_ESTILO.match(identificador)
			if coincide:
				nivel = int(coincide.group(2))
		if nivel is not None and 1 <= nivel <= 9:
			niveles[identificador] = min(nivel, 6)
	return niveles


def _texto(elemento: ET.Element, opciones: Opciones, referencias: list[str] | None = None) -> str:
	partes: list[str] = []
	for nodo in elemento.iter():
		etiqueta = nodo.tag
		if etiqueta == f"{W}t":
			partes.append(nodo.text or "")
		elif etiqueta == f"{W}tab":
			partes.append("\t")
		elif etiqueta in (f"{W}br", f"{W}cr"):
			partes.append("\n")
		elif etiqueta == f"{W}footnoteReference" and referencias is not None:
			numero = nodo.get(f"{W}id", "")
			referencias.append(numero)
			partes.append(f"[{len(referencias)}]")
		elif etiqueta == f"{WP}docPr" and opciones.texto_alternativo:
			alternativo = (nodo.get("descr") or nodo.get("title") or "").strip()
			if alternativo:
				partes.append(" " + _("[Imagen: {t}]").format(t=alternativo) + " ")
	return "".join(partes)


def _notas(zip_: ZipSeguro) -> dict[str, ET.Element]:
	raiz = _xml(zip_, "word/footnotes.xml")
	if raiz is None:
		return {}
	return {nota.get(f"{W}id", ""): nota for nota in raiz.iter(f"{W}footnote")}


def metadatos_docx(zip_: ZipSeguro) -> dict[str, str]:
	datos: dict[str, str] = {}
	core = _xml(zip_, "docProps/core.xml")
	if core is not None:
		for clave, etiqueta in _CORE.items():
			nodo = core.find(etiqueta)
			if nodo is not None and (nodo.text or "").strip():
				datos[clave] = nodo.text.strip()
	app = _xml(zip_, "docProps/app.xml")
	if app is not None:
		for nodo in app:
			if nodo.tag.endswith("}Pages") and (nodo.text or "").strip().isdigit():
				datos["paginas"] = nodo.text.strip()
	return datos


def convertir_docx(datos: bytes, nombre: str, opciones: Opciones):
	with ZipSeguro(io.BytesIO(datos)) as zip_:
		documento = _xml(zip_, "word/document.xml")
		if documento is None:
			raise ErrorDocumento(_("No es un documento de Word: falta word/document.xml"))
		metadatos = metadatos_docx(zip_)
		niveles = _niveles_estilos(zip_)
		notas = _notas(zip_)
		constructor = Constructor(metadatos.get("titulo") or nombre)
		cuerpo = documento.find(f"{W}body")
		if cuerpo is None:
			return constructor.documento(metadatos)
		referencias: list[str] = []
		for bloque in cuerpo:
			_bloque(bloque, constructor, niveles, notas, opciones, referencias)
		return constructor.documento(metadatos)


def _bloque(bloque: ET.Element, c: Constructor, niveles: dict[str, int], notas: dict[str, ET.Element], opciones: Opciones,
		referencias: list[str]) -> None:
	"""Un hijo de ``w:body``; ``referencias`` lleva la cuenta de las notas citadas en todo el documento."""
	if bloque.tag == f"{W}p":
		antes = len(referencias)
		texto = _texto(bloque, opciones, referencias)
		estilo = bloque.find(f"{W}pPr/{W}pStyle")
		nivel = niveles.get(estilo.get(f"{W}val", "")) if estilo is not None else None
		esquema = bloque.find(f"{W}pPr/{W}outlineLvl")
		if nivel is None and esquema is not None and esquema.get(f"{W}val", "").isdigit() and int(esquema.get(f"{W}val")) < 9:
			nivel = min(6, int(esquema.get(f"{W}val")) + 1)
		if nivel is not None and texto.strip():
			c.encabezado(texto, nivel)
		else:
			c.parrafo(texto)
		for posicion in range(antes, len(referencias)):
			nota = notas.get(referencias[posicion])
			if nota is not None:
				c.nota(_texto(nota, opciones), str(posicion + 1))
	elif bloque.tag == f"{W}tbl":
		filas = []
		for fila in bloque.iter(f"{W}tr"):
			filas.append([" ".join(_texto(p, opciones) for p in celda.iter(f"{W}p")) for celda in fila.findall(f"{W}tc")])
		c.tabla(filas)
	elif bloque.tag == f"{W}sdt":
		contenido = bloque.find(f"{W}sdtContent")
		if contenido is not None:
			for interior in contenido:
				_bloque(interior, c, niveles, notas, opciones, referencias)
