# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ganchos del sistema de archivos virtual en el motor de copia (diseño 2.0, 14.5, 14.6 y 18.2)."""

from __future__ import annotations

import io
import os
from typing import BinaryIO

import pytest

from app.plugins.api import pruebas
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar, pregunta_error
from app.services.operaciones.gestor import GestorOperaciones
from app.services.operaciones.modelo import Politica
from app.services.vfs import base
from app.services.vfs.local import ProveedorLocal


class Memoria(base.Proveedor):
	"""Proveedor en memoria con identidad de cuenta («mem:<cuenta>»)."""

	esquema = "mem"

	def __init__(self, cuenta: str = "ana", **capacidades) -> None:
		super().__init__()
		self.servidor = cuenta
		self.archivos: dict[str, bytes] = {}
		self.carpetas: set[str] = {"/"}
		self.escrituras: list[str] = []
		self.renombrados: list[tuple[str, str]] = []
		self.lotes: list[list[tuple[str, str]]] = []
		self.transferidos: list[str] = []
		self.admite_lote = False
		self.admite_transferir = False
		for clave, valor in capacidades.items():
			setattr(self.capacidades, clave, valor)

	def listar(self, ruta, cancelacion=None):
		hijos = []
		prefijo = ruta.rstrip("/") + "/"
		for nombre in [*self.archivos, *self.carpetas]:
			if nombre != ruta and nombre.startswith(prefijo) and "/" not in nombre[len(prefijo):]:
				hijos.append(self.info(nombre))
		return hijos

	def info(self, ruta):
		if ruta in self.carpetas:
			return base.Entrada(ruta.rsplit("/", 1)[-1] or "/", ruta, es_carpeta=True)
		if ruta in self.archivos:
			return base.Entrada(ruta.rsplit("/", 1)[-1], ruta, tamano=len(self.archivos[ruta]))
		raise base.NoEncontrado("no existe", ruta)

	def padre(self, ruta):
		return None if ruta == "/" else (ruta.rsplit("/", 1)[0] or "/")

	def unir(self, carpeta, nombre):
		return carpeta.rstrip("/") + "/" + nombre

	def raiz(self, ruta):
		return "/"

	def mostrar(self, ruta):
		return f"mem://{self.servidor}{ruta}"

	def mismo_volumen(self, ruta_a, ruta_b):
		return True  # «todo es el mismo volumen»: el motor no debe creerlo sin mirar la identidad

	def abrir_lectura(self, ruta) -> BinaryIO:
		return io.BytesIO(self.archivos[ruta])

	def abrir_escritura(self, ruta, tamano=-1):
		self.escrituras.append(ruta)
		proveedor = self

		class _Flujo(io.BytesIO):
			def close(self_flujo):
				proveedor.archivos[ruta] = self_flujo.getvalue()
				super().close()

		return _Flujo()

	def crear_carpeta(self, ruta):
		self.carpetas.add(ruta)

	def eliminar(self, ruta, recursivo=False, cancelacion=None):
		self.archivos.pop(ruta, None)
		self.carpetas.discard(ruta)

	def renombrar(self, origen, destino):
		self.renombrados.append((origen, destino))
		self.archivos[destino] = self.archivos.pop(origen)

	def transferir(self, origen, ruta_origen, ruta_destino, progreso, cancelacion):
		if not self.admite_transferir:
			return False
		with origen.abrir_lectura(ruta_origen) as fuente:
			self.archivos[ruta_destino] = fuente.read()
		self.transferidos.append(ruta_destino)
		progreso(1, 1)
		return True

	def transferir_lote(self, origen, pares, mover, progreso, cancelacion):
		if not self.admite_lote:
			return None
		self.lotes.append(list(pares))
		resultados = []
		for ruta_origen, ruta_destino in pares:
			with origen.abrir_lectura(ruta_origen) as fuente:
				self.archivos[ruta_destino] = fuente.read()
			resultados.append(base.ResultadoPar(ruta_origen, ruta_destino, True))
		return resultados


def _ejecutar(operacion) -> None:
	from app.core.tareas import ejecutor_directo

	gestor = GestorOperaciones(pruebas.DecisorFalso(), max_paralelas=1, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)


@pytest.fixture
def origen():
	memoria = Memoria("origen")
	memoria.archivos["/a.txt"] = b"uno"
	memoria.archivos["/b.txt"] = b"dos"
	return memoria


def _entradas(proveedor):
	return [proveedor.info("/a.txt"), proveedor.info("/b.txt")]


