# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Correcciones de la ronda N: F12, progreso por voz, sonidos, árbol, eliminar, columna Ruta,
textos, detener órdenes, perfiles, ejecutables de comprimidos, marcas ocultas y Tab desde una vista.

Cada prueba dice qué fallo cubre. Las que necesitan la ventana completa la
crean sin diálogos reales (``ShowModal`` está prohibido en ``conftest``).
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from tests.conftest import procesar_eventos

wx = pytest.importorskip("wx")


@pytest.fixture
def carpeta(tmp_path):
	base = tmp_path / "trabajo"
	base.mkdir()
	(base / "uno.txt").write_text("1", encoding="utf-8")
	(base / "dos.md").write_text("22", encoding="utf-8")
	(base / "tres.txt").write_text("333", encoding="utf-8")
	(base / "sub").mkdir()
	(base / "sub" / "dentro.txt").write_text("x", encoding="utf-8")
	return base


@pytest.fixture
def ventana(app_wx, carpeta, monkeypatch):
	from app.core.configuracion import Configuracion
	from app.services import sesion

	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {
			"izquierdo": {"pestanas": [sesion.pestana(ruta=str(carpeta))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(carpeta / "sub"))], "actual": 0},
		},
	})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	from app.ui.ventana_principal import VentanaPrincipal

	marco = VentanaPrincipal(config)
	marco.mostrar()
	assert procesar_eventos(lambda: len(marco.izquierdo.panel_actual().entradas()) >= 4, 10)
	assert procesar_eventos(lambda: len(marco.derecho.panel_actual().entradas()) >= 1, 10)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


@pytest.fixture
def anunciados(monkeypatch):
	"""Textos que se anuncian (sin hablar: la voz ya está silenciada en ``conftest``)."""
	from app.ui import anuncios

	textos: list[str] = []
	original = anuncios.anunciar

	def anunciar(texto, nivel=anuncios.NORMAL, completo="", interrumpir=None, sonido=""):
		if texto:
			textos.append(texto)
		original(texto, nivel, completo, interrumpir, sonido=sonido)

	monkeypatch.setattr(anuncios, "anunciar", anunciar)
	return textos


class _Config:
	"""Configuración mínima de diccionario para las piezas que solo leen."""

	def __init__(self, **valores) -> None:
		self.valores = {clave.replace("__", "."): valor for clave, valor in valores.items()}

	def obtener(self, clave):
		return self.valores[clave]


# ── 1. F12 usa VentanaOperaciones.mostrar ─────────────────────────────────────

def test_f12_muestra_con_refresco_y_foco_en_la_lista(ventana, monkeypatch):
	from app.ui.ventanas.operaciones import VentanaOperaciones

	llamadas = []
	original = VentanaOperaciones.mostrar

	def mostrar(self):
		llamadas.append(self)
		original(self)

	monkeypatch.setattr(VentanaOperaciones, "mostrar", mostrar)
	ventana.mostrar_operaciones()
	operaciones = ventana._ventana_operaciones  # noqa: SLF001 - se comprueba la ventana creada
	assert llamadas == [operaciones]
	assert operaciones.IsShown()
	# Show() y Raise() no arrancaban el refresco: mostrar() sí.
	assert operaciones._temporizador.IsRunning()  # noqa: SLF001
	operaciones.ocultar()


# ── 2. «Cada 25 %» anuncia 25, 50 y 75 una sola vez ───────────────────────────

def test_seguimiento_dice_cada_hito_una_vez():
	from app.ui.ventana_principal import SeguimientoProgreso

	seguimiento = SeguimientoProgreso()
	assert seguimiento.nuevo_hito(None) is None
	assert seguimiento.nuevo_hito(10) is None
	assert seguimiento.nuevo_hito(26) == 25
	assert seguimiento.nuevo_hito(30) is None
	# Un salto de 30 a 80 dice solo el más alto y da el 50 por dicho.
	assert seguimiento.nuevo_hito(80) == 75
	assert seguimiento.nuevo_hito(100) is None
	assert seguimiento.hitos_dichos == {25, 50, 75}


