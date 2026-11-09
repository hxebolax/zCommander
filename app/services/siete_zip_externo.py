# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""7-Zip de consola: el 7za que trae zCommander y el 7z.exe que tenga instalado la persona (diseño 2.0, 8.4 y 8.5). Sin wx.

Los dos son el mismo programa de consola y se usan igual:

- Siempre con ``app.core.procesos.lanzar``: sin consola ni shell, lista de
  argumentos, rutas tras ``--``, ``-spd`` (sin comodines), dentro del Job
  Object global y con cancelación.
- **Contraseñas por la entrada estándar**, nunca en la línea de órdenes (la
  pueden leer otros procesos) ni en el registro. Reglas comprobadas con 7za
  26.06 (21.3):

  - Crear (``a``) sin contraseña: sin ``-p``. Con contraseña: ``-p`` vacío y la
    contraseña escrita una vez en la entrada estándar.
  - Listar, probar o extraer (``l``, ``t``, ``x``) con una contraseña
    conocida: SIN ``-p`` y la contraseña en la entrada estándar. Sin
    contraseña conocida: ``-p`` vacío y la entrada cerrada, para que falle
    enseguida si hace falta una (en vez de quedarse esperando).

- Progreso con ``-bsp1`` (porcentajes en la salida, separados por retrocesos).
- Códigos de salida de comprimidos-y-red.md A.3 traducidos a mensajes.
"""

from __future__ import annotations

import builtins
import logging
import re
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core import procesos
from app.services.vfs import base, temporales

log = logging.getLogger(__name__)

#: Tiempo máximo de una creación o extracción (la cancelación es lo normal para pararla).
TIEMPO_LARGO = 7 * 24 * 3600
#: Tiempo máximo de un listado o de ``7z i``.
TIEMPO_CORTO = 120

_NIVELES = {"sin": "-mx0", "rapido": "-mx1", "normal": "-mx5", "maximo": "-mx9"}
_PORCENTAJE = re.compile(rb"(\d{1,3})%")
_VERSION = re.compile(r"7-Zip(?: \(a\))?(?: \(r\))? ([0-9][0-9.]*)")

_cache_version: dict[str, str] = {}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ContrasenaIncorrecta(base.ErrorAcceso):
	"""7-Zip dice «Wrong password»: falta la contraseña o no es la correcta."""


# ── Dónde está ───────────────────────────────────────────────────────────────


def _config(clave: str, por_defecto):
	from app.services.vfs import resolver

	config = resolver.servicios().config
	if config is None:
		return por_defecto
	try:
		return config.obtener(clave)
	except Exception:  # noqa: BLE001 - una clave que falta no impide usar 7-Zip: valor de fábrica
		log.debug("Sin la clave %s", clave, exc_info=True)
		return por_defecto


def ruta_7za() -> Path | None:
	"""``data/bin/7za/7za.exe`` (por el servicio de componentes) si existe y ``comprimidos.usar_7za`` está activa."""
	if not _config("comprimidos.usar_7za", True):
		return None
	try:
		from app.services.componentes import estado

		return Path(estado.ejecutable("7za", "7za.exe"))
	except Exception as error:  # noqa: BLE001 - sin 7za se usa la alternativa (py7zr o libarchive)
		log.debug("7za no disponible: %s", getattr(error, "mensaje", error))
		return None


def version(ejecutable: Path | str) -> str:
	"""«26.06» (con ``7z i``), o vacío si no se pudo saber. Se guarda por ruta."""
	clave = str(ejecutable).casefold()
	if clave in _cache_version:
		return _cache_version[clave]
	texto = ""
	try:
		resultado = procesos.lanzar([str(ejecutable), "i"], tiempo_s=20)
		coincidencia = _VERSION.search(resultado.salida.decode("utf-8", "replace"))
		texto = coincidencia.group(1) if coincidencia else ""
	except (procesos.ErrorProceso, OSError):
		log.warning("No se pudo leer la versión de %s", ejecutable, exc_info=True)
	_cache_version[clave] = texto
	return texto


# ── Ejecutar ─────────────────────────────────────────────────────────────────


class _Cancelador:
	"""Adapta la cancelación de zCommander a ``procesos.lanzar`` (que no debe recibir excepciones)."""

	def __init__(self, cancelacion) -> None:
		self._cancelacion = cancelacion

	def __call__(self) -> bool:
		try:
			base.comprobar(self._cancelacion)
		except base.Cancelado:
			return True
		return False


def _mensaje(codigo: int, errores: str) -> str:
	detalle = next((linea.strip() for linea in errores.splitlines() if linea.strip()), "")
	if codigo == 1:
		return _("7-Zip terminó con avisos: {d}").format(d=detalle or _("algún archivo no se pudo leer"))
	if codigo == 7:
		return _("7-Zip no entendió la orden (es un fallo de zCommander): {d}").format(d=detalle)
	if codigo == 8:
		return _("7-Zip se quedó sin memoria.")
	if codigo == 255:
		return _("7-Zip se detuvo.")
	return _("7-Zip no pudo terminar: {d}").format(d=detalle or _("error grave"))


def ejecutar(ejecutable: Path | str, orden: str, interruptores: list[str], archivo: str, miembros: list[str] | None = None, *,
		contrasena: str | None = None, cancelacion=None, al_progreso: Callable[[int], None] | None = None,
		tiempo_s: float = TIEMPO_LARGO, carpeta: str | None = None) -> procesos.ResultadoPrograma:
	"""Ejecuta ``7z <orden> <interruptores> -- archivo [miembros]`` con las reglas de contraseña de 8.4.

	:raises ContrasenaIncorrecta: si 7-Zip dice que falta la contraseña o no es la correcta.
	:raises Cancelado: si se canceló.
	:raises ErrorArchivos: con el mensaje del código de salida.
	"""
	argumentos = [str(ejecutable), orden, *interruptores, "-sccUTF-8", "-spd"]
	entrada = b""
	if orden == "a":
		if contrasena:
			argumentos.append("-p")
			entrada = (contrasena + "\r\n").encode("utf-8")
	elif contrasena is not None:
		entrada = (contrasena + "\r\n").encode("utf-8")
	else:
		argumentos.append("-p")
	if al_progreso is not None:
		argumentos += ["-bsp1", "-bso0"]
	argumentos += ["--", archivo, *(miembros or [])]
	ultimo = [-1]

	def leer(bloque: bytes) -> None:
		if al_progreso is None:
			return
		for coincidencia in _PORCENTAJE.finditer(bloque):
			valor = int(coincidencia.group(1))
			if ultimo[0] < valor <= 100:
				ultimo[0] = valor
				al_progreso(valor)

	log.info("7-Zip %s %s (%s)", orden, archivo, "con contraseña" if contrasena else "sin contraseña")
	try:
		resultado = procesos.lanzar(argumentos, entrada=entrada, tiempo_s=tiempo_s, cancelacion=_Cancelador(cancelacion),
			al_leer=leer, carpeta=carpeta)
	except procesos.ErrorProceso as error:
		raise base.ErrorArchivos(error.mensaje, archivo) from error
	if resultado.cancelado:
		base.comprobar(cancelacion)
		raise base.Cancelado(_("7-Zip tardó demasiado y se detuvo."), archivo)
	errores = resultado.errores.decode("utf-8", "replace")
	if resultado.codigo != 0:
		log.warning("7-Zip %s terminó con el código %d: %s", orden, resultado.codigo, errores.strip()[:500])
		if "wrong password" in errores.lower() or "encrypted" in errores.lower() and "password" in errores.lower():
			raise ContrasenaIncorrecta(_("La contraseña no es correcta o hace falta una."), archivo)
		if not (orden == "t" and resultado.codigo in (1, 2)):
			# Al probar, los avisos y los errores de datos los analiza ``probar``: no paran la prueba.
			raise base.ErrorArchivos(_mensaje(resultado.codigo, errores), archivo)
	return resultado


# ── Listar ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Miembro:
	"""Una línea del listado técnico de 7-Zip (``l -slt``)."""

	ruta: str
	es_carpeta: bool
	tamano: int
	modificado: float
	cifrado: bool
	solo_lectura: bool
	enlace: bool


def _fecha(texto: str) -> float:
	try:
		return datetime.strptime(texto[:19], "%Y-%m-%d %H:%M:%S").timestamp()
	except (ValueError, OverflowError, OSError):
		return 0.0


def analizar_listado(texto: str) -> list[Miembro]:
	"""Bloques ``Clave = valor`` separados por líneas vacías (formato de comprimidos-y-red.md A.3)."""
	miembros = []
	for bloque in re.split(r"\r?\n\s*\r?\n", texto):
		campos: dict[str, str] = {}
		for linea in bloque.splitlines():
			clave, separador, valor = linea.partition(" = ")
			if separador:
				campos[clave.strip()] = valor
		if "Path" not in campos:
			continue
		atributos = campos.get("Attributes", "")
		dos = atributos.split(" ", 1)[0]
		es_carpeta = campos.get("Folder", "") == "+" or "D" in dos
		unix = atributos.split(" ", 1)[1] if " " in atributos else ""
		enlace = unix.lstrip("-").startswith("l") or bool(campos.get("Symbolic Link")) or bool(campos.get("Hard Link"))
		try:
			tamano = int(campos.get("Size", "") or 0)
		except ValueError:
			tamano = 0
		miembros.append(Miembro(campos["Path"], es_carpeta, tamano, _fecha(campos.get("Modified", "")),
			campos.get("Encrypted", "") == "+", "R" in dos, enlace))
	return miembros


def listar(ejecutable: Path | str, archivo: str, contrasena: str | None = None, cancelacion=None) -> list[Miembro]:
	resultado = ejecutar(ejecutable, "l", ["-slt", "-ba"], archivo, contrasena=contrasena, cancelacion=cancelacion,
		tiempo_s=TIEMPO_CORTO * 10)
	return analizar_listado(resultado.salida.decode("utf-8", "replace"))


# ── Extraer ──────────────────────────────────────────────────────────────────


def extraer(ejecutable: Path | str, archivo: str, miembros: list[str], contrasena: str | None = None,
		cancelacion=None) -> dict[str, str]:
	"""Extrae ``miembros`` (nombres tal como los lista 7-Zip) a temporales propios de ``data/temp``.

	Devuelve nombre → temporal. Se extrae con rutas (``x``) en una carpeta única
	para que dos miembros con el mismo nombre en carpetas distintas no choquen;
	después cada archivo pasa a su propio temporal y la carpeta se borra.
	"""
	carpeta = temporales.carpeta_temporal() / f"7z-{uuid.uuid4().hex[:12]}"
	carpeta.mkdir(parents=True, exist_ok=True)
	resultado: dict[str, str] = {}
	try:
		ejecutar(ejecutable, "x", [f"-o{carpeta}", "-y", "-bso0", "-bsp0"], archivo, miembros, contrasena=contrasena,
			cancelacion=cancelacion)
		for miembro in miembros:
			origen = carpeta / miembro.replace("/", "\\")
			if not origen.is_file():
				continue
			destino = temporales.ruta_temporal(miembro.replace("\\", "/").rpartition("/")[2])
			shutil.move(str(origen), destino)
			resultado[miembro] = destino
	except BaseException:
		for temporal in resultado.values():
			temporales.borrar(temporal)
		raise
	finally:
		shutil.rmtree(carpeta, ignore_errors=True)
	return resultado


def probar(ejecutable: Path | str, archivo: str, contrasena: str | None = None, cancelacion=None) -> list[tuple[str, str]]:
	"""``7z t``: lista de (miembro, problema); vacía si está bien."""
	resultado = ejecutar(ejecutable, "t", ["-bso1", "-bsp0"], archivo, contrasena=contrasena, cancelacion=cancelacion)
	if resultado.codigo == 0:
		return []
	problemas = []
	for linea in (resultado.salida + b"\n" + resultado.errores).decode("utf-8", "replace").splitlines():
		if "ERROR:" in linea or "CRC Failed" in linea or "Data Error" in linea:
			problemas.append((linea.strip(), _("Datos dañados")))
	return problemas or [(archivo, _mensaje(resultado.codigo, resultado.errores.decode("utf-8", "replace")))]


# ── Crear ────────────────────────────────────────────────────────────────────


def argumentos_crear(formato: str, nivel: str, contrasena: bool, cifrar_nombres: bool) -> list[str]:
	"""Interruptores de ``7za a`` para 7z o ZIP (con AES-256 si hay contraseña). La contraseña NUNCA va aquí."""
	interruptores = [f"-t{'zip' if formato == 'zip' else '7z'}", _NIVELES.get(nivel, "-mx5"), "-mmt=on", "-scsUTF-8", "-y"]
	if contrasena and formato == "zip":
		interruptores.append("-mem=AES256")
	if contrasena and cifrar_nombres and formato == "7z":
		interruptores.append("-mhe=on")
	return interruptores


def crear(ejecutable: Path | str, destino: str, rutas: list[str], formato: str = "7z", nivel: str = "normal",
		contrasena: str | None = None, cifrar_nombres: bool = False, cancelacion=None,
		al_progreso: Callable[[int], None] | None = None) -> None:
	"""Crea ``destino`` con ``rutas`` (absolutas; cada una se guarda con su último componente y su contenido).

	La lista va en un archivo UTF-8 de ``data/temp`` (``-scsUTF-8``): así no hay
	límite de longitud de la línea de órdenes ni problemas con los nombres.
	"""
	lista = Path(temporales.ruta_temporal("lista-7z.txt"))
	try:
		lista.write_text("\n".join(rutas) + "\n", encoding="utf-8")
		ejecutar(ejecutable, "a", [*argumentos_crear(formato, nivel, bool(contrasena), cifrar_nombres), f"-i@{lista}"], destino,
			contrasena=contrasena, cancelacion=cancelacion, al_progreso=al_progreso or (lambda _n: None))
	finally:
		temporales.borrar(str(lista))
