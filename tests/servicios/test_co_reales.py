# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Componentes reales de ``data/bin`` (diseño 2.0, 6.2 y 18.2): fichas definitivas y pruebas con los binarios (marca ``componentes``).

Solo leen ``data/bin``: nunca lo cambian. Las que necesitan un binario se
saltan si no está.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.componentes import fichas, prueba

RAIZ = Path(__file__).resolve().parents[2]
BIN = RAIZ / "data" / "bin"


def _ficha(id: str) -> dict:
	return fichas.buscar(fichas.leer(BIN / "componentes.json"), id)


def test_fichas_definitivas_validas_y_al_dia():
	base = fichas.leer(BIN / "linea_base.json")
	instalados = fichas.leer(BIN / "componentes.json")
	assert fichas.validar(base, linea_base=True) == []
	assert fichas.validar(instalados, linea_base=False) == []
	assert "provisional" not in base
	assert {f["id"] for f in base["componentes"]} == {"rclone", "libarchive", "7za", "ffmpeg", "nvda"}
	from tools import preparar_componentes

	assert preparar_componentes.main(["--comprobar"]) == 0, "linea_base.json tiene las sumas de lo instalado hoy"
	assert instalados == preparar_componentes.instalados_desde(base)
	for ficha in base["componentes"]:
		if ficha.get("actualizable", True):
			assert ficha["archivos"] and ficha["sha256_paquete"] and ficha["url_paquete_exacta"].startswith("https://")
	assert len(fichas.buscar(base, "libarchive")["paquetes_exactos"]) == 8


@pytest.mark.componentes
@pytest.mark.parametrize("id", ["rclone", "7za", "ffmpeg"])
def test_prueba_de_la_ficha_con_el_binario_real(id):
	ficha = _ficha(id)
	if not (BIN / ficha["carpeta"] / ficha["prueba"]["ejecutable"]).is_file():
		pytest.skip(f"Falta el binario de {id}")
	resultado = prueba.probar_ficha(ficha, BIN / ficha["carpeta"], definitiva=True)
	assert resultado.correcta, resultado.detalle
	if id == "ffmpeg":
		assert resultado.version == ficha["version"], "version_desde programa: la versión sale de «ffmpeg -version»"


@pytest.mark.componentes
def test_probar_componente_libarchive_con_otra_instancia_abierta(tmp_path, app_wx):
	if not (BIN / "libarchive" / "libarchive-13.dll").is_file():
		pytest.skip("Falta libarchive")
	from app.services.libarchive import prueba as prueba_libarchive

	if "PROVISIONAL" in (prueba_libarchive.__doc__ or ""):
		pytest.skip("La prueba de libarchive es aún la provisional de N2 (bloque CM)")
	from app.core.instancia_unica import InstanciaUnica
	from app.core.version import ID_APLICACION

	datos = Path(os.environ["APP_DATA_DIR"])
	(datos / "bin").mkdir(parents=True, exist_ok=True)
	shutil.copytree(BIN / "libarchive", datos / "bin" / "libarchive")
	for nombre in ("componentes.json", "linea_base.json"):
		shutil.copy2(BIN / nombre, datos / "bin" / nombre)
	instancia = InstanciaUnica(ID_APLICACION)
	try:
		entorno = dict(os.environ, APP_DATA_DIR=str(datos))
		orden = [sys.executable, str(RAIZ / "main.py"), "--probar-componente", "libarchive"]
		resultado = subprocess.run(orden, cwd=RAIZ, env=entorno, capture_output=True, timeout=120,
			creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
		assert resultado.returncode == 0, resultado.stderr.decode("utf-8", "replace")[-2000:]
		otra = subprocess.run([*orden, "--carpeta", str(datos / "bin" / "libarchive")], cwd=RAIZ, env=entorno, capture_output=True,
			timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
		assert otra.returncode == 0
	finally:
		instancia.liberar()


def test_probar_componente_sin_ficha_devuelve_1():
	assert prueba.probar_componente("no_existe", None) == 1


def test_version_en_salida():
	assert prueba.version_en_salida("ffmpeg version n9.0.2-48-gd4070a14ce-20261108 Copyright") == "9.0.2"
	assert prueba.version_en_salida("rclone v1.76.0\n- os/version") == "1.76.0"
	assert prueba.version_en_salida("7-Zip (a) 26.06 (x64) : Copyright") == "26.06"