def test_seguimiento_decenas_para_los_tonos():
	from app.ui.ventana_principal import SeguimientoProgreso

	seguimiento = SeguimientoProgreso()
	assert [seguimiento.nueva_decena(p) for p in (5, 12, 15, 33, 33, 99, 100)] == [None, 10, None, 30, None, 90, None]


class _Operacion:
	def __init__(self, ident: int, estado: str = "ejecutando") -> None:
		self.id = ident
		self.estado = SimpleNamespace(value=estado)
		self.porcentaje: int | None = 0

	def descripcion(self) -> str:
		return f"Copiar {self.id}"

	def instantanea(self):
		return SimpleNamespace(porcentaje=self.porcentaje)


@pytest.fixture
def sonidos_pedidos(monkeypatch):
	"""Lo que se pide a ``servicio.sonar`` (2.0, 4.3): (evento, variante)."""
	from app.services.sonidos import servicio

	pedidos: list[tuple[str, str]] = []
	monkeypatch.setattr(servicio, "sonar", lambda evento, variante="", *, sustituye=False: pedidos.append((evento, variante)) or True)
	return pedidos


def _ventana_falsa(modo: str, progreso: str, operaciones):
	"""Reescrita en la 2.0 (18.1 y precisión 5 de la ronda 4): el progreso sonoro lo decide la ventana en el latido."""
	from app.ui.ventana_principal import VentanaPrincipal

	falsa = SimpleNamespace(config=_Config(accesibilidad__progreso_voz=modo, sonidos__progreso=progreso), _seguimientos={},
		operaciones=SimpleNamespace(en_marcha=lambda: list(operaciones)))
	return falsa, (lambda: VentanaPrincipal.seguir_progreso(falsa))


def test_cada_25_anuncia_hitos_y_al_empezar_y_terminar_no(anunciados, sonidos_pedidos):
	operacion = _Operacion(1)
	_falsa, seguir = _ventana_falsa("hitos", "cada_25", [operacion])
	for porcentaje in (0, 20, 25, 40, 55, 60, 99):
		operacion.porcentaje = porcentaje
		seguir()
	assert anunciados == ["Copiar 1: 25 %", "Copiar 1: 50 %", "Copiar 1: 75 %"]
	# Con «cada 25 %», op.progreso suena en los hitos 25, 50 y 75, una vez cada uno.
	assert sonidos_pedidos == [("op.progreso", "25"), ("op.progreso", "50"), ("op.progreso", "75")]
	anunciados.clear()
	sonidos_pedidos.clear()
	operacion2 = _Operacion(2)
	_falsa, seguir = _ventana_falsa("inicio_fin", "no", [operacion2])
	operacion2.porcentaje = 80
	seguir()
	assert anunciados == []
	assert sonidos_pedidos == []


def test_tonos_cada_10_y_decision(anunciados, sonidos_pedidos):
	operacion = _Operacion(1)
	_falsa, seguir = _ventana_falsa("final", "cada_10", [operacion])
	for porcentaje in (5, 10, 14, 21, 47):
		operacion.porcentaje = porcentaje
		seguir()
	assert sonidos_pedidos == [("op.progreso", "10"), ("op.progreso", "20"), ("op.progreso", "40")]
	operacion.estado.value = "esperando_decision"
	seguir()
	seguir()
	assert sonidos_pedidos.count(("op.decision", "")) == 1
	assert anunciados == []


# ── 3. Sonidos: el servicio filtra, el reproductor suena (reescritas en la 2.0, 18.1) ──

class _ReproductorFalso:
	def __init__(self) -> None:
		self.pedidos: list[tuple[str, str, bool]] = []

	def sonar(self, evento, variante, sustituye):
		self.pedidos.append((evento.id, variante, sustituye))
		return True

	def recargar(self):
		return None

	def cerrar(self):
		return None


