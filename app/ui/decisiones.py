# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cola única de decisiones: la interfaz responde a las preguntas de las operaciones.

``GestorDecisiones`` implementa el protocolo ``Decisor`` del motor de
operaciones (sección 9.6 del diseño). Por qué funciona así:

- Los métodos se llaman desde el hilo de una operación y lo BLOQUEAN hasta que
  la persona responde. La pregunta se muestra con un diálogo modal en el hilo
  de la interfaz (``wx.CallAfter``) y la respuesta vuelve con un
  ``threading.Event``. Llamarlos desde el hilo de la interfaz lo congelaría
  (el diálogo nunca llegaría a mostrarse), así que ahí lanzan ``RuntimeError``.
- Hay UNA sola cola: nunca se abren dos preguntas a la vez, para que el lector
  de pantalla no salte de un diálogo a otro sin que la persona sepa de dónde
  viene cada uno.
- Una pregunta solo se muestra enseguida si nace de una orden recién pedida
  (la operación se marcó hace menos de 3 s y es la última marcada) y la
  persona sigue en la ventana principal sin ningún diálogo modal abierto:
  típicamente la lista de conflictos tras F5. Si no, robarle el foco a quien
  está haciendo otra cosa la desorientaría: la pregunta queda pendiente, se
  anuncia como aviso esencial, se recuerda cada 60 s y se atiende desde la
  ventana de operaciones (``atender_pendiente``) o al volver a la ventana
  principal (``revisar``, que la ventana llama en ``EVT_ACTIVATE``).
- Cada espera se corta sola si la operación se cancela (se mira su token cada
  0,2 s) o si se llama a ``cancelar_todas`` al salir: el hilo recibe
  «cancelar» y nunca se queda colgado.
- Todos los diálogos de decisión ignoran las teclas durante sus primeros
  300 ms: una pulsación dirigida al panel (Intro, una letra) que llega justo
  cuando aparece el diálogo no debe pulsar un botón sin que la persona lo vea.
