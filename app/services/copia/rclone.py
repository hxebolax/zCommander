# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""El ``rclone.conf`` de una copia: qué remotos ejecutan programas y cómo quitarlos (diseño 2.0, 7.2). Sin wx.

rclone ejecuta opciones como ``bearer_token_command`` (WebDAV), ``ssh`` (SFTP)
o cualquier ``*_command`` al usar la cuenta, con su entorno (también
``RCLONE_CONFIG_PASS``). Por eso un remoto así de una copia no se restaura sin
que la persona lo marque.

El archivo de la copia está cifrado por rclone; se lee y se edita con el propio
``rclone config dump`` y ``rclone config delete`` (``procesos.lanzar``, ruta
absoluta, la contraseña en ``RCLONE_CONFIG_PASS`` del entorno y nunca en los
argumentos). Un archivo sin cifrar se lee con ``configparser``.
"""

from __future__ import annotations

import builtins
import configparser
import json
import logging
import os
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.services.copia.formato import ErrorCopia, opcion_rclone_ejecuta

log = logging.getLogger(__name__)

MARCA_CIFRADO = b"# Encrypted rclone configuration File"
TIEMPO_S = 60


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class RemotoEjecutable:
	nombre: str
	tipo: str
	opcion: str
	valor: str


def cifrado(contenido: bytes) -> bool:
	return contenido.lstrip().startswith(MARCA_CIFRADO)


def ejecutable_rclone() -> Path:
	"""``rclone.exe`` del componente (CO); ``ErrorCopia`` si falta."""
	from app.services.componentes import estado
	from app.services.vfs.base import ErrorArchivos

	try:
		return estado.ejecutable("rclone", "rclone.exe")
	except ErrorArchivos as error:
		raise ErrorCopia(_("Falta rclone: no se pueden revisar las cuentas de nube de la copia.")) from error


@contextmanager
def _temporal(contenido: bytes, carpeta: Path):
	"""El ``rclone.conf`` de la copia en un archivo temporal de ``data/temp`` que se borra siempre."""
	carpeta = Path(carpeta) / f"copia-rclone-{os.getpid()}-{uuid.uuid4().hex[:8]}"
	carpeta.mkdir(parents=True, exist_ok=True)
	ruta = carpeta / "rclone.conf"
	try:
		ruta.write_bytes(contenido)
		yield ruta
	finally:
		shutil.rmtree(carpeta, ignore_errors=True)


def _lanzar(ejecutable: Path, argumentos: list[str], contrasena: str) -> bytes:
	from app.core import procesos

	entorno = dict(os.environ)
	entorno.pop("RCLONE_CONFIG", None)
	entorno["RCLONE_CONFIG_PASS"] = contrasena
	try:
		resultado = procesos.lanzar([str(ejecutable), *argumentos, "--ask-password=false"], tiempo_s=TIEMPO_S,
			entorno=entorno)
	except procesos.ErrorProceso as error:
		raise ErrorCopia(error.mensaje) from error
	if resultado.codigo != 0:
		log.warning("rclone %s terminó con el código %s", argumentos[:2], resultado.codigo)
		raise ErrorCopia(_("rclone no pudo leer las cuentas de nube de la copia (¿contraseña de la copia correcta?)."))
	return resultado.salida


def remotos(contenido: bytes, contrasena: str, carpeta_temporal: Path, ejecutable: Path | None = None) -> dict[str, dict]:
	"""Remotos del archivo: nombre → opciones (con ``type``)."""
	if not cifrado(contenido):
		lector = configparser.RawConfigParser(strict=False, interpolation=None)
		try:
			lector.read_string(contenido.decode("utf-8-sig"))
		except (configparser.Error, UnicodeDecodeError) as error:
			raise ErrorCopia(_("El archivo de cuentas de nube de la copia está dañado.")) from error
		return {s: dict(lector.items(s)) for s in lector.sections()}
	ejecutable = ejecutable or ejecutable_rclone()
	with _temporal(contenido, carpeta_temporal) as ruta:
		salida = _lanzar(ejecutable, ["config", "dump", "--config", str(ruta)], contrasena)
	try:
		datos = json.loads(salida.decode("utf-8"))
	except (ValueError, UnicodeDecodeError) as error:
		raise ErrorCopia(_("rclone devolvió algo inesperado al leer las cuentas de la copia.")) from error
	return {str(k): {str(o): str(v) for o, v in (opciones or {}).items()} for k, opciones in datos.items()
		if isinstance(opciones, dict)} if isinstance(datos, dict) else {}


def ejecutables(datos_remotos: dict[str, dict]) -> list[RemotoEjecutable]:
	"""Los remotos con alguna opción que ejecuta un programa (una entrada por remoto, la primera opción)."""
	resultado = []
	for nombre, opciones in sorted(datos_remotos.items()):
		for opcion, valor in sorted(opciones.items()):
			if opcion_rclone_ejecuta(opcion) and str(valor).strip():
				resultado.append(RemotoEjecutable(nombre, str(opciones.get("type", "")), opcion, str(valor)))
				break
	return resultado


def quitar_remotos(contenido: bytes, nombres: list[str], contrasena: str, carpeta_temporal: Path,
		ejecutable: Path | None = None) -> bytes:
	"""El archivo sin los remotos ``nombres`` (sigue cifrado si lo estaba)."""
	if not nombres:
		return contenido
	if not cifrado(contenido):
		lector = configparser.RawConfigParser(strict=False, interpolation=None)
		lector.read_string(contenido.decode("utf-8-sig"))
		for nombre in nombres:
			lector.remove_section(nombre)
		with _temporal(b"", carpeta_temporal) as ruta:
			with open(ruta, "w", encoding="utf-8") as salida:
				lector.write(salida)
			return ruta.read_bytes()
	ejecutable = ejecutable or ejecutable_rclone()
	with _temporal(contenido, carpeta_temporal) as ruta:
		for nombre in nombres:
			_lanzar(ejecutable, ["config", "delete", nombre, "--config", str(ruta)], contrasena)
		resultado = ruta.read_bytes()
	if cifrado(contenido) and not cifrado(resultado):
		# rclone nunca descifra al borrar; si pasara, no se deja un archivo de tokens en claro.
		raise ErrorCopia(_("No se pudo quitar una cuenta de nube sin descifrar el archivo; no se restauran."))
	return resultado
