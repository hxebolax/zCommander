# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Componentes externos» y enganche del bloque CO (diseño 2.0, 6.4, 6.5, 14.9 y 18.2)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

wx = pytest.importorskip("wx")

from app.core.tareas import TokenCancelacion  # noqa: E402
from app.services import actualizador  # noqa: E402
from app.services.componentes import estado, fuentes, instalar  # noqa: E402
from app.services.componentes.fuentes import Paquete, VersionNueva  # noqa: E402
from app.services.operaciones.modelo import ContextoEjecucion  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import componentes_co  # noqa: E402
from app.ui.dialogos import co_componentes  # noqa: E402
from tests.servicios import apoyo_co  # noqa: E402
from tests.servicios.apoyo_co import ServidorPrueba, sha  # noqa: E402


def _sincrono(funcion, al_terminar, al_fallar):
	try:
		resultado = funcion()
	except Exception as error:  # noqa: BLE001
		al_fallar(error)
		return
	al_terminar(resultado)


def _lanzar_sincrono(operacion, en_cola=False, al_terminar=None):
	contexto = ContextoEjecucion(TokenCancelacion(), None)
	operacion.contexto = contexto
	operacion.ejecutar(contexto)
	if al_terminar is not None:
		al_terminar(operacion)


@pytest.fixture
def servidor():
	servidor = ServidorPrueba()
	yield servidor
	servidor.cerrar()


@pytest.fixture
def gestor(tmp_path):
	return apoyo_co.gestor(apoyo_co.crear_entorno(tmp_path / "datos"))


def _dialogo(gestor, **opciones):
	return co_componentes.DialogoComponentes(None, gestor, en_hilo=_sincrono, lanzar_operacion=_lanzar_sincrono, **opciones)


def _procesar():
	from tests.conftest import procesar_eventos

	procesar_eventos(segundos=0.2)


def test_teclado_y_columnas(app_wx, gestor):
	dialogo = _dialogo(gestor, al_reiniciar=lambda: None, al_abrir_carpeta=lambda c: None)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.lista.numero_filas() == 1
		assert dialogo.lista.valores_fila(0) == ["Demo", "1.0.0", "—", "Línea base", "MIT", "Núcleo"]
		assert "Demo: instalada 1.0.0" in dialogo.detalles.GetValue()
		assert not dialogo.boton_actualizar.IsEnabled() and not dialogo.boton_volver.IsEnabled()
		assert dialogo.boton_buscar.IsEnabled() and dialogo.boton_restaurar.IsEnabled()
	finally:
		dialogo.Destroy()


def test_una_fila_sin_version_nueva_no_se_deja_marcar(app_wx, gestor):
	dialogo = _dialogo(gestor)
	try:
		dialogo.lista.CheckItem(0, True)
		_procesar()
		assert not dialogo.lista.IsItemChecked(0)
	finally:
		dialogo.Destroy()


