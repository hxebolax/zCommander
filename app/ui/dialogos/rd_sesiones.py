# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""«Sesiones y archivos abiertos por la red» (diseño 2.0, 9.8; orden ``red_sesiones``; pide administrador).

Dos listas: quién está conectado a los recursos compartidos de ESTE equipo
(equipo, usuario, tiempo, inactividad) y qué archivos tiene abiertos (ruta,
usuario, bloqueos). «Cerrar la sesión» y «Cerrar el archivo» cortan a quien
los usa (puede perder lo no guardado): se confirman con el foco en «No».

Letras: S (Sesiones), B (Archivos abiertos), N (Cerrar la sesión), H (Cerrar el archivo), A (Actualizar) y E (Cerrar).
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Sequence

import wx

from app.services import formato
from app.services.windows import red
from app.services.windows.red_servidor import ArchivoAbierto, Sesion
from app.ui import anuncios
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoSesiones(f_comun.DialogoF):
	"""Sesiones y archivos abiertos, con cerrar y actualizar.

	:param leer: ``leer() -> (sesiones, archivos)`` (lanza ``ErrorUnidadRed`` si no puede).
	:param cerrar_sesion: corta una sesión (lanza ``ErrorUnidadRed``).
	:param cerrar_archivo: cierra un archivo (lanza ``ErrorUnidadRed``).
	"""

	def __init__(self, padre: wx.Window | None, sesiones: Sequence[Sesion], archivos: Sequence[ArchivoAbierto],
			leer: Callable[[], tuple[list[Sesion], list[ArchivoAbierto]]],
			cerrar_sesion: Callable[[Sesion], object], cerrar_archivo: Callable[[ArchivoAbierto], object]) -> None:
		super().__init__(padre, _("Sesiones y archivos abiertos por la red"))
		self.sesiones, self.archivos = list(sesiones), list(archivos)
		self._leer, self._cerrar_sesion, self._cerrar_archivo = leer, cerrar_sesion, cerrar_archivo
		self.etiqueta_sesiones = wx.StaticText(self.panel, label=_("&Sesiones:"))
		self.lista_sesiones = ListaAccesible(self.panel, _("Sesiones"), columnas=[
			(_("Equipo"), self.FromDIP(160)), (_("Usuario"), self.FromDIP(140)), (_("Tiempo"), self.FromDIP(100)),
			(_("Inactividad"), self.FromDIP(100))])
		self.lista_sesiones.SetMinSize(self.FromDIP(wx.Size(520, 140)))
		self.lista_sesiones.SetHelpText(_("Equipos conectados ahora a los recursos compartidos de este equipo."))
		self.sizer.Add(self.etiqueta_sesiones, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista_sesiones, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		self.etiqueta_archivos = wx.StaticText(self.panel, label=_("Archivos a&biertos:"))
		self.lista_archivos = ListaAccesible(self.panel, _("Archivos abiertos"), columnas=[
			(_("Ruta"), self.FromDIP(320)), (_("Usuario"), self.FromDIP(140)), (_("Bloqueos"), self.FromDIP(80))])
		self.lista_archivos.SetMinSize(self.FromDIP(wx.Size(520, 140)))
		self.lista_archivos.SetHelpText(_("Archivos de este equipo que otros tienen abiertos por la red."))
		self.sizer.Add(self.etiqueta_archivos, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista_archivos, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_sesion = self.boton(_("Cerrar la sesió&n..."), _("Desconecta el equipo elegido; puede perder lo que no haya guardado."),
			self.cerrar_sesion, fila)
		self.boton_archivo = self.boton(_("Cerrar el arc&hivo..."), _("Cierra el archivo elegido a quien lo tiene abierto."),
			self.cerrar_archivo, fila)
		self.boton(_("&Actualizar"), _("Vuelve a leer las sesiones y los archivos abiertos."), self.actualizar, fila)
		self.sizer.Add(fila, 0)
		self.terminar(wx.CLOSE, foco=self.lista_sesiones, id_escape=wx.ID_CLOSE)
		self.FindWindow(wx.ID_CLOSE).Bind(wx.EVT_BUTTON, lambda _e: self.cerrar(wx.ID_CLOSE))
		self._rellenar()

	def _rellenar(self) -> None:
		filas_sesiones = [[s.equipo, s.usuario, formato.duracion(s.segundos), formato.duracion(s.inactiva_s)] for s in self.sesiones]
		filas_archivos = [[a.ruta, a.usuario, str(a.bloqueos)] for a in self.archivos]
		self.lista_sesiones.reemplazar_filas(filas_sesiones or [[_("No hay sesiones"), "", "", ""]], conservar_foco=True)
		self.lista_archivos.reemplazar_filas(filas_archivos or [[_("No hay archivos abiertos"), "", ""]], conservar_foco=True)
		self.boton_sesion.Enable(bool(self.sesiones))
		self.boton_archivo.Enable(bool(self.archivos))

	def actualizar(self) -> None:
		try:
			self.sesiones, self.archivos = (list(x) for x in self._leer())
		except red.ErrorUnidadRed as error:
			f_comun.avisar(self, error.mensaje, self.titulo)
			return
		self._rellenar()
		anuncios.anunciar(_("{s} sesiones, {a} archivos abiertos").format(s=len(self.sesiones), a=len(self.archivos)), anuncios.RESULTADO)

	def cerrar_sesion(self) -> None:
		fila = self.lista_sesiones.fila_actual()
		if not self.sesiones or not 0 <= fila < len(self.sesiones):
			return
		sesion = self.sesiones[fila]
		pregunta = _("¿Cerrar la sesión de {u} desde {e}? Puede perder lo que tenga sin guardar en este equipo.").format(
			u=sesion.usuario or _("sin usuario"), e=sesion.equipo)
		if f_comun.preguntar(self, pregunta, _("Cerrar la sesión"), peligroso=True):
			self._hacer(lambda: self._cerrar_sesion(sesion), _("Sesión de {e} cerrada").format(e=sesion.equipo))
		self.lista_sesiones.SetFocus()

	def cerrar_archivo(self) -> None:
		fila = self.lista_archivos.fila_actual()
		if not self.archivos or not 0 <= fila < len(self.archivos):
			return
		archivo = self.archivos[fila]
		pregunta = _("¿Cerrar {r} a {u}? Puede perder lo que tenga sin guardar.").format(r=archivo.ruta, u=archivo.usuario or _("quien lo usa"))
		if f_comun.preguntar(self, pregunta, _("Cerrar el archivo"), peligroso=True):
			self._hacer(lambda: self._cerrar_archivo(archivo), _("Archivo cerrado: {r}").format(r=archivo.ruta))
		self.lista_archivos.SetFocus()

	def _hacer(self, accion: Callable[[], object], hecho: str) -> None:
		try:
			accion()
		except red.ErrorUnidadRed as error:
			f_comun.avisar(self, error.mensaje, self.titulo)
			return
		anuncios.anunciar(hecho, anuncios.RESULTADO)
		self.actualizar()
