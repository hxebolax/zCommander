# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Gestor de complementos y ventanas del bloque PL (diseño 2.0, 3.6, 3.10, 3.11, 14.7, 15.1 y 18.2).

Cada ventana nueva pasa ``revisar_teclado``; las preguntas se sustituyen (ningún
``ShowModal`` real). La carpeta ``data`` es la temporal de cada prueba.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

wx = pytest.importorskip("wx")

from app.core import paths  # noqa: E402
from app.core.configuracion import Configuracion  # noqa: E402
from app.core.tareas import GestorTareas  # noqa: E402
from app.plugins import api, cargador, config_plugins, estado, paquetes, registro, serie  # noqa: E402
from app.plugins.estado import EstadoComplemento  # noqa: E402
from app.services import renombrado  # noqa: E402
from app.services.vfs import resolver  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.dialogos import e_renombrado, pl_gestor, pl_instalar, pl_preferencias  # noqa: E402
from app.ui.dialogos.b_buscar import DialogoBuscar  # noqa: E402
from app.ui.ventanas import visor  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402
from tools import crear_plugin, empaquetar_plugin  # noqa: E402

EXTRA = """
[[configuracion]]
clave = "veces"
tipo = "entero"
defecto = 2
etiqueta = "&Veces:"
ayuda = "Cuántas veces."
minimo = 1
maximo = 9

[[configuracion]]
clave = "carpeta"
tipo = "carpeta"
defecto = ""
etiqueta = "Carpeta de &trabajo:"

[[configuracion]]
clave = "extensiones"
tipo = "lista"
defecto = ["txt"]
etiqueta = "E&xtensiones:"
pagina = "general"

[[configuracion]]
clave = "oculta"
tipo = "bool"
defecto = true
interna = true

[[visores]]
id = "doc"
patrones = ["*.doc1"]

[[mascaras]]
marcador = "[ANA:largo]"
descripcion = "Largo del nombre"
"""

CODIGO = """
import time
from app.plugins import api


class Complemento(api.Complemento):
	def activar(self, zc):
		self.zc = zc
		zc.ordenes.manejador("saludar", lambda ctx: ctx.anunciar("hola"))
		zc.visores.visor("doc", self.ver)
		zc.renombrado.mascara("[ANA:largo]", self.largo)

	def ver(self, proveedor, ruta, cancelacion):
		return api.Documento("Manual", (
			api.Seccion("Introducción", texto="Para empezar.", pagina=1),
			api.Seccion("Instalación", nivel=2, texto="Pasos.", pagina=2),
			api.Seccion("Uso", texto="Así se usa.", pagina=4),
		), aviso="Documento de prueba")

	def largo(self, entrada, proveedor):
		time.sleep(0.2)
		return str(len(entrada.nombre))
"""


class Config:
	def __init__(self) -> None:
		self.valores = {"complementos.inhabilitados": [], "complementos.confiados": {}, "complementos.permitir_sin_firma": True,
			"complementos.fallos_maximos": 3, "complementos.modo_desarrollo": False}

	def obtener(self, clave, *defecto):
		return self.valores[clave]

	def establecer(self, clave, valor) -> bool:
		self.valores[clave] = valor
		return True


@pytest.fixture
def instalado(registro_vacio, tmp_path, monkeypatch, app_wx):
	"""Un complemento de la persona ya instalado y aceptado en ``data/plugins`` (y el cargador de la sesión)."""
	for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
		del sys.modules[nombre]
	monkeypatch.setattr(serie, "SERIE", {})
	estado.reiniciar()
	config = Config()
	fuente = tmp_path / "fuente"
	assert crear_plugin.crear(fuente, "ana.ejemplo", "Ejemplo de Ana", autor="Ana") == []
	ruta = fuente / "manifiesto.toml"
	ruta.write_text(ruta.read_text(encoding="utf-8") + EXTRA, encoding="utf-8")
	(fuente / "__init__.py").write_text(textwrap.dedent(CODIGO), encoding="utf-8")
	resumen = paquetes.preparar(empaquetar_plugin.empaquetar(fuente, tmp_path / "ana.zcplugin"), config)
	paquetes.instalar(resumen, config)
	sesion = cargador.Cargador(config, carpeta_serie=tmp_path / "serie", carpeta_centinelas=tmp_path / "cargando")
	sesion.descubrir()
	cargador.fijar_actual(sesion)
	cargador.fijar_planificador(wx.CallAfter)
	yield type("Instalado", (), {"config": config, "cargador": sesion, "tmp": tmp_path, "fuente": fuente})
	sesion.cerrar()
	cargador.fijar_planificador(None)
	cargador.fijar_actual(None)
	for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
		del sys.modules[nombre]


