# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Reglas de arquitectura del diseño (1.x 9.1, 9.3 y 20.3; 2.0 18.1) comprobadas sobre el código.

- Capas: ``app/core``, ``app/services`` y ``app/plugins`` no importan ``wx`` ni
  ``app.ui`` (se prueban sin interfaz y los usan los hilos de trabajo).
  ``app/plugins`` SIN ninguna excepción, ni siquiera de forma perezosa.
- Ningún complemento de serie importa ``app.`` fuera de ``app.plugins.api``.
- Provisionales parametrizados por bloque (2.0, 18.1): un manejador
  provisional de un bloque abierto (``BLOQUES_ABIERTOS``) se permite; uno de un
  bloque cerrado falla. Cada bloque se quita de la lista en su definición de
  terminado (19.4).
- Los anexos generados (órdenes, configuración, teclas, sonidos, serie) están al día.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PROHIBIDOS = ("wx", "app.ui")
# Plantillas del núcleo que importan wx dentro de una función, solo cuando hay
# interfaz (llevar la respuesta de una tarea al hilo de la interfaz, traer la
# ventana al frente); funcionan igual sin wx. app/plugins no tiene excepciones.
WX_PEREZOSO = {"app/core/tareas.py", "app/core/instancia_unica.py"}

#: Bloques de la 2.0 aún abiertos (19.4): todos al cerrar N2; al final queda vacía.
BLOQUES_ABIERTOS: set[str] = set()
#: Todos los bloques (cerrados y abiertos); se escribe aparte para que cerrar un bloque no lo borre de aquí.
TODOS_LOS_BLOQUES = sorted({
	"N", "A", "B", "C", "D", "E", "F", "G",
	"PL", "SO", "AC", "CO", "CS", "CM", "RD", "PE", "NV", "LI", "P1", "P2", "P3", "P4", "P5", "NU", "NS",
})
#: Sufijo de cada módulo de acciones de bloque de la 2.0 (su ``instalar`` cuenta para ese bloque).
SUFIJOS = {"_so": "SO", "_pl": "PL", "_co": "CO", "_ac": "AC", "_cs": "CS", "_rd": "RD", "_nv": "NV"}
#: Provisionales de N2 en archivos de otros bloques (tabla de 19.1), por su dueño posterior.
PROVISIONALES_OTROS = {
	"app/services/componentes/fichas.py": "CO", "app/services/componentes/estado.py": "CO",
	"app/services/componentes/integrar.py": "CO", "app/services/componentes/prueba.py": "CO",
	"app/services/libarchive/prueba.py": "CM",
	"app/services/sonidos/paquetes.py": "SO", "app/ui/dialogos/so_pagina_sonidos.py": "SO",
	"app/plugins/prueba.py": "PL", "app/plugins/gestor.py": "PL",
	"app/ui/instalar_complemento.py": "NV",
}


def _importaciones(archivo: Path) -> list[tuple[int, str]]:
	arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
	resultado = []
	for nodo in ast.walk(arbol):
		if isinstance(nodo, ast.Import):
			resultado.extend((nodo.lineno, alias.name) for alias in nodo.names)
		elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
			resultado.append((nodo.lineno, nodo.module))
	return resultado


def _archivos(carpeta: str) -> list[Path]:
	return sorted((RAIZ / carpeta).rglob("*.py"))


@pytest.mark.parametrize("carpeta", ["app/core", "app/services", "app/plugins"])
def test_capas_sin_interfaz(carpeta):
	problemas = []
	for archivo in _archivos(carpeta):
		for linea, modulo in _importaciones(archivo):
			relativo = archivo.relative_to(RAIZ).as_posix()
			if carpeta != "app/plugins" and relativo in WX_PEREZOSO and modulo == "wx":
				continue
			if any(modulo == p or modulo.startswith(p + ".") for p in PROHIBIDOS):
				problemas.append(f"{archivo.relative_to(RAIZ)}:{linea} importa {modulo}")
	assert not problemas, "\n".join(problemas)


