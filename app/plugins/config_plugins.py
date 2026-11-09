# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Configuración propia de cada complemento (diseño 2.0, 3.6). Sin wx.

Cada complemento con ``[[configuracion]]`` tiene su propia ``Configuracion``
(la clase de la 1.x) en ``data/config/plugins/<id>.json``, con la sección
única ``ajustes``, valores por defecto y reglas construidos desde el
manifiesto: una configuración dañada de un complemento no toca la de
zCommander, y desinstalar puede borrarla.

Nombre completo de una clave: ``plugin.<id>.<clave>``; se separa por el
ÚLTIMO punto (todo lo que hay entre «plugin.» y el último punto es el id).
``ConfigPlugins`` resuelve esos nombres para Preferencias, copias y macros.
"""

from __future__ import annotations

import builtins
import logging
import threading
from pathlib import Path
from typing import Any

from app.core import paths
from app.core.configuracion import Configuracion, Regla

log = logging.getLogger(__name__)

SECCION = "ajustes"
PREFIJO = "plugin."


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def separar_clave(clave_completa: str) -> tuple[str, str]:
	"""``plugin.zc.reproductor.salto_corto_s`` → (``zc.reproductor``, ``salto_corto_s``)."""
	if not clave_completa.startswith(PREFIJO) or clave_completa.count(".") < 3:
		raise ValueError(_("«{c}» no es una clave de complemento (plugin.<id>.<clave>)").format(c=clave_completa))
	resto = clave_completa[len(PREFIJO):]
	id_complemento, _punto, clave = resto.rpartition(".")
	return id_complemento, clave


def clave_completa(id_complemento: str, clave: str) -> str:
	return f"{PREFIJO}{id_complemento}.{clave}"


def _reglas(declaraciones: list[dict]) -> dict[str, Regla]:
	reglas = {}
	for declaracion in declaraciones:
		minimo, maximo = declaracion.get("minimo"), declaracion.get("maximo")
		opciones = tuple(o[0] for o in declaracion.get("opciones", []) if isinstance(o, list) and o) or None
		if minimo is not None or maximo is not None or opciones:
			reglas[f"{SECCION}.{declaracion['clave']}"] = Regla(minimo=minimo, maximo=maximo, opciones=opciones)
	return reglas


def crear(id_complemento: str, declaraciones: list[dict], carpeta: Path | None = None) -> Configuracion:
	"""La ``Configuracion`` de un complemento con los ``[[configuracion]]`` de su manifiesto."""
	carpeta = paths.ruta_config_plugins() if carpeta is None else Path(carpeta)
	por_defecto = {SECCION: {d["clave"]: d.get("defecto") for d in declaraciones if "clave" in d}}
	return Configuracion(carpeta / f"{id_complemento}.json", por_defecto=por_defecto, reglas=_reglas(declaraciones),
		version=1, migraciones={})


class ConfigPlugins:
	"""Registro global de las configuraciones de los complementos, por nombre completo."""

	def __init__(self) -> None:
		self._candado = threading.Lock()
		self._declaraciones: dict[str, list[dict]] = {}
		self._abiertas: dict[str, Configuracion] = {}

	def declarar(self, id_complemento: str, declaraciones: list[dict]) -> None:
		with self._candado:
			self._declaraciones[id_complemento] = [dict(d) for d in declaraciones if isinstance(d, dict) and "clave" in d]
			self._abiertas.pop(id_complemento, None)

	def quitar(self, id_complemento: str) -> None:
		with self._candado:
			self._declaraciones.pop(id_complemento, None)
			self._abiertas.pop(id_complemento, None)

	def vaciar(self) -> None:
		with self._candado:
			self._declaraciones.clear()
			self._abiertas.clear()

	def de(self, id_complemento: str) -> Configuracion:
		"""La ``Configuracion`` del complemento (se crea al pedirla)."""
		with self._candado:
			if id_complemento not in self._abiertas:
				self._abiertas[id_complemento] = crear(id_complemento, self._declaraciones.get(id_complemento, []))
			return self._abiertas[id_complemento]

	def declaraciones(self, id_complemento: str) -> list[dict]:
		with self._candado:
			return list(self._declaraciones.get(id_complemento, []))

	def claves(self) -> list[str]:
		"""Nombres completos de todas las claves declaradas."""
		with self._candado:
			return [clave_completa(i, d["clave"]) for i, lista in sorted(self._declaraciones.items()) for d in lista]

	def obtener(self, clave: str) -> Any:
		id_complemento, corta = separar_clave(clave)
		return self.de(id_complemento).obtener(f"{SECCION}.{corta}")

	def establecer(self, clave: str, valor: Any) -> bool:
		id_complemento, corta = separar_clave(clave)
		return bool(self.de(id_complemento).establecer(f"{SECCION}.{corta}", valor))


_registro = ConfigPlugins()


def registro() -> ConfigPlugins:
	return _registro
