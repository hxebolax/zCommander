# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Árbol de carpetas (Alt+F10): elegir una carpeta de la unidad actual en un árbol.

Usa el ``ArbolCarpetas`` del núcleo (árbol nativo, cargado bajo demanda en
hilos, búsqueda tecleando) y le añade los botones Ir, Crear carpeta,
Renombrar y Eliminar. Moverse por el árbol NO lleva el panel a ningún sitio:
solo Ir (o Intro) lo hace, al cerrar el diálogo.

Crear es una tarea corta en un hilo; renombrar y eliminar son operaciones del
motor (``lanzar``), con su deshacer y su papelera. Al terminar, la rama se
vuelve a leer para que el árbol muestre el cambio.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from typing import Any

import wx

from app.core.tareas import GestorTareas
from app.services.vfs.base import Proveedor
from app.ui import anuncios
from app.ui.arbol_carpetas import ArbolCarpetas
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _mensaje(error: BaseException) -> str:
	return getattr(error, "mensaje", None) or str(error)


class DialogoArbol(f_comun.DialogoF):
	"""``elegida`` queda con la carpeta a la que ir.

	:param lanzar: ``lanzar(operacion, al_terminar)`` para renombrar y eliminar
		con el motor de operaciones (``ctx.lanzar``).
	:param papelera: Eliminar envía a la papelera (``general.usar_papelera``).
	"""

	def __init__(self, padre: wx.Window | None, proveedor: Proveedor, raiz: str, ruta_inicial: str, tareas: GestorTareas,
			lanzar: Callable[[Any, Callable[[Any], None]], None] | None = None, papelera: bool = True) -> None:
		super().__init__(padre, _("Árbol de carpetas"))
		self.proveedor = proveedor
		self.tareas = tareas
		self._lanzar = lanzar
		self.papelera = papelera
		self.elegida: str | None = None
		# Sin pausa ni efecto: en el diálogo, moverse no elige; elegir es Ir.
		self.arbol = ArbolCarpetas(self.panel, _("Ár&bol de carpetas:"), proveedor, raiz, lambda _ruta: None, tareas, retardo_ms=0)
		self.arbol.SetMinSize(self.FromDIP(wx.Size(460, 340)))
		self.sizer.Add(self.arbol, 1, wx.EXPAND | wx.ALL, self.FromDIP(4))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_ir = self.boton(_("&Ir"), _("Cierra el árbol y lleva el panel a la carpeta elegida."), self.ir, fila)
		escribir = proveedor.capacidades.escribir
		self.boton_crear = self.boton(_("Crear car&peta..."), _("Crea una carpeta dentro de la elegida."), self.crear, fila)
		self.boton_renombrar = self.boton(_("&Renombrar..."), _("Cambia el nombre de la carpeta elegida."), self.renombrar, fila)
		self.boton_eliminar = self.boton(_("E&liminar"), _("Elimina la carpeta elegida y su contenido; pide confirmación."), self.eliminar, fila)
		for boton in (self.boton_crear, self.boton_renombrar, self.boton_eliminar):
			boton.Enable(bool(escribir))
		self.sizer.Add(fila, 0)
		self.arbol.arbol.Bind(wx.EVT_TREE_ITEM_ACTIVATED, lambda _e: self.ir())
		self.terminar(wx.CLOSE, foco=self.arbol.control_enfocable(), id_escape=wx.ID_CLOSE)
		self.FindWindow(wx.ID_CLOSE).Bind(wx.EVT_BUTTON, lambda _e: self.cerrar(wx.ID_CLOSE))
		self.boton_ir.SetDefault()
		if ruta_inicial:
			self.arbol.ir_a(ruta_inicial)

	def ruta(self) -> str | None:
		return self.arbol.ruta_elegida()

	def ir(self) -> None:
		ruta = self.ruta()
		if ruta is None:
			anuncios.anunciar(_("Elija una carpeta del árbol"), anuncios.RESULTADO)
			return
		self.elegida = ruta
		self.cerrar(wx.ID_OK)

	# ── Crear, renombrar, eliminar ───────────────────────────────────────────

	def crear(self) -> None:
		carpeta = self.ruta()
		if carpeta is None:
			return
		from app.ui.dialogos.nombre import pedir_nombre

		nombre = pedir_nombre(self, _("Crear carpeta"), _("&Nombre de la carpeta:"), "", seleccionar_sin_extension=False)
		if not nombre:
			return
		nueva = self.proveedor.unir(carpeta, nombre)

		def trabajo(_tarea):
			self.proveedor.crear_carpeta(nueva)
			return nueva

		def listo(_ruta) -> None:
			if not self:
				return
			anuncios.anunciar(_("Carpeta creada: {n}").format(n=nombre), anuncios.RESULTADO)
			self.arbol.refrescar(carpeta)
			self.arbol.ir_a(nueva)

		self.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda e: anuncios.anunciar(_mensaje(e), anuncios.ESENCIAL),
			nombre="arbol-crear")

	def renombrar(self) -> None:
		ruta = self.ruta()
		padre = self.proveedor.padre(ruta) if ruta else None
		if ruta is None or padre is None or self._lanzar is None:
			anuncios.anunciar(_("Esta carpeta no se puede renombrar"), anuncios.RESULTADO)
			return
		from app.services.operaciones.renombrar import OperacionRenombrar
		from app.ui.dialogos.nombre import pedir_nombre

		actual = self.proveedor.nombre(ruta)
		nombre = pedir_nombre(self, _("Renombrar la carpeta"), _("&Nombre nuevo:"), actual, seleccionar_sin_extension=False)
		if not nombre or nombre == actual:
			return

		def al_terminar(operacion) -> None:
			if not self:
				return
			self.arbol.refrescar(padre)
			if getattr(operacion.estado, "value", "") == "terminada":
				self.arbol.ir_a(self.proveedor.unir(padre, nombre))

		self._lanzar(OperacionRenombrar(self.proveedor, [(ruta, nombre)]), al_terminar)

	def eliminar(self) -> None:
		ruta = self.ruta()
		padre = self.proveedor.padre(ruta) if ruta else None
		if ruta is None or padre is None or self._lanzar is None:
			anuncios.anunciar(_("Esta carpeta no se puede eliminar"), anuncios.RESULTADO)
			return
		nombre = self.proveedor.nombre(ruta)
		texto = (_("¿Enviar la carpeta «{n}» y todo su contenido a la papelera?") if self.papelera
			else _("¿Eliminar DEFINITIVAMENTE la carpeta «{n}» y todo su contenido? No se puede deshacer.")).format(n=nombre)
		if not f_comun.preguntar(self, texto, _("Eliminar"), peligroso=True):
			return
		from app.services.operaciones.eliminar import OperacionEliminar

		def trabajo(_tarea):
			return self.proveedor.info(ruta)

		def al_terminar(_operacion) -> None:
			if self:
				self.arbol.refrescar(padre)
				self.arbol.ir_a(padre)

		def listo(entrada) -> None:
			if self and self._lanzar is not None:
				self._lanzar(OperacionEliminar(self.proveedor, [entrada], self.papelera), al_terminar)

		self.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda e: anuncios.anunciar(_mensaje(e), anuncios.ESENCIAL),
			nombre="arbol-eliminar")


def elegir_carpeta(padre: wx.Window | None, proveedor: Proveedor, raiz: str, ruta_inicial: str, tareas: GestorTareas,
		lanzar=None, papelera: bool = True) -> str | None:
	dialogo = DialogoArbol(padre, proveedor, raiz, ruta_inicial, tareas, lanzar, papelera)
	return f_comun.mostrar(dialogo, lambda d: d.elegida)
