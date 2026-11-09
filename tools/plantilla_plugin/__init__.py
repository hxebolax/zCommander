# SPDX-License-Identifier: GPL-3.0-or-later
"""Complemento «{{nombre}}» de zCommander (generado con tools/crear_plugin.py).

Reglas que conviene no olvidar (guía del autor, diseño 2.0, 15.3):

- Solo se importa ``app.plugins.api``: lo demás de zCommander puede cambiar.
- ``activar`` solo registra funciones; no abre diálogos ni hace trabajo largo.
- Los manejadores corren en el hilo de la interfaz y duran poco: lo largo va a
  ``zc.tareas`` o ``zc.lanzar``. Las preguntas, con ``zc.ui`` en la interfaz y
  con ``zc.decisor`` desde un hilo.
- Los anuncios, con ``ctx.anunciar`` y su nivel; nunca accessible_output2 directamente.
"""

from __future__ import annotations

from app.plugins import api


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		zc.ordenes.manejador("saludar", self.saludar)

	def saludar(self, ctx: api.ContextoComplemento) -> None:
		cursor = ctx.activo.cursor()
		saludo = self.zc.config.obtener("saludo")
		ctx.sonar("saludo")
		ctx.anunciar(f"{saludo}, {cursor.nombre}" if cursor is not None else str(saludo), api.RESULTADO)