def test_sonidos_respetan_las_casillas():
	"""``sonidos.activos`` y ``sonidos.eventos`` filtran; el reproductor recibe el evento y la variante."""
	from app.services.sonidos import servicio

	config = _Config(sonidos__activos=False, sonidos__eventos={})
	reproductor = _ReproductorFalso()
	servicio.iniciar(config, reproductor)
	try:
		assert not servicio.sonar("op.fin")
		assert reproductor.pedidos == []
		config.valores["sonidos.activos"] = True
		servicio._recalcular()
		assert servicio.sonar("op.fin")
		assert not servicio.sonar("nav.entrar")  # desactivado de fábrica
		config.valores["sonidos.eventos"] = {"op.fin": False, "nav.entrar": True}
		servicio._recalcular()
		assert not servicio.sonar("op.fin")
		assert servicio.sonar("nav.entrar")
		assert servicio.sonar("op.progreso", "30")
		assert reproductor.pedidos == [("op.fin", "", False), ("nav.entrar", "", False), ("op.progreso", "30", False)]
	finally:
		servicio.cerrar()


def test_tonos_suben_con_el_porcentaje_y_van_en_otro_hilo(tmp_path, monkeypatch):
	"""El motor de 4.4 nunca bloquea: ``sonar`` vuelve al momento y el sonido suena en el hilo «sonidos»."""
	from array import array

	from app.services.sonidos import catalogo, paquetes, wav
	from app.services.sonidos.motor import Motor

	carpeta = tmp_path / "sounds" / "clasico"
	for variante in ("10", "20"):
		wav.escribir(carpeta / f"op_progreso_{variante}.wav", array("h", [1000] * 800), 8000)
	paquetes.escribir_manifiesto(paquetes.Paquete(id="clasico", nombre="Clásico", carpeta=carpeta, de_serie=True, hereda=None))
	monkeypatch.setattr(paquetes, "carpeta_serie", lambda: tmp_path / "sounds")
	monkeypatch.setattr(paquetes, "carpeta_propios", lambda: tmp_path / "sounds_usuario")
	hilos = []

	class Salida:
		def reproducir(self, datos):
			hilos.append(threading.current_thread().name)

		def detener(self):
			return None

	motor = Motor(_Config(sonidos__volumen=70, sonidos__paquete="clasico", sonidos__intervalo_navegacion_ms=0),
		salida=Salida(), precargar=False)
	try:
		inicio = time.monotonic()
		assert motor.sonar(catalogo.evento("op.progreso"), "10", False)
		assert time.monotonic() - inicio < 0.5
		limite = time.monotonic() + 3
		while not hilos and time.monotonic() < limite:
			time.sleep(0.01)
		assert hilos == ["sonidos"]
		# Un evento sin archivo en el paquete no se acepta.
		assert not motor.sonar(catalogo.evento("nav.entrar"), "", False)
	finally:
		motor.cerrar()


def test_fin_de_operacion_suena_si_estan_activos(ventana, carpeta, monkeypatch, sonidos_pedidos):
	"""La ventana pide ``sonar("op.fin")`` al terminar bien una operación."""
	from app.ui.dialogos.copiar import DialogoCopiar

	monkeypatch.setattr(DialogoCopiar, "ShowModal", lambda self: wx.ID_OK)
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.ir_a_nombre("uno.txt")
	ventana.ejecutar_orden("copiar")
	assert procesar_eventos(lambda: ("op.fin", "") in sonidos_pedidos, 10)


# ── 4. paneles.retardo_arbol_ms llega a la vista Árbol ────────────────────────

