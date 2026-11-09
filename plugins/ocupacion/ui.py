# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventanas de la ocupación del disco (diseño 2.0, 11.8 y 15.1).

Con los controles accesibles de ``zc.ui``: etiqueta antes de cada control,
letras sin repetir, Escape que cierra, Ctrl+H y F1 con la ayuda del complemento.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from app.plugins import api

from . import motor

_ = api.traduccion("zc.ocupacion")[0]


def _boton(padre: wx.Window, etiqueta: str, ayuda: str, identificador: int = wx.ID_ANY) -> wx.Button:
	boton = wx.Button(padre, identificador, etiqueta)
	boton.SetHelpText(ayuda)
	return boton


def _f1(dialogo: wx.Dialog, zc: api.Anfitrion) -> None:
	def al_pulsar(evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F1 and not evento.HasAnyModifiers():
			try:
				zc.abrir_ayuda()
			except api.NoAdmitido:
				zc.registro.debug("Sin ventana para abrir la ayuda", exc_info=True)
			return
		evento.Skip()

	dialogo.Bind(wx.EVT_CHAR_HOOK, al_pulsar)


class DialogoAnalizar(wx.Dialog):
	"""Qué carpeta o unidad se analiza y con qué opciones (Ctrl+Mayús+F7)."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, carpeta: str) -> None:
		super().__init__(padre, title=_("Analizar la ocupación"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo = ui.crear_campo(self, _("&Qué analizar (carpeta o unidad):"), wx.TextCtrl, value=carpeta, sizer=sizer,
			ayuda=_("Carpeta o unidad, como D:\\ o C:\\Usuarios. El análisis se hace como operación y se puede cancelar con F12."))
		self.enlaces = self._casilla(sizer, _("Seguir &enlaces y uniones"), "seguir_enlaces",
			_("Marcado, se cuenta también lo que hay al otro lado de los enlaces y uniones (sin contar dos veces lo mismo)."))
		self.en_disco = self._casilla(sizer, _("Tamaño en el &disco en lugar del tamaño de los archivos"), "tamano_en_disco",
			_("Marcado, se cuenta lo que de verdad ocupa cada archivo en el disco (comprimidos, dispersos y clúster)."))
		self.nube = self._casilla(sizer, _("Incluir archivos de la &nube sin descargar"), "incluir_nube",
			_("Marcado, se cuentan los archivos de OneDrive y similares que no están en este equipo."))
		botones = wx.StdDialogButtonSizer()
		aceptar = _boton(self, _("&Analizar"), _("Empieza el análisis."), wx.ID_OK)
		aceptar.SetDefault()
		botones.AddButton(aceptar)
		botones.AddButton(_boton(self, _("&Cancelar"), _("Cierra sin analizar."), wx.ID_CANCEL))
		botones.Realize()
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.FromDIP(wx.Size(480, -1)))
		ui.preparar_dialogo(self, foco_inicial=self.campo)
		_f1(self, zc)

	def _casilla(self, sizer: wx.Sizer, etiqueta: str, clave: str, ayuda: str) -> wx.CheckBox:
		casilla = wx.CheckBox(self, label=etiqueta)
		casilla.SetValue(bool(self.zc.config.obtener(clave)))
		casilla.SetHelpText(ayuda)
		sizer.Add(casilla, 0, wx.ALL, 5)
		return casilla

	def carpeta(self) -> str:
		return self.campo.GetValue().strip().strip('"')

	def opciones(self) -> motor.Opciones:
		return motor.Opciones(seguir_enlaces=self.enlaces.GetValue(), tamano_en_disco=self.en_disco.GetValue(),
			incluir_nube=self.nube.GetValue(), anios_antiguedad=int(self.zc.config.obtener("anios_antiguedad")))


class DialogoArchivos(wx.Dialog):
	"""Los 100 archivos más grandes o los no modificados en más de N años."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, analisis: motor.Analisis, antiguos: bool = False,
			acciones: dict[str, Callable[[DialogoArchivos], None]] | None = None) -> None:
		super().__init__(padre, title=_("Archivos grandes y antiguos"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self.analisis = analisis
		self.acciones = acciones or {}
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		anios = analisis.opciones.anios_antiguedad
		_e, self.selector = ui.crear_campo(self, _("&Mostrar:"), wx.Choice, sizer=sizer, choices=[
			_("Los {n} archivos más grandes").format(n=motor.MAYORES),
			_("No modificados en más de {n} años").format(n=anios)],
			ayuda=_("Qué lista se ve: los más grandes o los que nadie ha tocado en años, de mayor a menor."))
		self.selector.SetSelection(1 if antiguos else 0)
		_e, self.campo_resumen = ui.crear_campo(self, _("&Resumen:"), wx.TextCtrl, style=wx.TE_READONLY, sizer=sizer,
			ayuda=_("Qué se está viendo y cuánto ocupa."))
		etiqueta = wx.StaticText(self, label=_("&Archivos:"))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.lista = ui.ListaAccesible(self, _("Archivos"), [(_("Nombre"), 240), (_("Tamaño"), 100), (_("Carpeta"), 320),
			(_("Modificado"), 150)])
		sizer.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		for clave, etiqueta_boton, ayuda in (
				("ir", _("&Ir al archivo"), _("Lleva el otro panel a la carpeta del archivo, con el cursor sobre él.")),
				("panel", _("Enviar al &panel"), _("Muestra esta lista en el panel activo como lista de resultados.")),
				("exportar", _("E&xportar..."), _("Guarda esta lista en un archivo de texto o CSV."))):
			boton = _boton(self, etiqueta_boton, ayuda)
			self.Bind(wx.EVT_BUTTON, lambda _e, c=clave: self._accion(c), boton)
			fila.Add(boton, 0, wx.ALL, 3)
		fila.Add(_boton(self, _("C&errar"), _("Cierra la lista."), wx.ID_CLOSE), 0, wx.ALL, 3)
		sizer.Add(fila, 0, wx.ALL, 2)
		self.SetSizer(sizer)
		self.SetSize(self.FromDIP(wx.Size(860, 520)))
		ui.preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista)
		_f1(self, zc)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE), id=wx.ID_CLOSE)
		self.selector.Bind(wx.EVT_CHOICE, lambda _e: self.recargar())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self._accion("ir"))
		self.recargar()

	def archivos(self) -> list[motor.ArchivoGrande]:
		return self.analisis.antiguos if self.selector.GetSelection() == 1 else self.analisis.mayores

	def recargar(self) -> None:
		archivos = self.archivos()
		if self.selector.GetSelection() == 1:
			texto = _("{a} sin modificar en más de {n} años, {t}; se ven los {v} más grandes").format(
				a=api.formato.plural(self.analisis.antiguos_total, _("{n} archivo"), _("{n} archivos")),
				n=self.analisis.opciones.anios_antiguedad, t=api.formato.tamano_legible(self.analisis.antiguos_bytes), v=len(archivos))
		else:
			texto = _("Los {n} archivos más grandes de {r}: {t}").format(n=len(archivos), r=self.analisis.raiz,
				t=api.formato.tamano_legible(sum(a.tamano for a in archivos)))
		self.campo_resumen.SetValue(texto)
		self.lista.reemplazar_filas([[a.nombre, api.formato.tamano_legible(a.tamano), a.carpeta,
			api.formato.fecha(a.modificado, "larga")] for a in archivos], conservar_foco=False)

	def archivo_actual(self) -> motor.ArchivoGrande | None:
		fila = self.lista.fila_actual()
		archivos = self.archivos()
		return archivos[fila] if 0 <= fila < len(archivos) else None

	def _accion(self, clave: str) -> None:
		funcion = self.acciones.get(clave)
		if funcion is not None:
			funcion(self)


