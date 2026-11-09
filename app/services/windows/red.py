# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Unidades de red de Windows: listar, conectar, reconectar, desconectar y credenciales (diseño 2.0, 9).

Usa ``win32wnet`` (pywin32): ``WNetAddConnection2``, ``WNetCancelConnection2``
y ``WNetOpenEnum`` con las conexiones activas y las recordadas (las que se
reconectan al iniciar sesión). Lo que pywin32 no expone va por ``ctypes`` con
``mpr.dll``: los cuadros ``WNetConnectionDialog`` y ``WNetDisconnectDialog``,
``WNetUseConnectionW`` (letra automática), ``WNetRestoreSingleConnectionW``
(reconectar) y ``WNetGetProviderNameW``.

Estas llamadas pueden tardar mucho con la red caída: la interfaz las hace en
un hilo desechable (1.x 9.7), nunca en el hilo de la interfaz, salvo los dos
cuadros de Windows, que son ventanas modales y necesitan ese hilo.

Las contraseñas se pasan a Windows y nunca se guardan ni se registran aquí:
con «Recordar la contraseña» las guarda el Administrador de credenciales de
Windows (``CredWrite`` de tipo dominio, que ninguna aplicación puede volver a
leer; solo las usa LSA al conectar).
"""

from __future__ import annotations

import builtins
import contextlib
import ctypes
import logging
import string
import urllib.parse
from collections.abc import Iterator
from ctypes import wintypes
from dataclasses import dataclass

from app.services.vfs import base

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


RESOURCETYPE_ANY = 0
RESOURCETYPE_DISK = 1
RESOURCETYPE_PRINT = 2
RESOURCE_CONNECTED = 1
RESOURCE_GLOBALNET = 2
RESOURCE_REMEMBERED = 3
RESOURCEDISPLAYTYPE_SERVER = 2
RESOURCEUSAGE_CONTAINER = 2
CONNECT_UPDATE_PROFILE = 0x1
CONNECT_TEMPORARY = 0x4
CONNECT_INTERACTIVE = 0x8
CONNECT_PROMPT = 0x10
CONNECT_REDIRECT = 0x80
CONNECT_LOCALDRIVE = 0x100
CONNECT_REQUIRE_INTEGRITY = 0x4000
CONNECT_REQUIRE_PRIVACY = 0x8000
UNIVERSAL_NAME_INFO_LEVEL = 1
CRED_TYPE_DOMAIN_PASSWORD = 2
CRED_PERSIST_ENTERPRISE = 3

NO_ERROR = 0
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_PASSWORD = 86
ERROR_CONNECTION_UNAVAIL = 1201
ERROR_EXTENDED_ERROR = 1208
ERROR_SESSION_CREDENTIAL_CONFLICT = 1219
ERROR_CANCELLED = 1223
ERROR_NOT_AUTHENTICATED = 1244
ERROR_SMB_GUEST_LOGON_BLOCKED = 1272
ERROR_LOGON_FAILURE = 1326
ERROR_NOT_FOUND = 1168
ERROR_NO_BROWSER_SERVERS = 6118
ERROR_NOT_CONNECTED = 2250
ERROR_OPEN_FILES = 2401
ERROR_DEVICE_IN_USE = 2404

#: Códigos con los que hay que pedir usuario y contraseña y repetir (9.3).
CODIGOS_CREDENCIALES = frozenset({ERROR_ACCESS_DENIED, ERROR_INVALID_PASSWORD, ERROR_NOT_AUTHENTICATED, ERROR_LOGON_FAILURE})

# ``ui2_status`` de ``NetUseEnum`` nivel 2.
USE_OK, USE_PAUSED, USE_SESSLOST, USE_NETERR, USE_CONN, USE_RECONN = 0, 1, 2, 3, 4, 5

#: Estados de una unidad o conexión (``UnidadRed.estado``).
CONECTADA, DESCONECTADA, NO_DISPONIBLE = "conectada", "desconectada", "no_disponible"

PROVEEDOR_SMB = "Microsoft Windows Network"
PROVEEDOR_WEBDAV = "Web Client Network"
PROVEEDOR_P9 = "Plan 9 Network Provider"


@dataclass(frozen=True)
class UnidadRed:
	"""Una letra asignada a un recurso compartido, o una conexión sin letra (``letra`` vacía).

	:param letra: «Z:», o «» en una conexión sin letra.
	:param remoto: «\\\\servidor\\recurso» o la dirección WebDAV.
	:param conectada: Windows la tiene conectada ahora.
	:param recordada: Windows la vuelve a conectar al iniciar sesión.
	:param proveedor: proveedor de red de Windows («Microsoft Windows Network»...).
	:param usuario: cuenta con la que se conectó, si Windows lo dice.
	:param estado: ``CONECTADA``, ``DESCONECTADA`` (recordada sin conectar) o ``NO_DISPONIBLE`` (sesión perdida).
	"""

	letra: str
	remoto: str
	conectada: bool = True
	recordada: bool = False
	proveedor: str = ""
	usuario: str = ""
	estado: str = ""

	@property
	def nombre(self) -> str:
		"""La letra o, sin letra, el remoto (lo que acepta ``desconectar``)."""
		return self.letra or self.remoto

	@property
	def estado_efectivo(self) -> str:
		if self.estado:
			return self.estado
		return CONECTADA if self.conectada else DESCONECTADA

	def texto_estado(self) -> str:
		"""«Conectada», «Desconectada: Intro para volver a conectar» o «No disponible» (9.1)."""
		estado = self.estado_efectivo
		if estado == CONECTADA:
			return _("Conectada")
		if estado == NO_DISPONIBLE:
			return _("No disponible")
		return _("Desconectada: Intro para volver a conectar")

	def describir(self) -> str:
		"""«Z:, \\\\servidor\\recurso» y, si no está activa, «desconectada»."""
		texto = f"{self.letra}, {self.remoto}" if self.letra else _("{r}, sin letra").format(r=self.remoto)
		if not self.conectada:
			texto += ", " + _("desconectada (se reconecta al usarla)")
		elif self.estado == NO_DISPONIBLE:
			texto += ", " + _("no disponible")
		return texto

	def mensaje_no_disponible(self) -> str:
		"""«Z: no está disponible (\\\\DS220\\home). Intro para volver a conectar» (9.4)."""
		return _("{l} no está disponible ({r}). Intro para volver a conectar").format(l=self.nombre, r=self.remoto)


@dataclass(frozen=True)
class RecursoRed:
	"""Un recurso compartido de un servidor (``NetShareEnum`` nivel 1)."""

	nombre: str
	ruta: str
	tipo: str  # «disco», «impresora», «dispositivo», «ipc»
	comentario: str = ""
	especial: bool = False  # recursos con «$» (administrativos u ocultos)


@dataclass(frozen=True)
class Credencial:
	"""Credencial de tipo dominio del Administrador de credenciales (sin la contraseña: no se puede leer)."""

	objetivo: str
	usuario: str
	persistencia: int = CRED_PERSIST_ENTERPRISE


@dataclass(frozen=True)
class OtroProveedor:
	"""Proveedor de red que no es SMB (9.1, 9.7): WSL, escritorio remoto, WebDAV, SSHFS o NFS."""

	clave: str  # «wsl», «tsclient», «webdav», «sshfs», «nfs»
	nombre: str  # texto visible
	ruta: str  # «\\\\wsl.localhost» o la dirección para el diálogo de conectar
	ayuda: str = ""


# ── Mensajes ─────────────────────────────────────────────────────────────────


def _mensajes() -> dict[int, str]:
	return {
		2: _("No se encuentra la unidad o la ruta de red."),
		3: _("No se encuentra la ruta de red."),
		5: _("No tiene permiso para usar ese recurso compartido."),
		53: _("No se encuentra la ruta de red. Revise el nombre del servidor."),
		64: _("Se perdió la conexión con el servidor."),
		67: _("No se encuentra el recurso compartido en ese servidor."),
		85: _("Esa letra de unidad ya está en uso."),
		86: _("La contraseña no es correcta."),
		1201: _("La unidad está desconectada."),
		1202: _("Esa letra ya está asignada a otra conexión recordada."),
		1203: _("No se encuentra la ruta de red o la red no está disponible."),
		1219: _("Ya hay una conexión a ese servidor con otro usuario. Desconéctela antes de usar otras credenciales."),
		1222: _("La red no está disponible."),
		1223: _("Se canceló la conexión."),
		1240: _("La cuenta no puede iniciar sesión desde este equipo."),
		1244: _("El servidor pide usuario y contraseña."),
		1272: _("Windows bloqueó el acceso como invitado (SMB sin autenticación). Conecte con un usuario y contraseña del servidor."),
		1326: _("Usuario o contraseña incorrectos."),
		1327: _("La cuenta tiene restricciones que impiden conectar."),
		1330: _("La contraseña de la cuenta ha caducado."),
		1331: _("La cuenta está deshabilitada."),
		1909: _("La cuenta está bloqueada."),
		2250: _("Esa unidad no está conectada."),
		2401: _("Hay archivos abiertos en esa unidad."),
		2404: _("La unidad está en uso (quizá es la carpeta actual de algún programa)."),
		6118: _("Windows ya no puede listar los equipos del grupo de trabajo; se buscan por detección de redes."),
	}


def _texto_extendido() -> str:
	"""Texto del proveedor para el error 1208 (``WNetGetLastError``)."""
	try:
		_codigo, texto, proveedor = _win32wnet().WNetGetLastError()
	except Exception:  # noqa: BLE001 - sin detalle se da el mensaje genérico
		log.debug("WNetGetLastError no dio detalle", exc_info=True)
		return ""
	texto = (texto or "").strip()
	return f"{proveedor}: {texto}" if texto and proveedor else texto


def _mensaje_error(codigo: int, remoto: str = "") -> str:
	if codigo == ERROR_EXTENDED_ERROR:
		texto = _texto_extendido() or _("El proveedor de red devolvió un error sin detalle.")
	else:
		texto = _mensajes().get(codigo) or _("Windows devolvió el error {c}.").format(c=codigo)
	if codigo in (2, 3, ERROR_CONNECTION_UNAVAIL, ERROR_NOT_CONNECTED) and es_elevado():
		texto += " " + aviso_elevacion()
	return f"{texto} ({remoto})" if remoto else texto


class ErrorUnidadRed(base.ErrorRed):
	"""Error de una unidad de red con el código de Windows (``codigo``)."""

	def __init__(self, mensaje: str, codigo: int, ruta: str = "") -> None:
		super().__init__(mensaje, ruta)
		self.codigo = codigo

	@property
	def pide_credenciales(self) -> bool:
		return self.codigo in CODIGOS_CREDENCIALES


def codigo_de(error: BaseException) -> int:
	"""Código de Windows de una excepción de pywin32, de ``OSError`` o de ``ErrorUnidadRed``."""
	for atributo in ("codigo", "winerror"):
		valor = getattr(error, atributo, None)
		if isinstance(valor, int) and valor:
			return valor
	argumentos = getattr(error, "args", None) or ()
	return int(argumentos[0]) if argumentos and isinstance(argumentos[0], int) else 0


def _error(error: BaseException, remoto: str = "") -> ErrorUnidadRed:
	if isinstance(error, ErrorUnidadRed):
		return error
	codigo = codigo_de(error)
	return ErrorUnidadRed(_mensaje_error(codigo, remoto), codigo, remoto)


def error_de_codigo(codigo: int, remoto: str = "") -> ErrorUnidadRed:
	return ErrorUnidadRed(_mensaje_error(codigo, remoto), codigo, remoto)


# ── Acceso a pywin32 y a mpr.dll (las pruebas los sustituyen) ─────────────────


def _win32wnet():
	import win32wnet

	return win32wnet


def _win32net():
	import win32net

	return win32net


def _win32cred():
	import win32cred

	return win32cred


def _mpr():
	return ctypes.WinDLL("mpr.dll", use_last_error=True)


class NETRESOURCEW(ctypes.Structure):
	_fields_ = [
		("dwScope", wintypes.DWORD), ("dwType", wintypes.DWORD), ("dwDisplayType", wintypes.DWORD),
		("dwUsage", wintypes.DWORD), ("lpLocalName", wintypes.LPWSTR), ("lpRemoteName", wintypes.LPWSTR),
		("lpComment", wintypes.LPWSTR), ("lpProvider", wintypes.LPWSTR),
	]


@contextlib.contextmanager
def sin_cuadros_de_error() -> Iterator[None]:
	"""``SEM_FAILCRITICALERRORS`` en este hilo: una letra caída no abre cuadros de Windows (9.9)."""
	anterior = wintypes.DWORD(0)
	cambiado = False
	try:
		cambiado = bool(ctypes.windll.kernel32.SetThreadErrorMode(0x0001, ctypes.byref(anterior)))
	except (AttributeError, OSError):
		log.debug("SetThreadErrorMode no disponible", exc_info=True)
	try:
		yield
	finally:
		if cambiado:
			ctypes.windll.kernel32.SetThreadErrorMode(anterior.value, None)


def es_elevado() -> bool:
	"""zCommander se ejecuta como administrador (no ve las letras de la sesión sin elevar)."""
	try:
		return bool(ctypes.windll.shell32.IsUserAnAdmin())
	except (AttributeError, OSError):
		return False


def aviso_elevacion() -> str:
	return _("zCommander se ejecuta como administrador y Windows no le deja ver las unidades de red de la sesión normal "
		"(salvo con la directiva EnableLinkedConnections, que zCommander no cambia).")


# ── Rutas ────────────────────────────────────────────────────────────────────


def es_webdav(texto: str) -> bool:
	"""Dirección WebDAV: ``https://...``, ``http://...`` o ``\\\\srv@SSL@puerto\\DavWWWRoot\\...``."""
	texto = (texto or "").strip()
	return texto.lower().startswith(("http://", "https://")) or "@ssl" in texto.lower() or "\\davwwwroot" in texto.lower()


