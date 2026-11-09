# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cola de decisiones y lista de conflictos (núcleo).

Nada se muestra: los diálogos se construyen sin ``ShowModal`` (el conftest lo
prohíbe) y la cola de decisiones se prueba con una pregunta que queda
pendiente porque no hay ventana principal activa.
"""

from __future__ import annotations

import threading
import time

import pytest

wx = pytest.importorskip("wx")

from app.services.operaciones.modelo import (  # noqa: E402
	AccionConflicto,
	AccionError,
	Conflicto,
	Operacion,
	PreguntaError,
	RespuestaConflicto,
)
from app.services.vfs import base  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.decisiones import GestorDecisiones, ignorar_teclas_iniciales  # noqa: E402
from app.ui.dialogos.conflictos import DialogoConflicto, DialogoConflictos  # noqa: E402
from tests.ayudas_wx import esperar_hasta, simular_tecla  # noqa: E402


class OperacionFalsa(Operacion):
	tipo = "falsa"

	def descripcion(self) -> str:
		return "Copiar 3 elementos a D:\\Copias"

	def ejecutar(self, ctx) -> None:
		pass


class _Token:
	def __init__(self) -> None:
		self.activo = False

	def is_set(self) -> bool:
		return self.activo

	def set(self) -> None:
		self.activo = True


class _Contexto:
	def __init__(self) -> None:
		self.token = _Token()


def _conflictos() -> list[Conflicto]:
	ahora = time.time()
	datos = [("a.txt", ahora, ahora - 3600), ("sub\\b.txt", ahora - 3600, ahora), ("c.txt", ahora, ahora)]
	resultado = []
	for relativo, fecha_origen, fecha_destino in datos:
		origen = base.Entrada(relativo, "C:\\origen\\" + relativo, tamano=1000, modificado=fecha_origen)
		destino = base.Entrada(relativo, "D:\\destino\\" + relativo, tamano=2000, modificado=fecha_destino)
		resultado.append(Conflicto(relativo, origen, destino, destino.ruta))
	return resultado


@pytest.fixture
def lista_conflictos(app_wx):
	dialogo = DialogoConflictos(None, _conflictos(), object(), object(), titulo="Copiar")
	yield dialogo
	dialogo.Destroy()


# ── Lista de conflictos ─────────────────────────────────────────────────────

def test_lista_de_conflictos_teclado(lista_conflictos):
	afirmar_teclado_correcto(lista_conflictos, teclas_propias=["S", "O", "C", "E"])


def test_lista_empieza_en_omitir(lista_conflictos):
	assert lista_conflictos.lista.GetItemCount() == 3
	assert lista_conflictos.resultado() == [RespuestaConflicto(AccionConflicto.OMITIR)] * 3
	assert "Ya existe «a.txt»" in lista_conflictos.texto.GetValue()


def test_letras_cambian_la_accion_de_las_filas(lista_conflictos):
	from app.ui.accesibilidad import voz

	dialogo = lista_conflictos
	lista = dialogo.lista
	# La fila del cursor (la 0, seleccionada al abrir).
	assert dialogo.aplicar_tecla("s")
	assert dialogo.acciones[0] == AccionConflicto.SOBRESCRIBIR
	assert lista.GetItemText(0, 2) == "Sobrescribir"
	assert "Sobrescribir: a.txt" in voz.dichos_en_prueba
	# Varias seleccionadas.
	lista.Select(0, False)
	lista.Select(1)
	lista.Select(2)
	assert dialogo.aplicar_tecla("E")
	assert dialogo.acciones[1:] == [AccionConflicto.RENOMBRAR_EXISTENTE] * 2
	assert "Renombrar el existente: 2 filas" in voz.dichos_en_prueba
	# Por el manejador de teclas de la lista (EVT_KEY_DOWN), como al pulsar C.
	lista.Select(1, False)
	resultado = simular_tecla(lista, "c", tipo=wx.wxEVT_KEY_DOWN)
	assert resultado.gestionado and not resultado.saltado
	assert dialogo.acciones[2] == AccionConflicto.RENOMBRAR_COPIA
	# La O vuelve a omitir; otra letra no hace nada y sigue su camino.
	assert dialogo.aplicar_tecla("o")
	assert dialogo.acciones[2] == AccionConflicto.OMITIR
	assert not dialogo.aplicar_tecla("x")
	assert simular_tecla(lista, "x", tipo=wx.wxEVT_KEY_DOWN).saltado
	assert dialogo.resultado() == [
		RespuestaConflicto(AccionConflicto.SOBRESCRIBIR),
		RespuestaConflicto(AccionConflicto.RENOMBRAR_EXISTENTE),
		RespuestaConflicto(AccionConflicto.OMITIR),
	]


def test_aplicar_a_todos_y_filtro(lista_conflictos):
	dialogo = lista_conflictos
	dialogo.aplicar_tecla("S")
	dialogo.aplicar_a_todos()
	assert dialogo.acciones == [AccionConflicto.SOBRESCRIBIR] * 3
	# Solo el segundo tiene el destino más reciente.
	dialogo.mostrar.SetSelection(1)
	dialogo._rellenar()
	assert dialogo.lista.GetItemCount() == 1
	assert dialogo.lista.GetItemText(0, 0) == "sub\\b.txt"
	dialogo.aplicar_tecla("O")
	assert dialogo.acciones == [AccionConflicto.SOBRESCRIBIR, AccionConflicto.OMITIR, AccionConflicto.SOBRESCRIBIR]
	assert len(dialogo.resultado()) == 3


def test_sobrescribir_los_mas_antiguos_resuelve_todo(lista_conflictos):
	lista_conflictos.sobrescribir_antiguos()
	assert lista_conflictos.GetReturnCode() == wx.ID_OK
	assert lista_conflictos.resultado() == [RespuestaConflicto(AccionConflicto.SOBRESCRIBIR_SI_MAS_ANTIGUO)] * 3


def test_pregunta_individual(app_wx):
	dialogo = DialogoConflicto(None, _conflictos()[0], titulo="Copiar")
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.GetEscapeId() == dialogo.boton_omitir.GetId()
		assert dialogo.respuesta() == RespuestaConflicto(AccionConflicto.OMITIR)
		assert dialogo.nombre_propuesto() == "a (2).txt"
		dialogo.elegir(RespuestaConflicto(AccionConflicto.SOBRESCRIBIR, para_todos=True))
		assert dialogo.respuesta().para_todos
	finally:
		dialogo.Destroy()


def test_bloqueo_de_teclas_al_abrir(app_wx):
	dialogo = DialogoConflicto(None, _conflictos()[0])
	try:
		bloqueo = ignorar_teclas_iniciales(dialogo)
		assert bloqueo.activo()
		resultado = simular_tecla(dialogo, wx.WXK_RETURN)
		assert resultado.gestionado and not resultado.saltado
		bloqueo.hasta = time.monotonic() - 1
		assert not bloqueo.activo()
		assert simular_tecla(dialogo, wx.WXK_TAB).saltado
	finally:
		dialogo.Destroy()


# ── Gestor de decisiones ────────────────────────────────────────────────────

def test_desde_el_hilo_principal_da_error(app_wx):
	gestor = GestorDecisiones(None)
	with pytest.raises(RuntimeError):
		gestor.elegir("Espacio", "No cabe", ["&Continuar", "&Cancelar"], escape=1)


def test_pendiente_se_responde_con_cancelar_todas(app_wx):
	from app.ui.accesibilidad import voz

	gestor = GestorDecisiones(None)
	operacion = OperacionFalsa()
	gestor.marcar_reciente(operacion)
	respuestas: dict[str, object] = {}

	def en_hilo():
		respuestas["elegir"] = gestor.elegir("Espacio insuficiente", "No cabe", ["&Continuar", "&Cancelar"], escape=1)

	hilo = threading.Thread(target=en_hilo, name="operaciones-prueba")
	hilo.start()
	# Sin ventana principal activa no se muestra: queda pendiente y se anuncia.
	esperar_hasta(gestor.hay_pendientes, 3, "La pregunta no llegó a la cola")
	assert gestor.pendientes() == ["Espacio insuficiente"]
	assert "Espacio insuficiente: espera su decisión" in voz.dichos_en_prueba
	gestor.cancelar_todas()
	hilo.join(3)
	assert not hilo.is_alive()
	assert respuestas["elegir"] == 1
	assert not gestor.hay_pendientes()
	# Después de cancelar_todas, las preguntas nuevas se cancelan al momento.
	resultado = {}
	otro = threading.Thread(
		target=lambda: resultado.setdefault("r", gestor.resolver_conflictos(operacion, _conflictos())), name="operaciones-prueba-2")
	otro.start()
	otro.join(3)
	assert resultado["r"] is None


def test_la_espera_se_corta_al_cancelar_la_operacion(app_wx):
	gestor = GestorDecisiones(None)
	operacion = OperacionFalsa()
	operacion.contexto = _Contexto()
	respuestas: dict[str, object] = {}

	def en_hilo():
		respuestas["error"] = gestor.preguntar_error(operacion, PreguntaError("C:\\a.txt", "En uso"))
		respuestas["conflicto"] = gestor.preguntar_conflicto(operacion, _conflictos()[0])

	hilo = threading.Thread(target=en_hilo, name="operaciones-prueba")
	hilo.start()
	esperar_hasta(gestor.hay_pendientes, 3, "La pregunta no llegó a la cola")
	assert gestor.pendientes() == [operacion.descripcion()]
	operacion.contexto.token.set()
	hilo.join(3)
	assert not hilo.is_alive()
	assert respuestas["error"] == AccionError.CANCELAR
	assert respuestas["conflicto"].accion == AccionConflicto.CANCELAR
	esperar_hasta(lambda: not gestor.hay_pendientes(), 3, "La pregunta cancelada sigue en la cola")
	gestor.cancelar_todas()


def test_reciente(app_wx):
	gestor = GestorDecisiones(None)
	primera, segunda = OperacionFalsa(), OperacionFalsa()
	gestor.marcar_reciente(primera)
	assert gestor.es_reciente(primera)
	gestor.marcar_reciente(segunda)
	assert not gestor.es_reciente(primera)
	assert gestor.es_reciente(segunda)
	gestor._momento_ultima -= 5
	assert not gestor.es_reciente(segunda)


def test_inmediata_muestra_el_dialogo_y_devuelve_la_respuesta(app_wx, monkeypatch):
	"""Operación recién lanzada y ventana principal activa: el diálogo se abre enseguida."""
	def show_modal(dialogo):
		# La persona pulsa S sobre la fila del cursor y Continuar.
		dialogo.aplicar_tecla("S")
		return wx.ID_OK

	monkeypatch.setattr(DialogoConflictos, "ShowModal", show_modal)
	gestor = GestorDecisiones(None)
	monkeypatch.setattr(gestor, "_principal_activa", lambda: True)
	operacion = OperacionFalsa()
	gestor.marcar_reciente(operacion)
	respuestas: dict[str, object] = {}
	hilo = threading.Thread(
		target=lambda: respuestas.setdefault("r", gestor.resolver_conflictos(operacion, _conflictos())), name="operaciones-prueba")
	hilo.start()
	esperar_hasta(lambda: "r" in respuestas, 3, "El diálogo inmediato no respondió")
	hilo.join(3)
	assert [r.accion for r in respuestas["r"]] == [AccionConflicto.SOBRESCRIBIR, AccionConflicto.OMITIR, AccionConflicto.OMITIR]
	assert not gestor.hay_pendientes()
	gestor.cancelar_todas()
