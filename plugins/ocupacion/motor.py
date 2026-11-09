# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor de la ocupación del disco (diseño 2.0, 11.8). Sin wx.

- ``analizar`` recorre una carpeta o unidad (sin seguir enlaces ni uniones,
  salvo que se pida) y guarda un árbol de CARPETAS con su tamaño total, sus
  archivos y su fecha más reciente; además los 100 archivos más grandes, la
  ocupación por extensión y los archivos antiguos. Los archivos de cada carpeta
  no se guardan (en una unidad entera serían millones): el proveedor los lee
  del disco al entrar en la carpeta, que es una sola lectura.
- ``ProveedorOcupacion`` (esquema ``ocupacion://<id>/<ruta>``) navega el
  análisis en el panel, de solo lectura, con las rutas reales del disco: así
  Ver, Copiar o «Ir a esta carpeta en el disco» funcionan sobre lo real.
- Cancelar deja el análisis parcial marcado como incompleto.
"""

from __future__ import annotations

import csv
import ctypes
import hashlib
import heapq
import io
import json
import logging
import os
import shutil
import stat
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from app.plugins import api

_ = api.traduccion("zc.ocupacion")[0]
log = logging.getLogger("zcplugins.zc.ocupacion")

ESQUEMA = "ocupacion"
MAYORES = 100
ANTIGUOS = 500
FORMATO = 1
#: Archivos de la nube que no están descargados (OneDrive y similares): no ocupan sitio en el disco.
_EN_NUBE = 0x00400000 | 0x00040000 | stat.FILE_ATTRIBUTE_OFFLINE
SIN_EXTENSION = "(sin extensión)"


def porcentaje(parte: int, total: int) -> str:
	"""«38 %», «33,3 %» o «0,4 %»: entero si es exacto, un decimal si no."""
	if total <= 0:
		return "0 %"
	valor = parte * 100 / total
	if abs(valor - round(valor)) < 1e-9:
		return f"{round(valor)} %"
	return f"{valor:.1f}".replace(".", ",") + " %"


def id_de(raiz: str) -> str:
	"""Id estable de un análisis: el mismo para la misma carpeta (así se recuerda el último)."""
	return hashlib.sha1(os.path.normcase(os.path.abspath(raiz)).encode("utf-8")).hexdigest()[:12]


# ── Datos ────────────────────────────────────────────────────────────────────


@dataclass
class Nodo:
	"""Una carpeta del análisis. ``tamano``, ``archivos`` y ``carpetas`` incluyen todo lo de dentro."""

	nombre: str
	ruta: str
	propio: int = 0
	archivos_propios: int = 0
	tamano: int = 0
	archivos: int = 0
	carpetas: int = 0
	modificado: float = 0.0
	sin_leer: bool = False
	hijos: list[Nodo] = field(default_factory=list)

	def como_lista(self) -> list:
		return [self.nombre, self.propio, self.archivos_propios, self.modificado, int(self.sin_leer), [h.como_lista() for h in self.hijos]]

	@classmethod
	def de_lista(cls, datos: list, padre: str) -> Nodo:
		nombre, propio, archivos_propios, modificado, sin_leer, hijos = datos
		ruta = os.path.join(padre, nombre) if padre else nombre
		nodo = cls(nombre, ruta, propio=propio, archivos_propios=archivos_propios, modificado=modificado, sin_leer=bool(sin_leer))
		nodo.hijos = [cls.de_lista(h, ruta) for h in hijos]
		return nodo


@dataclass(frozen=True)
class ArchivoGrande:
	tamano: int
	ruta: str
	modificado: float

	@property
	def nombre(self) -> str:
		return os.path.basename(self.ruta)

	@property
	def carpeta(self) -> str:
		return os.path.dirname(self.ruta)


@dataclass
class Opciones:
	seguir_enlaces: bool = False
	tamano_en_disco: bool = False
	incluir_nube: bool = False
	anios_antiguedad: int = 2


@dataclass
class Analisis:
	raiz: str
	nodo: Nodo
	fecha: float = field(default_factory=time.time)
	completo: bool = True
	opciones: Opciones = field(default_factory=Opciones)
	mayores: list[ArchivoGrande] = field(default_factory=list)
	antiguos: list[ArchivoGrande] = field(default_factory=list)
	antiguos_total: int = 0
	antiguos_bytes: int = 0
	extensiones: dict[str, list[int]] = field(default_factory=dict)
	sin_leer: int = 0
	unidad: tuple[int, int] | None = None  # (total, libre)
	_indice: dict[str, Nodo] = field(default_factory=dict, repr=False, compare=False)

	@property
	def id(self) -> str:
		return id_de(self.raiz)

	@property
	def direccion(self) -> str:
		return f"{ESQUEMA}://{self.id}/"

	def indexar(self) -> None:
		self._indice = {os.path.normcase(n.ruta): n for n in recorrer_nodos(self.nodo)}

	def buscar(self, ruta: str) -> Nodo | None:
		if not self._indice:
			self.indexar()
		return self._indice.get(os.path.normcase(ruta or self.raiz))

	def extensiones_ordenadas(self) -> list[tuple[str, int, int]]:
		"""(extensión, bytes, archivos) de más a menos ocupación."""
		return sorted(((e, v[0], v[1]) for e, v in self.extensiones.items()), key=lambda x: (-x[1], x[0]))

	def resumen(self) -> str:
		"""«D:\\Datos: 120 GB en 34 000 archivos y 2 100 carpetas; la unidad tiene 200 GB libres de 500 GB»."""
		n = self.nodo
		texto = _("{r}: {t} en {a} y {c}").format(r=self.raiz, t=api.formato.tamano_legible(n.tamano),
			a=api.formato.plural(n.archivos, _("{n} archivo"), _("{n} archivos")),
			c=api.formato.plural(n.carpetas, _("{n} carpeta"), _("{n} carpetas")))
		if self.unidad is not None:
			total, libre = self.unidad
			texto += "; " + _("la unidad tiene {l} libres de {t}").format(l=api.formato.tamano_legible(libre), t=api.formato.tamano_legible(total))
		if self.sin_leer:
			texto += "; " + api.formato.plural(self.sin_leer, _("{n} carpeta sin leer"), _("{n} carpetas sin leer"))
		if not self.completo:
			texto += ". " + _("Análisis incompleto: se canceló")
		return texto


def recorrer_nodos(nodo: Nodo) -> Iterator[Nodo]:
	pendientes = [nodo]
	while pendientes:
		actual = pendientes.pop()
		yield actual
		pendientes.extend(actual.hijos)


def describir(nodo: Nodo, total_padre: int) -> str:
	"""«Vídeos: 45 GB, 38 %, 1 200 archivos» (lo que se dice de una carpeta del análisis)."""
	return _("{n}: {t}, {p}, {a}").format(n=nodo.nombre, t=api.formato.tamano_legible(nodo.tamano), p=porcentaje(nodo.tamano, total_padre),
		a=api.formato.plural(nodo.archivos, _("{n} archivo"), _("{n} archivos")))


# ── Análisis ─────────────────────────────────────────────────────────────────


def _cluster(raiz: str) -> int:
	try:
		sectores, bytes_sector = ctypes.c_ulong(), ctypes.c_ulong()
		libres, totales = ctypes.c_ulong(), ctypes.c_ulong()
		unidad = os.path.splitdrive(os.path.abspath(raiz))[0] + "\\"
		if ctypes.windll.kernel32.GetDiskFreeSpaceW(unidad, ctypes.byref(sectores), ctypes.byref(bytes_sector),
				ctypes.byref(libres), ctypes.byref(totales)):
			return max(1, sectores.value * bytes_sector.value)
	except (AttributeError, OSError):
		log.debug("No se pudo saber el tamaño de clúster de %s", raiz, exc_info=True)
	return 4096


_kernel32: ctypes.WinDLL | None = None


def _comprimido(ruta: str) -> int | None:
	"""``GetCompressedFileSizeW``: lo que ocupa de verdad un archivo comprimido o disperso; ``None`` si falla."""
	global _kernel32
	if _kernel32 is None:
		_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
		_kernel32.GetCompressedFileSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
		_kernel32.GetCompressedFileSizeW.restype = ctypes.c_ulong
	alto = ctypes.c_ulong(0)
	bajo = _kernel32.GetCompressedFileSizeW(ruta, ctypes.byref(alto))
	if bajo == 0xFFFFFFFF and ctypes.get_last_error() != 0:
		return None
	return (alto.value << 32) + bajo


def _tamano_en_disco(ruta: str, logico: int, cluster: int) -> int:
	"""Tamaño ocupado en el disco: el comprimido o disperso, redondeado al clúster."""
	try:
		comprimido = _comprimido(ruta)
		if comprimido is not None:
			logico = comprimido
	except (AttributeError, OSError):
		log.debug("GetCompressedFileSizeW falló con %s", ruta, exc_info=True)
	return -(-logico // cluster) * cluster if logico else 0


def _extension(nombre: str) -> str:
	punto = nombre.rfind(".")
	return nombre[punto + 1:].lower() if punto > 0 else SIN_EXTENSION


def analizar(raiz: str, opciones: Opciones | None = None, cancelacion=None,
		al_avanzar: Callable[[str, int, int], None] | None = None) -> Analisis:
	"""Analiza ``raiz``. Si se cancela, devuelve lo leído hasta entonces con ``completo = False``."""
	opciones = opciones or Opciones()
	raiz = os.path.abspath(raiz)
	nombre_raiz = os.path.basename(raiz.rstrip("\\/")) or raiz
	analisis = Analisis(raiz, Nodo(nombre_raiz, raiz), opciones=opciones)
	limite_antiguo = time.time() - max(0, opciones.anios_antiguedad) * 365.25 * 86400
	cluster = _cluster(raiz) if opciones.tamano_en_disco else 1
	mayores: list[tuple[int, str, float]] = []
	antiguos: list[tuple[int, str, float]] = []
	visitadas: set[str] = set()
	pendientes: list[Nodo] = [analisis.nodo]
	todos: list[Nodo] = []
	archivos_vistos = bytes_vistos = 0
	try:
		while pendientes:
			api.comprobar(cancelacion)
			nodo = pendientes.pop()
			todos.append(nodo)
			if opciones.seguir_enlaces:
				real = os.path.normcase(os.path.realpath(nodo.ruta))
				if real in visitadas:
					continue  # un enlace que vuelve a una carpeta ya contada: sin bucles ni dobles cuentas
				visitadas.add(real)
			if al_avanzar is not None:
				al_avanzar(nodo.ruta, archivos_vistos, bytes_vistos)
			try:
				elementos = list(os.scandir(nodo.ruta))
			except OSError as error:
				log.debug("No se pudo leer %s: %s", nodo.ruta, error)
				nodo.sin_leer = True
				analisis.sin_leer += 1
				continue
			for elemento in elementos:
				api.comprobar(cancelacion)
				try:
					enlace = elemento.is_symlink() or elemento.is_junction()
					if enlace and not opciones.seguir_enlaces:
						continue
					if elemento.is_dir(follow_symlinks=opciones.seguir_enlaces):
						hijo = Nodo(elemento.name, elemento.path)
						nodo.hijos.append(hijo)
						pendientes.append(hijo)
						continue
					datos = elemento.stat(follow_symlinks=opciones.seguir_enlaces)
				except OSError:
					log.debug("No se pudo leer %s", elemento.path, exc_info=True)
					continue
				if not opciones.incluir_nube and getattr(datos, "st_file_attributes", 0) & _EN_NUBE:
					continue
				tamano = _tamano_en_disco(elemento.path, datos.st_size, cluster) if opciones.tamano_en_disco else datos.st_size
				nodo.propio += tamano
				nodo.archivos_propios += 1
				nodo.modificado = max(nodo.modificado, datos.st_mtime)
				archivos_vistos += 1
				bytes_vistos += tamano
				extension = analisis.extensiones.setdefault(_extension(elemento.name), [0, 0])
				extension[0] += tamano
				extension[1] += 1
				registro = (tamano, elemento.path, datos.st_mtime)
				if len(mayores) < MAYORES:
					heapq.heappush(mayores, registro)
				elif tamano > mayores[0][0]:
					heapq.heapreplace(mayores, registro)
				if datos.st_mtime < limite_antiguo:
					analisis.antiguos_total += 1
					analisis.antiguos_bytes += tamano
					if len(antiguos) < ANTIGUOS:
						heapq.heappush(antiguos, registro)
					elif tamano > antiguos[0][0]:
						heapq.heapreplace(antiguos, registro)
	except api.Cancelado:
		analisis.completo = False
	_sumar(todos or [analisis.nodo])
	analisis.mayores = [ArchivoGrande(t, r, m) for t, r, m in sorted(mayores, key=lambda x: (-x[0], x[1]))]
	analisis.antiguos = [ArchivoGrande(t, r, m) for t, r, m in sorted(antiguos, key=lambda x: (-x[0], x[1]))]
	try:
		uso = shutil.disk_usage(raiz)
		analisis.unidad = (uso.total, uso.free)
	except OSError:
		analisis.unidad = None
	analisis.indexar()
	return analisis


def _sumar(nodos: list[Nodo]) -> None:
	"""Totales de abajo arriba (los hijos se crearon después que su padre)."""
	for nodo in reversed(nodos):
		nodo.tamano = nodo.propio + sum(h.tamano for h in nodo.hijos)
		nodo.archivos = nodo.archivos_propios + sum(h.archivos for h in nodo.hijos)
		nodo.carpetas = len(nodo.hijos) + sum(h.carpetas for h in nodo.hijos)
		nodo.modificado = max([nodo.modificado, *(h.modificado for h in nodo.hijos)])
		nodo.hijos.sort(key=lambda h: (-h.tamano, h.nombre.casefold()))


# ── Guardar y recordar ───────────────────────────────────────────────────────


def _archivo(carpeta: Path, id_analisis: str) -> Path:
	return Path(carpeta) / f"{id_analisis}.json"


def guardar(analisis: Analisis, carpeta: Path) -> Path:
	"""Guarda el análisis en ``datos/analisis/`` (escritura atómica: un temporal y ``os.replace``)."""
	carpeta = Path(carpeta)
	carpeta.mkdir(parents=True, exist_ok=True)
	datos = {
		"formato": FORMATO, "raiz": analisis.raiz, "fecha": analisis.fecha, "completo": analisis.completo,
		"opciones": vars(analisis.opciones), "arbol": analisis.nodo.como_lista(),
		"mayores": [[a.tamano, a.ruta, a.modificado] for a in analisis.mayores],
		"antiguos": [[a.tamano, a.ruta, a.modificado] for a in analisis.antiguos],
		"antiguos_total": analisis.antiguos_total, "antiguos_bytes": analisis.antiguos_bytes,
		"extensiones": analisis.extensiones, "sin_leer": analisis.sin_leer,
		"unidad": list(analisis.unidad) if analisis.unidad else None,
	}
	destino = _archivo(carpeta, analisis.id)
	temporal = destino.with_suffix(".tmp")
	temporal.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
	os.replace(temporal, destino)
	return destino


def cargar(carpeta: Path, id_analisis: str) -> Analisis | None:
	"""El análisis guardado con ese id, o ``None`` si no hay o está dañado."""
	ruta = _archivo(carpeta, id_analisis)
	try:
		datos = json.loads(ruta.read_text(encoding="utf-8"))
		if datos.get("formato") != FORMATO:
			return None
		raiz = datos["raiz"]
		nombre, propio, archivos_propios, modificado, sin_leer, hijos = datos["arbol"]
		nodo = Nodo(nombre, raiz, propio=propio, archivos_propios=archivos_propios, modificado=modificado, sin_leer=bool(sin_leer))
		nodo.hijos = [Nodo.de_lista(h, raiz) for h in hijos]
		analisis = Analisis(raiz, nodo, fecha=datos["fecha"], completo=datos["completo"],
			opciones=Opciones(**{k: v for k, v in datos.get("opciones", {}).items() if k in Opciones.__dataclass_fields__}),
			mayores=[ArchivoGrande(*a) for a in datos.get("mayores", [])], antiguos=[ArchivoGrande(*a) for a in datos.get("antiguos", [])],
			antiguos_total=datos.get("antiguos_total", 0), antiguos_bytes=datos.get("antiguos_bytes", 0),
			extensiones={k: list(v) for k, v in datos.get("extensiones", {}).items()}, sin_leer=datos.get("sin_leer", 0),
			unidad=tuple(datos["unidad"]) if datos.get("unidad") else None)
	except FileNotFoundError:
		return None
	except (OSError, ValueError, KeyError, TypeError, IndexError):
		log.warning("El análisis guardado %s está dañado; se ignora", ruta, exc_info=True)
		return None
	_sumar(list(recorrer_nodos_en_orden(analisis.nodo)))
	analisis.indexar()
	return analisis


def recorrer_nodos_en_orden(nodo: Nodo) -> Iterator[Nodo]:
	"""Padres antes que hijos (lo que necesita ``_sumar``)."""
	cola = deque([nodo])
	while cola:
		actual = cola.popleft()
		yield actual
		cola.extend(actual.hijos)


# ── Exportar ─────────────────────────────────────────────────────────────────


def informe_texto(analisis: Analisis) -> str:
	lineas = [_("Ocupación del disco: informe de zCommander"), analisis.resumen(),
		_("Fecha del análisis: {f}").format(f=api.formato.fecha(analisis.fecha, "larga")), "", _("Carpetas del primer nivel:")]
	for hijo in analisis.nodo.hijos:
		lineas.append("  " + describir(hijo, analisis.nodo.tamano))
	lineas += ["", _("Los {n} archivos más grandes:").format(n=len(analisis.mayores))]
	lineas += [f"  {api.formato.tamano_legible(a.tamano)}  {a.ruta}" for a in analisis.mayores]
	lineas += ["", _("Ocupación por extensión:")]
	for extension, bytes_, archivos in analisis.extensiones_ordenadas():
		lineas.append("  " + _("{e}: {t}, {p}, {a}").format(e=extension, t=api.formato.tamano_legible(bytes_),
			p=porcentaje(bytes_, analisis.nodo.tamano), a=api.formato.plural(archivos, _("{n} archivo"), _("{n} archivos"))))
	lineas += ["", _("No modificados en más de {n} años: {a}, {t}").format(n=analisis.opciones.anios_antiguedad,
		a=api.formato.plural(analisis.antiguos_total, _("{n} archivo"), _("{n} archivos")),
		t=api.formato.tamano_legible(analisis.antiguos_bytes))]
	return "\n".join(lineas) + "\n"


def informe_csv(analisis: Analisis) -> str:
	"""Todas las carpetas del análisis: ruta, bytes, porcentaje del padre y del total, archivos y fecha."""
	salida = io.StringIO()
	escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
	escritor.writerow([_("Carpeta"), _("Bytes"), _("Porcentaje del padre"), _("Porcentaje del total"), _("Archivos"), _("Modificado")])
	total = analisis.nodo.tamano
	pendientes: list[tuple[Nodo, int]] = [(analisis.nodo, total)]
	while pendientes:
		nodo, del_padre = pendientes.pop(0)
		escritor.writerow([nodo.ruta, nodo.tamano, porcentaje(nodo.tamano, del_padre), porcentaje(nodo.tamano, total), nodo.archivos,
			api.formato.fecha(nodo.modificado, "larga") if nodo.modificado else ""])
		pendientes.extend((h, nodo.tamano) for h in nodo.hijos)
	return salida.getvalue()


def lista_csv(archivos: list[ArchivoGrande]) -> str:
	salida = io.StringIO()
	escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
	escritor.writerow([_("Nombre"), _("Bytes"), _("Carpeta"), _("Modificado")])
	for archivo in archivos:
		escritor.writerow([archivo.nombre, archivo.tamano, archivo.carpeta, api.formato.fecha(archivo.modificado, "larga")])
	return salida.getvalue()


# ── Proveedor ocupacion:// ───────────────────────────────────────────────────


class ProveedorOcupacion(api.Proveedor):
	"""Un análisis navegable en el panel, de solo lectura. Las rutas son las reales del disco."""

	esquema = ESQUEMA
	#: De mayor a menor tamaño mientras la persona no elija otro orden (API 1.1).
	orden_preferido = ("tamano", True)

	def __init__(self, analisis: Analisis) -> None:
		super().__init__()
		self.analisis = analisis
		self.capacidades = api.Capacidades(escribir=False)

	def descripcion(self) -> str:
		return _("Análisis de ocupación")

	def _nodo(self, ruta: str) -> Nodo:
		nodo = self.analisis.buscar(ruta)
		if nodo is None:
			raise api.NoEncontrado(_("La carpeta {r} no está en el análisis").format(r=ruta), ruta)
		return nodo

	@staticmethod
	def _entrada_nodo(nodo: Nodo) -> api.Entrada:
		return api.Entrada(nodo.nombre, nodo.ruta, es_carpeta=True, tamano=nodo.tamano, modificado=nodo.modificado)

	def listar(self, ruta: str, cancelacion=None) -> list[api.Entrada]:
		nodo = self._nodo(ruta)
		entradas = [self._entrada_nodo(h) for h in nodo.hijos]
		try:
			with os.scandir(nodo.ruta) as elementos:
				for elemento in elementos:
					api.comprobar(cancelacion)
					try:
						if elemento.is_dir(follow_symlinks=False) or elemento.is_junction():
							continue
						datos = elemento.stat(follow_symlinks=False)
					except OSError:
						continue
					entradas.append(api.Entrada(elemento.name, elemento.path, tamano=datos.st_size, modificado=datos.st_mtime,
						creado=getattr(datos, "st_birthtime", 0.0), atributos=getattr(datos, "st_file_attributes", 0),
						es_enlace=elemento.is_symlink()))
		except OSError:
			log.debug("No se pueden leer ahora los archivos de %s", nodo.ruta, exc_info=True)
		entradas.sort(key=lambda e: (-max(0, e.tamano), e.nombre.casefold()))
		return entradas

	def info(self, ruta: str) -> api.Entrada:
		if not ruta:
			return self._entrada_nodo(self.analisis.nodo)
		nodo = self.analisis.buscar(ruta)
		if nodo is not None:
			return self._entrada_nodo(nodo)
		try:
			datos = os.stat(ruta)
		except OSError as error:
			raise api.NoEncontrado(_("No existe {r}").format(r=ruta), ruta) from error
		return api.Entrada(os.path.basename(ruta), ruta, tamano=datos.st_size, modificado=datos.st_mtime)

	def padre(self, ruta: str) -> str | None:
		if not ruta or os.path.normcase(ruta) == os.path.normcase(self.analisis.raiz):
			return None
		return os.path.dirname(ruta)

	def unir(self, carpeta: str, nombre: str) -> str:
		return os.path.join(carpeta or self.analisis.raiz, nombre)

	def raiz(self, ruta: str) -> str:
		return self.analisis.raiz

	def mostrar(self, ruta: str) -> str:
		texto = _("Ocupación de {r}").format(r=ruta or self.analisis.raiz)
		return texto if self.analisis.completo else texto + _(" (incompleto)")

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		try:
			return open(ruta, "rb")
		except OSError as error:
			raise api.ErrorAcceso(_("No se puede leer {r}: {e}").format(r=ruta, e=error.strerror or error), ruta) from error

	def ruta_local(self, ruta: str) -> str | None:
		return ruta or self.analisis.raiz

	def espacio_libre(self, ruta: str) -> tuple[int, int] | None:
		try:
			uso = shutil.disk_usage(self.analisis.raiz)
		except OSError:
			return None
		return uso.free, uso.total

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		return os.path.splitdrive(ruta_a)[0].casefold() == os.path.splitdrive(ruta_b)[0].casefold()


def separar_direccion(direccion: str) -> tuple[str, str]:
	"""``ocupacion://<id>/<ruta>`` → (id, ruta); la ruta vacía es la raíz del análisis."""
	resto = direccion.split("://", 1)[1] if "://" in direccion else direccion
	id_analisis, _barra, ruta = resto.partition("/")
	return id_analisis, ruta


def valor_columna(columna: str, entrada: api.Entrada, proveedor: api.Proveedor) -> str | None:
	"""Columnas Porcentaje del padre, Porcentaje del total y Archivos (solo en un panel ``ocupacion://``)."""
	if not isinstance(proveedor, ProveedorOcupacion) or entrada.es_superior:
		return None
	analisis = proveedor.analisis
	tamano = max(0, entrada.tamano)
	if columna == "porcentaje_total":
		return porcentaje(tamano, analisis.nodo.tamano)
	if columna == "porcentaje_padre":
		padre = analisis.buscar(os.path.dirname(entrada.ruta))
		return porcentaje(tamano, padre.tamano if padre is not None else analisis.nodo.tamano)
	if columna == "archivos":
		nodo = analisis.buscar(entrada.ruta) if entrada.es_carpeta else None
		return api.formato.miles(nodo.archivos) if nodo is not None else ""
	return None


class OperacionAnalizar(api.Operacion):
	"""El análisis como operación del motor: progreso, pausa, cancelación (F12) y cola."""

	tipo = "ocupacion"

	def __init__(self, raiz: str, opciones: Opciones) -> None:
		super().__init__()
		self.raiz = os.path.abspath(raiz)
		self.opciones = opciones
		self.analisis: Analisis | None = None

	def descripcion(self) -> str:
		return _("Analizar la ocupación de {r}").format(r=self.raiz)

	@property
	def carriles(self) -> frozenset[str]:
		# Solo lee: no ocupa el carril de su unidad para no esperar a una copia ni hacerla esperar.
		return frozenset()

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)

		def avanzar(carpeta: str, archivos: int, bytes_: int) -> None:
			ctx.comprobar()
			self.progresar(actual=carpeta, archivos_hechos=archivos, bytes_hechos=bytes_)

		self.analisis = analizar(self.raiz, self.opciones, ctx.token, avanzar)
		if not self.analisis.completo:
			self.cambiar_estado(api.Estado.CANCELADA)
			return
		self.cambiar_estado(api.Estado.TERMINADA)

	def resumen(self) -> str:
		return self.analisis.resumen() if self.analisis is not None else super().resumen()
