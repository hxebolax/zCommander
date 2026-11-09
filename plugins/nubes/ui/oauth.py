# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Espera accesible de la autorización y de los trabajos cortos (diseño 2.0, 12.5 y 15.1; nubes.md 10).

``DialogoEspera`` explica lo que va a pasar, tiene un texto de estado de solo
lectura que el lector puede releer, una barra con nombre y un anuncio prudente
cada 30 s. En modo OAuth ofrece «Abrir el &navegador» (predeterminado),
«&Copiar el enlace», «A&utorizar desde otro equipo...» y «&Cancelar» (que para
la autorización con ``config/oauthstop``). El trabajo corre en un hilo
(``zc.tareas``); el diálogo nunca espera bloqueado a la red.

``DialogoToken`` es la alternativa de pegar el token: enseña la orden
``rclone authorize "<tipo>"`` para copiarla y un campo multilínea para pegar el
resultado.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import wx

from app.plugins import api

from . import comun

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

ANUNCIO_CADA_S = 30
OTRO_EQUIPO = wx.NewIdRef()


class DialogoEspera(comun.DialogoNubes):
	"""Espera de un trabajo en un hilo; con ``url`` es la espera de una autorización en el navegador."""

	def __init__(self, zc: Any, padre: wx.Window | None, titulo: str, explicacion: str, *, url: str = "",
			otro_equipo: bool = False, estado: str = "") -> None:
		super().__init__(zc, padre, titulo)
		self.url = url
		self.resultado: Any = None
		self.error: BaseException | None = None
		self.tarea: Any = None
		self._terminada = False
		self._codigo = wx.ID_OK
		self._inicio = time.monotonic()
		self.explicacion = comun.texto_solo_lectura(zc, self.panel, _("&Qué va a pasar:"), explicacion, sizer=self.sizer, alto=90)
		self.estado = comun.campo(zc, self.panel, _("&Estado:"), wx.TextCtrl, estado or _("Esperando..."), sizer=self.sizer,
			style=wx.TE_READONLY, ayuda=_("Estado de la espera; se puede releer en cualquier momento."))
		wx.StaticText(self.panel, label=_("Progreso de la espera"))
		self.barra = wx.Gauge(self.panel, range=100, name=_("Progreso de la espera"))
		self.sizer.Add(self.barra, 0, wx.EXPAND | wx.ALL, 5)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_navegador = self.boton_copiar = self.boton_otro = None
		if url:
			self.boton_navegador = comun.boton(self.panel, _("Abrir el &navegador"), _("Abre la página de autorización en el navegador predeterminado."),
				self.abrir_navegador, sizer=fila)
			self.boton_copiar = comun.boton(self.panel, _("&Copiar el enlace"),
				_("Copia la dirección de autorización para abrirla en otro navegador."), self.copiar, sizer=fila)
			if otro_equipo:
				self.boton_otro = comun.boton(self.panel, _("A&utorizar desde otro equipo..."),
					_("Para autorizar con rclone en otro equipo y pegar aquí el resultado."), self.otro_equipo, sizer=fila)
		self.boton_cancelar = comun.boton(self.panel, _("Cance&lar") if url else _("&Cancelar"), _("Detiene la espera."), self.cancelar,
			sizer=fila, identificador=wx.ID_CANCEL)
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		if self.boton_navegador is not None:
			self.boton_navegador.SetDefault()
		self.Bind(wx.EVT_CLOSE, lambda _e: self.cancelar())
		self._reloj = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self._latido, self._reloj)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
		self.terminar(self.boton_navegador or self.estado)

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self and self._reloj.IsRunning():
			self._reloj.Stop()
		evento.Skip()

	def _latido(self, _evento: wx.TimerEvent) -> None:
		self.barra.Pulse()
		transcurrido = int(time.monotonic() - self._inicio)
		if transcurrido and transcurrido % ANUNCIO_CADA_S == 0:
			texto = _("Sigue esperando la autorización") if self.url else _("Sigue en marcha")
			self.zc.anunciar(texto, api.DETALLE)

	def poner_estado(self, texto: str) -> None:
		if self:
			self.estado.SetValue(texto)

	def abrir_navegador(self) -> None:
		if comun.abrir_navegador(self.url):
			self.poner_estado(_("Esperando la autorización en el navegador. Cuando termine, vuelva aquí."))
		else:
			self.poner_estado(_("No se pudo abrir el navegador; copie el enlace y ábralo a mano."))

	def copiar(self) -> None:
		if comun.copiar_al_portapapeles(self.url):
			self.zc.anunciar(_("Enlace copiado"), api.RESULTADO)

	def otro_equipo(self) -> None:
		self._parar(OTRO_EQUIPO)

	def cancelar(self) -> None:
		self.poner_estado(_("Cancelando..."))
		self._parar(wx.ID_CANCEL)

	def _parar(self, codigo: int) -> None:
		self._codigo = codigo
		tarea = self.tarea
		if tarea is not None and not self._terminada:
			tarea.token.cancelar()
		elif self.IsModal():
			self.EndModal(codigo)

	def lanzar(self, funcion: Callable[[Any], Any], *, sonido_inicio: str = "", sonido_fin: str = "") -> int:
		"""Muestra el diálogo mientras ``funcion(tarea)`` corre en un hilo. Devuelve wx.ID_OK, wx.ID_CANCEL u ``OTRO_EQUIPO``."""
		self._codigo = wx.ID_OK
		self._terminada = False

		def al_terminar(resultado: Any) -> None:
			self.resultado = resultado
			self._terminada = True
			if sonido_fin:
				self.zc.sonidos.sonar(sonido_fin)
				_traer_al_frente(self)
			if self and self.IsModal():
				self.EndModal(wx.ID_OK)

		def al_fallar(error: BaseException) -> None:
			self._terminada = True
			if not isinstance(error, (api.Cancelado,)) and type(error).__name__ != "TareaCancelada":
				self.error = error
			if self and self.IsModal():
				self.EndModal(self._codigo if self._codigo != wx.ID_OK else wx.ID_CANCEL)

		if sonido_inicio:
			self.zc.sonidos.sonar(sonido_inicio)
		self.tarea = self.zc.tareas.enviar(funcion, al_terminar=al_terminar, al_fallar=al_fallar, nombre="zc-nubes-espera")
		self._reloj.Start(1000)
		codigo = comun.mostrar_modal(self.zc, self)
		self._reloj.Stop()
		if self.error is not None:
			raise self.error
		return codigo


