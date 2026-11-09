# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Editor interno (bloque A, sección 8.3): formato, guardado seguro, reemplazar, cierre y teclado.

Las ventanas se crean sin mostrarse; los diálogos se sustituyen con ``monkeypatch``.
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
from app.ui.accesibilidad import dialogos  # noqa: E402
from app.ui.accesibilidad.revision_teclado import revisar_teclado  # noqa: E402
from app.ui.dialogos.a_buscar import DialogoReemplazar, OpcionesBusqueda  # noqa: E402
from app.ui.dialogos.a_formato import DialogoGuardarComo  # noqa: E402
from app.ui.ventanas import editor as mod_editor  # noqa: E402
from app.ui.ventanas.editor import FormatoTexto, VentanaEditor, codificar, leer_formato  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402


@pytest.fixture
def config(tmp_path):
	return Configuracion(ruta=tmp_path / "settings.json")


@pytest.fixture
def tareas():
	gestor = GestorTareas(max_hilos=2, nombre="prueba-editor")
	yield gestor
	gestor.apagar(2.0)


@pytest.fixture
def abrir_editor(app_wx, config, tareas):
	creadas = []

	def abrir(ruta, proveedor=None, padre=None):
		ventana = VentanaEditor(padre, proveedor or resolver.proveedor_local(), str(ruta), config, tareas)
		creadas.append(ventana)
		assert procesar_eventos(lambda: ventana.cargado, 10), "El editor no terminó de cargar"
		return ventana

	yield abrir
	for ventana in creadas:
		if ventana:
			ventana.texto.SetModified(False)
			ventana.Close(True)
	procesar_eventos(lambda: False, 0.2)


def _escribir(ventana, texto: str) -> None:
	"""Sustituye el texto como lo haría la persona (``SetValue`` deja el control «sin cambios»)."""
	ventana.texto.SelectAll()
	ventana.texto.WriteText(texto)
	assert ventana.modificado()


def _guardar(ventana) -> list[bool]:
	resultado: list[bool] = []
	ventana.guardar(resultado.append)
	assert procesar_eventos(lambda: resultado, 10), "No terminó de guardar"
	return resultado


# ── Formato ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("datos", "esperado"), [
	("Año\r\nniño\r\n".encode("cp1252"), FormatoTexto("cp1252", "\r\n", False)),
	(codecs.BOM_UTF8 + "Año\nniño\n".encode("utf-8"), FormatoTexto("utf-8", "\n", True)),
	(codecs.BOM_UTF16_LE + "Año\rniño\r".encode("utf-16-le"), FormatoTexto("utf-16-le", "\r", True)),
	(b"", FormatoTexto("utf-8", "\r\n", False)),
])
def test_leer_y_codificar_conserva_el_formato(datos, esperado):
	texto, formato_ = leer_formato(datos)
	assert formato_ == esperado
	assert "\r" not in texto
	assert codificar(texto, formato_) == datos


def test_codificar_falla_si_no_cabe():
	with pytest.raises(UnicodeEncodeError):
		codificar("emoji \U0001F600", FormatoTexto("cp1252"))


# ── Guardar ─────────────────────────────────────────────────────────────────


def test_guarda_conservando_crlf_y_la_codificacion(abrir_editor, tmp_path):
	ruta = tmp_path / "nota.txt"
	ruta.write_bytes("Año\r\nniño\r\n".encode("cp1252"))
	ventana = abrir_editor(ruta)
	assert ventana.texto.GetValue() == "Año\nniño\n"
	assert ventana.formato == FormatoTexto("cp1252", "\r\n", False)
	assert not ventana.modificado()
	ventana.texto.SetInsertionPointEnd()
	ventana.texto.WriteText("España\n")
	assert ventana.modificado()
	assert "(modificado)" in ventana.GetTitle()
	assert _guardar(ventana) == [True]
	assert ruta.read_bytes() == "Año\r\nniño\r\nEspaña\r\n".encode("cp1252")
	assert not ventana.modificado()
	assert "(modificado)" not in ventana.GetTitle()
	# Ni temporales ni .bak sueltos en la carpeta.
	assert sorted(os.listdir(tmp_path)) == ["nota.txt", "settings.json"]


