# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Vigilancia de carpetas con ``ReadDirectoryChangesW`` (pywin32) y detección de «ya terminó de llegar».

- Un hilo por carpeta, con E/S solapada: espera a la vez la notificación de
  Windows y el evento de parar, así ``detener()`` responde al momento y el
  cierre de zCommander nunca espera a que llegue un archivo.
- Un archivo nuevo o cambiado pasa a «pendiente». El ``Revisor`` (un hilo)
  lo da por llegado cuando lleva ``retraso_s`` sin avisos, su tamaño y su
  fecha no cambian entre dos miradas y se puede abrir sin compartir (nadie lo
  está escribiendo). Así una descarga de 2 GB se anuncia una sola vez, al
  terminar, y no en cada bloque.
- Se ignoran los temporales de los navegadores y de Office (``.crdownload``,
  ``.part``, ``~$...``): llegan con su nombre final al renombrarse.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import threading
import time
from collections.abc import Callable

log = logging.getLogger("zcplugins.zc.monitor")

TEMPORALES = ("*.crdownload", "*.part", "*.partial", "*.download", "*.tmp", "~$*", "*.!ut", "desktop.ini", "thumbs.db")
_AVISOS_UTILES = (1, 3, 5)  # FILE_ACTION_ADDED, MODIFIED, RENAMED_NEW_NAME


def es_temporal(ruta: str) -> bool:
	nombre = os.path.basename(ruta).casefold()
	return any(fnmatch.fnmatch(nombre, p) for p in TEMPORALES)


def _estado_real(ruta: str) -> tuple[int, float] | None:
	try:
		info = os.stat(ruta)
	except OSError:
		return None
	if not os.path.isfile(ruta):
		return None
	return info.st_size, info.st_mtime


def _abrible_en_exclusiva(ruta: str) -> bool:
	"""Verdadero si nadie tiene el archivo abierto para escribir (se abre sin compartir escritura)."""
	try:
		import pywintypes
		import win32con
		import win32file
	except ImportError:
		return True
	try:
		manejador = win32file.CreateFile(ruta, win32con.GENERIC_READ, win32con.FILE_SHARE_READ, None, win32con.OPEN_EXISTING, 0, None)
	except pywintypes.error:
		return False
	manejador.Close()
	return True


class Estabilidad:
	"""Decide cuándo un archivo pendiente ha terminado de llegar (sin hilos: se prueba con un reloj falso)."""

	def __init__(self, retraso_s: float, reloj: Callable[[], float] = time.monotonic,
			estado: Callable[[str], tuple[int, float] | None] = _estado_real,
			abrible: Callable[[str], bool] = _abrible_en_exclusiva) -> None:
		self.retraso_s = retraso_s
		self._reloj = reloj
		self._estado = estado
		self._abrible = abrible
		self._candado = threading.Lock()
		self._pendientes: dict[str, tuple[float, tuple[int, float] | None]] = {}
		self._ignorar: dict[str, float] = {}
		self._llegados: dict[str, tuple[int, float]] = {}

	def notificar(self, ruta: str) -> None:
		"""Un aviso de Windows sobre ``ruta`` (desde el hilo vigilante)."""
		if es_temporal(ruta):
			return
		clave = os.path.normcase(ruta)
		with self._candado:
			if self._ignorar.get(clave, 0) > self._reloj():
				return
		# Tamaño y fecha de ahora: si dentro de un retraso siguen iguales, ha terminado de llegar.
		actual = self._estado(ruta)
		with self._candado:
			self._pendientes[ruta] = (self._reloj(), actual)

	def ignorar(self, ruta: str, segundos: float = 30) -> None:
		"""No avisar de ``ruta`` durante un rato (lo que acaba de crear o renombrar una regla)."""
		with self._candado:
			self._ignorar[os.path.normcase(ruta)] = self._reloj() + segundos
			self._pendientes.pop(ruta, None)

	def vaciar(self) -> None:
		with self._candado:
			self._pendientes.clear()

	def revisar(self) -> list[str]:
		"""Los archivos que ya han llegado del todo (cada uno una sola vez)."""
		ahora = self._reloj()
		listos: list[str] = []
		with self._candado:
			candidatos = [(r, t, e) for r, (t, e) in self._pendientes.items() if ahora - t >= self.retraso_s]
			for clave in [c for c, hasta in self._ignorar.items() if hasta <= ahora]:
				del self._ignorar[clave]
		for ruta, momento, visto in candidatos:
			actual = self._estado(ruta)
			with self._candado:
				if self._pendientes.get(ruta, (None,))[0] != momento:
					continue  # llegó otro aviso mientras se miraba
				if actual is None:
					del self._pendientes[ruta]
					continue
				if visto != actual:
					# Primera mirada o aún crece: se vuelve a mirar dentro de un retraso.
					self._pendientes[ruta] = (ahora, actual)
					continue
			if not self._abrible(ruta):
				with self._candado:
					if ruta in self._pendientes:
						self._pendientes[ruta] = (ahora, actual)
				continue
			with self._candado:
				self._pendientes.pop(ruta, None)
				if self._llegados.get(ruta) == actual:
					continue  # el mismo archivo, sin cambios: ya se avisó
				self._llegados[ruta] = actual
				if len(self._llegados) > 5000:
					self._llegados.pop(next(iter(self._llegados)))
			listos.append(ruta)
		return listos


