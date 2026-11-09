# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Línea de órdenes: cambios de carpeta internos y ejecución de órdenes con salida capturada.

- ``cd ruta``, ``cd ..``, ``cd \\``, ``chdir`` y ``X:`` cambian la carpeta del
  panel sin lanzar un proceso (como en Norton).
- El resto se ejecuta con ``cmd.exe /d /s /c "orden"`` en la carpeta del
  panel (``cwd=``, nunca ``os.chdir``, que bloquearía la carpeta), sin ventana,
  leyendo la salida estándar y la de error línea a línea.
- La salida se decodifica con la página de códigos OEM de la consola (los
  programas de consola escriben así; si no, las eñes salen mal), salvo que la
  orden empiece por ``chcp 65001``.

2.0 (10.8; PE es el dueño posterior de este archivo): ``zc <orden>`` lo separa
``analizar_zc`` (N2); los alias los expande ``app.services.alias`` y el
autocompletar (Ctrl+Espacio) usa ``candidatos``, ``completar`` y ``poner_opcion``.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NEW_PROCESS_GROUP = 0x00000200

_UNIDAD = re.compile(r"^\s*([A-Za-z]):\s*$")
_CD = re.compile(r"^\s*(?:cd|chdir)(?:\s+/d)?(?:\s+(.*?))?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class CambioCarpeta:
	"""La orden era un cambio de carpeta: ``destino`` es la ruta escrita (relativa o absoluta)."""

	destino: str


@dataclass(frozen=True)
class OrdenZc:
	"""2.0 (10.8): ``zc <nombre> [resto]``: una orden del catálogo, ``macro <nombre>``, ``ayuda`` o una interna.

	Quien la atiende (la ventana) decide qué es ``nombre`` con el catálogo vivo; aquí
	solo se separa, sin lanzar ningún proceso.
	"""

	nombre: str
	argumentos: tuple[str, ...]
	resto: str


def analizar_zc(orden: str) -> OrdenZc | None:
	"""``zc ir_a_carpeta D:/x`` → ``OrdenZc("ir_a_carpeta", ("D:/x",), "D:/x")``; ``None`` si no empieza por «zc »."""
	texto = orden.strip()
	if not texto.lower().startswith("zc ") or len(texto) <= 3:
		return None
	cuerpo = texto[3:].strip()
	nombre, _espacio, resto = cuerpo.partition(" ")
	resto = resto.strip()
	try:
		import shlex

		argumentos = tuple(shlex.split(resto, posix=False)) if resto else ()
	except ValueError:
		argumentos = tuple(resto.split())
	return OrdenZc(nombre, tuple(a.strip('"') for a in argumentos), resto.strip('"'))


# ── 2.0 (10.8, bloque PE): autocompletar ────────────────────────────────────


@dataclass(frozen=True)
class Completado:
	"""Resultado de autocompletar: el texto nuevo y las opciones que había para la última palabra."""

	texto: str
	opciones: tuple[str, ...]


def ultima_palabra(texto: str) -> tuple[int, str]:
	"""(posición donde empieza, palabra) de la última palabra; respeta unas comillas abiertas."""
	if texto.count('"') % 2 == 1:
		inicio = texto.rfind('"')
		return inicio, texto[inicio + 1:]
	inicio = len(texto)
	while inicio > 0 and not texto[inicio - 1].isspace():
		inicio -= 1
	return inicio, texto[inicio:].strip('"')


def prefijo_comun(opciones: list[str] | tuple[str, ...]) -> str:
	"""Prefijo común sin distinguir mayúsculas (con las letras de la primera opción)."""
	if not opciones:
		return ""
	primera = opciones[0]
	largo = len(primera)
	for otra in opciones[1:]:
		largo = min(largo, len(otra))
		for i in range(largo):
			if primera[i].casefold() != otra[i].casefold():
				largo = i
				break
	return primera[:largo]


def candidatos_ruta(palabra: str, carpeta: str, limite: int = 500) -> list[str]:
	"""Nombres de la carpeta (o de la de la ruta escrita) que empiezan por lo escrito; las carpetas con «\\»."""
	base, _sep, inicio = palabra.replace("/", "\\").rpartition("\\")
	if _sep:
		directorio = base + "\\" if base.endswith(":") or not base else base
		directorio = directorio if os.path.isabs(directorio) else os.path.join(carpeta, directorio)
		prefijo = base + "\\"
	else:
		directorio, prefijo = carpeta, ""
	resultado: list[str] = []
	try:
		with os.scandir(directorio or ".") as elementos:
			for elemento in elementos:
				if elemento.name.casefold().startswith(inicio.casefold()):
					es_carpeta = elemento.is_dir()
					resultado.append(prefijo + elemento.name + ("\\" if es_carpeta else ""))
					if len(resultado) >= limite:
						break
	except OSError:
		log.debug("No se pudo listar %s para autocompletar", directorio, exc_info=True)
	return sorted(resultado, key=str.casefold)


def candidatos(texto: str, carpeta: str, alias: list[str], ordenes_zc: list[str]) -> list[str]:
	"""Opciones para la última palabra: tras «zc », órdenes; en la primera palabra, alias y rutas; si no, rutas."""
	inicio, palabra = ultima_palabra(texto)
	antes = texto[:inicio].strip().strip('"')
	if antes.lower() == "zc":
		return sorted({o for o in ordenes_zc if o.casefold().startswith(palabra.casefold())}, key=str.casefold)
	opciones: list[str] = []
	if not antes:
		opciones += [a for a in alias if a.casefold().startswith(palabra.casefold())]
	return opciones + candidatos_ruta(palabra, carpeta)


def completar(texto: str, opciones: list[str]) -> Completado:
	"""Completa la última palabra con lo común a todas las opciones (entrecomilla si hay espacios)."""
	if not opciones:
		return Completado(texto, ())
	inicio, palabra = ultima_palabra(texto)
	comun = opciones[0] if len(opciones) == 1 else prefijo_comun(opciones)
	if len(comun) < len(palabra):
		comun = palabra
	abierta = texto.count('"') % 2 == 1
	if abierta:
		nuevo = texto[:inicio] + '"' + comun + ('"' if len(opciones) == 1 and not comun.endswith("\\") else "")
	elif " " in comun:
		nuevo = texto[:inicio] + '"' + comun + ('"' if len(opciones) == 1 and not comun.endswith("\\") else "")
	else:
		nuevo = texto[:inicio] + comun
	if len(opciones) == 1 and not comun.endswith("\\") and not nuevo.endswith(" "):
		nuevo += " "
	return Completado(nuevo, tuple(opciones))


def poner_opcion(texto: str, opcion: str) -> str:
	"""Sustituye la última palabra por la opción elegida en la lista (segunda pulsación)."""
	inicio, _palabra = ultima_palabra(texto)
	if " " in opcion or texto.count('"') % 2 == 1:
		return texto[:inicio] + '"' + opcion + ('"' if not opcion.endswith("\\") else "")
	return texto[:inicio] + opcion + ("" if opcion.endswith("\\") else " ")


def analizar(orden: str) -> CambioCarpeta | None:
	"""Devuelve ``CambioCarpeta`` si la orden es ``cd`` o una unidad sola; si no, ``None``."""
	unidad = _UNIDAD.match(orden)
	if unidad:
		return CambioCarpeta(unidad.group(1).upper() + ":")
	cd = _CD.match(orden)
	if cd:
		destino = (cd.group(1) or "").strip().strip('"')
		return CambioCarpeta(destino)
	return None


def pagina_oem() -> str:
	"""Códec de la página OEM de la consola (``cp850`` en España)."""
	try:
		return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
	except (AttributeError, OSError):
		return "cp850"


class Proceso:
	"""Orden en marcha con su salida. Los avisos llegan en un hilo: la interfaz los pasa con ``CallAfter``.

	:param al_linea: ``al_linea(texto, es_error)`` por cada línea de salida.
	:param al_terminar: ``al_terminar(codigo)``; ``None`` si se detuvo.
	"""

	def __init__(
		self,
		orden: str,
		carpeta: str,
		entorno: dict[str, str] | None,
		al_linea: Callable[[str, bool], None],
		al_terminar: Callable[[int | None], None],
	) -> None:
		self.orden = orden
		self.carpeta = carpeta
		codificacion = "utf-8" if orden.lower().lstrip().startswith("chcp 65001") else pagina_oem()
		variables = dict(os.environ)
		variables.update(entorno or {})
		self._al_linea = al_linea
		self._al_terminar = al_terminar
		self._detenido = False
		from app.services.variables import linea_cmd

		self.proceso = subprocess.Popen(  # noqa: S602 - la orden la escribe la persona usuaria
			linea_cmd(orden),
			cwd=carpeta or None,
			env=variables,
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
		)
		self._hilos = [
			threading.Thread(target=self._leer, args=(self.proceso.stdout, False, codificacion), name="salida-orden", daemon=True),
			threading.Thread(target=self._leer, args=(self.proceso.stderr, True, codificacion), name="errores-orden", daemon=True),
		]
		for hilo in self._hilos:
			hilo.start()
		threading.Thread(target=self._esperar, name="espera-orden", daemon=True).start()

	def _leer(self, flujo, es_error: bool, codificacion: str) -> None:
		try:
			for linea in iter(flujo.readline, b""):
				self._al_linea(linea.decode(codificacion, errors="replace").rstrip("\r\n"), es_error)
		except (OSError, ValueError):
			log.debug("Se cerró la salida de la orden", exc_info=True)

	def _esperar(self) -> None:
		codigo = self.proceso.wait()
		for hilo in self._hilos:
			hilo.join(timeout=2)
		self._al_terminar(None if self._detenido else codigo)

	def en_marcha(self) -> bool:
		return self.proceso.poll() is None

	def detener(self) -> None:
		"""Termina el proceso y todos sus hijos (``taskkill /T``).

		Lo piden Escape en el panel (orden «cancelar», cuando el panel no tiene
		lectura, cálculo ni filtro rápido que quitar), Escape en la línea de
		órdenes vacía (orden «linea_vaciar») y el cierre de la ventana. Bloquea
		hasta que ``taskkill`` responde: la ventana lo llama desde un hilo de
		trabajo (``VentanaPrincipal.detener_orden``). ``al_terminar`` llega con
		``None`` y la ventana anuncia «Orden detenida».
		"""
		if not self.en_marcha():
			return
		self._detenido = True
		try:
			subprocess.run(
				["taskkill", "/F", "/T", "/PID", str(self.proceso.pid)],
				capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=10, check=False,
			)
		except (OSError, subprocess.TimeoutExpired):
			log.warning("No se pudo detener la orden %s", self.orden, exc_info=True)


def en_consola(orden: str, carpeta: str, entorno: dict[str, str] | None = None, programa: str = "cmd") -> None:
	"""Ejecuta en una consola nueva que queda abierta (programas interactivos)."""
	variables = dict(os.environ)
	variables.update(entorno or {})
	if programa == "powershell":
		linea = ["powershell.exe", "-NoExit", "-Command", orden]
		subprocess.Popen(linea, cwd=carpeta or None, env=variables, creationflags=CREATE_NEW_CONSOLE)  # noqa: S603
		return
	subprocess.Popen(  # noqa: S602 - orden de la persona usuaria
		f'cmd.exe /d /v:off /s /k "{orden}"', cwd=carpeta or None, env=variables, creationflags=CREATE_NEW_CONSOLE,
	)


def abrir_consola(carpeta: str, programa: str = "cmd") -> None:
	"""F11: consola vacía en la carpeta (cmd, powershell o terminal)."""
	if programa == "terminal":
		try:
			subprocess.Popen(["wt.exe", "-d", carpeta])  # noqa: S603, S607
			return
		except OSError:
			log.info("Windows Terminal no está instalado; se abre cmd.")
	if programa == "powershell":
		subprocess.Popen(["powershell.exe", "-NoExit"], cwd=carpeta, creationflags=CREATE_NEW_CONSOLE)  # noqa: S603, S607
		return
	subprocess.Popen(["cmd.exe"], cwd=carpeta, creationflags=CREATE_NEW_CONSOLE)  # noqa: S603, S607
