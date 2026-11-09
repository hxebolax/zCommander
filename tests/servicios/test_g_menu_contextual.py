# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque G: menú contextual del Explorador construido sin mostrarlo (sección 17.1, parte G)."""

from __future__ import annotations

import ctypes
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Solo Windows")


@pytest.fixture
def archivos(tmp_path):
	carpeta = tmp_path / "menu"
	carpeta.mkdir()
	uno = carpeta / "uno.txt"
	dos = carpeta / "dos.txt"
	uno.write_text("1", encoding="utf-8")
	dos.write_text("2", encoding="utf-8")
	otra = tmp_path / "otra"
	otra.mkdir()
	tres = otra / "tres.txt"
	tres.write_text("3", encoding="utf-8")
	return uno, dos, tres


def test_menu_de_un_archivo_local_se_construye(archivos):
	from app.services.windows import menu_contextual

	with menu_contextual.MenuContextual([str(archivos[0])], 0) as menu:
		assert menu.hmenu
		elementos = menu.elementos()
		assert elementos, "El menú del shell no tiene elementos"
		verbos = {e.verbo.casefold() for e in elementos if e.verbo}
		assert "properties" in verbos
		assert menu.identificador_de("properties") > 0
		assert all(e.texto or e.separador or e.submenu or e.identificador for e in elementos)
	# Cerrar dos veces no falla (el «with» ya cerró).
	menu.cerrar()
	assert menu.hmenu == 0


def test_menu_de_varios_archivos_de_la_misma_carpeta(archivos):
	from app.services.windows import menu_contextual

	with menu_contextual.MenuContextual([str(archivos[0]), str(archivos[1])], 0) as menu:
		assert menu.identificador_de("properties") > 0


def test_menu_de_archivos_de_carpetas_distintas(archivos):
	"""Listas de resultados y cesta: el shell recibe los PIDL absolutos desde el escritorio."""
	from app.services.windows import menu_contextual

	with menu_contextual.MenuContextual([str(archivos[0]), str(archivos[2])], 0) as menu:
		assert menu.elementos()


def test_menu_de_una_carpeta(archivos):
	from app.services.windows import menu_contextual

	with menu_contextual.MenuContextual([str(archivos[0].parent)], 0) as menu:
		assert menu.identificador_de("properties") > 0


def test_rutas_no_validas():
	from app.services.windows import menu_contextual

	with pytest.raises(menu_contextual.ErrorShell):
		menu_contextual.MenuContextual([], 0)
	with pytest.raises(menu_contextual.ErrorShell) as error:
		menu_contextual.MenuContextual(["C:\\" + "a" * 300 + ".txt"], 0)
	assert "259" in error.value.mensaje


def test_ventana_auxiliar_reenvia_los_mensajes_de_los_submenus(archivos):
	"""``WM_INITMENUPOPUP`` llega al shell: «Abrir con» se rellena al abrirse (si el menú lo tiene)."""
	from app.services.windows import menu_contextual

	user32 = ctypes.windll.user32
	user32.GetSubMenu.restype = ctypes.c_void_p
	user32.GetSubMenu.argtypes = [ctypes.c_void_p, ctypes.c_int]
	user32.GetMenuItemCount.argtypes = [ctypes.c_void_p]
	user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_ssize_t]
	user32.SendMessageW.restype = ctypes.c_ssize_t
	with menu_contextual.MenuContextual([str(archivos[0])], 0) as menu:
		menu._crear_auxiliar()
		assert menu._auxiliar
		menu_contextual.MenuContextual._activo = menu
		try:
			crecidos = {}
			for posicion, elemento in enumerate(menu.elementos()):
				if not elemento.submenu:
					continue
				sub = user32.GetSubMenu(menu.hmenu, posicion)
				antes = user32.GetMenuItemCount(sub)
				user32.SendMessageW(menu._auxiliar, menu_contextual.WM_INITMENUPOPUP, sub, posicion)
				crecidos[elemento.texto.replace("&", "").casefold()] = user32.GetMenuItemCount(sub) >= antes
		finally:
			menu_contextual.MenuContextual._activo = None
		assert all(crecidos.values())


def test_mostrar_menu_ejecuta_los_verbos_propios(archivos, monkeypatch):
	"""El verbo elegido que hace zCommander (renombrar) no llega al shell."""
	from app.services.windows import menu_contextual

	llamados = []
	ejecutados = []

	def mostrar(menu, x, y):
		llamados.append((x, y))
		return menu.identificador_de("properties")

	monkeypatch.setattr(menu_contextual.MenuContextual, "mostrar", mostrar)
	monkeypatch.setattr(menu_contextual.MenuContextual, "ejecutar", lambda menu, ident, *a, **k: ejecutados.append(ident))
	verbo = menu_contextual.mostrar_menu([str(archivos[0])], 0, 10, 20, propios={"properties": lambda: llamados.append("propio")})
	assert verbo.casefold() == "properties"
	assert llamados == [(10, 20), "propio"]
	assert ejecutados == []


def test_mostrar_menu_sin_elegir_devuelve_none(archivos, monkeypatch):
	from app.services.windows import menu_contextual

	monkeypatch.setattr(menu_contextual.MenuContextual, "mostrar", lambda menu, x, y: 0)
	assert menu_contextual.mostrar_menu([str(archivos[0])], 0, 0, 0) is None


def test_objeto_de_datos_para_las_propiedades_de_varios(archivos):
	"""``SHMultiFileProperties`` recibe el ``IDataObject`` del shell; aquí solo se obtiene (sin abrir el diálogo)."""
	from app.services.windows import menu_contextual

	api = menu_contextual._cargar_interfaces()
	objetos = menu_contextual._ObjetosShell([str(archivos[0]), str(archivos[1])])
	try:
		datos = objetos.objeto(0, iid=api["IID_IDataObject"])
		assert bool(datos)
		del datos
	finally:
		objetos.cerrar()


def test_propiedades_y_abrir_con_rechazan_rutas_largas():
	from app.services.windows import menu_contextual

	larga = "C:\\" + "b" * 300
	with pytest.raises(menu_contextual.ErrorShell):
		menu_contextual.propiedades([larga], 0)
	with pytest.raises(menu_contextual.ErrorShell):
		menu_contextual.abrir_con(larga, 0)