def test_guarda_utf8_con_bom_y_lf_y_copia_bak(abrir_editor, config, tmp_path):
	config.establecer("editor.copia_seguridad", True)
	ruta = tmp_path / "datos.md"
	original = codecs.BOM_UTF8 + "uno\ndos\n".encode("utf-8")
	ruta.write_bytes(original)
	ventana = abrir_editor(ruta)
	_escribir(ventana, "uno\ndos\ntres €\n")
	assert _guardar(ventana) == [True]
	assert ruta.read_bytes() == codecs.BOM_UTF8 + "uno\ndos\ntres €\n".encode("utf-8")
	assert (tmp_path / "datos.md.bak").read_bytes() == original


def test_avisa_si_cambio_en_el_disco(abrir_editor, tmp_path, monkeypatch):
	ruta = tmp_path / "nota.txt"
	ruta.write_text("primero\n", encoding="utf-8")
	ventana = abrir_editor(ruta)
	ruta.write_text("otro programa lo cambió\n", encoding="utf-8")
	os.utime(ruta, ns=(os.stat(ruta).st_atime_ns, os.stat(ruta).st_mtime_ns + 5_000_000_000))
	preguntas = []
	monkeypatch.setattr(dialogos, "confirmar", lambda padre, texto, *a, **k: preguntas.append(texto) or wx.ID_NO)
	_escribir(ventana, "mi versión\n")
	assert _guardar(ventana) == [False]
	assert "ha cambiado en el disco" in preguntas[0]
	assert ruta.read_text(encoding="utf-8") == "otro programa lo cambió\n"


def test_caracter_que_no_cabe_ofrece_utf8(abrir_editor, tmp_path, monkeypatch):
	ruta = tmp_path / "ansi.txt"
	ruta.write_bytes("café\r\n".encode("cp1252"))
	ventana = abrir_editor(ruta)
	monkeypatch.setattr(dialogos, "elegir_opcion", lambda *a, **k: 0)
	_escribir(ventana, "café ✓\n")
	assert _guardar(ventana) == [True]
	assert ruta.read_bytes() == "café ✓\r\n".encode("utf-8")
	assert ventana.formato.codificacion == "utf-8"


class _ZipFalso(base.Proveedor):
	"""Proveedor de solo lectura sin ruta local (como un comprimido)."""

	esquema = "zip"

	def __init__(self, contenedor, datos: bytes) -> None:
		super().__init__()
		self.capacidades.escribir = False
		self.contenedor = contenedor
		self.datos = datos

	def listar(self, ruta, cancelacion=None):
		return []

	def info(self, ruta):
		return base.Entrada(nombre=ruta, ruta=ruta, tamano=len(self.datos))

	def padre(self, ruta):
		return "" if ruta else None

	def unir(self, carpeta, nombre):
		return nombre

	def raiz(self, ruta):
		return ""

	def mostrar(self, ruta):
		return f"zip:{ruta}"

	def abrir_lectura(self, ruta):
		return io.BytesIO(self.datos)


def test_en_un_comprimido_guardar_lleva_a_guardar_como(abrir_editor, tmp_path, monkeypatch):
	local = resolver.proveedor_local()
	proveedor = _ZipFalso((local, str(tmp_path / "paquete.zip")), b"dentro\r\n")
	ventana = abrir_editor("leeme.txt", proveedor)
	assert ventana.en_comprimido
	assert ventana.ruta_propuesta() == str(tmp_path / "leeme.txt")
	llamadas = []
	monkeypatch.setattr(ventana, "guardar_como", lambda al_terminar=None: llamadas.append(al_terminar))
	ventana.guardar()
	assert len(llamadas) == 1
	resultado = []
	ventana.guardar_en(str(tmp_path / "leeme.txt"), ventana.formato, resultado.append)
	assert procesar_eventos(lambda: resultado, 10)
	assert (tmp_path / "leeme.txt").read_bytes() == b"dentro\r\n"
	assert not ventana.en_comprimido
	assert ventana.nombre == "leeme.txt"


# ── Buscar y reemplazar ─────────────────────────────────────────────────────


