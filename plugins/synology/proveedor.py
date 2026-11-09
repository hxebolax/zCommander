# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""File Station como origen del panel: ``synology://<id del servidor>/<carpeta compartida>/ruta`` (diseño 2.0, 13.7).

La raíz lista las carpetas compartidas (``List.list_share``); dentro, ``List.list``
paginado. Leer es ``Download.download`` en flujo; escribir, ``Upload.upload`` en
flujo multipart. Copiar o mover dentro del mismo NAS no pasa los bytes por el
equipo: usa ``CopyMove`` como tarea en segundo plano del propio NAS (gancho
``transferir`` y ``renombrar`` entre carpetas). En solo lectura el proveedor no
admite escritura (``Capacidades.escribir = False``) y cualquier escritura lanza
``SoloLectura`` con el mensaje del 116 sin llegar a enviarse.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from typing import Any, BinaryIO

from app.plugins import api

from . import errores
from .cliente import ClienteDSM

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.proveedor")

ESQUEMA = "synology"
PAGINA = 1000
ADICIONAL = ["real_path", "size", "owner", "time", "perm", "type"]


def separar_direccion(direccion: str) -> tuple[str, str]:
	"""«synology://casa/Documentos/a» → («casa», «/Documentos/a»)."""
	texto = (direccion or "").strip()
	if "://" in texto:
		texto = texto.split("://", 1)[1]
	texto = texto.replace("\\", "/")
	id_servidor, _barra, resto = texto.partition("/")
	return id_servidor.strip().lower(), normalizar(resto)


def normalizar(ruta: str) -> str:
	partes = [p for p in str(ruta or "").replace("\\", "/").split("/") if p and p != "."]
	return "/" + "/".join(partes)


def _posix(valor: Any) -> int:
	try:
		return int(str(valor), 8)
	except (TypeError, ValueError):
		return -1


