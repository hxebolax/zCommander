# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Piezas comunes de las ventanas de Nubes (accesibilidad-wx, diseño 2.0, 15).

Las ventanas usan los controles accesibles de zCommander a través de
``zc.ui`` (``crear_campo``, ``crear_botonera``, ``preparar_dialogo``,
``ListaAccesible``...). Sin la ventana de zCommander (``tools/validar_plugin.py``
y algunas pruebas) se usan aquí equivalentes mínimos con las mismas reglas:
etiqueta creada justo antes de cada control, letras de acceso, Escape que
cancela, Ctrl+H con la ayuda del control y F1 con la ayuda del complemento.
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any

import wx

from app.plugins import api

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

_ETIQUETAS = {wx.ID_OK: "&Aceptar", wx.ID_CANCEL: "&Cancelar", wx.ID_YES: "&Sí", wx.ID_NO: "&No", wx.ID_CLOSE: "C&errar",
	wx.ID_APPLY: "A&plicar", wx.ID_HELP: "A&yuda"}


def ui(zc: Any) -> Any | None:
	"""``zc.ui`` si hay ventana de zCommander; ``None`` si no (validación y pruebas sin interfaz)."""
	if api.interfaz() is None:
		return None
	return zc.ui


def letra(etiqueta: str) -> str | None:
	posicion = etiqueta.find("&")
	while posicion != -1 and posicion + 1 < len(etiqueta):
		siguiente = etiqueta[posicion + 1]
		if siguiente != "&":
			return siguiente.casefold()
		posicion = etiqueta.find("&", posicion + 2)
	return None


def con_letra(etiqueta: str, ocupadas: set[str]) -> str:
	"""Pone ``&`` en la primera letra libre de ``etiqueta`` (y la apunta en ``ocupadas``)."""
	limpia = etiqueta.replace("&", "")
	for indice, caracter in enumerate(limpia):
		base = unicodedata.normalize("NFKD", caracter.casefold())[:1]
		if caracter.isalnum() and base.isascii() and base not in ocupadas:
			ocupadas.add(base)
			return limpia[:indice] + "&" + limpia[indice:]
	return limpia


