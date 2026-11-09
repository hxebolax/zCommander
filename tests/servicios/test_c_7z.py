# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor 7z (py7zr 0.11.3): listar, leer miembro a miembro, contraseña, nombres peligrosos, probar y comprimir."""

from __future__ import annotations

import pytest

py7zr = pytest.importorskip("py7zr")

from app.services.operaciones.comprimir import OpcionesComprimir, OperacionComprimir, OperacionExtraer, OperacionProbar  # noqa: E402
from app.services.operaciones.copiar import OpcionesCopia  # noqa: E402
from app.services.operaciones.modelo import Estado  # noqa: E402
from app.services.vfs import base, registro_proveedores, resolver  # noqa: E402,F401 - registra los proveedores
from app.services.vfs.local import ProveedorLocal  # noqa: E402
from app.services.vfs.siete_z import ProveedorSieteZ  # noqa: E402
from tests.servicios.test_c_zip import DecisorFalso, _lanzar  # noqa: E402


class DecisorConClave(DecisorFalso):
	def __init__(self, respuestas) -> None:
		super().__init__()
		self.respuestas = list(respuestas)

	def pedir_texto(self, titulo, texto, valor="", oculto=False, operacion=None):
		self.textos.append(texto)
		assert oculto
		return self.respuestas.pop(0) if self.respuestas else None


@pytest.fixture
def local():
	return ProveedorLocal()


@pytest.fixture
def servicios(monkeypatch):
	"""Sustituye el decisor de los proveedores y lo devuelve al terminar."""

	def fijar(decisor):
		monkeypatch.setattr(resolver, "_servicios", resolver.Servicios(decisor=decisor))
		return decisor

	return fijar


def _origen(tmp_path):
	origen = tmp_path / "src"
	(origen / "sub").mkdir(parents=True)
	(origen / "a.txt").write_bytes(b"hola" * 1000)
	(origen / "sub" / "b.txt").write_bytes(b"adios")
	(origen / "vacio.txt").write_bytes(b"")
	return origen


def _crear(ruta, origen, contrasena=None, extra=()):
	with py7zr.SevenZipFile(ruta, "w", password=contrasena) as archivo:
		archivo.write(origen / "a.txt", "a.txt")
		archivo.write(origen / "sub", "sub")
		archivo.write(origen / "sub" / "b.txt", "sub/b.txt")
		archivo.write(origen / "vacio.txt", "vacio.txt")
		for nombre in extra:
			archivo.write(origen / "a.txt", nombre)


def test_7z_lista_y_lee(tmp_path, local):
	origen = _origen(tmp_path)
	ruta = tmp_path / "x.7z"
	_crear(ruta, origen, extra=("../malo.txt",))
	proveedor, carpeta, _cursor = resolver.abrir_ruta(str(ruta))
	assert isinstance(proveedor, ProveedorSieteZ) and carpeta == ""
	assert [e.nombre for e in proveedor.listar("")] == ["a.txt", "sub", "vacio.txt"]
	assert proveedor.omitidas == ["../malo.txt"]
	with proveedor.abrir_lectura("sub/b.txt") as flujo:
		assert flujo.read() == b"adios"
	# El anterior del mismo bloque sólido se guardó de paso y se sirve sin descomprimir otra vez.
	assert proveedor._previos
	with proveedor.abrir_lectura("a.txt") as flujo:
		assert flujo.read() == b"hola" * 1000
	assert not proveedor._previos
	with proveedor.abrir_lectura("vacio.txt") as flujo:
		assert flujo.read() == b""
	resultado = proveedor.probar()
	assert resultado.correcto and resultado.archivos == 3
	proveedor.cerrar()


def test_7z_con_contrasena_la_pide_y_reintenta(tmp_path, local, servicios):
	origen = _origen(tmp_path)
	ruta = tmp_path / "secreto.7z"
	_crear(ruta, origen, contrasena="buena")
	decisor = servicios(DecisorConClave(["mala", "buena"]))
	proveedor = resolver.abrir_comprimido(local, str(ruta))
	assert [e.nombre for e in proveedor.listar("")] == ["a.txt", "sub", "vacio.txt"]
	with proveedor.abrir_lectura("sub/b.txt") as flujo:
		assert flujo.read() == b"adios"
	assert len(decisor.textos) == 2
	assert "no es correcta" in decisor.textos[1]
	proveedor.cerrar()


def test_7z_cancelar_la_contrasena_cancela(tmp_path, local, servicios):
	origen = _origen(tmp_path)
	ruta = tmp_path / "secreto.7z"
	_crear(ruta, origen, contrasena="buena")
	servicios(DecisorConClave([]))
	proveedor = resolver.abrir_comprimido(local, str(ruta))
	with pytest.raises(base.Cancelado):
		proveedor.abrir_lectura("a.txt")
	proveedor.cerrar()


def test_extraer_7z(tmp_path, local):
	origen = _origen(tmp_path)
	ruta = tmp_path / "x.7z"
	_crear(ruta, origen, extra=("../fuera.txt",))
	destino = tmp_path / "salida"
	destino.mkdir()
	_lanzar(OperacionExtraer(local, [local.info(str(ruta))], local, str(destino), OpcionesCopia()))
	assert (destino / "a.txt").read_bytes() == b"hola" * 1000
	assert (destino / "sub" / "b.txt").read_bytes() == b"adios"
	assert (destino / "vacio.txt").read_bytes() == b""
	assert not (tmp_path / "fuera.txt").exists()


@pytest.mark.parametrize("nivel", ["sin", "rapido", "maximo"])
def test_comprimir_7z_con_contrasena(tmp_path, local, servicios, nivel):
	origen = _origen(tmp_path)
	destino = tmp_path / "salida.7z"
	opciones = OpcionesComprimir(formato="7z", nivel=nivel, contrasena="clave")
	operacion = _lanzar(OperacionComprimir(local, [local.info(str(origen))], str(destino), opciones))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	with pytest.raises(py7zr.exceptions.PasswordRequired), py7zr.SevenZipFile(destino) as archivo:
		archivo.readall()
	with py7zr.SevenZipFile(destino, password="clave") as archivo:
		contenido = {nombre: flujo.read() for nombre, flujo in archivo.readall().items()}
	assert contenido["src/sub/b.txt"] == b"adios"
	prueba = _lanzar(OperacionProbar(local, [str(destino)], contrasena="clave"))
	assert prueba.estado == Estado.TERMINADA, prueba.errores


def test_comprimir_zip_no_admite_contrasena(tmp_path):
	from app.services import comprimir

	with pytest.raises(base.NoAdmitido):
		comprimir.crear_escritor("zip", str(tmp_path / "x.zip"), contrasena="clave")
	assert comprimir.cambiar_extension("C:\\a\\copia.zip", "tar.gz") == "C:\\a\\copia.tar.gz"
	assert comprimir.cambiar_extension("copia.tar.gz", "7z") == "copia.7z"
	assert comprimir.formato_de("a.TGZ") == "tar.gz"
	assert comprimir.quitar_extension_comprimido("informe.final.docx") == "informe.final"
