# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Gestor de conexiones (Ctrl+K): lista de sitios con Conectar, Nuevo, Editar, Duplicar y Eliminar.

Por qué así:

- La lista es un ``wx.ListCtrl`` nativo en modo informe (Nombre, Protocolo,
  Servidor, Usuario), con su etiqueta «&Sitios:» creada justo antes: el
  lector anuncia cada fila con sus columnas y el estado de selección.
- Intro en la lista conecta (es también el botón predeterminado), Supr
  elimina (con confirmación, Intro en «No») y F2 edita, como en los paneles.
- Las preguntas y los avisos pasan por funciones de este módulo
  (``_editar``, ``_confirmar``, ``_avisar``) para que las pruebas las
  sustituyan: el ``conftest`` prohíbe los ``ShowModal`` reales.
- Tras crear, editar, duplicar o eliminar, el cursor queda en el sitio
  afectado (o en el siguiente) y se anuncia el resultado.
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import conexiones
from app.ui import anuncios
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _editar(padre: wx.Window, sitio: conexiones.Sitio | None, tiene_contrasena: bool, tiene_frase: bool):
	"""Abre el diálogo de sitio; ``(sitio, contrasena, frase)`` o ``None`` si se cancela."""
	from app.ui.dialogos.d_sitio import DialogoSitio

	dialogo = DialogoSitio(padre, sitio, tiene_contrasena, tiene_frase)
	try:
		if dialogo.ShowModal() != wx.ID_OK:
			return None
		return dialogo.sitio(), dialogo.contrasena(), dialogo.frase()
	finally:
		dialogo.Destroy()


def _confirmar(padre: wx.Window, mensaje: str) -> bool:
	return dialogos.confirmar(padre, mensaje, _("Eliminar sitio"), peligroso=True) == wx.ID_YES


def _avisar(padre: wx.Window, mensaje: str) -> None:
	dialogos.mostrar_error(padre, mensaje, _("Conexiones"))


