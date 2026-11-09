# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Buscador de duplicados (zc.duplicados, diseño 2.0, 11.7).

Mayús+F7 pregunta dónde y cómo buscar, lanza la búsqueda como operación del
motor (progreso, pausa, cancelación con F12) y, al terminar, abre la lista de
grupos con casillas: marcado automático con resumen hablado, enviar a la
papelera (operación de eliminar del núcleo), sustituir por enlaces duros,
exportar informe y enviar al panel.
"""

from __future__ import annotations

import os
from typing import Any

from app.plugins import api

from . import motor

_ = api.traduccion("zc.duplicados")[0]


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self._dialogo: Any = None
		zc.ordenes.manejador("buscar", self.buscar)

	# Orden ---------------------------------------------------------------------

	def buscar(self, ctx: api.ContextoComplemento) -> None:
		from . import ui

		carpetas = self._carpetas_iniciales(ctx)
		dialogo = ui.DialogoBuscar(None, self.zc, carpetas)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != ui.wx.ID_OK:
				return
			opciones = dialogo.opciones()
		finally:
			dialogo.Destroy()
		etiquetas = self._lector_etiquetas() if opciones.criterio == "etiquetas" else None
		if opciones.criterio == "etiquetas" and etiquetas is None:
			self.zc.anunciar(_("Para buscar por etiquetas de audio hace falta el complemento Metadatos y etiquetas de audio"), api.ESENCIAL)
			return
		operacion = motor.OperacionBuscarDuplicados(opciones, etiquetas)
		self.zc.lanzar(operacion, al_terminar=self._al_terminar_busqueda)

	@staticmethod
	def _carpetas_iniciales(ctx: api.ContextoComplemento) -> list[str]:
		"""Las carpetas marcadas del panel activo o, si no hay, la carpeta del panel."""
		panel = ctx.activo
		if panel.proveedor.esquema != "local":
			return []
		marcadas = [e.ruta for e in panel.marcadas() if e.es_carpeta]
		return marcadas or ([panel.ruta] if panel.ruta else [])

	def _lector_etiquetas(self) -> Any:
		"""``leer_etiquetas`` de ``zc.metadatos`` (11.0) si está; se llama desde el hilo de la operación."""
		zc = self.zc
		registro = zc.registro

		def leer(archivo: motor.Archivo) -> dict[str, str] | None:
			metadatos = zc.complemento("zc.metadatos")
			if metadatos is None or not hasattr(metadatos, "leer_etiquetas"):
				raise api.NoAdmitido(_("Para buscar por etiquetas de audio hace falta el complemento Metadatos y etiquetas de audio"))
			try:
				proveedor, _ruta = zc.vfs.resolver(os.path.dirname(archivo.ruta))
				return metadatos.leer_etiquetas(proveedor, archivo.ruta)
			except api.ErrorArchivos:
				registro.debug("Sin etiquetas para %s", archivo.ruta, exc_info=True)
				return None

		return leer

	def _al_terminar_busqueda(self, operacion: motor.OperacionBuscarDuplicados) -> None:
		resultado = operacion.resultado
		if operacion.estado == api.Estado.FALLIDA:
			return
		if not resultado.grupos:
			self.zc.anunciar(motor.resumen(resultado), api.RESULTADO)
			return
		self.mostrar_resultados(resultado)

	def mostrar_resultados(self, resultado: motor.Resultado) -> None:
		from . import ui

		acciones = {"ir": self._ir, "papelera": self._papelera, "enlaces": self._enlaces, "exportar": self._exportar,
			"panel": self._panel}
		dialogo = ui.DialogoResultados(None, self.zc, resultado, acciones)
		self._dialogo = dialogo
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			self._dialogo = None
			dialogo.Destroy()

	# Acciones de la lista ------------------------------------------------------

	def _ir(self, dialogo: Any) -> None:
		archivo = dialogo.archivo_actual()
		if archivo is None:
			return
		self.zc.abrir_ruta(archivo.ruta)
		dialogo.EndModal(0)

	def _comprobar_copias(self, dialogo: Any, marcadas: set[str]) -> bool:
		if not marcadas:
			self.zc.anunciar(_("No hay copias marcadas"), api.RESULTADO)
			return False
		sin_copia = motor.grupos_sin_copia(dialogo.resultado.grupos, marcadas)
		if sin_copia:
			self.zc.ui.mostrar_error(_("En el grupo {g} están marcadas todas las copias. Deje sin marcar al menos una.").format(
				g=sin_copia[0] + 1), _("Duplicados"), dialogo)
			return False
		return True

	def _papelera(self, dialogo: Any) -> None:
		marcadas = dialogo.marcadas()
		if not self._comprobar_copias(dialogo, marcadas):
			return
		archivos = [a for g in dialogo.resultado.grupos for a in g.archivos if a.ruta in marcadas]
		if not self.zc.ui.confirmar(_("¿Enviar a la papelera {n} ({b})?").format(
				n=api.formato.plural(len(archivos), _("{n} copia"), _("{n} copias")),
				b=api.formato.tamano_legible(sum(a.tamano for a in archivos))), _("Enviar a la papelera"), dialogo, peligroso=True):
			return
		proveedor, _ruta = self.zc.vfs.resolver(archivos[0].carpeta)
		entradas = [api.Entrada(a.nombre, a.ruta, tamano=a.tamano, modificado=a.modificado) for a in archivos]
		self.zc.lanzar(api.OperacionEliminar(proveedor, entradas, papelera=True), al_terminar=lambda _o: self._refrescar(dialogo))

	def _enlaces(self, dialogo: Any) -> None:
		marcadas = dialogo.marcadas()
		if not self._comprobar_copias(dialogo, marcadas):
			return
		pares = []
		for grupo in dialogo.resultado.grupos:
			conservados = [a for a in grupo.archivos if a.ruta not in marcadas]
			if not conservados:
				continue
			original = conservados[0]
			pares.extend((original.ruta, a.ruta) for a in grupo.archivos if a.ruta in marcadas)
		otra_unidad = [c for o, c in pares if not motor.mismo_volumen(o, c)]
		if otra_unidad:
			self.zc.ui.mostrar_error(_("«{c}» está en otra unidad que la copia que se conserva: un enlace duro solo puede ir en la misma.").format(
				c=os.path.basename(otra_unidad[0])), _("Duplicados"), dialogo)
			return
		if not self.zc.ui.confirmar(_("¿Sustituir {n} por enlaces duros? Los archivos seguirán en su sitio, pero compartirán el contenido: "
				"cambiar uno cambia todos.").format(n=api.formato.plural(len(pares), _("{n} copia"), _("{n} copias"))),
				_("Enlaces duros"), dialogo, peligroso=True):
			return
		self.zc.lanzar(motor.OperacionEnlacesDuros(pares), al_terminar=lambda _o: self._refrescar(dialogo))

	def _refrescar(self, dialogo: Any) -> None:
		if self._dialogo is dialogo and dialogo:
			dialogo.recargar()

	def _exportar(self, dialogo: Any) -> None:
		import wx

		selector = wx.FileDialog(dialogo, _("Exportar el informe de duplicados"), defaultFile=_("duplicados.txt"),
			wildcard=_("Texto (*.txt)|*.txt|CSV para hojas de cálculo (*.csv)|*.csv"), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		try:
			if self.zc.ui.mostrar_modal(selector) != wx.ID_OK:
				return
			ruta = selector.GetPath()
		finally:
			selector.Destroy()
		exportar(ruta, dialogo.resultado, dialogo.marcadas())
		self.zc.anunciar(_("Informe guardado en {r}").format(r=ruta), api.RESULTADO)

	def _panel(self, dialogo: Any) -> None:
		marcadas = dialogo.marcadas()
		rutas = [a.ruta for g in dialogo.resultado.grupos for a in g.archivos if not marcadas or a.ruta in marcadas]
		self.zc.ui.mostrar_resultados(_("Duplicados"), rutas)
		dialogo.EndModal(0)

	def ventanas_para_revisar(self, padre: Any) -> list:
		"""Los dos diálogos, sin mostrar, para ``revisar_teclado`` (3.12). Necesita la interfaz (``zc.ui``)."""
		from . import ui

		try:
			buscar = ui.DialogoBuscar(padre, self.zc, ["C:\\"])
		except api.NoAdmitido:
			self.zc.registro.info("Sin interfaz: las ventanas se revisan en las pruebas del bloque")
			return []
		archivo = motor.Archivo("C:\\a\\x.txt", "x.txt", 10, 0.0)
		resultado = motor.Resultado([motor.Grupo([archivo, motor.Archivo("C:\\b\\x.txt", "x.txt", 10, 0.0)])], revisados=2)
		return [buscar, ui.DialogoResultados(padre, self.zc, resultado)]


def exportar(ruta: str, resultado: motor.Resultado, marcadas: set[str]) -> None:
	"""Informe en texto, o en CSV si la ruta acaba en .csv (UTF-8 con BOM para que lo abra bien una hoja de cálculo)."""
	if ruta.casefold().endswith(".csv"):
		contenido, codificacion = motor.informe_csv(resultado, marcadas), "utf-8-sig"
	else:
		contenido, codificacion = motor.informe_texto(resultado, marcadas), "utf-8"
	with open(ruta, "w", encoding=codificacion, newline="") as archivo:
		archivo.write(contenido)