def test_complementos_de_serie_solo_usan_la_api():
	"""Un complemento de serie solo importa de ``app`` la fachada ``app.plugins.api`` (3.5, 18.1)."""
	problemas = []
	for archivo in _archivos("plugins"):
		for linea, modulo in _importaciones(archivo):
			if (modulo == "app" or modulo.startswith("app.")) and modulo != "app.plugins.api" and modulo != "app.plugins":
				problemas.append(f"{archivo.relative_to(RAIZ)}:{linea} importa {modulo}")
		arbol = ast.parse(archivo.read_text(encoding="utf-8"))
		for nodo in ast.walk(arbol):
			if isinstance(nodo, ast.ImportFrom) and nodo.module == "app.plugins" and any(a.name != "api" for a in nodo.names):
				problemas.append(f"{archivo.relative_to(RAIZ)}:{nodo.lineno} importa de app.plugins algo que no es api")
	assert not problemas, "\n".join(problemas)


def test_servicios_no_importan_core_de_interfaz():
	"""``app/core`` no depende de ``app/services`` salvo la configuración (el núcleo de abajo)."""
	problemas = []
	for archivo in _archivos("app/core"):
		for linea, modulo in _importaciones(archivo):
			if modulo.startswith("app.services"):
				problemas.append(f"{archivo.relative_to(RAIZ)}:{linea} importa {modulo}")
	assert not problemas, "\n".join(problemas)


def _provisionales_por_bloque() -> dict[str, list[str]]:
	"""Provisionales del catálogo, de los ``instalar`` de bloque, de la API y de los complementos de serie."""
	from app.plugins import api, manifiesto, registro
	from app.ui import ordenes

	por_bloque: dict[str, list[str]] = {}

	def anotar(bloque: str, texto: str) -> None:
		por_bloque.setdefault(bloque, []).append(texto)

	reales = {"complementos_pl.ejecutar", "complementos_pl.estado"}
	for orden in ordenes.CATALOGO:
		for referencia in filter(None, (orden.manejador, orden.estado)):
			if referencia in reales:
				continue
			modulo, funcion = referencia.rsplit(".", 1)
			objeto = getattr(importlib.import_module(f"app.ui.acciones.{modulo}"), funcion)
			if getattr(objeto, "provisional", False):
				anotar(orden.bloque, f"{orden.id} ({referencia})")
	from app.ui.acciones import personalizar_pe

	if getattr(personalizar_pe.ejecutar_macro, "provisional", False):
		anotar("PE", "personalizar_pe.ejecutar_macro")
	for archivo in sorted((RAIZ / "app" / "ui" / "acciones").glob("*.py")):
		bloque = next((b for sufijo, b in SUFIJOS.items() if archivo.stem.endswith(sufijo)), None)
		if bloque is None:
			continue
		instalar = getattr(importlib.import_module(f"app.ui.acciones.{archivo.stem}"), "instalar", None)
		if instalar is None:
			anotar(bloque, f"{archivo.stem}.instalar no existe")
		elif getattr(instalar, "provisional", False):
			anotar(bloque, f"{archivo.stem}.instalar")
	if getattr(api._sin_implementar, "provisional", False):
		anotar("PL", "api._sin_implementar")
	for carpeta in sorted(p for p in (RAIZ / "plugins").iterdir() if (p / manifiesto.NOMBRE).is_file()):
		datos = manifiesto.leer(carpeta)
		zc = api.pruebas.anfitrion_de_prueba(carpeta)
		zc.activar()
		for orden in datos.ordenes:
			funcion = registro.manejador(f"{datos.id}:{orden.id}")
			if funcion is None:
				anotar(datos.bloque, f"{datos.id}:{orden.id} sin manejador")
			elif getattr(funcion, "provisional", False):
				anotar(datos.bloque, f"{datos.id}:{orden.id}")
	return por_bloque


