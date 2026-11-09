# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Operación de atributos, fechas y permisos (bloque E, sección 8.9)."""

from __future__ import annotations

import os
import stat
import time

import pytest

from app.core.tareas import ejecutor_directo
from app.services import formato
from app.services.operaciones import atributos as at
from app.services.operaciones.gestor import GestorOperaciones
from app.services.operaciones.modelo import Estado
from app.services.vfs import base
from app.services.vfs.local import ProveedorLocal
from app.services.vfs.resultados import ProveedorResultados
from app.services.windows import atributos as atr_win


class _Decisor:
	def resolver_conflictos(self, operacion, conflictos):
		return None

	def preguntar_conflicto(self, operacion, conflicto):
		raise AssertionError

	def preguntar_error(self, operacion, pregunta):
		raise AssertionError

	def elegir(self, *args, **kwargs):
		return 0

	def pedir_texto(self, *args, **kwargs):
		return None


def _ejecutar(operacion):
	gestor = GestorOperaciones(_Decisor(), max_paralelas=1, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)
	return operacion


@pytest.fixture
def arbol(tmp_path):
	(tmp_path / "a.txt").write_text("a", encoding="utf-8")
	(tmp_path / "sub").mkdir()
	(tmp_path / "sub" / "b.txt").write_text("b", encoding="utf-8")
	(tmp_path / "sub" / "hondo").mkdir()
	(tmp_path / "sub" / "hondo" / "c.txt").write_text("c", encoding="utf-8")
	yield tmp_path
	# Quitar el solo lectura para que pytest pueda borrar la carpeta temporal.
	for carpeta, _dirs, archivos in os.walk(tmp_path):
		for nombre in archivos:
			os.chmod(os.path.join(carpeta, nombre), stat.S_IWRITE)


def _entradas(local, carpeta):
	return {e.nombre: e for e in local.listar(str(carpeta))}


def test_poner_y_quitar_atributos(arbol):
	local = ProveedorLocal()
	entrada = _entradas(local, arbol)["a.txt"]
	op = _ejecutar(at.OperacionAtributos(local, [entrada], at.CambiosAtributos(poner=formato.SOLO_LECTURA | formato.OCULTO)))
	assert op.estado == Estado.TERMINADA, op.errores
	valor = atr_win.leer_atributos(str(arbol / "a.txt"))
	assert valor & formato.SOLO_LECTURA and valor & formato.OCULTO
	assert op.instantanea().archivos_hechos == 1
	assert "a.txt" in op.descripcion()
	assert op.carriles == frozenset()  # metadatos en disco local sin recursión
	# Quitar solo uno de los dos.
	entrada = _entradas(local, arbol)["a.txt"]
	_ejecutar(at.OperacionAtributos(local, [entrada], at.CambiosAtributos(quitar=formato.OCULTO)))
	valor = atr_win.leer_atributos(str(arbol / "a.txt"))
	assert valor & formato.SOLO_LECTURA and not valor & formato.OCULTO


def test_fechas_aunque_sea_de_solo_lectura(arbol):
	local = ProveedorLocal()
	os.chmod(arbol / "a.txt", stat.S_IREAD)
	entrada = _entradas(local, arbol)["a.txt"]
	modificado = at.interpretar_fecha("2020-01-02 03:04:05")
	creado = at.interpretar_fecha("2019-05-06 07:08:09")
	op = _ejecutar(at.OperacionAtributos(local, [entrada], at.CambiosAtributos(modificado=modificado, creado=creado)))
	assert not op.errores
	st = os.stat(arbol / "a.txt")
	assert abs(st.st_mtime - modificado) < 1
	assert abs(st.st_birthtime - creado) < 1
	assert time.localtime(st.st_mtime)[:6] == (2020, 1, 2, 3, 4, 5)


def test_quitar_solo_lectura_y_cambiar_fecha(arbol):
	local = ProveedorLocal()
	os.chmod(arbol / "a.txt", stat.S_IREAD)
	entrada = _entradas(local, arbol)["a.txt"]
	marca = at.interpretar_fecha("2022-02-02")
	op = _ejecutar(at.OperacionAtributos(local, [entrada], at.CambiosAtributos(quitar=formato.SOLO_LECTURA, modificado=marca)))
	assert not op.errores
	assert os.access(arbol / "a.txt", os.W_OK)
	assert abs(os.stat(arbol / "a.txt").st_mtime - marca) < 1


