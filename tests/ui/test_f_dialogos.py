# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos y órdenes del bloque F (sección 17.1 del diseño, parte F).

Los diálogos se construyen SIN mostrarlos y se destruyen al terminar. Los
avisos y preguntas pasan por ``app.ui.dialogos.f_comun`` y se sustituyen aquí:
ningún ``ShowModal`` real llega a la pantalla (el ``conftest`` lo prohíbe).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.conftest import procesar_eventos

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.services import favoritos, menu_usuario, perfiles  # noqa: E402
from app.services.asociaciones import Regla  # noqa: E402
from app.services.menu_usuario import EntradaMenu  # noqa: E402
from app.services.teclas import MapaTeclas  # noqa: E402
from app.ui import anuncios, ordenes  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import dialogos_f  # noqa: E402
from app.ui.dialogos import (  # noqa: E402
	f_arbol,
	f_asistente,
	f_asociaciones,
	f_columnas,
	f_comun,
	f_favoritos,
	f_historial,
	f_mapa_teclas,
	f_menu_usuario,
	f_paleta,
	f_perfil,
	f_preferencias,
	f_unidades,
)


@pytest.fixture
def config(tmp_path):
	return Configuracion(ruta=tmp_path / "settings.json")


@pytest.fixture
def respuestas(monkeypatch):
	"""Sustituye avisos y preguntas; ``preguntar`` responde lo que diga ``respuestas.si``."""
	estado = SimpleNamespace(avisos=[], preguntas=[], elecciones=[], pedidos=[], si=True, eleccion=0, texto="")

	def preguntar(padre, texto, titulo="", peligroso=False):
		estado.preguntas.append(texto)
		return estado.si

	def elegir(padre, texto, titulo, opciones):
		estado.elecciones.append(texto)
		return estado.eleccion

	def pedir(padre, etiqueta, titulo, valor="", **opciones):
		estado.pedidos.append((etiqueta, valor))
		return estado.texto if estado.texto is not None else None

	monkeypatch.setattr(f_comun, "avisar", lambda padre, texto, titulo="": estado.avisos.append(texto))
	monkeypatch.setattr(f_comun, "preguntar", preguntar)
	monkeypatch.setattr(f_comun, "elegir", elegir)
	monkeypatch.setattr(f_comun, "pedir", pedir)
	return estado


def _mapa(config=None) -> MapaTeclas:
	personalizadas = config.obtener("teclado.personalizadas") if config is not None else {}
	return MapaTeclas(ordenes.teclas_por_defecto(), ordenes.ambitos(), personalizadas, ordenes.fijas())


def _textos_anunciados() -> list[str]:
	return [a.texto for a in anuncios.historial()]


@pytest.fixture
def destruir():
	"""Destruye al terminar los diálogos que se le pasan."""
	creados = []
	yield creados.append
	for dialogo in creados:
		if dialogo:
			dialogo.Destroy()
	_vaciar()


def _vaciar() -> None:
	"""Procesa la destrucción diferida de las ventanas (wx la hace en el evento «idle»)."""
	procesar_eventos(lambda: False, 0.05)


# ── Cada diálogo pasa revisar_teclado ───────────────────────────────────────

def _todos_los_dialogos(config, tmp_path):
	from app.core.tareas import GestorTareas
	from app.services.vfs import resolver

	tareas = GestorTareas(max_hilos=1, nombre="pruebas-f")
	entradas = [EntradaMenu("Comprimir", "A", ["7z a x.7z %M"]), EntradaMenu("Git", "G", submenu=[EntradaMenu("Estado", "E", ["git status"])])]
	destinos = f_unidades.destinos_iniciales(["C:"], lambda _r: "fija", [("Fotos", "D:\\Fotos")], [("Documentos", "C:\\Docs")])
	return tareas, [
		f_preferencias.DialogoPreferenciasZ(None, config),
		f_menu_usuario.DialogoMenuUsuario(None, entradas, "Aviso de prueba"),
		f_menu_usuario.DialogoEditarMenu(None, entradas),
		f_menu_usuario.DialogoEntradaMenu(None, entradas[0], False, set()),
		f_asociaciones.DialogoAsociaciones(None, [Regla("*.txt", editar="notepad.exe %P")]),
		f_asociaciones.DialogoRegla(None, Regla("*.txt"), True),
		f_favoritos.DialogoFavoritos(None, [favoritos.Favorito("Fotos", "D:\\Fotos")], "C:\\"),
		f_historial.DialogoHistorial(None, "Historial de carpetas", "Carpetas &visitadas:", ["C:\\", "D:\\"]),
		f_historial.DialogoHistorial(None, "Historial de órdenes", "Ó&rdenes ejecutadas:", ["dir"], ordenes=True),
		f_arbol.DialogoArbol(None, resolver.proveedor_local(), str(tmp_path), str(tmp_path), tareas),
		f_unidades.DialogoUnidades(None, "Unidad del lado izquierdo", destinos, "C:\\"),
		f_columnas.DialogoColumnas(None, "Columnas", ["nombre", "tamano"], {}, ["nombre", "extension"]),
		f_perfil.DialogoPerfil(None, config),
		f_mapa_teclas.DialogoMapaTeclas(None, _mapa()),
		f_mapa_teclas.DialogoCapturaTecla(None, "ver"),
		f_paleta.DialogoPaleta(None, _mapa()),
		f_asistente.DialogoAsistente(None, config),
	]


