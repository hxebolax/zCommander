# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor de nubes: un ``rclone rcd`` oculto por sesión (diseño 2.0, 12.2 y 12.3; rclone.md 2 y 6).

Por qué así:

- **Un solo rcd** en ``127.0.0.1``, arrancado bajo demanda, con usuario y
  contraseña aleatorios y NUEVOS en cada intento de arranque, pasados por el
  entorno del hijo (nunca en argumentos, que cualquier proceso puede leer).
- **Puerto** elegido en Python (enlazar a 0, leer y cerrar). Entre cerrar y que
  rclone lo ocupe, otro proceso local podría quedárselo: antes de enviar
  ninguna petición se comprueba con ``GetExtendedTcpTable`` que el dueño del
  socket que escucha es el PID del hijo. Si no, se mata el hijo y se reintenta
  con otro puerto y otras credenciales (3 intentos).
- **Sin ``--log-file``**: el registro de rclone sale por ``stderr`` (una línea
  JSON por mensaje), se redacta y va al registro de zCommander. Nunca hay un
  ``rclone.log`` en disco.
- **Configuración cifrada** (12.3): ``data/config/rclone.conf`` se cifra con
  ``rclone config encryption set`` (contraseña dos veces por la entrada
  estándar) ANTES de la primera cuenta y antes de arrancar rcd con él; la
  contraseña, 32 bytes aleatorios, vive en los secretos DPAPI del complemento.
- **Job Object**: el proceso se lanza con ``procesos.popen`` (Job anidado dentro
  del global de zCommander): si zCommander muere, rclone y sus montajes mueren.

