# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de copiar y mover, de nombre y de patrón, y la ventana de operaciones (núcleo).

Se construyen sin mostrarlos; ningún ``ShowModal`` real (lo prohíbe el conftest).
"""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.services.operaciones.copiar import OperacionCopiar  # noqa: E402
from app.services.operaciones.modelo import Estado, Operacion, Politica  # noqa: E402
from app.services.vfs import base  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.dialogos import nombre as mod_nombre  # noqa: E402
from app.ui.dialogos.copiar import DialogoCopiar, componer_resumen, normalizar_patron  # noqa: E402
from app.ui.ventanas.operaciones import VentanaOperaciones, admite_reintento, detalle_operacion, texto_errores  # noqa: E402
from tests.ayudas_wx import simular_tecla  # noqa: E402


@pytest.fixture
def configuracion(tmp_path):
	config = Configuracion(ruta=tmp_path / "settings.json")
	config.establecer_varias({
		"operaciones.politica_conflicto": "sobrescribir_si_mas_antiguo",
		"operaciones.verificar": True,
		"operaciones.copiar_carpetas_vacias": False,
	})
	return config


# ── Copiar y mover ──────────────────────────────────────────────────────────

def test_resumen():
	assert componer_resumen(False, 3, 1, 45 * 1024 * 1024) == "Copiar 3 archivos y 1 carpeta (45 MB) a:"
	assert componer_resumen(True, 1, 0) == "Mover 1 archivo a:"
	assert normalizar_patron(" * ") == ""
	assert normalizar_patron("*.txt") == "*.txt"


@pytest.mark.parametrize("mover", [False, True])
def test_dialogo_copiar_teclado(app_wx, configuracion, mover):
	dialogo = DialogoCopiar(None, componer_resumen(mover, 3, 1, 1000), "D:\\Copias", mover=mover, configuracion=configuracion)
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=["F2"])
		assert dialogo.GetTitle() == ("Mover" if mover else "Copiar")
	finally:
		dialogo.Destroy()


def test_dialogo_copiar_opciones_y_en_cola(app_wx, configuracion):
	dialogo = DialogoCopiar(None, "Copiar 1 archivo a:", "D:\\Copias\\", configuracion=configuracion)
	try:
		assert dialogo.politica() == Politica.SOBRESCRIBIR_SI_MAS_ANTIGUO
		assert dialogo.lista_politica.GetCount() == 7
		opciones = dialogo.opciones()
		assert opciones.verificar is True
		assert opciones.carpetas_vacias is False
		assert opciones.conservar_fechas is True
		assert opciones.copiar_enlaces is True
		assert opciones.patron == ""
		dialogo.campo_patron.SetValue("*.mp3")
		assert dialogo.opciones().patron == "*.mp3"
		assert dialogo.destino() == "D:\\Copias\\"
		assert not dialogo.en_cola
		# F2 equivale a «En cola».
		resultado = simular_tecla(dialogo, wx.WXK_F2)
		assert resultado.gestionado
		assert dialogo.en_cola
		assert dialogo.GetReturnCode() == wx.ID_OK
		# Las demás teclas siguen su camino (Tab, letras).
		assert simular_tecla(dialogo, wx.WXK_TAB).saltado
	finally:
		dialogo.Destroy()


# ── Nombre y patrón ─────────────────────────────────────────────────────────

def test_validar_nombre():
	assert mod_nombre.validar_nombre("CON")
	assert mod_nombre.validar_nombre("con.txt")
	assert mod_nombre.validar_nombre("a:b")
	assert mod_nombre.validar_nombre("informe.docx") is None
	assert mod_nombre.validar_nombre("a\\b") is not None
	assert mod_nombre.validar_nombre("a\\b\\c", permitir_ruta=True) is None
	assert mod_nombre.validar_nombre("a\\CON", permitir_ruta=True) is not None
	assert mod_nombre.rango_sin_extension("informe.final.docx") == (0, 13)
	assert mod_nombre.rango_sin_extension(".gitignore") == (0, 10)
	assert mod_nombre.rango_sin_extension("a\\b.txt") == (2, 3)


def test_dialogo_nombre_rechaza_con(app_wx, monkeypatch):
	avisos: list[str] = []
	monkeypatch.setattr(mod_nombre, "_avisar", lambda padre, mensaje, titulo: avisos.append(mensaje))
	dialogo = mod_nombre.DialogoNombre(None, "Renombrar", "&Nombre nuevo:", "CON")
	try:
		afirmar_teclado_correcto(dialogo)
		dialogo.SetReturnCode(0)
		assert dialogo.aceptar() is False
		assert avisos and "reservado" in avisos[0]
		assert dialogo.GetReturnCode() != wx.ID_OK
		dialogo.campo.SetValue("informe.txt")
		assert dialogo.aceptar() is True
		assert dialogo.GetReturnCode() == wx.ID_OK
		assert dialogo.valor() == "informe.txt"
	finally:
		dialogo.Destroy()


def test_dialogo_patron(app_wx, monkeypatch):
	avisos: list[str] = []
	monkeypatch.setattr(mod_nombre, "_avisar", lambda padre, mensaje, titulo: avisos.append(mensaje))
	dialogo = mod_nombre.DialogoPatron(None, "Marcar", "&Patrón:", ["*.txt", "*.mp3"])
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.valor() == "*.txt"
		assert dialogo.campo.GetCount() == 2
		dialogo.campo.SetValue("  ")
		assert dialogo.aceptar() is False and avisos
	finally:
		dialogo.Destroy()


# ── Ventana de operaciones ──────────────────────────────────────────────────

class OperacionFalsa(Operacion):
	tipo = "falsa"

	def descripcion(self) -> str:
		return "Eliminar 2 elementos"

	def ejecutar(self, ctx) -> None:
		pass


class GestorFalso:
	def __init__(self, operaciones) -> None:
		self.lista = list(operaciones)
		self.canceladas: list[Operacion] = []

	def operaciones(self):
		return list(self.lista)

	def cancelar(self, operacion) -> None:
		self.canceladas.append(operacion)

	def limpiar_terminadas(self) -> None:
		self.lista = [o for o in self.lista if not o.estado.final]


class DecisionesFalsas:
	def hay_pendientes(self) -> bool:
		return False

	def atender_pendiente(self, padre=None) -> bool:
		return False


def _copia_con_fallos() -> OperacionCopiar:
	from app.services.vfs.local import ProveedorLocal

	local = ProveedorLocal()
	entrada = base.Entrada("a.txt", "C:\\no-existe\\a.txt", tamano=10)
	copia = OperacionCopiar(local, [entrada], local, "D:\\Copias")
	copia.cambiar_estado(Estado.EJECUTANDO)
	copia.progresar(archivos_total=4, archivos_hechos=2, bytes_total=4000, bytes_hechos=1000, actual="a.txt",
		bytes_actual=5, total_actual=10)
	copia.anotar_error("C:\\no-existe\\a.txt", "No se encuentra el archivo")
	copia.fallidos.append(entrada)
	copia.cambiar_estado(Estado.TERMINADA_CON_ERRORES)
	return copia


def test_ventana_operaciones(app_wx):
	copia = _copia_con_fallos()
	otra = OperacionFalsa()
	gestor = GestorFalso([copia, otra])
	reintentos: list[Operacion] = []
	ventana = VentanaOperaciones(None, gestor, DecisionesFalsas(), reintentos.append)
	try:
		afirmar_teclado_correcto(ventana, teclas_propias=["Escape"])
		assert ventana.lista.GetItemCount() == 2
		assert ventana.lista.GetItemText(0, 1) == "Terminada con errores"
		assert ventana.lista.GetItemText(0, 2) == "25 %"
		assert ventana.operacion_elegida() is copia
		assert "Archivos: 2 de 4" in ventana.detalle.GetValue()
		assert ventana.boton_reintentar.IsEnabled()
		assert not ventana.boton_atender.IsEnabled()
		ventana.reintentar()
		assert reintentos == [copia]
		# El refresco conserva la fila elegida aunque desaparezcan otras.
		ventana.lista.Select(1)
		ventana.actualizar()
		assert ventana.operacion_elegida() is otra
		ventana.limpiar()
		assert ventana.lista.GetItemCount() == 1
		assert ventana.operacion_elegida() is otra
		ventana.cancelar()
		assert gestor.canceladas == [otra]
	finally:
		ventana.Destroy()


def test_textos_de_detalle():
	copia = _copia_con_fallos()
	texto = detalle_operacion(copia)
	assert texto.startswith("Copiar a.txt a ")
	assert "Total: 25 %" in texto
	assert "Errores: 1" in texto
	assert "No se encuentra el archivo" in texto_errores(copia)
	assert admite_reintento(copia)
	assert not admite_reintento(OperacionFalsa())