def validar_remoto(texto: str) -> str | None:
	"""Motivo por el que ``texto`` no es «\\\\servidor\\recurso» (o una dirección WebDAV), o ``None`` si vale."""
	texto = (texto or "").strip()
	if texto.lower().startswith(("http://", "https://")):
		partes = urllib.parse.urlsplit(texto)
		return None if partes.hostname else _("La dirección WebDAV no tiene servidor: https://servidor/carpeta.")
	if not texto.startswith("\\\\"):
		return _("Escriba la carpeta de red como \\\\servidor\\recurso.")
	partes = [p for p in texto[2:].split("\\") if p]
	if len(partes) < 2:
		return _("Falta el nombre del recurso compartido: \\\\servidor\\recurso.")
	if any(c in texto for c in '<>"|?*/'):
		return _("La carpeta de red tiene caracteres no válidos.")
	return None


def normalizar_remoto(texto: str) -> str:
	texto = (texto or "").strip()
	if texto.lower().startswith(("http://", "https://")):
		return texto.rstrip("/") if texto.count("/") > 3 else texto
	return texto.rstrip("\\")


def servidor_de(remoto: str) -> str:
	"""«DS220» de «\\\\DS220\\home», de «https://ds220:5006/x» o de «\\\\ds220@SSL@5006\\DavWWWRoot»."""
	remoto = (remoto or "").strip()
	if remoto.lower().startswith(("http://", "https://")):
		return urllib.parse.urlsplit(remoto).hostname or ""
	partes = [p for p in remoto.lstrip("\\").split("\\") if p]
	if not partes:
		return ""
	return partes[0].split("@", 1)[0]


