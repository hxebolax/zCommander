# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Synology Photos (synology.md 4.9): estado del índice y reindexar."""

from __future__ import annotations

import time
from typing import Any

from ..comun import Peticion


def indice(pet: Peticion) -> dict[str, Any]:
	photos = pet.estado.datos["photos"]
	return {"indexing": photos["indexando"], "photo_count": photos["fotos"], "video_count": photos["videos"],
		"last_index_time": photos["ultimo_indice"]}


def reindexar(pet: Peticion) -> dict[str, Any]:
	if pet.aplicar:
		photos = pet.estado.datos["photos"]
		photos["indexando"] = True
		photos["ultimo_indice"] = time.strftime("%Y-%m-%d %H:%M")
		pet.estado.anotar_registro("info", "Synology Photos ha empezado a volver a indexar las fotos.", pet.sesion.usuario)
	return {}


def tarea(pet: Peticion) -> dict[str, Any]:
	photos = pet.estado.datos["photos"]
	return {"tasks": [{"type": "index", "status": "running" if photos["indexando"] else "finished",
		"progress": 0.4 if photos["indexando"] else 1.0}]}


def ajustes(pet: Peticion) -> dict[str, Any]:
	return {"enable_shared_space": True, "enable_person": True, "enable_concept": True, "enable_geocoding": False}


def usuario(pet: Peticion) -> dict[str, Any]:
	return {"name": pet.sesion.usuario if pet.sesion else "", "is_admin": bool(pet.sesion and pet.sesion.administrador)}


MANEJADORES = {
	("SYNO.Foto.Index", "get"): indice,
	("SYNO.Foto.Index", "reindex"): reindexar,
	("SYNO.Foto.BackgroundTask.Info", "get"): tarea,
	("SYNO.Foto.Setting.Admin", "get"): ajustes,
	("SYNO.Foto.UserInfo", "me"): usuario,
}