def test_cada_dialogo_pasa_revisar_teclado(app_wx, config, tmp_path):
	tareas, dialogos = _todos_los_dialogos(config, tmp_path)
	try:
		for dialogo in dialogos:
			try:
				afirmar_teclado_correcto(dialogo)
			except AssertionError as error:
				raise AssertionError(f"{dialogo.GetTitle()}: {error}") from None
	finally:
		for dialogo in dialogos:
			dialogo.Destroy()
		tareas.apagar(2.0)
		_vaciar()


def test_cada_dialogo_tiene_escape_y_ayuda_en_los_controles(app_wx, config, tmp_path):
	tareas, dialogos = _todos_los_dialogos(config, tmp_path)
	try:
		for dialogo in dialogos:
			assert dialogo.GetEscapeId() in (wx.ID_CANCEL, wx.ID_CLOSE), dialogo.GetTitle()
	finally:
		for dialogo in dialogos:
			dialogo.Destroy()
		tareas.apagar(2.0)
		_vaciar()


# ── Paleta de órdenes ───────────────────────────────────────────────────────

def test_paleta_filtra_copiar_y_ejecuta_la_orden(app_wx, destruir):
	dialogo = f_paleta.DialogoPaleta(None, _mapa())
	destruir(dialogo)
	dialogo.campo.ChangeValue("copiar")
	dialogo.filtrar()
	assert dialogo.visibles, "hay órdenes con «copiar»"
	assert dialogo.visibles[0].id == "copiar"
	assert all("copiar" in f_comun.normalizar_busqueda(f_paleta.etiqueta(o) + " " + o.ayuda) for o in dialogo.visibles)
	assert "(F5)" in dialogo.lista.GetString(0)
	assert dialogo.ejecutar()
	assert dialogo.elegida == "copiar"
	assert dialogo.GetReturnCode() == wx.ID_OK


def test_paleta_sin_tildes_y_sin_ordenes_de_la_linea():
	assert f_paleta.filtrar_ordenes("ARBOL")[0].id in ("arbol_carpetas", "vista_arbol")
	ids = {o.id for o in f_paleta.filtrar_ordenes("")}
	assert "ejecutar_linea" not in ids and "paleta_ordenes" not in ids and "copiar" in ids
	assert f_paleta.filtrar_ordenes("xyzzy nada") == []


def test_orden_paleta_ejecuta_y_anuncia_el_atajo(app_wx, monkeypatch):
	def mostrar_simulado(self):
		self.campo.ChangeValue("copiar")
		self.filtrar()
		self.ejecutar()
		return wx.ID_OK

	monkeypatch.setattr(f_paleta.DialogoPaleta, "ShowModal", mostrar_simulado)
	ejecutadas = []
	ctx = SimpleNamespace(ventana=None, mapa_teclas=_mapa(), lado_objetivo=None,
		ejecutar_orden=lambda id_orden, lado=None: ejecutadas.append((id_orden, lado)))
	dialogos_f.paleta_ordenes(ctx)
	assert ejecutadas == [("copiar", None)]
	assert "Atajo: F5" in _textos_anunciados()


# ── Mapa de teclas ──────────────────────────────────────────────────────────

def test_mapa_rechaza_ctrl_r_para_otra_orden_avisando_del_choque(app_wx, respuestas, destruir):
	dialogo = f_mapa_teclas.DialogoMapaTeclas(None, _mapa())
	destruir(dialogo)
	respuestas.si = False
	assert dialogo.asignar("ver", "Ctrl+R") is False
	assert respuestas.preguntas and "Ctrl+R ya es Volver a leer" in respuestas.preguntas[0]
	assert dialogo.asignadas["ver"] == ("F3",)
	assert "Ctrl+R" in dialogo.asignadas["volver_a_leer"]
	assert dialogo.personalizadas() == {}
	# Si se acepta quitársela, pasa a la otra orden.
	respuestas.si = True
	assert dialogo.asignar("ver", "ctrl+r") is True
	assert dialogo.asignadas["ver"] == ("Ctrl+R",)
	assert dialogo.asignadas["volver_a_leer"] == ()
	assert dialogo.personalizadas() == {"ver": ["Ctrl+R"], "volver_a_leer": []}
	assert dialogo.restablecer("volver_a_leer") is True
	assert dialogo.asignadas["volver_a_leer"] == ("Ctrl+R",) and dialogo.asignadas["ver"] == ()


