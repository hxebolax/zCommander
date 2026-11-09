# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Enlaces en Windows: simbólicos, uniones de carpeta, enlaces duros y accesos directos (sección 8.11).

Por qué un módulo propio:

- Cada tipo tiene requisitos distintos que la persona no tiene por qué conocer
  (el simbólico pide el modo de desarrollador o ser administrador; la unión
  solo vale para carpetas locales; el duro solo para archivos del mismo
  volumen). ``problema`` los comprueba ANTES de intentarlo y dice qué falla.
- Si el simbólico falla por privilegios se lanza ``SinPrivilegios``, con la
  explicación de cómo activar el modo de desarrollador, para que la interfaz
  ofrezca una unión o un acceso directo, que no necesitan permisos.

Todas las funciones que crean algo tocan el disco: se llaman desde un hilo
de trabajo. Los accesos directos usan COM (``IShellLink``) y lo inician y
cierran en el propio hilo.
"""

from __future__ import annotations

import builtins
import ctypes
import logging
import os
import subprocess

from app.services import errores
from app.services.vfs import base, rutas

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


SIMBOLICO = "simbolico"
UNION = "union"
DURO = "duro"
ACCESO_DIRECTO = "acceso_directo"
TIPOS = (SIMBOLICO, UNION, DURO, ACCESO_DIRECTO)

ERROR_PRIVILEGIO = 1314
ERROR_DISTINTO_VOLUMEN = 17


def nombre_tipo(tipo: str) -> str:
	return {
		SIMBOLICO: _("Enlace simbólico"),
		UNION: _("Unión de carpeta"),
		DURO: _("Enlace duro"),
		ACCESO_DIRECTO: _("Acceso directo (.lnk)"),
	}[tipo]


def explicacion(tipo: str) -> str:
	"""Para el campo de explicación del diálogo: qué es y qué pide cada tipo."""
	textos = {
		SIMBOLICO: _(
			"Un enlace simbólico apunta a un archivo o una carpeta, en este disco, en otro o en la red. "
			"Los programas lo ven como el original. Windows exige el modo de desarrollador o ejecutar "
			"zCommander como administrador."),
		UNION: _(
			"Una unión apunta a una carpeta de un disco local. Los programas la ven como la carpeta original "
			"y no necesita permisos especiales. No sirve para archivos ni para carpetas de red."),
		DURO: _(
			"Un enlace duro es otro nombre para el mismo archivo: los dos comparten el contenido. Solo sirve "
			"para archivos (no carpetas) del mismo disco y no necesita permisos especiales."),
		ACCESO_DIRECTO: _(
			"Un acceso directo es un archivo .lnk que abre el destino desde el Explorador y el menú Inicio. "
			"Los programas no lo ven como el original. No necesita permisos especiales."),
	}
	texto = textos[tipo]
	if tipo == SIMBOLICO and not puede_crear_simbolicos():
		texto += " " + _("Ahora mismo no tiene ese permiso: si falla, se le ofrecerá crear una unión o un acceso directo.")
	return texto


class SinPrivilegios(base.ErrorAcceso):
	"""Windows rechaza el enlace simbólico por falta de privilegios (error 1314)."""

	def __init__(self, ruta: str = "") -> None:
		super().__init__(mensaje_sin_privilegios(), ruta)


def mensaje_sin_privilegios() -> str:
	return _(
		"Windows solo deja crear enlaces simbólicos con el modo de desarrollador activado o ejecutando "
		"zCommander como administrador. Para activar el modo de desarrollador: Configuración de Windows, "
		"Sistema, Para programadores, Modo de desarrollador. Mientras tanto puede crear una unión "
		"(solo carpetas) o un acceso directo, que no necesitan permisos.")


# ── Permisos ─────────────────────────────────────────────────────────────────


def modo_desarrollador_activo() -> bool:
	"""Lee (sin cambiar nada) si el modo de desarrollador de Windows está activo."""
	try:
		import winreg

		with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock") as clave:
			valor, _tipo = winreg.QueryValueEx(clave, "AllowDevelopmentWithoutDevLicense")
			return int(valor) == 1
	except OSError:
		log.debug("No se pudo leer el modo de desarrollador (se da por desactivado)", exc_info=True)
		return False


def es_administrador() -> bool:
	try:
		return bool(ctypes.windll.shell32.IsUserAnAdmin())
	except (AttributeError, OSError):
		log.debug("No se pudo saber si el proceso es administrador", exc_info=True)
		return False


def puede_crear_simbolicos() -> bool:
	return modo_desarrollador_activo() or es_administrador()


# ── Comprobaciones previas ───────────────────────────────────────────────────


def _destino_resuelto(enlace: str, destino: str) -> str:
	"""Un destino relativo se interpreta desde la carpeta del enlace (como hace Windows)."""
	if os.path.isabs(destino):
		return os.path.normpath(destino)
	return os.path.normpath(os.path.join(os.path.dirname(enlace), destino))


def problema(tipo: str, enlace: str, destino: str) -> str | None:
	"""Por qué no se puede crear ese enlace, o ``None`` si parece posible.

	Toca el disco (existencia y tipo del destino): llámela con rutas locales.
	"""
	if tipo not in TIPOS:
		return _("Tipo de enlace desconocido.")
	enlace, destino = enlace.strip(), destino.strip()
	if not destino:
		return _("Escriba el destino, es decir, a qué archivo o carpeta apunta el enlace.")
	if not enlace:
		return _("Escriba la ruta completa del enlace que se va a crear.")
	if not os.path.isabs(enlace):
		return _("El nombre del enlace debe ser una ruta completa, por ejemplo D:\\Enlaces\\Fotos.")
	nombre = os.path.basename(rutas.normalizar(enlace))
	motivo = rutas.problema_en_nombre(nombre)
	if motivo:
		return motivo
	carpeta = os.path.dirname(rutas.normalizar(enlace))
	if not os.path.isdir(carpeta):
		return _("No existe la carpeta donde se crearía el enlace: {c}").format(c=carpeta)
	if os.path.lexists(enlace):
		return _("Ya existe «{n}». Elija otro nombre para el enlace.").format(n=nombre)
	real = _destino_resuelto(enlace, destino)
	if not os.path.lexists(real):
		return _("No existe el destino: {d}").format(d=real)
	if os.path.normcase(real) == os.path.normcase(rutas.normalizar(enlace)):
		return _("El enlace no puede apuntar a sí mismo.")
	if tipo == UNION:
		if not os.path.isdir(real):
			return _("Una unión solo puede apuntar a una carpeta. Para un archivo use un enlace simbólico, duro o un acceso directo.")
		if real.startswith("\\\\"):
			return _("Una unión no puede apuntar a una carpeta de red. Use un enlace simbólico o un acceso directo.")
	elif tipo == DURO:
		if os.path.isdir(real):
			return _("Un enlace duro solo puede apuntar a un archivo. Para una carpeta use una unión o un enlace simbólico.")
		if not rutas.mismo_volumen(real, rutas.normalizar(enlace)):
			return _("Un enlace duro tiene que estar en el mismo disco que el archivo. Use un enlace simbólico o un acceso directo.")
	elif tipo == ACCESO_DIRECTO and not nombre.lower().endswith(".lnk"):
		return _("El nombre de un acceso directo debe terminar en .lnk.")
	return None


# ── Creación ─────────────────────────────────────────────────────────────────


def _convertir(error: OSError, ruta: str) -> base.ErrorArchivos:
	if getattr(error, "winerror", None) == ERROR_PRIVILEGIO:
		return SinPrivilegios(ruta)
	if getattr(error, "winerror", None) == ERROR_DISTINTO_VOLUMEN:
		return base.ErrorArchivos(_("Un enlace duro tiene que estar en el mismo disco que el archivo."), ruta)
	return errores.convertir(error, ruta)


def crear(tipo: str, enlace: str, destino: str) -> None:
	"""Crea el enlace del tipo pedido tras comprobarlo con ``problema``.

	:raises SinPrivilegios: el simbólico necesita el modo de desarrollador o administrador.
	:raises ErrorArchivos: cualquier otro motivo, con el mensaje para la persona.
	"""
	motivo = problema(tipo, enlace, destino)
	if motivo:
		raise base.ErrorArchivos(motivo, enlace)
	enlace, destino = rutas.normalizar(enlace.strip()), destino.strip()
	if tipo == SIMBOLICO:
		crear_simbolico(enlace, destino)
	elif tipo == UNION:
		crear_union(enlace, _destino_resuelto(enlace, destino))
	elif tipo == DURO:
		crear_duro(enlace, _destino_resuelto(enlace, destino))
	else:
		crear_acceso_directo(enlace, _destino_resuelto(enlace, destino))
	log.info("Enlace creado (%s): %s -> %s", tipo, enlace, destino)


def crear_simbolico(enlace: str, destino: str) -> None:
	"""``CreateSymbolicLinkW`` (Python ya pide el modo sin privilegios si el de desarrollador está activo)."""
	es_carpeta = os.path.isdir(_destino_resuelto(enlace, destino))
	try:
		os.symlink(destino, enlace, target_is_directory=es_carpeta)
	except OSError as error:
		raise _convertir(error, enlace) from error


def crear_union(enlace: str, destino: str) -> None:
	"""Unión de carpeta (punto de montaje). No necesita privilegios."""
	try:
		import _winapi

		crear = getattr(_winapi, "CreateJunction", None)
	except ImportError:
		crear = None
	try:
		if crear is not None:
			crear(os.path.abspath(destino), enlace)
			return
		# Respaldo: «mklink /J» es una orden interna de cmd (sin shell=True: argumentos en lista).
		resultado = subprocess.run(["cmd", "/c", "mklink", "/J", enlace, os.path.abspath(destino)],
			capture_output=True, text=True, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
		if resultado.returncode != 0:
			raise base.ErrorArchivos(_("No se pudo crear la unión: {e}").format(e=(resultado.stderr or resultado.stdout).strip()), enlace)
	except OSError as error:
		raise _convertir(error, enlace) from error


def crear_duro(enlace: str, destino: str) -> None:
	"""``CreateHardLinkW``: otro nombre para el mismo archivo del mismo volumen."""
	try:
		os.link(destino, enlace)
	except OSError as error:
		raise _convertir(error, enlace) from error


def crear_acceso_directo(enlace: str, destino: str, argumentos: str = "", descripcion: str = "") -> None:
	"""Archivo ``.lnk`` con ``IShellLink`` (COM iniciado y cerrado en este hilo)."""
	try:
		import pythoncom
		from win32com.shell import shell
	except ImportError as error:
		raise base.NoAdmitido(_("Para crear accesos directos hace falta pywin32."), enlace) from error
	pythoncom.CoInitialize()
	try:
		vinculo = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
		vinculo.SetPath(destino)
		carpeta = destino if os.path.isdir(destino) else os.path.dirname(destino)
		vinculo.SetWorkingDirectory(carpeta)
		if argumentos:
			vinculo.SetArguments(argumentos)
		if descripcion:
			vinculo.SetDescription(descripcion)
		vinculo.QueryInterface(pythoncom.IID_IPersistFile).Save(enlace, 0)
	except pythoncom.com_error as error:
		log.warning("No se pudo crear el acceso directo %s", enlace, exc_info=True)
		raise base.ErrorArchivos(_("No se pudo crear el acceso directo."), enlace) from error
	finally:
		pythoncom.CoUninitialize()


# ── Consulta ─────────────────────────────────────────────────────────────────


def destino_acceso_directo(ruta: str) -> str:
	"""Ruta a la que apunta un ``.lnk`` (cadena vacía si no se puede leer)."""
	try:
		import pythoncom
		from win32com.shell import shell
	except ImportError:
		log.debug("Sin pywin32 para leer %s", ruta, exc_info=True)
		return ""
	pythoncom.CoInitialize()
	try:
		vinculo = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
		vinculo.QueryInterface(pythoncom.IID_IPersistFile).Load(ruta, 0)
		return vinculo.GetPath(0)[0]
	except pythoncom.com_error:
		log.debug("No se pudo leer el acceso directo %s", ruta, exc_info=True)
		return ""
	finally:
		pythoncom.CoUninitialize()


def tipo_de(ruta: str) -> str | None:
	"""Qué clase de enlace es ``ruta`` (``SIMBOLICO``, ``UNION``, ``DURO``, ``ACCESO_DIRECTO``) o ``None``."""
	try:
		if os.path.islink(ruta):
			return SIMBOLICO
		if getattr(os.path, "isjunction", None) and os.path.isjunction(ruta):
			return UNION
		if ruta.lower().endswith(".lnk") and os.path.isfile(ruta):
			return ACCESO_DIRECTO
		st = os.stat(ruta, follow_symlinks=False)
		if not os.path.isdir(ruta) and st.st_nlink > 1:
			return DURO
	except OSError:
		log.debug("No se pudo saber el tipo de enlace de %s", ruta, exc_info=True)
	return None
