# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque G: descripción del tipo y iconos del sistema por extensión."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Solo Windows")


@pytest.mark.parametrize(("texto", "esperado"), [
	("txt", "txt"), (".TXT", "txt"), ("nota.Txt", "txt"), ("a.tar.gz", "gz"), ("", ""), ("final.", ""),
])
def test_clave_extension(texto, esperado):
	from app.services.windows import iconos

	assert iconos.clave_extension(texto) == esperado


def test_descripcion_tipo_por_extension_o_nombre():
	from app.services.windows import iconos

	iconos.olvidar()
	descripcion = iconos.descripcion_tipo("txt")
	assert descripcion
	assert iconos.descripcion_tipo(".txt") == descripcion
	assert iconos.descripcion_tipo("informe.TXT") == descripcion
	assert iconos.descripcion_tipo("") is None


def test_descripcion_de_una_extension_desconocida():
	from app.services.windows import iconos

	# Windows da «Archivo ZQX» (o «ZQX File»): siempre lleva la extensión.
	assert "ZQXJ" in (iconos.descripcion_tipo("zqxj") or "").upper()


def test_descripcion_desde_un_hilo():
	"""La ventana la pide desde un hilo de trabajo (``pedir_tipo``)."""
	import threading

	from app.services.windows import iconos

	iconos.olvidar()
	resultado = []
	hilo = threading.Thread(target=lambda: resultado.append(iconos.descripcion_tipo("txt")))
	hilo.start()
	hilo.join(10)
	assert resultado and resultado[0]


def test_icono_pequeno():
	from app.services.windows import iconos

	for clave in ("txt", iconos.CARPETA, ""):
		hicon = iconos.icono_pequeno(clave)
		assert hicon
		iconos.destruir_icono(hicon)
