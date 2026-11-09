# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque NV: constructor y código del complemento de zCommander para NVDA (diseño 2.0, 10.16 y 18.2).

Comprueban, sin NVDA y sin instalar nada:

- el constructor (``tools/construir_complemento.py``): paquete en
  ``data/bin/nvda/zCommander-<versión>.nvda-addon`` (en ``tmp_path``),
  manifiesto válido con ``minimumNVDAVersion = 2026.1`` y la versión de
  zCommander, traducciones compiladas, documentación en HTML y nada de
  ``__pycache__``, ``.pyc`` ni ``.po``;
- el código del complemento: compila, solo importa lo que NVDA trae y cada
  ``_("...")`` tiene traducción;
- la lógica del appModule con una NVDA simulada (``tests/nv_nvda_falso.py``):
  clase superpuesta, movimiento silencioso con una propiedad de ventana REAL
  puesta por ``app/ui/senales_nvda.py``, decodificación de
  ``zCommander.OrdenLectura`` (``[0, 3, 1]`` y 15 columnas), nombre de la fila
  en ese orden, lectura de celdas largas contra una lista virtual REAL de
  wxPython y el gesto NVDA+Mayúsculas+J.

Que NVDA lo anuncie de verdad se comprueba a mano con NVDA real.
"""

from __future__ import annotations

import ast
import ctypes
import gettext
import io
import py_compile
import shutil
import sys
import types
import zipfile
from ctypes import wintypes
from pathlib import Path

import pytest

from app.core.version import APP_VERSION, TITULAR
from app.ui import senales_nvda
from tests import nv_nvda_falso

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="NVDA y su complemento son de Windows")

RAIZ = nv_nvda_falso.RAIZ
CARPETA = nv_nvda_falso.CARPETA_COMPLEMENTO
MODULOS = sorted(p for p in CARPETA.rglob("*.py") if "__pycache__" not in p.parts)
constructor = nv_nvda_falso.cargar_modulo("construir_complemento_nv", RAIZ / "tools" / "construir_complemento.py")
Datos = constructor.Datos
ErrorComplemento = constructor.ErrorComplemento


# ════════════════════════════════════════════════════════════════════════════
# Constructor
# ════════════════════════════════════════════════════════════════════════════

def _datos(**cambios):
	valores = {"nombre": "zCommander", "version": "2.3.4", "nvda_minima": "2026.1", "nvda_probada": "2026.1",
		"autor": "Persona de prueba", "url": "", "cambios": ""}
	valores.update(cambios)
	return Datos(**valores)


@pytest.fixture
def origen(tmp_path):
	"""Copia de nvda_addon/ con cachés y restos de editor que NO deben viajar."""
	copia = tmp_path / "nvda_addon"
	shutil.copytree(RAIZ / "nvda_addon", copia, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.mo"))
	cache = copia / "addon" / "appModules" / "__pycache__"
	cache.mkdir()
	(cache / "zcommander.cpython-313.pyc").write_bytes(b"basura")
	(copia / "addon" / "appModules" / "viejo.pyc").write_bytes(b"basura")
	(copia / "addon" / "Thumbs.db").write_bytes(b"basura")
	return copia


def _leer(ruta: Path, interno: str) -> str:
	with zipfile.ZipFile(ruta) as zip_:
		return zip_.read(interno).decode("utf-8")


def test_paquete_por_defecto_en_data_bin_nvda_con_la_version_de_zcommander(origen, tmp_path):
	"""18.2: el paquete tiene minimumNVDAVersion = 2026.1 y la versión de zCommander."""
	destino = tmp_path / "data" / "bin" / "nvda"
	informe = constructor.construir(origen, destino)
	assert informe.ruta == destino / f"zCommander-{APP_VERSION}.nvda-addon"
	assert constructor.DESTINO == RAIZ / "data" / "bin" / "nvda"
	campos = constructor.leer_manifiesto(_leer(informe.ruta, "manifest.ini"))
	assert campos["name"] == "zCommander"
	assert campos["version"] == APP_VERSION
	assert campos["minimumNVDAVersion"] == "2026.1"
	assert campos["author"] == TITULAR
	assert campos["docFileName"] == "readme.html"
	assert constructor.validar_manifiesto(campos) == []
	assert not list(destino.glob("*.tmp")), "Quedó un temporal a medias"


def test_contenido_y_sin_restos(origen, tmp_path):
	informe = constructor.construir(origen, tmp_path, _datos())
	with zipfile.ZipFile(informe.ruta) as zip_:
		nombres = set(zip_.namelist())
		assert zip_.testzip() is None
	assert nombres == {
		"manifest.ini", "appModules/zcommander.py", "locale/es/LC_MESSAGES/nvda.mo", "locale/es/manifest.ini",
		"doc/es/readme.html",
	}


def test_borra_los_paquetes_de_otras_versiones(origen, tmp_path):
	(tmp_path / "zCommander-0.9.0.nvda-addon").write_bytes(b"viejo")
	(tmp_path / "otro-1.0.nvda-addon").write_bytes(b"ajeno")
	informe = constructor.construir(origen, tmp_path, _datos())
	assert sorted(p.name for p in tmp_path.glob("*.nvda-addon")) == ["otro-1.0.nvda-addon", informe.ruta.name]


def test_no_escribe_en_la_fuente(origen, tmp_path):
	antes = sorted(p.relative_to(origen).as_posix() for p in origen.rglob("*"))
	constructor.construir(origen, tmp_path / "salida", _datos())
	assert sorted(p.relative_to(origen).as_posix() for p in origen.rglob("*")) == antes


def test_manifiesto_traducido_y_opcionales(origen, tmp_path):
	informe = constructor.construir(origen, tmp_path, _datos())
	campos = constructor.leer_manifiesto(_leer(informe.ruta, "manifest.ini"))
	assert "url" not in campos and "changelog" not in campos
	traducido = constructor.leer_manifiesto(_leer(informe.ruta, "locale/es/manifest.ini"))
	assert "mejor lectura" in traducido["summary"]
	assert set(traducido) <= {"summary", "description", "changelog"}


@pytest.mark.parametrize(
	("cambio", "mensaje"),
	[
		({"version": "2.0b1"}, "version"),
		({"nvda_minima": "2026.10"}, "minimumNVDAVersion"),
		({"nvda_minima": "2026.2", "nvda_probada": "2026.1"}, "no puede ser mayor"),
		({"nombre": "z Commander"}, "name"),
		({"url": "http://ejemplo.es"}, "https"),
		({"autor": 'Nombre "apodo"'}, "comillas"),
	],
)
def test_manifiesto_invalido(origen, tmp_path, cambio, mensaje):
	with pytest.raises(ErrorComplemento, match=mensaje):
		constructor.construir(origen, tmp_path, _datos(**cambio))
	assert not list(tmp_path.glob("*.nvda-addon"))


def test_manifiesto_con_configobj_si_esta_disponible(origen, tmp_path):
	"""NVDA lee el manifiesto con configobj: si está instalado, se comprueba con él."""
	configobj = pytest.importorskip("configobj")
	informe = constructor.construir(origen, tmp_path, _datos())
	datos = configobj.ConfigObj(io.StringIO(_leer(informe.ruta, "manifest.ini")), encoding="utf-8")
	assert datos["name"] == "zCommander"


def test_mo_del_paquete_traduce(origen, tmp_path):
	informe = constructor.construir(origen, tmp_path, _datos())
	with zipfile.ZipFile(informe.ruta) as zip_:
		traduccion = gettext.GNUTranslations(io.BytesIO(zip_.read("locale/es/LC_MESSAGES/nvda.mo")))
	assert traduccion.gettext("Not in a list") == "No estás en una lista"


def test_readme_html_navegable(origen, tmp_path):
	pagina = _leer(constructor.construir(origen, tmp_path, _datos()).ruta, "doc/es/readme.html")
	assert pagina.startswith("<!DOCTYPE html>") and '<html lang="es">' in pagina
	assert "<h1>" in pagina and "<h2>" in pagina and "<ul>" in pagina


def test_readme_con_markdown_si_esta(origen, tmp_path, monkeypatch):
	falso = types.ModuleType("markdown")
	falso.markdown = lambda texto, extensions=None: "<p>CONVERTIDO CON MARKDOWN</p>"
	monkeypatch.setitem(sys.modules, "markdown", falso)
	informe = constructor.construir(origen, tmp_path, _datos())
	assert "CONVERTIDO CON MARKDOWN" in _leer(informe.ruta, "doc/es/readme.html")


def test_po_complejo(tmp_path):
	po = tmp_path / "nvda.po"
	po.write_text(
		'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
		'#, fuzzy\nmsgid "Dudosa"\nmsgstr "No"\n\n'
		'msgctxt "menú"\nmsgid "Open"\nmsgstr "Abrir"\n\n'
		'msgid "{0} item"\nmsgid_plural "{0} items"\nmsgstr[0] "{0} elemento"\nmsgstr[1] "{0} elementos"\n',
		encoding="utf-8",
	)
	catalogo = constructor.leer_po(po)
	assert "Dudosa" not in catalogo
	traduccion = gettext.GNUTranslations(io.BytesIO(constructor.compilar_mo(catalogo)))
	assert traduccion.pgettext("menú", "Open") == "Abrir"
	assert traduccion.ngettext("{0} item", "{0} items", 3) == "{0} elementos"


def test_lee_version_y_titular_de_la_app(tmp_path):
	(tmp_path / "app" / "core").mkdir(parents=True)
	(tmp_path / "app" / "core" / "version.py").write_text('APP_VERSION = "3.4.5"\nTITULAR = "Ana"\n', encoding="utf-8")
	assert constructor.leer_version_app(tmp_path) == "3.4.5"
	assert constructor.leer_titular_app(tmp_path) == "Ana"
	assert constructor.leer_titular_app(tmp_path / "no-existe") == constructor.AUTOR_POR_DEFECTO


def test_main(origen, tmp_path, capsys):
	assert constructor.main(["--origen", str(origen), "--destino", str(tmp_path), "--version", "2.0"]) == 0
	assert "Complemento generado" in capsys.readouterr().out
	assert (tmp_path / "zCommander-2.0.nvda-addon").is_file()
	assert constructor.main(["--origen", str(origen), "--destino", str(tmp_path), "--version", "dos"]) == 1
	assert "ERROR" in capsys.readouterr().err


# ════════════════════════════════════════════════════════════════════════════
# Estructura del código del complemento
# ════════════════════════════════════════════════════════════════════════════

#: Módulos de NVDA que un complemento suele importar.
MODULOS_NVDA = {
	"addonHandler", "api", "appModuleHandler", "config", "controlTypes", "globalPluginHandler", "logHandler",
	"NVDAObjects", "scriptHandler", "speech", "ui", "watchdog", "winBindings", "wx",
}
#: Biblioteca estándar que NVDA 2026.3 NO incluye (comprobado en su library.zip).
AUSENTES_EN_NVDA = {
	"cProfile", "compileall", "curses", "dbm", "ensurepip", "graphlib", "imaplib", "mailbox", "optparse",
	"profile", "pstats", "readline", "sched", "shelve", "smtplib", "sqlite3", "timeit", "tkinter", "zoneinfo",
}
CARPETA_NVDA = Path(r"C:\Program Files\NVDA")


def _importaciones(ruta: Path) -> set[str]:
	arbol = ast.parse(ruta.read_text(encoding="utf-8"))
	nombres: set[str] = set()
	for nodo in ast.walk(arbol):
		if isinstance(nodo, ast.Import):
			nombres.update(alias.name.split(".")[0] for alias in nodo.names)
		elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
			nombres.add(nodo.module.split(".")[0])
	return nombres


def _cadenas_traducibles(ruta: Path) -> set[str]:
	arbol = ast.parse(ruta.read_text(encoding="utf-8"))
	return {
		nodo.args[0].value
		for nodo in ast.walk(arbol)
		if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id == "_"
		and nodo.args and isinstance(nodo.args[0], ast.Constant) and isinstance(nodo.args[0].value, str)
	}


def test_appmodule_con_el_nombre_del_ejecutable():
	from app.core.version import ID_APLICACION

	assert nv_nvda_falso.APPMODULE.is_file()
	assert nv_nvda_falso.APPMODULE.stem == ID_APLICACION.lower().replace(".", "_")


@pytest.mark.parametrize("ruta", MODULOS, ids=lambda p: p.relative_to(CARPETA).as_posix())
def test_compila(ruta, tmp_path):
	py_compile.compile(str(ruta), cfile=str(tmp_path / "modulo.pyc"), doraise=True)


@pytest.mark.parametrize("ruta", MODULOS, ids=lambda p: p.relative_to(CARPETA).as_posix())
def test_importa_solo_lo_que_hay_en_nvda(ruta):
	for nombre in _importaciones(ruta):
		if nombre in MODULOS_NVDA:
			continue
		assert nombre in sys.stdlib_module_names, f"{ruta.name} importa «{nombre}», que NVDA no trae"
		assert nombre not in AUSENTES_EN_NVDA, f"{ruta.name} importa «{nombre}»: NVDA no lo incluye"


@pytest.mark.skipif(not (CARPETA_NVDA / "library.zip").is_file(), reason="NVDA no está instalado en este equipo")
@pytest.mark.parametrize("ruta", MODULOS, ids=lambda p: p.relative_to(CARPETA).as_posix())
def test_importaciones_existen_en_el_nvda_instalado(ruta):
	"""Contrasta con library.zip del NVDA instalado (solo lee la lista de nombres)."""
	with zipfile.ZipFile(CARPETA_NVDA / "library.zip") as biblioteca:
		disponibles = {n.split("/")[0].removesuffix(".pyc") for n in biblioteca.namelist()}
	disponibles |= {p.name.split(".")[0] for p in CARPETA_NVDA.glob("*.pyd")}
	disponibles |= set(sys.builtin_module_names)
	for nombre in _importaciones(ruta):
		assert nombre in disponibles, f"{ruta.name} importa «{nombre}», que no está en el NVDA instalado"


def test_cada_cadena_tiene_traduccion_al_espanol():
	catalogo = constructor.leer_po(CARPETA / "locale" / "es" / "LC_MESSAGES" / "nvda.po")
	for ruta in MODULOS:
		for cadena in _cadenas_traducibles(ruta):
			assert catalogo.get(cadena), f"Falta traducir en nvda.po: {cadena!r} ({ruta.name})"


# ════════════════════════════════════════════════════════════════════════════
# Lógica del appModule (NVDA simulada)
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def modulo(monkeypatch):
	modulo_app, estado = nv_nvda_falso.cargar_modulo_de_aplicacion(monkeypatch)
	modulo_app.estado_pruebas = estado
	return modulo_app


class _Objeto:
	def __init__(self, clase_ventana):
		self.windowClassName = clase_ventana


def test_mismas_propiedades_en_zcommander_y_en_el_complemento(modulo):
	assert modulo.PROPIEDAD_SILENCIO == senales_nvda.PROPIEDAD_SILENCIO == "zCommander.MovimientoSilencioso"
	assert modulo.PROPIEDAD_LECTURA == senales_nvda.PROPIEDAD_LECTURA == "zCommander.OrdenLectura"
	assert modulo.MAX_COLUMNAS == senales_nvda.MAX_COLUMNAS == 15
	assert modulo.TERMINADOR == senales_nvda.TERMINADOR == 0xF


def test_clase_superpuesta_solo_en_listas(modulo):
	lista_nvda = sys.modules["NVDAObjects.IAccessible.sysListView32"].ListItem
	app = modulo.AppModule()
	clases = [lista_nvda]
	app.chooseNVDAObjectOverlayClasses(_Objeto("SysListView32"), clases)
	assert clases[0] is modulo.ElementoListaZC
	otras = [object]
	app.chooseNVDAObjectOverlayClasses(_Objeto("Edit"), otras)
	assert otras == [object]


def test_gesto_declarado(modulo):
	guion = modulo.AppModule.script_leerFilaCompleta
	assert guion.gestures == ["kb:NVDA+shift+j"]
	assert guion.__doc__, "El gesto necesita descripción para «Gestos de entrada»"
	assert modulo.AppModule.scriptCategory == "zCommander"


@pytest.mark.parametrize(
	("valor", "ahora", "esperado"),
	[
		(0, 1000, False),  # sin marca
		(1000, 1000, True),
		(1000, 1500, True),  # justo en el límite de 500 ms
		(1000, 1501, False),  # caducada: la navegación vuelve a sonar
		(2000, 1000, False),  # marca del futuro: no silencia
		(2**40, 2**40 + 10, True),  # GetTickCount64 tras muchos días
	],
)
def test_marca_reciente(modulo, valor, ahora, esperado):
	assert modulo.marca_reciente(valor, ahora) is esperado


# ── Orden de lectura (10.5) ─────────────────────────────────────────────────

def test_decodifica_el_orden_que_publica_zcommander(modulo):
	"""18.2: el appModule decodifica lo que codifica senales_nvda.py para [0, 3, 1] y para 15 columnas."""
	assert modulo.decodificar_orden(senales_nvda.codificar_orden([0, 3, 1])) == [0, 3, 1]
	quince = [14, 0, 13, 1, 12, 2, 11, 3, 10, 4, 9, 5, 8, 6, 7]
	valor = senales_nvda.codificar_orden(quince)
	assert valor >> 60 == 0xF  # el terminador ocupa los 4 bits más altos
	assert modulo.decodificar_orden(valor) == quince
	assert modulo.decodificar_orden(senales_nvda.codificar_orden(list(range(15)))) == list(range(15))


@pytest.mark.parametrize(
	("valor", "esperado"),
	[
		(0, None),  # sin propiedad: NVDA lee como siempre
		(0xF, []),  # lista vacía: todas, en el orden de la lista
		(0x1234, None),  # sin terminador
		(0x1F30, None),  # bits detrás del terminador: no viene de zCommander
		(0xFFFFFFFFFFFFFFFF, None),  # terminador en la primera posición y bits detrás
	],
)
def test_decodifica_valores_raros(modulo, valor, esperado):
	assert modulo.decodificar_orden(valor) == esperado


class _FilaFalsa:
	"""Contenido y cabeceras de una fila de cuatro columnas (índices de la lista, base 0)."""

	CONTENIDO = {0: "informe.txt", 1: "3 KB", 2: "", 3: "C:\\Documentos\\informe.txt"}
	CABECERAS = {0: "Nombre", 1: "Tamaño", 2: "Tipo", 3: "Ruta"}
	childCount = 4

	def _getColumnContentRaw(self, index):  # noqa: N802 - API de NVDA
		return self.CONTENIDO[index] or None

	def _getColumnHeaderRaw(self, index):  # noqa: N802 - API de NVDA
		return self.CABECERAS[index]


def _elemento_con_orden(modulo, ventana):
	clase = type("FilaZC", (_FilaFalsa, modulo.ElementoListaZC), {})
	elemento = clase()
	elemento.windowHandle = ventana
	return elemento


def test_nombre_en_el_orden_publicado_con_ventana_real(modulo, ventana):
	elemento = _elemento_con_orden(modulo, ventana)
	assert elemento.name == "NOMBRE DE NVDA"  # sin propiedad: el nombre de NVDA
	senales_nvda.publicar_orden_lectura(ventana, [3, 0, 2, 1])
	assert modulo.orden_lectura(ventana) == [3, 0, 2, 1]
	# La primera columna sin cabecera, como NVDA; la vacía no se lee.
	assert elemento.name == "C:\\Documentos\\informe.txt; Nombre: informe.txt; Tamaño: 3 KB"


def test_nombre_sin_cabeceras_si_nvda_no_las_lee(modulo, ventana):
	modulo.estado_pruebas.conf["documentFormatting"]["reportTableHeaders"] = nv_nvda_falso.ReportTableHeaders.OFF
	senales_nvda.publicar_orden_lectura(ventana, [1, 0])
	assert _elemento_con_orden(modulo, ventana).name == "3 KB; informe.txt"


def test_orden_con_indices_de_mas_y_vacio(modulo, ventana):
	elemento = _elemento_con_orden(modulo, ventana)
	senales_nvda.publicar_orden_lectura(ventana, [9, 1])  # la columna 9 no existe en esta lista
	assert elemento.name == "3 KB"
	senales_nvda.publicar_orden_lectura(ventana, [])
	assert elemento.name == "NOMBRE DE NVDA"


def test_componer_nombre_quita_marcas_de_direccion(modulo):
	assert modulo.componer_nombre([(None, "\u200eabc\u200f"), ("Tamaño", "1 KB")], True) == "abc; Tamaño: 1 KB"


def test_si_falla_el_orden_vuelve_al_nombre_de_nvda(modulo, ventana):
	class Rota(_FilaFalsa):
		def _getColumnContentRaw(self, index):  # noqa: N802 - API de NVDA
			raise OSError("lista cerrada")

	senales_nvda.publicar_orden_lectura(ventana, [0])
	elemento = type("FilaRota", (Rota, modulo.ElementoListaZC), {})()
	elemento.windowHandle = ventana
	assert elemento.name == "NOMBRE DE NVDA"
	assert any(nivel == "debugWarning" for nivel, _m in modulo.estado_pruebas.registro.mensajes)


# ── Movimiento silencioso con una ventana real ──────────────────────────────

@pytest.fixture
def ventana():
	"""Ventana de solo mensajes (HWND_MESSAGE): real, invisible y sin wx."""
	user32 = ctypes.WinDLL("user32", use_last_error=True)
	crear = user32.CreateWindowExW
	crear.argtypes = (
		wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
		ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
	)
	crear.restype = wintypes.HWND
	destruir = user32.DestroyWindow
	destruir.argtypes = (wintypes.HWND,)
	quitar = user32.RemovePropW
	quitar.argtypes = (wintypes.HWND, wintypes.LPCWSTR)
	quitar.restype = wintypes.HANDLE
	hwnd = crear(0, "STATIC", "prueba", 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)
	assert hwnd, f"CreateWindowExW falló: {ctypes.get_last_error()}"
	yield hwnd
	for propiedad in (senales_nvda.PROPIEDAD_SILENCIO, senales_nvda.PROPIEDAD_LECTURA):
		quitar(hwnd, propiedad)
	destruir(hwnd)


def test_movimiento_silencioso_con_ventana_real(modulo, ventana):
	senales_nvda.configurar(True)
	elemento = modulo.ElementoListaZC()
	elemento.windowHandle = ventana
	assert modulo.movimiento_silencioso_activo(ventana) is False
	assert elemento.shouldAllowIAccessibleFocusEvent is True
	senales_nvda.marcar_movimiento_silencioso(ventana)
	assert modulo.movimiento_silencioso_activo(ventana) is True
	assert elemento.shouldAllowIAccessibleFocusEvent is False


def test_marca_antigua_no_silencia(modulo, ventana):
	"""Una marca olvidada caduca: nunca deja muda la navegación."""
	kernel32 = ctypes.WinDLL("kernel32")
	kernel32.GetTickCount64.restype = ctypes.c_ulonglong
	senales_nvda._fijar_propiedad(ventana, senales_nvda.PROPIEDAD_SILENCIO, kernel32.GetTickCount64() - 5000)
	assert modulo.movimiento_silencioso_activo(ventana) is False


def test_sin_ventana_no_silencia(modulo):
	elemento = modulo.ElementoListaZC()
	elemento.windowHandle = 0
	assert elemento.shouldAllowIAccessibleFocusEvent is True


# ── Lectura de celdas contra una lista virtual real de wxPython ─────────────

LARGO = "C:\\" + "carpeta\\" * 370 + "FIN-CELDA0"


@pytest.fixture
def lista_wx(app_wx):
	import wx

	class ListaVirtual(wx.ListCtrl):
		def __init__(self, padre):
			super().__init__(padre, style=wx.LC_REPORT | wx.LC_VIRTUAL)
			self.InsertColumn(0, "Ruta")
			self.InsertColumn(1, "Nombre")
			self.SetItemCount(2)

		def OnGetItemText(self, fila, columna):  # noqa: N802 - API de wx
			return LARGO if columna == 0 else f"archivo {fila}"

	marco = wx.Frame(None)
	lista = ListaVirtual(marco)
	yield lista
	marco.Destroy()


def _elemento_de(modulo, lista, fila=0):
	"""Elemento como el que crearía NVDA para la fila (IAccessibleChildID es base 1)."""
	kernel32 = ctypes.WinDLL("kernel32")
	kernel32.GetCurrentProcess.restype = wintypes.HANDLE
	elemento = modulo.ElementoListaZC()
	elemento.processHandle = kernel32.GetCurrentProcess()
	elemento.windowHandle = lista.GetHandle()
	elemento.IAccessibleChildID = fila + 1
	return elemento


def test_celda_larga_se_lee_completa(modulo, lista_wx):
	assert len(LARGO) > 511
	elemento = _elemento_de(modulo, lista_wx)
	assert elemento._getColumnContentRaw(0) == LARGO
	assert elemento._getColumnContentRaw(1) == "archivo 0"
	assert _elemento_de(modulo, lista_wx, 1)._getColumnContentRaw(1) == "archivo 1"


def test_con_el_bufer_de_nvda_se_corta(modulo, lista_wx):
	"""Demuestra el problema: con 512 caracteres (CBEMAXSTRLEN) se leen 511."""
	assert len(modulo.leer_celda_completa(_elemento_de(modulo, lista_wx), 0, maximo=512)) == 511


def test_si_falla_vuelve_a_la_lectura_de_nvda(modulo):
	elemento = modulo.ElementoListaZC()
	elemento.processHandle = None  # VirtualAllocEx fallará
	elemento.windowHandle = 0
	elemento.IAccessibleChildID = 1
	assert elemento._getColumnContentRaw(0) == "ORIGINAL"
	assert any(nivel == "debugWarning" for nivel, _m in modulo.estado_pruebas.registro.mensajes)


# ── Gesto NVDA+Mayúsculas+J ─────────────────────────────────────────────────

class _Foco:
	childCount = 2
	name = "informe.txt; 3 KB"

	def _getColumnHeader(self, columna):  # noqa: N802 - API de NVDA
		return {1: "Nombre", 2: "Tamaño"}[columna]

	def _getColumnContent(self, columna):  # noqa: N802 - API de NVDA
		return {1: "informe.txt", 2: " "}[columna]


def _foco_lista():
	lista_nvda = sys.modules["NVDAObjects.IAccessible.sysListView32"].ListItem
	return type("FocoLista", (_Foco, lista_nvda), {})()


def test_gesto_lee_la_fila_con_cabeceras(modulo):
	estado = modulo.estado_pruebas
	estado.foco = _foco_lista()
	modulo.AppModule().script_leerFilaCompleta(None)
	assert estado.dichos == ["Nombre: informe.txt. Tamaño: blank"]


def test_gesto_dos_veces_abre_ventana(modulo):
	estado = modulo.estado_pruebas
	estado.foco = _foco_lista()
	estado.repeticiones = 1
	modulo.AppModule().script_leerFilaCompleta(None)
	assert estado.ventanas == [("Nombre: informe.txt. Tamaño: blank", "Full row")]


def test_gesto_fuera_de_lista(modulo):
	estado = modulo.estado_pruebas
	estado.foco = object()
	modulo.AppModule().script_leerFilaCompleta(None)
	assert estado.dichos == ["Not in a list"]


def test_gesto_en_espanol(monkeypatch, tmp_path):
	"""Con el nvda.mo compilado, lo que se dice sale en español."""
	catalogo = constructor.leer_po(CARPETA / "locale" / "es" / "LC_MESSAGES" / "nvda.po")
	traduccion = gettext.GNUTranslations(io.BytesIO(constructor.compilar_mo(catalogo)))
	modulo_app, estado = nv_nvda_falso.cargar_modulo_de_aplicacion(monkeypatch, traduccion.gettext)
	estado.foco = _foco_lista()
	modulo_app.AppModule().script_leerFilaCompleta(None)
	assert estado.dichos == ["Nombre: informe.txt. Tamaño: vacío"]


def test_se_carga_desde_el_scratchpad(monkeypatch):
	"""Fuera de un complemento, initTranslation falla; el módulo debe cargar igualmente."""
	modulo_app, estado = nv_nvda_falso.cargar_modulo_de_aplicacion(monkeypatch, fuera_de_complemento=True)
	estado.foco = object()
	modulo_app.AppModule().script_leerFilaCompleta(None)
	assert estado.dichos == ["Not in a list"]
	assert any("scratchpad" in mensaje for _nivel, mensaje in estado.registro.mensajes)
