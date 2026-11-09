# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Papelera de reciclaje como panel (zc.papelera, diseño 2.0, 11.20).

Ctrl+F8 abre ``papelera://`` en el panel activo: cada elemento con su nombre
original, la carpeta de donde se eliminó (columna Ruta y columna «Ubicación
original»), la fecha de eliminación (columna Modificado y columna «Fecha de
eliminación») y su tamaño. Se puede entrar en una carpeta eliminada, copiar al
otro panel (F5), buscar dentro, eliminar definitivamente (Supr), restaurar a
su sitio y vaciar (con el foco en «Cancelar»). «Papelera» sale en el selector
de unidades con su resumen («312 elementos, 4,2 GB»).
"""

from __future__ import annotations

from typing import Any

from app.plugins import api

from . import motor

_ = api.traduccion("zc.papelera")[0]


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.papelera = motor.Papelera(self._carpetas)
		zc.ordenes.manejador("abrir", self.abrir)
		zc.ordenes.manejador("restaurar", self.restaurar)
		zc.ordenes.manejador("vaciar", self.vaciar)
		zc.vfs.esquema(motor.ESQUEMA, self.fabrica)
		zc.vfs.unidades(self.unidades)
		zc.columnas.extractor("ubicacion", self._columna_ubicacion)
		zc.columnas.extractor("eliminado", self._columna_eliminado)

	def _unidades_elegidas(self) -> list[str]:
		elegidas = [str(u).strip().rstrip("\\/").upper() for u in (self.zc.config.obtener("unidades") or []) if str(u).strip()]
		return [u if u.endswith(":") else u + ":" for u in elegidas] or motor.unidades_fijas()

	def _carpetas(self) -> list[str]:
		return motor.carpetas_papelera(self._unidades_elegidas())

	# VFS -----------------------------------------------------------------------

	def fabrica(self, direccion: str) -> tuple[api.Proveedor, str]:
		return motor.ProveedorPapelera(self.papelera, motor.separar_direccion(direccion)), ""

	def unidades(self) -> list[api.UnidadVirtual]:
		"""Entrada del selector de unidades con el resumen (en un hilo)."""
		return [api.UnidadVirtual(_("Papelera"), motor.DIRECCION, motor.resumen(self.papelera.elementos()))]

	@staticmethod
	def _elemento(entrada: api.Entrada, proveedor: api.Proveedor) -> motor.Elemento | None:
		if isinstance(proveedor, motor.ProveedorPapelera) and not entrada.es_superior:
			return proveedor.elemento(entrada.ruta)
		return None

	def _columna_ubicacion(self, entrada: api.Entrada, proveedor: api.Proveedor, _cancelacion: Any) -> str | None:
		elemento = self._elemento(entrada, proveedor)
		return elemento.carpeta_original if elemento is not None else None

	def _columna_eliminado(self, entrada: api.Entrada, proveedor: api.Proveedor, _cancelacion: Any) -> str | None:
		elemento = self._elemento(entrada, proveedor)
		return api.formato.fecha(elemento.eliminado, "larga") if elemento is not None else None

	# Órdenes -------------------------------------------------------------------

	def abrir(self, ctx: api.ContextoComplemento) -> None:
		self.zc.abrir_ruta(motor.DIRECCION)
		self.zc.tareas.enviar(lambda tarea: motor.resumen(self.papelera.elementos(cancelacion=tarea)),
			al_terminar=lambda texto: self.zc.anunciar(texto, api.RESULTADO), nombre="papelera-resumen")

	def restaurar(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.activo
		if not isinstance(panel.proveedor, motor.ProveedorPapelera):
			self.zc.anunciar(_("Esta orden sirve en el panel de la papelera"), api.ESENCIAL)
			return
		elementos = [e for e in (panel.proveedor.elemento(x.ruta) for x in panel.elementos_trabajo()) if e is not None]
		if not elementos:
			self.zc.anunciar(_("Elija un elemento de la papelera; lo de dentro de una carpeta eliminada se restaura con la carpeta"), api.ESENCIAL)
			return
		self.zc.lanzar(motor.OperacionRestaurar(elementos), al_terminar=lambda _o: panel.refrescar())

	def vaciar(self, ctx: api.ContextoComplemento) -> None:
		unidad = ""
		if isinstance(ctx.activo.proveedor, motor.ProveedorPapelera):
			unidad = ctx.activo.proveedor.unidad
		self.zc.tareas.enviar(lambda tarea: self.papelera.elementos(unidad, tarea),
			al_terminar=lambda elementos: self._preguntar_vaciar(ctx, unidad, elementos), nombre="papelera-vaciar")

	def _preguntar_vaciar(self, ctx: api.ContextoComplemento, unidad: str, elementos: list[motor.Elemento]) -> None:
		from . import ui

		if not elementos:
			self.zc.anunciar(_("La papelera está vacía"), api.RESULTADO)
			return
		dialogo = ui.DialogoVaciar(None, self.zc, motor.resumen(elementos), unidad)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != ui.ID_VACIAR:
				return
		finally:
			dialogo.Destroy()
		unidades = [unidad] if unidad else sorted({e.unidad for e in elementos})

		def al_terminar(operacion: api.Operacion) -> None:
			if operacion.estado in (api.Estado.TERMINADA, api.Estado.TERMINADA_CON_ERRORES):
				self.zc.sonidos.sonar("op.eliminado")
			if isinstance(ctx.activo.proveedor, motor.ProveedorPapelera):
				ctx.activo.refrescar()

		self.zc.lanzar(motor.OperacionVaciar(unidades), al_terminar=al_terminar)

	def ventanas_para_revisar(self, padre: Any) -> list:
		from . import ui

		try:
			return [ui.DialogoVaciar(padre, self.zc, "3 elementos, 2 MB", "")]
		except api.NoAdmitido:
			self.zc.registro.info("Sin interfaz: las ventanas se revisan en las pruebas del bloque")
			return []

