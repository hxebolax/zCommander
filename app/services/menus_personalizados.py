# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Menús, barra de botones y barra de teclas configurables (diseño 2.0, 10.6 y 10.11). Sin wx.

``data/config/menus.json``::

	{"version": 1,
	 "ocultas": ["sin_ordenar", "ordenar_tipo"],
	 "mis_ordenes": ["macro:Fotos a la copia", "-", "zc.reproductor:reproducir", "favoritos"],
	 "barra_botones": ["copiar", "mover", "eliminar", "-", "zc.nubes:cuentas"],
	 "barra_teclas": {"Shift+F7": "zc.duplicados:buscar"}}

- **Ocultar** quita elementos de los menús de fábrica; no se reordenan (el
  manual y los menús siguen iguales para todo el mundo). Las órdenes ocultas
  siguen con su tecla y en la paleta.
- **Mis órdenes**: menú propio (Alt+R) con órdenes, macros, órdenes de
  complementos y separadores («-»), en el orden de la persona.
- **Menús según el nivel** (10.11): con ``vista.menus_por_nivel`` y sin
  «Ver todas las órdenes», los menús muestran solo las órdenes de nivel menor
  o igual al del perfil (Personalizado cuenta como avanzado).
- Un hueco de la barra de teclas (``"Shift+F7"``) puede llevar otra orden; la
  etiqueta corta la escribe la persona o se calcula de la orden.

