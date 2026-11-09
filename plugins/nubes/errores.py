# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Traducción de los errores de rclone a ``ErrorArchivos`` en español (diseño 2.0, 12.2; rclone.md 3.8).

rclone devuelve ``{"error": "...", "status": 404}``: 404 si falta el objeto o la
carpeta, 400 si un parámetro está mal y 500 en lo demás, con el texto en inglés
del propio rclone o del servicio. Aquí se decide primero por el estado y después
por patrones del texto, de lo más concreto a lo más general. El texto original
solo va al registro (redactado), nunca a la persona.

``redactar`` tapa fichas de acceso y contraseñas: se aplica a todo lo que rclone
escribe en ``stderr`` antes de pasarlo al registro (además del filtro de los
manejadores del registro de zCommander), y a los textos de error.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.plugins import api

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

#: Puerto fijo del servidor de autorización de rclone (lib/oauthutil).
PUERTO_OAUTH = 53682

_REDACCION = (
	# usuario:clave@servidor en direcciones
	(re.compile(r"(?P<pre>[a-z][a-z0-9+.-]*://[^\s/:@]+:)[^\s@/]+(?=@)", re.IGNORECASE), r"\g<pre>***"),
	# "access_token":"...", refresh_token=..., token: ..., appPassword...
	(re.compile(r"(?P<pre>(?:\b|_)(?:access_token|refresh_token|id_token|token|client_secret|secret_access_key|apppassword|"
		r"password2?|pass|passwd|api_key|otp_code|trust_token|session_id)\\?[\"']?\\?\s*[=:]\s*\\?[\"']?)[^\s\"'\\&,;}]+",
		re.IGNORECASE), r"\g<pre>***"),
	# Authorization: Bearer ...
	(re.compile(r"(?P<pre>\bAuthorization\\?[\"']?\s*[=:]\s*\\?[\"']?)(?:(?:Bearer|Basic)\s+)?[^\s\"'\\,;}]+", re.IGNORECASE),
		r"\g<pre>***"),
	# RCLONE_CONFIG_PASS=..., RCLONE_RC_PASS=...
	(re.compile(r"(?P<pre>\bRCLONE_[A-Z0-9_]*(?:PASS|USER|TOKEN|SECRET)\b\s*[=:]\s*)\S+", re.IGNORECASE), r"\g<pre>***"),
	# code=... y state=... de la vuelta de OAuth
	(re.compile(r"(?P<pre>[?&](?:code|state)=)[^\s&\"']+", re.IGNORECASE), r"\g<pre>***"),
)


def redactar(texto: str) -> str:
	"""El texto sin fichas de acceso, contraseñas ni códigos de autorización."""
	for patron, sustituto in _REDACCION:
		texto = patron.sub(sustituto, texto)
	return texto


class ErrorRC(Exception):
	"""Respuesta de error del API remoto de rclone (antes de traducirla)."""

	def __init__(self, estado: int, texto: str, ruta: str = "") -> None:
		super().__init__(f"{estado} {ruta}: {texto}")
		self.estado = estado
		self.texto = texto
		self.ruta = ruta


class ErrorReconectar(api.ErrorAcceso):
	"""La autorización de la cuenta caducó o se revocó: la acción es «Volver a autorizar»."""


