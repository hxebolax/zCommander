# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Historial del portapapeles» (diseño 2.0, 11.16). Con wx.

Lo que actúa sobre la ventana principal (pegar en la línea de órdenes o en el
panel) se hace DESPUÉS de cerrar el diálogo: el diálogo devuelve qué se pidió
y con qué elemento, y el complemento lo ejecuta.
"""

from __future__ import annotations

import wx

from app.plugins import api

from . import historial

_, _n = api.traduccion("zc_portapapeles")

COLUMNAS = ((_("Contenido"), 420), (_("Hora"), 130), (_("Fijado"), 70))
#: Teclas que la lista atiende a mano.
TECLAS_PROPIAS = ("Delete",)

# Lo que se pide al cerrar.
PEGAR_LINEA = "linea"
PEGAR_ARCHIVOS = "archivos"
PEGAR_NUEVO = "nuevo"
COPIAR = "copiar"


class DialogoHistorial(wx.Dialog):
	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, datos: historial.Historial) -> None:
		super().__init__(padre, title=_("Historial del portapapeles"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			size=wx.Size(720, 480))
		self.zc = zc
		self.historial = datos
		self.pedido: tuple[str, historial.Elemento] | None = None
		self._visibles: list[historial.Elemento] = []
		ui = zc.ui
		raiz = wx.BoxSizer(wx.VERTICAL)
		_e, self.buscar = ui.crear_campo(self, _("Bu&scar:"), wx.TextCtrl, sizer=raiz,
			ayuda=_("Escriba parte del texto o del nombre de un archivo para ver solo esos elementos."))
		etiqueta = wx.StaticText(self, label=_("&Historial:"))
		self.lista = ui.ListaAccesible(self, _("Historial"), COLUMNAS)
		self.lista.SetHelpText(_("Lo copiado, lo más reciente primero. Intro lo vuelve a poner en el portapapeles; Supr lo borra."))
		raiz.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		botones = wx.GridSizer(2, 5, 5, 5)
		self.boton_linea = self._boton(botones, _("Pegar en la &línea de órdenes"), _("Escribe el texto en la línea de órdenes, sin ejecutarlo."))
		self.boton_archivos = self._boton(botones, _("Pegar como a&rchivos"),
			_("Copia los archivos del elemento a la carpeta del panel."))
		self.boton_nuevo = self._boton(botones, _("Pegar como archivo &nuevo"),
			_("Crea nota.txt con el texto en la carpeta del panel, sin sobrescribir nada."))
		self.boton_copiar = self._boton(botones, _("&Copiar al portapapeles"), _("Vuelve a poner el elemento en el portapapeles (Intro)."))
		self.boton_fijar = self._boton(botones, _("&Fijar o soltar"), _("Un elemento fijado no se borra al llenarse el historial."))
		self.boton_borrar = self._boton(botones, _("&Borrar"), _("Borra el elemento elegido del historial (Supr)."))
		self.boton_todo = self._boton(botones, _("Borrar &todo"), _("Borra todo el historial, también los fijados, con confirmación."))
		self.boton_cerrar = wx.Button(self, wx.ID_CANCEL, _("C&errar"))
		botones.Add(self.boton_cerrar)
		raiz.Add(botones, 0, wx.ALL, 5)
		self.SetSizer(raiz)
		ui.preparar_dialogo(self, foco_inicial=self.lista)
		self.buscar.Bind(wx.EVT_TEXT, lambda _e: self.pintar())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self._pedir(COPIAR))
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda e: (self._habilitar(), e.Skip()))
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
		self.boton_linea.Bind(wx.EVT_BUTTON, lambda _e: self._pedir(PEGAR_LINEA))
		self.boton_archivos.Bind(wx.EVT_BUTTON, lambda _e: self._pedir(PEGAR_ARCHIVOS))
		self.boton_nuevo.Bind(wx.EVT_BUTTON, lambda _e: self._pedir(PEGAR_NUEVO))
		self.boton_copiar.Bind(wx.EVT_BUTTON, lambda _e: self._pedir(COPIAR))
		self.boton_fijar.Bind(wx.EVT_BUTTON, lambda _e: self.fijar())
		self.boton_borrar.Bind(wx.EVT_BUTTON, lambda _e: self.borrar())
		self.boton_todo.Bind(wx.EVT_BUTTON, lambda _e: self.borrar_todo())
		self.pintar()

	def _boton(self, sizer: wx.Sizer, etiqueta: str, ayuda: str) -> wx.Button:
		boton = wx.Button(self, label=etiqueta)
		boton.SetHelpText(ayuda)
		sizer.Add(boton, 0, wx.EXPAND)
		return boton

	def pintar(self, elegir: historial.Elemento | None = None) -> None:
		anterior = elegir or self.elegido()
		self._visibles = self.historial.buscar(self.buscar.GetValue())
		self.lista.reemplazar_filas([[e.contenido, e.hora_texto(), _("Sí") if e.fijado else _("No")] for e in self._visibles],
			conservar_foco=False)
		if anterior is not None:
			fila = next((i for i, e in enumerate(self._visibles) if e.clave == anterior.clave), 0)
			if self._visibles:
				self.lista.enfocar_fila(min(fila, len(self._visibles) - 1), anunciar=False)
		self._habilitar()

	def elegido(self) -> historial.Elemento | None:
		fila = self.lista.fila_actual() if self.lista.numero_filas() else -1
		return self._visibles[fila] if 0 <= fila < len(self._visibles) else None

	def _habilitar(self) -> None:
		elemento = self.elegido()
		hay = elemento is not None
		self.boton_linea.Enable(hay)
		self.boton_archivos.Enable(hay and elemento.tipo == historial.ARCHIVOS)
		self.boton_nuevo.Enable(hay and elemento.tipo == historial.TEXTO)
		for boton in (self.boton_copiar, self.boton_fijar, self.boton_borrar):
			boton.Enable(hay)
		self.boton_todo.Enable(len(self.historial) > 0)

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.borrar()
			return
		evento.Skip()

	def _pedir(self, accion: str) -> None:
		elemento = self.elegido()
		if elemento is None:
			return
		if accion == PEGAR_ARCHIVOS and elemento.tipo != historial.ARCHIVOS:
			return
		if accion == PEGAR_NUEVO and elemento.tipo != historial.TEXTO:
			return
		self.pedido = (accion, elemento)
		self.EndModal(wx.ID_OK) if self.IsModal() else self.Close()

	def fijar(self) -> None:
		elemento = self.elegido()
		if elemento is None:
			return
		nuevo = self.historial.alternar_fijado(elemento)
		self.pintar(nuevo)
		self.zc.anunciar(_("Fijado") if nuevo.fijado else _("Ya no está fijado"), api.RESULTADO)

	def borrar(self) -> None:
		elemento = self.elegido()
		if elemento is None:
			return
		fila = self.lista.fila_actual()
		self.historial.borrar(elemento)
		self.pintar()
		if self._visibles:
			self.lista.enfocar_fila(min(fila, len(self._visibles) - 1), anunciar=False)
		self.zc.anunciar(_("Borrado"), api.RESULTADO)

	def borrar_todo(self) -> None:
		if not self.zc.ui.confirmar(_("¿Borrar todo el historial del portapapeles, también los elementos fijados?"),
				_("Borrar todo"), self, peligroso=True):
			return
		self.historial.borrar_todo()
		self.pintar()
		self.zc.anunciar(_("Historial vacío"), api.RESULTADO)
		self.buscar.SetFocus()
