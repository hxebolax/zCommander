# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cliente de la API web de DSM solo con la biblioteca estándar (diseño 2.0, 13.1 y 13.2; synology.md 1, 2 y 6).

- ``http.client`` y ``ssl``; POST con todo en el cuerpo (en la URL solo
  ``api``, ``version`` y ``method``), ``_sid`` en el cuerpo y la cabecera
  ``X-SYNO-TOKEN``.
- Parámetros codificados en JSON cuando la API declara ``requestFormat: "JSON"``.
- HTTPS con la huella SHA-256 del certificado fijada: se compara al abrir CADA
  conexión, antes de enviar nada (y, por tanto, antes de las credenciales).
- Modo solo lectura: toda llamada fuera de la lista blanca de
  ``metodos_lectura.py`` se bloquea aquí, sin llegar a enviarse.
- Un único reintento de inicio de sesión ante 106, 107, 119 y 150; nunca ante 407.
- Registro sin secretos (``account``, ``passwd``, ``_sid``, ``SynoToken``,
  ``device_id``, ``otp_code``, ``passphrase``, ``unzip_password``...).

Todos los métodos bloquean: se llaman desde un hilo de trabajo, nunca desde el
de la interfaz.
"""

from __future__ import annotations

import hashlib
import http.client
import io
import ipaddress
import json
import logging
import re
import socket
import ssl
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote, urlencode

from app.plugins import api

from . import errores
from .catalogo import Catalogo
from .metodos_lectura import es_lectura
from .sesion import DatosSesion, Iniciador, Preguntas

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.cliente")

#: Parámetros que nunca aparecen en el registro (13.2; lista de Home Assistant ampliada).
SECRETOS = frozenset({"account", "passwd", "password", "_sid", "SynoToken", "device_id", "otp_code", "passphrase",
	"unzip_password", "new_password", "SynoConfirmPWToken"})
PARAMETROS_BASE = frozenset({"api", "version", "method", "_sid", "SynoToken"})
BLOQUE = 256 * 1024
USER_AGENT = "zCommander (zc.synology)"


def redactar(parametros: Mapping[str, Any]) -> dict[str, Any]:
	return {k: ("***" if k in SECRETOS else v) for k, v in parametros.items()}


def codificar_parametros(parametros: Mapping[str, Any], formato_json: bool) -> dict[str, str]:
	"""synology.md 1.2: con ``requestFormat: "JSON"``, cada valor va en JSON (``name="plex"`` → ``"\\"plex\\""``).

	Sin ese formato (``SYNO.API.Auth``), los valores van tal cual; los booleanos como
	``true``/``false`` y las listas separadas por comas.
	"""
	campos: dict[str, str] = {}
	for clave, valor in parametros.items():
		if valor is None:
			continue
		if clave in PARAMETROS_BASE:
			campos[clave] = str(valor)
		elif formato_json:
			campos[clave] = json.dumps(valor, ensure_ascii=False)
		elif isinstance(valor, bool):
			campos[clave] = "true" if valor else "false"
		elif isinstance(valor, (list, tuple)):
			campos[clave] = ",".join(str(v) for v in valor)
		else:
			campos[clave] = str(valor)
	return campos


def huella_de(der: bytes) -> str:
	"""Huella SHA-256 de un certificado en DER: «SHA256:AB12CD...» (64 cifras hexadecimales en mayúsculas)."""
	return "SHA256:" + hashlib.sha256(der).hexdigest().upper()


def huella_legible(huella: str) -> str:
	"""Para leerla con el lector de pantalla: grupos de 4 cifras separados por espacios (13.2)."""
	cifras = huella.split(":", 1)[-1].replace(":", "")
	return " ".join(cifras[i:i + 4] for i in range(0, len(cifras), 4))


def _es_ip(host: str) -> bool:
	try:
		ipaddress.ip_address(host.strip("[]"))
	except ValueError:
		return False
	return True


# ── Versión de DSM y aviso de seguridad (synology.md 0.1) ────────────────────

_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?-(\d+)(?:\s+Update\s+(\d+))?", re.IGNORECASE)


def partes_version(texto: str) -> tuple[int, int, int, int, int] | None:
	encontrada = _VERSION.search(texto or "")
	if encontrada is None:
		return None
	mayor, menor, micro, compilacion, nano = encontrada.groups()
	return int(mayor), int(menor), int(micro or 0), int(compilacion), int(nano or 0)


def aviso_seguridad(version_texto: str) -> str:
	"""Aviso del boletín Synology-SA-26:06 (CVE-2026-40530) si el DSM 7.3 es anterior a 7.3.2-86009 Update 2."""
	partes = partes_version(version_texto)
	if partes is None or partes[:2] != (7, 3):
		return ""
	if partes < (7, 3, 2, 86009, 2):
		return _("Este NAS tiene {v}, sin la corrección de seguridad del boletín Synology-SA-26:06 (CVE-2026-40530). "
			"Actualice DSM a 7.3.2-86009 Update 2 o posterior cuanto antes.").format(v=version_texto)
	return ""


@dataclass
class InfoNAS:
	"""Lo que se sabe del NAS al conectar."""

	modelo: str = ""
	version: str = ""
	nombre_host: str = ""
	serie: str = ""
	ram_mb: int = 0
	temperatura: int = 0
	encendido_s: int = 0
	administrador: bool = True
	cuenta: str = ""
	aviso: str = ""
	extra: dict[str, Any] = field(default_factory=dict)

	def resumen(self) -> str:
		partes = [p for p in (self.modelo, self.version) if p]
		return ", ".join(partes)


# ── Flujos de descarga y subida ──────────────────────────────────────────────


class FlujoDescarga(io.RawIOBase):
	"""Lectura en flujo de ``SYNO.FileStation.Download`` con progreso y cancelación."""

	def __init__(self, conexion: http.client.HTTPConnection, respuesta: http.client.HTTPResponse, tamano: int,
			progreso: Callable[[int, int], None] | None, cancelacion: Any) -> None:
		super().__init__()
		self._conexion = conexion
		self._respuesta = respuesta
		self.tamano = tamano
		self._progreso = progreso
		self._cancelacion = cancelacion
		self.leidos = 0

	def readable(self) -> bool:
		return True

	def readinto(self, destino: Any) -> int:
		api.comprobar(self._cancelacion)
		try:
			cantidad = self._respuesta.readinto(destino)
		except (OSError, http.client.HTTPException) as error:
			raise errores.ErrorConexion(_("Se ha perdido la conexión con el NAS durante la descarga."), 0) from error
		self.leidos += cantidad or 0
		if self._progreso is not None and cantidad:
			self._progreso(self.leidos, self.tamano)
		return cantidad or 0

	def close(self) -> None:
		if not self.closed:
			try:
				self._respuesta.close()
				self._conexion.close()
			finally:
				super().close()


class SubidaEnFlujo(io.RawIOBase):
	"""Escritura que sube a ``SYNO.FileStation.Upload`` mientras se escribe (multipart con el archivo al final).

	Con el tamaño conocido, los bytes salen hacia el NAS según llegan; sin él, se
	guardan en un temporal de la caché del complemento y se suben al cerrar.
	"""

	def __init__(self, cliente: ClienteDSM, carpeta: str, nombre: str, tamano: int, sobrescribir: bool,
			progreso: Callable[[int, int], None] | None = None, cancelacion: Any = None, mtime: float | None = None) -> None:
		super().__init__()
		self._cliente = cliente
		self.carpeta = carpeta
		self.nombre = nombre
		self.tamano = int(tamano)
		self._sobrescribir = sobrescribir
		self._progreso = progreso
		self._cancelacion = cancelacion
		self._mtime = mtime
		self._conexion: http.client.HTTPConnection | None = None
		self._epilogo = b""
		self._escritos = 0
		self._temporal: Path | None = None
		self._archivo_temporal: BinaryIO | None = None
		self._error: BaseException | None = None
		self.respuesta: dict[str, Any] = {}

	def writable(self) -> bool:
		return True

	def _abrir(self) -> None:
		if self.tamano < 0:
			self._temporal = self._cliente.ruta_temporal(self.nombre)
			self._archivo_temporal = self._temporal.open("wb")
			return
		self._conexion, self._epilogo = self._cliente._empezar_subida(self.carpeta, self.nombre, self.tamano, self._sobrescribir,
			self._mtime)

	def write(self, datos: Any) -> int:
		if self._conexion is None and self._archivo_temporal is None:
			self._abrir()
		vista = memoryview(datos).cast("B")
		api.comprobar(self._cancelacion)
		if self._archivo_temporal is not None:
			self._archivo_temporal.write(vista)
			return len(vista)
		if self._escritos + len(vista) > self.tamano:
			self._abortar()
			raise errores.ErrorDSM(errores.mensaje(1800, "SYNO.FileStation.Upload"), 1800, "SYNO.FileStation.Upload", "upload")
		try:
			self._conexion.send(vista)
		except (OSError, http.client.HTTPException) as error:
			self._abortar()
			raise errores.ErrorConexion(_("Se ha perdido la conexión con el NAS durante la subida."), 0) from error
		self._escritos += len(vista)
		if self._progreso is not None:
			self._progreso(self._escritos, self.tamano)
		return len(vista)

	def _abortar(self) -> None:
		if self._conexion is not None:
			self._conexion.close()
			self._conexion = None

	def cancelar(self) -> None:
		"""Corta la subida sin terminarla: el NAS la descarta (no queda un archivo a medias con el nombre final)."""
		self._abortar()
		if self._archivo_temporal is not None:
			self._archivo_temporal.close()
			self._archivo_temporal = None
		if self._temporal is not None:
			self._temporal.unlink(missing_ok=True)
		super().close()

	def close(self) -> None:
		if self.closed:
			return
		try:
			if self._archivo_temporal is not None:
				self._archivo_temporal.close()
				self._archivo_temporal = None
				try:
					with self._temporal.open("rb") as origen:
						tamano = self._temporal.stat().st_size
						self.respuesta = self._cliente.subir(self.carpeta, self.nombre, origen, tamano, self._sobrescribir,
							self._progreso, self._cancelacion, self._mtime)
				finally:
					self._temporal.unlink(missing_ok=True)
				return
			if self._conexion is None:
				if self.tamano == 0 or self._escritos == 0:
					self._conexion, self._epilogo = self._cliente._empezar_subida(self.carpeta, self.nombre, self.tamano,
						self._sobrescribir, self._mtime)
				else:
					return
			if self._escritos != self.tamano:
				self._abortar()
				raise errores.ErrorDSM(errores.mensaje(1800, "SYNO.FileStation.Upload"), 1800, "SYNO.FileStation.Upload", "upload")
			conexion, self._conexion = self._conexion, None
			self.respuesta = self._cliente._terminar_subida(conexion, self._epilogo)
		finally:
			super().close()


# ── Cliente ──────────────────────────────────────────────────────────────────


class ClienteDSM:
	"""Una conexión lógica con un NAS: catálogo, sesión y llamadas."""

	def __init__(self, servidor: Any, secretos: Any = None, preguntas: Preguntas | None = None, *, tiempo_conexion: float = 10,
			tiempo_peticion: float = 30, sonar: Callable[[str], None] | None = None,
			al_guardar_servidor: Callable[[Any], None] | None = None, carpeta_temporal: Path | None = None,
			registro_detallado: bool = False, contrasena: str | None = None) -> None:
		self.servidor = servidor
		self.preguntas = preguntas
		self.tiempo_conexion = float(tiempo_conexion)
		self.tiempo_peticion = float(tiempo_peticion)
		self.registro_detallado = registro_detallado
		self._sonar = sonar or (lambda _evento: None)
		self._al_guardar_servidor = al_guardar_servidor
		self._carpeta_temporal = carpeta_temporal
		self._iniciador = Iniciador(servidor, self._transporte, preguntas, secretos, self._sonar)
		if contrasena is not None:
			self._iniciador.contrasena = contrasena
		self._candado = threading.RLock()
		self._sesion: DatosSesion | None = None
		self._huella_sesion = ""
		self._escritura_sesion = False
		self.catalogo: Catalogo | None = None
		self.info: InfoNAS | None = None

	# ── Estado ───────────────────────────────────────────────────────────────

	@property
	def conectado(self) -> bool:
		return self._sesion is not None

	@property
	def solo_lectura(self) -> bool:
		return bool(self.servidor.solo_lectura) and not self._escritura_sesion

	def permitir_cambios(self, permitir: bool, persistente: bool = False) -> None:
		"""Activa o desactiva el modo de escritura (13.6); ``persistente`` lo guarda en el servidor."""
		with self._candado:
			if not permitir:
				self._escritura_sesion = False
				self.servidor.solo_lectura = True
			elif persistente:
				self.servidor.solo_lectura = False
				self._escritura_sesion = False
			else:
				self._escritura_sesion = True
		if self._al_guardar_servidor is not None and (persistente or not permitir):
			self._al_guardar_servidor(self.servidor)

	def disponible(self, api_nombre: str) -> bool:
		return self.catalogo is not None and self.catalogo.disponible(api_nombre)[0]

	def ruta_temporal(self, nombre: str) -> Path:
		if self._carpeta_temporal is None:
			raise errores.ErrorDSM(_("No hay carpeta temporal para preparar la subida."), 0)
		carpeta = Path(self._carpeta_temporal)
		carpeta.mkdir(parents=True, exist_ok=True)
		return carpeta / f"subida-{uuid.uuid4().hex}.parcial"

	# ── Conexión de red y TLS ────────────────────────────────────────────────

	def _contexto_verificado(self) -> ssl.SSLContext:
		if self.servidor.ca_propia:
			contexto = ssl.create_default_context(cafile=self.servidor.ca_propia)
		else:
			contexto = ssl.create_default_context()
		contexto.check_hostname = not _es_ip(self.servidor.host)
		return contexto

	@staticmethod
	def _contexto_sin_verificar() -> ssl.SSLContext:
		contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
		contexto.check_hostname = False
		contexto.verify_mode = ssl.CERT_NONE
		return contexto

	def _fijada(self) -> str:
		return self.servidor.huella or self._huella_sesion

	def _conexion(self) -> http.client.HTTPConnection:
		"""Abre la conexión y, con HTTPS, comprueba el certificado ANTES de devolverla (no se ha enviado nada)."""
		host, puerto = self.servidor.host, int(self.servidor.puerto)
		if not self.servidor.https:
			conexion: http.client.HTTPConnection = http.client.HTTPConnection(host, puerto, timeout=self.tiempo_conexion)
			self._conectar(conexion)
			return conexion
		fijada = self._fijada()
		if not fijada:
			conexion = http.client.HTTPSConnection(host, puerto, timeout=self.tiempo_conexion, context=self._contexto_verificado())
			try:
				self._conectar(conexion)
				return conexion
			except errores.ErrorConexion as error:
				if not isinstance(error.__cause__, ssl.SSLCertVerificationError):
					raise
				log.info("El certificado de %s no es de una autoridad conocida: se pregunta por su huella", self.servidor.nombre)
			fijada = self._decidir_huella(self._leer_huella(), "")
		conexion = http.client.HTTPSConnection(host, puerto, timeout=self.tiempo_conexion, context=self._contexto_sin_verificar())
		self._conectar(conexion)
		huella = huella_de(conexion.sock.getpeercert(binary_form=True) or b"")
		if huella != fijada:
			conexion.close()
			self._decidir_huella(huella, fijada)
			return self._conexion()
		return conexion

	def _conectar(self, conexion: http.client.HTTPConnection) -> None:
		try:
			conexion.connect()
		except ssl.SSLCertVerificationError as error:
			conexion.close()
			raise errores.ErrorConexion(_("El certificado del NAS no es de confianza."), 0) from error
		except ssl.SSLError as error:
			conexion.close()
			raise errores.ErrorConexion(_("No se ha podido establecer una conexión segura con el NAS: {e}").format(e=error.reason or error),
				0) from error
		except TimeoutError as error:
			conexion.close()
			raise errores.ErrorConexion(_("El NAS {n} no responde (tiempo agotado al conectar).").format(n=self.servidor.nombre), 0) from error
		except ConnectionRefusedError as error:
			conexion.close()
			raise errores.ErrorConexion(_("El NAS {n} rechaza la conexión en el puerto {p}.").format(n=self.servidor.nombre,
				p=self.servidor.puerto), 0) from error
		except OSError as error:
			conexion.close()
			raise errores.ErrorConexion(_("No se puede conectar con el NAS {n}: {e}").format(n=self.servidor.nombre,
				e=error.strerror or error), 0) from error
		if conexion.sock is not None:
			conexion.sock.settimeout(self.tiempo_peticion)

	def _leer_huella(self) -> str:
		conexion = http.client.HTTPSConnection(self.servidor.host, int(self.servidor.puerto), timeout=self.tiempo_conexion,
			context=self._contexto_sin_verificar())
		try:
			self._conectar(conexion)
			return huella_de(conexion.sock.getpeercert(binary_form=True) or b"")
		finally:
			conexion.close()

	def _decidir_huella(self, huella: str, anterior: str) -> str:
		"""Pregunta por un certificado nuevo o cambiado. Devuelve la huella aceptada o lanza ``HuellaRechazada``."""
		if anterior:
			self._sonar("red.huella")
			log.warning("El certificado del NAS %s ha cambiado", self.servidor.nombre)
		decision = self.preguntas.huella(self.servidor, huella, anterior) if self.preguntas is not None else "cancelar"
		if decision == "recordar":
			self.servidor.huella = huella
			self._huella_sesion = ""
			if self._al_guardar_servidor is not None:
				self._al_guardar_servidor(self.servidor)
			return huella
		if decision == "sesion":
			self._huella_sesion = huella
			return huella
		if anterior:
			raise errores.HuellaRechazada(_("Conexión cancelada: el certificado del NAS {n} ha cambiado y no se ha aceptado.").format(
				n=self.servidor.nombre), 0)
		raise errores.HuellaRechazada(_("Conexión cancelada: no se ha aceptado el certificado del NAS {n}.").format(
			n=self.servidor.nombre), 0)

	# ── Transporte ───────────────────────────────────────────────────────────

	def _cabeceras(self, tipo: str = "application/x-www-form-urlencoded; charset=UTF-8", token: str = "") -> dict[str, str]:
		cabeceras = {"Content-Type": tipo, "User-Agent": USER_AGENT, "Accept": "application/json"}
		token = token or (self._sesion.synotoken if self._sesion is not None else "")
		if token:
			cabeceras["X-SYNO-TOKEN"] = token
		return cabeceras

	@staticmethod
	def _url(ruta: str, api_nombre: str, version: int, metodo: str) -> str:
		return f"/webapi/{ruta}?api={quote(api_nombre)}&version={int(version)}&method={quote(metodo)}"

	def _transporte(self, ruta: str, api_nombre: str, version: int, metodo: str, campos: dict[str, str], token: str = "") -> dict[str, Any]:
		"""Una petición POST; devuelve el JSON. Nunca registra los campos de ``SYNO.API.Auth``."""
		conexion = self._conexion()
		try:
			conexion.request("POST", self._url(ruta, api_nombre, version, metodo), urlencode(campos), self._cabeceras(token=token))
			respuesta = conexion.getresponse()
			cuerpo = respuesta.read()
		except TimeoutError as error:
			raise errores.ErrorConexion(_("El NAS no ha respondido a tiempo."), 0, api_nombre, metodo) from error
		except http.client.IncompleteRead as error:
			raise errores.ErrorConexion(_("La respuesta del NAS llegó incompleta o dañada."), 0, api_nombre, metodo) from error
		except (OSError, http.client.HTTPException) as error:
			raise errores.ErrorConexion(_("Se ha perdido la conexión con el NAS {n}.").format(n=self.servidor.nombre), 0,
				api_nombre, metodo) from error
		finally:
			conexion.close()
		return self._json(respuesta.status, cuerpo, api_nombre, metodo)

	def _json(self, estado: int, cuerpo: bytes, api_nombre: str, metodo: str) -> dict[str, Any]:
		if estado != 200:
			raise errores.ErrorConexion(_("El NAS ha respondido con el error HTTP {c}.").format(c=estado), 0, api_nombre, metodo)
		try:
			datos = json.loads(cuerpo.decode("utf-8"))
		except (UnicodeDecodeError, ValueError) as error:
			raise errores.ErrorConexion(_("La respuesta del NAS llegó incompleta o dañada."), 0, api_nombre, metodo) from error
		if not isinstance(datos, dict):
			raise errores.ErrorConexion(_("El NAS ha devuelto una respuesta inesperada."), 0, api_nombre, metodo)
		return datos

	# ── Conectar y desconectar ───────────────────────────────────────────────

	def conectar(self, cancelacion: Any = None) -> InfoNAS:
		"""Catálogo, inicio de sesión e información básica. Lanza ``ErrorArchivos`` con el motivo en español."""
		if not self.servidor.https and not self.servidor.es_local:
			raise errores.AccesoDSM(_("zCommander no envía la contraseña por HTTP. Active HTTPS en la conexión con {n}.").format(
				n=self.servidor.nombre), 0)
		api.comprobar(cancelacion)
		respuesta = self._transporte("entry.cgi", "SYNO.API.Info", 1, "query", {"query": "all"})
		if not respuesta.get("success"):
			raise errores.desde_respuesta(respuesta.get("error"), "SYNO.API.Info", "query")
		self.catalogo = Catalogo(respuesta.get("data") or {})
		api.comprobar(cancelacion)
		with self._candado:
			self._iniciar_sesion()
		self.info = self._leer_info()
		log.info("Conectado con el NAS %s (%s)", self.servidor.nombre, self.info.resumen())
		return self.info

	def _iniciar_sesion(self, reintento: bool = False) -> None:
		info = self.catalogo.info("SYNO.API.Auth") if self.catalogo is not None else None
		ruta = info.ruta if info is not None else "entry.cgi"
		version = self.catalogo.version("SYNO.API.Auth") if self.catalogo is not None else 7
		self._sesion = None
		self._sesion = self._iniciador.iniciar(ruta, version, reintento)

	def _leer_info(self) -> InfoNAS:
		info = InfoNAS(cuenta=self.servidor.usuario)
		try:
			datos = self.llamar("SYNO.DSM.Info", "getinfo")
			info.modelo = str(datos.get("model", ""))
			info.version = str(datos.get("version_string", ""))
			info.serie = str(datos.get("serial", ""))
			info.ram_mb = int(datos.get("ram", 0) or 0)
			info.temperatura = int(datos.get("temperature", 0) or 0)
			info.encendido_s = int(datos.get("uptime", 0) or 0)
		except errores.FuncionAusente:
			log.info("El NAS %s no tiene SYNO.DSM.Info", self.servidor.nombre)
		try:
			sistema = self.llamar("SYNO.Core.System", "info")
			info.modelo = info.modelo or str(sistema.get("model", ""))
			info.version = info.version or str(sistema.get("firmware_ver", ""))
			info.extra["sistema"] = sistema
		except errores.SinPermiso:
			info.administrador = False
		except errores.FuncionAusente:
			log.info("El NAS %s no tiene SYNO.Core.System", self.servidor.nombre)
		try:
			red = self.llamar("SYNO.DSM.Network", "list")
			info.nombre_host = str(red.get("hostname", ""))
		except (errores.SinPermiso, errores.FuncionAusente):
			info.nombre_host = ""
		info.aviso = aviso_seguridad(info.version)
		return info

	def desconectar(self) -> None:
		"""``logout`` (también al cerrar zCommander). No falla si el NAS ya no responde."""
		with self._candado:
			sesion, self._sesion = self._sesion, None
			self._iniciador.contrasena = None
			self._escritura_sesion = False
		if sesion is None or self.catalogo is None:
			return
		try:
			info = self.catalogo.info("SYNO.API.Auth")
			self._transporte(info.ruta if info else "entry.cgi", "SYNO.API.Auth", self.catalogo.version("SYNO.API.Auth"), "logout",
				{"session": "webui", "_sid": sesion.sid}, token=sesion.synotoken)
		except api.ErrorArchivos as error:
			log.info("No se pudo cerrar la sesión con %s: %s", self.servidor.nombre, error.mensaje)

	# ── Llamadas ─────────────────────────────────────────────────────────────

	def comprobar_escritura(self, api_nombre: str, metodo: str, parametros: Mapping[str, Any] | None = None) -> None:
		"""Lanza el bloqueo de solo lectura si la llamada no es de lectura (13.1). No envía nada."""
		if self.solo_lectura and not es_lectura(api_nombre, metodo, parametros):
			log.info("Bloqueado en el cliente (solo lectura): %s %s", api_nombre, metodo)
			raise errores.solo_lectura(self.servidor.nombre, api_nombre, metodo)

	def llamar(self, api_nombre: str, metodo: str, version: int | None = None, parametros: Mapping[str, Any] | None = None,
			**mas: Any) -> Any:
		"""Llama a ``api_nombre.metodo`` y devuelve ``data``. Lanza ``ErrorArchivos`` (familia de ``errores``)."""
		todos = dict(parametros or {})
		todos.update(mas)
		if self.catalogo is None:
			raise errores.ErrorSesion(_("No hay conexión con el NAS."), 119, api_nombre, metodo)
		info = self.catalogo.info(api_nombre)
		if info is None:
			raise errores.FuncionAusente(_("{m}.").format(m=self.catalogo.disponible(api_nombre)[1]), 102, api_nombre, metodo)
		version = self.catalogo.version(api_nombre, version)
		self.comprobar_escritura(api_nombre, metodo, todos)
		campos = codificar_parametros(todos, info.json)
		if self.registro_detallado:
			log.info("%s %s v%s %s", api_nombre, metodo, version, redactar(todos))
		else:
			log.debug("%s %s v%s", api_nombre, metodo, version)
		for intento in (1, 2):
			with self._candado:
				if self._sesion is None:
					self._iniciar_sesion(reintento=True)
				sid = self._sesion.sid
			respuesta = self._transporte(info.ruta, api_nombre, version, metodo, dict(campos, _sid=sid))
			if respuesta.get("success"):
				return respuesta.get("data", {}) if respuesta.get("data") is not None else {}
			error = errores.desde_respuesta(respuesta.get("error"), api_nombre, metodo)
			if isinstance(error, errores.ErrorSesion) and intento == 1:
				log.info("Sesión con %s no válida (%s): se vuelve a iniciar una vez", self.servidor.nombre, error.codigo)
				with self._candado:
					if self._sesion is not None and self._sesion.sid == sid:
						self._sesion = None
				continue
			raise error
		raise errores.ErrorSesion(errores.mensaje(119), 119, api_nombre, metodo)  # pragma: no cover

	def llamar_compuesta(self, peticiones: list[dict[str, Any]], modo: str = "sequential") -> list[dict[str, Any]]:
		"""Varias llamadas en una (``SYNO.Entry.Request``). Las que el NAS no tiene se devuelven con ``success: false`` y 102."""
		completas: list[dict[str, Any]] = []
		resultado_ausentes: dict[int, dict[str, Any]] = {}
		for indice, peticion in enumerate(peticiones):
			nombre = str(peticion["api"])
			if self.catalogo is None or not self.catalogo.disponible(nombre)[0]:
				resultado_ausentes[indice] = {"api": nombre, "method": peticion.get("method"), "success": False, "error": {"code": 102}}
				continue
			fila = dict(peticion)
			fila["version"] = self.catalogo.version(nombre, peticion.get("version"))
			completas.append(fila)
		datos = self.llamar("SYNO.Entry.Request", "request", compound=completas, mode=modo, stop_when_error=False) if completas else {}
		recibidos = list(datos.get("result", [])) if isinstance(datos, dict) else []
		salida: list[dict[str, Any]] = []
		for indice in range(len(peticiones)):
			if indice in resultado_ausentes:
				salida.append(resultado_ausentes[indice])
			else:
				salida.append(recibidos.pop(0) if recibidos else {"success": False, "error": {"code": 100}})
		return salida

	def confirmar_contrasena(self) -> str:
		"""``SYNO.Core.User.PasswordConfirm``: pide la contraseña con las preguntas y devuelve el ``SynoConfirmPWToken``."""
		if self.preguntas is None:
			raise api.Cancelado()
		contrasena = self.preguntas.contrasena_dsm(self.servidor, _("DSM pide otra vez la contraseña de {u} para este cambio.").format(
			u=self.servidor.usuario))
		if not contrasena:
			raise api.Cancelado()
		datos = self.llamar("SYNO.Core.User.PasswordConfirm", "auth", password=contrasena)
		return str(datos.get("SynoConfirmPWToken", ""))

	# ── Tareas en segundo plano (start → taskid → status → stop) ────────────

	def tarea_fondo(self, api_nombre: str, parametros_start: Mapping[str, Any], progreso: Callable[[int, int], None] | None = None,
			cancelacion: Any = None, intervalo: float = 0.4, metodo_estado: str = "status") -> dict[str, Any]:
		datos = self.llamar(api_nombre, "start", parametros=parametros_start)
		taskid = str(datos.get("taskid", ""))
		if not taskid:
			raise errores.ErrorDSM(_("El NAS no ha devuelto la tarea."), 0, api_nombre, "start")
		try:
			while True:
				api.comprobar(cancelacion)
				estado = self.llamar(api_nombre, metodo_estado, taskid=taskid)
				if progreso is not None:
					total = int(estado.get("total", 0) or 0)
					hechos = int(estado.get("processed_size", 0) or 0)
					if total <= 0:
						total, hechos = 1000, int(float(estado.get("progress", 0) or 0) * 1000)
					progreso(max(0, hechos), max(1, total))
				if estado.get("finished"):
					estado["taskid"] = taskid
					return estado
				_esperar(cancelacion, intervalo)
		except api.Cancelado:
			self._parar_tarea(api_nombre, taskid)
			raise

	def _parar_tarea(self, api_nombre: str, taskid: str) -> None:
		try:
			if self.solo_lectura and not es_lectura(api_nombre, "stop"):
				return
			self.llamar(api_nombre, "stop", taskid=taskid)
		except api.ErrorArchivos as error:
			log.info("No se pudo parar la tarea %s de %s: %s", taskid, api_nombre, error.mensaje)

	# ── Subir y descargar ────────────────────────────────────────────────────

	def _version_subida(self) -> int:
		return self.catalogo.version("SYNO.FileStation.Upload")

	def _empezar_subida(self, carpeta: str, nombre: str, tamano: int, sobrescribir: bool,
			mtime: float | None) -> tuple[http.client.HTTPConnection, bytes]:
		"""Envía las cabeceras y la parte inicial del multipart; devuelve la conexión y el final que falta."""
		self.comprobar_escritura("SYNO.FileStation.Upload", "upload")
		version = self._version_subida()
		info = self.catalogo.info("SYNO.FileStation.Upload")
		with self._candado:
			if self._sesion is None:
				self._iniciar_sesion(reintento=True)
			sid = self._sesion.sid
		valor_sobrescribir = ("overwrite" if sobrescribir else "skip") if version >= 3 else ("true" if sobrescribir else "false")
		campos = [("_sid", sid), ("path", carpeta), ("create_parents", "true"), ("overwrite", valor_sobrescribir)]
		if mtime:
			campos.append(("mtime", str(int(mtime * 1000))))
		limite = "zCommander" + uuid.uuid4().hex
		inicio = io.BytesIO()
		for clave, valor in campos:
			inicio.write(f'--{limite}\r\nContent-Disposition: form-data; name="{clave}"\r\n\r\n{valor}\r\n'.encode())
		nombre_cabecera = nombre.replace('"', "%22").replace("\r", " ").replace("\n", " ")
		inicio.write(f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{nombre_cabecera}"\r\n'
			f"Content-Type: application/octet-stream\r\n\r\n".encode())
		epilogo = f"\r\n--{limite}--\r\n".encode()
		preambulo = inicio.getvalue()
		conexion = self._conexion()
		try:
			conexion.putrequest("POST", self._url(info.ruta, "SYNO.FileStation.Upload", version, "upload"), skip_accept_encoding=True)
			for clave, valor in self._cabeceras(f"multipart/form-data; boundary={limite}").items():
				conexion.putheader(clave, valor)
			conexion.putheader("Content-Length", str(len(preambulo) + tamano + len(epilogo)))
			conexion.endheaders()
			conexion.send(preambulo)
		except (OSError, http.client.HTTPException) as error:
			conexion.close()
			raise errores.ErrorConexion(_("Se ha perdido la conexión con el NAS al empezar la subida."), 0) from error
		if self.registro_detallado:
			log.info("Subida de %s a %s (%s bytes)", nombre, carpeta, tamano)
		return conexion, epilogo

	def _terminar_subida(self, conexion: http.client.HTTPConnection, epilogo: bytes) -> dict[str, Any]:
		try:
			conexion.send(epilogo)
			respuesta = conexion.getresponse()
			cuerpo = respuesta.read()
		except TimeoutError as error:
			raise errores.ErrorConexion(_("El NAS no ha confirmado la subida a tiempo."), 0) from error
		except (OSError, http.client.HTTPException) as error:
			raise errores.ErrorConexion(_("Se ha perdido la conexión con el NAS al terminar la subida."), 0) from error
		finally:
			conexion.close()
		datos = self._json(respuesta.status, cuerpo, "SYNO.FileStation.Upload", "upload")
		if not datos.get("success"):
			raise errores.desde_respuesta(datos.get("error"), "SYNO.FileStation.Upload", "upload")
		return datos.get("data") or {}

	def abrir_subida(self, carpeta: str, nombre: str, tamano: int = -1, sobrescribir: bool = True,
			progreso: Callable[[int, int], None] | None = None, cancelacion: Any = None, mtime: float | None = None) -> SubidaEnFlujo:
		self.comprobar_escritura("SYNO.FileStation.Upload", "upload")
		return SubidaEnFlujo(self, carpeta, nombre, tamano, sobrescribir, progreso, cancelacion, mtime)

	def subir(self, ruta_carpeta: str, nombre: str, flujo: BinaryIO, tamano: int, sobrescribir: bool = True,
			progreso: Callable[[int, int], None] | None = None, cancelacion: Any = None, mtime: float | None = None) -> dict[str, Any]:
		"""Sube ``tamano`` bytes de ``flujo`` como ``ruta_carpeta/nombre``."""
		if tamano < 0:
			raise errores.ErrorDSM(_("Hace falta el tamaño del archivo para subirlo."), 1800, "SYNO.FileStation.Upload", "upload")
		destino = SubidaEnFlujo(self, ruta_carpeta, nombre, tamano, sobrescribir, progreso, cancelacion, mtime)
		try:
			while bloque := flujo.read(BLOQUE):
				destino.write(bloque)
		except BaseException:
			destino.cancelar()
			raise
		destino.close()
		return destino.respuesta

	def descargar(self, ruta: str, progreso: Callable[[int, int], None] | None = None, cancelacion: Any = None) -> FlujoDescarga:
		"""Flujo binario con el contenido de ``ruta`` (``SYNO.FileStation.Download``, ``mode=download``)."""
		api_nombre = "SYNO.FileStation.Download"
		if self.catalogo is None:
			raise errores.ErrorSesion(_("No hay conexión con el NAS."), 119, api_nombre, "download")
		info = self.catalogo.info(api_nombre)
		if info is None:
			raise errores.FuncionAusente(errores.mensaje(102, api_nombre), 102, api_nombre, "download")
		version = self.catalogo.version(api_nombre)
		campos = codificar_parametros({"path": [ruta], "mode": "download"}, info.json)
		for intento in (1, 2):
			api.comprobar(cancelacion)
			with self._candado:
				if self._sesion is None:
					self._iniciar_sesion(reintento=True)
				sid = self._sesion.sid
			conexion = self._conexion()
			try:
				conexion.request("POST", self._url(info.ruta, api_nombre, version, "download"), urlencode(dict(campos, _sid=sid)),
					self._cabeceras())
				respuesta = conexion.getresponse()
			except (OSError, http.client.HTTPException) as error:
				conexion.close()
				raise errores.ErrorConexion(_("Se ha perdido la conexión con el NAS al empezar la descarga."), 0, api_nombre) from error
			tipo = respuesta.getheader("Content-Type", "")
			if respuesta.status == 200 and "json" not in tipo.lower():
				tamano = int(respuesta.getheader("Content-Length", "-1") or -1)
				return FlujoDescarga(conexion, respuesta, tamano, progreso, cancelacion)
			try:
				cuerpo = respuesta.read()
			finally:
				conexion.close()
			if respuesta.status == 404:
				raise errores.NoEncontradoDSM(errores.mensaje(408, "SYNO.FileStation.List"), 408, api_nombre, "download", ruta)
			datos = self._json(respuesta.status, cuerpo, api_nombre, "download")
			error = errores.desde_respuesta(datos.get("error"), api_nombre, "download", ruta)
			if isinstance(error, errores.ErrorSesion) and intento == 1:
				with self._candado:
					self._sesion = None
				continue
			raise error
		raise errores.ErrorSesion(errores.mensaje(119), 119, api_nombre, "download")  # pragma: no cover


def _esperar(cancelacion: Any, segundos: float) -> None:
	espera = getattr(cancelacion, "wait", None)
	if callable(espera):
		if espera(segundos):
			raise api.Cancelado()
		return
	time.sleep(segundos)
	api.comprobar(cancelacion)


def es_ip_local(host: str) -> bool:
	"""Para avisos: direcciones privadas o de enlace local (192.168.x.x, 10.x.x.x...)."""
	try:
		return ipaddress.ip_address(socket.gethostbyname(host)).is_private
	except (OSError, ValueError):
		return False
