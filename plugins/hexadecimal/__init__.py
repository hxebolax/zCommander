# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Editor hexadecimal accesible (zc.hexadecimal, diseño 2.0, 11.10).

Ve y edita los bytes de cualquier archivo, también muy grande (tabla de
piezas: solo se lee lo visible). Los archivos de comprimidos o servidores se
abren en solo lectura (con «Guardar como» en local). La lógica vive en
``servicios`` (sin wx) y la ventana en ``ui``.
"""

from __future__ import annotations

import builtins
from typing import Any

from app.plugins import api


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.editores: list[Any] = []
		zc.ordenes.manejador("editar", self.editar)

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""La ventana del editor y el diálogo Reemplazar, sin mostrarlos, para ``revisar_teclado`` (3.12)."""
		try:
			ui = self.zc.ui
			ui.VentanaComplemento  # noqa: B018 - sin la ventana de zCommander lanza NoAdmitido
		except api.NoAdmitido:
			self.zc.registro.info("Sin la interfaz de zCommander no se pueden construir las ventanas para revisarlas")
			return []
		from .servicios.piezas import TablaPiezas
		from .ui.ventana import DialogoBuscar, EditorHexadecimal

		editor = EditorHexadecimal(self.zc, TablaPiezas(datos=b"Hola"), "ejemplo.bin", padre=padre)
		return [editor.ventana, DialogoBuscar(padre, ui, True, False, None)]

	def desactivar(self) -> None:
		for editor in self.editores:
			try:
				editor.tabla.cerrar()
			except OSError:
				self.zc.registro.debug("No se pudo cerrar un archivo del editor", exc_info=True)

	def editar(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		cursor = panel.cursor()
		if cursor is None or cursor.es_carpeta:
			ctx.anunciar(_("Sitúese en un archivo para editarlo en hexadecimal"), api.ESENCIAL)
			return
		proveedor = panel.proveedor
		local = proveedor.ruta_local(cursor.ruta)
		if local is not None:
			self.abrir(local, cursor.nombre, solo_lectura=False)
			return
		ctx.anunciar(_("Abriendo {n} en solo lectura...").format(n=cursor.nombre), api.NORMAL)

		def extraer(_tarea: Any) -> str:
			return proveedor.extraer_temporal(cursor.ruta)

		self.zc.tareas.enviar(extraer, al_terminar=lambda ruta: self.abrir(ruta, cursor.nombre, solo_lectura=True),
			al_fallar=lambda error: ctx.anunciar(_("No se pudo abrir: {e}").format(e=getattr(error, "mensaje", "") or error),
				api.ESENCIAL), nombre="zc.hexadecimal:extraer")

	def abrir(self, ruta: str, nombre: str, solo_lectura: bool) -> Any:
		from .servicios.piezas import TablaPiezas
		from .ui.ventana import EditorHexadecimal

		try:
			tabla = TablaPiezas(ruta)
		except OSError as error:
			self.zc.anunciar(_("No se pudo abrir {n}: {e}").format(n=nombre, e=error.strerror or error), api.ESENCIAL)
			return None
		editor = EditorHexadecimal(self.zc, tabla, nombre, solo_lectura=solo_lectura)
		self.editores = [e for e in self.editores if e.ventana]
		self.editores.append(editor)
		editor.ventana.Show()
		editor.volcado.SetFocus()
		editor.anunciar_byte()
		return editor
