# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana del reproductor (no modal): cola, estado en texto y botones (diseño 2.0, 11.1).

Se construye con lo que ofrece ``zc.ui`` (``VentanaComplemento``, ``ListaAccesible``,
``SliderAccesible``...), nunca con controles dibujados a mano. Cerrarla (Escape)
no detiene la reproducción.

Teclas propias de la ventana (además de Tab y las letras de acceso):
Espacio pausa o continúa; Izquierda y Derecha, salto corto; Ctrl+Izquierda y
Ctrl+Derecha, salto medio; Re Pág y Av Pág, salto largo; Más y Menos, volumen;
Ctrl+Más y Ctrl+Menos, velocidad; P dice la posición; G va a un tiempo; M añade
un marcador; Ctrl+M abre la lista de marcadores; R cambia el modo de repetir;
A, el orden aleatorio; Supr quita de la cola la pista elegida; Intro en la cola
la reproduce. Arriba y Abajo son de la lista.
"""

from __future__ import annotations

import builtins
import logging
import os
import time
from typing import Any

import wx

from . import listas, tiempos

log = logging.getLogger(__name__)

#: Para ``revisar_teclado`` en las pruebas: las teclas que la ventana atiende a mano.
TECLAS_PROPIAS = ("Espacio", "Izquierda", "Derecha", "Ctrl+Izquierda", "Ctrl+Derecha", "Re Pág", "Av Pág", "P", "G", "M",
	"Ctrl+M", "R", "A", "Supr")

VELOCIDADES = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class VentanaReproductor:
	"""Composición sobre ``zc.ui.VentanaComplemento``: ``self.marco`` es la ventana de wx."""

	def __init__(self, ui: Any, padre: wx.Window | None, reproductor: Any, complemento: Any) -> None:
		self.ui = ui
		self.reproductor = reproductor
		self.complemento = complemento
		self._firma_cola: tuple = ()
		self.marco = ui.VentanaComplemento(padre, _("Reproductor multimedia"), complemento.zc.id)
		panel = wx.Panel(self.marco)
		self.panel = panel
		sizer = wx.BoxSizer(wx.VERTICAL)

		sizer.Add(wx.StaticText(panel, label=_("C&ola de reproducción:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		self.lista = ui.ListaAccesible(panel, _("Cola de reproducción"),
			columnas=[(_("Número"), 70), (_("Título"), 360), (_("Duración"), 90)])
		self.lista.SetHelpText(_("Pistas de la cola. Intro reproduce la elegida y Supr la quita. Las flechas izquierda y derecha "
			"saltan dentro de la pista; Control más un número lee una columna."))
		sizer.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

		sizer.Add(wx.StaticText(panel, label=_("&Estado:")), 0, wx.LEFT | wx.RIGHT, 6)
		self.estado = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=panel.FromDIP(wx.Size(-1, 80)))
		self.estado.SetHelpText(_("Pista, posición, volumen, velocidad, repetición y temporizador. Se actualiza cada segundo."))
		sizer.Add(self.estado, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(wx.StaticText(panel, label=_("Vol&umen:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
		self.volumen = ui.SliderAccesible(panel, valor=reproductor.volumen, minimo=0, maximo=100, paso=5, paso_pagina=10)
		self.volumen.SetHelpText(_("Volumen del reproductor, de 0 a 100. Más y Menos lo cambian desde cualquier control."))
		fila.Add(self.volumen, 1, wx.EXPAND | wx.RIGHT, 12)
		fila.Add(wx.StaticText(panel, label=_("&Velocidad:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
		self.velocidad = wx.Choice(panel, choices=[tiempos.texto_velocidad(v) for v in VELOCIDADES])
		self.velocidad.SetHelpText(_("Velocidad de reproducción. Con FFplay no se puede cambiar."))
		fila.Add(self.velocidad, 0)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 6)

		rejilla = wx.WrapSizer(wx.HORIZONTAL)
		self.botones: dict[str, wx.Button] = {}
		for clave, etiqueta, ayuda, funcion in (
			("pausa", _("&Pausa o continuar"), _("Pausa la reproducción o la continúa (también Espacio)."), self._pausa),
			("detener", _("&Detener"), _("Detiene la reproducción; la posición de los archivos largos se recuerda."), self._detener),
			("anterior", _("Pista a&nterior"), _("Vuelve al principio de la pista o a la anterior."), self._anterior),
			("siguiente", _("&Siguiente pista"), _("Pasa a la pista siguiente de la cola."), self._siguiente),
			("ir", _("&Ir a un tiempo..."), _("Va a un tiempo (1:23:00) o a un porcentaje (50 %) de la pista (también G)."), self._ir_a),
			("marcar", _("Añadir &marcador..."), _("Guarda la posición actual con un nombre (también M)."), self._marcar),
			("marcadores", _("&Lista de marcadores..."), _("Va a uno de los marcadores de esta pista (también Ctrl+M)."), self._marcadores),
			("repetir", _("&Repetir"), _("Cambia entre sin repetir, repetir esta pista y repetir la cola (también R)."), self._repetir),
			("aleatorio", _("&Aleatorio"), _("Activa o quita el orden aleatorio (también A)."), self._aleatorio),
			("abrir", _("A&brir una lista M3U..."), _("Sustituye la cola por una lista M3U o M3U8."), self._abrir_lista),
			("guardar", _("&Guardar la cola como M3U..."), _("Guarda la cola en una lista M3U8 con rutas relativas."), self._guardar_lista),
			("quitar", _("&Quitar de la cola"), _("Quita de la cola la pista elegida en la lista (también Supr)."), self._quitar),
			("temporizador", _("&Temporizador de apagado..."), _("Detiene la reproducción cuando pasan los minutos elegidos."), self._temporizador),
			("cerrar", _("&Cerrar"), _("Cierra la ventana; la reproducción sigue (también Escape)."), lambda: self.marco.Close()),
		):
			boton = wx.Button(panel, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, f=funcion: f())
			rejilla.Add(boton, 0, wx.ALL, 3)
			self.botones[clave] = boton
		sizer.Add(rejilla, 0, wx.EXPAND | wx.ALL, 3)
		panel.SetSizer(sizer)
		self.marco.SetSize(self.marco.FromDIP(wx.Size(720, 520)))

		self._seleccionar_velocidad()
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda e: self.reproductor.ir_a_pista(e.GetIndex()))
		self.volumen.Bind(wx.EVT_SLIDER, lambda _e: self.reproductor.fijar_volumen(self.volumen.GetValue()))
		self.velocidad.Bind(wx.EVT_CHOICE, self._al_elegir_velocidad)
		self.estado.Bind(wx.EVT_SET_FOCUS, self._al_enfocar_estado)
		panel.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self.marco.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.reproductor.al_cambiar.append(self.refrescar)
		self.refrescar()

	# ── Refresco ─────────────────────────────────────────────────────────────

	def refrescar(self) -> None:
		if not self.marco:
			return
		reproductor = self.reproductor
		firma = tuple((p.ruta, p.nombre, int(p.duracion)) for p in reproductor.cola) + (reproductor.indice,)
		if firma != self._firma_cola:
			self._firma_cola = firma
			filas = []
			for numero, pista in enumerate(reproductor.cola, start=1):
				texto_numero = str(numero) if numero - 1 != reproductor.indice else _("{n}, actual").format(n=numero)
				filas.append([texto_numero, pista.nombre, tiempos.formatear(pista.duracion) if pista.duracion > 0 else ""])
			self.lista.reemplazar_filas(filas, conservar_foco=True)
		if self.volumen.GetValue() != reproductor.volumen:
			self.volumen.SetValue(reproductor.volumen)
		self._seleccionar_velocidad()
		if wx.Window.FindFocus() is not self.estado:
			self.estado.ChangeValue(self.texto_estado())

	def texto_estado(self) -> str:
		reproductor = self.reproductor
		pista = reproductor.pista
		lineas = []
		if pista is None:
			lineas.append(_("Sin reproducir. {n} pistas en la cola.").format(n=len(reproductor.cola)))
		else:
			estados = {"reproduciendo": _("Reproduciendo"), "pausado": _("En pausa"), "detenido": _("Detenido"),
				"cargando": _("Abriendo")}
			lineas.append(_("{e}: {t} (pista {n} de {c}).").format(e=estados.get(reproductor.estado(), reproductor.estado()),
				t=pista.nombre, n=reproductor.indice + 1, c=len(reproductor.cola)))
			lineas.append(reproductor.texto_posicion() + ".")
			if reproductor.motor is not None:
				lineas.append(_("Motor: {m}.").format(m=reproductor.motor.nombre))
		lineas.append(_("Volumen {v}. Velocidad {x}. {r}. {a}.").format(v=reproductor.volumen,
			x=tiempos.texto_velocidad(reproductor.velocidad), r=reproductor.texto_repetir(),
			a=_("Orden aleatorio") if reproductor.aleatorio else _("Orden de la cola")))
		if reproductor.fin_temporizador:
			restante = max(0, reproductor.fin_temporizador - time.time())
			lineas.append(_("Se detendrá dentro de {t}.").format(t=tiempos.formatear(restante)))
		return "\n".join(lineas)

	def _al_enfocar_estado(self, evento: wx.FocusEvent) -> None:
		self.estado.ChangeValue(self.texto_estado())
		evento.Skip()

	def _seleccionar_velocidad(self) -> None:
		cercana = min(range(len(VELOCIDADES)), key=lambda i: abs(VELOCIDADES[i] - self.reproductor.velocidad))
		if self.velocidad.GetSelection() != cercana:
			self.velocidad.SetSelection(cercana)

	def _al_elegir_velocidad(self, _evento: wx.CommandEvent) -> None:
		nueva = VELOCIDADES[self.velocidad.GetSelection()]
		self.reproductor.cambiar_velocidad(nueva - self.reproductor.velocidad)

	# ── Teclas ───────────────────────────────────────────────────────────────

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		caracter = chr(evento.GetUnicodeKey()) if evento.GetUnicodeKey() not in (0, wx.WXK_NONE) else ""
		modificadores = evento.GetModifiers()
		foco = wx.Window.FindFocus()
		en_control_propio = isinstance(foco, (wx.Slider, wx.Choice))
		saltos = self.complemento.saltos()
		if modificadores == wx.MOD_NONE:
			if codigo == wx.WXK_SPACE and not isinstance(foco, wx.Button):
				self._pausa()
				return
			if not en_control_propio and codigo in (wx.WXK_LEFT, wx.WXK_RIGHT):
				self.reproductor.saltar(saltos[0] if codigo == wx.WXK_RIGHT else -saltos[0])
				return
			if not en_control_propio and codigo in (wx.WXK_PAGEUP, wx.WXK_PAGEDOWN):
				self.reproductor.saltar(saltos[2] if codigo == wx.WXK_PAGEDOWN else -saltos[2])
				return
			if codigo == wx.WXK_DELETE and foco is self.lista:
				self._quitar()
				return
			letra = caracter.lower()
			acciones = {"p": self.reproductor.decir_posicion, "g": self._ir_a, "m": self._marcar, "r": self._repetir,
				"a": self._aleatorio}
			if letra in acciones and (not isinstance(foco, wx.TextCtrl) or not foco.IsEditable()):
				acciones[letra]()
				return
		if modificadores == wx.MOD_CONTROL:
			if codigo in (wx.WXK_LEFT, wx.WXK_RIGHT):
				self.reproductor.saltar(saltos[1] if codigo == wx.WXK_RIGHT else -saltos[1])
				return
			if codigo == ord("M"):
				self._marcadores()
				return
		if modificadores in (wx.MOD_NONE, wx.MOD_SHIFT, wx.MOD_CONTROL, wx.MOD_CONTROL | wx.MOD_SHIFT):
			mas = caracter == "+" or codigo == wx.WXK_NUMPAD_ADD
			menos = caracter == "-" or codigo == wx.WXK_NUMPAD_SUBTRACT
			if mas or menos:
				if modificadores & wx.MOD_CONTROL:
					self.reproductor.cambiar_velocidad(0.25 if mas else -0.25)
				else:
					self.reproductor.cambiar_volumen(5 if mas else -5)
				return
		evento.Skip()

	# ── Acciones ─────────────────────────────────────────────────────────────

	def _pausa(self) -> None:
		self.reproductor.pausa_continuar()

	def _detener(self) -> None:
		self.reproductor.detener()

	def _anterior(self) -> None:
		self.reproductor.anterior()

	def _siguiente(self) -> None:
		self.reproductor.siguiente()

	def _repetir(self) -> None:
		self.reproductor.cambiar_repetir()

	def _aleatorio(self) -> None:
		self.reproductor.cambiar_aleatorio()

	def _ir_a(self) -> None:
		self.complemento.pedir_ir_a(self.marco)

	def _marcar(self) -> None:
		self.complemento.pedir_marcador(self.marco)

	def _marcadores(self) -> None:
		self.complemento.elegir_marcador(self.marco)

	def _temporizador(self) -> None:
		self.complemento.pedir_temporizador(self.marco)

	def _guardar_lista(self) -> None:
		self.complemento.guardar_cola(self.marco)

	def _quitar(self) -> None:
		fila = self.lista.fila_actual()
		if fila < 0 or fila >= len(self.reproductor.cola):
			self.complemento.zc.anunciar(_("No hay ninguna pista elegida"), "resultado")
			return
		nombre = self.reproductor.cola[fila].nombre
		self.reproductor.quitar(fila)
		self.complemento.zc.anunciar(_("Quitada de la cola: {n}").format(n=nombre), "resultado")

	def _abrir_lista(self) -> None:
		dialogo = wx.FileDialog(self.marco, _("Abrir una lista M3U"), wildcard=_("Listas M3U (*.m3u;*.m3u8)|*.m3u;*.m3u8"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
		try:
			if self.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			ruta = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		self.complemento.abrir_lista(ruta)

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		try:
			self.reproductor.al_cambiar.remove(self.refrescar)
		except ValueError:
			log.debug("La ventana ya no estaba suscrita", exc_info=True)
		self.complemento.ventana_cerrada(self)
		evento.Skip()


def ruta_lista_por_defecto(cola: list[Any]) -> str:
	"""Carpeta de la primera pista y nombre «Cola.m3u8» para el diálogo de guardar."""
	if not cola:
		return ""
	return os.path.join(os.path.dirname(cola[0].ruta), "Cola" + listas.EXTENSIONES[1])