def es_servidor(ruta: str) -> bool:
	"""``\\\\servidor`` solo (sin recurso)."""
	ruta = (ruta or "").strip().rstrip("\\")
	return ruta.startswith("\\\\") and len([p for p in ruta[2:].split("\\") if p]) == 1


DRIVE_REMOTE = 4


def es_ruta_de_red(ruta: str) -> bool:
	"""Ruta UNC, o en una letra de red (conectada o recordada). No toca el servidor."""
	ruta = (ruta or "").strip()
	if ruta.startswith("\\\\"):
		return True
	if len(ruta) < 2 or ruta[1] != ":":
		return False
	try:
		if ctypes.windll.kernel32.GetDriveTypeW(ruta[:2] + "\\") == DRIVE_REMOTE:
			return True
	except (AttributeError, OSError):
		log.debug("GetDriveTypeW falló", exc_info=True)
	try:
		return unidad(ruta[:2]) is not None
	except (ErrorUnidadRed, base.NombreNoValido):
		return False


def normalizar_letra(letra: str) -> str:
	letra = (letra or "").strip().upper().rstrip("\\")
	if len(letra) == 1:
		letra += ":"
	if len(letra) != 2 or letra[1] != ":" or letra[0] not in string.ascii_uppercase:
		raise base.NombreNoValido(_("La letra de unidad no es válida: {l}").format(l=letra), letra)
	return letra


# ── Listar ───────────────────────────────────────────────────────────────────


def _enumerar(alcance: int) -> list[tuple[str, str, str]]:
	"""(letra, remoto, proveedor) de las conexiones de disco de ese alcance, con letra o sin ella."""
	wnet = _win32wnet()
	resultado = []
	manejador = wnet.WNetOpenEnum(alcance, RESOURCETYPE_DISK, 0, None)
	try:
		while True:
			lote = wnet.WNetEnumResource(manejador, 64)
			if not lote:
				break
			for recurso in lote:
				remoto = recurso.lpRemoteName or ""
				if not remoto:
					continue
				resultado.append(((recurso.lpLocalName or "").upper(), remoto, recurso.lpProvider or ""))
	finally:
		wnet.WNetCloseEnum(manejador)
	return resultado


