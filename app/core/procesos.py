# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Procesos hijos de zCommander con Job Objects de Windows (diseño 2.0, 14.9). Sin wx.

Por qué así:

- Un **Job Object global** con ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``: si
  zCommander muere de golpe, Windows cierra su identificador del Job y mata a
  todos sus hijos (rclone, FFmpeg, 7za, PowerShell, git...). zCommander NO
  está dentro: solo sus hijos.
- **Un Job anidado por cada** ``lanzar`` **y cada** ``popen``, hijo del global
  (Windows 8 o posterior admite Jobs anidados). Cancelar o agotar el tiempo
  termina TODO su árbol con ``TerminateJobObject``, también los nietos.
- **Sin escapes del Job**: el proceso se crea suspendido, se asigna al global
  y a su Job anidado y solo entonces se reanuda con ``NtResumeProcess``
  (``subprocess`` no da el identificador del hilo principal); así ningún
  nieto nace fuera. Si la asignación falla, el proceso suspendido se termina
  y se lanza ``ErrorProceso``: nunca queda un proceso suspendido.
- ``lanzar_independiente`` crea procesos FUERA del Job (sobreviven a
  zCommander): «Reiniciar», el ``.bat`` del actualizador, la instancia real de
  una tarea programada y los programas que abre la persona.