def test_retardo_del_arbol_sale_de_la_configuracion(ventana):
	ventana.config.establecer("paneles.retardo_arbol_ms", 120)
	panel = ventana.derecho.panel_actual()
	panel.aplicar_vista("arbol")
	arbol = panel.vista_actual()
	assert arbol.retardo_ms == 120
	ventana.config.establecer("paneles.retardo_arbol_ms", 900)
	assert procesar_eventos(lambda: arbol.retardo_ms == 900, 3)
	panel.aplicar_vista("completa")


# ── 5. Unidad sin papelera: Intro pulsa «Cancelar» ────────────────────────────

def test_sin_papelera_el_boton_predeterminado_es_cancelar(ventana, carpeta, monkeypatch):
	from app.services.windows import papelera
	from app.ui.accesibilidad import dialogos

	monkeypatch.setattr(papelera, "admite_papelera", lambda _ruta: False)
	vistos = []

	def mostrar(dialogo):
		predeterminado = dialogo.GetDefaultItem()
		vistos.append((dialogo.cuerpo.GetLabel() if hasattr(dialogo.cuerpo, "GetLabel") else "", predeterminado.GetLabel()))
		dialogo.Destroy()
		return wx.ID_CANCEL

	monkeypatch.setattr(dialogos, "_mostrar", mostrar)
	ventana.config.establecer("general.usar_papelera", True)
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.ir_a_nombre("uno.txt")
	ventana.ejecutar_orden("eliminar")
	assert len(vistos) == 1
	assert "Cancelar" in vistos[0][1]
	procesar_eventos(lambda: False, 0.3)
	assert (carpeta / "uno.txt").exists()


# ── 6. Columna Ruta en las listas de resultados ───────────────────────────────

def test_columnas_con_ruta_y_dialogo_la_ofrece():
	from app.ui.dialogos import f_columnas
	from app.ui.panel_archivos import columnas_con_ruta

	assert columnas_con_ruta(["nombre", "tamano"]) == ["nombre", "ruta", "tamano"]
	assert columnas_con_ruta(["nombre", "ruta"]) == ["nombre", "ruta"]
	assert "ruta" in f_columnas.orden_inicial(["nombre", "tamano"])


def test_lista_de_resultados_muestra_la_ruta_y_se_puede_quitar(ventana, carpeta):
	panel = ventana.izquierdo.panel_actual()
	de_carpeta = panel.columnas
	assert "ruta" not in panel.lista_archivos.columnas
	panel.abrir_lista("Resultados", [str(carpeta / "uno.txt"), str(carpeta / "sub" / "dentro.txt")])
	assert procesar_eventos(lambda: panel.es_lista() == "Resultados" and len(panel.entradas()) >= 2, 5)
	columnas = panel.lista_archivos.columnas
	assert columnas[:2] == ["nombre", "ruta"]
	indice = next(i for i, e in enumerate(panel.entradas()) if e.nombre == "dentro.txt")
	assert panel.lista_archivos.texto_celda(indice, 1) == str(carpeta / "sub")
	# Elegir columnas en la lista cambia las de las listas, no las de carpeta.
	panel.aplicar_columnas(["nombre", "tamano"])
	assert panel.lista_archivos.columnas == ["nombre", "tamano"]
	assert panel.columnas_carpeta() == de_carpeta
	panel.cerrar_lista()
	assert procesar_eventos(lambda: not panel.es_lista() and panel.ruta == str(carpeta), 5)
	assert panel.lista_archivos.columnas == de_carpeta
	assert panel.como_dict()["columnas"] == de_carpeta


# ── 7. Textos ─────────────────────────────────────────────────────────────────

