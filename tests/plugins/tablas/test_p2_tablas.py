# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas del complemento «Datos tabulares: SQLite y CSV» (zc.tablas, diseño 2.0, 11.22 y 18.2)."""

from __future__ import annotations

import sqlite3

import pytest

from app.plugins import api
from tests.plugins import p2_comun

NOMBRE = "tablas"


@pytest.fixture
def zc():
	return p2_comun.anfitrion(NOMBRE)


@pytest.fixture
def interfaz(app_wx):
	falsa = p2_comun.InterfazFalsa()
	api.fijar_interfaz(falsa)
	yield falsa
	api.fijar_interfaz(None)


@pytest.fixture
def base(tmp_path):
	ruta = tmp_path / "agenda.db"
	conexion = sqlite3.connect(ruta)
	conexion.executescript("""
		CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, ciudad TEXT);
		INSERT INTO clientes (nombre, ciudad) VALUES ('Ana', 'León'), ('Íñigo', 'Ávila'), ('Luis', 'Lugo');
		CREATE TABLE pedidos (id INTEGER, cliente INTEGER, total REAL);
		INSERT INTO pedidos VALUES (1, 1, 10.5), (2, 2, 3);
	""")
	conexion.commit()
	conexion.close()
	return ruta


def _local():
	return api.pruebas.PanelFalso().proveedor


def test_una_base_con_dos_tablas_se_lista_como_dos_csv(zc, base):
	proveedor_modulo = p2_comun.modulo(zc, "servicios.proveedor")
	proveedor = proveedor_modulo.fabrica(_local(), str(base))
	nombres = [e.nombre for e in proveedor.listar("")]
	assert nombres == ["clientes.csv", "pedidos.csv"]
	with proveedor.abrir_lectura("clientes.csv") as flujo:
		texto = flujo.read().decode("utf-8-sig")
	assert texto.splitlines()[0] == "id,nombre,ciudad"
	assert "2,Íñigo,Ávila" in texto
	assert not proveedor.capacidades.escribir


def test_un_db_que_no_es_sqlite_da_no_admitido(zc, tmp_path):
	proveedor_modulo = p2_comun.modulo(zc, "servicios.proveedor")
	falso = tmp_path / "Thumbs.db"
	falso.write_bytes(b"\xd0\xcf\x11\xe0 no es sqlite")
	with pytest.raises(api.NoAdmitido):
		proveedor_modulo.fabrica(_local(), str(falso))


def test_el_csv_con_punto_y_coma_y_tildes_en_windows_1252_muestra_las_cabeceras(zc, interfaz, tmp_path):
	archivo = tmp_path / "precios.csv"
	archivo.write_bytes("Artículo;Año;Precio\r\nCañón;2024;1.234,50\r\nBotón;2023;9,99\r\n".encode("cp1252"))
	datos = p2_comun.modulo(zc, "servicios.datos")
	tabla = zc.instancia.cargador(_local(), str(archivo))(None)
	assert tabla.cabeceras == ["Artículo", "Año", "Precio"]
	assert tabla.separador == ";" and tabla.codificacion == "Windows-1252"
	assert tabla.filas[0] == ("Cañón", "2024", "1.234,50")
	assert datos.ordenar(tabla, [0, 1], 2) == [1, 0]
	assert datos.filtrar(tabla, "botón") == [1]


def test_select_da_sus_filas_y_delete_se_rechaza_en_solo_lectura(zc, base):
	sqlite = p2_comun.modulo(zc, "servicios.sqlite")
	tabla = sqlite.consultar(str(base), "SELECT nombre FROM clientes WHERE ciudad LIKE 'L%' ORDER BY nombre")
	assert tabla.cabeceras == ["nombre"]
	assert tabla.filas == [("Ana",), ("Luis",)]
	with pytest.raises(sqlite.ErrorSQL, match="solo lectura"):
		sqlite.consultar(str(base), "DELETE FROM clientes")
	assert sqlite.contar(str(base), "clientes") == 3
	resultado = sqlite.consultar(str(base), "DELETE FROM clientes WHERE id = 3", solo_lectura=False)
	assert resultado.filas == [("1 filas cambiadas",)]
	assert sqlite.contar(str(base), "clientes") == 2
	assert sqlite.estructura(str(base), "clientes")[1] == ("nombre", "TEXT")


def test_el_visor_pasa_revisar_teclado_y_muestra_la_tabla(zc, interfaz, base):
	visor_modulo = p2_comun.modulo(zc, "ui.visor")
	sqlite = p2_comun.modulo(zc, "servicios.sqlite")
	visor = visor_modulo.VisorTabla(zc, "clientes", None, base_sqlite=str(base))
	try:
		p2_comun.revisar(visor.ventana)
		visor.mostrar(sqlite.leer_tabla(str(base), "clientes"))
		assert visor.lista.numero_filas() == 3
		assert visor.lista.GetColumn(1).GetText() == "nombre"
		assert visor.lista.texto_celda(1, 1) == "Íñigo"
		assert "3 filas y 3 columnas" in visor.estado.GetValue()
		visor.aplicar_filtro("lu")
		assert visor.lista.numero_filas() == 1 and visor.lista.texto_celda(0, 1) == "Luis"
		visor.aplicar_filtro("")
		visor.ordenar_por(1)
		visor.ordenar_por(1)
		assert [visor.lista.texto_celda(i, 1) for i in range(3)] == ["Luis", "Íñigo", "Ana"]
		assert "nombre: TEXT" in visor.texto_estructura()
	finally:
		visor.ventana.Destroy()


def test_el_dialogo_de_consulta_pasa_revisar_teclado_y_muestra_resultados(zc, interfaz, base):
	consulta_modulo = p2_comun.modulo(zc, "ui.consulta")
	sqlite = p2_comun.modulo(zc, "servicios.sqlite")
	dialogo = consulta_modulo.DialogoConsulta(None, zc, str(base), "SELECT * FROM pedidos")
	try:
		p2_comun.revisar(dialogo)
		dialogo.mostrar_resultado(sqlite.consultar(str(base), dialogo.sql.GetValue()))
		assert dialogo.lista.numero_filas() == 2
		assert dialogo.lista.texto_celda(0, 2) == "10.5"
		assert dialogo.exportar_boton.IsEnabled()
	finally:
		dialogo.Destroy()


def test_ver_tabla_sin_csv_avisa_y_consulta_encuentra_la_base(zc, interfaz, base, tmp_path):
	otro = tmp_path / "nota.txt"
	otro.write_text("hola", encoding="utf-8")
	zc.ejecutar("ver_tabla", api.pruebas.contexto_de_prueba(activo=p2_comun.panel([otro])))
	assert any("CSV" in a for a in interfaz.anuncios)
	zc.activar()
	assert zc.instancia.base_de(p2_comun.panel([base])) == str(base)
	assert zc.instancia.base_de(p2_comun.panel([otro])) is None
