# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Manejadores del simulador, un módulo por área (diseño 2.0, 13.9).

Cada módulo expone ``MANEJADORES: dict[(api, método), función]``. Las API del
catálogo sin manejador responden 103, como pide synology.md 7.5: el cliente
debe tolerarlo y ocultar la función.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import (
	actualizaciones,
	almacenamiento,
	auth,
	busqueda,
	carpetas,
	docker,
	drive,
	filestation,
	notificaciones,
	paquetes,
	photos,
	red,
	registros,
	seguridad,
	servicios,
	sistema,
	tareas,
	usuarios,
)

MODULOS = (auth, sistema, almacenamiento, filestation, carpetas, usuarios, paquetes, docker, drive, photos, tareas, registros,
	notificaciones, red, seguridad, servicios, actualizaciones, busqueda)

MANEJADORES: dict[tuple[str, str], Callable[[Any], Any]] = {}
for _modulo in MODULOS:
	MANEJADORES.update(_modulo.MANEJADORES)
