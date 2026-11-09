# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque G: propiedades, Abrir con, menú de Windows, consola, Explorador, soltar e iconos.

Los diálogos y menús del shell no se muestran: se sustituyen las funciones del
servicio y se comprueba qué reciben. La integración con la ventana real
comprueba los enganches de cada panel y la preferencia de iconos.
"""

from __future__ import annotations

import sys

import pytest

from tests.conftest import procesar_eventos
from tests.ui import g_comun

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Solo Windows")
wx = pytest.importorskip("wx")


@pytest.fixture
def config():
	from app.core.configuracion import Configuracion

	return Configuracion()


@pytest.fixture
def carpeta(tmp_path):
	base = tmp_path / "trabajo"
	base.mkdir()
	(base / "uno.txt").write_text("1", encoding="utf-8")
	(base / "dos.md").write_text("22", encoding="utf-8")
	(base / "sub").mkdir()
	return base


def _anuncios(n: int = 3) -> list[str]:
	from app.ui import anuncios

	return [a.texto for a in anuncios.historial()[-n:]]


# ── Propiedades, Abrir con y menú de Windows ─────────────────────────────────────

def test_propiedades_de_los_elementos_y_de_la_carpeta(config, carpeta, monkeypatch):
	from app.services.windows import menu_contextual
	from app.ui.acciones import windows_g

	pedidas = []
	monkeypatch.setattr(menu_contextual, "propiedades", lambda rutas, hwnd: pedidas.append(list(rutas)))
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(carpeta, [g_comun.entrada(carpeta / "uno.txt"), g_comun.entrada(carpeta / "dos.md")], ventana)
	windows_g.propiedades(g_comun.contexto(ventana, panel))
	vacio = g_comun.PanelFalso(carpeta, [], ventana)
	windows_g.propiedades(g_comun.contexto(ventana, vacio))
	assert pedidas == [[str(carpeta / "uno.txt"), str(carpeta / "dos.md")], [str(carpeta)]]


def test_propiedades_con_error_del_shell_avisa(config, carpeta, monkeypatch):
	from app.services.windows import menu_contextual
	from app.ui.acciones import windows_g

	def falla(rutas, hwnd):
		raise menu_contextual.ErrorShell("Windows no pudo abrir las propiedades: prueba")

	monkeypatch.setattr(menu_contextual, "propiedades", falla)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(carpeta, [g_comun.entrada(carpeta / "uno.txt")], ventana)
	windows_g.propiedades(g_comun.contexto(ventana, panel))
	assert "Windows no pudo abrir las propiedades: prueba" in _anuncios()


def test_abrir_con_solo_archivos(config, carpeta, monkeypatch):
	from app.services.windows import menu_contextual
	from app.ui.acciones import windows_g

	abiertos = []
	monkeypatch.setattr(menu_contextual, "abrir_con", lambda ruta, hwnd: abiertos.append(ruta) or True)
	ventana = g_comun.VentanaFalsa(config)
	windows_g.abrir_con(g_comun.contexto(ventana, g_comun.PanelFalso(carpeta, [g_comun.entrada(carpeta / "uno.txt")], ventana)))
	windows_g.abrir_con(g_comun.contexto(ventana, g_comun.PanelFalso(carpeta, [g_comun.entrada(carpeta / "sub")], ventana)))
	assert abiertos == [str(carpeta / "uno.txt")]
	assert "Abrir con solo se puede usar con un archivo" in _anuncios()


def test_menu_windows_junto_al_cursor_y_refresca(config, carpeta, monkeypatch):
	from app.services.windows import menu_contextual
	from app.ui.acciones import windows_g

	pedidos = []

	def mostrar_menu(rutas, hwnd, x, y, extendido=False, propios=None):
		pedidos.append((list(rutas), x, y, sorted(propios or {})))
		return "copy"

	monkeypatch.setattr(menu_contextual, "mostrar_menu", mostrar_menu)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(carpeta, [g_comun.entrada(carpeta / "uno.txt")], ventana)
	windows_g.menu_windows(g_comun.contexto(ventana, panel))
	assert pedidos == [([str(carpeta / "uno.txt")], 100, 200, ["rename"])]
	assert panel.refrescos == 1
	assert "1 elemento copiado al portapapeles" in _anuncios()


def test_menu_windows_cambiar_nombre_lo_hace_zcommander(app_wx, config, carpeta, monkeypatch):
	from app.services.windows import menu_contextual
	from app.ui.acciones import windows_g

	def mostrar_menu(rutas, hwnd, x, y, extendido=False, propios=None):
		propios["rename"]()
		return "rename"

	monkeypatch.setattr(menu_contextual, "mostrar_menu", mostrar_menu)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(carpeta, [g_comun.entrada(carpeta / "uno.txt")], ventana)
	windows_g.menu_windows(g_comun.contexto(ventana, panel))
	procesar_eventos(lambda: bool(ventana.ordenes), 2)
	assert ventana.ordenes == ["renombrar"]
	assert panel.refrescos == 0


def test_menu_windows_real_se_construye_sin_mostrarse(app_wx, config, carpeta, monkeypatch):
	"""Con el shell de verdad: se cierra sin elegir (``TrackPopupMenu`` devuelve 0)."""
	from app.services.windows import menu_contextual
	from app.ui.acciones import windows_g

	vistos = []

	def mostrar(menu, x, y):
		vistos.append(menu.identificador_de("properties"))
		return 0

	monkeypatch.setattr(menu_contextual.MenuContextual, "mostrar", mostrar)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(carpeta, [g_comun.entrada(carpeta / "uno.txt")], ventana)
	windows_g.menu_windows(g_comun.contexto(ventana, panel))
	assert vistos and vistos[0] > 0
	assert panel.refrescos == 0


# ── Consola y Explorador ────────────────────────────────────────────────────────

def test_consola_con_el_programa_configurado(config, carpeta, monkeypatch):
	from app.services import linea_ordenes
	from app.ui.acciones import windows_g

	abiertas = []
	monkeypatch.setattr(linea_ordenes, "abrir_consola", lambda carpeta_, programa="cmd": abiertas.append((carpeta_, programa)))
	config.establecer("general.consola", "powershell")
	ventana = g_comun.VentanaFalsa(config)
	windows_g.consola(g_comun.contexto(ventana, g_comun.PanelFalso(carpeta, [], ventana)))
	assert abiertas == [(str(carpeta), "powershell")]


def test_consola_avisa_si_falla(config, carpeta, monkeypatch):
	from app.services import linea_ordenes
	from app.ui.acciones import windows_g

	def falla(carpeta_, programa="cmd"):
		raise FileNotFoundError(2, "No se encuentra el programa")

	monkeypatch.setattr(linea_ordenes, "abrir_consola", falla)
	ventana = g_comun.VentanaFalsa(config)
	windows_g.consola(g_comun.contexto(ventana, g_comun.PanelFalso(carpeta, [], ventana)))
	assert "No se pudo abrir la consola: No se encuentra el programa" in _anuncios()


def test_explorador_selecciona_el_cursor(config, carpeta, monkeypatch):
	from app.services.windows import shell_basico
	from app.ui.acciones import windows_g

	abiertos = []
	monkeypatch.setattr(shell_basico, "explorador", lambda carpeta_, seleccionar=None: abiertos.append((carpeta_, seleccionar)))
	ventana = g_comun.VentanaFalsa(config)
	windows_g.explorador(g_comun.contexto(ventana, g_comun.PanelFalso(carpeta, [g_comun.entrada(carpeta / "uno.txt")], ventana)))
	windows_g.explorador(g_comun.contexto(ventana, g_comun.PanelFalso(carpeta, [], ventana)))
	assert abiertos == [(str(carpeta), str(carpeta / "uno.txt")), (str(carpeta), None)]


# ── Soltar ──────────────────────────────────────────────────────────────────────────

def test_soltar_con_mayusculas_mueve_con_el_motor(config, carpeta, tmp_path):
	from app.services.operaciones.copiar import OperacionCopiar
	from app.ui.acciones import windows_g

	destino = tmp_path / "destino"
	destino.mkdir()
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(destino, [], ventana)
	windows_g.soltar_en(panel, [str(carpeta / "uno.txt"), str(carpeta / "sub")], mover=True)
	operacion = ventana.lanzadas[0][0]
	assert isinstance(operacion, OperacionCopiar) and operacion.mover
	assert operacion.carpeta_destino == str(destino)
	windows_g.soltar_en(panel, [str(carpeta / "uno.txt")], mover=False)
	assert not ventana.lanzadas[1][0].mover


def test_destino_soltar_rechaza_listas_de_resultados(app_wx, config, carpeta):
	from app.ui.acciones import windows_g

	panel = g_comun.PanelFalso(carpeta, [], g_comun.VentanaFalsa(config))
	destino = windows_g.DestinoSoltar(panel)
	assert destino.OnDragOver(0, 0, wx.DragCopy) == wx.DragCopy
	assert destino.OnDragOver(0, 0, wx.DragMove) == wx.DragMove
	panel.lista_resultados = "Búsqueda"
	assert destino.OnDragOver(0, 0, wx.DragCopy) == wx.DragNone


def test_arrastrar_fuera_del_disco_avisa(app_wx, config, carpeta):
	from app.services.vfs import base
	from app.ui.acciones import windows_g

	class ProveedorRemoto:
		def ruta_local(self, ruta):
			return None

	panel = g_comun.PanelFalso(carpeta, [], g_comun.VentanaFalsa(config))
	panel.proveedor = ProveedorRemoto()
	assert windows_g.arrastrar(panel, [base.Entrada("a.txt", "/a.txt")]) == wx.DragNone
	assert "Arrastrar solo está disponible para elementos del disco" in _anuncios()


# ── Ventana real: enganches e iconos ───────────────────────────────────────────────

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
	configuracion = Configuracion()
	configuracion.establecer("general.confirmar_salida", False)
	from app.ui.ventana_principal import VentanaPrincipal

	marco = VentanaPrincipal(configuracion)
	marco.mostrar()
	assert procesar_eventos(lambda: len(marco.izquierdo.panel_actual().entradas()) >= 4, 10)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


def test_cada_panel_tiene_arrastrar_y_soltar(ventana):
	from app.ui.acciones import windows_g

	for panel in ventana.todos_los_paneles():
		lista = panel.lista()
		assert isinstance(lista.GetDropTarget(), windows_g.DestinoSoltar)
		assert lista._arrastre is not None


def test_iconos_se_activan_y_desactivan_al_momento(ventana):
	from app.ui.acciones import windows_g

	panel = ventana.izquierdo.panel_actual()
	lista = panel.lista()
	assert lista.GetImageList(wx.IMAGE_LIST_SMALL) is None
	ventana.config.establecer("paneles.iconos", True)
	assert procesar_eventos(lambda: lista.GetImageList(wx.IMAGE_LIST_SMALL) is not None, 3)
	gestor = windows_g._gestor_iconos(ventana)
	indice_txt = next(i for i, e in enumerate(lista.entradas()) if e.nombre == "uno.txt")
	indice_sub = next(i for i, e in enumerate(lista.entradas()) if e.nombre == "sub")
	lista.OnGetItemImage(indice_txt)
	lista.OnGetItemImage(indice_sub)
	assert procesar_eventos(lambda: "txt" in gestor.iconos and "<carpeta>" in gestor.iconos, 5)
	assert lista.OnGetItemImage(indice_txt) >= 0
	assert lista.OnGetItemImage(indice_sub) >= 0
	assert lista.OnGetItemImage(indice_sub) != lista.OnGetItemImage(indice_txt)
	ventana.config.establecer("paneles.iconos", False)
	assert procesar_eventos(lambda: lista.GetImageList(wx.IMAGE_LIST_SMALL) is None, 3)
	assert lista.OnGetItemImage(indice_txt) == -1


def test_pegar_en_la_ventana_real_lanza_la_copia(ventana, carpeta, monkeypatch):
	from app.services.operaciones.copiar import OperacionCopiar
	from app.services.windows import portapapeles

	guardado = g_comun.guardar_portapapeles()
	try:
		lanzadas = []
		monkeypatch.setattr(ventana, "lanzar_operacion", lambda op, en_cola=False, al_terminar=None: lanzadas.append(op))
		portapapeles.poner_archivos([str(carpeta / "uno.txt")])
		destino = ventana.derecho.panel_actual()
		destino.enfocar()
		ventana.ejecutar_orden("portapapeles_pegar", "derecho")
		assert procesar_eventos(lambda: bool(lanzadas), 5)
		assert isinstance(lanzadas[0], OperacionCopiar)
		assert lanzadas[0].carpeta_destino == str(carpeta / "sub")
	finally:
		g_comun.restaurar_portapapeles(guardado)


def test_menu_windows_en_la_ventana_real_junto_al_cursor(ventana, carpeta, monkeypatch):
	from app.services.windows import menu_contextual

	vistos = []

	def mostrar(menu, x, y):
		vistos.append((list(menu.rutas), x, y))
		return 0

	monkeypatch.setattr(menu_contextual.MenuContextual, "mostrar", mostrar)
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.ir_a_nombre("uno.txt")
	ventana.ejecutar_orden("menu_windows")
	assert len(vistos) == 1
	rutas, x, y = vistos[0]
	assert rutas == [str(carpeta / "uno.txt")]
	lista = panel.lista()
	origen = lista.ClientToScreen(wx.Point(0, 0))
	assert x >= origen.x and y >= origen.y
