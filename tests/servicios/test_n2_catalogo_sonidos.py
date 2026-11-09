# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Catálogo y servicio de sonidos (diseño 2.0, 4.2, 4.3 y 18.2)."""

from __future__ import annotations

from app.services.sonidos import catalogo, servicio


def test_eventos_del_nucleo_unicos_y_bien_formados():
	ids = [e.id for e in catalogo.EVENTOS_NUCLEO]
	assert len(ids) == 122
	assert len(set(ids)) == len(ids)
	for evento in catalogo.EVENTOS_NUCLEO:
		assert "." in evento.id and ":" not in evento.id
		assert evento.categoria in catalogo.CATEGORIAS
		assert evento.prioridad in catalogo.PRIORIDADES
		assert evento.nombre and evento.descripcion
	progreso = catalogo.evento("op.progreso")
	assert progreso.por_defecto and len(progreso.variantes) == 11
	assert catalogo.evento("nav.carpeta_vacia").archivo_paquete() == "nav_carpeta_vacia.wav"
	assert progreso.archivo_paquete("25") == "op_progreso_25.wav"


def test_con_los_complementos_de_serie_son_153():
	todos = catalogo.eventos()
	assert len(todos) == 153
	assert len({e.id for e in todos}) == 153
	de_complementos = catalogo.eventos_de_complementos()
	assert len(de_complementos) == 31
	for evento in de_complementos:
		complemento = evento.id.split(":", 1)[0]
		assert evento.categoria == f"plugin:{complemento}"
		assert evento.prioridad in catalogo.PRIORIDADES
		assert evento.archivo_paquete() == f"plugins/{complemento}/{evento.id.split(':', 1)[1]}.wav"


class _Config:
	def __init__(self, **valores) -> None:
		self.valores = {k.replace("__", "."): v for k, v in valores.items()}

	def obtener(self, clave):
		return self.valores[clave]


class _Reproductor:
	def __init__(self) -> None:
		self.pedidos = []

	def sonar(self, evento, variante, sustituye):
		self.pedidos.append((evento.id, variante, sustituye))
		return True

	def recargar(self):
		return None

	def cerrar(self):
		return None


def test_sin_reproductor_devuelve_falso():
	servicio.cerrar()
	assert servicio.sonar("op.fin") is False


def test_con_reproductor_falso_pasa_sustituye():
	reproductor = _Reproductor()
	servicio.iniciar(_Config(sonidos__activos=True, sonidos__eventos={}), reproductor)
	try:
		assert servicio.sonar("marca.marcar", sustituye=True)
		assert servicio.sonar("op.progreso", "50")
		assert not servicio.sonar("evento.que_no_existe")
		assert reproductor.pedidos == [("marca.marcar", "", True), ("op.progreso", "50", False)]
	finally:
		servicio.cerrar()
