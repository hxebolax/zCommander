# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Descubrir los equipos de la red local (diseño 2.0, 9.2).

Sin SMB1, Windows ya no lista los equipos del grupo de trabajo: ``NetServerEnum``
y el nivel de dominio de ``WNetOpenEnum`` fallan (6118 tras 31 s,
comprimidos-y-red.md B.1), así que no se usan. Las fuentes, cada una en un
hilo desechable y con un tiempo máximo común:

1. La carpeta «Red» del shell (``CSIDL_NETWORK``), lo mismo que ve el
   Explorador (WS-Discovery, SSDP, NetBIOS donde siga): se queda con lo que
   empieza por ``\\\\`` y se lee de uno en uno (``IEnumIDList.Next``) para
   entregar cada equipo en cuanto llega. Tarda unos 30 s.
2. mDNS (``DnsServiceBrowse`` de ``dnsapi.dll``, Windows 10 1903 o posterior)
   con ``_smb._tcp.local``: NAS y Mac que no hablan WS-Discovery.
3. Dominio de Active Directory (LDAP ``(objectCategory=computer)`` por ADSI),
   solo si ``NetGetJoinInformation`` dice que el equipo está en un dominio.

Cada equipo se entrega una sola vez (por nombre en mayúsculas). Cancelar no
espera a los hilos (pueden estar bloqueados en una llamada de Windows): se
abandonan y sus resultados tardíos se descartan. Sin wx.
"""

from __future__ import annotations

import builtins
import ctypes
import logging
import threading
import time
from collections.abc import Callable, Sequence
from ctypes import wintypes
from dataclasses import dataclass

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


SHELL, MDNS, DOMINIO = "shell", "mdns", "dominio"


@dataclass(frozen=True)
class EquipoRed:
	"""Un equipo encontrado: «DS220», «\\\\DS220», la fuente y su dirección IP si se sabe."""

	nombre: str
	ruta_unc: str
	fuente: str
	direccion: str = ""


Emisor = Callable[[EquipoRed], None]
Fuente = Callable[[Emisor, threading.Event], None]


# ── Fuente 1: carpeta «Red» del shell ─────────────────────────────────────────


def fuente_shell(emitir: Emisor, cancelado: threading.Event) -> None:
	import pythoncom
	from win32com.shell import shell, shellcon

	pythoncom.CoInitialize()
	try:
		pidl = shell.SHGetSpecialFolderLocation(0, shellcon.CSIDL_NETWORK)
		carpeta = shell.SHGetDesktopFolder().BindToObject(pidl, None, shell.IID_IShellFolder)
		enumerador = carpeta.EnumObjects(0, shellcon.SHCONTF_FOLDERS | shellcon.SHCONTF_NONFOLDERS)
		if enumerador is None:
			return
		while not cancelado.is_set():
			elementos = enumerador.Next(1)
			if not elementos:
				break
			try:
				nombre = carpeta.GetDisplayNameOf(elementos[0], shellcon.SHGDN_FORPARSING)
			except Exception:  # noqa: BLE001 - un elemento raro no detiene la búsqueda
				log.debug("Elemento de la carpeta Red sin nombre", exc_info=True)
				continue
			# Los dispositivos SSDP («::{F02C1A0D-...}») y las impresoras no son equipos.
			if isinstance(nombre, str) and nombre.startswith("\\\\"):
				corto = nombre[2:].split("\\", 1)[0]
				if corto:
					emitir(EquipoRed(corto, f"\\\\{corto}", SHELL))
	finally:
		pythoncom.CoUninitialize()


# ── Fuente 2: mDNS con DnsServiceBrowse ───────────────────────────────────────

DNS_TYPE_A = 0x0001
DNS_TYPE_PTR = 0x000C
DNS_TYPE_SRV = 0x0021
DNS_QUERY_REQUEST_VERSION1 = 1
DNS_REQUEST_PENDING = 9506
CONSULTA_SMB = "_smb._tcp.local"
#: Cuánto se escuchan las respuestas mDNS.
SEGUNDOS_MDNS = 10.0


class _DatosPTR(ctypes.Structure):
	_fields_ = [("pNameHost", wintypes.LPWSTR)]


class _DatosSRV(ctypes.Structure):
	_fields_ = [("pNameTarget", wintypes.LPWSTR), ("wPriority", wintypes.WORD), ("wWeight", wintypes.WORD),
		("wPort", wintypes.WORD), ("Pad", wintypes.WORD)]


class _DatosA(ctypes.Structure):
	_fields_ = [("IpAddress", wintypes.DWORD)]


class _Datos(ctypes.Union):
	_fields_ = [("PTR", _DatosPTR), ("SRV", _DatosSRV), ("A", _DatosA), ("relleno", ctypes.c_byte * 64)]


class DNS_RECORDW(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	pass


DNS_RECORDW._fields_ = [
	("pNext", ctypes.POINTER(DNS_RECORDW)), ("pName", wintypes.LPWSTR), ("wType", wintypes.WORD),
	("wDataLength", wintypes.WORD), ("Flags", wintypes.DWORD), ("dwTtl", wintypes.DWORD),
	("dwReserved", wintypes.DWORD), ("Data", _Datos),
]

_RETROLLAMADA = ctypes.WINFUNCTYPE(None, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(DNS_RECORDW))


class _PeticionBrowse(ctypes.Structure):
	_fields_ = [("Version", wintypes.ULONG), ("InterfaceIndex", wintypes.ULONG), ("QueryName", wintypes.LPCWSTR),
		("pBrowseCallback", _RETROLLAMADA), ("pQueryContext", ctypes.c_void_p)]


class _Cancelar(ctypes.Structure):
	_fields_ = [("reserved", ctypes.c_void_p)]


def equipos_de_registros(registros: Sequence[tuple[int, str, str]]) -> list[EquipoRed]:
	"""Equipos de una respuesta mDNS: tuplas (tipo, nombre, dato) de PTR, SRV y A.

	PTR «_smb._tcp.local» → «DS220._smb._tcp.local»; SRV de esa instancia → «ds220.local»;
	A de «ds220.local» → «192.168.1.5». El nombre del equipo es el del destino SRV sin «.local»
	(o, si no llegó, el de la instancia).
	"""
	instancias = [dato for tipo, _nombre, dato in registros if tipo == DNS_TYPE_PTR and dato]
	destinos = {nombre.casefold(): dato for tipo, nombre, dato in registros if tipo == DNS_TYPE_SRV}
	direcciones = {nombre.casefold(): dato for tipo, nombre, dato in registros if tipo == DNS_TYPE_A}
	resultado = []
	for instancia in instancias:
		destino = destinos.get(instancia.casefold(), "")
		nombre = destino.removesuffix(".").removesuffix(".local") if destino else instancia.split(".", 1)[0]
		nombre = nombre.split(".", 1)[0] if nombre else ""
		if nombre:
			resultado.append(EquipoRed(nombre, f"\\\\{nombre}", MDNS, direcciones.get(destino.casefold(), "")))
	return resultado


def _ipv4(valor: int) -> str:
	return ".".join(str((valor >> desplazamiento) & 0xFF) for desplazamiento in (0, 8, 16, 24))


def fuente_mdns(emitir: Emisor, cancelado: threading.Event) -> None:
	try:
		dns = ctypes.WinDLL("dnsapi.dll")
		buscar = dns.DnsServiceBrowse
		cancelar_busqueda = dns.DnsServiceBrowseCancel
		liberar = dns.DnsRecordListFree
	except (AttributeError, OSError):
		log.info("DnsServiceBrowse no está disponible (Windows anterior a 10 1903): sin búsqueda mDNS")
		return

	def recibir(estado, _contexto, registro) -> None:
		filas: list[tuple[int, str, str]] = []
		try:
			actual = registro
			while actual:
				r = actual.contents
				if r.wType == DNS_TYPE_PTR:
					filas.append((DNS_TYPE_PTR, r.pName or "", r.Data.PTR.pNameHost or ""))
				elif r.wType == DNS_TYPE_SRV:
					filas.append((DNS_TYPE_SRV, r.pName or "", r.Data.SRV.pNameTarget or ""))
				elif r.wType == DNS_TYPE_A:
					filas.append((DNS_TYPE_A, r.pName or "", _ipv4(r.Data.A.IpAddress)))
				actual = r.pNext
			if not cancelado.is_set():
				for equipo in equipos_de_registros(filas):
					emitir(equipo)
		except Exception:  # noqa: BLE001 - nunca debe salir una excepción a un hilo de Windows
			log.debug("Respuesta mDNS no válida (estado %s)", estado, exc_info=True)
		finally:
			if registro:
				try:
					liberar(registro, 1)
				except OSError:
					log.debug("DnsRecordListFree falló", exc_info=True)

	retrollamada = _RETROLLAMADA(recibir)
	peticion = _PeticionBrowse(DNS_QUERY_REQUEST_VERSION1, 0, CONSULTA_SMB, retrollamada, None)
	manejador = _Cancelar()
	resultado = buscar(ctypes.byref(peticion), ctypes.byref(manejador))
	if resultado != DNS_REQUEST_PENDING:
		log.info("DnsServiceBrowse devolvió %s: sin búsqueda mDNS", resultado)
		return
	# La búsqueda mDNS no acaba sola: las respuestas llegan en el primer segundo y se escucha un rato más.
	limite = time.monotonic() + SEGUNDOS_MDNS
	try:
		while not cancelado.wait(0.25) and time.monotonic() < limite:
			pass
	finally:
		cancelar_busqueda(ctypes.byref(manejador))
		# La retrollamada puede llegar aún un instante: se mantiene viva hasta aquí.
		del retrollamada


# ── Fuente 3: dominio de Active Directory ────────────────────────────────────

NET_SETUP_DOMAIN_NAME = 3


def en_dominio() -> bool:
	try:
		import win32net

		_nombre, tipo = win32net.NetGetJoinInformation(None)
	except Exception:  # noqa: BLE001 - sin el dato se supone grupo de trabajo
		log.debug("NetGetJoinInformation falló", exc_info=True)
		return False
	return int(tipo) == NET_SETUP_DOMAIN_NAME


def fuente_dominio(emitir: Emisor, cancelado: threading.Event) -> None:
	if not en_dominio():
		return
	import pythoncom
	import win32com.client

	pythoncom.CoInitialize()
	try:
		raiz = win32com.client.GetObject("LDAP://RootDSE").Get("defaultNamingContext")
		conexion = win32com.client.Dispatch("ADODB.Connection")
		conexion.Provider = "ADsDSOObject"
		conexion.Open("Active Directory Provider")
		orden = win32com.client.Dispatch("ADODB.Command")
		orden.ActiveConnection = conexion
		orden.CommandText = f"<LDAP://{raiz}>;(objectCategory=computer);name,dNSHostName;subtree"
		orden.Properties("Page Size").Value = 500
		filas = orden.Execute()[0]
		while not filas.EOF and not cancelado.is_set():
			nombre = str(filas.Fields("name").Value or "")
			if nombre:
				emitir(EquipoRed(nombre, f"\\\\{nombre}", DOMINIO, str(filas.Fields("dNSHostName").Value or "")))
			filas.MoveNext()
	finally:
		pythoncom.CoUninitialize()


# ── Descubrimiento ───────────────────────────────────────────────────────────


class Descubrimiento:
	"""Búsqueda de equipos en marcha (9.2). Tiene ``terminada`` y ``cancelar(motivo)``, como una tarea.

	:param al_encontrar: se llama (en un hilo de trabajo) con cada equipo nuevo, una vez por nombre.
	:param al_terminar: se llama una vez con (equipos, cancelada) al acabar, al agotarse el tiempo o al cancelar.
	:param fuentes: (nombre, función) de cada fuente; por defecto las de la configuración.
	"""

	def __init__(self, al_encontrar: Emisor | None = None, al_terminar: Callable[[list[EquipoRed], bool], None] | None = None,
			tiempo_maximo_s: float = 45, fuentes: Sequence[tuple[str, Fuente]] | None = None,
			mdns: bool = True, dominio: bool = True) -> None:
		self._al_encontrar = al_encontrar
		self._al_terminar = al_terminar
		self.tiempo_maximo_s = max(1.0, float(tiempo_maximo_s))
		self._fuentes = list(fuentes) if fuentes is not None else fuentes_por_defecto(mdns, dominio)
		self._cancelado = threading.Event()
		self._fin = threading.Event()
		self._candado = threading.Lock()
		self._equipos: dict[str, EquipoRed] = {}
		self.cancelada = False
		self.inicio = 0.0

	@property
	def terminada(self) -> bool:
		return self._fin.is_set()

	def equipos(self) -> list[EquipoRed]:
		with self._candado:
			return list(self._equipos.values())

	def iniciar(self) -> Descubrimiento:
		self.inicio = time.monotonic()
		hilos = [threading.Thread(target=self._ejecutar_fuente, args=(nombre, funcion), name=f"red-descubrir-{nombre}", daemon=True)
			for nombre, funcion in self._fuentes]
		for hilo in hilos:
			hilo.start()
		threading.Thread(target=self._vigilar, args=(hilos,), name="red-descubrir", daemon=True).start()
		return self

	def cancelar(self, motivo: str = "") -> None:
		if self._fin.is_set():
			return
		log.info("Búsqueda de equipos cancelada%s", f" ({motivo})" if motivo else "")
		self.cancelada = True
		self._cancelado.set()

	def esperar(self, segundos: float | None = None) -> bool:
		return self._fin.wait(segundos)

	def _emitir(self, equipo: EquipoRed) -> None:
		if self._cancelado.is_set() or self._fin.is_set():
			return
		clave = equipo.nombre.upper()
		with self._candado:
			if clave in self._equipos:
				anterior = self._equipos[clave]
				if not anterior.direccion and equipo.direccion:
					self._equipos[clave] = EquipoRed(anterior.nombre, anterior.ruta_unc, anterior.fuente, equipo.direccion)
				return
			self._equipos[clave] = equipo
		log.debug("Equipo encontrado: %s (%s)", equipo.nombre, equipo.fuente)
		if self._al_encontrar is not None:
			try:
				self._al_encontrar(equipo)
			except Exception:  # noqa: BLE001 - un aviso que falla no detiene la búsqueda
				log.exception("Falló el aviso de equipo encontrado")

	def _ejecutar_fuente(self, nombre: str, funcion: Fuente) -> None:
		try:
			funcion(self._emitir, self._cancelado)
		except Exception:  # noqa: BLE001 - una fuente que falla no deja sin las demás
			log.warning("Falló la búsqueda de equipos por %s", nombre, exc_info=True)

	def _vigilar(self, hilos: list[threading.Thread]) -> None:
		limite = self.inicio + self.tiempo_maximo_s
		for hilo in hilos:
			while hilo.is_alive() and not self._cancelado.is_set():
				restante = limite - time.monotonic()
				if restante <= 0:
					break
				hilo.join(min(0.2, restante))
		# Las fuentes que siguen vivas (bloqueadas en Windows) se abandonan.
		self._cancelado.set()
		with self._candado:
			equipos = list(self._equipos.values())
		self._fin.set()
		log.info("Búsqueda de equipos terminada: %d equipos en %.1f s%s", len(equipos), time.monotonic() - self.inicio,
			" (cancelada)" if self.cancelada else "")
		if self._al_terminar is not None:
			try:
				self._al_terminar(equipos, self.cancelada)
			except Exception:  # noqa: BLE001 - el aviso final no puede tumbar el hilo
				log.exception("Falló el aviso de fin de la búsqueda de equipos")


def fuentes_por_defecto(mdns: bool = True, dominio: bool = True) -> list[tuple[str, Fuente]]:
	fuentes: list[tuple[str, Fuente]] = [(SHELL, fuente_shell)]
	if mdns:
		fuentes.append((MDNS, fuente_mdns))
	if dominio:
		fuentes.append((DOMINIO, fuente_dominio))
	return fuentes
