# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Registro único de las páginas propias de Preferencias (diseño 2.0, 10.18).

Archivo de N2: ningún bloque lo edita. Los diccionarios ya vienen rellenos con
referencias perezosas en texto (``"módulo:función"``) que el diálogo importa al
abrir la página; cada bloque solo programa su módulo de destino (que N2 deja
provisional):

- ``PAGINAS_PROPIAS``: título de página → fábrica ``crear(padre, config) -> PaginaPropia``.
- ``BOTONES_PAGINA``: título de página → botones (etiqueta, función ``(padre) -> None``)
  que se añaden al final de una página declarativa sin convertirla en propia.

Los diálogos propios de los complementos no son páginas propias: se registran
en tiempo de ejecución con ``registrar_dialogo_complemento`` (la API lo llama
cuando un complemento usa ``zc.preferencias.dialogo``).
"""

from __future__ import annotations

import builtins
import importlib
import logging
from collections.abc import Callable
from typing import Any, Protocol

log = logging.getLogger(__name__)


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class PaginaPropia(Protocol):
	"""Página propia de Preferencias (un ``wx.Panel``)."""

	def validar(self) -> str | None: ...
	def aplicar(self) -> bool: ...
	def restablecer(self) -> None: ...
	def control_inicial(self) -> Any: ...


PAGINAS_PROPIAS: dict[str, str] = {
	N_("Sonidos"): "app.ui.dialogos.so_pagina_sonidos:crear",
	N_("Confirmaciones"): "app.ui.dialogos.pe_confirmaciones:crear",
}

BOTONES_PAGINA: dict[str, list[tuple[str, str]]] = {
	N_("Accesibilidad"): [(N_("Instalar el complemento de zCommander para &NVDA..."), "app.ui.instalar_complemento:abrir")],
	N_("Personalización"): [(N_("Teclas &globales..."), "app.ui.dialogos.pe_teclas_globales:abrir")],
}

_dialogos_complementos: dict[str, Callable[[Any], None]] = {}


def importar(referencia: str) -> Callable[..., Any]:
	"""Resuelve una referencia ``"módulo:función"``."""
	modulo, _dos, funcion = referencia.partition(":")
	return getattr(importlib.import_module(modulo), funcion)


def crear_pagina(titulo: str, padre: Any, config: Any) -> PaginaPropia:
	return importar(PAGINAS_PROPIAS[titulo])(padre, config)


def registrar_dialogo_complemento(id: str, funcion: Callable[[Any], None]) -> None:
	"""Diálogo de configuración avanzada de un complemento (``dialogo_preferencias = true``, 3.6)."""
	_dialogos_complementos[id] = funcion


def dialogo_complemento(id: str) -> Callable[[Any], None] | None:
	return _dialogos_complementos.get(id)


def abrir_preferencias(id: str, padre: Any = None, config: Any = None) -> None:
	"""Abre Preferencias en la página del complemento (``zc.preferencias.abrir``)."""
	from app.ui.dialogos import f_preferencias

	if padre is None or config is None:
		import wx

		padre = padre or (wx.GetApp().GetTopWindow() if wx.GetApp() else None)
		config = config or getattr(padre, "config", None)
	f_preferencias.abrir(padre, config, pagina=f"complemento:{id}")
