# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""``ProveedorRclone``: cada cuenta de nube es una unidad más del panel (diseño 2.0, 12.4; nubes.md 5.4).

Dirección ``nube://<cuenta>/ruta``; ``fs = "<cuenta>:"``. Rutas internas con «/»
y raíz «/». Correspondencia con ``Proveedor``:

- listar: ``operations/list``; info: ``operations/stat``; leer: GET por
  ``--rc-serve`` (con ``Range``); escribir: ``operations/uploadfile`` en flujo.
- crear carpeta: ``operations/mkdir``; eliminar: ``deletefile``/``purge``/``rmdir``;
  renombrar: ``movefile`` (archivo) o ``sync/move`` (carpeta, ``DirMove`` en el servidor).
- espacio: ``operations/about``; sumas: ``operations/hashsumfile``.
- ganchos 2.0 (14.5): ``transferir`` con ``operations/copyfile`` (copia en el
  servidor dentro de la misma cuenta; entre cuentas del mismo servicio con
  ``ServerSideAcrossConfigs`` si se permite) y ``transferir_lote`` con
  ``sync/copy`` o ``sync/move`` y la lista ``--files-from``: un solo trabajo para
  miles de archivos pequeños, con ``RCLONE_TRANSFERS`` en paralelo.

La caché de listados dura ``cache_listados_s`` (de la cuenta o del complemento);
cualquier escritura la invalida y ``invalidar()`` la vacía.
"""

from __future__ import annotations

import datetime
import io
import logging
import ntpath
import posixpath
import queue
import re
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, BinaryIO

from app.plugins import api

from . import errores
from .cliente_rc import ErrorTrabajo

if TYPE_CHECKING:
	from .cuentas import Cuenta
	from .servicio import Nubes

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

_FRACCION = re.compile(r"(\.\d{6})\d+")


def fecha_rclone(texto: str) -> float:
	"""``ModTime`` de rclone («2026-11-08T23:55:15.033713600+01:00») como marca de tiempo; 0 si no se entiende."""
	if not texto:
		return 0.0
	try:
		limpio = _FRACCION.sub(r"\1", texto.replace("Z", "+00:00"))
		return datetime.datetime.fromisoformat(limpio).timestamp()
	except ValueError:
		return 0.0


def ruta_remota(ruta: str) -> str:
	"""Ruta de rclone dentro del remoto: sin «/» inicial ni final («/a/b/» → «a/b»)."""
	return (ruta or "").replace("\\", "/").strip("/")


def ruta_local_rclone(ruta: str) -> str:
	"""Ruta local para rclone, con barras normales («C:\\a» → «C:/a»)."""
	return ruta.replace("\\", "/")


class ProveedorRclone(api.Proveedor):
	"""Una cuenta de nube manejada por rclone."""

	esquema = "nube"

	def __init__(self, nubes: Nubes, cuenta: Cuenta) -> None:
		super().__init__()
		self._nubes = nubes
		self.cuenta = cuenta
		#: Identidad de la cuenta: un carril por cuenta y la que compara el motor antes de mover (14.5).
		self.servidor = f"nube:{cuenta.id}"
		self._cache: dict[str, tuple[float, list[api.Entrada]]] = {}
		self._candado = threading.Lock()
		self._funciones: dict[str, Any] | None = None
		self._espacio: tuple[float, tuple[int, int] | None] | None = None
		self.capacidades.escribir = not cuenta.solo_lectura
		self.capacidades.papelera = bool(cuenta.papelera)
		self.capacidades.escritura_atomica = True
		self.capacidades.renombrar_barato = True
		self.capacidades.copia_servidor = True

	# Identidad --------------------------------------------------------------

	@property
	def remoto(self) -> str:
		return self.cuenta.remoto

	def descripcion(self) -> str:
		servicio = self._nubes.catalogo.servicio(self.cuenta.servicio)
		return servicio.nombre if servicio is not None else _("Cuenta de nube")

	def mostrar(self, ruta: str) -> str:
		interior = ruta_remota(ruta).replace("/", "\\")
		return f"{self.cuenta.nombre}:\\{interior}"

	def padre(self, ruta: str) -> str | None:
		limpia = "/" + ruta_remota(ruta)
		if limpia == "/":
			return None
		return posixpath.dirname(limpia) or "/"

	def unir(self, carpeta: str, nombre: str) -> str:
		return "/" + posixpath.join(ruta_remota(carpeta), nombre).strip("/")

	def raiz(self, ruta: str) -> str:
		return "/"

	def nombre(self, ruta: str) -> str:
		return posixpath.basename(ruta_remota(ruta)) or self.cuenta.nombre

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		# Solo se pregunta si origen y destino son de la misma cuenta (clave_carril, 14.5).
		return True

	# Llamadas -----------------------------------------------------------------

	def _rc(self, ruta: str, **parametros: Any) -> dict:
		return self._nubes.llamar(ruta, nombre=parametros.pop("_nombre", ""), **parametros)

	def _funciones_servicio(self) -> dict[str, Any]:
		"""``operations/fsinfo`` (una vez): rellena las capacidades reales del servicio."""
		if self._funciones is None:
			try:
				info = self._rc("operations/fsinfo", fs=self.remoto)
			except api.ErrorArchivos:
				log.debug("Sin fsinfo de %s", self.cuenta.id, exc_info=True)
				return {}
			funciones = dict(info.get("Features") or {})
			funciones["_hashes"] = list(info.get("Hashes") or [])
			self.capacidades.renombrar_barato = bool(funciones.get("Move") or funciones.get("DirMove"))
			self.capacidades.copia_servidor = bool(funciones.get("Copy"))
			self.capacidades.nombres_duplicados = bool(funciones.get("DuplicateFiles"))
			self.capacidades.escribir = not self.cuenta.solo_lectura
			self._funciones = funciones
		return self._funciones

	def _exigir_escritura(self, ruta: str) -> None:
		if self.cuenta.solo_lectura:
			raise api.SoloLectura(_("La cuenta {n} es de solo lectura").format(n=self.cuenta.nombre), ruta)

	def _ttl(self) -> float:
		if self.cuenta.cache_listados_s >= 0:
			return float(self.cuenta.cache_listados_s)
		return float(self._nubes.opcion("cache_listados_s", 30))

	def invalidar(self, ruta: str | None = None) -> None:
		"""Olvida los listados guardados (todos, o el de ``ruta`` y su carpeta)."""
		with self._candado:
			if ruta is None:
				self._cache.clear()
				self._espacio = None
				return
			for clave in {"/" + ruta_remota(ruta), self.padre(ruta) or "/"}:
				self._cache.pop(clave, None)
			self._espacio = None

	# Navegación ---------------------------------------------------------------

	def _entrada(self, carpeta: str, dato: dict[str, Any]) -> api.Entrada:
		nombre = str(dato.get("Name") or posixpath.basename(str(dato.get("Path", ""))))
		es_carpeta = bool(dato.get("IsDir"))
		tamano = int(dato.get("Size", -1)) if not es_carpeta else -1
		return api.Entrada(nombre=nombre, ruta=self.unir(carpeta, nombre), es_carpeta=es_carpeta, tamano=tamano,
			modificado=fecha_rclone(str(dato.get("ModTime", ""))))

	def listar(self, ruta: str, cancelacion=None) -> list[api.Entrada]:
		api.comprobar(cancelacion)
		clave = "/" + ruta_remota(ruta)
		ttl = self._ttl()
		with self._candado:
			guardado = self._cache.get(clave)
		if guardado is not None and ttl > 0 and time.monotonic() - guardado[0] < ttl:
			return list(guardado[1])
		self._funciones_servicio()
		datos = self._rc("operations/list", fs=self.remoto, remote=ruta_remota(ruta), opt={"noMimeType": True},
			_nombre=self.mostrar(ruta))
		api.comprobar(cancelacion)
		entradas: list[api.Entrada] = []
		vistos: dict[str, int] = {}
		for dato in datos.get("list", []) or []:
			entrada = self._entrada(clave, dato)
			clave_nombre = entrada.nombre.casefold()
			if clave_nombre in vistos:
				vistos[clave_nombre] += 1
				continue
			vistos[clave_nombre] = 1
			entradas.append(entrada)
		repetidos = {n: v for n, v in vistos.items() if v > 1}
		if repetidos:
			nombre, veces = next(iter(repetidos.items()))
			original = next((e.nombre for e in entradas if e.nombre.casefold() == nombre), nombre)
			self._nubes.avisar_duplicados(self.cuenta, original, veces)
		with self._candado:
			self._cache[clave] = (time.monotonic(), list(entradas))
		return entradas

	def info(self, ruta: str) -> api.Entrada:
		remota = ruta_remota(ruta)
		if not remota:
			return api.Entrada(nombre=self.cuenta.nombre, ruta="/", es_carpeta=True)
		datos = self._rc("operations/stat", fs=self.remoto, remote=remota, opt={"noMimeType": True},
			_nombre=posixpath.basename(remota))
		item = datos.get("item")
		if not item:
			raise api.NoEncontrado(_("No existe en la nube: {n}").format(n=posixpath.basename(remota)), ruta)
		return self._entrada(self.padre(ruta) or "/", item)

	# Contenido ----------------------------------------------------------------

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		return io.BufferedReader(self._nubes.cliente().abrir_objeto(self.remoto, ruta_remota(ruta)), 1024 * 1024)

	def abrir_escritura(self, ruta: str, tamano: int = -1) -> BinaryIO:
		self._exigir_escritura(ruta)
		remota = ruta_remota(ruta)
		carpeta, nombre = posixpath.split(remota)
		self.invalidar(ruta)
		return FlujoSubida(self._nubes.cliente(), self.remoto, carpeta, nombre, lambda: self.invalidar(ruta))

	def crear_carpeta(self, ruta: str) -> None:
		self._exigir_escritura(ruta)
		self._rc("operations/mkdir", fs=self.remoto, remote=ruta_remota(ruta), _nombre=self.nombre(ruta))
		self.invalidar(ruta)

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		self._exigir_escritura(ruta)
		entrada = self.info(ruta)
		remota = ruta_remota(ruta)
		try:
			if not entrada.es_carpeta:
				self._rc("operations/deletefile", fs=self.remoto, remote=remota, _nombre=entrada.nombre)
			elif recursivo:
				self._nubes.ejecutar("operations/purge", cancelacion=cancelacion, fs=self.remoto, remote=remota)
			else:
				self._rc("operations/rmdir", fs=self.remoto, remote=remota, _nombre=entrada.nombre)
		finally:
			self.invalidar(ruta)

	def renombrar(self, origen: str, destino: str) -> None:
		self._exigir_escritura(origen)
		entrada = self.info(origen)
		try:
			if entrada.es_carpeta:
				self._nubes.ejecutar("sync/move", srcFs=self.remoto + ruta_remota(origen), dstFs=self.remoto + ruta_remota(destino),
					deleteEmptySrcDirs=True, createEmptySrcDirs=True)
			else:
				self._rc("operations/movefile", srcFs=self.remoto, srcRemote=ruta_remota(origen), dstFs=self.remoto,
					dstRemote=ruta_remota(destino), _nombre=entrada.nombre)
		finally:
			self.invalidar(origen)
			self.invalidar(destino)

	def espacio_libre(self, ruta: str) -> tuple[int, int] | None:
		ahora = time.monotonic()
		if self._espacio is not None and ahora - self._espacio[0] < 30:
			return self._espacio[1]
		resultado: tuple[int, int] | None = None
		try:
			datos = self._rc("operations/about", fs=self.remoto)
			if datos.get("free") is not None and datos.get("total") is not None:
				resultado = (int(datos["free"]), int(datos["total"]))
		except api.NoAdmitido:
			resultado = None
		except api.ErrorArchivos:
			log.debug("Sin espacio libre de %s", self.cuenta.id, exc_info=True)
		self._espacio = (ahora, resultado)
		return resultado

	def suma(self, ruta: str, algoritmo: str) -> str | None:
		hashes = [h.lower() for h in self._funciones_servicio().get("_hashes", [])]
		if algoritmo.lower() not in hashes:
			return None
		try:
			datos = self._rc("operations/hashsumfile", fs=self.remoto, remote=ruta_remota(ruta), hashType=algoritmo.lower())
		except api.ErrorArchivos:
			log.debug("Sin suma %s de %s", algoritmo, ruta, exc_info=True)
			return None
		valor = str(datos.get("hash", "")).strip().lower()
		return valor or None

	def fijar_tiempos(self, ruta: str, modificado: float, creado: float = 0.0) -> None:
		"""rclone conserva la fecha al copiar; en una subida en flujo la fecha es la de la subida."""

	# Ganchos 2.0 ----------------------------------------------------------------

	def _origen_rclone(self, origen: api.Proveedor, ruta: str) -> tuple[str, str] | None:
		"""(fs de la carpeta, nombre) del origen si rclone puede leerlo directamente; ``None`` si no."""
		if isinstance(origen, ProveedorRclone):
			remota = ruta_remota(ruta)
			carpeta, nombre = posixpath.split(remota)
			return origen.remoto + carpeta, nombre
		local = origen.ruta_local(ruta) if origen.esquema in ("local", "resultados") else None
		if local:
			carpeta, nombre = ntpath.split(local)
			return ruta_local_rclone(carpeta) or "/", nombre
		return None

	def _config_entre_cuentas(self, origen: api.Proveedor) -> dict[str, Any]:
		if not isinstance(origen, ProveedorRclone) or origen.cuenta.id == self.cuenta.id:
			return {}
		if origen.cuenta.servicio != self.cuenta.servicio:
			return {}
		permitido = self.cuenta.copia_entre_cuentas
		if permitido is None:
			permitido = bool(self._nubes.opcion("copia_entre_cuentas", False))
		return {"ServerSideAcrossConfigs": True} if permitido else {}

	def transferir(self, origen: api.Proveedor, ruta_origen: str, ruta_destino: str,
			progreso: Callable[[int, int], None], cancelacion) -> bool:
		fuente = self._origen_rclone(origen, ruta_origen)
		if fuente is None:
			return False
		self._exigir_escritura(ruta_destino)
		fs_origen, nombre = fuente
		parametros = {"srcFs": fs_origen, "srcRemote": nombre, "dstFs": self.remoto, "dstRemote": ruta_remota(ruta_destino)}
		config = self._config_entre_cuentas(origen)
		try:
			self._nubes.ejecutar("operations/copyfile", cancelacion=cancelacion, progreso=progreso,
				**({"_config": config} if config else {}), **parametros)
		except api.Cancelado:
			raise
		except api.ErrorArchivos:
			if not config:
				raise
			log.info("La copia en el servidor entre cuentas falló; se repite pasando por zCommander", exc_info=True)
			self._nubes.ejecutar("operations/copyfile", cancelacion=cancelacion, progreso=progreso, **parametros)
		finally:
			self.invalidar(ruta_destino)
		return True

	def transferir_lote(self, origen: api.Proveedor, pares: Sequence[tuple[str, str]], mover: bool,
			progreso: Callable[[int, int], None], cancelacion) -> list[api.ResultadoPar] | None:
		if not pares or self._origen_rclone(origen, pares[0][0]) is None:
			return None
		self._exigir_escritura(pares[0][1])
		local = not isinstance(origen, ProveedorRclone)
		ruta_origen = (lambda r: origen.ruta_local(r) or r) if local else ruta_remota
		modulo = ntpath if local else posixpath
		origenes = [ruta_origen(o) for o, _d in pares]
		destinos = [ruta_remota(d) for _o, d in pares]
		try:
			raiz_origen = modulo.commonpath([modulo.dirname(o) for o in origenes]) if local else posixpath.commonpath(
				["/" + posixpath.dirname(o) for o in origenes]).lstrip("/")
		except ValueError:
			return None
		raiz_destino = posixpath.commonpath(["/" + posixpath.dirname(d) for d in destinos]).lstrip("/")
		lote: list[int] = []
		sueltos: list[int] = []
		relativos: list[str] = []
		for indice, (fuente, destino) in enumerate(zip(origenes, destinos, strict=True)):
			relativo_origen = modulo.relpath(fuente, raiz_origen).replace("\\", "/") if local else posixpath.relpath(
				"/" + fuente, "/" + raiz_origen)
			relativo_destino = posixpath.relpath("/" + destino, "/" + raiz_destino)
			if relativo_origen == relativo_destino and not relativo_origen.startswith(".."):
				lote.append(indice)
				relativos.append(relativo_origen)
			else:
				sueltos.append(indice)
		resultados: dict[int, api.ResultadoPar] = {}
		if lote:
			fs_origen = ruta_local_rclone(raiz_origen) if local else origen.remoto + raiz_origen  # type: ignore[union-attr]
			self._lote(fs_origen, raiz_destino, [pares[i] for i in lote], relativos, mover, origen, progreso, cancelacion,
				resultados, lote)
		for indice in sueltos:
			api.comprobar(cancelacion)
			fuente, destino = pares[indice]
			try:
				if mover:
					self._mover_uno(origen, fuente, destino, cancelacion)
				else:
					self.transferir(origen, fuente, destino, progreso, cancelacion)
				resultados[indice] = api.ResultadoPar(fuente, destino, True)
			except api.Cancelado:
				raise
			except api.ErrorArchivos as error:
				resultados[indice] = api.ResultadoPar(fuente, destino, False, error)
		self.invalidar()
		if isinstance(origen, ProveedorRclone):
			origen.invalidar()
		return [resultados[i] for i in range(len(pares))]

	def _mover_uno(self, origen: api.Proveedor, fuente: str, destino: str, cancelacion) -> None:
		fs_origen, nombre = self._origen_rclone(origen, fuente) or ("", "")
		self._nubes.ejecutar("operations/movefile", cancelacion=cancelacion, srcFs=fs_origen, srcRemote=nombre,
			dstFs=self.remoto, dstRemote=ruta_remota(destino))

	def _lote(self, fs_origen: str, raiz_destino: str, pares: list[tuple[str, str]], relativos: list[str], mover: bool,
			origen: api.Proveedor, progreso: Callable[[int, int], None], cancelacion,
			resultados: dict[int, api.ResultadoPar], indices: list[int]) -> None:
		"""Un solo ``sync/copy`` (o ``sync/move``) con la lista ``--files-from``."""
		lista = self._nubes.rutas.temp / f"zc-nubes-lista-{uuid.uuid4().hex}.txt"
		lista.parent.mkdir(parents=True, exist_ok=True)
		lista.write_text("\n".join(relativos) + "\n", encoding="utf-8")
		parametros: dict[str, Any] = {"srcFs": fs_origen, "dstFs": self.remoto + raiz_destino, "error": True,
			"_filter": {"FilesFrom": [str(lista)]}}
		config = self._config_entre_cuentas(origen)
		if config:
			parametros["_config"] = config
		if mover:
			parametros["deleteEmptySrcDirs"] = False
		try:
			self._nubes.ejecutar("sync/move" if mover else "sync/copy", cancelacion=cancelacion, progreso=progreso,
				conservar_salida=True, **parametros)
			for indice, par in zip(indices, pares, strict=True):
				resultados[indice] = api.ResultadoPar(par[0], par[1], True)
		except _FalloLote as fallo:
			fallidos = {str(r).replace("\\", "/") for r in fallo.salida.get("error", []) or []}
			for indice, par, relativo in zip(indices, pares, relativos, strict=True):
				if fallidos and relativo not in fallidos:
					resultados[indice] = api.ResultadoPar(par[0], par[1], True)
				else:
					resultados[indice] = api.ResultadoPar(par[0], par[1], False, fallo.error)
		finally:
			try:
				lista.unlink()
			except OSError:
				log.debug("No se pudo borrar la lista %s", lista, exc_info=True)


class _FalloLote(Exception):
	def __init__(self, error: api.ErrorArchivos, salida: dict) -> None:
		super().__init__(error.mensaje)
		self.error = error
		self.salida = salida


FalloLote = _FalloLote
ErrorTrabajoRC = ErrorTrabajo


class FlujoSubida(io.RawIOBase):
	"""Escritura en flujo hacia ``operations/uploadfile``: lo escrito pasa a un hilo que lo sube por trozos.

	Si se sale del ``with`` por un error, la subida se corta sin terminarla (rclone
	no crea un objeto a medias); al cerrar normalmente, espera a que rclone confirme.
	"""

	_FIN = object()
	_ABORTAR = object()

	def __init__(self, cliente: Any, remoto: str, carpeta: str, nombre: str, al_terminar: Callable[[], None] | None = None) -> None:
		super().__init__()
		self._cola: queue.Queue = queue.Queue(maxsize=16)
		self._error: BaseException | None = None
		self._al_terminar = al_terminar
		self._nombre = nombre

		def trozos():
			while True:
				trozo = self._cola.get()
				if trozo is FlujoSubida._FIN:
					return
				if trozo is FlujoSubida._ABORTAR:
					raise _SubidaAbortada()
				yield trozo

		def subir() -> None:
			try:
				cliente.subir(remoto, carpeta, nombre, trozos())
			except _SubidaAbortada:
				log.info("Subida de %s cancelada", nombre)
			except BaseException as error:  # noqa: BLE001 - se relanza en el hilo que escribe
				self._error = error
				while True:  # vacía la cola para que nadie quede bloqueado escribiendo
					try:
						self._cola.get_nowait()
					except queue.Empty:
						break

		self._hilo = threading.Thread(target=subir, daemon=True, name="zc-nubes-subida")
		self._hilo.start()

	def writable(self) -> bool:
		return True

	def _poner(self, elemento: Any) -> None:
		while True:
			if self._error is not None:
				raise self._error if isinstance(self._error, api.ErrorArchivos) else errores.traducir(self._error, self._nombre)
			if not self._hilo.is_alive():
				raise api.ErrorRed(_("La subida de {n} se cortó").format(n=self._nombre))
			try:
				self._cola.put(elemento, timeout=0.5)
				return
			except queue.Full:
				continue

	def write(self, datos: Any) -> int:
		if self.closed:
			raise ValueError("flujo cerrado")
		bloque = bytes(datos)
		if bloque:
			self._poner(bloque)
		return len(bloque)

	def abortar(self) -> None:
		if self.closed:
			return
		try:
			if self._hilo.is_alive():
				self._cola.put(FlujoSubida._ABORTAR, timeout=5)
		except queue.Full:
			log.debug("No se pudo avisar del corte de la subida de %s", self._nombre)
		self._hilo.join(30)
		super().close()

	def close(self) -> None:
		if self.closed:
			return
		try:
			if self._error is None and self._hilo.is_alive():
				self._poner(FlujoSubida._FIN)
			self._hilo.join()
		finally:
			super().close()
			if self._al_terminar is not None:
				self._al_terminar()
		if self._error is not None:
			raise self._error if isinstance(self._error, api.ErrorArchivos) else errores.traducir(self._error, self._nombre)

	def __exit__(self, tipo, valor, traza) -> None:
		if tipo is not None:
			self.abortar()
			return
		self.close()


class _SubidaAbortada(Exception):
	pass
