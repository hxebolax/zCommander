# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana principal completa: construcción, navegación, marcas, orden, despachador y menús."""

from __future__ import annotations

import importlib

import pytest

from tests.conftest import procesar_eventos

wx = pytest.importorskip("wx")


@pytest.fixture
def carpeta(tmp_path):
	base = tmp_path / "trabajo"
	base.mkdir()
	(base / "uno.txt").write_text("1", encoding="utf-8")
	(base / "dos.md").write_text("22", encoding="utf-8")
	(base / "tres.txt").write_text("333", encoding="utf-8")
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
	assert procesar_eventos(lambda: len(marco.izquierdo.panel_actual().entradas()) >= 4, 10)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


def test_lista_y_etiqueta(ventana, carpeta):
	panel = ventana.izquierdo.panel_actual()
	nombres = [e.nombre for e in panel.entradas()]
	assert nombres[0] == ".."
	assert nombres[1] == "sub"
	assert set(nombres[2:]) == {"uno.txt", "dos.md", "tres.txt"}
	assert str(carpeta) in panel.etiqueta.GetLabel()


def test_entrar_y_subir(ventana, carpeta):
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.ir_a_nombre("sub")
	ventana.ejecutar_orden("abrir")
	assert procesar_eventos(lambda: panel.ruta.endswith("sub"), 5)
	ventana.ejecutar_orden("subir")
	assert procesar_eventos(lambda: panel.ruta == str(carpeta), 5)
	assert panel.cursor().nombre == "sub"


def test_marcar_conserva_marcas_y_cambia_modo(ventana):
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	lista = panel.lista_archivos
	panel.ir_a_nombre("uno.txt")
	assert not lista.multiple
	ventana.ejecutar_orden("marcar")
	assert lista.multiple
	assert [e.nombre for e in panel.marcadas()] == ["uno.txt"]
	lista.mover_cursor(lista.cursor_indice() + 1)
	assert [e.nombre for e in panel.marcadas()] == ["uno.txt"]
	assert lista.GetSelectedItemCount() == 1
	ventana.ejecutar_orden("desmarcar_todo")
	assert not lista.multiple and not panel.marcadas()


def test_ordenar_y_marcar_extension(ventana):
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	ventana.ejecutar_orden("ordenar_tamano")
	procesar_eventos(lambda: False, 0.2)
	panel.ir_a_nombre("uno.txt")
	ventana.ejecutar_orden("marcar_extension")
	assert {e.nombre for e in panel.marcadas()} == {"uno.txt", "tres.txt"}


def test_todas_las_ordenes_tienen_manejador():
	from app.ui import ordenes

	for orden in ordenes.CATALOGO:
		modulo, funcion = orden.manejador.rsplit(".", 1)
		assert hasattr(importlib.import_module(f"app.ui.acciones.{modulo}"), funcion), orden.id
		if orden.estado:
			modulo, funcion = orden.estado.rsplit(".", 1)
			assert hasattr(importlib.import_module(f"app.ui.acciones.{modulo}"), funcion), orden.id


def test_menus_sin_letras_repetidas():
	from tools.comprobar_menus import problemas

	assert problemas() == []


def test_despachador_respeta_la_linea_de_ordenes(ventana):
	ventana.linea.SetFocus()
	ambitos, tipo = ventana._ambitos(ventana.linea)  # noqa: SLF001 - prueba del despachador
	assert tipo == "linea" and "panel" not in ambitos
	panel = ventana.izquierdo.panel_actual()
	ambitos, tipo = ventana._ambitos(panel.lista_archivos)  # noqa: SLF001
	assert tipo == "lista" and "panel" in ambitos


def test_cambiar_panel_y_sesion(ventana, carpeta):
	ventana.izquierdo.panel_actual().enfocar()
	ventana.ejecutar_orden("cambiar_panel")
	procesar_eventos(lambda: False, 0.2)
	datos = ventana.datos_sesion()
	assert datos["lados"]["izquierdo"]["pestanas"][0]["ruta"] == str(carpeta)
	assert datos["lados"]["derecho"]["pestanas"][0]["ruta"] == str(carpeta / "sub")


def test_f5_copia_al_otro_panel(ventana, carpeta, monkeypatch):
	"""De la orden al motor: diálogo de copiar (aceptado sin mostrarlo) y copia real."""
	from app.ui.dialogos.copiar import DialogoCopiar

	monkeypatch.setattr(DialogoCopiar, "ShowModal", lambda self: wx.ID_OK)
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.ir_a_nombre("uno.txt")
	ventana.ejecutar_orden("copiar")
	destino = carpeta / "sub" / "uno.txt"
	assert procesar_eventos(destino.exists, 10)
	assert destino.read_text(encoding="utf-8") == "1"


def test_f6_mueve_al_otro_panel(ventana, carpeta, monkeypatch):
	from app.ui.dialogos.copiar import DialogoCopiar

	monkeypatch.setattr(DialogoCopiar, "ShowModal", lambda self: wx.ID_OK)
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.ir_a_nombre("tres.txt")
	ventana.ejecutar_orden("mover")
	assert procesar_eventos(lambda: (carpeta / "sub" / "tres.txt").exists() and not (carpeta / "tres.txt").exists(), 10)


def test_al_entrar_en_otra_carpeta_el_cursor_va_arriba(ventana, carpeta):
	"""Entrar en una carpeta deja el cursor en la primera fila, no en el número de fila de la anterior."""
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	assert panel.ir_a_nombre("sub")
	assert panel.lista_archivos.cursor_indice() == 1  # «..» es la fila 0
	ventana.ejecutar_orden("abrir")
	assert procesar_eventos(lambda: panel.ruta.endswith("sub"), 5)
	assert panel.lista_archivos.cursor_indice() == 0
	assert panel.cursor().es_superior


def test_volver_a_leer_conserva_el_cursor(ventana):
	"""Ctrl+R en la misma carpeta no mueve el cursor (solo cambia al entrar en otra)."""
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	assert panel.ir_a_nombre("tres.txt")
	terminado = []
	panel.refrescar(al_terminar=terminado.append)
	assert procesar_eventos(lambda: bool(terminado), 5)
	assert panel.cursor().nombre == "tres.txt"
