# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Editar sitio» (FTP, FTPS o SFTP) del gestor de conexiones.

Por qué así:

- Cada campo tiene su etiqueta creada justo antes (el lector la toma como
  nombre) y una letra de acceso propia: N, P, S, R, U, T, G, I, M, O, E, V,
  X y F, más A y C de Aceptar y Cancelar.
- La contraseña nunca se muestra ni se rellena: si ya hay una guardada, el
  campo vacío la conserva (``MANTENER``); para olvidarla se desmarca
  «Guardar la contraseña».
- Al cambiar de protocolo se cambia el puerto si era el habitual del
  anterior, y se activan solo los campos que tienen sentido (modo pasivo y
  codificación en FTP; clave privada en SFTP).
- Se valida al pulsar Aceptar con ``conexiones.validar``: si algo no vale, se
  dice qué y el foco va a ese campo sin perder lo escrito.
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import conexiones
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo, crear_selector_ruta

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


CODIFICACIONES_VISIBLES = (("utf-8", "UTF-8"), ("latin-1", "Latin-1 (ISO-8859-1)"))


def _avisar(padre: wx.Window, mensaje: str) -> None:
	"""Motivo del rechazo (las pruebas la sustituyen: no hay ``ShowModal`` real)."""
	dialogos.mostrar_error(padre, mensaje, _("Sitio"))


