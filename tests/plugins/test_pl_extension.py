# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Puntos de extensión enganchados y herramientas de autor (diseño 2.0, 3.5, 3.12, 3.13 y 18.2, bloque PL).

Sin wx: columnas (en un hilo, con tiempo máximo), visores (``Documento``), acciones
de error, motores y extractores de búsqueda, y ``tools/validar_plugin.py``.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from app.plugins import api, cargador, estado, registro, serie
from app.services import busqueda
from app.services.operaciones.modelo import PreguntaError
from tools import crear_plugin, validar_plugin

from ..conftest import RAIZ

MANIFIESTO = """\
formato = 1
id = "ana.extension"
nombre = "Extensiones de Ana"
descripcion = "Columnas, visores, acciones de error y búsqueda."
version = "1.0.0"
autor = "Ana"
licencia = "GPL-3.0-or-later"
api_minima = "1.0"
api_probada = "1.0"
entrada = "__init__:Complemento"

[[ordenes]]
id = "nada"
etiqueta = "&Nada"
ayuda = "No hace nada."

[[columnas]]
id = "largo"
titulo = "Largo"
tipo = "numero"

[[columnas]]
id = "lenta"
titulo = "Lenta"
lenta = true

[[visores]]
id = "doc"
nombre = "Documentos de prueba"
patrones = ["*.doc1"]

[[acciones_error]]
id = "liberar"
etiqueta = "&Liberar el archivo"
codigos_windows = [32]

[[busqueda]]
id = "indice"
nombre = "Índice de Ana"

[[extractores]]
patrones = ["*.doc1"]
nombre = "Documentos de prueba"
"""

CODIGO = """
import threading, time
from app.plugins import api

HILOS = []

class Complemento(api.Complemento):
	def activar(self, zc):
		zc.ordenes.manejador("nada", lambda ctx: None)
		zc.columnas.extractor("largo", self.largo)
		zc.columnas.extractor("lenta", self.lenta)
		zc.visores.visor("doc", self.ver)
		zc.errores.accion("liberar", lambda pregunta: True, lambda pregunta: api.AccionError.REINTENTAR)
		zc.busqueda.proveedor("indice", self.buscar)
		zc.busqueda.extractor(self.extraer)

	def largo(self, entrada, proveedor, cancelacion):
		HILOS.append(threading.current_thread().name)
		return str(len(entrada.nombre))

	def lenta(self, entrada, proveedor, cancelacion):
		time.sleep(3)
		return "tarde"

	def ver(self, proveedor, ruta, cancelacion):
		return api.Documento("Prueba", (api.Seccion("Uno", texto="Primero", pagina=1), api.Seccion("Dos", texto="Segundo", pagina=2)))

	def buscar(self, criterios, entregar, cancelacion):
		entregar(criterios.nombres)

	def extraer(self, proveedor, ruta, cancelacion):
		return "texto secreto del documento"
"""


class Planificador:
	def __init__(self) -> None:
		self.cola: queue.Queue = queue.Queue()

	def __call__(self, funcion) -> None:
		self.cola.put(funcion)

	def bombear(self, condicion, segundos: float = 10.0) -> bool:
		limite = time.monotonic() + segundos
		while time.monotonic() < limite:
			try:
				self.cola.get(timeout=0.02)()
			except queue.Empty:
				if condicion():
					return True
		return condicion()


@pytest.fixture
def extension(registro_vacio, tmp_path, monkeypatch):
	for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
		del sys.modules[nombre]
	carpeta = tmp_path / "serie" / "extension"
	carpeta.mkdir(parents=True)
	(carpeta / "manifiesto.toml").write_text(MANIFIESTO, encoding="utf-8")
	(carpeta / "__init__.py").write_text(textwrap.dedent(CODIGO), encoding="utf-8")
	monkeypatch.setattr(serie, "SERIE", {"ana.extension": "1.0.0"})
	estado.reiniciar()
	sesion = cargador.Cargador(None, carpeta_serie=tmp_path / "serie", carpeta_usuario=tmp_path / "usuario",
		carpeta_centinelas=tmp_path / "cargando")
	sesion.descubrir()
	cargador.fijar_actual(sesion)
	yield sesion
	sesion.cerrar()
	cargador.fijar_planificador(None)
	cargador.fijar_actual(None)
	for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
		del sys.modules[nombre]


def test_columna_se_calcula_en_el_hilo_del_complemento_y_respeta_el_tiempo(extension, monkeypatch):
	planificador = Planificador()
	cargador.fijar_planificador(planificador)
	monkeypatch.setattr(registro, "TIEMPO_COLUMNA_S", 0.3)
	assert [c.id for c in registro.catalogo_columnas()] == ["ana.extension:largo", "ana.extension:lenta"]
	entrada = api.Entrada("informe.txt", "C:\\x\\informe.txt", tamano=10, modificado=1.0)
	listos: list[str] = []
	assert registro.valor_columna("ana.extension:largo", entrada, None, lambda: listos.append("largo")) is None, "nunca bloquea"
	assert planificador.bombear(lambda: "largo" in listos)
	assert threading.current_thread() is threading.main_thread()
	assert registro.valor_columna("ana.extension:largo", entrada, None, lambda: None) == "11", "de la caché"
	hilos = sys.modules["zcplugins.ana__extension"].HILOS
	assert hilos and all(h.startswith("zc-ana.extension") for h in hilos), "en el grupo de hilos propio del complemento"
	inicio = time.monotonic()
	assert registro.valor_columna("ana.extension:lenta", entrada, None, lambda: listos.append("lenta")) is None
	assert planificador.bombear(lambda: "lenta" in listos, 5)
	assert time.monotonic() - inicio < 2.5, "el tiempo máximo corta la espera"
	assert registro.valor_columna("ana.extension:lenta", entrada, None, lambda: None) == registro.SIN_DATOS


