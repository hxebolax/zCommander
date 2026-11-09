# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas del complemento «Lector de documentos» (zc.documentos, diseño 2.0, 11.2 y 18.2)."""

from __future__ import annotations

import importlib
import inspect
import zipfile

import pytest

from app.plugins import api
from tests.plugins import p2_comun

NOMBRE = "documentos"
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


@pytest.fixture
def zc():
	zc = p2_comun.anfitrion(NOMBRE)
	zc.activar()
	return zc


@pytest.fixture
def interfaz(app_wx):
	falsa = p2_comun.InterfazFalsa()
	api.fijar_interfaz(falsa)
	yield falsa
	api.fijar_interfaz(None)


def _local():
	return api.pruebas.PanelFalso().proveedor


# ── Generadores de documentos de prueba ──────────────────────────────────────


def crear_docx(ruta, parrafos):
	"""``parrafos``: lista de (estilo o None, texto)."""
	cuerpo = "".join(
		(f'<w:p><w:pPr><w:pStyle w:val="{estilo}"/></w:pPr><w:r><w:t>{texto}</w:t></w:r></w:p>' if estilo
			else f"<w:p><w:r><w:t>{texto}</w:t></w:r></w:p>")
		for estilo, texto in parrafos)
	cuerpo += ('<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Nombre</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Edad</w:t></w:r></w:p></w:tc></w:tr>'
		'<w:tr><w:tc><w:p><w:r><w:t>Ana</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>30</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
	estilos = (f'<w:styles {W}><w:style w:styleId="Ttulo1"><w:name w:val="heading 1"/></w:style>'
		'<w:style w:styleId="Ttulo2"><w:name w:val="heading 2"/></w:style></w:styles>')
	with zipfile.ZipFile(ruta, "w") as zip_:
		zip_.writestr("[Content_Types].xml", "<Types/>")
		zip_.writestr("word/document.xml", f"<w:document {W}><w:body>{cuerpo}</w:body></w:document>")
		zip_.writestr("word/styles.xml", estilos)
		zip_.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="x" xmlns:dc="http://purl.org/dc/elements/1.1/">'
			"<dc:title>Informe anual</dc:title><dc:creator>Ana Pérez</dc:creator></cp:coreProperties>")


def crear_pdf(ruta, textos, pypdf):
	"""Un PDF con una página por texto (``""`` = página en blanco), hecho con pypdf."""
	from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

	escritor = pypdf.PdfWriter()
	for texto in textos:
		pagina = escritor.add_blank_page(612, 792)
		if not texto:
			continue
		fuente = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
			NameObject("/BaseFont"): NameObject("/Helvetica")})
		pagina[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject(
			{NameObject("/F1"): escritor._add_object(fuente)})})
		flujo = DecodedStreamObject()
		flujo.set_data(f"BT /F1 18 Tf 72 700 Td ({texto}) Tj ET".encode("latin-1"))
		pagina[NameObject("/Contents")] = escritor._add_object(flujo)
	escritor.add_metadata({"/Title": "Prueba PDF", "/Author": "Luis"})
	with open(ruta, "wb") as salida:
		escritor.write(salida)


