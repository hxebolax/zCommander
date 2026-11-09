# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Red (synology.md 4.13): resumen, interfaces, DDNS y QuickConnect (direcciones ficticias)."""

from __future__ import annotations

from typing import Any

from ..comun import Peticion


def resumen(pet: Peticion) -> dict[str, Any]:
	red = pet.estado.datos["red"]
	return {"hostname": red["hostname"], "dns": red["dns"], "gateway": red["gateway"], "workgroup": red["workgroup"],
		"interfaces": [{"id": i["id"], "type": "lan", "mac": i["mac"],
			"ip": [{"address": i["ip"], "netmask": i["mascara"]}] if i["ip"] else []} for i in red["interfaces"]]}


def interfaces(pet: Peticion) -> list[dict[str, Any]]:
	return [{"ifname": i["id"], "type": "lan", "ip": i["ip"], "mask": i["mascara"], "mac": i["mac"], "speed": i["velocidad"],
		"status": i["estado"], "use_dhcp": i["dhcp"], "duplex": True} for i in pet.estado.datos["red"]["interfaces"]]


def ddns(pet: Peticion) -> dict[str, Any]:
	return {"records": list(pet.estado.datos["red"]["ddns"]), "next_update_time": "2026-11-09 06:00"}


def quickconnect(pet: Peticion) -> dict[str, Any]:
	return dict(pet.estado.datos["red"]["quickconnect"])


MANEJADORES = {
	("SYNO.DSM.Network", "list"): resumen,
	("SYNO.Core.Network.Interface", "list"): interfaces,
	("SYNO.Core.DDNS.Record", "list"): ddns,
	("SYNO.Core.QuickConnect", "get_misc_config"): quickconnect,
	("SYNO.Core.QuickConnect", "get"): quickconnect,
}