def campo(zc: Any, padre: wx.Window, etiqueta: str, fabrica: Callable[..., Any], *args: Any, ayuda: str = "",
		sizer: wx.Sizer | None = None, **kwargs: Any) -> Any:
	"""Etiqueta y, JUSTO DESPUÉS, su control (el lector toma de ella el nombre). Devuelve el control.

	Para ``wx.TextCtrl`` y ``wx.ComboBox`` el primer argumento es el valor inicial.
	"""
	if args and fabrica in (wx.TextCtrl, wx.ComboBox):
		kwargs["value"] = str(args[0])
		args = args[1:]
	modulo = ui(zc)
	if modulo is not None:
		return modulo.crear_campo(padre, etiqueta, fabrica, *args, ayuda=ayuda, sizer=sizer, **kwargs)[1]
	texto = wx.StaticText(padre, label=etiqueta)
	kwargs.setdefault("name", etiqueta.replace("&", "").rstrip(":"))
	control = fabrica(padre, *args, **kwargs)
	if ayuda:
		control.SetHelpText(ayuda)
	if sizer is not None:
		sizer.Add(texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		sizer.Add(control, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
	return control


def lista(zc: Any, padre: wx.Window, etiqueta: str, columnas: list[tuple[str, int]], *, ayuda: str = "",
		sizer: wx.Sizer | None = None, con_casillas: bool = False, proporcion: int = 1) -> wx.ListCtrl:
	"""``ListaAccesible`` (lectura por columnas) con su etiqueta; ``wx.ListCtrl`` de informe sin la ventana."""
	texto = wx.StaticText(padre, label=etiqueta)
	nombre = etiqueta.replace("&", "").rstrip(":")
	modulo = ui(zc)
	if modulo is not None:
		control = modulo.ListaAccesible(padre, nombre, columnas, con_casillas=con_casillas)
	else:
		control = wx.ListCtrl(padre, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, name=nombre)
		for indice, (cabecera, ancho) in enumerate(columnas):
			control.InsertColumn(indice, cabecera, width=ancho)
		if con_casillas:
			control.EnableCheckBoxes(True)
	if ayuda:
		control.SetHelpText(ayuda)
	if sizer is not None:
		sizer.Add(texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		sizer.Add(control, proporcion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
	return control


def llenar_lista(control: wx.ListCtrl, filas: Iterable[Iterable[str]], seleccion: int = 0) -> None:
	"""Rellena una lista (con o sin ``ListaAccesible``) y deja enfocada la fila ``seleccion``."""
	control.DeleteAllItems()
	cuenta = 0
	for fila in filas:
		valores = [str(v) for v in fila]
		indice = control.InsertItem(control.GetItemCount(), valores[0] if valores else "")
		for columna, valor in enumerate(valores[1:], start=1):
			control.SetItem(indice, columna, valor)
		cuenta += 1
	if cuenta:
		seleccion = max(0, min(seleccion, cuenta - 1))
		control.SetItemState(seleccion, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
		control.EnsureVisible(seleccion)


def fila_actual(control: wx.ListCtrl) -> int:
	fila = control.GetFirstSelected()
	if fila == -1:
		fila = control.GetFocusedItem()
	return fila


def texto_solo_lectura(zc: Any, padre: wx.Window, etiqueta: str, texto: str, *, sizer: wx.Sizer | None = None,
		alto: int = 120, ayuda: str = "") -> wx.TextCtrl:
	"""Texto largo de solo lectura (se puede releer con las flechas)."""
	control = campo(zc, padre, etiqueta, wx.TextCtrl, texto, ayuda=ayuda, sizer=sizer,
		style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=padre.FromDIP(wx.Size(520, alto)))
	return control


def botonera(zc: Any, padre: wx.Window, banderas: int, predeterminado: int | None = None) -> wx.Sizer:
	modulo = ui(zc)
	if modulo is not None:
		return modulo.crear_botonera(padre, banderas, predeterminado)
	sizer = wx.StdDialogButtonSizer()
	botones = {}
	for bandera, identificador in ((wx.OK, wx.ID_OK), (wx.YES, wx.ID_YES), (wx.NO, wx.ID_NO), (wx.CANCEL, wx.ID_CANCEL),
			(wx.APPLY, wx.ID_APPLY), (wx.CLOSE, wx.ID_CLOSE), (wx.HELP, wx.ID_HELP)):
		if banderas & bandera:
			botones[identificador] = wx.Button(padre, identificador, _(_ETIQUETAS[identificador]))
			sizer.AddButton(botones[identificador])
	sizer.Realize()
	elegido = predeterminado or (wx.ID_OK if wx.ID_OK in botones else wx.ID_YES)
	if elegido in botones:
		botones[elegido].SetDefault()
	return sizer


def boton(padre: wx.Window, etiqueta: str, ayuda: str, accion: Callable[[], None] | None = None, *,
		sizer: wx.Sizer | None = None, identificador: int = wx.ID_ANY) -> wx.Button:
	control = wx.Button(padre, identificador, etiqueta)
	control.SetHelpText(ayuda)
	if accion is not None:
		control.Bind(wx.EVT_BUTTON, lambda _e: accion())
	if sizer is not None:
		sizer.Add(control, 0, wx.ALL, 4)
	return control


def casilla(padre: wx.Window, etiqueta: str, ayuda: str, valor: bool = False, *, sizer: wx.Sizer | None = None) -> wx.CheckBox:
	control = wx.CheckBox(padre, label=etiqueta)
	control.SetValue(bool(valor))
	control.SetHelpText(ayuda)
	if sizer is not None:
		sizer.Add(control, 0, wx.ALL, 5)
	return control


def elegir(zc: Any, padre: wx.Window, etiqueta: str, opciones: list[tuple[str, str]], valor: str = "", *, ayuda: str = "",
		sizer: wx.Sizer | None = None) -> wx.Choice:
	"""Desplegable con (valor, texto); ``valor_elegido(control)`` devuelve el valor."""
	control = campo(zc, padre, etiqueta, wx.Choice, ayuda=ayuda, sizer=sizer, choices=[t for _v, t in opciones])
	control.valores = [v for v, _t in opciones]  # type: ignore[attr-defined]
	if valor in control.valores:  # type: ignore[attr-defined]
		control.SetSelection(control.valores.index(valor))  # type: ignore[attr-defined]
	elif opciones:
		control.SetSelection(0)
	return control


def valor_elegido(control: wx.Choice) -> str:
	indice = control.GetSelection()
	valores = getattr(control, "valores", [])
	return valores[indice] if 0 <= indice < len(valores) else ""


class DialogoNubes(wx.Dialog):
	"""Base de los diálogos del complemento: Escape cancela, Ctrl+H explica el control y F1 abre la ayuda."""

	def __init__(self, zc: Any, padre: wx.Window | None, titulo: str, *, estilo: int = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER) -> None:
		super().__init__(padre, title=titulo, style=estilo, name=titulo)
		self.zc = zc
		self.panel = wx.Panel(self)
		self.sizer = wx.BoxSizer(wx.VERTICAL)
		self.panel.SetSizer(self.sizer)
		externo = wx.BoxSizer(wx.VERTICAL)
		externo.Add(self.panel, 1, wx.EXPAND)
		self.SetSizer(externo)

	def terminar(self, foco: wx.Window | None = None, id_escape: int = wx.ID_CANCEL) -> None:
		"""Ajusta el tamaño y prepara Escape, Ctrl+H, F1 y el foco inicial."""
		self.panel.Layout()
		self.GetSizer().Fit(self)
		self.SetMinSize(self.GetSize())
		modulo = ui(self.zc)
		if modulo is not None:
			modulo.preparar_dialogo(self, id_escape=id_escape, foco_inicial=foco)
		else:
			self.SetEscapeId(id_escape)
			if foco is not None:
				self.Bind(wx.EVT_INIT_DIALOG, lambda evento: (foco.SetFocus(), evento.Skip()))
		self.Bind(wx.EVT_CHAR_HOOK, self._tecla_ayuda)
		self.CentreOnParent()

	def _tecla_ayuda(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F1 and not evento.HasAnyModifiers():
			try:
				self.zc.abrir_ayuda()
			except api.NoAdmitido:
				log.debug("Sin ventana para abrir la ayuda", exc_info=True)
			return
		evento.Skip()

	def botones(self, banderas: int, predeterminado: int | None = None) -> wx.Sizer:
		sizer = botonera(self.zc, self.panel, banderas, predeterminado)
		self.sizer.Add(sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		return sizer


def mostrar_modal(zc: Any, dialogo: wx.Dialog) -> int:
	modulo = ui(zc)
	if modulo is not None:
		return modulo.mostrar_modal(dialogo)
	return dialogo.ShowModal()


def avisar(zc: Any, texto: str, titulo: str = "") -> None:
	modulo = ui(zc)
	if modulo is not None:
		modulo.mostrar_mensaje(texto, titulo or _("Nubes"))
	else:
		zc.anunciar(texto, api.RESULTADO)


def error(zc: Any, texto: str, titulo: str = "") -> None:
	modulo = ui(zc)
	if modulo is not None:
		modulo.mostrar_error(texto, titulo or _("Nubes"))
	else:
		zc.anunciar(texto, api.ESENCIAL)


def confirmar(zc: Any, texto: str, titulo: str = "", *, peligroso: bool = False) -> bool:
	"""Pregunta sí o no; con ``peligroso`` el foco empieza en la opción segura (15.1)."""
	modulo = ui(zc)
	if modulo is None:
		return False
	return bool(modulo.confirmar(texto, titulo or _("Nubes"), peligroso=peligroso))


def opcion(zc: Any, texto: str, titulo: str, opciones: list[str]) -> int | None:
	modulo = ui(zc)
	if modulo is None:
		return None
	return modulo.elegir_opcion(texto, titulo, opciones)


def pedir(zc: Any, etiqueta: str, titulo: str, valor: str = "") -> str | None:
	modulo = ui(zc)
	if modulo is None:
		return None
	return modulo.pedir_texto(etiqueta, titulo, valor)


def copiar_al_portapapeles(texto: str) -> bool:
	if not wx.TheClipboard.Open():
		return False
	try:
		return bool(wx.TheClipboard.SetData(wx.TextDataObject(texto)))
	finally:
		wx.TheClipboard.Close()


def abrir_navegador(url: str) -> bool:
	import webbrowser

	try:
		return bool(webbrowser.open(url, new=2))
	except webbrowser.Error:
		log.warning("No se pudo abrir el navegador", exc_info=True)
		return False
