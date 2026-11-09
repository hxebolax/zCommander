# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""La voz arranca sin las DLL no libres de accessible_output2 (diseño 2.0, 2.3 y 18.2)."""

from __future__ import annotations

import ast
import sys
import types

from app.ui.accesibilidad import voz

from ..conftest import RAIZ


def test_voz_no_usa_auto():
	arbol = ast.parse((RAIZ / "app" / "ui" / "accesibilidad" / "voz.py").read_text(encoding="utf-8"))
	modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
	assert "accessible_output2.outputs.auto" not in modulos
	assert voz.SALIDAS_AO2 == ("nvda", "jaws", "sapi5")


def test_arranca_sin_las_dll_no_libres(monkeypatch):
	"""Simula una compilación sin SAAPI32, dolapi, PCTKUSR ni ZDSRAPI: importar esos módulos falla."""
	for nombre in ("system_access", "dolphin", "pc_talker", "zdsr", "auto"):
		monkeypatch.setitem(sys.modules, f"accessible_output2.outputs.{nombre}", None)
	falsos = {}
	for nombre, clase in (("nvda", "NVDA"), ("jaws", "Jaws"), ("sapi5", "SAPI5")):
		modulo = types.ModuleType(f"accessible_output2.outputs.{nombre}")
		setattr(modulo, clase, type(clase, (), {"speak": lambda self, texto, interrupt=False: None}))
		falsos[nombre] = modulo
		monkeypatch.setitem(sys.modules, f"accessible_output2.outputs.{nombre}", modulo)
	monkeypatch.setattr(voz, "_salidas", {})
	for nombre in ("nvda", "jaws", "sapi5"):
		assert voz._salida_ao2(nombre) is not None
	assert voz._salida_ao2("otro") is None
