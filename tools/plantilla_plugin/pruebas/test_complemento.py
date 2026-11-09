# SPDX-License-Identifier: GPL-3.0-or-later
"""Pruebas del complemento «{{nombre}}» con ``api.pruebas`` (sin ventana ni wx).

Se ejecutan con ``python tools/validar_plugin.py <carpeta>`` o con pytest desde
la carpeta de zCommander: ``python -m pytest <carpeta>/pruebas``.
"""

from __future__ import annotations

from pathlib import Path

from app.plugins import api
from app.plugins.api import pruebas

CARPETA = Path(__file__).resolve().parents[1]


def test_saludar_anuncia_el_nombre_del_cursor():
	zc = pruebas.anfitrion_de_prueba(CARPETA)
	panel = pruebas.PanelFalso([api.Entrada("informe.txt", "C:\\informe.txt")])
	anuncios: list[str] = []
	contexto = pruebas.contexto_de_prueba(activo=panel)
	contexto.anunciar = lambda texto, nivel=api.NORMAL, completo="", interrumpir=None: anuncios.append(texto)
	zc.ejecutar("saludar", contexto)
	assert anuncios == ["Hola, informe.txt"]


def test_el_saludo_sale_de_la_configuracion():
	zc = pruebas.anfitrion_de_prueba(CARPETA, config={"saludo": "Buenas"})
	assert zc.config.obtener("saludo") == "Buenas"
