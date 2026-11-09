# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sistema de archivos virtual: la entrada, el proveedor y los errores comunes.

Un panel no sabe si muestra el disco, un ZIP, un servidor FTP o una lista de
resultados: solo habla con un ``Proveedor`` y recibe ``Entrada``. Así el
motor de copia, la búsqueda o el visor funcionan igual sobre cualquier origen.

Rutas: cada proveedor usa su propio formato de ruta (en local, rutas de
Windows; en ZIP, rutas internas con «/»; en FTP, rutas remotas). Fuera del
proveedor solo se tratan como texto opaco y se combinan con sus métodos
``unir``, ``padre`` y ``raiz``.
"""

from __future__ import annotations

import builtins
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import BinaryIO

from app.core.tareas import TareaCancelada
from app.services import formato


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Errores ──────────────────────────────────────────────────────────────────


class ErrorArchivos(Exception):
	"""Error de archivos con un mensaje en español para la persona usuaria.

	:param mensaje: frase completa y útil («El archivo está abierto en otro programa»).
	:param ruta: ruta afectada (para el registro y los detalles).
	"""

	def __init__(self, mensaje: str, ruta: str = "") -> None:
		super().__init__(mensaje)
		self.mensaje = mensaje
		self.ruta = ruta


class ErrorAcceso(ErrorArchivos):
	"""Sin permiso, archivo en uso o bloqueado."""


class NoEncontrado(ErrorArchivos):
	"""La ruta no existe."""


class YaExiste(ErrorArchivos):
	"""El destino ya existe."""


class SoloLectura(ErrorArchivos):
	"""El proveedor o el archivo no admiten escritura."""


class ErrorRed(ErrorArchivos):
	"""Fallo de conexión, tiempo agotado o servidor que no responde."""


class NombreNoValido(ErrorArchivos):
	"""Nombre con caracteres prohibidos o reservado en Windows."""


class SinEspacio(ErrorArchivos):
	"""No queda espacio en el destino."""


class Cancelado(ErrorArchivos, TareaCancelada):
	"""La persona canceló la operación.

	Hereda también de ``TareaCancelada`` para que ``GestorTareas`` la trate como
	cancelación (no como fallo con traza) aunque se lance con otro token.
	"""

	def __init__(self, mensaje: str = "", ruta: str = "") -> None:
		super().__init__(mensaje or _("Operación cancelada"), ruta)


class NoAdmitido(ErrorArchivos):
	"""La operación no tiene sentido en este proveedor (crear enlaces en un ZIP...)."""


# ── Entrada ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Entrada:
	"""Un elemento de una carpeta (archivo, carpeta o la fila «..»).

	:param nombre: nombre visible, con extensión.
	:param ruta: ruta completa dentro de su proveedor.
	:param es_carpeta: carpeta (o algo en lo que se puede entrar como tal).
	:param tamano: bytes; −1 si se desconoce (carpetas sin calcular).
	:param modificado: fecha de modificación (marca de tiempo); 0 si se desconoce.
	:param creado: fecha de creación; 0 si se desconoce.
	:param atributos: bits de Windows (ver ``formato``).
	:param es_enlace: enlace simbólico o unión (NO los puntos de análisis de OneDrive).
	:param destino_enlace: a dónde apunta el enlace, si se sabe.
	:param es_superior: la fila «..» que lleva a la carpeta superior.
	:param ruta_real: en listas de resultados, la carpeta real que lo contiene (columna Ruta).
	"""

	nombre: str
	ruta: str
	es_carpeta: bool = False
	tamano: int = -1
	modificado: float = 0.0
	creado: float = 0.0
	atributos: int = 0
	es_enlace: bool = False
	destino_enlace: str = ""
	es_superior: bool = False
	ruta_real: str = ""
	#: Permisos Unix (SFTP) en octal, o −1 si no aplica.
	permisos: int = -1
	#: Archivo de OneDrive u otro proveedor de nube que no está descargado.
	en_nube: bool = False

	@property
	def extension(self) -> str:
		"""Extensión sin punto y en minúsculas. Vacía en carpetas y en «.gitignore»."""
		if self.es_carpeta or self.es_superior:
			return ""
		punto = self.nombre.rfind(".")
		if punto <= 0:
			return ""
		return self.nombre[punto + 1 :].lower()

	@property
	def nombre_sin_extension(self) -> str:
		ext = self.extension
		return self.nombre[: -(len(ext) + 1)] if ext else self.nombre

	@property
	def oculto(self) -> bool:
		return bool(self.atributos & formato.OCULTO)

	@property
	def sistema(self) -> bool:
		return bool(self.atributos & formato.SISTEMA)

	@property
	def solo_lectura(self) -> bool:
		return bool(self.atributos & formato.SOLO_LECTURA)

	def con(self, **cambios) -> Entrada:
		"""Copia con campos cambiados (por ejemplo, el tamaño calculado de una carpeta)."""
		return replace(self, **cambios)


def entrada_superior(ruta_padre: str) -> Entrada:
	"""La fila «..» que lleva a ``ruta_padre``."""
	return Entrada(nombre="..", ruta=ruta_padre, es_carpeta=True, es_superior=True)


# ── Cancelación ──────────────────────────────────────────────────────────────


class Cancelacion:
	"""Interfaz mínima de cancelación que usan los proveedores.

	Acepta un ``TokenCancelacion`` de ``app.core.tareas`` o un ``threading.Event``:
	los dos tienen ``is_set()``.
	"""

	def __init__(self, evento: threading.Event | None = None) -> None:
		self._evento = evento or threading.Event()

	def is_set(self) -> bool:
		return self._evento.is_set()

	def cancelar(self) -> None:
		self._evento.set()


def comprobar(cancelacion) -> None:
	"""Lanza ``Cancelado`` si se pidió cancelar. ``cancelacion`` puede ser ``None`` o una ``Tarea`` (usa su ``token``)."""
	cancelacion = getattr(cancelacion, "token", cancelacion)
	if cancelacion is not None and cancelacion.is_set():
		raise Cancelado()


# ── Proveedor ────────────────────────────────────────────────────────────────


@dataclass
class Capacidades:
	"""Qué admite un proveedor (la interfaz desactiva lo que no)."""

	escribir: bool = True
	papelera: bool = False
	atributos: bool = False
	enlaces: bool = False
	vigilar: bool = False
	permisos: bool = False
	# 2.0 (diseño 2.0, 14.5): ganchos para nubes y NAS; los valores por defecto
	# mantienen el comportamiento de la 1.x.
	#: Renombrar es barato: el motor puede escribir en un temporal y renombrar al final.
	renombrar_barato: bool = True
	#: La subida solo aparece completa al terminar: el motor escribe directamente con el nombre final.
	escritura_atomica: bool = False
	#: El proveedor puede copiar dentro de sí mismo sin pasar los bytes por zCommander.
	copia_servidor: bool = False
	#: Puede haber dos entradas con el mismo nombre en una carpeta.
	nombres_duplicados: bool = False


@dataclass(frozen=True)
class UnidadVirtual:
	"""Entrada del selector de unidades que no es una letra (nubes, NAS, Red, Papelera; 14.5).

	:param texto: «Google Drive de Ana».
	:param direccion: «nube://ana_drive/».
	:param descripcion: «15 GB libres de 100 GB».
	"""

	texto: str
	direccion: str
	descripcion: str = ""


@dataclass(frozen=True)
class ResultadoPar:
	"""Resultado de un par origen → destino de ``Proveedor.transferir_lote`` (14.5)."""

	origen: str
	destino: str
	ok: bool
	error: ErrorArchivos | None = None


class Proveedor(ABC):
	"""Origen de archivos (disco, comprimido, servidor, lista de resultados)."""

	#: «local», «zip», «tar», «7z», «ftp», «sftp», «resultados».
	esquema: str = ""
	#: 2.0 (API 1.1): orden con el que el panel muestra este proveedor si la persona no ha elegido
	#: otro estando en él: ``(criterio, inverso)`` con un criterio de ``app.services.ordenacion``
	#: («tamano», «fecha»...). ``None``: el orden del panel, como siempre.
	orden_preferido: tuple[str, bool] | None = None

	def __init__(self) -> None:
		self.capacidades = Capacidades()
		#: Para comprimidos: (proveedor, ruta) del archivo que lo contiene.
		self.contenedor: tuple[Proveedor, str] | None = None
		self._al_cerrar: list[Callable[[], None]] = []

	# Navegación -------------------------------------------------------------

	@abstractmethod
	def listar(self, ruta: str, cancelacion=None) -> list[Entrada]:
		"""Entradas de la carpeta ``ruta`` (sin la fila «..»).

		Lanza ``NoEncontrado``, ``ErrorAcceso``, ``ErrorRed`` o ``Cancelado``.
		"""

	@abstractmethod
	def info(self, ruta: str) -> Entrada:
		"""Entrada de una ruta concreta. Lanza ``NoEncontrado`` si no existe."""

	def existe(self, ruta: str) -> bool:
		try:
			self.info(ruta)
		except NoEncontrado:
			return False
		return True

	@abstractmethod
	def padre(self, ruta: str) -> str | None:
		"""Carpeta superior; ``None`` en la raíz del proveedor."""

	@abstractmethod
	def unir(self, carpeta: str, nombre: str) -> str:
		"""Ruta de ``nombre`` dentro de ``carpeta``."""

	@abstractmethod
	def raiz(self, ruta: str) -> str:
		"""Raíz que contiene ``ruta`` (la unidad en local, «/» en un servidor)."""

	def nombre(self, ruta: str) -> str:
		"""Último componente de la ruta."""
		padre = self.padre(ruta)
		if padre is None:
			return ruta
		resto = ruta[len(padre):] if ruta.startswith(padre) else ruta
		return resto.strip("/\\") or ruta

	@abstractmethod
	def mostrar(self, ruta: str) -> str:
		"""Texto para la etiqueta del panel y los anuncios (``C:\\datos\\a.zip\\docs``)."""

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		"""``True`` si mover entre las dos rutas puede ser un simple renombrado.

		El motor solo lo pregunta si origen y destino tienen la misma identidad de
		volumen (``modelo.clave_carril``): las rutas de nube, FTP y SFTP son relativas
		y el proveedor de origen no sabe nada del de destino (14.5).
		"""
		return False

	# Ganchos de la 2.0 (14.5): opcionales; la base mantiene la copia de la 1.x.

	def transferir(self, origen: Proveedor, ruta_origen: str, ruta_destino: str,
			progreso: Callable[[int, int], None], cancelacion) -> bool:
		"""Copia ``ruta_origen`` de ``origen`` a ``ruta_destino`` de este proveedor por su cuenta.

		``True`` si la hizo (copia en el servidor, subida por fragmentos) e informó del
		progreso; ``False`` (por defecto) para que el motor copie por bloques.
		"""
		return False

	def transferir_lote(self, origen: Proveedor, pares: Sequence[tuple[str, str]], mover: bool,
			progreso: Callable[[int, int], None], cancelacion) -> list[ResultadoPar] | None:
		"""Copia (o mueve) de una vez una lista de pares ya decidida por el análisis del motor.

		``None`` (por defecto) = no lo admite y el motor sigue archivo a archivo; si no,
		un ``ResultadoPar`` por par.
		"""
		return None

	def suma(self, ruta: str, algoritmo: str) -> str | None:
		"""Suma que el origen ya conoce (rclone, File Station); ``None`` si hay que leer el archivo."""
		return None

	# Contenido --------------------------------------------------------------

	@abstractmethod
	def abrir_lectura(self, ruta: str) -> BinaryIO:
		"""Flujo binario de lectura."""

	def abrir_escritura(self, ruta: str, tamano: int = -1) -> BinaryIO:
		"""Flujo binario de escritura (crea o sustituye).

		:param tamano: tamaño previsto en bytes (−1 si no se sabe); lo necesitan los
			proveedores que suben en flujo (rclone, File Station).
		"""
		raise SoloLectura(_("No se puede escribir aquí"), ruta)

	def crear_carpeta(self, ruta: str) -> None:
		raise SoloLectura(_("No se pueden crear carpetas aquí"), ruta)

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		raise SoloLectura(_("No se puede eliminar aquí"), ruta)

	def renombrar(self, origen: str, destino: str) -> None:
		raise SoloLectura(_("No se puede renombrar aquí"), origen)

	def fijar_tiempos(self, ruta: str, modificado: float, creado: float = 0.0) -> None:  # noqa: B027 - opcional
		"""Cambia las fechas; los proveedores que no puedan, no hacen nada."""

	def fijar_atributos(self, ruta: str, atributos: int) -> None:
		raise NoAdmitido(_("Este origen no admite atributos"), ruta)

	def fijar_permisos(self, ruta: str, modo: int) -> None:
		"""Permisos Unix (SFTP). Los demás proveedores no los admiten."""
		raise NoAdmitido(_("Este origen no admite permisos"), ruta)

	def espacio_libre(self, ruta: str) -> tuple[int, int] | None:
		"""(libre, total) en bytes, o ``None`` si no se sabe."""
		return None

	def ruta_local(self, ruta: str) -> str | None:
		"""Ruta en el disco si existe (permite usar el shell y las API nativas)."""
		return None

	def extraer_temporal(self, ruta: str) -> str:
		"""Copia el archivo a ``data/temp`` y devuelve su ruta local.

		La copia se borra al cerrar el proveedor.
		"""
		local = self.ruta_local(ruta)
		if local:
			return local
		from app.services.vfs import temporales

		destino = temporales.ruta_temporal(self.nombre(ruta))
		with self.abrir_lectura(ruta) as origen, open(destino, "wb") as salida:
			while bloque := origen.read(1024 * 1024):
				salida.write(bloque)
		self._al_cerrar.append(lambda: temporales.borrar(destino))
		return destino

	def transaccion(self):
		"""Contexto que agrupa escrituras: ``with proveedor.transaccion(): ...``.

		Lo abren las operaciones del núcleo (copiar, mover, eliminar, crear) en
		todo su ``ejecutar``. En local no hace nada. En un ZIP acumula los
		cambios; mientras tanto ``info``, ``existe`` y ``listar`` muestran los
		cambios pendientes; al salir sin error reconstruye el comprimido UNA vez;
		si se sale por error o cancelación, descarta lo pendiente y no escribe
		nada. Se puede anidar (solo cuenta la más externa).
		"""
		from contextlib import nullcontext

		return nullcontext(self)

	# Ciclo de vida -----------------------------------------------------------

	def clonar(self) -> Proveedor:
		"""Proveedor equivalente e independiente (otra conexión) para transferencias en otro hilo.

		Los proveedores sin estado compartido se devuelven a sí mismos.
		"""
		return self

	def cerrar(self) -> None:
		"""Libera conexiones y temporales. Se puede llamar varias veces."""
		while self._al_cerrar:
			funcion = self._al_cerrar.pop()
			try:
				funcion()
			except Exception:  # noqa: BLE001 - cerrar nunca debe fallar
				import logging

				logging.getLogger(__name__).debug("Fallo al liberar un recurso del proveedor", exc_info=True)

	def descripcion(self) -> str:
		"""Nombre del origen para la persona («Disco local», «Archivo ZIP», «Servidor FTP»)."""
		return self.esquema


@dataclass
class Ubicacion:
	"""Dónde está un panel: proveedor y ruta."""

	proveedor: Proveedor
	ruta: str
	extra: dict = field(default_factory=dict)

	def mostrar(self) -> str:
		return self.proveedor.mostrar(self.ruta)
