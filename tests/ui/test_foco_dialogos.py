# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""2.0.1: título de la ventana y lado activo al volver de un diálogo, con la ``VentanaPrincipal`` real.

Al cerrar un diálogo modal, Windows devuelve el foco a la ventana y a veces lo deja en la
lista del otro lado; su ``EVT_SET_FOCUS`` convertía ese lado en el activo y el título
seguía diciendo la carpeta del otro. Aquí se simula: se desactiva la ventana (se abre el
diálogo), el foco «cae» en el otro panel y se reactiva.
"""

from __future__ import annotations

import pytest

from tests.conftest import procesar_eventos

wx = pytest.importorskip("wx")


@pytest.fixture
def carpeta(tmp_path):
	base = tmp_path / "trabajo"
	base.mkdir()
	(base / "uno.txt").write_text("1", encoding="utf-8")
	(base / "dos.md").write_text("22", encoding="utf-8")
	(base / "sub").mkdir()
	(base / "sub" / "dentro.txt").write_text("x", encoding="utf-8")
	return base


@pytest.fixture
def ventana(app_wx, carpeta, monkeypatch):
	from app.core.configuracion import Configuracion
	from app.services import sesion

	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {
			"izquierdo": {"pestanas": [sesion.pestana(ruta=str(carpeta))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(carpeta / "sub"))], "actual": 0},
		},
	})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	from app.ui.ventana_principal import VentanaPrincipal

	marco = VentanaPrincipal(config)
	marco.mostrar()
	assert procesar_eventos(lambda: len(marco.izquierdo.panel_actual().entradas()) >= 3
		and len(marco.derecho.panel_actual().entradas()) >= 2, 10)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


def _titulo(panel) -> str:
	from app.core.version import NOMBRE_APLICACION

	return f"{panel.mostrar_ruta()} - {NOMBRE_APLICACION}"


def _activar(ventana, activa: bool) -> None:
	"""Lo que hace Windows al abrir (False) o cerrar (True) un diálogo modal."""
	ventana._al_activar(wx.ActivateEvent(wx.wxEVT_ACTIVATE, activa))  # noqa: SLF001 - se simula la activación


def _foco_en(monkeypatch, control) -> None:
	"""Fija lo que devuelve ``FindFocus``: sin ventana en primer plano, el foco real no es fiable."""
	monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: control))


def _empezar_en_izquierdo(ventana):
	izquierdo, derecho = ventana.izquierdo.panel_actual(), ventana.derecho.panel_actual()
	izquierdo.enfocar()
	ventana.panel_enfocado(izquierdo)
	procesar_eventos(lambda: False, 0.1)
	assert ventana._activo == "izquierdo"  # noqa: SLF001
	return izquierdo, derecho


def test_el_titulo_sigue_al_panel_activo(ventana):
	izquierdo, derecho = ventana.izquierdo.panel_actual(), ventana.derecho.panel_actual()
	ventana.panel_enfocado(derecho)
	assert ventana.GetTitle() == _titulo(derecho)
	ventana.panel_enfocado(izquierdo)
	assert ventana.GetTitle() == _titulo(izquierdo)


def test_el_titulo_sigue_a_la_carpeta_del_activo_y_no_a_la_del_otro(ventana, carpeta):
	izquierdo, derecho = _empezar_en_izquierdo(ventana)
	derecho.ir_a(str(carpeta))
	assert procesar_eventos(lambda: derecho.ruta == str(carpeta), 5)
	assert ventana.GetTitle() == _titulo(izquierdo)
	izquierdo.ir_a(str(carpeta / "sub"))
	assert procesar_eventos(lambda: ventana.GetTitle() == _titulo(izquierdo) and izquierdo.ruta.endswith("sub"), 5)


def test_tras_el_dialogo_vuelve_al_lado_que_estaba_activo(ventana, monkeypatch):
	izquierdo, derecho = _empezar_en_izquierdo(ventana)
	_activar(ventana, False)
	# Al cerrarse el diálogo, el foco cae en la lista del otro lado y la convierte en activa.
	ventana.panel_enfocado(derecho)
	assert ventana._activo == "derecho"  # noqa: SLF001
	_foco_en(monkeypatch, derecho.lista_archivos)
	_activar(ventana, True)
	assert procesar_eventos(lambda: ventana._activo == "izquierdo", 3)  # noqa: SLF001
	assert ventana.GetTitle() == _titulo(izquierdo)


def test_un_enfocar_explicito_del_otro_panel_se_respeta(ventana, monkeypatch):
	_izquierdo, derecho = _empezar_en_izquierdo(ventana)
	_activar(ventana, False)
	# Una orden mueve el foco al otro panel a propósito mientras el diálogo está abierto.
	derecho.enfocar()
	ventana.panel_enfocado(derecho)
	_foco_en(monkeypatch, derecho.lista_archivos)
	_activar(ventana, True)
	procesar_eventos(lambda: False, 0.3)
	assert ventana._activo == "derecho"  # noqa: SLF001
	assert ventana.GetTitle() == _titulo(derecho)


def test_un_clic_en_el_otro_panel_se_respeta(ventana, monkeypatch):
	_izquierdo, derecho = _empezar_en_izquierdo(ventana)
	_activar(ventana, False)
	derecho._al_pulsar_raton(wx.MouseEvent(wx.wxEVT_LEFT_DOWN))  # noqa: SLF001 - el clic que llega a la lista
	ventana.panel_enfocado(derecho)
	_foco_en(monkeypatch, derecho.lista_archivos)
	_activar(ventana, True)
	procesar_eventos(lambda: False, 0.3)
	assert ventana._activo == "derecho"  # noqa: SLF001


def test_si_el_foco_no_esta_en_una_lista_no_se_toca(ventana, monkeypatch):
	_izquierdo, derecho = _empezar_en_izquierdo(ventana)
	_activar(ventana, False)
	ventana.panel_enfocado(derecho)
	_foco_en(monkeypatch, ventana.linea)
	_activar(ventana, True)
	procesar_eventos(lambda: False, 0.3)
	assert ventana._activo == "derecho"  # noqa: SLF001


def test_sin_dialogo_cambiar_de_panel_sigue_funcionando(ventana):
	_izquierdo, derecho = _empezar_en_izquierdo(ventana)
	ventana.ejecutar_orden("cambiar_panel")
	procesar_eventos(lambda: False, 0.2)
	ventana.panel_enfocado(derecho)
	_activar(ventana, True)
	procesar_eventos(lambda: False, 0.3)
	assert ventana._activo == "derecho"  # noqa: SLF001


def test_devolver_foco_sin_control_previo_va_al_lado_guardado(ventana):
	from app.ui.accesibilidad import dialogos

	izquierdo, derecho = _empezar_en_izquierdo(ventana)
	_activar(ventana, False)
	ventana.panel_enfocado(derecho)
	aplicacion = wx.GetApp()
	anterior = aplicacion.GetTopWindow()
	aplicacion.SetTopWindow(ventana)
	try:
		dialogos.devolver_foco(None)
	finally:
		if anterior:
			aplicacion.SetTopWindow(anterior)
	assert ventana._activo == "izquierdo"  # noqa: SLF001
	assert ventana.GetTitle() == _titulo(izquierdo)


def test_devolver_foco_a_un_control_destruido_no_falla(ventana):
	from app.ui.accesibilidad import dialogos

	efimero = wx.TextCtrl(ventana)
	efimero.Destroy()
	procesar_eventos(lambda: False, 0.1)
	dialogos.devolver_foco(efimero)  # sin excepción


# ── 2.0.1 (revisión) ─────────────────────────────────────────────────────────

def test_una_restauracion_pendiente_no_se_sobrescribe(ventana, monkeypatch):
	"""Se reactiva y se vuelve a desactivar antes de que corra el CallAfter de la restauración."""
	izquierdo, derecho = _empezar_en_izquierdo(ventana)
	_activar(ventana, False)
	ventana.panel_enfocado(derecho)  # el foco cae en el otro lado al cerrar el primer diálogo
	_foco_en(monkeypatch, derecho.lista_archivos)
	_activar(ventana, True)  # su restauración queda pendiente (CallAfter)...
	_activar(ventana, False)  # ...y se abre otro diálogo antes de que corra
	assert ventana._lado_al_desactivar == "izquierdo"  # noqa: SLF001
	_activar(ventana, True)
	assert procesar_eventos(lambda: ventana._activo == "izquierdo", 3)  # noqa: SLF001
	assert ventana.GetTitle() == _titulo(izquierdo)
	assert ventana._lado_al_desactivar is None  # noqa: SLF001


def test_el_foco_en_el_arbol_del_otro_panel_tambien_se_corrige(ventana, monkeypatch):
	_izquierdo, derecho = _empezar_en_izquierdo(ventana)
	derecho.aplicar_vista("arbol")
	assert procesar_eventos(lambda: derecho.vista_actual() is not None, 3)
	vista = derecho.vista_actual()
	control = vista.control_enfocable() if hasattr(vista, "control_enfocable") else vista
	izquierdo = ventana.izquierdo.panel_actual()
	izquierdo.enfocar()
	ventana.panel_enfocado(izquierdo)
	procesar_eventos(lambda: False, 0.1)
	_activar(ventana, False)
	ventana.panel_enfocado(derecho)
	_foco_en(monkeypatch, control)
	_activar(ventana, True)
	assert procesar_eventos(lambda: ventana._activo == "izquierdo", 3)  # noqa: SLF001


def test_devolver_foco_no_actua_con_la_ventana_oculta_o_minimizada(ventana, monkeypatch):
	_izquierdo, derecho = _empezar_en_izquierdo(ventana)
	llamadas: list[str] = []
	for panel in ventana.todos_los_paneles():
		monkeypatch.setattr(panel, "enfocar", lambda p=panel: llamadas.append(p.lado))
	monkeypatch.setattr(ventana, "IsIconized", lambda: True)
	ventana.devolver_foco_panel()
	monkeypatch.setattr(ventana, "IsIconized", lambda: False)
	monkeypatch.setattr(ventana, "IsShown", lambda: False)
	ventana.devolver_foco_panel()
	assert llamadas == []
	monkeypatch.setattr(ventana, "IsShown", lambda: True)
	ventana.devolver_foco_panel()
	assert llamadas == ["izquierdo"]


def test_devolver_foco_con_los_paneles_ocultos_va_a_la_salida(ventana, monkeypatch):
	_empezar_en_izquierdo(ventana)
	llamadas: list[str] = []
	for panel in ventana.todos_los_paneles():
		monkeypatch.setattr(panel, "enfocar", lambda p=panel: llamadas.append(p.lado))
	monkeypatch.setattr(ventana.salida, "enfocar_final", lambda: llamadas.append("salida"))
	ventana.alternar_paneles()
	try:
		llamadas.clear()
		ventana.devolver_foco_panel()
		assert llamadas == ["salida"]
	finally:
		ventana.alternar_paneles()
