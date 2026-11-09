# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Arrancar zCommander al iniciar sesión en Windows (diseño 2.0, 10.17). Sin wx.

Es la ÚNICA escritura de zCommander en el Registro de Windows y solo por
petición expresa (``general.arrancar_con_windows``): el valor ``zCommander`` en
``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` con
``"<ruta del exe>" --al-iniciar-sesion``. Solo en la versión compilada (desde
código no hay un ``.exe`` estable que arrancar).

Las pruebas pasan otra ``clave`` (una subclave de prueba de HKCU) para no tocar
el inicio real.
"""

from __future__ import annotations

import builtins
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

CLAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOMBRE_VALOR = "zCommander"
ARGUMENTO = "--al-iniciar-sesion"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def disponible() -> bool:
	"""Solo la versión compilada puede arrancar con Windows."""
	return bool(getattr(sys, "frozen", False))


def ejecutable() -> Path:
	return Path(sys.executable).resolve()


def orden(exe: Path | None = None) -> str:
	return f'"{exe or ejecutable()}" {ARGUMENTO}'


def leer(clave: str = CLAVE_RUN) -> str | None:
	"""El valor actual, o ``None`` si no existe."""
	import winreg

	try:
		with winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave, 0, winreg.KEY_READ) as abierta:
			valor, _tipo = winreg.QueryValueEx(abierta, NOMBRE_VALOR)
			return str(valor)
	except FileNotFoundError:
		return None
	except OSError:
		log.warning("No se pudo leer %s\\%s", clave, NOMBRE_VALOR, exc_info=True)
		return None


def activar(exe: Path | None = None, clave: str = CLAVE_RUN) -> None:
	"""Escribe el valor (``OSError`` si Windows no lo permite)."""
	import winreg

	with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, clave, 0, winreg.KEY_SET_VALUE) as abierta:
		winreg.SetValueEx(abierta, NOMBRE_VALOR, 0, winreg.REG_SZ, orden(exe))
	log.info("Arrancar con Windows activado: %s", orden(exe))


def desactivar(clave: str = CLAVE_RUN) -> None:
	"""Borra el valor si existe."""
	import winreg

	try:
		with winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave, 0, winreg.KEY_SET_VALUE) as abierta:
			winreg.DeleteValue(abierta, NOMBRE_VALOR)
		log.info("Arrancar con Windows desactivado")
	except FileNotFoundError:
		return


def ruta_registrada(valor: str) -> Path | None:
	"""La ruta del ``.exe`` del valor de ``Run`` (entre comillas), o ``None``."""
	valor = valor.strip()
	if valor.startswith('"'):
		fin = valor.find('"', 1)
		return Path(valor[1:fin]) if fin > 1 else None
	return Path(valor.split(" ", 1)[0]) if valor else None


def apunta_a_otra_carpeta(exe: Path | None = None, clave: str = CLAVE_RUN) -> bool:
	"""El valor existe y apunta a otro ``.exe`` (la carpeta portable se movió)."""
	valor = leer(clave)
	if valor is None:
		return False
	registrada = ruta_registrada(valor)
	actual = exe or ejecutable()
	return registrada is None or str(registrada).casefold() != str(actual).casefold()


def aplicar(activo: bool, exe: Path | None = None, clave: str = CLAVE_RUN) -> None:
	"""Pone o quita el valor según la preferencia."""
	if activo:
		activar(exe, clave)
	else:
		desactivar(clave)
