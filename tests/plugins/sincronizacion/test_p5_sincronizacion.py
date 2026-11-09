# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de zc.sincronizacion (diseño 2.0, 11.12 y 18.2) con carpetas temporales reales."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from app.plugins import api, registro
from app.plugins.api import pruebas
from tests.plugins import p5_comun

NOMBRE = "sincronizacion"


@pytest.fixture
def zc():
	return p5_comun.anfitrion(NOMBRE)


@pytest.fixture
def motor(zc):
	return p5_comun.modulo(NOMBRE, "motor")


def _escribir(ruta: Path, texto: str, hace_s: float = 0) -> None:
	ruta.parent.mkdir(parents=True, exist_ok=True)
	ruta.write_text(texto, encoding="utf-8")
	if hace_s:
		momento = time.time() - hace_s
		os.utime(ruta, (momento, momento))


def _arbol(raiz: Path) -> dict[str, str]:
	return {p.relative_to(raiz).as_posix(): p.read_text(encoding="utf-8") for p in sorted(raiz.rglob("*")) if p.is_file()}


def _ejecutar(zc, nombre: str, simular: bool = False):
	exportado = registro.exportados("zc.sincronizacion")
	operacion = exportado["operacion_de_tarea"](nombre, simular=simular) if simular else exportado["operacion_de_tarea"](nombre)
	contexto = api.ContextoEjecucion(threading.Event(), pruebas.DecisorFalso())
	contexto.operacion = operacion
	operacion.contexto = contexto
	operacion.ejecutar(contexto)
	return operacion


def _perfil(zc, motor, tmp_path: Path, modo: str, versiones: bool = True):
	izquierda, derecha = tmp_path / "izq", tmp_path / "der"
	izquierda.mkdir(exist_ok=True)
	derecha.mkdir(exist_ok=True)
	motor.guardar_perfiles(zc.datos, [motor.Perfil("Prueba", str(izquierda), str(derecha), modo=modo, versiones=versiones)])
	return izquierda, derecha


def test_exporta_operacion_de_tarea_con_su_firma(zc, motor, tmp_path):
	_perfil(zc, motor, tmp_path, motor.ESPEJO)
	operacion = registro.exportados("zc.sincronizacion")["operacion_de_tarea"]("prueba")
	assert isinstance(operacion, api.Operacion)
	with pytest.raises(api.NoEncontrado):
		registro.exportados("zc.sincronizacion")["operacion_de_tarea"]("no existe")


def test_dos_sentidos_borrado_a_la_izquierda_se_borra_a_la_derecha_y_no_vuelve(zc, motor, tmp_path):
	izquierda, derecha = _perfil(zc, motor, tmp_path, motor.DOS_SENTIDOS)
	_escribir(izquierda / "a.txt", "a", hace_s=100)
	_escribir(izquierda / "sub" / "b.txt", "b", hace_s=100)
	_escribir(derecha / "c.txt", "c", hace_s=100)
	operacion = _ejecutar(zc, "Prueba")
	assert operacion.estado == api.Estado.TERMINADA, operacion.errores
	assert _arbol(izquierda) == _arbol(derecha) == {"a.txt": "a", "c.txt": "c", "sub/b.txt": "b"}
	(izquierda / "a.txt").unlink()
	operacion = _ejecutar(zc, "Prueba")
	assert [a.tipo for a in operacion.plan] == [motor.BORRAR_DERECHA]
	assert not (derecha / "a.txt").exists()
	assert not (izquierda / "a.txt").exists()
	# Lo borrado está en las versiones del destino, no se ha perdido.
	assert list((derecha / "_versiones").rglob("a.txt"))
	operacion = _ejecutar(zc, "Prueba")
	assert operacion.plan == []
	assert not (izquierda / "a.txt").exists() and not (derecha / "a.txt").exists()


