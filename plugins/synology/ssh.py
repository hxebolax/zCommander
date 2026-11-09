# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Herramientas avanzadas por SSH (diseño 2.0, 13.8; synology.md 8). Desactivadas de fábrica.

Con paramiko (parte del contrato de bibliotecas) y autenticación por clave
pública del agente de OpenSSH de Windows (o las claves de ``~/.ssh``). La
contraseña de ``sudo`` se pide CADA vez, viaja solo por la entrada estándar de
``sudo -S`` y nunca se guarda ni se registra. La huella del servidor SSH se
fija como en SFTP: se pregunta la primera vez y se avisa si cambia.

Lectura (siempre): atributos S.M.A.R.T. en bruto, registros largos de un
contenedor, ``docker stats``. Escritura (solo con cambios permitidos):
``docker compose pull`` y ``up -d`` de un proyecto y el rescate de un paquete
con ``synopkg``. ``synowebapi --exec`` es un transporte alternativo con los
mismos analizadores de respuesta y la misma lista blanca de lectura.

Las órdenes se construyen con valores validados y ``shlex.quote``: nada de lo
que escribe la persona llega sin comillas al intérprete del NAS.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import shlex
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.plugins import api

from . import errores
from .metodos_lectura import es_lectura

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.ssh")

_DISCO = re.compile(r"^(sata\d{1,2}|sd[a-z]|nvme\d+n\d+)$")
_NOMBRE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_CARPETA = re.compile(r"^/volume\d+(/[^\x00\n\r]+)+$")
ACCIONES_PAQUETE = ("start", "stop", "restart")


class EjecutorSSH(Protocol):
	def ejecutar(self, orden: str, entrada: bytes = b"", tiempo: float = 120) -> tuple[int, str, str]: ...
	def cerrar(self) -> None: ...


@dataclass(frozen=True)
class Herramienta:
	id: str
	etiqueta: str
	ayuda: str
	escritura: bool
	pide: str = ""  # «disco», «contenedor», «carpeta», «paquete» o «api»


HERRAMIENTAS: tuple[Herramienta, ...] = (
	Herramienta("smart", "Atributos S.M.A.R.T. en bruto", "smartctl -a de un disco (sata1, sata2...).", False, "disco"),
	Herramienta("registros", "Registro largo de un contenedor", "Las últimas 1000 líneas de docker logs.", False, "contenedor"),
	Herramienta("estadisticas", "Estadísticas de los contenedores", "docker stats --no-stream: procesador, memoria, red y disco.", False),
	Herramienta("compose", "Actualizar un proyecto Compose", "docker compose pull y up -d en la carpeta del proyecto.", True, "carpeta"),
	Herramienta("paquete", "Rescate de un paquete", "synopkg start, stop o restart cuando la interfaz web no responde.", True, "paquete"),
	Herramienta("webapi", "Llamar a la API web por SSH", "sudo synowebapi --exec con la misma lista blanca de lectura.", False, "api"),
)
POR_ID = {h.id: h for h in HERRAMIENTAS}


def _sudo(orden: str) -> str:
	return f"sudo -S -p '' {orden}"


def orden_smart(disco: str) -> str:
	if not _DISCO.match(disco or ""):
		raise api.NombreNoValido(_("El disco debe escribirse como sata1, sata2..."), disco)
	return _sudo(f"smartctl -a -d sat /dev/{disco}")


def orden_registros(contenedor: str, lineas: int = 1000) -> str:
	if not _NOMBRE.match(contenedor or ""):
		raise api.NombreNoValido(_("Nombre de contenedor no válido."), contenedor)
	return _sudo(f"docker logs --tail {int(lineas)} {shlex.quote(contenedor)}")


def orden_estadisticas() -> str:
	return _sudo("docker stats --no-stream")


def orden_compose(carpeta: str) -> str:
	carpeta = (carpeta or "").rstrip("/")
	if not _CARPETA.match(carpeta) or ".." in carpeta.split("/"):
		raise api.NombreNoValido(_("La carpeta del proyecto debe ser una ruta del NAS como /volume1/docker/multimedia."), carpeta)
	archivo = shlex.quote(f"{carpeta}/compose.yaml")
	interior = f"docker compose -f {archivo} pull && docker compose -f {archivo} up -d"
	return _sudo(f"sh -c {shlex.quote(interior)}")


def orden_paquete(paquete: str, accion: str) -> str:
	if not _NOMBRE.match(paquete or "") or accion not in ACCIONES_PAQUETE:
		raise api.NombreNoValido(_("Paquete o acción no válidos."), paquete)
	return _sudo(f"synopkg {accion} {shlex.quote(paquete)}")


def orden_webapi(api_nombre: str, metodo: str, version: int, parametros: Mapping[str, Any] | None = None) -> str:
	if not re.match(r"^SYNO(\.[A-Za-z0-9_]+)+$", api_nombre or "") or not re.match(r"^[a-z_]+$", metodo or ""):
		raise api.NombreNoValido(_("API o método no válidos."), api_nombre)
	partes = [f"api={api_nombre}", f"method={metodo}", f"version={int(version)}"]
	for clave, valor in (parametros or {}).items():
		if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", clave):
			raise api.NombreNoValido(_("Parámetro no válido: {p}").format(p=clave), clave)
		texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
		partes.append(shlex.quote(f"{clave}={texto}"))
	return _sudo("synowebapi --exec " + " ".join(partes))


