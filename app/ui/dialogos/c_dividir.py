# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de Dividir archivo y Unir archivos (sección 8.19).

Dividir: tamaño de cada parte (1,44 MB, 100 MB, 650 MB, 700 MB, 4095 MB,
4,7 GB o personalizado con su unidad) y carpeta de destino. El campo
personalizado y su unidad solo se activan con «Personalizado»; el tamaño se
valida al aceptar (no se usa ``wx.SpinCtrlDouble``: NVDA no lee su etiqueta).

Unir: archivo de destino (propuesto con el nombre original del ``.crc``).
"""

from __future__ import annotations

import builtins
import logging
import os

import wx

from app.services import dividir as servicio
from app.services import formato
from app.services.vfs import rutas
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos.c_comprimir import _campo_resumen, _cuadro, terminar

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoDividir(wx.Dialog):
	"""Tamaño de las partes y carpeta de destino. No lanza la operación.

	:param tamano: tamaño del archivo (para decir cuántas partes salen).
	"""

	def __init__(self, padre: wx.Window | None, resumen: str, carpeta: str, tamano: int = -1) -> None:
		super().__init__(padre, title=_("Dividir archivo"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=_("Dividir archivo"))
		self._tamano = tamano
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.texto_resumen = _campo_resumen(panel, sizer, resumen, _("Archivo que se divide."))
		opciones = [t for t, _b in servicio.TAMANOS_PREDEFINIDOS] + [_("Personalizado")]
		_etiqueta, self.lista_tamano = crear_campo(panel, _("&Tamaño de cada parte:"), wx.Choice, choices=opciones,
			ayuda=_("1,44 MB cabe en un disquete; 650 y 700 MB, en un CD; 4095 MB es el máximo de FAT32; 4,7 GB, un DVD."), sizer=sizer)
		self.lista_tamano.SetSelection(1)
		_etiqueta, self.campo_personalizado = crear_campo(panel, _("Tamaño &personalizado:"), wx.TextCtrl, value="10",
			ayuda=_("Número con decimales si hace falta (2,5). Se usa con «Personalizado»."), sizer=sizer)
		_etiqueta, self.lista_unidad = crear_campo(panel, _("&Unidad:"), wx.Choice, choices=[u for u, _b in servicio.UNIDADES],
			ayuda=_("Unidad del tamaño personalizado."), sizer=sizer)
		self.lista_unidad.SetSelection(1)
		_etiqueta, self.campo_carpeta = crear_campo(panel, _("Carpeta de &destino:"), wx.TextCtrl, value=carpeta,
			ayuda=_("Donde se crean las partes .001, .002... y el archivo .crc."), sizer=sizer)

		self.boton_aceptar = wx.Button(panel, wx.ID_OK, label=_("Di&vidir"))
		self.boton_aceptar.SetHelpText(_("Divide el archivo (Intro)."))
		self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, label=_("&Cancelar"))
		self.boton_aceptar.SetDefault()
		_cuadro(self, panel, sizer, [self.boton_aceptar, self.boton_cancelar])

		self.lista_tamano.Bind(wx.EVT_CHOICE, lambda _e: self._actualizar())
		self.boton_aceptar.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		self._actualizar()
		preparar_dialogo(self, foco_inicial=self.lista_tamano)
		self.CentreOnParent()

	def es_personalizado(self) -> bool:
		return self.lista_tamano.GetSelection() >= len(servicio.TAMANOS_PREDEFINIDOS)

	def _actualizar(self) -> None:
		personalizado = self.es_personalizado()
		self.campo_personalizado.Enable(personalizado)
		self.lista_unidad.Enable(personalizado)

	def tamano_parte(self) -> int | None:
		if not self.es_personalizado():
			return servicio.TAMANOS_PREDEFINIDOS[max(0, self.lista_tamano.GetSelection())][1]
		unidad = servicio.UNIDADES[max(0, self.lista_unidad.GetSelection())][1]
		return servicio.leer_tamano(self.campo_personalizado.GetValue(), unidad)

	def carpeta(self) -> str:
		return self.campo_carpeta.GetValue().strip().strip('"')

	def problema(self) -> str | None:
		tamano = self.tamano_parte()
		if tamano is None:
			return _("Escriba un tamaño de parte mayor que cero.")
		if not self.carpeta():
			return _("Escriba la carpeta de destino.")
		if self._tamano >= 0 and servicio.numero_partes(self._tamano, tamano) > 9999:
			return _("Saldrían más de 9999 partes: elija un tamaño mayor.")
		return None

	def aceptar(self) -> bool:
		problema = self.problema()
		if problema:
			dialogos.mostrar_error(self, problema, self.GetTitle())
			(self.campo_personalizado if self.es_personalizado() else self.campo_carpeta).SetFocus()
			return False
		terminar(self, wx.ID_OK)
		return True

	def describir(self) -> str:
		"""«3 partes de 1 MB» para anunciar al lanzar."""
		tamano = self.tamano_parte() or 1
		partes = servicio.numero_partes(max(0, self._tamano), tamano)
		return _("{p} de {t}").format(p=formato.plural(partes, _("{n} parte"), _("{n} partes")), t=formato.tamano_legible(tamano))


class DialogoUnir(wx.Dialog):
	"""Archivo de destino al unir las partes. No lanza la operación."""

	def __init__(self, padre: wx.Window | None, resumen: str, destino: str) -> None:
		super().__init__(padre, title=_("Unir archivos"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=_("Unir archivos"))
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.texto_resumen = _campo_resumen(panel, sizer, resumen, _("Partes que se van a unir."))
		_etiqueta, self.campo_destino = crear_campo(panel, _("&Archivo de destino:"), wx.TextCtrl, value=destino,
			ayuda=_("Ruta completa del archivo que se crea al unir las partes."), sizer=sizer)
		self.boton_aceptar = wx.Button(panel, wx.ID_OK, label=_("&Unir"))
		self.boton_aceptar.SetHelpText(_("Une las partes (Intro)."))
		self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, label=_("&Cancelar"))
		self.boton_aceptar.SetDefault()
		_cuadro(self, panel, sizer, [self.boton_aceptar, self.boton_cancelar])
		self.boton_aceptar.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		preparar_dialogo(self, foco_inicial=self.campo_destino)
		self.CentreOnParent()

	def destino(self) -> str:
		return self.campo_destino.GetValue().strip().strip('"')

	def problema(self) -> str | None:
		destino = self.destino()
		if not destino:
			return _("Escriba el archivo de destino.")
		return rutas.problema_en_nombre(os.path.basename(destino))

	def aceptar(self) -> bool:
		problema = self.problema()
		if problema:
			dialogos.mostrar_error(self, problema, self.GetTitle())
			self.campo_destino.SetFocus()
			return False
		terminar(self, wx.ID_OK)
		return True
