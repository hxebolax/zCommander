# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Peticiones HTTP con la biblioteca estándar (diseño 2.0, 0.3 y 14.9).

Reglas del agente red-http, sin su dependencia ``requests`` (ningún paquete
nuevo en tiempo de ejecución):

- **Tiempo de espera siempre**; reintentos solo de GET (y solo de fallos de
  conexión, tiempo o 429/5xx), respetando ``Retry-After``.
- **Solo https**, salvo a la propia máquina (``localhost``): así las pruebas
  usan ``http.server`` sin abrir la puerta a una bajada a http en Internet.
  Una redirección no puede bajar a http.
- Certificados del almacén de Windows (``ssl.create_default_context()`` lo
  carga) y proxy del sistema (``urllib.request.getproxies()``).
- Mensajes en español y URL redactadas en el registro (nunca fichas de acceso).

Se llama ``ErrorHTTP`` y no ``ErrorRed`` para no tener dos clases con el mismo
nombre: la de los complementos y del sistema de archivos es
``vfs.base.ErrorRed``, y la fachada ``ClienteRed`` convierte una en otra.
Sin wx y sin importar ``app.services`` (regla de capas).
"""

from __future__ import annotations

import builtins
import http.client
import json
import logging
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

HOSTS_LOCALES = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_REINTENTOS = 2
MAX_ESPERA_REINTENTO = 30.0
MAX_CUERPO = 64 * 1024 * 1024

CONEXION, TIEMPO, CERTIFICADO, HTTP, CANCELADO = "conexion", "tiempo", "certificado", "http", "cancelado"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class ConfiguracionRed:
	"""Identidad y tiempos de las peticiones (User-Agent «<nombre_app>/<version_app>»)."""

	nombre_app: str
	version_app: str
	proxy: str = "sistema"
	tiempo_conexion: float = 10
	tiempo_lectura: float = 30

	@property
	def agente(self) -> str:
		return f"{self.nombre_app}/{self.version_app}"


@dataclass(frozen=True)
class RespuestaRed:
	estado: int
	cabeceras: dict[str, str] = field(default_factory=dict)
	cuerpo: bytes = b""
	url_final: str = ""

	def texto(self) -> str:
		"""El cuerpo decodificado con el juego de caracteres de ``Content-Type`` (UTF-8 si no dice)."""
		tipo = next((v for k, v in self.cabeceras.items() if k.lower() == "content-type"), "")
		encontrado = re.search(r"charset=([\w.-]+)", tipo or "", re.IGNORECASE)
		codificacion = encontrado.group(1) if encontrado else "utf-8"
		try:
			return self.cuerpo.decode(codificacion, errors="replace")
		except LookupError:
			return self.cuerpo.decode("utf-8", errors="replace")

	def json(self) -> Any:
		return json.loads(self.texto())


class ErrorHTTP(Exception):
	"""Fallo de red o respuesta HTTP de error, con mensaje en español.

	:param categoria: ``conexion``, ``tiempo``, ``certificado``, ``http`` o ``cancelado``.
	:param estado: código HTTP (0 si no hubo respuesta).
	"""

	def __init__(self, categoria: str, mensaje: str, estado: int = 0) -> None:
		super().__init__(mensaje)
		self.categoria = categoria
		self.estado = estado
		self.mensaje = mensaje


@dataclass(frozen=True)
class InfoError:
	categoria: str
	mensaje: str
	reintentar: bool


_SECRETOS_URL = re.compile(
	r"((?:token|access_token|refresh_token|key|apikey|api_key|password|passwd|_sid|sid|signature|sig|code)=)[^&#\s]*",
	re.IGNORECASE,
)


def redactar_url(url: str) -> str:
	"""La URL sin usuario, contraseña ni valores de parámetros sensibles (para el registro)."""
	try:
		partes = urllib.parse.urlsplit(url)
		red = partes.hostname or ""
		if partes.port:
			red += f":{partes.port}"
		if partes.username or partes.password:
			red = "***@" + red
		url = urllib.parse.urlunsplit((partes.scheme, red, partes.path, partes.query, partes.fragment))
	except ValueError:
		log.debug("URL que no se pudo analizar al redactar", exc_info=True)
	return _SECRETOS_URL.sub(r"\1***", url)


def _mensaje_http(estado: int) -> str:
	if estado in (401, 403):
		return _("El servidor no da permiso (error {e}).").format(e=estado)
	if estado == 404:
		return _("No se encontró en el servidor (error 404).")
	if estado == 429:
		return _("El servidor pide esperar antes de volver a intentarlo (error 429).")
	if estado >= 500:
		return _("El servidor tiene un problema (error {e}). Inténtelo más tarde.").format(e=estado)
	return _("El servidor respondió con el error {e}.").format(e=estado)


def clasificar_error(error: BaseException) -> InfoError:
	"""Categoría, mensaje en español y si tiene sentido reintentar (solo GET)."""
	if isinstance(error, ErrorHTTP):
		reintentar = error.categoria in (CONEXION, TIEMPO) or (error.categoria == HTTP and (error.estado == 429 or error.estado >= 500))
		return InfoError(error.categoria, error.mensaje, reintentar)
	if isinstance(error, urllib.error.HTTPError):
		return InfoError(HTTP, _mensaje_http(error.code), error.code == 429 or error.code >= 500)
	razon = getattr(error, "reason", error)
	if isinstance(razon, ssl.SSLCertVerificationError) or isinstance(error, ssl.SSLCertVerificationError):
		return InfoError(CERTIFICADO, _("El certificado del servidor no es válido; no se ha conectado por seguridad."), False)
	if isinstance(razon, ssl.SSLError) or isinstance(error, ssl.SSLError):
		return InfoError(CERTIFICADO, _("No se pudo establecer una conexión segura con el servidor."), False)
	if isinstance(razon, (TimeoutError, socket.timeout)) or isinstance(error, (TimeoutError, socket.timeout)):
		return InfoError(TIEMPO, _("El servidor no respondió a tiempo."), True)
	if isinstance(razon, socket.gaierror):
		return InfoError(CONEXION, _("No se encontró el servidor. Compruebe la dirección y la conexión a Internet."), True)
	if isinstance(error, (urllib.error.URLError, ConnectionError, http.client.HTTPException, OSError)):
		return InfoError(CONEXION, _("No se pudo conectar con el servidor. Compruebe la conexión a Internet."), True)
	return InfoError(CONEXION, _("Error de red: {e}").format(e=error), False)


def comprobar_url(url: str) -> None:
	"""Solo https (o http a la propia máquina). Lanza ``ErrorHTTP`` si no."""
	partes = urllib.parse.urlsplit(url)
	if partes.scheme == "https":
		return
	if partes.scheme == "http" and (partes.hostname or "") in HOSTS_LOCALES:
		return
	raise ErrorHTTP(CONEXION, _("Solo se admiten direcciones https: {u}").format(u=redactar_url(url)))


def _es_http_local(url: str) -> bool:
	partes = urllib.parse.urlsplit(url)
	return partes.scheme == "http" and (partes.hostname or "") in HOSTS_LOCALES


class _SinBajarAHttp(urllib.request.HTTPRedirectHandler):
	"""Solo se siguen redirecciones a https.

	2.0.1: a http de la propia máquina, solo si la petición ya era http local (pruebas y
	servidores locales); un servidor remoto no puede mandar a zCommander a ``http://localhost``.
	"""

	def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 - firma de urllib
		comprobar_url(newurl)
		if _es_http_local(newurl) and not _es_http_local(req.full_url):
			raise ErrorHTTP(CONEXION, _("El servidor redirigió a una dirección de este equipo sin cifrar; no se sigue por seguridad: {u}").format(
				u=redactar_url(newurl)))
		return super().redirect_request(req, fp, code, msg, headers, newurl)


def _abridor(config: ConfiguracionRed) -> urllib.request.OpenerDirector:
	manejadores: list[Any] = [urllib.request.HTTPSHandler(context=ssl.create_default_context()), _SinBajarAHttp()]
	if config.proxy == "sistema":
		manejadores.append(urllib.request.ProxyHandler(urllib.request.getproxies()))
	elif config.proxy == "ninguno":
		manejadores.append(urllib.request.ProxyHandler({}))
	return urllib.request.build_opener(*manejadores)


def abrir(config: ConfiguracionRed, url: str, *, metodo: str = "GET", datos: bytes | None = None,
		cabeceras: dict[str, str] | None = None, tiempo_s: float | None = None):
	"""Abre la URL y devuelve la respuesta de ``urllib`` (hay que cerrarla). Lanza ``urllib.error.HTTPError`` o ``ErrorHTTP``."""
	comprobar_url(url)
	todas = {"User-Agent": config.agente}
	todas.update(cabeceras or {})
	peticion = urllib.request.Request(url, data=datos, headers=todas, method=metodo)
	try:
		respuesta = _abridor(config).open(peticion, timeout=tiempo_s or config.tiempo_lectura)
	except urllib.error.HTTPError:
		raise
	except ErrorHTTP:
		raise
	except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
		info = clasificar_error(error)
		log.warning("Fallo de red con %s: %s", redactar_url(url), error)
		raise ErrorHTTP(info.categoria, info.mensaje) from error
	try:
		comprobar_url(respuesta.geturl())
	except ErrorHTTP:
		respuesta.close()
		raise
	return respuesta


def _espera_reintento(error: urllib.error.HTTPError, intento: int) -> float:
	valor = error.headers.get("Retry-After") if error.headers is not None else None
	if valor and str(valor).strip().isdigit():
		return min(float(valor), MAX_ESPERA_REINTENTO)
	return min(2.0 ** intento, MAX_ESPERA_REINTENTO)


def _peticion(config: ConfiguracionRed, url: str, metodo: str, datos: bytes | None, cabeceras: dict[str, str] | None,
		tiempo_s: float) -> RespuestaRed:
	intentos = MAX_REINTENTOS + 1 if metodo == "GET" else 1
	for intento in range(intentos):
		try:
			with abrir(config, url, metodo=metodo, datos=datos, cabeceras=cabeceras, tiempo_s=tiempo_s) as respuesta:
				cuerpo = respuesta.read(MAX_CUERPO + 1)
				if len(cuerpo) > MAX_CUERPO:
					raise ErrorHTTP(HTTP, _("La respuesta del servidor es demasiado grande."))
				return RespuestaRed(respuesta.status, dict(respuesta.headers.items()), cuerpo, respuesta.geturl())
		except urllib.error.HTTPError as error:
			info = clasificar_error(error)
			if info.reintentar and intento + 1 < intentos:
				espera = _espera_reintento(error, intento)
				log.info("Error %s en %s; se reintenta en %.1f s", error.code, redactar_url(url), espera)
				time.sleep(espera)
				continue
			raise ErrorHTTP(HTTP, info.mensaje, error.code) from error
		except ErrorHTTP as error:
			if error.categoria in (CONEXION, TIEMPO) and intento + 1 < intentos:
				time.sleep(min(2.0 ** intento, MAX_ESPERA_REINTENTO))
				continue
			raise
	raise ErrorHTTP(CONEXION, _("No se pudo conectar con el servidor."))


def obtener(config: ConfiguracionRed, url: str, *, cabeceras: dict[str, str] | None = None, tiempo_s: float = 30) -> RespuestaRed:
	"""GET con reintentos. Lanza ``ErrorHTTP`` con el mensaje en español."""
	return _peticion(config, url, "GET", None, cabeceras, tiempo_s)


def enviar(config: ConfiguracionRed, url: str, datos: bytes | dict, *, metodo: str = "POST",
		cabeceras: dict[str, str] | None = None, tiempo_s: float = 30) -> RespuestaRed:
	"""POST (u otro método) sin reintentos; un ``dict`` se envía como JSON."""
	todas = dict(cabeceras or {})
	if isinstance(datos, dict):
		cuerpo = json.dumps(datos).encode("utf-8")
		todas.setdefault("Content-Type", "application/json; charset=utf-8")
	else:
		cuerpo = bytes(datos)
	return _peticion(config, url, metodo.upper(), cuerpo, todas, tiempo_s)
