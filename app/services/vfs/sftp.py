# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor SFTP con paramiko.

Decisiones:

- paramiko se importa al conectar por primera vez (diseño 13: arranque rápido).
- Cada proveedor tiene un ``Transport`` y un ``SFTPClient`` protegidos por un
  candado reentrante; los flujos de lectura y escritura toman el candado en
  cada bloque, no durante toda la transferencia, así un listado puede
  colarse entre dos bloques de una descarga. Las operaciones del motor usan
  ``clonar()`` (conexión propia).
- La clave del servidor se comprueba con ``data/config/known_hosts`` (formato
  OpenSSH, ``paramiko.HostKeys``). Desconocida o cambiada: se pregunta con
  ``elegir`` mostrando la huella SHA-256; si ha cambiado, el aviso es
  claro y la opción predeterminada es Cancelar (diseño 8.16 y 14).
- Autenticación: clave privada (con su frase guardada o preguntada) y, si no
  hay o el servidor la rechaza, contraseña o «keyboard-interactive».
- Si la conexión se pierde, se reconecta y se reintenta una vez.
"""

from __future__ import annotations

import builtins
import errno
import io
import logging
import os
import socket
import stat as stat_mod
import threading

from app.core import paths
from app.services import conexiones
from app.services.vfs import base, resolver

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ARCHIVO_KNOWN_HOSTS = "known_hosts"
#: Enlaces simbólicos que se resuelven por carpeta (uno a uno, con ``stat``).
MAXIMO_ENLACES_RESUELTOS = 200


def ruta_known_hosts() -> str:
	return str(paths.ruta_configuracion() / ARCHIVO_KNOWN_HOSTS)


def nombre_en_known_hosts(host: str, puerto: int) -> str:
	"""Como OpenSSH: «servidor» con el puerto 22 y «[servidor]:puerto» con otro."""
	return host if int(puerto) == 22 else f"[{host}]:{puerto}"


_candado_known_hosts = threading.Lock()


def _cargar_known_hosts():
	import paramiko

	claves = paramiko.HostKeys()
	ruta = ruta_known_hosts()
	if os.path.isfile(ruta):
		try:
			claves.load(ruta)
		except (OSError, UnicodeDecodeError):
			log.warning("No se pudo leer %s; se trata como vacío", ruta, exc_info=True)
	return claves


def guardar_clave_servidor(host: str, puerto: int, clave) -> None:
	"""Añade o sustituye la clave del servidor en ``known_hosts`` (escritura atómica)."""
	with _candado_known_hosts:
		claves = _cargar_known_hosts()
		claves.add(nombre_en_known_hosts(host, puerto), clave.get_name(), clave)
		ruta = ruta_known_hosts()
		temporal = f"{ruta}.{os.getpid()}-{threading.get_ident()}.tmp"
		try:
			claves.save(temporal)
			os.replace(temporal, ruta)
		except OSError:
			try:
				os.remove(temporal)
			except OSError:
				log.debug("No se pudo borrar %s", temporal, exc_info=True)
			raise
	log.info("Clave del servidor %s recordada en known_hosts", nombre_en_known_hosts(host, puerto))


def convertir_error(error: BaseException, ruta: str = "") -> base.ErrorArchivos:
	"""Traduce errores de paramiko y de SFTP a ``ErrorArchivos`` en español."""
	if isinstance(error, base.ErrorArchivos):
		return error
	import paramiko

	if isinstance(error, paramiko.AuthenticationException):
		return base.ErrorAcceso(_("Usuario o contraseña incorrectos."), ruta)
	if isinstance(error, socket.gaierror):
		return base.ErrorRed(_("No se encuentra el servidor. Revise el nombre."), ruta)
	if isinstance(error, (TimeoutError, socket.timeout)):
		return base.ErrorRed(_("El servidor no responde."), ruta)
	if isinstance(error, ConnectionRefusedError):
		return base.ErrorRed(_("El servidor no responde: rechazó la conexión en ese puerto."), ruta)
	if isinstance(error, FileNotFoundError) or getattr(error, "errno", None) == errno.ENOENT:
		return base.NoEncontrado(_("No existe {r} en el servidor.").format(r=ruta or "?"), ruta)
	if isinstance(error, PermissionError) or getattr(error, "errno", None) == errno.EACCES:
		return base.ErrorAcceso(_("El servidor no le da permiso sobre {r}.").format(r=ruta or "?"), ruta)
	if isinstance(error, (EOFError, ConnectionError, paramiko.SSHException)):
		return base.ErrorRed(_("Se perdió la conexión con el servidor."), ruta)
	if isinstance(error, OSError):
		texto = (error.strerror or str(error) or "").strip()
		if "no space" in texto.lower() or "quota" in texto.lower():
			return base.SinEspacio(_("El servidor no tiene espacio o superó su cuota."), ruta)
		return base.ErrorArchivos(_("El servidor rechazó la operación: {t}").format(t=texto or _("sin detalle")), ruta)
	return base.ErrorArchivos(str(error) or type(error).__name__, ruta)


class ProveedorSFTP(conexiones.ProveedorRemoto):
	"""Servidor SFTP (SSH).

	:param clave_privada: ruta de una clave privada OpenSSH o PEM (opcional).
	:param frase: frase de la clave, si se conoce; ``None`` para buscarla o preguntarla.
	"""

	esquema = "sftp"
	protocolo = "sftp"

	def __init__(self, servidor: str, puerto: int | None = None, usuario: str = "", contrasena: str | None = None,
			carpeta: str = "/", tiempo_espera: float = 30.0, sitio_id: str = "", nombre_sitio: str = "",
			clave_privada: str = "", frase: str | None = None) -> None:
		super().__init__(servidor, puerto, usuario, contrasena, carpeta, tiempo_espera, sitio_id, nombre_sitio)
		self.capacidades = base.Capacidades(escribir=True, papelera=False, atributos=False, enlaces=False, vigilar=False, permisos=True)
		self.clave_privada = clave_privada
		self._frase = frase
		self._frase_preguntada = False
		self._candado = threading.RLock()
		self._transporte = None
		self._sftp = None

	def descripcion(self) -> str:
		return _("Servidor SFTP")

	# Conexión ---------------------------------------------------------------

	def _comprobar_clave_servidor(self, clave) -> None:
		with _candado_known_hosts:
			conocidas = _cargar_known_hosts().lookup(nombre_en_known_hosts(self.host, self.puerto)) or {}
		guardada = conocidas.get(clave.get_name())
		huella_guardada = guardada.fingerprint if guardada is not None else None
		if guardada is None and conocidas:
			# Hay claves de otro tipo para este servidor: puede ser un cambio legítimo o un intruso.
			huella_guardada = next(iter(conocidas.values())).fingerprint
		self.confirmar_huella(_("la clave {t} del servidor").format(t=clave.get_name()), clave.fingerprint, huella_guardada,
			lambda _huella: guardar_clave_servidor(self.host, self.puerto, clave))

	def _obtener_frase(self, preguntar: bool, usar_guardada: bool = True) -> str | None:
		if self._frase is not None:
			return self._frase
		sitio = self._sitio_guardado() if usar_guardada else None
		if sitio is not None and sitio.guardar_contrasena:
			try:
				guardada = self._repositorio().frase(sitio.id)
			except Exception:  # noqa: BLE001 - una frase ilegible se pregunta
				log.warning("No se pudo leer la frase guardada del sitio %s", sitio.nombre, exc_info=True)
				guardada = None
			if guardada:
				self._frase = guardada
				return guardada
		if not preguntar:
			return None
		decisor = self._decisor()
		if decisor is None:
			raise base.ErrorAcceso(_("Hace falta la frase de la clave privada y no se puede preguntar."), "")
		texto = decisor.pedir_texto(_("Frase de la clave privada"),
			_("&Frase de {c}:").format(c=os.path.basename(self.clave_privada)), "", oculto=True)
		if texto is None:
			raise base.ErrorAcceso(_("No se conectó: no se escribió la frase de la clave privada."), "")
		self._frase, self._frase_preguntada = texto, True
		return texto

	def _cargar_clave_privada(self):
		import paramiko

		ruta = os.path.expanduser(self.clave_privada)
		if not os.path.isfile(ruta):
			raise base.NoEncontrado(_("No se encuentra la clave privada {r}.").format(r=ruta), ruta)

		def cargar(frase: str | None):
			# paramiko 5 pide la frase en bytes aunque la anote como str.
			return paramiko.PKey.from_path(ruta, password=frase.encode("utf-8") if frase else None)

		def pide_frase(error: BaseException) -> bool:
			# paramiko 5 deja pasar el TypeError de cryptography en lugar de PasswordRequiredException.
			return isinstance(error, paramiko.PasswordRequiredException) or (
				isinstance(error, TypeError) and "encrypted" in str(error).lower())

		frase = self._obtener_frase(preguntar=False)
		try:
			return cargar(frase)
		except (paramiko.SSHException, ValueError, TypeError) as error:
			if pide_frase(error):
				log.debug("La clave privada %s necesita frase", ruta)
			elif not frase:
				raise base.ErrorAcceso(_("No se pudo leer la clave privada {r}: el formato no se admite.").format(r=ruta), ruta) from error
			else:
				log.info("La frase guardada de la clave privada no vale; se pregunta")
		except OSError as error:
			raise base.ErrorAcceso(_("No se pudo leer la clave privada {r}.").format(r=ruta), ruta) from error
		self._frase = None
		frase = self._obtener_frase(preguntar=True, usar_guardada=False)
		try:
			return cargar(frase)
		except (paramiko.SSHException, ValueError, TypeError) as error:
			self._frase, self._frase_preguntada = None, False
			raise base.ErrorAcceso(_("La frase de la clave privada no es correcta."), ruta) from error

	def _autenticar(self, transporte) -> None:
		import paramiko

		usuario = self.usuario
		if self.clave_privada:
			clave = self._cargar_clave_privada()
			try:
				transporte.auth_publickey(usuario, clave)
				return
			except paramiko.AuthenticationException:
				log.info("El servidor %s rechazó la clave privada de %s; se prueba con contraseña", self.servidor, usuario)
				if transporte.is_authenticated():
					return
		contrasena = self.obtener_contrasena()
		try:
			transporte.auth_password(usuario, contrasena)
		except paramiko.BadAuthenticationType as error:
			if "keyboard-interactive" not in (error.allowed_types or []):
				self.olvidar_contrasena_erronea()
				raise base.ErrorAcceso(_("El servidor no admite contraseña para este usuario (solo {t}).").format(
					t=", ".join(error.allowed_types or [])), "") from error

			def responder(_titulo, _instrucciones, preguntas):
				return [contrasena for _texto, _eco in preguntas]

			try:
				transporte.auth_interactive(usuario, responder)
			except paramiko.AuthenticationException as error_interactivo:
				self.olvidar_contrasena_erronea()
				raise base.ErrorAcceso(_("Usuario o contraseña incorrectos."), "") from error_interactivo
		except paramiko.AuthenticationException as error:
			self.olvidar_contrasena_erronea()
			log.info("Inicio de sesión rechazado en %s para %s", self.servidor, usuario)
			raise base.ErrorAcceso(_("Usuario o contraseña incorrectos."), "") from error

	def _abrir(self):
		"""Conecta, comprueba la clave del servidor, autentica y abre el canal SFTP."""
		import paramiko

		try:
			zocalo = socket.create_connection((self.host, self.puerto), timeout=self.tiempo_espera)
		except OSError as error:
			raise convertir_error(error) from error
		transporte = paramiko.Transport(zocalo)
		transporte.banner_timeout = self.tiempo_espera
		transporte.auth_timeout = self.tiempo_espera
		try:
			transporte.start_client(timeout=self.tiempo_espera)
			self._comprobar_clave_servidor(transporte.get_remote_server_key())
			self._autenticar(transporte)
			cliente = paramiko.SFTPClient.from_transport(transporte)
			if cliente is None:
				raise base.ErrorRed(_("El servidor no ofrece SFTP."), "")
			cliente.get_channel().settimeout(self.tiempo_espera)
		except base.ErrorArchivos:
			transporte.close()
			raise
		except (paramiko.SSHException, OSError, EOFError) as error:
			transporte.close()
			if isinstance(error, paramiko.SSHException) and not isinstance(error, paramiko.AuthenticationException):
				raise base.ErrorRed(_("No se pudo establecer la conexión SSH: {e}").format(e=error), "") from error
			raise convertir_error(error) from error
		log.info("Conectado a %s (sftp)", self.servidor)
		return transporte, cliente

	def _cliente(self):
		if self._sftp is None or self._transporte is None or not self._transporte.is_active():
			self._cerrar_conexion()
			self._transporte, self._sftp = self._abrir()
		return self._sftp

	def _cerrar_conexion(self) -> None:
		cliente, transporte = self._sftp, self._transporte
		self._sftp = self._transporte = None
		for objeto in (cliente, transporte):
			if objeto is not None:
				try:
					objeto.close()
				except Exception:  # noqa: BLE001 - cerrar una conexión rota no debe fallar
					log.debug("Error al cerrar la conexión SFTP", exc_info=True)

	def _ejecutar(self, funcion, ruta: str = ""):
		"""``funcion(cliente)`` con el candado; reconecta y reintenta una vez si la conexión se perdió."""
		import paramiko

		with self._candado:
			for intento in (1, 2):
				ya_conectado = self._transporte is not None and self._transporte.is_active()
				cliente = self._cliente()
				try:
					return funcion(cliente)
				except base.ErrorArchivos:
					raise
				except (paramiko.SSHException, OSError, EOFError) as error:
					perdida = self._transporte is None or not self._transporte.is_active() or \
						isinstance(error, (EOFError, ConnectionError, socket.timeout, TimeoutError))
					if perdida:
						self._cerrar_conexion()
						if intento == 1 and ya_conectado:
							log.info("Se perdió la conexión con %s; se reintenta una vez", self.servidor)
							continue
						raise base.ErrorRed(_("Se perdió la conexión con el servidor; se reintentó una vez sin éxito."), ruta) from error
					raise convertir_error(error, ruta) from error
		raise base.ErrorRed(_("Se perdió la conexión con el servidor."), ruta)  # pragma: no cover

	def conectar(self) -> None:
		self._ejecutar(lambda cliente: None)

	def conectado(self) -> bool:
		return self._transporte is not None and self._transporte.is_active()

	# Navegación -------------------------------------------------------------

	def _entrada(self, carpeta: str, nombre: str, atributos) -> base.Entrada:
		modo = atributos.st_mode or 0
		es_carpeta = stat_mod.S_ISDIR(modo)
		return base.Entrada(
			nombre=nombre, ruta=self.unir(carpeta, nombre), es_carpeta=es_carpeta,
			tamano=-1 if es_carpeta else int(atributos.st_size or 0), modificado=float(atributos.st_mtime or 0),
			permisos=stat_mod.S_IMODE(modo) if modo else -1,
		)

	def listar(self, ruta: str, cancelacion=None) -> list[base.Entrada]:
		ruta = self._comprobar_ruta(ruta)
		base.comprobar(cancelacion)

		def trabajo(cliente):
			atributos = cliente.listdir_attr(ruta)
			resultado = []
			enlaces = 0
			for i, atributo in enumerate(atributos):
				if i % 256 == 0:
					base.comprobar(cancelacion)
				nombre = atributo.filename
				if nombre in (".", ".."):
					continue
				if stat_mod.S_ISLNK(atributo.st_mode or 0):
					# Un enlace se muestra como lo que señala (se sigue con stat).
					enlaces += 1
					if enlaces <= MAXIMO_ENLACES_RESUELTOS:
						try:
							atributo = cliente.stat(self.unir(ruta, nombre))
						except OSError:
							log.debug("Enlace roto %s", nombre, exc_info=True)
				resultado.append(self._entrada(ruta, nombre, atributo))
			return resultado

		entradas = self._ejecutar(trabajo, ruta)
		base.comprobar(cancelacion)
		return entradas

	def info(self, ruta: str) -> base.Entrada:
		ruta = self._comprobar_ruta(ruta)
		atributos = self._ejecutar(lambda cliente: cliente.stat(ruta), ruta)
		if ruta == "/":
			return base.Entrada(nombre="/", ruta="/", es_carpeta=True, modificado=float(atributos.st_mtime or 0))
		return self._entrada(self.padre(ruta) or "/", self.nombre(ruta), atributos)

	# Contenido --------------------------------------------------------------

	def abrir_lectura(self, ruta: str):
		ruta = self._comprobar_ruta(ruta)

		def abrir(cliente):
			archivo = cliente.open(ruta, "rb")
			try:
				archivo.prefetch()
			except Exception:  # noqa: BLE001 - sin lectura anticipada solo va más despacio
				log.debug("Sin lectura anticipada para %s", ruta, exc_info=True)
			return archivo

		return io.BufferedReader(_FlujoSFTP(self, self._ejecutar(abrir, ruta), ruta, escritura=False), 256 * 1024)

	def abrir_escritura(self, ruta: str, tamano: int = -1):
		ruta = self._comprobar_ruta(ruta)

		def abrir(cliente):
			archivo = cliente.open(ruta, "wb")
			archivo.set_pipelined(True)
			return archivo

		return io.BufferedWriter(_FlujoSFTP(self, self._ejecutar(abrir, ruta), ruta, escritura=True), 256 * 1024)

	def crear_carpeta(self, ruta: str) -> None:
		ruta = self._comprobar_ruta(ruta)
		try:
			self._ejecutar(lambda cliente: cliente.mkdir(ruta), ruta)
		except base.ErrorArchivos as error:
			if not isinstance(error, base.ErrorRed) and self.existe(ruta):
				raise base.YaExiste(_("Ya existe una carpeta o archivo con ese nombre."), ruta) from error
			raise

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		ruta = self._comprobar_ruta(ruta)
		if ruta == "/":
			raise base.ErrorAcceso(_("No se puede eliminar la raíz del servidor."), ruta)
		modo = self._ejecutar(lambda cliente: cliente.lstat(ruta), ruta).st_mode or 0
		if stat_mod.S_ISDIR(modo):
			if recursivo:
				nombres = self._ejecutar(lambda cliente: cliente.listdir(ruta), ruta)
				for nombre in nombres:
					base.comprobar(cancelacion)
					self.eliminar(self.unir(ruta, nombre), recursivo=True, cancelacion=cancelacion)
			self._ejecutar(lambda cliente: cliente.rmdir(ruta), ruta)
		else:
			# Un enlace se borra como enlace (remove), nunca lo que señala.
			self._ejecutar(lambda cliente: cliente.remove(ruta), ruta)

	def renombrar(self, origen: str, destino: str) -> None:
		origen, destino = self._comprobar_ruta(origen), self._comprobar_ruta(destino)
		if origen == destino:
			return
		if origen.casefold() != destino.casefold() and self.existe(destino):
			raise base.YaExiste(_("Ya existe «{n}».").format(n=self.nombre(destino)), destino)
		self._ejecutar(lambda cliente: cliente.rename(origen, destino), origen)

	def fijar_tiempos(self, ruta: str, modificado: float, creado: float = 0.0) -> None:
		if not modificado:
			return
		ruta = self._comprobar_ruta(ruta)
		try:
			self._ejecutar(lambda cliente: cliente.utime(ruta, (modificado, modificado)), ruta)
		except base.ErrorArchivos as error:
			if isinstance(error, base.ErrorRed):
				raise
			log.info("El servidor %s no cambió la fecha de %s: %s", self.servidor, ruta, error.mensaje)

	def fijar_permisos(self, ruta: str, modo: int) -> None:
		"""Permisos Unix (``0o644``...). Solo los 12 bits de permisos; el tipo no se toca."""
		ruta = self._comprobar_ruta(ruta)
		self._ejecutar(lambda cliente: cliente.chmod(ruta, int(modo) & 0o7777), ruta)
		log.info("Permisos de %s en %s: %o", ruta, self.servidor, int(modo) & 0o7777)

	# Ciclo de vida -----------------------------------------------------------

	def clonar(self) -> ProveedorSFTP:
		return ProveedorSFTP(self.host, self.puerto, self.usuario, self._contrasena, self.carpeta_inicial, self.tiempo_espera,
			self.sitio_id, self.nombre_sitio, self.clave_privada, self._frase)

	def cerrar(self) -> None:
		"""Suelta la conexión sin esperar a la red (la ventana lo llama desde el hilo de la interfaz)."""
		objetos: tuple = ()
		if self._candado.acquire(blocking=False):
			try:
				objetos = (self._sftp, self._transporte)
				self._sftp = self._transporte = None
			finally:
				self._candado.release()
		elif self._transporte is not None:
			# Otro hilo la está usando: se corta el transporte y ese hilo fallará con «Se perdió la conexión».
			objetos = (self._transporte,)
		if any(o is not None for o in objetos):
			log.info("Desconectado de %s", self.servidor)
			threading.Thread(target=_cerrar_objetos, args=(objetos,), daemon=True, name="sftp-cerrar").start()
		if self._frase_preguntada:
			self._frase, self._frase_preguntada = None, False
		super().cerrar()


def _cerrar_objetos(objetos) -> None:
	for objeto in objetos:
		if objeto is not None:
			try:
				objeto.close()
			except Exception:  # noqa: BLE001 - cerrar una conexión rota no debe fallar
				log.debug("Error al cerrar la conexión SFTP", exc_info=True)


class _FlujoSFTP(io.RawIOBase):
	"""``SFTPFile`` con el candado del proveedor en cada bloque y errores traducidos."""

	def __init__(self, proveedor: ProveedorSFTP, archivo, ruta: str, escritura: bool) -> None:
		super().__init__()
		self._proveedor = proveedor
		self._archivo = archivo
		self._ruta = ruta
		self._escritura = escritura

	def readable(self) -> bool:
		return not self._escritura

	def writable(self) -> bool:
		return self._escritura

	def readinto(self, destino) -> int:
		try:
			with self._proveedor._candado:
				datos = self._archivo.read(len(destino))
		except (OSError, EOFError) as error:
			raise convertir_error(error, self._ruta) from error
		except Exception as error:  # noqa: BLE001 - paramiko lanza SSHException al perder la conexión
			raise convertir_error(error, self._ruta) from error
		destino[: len(datos)] = datos
		return len(datos)

	def write(self, datos) -> int:
		try:
			with self._proveedor._candado:
				self._archivo.write(bytes(datos))
		except Exception as error:  # noqa: BLE001 - paramiko lanza SSHException u OSError
			raise convertir_error(error, self._ruta) from error
		return len(datos)

	def close(self) -> None:
		if self.closed:
			return
		try:
			with self._proveedor._candado:
				self._archivo.close()
		except Exception as error:  # noqa: BLE001 - el cierre confirma la escritura: su fallo importa
			if self._escritura:
				super().close()
				raise convertir_error(error, self._ruta) from error
			log.debug("Error al cerrar la lectura de %s", self._ruta, exc_info=True)
		super().close()


def _fabrica(url: str):
	return conexiones.proveedor_para_url(url)


resolver.registrar_esquema("sftp", _fabrica)
