# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo del organizador por metadatos (diseño 2.0, 11.23 y 15.1).

La vista previa (Nombre actual, Destino nuevo, Estado) se calcula en un hilo,
porque las máscaras de los complementos leen metadatos; mientras tanto el
resumen dice «Calculando la vista previa...». Organizar espera a que la vista
previa corresponda a lo escrito.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from app.plugins import api

from . import motor

_ = api.traduccion("zc.organizador")[0]

AYUDA_MARCADORES = _(
	"Cada tramo separado por una barra inversa es una carpeta. Marcadores de zCommander: [N] nombre, [E] extensión, "
	"[P] carpeta que lo contiene, [Y] año, [M] mes, [D] día de la fecha de modificación, [C] contador. "
	"De los complementos: [EXIF:fecha:AAAA] y [EXIF:fecha:MM] (fotos), [MP3:artista], [MP3:album], [MP3:pista] y [MP3:titulo] (música)."
)


def _boton(padre: wx.Window, etiqueta: str, ayuda: str, identificador: int = wx.ID_ANY) -> wx.Button:
	boton = wx.Button(padre, identificador, etiqueta)
	boton.SetHelpText(ayuda)
	return boton


class DialogoOrganizar(wx.Dialog):
	"""Plantilla, carpeta base, acción y vista previa.

	:param calcular: ``calcular(carpetas, archivo, base, al_terminar)`` calcula el plan en un hilo
		y llama a ``al_terminar(filas)`` en el hilo de la interfaz.
	"""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, base: str, cuantos: int,
			calcular: Callable[[str, str, str, Callable[[list[motor.Fila]], None]], None] | None = None) -> None:
		super().__init__(padre, title=_("Organizar por metadatos"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self._calcular = calcular
		self.filas: list[motor.Fila] = []
		self._vigente: tuple | None = None
		self._aceptar_al_terminar = False
		self._temporizador = wx.CallLater(600, self.actualizar)
		self._temporizador.Stop()
		self.plantillas = [dict(p) for p in (zc.config.obtener("plantillas") or []) if isinstance(p, dict)]
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.guardadas = ui.crear_campo(self, _("Plantillas &guardadas:"), wx.Choice, sizer=sizer,
			choices=[p.get("nombre", "") for p in self.plantillas] or [_("(ninguna)")],
			ayuda=_("Elija una plantilla para rellenar las de carpetas y nombre."))
		_e, self.carpetas = ui.crear_campo(self, _("Plantilla de las carpe&tas:"), wx.TextCtrl, sizer=sizer,
			ayuda=_("Dónde va cada archivo, dentro de la carpeta base. ") + AYUDA_MARCADORES)
		_e, self.archivo = ui.crear_campo(self, _("Plantilla del &nombre del archivo:"), wx.TextCtrl, value="[N]", sizer=sizer,
			ayuda=_("Nombre nuevo sin la extensión, que se conserva. [N] lo deja como está. ") + AYUDA_MARCADORES)
		_e, self.base = ui.crear_campo(self, _("Carpeta &base:"), wx.TextCtrl, value=base, sizer=sizer,
			ayuda=_("Carpeta en la que se crean las de la plantilla. Por defecto, la del otro panel."))
		_e, self.accion = ui.crear_campo(self, _("&Acción:"), wx.Choice, choices=[_("Mover"), _("Copiar")], sizer=sizer,
			ayuda=_("Mover deja los archivos solo en su sitio nuevo; copiar los deja también donde estaban."))
		self.accion.SetSelection(1 if zc.config.obtener("accion") == "copiar" else 0)
		_e, self.campo_resumen = ui.crear_campo(self, _("&Resumen:"), wx.TextCtrl, style=wx.TE_READONLY, sizer=sizer,
			value=api.formato.plural(cuantos, _("{n} elemento elegido"), _("{n} elementos elegidos")),
			ayuda=_("Cuántos archivos están listos y cuántos no se moverán (duplicados, ya existen)."))
		etiqueta = wx.StaticText(self, label=_("Vista &previa:"))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.lista = ui.ListaAccesible(self, _("Vista previa"), [(_("Nombre actual"), 220), (_("Destino nuevo"), 380), (_("Estado"), 160)])
		self.lista.SetHelpText(_("Qué pasará con cada archivo. Solo se mueven o copian los que están «Listo»."))
		sizer.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_actualizar = _boton(self, _("Actuali&zar la vista previa"), _("Vuelve a calcular la vista previa."))
		self.boton_guardar = _boton(self, _("Guardar como p&lantilla..."), _("Guarda las plantillas de carpetas y nombre con un nombre."))
		self.boton_organizar = _boton(self, _("&Organizar"), _("Mueve o copia los archivos «Listo» como una operación con deshacer."), wx.ID_OK)
		self.boton_organizar.SetDefault()
		cancelar = _boton(self, _("&Cancelar"), _("Cierra sin mover nada."), wx.ID_CANCEL)
		for boton in (self.boton_actualizar, self.boton_guardar, self.boton_organizar, cancelar):
			fila.Add(boton, 0, wx.ALL, 3)
		sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 2)
		self.SetSizer(sizer)
		self.SetSize(self.FromDIP(wx.Size(860, 640)))
		ui.preparar_dialogo(self, foco_inicial=self.guardadas if self.plantillas else self.carpetas)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self.guardadas.Bind(wx.EVT_CHOICE, self._al_elegir_plantilla)
		for campo in (self.carpetas, self.archivo, self.base):
			campo.Bind(wx.EVT_TEXT, lambda _e: self._programar())
		self.Bind(wx.EVT_BUTTON, lambda _e: self.actualizar(), self.boton_actualizar)
		self.Bind(wx.EVT_BUTTON, self._al_guardar, self.boton_guardar)
		self.Bind(wx.EVT_BUTTON, self._al_organizar, id=wx.ID_OK)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
		if self.plantillas:
			self.guardadas.SetSelection(0)
			self._poner_plantilla(self.plantillas[0])

	# Plantillas ------------------------------------------------------------------

	def _poner_plantilla(self, plantilla: dict) -> None:
		self.carpetas.ChangeValue(str(plantilla.get("carpetas", "")))
		self.archivo.ChangeValue(str(plantilla.get("archivo", "[N]")) or "[N]")
		self._programar()

	def _al_elegir_plantilla(self, _evento: wx.CommandEvent) -> None:
		indice = self.guardadas.GetSelection()
		if 0 <= indice < len(self.plantillas):
			self._poner_plantilla(self.plantillas[indice])

	def _al_guardar(self, _evento: wx.CommandEvent) -> None:
		nombre = self.zc.ui.pedir_texto(_("&Nombre de la plantilla:"), _("Guardar plantilla"), padre=self)
		nombre = (nombre or "").strip()
		if not nombre:
			return
		nueva = {"nombre": nombre, "carpetas": self.carpetas.GetValue(), "archivo": self.archivo.GetValue() or "[N]"}
		self.plantillas = [p for p in self.plantillas if p.get("nombre", "").casefold() != nombre.casefold()] + [nueva]
		self.zc.config.establecer("plantillas", self.plantillas)
		self.guardadas.Set([p.get("nombre", "") for p in self.plantillas])
		self.guardadas.SetSelection(len(self.plantillas) - 1)
		self.zc.anunciar(_("Plantilla {n} guardada").format(n=nombre), api.RESULTADO)

	# Vista previa ---------------------------------------------------------------

	def campos(self) -> tuple[str, str, str]:
		return self.carpetas.GetValue(), self.archivo.GetValue(), self.base.GetValue().strip().strip('"')

	def mover(self) -> bool:
		return self.accion.GetSelection() != 1

	def _programar(self) -> None:
		self._vigente = None
		self._temporizador.Start(600)

	def actualizar(self) -> None:
		self._temporizador.Stop()
		if self._calcular is None:
			return
		campos = self.campos()
		self.campo_resumen.SetValue(_("Calculando la vista previa..."))

		def listo(filas: list[motor.Fila], pedidos: tuple = campos) -> None:
			if not self or self.campos() != pedidos:
				return
			self.mostrar(filas)
			self._vigente = pedidos
			if self._aceptar_al_terminar:
				self._aceptar_al_terminar = False
				self._terminar()

		self._calcular(*campos, listo)

	def mostrar(self, filas: list[motor.Fila]) -> None:
		self.filas = filas
		self.lista.reemplazar_filas([[f.entrada.nombre, f.destino, motor.texto_estado(f.estado, f.mensaje if f.estado == motor.ERROR else "")]
			for f in filas])
		self.campo_resumen.SetValue(motor.resumen(filas))

	def _al_organizar(self, _evento: wx.CommandEvent) -> None:
		if self._vigente != self.campos():
			self._aceptar_al_terminar = True
			self.actualizar()
			return
		self._terminar()

	def _terminar(self) -> None:
		if not any(f.estado == motor.LISTO for f in self.filas):
			self.zc.ui.mostrar_error(_("No hay ningún archivo «Listo»: {r}.").format(r=motor.resumen(self.filas)), _("Organizar"), self)
			return
		self.EndModal(wx.ID_OK)

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F1 and not evento.HasAnyModifiers():
			try:
				self.zc.abrir_ayuda()
			except api.NoAdmitido:
				self.zc.registro.debug("Sin ventana para abrir la ayuda", exc_info=True)
			return
		evento.Skip()

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self:
			self._temporizador.Stop()
		evento.Skip()