def test_textos_corregidos(monkeypatch):
	from app.core import configuracion, descripciones_config
	from app.ui.acciones import archivos
	from app.ui.accesibilidad import dialogos
	from app.ui.dialogos import f_preferencias

	ayuda = descripciones_config.DESCRIPCIONES["vista.tamano_fuente"][1]
	assert "propio tamaño" in ayuda
	for valor in configuracion.REGLAS["visor.codificacion"].opciones:
		assert f_preferencias.nombre_opcion("visor.codificacion", valor) != valor
	preguntas = []
	monkeypatch.setattr(dialogos, "confirmar", lambda _p, texto, *_a, **_k: preguntas.append(texto) or wx.ID_NO)
	registro = SimpleNamespace(ultima=lambda: SimpleNamespace(descripcion="Renombrar 2 elementos"))
	archivos.deshacer(SimpleNamespace(ventana=None, servicio=lambda _n: registro))
	assert preguntas == ["¿Deshacer: Renombrar 2 elementos?"]


# ── 8. Escape detiene la orden de la línea de órdenes ─────────────────────────

def _lanzar_orden_larga(ventana, carpeta) -> None:
	ventana.ejecutar_proceso("ping -n 60 127.0.0.1", str(carpeta), None, refrescar=False)
	assert procesar_eventos(ventana.hay_orden_en_marcha, 5)


def test_escape_en_el_panel_detiene_la_orden(ventana, carpeta, anunciados):
	_lanzar_orden_larga(ventana, carpeta)
	ventana.izquierdo.panel_actual().enfocar()
	ventana.ejecutar_orden("cancelar")
	assert procesar_eventos(lambda: "Orden detenida" in anunciados, 15)
	assert not ventana.hay_orden_en_marcha()


def test_escape_en_la_linea_vacia_detiene_la_orden(ventana, carpeta, anunciados):
	_lanzar_orden_larga(ventana, carpeta)
	ventana.linea.ChangeValue("")
	ventana.ejecutar_orden("linea_vaciar")
	assert procesar_eventos(lambda: "Orden detenida" in anunciados, 15)
	assert not ventana.detener_orden()


# ── 9. Los perfiles cambian las columnas de las pestañas abiertas ─────────────

def test_perfil_cambia_las_columnas_abiertas_que_seguian_las_de_defecto(ventana):
	from app.services import perfiles

	izquierdo = ventana.izquierdo.panel_actual()
	derecho = ventana.derecho.panel_actual()
	assert izquierdo.columnas == ventana.config.obtener("paneles.columnas")
	derecho.aplicar_columnas(["nombre", "atributos"])
	perfiles.aplicar_perfil(ventana.config, perfiles.AVANZADO)
	esperadas = perfiles.PERFILES[perfiles.AVANZADO]["paneles.columnas"]
	assert procesar_eventos(lambda: izquierdo.lista_archivos.columnas == esperadas, 3)
	assert izquierdo.columnas == esperadas
	# La elegida a propósito para una pestaña se conserva.
	assert derecho.columnas == ["nombre", "atributos"]


# ── 10. Un ejecutable dentro de un comprimido o servidor se confirma siempre ──

def test_ejecutable_de_un_comprimido_pide_confirmacion(monkeypatch):
	from app.services import asociaciones
	from app.ui.acciones import navegacion
	from app.ui.accesibilidad import dialogos

	monkeypatch.setattr(asociaciones, "orden_para", lambda *_a, **_k: None)
	preguntas = []
	respuesta = {"valor": wx.ID_NO}

	def confirmar(_padre, texto, _titulo="", **opciones):
		preguntas.append((texto, opciones.get("peligroso")))
		return respuesta["valor"]

	monkeypatch.setattr(dialogos, "confirmar", confirmar)
	enviadas = []
	ctx = SimpleNamespace(ventana=None, config=_Config(general__confirmar_ejecutar=False),
		tareas=SimpleNamespace(enviar=lambda *a, **k: enviadas.append(a)))
	proveedor = SimpleNamespace(ruta_local=lambda _r: None)
	panel = SimpleNamespace(proveedor=proveedor, mostrar_ruta=lambda: "D:\\descargas\\juego.zip")
	entrada = SimpleNamespace(nombre="instalar.exe", ruta="instalar.exe")
	navegacion._abrir_archivo(ctx, panel, entrada)  # noqa: SLF001 - la decisión está en esta función
	assert len(preguntas) == 1 and preguntas[0][1] is True
	assert "juego.zip" in preguntas[0][0]
	assert enviadas == []
	respuesta["valor"] = wx.ID_YES
	navegacion._abrir_archivo(ctx, panel, entrada)  # noqa: SLF001
	assert len(enviadas) == 1
	# Un documento del comprimido se abre sin preguntar.
	navegacion._abrir_archivo(ctx, panel, SimpleNamespace(nombre="leeme.txt", ruta="leeme.txt"))  # noqa: SLF001
	assert len(preguntas) == 2 and len(enviadas) == 2


