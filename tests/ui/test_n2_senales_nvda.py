# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Señales para el complemento de NVDA (diseño 2.0, 10.5, 10.16 y 18.2)."""

from __future__ import annotations

import pytest

from app.ui import senales_nvda


def test_codifica_0_3_1():
	valor = senales_nvda.codificar_orden([0, 3, 1])
	assert valor == 0xF130
	assert senales_nvda.decodificar_orden(valor) == [0, 3, 1]


def test_quince_columnas_es_el_maximo():
	indices = list(range(15))
	valor = senales_nvda.codificar_orden(indices)
	assert valor < 2**64
	assert valor >> 60 == 0xF
	assert senales_nvda.decodificar_orden(valor) == indices
	with pytest.raises(ValueError):
		senales_nvda.codificar_orden(list(range(16)))
	with pytest.raises(ValueError):
		senales_nvda.codificar_orden([15])


def test_publica_y_marca_en_una_ventana(app_wx):
	import wx

	marco = wx.Frame(None)
	try:
		hwnd = marco.GetHandle()
		senales_nvda.publicar_orden_lectura(hwnd, [0, 3, 1])
		assert senales_nvda.leer_propiedad(hwnd, senales_nvda.PROPIEDAD_LECTURA) == 0xF130
		senales_nvda.configurar(True)
		senales_nvda.marcar_movimiento_silencioso(hwnd)
		hora = senales_nvda.leer_propiedad(hwnd, senales_nvda.PROPIEDAD_SILENCIO)
		assert hora > 0
		assert abs(hora - senales_nvda._ahora_ms()) < 5000
	finally:
		marco.Destroy()
