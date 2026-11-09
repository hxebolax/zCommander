# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Variables de órdenes: expansión y seguridad frente a inyección en cmd."""

from __future__ import annotations

import os
import subprocess

import pytest

from app.services import variables as v


@pytest.mark.parametrize("nombre", ["a&calc.txt", "100%PATH%.txt", "x^y (z).txt"])
def test_nombres_peligrosos_no_inyectan(tmp_path, nombre):
	ruta = tmp_path / nombre
	ruta.write_bytes(b"contenido seguro\r\n")
	expansion = v.expandir("type %P & echo [fin]", v.Valores(cursor=str(ruta), carpeta=str(tmp_path)))
	entorno = dict(os.environ)
	entorno.update(expansion.entorno)
	resultado = subprocess.run(
		v.linea_cmd(expansion.orden), env=entorno, capture_output=True, text=True, cwd=tmp_path, check=False,
	)
	salida = resultado.stdout.strip().splitlines()
	assert salida == ["contenido seguro", "[fin]"], resultado
	assert resultado.returncode == 0


def test_comillas_del_usuario_y_lista():
	expansion = v.expandir(
		'7z a "%O\\%N.7z" %M',
		v.Valores(cursor="C:\\x\\b.txt", otra_carpeta="D:\\", trabajo=["C:\\x\\b.txt", "C:\\x\\c d.txt"]),
	)
	assert expansion.orden == '7z a "%ZC_1%\\%ZC_2%.7z" "%ZC_3%" "%ZC_4%"'
	assert expansion.entorno["ZC_1"] == "D:\\."
	assert expansion.entorno["ZC_2"] == "b.txt"


def test_pedir_y_cancelar():
	e = v.expandir("echo %?Nombre?hola%", v.Valores(), pedir=lambda t, i: i + "!")
	assert e.entorno["ZC_1"] == "hola!"
	with pytest.raises(v.Cancelada):
		v.expandir("echo %?Nombre?%", v.Valores(), pedir=lambda t, i: None)


def test_expandir_directo():
	assert v.expandir_directo("notepad.exe %P", v.Valores(cursor="C:\\a b\\c.txt")) == 'notepad.exe "C:\\a b\\c.txt"'
	assert v.entrecomillar_argumento("C:\\a b\\") == '"C:\\a b\\\\"'


@pytest.mark.parametrize("plantilla", ['type "%P" & echo [fin]', "type %P & echo [fin]"])
@pytest.mark.parametrize("nombre", ["a&b!c!.txt", "x%PATH%y.txt"])
def test_comillas_propias_y_exclamaciones(tmp_path, plantilla, nombre):
	ruta = tmp_path / nombre
	ruta.write_bytes(b"ok\r\n")
	expansion = v.expandir(plantilla, v.Valores(cursor=str(ruta), carpeta=str(tmp_path)))
	entorno = dict(os.environ)
	entorno.update(expansion.entorno)
	resultado = subprocess.run(v.linea_cmd(expansion.orden), env=entorno, capture_output=True, text=True, cwd=tmp_path, check=False)
	assert resultado.stdout.split() == ["ok", "[fin]"], resultado


def test_palabra_compuesta_y_raiz(tmp_path):
	(tmp_path / "b.txt").write_bytes(b"hola\r\n")
	expansion = v.expandir(r"copy %P %O\%N.bak", v.Valores(cursor=str(tmp_path / "b.txt"), otra_carpeta=str(tmp_path)))
	assert expansion.orden == r'copy "%ZC_1%" "%ZC_2%\%ZC_3%.bak"'
	entorno = dict(os.environ)
	entorno.update(expansion.entorno)
	subprocess.run(v.linea_cmd(expansion.orden), env=entorno, capture_output=True, cwd=tmp_path, check=True)
	assert (tmp_path / "b.txt.bak").read_bytes() == b"hola\r\n"
	raiz = v.expandir("dir %D", v.Valores(carpeta="D:\\"))
	assert raiz.entorno["ZC_1"] == r"D:\."


def test_limite_y_m_pegada():
	with pytest.raises(v.DemasiadoLarga):
		v.expandir("echo %M", v.Valores(trabajo=["C:\\" + "x" * 200] * 60))
	with pytest.raises(ValueError):
		v.expandir("echo a%M", v.Valores(trabajo=["C:\a"]))


def test_directo_con_comillas_propias():
	r = v.expandir_directo('"C:\\Prog\\ed.exe" "%P"', v.Valores(cursor="C:\\a b\\c.txt"))
	assert r == '"C:\\Prog\\ed.exe" "C:\\a b\\c.txt"'
	r = v.expandir_directo('ver.exe "%D"', v.Valores(carpeta="C:\\x\\"))
	assert r == 'ver.exe "C:\\x"'


def test_variables_de_entorno_con_doble_porcentaje(tmp_path):
	e = v.expandir("echo %%OS%%", v.Valores())
	entorno = dict(os.environ)
	entorno.update(e.entorno)
	r = subprocess.run(v.linea_cmd(e.orden), env=entorno, capture_output=True, text=True, check=False)
	assert r.stdout.strip() == os.environ.get("OS", "Windows_NT")
	with pytest.raises(ValueError):
		v.expandir("echo %?Dato?%", v.Valores(), pedir=lambda t, i: 'a"b')