def test_transferir_lote_si_el_destino_lo_admite(origen):
	destino = Memoria("nube")
	destino.admite_lote = True
	operacion = OperacionCopiar(origen, _entradas(origen), destino, "/", OpcionesCopia(politica=Politica.SOBRESCRIBIR))
	_ejecutar(operacion)
	assert destino.lotes == [[("/a.txt", "/a.txt"), ("/b.txt", "/b.txt")]]
	assert destino.escrituras == []
	assert sorted(operacion.pares_hechos()) == [("/a.txt", "/a.txt"), ("/b.txt", "/b.txt")]


def test_transferir_por_archivo(origen):
	destino = Memoria("nube")
	destino.admite_transferir = True
	_ejecutar(OperacionCopiar(origen, _entradas(origen), destino, "/", OpcionesCopia(politica=Politica.SOBRESCRIBIR)))
	assert sorted(destino.transferidos) == ["/a.txt", "/b.txt"] and destino.escrituras == []


def test_copia_por_bloques_si_no_admite_nada_y_con_temporal(origen):
	destino = Memoria("nube")
	_ejecutar(OperacionCopiar(origen, _entradas(origen), destino, "/", OpcionesCopia(politica=Politica.SOBRESCRIBIR)))
	assert destino.archivos["/a.txt"] == b"uno"
	assert all(e.rsplit("/", 1)[-1].startswith("~zc") for e in destino.escrituras), "temporal y renombrado final"


def test_escritura_atomica_escribe_sin_temporal(origen):
	destino = Memoria("nube", escritura_atomica=True)
	_ejecutar(OperacionCopiar(origen, _entradas(origen), destino, "/", OpcionesCopia(politica=Politica.SOBRESCRIBIR)))
	assert sorted(destino.escrituras) == ["/a.txt", "/b.txt"]
	assert destino.renombrados == []


def test_mismo_esquema_distinta_cuenta_nunca_mueve_con_renombrar(origen):
	destino = Memoria("otra_cuenta")
	_ejecutar(OperacionCopiar(origen, _entradas(origen), destino, "/", OpcionesCopia(politica=Politica.SOBRESCRIBIR), mover=True))
	assert origen.renombrados == []
	assert all(o.rsplit("/", 1)[-1].startswith("~zc") for o, _d in destino.renombrados), "solo el temporal de la copia"
	assert destino.archivos["/a.txt"] == b"uno"
	assert "/a.txt" not in origen.archivos


def test_misma_cuenta_mueve_con_renombrar():
	unica = Memoria("ana")
	unica.archivos["/a.txt"] = b"uno"
	unica.carpetas.add("/destino")
	_ejecutar(OperacionCopiar(unica, [unica.info("/a.txt")], unica, "/destino", OpcionesCopia(), mover=True))
	assert unica.renombrados == [("/a.txt", "/destino/a.txt")]


def test_pregunta_error_lleva_el_codigo_32_de_un_archivo_abierto(tmp_path):
	"""Un archivo abierto en exclusiva por otro proceso da el ``winerror`` 32 en la pregunta (14.6)."""
	import subprocess
	import sys
	import time

	ruta = tmp_path / "abierto.txt"
	ruta.write_text("x", encoding="utf-8")
	# Otro proceso lo abre sin compartir (como haría Word) hasta que se le cierra.
	codigo = (
		"import ctypes, sys, time\n"
		"h = ctypes.windll.kernel32.CreateFileW(sys.argv[1], 0x80000000, 0, None, 3, 0x80, None)\n"
		"print('listo', flush=True)\n"
		"time.sleep(30)\n"
	)
	otro = subprocess.Popen([sys.executable, "-c", codigo, str(ruta)], stdout=subprocess.PIPE, text=True)
	try:
		assert otro.stdout.readline().strip() == "listo"
		time.sleep(0.2)
		# Mover un archivo abierto sin compartir: la API de Windows da ERROR_SHARING_VIOLATION (32);
		# el motor lo convierte en ErrorAcceso con la causa encadenada, como aquí.
		from app.services import errores

		try:
			os.replace(ruta, tmp_path / "movido.txt")
		except OSError as error:
			try:
				raise errores.convertir(error, str(ruta)) from error
			except base.ErrorArchivos as convertido:
				fallo = convertido
		else:
			pytest.fail("el archivo debería estar bloqueado")
	finally:
		otro.kill()
		otro.wait(10)
	pregunta = pregunta_error(str(ruta), fallo, "Copiar")
	assert pregunta.codigo_windows == 32
	assert pregunta.excepcion is fallo


def test_local_tiene_tamano_en_abrir_escritura(tmp_path):
	with ProveedorLocal().abrir_escritura(str(tmp_path / "x.bin"), 3) as salida:
		salida.write(b"abc")
	assert (tmp_path / "x.bin").read_bytes() == b"abc"
