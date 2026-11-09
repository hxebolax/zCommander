# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Buscador de duplicados (diseño 2.0, 11.7 y 18.2): pruebas mínimas de la ficha y de su motor."""

from __future__ import annotations

import os
import sys
import time

import pytest

from app.plugins import api, registro
from tests.plugins.p3_comun import contexto_operacion, modulo, preparar

TAMANO = 100 * 1024  # más de 64 KB: hace falta la suma completa para distinguir


@pytest.fixture
def entorno(tmp_path):
	zc, paquete = preparar("duplicados")
	return zc, modulo(paquete, "motor"), tmp_path


def _escribir(ruta, contenido: bytes, modificado: float | None = None) -> str:
	ruta.parent.mkdir(parents=True, exist_ok=True)
	ruta.write_bytes(contenido)
	if modificado is not None:
		os.utime(ruta, (modificado, modificado))
	return str(ruta)


def _arbol(carpeta) -> dict[str, str]:
	base = bytes(range(256)) * (TAMANO // 256)
	ahora = time.time()
	return {
		"antiguo": _escribir(carpeta / "a" / "foto.jpg", base, ahora - 3000),
		"medio": _escribir(carpeta / "b" / "copia de foto.jpg", base, ahora - 2000),
		"reciente": _escribir(carpeta / "c" / "d" / "foto.jpg", base, ahora - 1000),
		# Mismo tamaño y mismos 64 KB del principio: solo la suma completa lo separa.
		"distinto": _escribir(carpeta / "otra.jpg", base[:-1] + b"\x00", ahora),
	}


def test_tres_iguales_y_uno_distinto_del_mismo_tamano_dan_un_grupo_de_tres(entorno):
	_zc, motor, carpeta = entorno
	rutas = _arbol(carpeta)
	archivos = motor.recorrer(motor.Opciones([str(carpeta)], tamano_minimo=1))
	assert len(archivos) == 4
	grupos = motor.agrupar(archivos, "contenido")
	assert len(grupos) == 1
	assert {a.ruta for a in grupos[0].archivos} == {rutas["antiguo"], rutas["medio"], rutas["reciente"]}
	assert grupos[0].recuperable == 2 * TAMANO
	assert motor.describir_grupo(0, 1, grupos[0]) == "Grupo 1 de 1, 3 copias, 200 KB recuperables"


def test_conservar_el_mas_antiguo_marca_los_otros_dos(entorno):
	_zc, motor, carpeta = entorno
	rutas = _arbol(carpeta)
	grupos = motor.agrupar(motor.recorrer(motor.Opciones([str(carpeta)], tamano_minimo=1)), "contenido")
	marcadas = motor.marcar_automatico(grupos, "antiguo")
	assert marcadas == {rutas["medio"], rutas["reciente"]}
	assert motor.resumen_marcado(grupos, marcadas) == "Marcados 2 archivos en 1 grupo, 200 KB"
	assert motor.marcar_automatico(grupos, "reciente") == {rutas["antiguo"], rutas["medio"]}
	assert rutas["medio"] not in motor.marcar_automatico(grupos, "carpeta", str(carpeta / "b"))
	assert motor.grupos_sin_copia(grupos, {rutas["antiguo"], rutas["medio"], rutas["reciente"]}) == [0]


def test_por_nombre_y_por_nombre_y_tamano(entorno):
	_zc, motor, carpeta = entorno
	_arbol(carpeta)
	archivos = motor.recorrer(motor.Opciones([str(carpeta)], tamano_minimo=1))
	assert [len(g.archivos) for g in motor.agrupar(archivos, "nombre")] == [2]
	assert [len(g.archivos) for g in motor.agrupar(archivos, "nombre_tamano")] == [2]
	with pytest.raises(api.NoAdmitido):
		motor.agrupar(archivos, "etiquetas")


def test_excluir_y_ocultos(entorno):
	_zc, motor, carpeta = entorno
	_arbol(carpeta)
	_escribir(carpeta / "x.tmp", b"1" * 2000)
	_escribir(carpeta / "y.tmp", b"1" * 2000)
	archivos = motor.recorrer(motor.Opciones([str(carpeta)], tamano_minimo=1, excluir="*.tmp;otra.jpg"))
	assert all(not a.nombre.endswith(".tmp") and a.nombre != "otra.jpg" for a in archivos)
	assert len(motor.recorrer(motor.Opciones([str(carpeta)], tamano_minimo=TAMANO + 1))) == 0


def test_la_busqueda_se_cancela(entorno):
	_zc, motor, carpeta = entorno
	_arbol(carpeta)
	operacion = motor.OperacionBuscarDuplicados(motor.Opciones([str(carpeta)], tamano_minimo=1))
	ctx = contexto_operacion(cancelado=True)
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert operacion.estado == api.Estado.CANCELADA
	assert not operacion.resultado.completo
	assert "incompleta" in operacion.resumen()


def test_la_operacion_encuentra_el_grupo(entorno):
	_zc, motor, carpeta = entorno
	_arbol(carpeta)
	operacion = motor.OperacionBuscarDuplicados(motor.Opciones([str(carpeta)], tamano_minimo=1))
	ctx = contexto_operacion()
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert operacion.estado == api.Estado.TERMINADA
	assert len(operacion.resultado.grupos) == 1
	assert operacion.resultado.revisados == 4
	assert operacion.resumen().startswith("1 grupo de duplicados, 200 KB recuperables")


def test_sustituir_por_enlace_duro_deja_un_solo_contenido(entorno):
	_zc, motor, carpeta = entorno
	rutas = _arbol(carpeta)
	operacion = motor.OperacionEnlacesDuros([(rutas["antiguo"], rutas["medio"]), (rutas["antiguo"], rutas["reciente"])])
	ctx = contexto_operacion()
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert operacion.estado == api.Estado.TERMINADA, operacion.errores
	indices = {os.stat(rutas[c]).st_ino for c in ("antiguo", "medio", "reciente")}
	assert len(indices) == 1
	assert os.stat(rutas["antiguo"]).st_nlink == 3
	assert not [n for n in os.listdir(carpeta / "b") if n.startswith("~zcenlace")]


def test_un_enlace_duro_no_sustituye_un_archivo_que_ya_no_es_igual(entorno):
	_zc, motor, carpeta = entorno
	rutas = _arbol(carpeta)
	with pytest.raises(api.ErrorArchivos):
		motor.sustituir_por_enlace(rutas["antiguo"], rutas["distinto"])
	assert os.stat(rutas["antiguo"]).st_ino != os.stat(rutas["distinto"]).st_ino


def test_informe_en_texto_y_csv(entorno, tmp_path):
	zc, motor, carpeta = entorno
	rutas = _arbol(carpeta)
	resultado = motor.Resultado(motor.agrupar(motor.recorrer(motor.Opciones([str(carpeta)], tamano_minimo=1)), "contenido"), revisados=4)
	texto = motor.informe_texto(resultado, {rutas["medio"]})
	assert "Grupo 1 de 1, 3 copias" in texto and f"{rutas['medio']} (marcado)" in texto
	csv = motor.informe_csv(resultado, {rutas["medio"]})
	assert csv.splitlines()[0] == "Grupo;Nombre;Carpeta;Tamaño;Fecha;Marcado"
	assert len(csv.splitlines()) == 4
	destino = tmp_path / "informe.csv"
	sys.modules[type(zc.instancia).__module__].exportar(str(destino), resultado, set())
	assert destino.read_bytes().startswith(b"\xef\xbb\xbf")


def test_la_orden_tiene_manejador_real():
	zc, _paquete = preparar("duplicados")
	funcion = registro.manejador("zc.duplicados:buscar")
	assert funcion is not None and not getattr(funcion, "provisional", False)
	assert zc.config.obtener("excluir") == "*.tmp;Thumbs.db;desktop.ini"
