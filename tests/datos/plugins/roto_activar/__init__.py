# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Complemento roto de las pruebas: lanza en activar()."""

from __future__ import annotations

from app.plugins import api


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		raise RuntimeError("fallo en activar a propósito")