def test_dos_sentidos_cambio_en_el_destino_pasa_al_origen_y_lo_sustituido_va_a_versiones(zc, motor, tmp_path):
	izquierda, derecha = _perfil(zc, motor, tmp_path, motor.DOS_SENTIDOS)
	_escribir(izquierda / "informe.txt", "versión 1", hace_s=100)
	_ejecutar(zc, "Prueba")
	_escribir(derecha / "informe.txt", "versión 2 más larga")
	operacion = _ejecutar(zc, "Prueba")
	assert [a.tipo for a in operacion.plan] == [motor.COPIAR_A_IZQUIERDA]
	assert (izquierda / "informe.txt").read_text(encoding="utf-8") == "versión 2 más larga"
	dia = time.strftime("%Y-%m-%d")
	assert (izquierda / "_versiones" / dia / "informe.txt").read_text(encoding="utf-8") == "versión 1"


def test_dos_sentidos_detecta_un_renombrado(zc, motor, tmp_path):
	izquierda, derecha = _perfil(zc, motor, tmp_path, motor.DOS_SENTIDOS)
	_escribir(izquierda / "viejo.txt", "contenido", hace_s=100)
	_ejecutar(zc, "Prueba")
	(izquierda / "viejo.txt").rename(izquierda / "nuevo.txt")
	operacion = _ejecutar(zc, "Prueba")
	assert [(a.tipo, a.relativo, a.nuevo) for a in operacion.plan] == [(motor.RENOMBRAR_DERECHA, "viejo.txt", "nuevo.txt")]
	assert _arbol(derecha) == {"nuevo.txt": "contenido"}


def test_espejo_sustituido_va_a_versiones_y_lo_que_sobra_se_quita(zc, motor, tmp_path):
	izquierda, derecha = _perfil(zc, motor, tmp_path, motor.ESPEJO)
	_escribir(izquierda / "a.txt", "nuevo")
	_escribir(derecha / "a.txt", "viejo", hace_s=500)
	_escribir(derecha / "sobra.txt", "x")
	operacion = _ejecutar(zc, "Prueba")
	assert operacion.estado == api.Estado.TERMINADA, operacion.errores
	assert _arbol(derecha) == {"a.txt": "nuevo", **{k: v for k, v in _arbol(derecha).items() if k.startswith("_versiones/")}}
	versiones = {Path(k).name: v for k, v in _arbol(derecha / "_versiones").items()}
	assert versiones == {"a.txt": "viejo", "sobra.txt": "x"}


def test_actualizar_no_borra_ni_copia_lo_mas_antiguo(zc, motor, tmp_path):
	izquierda, derecha = _perfil(zc, motor, tmp_path, motor.ACTUALIZAR)
	_escribir(izquierda / "a.txt", "antiguo", hace_s=500)
	_escribir(derecha / "a.txt", "reciente")
	_escribir(derecha / "solo.txt", "s")
	_escribir(izquierda / "nuevo.txt", "n")
	_ejecutar(zc, "Prueba")
	assert _arbol(derecha) == {"a.txt": "reciente", "nuevo.txt": "n", "solo.txt": "s"}


def test_la_simulacion_no_cambia_nada(zc, motor, tmp_path):
	izquierda, derecha = _perfil(zc, motor, tmp_path, motor.ESPEJO)
	_escribir(izquierda / "a.txt", "a")
	_escribir(derecha / "b.txt", "b")
	antes = (_arbol(izquierda), _arbol(derecha))
	operacion = _ejecutar(zc, "Prueba", simular=True)
	assert (_arbol(izquierda), _arbol(derecha)) == antes
	assert {a.tipo for a in operacion.plan} == {motor.COPIAR_A_DERECHA, motor.BORRAR_DERECHA}
	assert any("Copiar al destino: a.txt" in linea for linea in operacion.informe.lineas)
	assert not list(zc.datos.glob("*.db"))


