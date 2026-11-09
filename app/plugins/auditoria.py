# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Auditoría opcional de los complementos (diseño 2.0, 3.8, ``complementos.auditoria``). Sin wx.

Bloque PL. Un gancho ``sys.addaudithook`` apunta en el registro las conexiones
(``socket.connect``) y los procesos (``subprocess.Popen``) que se originan en un
módulo ``zcplugins.*`` de un complemento que no declaró el permiso
correspondiente (``red`` o ``internet:<host>``; ``ejecutar_programas``).

Solo registra: no es una barrera (PEP 578: un gancho de auditoría no se puede
quitar y el código Python puede saltárselo). Por eso se instala una sola vez
por proceso y lo que se activa y desactiva es la comprobación.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any

from app.plugins import registro

log = logging.getLogger(__name__)

_estado = {"instalado": False, "activo": False}
_candado = threading.Lock()
_dentro = threading.local()
_EVENTOS = {"socket.connect": "red", "subprocess.Popen": "ejecutar_programas"}


def activa() -> bool:
	return _estado["activo"]


def _complemento_que_llama() -> str | None:
	"""Id del complemento cuyo código está en la pila de llamadas (el más cercano), o ``None``."""
	marco = sys._getframe(2)
	while marco is not None:
		nombre = marco.f_globals.get("__name__", "")
		if isinstance(nombre, str) and nombre.startswith("zcplugins."):
			codificado = nombre.split(".")[1]
			return codificado.replace("__", ".")
		marco = marco.f_back
	return None


def _permitido(id_complemento: str, permiso: str, argumentos: tuple) -> bool:
	registrado = registro.complemento(id_complemento)
	permisos = registrado.manifiesto.permisos if registrado is not None else ()
	if permiso in permisos:
		return True
	if permiso == "red":
		destino = argumentos[1] if len(argumentos) > 1 else None
		host = destino[0] if isinstance(destino, tuple) and destino else ""
		return f"internet:{host}" in permisos or host in ("127.0.0.1", "::1", "localhost")
	return False


def _gancho(evento: str, argumentos: tuple) -> None:
	if not _estado["activo"] or evento not in _EVENTOS or getattr(_dentro, "activo", False):
		return
	_dentro.activo = True
	try:
		id_complemento = _complemento_que_llama()
		if id_complemento is None:
			return
		permiso = _EVENTOS[evento]
		if not _permitido(id_complemento, permiso, argumentos):
			log.warning("Auditoría: el complemento %s usa %s sin el permiso «%s» (%s)", id_complemento, evento, permiso,
				_resumir(argumentos))
	except Exception:  # noqa: BLE001 - el gancho de auditoría nunca debe romper la llamada auditada
		log.debug("Fallo en el gancho de auditoría", exc_info=True)
	finally:
		_dentro.activo = False


def _resumir(argumentos: tuple) -> str:
	texto = repr(argumentos[1] if len(argumentos) > 1 else argumentos)
	return texto[:200]


def activar(activa_: bool = True) -> None:
	"""Activa (o desactiva) la auditoría; instala el gancho la primera vez."""
	with _candado:
		if activa_ and not _estado["instalado"]:
			sys.addaudithook(_gancho)
			_estado["instalado"] = True
		_estado["activo"] = bool(activa_)
	log.info("Auditoría de complementos %s", "activada" if activa_ else "desactivada")


def desde_configuracion(config: Any) -> None:
	"""Aplica ``complementos.auditoria`` (al arrancar y cuando cambia)."""
	try:
		valor = bool(config.obtener("complementos.auditoria"))
	except Exception:  # noqa: BLE001 - sin la clave, desactivada
		valor = False
	if valor or _estado["instalado"]:
		activar(valor)
