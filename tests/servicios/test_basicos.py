# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de formato, selección, ordenación, rutas y proveedor local."""

from __future__ import annotations

import os

import pytest

from app.services import formato, ordenacion, seleccion
from app.services.vfs import base, rutas
from app.services.vfs.local import ProveedorLocal


def test_tamanos():
	assert formato.tamano_legible(0) == "0 bytes"
	assert formato.tamano_legible(1) == "1 byte"
	assert formato.tamano_legible(1536) == "1,5 KB"
	assert formato.tamano_legible(1024 * 1024 * 12.25) == "12,2 MB" or formato.tamano_legible(1024 * 1024 * 12.25) == "12,3 MB"
	assert formato.tamano(1234567, "bytes") == "1.234.567"
	assert formato.miles(1234) == "1234"


def test_recuento_y_duracion():
	assert formato.recuento(0, 0) == "Vacía"
	assert formato.recuento(1, 2) == "1 carpeta y 2 archivos"
	assert formato.duracion(80) == "1 min 20 s"
	assert formato.atributos_cortos(formato.OCULTO | formato.ARCHIVO) == "-H-A"


@pytest.mark.parametrize(("nombre", "patron", "esperado"), [
	("a.txt", "*.txt", True),
	("A.TXT", "*.txt", True),
	("leeme", "*.*", True),
	("leeme", "leeme.*", True),
	("a.bak", "*.* | *.bak", False),
	("a.md", "*.txt;*.md", True),
	("b.py", "*.txt *.md", False),
	("x1.log", "x?.log", True),
])
def test_patrones(nombre, patron, esperado):
	assert seleccion.coincide(nombre, patron) is esperado


def test_contiene_sin_acentos():
	assert seleccion.contiene("Canción.mp3", "cancion")
	assert not seleccion.contiene("Año.txt", "ano")


def test_orden_natural_y_carpetas_primero():
	e = [
		base.Entrada("b10.txt", "b10.txt", tamano=5),
		base.Entrada("b2.txt", "b2.txt", tamano=50),
		base.Entrada("zeta", "zeta", es_carpeta=True),
		base.entrada_superior("x"),
	]
	nombres = [x.nombre for x in ordenacion.ordenar(e)]
	assert nombres == ["..", "zeta", "b2.txt", "b10.txt"]
	nombres = [x.nombre for x in ordenacion.ordenar(e, ordenacion.TAMANO, inverso=True)]
	assert nombres == ["..", "zeta", "b2.txt", "b10.txt"]


@pytest.mark.parametrize("nombre", ["CON", "nul.txt", "a<b", "fin.", "fin ", "", "COM1.log"])
def test_nombres_no_validos(nombre):
	assert rutas.problema_en_nombre(nombre)


def test_rutas():
	assert rutas.padre("C:\\") is None
	assert rutas.padre("C:\\a\\b") == "C:\\a"
	assert rutas.padre("\\\\srv\\rec") == "\\\\srv"
	assert rutas.es_raiz("c:")
	assert rutas.esta_dentro("C:\\a\\b", "c:\\A")
	assert not rutas.esta_dentro("C:\\ab", "C:\\a")
	larga = "C:\\" + "\\".join(["carpeta"] * 40)
	assert rutas.con_prefijo_largo(larga).startswith("\\\\?\\")


def test_proveedor_local(tmp_path):
	p = ProveedorLocal()
	(tmp_path / "a.txt").write_text("hola", encoding="utf-8")
	(tmp_path / "sub").mkdir()
	entradas = {e.nombre: e for e in p.listar(str(tmp_path))}
	assert entradas["a.txt"].tamano == 4 and not entradas["a.txt"].es_carpeta
	assert entradas["sub"].es_carpeta and entradas["sub"].tamano == -1
	p.renombrar(str(tmp_path / "a.txt"), str(tmp_path / "A.TXT"))
	assert "A.TXT" in os.listdir(tmp_path)
	with pytest.raises(base.YaExiste):
		p.crear_carpeta(str(tmp_path / "sub"))
	(tmp_path / "sub" / "x").write_text("1")
	p.eliminar(str(tmp_path / "sub"), recursivo=True)
	assert not (tmp_path / "sub").exists()
	with pytest.raises(base.NoEncontrado):
		p.listar(str(tmp_path / "noexiste"))


def test_atributos(tmp_path):
	from app.services.windows import atributos

	f = tmp_path / "o.txt"
	f.write_text("x")
	atributos.cambiar_atributos(str(f), poner=formato.OCULTO | formato.SOLO_LECTURA)
	assert ProveedorLocal().info(str(f)).oculto
	ProveedorLocal().eliminar(str(f))
	assert not f.exists()
