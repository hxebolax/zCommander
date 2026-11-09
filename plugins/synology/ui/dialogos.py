# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos del complemento NAS Synology (diseño 2.0, 13.2, 13.3, 13.6 y 13.8).

Reglas de accesibilidad: etiqueta creada justo antes de cada control y con el
mismo padre, letras de acceso sin repetir en cada diálogo (contando Aceptar y
Cancelar), Escape cancela, Ctrl+H explica el control enfocado, y las
decisiones arriesgadas (permitir cambios, aceptar un certificado) tienen el foco
inicial en la opción segura. Todos pasan ``revisar_teclado`` en las pruebas.
"""

from __future__ import annotations

import logging
from typing import Any

import wx

from app.plugins import api

from ..cliente import huella_legible
from ..preguntas import texto_huella
from ..servidores import ServidorNAS, id_desde_nombre
from . import en_interfaz, modulo_ui, poner_letra

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.ui")


def _fila_botones(panel: wx.Window, botones: list[wx.Button]) -> wx.BoxSizer:
	fila = wx.BoxSizer(wx.HORIZONTAL)
	for boton in botones:
		fila.Add(boton, 0, wx.ALL, 4)
	return fila


def _terminar(dialogo: wx.Dialog, panel: wx.Panel, sizer: wx.Sizer) -> None:
	panel.SetSizer(sizer)
	marco = wx.BoxSizer(wx.VERTICAL)
	marco.Add(panel, 1, wx.EXPAND)
	dialogo.SetSizerAndFit(marco)
	dialogo.CentreOnParent()


# ── Servidores ───────────────────────────────────────────────────────────────


class DialogoServidor(wx.Dialog):
	"""Alta o edición de un NAS (13.3). Empieza siempre en solo lectura."""

	def __init__(self, padre: wx.Window | None, servidor: ServidorNAS | None, existentes: set[str], contrasena_guardada: bool = False) -> None:
		titulo = _("Editar el NAS") if servidor else _("Nuevo NAS")
		super().__init__(padre, title=titulo, name=titulo)
		ui = modulo_ui()
		self._original = servidor
		self._existentes = existentes
		self.olvidar_huella = False
		self.olvidar_contrasena = False
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		valores = servidor or ServidorNAS("", "", "", 5001)
		_etq, self.nombre = ui.crear_campo(panel, _("&Nombre:"), wx.TextCtrl, value=valores.nombre, sizer=sizer,
			ayuda=_("Nombre con el que verá este NAS en zCommander, por ejemplo NAS de casa."))
		_etq, self.host = ui.crear_campo(panel, _("&Dirección (nombre o IP):"), wx.TextCtrl, value=valores.host, sizer=sizer,
			ayuda=_("Dirección IP o nombre del NAS en la red, por ejemplo 192.168.1.50. Sin http:// ni puerto."))
		_etq, self.puerto = ui.crear_campo(panel, _("&Puerto:"), wx.SpinCtrl, min=1, max=65535, initial=int(valores.puerto), sizer=sizer,
			ayuda=_("Puerto de DSM: 5001 con HTTPS y 5000 con HTTP, salvo que lo haya cambiado en DSM."))
		self.https = wx.CheckBox(panel, label=_("Usar &HTTPS (recomendado)"))
		self.https.SetValue(bool(valores.https))
		self.https.SetHelpText(_("Cifra la conexión. Sin HTTPS, zCommander no envía la contraseña salvo al NAS de demostración."))
		sizer.Add(self.https, 0, wx.ALL, 5)
		_etq, self.usuario = ui.crear_campo(panel, _("&Usuario:"), wx.TextCtrl, value=valores.usuario, sizer=sizer,
			ayuda=_("Cuenta de DSM. Para las áreas de administración tiene que ser del grupo administrators."))
		self.recordar = wx.CheckBox(panel, label=_("Recordar la contra&seña"))
		self.recordar.SetValue(bool(valores.recordar_contrasena))
		self.recordar.SetHelpText(_("Guarda la contraseña cifrada con DPAPI en este equipo (nunca en archivos de configuración)."))
		sizer.Add(self.recordar, 0, wx.ALL, 5)
		_etq, self.ca = ui.crear_campo(panel, _("Certificado de una autoridad p&ropia (PEM, opcional):"), wx.TextCtrl,
			value=valores.ca_propia, sizer=sizer, ayuda=_("Solo si su NAS usa un certificado firmado por una autoridad propia. Vacío: "
				"se fija la huella del certificado la primera vez."))
		self.examinar = wx.Button(panel, label=_("E&xaminar..."))
		self.examinar.SetHelpText(_("Elige el archivo PEM de la autoridad propia."))
		sizer.Add(self.examinar, 0, wx.ALL, 5)
		self.solo_lectura = wx.CheckBox(panel, label=_("Solo &lectura (recomendado)"))
		self.solo_lectura.SetValue(True if servidor is None else bool(servidor.solo_lectura))
		self.solo_lectura.SetHelpText(_("Con esta casilla marcada, zCommander no puede cambiar nada en el NAS. Desmarcarla pide confirmación."))
		sizer.Add(self.solo_lectura, 0, wx.ALL, 5)
		self.olvidar = wx.Button(panel, label=_("Ol&vidar la huella y la contraseña guardadas"))
		self.olvidar.SetHelpText(_("La próxima conexión volverá a preguntar por el certificado y la contraseña."))
		self.olvidar.Enable(bool(servidor and (servidor.huella or contrasena_guardada)))
		sizer.Add(self.olvidar, 0, wx.ALL, 5)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		_terminar(self, panel, sizer)
		self.https.Bind(wx.EVT_CHECKBOX, self._al_https)
		self.examinar.Bind(wx.EVT_BUTTON, self._al_examinar)
		self.olvidar.Bind(wx.EVT_BUTTON, self._al_olvidar)
		self.solo_lectura.Bind(wx.EVT_CHECKBOX, self._al_solo_lectura)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		ui.preparar_dialogo(self, foco_inicial=self.nombre)

	def _al_https(self, _evento: wx.CommandEvent) -> None:
		if self.https.GetValue() and self.puerto.GetValue() == 5000:
			self.puerto.SetValue(5001)
		elif not self.https.GetValue() and self.puerto.GetValue() == 5001:
			self.puerto.SetValue(5000)

	def _al_examinar(self, _evento: wx.CommandEvent) -> None:
		with wx.FileDialog(self, _("Certificado de la autoridad propia"), wildcard=_("Certificados (*.pem;*.crt)|*.pem;*.crt"),
				style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialogo:
			if modulo_ui().mostrar_modal(dialogo) == wx.ID_OK:
				self.ca.SetValue(dialogo.GetPath())

	def _al_olvidar(self, _evento: wx.CommandEvent) -> None:
		self.olvidar_huella = self.olvidar_contrasena = True
		self.olvidar.Enable(False)
		modulo_ui().mostrar_mensaje(_("Se olvidarán al pulsar Aceptar."), _("Huella y contraseña"), self)

	def _al_solo_lectura(self, _evento: wx.CommandEvent) -> None:
		if not self.solo_lectura.GetValue():
			permitir, _persistente = DialogoModoEscritura.preguntar(self, self.nombre.GetValue() or _("este NAS"), persistente_fijo=True)
			if not permitir:
				self.solo_lectura.SetValue(True)

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		ui = modulo_ui()
		if not self.nombre.GetValue().strip() or not self.host.GetValue().strip():
			ui.mostrar_error(_("Escriba el nombre y la dirección del NAS."), _("Faltan datos"), self)
			(self.nombre if not self.nombre.GetValue().strip() else self.host).SetFocus()
			return
		host = self.host.GetValue().strip()
		if "://" in host or "/" in host:
			ui.mostrar_error(_("Escriba solo la dirección del NAS, sin http:// ni barras."), _("Dirección no válida"), self)
			self.host.SetFocus()
			return
		evento.Skip()

	def resultado(self) -> ServidorNAS:
		original = self._original
		identificador = original.id if original else id_desde_nombre(self.nombre.GetValue(), self._existentes)
		return ServidorNAS(identificador, self.nombre.GetValue().strip(), self.host.GetValue().strip(), int(self.puerto.GetValue()),
			self.https.GetValue(), "" if self.olvidar_huella or not original else original.huella, self.ca.GetValue().strip(),
			self.usuario.GetValue().strip(), self.solo_lectura.GetValue(), self.recordar.GetValue(), False)


class DialogoServidores(wx.Dialog):
	"""Lista de NAS guardados (13.3): Conectar, Nuevo, Editar, Eliminar y NAS de demostración."""

	CONECTAR, DEMOSTRACION = 1, 2

	def __init__(self, padre: wx.Window | None, complemento: Any) -> None:
		super().__init__(padre, title=_("NAS Synology"), name=_("NAS Synology"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		ui = modulo_ui()
		self._complemento = complemento
		self.accion = 0
		self.elegido: ServidorNAS | None = None
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etq, self.lista = ui.crear_campo(panel, _("&Servidores:"), wx.ListBox, size=(420, 160), sizer=sizer,
			ayuda=_("NAS guardados. Intro conecta con el elegido."))
		_etq, self.detalle = ui.crear_campo(panel, _("&Detalle:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(420, 60),
			sizer=sizer, ayuda=_("Dirección, protocolo, usuario y modo del NAS elegido."))
		self.conectar = wx.Button(panel, label=_("&Conectar"))
		self.nuevo = wx.Button(panel, label=_("&Nuevo..."))
		self.editar = wx.Button(panel, label=_("&Editar..."))
		self.eliminar = wx.Button(panel, label=_("E&liminar"))
		self.demostracion = wx.Button(panel, label=_("NAS de de&mostración"))
		self.cerrar = wx.Button(panel, wx.ID_CANCEL, _("Ce&rrar"))
		self.conectar.SetHelpText(_("Conecta con el NAS elegido y abre su ventana."))
		self.nuevo.SetHelpText(_("Da de alta un NAS nuevo (empieza en solo lectura)."))
		self.editar.SetHelpText(_("Cambia los datos del NAS elegido."))
		self.eliminar.SetHelpText(_("Quita el NAS elegido de la lista y borra su contraseña guardada."))
		self.demostracion.SetHelpText(_("Arranca un NAS simulado en este equipo para practicar sin riesgo: nada sale a la red."))
		sizer.Add(_fila_botones(panel, [self.conectar, self.nuevo, self.editar, self.eliminar]), 0, wx.ALL, 4)
		sizer.Add(_fila_botones(panel, [self.demostracion, self.cerrar]), 0, wx.ALL, 4)
		_terminar(self, panel, sizer)
		self.conectar.SetDefault()
		self.lista.Bind(wx.EVT_LISTBOX, lambda _e: self._actualizar())
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self._terminar_con(self.CONECTAR))
		self.conectar.Bind(wx.EVT_BUTTON, lambda _e: self._terminar_con(self.CONECTAR))
		self.demostracion.Bind(wx.EVT_BUTTON, lambda _e: self._terminar_con(self.DEMOSTRACION))
		self.nuevo.Bind(wx.EVT_BUTTON, lambda _e: self._editar(None))
		self.editar.Bind(wx.EVT_BUTTON, lambda _e: self._editar(self._actual()))
		self.eliminar.Bind(wx.EVT_BUTTON, lambda _e: self._eliminar())
		self._servidores: list[ServidorNAS] = []
		self._cargar()
		ui.preparar_dialogo(self, foco_inicial=self.lista)

	def _cargar(self, elegir: str = "") -> None:
		self._servidores = self._complemento.almacen.todos()
		self.lista.Set([f"{s.nombre} ({_('solo lectura') if s.solo_lectura else _('cambios permitidos')})" for s in self._servidores])
		if self._servidores:
			indice = next((i for i, s in enumerate(self._servidores) if s.id == elegir), 0)
			self.lista.SetSelection(indice)
		self._actualizar()

	def _actual(self) -> ServidorNAS | None:
		indice = self.lista.GetSelection()
		return self._servidores[indice] if 0 <= indice < len(self._servidores) else None

	def _actualizar(self) -> None:
		actual = self._actual()
		self.detalle.SetValue(actual.descripcion() if actual else _("No hay ningún NAS guardado. Pulse Nuevo o pruebe el NAS de demostración."))
		for boton in (self.conectar, self.editar, self.eliminar):
			boton.Enable(actual is not None)

	def _terminar_con(self, accion: int) -> None:
		if accion == self.CONECTAR and self._actual() is None:
			return
		self.accion, self.elegido = accion, self._actual()
		self.EndModal(wx.ID_OK)

	def _editar(self, servidor: ServidorNAS | None) -> None:
		ui = modulo_ui()
		existentes = {s.id for s in self._servidores}
		dialogo = DialogoServidor(self, servidor, existentes, self._complemento.tiene_contrasena(servidor) if servidor else False)
		try:
			if ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			nuevo = dialogo.resultado()
			if dialogo.olvidar_contrasena:
				self._complemento.olvidar_secretos(nuevo.id)
		finally:
			dialogo.Destroy()
		self._complemento.almacen.guardar(nuevo)
		self._cargar(nuevo.id)
		self.lista.SetFocus()

	def _eliminar(self) -> None:
		actual = self._actual()
		if actual is None:
			return
		if not modulo_ui().confirmar(_("¿Quitar {n} de la lista? Se borrará también su contraseña guardada.").format(n=actual.nombre),
				_("Eliminar el NAS"), self, peligroso=True):
			return
		self._complemento.olvidar_secretos(actual.id)
		self._complemento.almacen.eliminar(actual.id)
		self._cargar()
		self.lista.SetFocus()


# ── Modo de escritura ────────────────────────────────────────────────────────


class DialogoModoEscritura(wx.Dialog):
	"""13.6: «Va a permitir que zCommander cambie cosas en el NAS...» con «Cancelar» predeterminado."""

	def __init__(self, padre: wx.Window | None, nombre: str, persistente: bool = False, persistente_fijo: bool = False) -> None:
		titulo = _("Permitir cambios en el NAS")
		super().__init__(padre, title=titulo, name=titulo)
		ui = modulo_ui()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		texto = _("Va a permitir que zCommander cambie cosas en el NAS {n}: arrancar y parar paquetes y contenedores, cambiar permisos, "
			"usuarios y servicios, borrar y mover archivos. Cada acción pedirá confirmación. ¿Permitir cambios?").format(n=nombre)
		_etq, self.texto = ui.crear_campo(panel, _("&Qué se permite:"), wx.TextCtrl, value=texto,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP, size=(440, 110), sizer=sizer)
		self.sesion = wx.RadioButton(panel, label=_("Solo durante esta &sesión"), style=wx.RB_GROUP)
		self.siempre = wx.RadioButton(panel, label=_("&Hasta que lo vuelva a activar"))
		self.sesion.SetHelpText(_("Al cerrar zCommander o desconectar, el NAS vuelve a solo lectura."))
		self.siempre.SetHelpText(_("El NAS queda con los cambios permitidos también en las próximas sesiones."))
		(self.siempre if persistente or persistente_fijo else self.sesion).SetValue(True)
		if persistente_fijo:
			self.sesion.Enable(False)
		sizer.Add(self.sesion, 0, wx.ALL, 5)
		sizer.Add(self.siempre, 0, wx.ALL, 5)
		self.permitir = wx.Button(panel, wx.ID_OK, _("&Permitir cambios"))
		self.cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cancelar"))
		self.cancelar.SetDefault()
		sizer.Add(_fila_botones(panel, [self.permitir, self.cancelar]), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		_terminar(self, panel, sizer)
		ui.preparar_dialogo(self, foco_inicial=self.texto)

	@classmethod
	def preguntar(cls, padre: wx.Window | None, nombre: str, persistente: bool = False, persistente_fijo: bool = False) -> tuple[bool, bool]:
		dialogo = cls(padre, nombre, persistente, persistente_fijo)
		try:
			if modulo_ui().mostrar_modal(dialogo) != wx.ID_OK:
				return False, False
			return True, dialogo.siempre.GetValue()
		finally:
			dialogo.Destroy()


# ── Verificación en dos pasos y certificado ──────────────────────────────────


class DialogoCodigo(wx.Dialog):
	"""13.2: «Código de verificación» de 6 dígitos con la casilla «Recordar este equipo»."""

	def __init__(self, padre: wx.Window | None, servidor: Any, mensaje: str) -> None:
		titulo = _("Verificación en dos pasos: {n}").format(n=servidor.nombre)
		super().__init__(padre, title=titulo, name=titulo)
		ui = modulo_ui()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		aviso = wx.StaticText(panel, label=mensaje)
		aviso.Wrap(420)
		sizer.Add(aviso, 0, wx.ALL, 6)
		_etq, self.codigo = ui.crear_campo(panel, _("Código de &verificación:"), wx.TextCtrl, sizer=sizer,
			ayuda=_("Los 6 dígitos que muestra ahora su aplicación de autenticación (Google Authenticator, Synology Secure SignIn...)."))
		self.codigo.SetMaxLength(8)
		self.recordar = wx.CheckBox(panel, label=_("&Recordar este equipo"))
		self.recordar.SetValue(True)
		self.recordar.SetHelpText(_("DSM recordará este equipo y no volverá a pedir el código. Puede revocarlo en DSM, Dispositivos de confianza."))
		sizer.Add(self.recordar, 0, wx.ALL, 5)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		_terminar(self, panel, sizer)
		ui.preparar_dialogo(self, foco_inicial=self.codigo)


class DialogoHuella(wx.Dialog):
	"""13.2: huella SHA-256 leída por grupos de 4, copiable, con «Aceptar y recordar», «Aceptar solo esta vez» y «Cancelar»."""

	def __init__(self, padre: wx.Window | None, servidor: Any, huella: str, anterior: str) -> None:
		titulo = _("Certificado del NAS {n}").format(n=servidor.nombre)
		super().__init__(padre, title=titulo, name=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		ui = modulo_ui()
		self.huella = huella
		self.decision = "cancelar"
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etq, self.texto = ui.crear_campo(panel, _("&Información del certificado:"), wx.TextCtrl, value=texto_huella(servidor, huella, anterior),
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP, size=(480, 200), sizer=sizer)
		self.recordar = wx.Button(panel, label=_("Aceptar y &recordar"))
		self.solo_ahora = wx.Button(panel, label=_("Aceptar &solo esta vez"))
		self.copiar = wx.Button(panel, label=_("Co&piar la huella"))
		self.cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cancelar"))
		self.recordar.SetHelpText(_("Acepta el certificado y lo recuerda: las próximas conexiones lo comprobarán."))
		self.solo_ahora.SetHelpText(_("Acepta el certificado hasta que cierre zCommander."))
		self.copiar.SetHelpText(_("Copia la huella al portapapeles para compararla con la de DSM."))
		self.cancelar.SetDefault()
		sizer.Add(_fila_botones(panel, [self.recordar, self.solo_ahora, self.copiar, self.cancelar]), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		_terminar(self, panel, sizer)
		self.recordar.Bind(wx.EVT_BUTTON, lambda _e: self._decidir("recordar"))
		self.solo_ahora.Bind(wx.EVT_BUTTON, lambda _e: self._decidir("sesion"))
		self.copiar.Bind(wx.EVT_BUTTON, lambda _e: copiar_al_portapapeles(huella_legible(huella)))
		ui.preparar_dialogo(self, foco_inicial=self.texto)

	def _decidir(self, decision: str) -> None:
		self.decision = decision
		self.EndModal(wx.ID_OK)


def copiar_al_portapapeles(texto: str) -> bool:
	if not wx.TheClipboard.Open():
		return False
	try:
		wx.TheClipboard.SetData(wx.TextDataObject(texto))
		wx.TheClipboard.Flush()
	finally:
		wx.TheClipboard.Close()
	return True


class PreguntasInterfaz:
	"""``Preguntas`` del cliente con los diálogos propios; se llama desde hilos de trabajo y espera en ellos (13.2)."""

	def __init__(self, padre: Any = None) -> None:
		self._padre = padre

	def _padre_actual(self) -> wx.Window | None:
		padre = self._padre() if callable(self._padre) else self._padre
		return padre or wx.GetApp().GetTopWindow()

	def credenciales(self, servidor: Any, motivo: str) -> tuple[str, str, bool] | None:
		def preguntar() -> tuple[str, str, bool] | None:
			ui = modulo_ui()
			usuario = servidor.usuario
			if not usuario:
				usuario = ui.pedir_texto(_("&Usuario de DSM:"), _("Conectar con {n}").format(n=servidor.nombre), "", self._padre_actual())
				if not usuario:
					return None
			contrasena = ui.pedir_texto(_("&Contraseña de {u}:").format(u=usuario), _("Conectar con {n}").format(n=servidor.nombre), "",
				self._padre_actual(), contrasena=True)
			if contrasena is None:
				return None
			return usuario, contrasena, bool(servidor.recordar_contrasena)

		return en_interfaz(preguntar)

	def codigo(self, servidor: Any, mensaje: str) -> tuple[str, bool] | None:
		def preguntar() -> tuple[str, bool] | None:
			dialogo = DialogoCodigo(self._padre_actual(), servidor, mensaje)
			try:
				if modulo_ui().mostrar_modal(dialogo) != wx.ID_OK:
					return None
				return dialogo.codigo.GetValue().strip(), dialogo.recordar.GetValue()
			finally:
				dialogo.Destroy()

		return en_interfaz(preguntar)

	def huella(self, servidor: Any, huella: str, anterior: str) -> str:
		def preguntar() -> str:
			dialogo = DialogoHuella(self._padre_actual(), servidor, huella, anterior)
			try:
				modulo_ui().mostrar_modal(dialogo)
				return dialogo.decision
			finally:
				dialogo.Destroy()

		return en_interfaz(preguntar)

	def contrasena_dsm(self, servidor: Any, motivo: str) -> str | None:
		return en_interfaz(lambda: modulo_ui().pedir_texto(_("&Contraseña de {u}:").format(u=servidor.usuario), motivo, "",
			self._padre_actual(), contrasena=True))


class ConfirmadorInterfaz:
	"""``areas.Confirmador`` con los diálogos de ``zc.ui`` (en el hilo de la interfaz)."""

	def __init__(self, padre: wx.Window | None) -> None:
		self._padre = padre

	def confirmar(self, titulo: str, texto: str, peligroso: bool = True) -> bool:
		return bool(modulo_ui().confirmar(texto, titulo, self._padre, peligroso=peligroso))

	def escribir_nombre(self, titulo: str, texto: str, esperado: str) -> bool:
		ui = modulo_ui()
		escrito = ui.pedir_texto(_("&Nombre del NAS:"), titulo + ": " + texto, "", self._padre)
		if escrito is None:
			return False
		if escrito.strip().casefold() != esperado.strip().casefold():
			ui.mostrar_error(_("El nombre no coincide con {n}: no se ha hecho nada.").format(n=esperado), titulo, self._padre)
			return False
		return True

	def pedir(self, titulo: str, peticion: Any) -> str | None:
		ui = modulo_ui()
		if peticion.tipo == "opcion":
			usadas = {"c"}
			opciones = [poner_letra(o, usadas) for o in peticion.opciones]
			indice = ui.elegir_opcion(peticion.etiqueta.replace("&", "").rstrip(":"), titulo, opciones, self._padre)
			return None if indice is None else peticion.opciones[indice]
		return ui.pedir_texto(peticion.etiqueta, titulo, peticion.valor, self._padre, contrasena=peticion.tipo == "contrasena")


# ── Elegir área ──────────────────────────────────────────────────────────────


class DialogoAreas(wx.Dialog):
	def __init__(self, padre: wx.Window | None, titulos: list[str]) -> None:
		titulo = _("Ir a un área del NAS")
		super().__init__(padre, title=titulo, name=titulo)
		ui = modulo_ui()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etq, self.lista = ui.crear_campo(panel, _("Á&rea:"), wx.ListBox, choices=titulos, size=(320, 260), sizer=sizer,
			ayuda=_("Intro abre la ventana del NAS en el área elegida."))
		if titulos:
			self.lista.SetSelection(0)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		_terminar(self, panel, sizer)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.EndModal(wx.ID_OK))
		ui.preparar_dialogo(self, foco_inicial=self.lista)


# ── Enlace, comprimir y extraer ──────────────────────────────────────────────


class DialogoEnlace(wx.Dialog):
	"""Crear un enlace compartido (``SYNO.FileStation.Sharing create``)."""

	def __init__(self, padre: wx.Window | None, elementos: list[str]) -> None:
		titulo = _("Crear un enlace compartido")
		super().__init__(padre, title=titulo, name=titulo)
		ui = modulo_ui()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etq, self.elementos = ui.crear_campo(panel, _("&Elementos:"), wx.TextCtrl, value="\n".join(elementos),
			style=wx.TE_MULTILINE | wx.TE_READONLY, size=(420, 70), sizer=sizer)
		_etq, self.contrasena = ui.crear_campo(panel, _("Con&traseña (opcional, hasta 16 caracteres):"), wx.TextCtrl, style=wx.TE_PASSWORD,
			sizer=sizer, ayuda=_("Quien abra el enlace tendrá que escribirla. Vacía: sin contraseña."))
		self.contrasena.SetMaxLength(16)
		_etq, self.caduca = ui.crear_campo(panel, _("Ca&duca el (AAAA-MM-DD, vacío para nunca):"), wx.TextCtrl, sizer=sizer,
			ayuda=_("Fecha en la que el enlace deja de funcionar, por ejemplo 2026-12-31."))
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		_terminar(self, panel, sizer)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		ui.preparar_dialogo(self, foco_inicial=self.contrasena)

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		import re

		fecha = self.caduca.GetValue().strip()
		if fecha and not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha):
			modulo_ui().mostrar_error(_("Escriba la fecha como AAAA-MM-DD, por ejemplo 2026-12-31, o déjela vacía."), _("Fecha no válida"), self)
			self.caduca.SetFocus()
			return
		evento.Skip()


NIVELES = (("moderate", "Normal"), ("store", "Solo guardar"), ("fastest", "La más rápida"), ("best", "La máxima"))


class DialogoComprimir(wx.Dialog):
	def __init__(self, padre: wx.Window | None, nombre: str, cuantos: int) -> None:
		titulo = _("Comprimir en el NAS")
		super().__init__(padre, title=titulo, name=titulo)
		ui = modulo_ui()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		resumen = wx.StaticText(panel, label=_n("Se comprime {n} elemento en el propio NAS.", "Se comprimen {n} elementos en el propio NAS.",
			cuantos).format(n=cuantos))
		sizer.Add(resumen, 0, wx.ALL, 6)
		_etq, self.nombre = ui.crear_campo(panel, _("&Nombre del archivo comprimido:"), wx.TextCtrl, value=nombre, sizer=sizer,
			ayuda=_("Se crea en la misma carpeta del NAS."))
		_etq, self.formato = ui.crear_campo(panel, _("&Formato:"), wx.Choice, choices=["ZIP", "7z"], sizer=sizer)
		self.formato.SetSelection(0)
		_etq, self.nivel = ui.crear_campo(panel, _("Ni&vel de compresión:"), wx.Choice, choices=[_(t) for _c, t in NIVELES], sizer=sizer)
		self.nivel.SetSelection(0)
		_etq, self.contrasena = ui.crear_campo(panel, _("Con&traseña (opcional):"), wx.TextCtrl, style=wx.TE_PASSWORD, sizer=sizer,
			ayuda=_("Cifra el archivo comprimido. Vacía: sin contraseña."))
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		_terminar(self, panel, sizer)
		self.formato.Bind(wx.EVT_CHOICE, self._al_formato)
		ui.preparar_dialogo(self, foco_inicial=self.nombre)

	def _al_formato(self, _evento: wx.CommandEvent) -> None:
		extension = ".7z" if self.formato.GetSelection() == 1 else ".zip"
		nombre = self.nombre.GetValue()
		base = nombre.rsplit(".", 1)[0] if nombre.lower().endswith((".zip", ".7z")) else nombre
		self.nombre.SetValue(base + extension)

	def valores(self) -> dict[str, Any]:
		return {"nombre": self.nombre.GetValue().strip(), "formato": "7z" if self.formato.GetSelection() == 1 else "zip",
			"nivel": NIVELES[max(0, self.nivel.GetSelection())][0], "contrasena": self.contrasena.GetValue()}


class DialogoExtraer(wx.Dialog):
	def __init__(self, padre: wx.Window | None, archivo: str, destino: str) -> None:
		titulo = _("Extraer en el NAS")
		super().__init__(padre, title=titulo, name=titulo)
		ui = modulo_ui()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		resumen = wx.StaticText(panel, label=_("Se extrae {a} en el propio NAS.").format(a=archivo))
		sizer.Add(resumen, 0, wx.ALL, 6)
		_etq, self.destino = ui.crear_campo(panel, _("Carpeta de &destino en el NAS:"), wx.TextCtrl, value=destino, sizer=sizer,
			ayuda=_("Ruta de File Station, por ejemplo /Documentos/Facturas."))
		self.subcarpeta = wx.CheckBox(panel, label=_("Crear una &subcarpeta con el nombre del archivo"))
		self.subcarpeta.SetValue(True)
		self.sobrescribir = wx.CheckBox(panel, label=_("Sobrescribir los archivos que ya &existan"))
		sizer.Add(self.subcarpeta, 0, wx.ALL, 5)
		sizer.Add(self.sobrescribir, 0, wx.ALL, 5)
		_etq, self.contrasena = ui.crear_campo(panel, _("Con&traseña (si la tiene):"), wx.TextCtrl, style=wx.TE_PASSWORD, sizer=sizer)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		_terminar(self, panel, sizer)
		ui.preparar_dialogo(self, foco_inicial=self.destino)


# ── SSH ──────────────────────────────────────────────────────────────────────


class DialogoSSH(wx.Dialog):
	"""Herramientas avanzadas por SSH (13.8). La contraseña de sudo nunca se guarda."""

	def __init__(self, padre: wx.Window | None, complemento: Any, conexion: Any) -> None:
		from ..ssh import ACCIONES_PAQUETE, HERRAMIENTAS

		titulo = _("Herramientas avanzadas por SSH: {n}").format(n=conexion.servidor.nombre)
		super().__init__(padre, title=titulo, name=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		ui = modulo_ui()
		self._complemento = complemento
		self._conexion = conexion
		self._herramientas = HERRAMIENTAS
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiquetas = [f"{_(h.etiqueta)}{_(' (cambia cosas)') if h.escritura else ''}" for h in HERRAMIENTAS]
		_etq, self.lista = ui.crear_campo(panel, _("&Herramienta:"), wx.ListBox, choices=etiquetas, size=(460, 130), sizer=sizer,
			ayuda=_("Elija qué hacer. Las que cambian cosas solo funcionan con los cambios permitidos en el NAS."))
		self.lista.SetSelection(0)
		_etq, self.dato = ui.crear_campo(panel, _("&Dato que pide la herramienta:"), wx.TextCtrl, value="sata1", sizer=sizer)
		_etq, self.accion = ui.crear_campo(panel, _("Acción del pa&quete:"), wx.Choice, choices=list(ACCIONES_PAQUETE), sizer=sizer)
		self.accion.SetSelection(0)
		_etq, self.puerto = ui.crear_campo(panel, _("&Puerto SSH:"), wx.SpinCtrl, min=1, max=65535, initial=22, sizer=sizer)
		_etq, self.sudo = ui.crear_campo(panel, _("Contraseña de &sudo (no se guarda):"), wx.TextCtrl, style=wx.TE_PASSWORD, sizer=sizer,
			ayuda=_("La contraseña de su cuenta en el NAS. Se envía solo a sudo y se olvida al cerrar este diálogo."))
		_etq, self.resultado = ui.crear_campo(panel, _("&Resultado:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
			size=(560, 220), sizer=sizer)
		self.ejecutar = wx.Button(panel, label=_("&Ejecutar"))
		self.cerrar = wx.Button(panel, wx.ID_CANCEL, _("Cerr&ar"))
		self.ejecutar.SetDefault()
		sizer.Add(_fila_botones(panel, [self.ejecutar, self.cerrar]), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		_terminar(self, panel, sizer)
		self.lista.Bind(wx.EVT_LISTBOX, lambda _e: self._al_elegir())
		self.ejecutar.Bind(wx.EVT_BUTTON, lambda _e: self._al_ejecutar())
		self._al_elegir()
		ui.preparar_dialogo(self, foco_inicial=self.lista)

	def _herramienta(self) -> Any:
		return self._herramientas[max(0, self.lista.GetSelection())]

	def _al_elegir(self) -> None:
		herramienta = self._herramienta()
		ejemplos = {"disco": "sata1", "contenedor": "jellyfin", "carpeta": "/volume1/docker/multimedia", "paquete": "ContainerManager",
			"api": "SYNO.Core.System info 3"}
		self.dato.Enable(bool(herramienta.pide))
		if herramienta.pide:
			self.dato.SetValue(ejemplos.get(herramienta.pide, ""))
		self.dato.SetHelpText(_(herramienta.ayuda))
		self.accion.Enable(herramienta.pide == "paquete")

	def _al_ejecutar(self) -> None:
		herramienta = self._herramienta()
		ui = modulo_ui()
		if herramienta.escritura and self._conexion.solo_lectura:
			ui.mostrar_error(_("Esta herramienta cambia cosas en el NAS y el NAS está en solo lectura."), _("Solo lectura"), self)
			return
		if herramienta.escritura and not ui.confirmar(_("¿Ejecutar «{h}» con {d} en el NAS {n}?").format(h=_(herramienta.etiqueta),
				d=self.dato.GetValue(), n=self._conexion.servidor.nombre), _("Herramientas por SSH"), self, peligroso=True):
			return
		datos = {"herramienta": herramienta.id, "dato": self.dato.GetValue().strip(), "accion": self.accion.GetStringSelection(),
			"puerto": int(self.puerto.GetValue()), "sudo": self.sudo.GetValue()}
		self.resultado.SetValue(_("Ejecutando..."))
		self.ejecutar.Enable(False)
		self._complemento.ejecutar_ssh(self._conexion, datos, self._al_terminar)

	def _al_terminar(self, texto: str) -> None:
		if not self:
			return
		self.ejecutar.Enable(True)
		self.resultado.SetValue(texto)
		self.resultado.SetFocus()
		self.resultado.SetInsertionPoint(0)
