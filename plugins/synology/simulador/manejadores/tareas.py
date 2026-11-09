# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tareas programadas (synology.md 4.10): lista, ejecutar ya, activar o desactivar e historial."""

from __future__ import annotations

import time
from typing import Any

from ..comun import ErrorSim, Peticion


def _tarea(t: dict[str, Any]) -> dict[str, Any]:
	return {"id": t["id"], "name": t["name"], "type": t["type"], "enable": t["enable"], "owner": t["owner"],
		"real_owner": t["owner"], "can_run": True, "can_edit": True, "can_delete": True, "action": t["action"],
		"next_trigger_time": t["next_trigger_time"] if t["enable"] else ""}


def listar(pet: Peticion) -> dict[str, Any]:
	tareas = [_tarea(t) for t in pet.estado.datos["tareas"]]
	return {"tasks": tareas, "total": len(tareas)}


def _buscar(pet: Peticion, identificador: Any) -> dict[str, Any]:
	tarea = next((t for t in pet.estado.datos["tareas"] if str(t["id"]) == str(identificador)), None)
	if tarea is None:
		raise ErrorSim(120)
	return tarea


def obtener(pet: Peticion) -> dict[str, Any]:
	return _tarea(_buscar(pet, pet.texto("id")))


def ejecutar(pet: Peticion) -> dict[str, Any]:
	for pedida in pet.lista("tasks"):
		tarea = _buscar(pet, pedida.get("id") if isinstance(pedida, dict) else pedida)
		if pet.aplicar:
			tarea["ultimo"] = time.strftime("%Y-%m-%d %H:%M")
			tarea["resultado"] = "Correcto"
			pet.estado.anotar_registro("info", f"La tarea programada [{tarea['name']}] se ha ejecutado a petición del usuario.",
				pet.sesion.usuario)
	return {}


def activar(pet: Peticion) -> dict[str, Any]:
	for pedida in pet.lista("status"):
		if not isinstance(pedida, dict):
			raise ErrorSim(120)
		tarea = _buscar(pet, pedida.get("id"))
		if pet.aplicar:
			tarea["enable"] = bool(pedida.get("enable"))
	return {}


def historial(pet: Peticion) -> dict[str, Any]:
	filas = [{"id": t["id"], "name": t["name"], "last_run_time": t["ultimo"], "result": t["resultado"]}
		for t in pet.estado.datos["tareas"]]
	return {"list": filas, "total": len(filas)}


MANEJADORES = {
	("SYNO.Core.TaskScheduler", "list"): listar,
	("SYNO.Core.TaskScheduler", "get"): obtener,
	("SYNO.Core.TaskScheduler", "run"): ejecutar,
	("SYNO.Core.TaskScheduler", "set_enable"): activar,
	("SYNO.Core.TaskScheduler", "get_history_status_list"): historial,
}
