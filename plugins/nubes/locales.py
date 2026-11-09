# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Carpetas de los programas oficiales de nube que ya hay en este equipo (sin rclone ni credenciales).

OneDrive, Dropbox, Google Drive para escritorio, iCloud para Windows, Box Drive,
pCloud Drive, Proton Drive o Synology Drive dejan en el equipo una carpeta (o una
letra de unidad) con los archivos de la cuenta. Usarla es legítimo y no pide
iniciar sesión: el programa oficial ya la tiene iniciada. Este módulo SOLO busca
rutas; nunca lee ni reutiliza las fichas de acceso de esos programas.

Fuentes, en este orden (la primera que da una ruta gana; no se repiten rutas):

1. Registro de raíces de sincronización de Windows
   (``HKLM\\...\\Explorer\\SyncRootManager\\<Proveedor>!<SID>!<cuenta>``): nombre en
   ``DisplayNameResource`` (cadena indirecta «@...» resuelta con
   ``SHLoadIndirectString``) y ruta en ``UserSyncRoots``, valor con el SID de la
   persona actual.
2. OneDrive: ``HKCU\\Software\\Microsoft\\OneDrive\\Accounts\\Personal`` y
   ``Business1..N`` (``UserFolder``); variables ``OneDriveConsumer``,
   ``OneDriveCommercial`` y ``OneDrive``.
3. Dropbox: ``info.json`` en ``%APPDATA%\\Dropbox`` o ``%LOCALAPPDATA%\\Dropbox``.
4. Google Drive para escritorio: ``DefaultMountPoint`` de ``DriveFS`` (HKCU, HKLM y
   directivas); si no, una unidad con la etiqueta «Google Drive».
5. iCloud (``%USERPROFILE%\\iCloudDrive``), Box Drive (``%USERPROFILE%\\Box``, solo si
   Box Drive está instalado en ``%ProgramFiles%\\Box\\Box``) y pCloud Drive (unidad con
   la etiqueta «pCloud Drive»).

Proton Drive y Synology Drive solo se ven por el registro de sincronización
(Synology Drive, solo con la sincronización bajo demanda). Google Drive para
escritorio en modo réplica (sin letra de unidad) no se detecta: no hay un dato
documentado con su carpeta.

Todo es tolerante: un registro raro, un JSON dañado o una unidad que no responde
se omiten con un ``log.debug`` y nunca rompen el arranque ni el selector de
unidades. Cada comprobación de una carpeta o lectura de un archivo tiene un tope
de tiempo (``TIEMPO_RUTA_S``): una ruta de red sin conexión (``%APPDATA%`` u
OneDrive redirigidos a ``\\\\servidor``) no congela nada. Las rutas tienen que ser
absolutas y de texto; las del registro con variables (``REG_EXPAND_SZ``) se
expanden. Las fuentes del sistema se inyectan (``Fuentes``) para probarlo sin
depender del equipo real.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("zcplugins.zc.nubes")

CLAVE_RAICES = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\SyncRootManager"
CLAVE_ONEDRIVE = r"Software\Microsoft\OneDrive\Accounts"
CLAVES_DRIVEFS = (("HKCU", r"Software\Google\DriveFS"), ("HKLM", r"Software\Google\DriveFS"),
	("HKLM", r"Software\Policies\Google\DriveFS"))
#: Prefijo de la clave del registro de sincronización → nombre del programa.
PROVEEDORES = {"onedrive": "OneDrive", "iclouddrive": "iCloud Drive", "icloud": "iCloud Drive", "synologydrive": "Synology Drive",
	"protondrive": "Proton Drive", "proton": "Proton Drive", "dropbox": "Dropbox", "box": "Box", "googledrivefs": "Google Drive",
	"googledrive": "Google Drive", "drivefs": "Google Drive", "pcloud": "pCloud", "megasync": "MEGA", "mega": "MEGA",
	"nextcloud": "Nextcloud", "owncloud": "ownCloud"}
#: Etiquetas de volumen de los programas que montan una letra de unidad propia.
ETIQUETAS = {"google drive": "Google Drive", "pcloud drive": "pCloud"}

