# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Integrar los componentes que trae una actualización de la aplicación (diseño 2.0, 5.3, 6.7 y 18.2)."""

from __future__ import annotations

import shutil

import pytest

from app.core import paths
from app.services.componentes import estado, fichas, instalar, integrar
from tests.servicios import apoyo_co


@pytest.fixture(autouse=True)
def lanzador_falso(monkeypatch):
	original = instalar.Instalador.__init__

	def con_lanzador(self, *args, **kwargs):
		original(self, *args, **kwargs)
		self.lanzar = apoyo_co.lanzar_falso
		self.esperas = apoyo_co.ESPERAS_CORTAS

	monkeypatch.setattr(instalar.Instalador, "__init__", con_lanzador)


def _con_entrante(datos, version_base: dict[str, str]) -> estado.Entorno:
	"""``data`` con demo 1.0.0 y otro 2.0.0 activos y un ``.entrante`` con la línea base nueva."""
	fichas_base = [apoyo_co.ficha_demo("1.0.0"), apoyo_co.ficha_demo("2.0.0", id="otro", nombre="Otro", carpeta="otro",
		prueba={"ejecutable": "otro.exe", "argumentos": [], "salida_contiene": "otro v{version}"})]
	entorno = apoyo_co.crear_entorno(datos, fichas_base, {
		"demo": {"demo.exe": "demo v1.0.0", "LICENCIA.txt": "MIT"}, "otro": {"otro.exe": "otro v2.0.0"}})
	entrante = entorno.entrante
	nuevas = []
	for ficha in fichas_base:
		version = version_base[ficha["id"]]
		carpeta = entrante / ficha["carpeta"]
		carpeta.mkdir(parents=True)
		(carpeta / ficha["prueba"]["ejecutable"]).write_text(f"{ficha['id']} v{version}", encoding="utf-8")
		nuevas.append(dict(ficha, version=version, archivos=fichas.sumas_de_carpeta(carpeta)))
	fichas.escribir(entrante / "linea_base.json", {"formato": 1, "aplicacion": "2.1.0", "componentes": nuevas})
	return entorno


def test_integra_la_base_nueva_y_conserva_la_mas_nueva(tmp_path, monkeypatch):
	monkeypatch.setattr(integrar, "APP_VERSION", "2.1.0")
	datos = paths.ruta_datos()
	entorno = _con_entrante(datos, {"demo": "1.1.0", "otro": "2.0.0"})
	# La persona actualizó «otro» a 2.5.0: más nuevo que lo que trae la base nueva (2.0.0).
	(entorno.bin / "otro" / "otro.exe").write_text("otro v2.5.0", encoding="utf-8")
	estado.guardar_ficha(dict(estado.ficha_instalada("otro", entorno), version="2.5.0",
		archivos=fichas.sumas_de_carpeta(entorno.bin / "otro")), entorno)
	anunciados = []
	integrar.fijar_anunciador(anunciados.append)
	try:
		assert integrar.hay_entrante(datos)
		resumen = integrar.integrar_entrante(datos)
	finally:
		integrar.fijar_anunciador(None)
	assert anunciados == ["Preparando los componentes nuevos de zCommander..."]
	assert resumen.instalados == ["demo"] and resumen.conservados == ["otro"] and resumen.revertidos == []
	assert "Se conserva Otro 2.5.0" in resumen.mensaje
	assert (entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.1.0"
	assert not (entorno.bin / "demo" / "LICENCIA.txt").exists(), "lo que trae la aplicación sustituye entero"
	assert (entorno.bin / "otro" / "otro.exe").read_text(encoding="utf-8") == "otro v2.5.0"
	assert estado.ficha_base("demo", entorno)["version"] == "1.1.0", "la línea base pasa a ser la nueva"
	assert (entorno.respaldo / "linea_base-1.0.0.json").is_file()
	assert entorno.integracion.is_file() and entorno.entrante.is_dir(), "se guardan hasta confirmar la salud"
	assert integrar.integrar_entrante(datos) is None, "un segundo arranque no vuelve a integrar"
	integrar.confirmar_integracion()
	assert not entorno.integracion.exists() and not entorno.entrante.exists()


def test_si_la_aplicacion_vuelve_atras_lo_integrado_se_revierte(tmp_path, monkeypatch):
	datos = paths.ruta_datos()
	entorno = _con_entrante(datos, {"demo": "1.1.0", "otro": "2.0.0"})
	antes = fichas.mapa_sumas(fichas.sumas_de_carpeta(entorno.bin / "demo"))
	base_antes = entorno.linea_base.read_text(encoding="utf-8")
	monkeypatch.setattr(integrar, "APP_VERSION", "2.1.0")
	assert integrar.integrar_entrante(datos).instalados == ["demo"]
	# El .bat del actualizador vuelve a la 2.0.0 sin que la 2.1.0 confirmara su salud: arranca la versión anterior.
	monkeypatch.setattr(integrar, "APP_VERSION", "1.0.0")
	resumen = integrar.integrar_entrante(datos)
	assert resumen.revertidos == ["demo"] and "versión anterior" in resumen.mensaje
	assert fichas.mapa_sumas(fichas.sumas_de_carpeta(entorno.bin / "demo")) == antes
	assert entorno.linea_base.read_text(encoding="utf-8") == base_antes
	assert not entorno.integracion.exists() and not entorno.entrante.exists()
	assert "comp.revertido" in integrar.sonidos_pendientes()


def test_sin_entrante_no_hace_nada(tmp_path):
	datos = paths.ruta_datos()
	apoyo_co.crear_entorno(datos)
	assert integrar.integrar_entrante(datos) is None
	assert integrar.aplicar_pendientes(datos) == []
	assert not integrar.hay_entrante(datos)


def test_entrante_sin_componentes_json_usa_la_base_anterior(tmp_path, monkeypatch):
	monkeypatch.setattr(integrar, "APP_VERSION", "2.1.0")
	datos = paths.ruta_datos()
	entorno = _con_entrante(datos, {"demo": "1.1.0", "otro": "2.1.0"})
	entorno.instalados.unlink()
	resumen = integrar.integrar_entrante(datos)
	assert sorted(resumen.instalados) == ["demo", "otro"]
	shutil.rmtree(entorno.entrante)
