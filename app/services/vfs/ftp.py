# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor FTP y FTPS (TLS explícito) con ``ftplib``.

Decisiones:

- ``ftplib.FTP`` no es seguro entre hilos y su conexión de control solo hace
  una cosa a la vez: cada proveedor tiene UNA conexión principal protegida
  por un candado. Un flujo de lectura o escritura abierto la ocupa hasta que
  se cierra. Si el mismo hilo (copiar dentro del mismo servidor) u otro hilo
  necesita el servidor mientras tanto, se abre una conexión aparte de un solo
  uso en vez de esperar: así nunca hay bloqueos mutuos.
- Las operaciones del motor usan ``clonar()``, que da otro proveedor con su
  propia conexión: una descarga larga no bloquea la navegación del panel.
- Listar usa MLSD (fechas en UTC, tipos fiables); si el servidor no lo
  entiende, LIST con un intérprete de los formatos Unix y DOS.
- Si la conexión se pierde a mitad de una orden, se reconecta y se reintenta
  UNA vez (diseño 8.16); si vuelve a fallar, «Se perdió la conexión».
- FTPS: el certificado se fija por su huella SHA-256 (la primera vez se
  pregunta; diseño 8.16 y 14), porque muchos servidores FTPS usan
  certificados propios que ninguna autoridad firma. La conexión de datos
  también va cifrada (``PROT P``) y reutiliza la sesión TLS, que muchos
  servidores (vsftpd, FileZilla Server) exigen.
- FTP sin TLS con usuario y contraseña: se avisa la primera vez por sitio de
  que viajan en claro (confirmación ``ftp_sin_cifrar`` de ``general.no_preguntar``, 2.0 10.12).
