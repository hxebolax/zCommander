# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""El bloque PE con la ventana principal real (diseño 2.0, 10.1, 10.6, 10.8, 10.9, 10.10, 10.15 y 18.2)."""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.services import espacios, reglas, sesion  # noqa: E402
from app.ui.acciones import personalizar_pe  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402

from ..conftest import procesar_eventos  # noqa: E402


@pytest.fixture
def carpetas(tmp_path):
	origen, destino = tmp_path / "origen", tmp_path / "destino"
	origen.mkdir()
	destino.mkdir()
	for nombre in ("a.txt", "b.txt", "c.log"):
		(origen / nombre).write_text(nombre, encoding="utf-8")
	(tmp_path / "otra").mkdir()
	return tmp_path


@pytest.fixture
def ventana(app_wx, carpetas, monkeypatch):
	from app.ui.ventana_principal import VentanaPrincipal

	monkeypatch.setattr(sesion, "cargar", lambda: {**sesion.POR_DEFECTO, "lados": {
		"izquierdo": {"pestanas": [sesion.pestana(ruta=str(carpetas / "otra"))], "actual": 0},
		"derecho": {"pestanas": [sesion.pestana(ruta=str(carpetas / "destino"))], "actual": 0}}})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	marco = VentanaPrincipal(config)
	marco.mostrar()
	procesar_eventos(lambda: marco.izquierdo.panel_actual().ruta == str(carpetas / "otra"), 5)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.3)


def _leyendo(ventana) -> bool:
	return any(getattr(p, "_leyendo", False) for p in ventana.todos_los_paneles())


def test_instalar_sustituye_grabador_y_macros(ventana):
	pe = personalizar_pe.servicio()
	assert pe is not None and ventana.servicio("grabador") is pe.grabador and ventana.servicio("macros") is pe.ejecutor


def test_grabar_y_reproducir_ir_marcar_y_copiar(ventana, carpetas, monkeypatch):
	from app.ui.accesibilidad import dialogos
	from app.ui.dialogos import copiar, nombre, pe_macros

	origen, destino = carpetas / "origen", carpetas / "destino"
	monkeypatch.setattr(dialogos, "pedir_texto", lambda *a, **k: str(origen))
	monkeypatch.setattr(nombre, "pedir_patron", lambda *a, **k: "*.txt")
	monkeypatch.setattr(copiar.DialogoCopiar, "ShowModal", lambda self: wx.ID_OK)
	# Marcados con el cursor en otro elemento: «¿Copiar los 2 marcados?» responde Sí.
	monkeypatch.setattr(dialogos, "elegir_con_casilla", lambda *a, **k: (0, False))
	grabadas = []
	monkeypatch.setattr(pe_macros, "guardar_grabada", lambda padre, pe, pasos: grabadas.append(pasos))
	pe = personalizar_pe.servicio()
	ventana.ejecutar_orden("macro_grabar")
	assert pe.grabador.grabando and "Grabando macro" in ventana.GetTitle()
	ventana.ejecutar_orden("ir_a_carpeta")
	assert procesar_eventos(lambda: ventana.activo.ruta == str(origen) and not _leyendo(ventana), 5)
	ventana.ejecutar_orden("marcar_patron")
	assert len(ventana.activo.marcadas()) == 2
	ventana.ejecutar_orden("decir_ruta")  # de consulta: no se graba
	ventana.ejecutar_orden("copiar")
	assert procesar_eventos(lambda: (destino / "a.txt").exists() and not ventana.operaciones.en_marcha(), 10)
	ventana.ejecutar_orden("macro_grabar")
	assert not pe.grabador.grabando and grabadas
	pasos = grabadas[0]
	assert [p.orden for p in pasos] == ["ir_a_carpeta", "marcar_patron", "copiar"]
	assert pasos[0].argumento == str(origen) and pasos[1].argumento == "*.txt"
	assert pasos[2].argumento["sin_dialogo"] is True and pasos[2].argumento["destino"].rstrip("\\") == str(destino)
	# Reproducir: se borra lo copiado, el panel va a otra carpeta y la macro hace lo mismo sin diálogos.
	for archivo in destino.iterdir():
		archivo.unlink()
	monkeypatch.setattr(copiar.DialogoCopiar, "ShowModal", lambda self: pytest.fail("la macro no debe abrir el diálogo de copiar"))
	monkeypatch.setattr(dialogos, "pedir_texto", lambda *a, **k: pytest.fail("la macro no debe preguntar la carpeta"))
	from app.services.macros import Macro

	pe.guardar_macros([Macro("Grabada", pasos=pasos)])
	ventana.izquierdo.panel_actual().ir_a(str(carpetas / "otra"))
	procesar_eventos(lambda: not _leyendo(ventana), 3)
	ventana.ejecutar_orden("macro:Grabada")
	assert procesar_eventos(lambda: not pe.ejecutor.en_curso(), 15)
	from app.ui import anuncios

	assert sorted(p.name for p in destino.iterdir()) == ["a.txt", "b.txt"], " | ".join(a.texto for a in anuncios.historial()[6:])
	assert pe.ejecutor.ultima == "Grabada"