def test_recursivo(arbol):
	local = ProveedorLocal()
	sub = _entradas(local, arbol)["sub"]
	op = at.OperacionAtributos(local, [sub], at.CambiosAtributos(poner=formato.OCULTO, recursivo=True))
	assert op.carriles  # con recursión declara el volumen
	_ejecutar(op)
	assert not op.errores
	for ruta in (arbol / "sub", arbol / "sub" / "b.txt", arbol / "sub" / "hondo", arbol / "sub" / "hondo" / "c.txt"):
		assert atr_win.leer_atributos(str(ruta)) & formato.OCULTO, ruta
	assert not atr_win.leer_atributos(str(arbol / "a.txt")) & formato.OCULTO
	assert op.instantanea().archivos_hechos == 4


def test_sin_recursion_no_toca_el_contenido(arbol):
	local = ProveedorLocal()
	sub = _entradas(local, arbol)["sub"]
	_ejecutar(at.OperacionAtributos(local, [sub], at.CambiosAtributos(poner=formato.OCULTO)))
	assert atr_win.leer_atributos(str(arbol / "sub")) & formato.OCULTO
	assert not atr_win.leer_atributos(str(arbol / "sub" / "b.txt")) & formato.OCULTO


def test_lista_de_resultados(arbol):
	resultados = ProveedorResultados("Búsqueda", [str(arbol / "a.txt"), str(arbol / "sub" / "b.txt")])
	entradas = resultados.listar("")
	op = _ejecutar(at.OperacionAtributos(resultados, entradas, at.CambiosAtributos(poner=formato.ARCHIVO | formato.NO_INDEXAR)))
	assert not op.errores
	for ruta in (arbol / "a.txt", arbol / "sub" / "b.txt"):
		assert atr_win.leer_atributos(str(ruta)) & formato.NO_INDEXAR


def test_error_de_un_elemento_no_para_el_resto(arbol):
	local = ProveedorLocal()
	buena = _entradas(local, arbol)["a.txt"]
	mala = base.Entrada("falta.txt", str(arbol / "falta.txt"))
	op = _ejecutar(at.OperacionAtributos(local, [mala, buena], at.CambiosAtributos(poner=formato.OCULTO)))
	assert op.estado == Estado.TERMINADA_CON_ERRORES
	assert len(op.errores) == 1 and op.errores[0].ruta.endswith("falta.txt")
	assert atr_win.leer_atributos(str(arbol / "a.txt")) & formato.OCULTO


def test_permisos_en_un_proveedor_que_no_los_admite(arbol):
	local = ProveedorLocal()
	entrada = _entradas(local, arbol)["a.txt"]
	op = _ejecutar(at.OperacionAtributos(local, [entrada], at.CambiosAtributos(permisos=0o644)))
	assert op.errores and "permisos" in op.errores[0].mensaje


def test_permisos_con_un_proveedor_que_los_admite():
	class Remoto(ProveedorLocal):
		esquema = "sftp"
		servidor = "ejemplo:22"

		def __init__(self):
			super().__init__()
			self.cambios = []

		def fijar_permisos(self, ruta, modo):
			self.cambios.append((ruta, modo))

	remoto = Remoto()
	entrada = base.Entrada("x.sh", "/home/x.sh", permisos=0o600)
	op = _ejecutar(at.OperacionAtributos(remoto, [entrada], at.CambiosAtributos(permisos=at.interpretar_permisos("755"))))
	assert not op.errores
	assert remoto.cambios == [("/home/x.sh", 0o755)]
	assert op.carriles == frozenset({"sftp:ejemplo:22"})


def test_estado_comun():
	ro = base.Entrada("a", "a", atributos=formato.SOLO_LECTURA)
	normal = base.Entrada("b", "b", atributos=formato.ARCHIVO)
	assert at.estado_comun([ro], formato.SOLO_LECTURA) is True
	assert at.estado_comun([normal], formato.SOLO_LECTURA) is False
	assert at.estado_comun([ro, normal], formato.SOLO_LECTURA) is None
	assert at.CambiosAtributos().vacio
	assert not at.CambiosAtributos(poner=1).vacio


def test_interpretar_fechas_y_permisos():
	assert time.localtime(at.interpretar_fecha("31/05/2024 18:20"))[:5] == (2024, 5, 31, 18, 20)
	assert time.localtime(at.interpretar_fecha(" 2024-05-31 "))[:3] == (2024, 5, 31)
	assert at.interpretar_fecha(at.texto_fecha(at.interpretar_fecha("2024-05-31 18:20:05"))) == at.interpretar_fecha("2024-05-31 18:20:05")
	for malo in ("ayer", "2024-13-01", "1900-01-01"):
		with pytest.raises(ValueError):
			at.interpretar_fecha(malo)
	assert at.interpretar_permisos("0644") == 0o644
	for malo in ("64", "888", "rwx"):
		with pytest.raises(ValueError):
			at.interpretar_permisos(malo)
