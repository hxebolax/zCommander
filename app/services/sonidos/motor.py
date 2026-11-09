# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor de sonidos de zCommander (diseño 2.0, 4.4): el ``Reproductor`` real. Sin wx ni dependencias.

- **Resolución**: paquete elegido → su cadena ``hereda`` → ``clasico`` →
  ``sonidos/`` del paquete del complemento → silencio (``paquetes.resolver``),
  con una caché por (paquete, evento, variante).
- **Volumen**: ``sonidos.volumen`` de 0 a 100 con la ganancia de 4.4; las
  muestras se escalan una vez por (archivo, volumen) y se guardan en una caché
  de 32 MB como máximo, que se vacía al cambiar el volumen o el paquete.
- **Cola con prioridades** en un hilo ``sonidos``: una alta corta lo que suena
  si es de prioridad menor; una baja se descarta si suena una de prioridad
  mayor; varias bajas seguidas se agrupan (solo suena la última) y como mucho
  una cada ``sonidos.intervalo_navegacion_ms``; las altas nunca se descartan
  (se encadenan, como mucho 4 en cola). Una petición que sustituye un anuncio
  se acepta o se rechaza en el momento y, si se acepta, ya no se descarta.
- **Reproducción**: ``PlaySoundW`` de ``winmm.dll`` con ``SND_MEMORY |
  SND_ASYNC | SND_NODEFAULT`` (``winsound`` no admite ``SND_ASYNC`` con
  ``SND_MEMORY``). El búfer en curso se guarda hasta que acaba o lo sustituye
  otro, para que Windows nunca lea memoria liberada.

``sonar`` solo consulta valores ya calculados, busca en las cachés y encola:
menos de 5 ms (objetivo 10 de 1.2). Nunca bloquea ni lanza.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.services.sonidos import catalogo, paquetes, wav
from app.services.sonidos.catalogo import ALTA, BAJA, MEDIA, EventoSonido

log = logging.getLogger(__name__)

#: Rango de cada prioridad (menor = más importante).
RANGO = {ALTA: 0, MEDIA: 1, BAJA: 2}
#: Tope de la caché de muestras ya escaladas (4.4).
MAX_CACHE = 32 * 1024 * 1024
#: Altas en cola como máximo (4.4).
MAX_ALTAS = 4
#: Ventana en la que varias peticiones bajas seguidas se agrupan en la última.
AGRUPAR_S = 0.02
#: Una baja que no ha podido sonar en este tiempo ya no orienta: se descarta.
CADUCIDAD_BAJA_S = 0.4
#: Margen tras el final de un sonido antes de soltar su búfer (4.4).
MARGEN_BUFER_S = 0.05
#: La precarga espera a que pase el arranque para no competir con la ventana.
RETRASO_PRECARGA_S = 2.0


class Salida(Protocol):
	"""Lo que de verdad emite el sonido (Windows, o un falso en las pruebas)."""

	def reproducir(self, datos: bytes) -> None: ...
	def detener(self) -> None: ...


class SalidaWinmm:
	"""``PlaySoundW`` asíncrono desde memoria. Fuera de Windows no suena nada."""

	SND_ASYNC = 0x0001
	SND_NODEFAULT = 0x0002
	SND_MEMORY = 0x0004

	def __init__(self) -> None:
		self._bufer: bytes | None = None
		self._play: Any = None
		if sys.platform == "win32":
			try:
				import ctypes

				funcion = ctypes.windll.winmm.PlaySoundW
				funcion.argtypes = (ctypes.c_char_p, ctypes.c_void_p, ctypes.c_uint)
				funcion.restype = ctypes.c_int
				self._play = funcion
			except (OSError, AttributeError):
				log.warning("No se pudo cargar winmm.dll: no habrá sonidos", exc_info=True)

	def reproducir(self, datos: bytes) -> None:
		if self._play is None:
			return
		# Se guarda ANTES de llamar: Windows lee el búfer mientras suena.
		self._bufer = datos
		self._play(datos, None, self.SND_MEMORY | self.SND_ASYNC | self.SND_NODEFAULT)

	def detener(self) -> None:
		if self._play is None:
			return
		self._play(None, None, 0)
		self._bufer = None


@dataclass(frozen=True)
class Sonido:
	"""Un WAV listo para ``PlaySoundW``: bytes ya escalados al volumen y su duración."""

	datos: bytes
	duracion: float


