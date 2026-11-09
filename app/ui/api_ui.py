# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lo que ``zc.ui`` delega en la interfaz (diseño 2.0, 3.7): diálogos y controles accesibles para complementos.

``app.plugins.api.ModuloUI`` no importa wx: cada nombre que pide un complemento
(``zc.ui.confirmar``, ``zc.ui.VentanaComplemento``...) lo busca aquí a través
de ``InterfazAnfitrion.modulo_ui``. Lo crea N2 (versión funcional mínima);
dueño posterior PL.

Todos los diálogos pasan por ``mostrar_modal``, que pone el latido del
vigilante de bloqueos en pausa (3.8): el tiempo que la persona pasa en un
diálogo no cuenta como bloqueo de la interfaz.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Sequence
from typing import Any

import wx

from app.plugins import estado
from app.ui import senales_nvda
from app.ui.accesibilidad import dialogos as _dialogos
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.controles import SliderAccesible
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.accesibilidad.progreso import IndicadorProgreso

log = logging.getLogger(__name__)

__all__ = [
	"CheckListBoxAccesible", "IndicadorProgreso", "ListaAccesible", "SliderAccesible", "VentanaComplemento", "confirmar",
	"crear_botonera", "crear_campo", "elegir_opcion", "mostrar_diferencias", "mostrar_documento", "mostrar_error", "mostrar_mensaje",
	"mostrar_modal",
	"mostrar_resultados", "mostrar_texto", "movimiento_silencioso", "pedir_texto", "preparar_dialogo",
]


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _padre() -> wx.Window | None:
	return wx.GetApp().GetTopWindow() if wx.GetApp() else None


def mostrar_modal(dialogo: wx.Dialog) -> int:
	"""``ShowModal`` con el vigilante de bloqueos en pausa; los complementos no llaman a ``ShowModal`` directamente."""
	with estado.pausa_modal():
		return dialogo.ShowModal()


def mostrar_mensaje(mensaje: str, titulo: str = "", padre: wx.Window | None = None) -> None:
	with estado.pausa_modal():
		_dialogos.mostrar_mensaje(padre or _padre(), mensaje, titulo)


def mostrar_error(mensaje: str, titulo: str = "", padre: wx.Window | None = None) -> None:
	with estado.pausa_modal():
		_dialogos.mostrar_error(padre or _padre(), mensaje, titulo)


def confirmar(mensaje: str, titulo: str = "", padre: wx.Window | None = None, peligroso: bool = False) -> bool:
	with estado.pausa_modal():
		return _dialogos.confirmar(padre or _padre(), mensaje, titulo, peligroso=peligroso) == wx.ID_YES


def elegir_opcion(mensaje: str, titulo: str, opciones: Sequence[str], padre: wx.Window | None = None) -> int | None:
	with estado.pausa_modal():
		return _dialogos.elegir_opcion(padre or _padre(), mensaje, titulo, opciones)


def pedir_texto(etiqueta: str, titulo: str, valor: str = "", padre: wx.Window | None = None, **opciones: Any) -> str | None:
	with estado.pausa_modal():
		return _dialogos.pedir_texto(padre or _padre(), etiqueta, titulo, valor, **opciones)


def mostrar_texto(titulo: str, texto: str, padre: wx.Window | None = None) -> None:
	"""Ventana de solo lectura accesible."""
	from app.ui import dialogo_texto

	with estado.pausa_modal():
		dialogo_texto.mostrar_texto(padre or _padre(), titulo, _("&Texto:"), texto, copiable=True)


def mostrar_documento(documento: Any, padre: wx.Window | None = None) -> None:
	"""El visor interno con secciones para un ``api.Documento`` (14.7): F6, Mayús+F6, Ctrl+L y Ctrl+P."""
	from app.ui.ventanas import visor

	visor.abrir_documento(padre or _padre(), documento)


def mostrar_diferencias(ruta_a: str, ruta_b: str, padre: wx.Window | None = None) -> None:
	"""La ventana de diferencias del núcleo (no modal) con dos archivos del disco (11.21).

	Si la persona tiene un programa externo de diferencias en Preferencias, se usa ese,
	como en «Comparar archivos» del núcleo.
	"""
	from app.services.vfs import resolver
	from app.ui.ventanas import diferencias

	local = resolver.proveedor_local()
	diferencias.abrir(padre or _padre(), (local, str(ruta_a)), (local, str(ruta_b)))


def mostrar_resultados(titulo: str, rutas: Sequence[str], lado: str | None = None) -> None:
	"""Muestra una lista de resultados en un panel (el activo o el de ``lado``)."""
	ventana = _padre()
	if ventana is None or not hasattr(ventana, "activo"):
		return
	panel = ventana.lado(lado).panel_actual() if lado in ("izquierdo", "derecho") else ventana.activo
	panel.abrir_lista(titulo, list(rutas))


def movimiento_silencioso(ventana: wx.Window) -> None:
	"""Marca de 10.16 antes de mover el foco por código."""
	senales_nvda.marcar_movimiento_silencioso(ventana.GetHandle())


def revisar_en_desarrollo(ventana: wx.Window, id_complemento: str = "") -> list:
	"""``revisar_teclado`` de una ventana de complemento, solo en modo desarrollo: registra y anuncia los problemas."""
	from app.plugins import registro

	if not registro.modo_desarrollo():
		return []
	try:
		from app.ui.accesibilidad.revision_teclado import informe, revisar_teclado

		problemas = [p for p in revisar_teclado(ventana) if not getattr(p, "aviso", False)]
	except Exception:  # noqa: BLE001 - la revisión nunca impide abrir la ventana
		log.debug("No se pudo revisar el teclado de %s", ventana.GetTitle(), exc_info=True)
		return []
	if problemas:
		texto = informe(problemas)
		log.warning("Accesibilidad de la ventana «%s» del complemento %s:\n%s", ventana.GetTitle(), id_complemento, texto)
		from app.ui import anuncios

		anuncios.anunciar(_("La ventana {v} tiene {n} problemas de teclado; detalles en el registro").format(
			v=ventana.GetTitle(), n=len(problemas)), anuncios.RESULTADO)
	return problemas


class VentanaComplemento(wx.Frame):
	"""Ventana no modal de un complemento: Escape cierra y F1 abre la ayuda del complemento."""

	def __init__(self, padre: wx.Window | None, titulo: str, id_complemento: str = "", **opciones: Any) -> None:
		super().__init__(padre or _padre(), title=titulo, name=titulo, **opciones)
		self.id_complemento = id_complemento
		self._revisada = False
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)

	def Show(self, show: bool = True) -> bool:  # noqa: N802 - API de wx
		"""En modo desarrollo, la primera vez que se muestra pasa ``revisar_teclado`` y avisa de lo que encuentre (3.7, 3.12)."""
		if show and not self._revisada:
			self._revisada = True
			revisar_en_desarrollo(self, self.id_complemento)
		return super().Show(show)

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		if codigo == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			self.Close()
			return
		if codigo == wx.WXK_F1 and not evento.HasAnyModifiers() and self.id_complemento:
			from app.plugins import api

			interfaz = api.interfaz()
			if interfaz is not None:
				interfaz.abrir_ayuda(self.id_complemento)
				return
		evento.Skip()
