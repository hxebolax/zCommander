# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Esquemas de teclas (diseño 2.0, 10.7). Sin wx.

Solo las DIFERENCIAS con ``norton`` (el de fábrica, el de la 1.x): para cada
orden que cambia, su tupla de teclas completa en el esquema (tupla vacía = la
orden queda sin tecla y sigue en menús y paleta). El ``MapaTeclas`` se construye
con las teclas de fábrica del catálogo, después los cambios del esquema y
después ``teclado.personalizadas``.

N2 creó este archivo con las diferencias de 10.7; PE las contrastó con la ayuda
oficial de cada programa (21.2.5) el 8 de noviembre de 2026. Lo que no se pudo
confirmar en una fuente oficial se queda como en Norton:

- **Total Commander**: Ctrl+S (filtro rápido; se quita con Ctrl+F10), Ctrl+L
  (calcular el espacio ocupado), Mayús+F2 (comparar listas de archivos) y Ctrl+F
  (conectar con un servidor FTP), confirmadas con el texto de ``KEYBOARD.TXT``
  de Total Commander que reproduce el foro oficial de Ghisler (ghisler.ch).
- **Far Manager**: Ctrl+T (panel de árbol), Mayús+F1 (añadir a un comprimido)
  y Mayús+F2 (extraer), confirmadas en la ayuda oficial (``FarEng.hlf.m4`` del
  repositorio FarGroup/FarManager). Ctrl+I para el filtro NO aparece en la ayuda
  oficial (solo en guías de terceros): el filtro se queda con su tecla de Norton.
- **Explorador de Windows**: F2 (cambiar el nombre), Ctrl+Mayús+N (carpeta
  nueva) y Ctrl+L (llevar el foco a la barra de direcciones), confirmadas en
  «Métodos abreviados de teclado de Windows» de support.microsoft.com
  (Explorador de archivos de Windows 11).

Las teclas F de Norton (F3 a F8, F10) no cambian en ningún esquema.
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from dataclasses import dataclass

NORTON = "norton"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


ESQUEMAS: dict[str, dict[str, tuple[str, ...]]] = {
	NORTON: {},
	"total_commander": {
		"filtro_rapido": ("Ctrl+S",),
		"busqueda_rapida": (),
		"tamano_carpetas": ("Shift+Space", "Ctrl+L"),
		"vista_informacion": (),
		"quitar_filtro": ("Ctrl+F10",),
		"comparar_carpetas": ("Shift+F2",),
		"ir_linea_ordenes": (),
		"conexiones": ("Ctrl+K", "Ctrl+F"),
	},
	"far": {
		"vista_arbol": ("Ctrl+T",),
		"pestana_nueva": (),
		"comprimir": ("Alt+F5", "Shift+F1"),
		"lista_teclas": (),
		"extraer": ("Alt+F6", "Alt+F9", "Shift+F2"),
		"ir_linea_ordenes": (),
	},
	"explorador": {
		"renombrar": ("Shift+F6", "F2"),
		"menu_usuario": (),
		"crear_carpeta": ("F7", "Ctrl+Shift+N"),
		"invertir_marcas": ("KP_MULTIPLY",),
		"ir_a_carpeta": ("Ctrl+G", "Ctrl+L"),
		"vista_informacion": (),
	},
}

NOMBRES: dict[str, str] = {
	NORTON: "Norton Commander",
	"total_commander": "Total Commander",
	"far": "Far Manager",
	"explorador": N_("Explorador de Windows"),
}

DESCRIPCIONES: dict[str, str] = {
	NORTON: N_("Las teclas de fábrica de zCommander, como Norton Commander."),
	"total_commander": N_("Como Total Commander: Ctrl+S filtra, Ctrl+L calcula el tamaño, Mayús+F2 compara carpetas y Ctrl+F abre las conexiones FTP."),
	"far": N_("Como Far Manager: Ctrl+T muestra el árbol, Mayús+F1 comprime y Mayús+F2 extrae."),
	"explorador": N_("Como el Explorador de Windows: F2 cambia el nombre, Ctrl+Mayús+N crea una carpeta y Ctrl+L va a una carpeta."),
}

#: Fuente oficial con la que se contrastó cada esquema (para el diálogo y el manual).
FUENTES: dict[str, str] = {
	"total_commander": "KEYBOARD.TXT de Total Commander (citado en el foro oficial ghisler.ch)",
	"far": "Ayuda oficial de Far Manager (FarEng.hlf.m4, github.com/FarGroup/FarManager)",
	"explorador": "support.microsoft.com, «Métodos abreviados de teclado de Windows»",
}


@dataclass(frozen=True)
class Diferencia:
	"""Una orden que cambia de teclas al aplicar un esquema."""

	orden: str
	actuales: tuple[str, ...]
	nuevas: tuple[str, ...]


def aplicar(teclas: Mapping[str, tuple[str, ...]], esquema: str) -> dict[str, tuple[str, ...]]:
	"""Teclas de fábrica con las diferencias del esquema aplicadas (las órdenes que no existen se ignoran)."""
	resultado = dict(teclas)
	for id_orden, nuevas in ESQUEMAS.get(esquema, {}).items():
		if id_orden in resultado:
			resultado[id_orden] = tuple(nuevas)
	return resultado


def diferencias(fabrica: Mapping[str, tuple[str, ...]], actual: str, nuevo: str) -> list[Diferencia]:
	"""Órdenes cuyas teclas de esquema cambian al pasar de ``actual`` a ``nuevo`` (sin las personalizadas).

	:param fabrica: teclas de fábrica del catálogo (sin esquema).
	"""
	antes = aplicar(fabrica, actual)
	despues = aplicar(fabrica, nuevo)
	cambios = []
	for id_orden in sorted(set(ESQUEMAS.get(actual, {})) | set(ESQUEMAS.get(nuevo, {}))):
		if id_orden in despues and tuple(antes.get(id_orden, ())) != tuple(despues[id_orden]):
			cambios.append(Diferencia(id_orden, tuple(antes.get(id_orden, ())), tuple(despues[id_orden])))
	return cambios


def nombre(esquema: str) -> str:
	return _(NOMBRES.get(esquema, esquema))


def descripcion(esquema: str) -> str:
	return _(DESCRIPCIONES.get(esquema, ""))
