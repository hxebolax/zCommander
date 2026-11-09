# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Punto de entrada de los lectores: elige el formato por la extensión, lee los bytes y convierte.

Todo se llama en un hilo de trabajo y acepta cancelación. Los errores se
lanzan como ``ErrorDocumento`` (un ``api.ErrorArchivos``) con el mensaje en español.
"""

from __future__ import annotations

import builtins
import os
from collections.abc import Callable
from typing import Any

from app.plugins import api

from . import epub, fb2, html, odf, ooxml, pdf, rtf
from .comun import ErrorDocumento, Opciones, ZipSeguro, limpiar

#: Extensión → nombre del formato (el orden es el de las preferencias).
FORMATOS: dict[str, str] = {
	"pdf": "PDF", "docx": "Word", "doc": "Word 97-2003", "odt": "OpenDocument", "epub": "EPUB", "rtf": "RTF",
	"html": "HTML", "htm": "HTML", "xhtml": "XHTML", "fb2": "FictionBook",
}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def extension(nombre: str) -> str:
	return os.path.splitext(nombre)[1].lower().lstrip(".")


def admitido(nombre: str, formatos: list[str] | None = None) -> bool:
	ext = extension(nombre)
	if ext not in FORMATOS:
		return False
	if formatos is None:
		return True
	activos = {f.lower().lstrip(".*") for f in formatos}
	return ext in activos or (ext == "htm" and "html" in activos) or (ext == "xhtml" and "html" in activos)


def leer_bytes(proveedor: api.Proveedor, ruta: str, maximo: int, cancelacion: Any = None) -> bytes:
	"""Contenido del archivo; ``ErrorDocumento`` si pasa de ``maximo`` bytes."""
	try:
		tamano = proveedor.info(ruta).tamano
	except api.ErrorArchivos:
		tamano = -1
	if maximo > 0 and tamano > maximo:
		raise ErrorDocumento(_("El documento ocupa más de {m} MB, el máximo de las preferencias del complemento").format(
			m=maximo // (1024 * 1024)), ruta)
	partes = []
	leidos = 0
	with proveedor.abrir_lectura(ruta) as flujo:
		while bloque := flujo.read(1024 * 1024):
			api.comprobar(cancelacion)
			partes.append(bloque)
			leidos += len(bloque)
			if maximo > 0 and leidos > maximo:
				raise ErrorDocumento(_("El documento ocupa más de {m} MB, el máximo de las preferencias del complemento").format(
					m=maximo // (1024 * 1024)), ruta)
	return b"".join(partes)


def convertir(proveedor: api.Proveedor, ruta: str, cancelacion: Any = None, opciones: Opciones | None = None,
		maximo: int = 100 * 1024 * 1024, carpeta_temporal: str | None = None,
		ocr: Callable[[api.Proveedor, str, Any], api.Documento] | None = None) -> api.Documento:
	"""``Documento`` con secciones del archivo ``ruta``.

	:param ocr: si se da y el PDF no tiene texto, se reconoce con esta función (la de ``zc.ocr``).
	"""
	opciones = opciones or Opciones()
	nombre = proveedor.nombre(ruta)
	titulo = os.path.splitext(nombre)[0]
	ext = extension(nombre)
	if ext not in FORMATOS:
		raise ErrorDocumento(_("El lector de documentos no conoce el formato .{e}").format(e=ext), ruta)
	api.comprobar(cancelacion)
	if ext == "doc":
		from . import word

		local = proveedor.ruta_local(ruta) or proveedor.extraer_temporal(ruta)
		return word.convertir_doc(local, titulo, opciones, carpeta_temporal)
	datos = leer_bytes(proveedor, ruta, maximo, cancelacion)
	api.comprobar(cancelacion)
	if ext == "pdf":
		documento = pdf.convertir_pdf(datos, titulo, opciones, cancelacion)
		if documento.aviso and ocr is not None:
			reconocido = ocr(proveedor, ruta, cancelacion)
			if reconocido is not None:
				aviso = _("PDF sin texto: el texto se ha reconocido con OCR y puede tener errores.")
				return api.Documento(documento.titulo, reconocido.secciones, {**documento.metadatos, **reconocido.metadatos}, aviso)
		return documento
	if ext == "docx":
		return ooxml.convertir_docx(datos, titulo, opciones)
	if ext == "odt":
		return odf.convertir_odt(datos, titulo, opciones)
	if ext == "epub":
		return epub.convertir_epub(datos, titulo, opciones, cancelacion)
	if ext == "rtf":
		return rtf.convertir_rtf(datos, titulo, opciones)
	if ext == "fb2":
		return fb2.convertir_fb2(datos, titulo, opciones)
	return html.convertir_html(datos, titulo, opciones)


def metadatos(proveedor: api.Proveedor, ruta: str, cancelacion: Any = None, maximo: int = 100 * 1024 * 1024) -> dict[str, str]:
	"""Título, autor, páginas y fecha sin convertir todo el documento (para columnas e información)."""
	import io

	nombre = proveedor.nombre(ruta)
	ext = extension(nombre)
	if ext not in FORMATOS or ext == "doc":
		return {}
	datos = leer_bytes(proveedor, ruta, maximo, cancelacion)
	if ext == "pdf":
		return pdf.metadatos_pdf(datos)
	if ext in ("docx", "odt", "epub"):
		with ZipSeguro(io.BytesIO(datos)) as zip_:
			if ext == "docx":
				return ooxml.metadatos_docx(zip_)
			if ext == "odt":
				return odf.metadatos_odt(zip_)
			ruta_opf, opf = epub._paquete(zip_)  # noqa: SLF001 - mismo paquete
			resultado = epub.metadatos_epub(opf)
			resultado["capitulos"] = str(len(epub.capitulos(zip_, ruta_opf, opf)))
			return resultado
	# RTF, FB2 y HTML: convertir es barato y da el título.
	return dict(convertir(proveedor, ruta, cancelacion, Opciones(), maximo).metadatos)


def texto_plano(documento: api.Documento) -> str:
	"""Todo el texto de un documento, sin marcas (para buscar dentro)."""
	partes = []
	for seccion in documento.secciones:
		partes.append(seccion.titulo)
		if seccion.texto:
			partes.append(seccion.texto)
	return limpiar("\n".join(partes))
