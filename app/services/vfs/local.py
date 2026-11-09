# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor del disco local y de las rutas de red UNC.

Usa ``os.scandir``: en Windows reutiliza los datos de ``FindFirstFile``, así
que tamaño, fechas y atributos llegan sin una llamada ``stat`` por archivo
(clave para carpetas de 100 000 archivos).
"""

from __future__ import annotations

import builtins
import logging
import os
import shutil
import stat as stat_mod
from typing import BinaryIO

from app.services import errores, formato
from app.services.vfs import base, rutas

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _creado(st: os.stat_result) -> float:
	return float(getattr(st, "st_birthtime", 0.0) or getattr(st, "st_ctime", 0.0))


# Etiquetas de punto de análisis que son enlaces de verdad (se recorren como enlace, no se siguen).
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
IO_REPARSE_TAG_SYMLINK = 0xA000000C
_ETIQUETAS_ENLACE = {IO_REPARSE_TAG_MOUNT_POINT, IO_REPARSE_TAG_SYMLINK}


def es_enlace_real(st: os.stat_result) -> bool:
	"""Enlace simbólico o unión. Los puntos de análisis de OneDrive y similares NO lo son."""
	if stat_mod.S_ISLNK(st.st_mode):
		return True
	atributos = int(getattr(st, "st_file_attributes", 0))
	return bool(atributos & formato.PUNTO_ANALISIS) and int(getattr(st, "st_reparse_tag", 0)) in _ETIQUETAS_ENLACE


def entrada_desde_stat(nombre: str, ruta: str, st: os.stat_result, es_enlace: bool = False) -> base.Entrada:
	"""Construye una ``Entrada`` a partir de un ``stat`` de Windows (sin seguir enlaces)."""
	atributos = int(getattr(st, "st_file_attributes", 0))
	es_carpeta = stat_mod.S_ISDIR(st.st_mode) or bool(atributos & formato.CARPETA)
	es_punto = es_enlace or es_enlace_real(st)
	en_nube = bool(atributos & (formato.DESCARGA_AL_ACCEDER | formato.SIN_CONEXION))
	destino = ""
	if es_punto:
		try:
			destino = os.readlink(ruta)
		except (OSError, ValueError):
			destino = ""
	return base.Entrada(
		nombre=nombre,
		ruta=ruta,
		es_carpeta=es_carpeta,
		tamano=-1 if es_carpeta else int(st.st_size),
		modificado=float(st.st_mtime),
		creado=_creado(st),
		atributos=atributos,
		es_enlace=es_punto,
		destino_enlace=rutas.quitar_prefijo(destino),
		en_nube=en_nube,
	)


#: ``ERROR_CONNECTION_UNAVAIL``: la letra está recordada pero no conectada.
ERROR_CONEXION_NO_DISPONIBLE = 1201
#: «No se encuentra el archivo o la ruta»: lo da también una letra recordada sin conectar.
_ERRORES_SIN_RUTA = (2, 3)


def _reconectar_letra(ruta: str, causa: BaseException | None, cancelacion=None) -> bool:
	"""2.0 (9.4): al entrar en una letra de red recordada y desconectada (1201, o 2 y 3 sin la raíz),
	la vuelve a conectar con ``ProveedorRed.preparar`` (respeta ``red.reconectar_al_entrar`` y pide
	credenciales con el ``Decisor``). Verdadero si reconectó y hay que repetir la lectura. Bloquea:
	se llama en el hilo de listado.

	:raises ErrorUnidadRed: si no se pudo (o no se debe) reconectar; su mensaje explica qué pasa.
	:raises Cancelado: si la persona cancela las credenciales.
	"""
	codigo = getattr(causa, "winerror", None)
	if len(ruta) < 2 or ruta[1] != ":" or codigo not in (ERROR_CONEXION_NO_DISPONIBLE, *_ERRORES_SIN_RUTA):
		return False
	if codigo in _ERRORES_SIN_RUTA and os.path.exists(ruta[:2] + "\\"):
		return False  # La unidad está: lo que falta es la carpeta.
	from app.services.vfs import red as vfs_red

	return bool(vfs_red.proveedor_red().preparar(ruta, cancelacion))


class ProveedorLocal(base.Proveedor):
	"""Disco local, unidades de red asignadas y rutas UNC."""

	esquema = "local"

	def __init__(self) -> None:
		super().__init__()
		self.capacidades = base.Capacidades(
			escribir=True, papelera=True, atributos=True, enlaces=True, vigilar=True, permisos=False,
		)

	def descripcion(self) -> str:
		return _("Disco local")

	# Navegación -------------------------------------------------------------

	def listar(self, ruta: str, cancelacion=None) -> list[base.Entrada]:
		ruta = rutas.normalizar(ruta)
		partes = [p for p in ruta.split("\\") if p]
		if ruta.startswith("\\\\") and len(partes) == 1:
			return self._listar_recursos(partes[0])
		try:
			return self._leer_carpeta(ruta, cancelacion)
		except base.Cancelado:
			raise
		except base.ErrorArchivos as error:
			if not _reconectar_letra(ruta, error.__cause__, cancelacion):
				raise
		# La letra se volvió a conectar: una sola repetición (si vuelve a fallar, ese es el error).
		return self._leer_carpeta(ruta, cancelacion)

	def _leer_carpeta(self, ruta: str, cancelacion=None) -> list[base.Entrada]:
		resultado: list[base.Entrada] = []
		try:
			with os.scandir(rutas.con_prefijo_largo(ruta)) as iterador:
				for i, elemento in enumerate(iterador):
					if i % 256 == 0:
						base.comprobar(cancelacion)
					try:
						es_enlace = elemento.is_symlink()
						st = elemento.stat(follow_symlinks=False)
					except OSError:
						log.debug("Sin datos de %s", elemento.path, exc_info=True)
						continue
					completa = rutas.unir(ruta, elemento.name)
					resultado.append(entrada_desde_stat(elemento.name, completa, st, es_enlace))
		except base.Cancelado:
			raise
		except OSError as error:
			raise errores.convertir(error, ruta) from error
		return resultado

	def _listar_recursos(self, servidor: str) -> list[base.Entrada]:
		"""Recursos compartidos de ``\\\\servidor`` (NetShareEnum de pywin32)."""
		try:
			import win32net

			recursos, _total, _reanudar = win32net.NetShareEnum(servidor, 1)
		except Exception as error:  # noqa: BLE001 - pywin32 lanza su propio tipo
			raise base.ErrorRed(_("No se pudieron leer los recursos de {s}.").format(s=servidor), servidor) from error
		entradas = []
		for recurso in recursos:
			# Tipo 0: disco. Se omiten impresoras, IPC$ y recursos administrativos ocultos.
			if recurso.get("type", 0) & 0xFF != 0:
				continue
			nombre = recurso["netname"]
			entradas.append(base.Entrada(nombre=nombre, ruta=f"\\\\{servidor}\\{nombre}", es_carpeta=True))
		return entradas

	def info(self, ruta: str) -> base.Entrada:
		ruta = rutas.normalizar(ruta)
		try:
			st = os.stat(rutas.con_prefijo_largo(ruta), follow_symlinks=False)
		except OSError as error:
			raise errores.convertir(error, ruta) from error
		nombre = os.path.basename(ruta) or ruta
		return entrada_desde_stat(nombre, ruta, st)

	def existe(self, ruta: str) -> bool:
		return os.path.lexists(rutas.con_prefijo_largo(rutas.normalizar(ruta)))

	def padre(self, ruta: str) -> str | None:
		return rutas.padre(ruta)

	def unir(self, carpeta: str, nombre: str) -> str:
		return rutas.unir(carpeta, nombre)

	def raiz(self, ruta: str) -> str:
		return rutas.raiz(rutas.normalizar(ruta))

	def nombre(self, ruta: str) -> str:
		ruta = rutas.normalizar(ruta)
		return os.path.basename(ruta) or ruta

	def mostrar(self, ruta: str) -> str:
		return rutas.normalizar(ruta)

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		return rutas.mismo_volumen(ruta_a, ruta_b)

	# Contenido --------------------------------------------------------------

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		try:
			return open(rutas.con_prefijo_largo(rutas.normalizar(ruta)), "rb")  # noqa: SIM115 - lo cierra quien lo pide
		except OSError as error:
			raise errores.convertir(error, ruta) from error

	def abrir_escritura(self, ruta: str, tamano: int = -1) -> BinaryIO:
		try:
			return open(rutas.con_prefijo_largo(rutas.normalizar(ruta)), "wb")  # noqa: SIM115
		except OSError as error:
			raise errores.convertir(error, ruta) from error

	def crear_carpeta(self, ruta: str) -> None:
		try:
			os.makedirs(rutas.con_prefijo_largo(rutas.normalizar(ruta)), exist_ok=False)
		except FileExistsError as error:
			raise base.YaExiste(_("Ya existe una carpeta o archivo con ese nombre."), ruta) from error
		except OSError as error:
			raise errores.convertir(error, ruta) from error

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		"""Borrado DEFINITIVO. Nunca entra en uniones ni enlaces: los borra como enlace."""
		ruta = rutas.normalizar(ruta)
		larga = rutas.con_prefijo_largo(ruta)
		try:
			st = os.stat(larga, follow_symlinks=False)
			atributos = int(getattr(st, "st_file_attributes", 0))
			es_enlace = es_enlace_real(st)
			es_carpeta = stat_mod.S_ISDIR(st.st_mode) or bool(atributos & formato.CARPETA)
			if es_carpeta and not es_enlace and recursivo:
				self._borrar_arbol(larga, cancelacion)
			elif es_carpeta:
				os.rmdir(larga)
			else:
				if atributos & formato.SOLO_LECTURA:
					os.chmod(larga, stat_mod.S_IWRITE)
				os.remove(larga)
		except base.Cancelado:
			raise
		except OSError as error:
			raise errores.convertir(error, ruta) from error

	def _borrar_arbol(self, carpeta: str, cancelacion) -> None:
		for elemento in os.scandir(carpeta):
			base.comprobar(cancelacion)
			st = elemento.stat(follow_symlinks=False)
			atributos = int(getattr(st, "st_file_attributes", 0))
			es_enlace = elemento.is_symlink() or es_enlace_real(st)
			if elemento.is_dir(follow_symlinks=False) and not es_enlace:
				self._borrar_arbol(elemento.path, cancelacion)
			elif elemento.is_dir(follow_symlinks=False):
				os.rmdir(elemento.path)
			else:
				if atributos & formato.SOLO_LECTURA:
					os.chmod(elemento.path, stat_mod.S_IWRITE)
				os.remove(elemento.path)
		os.rmdir(carpeta)

	def renombrar(self, origen: str, destino: str) -> None:
		o = rutas.con_prefijo_largo(rutas.normalizar(origen))
		d = rutas.con_prefijo_largo(rutas.normalizar(destino))
		try:
			if o.casefold() == d.casefold() and o != d:
				# Solo cambian mayúsculas: Windows lo admite con os.rename directo.
				os.rename(o, d)
				return
			if os.path.lexists(d):
				raise base.YaExiste(_("Ya existe «{n}».").format(n=os.path.basename(destino)), destino)
			os.rename(o, d)
		except base.ErrorArchivos:
			raise
		except OSError as error:
			raise errores.convertir(error, origen) from error

	def fijar_tiempos(self, ruta: str, modificado: float, creado: float = 0.0) -> None:
		larga = rutas.con_prefijo_largo(rutas.normalizar(ruta))
		try:
			if modificado:
				st = os.stat(larga)
				# En Windows os.utime no admite follow_symlinks=False.
				os.utime(larga, (st.st_atime, modificado))
			if creado:
				from app.services.windows import atributos as atr

				atr.fijar_fecha_creacion(larga, creado)
		except OSError as error:
			raise errores.convertir(error, ruta) from error

	def fijar_atributos(self, ruta: str, atributos: int) -> None:
		from app.services.windows import atributos as atr

		atr.fijar_atributos(rutas.con_prefijo_largo(rutas.normalizar(ruta)), atributos)

	def espacio_libre(self, ruta: str) -> tuple[int, int] | None:
		try:
			uso = shutil.disk_usage(rutas.raiz(rutas.normalizar(ruta)))
		except OSError:
			log.debug("Sin espacio libre de %s", ruta, exc_info=True)
			return None
		return int(uso.free), int(uso.total)

	def ruta_local(self, ruta: str) -> str | None:
		return rutas.normalizar(ruta)