def test_mapa_no_permite_reservadas_fijas_menus_ni_letras(app_wx, respuestas, destruir):
	dialogo = f_mapa_teclas.DialogoMapaTeclas(None, _mapa())
	destruir(dialogo)
	for tecla in ("Alt+F4", "Tab", "Ctrl+H", "Alt+A", "Q", "Shift+Q"):
		assert dialogo.asignar("ver", tecla) is False, tecla
	assert len(respuestas.avisos) == 6 and not respuestas.preguntas
	assert "reservada" in respuestas.avisos[0]
	assert "fija" in respuestas.avisos[1] and "Cambiar de panel" in respuestas.avisos[1]
	assert "menú Archivos" in respuestas.avisos[3]
	assert dialogo.quitar("cambiar_panel") is False
	# Misma tecla en ámbitos que no se solapan: Intro abre en el panel y ejecuta en la línea.
	assert f_mapa_teclas.comprobar(dialogo.asignadas, dialogo.ambitos, dialogo.fijas, "ejecutar_linea", "Return").choques == ()
	assert dialogo.asignar("ver", "Ctrl+Alt+F3", reemplazar=False) is True
	assert dialogo.asignadas["ver"] == ("F3", "Ctrl+Alt+F3")


def test_mapa_buscar_y_guardar_desde_la_orden(app_wx, config, respuestas, monkeypatch, destruir):
	dialogo = f_mapa_teclas.DialogoMapaTeclas(None, _mapa())
	destruir(dialogo)
	dialogo.campo.ChangeValue("f5")
	dialogo.filtrar()
	assert "copiar" in dialogo.visibles
	monkeypatch.setattr(f_mapa_teclas, "editar_mapa", lambda padre, mapa: {"ver": ["Ctrl+Alt+V"]})
	ctx = SimpleNamespace(ventana=None, config=config, mapa_teclas=_mapa(config))
	dialogos_f.mapa_teclas(ctx)
	assert config.obtener("teclado.personalizadas") == {"ver": ["Ctrl+Alt+V"]}
	assert _mapa(config).teclas_de("ver") == ("Ctrl+Alt+V",)


def test_captura_de_tecla(app_wx, respuestas, destruir):
	dialogo = f_mapa_teclas.DialogoCapturaTecla(None, "ver")
	destruir(dialogo)
	assert dialogo.aceptar() is False and respuestas.avisos
	dialogo.poner("ctrl+mayús+f5")
	assert dialogo.tecla == "Ctrl+Shift+F5"
	assert dialogo.campo.GetValue() == "Ctrl+Mayús+F5"
	assert dialogo.aceptar() is True


# ── Perfil ──────────────────────────────────────────────────────────────────

def test_aplicar_perfil_avanzado_desde_fabrica_devuelve_7(config):
	assert perfiles.perfil_actual(config) == perfiles.INTERMEDIO
	assert perfiles.aplicar_perfil(config, "avanzado") == 7
	assert perfiles.perfil_actual(config) == perfiles.AVANZADO


def test_dialogo_perfil_confirma_y_aplica(app_wx, config, respuestas, destruir):
	dialogo = f_perfil.DialogoPerfil(None, config)
	destruir(dialogo)
	assert "Intermedio" in dialogo.texto_actual.GetLabel()
	dialogo.lista.SetSelection(f_perfil.ORDEN.index(perfiles.AVANZADO))
	dialogo._describir()  # noqa: SLF001 - lo que hace EVT_LISTBOX
	assert "cambiarán 7 preferencias" in dialogo.descripcion.GetValue()
	respuestas.si = False
	assert dialogo.aplicar() is None and perfiles.perfil_actual(config) == perfiles.INTERMEDIO
	respuestas.si = True
	assert dialogo.aplicar() == 7
	assert "7 preferencias" in respuestas.preguntas[-1]
	assert "Avanzado" in dialogo.texto_actual.GetLabel()


# ── Menú de usuario ─────────────────────────────────────────────────────────

def _entrada(nombre, ruta):
	return SimpleNamespace(nombre=nombre, ruta=ruta, es_superior=False)


def _panel(carpeta, lado="izquierdo", cursor=None, marcadas=()):
	return SimpleNamespace(
		lado=lado, ruta=str(carpeta), es_local=lambda: True, ruta_local=lambda: str(carpeta),
		cursor=lambda: cursor, elementos_trabajo=lambda: list(marcadas) or ([cursor] if cursor else []),
		mostrar_ruta=lambda: str(carpeta), es_lista=lambda: None,
	)


