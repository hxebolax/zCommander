# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Nextcloud y ownCloud con Login Flow v2 (diseño 2.0, 12.4; nubes.md 3.9).

1. ``POST https://<servidor>/index.php/login/v2`` (anónimo) devuelve la URL
   ``login`` (la abre o la copia la persona) y ``poll`` con su ``token``.
2. Se consulta ``poll.endpoint`` con el ``token`` cada 2 s (hasta 10 min): 404
   mientras espera y 200 una sola vez con ``server``, ``loginName`` y ``appPassword``.
3. La contraseña de aplicación va a los secretos y la cuenta se crea como WebDAV
   nativo en ``https://<servidor>/remote.php/dav/files/<usuario>/``.

Nunca se teclea la contraseña real; la verificación en dos pasos ocurre en el
navegador y la contraseña de aplicación se revoca desde la web. Sin wx: usa
``zc.red`` (``ClienteRed``) y corre en un hilo de trabajo.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.plugins import api

from .cliente_rc import esperar

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

INTERVALO_S = 2.0
TIEMPO_MAX_S = 600.0


@dataclass(frozen=True)
class InicioLogin:
	login: str
	token: str
	endpoint: str


@dataclass(frozen=True)
class CredencialesNextcloud:
	servidor: str
	usuario: str
	contrasena_app: str

	@property
	def url_webdav(self) -> str:
		return url_webdav(self.servidor, self.usuario)


def normalizar_servidor(texto: str) -> str:
	"""«nube.ejemplo.com» → «https://nube.ejemplo.com» (sin barra final ni ``/index.php``)."""
	texto = texto.strip()
	if not texto:
		raise api.NombreNoValido(_("Escriba la dirección del servidor"))
	if "://" not in texto:
		texto = "https://" + texto
	partes = urllib.parse.urlsplit(texto)
	ruta = partes.path.rstrip("/")
	for sobra in ("/index.php", "/remote.php/webdav", "/remote.php/dav"):
		if sobra in ruta:
			ruta = ruta.split(sobra, 1)[0]
	return urllib.parse.urlunsplit((partes.scheme, partes.netloc, ruta, "", ""))


def url_webdav(servidor: str, usuario: str) -> str:
	return f"{servidor.rstrip('/')}/remote.php/dav/files/{urllib.parse.quote(usuario, safe='')}/"


def _estado_de(error: BaseException) -> int:
	causa = error.__cause__
	return int(getattr(causa, "estado", 0) or 0)


def iniciar(red: Any, servidor: str) -> InicioLogin:
	"""Primer paso: pide al servidor la URL de inicio de sesión y el token de consulta."""
	servidor = normalizar_servidor(servidor)
	try:
		try:
			respuesta = red.enviar(f"{servidor}/index.php/login/v2", b"", cabeceras={"Accept": "application/json"})
		except api.ErrorRed as error:
			if _estado_de(error):
				raise
			# Un corte de la conexión: pedir otro flujo de inicio de sesión es inocuo, se repite una vez.
			log.info("Se repite el inicio de Login Flow v2 tras un corte de la conexión")
			respuesta = red.enviar(f"{servidor}/index.php/login/v2", b"", cabeceras={"Accept": "application/json"})
		datos = respuesta.json()
		return InicioLogin(str(datos["login"]), str(datos["poll"]["token"]), str(datos["poll"]["endpoint"]))
	except (KeyError, TypeError, ValueError) as error:
		raise api.ErrorArchivos(_("El servidor {s} no parece un Nextcloud u ownCloud con Login Flow v2").format(s=servidor)) from error


def esperar_credenciales(red: Any, inicio: InicioLogin, cancelacion: Any = None, *, intervalo_s: float = INTERVALO_S,
		tiempo_max_s: float = TIEMPO_MAX_S, al_esperar: Callable[[float], None] | None = None) -> CredencialesNextcloud:
	"""Consulta ``poll`` hasta recibir la contraseña de aplicación (404 = sigue esperando)."""
	cuerpo = urllib.parse.urlencode({"token": inicio.token}).encode("ascii")
	cabeceras = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
	comienzo = time.monotonic()
	cortes = 0
	while True:
		api.comprobar(cancelacion)
		try:
			respuesta = red.enviar(inicio.endpoint, cuerpo, cabeceras=cabeceras)
			datos = respuesta.json()
			return CredencialesNextcloud(str(datos["server"]).rstrip("/"), str(datos["loginName"]), str(datos["appPassword"]))
		except api.ErrorRed as error:
			estado = _estado_de(error)
			if estado == 0:
				# Corte pasajero de la red mientras se espera: se sigue consultando (5 seguidos se dan por fallo).
				cortes += 1
				if cortes >= 5:
					raise
			elif estado != 404:
				raise
			else:
				cortes = 0
		except (KeyError, TypeError, ValueError) as error:
			raise api.ErrorArchivos(_("El servidor devolvió una respuesta que no se entiende")) from error
		transcurrido = time.monotonic() - comienzo
		if transcurrido > tiempo_max_s:
			raise api.ErrorRed(_("No se recibió la autorización a tiempo"))
		if al_esperar is not None:
			al_esperar(transcurrido)
		esperar(cancelacion, intervalo_s)
