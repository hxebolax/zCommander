# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas del complemento «Reconocimiento de texto, OCR» (zc.ocr, diseño 2.0, 11.3 y 18.2)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.plugins import api
from tests.plugins import p2_comun

NOMBRE = "ocr"
SALIDA_EJEMPLO = Path(__file__).with_name("salida_ocr_ps1.json")


@pytest.fixture
def zc():
	zc = p2_comun.anfitrion(NOMBRE)
	zc.activar()
	return zc


@pytest.fixture
def motor(zc):
	return p2_comun.modulo(zc, "servicios.motor")


@pytest.fixture
def interfaz(app_wx):
	falsa = p2_comun.InterfazFalsa()
	api.fijar_interfaz(falsa)
	yield falsa
	api.fijar_interfaz(None)


class MotorFalso:
	nombre = "falso"

	def __init__(self, motor_modulo, paginas=None):
		self.m = motor_modulo
		self.paginas = paginas or [["Primera línea", "Segunda línea"]]
		self.llamadas: list[str] = []

	def idiomas(self):
		return [("es-ES", "Español (España)"), ("en-US", "Inglés (Estados Unidos)")]

	def reconocer(self, ruta, idioma="", escala=2.0, cancelacion=None):
		self.llamadas.append(ruta)
		return self.m.Resultado([list(p) for p in self.paginas], "es-ES")


def test_con_un_motor_falso_una_imagen_da_su_texto_por_lineas_en_el_visor(zc, motor, interfaz, tmp_path):
	foto = tmp_path / "foto.png"
	foto.write_bytes(b"no importa")
	zc.instancia._motor = MotorFalso(motor)
	zc.ejecutar("reconocer", api.pruebas.contexto_de_prueba(activo=p2_comun.panel([foto])))
	p2_comun.esperar_tareas(zc)
	documento = interfaz.documentos[-1]
	assert documento.titulo == "foto"
	assert documento.secciones[0].texto == "Primera línea\nSegunda línea"
	assert zc.sonidos_pedidos[-1] == "zc.ocr:fin"
	assert any("2 líneas" in a for a in interfaz.anuncios)


def test_un_pdf_da_una_seccion_por_pagina(zc, motor, tmp_path):
	pdf = tmp_path / "carta.pdf"
	pdf.write_bytes(b"%PDF")
	zc.instancia._motor = MotorFalso(motor, [["uno"], ["dos"]])
	documento = zc.instancia.reconocer(api.pruebas.PanelFalso().proveedor, str(pdf))
	assert [(s.titulo, s.pagina, s.texto) for s in documento.secciones] == [("Página 1 de 2", 1, "uno"), ("Página 2 de 2", 2, "dos")]


def test_el_lote_crea_foto_txt_junto_a_foto_png_sin_sobrescribir(zc, motor, tmp_path):
	lotes = p2_comun.modulo(zc, "servicios.lotes")
	foto, otra = tmp_path / "foto.png", tmp_path / "otra.jpg"
	foto.write_bytes(b"x")
	otra.write_bytes(b"x")
	(tmp_path / "otra.txt").write_text("de antes", encoding="utf-8")
	zc.instancia._motor = MotorFalso(motor)
	op = lotes.OperacionLotes(api.pruebas.PanelFalso().proveedor, [str(foto), str(otra)], zc.instancia.reconocer_ruta)
	p2_comun.ejecutar_operacion(op)
	assert (tmp_path / "foto.txt").read_text(encoding="utf-8") == "Primera línea\nSegunda línea\n"
	assert (tmp_path / "otra.txt").read_text(encoding="utf-8") == "de antes"
	assert op.instantanea().omitidos == 1 and op.estado == api.Estado.TERMINADA


def test_la_orden_de_lotes_lanza_la_operacion(zc, interfaz, tmp_path):
	foto = tmp_path / "foto.png"
	foto.write_bytes(b"x")
	zc.ejecutar("lotes", api.pruebas.contexto_de_prueba(activo=p2_comun.panel([foto])))
	assert len(zc.operaciones_lanzadas) == 1
	assert zc.operaciones_lanzadas[0].orden_origen == "zc.ocr:lotes"


def test_el_analizador_acepta_la_salida_de_ejemplo_de_ocr_ps1(motor):
	datos = motor.analizar_salida(SALIDA_EJEMPLO.read_text(encoding="utf-8"))
	resultado = motor.resultado_de(datos)
	assert resultado.paginas == [["Hola mundo prueba"]] and resultado.idioma == "es-ES"
	assert motor.analizar_salida('aviso de PowerShell\n{"ok":true,"idiomas":[{"etiqueta":"es-ES","nombre":"Español"}]}')["idiomas"]
	with pytest.raises(motor.ErrorOCR, match="Archivo no encontrado"):
		motor.analizar_salida('{"ok":false,"codigo":"error","error":"Archivo no encontrado"}')
	with pytest.raises(motor.ErrorOCR):
		motor.analizar_salida("nada que ver")


