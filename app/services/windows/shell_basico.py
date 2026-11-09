# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Abrir con el programa asociado, abrir en el Explorador y lanzar programas, sin bloquear la interfaz.

``os.startfile`` y ``ShellExecuteEx`` pueden tardar segundos con rutas de red
o con programas que tardan en arrancar: se llaman en un hilo de trabajo con
COM iniciado. Los errores se devuelven por ``al_error`` (en ese hilo).
"""

from __future__ import annotations

import builtins
import logging
import os
import subprocess
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

EJECUTABLES = {"exe", "bat", "cmd", "com", "msi", "lnk", "ps1", "vbs", "js", "wsf", "scr"}
SIEMPRE_CONFIRMAR = {"ps1", "vbs", "js", "wsf", "scr"}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def es_ejecutable(nombre: str) -> bool:
	return nombre.rsplit(".", 1)[-1].lower() in EJECUTABLES if "." in nombre else False


def exige_confirmacion(nombre: str, confirmar_ejecutar: bool) -> bool:
	extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
	return extension in SIEMPRE_CONFIRMAR or (confirmar_ejecutar and extension in EJECUTABLES)


def _en_hilo(funcion: Callable[[], None], al_error: Callable[[BaseException], None] | None) -> None:
	def trabajo() -> None:
		try:
			import pythoncom

			pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
		except Exception:  # noqa: BLE001 - sin pywin32 también funciona os.startfile
			log.debug("Sin CoInitializeEx", exc_info=True)
		try:
			funcion()
		except Exception as error:  # noqa: BLE001 - se informa a quien llama
			log.warning("No se pudo abrir: %s", error, exc_info=True)
			if al_error is not None:
				al_error(error)

	threading.Thread(target=trabajo, name="abrir-shell", daemon=True).start()


def abrir(ruta: str, al_error: Callable[[BaseException], None] | None = None, carpeta: str | None = None) -> None:
	"""Abre ``ruta`` con su programa (o la ejecuta) en su carpeta."""
	def accion() -> None:
		if carpeta:
			os.startfile(ruta, cwd=carpeta)  # noqa: S606 - archivo elegido por la persona
		else:
			os.startfile(ruta)  # noqa: S606

	_en_hilo(accion, al_error)


def explorador(carpeta: str, seleccionar: str | None = None) -> None:
	"""Abre la carpeta en el Explorador (con el elemento seleccionado si se da)."""
	if seleccionar:
		subprocess.Popen(["explorer.exe", f"/select,{seleccionar}"])  # noqa: S603, S607
	else:
		subprocess.Popen(["explorer.exe", carpeta])  # noqa: S603, S607


def lanzar(linea: str, carpeta: str | None = None, al_error: Callable[[BaseException], None] | None = None) -> None:
	"""Lanza un programa externo (visor o editor) con una línea ya entrecomillada, sin ``cmd``."""
	def accion() -> None:
		subprocess.Popen(linea, cwd=carpeta or None)  # noqa: S603 - programa configurado por la persona

	_en_hilo(accion, al_error)
