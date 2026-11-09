# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Piezas comunes de los diálogos de sonidos (bloque SO): mapa, paquetes y asistente.

Los avisos, preguntas y selectores de archivo pasan por las funciones de ESTE
módulo para que las pruebas las sustituyan: ningún ``ShowModal`` real llega a
la pantalla. ``mostrar_modal`` muestra un diálogo con el sonido de abrir y
cerrar, lo destruye y devuelve el foco a donde estaba.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.services.sonidos import paquetes
from app.ui.accesibilidad import dialogos

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def avisar(padre: wx.Window | None, texto: str, titulo: str = "") -> None:
	dialogos.mostrar_mensaje(padre, texto, titulo or _("Sonidos"), icono=wx.ICON_WARNING)


def error(padre: wx.Window | None, texto: str, titulo: str = "") -> None:
	dialogos.mostrar_error(padre, texto, titulo or _("Sonidos"))


def preguntar(padre: wx.Window | None, texto: str, titulo: str = "", peligroso: bool = False) -> bool:
	"""Sí o No; con ``peligroso``, Intro (y el foco inicial) es «No»."""
	return dialogos.confirmar(padre, texto, titulo or _("Confirmación"), peligroso=peligroso) == wx.ID_YES


def _dialogo_archivo(padre: wx.Window | None, mensaje: str, comodin: str, estilo: int, nombre: str = "") -> Path | None:
	dialogo = wx.FileDialog(padre, mensaje, defaultFile=nombre, wildcard=comodin, style=estilo)
	try:
		return Path(dialogo.GetPath()) if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def elegir_wav(padre: wx.Window | None) -> Path | None:
	"""Selector de un ``.wav`` para sustituir un sonido."""
	return _dialogo_archivo(padre, _("Elija un archivo WAV"), _("Sonidos WAV (*.wav)|*.wav"), wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)


def elegir_zcsonidos(padre: wx.Window | None) -> Path | None:
	"""Selector de un ``.zcsonidos`` para importarlo."""
	return _dialogo_archivo(padre, _("Elija un paquete de sonidos"), _("Paquetes de sonidos (*.zcsonidos)|*.zcsonidos"),
		wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)


def elegir_destino(padre: wx.Window | None, nombre: str) -> Path | None:
	"""Dónde guardar un ``.zcsonidos`` exportado."""
	return _dialogo_archivo(padre, _("Exportar el paquete de sonidos"), _("Paquetes de sonidos (*.zcsonidos)|*.zcsonidos"),
		wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT, nombre)


def sonar(evento: str) -> None:
	"""Sonido del catálogo; un diálogo nunca falla por un sonido."""
	try:
		from app.services.sonidos import servicio

		servicio.sonar(evento)
	except Exception:  # noqa: BLE001 - sin sonidos se sigue igual
		log.debug("No se pudo pedir el sonido %s", evento, exc_info=True)


def mostrar_modal(dialogo: wx.Dialog) -> int:
	"""Muestra el diálogo, lo destruye y devuelve el foco a donde estaba."""
	foco_previo = wx.Window.FindFocus()
	sonar("dialogo.abrir")
	try:
		return dialogo.ShowModal()
	finally:
		sonar("dialogo.cerrar")
		dialogo.Destroy()
		if foco_previo:
			foco_previo.SetFocus()


def nombre_evento(evento: Any, variante: str = "") -> str:
	"""Nombre visible de un evento con su variante («Progreso, 30 %»)."""
	nombre = _(evento.nombre)
	return _("{n}, {v} %").format(n=nombre, v=variante) if variante else nombre


def boton(padre: wx.Window, etiqueta: str, ayuda: str, accion: Callable[[], Any], sizer: wx.Sizer) -> wx.Button:
	"""Botón con su ayuda de Ctrl+H, añadido a ``sizer``."""
	control = wx.Button(padre, label=etiqueta)
	control.SetHelpText(ayuda)
	control.Bind(wx.EVT_BUTTON, lambda _e: accion())
	sizer.Add(control, 0, wx.ALL, padre.FromDIP(3))
	return control


def nombre_paquete(id_paquete: str) -> str:
	paquete = paquetes.obtener(id_paquete)
	return paquete.nombre if paquete else id_paquete
