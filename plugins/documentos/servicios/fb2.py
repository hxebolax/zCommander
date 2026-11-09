# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""FictionBook 2 (FB2, también dentro de un ``.fb2.zip`` no: solo el XML) con ``xml.etree``.

Cada ``section`` con su ``title`` abre una sección (el nivel es su profundidad);
``p``, ``poem``, ``cite`` y ``table`` dan el texto; el cuerpo de notas
(``body name="notes"``) va como sección «Notas» al final.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .comun import Constructor, ErrorDocumento, Opciones, _, quitar_espacio_nombres


def _hijos(elemento: ET.Element, nombre: str) -> list[ET.Element]:
	return [h for h in elemento if quitar_espacio_nombres(h.tag) == nombre]


def _texto(elemento: ET.Element) -> str:
	return "".join(elemento.itertext())


def metadatos_fb2(raiz: ET.Element) -> dict[str, str]:
	datos: dict[str, str] = {}
	for descripcion in _hijos(raiz, "description"):
		for info in _hijos(descripcion, "title-info"):
			for titulo in _hijos(info, "book-title"):
				datos["titulo"] = _texto(titulo).strip()
			autores = []
			for autor in _hijos(info, "author"):
				partes = [_texto(p).strip() for nombre in ("first-name", "middle-name", "last-name") for p in _hijos(autor, nombre)]
				autores.append(" ".join(p for p in partes if p))
			if autores:
				datos["autor"] = ", ".join(a for a in autores if a)
			for fecha in _hijos(info, "date"):
				datos["fecha"] = (fecha.get("value") or _texto(fecha)).strip()
	return {k: v for k, v in datos.items() if v}


def _seccion(seccion: ET.Element, c: Constructor, nivel: int, opciones: Opciones) -> None:
	for hijo in seccion:
		nombre = quitar_espacio_nombres(hijo.tag)
		if nombre == "title":
			c.encabezado(" ".join(_texto(p) for p in hijo), nivel)
		elif nombre == "section":
			_seccion(hijo, c, min(6, nivel + 1), opciones)
		elif nombre in ("p", "subtitle", "text-author"):
			c.parrafo(_texto(hijo))
		elif nombre in ("poem", "cite", "epigraph"):
			c.parrafo("\n".join(_texto(p) for p in hijo.iter() if quitar_espacio_nombres(p.tag) in ("p", "v", "text-author")))
		elif nombre == "table":
			c.tabla([[_texto(celda) for celda in fila] for fila in _hijos(hijo, "tr")])
		elif nombre == "image" and opciones.texto_alternativo:
			alternativo = (hijo.get("alt") or hijo.get("title") or "").strip()
			if alternativo:
				c.parrafo(_("[Imagen: {t}]").format(t=alternativo))


def convertir_fb2(datos: bytes, nombre: str, opciones: Opciones):
	try:
		raiz = ET.fromstring(datos)
	except ET.ParseError as error:
		raise ErrorDocumento(_("El libro FB2 está dañado: no es XML válido")) from error
	metadatos = metadatos_fb2(raiz)
	constructor = Constructor(metadatos.get("titulo") or nombre)
	notas: list[ET.Element] = []
	for cuerpo in _hijos(raiz, "body"):
		if cuerpo.get("name") in ("notes", "comments"):
			notas.append(cuerpo)
			continue
		_seccion(cuerpo, constructor, 1, opciones)
	for cuerpo in notas:
		constructor.encabezado(_("Notas"), 1)
		for seccion in _hijos(cuerpo, "section"):
			titulo = " ".join(_texto(t) for t in _hijos(seccion, "title")).strip()
			texto = " ".join(_texto(p) for p in seccion if quitar_espacio_nombres(p.tag) != "title")
			constructor.parrafo(f"{titulo}: {texto}" if titulo else texto)
	return constructor.documento(metadatos)