@pytest.fixture
def ctx_menu(config, tmp_path):
	carpeta = tmp_path / "descargas"
	carpeta.mkdir()
	(carpeta / menu_usuario.NOMBRE_LOCAL).write_text(json.dumps(
		{"version": 1, "entradas": [{"etiqueta": "Peligro", "tecla": "P", "ordenes": ["del /q *.*"]}]}), encoding="utf-8")
	ejecutadas = []
	linea = SimpleNamespace(ejecutar=lambda expansion, consola=False, refrescar=True: ejecutadas.append((expansion, consola, refrescar)))
	ctx = SimpleNamespace(
		ventana=None, config=config,
		activo=_panel(carpeta, cursor=_entrada("a&calc.txt", str(carpeta / "a&calc.txt"))),
		pasivo=_panel(tmp_path, "derecho"),
		servicio=lambda nombre: linea,
	)
	ctx.ejecutadas = ejecutadas
	return ctx


def test_menu_local_no_se_usa_sin_confianza(app_wx, ctx_menu, respuestas, monkeypatch):
	menu_usuario.guardar([EntradaMenu("Global", "G", ["echo %N"])])
	vistas = []
	monkeypatch.setattr(f_menu_usuario, "elegir_entrada", lambda padre, entradas, aviso="": vistas.append((entradas, aviso)))
	respuestas.eleccion = 1  # «No usarlo»
	dialogos_f.menu_usuario(ctx_menu)
	assert respuestas.elecciones and "del /q *.*" in respuestas.elecciones[0], "se enseñan las órdenes antes de confiar"
	entradas, aviso = vistas[0]
	assert [e.etiqueta for e in entradas] == ["Global"]
	assert "no se usa" in aviso
	assert ctx_menu.config.obtener(menu_usuario.CLAVE_CONFIANZA) == {}
	# Confiar: el menú local aparece primero y ya no se pregunta la próxima vez.
	respuestas.eleccion = 0
	dialogos_f.menu_usuario(ctx_menu)
	assert [e.etiqueta for e in vistas[1][0]] == ["Peligro", "Global"]
	respuestas.elecciones.clear()
	dialogos_f.menu_usuario(ctx_menu)
	assert not respuestas.elecciones
	assert [e.etiqueta for e in vistas[2][0]] == ["Peligro", "Global"]


def test_ejecutar_entrada_sin_inyeccion(app_wx, ctx_menu, monkeypatch):
	monkeypatch.setattr(f_menu_usuario, "elegir_entrada", lambda padre, entradas, aviso="": entradas[0])
	menu_usuario.guardar([EntradaMenu("Ver nombre", "V", ["type %N", "echo %O"], consola=True, refrescar=False)])
	monkeypatch.setattr(menu_usuario, "leer_local", lambda carpeta: None)
	dialogos_f.menu_usuario(ctx_menu)
	expansion, consola, refrescar = ctx_menu.ejecutadas[0]
	assert consola is True and refrescar is False
	assert "&calc" not in expansion.orden, "el nombre va en una variable de entorno, no en la orden"
	assert expansion.orden == 'type "%ZC_1%" & echo "%ZC_2%"'
	assert expansion.entorno["ZC_1"] == "a&calc.txt"


def test_dialogo_menu_usuario_tecla_y_submenu(app_wx, destruir):
	entradas = [EntradaMenu("Comprimir", "A", ["7z"]), EntradaMenu("Git", "G", submenu=[EntradaMenu("Estado", "E", ["git status"])])]
	dialogo = f_menu_usuario.DialogoMenuUsuario(None, entradas)
	destruir(dialogo)
	assert dialogo.lista.GetString(0) == "A: Comprimir"
	assert dialogo.pulsar_tecla("g") is True and dialogo.elegida is None
	assert dialogo.lista.GetString(0) == "E: Estado"
	assert dialogo.volver() is True and dialogo.lista.GetSelection() == 1
	assert dialogo.pulsar_tecla("x") is False
	assert dialogo.pulsar_tecla("a") is True and dialogo.elegida.etiqueta == "Comprimir"


