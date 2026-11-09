# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Información de una unidad o ruta de red (diseño 2.0, 9.6).

Junta lo que Windows sabe de una conexión: espacio (``GetDiskFreeSpaceEx``),
volumen (``GetVolumeInformation``), remoto, usuario y proveedor
(``WNetGetConnection``, ``WNetGetUser``), estado (``NetUseEnum`` nivel 2) y el
detalle SMB por WMI (``MSFT_SmbConnection``: dialecto, cifrado, firma y
archivos abiertos; ``MSFT_SmbMultichannelConnection``: velocidad del enlace),
lo mismo que ``Get-SmbConnection`` sin lanzar PowerShell.

Cada parte es independiente: si una falla (WMI sin permiso, servidor caído),
las demás siguen y el fallo queda en el registro. Bloquea: se llama en un
hilo. Sin wx.
"""

from __future__ import annotations

import builtins
import logging
import shutil
from dataclasses import dataclass, field

from app.services import formato
from app.services.windows import red

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class InfoRed:
	"""Lo que se sabe de una conexión de red. Los campos desconocidos quedan vacíos, en −1 o en ``None``."""

	ruta: str
	letra: str = ""
	remoto: str = ""
	usuario: str = ""
	proveedor: str = ""
	estado: str = ""
	libre: int = -1
	total: int = -1
	etiqueta: str = ""
	sistema_archivos: str = ""
	dialecto: str = ""
	cifrada: bool | None = None
	firmada: bool | None = None
	archivos_abiertos: int = -1
	velocidad_bps: int = 0
	notas: list[str] = field(default_factory=list)

	@property
	def nombre(self) -> str:
		return self.letra or self.remoto or self.ruta

	def texto_protocolo(self) -> str:
		"""«SMB 3.1.1 cifrada», «SMB 3.0 firmada», «SMB 2.1» o «»."""
		if not self.dialecto:
			return ""
		texto = _("SMB {d}").format(d=self.dialecto)
		if self.cifrada:
			texto += " " + _("cifrada")
		elif self.firmada:
			texto += " " + _("firmada")
		return texto

	def texto_espacio(self) -> str:
		if self.libre < 0 or self.total <= 0:
			return ""
		return _("{l} libres de {t}").format(l=formato.tamano_legible(self.libre), t=formato.tamano_legible(self.total))

	def texto_velocidad(self) -> str:
		return _("enlace a {v}").format(v=velocidad_enlace(self.velocidad_bps)) if self.velocidad_bps > 0 else ""

	def resumen(self) -> str:
		"""Una línea: «Z:, \\\\DS220\\home, conectada, SMB 3.1.1 cifrada, usuario ana, 1,2 TB libres de 2 TB, enlace a 1 Gbps»."""
		partes = [self.letra] if self.letra else []
		if self.remoto:
			partes.append(self.remoto)
		if self.estado:
			partes.append(self.estado.lower() if self.estado else "")
		partes.append(self.texto_protocolo())
		if self.usuario:
			partes.append(_("usuario {u}").format(u=self.usuario))
		partes.extend([self.texto_espacio(), self.texto_velocidad()])
		return ", ".join(p for p in partes if p) or self.ruta

	def texto(self) -> str:
		"""Todo, una línea por dato, para el diálogo de la orden ``red_info``."""
		sin_dato = _("no se sabe")
		si_no = {True: _("sí"), False: _("no"), None: sin_dato}
		lineas = [
			_("Ruta: {v}").format(v=self.ruta),
			_("Letra de unidad: {v}").format(v=self.letra or _("ninguna")),
			_("Recurso remoto: {v}").format(v=self.remoto or sin_dato),
			_("Estado: {v}").format(v=self.estado or sin_dato),
			_("Usuario: {v}").format(v=self.usuario or sin_dato),
			_("Proveedor de red: {v}").format(v=self.proveedor or sin_dato),
			_("Espacio: {v}").format(v=self.texto_espacio() or sin_dato),
			_("Volumen: {v}").format(v=self.etiqueta or _("sin etiqueta")),
			_("Sistema de archivos que informa el servidor: {v}").format(v=self.sistema_archivos or sin_dato),
			_("Protocolo: {v}").format(v=_("SMB {d}").format(d=self.dialecto) if self.dialecto else sin_dato),
			_("Cifrado SMB: {v}").format(v=si_no[self.cifrada]),
			_("Firma SMB: {v}").format(v=si_no[self.firmada]),
			_("Archivos abiertos en esta conexión: {v}").format(v=self.archivos_abiertos if self.archivos_abiertos >= 0 else sin_dato),
			_("Velocidad del enlace: {v}").format(v=velocidad_enlace(self.velocidad_bps) if self.velocidad_bps > 0 else sin_dato),
		]
		return "\n".join([*lineas, *self.notas])


#: ``WBEM_E_ACCESS_DENIED``: las clases SMB de WMI piden ser administrador.
WBEM_ACCESO_DENEGADO = -2147217405


def velocidad_enlace(bits_por_segundo: int) -> str:
	"""«1 Gbps», «100 Mbps», «2,5 Gbps»."""
	for limite, unidad in ((1_000_000_000, "Gbps"), (1_000_000, "Mbps"), (1_000, "kbps")):
		if bits_por_segundo >= limite:
			valor = bits_por_segundo / limite
			texto = f"{valor:.1f}".rstrip("0").rstrip(".").replace(".", ",")
			return f"{texto} {unidad}"
	return f"{bits_por_segundo} bps"


def _letra_y_raiz(ruta: str) -> tuple[str, str]:
	"""(«Z:», «Z:\\») o («», «\\\\srv\\rec\\») de una ruta."""
	ruta = (ruta or "").strip()
	if len(ruta) >= 2 and ruta[1] == ":":
		letra = ruta[:2].upper()
		return letra, letra + "\\"
	if ruta.startswith("\\\\"):
		partes = [p for p in ruta[2:].split("\\") if p]
		if len(partes) >= 2:
			return "", f"\\\\{partes[0]}\\{partes[1]}\\"
	return "", ruta


def conexiones_smb() -> tuple[list[dict], list[dict]]:
	"""Filas de ``MSFT_SmbConnection`` y ``MSFT_SmbMultichannelConnection`` (WMI, solo lectura)."""
	import pythoncom
	import win32com.client

	def consultar() -> tuple[list[dict], list[dict]]:
		# Los objetos COM viven solo dentro de esta función: se liberan antes de CoUninitialize.
		servicio = win32com.client.GetObject("winmgmts:root\\Microsoft\\Windows\\SMB")
		campos = ("ServerName", "ShareName", "UserName", "Dialect", "NumOpens", "Encrypted", "Signed")
		conexiones = [{c: getattr(f, c, None) for c in campos} for f in servicio.ExecQuery("SELECT * FROM MSFT_SmbConnection")]
		canales = [{c: getattr(f, c, None) for c in ("ServerName", "ClientLinkSpeed")}
			for f in servicio.ExecQuery("SELECT * FROM MSFT_SmbMultichannelConnection")]
		return conexiones, canales

	pythoncom.CoInitialize()
	try:
		return consultar()
	finally:
		import gc

		gc.collect()
		pythoncom.CoUninitialize()


def _completar_smb(info: InfoRed) -> None:
	servidor = red.servidor_de(info.remoto).casefold()
	recurso = info.remoto.strip("\\").split("\\")[1].casefold() if info.remoto.startswith("\\\\") and info.remoto.count("\\") >= 3 else ""
	if not servidor or not info.remoto.startswith("\\\\"):
		return
	try:
		conexiones, canales = conexiones_smb()
	except Exception as error:  # noqa: BLE001 - WMI puede no estar o no dar permiso
		log.info("No se pudo leer el detalle SMB por WMI", exc_info=True)
		if WBEM_ACCESO_DENEGADO in getattr(error, "args", ()):
			info.notas.append(_("El protocolo, el cifrado y la velocidad del enlace solo se pueden leer con zCommander como administrador."))
		return
	for fila in conexiones:
		if str(fila.get("ServerName") or "").casefold() == servidor and (not recurso or str(fila.get("ShareName") or "").casefold() == recurso):
			info.dialecto = str(fila.get("Dialect") or "")
			info.cifrada = bool(fila.get("Encrypted")) if fila.get("Encrypted") is not None else None
			info.firmada = bool(fila.get("Signed")) if fila.get("Signed") is not None else None
			if fila.get("NumOpens") is not None:
				info.archivos_abiertos = int(fila["NumOpens"])
			if not info.usuario and fila.get("UserName"):
				info.usuario = str(fila["UserName"])
			break
	velocidades = [int(f.get("ClientLinkSpeed") or 0) for f in canales if str(f.get("ServerName") or "").casefold() == servidor]
	if velocidades:
		info.velocidad_bps = max(velocidades)


def informacion(ruta: str) -> InfoRed:
	"""Todo lo que se sabe de la conexión de ``ruta`` («Z:\\carpeta», «\\\\srv\\rec» o «Z:»). Bloquea."""
	letra, raiz = _letra_y_raiz(ruta)
	info = InfoRed(ruta=ruta, letra=letra)
	with red.sin_cuadros_de_error():
		try:
			conexion = red.unidad(letra or raiz.rstrip("\\"))
		except red.ErrorUnidadRed:
			log.debug("No se pudieron leer las conexiones", exc_info=True)
			conexion = None
		if conexion is not None:
			info.remoto, info.proveedor, info.usuario = conexion.remoto, conexion.proveedor, conexion.usuario
			info.estado = {red.CONECTADA: _("Conectada"), red.NO_DISPONIBLE: _("No disponible")}.get(conexion.estado_efectivo, _("Desconectada"))
		elif raiz.startswith("\\\\"):
			info.remoto = raiz.rstrip("\\")
		elif letra:
			try:
				info.remoto = red._win32wnet().WNetGetConnection(letra)
			except Exception:  # noqa: BLE001 - la letra no es de red
				info.notas.append(_("{l} no es una unidad de red.").format(l=letra))
		if not info.usuario and (letra or info.remoto):
			try:
				info.usuario = str(red._win32wnet().WNetGetUser(letra or info.remoto) or "")
			except Exception:  # noqa: BLE001 - sin usuario conocido
				log.debug("WNetGetUser no dio el usuario de %s", letra or info.remoto, exc_info=True)
		if info.estado != _("Desconectada"):
			try:
				uso = shutil.disk_usage(raiz)
				info.libre, info.total = int(uso.free), int(uso.total)
			except OSError:
				log.debug("Sin espacio libre de %s", raiz, exc_info=True)
			try:
				import win32api

				etiqueta, _serie, _largo, _indicadores, sistema = win32api.GetVolumeInformation(raiz)
				info.etiqueta, info.sistema_archivos = str(etiqueta or ""), str(sistema or "")
			except Exception:  # noqa: BLE001 - un servidor caído no da el volumen
				log.debug("Sin datos del volumen de %s", raiz, exc_info=True)
	if info.remoto and red.es_webdav(info.remoto):
		info.notas.append(red.aviso_webdav())
	else:
		_completar_smb(info)
	if red.es_elevado():
		info.notas.append(red.aviso_elevacion())
	return info
