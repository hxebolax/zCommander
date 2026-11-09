# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor de operaciones: copiar, mover, conflictos, verificación, cancelación y carriles."""

from __future__ import annotations

import os
import time

import pytest

from app.core.tareas import ejecutor_directo
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar
from app.services.operaciones.gestor import GestorOperaciones
from app.services.operaciones.modelo import AccionConflicto, AccionError, Estado, Politica, RespuestaConflicto
from app.services.vfs.local import ProveedorLocal


class DecisorFalso:
	def __init__(self, accion=AccionConflicto.OMITIR) -> None:
		self.accion = accion
		self.listas: list[list] = []
		self.elecciones: list[str] = []

	def resolver_conflictos(self, operacion, conflictos):
		self.listas.append(list(conflictos))
		return [RespuestaConflicto(self.accion) for _ in conflictos]

	def preguntar_conflicto(self, operacion, conflicto):
		return RespuestaConflicto(self.accion)

	def preguntar_error(self, operacion, pregunta):
		return AccionError.OMITIR

	def elegir(self, titulo, texto, opciones, predeterminada=0, escape=-1, operacion=None):
		self.elecciones.append(titulo)
		return 0

	def pedir_texto(self, titulo, texto, valor="", oculto=False, operacion=None):
		return None


@pytest.fixture
def local():
	return ProveedorLocal()


def _arbol(base):
	(base / "a.txt").write_text("uno", encoding="utf-8")
	(base / "sub").mkdir()
	(base / "sub" / "b.txt").write_text("dos" * 1000, encoding="utf-8")
	(base / "sub" / "vacia").mkdir()


def _lanzar(decisor, operacion):
	gestor = GestorOperaciones(decisor, max_paralelas=2, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)
	return operacion


