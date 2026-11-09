# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas del registro básico: archivo de sesión, ganchos y fallo de arranque."""

from __future__ import annotations

import logging
import sys
import threading

import pytest

from app.core import registro


@pytest.fixture
def carpeta_logs(tmp_path):
	excepthook, threadhook = sys.excepthook, threading.excepthook
	nivel = logging.getLogger().level
	carpeta = tmp_path / "logs"
	yield carpeta
	registro.establecer_aviso_usuario(None)
	registro.detener_registro()
	sys.excepthook, threading.excepthook = excepthook, threadhook
	logging.getLogger().setLevel(nivel)


def _texto(carpeta):
	for manejador in logging.getLogger().handlers:
		manejador.flush()
	return "\n".join(p.read_text(encoding="utf-8") for p in sorted(carpeta.glob("sesion_*.log")))


def test_crea_sesion_con_cabecera(carpeta_logs):
	archivo = registro.configurar_registro("Prueba", "9.9.9", carpeta=carpeta_logs)
	assert archivo.is_file()
	logging.getLogger("app.prueba").info("Mensaje con %s", "formato diferido")
	texto = _texto(carpeta_logs)
	assert "Prueba 9.9.9" in texto
	assert "Mensaje con formato diferido" in texto
	assert "test_registro.py" in texto, "cada línea indica archivo, línea y función"
	assert (carpeta_logs / "fallo_nativo.log").exists()


def test_excepcion_no_controlada_se_registra_y_avisa(carpeta_logs):
	avisos = []
	registro.configurar_registro("Prueba", "1.0", carpeta=carpeta_logs)
	registro.establecer_aviso_usuario(avisos.append)
	try:
		{}["clave"]
	except KeyError:
		sys.excepthook(*sys.exc_info())
	texto = _texto(carpeta_logs)
	assert "Excepción no controlada" in texto
	assert "KeyError" in texto and "Traceback" in texto
	assert avisos and "KeyError" in avisos[0]


def test_excepcion_en_hilo_se_registra(carpeta_logs):
	registro.configurar_registro("Prueba", "1.0", carpeta=carpeta_logs)

	def falla():
		raise ValueError("fallo en hilo")

	hilo = threading.Thread(target=falla, name="hilo-de-prueba")
	hilo.start()
	hilo.join()
	texto = _texto(carpeta_logs)
	assert "hilo-de-prueba" in texto
	assert "fallo en hilo" in texto


def test_salida_estandar_ausente_va_al_registro(carpeta_logs, monkeypatch):
	monkeypatch.setattr(sys, "stdout", None)
	registro.configurar_registro("Prueba", "1.0", carpeta=carpeta_logs)
	print("texto impreso sin consola")
	assert "texto impreso sin consola" in _texto(carpeta_logs)
	registro.detener_registro()
	assert sys.stdout is None


def test_conserva_solo_las_ultimas_sesiones(carpeta_logs):
	carpeta_logs.mkdir(parents=True)
	for numero in range(15):
		(carpeta_logs / f"sesion_20000101_0000{numero:02d}.log").write_text("x", encoding="utf-8")
	registro.configurar_registro("Prueba", "1.0", carpeta=carpeta_logs)
	assert len(list(carpeta_logs.glob("sesion_*.log"))) == registro.SESIONES_A_CONSERVAR


def test_detener_restaura_los_ganchos(carpeta_logs):
	original = sys.excepthook
	registro.configurar_registro("Prueba", "1.0", carpeta=carpeta_logs)
	assert sys.excepthook is not original
	registro.detener_registro()
	assert sys.excepthook is original


def test_registrar_fallo_de_arranque(datos_temporales):
	try:
		raise RuntimeError("no arranca")
	except RuntimeError as error:
		ruta = registro.registrar_fallo_de_arranque(error)
	assert ruta == datos_temporales / "logs" / "arranque_fallido.log"
	texto = ruta.read_text(encoding="utf-8")
	assert "RuntimeError: no arranca" in texto
	assert "Fallo de arranque" in texto


def test_ocultar_secretos_en_direcciones_y_claves():
	from app.core.registro import ocultar_secretos

	assert ocultar_secretos("Conectando a ftp://ana:s3cr3t@servidor/dir") == "Conectando a ftp://ana:***@servidor/dir"
	assert ocultar_secretos('login password="abc def" ok') == "login password=*** ok"
	assert ocultar_secretos("contraseña: hola123") == "contraseña: ***"
	assert ocultar_secretos("sftp://servidor:22/ruta") == "sftp://servidor:22/ruta"


def test_al_cerrar_bien_se_quitan_solo_las_excepciones_com_controladas(tmp_path):
	"""0x8001010d (el lector consulta la ventana con un diálogo modal) no es un fallo: se quita al cerrar bien."""
	from app.core.registro import descartar_avisos_com_controlados

	ruta = tmp_path / "fallo_nativo.log"
	previo = "de una sesión anterior\n"
	ruta.write_text(previo + "Windows fatal exception: code 0x8001010d\n\nThread 0x1 (most recent call first):\n", encoding="utf-8")
	assert descartar_avisos_com_controlados(ruta, len(previo.encode("utf-8"))) == 1
	assert ruta.read_text(encoding="utf-8") == previo


def test_un_fallo_real_se_conserva(tmp_path):
	from app.core.registro import descartar_avisos_com_controlados

	ruta = tmp_path / "fallo_nativo.log"
	texto = "Windows fatal exception: code 0x8001010d\n...\nWindows fatal exception: access violation\n"
	ruta.write_text(texto, encoding="utf-8")
	assert descartar_avisos_com_controlados(ruta, 0) == 0
	assert ruta.read_text(encoding="utf-8") == texto
