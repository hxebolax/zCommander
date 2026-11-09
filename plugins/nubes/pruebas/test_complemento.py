# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas rápidas del complemento Nubes con ``api.pruebas`` (las ejecuta ``tools/validar_plugin.py``).

Sin red ni rclone: activación, manejadores reales, catálogo y traductor de
errores. Las pruebas con rclone real están en ``tests/plugins/nu/``.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app.plugins import api
from app.plugins.api import pruebas

CARPETA = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _datos_temporales(tmp_path, monkeypatch):
	"""Nunca el ``data`` real: lanzadas sueltas (sin ``tests/conftest.py``), estas pruebas escribirían configuración."""
	monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))


def _activado() -> pruebas.AnfitrionFalso:
	zc = pruebas.anfitrion_de_prueba(CARPETA)
	zc.activar()
	return zc


def test_activa_sin_arrancar_rclone_y_cada_orden_tiene_manejador():
	zc = _activado()
	assert zc.instancia.nubes.motor.vivo() is False
	contexto = pruebas.contexto_de_prueba()
	zc.ejecutar("espacio", contexto)
	assert any("No hay cuentas de nube" in texto for texto, _nivel in zc.anuncios)


def test_catalogo_y_errores():
	zc = _activado()
	assert zc.instancia.nubes.catalogo.servicio("drive") is not None
	errores = importlib.import_module("zcplugins.zc__nubes.errores")
	assert isinstance(errores.traducir(errores.ErrorRC(404, "object not found"), "a.txt"), api.NoEncontrado)
