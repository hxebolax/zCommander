# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ocupación del disco accesible (zc.ocupacion, diseño 2.0, 11.8).

Ctrl+Mayús+F7 analiza una carpeta o unidad como operación del motor y abre el
resultado en el panel (``ocupacion://<id>/``): se entra y se sale como en
cualquier carpeta, con las columnas Porcentaje del padre, Porcentaje del total
y Archivos. Los 100 archivos más grandes, los antiguos y la ocupación por
extensión se ven en listas; «Ir a esta carpeta en el disco» lleva el otro
panel a lo real. El último análisis de cada carpeta se recuerda en
``datos/analisis/``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.plugins import api

from . import motor

_ = api.traduccion("zc.ocupacion")[0]

COLUMNAS = ("porcentaje_padre", "porcentaje_total", "archivos")


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.analisis: dict[str, motor.Analisis] = {}
		self.ultimo: str = ""
		zc.ordenes.manejador("analizar", self.analizar)
		zc.ordenes.manejador("mayores", self.mayores)
		zc.ordenes.manejador("extensiones", self.extensiones)
		zc.ordenes.manejador("ir", self.ir)
		zc.vfs.esquema(motor.ESQUEMA, self.fabrica)
		for columna in COLUMNAS:
			zc.columnas.extractor(columna, lambda entrada, proveedor, _c, col=columna: motor.valor_columna(col, entrada, proveedor))

	@property
	def carpeta_analisis(self) -> Path:
		return self.zc.datos / "analisis"

	# Proveedor -----------------------------------------------------------------

	def fabrica(self, direccion: str) -> tuple[api.Proveedor, str]:
		"""``ocupacion://<id>/<ruta>`` [trabajo]: el análisis en memoria o el guardado en ``datos/analisis/``."""
		id_analisis, ruta = motor.separar_direccion(direccion)
		analisis = self.analisis.get(id_analisis) or motor.cargar(self.carpeta_analisis, id_analisis)
		if analisis is None:
			raise api.NoEncontrado(_("Ese análisis de ocupación ya no está; vuelva a analizar la carpeta"), direccion)
		self.analisis[id_analisis] = analisis
		return motor.ProveedorOcupacion(analisis), ruta or analisis.raiz

	# Órdenes -------------------------------------------------------------------

	def analizar(self, ctx: api.ContextoComplemento) -> None:
		from . import ui

		dialogo = ui.DialogoAnalizar(None, self.zc, self._carpeta_inicial(ctx))
		try:
			if self.zc.ui.mostrar_modal(dialogo) != ui.wx.ID_OK:
				return
			carpeta, opciones = dialogo.carpeta(), dialogo.opciones()
		finally:
			dialogo.Destroy()
		if not carpeta or not os.path.isdir(carpeta):
			self.zc.ui.mostrar_error(_("No existe la carpeta {c}").format(c=carpeta), _("Analizar la ocupación"))
			return
		guardado = self.carpeta_analisis / f"{motor.id_de(carpeta)}.json"
		if guardado.is_file():
			fecha = api.formato.fecha(guardado.stat().st_mtime, "larga")
			eleccion = self.zc.ui.elegir_opcion(_("Ya hay un análisis de {c} del {f}.").format(c=carpeta, f=fecha), _("Analizar la ocupación"),
				[_("&Usar el último análisis"), _("Analizar de &nuevo")])
			if eleccion is None:
				return
			if eleccion == 0:
				self.zc.tareas.enviar(lambda _t: motor.cargar(self.carpeta_analisis, motor.id_de(carpeta)),
					al_terminar=self._al_cargar, al_fallar=self._al_fallar, nombre="ocupacion-cargar")
				return
		self.zc.lanzar(motor.OperacionAnalizar(carpeta, opciones), al_terminar=self._al_terminar)

	def _carpeta_inicial(self, ctx: api.ContextoComplemento) -> str:
		panel = ctx.activo
		analisis = getattr(panel.proveedor, "analisis", None)
		if isinstance(analisis, motor.Analisis):
			return analisis.raiz
		if panel.proveedor.esquema == "local" and panel.ruta:
			cursor = panel.cursor()
			return cursor.ruta if cursor is not None and cursor.es_carpeta and not cursor.es_enlace else panel.ruta
		return ""

	def _al_terminar(self, operacion: motor.OperacionAnalizar) -> None:
		analisis = operacion.analisis
		if analisis is None:
			return
		self._publicar(analisis)
		self.zc.tareas.enviar(lambda _t: motor.guardar(analisis, self.carpeta_analisis), al_fallar=self._al_fallar,
			nombre="ocupacion-guardar")

	def _al_cargar(self, analisis: motor.Analisis | None) -> None:
		if analisis is None:
			self.zc.anunciar(_("No se pudo leer el análisis guardado; vuelva a analizar"), api.ESENCIAL)
			return
		self._publicar(analisis)

	def _al_fallar(self, error: BaseException) -> None:
		self.zc.registro.warning("Falló un trabajo de la ocupación: %s", error, exc_info=error)
		self.zc.anunciar(_("No se pudo guardar o leer el análisis: {e}").format(e=getattr(error, "mensaje", error)), api.ESENCIAL)

	def _publicar(self, analisis: motor.Analisis) -> None:
		"""Lo deja en memoria, lo abre en el panel activo y dice el resumen."""
		self.analisis[analisis.id] = analisis
		self.ultimo = analisis.id
		self.zc.abrir_ruta(analisis.direccion)
		self.zc.anunciar(analisis.resumen(), api.RESULTADO)

	def _analisis_de(self, ctx: api.ContextoComplemento) -> motor.Analisis | None:
		"""El del panel activo; si no, el último de la sesión; si no, el guardado de la carpeta del panel."""
		analisis = getattr(ctx.activo.proveedor, "analisis", None)
		if isinstance(analisis, motor.Analisis):
			return analisis
		if self.ultimo in self.analisis:
			return self.analisis[self.ultimo]
		if ctx.activo.proveedor.esquema == "local" and ctx.activo.ruta:
			analisis = motor.cargar(self.carpeta_analisis, motor.id_de(ctx.activo.ruta))
			if analisis is not None:
				self.analisis[analisis.id] = analisis
				return analisis
		self.zc.anunciar(_("Todavía no hay ningún análisis: use Analizar la ocupación"), api.ESENCIAL)
		return None

	def mayores(self, ctx: api.ContextoComplemento) -> None:
		from . import ui

		analisis = self._analisis_de(ctx)
		if analisis is None:
			return
		self._lado_otro = ctx.pasivo.lado
		dialogo = ui.DialogoArchivos(None, self.zc, analisis, acciones={"ir": self._ir_archivo, "panel": self._al_panel,
			"exportar": self._exportar_lista})
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()

	def extensiones(self, ctx: api.ContextoComplemento) -> None:
		from . import ui

		analisis = self._analisis_de(ctx)
		if analisis is None:
			return
		dialogo = ui.DialogoExtensiones(None, self.zc, analisis, al_exportar=self._exportar_informe)
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()

	def ir(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.activo
		if not isinstance(getattr(panel.proveedor, "analisis", None), motor.Analisis):
			self.zc.anunciar(_("Esta orden sirve en un panel con un análisis de ocupación"), api.ESENCIAL)
			return
		cursor = panel.cursor()
		ruta = cursor.ruta if cursor is not None else panel.ruta
		self.zc.abrir_ruta(ruta, ctx.pasivo.lado)

	# Acciones de las listas ----------------------------------------------------

	def _ir_archivo(self, dialogo: Any) -> None:
		archivo = dialogo.archivo_actual()
		if archivo is None:
			return
		self.zc.abrir_ruta(archivo.ruta, getattr(self, "_lado_otro", None))
		dialogo.EndModal(0)

	def _al_panel(self, dialogo: Any) -> None:
		archivos = dialogo.archivos()
		titulo = _("Archivos antiguos") if dialogo.selector.GetSelection() == 1 else _("Los archivos más grandes")
		self.zc.ui.mostrar_resultados(titulo, [a.ruta for a in archivos])
		dialogo.EndModal(0)

	def _exportar_lista(self, dialogo: Any) -> None:
		from . import ui

		ruta = ui.pedir_archivo(dialogo, self.zc, _("Exportar la lista"), _("archivos.txt"))
		if not ruta:
			return
		archivos = dialogo.archivos()
		if ruta.casefold().endswith(".csv"):
			escribir(ruta, motor.lista_csv(archivos), "utf-8-sig")
		else:
			escribir(ruta, "\n".join(f"{api.formato.tamano_legible(a.tamano)}\t{a.ruta}" for a in archivos) + "\n")
		self.zc.anunciar(_("Lista guardada en {r}").format(r=ruta), api.RESULTADO)

	def _exportar_informe(self, dialogo: Any) -> None:
		from . import ui

		ruta = ui.pedir_archivo(dialogo, self.zc, _("Exportar el informe de ocupación"), _("ocupacion.txt"))
		if not ruta:
			return
		analisis = dialogo.analisis
		if ruta.casefold().endswith(".csv"):
			escribir(ruta, motor.informe_csv(analisis), "utf-8-sig")
		else:
			escribir(ruta, motor.informe_texto(analisis))
		self.zc.anunciar(_("Informe guardado en {r}").format(r=ruta), api.RESULTADO)

	def ventanas_para_revisar(self, padre: Any) -> list:
		from . import ui

		analisis = motor.Analisis("C:\\", motor.Nodo("C:\\", "C:\\"))
		try:
			return [ui.DialogoAnalizar(padre, self.zc, "C:\\"), ui.DialogoArchivos(padre, self.zc, analisis),
				ui.DialogoExtensiones(padre, self.zc, analisis)]
		except api.NoAdmitido:
			self.zc.registro.info("Sin interfaz: las ventanas se revisan en las pruebas del bloque")
			return []


def escribir(ruta: str, texto: str, codificacion: str = "utf-8") -> None:
	with open(ruta, "w", encoding=codificacion, newline="") as archivo:
		archivo.write(texto)
