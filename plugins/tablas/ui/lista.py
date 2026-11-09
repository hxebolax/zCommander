# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lista virtual de una tabla sobre la ``ListaAccesible`` de la API.

La ``ListaAccesible`` guarda una copia de cada celda; con un millón de filas
eso duplicaría la memoria. Esta subclase lee las celdas directamente de la
``Tabla`` y de la lista de índices visibles (filtro y orden), y conserva todo
lo demás: lectura por columnas con Izquierda y Derecha, Ctrl+1 a Ctrl+0,
foco siempre en una fila.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import wx

_CLASES: dict[type, type] = {}


def clase_lista(base: type) -> type:
	"""Subclase virtual de ``base`` (``zc.ui.ListaAccesible``), creada una vez por clase base."""
	if base in _CLASES:
		return _CLASES[base]

	class ListaTabla(base):  # type: ignore[misc, valid-type]
		def __init__(self, padre: wx.Window, nombre: str) -> None:
			super().__init__(padre, nombre, columnas=[], virtual=True)
			self._tabla: Any = None
			self._indices: list[int] = []

		def fijar(self, tabla: Any, indices: Sequence[int], cabeceras_nuevas: bool = False) -> None:
			"""Muestra ``tabla`` con las filas ``indices`` (en ese orden)."""
			self.Freeze()
			try:
				if cabeceras_nuevas or self.GetColumnCount() != len(tabla.cabeceras):
					self.ClearAll()
					for posicion, cabecera in enumerate(tabla.cabeceras):
						self.InsertColumn(posicion, cabecera, width=self.FromDIP(140))
					self.reiniciar_columna()
				self._tabla, self._indices = tabla, list(indices)
				self._num_filas = len(self._indices)
				self.SetItemCount(self._num_filas)
				self.Refresh()
			finally:
				self.Thaw()
			if self._num_filas:
				self.enfocar_fila(0, anunciar=False)

		def indice_tabla(self, fila: int) -> int:
			return self._indices[fila] if 0 <= fila < len(self._indices) else -1

		def texto_celda(self, fila: int, columna: int) -> str:
			if self._tabla is None or not 0 <= fila < len(self._indices):
				return ""
			datos = self._tabla.filas[self._indices[fila]]
			return str(datos[columna]) if columna < len(datos) else ""

		def OnGetItemText(self, item: int, column: int) -> str:  # noqa: N802 - API de wx
			return self.texto_celda(item, column)

		def columna_actual(self) -> int:
			return int(getattr(self, "_columna", 0))

	_CLASES[base] = ListaTabla
	return ListaTabla