@pytest.fixture(scope="module")
def provisionales(tmp_path_factory):
	"""Activa los complementos de serie para leer sus manejadores, con una ``data``
	temporal: activar un complemento puede crear su configuración, y no debe
	ensuciar la ``data`` real del proyecto (que se distribuye)."""
	import os

	anterior = os.environ.get("APP_DATA_DIR")
	os.environ["APP_DATA_DIR"] = str(tmp_path_factory.mktemp("data_arquitectura"))
	try:
		return _provisionales_por_bloque()
	finally:
		if anterior is None:
			os.environ.pop("APP_DATA_DIR", None)
		else:
			os.environ["APP_DATA_DIR"] = anterior


@pytest.mark.parametrize("bloque", TODOS_LOS_BLOQUES)
def test_ningun_manejador_provisional(bloque, provisionales):
	encontrados = provisionales.get(bloque, [])
	sin_manejador = [t for t in encontrados if t.endswith("sin manejador") or t.endswith("no existe")]
	assert not sin_manejador, "Faltan manejadores:\n" + "\n".join(sin_manejador)
	if bloque in BLOQUES_ABIERTOS:
		return
	assert not encontrados, f"Órdenes aún provisionales del bloque {bloque}:\n" + "\n".join(sorted(set(encontrados)))


def _bloque_del_archivo(relativo: str) -> str | None:
	"""Bloque dueño de un archivo con provisionales permitidos (si está abierto)."""
	if relativo in PROVISIONALES_OTROS:
		return PROVISIONALES_OTROS[relativo]
	ruta = Path(relativo)
	if relativo.startswith("app/ui/acciones/"):
		return next((b for sufijo, b in SUFIJOS.items() if ruta.stem.endswith(sufijo)), None)
	if relativo.startswith("plugins/") and len(ruta.parts) > 1:
		from app.plugins import manifiesto

		carpeta = RAIZ / "plugins" / ruta.parts[1]
		try:
			return manifiesto.leer(carpeta).bloque or None
		except manifiesto.ErrorManifiesto:
			return None
	return None


def test_sin_pendientes_en_el_codigo():
	marcas = ("NotImplementedError", "Todavía no disponible")
	problemas = []
	for archivo in [*_archivos("app"), *_archivos("plugins")]:
		if archivo.name == "__init__.py" and archivo.parent.name == "acciones":
			continue  # define la función provisional en sí
		relativo = archivo.relative_to(RAIZ).as_posix()
		if relativo.startswith("plugins/") and "/lib/" in relativo:
			continue  # bibliotecas de terceros vendorizadas (mutagen...): no son código del proyecto
		texto = archivo.read_text(encoding="utf-8")
		for marca in marcas:
			if marca in texto and not _solo_en_abstractos(archivo, marca):
				bloque = _bloque_del_archivo(relativo)
				if bloque is not None and bloque in BLOQUES_ABIERTOS:
					continue
				problemas.append(f"{relativo}: {marca}")
	assert not problemas, "\n".join(problemas)


def _solo_en_abstractos(archivo: Path, marca: str) -> bool:
	"""``NotImplementedError`` es legítimo en métodos de una clase base abstracta (``Proveedor``)."""
	if marca != "NotImplementedError":
		return False
	return archivo.relative_to(RAIZ).as_posix() in {"app/services/vfs/base.py", "app/services/operaciones/modelo.py"}


def test_anexos_al_dia():
	resultado = subprocess.run(
		[sys.executable, str(RAIZ / "tools" / "generar_anexos.py"), "--comprobar"],
		cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
	)
	assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_letras_de_preferencias_sin_choques():
	from tools.comprobar_preferencias import problemas

	assert problemas() == []


def test_lista_de_teclas_coincide_con_el_codigo():
	"""Catálogo (núcleo y complementos de serie), menús del visor, editor y ayuda frente a ``data/docs/teclas.md``."""
	from tools import comprobar_teclas

	resultado = comprobar_teclas.comprobar(RAIZ, RAIZ / "data" / "docs" / "teclas.md")
	assert not (resultado.no_documentados or resultado.obsoletos or resultado.duplicados), comprobar_teclas.formatear(resultado)
