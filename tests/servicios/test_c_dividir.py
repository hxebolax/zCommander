# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Dividir y unir: partes .001, .002..., archivo .crc, comprobación y cancelación."""

from __future__ import annotations

import io
import os

import pytest

from app.services import dividir
from app.services.operaciones.comprimir import OperacionDividir, OperacionUnir
from app.services.operaciones.modelo import Estado
from app.services.vfs import base
from app.services.vfs.local import ProveedorLocal
from tests.servicios.test_c_zip import _lanzar

MB = 1024 * 1024


@pytest.fixture
def original(tmp_path):
	ruta = tmp_path / "video.mp4"
	ruta.write_bytes(os.urandom(int(2.5 * MB)))
	return ruta


def test_dividir_en_tres_partes_y_unir(tmp_path, original):
	local = ProveedorLocal()
	destino = tmp_path / "partes"
	destino.mkdir()
	operacion = _lanzar(OperacionDividir(local, local.info(str(original)), str(destino), MB))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert sorted(os.listdir(destino)) == ["video.crc", "video.mp4.001", "video.mp4.002", "video.mp4.003"]
	assert [os.path.getsize(destino / f"video.mp4.00{n}") for n in (1, 2, 3)] == [MB, MB, MB // 2]
	info = dividir.leer_crc((destino / "video.crc").read_text(encoding="utf-8"))
	assert info.nombre == "video.mp4" and info.tamano == int(2.5 * MB)
	assert "3 partes" in operacion.resumen()
	assert dividir.nombre_original(str(destino / "video.mp4.001")) == "video.mp4"
	unido = tmp_path / "unido.mp4"
	union = _lanzar(OperacionUnir(str(destino / "video.mp4.001"), str(unido)))
	assert union.estado == Estado.TERMINADA, union.errores
	assert unido.read_bytes() == original.read_bytes()
	assert union.resultado.comprobado is True
	assert "comprobado" in union.resumen()


def test_unir_con_una_parte_danada_avisa(tmp_path, original):
	destino = tmp_path / "partes"
	destino.mkdir()
	with open(original, "rb") as flujo:
		dividir.dividir(flujo, original.name, original.stat().st_size, str(destino), MB)
	parte = destino / "video.mp4.002"
	datos = bytearray(parte.read_bytes())
	datos[10] ^= 0xFF
	parte.write_bytes(bytes(datos))
	union = _lanzar(OperacionUnir(str(destino / "video.mp4.001"), str(tmp_path / "unido.mp4")))
	assert union.estado == Estado.TERMINADA_CON_ERRORES
	assert union.resultado.comprobado is False
	assert "ERROR" in union.resumen()


def test_dividir_tamano_exacto_y_vacio(tmp_path):
	carpeta = tmp_path / "p"
	carpeta.mkdir()
	creados = dividir.dividir(io.BytesIO(b"x" * 2048), "a.bin", 2048, str(carpeta), 1024)
	assert [os.path.basename(c) for c in creados] == ["a.bin.001", "a.bin.002", "a.crc"]
	vacio = tmp_path / "v"
	vacio.mkdir()
	creados = dividir.dividir(io.BytesIO(b""), "nada.bin", 0, str(vacio), 1024)
	assert [os.path.basename(c) for c in creados] == ["nada.bin.001", "nada.crc"]


def test_cancelar_no_deja_partes(tmp_path):
	carpeta = tmp_path / "p"
	carpeta.mkdir()
	cancelacion = base.Cancelacion()
	leidos = []

	def avanzar(n: int) -> None:
		leidos.append(n)
		if sum(leidos) >= 3 * MB:
			cancelacion.cancelar()

	with pytest.raises(base.Cancelado):
		dividir.dividir(io.BytesIO(b"z" * (5 * MB)), "a.bin", 5 * MB, str(carpeta), 2 * MB, cancelacion, avanzar)
	assert os.listdir(carpeta) == []


def test_tamanos_y_nombres():
	assert dividir.leer_tamano("2,5", MB) == int(2.5 * MB)
	assert dividir.leer_tamano("1.5", 1024) == 1536
	assert dividir.leer_tamano("0", MB) is None
	assert dividir.leer_tamano("abc", MB) is None
	assert dividir.numero_partes(int(2.5 * MB), MB) == 3
	assert dividir.TAMANOS_PREDEFINIDOS[0] == ("1,44 MB", 1457664)
	assert dividir.es_primera_parte("a.zip.001") and not dividir.es_primera_parte("a.zip.002")
	assert dividir.leer_crc("filename=a.b\nsize=10\ncrc32=abc\n").crc32 == "ABC"
