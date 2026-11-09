# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lector de repositorios Git en Python puro, solo lectura (diseño 2.0, 11.21). Sin wx.

Es la alternativa cuando no hay ``git.exe`` instalado: estado, historial y la
versión confirmada de un archivo (para las diferencias). El diseño proponía
dulwich vendorizado; este bloque no puede instalar ni descargar nada, así que
se lee el formato de Git directamente (está documentado y es estable):

- Referencias sueltas y ``packed-refs``; ``HEAD`` simbólico o separado.
- Objetos sueltos (zlib) y empaquetados (``.idx`` versión 2 y ``.pack`` con
  deltas ``OFS_DELTA`` y ``REF_DELTA``).
- Índice (``.git/index``) versiones 2, 3 y 4 (nombres comprimidos).
- ``.gitignore`` de cada carpeta y ``.git/info/exclude`` (patrones con ``!``,
  ``/`` al principio o al final y ``**``).

Nunca escribe nada dentro del repositorio.
"""

from __future__ import annotations

import bisect
import hashlib
import heapq
import mmap
import os
import re
import stat
import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

MODIFICADO = "modificado"
NUEVO = "nuevo"
SIN_SEGUIMIENTO = "sin seguimiento"
IGNORADO = "ignorado"
ELIMINADO = "eliminado"
RENOMBRADO = "renombrado"
CONFLICTO = "en conflicto"

TIPOS = {1: "commit", 2: "tree", 3: "blob", 4: "tag"}
OFS_DELTA, REF_DELTA = 6, 7
MODO_ARBOL = 0o040000
MODO_SUBMODULO = 0o160000


class ErrorGit(Exception):
	"""El repositorio no se puede leer (formato desconocido o dañado)."""


def buscar_raiz(carpeta: str) -> tuple[str, str] | None:
	"""(carpeta de trabajo, carpeta .git) del repositorio que contiene ``carpeta``, o ``None``."""
	actual = Path(carpeta).resolve()
	for candidata in (actual, *actual.parents):
		punto_git = candidata / ".git"
		if punto_git.is_dir() and (punto_git / "HEAD").is_file():
			return str(candidata), str(punto_git)
		if punto_git.is_file():
			try:
				texto = punto_git.read_text(encoding="utf-8", errors="replace").strip()
			except OSError:
				return None
			if texto.startswith("gitdir:"):
				destino = Path(texto[7:].strip())
				if not destino.is_absolute():
					destino = (candidata / destino).resolve()
				if (destino / "HEAD").is_file():
					return str(candidata), str(destino)
	return None


def _varint_desplazamiento(datos: bytes | mmap.mmap, posicion: int) -> tuple[int, int]:
	"""Entero del formato de desplazamientos de Git (OFS_DELTA y nombres del índice v4)."""
	c = datos[posicion]
	posicion += 1
	valor = c & 0x7F
	while c & 0x80:
		valor += 1
		c = datos[posicion]
		posicion += 1
		valor = (valor << 7) + (c & 0x7F)
	return valor, posicion


def _leb128(datos: bytes, posicion: int) -> tuple[int, int]:
	valor = desplazamiento = 0
	while True:
		c = datos[posicion]
		posicion += 1
		valor |= (c & 0x7F) << desplazamiento
		desplazamiento += 7
		if not c & 0x80:
			return valor, posicion


def aplicar_delta(base: bytes, delta: bytes) -> bytes:
	tamano_base, posicion = _leb128(delta, 0)
	if tamano_base != len(base):
		raise ErrorGit("delta sobre una base de otro tamaño")
	tamano, posicion = _leb128(delta, posicion)
	salida = bytearray()
	while posicion < len(delta):
		orden = delta[posicion]
		posicion += 1
		if orden & 0x80:
			desde = cuantos = 0
			for bit in range(4):
				if orden & (1 << bit):
					desde |= delta[posicion] << (8 * bit)
					posicion += 1
			for bit in range(3):
				if orden & (0x10 << bit):
					cuantos |= delta[posicion] << (8 * bit)
					posicion += 1
			salida += base[desde:desde + (cuantos or 0x10000)]
		elif orden:
			salida += delta[posicion:posicion + orden]
			posicion += orden
		else:
			raise ErrorGit("instrucción de delta no válida")
	if len(salida) != tamano:
		raise ErrorGit("delta de tamaño incorrecto")
	return bytes(salida)


class _Paquete:
	"""Un ``.pack`` con su ``.idx`` versión 2."""

	def __init__(self, idx: Path) -> None:
		datos = idx.read_bytes()
		if datos[:4] != b"\xfftOc" or struct.unpack_from(">I", datos, 4)[0] != 2:
			raise ErrorGit(f"índice de paquete no admitido: {idx.name}")
		self.total = struct.unpack_from(">I", datos, 8 + 255 * 4)[0]
		inicio_nombres = 8 + 256 * 4
		self.nombres = [datos[inicio_nombres + i * 20:inicio_nombres + (i + 1) * 20] for i in range(self.total)]
		inicio_despl = inicio_nombres + self.total * 24
		inicio_grandes = inicio_despl + self.total * 4
		self.desplazamientos = []
		for i in range(self.total):
			valor = struct.unpack_from(">I", datos, inicio_despl + i * 4)[0]
			if valor & 0x80000000:
				valor = struct.unpack_from(">Q", datos, inicio_grandes + (valor & 0x7FFFFFFF) * 8)[0]
			self.desplazamientos.append(valor)
		self.ruta = idx.with_suffix(".pack")
		self._archivo = None
		self._mapa: mmap.mmap | None = None

	def buscar(self, binario: bytes) -> int | None:
		posicion = bisect.bisect_left(self.nombres, binario)
		if posicion < self.total and self.nombres[posicion] == binario:
			return self.desplazamientos[posicion]
		return None

	def mapa(self) -> mmap.mmap:
		if self._mapa is None:
			self._archivo = open(self.ruta, "rb")  # noqa: SIM115 - vive con el paquete y se cierra en cerrar()
			self._mapa = mmap.mmap(self._archivo.fileno(), 0, access=mmap.ACCESS_READ)
		return self._mapa

	def cerrar(self) -> None:
		if self._mapa is not None:
			self._mapa.close()
			self._archivo.close()
			self._mapa = None


@dataclass(frozen=True)
class EntradaIndice:
	ruta: str
	sha: str
	tamano: int
	mtime: int
	mtime_ns: int
	modo: int
	etapa: int = 0


@dataclass(frozen=True)
class Confirmacion:
	sha: str
	autor: str
	fecha: int
	zona: str
	mensaje: str
	padres: tuple[str, ...] = ()
	arbol: str = ""

	@property
	def resumen(self) -> str:
		return self.mensaje.strip().splitlines()[0] if self.mensaje.strip() else ""


@dataclass
class _Ignorar:
	reglas: list[tuple[str, re.Pattern, bool, bool]] = field(default_factory=list)  # (base, patrón, negado, solo carpetas)


def _patron_a_regex(patron: str) -> tuple[re.Pattern, bool]:
	"""Un patrón de ``.gitignore`` a expresión regular sobre la ruta relativa a su carpeta."""
	anclado = "/" in patron.rstrip("/")
	patron = patron.lstrip("/")
	partes = []
	i = 0
	while i < len(patron):
		c = patron[i]
		if patron.startswith("**/", i):
			partes.append(r"(?:.*/)?")
			i += 3
			continue
		if patron.startswith("/**", i) and i + 3 == len(patron):
			partes.append(r"/.*")
			i += 3
			continue
		if patron.startswith("**", i):
			partes.append(r".*")
			i += 2
			continue
		if c == "*":
			partes.append(r"[^/]*")
		elif c == "?":
			partes.append(r"[^/]")
		elif c == "[":
			fin = patron.find("]", i + 1)
			if fin < 0:
				partes.append(re.escape(c))
			else:
				clase = patron[i + 1:fin].replace("\\", "\\\\")
				partes.append("[" + ("^" + clase[1:] if clase.startswith("!") else clase) + "]")
				i = fin
		elif c == "\\" and i + 1 < len(patron):
			i += 1
			partes.append(re.escape(patron[i]))
		else:
			partes.append(re.escape(c))
		i += 1
	cuerpo = "".join(partes)
	prefijo = "" if anclado else r"(?:.*/)?"
	return re.compile(f"^{prefijo}{cuerpo}$", re.IGNORECASE), anclado


class Repositorio:
	"""Un repositorio Git de solo lectura."""

	def __init__(self, raiz: str, git: str) -> None:
		self.raiz = raiz
		self.git = Path(git)
		comun = self.git / "commondir"
		self.comun = (self.git / comun.read_text(encoding="utf-8").strip()).resolve() if comun.is_file() else self.git
		self._paquetes: list[_Paquete] | None = None
		self._cache: dict[str, tuple[str, bytes]] = {}

	@classmethod
	def de_carpeta(cls, carpeta: str) -> Repositorio | None:
		encontrado = buscar_raiz(carpeta)
		return cls(*encontrado) if encontrado else None

	def cerrar(self) -> None:
		for paquete in self._paquetes or []:
			paquete.cerrar()
		self._paquetes = None

	# ── Referencias ─────────────────────────────────────────────────────────

	def _ref(self, nombre: str, profundidad: int = 0) -> str | None:
		if profundidad > 10:
			raise ErrorGit("referencias en bucle")
		for base in (self.git, self.comun):
			archivo = base / nombre
			if archivo.is_file():
				texto = archivo.read_text(encoding="utf-8", errors="replace").strip()
				if texto.startswith("ref:"):
					return self._ref(texto[4:].strip(), profundidad + 1)
				return texto or None
		empaquetadas = self.comun / "packed-refs"
		if empaquetadas.is_file():
			for linea in empaquetadas.read_text(encoding="utf-8", errors="replace").splitlines():
				if linea and not linea.startswith(("#", "^")):
					sha, _espacio, ref = linea.partition(" ")
					if ref.strip() == nombre:
						return sha.strip()
		return None

	def rama(self) -> str:
		"""Nombre de la rama actual, o ``""`` con HEAD separado."""
		texto = (self.git / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
		if texto.startswith("ref:"):
			ref = texto[4:].strip()
			return ref.removeprefix("refs/heads/")
		return ""

	def head(self) -> str | None:
		return self._ref("HEAD")

	def ramas(self) -> list[str]:
		nombres = set()
		carpeta = self.comun / "refs" / "heads"
		if carpeta.is_dir():
			for archivo in carpeta.rglob("*"):
				if archivo.is_file():
					nombres.add(archivo.relative_to(carpeta).as_posix())
		empaquetadas = self.comun / "packed-refs"
		if empaquetadas.is_file():
			for linea in empaquetadas.read_text(encoding="utf-8", errors="replace").splitlines():
				_sha, _e, ref = linea.partition(" ")
				if ref.startswith("refs/heads/"):
					nombres.add(ref.removeprefix("refs/heads/"))
		return sorted(nombres)

	# ── Objetos ─────────────────────────────────────────────────────────────

	def _lista_paquetes(self) -> list[_Paquete]:
		if self._paquetes is None:
			carpeta = self.comun / "objects" / "pack"
			self._paquetes = [_Paquete(idx) for idx in sorted(carpeta.glob("*.idx"))] if carpeta.is_dir() else []
		return self._paquetes

	def objeto(self, sha: str) -> tuple[str, bytes]:
		"""(tipo, contenido) de un objeto."""
		if sha in self._cache:
			return self._cache[sha]
		suelto = self.comun / "objects" / sha[:2] / sha[2:]
		if suelto.is_file():
			datos = zlib.decompress(suelto.read_bytes())
			cabecera, _nulo, contenido = datos.partition(b"\0")
			resultado = (cabecera.split(b" ", 1)[0].decode("ascii"), contenido)
		else:
			binario = bytes.fromhex(sha)
			for paquete in self._lista_paquetes():
				desplazamiento = paquete.buscar(binario)
				if desplazamiento is not None:
					resultado = self._de_paquete(paquete, desplazamiento)
					break
			else:
				raise ErrorGit(f"falta el objeto {sha}")
		if len(self._cache) > 2000:
			self._cache.clear()
		self._cache[sha] = resultado
		return resultado

	def _de_paquete(self, paquete: _Paquete, desplazamiento: int) -> tuple[str, bytes]:
		mapa = paquete.mapa()
		posicion = desplazamiento
		c = mapa[posicion]
		posicion += 1
		tipo = (c >> 4) & 7
		while c & 0x80:
			c = mapa[posicion]
			posicion += 1
		if tipo == OFS_DELTA:
			distancia, posicion = _varint_desplazamiento(mapa, posicion)
			base = self._de_paquete(paquete, desplazamiento - distancia)
		elif tipo == REF_DELTA:
			base = self.objeto(mapa[posicion:posicion + 20].hex())
			posicion += 20
		descompresor = zlib.decompressobj()
		datos = bytearray()
		while not descompresor.eof:
			trozo = mapa[posicion:posicion + 65536]
			if not trozo:
				raise ErrorGit("paquete truncado")
			datos += descompresor.decompress(trozo)
			posicion += len(trozo)
		if tipo in (OFS_DELTA, REF_DELTA):
			return base[0], aplicar_delta(base[1], bytes(datos))
		if tipo not in TIPOS:
			raise ErrorGit(f"tipo de objeto desconocido: {tipo}")
		return TIPOS[tipo], bytes(datos)

	def arbol(self, sha: str) -> list[tuple[int, str, str]]:
		tipo, datos = self.objeto(sha)
		if tipo != "tree":
			raise ErrorGit(f"{sha} no es un árbol")
		entradas = []
		posicion = 0
		while posicion < len(datos):
			espacio = datos.index(b" ", posicion)
			nulo = datos.index(b"\0", espacio)
			modo = int(datos[posicion:espacio], 8)
			nombre = datos[espacio + 1:nulo].decode("utf-8", errors="surrogateescape")
			entradas.append((modo, nombre, datos[nulo + 1:nulo + 21].hex()))
			posicion = nulo + 21
		return entradas

	def confirmacion(self, sha: str) -> Confirmacion:
		tipo, datos = self.objeto(sha)
		if tipo != "commit":
			raise ErrorGit(f"{sha} no es una confirmación")
		cabecera, _separador, mensaje = datos.decode("utf-8", errors="replace").partition("\n\n")
		arbol, padres, autor, fecha, zona = "", [], "", 0, "+0000"
		for linea in cabecera.splitlines():
			clave, _e, valor = linea.partition(" ")
			if clave == "tree":
				arbol = valor
			elif clave == "parent":
				padres.append(valor)
			elif clave == "author":
				encontrado = re.match(r"(.*?) <.*?> (\d+) ([+-]\d{4})", valor)
				if encontrado:
					autor, fecha, zona = encontrado.group(1), int(encontrado.group(2)), encontrado.group(3)
		return Confirmacion(sha, autor, fecha, zona, mensaje, tuple(padres), arbol)

	def archivos(self, arbol: str, prefijo: str = "") -> dict[str, str]:
		"""``{ruta: sha del blob}`` de todo un árbol."""
		resultado: dict[str, str] = {}
		for modo, nombre, sha in self.arbol(arbol):
			ruta = f"{prefijo}{nombre}"
			if modo == MODO_ARBOL:
				resultado.update(self.archivos(sha, ruta + "/"))
			elif modo != MODO_SUBMODULO:
				resultado[ruta] = sha
		return resultado

	def entrada_en(self, arbol: str, ruta: str) -> str | None:
		"""Sha del blob o del árbol de ``ruta`` (con «/») dentro de ``arbol``; ``""`` es el propio árbol."""
		actual = arbol
		for parte in [p for p in ruta.split("/") if p]:
			siguiente = next((sha for _m, nombre, sha in self.arbol(actual) if nombre == parte), None)
			if siguiente is None:
				return None
			actual = siguiente
		return actual

	def contenido_confirmado(self, ruta: str, referencia: str = "HEAD") -> bytes | None:
		"""Contenido de ``ruta`` (relativa, con «/») en la última confirmación; ``None`` si no estaba."""
		sha = self._ref(referencia) if not re.fullmatch(r"[0-9a-f]{40}", referencia) else referencia
		if not sha:
			return None
		blob = self.entrada_en(self.confirmacion(sha).arbol, ruta)
		if blob is None:
			return None
		tipo, datos = self.objeto(blob)
		return datos if tipo == "blob" else None

	# ── Índice ──────────────────────────────────────────────────────────────

	def indice(self) -> list[EntradaIndice]:
		archivo = self.git / "index"
		if not archivo.is_file():
			return []
		datos = archivo.read_bytes()
		if datos[:4] != b"DIRC":
			raise ErrorGit("índice dañado")
		version, total = struct.unpack_from(">II", datos, 4)
		if version not in (2, 3, 4):
			raise ErrorGit(f"versión del índice no admitida: {version}")
		posicion = 12
		anterior = b""
		entradas = []
		for _i in range(total):
			inicio = posicion
			campos = struct.unpack_from(">10I", datos, posicion)
			posicion += 40
			sha = datos[posicion:posicion + 20].hex()
			posicion += 20
			banderas = struct.unpack_from(">H", datos, posicion)[0]
			posicion += 2
			if version >= 3 and banderas & 0x4000:
				posicion += 2
			if version == 4:
				quitar, posicion = _varint_desplazamiento(datos, posicion)
				fin = datos.index(b"\0", posicion)
				nombre = anterior[:len(anterior) - quitar] + datos[posicion:fin]
				posicion = fin + 1
			else:
				fin = datos.index(b"\0", posicion)
				nombre = datos[posicion:fin]
				posicion = inicio + ((fin - inicio) // 8 + 1) * 8
			anterior = nombre
			entradas.append(EntradaIndice(nombre.decode("utf-8", errors="surrogateescape"), sha, campos[9], campos[2], campos[3],
				campos[6], (banderas >> 12) & 3))
		return entradas

	# ── Estado ──────────────────────────────────────────────────────────────

	def _sha_trabajo(self, ruta: Path) -> str:
		datos = ruta.read_bytes()
		return hashlib.sha1(b"blob %d\0" % len(datos) + datos, usedforsecurity=False).hexdigest()

	def _igual(self, ruta: Path, entrada: EntradaIndice) -> bool:
		try:
			info = ruta.stat()
		except OSError:
			return False
		if info.st_size == entrada.tamano and int(info.st_mtime) == entrada.mtime and info.st_mtime_ns % 1_000_000_000 == entrada.mtime_ns:
			return True
		datos = ruta.read_bytes()
		for variante in (datos, datos.replace(b"\r\n", b"\n")):
			if hashlib.sha1(b"blob %d\0" % len(variante) + variante, usedforsecurity=False).hexdigest() == entrada.sha:
				return True
		return False

	def _reglas_ignorar(self) -> _Ignorar:
		reglas = _Ignorar()
		exclude = self.comun / "info" / "exclude"
		if exclude.is_file():
			self._anadir_reglas(reglas, "", exclude)
		return reglas

	def _anadir_reglas(self, reglas: _Ignorar, base: str, archivo: Path) -> None:
		try:
			lineas = archivo.read_text(encoding="utf-8", errors="replace").splitlines()
		except OSError:
			return
		for linea in lineas:
			linea = linea.rstrip()
			if not linea or linea.startswith("#"):
				continue
			negado = linea.startswith("!")
			if negado:
				linea = linea[1:]
			solo_carpetas = linea.endswith("/")
			patron, _anclado = _patron_a_regex(linea.rstrip("/"))
			reglas.reglas.append((base, patron, negado, solo_carpetas))

	@staticmethod
	def _ignorado(reglas: _Ignorar, ruta: str, es_carpeta: bool) -> bool:
		resultado = False
		for base, patron, negado, solo_carpetas in reglas.reglas:
			if base and not ruta.startswith(base + "/"):
				continue
			relativa = ruta[len(base) + 1:] if base else ruta
			if solo_carpetas and not es_carpeta:
				continue
			if patron.match(relativa):
				resultado = not negado
		return resultado

	def estado(self, incluir_ignorados: bool = True) -> dict[str, str]:
		"""``{ruta relativa con «/»: estado}`` de lo que no está limpio (y de las carpetas ignoradas, con «/» al final)."""
		resultado: dict[str, str] = {}
		head = self.head()
		confirmados = self.archivos(self.confirmacion(head).arbol) if head else {}
		indice = self.indice()
		en_indice = {}
		for entrada in indice:
			if entrada.etapa:
				resultado[entrada.ruta] = CONFLICTO
				continue
			en_indice[entrada.ruta] = entrada
		for ruta, entrada in en_indice.items():
			if ruta not in confirmados:
				resultado[ruta] = NUEVO
			elif confirmados[ruta] != entrada.sha:
				resultado[ruta] = MODIFICADO
			archivo = Path(self.raiz, *ruta.split("/"))
			if not archivo.exists():
				resultado[ruta] = ELIMINADO
			elif not stat.S_ISLNK(entrada.modo) and not self._igual(archivo, entrada):
				resultado.setdefault(ruta, MODIFICADO)
		for ruta in confirmados:
			if ruta not in en_indice and ruta not in resultado:
				resultado[ruta] = ELIMINADO
		reglas = self._reglas_ignorar()
		carpetas_indice = {r.rsplit("/", 1)[0] for r in en_indice if "/" in r}
		carpetas_con_seguidos = set()
		for carpeta in carpetas_indice:
			partes = carpeta.split("/")
			for i in range(1, len(partes) + 1):
				carpetas_con_seguidos.add("/".join(partes[:i]))
		for ruta, es_carpeta in self._recorrer("", reglas):
			if ruta in en_indice:
				continue
			if self._ignorado(reglas, ruta, es_carpeta):
				if incluir_ignorados and (not es_carpeta or ruta not in carpetas_con_seguidos):
					resultado[ruta + ("/" if es_carpeta else "")] = IGNORADO
				continue
			if not es_carpeta:
				resultado[ruta] = SIN_SEGUIMIENTO
		return resultado

	def _recorrer(self, relativa: str, reglas: _Ignorar) -> Iterator[tuple[str, bool]]:
		"""Rutas de la carpeta de trabajo; no entra en carpetas ignoradas ni en ``.git``."""
		carpeta = Path(self.raiz, *relativa.split("/")) if relativa else Path(self.raiz)
		gitignore = carpeta / ".gitignore"
		if gitignore.is_file():
			self._anadir_reglas(reglas, relativa, gitignore)
		try:
			elementos = sorted(os.scandir(carpeta), key=lambda e: e.name)
		except OSError:
			return
		for elemento in elementos:
			if elemento.name == ".git":
				continue
			ruta = f"{relativa}/{elemento.name}" if relativa else elemento.name
			es_carpeta = elemento.is_dir(follow_symlinks=False)
			yield ruta, es_carpeta
			if es_carpeta and not self._ignorado(reglas, ruta, True) and not (Path(elemento.path) / ".git").exists():
				yield from self._recorrer(ruta, reglas)

	# ── Historial ───────────────────────────────────────────────────────────

	def historial(self, ruta: str = "", maximo: int = 500, visitar: int = 20000) -> list[Confirmacion]:
		"""Confirmaciones que cambian ``ruta`` (archivo o carpeta, relativa con «/»; vacía = todo), de la más reciente a la más antigua."""
		head = self.head()
		if not head:
			return []
		resultado: list[Confirmacion] = []
		vistos = {head}
		cola = [(-self.confirmacion(head).fecha, head)]
		while cola and len(resultado) < maximo and len(vistos) <= visitar:
			_fecha, sha = heapq.heappop(cola)
			confirmacion = self.confirmacion(sha)
			actual = self.entrada_en(confirmacion.arbol, ruta) if ruta else confirmacion.arbol
			anterior = None
			if confirmacion.padres:
				padre = self.confirmacion(confirmacion.padres[0])
				anterior = self.entrada_en(padre.arbol, ruta) if ruta else padre.arbol
			if actual != anterior and (actual is not None or anterior is not None):
				resultado.append(confirmacion)
			for padre in confirmacion.padres:
				if padre not in vistos:
					vistos.add(padre)
					heapq.heappush(cola, (-self.confirmacion(padre).fecha, padre))
		return resultado
