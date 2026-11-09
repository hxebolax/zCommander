# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ayuda: manual, teclas, novedades, ayuda del control, información para soporte, carpetas de datos."""

from __future__ import annotations

import builtins
import logging
import os
import platform
import sys

import wx

from app.core import paths
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _documento(ctx, funcion: str, nombre: str, titulo: str) -> None:
	"""Abre un documento en el visor de ayuda accesible (con la lista de secciones).

	Si el visor falla (por ejemplo, sin el motor HTML), se muestra el texto en un
	cuadro de solo lectura, para que la ayuda nunca deje de estar disponible.
	"""
	try:
		from app.ui import visor_ayuda

		getattr(visor_ayuda, funcion)(ctx.ventana)
		return
	except Exception:  # noqa: BLE001 - si el visor de ayuda falla, se usa el texto simple
		log.exception("Falló el visor de ayuda al abrir %s", nombre)
	from app.ui.dialogo_texto import mostrar_documento

	mostrar_documento(ctx.ventana, nombre, titulo)


def manual(ctx) -> None:
	_documento(ctx, "abrir_manual", "manual", _("Manual de usuario"))


def lista_teclas(ctx) -> None:
	_documento(ctx, "abrir_teclas", "teclas", _("Lista de teclas"))


def novedades(ctx) -> None:
	_documento(ctx, "abrir_novedades", "changelog", _("Novedades"))


def ayuda_contextual(ctx) -> None:
	from app.ui.accesibilidad import ayuda

	ayuda.describir_control_enfocado(ctx.ventana)


def info_soporte(ctx) -> None:
	from app.core.version import APP_VERSION, NOMBRE_APLICACION
	from app.ui.dialogo_texto import copiar_al_portapapeles

	lineas = [
		f"{NOMBRE_APLICACION} {APP_VERSION}",
		f"Windows {platform.version()} ({platform.machine()})",
		f"Python {sys.version.split()[0]}, wxPython {wx.version()}",
		f"Datos: {paths.ruta_datos()}",
		f"Perfil: {ctx.ventana.perfil_actual()}",
		"",
	]
	# 2.0 (14.9): complementos, componentes y paquete de sonidos; cada bloque aporta sus líneas.
	from app.plugins import gestor
	from app.services.componentes import estado as estado_componentes
	from app.services.sonidos import paquetes

	for titulo, origen in (("Complementos", gestor.lineas_soporte), ("Componentes", estado_componentes.lineas_soporte),
			("Sonidos", paquetes.lineas_soporte)):
		try:
			extra = origen()
		except Exception:  # noqa: BLE001 - una parte que falla no impide copiar el resto
			log.exception("No se pudieron obtener las líneas de soporte de %s", titulo)
			extra = []
		if titulo == "Sonidos":
			extra = [f"Paquete: {ctx.config.obtener('sonidos.paquete')}", *extra]
		if extra:
			lineas += [f"{titulo}:", *(f"  {linea}" for linea in extra), ""]
	registros = sorted(paths.ruta_registros().glob("*.log"), key=os.path.getmtime)
	if registros:
		with open(registros[-1], encoding="utf-8", errors="replace") as archivo:
			lineas += archivo.readlines()[-50:]
	if copiar_al_portapapeles("\n".join(x.rstrip("\n") for x in lineas)):
		anuncios.anunciar(_("Información para soporte copiada al portapapeles"), anuncios.RESULTADO)


def acerca_de(ctx) -> None:
	from app.ui.acerca_de import mostrar_acerca_de

	mostrar_acerca_de(ctx.ventana)


def _abrir_carpeta(carpeta) -> None:
	try:
		os.startfile(carpeta)  # noqa: S606 - carpeta propia de la aplicación
	except OSError:
		log.exception("No se pudo abrir %s", carpeta)


def carpeta_datos(ctx) -> None:
	_abrir_carpeta(paths.ruta_datos())


def carpeta_registros(ctx) -> None:
	_abrir_carpeta(paths.ruta_registros())
