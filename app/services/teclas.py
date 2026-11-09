# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Teclas: formato canónico, nombres en español y mapa de teclas.

Formato canónico (el que se guarda en la configuración y se pone tras ``\\t``
en los menús, porque wx lo entiende como acelerador):

- Modificadores en este orden: ``Ctrl+``, ``Alt+``, ``Shift+``.
- Tecla: letra mayúscula (``A``), dígito (``1``), ``F1`` a ``F24``, ``Return``,
  ``Back``, ``Delete``, ``Insert``, ``Space``, ``Tab``, ``Escape``, ``Home``,
  ``End``, ``PgUp``, ``PgDn``, ``Up``, ``Down``, ``Left``, ``Right``,
  ``KP_ADD``, ``KP_SUBTRACT``, ``KP_MULTIPLY``, ``KP_DIVIDE``, ``Menu`` y los
  signos ``.`` y ``,``.

Ejemplos: ``Ctrl+Shift+F10``, ``Alt+Left``, ``KP_ADD``, ``Shift+Space``.

Este módulo no importa wx (capa de servicios): la conversión de un
``wx.KeyEvent`` a esta cadena está en ``app/ui/teclado_eventos.py``.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


MODIFICADORES = ("Ctrl", "Alt", "Shift")

_ALIAS = {
	"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "mayús": "Shift", "mayus": "Shift",
	"enter": "Return", "intro": "Return", "return": "Return", "retroceso": "Back", "backspace": "Back", "back": "Back",
	"supr": "Delete", "del": "Delete", "delete": "Delete", "ins": "Insert", "insert": "Insert",
	"espacio": "Space", "space": "Space", "tab": "Tab", "esc": "Escape", "escape": "Escape",
	"inicio": "Home", "home": "Home", "fin": "End", "end": "End",
	"repág": "PgUp", "re pág": "PgUp", "pgup": "PgUp", "pageup": "PgUp", "page up": "PgUp",
	"avpág": "PgDn", "av pág": "PgDn", "pgdn": "PgDn", "pagedown": "PgDn", "page down": "PgDn",
	"arriba": "Up", "up": "Up", "abajo": "Down", "down": "Down", "izquierda": "Left", "left": "Left",
	"derecha": "Right", "right": "Right", "kp_add": "KP_ADD", "num +": "KP_ADD", "num+": "KP_ADD",
	"kp_subtract": "KP_SUBTRACT", "num -": "KP_SUBTRACT", "num-": "KP_SUBTRACT",
	"kp_multiply": "KP_MULTIPLY", "num *": "KP_MULTIPLY", "num*": "KP_MULTIPLY",
	"kp_divide": "KP_DIVIDE", "num /": "KP_DIVIDE", "num/": "KP_DIVIDE",
	"menu": "Menu", "aplicaciones": "Menu",
}

_NOMBRES_ES = {
	"Return": "Intro", "Back": "Retroceso", "Delete": "Supr", "Insert": "Insert", "Space": "Espacio",
	"Tab": "Tab", "Escape": "Escape", "Home": "Inicio", "End": "Fin", "PgUp": "Re Pág", "PgDn": "Av Pág",
	"Up": "Arriba", "Down": "Abajo", "Left": "Izquierda", "Right": "Derecha", "KP_ADD": "Num +",
	"KP_SUBTRACT": "Num -", "KP_MULTIPLY": "Num *", "KP_DIVIDE": "Num /", "Menu": "Aplicaciones",
	".": "punto", ",": "coma",
}
_MODIFICADORES_ES = {"Ctrl": "Ctrl", "Alt": "Alt", "Shift": "Mayús"}

#: Teclas que nunca se pueden asignar (motivo para explicarlo en el diálogo).
RESERVADAS: dict[str, str] = {
	"Alt+F4": "Windows la usa para cerrar la ventana.",
	"Alt+Space": "Abre el menú de sistema de la ventana.",
	"Ctrl+Escape": "Windows la usa para el menú Inicio.",
	"Ctrl+Shift+Escape": "Windows la usa para el Administrador de tareas.",
	"Alt+Tab": "Windows la usa para cambiar de ventana.",
	"Alt+Shift+Tab": "Windows la usa para cambiar de ventana.",
}

#: Teclas de edición: con el foco en un campo de texto las recibe el campo.
EDICION: frozenset[str] = frozenset({
	"Space", "Shift+Space", "Back", "Ctrl+Back", "Delete", "Ctrl+Delete", "Home", "End", "Shift+Home", "Shift+End",
	"Left", "Right", "Shift+Left", "Shift+Right", "Ctrl+Left", "Ctrl+Right", "Ctrl+Shift+Left", "Ctrl+Shift+Right",
	"Ctrl+A", "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z", "Ctrl+Y", "Insert", "Shift+Insert", "Ctrl+Insert",
	"Shift+Delete", "Up", "Down", "Ctrl+Home", "Ctrl+End", "Ctrl+Shift+Home", "Ctrl+Shift+End", "PgUp", "PgDn",
	"Shift+PgUp", "Shift+PgDn", "Shift+Up", "Shift+Down",
})
"""Con el foco en la línea de órdenes, el despachador consulta ANTES el ámbito «linea»
(Intro, Arriba, Abajo, Escape y Tab son órdenes suyas); el resto de teclas de
edición son del campo. En cualquier otro campo de texto, todas estas son del campo."""


