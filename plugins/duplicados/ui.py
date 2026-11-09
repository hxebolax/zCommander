# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventanas del buscador de duplicados (diseño 2.0, 11.7 y 15.1).

Se construyen con los controles accesibles de ``zc.ui`` (``ListaAccesible``,
``crear_campo``, ``preparar_dialogo``): etiqueta creada antes de cada control,
letras de acceso sin repetir, Escape que cierra, Ctrl+H con ayuda en cada
control y F1 con la ayuda del complemento. Se abren con ``zc.ui.mostrar_modal``.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import wx

from app.plugins import api

from . import motor

_ = api.traduccion("zc.duplicados")[0]


def _boton(padre: wx.Window, etiqueta: str, ayuda: str, identificador: int = wx.ID_ANY) -> wx.Button:
	boton = wx.Button(padre, identificador, etiqueta)
	boton.SetHelpText(ayuda)
	return boton


def _f1(dialogo: wx.Dialog, zc: api.Anfitrion) -> None:
	"""F1 abre la ayuda del complemento (15.1); lo demás sigue su camino."""

	def al_pulsar(evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F1 and not evento.HasAnyModifiers():
			try:
				zc.abrir_ayuda()
			except api.NoAdmitido:
				zc.registro.debug("Sin ventana para abrir la ayuda", exc_info=True)
			return
		evento.Skip()

	dialogo.Bind(wx.EVT_CHAR_HOOK, al_pulsar)


class DialogoBuscar(wx.Dialog):
	"""Dónde y cómo buscar (Mayús+F7)."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, carpetas: list[str]) -> None:
		super().__init__(padre, title=_("Buscar duplicados"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_carpetas = ui.crear_campo(self, _("&Dónde buscar (carpetas separadas por punto y coma):"), wx.TextCtrl,
			value="; ".join(carpetas), sizer=sizer,
			ayuda=_("Una o varias carpetas separadas por punto y coma. Se busca también en sus subcarpetas."))
		_e, self.criterio = ui.crear_campo(self, _("C&riterio:"), wx.Choice, choices=motor.textos_criterios(), sizer=sizer,
			ayuda=_("Qué hace iguales a dos archivos. Por contenido es lo más seguro: compara el tamaño y una suma BLAKE2b."))
		self.criterio.SetSelection(0)
		_e, self.tamano = ui.crear_campo(self, _("&Tamaño mínimo en KB:"), wx.SpinCtrl, min=0, max=10_000_000,
			initial=int(zc.config.obtener("tamano_minimo_kb")), sizer=sizer,
			ayuda=_("Los archivos más pequeños no se comparan. 0 compara todos."))
		_e, self.excluir = ui.crear_campo(self, _("E&xcluir (patrones separados por punto y coma):"), wx.TextCtrl,
			value=str(zc.config.obtener("excluir")), sizer=sizer,
			ayuda=_("Archivos y carpetas que no se miran, como *.tmp;Thumbs.db."))
		self.ocultos = wx.CheckBox(self, label=_("Incluir archivos &ocultos y de sistema"))
		self.ocultos.SetValue(bool(zc.config.obtener("incluir_ocultos")))
		self.ocultos.SetHelpText(_("Marcado, también se comparan los archivos ocultos y los de sistema."))
		sizer.Add(self.ocultos, 0, wx.ALL, 5)
		botones = wx.StdDialogButtonSizer()
		aceptar = _boton(self, _("&Buscar"), _("Empieza la búsqueda como una operación con progreso."), wx.ID_OK)
		aceptar.SetDefault()
		botones.AddButton(aceptar)
		botones.AddButton(_boton(self, _("&Cancelar"), _("Cierra sin buscar."), wx.ID_CANCEL))
		botones.Realize()
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.FromDIP(wx.Size(520, -1)))
		ui.preparar_dialogo(self, foco_inicial=self.campo_carpetas)
		_f1(self, zc)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)

	def opciones(self) -> motor.Opciones:
		carpetas = [c.strip().strip('"') for c in self.campo_carpetas.GetValue().split(";") if c.strip()]
		return motor.Opciones(carpetas=carpetas, criterio=motor.CRITERIOS[max(0, self.criterio.GetSelection())],
			tamano_minimo=self.tamano.GetValue() * 1024, excluir=self.excluir.GetValue(), incluir_ocultos=self.ocultos.GetValue())

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		faltan = [c for c in self.opciones().carpetas if not os.path.isdir(c)]
		if not self.opciones().carpetas or faltan:
			texto = _("No existe la carpeta {c}").format(c=faltan[0]) if faltan else _("Escriba al menos una carpeta")
			self.zc.ui.mostrar_error(texto, _("Buscar duplicados"), self)
			self.campo_carpetas.SetFocus()
			return
		evento.Skip()


class DialogoResultados(wx.Dialog):
	"""Lista de grupos con casillas para elegir qué copias quitar."""

	def __init__(self, padre: wx.Window | None, zc: api.Anfitrion, resultado: motor.Resultado,
			acciones: dict[str, Callable[[DialogoResultados], None]] | None = None) -> None:
		super().__init__(padre, title=_("Duplicados encontrados"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self.resultado = resultado
		self.acciones = acciones or {}
		self.filas: list[tuple[int, motor.Archivo]] = []
		self._grupo_anunciado = -1
		ui = zc.ui
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_resumen = ui.crear_campo(self, _("&Resumen:"), wx.TextCtrl, value=motor.resumen(resultado),
			style=wx.TE_READONLY, sizer=sizer, ayuda=_("Cuántos grupos hay y cuánto espacio se recupera."))
		etiqueta = wx.StaticText(self, label=_("&Duplicados (marque las copias que quiere quitar):"))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.lista = ui.ListaAccesible(self, _("Duplicados"), [(_("Grupo"), 90), (_("Nombre"), 220), (_("Carpeta"), 300),
			(_("Tamaño"), 90), (_("Fecha"), 150)], con_casillas=True)
		self.lista.SetHelpText(_("Cada fila es una copia. Espacio marca o desmarca la copia para quitarla; "
			"al pasar a otro grupo se dice cuántas copias tiene y cuánto se recupera."))
		sizer.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		fila1 = wx.BoxSizer(wx.HORIZONTAL)
		fila2 = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_auto = _boton(self, _("Marcado &automático..."), _("Marca todas las copias menos una en cada grupo con la regla que elija."))
		self.boton_quitar = _boton(self, _("&Quitar todas las marcas"), _("Desmarca todas las copias."))
		self.boton_ir = _boton(self, _("&Ir al archivo"), _("Lleva el panel activo a la carpeta del archivo de la fila."))
		self.boton_papelera = _boton(self, _("Enviar los marcados a la &papelera"), _("Envía a la papelera las copias marcadas."))
		self.boton_enlaces = _boton(self, _("Sustituir por en&laces duros"),
			_("Cambia cada copia marcada por un enlace duro al archivo que se conserva (misma unidad NTFS): ocupa el espacio una sola vez."))
		self.boton_exportar = _boton(self, _("E&xportar informe..."), _("Guarda la lista en un archivo de texto o CSV."))
		self.boton_panel = _boton(self, _("Enviar al pa&nel"), _("Muestra las copias marcadas, o todas si no hay marcas, como lista en el panel."))
		for boton in (self.boton_auto, self.boton_quitar, self.boton_ir, self.boton_exportar):
			fila1.Add(boton, 0, wx.ALL, 3)
		for boton in (self.boton_papelera, self.boton_enlaces, self.boton_panel):
			fila2.Add(boton, 0, wx.ALL, 3)
		cerrar = _boton(self, _("C&errar"), _("Cierra la lista de duplicados."), wx.ID_CLOSE)
		fila2.Add(cerrar, 0, wx.ALL, 3)
		sizer.Add(fila1, 0, wx.LEFT | wx.RIGHT, 2)
		sizer.Add(fila2, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)
		self.SetSizer(sizer)
		self.SetSize(self.FromDIP(wx.Size(900, 560)))
		ui.preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista)
		_f1(self, zc)
		if zc.config.obtener("accion") == "enlace_duro":
			self.boton_enlaces.SetDefault()
		else:
			self.boton_papelera.SetDefault()
		self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE), id=wx.ID_CLOSE)
		self.Bind(wx.EVT_BUTTON, self._al_auto, self.boton_auto)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.marcar(set(), anunciar=True), self.boton_quitar)
		for clave, boton in (("ir", self.boton_ir), ("papelera", self.boton_papelera), ("enlaces", self.boton_enlaces),
				("exportar", self.boton_exportar), ("panel", self.boton_panel)):
			self.Bind(wx.EVT_BUTTON, lambda _e, c=clave: self._accion(c), boton)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._al_enfocar)
		self.recargar()

	# Datos -------------------------------------------------------------------

	def recargar(self, marcadas: set[str] | None = None) -> None:
		"""Rellena la lista con los grupos (quitando los archivos que ya no existen)."""
		marcadas = self.marcadas() if marcadas is None else marcadas
		grupos = []
		for grupo in self.resultado.grupos:
			vivos = [a for a in grupo.archivos if os.path.exists(a.ruta)]
			if len(vivos) > 1:
				grupos.append(motor.Grupo(vivos, grupo.clave))
		self.resultado.grupos = grupos
		total = len(grupos)
		self.filas = [(i, a) for i, g in enumerate(grupos) for a in g.archivos]
		self.lista.reemplazar_filas([[
			_("{i} de {t}").format(i=i + 1, t=total), a.nombre, a.carpeta, api.formato.tamano_legible(a.tamano),
			api.formato.fecha(a.modificado, "larga")] for i, a in self.filas])
		self.marcar(marcadas)
		self.campo_resumen.SetValue(motor.resumen(self.resultado))

	def marcadas(self) -> set[str]:
		return {self.filas[f][1].ruta for f in self.lista.filas_marcadas() if f < len(self.filas)}

	def marcar(self, rutas: set[str], anunciar: bool = False) -> None:
		for fila, (_g, archivo) in enumerate(self.filas):
			if bool(self.lista.IsItemChecked(fila)) != (archivo.ruta in rutas):
				self.lista.CheckItem(fila, archivo.ruta in rutas)
		if anunciar:
			texto = motor.resumen_marcado(self.resultado.grupos, rutas) if rutas else _("Sin marcas")
			self.zc.anunciar(texto, api.RESULTADO)

	def archivo_actual(self) -> motor.Archivo | None:
		fila = self.lista.fila_actual()
		return self.filas[fila][1] if 0 <= fila < len(self.filas) else None

	# Eventos -----------------------------------------------------------------

	def _al_enfocar(self, evento: wx.ListEvent) -> None:
		fila = evento.GetIndex()
		if 0 <= fila < len(self.filas):
			grupo = self.filas[fila][0]
			if grupo != self._grupo_anunciado:
				self._grupo_anunciado = grupo
				self.zc.anunciar(motor.describir_grupo(grupo, len(self.resultado.grupos), self.resultado.grupos[grupo]), api.DETALLE)
		evento.Skip()

	def _al_auto(self, _evento: wx.CommandEvent) -> None:
		eleccion = self.zc.ui.elegir_opcion(_("¿Qué copia conserva en cada grupo? Las demás quedan marcadas."),
			_("Marcado automático"), motor.textos_marcados(), self)
		if eleccion is None:
			return
		modo = motor.MARCADOS[eleccion]
		self.marcar(motor.marcar_automatico(self.resultado.grupos, modo, str(self.zc.config.obtener("carpeta_preferida"))), anunciar=True)

	def _accion(self, clave: str) -> None:
		funcion = self.acciones.get(clave)
		if funcion is not None:
			funcion(self)
