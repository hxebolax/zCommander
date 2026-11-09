# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lista blanca de métodos de LECTURA de la API de DSM (diseño 2.0, 13.1 y 13.9; synology.md 7.4).

La comparten el cliente (que bloquea en el equipo, antes de enviar nada, toda
llamada que no sea de lectura mientras el NAS está en solo lectura) y el
simulador (que en su modo ``lectura`` rechaza el resto con el error 116).
Tenerla en un único sitio evita que las dos barreras se contradigan.

Regla: solo es lectura lo que está en la lista explícita. **Todo lo demás
cuenta como escritura, también lo desconocido.** Sin wx y sin dependencias de
zCommander (el simulador se ejecuta también como programa suelto).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Métodos que en cualquier API solo consultan.
METODOS_LECTURA: frozenset[str] = frozenset({
	"get", "list", "info", "getinfo", "load_info", "list_share", "status", "check", "query", "latestlog_get",
	"get_smart_info", "get_health_info", "get_space_usage", "get_state", "get_status", "get_misc_config",
	"get_setting", "get_history_status_list", "get_global_setting", "get_log_list", "list_by_user",
	"list_by_group", "list_status", "summary", "version", "load", "view", "cnt_get", "eps_get", "system_get",
	"rule_get", "first_get", "group_enum", "me", "progress", "smart_warning_get", "get_smart_test_log",
})

#: Métodos de lectura propios de una API concreta (crean una tarea, pero no tocan nada).
LECTURA_POR_API: Mapping[str, frozenset[str]] = {
	"SYNO.API.Info": frozenset({"query"}),
	"SYNO.API.Auth": frozenset({"login", "logout", "token"}),
	"SYNO.Core.User.PasswordConfirm": frozenset({"auth"}),
	"SYNO.FileStation.Search": frozenset({"start", "list", "stop", "clean"}),
	"SYNO.FileStation.DirSize": frozenset({"start", "status", "stop"}),
	"SYNO.FileStation.MD5": frozenset({"start", "status", "stop"}),
	"SYNO.FileStation.Download": frozenset({"download"}),
	"SYNO.FileStation.Extract": frozenset({"list"}),
	"SYNO.FileStation.CheckPermission": frozenset({"write"}),
	"SYNO.FileStation.CheckExist": frozenset({"check"}),
	"SYNO.FileStation.Thumb": frozenset({"get"}),
	"SYNO.Core.SecurityScan.Operation": frozenset({"start"}),
	"SYNO.Finder.FileIndexing.Search": frozenset({"search"}),
	"SYNO.Docker.Registry": frozenset({"search", "tags"}),
}

#: Pares que son SIEMPRE escritura, aunque un día un nombre de método coincida con la lista de lectura.
ESCRITURA_SIEMPRE: frozenset[tuple[str, str]] = frozenset({
	("SYNO.Core.System", "shutdown"), ("SYNO.Core.System", "reboot"), ("SYNO.Core.System", "reset"),
	("SYNO.Core.Upgrade", "start"), ("SYNO.Storage.CGI.Smart", "secure_erase"),
})

#: Raíces de método que nunca se aceptan como lectura (borran, desinstalan o apagan).
_PELIGROSOS = ("delete", "uninstall", "remove", "shutdown", "reboot", "erase", "format", "kick")


def es_lectura(api: str, metodo: str, parametros: Mapping[str, Any] | None = None) -> bool:
	"""``True`` si ``api.metodo`` solo consulta y se puede llamar en modo solo lectura.

	:param parametros: hacen falta en dos casos: ``SYNO.Core.DSMNotify notify`` solo
		es lectura con ``action=load``, y ``SYNO.Entry.Request request`` lo es solo si
		todas sus peticiones internas (``compound``) lo son.
	"""
	api = str(api or "")
	metodo = str(metodo or "")
	if not api or not metodo:
		return False
	if (api, metodo) in ESCRITURA_SIEMPRE or any(metodo.startswith(p) for p in _PELIGROSOS):
		return False
	parametros = parametros or {}
	if api == "SYNO.Core.DSMNotify" and metodo == "notify":
		return _texto(parametros.get("action")) == "load"
	if api == "SYNO.Entry.Request" and metodo == "request":
		compuesta = parametros.get("compound")
		if not isinstance(compuesta, list) or not compuesta:
			return False
		return all(isinstance(p, Mapping) and es_lectura(str(p.get("api", "")), str(p.get("method", "")), p) for p in compuesta)
	if metodo in LECTURA_POR_API.get(api, frozenset()):
		return True
	return metodo in METODOS_LECTURA


def _texto(valor: Any) -> str:
	"""Un parámetro puede llegar codificado en JSON (``"\\"load\\""``) o tal cual."""
	texto = str(valor or "")
	if len(texto) >= 2 and texto[0] == texto[-1] == '"':
		return texto[1:-1]
	return texto
