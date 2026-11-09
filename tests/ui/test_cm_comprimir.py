# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque CM: el diálogo Comprimir con los formatos de la 2.0 (8.6): teclado, motor, contraseñas y formatos de un solo archivo."""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.dialogos.c_comprimir import DialogoComprimir  # noqa: E402
from tests.servicios.cm_comun import recursos_reales, servicios_cm  # noqa: E402,F401 - fixtures

pytestmark = pytest.mark.usefixtures("recursos_reales", "servicios_cm")


def _elegir(dialogo, clave):
	indice = next(i for i, (c, _t) in enumerate(dialogo._formatos) if c == clave)
	dialogo.lista_formato.SetSelection(indice)
	dialogo._al_cambiar_formato(wx.CommandEvent())


def test_teclado_y_motor(app_wx):
	dialogo = DialogoComprimir(None, "Comprimir 2 archivos", "D:\\Copias\\datos.zip")
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=["F2"])
		assert dialogo.texto_motor.GetValue() == "Python"
		_elegir(dialogo, "iso")
		assert dialogo.destino() == "D:\\Copias\\datos.iso"
		assert dialogo.texto_motor.GetValue().startswith("libarchive 3.8")
		assert not dialogo.campo_contrasena.IsEnabled() and not dialogo.casilla_cifrar_nombres.IsEnabled()
		_elegir(dialogo, "7z")
		assert dialogo.casilla_cifrar_nombres.IsEnabled() and dialogo.campo_contrasena.IsEnabled()
		dialogo.campo_contrasena.SetValue("clave")
		dialogo.campo_confirmar.SetValue("clave")
		dialogo.casilla_cifrar_nombres.SetValue(True)
		opciones = dialogo.opciones()
		assert opciones.formato == "7z" and opciones.cifrar_nombres and opciones.contrasena == "clave"
	finally:
		dialogo.Destroy()


def test_zip_cifrado_y_zstandard(app_wx):
	dialogo = DialogoComprimir(None, "Comprimir 1 carpeta", "D:\\Copias\\datos.zip")
	try:
		_elegir(dialogo, "zip:aes")
		assert dialogo.formato() == "zip" and dialogo.variante() == "aes"
		assert dialogo.destino() == "D:\\Copias\\datos.zip"
		assert dialogo.campo_contrasena.IsEnabled() and not dialogo.casilla_cifrar_nombres.IsEnabled()
		assert "contraseña del ZIP" in dialogo.problema()
		dialogo.campo_contrasena.SetValue("x")
		dialogo.campo_confirmar.SetValue("x")
		assert dialogo.problema() is None
		assert dialogo.opciones().variante == "aes" and dialogo.opciones().contrasena == "x"
		_elegir(dialogo, "zip:zstd")
		assert dialogo.opciones().variante == "zstd" and dialogo.opciones().contrasena == ""
		assert not dialogo.campo_contrasena.IsEnabled()
	finally:
		dialogo.Destroy()


def test_formatos_de_un_solo_archivo(app_wx):
	dialogo = DialogoComprimir(None, "Comprimir 2 archivos", "D:\\Copias\\datos.zip")
	try:
		_elegir(dialogo, "gz")
		assert dialogo.destino() == "D:\\Copias"
		assert dialogo.casilla_por_elemento.GetValue() and not dialogo.casilla_por_elemento.IsEnabled()
		assert dialogo.opciones().por_elemento and dialogo.opciones().formato == "gz"
		_elegir(dialogo, "tar.zst")
		assert dialogo.destino() == "D:\\Copias\\datos.tar.zst"
		assert not dialogo.casilla_por_elemento.GetValue() and dialogo.casilla_por_elemento.IsEnabled()
	finally:
		dialogo.Destroy()
	con_carpetas = DialogoComprimir(None, "Comprimir 1 carpeta", "D:\\Copias\\datos.zip", hay_carpetas=True)
	try:
		assert "gz" not in [c for c, _t in con_carpetas._formatos]
		assert "carpetas" in con_carpetas.lista_formato.GetHelpText()
	finally:
		con_carpetas.Destroy()
