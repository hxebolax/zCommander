# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Integración del bloque PE (y una petición de PL) en el núcleo (docs/revision/peticiones-pe.md, puntos 2 a 7).

Menús y barra de teclas personalizados, alias en la línea de órdenes, plantillas
en Mayús+F4, Intro sobre un ``.zcteclas``, tecla global de «Ir a la carpeta» y
orden de lectura en la primera carga; letras del buscador de Preferencias.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.core.tareas import GestorTareas  # noqa: E402
from app.services import menus_personalizados, plantillas  # noqa: E402
from app.services.vfs import resolver  # noqa: E402
from app.ui import ordenes  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import dialogos_f, personalizar_pe  # noqa: E402
from app.ui.acciones import visor as acciones_visor  # noqa: E402
from app.ui.barra_teclas import BarraTeclas  # noqa: E402
from app.ui.dialogos import nombre as mod_nombre  # noqa: E402
from app.ui.ventanas import editor as mod_editor  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402


@pytest.fixture(autouse=True)
def sin_personalizador():
	ordenes.fijar_personalizador(None)
	yield
	ordenes.fijar_personalizador(None)


def personalizador(**datos) -> menus_personalizados.Personalizador:
	menus = menus_personalizados.DatosMenus(**datos)
	return menus_personalizados.Personalizador(lambda: menus, lambda: "avanzado", lambda: False, lambda: False, ordenes.POR_ID.get)


def _ids(elementos) -> list[str]:
	"""Ids de una lista de menú, también los de sus submenús."""
	resultado: list[str] = []
	for elemento in elementos:
		if isinstance(elemento, tuple):
			resultado += _ids(elemento[1])
		elif elemento is not None:
			resultado.append(str(elemento))
	return resultado


# ── 2. Menús personalizados, menú del lado y barra de teclas ─────────────────


def test_sin_personalizador_todo_es_de_fabrica():
	assert ordenes.menu_lado() == ordenes.MENU_LADO
	assert ordenes.barra_teclas("") == ordenes.BARRA_TECLAS[""]
	assert ordenes.barra_teclas("Shift") == ordenes.BARRA_TECLAS["Shift"]


def test_personalizador_oculta_ordenes_y_cambia_la_barra_de_teclas():
	ordenes.fijar_personalizador(personalizador(ocultas=["vista_rapida", "ver", "pestana_nueva"], mis_ordenes=["copiar"],
		barra_teclas={"F2": ("crear_carpeta", "Nueva")}))
	assert "vista_rapida" not in _ids(ordenes.menu_lado()) and "pestana_nueva" not in _ids(ordenes.menu_lado())
	assert "vista_breve" in _ids(ordenes.menu_lado())
	todos = [i for _titulo, contenido in ordenes.menus() if contenido != ordenes.LADO for i in _ids(contenido)]
	assert "ver" not in todos and "copiar" in todos
	assert (ordenes.TITULO_MIS_ORDENES, ["copiar"]) in ordenes.menus()
	assert ordenes.barra_teclas("")[1] == ("F2", "crear_carpeta", "Nueva")
	assert ordenes.barra_teclas("")[0] == ordenes.BARRA_TECLAS[""][0]
	assert "ver" not in _ids(ordenes.menu_contextual())


def test_un_personalizador_roto_deja_los_menus_de_fabrica():
	class Roto:
		def menus(self, originales):
			raise RuntimeError("menus.json raro")

		lista = barra_teclas = menus

	ordenes.fijar_personalizador(Roto())
	assert ordenes.menu_lado() == ordenes.MENU_LADO
	assert ordenes.barra_teclas("") == ordenes.BARRA_TECLAS[""]
	assert ordenes.menus()


def test_la_barra_de_teclas_usa_los_huecos_cambiados(app_wx):
	ordenes.fijar_personalizador(personalizador(barra_teclas={"F2": ("crear_carpeta", "Nueva"), "F3": ("", "")}))
	pulsadas: list[str] = []
	ventana = SimpleNamespace(ejecutar_orden=pulsadas.append, activo=SimpleNamespace(enfocar=lambda: None))
	marco = wx.Frame(None)
	try:
		barra = BarraTeclas(marco, ventana)
		barra.actualizar(forzar=True)
		assert barra.botones[1].GetLabel() == "F2 Nueva"
		assert not barra.botones[2].IsEnabled(), "un hueco vacío queda inhabilitado"
		barra._pulsar(1)  # noqa: SLF001 - lo que hace el clic en el botón
		assert pulsadas == ["crear_carpeta"]
	finally:
		marco.Destroy()


