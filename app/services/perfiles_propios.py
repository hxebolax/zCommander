# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Perfiles propios con nombre (diseño 2.0, 10.2; el ``.zcperfil`` es del bloque CS). Sin wx.

``data/config/perfiles/<nombre>.json``::

	{"version": 1, "nombre": "Clase de los martes", "descripcion": "...", "valores": {"seccion.clave": valor}}

Solo claves de preferencias y teclas: nunca secretos (no están en la
configuración), ni ``ventana.*``, ni el estado interno (asistente hecho,
complementos confiados...). Aplicar un perfil propio escribe todos sus valores
de una vez con ``establecer_varias``.
"""

from __future__ import annotations

import builtins
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import almacen_json, paths

log = logging.getLogger(__name__)

CARPETA = "perfiles"
VERSION = 1
PREFIJOS_EXCLUIDOS = ("ventana.",)
CLAVES_EXCLUIDAS = frozenset({
	"general.asistente_hecho", "sonidos.aviso_inicial_mostrado", "complementos.confiados", "complementos.inhabilitados",
	"accesibilidad.complemento_nvda_ofrecido", "general.arrancar_con_windows",
})
_NO_VALIDO = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorPerfil(ValueError):
	"""Nombre o archivo de perfil no válido (mensaje en español)."""


@dataclass
class PerfilPropio:
	nombre: str
	descripcion: str = ""
	valores: dict[str, Any] = field(default_factory=dict)

	def como_dict(self) -> dict[str, Any]:
		return {"version": VERSION, "nombre": self.nombre, "descripcion": self.descripcion, "valores": dict(self.valores)}


def carpeta() -> Path:
	ruta = paths.ruta_configuracion() / CARPETA
	ruta.mkdir(parents=True, exist_ok=True)
	return ruta


def validar_nombre(nombre: str, reservados: tuple[str, ...] = ()) -> str:
	limpio = " ".join(nombre.split())
	if not limpio:
		raise ErrorPerfil(_("El perfil necesita un nombre"))
	if _NO_VALIDO.search(limpio) or limpio.endswith(".") or len(limpio) > 60:
		raise ErrorPerfil(_("El nombre no puede llevar < > : \" / \\ | ? * ni acabar en punto (60 caracteres como mucho)"))
	if limpio.casefold() in {r.casefold() for r in reservados}:
		raise ErrorPerfil(_("«{n}» es el nombre de un perfil de fábrica").format(n=limpio))
	return limpio


def guardable(clave: str) -> bool:
	return clave not in CLAVES_EXCLUIDAS and not clave.startswith(PREFIJOS_EXCLUIDOS)


def capturar(config: Any, nombre: str, descripcion: str = "") -> PerfilPropio:
	"""Las preferencias y teclas actuales como un perfil."""
	valores = {clave: config.obtener(clave) for clave in config.claves() if guardable(clave)}
	return PerfilPropio(nombre, descripcion, valores)


def _archivo(nombre: str) -> str:
	return f"{nombre}.json"


def listar() -> list[PerfilPropio]:
	resultado = []
	for ruta in sorted(carpeta().glob("*.json")):
		try:
			datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
		except (OSError, ValueError):
			log.warning("Perfil propio dañado: %s", ruta, exc_info=True)
			continue
		if not isinstance(datos, dict) or not isinstance(datos.get("valores"), dict):
			continue
		resultado.append(PerfilPropio(str(datos.get("nombre") or ruta.stem), str(datos.get("descripcion", "")),
			{str(k): v for k, v in datos["valores"].items() if guardable(str(k))}))
	return sorted(resultado, key=lambda p: p.nombre.casefold())


def guardar(perfil: PerfilPropio) -> None:
	almacen_json.escribir(_archivo(perfil.nombre), perfil.como_dict(), carpeta())


def eliminar(nombre: str) -> None:
	for sufijo in ("", ".bak"):
		ruta = carpeta() / (_archivo(nombre) + sufijo)
		if ruta.exists():
			ruta.unlink()


def renombrar(anterior: str, nuevo: str) -> None:
	perfiles = {p.nombre.casefold(): p for p in listar()}
	perfil = perfiles.get(anterior.casefold())
	if perfil is None:
		raise ErrorPerfil(_("No existe el perfil «{n}»").format(n=anterior))
	if nuevo.casefold() != anterior.casefold() and nuevo.casefold() in perfiles:
		raise ErrorPerfil(_("Ya hay un perfil «{n}»").format(n=nuevo))
	perfil.nombre = nuevo
	guardar(perfil)
	if nuevo.casefold() != anterior.casefold() or nuevo != anterior:
		if (carpeta() / _archivo(anterior)).resolve() != (carpeta() / _archivo(nuevo)).resolve():
			eliminar(anterior)


def cambios_al_aplicar(config: Any, perfil: PerfilPropio) -> dict[str, Any]:
	conocidas = set(config.claves())
	return {c: v for c, v in perfil.valores.items() if c in conocidas and config.obtener(c) != v}


def aplicar(config: Any, perfil: PerfilPropio) -> int:
	"""Escribe los valores que cambian; las claves que no valen se saltan (y se registra)."""
	cambios = {}
	for clave, valor in cambios_al_aplicar(config, perfil).items():
		try:
			config.validar(clave, valor)
		except Exception:  # noqa: BLE001 - ErrorValidacion: un valor de otra versión no impide el resto
			log.warning("Perfil %s: valor no válido para %s; se salta", perfil.nombre, clave)
			continue
		cambios[clave] = valor
	if cambios:
		config.establecer_varias(cambios)
	return len(cambios)


def coincide(config: Any, perfil: PerfilPropio) -> bool:
	return not cambios_al_aplicar(config, perfil)
