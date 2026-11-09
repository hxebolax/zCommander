# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana de la búsqueda instantánea (diseño 2.0, 11.5). Con wx: solo se importa al abrirla.

Recorrido con el teclado: «Buscar» (foco inicial) → «Texto contenido» →
«Búsquedas guardadas» → «Estado» (solo lectura) → «Resultados» → botones.
Se busca al dejar de teclear (``retardo_ms``) en un hilo; el recuento se
anuncia como resultado tras esa pausa, nunca en cada tecla. En la lista,
Intro va al archivo en el panel activo. Escape cierra y F1 abre la ayuda
(``VentanaComplemento``); Ctrl+H dice la ayuda del control enfocado.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import wx

from app.plugins import api

from . import consulta, motores

log = logging.getLogger("zcplugins.zc.busqueda_instantanea")

ARCHIVO_GUARDADAS = "busquedas.json"


def leer_guardadas(carpeta: Path) -> list[str]:
	try:
		datos = json.loads((carpeta / ARCHIVO_GUARDADAS).read_text(encoding="utf-8"))
	except FileNotFoundError:
		return []
	except (OSError, ValueError):
		log.warning("No se pudieron leer las búsquedas guardadas", exc_info=True)
		return []
	return [str(d) for d in datos if isinstance(d, str) and d.strip()] if isinstance(datos, list) else []


def escribir_guardadas(carpeta: Path, busquedas: list[str]) -> None:
	ruta = carpeta / ARCHIVO_GUARDADAS
	temporal = ruta.with_suffix(".tmp")
	temporal.write_text(json.dumps(busquedas, ensure_ascii=False, indent=1), encoding="utf-8")
	temporal.replace(ruta)


