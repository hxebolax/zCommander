# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos y órdenes del bloque C: teclado (``revisar_teclado``), valores y lanzamiento de operaciones.

Los diálogos se construyen sin mostrarlos; las órdenes se prueban con un panel
y un contexto falsos y con ``ShowModal`` sustituido (el conftest prohíbe los reales).
"""

from __future__ import annotations

import zipfile

import pytest

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.services import sumas  # noqa: E402
from app.services.operaciones.comprimir import (  # noqa: E402
	OperacionComprimir,
	OperacionCrearSumas,
	OperacionDividir,
	OperacionExtraer,
	OperacionProbar,
	OperacionUnir,
)
from app.services.operaciones.modelo import Politica  # noqa: E402
from app.services.vfs import registro_proveedores, resolver  # noqa: E402,F401 - registra los proveedores
from app.services.vfs.local import ProveedorLocal  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import comprimidos_c  # noqa: E402
from app.ui.dialogos.c_comprimir import DialogoComprimir, DialogoExtraer  # noqa: E402
from app.ui.dialogos.c_dividir import DialogoDividir, DialogoUnir  # noqa: E402
from app.ui.dialogos.c_sumas import DialogoCrearSumas, DialogoResultadosSumas  # noqa: E402
from tests.ayudas_wx import simular_tecla  # noqa: E402


@pytest.fixture
def configuracion(tmp_path):
	config = Configuracion(ruta=tmp_path / "settings.json")
	config.establecer("operaciones.politica_conflicto", "omitir")
	return config


# ── Diálogos ────────────────────────────────────────────────────────────────


def test_dialogo_comprimir(app_wx):
	dialogo = DialogoComprimir(None, "Comprimir 2 archivos", "D:\\Copias\\datos.zip")
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=["F2"])
		assert dialogo.formato() == "zip" and dialogo.nivel() == "normal"
		assert not dialogo.campo_contrasena.IsEnabled()
		dialogo.lista_formato.SetSelection(1)
		dialogo._al_cambiar_formato(wx.CommandEvent())
		assert dialogo.formato() == "7z"
		assert dialogo.destino() == "D:\\Copias\\datos.7z"
		assert dialogo.campo_contrasena.IsEnabled()
		dialogo.campo_contrasena.SetValue("uno")
		dialogo.campo_confirmar.SetValue("dos")
		assert "no coinciden" in dialogo.problema()
		dialogo.campo_confirmar.SetValue("uno")
		assert dialogo.problema() is None
		opciones = dialogo.opciones()
		assert opciones.formato == "7z" and opciones.contrasena == "uno" and not opciones.mover
		assert simular_tecla(dialogo, wx.WXK_F2).gestionado
		assert dialogo.en_cola and dialogo.GetReturnCode() == wx.ID_OK
	finally:
		dialogo.Destroy()


def test_dialogo_extraer(app_wx, configuracion):
	dialogo = DialogoExtraer(None, "Extraer 1 archivo", "D:\\Destino", configuracion, por_carpeta=True)
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=["F2"])
		assert dialogo.politica() == Politica.OMITIR
		assert dialogo.por_carpeta() and dialogo.patron() == ""
		dialogo.campo_patron.SetValue("*.txt")
		assert dialogo.patron() == "*.txt"
		dialogo.campo_destino.SetValue("")
		assert dialogo.problema()
	finally:
		dialogo.Destroy()


def test_dialogo_crear_sumas(app_wx):
	dialogo = DialogoCrearSumas(None, "Sumas de 1 archivo", "D:\\Datos", "informe.pdf", un_archivo=True)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.algoritmo().id == "sha256"
		assert dialogo.nombre_archivo() == "informe.pdf.sha256"
		dialogo.lista_algoritmo.SetSelection(1)
		dialogo._al_cambiar_algoritmo(wx.CommandEvent())
		assert dialogo.nombre_archivo() == "informe.pdf.md5"
		dialogo.casilla_portapapeles.SetValue(True)
		dialogo._actualizar()
		assert dialogo.al_portapapeles() and not dialogo.campo_carpeta.IsEnabled()
	finally:
		dialogo.Destroy()


def test_dialogo_resultados_sumas(app_wx):
	verificaciones = [sumas.Verificacion("a.txt", sumas.Resultado.CORRECTO), sumas.Verificacion("b.txt", sumas.Resultado.DISTINTO)]
	dialogo = DialogoResultadosSumas(None, "Verificar datos.sha256", verificaciones)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.lista.GetItemCount() == 2
		assert dialogo.lista.GetItemText(1, 1) == "Distinto"
		assert dialogo.lista.GetFocusedItem() == 0
		assert dialogo.texto_resumen.GetValue() == "1 correcto, 1 distinto"
	finally:
		dialogo.Destroy()


def test_dialogos_dividir_y_unir(app_wx):
	dialogo = DialogoDividir(None, "Dividir video.mp4", "D:\\Partes", 3 * 1024 * 1024)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.tamano_parte() == 100 * 1024 * 1024
		assert not dialogo.campo_personalizado.IsEnabled()
		dialogo.lista_tamano.SetSelection(dialogo.lista_tamano.GetCount() - 1)
		dialogo._actualizar()
		assert dialogo.campo_personalizado.IsEnabled()
		dialogo.campo_personalizado.SetValue("1")
		assert dialogo.tamano_parte() == 1024 * 1024
		assert dialogo.describir() == "3 partes de 1 MB"
		dialogo.campo_personalizado.SetValue("cero")
		assert dialogo.problema()
	finally:
		dialogo.Destroy()
	dialogo = DialogoUnir(None, "Unir 3 partes", "D:\\video.mp4")
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.problema() is None
		dialogo.campo_destino.SetValue("D:\\vi:deo.mp4")
		assert dialogo.problema()
	finally:
		dialogo.Destroy()


# ── Órdenes con un contexto falso ───────────────────────────────────────────


class PanelFalso:
	def __init__(self, carpeta: str, proveedor=None) -> None:
		self.proveedor = proveedor or ProveedorLocal()
		self.ruta = carpeta
		self._cursor = None
		self.trabajo: list = []

	def es_lista(self):
		return None

	def es_local(self):
		return self.proveedor.esquema == "local"

	def ruta_local(self):
		return self.ruta if self.es_local() else None

	def mostrar_ruta(self):
		return self.proveedor.mostrar(self.ruta)

	def elementos_trabajo(self):
		return list(self.trabajo)

	def cursor(self):
		return self._cursor or (self.trabajo[0] if self.trabajo else None)

	def enfocar(self):
		pass


class CtxFalso:
	def __init__(self, activo, pasivo, config) -> None:
		self.activo, self.pasivo, self.config = activo, pasivo, config
		self.ventana = None
		self.lanzadas: list = []

	def lanzar(self, operacion, en_cola=False, al_terminar=None):
		self.lanzadas.append((operacion, en_cola, al_terminar))


@pytest.fixture
def entorno(tmp_path, configuracion):
	origen, destino = tmp_path / "origen", tmp_path / "destino"
	origen.mkdir()
	destino.mkdir()
	(origen / "a.txt").write_text("a", encoding="utf-8")
	with zipfile.ZipFile(origen / "x.zip", "w") as archivo:
		archivo.writestr("dentro.txt", "d")
	(origen / "v.bin.001").write_bytes(b"1")
	local = ProveedorLocal()
	activo, pasivo = PanelFalso(str(origen)), PanelFalso(str(destino))
	return CtxFalso(activo, pasivo, configuracion), local, origen, destino


def _aceptar_dialogos(monkeypatch, preparar=None):
	def mostrar(dialogo):
		if preparar is not None:
			preparar(dialogo)
		return wx.ID_OK

	monkeypatch.setattr(wx.Dialog, "ShowModal", mostrar)


def test_ordenes_lanzan_sus_operaciones(app_wx, entorno, monkeypatch):
	ctx, local, origen, destino = entorno
	ctx.activo.trabajo = [local.info(str(origen / "a.txt"))]
	_aceptar_dialogos(monkeypatch)
	comprimidos_c.comprimir(ctx)
	operacion = ctx.lanzadas[-1][0]
	assert isinstance(operacion, OperacionComprimir)
	assert operacion.destino == str(destino / "a.zip")
	comprimidos_c.sumas_crear(ctx)
	assert isinstance(ctx.lanzadas[-1][0], OperacionCrearSumas)
	comprimidos_c.dividir(ctx)
	assert isinstance(ctx.lanzadas[-1][0], OperacionDividir)
	assert ctx.lanzadas[-1][0].carpeta_destino == str(destino)

	ctx.activo.trabajo = [local.info(str(origen / "x.zip"))]
	comprimidos_c.extraer(ctx)
	extraccion = ctx.lanzadas[-1][0]
	assert isinstance(extraccion, OperacionExtraer) and extraccion.carpeta_destino == str(destino)
	comprimidos_c.probar(ctx)
	assert isinstance(ctx.lanzadas[-1][0], OperacionProbar)

	ctx.activo.trabajo = [local.info(str(origen / "v.bin.001"))]
	comprimidos_c.unir(ctx)
	union = ctx.lanzadas[-1][0]
	assert isinstance(union, OperacionUnir) and union.destino == str(destino / "v.bin")


def test_comprimir_por_elemento_pregunta_si_ya_existe(app_wx, entorno, monkeypatch):
	ctx, local, origen, destino = entorno
	(destino / "a.zip").write_bytes(b"")
	ctx.activo.trabajo = [local.info(str(origen / "a.txt"))]
	preguntas: list[tuple[str, list[str]]] = []

	def elegir(padre, mensaje, titulo, opciones):
		preguntas.append((mensaje, list(opciones)))
		return 2  # Cambiar el nombre

	monkeypatch.setattr("app.ui.accesibilidad.dialogos.elegir_opcion", elegir)
	_aceptar_dialogos(monkeypatch, lambda dialogo: dialogo.casilla_por_elemento.SetValue(True))
	comprimidos_c.comprimir(ctx)
	assert len(preguntas) == 1 and "a.zip" in preguntas[0][0]
	assert len(preguntas[0][1]) == 5
	operacion = ctx.lanzadas[-1][0]
	assert operacion.opciones.por_elemento and operacion.opciones.si_existe == "renombrar"
	# Cancelar no lanza nada.
	monkeypatch.setattr("app.ui.accesibilidad.dialogos.elegir_opcion", lambda *a: None)
	comprimidos_c.comprimir(ctx)
	assert len(ctx.lanzadas) == 1


def test_extraer_desde_dentro_de_un_comprimido_es_copiar(app_wx, entorno, monkeypatch):
	from app.services.operaciones.copiar import OperacionCopiar

	ctx, local, origen, destino = entorno
	proveedor = resolver.abrir_comprimido(local, str(origen / "x.zip"))
	ctx.activo = PanelFalso("", proveedor)
	ctx.activo.trabajo = proveedor.listar("")
	_aceptar_dialogos(monkeypatch)
	comprimidos_c.extraer(ctx)
	operacion = ctx.lanzadas[-1][0]
	assert isinstance(operacion, OperacionCopiar) and operacion.origen is proveedor
	comprimidos_c.probar(ctx)
	prueba = ctx.lanzadas[-1][0]
	assert isinstance(prueba, OperacionProbar) and prueba.rutas == [str(origen / "x.zip")]
	proveedor.cerrar()


def test_sin_elementos_avisa_sin_lanzar(app_wx, entorno):
	ctx, _local, _origen, _destino = entorno
	for orden in (comprimidos_c.comprimir, comprimidos_c.extraer, comprimidos_c.probar, comprimidos_c.sumas_crear,
			comprimidos_c.dividir, comprimidos_c.unir):
		orden(ctx)
	assert ctx.lanzadas == []


def test_ningun_manejador_es_provisional():
	for nombre in ("comprimir", "extraer", "probar", "sumas_crear", "sumas_verificar", "dividir", "unir"):
		assert not getattr(getattr(comprimidos_c, nombre), "provisional", False), nombre