# ── Ventana: menú del lado, alias, tecla global y cierre ─────────────────────


@pytest.fixture
def ventana(app_wx, tmp_path, monkeypatch):
	from app.services import sesion

	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {
			"izquierdo": {"pestanas": [sesion.pestana(ruta=str(tmp_path))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(tmp_path))], "actual": 0},
		},
	})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	from app.ui.ventana_principal import VentanaPrincipal

	marco = VentanaPrincipal(config)
	marco.mostrar()
	assert procesar_eventos(lambda: marco.izquierdo.panel_actual().ruta == str(tmp_path), 10)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 1.0)


def test_menu_del_lado_personalizado_y_cierre_suelta_el_personalizador(ventana):
	assert ("vista_rapida", "izquierdo") in ventana._elementos_menu  # noqa: SLF001
	ordenes.fijar_personalizador(personalizador(ocultas=["vista_rapida"]))
	assert procesar_eventos(lambda: ("vista_rapida", "izquierdo") not in ventana._elementos_menu, 5)  # noqa: SLF001
	assert ("vista_breve", "derecho") in ventana._elementos_menu  # noqa: SLF001
	ventana.Close(True)
	procesar_eventos(lambda: False, 1.0)
	assert ordenes._personalizador[0] is None  # noqa: SLF001


def test_alias_de_la_linea_de_ordenes_lleva_su_entorno(ventana, monkeypatch, tmp_path):
	def expandir(_ventana, texto):
		if texto == "error":
			return "", None
		return ("eco %ZC_1%", {"ZC_1": "hola"}) if texto == "e hola" else (texto, None)

	monkeypatch.setattr(personalizar_pe, "expandir_linea", expandir)
	lanzados: list[tuple] = []
	monkeypatch.setattr(ventana, "ejecutar_proceso", lambda orden, carpeta, entorno, refrescar=True: lanzados.append((orden, entorno)))
	for texto in ("e hola", "dir", "error"):
		ventana.linea.ChangeValue(texto)
		ventana.ejecutar_linea()
	assert lanzados == [("eco %ZC_1%", {"ZC_1": "hola"}), ("dir", None)]


def test_tecla_global_de_ir_a_la_carpeta_trae_antes_la_ventana(ventana, monkeypatch):
	diario: list[str] = []
	monkeypatch.setattr(ventana, "traer_al_frente", lambda: diario.append("frente"))
	monkeypatch.setattr(ventana, "ejecutar_orden", lambda id_orden, *a, **k: diario.append(id_orden))
	monkeypatch.setattr(ventana, "_teclas_globales", {901: "ir_a_carpeta", 902: "copiar"})
	ventana._al_tecla_global(SimpleNamespace(GetId=lambda: 901))  # noqa: SLF001
	ventana._al_tecla_global(SimpleNamespace(GetId=lambda: 902))  # noqa: SLF001
	assert diario == ["frente", "ir_a_carpeta", "copiar"]


# ── 7. Orden de lectura en la primera carga ──────────────────────────────────


def test_primera_carga_aplica_el_orden_de_lectura(ventana, monkeypatch):
	panel = ventana.izquierdo.panel_actual()
	panel.lectura = ["tamano", "nombre"]
	aplicadas: list[list[str]] = []
	monkeypatch.setattr(panel, "aplicar_lectura", lambda lectura: aplicadas.append(list(lectura)))
	panel._tras_inicio(True)  # noqa: SLF001
	assert aplicadas == [["tamano", "nombre"]]


# ── 4. Plantillas en Mayús+F4 ────────────────────────────────────────────────


class _Panel:
	def __init__(self, carpeta) -> None:
		self.proveedor = resolver.proveedor_local()
		self.ruta = str(carpeta)
		self.ir_a: list[str] = []

	def cursor(self):
		return None

	def marcadas(self):
		return []

	def es_lista(self):
		return None

	def es_local(self):
		return True

	def ruta_local(self):
		return self.ruta

	def refrescar(self, conservar=True, al_terminar=None):
		if al_terminar:
			al_terminar(True)

	def ir_a_nombre(self, nombre):
		self.ir_a.append(nombre)
		return True


