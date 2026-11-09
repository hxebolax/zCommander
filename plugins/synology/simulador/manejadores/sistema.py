# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sistema y salud (synology.md 4.1 y 4.16): información, utilización, ventilador, apagar y reiniciar."""

from __future__ import annotations

import time
from typing import Any

from ..comun import ErrorSim, Peticion


def _encendido(segundos: int) -> str:
	horas, resto = divmod(int(segundos), 3600)
	minutos, segundos = divmod(resto, 60)
	return f"{horas}:{minutos:02d}:{segundos:02d}"


def system_info(pet: Peticion) -> dict[str, Any]:
	sistema, red = pet.estado.sistema, pet.estado.datos["red"]
	tipo = pet.texto("type")
	if tipo == "network":
		return {"hostname": red["hostname"], "dns_primary": red["dns"][0], "gateway": red["gateway"], "workgroup": red["workgroup"],
			"nif": [{"id": i["id"], "ip": i["ip"], "mask": i["mascara"], "mac": i["mac"].replace("-", ":").lower(),
				"speed": i["velocidad"], "status": i["estado"], "type": "lan"} for i in red["interfaces"]]}
	if tipo == "storage":
		return {
			"hdd_info": [{"diskno": d["nombre"], "model": d["modelo"], "status": d["estado"], "temp": d["temp"],
				"capacity": d["tamano"], "volume": "volume_1"} for d in pet.estado.datos["discos"]],
			"vol_info": [{"name": v["id"], "status": v["estado"], "total_size": v["total"], "used_size": v["usado"], "desc": ""}
				for v in pet.estado.datos["volumenes"]],
		}
	return {
		"model": sistema["modelo"], "cpu_vendor": sistema["cpu_vendor"], "cpu_family": sistema["cpu_family"],
		"cpu_series": sistema["cpu_series"], "cpu_cores": sistema["cpu_cores"], "cpu_clock_speed": sistema["cpu_clock_speed"],
		"ram_size": sistema["ram_mb"], "firmware_ver": sistema["version_string"], "firmware_date": sistema["firmware_date"],
		"serial": sistema["serie"], "sys_temp": sistema["temperatura"], "temperature_warning": sistema["temperatura"] >= 60,
		"sys_tempwarn": sistema["temperatura"] >= 60, "up_time": _encendido(pet.estado.encendido_s()),
		"time": time.strftime("%Y-%m-%d %H:%M:%S"), "time_zone": sistema["zona"], "time_zone_desc": sistema["zona_desc"],
		"enabled_ntp": True, "ntp_server": sistema["ntp"], "support_esata": "no", "sata_dev": [], "usb_dev": [],
	}


def dsm_info(pet: Peticion) -> dict[str, Any]:
	sistema = pet.estado.sistema
	return {"model": sistema["modelo"], "ram": sistema["ram_mb"], "serial": sistema["serie"], "temperature": sistema["temperatura"],
		"temperature_warn": sistema["temperatura"] >= 60, "uptime": pet.estado.encendido_s(), "version": sistema["version"],
		"version_string": sistema["version_string"], "codepage": "spn", "time": time.strftime("%a %b %d %H:%M:%S %Y")}


def apagar(pet: Peticion) -> dict[str, Any]:
	if pet.version != 1:
		raise ErrorSim(103)
	if pet.aplicar:
		pet.estado.anotar_registro("warn", "El sistema se está apagando a petición del usuario.", pet.sesion.usuario)
		pet.estado.apagado = True
	return {}


def reiniciar(pet: Peticion) -> dict[str, Any]:
	if pet.version != 1:
		raise ErrorSim(103)
	if pet.aplicar:
		pet.estado.reinicios += 1
		pet.estado.arranque = time.time()
		pet.estado.sesiones.clear()
		pet.estado.sistema["necesita_reinicio"] = False
		pet.estado.anotar_registro("warn", "El sistema se ha reiniciado a petición del usuario.", pet.sesion.usuario)
	return {}


def estado_sistema(pet: Peticion) -> dict[str, Any]:
	return {"is_system_crashed": False, "upgrade_ready": False}


