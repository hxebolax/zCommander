# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas del arranque completo: main.py en otro proceso, sin mostrar ventanas."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from app.core.version import ID_APLICACION

from .conftest import RAIZ


def _ejecutar_main(datos, *argumentos, comprobar: bool = True):
	entorno = {**os.environ, "APP_DATA_DIR": str(datos)}
	previos = ["--comprobar-arranque"] if comprobar else []
	return subprocess.run(
		[sys.executable, str(RAIZ / "main.py"), *previos, *argumentos],
		capture_output=True,
		text=True,
		timeout=120,
		env=entorno,
		cwd=str(RAIZ),
	)


def test_arranque_completo_y_cierre(datos_temporales):
	"""2.0 (14.8, reescrita): ``--comprobar-arranque`` deja su registro mínimo en ``data/logs/prueba-*.log``
	y escribe todo lo demás en una carpeta temporal que borra al terminar (la ``data`` real queda limpia)."""
	resultado = _ejecutar_main(datos_temporales)
	assert resultado.returncode == 0, resultado.stderr
	pruebas = list((datos_temporales / "logs").glob("prueba-*.log"))
	assert len(pruebas) == 1
	texto = pruebas[0].read_text(encoding="utf-8")
	assert "Arranque completado" in texto
	assert "Cierre normal" in texto
	assert "ERROR" not in texto and "CRITICAL" not in texto
	assert not (datos_temporales / "config").exists(), "la configuración va a la carpeta temporal"
	assert not list((datos_temporales / "temp").glob("comprobar-arranque-*")), "la carpeta temporal se borra"


def test_segunda_instancia_pide_mostrar_y_sale(app_wx, datos_temporales):
	from app.core.instancia_unica import ORDEN_MOSTRAR, InstanciaUnica

	# Esta prueba hace de «primera instancia» con la misma carpeta data.
	primera = InstanciaUnica(ID_APLICACION)
	try:
		# 2.0 (14.8, reescrita): --comprobar-arranque ya no pasa por la instancia única; el arranque normal sí.
		resultado = _ejecutar_main(datos_temporales, comprobar=False)
		assert resultado.returncode == 0, resultado.stderr
		ordenes = primera.recoger_ordenes()
		assert [o.orden for o in ordenes] == [ORDEN_MOSTRAR]
		texto = "".join(p.read_text(encoding="utf-8") for p in (datos_temporales / "logs").glob("sesion_*.log"))
		assert "Ya hay otra instancia" in texto
		assert "Arranque completado" not in texto, "la segunda instancia no crea ventana"
	finally:
		primera.liberar()


def test_red_de_seguridad_del_arranque(monkeypatch, datos_temporales):
	import main

	carteles = []

	def falla(argumentos):
		raise RuntimeError("fallo simulado")

	monkeypatch.setattr(main, "_principal", falla)
	monkeypatch.setattr(main, "_mostrar_error_arranque", carteles.append)
	assert main.principal([]) == 1
	assert carteles and "RuntimeError: fallo simulado" in carteles[0]
	registro = datos_temporales / "logs" / "arranque_fallido.log"
	assert registro.is_file()
	assert "fallo simulado" in registro.read_text(encoding="utf-8")


def test_main_no_arranca_al_importarse():
	import main

	assert callable(main.principal)
	assert sys.getswitchinterval() == pytest.approx(0.001)