ORIGEN_RAICES = "registro de sincronización de Windows"
ORIGEN_ONEDRIVE = "registro de OneDrive"
ORIGEN_VARIABLE = "variable de entorno"
ORIGEN_DROPBOX = "info.json de Dropbox"
ORIGEN_DRIVEFS = "registro de Google Drive para escritorio"
ORIGEN_ETIQUETA = "etiqueta de la unidad"
ORIGEN_CARPETA = "carpeta conocida"
#: Tope de cada comprobación de una ruta o lectura de un archivo (una ruta de red caída no espera más).
TIEMPO_RUTA_S = 2.0


@dataclass(frozen=True)
class CarpetaNube:
	"""Una carpeta de un programa oficial de nube.

	:param nombre: nombre visible («OneDrive - Personal», «iCloud Drive»).
	:param proveedor: programa o servicio («OneDrive», «Dropbox»).
	:param ruta: ruta local que existe («C:\\Users\\ana\\OneDrive», «G:\\Mi unidad»).
	:param origen: de dónde salió (para el registro y para explicarlo).
	"""

	nombre: str
	proveedor: str
	ruta: str
	origen: str

	@property
	def clave(self) -> str:
		return clave_ruta(self.ruta)


def clave_ruta(ruta: str) -> str:
	"""Ruta normalizada para comparar y para guardar en la configuración («c:\\users\\ana\\onedrive»)."""
	normal = os.path.normcase(os.path.normpath(str(ruta).strip()))
	return normal if re.fullmatch(r"[a-z]:\\", normal) else normal.rstrip("\\/")


# ── Fuentes del sistema (inyectables) ────────────────────────────────────────


@dataclass
class Fuentes:
	"""Lo que se consulta del sistema. Las pruebas sustituyen cada función por una falsa.

	- ``subclaves(raiz, ruta)`` y ``valores(raiz, ruta)``: registro (``raiz`` es «HKLM» o «HKCU»).
	- ``entorno``: variables de entorno.
	- ``existe(ruta)``: si la carpeta existe.
	- ``leer_texto(ruta)``: contenido de un archivo de texto.
	- ``etiquetas()``: ``[(«G:\\», «Google Drive»), ...]`` de las unidades fijas.
	- ``sid``: SID de la persona actual (vacío si no se sabe).
	- ``indirecta(texto)``: resuelve una cadena «@...» del registro.
	"""

	subclaves: Callable[[str, str], list[str]] = field(default=lambda _r, _c: [])
	valores: Callable[[str, str], dict[str, Any]] = field(default=lambda _r, _c: {})
	entorno: dict[str, str] = field(default_factory=dict)
	existe: Callable[[str], bool] = field(default=os.path.isdir)
	leer_texto: Callable[[str], str] = field(default=lambda ruta: Path(ruta).read_text(encoding="utf-8"))
	etiquetas: Callable[[], list[tuple[str, str]]] = field(default=lambda: [])
	sid: str = ""
	indirecta: Callable[[str], str] = field(default=lambda texto: "")


def fuentes_de_windows() -> Fuentes:
	"""Las fuentes reales: ``winreg``, ``os.environ`` y ctypes (``SHLoadIndirectString``, SID y etiquetas)."""
	return Fuentes(subclaves=_subclaves_winreg, valores=_valores_winreg, entorno=dict(os.environ), existe=_existe,
		leer_texto=_leer_con_tope, etiquetas=_etiquetas_unidades, sid=_sid_actual(), indirecta=_cadena_indirecta)


def con_tope(funcion: Callable[[], Any], segundos: float, defecto: Any) -> Any:
	"""``funcion()`` en un hilo aparte; si no termina en ``segundos``, ``defecto`` (el hilo acaba solo, sin esperarlo)."""
	resultado: list[Any] = []
	fallo: list[BaseException] = []

	def correr() -> None:
		try:
			resultado.append(funcion())
		except BaseException as error:  # noqa: BLE001 - se devuelve a quien llama
			fallo.append(error)

	hilo = threading.Thread(target=correr, daemon=True, name="zc-nubes-ruta")
	hilo.start()
	hilo.join(segundos)
	if hilo.is_alive():
		log.debug("Una ruta no respondió en %s s; se omite", segundos)
		return defecto
	if fallo:
		raise fallo[0]
	return resultado[0] if resultado else defecto