``Personalizador`` es lo que la ventana aplica a los menús que devuelve
``ordenes.menus()`` (enganche pedido en ``docs/revision/peticiones-pe.md``).
"""

from __future__ import annotations

import builtins
import copy
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import almacen_json

log = logging.getLogger(__name__)

ARCHIVO = "menus.json"
VERSION = 1
SEPARADOR = "-"
POR_DEFECTO: dict[str, Any] = {"version": VERSION, "ocultas": [], "mis_ordenes": [], "barra_botones": [], "barra_teclas": {}}
NIVELES = ("novato", "intermedio", "avanzado")
LADO = "@lado"
TITULO_MIS_ORDENES = "Mis ó&rdenes"
TITULO_OPCIONES = "&Opciones"
TODAS = "todas_las_ordenes"
MODIFICADORES = ("", "Shift", "Ctrl", "Alt")
#: Barra de botones de fábrica (cuando la persona aún no ha elegido ninguno).
BOTONES_FABRICA = ("ver", "editar", "copiar", "mover", "crear_carpeta", "eliminar", SEPARADOR, "buscar_archivos", "comparar_carpetas")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class DatosMenus:
	ocultas: list[str] = field(default_factory=list)
	mis_ordenes: list[str] = field(default_factory=list)
	barra_botones: list[str] = field(default_factory=list)
	#: hueco («Shift+F7») → (id de orden, etiqueta corta o «» para calcularla).
	barra_teclas: dict[str, tuple[str, str]] = field(default_factory=dict)

	def como_dict(self) -> dict[str, Any]:
		teclas: dict[str, Any] = {}
		for hueco, (orden, etiqueta) in self.barra_teclas.items():
			teclas[hueco] = {"orden": orden, "etiqueta": etiqueta} if etiqueta else orden
		return {"version": VERSION, "ocultas": list(self.ocultas), "mis_ordenes": list(self.mis_ordenes),
			"barra_botones": list(self.barra_botones), "barra_teclas": teclas}


def _lista(valor: Any) -> list[str]:
	return [str(v) for v in valor if isinstance(v, str) and v.strip()] if isinstance(valor, list) else []


def cargar(carpeta: Path | None = None) -> DatosMenus:
	datos = almacen_json.leer(ARCHIVO, POR_DEFECTO, carpeta)
	teclas: dict[str, tuple[str, str]] = {}
	for hueco, valor in (datos.get("barra_teclas") or {}).items():
		if isinstance(valor, str) and valor:
			teclas[str(hueco)] = (valor, "")
		elif isinstance(valor, dict) and isinstance(valor.get("orden"), str):
			teclas[str(hueco)] = (valor["orden"], str(valor.get("etiqueta", "") or ""))
	return DatosMenus(_lista(datos.get("ocultas")), _lista(datos.get("mis_ordenes")), _lista(datos.get("barra_botones")), teclas)


def guardar(datos: DatosMenus, carpeta: Path | None = None) -> None:
	almacen_json.escribir(ARCHIVO, datos.como_dict(), carpeta)


def hueco(modificador: str, numero: int) -> str:
	return f"{modificador}+F{numero}" if modificador else f"F{numero}"


def etiqueta_corta(etiqueta: str, largo: int = 7) -> str:
	"""«&Buscar duplicados...» → «Buscar»: la primera palabra, sin «&» ni puntos, como mucho ``largo`` letras."""
	limpia = etiqueta.replace("&&", "\x00").replace("&", "").replace("\x00", "&").replace("...", "").strip()
	palabra = limpia.split()[0] if limpia.split() else limpia
	return palabra[:largo]


def nivel_del_perfil(perfil: str) -> str:
	"""Novato e Intermedio son su nivel; Avanzado y Personalizado, avanzado (10.11)."""
	return perfil if perfil in ("novato", "intermedio") else "avanzado"


def _letra(etiqueta: str) -> str | None:
	i = 0
	while True:
		i = etiqueta.find("&", i)
		if i < 0 or i + 1 >= len(etiqueta):
			return None
		if etiqueta[i + 1] == "&":
			i += 2
			continue
		return etiqueta[i + 1].lower()


def _limpiar(elementos: list) -> list:
	"""Sin separadores al principio, al final ni seguidos, y sin submenús vacíos."""
	resultado: list = []
	for elemento in elementos:
		if isinstance(elemento, tuple) and isinstance(elemento[1], list | tuple):
			hijos = _limpiar(list(elemento[1]))
			if not [h for h in hijos if h is not None]:
				continue
			elemento = (elemento[0], hijos)
		if elemento is None and (not resultado or resultado[-1] is None):
			continue
		resultado.append(elemento)
	while resultado and resultado[-1] is None:
		resultado.pop()
	return resultado


class Personalizador:
	"""Aplica ``menus.json`` y los menús por nivel a la forma de ``ordenes.menus()``.

	:param datos: función que da los ``DatosMenus`` vigentes (se leen al construir los menús).
	:param nivel: nivel del perfil actual (``novato``, ``intermedio`` o ``avanzado``).
	:param por_nivel: si ``vista.menus_por_nivel`` está activa.
	:param todas: si la casilla «Ver todas las órdenes» está marcada.
	:param orden: ``orden(id) -> Orden | None`` del catálogo vivo (para el nivel, la etiqueta y si existe).
	:param macros_en_menu: nombres de las macros con ``menu = true``.
	"""

	def __init__(self, datos: Callable[[], DatosMenus], nivel: Callable[[], str], por_nivel: Callable[[], bool],
			todas: Callable[[], bool], orden: Callable[[str], Any], macros_en_menu: Callable[[], Sequence[str]] = lambda: ()) -> None:
		self._datos = datos
		self._nivel = nivel
		self._por_nivel = por_nivel
		self._todas = todas
		self._orden = orden
		self._macros = macros_en_menu

	def _filtrando_nivel(self) -> int | None:
		if not self._por_nivel() or self._todas():
			return None
		return NIVELES.index(self._nivel()) if self._nivel() in NIVELES else len(NIVELES) - 1

	def _visible(self, id_orden: str, ocultas: set[str], tope: int | None) -> bool:
		if id_orden in ocultas and id_orden != TODAS:
			return False
		if tope is not None:
			orden = self._orden(id_orden)
			nivel = getattr(orden, "nivel", "novato") if orden is not None else "novato"
			if nivel in NIVELES and NIVELES.index(nivel) > tope:
				return False
		return True

	def lista(self, elementos: Sequence) -> list:
		"""Un menú (lista de ids, ``None`` y submenús) sin lo oculto ni lo de otro nivel."""
		datos = self._datos()
		return self._filtrar(list(elementos), set(datos.ocultas), self._filtrando_nivel())

	def _filtrar(self, elementos: list, ocultas: set[str], tope: int | None) -> list:
		resultado: list = []
		for elemento in elementos:
			if elemento is None:
				resultado.append(None)
			elif isinstance(elemento, tuple):
				resultado.append((elemento[0], self._filtrar(list(elemento[1]), ocultas, tope)))
			elif self._visible(str(elemento), ocultas, tope):
				resultado.append(elemento)
		return _limpiar(resultado)

	def mis_ordenes(self) -> list:
		"""Elementos de «Mis órdenes»: los de la persona y las macros con ``menu`` que no ha puesto."""
		datos = self._datos()
		elementos: list = []
		for elemento in datos.mis_ordenes:
			if elemento == SEPARADOR:
				elementos.append(None)
			elif self._orden(elemento) is not None:
				elementos.append(elemento)
		puestas = set(datos.mis_ordenes)
		macros = [f"macro:{n}" for n in self._macros() if f"macro:{n}" not in puestas and self._orden(f"macro:{n}") is not None]
		if macros:
			elementos += ([None] if elementos else []) + macros
		return _limpiar(elementos)

	def menus(self, originales: Sequence[tuple]) -> tuple:
		"""La barra de menús personalizada (misma forma que ``ordenes.menus()``)."""
		datos = self._datos()
		ocultas = set(datos.ocultas)
		tope = self._filtrando_nivel()
		resultado: list[tuple] = []
		for titulo, contenido in originales:
			if titulo == TITULO_MIS_ORDENES:
				continue  # se rehace abajo con lo de la persona
			if contenido == LADO:
				resultado.append((titulo, contenido))
				continue
			elementos = self._filtrar(list(contenido), ocultas, tope)
			if tope is not None and TODAS not in elementos:
				# Al final de cada menú, «Ver todas las órdenes», si su letra está libre en ese menú (10.11).
				orden = self._orden(TODAS)
				letra = _letra(getattr(orden, "etiqueta", "")) if orden is not None else None
				ocupadas = {_letra(e[0] if isinstance(e, tuple) else getattr(self._orden(e), "etiqueta", "")) for e in elementos if e}
				if orden is not None and letra not in ocupadas:
					elementos = [*elementos, None, TODAS]
			resultado.append((titulo, elementos))
			if titulo == TITULO_OPCIONES:
				mis = self.mis_ordenes()
				if mis:
					resultado.append((TITULO_MIS_ORDENES, mis))
		return tuple(resultado)

	def barra_teclas(self, modificador: str, fabrica: Sequence[tuple[str, str, str]]) -> tuple[tuple[str, str, str], ...]:
		"""Los diez huecos de un modificador con lo que la persona cambió (tecla, orden, etiqueta)."""
		cambios = self._datos().barra_teclas
		resultado = []
		for indice, (tecla, orden, texto) in enumerate(fabrica):
			propio = cambios.get(hueco(modificador, indice + 1))
			if propio is not None and (propio[0] == "" or self._orden(propio[0]) is not None):
				id_orden, etiqueta = propio
				if id_orden and not etiqueta:
					etiqueta = etiqueta_corta(_(getattr(self._orden(id_orden), "etiqueta", id_orden)))
				resultado.append((tecla, id_orden, etiqueta))
			else:
				resultado.append((tecla, orden, texto))
		return tuple(resultado)


def botones(datos: DatosMenus, existe: Callable[[str], bool]) -> list[str]:
	"""Órdenes de la barra de botones (``"-"`` = separador), sin las que ya no existen."""
	lista = datos.barra_botones or list(BOTONES_FABRICA)
	resultado = [b for b in lista if b == SEPARADOR or existe(b)]
	while resultado and resultado[0] == SEPARADOR:
		resultado.pop(0)
	while resultado and resultado[-1] == SEPARADOR:
		resultado.pop()
	return resultado


def mover(lista: list, indice: int, paso: int) -> int:
	destino = indice + paso
	if not 0 <= indice < len(lista) or not 0 <= destino < len(lista):
		return indice
	lista[indice], lista[destino] = lista[destino], lista[indice]
	return destino


def copia(datos: DatosMenus) -> DatosMenus:
	return copy.deepcopy(datos)


def teclas_ocupadas(barra: Mapping[str, tuple[str, str]]) -> set[str]:
	return {h for h, (orden, _e) in barra.items() if orden}
