# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana del NAS (diseño 2.0, 13.4): «NAS Synology: <nombre>», no modal.

- A la izquierda, «Áreas» (lista nativa con las áreas que tiene ESTE NAS); al
  elegir una con Intro, o al quedarse 400 ms en ella, a la derecha aparece su
  vista: «Sección» (si el área tiene varias), «Elementos» (``ListaAccesible``
  con lectura por columnas), «Detalle» (texto de solo lectura) y los botones de
  las acciones del área.
- F6 alterna entre las áreas y los elementos; Control+R vuelve a leer;
  Control+Mayúsculas+T dice el uso del NAS; Escape cierra; F1 abre la ayuda.
- El modo («Solo lectura» o «Cambios permitidos») está en el texto de estado y
  en el título: con cambios permitidos el título empieza por «CAMBIOS
  PERMITIDOS:» para que el lector lo diga al volver a la ventana.
- Las vistas se refrescan cada ``refresco_estado_s`` solo si la ventana se ve,
  sin mover el foco; un aviso de salud nuevo se anuncia una sola vez (suena
  ``zc.synology:aviso_salud``) si ``anunciar_avisos`` está activa.
- Las acciones que cambian algo están desactivadas en solo lectura, con la
  ayuda de Control+H «Desactive el modo solo lectura del NAS para usar esta acción».