def test_copia_simple(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	_arbol(origen)
	entradas = local.listar(str(origen))
	op = _lanzar(DecisorFalso(), OperacionCopiar(local, entradas, local, str(destino), OpcionesCopia(verificar=True)))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (destino / "sub" / "b.txt").read_text(encoding="utf-8") == "dos" * 1000
	assert (destino / "sub" / "vacia").is_dir()
	assert not any(n.startswith("~zc") for n in os.listdir(destino))
	assert op.instantanea().archivos_hechos == 2
	assert "Copiar 2 elementos" in op.descripcion()


def test_lista_de_conflictos_y_politicas(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	(origen / "x.txt").write_text("nuevo", encoding="utf-8")
	(destino / "x.txt").write_text("viejo", encoding="utf-8")
	entradas = local.listar(str(origen))
	decisor = DecisorFalso(AccionConflicto.OMITIR)
	_lanzar(decisor, OperacionCopiar(local, entradas, local, str(destino)))
	assert len(decisor.listas) == 1 and (destino / "x.txt").read_text(encoding="utf-8") == "viejo"
	decisor = DecisorFalso(AccionConflicto.SOBRESCRIBIR)
	_lanzar(decisor, OperacionCopiar(local, entradas, local, str(destino)))
	assert (destino / "x.txt").read_text(encoding="utf-8") == "nuevo"
	_lanzar(DecisorFalso(), OperacionCopiar(local, entradas, local, str(destino), OpcionesCopia(politica=Politica.RENOMBRAR_COPIA)))
	assert (destino / "x (2).txt").exists()


def test_sobrescribir_si_mas_antiguo(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	(origen / "x.txt").write_text("nuevo", encoding="utf-8")
	(destino / "x.txt").write_text("destino reciente", encoding="utf-8")
	antiguo = time.time() - 3600
	os.utime(origen / "x.txt", (antiguo, antiguo))
	entradas = local.listar(str(origen))
	opciones = OpcionesCopia(politica=Politica.SOBRESCRIBIR_SI_MAS_ANTIGUO)
	op = _lanzar(DecisorFalso(), OperacionCopiar(local, entradas, local, str(destino), opciones))
	assert (destino / "x.txt").read_text(encoding="utf-8") == "destino reciente"
	assert op.instantanea().omitidos == 1


def test_mover_mismo_volumen_y_deshacer(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	_arbol(origen)
	entradas = local.listar(str(origen))
	op = _lanzar(DecisorFalso(), OperacionCopiar(local, entradas, local, str(destino), mover=True))
	assert op.estado == Estado.TERMINADA, op.errores
	assert not (origen / "a.txt").exists() and (destino / "sub" / "b.txt").exists()
	from app.services.operaciones.deshacer import RegistroDeshacer

	resultado = RegistroDeshacer().deshacer(op.deshacer)
	assert resultado.hechos == 2 and (origen / "sub" / "b.txt").exists()


def test_no_copiar_en_si_misma(tmp_path, local):
	(tmp_path / "c").mkdir()
	entradas = [local.info(str(tmp_path / "c"))]
	op = _lanzar(DecisorFalso(), OperacionCopiar(local, entradas, local, str(tmp_path / "c")))
	assert op.estado == Estado.FALLIDA
	assert "dentro de sí misma" in op.errores[0].mensaje


def test_cancelar(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	for i in range(200):
		(origen / f"f{i}.bin").write_bytes(os.urandom(20000))
	entradas = local.listar(str(origen))
	gestor = GestorOperaciones(DecisorFalso(), ejecutor_interfaz=ejecutor_directo)
	op = gestor.lanzar(OperacionCopiar(local, entradas, local, str(destino)))
	op.cancelar()
	assert gestor.esperar(30)
	assert op.estado in (Estado.CANCELADA, Estado.TERMINADA)
	assert not any(n.startswith("~zc") for n in os.listdir(destino))
	gestor.apagar(1)


def test_carriles_en_serie(tmp_path, local):
	"""Dos copias al mismo volumen no se solapan."""
	origen = tmp_path / "o"
	origen.mkdir()
	(origen / "a.txt").write_text("x" * 100000, encoding="utf-8")
	entradas = local.listar(str(origen))
	gestor = GestorOperaciones(DecisorFalso(), max_paralelas=4, ejecutor_interfaz=ejecutor_directo)
	ops = []
	for i in range(3):
		(tmp_path / f"d{i}").mkdir()
		ops.append(gestor.lanzar(OperacionCopiar(local, entradas, local, str(tmp_path / f"d{i}"))))
	assert gestor.esperar(30)
	intervalos = sorted((o.instantanea().inicio, o.instantanea().fin) for o in ops)
	for (_i1, f1), (i2, _f2) in zip(intervalos, intervalos[1:], strict=False):
		assert i2 >= f1 - 0.01
	gestor.apagar(1)


def test_pausa_y_reanudar(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	for i in range(50):
		(origen / f"f{i}.bin").write_bytes(os.urandom(50000))
	entradas = local.listar(str(origen))
	gestor = GestorOperaciones(DecisorFalso(), ejecutor_interfaz=ejecutor_directo)
	op = OperacionCopiar(local, entradas, local, str(destino))
	gestor.lanzar(op)
	op.pausar()
	time.sleep(0.3)
	op.reanudar()
	assert gestor.esperar(30)
	assert op.estado == Estado.TERMINADA
	assert len(os.listdir(destino)) == 50
	gestor.apagar(1)


def test_eliminar_definitivo_con_solo_lectura(tmp_path, local):
	from app.services import formato
	from app.services.operaciones.eliminar import OperacionEliminar
	from app.services.windows import atributos

	_arbol(tmp_path)
	atributos.cambiar_atributos(str(tmp_path / "sub" / "b.txt"), poner=formato.SOLO_LECTURA)
	decisor = DecisorFalso()
	entradas = [e for e in local.listar(str(tmp_path)) if e.nombre in ("sub", "a.txt")]
	op = _lanzar(decisor, OperacionEliminar(local, entradas, papelera=False))
	assert op.estado == Estado.TERMINADA, op.errores
	assert not (tmp_path / "sub").exists() and not (tmp_path / "a.txt").exists()
	assert decisor.elecciones == ["Archivo de solo lectura"]


def test_todo_omitido_y_patron_vacio_terminan_bien(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	(origen / "x.txt").write_text("1", encoding="utf-8")
	(destino / "x.txt").write_text("2", encoding="utf-8")
	entradas = local.listar(str(origen))
	op = _lanzar(DecisorFalso(AccionConflicto.OMITIR), OperacionCopiar(local, entradas, local, str(destino)))
	assert op.estado == Estado.TERMINADA, op.errores
	op = _lanzar(DecisorFalso(), OperacionCopiar(local, entradas, local, str(destino), OpcionesCopia(patron="*.nada")))
	assert op.estado == Estado.TERMINADA, op.errores


def test_lanzar_desde_operacion_falla():
	import threading

	gestor = GestorOperaciones(DecisorFalso(), ejecutor_interfaz=ejecutor_directo)
	errores = []

	def en_hilo():
		try:
			gestor.lanzar(OperacionCopiar(ProveedorLocal(), [], ProveedorLocal(), "C:\\"))
		except RuntimeError as error:
			errores.append(error)

	hilo = threading.Thread(target=en_hilo, name="operaciones_0")
	hilo.start()
	hilo.join()
	assert errores
	gestor.apagar(1)


def test_mismo_nombre_desde_dos_carpetas_no_se_pisa(tmp_path, local):
	(tmp_path / "a").mkdir()
	(tmp_path / "b").mkdir()
	(tmp_path / "d").mkdir()
	(tmp_path / "a" / "informe.txt").write_text("de a", encoding="utf-8")
	(tmp_path / "b" / "informe.txt").write_text("de b", encoding="utf-8")
	entradas = [local.info(str(tmp_path / "a" / "informe.txt")), local.info(str(tmp_path / "b" / "informe.txt"))]
	opciones = OpcionesCopia(politica=Politica.SOBRESCRIBIR)
	op = _lanzar(DecisorFalso(), OperacionCopiar(local, entradas, local, str(tmp_path / "d"), opciones, mover=True))
	assert op.estado == Estado.TERMINADA, op.errores
	contenidos = sorted(p.read_text(encoding="utf-8") for p in (tmp_path / "d").iterdir())
	assert contenidos == ["de a", "de b"]


def test_sobrescribir_destino_de_solo_lectura(tmp_path, local):
	from app.services import formato
	from app.services.windows import atributos

	(tmp_path / "o").mkdir()
	(tmp_path / "d").mkdir()
	(tmp_path / "o" / "x.txt").write_text("nuevo", encoding="utf-8")
	(tmp_path / "d" / "x.txt").write_text("viejo", encoding="utf-8")
	atributos.cambiar_atributos(str(tmp_path / "d" / "x.txt"), poner=formato.SOLO_LECTURA)
	opciones = OpcionesCopia(politica=Politica.SOBRESCRIBIR)
	op = _lanzar(DecisorFalso(), OperacionCopiar(local, local.listar(str(tmp_path / "o")), local, str(tmp_path / "d"), opciones))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (tmp_path / "d" / "x.txt").read_text(encoding="utf-8") == "nuevo"
	assert not any(p.name.startswith("~zc") for p in (tmp_path / "d").iterdir())


def test_renombrar_ciclo_y_deshacer(tmp_path, local):
	from app.services.operaciones.deshacer import RegistroDeshacer
	from app.services.operaciones.renombrar import OperacionRenombrar

	(tmp_path / "a.txt").write_text("A", encoding="utf-8")
	(tmp_path / "b.txt").write_text("B", encoding="utf-8")
	op = _lanzar(DecisorFalso(), OperacionRenombrar(local, [(str(tmp_path / "a.txt"), "b.txt"), (str(tmp_path / "b.txt"), "a.txt")]))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "B"
	RegistroDeshacer().deshacer(op.deshacer)
	assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "A"


def test_renombrar_en_lista_de_resultados(tmp_path):
	"""En búsqueda, cesta o vista plana no hay carpeta superior: se usa la carpeta real."""
	from app.services.operaciones.renombrar import OperacionRenombrar
	from app.services.vfs.resultados import ProveedorResultados

	(tmp_path / "sub").mkdir()
	(tmp_path / "sub" / "uno.txt").write_text("1", encoding="utf-8")
	lista = ProveedorResultados("Resultados", [str(tmp_path / "sub" / "uno.txt")])
	op = _lanzar(DecisorFalso(), OperacionRenombrar(lista, [(str(tmp_path / "sub" / "uno.txt"), "dos.txt")]))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (tmp_path / "sub" / "dos.txt").is_file()
	assert lista.rutas == [str(tmp_path / "sub" / "dos.txt")]
