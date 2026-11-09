# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Container Manager (synology.md 4.7): contenedores, proyectos e imágenes FICTICIOS.

Los nombres llegan codificados en JSON (``name="\\"jellyfin\\""``); el servidor ya
los decodifica. Los campos siguen la forma recogida en la investigación, que
está marcada «por verificar» con el NAS real.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from ..comun import ErrorSim, Peticion

_REGISTROS = {
	"jellyfin": ["Starting server on :8096", "Startup complete 0:00:04.112", "Scheduled task: Scan Media Library finished",
		"WebSocket connection from 192.168.1.20"],
	"pihole": ["FTL started", "Blocking status is enabled", "Gravity database updated: 182345 domains", "Query rate: 12/min"],
	"vaultwarden": ["Rocket has launched from http://0.0.0.0:80", "Shutting down"],
	"homeassistant": ["Setting up integration zha", "ERROR (MainThread) Error setting up entry Termostato salón",
		"WARNING Health check failed: timeout after 30 s", "Home Assistant initialized in 18.4 s"],
}


def _contenedor(c: dict[str, Any]) -> dict[str, Any]:
	arriba = f"Up {c['up_dias']} days" if c["status"] == "running" else "Exited (0) 2 days ago"
	return {"name": c["name"], "id": c["id"], "image": c["image"], "status": c["status"], "up_status": arriba,
		"is_package": False, "health": c["health"], "restartCount": 0, "created": 1761900000,
		"State": {"Running": c["status"] == "running", "Status": c["status"]}}


def _buscar(pet: Peticion) -> dict[str, Any]:
	nombre = pet.texto("name")
	contenedor = next((c for c in pet.estado.datos["contenedores"] if c["name"] == nombre), None)
	if contenedor is None:
		raise ErrorSim(120)
	return contenedor


def listar(pet: Peticion) -> dict[str, Any]:
	contenedores = [_contenedor(c) for c in pet.estado.datos["contenedores"]
		if pet.texto("type", "all") != "running" or c["status"] == "running"]
	return {"containers": contenedores, "limit": -1, "offset": 0, "total": len(contenedores)}


def obtener(pet: Peticion) -> dict[str, Any]:
	return {"details": _contenedor(_buscar(pet)), "profile": {"name": pet.texto("name")}}


def _cambiar(pet: Peticion, estado: str, texto: str) -> dict[str, Any]:
	contenedor = _buscar(pet)
	if pet.aplicar:
		contenedor["status"] = estado
		contenedor["up_dias"] = 0
		if estado == "running" and contenedor["health"] == "":
			contenedor["health"] = "healthy"
		pet.estado.anotar_registro("info", f"El contenedor [{contenedor['name']}] {texto}.", pet.sesion.usuario)
	return {"name": contenedor["name"]}


def iniciar(pet: Peticion) -> dict[str, Any]:
	return _cambiar(pet, "running", "se ha iniciado")


def parar(pet: Peticion) -> dict[str, Any]:
	return _cambiar(pet, "stopped", "se ha detenido")


def reiniciar(pet: Peticion) -> dict[str, Any]:
	return _cambiar(pet, "running", "se ha reiniciado")


def registro(pet: Peticion) -> dict[str, Any]:
	contenedor = _buscar(pet)
	lineas = _REGISTROS.get(contenedor["name"], ["(sin registro)"])
	ahora = time.time()
	filas = []
	for repeticion in range(55):
		for indice, texto in enumerate(lineas):
			momento = ahora - (repeticion * len(lineas) + indice) * 97
			filas.append({"created": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(momento)), "docid": str(len(filas) + 1),
				"stream": "stderr" if "ERROR" in texto or "WARNING" in texto else "stdout", "text": texto})
	filas.reverse()
	limite = pet.entero("limit", 200)
	trozo = filas[-limite:] if limite > 0 else filas
	return {"logs": trozo, "offset": 0, "limit": limite, "total": len(filas)}


