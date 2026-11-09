# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Servicios (synology.md 4.15): SMB, SSH y Telnet, WebDAV, NFS, FTP y SFTP. ``WebDAV.Common`` tiene forma supuesta."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..comun import Peticion

#: API → (clave en los datos, campos que se pueden cambiar).
SERVICIOS = {
	"SYNO.Core.FileServ.SMB": ("smb", ("enable_samba", "workgroup", "smb_min_protocol", "smb_max_protocol")),
	"SYNO.Core.Terminal": ("ssh", ("enable_ssh", "ssh_port", "enable_telnet")),
	"SYNO.WebDAV.Common": ("webdav", ("enable_http", "http_port", "enable_https", "https_port")),
	"SYNO.Core.FileServ.NFS": ("nfs", ("enable_nfs", "enable_nfs_v4")),
	"SYNO.Core.FileServ.FTP": ("ftp", ("enable_ftp", "enable_ftps", "portnum")),
	"SYNO.Core.FileServ.FTP.SFTP": ("sftp", ("enable", "portnum")),
}


def _obtener(api: str) -> Callable[[Peticion], dict[str, Any]]:
	def manejador(pet: Peticion) -> dict[str, Any]:
		return dict(pet.estado.datos["servicios"][SERVICIOS[api][0]])

	return manejador


def _fijar(api: str) -> Callable[[Peticion], dict[str, Any]]:
	def manejador(pet: Peticion) -> dict[str, Any]:
		clave, campos = SERVICIOS[api]
		if pet.aplicar:
			datos = pet.estado.datos["servicios"][clave]
			for campo in campos:
				if campo in pet.params:
					valor = pet.params[campo]
					datos[campo] = pet.booleano(campo) if isinstance(datos.get(campo), bool) else valor
			pet.estado.anotar_registro("info", f"Se ha cambiado la configuración del servicio {clave.upper()}.", pet.sesion.usuario)
		return {}

	return manejador


MANEJADORES: dict[tuple[str, str], Callable[[Peticion], Any]] = {}
for _api in SERVICIOS:
	MANEJADORES[(_api, "get")] = _obtener(_api)
	MANEJADORES[(_api, "set")] = _fijar(_api)