def test_buscar_marcar_y_actualizar(app_wx, gestor, servidor, monkeypatch):
	paquete = apoyo_co.zip_de({"demo-v1.1.0/demo.exe": "demo v1.1.0"})
	nueva = VersionNueva("demo", "1.1.0", "1.1.0", [Paquete(servidor.poner("/demo.zip", paquete), "demo-v1.1.0.zip", sha(paquete),
		len(paquete), {"demo-v1.1.0/demo.exe": "demo.exe"})], novedades="Arreglos.", cambio_grande=True)
	monkeypatch.setattr(fuentes, "comprobar", lambda ficha, config: nueva if ficha["id"] == "demo" else None)
	sonidos = []
	monkeypatch.setattr(co_componentes, "_sonar", sonidos.append)
	sacadas = []
	dialogo = _dialogo(gestor, antes_de_renombrar=sacadas.append)
	try:
		dialogo.buscar()
		assert dialogo.lista.valores_fila(0)[2] == "1.1.0"
		assert "Cambio grande" in dialogo.detalles.GetValue() and "Arreglos." in dialogo.detalles.GetValue()
		assert dialogo.progreso.estado.GetValue() == "Hay una versión nueva de Demo"
		assert sonidos == ["comp.disponible"]
		dialogo.lista.CheckItem(0, True)
		_procesar()
		assert dialogo.lista.IsItemChecked(0)
		dialogo.actualizar_elegidos()
		_procesar()
		assert (gestor.entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.1.0"
		assert sacadas == [gestor.entorno.bin / "demo"]
		assert "comp.actualizado" in sonidos
		assert dialogo.lista.valores_fila(0)[:4] == ["Demo", "1.1.0", "—", "Actualizada"]
		assert dialogo.boton_volver.IsEnabled()
		assert "Demo actualizado a 1.1.0" in dialogo.progreso.estado.GetValue()
	finally:
		dialogo.Destroy()


def test_restaurar_confirma_con_la_lista_y_vuelve_a_la_base(app_wx, gestor, servidor, monkeypatch):
	paquete = apoyo_co.zip_de({"demo-v1.1.0/demo.exe": "demo v1.1.0"})
	nueva = VersionNueva("demo", "1.1.0", "1.1.0", [Paquete(servidor.poner("/demo.zip", paquete), "demo-v1.1.0.zip", sha(paquete),
		len(paquete), {"demo-v1.1.0/demo.exe": "demo.exe"})])
	assert gestor.instalador().actualizar(nueva).estado == instalar.ACTUALIZADO
	preguntas = []
	respuestas = [False, True]
	monkeypatch.setattr(co_componentes, "_confirmar", lambda padre, mensaje, titulo: preguntas.append(mensaje) or respuestas.pop(0))
	monkeypatch.setattr(co_componentes, "_sonar", lambda evento: None)
	dialogo = _dialogo(gestor)
	try:
		dialogo.restaurar_originales()
		assert "Demo: de 1.1.0 a 1.0.0" in preguntas[0]
		assert (gestor.entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.1.0", "«No» no cambia nada"
		dialogo.restaurar_originales()
		assert (gestor.entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.0.0"
		assert dialogo.lista.valores_fila(0)[3] == "Línea base"
	finally:
		dialogo.Destroy()


def test_omitir_y_abrir_carpeta(app_wx, gestor):
	estado.anotar_comprobacion({"demo": VersionNueva("demo", "1.1.0", "1.1.0", []).a_dict()}, gestor.entorno)
	abiertas = []
	dialogo = _dialogo(gestor, al_abrir_carpeta=abiertas.append)
	try:
		assert dialogo.boton_omitir.IsEnabled()
		dialogo.omitir()
		assert dialogo.lista.valores_fila(0)[2] == "1.1.0 (omitida)"
		assert not dialogo.boton_omitir.IsEnabled() and not dialogo.boton_actualizar.IsEnabled()
		dialogo.abrir_carpeta()
		assert abiertas == [gestor.entorno.bin / "demo"]
	finally:
		if dialogo:
			dialogo.Destroy()


def test_orden_abre_el_dialogo(app_wx, monkeypatch):
	abiertos = []
	monkeypatch.setattr(co_componentes.DialogoComponentes, "ShowModal", lambda self: abiertos.append(self.GetTitle()) or wx.ID_CANCEL)

	class Ventana(wx.Frame):
		tareas = None

		def lanzar_operacion(self, *args, **kwargs):
			raise AssertionError("no se lanza nada al solo abrir")

	ventana = Ventana(None)

	class Contexto:
		def __init__(self):
			self.ventana = ventana

	try:
		componentes_co.componentes(Contexto())
		assert abiertos == ["Componentes externos"]
	finally:
		ventana.Destroy()


class _VentanaFalsa:
	def __init__(self, config):
		self.config = config
		self.servicios = {}
		self.tardes = []
		self.anuncios = []

		class Tareas:
			def enviar(self_, funcion, al_terminar=None, al_fallar=None, nombre=None):
				al_terminar(funcion(None))
				return object()

		self.tareas = Tareas()

	def registrar_servicio(self, nombre, objeto):
		self.servicios[nombre] = objeto

	def llamar_mas_tarde(self, ms, funcion):
		self.tardes.append(funcion)

	def anunciar(self, texto, nivel="normal", completo="", sonido=""):
		self.anuncios.append((texto, sonido))


class _Config:
	def __init__(self, **valores):
		self.valores = {"actualizaciones.componentes_comprobar": True, "actualizaciones.componentes_intervalo_dias": 7, **valores}

	def obtener(self, clave):
		return self.valores[clave]


def test_instalar_registra_servicio_comprobacion_e_integridad(app_wx, tmp_path, monkeypatch):
	entorno = apoyo_co.crear_entorno(tmp_path / "datos")
	monkeypatch.setattr(estado.Entorno, "actual", classmethod(lambda cls: entorno))
	(entorno.bin / "demo" / "LICENCIA.txt").unlink()
	ventana = _VentanaFalsa(_Config())
	componentes_co.instalar(ventana)
	try:
		servicio = ventana.servicios["componentes"]
		assert servicio.estado_de("demo") == "Dañado" and not servicio.disponible("demo")
		assert "componentes" in actualizador.comprobaciones()
		for funcion in ventana.tardes:
			funcion()
		assert ventana.anuncios and "Faltan archivos de demo" in ventana.anuncios[0][0]
	finally:
		estado.marcar_danados([])


def test_comprobacion_periodica_y_su_intervalo(tmp_path, monkeypatch):
	entorno = apoyo_co.crear_entorno(tmp_path / "datos")
	config = _Config()
	assert componentes_co.comprobacion_activa(config, entorno)
	estado.anotar_comprobacion({}, entorno, cuando=time.time())
	assert not componentes_co.comprobacion_activa(config, entorno)
	assert componentes_co.comprobacion_activa(config, entorno, ahora=time.time() + 8 * 86400)
	assert not componentes_co.comprobacion_activa(_Config(**{"actualizaciones.componentes_comprobar": False}), entorno)
	g = apoyo_co.gestor(entorno)
	monkeypatch.setattr(fuentes, "comprobar", lambda ficha, cfg: VersionNueva("demo", "1.1.0", "1.1.0", []))
	novedades = componentes_co.comprobacion_periodica(TokenCancelacion(), g)
	assert novedades == [actualizador.Novedad("componentes", "Hay una versión nueva de un componente. Opciones, Componentes externos.", True)]
	g.omitir("demo")
	assert componentes_co.comprobacion_periodica(TokenCancelacion(), g) == []


def test_sacar_paneles_de_la_carpeta(app_wx, tmp_path):
	carpeta = tmp_path / "bin" / "demo"

	class Panel:
		def __init__(self, ruta):
			self.ruta = str(ruta)
			self.proveedor = type("P", (), {"esquema": "local"})()

		def ir_a(self, ruta):
			self.ruta = ruta

	dentro, fuera = Panel(carpeta / "sub"), Panel(tmp_path)
	ventana = type("V", (), {"todos_los_paneles": lambda self: [dentro, fuera]})()
	componentes_co.sacar_paneles(ventana, carpeta)
	assert Path(dentro.ruta) == carpeta.parent and Path(fuera.ruta) == tmp_path
