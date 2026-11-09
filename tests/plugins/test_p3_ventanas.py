# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventanas del bloque P3 (diseño 2.0, 15.1 y 18.2): todas pasan ``revisar_teclado`` y se manejan con teclado.

Se construyen con los controles reales de ``app.ui.api_ui`` (por una
``InterfazAnfitrion`` de prueba) y sin mostrarse; ningún ``ShowModal`` real:
``mostrar_modal`` se sustituye por una función que rellena el diálogo y
devuelve el botón pulsado.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

wx = pytest.importorskip("wx")

from app.plugins import api  # noqa: E402
from app.plugins.api import pruebas  # noqa: E402
from app.services.vfs import resolver  # noqa: E402
from app.ui import api_ui  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from tests.plugins.p3_comun import CARPETAS, PLUGINS, RAIZ, InterfazFalsa, modulo, preparar  # noqa: E402


@pytest.fixture
def interfaz(app_wx):
	falsa = InterfazFalsa()
	api.fijar_interfaz(falsa)
	padre = wx.Frame(None, title="Pruebas P3")
	yield falsa, padre
	api.fijar_interfaz(None)
	padre.Destroy()


@pytest.mark.parametrize("carpeta", CARPETAS)
def test_cada_ventana_pasa_revisar_teclado(interfaz, carpeta):
	_falsa, padre = interfaz
	zc, _paquete = preparar(carpeta)
	ventanas = zc.instancia.ventanas_para_revisar(padre)
	assert ventanas, f"{carpeta} no devolvió ventanas para revisar"
	try:
		for ventana in ventanas:
			afirmar_teclado_correcto(ventana, teclas_propias=["F1"])
			assert ventana.GetEscapeId() in (wx.ID_CANCEL, wx.ID_CLOSE)
	finally:
		for ventana in ventanas:
			ventana.Destroy()


def test_sin_interfaz_las_ventanas_no_se_pueden_crear(app_wx):
	"""Sin la ventana de zCommander, ``ventanas_para_revisar`` no falla: devuelve una lista vacía."""
	api.fijar_interfaz(None)
	zc, _paquete = preparar("papelera")
	padre = wx.Frame(None)
	try:
		assert zc.instancia.ventanas_para_revisar(padre) == []
	finally:
		padre.Destroy()


def test_vaciar_la_papelera_tiene_cancelar_como_predeterminado(interfaz, monkeypatch, tmp_path):
	_falsa, padre = interfaz
	zc, paquete = preparar("papelera")
	ui = modulo(paquete, "ui")
	dialogo = ui.DialogoVaciar(padre, zc, "3 elementos, 2 MB")
	try:
		assert dialogo.GetDefaultItem() is dialogo.boton_cancelar
		assert dialogo.GetEscapeId() == wx.ID_CANCEL
		assert "No se puede deshacer" in dialogo.mensaje.GetLabel()
	finally:
		dialogo.Destroy()
	# La orden: con la papelera de mentira, «Cancelar» no lanza nada y «Vaciar» lanza la operación.
	motor = modulo(paquete, "motor")
	bin_ = tmp_path / "$Recycle.Bin" / "S-1"
	bin_.mkdir(parents=True)
	(bin_ / "$RAAA.txt").write_bytes(b"x")
	(bin_ / "$IAAA.txt").write_bytes(motor.formar_i(1, time.time(), str(tmp_path / "x.txt")))
	zc.instancia.papelera = motor.Papelera(lambda: [str(bin_)])
	respuestas = [wx.ID_CANCEL, ui.ID_VACIAR]
	vistos: list[wx.Dialog] = []

	def modal(dialogo_abierto):
		vistos.append(dialogo_abierto.GetDefaultItem())
		return respuestas.pop(0)

	monkeypatch.setattr(api_ui, "mostrar_modal", modal)
	ctx = pruebas.contexto_de_prueba()
	zc.instancia._preguntar_vaciar(ctx, "", zc.instancia.papelera.elementos())
	assert zc.operaciones_lanzadas == []
	zc.instancia._preguntar_vaciar(ctx, "", zc.instancia.papelera.elementos())
	assert [type(o).__name__ for o in zc.operaciones_lanzadas] == ["OperacionVaciar"]
	assert all(boton.GetLabel() == "&Cancelar" for boton in vistos)


