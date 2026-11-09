# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Firma Authenticode de ejecutables e instaladores con ``WinVerifyTrust`` (diseño 2.0, 11.19). Sin wx.

Dos clases de firma:

- **Incrustada** en el propio archivo (instaladores, programas de terceros).
- **De catálogo**: muchos archivos de Windows (``notepad.exe``) no llevan la
  firma dentro; su suma está en un catálogo ``.cat`` firmado. Se busca con
  ``CryptCATAdminCalcHashFromFileHandle2`` y ``CryptCATAdminEnumCatalogFromHash``
  y se verifica con ``WTD_CHOICE_CATALOG``.

Nunca se consulta la red: sin comprobación de revocación y solo con lo que
Windows ya tiene en caché (``WTD_CACHE_ONLY_URL_RETRIEVAL``). Así comprobar una
columna de 300 archivos no hace 300 conexiones ni se cuelga sin red.

El nombre del firmante sale de la cadena que ya ha construido ``WinVerifyTrust``
(``WTHelperProvDataFromStateData``) con ``CertGetNameStringW``.
"""

from __future__ import annotations

import ctypes
import logging
import uuid
from ctypes import wintypes
from dataclasses import dataclass

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_seguridad")

VALIDA = "valida"
NO_VALIDA = "no_valida"
SIN_FIRMA = "sin_firma"
ERROR = "error"

INCRUSTADA = "incrustada"
CATALOGO = "catalogo"

WTD_UI_NONE = 2
WTD_REVOKE_NONE = 0
WTD_CHOICE_FILE = 1
WTD_CHOICE_CATALOG = 2
WTD_STATEACTION_VERIFY = 1
WTD_STATEACTION_CLOSE = 2
WTD_REVOCATION_CHECK_NONE = 0x10
WTD_CACHE_ONLY_URL_RETRIEVAL = 0x1000
CERT_NAME_SIMPLE_DISPLAY_TYPE = 4

TRUST_E_NOSIGNATURE = 0x800B0100
TRUST_E_SUBJECT_FORM_UNKNOWN = 0x800B0003
TRUST_E_PROVIDER_UNKNOWN = 0x800B0001
TRUST_E_BAD_DIGEST = 0x80096010
TRUST_E_EXPLICIT_DISTRUST = 0x800B0111
TRUST_E_SUBJECT_NOT_TRUSTED = 0x800B0004
CERT_E_EXPIRED = 0x800B0101
CERT_E_UNTRUSTEDROOT = 0x800B0109
CERT_E_REVOKED = 0x800B010C
CERT_E_CHAINING = 0x800B010A
CRYPT_E_SECURITY_SETTINGS = 0x80092026

_SIN_FIRMA = {TRUST_E_NOSIGNATURE, TRUST_E_SUBJECT_FORM_UNKNOWN, TRUST_E_PROVIDER_UNKNOWN}
_MOTIVOS = {
	TRUST_E_BAD_DIGEST: "el archivo ha cambiado después de firmarse",
	TRUST_E_EXPLICIT_DISTRUST: "el firmante está bloqueado en Windows",
	TRUST_E_SUBJECT_NOT_TRUSTED: "la firma no es de confianza",
	CERT_E_EXPIRED: "el certificado ha caducado",
	CERT_E_UNTRUSTEDROOT: "el certificado no viene de una autoridad de confianza",
	CERT_E_REVOKED: "el certificado está revocado",
	CERT_E_CHAINING: "no se pudo comprobar la cadena del certificado",
	CRYPT_E_SECURITY_SETTINGS: "la configuración de seguridad de Windows no la admite",
}

#: Extensiones con firma Authenticode posible (las de la columna Firma y de la información).
EXTENSIONES = ("exe", "dll", "msi", "msix", "appx", "sys", "ocx", "cab", "cat", "ps1", "psm1", "vbs", "js", "scr", "cpl", "drv", "efi", "mui")


class GUID(ctypes.Structure):
	_fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

	@classmethod
	def de(cls, texto: str) -> GUID:
		valor = uuid.UUID(texto)
		guid = cls()
		guid.Data1, guid.Data2, guid.Data3 = valor.fields[0], valor.fields[1], valor.fields[2]
		for indice, octeto in enumerate(valor.bytes[8:]):
			guid.Data4[indice] = octeto
		return guid


WINTRUST_ACTION_GENERIC_VERIFY_V2 = GUID.de("00AAC56B-CD44-11d0-8CC2-00C04FC295EE")
DRIVER_ACTION_VERIFY = GUID.de("F750E6C3-38EE-11d1-85E5-00C04FC295EE")


class WINTRUST_FILE_INFO(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [("cbStruct", wintypes.DWORD), ("pcwszFilePath", wintypes.LPCWSTR), ("hFile", wintypes.HANDLE),
		("pgKnownSubject", ctypes.POINTER(GUID))]


class WINTRUST_CATALOG_INFO(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [("cbStruct", wintypes.DWORD), ("dwCatalogVersion", wintypes.DWORD), ("pcwszCatalogFilePath", wintypes.LPCWSTR),
		("pcwszMemberTag", wintypes.LPCWSTR), ("pcwszMemberFilePath", wintypes.LPCWSTR), ("hMemberFile", wintypes.HANDLE),
		("pbCalculatedFileHash", ctypes.POINTER(ctypes.c_ubyte)), ("cbCalculatedFileHash", wintypes.DWORD),
		("pcCatalogContext", ctypes.c_void_p), ("hCatAdmin", wintypes.HANDLE)]


class WINTRUST_DATA(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [("cbStruct", wintypes.DWORD), ("pPolicyCallbackData", ctypes.c_void_p), ("pSIPClientData", ctypes.c_void_p),
		("dwUIChoice", wintypes.DWORD), ("fdwRevocationChecks", wintypes.DWORD), ("dwUnionChoice", wintypes.DWORD),
		("pUnion", ctypes.c_void_p), ("dwStateAction", wintypes.DWORD), ("hWVTStateData", wintypes.HANDLE),
		("pwszURLReference", wintypes.LPCWSTR), ("dwProvFlags", wintypes.DWORD), ("dwUIContext", wintypes.DWORD),
		("pSignatureSettings", ctypes.c_void_p)]


class CATALOG_INFO(ctypes.Structure):  # noqa: N801 - nombre de la API de Windows
	_fields_ = [("cbStruct", wintypes.DWORD), ("wszCatalogFile", wintypes.WCHAR * 260)]


@dataclass(frozen=True)
class ResultadoFirma:
	estado: str
	firmante: str = ""
	tipo: str = ""
	codigo: int = 0

	@property
	def texto(self) -> str:
		"""«Firmado por Mozilla Corporation, firma válida», «Sin firma» o «Firma no válida: ...»."""
		if self.estado == VALIDA:
			por = _(" (catálogo de Windows)") if self.tipo == CATALOGO else ""
			return _("Firmado por {f}, firma válida{c}").format(f=self.firmante or _("firmante desconocido"), c=por)
		if self.estado == SIN_FIRMA:
			return _("Sin firma")
		if self.estado == NO_VALIDA:
			motivo = _MOTIVOS.get(self.codigo, "")
			quien = _(" de {f}").format(f=self.firmante) if self.firmante else ""
			return _("Firma no válida{q}: {m}").format(q=quien, m=_(motivo)) if motivo else _("Firma no válida{q}").format(q=quien)
		return _("No se pudo comprobar la firma")

	@property
	def corto(self) -> str:
		"""Texto de la columna Firma."""
		if self.estado == VALIDA:
			return self.firmante or _("Válida")
		return {SIN_FIRMA: _("Sin firma"), NO_VALIDA: _("No válida")}.get(self.estado, _("Sin datos"))

	@property
	def sospechosa(self) -> bool:
		return self.estado in (SIN_FIRMA, NO_VALIDA)


_DLL: dict[str, ctypes.WinDLL] = {}


def _dll(nombre: str) -> ctypes.WinDLL:
	if nombre not in _DLL:
		_DLL[nombre] = ctypes.WinDLL(nombre, use_last_error=True)
		_preparar(nombre, _DLL[nombre])
	return _DLL[nombre]


def _preparar(nombre: str, dll: ctypes.WinDLL) -> None:
	if nombre == "wintrust":
		dll.WinVerifyTrust.argtypes = [wintypes.HWND, ctypes.POINTER(GUID), ctypes.POINTER(WINTRUST_DATA)]
		dll.WinVerifyTrust.restype = ctypes.c_long
		dll.WTHelperProvDataFromStateData.argtypes = [wintypes.HANDLE]
		dll.WTHelperProvDataFromStateData.restype = ctypes.c_void_p
		dll.WTHelperGetProvSignerFromChain.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
		dll.WTHelperGetProvSignerFromChain.restype = ctypes.c_void_p
		dll.WTHelperGetProvCertFromChain.argtypes = [ctypes.c_void_p, wintypes.DWORD]
		dll.WTHelperGetProvCertFromChain.restype = ctypes.c_void_p
		dll.CryptCATAdminAcquireContext2.argtypes = [ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(GUID), wintypes.LPCWSTR,
			ctypes.c_void_p, wintypes.DWORD]
		dll.CryptCATAdminCalcHashFromFileHandle2.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
			ctypes.POINTER(ctypes.c_ubyte), wintypes.DWORD]
		dll.CryptCATAdminEnumCatalogFromHash.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_ubyte), wintypes.DWORD,
			wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
		dll.CryptCATAdminEnumCatalogFromHash.restype = wintypes.HANDLE
		dll.CryptCATCatalogInfoFromContext.argtypes = [wintypes.HANDLE, ctypes.POINTER(CATALOG_INFO), wintypes.DWORD]
		dll.CryptCATAdminReleaseCatalogContext.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD]
		dll.CryptCATAdminReleaseContext.argtypes = [wintypes.HANDLE, wintypes.DWORD]
	elif nombre == "crypt32":
		dll.CertGetNameStringW.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.LPWSTR,
			wintypes.DWORD]
		dll.CertGetNameStringW.restype = wintypes.DWORD
	elif nombre == "kernel32":
		dll.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
			wintypes.DWORD, wintypes.HANDLE]
		dll.CreateFileW.restype = wintypes.HANDLE
		dll.CloseHandle.argtypes = [wintypes.HANDLE]


def _firmante(datos: WINTRUST_DATA) -> str:
	wintrust = _dll("wintrust")
	proveedor = wintrust.WTHelperProvDataFromStateData(datos.hWVTStateData)
	if not proveedor:
		return ""
	firmante = wintrust.WTHelperGetProvSignerFromChain(proveedor, 0, False, 0)
	if not firmante:
		return ""
	certificado = wintrust.WTHelperGetProvCertFromChain(firmante, 0)
	if not certificado:
		return ""
	# CRYPT_PROVIDER_CERT: DWORD cbStruct; PCCERT_CONTEXT pCert; ... (pCert va alineado al tamaño de un puntero).
	contexto = ctypes.c_void_p.from_address(certificado + ctypes.sizeof(ctypes.c_void_p)).value
	if not contexto:
		return ""
	bufer = ctypes.create_unicode_buffer(512)
	_dll("crypt32").CertGetNameStringW(contexto, CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, None, bufer, len(bufer))
	return bufer.value


def _verificar(eleccion: int, union: ctypes.Structure) -> tuple[int, str]:
	datos = WINTRUST_DATA()
	datos.cbStruct = ctypes.sizeof(WINTRUST_DATA)
	datos.dwUIChoice = WTD_UI_NONE
	datos.fdwRevocationChecks = WTD_REVOKE_NONE
	datos.dwUnionChoice = eleccion
	datos.pUnion = ctypes.cast(ctypes.pointer(union), ctypes.c_void_p)
	datos.dwStateAction = WTD_STATEACTION_VERIFY
	datos.dwProvFlags = WTD_REVOCATION_CHECK_NONE | WTD_CACHE_ONLY_URL_RETRIEVAL
	wintrust = _dll("wintrust")
	accion = GUID.de("00AAC56B-CD44-11d0-8CC2-00C04FC295EE")
	codigo = wintrust.WinVerifyTrust(None, ctypes.byref(accion), ctypes.byref(datos)) & 0xFFFFFFFF
	try:
		firmante = _firmante(datos) if codigo not in _SIN_FIRMA else ""
	except OSError:
		log.debug("No se pudo leer el firmante", exc_info=True)
		firmante = ""
	finally:
		datos.dwStateAction = WTD_STATEACTION_CLOSE
		wintrust.WinVerifyTrust(None, ctypes.byref(accion), ctypes.byref(datos))
	return codigo, firmante


def _incrustada(ruta: str) -> tuple[int, str]:
	info = WINTRUST_FILE_INFO()
	info.cbStruct = ctypes.sizeof(WINTRUST_FILE_INFO)
	info.pcwszFilePath = ruta
	return _verificar(WTD_CHOICE_FILE, info)


def _de_catalogo(ruta: str) -> tuple[int, str] | None:
	"""Verificación por catálogo; ``None`` si la suma del archivo no está en ningún catálogo del sistema."""
	wintrust = _dll("wintrust")
	kernel32 = _dll("kernel32")
	for algoritmo in ("SHA256", None):
		administrador = wintypes.HANDLE()
		if not wintrust.CryptCATAdminAcquireContext2(ctypes.byref(administrador), ctypes.byref(DRIVER_ACTION_VERIFY), algoritmo,
				None, 0):
			continue
		archivo = kernel32.CreateFileW(ruta, 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0, None)
		if not archivo or archivo == wintypes.HANDLE(-1).value:
			wintrust.CryptCATAdminReleaseContext(administrador, 0)
			raise OSError(ctypes.get_last_error(), _("No se pudo abrir el archivo"))
		try:
			tamano = wintypes.DWORD(0)
			wintrust.CryptCATAdminCalcHashFromFileHandle2(administrador, archivo, ctypes.byref(tamano), None, 0)
			if not tamano.value:
				continue
			suma = (ctypes.c_ubyte * tamano.value)()
			if not wintrust.CryptCATAdminCalcHashFromFileHandle2(administrador, archivo, ctypes.byref(tamano), suma, 0):
				continue
			catalogo = wintrust.CryptCATAdminEnumCatalogFromHash(administrador, suma, tamano, 0, None)
			if not catalogo:
				continue
			try:
				info_catalogo = CATALOG_INFO()
				info_catalogo.cbStruct = ctypes.sizeof(CATALOG_INFO)
				if not wintrust.CryptCATCatalogInfoFromContext(catalogo, ctypes.byref(info_catalogo), 0):
					continue
				info = WINTRUST_CATALOG_INFO()
				info.cbStruct = ctypes.sizeof(WINTRUST_CATALOG_INFO)
				info.pcwszCatalogFilePath = info_catalogo.wszCatalogFile
				info.pcwszMemberTag = bytes(suma).hex().upper()
				info.pcwszMemberFilePath = ruta
				info.pbCalculatedFileHash = suma
				info.cbCalculatedFileHash = tamano.value
				info.hCatAdmin = administrador
				return _verificar(WTD_CHOICE_CATALOG, info)
			finally:
				wintrust.CryptCATAdminReleaseCatalogContext(administrador, catalogo, 0)
		finally:
			kernel32.CloseHandle(archivo)
			wintrust.CryptCATAdminReleaseContext(administrador, 0)
	return None


def verificar(ruta: str) -> ResultadoFirma:
	"""Firma de un archivo local, sin red [trabajo]."""
	try:
		codigo, firmante = _incrustada(ruta)
		if codigo == 0:
			return ResultadoFirma(VALIDA, firmante, INCRUSTADA)
		if codigo not in _SIN_FIRMA:
			return ResultadoFirma(NO_VALIDA, firmante, INCRUSTADA, codigo)
		catalogo = _de_catalogo(ruta)
		if catalogo is None:
			return ResultadoFirma(SIN_FIRMA, codigo=codigo)
		codigo, firmante = catalogo
		if codigo == 0:
			return ResultadoFirma(VALIDA, firmante, CATALOGO)
		return ResultadoFirma(NO_VALIDA, firmante, CATALOGO, codigo)
	except OSError as error:
		log.info("No se pudo comprobar la firma de %s: %s", ruta, error)
		return ResultadoFirma(ERROR, codigo=getattr(error, "winerror", 0) or 0)


def admite_firma(nombre: str) -> bool:
	return nombre.rsplit(".", 1)[-1].casefold() in EXTENSIONES if "." in nombre else False
