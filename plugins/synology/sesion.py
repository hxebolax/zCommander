# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Inicio de sesión en DSM 7 con verificación en dos pasos (diseño 2.0, 13.2; synology.md 2).

``SYNO.API.Auth`` v7 ``login`` con ``format=sid``, ``enable_syno_token=yes``,
``session=webui`` y el ``device_id`` guardado si lo hay. Con 403 o 406 se pide el
código de 6 dígitos (suena ``zc.synology:otp``) y se repite con ``otp_code``,
``enable_device_token=yes`` y ``device_name``; el ``device_id`` devuelto se
guarda en los secretos. 404 es «código incorrecto» (se puede repetir, contando
los intentos). 407 (IP bloqueada) no se reintenta jamás, y la contraseña se
prueba UNA sola vez por acción de la persona: nunca hay bucles de contraseña
que activen el bloqueo automático de DSM.

Nunca se registra el cuerpo de una respuesta de ``SYNO.API.Auth`` ni ninguno de
sus parámetros.
"""

from __future__ import annotations

import logging
import platform
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.plugins import api

from . import errores

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.sesion")

INTENTOS_CODIGO = 3


@dataclass
class DatosSesion:
	sid: str
	synotoken: str
	cuenta: str


class Preguntas(Protocol):
	"""Lo que el cliente pregunta a la persona. Se llama SIEMPRE desde un hilo de trabajo."""

	def credenciales(self, servidor: Any, motivo: str) -> tuple[str, str, bool] | None:
		"""(usuario, contraseña, recordar) o ``None`` si cancela."""

	def codigo(self, servidor: Any, mensaje: str) -> tuple[str, bool] | None:
		"""(código de 6 dígitos, recordar este equipo) o ``None`` si cancela."""

	def huella(self, servidor: Any, huella: str, anterior: str) -> str:
		"""«recordar», «sesion» o «cancelar»."""

	def contrasena_dsm(self, servidor: Any, motivo: str) -> str | None:
		"""La contraseña de la cuenta para la confirmación de DSM (``SynoConfirmPWToken``)."""


Transporte = Callable[[str, str, int, str, dict[str, str]], dict[str, Any]]


def nombre_equipo() -> str:
	"""Nombre con el que este equipo aparece en «Dispositivos de confianza» de DSM."""
	return f"zCommander-{platform.node() or 'equipo'}"


class Iniciador:
	"""Hace el inicio de sesión completo; ``contrasena`` queda en memoria para el reintento único de 106, 107 y 119."""

	def __init__(self, servidor: Any, transporte: Transporte, preguntas: Preguntas | None, secretos: Any,
			sonar: Callable[[str], None] | None = None) -> None:
		self.servidor = servidor
		self._transporte = transporte
		self._preguntas = preguntas
		self._secretos = secretos
		self._sonar = sonar or (lambda _evento: None)
		self.contrasena: str | None = None

	# ── Secretos ─────────────────────────────────────────────────────────────

	def _secreto(self, nombre: str) -> str | None:
		if self._secretos is None:
			return None
		try:
			return self._secretos.obtener(f"{self.servidor.id}:{nombre}")
		except Exception:  # noqa: BLE001 - un almacén de secretos ilegible se trata como vacío (se pregunta)
			log.warning("No se pudo leer el secreto %s del NAS %s", nombre, self.servidor.id, exc_info=True)
			return None

	def _guardar(self, nombre: str, valor: str) -> None:
		if self._secretos is None or self.servidor.demostracion:
			return
		try:
			self._secretos.guardar(f"{self.servidor.id}:{nombre}", valor)
		except Exception:  # noqa: BLE001 - no poder guardar no impide la sesión; se registra
			log.warning("No se pudo guardar el secreto %s del NAS %s", nombre, self.servidor.id, exc_info=True)

	def _borrar(self, nombre: str) -> None:
		if self._secretos is None:
			return
		try:
			self._secretos.borrar(f"{self.servidor.id}:{nombre}")
		except Exception:  # noqa: BLE001 - borrar un secreto que no está no es un fallo
			log.debug("No se pudo borrar el secreto %s del NAS %s", nombre, self.servidor.id, exc_info=True)

	# ── Inicio de sesión ─────────────────────────────────────────────────────

	def iniciar(self, ruta: str, version: int, reintento: bool = False) -> DatosSesion:
		"""Una sola prueba de la contraseña. En un reintento (106, 107, 119) no se pregunta nada nuevo."""
		usuario = self.servidor.usuario
		contrasena = self.contrasena
		guardar_contrasena = False
		if contrasena is None and self.servidor.recordar_contrasena:
			contrasena = self._secreto("contrasena")
		if contrasena is None:
			if reintento or self._preguntas is None:
				raise errores.ErrorSesion(_("La sesión con el NAS ha caducado y no hay contraseña para volver a entrar."), 119,
					"SYNO.API.Auth", "login")
			respuesta = self._preguntas.credenciales(self.servidor, _("Escriba la contraseña de {u} en {n}.").format(
				u=usuario or _("su cuenta"), n=self.servidor.nombre))
			if respuesta is None:
				raise api.Cancelado(_("Conexión cancelada"))
			usuario, contrasena, guardar_contrasena = respuesta
			if usuario:
				self.servidor.usuario = usuario
		parametros = {"account": self.servidor.usuario, "passwd": contrasena, "session": "webui", "format": "sid",
			"enable_syno_token": "yes"}
		dispositivo = self._secreto("device_id")
		if dispositivo:
			parametros["device_id"] = dispositivo
			parametros["device_name"] = nombre_equipo()
		try:
			datos = self._enviar(ruta, version, parametros)
		except errores.NecesitaCodigo:
			if dispositivo:
				log.info("El dispositivo de confianza del NAS %s ya no vale: se pide el código", self.servidor.id)
				self._borrar("device_id")
			datos = self._con_codigo(ruta, version, parametros, reintento)
		except errores.IPBloqueada:
			raise
		except errores.ErrorAutenticacion as error:
			if error.codigo == 400 and self.contrasena is None and not guardar_contrasena:
				# La contraseña guardada ya no vale: se olvida para preguntar la próxima vez.
				self._borrar("contrasena")
			raise
		self.contrasena = contrasena
		if guardar_contrasena and self.servidor.recordar_contrasena:
			self._guardar("contrasena", contrasena)
		sid = str(datos.get("sid", ""))
		if not sid:
			raise errores.ErrorDSM(_("El NAS no ha devuelto una sesión válida."), 119, "SYNO.API.Auth", "login")
		return DatosSesion(sid, str(datos.get("synotoken", "")), self.servidor.usuario)

	def _con_codigo(self, ruta: str, version: int, parametros: dict[str, str], reintento: bool) -> dict[str, Any]:
		if reintento or self._preguntas is None:
			raise errores.NecesitaCodigo(errores.mensaje(403, "SYNO.API.Auth"), 403, "SYNO.API.Auth", "login")
		mensaje = _("{n} pide el código de verificación en dos pasos de su aplicación de autenticación.").format(n=self.servidor.nombre)
		for intento in range(1, INTENTOS_CODIGO + 1):
			self._sonar("otp")
			respuesta = self._preguntas.codigo(self.servidor, mensaje)
			if respuesta is None:
				raise api.Cancelado(_("Conexión cancelada"))
			codigo, recordar = respuesta
			con_codigo = {k: v for k, v in parametros.items() if k != "device_id"}
			con_codigo.update(otp_code=codigo.strip(), device_name=nombre_equipo())
			if recordar:
				con_codigo["enable_device_token"] = "yes"
			try:
				datos = self._enviar(ruta, version, con_codigo)
			except errores.CodigoIncorrecto:
				quedan = INTENTOS_CODIGO - intento
				if quedan <= 0:
					raise
				mensaje = _n("El código no es correcto. Le queda {n} intento.", "El código no es correcto. Le quedan {n} intentos.",
					quedan).format(n=quedan)
				continue
			dispositivo = datos.get("device_id") or datos.get("did")
			if recordar and dispositivo:
				self._guardar("device_id", str(dispositivo))
			return datos
		raise errores.CodigoIncorrecto(errores.mensaje(404, "SYNO.API.Auth"), 404, "SYNO.API.Auth", "login")  # pragma: no cover

	def _enviar(self, ruta: str, version: int, parametros: dict[str, str]) -> dict[str, Any]:
		respuesta = self._transporte(ruta, "SYNO.API.Auth", version, "login", parametros)
		if respuesta.get("success"):
			return respuesta.get("data") or {}
		raise errores.desde_respuesta(respuesta.get("error"), "SYNO.API.Auth", "login")
