# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de la revisión de teclado por pantalla (PLANTILLA del agente «accesibilidad-wx»).

Crean ventanas SIN mostrarlas. Comprueban lo que se puede deducir de la
estructura de la ventana (etiquetas, letras de acceso, atajos), no lo que
dice el lector de pantalla.
"""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from app.ui.accesibilidad import revision_teclado as rt  # noqa: E402
from app.ui.accesibilidad.dialogos import crear_botonera  # noqa: E402
from app.ui.accesibilidad.lista import ListaAccesible  # noqa: E402
from app.ui.accesibilidad.nombres import crear_campo  # noqa: E402
from app.ui.accesibilidad.teclado import instalar_atajos  # noqa: E402

_APLICACION_WX = None


@pytest.fixture(scope="module")
def app():
	"""La wx.App de la sesión: se reutiliza la que exista y NUNCA se destruye."""
	global _APLICACION_WX
	_APLICACION_WX = wx.GetApp() or wx.App(False)
	return _APLICACION_WX


@pytest.fixture
def marco(app):
	ventana = wx.Frame(None)
	yield ventana
	ventana.Destroy()


@pytest.fixture
def dialogo(app):
	ventana = wx.Dialog(None)
	yield ventana
	ventana.Destroy()


def _codigos(problemas):
	return sorted(p.codigo for p in problemas)


def _barra(marco, *menus):
	"""menus: (titulo, [etiquetas de elementos])."""
	barra = wx.MenuBar()
	for titulo, elementos in menus:
		menu = wx.Menu()
		for etiqueta in elementos:
			menu.Append(wx.ID_ANY, etiqueta)
		barra.Append(menu, titulo)
	marco.SetMenuBar(barra)
	return barra


# --- Funciones puras ---------------------------------------------------------

@pytest.mark.parametrize(("etiqueta", "letra"), [
	("&Guardar", "g"), ("A&plicar", "p"), ("Pan && vino", None), ("Pan && &vino", "v"),
	("Sin letra", None), ("&Abrir...\tCtrl+O", "a"), ("Final&", None), ("&Índice", "í"),
])
def test_letra_de_acceso(etiqueta, letra):
	assert rt.letra_de_acceso(etiqueta) == letra


@pytest.mark.parametrize(("texto", "normalizado"), [
	("ctrl+shift+s", "Ctrl+Mayús+S"), ("Mayús+Ctrl+S", "Ctrl+Mayús+S"), ("alt+f4", "Alt+F4"),
	("Ctrl++", "Ctrl++"), ("Ctrl+Insert", "Ctrl+Insert"), ("Shift + F10", "Mayús+F10"), ("esc", "Escape"),
])
def test_normalizar_atajo(texto, normalizado):
	assert rt.normalizar_atajo(texto) == normalizado


def test_atajo_de_entrada():
	assert rt.atajo_de_entrada(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("s")) == "Ctrl+Mayús+S"
	assert rt.atajo_de_entrada(wx.ACCEL_NORMAL, wx.WXK_F5) == "F5"
	assert rt.atajo_de_entrada(wx.ACCEL_ALT, wx.WXK_SPACE) == "Alt+Espacio"


# --- Pantallas correctas -----------------------------------------------------

def test_dialogo_correcto_sin_problemas(dialogo):
	panel = wx.Panel(dialogo)
	crear_campo(panel, "&Nombre:", wx.TextCtrl)
	crear_campo(panel, "&Tipo:", wx.Choice, choices=["Uno", "Dos"])
	wx.CheckBox(panel, label="&Recordar")
	crear_botonera(panel, wx.OK | wx.CANCEL)
	problemas = rt.revisar_teclado(dialogo)
	assert problemas == [], rt.informe(problemas)
	rt.afirmar_teclado_correcto(dialogo)


def test_marco_con_menus_y_atajos_correctos(marco):
	barra = wx.MenuBar()
	archivo = wx.Menu()
	guardar = archivo.Append(wx.ID_SAVE, "&Guardar\tCtrl+S")
	archivo.Append(wx.ID_EXIT, "&Salir")
	barra.Append(archivo, "&Archivo")
	marco.SetMenuBar(barra)
	panel = wx.Panel(marco)
	crear_campo(panel, "&Buscar:", wx.TextCtrl)
	wx.Button(panel, label="&Filtrar")
	instalar_atajos(marco, [(wx.ACCEL_NORMAL, wx.WXK_F5, lambda: None)])
	herramientas = marco.CreateToolBar()
	herramientas.AddTool(guardar.GetId(), "Guardar", wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR))
	herramientas.Realize()
	problemas = rt.revisar_teclado(marco, teclas_propias=["Ctrl+F"])
	assert problemas == [], rt.informe(problemas)


# --- Etiquetas -----------------------------------------------------------------

def test_campo_sin_etiqueta_y_etiqueta_tardia(dialogo):
	panel = wx.Panel(dialogo)
	wx.TextCtrl(panel)  # sin etiqueta
	wx.Choice(panel)
	wx.StaticText(panel, label="&Tipo:")  # creada DESPUÉS del desplegable
	problemas = rt.revisar_teclado(dialogo)
	assert _codigos(problemas) == [rt.LETRA_SIN_DESTINO, rt.SIN_ETIQUETA, rt.SIN_ETIQUETA]


def test_etiqueta_sin_letra_y_boton_sin_letra(dialogo):
	panel = wx.Panel(dialogo)
	crear_campo(panel, "Nombre:", wx.TextCtrl)
	wx.Button(panel, label="Guardar")
	problemas = rt.revisar_teclado(dialogo)
	assert _codigos(problemas) == [rt.SIN_LETRA, rt.SIN_LETRA]
	assert "Nombre" in problemas[0].mensaje
	assert "Guardar" in problemas[1].mensaje


def test_controles_ocultos_no_cuentan(dialogo):
	panel = wx.Panel(dialogo)
	wx.Button(panel, label="&Guardar")
	wx.Button(panel, label="&Generar").Hide()
	assert rt.revisar_teclado(dialogo) == []


# --- Letras repetidas ----------------------------------------------------------

def test_letra_repetida_entre_etiqueta_y_boton(dialogo):
	panel = wx.Panel(dialogo)
	crear_campo(panel, "&Categoría:", wx.Choice)
	crear_botonera(panel, wx.OK | wx.CANCEL)  # «&Cancelar» también usa la C
	problemas = rt.revisar_teclado(dialogo)
	assert _codigos(problemas) == [rt.LETRA_REPETIDA]
	assert "Alt+C" in problemas[0].mensaje
	assert "Categoría" in problemas[0].mensaje and "Cancelar" in problemas[0].mensaje


def test_letra_repetida_en_paneles_anidados_y_grupos(dialogo):
	panel = wx.Panel(dialogo)
	caja = wx.StaticBox(panel, label="&Opciones")
	wx.CheckBox(caja, label="&Ocultar")
	problemas = rt.revisar_teclado(dialogo)
	assert _codigos(problemas) == [rt.LETRA_REPETIDA]


def test_pestanas_distintas_no_chocan_pero_con_lo_comun_si(dialogo):
	panel = wx.Panel(dialogo)
	cuaderno = wx.Notebook(panel)
	general, avanzado = wx.Panel(cuaderno), wx.Panel(cuaderno)
	cuaderno.AddPage(general, "General")
	cuaderno.AddPage(avanzado, "Avanzado")
	crear_campo(general, "&Nombre:", wx.TextCtrl)
	crear_campo(avanzado, "&Nivel:", wx.SpinCtrl)  # otra página: no choca con «&Nombre»
	wx.CheckBox(avanzado, label="&Aceptar cookies")  # choca con el botón común «&Aceptar»
	crear_botonera(panel, wx.OK | wx.CANCEL)
	problemas = rt.revisar_teclado(dialogo)
	assert _codigos(problemas) == [rt.LETRA_REPETIDA]
	assert "Aceptar cookies" in problemas[0].mensaje


def test_opciones_de_un_radiobox(dialogo):
	panel = wx.Panel(dialogo)
	wx.RadioBox(panel, label="&Modo", choices=["&Rápido", "Lento"])
	wx.Button(panel, label="&Reiniciar")
	problemas = rt.revisar_teclado(dialogo)
	assert _codigos(problemas) == [rt.LETRA_REPETIDA, rt.SIN_LETRA]


def test_letra_acentuada_es_aviso(dialogo):
	panel = wx.Panel(dialogo)
	wx.Button(panel, label="&Índice")
	problemas = rt.revisar_teclado(dialogo)
	assert [(p.codigo, p.aviso) for p in problemas] == [(rt.LETRA_DIFICIL, True)]
	rt.afirmar_teclado_correcto(dialogo)  # los avisos no hacen fallar por defecto
	with pytest.raises(AssertionError, match="Índice"):
		rt.afirmar_teclado_correcto(dialogo, con_avisos=True)


# --- Menús -------------------------------------------------------------------

def test_control_que_choca_con_la_barra_de_menus(marco):
	_barra(marco, ("&Archivo", ["&Salir"]), ("A&yuda", ["&Manual"]))
	panel = wx.Panel(marco)
	crear_campo(panel, "&Apellidos:", wx.TextCtrl)
	problemas = rt.revisar_teclado(marco)
	assert _codigos(problemas) == [rt.CHOCA_CON_MENU]
	assert "Archivo" in problemas[0].mensaje and "Apellidos" in problemas[0].mensaje


def test_letras_de_menu_repetidas_y_sin_letra(marco):
	_barra(marco, ("&Archivo", ["&Abrir", "&Abrir reciente", "Salir"]), ("&Ayuda", ["&Manual"]))
	problemas = rt.revisar_teclado(marco)
	assert _codigos(problemas) == [rt.LETRA_REPETIDA, rt.LETRA_REPETIDA, rt.SIN_LETRA]
	mensajes = " ".join(p.mensaje for p in problemas)
	assert "Abrir reciente" in mensajes and "Salir" in mensajes and "dos menús" in mensajes


def test_submenus_se_revisan(marco):
	barra = wx.MenuBar()
	archivo = wx.Menu()
	exportar = wx.Menu()
	exportar.Append(wx.ID_ANY, "&Texto")
	exportar.Append(wx.ID_ANY, "&Tabla")
	archivo.AppendSubMenu(exportar, "&Exportar")
	barra.Append(archivo, "&Archivo")
	marco.SetMenuBar(barra)
	problemas = rt.revisar_teclado(marco)
	assert _codigos(problemas) == [rt.LETRA_REPETIDA]
	assert "Exportar" in problemas[0].mensaje


# --- Atajos ------------------------------------------------------------------

def test_atajo_repetido_entre_menu_tabla_y_teclas_propias(marco):
	_barra(marco, ("&Archivo", ["&Guardar\tCtrl+S", "&Sincronizar\tCtrl+S"]))
	instalar_atajos(marco, [(wx.ACCEL_NORMAL, wx.WXK_F5, lambda: None)])
	problemas = rt.revisar_teclado(marco, teclas_propias=["F5"])
	assert _codigos(problemas) == [rt.ATAJO_REPETIDO, rt.ATAJO_REPETIDO]
	assert "Ctrl+S" in problemas[0].mensaje and "F5" in problemas[1].mensaje


def test_mismo_id_en_menu_y_tabla_no_es_repeticion(marco):
	barra = wx.MenuBar()
	menu = wx.Menu()
	menu.Append(wx.ID_SAVE, "&Guardar\tCtrl+S")
	barra.Append(menu, "&Archivo")
	marco.SetMenuBar(barra)
	marco._atajos_accesibles = [(wx.ACCEL_CTRL, ord("S"), wx.ID_SAVE)]
	assert rt.revisar_teclado(marco) == []


def test_atajos_reservados(marco):
	_barra(marco, ("&Archivo", ["&Historial\tCtrl+H", "&Leer\tCtrl+Insert"]))
	panel = wx.Panel(marco)
	wx.StaticText(panel, label="&Elementos:")
	ListaAccesible(panel, "Elementos", [("Nombre", 100)])
	problemas = rt.revisar_teclado(marco, teclas_propias=["Ctrl+2", "Shift+F10"])
	assert _codigos(problemas) == [rt.ATAJO_RESERVADO] * 4
	mensajes = " ".join(p.mensaje for p in problemas)
	assert "ayuda contextual" in mensajes and "lector" in mensajes and "columna" in mensajes and "contextual" in mensajes


def test_ctrl_tab_reservado_con_pestanas(dialogo):
	panel = wx.Panel(dialogo)
	cuaderno = wx.Notebook(panel)
	cuaderno.AddPage(wx.Panel(cuaderno), "Uno")
	problemas = rt.revisar_teclado(dialogo, teclas_propias=["Ctrl+Tab"])
	assert _codigos(problemas) == [rt.ATAJO_RESERVADO]


def test_alt_letra_choca_con_menu_y_con_control(marco):
	_barra(marco, ("&Archivo", ["&Nuevo\tAlt+A"]))
	panel = wx.Panel(marco)
	wx.Button(panel, label="&Borrar")
	problemas = rt.revisar_teclado(marco, teclas_propias=["Alt+B"])
	assert _codigos(problemas) == [rt.CHOCA_CON_MENU, rt.LETRA_REPETIDA]


def test_atajo_de_edicion_con_campos_es_aviso(marco):
	_barra(marco, ("&Edición", ["&Copiar\tCtrl+C"]))
	panel = wx.Panel(marco)
	crear_campo(panel, "&Nota:", wx.TextCtrl)
	problemas = rt.revisar_teclado(marco)
	assert [(p.codigo, p.aviso) for p in problemas] == [(rt.ATAJO_EDICION, True)]
	assert rt.revisar_teclado(marco, ignorar=[rt.ATAJO_EDICION]) == []


def test_boton_de_barra_de_herramientas_sin_teclado(marco):
	_barra(marco, ("&Archivo", ["&Salir"]))
	herramientas = marco.CreateToolBar()
	herramientas.AddTool(wx.NewIdRef(), "Refrescar", wx.ArtProvider.GetBitmap(wx.ART_REDO, wx.ART_TOOLBAR), shortHelp="Refrescar")
	herramientas.Realize()
	problemas = rt.revisar_teclado(marco)
	assert _codigos(problemas) == [rt.SIN_TECLADO]
	assert "Refrescar" in problemas[0].mensaje


def test_informe_legible(dialogo):
	panel = wx.Panel(dialogo)
	wx.Button(panel, label="Guardar")
	texto = rt.informe(rt.revisar_teclado(dialogo))
	assert texto.startswith("1 errores y 0 avisos de teclado:")
	assert rt.informe([]) == "Sin problemas de teclado."
	with pytest.raises(AssertionError, match="Guardar"):
		rt.afirmar_teclado_correcto(dialogo)


def test_ctrl_h_permitido_si_es_la_propia_ayuda_contextual(marco):
	_barra(marco, ("A&yuda", ["Ayuda del control &enfocado\tCtrl+H"]))
	assert rt.revisar_teclado(marco) == []


def test_mensajes_con_articulo_correcto(dialogo):
	panel = wx.Panel(dialogo)
	wx.CheckBox(panel, label="&Anunciar")
	crear_botonera(panel, wx.OK)
	(problema,) = rt.revisar_teclado(dialogo)
	assert problema.mensaje == "Alt+A está repetido: la casilla «Anunciar» y el botón «Aceptar»."
