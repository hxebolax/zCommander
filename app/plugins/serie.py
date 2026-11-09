# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lista de los complementos de serie (diseño 2.0, 3.2). Sin wx.

``SERIE`` lo GENERA ``tools/generar_anexos.py`` desde los manifiestos de
``plugins/`` (no se edita a mano; ``test_anexos_al_dia`` comprueba que está al
día). Un complemento de ``<raíz>/plugins/`` es «Oficial» sin firma solo si su
id y su versión están aquí. ``SUMAS`` solo existe en la versión compilada
(``serie_sumas.py``, que genera ``setup_cx.py``); desde el código fuente vale
``None`` y los de serie no se comprueban.
"""

from __future__ import annotations

SERIE: dict[str, str] = {
	"zc.busqueda_instantanea": "1.0.0",
	"zc.cifrado": "1.0.0",
	"zc.documentos": "1.0.0",
	"zc.duplicados": "1.0.0",
	"zc.ffmpeg": "1.0.0",
	"zc.git": "1.0.0",
	"zc.hexadecimal": "1.0.0",
	"zc.imagenes": "1.0.0",
	"zc.metadatos": "1.0.0",
	"zc.monitor": "1.0.0",
	"zc.notas": "1.0.0",
	"zc.nubes": "1.1.0",
	"zc.ocr": "1.0.0",
	"zc.ocupacion": "1.0.0",
	"zc.organizador": "1.0.0",
	"zc.papelera": "1.0.0",
	"zc.portapapeles": "1.0.0",
	"zc.procesos": "1.0.0",
	"zc.programador": "1.0.0",
	"zc.proyectos": "1.0.0",
	"zc.reproductor": "1.0.0",
	"zc.seguridad": "1.0.0",
	"zc.sincronizacion": "1.0.0",
	"zc.synology": "1.0.0",
	"zc.tablas": "1.0.0",
	"zc.texto": "1.0.0",
	"zc.voz": "1.0.0",
}

try:
	from app.plugins.serie_sumas import SUMAS  # type: ignore[import-not-found]
except ImportError:
	SUMAS: dict[str, dict[str, str]] | None = None
