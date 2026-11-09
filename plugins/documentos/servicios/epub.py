# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""EPUB 2 y 3: el orden de lectura (``spine``) del paquete OPF, cada capítulo con el lector HTML.

Todo se lee en memoria desde el ZIP; una ruta del manifiesto que sale de la
raíz del libro («../../algo») se ignora (``resolver_ruta``), así un libro
malicioso no puede hacer leer ni escribir nada fuera de él.
"""

from __future__ import annotations

import io
import posixpath
import re
import xml.etree.ElementTree as ET

from .comun import Constructor, ErrorDocumento, Opciones, ZipSeguro, _, resolver_ruta
from .html import decodificar_html, leer_html

OPF = "{http://www.idpf.org/2007/opf}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENEDOR = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_XHTML = ("application/xhtml+xml", "text/html", "application/x-dtbook+xml")


def _xml(datos: bytes | None, nombre: str) -> ET.Element:
	if datos is None:
		raise ErrorDocumento(_("El libro está dañado: falta {m}").format(m=nombre))
	try:
		return ET.fromstring(datos)
	except ET.ParseError as error:
		raise ErrorDocumento(_("El libro está dañado: {m} no es XML válido").format(m=nombre)) from error


def _paquete(zip_: ZipSeguro) -> tuple[str, ET.Element]:
	contenedor = _xml(zip_.leer("META-INF/container.xml"), "META-INF/container.xml")
	raiz = contenedor.find(f".//{CONTENEDOR}rootfile")
	ruta = resolver_ruta("", raiz.get("full-path", "")) if raiz is not None else None
	if ruta is None:
		raise ErrorDocumento(_("El libro está dañado: no dice dónde está su paquete OPF"))
	return ruta, _xml(zip_.leer(ruta), ruta)


def metadatos_epub(opf: ET.Element) -> dict[str, str]:
	datos: dict[str, str] = {}
	meta = opf.find(f"{OPF}metadata")
	if meta is None:
		return datos
	for clave, etiqueta in (("titulo", f"{DC}title"), ("autor", f"{DC}creator"), ("fecha", f"{DC}date"),
			("idioma", f"{DC}language"), ("editorial", f"{DC}publisher")):
		nodo = meta.find(etiqueta)
		if nodo is not None and (nodo.text or "").strip():
			datos[clave] = nodo.text.strip()
	return datos


def capitulos(zip_: ZipSeguro, ruta_opf: str, opf: ET.Element) -> list[str]:
	"""Rutas de los capítulos en orden de lectura (solo las que quedan dentro del libro)."""
	base = posixpath.dirname(ruta_opf)
	manifiesto = {}
	for item in opf.iter(f"{OPF}item"):
		manifiesto[item.get("id", "")] = (item.get("href", ""), item.get("media-type", ""))
	rutas = []
	for itemref in opf.iter(f"{OPF}itemref"):
		href, tipo = manifiesto.get(itemref.get("idref", ""), ("", ""))
		if tipo and tipo not in _XHTML:
			continue
		ruta = resolver_ruta(base, href)
		if ruta is not None and zip_.existe(ruta) and ruta not in rutas:
			rutas.append(ruta)
	return rutas


def convertir_epub(datos: bytes, nombre: str, opciones: Opciones, cancelacion=None):
	from app.plugins import api

	with ZipSeguro(io.BytesIO(datos)) as zip_:
		ruta_opf, opf = _paquete(zip_)
		metadatos = metadatos_epub(opf)
		constructor = Constructor(metadatos.get("titulo") or nombre)
		lista = capitulos(zip_, ruta_opf, opf)
		metadatos["capitulos"] = str(len(lista))
		for numero, ruta in enumerate(lista, start=1):
			api.comprobar(cancelacion)
			contenido = zip_.leer(ruta)
			if contenido is None:
				continue
			texto = decodificar_html(contenido)
			titulo = _TITULO.search(texto)
			constructor.capitulo(" ".join(titulo.group(1).split()) if titulo and titulo.group(1).strip()
				else _("Capítulo {n}").format(n=numero))
			leer_html(texto, constructor, opciones)
	return constructor.documento(metadatos)
