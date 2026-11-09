# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Quién tiene abierto un archivo, con el Restart Manager de Windows (diseño 2.0, 11.9). Sin wx.

Por qué el Restart Manager (``rstrtmgr.dll``) y no recorrer los identificadores
de todos los procesos: es la API documentada que usa el propio Windows para
decir «el archivo está abierto en X», no necesita permisos de administrador
para los programas de la persona y sabe cerrar esos programas de forma
ordenada (``RmShutdown``), como hace un instalador.

Reglas de seguridad de este módulo (las comprueba ``se_puede_cerrar``):

- Nunca se cierra un servicio, un proceso crítico, el Explorador, un proceso de
  la sesión 0 ni el propio zCommander.
- Si alguno de los que usan el archivo no se puede cerrar, no se cierra
  ninguno: ``RmShutdown`` actúa sobre todos los que usan los recursos
  registrados a la vez.
"""

from __future__ import annotations

import ctypes
import logging
import os
from collections.abc import Sequence
from ctypes import wintypes
from dataclasses import dataclass

from app.plugins import api

from . import sistema

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_procesos")

# Tipos de aplicación del Restart Manager (RM_APP_TYPE).
RM_DESCONOCIDA = 0
RM_VENTANA = 1
RM_OTRA_VENTANA = 2
RM_SERVICIO = 3
RM_EXPLORADOR = 4
RM_CONSOLA = 5
RM_CRITICA = 1000

RM_FORZAR = 0x1
ERROR_MORE_DATA = 234
ERROR_FAIL_SHUTDOWN = 351
CCH_RM_SESSION_KEY = 33
#: Tope de archivos que se registran por consulta (una carpeta enorme no bloquea el Restart Manager).
MAX_ARCHIVOS = 2000


class FILETIME(ctypes.Structure):
	_fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class RM_UNIQUE_PROCESS(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [("dwProcessId", wintypes.DWORD), ("ProcessStartTime", FILETIME)]


class RM_PROCESS_INFO(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [
		("Process", RM_UNIQUE_PROCESS),
		("strAppName", wintypes.WCHAR * 256),
		("strServiceShortName", wintypes.WCHAR * 64),
		("ApplicationType", ctypes.c_int),
		("AppStatus", wintypes.ULONG),
		("TSSessionId", wintypes.DWORD),
		("bRestartable", wintypes.BOOL),
	]


class ErrorUso(api.ErrorArchivos):
	"""El Restart Manager no pudo responder (con el mensaje para la persona)."""


@dataclass(frozen=True)
class ProcesoUso:
	"""Un proceso que tiene abierto alguno de los archivos consultados."""

	pid: int
	nombre: str
	servicio: str = ""
	tipo: int = RM_DESCONOCIDA
	sesion: int = -1

	@property
	def descripcion(self) -> str:
		"""«Microsoft Word (PID 1234)» o «Servicio de cola de impresión, servicio Spooler (PID 99)»."""
		if self.servicio:
			return _("{n}, servicio {s} (PID {p})").format(n=self.nombre, s=self.servicio, p=self.pid)
		return _("{n} (PID {p})").format(n=self.nombre, p=self.pid)


def _api():
	rm = ctypes.WinDLL("rstrtmgr", use_last_error=True)
	rm.RmStartSession.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.LPWSTR]
	rm.RmStartSession.restype = wintypes.DWORD
	rm.RmRegisterResources.argtypes = [wintypes.DWORD, wintypes.UINT, ctypes.POINTER(wintypes.LPCWSTR), wintypes.UINT,
		ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p]
	rm.RmRegisterResources.restype = wintypes.DWORD
	rm.RmGetList.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT),
		ctypes.POINTER(RM_PROCESS_INFO), ctypes.POINTER(wintypes.DWORD)]
	rm.RmGetList.restype = wintypes.DWORD
	rm.RmShutdown.argtypes = [wintypes.DWORD, wintypes.ULONG, ctypes.c_void_p]
	rm.RmShutdown.restype = wintypes.DWORD
	rm.RmEndSession.argtypes = [wintypes.DWORD]
	rm.RmEndSession.restype = wintypes.DWORD
	return rm


def _mensaje_error(codigo: int) -> str:
	return ctypes.FormatError(codigo).strip() if codigo else ""


class _Sesion:
	"""Sesión del Restart Manager con los archivos registrados; se cierra siempre al salir."""

	def __init__(self, rutas: Sequence[str]) -> None:
		self._rm = _api()
		self._rutas = [str(r) for r in rutas][:MAX_ARCHIVOS]
		self._asa = wintypes.DWORD(0)

	def __enter__(self) -> _Sesion:
		clave = ctypes.create_unicode_buffer(CCH_RM_SESSION_KEY + 1)
		codigo = self._rm.RmStartSession(ctypes.byref(self._asa), 0, clave)
		if codigo:
			raise ErrorUso(_("Windows no pudo consultar quién usa el archivo: {e}").format(e=_mensaje_error(codigo)))
		matriz = (wintypes.LPCWSTR * len(self._rutas))(*self._rutas)
		codigo = self._rm.RmRegisterResources(self._asa, len(self._rutas), matriz, 0, None, 0, None)
		if codigo:
			self._rm.RmEndSession(self._asa)
			raise ErrorUso(_("Windows no pudo consultar quién usa el archivo: {e}").format(e=_mensaje_error(codigo)))
		return self

	def __exit__(self, *_exc: object) -> None:
		self._rm.RmEndSession(self._asa)

	def lista(self) -> list[ProcesoUso]:
		necesarios = wintypes.UINT(0)
		cuantos = wintypes.UINT(0)
		motivos = wintypes.DWORD(0)
		for _intento in range(5):
			matriz = (RM_PROCESS_INFO * max(1, necesarios.value))()
			cuantos.value = len(matriz)
			codigo = self._rm.RmGetList(self._asa, ctypes.byref(necesarios), ctypes.byref(cuantos), matriz, ctypes.byref(motivos))
			if codigo == ERROR_MORE_DATA:
				continue
			if codigo:
				raise ErrorUso(_("Windows no pudo decir quién usa el archivo: {e}").format(e=_mensaje_error(codigo)))
			resultado = []
			for info in matriz[: cuantos.value]:
				pid = int(info.Process.dwProcessId)
				nombre = info.strAppName or sistema.nombre_de(pid) or _("Programa sin nombre")
				resultado.append(ProcesoUso(pid, nombre, info.strServiceShortName, int(info.ApplicationType), int(info.TSSessionId)))
			return resultado
		raise ErrorUso(_("La lista de programas que usan el archivo cambia demasiado deprisa; inténtelo de nuevo"))

	def cerrar(self, forzar: bool) -> int:
		# Sin RmShutdownOnlyRegistered (0x10): ese indicador exige que TODOS los programas se hayan
		# registrado para reiniciarse con RegisterApplicationRestart, y casi ninguno lo hace.
		return int(self._rm.RmShutdown(self._asa, RM_FORZAR if forzar else 0, None))


def archivos_de(rutas: Sequence[str]) -> list[str]:
	"""Los archivos que hay que registrar: los de las rutas y, en carpetas, los de dentro (hasta ``MAX_ARCHIVOS``)."""
	resultado: list[str] = []
	for ruta in rutas:
		if os.path.isdir(ruta):
			for carpeta, _subcarpetas, archivos in os.walk(ruta):
				resultado.extend(os.path.join(carpeta, a) for a in archivos)
				if len(resultado) >= MAX_ARCHIVOS:
					return resultado[:MAX_ARCHIVOS]
		else:
			resultado.append(ruta)
	return resultado[:MAX_ARCHIVOS]


def quien_usa(rutas: Sequence[str]) -> list[ProcesoUso]:
	"""Procesos que tienen abierto alguno de ``rutas`` (archivos o carpetas, locales) [trabajo]."""
	archivos = archivos_de(rutas)
	if not archivos:
		return []
	with _Sesion(archivos) as sesion:
		return sesion.lista()


def motivo_para_no_cerrar(proceso: ProcesoUso) -> str:
	"""Por qué no se puede cerrar ese proceso desde zCommander, o ``""`` si se puede."""
	if proceso.pid == os.getpid():
		return _("es el propio zCommander")
	if proceso.tipo == RM_SERVICIO or proceso.servicio:
		return _("es un servicio de Windows")
	if proceso.tipo == RM_CRITICA:
		return _("es un proceso crítico del sistema")
	if proceso.tipo == RM_EXPLORADOR:
		return _("es el Explorador de Windows; cierre su ventana")
	if proceso.sesion == 0 or sistema.es_del_sistema_pid(proceso.pid):
		return _("es un proceso del sistema")
	return ""


def se_puede_cerrar(proceso: ProcesoUso) -> bool:
	return not motivo_para_no_cerrar(proceso)


def cerrar(rutas: Sequence[str], forzar: bool = False) -> list[ProcesoUso]:
	"""Cierra los programas que usan ``rutas`` y devuelve los que lo siguen usando [trabajo].

	Sin ``forzar``, el Restart Manager les pide que se cierren (como al apagar el
	equipo: pueden preguntar si se guarda); con ``forzar``, los termina.

	:raises ErrorUso: si alguno no se puede cerrar (``motivo_para_no_cerrar``); entonces no se cierra ninguno.
	"""
	archivos = archivos_de(rutas)
	if not archivos:
		return []
	with _Sesion(archivos) as sesion:
		usuarios = sesion.lista()
		for proceso in usuarios:
			motivo = motivo_para_no_cerrar(proceso)
			if motivo:
				raise ErrorUso(_("No se puede cerrar {p}: {m}").format(p=proceso.descripcion, m=motivo))
		if not usuarios:
			return []
		codigo = sesion.cerrar(forzar)
		if codigo and codigo != ERROR_FAIL_SHUTDOWN:
			raise ErrorUso(_("Windows no pudo cerrar el programa: {e}").format(e=_mensaje_error(codigo)))
		log.info("Restart Manager cerró %s (forzar=%s, código %d)", [p.pid for p in usuarios], forzar, codigo)
	return quien_usa(rutas)


def describir(procesos: Sequence[ProcesoUso]) -> str:
	"""Frase para anunciar: «Lo usa Bloc de notas (PID 12)» o «Lo usan: A (PID 1), B (PID 2)»."""
	if not procesos:
		return _("Ningún programa tiene abierto el archivo")
	if len(procesos) == 1:
		return _("Lo usa {p}").format(p=procesos[0].descripcion)
	return _("Lo usan {n} programas: {l}").format(n=len(procesos), l="; ".join(p.descripcion for p in procesos))