Este módulo no importa wx: lo usan los hilos de trabajo y las pruebas.
"""

from __future__ import annotations

import collections
import ctypes
import datetime
import json
import logging
import os
import secrets
import socket
import struct
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.plugins import api

from . import errores
from .cliente_rc import ClienteRC

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")
log_rclone = logging.getLogger("zcplugins.zc.nubes.rclone")

#: Versión de rclone con la que se probó este complemento (la de la línea base).
VERSION_PROBADA = "1.76.0"
#: Cabecera de un ``rclone.conf`` cifrado (comprobado con rclone 1.76, diseño 21.3).
MARCA_CIFRADO = "# Encrypted rclone configuration File"
INTENTOS_ARRANQUE = 3
ESPERA_PUERTO_S = 10.0
#: Nombre del secreto con la contraseña de ``rclone.conf`` (``plugin:zc.nubes:rclone_config_pass``).
SECRETO_CONFIG = "rclone_config_pass"


@dataclass(frozen=True)
class RutasMotor:
	"""Rutas de ``data`` que usa rclone (todo dentro de la carpeta portable)."""

	config: Path   # data/config/rclone.conf
	cache: Path    # data/cache/rclone
	temp: Path     # data/temp

	@property
	def bisync(self) -> Path:
		return self.cache / "bisync"

	@classmethod
	def desde_anfitrion(cls, datos: Path, cache: Path) -> RutasMotor:
		"""``datos`` es ``data/config/plugins/zc.nubes`` y ``cache`` ``data/cache/plugins/zc.nubes``."""
		config = Path(datos).parents[1]
		cache_raiz = Path(cache).parents[1]
		return cls(config / "rclone.conf", cache_raiz / "rclone", cache_raiz.parent / "temp")


# ── Puerto y dueño del puerto ────────────────────────────────────────────────


def puerto_libre() -> int:
	"""Un puerto libre de 127.0.0.1 (enlazar a 0, leer y cerrar)."""
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as enchufe:
		enchufe.bind(("127.0.0.1", 0))
		return int(enchufe.getsockname()[1])


_ERROR_BUFFER_PEQUENO = 122
_TCP_TABLE_OWNER_PID_LISTENER = 3


def dueno_puerto(puerto: int, direccion: str = "127.0.0.1") -> int | None:
	"""PID del proceso que ESCUCHA en ``direccion:puerto`` (IPv4), según ``GetExtendedTcpTable``; ``None`` si nadie."""
	try:
		iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
	except AttributeError:  # pragma: no cover - fuera de Windows
		return None
	tamano = ctypes.c_ulong(0)
	iphlpapi.GetExtendedTcpTable(None, ctypes.byref(tamano), False, socket.AF_INET, _TCP_TABLE_OWNER_PID_LISTENER, 0)
	tabla = None
	for _intento in range(5):
		tabla = ctypes.create_string_buffer(max(4, tamano.value))
		resultado = iphlpapi.GetExtendedTcpTable(tabla, ctypes.byref(tamano), False, socket.AF_INET,
			_TCP_TABLE_OWNER_PID_LISTENER, 0)
		if resultado == 0:
			break
		if resultado != _ERROR_BUFFER_PEQUENO:
			log.debug("GetExtendedTcpTable devolvió %s", resultado)
			return None
	else:
		return None
	filas = struct.unpack_from("<I", tabla, 0)[0]
	for indice in range(filas):
		_estado, local, puerto_red, _remota, _puerto_remoto, pid = struct.unpack_from("<6I", tabla, 4 + indice * 24)
		if socket.ntohs(puerto_red & 0xFFFF) != puerto:
			continue
		if socket.inet_ntoa(struct.pack("<I", local)) in (direccion, "0.0.0.0"):
			return int(pid)
	return None


# ── Configuración cifrada ────────────────────────────────────────────────────


def estado_configuracion(ruta: Path) -> str:
	"""«vacia», «cifrada» o «sin_cifrar» (con alguna cuenta en claro)."""
	try:
		contenido = ruta.read_text(encoding="utf-8", errors="replace")
	except FileNotFoundError:
		return "vacia"
	if contenido.lstrip().startswith(MARCA_CIFRADO):
		return "cifrada"
	utiles = [linea for linea in contenido.splitlines() if linea.strip() and not linea.lstrip().startswith(("#", ";"))]
	return "sin_cifrar" if utiles else "vacia"


class ConfiguracionCifrada:
	"""Prepara ``rclone.conf`` cifrado y guarda su contraseña en los secretos del complemento (12.3).

	:param ejecutar: ``ejecutar(argumentos, entrada=bytes, tiempo_s=float)`` -> ``ResultadoPrograma``
		(``zc.ejecutar_programa``): proceso sin consola, en el Job Object.
	:param secretos: ``zc.secretos`` (``obtener``, ``guardar``).
	"""

	def __init__(self, ruta: Path, ejecutable: Callable[[], Path], ejecutar: Callable[..., Any], secretos: Any) -> None:
		self.ruta = Path(ruta)
		self._ejecutable = ejecutable
		self._ejecutar = ejecutar
		self._secretos = secretos
		self._candado = threading.Lock()
		#: Aviso pendiente para la persona («cifradas para otro usuario o equipo»), o vacío.
		self.aviso = ""

	def contrasena(self) -> str | None:
		return self._secretos.obtener(SECRETO_CONFIG)

	def asegurar(self) -> str:
		"""Deja ``rclone.conf`` cifrado y devuelve su contraseña. Lanza ``ErrorArchivos`` si no se puede."""
		with self._candado:
			contrasena = self.contrasena()
			estado = estado_configuracion(self.ruta)
			if estado == "cifrada" and not contrasena:
				self._apartar("ilegible")
				self.aviso = _("Las cuentas de nube están cifradas para otro usuario o equipo. Vuelva a añadirlas.")
				log.warning("rclone.conf cifrado sin su contraseña (¿copiado de otro equipo?): se aparta")
				estado = "vacia"
			if estado == "sin_cifrar":
				raise api.ErrorAcceso(_("La configuración de las nubes (rclone.conf) tiene cuentas sin cifrar y no se usa por "
					"seguridad. Apártela o bórrela y vuelva a añadir las cuentas."), str(self.ruta))
			if estado == "cifrada":
				return str(contrasena)
			if not contrasena:
				contrasena = secrets.token_urlsafe(32)
				self._secretos.guardar(SECRETO_CONFIG, contrasena)
			self._cifrar_vacia(contrasena)
			return contrasena

	def _apartar(self, motivo: str) -> None:
		marca = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
		destino = self.ruta.with_name(f"{self.ruta.name}.{motivo}-{marca}")
		try:
			os.replace(self.ruta, destino)
		except OSError as error:
			raise api.ErrorAcceso(_("No se pudo apartar la configuración de las nubes: {e}").format(e=error), str(self.ruta)) from error

	def _cifrar_vacia(self, contrasena: str) -> None:
		"""``rclone config encryption set`` sobre el archivo vacío, con la contraseña dos veces por la entrada estándar."""
		self.ruta.parent.mkdir(parents=True, exist_ok=True)
		self.ruta.write_bytes(b"")
		ejecutable = self._ejecutable()
		entrada = f"{contrasena}\n{contrasena}\n".encode()
		try:
			resultado = self._ejecutar([str(ejecutable), "config", "encryption", "set", "--config", str(self.ruta),
				"--ask-password=true", "--log-level", "ERROR"], entrada=entrada, tiempo_s=60)
		except api.ErrorArchivos:
			self._borrar()
			raise
		if estado_configuracion(self.ruta) != "cifrada":
			log.error("rclone config encryption set no cifró el archivo (código %s): %s", getattr(resultado, "codigo", "?"),
				errores.redactar(bytes(getattr(resultado, "errores", b"")).decode("utf-8", "replace"))[-500:])
			self._borrar()
			raise api.ErrorArchivos(_("No se pudo cifrar la configuración de las nubes; no se ha guardado ninguna cuenta"),
				str(self.ruta))

	def _borrar(self) -> None:
		try:
			self.ruta.unlink()
		except FileNotFoundError:
			pass
		except OSError:
			log.warning("No se pudo borrar %s", self.ruta, exc_info=True)


# ── Motor ────────────────────────────────────────────────────────────────────


class _Reintentar(Exception):
	"""El intento de arranque falló de forma que otro puerto puede arreglarlo."""


class Motor:
	"""Arranca, vigila y para el ``rclone rcd`` de la sesión.

	Todo se inyecta para poder probarlo sin la ventana:

	:param ejecutable: ruta de ``rclone.exe`` pedida EN CADA USO (``zc.componentes``).
	:param configuracion: ``ConfiguracionCifrada`` (prepara el archivo y da la contraseña).
	:param lanzar: ``lanzar(argumentos, entorno) -> Popen`` (``procesos.popen`` con ``stderr`` en tubería).
	:param terminar: ``terminar(proceso)`` (termina su árbol: ``procesos.terminar_arbol``).
	:param opciones: ``opciones() -> dict`` con las globales (transferencias, horario, reintentos, detallado).
	:param al_detenerse: se llama (en un hilo) si el motor muere sin que se le pida.
	:param elegir_puerto: para las pruebas (por defecto ``puerto_libre``).
	"""

	def __init__(self, *, ejecutable: Callable[[], Path], rutas: RutasMotor, configuracion: ConfiguracionCifrada,
			lanzar: Callable[[list[str], dict[str, str]], subprocess.Popen], terminar: Callable[[subprocess.Popen], None],
			opciones: Callable[[], dict[str, Any]] | None = None, al_detenerse: Callable[[], None] | None = None,
			elegir_puerto: Callable[[], int] = puerto_libre, soltar: Callable[[subprocess.Popen], None] | None = None) -> None:
		self._ejecutable = ejecutable
		self.rutas = rutas
		self.configuracion = configuracion
		self._lanzar = lanzar
		self._terminar = terminar
		self._soltar = soltar
		self._opciones = opciones or dict
		self._al_detenerse = al_detenerse
		self._elegir_puerto = elegir_puerto
		self._candado = threading.RLock()
		self._proceso: subprocess.Popen | None = None
		self._cliente: ClienteRC | None = None
		self._parando = False
		self.version = ""
		#: Últimas líneas de rclone (redactadas), para explicar un arranque fallido.
		self.ultimas_lineas: collections.deque[str] = collections.deque(maxlen=50)
		#: Intentos de arranque (puerto, usuario) de esta sesión: las pruebas comprueban que no se repiten.
		self.intentos: list[tuple[int, str]] = []
		#: Opciones con las que se arrancó (para saber si hay que reiniciar al cambiar la configuración).
		self.opciones_arranque: dict[str, Any] = {}

	# Estado -------------------------------------------------------------------

	@property
	def pid(self) -> int | None:
		proceso = self._proceso
		return proceso.pid if proceso is not None and proceso.poll() is None else None

	def vivo(self) -> bool:
		proceso = self._proceso
		return proceso is not None and proceso.poll() is None

	def cliente(self) -> ClienteRC:
		"""Cliente del rcd vivo; lo arranca si hace falta [trabajo]."""
		with self._candado:
			if self.vivo() and self._cliente is not None:
				return self._cliente
			self.arrancar()
			assert self._cliente is not None
			return self._cliente

	def cliente_si_vivo(self) -> ClienteRC | None:
		return self._cliente if self.vivo() else None

	# Arranque -------------------------------------------------------------------

	def _ruta_ejecutable(self) -> Path:
		try:
			return Path(self._ejecutable())
		except api.NoAdmitido as error:
			if "actualiz" in error.mensaje.casefold():
				raise api.ErrorRed(_("El motor de nubes se está actualizando; inténtelo dentro de un momento")) from error
			raise api.ErrorRed(_("El motor de nubes no está disponible: {e}").format(e=error.mensaje)) from error

	def _argumentos(self, ejecutable: Path, puerto: int, opciones: dict[str, Any]) -> list[str]:
		nivel = "INFO" if opciones.get("registro_detallado") else "NOTICE"
		return [str(ejecutable), "rcd", "--rc-addr", f"127.0.0.1:{puerto}", "--rc-serve", "--rc-job-expire-duration", "10m",
			"--rc-server-write-timeout", "24h", "--rc-server-read-timeout", "24h", "--config", str(self.rutas.config),
			"--cache-dir", str(self.rutas.cache), "--temp-dir", str(self.rutas.temp), "--ask-password=false",
			"--log-level", nivel, "--use-json-log"]

	@staticmethod
	def _entorno(usuario: str, clave: str, contrasena_config: str, opciones: dict[str, Any]) -> dict[str, str]:
		# Ninguna variable RCLONE_* de la persona se cuela (otro --config, otra contraseña...).
		entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith("RCLONE_")}
		entorno.update({"RCLONE_RC_USER": usuario, "RCLONE_RC_PASS": clave, "RCLONE_CONFIG_PASS": contrasena_config})
		transferencias = int(opciones.get("transferencias", 4) or 4)
		entorno["RCLONE_TRANSFERS"] = str(max(1, min(32, transferencias)))
		reintentos = int(opciones.get("reintentos", 3))
		entorno["RCLONE_RETRIES"] = str(max(0, min(10, reintentos)) or 1)
		limite = str(opciones.get("bwlimit", "") or "")
		if limite:
			entorno["RCLONE_BWLIMIT"] = limite
		return entorno

	def arrancar(self) -> None:
		"""Arranca rcd (si no está vivo). Lanza ``ErrorRed`` o ``ErrorAcceso`` con el motivo en español."""
		with self._candado:
			if self.vivo() and self._cliente is not None:
				return
			ejecutable = self._ruta_ejecutable()
			contrasena = self.configuracion.asegurar()
			for carpeta in (self.rutas.cache, self.rutas.temp, self.rutas.bisync):
				carpeta.mkdir(parents=True, exist_ok=True)
			opciones = dict(self._opciones())
			for intento in range(1, INTENTOS_ARRANQUE + 1):
				puerto = self._elegir_puerto()
				usuario, clave = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
				self.intentos.append((puerto, usuario))
				proceso = self._lanzar(self._argumentos(ejecutable, puerto, opciones), self._entorno(usuario, clave, contrasena, opciones))
				self._leer_errores(proceso)
				try:
					self._esperar_dueno(proceso, puerto)
					cliente = ClienteRC(puerto, usuario, clave)
					self._comprobar(cliente, proceso)
				except _Reintentar as motivo:
					log.warning("Intento %s de arrancar el motor de nubes fallido: %s", intento, motivo)
					self._matar(proceso)
					continue
				except api.ErrorArchivos:
					self._matar(proceso)
					raise
				self._proceso, self._cliente, self._parando = proceso, cliente, False
				self.opciones_arranque = opciones
				threading.Thread(target=self._vigilar, args=(proceso,), daemon=True, name="zc-nubes-vigilante").start()
				log.info("Motor de nubes arrancado (rclone %s, PID %s)", self.version, proceso.pid)
				return
			detalle = " ".join(list(self.ultimas_lineas)[-3:])
			raise api.ErrorRed(_("No se pudo arrancar el motor de nubes. Detalles en el registro.") +
				(f" ({detalle[:200]})" if detalle else ""))

	def _esperar_dueno(self, proceso: subprocess.Popen, puerto: int) -> None:
		"""Hasta que el hijo escuche en el puerto. Ninguna petición antes de saber que el dueño es el hijo."""
		limite = time.monotonic() + ESPERA_PUERTO_S
		while time.monotonic() < limite:
			if proceso.poll() is not None:
				raise _Reintentar(_("rclone terminó al arrancar (código {c})").format(c=proceso.returncode))
			dueno = dueno_puerto(puerto)
			if dueno is not None:
				if dueno == proceso.pid:
					return
				raise _Reintentar(_("Otro proceso (PID {p}) escucha en el puerto {n}").format(p=dueno, n=puerto))
			time.sleep(0.05)
		raise _Reintentar(_("rclone no escuchó en el puerto {n} en {s} s").format(n=puerto, s=int(ESPERA_PUERTO_S)))

	def _comprobar(self, cliente: ClienteRC, proceso: subprocess.Popen) -> None:
		"""``core/pid`` (el mismo PID), ``core/version``, ``config/paths`` y que la configuración se descifre."""
		try:
			pid = int(cliente.llamar("core/pid").get("pid", -1))
		except (errores.ErrorRC, api.ErrorArchivos) as error:
			raise _Reintentar(str(error)) from error
		if pid != proceso.pid:
			raise _Reintentar(_("core/pid devolvió {a} y el hijo es {b}").format(a=pid, b=proceso.pid))
		try:
			version = str(cliente.llamar("core/version").get("version", ""))
			self.version = version.lstrip("v")
			if self.version != VERSION_PROBADA:
				log.warning("rclone %s no es la versión probada (%s)", self.version, VERSION_PROBADA)
			rutas = cliente.llamar("config/paths")
			if Path(str(rutas.get("config", ""))).resolve() != self.rutas.config.resolve():
				log.warning("rclone usa otra configuración: %s", rutas.get("config"))
			cliente.llamar("config/listremotes")
		except errores.ErrorRC as error:
			raise errores.traducir(error) from error

	def _leer_errores(self, proceso: subprocess.Popen) -> None:
		"""Pasa al registro lo que rclone escribe en ``stderr`` (JSON por línea), redactado."""
		flujo = proceso.stderr
		if flujo is None:
			return

		def leer() -> None:
			niveles = {"debug": logging.DEBUG, "info": logging.INFO, "notice": logging.INFO, "warning": logging.WARNING,
				"error": logging.WARNING, "critical": logging.ERROR, "alert": logging.ERROR, "emergency": logging.ERROR}
			try:
				for bruta in iter(flujo.readline, b""):
					texto = bruta.decode("utf-8", "replace").strip()
					if not texto:
						continue
					try:
						datos = json.loads(texto)
						nivel = niveles.get(str(datos.get("level", "notice")).lower(), logging.INFO)
						mensaje = str(datos.get("msg", "")).strip()
						objeto = datos.get("object")
						if objeto:
							mensaje = f"{objeto}: {mensaje}"
					except (ValueError, AttributeError):
						nivel, mensaje = logging.INFO, texto
					limpio = errores.redactar(mensaje)
					self.ultimas_lineas.append(limpio)
					log_rclone.log(nivel, "%s", limpio)
			except (OSError, ValueError):
				log.debug("Se cerró la salida de errores de rclone", exc_info=True)

		threading.Thread(target=leer, daemon=True, name="zc-nubes-stderr").start()

	def _vigilar(self, proceso: subprocess.Popen) -> None:
		proceso.wait()
		with self._candado:
			esperado = self._parando or self._proceso is not proceso
			if self._proceso is proceso:
				self._cliente = None
		if self._soltar is not None:
			try:
				self._soltar(proceso)
			except Exception:  # noqa: BLE001 - liberar el Job nunca impide seguir
				log.debug("No se pudo soltar el Job de rclone", exc_info=True)
		if not esperado:
			log.error("El motor de nubes se ha detenido (código %s)", proceso.returncode)
			if self._al_detenerse is not None:
				try:
					self._al_detenerse()
				except Exception:  # noqa: BLE001 - el aviso nunca rompe el vigilante
					log.warning("Falló el aviso de motor detenido", exc_info=True)

	def _matar(self, proceso: subprocess.Popen) -> None:
		try:
			self._terminar(proceso)
		except Exception:  # noqa: BLE001 - si ya no existe, mejor
			log.debug("No se pudo terminar rclone", exc_info=True)
		try:
			proceso.wait(5)
		except subprocess.TimeoutExpired:
			log.warning("rclone (PID %s) no terminó a tiempo", proceso.pid)
		if self._soltar is not None:
			try:
				self._soltar(proceso)
			except Exception:  # noqa: BLE001
				log.debug("No se pudo soltar el Job de rclone", exc_info=True)

	# Parada -------------------------------------------------------------------

	def hay_trabajo(self) -> bool:
		"""Transferencias en marcha o unidades montadas (no se puede parar sin perder nada)."""
		cliente = self.cliente_si_vivo()
		if cliente is None:
			return False
		try:
			# Cada llamada al API es un trabajo: la propia consulta de job/list sale entre los que corren.
			if len(cliente.llamar("job/list", tiempo_s=3).get("runningIds") or []) > 1:
				return True
			if cliente.llamar("mount/listmounts", tiempo_s=3).get("mountPoints"):
				return True
		except (errores.ErrorRC, api.ErrorArchivos):
			log.debug("No se pudo consultar el trabajo de rclone", exc_info=True)
		return False

	def detener(self, espera_s: float = 5.0) -> None:
		"""Desmonta, deja de servir y cierra rcd; si no responde en ``espera_s``, termina el proceso."""
		with self._candado:
			proceso, cliente = self._proceso, self._cliente
			self._parando = True
			self._cliente = None
		if proceso is None:
			return
		if proceso.poll() is None and cliente is not None:
			limite = time.monotonic() + espera_s
			for ruta in ("mount/unmountall", "serve/stopall", "core/quit"):
				restante = max(0.5, limite - time.monotonic())
				try:
					cliente.llamar(ruta, tiempo_s=restante)
				except (errores.ErrorRC, api.ErrorArchivos):
					log.debug("rclone no respondió a %s", ruta, exc_info=True)
			cliente.cerrar()
			try:
				proceso.wait(max(0.5, limite - time.monotonic()))
			except subprocess.TimeoutExpired:
				log.warning("rclone no se cerró en %s s; se termina", espera_s)
		if proceso.poll() is None:
			self._matar(proceso)
		with self._candado:
			if self._proceso is proceso:
				self._proceso = None

	def reiniciar(self) -> None:
		"""Para y vuelve a arrancar (al cambiar las transferencias o el horario de límites)."""
		self.detener()
		self.arrancar()
