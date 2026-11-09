# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Avisos de la campana de DSM (synology.md 4.12). Forma por verificar: se devuelven ya en español."""

from __future__ import annotations

import time
from typing import Any

from ..comun import Peticion


def avisos(pet: Peticion) -> dict[str, Any]:
	ahora = time.time()
	filas = [{"id": a["id"], "level": a["nivel"], "title": a["titulo"], "msg": a["mensaje"],
		"time": int(ahora - a["minutos"] * 60)} for a in pet.estado.datos["avisos"]]
	for disco in pet.estado.datos["discos"]:
		if disco["smart"] != "normal":
			filas.insert(0, {"id": 100, "level": "error", "title": "Aviso de disco",
				"msg": f"{disco['nombre']} tiene {disco['unc']} sectores dañados: haga una copia de seguridad y cámbielo.",
				"time": int(ahora - 60)})
	return {"items": filas, "total": len(filas)}


MANEJADORES = {
	("SYNO.Core.DSMNotify", "notify"): avisos,
}
