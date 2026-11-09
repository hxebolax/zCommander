# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Correcciones del motor de operaciones: carpetas vacías, «Omitir todos», comprimir por elemento,
archivo frente a carpeta al sincronizar y deshacer copias de carpetas y carpetas de varios niveles.
"""

from __future__ import annotations

import os
import shutil
import zipfile

import pytest

from app.core.tareas import ejecutor_directo
from app.services import diferencias_carpetas as dc
from app.services.operaciones.comprimir import OpcionesComprimir, OperacionComprimir
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar
from app.services.operaciones.deshacer import AccionDeshacer, Paso, RegistroDeshacer, pasos_carpetas_nuevas
from app.services.operaciones.gestor import GestorOperaciones
from app.services.operaciones.modelo import AccionConflicto, AccionError, Estado, RespuestaConflicto
from app.services.vfs import base, registro_proveedores, resolver  # noqa: F401 - registra los proveedores
from app.services.vfs.local import ProveedorLocal


class DecisorFalso:
	def __init__(self, error=AccionError.OMITIR, eleccion: int = 0) -> None:
		self.error = error
		self.eleccion = eleccion
		self.errores: list = []
		self.elecciones: list[str] = []

	def resolver_conflictos(self, operacion, conflictos):
		return [RespuestaConflicto(AccionConflicto.OMITIR) for _ in conflictos]

	def preguntar_conflicto(self, operacion, conflicto):
		return RespuestaConflicto(AccionConflicto.OMITIR)

	def preguntar_error(self, operacion, pregunta):
		self.errores.append(pregunta)
		return self.error

	def elegir(self, titulo, texto, opciones, predeterminada=0, escape=-1, operacion=None):
		self.elecciones.append(texto)
		return self.eleccion

	def pedir_texto(self, titulo, texto, valor="", oculto=False, operacion=None):
		return None


@pytest.fixture
def local():
	return ProveedorLocal()


def _lanzar(operacion, decisor=None):
	gestor = GestorOperaciones(decisor or DecisorFalso(), max_paralelas=2, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)
	return operacion


def _arbol_con_vacias(raiz):
	"""a.txt, sub\\b.txt, sub\\vacia\\, solo_md\\nota.md y hueca\\ (vacía)."""
	raiz.mkdir()
	(raiz / "a.txt").write_text("uno", encoding="utf-8")
	(raiz / "sub" / "vacia").mkdir(parents=True)
	(raiz / "sub" / "b.txt").write_text("dos", encoding="utf-8")
	(raiz / "solo_md").mkdir()
	(raiz / "solo_md" / "nota.md").write_text("md", encoding="utf-8")
	(raiz / "hueca").mkdir()


# ── 1. Copiar también las carpetas vacías ───────────────────────────────────


def test_sin_carpetas_vacias_no_se_crean_al_copiar(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	_arbol_con_vacias(origen)
	destino.mkdir()
	opciones = OpcionesCopia(carpetas_vacias=False, patron="*.txt")
	op = _lanzar(OperacionCopiar(local, local.listar(str(origen)), local, str(destino), opciones))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (destino / "sub" / "b.txt").is_file()
	assert not (destino / "sub" / "vacia").exists()
	assert not (destino / "hueca").exists()
	# Con el patrón, «solo_md» quedaría vacía: tampoco se crea.
	assert not (destino / "solo_md").exists()


def test_con_carpetas_vacias_se_crean(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	_arbol_con_vacias(origen)
	destino.mkdir()
	op = _lanzar(OperacionCopiar(local, local.listar(str(origen)), local, str(destino), OpcionesCopia(carpetas_vacias=True)))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (destino / "sub" / "vacia").is_dir()
	assert (destino / "hueca").is_dir()


def test_sin_carpetas_vacias_al_mover_por_renombrado(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	_arbol_con_vacias(origen)
	destino.mkdir()
	op = _lanzar(OperacionCopiar(local, local.listar(str(origen)), local, str(destino), OpcionesCopia(carpetas_vacias=False),
		mover=True))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (destino / "sub" / "b.txt").is_file()
	assert not (destino / "sub" / "vacia").exists()
	assert not (destino / "hueca").exists()
	# Las carpetas de origen vacías se quitan igualmente.
	assert not (origen / "hueca").exists()
	assert not (origen / "sub").exists()


def test_sin_carpetas_vacias_al_mover_copiando(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	_arbol_con_vacias(origen)
	destino.mkdir()
	# Con patrón no se mueve por renombrado: se copia y se borra cada origen.
	opciones = OpcionesCopia(carpetas_vacias=False, patron="*.txt")
	op = _lanzar(OperacionCopiar(local, local.listar(str(origen)), local, str(destino), opciones, mover=True))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (destino / "sub" / "b.txt").is_file()
	assert not (destino / "sub" / "vacia").exists()
	assert not (destino / "hueca").exists()
	assert not (origen / "sub").exists()
	assert not (origen / "hueca").exists()
	# «solo_md» conserva lo que no coincidía con el patrón.
	assert (origen / "solo_md" / "nota.md").is_file()


# ── 2. «Omitir todos» en los errores que afectan a toda la operación ────────


def _copia_sin_espacio(tmp_path, local, monkeypatch):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	for nombre in ("1.txt", "2.txt", "3.txt"):
		(origen / nombre).write_text(nombre, encoding="utf-8")

	def sin_espacio(self, ctx, paso, tardio):
		raise base.SinEspacio("No queda espacio en el disco.", paso.destino)

	monkeypatch.setattr(OperacionCopiar, "_copiar_archivo", sin_espacio)
	return OperacionCopiar(local, local.listar(str(origen)), local, str(destino))


def test_omitir_todos_recuerda_la_decision(tmp_path, local, monkeypatch):
	decisor = DecisorFalso(error=AccionError.OMITIR_TODOS)
	op = _lanzar(_copia_sin_espacio(tmp_path, local, monkeypatch), decisor)
	assert len(decisor.errores) == 1
	assert len(op.fallidos) == 3


def test_omitir_pregunta_cada_vez(tmp_path, local, monkeypatch):
	decisor = DecisorFalso(error=AccionError.OMITIR)
	op = _lanzar(_copia_sin_espacio(tmp_path, local, monkeypatch), decisor)
	assert len(decisor.errores) == 3
	assert len(op.fallidos) == 3


# ── 3. Comprimir: un comprimido por cada elemento que ya existe ─────────────


@pytest.fixture
def por_elemento(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	origen.mkdir()
	destino.mkdir()
	(origen / "a.txt").write_text("a", encoding="utf-8")
	(origen / "b.txt").write_text("b", encoding="utf-8")
	with zipfile.ZipFile(destino / "a.zip", "w") as archivo:
		archivo.writestr("viejo.txt", "v")
	entradas = [local.info(str(origen / "a.txt")), local.info(str(origen / "b.txt"))]
	return origen, destino, entradas


def _nombres(ruta) -> list[str]:
	with zipfile.ZipFile(ruta) as archivo:
		return sorted(archivo.namelist())


def test_comprimir_por_elemento_pregunta_si_existe(por_elemento, local):
	origen, destino, entradas = por_elemento
	decisor = DecisorFalso(eleccion=0)  # Añadir
	op = _lanzar(OperacionComprimir(local, entradas, str(destino), OpcionesComprimir(por_elemento=True)), decisor)
	assert op.estado == Estado.TERMINADA, op.errores
	assert len(decisor.elecciones) == 1 and "a.zip" in decisor.elecciones[0]
	assert _nombres(destino / "a.zip") == ["a.txt", "viejo.txt"]
	assert _nombres(destino / "b.zip") == ["b.txt"]


@pytest.mark.parametrize(("decision", "esperado"), [
	("sustituir", {"a.zip": ["a.txt"]}),
	("renombrar", {"a.zip": ["viejo.txt"], "a (2).zip": ["a.txt"]}),
	("omitir", {"a.zip": ["viejo.txt"]}),
])
def test_comprimir_por_elemento_decision_elegida(por_elemento, local, decision, esperado):
	origen, destino, entradas = por_elemento
	decisor = DecisorFalso()
	op = _lanzar(OperacionComprimir(local, entradas, str(destino), OpcionesComprimir(por_elemento=True, si_existe=decision)),
		decisor)
	assert op.estado == Estado.TERMINADA, op.errores
	assert not decisor.elecciones
	for nombre, contenido in esperado.items():
		assert _nombres(destino / nombre) == contenido
	assert _nombres(destino / "b.zip") == ["b.txt"]


def test_comprimir_por_elemento_omitir_no_borra_ese_original_al_mover(por_elemento, local):
	origen, destino, entradas = por_elemento
	opciones = OpcionesComprimir(por_elemento=True, si_existe="omitir", mover=True)
	op = _lanzar(OperacionComprimir(local, entradas, str(destino), opciones))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (origen / "a.txt").exists()
	assert not (origen / "b.txt").exists()
	assert _nombres(destino / "a.zip") == ["viejo.txt"]


def test_comprimir_por_elemento_cancelar(por_elemento, local):
	origen, destino, entradas = por_elemento
	op = _lanzar(OperacionComprimir(local, entradas, str(destino), OpcionesComprimir(por_elemento=True)), DecisorFalso(eleccion=4))
	assert op.estado == Estado.CANCELADA
	assert _nombres(destino / "a.zip") == ["viejo.txt"]


# ── 4. Sincronizar: archivo frente a carpeta ─────────────────────────────────


def test_archivo_frente_a_carpeta_es_conflicto_propio(tmp_path, local):
	izq, der = tmp_path / "i", tmp_path / "d"
	izq.mkdir()
	der.mkdir()
	(izq / "choque").write_text("archivo", encoding="utf-8")
	(der / "choque").mkdir()
	filas = dc.comparar((local, str(izq)), (local, str(der)))
	for direccion in dc.Direccion:
		propuesta = dc.proponer(filas, direccion, eliminar_sobrantes=True)
		assert [f.accion for f in propuesta] == [dc.Accion.NADA]
		assert dc.texto_accion(propuesta[0]) == "Archivo frente a carpeta: nada"
		assert "1 archivo frente a carpeta" in dc.resumen_acciones(propuesta)
		assert dc.accion_posible(propuesta[0], dc.Accion.COPIAR_DERECHA) is False


# ── 5. Deshacer ──────────────────────────────────────────────────────────────


@pytest.fixture
def papelera_falsa(monkeypatch):
	"""Sustituye la papelera de Windows: borra y recuerda lo que se le envió."""
	enviados: list[list[str]] = []

	def enviar(rutas_):
		enviados.append(list(rutas_))
		for ruta in rutas_:
			if os.path.isdir(ruta):
				shutil.rmtree(ruta)
			else:
				os.remove(ruta)

	monkeypatch.setattr("app.services.windows.papelera.enviar", enviar)
	return enviados


def _copiar_carpeta(tmp_path, local):
	origen, destino = tmp_path / "o", tmp_path / "d"
	(origen / "carpeta" / "sub").mkdir(parents=True)
	(origen / "carpeta" / "uno.txt").write_text("uno", encoding="utf-8")
	(origen / "carpeta" / "sub" / "dos.txt").write_text("dos", encoding="utf-8")
	(origen / "carpeta" / "vacia").mkdir()
	destino.mkdir()
	op = _lanzar(OperacionCopiar(local, [local.info(str(origen / "carpeta"))], local, str(destino)))
	assert op.estado == Estado.TERMINADA, op.errores
	return destino / "carpeta", op.deshacer


def test_deshacer_copia_de_carpeta_intacta_la_manda_entera(tmp_path, local, papelera_falsa):
	copia, accion = _copiar_carpeta(tmp_path, local)
	resultado = RegistroDeshacer().deshacer(accion)
	assert papelera_falsa == [[str(copia)]]
	assert not copia.exists()
	assert resultado.omitidos == []


def test_deshacer_copia_de_carpeta_cambiada_solo_quita_lo_copiado(tmp_path, local, papelera_falsa):
	copia, accion = _copiar_carpeta(tmp_path, local)
	cambiado = copia / "sub" / "dos.txt"
	cambiado.write_text("modificado después", encoding="utf-8")
	nuevo = copia / "nuevo.txt"
	nuevo.write_text("añadido después", encoding="utf-8")
	resultado = RegistroDeshacer().deshacer(accion)
	enviados = [os.path.normcase(r) for lote in papelera_falsa for r in lote]
	assert os.path.normcase(str(copia)) not in enviados
	assert os.path.normcase(str(copia / "uno.txt")) in enviados
	assert cambiado.read_text(encoding="utf-8") == "modificado después"
	assert nuevo.exists()
	assert not (copia / "uno.txt").exists()
	assert not (copia / "vacia").exists()
	assert str(cambiado) in resultado.omitidos
	assert str(copia) in resultado.omitidos


def test_pasos_carpetas_nuevas_y_deshacer_varios_niveles(tmp_path):
	ruta = tmp_path / "a" / "b" / "c"
	pasos = pasos_carpetas_nuevas(str(ruta))
	assert [p.despues for p in pasos] == [str(tmp_path / "a"), str(tmp_path / "a" / "b"), str(ruta)]
	assert all(p.tipo == "quitar_carpeta" for p in pasos)
	os.makedirs(ruta)
	resultado = RegistroDeshacer().deshacer(AccionDeshacer("Crear la carpeta a\\b\\c", pasos))
	assert resultado.hechos == 3
	assert not (tmp_path / "a").exists()


def test_deshacer_varios_niveles_no_quita_lo_que_ya_no_esta_vacio(tmp_path):
	(tmp_path / "a").mkdir()
	ruta = tmp_path / "a" / "b" / "c"
	pasos = pasos_carpetas_nuevas(str(ruta))
	assert [p.despues for p in pasos] == [str(tmp_path / "a" / "b"), str(ruta)]
	os.makedirs(ruta)
	(tmp_path / "a" / "b" / "otro.txt").write_text("x", encoding="utf-8")
	# El orden de los pasos no importa: se quitan de dentro afuera.
	resultado = RegistroDeshacer().deshacer(AccionDeshacer("Crear", list(reversed(pasos))))
	assert not ruta.exists()
	assert (tmp_path / "a" / "b").is_dir()
	assert resultado.omitidos == [str(tmp_path / "a" / "b")]


def test_deshacer_un_solo_paso_de_carpeta_sigue_funcionando(tmp_path):
	carpeta = tmp_path / "x"
	carpeta.mkdir()
	resultado = RegistroDeshacer().deshacer(AccionDeshacer("Crear", [Paso("quitar_carpeta", str(carpeta))]))
	assert resultado.hechos == 1 and not carpeta.exists()
