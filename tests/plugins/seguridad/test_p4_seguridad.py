# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de ``zc.seguridad`` (diseño 2.0, 11.19 y 18.2). Sin red: VirusTotal y Defender con respuestas guardadas."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys

import pytest

from app.core import red
from app.plugins import api
from app.plugins.api import pruebas
from tests.plugins import p4_comun

NOTEPAD = r"C:\Windows\System32\notepad.exe"

# Ejemplos guardados de la salida de MpCmdRun.exe -Scan -ScanType 3 -File.
DEFENDER_LIMPIO = """Scan starting...
Scan finished.
Scanning C:\\Users\\ana\\Descargas\\setup.exe found no threats.
"""
DEFENDER_AMENAZA = """Scan starting...
Scan finished.
Scanning C:\\Users\\ana\\Descargas\\eicar.com found 1 threats.

<===========================LIST OF DETECTED THREATS==========================>
----------------------------- Threat information ------------------------------
Threat                  : Virus:DOS/EICAR_Test_File
Resources               : 1 total
    file                : C:\\Users\\ana\\Descargas\\eicar.com
-------------------------------------------------------------------------------
"""
DEFENDER_ERROR = """Scan starting...
CmdTool: Failed with hr = 0x80508023. Check C:\\Users\\ana\\AppData\\Local\\Temp\\MpCmdRun.log for more information
"""
VIRUSTOTAL = {"data": {"id": "x", "type": "file", "attributes": {
	"last_analysis_stats": {"malicious": 5, "suspicious": 1, "undetected": 60, "harmless": 0, "timeout": 0},
	"popular_threat_classification": {"suggested_threat_label": "trojan.agent"}, "names": ["setup.exe"]}}}


@pytest.fixture
def zc():
	return p4_comun.anfitrion("seguridad")


@pytest.fixture
def firma(zc):
	return p4_comun.modulo(zc, "firma")


@pytest.fixture
def comprobaciones(zc):
	return p4_comun.modulo(zc, "comprobaciones")


def test_notepad_tiene_firma_valida(firma):
	resultado = firma.verificar(NOTEPAD)
	assert resultado.estado == firma.VALIDA, resultado
	assert "firma válida" in resultado.texto and resultado.firmante


