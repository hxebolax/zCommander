# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Servidores NAS guardados (diseño 2.0, 13.3): ``<datos del complemento>/servidores.json``.

Las contraseñas y el ``device_id`` de la verificación en dos pasos NUNCA van
aquí: van en el almacén de secretos (DPAPI) como
``plugin:zc.synology:<id>:contrasena`` y ``plugin:zc.synology:<id>:device_id``.
La escritura es atómica (temporal y ``os.replace``) para que un corte no deje
el archivo a medias.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

log = logging.getLogger("zcplugins.zc.synology.servidores")

VERSION = 1
NOMBRE_ARCHIVO = "servidores.json"
ID_DEMOSTRACION = "demo"
_ID_VALIDO = re.compile(r"[^a-z0-9_]+")


@dataclass
class ServidorNAS:
	"""Un NAS que la persona ha dado de alta. ``solo_lectura`` empieza siempre en verdadero (13.1)."""

	id: str
	nombre: str
	host: str
	puerto: int = 5001
	https: bool = True
	huella: str = ""
	ca_propia: str = ""
	usuario: str = ""
	solo_lectura: bool = True
	recordar_contrasena: bool = True
	demostracion: bool = False

	@property
	def es_local(self) -> bool:
		"""127.0.0.1 o ``localhost``: el único caso en que se admite HTTP con contraseña (el simulador, 13.1)."""
		return self.host.strip().lower() in ("127.0.0.1", "localhost", "::1")

	@property
	def direccion(self) -> str:
		return f"synology://{self.id}/"

	def descripcion(self) -> str:
		protocolo = "HTTPS" if self.https else "HTTP"
		modo = "solo lectura" if self.solo_lectura else "cambios permitidos"
		return f"{self.host}:{self.puerto} por {protocolo}, usuario {self.usuario or 'sin indicar'}, {modo}"

	@classmethod
	def desde_dict(cls, datos: dict[str, Any]) -> ServidorNAS:
		conocidos = {f.name for f in fields(cls)}
		valores = {k: v for k, v in datos.items() if k in conocidos}
		servidor = cls(**valores)
		servidor.puerto = int(servidor.puerto)
		return servidor


def id_desde_nombre(nombre: str, existentes: set[str] | frozenset[str] = frozenset()) -> str:
	"""«NAS de casa» → «nas_de_casa» (sin repetir; el id va en las direcciones ``synology://<id>/``)."""
	base = _ID_VALIDO.sub("_", nombre.strip().lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))).strip("_") or "nas"
	if base[0].isdigit():
		base = "nas_" + base
	candidato, numero = base, 2
	while candidato in existentes or candidato == ID_DEMOSTRACION:
		candidato, numero = f"{base}_{numero}", numero + 1
	return candidato


class AlmacenServidores:
	"""Lista de servidores en disco. Segura entre hilos (la lee el hilo del selector de unidades)."""

	def __init__(self, carpeta: Path | Callable[[], Path]) -> None:
		# La carpeta puede llegar como función: así activar el complemento no crea carpetas en data/ (13.3).
		self._carpeta = carpeta
		self._candado = threading.RLock()
		self._servidores: list[ServidorNAS] | None = None

	@property
	def ruta(self) -> Path:
		carpeta = self._carpeta() if callable(self._carpeta) else self._carpeta
		return Path(carpeta) / NOMBRE_ARCHIVO

	def _cargar(self) -> list[ServidorNAS]:
		if not self.ruta.is_file():
			return []
		try:
			datos = json.loads(self.ruta.read_text(encoding="utf-8"))
		except (OSError, ValueError):
			log.warning("No se pudo leer %s; se aparta y se empieza sin servidores", self.ruta, exc_info=True)
			try:
				os.replace(self.ruta, self.ruta.with_suffix(".json.dañado"))
			except OSError:
				log.debug("No se pudo apartar el archivo dañado", exc_info=True)
			return []
		servidores = []
		for fila in datos.get("servidores", []) if isinstance(datos, dict) else []:
			try:
				servidores.append(ServidorNAS.desde_dict(fila))
			except (TypeError, ValueError):
				log.warning("Servidor no válido en %s: %r", self.ruta, fila)
		return servidores

	def todos(self) -> list[ServidorNAS]:
		with self._candado:
			if self._servidores is None:
				self._servidores = self._cargar()
			return [replace(s) for s in self._servidores]

	def obtener(self, id_servidor: str) -> ServidorNAS | None:
		return next((s for s in self.todos() if s.id == id_servidor), None)

	def guardar(self, servidor: ServidorNAS) -> None:
		"""Añade o sustituye (por id). El NAS de demostración nunca se guarda."""
		if servidor.demostracion:
			return
		with self._candado:
			lista = self.todos()
			lista = [servidor if s.id == servidor.id else s for s in lista]
			if not any(s.id == servidor.id for s in lista):
				lista.append(servidor)
			self._escribir(lista)

	def eliminar(self, id_servidor: str) -> None:
		with self._candado:
			self._escribir([s for s in self.todos() if s.id != id_servidor])

	def _escribir(self, lista: list[ServidorNAS]) -> None:
		self.ruta.parent.mkdir(parents=True, exist_ok=True)
		temporal = self.ruta.with_suffix(".json.tmp")
		contenido = {"version": VERSION, "servidores": [asdict(s) for s in lista if not s.demostracion]}
		temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent="\t"), encoding="utf-8")
		os.replace(temporal, self.ruta)
		self._servidores = [replace(s) for s in lista]
