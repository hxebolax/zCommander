# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Interfaz accesible del actualizador de zCommander (diseño 2.0, 5.4).

Parte de la plantilla del agente «actualizador». Lo propio de zCommander:

- Anuncios con ``app/ui/anuncios.py`` y sonidos ``act.*`` del catálogo (4.2).
- La comprobación manual es la orden ``buscar_actualizaciones`` del catálogo
  (Ayuda, «Buscar ac&tualizaciones...», ``app/ui/acciones/actualizar_ac.py``),
  no ``anadir_menu_ayuda`` de la plantilla.
- :class:`ComprobadorPeriodico` hace la pasada compartida: la aplicación y las
  comprobaciones que CO y PL registran con ``actualizador.registrar_comprobacion``.
  El diálogo de una versión nueva no se abre solo mientras la ventana no esté
  libre (``esta_libre``: ni diálogo, ni menú, ni operación esperando decisión).
- Antes de cerrar para instalar se aplican las reglas de salida (1.x §8.5): con
  operaciones en curso se pregunta «Esperar y actualizar», «Cancelar las
  operaciones y actualizar» o «No actualizar ahora».
- :func:`atender_arranque`: lo que dice ``actualizador.al_arrancar`` (versión
  instalada, vuelta atrás, «salud sin confirmar» con «Volver a la versión
  anterior» o «Seguir con esta versión»).

