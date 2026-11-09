# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas del complemento «Editor hexadecimal accesible» (zc.hexadecimal, diseño 2.0, 11.10 y 18.2)."""

from __future__ import annotations

import os

import pytest

from app.plugins import api
from tests.plugins import p2_comun

NOMBRE = "hexadecimal"


@pytest.fixture
def zc():
	zc = p2_comun.anfitrion(NOMBRE)
	zc.activar()
	return zc


@pytest.fixture
def piezas(zc):
	return p2_comun.modulo(zc, "servicios.piezas")


@pytest.fixture
def herramientas(zc):
	return p2_comun.modulo(zc, "servicios.herramientas")


@pytest.fixture
def interfaz(app_wx):
	falsa = p2_comun.InterfazFalsa()
	api.fijar_interfaz(falsa)
	yield falsa
	api.fijar_interfaz(None)


def test_la_tabla_de_piezas_inserta_sobrescribe_borra_deshace_rehace_y_guarda_3_mb(tmp_path, piezas):
	original = bytes(range(256)) * (3 * 1024 * 1024 // 256)
	ruta = tmp_path / "grande.bin"
	ruta.write_bytes(original)
	tabla = piezas.TablaPiezas(str(ruta))
	try:
		esperado = bytearray(original)
		tabla.insertar(10, b"ABC")
		esperado[10:10] = b"ABC"
		tabla.sobrescribir(2_000_000, b"\xff\xfe")
		esperado[2_000_000:2_000_002] = b"\xff\xfe"
		tabla.borrar(100, 50)
		del esperado[100:150]
		assert len(tabla) == len(esperado)
		assert tabla.leer(0, 200) == bytes(esperado[:200])
		assert tabla.deshacer() == 100
		assert tabla.leer(100, 50) == bytes(original[97:147])
		assert tabla.rehacer() == 100
		assert tabla.modificado
		tabla.guardar(copia_seguridad=True)
		assert ruta.read_bytes() == bytes(esperado)
		assert (tmp_path / "grande.bin.bak").read_bytes() == original
		assert not tabla.modificado and len(tabla) == len(esperado)
		assert not [n for n in os.listdir(tmp_path) if n.endswith(".zctmp")]
	finally:
		tabla.cerrar()


def test_sobrescribir_al_final_hace_crecer_el_archivo(piezas):
	tabla = piezas.TablaPiezas(datos=b"Hola")
	tabla.sobrescribir(3, b"a!!")
	assert tabla.leer(0, 10) == b"Hola!!"
	tabla.iniciar_grupo()
	tabla.borrar(0, 1)
	tabla.insertar(0, b"h")
	tabla.terminar_grupo(0)
	assert tabla.leer(0, 10) == b"hola!!"
	assert tabla.deshacer() == 0 and tabla.leer(0, 10) == b"Hola!!"


def test_buscar_48_comodin_6c_encuentra_hel(piezas, herramientas):
	tabla = piezas.TablaPiezas(datos=b"xxHello, Hola Hel")
	patron = herramientas.patron_hexadecimal("48 ?? 6C")
	assert herramientas.buscar(tabla, patron, 0) == 2
	assert herramientas.buscar(tabla, patron, 3) == 9
	assert herramientas.buscar(tabla, patron, 9, atras=True) == 2
	assert herramientas.buscar_todos(tabla, patron) == [2, 9, 14]
	assert herramientas.buscar(tabla, herramientas.patron_texto("Hola", "cp1252"), 0) == 9
	with pytest.raises(ValueError):
		herramientas.patron_hexadecimal("4G")


def test_el_inspector_de_01_00_00_00(herramientas):
	little = dict(herramientas.inspeccionar(b"\x01\x00\x00\x00", "little"))
	big = dict(herramientas.inspeccionar(b"\x01\x00\x00\x00", "big"))
	assert little["Entero de 32 bits sin signo"] == "1"
	assert big["Entero de 32 bits sin signo"] == "16777216"
	assert "Fecha Unix de 32 bits" in little


def test_ir_a_0x10_mas_16_y_50_por_ciento(herramientas):
	assert herramientas.destino("0x10", 0, 1000) == 16
	assert herramientas.destino("+16", 100, 1000) == 116
	assert herramientas.destino("-16", 100, 1000) == 84
	assert herramientas.destino("50%", 0, 1000) == 500
	assert herramientas.destino("1234", 0, 1000) == 999
	with pytest.raises(ValueError):
		herramientas.destino("hola", 0, 1000)


def test_volcado_y_anuncio(herramientas):
	assert herramientas.linea_volcado(16, b"Hola", 16, "cp1252").startswith("00000010  48 6F 6C 61")
	assert herramientas.linea_volcado(16, b"Hola", 16, "cp1252").endswith("  Hola")
	assert herramientas.anuncio(0x1A, b"O", "cp1252", False) == "Desplazamiento 0x1A, 4F, letra O"
	assert herramientas.anuncio(0x1A, b"O", "cp1252", True).endswith("decimal 79, binario 01001111")


def test_la_ventana_pasa_revisar_teclado_y_mover_el_cursor_anuncia(zc, interfaz, piezas):
	ventana_modulo = p2_comun.modulo(zc, "ui.ventana")
	editor = ventana_modulo.EditorHexadecimal(zc, piezas.TablaPiezas(datos=b"Hola mundo, esto es una prueba larga."), "a.bin")
	dialogo = ventana_modulo.DialogoBuscar(None, zc.ui, True, False, None)
	try:
		p2_comun.revisar(editor.ventana, teclas_propias=["F2", "Tab"])
		p2_comun.revisar(dialogo)
		zc.anuncios.clear()
		editor.mover(1)
		assert zc.anuncios[-1][0] == "Desplazamiento 0x1, 6F, letra o"
		editor.mover(17)
		assert zc.anuncios[-1][0] == "Desplazamiento 0x11, 65, letra e"
		assert "Desplazamiento 0x11 de 0x25" in editor.barra.GetStatusText()
		assert editor.volcado.GetInsertionPoint() == editor.volcado.XYToPosition(10 + 3, 1)
		editor.cambiar_columna()
		assert editor.volcado.GetInsertionPoint() == editor.volcado.XYToPosition(10 + 16 * 3 + 1 + 1, 1)
	finally:
		editor.tabla.cerrar()
		editor.ventana.Destroy()
		dialogo.Destroy()


def test_editar_en_la_ventana(zc, interfaz, piezas):
	ventana_modulo = p2_comun.modulo(zc, "ui.ventana")
	editor = ventana_modulo.EditorHexadecimal(zc, piezas.TablaPiezas(datos=b"Hola"), "a.bin")
	try:
		editor.escribir_digito("4")
		editor.escribir_digito("a")
		assert editor.tabla.leer(0, 4) == b"Jola"
		editor.escribir_digito("z")
		assert zc.sonidos_pedidos[-1] == "zc.hexadecimal:no_valido"
		editor.cambiar_modo()
		editor.cambiar_columna()
		editor.escribir_texto("!")
		assert editor.tabla.leer(0, 5) == b"J!ola"
		editor.borrar(retroceso=True)
		assert editor.tabla.leer(0, 5) == b"Jola"
		editor.cambiar_columna()
		editor.pegar_texto("6F 6B")
		assert editor.tabla.leer(0, 6) == b"Jokola"
		editor.deshacer()
		assert editor.tabla.leer(0, 6) == b"Jola"
		assert editor.tabla.modificado and editor.ventana.GetTitle().startswith("*a.bin")
	finally:
		editor.tabla.cerrar()
		editor.ventana.Destroy()


def test_la_orden_abre_el_editor_y_el_solo_lectura(zc, interfaz, tmp_path, monkeypatch):
	from app.ui import api_ui

	# Las ventanas de las pruebas no se muestran (conftest): solo se comprueba que la orden la crea.
	mostradas = []
	monkeypatch.setattr(api_ui.VentanaComplemento, "Show", lambda self, show=True: mostradas.append(show) or True)
	ruta = tmp_path / "datos.bin"
	ruta.write_bytes(b"\x00\x01\x02")
	zc.ejecutar("editar", api.pruebas.contexto_de_prueba(activo=p2_comun.panel([ruta])))
	editor = zc.instancia.editores[-1]
	try:
		assert mostradas == [True]
		assert editor.tabla.leer(0, 3) == b"\x00\x01\x02" and not editor.solo_lectura
		editor.solo_lectura = True
		editor.escribir_digito("4")
		editor.escribir_digito("1")
		assert editor.tabla.leer(0, 1) == b"\x00"
	finally:
		editor.tabla.cerrar()
		editor.ventana.Destroy()
