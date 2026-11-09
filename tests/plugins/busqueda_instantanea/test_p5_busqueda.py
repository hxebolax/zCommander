# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de zc.busqueda_instantanea (diseño 2.0, 11.5 y 18.2): sin Everything ni índice reales."""

from __future__ import annotations

import datetime

import pytest

from app.plugins import api, registro
from tests.plugins import p5_comun

NOMBRE = "busqueda_instantanea"


@pytest.fixture
def zc():
	return p5_comun.anfitrion(NOMBRE)


@pytest.fixture
def consulta(zc):
	return p5_comun.modulo(NOMBRE, "consulta")


@pytest.fixture
def motores(zc):
	return p5_comun.modulo(NOMBRE, "motores")


def test_sql_del_indice_de_windows_para_pdf_en_una_carpeta(consulta):
	assert consulta.a_sql_windows("*.pdf", carpeta="C:\\Docs") == (
		"SELECT TOP 1000 System.ItemPathDisplay FROM SYSTEMINDEX WHERE SCOPE='file:C:/Docs' AND System.FileName LIKE '%.pdf'")


def test_sql_traduce_la_sintaxis_de_everything(consulta):
	hoy = datetime.date(2026, 11, 9)
	sql = consulta.a_sql_windows('ext:pdf;docx size:>1gb dm:today !borrador "informe anual"', max_resultados=50,
		contenido="factura de luz", hoy=hoy)
	assert sql.startswith("SELECT TOP 50 System.ItemPathDisplay FROM SYSTEMINDEX WHERE ")
	assert "(System.FileExtension = '.pdf' OR System.FileExtension = '.docx')" in sql
	assert f"System.Size > {1024 ** 3}" in sql
	assert "System.DateModified >= '2026/11/09'" in sql
	assert "NOT System.FileName LIKE '%borrador%'" in sql
	assert "System.FileName LIKE '%informe anual%'" in sql
	assert "CONTAINS(*, '\"factura de luz\"')" in sql


def test_sql_escapa_comillas_y_comodines(consulta):
	sql = consulta.a_sql_windows("o'neil_?")
	assert "LIKE 'o''neil[_]_'" in sql


def test_patrones_del_dialogo_buscar_en_sintaxis_de_everything(consulta):
	assert consulta.desde_patrones("*.txt;*.md | *.bak") == "*.txt|*.md !*.bak"
	assert consulta.desde_patrones("*") == ""


def test_analizador_de_la_respuesta_de_everything(consulta):
	bufer = consulta.respuesta_de_ejemplo([
		("factura.pdf", "C:\\Docs", 0),
		("Fotos", "D:\\", consulta.ELEMENTO_CARPETA),
		("C:", "", consulta.ELEMENTO_UNIDAD),
	])
	assert consulta.leer_respuesta_everything(bufer) == [
		("C:\\Docs\\factura.pdf", False), ("D:\\Fotos", True), ("C:\\", True)]


def test_respuesta_de_everything_dañada_se_rechaza(consulta):
	with pytest.raises(consulta.ErrorConsulta):
		consulta.leer_respuesta_everything(b"\x00" * 10)
	bufer = bytearray(consulta.respuesta_de_ejemplo([("a.txt", "C:\\", 0)]))
	bufer[20:24] = (99).to_bytes(4, "little")  # dice traer 99 elementos
	with pytest.raises(consulta.ErrorConsulta):
		consulta.leer_respuesta_everything(bytes(bufer))


def test_consulta_de_everything_tiene_la_cabecera_del_protocolo(consulta):
	datos = consulta.consulta_everything("ext:pdf", 0x1234, 7, 100)
	assert datos[:20] == (0x1234).to_bytes(4, "little") + (7).to_bytes(4, "little") + bytes(8) + (100).to_bytes(4, "little")
	assert datos[20:] == "ext:pdf".encode("utf-16-le") + b"\x00\x00"


def test_filtro_de_excluidas_y_maximo(consulta):
	rutas = ["C:\\Windows\\a.pdf", "C:\\Docs\\b.pdf", "C:\\WindowsViejo\\c.pdf", "D:\\d.pdf"]
	assert consulta.filtrar(rutas, ["c:\\windows"], 2) == ["C:\\Docs\\b.pdf", "C:\\WindowsViejo\\c.pdf"]


