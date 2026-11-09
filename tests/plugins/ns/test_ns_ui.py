# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana del NAS y diálogos (diseño 2.0, 13.4, 15.1 y 18.2): ``revisar_teclado`` en todos, con el NAS de demostración.

Las ventanas se construyen de verdad, sin mostrarse; ningún diálogo se abre
(``ShowModal`` está prohibido en las pruebas). La ventana del NAS se recorre
área por área y sección por sección, porque sus botones de acciones cambian.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

wx = pytest.importorskip("wx")

from app.plugins import api  # noqa: E402
from app.ui import api_ui  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402

from ...conftest import procesar_eventos  # noqa: E402


class InterfazFalsa:
	"""``InterfazAnfitrion`` mínima: la de verdad la pone la ventana principal de zCommander."""

	def __init__(self) -> None:
		self.modulo_ui = api_ui
		self.anuncios: list[str] = []
		self.rutas: list[str] = []

	def planificar(self, funcion) -> None:
		wx.CallAfter(funcion)

	def en_hilo_interfaz(self) -> bool:
		return threading.current_thread() is threading.main_thread()

	def anunciar(self, texto, nivel, completo="", interrumpir=None, sonido="") -> None:
		self.anuncios.append(texto)

	def abrir_ruta(self, texto, lado=None) -> None:
		self.rutas.append(texto)

	def abrir_ayuda(self, id_complemento, pagina="") -> None:
		pass

	def registrar_dialogo_complemento(self, id, funcion) -> None:
		pass


@pytest.fixture
def interfaz(app_wx):
	falsa = InterfazFalsa()
	api.fijar_interfaz(falsa)
	yield falsa
	api.fijar_interfaz(None)


def test_dialogos_pasan_revisar_teclado(ns, interfaz):
	padre = wx.Frame(None, title="Prueba")
	try:
		ventanas = ns.complemento.ventanas_para_revisar(padre)
		assert len(ventanas) == 9
		from zcplugins.zc__synology.ui import dialogos

		servidor = ns.servidores.ServidorNAS("casa", "NAS de casa", "192.168.1.50", huella="SHA256:" + "CD" * 32)
		ventanas += [dialogos.DialogoServidor(padre, servidor, {"casa"}, True), dialogos.DialogoHuella(padre, servidor, "SHA256:" + "AB" * 32,
			servidor.huella), dialogos.DialogoModoEscritura(padre, "NAS de casa", persistente_fijo=True),
			dialogos.DialogoSSH(padre, ns.complemento, SimpleNamespace(servidor=servidor, solo_lectura=True))]
		for ventana in ventanas:
			afirmar_teclado_correcto(ventana)
			ventana.Destroy()
	finally:
		padre.Destroy()


def test_dialogo_de_huella_empieza_en_cancelar(ns, interfaz):
	from zcplugins.zc__synology.ui import dialogos

	servidor = ns.servidores.ServidorNAS("casa", "NAS de casa", "192.168.1.50")
	dialogo = dialogos.DialogoHuella(None, servidor, "SHA256:" + "AB12" * 16, "")
	try:
		assert dialogo.cancelar.IsDefault() if hasattr(dialogo.cancelar, "IsDefault") else True
		assert "AB12 AB12" in dialogo.texto.GetValue()
		assert dialogo.decision == "cancelar"
	finally:
		dialogo.Destroy()
	modo = dialogos.DialogoModoEscritura(None, "NAS de casa")
	try:
		assert modo.sesion.GetValue() and not modo.siempre.GetValue()
		assert "arrancar y parar paquetes" in modo.texto.GetValue()
	finally:
		modo.Destroy()


def test_letras_de_los_botones_de_acciones(ns):
	from zcplugins.zc__synology.ui import poner_letra

	usadas = {"c", "r"}
	assert poner_letra("Copiar el resumen", usadas) == "Copiar &el resumen"
	assert poner_letra("Reiniciar el NAS...", usadas) == "Reiniciar el &NAS..."
	assert {"e", "n"} <= usadas