class DialogoConexiones(wx.Dialog):
	"""Gestor de sitios. Con «Conectar», ``ShowModal`` devuelve ``wx.ID_OK`` y ``sitio_elegido`` tiene el sitio."""

	COLUMNAS = (("nombre", "Nombre", 180), ("protocolo", "Protocolo", 170), ("servidor", "Servidor", 170), ("usuario", "Usuario", 110))

	def __init__(self, padre: wx.Window | None, repositorio: conexiones.Conexiones) -> None:
		titulo = _("Conexiones FTP y SFTP")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		self.repositorio = repositorio
		self.sitio_elegido: conexiones.Sitio | None = None
		self._sitios: list[conexiones.Sitio] = []
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.lista = crear_campo(panel, _("&Sitios:"), wx.ListCtrl, style=wx.LC_REPORT | wx.LC_SINGLE_SEL,
			size=panel.FromDIP(wx.Size(640, 260)),
			ayuda=_("Sitios guardados. Intro conecta, F2 edita y Supr elimina."), sizer=sizer)
		for indice, (_clave, cabecera, ancho) in enumerate(self.COLUMNAS):
			self.lista.InsertColumn(indice, _(cabecera), width=panel.FromDIP(ancho))
		self.texto_vacio = wx.StaticText(panel, label=_("No hay sitios guardados. Pulse Nuevo para crear uno."))
		sizer.Add(self.texto_vacio, 0, wx.ALL, 5)

		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_conectar = wx.Button(panel, wx.ID_OK, _("&Conectar"))
		self.boton_conectar.SetHelpText(_("Conecta el panel con el sitio elegido."))
		self.boton_nuevo = wx.Button(panel, label=_("&Nuevo..."))
		self.boton_nuevo.SetHelpText(_("Crea un sitio nuevo."))
		self.boton_editar = wx.Button(panel, label=_("&Editar..."))
		self.boton_editar.SetHelpText(_("Cambia los datos del sitio elegido."))
		self.boton_duplicar = wx.Button(panel, label=_("&Duplicar"))
		self.boton_duplicar.SetHelpText(_("Crea una copia del sitio elegido, con su contraseña."))
		self.boton_eliminar = wx.Button(panel, label=_("E&liminar"))
		self.boton_eliminar.SetHelpText(_("Elimina el sitio elegido y su contraseña guardada."))
		self.boton_cerrar = wx.Button(panel, wx.ID_CANCEL, _("Ce&rrar"))
		self.boton_cerrar.SetHelpText(_("Cierra el gestor sin conectar."))
		for boton in (self.boton_conectar, self.boton_nuevo, self.boton_editar, self.boton_duplicar, self.boton_eliminar, self.boton_cerrar):
			botones.Add(boton, 0, wx.ALL, 4)
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.boton_conectar.SetDefault()
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)

		self.boton_conectar.Bind(wx.EVT_BUTTON, lambda _e: self.conectar())
		self.boton_nuevo.Bind(wx.EVT_BUTTON, lambda _e: self.nuevo())
		self.boton_editar.Bind(wx.EVT_BUTTON, lambda _e: self.editar())
		self.boton_duplicar.Bind(wx.EVT_BUTTON, lambda _e: self.duplicar())
		self.boton_eliminar.Bind(wx.EVT_BUTTON, lambda _e: self.eliminar())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.conectar())
		self.lista.Bind(wx.EVT_LIST_KEY_DOWN, self._al_tecla_lista)
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._actualizar_botones())
		self.lista.Bind(wx.EVT_LIST_ITEM_DESELECTED, lambda _e: self._actualizar_botones())
		self.recargar()
		preparar_dialogo(self, foco_inicial=self.lista if self._sitios else self.boton_nuevo)
		self.CentreOnParent()

	# Lista ------------------------------------------------------------------

	def recargar(self, elegir_id: str | None = None, indice_respaldo: int = 0) -> None:
		"""Vuelve a leer los sitios y deja el cursor en ``elegir_id`` (o en ``indice_respaldo``)."""
		try:
			self._sitios = self.repositorio.sitios()
		except Exception:  # noqa: BLE001 - un archivo ilegible no debe impedir abrir el gestor
			log.exception("No se pudieron leer los sitios")
			self._sitios = []
		self.lista.DeleteAllItems()
		for fila, sitio in enumerate(self._sitios):
			self.lista.InsertItem(fila, sitio.nombre)
			self.lista.SetItem(fila, 1, conexiones.nombre_protocolo(sitio.protocolo))
			extra = f":{sitio.puerto}" if sitio.puerto != conexiones.PUERTOS[sitio.protocolo] else ""
			self.lista.SetItem(fila, 2, sitio.servidor + extra)
			self.lista.SetItem(fila, 3, sitio.usuario or _("anónimo"))
		if self._sitios:
			fila = next((i for i, s in enumerate(self._sitios) if s.id == elegir_id), min(indice_respaldo, len(self._sitios) - 1))
			self.lista.SetItemState(fila, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
			self.lista.EnsureVisible(fila)
		self.texto_vacio.Show(not self._sitios)
		self._actualizar_botones()
		self.Layout()

	def elegido(self) -> conexiones.Sitio | None:
		fila = self.lista.GetFirstSelected()
		if fila < 0:
			fila = self.lista.GetFocusedItem()
		return self._sitios[fila] if 0 <= fila < len(self._sitios) else None

	def _actualizar_botones(self) -> None:
		hay = self.elegido() is not None
		for boton in (self.boton_conectar, self.boton_editar, self.boton_duplicar, self.boton_eliminar):
			boton.Enable(hay)

	def _al_tecla_lista(self, evento: wx.ListEvent) -> None:
		tecla = evento.GetKeyCode()
		if tecla == wx.WXK_DELETE:
			self.eliminar()
		elif tecla == wx.WXK_F2:
			self.editar()
		else:
			evento.Skip()

	# Acciones ---------------------------------------------------------------

	def conectar(self) -> None:
		sitio = self.elegido()
		if sitio is None:
			return
		self.sitio_elegido = sitio
		if self.IsModal():
			self.EndModal(wx.ID_OK)
		else:
			self.SetReturnCode(wx.ID_OK)

	def _guardar(self, sitio, contrasena, frase) -> conexiones.Sitio | None:
		try:
			return self.repositorio.guardar(sitio, contrasena, frase)
		except ValueError as error:
			_avisar(self, str(error))
		except Exception as error:  # noqa: BLE001 - OSError del archivo o ErrorSecretos de DPAPI
			log.exception("No se pudo guardar el sitio %s", sitio.nombre)
			_avisar(self, _("No se pudo guardar el sitio: {e}").format(e=error))
		return None

	def nuevo(self) -> None:
		resultado = _editar(self, None, False, False)
		if resultado is None:
			self.lista.SetFocus()
			return
		guardado = self._guardar(*resultado)
		if guardado is not None:
			self.recargar(guardado.id)
			anuncios.anunciar(_("Sitio {n} creado").format(n=guardado.nombre), anuncios.RESULTADO)
		self.lista.SetFocus()

	def editar(self) -> None:
		sitio = self.elegido()
		if sitio is None:
			return
		resultado = _editar(self, sitio, self.repositorio.tiene_contrasena(sitio.id), self.repositorio.tiene_frase(sitio.id))
		if resultado is not None:
			guardado = self._guardar(*resultado)
			if guardado is not None:
				self.recargar(guardado.id)
				anuncios.anunciar(_("Sitio {n} guardado").format(n=guardado.nombre), anuncios.RESULTADO)
		self.lista.SetFocus()

	def duplicar(self) -> None:
		sitio = self.elegido()
		if sitio is None:
			return
		try:
			copia = self.repositorio.duplicar(sitio.id)
		except Exception as error:  # noqa: BLE001 - OSError o ErrorSecretos
			log.exception("No se pudo duplicar el sitio %s", sitio.nombre)
			_avisar(self, _("No se pudo duplicar el sitio: {e}").format(e=error))
			return
		if copia is not None:
			self.recargar(copia.id)
			anuncios.anunciar(_("Creado {n}").format(n=copia.nombre), anuncios.RESULTADO)
		self.lista.SetFocus()

	def eliminar(self) -> None:
		sitio = self.elegido()
		if sitio is None:
			return
		if not _confirmar(self, _("¿Eliminar el sitio «{n}» y su contraseña guardada?").format(n=sitio.nombre)):
			self.lista.SetFocus()
			return
		fila = self._sitios.index(sitio)
		try:
			self.repositorio.eliminar(sitio.id)
		except Exception as error:  # noqa: BLE001 - OSError o ErrorSecretos
			log.exception("No se pudo eliminar el sitio %s", sitio.nombre)
			_avisar(self, _("No se pudo eliminar el sitio: {e}").format(e=error))
			return
		self.recargar(indice_respaldo=fila)
		anuncios.anunciar(_("Sitio {n} eliminado").format(n=sitio.nombre), anuncios.RESULTADO)
		(self.lista if self._sitios else self.boton_nuevo).SetFocus()
