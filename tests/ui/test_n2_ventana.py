# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Enganches de la 2.0 en la ventana principal (diseño 2.0, 3.4, 14.8, 14.9 y 18.2)."""

from __future__ import annotations

import importlib
from concurrent.futures import Future

import pytest

from app.plugins import api
from app.services import eventos
from app.services import servicios_nucleo as nucleo
from app.ui import ordenes
from app.ui import ventana_principal as modulo_ventana

from ..conftest import procesar_eventos


@pytest.fixture
def carpeta(tmp_path):
	(tmp_path / "uno.txt").write_text("1", encoding="utf-8")
	(tmp_path / "sub").mkdir()
	return tmp_path


class CargadorFalso(nucleo.CargadorNulo):
	"""Apunta cada paso del cierre (3.4) y permite vetarlo con puede_cerrar()."""

	def __init__(self, diario: list[str], veta: bool = False) -> None:
		self.diario = diario
		self.veta = veta
		self.tareas: list[str] = []
		diario_local = diario
		veta_local = self

		class _Complemento:
			def puede_cerrar(self_c) -> bool:
				diario_local.append("puede_cerrar")
				return not veta_local.veta

			def desactivar(self_c) -> None:
				diario_local.append("desactivar")

		self.complemento = _Complemento()

	def congelar(self) -> None:
		self.diario.append("congelar")

	def descongelar(self) -> None:
		self.diario.append("descongelar")

	def cerrar(self) -> None:
		self.diario.append("cargador.cerrar")

	def activos(self):
		return [("prueba.falso", self.complemento)]

	def ejecutar_tarea_programada(self, id: str, al_terminar) -> None:
		self.tareas.append(id)
		self.al_terminar = al_terminar


def _ventana(carpeta, monkeypatch, arranque=None, **config_extra):
	from app.core.configuracion import Configuracion
	from app.services import sesion

	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {
			"izquierdo": {"pestanas": [sesion.pestana(ruta=str(carpeta))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(carpeta / "sub"))], "actual": 0},
		},
	})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	for clave, valor in config_extra.items():
		config.establecer(clave.replace("__", "."), valor)
	return modulo_ventana.VentanaPrincipal(config, arranque=arranque)


def _cerrar(ventana) -> None:
	if ventana:
		ventana.Close(True)
		procesar_eventos(lambda: False, 0.3)


def test_instaladores_en_orden_y_uno_roto_no_impide_los_demas(app_wx, carpeta, monkeypatch):
	llamadas = []
	for nombre in modulo_ventana.INSTALADORES:
		modulo = importlib.import_module(f"app.ui.acciones.{nombre}")

		def instalar(ventana, nombre=nombre):
			llamadas.append(nombre)
			if nombre == "componentes_co":
				raise RuntimeError("instalar roto a propósito")

		monkeypatch.setattr(modulo, "instalar", instalar)
	ventana = _ventana(carpeta, monkeypatch)
	try:
		assert modulo_ventana.INSTALADORES == ("sonidos_so", "complementos_pl", "componentes_co", "actualizar_ac", "copia_cs",
			"red_rd", "personalizar_pe", "nvda_nv")
		assert llamadas == list(modulo_ventana.INSTALADORES)
	finally:
		_cerrar(ventana)


def test_servicios_nuevos_con_sus_nulos_y_registrar_servicio(app_wx, carpeta, monkeypatch):
	ventana = _ventana(carpeta, monkeypatch)
	try:
		assert ventana.servicio("eventos") is eventos.bus()
		assert ventana.servicio("grabador").grabando is False
		assert ventana.servicio("macros").en_curso() is False
		assert ventana.servicio("componentes").estado_de("no_existe") == "Falta"
		assert ventana.servicio("confirmaciones").debe_preguntar(ventana.config, "marcas_cursor")
		assert isinstance(ventana.servicio("plugins"), nucleo.CargadorNulo)
		propio = object()
		ventana.registrar_servicio("macros", propio)
		assert ventana.servicio("macros") is propio
		with pytest.raises(ValueError):
			ventana.registrar_servicio("inventado", object())
	finally:
		_cerrar(ventana)


def test_fijar_interfaz_al_construir_y_none_al_cerrar(app_wx, carpeta, monkeypatch):
	ventana = _ventana(carpeta, monkeypatch)
	assert api.interfaz() is not None
	ventana.mostrar()  # los paneles cargan la sesión al mostrarse
	assert procesar_eventos(lambda: api.interfaz().panel("activo").ruta == str(carpeta), 5)
	_cerrar(ventana)
	assert api.interfaz() is None


