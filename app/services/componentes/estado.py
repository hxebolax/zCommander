# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Estado de los componentes de ``data/bin`` (diseño 2.0, 3.7, 6.3, 6.8 y 14.9). Sin wx.

- Funciones de destino de la fachada ``zc.componentes`` y del servicio
  ``componentes`` de la ventana: ``ruta``, ``ejecutable``, ``disponible``,
  ``registrar_al_detener`` y ``estado_de``. Leen ``componentes.json`` (lo
  instalado) y, si falta, ``linea_base.json``.
- **En mantenimiento** (6.3): mientras un componente se detiene, se sustituye o
  se restaura, ``ruta()``, ``ejecutable()`` y ``disponible()`` responden como
  si faltara. Por eso ``ruta()`` y ``ejecutable()`` se piden en cada uso y
  nunca se guardan: quien guarda la ``Path`` se salta el mantenimiento.
- **Dañado** (6.8): la comprobación de integridad al arrancar (existencia y
  tamaño de cada archivo de la ficha) marca los componentes a los que les falta
  algo; sus funciones dicen «Falta el componente X: Opciones, Componentes
  externos, Restaurar».
- ``data/config/estado_componentes.json`` (6.3): última comprobación, versiones
  nuevas conocidas y versiones omitidas.
"""

from __future__ import annotations

import builtins
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import paths
from app.services.componentes import fichas
from app.services.vfs.base import NoAdmitido

log = logging.getLogger(__name__)

NOMBRE_ESTADO = "estado_componentes.json"
INSTALADO, FALTA, EN_MANTENIMIENTO, DANADO = "Instalado", "Falta", "En mantenimiento", "Dañado"

_candado = threading.RLock()
_al_detener: dict[str, Callable[[], bool]] = {}
_mantenimiento: dict[str, int] = {}
_danados: set[str] = set()


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Entorno:
	"""Carpetas con las que trabaja el bloque: ``data/bin``, ``data/temp`` y ``data/config``.

	Las pruebas crean uno con carpetas temporales; la aplicación usa ``actual()``.
	"""

	bin: Path
	temp: Path
	config: Path

	@classmethod
	def actual(cls) -> Entorno:
		# «temp» y «config» no se crean solo por mirar dónde está un componente: quien escribe
		# en ellas crea antes la carpeta. Así cargar libarchive al importar no deja carpetas
		# personales vacías en la ``data`` que se distribuye.
		datos = paths.ruta_datos()
		return cls(paths.ruta_binarios(), datos / "temp", datos / "config")

	@classmethod
	def desde_datos(cls, ruta_datos: Path) -> Entorno:
		"""El de una carpeta ``data`` (lo que recibe ``main.py`` en los pasos 5 y 6 de 14.8)."""
		ruta = Path(ruta_datos)
		return cls(ruta / "bin", ruta / "temp", ruta / "config")

	@property
	def instalados(self) -> Path:
		return self.bin / fichas.NOMBRE_INSTALADOS

	@property
	def linea_base(self) -> Path:
		return self.bin / fichas.NOMBRE_LINEA_BASE

	@property
	def respaldo(self) -> Path:
		return self.bin / "respaldo"

	@property
	def pendiente(self) -> Path:
		return self.bin / ".pendiente"

	@property
	def entrante(self) -> Path:
		return self.bin / ".entrante"

	@property
	def diario(self) -> Path:
		return self.bin / "instalando.json"

	@property
	def integracion(self) -> Path:
		return self.bin / "integracion.json"

	@property
	def temporal(self) -> Path:
		return self.temp / "componentes"

	@property
	def estado(self) -> Path:
		return self.config / NOMBRE_ESTADO


def _entorno(entorno: Entorno | None) -> Entorno:
	return entorno or Entorno.actual()


# ── Fichas ───────────────────────────────────────────────────────────────────


def linea_base(entorno: Entorno | None = None) -> dict:
	"""``linea_base.json`` (lista vacía si falta o no se entiende)."""
	return fichas.leer_o_vacio(_entorno(entorno).linea_base)


def instalados(entorno: Entorno | None = None) -> dict:
	"""``componentes.json``; si no existe, lo que dice la línea base (lo que trae esta versión)."""
	actual = _entorno(entorno)
	if actual.instalados.is_file():
		return fichas.leer_o_vacio(actual.instalados)
	base = linea_base(actual)
	return {"formato": fichas.FORMATO, "componentes": [fichas.sin_campos_de_base(f) for f in base.get("componentes", [])]}


def ficha_instalada(id: str, entorno: Entorno | None = None) -> dict | None:
	return fichas.buscar(instalados(entorno), id)


def ficha_base(id: str, entorno: Entorno | None = None) -> dict | None:
	return fichas.buscar(linea_base(entorno), id)


def guardar_ficha(ficha: dict, entorno: Entorno | None = None) -> None:
	"""Pone ``ficha`` en ``componentes.json`` (atómico); sin los campos que solo van en la línea base."""
	actual = _entorno(entorno)
	with _candado:
		datos = instalados(actual)
		fichas.escribir(actual.instalados, fichas.poner(datos, fichas.sin_campos_de_base(ficha)))


def carpeta_de(id: str, entorno: Entorno | None = None) -> Path:
	"""``data/bin/<carpeta>`` del componente (aunque no exista)."""
	actual = _entorno(entorno)
	ficha = ficha_instalada(id, actual) or ficha_base(id, actual)
	return actual.bin / str((ficha or {}).get("carpeta") or id)


# ── Mantenimiento y daños ────────────────────────────────────────────────────


def entrar_mantenimiento(id: str) -> None:
	with _candado:
		_mantenimiento[id] = _mantenimiento.get(id, 0) + 1
	log.info("Componente %s en mantenimiento", id)


def salir_mantenimiento(id: str) -> None:
	with _candado:
		cuenta = _mantenimiento.get(id, 0) - 1
		if cuenta > 0:
			_mantenimiento[id] = cuenta
		else:
			_mantenimiento.pop(id, None)
	log.info("Componente %s fuera de mantenimiento", id)


@contextmanager
def mantenimiento(id: str) -> Iterator[None]:
	entrar_mantenimiento(id)
	try:
		yield
	finally:
		salir_mantenimiento(id)


def en_mantenimiento(id: str) -> bool:
	with _candado:
		return id in _mantenimiento


def marcar_danados(ids: list[str]) -> None:
	with _candado:
		_danados.clear()
		_danados.update(ids)


def quitar_danado(id: str) -> None:
	with _candado:
		_danados.discard(id)


def esta_danado(id: str) -> bool:
	with _candado:
		return id in _danados


def comprobar_integridad(entorno: Entorno | None = None) -> list[str]:
	"""Comprueba (solo existencia y tamaño, rápido) los archivos de cada ficha instalada (6.8).

	Devuelve los ids dañados y los deja marcados. Un componente opcional que
	falta entero no está dañado: está «Falta».
	"""
	actual = _entorno(entorno)
	danados = []
	for ficha in instalados(actual).get("componentes", []):
		if not isinstance(ficha, dict) or not ficha.get("id"):
			continue
		carpeta = actual.bin / str(ficha.get("carpeta") or ficha["id"])
		if ficha.get("opcional") and not carpeta.is_dir():
			continue
		for archivo in ficha.get("archivos", []):
			ruta = carpeta / str(archivo.get("ruta", ""))
			try:
				correcto = ruta.is_file() and ruta.stat().st_size == int(archivo.get("tamano", -1))
			except OSError:
				correcto = False
			if not correcto:
				log.warning("Componente %s dañado: %s falta o tiene otro tamaño", ficha["id"], archivo.get("ruta"))
				danados.append(ficha["id"])
				break
	marcar_danados(danados)
	return danados


# ── Funciones de destino de 3.7 y 14.9 ────────────────────────────────────────


def _falta(id: str) -> NoAdmitido:
	return NoAdmitido(_("Falta el componente {c}: Opciones, Componentes externos, Restaurar").format(c=id))


def ruta(id: str) -> Path:
	"""Carpeta ``data/bin/<carpeta>`` del componente; ``NoAdmitido`` si falta, está dañado o en mantenimiento.

	Se pide en cada uso y nunca se guarda (6.3).
	"""
	if en_mantenimiento(id):
		raise NoAdmitido(_("El componente {c} se está actualizando; inténtelo dentro de un momento").format(c=id))
	if esta_danado(id):
		raise _falta(id)
	carpeta = carpeta_de(id)
	if not carpeta.is_dir():
		raise _falta(id)
	return carpeta


def ejecutable(id: str, nombre: str) -> Path:
	"""Ruta absoluta de un programa del componente; ``NoAdmitido`` si falta."""
	archivo = ruta(id) / nombre
	if not archivo.is_file():
		raise NoAdmitido(_("Falta {n} del componente {c}: Opciones, Componentes externos, Restaurar").format(n=nombre, c=id))
	return archivo


def disponible(id: str) -> bool:
	try:
		ruta(id)
		return True
	except NoAdmitido:
		return False


def registrar_al_detener(id: str, funcion: Callable[[], bool]) -> None:
	"""Cómo parar un componente para actualizarlo (lo registra su dueño, 6.6): verdadero si lo detuvo."""
	with _candado:
		_al_detener[id] = funcion


def funcion_al_detener(id: str) -> Callable[[], bool] | None:
	with _candado:
		return _al_detener.get(id)


def estado_de(id: str) -> str:
	"""«Instalado», «Falta», «En mantenimiento» o «Dañado» (texto, nunca un icono: 15.2)."""
	if en_mantenimiento(id):
		return _(EN_MANTENIMIENTO)
	if esta_danado(id):
		return _(DANADO)
	return _(INSTALADO) if carpeta_de(id).is_dir() else _(FALTA)


def origen_de(id: str, entorno: Entorno | None = None) -> str:
	"""«Línea base», «Actualizada», «Falta», «Dañado», «En mantenimiento» o «Pendiente de reiniciar» (6.5)."""
	actual = _entorno(entorno)
	if en_mantenimiento(id):
		return _(EN_MANTENIMIENTO)
	if (actual.pendiente / id).is_dir():
		return _("Pendiente de reiniciar")
	instalada = ficha_instalada(id, actual)
	carpeta = actual.bin / str((instalada or {}).get("carpeta") or id)
	if instalada is None or not carpeta.is_dir():
		return _(FALTA)
	if esta_danado(id):
		return _(DANADO)
	base = ficha_base(id, actual)
	if base is not None and fichas.mapa_sumas(base.get("archivos", [])) == fichas.mapa_sumas(instalada.get("archivos", [])):
		return _("Línea base")
	if base is not None and instalada.get("version") == base.get("version") and not instalada.get("asset"):
		return _("Línea base")
	return _("Actualizada")


def lineas_soporte() -> list[str]:
	"""Líneas para «Información para soporte»: id, versión instalada, origen y estado."""
	lineas = []
	for ficha in instalados().get("componentes", []):
		if isinstance(ficha, dict) and ficha.get("id"):
			lineas.append(f"{ficha['id']} {ficha.get('version', '?')} ({origen_de(ficha['id'])}, {estado_de(ficha['id'])})")
	return lineas


# ── estado_componentes.json (6.3) ─────────────────────────────────────────────


def leer_estado(entorno: Entorno | None = None) -> dict[str, Any]:
	"""Última comprobación, versiones nuevas conocidas (por id) y omitidas."""
	ruta_estado = _entorno(entorno).estado
	try:
		datos = json.loads(ruta_estado.read_text(encoding="utf-8"))
		if isinstance(datos, dict):
			datos.setdefault("nuevas", {})
			datos.setdefault("omitidas", {})
			return datos
	except FileNotFoundError:
		pass
	except (OSError, ValueError):
		log.warning("No se pudo leer %s; se empieza de cero", ruta_estado, exc_info=True)
	return {"ultima_comprobacion": 0, "nuevas": {}, "omitidas": {}}


def guardar_estado(datos: dict[str, Any], entorno: Entorno | None = None) -> None:
	with _candado:
		fichas.escribir(_entorno(entorno).estado, datos)


def anotar_comprobacion(nuevas: dict[str, dict], entorno: Entorno | None = None, *, cuando: float | None = None) -> dict[str, Any]:
	"""Guarda el resultado de una comprobación (sustituye las nuevas conocidas)."""
	with _candado:
		datos = leer_estado(entorno)
		datos["ultima_comprobacion"] = time.time() if cuando is None else cuando
		datos["nuevas"] = nuevas
		guardar_estado(datos, entorno)
		return datos


def omitir(id: str, version: str, entorno: Entorno | None = None) -> None:
	"""«Omitir esta versión» (6.5): no se vuelve a ofrecer ni a anunciar."""
	with _candado:
		datos = leer_estado(entorno)
		datos["omitidas"][id] = version
		guardar_estado(datos, entorno)


def olvidar_nueva(id: str, entorno: Entorno | None = None) -> None:
	"""Tras instalar una versión, deja de ofrecerla."""
	with _candado:
		datos = leer_estado(entorno)
		if datos["nuevas"].pop(id, None) is not None:
			guardar_estado(datos, entorno)
