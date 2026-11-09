# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de ``zc.git`` (diseño 2.0, 11.21 y 18.2).

El repositorio de prueba se crea con ``git.exe`` (el diseño pedía dulwich, que
no está en el entorno: ver ``docs/revision/peticiones-p4.md``); el lector en
Python puro se comprueba contra lo que dice el propio Git.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from app.plugins import api
from app.plugins.api import pruebas
from tests.plugins import p4_comun

GIT = shutil.which("git")
necesita_git = pytest.mark.skipif(GIT is None, reason="Hace falta git.exe para crear el repositorio de prueba")


def _git(carpeta, *argumentos):
	entorno = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_DATE="2026-01-01T10:00:00+01:00",
		GIT_COMMITTER_DATE="2026-01-01T10:00:00+01:00")
	return subprocess.run([GIT, "-C", str(carpeta), *argumentos], check=True, capture_output=True, env=entorno,
		creationflags=subprocess.CREATE_NO_WINDOW).stdout.decode("utf-8", errors="replace")


@pytest.fixture
def repo(tmp_path):
	carpeta = tmp_path / "proyecto"
	carpeta.mkdir()
	_git(carpeta, "init", "-q", "-b", "main")
	_git(carpeta, "config", "user.name", "Ana Prueba")
	_git(carpeta, "config", "user.email", "ana@ejemplo.invalid")
	_git(carpeta, "config", "core.autocrlf", "false")
	(carpeta / "a.txt").write_bytes(b"uno\n")
	(carpeta / ".gitignore").write_bytes(b"*.log\nconstruido/\n")
	_git(carpeta, "add", ".")
	_git(carpeta, "commit", "-q", "-m", "Primera confirmación")
	(carpeta / "a.txt").write_bytes(b"uno\ndos\n")
	(carpeta / "sub").mkdir()
	(carpeta / "sub" / "b.txt").write_bytes(b"b\n")
	_git(carpeta, "add", ".")
	_git(carpeta, "commit", "-q", "-m", "Segunda confirmación")
	(carpeta / "a.txt").write_bytes(b"uno\ndos\ntres\n")
	(carpeta / "nuevo.txt").write_bytes(b"sin seguimiento\n")
	(carpeta / "registro.log").write_bytes(b"ignorado\n")
	(carpeta / "preparado.txt").write_bytes(b"preparado\n")
	_git(carpeta, "add", "preparado.txt")
	return carpeta


@pytest.fixture
def zc():
	return p4_comun.anfitrion("git")


ESPERADO = {"a.txt": "modificado", "nuevo.txt": "sin seguimiento", "registro.log": "ignorado", "preparado.txt": "nuevo"}


@necesita_git
def test_estados_con_git_y_con_el_lector(zc, repo):
	motor = p4_comun.modulo(zc, "motor")
	lector = p4_comun.modulo(zc, "lector")
	con_git = zc.instancia.git.estado(str(repo))
	assert con_git.rama == "main"
	assert {r: c for r, c in con_git.cambios.items() if r in ESPERADO} == ESPERADO
	repositorio = lector.Repositorio.de_carpeta(str(repo / "sub"))
	try:
		assert repositorio.rama() == "main"
		assert repositorio.estado() == ESPERADO
	finally:
		repositorio.cerrar()
	assert con_git.resumen() == "Rama main, 3 cambios: 1 modificado, 1 sin seguimiento, 1 nuevo" or \
		con_git.resumen().startswith("Rama main, 3 cambios:")
	assert motor.interpretar_porcelain(b"?? x.txt\0 M a.txt\0R  nuevo.txt\0viejo.txt\0!! b/\0") == {
		"x.txt": "sin seguimiento", "a.txt": "modificado", "nuevo.txt": "renombrado", "b/": "ignorado"}


@necesita_git
def test_columna_git(zc, repo):
	zc.activar()
	columna = zc.instancia.columna
	assert columna(p4_comun.entrada(repo / "a.txt"), None, None) == "modificado"
	assert columna(p4_comun.entrada(repo / "nuevo.txt"), None, None) == "sin seguimiento"
	assert columna(p4_comun.entrada(repo / "registro.log"), None, None) == "ignorado"
	assert columna(p4_comun.entrada(repo / "sub" / "b.txt"), None, None) == ""
	assert columna(p4_comun.entrada(repo / ".gitignore"), None, None) == ""


@necesita_git
def test_historial_lista_dos_confirmaciones(zc, repo):
	zc.activar()
	lector = p4_comun.modulo(zc, "lector")
	confirmaciones = zc.instancia.git.historial(str(repo / "a.txt"))
	assert [c.resumen for c in confirmaciones] == ["Segunda confirmación", "Primera confirmación"]
	assert confirmaciones[0].autor == "Ana Prueba"
	repositorio = lector.Repositorio.de_carpeta(str(repo))
	try:
		assert [c.resumen for c in repositorio.historial("a.txt")] == ["Segunda confirmación", "Primera confirmación"]
		assert [c.resumen for c in repositorio.historial("sub")] == ["Segunda confirmación"]
		assert repositorio.contenido_confirmado("a.txt") == b"uno\ndos\n"
	finally:
		repositorio.cerrar()


