# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Simulador DSM: un NAS Synology falso que escucha SOLO en 127.0.0.1 (diseño 2.0, 13.9; synology.md 7).

Responde como el DS220+ real de la persona (catálogo exacto de 841 API, DSM
7.3.2-86009 Update 5, paquetes reales) con datos ficticios coherentes. Sirve
para las pruebas (nunca se toca el NAS real) y como «NAS de demostración».

Modos (synology.md 7.4), con la lista blanca de ``metodos_lectura.py``:

- ``lectura``: las escrituras se rechazan con el error 116.
- ``simular``: las escrituras responden con la forma real, apuntan la llamada en
  el diario (``/__control/diario``) y NO cambian nada.
- ``escritura``: las escrituras cambian el estado en memoria (se pierde al parar).

Uso desde el código::

	simulador = SimuladorDSM(puerto=0, modo="simular")
	url = simulador.iniciar()      # «http://127.0.0.1:53124»
	...
	simulador.parar()

Y como programa (solo para probar a mano con NVDA)::

	python -I plugins/synology/simulador/servidor.py --puerto 55001 --modo simular

Inyección de fallos y escenarios por ``/__control`` (solo desde 127.0.0.1) o
por los atributos ``fallos`` y ``escenario()`` del objeto.
"""

from __future__ import annotations

import json
import logging
import ssl
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

if __name__ == "__main__" and not __package__:
	# Ejecutado como programa: se importa como paquete propio sin pasar por zCommander (y sin sus dependencias).
	import importlib
	import types

	_carpeta = Path(__file__).resolve().parents[1]
	_paquete = types.ModuleType("zc_synology_sim")
	_paquete.__path__ = [str(_carpeta)]  # type: ignore[attr-defined]
	sys.modules["zc_synology_sim"] = _paquete
	sys.exit(importlib.import_module("zc_synology_sim.simulador.servidor").main())

from ..metodos_lectura import es_lectura
from .comun import ErrorSim, Peticion, RespuestaBinaria
from .estado import EstadoNAS
from .manejadores import MANEJADORES

log = logging.getLogger("zc.synology.simulador")

MODOS = ("lectura", "simular", "escritura")
#: Parámetros que nunca se decodifican de JSON ni se guardan en claro.
PARAMETROS_BASE = frozenset({"api", "version", "method", "_sid", "SynoToken"})
SECRETOS = frozenset({"passwd", "password", "otp_code", "device_id", "_sid", "SynoToken", "account", "passphrase",
	"unzip_password", "new_password"})
#: API que un usuario sin privilegios puede usar (las demás dan 105, como en DSM).
API_DE_USUARIO = ("SYNO.API.", "SYNO.Entry.", "SYNO.FileStation.", "SYNO.Finder.", "SYNO.DSM.Info",
	"SYNO.SynologyDrive.Files", "SYNO.Foto.UserInfo", "SYNO.Core.User.PasswordConfirm")


@dataclass
class Fallos:
	"""Fallos inyectables (synology.md 7.3)."""

	latencia_ms: int = 0
	#: Peticiones correctas que quedan antes de dar por caducada la sesión (106) una vez; 0 = nunca.
	caducar_en: int = 0
	#: Inicios de sesión fallidos desde una IP antes del bloqueo (407).
	bloquear_tras: int = 5
	#: Próximas N respuestas con HTTP 502.
	http_502: int = 0
	#: Próximas N respuestas cortadas a la mitad.
	cortar: int = 0
	#: Cada cuántas lecturas de ``SYNO.Core.System.Utilization`` falla con 1055 (0 = nunca).
	error_utilizacion: int = 0


def _redactar(params: dict[str, Any]) -> dict[str, Any]:
	return {k: ("***" if k in SECRETOS else v) for k, v in params.items()}


class SimuladorDSM:
	"""Servidor DSM falso con su estado; ``iniciar()`` lo arranca en un hilo y devuelve la URL."""

	def __init__(self, puerto: int = 0, modo: str = "lectura", https: bool = False, datos: Any = None,
			certificado: tuple[str | Path, str | Path] | None = None, ritmo_tareas: float | None = None) -> None:
		if modo not in MODOS:
			raise ValueError(f"Modo desconocido: {modo}")
		if https and certificado is None:
			raise ValueError("Con https hace falta el certificado (cert, clave)")
		self.puerto = int(puerto)
		self.modo = modo
		self.https = bool(https)
		self.estado = EstadoNAS(datos)
		if ritmo_tareas is not None:
			self.estado.ritmo_tareas = float(ritmo_tareas)
		self.fallos = Fallos()
		self.diario: list[dict[str, Any]] = []
		#: Últimas peticiones recibidas TAL CUAL llegaron (con los secretos tapados): sirven para comprobar la codificación.
		self.peticiones: deque[dict[str, Any]] = deque(maxlen=500)
		self._certificado = certificado
		self._contexto: ssl.SSLContext | None = None
		self._servidor: ThreadingHTTPServer | None = None
		self._hilo: threading.Thread | None = None
		self._lecturas_utilizacion = 0

	# ── Ciclo de vida ────────────────────────────────────────────────────────

	@property
	def url(self) -> str:
		esquema = "https" if self.https else "http"
		return f"{esquema}://127.0.0.1:{self.puerto}"

	@property
	def activo(self) -> bool:
		return self._servidor is not None

	def iniciar(self) -> str:
		if self._servidor is not None:
			return self.url
		servidor = _ServidorHTTP(("127.0.0.1", self.puerto), _ManejadorHTTP)
		servidor.simulador = self  # type: ignore[attr-defined]
		if self.https:
			contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
			contexto.load_cert_chain(str(self._certificado[0]), str(self._certificado[1]))
			servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
			self._contexto = contexto
		self._servidor = servidor
		self.puerto = servidor.server_address[1]
		self._hilo = threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.2},
			name=f"simulador-dsm-{self.puerto}", daemon=True)
		self._hilo.start()
		log.info("Simulador DSM en %s (modo %s)", self.url, self.modo)
		return self.url

	def parar(self) -> None:
		servidor, self._servidor = self._servidor, None
		if servidor is None:
			return
		servidor.shutdown()
		servidor.server_close()
		if self._hilo is not None:
			self._hilo.join(5)
			self._hilo = None
		log.info("Simulador DSM parado (%s)", self.url)

	def __enter__(self) -> SimuladorDSM:
		self.iniciar()
		return self

	def __exit__(self, *_error: object) -> None:
		self.parar()

	def cambiar_certificado(self, cert: str | Path, clave: str | Path) -> None:
		"""Las conexiones nuevas reciben otro certificado (para probar el aviso de huella cambiada)."""
		if self._contexto is None:
			raise RuntimeError("El simulador no usa HTTPS")
		self._contexto.load_cert_chain(str(cert), str(clave))

	def escenario(self, **cambios: Any) -> None:
		"""Escenarios de synology.md 7.6: ``actualizacion``, ``disco_aviso``, ``volumen_degradado``, ``limpieza``, ``ritmo_tareas``."""
		with self.estado.candado:
			datos = self.estado.datos
			if "actualizacion" in cambios:
				datos["actualizacion"]["disponible"] = bool(cambios["actualizacion"])
			if "disco_aviso" in cambios:
				disco = datos["discos"][1]
				disco["smart"], disco["unc"] = ("warning", 3) if cambios["disco_aviso"] else ("normal", 0)
				disco["estado"] = "warning" if cambios["disco_aviso"] else "normal"
			if "volumen_degradado" in cambios:
				estado = "degraded" if cambios["volumen_degradado"] else "normal"
				datos["volumenes"][0]["estado"] = estado
				datos["grupos"][0]["estado"] = estado
			if "limpieza" in cambios:
				datos["volumenes"][0]["limpieza"] = "running" if cambios["limpieza"] else ""
			if "ritmo_tareas" in cambios:
				self.estado.ritmo_tareas = float(cambios["ritmo_tareas"])
			if "temperatura" in cambios:
				datos["sistema"]["temperatura"] = int(cambios["temperatura"])

	# ── Proceso de una petición ──────────────────────────────────────────────

	def procesar(self, api: str, version: Any, metodo: str, crudos: dict[str, str], ip: str, cabeceras: dict[str, str],
			archivo: bytes | None = None, nombre_archivo: str = "") -> Any:
		"""Devuelve el dict de la respuesta JSON o una ``RespuestaBinaria``."""
		self.peticiones.append({"api": api, "version": version, "method": metodo, "params": _redactar(crudos),
			"cabecera_token": bool(cabeceras.get("x-syno-token"))})
		try:
			return {"success": True, "data": self._procesar(api, version, metodo, crudos, ip, cabeceras, archivo, nombre_archivo)}
		except ErrorSim as error:
			cuerpo: dict[str, Any] = {"code": error.codigo}
			if error.errores is not None:
				cuerpo["errors"] = error.errores
			return {"success": False, "error": cuerpo}

	def _procesar(self, api: str, version: Any, metodo: str, crudos: dict[str, str], ip: str, cabeceras: dict[str, str],
			archivo: bytes | None, nombre_archivo: str) -> Any:
		if not api or not metodo or version in (None, ""):
			raise ErrorSim(101)
		sesion = None
		publica = api == "SYNO.API.Info" or (api == "SYNO.API.Auth" and metodo == "login")
		if not publica:
			sesion = self._sesion(crudos, cabeceras, ip, api)
		resultado = self.ejecutar(api, version, metodo, crudos, sesion, ip, archivo, nombre_archivo)
		return resultado

	def ejecutar(self, api: str, version: Any, metodo: str, crudos: dict[str, Any], sesion: Any, ip: str,
			archivo: bytes | None = None, nombre_archivo: str = "", decodificados: bool = False) -> Any:
		"""Valida, aplica el modo y llama al manejador (también lo usa ``SYNO.Entry.Request``)."""
		info = self.estado.catalogo.get(api)
		if info is None:
			raise ErrorSim(102)
		try:
			version_n = int(version)
		except (TypeError, ValueError) as error:
			raise ErrorSim(101) from error
		if not int(info["minVersion"]) <= version_n <= int(info["maxVersion"]):
			raise ErrorSim(104)
		manejador = MANEJADORES.get((api, metodo))
		if manejador is None:
			raise ErrorSim(103)
		params = dict(crudos) if decodificados else self._decodificar(crudos, info)
		if sesion is not None and not sesion.administrador and not api.startswith(API_DE_USUARIO):
			raise ErrorSim(105)
		aplicar = True
		if not es_lectura(api, metodo, params):
			entrada = {"api": api, "method": metodo, "version": version_n, "params": _redactar(
				{k: v for k, v in params.items() if k not in PARAMETROS_BASE}), "modo": self.modo, "momento": time.time()}
			if self.modo == "lectura":
				entrada.update(aplicado=False, resultado="rechazada")
				self.diario.append(entrada)
				raise ErrorSim(116)
			aplicar = self.modo == "escritura"
			entrada.update(aplicado=aplicar, resultado="aplicada" if aplicar else "simulada")
			self.diario.append(entrada)
		peticion = Peticion(api, version_n, metodo, params, self.estado, self, sesion, aplicar, ip, archivo, nombre_archivo)
		with self.estado.candado:
			return manejador(peticion)

	def _decodificar(self, crudos: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
		"""``requestFormat: "JSON"``: cada valor viene codificado en JSON (synology.md 1.2); lo que no lo es se queda como texto."""
		if str(info.get("requestFormat", "")).upper() != "JSON":
			return dict(crudos)
		params: dict[str, Any] = {}
		for clave, valor in crudos.items():
			if clave in PARAMETROS_BASE or not isinstance(valor, str):
				params[clave] = valor
				continue
			try:
				params[clave] = json.loads(valor)
			except ValueError:
				params[clave] = valor
		return params

	def _sesion(self, crudos: dict[str, str], cabeceras: dict[str, str], ip: str, api: str) -> Any:
		sid = crudos.get("_sid") or ""
		sesion = self.estado.sesiones.get(sid)
		if sesion is None:
			raise ErrorSim(119)
		token = cabeceras.get("x-syno-token") or crudos.get("SynoToken") or ""
		if token != sesion.synotoken:
			raise ErrorSim(105)
		if sesion.ip != ip:
			raise ErrorSim(150)
		if self.fallos.caducar_en > 0:
			self.fallos.caducar_en -= 1
			if self.fallos.caducar_en == 0:
				self.estado.sesiones.pop(sid, None)
				raise ErrorSim(106)
		sesion.peticiones += 1
		return sesion

	def contar_lectura_utilizacion(self) -> bool:
		"""Verdadero si esta lectura de ``Utilization`` debe fallar con 1055."""
		self._lecturas_utilizacion += 1
		cada = self.fallos.error_utilizacion
		return bool(cada) and self._lecturas_utilizacion % cada == 0

	# ── /__control ───────────────────────────────────────────────────────────

	def control(self, ruta: str, metodo: str, cuerpo: dict[str, Any]) -> tuple[int, dict[str, Any]]:
		if ruta == "/__control/diario":
			if metodo == "DELETE":
				self.diario.clear()
			return 200, {"diario": list(self.diario)}
		if ruta == "/__control/estado":
			return 200, {"modo": self.modo, "apagado": self.estado.apagado, "reinicios": self.estado.reinicios,
				"sesiones": len(self.estado.sesiones), "fallos": asdict(self.fallos), "entradas": self.estado.contar_entradas()}
		if ruta == "/__control/modo" and metodo == "POST":
			modo = str(cuerpo.get("modo", ""))
			if modo not in MODOS:
				return 400, {"error": f"Modo desconocido: {modo}"}
			self.modo = modo
			return 200, {"modo": modo}
		if ruta == "/__control/fallos" and metodo == "POST":
			for clave, valor in cuerpo.items():
				if hasattr(self.fallos, clave):
					setattr(self.fallos, clave, int(valor))
			return 200, asdict(self.fallos)
		if ruta == "/__control/escenario" and metodo == "POST":
			self.escenario(**cuerpo)
			return 200, {"ok": True}
		if ruta == "/__control/encender" and metodo == "POST":
			self.estado.apagado = False
			return 200, {"ok": True}
		return 404, {"error": "Ruta de control desconocida"}


# ── HTTP ─────────────────────────────────────────────────────────────────────


class _ServidorHTTP(ThreadingHTTPServer):
	daemon_threads = True

	def handle_error(self, request: Any, client_address: Any) -> None:
		"""Un cliente que corta la conexión (o comprueba solo el certificado) no es un fallo del simulador."""
		log.debug("Conexión cortada por %s: %s", client_address, sys.exc_info()[1])


class _ManejadorHTTP(BaseHTTPRequestHandler):
	protocol_version = "HTTP/1.1"
	server_version = "nginx"
	sys_version = ""

	def log_message(self, formato: str, *argumentos: Any) -> None:  # noqa: D102 - sin ruido en la consola
		log.debug("%s %s", self.client_address[0], formato % argumentos)

	@property
	def simulador(self) -> SimuladorDSM:
		return self.server.simulador  # type: ignore[attr-defined]

	def do_GET(self) -> None:  # noqa: N802 - API de http.server
		self._atender()

	def do_POST(self) -> None:  # noqa: N802 - API de http.server
		self._atender()

	def do_DELETE(self) -> None:  # noqa: N802 - API de http.server
		self._atender()

	def _leer_cuerpo(self) -> bytes | None:
		"""El cuerpo completo, o ``None`` si el cliente cortó antes (una subida cancelada no deja nada, como en DSM)."""
		largo = int(self.headers.get("Content-Length") or 0)
		if largo <= 0:
			return b""
		cuerpo = self.rfile.read(largo)
		return cuerpo if len(cuerpo) == largo else None

	def _atender(self) -> None:
		try:
			self._atender_sin_proteger()
		except Exception:  # noqa: BLE001 - un fallo del simulador se registra y responde 500, como un NAS con un error interno
			log.exception("Fallo interno del simulador DSM atendiendo %s", self.path.split("?", 1)[0])
			try:
				self._texto(500, "Internal Server Error")
			except OSError:
				log.debug("No se pudo enviar el error 500", exc_info=True)

	def _atender_sin_proteger(self) -> None:
		simulador = self.simulador
		partes = urlsplit(self.path)
		ip = self.client_address[0]
		cuerpo = self._leer_cuerpo()
		if cuerpo is None:
			log.info("Petición cortada por el cliente: se descarta (%s)", partes.path)
			self.close_connection = True
			return
		if partes.path.startswith("/__control"):
			if ip != "127.0.0.1":
				self._json(403, {"error": "Solo desde 127.0.0.1"})
				return
			try:
				datos = json.loads(cuerpo.decode("utf-8")) if cuerpo else {}
			except ValueError:
				datos = {}
			estado, respuesta = simulador.control(partes.path, self.command, datos if isinstance(datos, dict) else {})
			self._json(estado, respuesta)
			return
		if simulador.estado.apagado:
			# Un NAS apagado no contesta: se corta la conexión sin respuesta.
			self.close_connection = True
			return
		if simulador.fallos.latencia_ms:
			time.sleep(simulador.fallos.latencia_ms / 1000)
		if not partes.path.startswith("/webapi/"):
			self._texto(404, "Not Found")
			return
		if simulador.fallos.http_502 > 0:
			simulador.fallos.http_502 -= 1
			self._texto(502, "<html><body><h1>502 Bad Gateway</h1></body></html>")
			return
		crudos = {k: v[0] for k, v in parse_qs(partes.query, keep_blank_values=True).items()}
		archivo, nombre_archivo = None, ""
		tipo = self.headers.get("Content-Type", "")
		if cuerpo and tipo.startswith("multipart/form-data"):
			campos, archivo, nombre_archivo = _multipart(tipo, cuerpo)
			crudos.update(campos)
		elif cuerpo:
			crudos.update({k: v[0] for k, v in parse_qs(cuerpo.decode("utf-8"), keep_blank_values=True).items()})
		cabeceras = {k.lower(): v for k, v in self.headers.items()}
		respuesta = simulador.procesar(crudos.get("api", ""), crudos.get("version"), crudos.get("method", ""), crudos, ip,
			cabeceras, archivo, nombre_archivo)
		if isinstance(respuesta, dict) and respuesta.get("success") and isinstance(respuesta.get("data"), RespuestaBinaria):
			self._binario(respuesta["data"])
			return
		cortar = simulador.fallos.cortar > 0
		if cortar:
			simulador.fallos.cortar -= 1
		self._json(200, respuesta, cortar=cortar)

	def _json(self, estado: int, datos: Any, cortar: bool = False) -> None:
		cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
		self.send_response(estado)
		self.send_header("Content-Type", 'application/json; charset="UTF-8"')
		self.send_header("Content-Length", str(len(cuerpo)))
		self.end_headers()
		self.wfile.write(cuerpo[: len(cuerpo) // 2] if cortar else cuerpo)
		if cortar:
			self.close_connection = True

	def _texto(self, estado: int, texto: str) -> None:
		cuerpo = texto.encode("utf-8")
		self.send_response(estado)
		self.send_header("Content-Type", "text/html; charset=UTF-8")
		self.send_header("Content-Length", str(len(cuerpo)))
		self.end_headers()
		self.wfile.write(cuerpo)

	def _binario(self, respuesta: RespuestaBinaria) -> None:
		self.send_response(200)
		self.send_header("Content-Type", "application/octet-stream")
		self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(respuesta.nombre)}")
		self.send_header("Content-Length", str(respuesta.tamano))
		self.end_headers()
		try:
			for parte in respuesta.partes:
				self.wfile.write(parte)
		except (ConnectionError, OSError):
			log.debug("El cliente cortó la descarga de %s", respuesta.nombre)
			self.close_connection = True


def _multipart(tipo: str, cuerpo: bytes) -> tuple[dict[str, str], bytes | None, str]:
	"""Campos y archivo de un ``multipart/form-data`` (el módulo ``cgi`` ya no existe en Python 3.13+)."""
	mensaje = BytesParser(policy=policy.HTTP).parsebytes(b"Content-Type: " + tipo.encode("latin-1") + b"\r\n\r\n" + cuerpo)
	campos: dict[str, str] = {}
	archivo, nombre_archivo = None, ""
	for parte in mensaje.iter_parts():
		nombre = parte.get_param("name", header="content-disposition") or ""
		nombre_parte = parte.get_filename()
		datos = parte.get_payload(decode=True) or b""
		if nombre_parte is not None:
			archivo, nombre_archivo = datos, nombre_parte
		else:
			campos[str(nombre)] = datos.decode("utf-8")
	return campos, archivo, nombre_archivo


# ── Programa suelto ──────────────────────────────────────────────────────────


def main(argumentos: list[str] | None = None) -> int:
	import argparse

	analizador = argparse.ArgumentParser(description="Simulador DSM (NAS Synology falso) de zCommander. Escucha solo en 127.0.0.1.")
	analizador.add_argument("--puerto", type=int, default=55001)
	analizador.add_argument("--modo", choices=MODOS, default="lectura")
	analizador.add_argument("--https", action="store_true", help="Con certificado propio (--cert y --clave)")
	analizador.add_argument("--cert", help="Certificado PEM")
	analizador.add_argument("--clave", help="Clave privada PEM")
	analizador.add_argument("--ritmo", type=float, default=0.1, help="Avance de las tareas por segundo (0.1 = 10 %%)")
	opciones = analizador.parse_args(argumentos)
	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
	certificado = (opciones.cert, opciones.clave) if opciones.https else None
	simulador = SimuladorDSM(opciones.puerto, opciones.modo, opciones.https, certificado=certificado, ritmo_tareas=opciones.ritmo)
	url = simulador.iniciar()
	print(f"Simulador DSM en {url} (modo {opciones.modo}). Cuentas de prueba: demo/demo, lectura/lectura, "
		"prueba2fa/prueba2fa con el código 123456. Ctrl+C para parar.", flush=True)
	try:
		while True:
			time.sleep(0.5)
	except KeyboardInterrupt:
		pass
	finally:
		simulador.parar()
	return 0

