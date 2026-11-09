# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Unidades de Windows: letras, tipo, etiqueta, sistema de archivos y espacio.

Cada consulta a una unidad puede colgarse (red caída, lector óptico que gira):
``info_unidad_con_limite`` la hace en un hilo DESECHABLE (no del grupo de
tareas) y devuelve lo que haya a tiempo, para que una unidad muerta no
agote los hilos ni congele nada.
"""

from __future__ import annotations

import builtins
import ctypes
import ctypes.wintypes as wt
import logging
import string
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)

TIPOS = {0: "desconocida", 1: "sin_raiz", 2: "extraible", 3: "fija", 4: "red", 5: "optica", 6: "ram"}
SEM_FAILCRITICALERRORS = 0x0001
SEM_NOOPENFILEERRORBOX = 0x8000


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def nombre_tipo(tipo: str) -> str:
	return {
		"extraible": _("Extraíble"), "fija": _("Disco local"), "red": _("Unidad de red"), "optica": _("Unidad óptica"),
		"ram": _("Disco en memoria"), "desconocida": _("Desconocida"), "sin_raiz": _("Sin raíz"),
	}.get(tipo, tipo)


def evitar_errores_criticos() -> None:
	"""Que Windows no muestre «Inserte un disco» ni cuelgue el hilo con un cartel (llamar al arrancar)."""
	try:
		ctypes.windll.kernel32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)
	except (AttributeError, OSError):
		log.debug("SetErrorMode no disponible", exc_info=True)


@dataclass(frozen=True)
class Unidad:
	letra: str  # «C:»
	raiz: str  # «C:\»
	tipo: str
	etiqueta: str = ""
	sistema_archivos: str = ""
	numero_serie: int = 0
	libre: int = -1
	total: int = -1
	preparada: bool = True
	destino_red: str = ""

	def describir(self) -> str:
		"""«C:, Disco local, Sistema, NTFS, 120 GB libres de 476 GB» o «E:, Extraíble, sin disco»."""
		from app.services import formato

		partes = [self.letra, nombre_tipo(self.tipo)]
		if self.destino_red:
			partes.append(self.destino_red)
		if not self.preparada:
			partes.append(_("sin disco o sin respuesta"))
			return ", ".join(partes)
		if self.etiqueta:
			partes.append(self.etiqueta)
		if self.sistema_archivos:
			partes.append(self.sistema_archivos)
		if self.total > 0:
			partes.append(_("{libre} libres de {total}").format(
				libre=formato.tamano_legible(self.libre), total=formato.tamano_legible(self.total)))
		return ", ".join(partes)


def letras() -> list[str]:
	"""«C:», «D:»... de las unidades presentes (``GetLogicalDrives``, no toca el disco)."""
	mascara = ctypes.windll.kernel32.GetLogicalDrives()
	return [f"{letra}:" for i, letra in enumerate(string.ascii_uppercase) if mascara & (1 << i)]


def tipo_de(raiz: str) -> str:
	return TIPOS.get(ctypes.windll.kernel32.GetDriveTypeW(raiz), "desconocida")


def _destino_red(letra: str) -> str:
	buffer = ctypes.create_unicode_buffer(1024)
	longitud = wt.DWORD(1024)
	try:
		if ctypes.windll.mpr.WNetGetConnectionW(letra, buffer, ctypes.byref(longitud)) == 0:
			return buffer.value
	except (AttributeError, OSError):
		log.debug("WNetGetConnectionW falló", exc_info=True)
	return ""


def info_unidad(letra: str) -> Unidad:
	"""Consulta completa (puede tardar o colgarse: usar con ``info_unidad_con_limite``)."""
	raiz = letra + "\\"
	tipo = tipo_de(raiz)
	destino = _destino_red(letra) if tipo == "red" else ""
	etiqueta = ctypes.create_unicode_buffer(261)
	sistema = ctypes.create_unicode_buffer(261)
	serie = wt.DWORD()
	longitud = wt.DWORD()
	banderas = wt.DWORD()
	ok = ctypes.windll.kernel32.GetVolumeInformationW(
		raiz, etiqueta, 261, ctypes.byref(serie), ctypes.byref(longitud), ctypes.byref(banderas), sistema, 261,
	)
	if not ok:
		return Unidad(letra, raiz, tipo, preparada=False, destino_red=destino)
	libre = ctypes.c_ulonglong()
	total = ctypes.c_ulonglong()
	ctypes.windll.kernel32.GetDiskFreeSpaceExW(raiz, ctypes.byref(libre), ctypes.byref(total), None)
	return Unidad(letra, raiz, tipo, etiqueta.value, sistema.value, serie.value, libre.value, total.value, True, destino)


def info_unidad_con_limite(letra: str, segundos: float = 3.0) -> Unidad:
	"""``info_unidad`` con tiempo límite; si no responde, se da como no preparada."""
	resultado: list[Unidad] = []

	def trabajo() -> None:
		try:
			resultado.append(info_unidad(letra))
		except Exception:  # noqa: BLE001 - una unidad rara no debe romper la lista
			log.debug("Error al consultar %s", letra, exc_info=True)

	hilo = threading.Thread(target=trabajo, name=f"unidad-{letra}", daemon=True)
	hilo.start()
	hilo.join(segundos)
	if resultado:
		return resultado[0]
	raiz = letra + "\\"
	return Unidad(letra, raiz, tipo_de(raiz), preparada=False)


def todas(segundos: float = 3.0) -> list[Unidad]:
	"""Información de todas las unidades, en paralelo y con tiempo límite total."""
	lista = letras()
	resultados: dict[str, Unidad] = {}
	hilos = []
	for letra in lista:
		def trabajo(l=letra) -> None:
			resultados[l] = info_unidad_con_limite(l, segundos)
		hilo = threading.Thread(target=trabajo, daemon=True, name=f"unidades-{letra}")
		hilo.start()
		hilos.append(hilo)
	for hilo in hilos:
		hilo.join(segundos + 0.5)
	return [resultados.get(l) or Unidad(l, l + "\\", "desconocida", preparada=False) for l in lista]


def carpetas_especiales() -> list[tuple[str, str]]:
	"""(nombre, ruta) de Escritorio, Documentos, Descargas, Imágenes, Música, Vídeos y carpeta personal."""
	import os

	casa = os.path.expanduser("~")
	candidatas = [
		(_("Carpeta personal"), casa),
		(_("Escritorio"), os.path.join(casa, "Desktop")),
		(_("Documentos"), os.path.join(casa, "Documents")),
		(_("Descargas"), os.path.join(casa, "Downloads")),
		(_("Imágenes"), os.path.join(casa, "Pictures")),
		(_("Música"), os.path.join(casa, "Music")),
		(_("Vídeos"), os.path.join(casa, "Videos")),
	]
	try:
		from win32com.shell import shell, shellcon

		reales = {
			_("Escritorio"): shellcon.CSIDL_DESKTOPDIRECTORY, _("Documentos"): shellcon.CSIDL_PERSONAL,
			_("Imágenes"): shellcon.CSIDL_MYPICTURES, _("Música"): shellcon.CSIDL_MYMUSIC, _("Vídeos"): shellcon.CSIDL_MYVIDEO,
		}
		candidatas = [
			(nombre, shell.SHGetFolderPath(0, reales[nombre], None, 0) if nombre in reales else ruta)
			for nombre, ruta in candidatas
		]
	except Exception:  # noqa: BLE001 - sin pywin32 se usan las rutas habituales
		log.debug("Rutas especiales sin pywin32", exc_info=True)
	return [(n, r) for n, r in candidatas if os.path.isdir(r)]


def es_usb(letra: str) -> bool:
	"""``True`` si la unidad está en un disco USB (aunque Windows la declare fija).

	Se pregunta el tipo de bus con ``IOCTL_STORAGE_QUERY_PROPERTY``. Si no se
	puede saber, se responde ``False``.
	"""
	IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
	BUS_USB = 7

	class Consulta(ctypes.Structure):
		_fields_ = [("PropertyId", ctypes.c_int), ("QueryType", ctypes.c_int), ("Extra", ctypes.c_ubyte * 1)]

	kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	kernel32.CreateFileW.restype = wt.HANDLE
	kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
	manejador = kernel32.CreateFileW("\\\\.\\" + letra[:2], 0, 3, None, 3, 0, None)
	if not manejador or manejador == wt.HANDLE(-1).value:
		return False
	try:
		consulta = Consulta(0, 0)
		salida = ctypes.create_string_buffer(1024)
		devueltos = wt.DWORD()
		ok = kernel32.DeviceIoControl(
			wt.HANDLE(manejador), IOCTL_STORAGE_QUERY_PROPERTY, ctypes.byref(consulta), ctypes.sizeof(consulta),
			salida, 1024, ctypes.byref(devueltos), None,
		)
		if not ok or devueltos.value < 32:
			return False
		# STORAGE_DEVICE_DESCRIPTOR: BusType es un DWORD en el desplazamiento 28.
		return int.from_bytes(salida.raw[28:32], "little") == BUS_USB
	finally:
		kernel32.CloseHandle(wt.HANDLE(manejador))
