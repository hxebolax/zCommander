# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Consulta SQL» de una base SQLite.

«&SQL:» (texto de varias líneas; Ctrl+Intro ejecuta), «&Ejecutar», «&Resultados:»
(lista que se lee por columnas), «Es&tado:» (filas y errores), «E&xportar a CSV...»
y «&Cerrar». En solo lectura (por defecto), lo que cambiaría datos se rechaza
con un mensaje claro. La consulta corre en un hilo: la interfaz no se bloquea.
"""

from __future__ import annotations

import builtins
import os
from typing import Any

import wx

from ..servicios import datos as servicio_datos
from ..servicios import sqlite
from .comun import atender_f1, botonera
from .lista import clase_lista


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class DialogoConsulta(wx.Dialog):
	def __init__(self, padre: wx.Window | None, zc: Any, ruta_base: str, sql_inicial: str = "") -> None:
		super().__init__(padre, title=_("Consulta SQL: {n}").format(n=os.path.basename(ruta_base)),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self.ui = zc.ui
		self.ruta_base = ruta_base
		self.resultado: servicio_datos.Tabla | None = None
		self._tarea: Any = None
		raiz = wx.BoxSizer(wx.VERTICAL)
		solo_lectura = bool(zc.config.obtener("solo_lectura", True))
		_e, self.sql = self.ui.crear_campo(self, _("&SQL:"), wx.TextCtrl, sizer=raiz, value=sql_inicial,
			style=wx.TE_MULTILINE | wx.TE_PROCESS_TAB | wx.TE_DONTWRAP,
			ayuda=_("Una consulta SQL, por ejemplo SELECT * FROM clientes. Control+Intro la ejecuta.")
				+ (" " + _("La base está en solo lectura: las consultas que cambian datos se rechazan.") if solo_lectura else ""))
		self.sql.SetMinSize(self.FromDIP(wx.Size(600, 90)))
		self.ejecutar_boton = wx.Button(self, label=_("&Ejecutar"))
		self.ejecutar_boton.SetHelpText(_("Ejecuta la consulta y muestra sus filas en Resultados."))
		raiz.Add(self.ejecutar_boton, 0, wx.ALL, 5)
		etiqueta = wx.StaticText(self, label=_("&Resultados:"))
		self.lista = clase_lista(self.ui.ListaAccesible)(self, _("Resultados"))
		self.lista.SetHelpText(_("Filas del resultado. Izquierda y Derecha cambian de columna."))
		raiz.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		_e, self.estado = self.ui.crear_campo(self, _("Es&tado:"), wx.TextCtrl, sizer=raiz, horizontal=True,
			value=_("Escriba una consulta y pulse Ejecutar."), style=wx.TE_READONLY,
			ayuda=_("Filas del resultado o el error de la consulta."))
		self.exportar_boton = wx.Button(self, label=_("E&xportar a CSV..."))
		self.exportar_boton.SetHelpText(_("Guarda el resultado en un archivo CSV."))
		self.exportar_boton.Disable()
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(self.exportar_boton, 0, wx.RIGHT, 10)
		fila.AddStretchSpacer()
		fila.Add(botonera(self, [(wx.ID_CANCEL, _("&Cerrar"))], wx.ID_CANCEL), 0)
		raiz.Add(fila, 0, wx.EXPAND | wx.ALL, 5)
		self.SetSizerAndFit(raiz)
		self.SetSize(self.FromDIP(wx.Size(760, 560)))
		self.ui.preparar_dialogo(self, foco_inicial=self.sql)
		atender_f1(self, getattr(zc, "abrir_ayuda", None))
		self.ejecutar_boton.Bind(wx.EVT_BUTTON, lambda _e: self.ejecutar())
		self.exportar_boton.Bind(wx.EVT_BUTTON, lambda _e: self.exportar())
		self.sql.Bind(wx.EVT_KEY_DOWN, self._al_tecla_sql)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)

	def _al_tecla_sql(self, evento: wx.KeyEvent) -> None:
		# atajo: Ctrl+Intro
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.GetModifiers() == wx.MOD_CONTROL:
			self.ejecutar()
			return
		evento.Skip()

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self and self._tarea is not None:
			self.zc.tareas.cancelar(self._tarea)
		evento.Skip()

	def ejecutar(self) -> None:
		texto = self.sql.GetValue()
		solo_lectura = bool(self.zc.config.obtener("solo_lectura", True))
		maximas = int(self.zc.config.obtener("filas_maximas", 1_000_000))
		self.estado.SetValue(_("Ejecutando..."))
		self.ejecutar_boton.Disable()
		self._tarea = self.zc.tareas.enviar(lambda tarea: sqlite.consultar(self.ruta_base, texto, solo_lectura, maximas, tarea),
			al_terminar=self.mostrar_resultado, al_fallar=self._fallo, nombre="zc.tablas:consulta")

	def mostrar_resultado(self, tabla: servicio_datos.Tabla) -> None:
		if not self:
			return
		self.ejecutar_boton.Enable()
		self.resultado = tabla
		self.lista.fijar(tabla, range(len(tabla.filas)), cabeceras_nuevas=True)
		texto = _("{f} filas y {c} columnas.").format(f=len(tabla.filas), c=tabla.num_columnas)
		if tabla.truncada:
			texto += " " + _("Solo se muestran las primeras {f}.").format(f=len(tabla.filas))
		self.estado.SetValue(texto)
		self.exportar_boton.Enable(bool(tabla.filas))
		self.zc.anunciar(texto, "resultado")

	def _fallo(self, error: BaseException) -> None:
		if not self:
			return
		self.ejecutar_boton.Enable()
		if type(error).__name__ in ("TareaCancelada", "Cancelado"):
			return
		self.estado.SetValue(str(error))
		self.zc.anunciar(str(error), "esencial")

	def exportar(self) -> None:
		if self.resultado is None:
			return
		dialogo = wx.FileDialog(self, _("Exportar a CSV"), defaultFile=_("resultado.csv"),
			wildcard=_("Archivos CSV (*.csv)|*.csv|Todos los archivos (*.*)|*.*"), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		try:
			if self.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			destino = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		try:
			with open(destino, "w", encoding="utf-8-sig", newline="") as salida:
				salida.write(servicio_datos.a_csv(self.resultado.cabeceras, self.resultado.filas))
		except OSError as error:
			self.zc.anunciar(_("No se pudo exportar: {e}").format(e=error.strerror or error), "esencial")
			return
		self.zc.anunciar(_("Exportado a {a}").format(a=os.path.basename(destino)), "resultado")