def _usos() -> dict[str, dict]:
	"""``NetUseEnum(None, 2)`` por letra (o remoto, sin letra) en mayúsculas: estado y usuario."""
	try:
		datos = _win32net().NetUseEnum(None, 2)
	except Exception:  # noqa: BLE001 - sin el detalle se usa lo de WNetOpenEnum
		log.debug("NetUseEnum falló", exc_info=True)
		return {}
	filas = datos[0] if isinstance(datos, tuple) else datos
	resultado = {}
	for fila in filas or []:
		local = str(fila.get("local") or "").upper()
		remoto = str(fila.get("remote") or "")
		resultado[local or remoto.upper()] = fila
	return resultado


def _estado_de_uso(fila: dict | None, conectada: bool) -> str:
	if not conectada:
		return DESCONECTADA
	if fila is None:
		return CONECTADA
	estado = fila.get("status", USE_OK)
	return NO_DISPONIBLE if estado in (USE_SESSLOST, USE_NETERR) else CONECTADA


def _usuario_de(fila: dict | None) -> str:
	if not fila:
		return ""
	usuario = str(fila.get("username") or "")
	dominio = str(fila.get("domainname") or "")
	return f"{dominio}\\{usuario}" if usuario and dominio and "\\" not in usuario and "@" not in usuario else usuario


def unidades_red(con_sin_letra: bool = True) -> list[UnidadRed]:
	"""Letras de red activas y recordadas y, si se pide, las conexiones sin letra.

	Las letras van primero (por letra) y después las conexiones sin letra (por remoto).
	Las conexiones a ``IPC$`` (solo autenticación) no se listan.

	:raises ErrorUnidadRed: si Windows no deja enumerarlas.
	"""
	try:
		conectadas = _enumerar(RESOURCE_CONNECTED)
		recordadas = _enumerar(RESOURCE_REMEMBERED)
	except ImportError as error:
		raise ErrorUnidadRed(_("Falta pywin32 para gestionar unidades de red."), 0) from error
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		raise _error(error) from error
	usos = _usos()
	por_letra: dict[str, UnidadRed] = {}
	sin_letra: dict[str, UnidadRed] = {}
	activas = {(l or r.upper()) for l, r, _p in conectadas}
	guardadas = {(l or r.upper()) for l, r, _p in recordadas}
	for letra, remoto, proveedor in [*conectadas, *recordadas]:
		clave = letra or remoto.upper()
		if not letra and (not con_sin_letra or remoto.upper().endswith("\\IPC$")):
			continue
		destino = por_letra if letra else sin_letra
		if clave in destino:
			continue
		conectada = clave in activas
		uso = usos.get(clave)
		destino[clave] = UnidadRed(letra, remoto, conectada, clave in guardadas, proveedor, _usuario_de(uso),
			_estado_de_uso(uso, conectada))
	return [por_letra[k] for k in sorted(por_letra)] + [sin_letra[k] for k in sorted(sin_letra)]


def letras_libres(ocupadas_extra: list[str] | None = None) -> list[str]:
	"""Letras sin unidad ni conexión recordada, de la Z hacia atrás (como el Explorador)."""
	from app.services.windows import unidades

	ocupadas = {l.upper() for l in unidades.letras()}
	try:
		ocupadas |= {u.letra for u in unidades_red(con_sin_letra=False)}
	except ErrorUnidadRed:
		log.debug("No se pudieron leer las conexiones recordadas", exc_info=True)
	ocupadas |= {normalizar_letra(l) for l in (ocupadas_extra or [])}
	return [f"{l}:" for l in reversed(string.ascii_uppercase[3:]) if f"{l}:" not in ocupadas]


def unidad(letra_o_remoto: str) -> UnidadRed | None:
	"""La unidad o conexión con ese nombre, o ``None``."""
	nombre = (letra_o_remoto or "").strip().rstrip("\\").upper()
	if len(nombre) == 1 or (len(nombre) == 2 and nombre[1] == ":"):
		nombre = normalizar_letra(nombre)
	for elemento in unidades_red():
		if elemento.letra.upper() == nombre or (not elemento.letra and elemento.remoto.rstrip("\\").upper() == nombre):
			return elemento
	return None


def conexiones_a_servidor(servidor: str) -> list[str]:
	"""Nombres (letra o remoto) de todo lo conectado a ``servidor``, también ``IPC$`` (para el error 1219)."""
	servidor = servidor.strip("\\").upper()
	nombres: list[str] = []
	try:
		for letra, remoto, _proveedor in _enumerar(RESOURCE_CONNECTED):
			if servidor_de(remoto).upper() == servidor:
				nombres.append(letra or remoto)
	except Exception:  # noqa: BLE001 - se sigue con NetUseEnum
		log.debug("No se pudieron enumerar las conexiones", exc_info=True)
	for clave, fila in _usos().items():
		remoto = str(fila.get("remote") or "")
		nombre = str(fila.get("local") or "") or remoto
		if servidor_de(remoto).upper() == servidor and nombre.upper() not in {n.upper() for n in nombres}:
			nombres.append(nombre or clave)
	return nombres


# ── Recursos de un servidor (9.3) ─────────────────────────────────────────────

STYPE_DISKTREE, STYPE_PRINTQ, STYPE_DEVICE, STYPE_IPC = 0, 1, 2, 3
STYPE_SPECIAL = 0x80000000


def _tipo_recurso(tipo: int) -> str:
	return {STYPE_DISKTREE: "disco", STYPE_PRINTQ: "impresora", STYPE_DEVICE: "dispositivo", STYPE_IPC: "ipc"}.get(tipo & 0xFF, "disco")


def _ordenar_recursos(recursos: list[RecursoRed], mostrar_ocultos: bool) -> list[RecursoRed]:
	visibles = [r for r in recursos if mostrar_ocultos or not (r.especial or r.nombre.endswith("$"))]
	discos = sorted((r for r in visibles if r.tipo != "impresora"), key=lambda r: r.nombre.casefold())
	impresoras = sorted((r for r in visibles if r.tipo == "impresora"), key=lambda r: r.nombre.casefold())
	return discos + impresoras