def test_duplicados_de_la_busqueda_a_la_papelera(interfaz, monkeypatch, tmp_path):
	_falsa, _padre = interfaz
	zc, paquete = preparar("duplicados")
	motor, ui = modulo(paquete, "motor"), modulo(paquete, "ui")
	for nombre, antiguedad in (("a/x.bin", 300), ("b/x.bin", 200), ("c/x.bin", 100)):
		ruta = tmp_path / nombre
		ruta.parent.mkdir(parents=True)
		ruta.write_bytes(b"igual" * 400)
		os.utime(ruta, (time.time() - antiguedad, time.time() - antiguedad))

	def buscar(dialogo):
		assert dialogo.campo_carpetas.GetValue() == str(tmp_path)
		dialogo.criterio.SetSelection(0)
		return wx.ID_OK

	monkeypatch.setattr(api_ui, "mostrar_modal", buscar)
	activo = pruebas.PanelFalso(ruta=str(tmp_path))
	zc.ejecutar("buscar", pruebas.contexto_de_prueba(activo=activo))
	(operacion,) = zc.operaciones_lanzadas
	assert isinstance(operacion, motor.OperacionBuscarDuplicados)
	ctx = api.ContextoEjecucion(__import__("threading").Event(), pruebas.DecisorFalso())
	operacion.contexto, ctx.operacion = ctx, operacion
	operacion.ejecutar(ctx)
	assert len(operacion.resultado.grupos) == 1

	# La lista: marcado automático (conservar el más antiguo) y a la papelera con confirmación.
	monkeypatch.setattr(api_ui, "elegir_opcion", lambda *a, **k: 0)
	monkeypatch.setattr(api_ui, "confirmar", lambda *a, **k: True)
	marcadas: list[set[str]] = []

	def lista(dialogo):
		assert isinstance(dialogo, ui.DialogoResultados)
		assert dialogo.lista.numero_filas() == 3
		assert dialogo.lista.valores_fila(0)[0] == "1 de 1"
		dialogo._al_auto(None)
		marcadas.append(dialogo.marcadas())
		dialogo._accion("papelera")
		return wx.ID_CLOSE

	monkeypatch.setattr(api_ui, "mostrar_modal", lista)
	zc.instancia._al_terminar_busqueda(operacion)
	assert marcadas == [{str(tmp_path / "b" / "x.bin"), str(tmp_path / "c" / "x.bin")}]
	eliminar = zc.operaciones_lanzadas[-1]
	assert isinstance(eliminar, api.OperacionEliminar) and eliminar.papelera
	assert sorted(e.ruta for e in eliminar.entradas) == sorted(marcadas[0])
	assert any(t.startswith("Marcados 2 archivos en 1 grupo") for t, _n in zc.anuncios)


def test_notas_ctrl_n_guarda_el_comentario_y_en_dos_puntos_la_nota(interfaz, monkeypatch, tmp_path):
	_falsa, _padre = interfaz
	zc, paquete = preparar("notas")
	(tmp_path / "carta.txt").write_text("c", encoding="utf-8")
	local = resolver.proveedor_local()
	entradas = local.listar(str(tmp_path))
	textos = ["Enviar el lunes", "Nota de la carpeta"]

	def modal(dialogo):
		dialogo.campo.SetValue(textos.pop(0))
		return wx.ID_OK

	monkeypatch.setattr(api_ui, "mostrar_modal", modal)
	panel = pruebas.PanelFalso(entradas, ruta=str(tmp_path))
	zc.ejecutar("comentario", pruebas.contexto_de_prueba(activo=panel))
	assert zc.instancia.almacen.comentario(str(tmp_path / "carta.txt")) == "Enviar el lunes"
	assert ("Comentario guardado", api.RESULTADO) in zc.anuncios
	assert panel.refrescos == 1
	en_superior = pruebas.PanelFalso([api.Entrada("..", str(tmp_path.parent), es_carpeta=True, es_superior=True)], ruta=str(tmp_path))
	en_superior.cursor = lambda: None  # PanelVista da None en «..»
	zc.ejecutar("comentario", pruebas.contexto_de_prueba(activo=en_superior))
	assert zc.instancia.almacen.comentario(str(tmp_path)) == "Nota de la carpeta"
	assert ("Nota guardada", api.RESULTADO) in zc.anuncios


