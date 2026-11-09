# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""¿Está en uso un componente? Esperar, detener o dejarlo para el reinicio (diseño 2.0, 6.6, paso 5). Sin wx.

- Los procesos se buscan SOLO entre los hijos de zCommander
  (``procesos.hijos_vivos``, el Job Object global): un rclone que la persona
  abrió por su cuenta no cuenta ni se toca.
- ``esperar_s``: cada uso es un proceso corto (7za, FFmpeg); se espera como
  mucho ese tiempo a que terminen.
- ``detener``: su dueño registró con ``zc.componentes.al_detener`` cómo pararlo
  cuando no hay trabajo en curso (rclone sin transferencias); si devuelve falso,
  no se puede ahora.
- ``al_reiniciar``: no se puede sustituir en caliente (DLL cargadas en el
  proceso, libarchive): siempre se deja para el reinicio.
"""

from __future__ import annotations

import builtins
import logging
import time
from collections.abc import Callable
from typing import Any

from app.core import procesos
from app.services.componentes import estado

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _cancelado(cancelacion: Any) -> bool:
	if cancelacion is None:
		return False
	for nombre in ("cancelado", "is_set"):
		valor = getattr(cancelacion, nombre, None)
		if valor is not None:
			return bool(valor() if callable(valor) else valor)
	return False


def procesos_vivos(ficha: dict, buscar: Callable[[str], list[int]] | None = None) -> list[int]:
	"""PID de los hijos de zCommander que usan el componente (por el nombre de su ejecutable)."""
	buscar = buscar or procesos.hijos_vivos
	vivos: list[int] = []
	for nombre in (ficha.get("en_uso") or {}).get("procesos", []):
		vivos.extend(buscar(str(nombre)))
	return vivos


def liberar(ficha: dict, *, cancelacion: Any = None, al_fase: Callable[[str], None] | None = None,
		buscar: Callable[[str], list[int]] | None = None, sondeo_s: float = 0.25) -> bool:
	"""Verdadero si el componente se puede sustituir ya; falso si hay que dejarlo para el reinicio."""
	en_uso = ficha.get("en_uso") or {}
	nombre = str(ficha.get("nombre") or ficha.get("id"))
	if en_uso.get("al_reiniciar"):
		log.info("%s se carga en el proceso: se aplicará al reiniciar", nombre)
		return False
	vivos = procesos_vivos(ficha, buscar)
	if not vivos:
		return True
	esperar = float(en_uso.get("esperar_s") or 0)
	if esperar > 0:
		if al_fase is not None:
			al_fase(_("Esperando a que termine {c}").format(c=nombre))
		limite = time.monotonic() + esperar
		while vivos and time.monotonic() < limite and not _cancelado(cancelacion):
			time.sleep(sondeo_s)
			vivos = procesos_vivos(ficha, buscar)
		if not vivos:
			return True
	if en_uso.get("detener"):
		funcion = estado.funcion_al_detener(str(ficha.get("id")))
		if funcion is None:
			log.info("%s está en uso y su dueño no registró cómo detenerlo", nombre)
			return False
		if al_fase is not None:
			al_fase(_("Deteniendo {c}").format(c=nombre))
		try:
			detenido = bool(funcion())
		except Exception:  # noqa: BLE001 - la función de un complemento no tumba la actualización
			log.exception("Falló la función al_detener de %s", nombre)
			return False
		if not detenido:
			log.info("%s tiene trabajo en curso: se aplicará al reiniciar", nombre)
			return False
		limite = time.monotonic() + 5
		while procesos_vivos(ficha, buscar) and time.monotonic() < limite:
			time.sleep(sondeo_s)
		return not procesos_vivos(ficha, buscar)
	return False
