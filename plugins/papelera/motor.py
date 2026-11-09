# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Papelera de reciclaje de Windows como origen del panel (diseño 2.0, 11.20). Sin wx.

Cómo guarda Windows (Vista y posteriores) lo que se envía a la papelera: en
cada unidad fija, ``<unidad>\\$Recycle.Bin\\<SID del usuario>\\`` tiene, por
cada elemento, un ``$R<id>.<ext>`` (el archivo o la carpeta, renombrado) y un
``$I<id>.<ext>`` con los datos: versión (8 bytes), tamaño original (8),
fecha de eliminación como FILETIME (8) y la ruta original (en la versión 2,
longitud de 4 bytes y la ruta en UTF-16; en la 1, 260 caracteres fijos).

Leer esos ``$I`` es lo mismo que hace el Explorador para sus columnas
«Ubicación original» y «Fecha de eliminación», sin COM y sin bloquear. Restaurar
es devolver el ``$R`` a su ruta original y borrar su ``$I`` (lo que hace el
Explorador); vaciar usa ``SHEmptyRecycleBin`` del shell para que el icono y el
Explorador se enteren.

El proveedor ``papelera://`` (todas las unidades) o ``papelera://D:/`` (una)
lista los elementos con su nombre original, la carpeta original en
``ruta_real`` (columna Ruta) y la fecha de eliminación en ``modificado``.
"""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import string
import struct
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import BinaryIO

from app.plugins import api

_ = api.traduccion("zc.papelera")[0]
log = logging.getLogger("zcplugins.zc.papelera")

ESQUEMA = "papelera"
DIRECCION = f"{ESQUEMA}://"
CARPETA = "$Recycle.Bin"
_EPOCA_FILETIME = 116444736000000000  # 1601-01-01 → 1970-01-01, en intervalos de 100 ns


def filetime_a_marca(valor: int) -> float:
	return max(0.0, (valor - _EPOCA_FILETIME) / 10_000_000) if valor else 0.0


def marca_a_filetime(marca: float) -> int:
	return int(marca * 10_000_000) + _EPOCA_FILETIME


# ── Archivos $I ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Elemento:
	"""Un elemento de la papelera."""

	ruta_r: str          # el $R: el contenido (archivo o carpeta)
	ruta_i: str          # el $I: los datos
	original: str        # ruta completa de donde se eliminó
	tamano: int
	eliminado: float     # marca de tiempo

	@property
	def nombre(self) -> str:
		return os.path.basename(self.original.rstrip("\\/")) or self.original

	@property
	def carpeta_original(self) -> str:
		return os.path.dirname(self.original.rstrip("\\/"))

	@property
	def unidad(self) -> str:
		return os.path.splitdrive(self.ruta_r)[0].upper()


def leer_i(datos: bytes) -> tuple[int, float, str]:
	"""(tamaño, fecha de eliminación, ruta original) de un ``$I``. Lanza ``ValueError`` si no lo es."""
	if len(datos) < 24:
		raise ValueError("$I demasiado corto")
	version, tamano, filetime = struct.unpack_from("<qqq", datos, 0)
	if version == 2:
		(longitud,) = struct.unpack_from("<i", datos, 24)
		ruta = datos[28:28 + longitud * 2].decode("utf-16-le", errors="replace")
	elif version == 1:
		ruta = datos[24:24 + 520].decode("utf-16-le", errors="replace")
	else:
		raise ValueError(f"versión de $I desconocida: {version}")
	return tamano, filetime_a_marca(filetime), ruta.split("\x00", 1)[0]


def formar_i(tamano: int, eliminado: float, original: str) -> bytes:
	"""Un ``$I`` versión 2 (lo usan las pruebas para crear una papelera de mentira)."""
	ruta = original + "\x00"
	return struct.pack("<qqqi", 2, tamano, marca_a_filetime(eliminado), len(ruta)) + ruta.encode("utf-16-le")


# ── Dónde están las papeleras ────────────────────────────────────────────────


def sid_usuario() -> str:
	"""SID del usuario actual en texto («S-1-5-21-...»); vacío si no se puede saber."""
	try:
		import win32api
		import win32con
		import win32security

		token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
		sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
		return win32security.ConvertSidToStringSid(sid)
	except Exception:  # noqa: BLE001 - sin pywin32 se busca la carpeta que se pueda leer
		log.debug("No se pudo obtener el SID del usuario", exc_info=True)
		return ""


def unidades_fijas() -> list[str]:
	"""Letras de las unidades fijas («C:», «D:») con papelera."""
	resultado = []
	try:
		mascara = ctypes.windll.kernel32.GetLogicalDrives()
		for indice, letra in enumerate(string.ascii_uppercase):
			if mascara & (1 << indice) and ctypes.windll.kernel32.GetDriveTypeW(f"{letra}:\\") == 3:  # DRIVE_FIXED
				resultado.append(f"{letra}:")
	except (AttributeError, OSError):
		log.debug("No se pudieron listar las unidades", exc_info=True)
	return resultado


def carpetas_papelera(unidades: Iterable[str], sid: str = "") -> list[str]:
	"""Las carpetas ``$Recycle.Bin\\<SID>`` de las unidades que existen y se pueden leer."""
	sid = sid or sid_usuario()
	resultado = []
	for unidad in unidades:
		base = os.path.join(unidad.rstrip("\\/:") + ":\\", CARPETA)
		candidatas = [os.path.join(base, sid)] if sid else []
		if not sid:
			try:
				candidatas = [e.path for e in os.scandir(base) if e.is_dir() and e.name.upper().startswith("S-1-5-")]
			except OSError:
				candidatas = []
		for carpeta in candidatas:
			if os.path.isdir(carpeta):
				resultado.append(carpeta)
	return resultado


def leer_carpeta(carpeta: str, cancelacion=None) -> list[Elemento]:
	"""Elementos de una carpeta ``$Recycle.Bin\\<SID>`` (los ``$I`` sin su ``$R`` se omiten)."""
	elementos = []
	try:
		nombres = os.listdir(carpeta)
	except OSError:
		log.debug("No se puede leer la papelera %s", carpeta, exc_info=True)
		return []
	presentes = {n.casefold() for n in nombres}
	for nombre in nombres:
		api.comprobar(cancelacion)
		if not nombre.upper().startswith("$I"):
			continue
		nombre_r = "$R" + nombre[2:]
		if nombre_r.casefold() not in presentes:
			continue
		ruta_i = os.path.join(carpeta, nombre)
		try:
			with open(ruta_i, "rb") as archivo:
				tamano, eliminado, original = leer_i(archivo.read(4096))
		except (OSError, ValueError, struct.error):
			log.debug("$I ilegible: %s", ruta_i, exc_info=True)
			continue
		elementos.append(Elemento(os.path.join(carpeta, nombre_r), ruta_i, original, tamano, eliminado))
	return elementos


# ── Restaurar, eliminar y vaciar ─────────────────────────────────────────────


def nombre_libre(ruta: str) -> str:
	"""«informe (2).txt» si «informe.txt» ya existe."""
	if not os.path.lexists(ruta):
		return ruta
	carpeta, nombre = os.path.split(ruta)
	base, extension = os.path.splitext(nombre)
	contador = 2
	while True:
		candidata = os.path.join(carpeta, f"{base} ({contador}){extension}")
		if not os.path.lexists(candidata):
			return candidata
		contador += 1


def restaurar(elemento: Elemento, destino: str = "") -> str:
	"""Devuelve el elemento a ``destino`` (por defecto su ruta original) y borra su ``$I``. Devuelve la ruta final."""
	destino = destino or elemento.original
	if os.path.lexists(destino):
		raise api.YaExiste(_("Ya existe {r}").format(r=destino), destino)
	os.makedirs(os.path.dirname(destino), exist_ok=True)
	try:
		os.rename(elemento.ruta_r, destino)
	except OSError:
		shutil.move(elemento.ruta_r, destino)
	try:
		os.remove(elemento.ruta_i)
	except OSError:
		log.debug("No se pudo borrar %s tras restaurar", elemento.ruta_i, exc_info=True)
	return destino


def eliminar_definitivo(elemento: Elemento) -> None:
	if os.path.isdir(elemento.ruta_r) and not os.path.islink(elemento.ruta_r):
		shutil.rmtree(elemento.ruta_r)
	elif os.path.lexists(elemento.ruta_r):
		os.remove(elemento.ruta_r)
	if os.path.lexists(elemento.ruta_i):
		os.remove(elemento.ruta_i)


def vaciar_con_shell(unidad: str = "") -> None:
	"""``SHEmptyRecycleBin`` sin preguntas del shell (la pregunta ya la hizo zCommander)."""
	from win32com.shell import shell, shellcon

	banderas = shellcon.SHERB_NOCONFIRMATION | shellcon.SHERB_NOPROGRESSUI | shellcon.SHERB_NOSOUND
	try:
		shell.SHEmptyRecycleBin(None, (unidad.rstrip("\\/") + "\\") if unidad else None, banderas)
	except Exception as error:  # noqa: BLE001 - pywintypes.com_error: con la papelera ya vacía devuelve un error
		if getattr(error, "hresult", None) not in (None, -2147418113):  # E_UNEXPECTED = ya vacía
			raise api.ErrorArchivos(_("No se pudo vaciar la papelera: {e}").format(e=error)) from error


def avisar_shell(carpeta: str) -> None:
	"""Pide al Explorador que vuelva a leer una carpeta (la papelera tras restaurar)."""
	try:
		from win32com.shell import shell, shellcon

		shell.SHChangeNotify(shellcon.SHCNE_UPDATEDIR, shellcon.SHCNF_PATHW | shellcon.SHCNF_FLUSHNOWAIT, carpeta, None)
	except Exception:  # noqa: BLE001 - es solo un aviso al Explorador
		log.debug("SHChangeNotify falló con %s", carpeta, exc_info=True)


def resumen(elementos: Sequence[Elemento]) -> str:
	"""«312 elementos, 4,2 GB» (o «La papelera está vacía»)."""
	if not elementos:
		return _("La papelera está vacía")
	return _("{n}, {t}").format(n=api.formato.plural(len(elementos), _("{n} elemento"), _("{n} elementos")),
		t=api.formato.tamano_legible(sum(max(0, e.tamano) for e in elementos)))


# ── Proveedor papelera:// ────────────────────────────────────────────────────


class Papelera:
	"""Las papeleras de las unidades elegidas; ``fuentes`` se puede cambiar en las pruebas."""

	def __init__(self, fuentes: Callable[[], list[str]]) -> None:
		self._fuentes = fuentes

	def carpetas(self) -> list[str]:
		return self._fuentes()

	def elementos(self, unidad: str = "", cancelacion=None) -> list[Elemento]:
		resultado = []
		for carpeta in self.carpetas():
			if unidad and os.path.splitdrive(carpeta)[0].casefold() != unidad.rstrip("\\/").casefold():
				continue
			resultado.extend(leer_carpeta(carpeta, cancelacion))
		resultado.sort(key=lambda e: (-e.eliminado, e.nombre.casefold()))
		return resultado


class ProveedorPapelera(api.Proveedor):
	"""``papelera://`` o ``papelera://D:/``: la raíz es la lista de elementos; dentro de una carpeta eliminada se navega leyendo."""

	esquema = ESQUEMA
	#: Lo último eliminado primero (la fecha de las filas de la raíz es la de eliminación); API 1.1.
	orden_preferido = ("fecha", True)

	def __init__(self, papelera: Papelera, unidad: str = "") -> None:
		super().__init__()
		self.papelera = papelera
		self.unidad = unidad.rstrip("\\/").upper()
		# escribir = True para que Supr elimine definitivamente (sin papelera: ya se está en ella).
		self.capacidades = api.Capacidades(escribir=True, papelera=False)
		self._elementos: dict[str, Elemento] = {}

	def descripcion(self) -> str:
		return _("Papelera de reciclaje")

	def _raiz_texto(self) -> str:
		return _("Papelera de {u}").format(u=self.unidad) if self.unidad else _("Papelera de reciclaje")

	def elemento(self, ruta: str) -> Elemento | None:
		"""El elemento de la papelera de una ruta de la raíz (su ``$R``)."""
		return self._elementos.get(os.path.normcase(ruta))

	def _es_elemento(self, ruta: str) -> bool:
		return os.path.normcase(ruta) in self._elementos

	@staticmethod
	def _entrada(elemento: Elemento) -> api.Entrada:
		es_carpeta = os.path.isdir(elemento.ruta_r)
		return api.Entrada(elemento.nombre, elemento.ruta_r, es_carpeta=es_carpeta, tamano=elemento.tamano,
			modificado=elemento.eliminado, ruta_real=elemento.carpeta_original)

	def listar(self, ruta: str, cancelacion=None) -> list[api.Entrada]:
		if not ruta:
			elementos = self.papelera.elementos(self.unidad, cancelacion)
			self._elementos = {os.path.normcase(e.ruta_r): e for e in elementos}
			return [self._entrada(e) for e in elementos]
		try:
			resultado = []
			with os.scandir(ruta) as hijos:
				for hijo in hijos:
					api.comprobar(cancelacion)
					datos = hijo.stat(follow_symlinks=False)
					resultado.append(api.Entrada(hijo.name, hijo.path, es_carpeta=hijo.is_dir(follow_symlinks=False),
						tamano=datos.st_size if not hijo.is_dir(follow_symlinks=False) else -1, modificado=datos.st_mtime,
						atributos=getattr(datos, "st_file_attributes", 0), es_enlace=hijo.is_symlink() or hijo.is_junction()))
			return resultado
		except FileNotFoundError as error:
			raise api.NoEncontrado(_("Ya no está en la papelera: {r}").format(r=ruta), ruta) from error
		except OSError as error:
			raise api.ErrorAcceso(_("No se puede leer {r}: {e}").format(r=ruta, e=error.strerror or error), ruta) from error

	def info(self, ruta: str) -> api.Entrada:
		if not ruta:
			return api.Entrada(self._raiz_texto(), "", es_carpeta=True)
		elemento = self.elemento(ruta)
		if elemento is not None:
			return self._entrada(elemento)
		try:
			datos = os.stat(ruta)
		except OSError as error:
			raise api.NoEncontrado(_("Ya no está en la papelera: {r}").format(r=ruta), ruta) from error
		return api.Entrada(os.path.basename(ruta), ruta, es_carpeta=os.path.isdir(ruta), tamano=datos.st_size, modificado=datos.st_mtime)

	def padre(self, ruta: str) -> str | None:
		if not ruta:
			return None
		if self._es_elemento(ruta):
			return ""
		return os.path.dirname(ruta)

	def unir(self, carpeta: str, nombre: str) -> str:
		return os.path.join(carpeta, nombre) if carpeta else nombre

	def raiz(self, ruta: str) -> str:
		return ""

	def mostrar(self, ruta: str) -> str:
		if not ruta:
			return self._raiz_texto()
		elemento = self.elemento(ruta)
		if elemento is not None:
			return _("{p}\\{n}").format(p=self._raiz_texto(), n=elemento.nombre)
		# Dentro de una carpeta eliminada: «Papelera\Fotos\2024».
		for clave, padre in self._elementos.items():
			if os.path.normcase(ruta).startswith(clave + os.sep):
				return _("{p}\\{n}{r}").format(p=self._raiz_texto(), n=padre.nombre, r=ruta[len(padre.ruta_r):])
		return ruta

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		try:
			return open(ruta, "rb")
		except OSError as error:
			raise api.ErrorAcceso(_("No se puede leer {r}: {e}").format(r=ruta, e=error.strerror or error), ruta) from error

	def ruta_local(self, ruta: str) -> str | None:
		return ruta or None

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		"""Eliminar en la papelera es definitivo: el ``$R`` y su ``$I``."""
		elemento = self.elemento(ruta)
		if elemento is None:
			# Lo de dentro de una carpeta eliminada: el motor lo borra de dentro afuera antes que la carpeta.
			if not any(os.path.normcase(ruta).startswith(c + os.sep) for c in self._elementos):
				raise api.SoloLectura(_("Esto no está en la papelera"), ruta)
			try:
				if os.path.isdir(ruta) and not os.path.islink(ruta) and recursivo:
					shutil.rmtree(ruta)
				elif os.path.isdir(ruta) and not os.path.islink(ruta):
					os.rmdir(ruta)
				else:
					os.remove(ruta)
			except OSError as error:
				raise api.ErrorAcceso(_("No se pudo eliminar {r}: {e}").format(r=ruta, e=error.strerror or error), ruta) from error
			return
		try:
			eliminar_definitivo(elemento)
		except OSError as error:
			raise api.ErrorAcceso(_("No se pudo eliminar {n}: {e}").format(n=elemento.nombre, e=error.strerror or error), ruta) from error
		self._elementos.pop(os.path.normcase(ruta), None)


