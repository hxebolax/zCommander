# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Menú de usuario y favoritos (bloque F), sin ventanas.

Lo esencial (sección 14 del diseño): el menú local de una carpeta NO se usa
sin confianza, y la confianza va ligada a la suma del archivo.
"""

from __future__ import annotations

import json

import pytest

from app.core.configuracion import Configuracion
from app.services import favoritos, menu_usuario
from app.services.menu_usuario import EntradaMenu


@pytest.fixture
def config(tmp_path):
	return Configuracion(ruta=tmp_path / "settings.json")


def _escribir_local(carpeta, entradas):
	(carpeta / menu_usuario.NOMBRE_LOCAL).write_text(
		json.dumps({"version": 1, "entradas": entradas}, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def carpeta_con_menu(tmp_path):
	carpeta = tmp_path / "descargado"
	carpeta.mkdir()
	_escribir_local(carpeta, [{"etiqueta": "Borrar todo", "tecla": "b", "ordenes": ["del /q *.*"]}])
	return carpeta


GLOBAL = [EntradaMenu("Comprimir con 7-Zip", "A", ["7z a %O\\%N.7z %M"])]


def test_menu_local_no_se_usa_sin_confianza(config, carpeta_con_menu):
	menu = menu_usuario.leer_local(str(carpeta_con_menu))
	assert menu is not None and [e.etiqueta for e in menu.entradas] == ["Borrar todo"]
	assert menu_usuario.estado_confianza(config.obtener(menu_usuario.CLAVE_CONFIANZA), menu) == menu_usuario.DESCONOCIDO
	entradas = menu_usuario.entradas_disponibles(config, menu, GLOBAL)
	assert [e.etiqueta for e in entradas] == ["Comprimir con 7-Zip"], "sin confianza no aparece el menú local"


def test_con_confianza_va_primero_y_si_cambia_deja_de_usarse(config, carpeta_con_menu):
	menu = menu_usuario.leer_local(str(carpeta_con_menu))
	menu_usuario.confiar(config, menu)
	guardado = config.obtener(menu_usuario.CLAVE_CONFIANZA)
	assert list(guardado.values()) == [menu.suma]
	entradas = menu_usuario.entradas_disponibles(config, menu_usuario.leer_local(str(carpeta_con_menu)), GLOBAL)
	assert [e.etiqueta for e in entradas] == ["Borrar todo", "Comprimir con 7-Zip"]
	assert entradas[0].local and entradas[0].tecla == "B"
	# Alguien cambia el archivo: la suma ya no coincide.
	_escribir_local(carpeta_con_menu, [{"etiqueta": "Otra cosa", "ordenes": ["format c:"]}])
	cambiado = menu_usuario.leer_local(str(carpeta_con_menu))
	assert menu_usuario.estado_confianza(config.obtener(menu_usuario.CLAVE_CONFIANZA), cambiado) == menu_usuario.CAMBIADO
	assert [e.etiqueta for e in menu_usuario.entradas_disponibles(config, cambiado, GLOBAL)] == ["Comprimir con 7-Zip"]
	assert menu_usuario.retirar_confianza(config, str(carpeta_con_menu))
	assert config.obtener(menu_usuario.CLAVE_CONFIANZA) == {}


def test_menu_local_danado_no_se_usa(config, tmp_path):
	carpeta = tmp_path / "rota"
	carpeta.mkdir()
	(carpeta / menu_usuario.NOMBRE_LOCAL).write_text("{no es json", encoding="utf-8")
	menu = menu_usuario.leer_local(str(carpeta))
	assert menu is not None and menu.error and not menu.entradas
	assert menu_usuario.entradas_disponibles(config, menu, GLOBAL) == GLOBAL
	assert menu_usuario.leer_local(str(tmp_path / "no-existe")) is None
	assert menu_usuario.leer_local(None) is None


def test_guardar_y_cargar_con_submenu():
	entradas = [
		EntradaMenu("Comprimir", "c", ["7z a x.7z %M"], consola=True, refrescar=False),
		EntradaMenu("Git", "G", ["esto se ignora"], submenu=[EntradaMenu("Estado", "E", ["git status"])]),
	]
	menu_usuario.guardar(entradas)
	leidas = menu_usuario.cargar()
	assert leidas[0].tecla == "C" and leidas[0].consola and not leidas[0].refrescar
	assert leidas[1].es_submenu and leidas[1].ordenes == [] and leidas[1].submenu[0].ordenes == ["git status"]
	assert leidas[1].texto() == "G: Git (submenú)"
	assert menu_usuario.buscar_tecla(leidas, "g") is leidas[1]
	assert menu_usuario.buscar_tecla(leidas, "Z") is None


def test_entradas_mal_formadas_y_profundidad():
	profundo: dict = {"etiqueta": "n0", "submenu": []}
	actual = profundo
	for nivel in range(1, 20):
		hijo = {"etiqueta": f"n{nivel}", "submenu": []}
		actual["submenu"].append(hijo)
		actual = hijo
	entradas = menu_usuario.leer_entradas([{"sin": "etiqueta"}, "texto", {"etiqueta": "  "}, {"etiqueta": "Bien", "tecla": "ab"}, profundo])
	assert [e.etiqueta for e in entradas] == ["Bien", "n0"]
	assert entradas[0].tecla == ""  # «ab» no es una tecla
	niveles, actual_entrada = 0, entradas[1]
	while actual_entrada.submenu:
		niveles += 1
		actual_entrada = actual_entrada.submenu[0]
	assert niveles <= menu_usuario.PROFUNDIDAD_MAXIMA


def test_plantilla_y_resumen():
	entrada = EntradaMenu("Dos", ordenes=["echo uno", "  ", "echo dos"])
	assert menu_usuario.plantilla(entrada) == "echo uno & echo dos"
	assert menu_usuario.resumen_ordenes([entrada]) == ["Dos", "    echo uno", "    echo dos"]


def test_clave_carpeta_de_unidad_y_mayusculas(tmp_path):
	assert menu_usuario.clave_carpeta("D:") == menu_usuario.clave_carpeta("d:\\")
	assert menu_usuario.clave_carpeta(str(tmp_path).upper()) == menu_usuario.clave_carpeta(str(tmp_path) + "\\")


# ── Favoritos ───────────────────────────────────────────────────────────────

def test_favoritos_agregar_mover_eliminar_y_guardar():
	lista: list[favoritos.Favorito] = []
	assert favoritos.agregar(lista, "", "D:\\Fotos\\") == 0
	assert lista[0].nombre == "Fotos"
	assert favoritos.agregar(lista, "Música", "E:\\Musica") == 1
	assert favoritos.agregar(lista, "Fotos nuevas", "d:\\fotos") == 0, "misma ruta: se renombra, no se duplica"
	assert lista[0].nombre == "Fotos nuevas" and len(lista) == 2
	assert favoritos.mover(lista, 1, -1) == 0 and lista[0].nombre == "Música"
	assert favoritos.mover(lista, 0, -1) == 0, "al borde no se mueve"
	favoritos.renombrar(lista, 1, "Fotos")
	with pytest.raises(ValueError):
		favoritos.renombrar(lista, 1, "  ")
	favoritos.guardar(lista)
	assert [(f.nombre, f.ruta) for f in favoritos.cargar()] == [("Música", "E:\\Musica"), ("Fotos", "D:\\Fotos\\")]
	assert favoritos.eliminar(lista, 0).nombre == "Música"
	assert favoritos.buscar(lista, "D:\\FOTOS") == 0


def test_favoritos_nombres_sugeridos_y_archivo_raro(tmp_path):
	assert favoritos.nombre_sugerido("C:\\") == "C:"
	assert favoritos.nombre_sugerido("\\\\servidor\\recurso") == "recurso"
	assert favoritos.nombre_sugerido("sftp://equipo/home/ana") == "ana"
	from app.core import almacen_json

	almacen_json.escribir(favoritos.NOMBRE, {"version": 1, "favoritos": [{"ruta": "C:\\x"}, {"nombre": "sin ruta"}, 3]})
	assert [(f.nombre, f.ruta) for f in favoritos.cargar()] == [("x", "C:\\x")]
