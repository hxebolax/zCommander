# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Compartir una carpeta o una nube en la red con ``serve`` de rclone (diseño 2.0, 12.6; rclone.md 4.9).

Por defecto solo en ``127.0.0.1`` (este equipo); escuchar en la red local exige
marcar la casilla y confirmarlo, con el aviso del cortafuegos de Windows.
Usuario y contraseña aleatorios; solo lectura por defecto. La lista de carpetas
compartidas permite copiar la dirección y dejar de compartir.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

import wx

from app.plugins import api

from . import comun

_ = api.traduccion("zc_nubes")[0]

PROTOCOLOS = [("webdav", _("WebDAV (unidad de red, programas de archivos)")), ("sftp", _("SFTP (SSH)")),
	("http", _("HTTP (página web de solo lectura)")), ("dlna", _("DLNA (televisores y reproductores multimedia)"))]


class DialogoServir(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, origenes: list[tuple[str, str]], origen: str = "", *,
			solo_local: bool = True) -> None:
		super().__init__(zc, padre, _("Compartir en la red"))
		self.origen = comun.elegir(zc, self.panel, _("&Qué compartir:"), origenes, origen, sizer=self.sizer,
			ayuda=_("Una cuenta de nube o la carpeta del panel activo."))
		self.protocolo = comun.elegir(zc, self.panel, _("&Protocolo:"), PROTOCOLOS, "webdav", sizer=self.sizer,
			ayuda=_("Cómo se conectarán los demás programas o aparatos."))
		self.red = comun.casilla(self.panel, _("Permitir el acceso desde la &red local"), _("Sin marcar, solo este equipo puede "
			"conectarse. Marcada, cualquier equipo de su red podrá hacerlo (se pedirá confirmación)."), not solo_local, sizer=self.sizer)
		self.puerto = comun.campo(zc, self.panel, _("P&uerto (0 automático):"), wx.SpinCtrl, sizer=self.sizer, min=0, max=65535,
			initial=0, ayuda=_("Puerto en el que se escucha; 0 elige uno libre."))
		self.usuario = comun.campo(zc, self.panel, _("U&suario:"), wx.TextCtrl, "zc", sizer=self.sizer,
			ayuda=_("Usuario que tendrán que escribir (DLNA no usa usuario)."))
		self.contrasena = comun.campo(zc, self.panel, _("Con&traseña:"), wx.TextCtrl, secrets.token_urlsafe(12), sizer=self.sizer,
			ayuda=_("Contraseña aleatoria; puede cambiarla."))
		self.solo_lectura = comun.casilla(self.panel, _("Solo &lectura"), _("Quien se conecte podrá ver y bajar, pero no cambiar nada."),
			True, sizer=self.sizer)
		self.botones(wx.OK | wx.CANCEL)
		self.terminar(self.origen)

	def datos(self) -> dict[str, Any]:
		return {"origen": comun.valor_elegido(self.origen), "tipo": comun.valor_elegido(self.protocolo), "red": self.red.GetValue(),
			"puerto": self.puerto.GetValue(), "usuario": self.usuario.GetValue().strip(), "contrasena": self.contrasena.GetValue(),
			"solo_lectura": self.solo_lectura.GetValue()}


class DialogoServicios(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, listar: Callable[[], list[dict[str, str]]], parar: Callable[[str], None]) -> None:
		super().__init__(zc, padre, _("Carpetas compartidas por zCommander"))
		self._listar = listar
		self._parar = parar
		self.filas: list[dict[str, str]] = []
		self.lista = comun.lista(zc, self.panel, _("Carpetas co&mpartidas:"), [(_("Protocolo"), 100), (_("Dirección"), 220),
			(_("Qué"), 260)], sizer=self.sizer, ayuda=_("Lo que zCommander comparte ahora; Supr deja de compartir lo elegido."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		comun.boton(self.panel, _("&Dejar de compartir"), _("Deja de compartir lo elegido."), self.parar, sizer=fila)
		comun.boton(self.panel, _("Copiar la di&rección"), _("Copia la dirección para escribirla en otro programa."), self.copiar,
			sizer=fila)
		self.sizer.Add(fila, 0, wx.ALL, 4)
		cerrar = wx.Button(self.panel, wx.ID_CLOSE, _("&Cerrar"))
		cerrar.SetHelpText(_("Cierra la ventana."))
		self.sizer.Add(cerrar, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE) if self.IsModal() else self.Close(), id=wx.ID_CLOSE)
		self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla)
		self.refrescar()
		self.terminar(self.lista, wx.ID_CLOSE)

	def refrescar(self) -> None:
		self.filas = self._listar()
		comun.llenar_lista(self.lista, [[s["tipo"], s["addr"], s["fs"]] for s in self.filas] or [[_("Nada"), "", ""]])

	def _tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.parar()
			return
		evento.Skip()

	def _elegido(self) -> dict[str, str] | None:
		fila = comun.fila_actual(self.lista)
		return self.filas[fila] if 0 <= fila < len(self.filas) else None

	def parar(self) -> None:
		elegido = self._elegido()
		if elegido is not None:
			self._parar(elegido["id"])
			self.refrescar()

	def copiar(self) -> None:
		elegido = self._elegido()
		if elegido is not None and comun.copiar_al_portapapeles(elegido["addr"]):
			self.zc.anunciar(_("Dirección copiada"), api.RESULTADO)