# ── Gestor ───────────────────────────────────────────────────────────────────


def test_gestor_pasa_revisar_teclado_con_los_complementos_de_serie(app_wx):
	config = Config()
	dialogo = pl_gestor.DialogoGestor(None, config)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.lista.GetItemCount() == len(registro.complementos())
		estados = {dialogo.lista.texto_celda(i, 2) for i in range(dialogo.lista.GetItemCount())}
		assert estados == {"Sin cargar todavía"}, "el estado es texto"
		assert dialogo.lista.texto_celda(0, 3) == "De serie" and dialogo.lista.texto_celda(0, 4) == "Oficial"
		assert not dialogo.boton_desinstalar.IsEnabled(), "los de serie no se desinstalan"
		assert "Licencia:" in dialogo.detalles.GetValue()
	finally:
		dialogo.Destroy()


def test_gestor_inhabilita_con_espacio_y_desinstala_con_confirmacion(instalado, monkeypatch):
	dialogo = pl_gestor.DialogoGestor(None, instalado.config)
	try:
		afirmar_teclado_correcto(dialogo)
		assert [f.id for f in dialogo.filas] == ["ana.ejemplo"]
		dialogo.alternar_habilitado()
		assert registro.estado("ana.ejemplo") == EstadoComplemento.INHABILITADO
		assert dialogo.lista.texto_celda(0, 2) == "Inhabilitado" and dialogo.boton_habilitar.GetLabel() == "&Habilitar"
		dialogo.alternar_habilitado()
		assert registro.estado("ana.ejemplo") == EstadoComplemento.REGISTRADO
		preguntas: list[tuple[str, bool]] = []
		monkeypatch.setattr(pl_gestor, "preguntar", lambda padre, texto, titulo="", peligroso=False: preguntas.append((texto, peligroso)) or True)
		dialogo.desinstalar()
		assert all(peligroso for _t, peligroso in preguntas) and len(preguntas) == 2
		assert dialogo.lista.texto_celda(0, 2) == "Sin cargar todavía, se desinstalará al reiniciar"
		assert dialogo.boton_reiniciar.IsShown()
	finally:
		dialogo.Destroy()


def test_gestor_ver_permisos_registro_y_configurar(instalado, monkeypatch):
	textos: list[tuple[str, str]] = []
	monkeypatch.setattr(pl_gestor, "mostrar_texto", lambda padre, titulo, texto: textos.append((titulo, texto)))
	mostrados: list[str] = []
	monkeypatch.setattr(pl_preferencias, "abrir_dialogo", lambda padre, id_: mostrados.append(id_) or True)
	dialogo = pl_gestor.DialogoGestor(None, instalado.config)
	try:
		dialogo.ver_permisos()
		dialogo.ver_registro()
		dialogo.configurar()
		assert [t for t, _x in textos] == ["Permisos de Ejemplo de Ana", "Registro de Ejemplo de Ana"]
		assert "ningún permiso" in textos[0][1]
		assert mostrados == ["ana.ejemplo"]
	finally:
		dialogo.Destroy()


# ── Instalar ─────────────────────────────────────────────────────────────────


