# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Catálogo de API de un NAS (``SYNO.API.Info query=all``) y elección de versión (diseño 2.0, 13.1).

Cada llamada usa ``max(minVersion, min(versión preferida, maxVersion))``: hay
API con ``minVersion`` 2 (``SYNO.DSM.Info``, ``SYNO.DSM.Network``,
``SYNO.FileStation.Upload``) que con la versión 1 darían el error 104. Si la
versión resultante queda fuera de las que el cliente sabe manejar, la función
se oculta con el motivo; lo que el NAS no tiene se oculta con el motivo
(«Necesita el paquete Hyper Backup»), nunca según el modelo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.plugins import api

_, _n = api.traduccion("zc_synology")

#: API → (versión preferida, mínima que el cliente sabe manejar, máxima que sabe manejar).
#: Las que no están aquí se llaman con su versión máxima (y el cliente las acepta todas).
VERSIONES: Mapping[str, tuple[int, int, int]] = {
	"SYNO.API.Info": (1, 1, 1),
	"SYNO.API.Auth": (7, 6, 7),
	"SYNO.Entry.Request": (1, 1, 2),
	"SYNO.Core.System": (3, 1, 3),
	"SYNO.DSM.Info": (2, 1, 2),
	"SYNO.DSM.Network": (2, 1, 2),
	"SYNO.Core.Package": (2, 1, 2),
	"SYNO.Core.Package.Server": (2, 1, 2),
	"SYNO.Core.TaskScheduler": (3, 1, 4),
	"SYNO.Core.Upgrade.Server": (4, 1, 4),
	"SYNO.Core.Upgrade.Setting": (4, 1, 4),
	"SYNO.Core.Terminal": (3, 1, 3),
	"SYNO.Core.FileServ.SMB": (3, 1, 3),
	"SYNO.Core.QuickConnect": (2, 1, 3),
	"SYNO.Core.User.PasswordConfirm": (2, 1, 2),
	"SYNO.FileStation.List": (2, 1, 2),
	"SYNO.FileStation.Upload": (3, 2, 3),
	"SYNO.FileStation.Download": (2, 1, 2),
	"SYNO.FileStation.CopyMove": (3, 1, 3),
	"SYNO.FileStation.Delete": (2, 1, 2),
	"SYNO.FileStation.Search": (2, 1, 2),
	"SYNO.FileStation.Sharing": (3, 1, 3),
	"SYNO.FileStation.Compress": (3, 1, 3),
	"SYNO.FileStation.Extract": (2, 1, 2),
	"SYNO.FileStation.BackgroundTask": (3, 1, 3),
	"SYNO.SynologyDrive.Connection": (2, 1, 2),
}

#: Prefijo de API → paquete de DSM que la trae (para el motivo de una función ausente).
PAQUETES: Mapping[str, str] = {
	"SYNO.Docker.": "Container Manager",
	"SYNO.SynologyDrive": "Synology Drive Server",
	"SYNO.Foto": "Synology Photos",
	"SYNO.Finder.": "Synology Universal Search",
	"SYNO.Backup.Task": "Hyper Backup",
	"SYNO.DownloadStation": "Download Station",
	"SYNO.SurveillanceStation": "Surveillance Station",
	"SYNO.LogCenter": "Log Center",
	"SYNO.WebDAV.": "WebDAV Server",
	"SYNO.SecurityAdvisor": "Asesor de seguridad",
	"SYNO.USBCopy": "USB Copy",
	"SYNO.ActiveInsight": "Active Insight",
	"SYNO.Virtualization": "Virtual Machine Manager",
	"SYNO.AntiVirus": "Antivirus",
	"SYNO.CloudSync": "Cloud Sync",
}


@dataclass(frozen=True)
class InfoAPI:
	"""Una API del catálogo del NAS."""

	nombre: str
	minima: int
	maxima: int
	ruta: str = "entry.cgi"
	json: bool = False


class Catalogo:
	"""Las API que tiene un NAS concreto."""

	def __init__(self, datos: Mapping[str, Any]) -> None:
		self._apis: dict[str, InfoAPI] = {}
		for nombre, info in (datos or {}).items():
			if not isinstance(info, Mapping):
				continue
			try:
				self._apis[str(nombre)] = InfoAPI(
					str(nombre), int(info.get("minVersion", 1)), int(info.get("maxVersion", 1)),
					str(info.get("path", "entry.cgi")), str(info.get("requestFormat", "")).upper() == "JSON")
			except (TypeError, ValueError):
				continue

	def __len__(self) -> int:
		return len(self._apis)

	def __contains__(self, nombre: object) -> bool:
		return nombre in self._apis

	def tiene(self, nombre: str) -> bool:
		return nombre in self._apis

	def tiene_todas(self, nombres: Iterable[str]) -> bool:
		return all(n in self._apis for n in nombres)

	def info(self, nombre: str) -> InfoAPI | None:
		return self._apis.get(nombre)

	def nombres(self) -> list[str]:
		return sorted(self._apis)

	def como_dict(self) -> dict[str, dict[str, Any]]:
		"""Para guardar en la caché con la misma forma que devuelve ``SYNO.API.Info``."""
		resultado: dict[str, dict[str, Any]] = {}
		for nombre, info in self._apis.items():
			fila: dict[str, Any] = {"minVersion": info.minima, "maxVersion": info.maxima, "path": info.ruta}
			if info.json:
				fila["requestFormat"] = "JSON"
			resultado[nombre] = fila
		return resultado

	def version(self, nombre: str, preferida: int | None = None) -> int:
		"""Versión que se usa para ``nombre``. Lanza ``FuncionAusente`` si no se puede usar."""
		from . import errores

		info = self._apis.get(nombre)
		if info is None:
			raise errores.FuncionAusente(motivo_ausente(nombre), 102, nombre)
		pref, minima_cliente, maxima_cliente = VERSIONES.get(nombre, (info.maxima, 1, 1_000))
		if preferida is not None:
			pref = preferida
		elegida = elegir_version(info.minima, info.maxima, pref)
		if preferida is None and not (minima_cliente <= elegida <= maxima_cliente):
			raise errores.FuncionAusente(_("zCommander no sabe usar la versión {v} de {a} que tiene este NAS.").format(
				v=elegida, a=nombre), 104, nombre)
		return elegida

	def disponible(self, nombre: str) -> tuple[bool, str]:
		"""(se puede usar, motivo si no)."""
		from . import errores

		try:
			self.version(nombre)
		except errores.FuncionAusente as error:
			return False, error.mensaje
		return True, ""


def elegir_version(minima: int, maxima: int, preferida: int) -> int:
	"""``max(minVersion, min(preferida, maxVersion))`` (13.1)."""
	return max(int(minima), min(int(preferida), int(maxima)))


def motivo_ausente(nombre: str) -> str:
	"""«Necesita el paquete Hyper Backup» o «Este NAS no tiene la función X»."""
	for prefijo, paquete in PAQUETES.items():
		if nombre.startswith(prefijo):
			return _("Necesita el paquete {p}").format(p=paquete)
	return _("Este NAS no tiene la función {a}").format(a=nombre)
