# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Registros y conexiones (synology.md 4.11): ``SyslogClient`` y ``CurrentConnection`` (no hay Log Center)."""

from __future__ import annotations

import time
from typing import Any

from ..comun import ErrorSim, Peticion


def lista(pet: Peticion) -> dict[str, Any]:
	registros = pet.estado.registros
	tipos = {t.strip().lower() for t in pet.texto("logtype").split(",") if t.strip()}
	clave = pet.texto("keyword").casefold()
	nivel = pet.texto("level")
	filas = [r for r in registros if (not tipos or r["logtype"].lower() in tipos) and (not clave or clave in r["descr"].casefold())
		and (not nivel or r["level"] == nivel)]
	inicio, limite = pet.entero("start", pet.entero("offset", 0)), pet.entero("limit", 50)
	trozo = filas[inicio:inicio + limite] if limite > 0 else filas[inicio:]
	return {"items": [{k: v for k, v in r.items() if k != "orden"} for r in trozo], "total": len(filas)}


def ultimos(pet: Peticion) -> dict[str, Any]:
	return {"logs": [{k: v for k, v in r.items() if k != "orden"} for r in pet.estado.registros[:5]]}


def _conexiones(pet: Peticion) -> list[dict[str, Any]]:
	ahora = time.time()
	filas = []
	for indice, c in enumerate(pet.estado.datos["conexiones"], 1):
		filas.append({"who": c["who"], "type": c["type"], "from": c["from"], "descr": c["descr"],
			"time": time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(ahora - c["minutos"] * 60)), "pid": 12000 + indice,
			"can_be_kicked": True})
	return filas


def conexiones(pet: Peticion) -> dict[str, Any]:
	filas = _conexiones(pet)
	return {"items": filas, "total": len(filas), "systime": time.strftime("%Y/%m/%d %H:%M:%S")}


def expulsar(pet: Peticion) -> dict[str, Any]:
	pedidas = pet.lista("connection") or pet.lista("pid")
	if not pedidas:
		raise ErrorSim(114)
	pids = {str(p.get("pid") if isinstance(p, dict) else p) for p in pedidas}
	actuales = _conexiones(pet)
	quitar = [i for i, c in enumerate(actuales) if str(c["pid"]) in pids]
	if not quitar:
		raise ErrorSim(120)
	if pet.aplicar:
		for indice in sorted(quitar, reverse=True):
			conexion = pet.estado.datos["conexiones"].pop(indice)
			pet.estado.anotar_registro("warn", f"Se ha cerrado la conexión {conexion['type']} de [{conexion['who']}] desde [{conexion['from']}].",
				pet.sesion.usuario)
	return {}


MANEJADORES = {
	("SYNO.Core.SyslogClient.Log", "list"): lista,
	("SYNO.Core.SyslogClient.Status", "latestlog_get"): ultimos,
	("SYNO.Core.CurrentConnection", "get"): conexiones,
	("SYNO.Core.CurrentConnection", "list"): conexiones,
	("SYNO.Core.CurrentConnection", "kick_connection"): expulsar,
}
