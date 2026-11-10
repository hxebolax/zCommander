# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""tools/dependencias_pe.py y la python3t.dll compatible (fallo de cryptography de la 2.0.0 y la 2.0.1)."""

from __future__ import annotations

import shutil
import sys
import sysconfig
from pathlib import Path

import pytest

from tools import dependencias_pe as dpe

BASE = Path(sys.base_prefix)
COMPATIBLE = BASE / "abi3t-compat" / "python3t.dll"
SIN_GIL = BASE / "python3t.dll"
VERSION_DLL = f"python{sys.version_info.major}{sys.version_info.minor}"

necesita_las_dos = pytest.mark.skipif(not (COMPATIBLE.is_file() and SIN_GIL.is_file()),
	reason="Este Python no trae las dos python3t.dll")


def test_lee_importaciones_de_un_ejecutable_real():
	info = dpe.leer_pe(Path(sys.executable))
	assert any(n.lower().startswith("python") or n.lower() == "kernel32.dll" for n in info.importa)


def test_lee_los_reenvios_de_python3_dll():
	info = dpe.leer_pe(BASE / "python3.dll")
	assert [n.lower() for n in info.reenvia_a] == [f"{VERSION_DLL}.dll"]


@necesita_las_dos
def test_las_dos_python3t_reenvian_a_interpretes_distintos():
	assert [n.lower() for n in dpe.leer_pe(SIN_GIL).reenvia_a] == [f"{VERSION_DLL}t.dll"]
	assert [n.lower() for n in dpe.leer_pe(COMPATIBLE).reenvia_a] == [f"{VERSION_DLL}.dll"]


def test_no_es_pe(tmp_path):
	falso = tmp_path / "falso.dll"
	falso.write_bytes(b"no soy un ejecutable")
	with pytest.raises(dpe.ErrorPE):
		dpe.leer_pe(falso)


@necesita_las_dos
def test_detecta_la_python3t_equivocada(tmp_path):
	"""Lo que pasaba en la 2.0.1: python3t.dll reenvía a python315t.dll, que no va en la compilación."""
	carpeta = tmp_path / "ZCommander"
	carpeta.mkdir()
	shutil.copy2(BASE / f"{VERSION_DLL}.dll", carpeta)
	shutil.copy2(SIN_GIL, carpeta / "python3t.dll")
	def de_python3t() -> list[str]:
		return [p for p in dpe.problemas(carpeta) if p.startswith("python3t.dll")]

	assert de_python3t() == [f"python3t.dll reenvía a {VERSION_DLL}t.dll, que no va en la compilación"]
	shutil.copy2(COMPATIBLE, carpeta / "python3t.dll")
	assert de_python3t() == []


def test_las_dll_de_python_no_valen_del_sistema(tmp_path):
	"""Aunque python315.dll estuviera en System32 de este equipo, tiene que ir en la compilación."""
	carpeta = tmp_path / "ZCommander"
	carpeta.mkdir()
	shutil.copy2(BASE / "python3.dll", carpeta)
	sistema = tmp_path / "System32"
	sistema.mkdir()
	(sistema / f"{VERSION_DLL}.dll").write_bytes(b"MZ")
	assert dpe.problemas(carpeta, sistema=sistema) == [f"python3.dll reenvía a {VERSION_DLL}.dll, que no va en la compilación"]


def test_entorno_limpio_quita_python_del_path():
	entorno = dpe.entorno_limpio({"SystemRoot": r"C:\Windows", "PYTHONPATH": "x",
		"PATH": r"C:\Python315;C:\Windows\system32;C:\Python315\Scripts;C:\Windows;C:\Windows\System32\Wbem"})
	assert entorno["PATH"].split(";") == [r"C:\Windows\system32", r"C:\Windows", r"C:\Windows\System32\Wbem"]
	assert "PYTHONPATH" not in entorno


@pytest.mark.skipif(bool(sysconfig.get_config_var("Py_GIL_DISABLED")), reason="Con un Python sin GIL vale la de la raíz")
def test_setup_pone_la_python3t_compatible(tmp_path):
	import setup_cx

	if not COMPATIBLE.is_file():
		assert setup_cx.python3t_compatible() is None
		return
	(tmp_path / "python3t.dll").write_bytes(b"equivocada")
	assert setup_cx.poner_python3t_compatible(tmp_path) is True
	assert (tmp_path / "python3t.dll").read_bytes() == COMPATIBLE.read_bytes()
	vacia = tmp_path / "sin"
	vacia.mkdir()
	assert setup_cx.poner_python3t_compatible(vacia) is False  # si no hay python3t.dll, no se añade