def separar_direccion(direccion: str) -> str:
	"""``papelera://`` → «»; ``papelera://D:/`` → «D:»."""
	resto = direccion.split("://", 1)[1] if "://" in direccion else direccion
	resto = resto.strip("/\\")
	return resto[:2].upper() if len(resto) >= 2 and resto[1] == ":" else ""


# ── Operaciones del motor ────────────────────────────────────────────────────


class OperacionRestaurar(api.Operacion):
	"""Devuelve los elementos a su sitio. Si el sitio está ocupado, pregunta (Restaurar con otro nombre, Omitir, Cancelar)."""

	tipo = "restaurar"

	def __init__(self, elementos: Sequence[Elemento]) -> None:
		super().__init__()
		self.elementos = list(elementos)
		self.restaurados: list[str] = []
		self._siempre: int | None = None

	def descripcion(self) -> str:
		que = self.elementos[0].nombre if len(self.elementos) == 1 else api.formato.plural(len(self.elementos), _("{n} elemento"), _("{n} elementos"))
		return _("Restaurar {q} desde la papelera").format(q=que)

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset("local:" + e.unidad.casefold() + "\\" for e in self.elementos)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [(ESQUEMA, "")] + sorted({("local", e.carpeta_original) for e in self.elementos})

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.elementos), bytes_total=sum(max(0, e.tamano) for e in self.elementos))
		carpetas: set[str] = set()
		for elemento in self.elementos:
			ctx.comprobar()
			self.progresar(actual=elemento.nombre)
			destino = elemento.original
			if os.path.lexists(destino):
				eleccion = self._siempre
				if eleccion is None:
					with ctx.esperando():
						eleccion = ctx.decisor.elegir(_("Ya existe"), _("Ya hay un «{n}» en {c}. ¿Qué hace?").format(
							n=elemento.nombre, c=elemento.carpeta_original),
							[_("Restaurar con &otro nombre"), _("Otro nombre para &todos"), _("&Omitir"), _("&Cancelar")],
							predeterminada=0, escape=3, operacion=self)
					if eleccion == 1:
						self._siempre = eleccion = 0
				if eleccion == 3:
					raise api.Cancelado()
				if eleccion == 2:
					self.sumar(omitidos=1)
					continue
				destino = nombre_libre(destino)
			try:
				self.restaurados.append(restaurar(elemento, destino))
				carpetas.add(os.path.dirname(elemento.ruta_r))
				self.sumar(archivos_hechos=1, bytes_hechos=max(0, elemento.tamano))
			except (OSError, api.ErrorArchivos) as error:
				self.anotar_error(elemento.original, getattr(error, "mensaje", None) or str(error))
		for carpeta in carpetas:
			avisar_shell(carpeta)


class OperacionVaciar(api.Operacion):
	"""Vacía la papelera (de una unidad o de todas)."""

	tipo = "vaciar_papelera"
	admite_pausa = False

	def __init__(self, unidades: Sequence[str], vaciar: Callable[[str], None] = vaciar_con_shell) -> None:
		super().__init__()
		self.unidades = list(unidades)
		self._vaciar = vaciar

	def descripcion(self) -> str:
		if len(self.unidades) == 1 and self.unidades[0]:
			return _("Vaciar la papelera de {u}").format(u=self.unidades[0])
		return _("Vaciar la papelera")

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [(ESQUEMA, "")]

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.unidades))
		for unidad in self.unidades:
			ctx.comprobar()
			self.progresar(actual=unidad or _("todas las unidades"))
			try:
				self._vaciar(unidad)
			except api.ErrorArchivos as error:
				self.anotar_error(unidad, error.mensaje)
			self.sumar(archivos_hechos=1)