def test_escape_detiene_la_macro_en_curso(ventana):
	from app.services.macros import Macro, Paso

	pe = personalizar_pe.servicio()
	pe.guardar_macros([Macro("Larga", pasos=[Paso("paso:esperar", 5000), Paso("paso:decir", "fin")])])
	ventana.ejecutar_orden("macro:Larga")
	assert pe.ejecutor.en_curso()
	ventana.ejecutar_orden("cancelar")
	assert not pe.ejecutor.en_curso()


def test_zc_ir_a_carpeta_cambia_el_panel_sin_lanzar_procesos(ventana, carpetas):
	ventana.linea.ChangeValue(f"zc ir_a_carpeta {carpetas / 'origen'}")
	ventana.ejecutar_linea()
	assert procesar_eventos(lambda: ventana.activo.ruta == str(carpetas / "origen"), 5)
	assert ventana._procesos == []  # noqa: SLF001 - sin procesos lanzados


def test_alias_se_expande_para_la_linea(ventana, carpetas):
	from app.services.alias import Alias

	pe = personalizar_pe.servicio()
	pe.guardar_alias([Alias("ll", "dir /a %1"), Alias("ir", f"zc ir_a_carpeta {carpetas}")])
	orden, entorno = personalizar_pe.expandir_linea(ventana, "ll x&y")
	assert orden == 'dir /a "%ZC_1%"' and entorno == {"ZC_1": "x&y"}
	assert personalizar_pe.expandir_linea(ventana, "ir") == (f"zc ir_a_carpeta {carpetas}", None)
	assert personalizar_pe.expandir_linea(ventana, "dir") == ("dir", None)


def test_abrir_un_espacio_restaura_pestanas_y_guarda_anterior(ventana, carpetas):
	izquierdo = ventana.izquierdo
	izquierdo.panel_actual().aplicar_orden("fecha", True)
	espacios.guardar_actual("Proyecto")
	izquierdo.nueva_pestana(ruta=str(carpetas / "origen"))
	procesar_eventos(lambda: not _leyendo(ventana), 3)
	assert izquierdo.cuaderno.GetPageCount() == 2
	espacios.abrir("Proyecto")
	assert procesar_eventos(lambda: izquierdo.cuaderno.GetPageCount() == 1 and not _leyendo(ventana), 5)
	panel = izquierdo.panel_actual()
	assert panel.criterio_orden == "fecha" and panel.orden_inverso is True
	assert procesar_eventos(lambda: panel.ruta == str(carpetas / "otra"), 5)
	anterior = espacios.buscar(espacios.cargar(), "Anterior")
	assert anterior is not None and len(anterior.disposicion["lados"]["izquierdo"]["pestanas"]) == 2


def test_regla_pone_la_columna_regla_y_su_sonido(ventana, carpetas, monkeypatch):
	from app.services.sonidos import servicio

	sonados = []
	monkeypatch.setattr(servicio, "sonar", lambda evento, variante="", *, sustituye=False: sonados.append(evento) or True)
	pe = personalizar_pe.servicio()
	pe.guardar_reglas([reglas.Regla("Textos", condicion=reglas.Condicion(patron="*.txt"), texto="TXT", sonido="regla.b")])
	panel = ventana.izquierdo.panel_actual()
	panel.ir_a(str(carpetas / "origen"))
	assert procesar_eventos(lambda: panel.ruta == str(carpetas / "origen") and not _leyendo(ventana), 5)
	panel.aplicar_columnas(["nombre", "regla"])
	lista = panel.lista_archivos
	textos = {lista.OnGetItemText(i, 0): lista.OnGetItemText(i, 1) for i in range(len(lista.entradas()))}
	assert textos.get("a.txt") == "TXT" and textos.get("c.log") == ""
	entrada = next(e for e in panel.entradas() if e.nombre == "a.txt")
	pe.al_cambiar_cursor(panel=panel, entrada=entrada)
	assert sonados == ["regla.b"]


def test_barra_de_botones_visible_y_teclado(ventana):
	ventana.config.establecer("vista.barra_botones_visible", True)
	pe = personalizar_pe.servicio()
	pe.colocar_barra()
	assert pe.barra is not None and pe.barra.botones
	afirmar_teclado_correcto(pe.barra, ignorar=("sin-letra",))
	assert not pe.barra.botones[0].AcceptsFocusFromKeyboard(), "fuera del orden de tabulación"
	ventana.ejecutar_orden("ir_barra_botones")
	ventana.config.establecer("vista.barra_botones_visible", False)
	pe.colocar_barra()
	assert pe.barra is None


@pytest.mark.interfaz
def test_teclas_globales_registran_y_liberan(ventana):
	ventana.config.establecer_varias({"teclado.globales_activas": True, "teclado.globales": {"traer_al_frente": "Ctrl+Alt+Shift+F12"}})
	pe = personalizar_pe.servicio()
	rechazadas = pe.registrar_teclas_globales()
	assert rechazadas == [] and list(ventana._teclas_globales.values()) == ["traer_al_frente"]  # noqa: SLF001
	ventana.liberar_teclas_globales()
	assert ventana._teclas_globales == {}  # noqa: SLF001
	ventana.config.establecer("teclado.globales_activas", False)
	assert pe.registrar_teclas_globales() == [] and ventana._teclas_globales == {}  # noqa: SLF001
