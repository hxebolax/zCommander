# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sumas, marca de la Web, datos del ejecutable, Defender y VirusTotal (diseño 2.0, 11.19). Sin wx.

Todo lo que interpreta una salida (la de ``MpCmdRun.exe``, el JSON de
VirusTotal, la suma que hay en el portapapeles) es una función pura que se
prueba con ejemplos guardados, sin ejecutar Defender ni conectarse a nada.
"""

from __future__ import annotations

import glob
import hashlib
import logging
import os
import re
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_seguridad")

# ── Sumas ─────────────────────────────────────────────────────────────────────

#: Longitud en cifras hexadecimales → algoritmo.
POR_LONGITUD = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}
NOMBRES = {"md5": "MD5", "sha1": "SHA-1", "sha256": "SHA-256", "sha512": "SHA-512"}


def extraer_suma(texto: str) -> tuple[str, str] | None:
	"""(algoritmo, suma en minúsculas) de un texto copiado, o ``None``.

	Acepta mayúsculas o minúsculas, espacios entre los grupos («AB CD EF...»),
	una etiqueta delante («SHA256: ...», «SHA-256 = ...») y el formato de
	``sha256sum`` («<suma>  nombre.zip»).
	"""
	if not texto:
		return None
	limpio = texto.strip()
	sin_etiqueta = re.sub(r"^\s*(sha-?(1|256|512)|md5)\s*(\(.*?\))?\s*[:=]?\s*", "", limpio, flags=re.IGNORECASE)
	compacto = re.sub(r"[\s:]+", "", sin_etiqueta)
	if re.fullmatch(r"[0-9a-fA-F]+", compacto) and len(compacto) in POR_LONGITUD:
		return POR_LONGITUD[len(compacto)], compacto.lower()
	for candidato in re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,128}(?![0-9a-fA-F])", limpio):
		if len(candidato) in POR_LONGITUD:
			return POR_LONGITUD[len(candidato)], candidato.lower()
	return None


def calcular_suma(lector: Any, algoritmo: str, comprobar: Callable[[], None] | None = None) -> str:
	"""Suma de un flujo abierto [trabajo]."""
	suma = hashlib.new(algoritmo)
	while True:
		if comprobar is not None:
			comprobar()
		bloque = lector.read(1024 * 1024)
		if not bloque:
			return suma.hexdigest()
		suma.update(bloque)


# ── Marca de la Web (flujo Zone.Identifier) ─────────────────────────────────

FLUJO = ":Zone.Identifier"
ZONAS = {0: "Este equipo", 1: "Intranet", 2: "Sitios de confianza", 3: "Internet", 4: "Sitios restringidos"}


@dataclass(frozen=True)
class MarcaWeb:
	zona: int
	origen: str = ""
	referente: str = ""

	@property
	def texto(self) -> str:
		return _(ZONAS.get(self.zona, "Zona {z}")).format(z=self.zona)

	@property
	def descripcion(self) -> str:
		"""«Descargado de Internet: https://ejemplo.org/x.zip»."""
		donde = self.origen or self.referente
		base = _("Descargado de {z}").format(z=self.texto.lower() if self.zona != 3 else _("Internet"))
		return f"{base}: {donde}" if donde else base


def leer_marca(ruta: str) -> MarcaWeb | None:
	"""La marca de la Web de un archivo local, o ``None`` si no la tiene (o el disco no admite flujos)."""
	try:
		with open(ruta + FLUJO, encoding="utf-8", errors="replace") as flujo:
			contenido = flujo.read(64 * 1024)
	except OSError:
		return None
	valores = dict(re.findall(r"^\s*(\w+)\s*=\s*(.*?)\s*$", contenido, flags=re.MULTILINE))
	try:
		zona = int(valores.get("ZoneId", "3"))
	except ValueError:
		zona = 3
	return MarcaWeb(zona, valores.get("HostUrl", ""), valores.get("ReferrerUrl", ""))


