# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Salida de voz y braille directa al lector de pantalla.

La voz es un COMPLEMENTO de la semántica accesible, no su sustituto: el
lector ya anuncia por su cuenta el foco, los nombres, los roles y los estados
de los controles nativos. Solo se habla desde la aplicación cuando el lector
no puede saberlo (lectura lógica por columnas, resultado de una acción,
cambios en segundo plano).

Características:

- ``accessible_output2`` (NVDA, JAWS, Narrador/SAPI...) inicializado de forma
  perezosa; sin él, los anuncios van al registro en DEBUG.
- Un único hilo trabajador con cola (no un hilo por anuncio).
- COALESCENCIA: si llegan varios anuncios interrumpibles seguidos (navegación
  rápida), solo se dice el último. Los aditivos nunca se descartan.
- Retardo configurable (0-600 ms) antes de los interrumpibles, para que el
  mensaje llegue DESPUÉS del anuncio automático de foco del lector y lo gane.
- CANALES con interruptor propio: ``"navegacion"`` (lo que el usuario pide
  explícitamente: columnas, Ctrl+H) y ``"avisos"`` (eventos del sistema,
  progreso). Desactivar los avisos no deja muda la lectura de listas.
- Historial de los últimos 200 anuncios (repetir el último, consultarlos).
- Braille opcional (mismo texto a la línea braille).

PLANTILLA del agente «accesibilidad-wx».
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

log = logging.getLogger(__name__)

NAVEGACION = "navegacion"
AVISOS = "avisos"

_salida = None
_salida_intentada = False
_candado_salida = threading.Lock()

_cola: queue.Queue[_Anuncio | None] = queue.Queue()
_hilo: threading.Thread | None = None
_candado_hilo = threading.Lock()

_config = {
	"activada": True,      # interruptor general
	"silencio": False,     # modo «No molestar» temporal
	"retraso_ms": 120,
	"braille": True,
	"canales": {NAVEGACION: True, AVISOS: True},
}

_historial: deque[tuple[float, str]] = deque(maxlen=200)
_candado_historial = threading.Lock()


@dataclass
class _Anuncio:
	texto: str
	interrumpir: bool
	canal: str = AVISOS


# ── Configuración ─────────────────────────────────────────────────────────────

def configurar(
	activada: bool | None = None,
	retraso_ms: int | None = None,
	braille: bool | None = None,
	navegacion: bool | None = None,
	avisos: bool | None = None,
) -> None:
	"""Aplica las preferencias de voz (llamar al arrancar y al Aceptar/Aplicar Preferencias)."""
	if activada is not None:
		_config["activada"] = bool(activada)
	if retraso_ms is not None:
		_config["retraso_ms"] = max(0, min(2000, int(retraso_ms)))
	if braille is not None:
		_config["braille"] = bool(braille)
	if navegacion is not None:
		_config["canales"][NAVEGACION] = bool(navegacion)
	if avisos is not None:
		_config["canales"][AVISOS] = bool(avisos)


def silenciar(valor: bool) -> None:
	"""Activa o desactiva el silencio temporal («No molestar»)."""
	_config["silencio"] = bool(valor)


def esta_silenciado() -> bool:
	"""Indica si el silencio temporal está activo."""
	return bool(_config["silencio"])


def ultimo_anuncio() -> str:
	"""Texto del último anuncio (para una orden «repetir último mensaje»)."""
	with _candado_historial:
		return _historial[-1][1] if _historial else ""


def historial() -> list[tuple[float, str]]:
	"""Copia del historial (marca de tiempo, texto)."""
	with _candado_historial:
		return list(_historial)


# ── Salida ────────────────────────────────────────────────────────────────────

# Modo de salida («automatica», «lector», «uia», «ninguna») y SAPI sin lector.
_config["salida"] = "automatica"
_config["sapi_sin_lector"] = False
_salidas: dict[str, object] = {}


def configurar_salida(modo: str = "automatica", sapi_sin_lector: bool = False) -> None:
	"""Elige por dónde salen los anuncios (preferencias ``accesibilidad.salida_voz`` y ``sapi_sin_lector``).

	- «automatica»: NVDA o JAWS por accessible_output2; Narrador por notificaciones UIA.
	- «lector»: siempre accessible_output2 (el lector que detecte).
	- «uia»: siempre notificaciones UIA (Narrador, NVDA).
	- «ninguna»: solo el historial.
	"""
	_config["salida"] = modo
	_config["sapi_sin_lector"] = bool(sapi_sin_lector)


#: Las únicas salidas de accessible_output2 que se crean (2.0, 2.3 y 15.4): ninguna
#: necesita las DLL no libres (System Access, Dolphin, PC-Talker, Zhengdu), que la
#: compilación no lleva. Los demás lectores van por notificaciones UIA.
SALIDAS_AO2 = ("nvda", "jaws", "sapi5")


