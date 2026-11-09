# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Synology Drive (synology.md 4.8): estado del servicio y equipos conectados (forma por verificar con el NAS real)."""

from __future__ import annotations

import time
from typing import Any

from ..comun import Peticion


def estado(pet: Peticion) -> dict[str, Any]:
	drive = pet.estado.datos["drive"]
	return {"status": drive["estado"], "version": drive["version"], "is_activated": True}


def resumen(pet: Peticion) -> dict[str, Any]:
	equipos = pet.estado.datos["drive"]["equipos"]
	return {"total": len(equipos), "desktop": sum(1 for e in equipos if "Windows" in e["client_type"]),
		"mobile": sum(1 for e in equipos if "Android" in e["client_type"] or "iOS" in e["client_type"]),
		"team_folders": len(pet.estado.datos["drive"]["carpetas_equipo"])}


def conexiones(pet: Peticion) -> dict[str, Any]:
	ahora = time.time()
	filas = [{"device_name": e["device_name"], "client_type": e["client_type"], "user_name": e["user"], "ip_address": e["ip"],
		"status": e["status"], "last_connected": time.strftime("%Y-%m-%d %H:%M", time.localtime(ahora - e["minutos"] * 60))}
		for e in pet.estado.datos["drive"]["equipos"]]
	return {"items": filas, "total": len(filas)}


MANEJADORES = {
	("SYNO.SynologyDrive", "get_status"): estado,
	("SYNO.SynologyDrive.Connection", "summary"): resumen,
	("SYNO.SynologyDrive.Connection", "list"): conexiones,
}