def test_editar_menu_y_entrada(app_wx, respuestas, monkeypatch, destruir):
	dialogo = f_menu_usuario.DialogoEditarMenu(None, [EntradaMenu("Uno", "U", ["echo 1"])])
	destruir(dialogo)
	monkeypatch.setattr(f_menu_usuario, "editar_entrada", lambda padre, entrada, nueva, teclas: EntradaMenu("Dos", "D", ["echo 2"]))
	dialogo.nueva()
	assert [e.etiqueta for e in dialogo.entradas] == ["Uno", "Dos"]
	dialogo.mover(-1)
	assert [e.etiqueta for e in dialogo.entradas] == ["Dos", "Uno"]
	dialogo.abrir_submenu()
	dialogo.nueva()
	dialogo.volver()
	assert dialogo.entradas[0].es_submenu and dialogo.entradas[0].submenu[0].etiqueta == "Dos"
	dialogo.lista.SetSelection(1)
	dialogo.eliminar()
	assert [e.etiqueta for e in dialogo.entradas] == ["Dos"]
	entrada = f_menu_usuario.DialogoEntradaMenu(None, EntradaMenu(""), True, {"D"})
	destruir(entrada)
	entrada.campo_etiqueta.SetValue("Tres")
	entrada.campo_tecla.SetValue("d")
	assert entrada.aceptar() is False and "ya la usa" in respuestas.avisos[-1]
	entrada.campo_tecla.SetValue("t")
	entrada.campo_ordenes.SetValue("echo 3\n\n  echo 4  ")
	assert entrada.aceptar() is True
	assert (entrada.entrada.etiqueta, entrada.entrada.tecla, entrada.entrada.ordenes) == ("Tres", "T", ["echo 3", "echo 4"])


# ── Asociaciones, favoritos, historiales ────────────────────────────────────

def test_asociaciones_editar_ordenar_y_guardar(app_wx, respuestas, monkeypatch, destruir):
	from app.services import asociaciones

	dialogo = f_asociaciones.DialogoAsociaciones(None, [Regla("*.txt", editar="notepad.exe %P"), Regla("*.md", ver="x %P")])
	destruir(dialogo)
	assert dialogo.lista.texto_celda(0, 1) == "(por defecto)"
	dialogo.lista.enfocar_fila(1, anunciar=False)
	dialogo.mover(-1)
	assert [r.patron for r in dialogo.reglas] == ["*.md", "*.txt"]
	regla = f_asociaciones.DialogoRegla(None, Regla(""), True)
	destruir(regla)
	assert regla.aceptar() is False
	regla.campo_patron.SetValue("*.log")
	assert regla.aceptar() is False and "al menos una orden" in respuestas.avisos[-1]
	regla.campo_ver.SetValue("notepad.exe %P")
	assert regla.aceptar() is True and regla.regla == Regla("*.log", "", "notepad.exe %P", "")
	monkeypatch.setattr(f_asociaciones, "editar_asociaciones", lambda padre, reglas: [Regla("*.log", ver="v %P")])
	dialogos_f.editar_asociaciones(SimpleNamespace(ventana=None))
	assert asociaciones.orden_para("hoy.log", "ver") == "v %P"


def test_favoritos_dialogo_y_ordenes(app_wx, respuestas, monkeypatch, tmp_path, destruir):
	respuestas.texto = "Trabajo"
	idos = []
	panel = _panel(tmp_path)
	panel.ir_historial = idos.append
	ctx = SimpleNamespace(ventana=None, activo=panel)
	dialogos_f.agregar_favorito(ctx)
	assert [(f.nombre, f.ruta) for f in favoritos.cargar()] == [("Trabajo", str(tmp_path))]
	assert "Añadido a favoritos: Trabajo" in _textos_anunciados()
	dialogo = f_favoritos.DialogoFavoritos(None, favoritos.cargar(), "D:\\Otra")
	destruir(dialogo)
	respuestas.texto = "Otra"
	dialogo.anadir_actual()
	assert [f.nombre for f in favoritos.cargar()] == ["Trabajo", "Otra"], "se guarda al momento"
	dialogo.mover(-1)
	assert [f.nombre for f in favoritos.cargar()] == ["Otra", "Trabajo"]
	dialogo.eliminar()
	assert [f.nombre for f in favoritos.cargar()] == ["Trabajo"]
	dialogo.ir()
	assert dialogo.elegido.nombre == "Trabajo"
	monkeypatch.setattr(f_favoritos, "elegir_favorito", lambda padre, ruta: favoritos.Favorito("Trabajo", "C:\\Trabajo"))
	dialogos_f.favoritos(ctx)
	assert idos == ["C:\\Trabajo"]


def test_historiales_filtran_y_eligen(app_wx, monkeypatch, destruir):
	dialogo = f_historial.DialogoHistorial(None, "Historial de órdenes", "Ó&rdenes:", ["dir /s", "echo Árbol", "copy a b"], ordenes=True)
	destruir(dialogo)
	dialogo.campo.ChangeValue("ARBOL")
	dialogo.aplicar_filtro()
	assert dialogo.visibles == ["echo Árbol"]
	dialogo.elegir(f_historial.EJECUTAR)
	assert (dialogo.elegido, dialogo.accion) == ("echo Árbol", "ejecutar")
	puestas, ejecutadas = [], []
	linea = SimpleNamespace(historial=lambda: ["dir"], poner=puestas.append)
	ctx = SimpleNamespace(ventana=None, servicio=lambda _n: linea, ejecutar_orden=ejecutadas.append)
	monkeypatch.setattr(f_historial, "elegir_orden", lambda padre, ordenes_: ("dir", f_historial.EJECUTAR))
	dialogos_f.historial_ordenes(ctx)
	assert puestas == ["dir"] and ejecutadas == ["ejecutar_linea"]


