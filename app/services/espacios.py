# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Espacios de trabajo (diseño 2.0, 10.9). Sin wx.

Un espacio guarda la disposición completa (pestañas de cada lado con su
carpeta, vista, orden, filtro, columnas, orden de lectura y bloqueo; lado
activo; lados visibles; orientación; salida de órdenes y barra de botones
visibles) y, si se pide, la cesta. ``data/config/espacios.json``::

	{"version": 1, "espacios": [{"nombre": "Proyecto web", "nota": "",
	  "disposicion": {...el formato de sesion.json más «vista»...}, "con_cesta": false}]}

Capturar y restaurar la disposición lo hace la interfaz: ``personalizar_pe``
fija al arrancar las dos funciones con ``fijar_anfitrion``. Así este módulo
sigue sin wx y la fachada ``zc.espacios`` de los complementos (3.7: ``listar``,
``guardar_actual`` y ``abrir``, con su firma de N2) funciona igual.
"""

from __future__ import annotations

import builtins
import copy
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import almacen_json
from app.services.vfs.base import NoAdmitido

log = logging.getLogger(__name__)

ARCHIVO = "espacios.json"
VERSION = 1
POR_DEFECTO: dict[str, Any] = {"version": VERSION, "espacios": []}
#: Nombre del espacio que se guarda solo antes de abrir otro (para volver).
ANTERIOR = "Anterior"

_candado = threading.RLock()
_anfitrion: dict[str, Callable | None] = {"capturar": None, "restaurar": None}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class Espacio:
	nombre: str
	nota: str = ""
	disposicion: dict[str, Any] = field(default_factory=dict)
	con_cesta: bool = False

	def como_dict(self) -> dict[str, Any]:
		return {"nombre": self.nombre, "nota": self.nota, "disposicion": copy.deepcopy(self.disposicion), "con_cesta": self.con_cesta}

	@classmethod
	def desde_dict(cls, datos: Any) -> Espacio | None:
		if not isinstance(datos, dict) or not str(datos.get("nombre", "")).strip() or not isinstance(datos.get("disposicion"), dict):
			return None
		return cls(str(datos["nombre"]).strip(), str(datos.get("nota", "")), copy.deepcopy(datos["disposicion"]),
			bool(datos.get("con_cesta", False)))


def cargar(carpeta: Path | None = None) -> list[Espacio]:
	datos = almacen_json.leer(ARCHIVO, POR_DEFECTO, carpeta)
	resultado: list[Espacio] = []
	for elemento in datos.get("espacios", []) or []:
		espacio = Espacio.desde_dict(elemento)
		if espacio is not None and buscar(resultado, espacio.nombre) is None:
			resultado.append(espacio)
	return resultado


def guardar(espacios: list[Espacio], carpeta: Path | None = None) -> None:
	almacen_json.escribir(ARCHIVO, {"version": VERSION, "espacios": [e.como_dict() for e in espacios]}, carpeta)


def buscar(espacios: list[Espacio], nombre: str) -> Espacio | None:
	clave = nombre.strip().casefold()
	return next((e for e in espacios if e.nombre.casefold() == clave), None)


def poner(espacios: list[Espacio], espacio: Espacio) -> int:
	"""Añade o sustituye (por nombre) y devuelve su posición."""
	for indice, actual in enumerate(espacios):
		if actual.nombre.casefold() == espacio.nombre.casefold():
			espacios[indice] = espacio
			return indice
	espacios.append(espacio)
	return len(espacios) - 1


# ── Enganche con la interfaz ────────────────────────────────────────────────


def fijar_anfitrion(capturar: Callable[[bool], dict[str, Any]] | None, restaurar: Callable[[dict[str, Any], bool], None] | None) -> None:
	"""``capturar(con_cesta) -> disposición`` y ``restaurar(disposición, con_cesta)``; ``None`` al cerrar."""
	_anfitrion["capturar"], _anfitrion["restaurar"] = capturar, restaurar


def _exigir(nombre: str) -> Callable:
	funcion = _anfitrion[nombre]
	if funcion is None:
		raise NoAdmitido(_("Los espacios de trabajo necesitan la ventana de zCommander"))
	return funcion


def capturar(nombre: str, nota: str = "", con_cesta: bool = False) -> Espacio:
	return Espacio(" ".join(nombre.split()), nota, _exigir("capturar")(con_cesta), con_cesta)


def guardar_espacio(espacio: Espacio) -> None:
	with _candado:
		espacios = cargar()
		poner(espacios, espacio)
		guardar(espacios)


def abrir_espacio(espacio: Espacio, guardar_anterior: bool = True) -> None:
	"""Restaura un espacio; antes guarda la disposición actual como «Anterior» (para volver)."""
	restaurar = _exigir("restaurar")
	if guardar_anterior and espacio.nombre.casefold() != _(ANTERIOR).casefold():
		try:
			guardar_espacio(capturar(_(ANTERIOR), _("La disposición antes de abrir «{n}»").format(n=espacio.nombre)))
		except OSError:
			log.exception("No se pudo guardar el espacio Anterior")
	restaurar(copy.deepcopy(espacio.disposicion), espacio.con_cesta)


# ── Fachada zc.espacios (3.7) ───────────────────────────────────────────────


def listar() -> list[str]:
	"""Nombres de los espacios de trabajo guardados."""
	with _candado:
		return [e.nombre for e in cargar()]


def guardar_actual(nombre: str, nota: str = "") -> None:
	"""Guarda la disposición actual con ese nombre (sustituye uno con el mismo nombre)."""
	if not nombre.strip():
		raise NoAdmitido(_("El espacio de trabajo necesita un nombre"))
	guardar_espacio(capturar(nombre, nota))


def abrir(nombre: str) -> None:
	"""Abre un espacio de trabajo guardado."""
	espacio = buscar(cargar(), nombre)
	if espacio is None:
		raise NoAdmitido(_("No existe el espacio de trabajo «{n}»").format(n=nombre))
	abrir_espacio(espacio)