class Vigilante(threading.Thread):
	"""Lee los cambios de una carpeta (sin subcarpetas) y llama a ``al_cambio(ruta)`` en su hilo."""

	def __init__(self, carpeta: str, al_cambio: Callable[[str], None]) -> None:
		super().__init__(name=f"zc-monitor-{os.path.basename(carpeta.rstrip(chr(92))) or carpeta}", daemon=True)
		self.carpeta = carpeta
		self.al_cambio = al_cambio
		self.error = ""
		import win32event

		self._parar = win32event.CreateEvent(None, True, False, None)
		self.listo = threading.Event()

	def detener(self) -> None:
		import win32event

		win32event.SetEvent(self._parar)

	def run(self) -> None:
		import pywintypes
		import win32con
		import win32event
		import win32file

		try:
			manejador = win32file.CreateFile(self.carpeta, 0x0001,  # FILE_LIST_DIRECTORY
				win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE, None, win32con.OPEN_EXISTING,
				win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED, None)
		except pywintypes.error as error:
			self.error = f"No se puede vigilar {self.carpeta}: {error.strerror}"
			log.warning(self.error)
			self.listo.set()
			return
		filtro = (win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_SIZE
			| win32con.FILE_NOTIFY_CHANGE_LAST_WRITE)
		solapado = pywintypes.OVERLAPPED()
		solapado.hEvent = win32event.CreateEvent(None, True, False, None)
		bufer = win32file.AllocateReadBuffer(64 * 1024)
		try:
			while True:
				win32event.ResetEvent(solapado.hEvent)
				win32file.ReadDirectoryChangesW(manejador, bufer, False, filtro, solapado)
				self.listo.set()
				resultado = win32event.WaitForMultipleObjects([solapado.hEvent, self._parar], False, win32event.INFINITE)
				if resultado != win32event.WAIT_OBJECT_0:
					win32file.CancelIo(manejador)
					break
				try:
					leidos = win32file.GetOverlappedResult(manejador, solapado, True)
				except pywintypes.error as error:
					self.error = f"Se dejó de vigilar {self.carpeta}: {error.strerror}"
					log.warning(self.error)
					break
				if not leidos:
					# El búfer se desbordó: Windows no dice qué cambió; se revisa la carpeta entera.
					self._revisar_todo()
					continue
				for accion, nombre in win32file.FILE_NOTIFY_INFORMATION(bufer, leidos):
					if accion in _AVISOS_UTILES:
						self._avisar(os.path.join(self.carpeta, nombre))
		finally:
			manejador.Close()
			self.listo.set()

	def _avisar(self, ruta: str) -> None:
		try:
			self.al_cambio(ruta)
		except Exception:  # noqa: BLE001 - un fallo al avisar no detiene la vigilancia
			log.exception("Falló el aviso del monitor para %s", ruta)

	def _revisar_todo(self) -> None:
		try:
			for elemento in os.scandir(self.carpeta):
				if elemento.is_file(follow_symlinks=False):
					self._avisar(elemento.path)
		except OSError:
			log.debug("No se pudo revisar %s", self.carpeta, exc_info=True)


class Revisor(threading.Thread):
	"""Cada medio segundo pide a ``Estabilidad`` los archivos llegados y llama a ``al_llegar(ruta)`` en este hilo."""

	def __init__(self, estabilidad: Estabilidad, al_llegar: Callable[[str], None], intervalo_s: float = 0.5) -> None:
		super().__init__(name="zc-monitor-revisor", daemon=True)
		self.estabilidad = estabilidad
		self.al_llegar = al_llegar
		self.intervalo_s = intervalo_s
		self._parar = threading.Event()

	def detener(self) -> None:
		self._parar.set()

	def run(self) -> None:
		while not self._parar.wait(self.intervalo_s):
			for ruta in self.estabilidad.revisar():
				if self._parar.is_set():
					return
				try:
					self.al_llegar(ruta)
				except Exception:  # noqa: BLE001 - un archivo que falla no detiene el monitor
					log.exception("Falló el monitor con %s", ruta)
