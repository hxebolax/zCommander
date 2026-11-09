# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Historial del portapapeles en memoria y, si se pide, en disco cifrado con DPAPI (diseño 2.0, 11.16). Sin wx.

- Lo más reciente va primero. Copiar algo que ya está lo sube arriba (sin repetirlo).
- Los fijados no se pierden al llegar al máximo de ``elementos``.
- En disco (``datos/historial.json``) solo con ``guardar_entre_sesiones``, y
  siempre cifrado con DPAPI: solo lo puede leer el mismo usuario de Windows.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_portapapeles")

TEXTO = "texto"
ARCHIVOS = "archivos"
#: Textos más largos no se guardan en el historial (se registra y se sigue).
MAX_TEXTO = 1_000_000
ENTROPIA = b"zCommander/zc.portapapeles/v1"
FORMATO = 1


@dataclass(frozen=True)
class Elemento:
	tipo: str
	texto: str = ""
	archivos: tuple[str, ...] = ()
	hora: float = 0.0
	fijado: bool = False

	@property
	def clave(self) -> tuple:
		return (self.tipo, self.texto, self.archivos)

	@property
	def contenido(self) -> str:
		"""Lo que se ve en la lista: el texto en una línea o «3 archivos de D:\\Fotos»."""
		if self.tipo == ARCHIVOS:
			carpetas = {os.path.dirname(a) for a in self.archivos}
			donde = carpetas.pop() if len(carpetas) == 1 else _("varias carpetas")
			if len(self.archivos) == 1:
				return _("{n} de {c}").format(n=os.path.basename(self.archivos[0]), c=donde)
			return _n("{n} archivo de {c}", "{n} archivos de {c}", len(self.archivos)).format(n=len(self.archivos), c=donde)
		linea = " ".join(self.texto.split())
		return linea if len(linea) <= 200 else linea[:199] + "…"

	@property
	def como_texto(self) -> str:
		"""Para la línea de órdenes y para «archivo nuevo»: el texto, o las rutas entre comillas."""
		if self.tipo == ARCHIVOS:
			return " ".join(f'"{a}"' if " " in a else a for a in self.archivos)
		return self.texto

	def hora_texto(self) -> str:
		momento = time.localtime(self.hora)
		hoy = time.localtime()
		if (momento.tm_year, momento.tm_yday) == (hoy.tm_year, hoy.tm_yday):
			return time.strftime("%H:%M:%S", momento)
		return time.strftime("%d/%m/%Y %H:%M", momento)


def de_texto(texto: str) -> Elemento | None:
	if not texto or not texto.strip() or len(texto) > MAX_TEXTO:
		if texto and len(texto) > MAX_TEXTO:
			log.info("Texto copiado demasiado largo para el historial (%d caracteres)", len(texto))
		return None
	return Elemento(TEXTO, texto=texto, hora=time.time())


def de_archivos(rutas: Sequence[str]) -> Elemento | None:
	rutas = tuple(r for r in rutas if r)
	return Elemento(ARCHIVOS, archivos=rutas, hora=time.time()) if rutas else None


class Historial:
	"""Lista de elementos, segura entre hilos (la escucha añade desde su hilo; la ventana lee en la interfaz)."""

	def __init__(self, maximo: int = 50) -> None:
		self._candado = threading.RLock()
		self._elementos: list[Elemento] = []
		self.maximo = maximo
		self.version = 0

	def elementos(self) -> list[Elemento]:
		with self._candado:
			return list(self._elementos)

	def __len__(self) -> int:
		with self._candado:
			return len(self._elementos)

	def anadir(self, elemento: Elemento) -> bool:
		"""Añade arriba; si ya estaba, lo sube conservando si estaba fijado. Verdadero si es nuevo."""
		with self._candado:
			previo = next((e for e in self._elementos if e.clave == elemento.clave), None)
			if previo is not None:
				self._elementos.remove(previo)
				elemento = replace(elemento, fijado=previo.fijado)
			self._elementos.insert(0, elemento)
			self._recortar()
			self.version += 1
			return previo is None

	def _recortar(self) -> None:
		sobran = len(self._elementos) - max(1, self.maximo)
		for elemento in reversed(list(self._elementos)):
			if sobran <= 0:
				break
			if not elemento.fijado:
				self._elementos.remove(elemento)
				sobran -= 1

	def fijar_maximo(self, maximo: int) -> None:
		with self._candado:
			self.maximo = maximo
			self._recortar()
			self.version += 1

	def alternar_fijado(self, elemento: Elemento) -> Elemento:
		with self._candado:
			indice = self._elementos.index(elemento)
			nuevo = replace(elemento, fijado=not elemento.fijado)
			self._elementos[indice] = nuevo
			self.version += 1
			return nuevo

	def borrar(self, elemento: Elemento) -> None:
		with self._candado:
			if elemento in self._elementos:
				self._elementos.remove(elemento)
				self.version += 1

	def borrar_todo(self) -> None:
		with self._candado:
			self._elementos.clear()
			self.version += 1

	def buscar(self, texto: str) -> list[Elemento]:
		texto = texto.strip().casefold()
		elementos = self.elementos()
		if not texto:
			return elementos
		return [e for e in elementos if texto in e.texto.casefold() or any(texto in a.casefold() for a in e.archivos)]

	# ── Disco (DPAPI) ───────────────────────────────────────────────────────

	def guardar(self, ruta: Path) -> None:
		import win32crypt

		with self._candado:
			datos = {"formato": FORMATO, "elementos": [{**asdict(e), "archivos": list(e.archivos)} for e in self._elementos]}
		claro = json.dumps(datos, ensure_ascii=False).encode("utf-8")
		cifrado = win32crypt.CryptProtectData(claro, "zCommander: historial del portapapeles", ENTROPIA, None, None, 0)
		ruta.parent.mkdir(parents=True, exist_ok=True)
		temporal = ruta.with_suffix(ruta.suffix + ".tmp")
		temporal.write_bytes(cifrado)
		os.replace(temporal, ruta)

	def cargar(self, ruta: Path) -> int:
		"""Lee el historial guardado; uno ilegible (otro usuario u otro equipo) se aparta y se empieza vacío."""
		if not ruta.is_file():
			return 0
		import win32crypt

		try:
			_descripcion, claro = win32crypt.CryptUnprotectData(ruta.read_bytes(), ENTROPIA, None, None, 0)
			datos = json.loads(claro.decode("utf-8"))
			elementos = [Elemento(str(d["tipo"]), str(d.get("texto", "")), tuple(d.get("archivos", ())), float(d.get("hora", 0)),
				bool(d.get("fijado", False))) for d in datos.get("elementos", [])]
		except Exception:  # noqa: BLE001 - DPAPI de otro usuario o archivo dañado: se aparta, nunca se pierde en silencio
			log.warning("No se pudo leer el historial del portapapeles; se aparta", exc_info=True)
			try:
				os.replace(ruta, ruta.with_suffix(ruta.suffix + f".ilegible-{int(time.time())}"))
			except OSError:
				log.debug("No se pudo apartar %s", ruta, exc_info=True)
			return 0
		with self._candado:
			conocidos = {e.clave for e in self._elementos}
			self._elementos.extend(e for e in elementos if e.clave not in conocidos and e.tipo in (TEXTO, ARCHIVOS))
			self._recortar()
			self.version += 1
		return len(elementos)
