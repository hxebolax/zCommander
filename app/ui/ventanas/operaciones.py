# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana de operaciones en curso (F12), sección 8.5.

Ventana no modal con la lista de operaciones y el detalle de la elegida. Por
qué está hecha así:

- Se refresca con un ``wx.Timer`` 4 veces por segundo como mucho, y solo
  mientras se ve: leer ``instantanea()`` es barato, pero no hace falta si nadie
  mira.
- El refresco nunca mueve la selección ni el foco y no anuncia nada: solo
  cambia los textos que han cambiado. La persona lee a su ritmo; los avisos de
  fin y de decisiones los da la ventana principal y el gestor de decisiones.
  Un botón con el foco nunca se desactiva (Windows llevaría el foco a otro
  sitio sin avisar): si su acción ya no procede, al pulsarlo se dice por qué.
- El detalle va en un campo de solo lectura (se recorre línea a línea y se
  copia); si tiene el foco, se conserva la posición del cursor al refrescarlo.
- Escape o «Cerrar» la ocultan (no la destruyen): las operaciones siguen y
  F12 la vuelve a mostrar tal como estaba.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable

import wx

from app.services import formato
from app.services.operaciones.copiar import OperacionCopiar
from app.services.operaciones.modelo import Estado, Operacion
from app.ui import anuncios

log = logging.getLogger(__name__)

#: 4 veces por segundo como mucho (sección 8.5).
MILISEGUNDOS_REFRESCO = 250

COL_OPERACION, COL_ESTADO, COL_PROGRESO = range(3)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def texto_progreso(operacion: Operacion) -> str:
	"""«45 %» para la columna Progreso; vacío si aún no se sabe."""
	porcentaje = operacion.instantanea().porcentaje
	return "" if porcentaje is None else f"{porcentaje} %"


def detalle_operacion(operacion: Operacion) -> str:
	"""Texto del detalle: descripción (origen y destino), archivo actual, porcentajes, bytes, velocidad, tiempos."""
	p = operacion.instantanea()
	lineas = [operacion.descripcion(), _("Estado: {e}").format(e=operacion.estado.texto)]
	if p.actual:
		porcentaje_actual = p.porcentaje_actual
		if porcentaje_actual is not None and not operacion.estado.final:
			lineas.append(_("Archivo actual: {a} ({p} %)").format(a=p.actual, p=porcentaje_actual))
		else:
			lineas.append(_("Archivo actual: {a}").format(a=p.actual))
	if p.porcentaje is not None:
		lineas.append(_("Total: {p} %").format(p=p.porcentaje))
	if p.bytes_total > 0:
		lineas.append(_("Bytes: {h} de {t}").format(h=formato.tamano_legible(p.bytes_hechos), t=formato.tamano_legible(p.bytes_total)))
	elif p.bytes_hechos > 0:
		lineas.append(_("Bytes: {h}").format(h=formato.tamano_legible(p.bytes_hechos)))
	if p.archivos_total > 0:
		lineas.append(_("Archivos: {h} de {t}").format(h=formato.miles(p.archivos_hechos), t=formato.miles(p.archivos_total)))
	if p.velocidad > 0 and not operacion.estado.final:
		lineas.append(_("Velocidad: {v}").format(v=formato.velocidad(p.velocidad)))
	if p.restante_s is not None and p.restante_s > 0 and not operacion.estado.final:
		lineas.append(_("Tiempo restante: {t}").format(t=formato.duracion(p.restante_s)))
	if p.duracion >= 1:
		lineas.append(_("Tiempo transcurrido: {t}").format(t=formato.duracion(p.duracion)))
	lineas.append(_("Omitidos: {n}").format(n=formato.miles(p.omitidos)))
	lineas.append(_("Errores: {n}").format(n=formato.miles(len(operacion.errores))))
	return "\n".join(lineas)


def texto_errores(operacion: Operacion) -> str:
	"""Lista copiable de errores, una línea por elemento."""
	if not operacion.errores:
		return _("Esta operación no tiene errores.")
	lineas = [operacion.descripcion(), ""]
	for error in list(operacion.errores):
		lineas.append(f"{error.ruta}: {error.mensaje}" if error.ruta else error.mensaje)
	return "\n".join(lineas)


