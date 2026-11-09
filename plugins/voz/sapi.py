# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Voces de Windows por SAPI 5 (pywin32, del contrato de bibliotecas de la API). Sin wx.

- ``VozSapi``: lectura en vivo. El objeto COM vive en un hilo propio
  (``zc-voz``) que recibe órdenes por una cola: hablar una frase, pausar,
  continuar, callar y ajustes. Así la interfaz nunca espera a la voz, y COM se
  usa siempre desde el hilo que lo creó.
- ``exportar_wav``: escribe un WAV con ``SAPI.SpFileStream`` (bloquea; se llama
  en el hilo de la operación, con su propio COM).
- Voces: las de SAPI 5 y, si las hay, las de OneCore (Windows 10 y 11), que SAPI
  puede usar leyendo su categoría del registro.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass

log = logging.getLogger(__name__)

SVSF_ASINCRONO, SVSF_PURGAR, SVSF_XML = 1, 2, 8
SSFM_CREAR_ESCRITURA = 3
#: SpeechAudioFormatType: 22 kHz, 16 bits, mono (voz clara y archivos pequeños).
SAFT_22KHZ_16BIT_MONO = 22
CATEGORIA_ONECORE = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"


@dataclass(frozen=True)
class Ajustes:
	voz: str = ""
	velocidad: int = 0
	tono: int = 0
	volumen: int = 100


def _tokens(sapi: object) -> list[object]:
	"""Fichas de voz: las de SAPI 5 y las de OneCore (si la categoría existe)."""
	import win32com.client

	fichas = []
	coleccion = sapi.GetVoices()
	fichas.extend(coleccion.Item(i) for i in range(coleccion.Count))
	try:
		categoria = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
		categoria.SetId(CATEGORIA_ONECORE, False)
		onecore = categoria.EnumerateTokens()
		vistas = {f.GetDescription() for f in fichas}
		fichas.extend(onecore.Item(i) for i in range(onecore.Count) if onecore.Item(i).GetDescription() not in vistas)
	except Exception:  # noqa: BLE001 - sin OneCore quedan las voces de SAPI 5
		log.debug("No hay voces OneCore", exc_info=True)
	return fichas


def _aplicar(sapi: object, ajustes: Ajustes) -> None:
	sapi.Rate = max(-10, min(10, int(ajustes.velocidad)))
	sapi.Volume = max(0, min(100, int(ajustes.volumen)))
	if ajustes.voz:
		for ficha in _tokens(sapi):
			if ficha.GetDescription().casefold() == ajustes.voz.casefold():
				try:
					sapi.Voice = ficha
				except Exception:  # noqa: BLE001 - una voz OneCore que SAPI no admite: se queda la predeterminada
					log.warning("SAPI no puede usar la voz %s; se usa la predeterminada", ajustes.voz, exc_info=True)
				return
		log.info("No se encuentra la voz %s; se usa la predeterminada", ajustes.voz)


def voces() -> list[str]:
	"""Nombres de las voces instaladas (SAPI 5 y OneCore). [cualquiera: crea su propio COM]."""
	import pythoncom
	import win32com.client

	pythoncom.CoInitialize()
	try:
		sapi = win32com.client.Dispatch("SAPI.SpVoice")
		fichas = _tokens(sapi)
		nombres = [f.GetDescription() for f in fichas]
		# Los objetos COM se sueltan ANTES de CoUninitialize: soltarlos después rompe el proceso.
		del fichas, sapi
		return nombres
	finally:
		pythoncom.CoUninitialize()


