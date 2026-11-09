# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Carpetas compartidas y sus permisos (synology.md 4.4)."""

from __future__ import annotations

import uuid
from typing import Any

from ..comun import ErrorSim, Peticion


def _carpeta(c: dict[str, Any]) -> dict[str, Any]:
	return {"name": c["name"], "vol_path": "/volume1", "desc": c["desc"], "hidden": c["hidden"], "encryption": c["encryption"],
		"is_aclmode": True, "enable_recycle_bin": c["recyclebin"], "recycle_bin_admin_only": False,
		"support_snapshot": c["snapshot"], "share_quota": c["quota_mb"], "enable_share_compress": False,
		"uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, "nas-casa/" + c["name"]))}


def listar(pet: Peticion) -> dict[str, Any]:
	carpetas = [_carpeta(c) for c in pet.estado.datos["carpetas"]]
	return {"shares": carpetas, "total": len(carpetas)}


def obtener(pet: Peticion) -> dict[str, Any]:
	nombre = pet.texto("name")
	carpeta = pet.estado.es_compartida(nombre)
	if carpeta is None:
		raise ErrorSim(120)
	return {"shares": [_carpeta(carpeta)]}


def permisos(pet: Peticion) -> dict[str, Any]:
	nombre = pet.texto("name")
	if pet.estado.es_compartida(nombre) is None:
		raise ErrorSim(120)
	tipo = pet.texto("user_group_type", "local_user")
	if tipo == "local_group":
		filas = [{"name": "administrators", "is_readonly": False, "is_writable": True, "is_deny": False, "is_custom": False},
			{"name": "users", "is_readonly": True, "is_writable": False, "is_deny": False, "is_custom": False}]
	else:
		filas = [dict(p, is_custom=False, inherit="-") for p in pet.estado.datos["permisos"].get(nombre, [])]
	return {"items": filas, "total": len(filas)}


def fijar_permisos(pet: Peticion) -> dict[str, Any]:
	nombre = pet.texto("name")
	if pet.estado.es_compartida(nombre) is None:
		raise ErrorSim(120)
	nuevos = pet.lista("permissions")
	if not nuevos:
		raise ErrorSim(114)
	if pet.aplicar:
		actuales = pet.estado.datos["permisos"].setdefault(nombre, [])
		for permiso in nuevos:
			if not isinstance(permiso, dict) or not permiso.get("name"):
				raise ErrorSim(120)
			fila = next((p for p in actuales if p["name"] == permiso["name"]), None)
			valores = {"name": permiso["name"], "is_writable": bool(permiso.get("is_writable")),
				"is_readonly": bool(permiso.get("is_readonly")), "is_deny": bool(permiso.get("is_deny"))}
			if fila is None:
				actuales.append(valores)
			else:
				fila.update(valores)
		pet.estado.anotar_registro("info", f"Se han cambiado los permisos de la carpeta compartida [{nombre}].", pet.sesion.usuario)
	return {}


MANEJADORES = {
	("SYNO.Core.Share", "list"): listar,
	("SYNO.Core.Share", "get"): obtener,
	("SYNO.Core.Share.Permission", "list"): permisos,
	("SYNO.Core.Share.Permission", "set"): fijar_permisos,
}
