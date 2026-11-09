# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Actualizaciones de DSM (synology.md 4.16). Escenario configurable: hay o no hay actualización."""

from __future__ import annotations

from typing import Any

from ..comun import ErrorSim, Peticion


def comprobar(pet: Peticion) -> dict[str, Any]:
	datos = pet.estado.datos["actualizacion"]
	if not datos["disponible"]:
		return {"update": {"available": False}}
	nano = int(datos["version"].rsplit(" ", 1)[-1]) if "Update" in datos["version"] else 0
	return {"update": {"available": True, "type": datos["tipo"], "version": datos["version"], "reboot": datos["reinicio"],
		"restart": "some", "version_details": {"os_name": "DSM", "major": 7, "minor": 3, "micro": 2, "buildnumber": 86009,
			"nano": nano}}}


def ajustes(pet: Peticion) -> dict[str, Any]:
	datos = pet.estado.datos["actualizacion"]
	return {"autoupdate_type": datos["auto"], "upgrade_type": "auto", "schedule": {"hour": 4, "minute": 0},
		"last_check": datos["comprobado"]}


def descargar(pet: Peticion) -> dict[str, Any]:
	if not pet.estado.datos["actualizacion"]["disponible"]:
		raise ErrorSim(120)
	return {"taskid": pet.estado.nuevo_id("DSMDownload_")}


def progreso_descarga(pet: Peticion) -> dict[str, Any]:
	return {"progress": 100, "status": "finished"}


def instalar(pet: Peticion) -> dict[str, Any]:
	datos = pet.estado.datos["actualizacion"]
	if not datos["disponible"]:
		raise ErrorSim(120)
	if pet.aplicar:
		pet.estado.sistema["version_string"] = "DSM " + datos["version"]
		datos["disponible"] = False
		pet.estado.reinicios += 1
		pet.estado.sesiones.clear()
		pet.estado.anotar_registro("warn", f"Se ha instalado {datos['version']} y el sistema se ha reiniciado.", pet.sesion.usuario)
	return {}


def estado_instalacion(pet: Peticion) -> dict[str, Any]:
	return {"status": "none", "progress": 0}


MANEJADORES = {
	("SYNO.Core.Upgrade.Server", "check"): comprobar,
	("SYNO.Core.Upgrade.Setting", "get"): ajustes,
	("SYNO.Core.Upgrade.Server.Download", "start"): descargar,
	("SYNO.Core.Upgrade.Server.Download", "progress"): progreso_descarga,
	("SYNO.Core.Upgrade", "start"): instalar,
	("SYNO.Core.Upgrade", "status"): estado_instalacion,
}
