# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Manifiestos de complementos (diseño 2.0, 3.3 y 18.2)."""

from __future__ import annotations

import shutil
import sys

import pytest

from app.plugins import config_plugins, manifiesto, registro

from ..conftest import RAIZ

EJEMPLO = RAIZ / "tests" / "datos" / "plugins" / "ejemplo"


def _datos(**cambios) -> dict:
	import tomllib

	with (EJEMPLO / "manifiesto.toml").open("rb") as archivo:
		datos = tomllib.load(archivo)
	datos.update(cambios)
	return datos


def test_manifiesto_valido():
	datos = manifiesto.leer(EJEMPLO)
	assert datos.id == "prueba.ejemplo"
	assert [o.id for o in datos.ordenes] == ["saludar"]
	assert datos.ordenes[0].argumento == "texto"
	assert datos.orden_prueba == "saludar"
	assert datos.codificado == "prueba__ejemplo"


@pytest.mark.parametrize(("cambios", "texto"), [
	({"id": "Mal.Id"}, "no es válido"),
	({"id": "prueba"}, "no es válido"),
	({"version": "1.0"}, "mayor.menor.parche"),
	({"api_minima": "1.2", "api_probada": "1.0"}, "api_minima"),
	({"licencia": ""}, "licencia"),
	({"entrada": "sin_clase"}, "módulo:Clase"),
	({"formato": 7}, "Formato"),
	({"prueba": "no_existe"}, "no está declarada"),
	({"permisos": ["volar"]}, "permisos"),
	({"ordenes": [{"id": "a", "etiqueta": "&Uno", "ayuda": "x", "teclas": ["ctrl+shift+f5"]}]}, "canónico"),
	({"ordenes": [{"id": "a", "etiqueta": "&Uno", "ayuda": ""}]}, "ayuda"),
	({"ordenes": [{"id": "a", "etiqueta": "&Uno", "ayuda": "x"}, {"id": "b", "etiqueta": "&Una", "ayuda": "y"}]}, "letra de acceso"),
	({"acciones_error": [{"id": "x", "etiqueta": "&X", "codigos_windows": ["32"]}]}, "codigos_windows"),
	({"configuracion": [{"clave": "a", "tipo": "archivo", "defecto": "", "ejecuta": "sí"}]}, "ejecuta"),
	({"configuracion": [{"clave": "a.b", "tipo": "bool", "defecto": True}]}, "no válida"),
	({"configuracion": [{"clave": "a", "tipo": "entero", "defecto": "5"}]}, "valor por defecto"),
	({"mascaras": [{"marcador": "[N]"}]}, "prefijo propio"),
])
def test_cada_campo_malo_da_su_mensaje(cambios, texto):
	with pytest.raises(manifiesto.ErrorManifiesto) as error:
		manifiesto.validar(_datos(**cambios))
	assert any(texto in problema for problema in error.value.problemas), error.value.problemas


def test_lib_con_nombre_de_la_biblioteca_estandar(tmp_path):
	carpeta = tmp_path / "ej"
	shutil.copytree(EJEMPLO, carpeta)
	(carpeta / "lib").mkdir()
	(carpeta / "lib" / "json.py").write_text("x = 1\n", encoding="utf-8")
	with pytest.raises(manifiesto.ErrorManifiesto) as error:
		manifiesto.leer(carpeta)
	assert any("lib/json.py" in p for p in error.value.problemas)


def test_clave_completa_se_resuelve_al_complemento():
	assert config_plugins.separar_clave("plugin.prueba.ejemplo.volumen") == ("prueba.ejemplo", "volumen")
	assert config_plugins.separar_clave("plugin.zc.reproductor.salto_corto_s") == ("zc.reproductor", "salto_corto_s")
	with pytest.raises(ValueError):
		config_plugins.separar_clave("sonidos.volumen")


def test_configuracion_propia_desde_el_manifiesto(registro_vacio, datos_temporales):
	registro_vacio.registrar(manifiesto.leer(EJEMPLO), EJEMPLO, "usuario")
	registro_global = config_plugins.registro()
	assert registro_global.claves() == ["plugin.prueba.ejemplo.volumen"]
	assert registro_global.obtener("plugin.prueba.ejemplo.volumen") == 5
	assert registro_global.establecer("plugin.prueba.ejemplo.volumen", 8)
	assert (datos_temporales / "config" / "plugins" / "prueba.ejemplo.json").is_file()


def test_id_repetido_en_la_misma_ubicacion(tmp_path):
	shutil.copytree(EJEMPLO, tmp_path / "uno")
	shutil.copytree(EJEMPLO, tmp_path / "dos")
	resultado = registro.descubrir_carpeta(tmp_path)
	assert len(resultado) == 2
	for _ruta, datos in resultado:
		assert isinstance(datos, list) and "repetido" in datos[0]


def test_registrar_serie_sin_importar_codigo(registro_vacio):
	antes = {m for m in sys.modules if m.startswith("zcplugins")}
	registro_vacio.registrar_serie()
	assert len(registro_vacio.complementos()) == 27
	assert {m for m in sys.modules if m.startswith("zcplugins")} == antes
	assert not registro_vacio.errores()
	for registrado in registro_vacio.complementos():
		assert registrado.manifiesto.bloque in manifiesto.BLOQUES_SERIE
