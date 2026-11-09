# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""«Información de la conexión» (diseño 2.0, 9.6; orden ``red_info``).

Un texto de solo lectura, una línea por dato (remoto, estado, usuario,
proveedor, espacio, volumen, protocolo SMB, cifrado, firma, archivos abiertos
y velocidad del enlace), que se recorre con las flechas y se puede copiar.
Se monta sobre ``DialogoTexto`` de la 1.x (etiqueta antes del campo, foco al
principio del texto, «Co&piar al portapapeles» y «C&errar» con Escape).
"""

from __future__ import annotations

import builtins

import wx

from app.services.windows.red_info import InfoRed
from app.ui.dialogo_texto import DialogoTexto


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoInfoRed(DialogoTexto):
	"""El texto de ``InfoRed.texto()`` con el resumen de una línea al principio."""

	def __init__(self, padre: wx.Window | None, info: InfoRed) -> None:
		texto = f"{info.resumen()}\n\n{info.texto()}"
		super().__init__(padre, _("Información de la conexión: {n}").format(n=info.nombre), _("&Información:"), texto, copiable=True)
		self.info = info
		self.campo.SetHelpText(_("Datos de la conexión de red, uno por línea. La primera línea es el resumen. "
			"Control+A y Control+C para copiarlos, o el botón Copiar."))


def mostrar(padre: wx.Window | None, info: InfoRed) -> None:
	dialogo = DialogoInfoRed(padre, info)
	try:
		dialogo.ShowModal()
	finally:
		dialogo.Destroy()
