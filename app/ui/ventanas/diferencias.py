# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana de comparación de dos archivos por contenido (sección 8.19, bloque A).

La usan la orden «Comparar archivos por contenido», la lista de conflictos
(núcleo) y la sincronización de carpetas (bloque B), siempre con la misma
firma: ``abrir(padre, (proveedor, ruta), (proveedor, ruta))``.

Por qué está hecha así:

- La comparación (``app/services/comparar_archivos.py``) va en un hilo: leer
  dos archivos de un servidor o de un comprimido puede tardar.
- Las diferencias son una **lista nativa** con su etiqueta («Línea 12:
  cambiada»): el lector dice cada una al recorrerla con las flechas. Para la
  elegida, las dos versiones van en dos campos de solo lectura, que se
  pueden repasar línea a línea y copiar.
- «Siguiente» y «Anterior» mueven la lista sin quitar el foco del botón, así
  que dicen la diferencia a la que llegan (el lector no la leería sola).
- En archivos binarios hay una sola fila («Distintos a partir del byte
  4096») y los campos muestran el volcado hexadecimal de esa zona en cada uno.
- Si hay un programa externo de diferencias configurado
  (``general.diferencias_externo``, con %P y %T), se usa ese en su lugar.
"""

from __future__ import annotations

import builtins
import logging
import os
from typing import Any

import wx

from app.core.tareas import TareaCancelada
from app.services import codificacion, comparar_archivos, formato
from app.services.vfs import base
from app.ui import anuncios
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.ventanas.visor import configuracion_de, extraer, mensaje_error, tareas_de

log = logging.getLogger(__name__)

#: Bytes del volcado que se muestra en cada lado para los binarios.
MUESTRA_HEX = 128


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _leer_desde(proveedor: base.Proveedor, ruta: str, inicio: int, cantidad: int) -> bytes:
	"""Bytes de una zona del archivo (con ``seek`` si el flujo lo admite; si no, leyendo hasta ahí)."""
	with proveedor.abrir_lectura(ruta) as flujo:
		try:
			flujo.seek(inicio)
		except (OSError, AttributeError, ValueError):
			pendiente = inicio
			while pendiente > 0:
				trozo = flujo.read(min(pendiente, 1024 * 1024))
				if not trozo:
					return b""
				pendiente -= len(trozo)
		return flujo.read(cantidad)


class VentanaDiferencias(wx.Frame):
	"""Diferencias entre dos archivos. Escape o «Cerrar» la cierran."""

	def __init__(self, padre: wx.Window | None, izquierda: tuple[Any, str], derecha: tuple[Any, str], tareas=None) -> None:
		self.izquierda, self.derecha = izquierda, derecha
		self.nombre_izq = izquierda[0].nombre(izquierda[1]) or izquierda[1]
		self.nombre_der = derecha[0].nombre(derecha[1]) or derecha[1]
		titulo = _("Comparar {a} y {b}").format(a=self.nombre_izq, b=self.nombre_der)
		super().__init__(padre, title=titulo, name=titulo)
		self.SetSize(self.FromDIP(wx.Size(900, 700)))
		self.tareas = tareas or tareas_de(padre)
		self.resultado: comparar_archivos.Resultado | None = None
		self._extra: tuple[str, str] | None = None
		self._tarea = None
		self._cerrando = False

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.resumen = crear_campo(panel, _("&Resumen:"), wx.TextCtrl,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=panel.FromDIP(wx.Size(-1, 70)),
			ayuda=_("Resultado de la comparación y qué archivo está a cada lado."), sizer=sizer)
		_etiqueta, self.lista = crear_campo(panel, _("&Diferencias:"), wx.ListBox, style=wx.LB_SINGLE,
			size=panel.FromDIP(wx.Size(-1, 160)),
			ayuda=_("Cada tramo distinto. Al elegir uno, sus líneas de cada archivo aparecen debajo."), sizer=sizer)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		columna_izq = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.texto_izq = crear_campo(panel, _("Texto del &izquierdo ({n}):").format(n=self.nombre_izq), wx.TextCtrl,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_DONTWRAP,
			ayuda=_("Las líneas de la diferencia elegida tal como están en el primer archivo."), sizer=columna_izq)
		columna_der = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.texto_der = crear_campo(panel, _("Texto del d&erecho ({n}):").format(n=self.nombre_der), wx.TextCtrl,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_DONTWRAP,
			ayuda=_("Las líneas de la diferencia elegida tal como están en el segundo archivo."), sizer=columna_der)
		for columna in (columna_izq, columna_der):
			for hijo in columna.GetChildren():
				if hijo.GetWindow() and isinstance(hijo.GetWindow(), wx.TextCtrl):
					hijo.SetProportion(1)
			fila.Add(columna, 1, wx.EXPAND)
		sizer.Add(fila, 1, wx.EXPAND)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_siguiente = wx.Button(panel, label=_("&Siguiente"))
		self.boton_siguiente.SetHelpText(_("Va a la diferencia siguiente y la dice."))
		self.boton_anterior = wx.Button(panel, label=_("&Anterior"))
		self.boton_anterior.SetHelpText(_("Va a la diferencia anterior y la dice."))
		self.boton_otra_vez = wx.Button(panel, label=_("&Volver a comparar"))
		self.boton_otra_vez.SetHelpText(_("Vuelve a leer los dos archivos y los compara de nuevo."))
		self.boton_cerrar = wx.Button(panel, wx.ID_CLOSE, _("&Cerrar"))
		self.boton_cerrar.SetHelpText(_("Cierra esta ventana (también Escape)."))
		for boton in (self.boton_siguiente, self.boton_anterior, self.boton_otra_vez, self.boton_cerrar):
			botones.Add(boton, 0, wx.ALL, 5)
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		panel.SetSizer(sizer)

		self.lista.Bind(wx.EVT_LISTBOX, lambda _e: self._mostrar_elegida())
		self.boton_siguiente.Bind(wx.EVT_BUTTON, lambda _e: self.mover(1))
		self.boton_anterior.Bind(wx.EVT_BUTTON, lambda _e: self.mover(-1))
		self.boton_otra_vez.Bind(wx.EVT_BUTTON, lambda _e: self.comparar())
		self.boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.Close())
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.comparar()

	def mostrar(self) -> None:
		self.Show()
		self.Raise()
		self.lista.SetFocus()

	# Comparación --------------------------------------------------------------

	def comparar(self) -> None:
		(prov_izq, ruta_izq), (prov_der, ruta_der) = self.izquierda, self.derecha
		self.resultado = None
		self.lista.Set([_("Comparando...")])
		self.lista.SetSelection(0)
		self.resumen.ChangeValue(_("Comparando..."))
		self.texto_izq.ChangeValue("")
		self.texto_der.ChangeValue("")

		def trabajo(tarea):
			info_izq, info_der = prov_izq.info(ruta_izq), prov_der.info(ruta_der)
			resultado = comparar_archivos.comparar(
				lambda: prov_izq.abrir_lectura(ruta_izq), lambda: prov_der.abrir_lectura(ruta_der),
				info_izq.tamano, info_der.tamano, tarea)
			extra = None
			if not resultado.es_texto and resultado.primer_distinto is not None:
				inicio = max(0, (resultado.primer_distinto // 16) * 16 - 16)
				extra = (
					codificacion.hexadecimal(_leer_desde(prov_izq, ruta_izq, inicio, MUESTRA_HEX), inicio),
					codificacion.hexadecimal(_leer_desde(prov_der, ruta_der, inicio, MUESTRA_HEX), inicio),
				)
			return resultado, extra

		def fallo(error: BaseException) -> None:
			if isinstance(error, TareaCancelada) or self._cerrando or not self:
				return
			texto = _("No se pudieron comparar: {e}").format(e=mensaje_error(error))
			self.lista.Set([texto])
			self.lista.SetSelection(0)
			self.resumen.ChangeValue(texto)
			anuncios.anunciar(texto, anuncios.ESENCIAL)

		def listo(respuesta) -> None:
			if self._cerrando or not self:
				return
			self.mostrar_resultado(*respuesta)

		self._tarea = self.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre="comparar-archivos")

	def filas(self) -> list[str]:
		resultado = self.resultado
		if resultado is None:
			return []
		if resultado.es_texto and resultado.diferencias:
			return [comparar_archivos.describir(d) for d in resultado.diferencias]
		return [comparar_archivos.resumen(resultado)]

	def mostrar_resultado(self, resultado: comparar_archivos.Resultado, extra: tuple[str, str] | None = None) -> None:
		self.resultado, self._extra = resultado, extra
		resumen = comparar_archivos.resumen(resultado)
		lineas = [resumen]
		for lado, (proveedor, ruta), cod in ((_("Izquierdo"), self.izquierda, resultado.codificacion_izq),
				(_("Derecho"), self.derecha, resultado.codificacion_der)):
			detalle = proveedor.mostrar(ruta)
			if cod:
				detalle += f" ({codificacion.NOMBRES.get(cod, cod)})"
			lineas.append(f"{lado}: {detalle}")
		if resultado.es_texto:
			lineas.append(_("Líneas: {a} a la izquierda y {b} a la derecha").format(
				a=formato.miles(len(resultado.lineas_izq)), b=formato.miles(len(resultado.lineas_der))))
		if resultado.nota:
			lineas.append(resultado.nota)
		self.resumen.ChangeValue("\n".join(lineas))
		self.lista.Set(self.filas())
		self.lista.SetSelection(0)
		self._mostrar_elegida()
		anuncios.anunciar(resumen, anuncios.RESULTADO)

	def _mostrar_elegida(self) -> None:
		resultado = self.resultado
		indice = self.lista.GetSelection()
		if resultado is None or indice == wx.NOT_FOUND:
			return
		if not resultado.es_texto:
			izquierdo, derecho = self._extra or ("", "")
		elif resultado.diferencias:
			diferencia = resultado.diferencias[indice]
			izquierdo = "\n".join(resultado.lineas_izq[diferencia.inicio_izq:diferencia.fin_izq]) or _("(No hay líneas en este lado.)")
			derecho = "\n".join(resultado.lineas_der[diferencia.inicio_der:diferencia.fin_der]) or _("(No hay líneas en este lado.)")
		else:
			izquierdo = derecho = ""
		self.texto_izq.ChangeValue(izquierdo)
		self.texto_der.ChangeValue(derecho)

	def mover(self, paso: int) -> None:
		"""Siguiente o anterior diferencia; lo dice porque el foco sigue en el botón."""
		total = self.lista.GetCount()
		if self.resultado is None or total == 0:
			anuncios.anunciar(_("Todavía se está comparando"), anuncios.RESULTADO)
			return
		actual = self.lista.GetSelection()
		destino = (0 if paso > 0 else total - 1) if actual == wx.NOT_FOUND else actual + paso
		if destino < 0 or destino >= total:
			anuncios.anunciar(_("Es la primera diferencia") if destino < 0 else _("Es la última diferencia"), anuncios.RESULTADO)
			return
		self.lista.SetSelection(destino)
		self._mostrar_elegida()
		anuncios.anunciar(_("{d}. {i} de {t}").format(d=self.lista.GetString(destino), i=destino + 1, t=total), anuncios.RESULTADO)

	# Teclado y cierre --------------------------------------------------------

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla == wx.WXK_ESCAPE and modificadores == wx.MOD_NONE:
			self.Close()
			return
		if tecla == ord("H") and modificadores == wx.MOD_CONTROL:
			from app.ui.accesibilidad.ayuda import describir_control_enfocado

			describir_control_enfocado(self)
			return
		evento.Skip()

	def _al_cerrar(self, _evento: wx.CloseEvent) -> None:
		self._cerrando = True
		if self._tarea is not None:
			self._tarea.cancelar("Se cerró la comparación")
		self.Destroy()


def _ventana_principal(padre: wx.Window | None) -> wx.Window | None:
	"""La ventana principal (la que tiene el gestor de tareas), para que la comparación sobreviva al diálogo que la abrió."""
	actual = padre
	while actual is not None:
		if hasattr(actual, "lanzar_operacion"):
			return actual
		actual = actual.GetParent()
	return padre


def abrir_externo(padre: wx.Window | None, plantilla: str, izquierda: tuple[Any, str], derecha: tuple[Any, str]) -> None:
	"""Lanza el programa externo de diferencias con %P (izquierdo) y %T (derecho), extrayendo lo que no esté en el disco."""
	from app.services import variables
	from app.services.vfs import temporales
	from app.services.windows import shell_basico

	principal = _ventana_principal(padre)

	def trabajo(tarea):
		locales = []
		for proveedor, ruta in (izquierda, derecha):
			local = proveedor.ruta_local(ruta)
			if local is None:
				local = extraer(proveedor, ruta, tarea)
				locales.append((local, proveedor, ruta, True))
			else:
				locales.append((local, proveedor, ruta, False))
		return locales

	def listo(locales) -> None:
		(local_izq, *_r1), (local_der, *_r2) = locales
		if principal is not None and hasattr(principal, "lanzar_operacion"):
			from app.ui.acciones import archivos

			for local, proveedor, ruta, temporal in locales:
				if temporal:
					temporales.vigilados.vigilar(local, proveedor, ruta, archivos.ofrecer_actualizar_desde(principal))
		valores = variables.Valores(cursor=local_izq, carpeta=os.path.dirname(local_izq), otra_carpeta=os.path.dirname(local_der),
			cursor_otro=local_der, trabajo=[local_izq, local_der])

		def al_error(error: BaseException) -> None:
			wx.CallAfter(anuncios.anunciar, _("No se pudo abrir el programa de diferencias: {e}").format(e=error), anuncios.ESENCIAL)

		shell_basico.lanzar(variables.expandir_directo(plantilla, valores), os.path.dirname(local_izq), al_error)
		anuncios.anunciar(_("Comparando con el programa externo"), anuncios.DETALLE)

	def fallo(error: BaseException) -> None:
		if not isinstance(error, TareaCancelada):
			anuncios.anunciar(_("No se pudieron preparar los archivos: {e}").format(e=mensaje_error(error)), anuncios.ESENCIAL)

	tareas_de(padre).enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre="diferencias-externo")


def abrir(padre: Any, izquierda: tuple[Any, str], derecha: tuple[Any, str]) -> None:
	"""Abre la comparación de ``(proveedor, ruta)`` frente a ``(proveedor, ruta)`` (no modal).

	Firma fija: la usan el núcleo (lista de conflictos) y el bloque B (sincronizar).
	"""
	plantilla = str(configuracion_de(padre).obtener("general.diferencias_externo", "") or "").strip()
	if plantilla:
		abrir_externo(padre, plantilla, izquierda, derecha)
		return
	ventana = VentanaDiferencias(_ventana_principal(padre), izquierda, derecha, tareas_de(padre))
	ventana.mostrar()
