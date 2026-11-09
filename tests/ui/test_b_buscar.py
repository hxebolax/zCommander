# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque B en la interfaz: diálogos de buscar y sincronizar, y las órdenes sobre la ventana real.

Ningún ``ShowModal`` real (lo prohíbe el conftest): los diálogos se construyen
sin mostrarlos y se manejan con sus métodos; las tareas corren en un
``GestorTareas`` real y sus respuestas llegan con ``procesar_eventos``.
"""

from __future__ import annotations

import os
import time

import pytest

from tests.conftest import procesar_eventos

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.core.tareas import GestorTareas  # noqa: E402
from app.services import busqueda  # noqa: E402
from app.services.busqueda import ErrorCriterios  # noqa: E402
from app.services.diferencias_carpetas import Accion  # noqa: E402
from app.services.operaciones.sincronizar import OperacionSincronizar  # noqa: E402
from app.services.vfs import base  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.dialogos import b_buscar  # noqa: E402
from app.ui.dialogos.b_buscar import DialogoBuscar  # noqa: E402
from app.ui.dialogos.b_sincronizar import DialogoSincronizar  # noqa: E402
from tests.ayudas_wx import simular_tecla  # noqa: E402


@pytest.fixture
def configuracion(tmp_path):
	return Configuracion(ruta=tmp_path / "settings.json")


@pytest.fixture
def tareas():
	gestor = GestorTareas(max_hilos=2, nombre="pruebas-b")
	yield gestor
	gestor.apagar(2)


@pytest.fixture
def cinco(tmp_path):
	raiz = tmp_path / "busca"
	(raiz / "sub").mkdir(parents=True)
	(raiz / "uno.txt").write_text("hola", encoding="utf-8")
	(raiz / "sub" / "dos.txt").write_text("y hola", encoding="utf-8")
	(raiz / "tres.txt").write_text("adiós", encoding="utf-8")
	(raiz / "cuatro.md").write_text("hola", encoding="utf-8")
	(raiz / "cinco.bin").write_bytes(b"x" * 3000)
	return raiz


@pytest.fixture
def dialogo_buscar(app_wx, configuracion, tareas, cinco):
	llamadas: dict[str, list] = {"ir": [], "ver": [], "enviar": [], "cerrar": []}
	dialogo = DialogoBuscar(
		None, configuracion, tareas, str(cinco),
		al_ir=lambda r: llamadas["ir"].append(r),
		al_ver=lambda r, editar: llamadas["ver"].append((r, editar)),
		al_enviar=lambda titulo, rutas: llamadas["enviar"].append((titulo, rutas)),
		al_cerrar=lambda: llamadas["cerrar"].append(True),
	)
	dialogo.llamadas = llamadas
	yield dialogo
	if dialogo:
		dialogo.Destroy()
	procesar_eventos(lambda: False, 0.1)


def _buscar_y_esperar(dialogo) -> None:
	assert dialogo.buscar()
	assert procesar_eventos(lambda: not dialogo.buscando, 10)
	procesar_eventos(lambda: False, 0.05)


# ── Teclado ─────────────────────────────────────────────────────────────────

def test_dialogo_buscar_pasa_revisar_teclado(dialogo_buscar):
	afirmar_teclado_correcto(dialogo_buscar, teclas_propias=["F3", "F4"])
	assert dialogo_buscar.libro.GetPageCount() == 3


def test_dialogo_sincronizar_pasa_revisar_teclado(app_wx, configuracion, tareas, tmp_path):
	dialogo = DialogoSincronizar(None, configuracion, tareas, None, None)
	try:
		afirmar_teclado_correcto(dialogo)
	finally:
		dialogo.Destroy()


# ── Buscar ───────────────────────────────────────────────────────────────────

def test_buscar_txt_con_hola_y_enviar_al_panel(dialogo_buscar, cinco):
	dialogo = dialogo_buscar
	dialogo.campo_nombres.SetValue("*.txt")
	dialogo.campo_texto.SetValue("hola")
	_buscar_y_esperar(dialogo)
	nombres = sorted(r.entrada.nombre for r in dialogo.resultados)
	assert nombres == ["dos.txt", "uno.txt"]
	assert dialogo.lista.numero_filas() == 2
	assert dialogo.lista.texto_celda(0, 0) in ("dos.txt", "uno.txt")
	assert "Búsqueda terminada: 2 resultados" in dialogo.campo_estado.GetValue()
	assert dialogo.boton_enviar.IsEnabled() and dialogo.boton_ver.IsEnabled()
	assert dialogo.boton_buscar.GetLabel() == "&Buscar"
	from app.ui.accesibilidad import voz

	assert any("Búsqueda terminada" in d for d in voz.dichos_en_prueba)
	assert dialogo.enviar_al_panel()
	titulo, rutas = dialogo.llamadas["enviar"][0]
	assert titulo == "Búsqueda: *.txt, «hola»"
	assert sorted(os.path.basename(r) for r in rutas) == ["dos.txt", "uno.txt"]
	assert all(os.path.isabs(r) for r in rutas)


def test_tamano_minimo_ver_e_ir(dialogo_buscar):
	dialogo = dialogo_buscar
	dialogo.campo_minimo.SetValue("1")
	dialogo.lista_unidad.SetSelection(1)  # KB
	_buscar_y_esperar(dialogo)
	assert [r.entrada.nombre for r in dialogo.resultados] == ["cinco.bin"]
	dialogo.lista.enfocar_fila(0, anunciar=False)
	resultado = simular_tecla(dialogo, wx.WXK_F4)
	assert resultado.gestionado
	assert dialogo.llamadas["ver"][0][1] is True
	assert dialogo.ir_al_archivo()
	assert dialogo.llamadas["ir"][0].entrada.nombre == "cinco.bin"
	assert dialogo.llamadas["cerrar"] == [True]


def test_la_busqueda_se_detiene_con_escape(dialogo_buscar, monkeypatch):
	dialogo = dialogo_buscar

	def lenta(raices, criterios, cancelacion=None, al_resultado=None, al_revisar=None):
		proveedor, carpeta = raices[0]
		al_resultado(busqueda.Resultado(base.Entrada("a.txt", os.path.join(carpeta, "a.txt")), proveedor, carpeta, carpeta,
			os.path.join(carpeta, "a.txt")))
		limite = time.monotonic() + 10
		while time.monotonic() < limite:
			base.comprobar(cancelacion)
			time.sleep(0.01)
		return busqueda.Estadisticas()

	monkeypatch.setattr(b_buscar.busqueda, "buscar", lenta)
	assert dialogo.buscar()
	assert dialogo.buscando
	assert dialogo.boton_buscar.GetLabel() == "&Detener"
	procesar_eventos(lambda: dialogo.lista.numero_filas() == 1, 3)
	assert simular_tecla(dialogo, wx.WXK_ESCAPE).gestionado  # primer Escape: detiene
	assert procesar_eventos(lambda: not dialogo.buscando, 5)
	assert "Búsqueda detenida: 1 resultado" in dialogo.campo_estado.GetValue()
	assert dialogo.resultados and dialogo  # sigue abierto con lo encontrado


def test_criterios_desde_los_campos(dialogo_buscar):
	dialogo = dialogo_buscar
	dialogo.campo_minimo.SetValue("1,5")
	dialogo.lista_unidad.SetSelection(2)  # MB
	dialogo.campo_desde.SetValue("01/02/2025")
	dialogo.campo_hasta.SetValue("28/02/2025")
	dialogo.campo_profundidad.SetValue(2)
	dialogo.lista_tipo.SetSelection(2)
	criterios = dialogo.criterios()
	assert criterios.tamano_min == int(1.5 * 1024 * 1024)
	assert criterios.tamano_max is None
	assert time.localtime(criterios.desde)[:3] == (2025, 2, 1)
	assert time.localtime(criterios.hasta)[:6] == (2025, 2, 28, 23, 59, 59)
	assert criterios.profundidad == 2
	assert criterios.que == busqueda.AMBOS
	dialogo.campo_desde.SetValue("31/31/2025")
	with pytest.raises(ErrorCriterios):
		dialogo.criterios()
	dialogo.campo_desde.SetValue("")
	dialogo.campo_texto.SetValue("(")
	dialogo.casilla_texto_regex.SetValue(True)
	with pytest.raises(ErrorCriterios):
		dialogo.criterios()
	assert not dialogo.buscar()  # avisa y no empieza
	assert "no es válida" in dialogo.campo_estado.GetValue()


def test_busquedas_guardadas_en_el_dialogo(dialogo_buscar):
	dialogo = dialogo_buscar
	dialogo.campo_nombres.SetValue("*.mp3")
	dialogo.casilla_ocultos.SetValue(True)
	assert dialogo.guardar_busqueda("Música")
	assert dialogo.lista_guardadas.GetStrings() == ["Música"]
	dialogo.campo_nombres.SetValue("*")
	dialogo.casilla_ocultos.SetValue(False)
	assert dialogo.cargar_guardada(0)
	assert dialogo.campo_nombres.GetValue() == "*.mp3"
	assert dialogo.casilla_ocultos.GetValue()
	assert busqueda.cargar_guardadas()[0]["campos"]["nombres"] == "*.mp3"
	assert dialogo.borrar_guardada(confirmar=False)
	assert dialogo.lista_guardadas.GetCount() == 0


def test_resultados_fuera_del_disco_no_se_envian(dialogo_buscar):
	dialogo = dialogo_buscar

	class Remoto(base.Proveedor):
		esquema = "ftp"

		def listar(self, ruta, cancelacion=None):
			return []

		def info(self, ruta):
			return base.Entrada("x", ruta)

		def padre(self, ruta):
			return "/"

		def unir(self, carpeta, nombre):
			return carpeta + nombre

		def raiz(self, ruta):
			return "/"

		def mostrar(self, ruta):
			return "ftp://servidor" + ruta

		def abrir_lectura(self, ruta):
			raise base.NoAdmitido("no", ruta)

	remoto = Remoto()
	dialogo._hilo.cola.append(busqueda.Resultado(base.Entrada("x.txt", "/x.txt"), remoto, "/", "ftp://servidor/", None))
	assert dialogo.volcar() == 1
	assert not dialogo.boton_enviar.IsEnabled()
	assert not dialogo.enviar_al_panel()
	assert dialogo.llamadas["enviar"] == []


def test_guardar_resultados(dialogo_buscar, tmp_path):
	dialogo = dialogo_buscar
	dialogo.campo_nombres.SetValue("uno.txt")
	_buscar_y_esperar(dialogo)
	destino = tmp_path / "resultados.txt"
	assert dialogo.guardar_resultados(str(destino))
	assert procesar_eventos(destino.exists, 5)
	procesar_eventos(lambda: False, 0.2)
	assert destino.read_text(encoding="utf-8-sig").strip().endswith("uno.txt")


# ── Sincronizar ──────────────────────────────────────────────────────────────

@pytest.fixture
def dos(tmp_path):
	izq, der = tmp_path / "izq", tmp_path / "der"
	izq.mkdir()
	der.mkdir()
	(izq / "falta.txt").write_text("f", encoding="utf-8")
	(izq / "comun.txt").write_text("c", encoding="utf-8")
	(der / "comun.txt").write_text("c", encoding="utf-8")
	marca = time.time() - 3600
	os.utime(izq / "comun.txt", (marca, marca))
	os.utime(der / "comun.txt", (marca, marca))
	(der / "sobra.txt").write_text("s", encoding="utf-8")
	return izq, der


def test_sincronizar_propone_copiar_a_la_derecha_y_se_cambia_con_teclas(app_wx, configuracion, tareas, dos):
	izq, der = dos
	dialogo = DialogoSincronizar(None, configuracion, tareas, None, None)
	try:
		dialogo.campo_izquierda.SetValue(str(izq))
		dialogo.campo_derecha.SetValue(str(der))
		assert dialogo.comparar()
		assert procesar_eventos(lambda: not dialogo.comparando, 10)
		procesar_eventos(lambda: False, 0.05)
		textos = {dialogo.lista.texto_celda(i, 0): dialogo.lista.texto_celda(i, 2) for i in range(dialogo.lista.numero_filas())}
		assert textos == {"falta.txt": "Copiar a la derecha", "sobra.txt": "Nada"}
		assert dialogo.boton_sincronizar.IsEnabled()
		fila_sobra = next(i for i in range(dialogo.lista.numero_filas()) if dialogo.lista.texto_celda(i, 0) == "sobra.txt")
		dialogo.lista.enfocar_fila(fila_sobra)
		# B: borrar en el destino (a la derecha); D en una fila sin archivo a la izquierda no se puede.
		assert simular_tecla(dialogo.lista, "B", tipo=wx.wxEVT_KEY_DOWN).gestionado
		assert dialogo.lista.texto_celda(fila_sobra, 2) == "Eliminar a la derecha"
		assert dialogo.cambiar_accion(Accion.COPIAR_DERECHA) == 0
		dialogo.lista_filtro.SetSelection(1)  # solo «Copiar a la derecha»
		dialogo._mostrar()
		assert dialogo.lista.numero_filas() == 1
		assert dialogo.sincronizar(confirmar=False)
		operacion = dialogo.operacion
		assert isinstance(operacion, OperacionSincronizar)
		assert {f.accion for f in operacion.filas} == {Accion.COPIAR_DERECHA, Accion.ELIMINAR_DERECHA}
		assert dialogo.GetReturnCode() == wx.ID_OK
	finally:
		dialogo.Destroy()


def test_sincronizar_recalcula_al_cambiar_la_direccion(app_wx, configuracion, tareas, dos, monkeypatch):
	izq, der = dos
	anunciados: list[str] = []
	monkeypatch.setattr("app.ui.anuncios.anunciar", lambda texto, *a, **k: anunciados.append(texto))
	dialogo = DialogoSincronizar(None, configuracion, tareas, None, None)
	try:
		dialogo.campo_izquierda.SetValue(str(izq))
		dialogo.campo_derecha.SetValue(str(der))
		assert dialogo.comparar()
		assert procesar_eventos(lambda: not dialogo.comparando, 10)
		procesar_eventos(lambda: False, 0.05)
		# Sin volver a comparar (no se lanza otra tarea): se proponen las acciones para la dirección nueva.
		monkeypatch.setattr(dialogo._tareas, "enviar", lambda *a, **k: pytest.fail("No debe volver a leer el disco"))
		dialogo.lista_direccion.SetSelection(1)  # de derecha a izquierda
		dialogo._al_cambiar_direccion()
		textos = {dialogo.lista.texto_celda(i, 0): dialogo.lista.texto_celda(i, 2) for i in range(dialogo.lista.numero_filas())}
		assert textos == {"falta.txt": "Nada", "sobra.txt": "Copiar a la izquierda"}
		assert "Acciones recalculadas" in dialogo.campo_estado.GetValue()
		assert any("Acciones recalculadas" in t for t in anunciados)
		dialogo.casilla_eliminar.SetValue(True)
		assert dialogo.recalcular()
		textos = {dialogo.lista.texto_celda(i, 0): dialogo.lista.texto_celda(i, 2) for i in range(dialogo.lista.numero_filas())}
		assert textos == {"falta.txt": "Eliminar a la izquierda", "sobra.txt": "Copiar a la izquierda"}
	finally:
		dialogo.Destroy()


def test_sincronizar_avisa_si_la_carpeta_no_existe(app_wx, configuracion, tareas, dos, tmp_path):
	izq, _der = dos
	dialogo = DialogoSincronizar(None, configuracion, tareas, None, None)
	try:
		dialogo.campo_izquierda.SetValue(str(izq))
		dialogo.campo_derecha.SetValue(str(tmp_path / "no_existe"))
		assert dialogo.comparar()
		assert procesar_eventos(lambda: not dialogo.comparando, 10)
		procesar_eventos(lambda: False, 0.05)
		assert "No se encuentra la carpeta" in dialogo.campo_estado.GetValue()
		assert not dialogo.boton_sincronizar.IsEnabled()
	finally:
		dialogo.Destroy()


# ── Órdenes sobre la ventana real ──────────────────────────────────────────────

@pytest.fixture
def ventana(app_wx, dos, monkeypatch):
	from app.services import sesion

	izq, der = dos
	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {
			"izquierdo": {"pestanas": [sesion.pestana(ruta=str(izq))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(der))], "actual": 0},
		},
	})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	from app.ui.ventana_principal import VentanaPrincipal

	marco = VentanaPrincipal(config)
	marco.mostrar()
	assert procesar_eventos(lambda: len(marco.izquierdo.panel_actual().entradas()) >= 3
		and len(marco.derecho.panel_actual().entradas()) >= 3, 10)
	yield marco
	if marco:
		marco.Close(True)
		procesar_eventos(lambda: False, 0.5)


def _contexto(ventana, orden: str):
	from app.ui import ordenes

	return ventana._contexto(ordenes.POR_ID[orden], None)


def test_comparar_carpetas_marca_el_mas_reciente_solo_a_la_izquierda(ventana, dos):
	from app.services.diferencias_carpetas import Criterio
	from app.ui.acciones import busqueda_b

	izq, der = dos
	(der / "sobra.txt").unlink()
	(izq / "falta.txt").unlink()
	os.utime(izq / "comun.txt", None)  # ahora la izquierda es más reciente
	for panel in (ventana.izquierdo.panel_actual(), ventana.derecho.panel_actual()):
		panel.refrescar()
	assert procesar_eventos(lambda: len(ventana.derecho.panel_actual().entradas()) == 2
		and len(ventana.izquierdo.panel_actual().entradas()) == 2, 5)
	ctx = _contexto(ventana, "comparar_carpetas")
	assert busqueda_b.ejecutar_comparacion(ctx, Criterio.FECHA) is not None
	izquierdo, derecho = ventana.izquierdo.panel_actual(), ventana.derecho.panel_actual()
	assert procesar_eventos(lambda: izquierdo.marcadas(), 5)
	assert [e.nombre for e in izquierdo.marcadas()] == ["comun.txt"]
	assert derecho.marcadas() == []
	from app.ui.accesibilidad import voz

	assert "Diferencias: 1 a la izquierda, 0 a la derecha" in voz.dichos_en_prueba


def test_orden_comparar_carpetas_pregunta_el_criterio(ventana, dos, monkeypatch):
	from app.ui.accesibilidad import dialogos

	preguntas = []
	monkeypatch.setattr(dialogos, "elegir_opcion", lambda padre, mensaje, titulo, opciones: preguntas.append(opciones) or 0)
	ventana.ejecutar_orden("comparar_carpetas")  # criterio «Nombre»: solo la existencia
	izquierdo, derecho = ventana.izquierdo.panel_actual(), ventana.derecho.panel_actual()
	assert procesar_eventos(lambda: izquierdo.marcadas() and derecho.marcadas(), 5)
	assert len(preguntas[0]) == 4
	assert [e.nombre for e in izquierdo.marcadas()] == ["falta.txt"]
	assert [e.nombre for e in derecho.marcadas()] == ["sobra.txt"]


def test_vista_plana_cesta_y_tamano(ventana, dos, monkeypatch):
	from app.ui.acciones import busqueda_b

	izq, _der = dos
	(izq / "carpeta").mkdir()
	(izq / "carpeta" / "dentro.txt").write_text("1234567890", encoding="utf-8")
	panel = ventana.izquierdo.panel_actual()
	panel.enfocar()
	panel.refrescar()
	assert procesar_eventos(lambda: panel.ir_a_nombre("carpeta"), 5)

	# Tamaño de la carpeta del cursor (Mayús+Espacio).
	ventana.ejecutar_orden("tamano_carpetas")
	assert procesar_eventos(lambda: panel._tamanos, 5)
	assert list(panel._tamanos.values()) == [10]

	# Vista plana: todos los archivos de la carpeta y sus subcarpetas.
	ventana.ejecutar_orden("vista_plana")
	assert procesar_eventos(lambda: panel.es_lista() is not None and len(panel.entradas()) >= 3, 5)
	assert busqueda_b.es_vista_plana(_contexto(ventana, "vista_plana"))
	assert {e.nombre for e in panel.entradas()} >= {"dentro.txt", "falta.txt", "comun.txt"}
	ventana.ejecutar_orden("vista_plana")  # otra vez: vuelve a la carpeta
	assert procesar_eventos(lambda: panel.es_lista() is None and panel.ruta == str(izq), 5)

	# Cesta: añadir, abrir como lista y vaciar.
	assert procesar_eventos(lambda: panel.ir_a_nombre("falta.txt"), 5)
	ventana.ejecutar_orden("cesta_agregar")
	assert ventana.cesta.rutas() == [str(izq / "falta.txt")]
	ventana.ejecutar_orden("cesta_abrir")
	assert procesar_eventos(lambda: panel.es_lista() == "Cesta"
		and [e.nombre for e in panel.entradas() if not e.es_superior] == ["falta.txt"], 5)
	from app.ui.accesibilidad import dialogos

	monkeypatch.setattr(dialogos, "confirmar", lambda *a, **k: wx.ID_YES)
	ventana.ejecutar_orden("cesta_vaciar")
	assert len(ventana.cesta) == 0
	assert procesar_eventos(lambda: panel.es_lista() is None, 5)


def test_buscar_archivos_abre_un_solo_dialogo_y_va_al_resultado(ventana, dos, monkeypatch):
	from app.ui.acciones import busqueda_b

	izq, _der = dos
	monkeypatch.setattr(DialogoBuscar, "Show", lambda self, mostrar=True: True)
	ventana.izquierdo.panel_actual().enfocar()
	ventana.ejecutar_orden("buscar_archivos")
	dialogo = busqueda_b._busqueda_abierta()
	assert dialogo is not None
	assert dialogo.campo_buscar_en.GetValue() == str(izq)
	ventana.ejecutar_orden("buscar_archivos")
	assert busqueda_b._busqueda_abierta() is dialogo
	dialogo.campo_nombres.SetValue("falta.txt")
	_buscar_y_esperar(dialogo)
	assert len(dialogo.resultados) == 1
	panel = ventana.derecho.panel_actual()
	ventana.panel_enfocado(panel)  # el foco real no llega sin ventana en primer plano
	assert ventana.activo is panel
	dialogo.lista.enfocar_fila(0, anunciar=False)
	assert dialogo.ir_al_archivo()
	assert procesar_eventos(lambda: panel.ruta == str(izq) and panel.cursor() is not None and panel.cursor().nombre == "falta.txt", 5)
	assert busqueda_b._busqueda_abierta is None
