# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tabla de piezas: el archivo original (que nunca se modifica) más la lista de cambios.

Así se edita un archivo de varios gigas sin cargarlo: cada pieza dice si sus
bytes salen del original o del búfer de lo añadido, y desde qué posición.
Solo se lee del disco lo que se pide (``leer``). Deshacer y rehacer guardan la
lista de piezas de antes y después de cada cambio (sin límite en la sesión).

Guardar escribe todo en un temporal de la misma carpeta y lo cambia por el
archivo de una vez (con ``.bak`` si se pide): nunca queda un archivo a medias.
"""

from __future__ import annotations

import builtins
import os
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, BinaryIO

BLOQUE = 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Pieza:
	"""``anadido`` falso: bytes del original desde ``inicio``; verdadero: del búfer de lo añadido."""

	anadido: bool
	inicio: int
	longitud: int


class TablaPiezas:
	"""Contenido editable de un archivo (o de unos bytes, para las pruebas)."""

	def __init__(self, ruta: str | None = None, datos: bytes | None = None) -> None:
		self.ruta = ruta
		self._original: BinaryIO | None = None
		self._datos_originales = datos
		if ruta is not None:
			self._original = open(ruta, "rb")  # noqa: SIM115 - abierto mientras dure la edición; se cierra en cerrar()
			tamano = os.fstat(self._original.fileno()).st_size
		else:
			tamano = len(datos or b"")
		self._anadido = bytearray()
		self.piezas: list[Pieza] = [Pieza(False, 0, tamano)] if tamano else []
		self._deshacer: list[tuple[list[Pieza], list[Pieza], int]] = []
		self._rehacer: list[tuple[list[Pieza], list[Pieza], int]] = []
		self._grupo: list[Pieza] | None = None
		self._candado = threading.RLock()
		self.guardado = list(self.piezas)

	# ── Consultas ────────────────────────────────────────────────────────────

	def __len__(self) -> int:
		return sum(p.longitud for p in self.piezas)

	@property
	def modificado(self) -> bool:
		return self.piezas != self.guardado

	@property
	def puede_deshacer(self) -> bool:
		return bool(self._deshacer)

	@property
	def puede_rehacer(self) -> bool:
		return bool(self._rehacer)

	def _leer_original(self, inicio: int, n: int) -> bytes:
		if self._original is None:
			return (self._datos_originales or b"")[inicio:inicio + n]
		with self._candado:
			self._original.seek(inicio)
			return self._original.read(n)

	def leer(self, desplazamiento: int, n: int) -> bytes:
		"""Hasta ``n`` bytes desde ``desplazamiento`` (menos al final del archivo)."""
		if n <= 0 or desplazamiento < 0:
			return b""
		partes = []
		posicion = 0
		fin = desplazamiento + n
		for pieza in list(self.piezas):
			siguiente = posicion + pieza.longitud
			if siguiente > desplazamiento and posicion < fin:
				desde = max(desplazamiento, posicion) - posicion
				hasta = min(fin, siguiente) - posicion
				if pieza.anadido:
					partes.append(bytes(self._anadido[pieza.inicio + desde:pieza.inicio + hasta]))
				else:
					partes.append(self._leer_original(pieza.inicio + desde, hasta - desde))
			if siguiente >= fin:
				break
			posicion = siguiente
		return b"".join(partes)

	# ── Cambios ──────────────────────────────────────────────────────────────

	def _partir(self, piezas: list[Pieza], desplazamiento: int) -> tuple[list[Pieza], list[Pieza]]:
		"""Piezas antes y después de ``desplazamiento`` (partiendo la que lo contiene)."""
		antes: list[Pieza] = []
		despues: list[Pieza] = []
		posicion = 0
		for pieza in piezas:
			if posicion + pieza.longitud <= desplazamiento:
				antes.append(pieza)
			elif posicion >= desplazamiento:
				despues.append(pieza)
			else:
				corte = desplazamiento - posicion
				antes.append(Pieza(pieza.anadido, pieza.inicio, corte))
				despues.append(Pieza(pieza.anadido, pieza.inicio + corte, pieza.longitud - corte))
			posicion += pieza.longitud
		return antes, despues

	@staticmethod
	def _unir(piezas: list[Pieza]) -> list[Pieza]:
		"""Junta piezas contiguas del mismo origen (así una edición larga no deja miles de piezas)."""
		resultado: list[Pieza] = []
		for pieza in piezas:
			if pieza.longitud <= 0:
				continue
			if resultado and resultado[-1].anadido == pieza.anadido and resultado[-1].inicio + resultado[-1].longitud == pieza.inicio:
				ultima = resultado[-1]
				resultado[-1] = Pieza(ultima.anadido, ultima.inicio, ultima.longitud + pieza.longitud)
			else:
				resultado.append(pieza)
		return resultado

	def _cambiar(self, nuevas: list[Pieza], cursor: int) -> None:
		anteriores = self.piezas
		self.piezas = self._unir(nuevas)
		if self._grupo is None:
			self._deshacer.append((anteriores, self.piezas, cursor))
			self._rehacer.clear()

	def insertar(self, desplazamiento: int, datos: bytes) -> None:
		if not datos:
			return
		desplazamiento = max(0, min(desplazamiento, len(self)))
		antes, despues = self._partir(self.piezas, desplazamiento)
		nueva = Pieza(True, len(self._anadido), len(datos))
		self._anadido.extend(datos)
		self._cambiar(antes + [nueva] + despues, desplazamiento)

	def borrar(self, desplazamiento: int, n: int) -> None:
		total = len(self)
		if n <= 0 or desplazamiento >= total:
			return
		antes, resto = self._partir(self.piezas, desplazamiento)
		_quitado, despues = self._partir(resto, min(n, total - desplazamiento))
		self._cambiar(antes + despues, desplazamiento)

	def sobrescribir(self, desplazamiento: int, datos: bytes) -> None:
		"""Cambia los bytes desde ``desplazamiento`` (si pasa del final, el archivo crece)."""
		if not datos:
			return
		desplazamiento = max(0, min(desplazamiento, len(self)))
		antes, resto = self._partir(self.piezas, desplazamiento)
		_quitado, despues = self._partir(resto, len(datos))
		nueva = Pieza(True, len(self._anadido), len(datos))
		self._anadido.extend(datos)
		self._cambiar(antes + [nueva] + despues, desplazamiento)

	def iniciar_grupo(self) -> None:
		"""Los cambios hasta ``terminar_grupo`` se deshacen de una vez (reemplazar todos)."""
		if self._grupo is None:
			self._grupo = self.piezas

	def terminar_grupo(self, cursor: int = 0) -> None:
		if self._grupo is None:
			return
		anteriores, self._grupo = self._grupo, None
		if anteriores != self.piezas:
			self._deshacer.append((anteriores, self.piezas, cursor))
			self._rehacer.clear()

	def deshacer(self) -> int | None:
		"""Deshace el último cambio; devuelve dónde ocurrió (para llevar el cursor) o ``None``."""
		if not self._deshacer:
			return None
		anteriores, posteriores, cursor = self._deshacer.pop()
		self.piezas = anteriores
		self._rehacer.append((anteriores, posteriores, cursor))
		return cursor

	def rehacer(self) -> int | None:
		if not self._rehacer:
			return None
		anteriores, posteriores, cursor = self._rehacer.pop()
		self.piezas = posteriores
		self._deshacer.append((anteriores, posteriores, cursor))
		return cursor

	# ── Guardar ──────────────────────────────────────────────────────────────

	def escribir(self, salida: BinaryIO, al_progresar: Callable[[int, int], None] | None = None, cancelacion: Any = None) -> None:
		total = len(self)
		hecho = 0
		while hecho < total:
			if cancelacion is not None and cancelacion.is_set():
				from app.plugins.api import Cancelado

				raise Cancelado()
			bloque = self.leer(hecho, BLOQUE)
			if not bloque:
				break
			salida.write(bloque)
			hecho += len(bloque)
			if al_progresar is not None:
				al_progresar(hecho, total)

	def guardar(self, destino: str | None = None, copia_seguridad: bool = False,
			al_progresar: Callable[[int, int], None] | None = None, cancelacion: Any = None) -> str:
		"""Guarda en ``destino`` (por defecto, el propio archivo). Devuelve la ruta guardada.

		Sobre el propio archivo: temporal en la misma carpeta, ``.bak`` si se pide, y
		cambio de nombre de una vez; después la tabla vuelve a tener una sola pieza.
		"""
		destino = destino or self.ruta
		if destino is None:
			raise ValueError("Sin destino")
		carpeta = os.path.dirname(os.path.abspath(destino))
		temporal = os.path.join(carpeta, f"~{os.path.basename(destino)}.{uuid.uuid4().hex[:8]}.zctmp")
		try:
			with open(temporal, "wb") as salida:
				self.escribir(salida, al_progresar, cancelacion)
			mismo = self.ruta is not None and os.path.normcase(os.path.abspath(destino)) == os.path.normcase(os.path.abspath(self.ruta))
			if mismo and self._original is not None:
				with self._candado:
					self._original.close()
					self._original = None
			if copia_seguridad and os.path.exists(destino):
				shutil.copy2(destino, destino + ".bak")
			os.replace(temporal, destino)
		except BaseException:
			if os.path.exists(temporal):
				os.remove(temporal)
			if self._original is None and self.ruta is not None and os.path.exists(self.ruta):
				self._original = open(self.ruta, "rb")  # noqa: SIM115
			raise
		# Lo guardado pasa a ser el original (también con «Guardar como»: se sigue editando la copia nueva).
		self._reabrir(destino)
		self.guardado = list(self.piezas)
		return destino

	def _reabrir(self, ruta: str) -> None:
		"""Tras guardar sobre el archivo, el original pasa a ser el guardado (y el historial sigue valiendo para el texto)."""
		with self._candado:
			if self._original is not None:
				self._original.close()
			self.ruta = ruta
			self._original = open(ruta, "rb")  # noqa: SIM115
			tamano = os.fstat(self._original.fileno()).st_size
			self._datos_originales = None
			self._anadido = bytearray()
			self.piezas = [Pieza(False, 0, tamano)] if tamano else []
			# Las piezas de deshacer apuntaban al original de antes: ya no sirven.
			self._deshacer.clear()
			self._rehacer.clear()

	def cerrar(self) -> None:
		with self._candado:
			if self._original is not None:
				self._original.close()
				self._original = None


def firma_disco(ruta: str) -> tuple[int, int] | None:
	"""(fecha, tamaño) para saber si el archivo cambió en disco desde que se abrió."""
	try:
		estado = os.stat(ruta)
	except OSError:
		return None
	return estado.st_mtime_ns, estado.st_size