La red y el disco van SIEMPRE en hilos; los controles solo se tocan desde el hilo
principal (``wx.CallAfter``).
"""

from __future__ import annotations

import builtins
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import wx

from app.services import actualizador
from app.ui import anuncios

log = logging.getLogger(__name__)

Anunciar = Callable[[str], None]

TITULO_BUSCAR = "Buscar actualizaciones"


def _(texto: str) -> str:
	"""Traduce con el ``_`` de gettext si está instalado en ``builtins``."""
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _anunciar_resultado(texto: str) -> None:
	anuncios.anunciar(texto, anuncios.RESULTADO)


def _sonar(evento: str) -> None:
	"""Sonido del catálogo; el actualizador nunca falla por un sonido."""
	try:
		from app.services.sonidos import servicio

		servicio.sonar(evento)
	except Exception:  # noqa: BLE001 - sin sonidos se sigue igual
		log.debug("No se pudo pedir el sonido %s", evento, exc_info=True)


def _decir(anunciar: Anunciar | None, texto: str) -> None:
	if anunciar is None:
		return
	try:
		anunciar(texto)
	except Exception:  # noqa: BLE001 - la voz es opcional: un fallo nunca rompe la interfaz
		log.debug("No se pudo anunciar por voz: %s", texto, exc_info=True)


def mostrar_mensaje(padre: wx.Window | None, mensaje: str, titulo: str, icono: int = wx.ICON_INFORMATION) -> None:
	"""Mensaje modal accesible con «&Aceptar» en español (nunca ``wx.MessageBox``)."""
	from app.ui.accesibilidad import dialogos

	if icono == wx.ICON_ERROR:
		dialogos.mostrar_error(padre, mensaje, titulo)
	else:
		dialogos.mostrar_mensaje(padre, mensaje, titulo, icono=icono)


_NOMBRES_FASE = {
	"descarga": "Descargando",
	"verificacion": "Verificando el paquete",
	"extraccion": "Descomprimiendo",
	"preparacion": "Preparando la instalación",
}
# Porcentajes de la descarga que se anuncian por voz (hitos, no cada cambio).
_HITOS_VOZ = (25, 50, 75, 100)


def _cerrar_aplicacion() -> None:
	"""Cierre normal de la ventana principal (se guardan la sesión y las preferencias).

	``salir()`` y no ``Close()`` a secas: con «minimizar a la bandeja», ``Close()``
	solo la ocultaría y el script de sustitución se cansaría de esperar.
	"""
	aplicacion = wx.GetApp()
	ventana = aplicacion.GetTopWindow() if aplicacion else None
	if not ventana:
		return
	salir = getattr(ventana, "salir", None)
	if callable(salir):
		salir()
	else:
		ventana.Close(force=True)


def _ventana_principal(padre: wx.Window | None) -> Any:
	"""La ventana con ``operaciones`` (la principal), subiendo por los padres."""
	ventana = padre
	while ventana is not None:
		if hasattr(ventana, "operaciones"):
			return ventana
		ventana = ventana.GetParent() if isinstance(ventana, wx.Window) else None
	aplicacion = wx.GetApp()
	arriba = aplicacion.GetTopWindow() if aplicacion else None
	return arriba if hasattr(arriba, "operaciones") else None


def reglas_de_salida(padre: wx.Window | None) -> bool:
	"""Reglas de salida de la 1.x (§8.5) antes de cerrar para instalar. Falso: no actualizar ahora."""
	ventana = _ventana_principal(padre)
	operaciones = getattr(ventana, "operaciones", None)
	if operaciones is None or not operaciones.en_marcha():
		return True
	from app.ui.accesibilidad import dialogos

	eleccion = dialogos.elegir_opcion(
		padre, _("Hay {n} operaciones en curso. zCommander tiene que cerrarse para instalar la actualización.").format(
			n=len(operaciones.en_marcha())),
		_("Actualizar"), [_("&Esperar y actualizar"), _("Cancelar las operaciones y a&ctualizar"), _("&No actualizar ahora")],
	)
	if eleccion not in (0, 1):
		return False
	if eleccion == 1:
		operaciones.cancelar_todas()
	if operaciones.en_marcha():
		with wx.BusyInfo(_("Esperando a que terminen las operaciones...")):
			while operaciones.en_marcha():
				wx.SafeYield(None, True)
				time.sleep(0.05)
	return True


class DialogoActualizacion(wx.Dialog):
	"""Ofrece la versión nueva y, si la persona acepta, la descarga y la instala."""

	RESULTADO_ACTUALIZAR = "actualizar"
	RESULTADO_MAS_TARDE = "mas_tarde"
	RESULTADO_OMITIR = "omitir"

	def __init__(
		self,
		padre: wx.Window | None,
		config: actualizador.Configuracion,
		info: actualizador.InfoActualizacion,
		anunciar: Anunciar | None = None,
		al_cerrar_app: Callable[[], None] | None = None,
		*,
		foco_en_novedades: bool = False,
	) -> None:
		super().__init__(padre, title=_("Actualización disponible"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			name=_("Actualización disponible"))
		self.config = config
		self.info = info
		self.resultado = self.RESULTADO_MAS_TARDE
		self._anunciar = anunciar if anunciar is not None else _anunciar_resultado
		self._al_cerrar_app = al_cerrar_app or _cerrar_aplicacion
		self._foco_en_novedades = foco_en_novedades
		self._cancelar = threading.Event()
		self._hilo: threading.Thread | None = None
		self._bat_preparado = None
		self._fase = ""
		self._ultimo_hito = -1
		self._ultimo_hito_voz = 0
		self._crear_controles()
		from app.ui.accesibilidad import dialogos

		dialogos.preparar_dialogo(self, id_escape=wx.ID_CANCEL)
		# Escape se atiende aquí (después de enlazar el de preparar_dialogo, así va
		# primero): durante la descarga cancela en lugar de cerrar el diálogo.
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()
		wx.CallAfter(self._enfocar_inicial)

	# ── Construcción ─────────────────────────────────────────────────────────

	def _crear_controles(self) -> None:
		info, config = self.info, self.config
		principal = wx.BoxSizer(wx.VERTICAL)
		fecha = _(", publicada el %s") % info.fecha if info.fecha else ""
		self.resumen = wx.StaticText(
			self,
			label=_("Hay una versión nueva de %(app)s.\nVersión instalada: %(actual)s.\nVersión nueva: %(nueva)s%(fecha)s.")
			% {"app": config.nombre_app, "actual": config.version_actual, "nueva": info.version, "fecha": fecha},
		)
		principal.Add(self.resumen, 0, wx.ALL | wx.EXPAND, 10)

		# La etiqueta va justo antes del cuadro: así el lector la usa como nombre.
		principal.Add(wx.StaticText(self, label=_("&Novedades:")), 0, wx.LEFT | wx.RIGHT, 10)
		self.novedades = wx.TextCtrl(
			self,
			value=info.novedades or _("El servidor no ha publicado novedades para esta versión."),
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
			size=(520, 220),
			name=_("Novedades"),
		)
		self.novedades.SetHelpText(_("Cambios de la versión nueva. Recórralos con las flechas; es de solo lectura."))
		principal.Add(self.novedades, 1, wx.ALL | wx.EXPAND, 10)

		self.etiqueta_estado = wx.StaticText(self, label=_("&Estado:"))
		self.estado = wx.TextCtrl(self, style=wx.TE_READONLY, name=_("Estado"))
		self.estado.SetHelpText(_("Lo que está haciendo la actualización, o por qué no se pudo hacer."))
		self.barra = wx.Gauge(self, range=100, name=_("Progreso de la actualización"))
		principal.Add(self.etiqueta_estado, 0, wx.LEFT | wx.RIGHT, 10)
		principal.Add(self.estado, 0, wx.ALL | wx.EXPAND, 10)
		principal.Add(self.barra, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_actualizar = wx.Button(self, label=_("&Actualizar ahora"))
		self.boton_actualizar.SetHelpText(_("Descarga la versión nueva, la comprueba y la instala. zCommander se cierra y "
			"vuelve a abrirse solo; sus datos no se tocan."))
		self.boton_omitir = wx.Button(self, label=_("Omitir esta &versión"))
		self.boton_omitir.SetHelpText(_("No vuelve a avisar de esta versión. Ayuda, Buscar actualizaciones la sigue mostrando."))
		self.boton_mas_tarde = wx.Button(self, wx.ID_CANCEL, label=_("&Más tarde"))
		self.boton_mas_tarde.SetHelpText(_("Cierra sin actualizar; mientras descarga, cancela la descarga (se continúa después)."))
		for boton in (self.boton_actualizar, self.boton_omitir, self.boton_mas_tarde):
			botones.Add(boton, 0, wx.ALL, 5)
		principal.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(principal)

		self.boton_actualizar.SetDefault()
		self.boton_actualizar.Bind(wx.EVT_BUTTON, self._al_actualizar)
		self.boton_omitir.Bind(wx.EVT_BUTTON, self._al_omitir)
		self.boton_mas_tarde.Bind(wx.EVT_BUTTON, self._al_mas_tarde)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)

		self._mostrar_progreso(False)
		if not actualizador.puede_instalar(config):
			self.boton_actualizar.Disable()
			self._mostrar_progreso(True, barra=False)
			self.estado.SetValue(_("Esta copia se ejecuta desde el código fuente: no se sustituye automáticamente. "
				"Actualícela con su sistema de control de versiones."))

	def _mostrar_progreso(self, visible: bool, barra: bool = True) -> None:
		self.etiqueta_estado.Show(visible)
		self.estado.Show(visible)
		self.barra.Show(visible and barra)
		self.Layout()

	def _enfocar_inicial(self) -> None:
		"""Comprobación periódica: foco en «Novedades» (5.4); manual: en «Actualizar ahora»."""
		if not self:
			return
		from app.ui.accesibilidad import dialogos

		if self._foco_en_novedades or not self.boton_actualizar.IsEnabled():
			dialogos.enfocar(self.novedades)
		else:
			self.boton_actualizar.SetFocus()

	def _terminar(self, resultado: str, codigo: int) -> None:
		self.resultado = resultado
		if self.IsModal():
			self.EndModal(codigo)
		else:
			self.SetReturnCode(codigo)
			self.Hide()

	# ── Botones y teclas ─────────────────────────────────────────────────────

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_ESCAPE and evento.GetModifiers() == wx.MOD_NONE:
			self._al_mas_tarde(None)
			return
		evento.Skip()

	def _al_mas_tarde(self, _evento: wx.CommandEvent | None) -> None:
		if self._trabajando():
			self._cancelar.set()
			self._poner_estado(_("Cancelando la descarga..."))
			return
		if self._bat_preparado is not None:
			actualizador.descartar_preparada(self.config)
			self._bat_preparado = None
		self._terminar(self.RESULTADO_MAS_TARDE, wx.ID_CANCEL)

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self._trabajando() and evento.CanVeto():
			self._cancelar.set()
			evento.Veto()
			return
		self._al_mas_tarde(None)

	def _al_omitir(self, _evento: wx.CommandEvent | None) -> None:
		actualizador.omitir_version(self.config, self.info.version)
		if self._bat_preparado is not None:
			actualizador.descartar_preparada(self.config)
			self._bat_preparado = None
		self._terminar(self.RESULTADO_OMITIR, wx.ID_CANCEL)

	def _al_actualizar(self, _evento: wx.CommandEvent | None) -> None:
		if self._trabajando():
			return
		if self._bat_preparado is not None:
			self._instalar(self._bat_preparado)
			return
		self._cancelar.clear()
		self._fase = ""
		self._ultimo_hito = -1
		self._ultimo_hito_voz = 0
		self.boton_actualizar.Disable()
		self.boton_omitir.Disable()
		self.boton_mas_tarde.SetLabel(_("&Cancelar"))
		self._mostrar_progreso(True)
		self.barra.SetValue(0)
		self._poner_estado(_("Iniciando la descarga..."), voz=True)
		self.boton_mas_tarde.SetFocus()  # el único botón útil mientras se descarga
		self._hilo = threading.Thread(target=self._trabajo, name="actualizador", daemon=True)
		self._hilo.start()

	def _trabajando(self) -> bool:
		return self._hilo is not None and self._hilo.is_alive()

	# ── Hilo de trabajo (nunca toca controles directamente) ─────────────────

	def _trabajo(self) -> None:
		try:
			ruta_bat = actualizador.descargar_y_preparar(
				self.config, self.info, progreso=self._progreso_desde_hilo, cancelado=self._cancelar.is_set
			)
		except actualizador.ErrorCancelado as error:
			log.info("Descarga de la actualización cancelada por la persona")
			wx.CallAfter(self._al_fallar, str(error), cancelado=True)
		except actualizador.ErrorActualizacion as error:
			log.warning("No se pudo preparar la actualización: %s", error)
			wx.CallAfter(self._al_fallar, str(error))
		except Exception:  # noqa: BLE001 - cualquier fallo se registra y se ofrece reintentar
			log.exception("Fallo inesperado al preparar la actualización")
			wx.CallAfter(self._al_fallar,
				_("Se produjo un error inesperado al preparar la actualización. Los detalles están en el registro."))
		else:
			wx.CallAfter(self._al_preparada, ruta_bat)

	def _progreso_desde_hilo(self, fase: str, hecho: int, total: int) -> None:
		wx.CallAfter(self.actualizar_progreso, fase, hecho, total)

	# ── Hilo principal ───────────────────────────────────────────────────────

	def _poner_estado(self, texto: str, voz: bool = False) -> None:
		self.estado.SetValue(texto)
		if voz:
			_decir(self._anunciar, texto)

	def actualizar_progreso(self, fase: str, hecho: int, total: int) -> None:
		"""Refleja el avance: barra siempre; texto y voz solo en hitos y cambios de fase."""
		if not self:
			return
		porcentaje = min(100, int(hecho * 100 / total)) if total else 0
		self.barra.SetValue(porcentaje)
		nombre = _(_NOMBRES_FASE.get(fase, fase))
		if fase != self._fase:
			self._fase = fase
			self._ultimo_hito = -1
			self._ultimo_hito_voz = 0
			self._poner_estado(_("%s...") % nombre, voz=fase != "descarga")
		if fase == "descarga":
			# El texto cambia cada 10 %; la voz solo en los hitos (25, 50, 75, 100).
			decena = porcentaje // 10 * 10
			hito_voz = max((hito for hito in _HITOS_VOZ if porcentaje >= hito), default=0)
			decir = hito_voz > self._ultimo_hito_voz
			if decena > self._ultimo_hito or decir:
				self._ultimo_hito = decena
				if decir:
					self._ultimo_hito_voz = hito_voz
				mostrado = hito_voz if decir else decena
				texto = _("Descargando: %(p)d %% (%(h).1f de %(t).1f MB)") % {
					"p": mostrado, "h": hecho / (1024 * 1024), "t": total / (1024 * 1024)}
				self._poner_estado(texto, voz=decir)

	def _al_fallar(self, mensaje: str, cancelado: bool = False) -> None:
		if not self:
			return
		self.boton_actualizar.SetLabel(_("&Reintentar"))
		self.boton_actualizar.Enable()
		self.boton_omitir.Enable()
		self.boton_mas_tarde.SetLabel(_("&Más tarde"))
		self._mostrar_progreso(True)
		self.barra.SetValue(0)
		if cancelado:
			self._poner_estado(mensaje, voz=True)
		else:
			self.estado.SetValue(mensaje)
			if self._anunciar is _anunciar_resultado:
				anuncios.anunciar(mensaje, anuncios.ESENCIAL)  # un error se dice siempre
			else:
				_decir(self._anunciar, mensaje)
			self.boton_actualizar.SetDefault()
		# El foco va al estado para que el lector lea el error y se pueda releer.
		self.estado.SetFocus()

	def _al_preparada(self, ruta_bat) -> None:
		if not self:
			return
		self.barra.SetValue(100)
		_sonar("act.descargada")
		self._bat_preparado = ruta_bat
		self._instalar(ruta_bat)

	def _instalar(self, ruta_bat) -> None:
		"""Reglas de salida, lanzar el script y cerrar zCommander para que sustituya el programa."""
		if not reglas_de_salida(self):
			self.boton_actualizar.SetLabel(_("&Actualizar ahora"))
			self.boton_actualizar.Enable()
			self.boton_omitir.Enable()
			self.boton_mas_tarde.SetLabel(_("&Más tarde"))
			self._poner_estado(_("La actualización está preparada. Pulse Actualizar ahora cuando quiera instalarla; "
				"Más tarde la descarta."), voz=True)
			self.boton_actualizar.SetFocus()
			return
		self._poner_estado(
			_("Actualización lista. zCommander se cerrará y volverá a abrirse solo en unos segundos."), voz=True)
		try:
			actualizador.lanzar_sustitucion(ruta_bat)
		except OSError:
			log.exception("No se pudo lanzar el script de sustitución")
			self._bat_preparado = None
			self._al_fallar(_("No se pudo iniciar la instalación de la actualización. Los detalles están en el registro."))
			return
		self._bat_preparado = None
		self._terminar(self.RESULTADO_ACTUALIZAR, wx.ID_OK)
		# Un momento de margen para que el lector de pantalla diga el aviso.
		wx.CallLater(1500, self._al_cerrar_app)


_dialogo_abierto = threading.Event()


def dialogo_abierto() -> bool:
	return _dialogo_abierto.is_set()


def mostrar_dialogo(
	padre: wx.Window | None,
	config: actualizador.Configuracion,
	info: actualizador.InfoActualizacion,
	anunciar: Anunciar | None = None,
	*,
	foco_en_novedades: bool = False,
) -> str:
	"""Muestra el diálogo de forma modal y devuelve su resultado."""
	_dialogo_abierto.set()
	dialogo = DialogoActualizacion(padre, config, info, anunciar=anunciar, foco_en_novedades=foco_en_novedades)
	foco_previo = wx.Window.FindFocus()
	_sonar("dialogo.abrir")
	try:
		dialogo.ShowModal()
		return dialogo.resultado
	finally:
		_sonar("dialogo.cerrar")
		dialogo.Destroy()
		_dialogo_abierto.clear()
		if foco_previo:
			try:
				foco_previo.SetFocus()
			except RuntimeError:
				log.debug("El control que tenía el foco ya no existe", exc_info=True)


# ════════════════════════════════════════════════════════════════════════════
# Comprobación manual (orden buscar_actualizaciones) y periódica
# ════════════════════════════════════════════════════════════════════════════

_comprobacion_en_curso = threading.Lock()


def comprobar_manualmente(padre: wx.Window | None, config: actualizador.Configuracion, anunciar: Anunciar | None = None) -> bool:
	"""Busca actualizaciones en un hilo y SIEMPRE informa del resultado. Falso si ya había una en curso.

	La manual no respeta la versión omitida: si la persona pregunta, se le dice.
	"""
	anunciar = anunciar if anunciar is not None else _anunciar_resultado
	if dialogo_abierto():
		_decir(anunciar, _("El diálogo de actualización ya está abierto."))
		return False
	if not _comprobacion_en_curso.acquire(blocking=False):
		_decir(anunciar, _("Ya se están buscando actualizaciones."))
		return False
	_decir(anunciar, _("Buscando actualizaciones..."))

	def trabajo() -> None:
		try:
			info = actualizador.comprobar(config, respetar_omitida=False)
		except actualizador.ErrorActualizacion as error:
			wx.CallAfter(informar_manual, padre, config, None, str(error), anunciar)
		except Exception:  # noqa: BLE001 - cualquier fallo se registra y se dice
			log.exception("Fallo inesperado al buscar actualizaciones")
			wx.CallAfter(informar_manual, padre, config, None, _("Error inesperado al buscar actualizaciones."), anunciar)
		else:
			wx.CallAfter(informar_manual, padre, config, info, None, anunciar)
		finally:
			_comprobacion_en_curso.release()

	threading.Thread(target=trabajo, name="buscar-actualizaciones", daemon=True).start()
	return True


def informar_manual(padre, config, info, error, anunciar=None) -> None:
	"""Resultado de la comprobación manual: error, «al día» (sonido y anuncio) o el diálogo."""
	if padre is not None and not padre:
		return
	if error:
		mostrar_mensaje(padre, error, _(TITULO_BUSCAR), wx.ICON_WARNING)
	elif info is None:
		_sonar("act.al_dia")
		_decir(anunciar if anunciar is not None else _anunciar_resultado,
			_("Sin novedades: zCommander está al día (versión %s).") % config.version_actual)
	else:
		mostrar_dialogo(padre, config, info, anunciar)


def _texto_config(config_app: Any, clave: str, defecto: Any) -> Any:
	try:
		return config_app.obtener(clave)
	except Exception:  # noqa: BLE001 - sin la clave se usa el valor por defecto
		log.debug("No se pudo leer %s", clave, exc_info=True)
		return defecto


class ComprobadorPeriodico:
	"""Pasada periódica compartida (5.4): la primera a los 60 s y después cada ``actualizaciones.intervalo_horas``.

	La fecha de la última pasada se guarda en ``data/config``: reiniciar no
	provoca otra consulta. Comprueba si toca cada hora. La pasada va en un hilo
	del gestor de tareas de la ventana (se cancela al cerrar). Los fallos de red
	solo se registran: no se molesta a la persona por no tener conexión.
	"""

	def __init__(self, ventana: Any, config: actualizador.Configuracion, config_app: Any, *,
			retraso_inicial: float = 60.0, cada_s: float = 3600.0) -> None:
		self.ventana = ventana
		self.config = config
		self.config_app = config_app
		self.retraso_inicial = retraso_inicial
		self.cada_s = cada_s
		self._detenido = False
		self._en_curso = False
		self._tarea = None
		self._pendiente: actualizador.InfoActualizacion | None = None

	def iniciar(self) -> None:
		self._programar(self.retraso_inicial)

	def detener(self) -> None:
		self._detenido = True
		self._pendiente = None
		if self._tarea is not None:
			try:
				self._tarea.cancelar(_("zCommander se cierra"))
			except Exception:  # noqa: BLE001 - al cerrar, una tarea que no se deja cancelar no importa
				log.debug("No se pudo cancelar la pasada periódica", exc_info=True)

	def _programar(self, segundos: float) -> None:
		if self._detenido:
			return
		try:
			self.ventana.llamar_mas_tarde(int(segundos * 1000), self._tic)
		except RuntimeError:
			log.debug("La ventana ya no existe: se detiene la comprobación periódica", exc_info=True)
			self._detenido = True

	def _viva(self) -> bool:
		"""Una ventana wx destruida es «falsa»: entonces la comprobación se detiene sola."""
		try:
			return bool(self.ventana)
		except RuntimeError:
			return False

	def _tic(self) -> None:
		if self._detenido:
			return
		if not self._viva():
			self.detener()
			return
		try:
			self.comprobar_si_toca()
		except Exception:  # noqa: BLE001 - la comprobación periódica nunca rompe la ventana
			log.exception("Falló la comprobación periódica")
		self._programar(self.cada_s)

	def intervalo_horas(self) -> float:
		try:
			return max(1.0, float(_texto_config(self.config_app, "actualizaciones.intervalo_horas", 24)))
		except (TypeError, ValueError):
			return 24.0

	def app_activa(self) -> bool:
		return bool(_texto_config(self.config_app, "actualizaciones.comprobar", True))

	def toca(self) -> bool:
		return actualizador.toca_pasada(self.config, self.intervalo_horas())

	def comprobar_si_toca(self) -> bool:
		"""Lanza la pasada si toca. Devuelve si la lanzó."""
		if self._detenido or self._en_curso or not self.toca():
			return False
		comprobar_app = self.app_activa()
		if not comprobar_app and not actualizador.comprobaciones():
			return False
		tareas = getattr(self.ventana, "tareas", None)
		if tareas is None:
			return False
		config = self.config

		def trabajo(tarea) -> actualizador.ResultadoPasada:
			return actualizador.pasada(config, tarea.token, comprobar_app=comprobar_app)

		self._en_curso = True
		self._tarea = tareas.enviar(trabajo, al_terminar=self._al_terminar, al_fallar=self._al_fallar,
			clave_unica="actualizador.pasada", nombre="Comprobación periódica de actualizaciones")
		if self._tarea is None:
			self._en_curso = False
			return False
		return True

	def _al_fallar(self, error: BaseException) -> None:
		self._en_curso = False
		self._tarea = None
		log.info("La pasada periódica no terminó: %s", error)

	def _al_terminar(self, resultado: actualizador.ResultadoPasada) -> None:
		self._en_curso = False
		self._tarea = None
		if self._detenido or resultado is None:
			return
		for novedad in resultado.novedades:
			self.ventana.anunciar(novedad.texto, anuncios.ESENCIAL if novedad.esencial else anuncios.NORMAL)
		if resultado.info is not None:
			self.avisar_version(resultado.info)

	def avisar_version(self, info: actualizador.InfoActualizacion) -> None:
		self.ventana.anunciar(
			_("Hay una versión nueva de zCommander: {v}. Se abrirá su diálogo; también está en Ayuda, Buscar actualizaciones.").format(
				v=info.version), anuncios.ESENCIAL, sonido="act.disponible")
		self._pendiente = info
		self._abrir_cuando_libre()

	def _abrir_cuando_libre(self) -> None:
		"""El diálogo no se abre solo encima de un diálogo, un menú o una decisión pendiente (5.4)."""
		if self._detenido or self._pendiente is None or not self._viva():
			return
		if dialogo_abierto() or not self.ventana.esta_libre():
			self.ventana.llamar_mas_tarde(2000, self._abrir_cuando_libre)
			return
		info, self._pendiente = self._pendiente, None
		mostrar_dialogo(self.ventana.padre(), self.config, info, foco_en_novedades=True)


# ════════════════════════════════════════════════════════════════════════════
# Arranque: lo que dice actualizador.al_arrancar (paso 10 de 14.8)
# ════════════════════════════════════════════════════════════════════════════


def atender_arranque(ventana: Any, config: actualizador.Configuracion, resultado: actualizador.ResultadoArranque) -> None:
	"""Anuncios y sonidos de 5.4 y la pregunta de «salud sin confirmar» de 5.2.

	La llama ``actualizador.al_arrancar`` desde el hilo de la interfaz; lo que
	necesita un diálogo espera a que la ventana esté libre.
	"""
	if resultado.instalada:
		ventana.anunciar(_("zCommander se ha actualizado a la versión {v}.").format(v=resultado.instalada),
			anuncios.RESULTADO, sonido="act.instalada")
	if resultado.mensaje:
		ventana.anunciar(resultado.mensaje, anuncios.ESENCIAL, sonido="act.revertida" if resultado.revertida else "")
	if resultado.sin_confirmar is not None:
		ventana.llamar_mas_tarde(300, lambda: _preguntar_sin_confirmar(ventana, config, resultado.sin_confirmar))


def _preguntar_sin_confirmar(ventana: Any, config: actualizador.Configuracion, pendiente: actualizador.SinConfirmar) -> None:
	if not ventana:
		return
	if not ventana.esta_libre():
		ventana.llamar_mas_tarde(2000, lambda: _preguntar_sin_confirmar(ventana, config, pendiente))
		return
	from app.ui.accesibilidad import dialogos

	eleccion = dialogos.elegir_opcion(
		ventana.padre(),
		_("La última vez que se abrió, la versión {v} de zCommander no llegó a confirmar que arrancaba bien. "
			"Puede volver a la versión anterior ({a}) o seguir con esta.").format(v=pendiente.version, a=pendiente.anterior),
		_("Actualización sin confirmar"),
		[_("&Volver a la versión anterior"), _("&Seguir con esta versión")],
	)
	if eleccion == 1:
		actualizador.seguir_con_esta_version(config)
		ventana.anunciar(_("Se sigue con la versión {v}.").format(v=pendiente.version), anuncios.RESULTADO)
	elif eleccion == 0:
		volver_a_la_anterior(ventana, config)
	# Cancelar: se vuelve a preguntar en el próximo arranque.


def volver_a_la_anterior(ventana: Any, config: actualizador.Configuracion, al_cerrar_app: Callable[[], None] | None = None) -> bool:
	"""Lanza el ``.bat`` de vuelta atrás y cierra zCommander. Falso si no se pudo."""
	try:
		ruta = actualizador.preparar_vuelta_atras(config)
		actualizador.lanzar_sustitucion(ruta)
	except (actualizador.ErrorActualizacion, OSError) as error:
		log.exception("No se pudo preparar la vuelta a la versión anterior")
		mostrar_mensaje(ventana.padre(), str(error) if isinstance(error, actualizador.ErrorActualizacion) else
			_("No se pudo iniciar la vuelta a la versión anterior. Los detalles están en el registro."),
			_("Actualización sin confirmar"), wx.ICON_ERROR)
		return False
	ventana.anunciar(_("zCommander se cerrará y volverá a abrirse con la versión anterior."), anuncios.ESENCIAL)
	cerrar = al_cerrar_app or getattr(ventana, "salir", None) or _cerrar_aplicacion
	ventana.llamar_mas_tarde(1500, cerrar)
	return True