@necesita_git
def test_el_lector_lee_paquetes_e_indice_v4(zc, repo):
	lector = p4_comun.modulo(zc, "lector")
	_git(repo, "gc", "-q", "--aggressive")
	_git(repo, "update-index", "--index-version", "4")
	assert not list((repo / ".git" / "objects").glob("[0-9a-f][0-9a-f]/*"))
	repositorio = lector.Repositorio.de_carpeta(str(repo))
	try:
		assert [c.resumen for c in repositorio.historial("a.txt")] == ["Segunda confirmación", "Primera confirmación"]
		assert repositorio.contenido_confirmado("sub/b.txt") == b"b\n"
		assert sorted(e.ruta for e in repositorio.indice()) == [".gitignore", "a.txt", "preparado.txt", "sub/b.txt"]
		assert repositorio.estado() == ESPERADO
	finally:
		repositorio.cerrar()


@necesita_git
def test_sin_git_confirmar_dice_que_hace_falta(zc, repo, monkeypatch):
	motor = p4_comun.modulo(zc, "motor")
	monkeypatch.setattr(motor, "buscar_git", lambda configurado="": "")
	zc.ejecutar("confirmar", pruebas.contexto_de_prueba(activo=p4_comun.panel([repo / "a.txt"], ruta=str(repo))))
	assert zc.anuncios == [("Hace falta Git instalado", api.ESENCIAL)]
	# Sin git.exe el estado sigue funcionando con el lector.
	assert zc.instancia.git.estado(str(repo)).cambios == ESPERADO


@necesita_git
def test_anadir_y_estado_con_las_ordenes(zc, repo):
	panel = p4_comun.panel([repo / "nuevo.txt"], ruta=str(repo))
	zc.ejecutar("anadir", pruebas.contexto_de_prueba(activo=panel))
	p4_comun.esperar_tareas(zc)
	assert zc.anuncios[-1] == ("Preparados para confirmar: 1", api.RESULTADO) and panel.refrescos == 1
	assert "A  nuevo.txt" in _git(repo, "status", "--porcelain")
	zc.ejecutar("estado", pruebas.contexto_de_prueba(activo=panel))
	p4_comun.esperar_tareas(zc)
	assert zc.anuncios[-1][0].startswith("Rama main, 3 cambios")


@necesita_git
def test_orden_interna_y_anuncio_al_entrar(zc, repo):
	zc.activar()
	salida: list[str] = []
	from app.services.vfs import resolver

	proveedor = resolver.proveedor_local()
	zc.instancia._al_cambiar_carpeta(panel=pruebas.PanelFalso(lado="izquierdo"), proveedor=proveedor, ruta=str(repo / "sub"))
	p4_comun.esperar_tareas(zc)
	assert zc.sonidos_pedidos == ["zc.git:repositorio"] and zc.anuncios[-1][1] == api.DETALLE
	zc.instancia._al_cambiar_carpeta(panel=pruebas.PanelFalso(lado="izquierdo"), proveedor=proveedor, ruta=str(repo))
	p4_comun.esperar_tareas(zc)
	assert zc.sonidos_pedidos == ["zc.git:repositorio"], "dentro del mismo repositorio no se repite"
	assert zc.instancia.interna(["rev-parse", "--abbrev-ref", "HEAD"], salida.append, None) == 0
	assert salida == ["main"]


def test_fuera_de_un_repositorio(zc, tmp_path):
	zc.ejecutar("estado", pruebas.contexto_de_prueba(activo=pruebas.PanelFalso(ruta=str(tmp_path))))
	assert zc.anuncios == [("Esta carpeta no está en un repositorio Git", api.RESULTADO)]


def test_nombre_de_clon(zc):
	zc.activar()
	modulo = __import__(type(zc.instancia).__module__, fromlist=["nombre_de_clon"])
	assert modulo.nombre_de_clon("https://github.com/ana/proyecto.git") == "proyecto"
	assert modulo.nombre_de_clon("git@github.com:ana/otro") == "otro"


def test_dialogos_pasan_revisar_teclado(zc, app_wx):
	from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

	zc.activar()
	api.fijar_interfaz(p4_comun.InterfazFalsa())
	try:
		ventanas = zc.instancia.ventanas_para_revisar(None)
		assert len(ventanas) == 2
		for ventana in ventanas:
			afirmar_teclado_correcto(ventana)
			ventana.Destroy()
	finally:
		api.fijar_interfaz(None)
