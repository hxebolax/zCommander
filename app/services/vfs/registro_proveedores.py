# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Importa los módulos de proveedores de los bloques C, D, CM y RD, que se registran solos en ``resolver``.

Cada importación va protegida: si un bloque falla, el resto de zCommander
sigue funcionando y el fallo queda en el registro.
"""

from __future__ import annotations

import importlib
import logging

log = logging.getLogger(__name__)

MODULOS = (
	"app.services.vfs.zip",
	"app.services.vfs.tar",
	"app.services.vfs.siete_z",
	"app.services.vfs.ftp",
	"app.services.vfs.sftp",
	# 2.0 (8.8, 9.10): los dejó N2; existen cuando CM y RD los programan (mientras, ModuleNotFoundError).
	"app.services.vfs.libarchive",
	"app.services.vfs.flujo",
	"app.services.vfs.siete_zip_instalado",
	"app.services.vfs.red",
)

for _modulo in MODULOS:
	try:
		importlib.import_module(_modulo)
	except ModuleNotFoundError as _error:
		if _error.name != _modulo:
			log.exception("Falta una dependencia de %s", _modulo)
		else:
			log.debug("Proveedor %s todavía no disponible", _modulo)
	except Exception:  # noqa: BLE001 - un proveedor roto no impide arrancar
		log.exception("No se pudo registrar el proveedor %s", _modulo)