def quitar_marca(ruta: str) -> bool:
	"""Borra el flujo ``Zone.Identifier``. Falso si no tenía."""
	try:
		os.remove(ruta + FLUJO)
		return True
	except FileNotFoundError:
		return False


# ── Datos del ejecutable ─────────────────────────────────────────────────────

MAQUINAS = {0x014C: "x86 (32 bits)", 0x8664: "x64 (64 bits)", 0xAA64: "ARM64", 0x01C4: "ARM (32 bits)", 0x0200: "Itanium"}


def arquitectura(ruta: str) -> str:
	"""Arquitectura de un ejecutable PE leyendo su cabecera; ``""`` si no es un PE."""
	try:
		with open(ruta, "rb") as archivo:
			cabecera = archivo.read(64)
			if len(cabecera) < 64 or cabecera[:2] != b"MZ":
				return ""
			archivo.seek(struct.unpack_from("<I", cabecera, 0x3C)[0])
			pe = archivo.read(6)
	except OSError:
		return ""
	if len(pe) < 6 or pe[:4] != b"PE\0\0":
		return ""
	maquina = struct.unpack_from("<H", pe, 4)[0]
	return _(MAQUINAS.get(maquina, "Desconocida ({m:#06x})")).format(m=maquina)


def datos_ejecutable(ruta: str) -> dict[str, str]:
	"""Empresa, producto, descripción, versión y arquitectura (``win32api.GetFileVersionInfo``)."""
	datos: dict[str, str] = {}
	try:
		import win32api

		traducciones = win32api.GetFileVersionInfo(ruta, "\\VarFileInfo\\Translation") or [(0x0409, 0x04B0)]
		idioma, pagina = traducciones[0]
		for clave, nombre in (("CompanyName", "empresa"), ("ProductName", "producto"), ("FileDescription", "descripcion"),
				("ProductVersion", "version_producto"), ("FileVersion", "version")):
			valor = win32api.GetFileVersionInfo(ruta, f"\\StringFileInfo\\{idioma:04x}{pagina:04x}\\{clave}")
			if valor:
				datos[nombre] = str(valor).strip()
	except Exception:  # noqa: BLE001 - un ejecutable sin recurso de versión es normal
		log.debug("Sin información de versión en %s", ruta, exc_info=True)
	maquina = arquitectura(ruta)
	if maquina:
		datos["arquitectura"] = maquina
	return datos


def lineas_ejecutable(datos: dict[str, str]) -> list[str]:
	etiquetas = (("empresa", _("Empresa")), ("producto", _("Producto")), ("descripcion", _("Descripción")),
		("version", _("Versión del archivo")), ("version_producto", _("Versión del producto")), ("arquitectura", _("Arquitectura")))
	return [f"{texto}: {datos[clave]}" for clave, texto in etiquetas if datos.get(clave)]


# ── Microsoft Defender ────────────────────────────────────────────────────────


def ruta_mpcmdrun() -> str:
	"""``MpCmdRun.exe`` de la plataforma más reciente de Defender, o el de Archivos de programa; ``""`` si no hay."""
	datos_programa = os.environ.get("ProgramData", r"C:\ProgramData")
	candidatos = glob.glob(os.path.join(datos_programa, "Microsoft", "Windows Defender", "Platform", "*", "MpCmdRun.exe"))

	def version(ruta: str) -> tuple[int, ...]:
		partes = re.findall(r"\d+", os.path.basename(os.path.dirname(ruta)))
		return tuple(int(p) for p in partes)

	for candidato in sorted(candidatos, key=version, reverse=True):
		if os.path.isfile(candidato):
			return candidato
	clasico = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Windows Defender", "MpCmdRun.exe")
	return clasico if os.path.isfile(clasico) else ""


def argumentos_defender(mpcmdrun: str, ruta: str) -> list[str]:
	"""Análisis de un archivo o carpeta sin limpiar nada (la persona decide qué hacer)."""
	return [mpcmdrun, "-Scan", "-ScanType", "3", "-File", ruta, "-DisableRemediation"]