# ── 11. Las marcas de lo que deja de verse vuelven al verse ───────────────────

def test_marcas_ocultas_por_el_filtro_vuelven(ventana, carpeta):
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.marcar(lambda e: e.nombre in ("uno.txt", "dos.md"))
	assert {e.nombre for e in panel.marcadas()} == {"uno.txt", "dos.md"}
	panel.aplicar_filtro("*.txt")
	assert [e.nombre for e in panel.marcadas()] == ["uno.txt"]
	assert "Marcados: 1" in panel.texto_resumen()
	assert panel.lista_archivos.marcas_ocultas() == {str(carpeta / "dos.md").casefold()}
	panel.aplicar_filtro("")
	assert {e.nombre for e in panel.marcadas()} == {"uno.txt", "dos.md"}
	# Al cambiar de carpeta se olvidan también las que no se veían.
	panel.aplicar_filtro("*.txt")
	panel.ir_a(str(carpeta / "sub"))
	assert procesar_eventos(lambda: panel.ruta == str(carpeta / "sub"), 5)
	panel.ir_a(str(carpeta))
	assert procesar_eventos(lambda: panel.ruta == str(carpeta), 5)
	panel.aplicar_filtro("")
	assert panel.marcadas() == [] and panel.lista_archivos.marcas_ocultas() == set()


def test_marca_oculta_de_un_archivo_borrado_no_vuelve(ventana, carpeta):
	panel = ventana.izquierdo.panel_actual()
	panel.marcar(lambda e: e.nombre == "dos.md")
	panel.aplicar_filtro("*.txt")
	(carpeta / "dos.md").unlink()
	hecho = []
	panel.refrescar(al_terminar=hecho.append)
	assert procesar_eventos(lambda: hecho, 5)
	assert panel.lista_archivos.marcas_ocultas() == set()
	(carpeta / "dos.md").write_text("nuevo", encoding="utf-8")
	hecho.clear()
	panel.refrescar(al_terminar=hecho.append)
	assert procesar_eventos(lambda: hecho, 5)
	panel.aplicar_filtro("")
	assert panel.marcadas() == []


# ── 12. Tab desde una vista vuelve al otro panel ──────────────────────────────

def test_tab_desde_una_vista_del_lado_pasivo_vuelve_al_activo(ventana, monkeypatch):
	izquierdo = ventana.izquierdo.panel_actual()
	derecho = ventana.derecho.panel_actual()
	izquierdo.enfocar()
	ventana.panel_enfocado(izquierdo)
	derecho.aplicar_vista("informacion")
	control = derecho.vista_actual().control_enfocable()
	# El foco está en la vista del lado derecho, pero el activo sigue siendo el izquierdo.
	monkeypatch.setattr(wx.Window, "FindFocus", staticmethod(lambda: control))
	enfocados = []
	monkeypatch.setattr(izquierdo, "enfocar", lambda: enfocados.append("izquierdo"))
	monkeypatch.setattr(derecho, "enfocar", lambda: enfocados.append("derecho"))
	assert ventana._ambitos(control)[1] == "vista"  # noqa: SLF001 - el despachador manda Tab a cambiar_panel
	ventana.ejecutar_orden("cambiar_panel")
	assert enfocados == ["izquierdo"]