class DialogoSitio(wx.Dialog):
	"""Crea o edita un sitio. ``ShowModal`` devuelve ``wx.ID_OK`` solo con datos válidos.

	:param tiene_contrasena: el sitio ya tiene una contraseña guardada.
	:param tiene_frase: el sitio ya tiene guardada la frase de su clave privada.
	"""

	def __init__(self, padre: wx.Window | None, sitio: conexiones.Sitio | None = None, tiene_contrasena: bool = False,
			tiene_frase: bool = False) -> None:
		nuevo = sitio is None
		titulo = _("Nuevo sitio") if nuevo else _("Editar sitio")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		self.original = sitio or conexiones.Sitio()
		self.tiene_contrasena = tiene_contrasena
		self.tiene_frase = tiene_frase
		s = self.original
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		ancho = panel.FromDIP(wx.Size(380, -1))

		_e, self.campo_nombre = crear_campo(panel, _("&Nombre del sitio:"), wx.TextCtrl, value=s.nombre, size=ancho,
			ayuda=_("Nombre con el que aparece en la lista de sitios."), sizer=sizer)
		_e, self.lista_protocolo = crear_campo(panel, _("&Protocolo:"), wx.Choice,
			choices=[conexiones.nombre_protocolo(p) for p in conexiones.PROTOCOLOS],
			ayuda=_("FTP manda la contraseña sin cifrar. FTPS es FTP con TLS explícito. SFTP va sobre SSH."), sizer=sizer)
		self.lista_protocolo.SetSelection(conexiones.PROTOCOLOS.index(s.protocolo))
		self._protocolo_anterior = s.protocolo
		_e, self.campo_servidor = crear_campo(panel, _("&Servidor:"), wx.TextCtrl, value=s.servidor, size=ancho,
			ayuda=_("Nombre o dirección del servidor, sin ftp:// ni barras (por ejemplo, ftp.ejemplo.org)."), sizer=sizer)
		_e, self.campo_puerto = crear_campo(panel, _("Pue&rto:"), wx.SpinCtrl, min=1, max=65535, initial=int(s.puerto),
			ayuda=_("21 para FTP y FTPS, 22 para SFTP, salvo que el servidor use otro."), sizer=sizer, expandir=False)
		_e, self.campo_usuario = crear_campo(panel, _("&Usuario (vacío para anónimo):"), wx.TextCtrl, value=s.usuario, size=ancho,
			ayuda=_("Usuario del servidor. Vacío en FTP para entrar como anónimo; SFTP necesita usuario."), sizer=sizer)
		ayuda_clave = _("Se guarda cifrada para su usuario de Windows en secretos.dat. ")
		if tiene_contrasena:
			ayuda_clave += _("Déjela vacía para conservar la que ya hay guardada.")
		else:
			ayuda_clave += _("Si no la escribe o no la guarda, se pedirá al conectar.")
		_e, self.campo_contrasena = crear_campo(panel, _("Con&traseña:"), wx.TextCtrl, style=wx.TE_PASSWORD, size=ancho,
			ayuda=ayuda_clave, sizer=sizer)
		self.casilla_guardar = wx.CheckBox(panel, label=_("&Guardar la contraseña (cifrada)"))
		self.casilla_guardar.SetValue(s.guardar_contrasena)
		self.casilla_guardar.SetHelpText(_("Desmarcada: la contraseña se pide cada vez y se borra la que hubiera guardada."))
		sizer.Add(self.casilla_guardar, 0, wx.ALL, 5)
		_e, self.campo_carpeta = crear_campo(panel, _("Carpeta remota &inicial:"), wx.TextCtrl, value=s.carpeta, size=ancho,
			ayuda=_("Carpeta del servidor que se abre al conectar, con barras normales (por ejemplo, /public_html)."), sizer=sizer)
		self.casilla_pasivo = wx.CheckBox(panel, label=_("&Modo pasivo (FTP)"))
		self.casilla_pasivo.SetValue(s.pasivo)
		self.casilla_pasivo.SetHelpText(_("Recomendado detrás de un router o un cortafuegos. Desmárquelo solo si el servidor lo pide."))
		sizer.Add(self.casilla_pasivo, 0, wx.ALL, 5)
		_e, self.lista_codificacion = crear_campo(panel, _("C&odificación de los nombres (FTP):"), wx.Choice,
			choices=[texto for _c, texto in CODIFICACIONES_VISIBLES],
			ayuda=_("UTF-8 en casi todos los servidores; Latin-1 si los nombres con tildes salen mal."), sizer=sizer)
		self.lista_codificacion.SetSelection(next((i for i, (c, _t) in enumerate(CODIFICACIONES_VISIBLES) if c == s.codificacion), 0))
		_e, self.campo_tiempo = crear_campo(panel, _("Tiempo de &espera (segundos):"), wx.SpinCtrl, min=conexiones.TIEMPO_MINIMO,
			max=conexiones.TIEMPO_MAXIMO, initial=int(s.tiempo_espera_s),
			ayuda=_("Segundos sin respuesta del servidor antes de dar la conexión por perdida."), sizer=sizer, expandir=False)
		_e, self.campo_clave, self.boton_clave = crear_selector_ruta(panel, _("Clave pri&vada (SFTP, opcional):"), carpeta=False,
			valor=s.clave_privada, comodin=_("Todos los archivos (*.*)|*.*"),
			ayuda=_("Archivo de clave privada OpenSSH o PEM. Vacío para entrar con contraseña."), sizer=sizer)
		ayuda_frase = _("Frase que protege la clave privada. ")
		ayuda_frase += _("Déjela vacía para conservar la guardada.") if tiene_frase else _("Si no la escribe, se pedirá al conectar.")
		_e, self.campo_frase = crear_campo(panel, _("&Frase de la clave privada:"), wx.TextCtrl, style=wx.TE_PASSWORD, size=ancho,
			ayuda=ayuda_frase, sizer=sizer)

		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.lista_protocolo.Bind(wx.EVT_CHOICE, self._al_cambiar_protocolo)
		self.casilla_guardar.Bind(wx.EVT_CHECKBOX, lambda _e: self._actualizar())
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, self._al_aceptar)
		self._actualizar()
		preparar_dialogo(self, foco_inicial=self.campo_nombre if nuevo or not s.nombre else self.campo_servidor)
		self.CentreOnParent()

	# Estado ---------------------------------------------------------------

	def protocolo(self) -> str:
		return conexiones.PROTOCOLOS[max(0, self.lista_protocolo.GetSelection())]

	def _al_cambiar_protocolo(self, _evento: wx.CommandEvent) -> None:
		nuevo = self.protocolo()
		if self.campo_puerto.GetValue() == conexiones.PUERTOS.get(self._protocolo_anterior):
			self.campo_puerto.SetValue(conexiones.PUERTOS[nuevo])
		self._protocolo_anterior = nuevo
		self._actualizar()

	def _actualizar(self) -> None:
		es_sftp = self.protocolo() == "sftp"
		for control in (self.casilla_pasivo, self.lista_codificacion):
			control.Enable(not es_sftp)
		for control in (self.campo_clave, self.boton_clave):
			control.Enable(es_sftp)
		self.campo_frase.Enable(es_sftp and self.casilla_guardar.GetValue())

	def sitio(self) -> conexiones.Sitio:
		"""Sitio con lo escrito (conserva el ``id`` y el aviso de FTP sin cifrar del original)."""
		indice = max(0, self.lista_codificacion.GetSelection())
		return conexiones.Sitio(
			id=self.original.id,
			nombre=self.campo_nombre.GetValue().strip(),
			protocolo=self.protocolo(),
			servidor=self.campo_servidor.GetValue().strip(),
			puerto=int(self.campo_puerto.GetValue()),
			usuario=self.campo_usuario.GetValue().strip(),
			guardar_contrasena=self.casilla_guardar.GetValue(),
			carpeta=conexiones.normalizar_remota(self.campo_carpeta.GetValue().strip() or "/"),
			pasivo=self.casilla_pasivo.GetValue(),
			codificacion=CODIFICACIONES_VISIBLES[indice][0],
			tiempo_espera_s=int(self.campo_tiempo.GetValue()),
			clave_privada=self.campo_clave.GetValue().strip() if self.protocolo() == "sftp" else "",
			aviso_sin_cifrar_mostrado=self.original.aviso_sin_cifrar_mostrado,
		)

	def contrasena(self):
		"""Texto nuevo, o ``conexiones.MANTENER`` si el campo se dejó vacío y ya había una guardada."""
		texto = self.campo_contrasena.GetValue()
		if not texto and self.tiene_contrasena:
			return conexiones.MANTENER
		return texto or None

	def frase(self):
		texto = self.campo_frase.GetValue() if self.protocolo() == "sftp" else ""
		if not texto and self.tiene_frase and self.protocolo() == "sftp":
			return conexiones.MANTENER
		return texto or None

	def _control_de(self, campo: str) -> wx.Window:
		return {
			"nombre": self.campo_nombre, "protocolo": self.lista_protocolo, "servidor": self.campo_servidor,
			"puerto": self.campo_puerto, "usuario": self.campo_usuario, "carpeta": self.campo_carpeta,
			"codificacion": self.lista_codificacion, "tiempo_espera_s": self.campo_tiempo,
		}.get(campo, self.campo_nombre)

	def aceptar(self) -> bool:
		"""Cierra con Aceptar si el sitio vale; si no, dice por qué y lleva el foco al campo."""
		problema = conexiones.validar(self.sitio())
		if problema is not None:
			campo, motivo = problema
			_avisar(self, motivo)
			dialogos.enfocar(self._control_de(campo))
			return False
		if self.IsModal():
			self.EndModal(wx.ID_OK)
		else:
			self.SetReturnCode(wx.ID_OK)
		return True

	def _al_aceptar(self, _evento: wx.CommandEvent) -> None:
		self.aceptar()