@pytest.fixture
def tareas():
	gestor = GestorTareas(max_hilos=2, nombre="prueba-plantillas")
	yield gestor
	gestor.apagar(2.0)


def _contexto(config, tareas, panel):
	from app.ui.contexto import ContextoOrden

	return ContextoOrden(ventana=None, config=config, tareas=tareas, operaciones=None, activo=panel, pasivo=_Panel(panel.ruta))


def test_mayus_f4_con_plantilla_pone_su_contenido_y_su_extension(app_wx, tmp_path, tareas, monkeypatch):
	serie = tmp_path / "serie"
	serie.mkdir()
	(serie / "Nota.md").write_text("# {{nombre}}\n", encoding="utf-8")
	monkeypatch.setattr(plantillas, "disponibles", lambda: [plantillas.Plantilla("Nota.md", serie / "Nota.md", True)])
	vistas: list = []

	def pedir(*_a, opciones=(), eleccion=None, **_k):
		vistas.append(list(opciones))
		eleccion[:] = [1]
		return "diario"

	monkeypatch.setattr(mod_nombre, "pedir_nombre", pedir)
	abiertos: list[str] = []
	monkeypatch.setattr(mod_editor, "abrir", lambda padre, proveedor, ruta, *a, **k: abiertos.append(ruta))
	carpeta = tmp_path / "trabajo"
	carpeta.mkdir()
	panel = _Panel(carpeta)
	acciones_visor.crear_archivo(_contexto(Configuracion(ruta=tmp_path / "settings.json"), tareas, panel))
	assert procesar_eventos(lambda: abiertos, 5)
	assert vistas == [["Archivo vacío", "Nota"]]
	assert (carpeta / "diario.md").read_text(encoding="utf-8") == "# diario\n"
	assert panel.ir_a == ["diario.md"]


def test_dialogo_nombre_con_plantillas_teclado_y_eleccion(app_wx):
	dialogo = mod_nombre.DialogoNombre(None, "Crear archivo", "&Nombre del archivo nuevo:", "", False,
		opciones=["Archivo vacío", "Nota"], etiqueta_opciones="&Plantilla:", ayuda_opciones="Contenido inicial.")
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.opcion() == 0
		dialogo.lista_opciones.SetSelection(1)
		assert dialogo.opcion() == 1
	finally:
		dialogo.Destroy()
	sin_lista = mod_nombre.DialogoNombre(None, "Renombrar", "&Nombre:", "a.txt")
	try:
		assert sin_lista.lista_opciones is None and sin_lista.opcion() == 0
	finally:
		sin_lista.Destroy()


# ── 5. Intro sobre un .zcteclas ──────────────────────────────────────────────


def test_mapa_teclas_con_argumento_importa(monkeypatch):
	from app.ui.dialogos import f_mapa_teclas

	pedidas: list = []
	monkeypatch.setattr(f_mapa_teclas, "editar_mapa", lambda padre, mapa, importar=None: pedidas.append(importar))
	ctx = SimpleNamespace(ventana=None, mapa_teclas=None, argumento="C:\\teclas\\mias.zcteclas")
	dialogos_f.mapa_teclas(ctx)
	ctx.argumento = None
	dialogos_f.mapa_teclas(ctx)
	assert pedidas == ["C:\\teclas\\mias.zcteclas", None]


# ── PL: letras del buscador de Preferencias ──────────────────────────────────


def test_letras_del_buscador_de_preferencias_reservadas():
	from app.ui.dialogos import pl_preferencias
	from tools import validar_plugin

	assert {"r", "u"} <= pl_preferencias.LETRAS_DIALOGO
	assert validar_plugin.LETRAS_PREFERENCIAS == pl_preferencias.LETRAS_DIALOGO


def test_las_macros_de_la_fuente_del_catalogo_no_se_pierden_con_el_personalizador():
	ordenes.fijar_fuente_macros(lambda: [("Fotos", True, True)])
	try:
		ordenes.fijar_personalizador(personalizador(mis_ordenes=["copiar"]))
		mis = dict(ordenes.menus())[ordenes.TITULO_MIS_ORDENES]
		assert mis == ["copiar", None, "macro:Fotos"]
	finally:
		ordenes.fijar_fuente_macros(None)