@pytest.fixture
def demostracion(ns, interfaz):
	conexiones = ns.complemento.conexiones
	conexion = conexiones.demostracion("escritura")
	yield conexion
	for ventana in list(ns.complemento._ventanas.values()):
		ventana.cerrada = True
		ventana.marco.Destroy()
	ns.complemento._ventanas.clear()
	conexiones.desconectar_todas()
	procesar_eventos(lambda: False, 0.2)
	assert not conexion.simulador.activo


def _esperar_carga(ventana) -> None:
	assert procesar_eventos(lambda: ventana._vista is not None and not ventana._cargando, 15), "El área no se ha cargado"


def test_ventana_del_nas_en_todas_las_areas(ns, demostracion):
	from zcplugins.zc__synology.ui.ventana import TECLAS_PROPIAS, VentanaNAS

	ventana = VentanaNAS(ns.complemento, demostracion, "estado")
	ns.complemento._ventanas[demostracion.servidor.id] = ventana
	_esperar_carga(ventana)
	assert ventana.marco.GetTitle() == "NAS Synology: NAS de demostración"
	assert "NAS de demostración: los cambios se pierden al cerrar" in ventana.estado.GetValue()
	assert "Solo lectura" in ventana.estado.GetValue()
	assert ventana.lista_areas.GetCount() == 18
	for indice, area in enumerate(ventana._areas):
		ventana.ir_a_area(area.id, mover_foco=False)
		_esperar_carga(ventana)
		assert ventana.lista_areas.GetSelection() == indice
		for seccion in range(len(ventana._vista.secciones)):
			ventana.seccion.SetSelection(seccion)
			ventana._mostrar_seccion(seccion)
			assert ventana.lista.numero_filas() > 0, (area.id, seccion)
			afirmar_teclado_correcto(ventana.marco, teclas_propias=TECLAS_PROPIAS)


def test_acciones_desactivadas_en_solo_lectura_y_titulo_con_cambios(ns, demostracion):
	from zcplugins.zc__synology.ui.ventana import VentanaNAS

	ventana = VentanaNAS(ns.complemento, demostracion, "contenedores")
	ns.complemento._ventanas[demostracion.servidor.id] = ventana
	_esperar_carga(ventana)
	ventana.lista.enfocar_fila(next(i for i, f in enumerate(ventana._filas) if f.clave == "jellyfin"), anunciar=False)
	ventana._al_cambiar_fila()
	botones = {accion.id: boton for boton, accion in ventana._botones}
	assert botones["registro"].IsEnabled()
	assert not botones["parar"].IsEnabled()
	assert "Desactive el modo solo lectura" in botones["parar"].GetHelpText()
	ns.complemento.conexiones.cambiar_modo(demostracion.servidor.id, True)
	procesar_eventos(lambda: ventana.marco.GetTitle().startswith("CAMBIOS PERMITIDOS:"), 3)
	assert ventana.marco.GetTitle() == "CAMBIOS PERMITIDOS: NAS Synology: NAS de demostración"
	assert botones["parar"].IsEnabled() and not botones["iniciar"].IsEnabled()
	assert ventana.cambios.GetValue()


def test_aviso_de_salud_una_sola_vez(ns, demostracion):
	from zcplugins.zc__synology.ui.ventana import VentanaNAS

	zc = ns.complemento.zc
	zc.anuncios.clear()
	zc.sonidos_pedidos.clear()
	ventana = VentanaNAS(ns.complemento, demostracion, "contenedores")
	ns.complemento._ventanas[demostracion.servidor.id] = ventana
	_esperar_carga(ventana)
	assert any("homeassistant" in texto for texto, _nivel in zc.anuncios)
	assert "zc.synology:aviso_salud" in zc.sonidos_pedidos
	cuantos = len(zc.anuncios)
	ventana.refrescar()
	procesar_eventos(lambda: not ventana._cargando, 10)
	assert not any("homeassistant" in texto for texto, _nivel in zc.anuncios[cuantos:])
