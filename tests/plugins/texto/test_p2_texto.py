# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas del complemento «Codificaciones y fines de línea» (zc.texto, diseño 2.0, 11.25 y 18.2)."""

from __future__ import annotations

import codecs

import pytest

from app.plugins import api
from tests.plugins import p2_comun

NOMBRE = "texto"


@pytest.fixture
def zc():
	return p2_comun.anfitrion(NOMBRE)


@pytest.fixture
def conversion(zc):
	return p2_comun.modulo(zc, "servicios.conversion")


@pytest.fixture
def deteccion(zc):
	return p2_comun.modulo(zc, "servicios.deteccion")


@pytest.fixture
def operacion(zc):
	return p2_comun.modulo(zc, "servicios.operacion")


@pytest.fixture
def interfaz(app_wx):
	falsa = p2_comun.InterfazFalsa()
	api.fijar_interfaz(falsa)
	yield falsa
	api.fijar_interfaz(None)


def _convertir(operacion, conversion, rutas, opciones, copia_bak, tmp_path):
	respaldos = operacion.Respaldos(tmp_path / "deshacer")
	op = operacion.OperacionConvertirTexto(api.pruebas.PanelFalso().proveedor, [str(r) for r in rutas], opciones, copia_bak, respaldos)
	p2_comun.ejecutar_operacion(op)
	return op, respaldos


def test_windows_1252_con_ano_pasa_a_utf8_con_los_mismos_caracteres(tmp_path, operacion, conversion, deteccion):
	archivo = tmp_path / "carta.txt"
	archivo.write_bytes("Feliz año, señoría.\r\nÚltima línea\r\n".encode("cp1252"))
	assert deteccion.detectar_archivo(str(archivo)).codificacion == "cp1252"
	op, _r = _convertir(operacion, conversion, [archivo], conversion.Opciones(destino="utf8"), True, tmp_path)
	assert op.estado == api.Estado.TERMINADA
	assert archivo.read_bytes().decode("utf-8") == "Feliz año, señoría.\r\nÚltima línea\r\n"
	assert (tmp_path / "carta.txt.bak").read_bytes() == "Feliz año, señoría.\r\nÚltima línea\r\n".encode("cp1252")


def test_fines_mezclados_se_informan_y_quedan_en_crlf(tmp_path, operacion, conversion, deteccion):
	archivo = tmp_path / "mezcla.txt"
	archivo.write_bytes(b"uno\r\ndos\ntres\rcuatro")
	assert deteccion.detectar_archivo(str(archivo)).fin_linea == "Mezclado"
	_convertir(operacion, conversion, [archivo], conversion.Opciones(fin_linea="crlf"), False, tmp_path)
	assert archivo.read_bytes() == b"uno\r\ndos\r\ntres\r\ncuatro"
	assert deteccion.detectar_archivo(str(archivo)).fin_linea == "CRLF"


def test_deshacer_recupera_los_bytes_originales(tmp_path, monkeypatch, operacion, conversion):
	from app.services.operaciones.deshacer import RegistroDeshacer
	from app.services.windows import papelera

	original = "Canción de año\nviejo\t \n".encode("cp1252")
	archivo = tmp_path / "cancion.txt"
	archivo.write_bytes(original)
	enviados: list[str] = []

	def a_papelera(rutas, *args, **kwargs):
		for ruta in rutas:
			enviados.append(ruta)
			import os

			os.remove(ruta)

	monkeypatch.setattr(papelera, "enviar", a_papelera)
	op, _r = _convertir(operacion, conversion, [archivo],
		conversion.Opciones(destino="utf8_bom", fin_linea="crlf", quitar_espacios_finales=True), False, tmp_path)
	assert archivo.read_bytes() == codecs.BOM_UTF8 + "Canción de año\r\nviejo\r\n".encode("utf-8")
	assert op.deshacer is not None
	resultado = RegistroDeshacer().deshacer(op.deshacer)
	assert archivo.read_bytes() == original
	assert not resultado.omitidos
	assert len(enviados) == 1 and not (tmp_path / "cancion.txt.bak").exists()


def test_sin_cambios_no_toca_el_archivo(tmp_path, operacion, conversion):
	archivo = tmp_path / "ya.txt"
	archivo.write_bytes(b"ya en utf-8\r\n")
	op, _r = _convertir(operacion, conversion, [archivo], conversion.Opciones(), True, tmp_path)
	assert op.instantanea().omitidos == 1 and op.deshacer is None
	assert not (tmp_path / "ya.txt.bak").exists()


