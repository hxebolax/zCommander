# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos del programador de tareas (diseño 2.0, 11.24). Con wx: se importa al abrirlos.

- «Programador de tareas»: lista de tareas (Nombre, Qué hace, Cuándo, Última
  ejecución, Resultado, Activa) y un estado que dice si se usan las tareas de
  Windows. Intro edita y Supr borra (pregunta con el foco en «No»).
- «Tarea programada»: el editor; solo se habilitan los campos que usan el
  tipo y la frecuencia elegidos, y la etiqueta del objetivo dice qué escribir.
- «Registro de ejecuciones»: resultado de cada ejecución y, abajo, sus
  detalles con las decisiones tomadas sin preguntar.
"""

from __future__ import annotations

import time

import wx

from app.plugins import api

from . import tareas


def _boton(padre: wx.Window, etiqueta: str, ayuda: str, sizer: wx.Sizer, al_pulsar=None, id_boton: int = wx.ID_ANY) -> wx.Button:
	boton = wx.Button(padre, id_boton, etiqueta)
	boton.SetHelpText(ayuda)
	if al_pulsar is not None:
		boton.Bind(wx.EVT_BUTTON, lambda _e: al_pulsar())
	sizer.Add(boton, 0, wx.ALL, 4)
	return boton


def _fecha(momento: float) -> str:
	return time.strftime("%d/%m/%Y %H:%M", time.localtime(momento)) if momento else "Nunca"


class DialogoTarea(wx.Dialog):
	"""Crea o cambia una tarea. ``tarea()`` la devuelve con lo escrito (conserva su id)."""

	_TIPOS = list(tareas.TIPOS)
	_FRECUENCIAS = list(tareas.FRECUENCIAS)
	_CONFLICTOS = list(tareas.CONFLICTOS)
	_ERRORES = list(tareas.ERRORES)

	def __init__(self, zc: api.Anfitrion, padre: wx.Window | None, tarea: tareas.Tarea) -> None:
		super().__init__(padre, title="Tarea programada", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self._base = tarea
		ui = zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		_, self.nombre = ui.crear_campo(self, "&Nombre:", wx.TextCtrl, sizer=cuerpo, value=tarea.nombre,
			ayuda="Nombre de la tarea; se dice al terminar y sale en el registro.")
		_, self.tipo = ui.crear_campo(self, "&Qué hace:", wx.Choice, sizer=cuerpo, choices=[tareas.TIPOS[t] for t in self._TIPOS],
			ayuda="Qué ejecuta la tarea: una sincronización, una copia, las reglas del monitor, una limpieza, una macro, "
				"una entrada del menú de usuario o una orden.")
		self.tipo.SetSelection(self._TIPOS.index(tarea.tipo))
		self.etiqueta_objetivo, self.objetivo = ui.crear_campo(self, "&Objetivo:", wx.TextCtrl, sizer=cuerpo, value=tarea.objetivo)
		_, self.destino = ui.crear_campo(self, "&Destino (solo al copiar):", wx.TextCtrl, sizer=cuerpo, value=tarea.destino,
			ayuda="Carpeta adonde se copia. En una orden, el argumento que recibe (opcional).")
		_, self.dias = ui.crear_campo(self, "Días de anti&güedad (solo al limpiar):", wx.SpinCtrl, sizer=cuerpo, min=0, max=36500,
			initial=tarea.dias, ayuda="La limpieza manda a la papelera los archivos modificados hace más de estos días.")
		_, self.frecuencia = ui.crear_campo(self, "&Frecuencia:", wx.Choice, sizer=cuerpo,
			choices=[tareas.FRECUENCIAS[f] for f in self._FRECUENCIAS], ayuda="Cuándo se ejecuta la tarea.")
		self.frecuencia.SetSelection(self._FRECUENCIAS.index(tarea.frecuencia))
		_, self.hora = ui.crear_campo(self, "&Hora (HH:MM):", wx.TextCtrl, sizer=cuerpo, value=tarea.hora,
			ayuda="Hora del día, de 00:00 a 23:59.")
		_, self.fecha = ui.crear_campo(self, "Fecha, &una vez o primer día (AAAA-MM-DD):", wx.TextCtrl, sizer=cuerpo,
			value=tarea.fecha, ayuda="Día de la ejecución única o, en las demás, desde cuándo. Vacío: desde hoy.")
		etiqueta = wx.StaticText(self, label="Días de la se&mana:")
		self.dias_semana = ui.CheckListBoxAccesible(self, "Días de la semana", tareas.DIAS)
		self.dias_semana.SetHelpText("Días en los que se ejecuta una tarea semanal. Espacio marca o desmarca.")
		for dia in tarea.dias_semana:
			if 0 <= dia < 7:
				self.dias_semana.Check(dia)
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.dias_semana, 0, wx.EXPAND | wx.ALL, 5)
		_, self.conflicto = ui.crear_campo(self, "Si el destino e&xiste:", wx.Choice, sizer=cuerpo,
			choices=[tareas.CONFLICTOS[c] for c in self._CONFLICTOS],
			ayuda="Respuesta automática a un archivo que ya existe: la tarea no pregunta.")
		self.conflicto.SetSelection(self._CONFLICTOS.index(tarea.conflicto) if tarea.conflicto in self._CONFLICTOS else 0)
		_, self.error = ui.crear_campo(self, "Ante un &error:", wx.Choice, sizer=cuerpo, choices=[tareas.ERRORES[e] for e in self._ERRORES],
			ayuda="Respuesta automática a un error: omitir ese elemento o cancelar la tarea.")
		self.error.SetSelection(self._ERRORES.index(tarea.error) if tarea.error in self._ERRORES else 0)
		self.activa = wx.CheckBox(self, label="Tarea act&iva")
		self.activa.SetValue(tarea.activa)
		self.activa.SetHelpText("Una tarea desactivada se conserva pero no se ejecuta sola.")
		cuerpo.Add(self.activa, 0, wx.ALL, 5)
		cuerpo.Add(ui.crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(cuerpo)
		self.tipo.Bind(wx.EVT_CHOICE, lambda _e: self._habilitar())
		self.frecuencia.Bind(wx.EVT_CHOICE, lambda _e: self._habilitar())
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		self._habilitar()
		ui.preparar_dialogo(self, foco_inicial=self.nombre)

	def _habilitar(self) -> None:
		tipo = self._TIPOS[max(0, self.tipo.GetSelection())]
		frecuencia = self._FRECUENCIAS[max(0, self.frecuencia.GetSelection())]
		# La etiqueta dice qué escribir; el lector la lee al llegar al campo. La letra (O) no cambia.
		self.etiqueta_objetivo.SetLabel(f"&Objetivo, {tareas.OBJETIVOS[tipo]}:")
		self.objetivo.SetHelpText(f"Escriba el {tareas.OBJETIVOS[tipo]}.")
		self.destino.Enable(tipo in (tareas.COPIA, tareas.ORDEN))
		self.dias.Enable(tipo == tareas.LIMPIEZA)
		self.conflicto.Enable(tipo in (tareas.COPIA, tareas.SINCRONIZACION, tareas.REGLAS))
		self.error.Enable(tipo not in (tareas.MACRO, tareas.MENU_USUARIO, tareas.ORDEN))
		self.hora.Enable(frecuencia != tareas.AL_INICIAR_SESION)
		self.fecha.Enable(frecuencia != tareas.AL_INICIAR_SESION)
		self.dias_semana.Enable(frecuencia == tareas.SEMANAL)

	def tarea(self) -> tareas.Tarea:
		return tareas.Tarea(nombre=self.nombre.GetValue().strip(), tipo=self._TIPOS[max(0, self.tipo.GetSelection())],
			objetivo=self.objetivo.GetValue().strip(), destino=self.destino.GetValue().strip(), dias=self.dias.GetValue(),
			frecuencia=self._FRECUENCIAS[max(0, self.frecuencia.GetSelection())], hora=self.hora.GetValue().strip(),
			fecha=self.fecha.GetValue().strip(), dias_semana=list(self.dias_semana.GetCheckedItems()),
			conflicto=self._CONFLICTOS[max(0, self.conflicto.GetSelection())], error=self._ERRORES[max(0, self.error.GetSelection())],
			activa=self.activa.GetValue(), id=self._base.id, ultima=self._base.ultima, resultado=self._base.resultado)

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		problema = self.tarea().error_de_datos()
		if problema:
			self.zc.ui.mostrar_error(problema, "Tarea programada", self)
			return
		evento.Skip()


class DialogoTareas(wx.Dialog):
	def __init__(self, complemento, padre: wx.Window | None, propuesta: str = "") -> None:
		super().__init__(padre, title="Programador de tareas", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, size=(860, 480))
		self.complemento = complemento
		self.zc: api.Anfitrion = complemento.zc
		self.propuesta = propuesta
		ui = self.zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		_, self.estado = ui.crear_campo(self, "E&stado:", wx.TextCtrl, sizer=cuerpo, style=wx.TE_READONLY,
			ayuda="Cómo se ejecutan las tareas: con el Programador de tareas de Windows o solo con zCommander abierto.")
		etiqueta = wx.StaticText(self, label="&Tareas programadas:")
		self.lista = ui.ListaAccesible(self, "Tareas programadas", [("Nombre", 140), ("Qué hace", 240), ("Cuándo", 190),
			("Última ejecución", 120), ("Resultado", 110), ("Activa", 60)])
		self.lista.SetHelpText("Tareas programadas. Intro edita la tarea; Supr la borra.")
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		botones = wx.WrapSizer(wx.HORIZONTAL)
		_boton(self, "&Nueva...", "Crea una tarea programada.", botones, self.nueva)
		self.boton_editar = _boton(self, "&Editar...", "Cambia la tarea elegida.", botones, self.editar)
		self.boton_borrar = _boton(self, "&Borrar", "Borra la tarea elegida (y su tarea de Windows).", botones, self.borrar)
		self.boton_ahora = _boton(self, "E&jecutar ahora", "Ejecuta la tarea elegida ya, en esta ventana de zCommander.", botones,
			self.ejecutar_ahora)
		_boton(self, "&Registro de ejecuciones...", "Muestra el resultado de las tareas ejecutadas.", botones, self.ver_registro)
		cerrar = _boton(self, "&Cerrar", "Cierra la ventana (también con Escape).", botones, id_boton=wx.ID_CLOSE)
		cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE) if self.IsModal() else self.Destroy())
		cuerpo.Add(botones, 0, wx.EXPAND | wx.ALL, 5)
		self.SetSizer(cuerpo)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.editar())
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
		ui.preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista)
		self.tareas: list[tareas.Tarea] = []
		self.recargar()

	def recargar(self, elegir: str = "") -> None:
		if not self:
			return
		self.estado.SetValue("Las tareas se ejecutan con el Programador de tareas de Windows, también con zCommander cerrado."
			if self.complemento.usar_windows else "Las tareas solo se ejecutan mientras zCommander está abierto.")
		self.tareas = self.complemento.leer()
		filas = [[t.nombre, t.que_hace(), t.cuando(), _fecha(t.ultima),
			tareas.TEXTO_CODIGO.get(t.resultado, "Sin datos"), "Sí" if t.activa else "No"] for t in self.tareas]
		self.lista.reemplazar_filas(filas)
		for indice, tarea in enumerate(self.tareas):
			if tarea.id == elegir:
				self.lista.enfocar_fila(indice, anunciar=False)
		hay = bool(self.tareas)
		for boton in (self.boton_editar, self.boton_borrar, self.boton_ahora):
			boton.Enable(hay)

	def actual(self) -> tareas.Tarea | None:
		fila = self.lista.fila_actual()
		return self.tareas[fila] if 0 <= fila < len(self.tareas) else None

	def _editar(self, tarea: tareas.Tarea) -> None:
		dialogo = DialogoTarea(self.zc, self, tarea)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			cambiada = dialogo.tarea()
		finally:
			dialogo.Destroy()
		self.complemento.guardar_tarea(cambiada)
		self.recargar(cambiada.id)
		self.zc.anunciar(f"Tarea guardada: {cambiada.nombre}", api.RESULTADO)

	def nueva(self) -> None:
		self._editar(tareas.Tarea("", objetivo="", tipo=tareas.SINCRONIZACION))

	def editar(self) -> None:
		tarea = self.actual()
		if tarea is not None:
			self._editar(tarea)

	def borrar(self) -> None:
		tarea = self.actual()
		if tarea is None:
			return
		if not self.zc.ui.confirmar(f"¿Borrar la tarea programada «{tarea.nombre}»?", "Borrar la tarea", self, peligroso=True):
			return
		self.complemento.borrar_tarea(tarea)
		self.recargar()
		self.zc.anunciar(f"Tarea borrada: {tarea.nombre}", api.RESULTADO)

	def ejecutar_ahora(self) -> None:
		tarea = self.actual()
		if tarea is not None:
			self.zc.anunciar(f"Ejecutando {tarea.nombre}", api.RESULTADO)
			self.complemento.ejecutar_tarea(tarea.id, lambda _codigo: self.recargar(tarea.id))

	def ver_registro(self) -> None:
		dialogo = DialogoRegistro(self.complemento, self)
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.borrar()
			return
		evento.Skip()


class DialogoRegistro(wx.Dialog):
	def __init__(self, complemento, padre: wx.Window | None) -> None:
		super().__init__(padre, title="Registro de ejecuciones", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, size=(780, 500))
		self.complemento = complemento
		self.zc: api.Anfitrion = complemento.zc
		ui = self.zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label="&Ejecuciones:")
		self.lista = ui.ListaAccesible(self, "Ejecuciones", [("Fecha", 130), ("Tarea", 160), ("Resultado", 130), ("Resumen", 320)])
		self.lista.SetHelpText("Ejecuciones de las tareas, la más reciente primero. Abajo, sus detalles.")
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		_, self.detalles = ui.crear_campo(self, "&Detalles:", wx.TextCtrl, sizer=cuerpo,
			style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 120),
			ayuda="Resumen de la ejecución elegida y las decisiones que se tomaron sin preguntar.")
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_vaciar = _boton(self, "&Vaciar el registro", "Borra todas las ejecuciones apuntadas.", botones, self.vaciar)
		cerrar = _boton(self, "&Cerrar", "Cierra la ventana (también con Escape).", botones, id_boton=wx.ID_CLOSE)
		cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE) if self.IsModal() else self.Destroy())
		cuerpo.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizer(cuerpo)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda _e: self._mostrar_detalles())
		ui.preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista)
		self.ejecuciones: list[tareas.Ejecucion] = []
		self.recargar()

	def recargar(self) -> None:
		self.ejecuciones = list(reversed(self.complemento.registro_ejecuciones.leer()))
		self.lista.reemplazar_filas([[_fecha(e.inicio), e.nombre, e.texto(), e.resumen] for e in self.ejecuciones],
			conservar_foco=False)
		self.boton_vaciar.Enable(bool(self.ejecuciones))
		self._mostrar_detalles()

	def _mostrar_detalles(self) -> None:
		fila = self.lista.fila_actual()
		if not 0 <= fila < len(self.ejecuciones):
			self.detalles.SetValue("No hay ninguna ejecución apuntada." if not self.ejecuciones else "")
			return
		ejecucion = self.ejecuciones[fila]
		lineas = [f"{ejecucion.nombre}: {ejecucion.texto()}", f"Empezó: {_fecha(ejecucion.inicio)}",
			f"Terminó: {_fecha(ejecucion.fin)}" if ejecucion.fin else "Sin terminar", ejecucion.resumen]
		if ejecucion.decisiones:
			lineas.append("Decisiones tomadas sin preguntar:")
			lineas.extend(ejecucion.decisiones)
		self.detalles.SetValue("\n".join(linea for linea in lineas if linea))

	def vaciar(self) -> None:
		if self.zc.ui.confirmar("¿Vaciar el registro de ejecuciones?", "Vaciar el registro", self, peligroso=True):
			self.complemento.registro_ejecuciones.vaciar()
			self.recargar()