def test_notas_etiquetas_desde_el_dialogo(interfaz, monkeypatch, tmp_path):
	_falsa, _padre = interfaz
	zc, _paquete = preparar("notas")
	for nombre in ("a.txt", "b.txt"):
		(tmp_path / nombre).write_text("x", encoding="utf-8")
	local = resolver.proveedor_local()
	panel = pruebas.PanelFalso(local.listar(str(tmp_path)), marcadas=["a.txt", "b.txt"], ruta=str(tmp_path))

	def modal(dialogo):
		dialogo.lista.Check(0, True)  # Urgente
		dialogo.lista.Check(2, True)  # Facturas
		return wx.ID_OK

	monkeypatch.setattr(api_ui, "mostrar_modal", modal)
	zc.ejecutar("etiquetas", pruebas.contexto_de_prueba(activo=panel))
	for nombre in ("a.txt", "b.txt"):
		assert zc.instancia.almacen.etiquetas(str(tmp_path / nombre)) == ["Facturas", "Urgente"]
	assert ("Etiquetas: Urgente (rojo), Facturas (verde)", api.RESULTADO) in zc.anuncios


def test_organizador_vista_previa_y_organizar(interfaz, monkeypatch, tmp_path):
	_falsa, _padre = interfaz
	zc, paquete = preparar("organizador")
	ui = modulo(paquete, "ui")
	origen = tmp_path / "origen"
	origen.mkdir()
	for nombre in ("a.txt", "b.txt"):
		(origen / nombre).write_text(nombre, encoding="utf-8")
	destino = tmp_path / "destino"
	destino.mkdir()
	local = resolver.proveedor_local()
	activo = pruebas.PanelFalso(local.listar(str(origen)), marcadas=["a.txt", "b.txt"], ruta=str(origen))
	pasivo = pruebas.PanelFalso(ruta=str(destino), lado="derecho")
	# La vista previa se calcula en el hilo: se espera a que llegue procesando los eventos.
	from tests.conftest import procesar_eventos

	vistas: list[list[str]] = []

	def modal(dialogo):
		assert isinstance(dialogo, ui.DialogoOrganizar)
		assert dialogo.base.GetValue() == str(destino)
		dialogo.carpetas.SetValue("Textos\\[E]")
		dialogo.actualizar()
		assert procesar_eventos(lambda: dialogo._vigente == dialogo.campos(), 5)
		vistas.append([dialogo.lista.valores_fila(i)[2] for i in range(dialogo.lista.numero_filas())])
		return wx.ID_OK

	zc._tareas = None  # las respuestas vuelven por wx.CallAfter, como en la aplicación
	monkeypatch.setattr(api_ui, "mostrar_modal", modal)
	zc.ejecutar("organizar", pruebas.contexto_de_prueba(activo=activo, pasivo=pasivo))
	assert vistas == [["Listo", "Listo"]]
	(operacion,) = zc.operaciones_lanzadas
	assert [f.destino for f in operacion.filas] == [str(destino / "Textos" / "txt" / "a.txt"), str(destino / "Textos" / "txt" / "b.txt")]
	assert operacion.mover


@pytest.mark.lento
@pytest.mark.parametrize("carpeta", CARPETAS)
def test_validar_plugin_devuelve_cero(carpeta):
	resultado = subprocess.run([sys.executable, str(RAIZ / "tools" / "validar_plugin.py"), str(PLUGINS / carpeta)], cwd=RAIZ,
		capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
	assert resultado.returncode == 0, resultado.stdout + resultado.stderr
