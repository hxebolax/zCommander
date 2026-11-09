# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Paquetes (synology.md 4.6): los 23 paquetes REALES del NAS, con versiones ficticias."""

from __future__ import annotations

import time
from typing import Any

from ..comun import ErrorSim, Peticion


def _paquete(p: dict[str, Any]) -> dict[str, Any]:
	return {"id": p["id"], "name": p["nombre"], "version": p["version"], "timestamp": 1762000000000,
		"additional": {"status": p["estado"], "startable": p["id"] not in ("FileStation", "StorageManager"),
			"install_type": "", "description": p["descripcion"], "autoupdate": False, "distributor": "Synology Inc."}}


def listar(pet: Peticion) -> dict[str, Any]:
	paquetes = [_paquete(p) for p in pet.estado.datos["paquetes"]]
	return {"packages": paquetes, "total": len(paquetes)}


def _buscar(pet: Peticion) -> dict[str, Any]:
	identificador = pet.texto("id") or pet.texto("name")
	paquete = next((p for p in pet.estado.datos["paquetes"] if p["id"] == identificador), None)
	if paquete is None:
		raise ErrorSim(120)
	return paquete


def obtener(pet: Peticion) -> dict[str, Any]:
	return _paquete(_buscar(pet))


def iniciar(pet: Peticion) -> dict[str, Any]:
	paquete = _buscar(pet)
	if pet.aplicar:
		paquete["estado"] = "running"
		pet.estado.anotar_registro("info", f"El paquete [{paquete['nombre']}] se ha iniciado.", pet.sesion.usuario)
	return {"id": paquete["id"], "status": "running"}


def parar(pet: Peticion) -> dict[str, Any]:
	paquete = _buscar(pet)
	if pet.aplicar:
		paquete["estado"] = "stop"
		pet.estado.anotar_registro("info", f"El paquete [{paquete['nombre']}] se ha detenido.", pet.sesion.usuario)
	return {"id": paquete["id"], "status": "stop"}


def servidor(pet: Peticion) -> dict[str, Any]:
	"""Paquetes disponibles en el centro de paquetes: los instalados con la versión que hay (para ver las actualizaciones)."""
	filas = [{"id": p["id"], "dname": p["nombre"], "version": p.get("actualizable") or p["version"],
		"changelog": "Correcciones y mejoras (texto ficticio)."} for p in pet.estado.datos["paquetes"]]
	return {"packages": filas, "total": len(filas)}


def actualizar(pet: Peticion) -> dict[str, Any]:
	paquete = _buscar(pet)
	nueva = paquete.get("actualizable")
	if not nueva:
		raise ErrorSim(120)
	if pet.aplicar:
		paquete["version"] = nueva
		paquete.pop("actualizable", None)
		pet.estado.anotar_registro("info", f"El paquete [{paquete['nombre']}] se ha actualizado a la versión {nueva}.",
			pet.sesion.usuario)
	return {"id": paquete["id"], "version": nueva, "finished": True, "time": int(time.time())}


MANEJADORES = {
	("SYNO.Core.Package", "list"): listar,
	("SYNO.Core.Package", "get"): obtener,
	("SYNO.Core.Package.Control", "start"): iniciar,
	("SYNO.Core.Package.Control", "stop"): parar,
	("SYNO.Core.Package.Server", "list"): servidor,
	("SYNO.Core.Package.Installation", "upgrade"): actualizar,
}
