# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Dividir un archivo en partes y unirlas (sección 8.19).

Formato compatible con Total Commander: ``nombre.001``, ``nombre.002``... y
``nombre.crc`` con tres líneas::

	filename=nombre.ext
	size=2621440
	crc32=1A2B3C4D

Unir parte de ``.001``, busca las siguientes en orden y, si hay ``.crc``,
comprueba tamaño y CRC32 del resultado.

Las funciones trabajan en el disco local (las partes y el resultado son
archivos locales); el origen de dividir se lee con un flujo, así que puede
venir de cualquier proveedor. Escriben en temporales ``~zc*.tmp`` y solo los
renombran al terminar: una cancelación no deja partes a medias.
"""

from __future__ import annotations

import builtins
import logging
import os
import re
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO

from app.services import errores
from app.services.operaciones import nombres
from app.services.vfs import base, rutas

log = logging.getLogger(__name__)

BLOQUE = 1024 * 1024
KB, MB, GB = 1024, 1024 * 1024, 1024 * 1024 * 1024

#: Tamaños de parte del diálogo: (etiqueta, bytes). 1,44 MB es el del disquete (1 457 664 bytes).
TAMANOS_PREDEFINIDOS: tuple[tuple[str, int], ...] = (
	("1,44 MB", 1457664),
	("100 MB", 100 * MB),
	("650 MB", 650 * MB),
	("700 MB", 700 * MB),
	("4095 MB", 4095 * MB),
	("4,7 GB", 4700000000),
)
UNIDADES: tuple[tuple[str, int], ...] = (("KB", KB), ("MB", MB), ("GB", GB))


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def leer_tamano(texto: str, unidad: int) -> int | None:
	"""«2,5» (o «2.5») con MB → 2 621 440. ``None`` si no es un número positivo."""
	limpio = texto.strip().replace(" ", "").replace(",", ".")
	try:
		valor = float(limpio)
	except ValueError:
		return None
	bytes_ = int(valor * unidad)
	return bytes_ if bytes_ > 0 else None


def nombre_parte(nombre: str, numero: int) -> str:
	"""«video.mp4.001». Con más de 999 partes la numeración crece («.1000»)."""
	return f"{nombre}.{numero:03d}"


def numero_partes(tamano: int, tamano_parte: int) -> int:
	return max(1, -(-tamano // tamano_parte))


@dataclass
class InfoCrc:
	"""Contenido de un archivo ``.crc``."""

	nombre: str = ""
	tamano: int = -1
	crc32: str = ""


def componer_crc(info: InfoCrc) -> str:
	return f"filename={info.nombre}\r\nsize={info.tamano}\r\ncrc32={info.crc32.upper()}\r\n"


def leer_crc(texto: str) -> InfoCrc:
	info = InfoCrc()
	for linea in texto.splitlines():
		clave, _sep, valor = linea.partition("=")
		clave = clave.strip().lower()
		valor = valor.strip()
		if clave == "filename":
			info.nombre = valor
		elif clave == "size":
			try:
				info.tamano = int(valor)
			except ValueError:
				log.info("Tamaño no válido en el archivo .crc: %r", valor)
		elif clave == "crc32":
			info.crc32 = valor.upper()
	return info


def _escribir_final(temporal: str, destino: str) -> None:
	from app.services.windows import copia_nativa

	copia_nativa.mover(temporal, destino, reemplazar=True)


def _borrar(ruta: str) -> None:
	try:
		if os.path.exists(rutas.con_prefijo_largo(ruta)):
			os.remove(rutas.con_prefijo_largo(ruta))
	except OSError:
		log.warning("No se pudo borrar %s", ruta, exc_info=True)


def dividir(flujo: BinaryIO, nombre: str, tamano: int, carpeta: str, tamano_parte: int, cancelacion=None,
		al_avanzar: Callable[[int], None] | None = None) -> list[str]:
	"""Escribe las partes de ``flujo`` en ``carpeta`` y el ``.crc``; devuelve las rutas creadas.

	:param nombre: nombre del archivo original («video.mp4»).
	:param tamano: su tamaño (para el ``.crc``; si no cuadra con lo leído, manda lo leído).
	:raises Cancelado: si se cancela (se borra lo escrito).
	"""
	if tamano_parte <= 0:
		raise ValueError("El tamaño de parte debe ser positivo")
	temporales: list[tuple[str, str]] = []
	crc = 0
	leidos = 0
	numero = 0
	try:
		while True:
			datos = flujo.read(min(BLOQUE, tamano_parte))
			if not datos and numero > 0:
				break
			numero += 1
			temporal = rutas.unir(carpeta, nombres.temporal())
			temporales.append((temporal, rutas.unir(carpeta, nombre_parte(nombre, numero))))
			escritos = 0
			with open(rutas.con_prefijo_largo(temporal), "wb") as salida:
				while datos:
					base.comprobar(cancelacion)
					salida.write(datos)
					crc = zlib.crc32(datos, crc)
					escritos += len(datos)
					leidos += len(datos)
					if al_avanzar is not None:
						al_avanzar(len(datos))
					if escritos >= tamano_parte:
						break
					datos = flujo.read(min(BLOQUE, tamano_parte - escritos))
			if escritos < tamano_parte:
				break
		if tamano >= 0 and tamano != leidos:
			log.info("%s: se esperaban %d bytes y se leyeron %d", nombre, tamano, leidos)
		info = InfoCrc(nombre, leidos, f"{crc & 0xFFFFFFFF:08X}")
		temporal_crc = rutas.unir(carpeta, nombres.temporal())
		temporales.append((temporal_crc, rutas.unir(carpeta, base_crc(nombre))))
		with open(rutas.con_prefijo_largo(temporal_crc), "w", encoding="utf-8", newline="") as salida:
			salida.write(componer_crc(info))
		creados = []
		for temporal, destino in temporales:
			_escribir_final(temporal, destino)
			creados.append(destino)
		return creados
	except BaseException as error:
		for temporal, _destino in temporales:
			_borrar(temporal)
		if isinstance(error, OSError):
			raise errores.convertir(error, carpeta) from error
		raise


def base_crc(nombre: str) -> str:
	"""Nombre del archivo ``.crc``: el del original sin su extensión («video.mp4» → «video.crc»), como Total Commander."""
	return nombres.partir(nombre)[0] + ".crc"


_PARTE = re.compile(r"^(?P<base>.+)\.(?P<numero>\d{3,})$")


def es_primera_parte(nombre: str) -> bool:
	coincide = _PARTE.match(nombre)
	return bool(coincide) and int(coincide["numero"]) == 1


def buscar_partes(primera: str) -> list[str]:
	"""Rutas de las partes consecutivas desde ``primera`` (``nombre.001``) que existen."""
	coincide = _PARTE.match(os.path.basename(primera))
	if not coincide:
		raise base.ErrorArchivos(_("«{n}» no es la primera parte (.001) de un archivo dividido.").format(
			n=os.path.basename(primera)), primera)
	carpeta = os.path.dirname(primera)
	nombre = coincide["base"]
	partes = []
	numero = int(coincide["numero"])
	while True:
		ruta = os.path.join(carpeta, nombre_parte(nombre, numero))
		if not os.path.isfile(rutas.con_prefijo_largo(ruta)):
			break
		partes.append(ruta)
		numero += 1
	return partes


def nombre_original(primera: str) -> str:
	"""Nombre que tendrá el archivo unido: el del ``.crc`` si existe; si no, el de la parte sin «.001»."""
	info = leer_info_crc(primera)
	if info is not None and info.nombre and rutas.nombre_valido(info.nombre):
		return info.nombre
	coincide = _PARTE.match(os.path.basename(primera))
	return coincide["base"] if coincide else os.path.basename(primera)


def leer_info_crc(primera: str) -> InfoCrc | None:
	"""Lee el ``.crc`` junto a las partes («video.crc» o «video.mp4.crc»), si existe."""
	coincide = _PARTE.match(os.path.basename(primera))
	if not coincide:
		return None
	carpeta = os.path.dirname(primera)
	for candidato in (base_crc(coincide["base"]), coincide["base"] + ".crc"):
		ruta = os.path.join(carpeta, candidato)
		try:
			with open(rutas.con_prefijo_largo(ruta), encoding="utf-8", errors="replace") as archivo:
				return leer_crc(archivo.read())
		except FileNotFoundError:
			continue
		except OSError:
			log.info("No se pudo leer %s", ruta, exc_info=True)
	return None


@dataclass
class ResultadoUnion:
	destino: str
	partes: int
	tamano: int
	crc32: str
	#: True si se comprobó con un .crc y coincide; False si no coincide; None si no había .crc.
	comprobado: bool | None


def unir(primera: str, destino: str, cancelacion=None, al_avanzar: Callable[[int], None] | None = None,
		partes: list[str] | None = None) -> ResultadoUnion:
	"""Junta las partes en ``destino`` y comprueba con el ``.crc`` si lo hay.

	Si la comprobación falla, el archivo unido se conserva (puede valer en
	parte) y ``comprobado`` es ``False``: quien llama lo anuncia como error.
	"""
	partes = partes if partes is not None else buscar_partes(primera)
	if not partes:
		raise base.NoEncontrado(_("No se encuentra {n}.").format(n=os.path.basename(primera)), primera)
	carpeta = os.path.dirname(destino)
	temporal = os.path.join(carpeta, nombres.temporal())
	crc = 0
	total = 0
	try:
		with open(rutas.con_prefijo_largo(temporal), "wb") as salida:
			for parte in partes:
				with open(rutas.con_prefijo_largo(parte), "rb") as entrada:
					while datos := entrada.read(BLOQUE):
						base.comprobar(cancelacion)
						salida.write(datos)
						crc = zlib.crc32(datos, crc)
						total += len(datos)
						if al_avanzar is not None:
							al_avanzar(len(datos))
		_escribir_final(temporal, destino)
	except BaseException as error:
		_borrar(temporal)
		if isinstance(error, OSError):
			raise errores.convertir(error, destino) from error
		raise
	texto_crc = f"{crc & 0xFFFFFFFF:08X}"
	info = leer_info_crc(primera)
	comprobado = None
	if info is not None and info.crc32:
		comprobado = info.crc32 == texto_crc and (info.tamano < 0 or info.tamano == total)
	return ResultadoUnion(destino, len(partes), total, texto_crc, comprobado)
