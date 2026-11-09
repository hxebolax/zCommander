# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sumas de comprobación: algoritmos, formatos de archivo, crear y verificar."""

from __future__ import annotations

import io

import pytest

from app.services import sumas
from app.services.operaciones.comprimir import OperacionCrearSumas, OperacionVerificarSumas
from app.services.operaciones.modelo import Estado
from app.services.vfs import base
from app.services.vfs.local import ProveedorLocal
from tests.servicios.test_c_zip import _lanzar


@pytest.fixture
def local():
	return ProveedorLocal()


def test_algoritmos_con_valores_conocidos():
	assert sumas.calcular(io.BytesIO(b"abc"), "sha256") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
	assert sumas.calcular(io.BytesIO(b"abc"), "md5") == "900150983cd24fb0d6963f7d28e17f72"
	assert sumas.calcular(io.BytesIO(b"abc"), "sha1") == "a9993e364706816aba3e25717850c26c9cd0d89d"
	assert sumas.calcular(io.BytesIO(b"abc"), "crc32") == "352441C2"
	assert sumas.calcular_bytes(b"abc", "sha512").startswith("ddaf35a193617aba")
	assert sumas.calcular_bytes(b"abc", "blake2b").startswith("ba80a53f981c4d0d")


def test_cancelar_el_calculo():
	cancelacion = base.Cancelacion()
	cancelacion.cancelar()
	with pytest.raises(base.Cancelado):
		sumas.calcular(io.BytesIO(b"x" * 10), "sha256", cancelacion)


def test_formatos_de_linea_y_lectura():
	assert sumas.linea("sha256", "a.txt", "ABC") == "abc *a.txt"
	assert sumas.linea("crc32", "a.txt", "352441c2") == "a.txt 352441C2"
	texto = sumas.componer("sha256", [("a.txt", "aa"), ("sub\\b.txt", "bb")])
	assert texto == "aa *a.txt\r\nbb *sub\\b.txt\r\n"
	assert sumas.leer(texto) == [("a.txt", "aa"), ("sub\\b.txt", "bb")]
	# Modo texto de sha256sum, estilo BSD y comentarios.
	assert sumas.leer("# comentario\ncc  con espacios.txt\nSHA256 (otro.bin) = DD\n") == [
		("con espacios.txt", "cc"), ("otro.bin", "dd")]
	sfv = "; creado por alguien\r\nnombre con espacios.iso 1A2B3C4D\r\n"
	assert sumas.leer(sfv, "crc32") == [("nombre con espacios.iso", "1A2B3C4D")]
	assert sumas.algoritmo_de_archivo("copia.SHA256").id == "sha256"
	assert sumas.algoritmo_de_archivo("x.sfv").id == "crc32"
	assert sumas.algoritmo_de_archivo("x.txt") is None
	assert sumas.deducir_algoritmo([("a", "0" * 64)]) == "sha256"
	assert sumas.decodificar("﻿aa *ñ.txt".encode()) == "aa *ñ.txt"
	assert sumas.decodificar("aa *ñ.txt".encode("cp1252")) == "aa *ñ.txt"


def _carpeta(tmp_path):
	carpeta = tmp_path / "datos"
	(carpeta / "sub").mkdir(parents=True)
	(carpeta / "a.txt").write_bytes(b"abc")
	(carpeta / "sub" / "b.txt").write_bytes(b"segundo")
	return carpeta


def test_crear_y_verificar_uno_para_todos(tmp_path, local):
	carpeta = _carpeta(tmp_path)
	entradas = sorted(local.listar(str(carpeta)), key=lambda e: e.nombre)
	operacion = _lanzar(OperacionCrearSumas(local, entradas, "sha256", str(carpeta), nombre_archivo="datos"))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	archivo = carpeta / "datos.sha256"
	assert operacion.archivos_creados == [str(archivo)]
	texto = archivo.read_text(encoding="utf-8")
	assert "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad *a.txt" in texto
	assert "*sub\\b.txt" in texto
	verificar = _lanzar(OperacionVerificarSumas(local, str(archivo)))
	assert verificar.estado == Estado.TERMINADA
	assert [v.resultado for v in verificar.verificaciones] == [sumas.Resultado.CORRECTO] * 2
	assert verificar.resumen().endswith("2 correctos")
	# Un archivo cambiado y otro borrado.
	(carpeta / "a.txt").write_bytes(b"abd")
	(carpeta / "sub" / "b.txt").unlink()
	verificar = _lanzar(OperacionVerificarSumas(local, str(archivo)))
	assert verificar.estado == Estado.TERMINADA_CON_ERRORES
	assert [(v.nombre, v.resultado) for v in verificar.verificaciones] == [
		("a.txt", sumas.Resultado.DISTINTO), ("sub\\b.txt", sumas.Resultado.NO_ENCONTRADO)]
	assert "1 distinto" in verificar.resumen() and "1 no encontrado" in verificar.resumen()


def test_crear_sfv_por_archivo_en_otra_carpeta(tmp_path, local):
	carpeta = _carpeta(tmp_path)
	otra = tmp_path / "sumas"
	otra.mkdir()
	entrada = local.info(str(carpeta / "a.txt"))
	operacion = _lanzar(OperacionCrearSumas(local, [entrada], "crc32", str(otra), uno_por_archivo=True))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	sfv = (otra / "a.txt.sfv").read_text(encoding="utf-8")
	assert "..\\datos\\a.txt 352441C2" in sfv
	verificar = _lanzar(OperacionVerificarSumas(local, str(otra / "a.txt.sfv")))
	assert [v.resultado for v in verificar.verificaciones] == [sumas.Resultado.CORRECTO]


def test_solo_calcular_para_el_portapapeles(tmp_path, local):
	carpeta = _carpeta(tmp_path)
	entrada = local.info(str(carpeta / "a.txt"))
	operacion = _lanzar(OperacionCrearSumas(local, [entrada], "md5", "", guardar=False))
	assert operacion.sumas == [("a.txt", "900150983cd24fb0d6963f7d28e17f72")]
	assert operacion.archivos_creados == []
	assert sorted(p.name for p in carpeta.iterdir()) == ["a.txt", "sub"]