def _salida_ao2(nombre: str):
	"""Salida concreta de accessible_output2 (nvda, jaws, sapi5), creada una sola vez."""
	with _candado_salida:
		if nombre in _salidas:
			return _salidas[nombre]
		salida = None
		try:
			if nombre == "nvda":
				from accessible_output2.outputs.nvda import NVDA as Clase
			elif nombre == "jaws":
				from accessible_output2.outputs.jaws import Jaws as Clase
			elif nombre == "sapi5":
				from accessible_output2.outputs.sapi5 import SAPI5 as Clase
			else:
				log.warning("Salida de voz desconocida: %s", nombre)
				_salidas[nombre] = None
				return None
			salida = Clase()
			log.info("Salida de voz: %s (accessible_output2).", nombre)
		except Exception:  # noqa: BLE001 - accessible_output2 lanza tipos variados
			log.warning("No se pudo iniciar la salida de voz %s.", nombre, exc_info=True)
		_salidas[nombre] = salida
		return salida


def _obtener_salida():
	"""Salida adecuada al lector que hay ahora (se recalcula cada pocos segundos)."""
	from app.ui.accesibilidad import uia

	modo = _config["salida"]
	if modo == "ninguna":
		return None
	if modo == "uia":
		return "uia"
	lector = uia.lector_activo()
	if lector in ("nvda", "jaws"):
		return _salida_ao2(lector)
	if lector in ("narrador", "otro"):
		# Narrador y lectores que accessible_output2 no conoce: notificaciones UIA
		# (sin las DLL no libres de otros lectores, 2.3).
		return "uia"
	return _salida_ao2("sapi5") if _config["sapi_sin_lector"] else None


def _emitir(texto: str, interrumpir: bool, canal: str = AVISOS) -> None:
	salida = _obtener_salida()
	if salida is None:
		log.debug("[voz] %s", texto)
		return
	if salida == "uia":
		from app.ui.accesibilidad import uia

		try:
			import wx

			# UIA se lanza desde el hilo de la interfaz, dueño de la ventana.
			wx.CallAfter(uia.notificar, texto, interrumpir, 0, f"zCommander.{canal}")
		except Exception:  # noqa: BLE001 - sin wx (pruebas), se intenta directo
			uia.notificar(texto, interrumpir, actividad=f"zCommander.{canal}")
		return
	try:
		salida.speak(texto, interrupt=interrumpir)
		if _config["braille"] and hasattr(salida, "braille"):
			try:
				salida.braille(texto)
			except Exception:  # noqa: BLE001 - no todos los lectores/salidas admiten braille
				log.debug("La salida activa no admite braille.", exc_info=True)
	except Exception:
		log.exception("Error al enviar un anuncio al lector de pantalla.")


def _trabajador() -> None:
	while True:
		anuncio = _cola.get()
		if anuncio is None:
			return
		# Coalescencia: entre interrumpibles seguidos gana el último. Si detrás
		# llega uno aditivo, se dice primero el interrumpible pendiente y luego
		# el aditivo: ninguno de los dos se pierde.
		while anuncio.interrumpir:
			try:
				siguiente = _cola.get_nowait()
			except queue.Empty:
				break
			if siguiente is None:
				return
			if not siguiente.interrumpir:
				_emitir(anuncio.texto, True, anuncio.canal)
				anuncio = siguiente
				break
			anuncio = siguiente
		if anuncio.interrumpir and _config["retraso_ms"] > 0:
			time.sleep(_config["retraso_ms"] / 1000.0)
		_emitir(anuncio.texto, anuncio.interrumpir, anuncio.canal)


def _asegurar_hilo() -> None:
	global _hilo
	with _candado_hilo:
		if _hilo is None or not _hilo.is_alive():
			_hilo = threading.Thread(target=_trabajador, name="voz", daemon=True)
			_hilo.start()


def hablar(texto: str, interrumpir: bool = True, canal: str = AVISOS, sincrono: bool = False, forzar: bool = False) -> None:
	"""Anuncia ``texto`` por el lector de pantalla activo.

	:param interrumpir: corta lo que el lector esté diciendo (lo habitual).
		Use ``False`` para mensajes que no deben pisar a otros (resultado de
		una tarea larga mientras el usuario lee).
	:param canal: ``NAVEGACION`` para lo que el usuario pide explícitamente
		(columnas, ayuda Ctrl+H); ``AVISOS`` para eventos del sistema.
	:param sincrono: habla en el hilo actual sin cola ni retardo. Solo para el
		aviso de arranque ANTES de las importaciones pesadas (si fuera por la
		cola, el hilo de voz no conseguiría el GIL hasta el final).
	"""
	texto = (texto or "").strip()
	if not texto:
		return
	# ``forzar``: avisos esenciales (decisiones pendientes, errores) que no se pueden silenciar.
	if not forzar and (not _config["activada"] or _config["silencio"]):
		return
	if not _config["canales"].get(canal, True):
		log.debug("[voz desactivada en el canal %s] %s", canal, texto)
		return
	with _candado_historial:
		_historial.append((time.time(), texto))
	if sincrono:
		_emitir(texto, interrumpir, canal)
		return
	_asegurar_hilo()
	_cola.put(_Anuncio(texto, interrumpir, canal))


def detener() -> None:
	"""Detiene el hilo de voz al cerrar la aplicación."""
	global _hilo
	with _candado_hilo:
		if _hilo is not None and _hilo.is_alive():
			_cola.put(None)
			_hilo.join(timeout=2)
		_hilo = None