"""

from __future__ import annotations

import builtins
import calendar
import ftplib
import io
import logging
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field

from app.services import conexiones
from app.services.vfs import base, resolver

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Segundos que se espera a la conexión principal antes de abrir una aparte.
ESPERA_CONEXION_PRINCIPAL = 2.0
#: Enlaces simbólicos de LIST que se resuelven por carpeta como mucho (uno a uno, con CWD).
MAXIMO_ENLACES_RESUELTOS = 64

_MESES = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


# ── Errores ──────────────────────────────────────────────────────────────────


def _codigo(error: BaseException) -> str:
	return str(error)[:3]


def convertir_error(error: BaseException, ruta: str = "") -> base.ErrorArchivos:
	"""Traduce errores de ``ftplib``, de sockets y de TLS a ``ErrorArchivos`` con mensaje en español."""
	if isinstance(error, base.ErrorArchivos):
		return error
	texto = str(error).strip()
	if isinstance(error, ftplib.error_perm):
		codigo = _codigo(error)
		if codigo == "530":
			return base.ErrorAcceso(_("Usuario o contraseña incorrectos."), ruta)
		if codigo == "550":
			minusculas = texto.lower()
			if any(p in minusculas for p in ("not found", "no such", "no existe", "doesn't exist", "does not exist", "not exist")):
				return base.NoEncontrado(_("No existe {r} en el servidor.").format(r=ruta or "?"), ruta)
			return base.ErrorAcceso(_("El servidor no permite esta operación sobre {r} ({t}).").format(r=ruta or "?", t=texto), ruta)
		if codigo == "553":
			return base.NombreNoValido(_("El servidor no admite ese nombre ({t}).").format(t=texto), ruta)
		if codigo == "552":
			return base.SinEspacio(_("El servidor no tiene espacio o superó su cuota ({t}).").format(t=texto), ruta)
		if codigo in ("500", "501", "502", "504"):
			return base.NoAdmitido(_("El servidor no admite esta orden ({t}).").format(t=texto), ruta)
		if codigo == "532":
			return base.ErrorAcceso(_("El servidor pide una cuenta para guardar archivos."), ruta)
		return base.ErrorArchivos(_("El servidor respondió: {t}").format(t=texto), ruta)
	if isinstance(error, ftplib.error_temp):
		codigo = _codigo(error)
		if codigo == "421":
			return base.ErrorRed(_("El servidor cerró la conexión ({t}).").format(t=texto), ruta)
		if codigo in ("425", "426"):
			return base.ErrorRed(_("Falló la conexión de datos. Pruebe a cambiar el modo pasivo del sitio."), ruta)
		if codigo == "450":
			return base.ErrorAcceso(_("El archivo no está disponible ahora (quizá está en uso)."), ruta)
		if codigo == "452":
			return base.SinEspacio(_("El servidor no tiene espacio suficiente."), ruta)
		return base.ErrorRed(_("El servidor tiene un problema pasajero: {t}").format(t=texto), ruta)
	if isinstance(error, (ftplib.error_reply, ftplib.error_proto)):
		return base.ErrorRed(_("El servidor dio una respuesta inesperada: {t}").format(t=texto), ruta)
	if isinstance(error, socket.gaierror):
		return base.ErrorRed(_("No se encuentra el servidor. Revise el nombre."), ruta)
	if isinstance(error, (TimeoutError, socket.timeout)):
		return base.ErrorRed(_("El servidor no responde."), ruta)
	if isinstance(error, ConnectionRefusedError):
		return base.ErrorRed(_("El servidor no responde: rechazó la conexión en ese puerto."), ruta)
	if isinstance(error, ssl.SSLError):
		return base.ErrorRed(_("Falló la conexión segura (TLS): {t}").format(t=texto), ruta)
	if isinstance(error, (ConnectionError, EOFError)):
		return base.ErrorRed(_("Se perdió la conexión con el servidor."), ruta)
	if isinstance(error, OSError):
		return base.ErrorRed(_("Error de red: {t}").format(t=error.strerror or texto), ruta)
	return base.ErrorArchivos(texto or type(error).__name__, ruta)


def _es_conexion_perdida(error: BaseException) -> bool:
	"""Fallos tras los que la conexión de control ya no sirve (se reconecta y se reintenta una vez)."""
	if isinstance(error, ftplib.error_temp) and _codigo(error) == "421":
		return True
	if isinstance(error, (ftplib.error_perm, ftplib.error_temp, ftplib.error_reply, ftplib.error_proto)):
		return False
	return isinstance(error, (EOFError, ConnectionError, TimeoutError, socket.timeout, ssl.SSLError, OSError))


# ── Listados ─────────────────────────────────────────────────────────────────


def _fecha_mlsd(valor: str) -> float:
	"""«20240131235959[.123]» en UTC → marca de tiempo."""
	try:
		principal, _sep, fraccion = valor.partition(".")
		estructura = time.strptime(principal[:14], "%Y%m%d%H%M%S")
		return calendar.timegm(estructura) + (float("0." + fraccion) if fraccion.isdigit() else 0.0)
	except (ValueError, OverflowError):
		return 0.0


@dataclass
class _Fila:
	"""Una línea de listado interpretada."""

	nombre: str
	tipo: str  # «archivo», «carpeta», «enlace»
	tamano: int = -1
	modificado: float = 0.0
	destino: str = ""
	extra: dict = field(default_factory=dict)


def analizar_mlsd(linea: str) -> _Fila | None:
	"""``type=file;size=12;modify=20240101120000; nombre`` → fila (``None`` para «.» y «..»)."""
	hechos_texto, separador, nombre = linea.partition(" ")
	if not separador or not nombre:
		return None
	hechos: dict[str, str] = {}
	for hecho in hechos_texto.split(";"):
		if "=" in hecho:
			clave, _igual, valor = hecho.partition("=")
			hechos[clave.strip().lower()] = valor
	tipo_bruto = hechos.get("type", "file").lower()
	if tipo_bruto in ("cdir", "pdir") or nombre in (".", ".."):
		return None
	if tipo_bruto == "dir":
		tipo = "carpeta"
	elif "slink" in tipo_bruto or "symlink" in tipo_bruto:
		tipo = "enlace"
	else:
		tipo = "archivo"
	try:
		tamano = int(hechos.get("size", hechos.get("sizd", "-1")))
	except ValueError:
		tamano = -1
	destino = tipo_bruto.split(":", 1)[1] if tipo == "enlace" and ":" in tipo_bruto else ""
	return _Fila(nombre, tipo, tamano if tipo == "archivo" else -1, _fecha_mlsd(hechos.get("modify", "")), destino, hechos)


_UNIX = re.compile(
	r"^(?P<tipo>[\-dlbcps])[\-rwxsStTlL+.@]{9}\S*\s+\d+\s+\S+(?:\s+\S+)?\s+(?P<tamano>\d+)\s+"
	r"(?P<mes>[A-Za-z]{3})\s+(?P<dia>\d{1,2})\s+(?P<hora>\d{1,2}:\d{2}|\d{4})\s(?P<nombre>.+)$"
)
_DOS = re.compile(
	r"^(?P<mes>\d{2})-(?P<dia>\d{2})-(?P<anio>\d{2,4})\s+(?P<h>\d{1,2}):(?P<m>\d{2})\s*(?P<ampm>[AaPp][Mm])?\s+"
	r"(?P<tamano><DIR>|\d+)\s+(?P<nombre>.+)$"
)


def _fecha_unix(mes: str, dia: str, hora: str, ahora: float | None = None) -> float:
	"""Fecha de LIST («Jan 31 12:00» o «Jan 31 2020»). Sin zona horaria conocida: se toma como UTC."""
	numero = _MESES.get(mes.lower())
	if numero is None:
		return 0.0
	try:
		if ":" in hora:
			horas, minutos = (int(x) for x in hora.split(":"))
			actual = time.gmtime(ahora if ahora is not None else time.time())
			anio = actual.tm_year
			marca = calendar.timegm((anio, numero, int(dia), horas, minutos, 0, 0, 0, 0))
			# Sin año, la fecha es de los últimos 12 meses: si cae en el futuro, era del año pasado.
			if marca > (ahora if ahora is not None else time.time()) + 86400:
				marca = calendar.timegm((anio - 1, numero, int(dia), horas, minutos, 0, 0, 0, 0))
			return float(marca)
		return float(calendar.timegm((int(hora), numero, int(dia), 0, 0, 0, 0, 0, 0)))
	except (ValueError, OverflowError):
		return 0.0


def analizar_list(linea: str, ahora: float | None = None) -> _Fila | None:
	"""Una línea de LIST en formato Unix (``ls -l``) o DOS/IIS. ``None`` si no se entiende o es «.»/«..»."""
	linea = linea.rstrip("\r\n")
	if not linea or linea.lower().startswith("total "):
		return None
	coincidencia = _UNIX.match(linea)
	if coincidencia:
		nombre = coincidencia["nombre"]
		tipo = {"d": "carpeta", "l": "enlace"}.get(coincidencia["tipo"], "archivo")
		destino = ""
		if tipo == "enlace" and " -> " in nombre:
			nombre, destino = nombre.split(" -> ", 1)
		if nombre in (".", ".."):
			return None
		tamano = int(coincidencia["tamano"]) if tipo == "archivo" else -1
		return _Fila(nombre, tipo, tamano, _fecha_unix(coincidencia["mes"], coincidencia["dia"], coincidencia["hora"], ahora), destino)
	coincidencia = _DOS.match(linea)
	if coincidencia:
		nombre = coincidencia["nombre"]
		if nombre in (".", ".."):
			return None
		anio = int(coincidencia["anio"])
		if anio < 100:
			anio += 2000 if anio < 70 else 1900
		hora = int(coincidencia["h"]) % 12 if coincidencia["ampm"] else int(coincidencia["h"])
		if coincidencia["ampm"] and coincidencia["ampm"].lower() == "pm":
			hora += 12
		try:
			marca = float(calendar.timegm((anio, int(coincidencia["mes"]), int(coincidencia["dia"]), hora, int(coincidencia["m"]), 0, 0, 0, 0)))
		except (ValueError, OverflowError):
			marca = 0.0
		es_carpeta = coincidencia["tamano"].upper() == "<DIR>"
		return _Fila(nombre, "carpeta" if es_carpeta else "archivo", -1 if es_carpeta else int(coincidencia["tamano"]), marca)
	return None


# ── Conexión ─────────────────────────────────────────────────────────────────


class _FTPTLS(ftplib.FTP_TLS):
	"""``FTP_TLS`` que reutiliza la sesión TLS de control en la conexión de datos.

	Muchos servidores rechazan una conexión de datos que no reanuda la sesión
	de la de control (protección contra robo de la conexión de datos).
	"""

	def ntransfercmd(self, cmd, rest=None):  # noqa: D102 - API de ftplib
		conexion, tamano = ftplib.FTP.ntransfercmd(self, cmd, rest)
		if self._prot_p:
			conexion = self.context.wrap_socket(conexion, server_hostname=self.host, session=self.sock.session)
		return conexion, tamano


class _Conexion:
	"""Una conexión de control ya autenticada y lo que se sabe del servidor."""

	def __init__(self, ftp: ftplib.FTP, caracteristicas: set[str]) -> None:
		self.ftp = ftp
		self.mlsd: bool | None = None if "MLST" in caracteristicas else False
		self.mlst = "MLST" in caracteristicas
		self.mfmt = "MFMT" in caracteristicas
		self.rota = False

	def cerrar(self) -> None:
		try:
			self.ftp.close()
		except OSError:
			log.debug("Error al cerrar una conexión FTP", exc_info=True)


class ProveedorFTP(conexiones.ProveedorRemoto):
	"""Servidor FTP o FTPS.

	:param tls: TLS explícito (``AUTH TLS``; protocolo «ftps»).
	:param pasivo: modo pasivo (lo normal detrás de un router o un cortafuegos).
	:param codificacion: «utf-8» o «latin-1» para los nombres.
	"""

	esquema = "ftp"

	def __init__(self, servidor: str, puerto: int | None = None, usuario: str = "", contrasena: str | None = None,
			tls: bool = False, pasivo: bool = True, codificacion: str = "utf-8", carpeta: str = "/",
			tiempo_espera: float = 30.0, sitio_id: str = "", nombre_sitio: str = "") -> None:
		self.protocolo = "ftps" if tls else "ftp"
		super().__init__(servidor, puerto, usuario, contrasena, carpeta, tiempo_espera, sitio_id, nombre_sitio)
		self.tls = tls
		self.pasivo = pasivo
		self.codificacion = codificacion if codificacion in conexiones.CODIFICACIONES else "utf-8"
		self._principal: _Conexion | None = None
		self._candado = threading.Lock()
		self._duenno: int | None = None
		self._aviso_hecho = False

	def descripcion(self) -> str:
		return _("Servidor FTPS") if self.tls else _("Servidor FTP")

	# Conexiones ---------------------------------------------------------------

	def _nueva_conexion(self) -> _Conexion:
		"""Conecta, verifica, autentica y prepara una conexión de control nueva."""
		if self.tls:
			contexto = ssl.create_default_context()
			# La identidad se comprueba fijando la huella (se pregunta la primera vez), no por autoridad.
			contexto.check_hostname = False
			contexto.verify_mode = ssl.CERT_NONE
			ftp: ftplib.FTP = _FTPTLS(context=contexto, encoding=self.codificacion, timeout=self.tiempo_espera)
		else:
			ftp = ftplib.FTP(encoding=self.codificacion, timeout=self.tiempo_espera)
		try:
			ftp.connect(self.host, self.puerto, timeout=self.tiempo_espera)
			if self.tls:
				ftp.auth()
				certificado = ftp.sock.getpeercert(binary_form=True) or b""
				self.confirmar_huella(_("su certificado"), conexiones.huella_sha256(certificado),
					conexiones.huella_tls_guardada(self.servidor), lambda h: conexiones.guardar_huella_tls(self.servidor, h))
			else:
				self._avisar_sin_cifrar()
			contrasena = self.obtener_contrasena()
			usuario = self.usuario.strip() or "anonymous"
			try:
				ftp.login(usuario, contrasena if (contrasena or not self.anonimo) else "anonymous@")
			except ftplib.error_perm as error:
				if _codigo(error) in ("530", "331", "332"):
					self.olvidar_contrasena_erronea()
					log.info("Inicio de sesión rechazado en %s para %s", self.servidor, usuario)
					raise base.ErrorAcceso(_("Usuario o contraseña incorrectos."), "") from error
				raise
			if self.tls:
				ftp.prot_p()
			ftp.set_pasv(self.pasivo)
			caracteristicas = self._caracteristicas(ftp)
			if self.codificacion == "utf-8" and "UTF8" in caracteristicas:
				try:
					ftp.sendcmd("OPTS UTF8 ON")
				except ftplib.Error:
					log.debug("El servidor no acepta OPTS UTF8 ON", exc_info=True)
			ftp.voidcmd("TYPE I")
		except base.ErrorArchivos:
			_cerrar_silencioso(ftp)
			raise
		except (ftplib.Error, OSError, EOFError) as error:
			_cerrar_silencioso(ftp)
			raise convertir_error(error) from error
		log.info("Conectado a %s (%s, %s)", self.servidor, self.protocolo, "pasivo" if self.pasivo else "activo")
		return _Conexion(ftp, caracteristicas)

	@staticmethod
	def _caracteristicas(ftp: ftplib.FTP) -> set[str]:
		try:
			respuesta = ftp.sendcmd("FEAT")
		except ftplib.Error:
			return set()
		resultado = set()
		for linea in respuesta.splitlines()[1:]:
			palabra = linea.strip().split(" ", 1)[0].upper()
			if palabra and not palabra[0].isdigit():
				resultado.add(palabra)
		return resultado

	def _avisar_sin_cifrar(self) -> None:
		"""Aviso de que usuario y contraseña viajan en claro (una vez por sitio, o por sesión sin sitio)."""
		if self.anonimo or self._aviso_hecho:
			return
		sitio = self._sitio_guardado()
		# 2.0 (10.12): confirmación silenciable por sitio (o por servidor sin sitio guardado);
		# silenciar «ftp_sin_cifrar» vale para todos (lo que hacía ftp.avisar_sin_cifrar).
		from app.services import confirmaciones
		from app.services.vfs import resolver

		config = resolver.servicios().config
		clave = f"ftp_sin_cifrar:{sitio.id}" if sitio is not None else f"ftp_sin_cifrar:{self.servidor}"
		if config is not None and not confirmaciones.debe_preguntar(config, clave):
			return
		if sitio is not None and sitio.aviso_sin_cifrar_mostrado:
			return
		if sitio is None and conexiones.huella_aceptada_en_sesion(f"sincifrar:{self.servidor}"):
			return
		decisor = self._decisor()
		if decisor is None:
			log.warning("FTP sin cifrar con %s: no hay a quién avisar", self.servidor)
			return
		texto = _(
			"El sitio {s} usa FTP sin cifrar: el usuario, la contraseña y los archivos viajan en claro y "
			"cualquiera en la misma red puede leerlos.\n\nSi el servidor lo admite, use FTP con TLS (FTPS) o SFTP. "
			"Este aviso no se repetirá para este sitio."
		).format(s=self.servidor)
		if decisor.elegir(_("Conexión sin cifrar"), texto, [_("C&onectar igualmente"), _("&Cancelar")], 0, 1) != 0:
			raise base.ErrorAcceso(_("No se conectó a {s}.").format(s=self.servidor), "")
		self._aviso_hecho = True
		if sitio is not None:
			try:
				self._repositorio().marcar_aviso_sin_cifrar(sitio.id)
			except OSError:
				log.warning("No se pudo recordar el aviso de FTP sin cifrar", exc_info=True)
		else:
			conexiones.aceptar_en_sesion(f"sincifrar:{self.servidor}", "visto")

	def _tomar(self) -> tuple[_Conexion, bool]:
		"""(conexión, es_aparte). La principal queda ocupada hasta ``_devolver``."""
		ident = threading.get_ident()
		if self._duenno != ident and self._candado.acquire(timeout=ESPERA_CONEXION_PRINCIPAL):
			self._duenno = ident
			try:
				if self._principal is None or self._principal.rota:
					if self._principal is not None:
						self._principal.cerrar()
					self._principal = None
					self._principal = self._nueva_conexion()
				return self._principal, False
			except BaseException:
				self._duenno = None
				self._candado.release()
				raise
		log.debug("Conexión principal de %s ocupada: se abre una aparte", self.servidor)
		return self._nueva_conexion(), True

	def _devolver(self, conexion: _Conexion, aparte: bool) -> None:
		if aparte:
			try:
				conexion.ftp.quit()
			except (ftplib.Error, OSError, EOFError):
				log.debug("Cierre de una conexión aparte", exc_info=True)
			conexion.cerrar()
			return
		if conexion.rota:
			conexion.cerrar()
			if self._principal is conexion:
				self._principal = None
		self._duenno = None
		self._candado.release()

	def _ejecutar(self, funcion, ruta: str = ""):
		"""Ejecuta ``funcion(conexion)`` con la conexión; reconecta y reintenta una vez si se perdió."""
		for intento in (1, 2):
			ya_conectada = self._principal is not None and not self._principal.rota
			conexion, aparte = self._tomar()
			try:
				return funcion(conexion)
			except base.ErrorArchivos:
				raise
			except (ftplib.Error, OSError, EOFError) as error:
				if _es_conexion_perdida(error):
					conexion.rota = True
					if intento == 1 and ya_conectada and not aparte:
						log.info("Se perdió la conexión con %s; se reintenta una vez", self.servidor)
						continue
					raise base.ErrorRed(_("Se perdió la conexión con el servidor; se reintentó una vez sin éxito."), ruta) from error
				raise convertir_error(error, ruta) from error
			finally:
				self._devolver(conexion, aparte)
		raise base.ErrorRed(_("Se perdió la conexión con el servidor."), ruta)  # pragma: no cover - el bucle siempre devuelve o lanza

	def conectar(self) -> None:
		self._ejecutar(lambda conexion: None)

	def conectado(self) -> bool:
		return self._principal is not None and not self._principal.rota

	# Navegación -------------------------------------------------------------

	def _filas(self, conexion: _Conexion, ruta: str) -> list[_Fila]:
		ftp = conexion.ftp
		if conexion.mlsd is not False:
			lineas: list[str] = []
			try:
				ftp.retrlines(f"MLSD {ruta}", lineas.append)
				conexion.mlsd = True
				return [f for f in map(analizar_mlsd, lineas) if f is not None]
			except ftplib.error_perm as error:
				if _codigo(error) not in ("500", "501", "502", "504"):
					raise
				conexion.mlsd = False
		# LIST con CWD: muchos servidores no entienden rutas con espacios como argumento de LIST.
		ftp.cwd(ruta)
		lineas = []
		try:
			ftp.retrlines("LIST -a", lineas.append)
		except ftplib.error_perm:
			lineas = []
			ftp.retrlines("LIST", lineas.append)
		ahora = time.time()
		return [f for f in (analizar_list(linea, ahora) for linea in lineas) if f is not None]

	def _resolver_enlaces(self, conexion: _Conexion, ruta: str, filas: list[_Fila]) -> None:
		"""Un enlace se muestra como lo que señala (carpeta si se puede entrar con CWD)."""
		enlaces = [f for f in filas if f.tipo == "enlace"]
		for fila in enlaces[:MAXIMO_ENLACES_RESUELTOS]:
			try:
				conexion.ftp.cwd(self.unir(ruta, fila.nombre))
				fila.tipo = "carpeta"
			except ftplib.error_perm:
				fila.tipo = "archivo"
		for fila in enlaces[MAXIMO_ENLACES_RESUELTOS:]:
			fila.tipo = "archivo"

	def _entrada(self, carpeta: str, fila: _Fila) -> base.Entrada:
		es_carpeta = fila.tipo == "carpeta"
		return base.Entrada(
			nombre=fila.nombre, ruta=self.unir(carpeta, fila.nombre), es_carpeta=es_carpeta,
			tamano=-1 if es_carpeta else fila.tamano, modificado=fila.modificado,
		)

	def listar(self, ruta: str, cancelacion=None) -> list[base.Entrada]:
		ruta = self._comprobar_ruta(ruta)
		base.comprobar(cancelacion)

		def trabajo(conexion: _Conexion) -> list[_Fila]:
			filas = self._filas(conexion, ruta)
			if any(f.tipo == "enlace" for f in filas):
				self._resolver_enlaces(conexion, ruta, filas)
			return filas

		filas = self._ejecutar(trabajo, ruta)
		base.comprobar(cancelacion)
		return [self._entrada(ruta, f) for f in filas]

	def info(self, ruta: str) -> base.Entrada:
		ruta = self._comprobar_ruta(ruta)
		if ruta == "/":
			return base.Entrada(nombre="/", ruta="/", es_carpeta=True)

		def trabajo(conexion: _Conexion) -> base.Entrada | None:
			if conexion.mlst:
				try:
					respuesta = conexion.ftp.sendcmd(f"MLST {ruta}")
				except ftplib.error_perm as error:
					if _codigo(error) == "550":
						return None
					if _codigo(error) not in ("500", "501", "502", "504"):
						raise
					conexion.mlst = False
				else:
					for linea in respuesta.splitlines()[1:]:
						if linea.startswith(" "):
							fila = analizar_mlsd(linea[1:])
							if fila is not None:
								fila.nombre = self.nombre(ruta)
								if fila.tipo == "enlace":
									self._resolver_enlaces(conexion, self.padre(ruta) or "/", [fila])
								return self._entrada(self.padre(ruta) or "/", fila)
			# Sin MLST: se lista la carpeta superior y se busca el nombre.
			padre, nombre = self.padre(ruta) or "/", self.nombre(ruta)
			try:
				filas = self._filas(conexion, padre)
			except ftplib.error_perm as error:
				if _codigo(error) == "550":
					return None
				raise
			for fila in filas:
				if fila.nombre == nombre:
					if fila.tipo == "enlace":
						self._resolver_enlaces(conexion, padre, [fila])
					return self._entrada(padre, fila)
			return None

		entrada = self._ejecutar(trabajo, ruta)
		if entrada is None:
			raise base.NoEncontrado(_("No existe {r} en el servidor.").format(r=ruta), ruta)
		return entrada

	# Contenido --------------------------------------------------------------

	def _abrir_transferencia(self, orden: str, ruta: str) -> tuple[_Conexion, bool, socket.socket]:
		for intento in (1, 2):
			ya_conectada = self._principal is not None and not self._principal.rota
			conexion, aparte = self._tomar()
			try:
				conexion.ftp.voidcmd("TYPE I")
				datos = conexion.ftp.transfercmd(f"{orden} {ruta}")
				datos.settimeout(self.tiempo_espera)
				return conexion, aparte, datos
			except (ftplib.Error, OSError, EOFError) as error:
				perdida = _es_conexion_perdida(error)
				if perdida:
					conexion.rota = True
				self._devolver(conexion, aparte)
				if perdida and intento == 1 and ya_conectada and not aparte:
					log.info("Se perdió la conexión con %s; se reintenta una vez", self.servidor)
					continue
				raise convertir_error(error, ruta) from error
			except BaseException:
				self._devolver(conexion, aparte)
				raise
		raise base.ErrorRed(_("Se perdió la conexión con el servidor."), ruta)  # pragma: no cover

	def abrir_lectura(self, ruta: str):
		ruta = self._comprobar_ruta(ruta)
		conexion, aparte, datos = self._abrir_transferencia("RETR", ruta)
		return io.BufferedReader(_FlujoFTP(self, conexion, aparte, datos, ruta, escritura=False), 256 * 1024)

	def abrir_escritura(self, ruta: str, tamano: int = -1):
		ruta = self._comprobar_ruta(ruta)
		conexion, aparte, datos = self._abrir_transferencia("STOR", ruta)
		return io.BufferedWriter(_FlujoFTP(self, conexion, aparte, datos, ruta, escritura=True), 256 * 1024)

	def crear_carpeta(self, ruta: str) -> None:
		ruta = self._comprobar_ruta(ruta)
		try:
			self._ejecutar(lambda c: c.ftp.mkd(ruta), ruta)
		except base.ErrorArchivos as error:
			if not isinstance(error, base.ErrorRed) and self.existe(ruta):
				raise base.YaExiste(_("Ya existe una carpeta o archivo con ese nombre."), ruta) from error
			raise

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		ruta = self._comprobar_ruta(ruta)
		if ruta == "/":
			raise base.ErrorAcceso(_("No se puede eliminar la raíz del servidor."), ruta)
		entrada = self.info(ruta)
		if entrada.es_carpeta:
			if recursivo:
				for hijo in self.listar(ruta, cancelacion):
					base.comprobar(cancelacion)
					self.eliminar(hijo.ruta, recursivo=True, cancelacion=cancelacion)
			self._ejecutar(lambda c: c.ftp.rmd(ruta), ruta)
		else:
			self._ejecutar(lambda c: c.ftp.delete(ruta), ruta)

	def renombrar(self, origen: str, destino: str) -> None:
		origen, destino = self._comprobar_ruta(origen), self._comprobar_ruta(destino)
		if origen == destino:
			return
		if origen.casefold() != destino.casefold() and self.existe(destino):
			raise base.YaExiste(_("Ya existe «{n}».").format(n=self.nombre(destino)), destino)
		self._ejecutar(lambda c: c.ftp.rename(origen, destino), origen)

	def fijar_tiempos(self, ruta: str, modificado: float, creado: float = 0.0) -> None:
		"""MFMT si el servidor lo admite; si no, la fecha queda la de la subida (no es un error)."""
		if not modificado:
			return
		ruta = self._comprobar_ruta(ruta)
		marca = time.strftime("%Y%m%d%H%M%S", time.gmtime(modificado))

		def trabajo(conexion: _Conexion) -> None:
			if not conexion.mfmt:
				return
			try:
				conexion.ftp.sendcmd(f"MFMT {marca} {ruta}")
			except ftplib.error_perm:
				log.info("El servidor %s no cambió la fecha de %s", self.servidor, ruta, exc_info=True)

		self._ejecutar(trabajo, ruta)

	# Ciclo de vida -----------------------------------------------------------

	def clonar(self) -> ProveedorFTP:
		"""Otro proveedor con su propia conexión (contraseña y huellas ya aceptadas, sin preguntar)."""
		clon = ProveedorFTP(self.host, self.puerto, self.usuario, self._contrasena, self.tls, self.pasivo, self.codificacion,
			self.carpeta_inicial, self.tiempo_espera, self.sitio_id, self.nombre_sitio)
		clon._aviso_hecho = True
		return clon

	def cerrar(self) -> None:
		"""Suelta la conexión sin esperar a la red.

		La ventana lo llama desde el hilo de la interfaz (al desconectar o al ir a
		una unidad local): el QUIT, que puede tardar con un servidor lento, se
		manda en un hilo aparte.
		"""
		principal = None
		if self._candado.acquire(blocking=False):
			try:
				principal, self._principal = self._principal, None
			finally:
				self._candado.release()
		elif self._principal is not None:
			# Un flujo la tiene ocupada: se corta el socket y ese flujo fallará con «Se perdió la conexión».
			self._principal.rota = True
			self._principal.cerrar()
		if principal is not None:
			threading.Thread(target=_despedirse, args=(principal, self.servidor), daemon=True, name="ftp-cerrar").start()
		super().cerrar()


def _despedirse(conexion: _Conexion, servidor: str) -> None:
	try:
		conexion.ftp.quit()
	except (ftplib.Error, OSError, EOFError):
		log.debug("QUIT sin respuesta de %s", servidor, exc_info=True)
	conexion.cerrar()
	log.info("Desconectado de %s", servidor)


def _cerrar_silencioso(ftp: ftplib.FTP) -> None:
	try:
		ftp.close()
	except OSError:
		log.debug("Error al cerrar tras un fallo de conexión", exc_info=True)


class _FlujoFTP(io.RawIOBase):
	"""Socket de datos de RETR o STOR; al cerrarse lee la respuesta final y libera la conexión."""

	def __init__(self, proveedor: ProveedorFTP, conexion: _Conexion, aparte: bool, datos: socket.socket, ruta: str,
			escritura: bool) -> None:
		super().__init__()
		self._proveedor = proveedor
		self._conexion = conexion
		self._aparte = aparte
		self._datos: socket.socket | None = datos
		self._ruta = ruta
		self._escritura = escritura
		self._fin = False

	def readable(self) -> bool:
		return not self._escritura

	def writable(self) -> bool:
		return self._escritura

	def readinto(self, destino) -> int:
		if self._datos is None:
			return 0
		try:
			leidos = self._datos.recv_into(destino)
		except (OSError, EOFError) as error:
			self._conexion.rota = True
			raise convertir_error(error, self._ruta) from error
		if leidos == 0:
			self._fin = True
		return leidos

	def write(self, datos) -> int:
		if self._datos is None:
			raise ValueError("flujo cerrado")
		try:
			self._datos.sendall(datos)
		except (OSError, EOFError) as error:
			self._conexion.rota = True
			raise convertir_error(error, self._ruta) from error
		return len(datos)

	def close(self) -> None:
		if self.closed:
			return
		datos, self._datos = self._datos, None
		error_final: BaseException | None = None
		try:
			if datos is not None:
				try:
					if self._escritura and isinstance(datos, ssl.SSLSocket):
						datos.unwrap()
				except (OSError, ValueError):
					log.debug("Cierre TLS de la conexión de datos", exc_info=True)
				datos.close()
			try:
				self._conexion.ftp.voidresp()
			except ftplib.error_temp as error:
				# 426 o 451 al cortar una lectura antes del final es lo esperado (se canceló).
				if self._escritura or self._fin:
					error_final = convertir_error(error, self._ruta)
				else:
					log.debug("Lectura de %s cortada antes del final: %s", self._ruta, error)
			except ftplib.Error as error:
				error_final = convertir_error(error, self._ruta)
			except (OSError, EOFError) as error:
				self._conexion.rota = True
				if self._escritura:
					error_final = convertir_error(error, self._ruta)
				else:
					log.debug("Sin respuesta final tras leer %s", self._ruta, exc_info=True)
		finally:
			self._proveedor._devolver(self._conexion, self._aparte)
			super().close()
		if error_final is not None:
			raise error_final


def _fabrica(url: str):
	return conexiones.proveedor_para_url(url)


resolver.registrar_esquema("ftp", _fabrica)
resolver.registrar_esquema("ftps", _fabrica)
