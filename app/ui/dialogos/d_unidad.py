# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos «Conectar unidad de red» y «Desconectar unidad de red» (1.x 8.22, ampliados en 2.0 9.4 y 9.5).

Por qué propios y no solo los de Windows: los de Windows
(``WNetConnectionDialog``) cambian según la versión y su campo de carpeta
es un desplegable con autocompletado que algunos lectores leen a medias.
Estos usan controles nativos sencillos con etiqueta y letra de acceso; el
botón «Usar el cuadro de &Windows...» sigue disponible para quien lo prefiera
(``ShowModal`` devuelve ``wx.ID_MORE``).

Lo que añade la 2.0: «Carpeta de red» con los servidores recientes; la letra
puede ser «Automática» (Windows elige) o «Sin letra» (solo abrir el recurso
con otra cuenta, orden ``red_conectar_recurso``); «Exigir cifrado SMB»;
«Recordar la contraseña en Windows»; y, al desconectar, las conexiones sin
letra y «Olvidar también la contraseña guardada».

Letras: Conectar usa L, R, V, X, O, U, T, D, W, N y C; Desconectar usa U, O, G, F, W, D y C.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Sequence

import wx

from app.services.windows import red
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)

#: Valores de ``datos()[0]`` para las dos opciones nuevas de la letra.
AUTOMATICA, SIN_LETRA = "*", ""


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _avisar(padre: wx.Window, mensaje: str, titulo: str) -> None:
	"""Motivo del rechazo (las pruebas la sustituyen)."""
	dialogos.mostrar_error(padre, mensaje, titulo)


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


def _botonera(panel: wx.Window, etiqueta: str, ayuda: str) -> tuple[wx.StdDialogButtonSizer, wx.Button]:
	"""«Etiqueta» (``wx.ID_OK``, predeterminado) y «&Cancelar»: botones que dicen la acción."""
	botonera = wx.StdDialogButtonSizer()
	aceptar = wx.Button(panel, wx.ID_OK, etiqueta)
	aceptar.SetHelpText(ayuda)
	botonera.AddButton(aceptar)
	cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cancelar"))
	cancelar.SetHelpText(_("Cierra sin hacer nada."))
	botonera.AddButton(cancelar)
	botonera.Realize()
	aceptar.SetDefault()
	return botonera, aceptar


def _ayuda_remoto() -> str:
	try:
		formas = red.ayuda_formas_de_ruta()
	except Exception:  # noqa: BLE001 - la ayuda sale sin los proveedores opcionales
		log.debug("Sin las formas de ruta de los proveedores", exc_info=True)
		formas = ""
	return " ".join(p for p in (_("Recurso compartido, por ejemplo \\\\nas\\fotos. La lista tiene los servidores recientes."), formas) if p)


