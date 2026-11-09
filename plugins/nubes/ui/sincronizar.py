# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sincronizar, comprobar y buscar nombres duplicados (diseño 2.0, 12.6).

- ``DialogoRutas``: origen y destino (carpetas locales o direcciones
  ``nube://``) con las casillas de cada orden.
- ``DialogoCambios``: el resultado de una simulación o de una comprobación como
  lista (Cambio, Archivo) con un resumen de solo lectura; para sincronizar,
  el botón «&Sincronizar» no es el predeterminado: Intro no borra nada.
- ``DialogoDuplicados``: cuenta, carpeta y la acción que se aplicará (siempre
  con simulación antes).
"""

from __future__ import annotations

from typing import Any

import wx

from app.plugins import api

from . import comun

_ = api.traduccion("zc_nubes")[0]

TEXTO_CAMBIO = {"+": _("Se copiará"), "-": _("Se borrará en el destino"), "*": _("Distinto"), "=": _("Igual"), "!": _("Error")}
TEXTO_CAMBIO_COMPROBAR = {"+": _("Solo en el origen"), "-": _("Solo en el destino"), "*": _("Distinto"), "=": _("Igual"),
	"!": _("Error al leer")}


class DialogoRutas(comun.DialogoNubes):
	"""Origen, destino y casillas propias de la orden."""

	def __init__(self, zc: Any, padre: wx.Window | None, titulo: str, origen: str, destino: str, casillas: list[tuple[str, str, str, bool]],
			*, boton_aceptar: str = "&Simular", explicacion: str = "", con_copias: bool = False) -> None:
		super().__init__(zc, padre, titulo)
		if explicacion:
			comun.texto_solo_lectura(zc, self.panel, _("&Qué hace:"), explicacion, sizer=self.sizer, alto=60)
		self.origen = comun.campo(zc, self.panel, _("&Origen:"), wx.TextCtrl, origen, sizer=self.sizer,
			ayuda=_("Carpeta local (C:\\...) o dirección de nube (nube://cuenta/carpeta)."))
		self.destino = comun.campo(zc, self.panel, _("&Destino:"), wx.TextCtrl, destino, sizer=self.sizer,
			ayuda=_("Carpeta local o dirección de nube. Al sincronizar, el destino queda igual que el origen."))
		self.casillas: dict[str, wx.CheckBox] = {}
		for clave, etiqueta, ayuda, valor in casillas:
			self.casillas[clave] = comun.casilla(self.panel, etiqueta, ayuda, valor, sizer=self.sizer)
		self.copias = None
		if con_copias:
			self.copias = comun.campo(zc, self.panel, _("Carpeta de co&pias (opcional):"), wx.TextCtrl, sizer=self.sizer,
				ayuda=_("Si escribe una carpeta del mismo destino, lo que se borre o sobrescriba se guarda allí (BackupDir)."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		aceptar = comun.boton(self.panel, boton_aceptar, _("Sigue con estos datos."), sizer=fila, identificador=wx.ID_OK)
		comun.boton(self.panel, _("&Cancelar"), _("Cierra sin hacer nada."), sizer=fila, identificador=wx.ID_CANCEL)
		aceptar.SetDefault()
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.terminar(self.origen)

	def valor(self, clave: str) -> bool:
		return bool(self.casillas[clave].GetValue()) if clave in self.casillas else False

	def rutas(self) -> tuple[str, str]:
		return self.origen.GetValue().strip(), self.destino.GetValue().strip()


class DialogoCambios(comun.DialogoNubes):
	"""Lista de cambios o de diferencias, con su resumen."""

	def __init__(self, zc: Any, padre: wx.Window | None, titulo: str, resumen: str, filas: list[tuple[str, str]], *,
			boton_accion: str = "") -> None:
		super().__init__(zc, padre, titulo)
		comun.texto_solo_lectura(zc, self.panel, _("&Resumen:"), resumen, sizer=self.sizer, alto=60)
		self.lista = comun.lista(zc, self.panel, _("&Elementos:"), [(_("Cambio"), 200), (_("Archivo"), 420)], sizer=self.sizer,
			ayuda=_("Cada archivo con lo que le pasa o le pasaría."))
		comun.llenar_lista(self.lista, filas or [(_("Ninguno"), _("No hay nada que hacer"))])
		fila = wx.BoxSizer(wx.HORIZONTAL)
		if boton_accion:
			comun.boton(self.panel, boton_accion, _("Hace de verdad lo que muestra la lista."), sizer=fila, identificador=wx.ID_OK)
			cerrar = comun.boton(self.panel, _("&Cancelar"), _("Cierra sin hacer nada."), sizer=fila, identificador=wx.ID_CANCEL)
		else:
			cerrar = comun.boton(self.panel, _("&Cerrar"), _("Cierra la lista."), sizer=fila, identificador=wx.ID_CANCEL)
		cerrar.SetDefault()
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.terminar(self.lista)


class DialogoDuplicados(comun.DialogoNubes):
	"""Cuenta y carpeta donde buscar nombres duplicados, y qué hacer con ellos."""

	MODOS = [("newest", _("Conservar el más nuevo y borrar los demás")), ("oldest", _("Conservar el más antiguo")),
		("largest", _("Conservar el más grande")), ("smallest", _("Conservar el más pequeño")),
		("rename", _("Renombrar todos para que no se repitan")), ("first", _("Conservar el primero de la lista"))]

	def __init__(self, zc: Any, padre: wx.Window | None, cuentas: list[tuple[str, str]], cuenta: str = "", carpeta: str = "/") -> None:
		super().__init__(zc, padre, _("Buscar nombres duplicados"))
		self.cuenta = comun.elegir(zc, self.panel, _("C&uenta:"), cuentas, cuenta, sizer=self.sizer,
			ayuda=_("Cuenta en la que buscar (Drive y Mega permiten dos archivos con el mismo nombre)."))
		self.carpeta = comun.campo(zc, self.panel, _("Ca&rpeta:"), wx.TextCtrl, carpeta, sizer=self.sizer,
			ayuda=_("Carpeta de la cuenta; / es toda la cuenta."))
		self.modo = comun.elegir(zc, self.panel, _("&Qué hacer con los duplicados:"), self.MODOS, "newest", sizer=self.sizer,
			ayuda=_("Antes de hacer nada se muestra una simulación."))
		self.por_contenido = comun.casilla(self.panel, _("&Buscar también por contenido (iguales con otro nombre)"),
			_("Busca archivos con el mismo contenido aunque tengan otro nombre (by-hash)."), sizer=self.sizer)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		listar = comun.boton(self.panel, _("&Listar los duplicados"), _("Busca y muestra los duplicados sin cambiar nada."),
			sizer=fila, identificador=wx.ID_OK)
		comun.boton(self.panel, _("&Cancelar"), _("Cierra sin hacer nada."), sizer=fila, identificador=wx.ID_CANCEL)
		listar.SetDefault()
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.terminar(self.cuenta)


class DialogoInforme(comun.DialogoNubes):
	"""Texto de un informe de rclone (dedupe) con un botón de acción opcional que no es el predeterminado."""

	def __init__(self, zc: Any, padre: wx.Window | None, titulo: str, texto: str, boton_accion: str = "") -> None:
		super().__init__(zc, padre, titulo)
		self.texto = comun.texto_solo_lectura(zc, self.panel, _("&Informe:"), texto or _("Sin resultados."), sizer=self.sizer, alto=240)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		if boton_accion:
			comun.boton(self.panel, boton_accion, _("Sigue con la acción."), sizer=fila, identificador=wx.ID_OK)
		cerrar = comun.boton(self.panel, _("&Cancelar") if boton_accion else _("&Cerrar"), _("Cierra el informe."), sizer=fila,
			identificador=wx.ID_CANCEL)
		cerrar.SetDefault()
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.terminar(self.texto)
