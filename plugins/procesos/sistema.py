# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lista de procesos con memoria, CPU, usuario y ruta (diseño 2.0, 11.9). Sin wx y sin psutil.

Por qué así:

- La lista de procesos sale de ``CreateToolhelp32Snapshot`` (da el nombre de
  todos, también de los protegidos que no se pueden abrir) y el resto de
  datos de ``OpenProcess`` con ``PROCESS_QUERY_LIMITED_INFORMATION``, el
  permiso mínimo que Windows concede sobre los procesos de la persona.
- La CPU se calcula como la diferencia del tiempo de CPU (núcleo y usuario)
  entre dos lecturas, repartida entre los procesadores: lo mismo que enseña el
  Administrador de tareas y sin contadores de rendimiento.
- «Del sistema» es conservador: lo que no se puede abrir, lo de la sesión 0,
  lo de las cuentas de servicio y una lista de procesos críticos. Esos nunca
  se terminan desde zCommander.
"""

from __future__ import annotations

import ctypes
import logging
import os
import time
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import dataclass

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_procesos")

PROCESS_TERMINATE = 0x0001
PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
TOKEN_QUERY = 0x0008

#: Procesos que nunca se terminan desde zCommander aunque se puedan abrir.
CRITICOS = frozenset({
	"system", "idle", "system idle process", "registry", "memory compression", "secure system", "smss.exe", "csrss.exe",
	"wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe", "svchost.exe", "dwm.exe", "fontdrvhost.exe",
	"sihost.exe", "ctfmon.exe", "audiodg.exe", "spoolsv.exe", "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe",
})
#: Cuentas de servicio: sus procesos son del sistema.
CUENTAS_SISTEMA = frozenset({"system", "local service", "network service", "servicio local", "servicio de red"})

#: Clases de prioridad que se ofrecen (sin «Tiempo real», que puede dejar el equipo sin responder).
PRIORIDADES: tuple[tuple[int, str], ...] = (
	(0x00000040, "Baja"),
	(0x00004000, "Por debajo de lo normal"),
	(0x00000020, "Normal"),
	(0x00008000, "Por encima de lo normal"),
	(0x00000080, "Alta"),
)


class PROCESSENTRY32W(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [
		("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
		("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
		("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
		("szExeFile", wintypes.WCHAR * 260),
	]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [
		("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
		("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
		("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
		("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
	]


class _FILETIME(ctypes.Structure):
	_fields_ = [("bajo", wintypes.DWORD), ("alto", wintypes.DWORD)]

	@property
	def valor(self) -> int:
		return (self.alto << 32) | self.bajo


def _kernel32():
	k = ctypes.WinDLL("kernel32", use_last_error=True)
	k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
	k.OpenProcess.restype = wintypes.HANDLE
	k.CloseHandle.argtypes = [wintypes.HANDLE]
	k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
	k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(_FILETIME)] * 4
	k.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
	k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
	k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
	k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
	k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
	k.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
	k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
	k.GetPriorityClass.argtypes = [wintypes.HANDLE]
	k.GetPriorityClass.restype = wintypes.DWORD
	return k


def _psapi():
	p = ctypes.WinDLL("psapi", use_last_error=True)
	p.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
	return p


_K32 = None
_PSAPI = None


def _k32():
	global _K32
	if _K32 is None:
		_K32 = _kernel32()
	return _K32


@dataclass(frozen=True)
class InfoProceso:
	pid: int
	nombre: str
	padre: int = 0
	memoria: int = -1
	cpu_100ns: int = -1
	usuario: str = ""
	ruta: str = ""
	sesion: int = -1
	prioridad: int = 0
	abierto: bool = False

	@property
	def del_sistema(self) -> bool:
		return es_del_sistema(self)


def instantanea() -> dict[int, tuple[str, int]]:
	"""``{pid: (nombre, pid del padre)}`` de todos los procesos (``CreateToolhelp32Snapshot``)."""
	k = _k32()
	asa = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	if not asa or asa == wintypes.HANDLE(-1).value:
		raise OSError(ctypes.get_last_error(), _("No se pudo leer la lista de procesos"))
	resultado: dict[int, tuple[str, int]] = {}
	try:
		entrada = PROCESSENTRY32W()
		entrada.dwSize = ctypes.sizeof(PROCESSENTRY32W)
		seguir = k.Process32FirstW(asa, ctypes.byref(entrada))
		while seguir:
			resultado[int(entrada.th32ProcessID)] = (entrada.szExeFile, int(entrada.th32ParentProcessID))
			seguir = k.Process32NextW(asa, ctypes.byref(entrada))
	finally:
		k.CloseHandle(asa)
	return resultado


def nombre_de(pid: int) -> str:
	"""Nombre del ejecutable de un proceso, o ``""``."""
	try:
		return instantanea().get(pid, ("", 0))[0]
	except OSError:
		log.debug("Sin instantánea de procesos", exc_info=True)
		return ""


_usuarios_por_sid: dict[str, str] = {}


def _usuario(asa: int) -> str:
	try:
		import win32security

		token = win32security.OpenProcessToken(asa, TOKEN_QUERY)
		try:
			sid, _atributos = win32security.GetTokenInformation(token, win32security.TokenUser)
		finally:
			token.Close()
		clave = win32security.ConvertSidToStringSid(sid)
		if clave not in _usuarios_por_sid:
			nombre, dominio, _tipo = win32security.LookupAccountSid(None, sid)
			_usuarios_por_sid[clave] = f"{dominio}\\{nombre}" if dominio else nombre
		return _usuarios_por_sid[clave]
	except Exception:  # noqa: BLE001 - sin permiso para leer el usuario: se deja vacío
		log.debug("No se pudo leer el usuario del proceso", exc_info=True)
		return ""


def sesion_de(pid: int) -> int:
	sesion = wintypes.DWORD(0)
	if _k32().ProcessIdToSessionId(pid, ctypes.byref(sesion)):
		return int(sesion.value)
	return -1


def info(pid: int, nombre: str = "", padre: int = 0) -> InfoProceso:
	"""Los datos de un proceso que se pueden leer sin permisos de administrador."""
	global _PSAPI
	k = _k32()
	sesion = sesion_de(pid)
	asa = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid) if pid not in (0, 4) else None
	if not asa:
		return InfoProceso(pid, nombre or nombre_de(pid), padre, sesion=sesion)
	try:
		tamano = wintypes.DWORD(32768)
		bufer = ctypes.create_unicode_buffer(tamano.value)
		ruta = bufer.value if k.QueryFullProcessImageNameW(asa, 0, bufer, ctypes.byref(tamano)) else ""
		if _PSAPI is None:
			_PSAPI = _psapi()
		contadores = PROCESS_MEMORY_COUNTERS()
		contadores.cb = ctypes.sizeof(contadores)
		memoria = int(contadores.WorkingSetSize) if _PSAPI.GetProcessMemoryInfo(asa, ctypes.byref(contadores), contadores.cb) else -1
		tiempos = [_FILETIME() for _i in range(4)]
		cpu = -1
		if k.GetProcessTimes(asa, *(ctypes.byref(t) for t in tiempos)):
			cpu = tiempos[2].valor + tiempos[3].valor
		prioridad = int(k.GetPriorityClass(asa))
		usuario = _usuario(asa)
	finally:
		k.CloseHandle(asa)
	return InfoProceso(pid, nombre or os.path.basename(ruta), padre, memoria, cpu, usuario, ruta, sesion, prioridad, True)


def listar() -> list[InfoProceso]:
	"""Todos los procesos con sus datos [trabajo]."""
	resultado = []
	for pid, (nombre, padre) in instantanea().items():
		try:
			resultado.append(info(pid, nombre, padre))
		except OSError:
			log.debug("No se pudo leer el proceso %d", pid, exc_info=True)
			resultado.append(InfoProceso(pid, nombre, padre))
	return resultado


def es_del_sistema(proceso: InfoProceso) -> bool:
	"""Procesos que zCommander nunca termina: críticos, de la sesión 0, de cuentas de servicio o que no se pueden abrir."""
	if proceso.pid in (0, 4) or proceso.nombre.casefold() in CRITICOS:
		return True
	if proceso.sesion == 0 or not proceso.abierto:
		return True
	cuenta = proceso.usuario.rsplit("\\", 1)[-1].casefold()
	return cuenta in CUENTAS_SISTEMA


def es_del_sistema_pid(pid: int) -> bool:
	try:
		return es_del_sistema(info(pid))
	except OSError:
		log.debug("No se pudo leer el proceso %d", pid, exc_info=True)
		return True


def motivo_para_no_terminar(proceso: InfoProceso) -> str:
	"""Por qué no se puede terminar desde la lista, o ``""``."""
	if proceso.pid == os.getpid():
		return _("No se puede terminar zCommander desde aquí: ciérrelo con Alt+F4")
	if es_del_sistema(proceso):
		return _("{n} es un proceso del sistema y no se puede terminar desde zCommander").format(n=proceso.nombre)
	return ""


def terminar(proceso: InfoProceso) -> None:
	"""Termina un proceso que no es del sistema [trabajo]. :raises api.ErrorArchivos: con el motivo."""
	motivo = motivo_para_no_terminar(proceso)
	if motivo:
		raise api.ErrorAcceso(motivo)
	k = _k32()
	asa = k.OpenProcess(PROCESS_TERMINATE, False, proceso.pid)
	if not asa:
		raise api.ErrorAcceso(_("Windows no deja terminar {n}: {e}").format(n=proceso.nombre, e=ctypes.FormatError(ctypes.get_last_error())))
	try:
		if not k.TerminateProcess(asa, 1):
			raise api.ErrorAcceso(_("No se pudo terminar {n}: {e}").format(n=proceso.nombre, e=ctypes.FormatError(ctypes.get_last_error())))
	finally:
		k.CloseHandle(asa)
	log.info("Proceso %s (%d) terminado a petición", proceso.nombre, proceso.pid)


def cambiar_prioridad(proceso: InfoProceso, clase: int) -> None:
	"""Cambia la clase de prioridad [trabajo]. :raises api.ErrorAcceso: si Windows no lo permite."""
	if clase not in {c for c, _t in PRIORIDADES}:
		raise ValueError(clase)
	k = _k32()
	asa = k.OpenProcess(PROCESS_SET_INFORMATION, False, proceso.pid)
	if not asa:
		raise api.ErrorAcceso(_("Windows no deja cambiar la prioridad de {n}").format(n=proceso.nombre))
	try:
		if not k.SetPriorityClass(asa, clase):
			raise api.ErrorAcceso(_("No se pudo cambiar la prioridad de {n}: {e}").format(
				n=proceso.nombre, e=ctypes.FormatError(ctypes.get_last_error())))
	finally:
		k.CloseHandle(asa)


def texto_prioridad(clase: int) -> str:
	return next((_(t) for c, t in PRIORIDADES if c == clase), _("Otra") if clase else "")


class MedidorCPU:
	"""Porcentaje de CPU de cada proceso entre dos llamadas a ``medir``."""

	def __init__(self) -> None:
		self._anterior: dict[int, int] = {}
		self._momento = 0.0
		self._procesadores = os.cpu_count() or 1

	def medir(self, procesos: Iterable[InfoProceso]) -> dict[int, float | None]:
		ahora = time.monotonic()
		transcurrido = ahora - self._momento if self._momento else 0.0
		resultado: dict[int, float | None] = {}
		actuales: dict[int, int] = {}
		for proceso in procesos:
			if proceso.cpu_100ns < 0:
				resultado[proceso.pid] = None
				continue
			actuales[proceso.pid] = proceso.cpu_100ns
			previo = self._anterior.get(proceso.pid)
			if previo is None or transcurrido <= 0:
				resultado[proceso.pid] = None
			else:
				uso = (proceso.cpu_100ns - previo) / 1e7 / transcurrido / self._procesadores * 100
				resultado[proceso.pid] = max(0.0, min(100.0, uso))
		self._anterior, self._momento = actuales, ahora
		return resultado


def resumen(proceso: InfoProceso, cpu: float | None = None) -> str:
	"""Texto para copiar al portapapeles con todos los datos."""
	lineas = [
		_("Nombre: {v}").format(v=proceso.nombre),
		_("PID: {v}").format(v=proceso.pid),
		_("Proceso padre: {v}").format(v=proceso.padre),
		_("Memoria: {v}").format(v=api.formato.tamano_legible(proceso.memoria) if proceso.memoria >= 0 else _("Sin datos")),
		_("CPU: {v}").format(v=f"{cpu:.1f} %".replace(".", ",") if cpu is not None else _("Sin datos")),
		_("Usuario: {v}").format(v=proceso.usuario or _("Sin datos")),
		_("Ruta: {v}").format(v=proceso.ruta or _("Sin datos")),
		_("Sesión: {v}").format(v=proceso.sesion),
		_("Prioridad: {v}").format(v=texto_prioridad(proceso.prioridad) or _("Sin datos")),
	]
	return "\r\n".join(lineas)
