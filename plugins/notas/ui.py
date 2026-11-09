# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventanas de notas, comentarios y etiquetas (diseño 2.0, 11.14 y 15.1).

Con los controles accesibles de ``zc.ui``: etiqueta antes de cada control,
letras sin repetir, Escape que cancela, Ctrl+H y F1 con la ayuda del complemento.
"""

from __future__ import annotations

import wx

from app.plugins import api

from . import motor

_ = api.traduccion("zc.notas")[0]

#: Lo que devuelve ``DialogoComentario`` al pulsar «Quitar el comentario».
ID_QUITAR = wx.ID_DELETE


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


class DialogoComentario(wx.Dialog):
	"""Edita el comentario de un elemento o la nota de una carpeta (varias líneas)."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, nombre: str, texto: str, es_nota: bool = False) -> None:
		titulo = _("Nota de la carpeta {n}") if es_nota else _("Comentario de {n}")
		super().__init__(padre, title=titulo.format(n=nombre), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = _("&Texto de la nota:") if es_nota else _("&Texto del comentario:")
		_e, self.campo = ui.crear_campo(self, etiqueta, wx.TextCtrl, value=texto, style=wx.TE_MULTILINE, sizer=sizer,
			ayuda=_("Puede tener varias líneas: Intro empieza una línea nueva. Tab lleva a los botones."))
		self.campo.SetMinSize(self.FromDIP(wx.Size(460, 140)))
		botones = wx.BoxSizer(wx.HORIZONTAL)
		guardar = _boton(self, _("&Guardar"), _("Guarda el texto (vacío lo quita)."), wx.ID_OK)
		guardar.SetDefault()
		quitar = _boton(self, _("&Quitar"), _("Borra el comentario o la nota."), ID_QUITAR)
		quitar.Enable(bool(texto))
		cancelar = _boton(self, _("&Cancelar"), _("Cierra sin cambiar nada."), wx.ID_CANCEL)
		for boton in (guardar, quitar, cancelar):
			botones.Add(boton, 0, wx.ALL, 3)
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 3)
		self.SetSizerAndFit(sizer)
		ui.preparar_dialogo(self, foco_inicial=self.campo)
		_f1(self, zc)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(ID_QUITAR), id=ID_QUITAR)

	def texto(self) -> str:
		return self.campo.GetValue()


class DialogoEtiquetas(wx.Dialog):
	"""Pone y quita etiquetas a los elementos de trabajo; crea etiquetas nuevas con nombre y color."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, definidas: list[dict], marcadas: set[str], cuantos: int) -> None:
		super().__init__(padre, title=_("Etiquetas"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self.definidas = [dict(d) for d in definidas]
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		texto = api.formato.plural(cuantos, _("{n} elemento"), _("{n} elementos"))
		etiqueta = wx.StaticText(self, label=_("&Etiquetas de {q}:").format(q=texto))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.lista = ui.CheckListBoxAccesible(self, _("Etiquetas"), self._textos())
		self.lista.SetHelpText(_("Espacio marca o desmarca la etiqueta. Al aceptar, las marcadas se ponen a todos los elementos; "
			"las que tenían todos y desmarque se quitan."))
		for indice, definida in enumerate(self.definidas):
			self.lista.Check(indice, definida["nombre"] in marcadas)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		self.boton_nueva = _boton(self, _("&Nueva etiqueta..."), _("Crea una etiqueta con nombre y color, y la deja marcada."))
		sizer.Add(self.boton_nueva, 0, wx.ALL, 5)
		botones = ui.crear_botonera(self, wx.OK | wx.CANCEL)
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.FromDIP(wx.Size(420, 300)))
		ui.preparar_dialogo(self, foco_inicial=self.lista)
		_f1(self, zc)
		self.Bind(wx.EVT_BUTTON, self._al_nueva, self.boton_nueva)
		if self.lista.GetCount():
			self.lista.SetSelection(0)

	def _textos(self) -> list[str]:
		return [motor.texto_etiquetas([d["nombre"]], self.definidas) for d in self.definidas]

	def _al_nueva(self, _evento: wx.CommandEvent) -> None:
		nombre = self.zc.ui.pedir_texto(_("&Nombre de la etiqueta:"), _("Nueva etiqueta"), padre=self)
		nombre = (nombre or "").strip()
		if not nombre:
			return
		if any(d["nombre"].casefold() == nombre.casefold() for d in self.definidas):
			indice = next(i for i, d in enumerate(self.definidas) if d["nombre"].casefold() == nombre.casefold())
		else:
			color = self.zc.ui.elegir_opcion(_("¿De qué color es la etiqueta {n}? El color siempre se dice también en texto.").format(n=nombre),
				_("Color de la etiqueta"), motor.textos_colores(), self)
			self.definidas.append({"nombre": nombre, "color": motor.COLORES[color] if color is not None else ""})
			self.lista.Append(self._textos()[-1])
			indice = len(self.definidas) - 1
		self.lista.Check(indice, True)
		self.lista.SetSelection(indice)
		self.lista.SetFocus()

	def elegidas(self) -> list[str]:
		return [d["nombre"] for i, d in enumerate(self.definidas) if self.lista.IsChecked(i)]


class DialogoBuscar(wx.Dialog):
	"""Buscar por comentario y por etiqueta (también sirve de filtro por etiqueta)."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, carpeta: str, definidas: list[dict]) -> None:
		super().__init__(padre, title=_("Buscar por etiqueta o comentario"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		ui = zc.ui
		self.definidas = definidas
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.texto = ui.crear_campo(self, _("&Texto que contiene el comentario:"), wx.TextCtrl, sizer=sizer,
			ayuda=_("Parte del comentario o de la nota. Vacío: solo cuenta la etiqueta."))
		_e, self.etiqueta = ui.crear_campo(self, _("&Etiqueta:"), wx.Choice, sizer=sizer,
			choices=[_("Cualquiera")] + [motor.texto_etiquetas([d["nombre"]], definidas) for d in definidas],
			ayuda=_("Solo los elementos con esta etiqueta. Con el texto vacío, es un filtro por etiqueta."))
		self.etiqueta.SetSelection(0)
		_e, self.carpeta = ui.crear_campo(self, _("&Dónde buscar:"), wx.TextCtrl, value=carpeta, sizer=sizer,
			ayuda=_("Carpeta en la que se busca."))
		self.subcarpetas = wx.CheckBox(self, label=_("Incluir &subcarpetas"))
		self.subcarpetas.SetValue(True)
		self.subcarpetas.SetHelpText(_("Marcado, se busca también dentro de las subcarpetas."))
		sizer.Add(self.subcarpetas, 0, wx.ALL, 5)
		botones = wx.StdDialogButtonSizer()
		buscar = _boton(self, _("&Buscar"), _("Busca y muestra los resultados como lista en el panel activo."), wx.ID_OK)
		buscar.SetDefault()
		botones.AddButton(buscar)
		botones.AddButton(_boton(self, _("&Cancelar"), _("Cierra sin buscar."), wx.ID_CANCEL))
		botones.Realize()
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.FromDIP(wx.Size(460, -1)))
		ui.preparar_dialogo(self, foco_inicial=self.texto)
		_f1(self, zc)

	def criterios(self) -> tuple[str, str, str, bool]:
		indice = self.etiqueta.GetSelection()
		etiqueta = self.definidas[indice - 1]["nombre"] if indice > 0 else ""
		return self.texto.GetValue(), etiqueta, self.carpeta.GetValue().strip().strip('"'), self.subcarpetas.GetValue()
