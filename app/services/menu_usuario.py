# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Menú de usuario (F2): entradas propias y menú local de una carpeta con confianza.

Formato de ``data/config/menu_usuario.json`` y del local ``zcommander.menu.json``
(sección 10 del diseño)::

	{"version": 1, "entradas": [{"etiqueta": "Comprimir con 7-Zip", "tecla": "A",
		"ordenes": ["7z a %O\\%N.7z %M"], "consola": false, "refrescar": true, "submenu": []}]}

Una entrada con ``submenu`` no vacío es un submenú y sus ``ordenes`` se ignoran.

Seguridad del menú local (sección 14): un ``zcommander.menu.json`` que llega
con una carpeta descargada o de otra persona ejecutaría sus órdenes con solo
pulsar su tecla. Por eso solo se usa si la persona confía en esa carpeta, y la
confianza se guarda como ruta y SHA-256 del archivo en
``seguridad.menus_locales_confiados``: si el archivo cambia, la suma deja de
coincidir y se vuelve a preguntar. La suma se calcula sobre los MISMOS bytes
que se interpretan, para que nadie pueda cambiar el archivo entre la
comprobación y la lectura.

Sin wx: lo usa ``app/ui/acciones/dialogos_f.py`` y se prueba sin ventanas.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import almacen_json

log = logging.getLogger(__name__)

NOMBRE = "menu_usuario.json"
NOMBRE_LOCAL = "zcommander.menu.json"
CLAVE_CONFIANZA = "seguridad.menus_locales_confiados"
VERSION = 1
#: Profundidad máxima de submenús: un archivo hostil con miles de niveles no debe agotar la pila.
PROFUNDIDAD_MAXIMA = 8
#: Tamaño máximo del menú local: es texto de unas pocas entradas; algo mayor no es un menú.
TAMANO_MAXIMO_LOCAL = 512 * 1024

CONFIADO, CAMBIADO, DESCONOCIDO = "confiado", "cambiado", "desconocido"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class EntradaMenu:
	"""Una entrada del menú: una o varias órdenes, o un submenú."""

	etiqueta: str
	tecla: str = ""
	ordenes: list[str] = field(default_factory=list)
	consola: bool = False
	refrescar: bool = True
	submenu: list[EntradaMenu] = field(default_factory=list)
	#: Viene del menú local de la carpeta (no se guarda en el archivo).
	local: bool = False

	@property
	def es_submenu(self) -> bool:
		return bool(self.submenu)

	def texto(self) -> str:
		"""Texto de la lista: «A: Comprimir con 7-Zip», con «(submenú)» o «(de esta carpeta)» si toca."""
		partes = f"{self.tecla}: {self.etiqueta}" if self.tecla else self.etiqueta
		if self.es_submenu:
			partes += " " + _("(submenú)")
		if self.local:
			partes += " " + _("(de esta carpeta)")
		return partes


# ── Conversión desde y hacia JSON ────────────────────────────────────────────

def normalizar_tecla(tecla: Any) -> str:
	"""Una sola letra o dígito en mayúscula; cualquier otra cosa, sin tecla."""
	if not isinstance(tecla, str):
		return ""
	tecla = tecla.strip()
	return tecla.upper() if len(tecla) == 1 and tecla.isalnum() else ""


def desde_dict(datos: Any, profundidad: int = 0, local: bool = False) -> EntradaMenu | None:
	"""Entrada a partir de un diccionario del JSON; ``None`` si no tiene la forma esperada."""
	if not isinstance(datos, dict) or not isinstance(datos.get("etiqueta"), str) or not datos["etiqueta"].strip():
		return None
	ordenes = datos.get("ordenes", [])
	if isinstance(ordenes, str):
		ordenes = [ordenes]
	if not isinstance(ordenes, list):
		ordenes = []
	submenu: list[EntradaMenu] = []
	if profundidad < PROFUNDIDAD_MAXIMA and isinstance(datos.get("submenu"), list):
		submenu = leer_entradas(datos["submenu"], profundidad + 1, local)
	elif datos.get("submenu"):
		log.warning("Submenú «%s» descartado: pasa de %d niveles", datos["etiqueta"], PROFUNDIDAD_MAXIMA)
	return EntradaMenu(
		etiqueta=datos["etiqueta"].strip(),
		tecla=normalizar_tecla(datos.get("tecla", "")),
		ordenes=[o for o in ordenes if isinstance(o, str) and o.strip()],
		consola=bool(datos.get("consola", False)),
		refrescar=bool(datos.get("refrescar", True)),
		submenu=submenu,
		local=local,
	)


def leer_entradas(lista: Any, profundidad: int = 0, local: bool = False) -> list[EntradaMenu]:
	if not isinstance(lista, list):
		return []
	entradas = []
	for datos in lista:
		entrada = desde_dict(datos, profundidad, local)
		if entrada is None:
			log.warning("Entrada del menú de usuario mal formada descartada: %r", datos)
			continue
		entradas.append(entrada)
	return entradas


def a_dict(entrada: EntradaMenu) -> dict:
	return {
		"etiqueta": entrada.etiqueta,
		"tecla": entrada.tecla,
		"ordenes": [] if entrada.es_submenu else list(entrada.ordenes),
		"consola": entrada.consola,
		"refrescar": entrada.refrescar,
		"submenu": [a_dict(e) for e in entrada.submenu],
	}


def cargar() -> list[EntradaMenu]:
	"""Menú global de ``data/config/menu_usuario.json`` (vacío si no existe)."""
	datos = almacen_json.leer(NOMBRE, {"version": VERSION, "entradas": []})
	return leer_entradas(datos.get("entradas", []))


