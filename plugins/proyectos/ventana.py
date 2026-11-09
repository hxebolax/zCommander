# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de salto rápido y de proyectos (diseño 2.0, 11.15). Con wx: se importa al abrirlos.

Salto rápido: escribir en «Ir a» filtra al momento (todo está en memoria); la
lista no se anuncia en cada tecla: el lector lee la primera propuesta al bajar
con la flecha, que lleva del campo a la lista. Intro en el campo o en la lista
abre la carpeta elegida (la primera si no se ha movido a la lista).
"""

from __future__ import annotations

import time

import wx

from app.plugins import api

from . import datos

ORIGENES = {"frecuente": "Frecuente", "windows": "Reciente de Windows"}


def _boton(padre: wx.Window, etiqueta: str, ayuda: str, sizer: wx.Sizer, al_pulsar=None, id_boton: int = wx.ID_ANY) -> wx.Button:
	boton = wx.Button(padre, id_boton, etiqueta)
	boton.SetHelpText(ayuda)
	if al_pulsar is not None:
		boton.Bind(wx.EVT_BUTTON, lambda _e: al_pulsar())
	sizer.Add(boton, 0, wx.ALL, 4)
	return boton


class DialogoSalto(wx.Dialog):
	"""Campo «Ir a» con la lista de carpetas propuestas. ``elegida()`` da la ruta al aceptar."""

	def __init__(self, complemento, padre: wx.Window | None, recientes_windows: bool = True) -> None:
		super().__init__(padre, title="Salto rápido", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, size=(700, 460))
		self.complemento = complemento
		self.zc: api.Anfitrion = complemento.zc
		self.propuestas: list[datos.Propuesta] = []
		self.windows: list[str] = []
		ui = self.zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		_, self.campo = ui.crear_campo(self, "&Ir a:", wx.TextCtrl, sizer=cuerpo,
			ayuda="Escriba parte del nombre de la carpeta (por ejemplo «fact»). Flecha abajo pasa a la lista; Intro abre "
				"la primera propuesta.")
		etiqueta = wx.StaticText(self, label="&Lista de carpetas:")
		self.lista = ui.ListaAccesible(self, "Lista de carpetas", [("Carpeta", 430), ("Origen", 140), ("Visitas", 70)])
		self.lista.SetHelpText("Carpetas propuestas, de la más usada y reciente a la menos. Intro lleva el panel a la carpeta.")
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_abrir = _boton(self, "&Abrir en el panel", "Lleva el panel activo a la carpeta elegida.", botones,
			id_boton=wx.ID_OK)
		self.boton_abrir.SetDefault()
		self.boton_olvidar = _boton(self, "&Olvidar esta carpeta", "Quita la carpeta elegida de las frecuentes.", botones,
			self.olvidar)
		_boton(self, "&Cancelar", "Cierra sin cambiar de carpeta (también con Escape).", botones, id_boton=wx.ID_CANCEL)
		cuerpo.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizer(cuerpo)
		self.campo.Bind(wx.EVT_TEXT, lambda _e: self.filtrar())
		self.campo.Bind(wx.EVT_KEY_DOWN, self._al_tecla_campo)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self._aceptar())
		self.lista.Bind(wx.EVT_SET_FOCUS, self._al_entrar_en_lista)
		self._uso_la_lista = False
		ui.preparar_dialogo(self, foco_inicial=self.campo)
		self.filtrar()
		if recientes_windows:
			self.zc.tareas.enviar(lambda tarea: complemento.recientes_de_windows(tarea), al_terminar=self.anadir_windows,
				nombre="proyectos_recientes_windows")

	def anadir_windows(self, carpetas: list[str]) -> None:
		if self:
			self.windows = list(carpetas)
			self.filtrar()

	def filtrar(self) -> None:
		texto = self.campo.GetValue()
		frecuentes = self.complemento.proponer(texto)
		ya = {p.ruta.casefold() for p in frecuentes}
		trozos = [t.casefold() for t in texto.split() if t]
		excluidas = self.complemento.excluidas()
		extra = [datos.Propuesta(r, 0.0, 0, "windows") for r in self.windows
			if r.casefold() not in ya and datos.coincide(r, trozos) and not datos.excluida(r, excluidas)]
		self.propuestas = frecuentes + extra
		self.lista.reemplazar_filas([[p.ruta, ORIGENES[p.origen], str(p.visitas) if p.visitas else ""] for p in self.propuestas],
			conservar_foco=False)
		hay = bool(self.propuestas)
		self.boton_abrir.Enable(hay)
		self.boton_olvidar.Enable(hay)
		self._uso_la_lista = False

	def _al_entrar_en_lista(self, evento: wx.FocusEvent) -> None:
		self._uso_la_lista = True
		evento.Skip()

	def elegida(self) -> str | None:
		"""La carpeta enfocada en la lista si la persona pasó por ella tras escribir; si no, la primera."""
		if not self.propuestas:
			return None
		fila = self.lista.fila_actual() if self._uso_la_lista else 0
		return self.propuestas[fila if 0 <= fila < len(self.propuestas) else 0].ruta

	def olvidar(self) -> None:
		ruta = self.elegida()
		if ruta and self.complemento.olvidar(ruta):
			self.zc.anunciar(f"Olvidada: {ruta}", api.RESULTADO)
			self.filtrar()

	def _aceptar(self) -> None:
		if self.propuestas and self.IsModal():
			self.EndModal(wx.ID_OK)

	def _al_tecla_campo(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DOWN and not evento.HasAnyModifiers() and self.propuestas:
			self.lista.SetFocus()
			self.lista.enfocar_fila(0)
			return
		evento.Skip()


class DialogoProyecto(wx.Dialog):
	"""Nota y carpetas propias de un proyecto."""

	def __init__(self, zc: api.Anfitrion, padre: wx.Window | None, proyecto: datos.Proyecto) -> None:
		super().__init__(padre, title=f"Proyecto {proyecto.nombre}", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		ui = zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		_, self.nota = ui.crear_campo(self, "&Nota:", wx.TextCtrl, sizer=cuerpo, value=proyecto.nota,
			style=wx.TE_MULTILINE, size=(460, 90), ayuda="Texto libre del proyecto: qué es, qué falta, contactos...")
		_, self.carpetas = ui.crear_campo(self, "Carpetas del &proyecto (una por línea):", wx.TextCtrl, sizer=cuerpo,
			value="\n".join(proyecto.carpetas), style=wx.TE_MULTILINE, size=(460, 110),
			ayuda="Carpetas a las que se puede ir desde la lista de proyectos.")
		cuerpo.Add(ui.crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(cuerpo)
		ui.preparar_dialogo(self, foco_inicial=self.nota)

	def valores(self) -> tuple[str, list[str]]:
		carpetas = [c.strip() for c in self.carpetas.GetValue().splitlines() if c.strip()]
		return self.nota.GetValue().strip(), carpetas


class DialogoProyectos(wx.Dialog):
	"""Lista de proyectos: abrir, guardar la ventana actual, editar, borrar e ir a una carpeta."""

	def __init__(self, complemento, padre: wx.Window | None, carpetas_actuales: list[str] | None = None) -> None:
		super().__init__(padre, title="Proyectos", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, size=(760, 440))
		self.complemento = complemento
		self.zc: api.Anfitrion = complemento.zc
		self.carpetas_actuales = list(carpetas_actuales or [])
		ui = self.zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label="&Proyectos:")
		self.lista = ui.ListaAccesible(self, "Proyectos", [("Nombre", 160), ("Nota", 260), ("Carpetas", 200), ("Creado", 110)])
		self.lista.SetHelpText("Proyectos guardados. Intro abre el proyecto; Supr lo borra.")
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		botones = wx.WrapSizer(wx.HORIZONTAL)
		self.boton_abrir = _boton(self, "&Abrir", "Abre el espacio de trabajo del proyecto (pestañas y vistas).", botones,
			self.abrir)
		_boton(self, "&Guardar la ventana actual como proyecto...", "Guarda las pestañas y vistas actuales como un proyecto "
			"nuevo, con su nota.", botones, self.guardar_actual)
		self.boton_editar = _boton(self, "&Editar...", "Cambia la nota y las carpetas del proyecto.", botones, self.editar)
		self.boton_borrar = _boton(self, "&Borrar", "Quita el proyecto de la lista (no borra ningún archivo).", botones,
			self.borrar)
		self.boton_carpeta = _boton(self, "Ir a una carpeta del p&royecto...", "Lleva el panel activo a una de sus carpetas.",
			botones, self.ir_a_carpeta)
		cerrar = wx.Button(self, wx.ID_CLOSE, "&Cerrar")
		cerrar.SetHelpText("Cierra la ventana (también con Escape).")
		cerrar.Bind(wx.EVT_BUTTON, lambda _e: self._cerrar())
		botones.Add(cerrar, 0, wx.ALL, 4)
		cuerpo.Add(botones, 0, wx.EXPAND | wx.ALL, 5)
		self.SetSizer(cuerpo)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.abrir())
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
		ui.preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista)
		self.proyectos: list[datos.Proyecto] = []
		self.recargar()

	def recargar(self, elegir: str = "") -> None:
		self.proyectos = datos.leer_proyectos(self.zc.datos)
		filas = [[p.nombre, p.nota.replace("\n", " ") or "Sin nota", ", ".join(p.carpetas) or "Ninguna",
			time.strftime("%d/%m/%Y", time.localtime(p.creado)) if p.creado else ""] for p in self.proyectos]
		self.lista.reemplazar_filas(filas)
		for indice, proyecto in enumerate(self.proyectos):
			if proyecto.nombre == elegir:
				self.lista.enfocar_fila(indice, anunciar=False)
		hay = bool(self.proyectos)
		for boton in (self.boton_abrir, self.boton_editar, self.boton_borrar, self.boton_carpeta):
			boton.Enable(hay)

	def actual(self) -> datos.Proyecto | None:
		fila = self.lista.fila_actual()
		return self.proyectos[fila] if 0 <= fila < len(self.proyectos) else None

	def abrir(self) -> None:
		proyecto = self.actual()
		if proyecto is not None and self.complemento.abrir_proyecto(proyecto):
			self._cerrar()

	def guardar_actual(self) -> None:
		ui = self.zc.ui
		nombre = ui.pedir_texto("&Nombre del proyecto:", "Guardar como proyecto", padre=self)
		if not nombre or not nombre.strip():
			return
		nota = ui.pedir_texto("N&ota del proyecto (opcional):", "Guardar como proyecto", padre=self) or ""
		proyecto = self.complemento.guardar_proyecto(nombre.strip(), nota.strip(), self.carpetas_actuales)
		self.recargar(proyecto.nombre)

	def editar(self) -> None:
		proyecto = self.actual()
		if proyecto is None:
			return
		dialogo = DialogoProyecto(self.zc, self, proyecto)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			proyecto.nota, proyecto.carpetas = dialogo.valores()
		finally:
			dialogo.Destroy()
		datos.guardar_proyectos(self.zc.datos, self.proyectos)
		self.recargar(proyecto.nombre)
		self.zc.anunciar(f"Proyecto guardado: {proyecto.nombre}", api.RESULTADO)

	def borrar(self) -> None:
		proyecto = self.actual()
		if proyecto is None:
			return
		if not self.zc.ui.confirmar(f"¿Quitar el proyecto «{proyecto.nombre}» de la lista? No se borra ningún archivo.",
				"Borrar el proyecto", self, peligroso=True):
			return
		datos.guardar_proyectos(self.zc.datos, [p for p in self.proyectos if p.nombre != proyecto.nombre])
		self.recargar()
		self.zc.anunciar(f"Proyecto borrado: {proyecto.nombre}", api.RESULTADO)

	def ir_a_carpeta(self) -> None:
		proyecto = self.actual()
		if proyecto is None:
			return
		if not proyecto.carpetas:
			self.zc.anunciar("Este proyecto no tiene carpetas. Añádalas con Editar.", api.RESULTADO)
			return
		indice = 0
		if len(proyecto.carpetas) > 1:
			indice = self.zc.ui.elegir_opcion("¿A qué carpeta del proyecto quiere ir?", "Carpetas del proyecto",
				proyecto.carpetas, padre=self)
			if indice is None:
				return
		self.zc.abrir_ruta(proyecto.carpetas[indice])
		self._cerrar()

	def _cerrar(self) -> None:
		if self.IsModal():
			self.EndModal(wx.ID_CLOSE)
		else:
			self.Close()

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.borrar()
			return
		evento.Skip()
