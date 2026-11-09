# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""``ContextoOrden`` 2.0: argumento, sonar, orden_origen y la grabación de macros (diseño 2.0, 10.1, 14.9 y 18.2)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ui.contexto import ContextoOrden

from ..conftest import procesar_eventos


def test_lanzar_pone_orden_origen():
	recibidas = []
	ventana = SimpleNamespace(lanzar_operacion=lambda op, en_cola, al_terminar: recibidas.append(op))
	ctx = ContextoOrden(ventana, None, None, None, orden="copiar")
	operacion = SimpleNamespace(orden_origen="")
	ctx.lanzar(operacion)
	assert recibidas == [operacion] and operacion.orden_origen == "copiar"


def test_sonar_y_argumento(monkeypatch):
	from app.services.sonidos import servicio

	pedidos = []
	monkeypatch.setattr(servicio, "sonar", lambda evento, variante="", *, sustituye=False: pedidos.append((evento, variante, sustituye)) or True)
	ctx = ContextoOrden(None, None, None, None, orden="x", argumento="D:\\Fotos")
	assert ctx.argumento == "D:\\Fotos"
	assert ctx.sonar("op.fin")
	assert ctx.sonar("op.progreso", "50", sustituye=True)
	assert pedidos == [("op.fin", "", False), ("op.progreso", "50", True)]


class GrabadorFalso:
	grabando = True

	def __init__(self) -> None:
		self.pasos: list[tuple[str, object]] = []

	def anotar(self, id_orden, argumento) -> None:
		self.pasos.append(("orden", id_orden))

	def anotar_argumento(self, valor) -> None:
		self.pasos.append(("argumento", valor))


@pytest.fixture
def ventana(app_wx, tmp_path, monkeypatch):
	from app.core.configuracion import Configuracion
	from app.services import sesion
	from app.ui.ventana_principal import VentanaPrincipal

	(tmp_path / "a.txt").write_text("a", encoding="utf-8")
	monkeypatch.setattr(sesion, "cargar", lambda: {**sesion.POR_DEFECTO, "lados": {
		"izquierdo": {"pestanas": [sesion.pestana(ruta=str(tmp_path))], "actual": 0},
		"derecho": {"pestanas": [sesion.pestana(ruta=str(tmp_path))], "actual": 0}}})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	marco = VentanaPrincipal(config)
	marco.mostrar()
	procesar_eventos(lambda: len(marco.izquierdo.panel_actual().entradas()) >= 1, 5)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.3)


def test_la_grabacion_apunta_el_paso_antes_del_argumento_del_dialogo(ventana, monkeypatch):
	from app.ui.dialogos import nombre

	grabador = GrabadorFalso()
	ventana.registrar_servicio("grabador", grabador)
	monkeypatch.setattr(nombre, "pedir_patron", lambda *a, **k: "*.txt")
	ventana.ejecutar_orden("marcar_patron")
	assert grabador.pasos == [("orden", "marcar_patron"), ("argumento", "*.txt")]
	grabador.pasos.clear()
	ventana.ejecutar_orden("decir_ruta")  # de consulta: no se graba
	assert grabador.pasos == []


def test_con_argumento_no_hay_dialogo(ventana, monkeypatch):
	from app.ui.dialogos import nombre

	monkeypatch.setattr(nombre, "pedir_patron", lambda *a, **k: pytest.fail("con argumento no se pregunta"))
	ventana.ejecutar_orden("marcar_patron", argumento="*.txt")
	assert [e.nombre for e in ventana.activo.marcadas()] == ["a.txt"]
