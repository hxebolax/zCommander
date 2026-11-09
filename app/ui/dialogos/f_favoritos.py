# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Favoritos (Ctrl+D): lista con nombre y ruta; Intro va.

Desde el diálogo se añade la carpeta actual, se renombra, se ordena y se
borra. Cada cambio se guarda al momento en ``favoritos.json``: aquí no hay
Aceptar que pueda olvidarse, y cerrar con Escape no debe perder un favorito
recién añadido. Si no se puede guardar, se avisa y la lista sigue en memoria.
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import favoritos
from app.services.favoritos import Favorito
from app.ui import anuncios
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def guardar(padre: wx.Window | None, lista: list[Favorito]) -> bool:
	"""Guarda y avisa si no se puede (disco lleno, permisos)."""
	try:
		favoritos.guardar(lista)
		return True
	except OSError as error:
		log.error("No se pudieron guardar los favoritos", exc_info=True)
		f_comun.avisar(padre, _("No se pudieron guardar los favoritos: {e}").format(e=error), _("Favoritos"))
		return False


class DialogoFavoritos(f_comun.DialogoF):
	"""``elegido`` queda con el favorito al que ir (o ``None``)."""

	def __init__(self, padre: wx.Window | None, lista: list[Favorito], ruta_actual: str) -> None:
		super().__init__(padre, _("Favoritos"))
		self.favoritos = lista
		self.ruta_actual = ruta_actual
		self.elegido: Favorito | None = None
		self.etiqueta_lista = wx.StaticText(self.panel, label=_("&Favoritos:"))
		self.lista = ListaAccesible(self.panel, _("Favoritos"), columnas=[(_("Nombre"), self.FromDIP(180)), (_("Ruta"), self.FromDIP(340))])
		self.lista.SetMinSize(self.FromDIP(wx.Size(540, 240)))
		self.lista.SetHelpText(_("Intro va a la carpeta. Izquierda y Derecha leen nombre y ruta."))
		self.sizer.Add(self.etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_ir = self.boton(_("&Ir"), _("Lleva el panel activo a la carpeta del favorito."), self.ir, fila)
		self.boton(_("Aña&dir la carpeta actual..."), _("Añade a favoritos la carpeta del panel activo pidiendo un nombre."),
			self.anadir_actual, fila)
		self.boton(_("&Renombrar..."), _("Cambia el nombre del favorito elegido."), self.renombrar, fila)
		self.boton(_("&Subir"), _("Sube el favorito una posición."), lambda: self.mover(-1), fila)
		self.boton(_("&Bajar"), _("Baja el favorito una posición."), lambda: self.mover(1), fila)
		self.boton(_("E&liminar"), _("Quita el favorito elegido (la carpeta no se toca)."), self.eliminar, fila)
		self.sizer.Add(fila, 0)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.ir())
		self.terminar(wx.CLOSE, foco=self.lista, id_escape=wx.ID_CLOSE)
		self.FindWindow(wx.ID_CLOSE).Bind(wx.EVT_BUTTON, lambda _e: self.cerrar(wx.ID_CLOSE))
		self.boton_ir.SetDefault()
		self._rellenar(0)

	def _rellenar(self, foco: int) -> None:
		self.lista.reemplazar_filas([[f.nombre, f.ruta] for f in self.favoritos], conservar_foco=False)
		if self.favoritos:
			self.lista.enfocar_fila(min(max(foco, 0), len(self.favoritos) - 1), anunciar=False)
		self.boton_ir.Enable(bool(self.favoritos))

	def indice(self) -> int:
		fila = self.lista.fila_actual()
		return fila if 0 <= fila < len(self.favoritos) else -1

	def ir(self) -> None:
		i = self.indice()
		if i < 0:
			return
		self.elegido = self.favoritos[i]
		self.cerrar(wx.ID_OK)

	def anadir_actual(self) -> None:
		nombre = f_comun.pedir(self, _("&Nombre del favorito:"), _("Añadir a favoritos"), favoritos.nombre_sugerido(self.ruta_actual))
		if nombre is None:
			return
		indice = favoritos.agregar(self.favoritos, nombre, self.ruta_actual)
		if guardar(self, self.favoritos):
			anuncios.anunciar(_("Añadido a favoritos: {n}").format(n=self.favoritos[indice].nombre), anuncios.RESULTADO)
		self._rellenar(indice)
		self.lista.SetFocus()

	def renombrar(self) -> None:
		i = self.indice()
		if i < 0:
			return
		nombre = f_comun.pedir(self, _("&Nombre del favorito:"), _("Renombrar el favorito"), self.favoritos[i].nombre)
		if not nombre or not nombre.strip():
			self.lista.SetFocus()
			return
		favoritos.renombrar(self.favoritos, i, nombre)
		guardar(self, self.favoritos)
		self._rellenar(i)
		self.lista.SetFocus()

	def mover(self, paso: int) -> None:
		i = self.indice()
		if i < 0:
			return
		destino = favoritos.mover(self.favoritos, i, paso)
		if destino == i:
			return
		guardar(self, self.favoritos)
		self._rellenar(destino)
		self.lista.SetFocus()
		anuncios.anunciar(_("Posición {n} de {t}").format(n=destino + 1, t=len(self.favoritos)), anuncios.RESULTADO)

	def eliminar(self) -> None:
		i = self.indice()
		if i < 0:
			return
		favorito = self.favoritos[i]
		if not f_comun.preguntar(self, _("¿Quitar «{n}» de favoritos? La carpeta no se borra.").format(n=favorito.nombre),
				_("Eliminar el favorito"), peligroso=True):
			return
		favoritos.eliminar(self.favoritos, i)
		guardar(self, self.favoritos)
		self._rellenar(i)
		self.lista.SetFocus()
		anuncios.anunciar(_("Quitado de favoritos: {n}").format(n=favorito.nombre), anuncios.RESULTADO)


def elegir_favorito(padre: wx.Window | None, ruta_actual: str) -> Favorito | None:
	dialogo = DialogoFavoritos(padre, favoritos.cargar(), ruta_actual)
	return f_comun.mostrar(dialogo, lambda d: d.elegido)
