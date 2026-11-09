# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Menús del catálogo completo (diseño 2.0, 14.1.1, 14.2 y 18.2)."""

from __future__ import annotations

from app.ui import ordenes


def test_comprobar_menus_sin_problemas_con_el_catalogo_completo():
	from tools import comprobar_menus

	assert comprobar_menus.problemas() == []


def test_mis_ordenes_lleno_y_modo_desarrollo(registro_vacio):
	from tools import comprobar_menus

	registro_vacio.registrar_serie()
	ordenes.fijar_fuente_macros(lambda: [("Fotos a la copia", True, True), ("Limpiar", True, False), ("Oculta", False, True)])
	registro_vacio.fijar_modo_desarrollo(True)
	try:
		titulos = [t for t, _c in ordenes.menus()]
		assert ordenes.TITULO_MIS_ORDENES in titulos
		mis = dict(ordenes.menus())[ordenes.TITULO_MIS_ORDENES]
		assert mis == ["macro:Fotos a la copia", "macro:Limpiar"]
		assert ordenes.POR_ID["macro:Limpiar"].manejador == "personalizar_pe.ejecutar_macro"
		assert "complemento_recargar" in dict(ordenes.menus())[ordenes.TITULO_COMPLEMENTOS]
		assert comprobar_menus.problemas() == []
	finally:
		ordenes.fijar_fuente_macros(None)
		registro_vacio.fijar_modo_desarrollo(False)
	assert "complemento_recargar" not in ordenes.POR_ID


def test_complementos_agrupados_por_categoria_y_sin_anclas():
	"""Cada complemento está entero en su submenú, dentro de su categoría; los menús del núcleo no llevan
	órdenes de complementos (antes «Ver y editar en hexadecimal» quedaba debajo de Salir)."""
	menus = dict(ordenes.menus())
	complementos = menus[ordenes.TITULO_COMPLEMENTOS]
	categorias = [e for e in complementos if isinstance(e, tuple)]
	assert [c[0].replace("&", "") for c in categorias] == [
		"Multimedia", "Documentos y datos", "Orden y limpieza del disco", "Sistema y seguridad", "Automatización", "Nubes y NAS",
	]
	submenus = [s for _titulo, contenido in categorias for s in contenido]
	assert len(submenus) == 27
	todas = {i for _t, ids in submenus for i in ids}
	assert {"zc.hexadecimal:editar", "zc.ocupacion:analizar", "zc.sincronizacion:perfiles",
		"zc.busqueda_instantanea:abrir", "zc.duplicados:buscar", "zc.organizador:organizar"} <= todas

	def ids(elementos):
		for e in elementos:
			if isinstance(e, tuple):
				yield from ids(e[1])
			elif e is not None:
				yield e

	for titulo in ("&Archivos", "&Comandos", "&Opciones", "Ay&uda"):
		assert not [i for i in ids(menus[titulo]) if i.startswith("zc.")], titulo
	assert menus["&Archivos"][-1] == "salir", "Salir es lo último de Archivos"
	# Cada orden del núcleo aparece una sola vez en los menús de la barra (salvo los de lado).
	vistos = [i for titulo, c in ordenes.menus() if c != ordenes.LADO for i in ids(c)]
	assert len(vistos) == len(set(vistos)), "hay órdenes repetidas en los menús"


def test_letras_submenus():
	assert ordenes.letras_submenus(["Nubes", "NAS"], {"n"}) == ["N&ubes", "N&AS"]
	resultado = ordenes.letras_submenus(["ab", "a", "b"], set())
	assert resultado == ["a&b", "&a", "b"] or len({r.split("&")[1][0] for r in resultado if "&" in r}) == 2
