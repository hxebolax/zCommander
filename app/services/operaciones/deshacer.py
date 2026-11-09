# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Deshacer: las últimas acciones de la sesión, solo en memoria.

Cada acción es una lista de pasos que se deshacen en orden inverso. Antes de
deshacer cada paso se comprueba que nada cambió desde entonces; lo que cambió
se omite y se dice.
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Paso:
	"""Un cambio reversible en el disco local.

	- ``tipo="renombrar"``: ``antes`` pasó a llamarse ``despues``; deshacer lo devuelve.
	- ``tipo="quitar_carpeta"``: se creó la carpeta ``despues``; deshacer la borra si sigue vacía. Una orden
	  que crea varios niveles deja un paso por cada carpeta nueva (ver ``pasos_carpetas_nuevas``).
	- ``tipo="a_papelera"``: se creó el archivo o carpeta ``despues`` (copia); deshacer lo envía a la papelera
	  si conserva ``tamano`` y ``modificado``. Una carpeta (sin tamaño) va entera solo si dentro únicamente
	  hay copias intactas de la misma acción y subcarpetas creadas por ella.
	- ``tipo="restaurar"`` (2.0, API 1.1): el archivo ``despues`` se cambió y ``antes`` es una copia de
	  cómo estaba (la guarda quien registra la acción, por ejemplo un complemento en su ``datos/``);
	  deshacer vuelve a poner esa copia sobre ``despues`` si este conserva ``tamano`` y ``modificado``
	  (los que tenía justo después del cambio). La copia no se borra: es de quien la creó.
	"""

	tipo: str
	despues: str
	antes: str = ""
	tamano: int = -1
	modificado: float = 0.0


def _clave(ruta: str) -> str:
	"""Ruta comparable (Windows no distingue mayúsculas ni separadores)."""
	return os.path.normcase(os.path.normpath(ruta))


def _es_enlace(ruta: str) -> bool:
	return os.path.islink(ruta) or os.path.isjunction(ruta)


def _sin_cambios(paso: Paso) -> bool:
	"""El archivo copiado sigue ahí con el tamaño y la fecha que tenía al copiarlo."""
	if not os.path.lexists(paso.despues):
		return False
	st = os.stat(paso.despues)
	return st.st_size == paso.tamano and abs(st.st_mtime - paso.modificado) <= 2


def pasos_carpetas_nuevas(ruta: str) -> list[Paso]:
	"""Un paso ``quitar_carpeta`` por cada nivel de ``ruta`` que todavía no existe, de fuera adentro.

	Hay que llamarla ANTES de crear la carpeta: después ya no se sabe qué
	niveles existían. Así deshacer «crear a\\b\\c» quita c, b y a (si siguen
	vacías) y nunca una carpeta que ya estaba.
	"""
	nuevas: list[Paso] = []
	actual = os.path.normpath(ruta)
	while not os.path.lexists(actual):
		nuevas.append(Paso("quitar_carpeta", actual))
		padre = os.path.dirname(actual)
		if not padre or padre == actual:
			break
		actual = padre
	return list(reversed(nuevas))


@dataclass
class AccionDeshacer:
	descripcion: str
	pasos: list[Paso] = field(default_factory=list)


@dataclass
class Resultado:
	hechos: int = 0
	omitidos: list[str] = field(default_factory=list)


