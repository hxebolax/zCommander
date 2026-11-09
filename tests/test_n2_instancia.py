# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Instancia única en la 2.0: orden «tarea», espera de entrega y ``--tarea`` (diseño 2.0, 14.8 y 18.2)."""

from __future__ import annotations

import threading
import time

import pytest

from app.core import instancia_unica


def test_tarea_es_valida_y_caduca_a_los_600_s(tmp_path):
	assert instancia_unica.ORDEN_TAREA in instancia_unica.ORDENES_VALIDAS
	assert instancia_unica.dejar_orden("tarea", ["copia_noche"], tmp_path)
	ordenes = instancia_unica.recoger_ordenes(tmp_path, ahora=time.time() + 300)
	assert [(o.orden, o.argumentos) for o in ordenes] == [("tarea", ["copia_noche"])]
	instancia_unica.dejar_orden("tarea", ["x"], tmp_path)
	instancia_unica.dejar_orden("mostrar", [], tmp_path)
	quedan = instancia_unica.recoger_ordenes(tmp_path, ahora=time.time() + 300)
	assert [o.orden for o in quedan] == ["tarea"], "a los 300 s la tarea sigue valiendo y mostrar ha caducado"
	instancia_unica.dejar_orden("tarea", ["y"], tmp_path)
	assert instancia_unica.recoger_ordenes(tmp_path, ahora=time.time() + instancia_unica.MAX_EDAD_TAREA + 1) == []


def test_dejar_orden_esperando_vuelve_cuando_la_recogen(tmp_path):
	hilo = threading.Thread(target=lambda: (time.sleep(0.3), instancia_unica.recoger_ordenes(tmp_path)))
	hilo.start()
	assert instancia_unica.dejar_orden_esperando("tarea", ["a"], 5, tmp_path)
	hilo.join()


def test_dejar_orden_esperando_falso_si_se_agota(tmp_path):
	assert not instancia_unica.dejar_orden_esperando("tarea", ["a"], 0.3, tmp_path)
	assert instancia_unica.hay_ordenes_pendientes(tmp_path)


def test_hay_instancia_sin_wx(app_wx, datos_temporales):
	"""Precisión 1 de la ronda 4: ``OpenMutexW`` sobre el nombre del mutex, sin crear ninguno."""
	from app.core.version import ID_APLICACION

	assert not instancia_unica.hay_instancia(ID_APLICACION)
	primera = instancia_unica.InstanciaUnica(ID_APLICACION)
	try:
		assert instancia_unica.hay_instancia(ID_APLICACION)
	finally:
		primera.liberar()
	assert not instancia_unica.hay_instancia(ID_APLICACION)


class _InstanciaFalsa:
	def __init__(self) -> None:
		self.liberada = False

	def liberar(self) -> None:
		self.liberada = True


def test_tarea_sin_instancia_lanza_la_real_y_entrega(monkeypatch):
	import main
	from app.core import procesos

	lanzados = []
	monkeypatch.setattr(procesos, "puede_salir_del_job", lambda: True)
	monkeypatch.setattr(procesos, "lanzar_independiente", lambda argumentos, carpeta=None: lanzados.append(argumentos) or 4321)
	monkeypatch.setattr(instancia_unica, "hay_instancia", lambda *_a, **_k: bool(lanzados))
	entregas = []
	monkeypatch.setattr(instancia_unica, "dejar_orden_esperando", lambda o, a, t: entregas.append((o, a, t)) or True)
	instancia = _InstanciaFalsa()
	assert main._tarea_sin_instancia(instancia, "copia") == 0
	assert instancia.liberada
	assert lanzados and lanzados[0][-1] == "--modo-tarea"
	assert entregas == [("tarea", ["copia"], main.ESPERA_ORDEN_TAREA_S)]


def test_tarea_sin_poder_salir_del_job_se_queda(monkeypatch):
	import main
	from app.core import procesos

	monkeypatch.setattr(procesos, "puede_salir_del_job", lambda: False)
	assert main._tarea_sin_instancia(_InstanciaFalsa(), "copia") is None


@pytest.mark.parametrize("argumentos", [["--tarea", "copia"], ["--tarea=copia"]])
def test_tarea_no_es_un_archivo(argumentos):
	import main

	opciones = main.analizar_argumentos([*argumentos, "C:\\x"])
	assert opciones.tarea == "copia"
	assert opciones.archivos == ["C:\\x"]


def test_tarea_con_otra_instancia_deja_la_orden_y_sale(app_wx, datos_temporales):
	import subprocess
	import sys

	from app.core.version import ID_APLICACION

	from .conftest import RAIZ

	primera = instancia_unica.InstanciaUnica(ID_APLICACION)
	try:
		import os

		resultado = subprocess.run([sys.executable, str(RAIZ / "main.py"), "--tarea", "copia_noche"], capture_output=True,
			text=True, timeout=120, env={**os.environ, "APP_DATA_DIR": str(datos_temporales)}, cwd=str(RAIZ))
		assert resultado.returncode == 0, resultado.stderr
		ordenes = primera.recoger_ordenes()
		assert [(o.orden, o.argumentos) for o in ordenes] == [("tarea", ["copia_noche"])]
	finally:
		primera.liberar()
