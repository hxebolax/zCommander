# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Codificaciones y fines de línea (zc.texto, diseño 2.0, 11.25).

- Columnas «Codificación» y «Fin de línea» (leen solo el principio del archivo).
- «Convertir la codificación y los fines de línea...»: diálogo con vista previa
  y operación del motor con deshacer.
- «Informe de caracteres no válidos»: texto de solo lectura con línea y columna
  de cada carácter dudoso.

La lógica vive en ``servicios`` (sin wx); los diálogos en ``ui``.
"""

from __future__ import annotations

import builtins
import fnmatch
import os
from typing import Any

from app.plugins import api

from .servicios import conversion, deteccion
from .servicios.operacion import OperacionConvertirTexto, Respaldos


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Tamaño máximo de cada archivo en el informe (lo demás se dice como error).
TAMANO_INFORME = 50 * 1024 * 1024


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.respaldos: Respaldos | None = None
		zc.ordenes.manejador("convertir", self.convertir)
		zc.ordenes.manejador("informe", self.informe)
		zc.columnas.extractor("codificacion", self.columna_codificacion)
		zc.columnas.extractor("fin_linea", self.columna_fin_linea)

	def desactivar(self) -> None:
		if self.respaldos is not None:
			self.respaldos.limpiar()

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""El diálogo Convertir, sin mostrarlo, para ``revisar_teclado`` (3.12)."""
		try:
			ui = self.zc.ui
			ui.ListaAccesible  # noqa: B018 - sin la ventana de zCommander lanza NoAdmitido
		except api.NoAdmitido:
			self.zc.registro.info("Sin la interfaz de zCommander no se pueden construir los diálogos para revisarlos")
			return []
		from .ui.dialogo_convertir import DialogoConvertir

		return [DialogoConvertir(padre, ui, ["ejemplo.txt"], conversion.Opciones(), True)]

	# ── Columnas ──────────────────────────────────────────────────────────────

	def _es_texto(self, nombre: str) -> bool:
		patrones = [p.strip() for p in str(self.zc.config.obtener("extensiones", "")).split(";") if p.strip()]
		return not patrones or any(fnmatch.fnmatch(nombre.casefold(), p.casefold()) for p in patrones)

	def _detectar(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any) -> deteccion.Deteccion | None:
		if entrada.es_carpeta or not self._es_texto(entrada.nombre):
			return None
		api.comprobar(cancelacion)
		with proveedor.abrir_lectura(entrada.ruta) as flujo:
			datos = flujo.read(deteccion.MUESTRA + 1)
		resultado = deteccion.detectar(datos[:deteccion.MUESTRA], cortado=len(datos) > deteccion.MUESTRA)
		return None if resultado.binario else resultado

	def columna_codificacion(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any) -> str | None:
		resultado = self._detectar(entrada, proveedor, cancelacion)
		return _(resultado.nombre_codificacion) if resultado else None

	def columna_fin_linea(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any) -> str | None:
		resultado = self._detectar(entrada, proveedor, cancelacion)
		return _(resultado.fin_linea) if resultado else None

	# ── Órdenes ───────────────────────────────────────────────────────────────

	def _archivos(self, ctx: api.ContextoComplemento) -> list[str] | None:
		"""Rutas locales de los archivos elegidos; anuncia por qué no hay ninguna."""
		panel = ctx.objetivo
		elementos = [e for e in panel.elementos_trabajo() if not e.es_carpeta and not e.es_superior]
		if not elementos:
			ctx.anunciar(_("Elija uno o varios archivos de texto"), api.ESENCIAL)
			return None
		rutas = [panel.proveedor.ruta_local(e.ruta) for e in elementos]
		if any(r is None for r in rutas):
			ctx.anunciar(_("Solo se pueden convertir archivos del disco; cópielos antes a una carpeta"), api.ESENCIAL)
			return None
		return [str(r) for r in rutas]

	def convertir(self, ctx: api.ContextoComplemento) -> None:
		rutas = self._archivos(ctx)
		if not rutas:
			return
		from .ui.dialogo_convertir import DialogoConvertir

		config = self.zc.config
		opciones = conversion.Opciones(destino=config.obtener("destino", "utf8"), fin_linea=config.obtener("fin_linea", "sin_cambio"))
		dialogo = DialogoConvertir(None, self.zc.ui, rutas, opciones, bool(config.obtener("copia_bak", True)),
			calcular=lambda o, al_listo: self._vista_previa(rutas, o, al_listo), al_ayuda=self.zc.abrir_ayuda)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx_id_ok():
				return
			opciones, copia_bak = dialogo.opciones(), dialogo.copia_bak()
		finally:
			dialogo.Destroy()
		if self.respaldos is None:
			self.respaldos = Respaldos(self.zc.datos / "deshacer")
		self.zc.lanzar(OperacionConvertirTexto(ctx.objetivo.proveedor, rutas, opciones, copia_bak, self.respaldos))

	def _vista_previa(self, rutas: list[str], opciones: conversion.Opciones, al_listo: Any) -> None:
		def trabajo(tarea: Any) -> list[tuple[str, str, str, str]]:
			return [fila_previa(ruta, opciones, tarea) for ruta in rutas]

		anterior = getattr(self, "_tarea_previa", None)
		if anterior is not None:
			self.zc.tareas.cancelar(anterior)
		self._tarea_previa = self.zc.tareas.enviar(trabajo, al_terminar=al_listo, nombre="zc.texto:vista previa",
			al_fallar=lambda error: self.zc.registro.debug("Vista previa sin terminar: %s", error))

	def informe(self, ctx: api.ContextoComplemento) -> None:
		rutas = self._archivos(ctx)
		if not rutas:
			return
		ctx.anunciar(_("Revisando {n} archivos...").format(n=len(rutas)) if len(rutas) > 1 else _("Revisando..."), api.NORMAL)

		def trabajo(tarea: Any) -> str:
			informes = []
			for ruta in rutas:
				tarea.comprobar()
				informes.append(informe_de(ruta))
			return conversion.texto_informe(informes)

		def mostrar(texto: str) -> None:
			self.zc.ui.mostrar_texto(_("Informe de caracteres no válidos"), texto)

		self.zc.tareas.enviar(trabajo, al_terminar=mostrar,
			al_fallar=lambda error: self.zc.anunciar(_("No se pudo hacer el informe: {e}").format(e=error), api.ESENCIAL))


