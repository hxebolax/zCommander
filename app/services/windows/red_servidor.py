# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sesiones y archivos abiertos por la red en ESTE equipo (diseño 2.0, 9.8; opcional y con elevación).

``NetSessionEnum`` (nivel 10: equipo, usuario, tiempo, inactividad) y
``NetFileEnum`` (nivel 3: ruta, usuario, bloqueos) piden permisos de
administrador. zCommander nunca se eleva solo: si no lo está, la orden lo
explica. Cerrar una sesión (``NetSessionDel``) o un archivo
(``NetFileClose``) puede hacer perder datos a quien lo tiene abierto, así
que la interfaz lo confirma antes. Sin wx.
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass

from app.services.windows import red

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Sesion:
	"""Un equipo conectado a los recursos de este equipo."""

	equipo: str
	usuario: str
	segundos: int
	inactiva_s: int


@dataclass(frozen=True)
class ArchivoAbierto:
	"""Un archivo de este equipo abierto por la red."""

	id: int
	ruta: str
	usuario: str
	bloqueos: int


def _win32net():
	import win32net

	return win32net


def es_elevado() -> bool:
	return red.es_elevado()


def aviso_sin_elevacion() -> str:
	return _("Para ver quién tiene abiertos archivos de este equipo por la red hace falta ejecutar zCommander como administrador "
		"(clic derecho, Ejecutar como administrador). zCommander no se eleva solo.")


def _todas(funcion, *argumentos) -> list[dict]:
	"""Recorre una enumeración de pywin32 con su marca de reanudación."""
	filas: list[dict] = []
	reanudar = 0
	while True:
		datos, _total, reanudar = funcion(*argumentos, reanudar) if reanudar else funcion(*argumentos)
		filas.extend(datos or [])
		if not reanudar:
			return filas


def sesiones() -> list[Sesion]:
	""":raises ErrorUnidadRed: 5 si no se es administrador."""
	try:
		filas = _todas(_win32net().NetSessionEnum, 10, None, None)
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		raise red._error(error) from error
	return sorted(
		(Sesion(str(f.get("client_name") or f.get("cname") or "").lstrip("\\"), str(f.get("user_name") or f.get("username") or ""),
			int(f.get("time") or 0), int(f.get("idle_time") or 0)) for f in filas),
		key=lambda s: (s.equipo.casefold(), s.usuario.casefold()),
	)


def archivos_abiertos() -> list[ArchivoAbierto]:
	""":raises ErrorUnidadRed: 5 si no se es administrador."""
	try:
		filas = _todas(_win32net().NetFileEnum, None, None, None, 3)
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		raise red._error(error) from error
	return sorted(
		(ArchivoAbierto(int(f.get("id") or 0), str(f.get("path_name") or ""), str(f.get("user_name") or ""), int(f.get("num_locks") or 0))
			for f in filas),
		key=lambda a: a.ruta.casefold(),
	)


def cerrar_sesion(sesion: Sesion) -> None:
	try:
		_win32net().NetSessionDel(None, f"\\\\{sesion.equipo}", sesion.usuario or None)
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		raise red._error(error, sesion.equipo) from error
	log.info("Sesión de %s en %s cerrada", sesion.usuario, sesion.equipo)


def cerrar_archivo(archivo: ArchivoAbierto) -> None:
	try:
		_win32net().NetFileClose(None, archivo.id)
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		raise red._error(error, archivo.ruta) from error
	log.info("Archivo abierto por la red cerrado: %s", archivo.ruta)