def test_buscar_reemplazar_y_reemplazar_todo(abrir_editor, tmp_path):
	ruta = tmp_path / "t.txt"
	ruta.write_text("gato perro gato\nel gato \U0001F600 gato\n", encoding="utf-8")
	ventana = abrir_editor(ruta)
	opciones = OpcionesBusqueda(texto="gato")
	assert ventana.buscar_con(opciones)
	assert ventana.texto.GetStringSelection() == "gato"
	assert ventana.buscar_con(opciones)
	assert ventana.texto.GetSelection() == (11, 15)
	assert ventana.reemplazar(opciones, "GATO")
	assert ventana.texto.GetValue().startswith("gato perro GATO\n")
	# Detrás del emoji las posiciones siguen cuadrando.
	ventana.texto.SetInsertionPoint(0)
	# Sin «distinguir mayúsculas», también cambia «GATO».
	assert ventana.reemplazar_todo(opciones, "felino") == 4
	assert ventana.texto.GetValue() == "felino perro felino\nel felino \U0001F600 felino\n"
	ventana.texto.Undo()
	assert ventana.texto.GetValue().startswith("gato perro GATO")
	regex = OpcionesBusqueda(texto=r"(\w+) perro", regex=True)
	assert ventana.reemplazar_todo(regex, r"perro \1") == 1
	assert ventana.texto.GetValue().startswith("perro gato GATO")
	ventana.ir_a_linea(2)
	assert ventana.linea_y_columna() == (2, 1)


# ── Cierre ────────────────────────────────────────────────────────────────────


def test_cerrar_con_cambios_pregunta(abrir_editor, tmp_path, monkeypatch):
	ruta = tmp_path / "t.txt"
	ruta.write_text("x\n", encoding="utf-8")
	ventana = abrir_editor(ruta)
	_escribir(ventana, "cambiado\n")
	respuestas = [None]
	monkeypatch.setattr(dialogos, "elegir_opcion", lambda *a, **k: respuestas[0])
	ventana.Close()
	procesar_eventos(lambda: False, 0.2)
	assert ventana and not ventana.IsBeingDeleted()  # Cancelar: sigue abierto
	respuestas[0] = 1
	ventana.Close()
	procesar_eventos(lambda: not ventana, 2)
	assert not ventana
	assert ruta.read_text(encoding="utf-8") == "x\n"


def test_cerrar_la_ventana_principal_pregunta_por_los_cambios(abrir_editor, tmp_path, monkeypatch):
	principal = wx.Frame(None)
	try:
		ruta = tmp_path / "t.txt"
		ruta.write_text("x\n", encoding="utf-8")
		ventana = abrir_editor(ruta, padre=principal)
		_escribir(ventana, "cambiado\n")
		monkeypatch.setattr(dialogos, "elegir_opcion", lambda *a, **k: None)
		assert not principal.Close()  # vetado: Cancelar
		procesar_eventos(lambda: False, 0.2)
		assert principal and ventana and not ventana.IsBeingDeleted()
		ventana.texto.SetModified(False)
		ventana.Close(True)
		procesar_eventos(lambda: not ventana, 2)
		# Ya no queda enganchado a la principal.
		assert principal.Close()
	finally:
		if principal:
			principal.Destroy()


def test_teclado_del_editor_y_sus_dialogos(abrir_editor, tmp_path):
	ruta = tmp_path / "t.txt"
	ruta.write_text("x\n", encoding="utf-8")
	ventana = abrir_editor(ruta)
	problemas = revisar_teclado(ventana, teclas_propias=["Ctrl+S", "Ctrl+F", "Shift+F7", "F10"], permitidas=["F10"])
	errores = [p for p in problemas if not p.aviso]
	assert errores == [], "\n".join(str(p) for p in errores)
	reemplazar = DialogoReemplazar(ventana, OpcionesBusqueda(texto="a"), "", lambda o: True, lambda o, n: True, lambda o, n: 0)
	try:
		assert revisar_teclado(reemplazar) == []
	finally:
		reemplazar.Destroy()
	guardar = DialogoGuardarComo(ventana, str(tmp_path / "t.txt"), "cp1252", "\n", False)
	try:
		assert revisar_teclado(guardar) == []
		assert guardar.codificacion() == "cp1252" and guardar.fin_de_linea() == "\n"
		guardar.campo_ruta.SetValue(str(tmp_path / "no_existe" / "a.txt"))
		assert "no existe" in guardar.problema()
		guardar.campo_ruta.SetValue(str(tmp_path / "nuevo.txt"))
		assert guardar.problema() is None
	finally:
		guardar.Destroy()


