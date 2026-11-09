# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de zc.proyectos (diseño 2.0, 11.15 y 18.2): frecencia, salto rápido y proyectos."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.plugins import api, registro
from tests.plugins import p5_comun

NOMBRE = "proyectos"
DIA = 86400


@pytest.fixture
def zc():
	return p5_comun.anfitrion(NOMBRE)


@pytest.fixture
def datos(zc):
	return p5_comun.modulo(NOMBRE, "datos")


def test_fact_propone_primero_la_mas_frecuente_y_reciente(datos, tmp_path):
	ahora = time.time()
	frecencia = datos.Frecencia(tmp_path)
	for _ in range(10):
		frecencia.visitar("D:\\Trabajo\\Facturas", ahora - 1 * DIA)
	for _ in range(3):
		frecencia.visitar("D:\\Viejo\\Facturas antiguas", ahora - 2 * DIA)
	frecencia.visitar("D:\\Fotos", ahora)
	frecencia.visitar("D:\\Contratos", ahora)
	propuestas = frecencia.buscar("fact", ahora=ahora)
	assert [p.ruta for p in propuestas] == ["D:\\Trabajo\\Facturas", "D:\\Viejo\\Facturas antiguas"]
	assert propuestas[0].visitas == 10


def test_la_media_vida_reduce_el_peso_de_lo_antiguo(datos, tmp_path):
	ahora = time.time()
	frecencia = datos.Frecencia(tmp_path)
	for _ in range(8):
		frecencia.visitar("D:\\Antiguo\\Facturas", ahora - 60 * DIA)
	for _ in range(2):
		frecencia.visitar("D:\\Nuevo\\Facturas", ahora)
	assert [p.ruta for p in frecencia.buscar("fact", ahora=ahora, media_vida_dias=14)][0] == "D:\\Nuevo\\Facturas"
	# Con una media vida larguísima, la frecuencia vuelve a mandar.
	assert [p.ruta for p in frecencia.buscar("fact", ahora=ahora, media_vida_dias=3650)][0] == "D:\\Antiguo\\Facturas"
	media = datos.Frecencia.puntuacion(4, ahora - 14 * DIA, ahora, 1.0, 14)
	assert media == pytest.approx(2.0)


def test_las_excluidas_no_aparecen(zc, datos):
	complemento = zc.instancia
	proveedor = SimpleNamespace(esquema="local")
	for ruta in ("C:\\Windows\\System32", "C:\\Datos\\Systemas"):
		complemento.al_cambiar_carpeta(proveedor=proveedor, ruta=ruta)
	assert [p.ruta for p in complemento.proponer("sys")] == ["C:\\Datos\\Systemas"]
	zc.config.establecer("excluidas", ["C:\\Datos"])
	assert complemento.proponer("sys") == []


def test_solo_cuenta_carpetas_del_disco(zc):
	complemento = zc.instancia
	complemento.al_cambiar_carpeta(proveedor=SimpleNamespace(esquema="sftp"), ruta="/home/ana")
	complemento.al_cambiar_carpeta(proveedor=SimpleNamespace(esquema="local"), ruta="D:\\Musica")
	assert list(complemento.frecencia.carpetas) == ["D:\\Musica"]


def test_cuenta_los_cambios_de_carpeta_del_bus_y_guarda_al_cerrar(zc, datos):
	from app.services import eventos

	eventos.bus().emitir("al_cambiar_carpeta", panel=None, proveedor=SimpleNamespace(esquema="local"), ruta="D:\\Musica")
	assert zc.instancia.frecencia.carpetas["D:\\Musica"][0] == 1
	eventos.bus().emitir_sincrono("al_cerrar")
	assert datos.Frecencia(zc.datos).cargar().carpetas["D:\\Musica"][0] == 1


def test_podar_deja_las_de_mas_puntuacion(datos, tmp_path):
	ahora = time.time()
	frecencia = datos.Frecencia(tmp_path)
	for indice in range(5):
		for _ in range(indice + 1):
			frecencia.visitar(f"D:\\c{indice}", ahora)
	frecencia.podar(2, 1.0, 14, ahora)
	assert sorted(frecencia.carpetas) == ["D:\\c3", "D:\\c4"]


def test_guardar_proyecto_sin_espacios_guarda_nota_y_carpetas(zc, datos, monkeypatch):
	def sin_espacios(nombre, nota=""):
		raise api.NoAdmitido("sin espacios")

	monkeypatch.setattr(zc.espacios, "guardar_actual", sin_espacios)
	zc.instancia.guardar_proyecto("Web", "Rediseño", ["D:\\web"])
	proyecto = datos.leer_proyectos(zc.datos)[0]
	assert (proyecto.nombre, proyecto.nota, proyecto.carpetas, proyecto.espacio) == ("Web", "Rediseño", ["D:\\web"], "")


def test_abrir_proyecto_usa_el_espacio_de_trabajo(zc, datos, monkeypatch):
	abiertos: list[str] = []
	monkeypatch.setattr(zc.espacios, "listar", lambda: ["Web"])
	monkeypatch.setattr(zc.espacios, "abrir", abiertos.append)
	assert zc.instancia.abrir_proyecto(datos.Proyecto("Web", espacio="Web"))
	assert abiertos == ["Web"]


def test_ordenes_con_manejador_real(zc):
	for orden in ("salto", "proyectos"):
		manejador = registro.manejador(f"zc.proyectos:{orden}")
		assert manejador is not None and not getattr(manejador, "provisional", False)


# ── Diálogos (wx) ────────────────────────────────────────────────────────────


@pytest.fixture
def interfaz(app_wx):
	creada = p5_comun.con_interfaz()
	yield creada
	api.fijar_interfaz(None)


def test_dialogos_pasan_revisar_teclado(zc, interfaz):
	ventanas = zc.instancia.ventanas_para_revisar(None)
	assert len(ventanas) == 3
	try:
		for ventana in ventanas:
			assert p5_comun.problemas_de_teclado(ventana) == [], ventana.GetTitle()
	finally:
		for ventana in ventanas:
			ventana.Destroy()


def test_salto_filtra_al_escribir_y_elige_la_primera(zc, interfaz):
	complemento = zc.instancia
	proveedor = SimpleNamespace(esquema="local")
	for _ in range(3):
		complemento.al_cambiar_carpeta(proveedor=proveedor, ruta="D:\\Facturas")
	complemento.al_cambiar_carpeta(proveedor=proveedor, ruta="D:\\Fotos")
	ventana = p5_comun.modulo(NOMBRE, "ventana")
	dialogo = ventana.DialogoSalto(complemento, None, recientes_windows=False)
	try:
		assert dialogo.lista.numero_filas() == 2
		dialogo.campo.SetValue("fact")
		assert dialogo.lista.numero_filas() == 1
		assert dialogo.elegida() == "D:\\Facturas"
		dialogo.anadir_windows(["E:\\Facturas viejas", "E:\\Otra"])
		assert [p.ruta for p in dialogo.propuestas] == ["D:\\Facturas", "E:\\Facturas viejas"]
		assert dialogo.lista.valores_fila(1)[1] == "Reciente de Windows"
	finally:
		dialogo.Destroy()
