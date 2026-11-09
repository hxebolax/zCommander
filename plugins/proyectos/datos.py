# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Frecencia de carpetas y proyectos (diseño 2.0, 11.15). Sin wx.

**Frecencia** (como zoxide): cada carpeta guarda cuántas veces se ha entrado
y cuándo fue la última. Su puntuación es ``visitas ** peso_frecuencia``
multiplicado por ``0,5 ** (días desde la última visita / media_vida_dias)``:
con la media vida de 14 días, una carpeta que no se visita desde hace dos
semanas pesa la mitad. Con ``peso_frecuencia`` 0 solo cuenta lo reciente; con
2, la frecuencia manda.

Buscar «fact» propone las carpetas cuya ruta contiene todos los trozos
escritos (sin distinguir mayúsculas), y las que lo tienen en el **último**
nombre de la ruta suben por delante (igual que zoxide): «fact» encuentra antes
``D:\\Facturas`` que ``D:\\Facturas\\2025\\Enero``.

**Proyecto**: un espacio de trabajo del núcleo (pestañas y vistas, con
``zc.espacios``) más una nota y unas carpetas propias.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("zcplugins.zc.proyectos")

ARCHIVO_FRECENCIA = "frecencia.json"
ARCHIVO_PROYECTOS = "proyectos.json"
_DIA = 86400.0


def _escribir_json(ruta: Path, datos: object) -> None:
	temporal = ruta.with_suffix(".tmp")
	temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
	temporal.replace(ruta)


def _leer_json(ruta: Path, defecto):
	try:
		return json.loads(ruta.read_text(encoding="utf-8"))
	except FileNotFoundError:
		return defecto
	except (OSError, ValueError):
		log.warning("No se pudo leer %s; se empieza de cero", ruta, exc_info=True)
		return defecto


def _clave(ruta: str) -> str:
	return ruta.rstrip("\\/").casefold() if len(ruta.rstrip("\\/")) > 2 else ruta.casefold()


def excluida(ruta: str, excluidas: Iterable[str]) -> bool:
	clave = _clave(ruta)
	for carpeta in excluidas:
		base = _clave(str(carpeta))
		if base and (clave == base or clave.startswith(base.rstrip("\\") + "\\")):
			return True
	return False


@dataclass(frozen=True)
class Propuesta:
	ruta: str
	puntuacion: float
	visitas: int
	origen: str = "frecuente"  # «frecuente» o «windows» (elementos recientes de Windows)