def test_exclusiones_y_sin_versiones(zc, motor, tmp_path):
	izquierda, derecha = tmp_path / "i", tmp_path / "d"
	izquierda.mkdir()
	derecha.mkdir()
	motor.guardar_perfiles(zc.datos, [motor.Perfil("P", str(izquierda), str(derecha), excluir="*.tmp;cache", versiones=False)])
	_escribir(izquierda / "a.txt", "a")
	_escribir(izquierda / "b.tmp", "b")
	_escribir(izquierda / "cache" / "c.txt", "c")
	_escribir(derecha / "a.txt", "viejo", hace_s=500)
	_ejecutar(zc, "P")
	assert _arbol(derecha) == {"a.txt": "a"}


def test_limpieza_de_versiones_antiguas(zc, motor, tmp_path):
	izquierda, derecha = _perfil(zc, motor, tmp_path, motor.ESPEJO)
	antigua = derecha / "_versiones" / "2000-01-01"
	_escribir(antigua / "x.txt", "x")
	_escribir(izquierda / "a.txt", "a")
	_ejecutar(zc, "Prueba")
	assert not antigua.exists()


def test_la_ultima_ejecucion_queda_apuntada_con_su_informe(zc, motor, tmp_path):
	izquierda, _derecha = _perfil(zc, motor, tmp_path, motor.ESPEJO)
	_escribir(izquierda / "a.txt", "a")
	_ejecutar(zc, "Prueba")
	perfil = motor.leer_perfiles(zc.datos)[0]
	assert perfil.ultima > 0 and perfil.resultado
	assert "Copiar al destino: a.txt" in motor.leer_informe(zc.datos, "Prueba")


def test_ejecutar_todas_pone_cada_tarea_en_cola(zc, motor, tmp_path):
	_perfil(zc, motor, tmp_path, motor.ESPEJO)
	zc.ejecutar("ejecutar_todas")
	assert len(zc.operaciones_lanzadas) == 1
	assert zc.operaciones_lanzadas[0].orden_origen == "zc.sincronizacion:ejecutar_todas"


def test_ordenes_con_manejador_real(zc):
	for orden in ("perfiles", "ejecutar_todas"):
		manejador = registro.manejador(f"zc.sincronizacion:{orden}")
		assert manejador is not None and not getattr(manejador, "provisional", False)


# ── Diálogos (wx) ────────────────────────────────────────────────────────────


@pytest.fixture
def interfaz(app_wx):
	creada = p5_comun.con_interfaz()
	yield creada
	api.fijar_interfaz(None)


def test_dialogos_pasan_revisar_teclado(zc, interfaz):
	ventanas = zc.instancia.ventanas_para_revisar(None)
	assert len(ventanas) == 2
	try:
		for ventana in ventanas:
			assert p5_comun.problemas_de_teclado(ventana) == [], ventana.GetTitle()
	finally:
		for ventana in ventanas:
			ventana.Destroy()


def test_dialogo_muestra_las_tareas_y_valida_el_editor(zc, motor, interfaz, tmp_path):
	_perfil(zc, motor, tmp_path, motor.DOS_SENTIDOS)
	ventana = p5_comun.modulo(NOMBRE, "ventana")
	dialogo = ventana.DialogoTareas(zc.instancia, None)
	editor = ventana.DialogoPerfil(zc, None, motor.Perfil("", "C:\\a", "C:\\a"), ["Prueba"])
	try:
		assert dialogo.lista.numero_filas() == 1
		assert dialogo.lista.valores_fila(0)[:2] == ["Prueba", "Dos sentidos"]
		assert editor.error() == "Escriba un nombre para la tarea."
		editor.nombre.SetValue("prueba")
		assert "Ya hay una tarea" in editor.error()
		editor.nombre.SetValue("Otra")
		assert "misma carpeta" in editor.error()
		editor.destino.SetValue("D:\\b")
		assert editor.error() == ""
		assert editor.perfil().modo == motor.ESPEJO
	finally:
		dialogo.Destroy()
		editor.Destroy()
