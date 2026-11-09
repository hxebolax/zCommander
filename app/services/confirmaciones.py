# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Confirmaciones silenciables una a una (diseño 2.0, 10.12).

Por qué existe: algunas preguntas de la 1.x solo informan (el aviso de que
escribir en un comprimido lo reconstruye entero, el de FTP sin cifrar) y
molestan a quien ya lo sabe. Cada una gana la casilla «No volver a preguntar»,
pero la lista es CERRADA: lo que protege de perder datos o de ejecutar código
(eliminar definitivamente, restaurar, instalar un complemento sin firma...)
nunca se puede silenciar, y los complementos no añaden confirmaciones
silenciables en la API 1.0.

Las silenciadas se guardan en ``general.no_preguntar``. Una confirmación
puede llevar un sufijo tras «:» (``ftp_sin_cifrar:<sitio>``) para silenciarla
solo en un sitio: ``debe_preguntar`` mira el id completo y también su prefijo
antes de «:», así silenciar ``ftp_sin_cifrar`` vale para todos los sitios.

Sin wx: lo usan los servicios (``vfs/ftp.py``) y la interfaz.
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

CLAVE = "general.no_preguntar"


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Confirmacion:
	"""Una confirmación silenciable: texto de la lista de Preferencias y su ayuda (Ctrl+H)."""

	etiqueta: str
	ayuda: str


CONFIRMACIONES: dict[str, Confirmacion] = {
	"comprimido_escritura": Confirmacion(
		N_("Aviso al escribir en un comprimido"),
		N_("Copiar o borrar dentro de un comprimido lo reconstruye entero; el aviso lo recuerda."),
	),
	"ftp_sin_cifrar": Confirmacion(
		N_("Aviso de conexión FTP sin cifrar"),
		N_("La contraseña y los archivos de un FTP sin cifrar viajan en claro por la red."),
	),
	"marcas_cursor": Confirmacion(
		N_("Pregunta de marcas y cursor"),
		N_("Con elementos marcados y el cursor en otro, pregunta sobre cuáles actuar."),
	),
	"esquema_cambio": Confirmacion(
		N_("Aviso al cambiar el esquema de teclas"),
		N_("Recuerda qué órdenes cambian de tecla al aplicar otro esquema."),
	),
	"copia_sin_secretos": Confirmacion(
		N_("Aviso al crear una copia sin contraseñas"),
		N_("Sin contraseñas, las conexiones guardadas pedirán la suya tras restaurar."),
	),
	"complemento_autor_confiado": Confirmacion(
		N_("Pregunta al instalar un complemento de un autor de confianza"),
		N_("Confirma la instalación aunque el complemento esté firmado por un autor en el que ya confía."),
	),
}


def _base(id_confirmacion: str) -> str:
	return id_confirmacion.split(":", 1)[0]


def _lista(config: Any) -> list[str]:
	try:
		valor = config.obtener(CLAVE)
	except Exception:  # noqa: BLE001 - una configuración falsa o rota no impide preguntar
		log.debug("No se pudo leer %s", CLAVE, exc_info=True)
		return []
	return [str(v) for v in valor] if isinstance(valor, (list, tuple)) else []


def debe_preguntar(config: Any, id_confirmacion: str) -> bool:
	"""``True`` si hay que preguntar: ni el id completo ni su prefijo antes de «:» están silenciados.

	Un id que no es de la lista cerrada se pregunta siempre (y se registra): así un
	error al escribir el nombre nunca silencia algo por accidente.
	"""
	if _base(id_confirmacion) not in CONFIRMACIONES:
		log.warning("Confirmación desconocida «%s»: se pregunta siempre", id_confirmacion)
		return True
	silenciadas = _lista(config)
	return id_confirmacion not in silenciadas and _base(id_confirmacion) not in silenciadas


def silenciar(config: Any, id_confirmacion: str) -> None:
	"""Añade la confirmación a ``general.no_preguntar`` (no se vuelve a preguntar)."""
	if _base(id_confirmacion) not in CONFIRMACIONES:
		raise ValueError(_("La confirmación «{c}» no se puede silenciar").format(c=id_confirmacion))
	silenciadas = _lista(config)
	if id_confirmacion in silenciadas:
		return
	config.establecer(CLAVE, [*silenciadas, id_confirmacion])


def volver_a_preguntar(config: Any, id_confirmacion: str | None = None) -> None:
	"""Quita una confirmación silenciada (con sus variantes «id:sitio»), o todas con ``None``."""
	if id_confirmacion is None:
		config.establecer(CLAVE, [])
		return
	base = _base(id_confirmacion)
	config.establecer(CLAVE, [c for c in _lista(config) if c != id_confirmacion and _base(c) != base])