class Frecencia:
	"""Visitas por carpeta. No es seguro entre hilos: se usa en el hilo de la interfaz y se guarda una copia."""

	def __init__(self, carpeta_datos: Path) -> None:
		self.archivo = Path(carpeta_datos) / ARCHIVO_FRECENCIA
		self.carpetas: dict[str, list] = {}  # ruta tal como se vio → [visitas, última visita]
		self.cambios = 0

	def cargar(self) -> Frecencia:
		datos = _leer_json(self.archivo, {})
		carpetas = datos.get("carpetas", {}) if isinstance(datos, dict) else {}
		self.carpetas = {str(r): [int(v[0]), float(v[1])] for r, v in carpetas.items()
			if isinstance(v, list) and len(v) == 2}
		return self

	def instantanea(self) -> dict:
		return {"version": 1, "carpetas": {r: list(v) for r, v in self.carpetas.items()}}

	def guardar(self, datos: dict | None = None) -> None:
		self.archivo.parent.mkdir(parents=True, exist_ok=True)
		_escribir_json(self.archivo, datos if datos is not None else self.instantanea())

	def _buscar_clave(self, ruta: str) -> str | None:
		clave = _clave(ruta)
		return next((r for r in self.carpetas if _clave(r) == clave), None)

	def visitar(self, ruta: str, ahora: float | None = None) -> None:
		ahora = time.time() if ahora is None else ahora
		existente = self._buscar_clave(ruta)
		if existente is None:
			self.carpetas[ruta] = [1, ahora]
		else:
			self.carpetas[existente][0] += 1
			self.carpetas[existente][1] = ahora
		self.cambios += 1

	def olvidar(self, ruta: str) -> bool:
		existente = self._buscar_clave(ruta)
		if existente is None:
			return False
		del self.carpetas[existente]
		self.cambios += 1
		return True

	@staticmethod
	def puntuacion(visitas: int, ultima: float, ahora: float, peso: float, media_vida_dias: float) -> float:
		edad_dias = max(0.0, (ahora - ultima) / _DIA)
		return (max(1, visitas) ** max(0.0, peso)) * math.pow(0.5, edad_dias / max(0.1, media_vida_dias))

	def podar(self, maximo: int, peso: float, media_vida_dias: float, ahora: float | None = None) -> None:
		"""Deja las ``maximo`` carpetas con más puntuación."""
		if len(self.carpetas) <= maximo:
			return
		ahora = time.time() if ahora is None else ahora
		orden = sorted(self.carpetas.items(), key=lambda kv: self.puntuacion(kv[1][0], kv[1][1], ahora, peso, media_vida_dias),
			reverse=True)
		self.carpetas = dict(orden[:max(0, maximo)])

	def buscar(self, texto: str, *, peso: float = 1.0, media_vida_dias: float = 14, excluidas: Iterable[str] = (),
			ahora: float | None = None, limite: int = 200) -> list[Propuesta]:
		"""Carpetas que contienen todos los trozos de ``texto``, de más a menos puntuación."""
		ahora = time.time() if ahora is None else ahora
		trozos = [t.casefold() for t in texto.split() if t]
		excluidas = list(excluidas)
		propuestas = []
		for ruta, (visitas, ultima) in self.carpetas.items():
			if excluidas and excluida(ruta, excluidas):
				continue
			if not coincide(ruta, trozos):
				continue
			puntos = self.puntuacion(visitas, ultima, ahora, peso, media_vida_dias)
			if trozos and trozos[-1] in nombre_final(ruta).casefold():
				puntos *= 4  # el último trozo en el nombre de la carpeta, como zoxide
			propuestas.append(Propuesta(ruta, puntos, visitas))
		propuestas.sort(key=lambda p: (-p.puntuacion, p.ruta.casefold()))
		return propuestas[:limite]


def nombre_final(ruta: str) -> str:
	limpia = ruta.rstrip("\\/")
	return limpia.rpartition("\\")[2] or limpia


def coincide(ruta: str, trozos: list[str]) -> bool:
	minusculas = ruta.casefold()
	posicion = 0
	for trozo in trozos:
		encontrado = minusculas.find(trozo, posicion)
		if encontrado < 0:
			return False
		posicion = encontrado + len(trozo)
	return True


# ── Proyectos ────────────────────────────────────────────────────────────────


@dataclass
class Proyecto:
	nombre: str
	nota: str = ""
	carpetas: list[str] = field(default_factory=list)
	espacio: str = ""  # nombre del espacio de trabajo del núcleo ("" si no se pudo guardar)
	creado: float = 0.0


def leer_proyectos(carpeta_datos: Path) -> list[Proyecto]:
	datos = _leer_json(Path(carpeta_datos) / ARCHIVO_PROYECTOS, {})
	proyectos = []
	for elemento in datos.get("proyectos", []) if isinstance(datos, dict) else []:
		try:
			proyectos.append(Proyecto(**{k: v for k, v in elemento.items() if k in Proyecto.__dataclass_fields__}))
		except TypeError:
			log.warning("Proyecto no válido: %r", elemento)
	return proyectos


def guardar_proyectos(carpeta_datos: Path, proyectos: Iterable[Proyecto]) -> None:
	Path(carpeta_datos).mkdir(parents=True, exist_ok=True)
	_escribir_json(Path(carpeta_datos) / ARCHIVO_PROYECTOS, {"version": 1, "proyectos": [asdict(p) for p in proyectos]})
