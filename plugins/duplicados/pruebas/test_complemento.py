# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Prueba rápida del complemento con ``api.pruebas`` (la ejecuta ``tools/validar_plugin.py``).

Las pruebas completas del bloque P3 están en ``tests/plugins/duplicados/`` de zCommander.
"""

from __future__ import annotations

from pathlib import Path

from app.plugins.api import pruebas

CARPETA = Path(__file__).resolve().parents[1]


def test_se_activa():
	zc = pruebas.anfitrion_de_prueba(CARPETA)
	zc.activar()
	assert zc.instancia is not None
