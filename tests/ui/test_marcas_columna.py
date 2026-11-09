# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""2.0.1: marcas en la columna «Marca» (``paneles.marcas_como``) y «Decir los elementos marcados» (Alt+Mayús+M).

Con ``"columna"`` la lista no usa la selección para las marcas (siempre selección
simple): ningún lector dice «seleccionado» por ellas y la columna dice «Marcado».
Con ``"seleccion"`` (de fábrica) todo es como en la 2.0.
"""

from __future__ import annotations

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
	return base


def _crear(carpeta, monkeypatch, marcas_como: str | None = None):
	from app.core.configuracion import Configuracion
	from app.services import sesion

	destino = carpeta.parent / "destino"
	destino.mkdir(exist_ok=True)
	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {
			"izquierdo": {"pestanas": [sesion.pestana(ruta=str(carpeta))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(destino))], "actual": 0},
		},
	})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	if marcas_como is not None:
		config.establecer("paneles.marcas_como", marcas_como)
	from app.ui.ventana_principal import VentanaPrincipal

	marco = VentanaPrincipal(config)
	marco.mostrar()
	assert procesar_eventos(lambda: len(marco.izquierdo.panel_actual().entradas()) >= 5, 10)
	return marco


@pytest.fixture
def ventana(app_wx, carpeta, monkeypatch):
	marco = _crear(carpeta, monkeypatch)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


def _pasar_a_columna(ventana) -> None:
	ventana.config.establecer("paneles.marcas_como", "columna")
	panel = ventana.izquierdo.panel_actual()
	assert procesar_eventos(lambda: panel.lista_archivos.marcas_en_columna and "marca" in panel.lista_archivos.columnas, 3)


def _marcar(panel, *nombres) -> None:
	panel.marcar(lambda e: e.nombre in nombres)


def _fila(lista, nombre) -> int:
	return lista.indice_de(nombre)


def test_de_fabrica_las_marcas_son_la_seleccion(ventana):
	from app.core.configuracion import Configuracion

	assert Configuracion().obtener("paneles.marcas_como") == "seleccion"
	panel = ventana.izquierdo.panel_actual()
	lista = panel.lista_archivos
	assert not lista.marcas_en_columna and "marca" not in lista.columnas
	_marcar(panel, "uno.txt", "tres.txt")
	assert lista.multiple and lista.GetSelectedItemCount() == 2


def test_en_columna_dice_marcado_solo_en_las_marcadas_y_la_lista_es_de_seleccion_simple(ventana):
	panel = ventana.izquierdo.panel_actual()
	lista = panel.lista_archivos
	_pasar_a_columna(ventana)
	assert panel.columnas_carpeta()[0] == "marca"
	assert lista.cabecera(0) == "Marca"
	_marcar(panel, "uno.txt", "tres.txt")
	assert not lista.multiple
	assert lista.GetSelectedItemCount() == 1  # solo la fila del cursor
	assert {e.nombre for e in panel.marcadas()} == {"uno.txt", "tres.txt"}
	assert lista.texto_celda(_fila(lista, "uno.txt"), 0) == "Marcado"
	assert lista.texto_celda(_fila(lista, "tres.txt"), 0) == "Marcado"
	assert lista.texto_celda(_fila(lista, "dos.md"), 0) == ""
	assert lista.texto_celda(_fila(lista, ".."), 0) == ""
	# Las filas marcadas se distinguen a la vista (negrita).
	atributo = lista.OnGetItemAttr(_fila(lista, "uno.txt"))
	assert atributo is not None and atributo.GetFont().GetWeight() >= wx.FONTWEIGHT_BOLD
	# Desmarcar quita «Marcado».
	_marcar_valor = panel.marcar(lambda e: e.nombre == "uno.txt", False)
	assert _marcar_valor == 1
	assert lista.texto_celda(_fila(lista, "uno.txt"), 0) == ""


def test_en_columna_las_ordenes_de_marcas_funcionan_igual(ventana):
	panel = ventana.izquierdo.panel_actual()
	lista = panel.lista_archivos
	_pasar_a_columna(ventana)
	panel.enfocar()
	panel.ir_a_nombre("dos.md")
	ventana.ejecutar_orden("marcar_sin_mover")
	assert [e.nombre for e in panel.marcadas()] == ["dos.md"]
	ventana.ejecutar_orden("marcar_extension")
	ventana.ejecutar_orden("invertir_marcas")
	assert {e.nombre for e in panel.marcadas()} == {"uno.txt", "tres.txt"}
	panel.ir_a_nombre("uno.txt")
	ventana.ejecutar_orden("marcar_bajar")
	assert not lista.multiple and lista.GetSelectedItemCount() == 1
	assert "Marcados: 2" in panel.texto_resumen() or "Marcados: 3" in panel.texto_resumen()
	ventana.ejecutar_orden("desmarcar_todo")
	assert not panel.marcadas()


def test_en_columna_copiar_actua_sobre_las_marcadas(ventana, carpeta, monkeypatch):
	from app.ui.acciones import archivos

	panel = ventana.izquierdo.panel_actual()
	_pasar_a_columna(ventana)
	panel.enfocar()
	_marcar(panel, "uno.txt", "tres.txt")
	panel.ir_a_nombre("uno.txt")
	copiados: list[str] = []
	monkeypatch.setattr(archivos, "_copiar_texto", lambda texto: copiados.append(texto) or True)
	ventana.ejecutar_orden("copiar_nombres")
	assert set(copiados[0].split("\r\n")) == {"uno.txt", "tres.txt"}
	destino = carpeta.parent / "destino"
	ventana.ejecutar_orden("copiar", argumento={"destino": str(destino), "sin_dialogo": True})
	assert procesar_eventos(lambda: (destino / "uno.txt").exists() and (destino / "tres.txt").exists(), 10)
	assert not (destino / "dos.md").exists()


def test_cambiar_de_modo_en_caliente_conserva_las_marcas(ventana):
	panel = ventana.izquierdo.panel_actual()
	lista = panel.lista_archivos
	_marcar(panel, "uno.txt", "dos.md")
	assert lista.multiple and lista.GetSelectedItemCount() == 2
	_pasar_a_columna(ventana)
	assert {e.nombre for e in panel.marcadas()} == {"uno.txt", "dos.md"}
	assert not lista.multiple and lista.GetSelectedItemCount() == 1
	ventana.config.establecer("paneles.marcas_como", "seleccion")
	assert procesar_eventos(lambda: not lista.marcas_en_columna, 3)
	# La columna la añadió zCommander: se quita sola; las marcas vuelven a ser la selección.
	assert "marca" not in panel.columnas_carpeta() and "marca" not in lista.columnas
	assert {e.nombre for e in panel.marcadas()} == {"uno.txt", "dos.md"}
	assert lista.multiple and lista.GetSelectedItemCount() == 2


def test_la_columna_puesta_a_proposito_se_queda_y_se_guarda_en_la_sesion(ventana):
	panel = ventana.izquierdo.panel_actual()
	panel.aplicar_columnas(["nombre", "marca", "tamano"])
	_pasar_a_columna(ventana)
	assert panel.columnas_carpeta() == ["nombre", "marca", "tamano"]  # no se duplica ni se mueve
	assert panel.como_dict()["marca_anadida"] is False
	ventana.config.establecer("paneles.marcas_como", "seleccion")
	assert procesar_eventos(lambda: not panel.lista_archivos.marcas_en_columna, 3)
	assert panel.columnas_carpeta() == ["nombre", "marca", "tamano"]


def test_la_columna_marca_tambien_entra_en_el_orden_de_lectura(ventana):
	panel = ventana.izquierdo.panel_actual()
	panel.lectura = ["nombre", "tamano"]
	_pasar_a_columna(ventana)
	assert panel.lectura == ["marca", "nombre", "tamano"]
	ventana.config.establecer("paneles.marcas_como", "seleccion")
	assert procesar_eventos(lambda: not panel.lista_archivos.marcas_en_columna, 3)
	assert panel.lectura == ["nombre", "tamano"]


def test_arrancar_en_modo_columna(app_wx, carpeta, monkeypatch):
	marco = _crear(carpeta, monkeypatch, "columna")
	try:
		panel = marco.izquierdo.panel_actual()
		_marcar(panel, "uno.txt", "tres.txt")
		assert panel.lista_archivos.marcas_en_columna
		assert not panel.lista_archivos.multiple
	finally:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


def test_marca_esta_entre_las_columnas_disponibles():
	from app.ui.dialogos import f_columnas

	assert "marca" in f_columnas.disponibles()
	assert f_columnas.titulo_columna("marca") == "Marca"


def test_preferencia_en_la_pagina_accesibilidad_con_sus_opciones():
	from app.core.configuracion import Configuracion
	from app.core.descripciones_config import ACCESIBILIDAD, DESCRIPCIONES
	from app.ui.dialogos.f_preferencias import NOMBRES_OPCIONES

	etiqueta, ayuda, pagina = DESCRIPCIONES["paneles.marcas_como"]
	assert pagina == ACCESIBILIDAD and "&" in etiqueta and "seleccionado" in ayuda
	assert set(NOMBRES_OPCIONES["paneles.marcas_como"]) == {"seleccion", "columna"}
	config = Configuracion()
	with pytest.raises((ValueError, TypeError)):
		config.establecer("paneles.marcas_como", "otra")
	assert config.obtener("paneles.marcas_como") == "seleccion"


def test_se_guarda_en_los_perfiles_propios():
	from app.services import perfiles_propios

	assert perfiles_propios.guardable("paneles.marcas_como")


# ── Decir los elementos marcados (Alt+Mayús+M) ─────────────────────────────

def test_orden_decir_marcados_en_el_catalogo_y_en_el_menu_marcas():
	from app.ui import ordenes

	orden = ordenes.POR_ID["decir_marcados"]
	assert orden.teclas == ("Alt+Shift+M",) and orden.ambito == ordenes.GLOBAL
	assert orden.manejador == "consulta.decir_marcados"
	assert orden.ayuda == "Dice cuántos elementos hay marcados, su tamaño y sus nombres."
	assert "decir_marcados" not in ordenes.SOLO_TECLA


@pytest.mark.parametrize("modo", ["seleccion", "columna"])
def test_decir_marcados(ventana, modo):
	from app.ui.accesibilidad import voz

	if modo == "columna":
		_pasar_a_columna(ventana)
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.ir_a_nombre("dos.md")
	voz.dichos_en_prueba.clear()
	ventana.ejecutar_orden("decir_marcados")
	assert procesar_eventos(lambda: any("No hay nada marcado; el elemento de trabajo es dos.md" in d for d in voz.dichos_en_prueba), 3)
	_marcar(panel, "uno.txt", "tres.txt")
	voz.dichos_en_prueba.clear()
	ventana.ejecutar_orden("decir_marcados")
	assert procesar_eventos(lambda: any(d.startswith("2 marcados, 4 bytes: ") for d in voz.dichos_en_prueba), 3), voz.dichos_en_prueba
	dicho = next(d for d in voz.dichos_en_prueba if d.startswith("2 marcados"))
	assert set(dicho.split(": ", 1)[1].split(", ")) == {"uno.txt", "tres.txt"}


def test_decir_marcados_corta_a_veinte_nombres():
	from types import SimpleNamespace

	from app.ui.acciones import consulta

	entradas = [SimpleNamespace(nombre=f"f{i:02d}", tamano=1024, es_superior=False, es_carpeta=False) for i in range(23)]
	panel = SimpleNamespace(marcadas=lambda: entradas, cursor=lambda: None)
	texto = consulta.texto_marcados(panel)
	assert texto.startswith("23 marcados, ")
	assert texto.endswith("f19 y 3 más")
	assert "f20" not in texto
	vacio = SimpleNamespace(marcadas=lambda: [], cursor=lambda: None)
	assert consulta.texto_marcados(vacio) == "No hay nada marcado"


# ── 2.0.1 (revisión): el tamaño de lo marcado con carpetas sin calcular ───

def _entrada(nombre: str, tamano: int, carpeta: bool = False):
	from types import SimpleNamespace

	return SimpleNamespace(nombre=nombre, tamano=tamano, es_superior=False, es_carpeta=carpeta)


def _panel_falso(entradas):
	from types import SimpleNamespace

	return SimpleNamespace(marcadas=lambda: entradas, cursor=lambda: None)


def test_decir_marcados_sin_cero_bytes_por_las_carpetas():
	from app.ui.acciones import consulta

	solo_carpetas = [_entrada("fotos", -1, True), _entrada("música", -1, True)]
	assert consulta.texto_marcados(_panel_falso(solo_carpetas)) == "2 marcados (2 carpetas): fotos, música"
	mezcla = [_entrada("fotos", -1, True), _entrada("a.txt", 2048), _entrada("b.txt", 1024)]
	assert consulta.texto_marcados(_panel_falso(mezcla)) == "3 marcados (1 carpeta), 3 KB en archivos: fotos, a.txt, b.txt"
	# Con el tamaño de las carpetas ya calculado, el total es completo y se dice como siempre.
	calculadas = [_entrada("fotos", 4096, True), _entrada("a.txt", 1024)]
	assert consulta.texto_marcados(_panel_falso(calculadas)) == "2 marcados, 5 KB: fotos, a.txt"


def test_recuento_al_marcar_en_grupo_sin_cero_bytes_por_las_carpetas(monkeypatch):
	from app.ui import anuncios
	from app.ui.acciones import marcas

	dichos: list[str] = []
	monkeypatch.setattr(anuncios, "anunciar", lambda texto, *_a, **_k: dichos.append(texto))
	marcas._anunciar_total(_panel_falso([_entrada("fotos", -1, True)]))
	marcas._anunciar_total(_panel_falso([_entrada("fotos", -1, True), _entrada("a.txt", 2048)]))
	marcas._anunciar_total(_panel_falso([_entrada("a.txt", 2048)]))
	assert dichos == ["Marcados 1 (1 carpeta)", "Marcados 2 (1 carpeta), 2 KB en archivos", "Marcados 1, 2 KB"]


def test_resumen_del_panel_sin_cero_bytes_por_las_carpetas(ventana):
	panel = ventana.izquierdo.panel_actual()
	_marcar(panel, "sub")
	assert panel.texto_resumen().endswith("Marcados: 1 (1 carpeta)")


# ── 2.0.1 (revisión): con las marcas en columna, «Marca» se ve siempre ─────

def test_arrancar_en_modo_columna_pone_la_marca_sin_tocar_la_pestana(app_wx, carpeta, monkeypatch):
	marco = _crear(carpeta, monkeypatch, "columna")
	try:
		panel = marco.izquierdo.panel_actual()
		assert "marca" not in panel.columnas_carpeta()  # la sesión no la tenía y no se ensucia
		assert panel.lista_archivos.columnas[0] == "marca"
		marco.config.establecer("paneles.marcas_como", "seleccion")
		assert procesar_eventos(lambda: "marca" not in panel.lista_archivos.columnas, 3)
	finally:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


def test_conjunto_de_vista_sin_marca_la_muestra_en_modo_columna(ventana):
	from app.services.vistas_modelo import ConjuntoVista

	panel = ventana.izquierdo.panel_actual()
	_pasar_a_columna(ventana)
	conjunto = ConjuntoVista("Música", ("nombre", "tamano"))
	panel.aplicar_conjunto(conjunto)
	assert panel.lista_archivos.columnas[0] == "marca"
	assert conjunto.columnas == ("nombre", "tamano")
	ventana.config.establecer("paneles.marcas_como", "seleccion")
	assert procesar_eventos(lambda: "marca" not in panel.lista_archivos.columnas, 3)


def test_restaurar_un_espacio_sin_marca_la_muestra_en_modo_columna(ventana):
	from app.ui.acciones import personalizar_pe

	panel = ventana.izquierdo.panel_actual()
	_pasar_a_columna(ventana)
	personalizar_pe._aplicar_pestana(panel, {"columnas": ["nombre", "tamano"], "ruta": panel.ruta})
	assert panel.columnas_carpeta() == ["nombre", "tamano"]
	assert panel.lista_archivos.columnas[0] == "marca"
	assert panel.marca_anadida is False


def test_orden_de_lectura_sin_marca_la_lee_en_modo_columna(ventana):
	panel = ventana.izquierdo.panel_actual()
	_pasar_a_columna(ventana)
	panel.lectura = ["nombre", "tamano"]
	panel.aplicar_lectura(panel.lectura)
	assert panel.lista_archivos.columnas[:3] == ["marca", "nombre", "tamano"]
	assert panel.lectura == ["nombre", "tamano"]  # lo guardado no cambia
	# Con la Marca detrás del Nombre, se lee detrás del Nombre.
	panel.aplicar_columnas(["nombre", "marca", "tamano"])
	panel.aplicar_lectura(["nombre", "tamano"])
	assert panel.lista_archivos.columnas[:3] == ["nombre", "marca", "tamano"]


def test_dialogo_columnas_no_deja_quitar_marca_en_modo_columna(app_wx, monkeypatch):
	from app.ui import anuncios
	from app.ui.dialogos import f_columnas

	dichos: list[str] = []
	monkeypatch.setattr(anuncios, "anunciar", lambda texto, *_a, **_k: dichos.append(texto))
	for obligatoria, esperado in ((True, True), (False, False)):
		dialogo = f_columnas.DialogoColumnas(None, "Columnas", ["marca", "nombre"], {}, ["nombre"], marca_obligatoria=obligatoria)
		try:
			indice = dialogo._orden.index("marca")
			dialogo.lista.Check(indice, False)
			evento = wx.CommandEvent(wx.wxEVT_CHECKLISTBOX, dialogo.lista.GetId())
			evento.SetInt(indice)
			dialogo._al_marcar(evento)
			assert dialogo.lista.IsChecked(indice) is esperado
		finally:
			dialogo.Destroy()
	assert dichos == [f_columnas.aviso_marca()]
	assert "Subir y Bajar" in dichos[0]


def test_la_marca_anadida_no_impide_seguir_las_columnas_por_defecto(ventana):
	panel = ventana.izquierdo.panel_actual()
	por_defecto = list(ventana.config.obtener("paneles.columnas"))
	assert panel.columnas_carpeta() == por_defecto
	_pasar_a_columna(ventana)
	assert panel.columnas_carpeta() == ["marca", *por_defecto] and panel.marca_anadida
	ventana.config.establecer("paneles.columnas", ["nombre", "tamano"])
	assert procesar_eventos(lambda: panel.columnas_carpeta() == ["marca", "nombre", "tamano"], 3)
	assert panel.marca_anadida
	# Una pestaña con columnas elegidas a propósito no sigue a las por defecto.
	panel.aplicar_columnas(["marca", "nombre", "modificado"])
	ventana.config.establecer("paneles.columnas", ["nombre"])
	procesar_eventos(lambda: False, 0.3)
	assert panel.columnas_carpeta() == ["marca", "nombre", "modificado"]


def test_el_dialogo_columnas_lee_el_modo_de_la_ventana_principal(ventana):
	from app.ui.dialogos import f_columnas

	assert f_columnas.marcas_en_columna(ventana) is False
	_pasar_a_columna(ventana)
	assert f_columnas.marcas_en_columna(ventana) is True
	dialogo = f_columnas.DialogoColumnas(ventana, "Columnas", ["nombre"], {}, ["nombre"])
	try:
		assert dialogo.marca_obligatoria
	finally:
		dialogo.Destroy()


def test_columnas_del_lado_reflejan_la_marca_garantizada(ventana, monkeypatch):
	from app.ui.dialogos import f_columnas

	panel = ventana.izquierdo.panel_actual()
	_pasar_a_columna(ventana)
	panel.aplicar_columnas(["nombre", "tamano"])  # como una pestaña restaurada sin Marca
	panel.marca_anadida = False
	vistas: list[list[str]] = []

	def elegir(_padre, _titulo, visibles, anchos, _fabrica):
		vistas.append(list(visibles))
		return list(visibles), dict(anchos)

	monkeypatch.setattr(f_columnas, "elegir_columnas", elegir)
	panel.enfocar()
	ventana.ejecutar_orden("columnas")
	assert vistas == [["marca", "nombre", "tamano"]]
	assert panel.columnas_carpeta() == ["marca", "nombre", "tamano"] and panel.marca_anadida
	ventana.config.establecer("paneles.marcas_como", "seleccion")
	assert procesar_eventos(lambda: "marca" not in panel.columnas_carpeta(), 3)