def recursos(pet: Peticion) -> dict[str, Any]:
	return {"resources": [{"name": c["name"], "cpu": c["cpu"] if c["status"] == "running" else 0.0,
		"memory": c["memoria"] if c["status"] == "running" else 0,
		"memoryPercent": round(100 * c["memoria"] / (10 * 1024 ** 3), 2) if c["status"] == "running" else 0.0}
		for c in pet.estado.datos["contenedores"]]}


def _proyecto(pet: Peticion, p: dict[str, Any]) -> dict[str, Any]:
	ids = [c["id"] for c in pet.estado.datos["contenedores"] if c["name"] in p["contenedores"]]
	return {"id": p["id"], "name": p["name"], "path": f"/volume1/docker/{p['name']}", "share_path": f"/docker/{p['name']}",
		"status": p["status"], "containerIds": ids, "is_package": False, "enable_service_portal": False,
		"created_at": "2026-03-14T14:07:04Z", "updated_at": "2026-10-01T09:00:00Z", "version": 2}


def proyectos(pet: Peticion) -> dict[str, Any]:
	return {p["id"]: _proyecto(pet, p) for p in pet.estado.datos["proyectos"]}


def _buscar_proyecto(pet: Peticion) -> dict[str, Any]:
	identificador = pet.texto("id")
	proyecto = next((p for p in pet.estado.datos["proyectos"] if p["id"] == identificador or p["name"] == identificador), None)
	if proyecto is None:
		raise ErrorSim(120)
	return proyecto


def proyecto(pet: Peticion) -> dict[str, Any]:
	return _proyecto(pet, _buscar_proyecto(pet))


def _proyecto_cambiar(pet: Peticion, estado: str) -> dict[str, Any]:
	proyecto_ = _buscar_proyecto(pet)
	if pet.aplicar:
		proyecto_["status"] = estado
		for contenedor in pet.estado.datos["contenedores"]:
			if contenedor["name"] in proyecto_["contenedores"]:
				contenedor["status"] = "running" if estado == "RUNNING" else "stopped"
		pet.estado.anotar_registro("info", f"El proyecto [{proyecto_['name']}] ha pasado a {estado}.", pet.sesion.usuario)
	return {"id": proyecto_["id"]}


def proyecto_iniciar(pet: Peticion) -> dict[str, Any]:
	return _proyecto_cambiar(pet, "RUNNING")


def proyecto_parar(pet: Peticion) -> dict[str, Any]:
	return _proyecto_cambiar(pet, "STOPPED")


def imagenes(pet: Peticion) -> dict[str, Any]:
	filas = [{"id": "sha256:" + hashlib.sha256(i["repository"].encode()).hexdigest()[:12], "repository": i["repository"],
		"tags": i["tags"], "size": i["size"], "created": 1761000000, "upgradable": i["upgradable"]} for i in pet.estado.datos["imagenes"]]
	return {"images": filas, "limit": -1, "offset": 0, "total": len(filas)}


def version(pet: Peticion) -> dict[str, Any]:
	return {"Version": "24.0.2", "ApiVersion": "1.43", "Os": "linux", "Arch": "amd64"}


MANEJADORES = {
	("SYNO.Docker.Container", "list"): listar,
	("SYNO.Docker.Container", "get"): obtener,
	("SYNO.Docker.Container", "start"): iniciar,
	("SYNO.Docker.Container", "stop"): parar,
	("SYNO.Docker.Container", "restart"): reiniciar,
	("SYNO.Docker.Container.Log", "get"): registro,
	("SYNO.Docker.Container.Resource", "get"): recursos,
	("SYNO.Docker.Project", "list"): proyectos,
	("SYNO.Docker.Project", "get"): proyecto,
	("SYNO.Docker.Project", "start"): proyecto_iniciar,
	("SYNO.Docker.Project", "stop"): proyecto_parar,
	("SYNO.Docker.Image", "list"): imagenes,
	("SYNO.Docker.Utils", "version"): version,
	("SYNO.Docker.Utils", "get"): version,
}
