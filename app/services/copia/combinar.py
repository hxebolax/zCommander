# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Combinar lo de una copia con lo actual y las huellas de servidores (diseño 2.0, 7.6). Sin wx.

«Combinar» añade lo que no existe y conserva lo actual:

- En las listas con identidad (favoritos por ruta, conexiones por ``id``,
  macros, alias y reglas por nombre, asociaciones por patrón, entradas del
  menú por etiqueta) se añaden los elementos de la copia que no están.
- En el resto de JSON se añaden las claves que faltan, sin tocar las que hay.

Las listas que hacen ejecutar órdenes (menú de usuario, asociaciones, alias y
macros) pasan antes por ``filtrar_ejecutables``: lo no marcado de la copia no
entra, y con «Sustituir» se conserva lo actual de esos elementos.

Las huellas (``known_hosts`` y ``hosts_conocidos.json``) nunca se añaden en
bloque al combinar: cada una nueva o distinta se confirma una a una, porque
una huella aceptada permite suplantar ese servidor.
"""

from __future__ import annotations

import base64
import builtins
import copy
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Archivo → (clave de la lista, campo que identifica cada elemento).
LISTAS: dict[str, tuple[str, str]] = {
	"config/favoritos.json": ("favoritos", "ruta"),
	"config/conexiones.json": ("sitios", "id"),
	"config/macros.json": ("macros", "nombre"),
	"config/asociaciones.json": ("reglas", "patron"),
	"config/alias.json": ("alias", "nombre"),
	"config/reglas.json": ("reglas", "nombre"),
	"config/menu_usuario.json": ("entradas", "etiqueta"),
	"config/espacios.json": ("espacios", "nombre"),
}

#: Listas cuyos elementos hacen ejecutar programas u órdenes (7.2): archivo → prefijo del id del elemento.
LISTAS_EJECUTABLES: dict[str, str] = {
	"config/menu_usuario.json": "menu_usuario",
	"config/asociaciones.json": "asociaciones",
	"config/alias.json": "alias",
	"config/macros.json": "macros",
}

CAMPOS_ID = ("id", "nombre", "ruta", "patron", "etiqueta")


def _clave(valor: Any) -> Any:
	if isinstance(valor, str):
		limpio = valor.strip()
		if len(limpio) > 3 and "://" not in limpio:
			limpio = limpio.rstrip("\\/")
		return limpio.casefold()
	return json.dumps(valor, sort_keys=True, ensure_ascii=False)


def _campo_comun(*listas: list) -> str | None:
	elementos = [e for lista in listas for e in lista]
	if not elementos or not all(isinstance(e, dict) for e in elementos):
		return None
	return next((c for c in CAMPOS_ID if all(c in e for e in elementos)), None)


def combinar_listas(actual: list, de_copia: list, campo: str | None = None) -> list:
	"""Lo actual y, detrás, lo de la copia que no está (por ``campo`` o por igualdad)."""
	resultado = copy.deepcopy(actual)
	campo = campo or _campo_comun(actual, de_copia)
	if campo:
		vistos = {_clave(e.get(campo)) for e in actual if isinstance(e, dict)}
		for elemento in de_copia:
			if isinstance(elemento, dict) and _clave(elemento.get(campo)) not in vistos:
				resultado.append(copy.deepcopy(elemento))
				vistos.add(_clave(elemento.get(campo)))
		return resultado
	vistos_valores = [_clave(e) for e in actual]
	for elemento in de_copia:
		if _clave(elemento) not in vistos_valores:
			resultado.append(copy.deepcopy(elemento))
			vistos_valores.append(_clave(elemento))
	return resultado


def combinar_json(actual: Any, de_copia: Any, archivo: str = "") -> Any:
	"""Combina dos JSON: añade lo que falta y conserva lo actual."""
	lista = LISTAS.get(archivo)
	if isinstance(actual, dict) and isinstance(de_copia, dict):
		resultado = copy.deepcopy(actual)
		for clave, valor in de_copia.items():
			if clave not in resultado:
				resultado[clave] = copy.deepcopy(valor)
			elif isinstance(resultado[clave], list) and isinstance(valor, list):
				campo = lista[1] if lista and clave == lista[0] else None
				resultado[clave] = combinar_listas(resultado[clave], valor, campo)
			elif isinstance(resultado[clave], dict) and isinstance(valor, dict):
				resultado[clave] = combinar_json(resultado[clave], valor)
		return resultado
	if isinstance(actual, list) and isinstance(de_copia, list):
		return combinar_listas(actual, de_copia)
	return copy.deepcopy(actual)


def elementos_lista(datos: Any, archivo: str) -> list[dict]:
	clave, _campo = LISTAS.get(archivo, ("", ""))
	lista = datos.get(clave) if isinstance(datos, dict) else None
	return [e for e in lista if isinstance(e, dict)] if isinstance(lista, list) else []


def id_elemento(archivo: str, elemento: dict) -> str:
	"""Id del elemento ejecutable: «macros:Fotos a la copia», «alias:ll»."""
	prefijo = LISTAS_EJECUTABLES[archivo]
	return f"{prefijo}:{elemento.get(LISTAS[archivo][1], '')}"


def filtrar_ejecutables(de_copia: Any, archivo: str, excluidos: set[str], actual: Any = None,
		sustituir: bool = False) -> Any:
	"""Quita de la copia los elementos ejecutables no marcados.

	Con ``sustituir``, los elementos actuales con el mismo id que uno no marcado se
	conservan (lo no marcado «se conserva lo actual», 7.2).
	"""
	if archivo not in LISTAS_EJECUTABLES or not isinstance(de_copia, dict):
		return copy.deepcopy(de_copia)
	clave, campo = LISTAS[archivo]
	resultado = copy.deepcopy(de_copia)
	originales = elementos_lista(de_copia, archivo)
	quitados = {_clave(e.get(campo)) for e in originales if id_elemento(archivo, e) in excluidos}
	resultado[clave] = [e for e in originales if _clave(e.get(campo)) not in quitados]
	if sustituir and quitados:
		for elemento in elementos_lista(actual, archivo):
			if _clave(elemento.get(campo)) in quitados:
				resultado[clave].append(copy.deepcopy(elemento))
	return resultado


def iguales(a: Any, b: Any) -> bool:
	return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


# ── Huellas de servidores ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Huella:
	"""Una huella de la copia nueva o distinta de la de este equipo."""

	id: str
	servidor: str
	puerto: int
	tipo: str
	huella: str
	distinta: bool

	def pregunta(self) -> str:
		if self.distinta:
			texto = _("La copia trae una huella DISTINTA de la que este equipo conoce para {s}, puerto {p} ({t} {h}). "
				"Si la acepta, zCommander confiará en ese servidor con esa clave. ¿Aceptarla?")
		else:
			texto = _("La copia trae esta huella para {s}, puerto {p} ({t} {h}). ¿Aceptarla?")
		return texto.format(s=self.servidor, p=self.puerto, t=self.tipo, h=self.huella)


def _huella_ssh(clave_b64: str) -> str:
	try:
		datos = base64.b64decode(clave_b64, validate=True)
	except ValueError:
		return clave_b64[:20]
	return "SHA256:" + base64.b64encode(hashlib.sha256(datos).digest()).decode("ascii").rstrip("=")


def _lineas_known_hosts(contenido: bytes) -> list[tuple[tuple[str, str] | None, str]]:
	"""(clave (hosts, tipo) o None para comentarios, línea)."""
	resultado = []
	for linea in contenido.decode("utf-8", errors="replace").splitlines():
		trozos = linea.split()
		if len(trozos) >= 3 and not linea.lstrip().startswith("#"):
			resultado.append(((trozos[0], trozos[1]), linea))
		elif linea.strip():
			resultado.append((None, linea))
	return resultado


def _servidor_y_puerto(hosts: str) -> tuple[str, int]:
	primero = hosts.split(",")[0]
	if primero.startswith("|1|"):
		return _("un servidor con el nombre oculto"), 22
	if primero.startswith("[") and "]:" in primero:
		nombre, _sep, puerto = primero[1:].partition("]:")
		return nombre, int(puerto) if puerto.isdigit() else 22
	return primero, 22


def huellas_ssh(copia: bytes | None, local: bytes | None) -> list[Huella]:
	if not copia:
		return []
	conocidas = {c: linea for c, linea in _lineas_known_hosts(local or b"") if c is not None}
	resultado = []
	for clave, linea in _lineas_known_hosts(copia):
		if clave is None:
			continue
		actual = conocidas.get(clave)
		if actual is not None and actual.split()[2] == linea.split()[2]:
			continue
		servidor, puerto = _servidor_y_puerto(clave[0])
		resultado.append(Huella(f"ssh:{clave[0]} {clave[1]}", servidor, puerto, clave[1], _huella_ssh(linea.split()[2]),
			actual is not None))
	return resultado


def combinar_known_hosts(local: bytes | None, copia: bytes, aceptadas: set[str]) -> bytes:
	"""Las líneas de este equipo con las aceptadas de la copia añadidas o sustituidas."""
	lineas = _lineas_known_hosts(local or b"")
	for clave, linea in _lineas_known_hosts(copia):
		if clave is None or f"ssh:{clave[0]} {clave[1]}" not in aceptadas:
			continue
		posicion = next((i for i, (c, _l) in enumerate(lineas) if c == clave), None)
		if posicion is None:
			lineas.append((clave, linea))
		else:
			lineas[posicion] = (clave, linea)
	return ("\n".join(linea for _c, linea in lineas) + "\n").encode("utf-8") if lineas else b""


def _huellas_tls(datos: Any) -> dict[str, str]:
	huellas = datos.get("huellas") if isinstance(datos, dict) else None
	return {str(k): str(v) for k, v in huellas.items() if isinstance(v, str)} if isinstance(huellas, dict) else {}


def huellas_tls(copia: Any, local: Any) -> list[Huella]:
	conocidas = _huellas_tls(local)
	resultado = []
	for servidor, huella in sorted(_huellas_tls(copia).items()):
		actual = conocidas.get(servidor.lower())
		if actual == huella:
			continue
		nombre, _sep, puerto = servidor.rpartition(":")
		if not nombre:
			nombre, puerto = servidor, "21"
		resultado.append(Huella(f"tls:{servidor.lower()}", nombre, int(puerto) if puerto.isdigit() else 21, "TLS", huella,
			actual is not None))
	return resultado


def combinar_tls(local: Any, copia: Any, aceptadas: set[str]) -> dict:
	resultado = copy.deepcopy(local) if isinstance(local, dict) else {"version": 1}
	huellas = _huellas_tls(resultado)
	for servidor, huella in _huellas_tls(copia).items():
		if f"tls:{servidor.lower()}" in aceptadas:
			huellas[servidor.lower()] = huella
	resultado["huellas"] = huellas
	resultado.setdefault("version", 1)
	return resultado
