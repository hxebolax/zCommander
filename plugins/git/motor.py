# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Git con ``git.exe`` (si está instalado) o con el lector en Python puro (diseño 2.0, 11.21). Sin wx.

``git.exe`` se busca en este orden: la clave ``ruta_git`` (si la persona eligió
uno), el ``PATH`` y las carpetas de instalación habituales de Git for Windows.
Nunca se instala ni se descarga nada. Se ejecuta siempre con
``zc.ejecutar_programa`` (sin consola, en el Job Object de zCommander) y con
``GIT_TERMINAL_PROMPT=0``: sin consola, una petición de usuario en el terminal
se quedaría esperando para siempre; las credenciales las pide el administrador
de credenciales de Git, en su propia ventana.

Sin ``git.exe`` funcionan estado, historial y diferencias (solo lectura, con
``lector.py``); el resto dice «Hace falta Git instalado».
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.plugins import api

from . import lector

_, _n = api.traduccion("zc_git")

HACE_FALTA_GIT = "Hace falta Git instalado"
CARPETAS_GIT = (r"%ProgramFiles%\Git\cmd\git.exe", r"%ProgramFiles(x86)%\Git\cmd\git.exe", r"%LocalAppData%\Programs\Git\cmd\git.exe")
ENTORNO = {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"}


class SinGit(api.NoAdmitido):
	def __init__(self) -> None:
		super().__init__(_(HACE_FALTA_GIT))


def buscar_git(configurado: str = "") -> str:
	"""Ruta absoluta de ``git.exe`` o ``""``."""
	if configurado:
		return configurado if os.path.isfile(configurado) else ""
	encontrado = shutil.which("git.exe") or shutil.which("git")
	if encontrado and os.path.isfile(encontrado):
		return os.path.abspath(encontrado)
	for candidato in CARPETAS_GIT:
		ruta = os.path.expandvars(candidato)
		if os.path.isfile(ruta):
			return ruta
	return ""


def codigo_de(xy: str) -> str:
	"""Estado de una línea de ``git status --porcelain`` (los dos caracteres XY)."""
	if xy == "??":
		return lector.SIN_SEGUIMIENTO
	if xy == "!!":
		return lector.IGNORADO
	if "U" in xy or xy in ("AA", "DD"):
		return lector.CONFLICTO
	if "R" in xy or "C" in xy:
		return lector.RENOMBRADO
	if xy[0] == "A":
		return lector.NUEVO
	if "D" in xy:
		return lector.ELIMINADO
	return lector.MODIFICADO


def interpretar_porcelain(salida: bytes) -> dict[str, str]:
	"""``git status --porcelain=v1 -z``: ``{ruta: estado}`` (las carpetas ignoradas acaban en «/»)."""
	resultado: dict[str, str] = {}
	partes = salida.decode("utf-8", errors="surrogateescape").split("\0")
	i = 0
	while i < len(partes):
		linea = partes[i]
		i += 1
		if len(linea) < 4:
			continue
		xy, ruta = linea[:2], linea[3:]
		resultado[ruta] = codigo_de(xy)
		if xy[0] in "RC":
			i += 1  # la ruta de origen del renombrado
	return resultado


@dataclass
class Estado:
	raiz: str
	rama: str
	cambios: dict[str, str] = field(default_factory=dict)
	momento: float = field(default_factory=time.monotonic)

	@property
	def pendientes(self) -> dict[str, str]:
		"""Los cambios sin los ignorados."""
		return {r: c for r, c in self.cambios.items() if c != lector.IGNORADO}

	def resumen(self) -> str:
		"""«Rama main, 3 cambios: 2 modificados, 1 sin seguimiento»."""
		rama = _("Rama {r}").format(r=self.rama) if self.rama else _("Sin rama (HEAD separado)")
		pendientes = self.pendientes
		if not pendientes:
			return _("{r}, sin cambios").format(r=rama)
		cuenta: dict[str, int] = {}
		for codigo in pendientes.values():
			cuenta[codigo] = cuenta.get(codigo, 0) + 1
		detalle = ", ".join(f"{n} {_plural(codigo, n)}" for codigo, n in sorted(cuenta.items(), key=lambda p: -p[1]))
		return _n("{r}, {n} cambio: {d}", "{r}, {n} cambios: {d}", len(pendientes)).format(r=rama, n=len(pendientes), d=detalle)

	def de(self, relativa: str, es_carpeta: bool = False) -> str:
		"""Texto de la columna Git para una ruta relativa a la raíz (con «/»)."""
		if relativa in self.cambios:
			return _(self.cambios[relativa])
		for ruta, codigo in self.cambios.items():
			if codigo == lector.IGNORADO and ruta.endswith("/") and (relativa + "/").startswith(ruta):
				return _(lector.IGNORADO)
			if codigo == lector.SIN_SEGUIMIENTO and ruta.endswith("/") and relativa.startswith(ruta):
				return _(lector.SIN_SEGUIMIENTO)
		if es_carpeta:
			prefijo = relativa + "/"
			if any(r.startswith(prefijo) and c != lector.IGNORADO for r, c in self.cambios.items()):
				return _("con cambios")
		return ""


_PLURALES = {lector.MODIFICADO: "modificados", lector.NUEVO: "nuevos", lector.ELIMINADO: "eliminados",
	lector.RENOMBRADO: "renombrados", lector.CONFLICTO: "en conflicto", lector.SIN_SEGUIMIENTO: "sin seguimiento"}


def _plural(codigo: str, n: int) -> str:
	return _(codigo) if n == 1 else _(_PLURALES.get(codigo, codigo))


Ejecutor = Callable[..., Any]


class Git:
	"""Operaciones de Git sobre una carpeta, con ``git.exe`` o, en solo lectura, con el lector."""

	def __init__(self, ejecutar: Ejecutor, ruta_git: Callable[[], str]) -> None:
		self._ejecutar = ejecutar
		self._ruta_git = ruta_git
		self._candados: dict[str, threading.Lock] = {}
		self._cache: dict[str, Estado] = {}
		self._candado = threading.Lock()

	@property
	def exe(self) -> str:
		return buscar_git(self._ruta_git())

	def ejecutar(self, carpeta: str, *argumentos: str, tiempo_s: float = 120, cancelacion: Any = None,
			al_leer: Callable[[bytes], None] | None = None, entrada: bytes = b"") -> Any:
		"""``git -C carpeta argumentos`` [trabajo]. :raises SinGit: sin ``git.exe``."""
		exe = self.exe
		if not exe:
			raise SinGit()
		return self._ejecutar([exe, "-c", "color.ui=never", "-c", "core.quotepath=off", "-C", carpeta, *argumentos],
			carpeta=carpeta, tiempo_s=tiempo_s, cancelacion=cancelacion, al_leer=al_leer, entorno=dict(ENTORNO), entrada=entrada)

	def comprobar(self, resultado: Any, que: str) -> str:
		"""Texto de la salida si salió bien; si no, ``ErrorArchivos`` con el mensaje de Git."""
		texto = (resultado.salida + resultado.errores).decode("utf-8", errors="replace").strip()
		if resultado.cancelado:
			raise api.Cancelado()
		if resultado.codigo != 0:
			lineas = [linea.removeprefix("fatal: ").removeprefix("error: ") for linea in texto.splitlines() if linea.strip()]
			raise api.ErrorArchivos(_("Git no pudo {q}: {m}").format(q=que, m=" ".join(lineas[-3:]) or _("código {c}").format(
				c=resultado.codigo)))
		return texto

	@staticmethod
	def raiz(carpeta: str) -> str | None:
		encontrado = lector.buscar_raiz(carpeta)
		return encontrado[0] if encontrado else None

	def estado(self, carpeta: str, maximo_s: float = 0.0) -> Estado | None:
		"""Estado del repositorio que contiene ``carpeta`` (con caché de ``maximo_s`` segundos) [trabajo]."""
		raiz = self.raiz(carpeta)
		if raiz is None:
			return None
		with self._candado:
			candado = self._candados.setdefault(raiz, threading.Lock())
		with candado:
			guardado = self._cache.get(raiz)
			if guardado is not None and maximo_s > 0 and time.monotonic() - guardado.momento < maximo_s:
				return guardado
			nuevo = self._leer_estado(raiz)
			self._cache[raiz] = nuevo
			return nuevo

	def olvidar(self, carpeta: str | None = None) -> None:
		with self._candado:
			if carpeta is None:
				self._cache.clear()
			else:
				raiz = self.raiz(carpeta)
				self._cache.pop(raiz or "", None)

	def _leer_estado(self, raiz: str) -> Estado:
		if self.exe:
			resultado = self.ejecutar(raiz, "status", "--porcelain=v1", "-z", "--ignored=matching", "--untracked-files=normal")
			self.comprobar(resultado, _("leer el estado"))
			rama = self.ejecutar(raiz, "branch", "--show-current")
			return Estado(raiz, rama.salida.decode("utf-8", errors="replace").strip(), interpretar_porcelain(resultado.salida))
		repositorio = lector.Repositorio.de_carpeta(raiz)
		try:
			return Estado(raiz, repositorio.rama(), repositorio.estado())
		finally:
			repositorio.cerrar()

	def historial(self, ruta: str, maximo: int = 500) -> list[lector.Confirmacion]:
		"""Confirmaciones que cambian ``ruta`` (archivo o carpeta), la más reciente primero [trabajo]."""
		raiz = self.raiz(ruta if os.path.isdir(ruta) else os.path.dirname(ruta))
		if raiz is None:
			return []
		relativa = relativa_a(raiz, ruta)
		if self.exe:
			argumentos = ["log", f"-n{maximo}", "--format=%H%x1f%an%x1f%at%x1f%ai%x1f%B%x1e"]
			if relativa:
				argumentos += ["--", relativa]
			resultado = self.ejecutar(raiz, *argumentos)
			if resultado.codigo and b"does not have any commits" in resultado.errores:
				return []
			texto = self.comprobar(resultado, _("leer el historial")) if resultado.codigo else resultado.salida.decode("utf-8", errors="replace")
			confirmaciones = []
			for bloque in texto.split("\x1e"):
				campos = bloque.strip("\n").split("\x1f")
				if len(campos) >= 5:
					confirmaciones.append(lector.Confirmacion(campos[0], campos[1], int(campos[2] or 0), campos[3][-5:], campos[4]))
			return confirmaciones
		repositorio = lector.Repositorio.de_carpeta(raiz)
		try:
			return repositorio.historial(relativa, maximo)
		finally:
			repositorio.cerrar()

	def contenido_confirmado(self, ruta: str) -> bytes | None:
		"""Contenido del archivo en la última confirmación (``HEAD``), o ``None`` si no estaba [trabajo]."""
		raiz = self.raiz(os.path.dirname(ruta))
		if raiz is None:
			return None
		relativa = relativa_a(raiz, ruta)
		if self.exe:
			resultado = self.ejecutar(raiz, "show", f"HEAD:{relativa}")
			return resultado.salida if resultado.codigo == 0 else None
		repositorio = lector.Repositorio.de_carpeta(raiz)
		try:
			return repositorio.contenido_confirmado(relativa)
		finally:
			repositorio.cerrar()

	def ramas(self, carpeta: str) -> list[str]:
		raiz = self.raiz(carpeta)
		if raiz is None:
			return []
		repositorio = lector.Repositorio.de_carpeta(raiz)
		try:
			return repositorio.ramas()
		finally:
			repositorio.cerrar()


def relativa_a(raiz: str, ruta: str) -> str:
	"""Ruta relativa a la raíz del repositorio, con «/» (``""`` para la propia raíz)."""
	relativa = os.path.relpath(os.path.abspath(ruta), os.path.abspath(raiz))
	return "" if relativa == "." else Path(relativa).as_posix()


def diferencias_texto(antes: bytes | None, despues: bytes | None, nombre: str) -> str:
	"""Diferencias unificadas en texto (para cuando no hay ventana de diferencias ni ``git.exe``)."""
	import difflib

	def lineas(datos: bytes | None) -> list[str]:
		return (datos or b"").decode("utf-8", errors="replace").splitlines(keepends=True)

	texto = "".join(difflib.unified_diff(lineas(antes), lineas(despues), f"{nombre} (confirmado)", f"{nombre} (actual)"))
	return texto or _("Sin diferencias")
