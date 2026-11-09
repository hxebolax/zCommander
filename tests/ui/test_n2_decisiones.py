# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Gestor de decisiones 2.0: respuestas automáticas, acciones de error de complementos y credenciales (14.6, 18.2)."""

from __future__ import annotations

import sys
import threading

import pytest
import wx

from app.plugins import cargador, registro, serie
from app.services.operaciones.modelo import AccionError, Politica, PreguntaError, RespuestasAutomaticas
from app.ui.decisiones import GestorDecisiones

from ..conftest import procesar_eventos


class _Operacion:
	def __init__(self, automaticas=None) -> None:
		self.respuestas_automaticas = automaticas
		self.padre = None

	def descripcion(self) -> str:
		return "Copiar de prueba"

	def raiz(self):
		return self


def test_respuestas_automaticas_sin_mostrar_nada(app_wx, caplog):
	import logging

	gestor = GestorDecisiones(None)
	operacion = _Operacion(RespuestasAutomaticas(Politica.SOBRESCRIBIR, AccionError.OMITIR, logging.getLogger("tarea")))
	resultado = {}

	def trabajo():
		resultado["conflictos"] = gestor.resolver_conflictos(operacion, [object(), object()])
		resultado["error"] = gestor.preguntar_error(operacion, PreguntaError("C:\\x", "falló", "Copiar"))

	hilo = threading.Thread(target=trabajo, daemon=True)
	with caplog.at_level(logging.INFO, logger="tarea"):
		hilo.start()
		hilo.join(5)
	assert [r.accion.value for r in resultado["conflictos"]] == ["sobrescribir", "sobrescribir"]
	assert resultado["error"] == AccionError.OMITIR
	assert not gestor.hay_pendientes()
	assert "C:\\x" in caplog.text


ACCIONES = """
formato = 1
id = "prueba.enuso"
nombre = "En uso"
descripcion = "Acción de error de prueba."
version = "1.0.0"
autor = "Pruebas"
licencia = "GPL-3.0-or-later"
api_minima = "1.0"
api_probada = "1.0"
entrada = "__init__:Complemento"

[[ordenes]]
id = "saludar"
etiqueta = "&Saludar"
ayuda = "Prueba."

[[acciones_error]]
id = "cerrar_programa"
etiqueta = "Cerrar el &programa que lo usa"
codigos_windows = [32, 33]
"""

CODIGO = """
from app.plugins import api

LLAMADAS = []

class Complemento(api.Complemento):
	def activar(self, zc):
		def funcion(pregunta):
			LLAMADAS.append(pregunta.codigo_windows)
			return api.AccionError.REINTENTAR
		zc.errores.accion("cerrar_programa", lambda pregunta: True, funcion)
		zc.ordenes.manejador("saludar", api.provisional("saludar"))
"""


@pytest.fixture
def enuso(registro_vacio, tmp_path, monkeypatch, app_wx):
	carpeta = tmp_path / "serie" / "enuso"
	carpeta.mkdir(parents=True)
	(carpeta / "manifiesto.toml").write_text(ACCIONES, encoding="utf-8")
	(carpeta / "__init__.py").write_text(CODIGO, encoding="utf-8")
	monkeypatch.setattr(serie, "SERIE", {"prueba.enuso": "1.0.0"})
	cargador.fijar_planificador(wx.CallAfter)
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


def test_accion_de_error_por_codigo_sin_activar(enuso):
	assert [a.id for a in registro.acciones_error_aplicables(PreguntaError("x", "en uso", codigo_windows=32))] == ["prueba.enuso:cerrar_programa"]
	assert registro.acciones_error_aplicables(PreguntaError("x", "sin permiso", codigo_windows=5)) == []
	assert "zcplugins.prueba__enuso" not in sys.modules, "decidir no activa el complemento"


def test_al_pulsarla_activa_el_complemento_y_llama_a_su_funcion(enuso, monkeypatch):
	gestor = GestorDecisiones(None)
	pulsada = {}

	def mostrar(dialogo):
		# El diálogo modal: se pulsa el botón de la acción del complemento (tras «Reintentar»).
		boton = dialogo.FindWindow(dialogo.ids_opciones[1])
		assert "programa" in boton.GetLabel()
		evento = wx.CommandEvent(wx.EVT_BUTTON.typeId, boton.GetId())
		evento.SetEventObject(boton)
		boton.GetEventHandler().ProcessEvent(evento)
		assert procesar_eventos(lambda: getattr(dialogo, "resultado_extra", None) is not None, 10)
		pulsada["ok"] = True
		return wx.ID_OK

	monkeypatch.setattr(wx.Dialog, "ShowModal", mostrar)
	monkeypatch.setattr(wx.Dialog, "EndModal", lambda dialogo, codigo: None)  # ShowModal falso: no hay bucle modal
	monkeypatch.setattr(gestor, "_principal_activa", lambda: True)
	monkeypatch.setattr(gestor, "es_reciente", lambda operacion: True)
	resultado = {}
	hilo = threading.Thread(target=lambda: resultado.setdefault("accion", gestor.preguntar_error(
		_Operacion(), PreguntaError("C:\\x", "en uso", "Copiar", codigo_windows=32))), daemon=True)
	hilo.start()
	assert procesar_eventos(lambda: "accion" in resultado, 15)
	hilo.join(5)
	assert resultado["accion"] == AccionError.REINTENTAR
	assert sys.modules["zcplugins.prueba__enuso"].LLAMADAS == [32]


def test_pedir_credenciales_desde_un_hilo(app_wx, monkeypatch):
	from app.ui.dialogos import rd_credenciales

	def mostrar(dialogo):
		assert isinstance(dialogo, rd_credenciales.DialogoCredenciales)
		dialogo.usuario.SetValue("ana")
		dialogo.contrasena.SetValue("secreta")
		dialogo.recordar.SetValue(True)
		return wx.ID_OK

	monkeypatch.setattr(rd_credenciales.DialogoCredenciales, "ShowModal", mostrar)
	gestor = GestorDecisiones(None)
	monkeypatch.setattr(gestor, "_principal_activa", lambda: True)
	resultado = {}
	hilo = threading.Thread(target=lambda: resultado.setdefault("valor", gestor.pedir_credenciales("Servidor", "Usuario y contraseña", "ana")), daemon=True)
	hilo.start()
	assert procesar_eventos(lambda: "valor" in resultado, 10)
	hilo.join(5)
	assert resultado["valor"] == ("ana", "secreta", True)