def guardar(entradas: list[EntradaMenu]) -> None:
	""":raises OSError: si no se pudo escribir."""
	almacen_json.escribir(NOMBRE, {"version": VERSION, "entradas": [a_dict(e) for e in entradas]})


# ── Menú local y confianza ───────────────────────────────────────────────────

@dataclass
class MenuLocal:
	"""El ``zcommander.menu.json`` de una carpeta, leído una sola vez."""

	carpeta: str
	ruta: str
	suma: str
	entradas: list[EntradaMenu]
	error: str = ""


def suma(contenido: bytes) -> str:
	return hashlib.sha256(contenido).hexdigest()


def clave_carpeta(carpeta: str) -> str:
	"""Clave de la carpeta en ``menus_locales_confiados``: absoluta y sin distinguir mayúsculas.

	«D:» sola sería la carpeta actual de esa unidad para ``abspath``: se le pone la barra.
	"""
	ruta = carpeta.rstrip("\\/")
	if len(ruta) == 2 and ruta[1] == ":":
		ruta += "\\"
	return os.path.normcase(os.path.abspath(ruta))


def leer_local(carpeta: str | None) -> MenuLocal | None:
	"""Menú local de ``carpeta`` (solo del disco), o ``None`` si no hay.

	Un archivo dañado o enorme se devuelve con ``error`` y sin entradas: la
	persona debe saber que existe aunque no se pueda usar.
	"""
	if not carpeta:
		return None
	archivo = Path(carpeta) / NOMBRE_LOCAL
	try:
		if not archivo.is_file():
			return None
		if archivo.stat().st_size > TAMANO_MAXIMO_LOCAL:
			return MenuLocal(carpeta, str(archivo), "", [], _("El menú local es demasiado grande para ser un menú."))
		contenido = archivo.read_bytes()
	except OSError:
		log.warning("No se pudo leer el menú local %s", archivo, exc_info=True)
		return None
	resumen = suma(contenido)
	try:
		datos = json.loads(contenido.decode("utf-8-sig"))
	except (UnicodeDecodeError, ValueError) as error:
		log.warning("Menú local dañado en %s: %s", archivo, error)
		return MenuLocal(carpeta, str(archivo), resumen, [], _("El menú local no es un JSON válido: {e}").format(e=error))
	entradas = leer_entradas(datos.get("entradas", []) if isinstance(datos, dict) else [], local=True)
	return MenuLocal(carpeta, str(archivo), resumen, entradas)


def estado_confianza(confiados: dict, menu: MenuLocal) -> str:
	"""``confiado`` (misma suma), ``cambiado`` (se confió en otra versión) o ``desconocido``."""
	guardada = confiados.get(clave_carpeta(menu.carpeta)) if isinstance(confiados, dict) else None
	if not guardada:
		return DESCONOCIDO
	return CONFIADO if guardada == menu.suma else CAMBIADO


def confiar(config, menu: MenuLocal) -> None:
	"""Recuerda que la persona confía en ESTA versión del menú de la carpeta."""
	confiados = dict(config.obtener(CLAVE_CONFIANZA) or {})
	confiados[clave_carpeta(menu.carpeta)] = menu.suma
	config.establecer(CLAVE_CONFIANZA, confiados)
	log.info("Menú local de confianza: %s (%s)", menu.ruta, menu.suma[:12])


def retirar_confianza(config, carpeta: str) -> bool:
	confiados = dict(config.obtener(CLAVE_CONFIANZA) or {})
	if confiados.pop(clave_carpeta(carpeta), None) is None:
		return False
	config.establecer(CLAVE_CONFIANZA, confiados)
	return True


def entradas_disponibles(config, menu_local: MenuLocal | None, globales: list[EntradaMenu] | None = None) -> list[EntradaMenu]:
	"""Lo que muestra F2: las entradas del menú local (solo si es de confianza) y después las globales.

	Esta es la única puerta por la que el menú local llega a la lista: sin
	confianza para su suma exacta, sus entradas no se devuelven.
	"""
	globales = cargar() if globales is None else globales
	if menu_local is None or menu_local.error or not menu_local.entradas:
		return list(globales)
	if estado_confianza(config.obtener(CLAVE_CONFIANZA) or {}, menu_local) != CONFIADO:
		return list(globales)
	return [*menu_local.entradas, *globales]


def buscar_tecla(entradas: list[EntradaMenu], tecla: str) -> EntradaMenu | None:
	"""Primera entrada con esa tecla rápida (sin distinguir mayúsculas)."""
	tecla = normalizar_tecla(tecla)
	if not tecla:
		return None
	return next((e for e in entradas if e.tecla == tecla), None)


def plantilla(entrada: EntradaMenu) -> str:
	"""Las órdenes de la entrada en una sola línea de ``cmd``, una tras otra (como un .bat).

	Se expanden juntas (``variables.expandir``) para que las referencias
	``%ZC_n%`` no se repitan entre órdenes.
	"""
	return " & ".join(o.strip() for o in entrada.ordenes if o.strip())


def resumen_ordenes(entradas: list[EntradaMenu], sangria: str = "") -> list[str]:
	"""Líneas legibles con cada entrada y sus órdenes (para enseñar el menú local antes de confiar)."""
	lineas: list[str] = []
	for entrada in entradas:
		lineas.append(f"{sangria}{entrada.texto()}")
		if entrada.es_submenu:
			lineas.extend(resumen_ordenes(entrada.submenu, sangria + "    "))
		else:
			lineas.extend(f"{sangria}    {o.strip()}" for o in entrada.ordenes if o.strip())
	return lineas


def recargar() -> None:
	"""Vuelve a leer su archivo tras restaurar una copia (2.0, 14.4): se lee en cada uso, así que solo avisa."""
	from app.services import recarga

	recarga.avisar(__name__)