def _recursos_netshare(servidor: str) -> list[RecursoRed]:
	net = _win32net()
	resultado: list[RecursoRed] = []
	reanudar = 0
	while True:
		datos, _total, reanudar = net.NetShareEnum(servidor, 1, reanudar) if reanudar else net.NetShareEnum(servidor, 1)
		for fila in datos:
			nombre = str(fila.get("netname", ""))
			tipo = int(fila.get("type", 0))
			resultado.append(RecursoRed(nombre, f"\\\\{servidor}\\{nombre}", _tipo_recurso(tipo), str(fila.get("remark") or ""),
				bool(tipo & STYPE_SPECIAL) or nombre.endswith("$")))
		if not reanudar:
			return resultado


def _recursos_wnet(servidor: str, proveedor: str | None) -> list[RecursoRed]:
	wnet = _win32wnet()
	contenedor = wnet.NETRESOURCE()
	contenedor.lpRemoteName = f"\\\\{servidor}"
	contenedor.dwDisplayType = RESOURCEDISPLAYTYPE_SERVER
	contenedor.dwUsage = RESOURCEUSAGE_CONTAINER
	contenedor.dwScope = RESOURCE_GLOBALNET
	contenedor.lpProvider = proveedor
	manejador = wnet.WNetOpenEnum(RESOURCE_GLOBALNET, RESOURCETYPE_ANY, 0, contenedor)
	resultado = []
	try:
		while True:
			lote = wnet.WNetEnumResource(manejador, 64)
			if not lote:
				break
			for recurso in lote:
				remoto = recurso.lpRemoteName or ""
				nombre = remoto.rstrip("\\").rsplit("\\", 1)[-1]
				if nombre:
					tipo = "impresora" if recurso.dwType == RESOURCETYPE_PRINT else "disco"
					resultado.append(RecursoRed(nombre, remoto, tipo, recurso.lpComment or "", nombre.endswith("$")))
	finally:
		wnet.WNetCloseEnum(manejador)
	return resultado


def recursos(servidor: str, mostrar_ocultos: bool = False) -> list[RecursoRed]:
	"""Recursos de ``\\\\servidor`` (9.3): ``NetShareEnum`` nivel 1 y, si falla, ``WNetOpenEnum`` con su proveedor.

	Los recursos con «$» solo con ``mostrar_ocultos``; las impresoras al final.

	:raises ErrorUnidadRed: ``pide_credenciales`` con 5, 86, 1244 o 1326; 1219, 1272...
	"""
	servidor = servidor.strip().strip("\\")
	try:
		with sin_cuadros_de_error():
			return _ordenar_recursos(_recursos_netshare(servidor), mostrar_ocultos)
	except ImportError as error:
		raise ErrorUnidadRed(_("Falta pywin32 para gestionar unidades de red."), 0, servidor) from error
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		primero = _error(error, f"\\\\{servidor}")
		if primero.codigo in (ERROR_SESSION_CREDENTIAL_CONFLICT, ERROR_SMB_GUEST_LOGON_BLOCKED):
			raise primero from error
		log.info("NetShareEnum de %s falló (código %s); se prueba WNetOpenEnum", servidor, primero.codigo)
	# Otros proveedores (WSL, WebDAV, NFS) no responden a NetShareEnum (da 5 o 53): su
	# contenedor sí se recorre con WNetOpenEnum. Si nada sirve, manda el error de NetShareEnum
	# (con 5, 86 o 1326, la interfaz pide credenciales).
	vacia = False
	for proveedor in (None, PROVEEDOR_SMB, PROVEEDOR_P9, PROVEEDOR_WEBDAV):
		try:
			with sin_cuadros_de_error():
				lista = _recursos_wnet(servidor, proveedor)
		except Exception:  # noqa: BLE001 - se prueba el siguiente proveedor
			log.debug("WNetOpenEnum de %s con %s falló", servidor, proveedor, exc_info=True)
			continue
		if lista:
			return _ordenar_recursos(lista, mostrar_ocultos)
		vacia = True
	if vacia and not primero.pide_credenciales:
		return []
	raise primero


# ── Conectar, reconectar y desconectar ───────────────────────────────────────


def estado_webclient() -> str:
	"""Inicio del servicio WebClient: «automatico», «manual», «deshabilitado», «no_instalado» o «desconocido»."""
	try:
		import win32service

		gestor = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
		try:
			try:
				servicio = win32service.OpenService(gestor, "WebClient", win32service.SERVICE_QUERY_CONFIG)
			except Exception as error:  # noqa: BLE001 - 1060: el servicio no existe
				if codigo_de(error) == 1060:
					return "no_instalado"
				raise
			try:
				inicio = win32service.QueryServiceConfig(servicio)[1]
			finally:
				win32service.CloseServiceHandle(servicio)
		finally:
			win32service.CloseServiceHandle(gestor)
	except Exception:  # noqa: BLE001 - no se sabe: se intenta conectar igualmente
		log.debug("No se pudo consultar el servicio WebClient", exc_info=True)
		return "desconocido"
	return {2: "automatico", 3: "manual", 4: "deshabilitado"}.get(int(inicio), "manual")


def aviso_webdav() -> str:
	return _("Las unidades WebDAV de Windows usan el servicio WebClient, que Microsoft declaró obsoleto en 2023. "
		"El complemento Nubes ofrece WebDAV propio sin depender de él.")


def comprobar_webdav() -> None:
	""":raises ErrorUnidadRed: si el servicio WebClient está deshabilitado o no está (no se intenta cambiarlo, 9.7)."""
	estado = estado_webclient()
	if estado == "deshabilitado":
		raise ErrorUnidadRed(_("El servicio WebClient de Windows está deshabilitado, así que no se pueden conectar unidades WebDAV. "
			"Puede habilitarlo un administrador en Servicios; zCommander no lo cambia.") + " " + aviso_webdav(), 1058)
	if estado == "no_instalado":
		raise ErrorUnidadRed(_("Este Windows no tiene el servicio WebClient, necesario para las unidades WebDAV.") + " " + aviso_webdav(), 1060)


