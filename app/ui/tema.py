# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Temas de color: sistema (por defecto), Norton clásico y alto contraste.

El tema «sistema» no fuerza colores: usa los de Windows (y su modo de alto
contraste, si está activo). «Norton clásico» reproduce los colores de Norton
Commander: fondo azul oscuro, texto cian, marcados en amarillo y cursor con
fondo cian. Comprobado a mano que el cursor sobre una fila marcada se distingue.
"""

from __future__ import annotations

import wx

from app.ui.accesibilidad import visual


def colores(tema: str) -> dict[str, wx.Colour] | None:
	"""Colores para ``ListaArchivos.aplicar_colores`` (None = los del sistema)."""
	if tema == "alto_contraste" or (tema == "sistema" and visual.alto_contraste_activo()):
		return None
	if tema == "norton":
		return {
			"fondo": wx.Colour(0, 0, 128),
			"texto": wx.Colour(0, 255, 255),
			"marcado_texto": wx.Colour(255, 255, 0),
			"cursor_fondo": wx.Colour(0, 170, 170),
			"cursor_texto": wx.Colour(0, 0, 0),
		}
	return None


def fuente(nombre: str, tamano: int) -> wx.Font:
	"""Letra de listas, visor y editor (nombre vacío = la de Windows)."""
	base = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
	letra = wx.Font(base)
	letra.SetPointSize(max(8, min(40, int(tamano))))
	if nombre:
		letra.SetFaceName(nombre)
	return letra


def aplicar_a_ventana(ventana: wx.Window, tema: str) -> None:
	"""Fondo y texto de paneles y textos (no de las listas, que usan ``colores``)."""
	paleta = colores(tema)
	if paleta is None:
		return
	ventana.SetBackgroundColour(paleta["fondo"])
	ventana.SetForegroundColour(paleta["texto"])
