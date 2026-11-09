# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lógica del reproductor: cola, pistas, saltos, volumen, velocidad, posiciones y temporizador. Sin wx.

Todo lo de la interfaz llega inyectado (anunciar, sonar, planificar, el motor),
así se prueba con un ``MediaCtrl`` falso. Los métodos públicos se llaman en el
hilo de la interfaz y vuelven enseguida: abrir un archivo, medirlo o leer sus
etiquetas va en el motor o en un hilo.
"""

from __future__ import annotations

import builtins
import logging
import os
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import motores, tiempos

log = logging.getLogger(__name__)

AUDIO = frozenset({"mp3", "wav", "wma", "m4a", "m4b", "aac", "flac", "ogg", "oga", "opus", "aif", "aiff", "mid", "midi",
	"ac3", "amr", "ape", "wv", "mka", "mp2", "mpc", "tta", "caf", "dsf", "spx"})
VIDEO = frozenset({"mp4", "m4v", "mkv", "avi", "wmv", "mov", "webm", "mpg", "mpeg", "ts", "m2ts", "flv", "3gp", "ogv", "vob"})
MULTIMEDIA = AUDIO | VIDEO
#: Formatos que el motor de Windows no abre sin extensiones: van directos a ffplay si está.
SOLO_FFPLAY = frozenset({"ogg", "oga", "opus", "ape", "wv", "mka", "mkv", "webm", "flv", "ac3", "amr", "mpc", "tta", "dsf",
	"spx", "ogv", "caf", "vob"})

REPETIR = ("no", "uno", "todos")
VELOCIDAD_MINIMA, VELOCIDAD_MAXIMA, PASO_VELOCIDAD = 0.5, 3.0, 0.25
PASO_VOLUMEN = 5
#: Cada cuánto se guarda la posición mientras suena (por si zCommander se cierra de golpe).
GUARDAR_CADA_S = 30


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def extension(ruta: str) -> str:
	return os.path.splitext(ruta)[1].lower().lstrip(".")


def es_multimedia(nombre: str) -> bool:
	return extension(nombre) in MULTIMEDIA


@dataclass
class Pista:
	ruta: str
	titulo: str = ""
	duracion: float = 0.0

	@property
	def nombre(self) -> str:
		return self.titulo or os.path.splitext(os.path.basename(self.ruta))[0]


class Reproductor:
	"""Un reproductor por sesión: lo crea el complemento la primera vez que hace falta."""

	def __init__(self, *, config: Callable[[str], Any], anunciar: Callable[..., None], sonar: Callable[[str], Any],
			memoria: Any, fabrica_motor: Callable[[str], Any], ffplay_disponible: Callable[[], bool],
			planificar_tarde: Callable[[float, Callable[[], None]], Any], titulos: Callable[[str, Callable[[str, float], None]], None] | None = None,
			guardar_config: Callable[[str, Any], Any] | None = None) -> None:
		self._config = config
		self._anunciar = anunciar
		self._sonar = sonar
		self.memoria = memoria
		self._fabrica_motor = fabrica_motor
		self._ffplay_disponible = ffplay_disponible
		self._planificar_tarde = planificar_tarde
		self._titulos = titulos
		self._guardar_config = guardar_config
		self.cola: list[Pista] = []
		self.indice = -1
		self._orden: list[int] = []
		self.repetir = "no"
		self.aleatorio = False
		self.motor: Any = None
		self._tipo_motor = ""
		self._motores: dict[str, Any] = {}
		self.volumen = int(self._leer("volumen", 80))
		self.velocidad = float(self._leer("velocidad", 1.0))
		self.cargando = False
		self._temporizador: Any = None
		self.fin_temporizador: float = 0.0
		self._latido: Any = None
		self._desde_guardado = 0
		self.al_cambiar: list[Callable[[], None]] = []
		self._intentado_ffplay = False
		self._anunciar_al_cargar = False

	# ── Utilidades ───────────────────────────────────────────────────────────

	def _leer(self, clave: str, defecto: Any) -> Any:
		try:
			valor = self._config(clave)
		except Exception:  # noqa: BLE001 - una clave rota no deja sin reproductor
			log.debug("No se pudo leer %s", clave, exc_info=True)
			return defecto
		return defecto if valor is None else valor

	def _avisar(self) -> None:
		for funcion in list(self.al_cambiar):
			try:
				funcion()
			except Exception:  # noqa: BLE001 - una ventana cerrada no corta el reproductor
				log.debug("Falló un aviso del reproductor", exc_info=True)

	@property
	def pista(self) -> Pista | None:
		return self.cola[self.indice] if 0 <= self.indice < len(self.cola) else None

	def estado(self) -> str:
		if self.cargando:
			return "cargando"
		if self.motor is None or self.pista is None:
			return motores.DETENIDO
		return self.motor.estado()

	def posicion(self) -> float:
		return self.motor.posicion() if self.motor is not None and self.pista is not None else 0.0

	def duracion(self) -> float:
		pista = self.pista
		if pista is None:
			return 0.0
		medida = self.motor.duracion() if self.motor is not None and not self.cargando else 0.0
		return medida or pista.duracion

	# ── Cola ─────────────────────────────────────────────────────────────────

	def reproducir_lista(self, rutas: list[str], inicio: int = 0) -> None:
		"""Sustituye la cola y empieza por ``inicio``."""
		self._guardar_posicion()
		self._parar_motor()
		self.cola = [Pista(r) for r in rutas]
		self._rehacer_orden(inicio)
		self._pedir_titulos(self.cola)
		if not self.cola:
			self.indice = -1
			self._avisar()
			return
		self._abrir(inicio, anunciar=True)

	def anadir(self, rutas: list[str]) -> int:
		nuevas = [Pista(r) for r in rutas]
		self.cola.extend(nuevas)
		self._orden.extend(range(len(self.cola) - len(nuevas), len(self.cola)))
		if self.aleatorio:
			self._rehacer_orden(self.indice)
		self._pedir_titulos(nuevas)
		self._avisar()
		return len(nuevas)

	def quitar(self, posicion: int) -> None:
		if not 0 <= posicion < len(self.cola):
			return
		if posicion == self.indice:
			self._guardar_posicion()
			self._parar_motor()
			self.indice = -1
		elif posicion < self.indice:
			self.indice -= 1
		self.cola.pop(posicion)
		self._rehacer_orden(self.indice)
		self._avisar()

	def _rehacer_orden(self, primero: int) -> None:
		indices = list(range(len(self.cola)))
		if self.aleatorio and indices:
			random.shuffle(indices)
			if 0 <= primero < len(self.cola):
				indices.remove(primero)
				indices.insert(0, primero)
		self._orden = indices

	def _pedir_titulos(self, pistas: list[Pista]) -> None:
		if self._titulos is None:
			return
		for pista in pistas:
			def llegado(titulo: str, duracion: float, pista: Pista = pista) -> None:
				if titulo:
					pista.titulo = titulo
				if duracion > 0 and pista.duracion <= 0:
					pista.duracion = duracion
				self._avisar()

			self._titulos(pista.ruta, llegado)

	# ── Abrir y avisos del motor ─────────────────────────────────────────────

	def _motor_para(self, ruta: str, forzar_ffplay: bool = False) -> str:
		usar_ffplay = bool(self._leer("usar_ffplay", True))
		if forzar_ffplay or extension(ruta) in SOLO_FFPLAY:
			if usar_ffplay and self._ffplay_disponible():
				return "ffplay"
			return ""
		return "windows"

	def _obtener_motor(self, tipo: str) -> Any:
		if tipo not in self._motores:
			motor = self._fabrica_motor(tipo)
			motor.al_cargado = lambda motor=motor: self._al_cargado(motor)
			motor.al_terminar = lambda motor=motor: self._al_terminar(motor)
			motor.al_error = lambda mensaje, motor=motor: self._al_error(motor, mensaje)
			self._motores[tipo] = motor
		return self._motores[tipo]

	def _parar_motor(self) -> None:
		if self.motor is not None:
			self.motor.detener()
		self.cargando = False

	def _abrir(self, indice: int, anunciar: bool = False, forzar_ffplay: bool = False) -> None:
		if not 0 <= indice < len(self.cola):
			return
		self._parar_motor()
		self.indice = indice
		pista = self.cola[indice]
		self._intentado_ffplay = forzar_ffplay
		self._anunciar_al_cargar = anunciar
		if not os.path.isfile(pista.ruta):
			self._anunciar(_("No se encuentra {n}").format(n=pista.nombre), "esencial")
			self.motor = None
			self._avisar()
			return
		tipo = self._motor_para(pista.ruta, forzar_ffplay)
		if not tipo:
			self.motor = None
			self._anunciar(_("Este formato necesita el componente FFmpeg"), "esencial")
			self._avisar()
			return
		self._intentado_ffplay = tipo == "ffplay"
		self.motor = self._obtener_motor(tipo)
		self._tipo_motor = tipo
		self.cargando = True
		if not self.motor.cargar(pista.ruta):
			self.cargando = False
			self._al_error(self.motor, "no_abre")
			return
		self._avisar()

	def _al_cargado(self, motor: Any) -> None:
		if motor is not self.motor or not self.cargando:
			return
		self.cargando = False
		pista = self.pista
		if pista is None:
			return
		duracion = motor.duracion()
		if duracion > 0:
			pista.duracion = duracion
		motor.fijar_volumen(self.volumen)
		if abs(self.velocidad - 1.0) > 0.001 and not motor.fijar_velocidad(self.velocidad):
			log.info("El motor %s no admite la velocidad %s", motor.nombre, self.velocidad)
		recordada = self._posicion_recordada(pista)
		if recordada:
			motor.ir_a(recordada)
		motor.reproducir()
		self._desde_guardado = 0
		self._latir()
		if self._anunciar_al_cargar:
			self._anunciar_al_cargar = False
			self._anunciar_pista(recordada)
		self._avisar()

	def _anunciar_pista(self, recordada: float | None = None) -> None:
		pista = self.pista
		if pista is None:
			return
		self._sonar("pista")
		if bool(self._leer("anunciar_pista", True)):
			texto = pista.nombre
			if len(self.cola) > 1:
				texto = _("{n} de {t}: {p}").format(n=self.indice + 1, t=len(self.cola), p=texto)
			if recordada:
				texto += ". " + _("Continúa en {t}").format(t=tiempos.formatear(recordada))
			self._anunciar(texto, "normal")
		elif recordada:
			self._anunciar(_("Continúa en {t}").format(t=tiempos.formatear(recordada)), "normal")

	def _al_terminar(self, motor: Any) -> None:
		if motor is not self.motor:
			return
		pista = self.pista
		if pista is not None:
			self.memoria.olvidar_posicion(pista.ruta)
		if self.repetir == "uno":
			self._abrir(self.indice)
			return
		siguiente = self._vecino(1)
		if siguiente is None:
			if self.repetir == "todos" and self.cola:
				self._rehacer_orden(-1)
				self._abrir(self._orden[0], anunciar=True)
				return
			self._parar_motor()
			self._sonar("fin_lista")
			self._anunciar(_("Fin de la cola de reproducción"), "resultado")
			self._avisar()
			return
		self._abrir(siguiente, anunciar=True)

	def _al_error(self, motor: Any, mensaje: str) -> None:
		if motor is not self.motor:
			return
		pista = self.pista
		self.cargando = False
		if pista is None:
			return
		if self._tipo_motor == "windows" and not self._intentado_ffplay:
			if bool(self._leer("usar_ffplay", True)) and self._ffplay_disponible():
				log.info("Windows no abre %s; se prueba con ffplay", pista.ruta)
				self._abrir(self.indice, anunciar=self._anunciar_al_cargar or True, forzar_ffplay=True)
				return
			self.motor.detener()
			self._anunciar(_("Este formato necesita el componente FFmpeg"), "esencial")
			self._avisar()
			return
		self._anunciar(_("No se puede reproducir {n}: {m}").format(n=pista.nombre, m=mensaje or _("error desconocido")), "esencial")
		siguiente = self._vecino(1)
		if siguiente is not None:
			self._abrir(siguiente, anunciar=True)
		else:
			self._parar_motor()
			self._avisar()

	def _vecino(self, paso: int) -> int | None:
		if not self.cola or self.indice not in self._orden:
			return None
		posicion = self._orden.index(self.indice) + paso
		if 0 <= posicion < len(self._orden):
			return self._orden[posicion]
		return None

	# ── Posiciones recordadas ────────────────────────────────────────────────

	def _es_largo(self, pista: Pista) -> bool:
		minutos = int(self._leer("recordar_desde_min", 10))
		return bool(self._leer("recordar_posicion", True)) and pista.duracion >= minutos * 60

	def _posicion_recordada(self, pista: Pista) -> float | None:
		if not self._es_largo(pista):
			return None
		segundos = self.memoria.posicion(pista.ruta)
		if segundos is None or segundos < 5 or (pista.duracion > 0 and segundos > pista.duracion - 5):
			return None
		return segundos

	def _guardar_posicion(self) -> None:
		pista = self.pista
		if pista is None or self.motor is None or self.cargando or not self._es_largo(pista):
			return
		posicion = self.motor.posicion()
		try:
			if posicion < 5 or (pista.duracion > 0 and posicion > pista.duracion - 10):
				self.memoria.olvidar_posicion(pista.ruta)
			else:
				self.memoria.guardar_posicion(pista.ruta, posicion)
		except OSError:
			log.warning("No se pudo guardar la posición de %s", pista.ruta, exc_info=True)

	def _latir(self) -> None:
		"""Cada segundo mientras suena: avisa a la ventana y guarda la posición cada 30 s."""
		if self._latido is not None:
			return

		def latido() -> None:
			self._latido = None
			if self.estado() != motores.REPRODUCIENDO:
				return
			self._desde_guardado += 1
			if self._desde_guardado >= GUARDAR_CADA_S:
				self._desde_guardado = 0
				self._guardar_posicion()
			self._avisar()
			self._latir()

		self._latido = self._planificar_tarde(1.0, latido)

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def _hay_pista(self) -> bool:
		if self.pista is None or self.motor is None:
			self._anunciar(_("No se está reproduciendo nada"), "resultado")
			return False
		return True

	def pausa_continuar(self) -> None:
		if self.pista is None and self.cola:
			self._abrir(self._orden[0] if self._orden else 0, anunciar=True)
			return
		if not self._hay_pista() or self.cargando:
			return
		estado = self.motor.estado()
		if estado == motores.REPRODUCIENDO:
			self.motor.pausar()
			self._guardar_posicion()
			self._anunciar(_("En pausa"), "resultado")
		elif estado == motores.PAUSADO:
			self.motor.reproducir()
			self._latir()
			self._anunciar(_("Continúa"), "resultado")
		else:
			self._abrir(self.indice, anunciar=True)
			return
		self._avisar()

	def detener(self) -> None:
		if self.pista is None or self.motor is None:
			self._anunciar(_("No se está reproduciendo nada"), "resultado")
			return
		self._guardar_posicion()
		self._parar_motor()
		self._anunciar(_("Detenido"), "resultado")
		self._avisar()

	def saltar(self, segundos: float) -> None:
		if not self._hay_pista() or self.cargando:
			return
		duracion = self.duracion()
		destino = self.motor.posicion() + segundos
		if duracion > 0:
			destino = min(destino, max(0.0, duracion - 1))
		self.ir_a(max(0.0, destino), anunciar=True)

	def ir_a(self, segundos: float, anunciar: bool = True) -> None:
		if not self._hay_pista() or self.cargando:
			return
		duracion = self.duracion()
		if duracion > 0 and segundos > duracion:
			self._anunciar(_("La pista dura {d}").format(d=tiempos.formatear(duracion)), "resultado")
			return
		self.motor.ir_a(segundos)
		if anunciar:
			self._anunciar(tiempos.formatear(segundos), "resultado")
		self._avisar()

	def ir_a_pista(self, indice: int) -> None:
		if 0 <= indice < len(self.cola):
			self._guardar_posicion()
			self._abrir(indice, anunciar=True)

	def siguiente(self) -> None:
		if not self.cola:
			self._anunciar(_("La cola está vacía"), "resultado")
			return
		vecino = self._vecino(1)
		if vecino is None and self.repetir == "todos":
			vecino = self._orden[0]
		if vecino is None:
			self._anunciar(_("Es la última pista"), "resultado")
			return
		self._guardar_posicion()
		self._abrir(vecino, anunciar=True)

	def anterior(self) -> None:
		if not self.cola:
			self._anunciar(_("La cola está vacía"), "resultado")
			return
		if self.motor is not None and self.posicion() > 5 and not self.cargando:
			self.ir_a(0, anunciar=False)
			self._anunciar(_("Principio de la pista"), "resultado")
			return
		vecino = self._vecino(-1)
		if vecino is None:
			self._anunciar(_("Es la primera pista"), "resultado")
			return
		self._guardar_posicion()
		self._abrir(vecino, anunciar=True)

	def cambiar_volumen(self, paso: int) -> None:
		self.fijar_volumen(self.volumen + paso)
		self._anunciar(_("Volumen {v}").format(v=self.volumen), "resultado")

	def fijar_volumen(self, volumen: int, guardar: bool = True) -> None:
		self.volumen = max(0, min(100, int(volumen)))
		if self.motor is not None and not self.cargando:
			self.motor.fijar_volumen(self.volumen)
		if guardar and self._guardar_config is not None:
			self._guardar_config("volumen", self.volumen)
		self._avisar()

	def cambiar_velocidad(self, paso: float) -> None:
		nueva = round(max(VELOCIDAD_MINIMA, min(VELOCIDAD_MAXIMA, self.velocidad + paso)), 2)
		if self.motor is not None and not self.motor.admite_velocidad and self.pista is not None:
			self._anunciar(_("Con este formato no se puede cambiar la velocidad"), "resultado")
			return
		if self.motor is not None and self.pista is not None and not self.cargando and not self.motor.fijar_velocidad(nueva):
			self._anunciar(_("Windows no puede cambiar la velocidad de este archivo"), "resultado")
			return
		self.velocidad = nueva
		if self._guardar_config is not None:
			self._guardar_config("velocidad", self.velocidad)
		self._anunciar(_("Velocidad {v}").format(v=tiempos.texto_velocidad(self.velocidad)), "resultado")
		self._avisar()

	def fijar_velocidad(self, velocidad: float) -> None:
		self.velocidad = round(max(VELOCIDAD_MINIMA, min(VELOCIDAD_MAXIMA, float(velocidad))), 2)
		if self.motor is not None and self.pista is not None and not self.cargando:
			self.motor.fijar_velocidad(self.velocidad)
		self._avisar()

	def cambiar_repetir(self) -> None:
		self.repetir = REPETIR[(REPETIR.index(self.repetir) + 1) % len(REPETIR)]
		self._anunciar(self.texto_repetir(), "resultado")
		self._avisar()

	def texto_repetir(self) -> str:
		return {"no": _("Sin repetir"), "uno": _("Repetir esta pista"), "todos": _("Repetir toda la cola")}[self.repetir]

	def cambiar_aleatorio(self) -> None:
		self.aleatorio = not self.aleatorio
		self._rehacer_orden(self.indice)
		self._anunciar(_("Orden aleatorio") if self.aleatorio else _("Orden de la cola"), "resultado")
		self._avisar()

	def texto_posicion(self) -> str:
		pista = self.pista
		if pista is None or self.motor is None:
			return _("No se está reproduciendo nada")
		if self.cargando:
			return _("Abriendo {n}").format(n=pista.nombre)
		return tiempos.decir_posicion(self.motor.posicion(), self.duracion())

	def decir_posicion(self) -> None:
		self._anunciar(self.texto_posicion(), "resultado")

	# ── Marcadores ───────────────────────────────────────────────────────────

	def anadir_marcador(self, nombre: str) -> bool:
		if not self._hay_pista():
			return False
		posicion = self.motor.posicion()
		texto = nombre.strip() or tiempos.formatear(posicion)
		self.memoria.anadir_marcador(self.pista.ruta, texto, posicion)
		self._sonar("marcador")
		self._anunciar(_("Marcador «{n}» en {t}").format(n=texto, t=tiempos.formatear(posicion)), "resultado")
		return True

	def marcadores(self) -> list[tuple[str, float]]:
		return self.memoria.marcadores(self.pista.ruta) if self.pista is not None else []

	# ── Temporizador de apagado ──────────────────────────────────────────────

	def fijar_temporizador(self, minutos: float, ahora: float) -> None:
		if self._temporizador is not None:
			try:
				self._temporizador.Stop()
			except Exception:  # noqa: BLE001 - ya había saltado
				log.debug("El temporizador ya no existía", exc_info=True)
			self._temporizador = None
			self.fin_temporizador = 0.0
		if minutos <= 0:
			self._anunciar(_("Temporizador de apagado quitado"), "resultado")
			return
		self.fin_temporizador = ahora + minutos * 60
		self._temporizador = self._planificar_tarde(minutos * 60, self._saltar_temporizador)
		self._anunciar(_("La reproducción se detendrá dentro de {m} minutos").format(m=f"{minutos:g}".replace(".", ",")), "resultado")

	def _saltar_temporizador(self) -> None:
		self._temporizador = None
		self.fin_temporizador = 0.0
		if self.pista is not None and self.motor is not None:
			self._guardar_posicion()
			self._parar_motor()
			self._anunciar(_("Temporizador de apagado: reproducción detenida"), "resultado")
			self._avisar()

	# ── Cierre ───────────────────────────────────────────────────────────────

	def cerrar(self) -> None:
		self._guardar_posicion()
		for motor in self._motores.values():
			try:
				motor.cerrar()
			except Exception:  # noqa: BLE001 - al cerrar no se interrumpe nada por un motor
				log.debug("No se pudo cerrar un motor", exc_info=True)
		self._motores.clear()
		self.motor = None
		self.indice = -1
