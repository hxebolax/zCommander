# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motores del reproductor: ``wx.media.MediaCtrl`` (Windows) y ``ffplay`` (componente FFmpeg).

Los dos cumplen el mismo contrato (``Motor``), así el reproductor no sabe cuál
suena. Los avisos (``al_cargado``, ``al_terminar``, ``al_error``) llegan siempre
en el hilo de la interfaz.

- ``MotorWindows`` envuelve un control con la interfaz de ``MediaCtrl`` (``Load``,
  ``Play``, ``Tell``...). Las pruebas le pasan un control falso; ``crear_control``
  crea el real en una ventana oculta.
- ``MotorFfplay`` lanza ``ffplay -nodisp -autoexit`` como proceso aparte (dentro
  del Job Object de zCommander, con ``zc.ejecutar_programa``). ffplay sin ventana
  no se puede pausar ni mover: pausar termina el proceso y recuerda la posición,
  y continuar o saltar lo vuelve a lanzar con ``-ss`` en esa posición. No admite
  cambiar la velocidad.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Estados de wx.media.MediaCtrl.GetState (los mismos números que wx.media.MEDIASTATE_*).
MEDIASTATE_STOPPED, MEDIASTATE_PAUSED, MEDIASTATE_PLAYING = 0, 1, 2

DETENIDO, PAUSADO, REPRODUCIENDO = "detenido", "pausado", "reproduciendo"

#: Segundos que se espera a que Windows diga que ha abierto el archivo.
TIEMPO_CARGA_S = 6.0


class Motor(Protocol):
	nombre: str
	admite_velocidad: bool
	al_cargado: Callable[[], None] | None
	al_terminar: Callable[[], None] | None
	al_error: Callable[[str], None] | None

	def cargar(self, ruta: str) -> bool: ...
	def reproducir(self) -> None: ...
	def pausar(self) -> None: ...
	def detener(self) -> None: ...
	def estado(self) -> str: ...
	def posicion(self) -> float: ...
	def duracion(self) -> float: ...
	def ir_a(self, segundos: float) -> None: ...
	def fijar_volumen(self, volumen: int) -> None: ...
	def fijar_velocidad(self, velocidad: float) -> bool: ...
	def cerrar(self) -> None: ...


class MotorWindows:
	"""Motor de Windows (``wx.media.MediaCtrl``, códecs instalados)."""

	nombre = "Windows"
	admite_velocidad = True

	def __init__(self, control: Any, planificar_tarde: Callable[[float, Callable[[], None]], Any] | None = None,
			al_cerrar: Callable[[], None] | None = None) -> None:
		self.control = control
		self._planificar_tarde = planificar_tarde
		self._al_cerrar = al_cerrar
		self.al_cargado: Callable[[], None] | None = None
		self.al_terminar: Callable[[], None] | None = None
		self.al_error: Callable[[str], None] | None = None
		self.cargado = False
		self._carga = 0
		self._ruta = ""

	def cargar(self, ruta: str) -> bool:
		"""Empieza a abrir ``ruta``; verdadero si Windows lo acepta (el aviso llega con ``evento_cargado``)."""
		self.cargado = False
		self._carga += 1
		self._ruta = ruta
		try:
			aceptado = bool(self.control.Load(ruta))
		except Exception:  # noqa: BLE001 - un códec roto no debe tumbar el reproductor
			log.warning("MediaCtrl no pudo abrir %s", ruta, exc_info=True)
			aceptado = False
		if aceptado and self._planificar_tarde is not None:
			carga = self._carga
			self._planificar_tarde(TIEMPO_CARGA_S, lambda: self._comprobar_carga(carga))
		return aceptado

	def _comprobar_carga(self, carga: int) -> None:
		if carga == self._carga and not self.cargado and self.al_error is not None:
			log.info("Windows no terminó de abrir %s a tiempo", self._ruta)
			self.al_error("no_abre")

	def evento_cargado(self) -> None:
		if self.cargado:
			return
		self.cargado = True
		if self.al_cargado is not None:
			self.al_cargado()

	def evento_terminado(self) -> None:
		if self.al_terminar is not None:
			self.al_terminar()

	def reproducir(self) -> None:
		self.control.Play()

	def pausar(self) -> None:
		self.control.Pause()

	def detener(self) -> None:
		self._carga += 1
		try:
			self.control.Stop()
		except Exception:  # noqa: BLE001 - detener lo que no está abierto no es un error
			log.debug("Stop falló", exc_info=True)

	def estado(self) -> str:
		valor = self.control.GetState()
		return {MEDIASTATE_PLAYING: REPRODUCIENDO, MEDIASTATE_PAUSED: PAUSADO}.get(valor, DETENIDO)

	def posicion(self) -> float:
		return max(0.0, self.control.Tell() / 1000)

	def duracion(self) -> float:
		return max(0.0, self.control.Length() / 1000)

	def ir_a(self, segundos: float) -> None:
		self.control.Seek(int(max(0.0, segundos) * 1000))

	def fijar_volumen(self, volumen: int) -> None:
		self.control.SetVolume(max(0, min(100, int(volumen))) / 100)

	def fijar_velocidad(self, velocidad: float) -> bool:
		try:
			return bool(self.control.SetPlaybackRate(float(velocidad)))
		except Exception:  # noqa: BLE001 - el motor puede no admitirlo
			log.debug("SetPlaybackRate falló", exc_info=True)
			return False

	def cerrar(self) -> None:
		self.detener()
		if self._al_cerrar is not None:
			self._al_cerrar()