@dataclass(frozen=True)
class ResultadoDefender:
	amenazas: tuple[str, ...] = ()
	error: str = ""
	analizado: bool = False

	@property
	def texto(self) -> str:
		if self.error:
			return _("Defender no pudo analizarlo: {e}").format(e=self.error)
		if self.amenazas:
			return _n("Defender encontró {n} amenaza: {l}", "Defender encontró {n} amenazas: {l}", len(self.amenazas)).format(
				n=len(self.amenazas), l=", ".join(self.amenazas))
		return _("Defender no encontró amenazas")


def interpretar_defender(salida: str, codigo: int) -> ResultadoDefender:
	"""Lee la salida de ``MpCmdRun.exe -Scan`` (en inglés en todas las versiones) y su código de salida.

	0: sin amenazas; 2: amenazas (se leen las líneas «Threat : ...»); otro: error
	(se toma la línea «failed with hr = 0x...» si la hay).
	"""
	amenazas = tuple(dict.fromkeys(m.strip() for m in re.findall(r"^\s*Threat\s*:\s*(.+?)\s*$", salida, flags=re.MULTILINE)))
	encontradas = re.search(r"found\s+(\d+)\s+threats?", salida, flags=re.IGNORECASE)
	if amenazas or codigo == 2 or (encontradas and int(encontradas.group(1)) > 0):
		return ResultadoDefender(amenazas or (_("amenaza sin nombre"),), analizado=True)
	if codigo == 0 or re.search(r"found no threats", salida, flags=re.IGNORECASE):
		return ResultadoDefender(analizado=True)
	fallo = re.search(r"failed with hr\s*=\s*(0x[0-9a-fA-F]+)", salida, flags=re.IGNORECASE)
	detalle = fallo.group(1) if fallo else (salida.strip().splitlines()[-1] if salida.strip() else _("código {c}").format(c=codigo))
	return ResultadoDefender(error=detalle)


# ── VirusTotal (solo el hash, nunca el archivo) ──────────────────────────────

HOST_VIRUSTOTAL = "www.virustotal.com"


def url_virustotal(sha256: str) -> str:
	if not re.fullmatch(r"[0-9a-f]{64}", sha256):
		raise ValueError(sha256)
	return f"https://{HOST_VIRUSTOTAL}/api/v3/files/{sha256}"


@dataclass(frozen=True)
class ResultadoVirusTotal:
	conocido: bool
	maliciosos: int = 0
	sospechosos: int = 0
	total: int = 0
	etiqueta: str = ""
	nombres: tuple[str, ...] = field(default=())

	@property
	def amenaza(self) -> bool:
		return self.maliciosos > 0

	@property
	def texto(self) -> str:
		if not self.conocido:
			return _("VirusTotal no conoce este archivo (nadie lo ha enviado para analizar)")
		texto = _("VirusTotal: {m} de {t} antivirus lo detectan").format(m=self.maliciosos, t=self.total)
		if self.sospechosos:
			texto += _n(", {n} lo ve sospechoso", ", {n} lo ven sospechoso", self.sospechosos).format(n=self.sospechosos)
		if self.etiqueta and self.maliciosos:
			texto += _(", como {e}").format(e=self.etiqueta)
		return texto


def interpretar_virustotal(datos: dict) -> ResultadoVirusTotal:
	"""Lee la respuesta de ``GET /api/v3/files/{hash}``."""
	atributos = (datos.get("data") or {}).get("attributes") or {}
	estadisticas = atributos.get("last_analysis_stats") or {}
	total = sum(int(v) for v in estadisticas.values() if isinstance(v, int))
	etiqueta = ((atributos.get("popular_threat_classification") or {}).get("suggested_threat_label") or "")
	return ResultadoVirusTotal(True, int(estadisticas.get("malicious", 0)), int(estadisticas.get("suspicious", 0)), total,
		str(etiqueta), tuple(str(n) for n in (atributos.get("names") or [])[:5]))