class DialogoConectarUnidad(wx.Dialog):
	"""Letra, carpeta de red, reconectar al iniciar sesión, cifrado y, si hace falta, otras credenciales.

	:param letras: letras libres, de la Z hacia atrás (la primera queda elegida).
	:param recientes: servidores o carpetas para la lista de «Carpeta de red».
	:param sin_letra: elige «Sin letra» y no deja cambiarla (orden ``red_conectar_recurso``).
	"""

	def __init__(self, padre: wx.Window | None, letras: Sequence[str], remoto: str = "", *, recientes: Sequence[str] = (),
			sin_letra: bool = False, exigir_cifrado: bool = False, usuario: str = "") -> None:
		titulo = _("Abrir un recurso compartido con otra cuenta") if sin_letra else _("Conectar unidad de red")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE, name=titulo)
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.titulo = titulo
		self.letras = list(letras)
		self._valores_letra = [*self.letras, AUTOMATICA, SIN_LETRA]
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		ancho = panel.FromDIP(wx.Size(360, -1))
		opciones = [*self.letras, _("Automática (la elige Windows)"), _("Sin letra")]
		_e, self.lista_letra = crear_campo(panel, _("&Letra de unidad:"), wx.Choice, choices=opciones,
			ayuda=_("Letra que tendrá la carpeta de red en zCommander y en el Explorador. «Automática» deja que Windows elija "
				"una libre; «Sin letra» solo abre el recurso con estas credenciales."), sizer=sizer, expandir=False)
		self.lista_letra.SetSelection(len(opciones) - 1 if sin_letra else 0)
		if sin_letra:
			self.lista_letra.Enable(False)
		_e, self.campo_remoto = crear_campo(panel, _("Carpeta de &red (\\\\servidor\\recurso):"), wx.ComboBox, value=remoto,
			choices=[r for r in recientes if r], style=wx.CB_DROPDOWN, size=ancho, ayuda=_ayuda_remoto(), sizer=sizer)
		self.casilla_recordar = wx.CheckBox(panel, label=_("&Volver a conectar al iniciar sesión"))
		self.casilla_recordar.SetValue(True)
		self.casilla_recordar.SetHelpText(_("Windows recordará la unidad y la conectará en cada inicio de sesión "
			"(lo guarda Windows en su perfil, fuera de la carpeta de zCommander)."))
		sizer.Add(self.casilla_recordar, 0, wx.ALL, 5)
		self.casilla_cifrado = wx.CheckBox(panel, label=_("E&xigir cifrado SMB"))
		self.casilla_cifrado.SetValue(bool(exigir_cifrado))
		self.casilla_cifrado.SetHelpText(_("No conecta si el servidor no cifra los datos (SMB 3). No se aplica a WebDAV."))
		sizer.Add(self.casilla_cifrado, 0, wx.ALL, 5)
		self.casilla_credenciales = wx.CheckBox(panel, label=_("Conectar con &otras credenciales"))
		self.casilla_credenciales.SetValue(bool(usuario) or sin_letra)
		self.casilla_credenciales.SetHelpText(_("Márquela si el servidor pide un usuario distinto del de Windows."))
		sizer.Add(self.casilla_credenciales, 0, wx.ALL, 5)
		_e, self.campo_usuario = crear_campo(panel, _("&Usuario:"), wx.TextCtrl, value=usuario, size=ancho,
			ayuda=_("Usuario del servidor, por ejemplo SERVIDOR\\ana o ana@dominio."), sizer=sizer)
		_e, self.campo_contrasena = crear_campo(panel, _("Con&traseña:"), wx.TextCtrl, style=wx.TE_PASSWORD, size=ancho,
			ayuda=_("Contraseña de ese usuario. zCommander no la guarda; se la pasa a Windows."), sizer=sizer)
		self.casilla_recordar_contrasena = wx.CheckBox(panel, label=_("Recor&dar la contraseña en Windows"))
		self.casilla_recordar_contrasena.SetHelpText(_("La guarda el Administrador de credenciales de Windows (no zCommander) "
			"para conectar sin preguntar. Se borra con Contraseñas guardadas de servidores."))
		sizer.Add(self.casilla_recordar_contrasena, 0, wx.ALL, 5)
		self.boton_windows = wx.Button(panel, label=_("Usar el cuadro de &Windows..."))
		self.boton_windows.SetHelpText(_("Abre el cuadro Conectar a unidad de red de Windows."))
		sizer.Add(self.boton_windows, 0, wx.ALL, 5)
		botonera, self.boton_conectar = _botonera(panel, _("Co&nectar"), _("Conecta la carpeta de red con estos datos."))
		sizer.Add(botonera, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.casilla_credenciales.Bind(wx.EVT_CHECKBOX, lambda _e: self._actualizar())
		self.lista_letra.Bind(wx.EVT_CHOICE, lambda _e: self._actualizar())
		self.boton_windows.Bind(wx.EVT_BUTTON, lambda _e: _terminar(self, wx.ID_MORE))
		self.boton_conectar.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		self._actualizar()
		preparar_dialogo(self, foco_inicial=self.campo_remoto)
		self.CentreOnParent()

	def _actualizar(self) -> None:
		otras = self.casilla_credenciales.GetValue()
		self.campo_usuario.Enable(otras)
		self.campo_contrasena.Enable(otras)
		self.casilla_recordar_contrasena.Enable(otras)
		self.casilla_recordar.Enable(self.letra() != SIN_LETRA)

	def letra(self) -> str:
		"""«Z:», ``AUTOMATICA`` («*») o ``SIN_LETRA`` («»)."""
		indice = self.lista_letra.GetSelection()
		return self._valores_letra[indice] if 0 <= indice < len(self._valores_letra) else SIN_LETRA

	def datos(self) -> tuple[str, str, str, str | None, bool]:
		"""(letra, remoto, usuario, contraseña, volver a conectar al iniciar sesión), como en la 1.x."""
		otras = self.casilla_credenciales.GetValue()
		return (self.letra(), self.campo_remoto.GetValue().strip(), self.campo_usuario.GetValue().strip() if otras else "",
			self.campo_contrasena.GetValue() if otras else None,
			self.casilla_recordar.GetValue() and self.letra() != SIN_LETRA)

	def opciones(self) -> tuple[bool, bool]:
		"""(recordar la contraseña en Windows, exigir cifrado SMB)."""
		otras = self.casilla_credenciales.GetValue()
		recordar = otras and self.casilla_recordar_contrasena.GetValue() and bool(self.campo_contrasena.GetValue())
		return bool(recordar), bool(self.casilla_cifrado.GetValue())

	def aceptar(self) -> bool:
		problema = red.validar_remoto(self.campo_remoto.GetValue())
		if problema is None and self.casilla_credenciales.GetValue() and not self.campo_usuario.GetValue().strip():
			_avisar(self, _("Escriba el usuario o desmarque «Conectar con otras credenciales»."), self.titulo)
			dialogos.enfocar(self.campo_usuario)
			return False
		if problema:
			_avisar(self, problema, self.titulo)
			self.campo_remoto.SetFocus()
			return False
		_terminar(self, wx.ID_OK)
		return True


class DialogoDesconectarUnidad(wx.Dialog):
	"""Lista de unidades de red y conexiones sin letra para quitar una, con olvidar y forzar."""

	def __init__(self, padre: wx.Window | None, unidades: Sequence[red.UnidadRed], elegida: str = "") -> None:
		titulo = _("Desconectar unidad de red")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE, name=titulo)
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.unidades = list(unidades)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		textos = [u.describir() for u in self.unidades] or [_("No hay unidades de red")]
		_e, self.lista = crear_campo(panel, _("&Unidades de red:"), wx.ListBox, choices=textos, style=wx.LB_SINGLE,
			size=panel.FromDIP(wx.Size(420, 160)), ayuda=_("Elija la unidad o la conexión sin letra que quiere quitar."), sizer=sizer)
		inicial = next((i for i, u in enumerate(self.unidades) if elegida and elegida.upper() in (u.letra.upper(), u.remoto.upper())), 0)
		self.lista.SetSelection(inicial)
		self.casilla_olvidar = wx.CheckBox(panel, label=_("&Olvidar la conexión (no volver a conectarla al iniciar sesión)"))
		self.casilla_olvidar.SetValue(True)
		self.casilla_olvidar.SetHelpText(_("Desmarcada, Windows la volverá a conectar en el próximo inicio de sesión."))
		sizer.Add(self.casilla_olvidar, 0, wx.ALL, 5)
		self.casilla_credencial = wx.CheckBox(panel, label=_("Olvidar también la contraseña &guardada"))
		self.casilla_credencial.SetHelpText(_("Borra del Administrador de credenciales de Windows la contraseña guardada de ese servidor."))
		sizer.Add(self.casilla_credencial, 0, wx.ALL, 5)
		self.casilla_forzar = wx.CheckBox(panel, label=_("&Forzar aunque haya archivos abiertos"))
		self.casilla_forzar.SetHelpText(_("Los programas que tengan archivos abiertos en la unidad pueden perder lo no guardado."))
		sizer.Add(self.casilla_forzar, 0, wx.ALL, 5)
		self.boton_windows = wx.Button(panel, label=_("Usar el cuadro de &Windows..."))
		self.boton_windows.SetHelpText(_("Abre el cuadro Desconectar unidades de red de Windows."))
		sizer.Add(self.boton_windows, 0, wx.ALL, 5)
		botonera, self.boton_desconectar = _botonera(panel, _("&Desconectar"), _("Quita la unidad elegida."))
		self.boton_desconectar.Enable(bool(self.unidades))
		self.lista.Enable(bool(self.unidades))
		sizer.Add(botonera, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.boton_windows.Bind(wx.EVT_BUTTON, lambda _e: _terminar(self, wx.ID_MORE))
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: _terminar(self, wx.ID_OK) if self.unidades else None)
		preparar_dialogo(self, foco_inicial=self.lista if self.unidades else self.boton_windows)
		self.CentreOnParent()

	def elegida(self) -> red.UnidadRed | None:
		indice = self.lista.GetSelection()
		return self.unidades[indice] if self.unidades and 0 <= indice < len(self.unidades) else None

	def opciones(self) -> tuple[bool, bool]:
		"""(olvidar, forzar)."""
		return self.casilla_olvidar.GetValue(), self.casilla_forzar.GetValue()

	def olvidar_credencial(self) -> bool:
		return bool(self.casilla_credencial.GetValue())
