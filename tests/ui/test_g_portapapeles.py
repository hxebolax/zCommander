# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque G: portapapeles con el formato del Explorador (sección 17.1, parte G).

- Copiar deja ``CF_HDROP`` con «Preferred DropEffect» 1; cortar, 2.
- Pegar desde un ``CF_HDROP`` lanza una ``OperacionCopiar`` (mover si se cortó).

El portapapeles real se guarda antes de cada prueba y se devuelve al terminar.
"""

from __future__ import annotations

import struct
import sys

import pytest

from tests.ui import g_comun

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Solo Windows")
wx = pytest.importorskip("wx")


@pytest.fixture(autouse=True)
def portapapeles_guardado():
	guardado = g_comun.guardar_portapapeles()
	yield
	g_comun.restaurar_portapapeles(guardado)


@pytest.fixture
def config():
	from app.core.configuracion import Configuracion

	return Configuracion()


@pytest.fixture
def origen(tmp_path):
	carpeta = tmp_path / "origen"
	carpeta.mkdir()
	(carpeta / "uno.txt").write_text("1", encoding="utf-8")
	(carpeta / "año ñ.md").write_text("22", encoding="utf-8")
	(carpeta / "sub").mkdir()
	return carpeta


@pytest.fixture
def destino(tmp_path):
	carpeta = tmp_path / "destino"
	carpeta.mkdir()
	return carpeta


def _hdrop_y_efecto() -> tuple[list[str], int | None]:
	"""Lee el portapapeles en crudo (sin pasar por ``leer_archivos``)."""
	import win32clipboard
	import win32con

	from app.services.windows import portapapeles

	with portapapeles._abierto():
		assert win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP)
		rutas = portapapeles._leer_hdrop(win32clipboard)
		formato = win32clipboard.RegisterClipboardFormat("Preferred DropEffect")
		efecto = None
		if win32clipboard.IsClipboardFormatAvailable(formato):
			efecto = struct.unpack_from("<I", win32clipboard.GetClipboardData(formato))[0]
	return rutas, efecto


def _poner_hdrop_a_mano(rutas: list[str], efecto: int | None) -> None:
	"""Pone archivos como lo haría el Explorador, sin usar el servicio que se prueba."""
	import win32clipboard
	import win32con

	from app.services.windows import portapapeles

	bloque = struct.pack("<IiiII", 20, 0, 0, 0, 1) + ("".join(r + "\0" for r in rutas) + "\0").encode("utf-16-le")
	with portapapeles._abierto():
		win32clipboard.EmptyClipboard()
		win32clipboard.SetClipboardData(win32con.CF_HDROP, bloque)
		if efecto is not None:
			win32clipboard.SetClipboardData(win32clipboard.RegisterClipboardFormat("Preferred DropEffect"), struct.pack("<I", efecto))


def _ultimos_anuncios(n: int = 3) -> list[str]:
	from app.ui import anuncios

	return [a.texto for a in anuncios.historial()[-n:]]


# ── Servicio ─────────────────────────────────────────────────────────────────

def test_bloque_dropfiles_ida_y_vuelta():
	from app.services.windows import portapapeles

	rutas = [r"C:\uno.txt", r"D:\carpeta con espacios\año ñ.md"]
	datos = portapapeles.datos_hdrop(rutas)
	assert struct.unpack_from("<I", datos)[0] == 20
	assert portapapeles.rutas_de_hdrop(datos) == rutas


def test_poner_y_leer_archivos(origen):
	from app.services.windows import portapapeles

	rutas = [str(origen / "uno.txt"), str(origen / "año ñ.md")]
	portapapeles.poner_archivos(rutas)
	leido = portapapeles.leer_archivos()
	assert leido is not None and list(leido.rutas) == rutas and not leido.mover
	portapapeles.poner_archivos(rutas[:1], mover=True)
	leido = portapapeles.leer_archivos()
	assert leido.mover and list(leido.rutas) == rutas[:1]


def test_efecto_del_explorador_al_copiar_no_mueve(origen):
	"""El Explorador pone 5 (copiar y enlazar) al copiar: pegar copia."""
	from app.services.windows import portapapeles

	_poner_hdrop_a_mano([str(origen / "uno.txt")], 5)
	assert not portapapeles.leer_archivos().mover
	_poner_hdrop_a_mano([str(origen / "uno.txt")], None)
	assert not portapapeles.leer_archivos().mover


def test_vaciar_solo_si_no_cambio(origen):
	from app.services.windows import portapapeles

	portapapeles.poner_archivos([str(origen / "uno.txt")], mover=True)
	leido = portapapeles.leer_archivos()
	portapapeles.poner_texto("otra cosa")
	assert not portapapeles.vaciar_si_no_cambio(leido.secuencia)
	assert portapapeles.leer_texto() == "otra cosa"
	portapapeles.poner_archivos([str(origen / "uno.txt")], mover=True)
	leido = portapapeles.leer_archivos()
	assert portapapeles.vaciar_si_no_cambio(leido.secuencia)
	assert portapapeles.leer_archivos() is None


# ── Órdenes ─────────────────────────────────────────────────────────────────────

def test_copiar_deja_cf_hdrop_con_efecto_copiar(config, origen):
	from app.ui.acciones import windows_g

	entradas = [g_comun.entrada(origen / "uno.txt"), g_comun.entrada(origen / "sub")]
	panel = g_comun.PanelFalso(origen, entradas)
	ventana = g_comun.VentanaFalsa(config)
	windows_g.portapapeles_copiar(g_comun.contexto(ventana, panel))
	rutas, efecto = _hdrop_y_efecto()
	assert rutas == [str(origen / "uno.txt"), str(origen / "sub")]
	assert efecto == 1
	assert "2 elementos copiados al portapapeles" in _ultimos_anuncios()


def test_cortar_deja_cf_hdrop_con_efecto_mover(config, origen):
	from app.ui.acciones import windows_g

	panel = g_comun.PanelFalso(origen, [g_comun.entrada(origen / "uno.txt")])
	windows_g.portapapeles_cortar(g_comun.contexto(g_comun.VentanaFalsa(config), panel))
	rutas, efecto = _hdrop_y_efecto()
	assert rutas == [str(origen / "uno.txt")]
	assert efecto == 2
	assert "1 elemento cortado al portapapeles" in _ultimos_anuncios()


def test_copiar_sin_elementos_avisa(config, origen):
	from app.ui.acciones import windows_g

	panel = g_comun.PanelFalso(origen, [])
	windows_g.portapapeles_copiar(g_comun.contexto(g_comun.VentanaFalsa(config), panel))
	assert "No hay elementos para copiar" in _ultimos_anuncios()


def test_pegar_desde_cf_hdrop_lanza_operacion_copiar(config, origen, destino):
	from app.services.operaciones.copiar import OperacionCopiar
	from app.ui.acciones import windows_g

	_poner_hdrop_a_mano([str(origen / "uno.txt"), str(origen / "año ñ.md")], 5)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(destino, [], ventana)
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	assert len(ventana.lanzadas) == 1
	operacion, en_cola, al_terminar = ventana.lanzadas[0]
	assert isinstance(operacion, OperacionCopiar)
	assert not operacion.mover and not en_cola and al_terminar is None
	assert operacion.carpeta_destino == str(destino)
	assert operacion.origen.esquema == "local"
	assert sorted(e.nombre for e in operacion.entradas) == sorted(["uno.txt", "año ñ.md"])


def test_pegar_lo_cortado_mueve_y_vacia_el_portapapeles(config, origen, destino):
	from app.services.operaciones.copiar import OperacionCopiar
	from app.services.windows import portapapeles
	from app.ui.acciones import windows_g

	_poner_hdrop_a_mano([str(origen / "uno.txt")], 2)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(destino, [], ventana)
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	operacion, _en_cola, al_terminar = ventana.lanzadas[0]
	assert isinstance(operacion, OperacionCopiar) and operacion.mover
	# La operación termina bien: como en el Explorador, el portapapeles se vacía.
	terminada = type("Op", (), {"estado": type("E", (), {"value": "terminada"})()})()
	al_terminar(terminada)
	assert portapapeles.leer_archivos() is None


def test_pegar_en_la_misma_carpeta_duplica(config, origen):
	from app.ui.acciones import windows_g

	_poner_hdrop_a_mano([str(origen / "uno.txt")], 1)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(origen, [], ventana)
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	operacion = ventana.lanzadas[0][0]
	assert operacion.nombre_nuevo == "uno (copia).txt"
	assert operacion.carpeta_destino == str(origen)


def test_mover_a_la_misma_carpeta_no_hace_nada(config, origen):
	from app.ui.acciones import windows_g

	_poner_hdrop_a_mano([str(origen / "uno.txt")], 2)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(origen, [], ventana)
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	assert ventana.lanzadas == []
	assert "1 elemento ya está en esta carpeta" in _ultimos_anuncios()


def test_pegar_omite_lo_que_ya_no_existe(config, origen, destino):
	from app.ui.acciones import windows_g

	_poner_hdrop_a_mano([str(origen / "uno.txt"), str(origen / "no existe.txt")], 1)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(destino, [], ventana)
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	assert [e.nombre for e in ventana.lanzadas[0][0].entradas] == ["uno.txt"]
	assert "1 elemento ya no existe y se omite" in _ultimos_anuncios()


def test_pegar_sin_archivos_avisa(config, destino):
	from app.services.windows import portapapeles
	from app.ui.acciones import windows_g

	portapapeles.poner_texto("hola")
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(destino, [], ventana)
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	assert ventana.lanzadas == []
	assert "El portapapeles no tiene archivos" in _ultimos_anuncios()


def test_pegar_ruta_de_texto_va_a_esa_carpeta(config, origen, destino):
	from app.services.windows import portapapeles
	from app.ui.acciones import windows_g

	config.establecer("general.pegar_ruta_del_portapapeles", True)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(destino, [], ventana)
	portapapeles.poner_texto(f'"{origen}"')
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	portapapeles.poner_texto(str(origen / "uno.txt"))
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	assert panel.idas == [(str(origen), None), (str(origen), "uno.txt")]


def test_pegar_en_lista_de_resultados_no_se_puede(config, origen, destino):
	from app.ui.acciones import windows_g

	_poner_hdrop_a_mano([str(origen / "uno.txt")], 1)
	ventana = g_comun.VentanaFalsa(config)
	panel = g_comun.PanelFalso(destino, [], ventana)
	panel.lista_resultados = "Búsqueda"
	windows_g.portapapeles_pegar(g_comun.contexto(ventana, panel))
	assert ventana.lanzadas == []
	assert "No se puede pegar en una lista de resultados" in _ultimos_anuncios()
