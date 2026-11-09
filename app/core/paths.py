# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Rutas de la aplicación (modo portable): TODO vive en ``data``.

La carpeta ``data`` está junto al programa:

- Desde el código: junto a ``main.py`` (la raíz del proyecto).
- Compilada con cx_Freeze: junto al ``.exe`` (``Path(sys.executable).parent``).

Nunca se escribe en %APPDATA%, %LOCALAPPDATA%, %TEMP% ni en el registro de
Windows: así la aplicación va en un pendrive, se desinstala borrando su
carpeta y la copia de seguridad es copiar una carpeta.

La variable de entorno ``APP_DATA_DIR`` redirige ``data`` a otra carpeta. La
usan las pruebas para no tocar nunca la configuración real del desarrollador.

Este módulo solo usa la biblioteca estándar: lo importa ``main.py`` antes que
nada (incluso antes que wx) para poder registrar un fallo de arranque.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ¿Se ejecuta la versión compilada con cx_Freeze?
CONGELADA: bool = bool(getattr(sys, "frozen", False))

# Variable de entorno que redirige la carpeta data (pruebas, perfiles aparte).
VARIABLE_DATA = "APP_DATA_DIR"

# Carpeta de la que salen los recursos distribuibles (bin, sounds, locales,
# docs, icons) cuando no coincide con ``ruta_datos()``. La fija
# ``--comprobar-arranque`` (diseño 2.0, 14.8): escribe en una carpeta temporal
# pero sigue leyendo los binarios y los sonidos de la ``data`` real, para que la
# prueba de la compilación cubra la carga de libarchive y de los paquetes.
_recursos: list[Path | None] = [None]


def fijar_recursos(ruta: Path | None) -> None:
	"""Hace que las rutas de recursos distribuibles salgan de ``ruta`` (``None`` vuelve a ``ruta_datos()``)."""
	_recursos[0] = Path(ruta).resolve() if ruta is not None else None


def _recurso(nombre: str) -> Path:
	"""Subcarpeta de recursos distribuibles: de ``fijar_recursos`` si se fijó; si no, de ``data``."""
	if _recursos[0] is None:
		return subcarpeta(nombre)
	ruta = _recursos[0] / nombre
	ruta.mkdir(parents=True, exist_ok=True)
	return ruta


def ruta_base() -> Path:
	"""Carpeta raíz del programa.

	Compilada: la carpeta del ejecutable. Desde código: la que contiene
	``main.py``, dos niveles por encima de este archivo (``<raíz>/app/core``).
	No se usa ``os.getcwd()``: un acceso directo o el Explorador pueden
	arrancar el programa con otra carpeta de trabajo.
	"""
	if CONGELADA:
		return Path(sys.executable).resolve().parent
	return Path(__file__).resolve().parent.parent.parent


def ruta_datos() -> Path:
	"""Devuelve (y crea si falta) la carpeta ``data``."""
	redireccion = os.environ.get(VARIABLE_DATA, "").strip()
	ruta = Path(redireccion).expanduser().resolve() if redireccion else ruta_base() / "data"
	ruta.mkdir(parents=True, exist_ok=True)
	return ruta


def subcarpeta(nombre: str) -> Path:
	"""Devuelve (y crea si falta) una subcarpeta de ``data``.

	Las carpetas se crean justo antes de usarse para no llenar ``data`` de
	carpetas vacías que luego alguien podría distribuir por error.
	"""
	ruta = ruta_datos() / nombre
	ruta.mkdir(parents=True, exist_ok=True)
	return ruta


# ── Generadas al usar la aplicación (NUNCA se distribuyen) ───────────────────


def ruta_configuracion() -> Path:
	"""Carpeta de configuración (``config.json``)."""
	return subcarpeta("config")


def ruta_registros() -> Path:
	"""Carpeta de registros (logs)."""
	return subcarpeta("logs")


def ruta_temporales() -> Path:
	"""Temporales de la aplicación (por ejemplo, el buzón de la instancia única)."""
	return subcarpeta("temp")


# ── Recursos que viajan con la distribución ──────────────────────────────────


def ruta_documentacion() -> Path:
	"""Manual de usuario, lista de teclas y novedades."""
	return _recurso("docs")


def ruta_iconos() -> Path:
	"""Iconos de la aplicación (``app.ico``)."""
	return _recurso("icons")


def ruta_sonidos() -> Path:
	"""Sonidos de la interfaz."""
	return _recurso("sounds")


def ruta_binarios() -> Path:
	"""Binarios auxiliares (ffmpeg y similares)."""
	return _recurso("bin")


def ruta_traducciones() -> Path:
	"""Catálogos gettext: ``data/locales/<idioma>/LC_MESSAGES``."""
	return _recurso("locales")


# ── Rutas de la 2.0 (complementos, cachés, copias, plantillas) ───────────────


def ruta_plugins_serie() -> Path:
	"""Complementos de serie: ``<raíz>/plugins`` (junto a ``main.py`` o al ``.exe``, fuera de ``data``).

	No se crea: solo la escribe una actualización de zCommander.
	"""
	return ruta_base() / "plugins"


def ruta_plugins_usuario() -> Path:
	"""Complementos instalados por la persona: ``data/plugins``."""
	return subcarpeta("plugins")


def ruta_cache() -> Path:
	"""Cachés que se pueden borrar sin perder nada: ``data/cache``."""
	return subcarpeta("cache")


def ruta_config_plugins() -> Path:
	"""Configuración y datos de los complementos: ``data/config/plugins``."""
	ruta = ruta_configuracion() / "plugins"
	ruta.mkdir(parents=True, exist_ok=True)
	return ruta


def ruta_cache_plugins() -> Path:
	"""Cachés de los complementos, índice de manifiestos y centinelas: ``data/cache/plugins``."""
	ruta = ruta_cache() / "plugins"
	ruta.mkdir(parents=True, exist_ok=True)
	return ruta


def ruta_copias() -> Path:
	"""Copias de seguridad por defecto (``copia.carpeta`` vacía): ``data/backups``."""
	return subcarpeta("backups")


def ruta_sonidos_usuario() -> Path:
	"""Paquetes de sonidos propios de la persona: ``data/sounds_usuario`` (nunca se distribuyen)."""
	return subcarpeta("sounds_usuario")


def ruta_plantillas() -> Path:
	"""Plantillas de archivo nuevo de la persona: ``data/plantillas``."""
	return subcarpeta("plantillas")


def ruta_plantillas_serie() -> Path:
	"""Plantillas de archivo nuevo de serie: ``data/docs/plantillas`` (viajan con la documentación)."""
	ruta = ruta_documentacion() / "plantillas"
	ruta.mkdir(parents=True, exist_ok=True)
	return ruta