def _usar_conexion(remoto: str, usuario: str, contrasena: str | None, banderas: int, proveedor: str | None = None) -> str:
	"""``WNetUseConnectionW`` con ``CONNECT_REDIRECT``: Windows elige la letra y la devuelve."""
	recurso = NETRESOURCEW(0, RESOURCETYPE_DISK, 0, 0, None, remoto, None, proveedor)
	bufer = ctypes.create_unicode_buffer(260)
	tamano = wintypes.DWORD(len(bufer))
	resultado = wintypes.DWORD(0)
	funcion = _mpr().WNetUseConnectionW
	funcion.argtypes = [wintypes.HWND, ctypes.POINTER(NETRESOURCEW), wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
		wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
	funcion.restype = wintypes.DWORD
	codigo = funcion(None, ctypes.byref(recurso), contrasena or None, usuario or None, banderas | CONNECT_REDIRECT, bufer,
		ctypes.byref(tamano), ctypes.byref(resultado))
	if codigo != NO_ERROR:
		raise error_de_codigo(int(codigo), remoto)
	return bufer.value.upper() if resultado.value & CONNECT_LOCALDRIVE else ""


def guardar_credencial(objetivo: str, usuario: str, contrasena: str) -> None:
	"""Guarda la contraseña en el Administrador de credenciales de Windows (``CRED_TYPE_DOMAIN_PASSWORD``).

	Equivale a ``cmdkey /add``. zCommander no la guarda en ningún otro sitio ni la registra.
	"""
	_win32cred().CredWrite({
		"Type": CRED_TYPE_DOMAIN_PASSWORD,
		"TargetName": objetivo,
		"UserName": usuario,
		"CredentialBlob": contrasena,
		"Persist": CRED_PERSIST_ENTERPRISE,
	}, 0)
	log.info("Credencial de %s guardada en el Administrador de credenciales de Windows", objetivo)


def conectar(letra: str, remoto: str, usuario: str = "", contrasena: str | None = "", recordar: bool = False, *,
		persistente: bool = True, exigir_cifrado: bool = False) -> str:
	"""Conecta ``remoto`` y devuelve la letra usada («» sin letra). Bloquea: llamar desde un hilo.

	Compatible con la llamada de la 1.x ``conectar(letra, remoto, usuario, contrasena, recordar)``.

	:param letra: «Z:»; «» para conectar sin letra (solo abrir el recurso); «*» para que Windows elija la letra.
	:param usuario: vacío para usar la cuenta de Windows.
	:param recordar: guardar la contraseña en el Administrador de credenciales de Windows (si hay usuario y contraseña).
	:param persistente: volver a conectar la letra al iniciar sesión (``CONNECT_UPDATE_PROFILE``).
	:param exigir_cifrado: exigir cifrado SMB (``CONNECT_REQUIRE_PRIVACY``).
	:raises ErrorUnidadRed: con el mensaje de Windows en español.
	"""
	problema = validar_remoto(remoto)
	if problema:
		raise base.NombreNoValido(problema, remoto)
	remoto = normalizar_remoto(remoto)
	automatica = (letra or "").strip() == "*"
	letra = "" if automatica or not (letra or "").strip() else normalizar_letra(letra)
	if es_webdav(remoto):
		comprobar_webdav()
	banderas = 0
	if persistente and (letra or automatica):
		banderas |= CONNECT_UPDATE_PROFILE
	if exigir_cifrado and not es_webdav(remoto):
		banderas |= CONNECT_REQUIRE_PRIVACY
	descripcion = letra or ("(automática)" if automatica else "(sin letra)")
	try:
		with sin_cuadros_de_error():
			if automatica:
				letra = _usar_conexion(remoto, usuario, contrasena, banderas)
			else:
				wnet = _win32wnet()
				recurso = wnet.NETRESOURCE()
				recurso.dwType = RESOURCETYPE_DISK
				recurso.lpLocalName = letra or None
				recurso.lpRemoteName = remoto
				recurso.lpProvider = None
				wnet.WNetAddConnection2(recurso, contrasena if contrasena else None, usuario or None, banderas)
	except ImportError as error:
		raise ErrorUnidadRed(_("Falta pywin32 para gestionar unidades de red."), 0, remoto) from error
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		convertido = _error(error, remoto)
		log.info("No se pudo conectar %s a %s: código %s", descripcion, remoto, convertido.codigo)
		raise convertido from error
	log.info("Conectado %s a %s%s%s", letra or descripcion, remoto, " (persistente)" if banderas & CONNECT_UPDATE_PROFILE else "",
		" (cifrado exigido)" if banderas & CONNECT_REQUIRE_PRIVACY else "")
	if recordar and usuario and contrasena:
		try:
			guardar_credencial(servidor_de(remoto), usuario, contrasena)
		except Exception:  # noqa: BLE001 - la conexión ya está hecha; solo no se recordará
			log.warning("No se pudo guardar la credencial de %s en Windows", servidor_de(remoto), exc_info=True)
	return letra


def autenticar(servidor: str, usuario: str, contrasena: str, recordar: bool = False) -> None:
	"""Inicia sesión en ``\\\\servidor\\IPC$`` sin letra (9.3), para poder listar sus recursos.

	:raises ErrorUnidadRed: 1219 si ya hay una sesión con ese servidor con otro usuario.
	"""
	nombre = servidor.strip().strip("\\")
	conectar("", f"\\\\{nombre}\\IPC$", usuario, contrasena, recordar, persistente=False)


def reconectar(letra: str, hwnd: int = 0) -> None:
	"""Vuelve a conectar una letra recordada que no está conectada (1201). Bloquea: llamar desde un hilo.

	Primero ``WNetRestoreSingleConnectionW`` (usa lo que Windows recuerda, credenciales incluidas);
	si falla por otro motivo que las credenciales, ``WNetAddConnection2`` con el remoto recordado.

	:raises ErrorUnidadRed: ``pide_credenciales`` si hay que pedir usuario y contraseña.
	"""
	letra = normalizar_letra(letra)
	try:
		funcion = _mpr().WNetRestoreSingleConnectionW
		funcion.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.BOOL]
		funcion.restype = wintypes.DWORD
		with sin_cuadros_de_error():
			codigo = int(funcion(hwnd or None, letra, False))
	except (AttributeError, OSError):
		log.debug("WNetRestoreSingleConnectionW no disponible", exc_info=True)
		codigo = -1
	if codigo == NO_ERROR:
		log.info("Unidad %s reconectada", letra)
		return
	if codigo in CODIGOS_CREDENCIALES or codigo in (ERROR_SESSION_CREDENTIAL_CONFLICT, ERROR_SMB_GUEST_LOGON_BLOCKED):
		raise error_de_codigo(codigo, letra)
	recordada = unidad(letra)
	if recordada is None or not recordada.remoto:
		raise error_de_codigo(codigo if codigo > 0 else ERROR_NOT_CONNECTED, letra)
	log.info("WNetRestoreSingleConnection de %s dio %s; se conecta con el remoto recordado", letra, codigo)
	conectar(letra, recordada.remoto, persistente=False)


