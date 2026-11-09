# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Organizador y renombrado por metadatos (diseño 2.0, 11.23 y 18.2).

La máscara ``[EXIF:fecha:…]`` es de ``zc.imagenes`` (P1): aquí se pone una
de prueba en el registro de máscaras (se quita sola al terminar) que da la
fecha de cada foto, como haría la de verdad con su EXIF.
"""

from __future__ import annotations

import os
import time

import pytest

from app.plugins import api, registro
from app.services.operaciones.deshacer import RegistroDeshacer
from app.services.vfs import resolver
from tests.plugins.p3_comun import contexto_operacion, modulo, preparar

FECHAS = {"playa.jpg": "2024-07-15", "nieve.jpg": "2025-01-03", "cumple.jpg": "2025-03-20", "sin_exif.jpg": ""}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
	zc, paquete = preparar("organizador")
	mascaras = registro._funciones("mascara")  # noqa: SLF001 - máscara de prueba que monkeypatch retira

	def fecha(parte: slice):
		return lambda entrada, _proveedor: (FECHAS.get(entrada.nombre, "") or "")[parte] or None

	monkeypatch.setitem(mascaras, "[EXIF:fecha:AAAA]", ("prueba.exif", fecha(slice(0, 4))))
	monkeypatch.setitem(mascaras, "[EXIF:fecha:MM]", ("prueba.exif", fecha(slice(5, 7))))
	origen = tmp_path / "Cámara"
	origen.mkdir()
	for nombre in FECHAS:
		(origen / nombre).write_bytes(nombre.encode())
	return zc, modulo(paquete, "motor"), tmp_path, origen


def _entradas(origen) -> list[api.Entrada]:
	return resolver.proveedor_local().listar(str(origen))


def test_tres_fotos_con_fechas_exif_distintas_van_a_sus_carpetas_de_anio_y_mes(entorno):
	zc, motor, carpeta, origen = entorno
	base = carpeta / "Ordenado"
	filas = zc.instancia.planificar(_entradas(origen), resolver.proveedor_local(), str(base),
		"Fotos\\[EXIF:fecha:AAAA]\\[EXIF:fecha:MM]", "[N]")
	destinos = {os.path.basename(f.origen): (f.destino, f.estado) for f in filas}
	assert destinos["playa.jpg"] == (str(base / "Fotos" / "2024" / "07" / "playa.jpg"), motor.LISTO)
	assert destinos["nieve.jpg"] == (str(base / "Fotos" / "2025" / "01" / "nieve.jpg"), motor.LISTO)
	assert destinos["cumple.jpg"] == (str(base / "Fotos" / "2025" / "03" / "cumple.jpg"), motor.LISTO)
	# Sin dato, la carpeta toma el texto de «sin_dato».
	assert destinos["sin_exif.jpg"][0] == str(base / "Fotos" / "Sin fecha" / "Sin fecha" / "sin_exif.jpg")
	assert motor.resumen(filas) == "4 listos"


def test_dos_que_darian_el_mismo_destino_se_marcan_duplicado(entorno):
	zc, motor, carpeta, origen = entorno
	filas = zc.instancia.planificar(_entradas(origen), resolver.proveedor_local(), str(carpeta / "Ordenado"),
		"[EXIF:fecha:AAAA]", "foto")
	estados = {os.path.basename(f.origen): f.estado for f in filas}
	assert estados == {"nieve.jpg": motor.DUPLICADO, "cumple.jpg": motor.DUPLICADO, "playa.jpg": motor.LISTO, "sin_exif.jpg": motor.LISTO}
	assert motor.resumen(filas) == "2 listos, 2 duplicados"
	assert motor.texto_estado(motor.DUPLICADO) == "Duplicado"
	(carpeta / "Ordenado" / "2024").mkdir(parents=True)
	(carpeta / "Ordenado" / "2024" / "foto.jpg").write_bytes(b"ya")
	filas = zc.instancia.planificar(_entradas(origen), resolver.proveedor_local(), str(carpeta / "Ordenado"), "[EXIF:fecha:AAAA]", "foto")
	assert {os.path.basename(f.origen): f.estado for f in filas}["playa.jpg"] == motor.EXISTE


def test_organizar_y_deshacer_las_devuelve(entorno):
	zc, motor, carpeta, origen = entorno
	base = carpeta / "Ordenado"
	local = resolver.proveedor_local()
	filas = zc.instancia.planificar(_entradas(origen), local, str(base), "Fotos\\[EXIF:fecha:AAAA]\\[EXIF:fecha:MM]", "[N]")
	operacion = motor.OperacionOrganizar(filas, local, local, mover=True)
	ctx = contexto_operacion()
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert not operacion.errores
	assert (base / "Fotos" / "2024" / "07" / "playa.jpg").read_bytes() == b"playa.jpg"
	assert (base / "Fotos" / "2025" / "03" / "cumple.jpg").is_file()
	assert sorted(os.listdir(origen)) == []
	assert len(operacion.pares_hechos()) == 4
	resultado = RegistroDeshacer().deshacer(operacion.deshacer)
	assert sorted(os.listdir(origen)) == sorted(FECHAS)
	assert (origen / "playa.jpg").read_bytes() == b"playa.jpg"
	assert not base.exists() or not any(base.rglob("*")), resultado.omitidos


def test_copiar_deja_los_originales_y_renombra_con_la_plantilla(entorno):
	zc, motor, carpeta, origen = entorno
	base = carpeta / "Copias"
	local = resolver.proveedor_local()
	ahora = time.localtime()
	filas = zc.instancia.planificar(_entradas(origen), local, str(base), "Por año\\[Y]", "[EXIF:fecha:MM] - [N]")
	operacion = motor.OperacionOrganizar(filas, local, local, mover=False)
	ctx = contexto_operacion()
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert sorted(os.listdir(origen)) == sorted(FECHAS)
	assert sorted(os.listdir(base / "Por año" / f"{ahora.tm_year:04d}")) == ["- sin_exif.jpg", "01 - nieve.jpg", "03 - cumple.jpg", "07 - playa.jpg"]


def test_tramos_limpiar_y_expandir(entorno):
	_zc, motor, carpeta, origen = entorno
	assert motor.tramos("Música\\[MP3:artista]/[MP3:album]") == ["Música", "[MP3:artista]", "[MP3:album]"]
	assert motor.limpiar("AC/DC: Live?") == "AC_DC_ Live_"
	assert motor.limpiar("con. ") == "_con"
	assert motor.limpiar("  ") == ""
	(origen / "sub").mkdir()
	(origen / "sub" / "x.jpg").write_bytes(b"x")
	local = resolver.proveedor_local()
	archivos = motor.expandir([local.info(str(origen))], local)
	assert sorted(a.nombre for a in archivos) == sorted([*FECHAS, "x.jpg"])


def test_exporta_planificar_y_operacion(entorno):
	_zc, motor, _carpeta, origen = entorno
	exportados = registro.exportados("zc.organizador")
	filas = exportados["planificar"]([str(origen / "playa.jpg")], "[EXIF:fecha:AAAA]")
	assert [f.destino for f in filas] == [str(origen / "2024" / "playa.jpg")]
	assert isinstance(exportados["operacion"](filas), motor.OperacionOrganizar)


def test_la_orden_tiene_manejador_real():
	preparar("organizador")
	funcion = registro.manejador("zc.organizador:organizar")
	assert funcion is not None and not getattr(funcion, "provisional", False)