def test_sin_motores_buscar_explica_que_hacer(motores, monkeypatch):
	monkeypatch.setattr(motores, "everything_disponible", lambda: False)

	def sin_indice(sql, cancelacion=None):
		raise motores.SinMotor("El índice de búsqueda de Windows no responde")

	monkeypatch.setattr(motores, "buscar_windows", sin_indice)
	with pytest.raises(motores.SinMotor) as error:
		motores.buscar("factura")
	assert "Everything no está abierto" in str(error.value)
	assert "Windows Search" in str(error.value)


def test_proveedor_del_dialogo_entrega_las_rutas(zc, motores, monkeypatch):
	pedidas = {}

	def falso(texto, **opciones):
		pedidas["texto"] = texto
		return motores.Resultado(motores.EVERYTHING, ["C:\\a.txt", "C:\\b.txt"])

	monkeypatch.setattr(motores, "buscar", falso)
	funcion = registro.funcion("busqueda", "zc.busqueda_instantanea:instantanea")
	entregadas: list[str] = []
	funcion(api.CriteriosBusqueda(nombres="*.txt | *.bak"), entregadas.append, None)
	assert pedidas["texto"] == "*.txt !*.bak"
	assert entregadas == ["C:\\a.txt", "C:\\b.txt"]


def test_proveedor_sin_motores_lo_anuncia_sin_fallar(zc, motores, monkeypatch):
	def sin_motor(texto, **opciones):
		raise motores.SinMotor(motores.texto_sin_motores())

	monkeypatch.setattr(motores, "buscar", sin_motor)
	funcion = registro.funcion("busqueda", "zc.busqueda_instantanea:instantanea")
	entregadas: list[str] = []
	funcion(api.CriteriosBusqueda(nombres="*.txt"), entregadas.append, None)
	assert entregadas == []
	assert "Everything no está abierto" in zc.anuncios[-1][0]


def test_orden_con_manejador_real(zc):
	manejador = registro.manejador("zc.busqueda_instantanea:abrir")
	assert manejador is not None and not getattr(manejador, "provisional", False)


# ── Ventana (wx) ─────────────────────────────────────────────────────────────


@pytest.fixture
def ventana(app_wx, zc):
	interfaz = p5_comun.con_interfaz()
	modulo = p5_comun.modulo(NOMBRE, "ventana")
	creada = modulo.VentanaBusqueda(zc, None, comprobar_motores=False)
	yield creada, interfaz
	creada.marco.Destroy()
	api.fijar_interfaz(None)


def test_ventana_pasa_revisar_teclado(ventana):
	creada, _interfaz = ventana
	assert p5_comun.problemas_de_teclado(creada.marco) == []


def test_ventana_sin_motores_lo_explica(ventana):
	creada, _interfaz = ventana
	creada.mostrar_motores([])
	assert "No hay ningún motor de búsqueda instantánea disponible" in creada.estado.GetValue()
	creada.mostrar_motores(["windows"])
	assert "índice de búsqueda de Windows" in creada.estado.GetValue()


def test_ventana_muestra_resultados_anuncia_el_recuento_y_va_al_archivo(ventana, zc, motores):
	creada, interfaz = ventana
	creada._generacion = 3
	creada.mostrar_resultado(3, motores.Resultado(motores.EVERYTHING, ["C:\\Docs\\factura.pdf", "C:\\b.txt"]))
	assert creada.lista.numero_filas() == 2
	assert creada.lista.valores_fila(0) == ["factura.pdf", "C:\\Docs"]
	assert zc.anuncios[-1] == ("2 resultados", api.RESULTADO)
	# Un resultado viejo (otra búsqueda) no pisa la lista.
	creada.mostrar_resultado(2, motores.Resultado(motores.EVERYTHING, []))
	assert creada.lista.numero_filas() == 2
	creada.ir_al_archivo(0)
	assert interfaz.rutas == ["C:\\Docs\\factura.pdf"]


def test_busquedas_guardadas_persisten(ventana, zc):
	creada, _interfaz = ventana
	creada.campo.ChangeValue("ext:pdf factura")
	creada.guardar_busqueda()
	modulo = p5_comun.modulo(NOMBRE, "ventana")
	assert modulo.leer_guardadas(zc.datos) == ["ext:pdf factura"]
	creada.olvidar_busqueda()
	assert modulo.leer_guardadas(zc.datos) == []
