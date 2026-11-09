# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tareas en segundo plano de File Station como operaciones del motor de zCommander (diseño 2.0, 13.7).

Comprimir y extraer en el NAS van por ``zc.lanzar``: así tienen el mismo
progreso consultable y por hitos, la misma cancelación y la misma cola que
copiar o mover en zCommander, aunque el trabajo lo haga el propio NAS.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.plugins import api

from .cliente import ClienteDSM

_, _n = api.traduccion("zc_synology")


class OperacionNAS(api.Operacion):
	"""``start`` → ``status`` repetido → ``stop`` si se cancela, con el progreso del NAS."""

	tipo = "nas"
	admite_pausa = False

	def __init__(self, cliente: ClienteDSM, api_nombre: str, parametros: Mapping[str, Any], texto: str, carpeta_afectada: str,
			id_servidor: str) -> None:
		super().__init__()
		self._cliente = cliente
		self._api = api_nombre
		self._parametros = dict(parametros)
		self._texto = texto
		self._carpeta = carpeta_afectada
		self._id_servidor = id_servidor
		self.resultado: dict[str, Any] = {}

	def descripcion(self) -> str:
		return self._texto

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset({f"synology:synology:{self._id_servidor}"})

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [("synology", self._carpeta)]

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=1, actual=self._texto)

		def progreso(hechos: int, total: int) -> None:
			ctx.comprobar()
			self.progresar(bytes_hechos=hechos, bytes_total=total)

		try:
			self.resultado = self._cliente.tarea_fondo(self._api, self._parametros, progreso=progreso, cancelacion=ctx.token)
		except api.Cancelado:
			raise
		except api.ErrorArchivos as error:
			self.anotar_error(self._carpeta, error.mensaje)
			return
		self.progresar(archivos_hechos=1)