# ── Columnas, unidades, preferencias, asistente, fábrica ────────────────────

def test_columnas_nombre_obligatorio_orden_y_ancho(app_wx, destruir):
	dialogo = f_columnas.DialogoColumnas(None, "Columnas", ["nombre", "tamano"], {"nombre": 300}, ["nombre", "extension"])
	destruir(dialogo)
	assert dialogo.elegidas() == ["nombre", "tamano"]
	assert dialogo.campo_ancho.GetValue() == 300
	dialogo.lista.SetSelection(1)  # Tamaño
	dialogo.mover(-1)
	assert dialogo.elegidas() == ["tamano", "nombre"]
	dialogo.lista.Check(1, False)  # quitar «nombre»: aceptar lo vuelve a poner
	dialogo.restablecer()
	assert dialogo.elegidas() == ["nombre", "extension"]
	assert dialogo.aceptar() and dialogo.columnas == ["nombre", "extension"]


def test_orden_columnas_aplica_al_panel(app_wx, config, monkeypatch):
	aplicadas = []
	panel = SimpleNamespace(lado="derecho", columnas=["nombre"], aplicar_columnas=lambda c, a: aplicadas.append((c, a)))
	monkeypatch.setattr(f_columnas, "elegir_columnas", lambda *a: (["nombre", "atributos"], {"nombre": 250}))
	dialogos_f.columnas(SimpleNamespace(ventana=None, config=config, objetivo=panel))
	assert aplicadas == [(["nombre", "atributos"], {"nombre": 250})]
	monkeypatch.setattr(f_columnas, "elegir_columnas", lambda *a: (["nombre", "tipo"], {"tipo": 90}))
	dialogos_f.columnas_defecto(SimpleNamespace(ventana=None, config=config))
	assert config.obtener("paneles.columnas") == ["nombre", "tipo"] and config.obtener("paneles.anchos")["tipo"] == 90


def test_unidades_letra_y_detalles(app_wx, destruir):
	from app.services.windows.unidades import Unidad

	destinos = f_unidades.destinos_iniciales(["C:", "D:"], lambda _r: "fija", [], [("Documentos", "C:\\Docs")])
	dialogo = f_unidades.DialogoUnidades(None, "Unidad", destinos, "D:\\Fotos")
	destruir(dialogo)
	assert dialogo.lista.GetSelection() == 1
	assert dialogo.lista.GetString(0) == "C:, Disco local"
	dialogo.poner_detalles([Unidad("C:", "C:\\", "fija", "Sistema", "NTFS", 1, 1024, 2048)])
	assert "NTFS" in dialogo.lista.GetString(0)
	assert dialogo.ir_a_letra("x") is False
	assert dialogo.ir_a_letra("c") is True and dialogo.elegido.ruta == "C:\\"


def test_preferencias_paginas_letras_y_fabrica_por_pagina(app_wx, config, respuestas, monkeypatch, destruir):
	from app.core import descripciones_config
	from app.ui import dialogo_preferencias as plantilla

	monkeypatch.setattr(plantilla, "mostrar_aviso", lambda padre, texto, titulo: respuestas.avisos.append(texto))
	dialogo = f_preferencias.DialogoPreferenciasZ(None, config)
	destruir(dialogo)
	titulos = [dialogo.libro.GetPageText(i) for i in range(dialogo.libro.GetPageCount())]
	# 2.0 (10.18, bloque PE): árbol de páginas con «Confirmaciones» tras «Personalización» y, bajo
	# «Complementos», una página por complemento con configuración.
	esperados = [t for _id, t in descripciones_config.PAGINAS]
	esperados.insert(esperados.index("Personalización") + 1, "Confirmaciones")
	assert titulos[:len(esperados)] == esperados
	from app.ui import paginas_propias

	propias = {i for i, t in descripciones_config.PAGINAS if t in paginas_propias.PAGINAS_PROPIAS}
	# Todas las claves con página declarativa aparecen, con su etiqueta justo antes (salvo las casillas).
	for clave, (_etiqueta, ayuda, pagina) in descripciones_config.DESCRIPCIONES.items():
		if pagina is None or pagina in propias:
			continue
		control = dialogo.control_de(clave)
		assert control.GetHelpText() == ayuda, clave
		if not isinstance(control, wx.CheckBox):
			hermanos = list(control.GetParent().GetChildren())
			assert isinstance(hermanos[hermanos.index(control) - 1], wx.StaticText), clave
	assert dialogo.control_de("vista.tema").GetString(1) == "Norton clásico"
	# Aplicar guarda y avisa; la página «Vista» vuelve a fábrica sin tocar las demás.
	dialogo.control_de("vista.tamano_fuente").SetValue(20)
	dialogo.control_de("general.confirmar_salida").SetValue(False)
	assert dialogo.aplicar()
	assert config.obtener("vista.tamano_fuente") == 20 and config.obtener("general.confirmar_salida") is False
	indice_vista = titulos.index("Vista")
	dialogo.libro.SetSelection(indice_vista)
	dialogo._al_restablecer(None)  # noqa: SLF001 - lo que hace el botón
	assert respuestas.preguntas
	assert dialogo.control_de("vista.tamano_fuente").GetValue() == 10
	assert dialogo.control_de("general.confirmar_salida").GetValue() is False, "otra página: no se toca"
	assert config.obtener("vista.tamano_fuente") == 20, "no se guarda hasta Aplicar"


