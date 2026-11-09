# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lectura en vivo frase a frase: pausa, continuar, frases y párrafos, y dónde se dejó. Sin wx.

La voz llega inyectada (``VozSapi`` o una falsa en las pruebas) con
``hablar(texto, numero, al_terminar)``, ``pausar``, ``continuar`` y ``callar``.
Cada frase lleva su número: un aviso de fin de una frase que ya no es la actual
(porque la persona saltó) se ignora.
"""

from __future__ import annotations

import builtins
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import texto as modulo_texto

log = logging.getLogger(__name__)

DETENIDO, LEYENDO, PAUSADO = "detenido", "leyendo", "pausado"
#: Cada cuántas frases se guarda dónde va la lectura (además de al pausar, detener y cerrar).
GUARDAR_CADA = 10


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Posiciones:
	"""``datos/posiciones.json``: ruta → frase y tamaño (si el archivo cambia, se empieza de nuevo)."""

	def __init__(self, carpeta: Path) -> None:
		self._archivo = Path(carpeta) / "posiciones.json"
		self._candado = threading.Lock()
		self._datos: dict[str, dict[str, Any]] | None = None

	def _todas(self) -> dict[str, dict[str, Any]]:
		if self._datos is None:
			try:
				datos = json.loads(self._archivo.read_text(encoding="utf-8"))
				self._datos = datos if isinstance(datos, dict) else {}
			except FileNotFoundError:
				self._datos = {}
			except (OSError, ValueError):
				log.warning("No se pudo leer %s", self._archivo, exc_info=True)
				self._datos = {}
		return self._datos

	def _guardar(self) -> None:
		self._archivo.parent.mkdir(parents=True, exist_ok=True)
		temporal = self._archivo.with_name(self._archivo.name + ".tmp")
		temporal.write_text(json.dumps(self._todas(), ensure_ascii=False), encoding="utf-8")
		os.replace(temporal, self._archivo)

	@staticmethod
	def _clave(ruta: str) -> str:
		return os.path.normcase(os.path.normpath(ruta))

	@staticmethod
	def _tamano(ruta: str) -> int:
		try:
			return os.path.getsize(ruta)
		except OSError:
			return -1

	def obtener(self, ruta: str) -> int:
		with self._candado:
			dato = self._todas().get(self._clave(ruta))
		if not isinstance(dato, dict) or int(dato.get("tamano", -2)) != self._tamano(ruta):
			return 0
		return max(0, int(dato.get("frase", 0)))

	def guardar(self, ruta: str, frase: int) -> None:
		with self._candado:
			datos = self._todas()
			datos[self._clave(ruta)] = {"frase": int(frase), "tamano": self._tamano(ruta), "fecha": time.time()}
			if len(datos) > 300:
				for clave in sorted(datos, key=lambda c: datos[c].get("fecha", 0))[:len(datos) - 300]:
					datos.pop(clave, None)
			try:
				self._guardar()
			except OSError:
				log.warning("No se pudo guardar la posición de lectura", exc_info=True)

	def olvidar(self, ruta: str) -> None:
		with self._candado:
			if self._todas().pop(self._clave(ruta), None) is not None:
				try:
					self._guardar()
				except OSError:
					log.warning("No se pudo guardar la posición de lectura", exc_info=True)


class Lector:
	def __init__(self, voz: Any, *, anunciar: Callable[..., None], sonar: Callable[[str], Any], posiciones: Posiciones | None,
			pausa_parrafo_ms: Callable[[], int] = lambda: 400, tono: Callable[[], int] = lambda: 0) -> None:
		self.voz = voz
		self._anunciar = anunciar
		self._sonar = sonar
		self.posiciones = posiciones
		self._pausa_parrafo_ms = pausa_parrafo_ms
		self._tono = tono
		self.frases: list[modulo_texto.Frase] = []
		self.indice = 0
		self.estado = DETENIDO
		self.ruta = ""
		self.nombre = ""
		self._numero = 0
		self._desde_guardado = 0

	# ── Empezar y avanzar ────────────────────────────────────────────────────

	def leer(self, texto: str, ruta: str = "", nombre: str = "", desde: int | None = None) -> None:
		self._callar()
		self.frases = modulo_texto.dividir(texto)
		self.ruta, self.nombre = ruta, nombre or os.path.basename(ruta)
		if not self.frases:
			self.estado = DETENIDO
			self._anunciar(_("{n} no tiene texto que leer").format(n=self.nombre or _("El documento")), "resultado")
			return
		inicio = desde if desde is not None else (self.posiciones.obtener(ruta) if self.posiciones is not None and ruta else 0)
		if not 0 <= inicio < len(self.frases):
			inicio = 0
		if inicio:
			self._anunciar(_("Continúa donde se dejó, frase {n} de {t}").format(n=inicio + 1, t=len(self.frases)), "normal")
		self.indice = inicio
		self.estado = LEYENDO
		self._decir_actual()

	def _decir_actual(self) -> None:
		self._numero += 1
		frase = self.frases[self.indice]
		silencio = 0
		siguiente = self.indice + 1
		if siguiente < len(self.frases) and self.frases[siguiente].parrafo != frase.parrafo:
			silencio = int(self._pausa_parrafo_ms())
		self.voz.hablar(modulo_texto.xml_sapi(frase.texto, self._tono(), silencio), self._numero, self._al_terminar_frase)

	def _al_terminar_frase(self, numero: int) -> None:
		if numero < 0:
			self.estado = DETENIDO
			self._anunciar(_("No hay ninguna voz de Windows disponible para leer"), "esencial")
			return
		if numero != self._numero or self.estado != LEYENDO:
			return
		self._desde_guardado += 1
		if self._desde_guardado >= GUARDAR_CADA:
			self._desde_guardado = 0
			self._guardar()
		if self.indice + 1 >= len(self.frases):
			self.estado = DETENIDO
			if self.posiciones is not None and self.ruta:
				self.posiciones.olvidar(self.ruta)
			self._sonar("fin")
			self._anunciar(_("Fin de la lectura"), "resultado")
			return
		self.indice += 1
		self._decir_actual()

	def _callar(self) -> None:
		if self.estado != DETENIDO:
			self._numero += 1
			self.voz.callar()

	def _guardar(self) -> None:
		if self.posiciones is not None and self.ruta and self.frases:
			self.posiciones.guardar(self.ruta, self.indice)

	# ── Órdenes ──────────────────────────────────────────────────────────────

	@property
	def activo(self) -> bool:
		return self.estado != DETENIDO and bool(self.frases)

	def pausa_continuar(self) -> None:
		if self.estado == LEYENDO:
			self.voz.pausar()
			self.estado = PAUSADO
			self._guardar()
			self._anunciar(_("Lectura en pausa"), "resultado")
		elif self.estado == PAUSADO:
			self.estado = LEYENDO
			self.voz.continuar()

	def detener(self) -> None:
		if not self.activo:
			self._anunciar(_("No se está leyendo nada"), "resultado")
			return
		self._guardar()
		self._callar()
		self.estado = DETENIDO
		self._anunciar(_("Lectura detenida"), "resultado")

	def _ir_a(self, indice: int, limite: str) -> None:
		if not self.frases:
			self._anunciar(_("No se está leyendo nada"), "resultado")
			return
		if not 0 <= indice < len(self.frases):
			self._anunciar(limite, "resultado")
			return
		self._callar()
		self.indice = indice
		self.estado = LEYENDO
		self._decir_actual()

	def frase_siguiente(self) -> None:
		self._ir_a(self.indice + 1, _("Es la última frase"))

	def frase_anterior(self) -> None:
		self._ir_a(self.indice - 1, _("Es la primera frase"))

	def parrafo_siguiente(self) -> None:
		if not self.frases:
			self._ir_a(-1, "")
			return
		actual = self.frases[self.indice].parrafo
		destino = next((i for i in range(self.indice + 1, len(self.frases)) if self.frases[i].parrafo != actual), -1)
		self._ir_a(destino, _("Es el último párrafo"))

	def parrafo_anterior(self) -> None:
		if not self.frases:
			self._ir_a(-1, "")
			return
		actual = self.frases[self.indice].parrafo
		inicio_actual = next(i for i in range(len(self.frases)) if self.frases[i].parrafo == actual)
		if self.indice > inicio_actual:
			destino = inicio_actual
		elif actual == self.frases[0].parrafo:
			destino = -1
		else:
			anterior = self.frases[inicio_actual - 1].parrafo
			destino = next(i for i in range(len(self.frases)) if self.frases[i].parrafo == anterior)
		self._ir_a(destino, _("Es el primer párrafo"))

	def cerrar(self) -> None:
		if self.activo:
			self._guardar()
		self._callar()
		self.estado = DETENIDO