"""

from __future__ import annotations

import logging
from typing import Any

import wx

from app.plugins import api

from .. import areas, errores
from . import modulo_ui, poner_letra
from .dialogos import ConfirmadorInterfaz, copiar_al_portapapeles

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.ventana")

ID_COMPLEMENTO = "zc.synology"
TECLAS_PROPIAS = ("F6", "Ctrl+R", "Ctrl+Mayús+T")
#: Letras de los controles fijos de la ventana: los botones de acciones no las usan.
LETRAS_FIJAS = frozenset({"c", "r", "s", "e", "d", "v", "i", "m", "a"})
AYUDA_SOLO_LECTURA = "Desactive el modo solo lectura del NAS para usar esta acción."


class VentanaNAS:
	"""Controlador de la ventana de un NAS conectado."""

	def __init__(self, complemento: Any, conexion: Any, area_inicial: str = "estado", seccion_inicial: str = "") -> None:
		self.ui = modulo_ui()
		self.complemento = complemento
		self.conexion = conexion
		self._areas = areas.disponibles(conexion.cliente)
		self._vista: areas.Vista | None = None
		self._area: areas.Area | None = None
		self._seccion_pedida = seccion_inicial
		self._filas: list[areas.Fila] = []
		self._avisos_conocidos: set[str] = set()
		self._cargando = False
		self._retardo: wx.CallLater | None = None
		self._mover_foco = False
		self.cerrada = False
		self.marco = self.ui.VentanaComplemento(None, conexion.titulo(), ID_COMPLEMENTO)
		self._construir()
		self._temporizador = wx.Timer(self.marco)
		self.marco.Bind(wx.EVT_TIMER, self._al_temporizador, self._temporizador)
		self.marco.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.marco.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self.actualizar_modo()
		self.ir_a_area(area_inicial, seccion_inicial, mover_foco=False)

	# ── Construcción ─────────────────────────────────────────────────────────

	def _construir(self) -> None:
		ui = self.ui
		marco = self.marco
		panel = wx.Panel(marco)
		self.panel = panel
		general = wx.BoxSizer(wx.VERTICAL)
		_etq, self.estado = ui.crear_campo(panel, _("&Conexión:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
			size=marco.FromDIP(wx.Size(860, 52)), sizer=general, ayuda=_("NAS conectado, su modelo y versión de DSM y el modo: solo lectura "
				"o cambios permitidos."))
		cuerpo = wx.BoxSizer(wx.HORIZONTAL)
		izquierda = wx.BoxSizer(wx.VERTICAL)
		_etq, self.lista_areas = ui.crear_campo(panel, _("Á&reas:"), wx.ListBox, choices=[a.titulo for a in self._areas],
			size=marco.FromDIP(wx.Size(220, 420)), sizer=izquierda, ayuda=_("Áreas del NAS. Intro abre la elegida; F6 pasa a sus elementos."))
		cuerpo.Add(izquierda, 0, wx.EXPAND)
		derecha = wx.BoxSizer(wx.VERTICAL)
		self.etiqueta_seccion, self.seccion = ui.crear_campo(panel, _("&Sección:"), wx.Choice, choices=[], sizer=derecha,
			ayuda=_("Partes del área elegida (por ejemplo, contenedores, proyectos e imágenes)."))
		etiqueta_lista = wx.StaticText(panel, label=_("&Elementos:"))
		derecha.Add(etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.lista = ui.ListaAccesible(panel, _("Elementos"), [(_("Dato"), marco.FromDIP(200))])
		self.lista.SetMinSize(marco.FromDIP(wx.Size(600, 260)))
		derecha.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		_etq, self.detalle = ui.crear_campo(panel, _("&Detalle:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
			size=marco.FromDIP(wx.Size(600, 110)), sizer=derecha, ayuda=_("Todo lo que se sabe del elemento elegido."))
		self.panel_acciones = wx.Panel(panel)
		self.panel_acciones.SetSizer(wx.WrapSizer(wx.HORIZONTAL))
		derecha.Add(self.panel_acciones, 0, wx.EXPAND | wx.ALL, 2)
		cuerpo.Add(derecha, 1, wx.EXPAND)
		general.Add(cuerpo, 1, wx.EXPAND)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.volver_a_leer = wx.Button(panel, label=_("&Volver a leer"))
		self.volver_a_leer.SetHelpText(_("Lee otra vez el área desde el NAS (Control+R)."))
		self.boton_acciones = wx.Button(panel, label=_("Acc&iones..."))
		self.boton_acciones.SetHelpText(_("Menú con todas las acciones de la sección, también las desactivadas y por qué (tecla Aplicaciones en "
			"la lista)."))
		self.cambios = wx.CheckBox(panel, label=_("Permitir ca&mbios en este NAS"))
		self.cambios.SetHelpText(_("Desmarcada (de fábrica), zCommander no puede cambiar nada en el NAS. Marcarla pide confirmación."))
		self.cerrar = wx.Button(panel, wx.ID_CLOSE, _("Cerr&ar"))
		self.cerrar.SetHelpText(_("Cierra esta ventana. La conexión con el NAS sigue abierta."))
		for control in (self.volver_a_leer, self.boton_acciones, self.cambios, self.cerrar):
			fila.Add(control, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
		general.Add(fila, 0, wx.ALL, 4)
		panel.SetSizer(general)
		marco_sizer = wx.BoxSizer(wx.VERTICAL)
		marco_sizer.Add(panel, 1, wx.EXPAND)
		marco.SetSizerAndFit(marco_sizer)
		self.lista_areas.Bind(wx.EVT_LISTBOX, self._al_mover_area)
		self.lista_areas.Bind(wx.EVT_KEY_DOWN, self._al_tecla_areas)
		self.lista_areas.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self._abrir_area_elegida(True))
		self.seccion.Bind(wx.EVT_CHOICE, lambda _e: self._mostrar_seccion(self.seccion.GetSelection(), mover_foco=False))
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda _e: self._al_cambiar_fila())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._al_cambiar_fila())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self._accion_por_defecto())
		self.lista.Bind(wx.EVT_CONTEXT_MENU, lambda _e: self._menu_acciones(self.lista))
		self.volver_a_leer.Bind(wx.EVT_BUTTON, lambda _e: self.refrescar(anunciar=True))
		self.boton_acciones.Bind(wx.EVT_BUTTON, lambda _e: self._menu_acciones(self.boton_acciones))
		self.cambios.Bind(wx.EVT_CHECKBOX, self._al_cambiar_modo)
		self.cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.marco.Close())

	# ── Estado y modo ────────────────────────────────────────────────────────

	def actualizar_modo(self) -> None:
		"""Título, texto de estado, casilla y botones según el modo (también cuando cambia desde la orden)."""
		conexion = self.conexion
		self.marco.SetTitle(conexion.titulo())
		info = conexion.info
		partes = [_("Conectado a {n} ({r}) como {u}.").format(n=info.nombre_host or conexion.servidor.nombre, r=info.resumen() or "DSM",
			u=info.cuenta or conexion.servidor.usuario)]
		if conexion.solo_lectura:
			partes.append(_("Solo lectura: las acciones que cambian algo están desactivadas."))
		else:
			partes.append(_("Cambios permitidos: cada acción pide confirmación."))
		if not info.administrador:
			partes.append(_("La cuenta no es de administración: algunas áreas dirán «Sin permiso con esta cuenta»."))
		if conexion.demostracion:
			partes.append(_("NAS de demostración: los cambios se pierden al cerrar."))
		if info.aviso:
			partes.append(info.aviso)
		self.estado.SetValue(" ".join(partes))
		self.cambios.SetValue(not conexion.solo_lectura)
		self._habilitar_acciones()

	def _al_cambiar_modo(self, _evento: wx.CommandEvent) -> None:
		permitir = self.cambios.GetValue()
		self.cambios.SetValue(not self.conexion.solo_lectura)
		self.complemento.cambiar_modo(self.conexion, permitir, padre=self.marco)

	# ── Áreas ────────────────────────────────────────────────────────────────

	def ir_a_area(self, id_area: str, seccion: str = "", mover_foco: bool = True) -> None:
		indice = next((i for i, a in enumerate(self._areas) if a.id == id_area), 0 if self._areas else -1)
		if indice < 0:
			self._pintar_mensaje(_("Este NAS no tiene ninguna de las áreas que zCommander sabe mostrar."))
			return
		self._seccion_pedida = seccion
		self.lista_areas.SetSelection(indice)
		self._cargar(self._areas[indice], mover_foco=mover_foco, nueva=True)

	def _al_mover_area(self, _evento: wx.CommandEvent) -> None:
		if self._retardo is not None:
			self._retardo.Stop()
		self._retardo = wx.CallLater(400, self._abrir_area_elegida, False)

	def _al_tecla_areas(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not evento.HasAnyModifiers():
			self._abrir_area_elegida(True)
			return
		evento.Skip()

	def _abrir_area_elegida(self, mover_foco: bool) -> None:
		if self.cerrada:
			return
		if self._retardo is not None:
			self._retardo.Stop()
			self._retardo = None
		indice = self.lista_areas.GetSelection()
		if not 0 <= indice < len(self._areas):
			return
		area = self._areas[indice]
		if self._area is area and self._vista is not None and not self._cargando:
			if mover_foco:
				self._enfocar_elementos()
			return
		self._cargar(area, mover_foco=mover_foco, nueva=True)

	def _ajustes(self) -> dict[str, Any]:
		return {"aviso_temperatura_c": self.complemento.ajuste("aviso_temperatura_c", 55)}

	def _cargar(self, area: areas.Area, mover_foco: bool = False, nueva: bool = False, anunciar: bool = False) -> None:
		if nueva:
			self._area = area
			self._vista = None
			self._pintar_mensaje(_("Leyendo {a}...").format(a=area.titulo))
		self._cargando = True
		self._mover_foco = mover_foco
		cliente = self.conexion.cliente
		ajustes = self._ajustes()
		self.complemento.zc.tareas.enviar(lambda _tarea: areas.cargar(area, cliente, ajustes),
			al_terminar=lambda vista: self._al_cargar(area, vista, nueva, anunciar),
			al_fallar=lambda error: self._al_fallar_carga(area, error), nombre=f"nas-area-{area.id}")

	def refrescar(self, anunciar: bool = False) -> None:
		if self._area is not None and not self._cargando:
			self._cargar(self._area, anunciar=anunciar)

	def _al_cargar(self, area: areas.Area, vista: areas.Vista, nueva: bool, anunciar: bool) -> None:
		self._cargando = False
		if self.cerrada or area is not self._area:
			return
		anterior = self._vista
		self._vista = vista
		titulos = [s.titulo for s in vista.secciones]
		mismo_esquema = anterior is not None and [s.titulo for s in anterior.secciones] == titulos and not nueva
		if not mismo_esquema:
			self.seccion.Set(titulos)
			varias = len(titulos) > 1
			self.etiqueta_seccion.Show(varias)
			self.seccion.Show(varias)
			indice = next((i for i, s in enumerate(vista.secciones) if s.id == self._seccion_pedida), 0)
			self._seccion_pedida = ""
			self.seccion.SetSelection(indice if titulos else wx.NOT_FOUND)
			self.panel.Layout()
			self._mostrar_seccion(indice, mover_foco=self._mover_foco)
		else:
			self._mostrar_seccion(self.seccion.GetSelection(), mover_foco=False, refresco=True)
		self._avisar(vista, primera=nueva)
		if anunciar:
			self.complemento.zc.anunciar(_("{a} leída de nuevo").format(a=area.titulo), api.RESULTADO)

	def _al_fallar_carga(self, area: areas.Area, error: BaseException) -> None:
		self._cargando = False
		if self.cerrada or area is not self._area:
			return
		mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
		log.warning("No se pudo leer el área %s de %s: %s", area.id, self.conexion.servidor.nombre, mensaje)
		self._pintar_mensaje(_("No se ha podido leer {a}: {m}").format(a=area.titulo, m=mensaje))
		self.complemento.zc.anunciar(_("No se ha podido leer {a}: {m}").format(a=area.titulo, m=mensaje), api.ESENCIAL)

	def _avisar(self, vista: areas.Vista, primera: bool) -> None:
		"""Cada aviso de salud se dice una sola vez por ventana (13.4)."""
		avisos = vista.avisos()
		nuevos = [texto for clave, texto in avisos.items() if clave not in self._avisos_conocidos]
		self._avisos_conocidos |= set(avisos)
		if not nuevos or not self.complemento.ajuste("anunciar_avisos", True):
			return
		self.complemento.zc.sonidos.sonar("aviso_salud")
		if primera and len(nuevos) > 1:
			texto = _n("Hay {n} aviso: {t}", "Hay {n} avisos: {t}", len(nuevos)).format(n=len(nuevos), t=". ".join(nuevos))
		else:
			texto = ". ".join(nuevos)
		self.complemento.zc.anunciar(texto, api.ESENCIAL)

	# ── Secciones y filas ────────────────────────────────────────────────────

	def _seccion_actual(self) -> areas.Seccion | None:
		if self._vista is None or not self._vista.secciones:
			return None
		indice = self.seccion.GetSelection()
		return self._vista.secciones[indice if 0 <= indice < len(self._vista.secciones) else 0]

	def _pintar_mensaje(self, texto: str) -> None:
		self._filas = []
		self._poner_columnas([_("Aviso")])
		self.lista.reemplazar_filas([[texto]], conservar_foco=False)
		self.detalle.SetValue(texto)
		self.seccion.Set([])
		self.etiqueta_seccion.Show(False)
		self.seccion.Show(False)
		self._poner_botones([])
		self.panel.Layout()

	def _poner_columnas(self, columnas: list[str]) -> None:
		actuales = [self.lista.GetColumn(i).GetText() for i in range(self.lista.GetColumnCount())]
		if actuales == columnas:
			return
		self.lista.limpiar()
		self.lista.DeleteAllColumns()
		for indice, titulo in enumerate(columnas):
			self.lista.InsertColumn(indice, titulo, width=self.marco.FromDIP(220 if indice == 0 else 150))
		reiniciar = getattr(self.lista, "reiniciar_columna", None)
		if callable(reiniciar):
			reiniciar()

	def _mostrar_seccion(self, indice: int, mover_foco: bool = False, refresco: bool = False) -> None:
		seccion = self._seccion_actual()
		if seccion is None:
			self._pintar_mensaje(_("Sin datos"))
			return
		self._filas = list(seccion.filas)
		self._poner_columnas(seccion.columnas)
		if self._filas:
			self.lista.reemplazar_filas([f.valores for f in self._filas], conservar_foco=refresco)
		else:
			self.lista.reemplazar_filas([[seccion.vacia or _("No hay elementos.")] + [""] * (len(seccion.columnas) - 1)], conservar_foco=False)
		if not refresco:
			self._poner_botones(seccion.acciones)
		self._al_cambiar_fila()
		if mover_foco:
			self._enfocar_elementos()

	def _enfocar_elementos(self) -> None:
		self.lista.SetFocus()
		if self.lista.numero_filas() and self.lista.fila_actual() < 0:
			self.lista.enfocar_fila(0, anunciar=False)

	def _fila(self) -> areas.Fila | None:
		indice = self.lista.fila_actual()
		return self._filas[indice] if 0 <= indice < len(self._filas) else None

	def _al_cambiar_fila(self) -> None:
		fila = self._fila()
		texto = fila.detalle if fila is not None else (self.lista.texto_celda(0, 0) if self.lista.numero_filas() else "")
		if self.detalle.GetValue() != texto:
			self.detalle.SetValue(texto)
		self._habilitar_acciones()

	# ── Acciones ─────────────────────────────────────────────────────────────

	def _poner_botones(self, acciones: list[areas.Accion]) -> None:
		enfocada = wx.Window.FindFocus()
		id_enfocada = getattr(enfocada, "id_accion", None) if enfocada is not None and enfocada.GetParent() is self.panel_acciones else None
		self.panel_acciones.DestroyChildren()
		sizer = self.panel_acciones.GetSizer()
		sizer.Clear()
		usadas = set(LETRAS_FIJAS)
		self._botones: list[tuple[wx.Button, areas.Accion]] = []
		for accion in acciones:
			boton = wx.Button(self.panel_acciones, label=poner_letra(accion.etiqueta, usadas))
			boton.id_accion = accion.id  # type: ignore[attr-defined]
			boton.Bind(wx.EVT_BUTTON, lambda _e, a=accion: self.ejecutar_accion(a))
			sizer.Add(boton, 0, wx.ALL, 3)
			self._botones.append((boton, accion))
		self.panel_acciones.Layout()
		self.panel.Layout()
		self._habilitar_acciones()
		if id_enfocada is not None:
			for boton, accion in self._botones:
				if accion.id == id_enfocada and boton.IsEnabled():
					boton.SetFocus()

	def _habilitar_acciones(self) -> None:
		fila = self._fila()
		solo_lectura = self.conexion.solo_lectura
		for boton, accion in getattr(self, "_botones", []):
			bloqueada = accion.escritura and solo_lectura
			boton.Enable(accion.aplicable(fila) and not bloqueada)
			boton.SetHelpText(f"{accion.ayuda} {_(AYUDA_SOLO_LECTURA)}" if bloqueada else accion.ayuda)

	def _menu_acciones(self, origen: wx.Window) -> None:
		seccion = self._seccion_actual()
		if seccion is None or not seccion.acciones:
			self.complemento.zc.anunciar(_("Esta sección no tiene acciones"), api.NORMAL)
			return
		menu = wx.Menu()
		usadas: set[str] = set()
		fila = self._fila()
		for accion in seccion.acciones:
			etiqueta = poner_letra(accion.etiqueta, usadas)
			if accion.escritura and self.conexion.solo_lectura:
				etiqueta += _(" (solo lectura)")
			elemento = menu.Append(wx.ID_ANY, etiqueta, accion.ayuda)
			elemento.Enable(accion.aplicable(fila) and not (accion.escritura and self.conexion.solo_lectura))
			self.marco.Bind(wx.EVT_MENU, lambda _e, a=accion: self.ejecutar_accion(a), elemento)
		origen.PopupMenu(menu)
		menu.Destroy()

	def _accion_por_defecto(self) -> None:
		seccion = self._seccion_actual()
		fila = self._fila()
		if seccion is None or fila is None:
			return
		accion = next((a for a in seccion.acciones if a.por_defecto and a.aplicable(fila)), None)
		if accion is None:
			self.detalle.SetFocus()
			return
		self.ejecutar_accion(accion)

	def ejecutar_accion(self, accion: areas.Accion) -> None:
		seccion = self._seccion_actual()
		fila = self._fila()
		zc = self.complemento.zc
		if seccion is None or not accion.aplicable(fila):
			zc.anunciar(_("Esta acción no se aplica al elemento elegido"), api.NORMAL)
			return
		try:
			valores = areas.preparar(accion, fila, seccion, self.conexion.cliente, ConfirmadorInterfaz(self.marco))
		except api.SoloLectura as error:
			zc.anunciar(error.mensaje, api.ESENCIAL)
			return
		if valores is None:
			zc.anunciar(_("Cancelado"), api.NORMAL)
			return
		cliente = self.conexion.cliente
		zc.tareas.enviar(lambda _tarea: areas.ejecutar(accion, cliente, fila, valores), al_terminar=lambda r: self._al_resultado(accion, r),
			al_fallar=lambda error: self._al_fallar_accion(accion, error), nombre=f"nas-accion-{accion.id}")

	def _al_resultado(self, accion: areas.Accion, resultado: areas.Resultado) -> None:
		zc = self.complemento.zc
		zc.anunciar(resultado.mensaje, api.RESULTADO)
		if resultado.copiar:
			copiar_al_portapapeles(resultado.copiar)
		if resultado.abrir:
			zc.abrir_ruta(resultado.abrir, "activo")
		if resultado.texto and not self.cerrada:
			self.ui.mostrar_texto(resultado.titulo or accion.etiqueta, resultado.texto, self.marco)
		if resultado.desconectar:
			self.complemento.desconectar_conexion(self.conexion)
			return
		if resultado.refrescar and not self.cerrada:
			self.refrescar()

	def _al_fallar_accion(self, accion: areas.Accion, error: BaseException) -> None:
		zc = self.complemento.zc
		if isinstance(error, api.Cancelado):
			zc.anunciar(_("Cancelado"), api.NORMAL)
			return
		mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
		if not isinstance(error, api.ErrorArchivos):
			log.error("Falló la acción %s", accion.id, exc_info=error)
		zc.anunciar(_("{a}: {m}").format(a=accion.etiqueta.rstrip("."), m=mensaje), api.ESENCIAL)
		if not self.cerrada and isinstance(error, errores.ErrorDSM):
			self.ui.mostrar_error(mensaje, accion.etiqueta.rstrip("."), self.marco)

	# ── Teclas, temporizador y cierre ────────────────────────────────────────

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla == wx.WXK_F6 and modificadores == wx.MOD_NONE:
			if wx.Window.FindFocus() is self.lista_areas:
				self._abrir_area_elegida(True)
			else:
				self.lista_areas.SetFocus()
			return
		if tecla == ord("R") and modificadores == wx.MOD_CONTROL:
			self.refrescar(anunciar=True)
			return
		if tecla == ord("T") and modificadores == (wx.MOD_CONTROL | wx.MOD_SHIFT):
			self.complemento.decir_estado(self.conexion)
			return
		evento.Skip()

	def mostrar(self) -> None:
		self.marco.Show()
		self.marco.Raise()
		self.lista_areas.SetFocus()
		segundos = int(self.complemento.ajuste("refresco_estado_s", 10))
		self._temporizador.Start(max(2, segundos) * 1000)

	def _al_temporizador(self, _evento: wx.TimerEvent) -> None:
		if self.cerrada or self._cargando or not self.marco.IsShownOnScreen() or self.marco.IsIconized():
			return
		self.refrescar()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		self.cerrada = True
		self._temporizador.Stop()
		if self._retardo is not None:
			self._retardo.Stop()
		self.complemento.ventana_cerrada(self)
		evento.Skip()
