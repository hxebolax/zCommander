# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Operaciones del motor para cifrar y descifrar (diseño 2.0, 11.13). Sin wx.

Por qué operaciones y no tareas sueltas: cifrar una carpeta de varios gigas
tarda; así tiene progreso, pausa, cola, F12 y resumen como una copia.

Reglas de seguridad:

- Todo se escribe primero en ``<destino>.parcial`` y solo se renombra al nombre
  final cuando ha salido bien: una contraseña equivocada, un archivo dañado o
  una cancelación no dejan ningún archivo descifrado (ni a medias).
- Lo cifrado se comprueba descifrándolo entero (sin escribirlo) y comparando su
  SHA-256 con el del original; solo entonces, si se pidió, el original va a la
  papelera. Nunca se borra nada definitivamente (no se promete borrado seguro).
- Nunca se sobrescribe un archivo: si el nombre existe, «nombre (2).ext».
"""

from __future__ import annotations

import logging
import os
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from app.plugins import api

from . import zcc

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_cifrado")

#: Tope de lo que se extrae de una carpeta cifrada (el mismo criterio que los paquetes: nada fuera de su carpeta).
MAX_MIEMBROS = 200_000


def _papelera(ruta: str) -> None:
	import send2trash

	send2trash.send2trash(ruta)


def tamano_carpeta(ruta: str) -> int:
	total = 0
	for carpeta, _subcarpetas, archivos in os.walk(ruta):
		for archivo in archivos:
			try:
				total += os.path.getsize(os.path.join(carpeta, archivo))
			except OSError:
				log.debug("Sin tamaño: %s", archivo, exc_info=True)
	return total


def comprimir_carpeta(origen: str, destino: str, comprobar: Callable[[], None]) -> None:
	"""ZIP (deflate) de una carpeta, con su nombre como raíz, para cifrarla como un solo archivo."""
	raiz = Path(origen)
	with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as paquete:
		paquete.write(raiz, raiz.name)
		for carpeta, subcarpetas, archivos in os.walk(raiz):
			subcarpetas.sort()
			for nombre in sorted(archivos) + [s for s in subcarpetas if not os.listdir(os.path.join(carpeta, s))]:
				comprobar()
				ruta = Path(carpeta) / nombre
				paquete.write(ruta, str(PurePosixPath(raiz.name, *ruta.relative_to(raiz).parts)))


def extraer_carpeta(zip_: str, destino: str, comprobar: Callable[[], None]) -> str:
	"""Extrae el ZIP de una carpeta cifrada dentro de ``destino`` sin salir de ella. Devuelve la carpeta creada."""
	base = Path(destino).resolve()
	creada = ""
	with zipfile.ZipFile(zip_) as paquete:
		miembros = paquete.infolist()
		if len(miembros) > MAX_MIEMBROS:
			raise api.ErrorArchivos(_("La carpeta cifrada tiene demasiados elementos"))
		for miembro in miembros:
			comprobar()
			partes = PurePosixPath(miembro.filename.replace("\\", "/")).parts
			if not partes or any(p in ("..", "") or ":" in p for p in partes) or miembro.filename.startswith("/"):
				raise api.ErrorArchivos(_("La carpeta cifrada contiene una ruta no válida: {r}").format(r=miembro.filename))
			objetivo = base.joinpath(*partes).resolve()
			if base not in objetivo.parents and objetivo != base:
				raise api.ErrorArchivos(_("La carpeta cifrada contiene una ruta no válida: {r}").format(r=miembro.filename))
			creada = creada or str(base / partes[0])
		paquete.extractall(base)
	return creada


class _Base(api.Operacion):
	def __init__(self, proveedor: api.Proveedor, entradas: list[api.Entrada]) -> None:
		super().__init__()
		self.proveedor = proveedor
		self.entradas = [e for e in entradas if not e.es_superior]
		self.creados: list[str] = []

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset(api.clave_carril(self.proveedor, e.ruta) for e in self.entradas)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return sorted({(self.proveedor.esquema, self.proveedor.padre(e.ruta) or "") for e in self.entradas})

	def _que(self) -> str:
		n = len(self.entradas)
		return self.entradas[0].nombre if n == 1 else _n("{n} elemento", "{n} elementos", n).format(n=n)

	def _destino_libre(self, carpeta: str, nombre: str) -> str:
		proveedor = self.proveedor
		return proveedor.unir(carpeta, zcc.nombre_libre(proveedor.existe, lambda n: proveedor.unir(carpeta, n), nombre))

	def _borrar(self, ruta: str) -> None:
		try:
			if self.proveedor.existe(ruta):
				self.proveedor.eliminar(ruta)
		except api.ErrorArchivos:
			log.warning("No se pudo borrar el temporal %s", ruta, exc_info=True)

	def _avance(self, ctx: api.ContextoEjecucion) -> Callable[[int], None]:
		def avanzar(bytes_: int) -> None:
			self.sumar(bytes_hechos=bytes_)

		return avanzar


class OperacionCifrar(_Base):
	"""Cifra cada elemento en un ``.zcc`` (las carpetas, antes a un ZIP) o en un 7z con AES-256."""

	tipo = "cifrar"

	def __init__(self, proveedor: api.Proveedor, entradas: list[api.Entrada], contrasena: str, *, formato: str = "zcc",
			coste: str = "normal", borrar_originales: bool = False, papelera: Callable[[str], None] = _papelera) -> None:
		super().__init__(proveedor, entradas)
		self._contrasena = contrasena
		self.formato = formato if formato in ("zcc", "7z") else "zcc"
		self.n = zcc.COSTES.get(coste, zcc.COSTES["normal"])
		self.borrar_originales = borrar_originales
		self._papelera = papelera
		self.a_papelera: list[str] = []

	def descripcion(self) -> str:
		return _("Cifrar {q}").format(q=self._que())

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.ANALIZANDO)
		total = 0
		for entrada in self.entradas:
			local = self.proveedor.ruta_local(entrada.ruta)
			total += tamano_carpeta(local) if entrada.es_carpeta and local else max(0, entrada.tamano)
		self.progresar(archivos_total=len(self.entradas), bytes_total=total * 2)
		self.cambiar_estado(api.Estado.EJECUTANDO)
		try:
			for entrada in self.entradas:
				ctx.comprobar()
				self.progresar(actual=entrada.nombre)
				try:
					if self.formato == "7z":
						self._cifrar_7z(ctx, entrada)
					else:
						self._cifrar_zcc(ctx, entrada)
					self.sumar(archivos_hechos=1)
				except api.Cancelado:
					raise
				except api.ErrorArchivos as error:
					log.info("No se cifró %s: %s", entrada.ruta, error.mensaje)
					self.anotar_error(entrada.ruta, error.mensaje)
				except OSError as error:
					log.info("No se cifró %s", entrada.ruta, exc_info=True)
					self.anotar_error(entrada.ruta, error.strerror or str(error))
		finally:
			self._contrasena = ""

	def _cifrar_zcc(self, ctx: api.ContextoEjecucion, entrada: api.Entrada) -> None:
		proveedor = self.proveedor
		carpeta = proveedor.padre(entrada.ruta) or ""
		destino = self._destino_libre(carpeta, entrada.nombre + zcc.EXTENSION)
		parcial = destino + ".parcial"
		temporal = ""
		try:
			if entrada.es_carpeta:
				local = proveedor.ruta_local(entrada.ruta)
				if not local:
					raise api.NoAdmitido(_("Las carpetas solo se pueden cifrar en el disco"))
				descriptor, temporal = tempfile.mkstemp(prefix=".zcc-", suffix=".zip", dir=os.path.dirname(local))
				os.close(descriptor)
				comprimir_carpeta(local, temporal, ctx.comprobar)
				lector = open(temporal, "rb")  # se cierra en el with de abajo
				nombre, tamano = entrada.nombre + ".zip", os.path.getsize(temporal)
			else:
				lector = proveedor.abrir_lectura(entrada.ruta)
				nombre, tamano = entrada.nombre, entrada.tamano
			with lector as origen, proveedor.abrir_escritura(parcial, -1) as salida:
				suma = zcc.cifrar(origen, salida, self._contrasena, nombre, tamano, n=self.n, carpeta=entrada.es_carpeta,
					al_progresar=self._avance(ctx), comprobar=ctx.comprobar)
			self.cambiar_estado(api.Estado.VERIFICANDO)
			with proveedor.abrir_lectura(parcial) as comprobacion:
				if zcc.descifrar(comprobacion, None, self._contrasena, al_progresar=self._avance(ctx), comprobar=ctx.comprobar) != suma:
					raise api.ErrorArchivos(_("La comprobación del cifrado de {n} no coincide").format(n=entrada.nombre))
			self.cambiar_estado(api.Estado.EJECUTANDO)
			proveedor.renombrar(parcial, destino)
			self.creados.append(destino)
		except BaseException:
			self._borrar(parcial)
			if self.estado == api.Estado.VERIFICANDO:
				self.cambiar_estado(api.Estado.EJECUTANDO)
			raise
		finally:
			if temporal:
				try:
					os.remove(temporal)
				except OSError:
					log.warning("No se pudo borrar el temporal %s", temporal, exc_info=True)
		self._a_la_papelera(entrada)

	def _cifrar_7z(self, ctx: api.ContextoEjecucion, entrada: api.Entrada) -> None:
		import py7zr

		local = self.proveedor.ruta_local(entrada.ruta)
		if not local:
			raise api.NoAdmitido(_("El formato 7z solo se puede crear en el disco"))
		destino = self._destino_libre(os.path.dirname(local), entrada.nombre + ".7z")
		parcial = destino + ".parcial"
		try:
			with py7zr.SevenZipFile(parcial, "w", password=self._contrasena, header_encryption=True) as archivo:
				if entrada.es_carpeta:
					archivo.writeall(local, entrada.nombre)
				else:
					archivo.write(local, entrada.nombre)
			ctx.comprobar()
			self.cambiar_estado(api.Estado.VERIFICANDO)
			with py7zr.SevenZipFile(parcial, "r", password=self._contrasena) as archivo:
				if archivo.testzip() is not None:
					raise api.ErrorArchivos(_("La comprobación del cifrado de {n} no coincide").format(n=entrada.nombre))
			self.cambiar_estado(api.Estado.EJECUTANDO)
			os.replace(parcial, destino)
			self.creados.append(destino)
			tamano = tamano_carpeta(local) if entrada.es_carpeta else max(0, entrada.tamano)
			self.sumar(bytes_hechos=tamano * 2)
		except BaseException:
			if os.path.exists(parcial):
				os.remove(parcial)
			if self.estado == api.Estado.VERIFICANDO:
				self.cambiar_estado(api.Estado.EJECUTANDO)
			raise
		self._a_la_papelera(entrada)

	def _a_la_papelera(self, entrada: api.Entrada) -> None:
		if not self.borrar_originales:
			return
		local = self.proveedor.ruta_local(entrada.ruta)
		if not local:
			self.anotar_error(entrada.ruta, _("El original no está en el disco: no se envió a la papelera"))
			return
		try:
			self._papelera(local)
			self.a_papelera.append(local)
		except Exception as error:  # noqa: BLE001 - la papelera puede fallar por muchas causas; se anota
			log.info("No se envió a la papelera %s", local, exc_info=True)
			self.anotar_error(entrada.ruta, _("Cifrado, pero el original no se pudo enviar a la papelera: {e}").format(e=error))


#: Contraseña que se pide de nuevo: (titulo, texto) -> contraseña o None (cancelar). Se llama desde el hilo de la operación.
PedirContrasena = Callable[[str, str], "str | None"]


class OperacionDescifrar(_Base):
	"""Descifra ``.zcc`` junto a cada uno. Si la contraseña no vale, la vuelve a pedir (o lo salta)."""

	tipo = "descifrar"

	def __init__(self, proveedor: api.Proveedor, entradas: list[api.Entrada], contrasena: str,
			pedir: PedirContrasena | None = None) -> None:
		super().__init__(proveedor, entradas)
		self._contrasena = contrasena
		self._pedir = pedir
		self.contrasena_valida = ""

	def descripcion(self) -> str:
		return _("Descifrar {q}").format(q=self._que())

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.entradas), bytes_total=sum(max(0, e.tamano) for e in self.entradas))
		try:
			for entrada in self.entradas:
				ctx.comprobar()
				self.progresar(actual=entrada.nombre)
				try:
					self._descifrar_uno(ctx, entrada)
					self.sumar(archivos_hechos=1)
				except api.Cancelado:
					raise
				except api.ErrorArchivos as error:
					log.info("No se descifró %s: %s", entrada.ruta, error.mensaje)
					self.anotar_error(entrada.ruta, error.mensaje)
				except OSError as error:
					log.info("No se descifró %s", entrada.ruta, exc_info=True)
					self.anotar_error(entrada.ruta, error.strerror or str(error))
		finally:
			self._contrasena = ""

	def _descifrar_uno(self, ctx: api.ContextoEjecucion, entrada: api.Entrada) -> None:
		proveedor = self.proveedor
		carpeta = proveedor.padre(entrada.ruta) or ""
		with proveedor.abrir_lectura(entrada.ruta) as origen:
			cabecera = zcc.leer_cabecera(origen)
		while True:
			ctx.comprobar()
			destino = self._destino_libre(carpeta, cabecera.nombre)
			parcial = destino + ".parcial"
			try:
				with proveedor.abrir_lectura(entrada.ruta) as origen, proveedor.abrir_escritura(parcial, -1) as salida:
					zcc.descifrar(origen, salida, self._contrasena, al_progresar=self._avance(ctx), comprobar=ctx.comprobar)
			except zcc.ErrorZcc as error:
				self._borrar(parcial)
				nueva = self._pedir_otra(ctx, entrada) if self._pedir is not None else None
				if nueva is None:
					raise api.ErrorArchivos(error.mensaje, entrada.ruta) from error
				self._contrasena = nueva
				continue
			except BaseException:
				self._borrar(parcial)
				raise
			break
		self.contrasena_valida = self._contrasena
		proveedor.renombrar(parcial, destino)
		if cabecera.carpeta:
			local = proveedor.ruta_local(destino)
			if local:
				try:
					self.creados.append(extraer_carpeta(local, os.path.dirname(local), ctx.comprobar) or destino)
				finally:
					os.remove(local)
				return
		self.creados.append(destino)

	def _pedir_otra(self, ctx: api.ContextoEjecucion, entrada: api.Entrada) -> str | None:
		with ctx.esperando():
			return self._pedir(_("Descifrar"), _("El archivo {n} está dañado o la contraseña no es correcta. Escriba la contraseña "
				"otra vez, o cancele para saltarlo:").format(n=entrada.nombre))

