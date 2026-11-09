# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de las vistas Información y Vista rápida y del árbol de carpetas.

Con wx real y sin ``MainLoop``: las ventanas se crean SIN mostrarse y las
respuestas de los hilos (``wx.CallAfter``) se atienden con
``procesar_eventos``. Trabajan sobre una carpeta de ``tmp_path``.
"""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from app.core.tareas import GestorTareas  # noqa: E402
from app.services import formato  # noqa: E402
from app.services.vfs.local import ProveedorLocal  # noqa: E402
from app.ui.accesibilidad.revision_teclado import informe, revisar_teclado  # noqa: E402
from app.ui.arbol_carpetas import ArbolCarpetas  # noqa: E402
from app.ui.vistas import VistaInformacion, VistaRapida  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402


@pytest.fixture
def carpeta(tmp_path):
	raiz = tmp_path / "datos"
	(raiz / "uno" / "dos").mkdir(parents=True)
	(raiz / "tres").mkdir()
	(raiz / "texto.txt").write_text("Hola, ñandú y café\nSegunda línea\n", encoding="utf-8")
	(raiz / "binario.bin").write_bytes(bytes(range(256)) * 4)
	return raiz


@pytest.fixture
def tareas():
	gestor = GestorTareas(max_hilos=2, nombre="pruebas_vistas", ejecutor_interfaz=wx.CallAfter)
	yield gestor
	gestor.apagar(espera=2.0)


@pytest.fixture
def marco(app_wx):
	ventana = wx.Frame(None)
	yield ventana
	ventana.Destroy()
	procesar_eventos(segundos=0.05)


def _entrada(proveedor, ruta):
	return proveedor.info(str(ruta))


def _sin_errores(ventana):
	problemas = [p for p in revisar_teclado(ventana) if not p.aviso]
	assert not problemas, informe(problemas)


# ── Vista rápida ─────────────────────────────────────────────────────────────

def test_vista_rapida_muestra_texto_utf8(marco, tareas, carpeta):
	vista = VistaRapida(marco, tareas)
	proveedor = ProveedorLocal()
	vista.mostrar(proveedor, _entrada(proveedor, carpeta / "texto.txt"), 64)
	assert procesar_eventos(lambda: "ñandú" in vista.valor())
	assert "Segunda línea" in vista.valor()
	assert vista.codificacion == "utf-8"


def test_vista_rapida_muestra_hexadecimal_de_binario(marco, tareas, carpeta):
	vista = VistaRapida(marco, tareas)
	proveedor = ProveedorLocal()
	vista.mostrar(proveedor, _entrada(proveedor, carpeta / "binario.bin"), 64)
	assert procesar_eventos(lambda: vista.codificacion == "hexadecimal")
	assert vista.valor().startswith("00000000  00 01 02 03")


def test_vista_rapida_no_lee_carpetas_ni_la_nube_hasta_intro(marco, tareas, carpeta):
	vista = VistaRapida(marco, tareas)
	proveedor = ProveedorLocal()
	vista.mostrar(proveedor, _entrada(proveedor, carpeta / "uno"), 64)
	assert vista.valor().startswith("Carpeta")
	en_nube = _entrada(proveedor, carpeta / "texto.txt").con(en_nube=True)
	vista.mostrar(proveedor, en_nube, 64)
	assert "Pulse Intro" in vista.valor()
	assert vista.hay_pendiente()
	assert vista.leer_pendiente()
	assert procesar_eventos(lambda: "ñandú" in vista.valor())


def test_vista_rapida_descarta_la_peticion_antigua(marco, tareas, carpeta):
	vista = VistaRapida(marco, tareas)
	proveedor = ProveedorLocal()
	vista.mostrar(proveedor, _entrada(proveedor, carpeta / "binario.bin"), 64)
	vista.mostrar(proveedor, _entrada(proveedor, carpeta / "texto.txt"), 64)
	assert procesar_eventos(lambda: "ñandú" in vista.valor())
	# Da tiempo a que llegue cualquier respuesta atrasada: no debe pisar la última.
	procesar_eventos(segundos=0.3)
	assert "ñandú" in vista.valor()


# ── Información ──────────────────────────────────────────────────────────────

def test_vista_informacion_muestra_el_tamano(marco, tareas, carpeta):
	vista = VistaInformacion(marco, tareas)
	proveedor = ProveedorLocal()
	entrada = _entrada(proveedor, carpeta / "binario.bin")
	vista.mostrar(proveedor, entrada, str(carpeta))
	assert procesar_eventos(lambda: "Tamaño" in vista.valor(), segundos=8)
	assert formato.tamano_legible(1024) in vista.valor()
	assert "Nombre: binario.bin" in vista.valor()
	assert "Archivo BIN" in vista.valor() or "Tipo:" in vista.valor()


def test_vista_informacion_sin_elemento(marco, tareas, carpeta):
	vista = VistaInformacion(marco, tareas)
	vista.mostrar(ProveedorLocal(), None, str(carpeta))
	assert procesar_eventos(lambda: vista.valor().startswith("Sin elemento"), segundos=8)


# ── Árbol de carpetas ────────────────────────────────────────────────────────

def test_arbol_ir_a_selecciona_y_intro_elige(marco, tareas, carpeta):
	elegidas: list[str] = []
	proveedor = ProveedorLocal()
	arbol = ArbolCarpetas(marco, "Ár&bol de carpetas:", proveedor, str(carpeta), elegidas.append, tareas, retardo_ms=50)
	destino = proveedor.unir(proveedor.unir(str(carpeta), "uno"), "dos")
	assert arbol.ir_a(destino)
	assert procesar_eventos(lambda: (arbol.ruta_elegida() or "").casefold() == destino.casefold())
	# ir_a no avisa: quien lo llama ya sabe a dónde va.
	procesar_eventos(segundos=0.2)
	assert elegidas == []
	# Intro en el árbol: Windows lo convierte en EVT_TREE_ITEM_ACTIVATED.
	evento = wx.TreeEvent(wx.wxEVT_TREE_ITEM_ACTIVATED, arbol.arbol, arbol.arbol.GetSelection())
	arbol.arbol.GetEventHandler().ProcessEvent(evento)
	assert [r.casefold() for r in elegidas] == [destino.casefold()]


def test_arbol_carga_bajo_demanda_y_refresca(marco, tareas, carpeta):
	proveedor = ProveedorLocal()
	arbol = ArbolCarpetas(marco, "Ár&bol de carpetas:", proveedor, str(carpeta), lambda _r: None, tareas)
	raiz = arbol.arbol.GetFirstChild(arbol.arbol.GetRootItem())[0]

	def hijos(item):
		textos = []
		hijo, cookie = arbol.arbol.GetFirstChild(item)
		while hijo.IsOk():
			textos.append(arbol.arbol.GetItemText(hijo))
			hijo, cookie = arbol.arbol.GetNextChild(item, cookie)
		return textos

	assert procesar_eventos(lambda: hijos(raiz) == ["tres", "uno"])
	(carpeta / "cuatro").mkdir()
	assert arbol.refrescar(str(carpeta))
	assert procesar_eventos(lambda: hijos(raiz) == ["cuatro", "tres", "uno"])


def test_arbol_del_disco_muestra_unidades(marco, tareas):
	from app.services.windows import unidades

	arbol = ArbolCarpetas(marco, "Ár&bol de carpetas:", ProveedorLocal(), "", lambda _r: None, tareas)
	primero = arbol.arbol.GetFirstChild(arbol.arbol.GetRootItem())[0]
	assert primero.IsOk()
	assert arbol.arbol.GetItemText(primero).startswith(unidades.letras()[0])


# ── Teclado ──────────────────────────────────────────────────────────────────

def test_vistas_y_arbol_pasan_la_revision_de_teclado(marco, tareas, carpeta):
	sizer = wx.BoxSizer(wx.VERTICAL)
	for control in (
		VistaInformacion(marco, tareas),
		VistaRapida(marco, tareas),
		ArbolCarpetas(marco, "Ár&bol de carpetas:", ProveedorLocal(), str(carpeta), lambda _r: None, tareas),
	):
		sizer.Add(control, 1, wx.EXPAND)
		_sin_errores(control)
	marco.SetSizer(sizer)
	_sin_errores(marco)


def test_arbol_elige_tras_la_pausa_al_mover_la_seleccion(marco, tareas, carpeta):
	elegidas: list[str] = []
	proveedor = ProveedorLocal()
	arbol = ArbolCarpetas(marco, "Ár&bol de carpetas:", proveedor, str(carpeta), elegidas.append, tareas, retardo_ms=50)
	tres = proveedor.unir(str(carpeta), "tres")
	assert procesar_eventos(lambda: arbol._items.get(arbol._clave(tres)) is not None)
	# Selección hecha como la haría la persona con las flechas (no por el programa).
	arbol.arbol.SelectItem(arbol._items[arbol._clave(tres)])
	assert elegidas == []
	assert procesar_eventos(lambda: bool(elegidas))
	assert [r.casefold() for r in elegidas] == [tres.casefold()]