class DialogoExtensiones(wx.Dialog):
	"""Cuánto ocupa cada extensión en el análisis."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, analisis: motor.Analisis,
			al_exportar: Callable[[DialogoExtensiones], None] | None = None) -> None:
		super().__init__(padre, title=_("Ocupación por extensión"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self.analisis = analisis
		self._al_exportar = al_exportar
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_resumen = ui.crear_campo(self, _("&Resumen:"), wx.TextCtrl, value=analisis.resumen(), style=wx.TE_READONLY,
			sizer=sizer, ayuda=_("Qué se analizó y cuánto ocupa."))
		etiqueta = wx.StaticText(self, label=_("&Lista de extensiones:"))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.lista = ui.ListaAccesible(self, _("Lista de extensiones"), [(_("Extensión"), 140), (_("Tamaño"), 110),
			(_("Porcentaje"), 100), (_("Archivos"), 100)])
		total = analisis.nodo.tamano
		self.lista.reemplazar_filas([[e, api.formato.tamano_legible(b), motor.porcentaje(b, total), api.formato.miles(a)]
			for e, b, a in analisis.extensiones_ordenadas()], conservar_foco=False)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		exportar = _boton(self, _("E&xportar el informe..."), _("Guarda el informe completo del análisis en texto, o las carpetas en CSV."))
		fila.Add(exportar, 0, wx.ALL, 3)
		fila.Add(_boton(self, _("C&errar"), _("Cierra la lista."), wx.ID_CLOSE), 0, wx.ALL, 3)
		sizer.Add(fila, 0, wx.ALL, 2)
		self.SetSizer(sizer)
		self.SetSize(self.FromDIP(wx.Size(600, 480)))
		ui.preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista)
		_f1(self, zc)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE), id=wx.ID_CLOSE)
		self.Bind(wx.EVT_BUTTON, lambda _e: self._al_exportar(self) if self._al_exportar else None, exportar)


def pedir_archivo(padre: wx.Window, zc: api.Anfitrion, titulo: str, nombre: str) -> str | None:
	"""Diálogo nativo de Guardar como (texto o CSV); ``None`` si se cancela."""
	selector = wx.FileDialog(padre, titulo, defaultFile=nombre,
		wildcard=_("Texto (*.txt)|*.txt|CSV para hojas de cálculo (*.csv)|*.csv"), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
	try:
		if zc.ui.mostrar_modal(selector) != wx.ID_OK:
			return None
		return selector.GetPath()
	finally:
		selector.Destroy()
