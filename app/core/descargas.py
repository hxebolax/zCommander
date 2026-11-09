# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Descargas reanudables y verificadas (diseño 2.0, 0.3 y 14.9).

Parte de ``_abrir`` y ``descargar`` de la plantilla del actualizador (solo
biblioteca estándar): se descarga a ``<destino>.parcial``, se reanuda con
``Range`` si el servidor lo admite (y se empieza de cero con un 416), nunca se
escribe más del tamaño anunciado y, si se da, se comprueba el SHA-256 antes de
dejar el archivo con su nombre final. El actualizador (AC), los componentes
(CO) y la fachada ``zc.red`` de los complementos usan esta única implementación.
"""

from __future__ import annotations

import builtins
import hashlib
import http.client
import logging
import os
import urllib.error
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core import red

log = logging.getLogger(__name__)

BLOQUE = 64 * 1024
MAX_SIN_TAMANO = 4 * 1024**3


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


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


def sha256_de(ruta: Path) -> str:
	suma = hashlib.sha256()
	with Path(ruta).open("rb") as archivo:
		for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
			suma.update(bloque)
	return suma.hexdigest()


def _nombre_desde_url(url: str) -> str:
	nombre = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
	return nombre or "descarga"


def descargar(config: red.ConfiguracionRed, url: str, destino: Path, *, sha256: str = "", tamano: int = -1,
		cancelacion: Any = None, al_progresar: Callable[[int, int], None] | None = None) -> Path:
	"""Descarga ``url`` a ``destino`` (archivo final, o carpeta existente: el nombre sale de la URL).

	:param sha256: suma esperada en hexadecimal; si no coincide, se borra y se lanza ``ErrorHTTP``.
	:param tamano: tamaño esperado (−1 si no se sabe): nunca se escribe más.
	:param al_progresar: ``(hechos, total)``, con total −1 si no se sabe.
	:return: la ruta del archivo final.
	"""
	destino = Path(destino)
	final = destino / _nombre_desde_url(url) if destino.is_dir() else destino
	final.parent.mkdir(parents=True, exist_ok=True)
	parcial = final.with_name(final.name + ".parcial")
	tope = tamano if tamano >= 0 else MAX_SIN_TAMANO
	inicio = parcial.stat().st_size if parcial.is_file() else 0
	if 0 <= tamano < inicio:
		parcial.unlink()
		inicio = 0
	if not (tamano >= 0 and inicio == tamano):
		cabeceras = {"Range": f"bytes={inicio}-"} if inicio else {}
		try:
			respuesta = red.abrir(config, url, cabeceras=cabeceras, tiempo_s=config.tiempo_lectura)
		except urllib.error.HTTPError as error:
			if error.code == 416 and inicio:
				log.info("El servidor no acepta reanudar desde %d; se empieza de cero", inicio)
				parcial.unlink(missing_ok=True)
				return descargar(config, url, destino, sha256=sha256, tamano=tamano, cancelacion=cancelacion, al_progresar=al_progresar)
			info = red.clasificar_error(error)
			raise red.ErrorHTTP(red.HTTP, info.mensaje, error.code) from error
		with respuesta:
			reanudada = bool(inicio) and respuesta.status == 206 and str(
				respuesta.headers.get("Content-Range", "")).startswith(f"bytes {inicio}-")
			if inicio and not reanudada:
				log.info("El servidor no admite reanudar; se descarga completo")
				inicio = 0
			total = tamano
			if total < 0:
				longitud = respuesta.headers.get("Content-Length")
				if longitud and str(longitud).isdigit():
					total = int(longitud) + inicio
			hecho = inicio
			log.info("Descargando %s desde el byte %d", red.redactar_url(url), inicio)
			with parcial.open("ab" if reanudada else "wb") as salida:
				while True:
					if _cancelado(cancelacion):
						raise red.ErrorHTTP(red.CANCELADO, _("Descarga cancelada. Podrá continuarla más tarde."))
					try:
						bloque = respuesta.read(BLOQUE)
					except (http.client.HTTPException, TimeoutError, OSError) as error:
						raise red.ErrorHTTP(red.CONEXION, _("La descarga se interrumpió. Vuelva a intentarlo: continuará donde se quedó.")) from error
					if not bloque:
						break
					hecho += len(bloque)
					if hecho > tope:
						salida.close()
						parcial.unlink(missing_ok=True)
						raise red.ErrorHTTP(red.HTTP, _("Lo descargado es mayor de lo anunciado; se descarta por seguridad."))
					salida.write(bloque)
					if al_progresar is not None:
						al_progresar(hecho, total)
		if tamano >= 0 and hecho < tamano:
			raise red.ErrorHTTP(red.CONEXION, _("La descarga se interrumpió. Vuelva a intentarlo: continuará donde se quedó."))
	if sha256:
		obtenida = sha256_de(parcial)
		if obtenida.lower() != sha256.lower():
			parcial.unlink(missing_ok=True)
			log.warning("Suma SHA-256 distinta en %s: %s", red.redactar_url(url), obtenida)
			raise red.ErrorHTTP(red.HTTP, _("Lo descargado no coincide con la suma esperada; se ha borrado por seguridad."))
	os.replace(parcial, final)
	return final
