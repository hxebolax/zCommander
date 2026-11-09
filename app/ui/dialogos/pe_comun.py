# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Piezas comunes de los diálogos del bloque PE (personalización).

- ``DialogoListaPE``: una lista multicolumna (``ListaAccesible``) con su
  etiqueta creada antes y una fila de botones; cada subclase da sus filas.
  Los cambios se guardan al momento (como Favoritos): cerrar con Escape no
  pierde nada ya hecho.
- ``elegir_de_lista`` y ``elegir_orden`` (el buscador de la paleta) para
  elegir sin escribir identificadores.
- Las preguntas pasan por ``f_comun`` (las pruebas las sustituyen).
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Sequence

import wx

from app.ui import anuncios
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoListaPE(f_comun.DialogoF):
	"""Lista con botones. Las subclases implementan ``filas()`` y crean sus botones con ``self.boton``.

	:param columnas: ``[(cabecera, ancho DIP), ...]``.
	"""

	def __init__(self, padre: wx.Window | None, titulo: str, etiqueta: str, columnas: Sequence[tuple[str, int]],
			ayuda_lista: str = "") -> None:
		super().__init__(padre, titulo)
		self.etiqueta_lista = wx.StaticText(self.panel, label=etiqueta)
		self.lista = ListaAccesible(self.panel, f_comun.texto_limpio(etiqueta).rstrip(":"),
			columnas=[(c, self.FromDIP(a)) for c, a in columnas])
		self.lista.SetMinSize(self.FromDIP(wx.Size(sum(a for _c, a in columnas) + 20, 220)))
		if ayuda_lista:
			self.lista.SetHelpText(ayuda_lista)
		self.sizer.Add(self.etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		self.botonera = wx.WrapSizer(wx.HORIZONTAL)

	def cerrar_lista(self, foco: wx.Window | None = None) -> None:
		"""Pone la botonera y «Cerrar» (Escape)."""
		self.sizer.Add(self.botonera, 0, wx.EXPAND)
		self.terminar(wx.CLOSE, foco=foco or self.lista, id_escape=wx.ID_CLOSE)
		self.FindWindow(wx.ID_CLOSE).Bind(wx.EVT_BUTTON, lambda _e: self.cerrar(wx.ID_CLOSE))

	def filas(self) -> list[list[str]]:
		"""Filas de la lista (cada subclase da las suyas)."""
		return []

	def rellenar(self, foco: int = 0) -> None:
		filas = self.filas()
		self.lista.reemplazar_filas(filas, conservar_foco=False)
		if filas:
			self.lista.enfocar_fila(min(max(foco, 0), len(filas) - 1), anunciar=False)

	def indice(self) -> int:
		fila = self.lista.fila_actual()
		return fila if 0 <= fila < self.lista.GetItemCount() else -1

	def anunciar_posicion(self, indice: int, total: int, nombre: str = "") -> None:
		texto = _("Posición {n} de {t}").format(n=indice + 1, t=total)
		anuncios.anunciar(f"{nombre}, {texto}" if nombre else texto, anuncios.RESULTADO)


class DialogoElegir(f_comun.DialogoF):
	"""Elegir una opción de una lista sencilla. ``elegida`` queda con el índice."""

	def __init__(self, padre: wx.Window | None, titulo: str, etiqueta: str, opciones: Sequence[str]) -> None:
		super().__init__(padre, titulo)
		self.elegida: int | None = None
		_e, self.lista = crear_campo(self.panel, etiqueta, wx.ListBox, choices=list(opciones), size=self.FromDIP(wx.Size(420, 240)),
			sizer=self.sizer, ayuda=_("Elija con las flechas y pulse Intro."))
		if opciones:
			self.lista.SetSelection(0)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.aceptar())
		self.terminar(wx.OK | wx.CANCEL, foco=self.lista)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())

	def aceptar(self) -> None:
		indice = self.lista.GetSelection()
		if indice != wx.NOT_FOUND:
			self.elegida = indice
			self.cerrar(wx.ID_OK)


def elegir_de_lista(padre: wx.Window | None, titulo: str, etiqueta: str, opciones: Sequence[str]) -> int | None:
	return f_comun.mostrar(DialogoElegir(padre, titulo, etiqueta, opciones), lambda d: d.elegida)


def elegir_orden(padre: wx.Window | None, titulo: str) -> str | None:
	"""Una orden del catálogo elegida con el buscador de la paleta (sin ejecutarla)."""
	from app.ui.dialogos import f_paleta

	mapa = getattr(padre, "mapa_teclas", None)
	if mapa is None and padre is not None:
		mapa = getattr(wx.GetTopLevelParent(padre), "mapa_teclas", None)
	return f_paleta.elegir_orden(padre, mapa, para_elegir=True, titulo=titulo)


def guardar_con_aviso(padre: wx.Window | None, guardar: Callable[[], None], titulo: str) -> bool:
	"""Guarda y avisa si no se puede (disco lleno, permisos)."""
	try:
		guardar()
		return True
	except OSError as error:
		log.error("No se pudo guardar (%s)", titulo, exc_info=True)
		f_comun.avisar(padre, _("No se pudo guardar: {e}").format(e=error), titulo)
		return False
