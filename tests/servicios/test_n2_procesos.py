# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Procesos hijos con Job Objects (diseño 2.0, 14.9 y 18.2)."""

from __future__ import annotations

import logging
import subprocess
import sys
import time

import pytest

from app.core import procesos

PYTHON = sys.executable
CREA_NIETO = (
	"import subprocess, sys, time\n"
	"subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
	"time.sleep(60)\n"
)


def _vivo(pid: int) -> bool:
	import ctypes

	manejador = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)
	if not manejador:
		return False
	try:
		return ctypes.windll.kernel32.WaitForSingleObject(manejador, 0) == 0x102  # WAIT_TIMEOUT: sigue vivo
	finally:
		ctypes.windll.kernel32.CloseHandle(manejador)


def _esperar(condicion, segundos: float = 10) -> bool:
	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		if condicion():
			return True
		time.sleep(0.05)
	return condicion()


@pytest.fixture
def gestor():
	nuevo = procesos.GestorProcesos()
	yield nuevo
	nuevo.cerrar()


def test_lanzar_devuelve_la_salida(gestor):
	resultado = gestor.lanzar([PYTHON, "-c", "import sys; print(sys.stdin.read().upper())"], entrada=b"hola", tiempo_s=30)
	assert resultado.codigo == 0 and not resultado.cancelado
	assert resultado.salida.strip() == b"HOLA"


def test_el_nieto_esta_en_el_job_y_agotar_el_tiempo_termina_el_arbol(gestor):
	nombre = PYTHON.rsplit("\\", 1)[-1]
	pids_vistos: list[list[int]] = []

	def mirar(_bloque: bytes) -> None:
		return None

	import threading

	def vigilar() -> None:
		_esperar(lambda: len(gestor.hijos_vivos(nombre)) >= 2, 20)
		pids_vistos.append(gestor.hijos_vivos(nombre))

	hilo = threading.Thread(target=vigilar)
	hilo.start()
	resultado = gestor.lanzar([PYTHON, "-c", CREA_NIETO], tiempo_s=4, al_leer=mirar)
	hilo.join()
	assert resultado.cancelado
	assert len(pids_vistos[0]) >= 2, "el hijo y el nieto están en el Job"
	assert _esperar(lambda: not any(_vivo(p) for p in pids_vistos[0])), "el nieto también muere"


def test_cancelar_termina_el_arbol(gestor):
	import threading

	cancelar = threading.Event()
	threading.Timer(1.5, cancelar.set).start()
	inicio = time.monotonic()
	resultado = gestor.lanzar([PYTHON, "-c", CREA_NIETO], tiempo_s=60, cancelacion=cancelar)
	assert resultado.cancelado and time.monotonic() - inicio < 20


def test_si_la_asignacion_falla_se_termina_y_se_lanza_error(gestor, monkeypatch):
	creados: list[subprocess.Popen] = []
	original = subprocess.Popen

	def popen(*args, **kwargs):
		proceso = original(*args, **kwargs)
		creados.append(proceso)
		return proceso

	monkeypatch.setattr(procesos.subprocess, "Popen", popen)

	def falla(*_args):
		raise OSError("asignación simulada que falla")

	monkeypatch.setattr(procesos.win32job, "AssignProcessToJobObject", falla)
	with pytest.raises(procesos.ErrorProceso, match="No se pudo controlar"):
		gestor.popen([PYTHON, "-c", "import time; time.sleep(30)"])
	assert creados and creados[0].wait(10) is not None, "el proceso suspendido no queda vivo"


def test_lanzar_independiente_sobrevive_al_cierre_del_job(gestor):
	dentro = gestor.popen([PYTHON, "-c", "import time; time.sleep(60)"])
	pid_fuera = procesos.lanzar_independiente([PYTHON, "-c", "import time; time.sleep(20)"])
	try:
		assert _vivo(pid_fuera)
		gestor.cerrar()
		assert _esperar(lambda: dentro.poll() is not None), "lo del Job muere al cerrarlo"
		assert _vivo(pid_fuera), "lo lanzado aparte sobrevive"
	finally:
		subprocess.run(["taskkill", "/F", "/PID", str(pid_fuera)], capture_output=True)


def test_sin_poder_salir_del_job_lanza_sin_breakaway_y_lo_registra(monkeypatch, caplog):
	banderas = []

	class _Popen:
		pid = 99

		def __init__(self, argumentos, cwd=None, creationflags=0, close_fds=True):
			banderas.append(creationflags)

	monkeypatch.setattr(procesos, "esta_en_un_job", lambda: True)
	monkeypatch.setattr(procesos, "puede_salir_del_job", lambda: False)
	monkeypatch.setattr(procesos.subprocess, "Popen", _Popen)
	with caplog.at_level(logging.WARNING):
		assert procesos.lanzar_independiente(["C:\\x.exe"]) == 99
	assert not banderas[0] & procesos.CREATE_BREAKAWAY_FROM_JOB
	assert "no deja salir" in caplog.text
	monkeypatch.setattr(procesos, "puede_salir_del_job", lambda: True)
	procesos.lanzar_independiente(["C:\\x.exe"])
	assert banderas[1] & procesos.CREATE_BREAKAWAY_FROM_JOB


def test_ruta_relativa_y_shell_se_rechazan(gestor):
	with pytest.raises(procesos.ErrorProceso):
		gestor.lanzar(["python", "-c", "1"])
	with pytest.raises(procesos.ErrorProceso):
		gestor.popen([PYTHON], shell=True)
