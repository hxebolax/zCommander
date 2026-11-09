# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""«Contraseñas guardadas de servidores» (diseño 2.0, 9.5; orden ``red_contrasenas``).

Lista las credenciales de tipo dominio del Administrador de credenciales de
Windows (``CredEnumerate``): las que Windows usa al conectar unidades y
recursos compartidos. Windows no deja leer la contraseña, así que la lista
solo dice el servidor y el usuario. «Olvidar» la borra (``CredDelete``) tras
confirmarlo, con el foco en «No». La lista se rehace al momento.

Letras: S (lista), O (Olvidar) y E (Cerrar).
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Sequence

import wx

from app.services.windows import red
from app.ui import anuncios
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoContrasenas(f_comun.DialogoF):
	"""Servidor y usuario de cada credencial guardada; «Olvidar» la borra de Windows.

	:param olvidar: ``olvidar(credencial)`` borra la credencial en Windows (lanza ``ErrorUnidadRed`` si no puede).
	:param leer: vuelve a leer la lista tras olvidar una.
	"""

	def __init__(self, padre: wx.Window | None, credenciales: Sequence[red.Credencial],
			olvidar: Callable[[red.Credencial], object], leer: Callable[[], list[red.Credencial]]) -> None:
		super().__init__(padre, _("Contraseñas guardadas de servidores"))
		self.credenciales = list(credenciales)
		self._olvidar = olvidar
		self._leer = leer
		self.etiqueta_lista = wx.StaticText(self.panel, label=_("&Servidores con contraseña guardada en Windows:"))
		self.lista = ListaAccesible(self.panel, _("Servidores con contraseña guardada en Windows"),
			columnas=[(_("Servidor"), self.FromDIP(220)), (_("Usuario"), self.FromDIP(220))])
		self.lista.SetMinSize(self.FromDIP(wx.Size(460, 200)))
		self.lista.SetHelpText(_("Las contraseñas que Windows usa al conectar recursos compartidos. Windows no deja verlas; "
			"Olvidar borra la del servidor elegido."))
		self.sizer.Add(self.etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_olvidar = self.boton(_("&Olvidar..."), _("Borra de Windows la contraseña guardada del servidor elegido."),
			self.olvidar, fila)
		self.sizer.Add(fila, 0)
		self.terminar(wx.CLOSE, foco=self.lista, id_escape=wx.ID_CLOSE)
		self.FindWindow(wx.ID_CLOSE).Bind(wx.EVT_BUTTON, lambda _e: self.cerrar(wx.ID_CLOSE))
		self._rellenar(0)

	def _rellenar(self, foco: int) -> None:
		if self.credenciales:
			self.lista.reemplazar_filas([[c.objetivo, c.usuario or _("Sin usuario")] for c in self.credenciales], conservar_foco=False)
			self.lista.enfocar_fila(min(max(foco, 0), len(self.credenciales) - 1), anunciar=False)
		else:
			self.lista.reemplazar_filas([[_("No hay contraseñas de servidores guardadas en Windows"), ""]], conservar_foco=False)
		self.boton_olvidar.Enable(bool(self.credenciales))

	def elegida(self) -> red.Credencial | None:
		fila = self.lista.fila_actual()
		return self.credenciales[fila] if self.credenciales and 0 <= fila < len(self.credenciales) else None

	def olvidar(self) -> None:
		credencial = self.elegida()
		if credencial is None:
			return
		pregunta = _("¿Olvidar la contraseña guardada de {s} (usuario {u})? Windows la volverá a pedir al conectar.").format(
			s=credencial.objetivo, u=credencial.usuario or _("sin usuario"))
		if not f_comun.preguntar(self, pregunta, _("Olvidar la contraseña"), peligroso=True):
			self.lista.SetFocus()
			return
		indice = self.lista.fila_actual()
		try:
			self._olvidar(credencial)
		except red.ErrorUnidadRed as error:
			f_comun.avisar(self, error.mensaje, _("Olvidar la contraseña"))
			self.lista.SetFocus()
			return
		anuncios.anunciar(_("Contraseña de {s} olvidada").format(s=credencial.objetivo), anuncios.RESULTADO)
		try:
			self.credenciales = list(self._leer())
		except red.ErrorUnidadRed:
			log.info("No se pudo volver a leer la lista de credenciales", exc_info=True)
			self.credenciales = [c for c in self.credenciales if c != credencial]
		self._rellenar(indice)
		self.lista.SetFocus()
