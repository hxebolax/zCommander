# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Migración de la configuración 1 → 2 (diseño 2.0, 14.3 y 18.2)."""

from __future__ import annotations

import json

from app.core import configuracion, descripciones_config


def _config_1x(tmp_path, **cambios):
	datos = {"version_esquema": 1, "accesibilidad": {"sonidos": False, "tonos_progreso": False, "anuncios": True},
		"ftp": {"avisar_sin_cifrar": True, "pasivo": True}, "operaciones": {"aviso_comprimido_mostrado": False}}
	for clave, valor in cambios.items():
		seccion, nombre = clave.split("__")
		datos[seccion][nombre] = valor
	ruta = tmp_path / "settings.json"
	ruta.write_text(json.dumps(datos), encoding="utf-8")
	return ruta


def test_sonidos_activos_para_todos_y_tonos_a_progreso(tmp_path):
	config = configuracion.Configuracion(_config_1x(tmp_path, accesibilidad__tonos_progreso=True))
	assert config.obtener("sonidos.activos") is True
	assert config.obtener("sonidos.progreso") == "cada_10"
	assert config.obtener("general.no_preguntar") == []
	guardado = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
	assert "sonidos" not in guardado.get("accesibilidad", {}) and "tonos_progreso" not in guardado.get("accesibilidad", {})


def test_avisos_de_la_1x_pasan_a_no_preguntar(tmp_path):
	ruta = _config_1x(tmp_path, ftp__avisar_sin_cifrar=False, operaciones__aviso_comprimido_mostrado=True)
	config = configuracion.Configuracion(ruta)
	assert config.obtener("sonidos.progreso") == "no"
	assert sorted(config.obtener("general.no_preguntar")) == ["comprimido_escritura", "ftp_sin_cifrar"]


def test_idempotente():
	datos = {"accesibilidad": {"sonidos": False, "tonos_progreso": True}, "ftp": {"avisar_sin_cifrar": False},
		"operaciones": {"aviso_comprimido_mostrado": True}}
	configuracion.MIGRACIONES[1](datos)
	una = json.loads(json.dumps(datos))
	configuracion.MIGRACIONES[1](datos)
	assert datos == una
	assert datos["general"]["no_preguntar"] == ["ftp_sin_cifrar", "comprimido_escritura"]


def test_ejecuta_nombra_claves_que_existen():
	claves = {f"{s}.{c}" for s, v in configuracion.VALORES_POR_DEFECTO.items() for c in v}
	assert descripciones_config.EJECUTA <= claves


def test_54_claves_nuevas_y_4_eliminadas():
	claves = {f"{s}.{c}" for s, v in configuracion.VALORES_POR_DEFECTO.items() for c in v}
	for vieja in ("accesibilidad.sonidos", "accesibilidad.tonos_progreso", "ftp.avisar_sin_cifrar", "operaciones.aviso_comprimido_mostrado"):
		assert vieja not in claves
	assert configuracion.VERSION_ESQUEMA == 2
	assert set(descripciones_config.DESCRIPCIONES) == claves


def test_confirmaciones_silenciables(tmp_path):
	from app.services import confirmaciones

	config = configuracion.Configuracion(tmp_path / "settings.json")
	assert confirmaciones.debe_preguntar(config, "ftp_sin_cifrar:sitio1")
	confirmaciones.silenciar(config, "ftp_sin_cifrar:sitio1")
	assert not confirmaciones.debe_preguntar(config, "ftp_sin_cifrar:sitio1")
	assert confirmaciones.debe_preguntar(config, "ftp_sin_cifrar:otro")
	confirmaciones.silenciar(config, "ftp_sin_cifrar")
	assert not confirmaciones.debe_preguntar(config, "ftp_sin_cifrar:otro")  # el prefijo cubre todos
	confirmaciones.volver_a_preguntar(config)
	assert confirmaciones.debe_preguntar(config, "ftp_sin_cifrar:sitio1")
