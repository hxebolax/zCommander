# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Visor interno (bloque A, sección 8.2): carga, hexadecimal, bloques, búsqueda y teclado.

Las ventanas se crean sin mostrarse; los hilos entregan con ``wx.CallAfter``
y ``procesar_eventos`` los atiende.
"""

from __future__ import annotations

import codecs
import io
import os

import pytest

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.core.tareas import GestorTareas  # noqa: E402
from app.services.vfs import base, resolver  # noqa: E402
from app.ui.accesibilidad.revision_teclado import revisar_teclado  # noqa: E402
from app.ui.dialogos import a_buscar  # noqa: E402
from app.ui.dialogos.a_buscar import DialogoBuscar, DialogoIrA, OpcionesBusqueda  # noqa: E402
from app.ui.dialogos.a_formato import DialogoCodificacion  # noqa: E402
from app.ui.ventanas import visor as mod_visor  # noqa: E402
from app.ui.ventanas.visor import BLOQUE, HEXADECIMAL, MapaPosiciones, ModeloVisor, VentanaVisor  # noqa: E402
from tests.ayudas_wx import simular_tecla  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402


@pytest.fixture
def config(tmp_path):
	return Configuracion(ruta=tmp_path / "settings.json")


@pytest.fixture
def tareas():
	gestor = GestorTareas(max_hilos=2, nombre="prueba-visor")
	yield gestor
	gestor.apagar(2.0)


@pytest.fixture
def abrir_visor(app_wx, config, tareas):
	creadas = []

	def abrir(ruta, proveedor=None, modo=None):
		ventana = VentanaVisor(None, proveedor or resolver.proveedor_local(), str(ruta), config, tareas, modo)
		creadas.append(ventana)
		assert procesar_eventos(lambda: ventana.modelo is not None, 10), "El visor no terminó de cargar"
		return ventana

	yield abrir
	for ventana in creadas:
		if ventana:
			ventana.Close()
	procesar_eventos(lambda: False, 0.2)


def _esperar_libre(ventana, segundos: float = 10) -> None:
	assert procesar_eventos(lambda: not ventana._ocupado, segundos), "El visor no terminó la tarea"


def test_utf16_con_bom_muestra_el_texto(abrir_visor, tmp_path):
	ruta = tmp_path / "unicode.txt"
	ruta.write_bytes(codecs.BOM_UTF16_LE + "Hola, mundo\r\nAño nuevo\r\n".encode("utf-16-le"))
	ventana = abrir_visor(ruta)
	assert ventana.texto.GetValue() == "Hola, mundo\nAño nuevo\n"
	assert ventana.modelo.codificacion == "utf-16-le"
	estado = ventana.textos_estado()
	assert estado[0] == "Línea 1, columna 1"
	assert "UTF-16" in estado[1]
	assert estado[2] == "Texto"


def test_f4_alterna_a_hexadecimal(abrir_visor, tmp_path):
	ruta = tmp_path / "hola.txt"
	ruta.write_bytes(b"Hola mundo")
	ventana = abrir_visor(ruta)
	assert ventana.texto.GetValue() == "Hola mundo"
	ventana.alternar_modo()
	_esperar_libre(ventana)
	assert ventana.modo == HEXADECIMAL
	assert ventana.texto.GetValue().startswith("00000000  48 6F 6C 61")
	assert ventana.item_hex.IsChecked()
	assert ventana.textos_estado()[2] == "Hexadecimal"
	ventana.alternar_modo()
	_esperar_libre(ventana)
	assert ventana.texto.GetValue() == "Hola mundo"


def test_binario_abre_en_hexadecimal(abrir_visor, tmp_path):
	ruta = tmp_path / "datos.bin"
	ruta.write_bytes(bytes(range(256)))
	ventana = abrir_visor(ruta)
	assert ventana.modo == HEXADECIMAL
	assert ventana.texto.GetValue().splitlines()[1].startswith("00000010  10 11 12")


def _archivo_grande(ruta, palabra_en: int | None = None) -> None:
	"""~3 MB de líneas numeradas; si se pide, «hola» en el tercer bloque."""
	lineas = [f"linea {i:07d} con texto de relleno para el visor\r\n" for i in range(60000)]
	contenido = "".join(lineas).encode("ascii")
	assert len(contenido) > 2 * BLOQUE + 1000
	if palabra_en is not None:
		contenido = contenido[:palabra_en] + b"hola" + contenido[palabra_en + 4:]
	ruta.write_bytes(contenido)


def test_buscar_hola_en_3_mb_por_bloques(abrir_visor, config, tmp_path):
	config.establecer("visor.limite_mb", 1)
	ruta = tmp_path / "grande.txt"
	posicion = 2 * BLOQUE + 50000
	_archivo_grande(ruta, posicion)
	ventana = abrir_visor(ruta)
	assert not ventana.modelo.entero
	assert ventana.modelo.bloques_texto == 3
	assert ventana.textos_estado()[3].endswith("bloque 1 de 3")
	resultados = []
	ventana.buscar_con(OpcionesBusqueda(texto="HOLA"), resultados.append)
	assert procesar_eventos(lambda: resultados, 15)
	assert resultados == [True]
	assert ventana.bloque == 2
	assert ventana.texto.GetStringSelection() == "hola"
	# El número de línea es el del archivo entero, no el del bloque.
	largo = len("linea 0000000 con texto de relleno para el visor\r\n")
	linea_real = (posicion // largo) + 1
	assert ventana.textos_estado()[0].startswith(f"Línea {linea_real:,}".replace(",", "."))
	# Otra vez: no hay más, da la vuelta y vuelve a encontrar la misma.
	resultados.clear()
	ventana.buscar_con(OpcionesBusqueda(texto="hola"), resultados.append)
	assert procesar_eventos(lambda: resultados, 15)
	assert resultados == [True] and ventana.bloque == 2
	resultados.clear()
	ventana.buscar_con(OpcionesBusqueda(texto="no existe"), resultados.append)
	assert procesar_eventos(lambda: resultados, 15)
	assert resultados == [False]


def test_bloques_e_ir_a_linea(abrir_visor, config, tmp_path):
	config.establecer("visor.limite_mb", 1)
	ruta = tmp_path / "grande.txt"
	_archivo_grande(ruta)
	ventana = abrir_visor(ruta)
	# Ninguna línea queda partida entre dos bloques.
	assert ventana.texto.GetValue().endswith("visor\n")
	listo = []
	ventana.cambiar_bloque(1, lambda: listo.append(1))
	assert procesar_eventos(lambda: listo, 10)
	assert ventana.bloque == 1
	assert ventana.texto.GetValue().startswith("linea ")
	listo.clear()
	ventana.ir_a_posicion(50000, lambda: listo.append(1))
	assert procesar_eventos(lambda: listo, 10)
	assert ventana.bloque == 2
	assert ventana.textos_estado()[0] == "Línea 50.000, columna 1"
	assert ventana.contenido[ventana.posicion():].startswith("linea 0049999 ")
	assert ventana.modelo.ir_a_linea(60000) is not None
	assert ventana.modelo.ir_a_linea(60001) is None
	assert ventana.modelo.total_lineas() == 60000


def test_modelo_hexadecimal_y_posiciones(tmp_path):
	ruta = tmp_path / "a.bin"
	ruta.write_bytes(bytes(range(256)) * 8192)  # 2 MB
	modelo = ModeloVisor(str(ruta), limite=BLOQUE)
	assert modelo.bloques_hex == 2
	bloque, posicion = mod_visor.posicion_hex(BLOQUE + 0x23)
	assert bloque == 1
	assert mod_visor.byte_de_hex(bloque, posicion) == BLOQUE + 0x23
	texto = modelo.hex_bloque(1)
	assert texto[posicion:posicion + 2] == "23"
	encontrado = modelo.buscar_bytes(a_buscar.compilar_bytes(OpcionesBusqueda(texto="ABC", mayusculas=True), "cp1252"), 100, False)
	assert encontrado.inicio == 0x41 + 256 and not encontrado.vuelta


def test_mapa_de_posiciones_con_emojis():
	texto = "ab\n\U0001F600x\nfin"
	mapa = MapaPosiciones(texto)
	assert mapa.a_control(texto.index("x")) == 5
	assert mapa.de_control(5) == texto.index("x")
	assert mapa.de_control(mapa.a_control(len(texto))) == len(texto)
	assert MapaPosiciones("sin nada raro").a_control(4) == 4


class _ProveedorMemoria(base.Proveedor):
	"""Proveedor sin ruta local (como un comprimido o un servidor)."""

	esquema = "memoria"

	def __init__(self, archivos: dict[str, bytes]) -> None:
		super().__init__()
		self.archivos = archivos

	def listar(self, ruta, cancelacion=None):
		return []

	def info(self, ruta):
		return base.Entrada(nombre=ruta, ruta=ruta, tamano=len(self.archivos[ruta]))

	def padre(self, ruta):
		return "" if ruta else None

	def unir(self, carpeta, nombre):
		return nombre

	def raiz(self, ruta):
		return ""

	def mostrar(self, ruta):
		return f"memoria:{ruta}"

	def abrir_lectura(self, ruta):
		return io.BytesIO(self.archivos[ruta])


def test_extrae_y_borra_el_temporal_al_cerrar(abrir_visor):
	proveedor = _ProveedorMemoria({"nota.txt": "Texto en un comprimido".encode()})
	ventana = abrir_visor("nota.txt", proveedor)
	assert ventana.texto.GetValue() == "Texto en un comprimido"
	temporal = ventana._temporal
	assert temporal and os.path.exists(temporal)
	assert "extraidos" in temporal
	ventana.Close()
	procesar_eventos(lambda: not os.path.exists(temporal), 2)
	assert not os.path.exists(temporal)


def test_teclado_del_visor(abrir_visor, tmp_path):
	ruta = tmp_path / "t.txt"
	ruta.write_text("uno\ndos\n", encoding="utf-8")
	ventana = abrir_visor(ruta)
	problemas = revisar_teclado(ventana, teclas_propias=["Ctrl+F", "Shift+F7", "F10"], permitidas=["F10"])
	# F10 cierra el visor por decisión de diseño (sección 8.2, como en Norton): es la única reserva admitida.
	errores = [p for p in problemas if not p.aviso]
	assert errores == [], "\n".join(str(p) for p in errores)
	# Las teclas que no son del visor siguen su camino (Tab, flechas, letras).
	assert simular_tecla(ventana, wx.WXK_TAB).saltado
	assert simular_tecla(ventana, "a").saltado


def test_f2_cambia_el_ajuste_y_conserva_la_etiqueta(abrir_visor, config, tmp_path):
	ruta = tmp_path / "t.txt"
	ruta.write_text("una línea muy larga " * 50, encoding="utf-8")
	ventana = abrir_visor(ruta)
	antes = ventana.ajuste
	ventana.alternar_ajuste()
	assert ventana.ajuste is not antes
	assert config.obtener("visor.ajuste_linea") is ventana.ajuste
	hijos = list(ventana.panel.GetChildren())
	assert hijos.index(ventana.texto) == hijos.index(ventana.etiqueta) + 1
	assert ventana.texto.GetValue().startswith("una línea muy larga")


def test_dialogos_de_busqueda_y_formato(app_wx):
	dialogo = DialogoBuscar(None, OpcionesBusqueda(texto="hola"))
	try:
		assert revisar_teclado(dialogo) == []
		dialogo.casilla_regex.SetValue(True)
		dialogo.campo.SetValue("(sin cerrar")
		assert "no es válida" in dialogo.problema()
		dialogo.campo.SetValue("ho+la")
		assert dialogo.problema() is None
		assert dialogo.aceptar()
		assert a_buscar.ULTIMA[0].texto == "ho+la"
	finally:
		dialogo.Destroy()
	ir_a = DialogoIrA(None, False, 1, 1, 100)
	try:
		assert revisar_teclado(ir_a) == []
		ir_a.campo.SetValue("150")
		assert "entre 1 y 100" in ir_a.problema()
		ir_a.campo.SetValue("42")
		assert ir_a.valor() == 42 and ir_a.problema() is None
	finally:
		ir_a.Destroy()
	assert a_buscar.interpretar_numero("0x1000", True) == 4096
	assert a_buscar.interpretar_numero("1000h", True) == 4096
	codif = DialogoCodificacion(None, "cp850")
	try:
		assert revisar_teclado(codif) == []
		assert codif.valor() == "cp850"
	finally:
		codif.Destroy()


def test_compilar_y_buscar_en():
	patron = a_buscar.compilar(OpcionesBusqueda(texto="sol", palabra=True))
	assert a_buscar.buscar_en("soldado y sol", patron, 0, False) == (10, 13, False)
	patron = a_buscar.compilar(OpcionesBusqueda(texto="a"))
	assert a_buscar.buscar_en("a b a", patron, 3, False) == (4, 5, False)
	assert a_buscar.buscar_en("a b a", patron, 5, False) == (0, 1, True)
	assert a_buscar.buscar_en("a b a", patron, 4, True) == (0, 1, False)
	assert a_buscar.buscar_en("a b a", patron, 0, True) == (4, 5, True)
	assert a_buscar.buscar_en("A", a_buscar.compilar(OpcionesBusqueda(texto="a", mayusculas=True)), 0, False) is None


# ── Órdenes F3 y Alt+F3, comparar archivos y ventana de diferencias ─────────────


class _Panel:
	"""Panel falso con lo que usan las órdenes del bloque A (``PanelProtocolo``)."""

	def __init__(self, carpeta, cursor=None, marcadas=()):
		self.proveedor = resolver.proveedor_local()
		self.ruta = str(carpeta)
		self._cursor = cursor
		self._marcadas = list(marcadas)

	def cursor(self):
		return self._cursor

	def marcadas(self):
		return self._marcadas

	def es_lista(self):
		return None

	def es_local(self):
		return True

	def ruta_local(self):
		return self.ruta


def _entrada(ruta, carpeta=False):
	return base.Entrada(nombre=os.path.basename(str(ruta)), ruta=str(ruta), es_carpeta=carpeta)


@pytest.fixture
def anunciados(monkeypatch):
	from app.ui import anuncios

	dichos = []
	monkeypatch.setattr(anuncios, "anunciar", lambda texto, *a, **k: dichos.append(texto))
	return dichos


def _contexto(config, tareas, activo, pasivo):
	from app.ui.contexto import ContextoOrden

	return ContextoOrden(ventana=None, config=config, tareas=tareas, operaciones=None, activo=activo, pasivo=pasivo)


def test_f3_usa_la_asociacion_o_el_visor_interno(app_wx, config, tareas, tmp_path, monkeypatch, anunciados):
	from app.services import asociaciones
	from app.ui.acciones import visor as acciones

	archivo = tmp_path / "a.txt"
	archivo.write_text("hola", encoding="utf-8")
	ctx = _contexto(config, tareas, _Panel(tmp_path, _entrada(archivo)), _Panel(tmp_path))
	abiertos, lanzados = [], []
	monkeypatch.setattr(mod_visor, "abrir", lambda padre, proveedor, ruta, *a, **k: abiertos.append(ruta))
	monkeypatch.setattr(acciones, "_lanzar_programa", lambda ctx, panel, ruta, plantilla: lanzados.append((ruta, plantilla)))
	acciones.ver(ctx)
	assert abiertos == [str(archivo)] and lanzados == []
	asociaciones.guardar([asociaciones.Regla("*.txt", ver="lector.exe %P")])
	acciones.ver(ctx)
	assert lanzados == [(str(archivo), "lector.exe %P")]
	# Alt+F3 sin visor externo configurado avisa.
	acciones.ver_externo(ctx)
	assert anunciados[-1].startswith("No hay visor externo configurado")
	config.establecer("visor.externo", "otro.exe %P")
	acciones.ver_externo(ctx)
	assert lanzados[-1] == (str(archivo), "otro.exe %P")


def test_programa_externo_con_archivo_de_comprimido_lo_extrae_y_vigila(app_wx, config, tareas, tmp_path, monkeypatch):
	from app.services.vfs import temporales
	from app.ui.acciones import visor as acciones

	proveedor = _ProveedorMemoria({"dentro.txt": b"contenido"})
	lanzados, vigilados = [], []
	monkeypatch.setattr(acciones, "_lanzar_programa", lambda ctx, panel, ruta, plantilla: lanzados.append(ruta))
	monkeypatch.setattr(temporales.vigilados, "vigilar", lambda local, prov, ruta, al_cambiar: vigilados.append((local, ruta)))
	ctx = _contexto(config, tareas, _Panel(tmp_path), _Panel(tmp_path))
	acciones.abrir_con_programa(ctx, ctx.activo, proveedor, "dentro.txt", "notepad.exe %P")
	assert procesar_eventos(lambda: lanzados, 5)
	assert open(lanzados[0], "rb").read() == b"contenido"
	assert vigilados == [(lanzados[0], "dentro.txt")]
	temporales.borrar(lanzados[0])


def test_elegir_archivos_a_comparar(app_wx, config, tareas, tmp_path, anunciados):
	from app.ui.acciones import visor as acciones

	a, b, c = (tmp_path / n for n in ("a.txt", "b.txt", "c.txt"))
	activo = _Panel(tmp_path, _entrada(a), marcadas=[_entrada(b), _entrada(c)])
	pasivo = _Panel(tmp_path, _entrada(a))
	pareja = acciones.archivos_a_comparar(_contexto(config, tareas, activo, pasivo))
	assert [r for _p, r in pareja] == [str(b), str(c)]
	activo._marcadas = []
	pasivo._cursor = _entrada(c)
	assert [r for _p, r in acciones.archivos_a_comparar(_contexto(config, tareas, activo, pasivo))] == [str(a), str(c)]
	pasivo._cursor = _entrada(tmp_path / "sub", carpeta=True)
	assert acciones.archivos_a_comparar(_contexto(config, tareas, activo, pasivo)) is None
	assert anunciados[-1].startswith("Para comparar hacen falta dos archivos")


def test_ventana_de_diferencias(app_wx, tareas, tmp_path, monkeypatch, anunciados):
	from app.ui.ventanas.diferencias import VentanaDiferencias

	izquierdo = [f"línea {i}" for i in range(1, 21)]
	derecho = list(izquierdo)
	derecho[11] = "cambiada"
	derecho.append("nueva al final")
	a, b = tmp_path / "a.txt", tmp_path / "b.txt"
	a.write_bytes(("\r\n".join(izquierdo) + "\r\n").encode("utf-8"))
	b.write_bytes(("\n".join(derecho) + "\n").encode("utf-8"))
	local = resolver.proveedor_local()
	ventana = VentanaDiferencias(None, (local, str(a)), (local, str(b)), tareas)
	try:
		assert procesar_eventos(lambda: ventana.resultado is not None, 10)
		assert ventana.lista.GetStrings() == ["Línea 12: cambiada", "Línea 21: solo en el derecho"]
		assert ventana.texto_izq.GetValue() == "línea 12"
		assert ventana.texto_der.GetValue() == "cambiada"
		assert anunciados[-1] == "2 diferencias"
		ventana.mover(1)
		assert ventana.lista.GetSelection() == 1
		assert ventana.texto_der.GetValue() == "nueva al final"
		assert ventana.texto_izq.GetValue().startswith("(No hay líneas")
		assert anunciados[-1] == "Línea 21: solo en el derecho. 2 de 2"
		ventana.mover(1)
		assert anunciados[-1] == "Es la última diferencia"
		assert revisar_teclado(ventana, teclas_propias=["Escape"]) == []
	finally:
		ventana.Destroy()


def test_diferencias_binarias_y_externo(app_wx, config, tareas, tmp_path, monkeypatch):
	from app.services.windows import shell_basico
	from app.ui.ventanas import diferencias

	a, b = tmp_path / "a.bin", tmp_path / "b.bin"
	datos = bytes(range(256)) * 40
	a.write_bytes(datos)
	b.write_bytes(datos[:5000] + b"\xff" + datos[5001:])
	local = resolver.proveedor_local()
	ventana = diferencias.VentanaDiferencias(None, (local, str(a)), (local, str(b)), tareas)
	try:
		assert procesar_eventos(lambda: ventana.resultado is not None, 10)
		assert ventana.lista.GetStrings() == ["Distintos a partir del byte 5000"]
		assert "00001380" in ventana.texto_izq.GetValue()
	finally:
		ventana.Destroy()
	# Con programa externo configurado, abrir lo usa con %P y %T.
	lanzadas = []
	monkeypatch.setattr(diferencias, "configuracion_de", lambda padre: config)
	monkeypatch.setattr(diferencias, "tareas_de", lambda padre: tareas)
	monkeypatch.setattr(shell_basico, "lanzar", lambda linea, carpeta=None, al_error=None: lanzadas.append(linea))
	config.establecer("general.diferencias_externo", "winmerge.exe %P %T")
	diferencias.abrir(None, (local, str(a)), (local, str(b)))
	assert procesar_eventos(lambda: lanzadas, 5)
	assert lanzadas == [f"winmerge.exe {a} {b}"]


def test_abrir_archivo_para_otros_bloques(app_wx, config, tareas, tmp_path, monkeypatch):
	from app.ui.acciones.visor import abrir_archivo
	from app.ui.ventanas.editor import VentanaEditor

	# Sin mostrarlas: una ventana visible robaría el foco durante las pruebas.
	mostradas = []
	monkeypatch.setattr(VentanaVisor, "mostrar", lambda self: mostradas.append(self))
	monkeypatch.setattr(VentanaEditor, "mostrar", lambda self: mostradas.append(self))

	principal = wx.Frame(None)
	principal.config, principal.tareas = config, tareas
	archivo = tmp_path / "r.txt"
	archivo.write_text("resultado", encoding="utf-8")
	try:
		vista = abrir_archivo(principal, resolver.proveedor_local(), str(archivo))
		assert isinstance(vista, VentanaVisor) and vista.config is config and vista.tareas is tareas
		assert procesar_eventos(lambda: vista.modelo is not None, 10)
		assert vista.texto.GetValue() == "resultado"
		edicion = abrir_archivo(principal, resolver.proveedor_local(), str(archivo), editar=True)
		assert isinstance(edicion, VentanaEditor)
		assert mostradas == [vista, edicion]
		assert procesar_eventos(lambda: edicion.cargado, 10)
		edicion.Close(True)
		vista.Close(True)
	finally:
		principal.Destroy()
		procesar_eventos(lambda: False, 0.2)