class RegistroDeshacer:
	"""Pila de acciones (máximo 20)."""

	def __init__(self, maximo: int = 20) -> None:
		self._pila: deque[AccionDeshacer] = deque(maxlen=maximo)
		self._candado = threading.Lock()

	def registrar(self, accion: AccionDeshacer) -> None:
		if accion.pasos:
			with self._candado:
				self._pila.append(accion)

	def ultima(self) -> AccionDeshacer | None:
		with self._candado:
			return self._pila[-1] if self._pila else None

	def sacar_ultima(self) -> AccionDeshacer | None:
		with self._candado:
			return self._pila.pop() if self._pila else None

	def deshacer(self, accion: AccionDeshacer) -> Resultado:
		"""Deshace los pasos de ``accion`` (en un hilo de trabajo: puede usar la papelera).

		Orden: renombrados; después lo que va a la papelera; al final las
		carpetas que hay que quitar, de dentro afuera (así una carpeta creada se
		quita cuando ya no tiene las copias de dentro, y «a\\b\\c» se deshace
		entero aunque los pasos lleguen en otro orden).

		Una carpeta copiada (``a_papelera`` sin tamaño) solo va entera a la
		papelera si contiene exactamente lo que se copió y nada cambió; si no,
		van a la papelera los archivos copiados que siguen igual, lo cambiado o
		añadido se queda (y se dice) y las carpetas que quedan vacías se quitan.
		"""
		resultado = Resultado()
		self._restaurar_copias([p for p in accion.pasos if p.tipo == "restaurar"], resultado)
		self._deshacer_renombrados([p for p in accion.pasos if p.tipo == "renombrar"], resultado)
		archivos = {_clave(p.despues): p for p in accion.pasos if p.tipo == "a_papelera" and p.tamano >= 0}
		carpetas = [p.despues for p in accion.pasos if p.tipo == "quitar_carpeta"]
		registradas = {_clave(c) for c in carpetas}
		a_papelera: list[str] = []
		enteras: list[str] = []
		for paso in reversed(accion.pasos):
			if paso.tipo != "a_papelera" or paso.tamano >= 0:
				continue
			try:
				if not os.path.lexists(paso.despues):
					resultado.omitidos.append(paso.despues)
				elif not os.path.isdir(paso.despues) or _es_enlace(paso.despues):
					a_papelera.append(paso.despues)
				elif not self._cambios_en_carpeta(paso.despues, archivos, registradas):
					a_papelera.append(paso.despues)
					enteras.append(_clave(paso.despues) + os.sep)
				else:
					log.info("La carpeta copiada %s cambió: solo se deshace lo que sigue igual", paso.despues)
					carpetas.append(paso.despues)
			except OSError:
				log.warning("No se pudo deshacer %s", paso, exc_info=True)
				resultado.omitidos.append(paso.despues)
		for clave, paso in reversed(list(archivos.items())):
			if any(clave.startswith(prefijo) for prefijo in enteras):
				continue
			try:
				if _sin_cambios(paso):
					a_papelera.append(paso.despues)
				else:
					resultado.omitidos.append(paso.despues)
			except OSError:
				log.warning("No se pudo deshacer %s", paso, exc_info=True)
				resultado.omitidos.append(paso.despues)
		if a_papelera:
			from app.services.windows import papelera

			papelera.enviar(a_papelera)
			resultado.hechos += len(a_papelera)
		self._quitar_carpetas(carpetas, enteras, resultado)
		return resultado

	@staticmethod
	def _cambios_en_carpeta(carpeta: str, archivos: dict[str, Paso], registradas: set[str]) -> list[str]:
		"""Lo que hay en ``carpeta`` y no es una copia intacta de esta acción (añadido o modificado).

		Un archivo copiado que ya no está no cuenta: mandar la carpeta a la
		papelera no pierde nada. Los enlaces se comparan como archivos (no se
		entra en ellos).
		"""
		cambios: list[str] = []
		pendientes = [carpeta]
		while pendientes:
			actual = pendientes.pop()
			with os.scandir(actual) as elementos:
				for elemento in elementos:
					clave = _clave(elemento.path)
					if elemento.is_dir(follow_symlinks=False) and not _es_enlace(elemento.path):
						if clave in registradas:
							pendientes.append(elemento.path)
						else:
							cambios.append(elemento.path)
						continue
					paso = archivos.get(clave)
					if paso is None or not _sin_cambios(paso):
						cambios.append(elemento.path)
		return cambios

	@staticmethod
	def _quitar_carpetas(carpetas: list[str], enteras: list[str], resultado: Resultado) -> None:
		"""Quita, de dentro afuera, las carpetas creadas que siguen vacías; las que no, se dicen."""
		vistas: set[str] = set()
		for carpeta in sorted(carpetas, key=lambda c: len(os.path.normpath(c)), reverse=True):
			clave = _clave(carpeta)
			if clave in vistas or any((clave + os.sep).startswith(prefijo) for prefijo in enteras):
				continue
			vistas.add(clave)
			try:
				if os.path.isdir(carpeta) and not os.listdir(carpeta):
					os.rmdir(carpeta)
					resultado.hechos += 1
				else:
					resultado.omitidos.append(carpeta)
			except OSError:
				log.warning("No se pudo quitar la carpeta %s", carpeta, exc_info=True)
				resultado.omitidos.append(carpeta)

	@staticmethod
	def _restaurar_copias(pasos: list[Paso], resultado: Resultado) -> None:
		"""Vuelve a poner cada copia sobre su archivo si este no cambió desde la acción (por un temporal, sin dejarlo a medias)."""
		import shutil

		from app.services.operaciones import nombres

		for paso in reversed(pasos):
			temporal = ""
			try:
				if not os.path.isfile(paso.antes) or not _sin_cambios(paso):
					resultado.omitidos.append(paso.despues)
					continue
				temporal = os.path.join(os.path.dirname(paso.despues), nombres.temporal())
				shutil.copy2(paso.antes, temporal)
				os.replace(temporal, paso.despues)
				temporal = ""
				resultado.hechos += 1
			except OSError:
				log.warning("No se pudo deshacer %s", paso, exc_info=True)
				resultado.omitidos.append(paso.despues)
			finally:
				if temporal and os.path.lexists(temporal):
					try:
						os.remove(temporal)
					except OSError:
						log.warning("No se pudo borrar el temporal %s", temporal, exc_info=True)

	@staticmethod
	def _deshacer_renombrados(pasos: list[Paso], resultado: Resultado) -> None:
		"""Devuelve los nombres en dos pasos (por un temporal) para que los ciclos a→b, b→a también se deshagan."""
		from app.services.operaciones import nombres

		apartados: list[tuple[Paso, str]] = []
		for paso in reversed(pasos):
			if not os.path.lexists(paso.despues):
				resultado.omitidos.append(paso.despues)
				continue
			temporal = os.path.join(os.path.dirname(paso.despues), nombres.temporal())
			try:
				os.rename(paso.despues, temporal)
				apartados.append((paso, temporal))
			except OSError:
				log.warning("No se pudo deshacer %s", paso, exc_info=True)
				resultado.omitidos.append(paso.despues)
		for paso, temporal in apartados:
			try:
				if os.path.lexists(paso.antes):
					os.rename(temporal, paso.despues)
					resultado.omitidos.append(paso.despues)
					continue
				os.rename(temporal, paso.antes)
				resultado.hechos += 1
			except OSError:
				log.warning("No se pudo deshacer %s (queda como %s)", paso, temporal, exc_info=True)
				resultado.omitidos.append(paso.despues)
