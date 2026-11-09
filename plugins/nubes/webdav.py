# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""``ProveedorWebDAV``: WebDAV nativo con la biblioteca estándar (diseño 2.0, 12.4; nubes.md 3.9).

Para Nextcloud, ownCloud, Synology, Koofr, kDrive, Yandex y servidores propios,
sin pasar por rclone: ``PROPFIND`` (profundidad 1) para listar, ``GET`` con
``Range``, ``PUT`` en flujo, ``MKCOL``, ``DELETE``, ``MOVE`` y ``COPY`` con
``Overwrite: F`` y la cuota con ``quota-available-bytes`` (RFC 4331).

- Contraseña en los secretos del complemento (``webdav:<id>:contrasena``), nunca
  en ``cuentas.json`` ni en el registro.
- Certificados: verificación normal; si falla (certificado propio de un NAS),
  se compara la huella SHA-256 con la aceptada para esa cuenta, como en FTPS.
  Una huella nueva solo se acepta con la confirmación de la persona.
- Esquemas ``webdav://`` y ``webdavs://`` para abrir una dirección sin cuenta
  guardada; si el servidor pide usuario, se pregunta con el ``Decisor``.
"""

from __future__ import annotations

import base64
import datetime
import email.utils
import hashlib
import http.client
import io
import logging
import posixpath
import queue
import socket
import ssl
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any, BinaryIO

from app.plugins import api

from .cuentas import Cuenta

if TYPE_CHECKING:
	from .servicio import Nubes

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

DAV = "{DAV:}"
TIEMPO_S = 60
_CUERPO_PROPFIND = (b'<?xml version="1.0" encoding="utf-8"?>\n<d:propfind xmlns:d="DAV:"><d:prop>'
	b"<d:resourcetype/><d:getcontentlength/><d:getlastmodified/><d:displayname/>"
	b"<d:quota-available-bytes/><d:quota-used-bytes/></d:prop></d:propfind>")


def huella_certificado(der: bytes) -> str:
	digest = hashlib.sha256(der).hexdigest().upper()
	return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


class ErrorHuella(api.ErrorAcceso):
	"""El certificado del servidor no es de confianza y su huella no es la aceptada."""

	def __init__(self, mensaje: str, huella: str, ruta: str = "") -> None:
		super().__init__(mensaje, ruta)
		self.huella = huella


def _fecha(texto: str) -> float:
	if not texto:
		return 0.0
	try:
		return email.utils.parsedate_to_datetime(texto).timestamp()
	except (TypeError, ValueError):
		try:
			return datetime.datetime.fromisoformat(texto.replace("Z", "+00:00")).timestamp()
		except ValueError:
			return 0.0


class ClienteWebDAV:
	"""Peticiones HTTP a un servidor WebDAV (una conexión por hilo)."""

	def __init__(self, url: str, usuario: str = "", contrasena: str = "", huella: str = "") -> None:
		partes = urllib.parse.urlsplit(url)
		if partes.scheme not in ("http", "https"):
			raise api.NombreNoValido(_("La dirección WebDAV debe empezar por http:// o https://"), url)
		self.seguro = partes.scheme == "https"
		self.anfitrion = partes.hostname or ""
		self.puerto = partes.port or (443 if self.seguro else 80)
		self.base = "/" + urllib.parse.unquote(partes.path).strip("/")
		self.usuario = usuario
		self.contrasena = contrasena
		self.huella = huella
		self._local = threading.local()

	# Conexión -------------------------------------------------------------------

	def _contexto(self, verificar: bool) -> ssl.SSLContext:
		contexto = ssl.create_default_context()
		if not verificar:
			contexto.check_hostname = False
			contexto.verify_mode = ssl.CERT_NONE
		return contexto

	def huella_servidor(self) -> str:
		"""Huella SHA-256 del certificado que presenta el servidor (sin verificarlo)."""
		with socket.create_connection((self.anfitrion, self.puerto), timeout=TIEMPO_S) as crudo, \
				self._contexto(False).wrap_socket(crudo, server_hostname=self.anfitrion) as seguro:
			return huella_certificado(seguro.getpeercert(binary_form=True) or b"")

	def _nueva_conexion(self, tiempo_s: float) -> http.client.HTTPConnection:
		if not self.seguro:
			return http.client.HTTPConnection(self.anfitrion, self.puerto, timeout=tiempo_s)
		if self.huella:
			conexion = http.client.HTTPSConnection(self.anfitrion, self.puerto, timeout=tiempo_s, context=self._contexto(False))
			conexion.connect()
			actual = huella_certificado(conexion.sock.getpeercert(binary_form=True) or b"")  # type: ignore[union-attr]
			if actual != self.huella:
				conexion.close()
				raise ErrorHuella(_("El certificado del servidor {s} ha cambiado desde que lo aceptó").format(s=self.anfitrion), actual)
			return conexion
		conexion = http.client.HTTPSConnection(self.anfitrion, self.puerto, timeout=tiempo_s, context=self._contexto(True))
		try:
			conexion.connect()
		except ssl.SSLCertVerificationError as error:
			conexion.close()
			raise ErrorHuella(_("El certificado del servidor {s} no es de confianza").format(s=self.anfitrion),
				self.huella_servidor()) from error
		return conexion

	def _conexion(self, tiempo_s: float) -> http.client.HTTPConnection:
		conexion = getattr(self._local, "conexion", None)
		if conexion is None:
			conexion = self._nueva_conexion(tiempo_s)
			self._local.conexion = conexion
		return conexion

	def _soltar(self) -> None:
		conexion = getattr(self._local, "conexion", None)
		self._local.conexion = None
		if conexion is not None:
			conexion.close()

	def ruta_http(self, ruta: str) -> str:
		completa = posixpath.join(self.base, (ruta or "").strip("/"))
		return urllib.parse.quote(completa if completa.startswith("/") else "/" + completa, safe="/")

	def cabeceras(self, extra: dict[str, str] | None = None) -> dict[str, str]:
		cabeceras = {"User-Agent": "zCommander (zc.nubes)"}
		if self.usuario or self.contrasena:
			credencial = base64.b64encode(f"{self.usuario}:{self.contrasena}".encode()).decode("ascii")
			cabeceras["Authorization"] = f"Basic {credencial}"
		cabeceras.update(extra or {})
		return cabeceras

	def peticion(self, metodo: str, ruta: str, *, cuerpo: bytes | None = None, cabeceras: dict[str, str] | None = None,
			tiempo_s: float = TIEMPO_S, leer: bool = True) -> tuple[int, dict[str, str], bytes, Any]:
		"""Una petición; repite una vez si una conexión reutilizada se había cerrado."""
		for intento in range(2):
			conexion = self._conexion(tiempo_s)
			try:
				conexion.request(metodo, self.ruta_http(ruta), body=cuerpo, headers=self.cabeceras(cabeceras))
				respuesta = conexion.getresponse()
				if not leer:
					return respuesta.status, dict(respuesta.getheaders()), b"", respuesta
				datos = respuesta.read()
				if (respuesta.getheader("Connection") or "").lower() == "close":
					self._soltar()
				return respuesta.status, {k.lower(): v for k, v in respuesta.getheaders()}, datos, None
			except (http.client.HTTPException, OSError) as error:
				self._soltar()
				if isinstance(error, api.ErrorArchivos):
					raise
				if intento == 1 or metodo not in ("GET", "PROPFIND", "HEAD", "OPTIONS"):
					raise api.ErrorRed(_("No hay conexión con el servidor WebDAV {s}").format(s=self.anfitrion), ruta) from error
		raise api.ErrorRed(_("No hay conexión con el servidor WebDAV {s}").format(s=self.anfitrion), ruta)


def error_http(estado: int, ruta: str, servidor: str = "") -> api.ErrorArchivos:
	nombre = posixpath.basename(ruta.rstrip("/")) or ruta
	if estado == 401:
		return api.ErrorAcceso(_("El servidor {s} no acepta el usuario o la contraseña").format(s=servidor), ruta)
	if estado in (403, 423):
		return api.ErrorAcceso(_("No tiene permiso para esto en el servidor"), ruta)
	if estado in (404, 410):
		return api.NoEncontrado(_("No existe en el servidor: {n}").format(n=nombre), ruta)
	if estado == 409:
		return api.NoEncontrado(_("No existe la carpeta de destino de {n}").format(n=nombre), ruta)
	if estado in (405, 412):
		return api.YaExiste(_("Ya existe un elemento con ese nombre: {n}").format(n=nombre), ruta)
	if estado == 507:
		return api.SinEspacio(_("No queda espacio en el servidor"), ruta)
	if estado == 429 or estado == 503:
		return api.ErrorRed(_("El servidor pide esperar; inténtelo más tarde"), ruta)
	return api.ErrorArchivos(_("El servidor WebDAV respondió con el error {e}").format(e=estado), ruta)


class ProveedorWebDAV(api.Proveedor):
	"""Una carpeta WebDAV como unidad del panel."""

	def __init__(self, cliente: ClienteWebDAV, *, nombre: str, esquema: str = "nube", servidor: str = "", solo_lectura: bool = False,
			decisor: Any = None, al_aceptar_huella: Any = None, cuenta: Cuenta | None = None) -> None:
		super().__init__()
		self.esquema = esquema
		self.cliente = cliente
		self.nombre_visible = nombre
		self.servidor = servidor or f"webdav:{cliente.anfitrion}:{cliente.puerto}"
		self.cuenta = cuenta
		self._solo_lectura = solo_lectura
		self._decisor = decisor
		self._al_aceptar_huella = al_aceptar_huella
		self._cuota: tuple[int, int] | None = None
		self._credenciales_pedidas = False
		self.capacidades.escribir = not solo_lectura
		self.capacidades.escritura_atomica = False
		self.capacidades.renombrar_barato = True
		self.capacidades.copia_servidor = True

	@classmethod
	def de_cuenta(cls, nubes: Nubes, cuenta: Cuenta) -> ProveedorWebDAV:
		contrasena = nubes.zc.secretos.obtener(f"webdav:{cuenta.id}:contrasena") or ""
		cliente = ClienteWebDAV(cuenta.url, cuenta.usuario, contrasena, cuenta.huella)

		def aceptar(huella: str) -> None:
			actual = nubes.cuentas.obtener(cuenta.id)
			if actual is not None:
				actual.huella = huella
				nubes.cuentas.guardar(actual)

		return cls(cliente, nombre=cuenta.nombre, servidor=f"nube:{cuenta.id}", solo_lectura=cuenta.solo_lectura,
			decisor=_decisor_de(nubes), al_aceptar_huella=aceptar, cuenta=cuenta)

	# Identidad --------------------------------------------------------------

	def descripcion(self) -> str:
		return _("Servidor WebDAV")

	def mostrar(self, ruta: str) -> str:
		return f"{self.nombre_visible}:\\" + (ruta or "/").strip("/").replace("/", "\\")

	def padre(self, ruta: str) -> str | None:
		limpia = "/" + (ruta or "").strip("/")
		return None if limpia == "/" else (posixpath.dirname(limpia) or "/")

	def unir(self, carpeta: str, nombre: str) -> str:
		return "/" + posixpath.join((carpeta or "").strip("/"), nombre).strip("/")

	def raiz(self, ruta: str) -> str:
		return "/"

	def nombre(self, ruta: str) -> str:
		return posixpath.basename((ruta or "").strip("/")) or self.nombre_visible

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		return True

	# Peticiones con huella y credenciales --------------------------------------------

	def _peticion(self, metodo: str, ruta: str, **opciones: Any) -> tuple[int, dict[str, str], bytes, Any]:
		for _intento in range(3):
			try:
				estado, cabeceras, datos, respuesta = self.cliente.peticion(metodo, ruta, **opciones)
			except ErrorHuella as error:
				if not self._preguntar_huella(error):
					raise
				continue
			if estado == 401 and self._pedir_credenciales():
				continue
			return estado, cabeceras, datos, respuesta
		return estado, cabeceras, datos, respuesta

	def _preguntar_huella(self, error: ErrorHuella) -> bool:
		if self._decisor is None:
			return False
		texto = _("{m}. Huella SHA-256 del certificado: {h}. Acéptela solo si coincide con la del servidor.").format(
			m=error.mensaje, h=error.huella)
		eleccion = self._decisor.elegir(_("Certificado del servidor WebDAV"), texto,
			[_("&No conectar"), _("&Aceptar esta huella")], predeterminada=0, escape=0)
		if eleccion != 1:
			return False
		self.cliente.huella = error.huella
		if self._al_aceptar_huella is not None:
			self._al_aceptar_huella(error.huella)
		return True

	def _pedir_credenciales(self) -> bool:
		if self._decisor is None or self._credenciales_pedidas or self.cuenta is not None:
			return False
		self._credenciales_pedidas = True
		respuesta = self._decisor.pedir_credenciales(_("Servidor WebDAV"),
			_("El servidor {s} pide usuario y contraseña").format(s=self.cliente.anfitrion), self.cliente.usuario)
		if not respuesta:
			return False
		self.cliente.usuario, self.cliente.contrasena = respuesta[0], respuesta[1]
		self.cliente._soltar()
		return True

	def _exigir_escritura(self, ruta: str) -> None:
		if self._solo_lectura:
			raise api.SoloLectura(_("{n} es de solo lectura").format(n=self.nombre_visible), ruta)

	def _comprobar(self, estado: int, ruta: str, *validos: int) -> None:
		if estado not in (validos or (200, 201, 204, 207)):
			raise error_http(estado, ruta, self.cliente.anfitrion)

	# Navegación ---------------------------------------------------------------

	def _propfind(self, ruta: str, profundidad: str) -> list[tuple[str, dict[str, str], bool]]:
		cabeceras = {"Depth": profundidad, "Content-Type": "application/xml; charset=utf-8"}
		estado, _c, datos, _r = self._peticion("PROPFIND", ruta, cuerpo=_CUERPO_PROPFIND, cabeceras=cabeceras)
		self._comprobar(estado, ruta, 207)
		try:
			arbol = ET.fromstring(datos)
		except ET.ParseError as error:
			raise api.ErrorArchivos(_("El servidor WebDAV devolvió una respuesta que no se entiende"), ruta) from error
		resultado = []
		for respuesta in arbol.iter(f"{DAV}response"):
			href = urllib.parse.unquote(urllib.parse.urlsplit(respuesta.findtext(f"{DAV}href", "")).path)
			propiedades: dict[str, str] = {}
			carpeta = False
			for propstat in respuesta.iter(f"{DAV}propstat"):
				if " 200" not in (propstat.findtext(f"{DAV}status", "") or " 200"):
					continue
				prop = propstat.find(f"{DAV}prop")
				if prop is None:
					continue
				for hijo in prop:
					nombre = hijo.tag.replace(DAV, "")
					if nombre == "resourcetype":
						carpeta = hijo.find(f"{DAV}collection") is not None
					else:
						propiedades[nombre] = (hijo.text or "").strip()
			resultado.append((href, propiedades, carpeta))
		return resultado

	def _es_la_misma(self, href: str, ruta: str) -> bool:
		return href.rstrip("/") == urllib.parse.unquote(self.cliente.ruta_http(ruta)).rstrip("/")

	def listar(self, ruta: str, cancelacion=None) -> list[api.Entrada]:
		api.comprobar(cancelacion)
		entradas = []
		for href, propiedades, carpeta in self._propfind(ruta, "1"):
			if self._es_la_misma(href, ruta):
				self._guardar_cuota(propiedades)
				continue
			nombre = posixpath.basename(href.rstrip("/"))
			if not nombre:
				continue
			tamano = -1 if carpeta else int(propiedades.get("getcontentlength") or 0)
			entradas.append(api.Entrada(nombre=nombre, ruta=self.unir(ruta, nombre), es_carpeta=carpeta, tamano=tamano,
				modificado=_fecha(propiedades.get("getlastmodified", ""))))
		return entradas

	def _guardar_cuota(self, propiedades: dict[str, str]) -> None:
		try:
			libre = int(propiedades.get("quota-available-bytes") or -1)
			usado = int(propiedades.get("quota-used-bytes") or 0)
		except ValueError:
			return
		if libre >= 0:
			self._cuota = (libre, libre + max(0, usado))

	def info(self, ruta: str) -> api.Entrada:
		limpia = "/" + (ruta or "").strip("/")
		if limpia == "/":
			return api.Entrada(nombre=self.nombre_visible, ruta="/", es_carpeta=True)
		for href, propiedades, carpeta in self._propfind(limpia, "0"):
			nombre = posixpath.basename(href.rstrip("/")) or posixpath.basename(limpia)
			return api.Entrada(nombre=nombre, ruta=limpia, es_carpeta=carpeta,
				tamano=-1 if carpeta else int(propiedades.get("getcontentlength") or 0),
				modificado=_fecha(propiedades.get("getlastmodified", "")))
		raise api.NoEncontrado(_("No existe en el servidor: {n}").format(n=posixpath.basename(limpia)), ruta)

	def espacio_libre(self, ruta: str) -> tuple[int, int] | None:
		if self._cuota is None:
			try:
				for href, propiedades, _carpeta in self._propfind(ruta or "/", "0"):
					if self._es_la_misma(href, ruta or "/"):
						self._guardar_cuota(propiedades)
			except api.ErrorArchivos:
				log.debug("Sin cuota WebDAV", exc_info=True)
		return self._cuota

	# Contenido ----------------------------------------------------------------

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		return io.BufferedReader(_FlujoGet(self, ruta), 1024 * 1024)

	def abrir_escritura(self, ruta: str, tamano: int = -1) -> BinaryIO:
		self._exigir_escritura(ruta)
		return _FlujoPut(self, ruta, tamano)

	def crear_carpeta(self, ruta: str) -> None:
		self._exigir_escritura(ruta)
		estado, *_resto = self._peticion("MKCOL", ruta)
		self._comprobar(estado, ruta, 200, 201)

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		self._exigir_escritura(ruta)
		entrada = self.info(ruta)
		if entrada.es_carpeta and not recursivo and self.listar(ruta):
			raise api.ErrorAcceso(_("La carpeta no está vacía"), ruta)
		estado, *_resto = self._peticion("DELETE", ruta + ("/" if entrada.es_carpeta else ""))
		self._comprobar(estado, ruta, 200, 202, 204)

	def _destino(self, ruta: str) -> str:
		esquema = "https" if self.cliente.seguro else "http"
		anfitrion = f"[{self.cliente.anfitrion}]" if ":" in self.cliente.anfitrion else self.cliente.anfitrion
		return f"{esquema}://{anfitrion}:{self.cliente.puerto}{self.cliente.ruta_http(ruta)}"

	def renombrar(self, origen: str, destino: str) -> None:
		self._exigir_escritura(origen)
		estado, *_resto = self._peticion("MOVE", origen, cabeceras={"Destination": self._destino(destino), "Overwrite": "F"})
		self._comprobar(estado, origen, 201, 204)

	def copiar_en_servidor(self, origen: str, destino: str) -> None:
		self._exigir_escritura(destino)
		estado, *_resto = self._peticion("COPY", origen, cabeceras={"Destination": self._destino(destino), "Overwrite": "F",
			"Depth": "infinity"})
		self._comprobar(estado, origen, 201, 204)

	def transferir(self, origen: api.Proveedor, ruta_origen: str, ruta_destino: str, progreso, cancelacion) -> bool:
		"""Dentro del mismo servidor, ``COPY`` (sin pasar los bytes por zCommander)."""
		if not isinstance(origen, ProveedorWebDAV) or origen.servidor != self.servidor:
			return False
		tamano = max(0, origen.info(ruta_origen).tamano)
		self.copiar_en_servidor(ruta_origen, ruta_destino)
		progreso(tamano, tamano)
		return True


class _FlujoGet(io.RawIOBase):
	"""GET en flujo con ``Range``; se reanuda donde se cortó."""

	def __init__(self, proveedor: ProveedorWebDAV, ruta: str) -> None:
		super().__init__()
		self._proveedor = proveedor
		self._ruta = ruta
		self._posicion = 0
		self._respuesta: Any = None
		self._fin = False

	def readable(self) -> bool:
		return True

	def _abrir(self) -> None:
		cliente = self._proveedor.cliente
		conexion = cliente._nueva_conexion(TIEMPO_S)
		cabeceras = cliente.cabeceras({"Range": f"bytes={self._posicion}-"} if self._posicion else None)
		conexion.request("GET", cliente.ruta_http(self._ruta), headers=cabeceras)
		respuesta = conexion.getresponse()
		if respuesta.status == 416:
			self._fin = True
			conexion.close()
			return
		if respuesta.status not in (200, 206):
			respuesta.read()
			conexion.close()
			raise error_http(respuesta.status, self._ruta, cliente.anfitrion)
		if self._posicion and respuesta.status == 200:
			restante = self._posicion
			while restante > 0:
				bloque = respuesta.read(min(restante, 1024 * 1024))
				if not bloque:
					break
				restante -= len(bloque)
		self._respuesta = (conexion, respuesta)

	def readinto(self, destino: Any) -> int:
		for intento in range(3):
			if self._fin:
				return 0
			try:
				if self._respuesta is None:
					self._abrir()
					if self._fin:
						return 0
				leidos = self._respuesta[1].readinto(destino)
				if leidos == 0:
					self._fin = True
				self._posicion += leidos
				return leidos
			except (http.client.HTTPException, OSError) as error:
				self._cerrar_conexion()
				if isinstance(error, api.ErrorArchivos) or intento == 2:
					if isinstance(error, api.ErrorArchivos):
						raise
					raise api.ErrorRed(_("Se cortó la descarga de {n}").format(n=self._ruta), self._ruta) from error
				time.sleep(0.5)
		return 0

	def _cerrar_conexion(self) -> None:
		if self._respuesta is not None:
			try:
				self._respuesta[0].close()
			except OSError:
				log.debug("No se pudo cerrar la descarga WebDAV", exc_info=True)
		self._respuesta = None

	def close(self) -> None:
		self._cerrar_conexion()
		super().close()


class _FlujoPut(io.RawIOBase):
	"""PUT en flujo: con ``Content-Length`` si se sabe el tamaño; si no, troceado."""

	_FIN = object()
	_ABORTAR = object()

	def __init__(self, proveedor: ProveedorWebDAV, ruta: str, tamano: int) -> None:
		super().__init__()
		self._cola: queue.Queue = queue.Queue(maxsize=16)
		self._error: BaseException | None = None
		self._ruta = ruta
		cliente = proveedor.cliente

		def subir() -> None:
			conexion = None
			try:
				conexion = cliente._nueva_conexion(TIEMPO_S * 10)
				conexion.putrequest("PUT", cliente.ruta_http(ruta))
				for clave, valor in cliente.cabeceras({"Content-Type": "application/octet-stream"}).items():
					conexion.putheader(clave, valor)
				troceado = tamano < 0
				conexion.putheader("Transfer-Encoding" if troceado else "Content-Length", "chunked" if troceado else str(tamano))
				conexion.endheaders()
				while True:
					trozo = self._cola.get()
					if trozo is _FlujoPut._FIN:
						break
					if trozo is _FlujoPut._ABORTAR:
						return
					conexion.send(f"{len(trozo):X}\r\n".encode() + trozo + b"\r\n" if troceado else trozo)
				if troceado:
					conexion.send(b"0\r\n\r\n")
				respuesta = conexion.getresponse()
				respuesta.read()
				if respuesta.status not in (200, 201, 204):
					self._error = error_http(respuesta.status, ruta, cliente.anfitrion)
			except BaseException as error:  # noqa: BLE001 - se relanza al cerrar
				self._error = error if isinstance(error, api.ErrorArchivos) else api.ErrorRed(
					_("Se cortó la subida de {n}").format(n=posixpath.basename(ruta)), ruta)
				log.debug("Subida WebDAV fallida", exc_info=True)
				while True:
					try:
						self._cola.get_nowait()
					except queue.Empty:
						break
			finally:
				if conexion is not None:
					conexion.close()

		self._hilo = threading.Thread(target=subir, daemon=True, name="zc-nubes-webdav-put")
		self._hilo.start()

	def writable(self) -> bool:
		return True

	def _poner(self, elemento: Any) -> None:
		while True:
			if self._error is not None:
				raise self._error
			if not self._hilo.is_alive():
				raise api.ErrorRed(_("Se cortó la subida de {n}").format(n=posixpath.basename(self._ruta)), self._ruta)
			try:
				self._cola.put(elemento, timeout=0.5)
				return
			except queue.Full:
				continue

	def write(self, datos: Any) -> int:
		bloque = bytes(datos)
		if bloque:
			self._poner(bloque)
		return len(bloque)

	def close(self) -> None:
		if self.closed:
			return
		try:
			if self._error is None and self._hilo.is_alive():
				self._poner(_FlujoPut._FIN)
			self._hilo.join()
		finally:
			super().close()
		if self._error is not None:
			raise self._error

	def __exit__(self, tipo, valor, traza) -> None:
		if tipo is not None:
			if not self.closed:
				try:
					self._cola.put(_FlujoPut._ABORTAR, timeout=5)
				except queue.Full:
					log.debug("No se pudo cortar la subida WebDAV")
				self._hilo.join(30)
				super().close()
			return
		self.close()


def _decisor_de(nubes: Any) -> Any:
	try:
		return nubes.zc.decisor
	except api.NoAdmitido:
		return None


def fabrica_direccion(nubes: Nubes, direccion: str) -> tuple[api.Proveedor, str]:
	"""``webdav://[usuario@]servidor[:puerto]/ruta`` o ``webdavs://...``: un servidor sin cuenta guardada."""
	partes = urllib.parse.urlsplit(direccion)
	seguro = partes.scheme.lower() == "webdavs"
	anfitrion = partes.hostname or ""
	if not anfitrion:
		raise api.NombreNoValido(_("Falta el servidor en la dirección {d}").format(d=direccion), direccion)
	puerto = f":{partes.port}" if partes.port else ""
	servidor = f"[{anfitrion}]" if ":" in anfitrion else anfitrion
	url = f"{'https' if seguro else 'http'}://{servidor}{puerto}/"
	cliente = ClienteWebDAV(url, urllib.parse.unquote(partes.username or ""), urllib.parse.unquote(partes.password or ""))
	proveedor = ProveedorWebDAV(cliente, nombre=anfitrion, esquema=partes.scheme.lower(), decisor=_decisor_de(nubes))
	return proveedor, "/" + urllib.parse.unquote(partes.path).strip("/")