def _existe(ruta: str) -> bool:
	def comprobar() -> bool:
		try:
			return os.path.isdir(ruta)
		except (OSError, ValueError):
			return False

	return bool(con_tope(comprobar, TIEMPO_RUTA_S, False))


def _leer_con_tope(ruta: str) -> str:
	texto = con_tope(lambda: Path(ruta).read_text(encoding="utf-8"), TIEMPO_RUTA_S, None)
	if texto is None:
		raise TimeoutError(ruta)
	return texto


def _raiz_winreg(raiz: str) -> Any:
	import winreg

	return winreg.HKEY_LOCAL_MACHINE if raiz == "HKLM" else winreg.HKEY_CURRENT_USER


def _subclaves_winreg(raiz: str, ruta: str) -> list[str]:
	try:
		import winreg

		with winreg.OpenKey(_raiz_winreg(raiz), ruta) as clave:
			numero = winreg.QueryInfoKey(clave)[0]
			return [winreg.EnumKey(clave, i) for i in range(numero)]
	except (ImportError, OSError):
		return []


def _valores_winreg(raiz: str, ruta: str) -> dict[str, Any]:
	try:
		import winreg

		with winreg.OpenKey(_raiz_winreg(raiz), ruta) as clave:
			numero = winreg.QueryInfoKey(clave)[1]
			resultado = {}
			for i in range(numero):
				nombre, valor, tipo = winreg.EnumValue(clave, i)
				if tipo == winreg.REG_EXPAND_SZ and isinstance(valor, str):
					valor = winreg.ExpandEnvironmentStrings(valor)   # «%USERPROFILE%\\OneDrive» → ruta real
				resultado[nombre] = valor
			return resultado
	except (ImportError, OSError):
		return {}


def _cadena_indirecta(texto: str) -> str:
	"""``SHLoadIndirectString`` (shlwapi): «@C:\\...\\x.dll,-101» → el texto de ese recurso; vacío si falla."""
	try:
		import ctypes
		from ctypes import wintypes

		shlwapi = ctypes.WinDLL("shlwapi")
		funcion = shlwapi.SHLoadIndirectString
		funcion.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, ctypes.c_void_p]
		funcion.restype = ctypes.c_long
		bufer = ctypes.create_unicode_buffer(512)
		if funcion(texto, bufer, len(bufer), None) == 0:
			return bufer.value
	except (OSError, AttributeError, ValueError):
		log.debug("No se pudo resolver la cadena indirecta %s", texto, exc_info=True)
	return ""


def _sid_actual() -> str:
	"""SID de la persona que ejecuta zCommander («S-1-5-21-...»), con ctypes; vacío si no se puede saber."""
	try:
		import ctypes
		from ctypes import wintypes

		advapi32 = ctypes.WinDLL("advapi32")
		kernel32 = ctypes.WinDLL("kernel32")
		kernel32.GetCurrentProcess.restype = wintypes.HANDLE
		kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
		kernel32.LocalFree.argtypes = [ctypes.c_void_p]
		advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
		advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
			ctypes.POINTER(wintypes.DWORD)]
		advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
		token = wintypes.HANDLE()
		if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
			return ""
		try:
			tamano = wintypes.DWORD()
			advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(tamano))   # TokenUser
			if not tamano.value:
				return ""
			bufer = ctypes.create_string_buffer(tamano.value)
			if not advapi32.GetTokenInformation(token, 1, bufer, tamano, ctypes.byref(tamano)):
				return ""
			psid = ctypes.cast(bufer, ctypes.POINTER(ctypes.c_void_p))[0]   # TOKEN_USER.User.Sid
			cadena = ctypes.c_void_p()
			if not advapi32.ConvertSidToStringSidW(psid, ctypes.byref(cadena)):
				return ""
			try:
				return ctypes.wstring_at(cadena.value) if cadena.value else ""
			finally:
				kernel32.LocalFree(cadena)
		finally:
			kernel32.CloseHandle(token)
	except (OSError, AttributeError, ValueError):
		log.debug("No se pudo saber el SID de la persona actual", exc_info=True)
		return ""