def test_cierre_en_el_orden_de_3_4(app_wx, carpeta, monkeypatch):
	diario: list[str] = []
	bus = eventos.bus()
	bus.suscribir(eventos.AL_CERRAR, lambda: diario.append("al_cerrar"))
	original_vaciar, original_cerrar = bus.vaciar, bus.cerrar
	monkeypatch.setattr(bus, "vaciar", lambda: (diario.append("vaciar"), original_vaciar()))
	monkeypatch.setattr(bus, "cerrar", lambda: (diario.append("bus.cerrar"), original_cerrar()))
	cargador_falso = CargadorFalso(diario, veta=True)
	ventana = _ventana(carpeta, monkeypatch, arranque=nucleo.ArranqueInfo(cargador=cargador_falso, bus=bus))
	ventana.Close()  # se puede vetar: el complemento lo veta
	procesar_eventos(lambda: False, 0.2)
	assert ventana, "el cierre se canceló"
	assert diario == ["congelar", "puede_cerrar", "descongelar"]
	diario.clear()
	cargador_falso.veta = False
	ventana.Close()
	procesar_eventos(lambda: False, 0.3)
	assert diario == ["congelar", "puede_cerrar", "vaciar", "al_cerrar", "desactivar", "bus.cerrar", "cargador.cerrar"]
	assert api.interfaz() is None


def test_modo_tarea_autocierre_sin_preguntas(app_wx, carpeta, monkeypatch):
	diario: list[str] = []
	cargador_falso = CargadorFalso(diario)
	ventana = _ventana(carpeta, monkeypatch, arranque=nucleo.ArranqueInfo(cargador=cargador_falso, bus=eventos.bus(), modo="tarea",
		tarea="copia"), general__confirmar_salida=True)
	monkeypatch.setattr(modulo_ventana, "AUTOCIERRE_MS", 10)
	from app.ui.accesibilidad import dialogos

	monkeypatch.setattr(dialogos, "confirmar", lambda *a, **k: pytest.fail("el autocierre no pregunta"))
	ventana.mostrar()
	assert procesar_eventos(lambda: cargador_falso.tareas == ["copia"], 5)
	ventana.ejecutar_tarea("otra")  # llega otra por el buzón antes de terminar la primera
	cargador_falso.al_terminar(0)  # termina la segunda...
	ventana._tareas_en_curso.add("copia")
	procesar_eventos(lambda: False, 0.3)
	assert ventana, "no cierra con otra tarea en la cola"
	ventana._tareas_en_curso.clear()
	ventana._autocierre()
	assert procesar_eventos(lambda: not ventana, 3)
	assert "puede_cerrar" not in diario, "sin fase con veto en el autocierre"


def test_menus_desde_menus_y_reconstruidos_con_al_cambiar_catalogo(app_wx, carpeta, monkeypatch):
	ventana = _ventana(carpeta, monkeypatch)
	try:
		barra = ventana.GetMenuBar()
		titulos = [barra.GetMenuLabel(i) for i in range(barra.GetMenuCount())]
		assert [t for t, _c in ordenes.menus()] == titulos
		ordenes.fijar_fuente_macros(lambda: [("Fotos", True, True)])
		assert procesar_eventos(lambda: ventana.GetMenuBar().GetMenuCount() == len(titulos) + 1, 3)
	finally:
		ordenes.fijar_fuente_macros(None)
		_cerrar(ventana)


def test_por_id_y_catalogo_ven_una_orden_registrada_despues(registro_vacio):
	from app.plugins import manifiesto

	from ..conftest import RAIZ

	assert "prueba.ejemplo:saludar" not in ordenes.POR_ID
	antes = len(ordenes.CATALOGO)
	registro_vacio.registrar(manifiesto.leer(RAIZ / "tests" / "datos" / "plugins" / "ejemplo"), RAIZ, "usuario")
	assert "prueba.ejemplo:saludar" in ordenes.POR_ID
	assert len(ordenes.CATALOGO) == antes + 1
	assert any(o.id == "prueba.ejemplo:saludar" for o in ordenes.CATALOGO)


def test_ejecutar_orden_futuro_y_eventos_de_orden(app_wx, carpeta, monkeypatch):
	ventana = _ventana(carpeta, monkeypatch)
	try:
		recibidos = []
		eventos.bus().suscribir(eventos.AL_EJECUTAR_ORDEN, lambda id, argumento: recibidos.append(("ejecutar", id)))
		eventos.bus().suscribir(eventos.AL_TERMINAR_ORDEN, lambda id, argumento, ok: recibidos.append(("terminar", id, ok)))
		futuro = ventana.ejecutar_orden_futuro("decir_ruta")
		assert isinstance(futuro, Future) and futuro.result(1) is True
		assert not ventana.ejecutar_orden_futuro("no_existe").result(1)
		procesar_eventos(lambda: len(recibidos) >= 2, 2)
		assert recibidos[:2] == [("ejecutar", "decir_ruta"), ("terminar", "decir_ruta", True)]
	finally:
		_cerrar(ventana)
