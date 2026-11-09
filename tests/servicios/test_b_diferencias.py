# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque B: diferencias entre carpetas, marcas de Comparar carpetas y la operación de sincronizar (8.13). Sin wx."""

from __future__ import annotations

import os
import time

import pytest

from app.core.tareas import ejecutor_directo
from app.services import diferencias_carpetas as dc
from app.services.diferencias_carpetas import Accion, Criterio, Direccion, Estado
from app.services.operaciones.copiar import OpcionesCopia
from app.services.operaciones.gestor import GestorOperaciones
from app.services.operaciones.modelo import AccionError, Estado as EstadoOp, RespuestaConflicto
from app.services.operaciones.sincronizar import OperacionSincronizar
from app.services.vfs import base
from app.services.vfs.local import ProveedorLocal


class DecisorFalso:
	def resolver_conflictos(self, operacion, conflictos):
		raise AssertionError("Sincronizar no debe preguntar conflictos: usa Sobrescribir")

	def preguntar_conflicto(self, operacion, conflicto):
		return RespuestaConflicto("sobrescribir")

	def preguntar_error(self, operacion, pregunta):
		return AccionError.OMITIR

	def elegir(self, titulo, texto, opciones, predeterminada=0, escape=-1, operacion=None):
		return 0

	def pedir_texto(self, titulo, texto, valor="", oculto=False, operacion=None):
		return None


@pytest.fixture
def local():
	return ProveedorLocal()


def _fecha(ruta, segundos_atras):
	marca = time.time() - segundos_atras
	os.utime(ruta, (marca, marca))


@pytest.fixture
def dos(tmp_path):
	"""izq: igual, nuevo (más reciente), solo_izq, sub/a; der: igual, nuevo (viejo), solo_der."""
	izq, der = tmp_path / "izq", tmp_path / "der"
	izq.mkdir()
	der.mkdir()
	for carpeta in (izq, der):
		(carpeta / "igual.txt").write_text("igual", encoding="utf-8")
		_fecha(carpeta / "igual.txt", 3600)
	(izq / "nuevo.txt").write_text("versión nueva", encoding="utf-8")
	(der / "nuevo.txt").write_text("versión vieja", encoding="utf-8")
	_fecha(der / "nuevo.txt", 7200)
	(izq / "solo_izq.txt").write_text("i", encoding="utf-8")
	(der / "solo_der.txt").write_text("d", encoding="utf-8")
	(izq / "sub").mkdir()
	(izq / "sub" / "a.txt").write_text("a", encoding="utf-8")
	return izq, der


def _comparar(local, izq, der, **opciones):
	return dc.comparar((local, str(izq)), (local, str(der)), **opciones)


def test_comparar_marca_el_mas_reciente_solo_a_la_izquierda(local, dos):
	izq, der = dos
	(der / "solo_der.txt").unlink()
	(izq / "solo_izq.txt").unlink()
	diferencias = _comparar(local, izq, der, criterio=Criterio.FECHA, subcarpetas=False, solo_archivos=True)
	marcas_i, marcas_d = dc.marcas(diferencias)
	assert marcas_i == {"nuevo.txt"}
	assert marcas_d == set()
	assert dc.anuncio_marcas(len(marcas_i), len(marcas_d)) == "Diferencias: 1 a la izquierda, 0 a la derecha"


def test_comparar_existencia_y_criterios(local, dos):
	izq, der = dos
	solo_nombre = _comparar(local, izq, der, criterio=Criterio.NOMBRE, subcarpetas=False, solo_archivos=True)
	assert {d.relativo: d.estado for d in solo_nombre} == {"solo_izq.txt": Estado.SOLO_IZQUIERDA, "solo_der.txt": Estado.SOLO_DERECHA}
	# Misma fecha y distinto tamaño: con «nombre, fecha y tamaño» se marcan los dos.
	(der / "igual.txt").write_text("igual pero más largo", encoding="utf-8")
	_fecha(der / "igual.txt", 3600)
	os.utime(der / "igual.txt", (os.stat(izq / "igual.txt").st_mtime,) * 2)
	por_tamano = {d.relativo: d.estado for d in _comparar(local, izq, der, criterio=Criterio.TAMANO, subcarpetas=False)}
	assert por_tamano["igual.txt"] == Estado.DISTINTOS
	marcas_i, marcas_d = dc.marcas(_comparar(local, izq, der, criterio=Criterio.TAMANO, subcarpetas=False))
	assert "igual.txt" in marcas_i and "igual.txt" in marcas_d
	assert "igual.txt" not in {d.relativo for d in _comparar(local, izq, der, criterio=Criterio.FECHA, subcarpetas=False)}