class VentanaBusqueda:
	"""Controla la ventana; ``marco`` es la ``zc.ui.VentanaComplemento`` (un ``wx.Frame``)."""

	def __init__(self, zc: api.Anfitrion, padre: wx.Window | None, comprobar_motores: bool = True) -> None:
		self.zc = zc
		ui = zc.ui
		self.marco: wx.Frame = ui.VentanaComplemento(padre, "Búsqueda instantánea", zc.id, size=(760, 560))
		self.rutas: list[str] = []
		self._tarea: Any = None
		self._generacion = 0
		self._temporizador: wx.CallLater | None = None
		self.motores: list[str] | None = None

		panel = wx.Panel(self.marco)
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		_, self.campo = ui.crear_campo(panel, "&Buscar:", wx.TextCtrl, sizer=cuerpo, style=wx.TE_PROCESS_ENTER,
			ayuda="Escriba parte del nombre. Admite la sintaxis de Everything: ext:pdf, size:>1gb, dm:today, "
				"comodines, | para «o» y ! para «no». Intro va al primer resultado.")
		_, self.contenido = ui.crear_campo(panel, "&Texto contenido (solo con el índice de Windows):", wx.TextCtrl,
			sizer=cuerpo, ayuda="Si escribe algo aquí, se buscan los archivos que lo contienen con el índice de búsqueda "
				"de Windows.")
		self.guardadas = leer_guardadas(zc.datos)
		_, self.lista_guardadas = ui.crear_campo(panel, "Búsquedas &guardadas:", wx.Choice, sizer=cuerpo,
			choices=self._opciones_guardadas(), ayuda="Elija una búsqueda guardada para repetirla.")
		self.lista_guardadas.SetSelection(0)
		_, self.estado = ui.crear_campo(panel, "&Estado:", wx.TextCtrl, sizer=cuerpo,
			style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_NO_VSCROLL, size=(-1, 50),
			ayuda="Qué motor se usa, cuántos resultados hay o por qué no se puede buscar.")
		self.estado.SetValue("Comprobando los motores de búsqueda...")
		etiqueta = wx.StaticText(panel, label="&Resultados:")
		self.lista = ui.ListaAccesible(panel, "Resultados", [("Nombre", 260), ("Carpeta", 420)], virtual=True)
		self.lista.SetHelpText("Resultados de la búsqueda. Intro va al archivo en el panel activo.")
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)

		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_ir = wx.Button(panel, label="&Ir al archivo")
		self.boton_ir.SetHelpText("Lleva el panel activo a la carpeta del resultado y pone el cursor en él.")
		self.boton_panel = wx.Button(panel, label="Enviar al &panel")
		self.boton_panel.SetHelpText("Muestra todos los resultados en el panel activo como lista de resultados.")
		self.boton_guardar = wx.Button(panel, label="Guar&dar la búsqueda")
		self.boton_guardar.SetHelpText("Guarda lo escrito en «Buscar» en las búsquedas guardadas.")
		self.boton_olvidar = wx.Button(panel, label="&Olvidar la búsqueda guardada")
		self.boton_olvidar.SetHelpText("Quita de la lista la búsqueda guardada elegida.")
		self.boton_cerrar = wx.Button(panel, wx.ID_CLOSE, label="&Cerrar")
		self.boton_cerrar.SetHelpText("Cierra la búsqueda instantánea (también con Escape).")
		for boton in (self.boton_ir, self.boton_panel, self.boton_guardar, self.boton_olvidar, self.boton_cerrar):
			botones.Add(boton, 0, wx.ALL, 4)
		cuerpo.Add(botones, 0, wx.ALIGN_RIGHT)
		panel.SetSizer(cuerpo)

		self.campo.Bind(wx.EVT_TEXT, self._al_escribir)
		self.contenido.Bind(wx.EVT_TEXT, self._al_escribir)
		self.campo.Bind(wx.EVT_TEXT_ENTER, lambda _e: self.ir_al_archivo(0))
		self.lista_guardadas.Bind(wx.EVT_CHOICE, self._al_elegir_guardada)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda e: self.ir_al_archivo(e.GetIndex()))
		self.boton_ir.Bind(wx.EVT_BUTTON, lambda _e: self.ir_al_archivo(self.lista.fila_actual()))
		self.boton_panel.Bind(wx.EVT_BUTTON, lambda _e: self.enviar_al_panel())
		self.boton_guardar.Bind(wx.EVT_BUTTON, lambda _e: self.guardar_busqueda())
		self.boton_olvidar.Bind(wx.EVT_BUTTON, lambda _e: self.olvidar_busqueda())
		self.boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.marco.Close())
		self.marco.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self.marco.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self._actualizar_botones()
		if comprobar_motores:
			zc.tareas.enviar(lambda _tarea: motores.motores_disponibles(), al_terminar=self.mostrar_motores,
				al_fallar=lambda _e: self.mostrar_motores([]), nombre="busqueda_instantanea_motores")

	# ── Estado ───────────────────────────────────────────────────────────────

	def _opciones_guardadas(self) -> list[str]:
		return ["(ninguna)", *self.guardadas]

	def mostrar_motores(self, disponibles: list[str]) -> None:
		"""Pone en «Estado» el motor que se usará o, si no hay ninguno, por qué y qué hacer."""
		if not self.marco:
			return
		self.motores = list(disponibles)
		if not disponibles:
			self.estado.SetValue(motores.texto_sin_motores())
			return
		nombres = " y ".join(motores.NOMBRES_MOTOR[m] for m in disponibles)
		self.estado.SetValue(f"Disponible: {nombres}. Escriba para buscar.")

	def _actualizar_botones(self) -> None:
		hay = bool(self.rutas)
		self.boton_ir.Enable(hay)
		self.boton_panel.Enable(hay)
		self.boton_olvidar.Enable(self.lista_guardadas.GetSelection() > 0)

	# ── Búsqueda ─────────────────────────────────────────────────────────────

	def _al_escribir(self, evento: wx.CommandEvent) -> None:
		evento.Skip()
		retardo = int(self.zc.config.obtener("retardo_ms", 300))
		if self._temporizador is not None and self._temporizador.IsRunning():
			self._temporizador.Stop()
		self._temporizador = wx.CallLater(retardo, self.buscar)

	def buscar(self) -> None:
		"""Lanza la búsqueda en un hilo; una búsqueda nueva cancela la anterior."""
		if not self.marco:
			return
		texto, contenido = self.campo.GetValue().strip(), self.contenido.GetValue().strip()
		if self._tarea is not None:
			self._tarea.cancelar()
		self._generacion += 1
		generacion = self._generacion
		if not texto and not contenido:
			self.mostrar_resultado(generacion, motores.Resultado("", []))
			return
		config = self.zc.config
		opciones = {
			"preferencia": str(config.obtener("motor", "automatico")),
			"contenido": contenido,
			"max_resultados": int(config.obtener("max_resultados", 1000)),
			"incluir_ocultos": bool(config.obtener("incluir_ocultos", False)),
			"excluidas": tuple(str(c) for c in config.obtener("carpetas_excluidas", []) or ()),
		}
		self.estado.SetValue("Buscando...")
		self._tarea = self.zc.tareas.enviar(
			lambda tarea: motores.buscar(texto, cancelacion=tarea, **opciones),
			al_terminar=lambda resultado: self.mostrar_resultado(generacion, resultado),
			al_fallar=lambda error: self.mostrar_fallo(generacion, error), nombre="busqueda_instantanea")

	def mostrar_resultado(self, generacion: int, resultado: motores.Resultado) -> None:
		if not self.marco or generacion != self._generacion:
			return
		self.rutas = list(resultado.rutas)
		self.lista.reemplazar_filas([consulta.nombre_y_carpeta(r) for r in self.rutas], conservar_foco=False)
		self._actualizar_botones()
		if not resultado.motor:
			self.estado.SetValue("Escriba para buscar.")
			return
		n = len(self.rutas)
		recuento = "Ningún resultado" if n == 0 else "1 resultado" if n == 1 else f"{n} resultados"
		self.estado.SetValue(f"{recuento} con {motores.NOMBRES_MOTOR[resultado.motor]}.")
		self.zc.anunciar(recuento, api.RESULTADO)

	def mostrar_fallo(self, generacion: int, error: BaseException) -> None:
		if not self.marco or generacion != self._generacion:
			return
		if type(error).__name__ in ("TareaCancelada", "TareaDuplicada"):
			return
		texto = str(error) if isinstance(error, motores.SinMotor) else f"No se pudo buscar: {error}"
		if not isinstance(error, motores.SinMotor):
			log.warning("Falló la búsqueda instantánea", exc_info=error)
		self.rutas = []
		self.lista.limpiar()
		self._actualizar_botones()
		self.estado.SetValue(texto)
		self.zc.anunciar(texto, api.RESULTADO)

	# ── Acciones ─────────────────────────────────────────────────────────────

	def ir_al_archivo(self, fila: int) -> None:
		if not 0 <= fila < len(self.rutas):
			if not self.rutas:
				self.zc.anunciar("No hay resultados", api.RESULTADO)
			return
		ruta = self.rutas[fila]
		self.zc.abrir_ruta(ruta)
		self.marco.Close()

	def enviar_al_panel(self) -> None:
		if not self.rutas:
			return
		titulo = f"Búsqueda instantánea: {self.campo.GetValue().strip() or self.contenido.GetValue().strip()}"
		self.zc.ui.mostrar_resultados(titulo, list(self.rutas))
		self.marco.Close()

	def guardar_busqueda(self) -> None:
		texto = self.campo.GetValue().strip()
		if not texto:
			self.zc.anunciar("Escriba antes qué buscar", api.RESULTADO)
			return
		if texto not in self.guardadas:
			self.guardadas.append(texto)
			escribir_guardadas(self.zc.datos, self.guardadas)
			self.lista_guardadas.Set(self._opciones_guardadas())
		self.lista_guardadas.SetSelection(self.guardadas.index(texto) + 1)
		self._actualizar_botones()
		self.zc.anunciar(f"Búsqueda guardada: {texto}", api.RESULTADO)

	def olvidar_busqueda(self) -> None:
		indice = self.lista_guardadas.GetSelection() - 1
		if not 0 <= indice < len(self.guardadas):
			return
		texto = self.guardadas.pop(indice)
		escribir_guardadas(self.zc.datos, self.guardadas)
		self.lista_guardadas.Set(self._opciones_guardadas())
		self.lista_guardadas.SetSelection(0)
		self._actualizar_botones()
		self.zc.anunciar(f"Búsqueda olvidada: {texto}", api.RESULTADO)

	def _al_elegir_guardada(self, evento: wx.CommandEvent) -> None:
		indice = self.lista_guardadas.GetSelection() - 1
		self._actualizar_botones()
		if 0 <= indice < len(self.guardadas):
			self.campo.SetValue(self.guardadas[indice])
		evento.Skip()

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == ord("H") and evento.GetModifiers() == wx.MOD_CONTROL:
			enfocado = wx.Window.FindFocus()
			ayuda = enfocado.GetHelpText() if enfocado else ""
			self.zc.anunciar(ayuda or "Este control no tiene ayuda", api.RESULTADO)
			return
		evento.Skip()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self._temporizador is not None and self._temporizador.IsRunning():
			self._temporizador.Stop()
		if self._tarea is not None:
			self._tarea.cancelar()
		evento.Skip()

	def mostrar(self) -> None:
		self.marco.Show()
		self.marco.Raise()
		self.campo.SetFocus()