# (patrones, clase, mensaje); el primero que coincide gana. Los mensajes usan {n} (nombre o ruta).
_TABLA: tuple[tuple[tuple[str, ...], type[api.ErrorArchivos], str], ...] = (
	(("oauth authentication was cancelled", "authentication was cancelled"), api.Cancelado, "Autorización cancelada"),
	(("context canceled",), api.Cancelado, "Operación cancelada"),
	(("failed to start auth webserver",), api.ErrorRed,
		"Otro programa está usando el puerto de autorización 53682 (quizá otro rclone abierto). Ciérrelo y vuelva a intentarlo"),
	(("unable to decrypt configuration", "couldn't decrypt configuration", "wrong password", "config file is encrypted"),
		api.ErrorAcceso, "No se pudo abrir la configuración cifrada de las nubes (¿se copió desde otro equipo?)"),
	(("didn't find section in config file",), api.NoEncontrado, "La cuenta {n} no existe en el motor de nubes"),
	(("invalid_grant", "token expired", "couldn't fetch token", "maybe token expired", "token has been expired or revoked",
		"unauthorized_client", "invalid_client"), ErrorReconectar,
		"La autorización de la cuenta caducó o se revocó. Pulse Volver a autorizar la cuenta"),
	(("is a directory not a file",), api.NoAdmitido, "Es una carpeta, no un archivo"),
	(("is a file not a directory", "not a directory"), api.NoAdmitido, "Es un archivo, no una carpeta"),
	(("directory not empty",), api.ErrorAcceso, "La carpeta no está vacía"),
	(("destination already exists", "already exists"), api.YaExiste, "Ya existe un elemento con ese nombre en el destino"),
	(("file name too long", "name too long"), api.NombreNoValido, "El nombre es demasiado largo para este servicio"),
	(("storagequotaexceeded", "quota exceeded", "insufficient_space", "storage full", "not enough space", "insufficientstorage",
		"no space left"), api.SinEspacio, "No queda espacio en la cuenta de nube"),
	(("ratelimitexceeded", "userratelimitexceeded", "too_many_requests", "too many requests", "over quota", "rate limit",
		"429"), api.ErrorRed, "El servicio pide esperar (límite de peticiones o de transferencia); se reintentará más tarde"),
	(("permission denied", "insufficientpermissions", "accessdenied", "access denied", "forbidden", "403"), api.ErrorAcceso,
		"No tiene permiso para esto en la nube"),
	(("401", "unauthorized"), ErrorReconectar,
		"La autorización de la cuenta caducó o se revocó. Pulse Volver a autorizar la cuenta"),
	(("object not found", "directory not found", "file not found", "not found", "404", "doesn't exist", "no such file"),
		api.NoEncontrado, "No existe en la nube: {n}"),
	(("optional feature not implemented", "can't purge", "incompatible remotes", "can't share directories with link",
		"doesn't support", "not supported", "can't move", "can't copy"), api.NoAdmitido, "Este servicio no permite esta operación"),
	(("can't upload empty files",), api.NoAdmitido, "Este servicio no admite archivos vacíos"),
	(("overlapping remotes", "overlapping"), api.NombreNoValido, "El origen y el destino se solapan"),
	(("immutable file modified",), api.ErrorAcceso, "El destino es inmutable y ha cambiado"),
	(("not deleting files as there were io errors",), api.ErrorArchivos,
		"No se borró nada en el destino porque hubo errores de lectura"),
	(("cannot find winfsp", "winfsp"), api.NoAdmitido,
		"Para montar como letra de unidad hace falta WinFsp, que no está instalado"),
	(("dial tcp", "no such host", "connection refused", "timeout", "timed out", "tls handshake", "eof", "connection reset",
		"network is unreachable", "i/o timeout"), api.ErrorRed, "No hay conexión con el servicio de nube"),
)


def _clasificar(texto: str, estado: int = 0) -> tuple[type[api.ErrorArchivos], str]:
	bajo = texto.casefold()
	for patrones, clase, mensaje in _TABLA:
		if any(p in bajo for p in patrones):
			return clase, mensaje
	if estado == 404:
		return api.NoEncontrado, "No existe en la nube: {n}"
	if estado == 400:
		return api.ErrorArchivos, "rclone rechazó la petición; detalles en el registro"
	return api.ErrorArchivos, "Error del servicio de nube: la operación no se pudo completar (detalles en el registro)"


def traducir(error: Any, nombre: str = "", ruta: str = "") -> api.ErrorArchivos:
	"""``ErrorArchivos`` con mensaje en español para un ``ErrorRC``, un texto o una excepción de red.

	:param nombre: elemento o cuenta afectada (para «No existe en la nube: <nombre>»).
	:param ruta: ruta para ``ErrorArchivos.ruta``.
	"""
	if isinstance(error, api.ErrorArchivos):
		return error
	estado = 0
	if isinstance(error, ErrorRC):
		texto, estado = error.texto, error.estado
	elif isinstance(error, (ConnectionError, TimeoutError)):
		texto = "connection refused" if isinstance(error, ConnectionRefusedError) else f"timeout {error}"
	elif isinstance(error, OSError):
		texto = f"connection reset {error}"
	else:
		texto = str(error)
	clase, mensaje = _clasificar(texto, estado)
	log.info("rclone: %s", redactar(texto)[:2000])
	return clase(_(mensaje).format(n=nombre or ruta), ruta)


def es_reconectar(error: BaseException) -> bool:
	return isinstance(error, ErrorReconectar)
