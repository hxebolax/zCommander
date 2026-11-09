# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Aplicar las reglas a lo que ya hay en una carpeta, como operación del motor (lo usa el programador, 11.24).

Cada error de un archivo se pregunta con el ``Decisor`` (reintentar, omitir o
cancelar); en una tarea programada responde el gestor de decisiones con las
respuestas automáticas de la tarea, sin mostrar nada. Las reglas que ejecutan
órdenes no se aplican aquí (necesitan el hilo de la interfaz): se dicen en el
registro.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from app.plugins import api

from . import reglas as modulo_reglas


class OperacionReglas(api.Operacion):
	tipo = "reglas"

	def __init__(self, carpeta: str, reglas: list[modulo_reglas.Regla], registro: modulo_reglas.Registro,
			herramientas: modulo_reglas.Herramientas | None = None,
			al_aplicar: Callable[[str], None] | None = None) -> None:
		super().__init__()
		self.carpeta = carpeta
		self.reglas = reglas
		self.registro = registro
		self.herramientas = herramientas or modulo_reglas.Herramientas()
		self.al_aplicar = al_aplicar
		self.hechos: list[modulo_reglas.Hecho] = []

	def descripcion(self) -> str:
		return f"Aplicar las reglas del monitor en {self.carpeta}"

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [("local", self.carpeta)]

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		try:
			elementos = sorted((e for e in os.scandir(self.carpeta) if e.is_file(follow_symlinks=False)),
				key=lambda e: e.name.casefold())
		except OSError as error:
			self.anotar_error(self.carpeta, f"No se puede leer la carpeta: {error.strerror or error}")
			self.cambiar_estado(api.Estado.FALLIDA)
			return
		self.progresar(archivos_total=len(elementos))
		omitir_todos = False
		try:
			for elemento in elementos:
				ctx.comprobar()
				self.progresar(actual=elemento.name)
				info = elemento.stat()
				regla = modulo_reglas.primera_que_coincide(self.reglas, elemento.path, self.carpeta, info.st_size, info.st_mtime)
				if regla is not None and regla.accion == modulo_reglas.ORDEN:
					self.historial.append(f"{elemento.name}: la regla {regla.nombre} ejecuta una orden; solo con el monitor en marcha")
					regla = None
				while regla is not None:
					try:
						hecho = modulo_reglas.aplicar(regla, elemento.path, self.herramientas)
					except modulo_reglas.ErrorRegla as error:
						if omitir_todos:
							self.anotar_error(elemento.path, str(error))
							break
						with ctx.esperando():
							respuesta = ctx.decisor.preguntar_error(self, api.PreguntaError(elemento.path, str(error),
								self.descripcion()))
						if respuesta == api.AccionError.REINTENTAR:
							continue
						if respuesta == api.AccionError.CANCELAR:
							raise api.Cancelado() from error
						omitir_todos = respuesta == api.AccionError.OMITIR_TODOS
						self.anotar_error(elemento.path, str(error))
						self.registro.apuntar(self.carpeta, modulo_reglas.Hecho(regla.nombre, regla.accion, elemento.path,
							str(error), ok=False))
						break
					self.hechos.append(hecho)
					self.registro.apuntar(self.carpeta, hecho)
					if self.al_aplicar is not None and hecho.nueva_ruta and hecho.nueva_ruta != elemento.path:
						self.al_aplicar(hecho.nueva_ruta)
					break
				self.sumar(archivos_hechos=1)
		except api.Cancelado:
			self.cambiar_estado(api.Estado.CANCELADA)
			raise
		self.cambiar_estado(api.Estado.TERMINADA_CON_ERRORES if self.errores else api.Estado.TERMINADA)