def _etiquetas_unidades() -> list[tuple[str, str]]:
	"""Etiqueta de volumen de cada unidad FIJA (las de red, extraíbles y ópticas se saltan: pueden tardar)."""
	resultado: list[tuple[str, str]] = []
	try:
		import ctypes
		from ctypes import wintypes

		kernel32 = ctypes.WinDLL("kernel32")
		kernel32.GetLogicalDrives.restype = wintypes.DWORD
		kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
		kernel32.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p,
			ctypes.c_void_p, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
		mapa = kernel32.GetLogicalDrives()
		for indice in range(2, 26):   # sin A: ni B:
			if not mapa & (1 << indice):
				continue
			raiz = f"{chr(ord('A') + indice)}:\\"
			if kernel32.GetDriveTypeW(raiz) != 3:   # DRIVE_FIXED
				continue
			etiqueta = ctypes.create_unicode_buffer(261)
			if kernel32.GetVolumeInformationW(raiz, etiqueta, len(etiqueta), None, None, None, None, 0):
				resultado.append((raiz, etiqueta.value))
	except (OSError, AttributeError, ValueError):
		log.debug("No se pudieron leer las etiquetas de las unidades", exc_info=True)
	return resultado


# ── Detección ──────────────────────────────────────────────────────────────────


def carpetas_de_nube(fuentes: Fuentes | None = None) -> list[CarpetaNube]:
	"""Carpetas de los programas oficiales de nube que existen en este equipo, sin rutas repetidas.

	Nunca lanza: cada fuente que falla se omite (y queda en el registro con ``log.debug``).
	"""
	try:
		fuentes = fuentes or fuentes_de_windows()
		try:
			etiquetas = list(fuentes.etiquetas())   # una sola vez por detección
		except Exception:  # noqa: BLE001 - sin etiquetas, el resto de fuentes sigue
			log.debug("No se pudieron leer las etiquetas de las unidades", exc_info=True)
			etiquetas = []
		fuentes = dataclasses.replace(fuentes, etiquetas=lambda: etiquetas)
	except Exception:  # noqa: BLE001 - sin fuentes no hay carpetas, pero el selector sigue
		log.debug("No se pudieron preparar las fuentes de las carpetas de nube", exc_info=True)
		return []
	resultado: list[CarpetaNube] = []
	vistas: set[str] = set()

	def anadir(carpeta: CarpetaNube | None) -> None:
		if carpeta is None or not isinstance(carpeta.ruta, str) or not carpeta.ruta.strip():
			return
		ruta = os.path.expandvars(carpeta.ruta.strip())
		if not os.path.isabs(ruta) or "%" in ruta:
			return   # una ruta relativa se comprobaría contra la carpeta de trabajo
		carpeta = dataclasses.replace(carpeta, ruta=ruta)
		clave = carpeta.clave
		if clave in vistas:
			return
		try:
			existe = fuentes.existe(ruta)
		except (OSError, ValueError):
			existe = False
		if existe:
			vistas.add(clave)
			resultado.append(carpeta)

	for buscar in (_raices_sincronizacion, _onedrive, _dropbox, _google_drive, _conocidas):
		try:
			for carpeta in buscar(fuentes):
				anadir(carpeta)
		except Exception:  # noqa: BLE001 - una fuente rara no deja sin las demás
			log.debug("Falló la búsqueda de carpetas de nube %s", buscar.__name__, exc_info=True)
	return resultado


def carpeta_google_drive(fuentes: Fuentes | None = None) -> CarpetaNube | None:
	"""La carpeta (o unidad) de Google Drive para escritorio, si está instalado y con la sesión iniciada."""
	return next((c for c in carpetas_de_nube(fuentes) if c.proveedor == "Google Drive"), None)