def fila_previa(ruta: str, opciones: conversion.Opciones, cancelacion: Any = None) -> tuple[str, str, str, str]:
	"""(archivo, codificación, fin de línea, cambios) para la vista previa del diálogo."""
	nombre = os.path.basename(ruta)
	api.comprobar(cancelacion)
	try:
		if os.path.getsize(ruta) > conversion.TAMANO_MAXIMO:
			return nombre, "", "", _("Error: demasiado grande")
		with open(ruta, "rb") as archivo:
			datos = archivo.read()
		resultado = conversion.convertir(datos, opciones)
	except conversion.ErrorConversion as error:
		det = deteccion.detectar(datos[:deteccion.MUESTRA]) if "datos" in locals() else None
		return (nombre, det.nombre_codificacion if det and not det.binario else "", det.fin_linea if det and not det.binario else "",
			_("Error: {e}").format(e=error))
	except OSError as error:
		return nombre, "", "", _("Error: {e}").format(e=error.strerror or error)
	return nombre, resultado.original.nombre_codificacion, resultado.original.fin_linea, resultado.resumen(opciones.destino)


def informe_de(ruta: str) -> conversion.Informe:
	try:
		if os.path.getsize(ruta) > TAMANO_INFORME:
			return conversion.Informe(ruta, None, error=_("es demasiado grande para revisarlo"))
		with open(ruta, "rb") as archivo:
			return conversion.informar(ruta, archivo.read())
	except OSError as error:
		return conversion.Informe(ruta, None, error=str(error.strerror or error))


def wx_id_ok() -> int:
	import wx

	return wx.ID_OK
