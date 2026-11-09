# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""2.0.1: página «Actualizaciones» de Preferencias con el origen de las actualizaciones.

El campo de la dirección personalizada solo está habilitado con «Una dirección
personalizada»; deshabilitado, Tab lo salta y el lector dice «no disponible».
"""

from __future__ import annotations

import pytest

from tests.conftest import procesar_eventos

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.ui.dialogos import f_preferencias  # noqa: E402

URL = "https://espejo.ejemplo.org/zc/version.json"


@pytest.fixture
def dialogo(app_wx, tmp_path, monkeypatch):
	from app.ui import dialogo_preferencias as plantilla

	avisos: list[str] = []
	monkeypatch.setattr(plantilla, "mostrar_aviso", lambda padre, texto, titulo: avisos.append(texto))
	config = Configuracion(ruta=tmp_path / "settings.json")
	ventana = f_preferencias.DialogoPreferenciasZ(None, config, pagina="Actualizaciones")
	ventana.avisos = avisos
	yield ventana
	ventana.Destroy()
	procesar_eventos()


def _elegir(dialogo, valor: str) -> None:
	control = dialogo.control_de("actualizaciones.fuente")
	valores = [v for v, _nombre in dialogo._controles["actualizaciones.fuente"][0].opciones]  # noqa: SLF001
	control.SetSelection(valores.index(valor))
	evento = wx.CommandEvent(wx.wxEVT_CHOICE, control.GetId())
	evento.SetEventObject(control)
	control.GetEventHandler().ProcessEvent(evento)


def test_las_opciones_se_ven_con_su_nombre_y_la_direccion_va_despues(dialogo):
	fuente = dialogo.control_de("actualizaciones.fuente")
	assert [fuente.GetString(i) for i in range(fuente.GetCount())] == [
		"Servidor de zCommander (xebolax.synology.me)", "GitHub (hxebolax/zCommander)",
		"Las dos: la que tenga la versión más nueva", "Una dirección personalizada"]
	assert fuente.GetSelection() == 0
	direccion = dialogo.control_de("actualizaciones.url_personalizada")
	hermanos = list(direccion.GetParent().GetChildren())
	assert isinstance(hermanos[hermanos.index(direccion) - 1], wx.StaticText), "etiqueta justo antes"
	assert "https://" in direccion.GetHelpText() and "firma" in fuente.GetHelpText()


def test_la_direccion_solo_se_habilita_con_la_opcion_personalizada(dialogo):
	direccion = dialogo.control_de("actualizaciones.url_personalizada")
	assert not direccion.IsEnabled()
	_elegir(dialogo, "personalizada")
	assert direccion.IsEnabled()
	_elegir(dialogo, "ambas")
	assert not direccion.IsEnabled()


def test_guardar_la_fuente_personalizada(dialogo):
	_elegir(dialogo, "personalizada")
	dialogo.control_de("actualizaciones.url_personalizada").SetValue(URL)
	assert dialogo.aplicar()
	assert dialogo._config.obtener("actualizaciones.fuente") == "personalizada"  # noqa: SLF001
	assert dialogo._config.obtener("actualizaciones.url_personalizada") == URL  # noqa: SLF001


def test_una_direccion_http_no_se_guarda_y_el_foco_va_al_campo(dialogo):
	_elegir(dialogo, "personalizada")
	direccion = dialogo.control_de("actualizaciones.url_personalizada")
	direccion.SetValue("http://espejo.ejemplo.org/version.json")
	assert not dialogo.aplicar()
	assert dialogo.avisos and "https://" in dialogo.avisos[-1]
	assert dialogo._config.obtener("actualizaciones.url_personalizada") == ""  # noqa: SLF001
	# Aunque luego se elija otra fuente (campo deshabilitado), el aviso lo habilita para poder corregirlo.
	_elegir(dialogo, "servidor")
	assert not dialogo.aplicar() and direccion.IsEnabled()


def test_valores_de_fabrica_vuelven_a_deshabilitar_la_direccion(dialogo):
	_elegir(dialogo, "personalizada")
	dialogo.restablecer_pagina(dialogo.libro.GetSelection())
	assert dialogo.control_de("actualizaciones.fuente").GetSelection() == 0
	assert not dialogo.control_de("actualizaciones.url_personalizada").IsEnabled()


def test_personalizada_sin_direccion_no_se_guarda_y_el_foco_va_al_campo(dialogo):
	"""2.0.1: con «Una dirección personalizada» la dirección es obligatoria."""
	_elegir(dialogo, "personalizada")
	direccion = dialogo.control_de("actualizaciones.url_personalizada")
	direccion.SetValue("   ")
	assert not dialogo.aplicar()
	assert dialogo.avisos and "https://" in dialogo.avisos[-1] and "otro origen" in dialogo.avisos[-1]
	assert dialogo._config.obtener("actualizaciones.fuente") == "servidor"  # noqa: SLF001
	assert procesar_eventos(lambda: wx.Window.FindFocus() is direccion, 2)


def test_direccion_con_usuario_o_contrasena_no_vale():
	from app.core.configuracion import comprobar_url_https

	for url in ("https://ana:secreto@espejo.ejemplo.org/version.json", "https://ana@espejo.ejemplo.org/version.json"):
		motivo = comprobar_url_https(url)
		assert motivo and "usuario ni contraseña" in motivo
	assert comprobar_url_https(URL) is None
	assert comprobar_url_https("") is None
	config = Configuracion()
	with pytest.raises((ValueError, TypeError)):
		config.establecer("actualizaciones.url_personalizada", "https://u:p@espejo.ejemplo.org/version.json")