def test_comparar_contenido(local, tmp_path):
	izq, der = tmp_path / "a", tmp_path / "b"
	izq.mkdir()
	der.mkdir()
	(izq / "x.txt").write_bytes(b"abcd")
	(der / "x.txt").write_bytes(b"abce")
	(izq / "y.txt").write_bytes(b"mismo")
	(der / "y.txt").write_bytes(b"mismo")
	_fecha(der / "y.txt", 9999)  # distinta fecha, mismo contenido: iguales
	diferencias = {d.relativo: d.estado for d in _comparar(local, izq, der, criterio=Criterio.CONTENIDO)}
	assert "y.txt" not in diferencias
	assert diferencias["x.txt"] in (Estado.DISTINTOS, Estado.IZQUIERDA_MAS_RECIENTE, Estado.DERECHA_MAS_RECIENTE)
	assert dc.mismo_contenido(local, str(izq / "y.txt"), local, str(der / "y.txt"), bloque=2)


def test_tolerancia_fat(local, tmp_path):
	izq, der = tmp_path / "a", tmp_path / "b"
	izq.mkdir()
	der.mkdir()
	(izq / "f.txt").write_text("1", encoding="utf-8")
	(der / "f.txt").write_text("1", encoding="utf-8")
	marca = time.time() - 100
	os.utime(izq / "f.txt", (marca, marca))
	os.utime(der / "f.txt", (marca - 1.5, marca - 1.5))
	assert _comparar(local, izq, der, criterio=Criterio.FECHA) == []
	assert _comparar(local, izq, der, criterio=Criterio.FECHA, tolerancia_s=0)[0].estado == Estado.IZQUIERDA_MAS_RECIENTE


def test_sincronizar_izquierda_a_derecha_propone_copiar_lo_que_falta(local, dos):
	izq, der = dos
	filas = dc.proponer(_comparar(local, izq, der), Direccion.A_LA_DERECHA)
	acciones = {f.relativo: f.accion for f in filas}
	assert acciones["solo_izq.txt"] == Accion.COPIAR_DERECHA
	assert acciones["sub"] == Accion.COPIAR_DERECHA
	assert acciones["nuevo.txt"] == Accion.COPIAR_DERECHA
	assert acciones["solo_der.txt"] == Accion.NADA
	assert "sub\\a.txt" not in acciones  # la carpeta que falta es una sola fila
	assert Accion.COPIAR_DERECHA.texto == "Copiar a la derecha"
	con_borrado = {f.relativo: f.accion for f in dc.proponer(_comparar(local, izq, der), Direccion.A_LA_DERECHA, True)}
	assert con_borrado["solo_der.txt"] == Accion.ELIMINAR_DERECHA


def test_propuestas_en_los_dos_sentidos_y_derecha_a_izquierda(local, dos):
	izq, der = dos
	ambos = {f.relativo: f.accion for f in dc.proponer(_comparar(local, izq, der), Direccion.AMBOS)}
	assert ambos["solo_der.txt"] == Accion.COPIAR_IZQUIERDA
	assert ambos["solo_izq.txt"] == Accion.COPIAR_DERECHA
	assert ambos["nuevo.txt"] == Accion.COPIAR_DERECHA
	al_reves = {f.relativo: f.accion for f in dc.proponer(_comparar(local, izq, der), Direccion.A_LA_IZQUIERDA, True)}
	assert al_reves["solo_der.txt"] == Accion.COPIAR_IZQUIERDA
	assert al_reves["solo_izq.txt"] == Accion.ELIMINAR_IZQUIERDA
	assert al_reves["nuevo.txt"] == Accion.NADA  # el destino es más reciente: no se pisa


def test_tecla_borrar_y_acciones_posibles(local, dos):
	izq, der = dos
	filas = {f.relativo: f for f in _comparar(local, izq, der)}
	assert dc.accion_borrar(filas["solo_der.txt"], Direccion.A_LA_DERECHA) == Accion.ELIMINAR_DERECHA
	assert dc.accion_borrar(filas["solo_izq.txt"], Direccion.A_LA_DERECHA) is None
	assert dc.accion_borrar(filas["solo_izq.txt"], Direccion.AMBOS) == Accion.ELIMINAR_IZQUIERDA
	assert dc.accion_borrar(filas["nuevo.txt"], Direccion.AMBOS) is None
	assert not dc.accion_posible(filas["solo_der.txt"], Accion.COPIAR_DERECHA)
	assert dc.describir_lado(None) == "No existe"