def test_dialogo_de_instalar_sin_firma_tiene_cancelar_como_predeterminado(instalado):
	resumen = paquetes.preparar(empaquetar_plugin.empaquetar(instalado.fuente, instalado.tmp / "otra.zcplugin"), instalado.config)
	dialogo = pl_instalar.DialogoInstalar(None, resumen)
	try:
		afirmar_teclado_correcto(dialogo)
		assert not resumen.instalable, "ya está instalada esa versión"
		assert dialogo.boton_instalar is None and dialogo.boton_cancelar.GetLabel() == "&Cerrar"
		assert "Ya está instalada la versión 0.1.0" in dialogo.texto.GetValue()
	finally:
		dialogo.Destroy()
		paquetes.descartar(resumen)
	fuente = instalado.tmp / "nueva"
	assert crear_plugin.crear(fuente, "ana.nueva", "Nueva") == []
	resumen = paquetes.preparar(empaquetar_plugin.empaquetar(fuente, instalado.tmp / "nueva.zcplugin"), instalado.config)
	dialogo = pl_instalar.DialogoInstalar(None, resumen)
	try:
		afirmar_teclado_correcto(dialogo)
		assert resumen.instalable and resumen.sin_firma
		assert dialogo.GetDefaultItem() is dialogo.boton_cancelar, "sin firma, Intro no instala"
		assert "no está firmado" in dialogo.texto.GetValue()
	finally:
		dialogo.Destroy()
		paquetes.descartar(resumen)


def test_instalar_desde_archivo_registra_sin_reiniciar(instalado, monkeypatch):
	fuente = instalado.tmp / "nueva"
	assert crear_plugin.crear(fuente, "ana.nueva", "Nueva") == []
	ruta = empaquetar_plugin.empaquetar(fuente, instalado.tmp / "nueva.zcplugin")
	vistos: list[str] = []
	monkeypatch.setattr(pl_instalar, "confirmar_instalacion", lambda padre, resumen: vistos.append(resumen.id) or True)
	terminado: list[bool] = []
	pl_gestor.instalar_desde_archivo(None, instalado.config, ruta, al_terminar=terminado.append)
	assert procesar_eventos(lambda: terminado, 15), "la instalación no terminó"
	assert terminado == [True] and vistos == ["ana.nueva"]
	assert registro.estado("ana.nueva") == EstadoComplemento.REGISTRADO
	assert (paths.ruta_plugins_usuario() / "ana.nueva" / "manifiesto.toml").is_file()


# ── Preferencias declarativas ────────────────────────────────────────────────


def test_pagina_declarativa_aparece_y_guarda_en_su_json(instalado):
	nodos = pl_preferencias.nodos()
	assert [(n.id, n.paginas) for n in nodos] == [("ana.ejemplo", (("general", "General"),))]
	assert [d["clave"] for d in pl_preferencias.declaraciones_de_pagina("ana.ejemplo", "")] == ["veces", "carpeta"]
	assert [d["clave"] for d in pl_preferencias.declaraciones_de_pagina("ana.ejemplo", "general")] == ["saludo", "extensiones"]
	marco = wx.Frame(None, title="Preferencias")
	try:
		pagina = pl_preferencias.crear(marco, None, "ana.ejemplo", "general")
		raiz = pl_preferencias.crear(marco, None, "ana.ejemplo", "")
		afirmar_teclado_correcto(pagina)
		afirmar_teclado_correcto(raiz)
		pagina.controles["saludo"][1].SetValue("Buenas")
		pagina.controles["extensiones"][1].SetValue("md\nrst")
		raiz.controles["veces"][1].SetValue(5)
		assert pagina.validar() is None and pagina.aplicar() and raiz.aplicar()
		guardado = json.loads((paths.ruta_config_plugins() / "ana.ejemplo.json").read_text(encoding="utf-8"))
		assert guardado["ajustes"]["saludo"] == "Buenas" and guardado["ajustes"]["extensiones"] == ["md", "rst"]
		assert guardado["ajustes"]["veces"] == 5
		assert "zcplugins.ana__ejemplo" not in sys.modules, "pintar la página no activa el complemento"
		pagina.restablecer()
		assert pagina.controles["saludo"][1].GetValue() == "Hola"
		assert config_plugins.registro().obtener("plugin.ana.ejemplo.saludo") == "Buenas", "restablecer no guarda"
	finally:
		marco.Destroy()


def test_dialogo_de_configuracion_del_gestor(instalado):
	dialogo = pl_preferencias.DialogoConfiguracion(None, "ana.ejemplo")
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.libro.GetPageCount() == 2
		dialogo.paginas[0].controles["veces"][1].SetValue(7)
		assert dialogo.aplicar()
		assert config_plugins.registro().obtener("plugin.ana.ejemplo.veces") == 7
	finally:
		dialogo.Destroy()


