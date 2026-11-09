# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Acerca de»: nombre, versión, titular, licencia y datos técnicos (diseño 2.0, 2.5).

No se usa ``wx.adv.AboutBox``: su ventana nativa mezcla etiquetas estáticas
que el lector no siempre recorre y no deja copiar el texto. Aquí va todo en
un campo de solo lectura (con la etiqueta «Información» creada justo antes,
para que el lector lo nombre) y cinco botones:

- «Ver la &licencia»: el texto íntegro de la GPL-3.0 en el visor de ayuda.
- «Componentes de &terceros»: ``LEEME-LICENCIAS.md`` en el visor.
- «&Oferta de fuentes»: ``OFERTA-DE-FUENTES.md`` en el visor.
- «Co&piar la información»: todo el texto al portapapeles (para un correo de soporte).
- «&Cerrar» (también Escape).

Los tres primeros cierran el diálogo y abren el documento en el visor (que no
es modal): así el visor no queda detrás de un diálogo modal ni se cierra con él.
"""

from __future__ import annotations

import builtins
import json
import logging
import platform
import sys

import wx

from app.core import paths
from app.core.version import APP_VERSION, NOMBRE_APLICACION, TITULAR

log = logging.getLogger(__name__)

#: Dónde se publican zCommander y sus fuentes (2.4).
URL_FUENTES = "https://xebolax.synology.me/zCommander/"
#: Documentos de ``data/docs`` que abren los botones (rutas relativas a ``data/docs``).
DOC_LICENCIA = "licencias/zCommander/GPL-3.0.txt"
DOC_TERCEROS = "licencias/LEEME-LICENCIAS.md"
DOC_OFERTA = "licencias/OFERTA-DE-FUENTES.md"
#: Clave del complemento Nubes que dice si montó alguna vez una unidad con WinFsp (12.9; la escribe NU).
CLAVE_WINFSP = "aviso_winfsp_mostrado"
ID_NUBES = "zc.nubes"

ID_LICENCIA = wx.NewIdRef()
ID_TERCEROS = wx.NewIdRef()
ID_OFERTA = wx.NewIdRef()


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def frase_licencia() -> str:
	"""La frase de 2.5 (la comprueba una prueba)."""
	return _("Este programa es software libre: puede redistribuirlo y modificarlo según la Licencia Pública General de GNU, "
		"versión 3 o posterior. Se distribuye sin ninguna garantía.")


def linea_titular() -> str:
	"""«Copyright © 2026 hxebolax y colaboradores. Licencia GPL-3.0 o posterior.» (21.2.1)."""
	return _("Copyright © 2026 {titular}. Licencia GPL-3.0 o posterior.").format(titular=TITULAR)


def nubes_uso_winfsp() -> bool:
	"""Verdadero si el complemento Nubes ha montado alguna vez una unidad con WinFsp.

	Se lee su archivo de configuración directamente (sin activar el complemento):
	«Acerca de» no debe cargar código de complementos.
	"""
	ruta = paths.ruta_config_plugins() / f"{ID_NUBES}.json"
	try:
		datos = json.loads(ruta.read_text(encoding="utf-8"))
	except FileNotFoundError:
		return False
	except (OSError, ValueError):
		log.debug("No se pudo leer %s para el aviso de WinFsp", ruta, exc_info=True)
		return False
	if not isinstance(datos, dict):
		return False
	# La configuración de un complemento guarda sus claves en la sección «ajustes» (config_plugins.SECCION).
	ajustes = datos.get("ajustes")
	return datos.get(CLAVE_WINFSP) is True or (isinstance(ajustes, dict) and ajustes.get(CLAVE_WINFSP) is True)


def aviso_winfsp() -> str:
	"""Aviso que exige la excepción FLOSS de WinFsp (rclone.md 4.8)."""
	return _("Las unidades de nube se montan con WinFsp - Windows File System Proxy, Copyright (C) Bill Zissimopoulos "
		"(https://github.com/winfsp/winfsp), que instala la persona por su cuenta.")


def texto_acerca_de() -> str:
	"""Compone el texto del diálogo (sin wx en la lógica, para poder probarlo)."""
	lineas = [
		f"{NOMBRE_APLICACION} {APP_VERSION}",
		linea_titular(),
		"",
		frase_licencia(),
		_("Código fuente y oferta de fuentes de los componentes: {url}").format(url=URL_FUENTES),
		"",
		_("Versión de Python: {version} ({bits})").format(version=platform.python_version(), bits=platform.architecture()[0]),
		_("Versión de wxPython: {version}").format(version=wx.version()),
		_("Sistema: {sistema}").format(sistema=platform.platform()),
		_("Versión compilada: {valor}").format(valor=_("sí") if paths.CONGELADA else _("no")),
		_("Carpeta de datos: {ruta}").format(ruta=paths.ruta_datos()),
		_("Ejecutable: {ruta}").format(ruta=sys.executable),
	]
	if nubes_uso_winfsp():
		lineas += ["", aviso_winfsp()]
	return "\n".join(lineas)


class DialogoAcercaDe(wx.Dialog):
	"""«Acerca de» accesible: texto de solo lectura y los botones de 2.5."""

	def __init__(self, padre: wx.Window | None) -> None:
		super().__init__(padre, title=_("Acerca de {nombre}").format(nombre=NOMBRE_APLICACION),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.texto = texto_acerca_de()

		# La etiqueta se crea JUSTO ANTES del campo: el lector toma de ella su nombre.
		etiqueta = wx.StaticText(self, label=_("&Información:"))
		self.campo = wx.TextCtrl(self, value=self.texto, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
		self.campo.SetHelpText(_("Nombre, versión, licencia y datos técnicos. Texto de solo lectura: muévase con las flechas."))

		self.boton_licencia = wx.Button(self, ID_LICENCIA, label=_("Ver la &licencia"))
		self.boton_licencia.SetHelpText(_("Abre el texto íntegro de la Licencia Pública General de GNU, versión 3."))
		self.boton_terceros = wx.Button(self, ID_TERCEROS, label=_("Componentes de &terceros"))
		self.boton_terceros.SetHelpText(_("Abre la lista de componentes de terceros con su licencia."))
		self.boton_oferta = wx.Button(self, ID_OFERTA, label=_("&Oferta de fuentes"))
		self.boton_oferta.SetHelpText(_("Explica cómo conseguir el código fuente de zCommander y de sus componentes."))
		self.boton_copiar = wx.Button(self, label=_("Co&piar la información"))
		self.boton_copiar.SetHelpText(_("Copia todo el texto al portapapeles, por ejemplo para un correo de soporte."))
		self.boton_cerrar = wx.Button(self, wx.ID_CANCEL, label=_("&Cerrar"))
		self.SetEscapeId(wx.ID_CANCEL)

		for boton in (self.boton_licencia, self.boton_terceros, self.boton_oferta):
			boton.Bind(wx.EVT_BUTTON, self._al_abrir_documento)
		self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)

		botones = wx.WrapSizer(wx.HORIZONTAL)
		for boton in (self.boton_licencia, self.boton_terceros, self.boton_oferta, self.boton_copiar, self.boton_cerrar):
			botones.Add(boton, 0, wx.RIGHT | wx.BOTTOM, 8)

		principal = wx.BoxSizer(wx.VERTICAL)
		principal.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
		principal.Add(self.campo, 1, wx.EXPAND | wx.ALL, 10)
		principal.Add(botones, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
		self.SetSizer(principal)
		self.SetSize(self.FromDIP(wx.Size(680, 480)))
		self.CentreOnParent()

		self.campo.SetInsertionPoint(0)
		self.campo.SetFocus()

	def _al_abrir_documento(self, evento: wx.CommandEvent) -> None:
		self.EndModal(evento.GetId())

	def _al_copiar(self, _evento: wx.CommandEvent) -> None:
		from app.ui.dialogo_texto import copiar_al_portapapeles, mostrar_mensaje

		if copiar_al_portapapeles(self.texto):
			from app.ui.accesibilidad import voz

			voz.hablar(_("Información copiada al portapapeles"))
		else:
			mostrar_mensaje(self, _("No se pudo abrir el portapapeles. Inténtelo de nuevo."), _("Copiar"), wx.ICON_WARNING)


def abrir_documento_de_licencias(padre: wx.Window | None, respuesta: int, *, mostrar: bool = True):
	"""Abre en el visor de ayuda el documento del botón pulsado y devuelve el visor (None si no era ninguno o falta)."""
	from app.ui import visor_ayuda

	documentos = {
		int(ID_LICENCIA): (DOC_LICENCIA, _("Licencia Pública General de GNU, versión 3"), True),
		int(ID_TERCEROS): (DOC_TERCEROS, _("Componentes de terceros"), False),
		int(ID_OFERTA): (DOC_OFERTA, _("Oferta de fuentes"), False),
	}
	if respuesta not in documentos:
		return None
	nombre, titulo, solo_texto = documentos[respuesta]
	return visor_ayuda.abrir_documento(padre, nombre, titulo, forzar_texto=solo_texto, mostrar=mostrar)


def mostrar_acerca_de(padre: wx.Window | None) -> None:
	"""Abre el diálogo «Acerca de» de forma modal y, si se pidió, el documento de licencias."""
	dialogo = DialogoAcercaDe(padre)
	try:
		respuesta = dialogo.ShowModal()
	finally:
		dialogo.Destroy()
	abrir_documento_de_licencias(padre, respuesta)