def _proveedor(prefijo: str) -> str:
	limpio = re.sub(r"[^a-z0-9]", "", prefijo.casefold())
	if limpio in PROVEEDORES:
		return PROVEEDORES[limpio]
	for clave, nombre in PROVEEDORES.items():
		if limpio.startswith(clave):
			return nombre
	return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", prefijo).strip() or prefijo


def _raices_sincronizacion(fuentes: Fuentes) -> list[CarpetaNube]:
	encontradas = []
	perfil = clave_ruta(fuentes.entorno.get("USERPROFILE", "")) if fuentes.entorno.get("USERPROFILE") else ""
	for nombre_clave in fuentes.subclaves("HKLM", CLAVE_RAICES):
		partes = nombre_clave.split("!")
		if len(partes) < 2:
			continue
		prefijo, sid_clave = partes[0], partes[1]
		if fuentes.sid and sid_clave and sid_clave.casefold() != fuentes.sid.casefold():
			continue   # una raíz de otra persona del equipo
		rutas = {k: v for k, v in fuentes.valores("HKLM", rf"{CLAVE_RAICES}\{nombre_clave}\UserSyncRoots").items()
			if isinstance(v, str)}
		ruta = ""
		if fuentes.sid:
			ruta = next((v for k, v in rutas.items() if k.casefold() == fuentes.sid.casefold()), "")
		else:
			# Sin SID: solo rutas dentro del perfil de la persona actual.
			ruta = next((v for v in rutas.values() if perfil and clave_ruta(os.path.expandvars(v)).startswith(perfil)), "")
		if not ruta:
			continue
		proveedor = _proveedor(prefijo)
		datos = fuentes.valores("HKLM", rf"{CLAVE_RAICES}\{nombre_clave}")
		nombre = str(datos.get("DisplayNameResource") or "").strip()
		if nombre.startswith("@"):
			nombre = (fuentes.indirecta(nombre) or "").strip()
		encontradas.append(CarpetaNube(nombre or proveedor, proveedor, ruta, ORIGEN_RAICES))
	return encontradas


def _onedrive(fuentes: Fuentes) -> list[CarpetaNube]:
	encontradas = []
	cuentas = fuentes.subclaves("HKCU", CLAVE_ONEDRIVE)
	orden = sorted(cuentas, key=lambda c: (c.casefold() != "personal", c.casefold()))
	for cuenta in orden:
		if cuenta.casefold() != "personal" and not re.fullmatch(r"(?i)business\d+", cuenta):
			continue
		datos = fuentes.valores("HKCU", rf"{CLAVE_ONEDRIVE}\{cuenta}")
		ruta = datos.get("UserFolder") if isinstance(datos.get("UserFolder"), str) else ""
		if not ruta:
			continue
		if cuenta.casefold() == "personal":
			nombre = "OneDrive - Personal"
		else:
			organizacion = str(datos.get("DisplayName") or "").strip()
			nombre = f"OneDrive - {organizacion}" if organizacion else "OneDrive"
		encontradas.append(CarpetaNube(nombre, "OneDrive", ruta, ORIGEN_ONEDRIVE))
	for variable, nombre in (("OneDriveConsumer", "OneDrive - Personal"), ("OneDriveCommercial", "OneDrive"), ("OneDrive", "OneDrive")):
		ruta = str(fuentes.entorno.get(variable, "") or "").strip()
		if ruta:
			encontradas.append(CarpetaNube(nombre, "OneDrive", ruta, ORIGEN_VARIABLE))
	return encontradas


