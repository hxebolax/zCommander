# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Traducción de errores del sistema a mensajes útiles en español.

La persona usuaria no debe ver «[WinError 32]»: ve «El archivo está abierto
en otro programa» y, si quiere, el detalle técnico está en el registro.
"""

from __future__ import annotations

import builtins
import errno

from app.services.vfs import base


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _mensajes_winerror() -> dict[int, str]:
	return {
		2: _("No se encuentra el archivo."),
		3: _("No se encuentra la ruta."),
		5: _("No tiene permiso o el archivo está protegido."),
		15: _("No se encuentra la unidad."),
		19: _("El disco está protegido contra escritura."),
		21: _("La unidad no está preparada (¿falta el disco?)."),
		32: _("El archivo está abierto en otro programa."),
		33: _("Otro programa tiene bloqueada una parte del archivo."),
		39: _("El disco está lleno."),
		53: _("No se encuentra la ruta de red."),
		64: _("Se perdió la conexión de red."),
		67: _("No se encuentra el recurso compartido de red."),
		80: _("El archivo ya existe."),
		112: _("No hay espacio suficiente en el disco."),
		121: _("Se agotó el tiempo de espera del dispositivo."),
		123: _("El nombre, la carpeta o la etiqueta no son válidos."),
		145: _("La carpeta no está vacía."),
		183: _("Ya existe un archivo o carpeta con ese nombre."),
		206: _("El nombre o la ruta son demasiado largos."),
		1314: _("Hace falta un privilegio que no tiene (por ejemplo, para crear enlaces simbólicos)."),
		1392: _("El archivo o la carpeta están dañados y no se pueden leer."),
		1920: _("El sistema no puede acceder al archivo (quizá está solo en la nube)."),
		4390: _("El archivo no es un punto de análisis válido."),
	}


def mensaje_para_usuario(error: BaseException) -> str:
	"""Frase en español que explica ``error``."""
	if isinstance(error, base.ErrorArchivos):
		return error.mensaje
	if isinstance(error, OSError):
		winerror = getattr(error, "winerror", None)
		mensajes = _mensajes_winerror()
		if winerror in mensajes:
			texto = mensajes[winerror]
		elif isinstance(error, PermissionError):
			texto = mensajes[5]
		elif isinstance(error, FileNotFoundError):
			texto = mensajes[2]
		elif isinstance(error, FileExistsError):
			texto = mensajes[183]
		elif error.errno == errno.ENOSPC:
			texto = mensajes[112]
		elif isinstance(error, TimeoutError):
			texto = _("Se agotó el tiempo de espera.")
		elif isinstance(error, ConnectionError):
			texto = _("Se perdió la conexión.")
		else:
			texto = error.strerror or str(error) or _("Error desconocido del sistema.")
		ruta = error.filename
		return f"{texto} ({ruta})" if ruta else texto
	return str(error) or type(error).__name__


def convertir(error: OSError, ruta: str = "") -> base.ErrorArchivos:
	"""Convierte un ``OSError`` en el ``ErrorArchivos`` adecuado (con la causa encadenada por quien lanza)."""
	winerror = getattr(error, "winerror", None)
	mensaje = mensaje_para_usuario(error)
	ruta = ruta or (error.filename or "")
	if isinstance(error, FileNotFoundError) or winerror in (2, 3, 15):
		return base.NoEncontrado(mensaje, ruta)
	if isinstance(error, FileExistsError) or winerror in (80, 183):
		return base.YaExiste(mensaje, ruta)
	if isinstance(error, PermissionError) or winerror in (5, 32, 33, 1314):
		return base.ErrorAcceso(mensaje, ruta)
	if winerror in (39, 112) or error.errno == errno.ENOSPC:
		return base.SinEspacio(mensaje, ruta)
	if winerror in (21, 53, 64, 67, 121) or isinstance(error, (TimeoutError, ConnectionError)):
		return base.ErrorRed(mensaje, ruta)
	if winerror in (123, 206):
		return base.NombreNoValido(mensaje, ruta)
	return base.ErrorArchivos(mensaje, ruta)