def test_patron_y_tipo_distinto(local, tmp_path):
	izq, der = tmp_path / "a", tmp_path / "b"
	izq.mkdir()
	der.mkdir()
	(izq / "x.mp3").write_text("1", encoding="utf-8")
	(izq / "x.txt").write_text("1", encoding="utf-8")
	(izq / "choque").write_text("archivo", encoding="utf-8")
	(der / "choque").mkdir()
	(der / "choque" / "dentro.txt").write_text("1", encoding="utf-8")
	filas = {d.relativo: d for d in _comparar(local, izq, der, patron="*.mp3;choque")}
	assert "x.txt" not in filas and "x.mp3" in filas
	assert filas["choque"].estado == Estado.TIPO_DISTINTO
	assert "choque\\dentro.txt" not in filas
	assert dc.accion_propuesta(filas["choque"], Direccion.A_LA_DERECHA) == Accion.NADA
	assert dc.texto_accion(filas["choque"].con_accion(Accion.NADA)) == "Archivo frente a carpeta: nada"


def _lanzar(operacion):
	gestor = GestorOperaciones(DecisorFalso(), max_paralelas=2, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)
	return operacion


def test_operacion_sincronizar_copia_y_borra(local, dos):
	izq, der = dos
	filas = dc.proponer(_comparar(local, izq, der), Direccion.A_LA_DERECHA, eliminar_sobrantes=True)
	operacion = OperacionSincronizar((local, str(izq)), (local, str(der)), filas, OpcionesCopia(), papelera=False)
	assert "Sincronizar" in operacion.descripcion()
	assert operacion.carriles
	_lanzar(operacion)
	assert operacion.estado == EstadoOp.TERMINADA, operacion.errores
	assert (der / "solo_izq.txt").read_text(encoding="utf-8") == "i"
	assert (der / "sub" / "a.txt").read_text(encoding="utf-8") == "a"
	assert (der / "nuevo.txt").read_text(encoding="utf-8") == "versión nueva"
	assert not (der / "solo_der.txt").exists()
	assert not any(n.startswith("~zc") for n in os.listdir(der))
	assert _comparar(local, izq, der) == []
	assert operacion.instantanea().archivos_hechos >= 3


def test_sincronizar_crea_carpetas_de_destino(local, tmp_path):
	izq, der = tmp_path / "a", tmp_path / "b"
	(izq / "uno" / "dos").mkdir(parents=True)
	(izq / "uno" / "dos" / "f.txt").write_text("f", encoding="utf-8")
	(der / "uno").mkdir(parents=True)
	fila = dc.Diferencia("uno\\dos\\f.txt", local.info(str(izq / "uno" / "dos" / "f.txt")), None, Estado.SOLO_IZQUIERDA,
		Accion.COPIAR_DERECHA)
	_lanzar(OperacionSincronizar((local, str(izq)), (local, str(der)), [fila], papelera=False))
	assert (der / "uno" / "dos" / "f.txt").read_text(encoding="utf-8") == "f"


def test_sincronizar_se_cancela(local, dos):
	izq, der = dos
	filas = dc.proponer(_comparar(local, izq, der), Direccion.A_LA_DERECHA)
	operacion = OperacionSincronizar((local, str(izq)), (local, str(der)), filas, papelera=False)
	from app.services.operaciones.modelo import ContextoEjecucion

	cancelacion = base.Cancelacion()
	cancelacion.set = cancelacion.cancelar  # interfaz de TokenCancelacion que usa Operacion.cancelar
	ctx = ContextoEjecucion(cancelacion, DecisorFalso())
	ctx.operacion = operacion
	operacion.contexto = ctx
	cancelacion.cancelar()
	with pytest.raises(base.Cancelado):
		operacion.ejecutar(ctx)
	assert not (der / "solo_izq.txt").exists()


def test_resumen_acciones(local, dos):
	izq, der = dos
	filas = dc.proponer(_comparar(local, izq, der), Direccion.A_LA_DERECHA)
	assert dc.resumen_acciones(filas) == "Copiar a la derecha: 3"
	assert dc.resumen_acciones([]) == "Nada que hacer"
