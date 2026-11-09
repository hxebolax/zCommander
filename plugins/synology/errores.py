# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Errores de DSM en español (diseño 2.0, 13.2; synology.md 3).

Cada error del NAS se convierte en una excepción de la familia
``api.ErrorArchivos`` con un mensaje que el lector de pantalla puede leer tal
cual. Así el proveedor ``synology://`` y las operaciones del motor de
zCommander la tratan como cualquier otro error de archivos (no encontrado,
sin permiso, sin espacio...), y el código del NAS se conserva en ``codigo``.
"""

from __future__ import annotations

from typing import Any

from app.plugins import api

_, _n = api.traduccion("zc_synology")

#: Mensaje del bloqueo del cliente y del 116 del simulador (13.2 y 13.6).
MENSAJE_SOLO_LECTURA = "Operación bloqueada: el servidor está en modo de solo lectura"

COMUNES: dict[int, str] = {
	100: "Error desconocido del NAS.",
	101: "Falta el nombre de la API, el método o la versión.",
	102: "Esta función no existe en el NAS (la API no está; quizá falta el paquete).",
	103: "El NAS no admite esta operación (el método no existe).",
	104: "El NAS no admite esta versión de la función.",
	105: "Tu cuenta no tiene permiso para esta operación.",
	106: "La sesión ha caducado. Vuelve a conectar.",
	107: "La sesión se ha cerrado porque se ha iniciado otra con la misma cuenta.",
	108: "No se ha podido subir el archivo.",
	109: "La conexión es inestable o el NAS está ocupado. Inténtalo de nuevo.",
	110: "La conexión es inestable o el NAS está ocupado. Inténtalo de nuevo.",
	111: "La conexión es inestable o el NAS está ocupado. Inténtalo de nuevo.",
	114: "Faltan datos obligatorios en la petición.",
	115: "No se permite subir archivos aquí.",
	116: MENSAJE_SOLO_LECTURA + ".",
	117: "La conexión es inestable o el NAS está ocupado. Inténtalo de nuevo.",
	118: "La conexión es inestable o el NAS está ocupado. Inténtalo de nuevo.",
	119: "La sesión no es válida. Vuelve a conectar.",
	120: "Algún dato de la petición no es válido.",
	150: "La dirección IP ha cambiado desde que iniciaste sesión. Vuelve a conectar.",
	160: "Tu cuenta no tiene permiso para usar esta aplicación del NAS.",
}

AUTENTICACION: dict[int, str] = {
	400: "Usuario o contraseña incorrectos.",
	401: "La cuenta está desactivada o es de invitado.",
	402: "Permiso denegado para iniciar sesión.",
	403: "Hace falta el código de verificación en dos pasos.",
	404: "El código de verificación no es correcto.",
	405: "El portal de aplicaciones no es correcto.",
	406: "Esta cuenta está obligada a usar la verificación en dos pasos.",
	407: "El NAS ha bloqueado esta dirección tras varios intentos fallidos.",
	408: "La contraseña ha caducado y no se puede cambiar.",
	409: "La contraseña ha caducado.",
	410: "Debes cambiar la contraseña en DSM antes de continuar.",
	411: "La cuenta está bloqueada por demasiados intentos.",
}

FILE_STATION: dict[int, str] = {
	400: "Parámetro no válido en la operación con archivos.",
	401: "Error desconocido en la operación con archivos.",
	402: "El sistema está demasiado ocupado.",
	403: "Usuario o grupo no válido para esta operación.",
	404: "Usuario o grupo no válido para esta operación.",
	405: "Usuario o grupo no válido para esta operación.",
	406: "No se ha podido consultar el servidor de cuentas.",
	407: "Operación no permitida.",
	408: "El archivo o la carpeta no existe.",
	409: "Sistema de archivos no compatible.",
	410: "No se ha podido conectar con el sistema de archivos remoto.",
	411: "El sistema de archivos es de solo lectura.",
	412: "El nombre es demasiado largo.",
	413: "El nombre es demasiado largo.",
	414: "Ya existe un archivo con ese nombre.",
	415: "Se ha superado la cuota de disco.",
	416: "No queda espacio en el NAS.",
	417: "Error de entrada o salida.",
	418: "Nombre o ruta no válidos.",
	419: "Nombre de archivo no válido.",
	420: "Nombre no válido en un sistema FAT.",
	421: "El dispositivo o recurso está ocupado.",
	599: "No existe esa tarea de archivos.",
	900: "No se han podido borrar algunos elementos.",
	1000: "No se han podido copiar o mover algunos elementos.",
	1001: "No se han podido copiar o mover algunos elementos.",
	1002: "Error en la carpeta de destino.",
	1003: "El destino ya existe y no se ha indicado si sobrescribir u omitir.",
	1004: "No se puede sustituir un archivo por una carpeta ni al revés.",
	1006: "Caracteres especiales no admitidos en FAT32.",
	1007: "Archivo de más de 4 GB hacia FAT32.",
	1100: "No se ha podido crear la carpeta.",
	1101: "Hay demasiadas carpetas en la carpeta superior.",
	1200: "No se ha podido cambiar el nombre.",
	1300: "No se ha podido comprimir.",
	1301: "El nombre del archivo comprimido es demasiado largo.",
	1400: "No se ha podido extraer.",
	1401: "No es un archivo comprimido válido.",
	1402: "Error al leer el archivo comprimido.",
	1403: "La contraseña del archivo comprimido no es correcta.",
	1404: "No se ha podido listar el contenido del archivo comprimido.",
	1405: "No se ha encontrado el elemento dentro del archivo comprimido.",
	1800: "La subida no coincide con el tamaño anunciado.",
	1801: "Subida cancelada por inactividad.",
	1802: "Falta el nombre del archivo en la subida.",
	1803: "Subida cancelada.",
	1804: "Archivo demasiado grande para un sistema FAT.",
	1805: "El destino ya existe y no se ha indicado si sobrescribir.",
	2000: "El enlace compartido no existe.",
	2001: "Hay demasiados enlaces compartidos.",
	2002: "No se puede acceder a los enlaces compartidos.",
}

OTROS: dict[tuple[str, int], str] = {
	("SYNO.Core.Hardware", 3712): "El modo de ventilador no es compatible con este modelo.",
	("SYNO.Core.System.Utilization", 1055): "No se han podido obtener los datos de utilización. Se reintenta en el siguiente ciclo.",
	("SYNO.Core.Storage.Volume", 53504): "Operación no posible en el volumen.",
}

#: Códigos de sesión que piden un único nuevo inicio de sesión (13.2).
SESION_CADUCADA = frozenset({106, 107, 119})
SIN_PERMISO = frozenset({105, 160})


def mensaje(codigo: int, api_nombre: str = "") -> str:
	"""Texto en español del error ``codigo`` devuelto por ``api_nombre``."""
	codigo = int(codigo)
	api_nombre = str(api_nombre or "")
	for (prefijo, valor), texto in OTROS.items():
		if valor == codigo and api_nombre.startswith(prefijo):
			return _(texto)
	if api_nombre == "SYNO.API.Auth" and codigo in AUTENTICACION:
		return _(AUTENTICACION[codigo])
	if api_nombre.startswith("SYNO.FileStation.") and codigo in FILE_STATION:
		return _(FILE_STATION[codigo])
	if codigo in COMUNES:
		return _(COMUNES[codigo])
	if api_nombre:
		return _("El NAS ha devuelto el error {c} en la función {a}.").format(c=codigo, a=api_nombre)
	return _("El NAS ha devuelto el error {c}.").format(c=codigo)


# ── Excepciones ──────────────────────────────────────────────────────────────


class ErrorDSM(api.ErrorArchivos):
	"""Error que devolvió el NAS: ``codigo`` de DSM, la API y el método, y el detalle ``errores``."""

	def __init__(self, mensaje_: str, codigo: int = 0, api_nombre: str = "", metodo: str = "", ruta: str = "",
			errores: Any = None) -> None:
		super().__init__(mensaje_, ruta)
		self.codigo = int(codigo)
		self.api = api_nombre
		self.metodo = metodo
		self.errores = errores


class ErrorSesion(ErrorDSM):
	"""106, 107, 119 o 150: la sesión ya no vale."""


class ErrorAutenticacion(ErrorDSM, api.ErrorAcceso):
	"""Inicio de sesión rechazado (400 a 411)."""


class NecesitaCodigo(ErrorAutenticacion):
	"""403 o 406: hace falta el código de verificación en dos pasos."""


class CodigoIncorrecto(ErrorAutenticacion):
	"""404: el código de verificación no es correcto."""


class IPBloqueada(ErrorAutenticacion):
	"""407: el bloqueo automático de DSM. Nunca se reintenta (13.2)."""


class SinPermiso(ErrorDSM, api.ErrorAcceso):
	"""105 o 160: la cuenta no puede usar esa función («Sin permiso con esta cuenta», 13.1)."""


class NoEncontradoDSM(ErrorDSM, api.NoEncontrado):
	pass


class YaExisteDSM(ErrorDSM, api.YaExiste):
	pass


class SinEspacioDSM(ErrorDSM, api.SinEspacio):
	pass


class NombreNoValidoDSM(ErrorDSM, api.NombreNoValido):
	pass


class AccesoDSM(ErrorDSM, api.ErrorAcceso):
	pass


class SoloLecturaDSM(ErrorDSM, api.SoloLectura):
	"""116 del NAS o el bloqueo del propio cliente (13.6)."""


class FuncionAusente(ErrorDSM, api.NoAdmitido):
	"""La API no está en el catálogo del NAS (102) o el cliente no sabe manejar su versión."""


class ErrorConexion(ErrorDSM, api.ErrorRed):
	"""Fallo de red, tiempo agotado, HTTP distinto de 200 o respuesta cortada."""


class HuellaRechazada(ErrorConexion):
	"""El certificado del NAS no coincide con la huella fijada y la persona no lo aceptó."""


class Cancelado(api.Cancelado):
	pass


def solo_lectura(nombre_nas: str = "", api_nombre: str = "", metodo: str = "") -> SoloLecturaDSM:
	"""El bloqueo del cliente: la petición NO se ha enviado."""
	texto = _("{m}. Permita los cambios en el NAS para usar esta acción.").format(m=_(MENSAJE_SOLO_LECTURA))
	if nombre_nas:
		texto = _("{m}: el NAS {n} está en solo lectura. Permita los cambios en el NAS para usar esta acción.").format(
			m=_(MENSAJE_SOLO_LECTURA), n=nombre_nas)
	return SoloLecturaDSM(texto, 116, api_nombre, metodo)


def desde_respuesta(error: Any, api_nombre: str, metodo: str, ruta: str = "") -> ErrorDSM:
	"""La excepción adecuada para ``{"code": N, "errors": ...}`` de una respuesta con ``success: false``.

	En las operaciones de varios archivos el código útil suele venir dentro de
	``errors`` (``{"code": 1100, "errors": [{"code": 408, "path": ...}]}``): se usa
	el interior cuando el exterior es genérico.
	"""
	error = error if isinstance(error, dict) else {}
	codigo = int(error.get("code", 100) or 100)
	detalle = error.get("errors")
	interior = _codigo_interior(detalle)
	if interior and codigo in (401, 1000, 1001, 1100, 1200, 900) and api_nombre.startswith("SYNO.FileStation."):
		codigo_util = interior
	else:
		codigo_util = codigo
	if isinstance(detalle, list) and detalle and isinstance(detalle[0], dict):
		ruta = ruta or str(detalle[0].get("path", ""))
	texto = mensaje(codigo_util, api_nombre)
	if codigo_util == 116:
		return SoloLecturaDSM(texto, 116, api_nombre, metodo, ruta, detalle)
	if api_nombre == "SYNO.API.Auth":
		if codigo_util in (403, 406):
			return NecesitaCodigo(texto, codigo_util, api_nombre, metodo, ruta, detalle)
		if codigo_util == 404:
			return CodigoIncorrecto(texto, codigo_util, api_nombre, metodo, ruta, detalle)
		if codigo_util == 407:
			return IPBloqueada(texto, codigo_util, api_nombre, metodo, ruta, detalle)
		if 400 <= codigo_util <= 411:
			return ErrorAutenticacion(texto, codigo_util, api_nombre, metodo, ruta, detalle)
	if codigo_util in SESION_CADUCADA or codigo_util == 150:
		return ErrorSesion(texto, codigo_util, api_nombre, metodo, ruta, detalle)
	if codigo_util in SIN_PERMISO:
		return SinPermiso(texto, codigo_util, api_nombre, metodo, ruta, detalle)
	if codigo_util in (102, 103, 104):
		return FuncionAusente(texto, codigo_util, api_nombre, metodo, ruta, detalle)
	if api_nombre.startswith("SYNO.FileStation."):
		if codigo_util in (408, 2000):
			return NoEncontradoDSM(texto, codigo_util, api_nombre, metodo, ruta, detalle)
		if codigo_util in (414, 1003, 1805):
			return YaExisteDSM(texto, codigo_util, api_nombre, metodo, ruta, detalle)
		if codigo_util in (415, 416):
			return SinEspacioDSM(texto, codigo_util, api_nombre, metodo, ruta, detalle)
		if codigo_util in (412, 413, 418, 419, 420, 1006):
			return NombreNoValidoDSM(texto, codigo_util, api_nombre, metodo, ruta, detalle)
		if codigo_util in (403, 404, 405, 407, 411):
			return AccesoDSM(texto, codigo_util, api_nombre, metodo, ruta, detalle)
	if codigo_util in (109, 110, 111, 117, 118):
		return ErrorConexion(texto, codigo_util, api_nombre, metodo, ruta, detalle)
	return ErrorDSM(texto, codigo_util, api_nombre, metodo, ruta, detalle)


def _codigo_interior(detalle: Any) -> int:
	if isinstance(detalle, list):
		for elemento in detalle:
			if isinstance(elemento, dict) and elemento.get("code"):
				return int(elemento["code"])
	return 0
