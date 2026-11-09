# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comprimidos leídos con un 7-Zip de consola: el que tiene instalado la persona, o el 7za de zCommander (diseño 2.0, 8.5).

zCommander nunca distribuye ni actualiza el 7-Zip completo (su código de RAR
lleva la restricción de unRAR, incompatible con la GPL; comprimidos-y-red.md
A.3), pero si la persona lo tiene instalado lo usa para lo que libarchive no
puede: RAR y 7z cifrados y los formatos ARJ, CHM, MSI, NSIS, WIM, VHD(X), DMG,
UDF y SquashFS. El 7za que sí trae zCommander lee 7z cifrados (no RAR).

Detección (8.5): ``comprimidos.ruta_7zip`` si la persona la fija; si no,
``HKLM\\SOFTWARE\\7-Zip`` y ``HKCU\\Software\\7-Zip``, valores ``Path64`` y
``Path``. Solo lectura del Registro.

``ProveedorSieteZipExterno`` lista con ``7z l -slt`` y extrae a temporales de
``data/temp`` (con rutas y en una carpeta única). Las contraseñas siguen las
reglas de ``siete_zip_externo`` (por la entrada estándar).
"""

from __future__ import annotations

import builtins
import logging
import threading
from pathlib import Path
from typing import BinaryIO

from app.services import siete_zip_externo as consola
from app.services.vfs import base, resolver
from app.services.vfs.zip import Indice, ProveedorComprimido, ResultadoPrueba, lectura_temporal, nombre_seguro

log = logging.getLogger(__name__)

#: Formatos que solo abre el 7-Zip de la persona (8.1, última fila).
EXTENSIONES = ("arj", "chm", "msi", "wim", "vhd", "vhdx", "dmg", "squashfs", "nsis")
#: Bytes de miembros anteriores que se extraen de paso (como en ``siete_z.py``).
LIMITE_PREVIO = 256 * 1024 * 1024
#: Miembros como máximo en una extracción por lotes (la línea de órdenes de Windows tiene un límite).
LIMITE_LOTE = 200

_candado = threading.Lock()
_detectado: list[Path | None] = []


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _config(clave: str, por_defecto):
	config = resolver.servicios().config
	if config is None:
		return por_defecto
	try:
		return config.obtener(clave)
	except Exception:  # noqa: BLE001 - una clave que falta: valor de fábrica
		log.debug("Sin la clave %s", clave, exc_info=True)
		return por_defecto


def _del_registro() -> list[Path]:
	"""Carpetas de 7-Zip que dice el Registro (64 y 32 bits, equipo y usuario)."""
	try:
		import winreg
	except ImportError:  # pragma: no cover - fuera de Windows
		return []
	carpetas = []
	for raiz, clave in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\7-Zip"), (winreg.HKEY_CURRENT_USER, r"Software\7-Zip")):
		for vista in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
			try:
				with winreg.OpenKey(raiz, clave, 0, winreg.KEY_READ | vista) as abierta:
					for valor in ("Path64", "Path"):
						try:
							texto, _tipo = winreg.QueryValueEx(abierta, valor)
						except OSError:
							continue
						if texto:
							carpetas.append(Path(str(texto)))
			except OSError:
				continue
	return carpetas


def detectar_7zip(forzar: bool = False) -> Path | None:
	"""Ruta de ``7z.exe`` instalado, o ``None``. Se busca una vez (``forzar`` vuelve a buscar)."""
	propia = str(_config("comprimidos.ruta_7zip", "") or "").strip().strip('"')
	if propia:
		ruta = Path(propia)
		ruta = ruta if ruta.suffix.lower() == ".exe" else ruta / "7z.exe"
		if ruta.is_file():
			return ruta.resolve()
		log.warning("comprimidos.ruta_7zip no tiene 7z.exe: %s", propia)
	with _candado:
		if _detectado and not forzar:
			return _detectado[0]
		encontrado = None
		for carpeta in _del_registro():
			candidato = carpeta / "7z.exe"
			if candidato.is_file():
				encontrado = candidato.resolve()
				break
		_detectado[:] = [encontrado]
		if encontrado:
			log.info("7-Zip instalado: %s", encontrado)
		return encontrado


def siete_zip_instalado() -> Path | None:
	"""El 7-Zip de la persona si está y ``comprimidos.usar_7zip_instalado`` está activa."""
	if not _config("comprimidos.usar_7zip_instalado", True):
		return None
	return detectar_7zip()


def motor_lectura(formato: str) -> Path | None:
	"""Qué 7-Zip puede leer un ``formato`` cifrado: para 7z, 7za y si no el instalado; para lo demás, solo el instalado."""
	if formato == "7z":
		return consola.ruta_7za() or siete_zip_instalado()
	return siete_zip_instalado()


class _Miembro:
	__slots__ = ("cifrado", "nombre", "orden", "tamano")

	def __init__(self, nombre: str, orden: int, tamano: int, cifrado: bool) -> None:
		self.nombre = nombre
		self.orden = orden
		self.tamano = tamano
		self.cifrado = cifrado


class ProveedorSieteZipExterno(ProveedorComprimido):
	"""Comprimido leído con un 7-Zip de consola, como carpeta de solo lectura.

	:param ejecutable: ``7z.exe`` instalado o ``7za.exe``.
	:param formato: extensión («rar», «7z», «msi»...), solo para los textos.
	"""

	esquema = "7zip"
	tipo_visible = "Comprimido"

	def __init__(self, contenedor: base.Proveedor, ruta_archivo: str, ejecutable: Path | str | None = None,
			formato: str = "") -> None:
		super().__init__(contenedor, ruta_archivo)
		self.capacidades = base.Capacidades(escribir=False)
		self.ejecutable = Path(ejecutable) if ejecutable else siete_zip_instalado()
		self.formato = (formato or resolver.extension_comprimido(contenedor.nombre(ruta_archivo)) or "").lower()
		self.tipo_visible = _("Archivo {f}").format(f=self.formato.upper()) if self.formato else _("Comprimido")
		self._previos: dict[str, str] = {}

	def descripcion(self) -> str:
		return self.tipo_visible

	def _exigir(self) -> Path:
		if self.ejecutable is None or not Path(self.ejecutable).is_file():
			raise base.NoAdmitido(_("Para abrir este comprimido hace falta 7-Zip instalado en el equipo."), self.ruta_archivo)
		return Path(self.ejecutable)

	def _con_contrasena(self, accion):
		"""Ejecuta ``accion(contrasena)``; si 7-Zip dice que falta o no vale, la pide (hasta cuatro veces)."""
		incorrecta = False
		for _intento in range(4):
			try:
				return accion(self._contrasena)
			except consola.ContrasenaIncorrecta:
				incorrecta = self._contrasena is not None
				self.pedir_contrasena(incorrecta)
		raise base.ErrorAcceso(_("La contraseña de {n} no es correcta.").format(n=self.nombre("")), self.ruta_archivo)

	# Índice ------------------------------------------------------------------------

	def _cargar(self, ruta: str, indice: Indice, cancelacion) -> None:
		ejecutable = self._exigir()
		miembros = self._con_contrasena(lambda clave: consola.listar(ejecutable, ruta, clave, cancelacion))
		for orden, miembro in enumerate(miembros):
			nombre = nombre_seguro(miembro.ruta)
			if nombre is None:
				indice.omitidas.append(miembro.ruta)
				continue
			if not nombre:
				continue
			if miembro.es_carpeta:
				indice.agregar(nombre, True, modificado=miembro.modificado)
				continue
			if miembro.enlace:
				indice.omitidas.append(miembro.ruta)
				continue
			indice.agregar(nombre, False, miembro.tamano, miembro.modificado, 0x1 if miembro.solo_lectura else 0,
				_Miembro(miembro.ruta, orden, miembro.tamano, miembro.cifrado))

	# Lectura ------------------------------------------------------------------------

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		ruta = self._limpia(ruta)
		indice = self.indice()
		entrada = indice.entradas.get(ruta)
		if entrada is None:
			raise base.NoEncontrado(_("No existe «{r}» en el comprimido.").format(r=ruta), ruta)
		if entrada.es_carpeta:
			raise base.ErrorAcceso(_("«{r}» es una carpeta.").format(r=ruta), ruta)
		miembro: _Miembro = indice.datos[ruta]  # type: ignore[assignment]
		with self._candado:
			previo = self._previos.pop(miembro.nombre, None)
		if previo is not None:
			return lectura_temporal(previo, ruta)
		lote = self._lote(indice, miembro)
		ejecutable = self._exigir()
		archivo = self.archivo_local()
		if miembro.cifrado and self._contrasena is None:
			self.pedir_contrasena(False)
		extraidos = self._con_contrasena(lambda clave: consola.extraer(ejecutable, archivo, lote, clave))
		propio = extraidos.pop(miembro.nombre, None)
		with self._candado:
			self._previos.update(extraidos)
		if propio is None:
			raise base.ErrorArchivos(_("7-Zip no extrajo «{n}».").format(n=ruta), ruta)
		return lectura_temporal(propio, ruta)

	def _lote(self, indice: Indice, objetivo: _Miembro) -> list[str]:
		"""El miembro pedido y los anteriores aún no leídos (en un comprimido sólido salen casi gratis)."""
		lote = [objetivo.nombre]
		acumulado = 0
		with self._candado:
			ya = set(self._previos)
		anteriores = sorted((d for d in indice.datos.values() if isinstance(d, _Miembro) and d.orden < objetivo.orden
			and d.nombre not in ya), key=lambda d: d.orden, reverse=True)
		for dato in anteriores:
			if len(lote) >= LIMITE_LOTE or acumulado + dato.tamano > LIMITE_PREVIO:
				break
			acumulado += dato.tamano
			lote.append(dato.nombre)
		return lote

	# Probar ----------------------------------------------------------------------------

	def probar(self, cancelacion=None, al_avanzar=None) -> ResultadoPrueba:
		ejecutable = self._exigir()
		indice = self.indice(cancelacion)
		archivo = self.archivo_local()
		if self._contrasena is None and any(isinstance(d, _Miembro) and d.cifrado for d in indice.datos.values()):
			self.pedir_contrasena(False)
		problemas = self._con_contrasena(lambda clave: consola.probar(ejecutable, archivo, clave, cancelacion))
		resultado = ResultadoPrueba(errores=list(problemas))
		if not problemas:
			for ruta in indice.archivos():
				tamano = max(0, indice.entradas[ruta].tamano)
				resultado.archivos += 1
				resultado.bytes += tamano
				if al_avanzar is not None:
					al_avanzar(ruta, tamano)
		return resultado

	# Ciclo de vida -------------------------------------------------------------------

	def _clon(self) -> ProveedorSieteZipExterno:
		otro = ProveedorSieteZipExterno(self.contenedor[0], self.ruta_archivo, self.ejecutable, self.formato)
		otro.contenedor = self.contenedor
		with self._candado:
			otro._indice, otro._firma = self._indice, self._firma
			otro._copia_local = self._copia_local
		otro._contrasena = self._contrasena
		return otro

	def cerrar(self) -> None:
		from app.services.vfs import temporales

		with self._candado:
			previos, self._previos = list(self._previos.values()), {}
		for previo in previos:
			temporales.borrar(previo)
		super().cerrar()


class ProveedorSieteZipInstalado(ProveedorSieteZipExterno):
	"""Los formatos que solo abre el 7-Zip de la persona (ARJ, MSI, WIM...)."""

	def __init__(self, contenedor: base.Proveedor, ruta_archivo: str) -> None:
		super().__init__(contenedor, ruta_archivo, siete_zip_instalado())


def _fabrica(contenedor: base.Proveedor, ruta_archivo: str) -> ProveedorSieteZipInstalado:
	if siete_zip_instalado() is None:
		raise base.NoAdmitido(_("Para abrir este comprimido hace falta 7-Zip instalado en el equipo."), ruta_archivo)
	return ProveedorSieteZipInstalado(contenedor, ruta_archivo)


def registrar() -> bool:
	"""Registra ARJ, CHM, MSI... si hay 7-Zip instalado y la opción está activa (8.1)."""
	if siete_zip_instalado() is None:
		log.info("Sin 7-Zip instalado (o desactivado): ARJ, CHM, MSI, WIM, VHD, DMG y SquashFS no se registran")
		return False
	resolver.registrar_comprimido(EXTENSIONES, _fabrica)
	return True


registrar()
