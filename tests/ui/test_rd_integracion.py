# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Integración del bloque RD en el núcleo (docs/revision/peticiones-rd.md, puntos 1 a 7).

Todo lo de Windows se simula: nada conecta, desconecta ni pregunta a un
servidor real. Las carpetas «de red» de la ventana son carpetas de ``tmp_path``.
"""

from __future__ import annotations

import os
import threading
from types import SimpleNamespace

import pytest

wx = pytest.importorskip("wx")

from app.services import errores, red_recientes  # noqa: E402
from app.services.vfs import base, resolver  # noqa: E402
from app.services.vfs import local as vfs_local  # noqa: E402
from app.services.vfs import red as vfs_red  # noqa: E402
from app.services.windows import red, red_info, unidades  # noqa: E402
from app.ui import anuncios, vistas  # noqa: E402
from app.ui.acciones import archivos, consulta, navegacion  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402

MENSAJE_RED = "En Red no se elimina nada. Para quitar una unidad o conexión, use Desconectar unidad de red."


@pytest.fixture(autouse=True)
def red_limpia(monkeypatch):
	monkeypatch.setattr(red, "otros_proveedores", lambda: [])
	monkeypatch.setattr(red, "es_elevado", lambda: False)
	vfs_red.olvidar_equipos()
	resolver.fijar_servicios()
	vistas.olvidar_resumenes_red()
	proveedor = vfs_red.proveedor_red()
	antes = proveedor.columnas_en_panel
	yield
	proveedor.columnas_en_panel = antes
	vfs_red.olvidar_equipos()
	resolver.fijar_servicios()
	vistas.olvidar_resumenes_red()


@pytest.fixture
def dichos(monkeypatch):
	lista: list[str] = []
	original = anuncios.anunciar

	def anunciar(texto, nivel=anuncios.NORMAL, completo="", interrumpir=None, sonido=""):
		lista.append(texto)
		original(texto, nivel, completo, interrumpir, sonido)

	monkeypatch.setattr(anuncios, "anunciar", anunciar)
	return lista


class PanelFalso:
	def __init__(self, proveedor=None, ruta: str = "", entradas=()) -> None:
		self.proveedor = proveedor or resolver.proveedor_local()
		self.ruta = ruta
		self._entradas = list(entradas)
		self.idas: list[tuple] = []
		self.lista_archivos = SimpleNamespace(esta_marcada=lambda indice: False, cursor_indice=lambda: 0)

	def cursor(self):
		return self._entradas[0] if self._entradas else None

	def elementos_trabajo(self):
		return list(self._entradas[:1])

	def es_lista(self):
		return None

	def ir_a(self, ruta, proveedor=None, cursor=None, al_terminar=None, historial=True, forzar_aqui=False):
		self.idas.append((ruta, proveedor, cursor))

	def _tipo(self, entrada):
		return "Carpeta" if entrada.es_carpeta else "Archivo"


class Tareas:
	"""Ejecuta las tareas en el acto (el orden se puede comprobar sin hilos)."""

	def enviar(self, funcion, *args, al_terminar=None, al_fallar=None, nombre="", **_otros):
		try:
			resultado = funcion(None, *args)
		except Exception as error:  # noqa: BLE001 - la prueba comprueba el camino de error
			if al_fallar is not None:
				al_fallar(error)
			return None
		if al_terminar is not None:
			al_terminar(resultado)
		return None


def contexto(panel, **config) -> SimpleNamespace:
	ordenes: list = []
	valores = {"general.usar_papelera": True, **config}
	ctx = SimpleNamespace(ventana=None, activo=panel, objetivo=panel, pasivo=None, argumento=None, param=None,
		config=SimpleNamespace(obtener=lambda clave: valores[clave]), tareas=Tareas(), ordenes=ordenes)
	ctx.ejecutar_orden = lambda id_orden, lado=None, argumento=None: ordenes.append((id_orden, argumento))
	return ctx


def _proveedor_con_filas(*filas: vfs_red.FilaRed) -> vfs_red.ProveedorRed:
	proveedor = vfs_red.ProveedorRed()
	proveedor._recordar(list(filas))  # noqa: SLF001 - filas de prueba sin simular toda la raíz
	return proveedor


FILA_Z = vfs_red.FilaRed("Z:\\", "Z:", vfs_red.UNIDAD, "\\\\DS220\\home", "Conectada")


# ── 1. Intro en una fila de «Red» ────────────────────────────────────────────


def test_intro_en_una_fila_de_red_ejecuta_la_orden_del_proveedor():
	proveedor = _proveedor_con_filas(FILA_Z)
	panel = PanelFalso(proveedor, "", [proveedor.info("Z:\\")])
	ctx = contexto(panel)
	navegacion.abrir(ctx)
	assert ctx.ordenes == [("red_raiz", "Z:\\")]
	assert panel.idas == []


def test_intro_en_una_carpeta_local_no_cambia(tmp_path):
	entrada = base.Entrada("sub", str(tmp_path / "sub"), es_carpeta=True)
	panel = PanelFalso(ruta=str(tmp_path), entradas=[entrada])
	ctx = contexto(panel)
	navegacion.abrir(ctx)
	assert ctx.ordenes == []
	assert panel.idas == [(entrada.ruta, None, None)]


# ── 2. Retroceso desde \\servidor\recurso y \\servidor ───────────────────────


def test_retroceso_desde_un_recurso_va_al_servidor_de_red_con_el_cursor_en_el_recurso():
	panel = PanelFalso(ruta="\\\\DS220\\home\\")
	navegacion.subir(contexto(panel))
	assert panel.idas == [("\\\\DS220", vfs_red.proveedor_red(), "home")]


def test_retroceso_desde_un_servidor_local_va_a_la_raiz_de_red():
	panel = PanelFalso(ruta="\\\\DS220")
	navegacion.subir(contexto(panel))
	assert panel.idas == [("", vfs_red.proveedor_red(), vfs_red.proveedor_red().nombre("\\\\DS220"))]
	assert panel.idas[0][2] == "DS220"


def test_retroceso_dentro_de_un_recurso_y_en_disco_no_cambia(tmp_path):
	panel = PanelFalso(ruta="\\\\DS220\\home\\fotos")
	navegacion.subir(contexto(panel))
	assert panel.idas == [("\\\\DS220\\home", None, None)]
	panel = PanelFalso(ruta=str(tmp_path / "a"))
	navegacion.subir(contexto(panel))
	assert panel.idas == [(str(tmp_path), None, None)]


# ── 3. \\servidor en Ir a la carpeta y en el historial ───────────────────────


@pytest.mark.parametrize("texto", ["\\\\DS220", "\\\\DS220\\", '"\\\\DS220"'])
def test_abrir_ruta_de_un_servidor_va_a_red(texto):
	assert resolver.abrir_ruta(texto) == (vfs_red.proveedor_red(), "\\\\DS220", None)


def test_abrir_ruta_de_un_recurso_sigue_siendo_local(monkeypatch):
	monkeypatch.setattr(resolver._local, "existe", lambda ruta: ruta == "\\\\DS220\\home")  # noqa: SLF001
	monkeypatch.setattr(resolver._local, "info", lambda ruta: base.Entrada("home", ruta, es_carpeta=True))  # noqa: SLF001
	proveedor, ruta, _cursor = resolver.abrir_ruta("\\\\DS220\\home")
	assert proveedor is resolver.proveedor_local() and ruta == "\\\\DS220\\home"


# ── 5. F8 y Supr en «Red» ────────────────────────────────────────────────────


@pytest.mark.parametrize("orden", [archivos.eliminar, archivos.eliminar_definitivo])
def test_f8_y_supr_en_red_dicen_que_se_use_desconectar(orden, dichos):
	proveedor = _proveedor_con_filas(FILA_Z)
	panel = PanelFalso(proveedor, "", [proveedor.info("Z:\\")])
	orden(contexto(panel))
	assert dichos == [MENSAJE_RED]


# ── 6. Resumen de la conexión en Ctrl+Mayús+I y en la vista Información ──────


@pytest.fixture
def conexion_z(monkeypatch):
	"""Z: es de red; C: es un disco fijo. Cuenta las lecturas de la información de la conexión."""
	lecturas: list[str] = []

	def informacion(ruta):
		lecturas.append(ruta)
		return red_info.InfoRed(ruta, letra="Z:", remoto="\\\\DS220\\home", estado="Conectada", usuario="ana")

	monkeypatch.setattr(red_info, "informacion", informacion)
	monkeypatch.setattr(unidades, "tipo_de", lambda raiz: "red" if raiz.upper().startswith("Z:") else "fija")
	monkeypatch.setattr(red, "es_ruta_de_red", lambda ruta: ruta.upper().startswith("Z:"))
	return lecturas


RESUMEN_Z = "Z:, \\\\DS220\\home, conectada, usuario ana"


def test_ctrl_mayus_i_en_una_fila_de_red_dice_columnas_y_resumen(conexion_z, dichos, registro_vacio):
	proveedor = _proveedor_con_filas(FILA_Z)
	panel = PanelFalso(proveedor, "", [proveedor.info("Z:\\")])
	consulta.decir_info(contexto(panel))
	assert dichos[0].startswith("Z:, Unidad de red, \\\\DS220\\home, Conectada")
	assert dichos[-1].endswith(RESUMEN_Z)
	assert conexion_z == ["Z:"]


def test_ctrl_mayus_i_en_un_archivo_de_una_letra_de_red(conexion_z, dichos, registro_vacio):
	panel = PanelFalso(ruta="Z:\\docs", entradas=[base.Entrada("a.txt", "Z:\\docs\\a.txt", tamano=10)])
	consulta.decir_info(contexto(panel))
	assert len(dichos) == 2 and dichos[1] == f"{dichos[0]}, {RESUMEN_Z}"


def test_ctrl_mayus_i_en_disco_local_no_pregunta_a_la_red(conexion_z, dichos, registro_vacio, monkeypatch):
	monkeypatch.setattr(red, "es_ruta_de_red", lambda ruta: pytest.fail("no debe consultar la red"))
	panel = PanelFalso(ruta="C:\\docs", entradas=[base.Entrada("a.txt", "C:\\docs\\a.txt", tamano=10)])
	consulta.decir_info(contexto(panel))
	assert len(dichos) == 1 and conexion_z == []


def test_vista_informacion_anade_la_conexion_y_la_reutiliza(conexion_z, monkeypatch):
	monkeypatch.setattr(vistas, "_lineas_unidad", lambda proveedor, ruta: [])
	monkeypatch.setattr(vistas, "_lineas_complementos", lambda entrada, proveedor: [])
	entrada = base.Entrada("a.txt", "Z:\\docs\\a.txt", tamano=10)
	texto = vistas.componer_informacion(None, resolver.proveedor_local(), entrada, "Z:\\docs")
	assert texto.splitlines()[-1] == f"Conexión de red: {RESUMEN_Z}"
	vistas.componer_informacion(None, resolver.proveedor_local(), entrada, "Z:\\docs")
	assert conexion_z == ["Z:"], "la segunda vez se reutiliza el resumen"
	local = vistas.componer_informacion(None, resolver.proveedor_local(), base.Entrada("b", "C:\\b", tamano=1), "C:\\")
	assert "Conexión de red" not in local


def test_vista_informacion_en_red_no_resume_servidores(conexion_z, monkeypatch):
	monkeypatch.setattr(vistas, "_lineas_unidad", lambda proveedor, ruta: [])
	proveedor = _proveedor_con_filas(vfs_red.FilaRed("\\\\DS220", "DS220", vfs_red.RECIENTE))
	texto = vistas.componer_informacion(None, proveedor, proveedor.info("\\\\DS220"), "")
	assert "Conexión de red" not in texto and conexion_z == []


# ── 7. Letra desconectada desde fuera de «Red» ───────────────────────────────


def _letra_libre() -> str:
	return next(f"{l}:" for l in "QRSTUVWXY" if not os.path.exists(f"{l}:\\"))


def _fallo(codigo: int, ruta: str) -> base.ErrorArchivos:
	causa = OSError(None, "simulado", ruta, codigo)
	error = errores.convertir(causa, ruta)
	error.__cause__ = causa
	return error


@pytest.fixture
def letra_desconectada(monkeypatch):
	letra = _letra_libre()
	unidad = red.UnidadRed(letra, "\\\\ds220\\home", False, True, estado=red.DESCONECTADA)
	monkeypatch.setattr(red, "unidad", lambda nombre: unidad if nombre.upper().startswith(letra) else None)
	reconexiones: list[str] = []
	monkeypatch.setattr(red, "reconectar", lambda l, hwnd=0: reconexiones.append(l))
	return SimpleNamespace(letra=letra, reconexiones=reconexiones)


@pytest.mark.parametrize("codigo", [1201, 3])
def test_listar_una_letra_desconectada_la_reconecta_y_repite(letra_desconectada, monkeypatch, codigo):
	ruta = letra_desconectada.letra + "\\"
	intentos: list[str] = []
	contenido = [base.Entrada("a.txt", ruta + "a.txt")]

	def leer(self, ruta_leida, cancelacion=None):
		intentos.append(ruta_leida)
		if len(intentos) == 1:
			raise _fallo(codigo, ruta_leida)
		return contenido

	monkeypatch.setattr(vfs_local.ProveedorLocal, "_leer_carpeta", leer)
	assert vfs_local.ProveedorLocal().listar(ruta) == contenido
	assert letra_desconectada.reconexiones == [letra_desconectada.letra]
	assert len(intentos) == 2


def test_listar_sin_reconectar_al_entrar_explica_que_no_esta(letra_desconectada, monkeypatch):
	resolver.fijar_servicios(config=SimpleNamespace(obtener=lambda clave: False if clave == "red.reconectar_al_entrar" else None))
	ruta = letra_desconectada.letra + "\\"
	monkeypatch.setattr(vfs_local.ProveedorLocal, "_leer_carpeta", lambda self, r, c=None: (_ for _ in ()).throw(_fallo(1201, r)))
	with pytest.raises(red.ErrorUnidadRed, match="no está disponible"):
		vfs_local.ProveedorLocal().listar(ruta)
	assert letra_desconectada.reconexiones == []


def test_carpeta_que_falta_en_un_disco_no_reconecta_nada(tmp_path, monkeypatch):
	monkeypatch.setattr(red, "unidad", lambda nombre: pytest.fail("no debe buscar unidades de red"))
	with pytest.raises(base.NoEncontrado):
		vfs_local.ProveedorLocal().listar(str(tmp_path / "no-existe"))


# ── 4 (y 1 de punta a punta). Columnas, orden e Intro en el panel de verdad ──


@pytest.fixture
def ventana(app_wx, tmp_path, monkeypatch):
	from app.core.configuracion import Configuracion
	from app.services import sesion

	recurso = tmp_path / "recurso"
	(recurso / "dentro").mkdir(parents=True)
	conexion = red.UnidadRed("", str(recurso), True, False, estado=red.CONECTADA)
	monkeypatch.setattr(red, "unidades_red", lambda con_sin_letra=True: [conexion])
	monkeypatch.setattr(red, "unidad", lambda nombre: None)
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
	config.establecer("red.descubrir_al_entrar", False)
	# Sin vigilar carpetas: «\\DS220\home» no existe y no se debe preguntar a la red por él.
	config.establecer("paneles.vigilar_cambios", False)
	from app.ui.ventana_principal import VentanaPrincipal

	marco = VentanaPrincipal(config)
	marco.mostrar()
	assert procesar_eventos(lambda: marco.izquierdo.panel_actual().ruta == str(tmp_path), 10)
	yield SimpleNamespace(ventana=marco, recurso=str(recurso), tmp=str(tmp_path))
	vfs_red.cancelar_descubrimiento("fin de la prueba")
	procesar_eventos(lambda: False, 0.3)
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 1.0)


def _nombres(panel) -> list[str]:
	return [e.nombre for e in panel.entradas()]


def test_red_en_el_panel_columnas_orden_e_intro(ventana):
	marco = ventana.ventana
	panel = marco.izquierdo.panel_actual()
	columnas_antes = panel.lista_archivos.columnas
	panel.enfocar()
	marco.ejecutar_orden("red_raiz")
	assert procesar_eventos(lambda: panel.mostrar_ruta() == "red://" and "ALFA" in _nombres(panel), 10), _nombres(panel)
	lista = panel.lista_archivos
	assert lista.columnas == ["nombre", "red_tipo", "red_remoto", "red_estado"]
	assert [lista.cabecera(i) for i in range(4)] == ["Nombre", "Tipo", "Remoto", "Estado"]
	# Orden por grupos (la conexión sin letra antes que el servidor reciente), no por nombre.
	assert _nombres(panel) == [ventana.recurso, "ALFA"]
	assert lista.texto_celda(1, 1) == "Servidor reciente"
	assert lista.texto_celda(0, 1) == "Conexión sin letra" and lista.texto_celda(0, 3) == "Conectada"
	assert panel.columnas == columnas_antes, "las columnas de la pestaña no cambian"
	# Intro en la conexión: entra con el proveedor local (con escritura).
	assert panel.ir_a_nombre(ventana.recurso)
	marco.ejecutar_orden("abrir")
	assert procesar_eventos(lambda: panel.ruta == ventana.recurso and panel.proveedor.esquema == "local", 10), panel.mostrar_ruta()
	assert panel.proveedor.capacidades.escribir
	assert "dentro" in _nombres(panel)
	assert lista.columnas == columnas_antes and lista.cabecera(0) == "Nombre"


def test_retroceso_desde_un_recurso_en_el_panel_vuelve_a_red(ventana, monkeypatch):
	monkeypatch.setattr(red, "recursos", lambda servidor, mostrar_ocultos=False: [
		red.RecursoRed("home", f"\\\\{servidor.strip(chr(92))}\\home", "disco")])
	monkeypatch.setattr(vfs_local.ProveedorLocal, "_leer_carpeta", lambda self, ruta, cancelacion=None: [])
	marco = ventana.ventana
	panel = marco.izquierdo.panel_actual()
	panel.ir_a("\\\\DS220\\home", resolver.proveedor_local())
	assert procesar_eventos(lambda: panel.ruta == "\\\\DS220\\home", 10)
	marco.ejecutar_orden("subir")
	assert procesar_eventos(lambda: panel.ruta == "\\\\DS220" and panel.cursor() is not None, 10), panel.mostrar_ruta()
	assert isinstance(panel.proveedor, vfs_red.ProveedorRed) and panel.cursor().nombre == "home"
	marco.ejecutar_orden("subir")
	assert procesar_eventos(lambda: panel.ruta == "" and panel.cursor() is not None, 10)
	assert panel.cursor().nombre == "DS220"
	# Atrás llega otra vez a «\\DS220» (el historial guarda «\\DS220» y ahora se resuelve en «Red»).
	marco.ejecutar_orden("atras")
	assert procesar_eventos(lambda: panel.ruta == "\\\\DS220", 10), panel.mostrar_ruta()


def test_hilos_de_prueba_terminados():
	"""Ninguna prueba de este archivo deja hilos de red vivos."""
	assert not [h for h in threading.enumerate() if h.name.startswith("red-") and h.is_alive()]
