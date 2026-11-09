# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Usuarios y grupos (synology.md 4.5). Cambiar una contraseña exige el ``SynoConfirmPWToken`` (13.2)."""

from __future__ import annotations

from typing import Any

from ..comun import ErrorSim, Peticion


def _usuario(u: dict[str, Any]) -> dict[str, Any]:
	return {"name": u["name"], "description": u["description"], "email": u["email"], "expired": u["expired"],
		"groups": list(u["grupos"]), "last_login": u.get("ultimo_acceso", "")}


def listar(pet: Peticion) -> dict[str, Any]:
	usuarios = [_usuario(u) for u in pet.estado.datos["usuarios"]]
	inicio, limite = pet.entero("offset", 0), pet.entero("limit", -1)
	trozo = usuarios[inicio:inicio + limite] if limite > 0 else usuarios[inicio:]
	return {"offset": inicio, "total": len(usuarios), "users": trozo}


def _buscar(pet: Peticion) -> dict[str, Any]:
	nombre = pet.texto("name")
	usuario = next((u for u in pet.estado.datos["usuarios"] if u["name"] == nombre), None)
	if usuario is None:
		raise ErrorSim(120)
	return usuario


def obtener(pet: Peticion) -> dict[str, Any]:
	return {"users": [_usuario(_buscar(pet))]}


def fijar(pet: Peticion) -> dict[str, Any]:
	usuario = _buscar(pet)
	if "password" in pet.params and not pet.texto("SynoConfirmPWToken"):
		raise ErrorSim(105)
	if pet.aplicar:
		if "expired" in pet.params:
			usuario["expired"] = pet.texto("expired")
		if "description" in pet.params:
			usuario["description"] = pet.texto("description")
		if "email" in pet.params:
			usuario["email"] = pet.texto("email")
		if "password" in pet.params:
			pet.estado.anotar_registro("info", f"Se ha cambiado la contraseña de [{usuario['name']}].", pet.sesion.usuario)
	return {"name": usuario["name"]}


def grupos(pet: Peticion) -> dict[str, Any]:
	filas = [dict(g, members=[u["name"] for u in pet.estado.datos["usuarios"] if g["name"] in u["grupos"]])
		for g in pet.estado.datos["grupos_usuarios"]]
	return {"groups": filas, "total": len(filas), "offset": 0}


MANEJADORES = {
	("SYNO.Core.User", "list"): listar,
	("SYNO.Core.User", "get"): obtener,
	("SYNO.Core.User", "set"): fijar,
	("SYNO.Core.Group", "list"): grupos,
}
