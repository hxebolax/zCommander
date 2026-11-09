# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Base: ``SYNO.API.Info``, ``SYNO.API.Auth`` (con 2FA y ``device_id``), ``SYNO.Entry.Request`` y la confirmación de contraseña."""

from __future__ import annotations

import secrets
from typing import Any

from ..comun import ErrorSim, Peticion
from ..estado import SesionSim


def info_query(pet: Peticion) -> dict[str, Any]:
	consulta = pet.texto("query", "all") or "all"
	catalogo = pet.estado.catalogo
	if consulta == "all":
		return dict(catalogo)
	pedidas = [p.strip() for p in consulta.split(",") if p.strip()]
	return {nombre: info for nombre, info in catalogo.items() if any(nombre == p or (p.endswith(".") and nombre.startswith(p))
		for p in pedidas)}


def login(pet: Peticion) -> dict[str, Any]:
	estado, fallos = pet.estado, pet.simulador.fallos
	if estado.fallos_login.get(pet.ip, 0) >= max(1, fallos.bloquear_tras):
		raise ErrorSim(407)
	cuenta_nombre = pet.texto("account")
	cuenta = estado.cuentas.get(cuenta_nombre)
	if cuenta is None or pet.texto("passwd") != cuenta["contrasena"]:
		estado.fallos_login[pet.ip] = estado.fallos_login.get(pet.ip, 0) + 1
		raise ErrorSim(407 if estado.fallos_login[pet.ip] >= max(1, fallos.bloquear_tras) else 400)
	respuesta: dict[str, Any] = {"is_portal_port": False, "account": cuenta_nombre}
	if cuenta.get("otp"):
		dispositivo = pet.texto("device_id")
		if not (dispositivo and estado.dispositivos.get(dispositivo) == cuenta_nombre):
			codigo = pet.texto("otp_code")
			if not codigo:
				raise ErrorSim(403, {"types": [{"type": "otp"}]})
			if codigo != str(cuenta["otp"]):
				raise ErrorSim(404)
			if pet.texto("enable_device_token") == "yes":
				nuevo = secrets.token_urlsafe(24)
				estado.dispositivos[nuevo] = cuenta_nombre
				respuesta["device_id" if pet.version >= 7 else "did"] = nuevo
	estado.fallos_login[pet.ip] = 0
	sesion = SesionSim(secrets.token_urlsafe(32), secrets.token_urlsafe(10), cuenta_nombre, bool(cuenta.get("administrador")), pet.ip)
	estado.sesiones[sesion.sid] = sesion
	respuesta["sid"] = sesion.sid
	if pet.texto("enable_syno_token") == "yes":
		respuesta["synotoken"] = sesion.synotoken
	return respuesta


def logout(pet: Peticion) -> dict[str, Any]:
	if pet.sesion is not None:
		pet.estado.sesiones.pop(pet.sesion.sid, None)
	return {}


def token(pet: Peticion) -> dict[str, Any]:
	return {"synotoken": pet.sesion.synotoken}


def compuesta(pet: Peticion) -> dict[str, Any]:
	peticiones = pet.lista("compound")
	if not peticiones:
		raise ErrorSim(114)
	parar = pet.booleano("stop_when_error")
	resultados: list[dict[str, Any]] = []
	hay_fallo = False
	for interna in peticiones:
		if not isinstance(interna, dict):
			raise ErrorSim(120)
		api, metodo, version = str(interna.get("api", "")), str(interna.get("method", "")), interna.get("version", 1)
		params = {k: v for k, v in interna.items() if k not in ("api", "method", "version")}
		fila: dict[str, Any] = {"api": api, "method": metodo, "version": version}
		try:
			fila.update(success=True, data=pet.simulador.ejecutar(api, version, metodo, params, pet.sesion, pet.ip, decodificados=True))
		except ErrorSim as error:
			hay_fallo = True
			fila.update(success=False, error={"code": error.codigo})
		resultados.append(fila)
		if hay_fallo and parar:
			break
	return {"has_fail": hay_fallo, "result": resultados}


def confirmar_contrasena(pet: Peticion) -> dict[str, Any]:
	cuenta = pet.estado.cuentas.get(pet.sesion.usuario, {})
	if pet.texto("password") != cuenta.get("contrasena"):
		raise ErrorSim(400)
	return {"SynoConfirmPWToken": secrets.token_urlsafe(16)}


MANEJADORES = {
	("SYNO.API.Info", "query"): info_query,
	("SYNO.API.Auth", "login"): login,
	("SYNO.API.Auth", "logout"): logout,
	("SYNO.API.Auth", "token"): token,
	("SYNO.Entry.Request", "request"): compuesta,
	("SYNO.Core.User.PasswordConfirm", "auth"): confirmar_contrasena,
}
