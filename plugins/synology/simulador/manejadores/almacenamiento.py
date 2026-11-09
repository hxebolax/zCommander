# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Almacenamiento (synology.md 4.2): volúmenes, grupos, discos, S.M.A.R.T. y limpieza de datos."""

from __future__ import annotations

from typing import Any

from ..comun import ErrorSim, Peticion


def _disco(d: dict[str, Any]) -> dict[str, Any]:
	return {"id": d["id"], "name": d["nombre"], "longName": d["nombre"], "device": f"/dev/{d['id']}", "model": d["modelo"],
		"vendor": d["fabricante"], "serial": d["serie"], "firm": d["firmware"], "diskType": "SATA", "isSsd": False,
		"size_total": d["tamano"], "temp": d["temp"], "status": d["estado"], "smart_status": d["smart"],
		"overview_status": d["estado"], "below_remain_life_thr": False, "exceed_bad_sector_thr": d["unc"] > 0, "unc": d["unc"],
		"used_by": d["grupo"], "container": {"str": "DS220+", "type": "internal", "order": 0}}


def load_info(pet: Peticion) -> dict[str, Any]:
	datos = pet.estado.datos
	return {
		"disks": [_disco(d) for d in datos["discos"]],
		"storagePools": [{"id": g["id"], "num_id": g["num_id"], "desc": "", "device_type": g["tipo"], "raidType": "single",
			"raid_desc": g["raid"], "disks": g["discos"], "status": g["estado"], "is_writable": True,
			"disk_failure_number": 0 if g["estado"] == "normal" else 1, "progress": {"percent": "-1", "step": "none"},
			"size": {"total": g["total"], "used": g["usado"]}} for g in datos["grupos"]],
		"volumes": [{"id": v["id"], "num_id": v["num_id"], "vol_path": v["ruta"], "pool_path": v["grupo"], "fs_type": v["fs"],
			"status": v["estado"], "is_writable": True, "size": {"total": v["total"], "used": v["usado"], "free_inode": "0",
				"total_inode": "0"}, "scrubbingStatus": v["limpieza"], "ssd_trim": {"support": "not support"}}
			for v in datos["volumenes"]],
		"env": {"model_name": "DS220+", "bay_number": "2", "status": {"system_crashed": False}},
	}


def _buscar_disco(pet: Peticion) -> dict[str, Any]:
	dispositivo = pet.texto("device") or pet.texto("disk") or pet.texto("id")
	identificador = dispositivo.rsplit("/", 1)[-1]
	disco = next((d for d in pet.estado.datos["discos"] if d["id"] == identificador), None)
	if disco is None:
		raise ErrorSim(120)
	return disco


def lista_discos(pet: Peticion) -> dict[str, Any]:
	return {"disks": [_disco(d) for d in pet.estado.datos["discos"]], "total": len(pet.estado.datos["discos"])}


def smart(pet: Peticion) -> dict[str, Any]:
	disco = _buscar_disco(pet)
	atributos = [
		("1", "Raw_Read_Error_Rate", 117, 99, 6, "123456789"), ("5", "Reallocated_Sector_Ct", 100, 100, 10, str(disco["unc"] * 8)),
		("9", "Power_On_Hours", 76, 76, 0, str(disco["horas"])), ("194", "Temperature_Celsius", 36, 45, 0, str(disco["temp"])),
		("197", "Current_Pending_Sector", 100, 100, 0, str(disco["unc"])), ("199", "UDMA_CRC_Error_Count", 200, 200, 0, "0"),
	]
	return {"healthInfo": {"overview": {"status": disco["smart"], "unc": disco["unc"]}},
		"smartInfo": [{"id": a[0], "name": a[1], "current": a[2], "worst": a[3], "threshold": a[4], "raw": a[5],
			"status": "OK" if a[0] not in ("5", "197") or disco["unc"] == 0 else "WARNING"} for a in atributos],
		"status": disco["smart"], "temp": disco["temp"], "power_on_hours": disco["horas"]}


def prueba_smart(pet: Peticion) -> dict[str, Any]:
	disco = _buscar_disco(pet)
	tipo = pet.texto("type", "quick")
	if pet.aplicar:
		pet.estado.anotar_registro("info", f"Prueba S.M.A.R.T. {'rápida' if tipo == 'quick' else 'completa'} iniciada en [{disco['nombre']}].",
			pet.sesion.usuario)
	return {}


def uso_espacio(pet: Peticion) -> dict[str, Any]:
	libre, total = pet.estado.espacio()
	return {"total": str(total), "used": str(total - libre), "free": str(libre)}


def limpieza(pet: Peticion) -> dict[str, Any]:
	if pet.aplicar:
		pet.estado.datos["volumenes"][0]["limpieza"] = "running"
		pet.estado.anotar_registro("info", "Se ha iniciado la limpieza de datos del grupo de almacenamiento 1.", pet.sesion.usuario)
	return {}


MANEJADORES = {
	("SYNO.Storage.CGI.Storage", "load_info"): load_info,
	("SYNO.Core.Storage.Disk", "list"): lista_discos,
	("SYNO.Core.Storage.Disk", "get_smart_info"): smart,
	("SYNO.Core.Storage.Disk", "do_smart_test"): prueba_smart,
	("SYNO.Storage.CGI.Smart", "get_health_info"): smart,
	("SYNO.Storage.CGI.Smart", "get_smart_info"): smart,
	("SYNO.Storage.CGI.Volume", "get_space_usage"): uso_espacio,
	("SYNO.Storage.CGI.Pool", "data_scrubbing"): limpieza,
}