def normalizar(texto: str) -> str:
	"""Convierte cualquier forma razonable al formato canónico.

	``"ctrl+mayús+f10"`` → ``"Ctrl+Shift+F10"``; ``"Num +"`` → ``"KP_ADD"``;
	``"ctrl++"`` → ``"Ctrl++"``. Lanza ``ValueError`` si está vacía.
	"""
	texto = (texto or "").strip()
	if not texto:
		raise ValueError("Tecla vacía")
	alias_completo = _ALIAS.get(texto.lower())
	if alias_completo:
		return alias_completo
	if texto.endswith("++"):
		partes = [*texto[:-2].split("+"), "+"]
	else:
		partes = texto.split("+")
	partes = [p.strip() for p in partes]
	*mods, tecla = partes
	presentes = set()
	for mod in mods:
		canonico = _ALIAS.get(mod.lower(), mod)
		if canonico not in MODIFICADORES:
			# «Num +» con modificadores: «Ctrl+Num +» llega partido.
			if mod.lower() == "num" and tecla == "":
				tecla = "num +"
				continue
			raise ValueError(f"Modificador desconocido: {mod}")
		presentes.add(canonico)
	tecla_l = tecla.lower()
	tecla = _ALIAS.get(tecla_l, tecla)
	if len(tecla) == 1:
		tecla = tecla.upper()
	elif tecla[:1] in "fF" and tecla[1:].isdigit():
		tecla = "F" + tecla[1:]
	orden = [m for m in MODIFICADORES if m in presentes]
	return "+".join([*orden, tecla])


def nombre_visible(canonica: str) -> str:
	"""Nombre en español para el manual y los anuncios: ``Ctrl+Shift+F10`` → ``Ctrl+Mayús+F10``."""
	if canonica.endswith("++"):
		*mods, tecla = [*canonica[:-2].split("+"), "+"]
	else:
		*mods, tecla = canonica.split("+")
	partes = [_MODIFICADORES_ES.get(m, m) for m in mods]
	partes.append(_NOMBRES_ES.get(tecla, tecla))
	return "+".join(partes)


def es_reservada(canonica: str) -> bool:
	return canonica in RESERVADAS


@dataclass(frozen=True)
class Choque:
	"""Una tecla asignada a más de una orden, o una reservada."""

	tecla: str
	ordenes: tuple[str, ...]
	motivo: str


#: Ámbitos que se solapan: una orden «global» funciona también en los otros dos.
SOLAPES = {("global", "panel"), ("panel", "global"), ("global", "linea"), ("linea", "global"), ("global", "global"),
	("panel", "panel"), ("linea", "linea")}


class MapaTeclas:
	"""Tecla canónica (y ámbito) → id de orden, con las sustituciones de la persona.

	:param por_defecto: ``{id_orden: [teclas]}`` del catálogo.
	:param ambitos: ``{id_orden: "panel" | "global" | "linea"}``; sin dato, «global».
	:param personalizadas: ``{id_orden: [teclas]}`` de la configuración; una lista
		vacía deja la orden sin tecla.
	:param fijas: órdenes cuyas teclas no se pueden cambiar ni dar a otra orden
		(Tab, Ctrl+H, el menú contextual).

	Dos órdenes pueden compartir tecla si sus ámbitos no se solapan (Intro abre
	en el panel y ejecuta en la línea de órdenes).
	"""

	def __init__(
		self,
		por_defecto: Mapping[str, Iterable[str]],
		ambitos: Mapping[str, str] | None = None,
		personalizadas: Mapping[str, Iterable[str]] | None = None,
		fijas: Iterable[str] = (),
	):
		self.fijas = frozenset(fijas)
		self._ambitos = dict(ambitos or {})
		self._por_orden: dict[str, tuple[str, ...]] = {}
		for orden, teclas in por_defecto.items():
			self._por_orden[orden] = tuple(normalizar(t) for t in teclas)
		teclas_fijas = {t for o in self.fijas for t in self._por_orden.get(o, ())}
		for orden, teclas in (personalizadas or {}).items():
			if orden in self._por_orden and orden not in self.fijas:
				# Una tecla fija no se puede robar: se descarta aquí y el diálogo
				# del mapa de teclas ya impide elegirla.
				self._por_orden[orden] = tuple(t for t in (normalizar(x) for x in teclas) if t not in teclas_fijas)
		self._indice: dict[tuple[str, str], str] = {}
		self.choques: list[Choque] = []
		usados: dict[str, list[str]] = {}
		for orden, teclas in self._por_orden.items():
			for tecla in teclas:
				usados.setdefault(tecla, []).append(orden)
		for tecla, ordenes in usados.items():
			if es_reservada(tecla):
				self.choques.append(Choque(tecla, tuple(ordenes), _(RESERVADAS[tecla])))
				continue
			for i, orden in enumerate(ordenes):
				ambito = self.ambito(orden)
				otras = [o for o in ordenes[:i] if (self.ambito(o), ambito) in SOLAPES]
				if otras:
					self.choques.append(Choque(tecla, (*otras, orden), _("Asignada a varias órdenes.")))
					continue
				self._indice[(ambito, tecla)] = orden

	def ambito(self, orden: str) -> str:
		return self._ambitos.get(orden, "global")

	def orden_de(self, tecla: str, ambitos_activos: Iterable[str] = ("panel", "global")) -> str | None:
		"""Orden de ``tecla`` en el primer ámbito activo que la tenga."""
		for ambito in ambitos_activos:
			orden = self._indice.get((ambito, tecla))
			if orden:
				return orden
		return None

	def teclas_de(self, orden: str) -> tuple[str, ...]:
		return self._por_orden.get(orden, ())

	def primera_tecla(self, orden: str) -> str:
		teclas = self.teclas_de(orden)
		return teclas[0] if teclas else ""

	def como_dict(self) -> dict[str, tuple[str, ...]]:
		return dict(self._por_orden)