def crear_control() -> tuple[Any, Callable[[MotorWindows], None], Callable[[], None]]:
	"""Crea el ``MediaCtrl`` real en una ventana oculta [interfaz].

	Devuelve el control, la función que engancha sus eventos a un motor y la que
	destruye la ventana oculta.
	"""
	import wx
	import wx.media

	oculta = wx.Frame(None, title="zCommander: reproductor", style=wx.FRAME_NO_TASKBAR)
	control = wx.media.MediaCtrl(oculta, szBackend=wx.media.MEDIABACKEND_WMP10)

	def enganchar(motor: MotorWindows) -> None:
		control.Bind(wx.media.EVT_MEDIA_LOADED, lambda _e: motor.evento_cargado())
		control.Bind(wx.media.EVT_MEDIA_FINISHED, lambda _e: motor.evento_terminado())

	def destruir() -> None:
		if oculta:
			oculta.Destroy()

	return control, enganchar, destruir


class MotorFfplay:
	"""``ffplay`` sin ventana como proceso aparte; se relanza con ``-ss`` para pausar y saltar."""

	nombre = "FFplay"
	admite_velocidad = False

	def __init__(self, ejecutable: Callable[[], str], ejecutar: Callable[..., Any], duracion_de: Callable[[str], float],
			planificar: Callable[[Callable[[], None]], None]) -> None:
		"""
		:param ejecutable: devuelve la ruta de ``ffplay.exe`` (se pide en cada uso, 6.3).
		:param ejecutar: ``zc.ejecutar_programa`` (bloquea: se llama en un hilo propio).
		:param duracion_de: segundos de un archivo (``ffprobe``), en un hilo.
		:param planificar: pasa una función al hilo de la interfaz.
		"""
		self._ejecutable = ejecutable
		self._ejecutar = ejecutar
		self._duracion_de = duracion_de
		self._planificar = planificar
		self.al_cargado: Callable[[], None] | None = None
		self.al_terminar: Callable[[], None] | None = None
		self.al_error: Callable[[str], None] | None = None
		self._ruta = ""
		self._duracion = 0.0
		self._base = 0.0
		self._inicio: float | None = None
		self._volumen = 80
		self._estado = DETENIDO
		self._cancelar: threading.Event | None = None
		self._lanzamiento = 0
		self._candado = threading.Lock()

	def argumentos(self, posicion: float) -> list[str]:
		"""Lista de argumentos de ffplay (sin shell; la ruta del archivo, la última)."""
		return [str(self._ejecutable()), "-nodisp", "-autoexit", "-loglevel", "error", "-volume", str(self._volumen),
			"-ss", f"{max(0.0, posicion):.2f}", "-i", self._ruta]

	def cargar(self, ruta: str) -> bool:
		self._parar_proceso()
		self._ruta = ruta
		self._base = 0.0
		self._duracion = 0.0
		self._estado = DETENIDO

		def medir() -> None:
			try:
				duracion = float(self._duracion_de(ruta))
			except Exception:  # noqa: BLE001 - sin duración se reproduce igual
				log.debug("No se pudo medir %s con ffprobe", ruta, exc_info=True)
				duracion = 0.0

			def listo() -> None:
				if self._ruta == ruta:
					self._duracion = duracion
					if self.al_cargado is not None:
						self.al_cargado()

			self._planificar(listo)

		threading.Thread(target=medir, name="zc-reproductor-ffprobe", daemon=True).start()
		return True

	def _parar_proceso(self) -> None:
		with self._candado:
			self._lanzamiento += 1
			if self._cancelar is not None:
				self._cancelar.set()
				self._cancelar = None

	def _lanzar(self) -> None:
		self._parar_proceso()
		with self._candado:
			lanzamiento = self._lanzamiento
			cancelar = threading.Event()
			self._cancelar = cancelar
		argumentos = self.argumentos(self._base)
		self._inicio = time.monotonic()
		tiempo = max(60.0, (self._duracion - self._base) * 1.5 + 60) if self._duracion > 0 else 24 * 3600.0

		def trabajo() -> None:
			try:
				resultado = self._ejecutar(argumentos, tiempo_s=tiempo, cancelacion=cancelar.is_set)
			except Exception as error:  # noqa: BLE001 - se informa en la interfaz
				log.warning("ffplay no se pudo lanzar", exc_info=True)
				mensaje = str(error)
				self._planificar(lambda: self._fin(lanzamiento, False, mensaje))
				return
			if getattr(resultado, "cancelado", False) or cancelar.is_set():
				return
			errores = bytes(getattr(resultado, "errores", b"")).decode("utf-8", errors="replace").strip()
			ok = getattr(resultado, "codigo", 1) == 0
			self._planificar(lambda: self._fin(lanzamiento, ok, errores.splitlines()[-1] if errores else ""))

		threading.Thread(target=trabajo, name="zc-reproductor-ffplay", daemon=True).start()

	def _fin(self, lanzamiento: int, ok: bool, mensaje: str) -> None:
		if lanzamiento != self._lanzamiento:
			return
		self._estado = DETENIDO
		self._inicio = None
		self._base = 0.0
		if ok:
			if self.al_terminar is not None:
				self.al_terminar()
		elif self.al_error is not None:
			self.al_error(mensaje or "ffplay")

	def reproducir(self) -> None:
		self._estado = REPRODUCIENDO
		self._lanzar()

	def pausar(self) -> None:
		if self._estado != REPRODUCIENDO:
			return
		self._base = self.posicion()
		self._inicio = None
		self._parar_proceso()
		self._estado = PAUSADO

	def detener(self) -> None:
		self._parar_proceso()
		self._inicio = None
		self._base = 0.0
		self._estado = DETENIDO

	def estado(self) -> str:
		return self._estado

	def posicion(self) -> float:
		if self._estado == REPRODUCIENDO and self._inicio is not None:
			actual = self._base + (time.monotonic() - self._inicio)
			return min(actual, self._duracion) if self._duracion > 0 else actual
		return self._base

	def duracion(self) -> float:
		return self._duracion

	def ir_a(self, segundos: float) -> None:
		self._base = max(0.0, segundos)
		if self._estado == REPRODUCIENDO:
			self._lanzar()

	def fijar_volumen(self, volumen: int) -> None:
		self._volumen = max(0, min(100, int(volumen)))
		if self._estado == REPRODUCIENDO:
			self._base = self.posicion()
			self._lanzar()

	def fijar_velocidad(self, velocidad: float) -> bool:
		return abs(velocidad - 1.0) < 0.001

	def cerrar(self) -> None:
		self.detener()
