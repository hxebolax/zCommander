# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Señales para el complemento de zCommander para NVDA (diseño 2.0, 10.5 y 10.16).

Pequeño y completo desde N2. zCommander publica dos propiedades de ventana
(``SetPropW``) que lee el appModule de NVDA (bloque NV):

- ``zCommander.MovimientoSilencioso``: la hora (milisegundos de
  ``GetTickCount``) en que zCommander va a mover el foco por su cuenta; el
  appModule no anuncia ese foco si la marca tiene menos de 500 ms.
- ``zCommander.OrdenLectura``: el orden de lectura de las columnas, un entero
  de 64 bits con un índice de columna de 4 bits por posición, de la menos
  significativa a la más, terminado en ``0xF``. Como mucho 15 columnas (15
  posiciones de 4 bits más el terminador), con índices de 0 a 14.

Sin el complemento de NVDA nadie lee estas propiedades y todo funciona igual.
"""

from __future__ import annotations

import ctypes
import logging
from collections.abc import Sequence

log = logging.getLogger(__name__)

PROPIEDAD_SILENCIO = "zCommander.MovimientoSilencioso"
PROPIEDAD_LECTURA = "zCommander.OrdenLectura"
MAX_COLUMNAS = 15
TERMINADOR = 0xF

_activo = [True]


def configurar(silencio_nvda: bool) -> None:
	"""``accesibilidad.silencio_nvda``: si se marca o no el movimiento silencioso."""
	_activo[0] = bool(silencio_nvda)


def codificar_orden(indices: Sequence[int]) -> int:
	"""``[0, 3, 1]`` → ``0xF130``: 4 bits por posición, la primera en los bits bajos, y el terminador."""
	indices = list(indices)
	if len(indices) > MAX_COLUMNAS:
		raise ValueError(f"Como mucho {MAX_COLUMNAS} columnas se leen al moverse")
	valor = 0
	for posicion, indice in enumerate(indices):
		if not 0 <= int(indice) < TERMINADOR:
			raise ValueError(f"Índice de columna fuera de rango: {indice}")
		valor |= int(indice) << (4 * posicion)
	return valor | (TERMINADOR << (4 * len(indices)))


def decodificar_orden(valor: int) -> list[int]:
	"""El inverso de ``codificar_orden`` (lo usa la prueba; el appModule hace lo mismo)."""
	indices = []
	for posicion in range(MAX_COLUMNAS + 1):
		parte = (valor >> (4 * posicion)) & 0xF
		if parte == TERMINADOR:
			return indices
		indices.append(parte)
	raise ValueError("Orden de lectura sin terminador")


def _fijar_propiedad(hwnd: int, nombre: str, valor: int) -> bool:
	try:
		user32 = ctypes.windll.user32
		user32.SetPropW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p)
		user32.SetPropW.restype = ctypes.c_bool
		return bool(user32.SetPropW(ctypes.c_void_p(int(hwnd)), nombre, ctypes.c_void_p(int(valor) & 0xFFFFFFFFFFFFFFFF)))
	except Exception:  # noqa: BLE001 - sin la propiedad, el complemento de NVDA se comporta como sin zCommander
		log.debug("No se pudo fijar la propiedad %s", nombre, exc_info=True)
		return False


def leer_propiedad(hwnd: int, nombre: str) -> int:
	"""Valor de una propiedad de ventana (0 si no está). Para pruebas y diagnóstico."""
	try:
		user32 = ctypes.windll.user32
		user32.GetPropW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
		user32.GetPropW.restype = ctypes.c_void_p
		return int(user32.GetPropW(ctypes.c_void_p(int(hwnd)), nombre) or 0)
	except Exception:  # noqa: BLE001
		log.debug("No se pudo leer la propiedad %s", nombre, exc_info=True)
		return 0


def _ahora_ms() -> int:
	try:
		return int(ctypes.windll.kernel32.GetTickCount64())
	except Exception:  # noqa: BLE001 - fuera de Windows
		import time

		return int(time.monotonic() * 1000)


def marcar_movimiento_silencioso(hwnd: int) -> None:
	"""Marca con la hora que el próximo cambio de foco lo hace zCommander por su cuenta."""
	if not _activo[0] or not hwnd:
		return
	_fijar_propiedad(hwnd, PROPIEDAD_SILENCIO, _ahora_ms() or 1)


def publicar_orden_lectura(hwnd: int, indices: Sequence[int]) -> None:
	"""Publica el orden de lectura de las columnas de una lista (como mucho 15)."""
	if not hwnd:
		return
	_fijar_propiedad(hwnd, PROPIEDAD_LECTURA, codificar_orden(list(indices)[:MAX_COLUMNAS]))
