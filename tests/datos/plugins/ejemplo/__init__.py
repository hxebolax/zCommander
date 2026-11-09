# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Complemento de ejemplo de las pruebas: una orden que anota lo que recibe."""

from __future__ import annotations

from app.plugins import api

LLAMADAS: list = []


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		import threading

		LLAMADAS.append(("activar", threading.current_thread().name))
		zc.ordenes.manejador("saludar", self.saludar)
		zc.exportar("saludo", lambda: "hola")

	def saludar(self, ctx: api.ContextoComplemento) -> None:
		cursor = ctx.activo.cursor()
		LLAMADAS.append(("saludar", ctx.argumento, ctx.activo.ruta, cursor.nombre if cursor else None))
		ctx.anunciar("Hola")

	def desactivar(self) -> None:
		LLAMADAS.append(("desactivar",))