class VozSapi:
	"""Voz en vivo. ``hablar`` llama a ``al_terminar(numero)`` (por ``planificar``) cuando acaba la frase."""

	def __init__(self, planificar: Callable[[Callable[[], None]], None], ajustes: Ajustes) -> None:
		self._planificar = planificar
		self._cola: queue.Queue = queue.Queue()
		self._ajustes = ajustes
		self._hilo = threading.Thread(target=self._bucle, name="zc-voz", daemon=True)
		self._hilo.start()

	def hablar(self, texto: str, numero: int, al_terminar: Callable[[int], None]) -> None:
		self._cola.put(("hablar", (texto, numero, al_terminar)))

	def pausar(self) -> None:
		self._cola.put(("pausar", None))

	def continuar(self) -> None:
		self._cola.put(("continuar", None))

	def callar(self) -> None:
		self._cola.put(("callar", None))

	def fijar(self, ajustes: Ajustes) -> None:
		self._ajustes = ajustes
		self._cola.put(("ajustes", ajustes))

	def cerrar(self) -> None:
		self._cola.put(("salir", None))

	@property
	def tono(self) -> int:
		return self._ajustes.tono

	def _bucle(self) -> None:
		import pythoncom
		import win32com.client

		pythoncom.CoInitialize()
		try:
			sapi = win32com.client.Dispatch("SAPI.SpVoice")
			_aplicar(sapi, self._ajustes)
		except Exception:  # noqa: BLE001 - sin SAPI no hay lectura: se dice al hablar
			log.error("No se pudo crear la voz de SAPI", exc_info=True)
			sapi = None
		pendiente: tuple[int, Callable[[int], None]] | None = None
		pausada = False
		try:
			while True:
				try:
					orden, datos = self._cola.get(timeout=0.05)
				except queue.Empty:
					orden, datos = "", None
				if orden == "salir":
					if sapi is not None:
						sapi.Speak("", SVSF_ASINCRONO | SVSF_PURGAR)
					sapi = None
					return
				if sapi is None:
					if orden == "hablar":
						_texto, numero, aviso = datos
						self._planificar(lambda n=numero, a=aviso: a(-1 - n))
					continue
				if orden == "hablar":
					texto, numero, aviso = datos
					if pausada:
						sapi.Resume()
						pausada = False
					sapi.Speak(texto, SVSF_ASINCRONO | SVSF_PURGAR | SVSF_XML)
					pendiente = (numero, aviso)
				elif orden == "pausar" and not pausada:
					sapi.Pause()
					pausada = True
				elif orden == "continuar" and pausada:
					sapi.Resume()
					pausada = False
				elif orden == "callar":
					if pausada:
						sapi.Resume()
						pausada = False
					sapi.Speak("", SVSF_ASINCRONO | SVSF_PURGAR)
					pendiente = None
				elif orden == "ajustes":
					_aplicar(sapi, datos)
				if pendiente is not None and not pausada and sapi.WaitUntilDone(0):
					numero, aviso = pendiente
					pendiente = None
					self._planificar(lambda n=numero, a=aviso: a(n))
		finally:
			sapi = None
			pythoncom.CoUninitialize()


def exportar_wav(textos: Iterable[str], ruta: str, ajustes: Ajustes, cancelado: Callable[[], bool],
		al_avanzar: Callable[[int], None] | None = None) -> bool:
	"""Escribe los textos (XML de SAPI) en un WAV. Falso si se canceló (el archivo queda a medias: lo borra quien llama)."""
	import pythoncom
	import win32com.client

	pythoncom.CoInitialize()
	try:
		sapi = win32com.client.Dispatch("SAPI.SpVoice")
		_aplicar(sapi, ajustes)
		flujo = win32com.client.Dispatch("SAPI.SpFileStream")
		formato = win32com.client.Dispatch("SAPI.SpAudioFormat")
		formato.Type = SAFT_22KHZ_16BIT_MONO
		flujo.Format = formato
		flujo.Open(ruta, SSFM_CREAR_ESCRITURA, False)
		try:
			sapi.AudioOutputStream = flujo
			for numero, texto in enumerate(textos):
				if cancelado():
					return False
				sapi.Speak(texto, SVSF_XML)
				if al_avanzar is not None:
					al_avanzar(numero)
		finally:
			flujo.Close()
		return True
	finally:
		# Los objetos COM se sueltan ANTES de CoUninitialize: soltarlos después rompe el proceso.
		sapi = flujo = formato = None
		pythoncom.CoUninitialize()
