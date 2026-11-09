# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Seguridad (synology.md 4.14): Asesor, accesos, IP bloqueadas y certificados (el de fábrica caduca en 60 días)."""

from __future__ import annotations

import time
from typing import Any

from ..comun import ErrorSim, Peticion


_MESES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _fecha_openssl(marca: float) -> str:
	"""«Jan  1 00:00:00 2027 GMT», en inglés como OpenSSL, sin depender del idioma del sistema."""
	t = time.gmtime(marca)
	return f"{_MESES[t.tm_mon - 1]} {t.tm_mday:2d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d} {t.tm_year} GMT"


def asesor(pet: Peticion) -> dict[str, Any]:
	filas = pet.estado.datos["seguridad"]["asesor"]
	return {"items": {f["categoria"]: {"title": f["nombre"], "failSeverity": f["nivel"], "description": f["texto"]} for f in filas},
		"lastScanTime": time.strftime("%Y-%m-%d %H:%M"), "sysProgress": 100, "sysStatus": "done"}


def analizar(pet: Peticion) -> dict[str, Any]:
	pet.estado.anotar_registro("info", "El Asesor de seguridad ha empezado un análisis.", pet.sesion.usuario if pet.sesion else "")
	return {"started": True}


def accesos(pet: Peticion) -> dict[str, Any]:
	ahora = time.time()
	filas = [{"user": a["user"], "ip": a["ip"], "time": int(ahora - a["minutos"] * 60), "result": a["resultado"],
		"location": a["pais"]} for a in pet.estado.datos["seguridad"]["accesos"]]
	return {"items": filas, "total": len(filas)}


def bloqueadas(pet: Peticion) -> dict[str, Any]:
	ahora = time.time()
	filas = [{"ip": b["ip"], "type": b["type"], "recordTime": int(ahora - b["minutos"] * 60), "expireTime": 0, "location": b["location"]}
		for b in pet.estado.datos["seguridad"]["ip_bloqueadas"] if pet.texto("type", "deny") in ("", b["type"])]
	return {"rules": filas, "total": len(filas)}


def desbloquear(pet: Peticion) -> dict[str, Any]:
	ips = {str(i) for i in pet.lista("ip")}
	if not ips:
		raise ErrorSim(114)
	lista = pet.estado.datos["seguridad"]["ip_bloqueadas"]
	if not any(b["ip"] in ips for b in lista):
		raise ErrorSim(120)
	if pet.aplicar:
		pet.estado.datos["seguridad"]["ip_bloqueadas"] = [b for b in lista if b["ip"] not in ips]
		for ip in ips:
			pet.estado.fallos_login.pop(ip, None)
			pet.estado.anotar_registro("info", f"Se ha desbloqueado la dirección [{ip}].", pet.sesion.usuario)
	return {}


def certificados(pet: Peticion) -> dict[str, Any]:
	filas = []
	for c in pet.estado.datos["seguridad"]["certificados"]:
		hasta = time.time() + c["caduca_en_dias"] * 86400
		filas.append({"id": c["id"], "desc": c["desc"], "is_default": c["is_default"], "is_broken": False,
			"issuer": {"common_name": c["emisor"], "organization": "Synology Inc."},
			"subject": {"common_name": c["sujeto"], "sub_alt_name": [c["sujeto"]]},
			"valid_from": _fecha_openssl(hasta - 365 * 86400), "valid_till": _fecha_openssl(hasta), "renewable": False,
			"services": [{"display_name": s, "service": s.lower().replace(" ", "_")} for s in c["servicios"]]})
	return {"certificates": filas}


MANEJADORES = {
	("SYNO.Core.SecurityScan.Status", "system_get"): asesor,
	("SYNO.Core.SecurityScan.Operation", "start"): analizar,
	("SYNO.SecurityAdvisor.LoginActivity", "list"): accesos,
	("SYNO.Core.Security.AutoBlock.Rules", "list"): bloqueadas,
	("SYNO.Core.Security.AutoBlock.Rules", "delete"): desbloquear,
	("SYNO.Core.Certificate.CRT", "list"): certificados,
}
