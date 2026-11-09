# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque RD: órdenes, diálogos y raíz «Red» en la ventana (diseño 2.0, 9 y 18.2).

Todo lo de Windows se simula (``win32wnet``, ``NetShareEnum``, la búsqueda de
equipos): nada conecta, desconecta ni guarda credenciales reales. Los hilos de
red de las órdenes se ejecutan en el acto para poder comprobar el orden.
"""

from __future__ import annotations

import os
import threading
from types import SimpleNamespace

import pytest

wx = pytest.importorskip("wx")

from app.services import red_recientes  # noqa: E402
from app.services.vfs import base, resolver  # noqa: E402
from app.services.vfs import red as vfs_red  # noqa: E402
from app.services.windows import red, red_descubrir, red_info  # noqa: E402
from app.services.windows.red_servidor import ArchivoAbierto, Sesion  # noqa: E402
from app.ui import anuncios  # noqa: E402
from app.ui.accesibilidad import dialogos  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import red_d, red_rd  # noqa: E402
from app.ui.dialogos import d_unidad, f_comun, rd_contrasenas, rd_credenciales, rd_info, rd_sesiones  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402

CONTRASENA = "Otra-secreta-de-prueba-5521"


def _sincrono(funcion, al_terminar, al_fallar, nombre):
	try:
		resultado = funcion()
	except Exception as error:  # noqa: BLE001 - la prueba comprueba el camino de error
		al_fallar(error)
		return None
	al_terminar(resultado)
	return None


@pytest.fixture
def sin_hilos(monkeypatch):
	monkeypatch.setattr(red_d, "_en_hilo", _sincrono)
	monkeypatch.setattr(red_rd, "_en_hilo", _sincrono)


@pytest.fixture
def dichos(monkeypatch):
	lista: list[str] = []
	original = anuncios.anunciar

	def anunciar(texto, nivel=anuncios.NORMAL, completo="", interrumpir=None, sonido=""):
		lista.append(f"{texto}|{sonido}")
		original(texto, nivel, completo, interrumpir, sonido)

	monkeypatch.setattr(anuncios, "anunciar", anunciar)
	return lista


@pytest.fixture(autouse=True)
def red_limpia(monkeypatch):
	monkeypatch.setattr(red, "otros_proveedores", lambda: [])
	monkeypatch.setattr(red, "es_elevado", lambda: False)
	vfs_red.olvidar_equipos()
	resolver.fijar_servicios()
	columnas_antes = vfs_red.proveedor_red().columnas_en_panel
	yield
	vfs_red.proveedor_red().columnas_en_panel = columnas_antes
	vfs_red.olvidar_equipos()
	resolver.fijar_servicios()


class PanelFalso:
	def __init__(self, proveedor=None, ruta: str = "", entradas=(), diario: list | None = None) -> None:
		self.proveedor = proveedor or resolver.proveedor_local()
		self.ruta = ruta
		self._entradas = list(entradas)
		self.cursor_indice = 0
		self.idas: list[tuple] = []
		self.diario = diario if diario is not None else []
		self.vinculadas: list = []
		self.refrescos = 0

	def cursor(self):
		return self._entradas[self.cursor_indice] if self._entradas else None

	def elementos_trabajo(self):
		return [self.cursor()] if self._entradas else []

	def ir_a(self, ruta, proveedor=None, cursor=None, al_terminar=None, historial=True, forzar_aqui=False):
		self.idas.append((ruta, proveedor))
		self.diario.append(("ir_a", ruta))
		if al_terminar is not None:
			al_terminar(True)

	def enfocar(self):
		pass

	def es_local(self):
		return self.proveedor.esquema == "local"

	def ruta_local(self):
		return self.ruta if self.es_local() else None

	def refrescar(self, conservar=True, al_terminar=None):
		self.refrescos += 1

	def vincular_tarea(self, tarea, descripcion):
		self.vinculadas.append((tarea, descripcion))

	def dejar_de_vigilar(self):
		self.diario.append(("dejar_de_vigilar",))


class ConfigFalsa:
	def __init__(self, **valores) -> None:
		self.valores = {"red.exigir_cifrado": False, **valores}

	def obtener(self, clave):
		return self.valores[clave]


def contexto(panel, argumento=None, **config) -> SimpleNamespace:
	ordenes: list = []
	ctx = SimpleNamespace(ventana=None, objetivo=panel, activo=panel, izquierdo=panel, derecho=None, config=ConfigFalsa(**config),
		argumento=argumento, estado=lambda texto: None, ordenes=ordenes)
	ctx.ejecutar_orden = lambda id_orden, lado=None, argumento=None: ordenes.append((id_orden, argumento))
	return ctx


# ── Diálogos: teclado ────────────────────────────────────────────────────────


@pytest.mark.parametrize("sin_letra", [False, True])
def test_dialogo_conectar_teclado_y_datos(app_wx, sin_letra, monkeypatch):
	monkeypatch.setattr(red, "ayuda_formas_de_ruta", lambda: "Formas de ruta.")
	dialogo = d_unidad.DialogoConectarUnidad(None, ["Z:", "Y:"], "", recientes=["\\\\DS220", "\\\\nas"], sin_letra=sin_letra,
		exigir_cifrado=True)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.campo_remoto.GetCount() == 2
		assert dialogo.lista_letra.GetCount() == 4 and dialogo.lista_letra.IsEnabled() == (not sin_letra)
		dialogo.campo_remoto.SetValue("\\\\nas\\fotos")
		dialogo.campo_usuario.SetValue("NAS\\ana")
		dialogo.campo_contrasena.SetValue(CONTRASENA)
		dialogo.casilla_recordar_contrasena.SetValue(True)
		if sin_letra:
			assert dialogo.casilla_credenciales.GetValue() and not dialogo.casilla_recordar.IsEnabled()
			assert dialogo.datos() == ("", "\\\\nas\\fotos", "NAS\\ana", CONTRASENA, False)
		else:
			dialogo.lista_letra.SetSelection(2)
			dialogo.casilla_credenciales.SetValue(True)
			dialogo._actualizar()
			assert dialogo.datos()[0] == d_unidad.AUTOMATICA
		assert dialogo.opciones() == (True, True)
		assert dialogo.aceptar()
	finally:
		dialogo.Destroy()


def test_dialogo_desconectar_con_conexion_sin_letra(app_wx):
	unidades = [red.UnidadRed("Z:", "\\\\nas\\fotos"), red.UnidadRed("", "\\\\nas\\docs")]
	dialogo = d_unidad.DialogoDesconectarUnidad(None, unidades, elegida="\\\\nas\\docs")
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.elegida().remoto == "\\\\nas\\docs" and "sin letra" in dialogo.lista.GetString(1)
		assert dialogo.opciones() == (True, False) and not dialogo.olvidar_credencial()
		assert dialogo.boton_desconectar.GetLabel() == "&Desconectar"
	finally:
		dialogo.Destroy()


@pytest.mark.parametrize("texto", ["", "Usuario o contraseña incorrectos.\n\nEscriba un usuario."])
def test_dialogo_credenciales_teclado_y_sonido(app_wx, texto, monkeypatch):
	from app.services.sonidos import servicio

	sonidos: list[str] = []
	monkeypatch.setattr(servicio, "sonar", lambda evento, variante="", sustituye=False: sonidos.append(evento) or True)
	dialogo = rd_credenciales.DialogoCredenciales(None, "Credenciales de nas", texto, "ana")
	try:
		afirmar_teclado_correcto(dialogo)
		assert sonidos == ["red.credenciales"]
		assert (dialogo.mensaje is not None) == bool(texto)
		dialogo.contrasena.SetValue(CONTRASENA)
		dialogo.recordar.SetValue(True)
		assert dialogo.valores() == ("ana", CONTRASENA, True)
		dialogo.contrasena.SetValue("")
		assert dialogo.valores() == ("ana", "", False)
	finally:
		dialogo.Destroy()


@pytest.mark.parametrize("credenciales", [[], [red.Credencial("nas", "nas\\ana"), red.Credencial("ds220", "")]])
def test_dialogo_contrasenas_teclado_y_olvidar(app_wx, credenciales, monkeypatch):
	borradas: list[str] = []
	monkeypatch.setattr(f_comun, "preguntar", lambda padre, texto, titulo="", peligroso=False: peligroso)
	restantes = list(credenciales[1:])
	dialogo = rd_contrasenas.DialogoContrasenas(None, credenciales, lambda c: borradas.append(c.objetivo), lambda: restantes)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.boton_olvidar.IsEnabled() == bool(credenciales)
		dialogo.olvidar()
		assert borradas == ([credenciales[0].objetivo] if credenciales else [])
		assert dialogo.credenciales == (restantes if credenciales else [])
	finally:
		dialogo.Destroy()


def test_dialogo_informacion_teclado(app_wx):
	info = red_info.InfoRed("Z:\\", letra="Z:", remoto="\\\\nas\\fotos", estado="Conectada", dialecto="3.1.1", cifrada=True)
	dialogo = rd_info.DialogoInfoRed(None, info)
	try:
		afirmar_teclado_correcto(dialogo)
		texto = dialogo.campo.GetValue()
		assert texto.startswith("Z:, \\\\nas\\fotos, conectada, SMB 3.1.1 cifrada") and "Cifrado SMB: sí" in texto
	finally:
		dialogo.Destroy()


def test_dialogo_sesiones_teclado_y_cerrar(app_wx, monkeypatch):
	preguntas: list[bool] = []
	monkeypatch.setattr(f_comun, "preguntar", lambda padre, texto, titulo="", peligroso=False: preguntas.append(peligroso) or True)
	cerradas: list = []
	sesion = Sesion("PC", "ana", 120, 10)
	archivo = ArchivoAbierto(7, "D:\\c\\a.txt", "ana", 1)
	dialogo = rd_sesiones.DialogoSesiones(None, [sesion], [archivo], lambda: ([], []), cerradas.append, cerradas.append)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.lista_sesiones.valores_fila(0)[:2] == ["PC", "ana"]
		dialogo.cerrar_archivo()
		assert cerradas == [archivo] and preguntas == [True]
		assert not dialogo.boton_sesion.IsEnabled() and not dialogo.boton_archivo.IsEnabled()
	finally:
		dialogo.Destroy()


# ── Credenciales desde un hilo ───────────────────────────────────────────────


def test_pedir_credenciales_desde_un_hilo_devuelve_usuario_contrasena_y_recordar(app_wx, monkeypatch):
	from app.ui.decisiones import GestorDecisiones

	def mostrar(dialogo):
		assert dialogo.mensaje is not None and "1272" not in dialogo.GetTitle()
		dialogo.usuario.SetValue("DS220\\ana")
		dialogo.contrasena.SetValue(CONTRASENA)
		dialogo.recordar.SetValue(True)
		return wx.ID_OK

	monkeypatch.setattr(rd_credenciales.DialogoCredenciales, "ShowModal", mostrar)
	gestor = GestorDecisiones(None)
	monkeypatch.setattr(gestor, "_principal_activa", lambda: True)
	resultado: dict = {}
	hilo = threading.Thread(target=lambda: resultado.setdefault("valor", gestor.pedir_credenciales(
		"Credenciales de DS220", red.error_de_codigo(1272, "\\\\DS220").mensaje)), daemon=True)
	hilo.start()
	assert procesar_eventos(lambda: "valor" in resultado, 10)
	hilo.join(5)
	assert resultado["valor"] == ("DS220\\ana", CONTRASENA, True)


def test_pedir_en_la_interfaz(app_wx, monkeypatch):
	monkeypatch.setattr(rd_credenciales.DialogoCredenciales, "ShowModal", lambda self: wx.ID_CANCEL)
	assert rd_credenciales.pedir(None, "Credenciales", "", "ana") is None


# ── Órdenes ──────────────────────────────────────────────────────────────────


def test_ordenes_rd_sin_provisionales():
	from app.ui import ordenes

	rd = [o for o in ordenes.CATALOGO if o.bloque == "RD" or o.id in ("conectar_unidad_red", "desconectar_unidad_red")]
	assert len(rd) >= 10
	for orden in rd:
		modulo, funcion = orden.manejador.split(".", 1)
		objeto = getattr({"red_rd": red_rd, "red_d": red_d}[modulo], funcion)
		assert not getattr(objeto, "provisional", False), orden.id
	assert not getattr(red_rd.instalar, "provisional", False)


def test_instalar_registra_red_en_el_selector(app_wx):
	ventana = SimpleNamespace(config=ConfigFalsa(), servicio=lambda nombre: (_ for _ in ()).throw(KeyError(nombre)))
	red_rd.instalar(ventana)
	try:
		assert any(u.direccion == "red://" for u in resolver.unidades_virtuales())
	finally:
		red_rd._seguimiento.cerrar()


def test_desconectar_2401_pregunta_antes_de_forzar(app_wx, sin_hilos, monkeypatch, dichos):
	diario: list = []
	unidad = red.UnidadRed("Q:", "\\\\nas\\fotos")
	monkeypatch.setattr(red, "unidades_red", lambda con_sin_letra=True: [unidad])

	def desconectar(nombre, forzar=False, olvidar=True, *, olvidar_credencial=False):
		diario.append(("desconectar", nombre, forzar, olvidar, olvidar_credencial))
		if not forzar:
			raise red.error_de_codigo(red.ERROR_OPEN_FILES, nombre)

	def mostrar(dialogo):
		dialogo.casilla_credencial.SetValue(True)
		return wx.ID_OK

	preguntas: list = []
	monkeypatch.setattr(red, "desconectar", desconectar)
	monkeypatch.setattr(d_unidad.DialogoDesconectarUnidad, "ShowModal", mostrar)
	monkeypatch.setattr(dialogos, "confirmar", lambda padre, texto, titulo="", con_cancelar=False, peligroso=False:
		preguntas.append((texto, peligroso)) or wx.ID_YES)
	panel = PanelFalso(ruta="Q:\\fotos\\2024", diario=diario)
	red_d.desconectar_unidad(contexto(panel))
	assert diario == [("dejar_de_vigilar",), ("ir_a", os.path.expanduser("~")),
		("desconectar", "Q:", False, True, True), ("desconectar", "Q:", True, True, True)]
	assert preguntas[0][1] is True and "¿Desconectar a la fuerza? Los programas que usan archivos de Q: pueden perder datos." in preguntas[0][0]
	assert any("Unidad Q: desconectada|red.desconectar" == d for d in dichos)


def test_desconectar_desde_la_raiz_solo_ofrece_la_fila(app_wx, sin_hilos, monkeypatch):
	unidades = [red.UnidadRed("Q:", "\\\\nas\\fotos"), red.UnidadRed("P:", "\\\\nas\\docs")]
	monkeypatch.setattr(red, "unidades_red", lambda con_sin_letra=True: unidades)
	monkeypatch.setattr(red, "unidad", lambda nombre: next(u for u in unidades if u.nombre == nombre.upper()))
	ofrecidas: list = []

	def mostrar(dialogo):
		ofrecidas.extend(dialogo.unidades)
		return wx.ID_CANCEL

	monkeypatch.setattr(d_unidad.DialogoDesconectarUnidad, "ShowModal", mostrar)
	proveedor = vfs_red.ProveedorRed()
	entradas = proveedor.listar("")
	panel = PanelFalso(proveedor, "", entradas)
	panel.cursor_indice = [e.ruta for e in entradas].index("P:\\")
	red_d.desconectar_unidad(contexto(panel))
	assert [u.letra for u in ofrecidas] == ["P:"]


def test_conectar_1219_ofrece_cerrar_las_conexiones(app_wx, sin_hilos, monkeypatch, dichos):
	monkeypatch.setattr(red, "letras_libres", lambda: ["Q:", "P:"])
	errores = [red.ERROR_SESSION_CREDENTIAL_CONFLICT]
	conexiones: list = []

	def conectar(letra, remoto, usuario="", contrasena="", recordar=False, *, persistente=True, exigir_cifrado=False):
		conexiones.append((letra, remoto, usuario, recordar, persistente, exigir_cifrado))
		if errores:
			raise red.error_de_codigo(errores.pop(0), remoto)
		return letra

	def mostrar(dialogo):
		dialogo.campo_remoto.SetValue("\\\\nas\\fotos")
		return wx.ID_OK

	cerradas: list = []
	opciones: list = []
	monkeypatch.setattr(red, "conectar", conectar)
	monkeypatch.setattr(red, "cerrar_conexiones_servidor", lambda servidor: cerradas.append(servidor) or 1)
	monkeypatch.setattr(d_unidad.DialogoConectarUnidad, "ShowModal", mostrar)
	monkeypatch.setattr(dialogos, "elegir_opcion", lambda padre, texto, titulo, ops: opciones.append(ops) or 0)
	panel = PanelFalso(ruta="C:\\")
	red_d.conectar_unidad(contexto(panel, **{"red.exigir_cifrado": True}))
	assert opciones[0][:2] == ["Cerrar las &conexiones a este servidor y reintentar", "Usar otro &nombre del servidor (su IP)"]
	assert cerradas == ["nas"]
	assert conexiones == [("Q:", "\\\\nas\\fotos", "", False, True, True)] * 2
	assert panel.idas[-1] == ("Q:\\", resolver.proveedor_local())
	assert red_recientes.recientes() == ["\\\\nas"]
	assert "Unidad Q: conectada a \\\\nas\\fotos|red.conectar" in dichos


def test_conectar_credenciales_rechazadas_vuelve_a_pedir(app_wx, sin_hilos, monkeypatch):
	monkeypatch.setattr(red, "letras_libres", lambda: ["Q:"])
	errores = [1326]
	monkeypatch.setattr(red, "conectar", lambda letra, remoto, *a, **k: (_ for _ in ()).throw(red.error_de_codigo(errores.pop(0), remoto))
		if errores else letra)
	vistas: list = []

	def mostrar(dialogo):
		vistas.append((dialogo.campo_remoto.GetValue(), dialogo.campo_usuario.GetValue()))
		if len(vistas) == 1:
			dialogo.campo_remoto.SetValue("\\\\nas\\fotos")
			dialogo.casilla_credenciales.SetValue(True)
			dialogo.campo_usuario.SetValue("ana")
			return wx.ID_OK
		return wx.ID_CANCEL

	avisos: list = []
	monkeypatch.setattr(d_unidad.DialogoConectarUnidad, "ShowModal", mostrar)
	monkeypatch.setattr(dialogos, "mostrar_error", lambda padre, mensaje, titulo="": avisos.append(mensaje))
	red_d.conectar_unidad(contexto(PanelFalso(ruta="C:\\")))
	assert vistas == [("", ""), ("\\\\nas\\fotos", "ana")]
	assert "Usuario o contraseña incorrectos" in avisos[0]


def test_conectar_recurso_sin_letra(app_wx, sin_hilos, monkeypatch):
	monkeypatch.setattr(red, "letras_libres", lambda: ["Q:"])
	conexiones: list = []
	monkeypatch.setattr(red, "conectar", lambda letra, remoto, *a, **k: conexiones.append((letra, remoto, k)) or "")

	def mostrar(dialogo):
		assert not dialogo.lista_letra.IsEnabled()
		dialogo.campo_remoto.SetValue("\\\\nas\\docs")
		dialogo.campo_usuario.SetValue("ana")
		return wx.ID_OK

	monkeypatch.setattr(d_unidad.DialogoConectarUnidad, "ShowModal", mostrar)
	panel = PanelFalso(ruta="C:\\")
	red_rd.red_conectar_recurso(contexto(panel))
	assert conexiones[0][:2] == ("", "\\\\nas\\docs") and conexiones[0][2]["persistente"] is False
	assert panel.idas[-1] == ("\\\\nas\\docs", resolver.proveedor_local())


def test_copiar_ruta_unc(app_wx, sin_hilos, monkeypatch, dichos):
	from app.ui import dialogo_texto

	monkeypatch.setattr(red, "_win32wnet", lambda: SimpleNamespace(WNetGetUniversalName=lambda ruta, nivel: "\\\\srv\\rec" + ruta[2:]))
	copiado: list[str] = []
	monkeypatch.setattr(dialogo_texto, "copiar_al_portapapeles", lambda texto: copiado.append(texto) or True)
	panel = PanelFalso(ruta="Z:\\", entradas=[base.Entrada("a", "Z:\\a")])
	red_rd.copiar_ruta_unc(contexto(panel))
	assert copiado == ["\\\\srv\\rec\\a"]
	assert "Ruta UNC copiada: \\\\srv\\rec\\a|portapapeles.texto" in dichos


def test_entrar_en_unidad_desconectada_reconecta(app_wx, sin_hilos, monkeypatch, dichos):
	unidad = red.UnidadRed("Q:", "\\\\ds220\\home", False, True, estado=red.DESCONECTADA)
	monkeypatch.setattr(red, "unidad", lambda nombre: unidad if nombre.upper().startswith("Q:") else None)
	reconexiones: list[str] = []
	monkeypatch.setattr(red, "reconectar", lambda letra, hwnd=0: reconexiones.append(letra))
	panel = PanelFalso(vfs_red.proveedor_red(), "")
	red_rd.red_raiz(contexto(panel, argumento="Q:\\", **{"red.reconectar_al_entrar": False}))
	assert reconexiones == ["Q:"]
	assert panel.idas == [("Q:\\", resolver.proveedor_local())]
	assert any(d.endswith("|red.reconectada") for d in dichos)


def test_entrar_en_unidad_que_pide_credenciales(app_wx, sin_hilos, monkeypatch):
	unidad = red.UnidadRed("Q:", "\\\\ds220\\home", False, True, estado=red.DESCONECTADA)
	monkeypatch.setattr(red, "unidad", lambda nombre: unidad)
	monkeypatch.setattr(red, "reconectar", lambda letra, hwnd=0: (_ for _ in ()).throw(red.error_de_codigo(1326, letra)))
	conexiones: list = []
	monkeypatch.setattr(red, "conectar", lambda *a, **k: conexiones.append((a, k)) or "Q:")

	class Decisor:
		def pedir_credenciales(self, titulo, texto, usuario="", operacion=None):
			assert "Usuario o contraseña incorrectos" in texto
			return "ds220\\ana", CONTRASENA, True

	resolver.fijar_servicios(decisor=Decisor())
	panel = PanelFalso(vfs_red.proveedor_red(), "")
	red_rd.abrir(contexto(panel), "Q:\\")
	assert conexiones == [(("Q:", "\\\\ds220\\home", "ds220\\ana", CONTRASENA, True), {"persistente": False})]
	assert panel.idas == [("Q:\\", resolver.proveedor_local())]


def test_abrir_otras_filas(app_wx, sin_hilos, dichos):
	panel = PanelFalso(vfs_red.proveedor_red(), "")
	ctx = contexto(panel)
	red_rd.abrir(ctx, "red://webdav")
	assert ctx.ordenes == [("conectar_unidad_red", "https://")]
	red_rd.abrir(ctx, "\\\\DS220")
	assert panel.idas[-1] == ("\\\\DS220", vfs_red.proveedor_red())
	red_rd.abrir(ctx, "red://")
	assert panel.idas[-1] == ("", vfs_red.proveedor_red())
	red_rd.abrir(ctx, vfs_red.RUTA_BUSCANDO)
	assert "Buscando equipos" in dichos[-1]


def test_red_info_y_sesiones(app_wx, sin_hilos, monkeypatch, dichos):
	from app.services.windows import red_servidor

	info = red_info.InfoRed("Z:", letra="Z:", remoto="\\\\nas\\fotos", estado="Conectada")
	monkeypatch.setattr(red_info, "informacion", lambda ruta: info)
	monkeypatch.setattr(red, "es_ruta_de_red", lambda ruta: ruta.upper().startswith("Z:"))
	mostradas: list = []
	monkeypatch.setattr(rd_info, "mostrar", lambda padre, dato: mostradas.append(dato))
	red_rd.red_info(contexto(PanelFalso(ruta="Z:\\fotos")))
	assert mostradas == [info]
	red_rd.red_info(contexto(PanelFalso(ruta="C:\\")))
	assert "C:\\ no está en una unidad de red|" in dichos
	mensajes: list = []
	monkeypatch.setattr(red_servidor, "es_elevado", lambda: False)
	monkeypatch.setattr(dialogos, "mostrar_mensaje", lambda padre, texto, titulo="", icono=0: mensajes.append(texto))
	red_rd.red_sesiones(contexto(PanelFalso()))
	assert "administrador" in mensajes[0]


# ── Raíz «Red» en la ventana ─────────────────────────────────────────────────


@pytest.fixture
def ventana_red(app_wx, tmp_path, monkeypatch):
	from app.core.configuracion import Configuracion
	from app.services import sesion

	soltar = threading.Event()
	fin = threading.Event()

	def fuente(emitir, cancelado):
		soltar.wait(10)
		if not cancelado.is_set():
			emitir(red_descubrir.EquipoRed("BETA", "\\\\BETA", "prueba", "192.168.1.9"))
		while not fin.is_set() and not cancelado.is_set():
			cancelado.wait(0.05)

	monkeypatch.setattr(red_descubrir, "fuentes_por_defecto", lambda mdns=True, dominio=True: [("prueba", fuente)])
	monkeypatch.setattr(red, "unidades_red", lambda con_sin_letra=True: [])
	monkeypatch.setattr(red, "recursos", lambda servidor, mostrar_ocultos=False: [
		red.RecursoRed("fotos", f"\\\\{servidor.strip(chr(92))}\\fotos", "disco")])
	red_recientes.anotar_reciente("ZETA")
	red_recientes.anotar_reciente("ALFA")
	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {
			"izquierdo": {"pestanas": [sesion.pestana(ruta=str(tmp_path))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(tmp_path))], "actual": 0},
		},
	})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	config.establecer("red.mostrar_otros_proveedores", False)
	from app.ui.ventana_principal import VentanaPrincipal

	marco = VentanaPrincipal(config)
	marco.mostrar()
	assert procesar_eventos(lambda: marco.izquierdo.panel_actual().ruta == str(tmp_path), 10)
	yield SimpleNamespace(ventana=marco, soltar=soltar, fin=fin)
	soltar.set()
	fin.set()
	vfs_red.cancelar_descubrimiento("fin de la prueba")
	# Los refrescos que quedan terminan aquí, con la carpeta data de la prueba aún puesta.
	busqueda = vfs_red.busqueda_actual()
	if busqueda is not None:
		busqueda.esperar(5)
	procesar_eventos(lambda: False, 0.5)
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 1.0)


def _nombres(panel) -> list[str]:
	return [e.nombre for e in panel.entradas()]


def test_raiz_en_el_panel_busca_sin_mover_el_cursor_y_escape_cancela(ventana_red):
	ventana = ventana_red.ventana
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	ventana.ejecutar_orden("red_raiz")
	assert procesar_eventos(lambda: "Buscando equipos..." in _nombres(panel), 10), _nombres(panel)
	assert panel.mostrar_ruta() == "red://"
	assert {"ALFA", "ZETA"} <= set(_nombres(panel))
	# Columnas propias de «Red» (petición RD 4): el tipo va en su columna, no en el nombre.
	assert panel.lista_archivos.columnas == ["nombre", "red_tipo", "red_remoto", "red_estado"]
	busqueda = vfs_red.busqueda_actual()
	assert busqueda is not None
	assert panel.ir_a_nombre("ZETA")
	indice = panel.lista_archivos.cursor_indice()
	ventana_red.soltar.set()
	assert procesar_eventos(lambda: "BETA" in _nombres(panel), 10), _nombres(panel)
	assert panel.cursor().nombre == "ZETA"
	# Orden por grupos (9.1): los equipos van detrás de los recientes; el cursor no se mueve.
	assert panel.lista_archivos.cursor_indice() == indice
	ventana.ejecutar_orden("cancelar")
	assert busqueda.esperar(5) and busqueda.cancelada
	assert procesar_eventos(lambda: not any(n.startswith("Buscando equipos") for n in _nombres(panel)), 10)
	assert panel.cursor().nombre == "ZETA"


def test_servidor_y_retroceso_vuelve_a_la_raiz_con_el_cursor_en_el(ventana_red):
	ventana = ventana_red.ventana
	ventana.config.establecer("red.descubrir_al_entrar", False)
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	ventana.ejecutar_orden("red_raiz")
	assert procesar_eventos(lambda: "ALFA" in _nombres(panel), 10)
	assert vfs_red.busqueda_actual() is None
	panel.ir_a_nombre("ALFA")
	ventana.ejecutar_orden("abrir")
	assert procesar_eventos(lambda: panel.ruta == "\\\\ALFA" and "fotos" in _nombres(panel), 10), (panel.ruta, _nombres(panel))
	assert panel.mostrar_ruta() == "\\\\ALFA"
	ventana.ejecutar_orden("subir")
	assert procesar_eventos(lambda: panel.ruta == "" and panel.cursor() is not None, 10)
	assert panel.cursor().nombre == "ALFA"