def test_sin_idiomas_el_mensaje_explica_como_instalarlos(motor):
	with pytest.raises(motor.ErrorOCR) as error:
		motor.analizar_salida('{"ok":false,"codigo":"sin_idiomas","error":"x"}')
	assert error.value.codigo == "sin_idiomas"
	assert "Agregar un idioma" in error.value.mensaje and "Reconocimiento óptico de caracteres" in error.value.mensaje


def test_powershell_lanza_el_guion_sin_consola_y_lee_su_salida(zc, motor, tmp_path):
	llamadas = []

	def ejecutar(argumentos, tiempo_s=60, cancelacion=None):
		llamadas.append(argumentos)
		return api.ResultadoPrograma(0, SALIDA_EJEMPLO.read_bytes(), b"", False)

	ps = motor.MotorPowershell(zc.carpeta / "recursos" / "ocr.ps1", ejecutar)
	resultado = ps.reconocer(str(tmp_path / "a.png"), "es-ES")
	assert resultado.paginas == [["Hola mundo prueba"]]
	argumentos = llamadas[0]
	assert argumentos[0].lower().endswith("powershell.exe")
	assert argumentos[1:6] == ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"]
	assert argumentos[argumentos.index("-Idioma") + 1] == "es-ES"
	assert (zc.carpeta / "recursos" / "ocr.ps1").is_file()


def test_elegir_usa_powershell_si_pywinrt_falla(motor, tmp_path, monkeypatch):
	monkeypatch.setattr(motor, "MotorWinrt", lambda: (_ for _ in ()).throw(ImportError("sin winrt")))
	falso = MotorFalso(motor)
	assert motor.elegir("automatico", tmp_path, lambda: falso) is falso
	assert falso.llamadas and not list(tmp_path.glob("*.bmp"))


def test_bmp_desde_dib(zc):
	captura = p2_comun.modulo(zc, "servicios.captura")
	motor = p2_comun.modulo(zc, "servicios.motor")
	bmp = motor.bmp_un_pixel()
	assert captura.bmp_desde_dib(bmp[14:]) == bmp


def test_la_funcion_exportada_tiene_la_firma_de_la_tabla(zc):
	from app.plugins import registro

	parametros = list(inspect.signature(registro.exportados("zc.ocr")["reconocer"]).parameters)
	assert parametros[:3] == ["proveedor", "ruta", "cancelacion"]


def test_el_dialogo_de_idioma_pasa_revisar_teclado(zc, interfaz):
	ventanas = zc.instancia.ventanas_para_revisar(None)
	assert ventanas
	dialogo = ventanas[0]
	try:
		p2_comun.revisar(dialogo)
		dialogo.poner_idiomas([("es-ES", "Español (España)"), ("en-US", "Inglés")])
		dialogo.idioma.SetSelection(2)
		assert dialogo.elegido() == "en-US"
	finally:
		dialogo.Destroy()


def _imagen_con_texto(ruta: Path) -> None:
	import wx

	mapa = wx.Bitmap(700, 140)
	dc = wx.MemoryDC(mapa)
	dc.SetBackground(wx.WHITE_BRUSH)
	dc.Clear()
	dc.SetTextForeground(wx.BLACK)
	dc.SetFont(wx.Font(36, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
	dc.DrawText("Hola mundo prueba", 20, 40)
	del dc
	mapa.SaveFile(str(ruta), wx.BITMAP_TYPE_PNG)


@pytest.mark.interfaz
@pytest.mark.parametrize("nombre_motor", ["winrt", "powershell"])
def test_real_con_el_ocr_de_windows(zc, motor, app_wx, tmp_path, nombre_motor):
	imagen = tmp_path / "texto.png"
	_imagen_con_texto(imagen)
	elegido = motor.MotorWinrt() if nombre_motor == "winrt" else zc.instancia._crear_powershell()
	try:
		idiomas = elegido.idiomas()
	except motor.ErrorOCR as error:
		pytest.skip(f"Sin OCR de Windows: {error.mensaje}")
	if not idiomas:
		pytest.skip("Windows no tiene idiomas de OCR instalados")
	resultado = elegido.reconocer(str(imagen))
	texto = " ".join(" ".join(p) for p in resultado.paginas).lower()
	assert "hola" in texto and "mundo" in texto
