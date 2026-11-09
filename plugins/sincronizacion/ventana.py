# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de las tareas de sincronización (diseño 2.0, 11.12). Con wx: se importa al abrirlos.

- «Tareas de sincronización»: lista con Nombre, Modo, Origen, Destino, Última
  ejecución y Resultado. Intro edita, Supr borra (con confirmación y el foco
  en «No»). Simular y Ejecutar lanzan la operación sin cerrar el diálogo.
- «Tarea de sincronización»: el editor de una tarea, con la etiqueta creada
  antes de cada campo y Aceptar y Cancelar en español.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import wx

from app.plugins import api

from . import motor


def _boton(padre: wx.Window, etiqueta: str, ayuda: str, sizer: wx.Sizer, al_pulsar: Callable[[], None]) -> wx.Button:
	boton = wx.Button(padre, label=etiqueta)
	boton.SetHelpText(ayuda)
	boton.Bind(wx.EVT_BUTTON, lambda _e: al_pulsar())
	sizer.Add(boton, 0, wx.ALL, 4)
	return boton


class DialogoPerfil(wx.Dialog):
	"""Crea o cambia una tarea. ``perfil()`` devuelve la tarea con lo escrito."""

	def __init__(self, zc: api.Anfitrion, padre: wx.Window | None, perfil: motor.Perfil, otros: list[str]) -> None:
		super().__init__(padre, title="Tarea de sincronización", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self._base = perfil
		self._otros = {o.casefold() for o in otros}
		ui = zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		_, self.nombre = ui.crear_campo(self, "&Nombre:", wx.TextCtrl, sizer=cuerpo, value=perfil.nombre,
			ayuda="Nombre de la tarea; con él la usa el programador de tareas.")
		_, self.origen = ui.crear_campo(self, "&Origen:", wx.TextCtrl, sizer=cuerpo, value=perfil.origen,
			ayuda="Carpeta o dirección de origen: disco, red, ftp://, sftp:// o una nube.")
		_, self.destino = ui.crear_campo(self, "&Destino:", wx.TextCtrl, sizer=cuerpo, value=perfil.destino,
			ayuda="Carpeta o dirección de destino.")
		self._modos = list(motor.MODOS)
		_, self.modo = ui.crear_campo(self, "&Modo:", wx.Choice, sizer=cuerpo, choices=[motor.MODOS[m] for m in self._modos],
			ayuda="Espejo deja el destino igual que el origen; Actualizar solo copia lo nuevo y lo más reciente; "
				"Dos sentidos lleva los cambios, borrados y renombrados de cada lado al otro.")
		self.modo.SetSelection(self._modos.index(perfil.modo))
		_, self.incluir = ui.crear_campo(self, "&Incluir solo estos archivos (patrones separados por punto y coma):", wx.TextCtrl,
			sizer=cuerpo, value=perfil.incluir, ayuda="Por ejemplo *.docx;*.pdf. Vacío: todos los archivos.")
		_, self.excluir = ui.crear_campo(self, "E&xcluir (patrones separados por punto y coma):", wx.TextCtrl, sizer=cuerpo,
			value=perfil.excluir, ayuda="Archivos o carpetas que no se sincronizan, por ejemplo *.tmp;Thumbs.db;node_modules.")
		self.subcarpetas = wx.CheckBox(self, label="Incluir &subcarpetas")
		self.subcarpetas.SetValue(perfil.subcarpetas)
		self.subcarpetas.SetHelpText("Si se desmarca, solo se sincronizan los archivos de la carpeta principal.")
		cuerpo.Add(self.subcarpetas, 0, wx.ALL, 5)
		self.versiones = wx.CheckBox(self, label="Conservar &versiones de lo sustituido o borrado")
		self.versiones.SetValue(perfil.versiones)
		self.versiones.SetHelpText("Lo que se sustituye o se borra va antes a la carpeta _versiones de ese lado, por días.")
		cuerpo.Add(self.versiones, 0, wx.ALL, 5)
		cuerpo.Add(ui.crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(cuerpo)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		ui.preparar_dialogo(self, foco_inicial=self.nombre)

	def error(self) -> str:
		"""Qué falta o está mal (vacío si se puede guardar)."""
		nombre = self.nombre.GetValue().strip()
		if not nombre:
			return "Escriba un nombre para la tarea."
		if nombre.casefold() in self._otros:
			return f"Ya hay una tarea llamada «{nombre}»."
		origen, destino = self.origen.GetValue().strip(), self.destino.GetValue().strip()
		if not origen or not destino:
			return "Escriba el origen y el destino."
		if origen.rstrip("\\/").casefold() == destino.rstrip("\\/").casefold():
			return "El origen y el destino no pueden ser la misma carpeta."
		return ""

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		problema = self.error()
		if problema:
			self.zc.ui.mostrar_error(problema, "Tarea de sincronización", self)
			return
		evento.Skip()

	def perfil(self) -> motor.Perfil:
		return motor.Perfil(nombre=self.nombre.GetValue().strip(), origen=self.origen.GetValue().strip(),
			destino=self.destino.GetValue().strip(), modo=self._modos[max(0, self.modo.GetSelection())],
			incluir=self.incluir.GetValue().strip(), excluir=self.excluir.GetValue().strip(),
			subcarpetas=self.subcarpetas.GetValue(), versiones=self.versiones.GetValue(),
			ultima=self._base.ultima, resultado=self._base.resultado)


class DialogoTareas(wx.Dialog):
	"""Lista de tareas con Nueva, Editar, Borrar, Simular, Ejecutar, Ejecutar todas e informe."""

	def __init__(self, complemento, padre: wx.Window | None, origen: str = "", destino: str = "") -> None:
		super().__init__(padre, title="Tareas de sincronización", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			size=(820, 480))
		self.complemento = complemento
		self.zc: api.Anfitrion = complemento.zc
		self._origen, self._destino = origen, destino
		ui = self.zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label="Tareas &guardadas:")
		self.lista = ui.ListaAccesible(self, "Tareas guardadas", [("Nombre", 150), ("Modo", 110), ("Origen", 170),
			("Destino", 170), ("Última ejecución", 130), ("Resultado", 220)])
		self.lista.SetHelpText("Tareas de sincronización. Intro edita la tarea; Supr la borra.")
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		botones = wx.WrapSizer(wx.HORIZONTAL)
		self.boton_nueva = _boton(self, "&Nueva...", "Crea una tarea; propone el panel activo como origen y el otro como destino.",
			botones, self.nueva)
		self.boton_editar = _boton(self, "&Editar...", "Cambia la tarea elegida.", botones, self.editar)
		self.boton_borrar = _boton(self, "&Borrar", "Borra la tarea elegida (no toca ningún archivo).", botones, self.borrar)
		self.boton_simular = _boton(self, "&Simular", "Muestra lo que haría la tarea sin cambiar nada.", botones, self.simular)
		self.boton_ejecutar = _boton(self, "E&jecutar", "Ejecuta la tarea elegida como una operación (F12 la sigue).",
			botones, self.ejecutar)
		self.boton_todas = _boton(self, "Ejecutar &todas", "Pone en cola todas las tareas, una tras otra.", botones,
			self.ejecutar_todas)
		self.boton_informe = _boton(self, "&Ver el último informe", "Muestra el informe de la última ejecución de la tarea.",
			botones, self.ver_informe)
		cerrar = wx.Button(self, wx.ID_CLOSE, "&Cerrar")
		cerrar.SetHelpText("Cierra la ventana (también con Escape).")
		cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE) if self.IsModal() else self.Close())
		botones.Add(cerrar, 0, wx.ALL, 4)
		cuerpo.Add(botones, 0, wx.EXPAND | wx.ALL, 5)
		self.SetSizer(cuerpo)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.editar())
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
		ui.preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista)
		self.perfiles: list[motor.Perfil] = []
		self.recargar()

	# ── Datos ────────────────────────────────────────────────────────────────

	def recargar(self, elegir: str = "") -> None:
		self.perfiles = motor.leer_perfiles(self.zc.datos)
		filas = []
		for perfil in self.perfiles:
			ultima = time.strftime("%d/%m/%Y %H:%M", time.localtime(perfil.ultima)) if perfil.ultima else "Nunca"
			filas.append([perfil.nombre, motor.MODOS[perfil.modo].split(":")[0], perfil.origen, perfil.destino, ultima,
				perfil.resultado or "Sin datos"])
		self.lista.reemplazar_filas(filas)
		if elegir:
			for indice, perfil in enumerate(self.perfiles):
				if perfil.nombre == elegir:
					self.lista.enfocar_fila(indice, anunciar=False)
		hay = bool(self.perfiles)
		for boton in (self.boton_editar, self.boton_borrar, self.boton_simular, self.boton_ejecutar, self.boton_todas,
				self.boton_informe):
			boton.Enable(hay)

	def actual(self) -> motor.Perfil | None:
		fila = self.lista.fila_actual()
		return self.perfiles[fila] if 0 <= fila < len(self.perfiles) else None

	# ── Acciones ─────────────────────────────────────────────────────────────

	def nueva(self) -> None:
		perfil = motor.Perfil("", self._origen, self._destino)
		self._editar(perfil, nueva=True)

	def editar(self) -> None:
		perfil = self.actual()
		if perfil is not None:
			self._editar(perfil, nueva=False)

	def _editar(self, perfil: motor.Perfil, nueva: bool) -> None:
		otros = [p.nombre for p in self.perfiles if nueva or p.nombre != perfil.nombre]
		dialogo = DialogoPerfil(self.zc, self, perfil, otros)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			cambiado = dialogo.perfil()
		finally:
			dialogo.Destroy()
		perfiles = [p for p in self.perfiles if nueva or p.nombre != perfil.nombre]
		perfiles.append(cambiado)
		motor.guardar_perfiles(self.zc.datos, perfiles)
		self.recargar(cambiado.nombre)
		self.zc.anunciar(f"Tarea guardada: {cambiado.nombre}", api.RESULTADO)

	def borrar(self) -> None:
		perfil = self.actual()
		if perfil is None:
			return
		if not self.zc.ui.confirmar(f"¿Borrar la tarea «{perfil.nombre}»? No se borra ningún archivo.", "Borrar la tarea",
				self, peligroso=True):
			return
		motor.guardar_perfiles(self.zc.datos, [p for p in self.perfiles if p.nombre != perfil.nombre])
		self.recargar()
		self.zc.anunciar(f"Tarea borrada: {perfil.nombre}", api.RESULTADO)

	def simular(self) -> None:
		perfil = self.actual()
		if perfil is not None:
			self.complemento.lanzar_simulacion(perfil.nombre)

	def ejecutar(self) -> None:
		perfil = self.actual()
		if perfil is not None:
			self.complemento.lanzar_tarea(perfil.nombre, al_terminar=lambda _op: self._recargar_si_abierto(perfil.nombre))

	def ejecutar_todas(self) -> None:
		self.complemento.lanzar_todas(al_terminar=lambda _op: self._recargar_si_abierto(""))

	def ver_informe(self) -> None:
		perfil = self.actual()
		if perfil is None:
			return
		texto = motor.leer_informe(self.zc.datos, perfil.nombre) or "Esta tarea aún no se ha ejecutado."
		self.zc.ui.mostrar_texto(f"Último informe de {perfil.nombre}", texto)

	def _recargar_si_abierto(self, nombre: str) -> None:
		if self:
			self.recargar(nombre)

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.borrar()
			return
		evento.Skip()
