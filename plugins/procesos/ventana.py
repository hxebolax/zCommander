# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana «Procesos» y espera accesible del cierre de un programa (diseño 2.0, 11.9). Con wx.

Todo lo de la interfaz llega por ``zc.ui`` (la API de complementos); este
módulo solo importa wx para construir sus controles. La lista se lee en un hilo
de ``zc.tareas`` cada ``refresco_s`` segundos y se actualiza sin mover al
usuario: la fila enfocada no se repinta mientras está enfocada (algunos
lectores la releen con cada cambio de la CPU) y se pone al día al llegar a ella.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

import wx

from app.plugins import api

from . import sistema

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_procesos")

COLUMNAS = ((_("Nombre"), 200), (_("PID"), 70), (_("Memoria"), 100), (_("CPU"), 70), (_("Usuario"), 180), (_("Ruta"), 360))
#: Teclas que la ventana atiende a mano (para revisar_teclado y la lista de teclas).
TECLAS_PROPIAS = ("Delete", "F5")


def _cpu(valor: float | None) -> str:
	return (f"{valor:.1f} %".replace(".", ",")) if valor is not None else _("Sin datos")


def filas_de(procesos: list[sistema.InfoProceso], cpu: dict[int, float | None], filtro: str = "",
		mostrar_sistema: bool = False) -> list[tuple[sistema.InfoProceso, list[str]]]:
	"""Procesos visibles, ordenados por nombre, con el texto de cada columna (sin wx: se prueba aparte)."""
	filtro = filtro.strip().casefold()
	resultado = []
	for proceso in procesos:
		if proceso.pid == 0:
			continue
		if not mostrar_sistema and proceso.del_sistema:
			continue
		if filtro and filtro not in proceso.nombre.casefold() and filtro not in proceso.ruta.casefold():
			continue
		memoria = api.formato.tamano_legible(proceso.memoria) if proceso.memoria >= 0 else _("Sin datos")
		resultado.append((proceso, [proceso.nombre, str(proceso.pid), memoria, _cpu(cpu.get(proceso.pid)),
			proceso.usuario or _("Sin datos"), proceso.ruta or _("Sin datos")]))
	resultado.sort(key=lambda par: (par[0].nombre.casefold(), par[0].pid))
	return resultado