def crear_epub(ruta, capitulos, extra_manifiesto=""):
	with zipfile.ZipFile(ruta, "w") as zip_:
		zip_.writestr("mimetype", "application/epub+zip")
		zip_.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
			'<rootfile full-path="OEBPS/libro.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
		items = "".join(f'<item id="c{i}" href="cap{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(len(capitulos)))
		orden = "".join(f'<itemref idref="c{i}"/>' for i in range(len(capitulos)))
		zip_.writestr("OEBPS/libro.opf", '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
			'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>El libro</dc:title><dc:creator>Autora</dc:creator></metadata>'
			f"<manifest>{items}{extra_manifiesto}</manifest><spine>{orden}"
			+ ('<itemref idref="malo"/>' if extra_manifiesto else "") + "</spine></package>")
		for i, (titulo, texto) in enumerate(capitulos):
			zip_.writestr(f"OEBPS/cap{i}.xhtml", f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{titulo}</title></head>'
				f"<body><h1>{titulo}</h1><p>{texto}</p></body></html>")


# ── Pruebas mínimas de la ficha ───────────────────────────────────────────────


def test_un_docx_con_dos_encabezados_da_dos_secciones_con_su_nivel(zc, tmp_path):
	ruta = tmp_path / "informe.docx"
	crear_docx(ruta, [("Ttulo1", "Introducción"), (None, "Primer párrafo."), ("Ttulo2", "Detalles"), (None, "Segundo párrafo.")])
	documento = zc.visor("documento", str(ruta))
	assert [(s.titulo, s.nivel) for s in documento.secciones] == [("Introducción", 1), ("Detalles", 2)]
	assert documento.secciones[0].texto == "Primer párrafo."
	assert "Tabla de 2 columnas." in documento.secciones[1].texto
	assert "Fila 2: Ana; 30." in documento.secciones[1].texto
	assert documento.titulo == "Informe anual" and documento.metadatos["autor"] == "Ana Pérez"


def test_un_pdf_de_dos_paginas_da_pagina_2_de_2(zc, tmp_path):
	pypdf = importlib.import_module("pypdf")
	ruta = tmp_path / "doble.pdf"
	crear_pdf(ruta, ["Hola primera pagina del documento", "Adios segunda pagina del documento"], pypdf)
	documento = zc.visor("documento", str(ruta))
	assert [s.titulo for s in documento.secciones] == ["Página 1 de 2", "Página 2 de 2"]
	assert documento.secciones[1].pagina == 2
	assert "Adios segunda" in documento.secciones[1].texto
	assert not documento.aviso
	assert documento.metadatos["paginas"] == "2" and documento.metadatos["titulo"] == "Prueba PDF"


def test_un_pdf_sin_texto_da_el_aviso(zc, tmp_path):
	pypdf = importlib.import_module("pypdf")
	ruta = tmp_path / "escaneado.pdf"
	crear_pdf(ruta, ["", ""], pypdf)
	documento = zc.visor("documento", str(ruta))
	assert documento.aviso.startswith("PDF sin texto: probablemente escaneado")


def test_un_epub_con_dos_capitulos_da_dos_secciones_en_orden(zc, tmp_path):
	ruta = tmp_path / "libro.epub"
	crear_epub(ruta, [("Capítulo uno", "Érase una vez."), ("Capítulo dos", "Y colorín colorado.")])
	documento = zc.visor("documento", str(ruta))
	assert [s.titulo for s in documento.secciones] == ["Capítulo uno", "Capítulo dos"]
	assert documento.secciones[1].texto == "Y colorín colorado."
	assert documento.metadatos["autor"] == "Autora"


def test_un_miembro_malicioso_de_un_epub_no_sale_de_la_carpeta(zc, tmp_path):
	libros = tmp_path / "libros"
	libros.mkdir()
	ruta = libros / "malo.epub"
	crear_epub(ruta, [("Bueno", "Texto bueno.")], '<item id="malo" href="../../../fuera.xhtml" media-type="application/xhtml+xml"/>')
	with zipfile.ZipFile(ruta, "a") as zip_:
		zip_.writestr("../../fuera.xhtml", "<html><body><h1>Fuera</h1></body></html>")
	antes = set(libros.rglob("*"))
	documento = zc.visor("documento", str(ruta))
	assert [s.titulo for s in documento.secciones] == ["Bueno"]
	assert set(libros.rglob("*")) == antes
	assert not list(tmp_path.rglob("fuera.xhtml"))
	assert not (tmp_path / "fuera.xhtml").exists() and not (tmp_path.parent / "fuera.xhtml").exists()


def test_el_extractor_encuentra_hola_dentro_de_un_docx(zc, tmp_path):
	ruta = tmp_path / "carta.docx"
	crear_docx(ruta, [(None, "Querida Ana: hola desde Madrid.")])
	from app.plugins import registro

	extractor = registro.funcion("extractor", "zc.documentos")
	texto = extractor(_local(), str(ruta), None)
	assert "hola" in texto


# ── Otros formatos y funciones ───────────────────────────────────────────────


def test_odt_con_encabezado_nota_y_tabla(zc, tmp_path):
	ruta = tmp_path / "acta.odt"
	contenido = ('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
		'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0">'
		"<office:body><office:text><text:h text:outline-level=\"1\">Acta</text:h>"
		"<text:p>Se aprueba<text:note><text:note-citation>1</text:note-citation><text:note-body><text:p>Por unanimidad.</text:p>"
		"</text:note-body></text:note> el presupuesto.</text:p>"
		"<table:table><table:table-row><table:table-cell><text:p>A</text:p></table:table-cell>"
		"<table:table-cell><text:p>B</text:p></table:table-cell></table:table-row></table:table>"
		"</office:text></office:body></office:document-content>")
	with zipfile.ZipFile(ruta, "w") as zip_:
		zip_.writestr("mimetype", "application/vnd.oasis.opendocument.text")
		zip_.writestr("content.xml", contenido)
	documento = zc.visor("documento", str(ruta))
	seccion = documento.secciones[0]
	assert seccion.titulo == "Acta"
	assert "Se aprueba[1] el presupuesto." in seccion.texto
	assert "Tabla de 2 columnas." in seccion.texto
	assert seccion.texto.endswith("Notas:\nNota 1: Por unanimidad.")


def test_rtf_con_encabezado_tildes_y_unicode(zc, tmp_path):
	ruta = tmp_path / "nota.rtf"
	ruta.write_bytes(rb"{\rtf1\ansi\ansicpg1252{\fonttbl{\f0 Arial;}}{\stylesheet{\s0 Normal;}{\s1 heading 1;}}"
		rb"{\info{\title Mi nota}{\author Eva}}"
		rb"\pard\s1 Cap\'edtulo\par\pard Caf\'e9 y " + b"\x5c" + b"u8364?uros." + rb"\par"
		rb"\trowd\intbl uno\cell dos\cell\row\pard Fin.\par}")
	documento = zc.visor("documento", str(ruta))
	assert documento.titulo == "Mi nota" and documento.metadatos["autor"] == "Eva"
	assert documento.secciones[-1].titulo == "Capítulo"
	texto = documento.secciones[-1].texto
	assert "Café y €uros." in texto and "Fila 1: uno; dos." in texto and texto.endswith("Fin.")


def test_html_y_fb2(zc, tmp_path):
	html = tmp_path / "pagina.html"
	html.write_text('<html><head><title>Web</title><style>p{}</style></head><body><p>Antes</p><h2>Parte</h2>'
		'<p>Texto <img alt="un gato"> fin</p><ul><li>uno</li></ul><script>malo()</script></body></html>', encoding="utf-8")
	documento = zc.visor("documento", str(html))
	assert documento.titulo == "Web"
	assert [s.titulo for s in documento.secciones] == ["Web", "Parte"]
	assert "[Imagen: un gato]" in documento.secciones[1].texto and "malo" not in documento.secciones[1].texto
	fb2 = tmp_path / "cuento.fb2"
	fb2.write_text('<?xml version="1.0" encoding="utf-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
		"<description><title-info><book-title>Cuento</book-title><author><first-name>Ana</first-name><last-name>Gil</last-name>"
		"</author></title-info></description><body><section><title><p>Uno</p></title><p>Había una vez.</p></section></body>"
		"</FictionBook>", encoding="utf-8")
	documento = zc.visor("documento", str(fb2))
	assert documento.titulo == "Cuento" and documento.metadatos["autor"] == "Ana Gil"
	assert documento.secciones[0].titulo == "Uno" and documento.secciones[0].texto == "Había una vez."


def test_un_formato_desactivado_va_al_visor_interno_y_uno_danado_da_su_aviso(tmp_path):
	zc = p2_comun.anfitrion(NOMBRE, config={"formatos": ["pdf"]})
	ruta = tmp_path / "a.html"
	ruta.write_text("<p>hola</p>", encoding="utf-8")
	assert zc.visor("documento", str(ruta)) is None
	roto = tmp_path / "roto.pdf"
	roto.write_bytes(b"%PDF-1.4 esto no es un pdf")
	documento = zc.visor("documento", str(roto))
	assert "dañado" in documento.aviso


def test_columnas_e_informacion(zc, tmp_path):
	ruta = tmp_path / "informe.docx"
	crear_docx(ruta, [("Ttulo1", "Uno")])
	entrada = p2_comun.entrada(ruta)
	assert zc.columna("titulo", entrada) == "Informe anual"
	assert zc.columna("autor", entrada) == "Ana Pérez"
	assert zc.columna("paginas", entrada) is None
	lineas = zc.instancia.lineas_info(entrada, _local())
	assert lineas[0] == "Documento Word" and "Autor: Ana Pérez" in lineas


def test_la_funcion_exportada_tiene_la_firma_de_la_tabla(zc):
	from app.plugins import registro

	exportado = registro.exportados("zc.documentos")
	parametros = list(inspect.signature(exportado["convertir"]).parameters)
	assert parametros[:3] == ["proveedor", "ruta", "cancelacion"]


def test_convertir_a_texto_y_markdown(zc, tmp_path):
	salida = p2_comun.modulo(zc, "servicios.salida")
	ruta = tmp_path / "informe.docx"
	crear_docx(ruta, [("Ttulo1", "Introducción"), (None, "Hola.")])
	elementos = [salida.Elemento(_local(), str(ruta), str(tmp_path / "informe.md"))]
	op = salida.OperacionConvertirDocumentos(elementos, "md", "utf-8", lambda p, r, c: zc.instancia.convertir(p, r, c))
	p2_comun.ejecutar_operacion(op)
	assert op.estado == api.Estado.TERMINADA
	texto = (tmp_path / "informe.md").read_text(encoding="utf-8")
	assert texto.startswith("# Informe anual") and "## Introducción" in texto and "Hola." in texto
	# Ya existe: el decisor dice «Omitir».
	op = salida.OperacionConvertirDocumentos(elementos, "md", "utf-8", lambda p, r, c: zc.instancia.convertir(p, r, c))
	p2_comun.ejecutar_operacion(op, api.pruebas.DecisorFalso([1]))
	assert op.instantanea().omitidos == 1


def test_la_orden_convertir_lanza_la_operacion_y_el_dialogo_pasa_revisar_teclado(zc, interfaz, tmp_path):
	import wx

	ruta = tmp_path / "informe.docx"
	crear_docx(ruta, [(None, "Hola.")])
	interfaz.respuestas["mostrar_modal"] = [wx.ID_OK]
	zc.ejecutar("convertir", api.pruebas.contexto_de_prueba(activo=p2_comun.panel([ruta])))
	assert len(zc.operaciones_lanzadas) == 1
	assert zc.operaciones_lanzadas[0].elementos[0].destino == str(tmp_path / "informe.txt")
	for ventana in zc.instancia.ventanas_para_revisar(None):
		try:
			p2_comun.revisar(ventana)
		finally:
			ventana.Destroy()


def test_propiedades_anuncia_los_metadatos(zc, interfaz, tmp_path):
	ruta = tmp_path / "informe.docx"
	crear_docx(ruta, [(None, "Hola.")])
	zc.ejecutar("propiedades", api.pruebas.contexto_de_prueba(activo=p2_comun.panel([ruta])))
	p2_comun.esperar_tareas(zc)
	assert any("Título: Informe anual" in a for a in interfaz.anuncios)