def test_un_ejecutable_firmado_y_modificado_no_es_valido(firma, tmp_path):
	candidatos = [getattr(sys, "_base_executable", sys.executable), r"C:\Windows\explorer.exe", NOTEPAD]
	firmado = next((c for c in candidatos if os.path.isfile(c) and firma.verificar(c).tipo == firma.INCRUSTADA
		and firma.verificar(c).estado == firma.VALIDA), None)
	if firmado is None:
		pytest.skip("No hay un ejecutable con firma incrustada en este equipo")
	copia = tmp_path / "copia.exe"
	shutil.copyfile(firmado, copia)
	datos = bytearray(copia.read_bytes())
	datos[len(datos) // 3] ^= 0xFF
	copia.write_bytes(bytes(datos))
	resultado = firma.verificar(str(copia))
	assert resultado.estado == firma.NO_VALIDA and resultado.texto.startswith("Firma no válida")
	sin_firma = tmp_path / "vacio.exe"
	sin_firma.write_bytes(b"MZ" + b"\0" * 200)
	assert firma.verificar(str(sin_firma)).texto == "Sin firma"


def test_orden_firma_suena_si_no_hay_firma(zc, tmp_path):
	sin_firma = tmp_path / "vacio.exe"
	sin_firma.write_bytes(b"MZ" + b"\0" * 200)
	zc.ejecutar("firma", pruebas.contexto_de_prueba(activo=p4_comun.panel([sin_firma])))
	p4_comun.esperar_tareas(zc)
	assert zc.anuncios[-1] == ("Sin firma", api.RESULTADO) and zc.sonidos_pedidos == ["zc.seguridad:sin_firma"]


def test_suma_del_portapapeles_en_mayusculas_minusculas_y_con_espacios(comprobaciones):
	suma = hashlib.sha256(b"x").hexdigest()
	espaciada = " ".join(suma[i:i + 4] for i in range(0, 64, 4)).upper()
	for texto in (suma, suma.upper(), espaciada, f"SHA256: {suma}", f"SHA-256 = {suma.upper()}", f"{suma}  setup.exe\n",
			f"  {suma}  "):
		assert comprobaciones.extraer_suma(texto) == ("sha256", suma), texto
	assert comprobaciones.extraer_suma(hashlib.md5(b"x").hexdigest().upper()) == ("md5", hashlib.md5(b"x").hexdigest())
	assert comprobaciones.extraer_suma("hola, esto no es una suma") is None


def test_comparar_suma_con_el_portapapeles(zc, tmp_path, monkeypatch):
	archivo = tmp_path / "setup.exe"
	archivo.write_bytes(b"contenido")
	suma = hashlib.sha256(b"contenido").hexdigest()
	zc.activar()
	monkeypatch.setattr(zc.instancia, "_texto_portapapeles", lambda: " ".join(suma[i:i + 8] for i in range(0, 64, 8)).upper())
	zc.ejecutar("comparar_suma", pruebas.contexto_de_prueba(activo=p4_comun.panel([archivo])))
	p4_comun.esperar_tareas(zc)
	assert zc.anuncios[-1] == ("Coincide con el SHA-256 del portapapeles", api.RESULTADO)
	monkeypatch.setattr(zc.instancia, "_texto_portapapeles", lambda: "0" * 64)
	zc.ejecutar("comparar_suma", pruebas.contexto_de_prueba(activo=p4_comun.panel([archivo])))
	p4_comun.esperar_tareas(zc)
	assert zc.anuncios[-1][0].startswith("No coincide con el SHA-256 del portapapeles") and "zc.seguridad:amenaza" in zc.sonidos_pedidos


def test_analizador_de_mpcmdrun_con_ejemplos_guardados(comprobaciones):
	limpio = comprobaciones.interpretar_defender(DEFENDER_LIMPIO, 0)
	assert limpio.analizado and not limpio.amenazas and limpio.texto == "Defender no encontró amenazas"
	amenaza = comprobaciones.interpretar_defender(DEFENDER_AMENAZA, 2)
	assert amenaza.amenazas == ("Virus:DOS/EICAR_Test_File",)
	assert amenaza.texto == "Defender encontró 1 amenaza: Virus:DOS/EICAR_Test_File"
	error = comprobaciones.interpretar_defender(DEFENDER_ERROR, 2147549183)
	assert error.error == "0x80508023" and error.texto.startswith("Defender no pudo analizarlo")
	argumentos = comprobaciones.argumentos_defender("C:\\MpCmdRun.exe", "C:\\x.exe")
	assert argumentos[1:] == ["-Scan", "-ScanType", "3", "-File", "C:\\x.exe", "-DisableRemediation"]


def test_defender_con_un_resultado_simulado(zc, monkeypatch, comprobaciones):
	zc.activar()
	monkeypatch.setattr(comprobaciones, "ruta_mpcmdrun", lambda: "C:\\MpCmdRun.exe")
	llamadas = []

	def ejecutar(argumentos, **opciones):
		llamadas.append(argumentos)
		return api.ResultadoPrograma(2, DEFENDER_AMENAZA.encode("mbcs"), b"", False)

	monkeypatch.setattr(zc, "ejecutar_programa", ejecutar)
	resultado = zc.instancia.analizar_con_defender(["C:\\x.exe"])
	zc.instancia._anunciar_defender(resultado)
	assert llamadas[0][-2] == "C:\\x.exe" and zc.sonidos_pedidos == ["zc.seguridad:amenaza"]
	assert zc.anuncios[-1][1] == api.ESENCIAL


def test_virustotal_solo_envia_el_hash(zc, comprobaciones, monkeypatch):
	zc.activar()
	pedidas = []

	def obtener(url, *, cabeceras=None, tiempo_s=30):
		pedidas.append((url, cabeceras))
		return red.RespuestaRed(200, {}, json.dumps(VIRUSTOTAL).encode(), url)

	monkeypatch.setattr(zc.red, "obtener", obtener)
	suma = hashlib.sha256(b"x").hexdigest()
	resultado = zc.instancia.consultar_virustotal(suma, "clave-inventada")
	assert pedidas == [(f"https://www.virustotal.com/api/v3/files/{suma}", {"x-apikey": "clave-inventada"})]
	assert resultado.amenaza and resultado.texto == ("VirusTotal: 5 de 66 antivirus lo detectan, 1 lo ve sospechoso, "
		"como trojan.agent")

	def no_encontrado(url, **_opciones):
		try:
			raise red.ErrorHTTP(red.HTTP, "No encontrado", 404)
		except red.ErrorHTTP as error:
			raise api.ErrorRed(error.mensaje, url) from error

	monkeypatch.setattr(zc.red, "obtener", no_encontrado)
	assert zc.instancia.consultar_virustotal(suma, "clave-inventada").texto.startswith("VirusTotal no conoce este archivo")
	with pytest.raises(ValueError):
		comprobaciones.url_virustotal("../otra-cosa")


def test_virustotal_sin_clave_no_se_conecta(zc, tmp_path, monkeypatch):
	archivo = tmp_path / "a.exe"
	archivo.write_bytes(b"x")
	zc.activar()
	monkeypatch.setattr(zc.red, "obtener", lambda *a, **k: pytest.fail("No debe conectarse"))
	monkeypatch.setattr(zc.secretos, "obtener", lambda nombre: None)
	interfaz = p4_comun.InterfazFalsa({"pedir_texto": [None]})
	api.fijar_interfaz(interfaz)
	try:
		zc.ejecutar("virustotal", pruebas.contexto_de_prueba(activo=p4_comun.panel([archivo])))
	finally:
		api.fijar_interfaz(None)
	assert [d[0] for d in interfaz.dialogos] == ["pedir_texto"]


def test_marca_de_la_web_se_lee_y_se_quita(zc, comprobaciones, tmp_path):
	archivo = tmp_path / "descarga.zip"
	archivo.write_bytes(b"PK")
	with open(str(archivo) + ":Zone.Identifier", "w", encoding="utf-8") as flujo:
		flujo.write("[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://ejemplo.org/descarga.zip\r\n")
	marca = comprobaciones.leer_marca(str(archivo))
	assert marca.texto == "Internet" and marca.descripcion == "Descargado de Internet: https://ejemplo.org/descarga.zip"
	zc.activar()
	assert zc.instancia.columna_marca(p4_comun.entrada(archivo), None, None) == "Internet"
	assert "Origen: Descargado de Internet: https://ejemplo.org/descarga.zip" in zc.instancia.lineas_info(p4_comun.entrada(archivo), None)
	api.fijar_interfaz(p4_comun.InterfazFalsa({"confirmar": [True]}))
	try:
		zc.ejecutar("quitar_marca", pruebas.contexto_de_prueba(activo=p4_comun.panel([archivo])))
	finally:
		api.fijar_interfaz(None)
	assert comprobaciones.leer_marca(str(archivo)) is None
	assert zc.anuncios[-1] == ("Marca quitada de 1 archivo", api.RESULTADO)


def test_informacion_y_columna_de_un_ejecutable(zc):
	zc.activar()
	entrada = p4_comun.entrada(NOTEPAD)
	assert zc.instancia.columna_firma(entrada, None, None) == "Microsoft Windows"
	lineas = zc.instancia.lineas_info(entrada, None)
	assert any(linea.startswith("Firma: Firmado por") for linea in lineas)
	assert any(linea.startswith("Empresa: Microsoft") for linea in lineas)
	assert "Arquitectura: x64 (64 bits)" in lineas


def test_solo_se_analiza_lo_que_viene_de_un_servidor(zc):
	zc.activar()

	class Proveedor:
		def __init__(self, esquema):
			self.esquema = esquema

	class Copia:
		origen, destino = Proveedor("sftp"), Proveedor("local")

		def pares_hechos(self):
			return [("/remoto/a.exe", "C:\\Descargas\\a.exe")]

	assert zc.instancia.rutas_descargadas(Copia()) == ["C:\\Descargas\\a.exe"]
	Copia.origen = Proveedor("local")
	assert zc.instancia.rutas_descargadas(Copia()) == []


def test_dialogo_de_la_clave_pasa_revisar_teclado(zc, app_wx):
	from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

	zc.activar()
	api.fijar_interfaz(p4_comun.InterfazFalsa())
	try:
		(dialogo,) = zc.instancia.ventanas_para_revisar(None)
		afirmar_teclado_correcto(dialogo)
		dialogo.Destroy()
	finally:
		api.fijar_interfaz(None)
