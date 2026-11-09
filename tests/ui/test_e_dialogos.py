# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos y órdenes del bloque E: renombrado múltiple, atributos y fechas, crear enlace.

Los diálogos se construyen sin mostrarlos (el conftest prohíbe ``ShowModal``);
las órdenes se prueban con un panel y un contexto falsos que cumplen lo que
usan de ``PanelProtocolo`` y ``ContextoOrden``.
"""

from __future__ import annotations

import os
import time

import pytest

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.services import formato, renombrado  # noqa: E402
from app.services.operaciones.atributos import CambiosAtributos, OperacionAtributos  # noqa: E402
from app.services.operaciones.renombrar import OperacionRenombrar  # noqa: E402
from app.services.vfs import base  # noqa: E402
from app.services.vfs.local import ProveedorLocal  # noqa: E402
from app.services.vfs.resultados import ProveedorResultados  # noqa: E402
from app.services.windows import enlaces  # noqa: E402
from app.ui import anuncios  # noqa: E402
from app.ui.acciones import edicion_e  # noqa: E402
from app.ui.accesibilidad import dialogos as dialogos_accesibles  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.dialogos import e_atributos, e_enlace, e_renombrado  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402

def _elementos(*nombres: str, carpeta: str = "C:\\Fotos") -> list[renombrado.Elemento]:
	return [renombrado.Elemento(ruta=f"{carpeta}\\{n}", nombre=n, carpeta_ruta=carpeta, carpeta="Fotos", modificado=0.0)
		for n in nombres]


@pytest.fixture
def avisos(monkeypatch):
	dichos: list[str] = []
	for modulo in (e_renombrado, e_atributos, e_enlace):
		monkeypatch.setattr(modulo, "_avisar", lambda padre, mensaje, titulo: dichos.append(mensaje))
	return dichos


# ── Renombrado múltiple ─────────────────────────────────────────────────────

def test_renombrado_teclado(app_wx):
	dialogo = e_renombrado.DialogoRenombrado(None, _elementos("a.jpg", "b.jpg"))
	try:
		afirmar_teclado_correcto(dialogo, con_avisos=True)
		assert dialogo.GetTitle() == "Renombrado múltiple"
		assert dialogo.lista.GetColumnCount() == 3
		assert dialogo.lista.GetName() == "Vista previa de los nombres"
	finally:
		dialogo.Destroy()


def test_vista_previa_inicial_y_al_teclear(app_wx):
	dialogo = e_renombrado.DialogoRenombrado(None, _elementos("a.jpg", "b.jpg", "c.jpg"))
	try:
		assert dialogo.campo_mascara_nombre.GetValue() == "[N]"
		assert dialogo.campo_mascara_extension.GetValue() == "[E]"
		assert dialogo.lista.numero_filas() == 3
		assert dialogo.lista.valores_fila(0) == ["a.jpg", "a.jpg", "Sin cambios"]
		assert dialogo.campo_resumen.GetValue() == "0 se renombran, 3 sin cambios"
		# Al teclear se espera 300 ms sin pulsaciones antes de recalcular.
		dialogo.campo_mascara_nombre.SetValue("foto [C:2]")
		assert dialogo.lista.valores_fila(0)[1] == "a.jpg"
		assert procesar_eventos(lambda: dialogo.lista.valores_fila(0)[1] == "foto 01.jpg", segundos=3)
		assert dialogo.lista.valores_fila(2) == ["c.jpg", "foto 03.jpg", "Correcto"]
		assert dialogo.campo_resumen.GetValue() == "3 se renombran"
		# Las casillas y los desplegables recalculan al momento.
		dialogo.lista_mayusculas_extension.SetSelection(renombrado.MAYUSCULAS.index("mayusculas"))
		dialogo.lista_mayusculas_extension.ProcessWindowEvent(wx.CommandEvent(wx.wxEVT_CHOICE, dialogo.lista_mayusculas_extension.GetId()))
		assert dialogo.lista.valores_fila(0)[1] == "foto 01.JPG"
	finally:
		dialogo.Destroy()


def test_renombrar_rechaza_duplicados_y_enfoca_la_fila(app_wx, avisos):
	dialogo = e_renombrado.DialogoRenombrado(None, _elementos("a.jpg", "b.jpg", "c.jpg"))
	try:
		dialogo.campo_buscar.ChangeValue("b")
		dialogo.campo_reemplazar.ChangeValue("a")
		dialogo.SetReturnCode(0)
		assert dialogo.aceptar() is False
		assert avisos and "Duplicado" in avisos[-1] and "b.jpg" in avisos[-1]
		assert dialogo.lista.GetFocusedItem() == 1
		assert dialogo.GetReturnCode() != wx.ID_OK
		# Sin nada que cambiar tampoco se renombra.
		dialogo.campo_buscar.ChangeValue("")
		assert dialogo.aceptar() is False
		assert "No hay nombres que cambiar" in avisos[-1]
		# Máscara no válida.
		dialogo.campo_mascara_nombre.ChangeValue("[N")
		assert dialogo.aceptar() is False
		assert "Máscara no válida" in avisos[-1]
		# Correcto.
		dialogo.campo_mascara_nombre.ChangeValue("[N]-1")
		assert dialogo.aceptar() is True
		assert dialogo.GetReturnCode() == wx.ID_OK
		assert dialogo.pares() == [("C:\\Fotos\\a.jpg", "a-1.jpg"), ("C:\\Fotos\\b.jpg", "b-1.jpg"), ("C:\\Fotos\\c.jpg", "c-1.jpg")]
	finally:
		dialogo.Destroy()


def test_nombre_no_valido_en_la_vista_previa(app_wx, avisos):
	dialogo = e_renombrado.DialogoRenombrado(None, _elementos("a.txt"))
	try:
		dialogo.campo_mascara_nombre.ChangeValue("a:b")
		dialogo.actualizar_vista_previa()
		assert dialogo.lista.valores_fila(0)[2] == "Nombre no válido: carácter :"
		assert dialogo.aceptar() is False
	finally:
		dialogo.Destroy()


def test_insertar_marcador(app_wx):
	dialogo = e_renombrado.DialogoRenombrado(None, _elementos("a.txt"))
	try:
		menu, ids = dialogo.menu_marcadores()
		try:
			assert "[C10+5:3]" in ids.values() and "[[" in ids.values()
			assert menu.GetMenuItemCount() == len(renombrado.marcadores())
		finally:
			menu.Destroy()
		# Todo seleccionado (se llegó con Tab): se añade al final.
		dialogo.campo_mascara_nombre.SelectAll()
		dialogo.insertar_marcador("_[Y]")
		assert dialogo.campo_mascara_nombre.GetValue() == "[N]_[Y]"
		# Con el cursor en medio, se escribe ahí.
		dialogo.campo_mascara_nombre.SetSelection(3, 3)
		dialogo.insertar_marcador("-")
		assert dialogo.campo_mascara_nombre.GetValue() == "[N]-_[Y]"
	finally:
		dialogo.Destroy()


def test_plantillas(app_wx, avisos, monkeypatch):
	monkeypatch.setattr(e_renombrado, "_pedir_nombre_plantilla", lambda padre, valor: "Viaje")
	monkeypatch.setattr(e_renombrado, "_confirmar", lambda padre, mensaje, titulo: True)
	dialogo = e_renombrado.DialogoRenombrado(None, _elementos("a.txt"))
	try:
		menu, acciones = dialogo.menu_plantillas()
		menu.Destroy()
		assert list(acciones.values()) == [("guardar", "")]
		dialogo.campo_mascara_nombre.ChangeValue("[d]_[C]")
		dialogo.casilla_regex.SetValue(True)
		assert dialogo.guardar_plantilla() is True
		menu, acciones = dialogo.menu_plantillas()
		menu.Destroy()
		assert ("cargar", "Viaje") in acciones.values() and ("borrar", "Viaje") in acciones.values()
		dialogo.aplicar_opciones(renombrado.OpcionesRenombrado())
		assert dialogo.cargar_plantilla("Viaje") is True
		assert dialogo.campo_mascara_nombre.GetValue() == "[d]_[C]"
		assert dialogo.casilla_regex.GetValue() is True
		assert dialogo.borrar_plantilla("Viaje") is True
		assert renombrado.leer_plantillas() == []
	finally:
		dialogo.Destroy()


# ── Atributos y fechas ──────────────────────────────────────────────────────

def _entrada(nombre: str, atributos: int = 0, es_carpeta: bool = False, permisos: int = -1) -> base.Entrada:
	return base.Entrada(nombre, f"C:\\x\\{nombre}", es_carpeta=es_carpeta, atributos=atributos, modificado=time.time(),
		creado=time.time(), permisos=permisos)


@pytest.mark.parametrize("varios", [False, True])
def test_atributos_teclado(app_wx, varios):
	entradas = [_entrada("a.txt"), _entrada("sub", es_carpeta=True)] if varios else [_entrada("a.txt")]
	dialogo = e_atributos.DialogoAtributos(None, entradas, permisos=True)
	try:
		afirmar_teclado_correcto(dialogo, con_avisos=True)
		assert (dialogo.casilla_recursivo is not None) == varios
		assert dialogo.casillas[formato.SOLO_LECTURA].Is3State() == varios
	finally:
		dialogo.Destroy()


def test_atributos_tres_estados_y_solo_lo_cambiado(app_wx):
	entradas = [_entrada("a.txt", formato.SOLO_LECTURA | formato.ARCHIVO), _entrada("b.txt", formato.ARCHIVO)]
	dialogo = e_atributos.DialogoAtributos(None, entradas)
	try:
		casillas = dialogo.casillas
		assert casillas[formato.SOLO_LECTURA].Get3StateValue() == wx.CHK_UNDETERMINED
		assert casillas[formato.ARCHIVO].Get3StateValue() == wx.CHK_CHECKED
		assert casillas[formato.OCULTO].Get3StateValue() == wx.CHK_UNCHECKED
		assert dialogo.cambios().vacio
		casillas[formato.SOLO_LECTURA].Set3StateValue(wx.CHK_UNCHECKED)
		casillas[formato.OCULTO].Set3StateValue(wx.CHK_CHECKED)
		cambios = dialogo.cambios()
		assert cambios.quitar == formato.SOLO_LECTURA
		assert cambios.poner == formato.OCULTO
		assert cambios.modificado is None and cambios.creado is None and not cambios.recursivo
	finally:
		dialogo.Destroy()


def test_atributos_fechas(app_wx, avisos):
	dialogo = e_atributos.DialogoAtributos(None, [_entrada("a.txt")])
	try:
		assert dialogo.casilla_sin_modificacion.GetValue() is True
		assert not dialogo.campo_modificacion.IsEnabled()
		# «Ahora» desmarca «sin cambio» y escribe la fecha actual.
		dialogo.boton_ahora_modificacion.ProcessWindowEvent(wx.CommandEvent(wx.wxEVT_BUTTON, dialogo.boton_ahora_modificacion.GetId()))
		assert dialogo.casilla_sin_modificacion.GetValue() is False
		assert abs(dialogo.cambios().modificado - time.time()) < 5
		dialogo.campo_modificacion.SetValue("mañana")
		dialogo.SetReturnCode(0)
		assert dialogo.aceptar() is False
		assert avisos and "No se entiende la fecha" in avisos[-1]
		dialogo.campo_modificacion.SetValue("2020-01-02 03:04:05")
		assert dialogo.aceptar() is True
		assert time.localtime(dialogo.cambios().modificado)[:6] == (2020, 1, 2, 3, 4, 5)
		assert dialogo.cambios().creado is None
	finally:
		dialogo.Destroy()


def test_atributos_permisos(app_wx, avisos):
	dialogo = e_atributos.DialogoAtributos(None, [_entrada("x.sh", permisos=0o600)], atributos=False, creacion=False, permisos=True)
	try:
		assert not dialogo.casillas
		assert dialogo.campo_permisos.GetValue() == "600"
		dialogo.campo_permisos.SetValue("9")
		assert dialogo.aceptar() is False and "permisos" in avisos[-1]
		dialogo.campo_permisos.SetValue("755")
		assert dialogo.aceptar() is True
		assert dialogo.cambios().permisos == 0o755
	finally:
		dialogo.Destroy()


# ── Crear enlace ────────────────────────────────────────────────────────────

def test_enlace_teclado_y_tipos(app_wx, tmp_path):
	destino = tmp_path / "datos"
	destino.mkdir()
	dialogo = e_enlace.DialogoEnlace(None, str(destino), str(tmp_path / "otro"))
	try:
		afirmar_teclado_correcto(dialogo, con_avisos=True)
		assert dialogo.lista_tipo.GetCount() == 4
		assert "modo de desarrollador" in dialogo.campo_explicacion.GetValue()
		dialogo.elegir_tipo(enlaces.ACCESO_DIRECTO)
		assert dialogo.enlace().endswith("otro.lnk")
		dialogo.elegir_tipo(enlaces.UNION)
		assert dialogo.enlace() == str(tmp_path / "otro")
		assert "unión" in dialogo.campo_explicacion.GetValue().lower()
	finally:
		dialogo.Destroy()


def test_enlace_valida_al_aceptar(app_wx, tmp_path, avisos):
	(tmp_path / "nota.txt").write_text("x", encoding="utf-8")
	dialogo = e_enlace.DialogoEnlace(None, str(tmp_path / "nota.txt"), str(tmp_path / "enlace"), enlaces.UNION)
	try:
		dialogo.SetReturnCode(0)
		assert dialogo.aceptar() is False
		assert "solo puede apuntar a una carpeta" in avisos[-1]
		dialogo.elegir_tipo(enlaces.DURO)
		assert dialogo.aceptar() is True
		assert dialogo.GetReturnCode() == wx.ID_OK
	finally:
		dialogo.Destroy()


# ── Órdenes con un panel y un contexto falsos ───────────────────────────────

class PanelFalso:
	lado = "izquierdo"

	def __init__(self, proveedor, ruta: str, entradas: list[base.Entrada], marcadas: list[base.Entrada] | None = None) -> None:
		self._proveedor = proveedor
		self._ruta = ruta
		self._entradas = entradas
		self._marcadas = marcadas or []
		self.refrescos = 0
		self.ir_a: list[str] = []

	@property
	def proveedor(self):
		return self._proveedor

	@property
	def ruta(self) -> str:
		return self._ruta

	def mostrar_ruta(self) -> str:
		return self._proveedor.mostrar(self._ruta)

	def es_local(self) -> bool:
		return self._proveedor.esquema == "local"

	def es_lista(self):
		return "Resultados" if self._proveedor.esquema == "resultados" else None

	def ruta_local(self):
		return self._ruta if self.es_local() else None

	def entradas(self):
		return list(self._entradas)

	def cursor(self):
		return self._entradas[0] if self._entradas else None

	def marcadas(self):
		return list(self._marcadas)

	def elementos_trabajo(self):
		return list(self._marcadas) or [e for e in self._entradas[:1] if not e.es_superior]

	def refrescar(self, conservar: bool = True, al_terminar=None) -> None:
		self.refrescos += 1
		if al_terminar:
			al_terminar(True)

	def ir_a_nombre(self, nombre: str) -> bool:
		self.ir_a.append(nombre)
		return True


class TareasFalsas:
	"""Ejecuta en el acto (en este hilo) y llama a al_terminar o al_fallar como el gestor real."""

	def enviar(self, funcion, *args, al_terminar=None, al_fallar=None, nombre=None, **_resto):
		try:
			resultado = funcion(None, *args)
		except Exception as error:  # noqa: BLE001 - se reenvía a al_fallar como hace GestorTareas
			if al_fallar:
				al_fallar(error)
			return None
		if al_terminar:
			al_terminar(resultado)
		return None


class ContextoFalso:
	def __init__(self, activo, pasivo, config) -> None:
		self.activo = activo
		self.pasivo = pasivo
		self.ventana = None
		self.config = config
		self.tareas = TareasFalsas()
		self.lanzadas: list = []

	def lanzar(self, operacion, en_cola: bool = False, al_terminar=None) -> None:
		self.lanzadas.append((operacion, al_terminar))


@pytest.fixture
def config(tmp_path_factory):
	# Fuera de tmp_path: las pruebas listan esa carpeta y no debe aparecer el archivo de configuración.
	return Configuracion(ruta=tmp_path_factory.mktemp("config") / "settings.json")


def test_ninguna_orden_es_provisional():
	for nombre in ("renombrado_multiple", "atributos", "crear_enlace"):
		manejador = getattr(edicion_e, nombre)
		assert callable(manejador) and not getattr(manejador, "provisional", False), nombre


def test_orden_renombrado_multiple(app_wx, tmp_path, config, monkeypatch):
	(tmp_path / "a.txt").write_text("a", encoding="utf-8")
	(tmp_path / "b.txt").write_text("b", encoding="utf-8")
	local = ProveedorLocal()
	entradas = sorted(local.listar(str(tmp_path)), key=lambda e: e.nombre)
	panel = PanelFalso(local, str(tmp_path), entradas, marcadas=entradas)
	ctx = ContextoFalso(panel, PanelFalso(local, str(tmp_path), []), config)
	vistos = {}

	def pedir(padre, elementos, existentes, validar_windows, leer_preferencias):
		vistos.update(elementos=elementos, existentes=existentes, validar=validar_windows, preferencias=leer_preferencias())
		calculo = renombrado.calcular(elementos, renombrado.OpcionesRenombrado(mascara_nombre="[N]_[C]"), existentes)
		return renombrado.pares(calculo)

	monkeypatch.setattr(e_renombrado, "pedir_renombrado", pedir)
	edicion_e.renombrado_multiple(ctx)
	assert [e.nombre for e in vistos["elementos"]] == ["a.txt", "b.txt"]
	assert vistos["validar"] is True
	assert set(vistos["existentes"][str(tmp_path)]) == {"a.txt", "b.txt"}
	(operacion, al_terminar), = ctx.lanzadas
	assert isinstance(operacion, OperacionRenombrar)
	assert operacion.descripcion() == f"Renombrar 2 elementos en {tmp_path}"
	assert operacion.pares == [(str(tmp_path / "a.txt"), "a_1.txt"), (str(tmp_path / "b.txt"), "b_2.txt")]
	al_terminar(operacion)
	assert panel.ir_a == ["a_1.txt"]


def test_orden_renombrado_sin_elementos(app_wx, tmp_path, config):
	panel = PanelFalso(ProveedorLocal(), str(tmp_path), [])
	ctx = ContextoFalso(panel, panel, config)
	edicion_e.renombrado_multiple(ctx)
	assert not ctx.lanzadas
	assert anuncios.historial()[-1].texto == "No hay elementos para renombrar"


def test_renombrado_en_lista_de_resultados(app_wx, tmp_path, config, monkeypatch):
	(tmp_path / "a.txt").write_text("a", encoding="utf-8")
	resultados = ProveedorResultados("Búsqueda", [str(tmp_path / "a.txt")])
	entradas = resultados.listar("")
	panel = PanelFalso(resultados, "", entradas)
	ctx = ContextoFalso(panel, panel, config)
	monkeypatch.setattr(e_renombrado, "pedir_renombrado", lambda padre, elementos, existentes, validar_windows, leer_preferencias:
		[(elementos[0].ruta, "z.txt")] if existentes is None and elementos[0].carpeta_ruta == str(tmp_path) else None)
	edicion_e.renombrado_multiple(ctx)
	(operacion, al_terminar), = ctx.lanzadas
	assert operacion.proveedor.esquema == "local"  # el de resultados no sabe la carpeta de cada ruta
	operacion.ejecutar(_contexto_ejecucion())
	al_terminar(operacion)
	assert (tmp_path / "z.txt").exists()
	assert resultados.rutas == [str(tmp_path / "z.txt")]


def _contexto_ejecucion():
	import threading

	from app.services.operaciones.modelo import ContextoEjecucion

	return ContextoEjecucion(threading.Event(), decisor=None)


def test_orden_atributos(app_wx, tmp_path, config, monkeypatch):
	(tmp_path / "a.txt").write_text("a", encoding="utf-8")
	local = ProveedorLocal()
	panel = PanelFalso(local, str(tmp_path), local.listar(str(tmp_path)))
	ctx = ContextoFalso(panel, panel, config)
	pedidos = {}

	def pedir(padre, entradas, atributos, fechas, creacion, permisos):
		pedidos.update(atributos=atributos, fechas=fechas, creacion=creacion, permisos=permisos)
		return CambiosAtributos(poner=formato.OCULTO)

	monkeypatch.setattr(e_atributos, "pedir_atributos", pedir)
	edicion_e.atributos(ctx)
	assert pedidos == {"atributos": True, "fechas": True, "creacion": True, "permisos": False}
	(operacion, _al_terminar), = ctx.lanzadas
	assert isinstance(operacion, OperacionAtributos) and operacion.cambios.poner == formato.OCULTO
	# Sin cambios no se lanza nada.
	monkeypatch.setattr(e_atributos, "pedir_atributos", lambda *a, **k: CambiosAtributos())
	edicion_e.atributos(ctx)
	assert len(ctx.lanzadas) == 1
	assert anuncios.historial()[-1].texto == "No ha cambiado nada"


def test_orden_crear_enlace_union(app_wx, tmp_path, config, monkeypatch):
	(tmp_path / "izq" / "datos").mkdir(parents=True)
	(tmp_path / "der").mkdir()
	local = ProveedorLocal()
	activo = PanelFalso(local, str(tmp_path / "izq"), local.listar(str(tmp_path / "izq")))
	pasivo = PanelFalso(local, str(tmp_path / "der"), [])
	ctx = ContextoFalso(activo, pasivo, config)
	propuesto = {}

	def pedir(padre, destino, enlace, tipo):
		propuesto.update(destino=destino, enlace=enlace, tipo=tipo)
		return enlaces.UNION, enlace, destino

	monkeypatch.setattr(e_enlace, "pedir_enlace", pedir)
	edicion_e.crear_enlace(ctx)
	# Por defecto en la carpeta del otro panel, con el mismo nombre.
	assert propuesto["destino"] == str(tmp_path / "izq" / "datos")
	assert propuesto["enlace"] == str(tmp_path / "der" / "datos")
	assert os.path.isdir(tmp_path / "der" / "datos")
	assert enlaces.tipo_de(str(tmp_path / "der" / "datos")) == enlaces.UNION
	assert pasivo.refrescos == 1
	assert "creado" in anuncios.historial()[-1].texto


def test_crear_enlace_sin_privilegios_ofrece_alternativa(app_wx, tmp_path, config, monkeypatch):
	(tmp_path / "datos").mkdir()
	local = ProveedorLocal()
	panel = PanelFalso(local, str(tmp_path), local.listar(str(tmp_path)))
	ctx = ContextoFalso(panel, panel, config)
	monkeypatch.setattr(e_enlace, "pedir_enlace", lambda padre, destino, enlace, tipo: (enlaces.SIMBOLICO, enlace, destino))
	monkeypatch.setattr(enlaces, "crear_simbolico", lambda enlace, destino: (_ for _ in ()).throw(enlaces.SinPrivilegios(enlace)))
	preguntas = []

	def elegir(padre, mensaje, titulo, opciones):
		preguntas.append((mensaje, list(opciones)))
		return 0  # «Crear una unión»

	monkeypatch.setattr(dialogos_accesibles, "elegir_opcion", elegir)
	edicion_e.crear_enlace(ctx)
	mensaje, opciones = preguntas[0]
	assert "modo de desarrollador" in mensaje
	assert opciones == ["Crear una &unión", "Crear un &acceso directo", "&Cancelar"]
	assert enlaces.tipo_de(str(tmp_path / "datos (2)")) == enlaces.UNION


def test_crear_enlace_fuera_del_disco(app_wx, config):
	panel = PanelFalso(ProveedorResultados("x", []), "", [])
	ctx = ContextoFalso(panel, panel, config)
	edicion_e.crear_enlace(ctx)
	assert "cursor" in anuncios.historial()[-1].texto