"""

from __future__ import annotations

import builtins
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import wx

from app.services.operaciones.modelo import (
	AccionConflicto,
	AccionError,
	Conflicto,
	Operacion,
	PreguntaError,
	RespuestaConflicto,
)
from app.ui import anuncios

log = logging.getLogger(__name__)

#: Una operación es «reciente» durante estos segundos tras marcarla.
SEGUNDOS_RECIENTE = 3.0
#: Cada cuánto se recuerdan las decisiones pendientes.
SEGUNDOS_RECORDATORIO = 60
#: Teclas ignoradas al abrir un diálogo de decisión.
MILISEGUNDOS_SIN_TECLAS = 300
#: Cada cuánto mira el hilo que espera si su operación se canceló.
_INTERVALO_ESPERA = 0.2


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Teclas ignoradas al abrir ───────────────────────────────────────────────

class BloqueoTeclas:
	"""Consume las pulsaciones de un diálogo durante sus primeros milisegundos.

	Se engancha a ``EVT_CHAR_HOOK``, que wx entrega antes que nadie (antes que
	el botón predeterminado, las letras de acceso o la lista), y vuelve a
	empezar a contar cuando el diálogo se muestra (``EVT_SHOW``): el diálogo
	puede construirse un rato antes de aparecer.
	"""

	def __init__(self, dialogo: wx.Window, milisegundos: int = MILISEGUNDOS_SIN_TECLAS) -> None:
		self.segundos = milisegundos / 1000
		self.hasta = time.monotonic() + self.segundos
		# Se enlaza DESPUÉS de los manejadores del propio diálogo (preparar_dialogo):
		# wx llama primero al último enlazado, así que este consume antes que ellos.
		dialogo.Bind(wx.EVT_CHAR_HOOK, self.al_pulsar)
		dialogo.Bind(wx.EVT_SHOW, self.al_mostrar)

	def activo(self) -> bool:
		return time.monotonic() < self.hasta

	def al_mostrar(self, evento: wx.ShowEvent) -> None:
		if evento.IsShown():
			self.hasta = time.monotonic() + self.segundos
		evento.Skip()

	def al_pulsar(self, evento: wx.KeyEvent) -> None:
		if self.activo():
			log.debug("Tecla %s ignorada: el diálogo de decisión acaba de abrirse", evento.GetKeyCode())
			return
		evento.Skip()


def ignorar_teclas_iniciales(dialogo: wx.Window, milisegundos: int = MILISEGUNDOS_SIN_TECLAS) -> BloqueoTeclas:
	"""Aplica ``BloqueoTeclas`` a ``dialogo`` (llámela cuando el diálogo ya esté construido)."""
	bloqueo = BloqueoTeclas(dialogo, milisegundos)
	dialogo._bloqueo_teclas = bloqueo  # se guarda con el diálogo para que no lo recoja el recolector
	return bloqueo


# ── Peticiones ──────────────────────────────────────────────────────────────

@dataclass(eq=False)
class _Peticion:
	"""Una pregunta que espera respuesta.

	:param crear: construye el diálogo (en el hilo de la interfaz) a partir del padre.
	:param interpretar: convierte (diálogo, código de ``ShowModal``) en la respuesta.
	:param cancelar: lo que se devuelve si se cancela la operación o se sale.
	"""

	descripcion: str
	operacion: Operacion | None
	crear: Callable[[wx.Window | None], wx.Dialog]
	interpretar: Callable[[wx.Dialog, int], Any]
	cancelar: Any
	evento: threading.Event = field(default_factory=threading.Event)
	resultado: Any = None
	resuelta: bool = False
	inmediata: bool = False
	anunciada: bool = False
	dialogo: wx.Dialog | None = None


class _Recordatorio(wx.Timer):
	"""Temporizador que recuerda las decisiones pendientes (sin ventana dueña)."""

	def __init__(self, funcion: Callable[[], None]) -> None:
		super().__init__()
		self._funcion = funcion

	def Notify(self) -> None:  # noqa: N802 - nombre de la API de wx
		try:
			self._funcion()
		except Exception:  # noqa: BLE001 - un fallo del recordatorio no debe tumbar el bucle de eventos
			log.exception("Falló el recordatorio de decisiones pendientes")


class GestorDecisiones:
	"""Implementa ``Decisor`` con una cola única de diálogos en el hilo de la interfaz.

	Créelo en el hilo de la interfaz (usa un ``wx.Timer``).

	:param ventana_principal: la ventana de los paneles; las preguntas inmediatas
		solo se muestran si es la ventana activa. También es el padre de los diálogos.
	"""

	def __init__(self, ventana_principal: wx.Window | None = None) -> None:
		self.ventana_principal = ventana_principal
		self._candado = threading.RLock()
		#: Todas las peticiones cuyo hilo está esperando (también las que aún no llegaron a la cola).
		self._esperas: list[_Peticion] = []
		#: Las que esperan turno en la interfaz, en orden de llegada.
		self._cola: list[_Peticion] = []
		self._mostrando: _Peticion | None = None
		self._ultima: Operacion | None = None
		self._momento_ultima = 0.0
		self._cerrado = False
		self._recordatorio = _Recordatorio(self._recordar)

	# ── Lo que llama la ventana ─────────────────────────────────────────────

	def marcar_reciente(self, operacion: Operacion) -> None:
		"""La ventana la llama al lanzar una operación por una orden de la persona."""
		with self._candado:
			self._ultima = operacion
			self._momento_ultima = time.monotonic()

	def es_reciente(self, operacion: Operacion | None) -> bool:
		"""Menos de 3 s desde que se marcó y es la última marcada.

		Sin operación, la pregunta no viene de una operación en segundo plano sino
		de lo que la persona hace ahora mismo (entrar en un servidor con Ctrl+G o
		al restaurar la sesión: contraseña, huella): se muestra enseguida, porque
		nada la explicaría si esperase en F12. Las operaciones siempre pasan
		``operacion``.
		"""
		if operacion is None:
			return True
		with self._candado:
			if self._ultima is None or time.monotonic() - self._momento_ultima >= SEGUNDOS_RECIENTE:
				return False
			return operacion is None or operacion is self._ultima

	def pendientes(self) -> list[str]:
		"""Descripciones de las decisiones que esperan turno (no la que se está mostrando)."""
		with self._candado:
			return [p.descripcion for p in self._cola if not p.resuelta]

	def hay_pendientes(self) -> bool:
		return bool(self.pendientes())

	def atender_pendiente(self, padre: wx.Window | None = None) -> bool:
		"""Muestra la primera decisión pendiente. ``False`` si no hay ninguna o ya hay una abierta.

		:param padre: ventana sobre la que se abre (por defecto, la principal).
		"""
		self._exigir_interfaz()
		with self._candado:
			if self._mostrando is not None:
				return False
			peticion = next((p for p in self._cola if not p.resuelta), None)
		if peticion is None:
			return False
		self._atender(peticion, padre)
		return True

	def revisar(self) -> None:
		"""La ventana principal la llama al activarse: atiende lo pendiente si no hay diálogos.

		Se difiere con ``wx.CallAfter`` porque ``EVT_ACTIVATE`` llega mientras se
		cierra el diálogo anterior, que aún figura como modal.
		"""
		wx.CallAfter(self._revisar_ahora)

	def cancelar_todas(self) -> None:
		"""Responde «cancelar» a todas las esperas, también a las futuras (al salir)."""
		with self._candado:
			self._cerrado = True
			esperas = list(self._esperas)
		for peticion in esperas:
			self._resolver(peticion, peticion.cancelar)
		if wx.IsMainThread():
			self._limpiar_interfaz()
		else:
			self._llamar_en_interfaz(self._limpiar_interfaz)

	# ── Protocolo Decisor ───────────────────────────────────────────────────

	# 2.0 (14.6): respuestas automáticas de las tareas programadas, sin mostrar nada.

	@staticmethod
	def _automaticas(operacion: Operacion | None):
		if operacion is None:
			return None
		propias = getattr(operacion, "respuestas_automaticas", None)
		return propias if propias is not None else getattr(_raiz(operacion), "respuestas_automaticas", None)

	@staticmethod
	def _apuntar(automaticas, operacion: Operacion, texto: str) -> None:
		registro = automaticas.registro or log
		registro.info("%s: %s", _raiz(operacion).descripcion(), texto)

	@staticmethod
	def _respuesta_automatica(automaticas) -> RespuestaConflicto:
		politica = str(automaticas.conflicto)
		try:
			accion = AccionConflicto(politica)
		except ValueError:
			accion = AccionConflicto.OMITIR  # «preguntar» no tiene sentido sin nadie a quien preguntar
		return RespuestaConflicto(accion)

	def resolver_conflictos(self, operacion: Operacion, conflictos: Sequence[Conflicto]) -> list[RespuestaConflicto] | None:
		automaticas = self._automaticas(operacion)
		if automaticas is not None:
			respuesta = self._respuesta_automatica(automaticas)
			self._apuntar(automaticas, operacion, f"{len(conflictos)} conflictos resueltos con «{respuesta.accion}»")
			return [respuesta for _c in conflictos]
		lista = list(conflictos)
		origen, destino = getattr(operacion, "origen", None), getattr(operacion, "destino", None)

		def crear(padre):
			from app.ui.dialogos.conflictos import DialogoConflictos

			return DialogoConflictos(padre, lista, origen, destino, titulo=_raiz(operacion).descripcion())

		def interpretar(dialogo, codigo):
			return dialogo.resultado() if codigo == wx.ID_OK else None

		raiz = _raiz(operacion)
		return self._esperar(raiz, raiz.descripcion(), crear, interpretar, None)

	def preguntar_conflicto(self, operacion: Operacion, conflicto: Conflicto) -> RespuestaConflicto:
		automaticas = self._automaticas(operacion)
		if automaticas is not None:
			respuesta = self._respuesta_automatica(automaticas)
			self._apuntar(automaticas, operacion, f"conflicto resuelto con «{respuesta.accion}»")
			return respuesta
		origen, destino = getattr(operacion, "origen", None), getattr(operacion, "destino", None)
		cancelar = RespuestaConflicto(AccionConflicto.CANCELAR)

		def crear(padre):
			from app.ui.dialogos.conflictos import DialogoConflicto

			return DialogoConflicto(padre, conflicto, origen, destino, titulo=_raiz(operacion).descripcion())

		def interpretar(dialogo, _codigo):
			return dialogo.respuesta()

		raiz = _raiz(operacion)
		return self._esperar(raiz, raiz.descripcion(), crear, interpretar, cancelar)

	def preguntar_error(self, operacion: Operacion, pregunta: PreguntaError) -> AccionError:
		automaticas = self._automaticas(operacion)
		if automaticas is not None:
			self._apuntar(automaticas, operacion, f"error en {pregunta.ruta} ({pregunta.mensaje}): «{automaticas.error}»")
			return automaticas.error
		acciones = [AccionError.REINTENTAR, AccionError.OMITIR, AccionError.OMITIR_TODOS, AccionError.CANCELAR]
		etiquetas = [_("&Reintentar"), _("&Omitir"), _("Omitir &todos"), _("&Cancelar")]
		texto = pregunta.mensaje
		if pregunta.ruta:
			texto += "\n" + _("Elemento: {ruta}").format(ruta=pregunta.ruta)
		if pregunta.operacion:
			texto += "\n" + _("Operación: {o}").format(o=pregunta.operacion)
		titulo = _("Error: {o}").format(o=_raiz(operacion).descripcion())

		def crear(padre):
			# 2.0 (14.6): acciones extra de los complementos, tras «Reintentar», según el manifiesto
			# (sin activar el complemento) y, si ya está activo, su aplica().
			extra = _acciones_extra(pregunta)
			dialogo = _dialogo_opciones(padre, titulo, texto, [etiquetas[0], *(a.etiqueta for a in extra), *etiquetas[1:]], 0)
			dialogo.acciones_extra = extra
			for indice, accion in enumerate(extra, start=1):
				boton = dialogo.FindWindow(dialogo.ids_opciones[indice])
				boton.Bind(wx.EVT_BUTTON, lambda _e, a=accion: _pulsar_accion_extra(dialogo, a, pregunta))
			return dialogo

		def interpretar(dialogo, codigo):
			if getattr(dialogo, "resultado_extra", None) is not None:
				return dialogo.resultado_extra
			ids = [i for n, i in enumerate(dialogo.ids_opciones) if not 1 <= n <= len(dialogo.acciones_extra)]
			return acciones[ids.index(codigo)] if codigo in ids else AccionError.CANCELAR

		raiz = _raiz(operacion)
		return self._esperar(raiz, raiz.descripcion(), crear, interpretar, AccionError.CANCELAR)

	def elegir(self, titulo: str, texto: str, opciones: Sequence[str], predeterminada: int = 0, escape: int = -1,
			operacion: Operacion | None = None) -> int:
		"""Ver ``Decisor.elegir``. ``operacion`` es opcional (el protocolo no la pasa)."""
		etiquetas = list(opciones)

		def crear(padre):
			return _dialogo_opciones(padre, titulo, texto, etiquetas, predeterminada)

		def interpretar(dialogo, codigo):
			ids = dialogo.ids_opciones
			return ids.index(codigo) if codigo in ids else escape

		raiz = _raiz(operacion) if operacion is not None else None
		descripcion = raiz.descripcion() if raiz is not None else titulo
		return self._esperar(raiz, descripcion, crear, interpretar, escape)

	def pedir_texto(self, titulo: str, texto: str, valor: str = "", oculto: bool = False,
			operacion: Operacion | None = None) -> str | None:
		"""Ver ``Decisor.pedir_texto``. ``operacion`` es opcional (el protocolo no la pasa)."""

		def crear(padre):
			from app.ui.accesibilidad.dialogos import DialogoTexto

			return DialogoTexto(padre, texto, titulo, valor, contrasena=oculto)

		def interpretar(dialogo, codigo):
			return dialogo.GetValue() if codigo == wx.ID_OK else None

		raiz = _raiz(operacion) if operacion is not None else None
		descripcion = raiz.descripcion() if raiz is not None else titulo
		return self._esperar(raiz, descripcion, crear, interpretar, None)

	def elegir_con_casilla(self, titulo: str, texto: str, opciones: Sequence[str], casilla: str, predeterminada: int = 0,
			escape: int = -1, operacion: Operacion | None = None) -> tuple[int, bool]:
		"""Como ``elegir``, con la casilla «No volver a preguntar» (10.12): (índice, casilla marcada)."""
		etiquetas = list(opciones)

		def crear(padre):
			from app.ui.accesibilidad.dialogos import DialogoMensaje

			dialogo = DialogoMensaje(padre, texto, titulo, opciones=etiquetas, icono=wx.ICON_QUESTION, casilla=casilla)
			return dialogo

		def interpretar(dialogo, codigo):
			ids = dialogo.ids_opciones
			if codigo not in ids:
				return escape, False
			return ids.index(codigo), bool(dialogo.casilla is not None and dialogo.casilla.GetValue())

		raiz = _raiz(operacion) if operacion is not None else None
		descripcion = raiz.descripcion() if raiz is not None else titulo
		return self._esperar(raiz, descripcion, crear, interpretar, (escape, False))

	def pedir_credenciales(self, titulo: str, texto: str, usuario: str = "",
			operacion: Operacion | None = None) -> tuple[str, str, bool] | None:
		"""Usuario, contraseña y «recordar» (9.4) con el diálogo de ``rd_credenciales`` (bloque RD)."""

		def crear(padre):
			from app.ui.dialogos import rd_credenciales

			return rd_credenciales.DialogoCredenciales(padre, titulo, texto, usuario)

		def interpretar(dialogo, codigo):
			return dialogo.valores() if codigo == wx.ID_OK else None

		raiz = _raiz(operacion) if operacion is not None else None
		descripcion = raiz.descripcion() if raiz is not None else titulo
		return self._esperar(raiz, descripcion, crear, interpretar, None)

	# ── Espera en el hilo de la operación ───────────────────────────────────

	@staticmethod
	def _exigir_interfaz() -> None:
		if not wx.IsMainThread():
			raise RuntimeError("Este método del gestor de decisiones solo se llama desde el hilo de la interfaz")

	def _esperar(self, operacion: Operacion | None, descripcion: str, crear, interpretar, cancelar) -> Any:
		if threading.current_thread() is threading.main_thread():
			# El diálogo se muestra en este mismo hilo: esperarlo aquí lo congelaría para siempre.
			raise RuntimeError("Las decisiones se piden desde el hilo de una operación, nunca desde el de la interfaz")
		peticion = _Peticion(descripcion, operacion, crear, interpretar, cancelar)
		with self._candado:
			if self._cerrado:
				return cancelar
			self._esperas.append(peticion)
		try:
			if not self._llamar_en_interfaz(self._encolar, peticion):
				return cancelar
			while not peticion.evento.wait(_INTERVALO_ESPERA):
				if self._operacion_cancelada(operacion) and self._resolver(peticion, cancelar):
					log.info("Decisión retirada: se canceló la operación %s", descripcion)
					self._llamar_en_interfaz(self._retirar, peticion)
			return peticion.resultado
		finally:
			with self._candado:
				if peticion in self._esperas:
					self._esperas.remove(peticion)

	@staticmethod
	def _operacion_cancelada(operacion: Operacion | None) -> bool:
		contexto = getattr(operacion, "contexto", None)
		token = getattr(contexto, "token", None)
		return token is not None and token.is_set()

	def _resolver(self, peticion: _Peticion, valor: Any) -> bool:
		"""Da la respuesta una sola vez (puede llegar del diálogo, de la cancelación o de la salida)."""
		with self._candado:
			if peticion.resuelta:
				return False
			peticion.resuelta = True
			peticion.resultado = valor
		peticion.evento.set()
		return True

	def _llamar_en_interfaz(self, funcion, *args) -> bool:
		try:
			wx.CallAfter(funcion, *args)
			return True
		except Exception:  # noqa: BLE001 - sin wx.App (cerrando) no hay a quién preguntar
			log.warning("No se pudo pasar la decisión a la interfaz; se cancela", exc_info=True)
			for peticion in args:
				if isinstance(peticion, _Peticion):
					self._resolver(peticion, peticion.cancelar)
			return False

	# ── Cola en el hilo de la interfaz ──────────────────────────────────────

	def _hay_modal_abierto(self) -> bool:
		for ventana in wx.GetTopLevelWindows():
			try:
				if isinstance(ventana, wx.Dialog) and ventana.IsShown() and ventana.IsModal():
					return True
			except RuntimeError:
				log.debug("Ventana ya destruida al buscar diálogos modales", exc_info=True)
		return False

	def _principal_activa(self) -> bool:
		"""La ventana principal es la activa y no hay ningún diálogo modal abierto."""
		principal = self.ventana_principal
		if principal is None:
			return False
		activa = wx.GetActiveWindow()
		if activa is None:
			return False
		superior = wx.GetTopLevelParent(activa)
		if activa is not principal and superior is not principal:
			return False
		return not self._hay_modal_abierto()

	def _encolar(self, peticion: _Peticion) -> None:
		if peticion.resuelta:
			return
		peticion.inmediata = self.es_reciente(peticion.operacion) and self._principal_activa()
		with self._candado:
			self._cola.append(peticion)
			libre = self._mostrando is None
		if peticion.inmediata and libre:
			self._atender(peticion)
		else:
			self._anunciar_pendiente(peticion)

	def _anunciar_pendiente(self, peticion: _Peticion) -> None:
		if not peticion.anunciada:
			peticion.anunciada = True
			anuncios.anunciar(_("{d}: espera su decisión").format(d=peticion.descripcion), anuncios.ESENCIAL)
		if not self._recordatorio.IsRunning():
			self._recordatorio.Start(SEGUNDOS_RECORDATORIO * 1000)

	def _recordar(self) -> None:
		pendientes = self.pendientes()
		if not pendientes:
			self._recordatorio.Stop()
			return
		if len(pendientes) == 1:
			texto = _("{d}: espera su decisión").format(d=pendientes[0])
		else:
			texto = _("{n} decisiones pendientes. La primera: {d}").format(n=len(pendientes), d=pendientes[0])
		anuncios.anunciar(texto, anuncios.ESENCIAL)

	def _revisar_ahora(self) -> None:
		with self._candado:
			ocupado = self._mostrando is not None or self._cerrado
		if not ocupado and self.hay_pendientes() and self._principal_activa():
			self.atender_pendiente()

	def _atender(self, peticion: _Peticion, padre: wx.Window | None = None) -> None:
		"""Muestra el diálogo de ``peticion`` (modal) y entrega la respuesta al hilo que espera."""
		with self._candado:
			if peticion in self._cola:
				self._cola.remove(peticion)
			if peticion.resuelta:
				return
			self._mostrando = peticion
		resultado = peticion.cancelar
		dialogo = None
		foco_previo = wx.Window.FindFocus()
		try:
			dialogo = peticion.crear(padre or self.ventana_principal)
			ignorar_teclas_iniciales(dialogo)
			peticion.dialogo = dialogo
			if peticion.resuelta:  # se canceló mientras se construía
				return
			codigo = dialogo.ShowModal()
			resultado = peticion.interpretar(dialogo, codigo)
		except Exception:  # noqa: BLE001 - el hilo de la operación no puede quedarse esperando
			log.exception("Falló el diálogo de decisión de %s; se responde cancelar", peticion.descripcion)
			resultado = peticion.cancelar
		finally:
			peticion.dialogo = None
			self._resolver(peticion, resultado)
			with self._candado:
				self._mostrando = None
			if dialogo is not None:
				dialogo.Destroy()
			if foco_previo:
				try:
					foco_previo.SetFocus()
				except RuntimeError:
					log.debug("El control que tenía el foco ya no existe", exc_info=True)
			wx.CallAfter(self._continuar)

	def _continuar(self) -> None:
		"""Tras cerrar un diálogo: la siguiente inmediata se muestra; el resto queda pendiente."""
		with self._candado:
			if self._mostrando is not None or self._cerrado:
				return
			cola = [p for p in self._cola if not p.resuelta]
		if not cola:
			self._recordatorio.Stop()
			return
		siguiente = cola[0]
		if siguiente.inmediata and self._principal_activa():
			self._atender(siguiente)
		else:
			self._anunciar_pendiente(siguiente)

	def _retirar(self, peticion: _Peticion) -> None:
		"""Quita una petición ya resuelta (operación cancelada) de la cola o cierra su diálogo."""
		with self._candado:
			if peticion in self._cola:
				self._cola.remove(peticion)
			vacia = not any(not p.resuelta for p in self._cola)
		dialogo = peticion.dialogo
		if dialogo is not None:
			try:
				if dialogo.IsModal():
					dialogo.EndModal(wx.ID_CANCEL)
			except RuntimeError:
				log.debug("El diálogo de la decisión ya estaba destruido", exc_info=True)
		if vacia and self._mostrando is None:
			self._recordatorio.Stop()

	def _limpiar_interfaz(self) -> None:
		with self._candado:
			cola, self._cola = self._cola, []
			mostrando = self._mostrando
		for peticion in cola:
			self._resolver(peticion, peticion.cancelar)
		if mostrando is not None:
			self._retirar(mostrando)
		self._recordatorio.Stop()


def _raiz(operacion: Operacion) -> Operacion:
	"""La operación de nivel superior: una suboperación pregunta en nombre de su padre.

	La marca de «reciente» y la descripción que se anuncia son las de la
	operación que la persona lanzó (sincronizar), no las de la copia interna.
	"""
	raiz = getattr(operacion, "raiz", None)
	try:
		return raiz() if callable(raiz) else operacion
	except Exception:  # noqa: BLE001 - una operación de prueba sin padre no debe impedir preguntar
		log.debug("No se pudo obtener la operación raíz", exc_info=True)
		return operacion


def _acciones_extra(pregunta: PreguntaError) -> list:
	"""Acciones de error de los complementos que aplican (nunca activa ninguno, 3.4)."""
	try:
		from app.plugins import registro

		return list(registro.acciones_error_aplicables(pregunta))
	except Exception:  # noqa: BLE001 - un complemento roto no impide preguntar
		log.exception("No se pudieron obtener las acciones de error de los complementos")
		return []


_RESULTADOS_EXTRA = (AccionError.REINTENTAR, AccionError.OMITIR, AccionError.CANCELAR)


def _pulsar_accion_extra(dialogo: wx.Dialog, accion, pregunta: PreguntaError) -> None:
	"""Botón de una acción de complemento: la activa si hace falta («Cargando el complemento...»).

	Mientras se carga, los botones quedan inhabilitados; el bucle del diálogo modal sigue
	atendiendo la activación. Un resultado REINTENTAR, OMITIR o CANCELAR cierra el diálogo
	con él; ``None`` vuelve a mostrar la misma pregunta.
	"""
	from app.plugins import cargador
	from app.ui import anuncios

	botones = [dialogo.FindWindow(i) for i in dialogo.ids_opciones]

	def habilitar(valor: bool) -> None:
		for boton in botones:
			if boton:
				boton.Enable(valor)

	def llamar() -> None:
		if not dialogo:
			return
		resultado = accion.funcion(pregunta)
		if resultado in _RESULTADOS_EXTRA:
			dialogo.resultado_extra = resultado
			dialogo.EndModal(wx.ID_OK)
			return
		habilitar(True)

	if accion.activo:
		llamar()
		return
	habilitar(False)
	anuncios.anunciar(_("Cargando el complemento..."), anuncios.RESULTADO, sonido="plugin.cargando")
	futuro = cargador.asegurar_activo(accion.complemento)

	def resuelto(_f) -> None:
		def continuar() -> None:
			if not dialogo:
				return
			try:
				ok = bool(futuro.result())
			except Exception:  # noqa: BLE001 - cancelado al cerrar
				ok = False
			if ok:
				llamar()
			else:
				anuncios.anunciar(_("No se pudo cargar el complemento"), anuncios.ESENCIAL)
				habilitar(True)

		cargador.planificar(continuar)

	futuro.add_done_callback(resuelto)


def _dialogo_opciones(padre: wx.Window | None, titulo: str, texto: str, etiquetas: Sequence[str], predeterminada: int) -> wx.Dialog:
	"""``DialogoMensaje`` con botones que dicen la acción y el predeterminado elegido.

	El texto va en un campo de solo lectura si es largo o de varias líneas (lo
	decide ``DialogoMensaje``); si no, el foco empieza en el botón predeterminado.
	"""
	from app.ui.accesibilidad.dialogos import DialogoMensaje

	dialogo = DialogoMensaje(padre, texto, titulo, opciones=etiquetas, icono=wx.ICON_QUESTION)
	if 0 <= predeterminada < len(dialogo.ids_opciones):
		boton = dialogo.FindWindow(dialogo.ids_opciones[predeterminada])
		if isinstance(boton, wx.Button):
			boton.SetDefault()
			if not isinstance(dialogo.cuerpo, wx.TextCtrl):
				def al_iniciar(evento, boton=boton):
					wx.CallAfter(boton.SetFocus)
					evento.Skip()

				dialogo.Bind(wx.EVT_INIT_DIALOG, al_iniciar)
	return dialogo