def test_repartir_letras_sin_repetir():
	etiquetas = ["&Disposición", "&Disco", "&Datos", "&Día"]
	resultado = f_comun.repartir_letras(etiquetas, {"a", "c"})
	letras = [f_comun.letras_de([e]) for e in resultado]
	assert resultado[3] == "&Día", "«Día» solo puede usar la D: las demás ceden la suya"
	assert all(len(letra) == 1 for letra in letras) and len(set().union(*letras)) == 4
	assert not set().union(*letras) & {"a", "c"}
	assert f_comun.repartir_letras(["&Datos", "&Disco"]) == ["&Datos", "D&isco"], "la primera conserva su letra"


def test_asistente_aplica_todo_al_terminar(app_wx, config, monkeypatch, destruir):
	dialogo = f_asistente.DialogoAsistente(None, config)
	destruir(dialogo)
	assert not dialogo.boton_atras.IsEnabled()
	dialogo.siguiente()
	dialogo.lista_perfil.SetSelection(f_asistente.PERFILES.index(perfiles.NOVATO))
	dialogo.siguiente()
	dialogo.casilla_lector.SetValue(True)
	dialogo.siguiente()
	dialogo.lista_tema.SetSelection(1)
	dialogo.siguiente()
	assert dialogo.pagina() == 4 and not dialogo.boton_siguiente.IsEnabled()
	assert "Novato" in dialogo.resumen.GetValue()
	dialogo.casilla_manual.SetValue(False)
	assert config.obtener("vista.tema") == "sistema", "nada se aplica antes de Terminar"
	dialogo.terminar_asistente()
	eleccion = dialogo.eleccion
	assert (eleccion.perfil, eleccion.tema, eleccion.lector, eleccion.abrir_manual) == ("novato", "norton", True, False)
	ejecutadas = []
	monkeypatch.setattr(f_asistente, "mostrar_asistente", lambda padre, conf: eleccion)
	dialogos_f.asistente(SimpleNamespace(ventana=None, config=config, ejecutar_orden=ejecutadas.append))
	assert perfiles.perfil_actual(config) == perfiles.NOVATO
	assert config.obtener("vista.tema") == "norton" and config.obtener("general.asistente_hecho") is True
	assert ejecutadas == []


def test_asistente_cancelado_no_se_repite(app_wx, config, monkeypatch):
	monkeypatch.setattr(f_asistente, "mostrar_asistente", lambda padre, conf: None)
	dialogos_f.asistente(SimpleNamespace(ventana=None, config=config))
	assert config.obtener("general.asistente_hecho") is True
	assert perfiles.perfil_actual(config) == perfiles.INTERMEDIO


def test_restablecer_fabrica_pide_confirmacion(config, respuestas):
	config.establecer_varias({"vista.tamano_fuente": 30, "general.asistente_hecho": True, "teclado.personalizadas": {"ver": ["F2"]}})
	ctx = SimpleNamespace(ventana=None, config=config)
	respuestas.si = False
	dialogos_f.restablecer_fabrica(ctx)
	assert config.obtener("vista.tamano_fuente") == 30
	respuestas.si = True
	dialogos_f.restablecer_fabrica(ctx)
	assert config.obtener("vista.tamano_fuente") == 10 and config.obtener("teclado.personalizadas") == {}
	assert config.obtener("general.asistente_hecho") is True, "no vuelve a salir el asistente"


def test_ayuda_teclado_alterna_el_modo():
	estado = SimpleNamespace(modo_ayuda_teclado=False)
	dialogos_f.ayuda_teclado(estado)
	assert estado.modo_ayuda_teclado is True
	dialogos_f.ayuda_teclado(estado)
	assert estado.modo_ayuda_teclado is False


