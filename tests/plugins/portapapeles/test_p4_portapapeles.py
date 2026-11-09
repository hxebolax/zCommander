# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de ``zc.portapapeles`` (diseño 2.0, 11.16 y 18.2). El portapapeles real se guarda y se devuelve."""

from __future__ import annotations

import time

import pytest

from app.plugins import api
from app.plugins.api import pruebas
from tests.plugins import p4_comun
from tests.ui import g_comun


@pytest.fixture(autouse=True)
def portapapeles_guardado():
	guardado = g_comun.guardar_portapapeles()
	yield
	g_comun.restaurar_portapapeles(guardado)


@pytest.fixture
def zc():
	zc = p4_comun.anfitrion("portapapeles")
	yield zc
	if zc.instancia is not None:
		zc.instancia.escucha.detener()


def _poner_texto(texto: str, extra: dict[str, bytes] | None = None) -> None:
	"""Escribe con la ventana propietaria y los reintentos del núcleo (con NULL, un vigilante lo cierra por debajo)."""
	import win32clipboard
	import win32con

	from app.services.windows import portapapeles as nucleo

	with nucleo._abierto() as portapapeles:
		portapapeles.EmptyClipboard()
		portapapeles.SetClipboardData(win32con.CF_UNICODETEXT, texto)
		for nombre, datos in (extra or {}).items():
			portapapeles.SetClipboardData(win32clipboard.RegisterClipboardFormat(nombre), datos)


def _esperar(condicion, segundos: float = 5.0) -> bool:
	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		if condicion():
			return True
		time.sleep(0.05)
	return condicion()


def _activo(zc):
	zc.activar()
	assert _esperar(lambda: zc.instancia.escucha.activa), zc.instancia.escucha.error
	return zc.instancia


def test_dos_textos_y_una_lista_de_archivos_en_orden(zc, tmp_path):
	from app.services.windows import portapapeles as nucleo

	complemento = _activo(zc)
	historial = p4_comun.modulo(zc, "historial")
	archivos = [tmp_path / "a.txt", tmp_path / "b.txt"]
	for archivo in archivos:
		archivo.write_text("x")
	_poner_texto("primer texto de la prueba")
	assert _esperar(lambda: any(e.texto == "primer texto de la prueba" for e in complemento.historial.elementos()))
	_poner_texto("segundo texto de la prueba")
	assert _esperar(lambda: any(e.texto == "segundo texto de la prueba" for e in complemento.historial.elementos()))
	nucleo.poner_archivos([str(a) for a in archivos])
	assert _esperar(lambda: complemento.historial.elementos()[0].tipo == historial.ARCHIVOS)
	primeros = complemento.historial.elementos()[:3]
	assert primeros[0].archivos == tuple(str(a) for a in archivos)
	assert primeros[0].contenido == f"2 archivos de {tmp_path}"
	assert [e.texto for e in primeros[1:]] == ["segundo texto de la prueba", "primer texto de la prueba"]


def test_lo_marcado_por_un_gestor_de_contrasenas_no_se_guarda(zc):
	complemento = _activo(zc)
	_poner_texto("antes de la contraseña")
	assert _esperar(lambda: any(e.texto == "antes de la contraseña" for e in complemento.historial.elementos()))
	_poner_texto("Contraseña-Secreta-1", {"ExcludeClipboardContentFromMonitorProcessing": b"\x00"})
	_poner_texto("Otra-Secreta-2", {"CanIncludeInClipboardHistory": b"\x00\x00\x00\x00"})
	_poner_texto("después de la contraseña")
	assert _esperar(lambda: any(e.texto == "después de la contraseña" for e in complemento.historial.elementos()))
	textos = [e.texto for e in complemento.historial.elementos()]
	assert "Contraseña-Secreta-1" not in textos and "Otra-Secreta-2" not in textos