@dataclass
class _Peticion:
	id: str
	prioridad: str
	sonido: Sonido
	firme: bool
	llegada: float

	@property
	def rango(self) -> int:
		return RANGO.get(self.prioridad, 1)


@dataclass
class _Sonando:
	peticion: _Peticion
	inicio: float
	fin: float


@dataclass
class _Colas:
	altas: deque[_Peticion] = field(default_factory=deque)
	medias: deque[_Peticion] = field(default_factory=deque)
	bajas: deque[_Peticion] = field(default_factory=deque)

	def vaciar(self) -> None:
		self.altas.clear()
		self.medias.clear()
		self.bajas.clear()


class Motor:
	"""Reproductor de 4.4 (protocolo ``servicio.Reproductor``).

	:param config: configuración (``sonidos.volumen``, ``sonidos.paquete``, ``sonidos.intervalo_navegacion_ms``).
	:param salida: lo que emite el sonido (por defecto ``SalidaWinmm``; las pruebas pasan uno falso).
	:param precargar: cargar en segundo plano los sonidos activos del paquete al empezar y al recargar.
	"""

	def __init__(self, config: Any, *, salida: Salida | None = None, reloj: Callable[[], float] = time.monotonic,
			precargar: bool = True) -> None:
		self.config = config
		self._salida: Salida = salida if salida is not None else SalidaWinmm()
		self._reloj = reloj
		self._condicion = threading.Condition()
		self._colas = _Colas()
		self._sonando: _Sonando | None = None
		self._ultima_baja = float("-inf")
		self._cerrado = False
		self._hilo: threading.Thread | None = None
		self._candado_cache = threading.RLock()
		self._rutas: dict[tuple[str, str, str], Path | None] = {}
		self._sonidos: OrderedDict[tuple[Path, int], Sonido] = OrderedDict()
		self._bytes_cache = 0
		self._invalidos: set[Path] = set()
		self._generacion = 0
		self._precargar = precargar
		self._parada = threading.Event()
		#: Últimos eventos que empezaron a sonar (los consultan las pruebas y el diagnóstico).
		self.reproducidos: deque[str] = deque(maxlen=200)
		self._volumen = 70
		self._paquete = paquetes.BASE
		self._leer_config()
		self._lanzar_precarga()

	# ── Configuración ──────────────────────────────────────────────────────

	def _obtener(self, clave: str, defecto: Any) -> Any:
		try:
			return self.config.obtener(clave)
		except Exception:  # noqa: BLE001 - una configuración falsa sin la clave usa el valor de fábrica
			return defecto

	def _leer_config(self) -> None:
		try:
			volumen = int(self._obtener("sonidos.volumen", 70))
		except (TypeError, ValueError):
			volumen = 70
		self._volumen = max(0, min(100, volumen))
		self._paquete = str(self._obtener("sonidos.paquete", paquetes.BASE) or paquetes.BASE)

	def _intervalo(self) -> float:
		try:
			return max(0, int(self._obtener("sonidos.intervalo_navegacion_ms", 40))) / 1000
		except (TypeError, ValueError):
			return 0.04

	@property
	def volumen(self) -> int:
		return self._volumen

	@property
	def paquete(self) -> str:
		return self._paquete

	# ── Protocolo Reproductor ──────────────────────────────────────────────

	def sonar(self, evento: EventoSonido, variante: str, sustituye: bool) -> bool:
		"""Acepta (verdadero) o no el sonido: volumen mayor que 0, archivo válido y no descartado."""
		try:
			if self._cerrado or self._volumen <= 0:
				return False
			sonido = self.preparar(evento, variante, self._paquete, self._volumen)
			if sonido is None:
				return False
			return self._encolar(_Peticion(evento.id, evento.prioridad, sonido, bool(sustituye), self._reloj()))
		except Exception:  # noqa: BLE001 - un sonido nunca rompe la orden que lo pidió
			log.warning("Falló el sonido %s", evento.id, exc_info=True)
			return False

	def recargar(self) -> None:
		"""Cambió el paquete, el volumen o los paquetes instalados: vacía las cachés y vuelve a leer."""
		with self._candado_cache:
			self._rutas.clear()
			self._sonidos.clear()
			self._bytes_cache = 0
			self._invalidos.clear()
			self._generacion += 1
		self._leer_config()
		self._lanzar_precarga()

	def cerrar(self) -> None:
		"""Vacía la cola, para el sonido en curso y espera al hilo 0,5 s como máximo."""
		self._parada.set()
		with self._condicion:
			self._cerrado = True
			self._colas.vaciar()
			self._condicion.notify_all()
			hilo = self._hilo
		with self._candado_cache:
			self._generacion += 1
		try:
			self._salida.detener()
		except Exception:  # noqa: BLE001 - cerrar nunca falla por la tarjeta de sonido
			log.debug("No se pudo detener el sonido en curso", exc_info=True)
		if hilo is not None and hilo is not threading.current_thread():
			hilo.join(0.5)
		with self._condicion:
			self._sonando = None

	# ── Probar (página Sonidos, mapa y asistente) ──────────────────────────

	def reproducir(self, evento: EventoSonido, variante: str = "", *, paquete: str | None = None,
			volumen: int | None = None) -> bool:
		"""Hace sonar el evento con ese paquete y volumen aunque esté desactivado (corta lo que suene)."""
		volumen = self._volumen if volumen is None else max(0, min(100, int(volumen)))
		if self._cerrado or volumen <= 0:
			return False
		sonido = self.preparar(evento, variante, paquete or self._paquete, volumen)
		if sonido is None:
			return False
		return self._encolar(_Peticion(evento.id, ALTA, sonido, False, self._reloj()), prueba=True)

	def reproducir_archivo(self, ruta: Path, *, volumen: int | None = None, nombre: str = "") -> bool:
		"""Hace sonar un WAV suelto (asistente: «Probar» un archivo aún no guardado)."""
		volumen = self._volumen if volumen is None else max(0, min(100, int(volumen)))
		if self._cerrado or volumen <= 0:
			return False
		sonido = self._cargar(Path(ruta), volumen)
		if sonido is None:
			return False
		return self._encolar(_Peticion(nombre or Path(ruta).name, ALTA, sonido, False, self._reloj()), prueba=True)

	# ── Archivos y caché ───────────────────────────────────────────────────

	def ruta(self, evento: EventoSonido, variante: str = "", paquete: str | None = None) -> Path | None:
		"""Archivo que suena para el evento con ese paquete (con caché)."""
		clave = (paquete or self._paquete, evento.id, variante)
		with self._candado_cache:
			if clave in self._rutas:
				return self._rutas[clave]
			generacion = self._generacion
		ruta = paquetes.resolver(evento, variante, clave[0])
		with self._candado_cache:
			if generacion == self._generacion:
				self._rutas[clave] = ruta
		return ruta

	def preparar(self, evento: EventoSonido, variante: str, paquete: str, volumen: int) -> Sonido | None:
		"""El sonido listo para reproducir (resuelto, leído, validado y escalado), o ``None``."""
		ruta = self.ruta(evento, variante, paquete)
		return None if ruta is None else self._cargar(ruta, volumen)

	def _cargar(self, ruta: Path, volumen: int) -> Sonido | None:
		clave = (ruta, volumen)
		with self._candado_cache:
			sonido = self._sonidos.get(clave)
			if sonido is not None:
				self._sonidos.move_to_end(clave)
				return sonido
			if ruta in self._invalidos:
				return None
			generacion = self._generacion
		try:
			audio = wav.leer(ruta)
		except wav.WavNoValido as error:
			with self._candado_cache:
				nuevo = ruta not in self._invalidos
				self._invalidos.add(ruta)
			if nuevo:
				log.warning("Sonido no válido, se trata como ausente: %s (%s)", ruta, error.mensaje)
			return None
		sonido = Sonido(audio.a_wav(wav.escalar(audio.muestras, wav.ganancia(volumen))), audio.duracion)
		with self._candado_cache:
			if generacion != self._generacion:
				return sonido
			self._sonidos[clave] = sonido
			self._bytes_cache += len(sonido.datos)
			while self._bytes_cache > MAX_CACHE and len(self._sonidos) > 1:
				_clave, viejo = self._sonidos.popitem(last=False)
				self._bytes_cache -= len(viejo.datos)
		return sonido

	def precargar(self, eventos: Iterable[EventoSonido] | None = None) -> int:
		"""Carga en la caché los sonidos de esos eventos (por defecto, los activos). Devuelve cuántos."""
		with self._candado_cache:
			generacion = self._generacion
		if eventos is None:
			from app.services.sonidos import servicio

			eventos = [e for e in catalogo.eventos() if servicio.evento_activo(e.id)]
		cargados = 0
		for evento in eventos:
			if self._cerrado or generacion != self._generacion:
				break
			for variante in ("", *evento.variantes):
				if self.preparar(evento, variante, self._paquete, self._volumen) is not None:
					cargados += 1
		return cargados

	def _lanzar_precarga(self) -> None:
		if not self._precargar or self._volumen <= 0:
			return

		def trabajar() -> None:
			if self._parada.wait(RETRASO_PRECARGA_S):
				return
			try:
				self.precargar()
			except Exception:  # noqa: BLE001 - la precarga solo adelanta trabajo; sin ella se carga al sonar
				log.debug("Falló la precarga de sonidos", exc_info=True)

		threading.Thread(target=trabajar, name="sonidos-precarga", daemon=True).start()

	# ── Cola con prioridades ───────────────────────────────────────────────

	def _actual(self, ahora: float) -> _Sonando | None:
		sonando = self._sonando
		return sonando if sonando is not None and sonando.fin > ahora else None

	def _encolar(self, peticion: _Peticion, *, prueba: bool = False) -> bool:
		with self._condicion:
			if self._cerrado:
				return False
			actual = self._actual(peticion.llegada)
			if prueba:
				# Probar un sonido sustituye a todo lo pendiente y corta lo que suene.
				self._colas.vaciar()
				self._colas.altas.append(peticion)
				self._sonando = None
			elif peticion.prioridad == ALTA:
				if len(self._colas.altas) >= MAX_ALTAS:
					log.debug("Cola de sonidos altos llena; no se acepta %s", peticion.id)
					return False
				self._colas.altas.append(peticion)
			else:
				if actual is not None and actual.peticion.rango < peticion.rango:
					# Suena uno de prioridad mayor: la baja se descarta y la que sustituye un anuncio no se acepta.
					if peticion.prioridad == BAJA or peticion.firme:
						return False
				cola = self._colas.medias if peticion.prioridad == MEDIA else self._colas.bajas
				if not peticion.firme:
					# Agrupar: la nueva sustituye a las pendientes de su prioridad que no son firmes.
					for pendiente in [p for p in cola if not p.firme]:
						cola.remove(pendiente)
				if len(cola) >= MAX_ALTAS:
					if peticion.firme:
						return False
					cola.popleft()
				cola.append(peticion)
			self._asegurar_hilo()
			self._condicion.notify_all()
			return True

	def _asegurar_hilo(self) -> None:
		if self._hilo is None or not self._hilo.is_alive():
			self._hilo = threading.Thread(target=self._trabajar, name="sonidos", daemon=True)
			self._hilo.start()

	def _elegir(self, ahora: float) -> tuple[_Peticion | None, float | None]:
		"""La petición que debe sonar ya, o cuánto esperar (``None``: hasta que llegue otra)."""
		actual = self._actual(ahora)
		if self._sonando is not None and actual is None and ahora > self._sonando.fin + MARGEN_BUFER_S:
			self._sonando = None
		colas = self._colas
		if colas.altas:
			if actual is None or actual.peticion.rango > 0:
				return colas.altas.popleft(), None
			return None, actual.fin - ahora
		if actual is not None:
			return None, actual.fin - ahora
		if colas.medias:
			return colas.medias.popleft(), None
		while colas.bajas and not colas.bajas[0].firme and ahora - colas.bajas[0].llegada > CADUCIDAD_BAJA_S:
			colas.bajas.popleft()
		if colas.bajas:
			primera = colas.bajas[0]
			lista = max(primera.llegada + (0 if primera.firme else AGRUPAR_S), self._ultima_baja + self._intervalo())
			if lista <= ahora:
				return colas.bajas.popleft(), None
			return None, lista - ahora
		return None, None

	def _trabajar(self) -> None:
		while True:
			with self._condicion:
				while True:
					if self._cerrado:
						return
					ahora = self._reloj()
					peticion, espera = self._elegir(ahora)
					if peticion is not None:
						break
					self._condicion.wait(None if espera is None else max(0.001, espera))
				self._sonando = _Sonando(peticion, ahora, ahora + peticion.sonido.duracion)
				if peticion.prioridad == BAJA:
					self._ultima_baja = ahora
				self.reproducidos.append(peticion.id)
			try:
				self._salida.reproducir(peticion.sonido.datos)
			except Exception:  # noqa: BLE001 - sin tarjeta de sonido se sigue sin sonidos
				log.warning("No se pudo reproducir %s", peticion.id, exc_info=True)
