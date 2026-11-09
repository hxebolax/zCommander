# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cliente del API remoto de ``rclone rcd`` (diseño 2.0, 12.2; rclone.md 2.3 y 3).

Solo biblioteca estándar: ``http.client`` con autenticación básica, POST con
JSON y tiempos de espera. Una conexión por hilo (``http.client`` no se comparte
entre hilos). Las llamadas de solo lectura se repiten una vez si la conexión se
corta (rcd la reabre); las que cambian algo nunca se repiten solas.

Trabajos largos: ``llamar_asincrono`` con ``_async`` y ``_group``; ``esperar_trabajo``
consulta ``job/status`` y ``core/stats`` como mucho 4 veces por segundo y, si se
cancela, para el grupo (``job/stopgroup``) y lanza ``Cancelado``.
"""

from __future__ import annotations

import base64
import http.client
import io
import json
import logging
import threading
import time
import urllib.parse
import uuid
from collections.abc import Callable, Iterable
from typing import Any, BinaryIO

from app.plugins import api

from . import errores

log = logging.getLogger("zcplugins.zc.nubes")

#: Rutas que no cambian nada: se pueden repetir si la conexión se corta.
SOLO_LECTURA = frozenset({
	"core/pid", "core/version", "core/stats", "core/transferred", "core/bwlimit_consulta", "job/status", "job/list",
	"config/listremotes", "config/paths", "config/oauthstatus", "config/providers", "operations/list", "operations/stat",
	"operations/about", "operations/fsinfo", "operations/size", "operations/hashsumfile", "mount/listmounts", "serve/list",
	"vfs/queue", "vfs/list", "options/get", "rc/noopauth", "mount/types", "serve/types",
})

#: Tiempo de espera de las llamadas normales (las largas van con ``_async``).
TIEMPO_LLAMADA_S = 120.0


def _cancelado(cancelacion: Any) -> bool:
	if cancelacion is None:
		return False
	cancelacion = getattr(cancelacion, "token", cancelacion)
	esta = getattr(cancelacion, "is_set", None)
	return bool(esta()) if callable(esta) else False


class ClienteRC:
	"""Habla con un rcd concreto (puerto y credenciales de ESE arranque)."""

	def __init__(self, puerto: int, usuario: str, contrasena: str, *, anfitrion: str = "127.0.0.1") -> None:
		self.puerto = puerto
		self.anfitrion = anfitrion
		self._autorizacion = "Basic " + base64.b64encode(f"{usuario}:{contrasena}".encode()).decode("ascii")
		self._local = threading.local()
		#: Trabajos asíncronos lanzados (las pruebas cuentan cuántos hace un lote).
		self.trabajos_lanzados = 0
		self._candado = threading.Lock()

	# ── Conexión ───────────────────────────────────────────────────────────

	def _conexion(self, tiempo_s: float) -> http.client.HTTPConnection:
		conexion = getattr(self._local, "conexion", None)
		if conexion is None:
			conexion = http.client.HTTPConnection(self.anfitrion, self.puerto, timeout=tiempo_s)
			self._local.conexion = conexion
		else:
			conexion.timeout = tiempo_s
			if conexion.sock is not None:
				conexion.sock.settimeout(tiempo_s)
		return conexion

	def _cerrar_conexion(self) -> None:
		conexion = getattr(self._local, "conexion", None)
		self._local.conexion = None
		if conexion is not None:
			try:
				conexion.close()
			except OSError:
				log.debug("No se pudo cerrar la conexión con rcd", exc_info=True)

	def _peticion(self, metodo: str, ruta: str, cuerpo: bytes | None, cabeceras: dict[str, str], tiempo_s: float,
			repetir: bool) -> tuple[int, bytes]:
		intentos = 2 if repetir else 1
		for intento in range(intentos):
			conexion = self._conexion(tiempo_s)
			try:
				conexion.request(metodo, ruta, body=cuerpo, headers={"Authorization": self._autorizacion, **cabeceras})
				respuesta = conexion.getresponse()
				datos = respuesta.read()
				if respuesta.getheader("Connection", "").lower() == "close":
					self._cerrar_conexion()
				return respuesta.status, datos
			except (http.client.HTTPException, OSError) as error:
				self._cerrar_conexion()
				if intento + 1 >= intentos:
					raise errores.traducir(error) from error
				log.debug("Conexión con rcd cortada en %s; se repite", ruta)
		raise api.ErrorRed(_texto("No hay conexión con el motor de nubes"))

	def cerrar(self) -> None:
		self._cerrar_conexion()

	# ── Llamadas ───────────────────────────────────────────────────────────

	def llamar(self, ruta: str, *, tiempo_s: float = TIEMPO_LLAMADA_S, **parametros: Any) -> dict:
		"""POST ``/<ruta>`` con los parámetros en JSON. Lanza ``ErrorRC`` si rclone responde con error."""
		cuerpo = json.dumps(parametros).encode("utf-8")
		estado, datos = self._peticion("POST", "/" + ruta, cuerpo, {"Content-Type": "application/json"}, tiempo_s,
			ruta in SOLO_LECTURA)
		return self._respuesta(ruta, estado, datos)

	@staticmethod
	def _respuesta(ruta: str, estado: int, datos: bytes) -> dict:
		try:
			contenido = json.loads(datos.decode("utf-8")) if datos.strip() else {}
		except ValueError:
			contenido = {"error": datos.decode("utf-8", "replace")[:500]}
		if estado >= 400 or (isinstance(contenido, dict) and contenido.get("error") and "status" in contenido):
			texto = str(contenido.get("error", "")) if isinstance(contenido, dict) else str(contenido)
			raise errores.ErrorRC(estado, texto, ruta)
		return contenido if isinstance(contenido, dict) else {"resultado": contenido}

	def llamar_asincrono(self, ruta: str, grupo: str = "", **parametros: Any) -> int:
		"""Lanza ``ruta`` con ``_async`` (y ``_group``) y devuelve el ``jobid``."""
		parametros["_async"] = True
		if grupo:
			parametros["_group"] = grupo
		respuesta = self.llamar(ruta, **parametros)
		with self._candado:
			self.trabajos_lanzados += 1
		return int(respuesta["jobid"])

	def esperar_trabajo(self, jobid: int, grupo: str = "", progreso: Callable[[int, int, float], None] | None = None,
			cancelacion: Any = None, *, intervalo_s: float = 0.25, tiempo_max_s: float = 0) -> dict:
		"""Espera a que termine el trabajo y devuelve su ``output``.

		:param progreso: ``progreso(bytes_hechos, bytes_totales, velocidad)`` desde ``core/stats`` del grupo.
		:raises Cancelado: si se cancela (antes se para el grupo o el trabajo).
		:raises ErrorArchivos: traducido, si el trabajo termina con error.
		"""
		inicio = time.monotonic()
		intervalo_s = max(0.25, intervalo_s)
		while True:
			if _cancelado(cancelacion):
				self.parar(jobid, grupo)
				raise api.Cancelado()
			estado = self.llamar("job/status", jobid=jobid)
			if progreso is not None and grupo:
				try:
					stats = self.llamar("core/stats", group=grupo)
					progreso(int(stats.get("bytes", 0) or 0), int(stats.get("totalBytes", 0) or 0), float(stats.get("speed", 0) or 0))
				except errores.ErrorRC:
					log.debug("Sin estadísticas del grupo %s", grupo, exc_info=True)
			if estado.get("finished"):
				if grupo:
					try:
						self.llamar("core/stats-delete", group=grupo)
					except (errores.ErrorRC, api.ErrorArchivos):
						log.debug("No se pudo borrar el grupo %s", grupo, exc_info=True)
				if not estado.get("success", False):
					texto = str(estado.get("error", "")) or "error"
					salida = estado.get("output") or {}
					raise _ErrorTrabajo(texto, salida if isinstance(salida, dict) else {})
				salida = estado.get("output")
				return salida if isinstance(salida, dict) else {}
			if tiempo_max_s and time.monotonic() - inicio > tiempo_max_s:
				self.parar(jobid, grupo)
				raise api.ErrorRed(_texto("La operación de la nube tarda demasiado; se ha detenido"))
			esperar(cancelacion, intervalo_s)

	def parar(self, jobid: int = 0, grupo: str = "") -> None:
		"""Para un trabajo o un grupo (cancelar no falla si ya terminó)."""
		try:
			if grupo:
				self.llamar("job/stopgroup", group=grupo)
			if jobid:
				self.llamar("job/stop", jobid=jobid)
		except (errores.ErrorRC, api.ErrorArchivos):
			log.debug("No se pudo parar el trabajo %s del grupo %s", jobid, grupo, exc_info=True)

	def ejecutar(self, ruta: str, grupo: str = "", progreso: Callable[[int, int, float], None] | None = None,
			cancelacion: Any = None, **parametros: Any) -> dict:
		"""``llamar_asincrono`` + ``esperar_trabajo``, con los errores ya traducidos."""
		jobid = self.llamar_asincrono(ruta, grupo, **parametros)
		try:
			return self.esperar_trabajo(jobid, grupo, progreso, cancelacion)
		except _ErrorTrabajo as error:
			raise errores.traducir(errores.ErrorRC(500, error.texto, ruta)) from error

	# ── Contenido ──────────────────────────────────────────────────────────

	def _ruta_objeto(self, remoto: str, ruta: str) -> str:
		ruta = ruta.lstrip("/")
		return "/[" + urllib.parse.quote(remoto, safe=":") + "]/" + urllib.parse.quote(ruta, safe="/")

	def abrir_objeto(self, remoto: str, ruta: str, desde: int = 0) -> BinaryIO:
		"""Flujo de lectura de un objeto por ``--rc-serve`` (GET con ``Range``); se reanuda solo si se corta."""
		return FlujoObjeto(self, remoto, ruta, desde)

	def subir(self, remoto: str, carpeta: str, nombre: str, datos: Iterable[bytes] | BinaryIO,
			tiempo_s: float = 24 * 3600) -> None:
		"""``operations/uploadfile`` en flujo (multipart/form-data troceado, sin cargar el archivo en memoria)."""
		frontera = "zcfrontera" + uuid.uuid4().hex
		# RFC 2231: el nombre viaja codificado (comillas, acentos y cualquier carácter llegan intactos).
		nombre_seguro = urllib.parse.quote(nombre, safe="")
		cabecera = (f"--{frontera}\r\nContent-Disposition: form-data; name=\"file0\"; filename*=UTF-8''{nombre_seguro}\r\n"
			"Content-Type: application/octet-stream\r\n\r\n").encode("ascii")
		cola = f"\r\n--{frontera}--\r\n".encode("ascii")
		trozos = _trozos(datos)

		def cuerpo() -> Iterable[bytes]:
			yield cabecera
			yield from trozos
			yield cola

		consulta = urllib.parse.urlencode({"fs": remoto, "remote": carpeta.strip("/")})
		conexion = http.client.HTTPConnection(self.anfitrion, self.puerto, timeout=tiempo_s)
		try:
			conexion.putrequest("POST", f"/operations/uploadfile?{consulta}")
			conexion.putheader("Authorization", self._autorizacion)
			conexion.putheader("Content-Type", f"multipart/form-data; boundary={frontera}")
			conexion.putheader("Transfer-Encoding", "chunked")
			conexion.endheaders()
			for trozo in cuerpo():
				if trozo:
					conexion.send(f"{len(trozo):X}\r\n".encode("ascii") + trozo + b"\r\n")
			conexion.send(b"0\r\n\r\n")
			respuesta = conexion.getresponse()
			self._respuesta("operations/uploadfile", respuesta.status, respuesta.read())
		except (http.client.HTTPException, OSError) as error:
			raise errores.traducir(error, nombre) from error
		finally:
			conexion.close()


class _ErrorTrabajo(Exception):
	def __init__(self, texto: str, salida: dict) -> None:
		super().__init__(texto)
		self.texto = texto
		self.salida = salida


ErrorTrabajo = _ErrorTrabajo


def _trozos(datos: Iterable[bytes] | BinaryIO, tamano: int = 1024 * 1024) -> Iterable[bytes]:
	if hasattr(datos, "read"):
		return iter(lambda: datos.read(tamano), b"")  # type: ignore[union-attr]
	return iter(datos)


def esperar(cancelacion: Any, segundos: float) -> None:
	"""Espera ``segundos`` o hasta la cancelación (sin dormir el hilo sin remedio)."""
	cancelacion = getattr(cancelacion, "token", cancelacion)
	esperar_evento = getattr(cancelacion, "wait", None)
	if callable(esperar_evento):
		esperar_evento(segundos)
	else:
		time.sleep(segundos)


def _texto(texto: str) -> str:
	return api.traduccion("zc_nubes")[0](texto)


class FlujoObjeto(io.RawIOBase):
	"""Lectura en flujo de un objeto por ``--rc-serve``; reanuda con ``Range`` si la conexión se corta."""

	def __init__(self, cliente: ClienteRC, remoto: str, ruta: str, desde: int = 0) -> None:
		super().__init__()
		self._cliente = cliente
		self._ruta = cliente._ruta_objeto(remoto, ruta)
		self._nombre = ruta
		self._posicion = max(0, desde)
		self._conexion: http.client.HTTPConnection | None = None
		self._respuesta: http.client.HTTPResponse | None = None
		self._fin = False

	def readable(self) -> bool:
		return True

	def seekable(self) -> bool:
		return True

	def tell(self) -> int:
		return self._posicion

	def seek(self, desplazamiento: int, desde: int = io.SEEK_SET) -> int:
		if desde == io.SEEK_CUR:
			desplazamiento += self._posicion
		elif desde != io.SEEK_SET:
			raise OSError("seek desde el final no admitido")
		if desplazamiento != self._posicion:
			self._soltar()
			self._posicion = max(0, desplazamiento)
			self._fin = False
		return self._posicion

	def _abrir(self) -> None:
		conexion = http.client.HTTPConnection(self._cliente.anfitrion, self._cliente.puerto, timeout=120)
		cabeceras = {"Authorization": self._cliente._autorizacion}
		if self._posicion:
			cabeceras["Range"] = f"bytes={self._posicion}-"
		conexion.request("GET", self._ruta, headers=cabeceras)
		respuesta = conexion.getresponse()
		if respuesta.status == 416:
			respuesta.read()
			conexion.close()
			self._fin = True
			return
		if respuesta.status >= 400:
			datos = respuesta.read()
			conexion.close()
			texto = datos.decode("utf-8", "replace")
			raise errores.traducir(errores.ErrorRC(respuesta.status, texto, "rc-serve"), self._nombre, self._nombre)
		if self._posicion and respuesta.status != 206:
			# El servidor no respetó el rango: se descarta lo ya leído.
			restante = self._posicion
			while restante > 0:
				bloque = respuesta.read(min(restante, 1024 * 1024))
				if not bloque:
					break
				restante -= len(bloque)
		self._conexion, self._respuesta = conexion, respuesta

	def _soltar(self) -> None:
		if self._conexion is not None:
			try:
				self._conexion.close()
			except OSError:
				log.debug("No se pudo cerrar el flujo de %s", self._nombre, exc_info=True)
		self._conexion = self._respuesta = None

	def readinto(self, destino: Any) -> int:
		if self._fin:
			return 0
		for intento in range(3):
			try:
				if self._respuesta is None:
					self._abrir()
					if self._fin:
						return 0
				leidos = self._respuesta.readinto(destino)  # type: ignore[union-attr]
				if leidos == 0:
					self._fin = True
					self._soltar()
				self._posicion += leidos
				return leidos
			except (http.client.HTTPException, OSError) as error:
				self._soltar()
				if intento == 2:
					raise errores.traducir(error, self._nombre, self._nombre) from error
				log.debug("Flujo de %s cortado; se reanuda en %s", self._nombre, self._posicion)
		return 0

	def close(self) -> None:
		self._soltar()
		super().close()
