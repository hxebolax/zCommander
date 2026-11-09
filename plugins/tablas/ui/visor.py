# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Visor de tabla: una ventana no modal con la tabla en una lista que se lee por columnas.

Teclas (menú «&Tabla»): Ctrl+F filtrar, Ctrl+G ir a una fila, Ctrl+O ordenar
por la columna actual (otra vez, al revés), Ctrl+E exportar a CSV, F5 consulta
SQL (solo bases SQLite), Ctrl+T estructura de la tabla. En la lista:
Izquierda y Derecha cambian de columna y Ctrl+1 a Ctrl+0 leen una columna.
Escape cierra, F1 abre la ayuda y Ctrl+H dice la ayuda del control.

Los datos se leen en un hilo: la ventana se abre enseguida con «Cargando...».
"""

from __future__ import annotations

import builtins
import os
from collections.abc import Callable
from typing import Any

import wx

from ..servicios import datos as servicio_datos
from .comun import atender_ctrl_h
from .lista import clase_lista


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class VisorTabla:
	"""Ventana del visor y su lógica. ``ventana`` es la ``VentanaComplemento`` (un ``wx.Frame``).

	:param cargar: ``cargar(cancelacion) -> Tabla``; se llama en un hilo del complemento.
	:param base_sqlite: ruta local de la base si la tabla es de SQLite (activa la consulta SQL).
	:param al_consulta: abre el diálogo de consulta para esa base.
	"""

	def __init__(self, zc: Any, titulo: str, cargar: Callable[[Any], servicio_datos.Tabla] | None, base_sqlite: str = "",
			al_consulta: Callable[[wx.Window, str], None] | None = None, padre: wx.Window | None = None) -> None:
		self.zc = zc
		self.ui = zc.ui
		self.tabla: servicio_datos.Tabla | None = None
		self.indices: list[int] = []
		self.filtro = ""
		self.orden: tuple[int, bool] | None = None
		self.base_sqlite = base_sqlite
		self._al_consulta = al_consulta
		self._tarea: Any = None
		ventana = self.ui.VentanaComplemento(padre, _("{t} - Visor de tabla").format(t=titulo), zc.id)
		self.ventana = ventana
		self.titulo = titulo
		self._crear_menus()
		panel = wx.Panel(ventana)
		raiz = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(panel, label=_("&Datos:"))
		self.lista = clase_lista(self.ui.ListaAccesible)(panel, titulo)
		self.lista.SetHelpText(_("Filas de la tabla. Izquierda y Derecha cambian de columna; Control más un número lee esa "
			"columna. Menú Tabla: Control+F filtra, Control+G va a una fila, Control+O ordena por la columna actual, "
			"Control+E exporta a CSV, Control+T dice la estructura."))
		raiz.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		_e, self.estado = self.ui.crear_campo(panel, _("E&stado:"), wx.TextCtrl, sizer=raiz, horizontal=True,
			value=_("Cargando..."), style=wx.TE_READONLY, ayuda=_("Filas, columnas, filtro y orden de la tabla."))
		panel.SetSizer(raiz)
		ventana.SetSize(ventana.FromDIP(wx.Size(900, 600)))
		atender_ctrl_h(ventana, lambda texto: self.zc.anunciar(texto))
		ventana.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.lista.SetFocus()
		if cargar is not None:
			self.cargar(cargar)

	# ── Menús ───────────────────────────────────────────────────────────────

	def _crear_menus(self) -> None:
		menu = wx.Menu()
		elementos = [
			(_("&Filtrar...\tCtrl+F"), _("Muestra solo las filas que contienen un texto"), self.filtrar),
			(_("&Ir a la fila...\tCtrl+G"), _("Va a una fila por su número"), self.ir_a_fila),
			(_("&Ordenar por la columna actual\tCtrl+O"), _("Ordena por la columna en la que está; otra vez, al revés"),
				self.ordenar),
			(_("&Exportar a CSV...\tCtrl+E"), _("Guarda las filas visibles en un archivo CSV"), self.exportar),
			(_("E&structura de la tabla\tCtrl+T"), _("Dice las columnas y sus tipos"), self.mostrar_estructura),
		]
		if self.base_sqlite:
			elementos.insert(4, (_("&Consulta SQL...\tF5"), _("Ejecuta una consulta SQL sobre la base"), self.consulta))
		for etiqueta, ayuda, accion in elementos:
			elemento = menu.Append(wx.ID_ANY, etiqueta, ayuda)
			self.ventana.Bind(wx.EVT_MENU, lambda _evento, a=accion: a(), elemento)
		menu.AppendSeparator()
		cerrar = menu.Append(wx.ID_CLOSE, _("Ce&rrar"), _("Cierra el visor (también Escape)"))
		self.ventana.Bind(wx.EVT_MENU, lambda _evento: self.ventana.Close(), cerrar)
		barra = wx.MenuBar()
		barra.Append(menu, _("&Tabla"))
		self.ventana.SetMenuBar(barra)

	# ── Carga ──────────────────────────────────────────────────────────────

	def cargar(self, cargar: Callable[[Any], servicio_datos.Tabla]) -> None:
		self.estado.SetValue(_("Cargando..."))
		self._tarea = self.zc.tareas.enviar(lambda tarea: cargar(tarea), al_terminar=self._cargada, al_fallar=self._fallo,
			nombre="zc.tablas:cargar")

	def _cargada(self, tabla: servicio_datos.Tabla) -> None:
		if not self.ventana:
			return
		self.mostrar(tabla)
		self.zc.anunciar(self.estado.GetValue(), "resultado")

	def _fallo(self, error: BaseException) -> None:
		if not self.ventana:
			return
		if type(error).__name__ in ("TareaCancelada", "Cancelado"):
			return
		texto = getattr(error, "mensaje", "") or str(error)
		self.estado.SetValue(_("No se pudo leer la tabla: {e}").format(e=texto))
		self.zc.anunciar(self.estado.GetValue(), "esencial")

	def mostrar(self, tabla: servicio_datos.Tabla) -> None:
		"""Pone ``tabla`` en la lista (también la usan las pruebas, sin hilos)."""
		self.tabla = tabla
		self.filtro = ""
		self.orden = None
		self.indices = list(range(len(tabla.filas)))
		self.lista.fijar(tabla, self.indices, cabeceras_nuevas=True)
		self._actualizar_estado()

	def _actualizar_estado(self) -> None:
		tabla = self.tabla
		if tabla is None:
			return
		partes = [_("{o} {n}: {f} filas y {c} columnas").format(o=tabla.origen.capitalize(), n=tabla.nombre,
			f=len(tabla.filas), c=tabla.num_columnas)]
		if tabla.truncada:
			partes.append(_("solo se leyeron las primeras {f} filas").format(f=len(tabla.filas)))
		if self.filtro:
			partes.append(_("filtro «{t}»: {n} filas").format(t=self.filtro, n=len(self.indices)))
		if self.orden is not None:
			columna, descendente = self.orden
			partes.append(_("ordenada por {c}, {s}").format(c=tabla.cabeceras[columna],
				s=_("de mayor a menor") if descendente else _("de menor a mayor")))
		self.estado.SetValue(". ".join(partes) + ".")

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self._tarea is not None:
			self.zc.tareas.cancelar(self._tarea)
		evento.Skip()

	# ── Acciones ───────────────────────────────────────────────────────────

	def _sin_datos(self) -> bool:
		if self.tabla is None:
			self.zc.anunciar(_("La tabla aún se está cargando"), "esencial")
			return True
		return False

	def aplicar_filtro(self, texto: str) -> None:
		self.filtro = texto.strip()
		self.indices = servicio_datos.filtrar(self.tabla, self.filtro)
		if self.orden is not None:
			self.indices = servicio_datos.ordenar(self.tabla, self.indices, *self.orden)
		self.lista.fijar(self.tabla, self.indices)
		self._actualizar_estado()

	def filtrar(self) -> None:
		if self._sin_datos():
			return
		texto = self.ui.pedir_texto(_("Mostrar solo las filas que contienen (vacío quita el filtro):"), _("Filtrar"),
			self.filtro, padre=self.ventana)
		if texto is None:
			return
		self.aplicar_filtro(texto)
		self.zc.anunciar(_("{n} filas").format(n=len(self.indices)) if self.filtro else _("Filtro quitado"), "resultado")

	def ir_a_fila(self) -> None:
		if self._sin_datos():
			return
		texto = self.ui.pedir_texto(_("Número de fila, de 1 a {n}:").format(n=len(self.indices)), _("Ir a la fila"), "",
			padre=self.ventana)
		if not texto:
			return
		try:
			numero = int(texto.strip())
		except ValueError:
			self.zc.anunciar(_("Escriba un número de fila"), "esencial")
			return
		if not 1 <= numero <= len(self.indices):
			self.zc.anunciar(_("No hay fila {n}; hay {t}").format(n=numero, t=len(self.indices)), "esencial")
			return
		self.lista.enfocar_fila(numero - 1)
		self.lista.SetFocus()

	def ordenar_por(self, columna: int) -> None:
		descendente = self.orden is not None and self.orden == (columna, False)
		self.orden = (columna, descendente)
		self.indices = servicio_datos.ordenar(self.tabla, self.indices, columna, descendente)
		self.lista.fijar(self.tabla, self.indices)
		self._actualizar_estado()

	def ordenar(self) -> None:
		if self._sin_datos() or not self.tabla.num_columnas:
			return
		columna = min(self.lista.columna_actual(), self.tabla.num_columnas - 1)
		self.ordenar_por(columna)
		self.zc.anunciar(_("Ordenada por {c}, {s}").format(c=self.tabla.cabeceras[columna],
			s=_("de mayor a menor") if self.orden[1] else _("de menor a mayor")), "resultado")

	def filas_visibles(self) -> list[tuple[str, ...]]:
		return [self.tabla.filas[i] for i in self.indices] if self.tabla else []

	def exportar(self) -> None:
		if self._sin_datos():
			return
		dialogo = wx.FileDialog(self.ventana, _("Exportar a CSV"), defaultFile=_nombre_csv(self.tabla.nombre),
			wildcard=_("Archivos CSV (*.csv)|*.csv|Todos los archivos (*.*)|*.*"), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		try:
			if self.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			destino = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		cabeceras, filas = list(self.tabla.cabeceras), self.filas_visibles()

		def escribir(_tarea: Any) -> int:
			with open(destino, "w", encoding="utf-8-sig", newline="") as salida:
				salida.write(servicio_datos.a_csv(cabeceras, filas))
			return len(filas)

		self.zc.tareas.enviar(escribir,
			al_terminar=lambda n: self.zc.anunciar(_("Exportadas {n} filas a {a}").format(n=n, a=os.path.basename(destino)), "resultado"),
			al_fallar=lambda e: self.zc.anunciar(_("No se pudo exportar: {e}").format(e=e), "esencial"))

	def consulta(self) -> None:
		if self._al_consulta is not None and self.base_sqlite:
			self._al_consulta(self.ventana, self.base_sqlite)

	def texto_estructura(self) -> str:
		tabla = self.tabla
		if tabla is None:
			return ""
		lineas = [_("{o} {n}: {c} columnas.").format(o=tabla.origen.capitalize(), n=tabla.nombre, c=tabla.num_columnas)]
		if tabla.estructura:
			lineas.extend(_("{c}: {t}.").format(c=c, t=t) for c, t in tabla.estructura)
		else:
			if tabla.codificacion:
				lineas.append(_("Codificación: {c}.").format(c=tabla.codificacion))
			if tabla.separador:
				lineas.append(_("Separador: {s}.").format(s=servicio_datos.NOMBRES_SEPARADOR.get(tabla.separador, tabla.separador)))
			lineas.extend(_("Columna {n}: {c}.").format(n=i + 1, c=c) for i, c in enumerate(tabla.cabeceras))
		return "\n".join(lineas)

	def mostrar_estructura(self) -> None:
		if self._sin_datos():
			return
		self.ui.mostrar_texto(_("Estructura de {n}").format(n=self.tabla.nombre), self.texto_estructura(), padre=self.ventana)

	def mostrar_ventana(self) -> None:
		self.ventana.Show()
		self.ventana.Raise()
		self.lista.SetFocus()


def _nombre_csv(nombre: str) -> str:
	limpio = "".join("_" if c in '<>:"/\\|?*' else c for c in nombre).strip() or "tabla"
	return limpio if limpio.lower().endswith(".csv") else limpio + ".csv"