``ErrorProceso`` (y no ``ErrorArchivos``) porque ``app/core`` no importa
``app.services``; ``Anfitrion.ejecutar_programa`` lo convierte en ``ErrorArchivos``.
"""

from __future__ import annotations

import builtins
import ctypes
import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

try:
	import win32api
	import win32con
	import win32job
	import win32process
except ImportError:  # pragma: no cover - fuera de Windows no hay Jobs
	win32api = win32con = win32job = win32process = None  # type: ignore[assignment]

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorProceso(Exception):
	"""No se pudo lanzar o controlar un programa; ``mensaje`` en español."""

	def __init__(self, mensaje: str) -> None:
		super().__init__(mensaje)
		self.mensaje = mensaje


@dataclass(frozen=True)
class ResultadoPrograma:
	codigo: int
	salida: bytes
	errores: bytes
	cancelado: bool


def _cancelado(cancelacion: Any) -> bool:
	if cancelacion is None:
		return False
	if callable(cancelacion):
		return bool(cancelacion())
	for nombre in ("cancelado", "esta_cancelado", "is_set"):
		valor = getattr(cancelacion, nombre, None)
		if valor is not None:
			return bool(valor() if callable(valor) else valor)
	return False


def _crear_job(matar_al_cerrar: bool) -> Any:
	job = win32job.CreateJobObject(None, "")
	if matar_al_cerrar:
		info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
		info["BasicLimitInformation"]["LimitFlags"] |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
		win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
	return job


def _reanudar(proceso: subprocess.Popen) -> None:
	estado = ctypes.windll.ntdll.NtResumeProcess(ctypes.c_void_p(int(proceso._handle)))  # type: ignore[attr-defined]
	if estado != 0:
		raise OSError(f"NtResumeProcess devolvió {estado:#x}")


def _nombre_exe(pid: int) -> str:
	try:
		manejador = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
	except Exception:  # noqa: BLE001 - el proceso pudo terminar entretanto
		log.debug("No se pudo abrir el proceso %s", pid, exc_info=True)
		return ""
	try:
		return os.path.basename(win32process.GetModuleFileNameEx(manejador, None))
	except Exception:  # noqa: BLE001 - sin permiso para leer su nombre
		try:
			buffer = ctypes.create_unicode_buffer(32768)
			tamano = ctypes.c_ulong(len(buffer))
			if ctypes.windll.kernel32.QueryFullProcessImageNameW(int(manejador), 0, buffer, ctypes.byref(tamano)):
				return os.path.basename(buffer.value)
		except Exception:  # noqa: BLE001 - se da por desconocido
			log.debug("No se pudo leer el nombre del proceso %s", pid, exc_info=True)
		return ""
	finally:
		win32api.CloseHandle(manejador)


class GestorProcesos:
	"""Un Job global y sus Jobs anidados. La aplicación usa uno (``gestor()``); las pruebas crean otros."""

	def __init__(self) -> None:
		self._candado = threading.Lock()
		self._job: Any = None
		self._anidados: dict[int, Any] = {}

	# ── Job global ──────────────────────────────────────────────────────────

	def job_global(self) -> Any:
		with self._candado:
			if self._job is None:
				if win32job is None:
					raise ErrorProceso(_("Este sistema no admite el control de procesos de Windows"))
				self._job = _crear_job(matar_al_cerrar=True)
			return self._job

	def cerrar(self) -> None:
		"""Cierra el Job global: Windows termina todos los procesos que siguen dentro."""
		with self._candado:
			job, self._job = self._job, None
			anidados, self._anidados = list(self._anidados.values()), {}
		for manejador in [*anidados, job]:
			if manejador is not None:
				try:
					manejador.Close()
				except Exception:  # noqa: BLE001 - un identificador ya cerrado no impide seguir
					log.debug("No se pudo cerrar un Job", exc_info=True)

	# ── Crear procesos dentro del Job ───────────────────────────────────────

	def _asignar(self, proceso: subprocess.Popen, anidado: Any) -> None:
		win32job.AssignProcessToJobObject(self.job_global(), int(proceso._handle))  # type: ignore[attr-defined]
		win32job.AssignProcessToJobObject(anidado, int(proceso._handle))  # type: ignore[attr-defined]

	def popen(self, argumentos: Sequence[str], **opciones: Any) -> subprocess.Popen:
		"""Proceso largo en su Job anidado (rcd, ffplay, OCR). Sin consola ni shell."""
		if opciones.pop("shell", False):
			raise ErrorProceso(_("No se ejecutan programas a través del intérprete de órdenes"))
		opciones["creationflags"] = int(opciones.get("creationflags", 0)) | CREATE_SUSPENDED | CREATE_NO_WINDOW
		nombre = os.path.basename(str(argumentos[0])) if argumentos else "?"
		anidado = _crear_job(matar_al_cerrar=True)
		proceso = subprocess.Popen(list(argumentos), **opciones)  # noqa: S603 - lista de argumentos sin shell
		try:
			self._asignar(proceso, anidado)
			_reanudar(proceso)
		except Exception as error:
			log.error("No se pudo meter %s en su Job; se termina el proceso suspendido", nombre, exc_info=True)
			try:
				win32api.TerminateProcess(int(proceso._handle), 1)  # type: ignore[attr-defined]
			except Exception:  # noqa: BLE001 - si ya no existe, mejor
				log.debug("TerminateProcess falló", exc_info=True)
			try:
				anidado.Close()
			except Exception:  # noqa: BLE001
				log.debug("No se pudo cerrar el Job anidado", exc_info=True)
			raise ErrorProceso(_("No se pudo controlar el programa {p}").format(p=nombre)) from error
		with self._candado:
			self._anidados[proceso.pid] = anidado
		return proceso

	def terminar_arbol(self, proceso: subprocess.Popen) -> None:
		"""Termina el proceso y todos sus descendientes (su Job anidado)."""
		with self._candado:
			anidado = self._anidados.get(proceso.pid)
		if anidado is None:
			proceso.kill()
			return
		try:
			win32job.TerminateJobObject(anidado, 1)
		except Exception:  # noqa: BLE001 - si el Job ya no tiene procesos, no hay nada que terminar
			log.debug("TerminateJobObject falló", exc_info=True)

	def soltar(self, proceso: subprocess.Popen) -> None:
		"""Cierra el Job anidado de un proceso ya terminado (sus restos mueren con él)."""
		with self._candado:
			anidado = self._anidados.pop(proceso.pid, None)
		if anidado is not None:
			try:
				anidado.Close()
			except Exception:  # noqa: BLE001
				log.debug("No se pudo cerrar el Job anidado", exc_info=True)

	def lanzar(self, argumentos: list[str], *, entrada: bytes = b"", carpeta: str | None = None, tiempo_s: float = 60,
			cancelacion: Any = None, al_leer: Callable[[bytes], None] | None = None,
			entorno: dict[str, str] | None = None) -> ResultadoPrograma:
		"""Ejecuta y espera (como mucho ``tiempo_s``). Sin consola, sin shell, con ruta absoluta.

		Si se cancela o se agota el tiempo, termina todo su árbol y devuelve ``cancelado=True``.
		"""
		if not argumentos:
			raise ErrorProceso(_("No hay programa que ejecutar"))
		if not os.path.isabs(str(argumentos[0])):
			raise ErrorProceso(_("El programa debe ir con su ruta completa: {p}").format(p=argumentos[0]))
		variables = None
		if entorno is not None:
			variables = dict(os.environ)
			variables.update(entorno)
		proceso = self.popen(argumentos, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
			cwd=carpeta, env=variables)
		salida: list[bytes] = []
		errores: list[bytes] = []

		def leer(flujo, destino: list[bytes], avisar: Callable[[bytes], None] | None) -> None:
			for bloque in iter(lambda: flujo.read1(65536) if hasattr(flujo, "read1") else flujo.read(65536), b""):
				destino.append(bloque)
				if avisar is not None:
					try:
						avisar(bloque)
					except Exception:  # noqa: BLE001 - quien lee la salida no corta la ejecución
						log.warning("Falló al_leer", exc_info=True)

		hilos = [
			threading.Thread(target=leer, args=(proceso.stdout, salida, al_leer), daemon=True, name="proceso-salida"),
			threading.Thread(target=leer, args=(proceso.stderr, errores, None), daemon=True, name="proceso-errores"),
		]
		for hilo in hilos:
			hilo.start()
		try:
			if entrada:
				proceso.stdin.write(entrada)
			proceso.stdin.close()
		except OSError:
			log.debug("El programa cerró su entrada antes de leerla", exc_info=True)
		cancelado = False
		limite = time.monotonic() + tiempo_s
		while proceso.poll() is None:
			if _cancelado(cancelacion) or time.monotonic() > limite:
				cancelado = True
				self.terminar_arbol(proceso)
				break
			time.sleep(0.05)
		codigo = proceso.wait()
		for hilo in hilos:
			hilo.join(2)
		self.soltar(proceso)
		return ResultadoPrograma(codigo, b"".join(salida), b"".join(errores), cancelado)

	def hijos_vivos(self, nombre_exe: str) -> list[int]:
		"""PID de los procesos del Job global (también de sus Jobs anidados) con ese nombre de ejecutable."""
		with self._candado:
			job = self._job
		if job is None:
			return []
		try:
			pids = win32job.QueryInformationJobObject(job, win32job.JobObjectBasicProcessIdList)
		except Exception:  # noqa: BLE001 - sin información, nada vivo
			log.debug("No se pudo consultar el Job global", exc_info=True)
			return []
		nombre = nombre_exe.casefold()
		return [pid for pid in pids if _nombre_exe(pid).casefold() == nombre]


_gestor = GestorProcesos()


def gestor() -> GestorProcesos:
	return _gestor


def lanzar(argumentos: list[str], *, entrada: bytes = b"", carpeta: str | None = None, tiempo_s: float = 60,
		cancelacion: Any = None, al_leer: Callable[[bytes], None] | None = None,
		entorno: dict[str, str] | None = None) -> ResultadoPrograma:
	return _gestor.lanzar(argumentos, entrada=entrada, carpeta=carpeta, tiempo_s=tiempo_s, cancelacion=cancelacion,
		al_leer=al_leer, entorno=entorno)


def popen(argumentos: Sequence[str], **opciones: Any) -> subprocess.Popen:
	return _gestor.popen(argumentos, **opciones)


def terminar_arbol(proceso: subprocess.Popen) -> None:
	_gestor.terminar_arbol(proceso)


def hijos_vivos(nombre_exe: str) -> list[int]:
	return _gestor.hijos_vivos(nombre_exe)


def esta_en_un_job() -> bool:
	if win32job is None:
		return False
	try:
		return bool(win32job.IsProcessInJob(win32api.GetCurrentProcess(), None))
	except Exception:  # noqa: BLE001 - si no se puede saber, se supone que no
		log.debug("IsProcessInJob falló", exc_info=True)
		return False


def puede_salir_del_job() -> bool:
	"""Si zCommander está en un Job ajeno, ¿admite ``CREATE_BREAKAWAY_FROM_JOB``? Sin Job, verdadero."""
	if not esta_en_un_job():
		return True
	try:
		info = win32job.QueryInformationJobObject(None, win32job.JobObjectExtendedLimitInformation)
	except Exception:  # noqa: BLE001 - sin poder consultarlo, no se intenta salir
		log.debug("No se pudo consultar el Job de zCommander", exc_info=True)
		return False
	banderas = int(info["BasicLimitInformation"]["LimitFlags"])
	return bool(banderas & (JOB_OBJECT_LIMIT_BREAKAWAY_OK | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK))


def lanzar_independiente(argumentos: list[str], *, carpeta: str | None = None, sin_ventana: bool = False) -> int:
	"""Proceso FUERA del Job de zCommander, que le sobrevive. Devuelve el PID.

	:param sin_ventana: sin consola visible (``CREATE_NO_WINDOW``). Para scripts
		como el ``.bat`` del actualizador: una consola que se abre le quita el foco
		al lector de pantalla. No usarlo para programas que la persona debe ver.
	"""
	banderas = CREATE_NEW_PROCESS_GROUP
	if sin_ventana:
		banderas |= subprocess.CREATE_NO_WINDOW
	if esta_en_un_job():
		if puede_salir_del_job():
			banderas |= CREATE_BREAKAWAY_FROM_JOB
		else:
			log.warning("zCommander está en un Job que no deja salir: %s se lanza dentro de ese Job", argumentos[:1])
	proceso = subprocess.Popen(list(argumentos), cwd=carpeta, creationflags=banderas, close_fds=True)  # noqa: S603 - sin shell
	return proceso.pid