def admite_reintento(operacion: Operacion) -> bool:
	return isinstance(operacion, OperacionCopiar) and bool(operacion.fallidos) and operacion.estado.final


class VentanaOperaciones(wx.Frame):
	"""Operaciones en curso. Muéstrela con ``mostrar()``; Escape o «Cerrar» la ocultan.

	:param gestor_operaciones: ``GestorOperaciones``.
	:param gestor_decisiones: ``GestorDecisiones`` (para «Atender la decisión pendiente»).
	:param reintentar: ``reintentar(operacion)`` lanza una copia nueva con los que fallaron.
	"""

	def __init__(self, padre: wx.Window | None, gestor_operaciones, gestor_decisiones,
			reintentar: Callable[[Operacion], None] | None = None) -> None:
		estilo = wx.DEFAULT_FRAME_STYLE | (wx.FRAME_FLOAT_ON_PARENT if padre is not None else 0)
		super().__init__(padre, title=_("Operaciones en curso"), style=estilo, name=_("Operaciones en curso"))
		self._gestor = gestor_operaciones
		self._decisiones = gestor_decisiones
		self._reintentar = reintentar
		self._filas: list[Operacion] = []

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)

		etiqueta_lista = wx.StaticText(panel, label=_("&Operaciones:"))
		self.lista = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=panel.FromDIP(wx.Size(640, 200)),
			name=_("Operaciones"))
		for columna, (texto, ancho) in enumerate(((_("Operación"), 400), (_("Estado"), 150), (_("Progreso"), 80))):
			self.lista.InsertColumn(columna, texto, width=panel.FromDIP(ancho))
		self.lista.SetHelpText(_("Copias, movimientos y demás operaciones de esta sesión. El detalle de la elegida va debajo."))
		sizer.Add(etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)

		etiqueta_detalle = wx.StaticText(panel, label=_("&Información de la operación:"))
		self.detalle = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
			size=panel.FromDIP(wx.Size(-1, 150)), name=_("Información de la operación"))
		self.detalle.SetHelpText(_("Archivo actual, porcentajes, bytes, velocidad y tiempo restante de la operación elegida."))
		sizer.Add(etiqueta_detalle, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.detalle, 1, wx.EXPAND | wx.ALL, 8)

		botones = wx.WrapSizer(wx.HORIZONTAL)
		self.boton_atender = wx.Button(panel, label=_("&Atender la decisión pendiente"))
		self.boton_atender.SetHelpText(_("Muestra la pregunta que espera respuesta de alguna operación."))
		self.boton_pausa = wx.Button(panel, label=_("&Pausar"))
		self.boton_pausa.SetHelpText(_("Pausa o reanuda la operación elegida."))
		self.boton_cancelar = wx.Button(panel, label=_("&Cancelar la operación"))
		self.boton_cancelar.SetHelpText(_("Cancela la operación elegida. Lo ya copiado se queda."))
		self.boton_detalles = wx.Button(panel, label=_("&Detalles"))
		self.boton_detalles.SetHelpText(_("Muestra los errores de la operación elegida en un texto que se puede copiar."))
		self.boton_reintentar = wx.Button(panel, label=_("Reintentar los que &fallaron"))
		self.boton_reintentar.SetHelpText(_("Lanza una copia nueva solo con los archivos que fallaron."))
		self.boton_limpiar = wx.Button(panel, label=_("&Limpiar las terminadas"))
		self.boton_limpiar.SetHelpText(_("Quita de la lista las operaciones que ya terminaron."))
		self.boton_cerrar = wx.Button(panel, wx.ID_CLOSE, label=_("C&errar"))
		self.boton_cerrar.SetHelpText(_("Oculta esta ventana; las operaciones siguen. F12 la vuelve a mostrar."))
		for boton in (self.boton_atender, self.boton_pausa, self.boton_cancelar, self.boton_detalles,
				self.boton_reintentar, self.boton_limpiar, self.boton_cerrar):
			botones.Add(boton, 0, wx.ALL, 4)
		sizer.Add(botones, 0, wx.EXPAND | wx.ALL, 4)

		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)

		self.boton_atender.Bind(wx.EVT_BUTTON, lambda _e: self.atender())
		self.boton_pausa.Bind(wx.EVT_BUTTON, lambda _e: self.alternar_pausa())
		self.boton_cancelar.Bind(wx.EVT_BUTTON, lambda _e: self.cancelar())
		self.boton_detalles.Bind(wx.EVT_BUTTON, lambda _e: self.ver_detalles())
		self.boton_reintentar.Bind(wx.EVT_BUTTON, lambda _e: self.reintentar())
		self.boton_limpiar.Bind(wx.EVT_BUTTON, lambda _e: self.limpiar())
		self.boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.ocultar())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self.actualizar())
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda _e: self.actualizar())
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)

		self._temporizador = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self._al_temporizador(), self._temporizador)
		self.actualizar()

	# ── Mostrar y ocultar ───────────────────────────────────────────────────

	def mostrar(self) -> None:
		"""Muestra la ventana con el foco en la lista y empieza a refrescar."""
		self.actualizar()
		if not self.IsShown():
			self.Show()
		if self.IsIconized():
			self.Iconize(False)
		self.Raise()
		if self._filas and self.lista.GetFirstSelected() < 0:
			self.lista.Focus(0)
			self.lista.Select(0)
		self.lista.SetFocus()
		if not self._temporizador.IsRunning():
			self._temporizador.Start(MILISEGUNDOS_REFRESCO)

	def ocultar(self) -> None:
		self._temporizador.Stop()
		self.Hide()
		padre = self.GetParent()
		if padre is not None and padre.IsShown():
			padre.Raise()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if evento.CanVeto():
			# Cerrar con Alt+F4 o la X solo la oculta: las operaciones siguen.
			evento.Veto()
			self.ocultar()
			return
		self._temporizador.Stop()
		evento.Skip()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_ESCAPE and evento.GetModifiers() == wx.MOD_NONE:
			self.ocultar()
			return
		if evento.GetKeyCode() == ord("H") and evento.GetModifiers() == wx.MOD_CONTROL:
			from app.ui.accesibilidad.ayuda import describir_control_enfocado

			describir_control_enfocado(self)
			return
		evento.Skip()

	def _al_temporizador(self) -> None:
		if not self.IsShown():
			self._temporizador.Stop()
			return
		try:
			self.actualizar()
		except Exception:  # noqa: BLE001 - un fallo al refrescar no debe repetirse 4 veces por segundo sin registro
			log.exception("Falló el refresco de la ventana de operaciones")
			self._temporizador.Stop()

	# ── Refresco ────────────────────────────────────────────────────────────

	def operacion_elegida(self) -> Operacion | None:
		fila = self.lista.GetFirstSelected()
		if fila < 0:
			fila = self.lista.GetFocusedItem()
		return self._filas[fila] if 0 <= fila < len(self._filas) else None

	def actualizar(self) -> None:
		"""Sincroniza filas, textos y botones con el gestor sin mover selección ni foco."""
		operaciones = self._gestor.operaciones()
		ids = [o.id for o in operaciones]
		# Quitar las que ya no están (de abajo arriba para no descolocar los índices).
		for fila in range(len(self._filas) - 1, -1, -1):
			if self._filas[fila].id not in ids:
				elegida = self.lista.IsSelected(fila)
				self.lista.DeleteItem(fila)
				del self._filas[fila]
				if elegida and self._filas:
					nueva = min(fila, len(self._filas) - 1)
					self.lista.Select(nueva)
					self.lista.Focus(nueva)
		presentes = {o.id for o in self._filas}
		for operacion in operaciones:
			if operacion.id not in presentes:
				fila = self.lista.GetItemCount()
				self.lista.InsertItem(fila, operacion.descripcion())
				self._filas.append(operacion)
		if self._filas and self.lista.GetFirstSelected() < 0:
			# Sin fila elegida el lector no lee nada al llegar a la lista; elegir una no mueve el foco.
			self.lista.Select(0)
			self.lista.Focus(0)
		for fila, operacion in enumerate(self._filas):
			self._poner(fila, COL_OPERACION, operacion.descripcion())
			self._poner(fila, COL_ESTADO, operacion.estado.texto)
			self._poner(fila, COL_PROGRESO, texto_progreso(operacion))
		self._actualizar_detalle()
		self._actualizar_botones()

	def _poner(self, fila: int, columna: int, texto: str) -> None:
		# Solo si cambia: reescribir el mismo texto genera eventos de cambio inútiles para el lector.
		if self.lista.GetItemText(fila, columna) != texto:
			self.lista.SetItem(fila, columna, texto)

	def _actualizar_detalle(self) -> None:
		operacion = self.operacion_elegida()
		if operacion is None:
			texto = _("No hay operaciones.") if not self._filas else _("Elija una operación de la lista.")
		else:
			texto = detalle_operacion(operacion)
		if self.detalle.GetValue() == texto:
			return
		if self.detalle.HasFocus():
			posicion = self.detalle.GetInsertionPoint()
			self.detalle.ChangeValue(texto)
			self.detalle.SetInsertionPoint(min(posicion, self.detalle.GetLastPosition()))
		else:
			self.detalle.ChangeValue(texto)

	@staticmethod
	def _habilitar(boton: wx.Button, valor: bool) -> None:
		"""Nunca desactiva el botón que tiene el foco: Windows movería el foco sin avisar."""
		if not valor and boton.HasFocus():
			return
		if boton.IsEnabled() != valor:
			boton.Enable(valor)

	@staticmethod
	def _etiquetar(boton: wx.Button, etiqueta: str) -> None:
		if boton.GetLabel() != etiqueta:
			boton.SetLabel(etiqueta)

	def _actualizar_botones(self) -> None:
		operacion = self.operacion_elegida()
		viva = operacion is not None and not operacion.estado.final
		self._habilitar(self.boton_atender, bool(self._decisiones is not None and self._decisiones.hay_pendientes()))
		en_pausa = operacion is not None and (operacion.pausa_pedida or operacion.estado == Estado.EN_PAUSA)
		self._etiquetar(self.boton_pausa, _("&Reanudar") if en_pausa else _("&Pausar"))
		self._habilitar(self.boton_pausa, viva and operacion.admite_pausa)
		self._habilitar(self.boton_cancelar, viva)
		self._habilitar(self.boton_detalles, operacion is not None and bool(operacion.errores))
		self._habilitar(self.boton_reintentar, operacion is not None and self._reintentar is not None and admite_reintento(operacion))
		self._habilitar(self.boton_limpiar, any(o.estado.final for o in self._filas))

	# ── Acciones ────────────────────────────────────────────────────────────

	def _elegida_o_aviso(self) -> Operacion | None:
		operacion = self.operacion_elegida()
		if operacion is None:
			anuncios.anunciar(_("No hay ninguna operación elegida"), anuncios.RESULTADO)
		return operacion

	def atender(self) -> None:
		if self._decisiones is None or not self._decisiones.atender_pendiente(padre=self):
			anuncios.anunciar(_("No hay decisiones pendientes"), anuncios.RESULTADO)
		self.actualizar()

	def alternar_pausa(self) -> None:
		operacion = self._elegida_o_aviso()
		if operacion is None:
			return
		if operacion.estado.final:
			anuncios.anunciar(_("La operación ya terminó"), anuncios.RESULTADO)
		elif not operacion.admite_pausa:
			anuncios.anunciar(_("Esta operación no se puede pausar"), anuncios.RESULTADO)
		elif operacion.pausa_pedida or operacion.estado == Estado.EN_PAUSA:
			operacion.reanudar()
		else:
			operacion.pausar()
		self.actualizar()

	def cancelar(self) -> None:
		operacion = self._elegida_o_aviso()
		if operacion is None:
			return
		if operacion.estado.final:
			anuncios.anunciar(_("La operación ya terminó"), anuncios.RESULTADO)
		else:
			self._gestor.cancelar(operacion)
			anuncios.anunciar(_("Cancelando: {d}").format(d=operacion.descripcion()), anuncios.RESULTADO)
		self.actualizar()

	def ver_detalles(self) -> None:
		operacion = self._elegida_o_aviso()
		if operacion is None:
			return
		from app.ui.dialogo_texto import mostrar_texto

		mostrar_texto(self, _("Errores de la operación"), _("&Errores:"), texto_errores(operacion), copiable=True)

	def reintentar(self) -> None:
		operacion = self._elegida_o_aviso()
		if operacion is None:
			return
		if self._reintentar is None or not admite_reintento(operacion):
			anuncios.anunciar(_("No hay archivos que reintentar en esta operación"), anuncios.RESULTADO)
			return
		self._reintentar(operacion)
		self.actualizar()

	def limpiar(self) -> None:
		self._gestor.limpiar_terminadas()
		self.actualizar()
