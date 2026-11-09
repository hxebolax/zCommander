# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Estados de los complementos y llamadas protegidas (diseño 2.0, 3.4 y 3.8). Sin wx.

Lo crea N2 y su dueño posterior es PL; ``cargador.py`` y ``gestor.py`` solo
lo importan.

- ``EstadoComplemento`` y ``Pendiente``: el estado de carga y el cambio que
  queda para el reinicio.
- ``llamar_protegido``: TODA entrada del núcleo a código de un complemento pasa
  por aquí. Captura la excepción, la registra con id, versión y traza, anuncia
  una vez por sesión y complemento y lleva el contador de fallos: al llegar a
  ``complementos.fallos_maximos`` el complemento pasa a ``FALLIDO``.
- **Vigilante de bloqueos**: un solo hilo propio. Antes de cada llamada en el
  hilo de la interfaz se apila un latido (marca de tiempo e id) y se desapila
  al volver; si el de arriba pasa de 2 s, se vuelcan una vez las trazas de
  todos los hilos en ``fallo_nativo.log`` con el complemento culpable. Los
  diálogos modales ponen el latido en pausa (``pausa_modal``).
"""

from __future__ import annotations

import builtins
import faulthandler
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from typing import Any

log = logging.getLogger(__name__)

#: Un latido de más de este tiempo en el hilo de la interfaz se considera bloqueo.
LIMITE_BLOQUEO_S = 2.0
INTERVALO_VIGILANTE_S = 0.5


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class EstadoComplemento(StrEnum):
	INCOMPATIBLE = "incompatible"
	INHABILITADO = "inhabilitado"
	SIN_ACEPTAR = "sin_aceptar"
	REGISTRADO = "registrado"
	CARGANDO = "cargando"
	ACTIVO = "activo"
	FALLIDO = "fallido"
	ERROR_MANIFIESTO = "error_manifiesto"


class Pendiente(StrEnum):
	NINGUNO = "ninguno"
	INSTALAR = "instalar"
	ACTUALIZAR = "actualizar"
	VOLVER_ATRAS = "volver_atras"
	DESINSTALAR = "desinstalar"


#: Texto del gestor para cada estado (3.11).
TEXTOS_ESTADO: dict[EstadoComplemento, str] = {
	EstadoComplemento.INCOMPATIBLE: "Incompatible",
	EstadoComplemento.INHABILITADO: "Inhabilitado",
	EstadoComplemento.SIN_ACEPTAR: "Sin aceptar",
	EstadoComplemento.REGISTRADO: "Sin cargar todavía",
	EstadoComplemento.CARGANDO: "Cargando",
	EstadoComplemento.ACTIVO: "Activo",
	EstadoComplemento.FALLIDO: "Fuera de uso por errores",
	EstadoComplemento.ERROR_MANIFIESTO: "Error en el manifiesto",
}


# ── Contador de fallos y avisos ──────────────────────────────────────────────

class _Protecciones:
	def __init__(self) -> None:
		self.candado = threading.Lock()
		self.fallos: dict[str, int] = {}
		self.avisados: set[str] = set()
		self.fallos_maximos = 3
		self.nombres: dict[str, tuple[str, str]] = {}
		self.anunciador: Callable[[str], None] | None = None
		self.al_quedar_fuera: Callable[[str, str], None] | None = None
		self.lentos: dict[str, int] = {}
		self.aviso_desarrollo: Callable[[str], None] | None = None


_proteccion = _Protecciones()


def fijar_fallos_maximos(numero: int) -> None:
	_proteccion.fallos_maximos = max(1, int(numero))


def fijar_datos(id_complemento: str, nombre: str, version: str) -> None:
	"""Nombre visible y versión de un complemento (para los avisos y el registro)."""
	with _proteccion.candado:
		_proteccion.nombres[id_complemento] = (nombre, version)


def fijar_anunciador(funcion: Callable[[str], None] | None) -> None:
	"""Cómo se anuncia un fallo como esencial (la ventana pone ``anuncios.anunciar``)."""
	_proteccion.anunciador = funcion


def fijar_al_quedar_fuera(funcion: Callable[[str, str], None] | None) -> None:
	"""Aviso al cargador de que un complemento debe pasar a ``FALLIDO`` (id, motivo)."""
	_proteccion.al_quedar_fuera = funcion


def fallos(id_complemento: str) -> int:
	with _proteccion.candado:
		return _proteccion.fallos.get(id_complemento, 0)


def reiniciar() -> None:
	"""Olvida contadores y avisos (pruebas y nueva sesión)."""
	with _proteccion.candado:
		_proteccion.fallos.clear()
		_proteccion.avisados.clear()
		_proteccion.lentos.clear()


def olvidar(id_complemento: str) -> None:
	"""Olvida los fallos de un complemento («Volver a intentarlo» del gestor, 3.8)."""
	with _proteccion.candado:
		_proteccion.fallos.pop(id_complemento, None)
		_proteccion.avisados.discard(id_complemento)
		_proteccion.lentos.pop(id_complemento, None)


#: Un manejador de evento que pasa de este tiempo cuenta como lento (3.8); tres veces, aviso.
LIMITE_EVENTO_S = 0.020
AVISOS_EVENTO_LENTO = 3


def llamar_evento(id_complemento: str, nombre: str, funcion: Callable[..., Any], *args: Any, **kwargs: Any) -> Any | None:
	"""``llamar_protegido`` de un suscriptor de evento, midiendo su tiempo (sin el de los diálogos modales).

	Si pasa de 20 ms tres veces se registra un aviso con el nombre del complemento y
	del evento (y se anuncia solo en modo desarrollo, con ``fijar_aviso_desarrollo``).
	"""
	inicio = time.perf_counter()
	pausado_antes = _latidos.pausado_total
	resultado = llamar_protegido(id_complemento, funcion, *args, **kwargs)
	duracion = time.perf_counter() - inicio - (_latidos.pausado_total - pausado_antes)
	if duracion > LIMITE_EVENTO_S:
		with _proteccion.candado:
			cuenta = _proteccion.lentos.get(id_complemento, 0) + 1
			_proteccion.lentos[id_complemento] = cuenta
		if cuenta == AVISOS_EVENTO_LENTO:
			log.warning("El complemento %s tarda más de %s ms en atender el evento %s (%s veces)", id_complemento,
				int(LIMITE_EVENTO_S * 1000), nombre, cuenta)
			aviso = _proteccion.aviso_desarrollo
			if aviso is not None:
				try:
					aviso(_("El complemento {n} tarda demasiado en atender {e}").format(n=nombre_de(id_complemento), e=nombre))
				except Exception:  # noqa: BLE001 - el aviso de desarrollo nunca rompe el evento
					log.debug("No se pudo anunciar el aviso de tiempo", exc_info=True)
	return resultado


def fijar_aviso_desarrollo(funcion: Callable[[str], None] | None) -> None:
	"""En modo desarrollo, cómo se anuncian los avisos de tiempo y de accesibilidad (3.12)."""
	_proteccion.aviso_desarrollo = funcion


def nombre_de(id_complemento: str) -> str:
	with _proteccion.candado:
		return _proteccion.nombres.get(id_complemento, (id_complemento, ""))[0]


def registrar_fallo(id_complemento: str, accion: str, error: BaseException | None = None, *, definitivo: bool = False) -> None:
	"""Cuenta un fallo, lo registra y lo anuncia una vez por sesión; con el máximo (o ``definitivo``), fuera de uso."""
	with _proteccion.candado:
		_proteccion.fallos[id_complemento] = _proteccion.fallos.get(id_complemento, 0) + 1
		cuenta = _proteccion.fallos[id_complemento]
		nombre, version = _proteccion.nombres.get(id_complemento, (id_complemento, ""))
		avisar = id_complemento not in _proteccion.avisados
		_proteccion.avisados.add(id_complemento)
		maximo = _proteccion.fallos_maximos
	log.error("El complemento %s %s falló al %s (fallo %s de %s)", id_complemento, version, accion, cuenta, maximo,
		exc_info=(type(error), error, error.__traceback__) if error is not None else None)
	if avisar and _proteccion.anunciador is not None:
		try:
			_proteccion.anunciador(_("El complemento {n} falló al {a}. Detalles en el registro.").format(n=nombre, a=accion))
		except Exception:  # noqa: BLE001 - un aviso que falla no debe tapar el fallo original
			log.debug("No se pudo anunciar el fallo del complemento", exc_info=True)
	if (definitivo or cuenta >= maximo) and _proteccion.al_quedar_fuera is not None:
		try:
			_proteccion.al_quedar_fuera(id_complemento, accion)
		except Exception:  # noqa: BLE001
			log.exception("No se pudo dejar fuera de uso el complemento %s", id_complemento)


def llamar_protegido(id_complemento: str, funcion: Callable[..., Any], *args: Any, **kwargs: Any) -> Any | None:
	"""Llama a código de un complemento sin que su excepción llegue al núcleo. ``None`` si lanzó.

	En el hilo principal (el de la interfaz) apila un latido para el vigilante de bloqueos.
	"""
	en_interfaz = threading.current_thread() is threading.main_thread()
	if en_interfaz:
		_latidos.apilar(id_complemento)
	try:
		return funcion(*args, **kwargs)
	except Exception as error:  # noqa: BLE001 - la protección es justo esto
		accion = getattr(funcion, "__name__", "ejecutar una función")
		registrar_fallo(id_complemento, _("ejecutar «{f}»").format(f=accion), error)
		return None
	finally:
		if en_interfaz:
			_latidos.desapilar()


# ── Latidos y vigilante de bloqueos ──────────────────────────────────────────

class _Latidos:
	def __init__(self) -> None:
		self.candado = threading.Lock()
		self.pila: list[list[Any]] = []  # [inicio, id, volcado, pausado_desde]
		self.vigilante: threading.Thread | None = None
		self.parar = threading.Event()
		self.archivo: Any = None
		#: Segundos que han pasado en diálogos modales (no cuentan en la medición de los eventos).
		self.pausado_total = 0.0

	def apilar(self, id_complemento: str) -> None:
		with self.candado:
			self.pila.append([time.monotonic(), id_complemento, False, None])

	def desapilar(self) -> None:
		with self.candado:
			if self.pila:
				self.pila.pop()

	def pausar(self) -> None:
		with self.candado:
			for latido in self.pila:
				if latido[3] is None:
					latido[3] = time.monotonic()

	def reanudar(self) -> None:
		ahora = time.monotonic()
		with self.candado:
			if self.pila and self.pila[-1][3] is not None:
				self.pausado_total += ahora - self.pila[-1][3]
			for latido in self.pila:
				if latido[3] is not None:
					latido[0] += ahora - latido[3]
					latido[3] = None

	def revisar(self) -> str | None:
		"""Id del complemento que bloquea la interfaz (solo la primera vez que se detecta), o ``None``."""
		ahora = time.monotonic()
		with self.candado:
			if not self.pila:
				return None
			latido = self.pila[-1]
			if latido[3] is not None or latido[2] or ahora - latido[0] < LIMITE_BLOQUEO_S:
				return None
			latido[2] = True
			return latido[1]


_latidos = _Latidos()


@contextmanager
def pausa_modal() -> Iterator[None]:
	"""El tiempo que la persona pasa en un diálogo modal no cuenta como bloqueo."""
	_latidos.pausar()
	try:
		yield
	finally:
		_latidos.reanudar()


def _vigilar() -> None:
	while not _latidos.parar.wait(INTERVALO_VIGILANTE_S):
		culpable = _latidos.revisar()
		if culpable is None:
			continue
		log.warning("El complemento %s bloquea la interfaz más de %s s", culpable, LIMITE_BLOQUEO_S)
		archivo = _latidos.archivo
		if archivo is not None:
			try:
				archivo.write(f"\n--- El complemento {culpable} bloquea la interfaz ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
				archivo.flush()
				faulthandler.dump_traceback(file=archivo, all_threads=True)
			except Exception:  # noqa: BLE001 - el vigilante nunca debe morir
				log.debug("No se pudo volcar la traza del bloqueo", exc_info=True)


def iniciar_vigilante(archivo: Any = None) -> None:
	"""Arranca el hilo vigilante (una vez). ``archivo``: el ``fallo_nativo.log`` de ``app.core.registro``."""
	if archivo is None:
		from app.core import registro

		archivo = registro.archivo_fallos()
	_latidos.archivo = archivo
	if _latidos.vigilante is not None and _latidos.vigilante.is_alive():
		return
	_latidos.parar.clear()
	_latidos.vigilante = threading.Thread(target=_vigilar, name="zc-vigilante", daemon=True)
	_latidos.vigilante.start()


def detener_vigilante() -> None:
	_latidos.parar.set()
