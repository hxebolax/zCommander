# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Complemento lento de las pruebas: tarda en importarse (para el tope de carga)."""

from __future__ import annotations

import time

from app.plugins import api

time.sleep(3)


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		zc.ordenes.manejador("saludar", api.provisional("saludar"))
