# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Marca de la Web (flujo alternativo ``Zone.Identifier``).

Windows marca lo descargado de Internet para que SmartScreen y la Vista
protegida de Office avisen antes de abrirlo. Al extraer de un comprimido
marcado, o al descargar de FTP o SFTP, zCommander copia o crea esa marca, como
hace el Explorador.
"""

from __future__ import annotations

import logging

from app.services.vfs import rutas

log = logging.getLogger(__name__)

FLUJO = ":Zone.Identifier"
INTERNET = "[ZoneTransfer]\r\nZoneId=3\r\n"


def leer(ruta: str) -> str | None:
	"""Contenido de la marca o None si no la tiene (o el sistema de archivos no admite flujos)."""
	try:
		# newline="": el contenido se copia tal cual (con sus CRLF) a lo extraído o descargado.
		with open(rutas.con_prefijo_largo(rutas.normalizar(ruta)) + FLUJO, encoding="utf-8", errors="replace",
				newline="") as flujo:
			return flujo.read()
	except OSError:
		return None


def escribir(ruta: str, contenido: str = INTERNET) -> bool:
	"""Escribe la marca. ``False`` si no se pudo (FAT, red sin flujos): no es un error grave."""
	try:
		with open(rutas.con_prefijo_largo(rutas.normalizar(ruta)) + FLUJO, "w", encoding="utf-8", newline="") as flujo:
			flujo.write(contenido)
		return True
	except OSError:
		log.debug("No se pudo escribir la marca de la Web en %s", ruta, exc_info=True)
		return False
