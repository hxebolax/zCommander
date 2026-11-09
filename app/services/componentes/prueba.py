# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Prueba de un componente (``--probar-componente``, diseño 2.0, 6.2, 6.6 y 14.8). Sin wx.

Dos formas de prueba en la ficha:

- La de un programa: ``{"ejecutable", "argumentos", "salida_contiene", "tiempo_s"}``
  (y, si hace falta, ``"adicionales"`` con más programas que probar, como
  ``ffprobe -version`` junto a ``ffmpeg -version``). Funciona si el programa
  termina con código 0 y su salida contiene el texto (con ``{version}``
  sustituido por la versión que se espera).
- La de una biblioteca que se carga en el proceso (libarchive):
  ``{"tipo": "zcommander", "argumentos": ["--probar-componente", "libarchive"]}``.
  zCommander se lanza a sí mismo sin interfaz (el argumento se atiende al
  principio de ``main``, antes de la instancia única: así funciona aunque haya
  otra instancia abierta) y, para probar una versión aún sin instalar, se le
  añade ``--carpeta <carpeta nueva>``.

Todo proceso va por ``app.core.procesos.lanzar``: sin consola, sin shell, con
ruta absoluta y dentro del Job Object.
"""

from __future__ import annotations

import builtins
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import paths, procesos
from app.services.componentes import fichas

log = logging.getLogger(__name__)

Lanzador = Callable[..., procesos.ResultadoPrograma]


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class ResultadoPrueba:
	"""``version``: la que dice el programa en su salida (la usa ``version_desde: programa``)."""

	correcta: bool
	detalle: str
	version: str = ""


def orden_zcommander() -> list[str]:
	"""Cómo lanzar este mismo zCommander: el ejecutable compilado o ``python main.py``."""
	if paths.CONGELADA:
		return [sys.executable]
	return [sys.executable, str(paths.ruta_base() / "main.py")]


def version_en_salida(texto: str) -> str:
	"""«ffmpeg version n9.0.2-48-g...» → «9.0.2»; «rclone v1.76.0» → «1.76.0»; «7-Zip (a) 26.06» → «26.06»."""
	encontrado = re.search(r"(?:version|v)\s*n?(\d+(?:\.\d+)+)", texto, re.IGNORECASE) or re.search(r"\b(\d+\.\d+(?:\.\d+)*)\b", texto)
	return encontrado.group(1) if encontrado else ""


def _probar_programa(prueba: dict, carpeta: Path, version: str, lanzar: Lanzador, cancelacion: Any) -> ResultadoPrueba:
	ejecutable = carpeta / str(prueba["ejecutable"])
	if not ejecutable.is_file():
		return ResultadoPrueba(False, _("Falta {e}").format(e=prueba["ejecutable"]))
	argumentos = [fichas.sustituir(str(a), version=version) for a in prueba.get("argumentos", [])]
	try:
		resultado = lanzar([str(ejecutable), *argumentos], carpeta=str(carpeta), tiempo_s=float(prueba.get("tiempo_s", 20)),
			cancelacion=cancelacion)
	except procesos.ErrorProceso as error:
		return ResultadoPrueba(False, error.mensaje)
	except OSError as error:
		log.warning("No se pudo lanzar %s", ejecutable, exc_info=True)
		return ResultadoPrueba(False, _("No se pudo ejecutar {e}: {m}").format(e=prueba["ejecutable"], m=error))
	salida = (resultado.salida + b"\n" + resultado.errores).decode("utf-8", errors="replace")
	if resultado.cancelado:
		return ResultadoPrueba(False, _("{e} no terminó a tiempo").format(e=prueba["ejecutable"]))
	if resultado.codigo != 0:
		return ResultadoPrueba(False, _("{e} terminó con el código {c}").format(e=prueba["ejecutable"], c=resultado.codigo))
	esperado = fichas.sustituir(str(prueba.get("salida_contiene") or ""), version=version)
	if esperado and esperado not in salida:
		return ResultadoPrueba(False, _("La salida de {e} no dice «{t}»").format(e=prueba["ejecutable"], t=esperado))
	return ResultadoPrueba(True, _("{e} funciona").format(e=prueba["ejecutable"]), version_en_salida(salida))


def probar_ficha(ficha: dict, carpeta: Path, *, version: str = "", definitiva: bool, lanzar: Lanzador | None = None,
		cancelacion: Any = None) -> ResultadoPrueba:
	"""Prueba el componente de ``ficha`` con los archivos de ``carpeta``.

	:param version: la versión que se espera (para ``{version}`` de ``salida_contiene``).
	:param definitiva: ``carpeta`` es ``data/bin/<carpeta>``; si no, a la prueba de
		tipo ``zcommander`` se le añade ``--carpeta`` (6.2).
	"""
	lanzar = lanzar or procesos.lanzar
	prueba = ficha.get("prueba")
	if not prueba:
		return ResultadoPrueba(True, _("Sin prueba"))
	version = version or str(ficha.get("version", ""))
	if prueba.get("tipo") == "zcommander":
		argumentos = [*orden_zcommander(), *[str(a) for a in prueba.get("argumentos", [])]]
		if not definitiva:
			argumentos += ["--carpeta", str(carpeta)]
		try:
			resultado = lanzar(argumentos, carpeta=str(paths.ruta_base()), tiempo_s=float(prueba.get("tiempo_s", 20)),
				cancelacion=cancelacion)
		except (procesos.ErrorProceso, OSError) as error:
			log.warning("No se pudo lanzar la prueba de %s", ficha.get("id"), exc_info=True)
			return ResultadoPrueba(False, getattr(error, "mensaje", str(error)))
		if resultado.codigo != 0 or resultado.cancelado:
			return ResultadoPrueba(False, _("La prueba de {c} falló (código {n})").format(c=ficha.get("nombre"), n=resultado.codigo))
		return ResultadoPrueba(True, _("{c} funciona").format(c=ficha.get("nombre")), version)
	primero = _probar_programa(prueba, carpeta, version, lanzar, cancelacion)
	if not primero.correcta:
		return primero
	for adicional in prueba.get("adicionales", []):
		otro = _probar_programa({"tiempo_s": prueba.get("tiempo_s", 20), **adicional}, carpeta, version, lanzar, cancelacion)
		if not otro.correcta:
			return otro
	return primero


def probar_componente(id: str, carpeta: Path | None) -> int:
	"""``--probar-componente <id> [--carpeta <ruta>]``: 0 si el componente funciona.

	libarchive se prueba cargando la DLL en este proceso (``app.services.libarchive.prueba``,
	de CM); los demás, ejecutando la prueba de su ficha desde ``carpeta`` o desde su sitio.
	"""
	if id == "libarchive":
		from app.services.libarchive import prueba

		return prueba.probar(carpeta)
	from app.services.componentes import estado

	ficha = estado.ficha_instalada(id)
	if ficha is None:
		log.warning("No hay ningún componente %s", id)
		return 1
	if (ficha.get("prueba") or {}).get("tipo") == "zcommander":
		log.warning("La prueba de %s no se puede lanzar desde sí misma", id)
		return 1
	destino = Path(carpeta) if carpeta is not None else estado.carpeta_de(id)
	resultado = probar_ficha(ficha, destino, definitiva=carpeta is None)
	log.info("Prueba de %s: %s", id, resultado.detalle)
	return 0 if resultado.correcta else 1