def test_pegar_como_archivo_nuevo_no_sobrescribe(zc, tmp_path):
	zc.activar()
	(tmp_path / "nota.txt").write_text("ya estaba", encoding="utf-8")
	panel = pruebas.PanelFalso(ruta=str(tmp_path))
	ruta = zc.instancia.pegar_como_archivo_nuevo(panel, "línea uno\nlínea dos")
	assert ruta == str(tmp_path / "nota (2).txt")
	assert (tmp_path / "nota.txt").read_text(encoding="utf-8") == "ya estaba"
	assert (tmp_path / "nota (2).txt").read_bytes() == "línea uno\r\nlínea dos".encode()
	assert panel.refrescos == 1 and ("Creado nota (2).txt", api.RESULTADO) in zc.anuncios


def test_historial_sin_repetidos_con_maximo_y_fijados(zc):
	historial = p4_comun.modulo(zc, "historial")
	datos = historial.Historial(maximo=3)
	for texto in ("a", "b", "c"):
		datos.anadir(historial.de_texto(texto))
	fijado = datos.alternar_fijado(datos.elementos()[-1])
	assert fijado.texto == "a" and fijado.fijado
	datos.anadir(historial.de_texto("d"))
	datos.anadir(historial.de_texto("b"))
	assert [e.texto for e in datos.elementos()] == ["b", "d", "a"]
	assert [e.texto for e in datos.buscar("D")] == ["d"]


def test_guardado_cifrado_con_dpapi(zc, tmp_path):
	historial = p4_comun.modulo(zc, "historial")
	datos = historial.Historial()
	datos.anadir(historial.de_texto("texto que se guarda"))
	datos.anadir(historial.de_archivos(["C:\\x.txt"]))
	ruta = tmp_path / "historial.json"
	datos.guardar(ruta)
	assert b"texto que se guarda" not in ruta.read_bytes()
	otro = historial.Historial()
	assert otro.cargar(ruta) == 2
	assert [e.clave for e in otro.elementos()] == [e.clave for e in datos.elementos()]
	ruta.write_bytes(b"no es dpapi")
	assert historial.Historial().cargar(ruta) == 0 and not ruta.exists()


def test_copia_externa_se_anuncia_si_se_pide(zc):
	zc.activar()
	historial = p4_comun.modulo(zc, "historial")
	zc.instancia._al_copiar(historial.de_texto("hola"), True)
	assert zc.anuncios == [] and zc.sonidos_pedidos == []
	zc.config.establecer("anunciar_externas", True)
	zc.instancia._al_copiar(historial.de_texto("adiós"), True)
	zc.instancia._al_copiar(historial.de_texto("propio"), False)
	assert zc.anuncios == [("Copiado: adiós", api.NORMAL)]
	assert zc.sonidos_pedidos == ["zc.portapapeles:copia_externa"]


def test_pegar_en_la_linea_de_ordenes(zc):
	zc.activar()
	historial = p4_comun.modulo(zc, "historial")
	ventana = p4_comun.modulo(zc, "ventana")
	interfaz = p4_comun.InterfazFalsa()
	api.fijar_interfaz(interfaz)
	try:
		contexto = pruebas.contexto_de_prueba()
		zc.instancia.ejecutar_pedido(contexto, ventana.PEGAR_LINEA, historial.de_archivos(["C:\\Mis datos\\a.txt", "C:\\b.txt"]))
	finally:
		api.fijar_interfaz(None)
	assert interfaz.lineas == ['"C:\\Mis datos\\a.txt" C:\\b.txt']


def test_dialogo_pasa_revisar_teclado(zc, app_wx):
	from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

	zc.activar()
	ventana = p4_comun.modulo(zc, "ventana")
	api.fijar_interfaz(p4_comun.InterfazFalsa())
	try:
		(dialogo,) = zc.instancia.ventanas_para_revisar(None)
		afirmar_teclado_correcto(dialogo, teclas_propias=ventana.TECLAS_PROPIAS)
		assert dialogo.lista.numero_filas() == 1 and dialogo.boton_nuevo.IsEnabled() and not dialogo.boton_archivos.IsEnabled()
		dialogo.Destroy()
	finally:
		api.fijar_interfaz(None)
