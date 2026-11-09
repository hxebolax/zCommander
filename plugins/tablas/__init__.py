# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Datos tabulares: SQLite y CSV (zc.tablas, diseño 2.0, 11.22).

- Intro en un ``.db``, ``.sqlite`` o ``.sqlite3`` entra en él como carpeta, con
  un ``<tabla>.csv`` por tabla y vista (``[[comprimidos]]``; la fábrica
  comprueba la cabecera y, si no es SQLite, lanza ``NoAdmitido``).
- F3 sobre un CSV, un TSV o una de esas tablas abre el visor de tabla (visor con
  ventana propia, ``zc.visores.ventana``); también «Ver como tabla».
- «Consulta SQL...» sobre una base (la del cursor o la del panel).

La lógica vive en ``servicios`` (sin wx); las ventanas en ``ui``.
"""

from __future__ import annotations

import builtins
import os
from typing import Any

from app.plugins import api

from .servicios import datos, sqlite
from .servicios.proveedor import ProveedorSQLite, fabrica

EXTENSIONES_CSV = (".csv", ".tsv", ".tab")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.visores: list[Any] = []
		zc.ordenes.manejador("ver_tabla", self.ver_tabla)
		zc.ordenes.manejador("consulta", self.consulta)
		zc.vfs.comprimido(sqlite.EXTENSIONES, lambda contenedor, ruta: fabrica(contenedor, ruta, str(zc.cache)))
		zc.visores.ventana("tabla", self.abrir_visor)

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""El visor y el diálogo de consulta, sin mostrarlos, para ``revisar_teclado`` (3.12)."""
		try:
			self.zc.ui.ListaAccesible  # noqa: B018 - sin la ventana de zCommander lanza NoAdmitido
		except api.NoAdmitido:
			self.zc.registro.info("Sin la interfaz de zCommander no se pueden construir las ventanas para revisarlas")
			return []
		from .ui.consulta import DialogoConsulta
		from .ui.visor import VisorTabla

		visor = VisorTabla(self.zc, "ejemplo", None, base_sqlite="ejemplo.db", padre=padre)
		return [visor.ventana, DialogoConsulta(padre, self.zc, "ejemplo.db")]

	# ── Visor ────────────────────────────────────────────────────────────────

	def cargador(self, proveedor: api.Proveedor, ruta: str) -> Any:
		"""Función que lee la tabla en un hilo (``cargar(cancelacion) -> Tabla``)."""
		maximas = int(self.zc.config.obtener("filas_maximas", 1_000_000))
		if isinstance(proveedor, ProveedorSQLite):
			base, tabla = proveedor.ruta_local_base, proveedor.objeto(ruta)
			return lambda cancelacion: sqlite.leer_tabla(base, tabla, maximas, cancelacion)
		separador = str(self.zc.config.obtener("separador", "automatico"))
		nombre = proveedor.nombre(ruta)

		def cargar(cancelacion: Any) -> datos.Tabla:
			api.comprobar(cancelacion)
			with proveedor.abrir_lectura(ruta) as flujo:
				contenido = flujo.read()
			api.comprobar(cancelacion)
			return datos.leer_csv(contenido, nombre, separador, maximas)

		return cargar

	def abrir_visor(self, proveedor: api.Proveedor, ruta: str) -> None:
		"""[interfaz] Visor de tabla de ``ruta`` (F3 y «Ver como tabla»)."""
		from .ui.visor import VisorTabla

		base = proveedor.ruta_local_base if isinstance(proveedor, ProveedorSQLite) else ""
		try:
			cargar = self.cargador(proveedor, ruta)
		except api.ErrorArchivos as error:
			self.zc.anunciar(error.mensaje, api.ESENCIAL)
			return
		titulo = proveedor.nombre(ruta)
		if titulo.lower().endswith(".csv") and base:
			titulo = titulo[:-4]
		visor = VisorTabla(self.zc, titulo, cargar, base_sqlite=base, al_consulta=self._abrir_consulta)
		self.visores = [v for v in self.visores if v.ventana]
		self.visores.append(visor)
		visor.mostrar_ventana()

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def ver_tabla(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		cursor = panel.cursor()
		if cursor is None or cursor.es_carpeta:
			ctx.anunciar(_("Sitúese en un archivo CSV o en una tabla de una base SQLite"), api.ESENCIAL)
			return
		if not isinstance(panel.proveedor, ProveedorSQLite) and not cursor.nombre.lower().endswith(EXTENSIONES_CSV):
			ctx.anunciar(_("«Ver como tabla» abre archivos CSV y TSV y las tablas de una base SQLite"), api.ESENCIAL)
			return
		self.abrir_visor(panel.proveedor, cursor.ruta)

	def consulta(self, ctx: api.ContextoComplemento) -> None:
		base = self.base_de(ctx.objetivo)
		if base is None:
			ctx.anunciar(_("Sitúese en una base de datos SQLite (.db, .sqlite o .sqlite3) o entre en ella"), api.ESENCIAL)
			return
		self._abrir_consulta(None, base)

	def base_de(self, panel: api.PanelComplemento) -> str | None:
		"""Ruta local de la base del panel (si está dentro de una) o de la del cursor."""
		if isinstance(panel.proveedor, ProveedorSQLite):
			return panel.proveedor.ruta_local_base
		cursor = panel.cursor()
		if cursor is None or cursor.es_carpeta or os.path.splitext(cursor.nombre)[1].lower().lstrip(".") not in sqlite.EXTENSIONES:
			return None
		local = panel.proveedor.ruta_local(cursor.ruta)
		if local is None or not sqlite.es_archivo_sqlite(local):
			return None
		return local

	def _abrir_consulta(self, padre: Any, base: str) -> None:
		from .ui.consulta import DialogoConsulta

		dialogo = DialogoConsulta(padre, self.zc, base)
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()
