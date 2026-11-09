# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lectura tolerante y escritura atómica de archivos JSON en ``data/config``.

Lo usan la sesión, los favoritos, el menú de usuario, las asociaciones, las
conexiones y demás archivos auxiliares. Mismo criterio que la configuración
(plantilla del agente de configuración): nunca perder datos.

- Escritura atómica: temporal único en la misma carpeta, ``fsync`` y
  ``os.replace`` con reintentos (el antivirus puede tener el archivo abierto).
- Copia ``.bak`` del archivo anterior.
- Un archivo dañado se aparta como ``nombre.corrupto-AAAAMMDD-HHMMSS``, se
  intenta el ``.bak`` y, si tampoco vale, se devuelve el valor por defecto.
- Todos los archivos llevan ``"version"``: quien lo lee decide si migra.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from app.core import paths

log = logging.getLogger(__name__)

_candado = threading.Lock()


def ruta(nombre: str) -> Path:
	"""``data/config/<nombre>`` (``nombre`` incluye la extensión)."""
	return paths.ruta_configuracion() / nombre


def _reemplazar(origen: Path, destino: Path, intentos: int = 6) -> None:
	espera = 0.05
	for intento in range(1, intentos + 1):
		try:
			os.replace(origen, destino)
			return
		except PermissionError:
			if intento == intentos:
				raise
			log.debug("Reemplazo de %s bloqueado; reintento %d", destino.name, intento, exc_info=True)
			time.sleep(espera)
			espera *= 2


def _leer(archivo: Path) -> Any:
	with open(archivo, encoding="utf-8-sig") as entrada:
		return json.load(entrada)


def leer(nombre: str, por_defecto: Any, carpeta: Path | None = None) -> Any:
	"""Datos del archivo o una COPIA de ``por_defecto`` si no existe o está dañado.

	Si ``por_defecto`` es un diccionario, el resultado se completa con sus
	claves que falten (archivos de versiones anteriores siguen sirviendo).
	Nunca lanza excepciones por el contenido; sí registra lo que pasó.
	"""
	archivo = (carpeta or paths.ruta_configuracion()) / nombre
	if not archivo.exists():
		return copy.deepcopy(por_defecto)
	try:
		datos = _leer(archivo)
	except (OSError, ValueError) as error:
		log.warning("El archivo %s está dañado o no se puede leer; se prueba la copia .bak", archivo, exc_info=True)
		datos = None
		# Solo se aparta un archivo DAÑADO; uno que no se pudo leer (permisos)
		# se deja donde está para no perder los datos reales.
		if isinstance(error, ValueError):
			apartado = archivo.with_name(f"{archivo.name}.corrupto-{time.strftime('%Y%m%d-%H%M%S')}")
			try:
				os.replace(archivo, apartado)
			except OSError:
				log.debug("No se pudo apartar %s", archivo, exc_info=True)
		respaldo = archivo.with_name(archivo.name + ".bak")
		if respaldo.exists():
			try:
				datos = _leer(respaldo)
				log.info("Recuperado %s desde su copia .bak", archivo.name)
			except (OSError, ValueError):
				log.warning("La copia %s tampoco se puede leer", respaldo, exc_info=True)
				datos = None
		if datos is None:
			return copy.deepcopy(por_defecto)
	if isinstance(por_defecto, dict):
		if not isinstance(datos, dict):
			log.warning("%s no tiene la forma esperada; se usan los valores por defecto", archivo)
			return copy.deepcopy(por_defecto)
		completo = copy.deepcopy(por_defecto)
		completo.update(datos)
		return completo
	if isinstance(por_defecto, list) and not isinstance(datos, list):
		log.warning("%s no tiene la forma esperada; se usa la lista por defecto", archivo)
		return copy.deepcopy(por_defecto)
	return datos


def escribir(nombre: str, datos: Any, carpeta: Path | None = None) -> None:
	"""Escribe ``datos`` de forma atómica y deja ``.bak`` del anterior.

	:raises OSError: si no se pudo escribir (disco lleno, permisos). Quien
		llama decide si avisa a la persona.
	"""
	destino_carpeta = carpeta or paths.ruta_configuracion()
	archivo = destino_carpeta / nombre
	texto = json.dumps(datos, ensure_ascii=False, indent=2)
	with _candado:
		destino_carpeta.mkdir(parents=True, exist_ok=True)
		temporal = destino_carpeta / f"{nombre}.{os.getpid()}-{threading.get_ident()}.tmp"
		try:
			with open(temporal, "w", encoding="utf-8", newline="\n") as salida:
				salida.write(texto)
				salida.flush()
				os.fsync(salida.fileno())
			if archivo.exists():
				try:
					shutil.copy2(archivo, archivo.with_name(archivo.name + ".bak"))
				except OSError:
					log.warning("No se pudo actualizar la copia .bak de %s", archivo, exc_info=True)
			_reemplazar(temporal, archivo)
		except OSError:
			try:
				temporal.unlink(missing_ok=True)
			except OSError:
				log.debug("No se pudo borrar el temporal %s", temporal, exc_info=True)
			log.error("No se pudo guardar %s", archivo, exc_info=True)
			raise
