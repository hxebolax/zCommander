# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tipos de datos de las vistas por carpeta y de las reglas (diseño 2.0, 10.4 y 10.10). Sin wx.

Los define N2 para que el panel (``PanelArchivos.aplicar_conjunto``) y la
lista (``ListaArchivos.fijar_decorador_fila``) tengan ya su contrato; PE los
usa en ``vistas_carpeta.py`` y ``reglas.py`` sin tocar la interfaz.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

#: Como mucho 15 columnas se leen al moverse (codificación de 10.5 en 64 bits).
MAX_COLUMNAS_LECTURA = 15


@dataclass(frozen=True)
class ConjuntoVista:
	"""Un conjunto de columnas y vista con nombre, el de ``vistas_carpeta.json`` (10.4).

	:param columnas: ids de columna (``nombre``, ``zc.metadatos:artista``...).
	:param anchos: ancho en píxeles DIP por id de columna.
	:param lectura: columnas que se leen al moverse, en su orden (10.5); vacía = el de ``columnas``.
	"""

	nombre: str
	columnas: tuple[str, ...] = ()
	anchos: dict[str, int] = field(default_factory=dict)
	orden: str = "nombre"
	inverso: bool = False
	vista: str = "completa"
	filtro: str = ""
	lectura: tuple[str, ...] = ()

	@classmethod
	def desde_dict(cls, datos: dict[str, Any]) -> ConjuntoVista:
		return cls(
			nombre=str(datos.get("nombre", "")),
			columnas=tuple(str(c) for c in datos.get("columnas", ()) or ()),
			anchos={str(k): int(v) for k, v in (datos.get("anchos") or {}).items()},
			orden=str(datos.get("orden", "nombre")),
			inverso=bool(datos.get("inverso", False)),
			vista=str(datos.get("vista", "completa")),
			filtro=str(datos.get("filtro", "")),
			lectura=tuple(str(c) for c in datos.get("lectura", ()) or ())[:MAX_COLUMNAS_LECTURA],
		)

	def como_dict(self) -> dict[str, Any]:
		datos = asdict(self)
		datos["columnas"] = list(self.columnas)
		datos["lectura"] = list(self.lectura)
		return datos


@dataclass(frozen=True)
class EfectoFila:
	"""Efectos de la primera regla que coincide con una fila (10.10).

	:param color: nombre de uno de los seis colores del tema («Rojo», «Verde»...) o ``None``.
	:param texto: palabra corta de la columna «Regla».
	:param sonido: ``regla.a``, ``regla.b`` o ``regla.c`` (al llegar el cursor), o vacío.
	:param anuncio: frase que se dice tras lo que lee el lector (nivel detalle), o vacía.
	"""

	color: str | None = None
	texto: str = ""
	sonido: str = ""
	anuncio: str = ""
