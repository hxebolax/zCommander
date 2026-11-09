# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Reglas de anuncio, color y sonido (diseño 2.0, 10.10). Sin wx.

``data/config/reglas.json``: lista ORDENADA de reglas
``{"nombre", "activa", "condicion": {...}, "efectos": {...}}``. La primera regla
activa que coincide decide los efectos de un elemento (sin mezclar). Se
evalúan al formatear la fila, con lo que ya se sabe de la entrada (sin E/S
extra); la lista guarda el resultado en caché por entrada.

Nada depende solo del color (15.2): una regla con ``color`` y sin ``texto``,
``sonido`` ni ``anuncio`` se guarda, pero el editor avisa «Este efecto solo se ve».
"""

from __future__ import annotations

import builtins
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import almacen_json
from app.services import seleccion
from app.services.vistas_modelo import EfectoFila

log = logging.getLogger(__name__)

ARCHIVO = "reglas.json"
VERSION = 1
POR_DEFECTO: dict[str, Any] = {"version": VERSION, "reglas": []}

COLORES = ("Rojo", "Verde", "Azul", "Ámbar", "Morado", "Gris")
SONIDOS = ("regla.a", "regla.b", "regla.c")
#: Bits de atributos de Windows (FILE_ATTRIBUTE_*).
ATRIBUTOS: dict[str, int] = {
	"solo_lectura": 0x1, "oculto": 0x2, "sistema": 0x4, "comprimido_ntfs": 0x800, "cifrado_ntfs": 0x4000,
}
#: Atributos que no son bits: se miran en la entrada.
ATRIBUTOS_ESPECIALES = ("enlace", "en_nube")
DIA = 86400.0


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


NOMBRES_ATRIBUTOS = {
	"solo_lectura": N_("Solo lectura"), "oculto": N_("Oculto"), "sistema": N_("Sistema"),
	"comprimido_ntfs": N_("Comprimido (NTFS)"), "cifrado_ntfs": N_("Cifrado (NTFS)"), "enlace": N_("Enlace"),
	"en_nube": N_("En la nube, sin descargar"),
}


class ErrorRegla(ValueError):
	"""Una regla no válida (mensaje en español)."""


@dataclass
class Condicion:
	patron: str = ""
	tamano_min: int | None = None
	tamano_max: int | None = None
	modificado_hace_menos_de: float | None = None
	modificado_hace_mas_de: float | None = None
	atributos: tuple[str, ...] = ()
	es_carpeta: bool | None = None

	def como_dict(self) -> dict[str, Any]:
		datos: dict[str, Any] = {}
		for clave in ("patron", "tamano_min", "tamano_max", "modificado_hace_menos_de", "modificado_hace_mas_de", "es_carpeta"):
			valor = getattr(self, clave)
			if valor not in (None, ""):
				datos[clave] = valor
		if self.atributos:
			datos["atributos"] = list(self.atributos)
		return datos

	@classmethod
	def desde_dict(cls, datos: Any) -> Condicion:
		datos = datos if isinstance(datos, dict) else {}

		def numero(clave: str, tipo=int):
			valor = datos.get(clave)
			if valor is None or isinstance(valor, bool):
				return None
			try:
				return tipo(valor)
			except (TypeError, ValueError):
				return None

		atributos = tuple(a for a in datos.get("atributos", []) or [] if a in ATRIBUTOS or a in ATRIBUTOS_ESPECIALES)
		es_carpeta = datos.get("es_carpeta")
		return cls(str(datos.get("patron", "") or ""), numero("tamano_min"), numero("tamano_max"),
			numero("modificado_hace_menos_de", float), numero("modificado_hace_mas_de", float), atributos,
			bool(es_carpeta) if isinstance(es_carpeta, bool) else None)

	def vacia(self) -> bool:
		return not self.como_dict()


@dataclass
class Regla:
	nombre: str
	activa: bool = True
	condicion: Condicion = field(default_factory=Condicion)
	color: str | None = None
	texto: str = ""
	sonido: str = ""
	anuncio: str = ""

	def efecto(self) -> EfectoFila:
		return EfectoFila(self.color, self.texto, self.sonido, self.anuncio)

	def solo_color(self) -> bool:
		"""Avisa «Este efecto solo se ve»: un color sin texto, sonido ni anuncio (15.2)."""
		return bool(self.color) and not (self.texto or self.sonido or self.anuncio)

	def como_dict(self) -> dict[str, Any]:
		efectos = {k: v for k, v in (("color", self.color), ("texto", self.texto), ("sonido", self.sonido),
			("anuncio", self.anuncio)) if v}
		return {"nombre": self.nombre, "activa": self.activa, "condicion": self.condicion.como_dict(), "efectos": efectos}

	@classmethod
	def desde_dict(cls, datos: Any) -> Regla:
		if not isinstance(datos, dict) or not str(datos.get("nombre", "")).strip():
			raise ErrorRegla(_("Una regla no tiene nombre"))
		efectos = datos.get("efectos") if isinstance(datos.get("efectos"), dict) else {}
		color = efectos.get("color")
		sonido = str(efectos.get("sonido", "") or "")
		return cls(str(datos["nombre"]).strip(), bool(datos.get("activa", True)), Condicion.desde_dict(datos.get("condicion")),
			color if color in COLORES else None, str(efectos.get("texto", "") or "")[:24],
			sonido if sonido in SONIDOS else "", str(efectos.get("anuncio", "") or ""))


def validar(regla: Regla) -> None:
	"""``ErrorRegla`` con el motivo si la regla no se puede guardar."""
	if not regla.nombre.strip():
		raise ErrorRegla(_("La regla necesita un nombre"))
	if regla.condicion.vacia():
		raise ErrorRegla(_("La regla necesita al menos una condición"))
	if not (regla.color or regla.texto or regla.sonido or regla.anuncio):
		raise ErrorRegla(_("La regla necesita al menos un efecto: color, texto, sonido o anuncio"))
	c = regla.condicion
	if c.tamano_min is not None and c.tamano_max is not None and c.tamano_min > c.tamano_max:
		raise ErrorRegla(_("El tamaño mínimo es mayor que el máximo"))
	if c.patron:
		try:
			seleccion.coincide("x", c.patron)
		except Exception as error:  # noqa: BLE001 - re.error u otro: patrón no válido
			raise ErrorRegla(_("El patrón no es válido: {e}").format(e=error)) from error


def cargar(carpeta: Path | None = None) -> list[Regla]:
	datos = almacen_json.leer(ARCHIVO, POR_DEFECTO, carpeta)
	resultado: list[Regla] = []
	for elemento in datos.get("reglas", []) or []:
		try:
			resultado.append(Regla.desde_dict(elemento))
		except ErrorRegla as error:
			log.warning("Regla descartada: %s", error)
	return resultado


def guardar(reglas: Sequence[Regla], carpeta: Path | None = None) -> None:
	almacen_json.escribir(ARCHIVO, {"version": VERSION, "reglas": [r.como_dict() for r in reglas]}, carpeta)


def coincide(condicion: Condicion, entrada: Any, ahora: float | None = None) -> bool:
	"""Todas las partes puestas de la condición se cumplen (con lo que ya trae la entrada)."""
	if getattr(entrada, "es_superior", False):
		return False
	es_carpeta = bool(getattr(entrada, "es_carpeta", False))
	if condicion.es_carpeta is not None and condicion.es_carpeta != es_carpeta:
		return False
	if condicion.patron and not seleccion.coincide(getattr(entrada, "nombre", ""), condicion.patron):
		return False
	tamano = int(getattr(entrada, "tamano", -1))
	if condicion.tamano_min is not None and (tamano < 0 or tamano < condicion.tamano_min):
		return False
	if condicion.tamano_max is not None and (tamano < 0 or tamano > condicion.tamano_max):
		return False
	modificado = float(getattr(entrada, "modificado", 0.0) or 0.0)
	if condicion.modificado_hace_menos_de is not None or condicion.modificado_hace_mas_de is not None:
		if modificado <= 0:
			return False
		dias = ((time.time() if ahora is None else ahora) - modificado) / DIA
		if condicion.modificado_hace_menos_de is not None and dias >= condicion.modificado_hace_menos_de:
			return False
		if condicion.modificado_hace_mas_de is not None and dias <= condicion.modificado_hace_mas_de:
			return False
	bits = int(getattr(entrada, "atributos", 0) or 0)
	for atributo in condicion.atributos:
		if atributo == "enlace":
			if not getattr(entrada, "es_enlace", False):
				return False
		elif atributo == "en_nube":
			if not getattr(entrada, "en_nube", False):
				return False
		elif not bits & ATRIBUTOS.get(atributo, 0):
			return False
	return True


def primera(reglas: Sequence[Regla], entrada: Any, ahora: float | None = None) -> Regla | None:
	"""La primera regla activa que coincide, o ``None``."""
	for regla in reglas:
		if regla.activa and coincide(regla.condicion, entrada, ahora):
			return regla
	return None


def decorador(fuente: Callable[[], Sequence[Regla]], activas: Callable[[], bool]) -> Callable[[Any], EfectoFila | None]:
	"""Función para ``fijar_decorador_fila``: efectos de la primera regla que coincide, o ``None``."""

	def efecto(entrada: Any) -> EfectoFila | None:
		if not activas():
			return None
		regla = primera(fuente(), entrada)
		return regla.efecto() if regla is not None else None

	return efecto


def describir(regla: Regla) -> str:
	"""Resumen en español de la condición («*.iso, más de 1 GB, solo lectura»)."""
	from app.services import formato

	c = regla.condicion
	partes: list[str] = []
	if c.patron:
		partes.append(c.patron)
	if c.es_carpeta is True:
		partes.append(_("carpetas"))
	elif c.es_carpeta is False:
		partes.append(_("archivos"))
	if c.tamano_min is not None:
		partes.append(_("más de {t}").format(t=formato.tamano_legible(c.tamano_min)))
	if c.tamano_max is not None:
		partes.append(_("menos de {t}").format(t=formato.tamano_legible(c.tamano_max)))
	if c.modificado_hace_menos_de is not None:
		partes.append(_("modificado hace menos de {d} días").format(d=_numero(c.modificado_hace_menos_de)))
	if c.modificado_hace_mas_de is not None:
		partes.append(_("modificado hace más de {d} días").format(d=_numero(c.modificado_hace_mas_de)))
	partes.extend(_(NOMBRES_ATRIBUTOS[a]).lower() for a in c.atributos if a in NOMBRES_ATRIBUTOS)
	return ", ".join(partes)


def describir_efectos(regla: Regla) -> str:
	partes = []
	if regla.texto:
		partes.append(_("texto «{t}»").format(t=regla.texto))
	if regla.color:
		partes.append(_("color {c}").format(c=_(regla.color).lower()))
	if regla.sonido:
		partes.append(_("sonido {s}").format(s=regla.sonido[-1].upper()))
	if regla.anuncio:
		partes.append(_("anuncio «{a}»").format(a=regla.anuncio))
	return ", ".join(partes)


def _numero(valor: float) -> str:
	return str(int(valor)) if float(valor).is_integer() else str(valor).replace(".", ",")
