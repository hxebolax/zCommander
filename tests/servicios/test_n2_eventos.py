# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bus de eventos (diseño 2.0, 14.4 y 18.2)."""

from __future__ import annotations

import queue
import threading

from app.services import eventos


class _PlanificadorFalso:
	"""Hace de ``wx.CallAfter``: guarda las llamadas y las ejecuta el «hilo de la interfaz» (el de la prueba)."""

	def __init__(self) -> None:
		self.cola: queue.Queue = queue.Queue()

	def __call__(self, funcion) -> None:
		self.cola.put(funcion)

	def bombear(self) -> int:
		hechas = 0
		while not self.cola.empty():
			self.cola.get()()
			hechas += 1
		return hechas


def test_bus_unico():
	assert eventos.bus() is eventos.bus()
	nuevo = eventos.reiniciar()
	assert eventos.bus() is nuevo


def test_entrega_en_el_hilo_del_planificador_y_protegida():
	bus = eventos.Bus()
	planificador = _PlanificadorFalso()
	bus.fijar_planificador(planificador)
	recibidos: list[tuple[str, int]] = []

	def roto(**_datos):
		raise RuntimeError("suscriptor roto a propósito")

	bus.suscribir("x", roto)
	bus.suscribir("x", lambda valor: recibidos.append((threading.current_thread().name, valor)))
	hilo = threading.Thread(target=lambda: bus.emitir("x", valor=7), name="emisor")
	hilo.start()
	hilo.join()
	assert recibidos == []  # aún no ha pasado por el «bucle de eventos»
	planificador.bombear()
	assert recibidos == [(threading.current_thread().name, 7)]


def test_sin_planificador_entrega_en_el_acto():
	bus = eventos.Bus()
	recibidos = []
	cancelar = bus.suscribir("x", lambda **d: recibidos.append(d))
	bus.emitir("x", a=1)
	assert recibidos == [{"a": 1}]
	cancelar()
	bus.emitir("x", a=2)
	assert recibidos == [{"a": 1}]


def test_emitir_sincrono_llama_en_el_acto():
	bus = eventos.Bus()
	bus.fijar_planificador(_PlanificadorFalso())
	recibidos = []
	bus.suscribir("al_cerrar", lambda: recibidos.append("cerrar"))
	bus.emitir_sincrono("al_cerrar")
	assert recibidos == ["cerrar"]


def test_vaciar_entrega_en_orden_y_no_repite():
	bus = eventos.Bus()
	planificador = _PlanificadorFalso()
	bus.fijar_planificador(planificador)
	recibidos = []
	bus.suscribir("x", lambda n: recibidos.append(n))
	for n in range(3):
		bus.emitir("x", n=n)
	bus.vaciar()
	assert recibidos == [0, 1, 2]
	planificador.bombear()
	assert recibidos == [0, 1, 2]


def test_cerrar_descarta():
	bus = eventos.Bus()
	recibidos = []
	bus.suscribir("x", lambda: recibidos.append(1))
	bus.cerrar()
	bus.emitir("x")
	bus.emitir_sincrono("x")
	assert recibidos == []
	assert bus.cerrado


def test_puente_de_la_configuracion_desde_otro_hilo(tmp_path):
	from app.core.configuracion import Configuracion

	bus = eventos.reiniciar()
	planificador = _PlanificadorFalso()
	bus.fijar_planificador(planificador)
	config = Configuracion(tmp_path / "settings.json")
	cancelar = eventos.puentear_configuracion(config)
	recibidos = []
	bus.suscribir(eventos.AL_CAMBIAR_PREFERENCIA, lambda clave, anterior, nuevo: recibidos.append((clave, anterior, nuevo,
		threading.current_thread() is threading.main_thread())))
	hilo = threading.Thread(target=lambda: config.establecer("sonidos.volumen", 30))
	hilo.start()
	hilo.join()
	planificador.bombear()
	assert recibidos == [("sonidos.volumen", 70, 30, True)]
	cancelar()
