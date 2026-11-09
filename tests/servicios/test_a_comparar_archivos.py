# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comparación de archivos por contenido (bloque A, sección 8.19)."""

from __future__ import annotations

import codecs
import io

import pytest

from app.services import comparar_archivos as ca
from app.services.vfs import base


def _lineas(n: int) -> list[str]:
	return [f"Línea número {i}" for i in range(1, n + 1)]


def test_linea_12_cambiada():
	izquierdo = _lineas(20)
	derecho = list(izquierdo)
	derecho[11] = "Esta es distinta"
	diferencias = ca.comparar_textos("\r\n".join(izquierdo) + "\r\n", "\r\n".join(derecho) + "\r\n")
	assert len(diferencias) == 1
	assert ca.describir(diferencias[0]) == "Línea 12: cambiada"
	assert diferencias[0].tipo == ca.CAMBIADA


def test_varias_lineas_y_solo_en_un_lado():
	izquierdo = _lineas(10)
	derecho = izquierdo[:2] + ["nueva a", "nueva b"] + izquierdo[2:7] + izquierdo[8:]
	descripciones = [ca.describir(d) for d in ca.comparar_lineas(izquierdo, derecho)]
	assert descripciones == ["Líneas 3 a 4: solo en el derecho", "Línea 8: solo en el izquierdo"]
	cambiadas = ca.comparar_lineas(["a", "b", "c", "d"], ["a", "X", "Y", "d"])
	assert [ca.describir(d) for d in cambiadas] == ["Líneas 2 a 3: cambiadas"]
	# Si en el derecho está en otro sitio, se dice entre paréntesis.
	movida = ca.comparar_lineas(["a", "b", "c"], ["n", "a", "X", "c"])
	assert [ca.describir(d) for d in movida] == ["Línea 1: solo en el derecho", "Línea 2: cambiada (línea 3 en el derecho)"]


def test_lineas_de_respeta_los_fines_de_linea():
	assert ca.lineas_de("a\r\nb\rc\nd") == ["a", "b", "c", "d"]
	assert ca.lineas_de("a\n") == ["a"]
	assert ca.lineas_de("") == []
	# El salto de página no parte la línea (splitlines sí lo haría).
	assert ca.lineas_de("a\x0cb\n") == ["a\x0cb"]


def test_textos_iguales_con_otra_codificacion():
	texto = "Año\r\nEspaña\r\n"
	utf8 = texto.encode("utf-8")
	utf16 = codecs.BOM_UTF16_LE + texto.encode("utf-16-le")
	resultado = ca.comparar_datos(utf8, utf16)
	assert resultado.es_texto
	assert not resultado.iguales
	assert resultado.texto_igual
	assert resultado.codificacion_der == "utf-16-le"
	assert ca.resumen(resultado) == "El texto es igual; cambian la codificación o los fines de línea"
	assert ca.resumen(ca.comparar_datos(utf8, utf8)) == "Los archivos son iguales"


def test_binarios_distintos_a_partir_del_byte():
	a = bytes(range(256)) * 32  # 8192 bytes con ceros: binario
	b = bytearray(a)
	b[4096] ^= 0xFF
	resultado = ca.comparar_datos(a, bytes(b))
	assert not resultado.es_texto
	assert resultado.primer_distinto == 4096
	assert ca.resumen(resultado) == "Distintos a partir del byte 4096"
	# Uno es el principio del otro: distintos donde acaba el corto.
	assert ca.primer_byte_distinto(io.BytesIO(a), io.BytesIO(a + b"\x00"), bloque=1000) == len(a)
	assert ca.primer_byte_distinto(io.BytesIO(a), io.BytesIO(a), bloque=1000) is None


def test_comparar_desde_proveedor_y_cancelar(tmp_path):
	from app.services.vfs import resolver

	local = resolver.proveedor_local()
	izq = tmp_path / "a.txt"
	der = tmp_path / "b.txt"
	izq.write_text("uno\ndos\ntres\n", encoding="utf-8")
	der.write_text("uno\nDOS\ntres\n", encoding="utf-8")
	resultado = ca.comparar(lambda: local.abrir_lectura(str(izq)), lambda: local.abrir_lectura(str(der)),
		izq.stat().st_size, der.stat().st_size)
	assert [ca.describir(d) for d in resultado.diferencias] == ["Línea 2: cambiada"]
	assert ca.resumen(resultado) == "1 diferencia"
	cancelado = base.Cancelacion()
	cancelado.cancelar()
	with pytest.raises(base.Cancelado):
		ca.comparar(lambda: local.abrir_lectura(str(izq)), lambda: local.abrir_lectura(str(der)), 1, 1, cancelado)
