# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""PDF con pypdf (vendorizado en ``lib/``; BSD-3-Clause).

Con «marcas de página» (por defecto), cada página es una sección «Página N de M»
con su número, así el visor va de página en página (F6) y Ctrl+P va a una.
Un PDF con muy poco texto para sus páginas se marca «PDF sin texto:
probablemente escaneado» (``Documento.aviso``).
"""

from __future__ import annotations

import io
import logging
from typing import Any

from app.plugins import api

from .comun import Constructor, ErrorDocumento, Opciones, _, limpiar

log = logging.getLogger("zcplugins.zc.documentos")

#: Media de caracteres por página por debajo de la cual se considera escaneado.
MINIMO_POR_PAGINA = 20


def _pypdf() -> Any:
	"""pypdf se importa por su nombre (lo resuelve el buscador de ``lib/`` del complemento) y solo al usarlo."""
	import pypdf

	logging.getLogger("pypdf").setLevel(logging.ERROR)
	return pypdf


def _lector(datos: bytes) -> Any:
	pypdf = _pypdf()
	try:
		lector = pypdf.PdfReader(io.BytesIO(datos), strict=False)
		if lector.is_encrypted:
			try:
				resultado = lector.decrypt("")
			except Exception as error:  # noqa: BLE001 - pypdf lanza varios tipos (falta de cryptography, AES...)
				raise ErrorDocumento(_("El PDF está protegido y no se puede abrir: {e}").format(e=error)) from error
			if not resultado:
				raise ErrorDocumento(_("El PDF está protegido con contraseña"))
		return lector
	except ErrorDocumento:
		raise
	except Exception as error:  # noqa: BLE001 - un PDF dañado puede lanzar casi cualquier cosa dentro de pypdf
		raise ErrorDocumento(_("El PDF está dañado o no se puede leer: {e}").format(e=error)) from error


def _texto_meta(valor: Any) -> str:
	try:
		return str(valor).strip() if valor else ""
	except Exception:  # noqa: BLE001 - metadatos con codificaciones raras
		return ""


def _fecha(valor: Any) -> str:
	"""«D:20240131120000+01'00'» → «2024-01-31»."""
	texto = _texto_meta(valor)
	if texto.startswith("D:"):
		texto = texto[2:]
	if len(texto) >= 8 and texto[:8].isdigit():
		return f"{texto[:4]}-{texto[4:6]}-{texto[6:8]}"
	return texto


def metadatos_lector(lector: Any) -> dict[str, str]:
	datos: dict[str, str] = {"paginas": str(len(lector.pages))}
	try:
		info = lector.metadata or {}
	except Exception:  # noqa: BLE001 - un diccionario de información dañado no impide leer el texto
		log.debug("Metadatos del PDF ilegibles", exc_info=True)
		info = {}
	for clave, campo in (("titulo", "/Title"), ("autor", "/Author"), ("asunto", "/Subject")):
		valor = _texto_meta(info.get(campo))
		if valor:
			datos[clave] = valor
	fecha = _fecha(info.get("/ModDate") or info.get("/CreationDate"))
	if fecha:
		datos["fecha"] = fecha
	return datos


def metadatos_pdf(datos: bytes) -> dict[str, str]:
	return metadatos_lector(_lector(datos))


def texto_pagina(pagina: Any) -> str:
	try:
		return pagina.extract_text() or ""
	except Exception:  # noqa: BLE001 - una página dañada no impide leer las demás
		log.debug("No se pudo extraer el texto de una página", exc_info=True)
		return ""


def parece_escaneado(textos: list[str]) -> bool:
	if not textos:
		return False
	caracteres = sum(len("".join(t.split())) for t in textos)
	return caracteres < MINIMO_POR_PAGINA * len(textos)


def sin_texto(datos: bytes, paginas: int = 3) -> bool:
	"""Mira las primeras ``paginas`` páginas: verdadero si casi no tienen texto (PDF escaneado)."""
	lector = _lector(datos)
	return parece_escaneado([texto_pagina(p) for p in list(lector.pages)[:paginas]])


AVISO_ESCANEADO = "PDF sin texto: probablemente escaneado."


def convertir_pdf(datos: bytes, nombre: str, opciones: Opciones, cancelacion: Any = None) -> api.Documento:
	lector = _lector(datos)
	metadatos = metadatos_lector(lector)
	total = len(lector.pages)
	constructor = Constructor(metadatos.get("titulo") or nombre)
	textos = []
	for numero, pagina in enumerate(lector.pages, start=1):
		api.comprobar(cancelacion)
		texto = texto_pagina(pagina)
		textos.append(texto)
		if opciones.marcas_pagina:
			constructor.encabezado(_("Página {n} de {t}").format(n=numero, t=total), 1, pagina=numero)
		constructor.parrafo(texto)
	aviso = _(AVISO_ESCANEADO) if parece_escaneado(textos) else ""
	documento = constructor.documento(metadatos, aviso)
	if not opciones.marcas_pagina and documento.secciones:
		primera = documento.secciones[0]
		documento = api.Documento(documento.titulo, (api.Seccion(primera.titulo, 1, primera.texto, 1),), documento.metadatos, aviso)
	return documento


def texto_plano(datos: bytes, cancelacion: Any = None) -> str:
	"""Todo el texto (para buscar dentro): sin secciones ni marcas."""
	lector = _lector(datos)
	partes = []
	for pagina in lector.pages:
		api.comprobar(cancelacion)
		partes.append(texto_pagina(pagina))
	return limpiar("\n".join(partes))
