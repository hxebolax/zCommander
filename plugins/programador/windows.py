# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tareas en el Programador de tareas de Windows (diseño 2.0, 11.24), por COM (``Schedule.Service``).

Cada tarea de zCommander es una tarea de Windows en la carpeta
``\\zCommander`` que lanza ``ZCommander.exe --tarea <id>``. Ajustes fijados
por el diseño, para que Windows nunca mate ni frene a zCommander:

- ``LogonType = InteractiveToken`` (``TASK_LOGON_INTERACTIVE_TOKEN``): corre en
  la sesión de la persona y con su usuario, así DPAPI descifra sus secretos y
  la ventana minimizada aparece en su escritorio.
- ``StartWhenAvailable``: si la sesión no estaba iniciada a la hora, se
  ejecuta al iniciarla.
- ``ExecutionTimeLimit = PT0S`` (sin límite), ``MultipleInstancesPolicy =
  Parallel`` (una segunda ejecución reenvía la orden a la instancia abierta),
  ``Priority = 4`` (normal; la 7 por defecto es baja) y sin parar ni dejar de
  empezar con batería.

La tarea se registra con su XML (el mismo que comprueban las pruebas). El
servicio COM se crea con una fábrica que las pruebas sustituyen: nunca se
crean tareas reales en las pruebas.
"""

from __future__ import annotations

import datetime as _fecha
import getpass
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from . import tareas as modulo_tareas

log = logging.getLogger("zcplugins.zc.programador")

CARPETA_WINDOWS = "zCommander"
TASK_CREATE_OR_UPDATE = 6
TASK_LOGON_INTERACTIVE_TOKEN = 3
_DIAS_XML = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class ErrorProgramador(Exception):
	"""El Programador de tareas de Windows rechazó algo (mensaje en español)."""


def nombre_windows(tarea: modulo_tareas.Tarea) -> str:
	return f"zCommander {tarea.id}"


def usuario_actual() -> str:
	dominio = os.environ.get("USERDOMAIN", "")
	usuario = os.environ.get("USERNAME") or getpass.getuser()
	return f"{dominio}\\{usuario}" if dominio else usuario


def comando(id_tarea: str) -> tuple[str, str, str]:
	"""(programa, argumentos, carpeta de trabajo) para lanzar zCommander con ``--tarea <id>``.

	Compilado, el ``ZCommander.exe`` que está ejecutándose; desde el código
	fuente, ``pythonw.exe`` (sin consola) con el ``main.py`` de la raíz.
	"""
	raiz = Path(__file__).resolve().parents[2]
	if getattr(sys, "frozen", False):
		ejecutable = Path(sys.executable)
		return str(ejecutable), f"--tarea {id_tarea}", str(ejecutable.parent)
	interprete = Path(sys.executable)
	sin_consola = interprete.with_name("pythonw.exe")
	programa = sin_consola if sin_consola.is_file() else interprete
	return str(programa), f'"{raiz / "main.py"}" --tarea {id_tarea}', str(raiz)


def _inicio(tarea: modulo_tareas.Tarea, hoy: _fecha.date) -> str:
	dia = _fecha.date.fromisoformat(tarea.fecha) if tarea.fecha else hoy
	horas, minutos = modulo_tareas.hora_y_minutos(tarea.hora)
	return f"{dia.isoformat()}T{horas:02d}:{minutos:02d}:00"


def _disparador(tarea: modulo_tareas.Tarea, usuario: str, hoy: _fecha.date) -> str:
	if tarea.frecuencia == modulo_tareas.AL_INICIAR_SESION:
		return (f"    <LogonTrigger>\n      <Enabled>true</Enabled>\n      <UserId>{escape(usuario)}</UserId>\n"
			"    </LogonTrigger>")
	inicio = _inicio(tarea, hoy)
	if tarea.frecuencia == modulo_tareas.UNA_VEZ:
		return f"    <TimeTrigger>\n      <StartBoundary>{inicio}</StartBoundary>\n      <Enabled>true</Enabled>\n    </TimeTrigger>"
	if tarea.frecuencia == modulo_tareas.DIARIA:
		calendario = "      <ScheduleByDay>\n        <DaysInterval>1</DaysInterval>\n      </ScheduleByDay>"
	else:
		dias = "".join(f"\n          <{_DIAS_XML[d]} />" for d in sorted(set(tarea.dias_semana)) if 0 <= d < 7)
		calendario = (f"      <ScheduleByWeek>\n        <DaysOfWeek>{dias}\n        </DaysOfWeek>\n"
			"        <WeeksInterval>1</WeeksInterval>\n      </ScheduleByWeek>")
	return (f"    <CalendarTrigger>\n      <StartBoundary>{inicio}</StartBoundary>\n      <Enabled>true</Enabled>\n"
		f"{calendario}\n    </CalendarTrigger>")


def xml_tarea(tarea: modulo_tareas.Tarea, programa: str, argumentos: str, carpeta_trabajo: str, usuario: str,
		hoy: _fecha.date | None = None) -> str:
	"""El XML de la tarea de Windows (esquema del Programador de tareas 1.2)."""
	hoy = hoy or _fecha.date.today()
	activa = "true" if tarea.activa else "false"
	return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>zCommander</Author>
    <Description>{escape(tarea.nombre)}: {escape(tarea.que_hace())}</Description>
  </RegistrationInfo>
  <Triggers>
{_disparador(tarea, usuario, hoy)}
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(usuario)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>{activa}</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(programa)}</Command>
      <Arguments>{escape(argumentos)}</Arguments>
      <WorkingDirectory>{escape(carpeta_trabajo)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _servicio_real() -> Any:
	# Red de seguridad: una prueba que olvide simular el COM nunca crea tareas reales en el equipo.
	if "PYTEST_CURRENT_TEST" in os.environ:
		raise ErrorProgramador("En las pruebas no se usa el Programador de tareas real")
	import win32com.client

	servicio = win32com.client.Dispatch("Schedule.Service")
	servicio.Connect()
	return servicio


class ProgramadorWindows:
	"""Registra y borra tareas en ``\\zCommander``. Llamar desde un hilo de trabajo (COM y disco)."""

	def __init__(self, fabrica: Callable[[], Any] | None = None) -> None:
		self._fabrica = fabrica or _servicio_real

	def _com(self, funcion: Callable[[Any], Any]) -> Any:
		iniciado = False
		try:
			import pythoncom

			pythoncom.CoInitialize()
			iniciado = True
		except ImportError:
			pass
		try:
			return funcion(self._fabrica())
		except ErrorProgramador:
			raise
		except Exception as error:  # noqa: BLE001 - com_error y demás: mensaje claro y traza en el registro
			log.warning("El Programador de tareas de Windows falló", exc_info=True)
			raise ErrorProgramador(f"El Programador de tareas de Windows no aceptó el cambio: {_texto_com(error)}") from error
		finally:
			if iniciado:
				import pythoncom

				pythoncom.CoUninitialize()

	@staticmethod
	def _carpeta(servicio: Any, crear: bool) -> Any:
		try:
			return servicio.GetFolder(f"\\{CARPETA_WINDOWS}")
		except Exception:  # noqa: BLE001 - no existe todavía
			if not crear:
				return None
			return servicio.GetFolder("\\").CreateFolder(CARPETA_WINDOWS)

	def registrar(self, tarea: modulo_tareas.Tarea, hoy: _fecha.date | None = None) -> None:
		programa, argumentos, carpeta = comando(tarea.id)
		xml = xml_tarea(tarea, programa, argumentos, carpeta, usuario_actual(), hoy)

		def hacer(servicio: Any) -> None:
			self._carpeta(servicio, crear=True).RegisterTask(nombre_windows(tarea), xml, TASK_CREATE_OR_UPDATE, None, None,
				TASK_LOGON_INTERACTIVE_TOKEN)

		self._com(hacer)

	def borrar(self, tarea: modulo_tareas.Tarea) -> None:
		def hacer(servicio: Any) -> None:
			carpeta = self._carpeta(servicio, crear=False)
			if carpeta is None:
				return
			try:
				carpeta.DeleteTask(nombre_windows(tarea), 0)
			except Exception:  # noqa: BLE001 - ya no estaba: no es un error
				log.debug("La tarea %s no estaba en el Programador de Windows", nombre_windows(tarea), exc_info=True)

		self._com(hacer)

	def sincronizar(self, lista: list[modulo_tareas.Tarea], usar_windows: bool) -> list[str]:
		"""Registra (o, sin el Programador de Windows, borra) las tareas de ``lista``. Devuelve los problemas.

		Solo toca las tareas de esta copia de zCommander (las de ``lista``): otra
		copia portátil del mismo equipo puede tener las suyas en la misma carpeta.
		"""
		problemas = []
		for tarea in lista:
			try:
				if usar_windows:
					self.registrar(tarea)
				else:
					self.borrar(tarea)
			except ErrorProgramador as error:
				problemas.append(f"{tarea.nombre}: {error}")
		return problemas


def _texto_com(error: BaseException) -> str:
	argumentos = getattr(error, "args", ())
	if len(argumentos) >= 3 and isinstance(argumentos[2], tuple) and len(argumentos[2]) > 2 and argumentos[2][2]:
		return str(argumentos[2][2]).strip()
	if len(argumentos) >= 2 and isinstance(argumentos[1], str):
		return argumentos[1]
	return str(error)
