# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Componentes externos» (diseño 2.0, 6.5): versiones, actualizaciones y restaurar los originales.

Por qué así:

- La lista es una ``ListaAccesible`` con casillas (estado anunciado) y las
  columnas Componente, Instalada, Nueva, Origen, Licencia y Usado por, con su
  etiqueta creada justo antes. Solo se pueden marcar las filas con versión
  nueva: al marcar otra, la casilla se desmarca sola y se dice por qué.
- «Detalles» es un texto de solo lectura (se puede releer con las flechas)
  con las novedades, el tamaño de la descarga, el aviso de cambio grande y el
  estado de la prueba del componente del cursor.
- Todo lo lento (buscar, descargar, probar, sustituir) va fuera del hilo de la
  interfaz: buscar en un hilo; actualizar, volver atrás y restaurar como
  operación del motor (``OperacionComponente``), con su progreso en una barra
  con nombre y anuncios por fase.
- Las preguntas pasan por funciones de este módulo (``_confirmar``) para que
  las pruebas las sustituyan; restaurar y descargar tienen el foco en «No».
"""

from __future__ import annotations

import builtins
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.services.componentes import instalar
from app.services.componentes.instalar import Fila, GestorComponentes, OperacionComponente, Resultado
from app.ui import anuncios
from app.ui.accesibilidad import dialogos, voz
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible

log = logging.getLogger(__name__)

EnHilo = Callable[[Callable[[], Any], Callable[[Any], None], Callable[[BaseException], None]], None]


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _confirmar(padre: wx.Window, mensaje: str, titulo: str) -> bool:
	return dialogos.confirmar(padre, mensaje, titulo, peligroso=True) == wx.ID_YES


def _sonar(evento: str) -> None:
	from app.services.sonidos import servicio

	servicio.sonar(evento)


def _en_hilo_por_defecto(funcion: Callable[[], Any], al_terminar: Callable[[Any], None], al_fallar: Callable[[BaseException], None]) -> None:
	"""Sin la ventana principal (pruebas, uso suelto): un hilo propio y la respuesta con ``wx.CallAfter``."""
	def trabajo() -> None:
		try:
			resultado = funcion()
		except Exception as error:  # noqa: BLE001 - el fallo se entrega a quien lo pidió
			log.exception("Falló una tarea del diálogo de componentes")
			wx.CallAfter(al_fallar, error)
			return
		wx.CallAfter(al_terminar, resultado)

	threading.Thread(target=trabajo, daemon=True, name="componentes").start()


def _lanzar_por_defecto(operacion: OperacionComponente, en_cola: bool = False, al_terminar: Callable | None = None) -> None:
	"""Sin el motor de la ventana: la operación corre en un hilo propio."""
	from app.core.tareas import TokenCancelacion
	from app.services.operaciones.modelo import ContextoEjecucion

	def trabajo() -> None:
		contexto = ContextoEjecucion(TokenCancelacion(), None)
		operacion.contexto = contexto
		try:
			operacion.ejecutar(contexto)
		except Exception:  # noqa: BLE001 - la operación registra y el diálogo se recupera
			log.exception("Falló la operación de componentes")
		if al_terminar is not None:
			wx.CallAfter(al_terminar, operacion)

	threading.Thread(target=trabajo, daemon=True, name="componentes-operacion").start()


class _Progreso:
	"""«Estado:» de solo lectura (con su etiqueta, se puede releer) y barra con nombre; voz en cada fase y en los hitos."""

	HITOS = (25, 50, 75, 100)

	def __init__(self, panel: wx.Window, sizer: wx.Sizer) -> None:
		self.etiqueta = wx.StaticText(panel, label=_("&Estado:"))
		self.estado = wx.TextCtrl(panel, style=wx.TE_READONLY, name=_("Estado"))
		self.estado.SetHelpText(_("Qué se está haciendo ahora y cómo terminó lo último."))
		self.barra = wx.Gauge(panel, range=100, name=_("Progreso de los componentes"))
		self.barra.SetHelpText(_("Progreso de la búsqueda o de la actualización."))
		sizer.Add(self.etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		sizer.Add(self.estado, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
		sizer.Add(self.barra, 0, wx.EXPAND | wx.ALL, 5)
		self._fase = ""
		self._hito = -1

	def fase(self, texto: str, indeterminado: bool = False) -> None:
		self.estado.SetValue(texto)
		if indeterminado:
			self.barra.Pulse()
		if texto != self._fase:
			self._fase, self._hito = texto, -1
			voz.hablar(texto, interrumpir=False)

	def porcentaje(self, valor: int) -> None:
		valor = max(0, min(100, int(valor)))
		self.barra.SetValue(valor)
		hito = max((h for h in self.HITOS if valor >= h), default=None)
		if hito is not None and hito != self._hito:
			self._hito = hito
			voz.hablar(_("{p} por ciento").format(p=hito), interrumpir=False)

	def terminar(self, texto: str, anunciar: bool = True) -> None:
		self.barra.SetValue(100)
		self.estado.SetValue(texto)
		self._fase = texto
		if anunciar:
			voz.hablar(texto, interrumpir=False)


class DialogoComponentes(wx.Dialog):
	"""Componentes de ``data/bin``. Se cierra con «Cerrar» o Escape (también con una tarea en marcha: se cancela)."""

	COLUMNAS = ((_("Componente"), 190), (_("Instalada"), 90), (_("Nueva"), 220), (_("Origen"), 130), (_("Licencia"), 160),
		(_("Usado por"), 120))

	def __init__(self, padre: wx.Window | None, gestor: GestorComponentes, *, en_hilo: EnHilo | None = None,
			lanzar_operacion: Callable[..., None] | None = None, antes_de_renombrar: Callable[[Path], None] | None = None,
			al_abrir_carpeta: Callable[[Path], None] | None = None, al_reiniciar: Callable[[], None] | None = None,
			anuncia_resumen: bool = False) -> None:
		"""
		:param en_hilo: ``en_hilo(funcion, al_terminar, al_fallar)``, el gestor de tareas de la ventana.
		:param lanzar_operacion: ``ventana.lanzar_operacion`` (que ya anuncia el resumen: ``anuncia_resumen`` falso).
		:param antes_de_renombrar: saca los paneles de la carpeta del componente (lo llama el hilo de la operación).
		:param al_abrir_carpeta: lleva el panel activo a la carpeta del componente.
		:param al_reiniciar: reinicia zCommander (para lo que se aplica al reiniciar).
		"""
		titulo = _("Componentes externos")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		self.gestor = gestor
		self._en_hilo = en_hilo or _en_hilo_por_defecto
		self._lanzar = lanzar_operacion or _lanzar_por_defecto
		self._anuncia_resumen = anuncia_resumen or lanzar_operacion is None
		self._antes_de_renombrar = antes_de_renombrar
		self._al_abrir_carpeta = al_abrir_carpeta
		self._al_reiniciar = al_reiniciar
		self._filas: list[Fila] = []
		self._ocupado = False
		self._operacion: OperacionComponente | None = None
		self._cancelar_busqueda = threading.Event()
		self._cerrado = False

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.etiqueta_lista = wx.StaticText(panel, label=_("Co&mponentes:"))
		self.lista = ListaAccesible(panel, _("Componentes"), [(c, panel.FromDIP(a)) for c, a in self.COLUMNAS], con_casillas=True)
		self.lista.SetMinSize(panel.FromDIP(wx.Size(860, 180)))
		self.lista.SetHelpText(_("Componentes de zCommander. Espacio marca los que tienen versión nueva para actualizarlos; "
			"izquierda y derecha leen las columnas."))
		sizer.Add(self.etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		self.etiqueta_detalles = wx.StaticText(panel, label=_("&Detalles:"))
		self.detalles = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, name=_("Detalles"),
			size=panel.FromDIP(wx.Size(860, 140)))
		self.detalles.SetHelpText(_("Novedades del componente elegido, tamaño de la descarga, aviso de cambio grande y estado de su prueba."))
		sizer.Add(self.etiqueta_detalles, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		sizer.Add(self.detalles, 0, wx.EXPAND | wx.ALL, 5)
		self.progreso = _Progreso(panel, sizer)

		self.boton_buscar = wx.Button(panel, label=_("&Buscar versiones nuevas"))
		self.boton_buscar.SetHelpText(_("Pregunta a GitHub y a MSYS2 si hay versiones nuevas. No descarga nada."))
		self.boton_actualizar = wx.Button(panel, label=_("&Actualizar los elegidos"))
		self.boton_actualizar.SetHelpText(_("Descarga, comprueba, prueba e instala los componentes marcados, con copia de lo anterior."))
		self.boton_volver = wx.Button(panel, label=_("&Volver a la versión anterior"))
		self.boton_volver.SetHelpText(_("Vuelve a la versión guardada antes de la última actualización del componente elegido."))
		self.boton_restaurar = wx.Button(panel, label=_("&Restaurar los componentes originales..."))
		self.boton_restaurar.SetHelpText(_("Vuelve a dejar todos los componentes como los trae esta versión de zCommander."))
		self.boton_instalar = wx.Button(panel, label=_("&Instalar"))
		self.boton_instalar.SetHelpText(_("Descarga e instala el componente opcional elegido, que falta."))
		self.boton_omitir = wx.Button(panel, label=_("&Omitir esta versión"))
		self.boton_omitir.SetHelpText(_("No vuelve a ofrecer ni a avisar de la versión nueva del componente elegido."))
		self.boton_carpeta = wx.Button(panel, label=_("Abrir su carpe&ta"))
		self.boton_carpeta.SetHelpText(_("Cierra este diálogo y abre en el panel activo la carpeta del componente elegido."))
		self.boton_reiniciar = wx.Button(panel, label=_("Reiniciar a&hora"))
		self.boton_reiniciar.SetHelpText(_("Cierra zCommander y lo vuelve a abrir para aplicar lo que está pendiente."))
		self.boton_cerrar = wx.Button(panel, wx.ID_CANCEL, _("&Cerrar"))
		self.boton_cerrar.SetHelpText(_("Cierra el diálogo; si hay una búsqueda o una actualización en marcha, la cancela."))
		self.botones_accion = (self.boton_buscar, self.boton_actualizar, self.boton_volver, self.boton_restaurar, self.boton_instalar,
			self.boton_omitir, self.boton_carpeta, self.boton_reiniciar)
		rejilla = wx.WrapSizer(wx.HORIZONTAL)
		for boton in (*self.botones_accion, self.boton_cerrar):
			rejilla.Add(boton, 0, wx.ALL, 4)
		sizer.Add(rejilla, 0, wx.EXPAND | wx.ALL, 4)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)

		self.boton_buscar.Bind(wx.EVT_BUTTON, lambda _e: self.buscar())
		self.boton_actualizar.Bind(wx.EVT_BUTTON, lambda _e: self.actualizar_elegidos())
		self.boton_volver.Bind(wx.EVT_BUTTON, lambda _e: self.volver_anterior())
		self.boton_restaurar.Bind(wx.EVT_BUTTON, lambda _e: self.restaurar_originales())
		self.boton_instalar.Bind(wx.EVT_BUTTON, lambda _e: self.instalar_opcional())
		self.boton_omitir.Bind(wx.EVT_BUTTON, lambda _e: self.omitir())
		self.boton_carpeta.Bind(wx.EVT_BUTTON, lambda _e: self.abrir_carpeta())
		self.boton_reiniciar.Bind(wx.EVT_BUTTON, lambda _e: self.reiniciar())
		self.boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.cerrar())
		self.Bind(wx.EVT_CLOSE, lambda _e: self.cerrar())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._al_cambiar_fila())
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda _e: self._al_cambiar_fila())
		self.lista.Bind(wx.EVT_LIST_ITEM_CHECKED, self._al_marcar)
		self.recargar()
		preparar_dialogo(self, foco_inicial=self.lista)
		self.CentreOnParent()

	# Lista ---------------------------------------------------------------------

	def recargar(self, conservar: str | None = None) -> None:
		"""Vuelve a leer los componentes y deja el cursor en ``conservar`` (o en la fila en la que estaba)."""
		actual = conservar or (self.fila().id if self.fila() else None)
		marcadas = {self._filas[i].id for i in self.lista.filas_marcadas() if i < len(self._filas)}
		try:
			self._filas = self.gestor.filas()
		except Exception:  # noqa: BLE001 - un archivo ilegible no impide abrir el diálogo
			log.exception("No se pudieron leer los componentes")
			self._filas = []
		self.lista.reemplazar_filas([[f.nombre, f.instalada, f.nueva, f.origen, f.licencia, f.usado_por] for f in self._filas])
		for indice, fila in enumerate(self._filas):
			if fila.id in marcadas and fila.elegible:
				self.lista.CheckItem(indice, True)
		if self._filas:
			indice = next((i for i, f in enumerate(self._filas) if f.id == actual), 0)
			self.lista.enfocar_fila(indice, anunciar=False)
		self._al_cambiar_fila()

	def fila(self) -> Fila | None:
		indice = self.lista.fila_actual()
		return self._filas[indice] if 0 <= indice < len(self._filas) else None

	def _al_marcar(self, evento: wx.ListEvent) -> None:
		indice = evento.GetIndex()
		fila = self._filas[indice] if 0 <= indice < len(self._filas) else None
		if fila is not None and not fila.elegible:
			wx.CallAfter(self._desmarcar, indice, fila)
		evento.Skip()

	def _desmarcar(self, indice: int, fila: Fila) -> None:
		if not self or indice >= self.lista.numero_filas():
			return
		self.lista.CheckItem(indice, False)
		if fila.pendiente:
			motivo = _("{c} ya tiene una actualización pendiente de reiniciar").format(c=fila.nombre)
		elif fila.omitida:
			motivo = _("Ha omitido la versión nueva de {c}").format(c=fila.nombre)
		else:
			motivo = _("{c} no tiene versión nueva que elegir").format(c=fila.nombre)
		voz.hablar(motivo, canal=voz.NAVEGACION)

	def _al_cambiar_fila(self) -> None:
		fila = self.fila()
		self.detalles.SetValue(self.gestor.detalles(fila) if fila else _("No hay componentes."))
		self._actualizar_botones()

	def _actualizar_botones(self) -> None:
		fila = self.fila()
		libre = not self._ocupado
		self.boton_buscar.Enable(libre)
		self.boton_actualizar.Enable(libre and any(f.elegible for f in self._filas))
		self.boton_volver.Enable(libre and bool(fila and fila.puede_volver and fila.actualizable))
		self.boton_restaurar.Enable(libre)
		self.boton_instalar.Enable(libre and bool(fila and fila.falta_opcional))
		self.boton_omitir.Enable(libre and bool(fila and fila.nueva_version is not None and not fila.omitida))
		self.boton_carpeta.Enable(libre and bool(fila) and (self.gestor.entorno.bin / self._carpeta(fila)).is_dir())
		self.boton_reiniciar.Enable(self._al_reiniciar is not None and any(f.pendiente for f in self._filas))

	def _carpeta(self, fila: Fila) -> str:
		from app.services.componentes import estado

		ficha = estado.ficha_instalada(fila.id, self.gestor.entorno) or estado.ficha_base(fila.id, self.gestor.entorno) or {}
		return str(ficha.get("carpeta") or fila.id)

	def _ocupar(self, ocupado: bool) -> None:
		self._ocupado = ocupado
		self._actualizar_botones()

	# Buscar -----------------------------------------------------------------------

	def buscar(self) -> None:
		if self._ocupado:
			return
		self._ocupar(True)
		self._cancelar_busqueda.clear()
		self.progreso.fase(_("Buscando versiones nuevas..."), indeterminado=True)
		self._en_hilo(lambda: self.gestor.comprobar(self._cancelar_busqueda), self._al_buscar, self._al_fallar)

	def _al_buscar(self, nuevas: dict) -> None:
		if self._cerrado or not self:
			return
		self._ocupar(False)
		self.recargar()
		sin_omitir = self.gestor.novedades_sin_omitir()
		if sin_omitir:
			texto = _("Hay versiones nuevas de {n} componentes").format(n=len(sin_omitir)) if len(sin_omitir) != 1 else \
				_("Hay una versión nueva de {c}").format(c=next((f.nombre for f in self._filas if f.id == sin_omitir[0]), sin_omitir[0]))
			_sonar("comp.disponible")
		else:
			texto = _("Todos los componentes están al día")
		if self.gestor.errores:
			texto += ". " + _("No se pudo comprobar: {l}").format(l=", ".join(sorted(self.gestor.errores)))
		self.progreso.terminar(texto)

	def _al_fallar(self, error: BaseException) -> None:
		if self._cerrado or not self:
			return
		self._ocupar(False)
		self.progreso.terminar(_("No se pudo terminar: {e}").format(e=getattr(error, "mensaje", error)))

	# Operaciones -------------------------------------------------------------------

	def _lanzar_acciones(self, titulo: str, acciones: list[tuple[str, Callable[[instalar.Instalador], Resultado]]]) -> None:
		if not acciones or self._ocupado:
			return
		self._ocupar(True)

		ultimo = [-1]

		def fabrica(**opciones: Any) -> instalar.Instalador:
			del_motor = opciones.pop("al_progresar", None)

			def avance(hecho: int, total: int) -> None:
				if del_motor is not None:
					del_motor(hecho, total)
				porcentaje = hecho * 100 // total if total > 0 else -1
				if porcentaje >= 0 and porcentaje // 5 != ultimo[0]:
					ultimo[0] = porcentaje // 5  # a la interfaz solo cada 5 %: la barra no satura el bucle de eventos
					wx.CallAfter(self._porcentaje, porcentaje)

			return self.gestor.instalador(antes_de_renombrar=self._antes_de_renombrar, al_progresar=avance, **opciones)

		def fase(_id: str, texto: str) -> None:
			wx.CallAfter(self._fase, texto)

		def resultado(r: Resultado) -> None:
			wx.CallAfter(self._resultado, r)

		operacion = OperacionComponente(titulo, acciones, fabrica, al_resultado=resultado, al_fase=fase)
		self._operacion = operacion
		self.progreso.fase(titulo, indeterminado=True)
		self._lanzar(operacion, False, self._al_terminar_operacion)

	def _fase(self, texto: str) -> None:
		if not self._cerrado and self:
			self.progreso.fase(texto, indeterminado=True)

	def _porcentaje(self, valor: int) -> None:
		if not self._cerrado and self:
			self.progreso.porcentaje(valor)

	def _resultado(self, resultado: Resultado) -> None:
		if self._cerrado or not self:
			return
		if resultado.sonido:
			_sonar(resultado.sonido)
		self.gestor.pruebas[resultado.id] = resultado.mensaje
		self.progreso.estado.SetValue(resultado.mensaje)

	def _al_terminar_operacion(self, operacion: OperacionComponente) -> None:
		self._operacion = None
		if self._cerrado or not self:
			return
		self._ocupar(False)
		self.recargar()
		texto = operacion.resumen()
		self.progreso.terminar(texto, anunciar=self._anuncia_resumen)
		if any(r.estado == instalar.PENDIENTE for r in operacion.resultados) and self._al_reiniciar is not None:
			self.boton_reiniciar.SetFocus()

	def actualizar_elegidos(self) -> None:
		elegidas = [self._filas[i] for i in self.lista.filas_marcadas() if i < len(self._filas) and self._filas[i].elegible]
		if not elegidas:
			fila = self.fila()
			elegidas = [fila] if fila is not None and fila.elegible else []
		if not elegidas:
			anuncios.anunciar(_("Marque con Espacio los componentes que quiera actualizar"), anuncios.RESULTADO)
			return
		acciones = [(f.id, lambda inst, n=f.nueva_version: inst.actualizar(n)) for f in elegidas]
		nombres = ", ".join(f.nombre for f in elegidas)
		self._lanzar_acciones(_("Actualizar {l}").format(l=nombres), acciones)

	def volver_anterior(self) -> None:
		fila = self.fila()
		if fila is None or not fila.puede_volver:
			return
		self._lanzar_acciones(_("Volver a la versión anterior de {c}").format(c=fila.nombre), [(fila.id, lambda inst, i=fila.id: inst.volver_anterior(i))])

	def restaurar_originales(self) -> None:
		cambios = self.gestor.cambios_restaurar()
		if not cambios:
			anuncios.anunciar(_("Todos los componentes ya tienen la versión original"), anuncios.RESULTADO)
			return
		lineas = "\n".join(_("{c}: de {a} a {b}").format(c=nombre, a=instalada, b=original) for _id, nombre, instalada, original in cambios)
		if not _confirmar(self, _("Se restaurarán los componentes originales de esta versión de zCommander:\n\n{l}\n\n¿Continuar?").format(l=lineas),
				_("Restaurar los componentes originales")):
			self.lista.SetFocus()
			return
		instalador = self.gestor.instalador()
		descargar = [nombre for id, nombre, _a, _b in cambios if instalador.necesita_descarga(id)]
		permiso = True
		if descargar:
			permiso = _confirmar(self, _("No está la copia de la versión original de {l}. ¿Descargarla de su origen?").format(l=", ".join(descargar)),
				_("Descargar los originales"))
		acciones = [(id, lambda inst, i=id: inst.restaurar_original(i, descargar=permiso)) for id, _n, _a, _b in cambios]
		self._lanzar_acciones(_("Restaurar los componentes originales"), acciones)

	def instalar_opcional(self) -> None:
		fila = self.fila()
		if fila is None or not fila.falta_opcional:
			return
		if not _confirmar(self, _("{c} no está instalado. ¿Descargarlo de su origen e instalarlo?").format(c=fila.nombre), _("Instalar componente")):
			return
		self._lanzar_acciones(_("Instalar {c}").format(c=fila.nombre), [(fila.id, lambda inst, i=fila.id: inst.instalar_desde_base(i))])

	def omitir(self) -> None:
		fila = self.fila()
		if fila is None or not self.gestor.omitir(fila.id):
			return
		self.recargar(fila.id)
		anuncios.anunciar(_("Versión omitida: no se volverá a avisar de ella"), anuncios.RESULTADO)

	def abrir_carpeta(self) -> None:
		fila = self.fila()
		if fila is None or self._al_abrir_carpeta is None:
			return
		carpeta = self.gestor.entorno.bin / self._carpeta(fila)
		self.cerrar()
		self._al_abrir_carpeta(carpeta)

	def reiniciar(self) -> None:
		if self._al_reiniciar is None:
			return
		self.cerrar()
		self._al_reiniciar()

	# Cierre ------------------------------------------------------------------------

	def cerrar(self) -> None:
		if self._cerrado:
			return
		self._cerrado = True
		self._cancelar_busqueda.set()
		if self._operacion is not None:
			self._operacion.cancelar()
		if self.IsModal():
			self.EndModal(wx.ID_CANCEL)
		else:
			self.Destroy()
