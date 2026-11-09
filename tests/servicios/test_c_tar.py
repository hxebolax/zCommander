# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor TAR: .tar, .tar.gz, .tar.bz2 y .tar.xz, nombres peligrosos, enlaces, extraer, probar y comprimir."""

from __future__ import annotations

import io
import tarfile

import pytest

from app.services.operaciones.comprimir import OpcionesComprimir, OperacionComprimir, OperacionExtraer, OperacionProbar
from app.services.operaciones.copiar import OpcionesCopia
from app.services.operaciones.modelo import Estado
from app.services.vfs import base, registro_proveedores, resolver  # noqa: F401 - registra los proveedores
from app.services.vfs.local import ProveedorLocal
from app.services.vfs.tar import ProveedorTar
from tests.servicios.test_c_zip import _lanzar


@pytest.fixture
def local():
	return ProveedorLocal()


def _agregar(archivo: tarfile.TarFile, nombre: str, datos: bytes = b"", tipo=tarfile.REGTYPE, enlace: str = "") -> None:
	info = tarfile.TarInfo(nombre)
	info.type = tipo
	info.linkname = enlace
	info.size = len(datos) if tipo == tarfile.REGTYPE else 0
	info.mtime = 1_700_000_000
	archivo.addfile(info, io.BytesIO(datos) if tipo == tarfile.REGTYPE else None)


def _tar_malicioso(ruta, modo: str) -> None:
	with tarfile.open(ruta, modo) as archivo:
		_agregar(archivo, "bueno.txt", b"hola")
		_agregar(archivo, "docs", tipo=tarfile.DIRTYPE)
		_agregar(archivo, "docs/dentro.txt", b"dentro" * 1000)
		_agregar(archivo, "../malo.txt", b"fuera")
		_agregar(archivo, "/etc/absoluto", b"fuera")
		_agregar(archivo, "enlace", tipo=tarfile.SYMTYPE, enlace="../../windows")
		_agregar(archivo, "duro.txt", tipo=tarfile.LNKTYPE, enlace="bueno.txt")
		_agregar(archivo, "dispositivo", tipo=tarfile.CHRTYPE)


@pytest.mark.parametrize(("extension", "modo"), [("tar", "w"), ("tar.gz", "w:gz"), ("tgz", "w:gz"), ("tar.bz2", "w:bz2"),
	("tar.xz", "w:xz")])
def test_tar_lista_sin_entradas_peligrosas(tmp_path, local, extension, modo):
	ruta = tmp_path / f"x.{extension}"
	_tar_malicioso(ruta, modo)
	proveedor = resolver.abrir_comprimido(local, str(ruta))
	assert isinstance(proveedor, ProveedorTar)
	assert not proveedor.capacidades.escribir
	assert [e.nombre for e in proveedor.listar("")] == ["bueno.txt", "docs", "duro.txt"]
	assert set(proveedor.omitidas) == {"../malo.txt", "/etc/absoluto", "enlace", "dispositivo"}
	with proveedor.abrir_lectura("duro.txt") as flujo:
		assert flujo.read() == b"hola"
	assert proveedor.info("docs/dentro.txt").tamano == 6000
	with pytest.raises(base.SoloLectura):
		proveedor.crear_carpeta("nueva")
	proveedor.cerrar()


def test_extraer_tar_gz(tmp_path, local):
	ruta = tmp_path / "datos" / "x.tar.gz"
	ruta.parent.mkdir()
	_tar_malicioso(ruta, "w:gz")
	destino = tmp_path / "datos" / "salida"
	destino.mkdir()
	operacion = _lanzar(OperacionExtraer(local, [local.info(str(ruta))], local, str(destino), OpcionesCopia(), por_carpeta=True))
	assert (destino / "x" / "bueno.txt").read_bytes() == b"hola"
	assert (destino / "x" / "docs" / "dentro.txt").read_bytes() == b"dentro" * 1000
	assert (destino / "x" / "duro.txt").read_bytes() == b"hola"
	assert not (tmp_path / "datos" / "malo.txt").exists()
	assert not (destino / "x" / "enlace").exists()
	assert operacion.estado == Estado.TERMINADA_CON_ERRORES  # avisa de las 4 omitidas
	prueba = _lanzar(OperacionProbar(local, [str(ruta)]))
	assert prueba.estado == Estado.TERMINADA
	assert prueba.instantanea().archivos_hechos == 3


@pytest.mark.parametrize("formato", ["tar", "tar.gz", "tar.bz2", "tar.xz"])
def test_comprimir_tar_y_volver_a_leerlo(tmp_path, local, formato):
	origen = tmp_path / "carpeta"
	(origen / "sub").mkdir(parents=True)
	(origen / "sub" / "a.txt").write_bytes(b"a" * 5000)
	(origen / "b.txt").write_bytes(b"b")
	destino = tmp_path / f"salida.{formato}"
	operacion = _lanzar(OperacionComprimir(local, [local.info(str(origen))], str(destino), OpcionesComprimir(formato=formato,
		nivel="rapido")))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	with tarfile.open(destino, "r:*") as archivo:
		assert sorted(archivo.getnames()) == ["carpeta", "carpeta/b.txt", "carpeta/sub", "carpeta/sub/a.txt"]
		assert archivo.extractfile("carpeta/sub/a.txt").read() == b"a" * 5000
	# Añadir a un TAR existente lo reescribe con lo que tenía.
	nuevo = tmp_path / "nuevo.txt"
	nuevo.write_bytes(b"nuevo")
	operacion = _lanzar(OperacionComprimir(local, [local.info(str(nuevo))], str(destino), OpcionesComprimir(formato=formato)))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	proveedor = resolver.abrir_comprimido(local, str(destino))
	assert sorted(e.nombre for e in proveedor.listar("")) == ["carpeta", "nuevo.txt"]
	with proveedor.abrir_lectura("carpeta/sub/a.txt") as flujo:
		assert flujo.read() == b"a" * 5000
	proveedor.cerrar()


def test_tar_danado_da_error_claro(tmp_path, local):
	ruta = tmp_path / "roto.tar.gz"
	ruta.write_bytes(b"\x1f\x8b\x08\x00" + b"basura" * 100)
	proveedor = resolver.abrir_comprimido(local, str(ruta))
	with pytest.raises(base.ErrorArchivos) as error:
		proveedor.listar("")
	assert "dañado" in error.value.mensaje
	proveedor.cerrar()
