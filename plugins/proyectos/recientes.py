# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Carpetas de la lista de elementos recientes de Windows (diseño 2.0, 11.15). Solo en un hilo.

Windows guarda un acceso directo por cada archivo o carpeta abiertos en
``%APPDATA%\\Microsoft\\Windows\\Recent``. Se resuelve cada ``.lnk`` con
``IShellLink`` (pywin32) y se toma la carpeta: la del propio destino si es una
carpeta, o la que contiene el archivo. Solo se leen; nunca se cambian.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("zcplugins.zc.proyectos")


def carpeta_recientes() -> Path | None:
	appdata = os.environ.get("APPDATA")
	return Path(appdata) / "Microsoft" / "Windows" / "Recent" if appdata else None


def carpetas_recientes(maximo: int = 200, cancelacion=None, carpeta: Path | None = None) -> list[str]:
	"""Carpetas de los elementos recientes, de la más reciente a la más antigua, sin repetir."""
	carpeta = carpeta or carpeta_recientes()
	if carpeta is None or not carpeta.is_dir():
		return []
	try:
		import pythoncom
		from win32com.shell import shell
	except ImportError:
		log.debug("Sin pywin32 no se leen los elementos recientes de Windows")
		return []
	try:
		accesos = sorted(carpeta.glob("*.lnk"), key=lambda p: p.stat().st_mtime, reverse=True)
	except OSError:
		log.debug("No se pudo leer %s", carpeta, exc_info=True)
		return []
	pythoncom.CoInitialize()
	resultado: list[str] = []
	vistas: set[str] = set()
	try:
		for acceso in accesos:
			token = getattr(cancelacion, "token", cancelacion)
			if token is not None and token.is_set():
				break
			try:
				enlace = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
				enlace.QueryInterface(pythoncom.IID_IPersistFile).Load(str(acceso), 0)
				destino = enlace.GetPath(0)[0]
			except Exception:  # noqa: BLE001 - un acceso roto se salta
				log.debug("Acceso reciente ilegible: %s", acceso, exc_info=True)
				continue
			if not destino:
				continue
			carpeta_destino = destino if os.path.isdir(destino) else os.path.dirname(destino)
			clave = carpeta_destino.casefold()
			if carpeta_destino and clave not in vistas and os.path.isdir(carpeta_destino):
				vistas.add(clave)
				resultado.append(carpeta_destino)
				if len(resultado) >= maximo:
					break
	finally:
		pythoncom.CoUninitialize()
	return resultado