class HerramientasSSH:
	"""Ejecuta las herramientas con un ``EjecutorSSH`` (paramiko en la aplicación; uno falso en las pruebas)."""

	def __init__(self, ejecutor: EjecutorSSH, solo_lectura: Callable[[], bool], nombre_nas: str = "") -> None:
		self._ejecutor = ejecutor
		self._solo_lectura = solo_lectura
		self._nombre = nombre_nas

	def _correr(self, orden: str, contrasena_sudo: str, escritura: bool, tiempo: float = 300) -> str:
		if escritura and self._solo_lectura():
			raise errores.solo_lectura(self._nombre)
		log.info("SSH: %s", orden.split(" -p '' ", 1)[-1][:200])
		codigo, salida, error = self._ejecutor.ejecutar(orden, (contrasena_sudo + "\n").encode("utf-8"), tiempo)
		if codigo != 0:
			detalle = (error or salida).strip().splitlines()
			motivo = detalle[-1] if detalle else _("sin detalle")
			if "incorrect password" in (error or "").lower() or "sorry, try again" in (error or "").lower():
				motivo = _("la contraseña de sudo no es correcta")
			raise errores.ErrorDSM(_("La orden ha fallado en el NAS (código {c}): {m}").format(c=codigo, m=motivo), codigo)
		return salida

	def smart(self, disco: str, sudo: str) -> str:
		return self._correr(orden_smart(disco), sudo, False)

	def registros(self, contenedor: str, sudo: str, lineas: int = 1000) -> str:
		return self._correr(orden_registros(contenedor, lineas), sudo, False)

	def estadisticas(self, sudo: str) -> str:
		return self._correr(orden_estadisticas(), sudo, False)

	def compose(self, carpeta: str, sudo: str) -> str:
		return self._correr(orden_compose(carpeta), sudo, True, tiempo=1800)

	def paquete(self, paquete: str, accion: str, sudo: str) -> str:
		return self._correr(orden_paquete(paquete, accion), sudo, True)

	def webapi(self, api_nombre: str, metodo: str, version: int, sudo: str, parametros: Mapping[str, Any] | None = None) -> Any:
		escritura = not es_lectura(api_nombre, metodo, parametros)
		salida = self._correr(orden_webapi(api_nombre, metodo, version, parametros), sudo, escritura)
		try:
			datos = json.loads(salida[salida.find("{"):]) if "{" in salida else {}
		except ValueError as error:
			raise errores.ErrorConexion(_("synowebapi no ha devuelto JSON."), 0, api_nombre, metodo) from error
		if not datos.get("success", False):
			raise errores.desde_respuesta(datos.get("error"), api_nombre, metodo)
		return datos.get("data", {})


# ── Paramiko ─────────────────────────────────────────────────────────────────


def huella_ssh(clave: Any) -> str:
	"""«SHA256:...» como la muestra OpenSSH."""
	import hashlib

	return "SHA256:" + base64.b64encode(hashlib.sha256(clave.asbytes()).digest()).decode().rstrip("=")


class EjecutorParamiko:
	"""Conexión SSH con paramiko: clave del agente de Windows o de ``~/.ssh``; huella fijada en ``known_hosts`` del complemento."""

	def __init__(self, host: str, puerto: int, usuario: str, known_hosts: Path, preguntar_huella: Callable[[str, str], bool],
			tiempo: float = 15) -> None:
		import paramiko

		self._paramiko = paramiko
		self.host, self.puerto, self.usuario = host, int(puerto), usuario
		self._known_hosts = Path(known_hosts)
		self._preguntar = preguntar_huella
		self._cliente = paramiko.SSHClient()
		if self._known_hosts.is_file():
			self._cliente.load_host_keys(str(self._known_hosts))
		ejecutor = self

		class _Politica(paramiko.MissingHostKeyPolicy):
			def missing_host_key(self, cliente: Any, nombre: str, clave: Any) -> None:  # noqa: D102 - API de paramiko
				if not ejecutor._preguntar(huella_ssh(clave), ""):
					raise errores.HuellaRechazada(_("No se ha aceptado la clave del servidor SSH."), 0)
				cliente.get_host_keys().add(nombre, clave.get_name(), clave)
				ejecutor._known_hosts.parent.mkdir(parents=True, exist_ok=True)
				cliente.save_host_keys(str(ejecutor._known_hosts))

		self._cliente.set_missing_host_key_policy(_Politica())
		try:
			self._cliente.connect(host, self.puerto, usuario, timeout=tiempo, allow_agent=True, look_for_keys=True, auth_timeout=tiempo)
		except paramiko.BadHostKeyException as error:
			self._cliente.close()
			if self._preguntar(huella_ssh(error.key), huella_ssh(error.expected_key)):
				raise errores.ErrorConexion(_("La clave SSH del NAS ha cambiado: bórrela de la lista de claves conocidas y vuelva a conectar."),
					0) from error
			raise errores.HuellaRechazada(_("La clave del servidor SSH ha cambiado y no se ha aceptado."), 0) from error
		except paramiko.AuthenticationException as error:
			self._cliente.close()
			raise errores.ErrorAutenticacion(_("El NAS no ha aceptado ninguna clave SSH. Añada su clave pública al agente de OpenSSH de "
				"Windows y a ~/.ssh/authorized_keys de su cuenta en el NAS."), 0) from error
		except (paramiko.SSHException, OSError) as error:
			self._cliente.close()
			raise errores.ErrorConexion(_("No se puede conectar por SSH con {h}: {e}").format(h=host, e=error), 0) from error

	def ejecutar(self, orden: str, entrada: bytes = b"", tiempo: float = 120) -> tuple[int, str, str]:
		canal_entrada, salida, error = self._cliente.exec_command(orden, timeout=tiempo)
		if entrada:
			canal_entrada.write(entrada)
			canal_entrada.flush()
		canal_entrada.channel.shutdown_write()
		texto = salida.read().decode("utf-8", "replace")
		texto_error = error.read().decode("utf-8", "replace")
		return salida.channel.recv_exit_status(), texto, texto_error

	def cerrar(self) -> None:
		self._cliente.close()