# ── Visor con secciones (14.7) ───────────────────────────────────────────────


def test_visor_de_complemento_muestra_el_documento_con_f6_entre_secciones(instalado, tmp_path):
	ruta = tmp_path / "informe.doc1"
	ruta.write_bytes(b"\x00binario")
	tareas = GestorTareas(max_hilos=2, nombre="prueba-pl-visor")
	config = Configuracion(ruta=tmp_path / "settings.json")
	ventana = visor.abrir(None, resolver.proveedor_local(), str(ruta), config, tareas, mostrar=False)
	try:
		from app.ui.accesibilidad.revision_teclado import revisar_teclado

		problemas = revisar_teclado(ventana, teclas_propias=["Ctrl+F", "Shift+F7", "F10"], permitidas=["F10"])
		assert [p for p in problemas if not p.aviso] == [], "las teclas nuevas del visor no chocan con las suyas"
		assert procesar_eventos(lambda: ventana.modelo is not None, 15), "el visor no cargó el documento"
		assert ventana.documento is not None and [s.titulo for _p, s in ventana.secciones] == ["Introducción", "Instalación", "Uso"]
		assert "Para empezar." in ventana.contenido and "Página 2" in ventana.contenido
		ventana.texto.SetInsertionPoint(0)
		ventana.cambiar_seccion(1)
		assert ventana.seccion_actual() == 0
		assert ventana.textos_estado()[0].startswith("Sección 1 de 3: Introducción")
		ventana.cambiar_seccion(1)
		assert ventana.seccion_actual() == 1
		ventana.cambiar_seccion(-1)
		assert ventana.seccion_actual() == 0
		assert ventana.ir_a_numero_de_pagina(3) and ventana.seccion_actual() == 2, "la página 3 no existe: va a la siguiente"
	finally:
		ventana.Close()
		procesar_eventos(lambda: False, 0.2)
		tareas.apagar(2)


def test_lista_de_secciones_filtra_y_elige(app_wx):
	dialogo = visor.DialogoSecciones(None, ["Introducción", "  Instalación", "Uso"], 1)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.elegida() == 1
		dialogo.filtrar("us")
		assert dialogo.elegida() == 2
	finally:
		dialogo.Destroy()


def test_abrir_documento_de_la_api(app_wx, tmp_path):
	documento = api.Documento("Notas", (api.Seccion("A", texto="uno"), api.Seccion("B", texto="dos")))
	tareas = GestorTareas(max_hilos=2, nombre="prueba-pl-doc")
	ventana = visor.abrir_documento(None, documento, Configuracion(ruta=tmp_path / "s.json"), tareas, mostrar=False)
	try:
		assert procesar_eventos(lambda: ventana.modelo is not None, 15)
		assert ventana.GetTitle() == "Notas - Visor" and len(ventana.secciones) == 2
	finally:
		ventana.Close()
		procesar_eventos(lambda: False, 0.2)
		tareas.apagar(2)


# ── Búsqueda y renombrado ────────────────────────────────────────────────────


def test_buscar_tiene_motor_y_casilla_de_documentos(app_wx, tmp_path):
	tareas = GestorTareas(max_hilos=1, nombre="prueba-pl-buscar")
	dialogo = DialogoBuscar(None, Configuracion(ruta=tmp_path / "s.json"), tareas, str(tmp_path))
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=["F3", "F4"])
		assert dialogo.lista_motor.GetString(0) == "El de zCommander"
		criterios = dialogo.criterios()
		assert criterios.motor == "" and criterios.dentro_de_documentos is False
	finally:
		dialogo.Destroy()
		tareas.apagar(2)