def salud(pet: Peticion) -> dict[str, Any]:
	datos = pet.estado.datos
	problemas = [d["nombre"] for d in datos["discos"] if d["smart"] != "normal"]
	degradado = any(v["estado"] != "normal" for v in datos["volumenes"])
	tipo = "warning" if problemas or degradado else "normal"
	return {"rule": {"type": tipo, "title": "Hay avisos de salud" if tipo != "normal" else "Correcto"},
		"interfaces": [{"id": i["id"], "type": "lan", "ip": [{"address": i["ip"]}] if i["ip"] else []} for i in datos["red"]["interfaces"]],
		"uptime": _encendido(pet.estado.encendido_s())}


def utilizacion(pet: Peticion) -> dict[str, Any]:
	if pet.simulador.contar_lectura_utilizacion():
		raise ErrorSim(1055, {"err_line": 1, "err_msg": "transmisión interrumpida"})
	azar = pet.estado.azar
	libre, total = pet.estado.espacio()
	uso_espacio = round(100 * (total - libre) / total) if total else 0
	usuario, sistema = azar.randint(2, 9), azar.randint(1, 4)
	rx, tx = azar.randint(20_000, 400_000), azar.randint(8_000, 120_000)
	return {
		"cpu": {"user_load": usuario, "system_load": sistema, "other_load": azar.randint(0, 2), "1min_load": azar.randint(20, 60),
			"5min_load": azar.randint(20, 50), "15min_load": azar.randint(20, 45), "device": "System"},
		"memory": {"memory_size": 10485760, "total_real": 10086136, "avail_real": 7123456, "cached": 2123456, "buffer": 15172,
			"real_usage": azar.randint(18, 26), "total_swap": 6762476, "avail_swap": 6700000, "swap_usage": 1},
		"network": [{"device": "total", "rx": rx, "tx": tx}, {"device": "eth0", "rx": rx, "tx": tx}, {"device": "eth1", "rx": 0, "tx": 0}],
		"disk": {"disk": [{"device": d["id"], "display_name": d["nombre"], "utilization": azar.randint(2, 15),
			"read_byte": azar.randint(10_000, 900_000), "write_byte": azar.randint(10_000, 900_000), "type": "internal"}
			for d in pet.estado.datos["discos"]], "total": {"device": "total", "utilization": azar.randint(3, 12)}},
		"space": {"volume": [{"device": "md2", "display_name": "volume1", "utilization": uso_espacio}]},
		"lun": [], "time": int(time.time()),
	}


def ventilador(pet: Peticion) -> dict[str, Any]:
	return {"dual_fan_speed": pet.estado.sistema["ventilador"], "cool_fan": "yes", "all_disk_temp_fail": "no", "fan_type": 11,
		"fan_support_adjust_by_ext_nic": "no"}


def fijar_ventilador(pet: Peticion) -> dict[str, Any]:
	modo = pet.texto("dual_fan_speed")
	if modo not in ("quietfan", "coolfan", "fullfan"):
		raise ErrorSim(3712)
	if pet.aplicar:
		pet.estado.sistema["ventilador"] = modo
	return {}


def necesita_reinicio(pet: Peticion) -> dict[str, Any]:
	return {"need_reboot": bool(pet.estado.sistema.get("necesita_reinicio"))}


def usb(pet: Peticion) -> dict[str, Any]:
	return {"devices": []}


MANEJADORES = {
	("SYNO.Core.System", "info"): system_info,
	("SYNO.Core.System", "shutdown"): apagar,
	("SYNO.Core.System", "reboot"): reiniciar,
	("SYNO.DSM.Info", "getinfo"): dsm_info,
	("SYNO.Core.System.Status", "get"): estado_sistema,
	("SYNO.Core.System.SystemHealth", "get"): salud,
	("SYNO.Core.System.Utilization", "get"): utilizacion,
	("SYNO.Core.Hardware.FanSpeed", "get"): ventilador,
	("SYNO.Core.Hardware.FanSpeed", "set"): fijar_ventilador,
	("SYNO.Core.Hardware.NeedReboot", "get"): necesita_reinicio,
	("SYNO.Core.ExternalDevice.Storage.USB", "list"): usb,
}
