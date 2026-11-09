# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Preparación común de las pruebas del bloque CM (comprimidos ampliados).

Las pruebas usan los binarios reales de ``data/bin`` (libarchive y 7za): se
fija la carpeta de recursos en la ``data`` del proyecto (como hace
``--comprobar-arranque``), mientras que los temporales y la configuración
siguen en la ``data`` temporal de cada prueba.
"""

from __future__ import annotations

import ctypes
import io
from pathlib import Path

import pytest

from app.core import paths
from app.services.vfs import base, resolver
from tests.servicios.test_c_zip import DecisorFalso

RAIZ = Path(__file__).resolve().parents[2]


class DecisorConClave(DecisorFalso):
	"""Responde a las peticiones de contraseña con ``respuestas`` (y anota los textos)."""

	def __init__(self, respuestas=()) -> None:
		super().__init__()
		self.respuestas = list(respuestas)

	def pedir_texto(self, titulo, texto, valor="", oculto=False, operacion=None):
		self.textos.append(texto)
		assert oculto
		return self.respuestas.pop(0) if self.respuestas else None


class ConfigFalsa:
	"""Configuración mínima con las claves de comprimidos (las demás, su valor por defecto)."""

	def __init__(self, **valores) -> None:
		self.valores = {"comprimidos.usar_libarchive": True, "comprimidos.usar_7za": True,
			"comprimidos.usar_7zip_instalado": True, "comprimidos.ruta_7zip": "", "comprimidos.metodo_zip": "deflate",
			"comprimidos.flujos_como_carpeta": True}
		self.valores.update({k.replace("__", "."): v for k, v in valores.items()})

	def obtener(self, clave, por_defecto=None):
		if clave in self.valores:
			return self.valores[clave]
		raise KeyError(clave)


@pytest.fixture
def recursos_reales():
	"""Binarios de la ``data`` real y proveedores de CM registrados."""
	paths.fijar_recursos(RAIZ / "data")
	from app.services.libarchive import ffi

	if ffi.cargar() is None:
		paths.fijar_recursos(None)
		pytest.skip("Falta data/bin/libarchive")
	from app.services.vfs import flujo, libarchive, registro_proveedores  # noqa: F401 - registran los proveedores

	libarchive.registrar()
	flujo.registrar()
	yield
	paths.fijar_recursos(None)


def fijar(monkeypatch, decisor=None, config=None):
	"""Fija el decisor y la configuración de los proveedores (``monkeypatch`` los quita al terminar)."""
	monkeypatch.setattr(resolver, "_servicios", resolver.Servicios(decisor=decisor or DecisorFalso(),
		config=config or ConfigFalsa()))
	return decisor


@pytest.fixture
def servicios_cm(monkeypatch):
	"""Decisor falso y configuración con las claves de comprimidos por defecto."""
	fijar(monkeypatch)


def abrir(ruta: Path) -> base.Proveedor:
	return resolver.abrir_comprimido(resolver.proveedor_local(), str(ruta))


def todo(proveedor: base.Proveedor) -> dict[str, bytes]:
	"""Contenido de todos los archivos del comprimido, por ruta interna."""
	contenido = {}
	for ruta in proveedor.indice().archivos():
		with proveedor.abrir_lectura(ruta) as flujo:
			contenido[ruta] = flujo.read()
	return contenido


def escribir_libarchive(ruta: Path, funcion_formato: str, miembros: list[tuple[str, bytes | None]], filtro: str | None = None,
		opciones: str = "") -> Path:
	"""Crea un comprimido con cualquier formato y filtro de libarchive (para formatos que zCommander no crea)."""
	from app.services.libarchive import ffi

	biblioteca = ffi.cargar()
	a = biblioteca.archive_write_new()
	entrada = biblioteca.archive_entry_new()
	try:
		assert getattr(biblioteca, funcion_formato)(a) == 0, ffi.texto_error(biblioteca, a)
		if filtro:
			assert getattr(biblioteca, filtro)(a) == 0, ffi.texto_error(biblioteca, a)
		if opciones:
			assert biblioteca.archive_write_set_options(a, opciones.encode()) >= ffi.ARCHIVE_WARN
		assert biblioteca.archive_write_open_filename_w(a, str(ruta)) == 0, ffi.texto_error(biblioteca, a)
		for nombre, datos in miembros:
			biblioteca.archive_entry_clear(entrada)
			biblioteca.archive_entry_copy_pathname_w(entrada, nombre)
			biblioteca.archive_entry_set_filetype(entrada, ffi.AE_IFDIR if datos is None else ffi.AE_IFREG)
			biblioteca.archive_entry_set_perm(entrada, 0o755 if datos is None else 0o644)
			biblioteca.archive_entry_set_size(entrada, len(datos or b""))
			biblioteca.archive_entry_set_mtime(entrada, 1_700_000_000, 0)
			assert biblioteca.archive_write_header(a, entrada) >= ffi.ARCHIVE_WARN, ffi.texto_error(biblioteca, a)
			if datos:
				bufer = ctypes.create_string_buffer(datos, len(datos))
				assert biblioteca.archive_write_data(a, bufer, len(datos)) == len(datos)
		assert biblioteca.archive_write_close(a) == 0, ffi.texto_error(biblioteca, a)
	finally:
		biblioteca.archive_entry_free(entrada)
		biblioteca.archive_write_free(a)
	return ruta


DATOS = bytes(range(256)) * 64
TEXTO = "Hola, ñandú y €\n".encode() * 50


def flujo(datos: bytes) -> io.BytesIO:
	return io.BytesIO(datos)