def test_guardar_local_no_deja_temporales_si_falla(tmp_path, monkeypatch):
	from app.services.windows import copia_nativa

	def falla(temporal, destino):
		raise OSError("simulado")

	monkeypatch.setattr(copia_nativa, "sustituir", falla)
	ruta = tmp_path / "a.txt"
	ruta.write_bytes(b"original")
	with pytest.raises(OSError):
		mod_editor.guardar_local(str(ruta), b"nuevo")
	assert ruta.read_bytes() == b"original"
	assert os.listdir(tmp_path) == ["a.txt"]


# ── Órdenes F4 y Mayús+F4 ──────────────────────────────────────────────────────


class _Panel:
	def __init__(self, carpeta, cursor=None):
		self.proveedor = resolver.proveedor_local()
		self.ruta = str(carpeta)
		self._cursor = cursor
		self.refrescos = 0
		self.ir_a = []

	def cursor(self):
		return self._cursor

	def marcadas(self):
		return []

	def es_lista(self):
		return None

	def es_local(self):
		return True

	def ruta_local(self):
		return self.ruta

	def refrescar(self, conservar=True, al_terminar=None):
		self.refrescos += 1
		if al_terminar:
			al_terminar(True)

	def ir_a_nombre(self, nombre):
		self.ir_a.append(nombre)
		return True


def _contexto(config, tareas, activo):
	from app.ui.contexto import ContextoOrden

	return ContextoOrden(ventana=None, config=config, tareas=tareas, operaciones=None, activo=activo, pasivo=_Panel(activo.ruta))


def test_f4_editor_interno_o_externo(app_wx, config, tareas, tmp_path, monkeypatch):
	from app.ui.acciones import visor as acciones

	archivo = tmp_path / "a.txt"
	archivo.write_text("x", encoding="utf-8")
	ctx = _contexto(config, tareas, _Panel(tmp_path, base.Entrada(nombre="a.txt", ruta=str(archivo))))
	internos, externos = [], []
	monkeypatch.setattr(mod_editor, "abrir", lambda padre, proveedor, ruta, *a, **k: internos.append(ruta))
	monkeypatch.setattr(acciones, "_lanzar_programa", lambda ctx, panel, ruta, plantilla: externos.append(plantilla))
	acciones.editar(ctx)
	assert internos == [str(archivo)] and externos == []
	config.establecer("editor.usar_externo", True)
	acciones.editar(ctx)
	assert externos == ["notepad.exe %P"]


def test_mayus_f4_crea_el_archivo_y_lo_abre(app_wx, config, tareas, tmp_path, monkeypatch):
	from app.ui.acciones import visor as acciones
	from app.ui.dialogos import nombre as mod_nombre

	panel = _Panel(tmp_path)
	ctx = _contexto(config, tareas, panel)
	abiertos = []
	monkeypatch.setattr(mod_editor, "abrir", lambda padre, proveedor, ruta, *a, **k: abiertos.append(ruta))
	monkeypatch.setattr(mod_nombre, "pedir_nombre", lambda *a, **k: "nuevo.txt")
	acciones.crear_archivo(ctx)
	assert procesar_eventos(lambda: abiertos, 5)
	assert (tmp_path / "nuevo.txt").read_bytes() == b""
	assert abiertos == [str(tmp_path / "nuevo.txt")]
	assert panel.ir_a == ["nuevo.txt"]
	# Si ya existe, se abre sin vaciarlo.
	(tmp_path / "nuevo.txt").write_bytes(b"contenido")
	acciones.crear_archivo(ctx)
	assert procesar_eventos(lambda: len(abiertos) == 2, 5)
	assert (tmp_path / "nuevo.txt").read_bytes() == b"contenido"