class PanelProcesos(wx.Panel):
	"""Contenido de la ventana «Procesos»."""

	def __init__(self, padre: wx.Window, zc: api.Anfitrion, *, cargar: bool = True) -> None:
		super().__init__(padre)
		self.zc = zc
		ui = zc.ui
		self._medidor = sistema.MedidorCPU()
		self._procesos: list[sistema.InfoProceso] = []
		self._cpu: dict[int, float | None] = {}
		self._visibles: list[sistema.InfoProceso] = []
		self._textos: list[list[str]] = []
		self._primera = True
		raiz = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.filtro = ui.crear_campo(self, _("&Filtrar por nombre:"), wx.TextCtrl, sizer=raiz,
			ayuda=_("Escriba parte del nombre o de la ruta para ver solo esos procesos."))
		etiqueta_lista = wx.StaticText(self, label=_("&Lista de procesos:"))
		self.lista = ui.ListaAccesible(self, _("Lista de procesos"), COLUMNAS)
		self.lista.SetHelpText(_("Procesos en marcha con su memoria, CPU, usuario y ruta. Supr termina el elegido; "
			"F5 actualiza la lista."))
		raiz.Add(etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		self.casilla_sistema = wx.CheckBox(self, label=_("Mostrar los procesos del &sistema"))
		self.casilla_sistema.SetValue(bool(zc.config.obtener("mostrar_sistema", False)))
		self.casilla_sistema.SetHelpText(_("Incluye los procesos de Windows y de los servicios, que no se pueden terminar desde aquí."))
		raiz.Add(self.casilla_sistema, 0, wx.ALL, 5)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_terminar = wx.Button(self, label=_("&Terminar"))
		self.boton_terminar.SetHelpText(_("Termina el proceso elegido, con confirmación. Lo que no haya guardado se pierde."))
		self.boton_prioridad = wx.Button(self, label=_("Cambiar la &prioridad..."))
		self.boton_prioridad.SetHelpText(_("Cambia la prioridad con la que Windows reparte el procesador a este proceso."))
		self.boton_carpeta = wx.Button(self, label=_("Abrir su &carpeta"))
		self.boton_carpeta.SetHelpText(_("Lleva el panel activo a la carpeta del ejecutable del proceso."))
		self.boton_copiar = wx.Button(self, label=_("C&opiar la información"))
		self.boton_copiar.SetHelpText(_("Copia al portapapeles todos los datos del proceso elegido."))
		self.boton_actualizar = wx.Button(self, label=_("&Actualizar"))
		self.boton_actualizar.SetHelpText(_("Vuelve a leer la lista de procesos (F5)."))
		self.boton_cerrar = wx.Button(self, wx.ID_CLOSE, _("C&errar"))
		for boton in (self.boton_terminar, self.boton_prioridad, self.boton_carpeta, self.boton_copiar, self.boton_actualizar,
				self.boton_cerrar):
			botones.Add(boton, 0, wx.ALL, 5)
		raiz.Add(botones, 0, wx.ALIGN_RIGHT)
		self.SetSizer(raiz)
		self.filtro.Bind(wx.EVT_TEXT, lambda _e: self._pintar())
		self.casilla_sistema.Bind(wx.EVT_CHECKBOX, self._al_casilla)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._al_enfocar)
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
		self.boton_terminar.Bind(wx.EVT_BUTTON, lambda _e: self.terminar())
		self.boton_prioridad.Bind(wx.EVT_BUTTON, lambda _e: self.cambiar_prioridad())
		self.boton_carpeta.Bind(wx.EVT_BUTTON, lambda _e: self.abrir_carpeta())
		self.boton_copiar.Bind(wx.EVT_BUTTON, lambda _e: self.copiar())
		self.boton_actualizar.Bind(wx.EVT_BUTTON, lambda _e: self.actualizar(anunciar=True))
		self.boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.GetTopLevelParent().Close())
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self._temporizador = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.actualizar(), self._temporizador)
		self._habilitar()
		if cargar:
			self.actualizar()
			segundos = max(1, min(60, int(zc.config.obtener("refresco_s", 3))))
			self._temporizador.Start(segundos * 1000)

	def detener(self) -> None:
		self._temporizador.Stop()

	# ── Datos ───────────────────────────────────────────────────────────────

	def actualizar(self, anunciar: bool = False) -> None:
		def leer(_tarea: Any) -> list[sistema.InfoProceso]:
			return sistema.listar()

		def listo(procesos: list[sistema.InfoProceso]) -> None:
			if not self:
				return
			self._procesos = procesos
			self._cpu = self._medidor.medir(procesos)
			self._pintar()
			if anunciar or self._primera:
				self._primera = False
				self.zc.anunciar(_n("{n} proceso", "{n} procesos", len(self._visibles)).format(n=len(self._visibles)), api.DETALLE)

		def fallo(error: BaseException) -> None:
			log.info("No se pudo leer la lista de procesos: %s", error)
			if anunciar:
				self.zc.anunciar(_("No se pudo leer la lista de procesos: {e}").format(e=error), api.ESENCIAL)

		self.zc.tareas.enviar(leer, al_terminar=listo, al_fallar=fallo, clave_unica="zc.procesos:lista", nombre="zc.procesos:lista")

	def _pintar(self) -> None:
		filas = filas_de(self._procesos, self._cpu, self.filtro.GetValue(), self.casilla_sistema.GetValue())
		nuevos = [p for p, _t in filas]
		textos = [t for _p, t in filas]
		enfocada = self.lista.fila_actual()
		pid_enfocado = self._visibles[enfocada].pid if 0 <= enfocada < len(self._visibles) else None
		if [p.pid for p in nuevos] == [p.pid for p in self._visibles]:
			for fila, valores in enumerate(textos):
				if fila != enfocada:
					self.lista.actualizar_fila(fila, valores)
		else:
			self.lista.reemplazar_filas(textos, conservar_foco=False)
			if pid_enfocado is not None:
				destino = next((i for i, p in enumerate(nuevos) if p.pid == pid_enfocado), min(enfocada, len(nuevos) - 1))
				if destino >= 0:
					self.lista.enfocar_fila(destino, anunciar=False)
		self._visibles, self._textos = nuevos, textos
		self._habilitar()

	def elegido(self) -> sistema.InfoProceso | None:
		fila = self.lista.fila_actual()
		return self._visibles[fila] if 0 <= fila < len(self._visibles) else None

	def _habilitar(self) -> None:
		proceso = self.elegido()
		self.boton_terminar.Enable(proceso is not None and not sistema.motivo_para_no_terminar(proceso))
		self.boton_prioridad.Enable(proceso is not None and not proceso.del_sistema)
		self.boton_carpeta.Enable(proceso is not None and bool(proceso.ruta))
		self.boton_copiar.Enable(proceso is not None)

	# ── Eventos ─────────────────────────────────────────────────────────────

	def _al_enfocar(self, evento: wx.ListEvent) -> None:
		fila = evento.GetIndex()
		if 0 <= fila < len(self._textos):
			self.lista.actualizar_fila(fila, self._textos[fila])
		self._habilitar()
		evento.Skip()

	def _al_casilla(self, _evento: wx.CommandEvent) -> None:
		self.zc.config.establecer("mostrar_sistema", self.casilla_sistema.GetValue())
		self._pintar()

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.terminar()
			return
		evento.Skip()

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F5 and not evento.HasAnyModifiers():
			self.actualizar(anunciar=True)
			return
		evento.Skip()

	# ── Acciones ────────────────────────────────────────────────────────────

	def terminar(self) -> None:
		proceso = self.elegido()
		if proceso is None:
			return
		motivo = sistema.motivo_para_no_terminar(proceso)
		if motivo:
			self.zc.anunciar(motivo, api.ESENCIAL)
			return
		pregunta = _("¿Terminar {n} (PID {p})? Lo que no haya guardado en ese programa se perderá.").format(n=proceso.nombre, p=proceso.pid)
		if not self.zc.ui.confirmar(pregunta, _("Terminar el proceso"), self, peligroso=True):
			return
		try:
			sistema.terminar(proceso)
		except api.ErrorArchivos as error:
			self.zc.ui.mostrar_error(error.mensaje, _("Terminar el proceso"), self)
			return
		self.zc.sonidos.sonar("cerrado")
		self.zc.anunciar(_("{n} terminado").format(n=proceso.nombre), api.RESULTADO)
		self.actualizar()

	def cambiar_prioridad(self) -> None:
		proceso = self.elegido()
		if proceso is None or proceso.del_sistema:
			return
		opciones = [_(t) for _c, t in sistema.PRIORIDADES]
		indice = self.zc.ui.elegir_opcion(_("Prioridad de {n} (ahora {a}):").format(n=proceso.nombre,
			a=sistema.texto_prioridad(proceso.prioridad) or _("desconocida")), _("Cambiar la prioridad"), opciones, self)
		if indice is None:
			return
		clase, texto = sistema.PRIORIDADES[indice]
		try:
			sistema.cambiar_prioridad(proceso, clase)
		except api.ErrorArchivos as error:
			self.zc.ui.mostrar_error(error.mensaje, _("Cambiar la prioridad"), self)
			return
		self.zc.anunciar(_("Prioridad de {n}: {p}").format(n=proceso.nombre, p=_(texto)), api.RESULTADO)
		self.actualizar()

	def abrir_carpeta(self) -> None:
		proceso = self.elegido()
		if proceso is None or not proceso.ruta:
			return
		self.zc.abrir_ruta(os.path.dirname(proceso.ruta))
		self.zc.anunciar(_("Panel en la carpeta de {n}").format(n=proceso.nombre), api.RESULTADO)

	def copiar(self) -> None:
		proceso = self.elegido()
		if proceso is None:
			return
		texto = sistema.resumen(proceso, self._cpu.get(proceso.pid))
		if wx.TheClipboard.Open():
			try:
				wx.TheClipboard.SetData(wx.TextDataObject(texto))
			finally:
				wx.TheClipboard.Close()
			self.zc.anunciar(_("Información de {n} copiada").format(n=proceso.nombre), api.RESULTADO)
		else:
			self.zc.anunciar(_("Otro programa está usando el portapapeles. Inténtelo de nuevo."), api.ESENCIAL)


