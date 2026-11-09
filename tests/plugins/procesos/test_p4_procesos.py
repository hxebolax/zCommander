# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de ``zc.procesos`` (diseño 2.0, 11.9 y 18.2): sin cerrar ningún proceso que no sea un hijo de la prueba."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from app.plugins import api, registro
from app.plugins.api import pruebas
from tests.plugins import p4_comun

HIJO = (
	"import sys, time\n"
	"f = open(sys.argv[1], 'r+b')\n"
	"print('listo', flush=True)\n"
	"time.sleep(60)\n"
)


@pytest.fixture
def zc():
	return p4_comun.anfitrion("procesos")


@pytest.fixture
def archivo_abierto(tmp_path):
	"""Un archivo que tiene abierto un proceso hijo de la prueba (nunca un proceso ajeno)."""
	ruta = tmp_path / "abierto.txt"
	ruta.write_bytes(b"contenido")
	hijo = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-c", HIJO, str(ruta)], stdout=subprocess.PIPE, text=True,
		creationflags=subprocess.CREATE_NO_WINDOW)
	assert hijo.stdout.readline().strip() == "listo"
	yield ruta, hijo
	if hijo.poll() is None:
		hijo.kill()
	hijo.wait(10)


def _modulos(zc):
	return p4_comun.modulo(zc, "uso")


def test_quien_usa_encuentra_al_hijo_con_su_pid(zc, archivo_abierto):
	ruta, hijo = archivo_abierto
	uso = _modulos(zc)
	procesos = uso.quien_usa([str(ruta)])
	assert hijo.pid in [p.pid for p in procesos]
	contexto = pruebas.contexto_de_prueba(activo=p4_comun.panel([ruta]))
	zc.ejecutar("quien_usa", contexto)
	p4_comun.esperar_tareas(zc)
	assert any(f"PID {hijo.pid}" in texto for texto, _nivel in zc.anuncios), zc.anuncios


def test_quien_usa_sin_nadie(zc, tmp_path):
	ruta = tmp_path / "libre.txt"
	ruta.write_text("x")
	uso = _modulos(zc)
	assert uso.quien_usa([str(ruta)]) == []
	assert uso.describir([]) == "Ningún programa tiene abierto el archivo"


def test_accion_de_error_solo_con_archivo_en_uso(zc):
	zc.activar()
	for codigo, esperado in ((32, True), (33, True), (5, False), (0, False)):
		pregunta = api.PreguntaError("C:\\x.txt", "mensaje cualquiera", codigo_windows=codigo)
		assert zc.instancia.aplica(pregunta) is esperado
		ids = {a.id for a in registro.acciones_error_aplicables(pregunta)}
		assert ("zc.procesos:ver_quien" in ids) is esperado
		assert ("zc.procesos:cerrar_reintentar" in ids) is esperado


def test_procesos_del_sistema_no_se_terminan(zc):
	zc.activar()
	sistema = sys.modules[type(zc.instancia).__module__ + ".sistema"] if type(zc.instancia).__module__ + ".sistema" in sys.modules \
		else p4_comun.modulo(zc, "sistema")
	procesos = {p.pid: p for p in sistema.listar()}
	nucleo = procesos.get(4) or sistema.InfoProceso(4, "System")
	assert sistema.motivo_para_no_terminar(nucleo)
	with pytest.raises(api.ErrorAcceso):
		sistema.terminar(nucleo)
	csrss = [p for p in procesos.values() if p.nombre.casefold() == "csrss.exe"]
	assert csrss and all(p.del_sistema for p in csrss)
	propio = sistema.info(os.getpid())
	assert "zCommander" in sistema.motivo_para_no_terminar(propio)
	ventana = p4_comun.modulo(zc, "ventana")
	visibles = [p.pid for p, _t in ventana.filas_de(list(procesos.values()), {}, mostrar_sistema=False)]
	assert 4 not in visibles and not any(procesos[pid].del_sistema for pid in visibles)
	con_sistema = [p.pid for p, _t in ventana.filas_de(list(procesos.values()), {}, mostrar_sistema=True)]
	assert 4 in con_sistema


def test_lista_de_procesos_con_datos_y_cpu(zc):
	zc.activar()
	sistema = p4_comun.modulo(zc, "sistema")
	medidor = sistema.MedidorCPU()
	primera = sistema.listar()
	assert all(v is None for v in medidor.medir(primera).values())
	time.sleep(0.2)
	segunda = medidor.medir(sistema.listar())
	propio = sistema.info(os.getpid())
	assert propio.ruta.lower().endswith("python.exe") and propio.memoria > 0 and propio.usuario
	assert segunda.get(os.getpid()) is not None
	assert "PID: " in sistema.resumen(propio, 1.5)


def test_cerrar_con_el_restart_manager_cierra_solo_al_hijo(zc, archivo_abierto):
	ruta, hijo = archivo_abierto
	uso = _modulos(zc)
	procesos = uso.quien_usa([str(ruta)])
	if [p.pid for p in procesos] != [hijo.pid]:
		pytest.skip(f"Otro proceso usa también el archivo: {procesos}")
	assert uso.se_puede_cerrar(procesos[0])
	quedan = uso.cerrar([str(ruta)], forzar=True)
	assert quedan == []
	hijo.wait(10)
	assert hijo.poll() is not None


def test_cerrar_y_reintentar_desde_la_pregunta_de_error(zc, archivo_abierto, monkeypatch):
	ruta, hijo = archivo_abierto
	uso = _modulos(zc)
	if [p.pid for p in uso.quien_usa([str(ruta)])] != [hijo.pid]:
		pytest.skip("Otro proceso usa también el archivo")
	interfaz = p4_comun.InterfazFalsa({"confirmar": [True, True]})
	api.fijar_interfaz(interfaz)
	ventana = p4_comun.modulo(zc, "ventana")
	monkeypatch.setattr(ventana, "esperar", lambda zc_, padre, titulo, texto, trabajo: trabajo())
	try:
		pregunta = api.PreguntaError(str(ruta), "En uso", codigo_windows=32)
		assert zc.instancia.cerrar_reintentar(pregunta) == api.AccionError.REINTENTAR
	finally:
		api.fijar_interfaz(None)
	assert [d for d in interfaz.dialogos if d[0] == "confirmar"]
	assert "zc.procesos:cerrado" in zc.sonidos_pedidos
	hijo.wait(10)


def test_cerrar_y_reintentar_no_cierra_sin_confirmar(zc, archivo_abierto):
	ruta, hijo = archivo_abierto
	zc.activar()
	interfaz = p4_comun.InterfazFalsa({"confirmar": [False]})
	api.fijar_interfaz(interfaz)
	try:
		assert zc.instancia.cerrar_reintentar(api.PreguntaError(str(ruta), "En uso", codigo_windows=32)) is None
	finally:
		api.fijar_interfaz(None)
	assert hijo.poll() is None


def test_ventanas_pasan_revisar_teclado(zc, app_wx):
	from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

	zc.activar()
	api.fijar_interfaz(p4_comun.InterfazFalsa())
	try:
		ventana_modulo = p4_comun.modulo(zc, "ventana")
		ventanas = zc.instancia.ventanas_para_revisar(None)
		assert len(ventanas) == 2
		for ventana in ventanas:
			afirmar_teclado_correcto(ventana, teclas_propias=ventana_modulo.TECLAS_PROPIAS)
			ventana.Destroy()
	finally:
		api.fijar_interfaz(None)
