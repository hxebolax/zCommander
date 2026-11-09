# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos accesibles con botones en español.

Reglas que aplican todas las funciones de este módulo:

- Botones con etiqueta EXPLÍCITA en español y acelerador (``&Aceptar``,
  ``&Cancelar``, ``&Sí``, ``&No``), aunque falle el catálogo de wx.
- Botón predeterminado (Intro) y botón de escape (Esc) definidos.
- Escape cierra el diálogo, SALVO si hay un desplegable abierto: entonces
  Escape solo cierra el desplegable (es lo que espera el usuario).
- Ctrl+H anuncia la ayuda del control enfocado en cualquier diálogo.
- Mensajes largos o de varias líneas en un campo de SOLO LECTURA: el lector
  puede recorrerlos línea a línea y copiarlos (un ``StaticText`` no).
- Foco inicial útil y, al cerrar, el foco vuelve a donde estaba.
- Para decisiones con consecuencias, botones que dicen LA ACCIÓN
  («Eliminar», «Conservar») en lugar de Sí/No (``elegir_opcion``).

PLANTILLA del agente «accesibilidad-wx».
"""

from __future__ import annotations

import builtins
import ctypes
import logging
from collections.abc import Sequence

import wx

from app.ui.accesibilidad.ayuda import asegurar_ayudas, describir_control_enfocado
from app.ui.accesibilidad.nombres import crear_campo


def _(texto: str) -> str:
	"""Traduce con gettext si está instalado en builtins; si no, devuelve el texto."""
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


log = logging.getLogger(__name__)

_CB_GETDROPPEDSTATE = 0x0157

# Etiquetas en español de los botones estándar.
ETIQUETAS = {
	wx.ID_OK: "&Aceptar",
	wx.ID_CANCEL: "&Cancelar",
	wx.ID_YES: "&Sí",
	wx.ID_NO: "&No",
	wx.ID_APPLY: "A&plicar",
	wx.ID_CLOSE: "C&errar",
	wx.ID_HELP: "A&yuda",
	wx.ID_SAVE: "&Guardar",
}


def desplegable_abierto(control: wx.Window | None) -> bool:
	"""Indica si ``control`` es un Choice/ComboBox con su lista desplegada."""
	if not isinstance(control, (wx.Choice, wx.ComboBox)):
		return False
	try:
		return bool(ctypes.windll.user32.SendMessageW(control.GetHandle(), _CB_GETDROPPEDSTATE, 0, 0))
	except (AttributeError, OSError):
		return False


def preparar_dialogo(
	dialogo: wx.Dialog,
	id_escape: int = wx.ID_CANCEL,
	foco_inicial: wx.Window | None = None,
	ayudas_genericas: bool = True,
) -> None:
	"""Aplica Escape, Ctrl+H, ayudas y foco inicial a cualquier diálogo.

	:param id_escape: código con el que se cierra al pulsar Escape.
	:param foco_inicial: control que recibe el foco al abrirse.
	:param ayudas_genericas: rellenar la ayuda de los controles que no la tengan.
	"""
	dialogo.SetEscapeId(id_escape)

	def al_pulsar(evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if modificadores == wx.MOD_CONTROL and tecla == ord("H"):
			describir_control_enfocado(dialogo)
			return
		if tecla == wx.WXK_ESCAPE and modificadores == wx.MOD_NONE:
			if desplegable_abierto(wx.Window.FindFocus()):
				evento.Skip()  # Escape cierra primero la lista desplegable
				return
			if dialogo.IsModal():
				dialogo.EndModal(id_escape)
			else:
				dialogo.Close()
			return
		evento.Skip()

	def al_iniciar(evento: wx.InitDialogEvent) -> None:
		if ayudas_genericas:
			asegurar_ayudas(dialogo)
		if foco_inicial:
			enfocar(foco_inicial)
		evento.Skip()

	dialogo.Bind(wx.EVT_CHAR_HOOK, al_pulsar)
	dialogo.Bind(wx.EVT_INIT_DIALOG, al_iniciar)


def enfocar(control: wx.Window) -> None:
	"""Pone el foco en un control y deja el cursor donde el lector espera.

	Campo editable de una línea: todo seleccionado (para escribir encima).
	Solo lectura o multilínea: cursor al principio (se lee desde arriba).
	"""
	control.SetFocus()
	if isinstance(control, wx.TextCtrl):
		if control.IsMultiLine() or not control.IsEditable():
			control.SetInsertionPoint(0)
			control.ShowPosition(0)
		else:
			control.SelectAll()


def crear_botonera(padre: wx.Window, banderas: int, predeterminado: int | None = None) -> wx.StdDialogButtonSizer:
	"""Botonera estándar (orden de Windows) con etiquetas en español.

	:param banderas: combinación de ``wx.OK``, ``wx.CANCEL``, ``wx.YES``, ``wx.NO``, ``wx.APPLY``, ``wx.CLOSE``, ``wx.HELP``.
	:param predeterminado: id del botón de Intro (por defecto Aceptar o Sí). En
		confirmaciones peligrosas pase ``wx.ID_NO`` o ``wx.ID_CANCEL``.
	"""
	sizer = wx.StdDialogButtonSizer()
	botones: dict[int, wx.Button] = {}
	for bandera, identificador in (
		(wx.OK, wx.ID_OK), (wx.YES, wx.ID_YES), (wx.NO, wx.ID_NO), (wx.CANCEL, wx.ID_CANCEL),
		(wx.APPLY, wx.ID_APPLY), (wx.CLOSE, wx.ID_CLOSE), (wx.HELP, wx.ID_HELP),
	):
		if banderas & bandera:
			boton = wx.Button(padre, identificador, _(ETIQUETAS[identificador]))
			botones[identificador] = boton
			sizer.AddButton(boton)
	sizer.Realize()
	elegido = predeterminado or (wx.ID_OK if wx.ID_OK in botones else wx.ID_YES)
	if elegido in botones:
		botones[elegido].SetDefault()
	return sizer


def _cuerpo_mensaje(padre: wx.Window, mensaje: str, nombre: str) -> tuple[wx.Window, wx.Sizer | None]:
	"""StaticText si el mensaje es corto; campo de solo lectura si es largo o multilínea.

	El campo lleva su etiqueta «&Mensaje:» creada justo antes (``name=`` no da
	nombre accesible a un TextCtrl nativo). Devuelve el control y, si lleva
	etiqueta, el sizer que hay que añadir en su lugar.
	"""
	if "\n" in mensaje or len(mensaje) > 200:
		etiqueta = wx.StaticText(padre, label=_("&Mensaje:"))
		campo = wx.TextCtrl(
			padre, value=mensaje, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
			size=(460, 180), name=nombre,
		)
		campo.SetHelpText(_("Texto del mensaje. Recórralo con las flechas; puede copiarlo."))
		columna = wx.BoxSizer(wx.VERTICAL)
		columna.Add(etiqueta, 0, wx.BOTTOM, 4)
		columna.Add(campo, 1, wx.EXPAND)
		return campo, columna
	texto = wx.StaticText(padre, label=mensaje)
	texto.Wrap(460)
	return texto, None


def es_etiqueta_de_cancelar(etiqueta: str) -> bool:
	"""«&Cancelar», «Cerrar»... (sin el acelerador ni mayúsculas)."""
	limpia = etiqueta.replace("&", "").strip().rstrip(".").lower()
	return limpia in {_("Cancelar").lower(), _("Cerrar").lower(), "cancelar", "cerrar"}


class DialogoMensaje(wx.Dialog):
	"""Mensaje, confirmación o elección con botones que dicen la acción.

	Devuelve con ``ShowModal`` el id del botón pulsado. Para ``elegir_opcion``
	cada botón personalizado recibe un id propio (ver ``ids_opciones``).
	"""

	def __init__(
		self,
		padre: wx.Window | None,
		mensaje: str,
		titulo: str,
		banderas: int = wx.OK,
		predeterminado: int | None = None,
		opciones: Sequence[str] = (),
		icono: int = 0,
		casilla: str = "",
	) -> None:
		super().__init__(padre, title=titulo or " ", style=wx.DEFAULT_DIALOG_STYLE, name=titulo or _("Mensaje"))
		#: Icono del mensaje: elige el sonido del catálogo al mostrarse (aviso.error, aviso.pregunta...).
		self.icono = icono
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		if icono:
			arte = {wx.ICON_ERROR: wx.ART_ERROR, wx.ICON_WARNING: wx.ART_WARNING,
					wx.ICON_QUESTION: wx.ART_QUESTION}.get(icono, wx.ART_INFORMATION)
			fila.Add(wx.StaticBitmap(panel, bitmap=wx.ArtProvider.GetBitmap(arte, wx.ART_MESSAGE_BOX)), 0, wx.ALL, 10)
		self.cuerpo, columna = _cuerpo_mensaje(panel, mensaje, titulo or _("Mensaje"))
		fila.Add(columna or self.cuerpo, 1, wx.EXPAND | wx.ALL, 10)
		sizer.Add(fila, 1, wx.EXPAND)
		#: 2.0 (10.12): casilla «No volver a preguntar» de las confirmaciones silenciables.
		self.casilla: wx.CheckBox | None = None
		if casilla:
			self.casilla = wx.CheckBox(panel, label=casilla)
			self.casilla.SetHelpText(_("Si la marca, esta pregunta no se volverá a hacer. Se recupera en Preferencias, Confirmaciones."))
			sizer.Add(self.casilla, 0, wx.LEFT | wx.RIGHT, 10)

		self.ids_opciones: list[int] = []
		if opciones:
			botonera = wx.BoxSizer(wx.HORIZONTAL)
			# Si una opción ya es «Cancelar» o «Cerrar», ella es la que responde a
			# Escape: añadir otro Cancelar daba dos botones iguales seguidos.
			cancelar_propio = next((i for i, e in enumerate(opciones) if es_etiqueta_de_cancelar(e)), None)
			for indice, etiqueta in enumerate(opciones):
				identificador = wx.ID_CANCEL if indice == cancelar_propio else wx.ID_ANY
				boton = wx.Button(panel, identificador, etiqueta)
				self.ids_opciones.append(boton.GetId())
				boton.Bind(wx.EVT_BUTTON, lambda _e, i=boton.GetId(): self.EndModal(i))
				if indice == 0:
					boton.SetDefault()
				botonera.Add(boton, 0, wx.ALL, 5)
			if cancelar_propio is None:
				cancelar = wx.Button(panel, wx.ID_CANCEL, _(ETIQUETAS[wx.ID_CANCEL]))
				botonera.Add(cancelar, 0, wx.ALL, 5)
			sizer.Add(botonera, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		else:
			sizer.Add(crear_botonera(panel, banderas, predeterminado), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
			for identificador in (wx.ID_YES, wx.ID_NO, wx.ID_OK):
				boton = self.FindWindow(identificador)
				if boton is not None and identificador != wx.ID_OK:
					boton.Bind(wx.EVT_BUTTON, lambda _e, i=identificador: self.EndModal(i))
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)

		id_escape = wx.ID_CANCEL if (opciones or banderas & wx.CANCEL) else (wx.ID_NO if banderas & wx.NO else wx.ID_OK)
		foco = self.cuerpo if isinstance(self.cuerpo, wx.TextCtrl) else None
		preparar_dialogo(self, id_escape=id_escape, foco_inicial=foco, ayudas_genericas=False)
		self.CentreOnParent()


_SONIDO_ICONO = {wx.ICON_ERROR: "aviso.error", wx.ICON_WARNING: "aviso.advertencia", wx.ICON_QUESTION: "aviso.pregunta",
	wx.ICON_INFORMATION: "aviso.informacion"}


def _sonar(evento: str) -> None:
	"""Sonido del catálogo (2.0, 4.3); un diálogo nunca falla por un sonido."""
	try:
		from app.services.sonidos import servicio

		servicio.sonar(evento)
	except Exception:  # noqa: BLE001 - sin sonidos se sigue igual
		import logging

		logging.getLogger(__name__).debug("No se pudo pedir el sonido %s", evento, exc_info=True)


def devolver_foco(foco_previo: wx.Window | None) -> None:
	"""Devuelve el foco tras cerrar un diálogo modal al control que lo tenía al abrirlo.

	Si no había ninguno, o desapareció mientras el diálogo estaba abierto (una pestaña
	cerrada), la ventana principal lo pone en la lista del panel que estaba activo
	(``devolver_foco_panel``), en lugar de dejar que Windows elija otro control.
	"""
	try:
		if foco_previo:
			foco_previo.SetFocus()
			return
	except RuntimeError:
		log.debug("El control que tenía el foco ya no existe", exc_info=True)
	aplicacion = wx.GetApp()
	ventana = aplicacion.GetTopWindow() if aplicacion else None
	devolver = getattr(ventana, "devolver_foco_panel", None) if ventana else None
	if callable(devolver):
		try:
			devolver()
		except RuntimeError:
			log.debug("No se pudo devolver el foco a la ventana principal", exc_info=True)


def _mostrar(dialogo: wx.Dialog) -> int:
	"""Muestra un diálogo modal, lo destruye y devuelve el foco a donde estaba."""
	foco_previo = wx.Window.FindFocus()
	_sonar(_SONIDO_ICONO.get(getattr(dialogo, "icono", 0), "dialogo.abrir"))
	try:
		return dialogo.ShowModal()
	finally:
		_sonar("dialogo.cerrar")
		dialogo.Destroy()
		devolver_foco(foco_previo)


def mostrar_mensaje(padre: wx.Window | None, mensaje: str, titulo: str = "", icono: int = wx.ICON_INFORMATION) -> None:
	"""Mensaje informativo con un botón «Aceptar»."""
	_mostrar(DialogoMensaje(padre, mensaje, titulo or _("Información"), wx.OK, icono=icono))


def mostrar_error(padre: wx.Window | None, mensaje: str, titulo: str = "") -> None:
	"""Mensaje de error con un botón «Aceptar»."""
	mostrar_mensaje(padre, mensaje, titulo or _("Error"), icono=wx.ICON_ERROR)


def confirmar(
	padre: wx.Window | None, mensaje: str, titulo: str = "", con_cancelar: bool = False, peligroso: bool = False
) -> int:
	"""Pregunta Sí/No (o Sí/No/Cancelar). Devuelve ``wx.ID_YES``, ``wx.ID_NO`` o ``wx.ID_CANCEL``.

	:param peligroso: el botón predeterminado (Intro) es «No», para que un
		Intro accidental no borre nada.
	"""
	banderas = wx.YES | wx.NO | (wx.CANCEL if con_cancelar else 0)
	dialogo = DialogoMensaje(
		padre, mensaje, titulo or _("Confirmación"), banderas,
		predeterminado=wx.ID_NO if peligroso else wx.ID_YES, icono=wx.ICON_QUESTION,
	)
	return _mostrar(dialogo)


def elegir_opcion(padre: wx.Window | None, mensaje: str, titulo: str, opciones: Sequence[str]) -> int | None:
	"""Botones que dicen la acción («&Impulsar», «&Citar»...). Devuelve el índice o ``None`` si se cancela.

	Si ``opciones`` incluye «&Cancelar» o «&Cerrar», Escape devuelve su índice
	y no se añade otro botón; si no, se añade un «Cancelar» que devuelve ``None``.
	"""
	dialogo = DialogoMensaje(padre, mensaje, titulo, opciones=opciones, icono=wx.ICON_QUESTION)
	ids = list(dialogo.ids_opciones)
	resultado = _mostrar(dialogo)
	return ids.index(resultado) if resultado in ids else None


CASILLA_NO_PREGUNTAR = "&No volver a preguntar"


def elegir_con_casilla(padre: wx.Window | None, mensaje: str, titulo: str, opciones: Sequence[str],
		casilla: str = CASILLA_NO_PREGUNTAR) -> tuple[int | None, bool]:
	"""Como ``elegir_opcion`` con una casilla (10.12): (índice o ``None`` si se cancela, casilla marcada).

	Si se cancela, la casilla cuenta como no marcada: cancelar nunca silencia nada.
	"""
	dialogo = DialogoMensaje(padre, mensaje, titulo, opciones=opciones, icono=wx.ICON_QUESTION, casilla=_(casilla))
	ids = list(dialogo.ids_opciones)
	marcada = [False]

	def recordar(evento: wx.CommandEvent) -> None:
		marcada[0] = bool(dialogo.casilla and dialogo.casilla.GetValue())
		evento.Skip()

	if dialogo.casilla is not None:
		dialogo.casilla.Bind(wx.EVT_CHECKBOX, recordar)
	resultado = _mostrar(dialogo)
	if resultado not in ids:
		return None, False
	return ids.index(resultado), marcada[0]


class DialogoTexto(wx.Dialog):
	"""Pide un texto con etiqueta, límite de caracteres, multilínea o contraseña."""

	def __init__(
		self,
		padre: wx.Window | None,
		etiqueta: str,
		titulo: str,
		valor: str = "",
		multilinea: bool = False,
		contrasena: bool = False,
		max_caracteres: int = 0,
		ayuda: str = "",
	) -> None:
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		estilo = wx.TE_MULTILINE if multilinea else (wx.TE_PASSWORD if contrasena else 0)
		_, self.campo = crear_campo(
			panel, etiqueta, wx.TextCtrl, value=valor, style=estilo,
			size=(460, 160) if multilinea else (360, -1), ayuda=ayuda, sizer=sizer,
		)
		if max_caracteres > 0:
			self.campo.SetMaxLength(max_caracteres)
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		preparar_dialogo(self, foco_inicial=self.campo)
		self.CentreOnParent()

	def GetValue(self) -> str:  # noqa: N802 - mismo nombre que wx.TextEntryDialog
		return self.campo.GetValue()


def pedir_texto(padre: wx.Window | None, etiqueta: str, titulo: str, valor: str = "", **opciones) -> str | None:
	"""Devuelve el texto escrito o ``None`` si se cancela."""
	dialogo = DialogoTexto(padre, etiqueta, titulo, valor, **opciones)
	foco_previo = wx.Window.FindFocus()
	try:
		return dialogo.GetValue() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()
		devolver_foco(foco_previo)


def dialogo_nativo(padre: wx.Window | None, mensaje: str, titulo: str, estilo: int = wx.OK | wx.ICON_INFORMATION) -> int:
	"""``wx.MessageDialog`` nativo de Windows con los botones forzados al español.

	Es el más compatible con cualquier lector (es un cuadro de Windows), pero
	su texto no se puede recorrer ni copiar como un campo.
	"""
	dialogo = wx.MessageDialog(padre, mensaje, titulo, estilo)
	if estilo & wx.YES_NO:
		if estilo & wx.CANCEL:
			dialogo.SetYesNoCancelLabels(_("&Sí"), _("&No"), _("&Cancelar"))
		else:
			dialogo.SetYesNoLabels(_("&Sí"), _("&No"))
	elif estilo & wx.CANCEL:
		dialogo.SetOKCancelLabels(_("&Aceptar"), _("&Cancelar"))
	else:
		dialogo.SetOKLabel(_("&Aceptar"))
	return _mostrar(dialogo)