def crear_ventana(zc: api.Anfitrion, *, cargar: bool = True) -> wx.Frame:
	"""Crea (sin mostrar) la ventana «Procesos»."""
	ventana = zc.ui.VentanaComplemento(None, _("Procesos"), zc.id, size=wx.Size(900, 560))
	panel = PanelProcesos(ventana, zc, cargar=cargar)
	ventana.panel = panel
	ventana.Bind(wx.EVT_CLOSE, lambda e: (panel.detener(), e.Skip()))
	panel.lista.SetFocus()
	return ventana


_abierta: list[wx.Frame] = []


def abrir(zc: api.Anfitrion) -> None:
	"""Abre la ventana o la trae al frente si ya está abierta [interfaz]."""
	for ventana in list(_abierta):
		if ventana:
			ventana.Raise()
			ventana.panel.lista.SetFocus()
			return
		_abierta.remove(ventana)
	ventana = crear_ventana(zc)
	_abierta.append(ventana)
	ventana.Show()
	ventana.panel.lista.SetFocus()


# ── Espera del cierre de un programa (acción de error) ───────────────────────


class DialogoEspera(wx.Dialog):
	"""Diálogo sin botones mientras un trabajo largo corre en un hilo; se cierra solo al terminar.

	El texto está en un campo de solo lectura (el lector lo lee al abrirse y se
	puede volver a leer). Escape no hace nada: el Restart Manager no se puede
	interrumpir a medias.
	"""

	def __init__(self, padre: wx.Window | None, titulo: str, texto: str) -> None:
		super().__init__(padre, title=titulo)
		raiz = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label=_("&Estado:"))
		raiz.Add(etiqueta, 0, wx.ALL, 5)
		self.texto = wx.TextCtrl(self, value=texto, style=wx.TE_MULTILINE | wx.TE_READONLY, size=wx.Size(420, 90))
		raiz.Add(self.texto, 1, wx.EXPAND | wx.ALL, 5)
		self.barra = wx.Gauge(self, range=100, name=titulo)
		raiz.Add(self.barra, 0, wx.EXPAND | wx.ALL, 5)
		self.SetSizerAndFit(raiz)
		self.Bind(wx.EVT_CHAR_HOOK, lambda e: None if e.GetKeyCode() == wx.WXK_ESCAPE else e.Skip())
		self.Bind(wx.EVT_CLOSE, lambda e: e.Veto() if e.CanVeto() else e.Skip())
		self._pulso = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.barra.Pulse(), self._pulso)
		self.texto.SetFocus()


def esperar(zc: api.Anfitrion, padre: wx.Window | None, titulo: str, texto: str, trabajo: Callable[[], Any]) -> Any:
	"""Ejecuta ``trabajo`` en un hilo con un diálogo modal de espera [interfaz]; devuelve su resultado o relanza su error."""
	resultado: dict[str, Any] = {}
	dialogo = DialogoEspera(padre, titulo, texto)

	def hilo() -> None:
		try:
			resultado["valor"] = trabajo()
		except BaseException as error:  # noqa: BLE001 - se relanza en el hilo de la interfaz
			resultado["error"] = error
		wx.CallAfter(lambda: dialogo.EndModal(wx.ID_OK) if dialogo and dialogo.IsModal() else None)

	dialogo._pulso.Start(300)
	threading.Thread(target=hilo, name="zc.procesos-espera", daemon=True).start()
	try:
		zc.ui.mostrar_modal(dialogo)
	finally:
		dialogo._pulso.Stop()
		dialogo.Destroy()
	if "error" in resultado:
		raise resultado["error"]
	return resultado.get("valor")