def desconectar(nombre: str, forzar: bool = False, olvidar: bool = True, *, olvidar_credencial: bool = False) -> None:
	"""Quita la unidad «Z:» (o la conexión «\\\\servidor\\recurso»). Bloquea: llamar desde un hilo.

	:param forzar: aunque haya archivos abiertos (los programas que los usan pueden perder datos).
	:param olvidar: que no se vuelva a conectar al iniciar sesión.
	:param olvidar_credencial: borrar también la contraseña guardada del servidor en Windows.
	:raises ErrorUnidadRed: ``codigo`` 2401 o 2404 si hay archivos abiertos y no se fuerza.
	"""
	nombre = nombre.strip()
	if not nombre.startswith("\\\\") and "://" not in nombre:
		nombre = normalizar_letra(nombre)
	servidor = ""
	if olvidar_credencial:
		if nombre.startswith("\\\\") or "://" in nombre:
			servidor = servidor_de(nombre)
		else:
			try:
				actual = unidad(nombre)
			except ErrorUnidadRed:
				actual = None
			servidor = servidor_de(actual.remoto) if actual else ""
	try:
		with sin_cuadros_de_error():
			_win32wnet().WNetCancelConnection2(nombre, CONNECT_UPDATE_PROFILE if olvidar else 0, bool(forzar))
	except ImportError as error:
		raise ErrorUnidadRed(_("Falta pywin32 para gestionar unidades de red."), 0, nombre) from error
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		convertido = _error(error, nombre)
		log.info("No se pudo desconectar %s: código %s", nombre, convertido.codigo)
		raise convertido from error
	log.info("Unidad de red %s desconectada%s", nombre, " a la fuerza" if forzar else "")
	if servidor:
		olvidar_credencial_de(servidor)


def cerrar_conexiones_servidor(servidor: str) -> int:
	"""Cierra todo lo conectado a ``servidor`` (también ``IPC$``) para resolver el error 1219. Devuelve cuántas."""
	cerradas = 0
	for nombre in conexiones_a_servidor(servidor):
		try:
			desconectar(nombre, forzar=False, olvidar=False)
			cerradas += 1
		except ErrorUnidadRed:
			log.info("No se pudo cerrar %s", nombre, exc_info=True)
	return cerradas


# ── Credenciales guardadas (9.5) ─────────────────────────────────────────────


def credenciales() -> list[Credencial]:
	"""Credenciales de tipo dominio guardadas en Windows (``CredEnumerate``), por objetivo."""
	try:
		filas = _win32cred().CredEnumerate(None, 0) or []
	except ImportError as error:
		raise ErrorUnidadRed(_("Falta pywin32 para leer las credenciales de Windows."), 0) from error
	except Exception as error:  # noqa: BLE001 - 1168: no hay ninguna
		if codigo_de(error) == ERROR_NOT_FOUND:
			return []
		raise _error(error) from error
	resultado = [
		Credencial(str(f.get("TargetName", "")), str(f.get("UserName") or ""), int(f.get("Persist", CRED_PERSIST_ENTERPRISE)))
		for f in filas if int(f.get("Type", 0)) == CRED_TYPE_DOMAIN_PASSWORD
	]
	return sorted(resultado, key=lambda c: c.objetivo.casefold())


def olvidar_credencial_de(objetivo: str) -> bool:
	"""Borra la credencial de tipo dominio de ``objetivo`` (``CredDelete``). Falso si no había ninguna."""
	try:
		_win32cred().CredDelete(objetivo, CRED_TYPE_DOMAIN_PASSWORD, 0)
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		if codigo_de(error) == ERROR_NOT_FOUND:
			return False
		raise _error(error, objetivo) from error
	log.info("Credencial de %s borrada del Administrador de credenciales", objetivo)
	return True


# ── Rutas UNC (copiar_ruta_unc, 9.6) ─────────────────────────────────────────


def ruta_unc(ruta: str) -> str:
	"""«\\\\srv\\rec\\carpeta» de «Z:\\carpeta» (``WNetGetUniversalName``). Una ruta UNC se devuelve igual.

	:raises ErrorUnidadRed: si la ruta no está en una unidad de red (2250) u otro error.
	"""
	ruta = (ruta or "").strip()
	if ruta.startswith("\\\\"):
		return ruta
	try:
		with sin_cuadros_de_error():
			resultado = _win32wnet().WNetGetUniversalName(ruta, UNIVERSAL_NAME_INFO_LEVEL)
	except ImportError as error:
		raise ErrorUnidadRed(_("Falta pywin32 para gestionar unidades de red."), 0, ruta) from error
	except Exception as error:  # noqa: BLE001 - pywin32 lanza pywintypes.error
		raise _error(error, ruta) from error
	return resultado if isinstance(resultado, str) else str(getattr(resultado, "lpUniversalName", resultado))


# ── Otros proveedores de red (9.1, 9.7) ──────────────────────────────────────


def _leer_registro(ruta: str, valor: str) -> str:
	import winreg

	with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta) as clave:
		return str(winreg.QueryValueEx(clave, valor)[0])