def test_visor_de_complemento_da_un_documento(extension):
	assert registro.visor_para("informe.doc1") == ("ana.extension:doc", False)
	assert registro.visor_para("informe.txt") is None
	assert "zcplugins.ana__extension" not in sys.modules, "elegir el visor no activa el complemento"
	documento = registro.documento_visor("ana.extension:doc", None, "C:\\informe.doc1")
	assert isinstance(documento, api.Documento) and [s.titulo for s in documento.secciones] == ["Uno", "Dos"]


def test_accion_de_error_aparece_en_la_pregunta_de_error(extension):
	acciones = registro.acciones_error_aplicables(PreguntaError("C:\\x", "en uso", codigo_windows=32))
	assert [(a.id, a.etiqueta, a.activo) for a in acciones] == [("ana.extension:liberar", "&Liberar el archivo", False)]
	assert registro.acciones_error_aplicables(PreguntaError("C:\\x", "otro", codigo_windows=5)) == []


def test_motor_y_extractor_de_busqueda(extension, tmp_path):
	assert registro.motores_busqueda() == [("ana.extension:indice", "Índice de Ana")]
	assert registro.hay_extractores()
	documento = tmp_path / "carpeta" / "informe.doc1"
	documento.parent.mkdir()
	documento.write_bytes(b"\x00\x01binario")
	from app.services.vfs import resolver

	local = resolver.proveedor_local()
	encontrados: list[str] = []
	busqueda.buscar([(local, str(documento.parent))], busqueda.Criterios(texto="secreto", dentro_de_documentos=True),
		al_resultado=lambda r: encontrados.append(r.entrada.nombre))
	assert encontrados == ["informe.doc1"]
	encontrados.clear()
	busqueda.buscar([(local, str(documento.parent))], busqueda.Criterios(texto="secreto"), al_resultado=lambda r: encontrados.append(r.entrada.nombre))
	assert encontrados == [], "sin la casilla, el extractor no se usa"
	encontrados.clear()
	busqueda.buscar([], busqueda.Criterios(nombres=str(documento), motor="ana.extension:indice"),
		al_resultado=lambda r: encontrados.append(r.entrada.nombre))
	assert encontrados == ["informe.doc1"]


# ── Herramientas de autor ────────────────────────────────────────────────────


def test_validar_plugin_acepta_la_plantilla_y_rechaza_un_manifiesto_sin_licencia(tmp_path, registro_vacio):
	carpeta = tmp_path / "plantilla"
	assert crear_plugin.crear(carpeta, "ana.plantilla", "Plantilla de Ana") == []
	resultado = subprocess.run([sys.executable, str(RAIZ / "tools" / "validar_plugin.py"), str(carpeta)], cwd=str(RAIZ),
		capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
	assert resultado.returncode == 0, resultado.stdout + resultado.stderr
	ruta = carpeta / "manifiesto.toml"
	ruta.write_text(ruta.read_text(encoding="utf-8").replace('licencia = "GPL-3.0-or-later"\n', ""), encoding="utf-8")
	assert validar_plugin.main([str(carpeta), "--sin-pruebas"]) == 1


def test_validar_plugin_dice_las_letras_repetidas_de_una_pagina(tmp_path, registro_vacio):
	carpeta = tmp_path / "letras"
	assert crear_plugin.crear(carpeta, "ana.letras", "Letras") == []
	ruta = carpeta / "manifiesto.toml"
	ruta.write_text(ruta.read_text(encoding="utf-8") + textwrap.dedent("""
		[[configuracion]]
		clave = "otro"
		tipo = "bool"
		defecto = false
		etiqueta = "&Silencio"
		pagina = "general"

		[[configuracion]]
		clave = "tercero"
		tipo = "bool"
		defecto = false
		etiqueta = "&Aplicar todo"
		pagina = "general"
	"""), encoding="utf-8")
	informe = validar_plugin.validar(carpeta, pruebas=False)
	assert any("otro" in e and "saludo" in e for e in informe.errores)
	assert any("tercero" in e and "Preferencias" in e for e in informe.errores)


def test_crear_plugin_rechaza_ids_reservados_o_no_validos(tmp_path):
	assert crear_plugin.crear(tmp_path / "a", "zc.mio", "Mío")
	assert crear_plugin.crear(tmp_path / "b", "Mal Id", "Mal")


@pytest.mark.lento
def test_comprobar_arranque_carga_un_complemento_de_prueba(tmp_path):
	"""``main.py --comprobar-arranque --complemento-prueba`` (desde el código fuente; la compilación hace lo mismo)."""
	carpeta = tmp_path / "prueba"
	assert crear_plugin.crear(carpeta, "ana.arranque", "Arranque") == []
	entorno = {**__import__("os").environ, "APP_DATA_DIR": str(tmp_path / "data")}
	resultado = subprocess.run([sys.executable, str(RAIZ / "main.py"), "--comprobar-arranque", "--complemento-prueba", str(carpeta)],
		cwd=str(RAIZ), env=entorno, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
	assert resultado.returncode == 0, resultado.stdout + resultado.stderr
	roto = tmp_path / "roto"
	assert crear_plugin.crear(roto, "ana.roto", "Roto") == []
	(roto / "__init__.py").write_text("raise ImportError('roto')\n", encoding="utf-8")
	resultado = subprocess.run([sys.executable, str(RAIZ / "main.py"), "--comprobar-arranque", "--complemento-prueba", str(roto)],
		cwd=str(RAIZ), env=entorno, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
	assert resultado.returncode == 1
	assert not Path(tmp_path / "data" / "temp").exists() or not any((tmp_path / "data" / "temp").iterdir())
