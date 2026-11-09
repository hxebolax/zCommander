# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Papelera de reciclaje con Send2Trash (usa ``IFileOperation`` de Windows).

``IFileOperation`` exige COM en modo STA en el hilo que la llama: se inicia
aquí con ``pythoncom.CoInitializeEx`` antes de usarla, en el hilo de la tarea.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Sequence

from app.services.vfs import base, rutas
from app.services.windows import unidades

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def admite_papelera(ruta: str) -> bool:
	"""Las unidades fijas tienen papelera; las de red y extraíbles, no. Las rutas largas tampoco funcionan."""
	if rutas.es_larga(ruta):
		return False
	raiz = rutas.raiz(rutas.normalizar(ruta))
	if raiz.startswith("\\\\"):
		return False
	return unidades.tipo_de(raiz) == "fija"


def enviar(rutas_: Sequence[str]) -> None:
	"""Envía a la papelera (en un hilo de trabajo). Lanza ``ErrorArchivos`` con mensaje en español."""
	if not rutas_:
		return
	try:
		import pythoncom

		pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
	except Exception:  # noqa: BLE001 - ya iniciado en este hilo o sin pywin32
		log.debug("CoInitializeEx no necesario o no disponible", exc_info=True)
	try:
		from send2trash import send2trash
		from send2trash.exceptions import TrashPermissionError

		send2trash([rutas.normalizar(r) for r in rutas_])
	except TrashPermissionError as error:
		raise base.ErrorAcceso(_("No se pudo enviar a la papelera: no tiene permiso."), str(rutas_[0])) from error
	except OSError as error:
		from app.services import errores

		raise errores.convertir(error, str(rutas_[0])) from error
