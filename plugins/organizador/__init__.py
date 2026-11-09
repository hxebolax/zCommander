# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Organizador y renombrado por metadatos (zc.organizador, diseño 2.0, 11.23).

«Organizar por metadatos...» (Comandos > Herramientas) lleva los elementos de
trabajo del panel activo (las carpetas, con todo lo que tienen dentro) a
carpetas y nombres sacados de una plantilla: ``Fotos\\[EXIF:fecha:AAAA]\\[EXIF:fecha:MM]``,
``Música\\[MP3:artista]\\[MP3:album]`` con el nombre ``[MP3:pista] - [MP3:titulo]``,
``Documentos\\[Y]``. La vista previa dice el destino y el estado de cada
archivo; organizar es una operación del motor con deshacer.

Exporta para otros complementos (el monitor de carpetas, 11.18):

- ``planificar(rutas, plantilla_carpetas, plantilla_archivo="[N]", base="") -> list`` [trabajo]
- ``operacion(filas, mover=True) -> Operacion``: la operación para ``zc.lanzar``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any

from app.plugins import api

from . import motor

_ = api.traduccion("zc.organizador")[0]


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		zc.ordenes.manejador("organizar", self.organizar)
		zc.exportar("planificar", self.planificar_rutas)
		zc.exportar("operacion", self.operacion)

	# Funciones -----------------------------------------------------------------

	def evaluar(self, plantilla: str, entrada: api.Entrada, proveedor: api.Proveedor) -> str:
		return self.zc.renombrado.evaluar(plantilla, entrada, proveedor)

	def planificar(self, entradas: Sequence[api.Entrada], proveedor: api.Proveedor, base: str, carpetas: str, archivo: str,
			cancelacion: Any = None) -> list[motor.Fila]:
		"""Vista previa [trabajo]: expande las carpetas y resuelve las plantillas."""
		archivos = motor.expandir(entradas, proveedor, cancelacion)
		return motor.planificar(archivos, proveedor, base, carpetas, archivo, self.evaluar, str(self.zc.config.obtener("sin_dato")),
			cancelacion)

	def planificar_rutas(self, rutas: Sequence[str], plantilla_carpetas: str, plantilla_archivo: str = "[N]", base: str = "") -> list[motor.Fila]:
		"""Para otros complementos [trabajo]: ``base`` vacía = la carpeta de cada archivo."""
		filas: list[motor.Fila] = []
		for ruta in rutas:
			proveedor, _carpeta = self.zc.vfs.resolver(os.path.dirname(ruta))
			try:
				entrada = proveedor.info(ruta)
				filas.extend(self.planificar([entrada], proveedor, base or os.path.dirname(ruta), plantilla_carpetas, plantilla_archivo))
			finally:
				proveedor.cerrar()
		return filas

	def operacion(self, filas: Sequence[motor.Fila], mover: bool = True) -> api.Operacion:
		local, _ruta = self.zc.vfs.resolver(os.path.dirname(filas[0].origen)) if filas else (None, "")
		return motor.OperacionOrganizar(filas, local, local, mover)

	# Orden ---------------------------------------------------------------------

	def organizar(self, ctx: api.ContextoComplemento) -> None:
		from . import ui

		activo, pasivo = ctx.activo, ctx.pasivo
		entradas = activo.elementos_trabajo()
		if not entradas:
			self.zc.anunciar(_("No hay nada que organizar: marque archivos o carpetas"), api.ESENCIAL)
			return
		origen = activo.proveedor
		base = ""
		for panel in (pasivo, activo):
			local = panel.proveedor.ruta_local(panel.ruta) if panel.ruta else None
			if local and panel.proveedor.esquema == "local":
				base = local
				break
		calcular = self._calculador(entradas, origen)
		dialogo = ui.DialogoOrganizar(None, self.zc, base, len(entradas), calcular)
		try:
			dialogo.actualizar()
			if self.zc.ui.mostrar_modal(dialogo) != ui.wx.ID_OK:
				return
			filas, mover, base = dialogo.filas, dialogo.mover(), dialogo.campos()[2]
		finally:
			dialogo.Destroy()
		destino, _ruta = self.zc.vfs.resolver(base)
		self.zc.lanzar(motor.OperacionOrganizar(filas, origen, destino, mover))

	def _calculador(self, entradas: Sequence[api.Entrada], proveedor: api.Proveedor) -> Callable:
		zc = self.zc
		pendiente: list[Any] = [None]

		def calcular(carpetas: str, archivo: str, base: str, al_terminar: Callable[[list[motor.Fila]], None]) -> None:
			if pendiente[0] is not None:
				pendiente[0].token.cancelar()

			def trabajo(tarea: Any) -> list[motor.Fila]:
				return self.planificar(entradas, proveedor, base, carpetas, archivo, tarea)

			def fallo(error: BaseException) -> None:
				if isinstance(error, api.Cancelado) or type(error).__name__ == "TareaCancelada":
					return
				zc.registro.warning("No se pudo calcular la vista previa: %s", error)
				al_terminar([])

			pendiente[0] = zc.tareas.enviar(trabajo, al_terminar=al_terminar, al_fallar=fallo, nombre="organizador-vista-previa")

		return calcular

	def ventanas_para_revisar(self, padre: Any) -> list:
		from . import ui

		try:
			return [ui.DialogoOrganizar(padre, self.zc, "C:\\", 3)]
		except api.NoAdmitido:
			self.zc.registro.info("Sin interfaz: las ventanas se revisan en las pruebas del bloque")
			return []
