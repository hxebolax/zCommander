# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes que graban y reciben un argumento en las macros (diseño 2.0, 10.1). Sin wx.

La tabla ``ARGUMENTOS`` la fija N2 y la usa PE (grabador y ejecutor de macros):
las órdenes que están aquí graban su argumento y, al reproducirse, lo reciben en
``ctx.argumento`` (con ``sin_dialogo`` no muestran su diálogo); las demás se
graban sin argumento y al reproducirse abren su diálogo como siempre.

Formato de cada argumento (``Argumento.tipo``):

- ``ruta``: texto con una ruta o dirección (``D:\\Fotos``, ``ftp://servidor/x``).
- ``patron``: patrón de nombres (``*.jpg;*.jpeg``, exclusiones con ``|``).
- ``texto``: texto libre (un nombre, una orden, la etiqueta de una entrada).
- ``json``: diccionario con los ``campos`` que se nombran (los que faltan toman
  el valor del diálogo).

Las órdenes de complementos con ``argumento`` en su ``[[ordenes]]`` (3.3)
también lo admiten: ``argumento_de`` las consulta en el catálogo vivo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TipoArgumento = Literal["ruta", "patron", "texto", "json"]
TIPOS: tuple[str, ...] = ("ruta", "patron", "texto", "json")


@dataclass(frozen=True)
class Argumento:
	tipo: TipoArgumento
	campos: tuple[str, ...] = ()


_COPIA = Argumento("json", ("destino", "politica", "verificar", "sin_dialogo"))

ARGUMENTOS: dict[str, Argumento] = {
	"ir_a_carpeta": Argumento("ruta"),
	"marcar_patron": Argumento("patron"),
	"desmarcar_patron": Argumento("patron"),
	"filtro": Argumento("patron"),
	"crear_carpeta": Argumento("texto"),
	"copiar": _COPIA,
	"mover": _COPIA,
	"comprimir": Argumento("json", ("formato", "nombre", "sin_dialogo")),
	"extraer": Argumento("json", ("destino", "sin_dialogo")),
	"ejecutar_linea": Argumento("texto"),
	"menu_usuario": Argumento("texto"),
	"espacios_trabajo": Argumento("texto"),
	# Pestañas: solo «Pestaña nueva» admite argumento (la carpeta que abre); las
	# demás pestana_* son deterministas (su número va en ``param``) y se graban sin él.
	"pestana_nueva": Argumento("ruta"),
}

#: Pasos especiales de una macro que no son órdenes del catálogo (prefijo ``paso:``).
PASOS_ESPECIALES: dict[str, Argumento] = {
	"paso:decir": Argumento("texto"),
	"paso:esperar": Argumento("texto"),
	"paso:sonar": Argumento("texto"),
}

#: Órdenes que, en una macro, esperan por defecto a que termine su operación.
ESPERAN_OPERACION = frozenset({"copiar", "mover", "comprimir", "extraer"})


def argumento_de(id_orden: str) -> Argumento | None:
	"""El argumento que admite una orden (núcleo, paso especial o complemento), o ``None``."""
	if id_orden in ARGUMENTOS:
		return ARGUMENTOS[id_orden]
	if id_orden in PASOS_ESPECIALES:
		return PASOS_ESPECIALES[id_orden]
	if ":" in id_orden and not id_orden.startswith(("macro:", "paso:")):
		from app.plugins import registro

		tipo = registro.argumento_orden(id_orden)
		if tipo in TIPOS:
			return Argumento(tipo)  # type: ignore[arg-type]
	return None