def _dropbox(fuentes: Fuentes) -> list[CarpetaNube]:
	encontradas = []
	for variable in ("APPDATA", "LOCALAPPDATA"):
		base = fuentes.entorno.get(variable, "")
		if not base:
			continue
		archivo = os.path.join(base, "Dropbox", "info.json")
		try:
			datos = json.loads(fuentes.leer_texto(archivo))
		except FileNotFoundError:
			continue
		except (OSError, ValueError, UnicodeDecodeError):
			log.debug("info.json de Dropbox no legible en %s", archivo, exc_info=True)
			continue
		if not isinstance(datos, dict):
			continue
		for tipo, nombre in (("personal", "Dropbox"), ("business", "Dropbox (empresa)")):
			cuenta = datos.get(tipo)
			if isinstance(cuenta, dict) and isinstance(cuenta.get("path"), str) and cuenta["path"].strip():
				encontradas.append(CarpetaNube(nombre, "Dropbox", cuenta["path"].strip(), ORIGEN_DROPBOX))
	return encontradas


def _punto_de_montaje(valor: Any) -> str:
	"""«G», «G:», «G:\\» o una ruta → ruta utilizable; vacío si no lo parece."""
	texto = str(valor or "").strip().strip('"')
	if len(texto) == 1 and texto.isalpha():
		return f"{texto.upper()}:\\"
	if len(texto) == 2 and texto[0].isalpha() and texto[1] == ":":
		return texto.upper() + "\\"
	if (len(texto) >= 3 and texto[1:3] == ":\\") or texto.startswith("\\\\"):
		return texto
	return ""


def _google_drive(fuentes: Fuentes) -> list[CarpetaNube]:
	puntos = []
	for raiz, clave in CLAVES_DRIVEFS:
		punto = _punto_de_montaje(fuentes.valores(raiz, clave).get("DefaultMountPoint"))
		if punto:
			puntos.append((punto, ORIGEN_DRIVEFS))
	for unidad, etiqueta in fuentes.etiquetas():
		if etiqueta.strip().casefold() == "google drive":
			puntos.append((_punto_de_montaje(unidad), ORIGEN_ETIQUETA))
	encontradas = []
	for punto, origen in puntos:
		if not punto:
			continue
		# «Mi unidad» (o «My Drive») es donde están los archivos; si no se ve, la raíz de la unidad.
		elegida = punto
		for sub in ("Mi unidad", "My Drive"):
			candidata = os.path.join(punto, sub)
			try:
				if fuentes.existe(candidata):
					elegida = candidata
					break
			except (OSError, ValueError):
				continue
		encontradas.append(CarpetaNube("Google Drive", "Google Drive", elegida, origen))
	return encontradas


def _conocidas(fuentes: Fuentes) -> list[CarpetaNube]:
	encontradas = []
	perfil = fuentes.entorno.get("USERPROFILE", "")
	if perfil:
		encontradas.append(CarpetaNube("iCloud Drive", "iCloud Drive", os.path.join(perfil, "iCloudDrive"), ORIGEN_CARPETA))
		# «%USERPROFILE%\\Box» puede ser cualquier carpeta: solo cuenta si Box Drive está instalado.
		programas = fuentes.entorno.get("ProgramFiles") or fuentes.entorno.get("PROGRAMFILES") or ""
		if programas and fuentes.existe(os.path.join(programas, "Box", "Box")):
			encontradas.append(CarpetaNube("Box", "Box", os.path.join(perfil, "Box"), ORIGEN_CARPETA))
	for unidad, etiqueta in fuentes.etiquetas():
		proveedor = ETIQUETAS.get(etiqueta.strip().casefold())
		if proveedor == "pCloud":
			encontradas.append(CarpetaNube("pCloud Drive", "pCloud", _punto_de_montaje(unidad), ORIGEN_ETIQUETA))
	return encontradas


def nombres_para_frase(carpetas: list[CarpetaNube]) -> str:
	"""«OneDrive - Personal», «OneDrive - Personal e iCloud Drive», «A, B y C» (con «e» ante «i»)."""
	nombres = [c.nombre for c in carpetas]
	if not nombres:
		return ""
	if len(nombres) == 1:
		return nombres[0]
	ultimo = nombres[-1]
	union = "e" if re.match(r"(?i)h?i(?![aeiouáéíóú])", ultimo) else "y"
	return f"{', '.join(nombres[:-1])} {union} {ultimo}"