def test_ningun_manejador_f_es_provisional():
	for orden in ordenes.CATALOGO:
		if orden.bloque != "F":
			continue
		modulo, funcion = orden.manejador.rsplit(".", 1)
		assert modulo == "dialogos_f", orden.id
		manejador = getattr(dialogos_f, funcion)
		assert not getattr(manejador, "provisional", False), orden.id


# ── Con la ventana principal real ───────────────────────────────────────────

@pytest.fixture
def ventana(app_wx, tmp_path, monkeypatch):
	from app.services import sesion
	from app.ui.ventana_principal import VentanaPrincipal

	carpeta = tmp_path / "trabajo"
	(carpeta / "sub").mkdir(parents=True)
	(carpeta / "uno.txt").write_text("1", encoding="utf-8")
	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {
			"izquierdo": {"pestanas": [sesion.pestana(ruta=str(carpeta))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(carpeta / "sub"))], "actual": 0},
		},
	})
	config = Configuracion()
	config.establecer_varias({"general.confirmar_salida": False, "general.asistente_hecho": True})
	marco = VentanaPrincipal(config)
	marco.mostrar()
	assert procesar_eventos(lambda: len(marco.izquierdo.panel_actual().entradas()) >= 3, 10)
	marco.carpeta_prueba = carpeta
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


def test_ordenes_f_en_la_ventana_real(ventana, respuestas, monkeypatch, caplog):
	import logging

	caplog.set_level(logging.ERROR)
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	carpeta = ventana.carpeta_prueba
	# Columnas del lado izquierdo desde su menú.
	monkeypatch.setattr(f_columnas, "elegir_columnas", lambda *a: (["nombre", "atributos"], {"nombre": 240}))
	ventana.ejecutar_orden("columnas", "izquierdo")
	assert panel.columnas == ["nombre", "atributos"]
	# Favorito de la carpeta actual y vuelta a él desde otra carpeta.
	respuestas.texto = "Trabajo"
	ventana.ejecutar_orden("agregar_favorito")
	assert [f.ruta for f in favoritos.cargar()] == [panel.mostrar_ruta()]
	panel.ir_a(str(carpeta / "sub"))
	assert procesar_eventos(lambda: panel.ruta.endswith("sub"), 5)
	monkeypatch.setattr(f_favoritos, "elegir_favorito", lambda padre, ruta: favoritos.cargar()[0])
	ventana.ejecutar_orden("favoritos")
	assert procesar_eventos(lambda: panel.ruta == str(carpeta), 5)
	# Historial de carpetas: la de antes está en la lista.
	monkeypatch.setattr(f_historial, "elegir_carpeta", lambda padre, carpetas: next(c for c in carpetas if c.endswith("sub")))
	ventana.ejecutar_orden("historial_carpetas")
	assert procesar_eventos(lambda: panel.ruta.endswith("sub"), 5)
	# Árbol: elegir la carpeta superior.
	monkeypatch.setattr(f_arbol, "elegir_carpeta", lambda padre, proveedor, raiz, ruta, tareas, lanzar, papelera: str(carpeta))
	ventana.ejecutar_orden("arbol_carpetas")
	assert procesar_eventos(lambda: panel.ruta == str(carpeta), 5)
	# Unidad del lado derecho: a una carpeta especial (la de trabajo, para no depender del equipo).
	derecho = ventana.derecho.panel_actual()
	monkeypatch.setattr(f_unidades, "elegir_destino", lambda *a: f_unidades.Destino(f_unidades.ESPECIAL, "Trabajo", str(carpeta)))
	ventana.ejecutar_orden("unidad_derecha")
	assert procesar_eventos(lambda: derecho.ruta == str(carpeta), 5)
	# Modo de ayuda de teclado y paleta.
	ventana.ejecutar_orden("ayuda_teclado")
	assert ventana.modo_ayuda_teclado is True
	ventana.ejecutar_orden("ayuda_teclado")
	assert ventana.modo_ayuda_teclado is False
	monkeypatch.setattr(f_paleta, "elegir_orden", lambda padre, mapa: "mostrar_ocultos")
	antes = ventana.config.obtener("paneles.mostrar_ocultos")
	ventana.ejecutar_orden("paleta_ordenes")
	assert ventana.config.obtener("paneles.mostrar_ocultos") is not antes
	# Mapa de teclas: la ventana reconstruye su mapa al guardar.
	monkeypatch.setattr(f_mapa_teclas, "editar_mapa", lambda padre, mapa: {"ver": ["Ctrl+Alt+V"]})
	ventana.ejecutar_orden("mapa_teclas")
	assert procesar_eventos(lambda: ventana.mapa_teclas.teclas_de("ver") == ("Ctrl+Alt+V",), 3)
	assert not [r for r in caplog.records if "Falló la orden" in r.getMessage()]