class ProveedorSynology(api.Proveedor):
	"""Un NAS concreto visto por File Station."""

	esquema = ESQUEMA

	def __init__(self, conexiones: Any, id_servidor: str, preguntas: Callable[[], Any] | None = None) -> None:
		super().__init__()
		self._conexiones = conexiones
		self.id_servidor = id_servidor
		#: Identidad del servidor para ``clave_carril``: cada NAS es un carril distinto.
		self.servidor = f"{ESQUEMA}:{id_servidor}"
		self._preguntas = preguntas
		self._volumen: dict[str, tuple[int, int]] = {}

	# ``Proveedor.__init__`` asigna ``capacidades``: aquí se calcula en cada consulta según el modo del NAS.
	@property
	def capacidades(self) -> api.Capacidades:  # type: ignore[override]
		return api.Capacidades(escribir=not self._solo_lectura(), papelera=False, atributos=False, enlaces=False, vigilar=False,
			permisos=False, renombrar_barato=True, escritura_atomica=True, copia_servidor=True)

	@capacidades.setter
	def capacidades(self, _valor: Any) -> None:
		return

	def _solo_lectura(self) -> bool:
		conexion = self._conexiones.obtener(self.id_servidor)
		if conexion is not None:
			return conexion.solo_lectura
		servidor = self._conexiones.servidor(self.id_servidor)
		return True if servidor is None else bool(servidor.solo_lectura)

	def _cliente(self, cancelacion: Any = None) -> ClienteDSM:
		conexion = self._conexiones.obtener(self.id_servidor)
		if conexion is None:
			preguntas = self._preguntas() if self._preguntas is not None else None
			conexion = self._conexiones.conectar_id(self.id_servidor, preguntas, cancelacion)
		return conexion.cliente

	def descripcion(self) -> str:
		servidor = self._conexiones.servidor(self.id_servidor)
		nombre = servidor.nombre if servidor is not None else self.id_servidor
		return _("NAS Synology {n} (File Station)").format(n=nombre)

	# ── Rutas ────────────────────────────────────────────────────────────────

	def padre(self, ruta: str) -> str | None:
		ruta = normalizar(ruta)
		if ruta == "/":
			return None
		return ruta.rsplit("/", 1)[0] or "/"

	def unir(self, carpeta: str, nombre: str) -> str:
		return normalizar(f"{normalizar(carpeta)}/{nombre}")

	def raiz(self, ruta: str) -> str:
		return "/"

	def nombre(self, ruta: str) -> str:
		ruta = normalizar(ruta)
		if ruta == "/":
			servidor = self._conexiones.servidor(self.id_servidor)
			return servidor.nombre if servidor is not None else self.id_servidor
		return ruta.rsplit("/", 1)[-1]

	def mostrar(self, ruta: str) -> str:
		return f"{ESQUEMA}://{self.id_servidor}{normalizar(ruta)}"

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		return True

	# ── Lectura ──────────────────────────────────────────────────────────────

	def _entrada(self, fila: dict[str, Any]) -> api.Entrada:
		extra = fila.get("additional") or {}
		tiempos = extra.get("time") or {}
		nombre = str(fila.get("name", ""))
		atributos = api.formato.OCULTO if nombre.startswith((".", "#", "@")) else 0
		es_carpeta = bool(fila.get("isdir"))
		return api.Entrada(nombre=nombre, ruta=normalizar(str(fila.get("path", ""))), es_carpeta=es_carpeta,
			tamano=-1 if es_carpeta else int(extra.get("size", -1) or 0), modificado=float(tiempos.get("mtime", 0) or 0),
			creado=float(tiempos.get("crtime", 0) or 0), atributos=atributos,
			permisos=_posix((extra.get("perm") or {}).get("posix")))

	def listar(self, ruta: str, cancelacion: Any = None) -> list[api.Entrada]:
		ruta = normalizar(ruta)
		api.comprobar(cancelacion)
		cliente = self._cliente(cancelacion)
		if ruta == "/":
			datos = cliente.llamar("SYNO.FileStation.List", "list_share", additional=["real_path", "owner", "time", "perm",
				"volume_status"], offset=0, limit=0)
			entradas = []
			for fila in datos.get("shares", []):
				estado = ((fila.get("additional") or {}).get("volume_status")) or {}
				if estado:
					self._volumen[str(fila.get("name"))] = (int(estado.get("freespace", 0)), int(estado.get("totalspace", 0)))
				entradas.append(self._entrada(dict(fila, isdir=True)))
			return entradas
		entradas: list[api.Entrada] = []
		desplazamiento = 0
		while True:
			api.comprobar(cancelacion)
			datos = cliente.llamar("SYNO.FileStation.List", "list", folder_path=ruta, offset=desplazamiento, limit=PAGINA,
				additional=ADICIONAL)
			filas = datos.get("files", [])
			entradas.extend(self._entrada(f) for f in filas)
			desplazamiento += len(filas)
			if not filas or desplazamiento >= int(datos.get("total", 0) or 0):
				return entradas

	def info(self, ruta: str) -> api.Entrada:
		ruta = normalizar(ruta)
		if ruta == "/":
			return api.Entrada(nombre=self.nombre("/"), ruta="/", es_carpeta=True)
		datos = self._cliente().llamar("SYNO.FileStation.List", "getinfo", path=[ruta], additional=ADICIONAL)
		filas = datos.get("files", [])
		if not filas or filas[0].get("code"):
			raise api.NoEncontrado(_("No existe {r} en el NAS.").format(r=self.mostrar(ruta)), ruta)
		return self._entrada(filas[0])

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		flujo = self._cliente().descargar(normalizar(ruta))
		return io.BufferedReader(flujo, 256 * 1024)

	def espacio_libre(self, ruta: str) -> tuple[int, int] | None:
		ruta = normalizar(ruta)
		compartida = ruta.split("/")[1] if ruta != "/" else ""
		if not self._volumen:
			try:
				self.listar("/")
			except api.ErrorArchivos:
				return None
		if compartida in self._volumen:
			return self._volumen[compartida]
		return next(iter(self._volumen.values()), None)

	def suma(self, ruta: str, algoritmo: str) -> str | None:
		if algoritmo.lower() != "md5":
			return None
		datos = self._cliente().tarea_fondo("SYNO.FileStation.MD5", {"file_path": normalizar(ruta)})
		return str(datos.get("md5", "")) or None

	# ── Escritura ────────────────────────────────────────────────────────────

	def abrir_escritura(self, ruta: str, tamano: int = -1) -> BinaryIO:
		ruta = normalizar(ruta)
		carpeta, nombre = self.padre(ruta) or "/", self.nombre(ruta)
		return self._cliente().abrir_subida(carpeta, nombre, tamano, sobrescribir=True)

	def crear_carpeta(self, ruta: str) -> None:
		ruta = normalizar(ruta)
		carpeta, nombre = self.padre(ruta) or "/", self.nombre(ruta)
		try:
			self._cliente().llamar("SYNO.FileStation.CreateFolder", "create", folder_path=[carpeta], name=[nombre], force_parent=False)
		except errores.YaExisteDSM as error:
			raise api.YaExiste(_("Ya existe {n} en el NAS.").format(n=nombre), ruta) from error

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion: Any = None) -> None:
		ruta = normalizar(ruta)
		if ruta.count("/") < 2:
			raise api.ErrorAcceso(_("Las carpetas compartidas no se borran desde aquí: hágalo en el Panel de control de DSM."), ruta)
		self._cliente(cancelacion).tarea_fondo("SYNO.FileStation.Delete", {"path": [ruta], "recursive": True,
			"accurate_progress": False}, cancelacion=cancelacion)

	def renombrar(self, origen: str, destino: str) -> None:
		origen, destino = normalizar(origen), normalizar(destino)
		cliente = self._cliente()
		carpeta_origen, carpeta_destino = self.padre(origen) or "/", self.padre(destino) or "/"
		nombre_origen, nombre_destino = self.nombre(origen), self.nombre(destino)
		if carpeta_origen == carpeta_destino:
			cliente.llamar("SYNO.FileStation.Rename", "rename", path=[origen], name=[nombre_destino])
			return
		cliente.tarea_fondo("SYNO.FileStation.CopyMove", {"path": [origen], "dest_folder_path": carpeta_destino, "overwrite": False,
			"remove_src": True})
		if nombre_origen != nombre_destino:
			cliente.llamar("SYNO.FileStation.Rename", "rename", path=[self.unir(carpeta_destino, nombre_origen)], name=[nombre_destino])

	def transferir(self, origen: api.Proveedor, ruta_origen: str, ruta_destino: str, progreso: Callable[[int, int], None],
			cancelacion: Any) -> bool:
		"""Copia dentro del MISMO NAS con ``CopyMove`` (en el servidor, sin bajar ni subir los bytes)."""
		if not isinstance(origen, ProveedorSynology) or origen.id_servidor != self.id_servidor:
			return False
		ruta_origen, ruta_destino = normalizar(ruta_origen), normalizar(ruta_destino)
		cliente = self._cliente(cancelacion)
		carpeta = self.padre(ruta_destino) or "/"
		cliente.tarea_fondo("SYNO.FileStation.CopyMove", {"path": [ruta_origen], "dest_folder_path": carpeta, "overwrite": True,
			"remove_src": False}, progreso=progreso, cancelacion=cancelacion)
		if self.nombre(ruta_origen) != self.nombre(ruta_destino):
			cliente.llamar("SYNO.FileStation.Rename", "rename", path=[self.unir(carpeta, self.nombre(ruta_origen))],
				name=[self.nombre(ruta_destino)])
		return True


def crear_fabrica(conexiones: Any, preguntas: Callable[[], Any] | None = None) -> Callable[[str], tuple[api.Proveedor, str]]:
	"""Fábrica para ``zc.vfs.esquema("synology", ...)``: no conecta (lo hace el primer ``listar``, en su hilo)."""

	def fabrica(direccion: str) -> tuple[api.Proveedor, str]:
		id_servidor, ruta = separar_direccion(direccion)
		if not id_servidor or conexiones.servidor(id_servidor) is None:
			raise api.NoEncontrado(_("No hay ningún NAS con el nombre «{i}». Añádalo con Conectar con un NAS.").format(i=id_servidor),
				direccion)
		return ProveedorSynology(conexiones, id_servidor, preguntas), ruta

	return fabrica