def test_un_byte_no_valido_no_se_convierte_y_el_informe_lo_situa(tmp_path, operacion, conversion):
	archivo = tmp_path / "roto.txt"
	archivo.write_bytes(b"a\xf1o uno\r\nmal\x81aqui\r\n")
	op, _r = _convertir(operacion, conversion, [archivo], conversion.Opciones(), True, tmp_path)
	assert op.estado == api.Estado.TERMINADA_CON_ERRORES
	assert archivo.read_bytes() == b"a\xf1o uno\r\nmal\x81aqui\r\n"
	informe = conversion.informar(str(archivo), archivo.read_bytes())
	assert informe.total == 1
	assert informe.problemas[0][:2] == (2, 4)
	assert "Línea 2, columna 4" in conversion.texto_informe([informe])


def test_oem_850_y_ascii_y_utf16(deteccion):
	assert deteccion.detectar("Año y canción".encode("cp850")).codificacion == "cp850"
	assert deteccion.detectar(b"solo ascii\n").nombre_codificacion == "ASCII"
	assert deteccion.detectar("hola".encode("utf-16")).codificacion == "utf-16-le"
	assert deteccion.detectar(bytes(range(256)) * 4).binario


def test_tabuladores_y_espacios(conversion):
	texto, cambios = conversion.transformar("\tuno\n        dos  \n", conversion.Opciones(tabuladores="a_espacios", ancho_tabulador=4))
	assert texto == "    uno\n        dos  \n" and cambios == 1
	texto, cambios = conversion.transformar("        dos  \n", conversion.Opciones(tabuladores="a_tabuladores", ancho_tabulador=4,
		quitar_espacios_finales=True))
	assert texto == "\t\tdos\n" and cambios == 1


def test_columnas(tmp_path, zc):
	archivo = tmp_path / "a.txt"
	archivo.write_bytes("año\n".encode("cp1252"))
	entrada = p2_comun.entrada(archivo)
	assert zc.columna("codificacion", entrada) == "Windows-1252"
	assert zc.columna("fin_linea", entrada) == "LF"
	binario = tmp_path / "b.txt"
	binario.write_bytes(b"\x00\x00\x01\x02")
	assert zc.columna("codificacion", p2_comun.entrada(binario)) is None
	assert zc.columna("codificacion", p2_comun.entrada(tmp_path / "a.txt").con(nombre="foto.png")) is None


def test_informe_desde_la_orden(tmp_path, zc, interfaz):
	archivo = tmp_path / "malo.txt"
	archivo.write_bytes(b"bien\nnulo\x00aqui\n" + "año".encode("utf-8"))
	contexto = api.pruebas.contexto_de_prueba(activo=p2_comun.panel([archivo]))
	zc.ejecutar("informe", contexto)
	p2_comun.esperar_tareas(zc)
	assert interfaz.textos and "malo.txt" in interfaz.textos[0][1]


def test_convertir_desde_la_orden_lanza_la_operacion(tmp_path, zc, interfaz):
	import wx

	archivo = tmp_path / "carta.txt"
	archivo.write_bytes("año\n".encode("cp1252"))
	interfaz.respuestas["mostrar_modal"] = [wx.ID_OK]
	contexto = api.pruebas.contexto_de_prueba(activo=p2_comun.panel([archivo]))
	zc.ejecutar("convertir", contexto)
	assert len(zc.operaciones_lanzadas) == 1
	assert zc.operaciones_lanzadas[0].orden_origen == "zc.texto:convertir"


def test_el_dialogo_pasa_revisar_teclado_y_muestra_la_vista_previa(tmp_path, zc, interfaz, conversion):
	dialogo_modulo = p2_comun.modulo(zc, "ui.dialogo_convertir")
	paquete = __import__(type(zc.instancia).__module__, fromlist=["fila_previa"])
	archivo = tmp_path / "carta.txt"
	archivo.write_bytes("año\nmás\n".encode("cp1252"))

	def calcular(opciones, al_listo):
		al_listo([paquete.fila_previa(str(archivo), opciones)])

	dialogo = dialogo_modulo.DialogoConvertir(None, zc.ui, [str(archivo)], conversion.Opciones(fin_linea="crlf"), True, calcular)
	try:
		p2_comun.revisar(dialogo)
		assert dialogo.previa.numero_filas() == 1
		fila = dialogo.previa.valores_fila(0)
		assert fila[:3] == ["carta.txt", "Windows-1252", "LF"]
		assert "2 líneas cambian" in fila[3]
		assert "1 de 1" in dialogo.estado.GetValue()
	finally:
		dialogo.Destroy()
