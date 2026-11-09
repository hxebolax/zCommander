# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Archivos temporales dentro de ``data/temp`` (nunca en %TEMP%: la aplicación es portable)."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)


def carpeta_temporal() -> Path:
	"""``data/temp/extraidos`` (se crea si no existe).

	Subcarpeta propia: ``data/temp/instancia`` es el buzón de la instancia única
	y nunca se toca desde aquí.
	"""
	carpeta = paths.ruta_temporales() / "extraidos"
	carpeta.mkdir(parents=True, exist_ok=True)
	return carpeta


def ruta_temporal(nombre: str) -> str:
	"""Ruta libre ``data/temp/<único>/<nombre>``: conserva el nombre para que el programa asociado lo reconozca."""
	carpeta = carpeta_temporal() / uuid.uuid4().hex[:12]
	carpeta.mkdir(parents=True, exist_ok=True)
	nombre = nombre.replace("/", "_").replace("\\", "_") or "archivo"
	return str(carpeta / nombre)


def borrar(ruta: str) -> None:
	"""Borra un temporal y su carpeta única si queda vacía."""
	try:
		os.remove(ruta)
	except FileNotFoundError:
		pass
	except OSError:
		log.debug("No se pudo borrar el temporal %s (quizá sigue abierto)", ruta, exc_info=True)
		return
	try:
		os.rmdir(os.path.dirname(ruta))
	except OSError:
		log.debug("La carpeta del temporal %s no estaba vacía", ruta, exc_info=True)


class Vigilados:
	"""Temporales abiertos con un programa externo (Intro con asociación, visor o editor externos).

	La ventana principal llama a ``revisar()`` cada vez que recupera el foco:
	si la fecha de un temporal cambió, avisa con ``al_cambiar(ruta_local,
	proveedor, ruta)`` para ofrecer «¿Actualizar en el comprimido o en el
	servidor?». Los temporales se borran al salir y al arrancar (no se sabe
	cuándo cierra el programa externo); los del visor interno, al cerrarlo.
	"""

	def __init__(self) -> None:
		self._lista: dict[str, tuple[float, object, str, object]] = {}

	def vigilar(self, ruta_local: str, proveedor, ruta: str, al_cambiar) -> None:
		try:
			marca = os.path.getmtime(ruta_local)
		except OSError:
			return
		self._lista[ruta_local] = (marca, proveedor, ruta, al_cambiar)

	def revisar(self) -> None:
		for ruta_local, (marca, proveedor, ruta, al_cambiar) in list(self._lista.items()):
			try:
				actual = os.path.getmtime(ruta_local)
			except OSError:
				del self._lista[ruta_local]
				continue
			if actual > marca + 1:
				self._lista[ruta_local] = (actual, proveedor, ruta, al_cambiar)
				al_cambiar(ruta_local, proveedor, ruta)


vigilados = Vigilados()


def limpiar_todo() -> None:
	"""Vacía ``data/temp/extraidos`` y las listas de ``%L`` (al arrancar: restos de una sesión que terminó de golpe)."""
	carpeta = carpeta_temporal()
	for hijo in carpeta.iterdir():
		try:
			if hijo.is_dir():
				shutil.rmtree(hijo)
			else:
				hijo.unlink()
		except OSError:
			log.debug("No se pudo limpiar %s", hijo, exc_info=True)
	# Listas de la variable %L del menú de usuario (data/temp/zc_lista_*.txt).
	for lista in carpeta.parent.glob("zc_lista_*.txt"):
		try:
			lista.unlink()
		except OSError:
			log.debug("No se pudo borrar %s", lista, exc_info=True)