def _traer_al_frente(ventana: wx.Window) -> None:
	"""Trae zCommander al frente cuando llega la autorización (Windows puede limitarlo; se avisa también con sonido)."""
	try:
		superior = wx.GetTopLevelParent(ventana) or ventana
		superior.Raise()
		superior.RequestUserAttention()
	except RuntimeError:
		log.debug("No se pudo traer la ventana al frente", exc_info=True)


def esperar(zc: Any, padre: wx.Window | None, titulo: str, explicacion: str, funcion: Callable[[Any], Any], **opciones: Any) -> Any:
	"""Atajo: ejecuta ``funcion(tarea)`` con un ``DialogoEspera``; devuelve su resultado o lanza ``Cancelado``."""
	dialogo = DialogoEspera(zc, padre, titulo, explicacion, estado=opciones.pop("estado", ""))
	try:
		codigo = dialogo.lanzar(funcion, **opciones)
		if codigo != wx.ID_OK:
			raise api.Cancelado()
		return dialogo.resultado
	finally:
		dialogo.Destroy()


class DialogoToken(comun.DialogoNubes):
	"""Autorizar desde otro equipo: la orden ``rclone authorize`` para copiar y el resultado para pegar."""

	def __init__(self, zc: Any, padre: wx.Window | None, orden: str, ayuda: str = "") -> None:
		super().__init__(zc, padre, _("Autorizar desde otro equipo"))
		explicacion = _("En un equipo con navegador y rclone, ejecute la orden de abajo, autorice en el navegador y pegue aquí "
			"todo lo que rclone escriba al terminar (un bloque de texto o el token en JSON).")
		comun.texto_solo_lectura(zc, self.panel, _("&Instrucciones:"), explicacion + ("\n\n" + ayuda if ayuda else ""), sizer=self.sizer,
			alto=90)
		self.orden = comun.campo(zc, self.panel, _("&Orden que hay que ejecutar:"), wx.TextCtrl, orden, sizer=self.sizer,
			style=wx.TE_READONLY, ayuda=_("Selecciónela y cópiela, o use el botón Copiar la orden."))
		comun.boton(self.panel, _("Co&piar la orden"), _("Copia la orden al portapapeles."),
			lambda: comun.copiar_al_portapapeles(self.orden.GetValue()) and zc.anunciar(_("Orden copiada"), api.RESULTADO),
			sizer=self.sizer)
		self.token = comun.campo(zc, self.panel, _("&Resultado pegado:"), wx.TextCtrl, sizer=self.sizer,
			style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(520, 120)), ayuda=_("Pegue aquí con Control más V lo que escribió rclone."))
		self.botones(wx.OK | wx.CANCEL)
		self.terminar(self.orden)

	def valor(self) -> str:
		return self.token.GetValue().strip()