def test_renombrado_con_mascara_de_complemento_se_calcula_en_un_hilo(instalado, avisos_renombrado):
	elementos = [renombrado.Elemento("C:\\Fotos\\a.jpg", "a.jpg", entrada=api.Entrada("a.jpg", "C:\\Fotos\\a.jpg"))]
	dialogo = e_renombrado.DialogoRenombrado(None, elementos)
	try:
		dialogo.campo_mascara_nombre.SetValue("[N]-[ANA:largo]")
		dialogo.actualizar_vista_previa()
		assert dialogo.lista.texto_celda(0, 1) == "a-….jpg", "en la interfaz nunca espera"
		assert not dialogo.aceptar(), "Renombrar espera al cálculo"
		assert procesar_eventos(lambda: dialogo.lista.texto_celda(0, 1) == "a-5.jpg", 15)
		assert dialogo.GetReturnCode() == wx.ID_OK, "al terminar el cálculo, renombra"
		assert dialogo.pares() == [("C:\\Fotos\\a.jpg", "a-5.jpg")]
	finally:
		dialogo.Destroy()


@pytest.fixture
def avisos_renombrado(monkeypatch):
	dichos: list[str] = []
	monkeypatch.setattr(e_renombrado, "_avisar", lambda padre, mensaje, titulo: dichos.append(mensaje))
	return dichos


def test_menu_de_marcadores_incluye_los_de_complementos(instalado):
	dialogo = e_renombrado.DialogoRenombrado(None, [renombrado.Elemento("C:\\a.txt", "a.txt")])
	try:
		menu, ids = dialogo.menu_marcadores()
		assert "[ANA:largo]" in ids.values()
		menu.Destroy()
	finally:
		dialogo.Destroy()


def test_complementos_pl_instalar_marca_las_preguntas_en_la_interfaz(instalado, monkeypatch):
	from app.services import actualizador, eventos
	from app.ui.acciones import complementos_pl

	registradas: dict = {}
	monkeypatch.setattr(actualizador, "registrar_comprobacion", lambda nombre, funcion, activa: registradas.setdefault(nombre, activa))

	class Ventana:
		config = Configuracion(ruta=instalado.tmp / "v.json")
		arranque = None

		def servicio(self, nombre):
			return instalado.cargador

		def llamar_mas_tarde(self, ms, funcion):
			funcion()

		def padre(self):
			return None

	complementos_pl.instalar(Ventana())
	assert "complementos" in registradas and instalado.cargador.preguntas_en_interfaz
	instalado.cargador.sin_aceptar = ["ana.ejemplo"]
	instalado.cargador.centinelas = []
	eventos.bus().emitir(eventos.AL_ARRANCAR)
	assert instalado.cargador.sin_aceptar == [], "el aceptado no se pregunta (no está SIN_ACEPTAR)"


def test_reiniciar_solo_lanza_si_el_cierre_sigue(app_wx, monkeypatch):
	from app.services import eventos
	from app.ui.acciones import complementos_pl

	lanzados: list[list[str]] = []

	class Ventana:
		def __init__(self, cierra: bool) -> None:
			self.cierra = cierra

		def Close(self):  # noqa: N802 - imita wx
			if self.cierra:
				eventos.bus().emitir_sincrono(eventos.AL_CERRAR)

	assert not complementos_pl.reiniciar_aplicacion(Ventana(False), lanzar=lanzados.append)
	assert lanzados == []
	assert complementos_pl.reiniciar_aplicacion(Ventana(True), sin_complementos=True, lanzar=lanzados.append)
	assert "--esperar-pid" in lanzados[0] and lanzados[0][-1] == "--sin-complementos"
	assert Path(lanzados[0][1]).name == "main.py"


def test_complemento_instalar_usa_la_ruta_del_argumento(app_wx, monkeypatch):
	"""Intro sobre un ``.zcplugin`` y ``copia_cs.instalar`` pasan la ruta como argumento (peticiones-cs.md)."""
	from types import SimpleNamespace

	from app.ui.acciones import complementos_pl

	pedidas: list[Path] = []
	monkeypatch.setattr(pl_gestor, "elegir_archivo", lambda padre: pytest.fail("con argumento no se pregunta"))
	monkeypatch.setattr(pl_gestor, "instalar_desde_archivo", lambda padre, config, ruta, **_k: pedidas.append(ruta))
	complementos_pl.complemento_instalar(SimpleNamespace(ventana=None, config=None, argumento="carpeta/ana.zcplugin"))
	assert pedidas == [Path("carpeta/ana.zcplugin")]