def proveedores_instalados() -> dict[str, str]:
	"""Clave de servicio → nombre visible de los proveedores de ``NetworkProvider\\Order`` (solo lectura)."""
	try:
		orden = _leer_registro(r"SYSTEM\CurrentControlSet\Control\NetworkProvider\Order", "ProviderOrder")
	except OSError:
		log.debug("No se pudo leer el orden de los proveedores de red", exc_info=True)
		return {}
	resultado = {}
	for clave in [c.strip() for c in orden.split(",") if c.strip()]:
		try:
			resultado[clave] = _leer_registro(rf"SYSTEM\CurrentControlSet\Services\{clave}\NetworkProvider", "Name")
		except OSError:
			resultado[clave] = clave
	return resultado


def nombre_proveedor(tipo_red: int) -> str:
	"""Nombre del proveedor de un tipo de red (``WNNC_NET_*``) con ``WNetGetProviderNameW``; «» si no está."""
	try:
		funcion = _mpr().WNetGetProviderNameW
		funcion.argtypes = [wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
		funcion.restype = wintypes.DWORD
		bufer = ctypes.create_unicode_buffer(256)
		tamano = wintypes.DWORD(len(bufer))
		return bufer.value if funcion(tipo_red, bufer, ctypes.byref(tamano)) == NO_ERROR else ""
	except (AttributeError, OSError):
		log.debug("WNetGetProviderNameW no disponible", exc_info=True)
		return ""


WNNC_NET_DAV = 0x002E0000
WNNC_NET_MS_NFS = 0x00420000


def _sesion_remota() -> bool:
	try:
		return bool(ctypes.windll.user32.GetSystemMetrics(0x1000))  # SM_REMOTESESSION
	except (AttributeError, OSError):
		return False


def _hay_sshfs() -> bool:
	import winreg

	for ruta in (r"SOFTWARE\WOW6432Node\WinFsp\Services\sshfs", r"SOFTWARE\WinFsp\Services\sshfs"):
		try:
			winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta))
			return True
		except OSError:
			continue
	return False


def otros_proveedores() -> list[OtroProveedor]:
	"""WSL, escritorio remoto, WebDAV, SSHFS-Win y NFS, si están instalados (solo se detectan; no se instalan)."""
	instalados = proveedores_instalados()
	claves = {c.lower() for c in instalados}
	nombres = {n.lower() for n in instalados.values()}
	resultado: list[OtroProveedor] = []
	if "p9np" in claves:
		resultado.append(OtroProveedor("wsl", "\\\\wsl.localhost", "\\\\wsl.localhost", _("Archivos de las distribuciones de Linux de WSL.")))
	if "rdpnp" in claves and _sesion_remota():
		resultado.append(OtroProveedor("tsclient", "\\\\tsclient", "\\\\tsclient", _("Unidades del equipo desde el que se conecta por escritorio remoto.")))
	if "webclient" in claves or PROVEEDOR_WEBDAV.lower() in nombres or nombre_proveedor(WNNC_NET_DAV):
		resultado.append(OtroProveedor("webdav", _("WebDAV (WebClient)"), "https://",
			_("Conecte una dirección https://servidor/carpeta o \\\\servidor@SSL@puerto\\DavWWWRoot\\carpeta.") + " " + aviso_webdav()))
	if "winfsp.np" in claves and _hay_sshfs():
		resultado.append(OtroProveedor("sshfs", "SSHFS", "\\\\sshfs\\",
			_("Conecte \\\\sshfs\\usuario@servidor!puerto\\ruta (relativa a la carpeta personal) o \\\\sshfs.r\\usuario@servidor\\ruta (desde la raíz).")))
	if "nfsrdr" in claves or any("nfs" in n for n in nombres) or nombre_proveedor(WNNC_NET_MS_NFS):
		resultado.append(OtroProveedor("nfs", "NFS", "\\\\", _("Conecte \\\\servidor\\exportación con el Cliente para NFS de Windows.")))
	return resultado


def ayuda_formas_de_ruta() -> str:
	"""Formas de ruta admitidas para la ayuda del campo «Carpeta de red» (9.7)."""
	partes = [_("Recurso compartido: \\\\servidor\\recurso."),
		_("WebDAV: https://servidor/carpeta o \\\\servidor@SSL@puerto\\DavWWWRoot\\carpeta.")]
	try:
		for otro in otros_proveedores():
			if otro.clave in ("sshfs", "nfs"):
				partes.append(f"{otro.nombre}: {otro.ayuda}")
	except Exception:  # noqa: BLE001 - la ayuda sale sin los proveedores opcionales
		log.debug("No se pudieron detectar los proveedores de red", exc_info=True)
	return " ".join(partes)


# ── Cuadros de Windows ───────────────────────────────────────────────────────


def dialogo_conectar_windows(hwnd: int) -> bool:
	"""Cuadro «Conectar a unidad de red» de Windows. ``True`` si se conectó algo.

	Es modal y tiene su propio bucle de mensajes: se llama desde el hilo de la interfaz.
	"""
	resultado = ctypes.windll.mpr.WNetConnectionDialog(ctypes.c_void_p(hwnd), RESOURCETYPE_DISK)
	if resultado in (NO_ERROR,):
		return True
	if resultado in (ERROR_CANCELLED, 0xFFFFFFFF, -1):
		return False
	raise ErrorUnidadRed(_mensaje_error(int(resultado)), int(resultado))


def dialogo_desconectar_windows(hwnd: int) -> bool:
	"""Cuadro «Desconectar unidades de red» de Windows. ``True`` si se desconectó algo."""
	resultado = ctypes.windll.mpr.WNetDisconnectDialog(ctypes.c_void_p(hwnd), RESOURCETYPE_DISK)
	if resultado == NO_ERROR:
		return True
	if resultado in (ERROR_CANCELLED, 0xFFFFFFFF, -1):
		return False
	raise ErrorUnidadRed(_mensaje_error(int(resultado)), int(resultado))
