# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Registro de complementos: marcadores y funciones (diseño 2.0, 3.4, 3.5 y 3.13). Sin wx.

No confundir con ``app/core/registro.py`` (el registro de la aplicación).

- **Marcadores**: lo que un manifiesto declara (órdenes, sonidos, columnas,
  unidades, acciones de error...). Existen ANTES de cargar el código: con ellos
  se construyen el catálogo de órdenes, los menús y las teclas.
- **Funciones**: lo que el complemento pone en ``activar(zc)`` sobre su
  ``Anfitrion`` (manejadores, extractores de columna, visores...).

El registro de marcadores solo cambia en el hilo principal (antes de que
exista la ventana) o en el de la interfaz; quien recorre el catálogo desde un
hilo usa la instantánea de ``ordenes.catalogo()``. Cada cambio sube un contador
de versión y avisa a los suscritos (``ordenes`` se suscribe y emite
``al_cambiar_catalogo``): este módulo no puede importar ``app.ui``.
"""

from __future__ import annotations

import builtins
import fnmatch
import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.plugins import config_plugins, manifiesto
from app.plugins.estado import EstadoComplemento, Pendiente
from app.services.sonidos import catalogo as catalogo_sonidos

log = logging.getLogger(__name__)

TIEMPO_COLUMNA_S = 5.0
TIEMPO_INFO_S = 1.0
AGOTAMIENTOS_POR_CARPETA = 3
HILOS_ABANDONADOS_MAXIMOS = 4
SIN_DATOS = "Sin datos"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Tipos de contrato ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ColumnaExterna:
	"""Columna de un complemento (``id`` = ``<id del complemento>:<columna>``)."""

	id: str
	titulo: str
	tipo: str
	lenta: bool
	complemento: str


@dataclass(frozen=True)
class AccionAplicable:
	"""Botón extra de la pregunta de error (14.6).

	:param activo: falso si el complemento aún no está activado: al pulsarlo hay que
		activarlo primero (``complemento``) y después llamar a ``funcion``.
	"""

	id: str
	etiqueta: str
	funcion: Callable[[Any], Any]
	complemento: str = ""
	activo: bool = True


@dataclass(frozen=True)
class ObjetivoCongelado:
	"""Instantánea inmutable de un panel tomada al pulsar la tecla de una orden (3.4)."""

	lado: str
	proveedor: Any
	ruta: str
	cursor: Any
	marcadas: tuple = ()
	elementos_trabajo: tuple = ()


@dataclass
class Registrado:
	"""Un complemento descubierto y su estado en esta sesión."""

	manifiesto: manifiesto.Manifiesto
	carpeta: Path
	origen: str = "serie"  # serie, usuario, desarrollo
	estado: EstadoComplemento = EstadoComplemento.REGISTRADO
	pendiente: Pendiente = Pendiente.NINGUNO
	confianza: str = ""
	motivo: str = ""
	#: Sumas que se comprueban al activar (ruta relativa → SHA-256); ``None`` = no se comprueban.
	sumas: dict[str, str] | None = None
	#: Suma del paquete aceptada (complementos sin firma de ``complementos.confiados``).
	suma_aceptada: str = ""
	reintentable: bool = True
	tiempo_carga: float = 0.0

	@property
	def id(self) -> str:
		return self.manifiesto.id

	@property
	def nombre(self) -> str:
		return self.manifiesto.nombre


@dataclass(frozen=True)
class OrdenComplemento:
	"""Una orden de complemento tal como entra en el catálogo (14.1.1)."""

	id: str  # id completo «zc.reproductor:reproducir»
	etiqueta: str
	ayuda: str
	teclas: tuple[str, ...]
	ambito: str
	menu: str
	tipo: str
	casilla_defecto: bool
	disponible_si: str
	nivel: str
	paleta: bool
	tecla_global: bool
	argumento: str
	bloque: str
	complemento: str
	nombre_complemento: str


# ── Estado del registro ──────────────────────────────────────────────────────


class _Registro:
	def __init__(self) -> None:
		self.candado = threading.RLock()
		self.complementos: dict[str, Registrado] = {}
		self.errores: list[tuple[Path, list[str]]] = []
		self.version = 0
		self.suscritos: list[Callable[[], None]] = []
		self.funciones: dict[str, dict[str, Any]] = {}  # tipo → clave → función
		self.exportados: dict[str, dict[str, Any]] = {}
		self.cache_columnas: dict[tuple, str] = {}
		self.columnas_pendientes: set[tuple] = set()
		self.agotamientos: dict[tuple[str, str], int] = {}
		self.abandonados: dict[str, int] = {}
		self.sin_columnas: set[str] = set()
		self.grupos: dict[str, ThreadPoolExecutor] = {}
		#: Funciones suscritas por cada complemento a cada evento (para entregarle el que lo activó).
		self.suscripciones: dict[tuple[str, str], list[Callable[..., None]]] = {}
		self.lote = 0
		self.cambio_en_lote = False


_r = _Registro()

_TIPOS_FUNCION = ("manejador", "estado", "disponible", "interna", "columna", "visor", "ventana", "info", "busqueda",
	"extractor", "mascara", "accion_error", "unidades")


def _funciones(tipo: str) -> dict[str, Any]:
	return _r.funciones.setdefault(tipo, {})


def suscribir_cambios(funcion: Callable[[], None]) -> None:
	"""Aviso de cada cambio del registro de marcadores (lo usa ``app.ui.ordenes``)."""
	with _r.candado:
		if funcion not in _r.suscritos:
			_r.suscritos.append(funcion)


def version() -> int:
	return _r.version


def _cambio() -> None:
	with _r.candado:
		_r.version += 1
		if _r.lote:
			_r.cambio_en_lote = True
			return
		suscritos = list(_r.suscritos)
	for funcion in suscritos:
		try:
			funcion()
		except Exception:  # noqa: BLE001 - un suscriptor roto no impide registrar
			log.exception("Falló un aviso de cambio del registro de complementos")


class lote:  # noqa: N801 - se usa como «with registro.lote():»
	"""Agrupa varios registros en un solo aviso de cambio (al descubrir todos los complementos)."""

	def __enter__(self) -> lote:
		with _r.candado:
			_r.lote += 1
		return self

	def __exit__(self, *_exc: object) -> None:
		with _r.candado:
			_r.lote -= 1
			avisar = _r.lote == 0 and _r.cambio_en_lote
			if avisar:
				_r.cambio_en_lote = False
		if avisar:
			_r.version -= 1
			_cambio()


# ── Registrar y consultar complementos ───────────────────────────────────────


def registrar(datos: manifiesto.Manifiesto, carpeta: Path, origen: str = "serie",
		estado: EstadoComplemento = EstadoComplemento.REGISTRADO, motivo: str = "", confianza: str = "") -> Registrado:
	"""Registra los marcadores de un manifiesto válido (sin importar su código)."""
	from app.plugins import estado as modulo_estado

	registrado = Registrado(datos, Path(carpeta), origen, estado, confianza=confianza, motivo=motivo)
	with _r.candado:
		anterior = _r.complementos.get(datos.id)
		if anterior is not None:
			log.info("El complemento %s se registra de nuevo (%s sustituye a %s)", datos.id, carpeta, anterior.carpeta)
		_r.complementos[datos.id] = registrado
	catalogo_sonidos.registrar_complemento(datos.id, datos.nombre, list(datos.sonidos))
	config_plugins.registro().declarar(datos.id, datos.tabla("configuracion"))
	modulo_estado.fijar_datos(datos.id, datos.nombre, datos.version)
	_cambio()
	return registrado


def anotar_error(carpeta: Path, problemas: list[str]) -> None:
	"""Un manifiesto que no se pudo registrar (``ERROR_MANIFIESTO``) para el gestor y el registro."""
	with _r.candado:
		_r.errores.append((Path(carpeta), list(problemas)))
	log.warning("Manifiesto con errores en %s: %s", carpeta, "; ".join(problemas))


def errores() -> list[tuple[Path, list[str]]]:
	with _r.candado:
		return list(_r.errores)


def quitar(id_complemento: str) -> None:
	with _r.candado:
		_r.complementos.pop(id_complemento, None)
		for tabla in _r.funciones.values():
			for clave in [c for c in tabla if c == id_complemento or c.startswith(id_complemento + ":")]:
				tabla.pop(clave, None)
		_r.exportados.pop(id_complemento, None)
		for clave in [c for c in _r.suscripciones if c[0] == id_complemento]:
			_r.suscripciones.pop(clave, None)
	catalogo_sonidos.quitar_complemento(id_complemento)
	config_plugins.registro().quitar(id_complemento)
	_cambio()


def vaciar() -> None:
	"""Deja el registro vacío (solo pruebas)."""
	with _r.candado:
		_r.complementos.clear()
		_r.errores.clear()
		_r.funciones.clear()
		_r.exportados.clear()
		_r.cache_columnas.clear()
		_r.columnas_pendientes.clear()
		_r.agotamientos.clear()
		_r.abandonados.clear()
		_r.sin_columnas.clear()
		_r.suscripciones.clear()
		grupos, _r.grupos = list(_r.grupos.values()), {}
	for grupo in grupos:
		grupo.shutdown(wait=False, cancel_futures=True)
	catalogo_sonidos.vaciar_complementos()
	config_plugins.registro().vaciar()
	_cambio()


def complemento(id_complemento: str) -> Registrado | None:
	with _r.candado:
		return _r.complementos.get(id_complemento)


def complementos() -> list[Registrado]:
	"""Los registrados, por nombre visible."""
	with _r.candado:
		return sorted(_r.complementos.values(), key=lambda r: (r.nombre.casefold(), r.id))


def estado(id_complemento: str) -> EstadoComplemento | None:
	registrado = complemento(id_complemento)
	return registrado.estado if registrado else None


def fijar_estado(id_complemento: str, nuevo: EstadoComplemento, motivo: str = "") -> None:
	"""Cambia el estado (lo usa el cargador en el hilo de la interfaz)."""
	with _r.candado:
		registrado = _r.complementos.get(id_complemento)
		if registrado is None:
			return
		registrado.estado = nuevo
		if motivo:
			registrado.motivo = motivo


def registrar_serie(carpeta: Path | None = None) -> None:
	"""Registra los marcadores de los complementos de serie sin importar código ni leer la configuración.

	La usan las herramientas (anexos, menús, teclas, provisionales) y la fixture
	``complementos_serie`` de las pruebas. Dos carpetas con el mismo id son un
	error de manifiesto para las dos.
	"""
	if carpeta is None:
		from app.core import paths

		carpeta = paths.ruta_plugins_serie()
	encontrados = descubrir_carpeta(Path(carpeta))
	with lote():
		for ruta, datos in encontrados:
			if isinstance(datos, manifiesto.Manifiesto):
				registrar(datos, ruta, "serie", confianza="Oficial")
			else:
				anotar_error(ruta, datos)


def descubrir_carpeta(carpeta: Path) -> list[tuple[Path, manifiesto.Manifiesto | list[str]]]:
	"""Lee los manifiestos de las subcarpetas de ``carpeta``: (carpeta, manifiesto o problemas)."""
	if not carpeta.is_dir():
		return []
	leidos: list[tuple[Path, manifiesto.Manifiesto | list[str]]] = []
	for sub in sorted(p for p in carpeta.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
		if not (sub / manifiesto.NOMBRE).is_file():
			continue
		try:
			leidos.append((sub, manifiesto.leer(sub)))
		except manifiesto.ErrorManifiesto as error:
			leidos.append((sub, error.problemas))
	cuenta: dict[str, int] = {}
	for _ruta, datos in leidos:
		if isinstance(datos, manifiesto.Manifiesto):
			cuenta[datos.id] = cuenta.get(datos.id, 0) + 1
	resultado: list[tuple[Path, manifiesto.Manifiesto | list[str]]] = []
	for ruta, datos in leidos:
		if isinstance(datos, manifiesto.Manifiesto) and cuenta[datos.id] > 1:
			resultado.append((ruta, [_("El id {i} está repetido en dos carpetas").format(i=datos.id)]))
		else:
			resultado.append((ruta, datos))
	return resultado


# ── Órdenes ──────────────────────────────────────────────────────────────────


def ordenes() -> list[OrdenComplemento]:
	"""Órdenes de todos los complementos registrados (los de error de manifiesto no tienen)."""
	resultado = []
	for registrado in complementos():
		datos = registrado.manifiesto
		bloque = datos.bloque if registrado.origen == "serie" and datos.bloque else "COMPLEMENTO"
		for orden in datos.ordenes:
			resultado.append(OrdenComplemento(
				id=f"{datos.id}:{orden.id}", etiqueta=orden.etiqueta, ayuda=orden.ayuda, teclas=orden.teclas,
				ambito=orden.ambito, menu=orden.menu, tipo=orden.tipo, casilla_defecto=orden.casilla_defecto,
				disponible_si=orden.disponible_si, nivel=orden.nivel or datos.nivel, paleta=orden.paleta,
				tecla_global=orden.tecla_global, argumento=orden.argumento, bloque=bloque, complemento=datos.id,
				nombre_complemento=datos.nombre,
			))
	return resultado


def orden(id_completo: str) -> OrdenComplemento | None:
	return next((o for o in ordenes() if o.id == id_completo), None)


def argumento_orden(id_completo: str) -> str:
	encontrada = orden(id_completo)
	return encontrada.argumento if encontrada else ""


def separar_orden(id_completo: str) -> tuple[str, str]:
	"""«zc.reproductor:reproducir» → (``zc.reproductor``, ``reproducir``)."""
	id_complemento, _dos, corto = id_completo.partition(":")
	return id_complemento, corto


# ── Funciones que pone el complemento al activarse ───────────────────────────


def fijar_funcion(tipo: str, clave: str, funcion: Any) -> None:
	if tipo not in _TIPOS_FUNCION:
		raise ValueError(f"Tipo de función desconocido: {tipo}")
	with _r.candado:
		_funciones(tipo)[clave] = funcion


def funcion(tipo: str, clave: str) -> Any:
	with _r.candado:
		return _r.funciones.get(tipo, {}).get(clave)


def funciones(tipo: str) -> dict[str, Any]:
	with _r.candado:
		return dict(_r.funciones.get(tipo, {}))


def manejador(id_completo: str) -> Callable | None:
	return funcion("manejador", id_completo)


def exportar(id_complemento: str, nombre: str, objeto: Any) -> None:
	with _r.candado:
		_r.exportados.setdefault(id_complemento, {})[nombre] = objeto


def exportados(id_complemento: str) -> dict[str, Any] | None:
	with _r.candado:
		datos = _r.exportados.get(id_complemento)
		return dict(datos) if datos is not None else None


def registrar_mascara(id_complemento: str, marcador: str, funcion_mascara: Callable) -> bool:
	"""Registra una máscara de renombrado; gana la que ya estaba (3.3). Falso si choca."""
	if marcador in manifiesto.MASCARAS_NUCLEO:
		log.warning("La máscara %s de %s choca con una de zCommander", marcador, id_complemento)
		return False
	with _r.candado:
		actual = _funciones("mascara").get(marcador)
		if actual is not None and actual[0] != id_complemento:
			log.warning("La máscara %s de %s ya la registró %s", marcador, id_complemento, actual[0])
			return False
		_funciones("mascara")[marcador] = (id_complemento, funcion_mascara)
	return True


# ── Unidades, columnas, información y acciones de error ──────────────────────


def _usable(registrado: Registrado) -> bool:
	return registrado.estado not in (EstadoComplemento.INHABILITADO, EstadoComplemento.INCOMPATIBLE,
		EstadoComplemento.ERROR_MANIFIESTO, EstadoComplemento.SIN_ACEPTAR)


def usable(id_complemento: str) -> bool:
	"""El complemento está registrado, habilitado y no ha quedado fuera de uso (sin activarlo)."""
	registrado = complemento(id_complemento)
	return registrado is not None and _usable(registrado) and registrado.estado != EstadoComplemento.FALLIDO


def unidades_fijas() -> list:
	"""Entradas fijas de ``[[unidades]]`` de los complementos usables (sin activarlos)."""
	from app.services.vfs.base import UnidadVirtual

	resultado = []
	for registrado in complementos():
		if not _usable(registrado):
			continue
		for unidad in registrado.manifiesto.tabla("unidades"):
			if unidad.get("texto") and unidad.get("direccion"):
				resultado.append(UnidadVirtual(str(unidad["texto"]), str(unidad["direccion"]), str(unidad.get("descripcion", ""))))
	return resultado


def complemento_de_comprimido(nombre: str) -> str | None:
	"""Id del complemento cuyo ``[[comprimidos]]`` abre ``nombre`` (sin activarlo), o ``None``.

	Gana la extensión más larga (``tar.zst`` antes que ``zst``).
	"""
	nombre = nombre.lower()
	mejor: tuple[int, str] | None = None
	for registrado in complementos():
		if not _usable(registrado) or registrado.estado == EstadoComplemento.FALLIDO:
			continue
		for comprimido in registrado.manifiesto.tabla("comprimidos"):
			for extension in comprimido.get("extensiones", []) or []:
				extension = str(extension).lower().lstrip(".")
				if nombre.endswith("." + extension) and (mejor is None or len(extension) > mejor[0]):
					mejor = (len(extension), registrado.id)
	return mejor[1] if mejor else None


def complemento_de_esquema(prefijo: str) -> str | None:
	"""Id del complemento cuyo ``[[esquemas]]`` declara ``prefijo`` (``papelera``, ``nube``...), sin activarlo."""
	prefijo = prefijo.lower().removesuffix("://")
	for registrado in complementos():
		if not _usable(registrado) or registrado.estado == EstadoComplemento.FALLIDO:
			continue
		for esquema in registrado.manifiesto.tabla("esquemas"):
			if str(esquema.get("prefijo", "")).lower() == prefijo:
				return registrado.id
	return None


# ── Suscripciones a eventos por complemento ──────────────────────────────────


def anotar_suscripcion(id_complemento: str, nombre: str, funcion: Callable[..., None]) -> Callable[[], None]:
	"""Anota que ``id_complemento`` suscribió ``funcion`` a ``nombre``; devuelve la función que la quita."""
	clave = (id_complemento, nombre)
	with _r.candado:
		_r.suscripciones.setdefault(clave, []).append(funcion)

	def quitar_suscripcion() -> None:
		with _r.candado:
			lista = _r.suscripciones.get(clave, [])
			if funcion in lista:
				lista.remove(funcion)

	return quitar_suscripcion


def entregar_evento(id_complemento: str, nombre: str, datos: dict[str, Any]) -> int:
	"""[interfaz] Entrega ``nombre`` solo a las funciones que ``id_complemento`` suscribió; devuelve cuántas.

	Lo usa el cargador con el evento que activó el complemento (``evento:<nombre>``):
	cuando el bus lo entregó, el complemento aún no se había suscrito.
	"""
	with _r.candado:
		funciones = list(_r.suscripciones.get((id_complemento, nombre), []))
	for funcion_evento in funciones:
		try:
			funcion_evento(**datos)
		except Exception:  # noqa: BLE001 - ya va protegida; esto solo evita cortar a las demás
			log.exception("Falló la entrega del evento %s a %s", nombre, id_complemento)
	return len(funciones)


def catalogo_columnas() -> list[ColumnaExterna]:
	"""Columnas declaradas por los complementos (título, tipo y si es lenta, del manifiesto)."""
	resultado = []
	for registrado in complementos():
		if not _usable(registrado):
			continue
		for columna in registrado.manifiesto.tabla("columnas"):
			resultado.append(ColumnaExterna(
				id=f"{registrado.id}:{columna['id']}", titulo=str(columna.get("titulo", columna["id"])),
				tipo=str(columna.get("tipo", "texto")), lenta=bool(columna.get("lenta", False)), complemento=registrado.id,
			))
	return resultado


def _grupo(id_complemento: str) -> ThreadPoolExecutor:
	"""Grupo de hilos propio de cada complemento (2 como máximo, 3.8): nunca el GestorTareas de la ventana."""
	with _r.candado:
		if id_complemento not in _r.grupos:
			_r.grupos[id_complemento] = ThreadPoolExecutor(2, thread_name_prefix=f"zc-{id_complemento}")
		return _r.grupos[id_complemento]


def _planificar(funcion_planificada: Callable[[], None]) -> None:
	from app.plugins import cargador

	cargador.planificar(funcion_planificada)


def _carpeta_de(ruta: str) -> str:
	return str(ruta).rsplit("\\", 1)[0].rsplit("/", 1)[0]


def olvidar_columnas(id_complemento: str | None = None, rutas: Iterable[str] | None = None, *, carpeta: str | None = None) -> int:
	"""Quita valores de la caché de columnas externas; devuelve cuántos [cualquiera].

	:param id_complemento: solo los de sus columnas; ``None``, de todos.
	:param rutas: solo los de esas rutas (comparadas sin distinguir mayúsculas); ``None``, todas.
	:param carpeta: solo los de los elementos de esa carpeta (``Ctrl+R``, «Volver a leer»).
	"""
	def normal(ruta: str) -> str:
		return str(ruta).rstrip("\\/").casefold()

	prefijo = f"{id_complemento}:" if id_complemento else ""
	buscadas = {normal(r) for r in rutas} if rutas is not None else None
	en_carpeta = normal(carpeta) if carpeta is not None else None
	with _r.candado:
		claves = [c for c in _r.cache_columnas
			if c[0].startswith(prefijo)
			and (buscadas is None or normal(c[1]) in buscadas)
			and (en_carpeta is None or normal(_carpeta_de(c[1])) == en_carpeta)]
		for clave in claves:
			_r.cache_columnas.pop(clave, None)
		if en_carpeta is not None:
			for clave in [c for c in _r.agotamientos if c[0].startswith(prefijo) and normal(c[1]) == en_carpeta]:
				_r.agotamientos.pop(clave, None)
	return len(claves)


def valor_columna(id: str, entrada: Any, proveedor: Any, al_listo: Callable[[], None]) -> str | None:
	"""Valor de una columna de complemento [interfaz]: nunca bloquea.

	Si está en la caché por (ruta, tamaño, fecha), lo devuelve; si no, manda el
	cálculo al grupo de hilos del complemento cuando su activación ha terminado
	(los 5 s cuentan desde ese momento) y devuelve ``None`` (la fila muestra «…»);
	cuando llega el valor, o se agota y queda «Sin datos», llama a ``al_listo``.
	"""
	id_complemento, _corto = separar_orden(id)
	clave = (id, getattr(entrada, "ruta", ""), getattr(entrada, "tamano", -1), getattr(entrada, "modificado", 0.0))
	carpeta = _carpeta_de(getattr(entrada, "ruta", ""))
	with _r.candado:
		if clave in _r.cache_columnas:
			return _r.cache_columnas[clave]
		if id_complemento in _r.sin_columnas or _r.agotamientos.get((id, carpeta), 0) >= AGOTAMIENTOS_POR_CARPETA:
			return SIN_DATOS
		if clave in _r.columnas_pendientes:
			return None
		_r.columnas_pendientes.add(clave)
	from app.plugins import cargador

	futuro = cargador.asegurar_activo(id_complemento)

	def guardar(valor: str) -> None:
		with _r.candado:
			_r.columnas_pendientes.discard(clave)
			_r.cache_columnas[clave] = valor
		_planificar(al_listo)

	def lanzar_calculo() -> None:
		ok = futuro.done() and not futuro.cancelled() and futuro.exception() is None and futuro.result()
		extractor = funcion("columna", id) if ok else None
		if extractor is None:
			guardar(SIN_DATOS)
			return
		terminado = threading.Event()
		from app.services.vfs.base import Cancelacion

		cancelacion = Cancelacion()

		def calcular() -> None:
			from app.plugins import estado as modulo_estado

			valor = modulo_estado.llamar_protegido(id_complemento, extractor, entrada, proveedor, cancelacion)
			if not terminado.is_set():
				terminado.set()
				guardar(SIN_DATOS if valor is None else str(valor))

		def agotado() -> None:
			if terminado.is_set():
				return
			terminado.set()
			cancelacion.cancelar()
			with _r.candado:
				_r.agotamientos[(id, carpeta)] = _r.agotamientos.get((id, carpeta), 0) + 1
				_r.abandonados[id_complemento] = _r.abandonados.get(id_complemento, 0) + 1
				if _r.abandonados[id_complemento] >= HILOS_ABANDONADOS_MAXIMOS:
					_r.sin_columnas.add(id_complemento)
			log.warning("La columna %s tarda demasiado en %s", id, carpeta)
			guardar(SIN_DATOS)

		temporizador = threading.Timer(TIEMPO_COLUMNA_S, agotado)
		temporizador.daemon = True
		temporizador.start()
		_grupo(id_complemento).submit(calcular)

	# La continuación solo se publica: nunca corre dentro de set_result (3.4).
	futuro.add_done_callback(lambda _f: _planificar(lanzar_calculo))
	return None


def coincide(nombre: str, patrones: Any) -> bool:
	if isinstance(patrones, str):
		patrones = [p for p in patrones.split(";") if p]
	return not patrones or any(fnmatch.fnmatch(nombre.casefold(), str(p).casefold()) for p in patrones)


def lineas_info(entrada: Any, proveedor: Any) -> list[str]:
	"""Líneas extra de «Información del elemento» de todos los complementos cuyo ``[[info]]`` coincide [trabajo]."""
	from app.plugins import cargador
	from app.plugins import estado as modulo_estado

	lineas: list[str] = []
	nombre = str(getattr(entrada, "nombre", ""))
	for registrado in complementos():
		if not _usable(registrado):
			continue
		if not any(coincide(nombre, info.get("patrones", [])) for info in registrado.manifiesto.tabla("info")):
			continue
		try:
			if not cargador.asegurar_activo(registrado.id).result(cargador.TIEMPO_CARGA_S):
				continue
		except Exception:  # noqa: BLE001 - un complemento que no se activa no aporta líneas
			log.debug("No se activó %s para la información del elemento", registrado.id, exc_info=True)
			continue
		funcion_info = funcion("info", registrado.id)
		if funcion_info is None:
			continue
		futuro: Future = _grupo(registrado.id).submit(modulo_estado.llamar_protegido, registrado.id, funcion_info, entrada, proveedor)
		try:
			resultado = futuro.result(TIEMPO_INFO_S)
		except Exception:  # noqa: BLE001 - agotado: se omiten sus líneas
			log.info("Las líneas de información de %s tardan demasiado; se omiten", registrado.id)
			continue
		if resultado:
			lineas.extend(str(linea) for linea in resultado)
	return lineas


def visor_para(nombre: str, *, vista_rapida: bool = False) -> tuple[str, bool] | None:
	"""Visor de complemento de mayor prioridad cuyo patrón coincide con ``nombre``: (id completo, ventana propia).

	Sin activar nada (decide el manifiesto). Con ``vista_rapida`` solo cuentan los que
	devuelven un ``Documento`` y no dicen ``vista_rapida = false`` (3.5). Un visor sin
	patrones no coincide con nada.
	"""
	mejor: tuple[int, str, bool] | None = None
	for registrado in complementos():
		if not _usable(registrado) or registrado.estado == EstadoComplemento.FALLIDO:
			continue
		for visor in registrado.manifiesto.tabla("visores"):
			patrones = visor.get("patrones", [])
			if not visor.get("id") or not patrones or not coincide(nombre, patrones):
				continue
			ventana = bool(visor.get("ventana", False))
			if vista_rapida and (ventana or not visor.get("vista_rapida", True)):
				continue
			try:
				prioridad = int(visor.get("prioridad", 0) or 0)
			except (TypeError, ValueError):
				prioridad = 0
			if mejor is None or prioridad > mejor[0]:
				mejor = (prioridad, f"{registrado.id}:{visor['id']}", ventana)
	return (mejor[1], mejor[2]) if mejor else None


def documento_visor(id: str, proveedor: Any, ruta: str, cancelacion: Any = None) -> Any | None:
	"""[trabajo] ``Documento`` de un visor de complemento, o ``None`` si no se pudo (se usa el visor interno).

	Activa el complemento si hace falta (esperando, 3.4) y llama a su función en el
	grupo de hilos propio del complemento, protegida.
	"""
	from app.plugins import cargador
	from app.plugins import estado as modulo_estado

	id_complemento, _corto = separar_orden(id)
	try:
		if not cargador.asegurar_activo(id_complemento).result(cargador.TIEMPO_CARGA_S):
			return None
	except Exception:  # noqa: BLE001 - sin el complemento se abre el visor interno
		log.info("No se activó %s para ver %s", id_complemento, ruta, exc_info=True)
		return None
	funcion_visor = funcion("visor", id)
	if funcion_visor is None:
		log.warning("El complemento %s no registró el visor %s", id_complemento, id)
		return None
	futuro: Future = _grupo(id_complemento).submit(modulo_estado.llamar_protegido, id_complemento, funcion_visor, proveedor,
		ruta, cancelacion)
	documento = futuro.result()
	if documento is None or not hasattr(documento, "secciones"):
		return None
	return documento


def abrir_ventana_visor(id: str, proveedor: Any, ruta: str, al_fallar: Callable[[str], None] | None = None) -> None:
	"""[interfaz] Visor con ventana propia (``ventana = true``): activa sin esperar y llama a su función en la interfaz."""
	from app.plugins import cargador
	from app.plugins import estado as modulo_estado

	id_complemento, _corto = separar_orden(id)
	futuro = cargador.asegurar_activo(id_complemento)

	def continuar() -> None:
		try:
			ok = bool(futuro.result())
		except Exception:  # noqa: BLE001 - cancelado o con error
			ok = False
		funcion_ventana = funcion("ventana", id) if ok else None
		if funcion_ventana is None:
			if al_fallar is not None:
				registrado = complemento(id_complemento)
				al_fallar(registrado.motivo if registrado and registrado.motivo else _("El visor del complemento no está disponible"))
			return
		modulo_estado.llamar_protegido(id_complemento, funcion_ventana, proveedor, ruta)

	futuro.add_done_callback(lambda _f: _planificar(continuar))


def mascaras_declaradas() -> list[tuple[str, str]]:
	"""(marcador, descripción) de las ``[[mascaras]]`` de los complementos usables (menú del renombrado)."""
	resultado = []
	for registrado in complementos():
		if not _usable(registrado):
			continue
		for mascara in registrado.manifiesto.tabla("mascaras"):
			marcador = str(mascara.get("marcador", ""))
			if marcador:
				resultado.append((marcador, str(mascara.get("descripcion", "")) or registrado.nombre))
	return resultado


def motores_busqueda() -> list[tuple[str, str]]:
	"""(id completo, nombre) de los ``[[busqueda]]`` de los complementos usables (desplegable «Motor»)."""
	resultado = []
	for registrado in complementos():
		if not _usable(registrado) or registrado.estado == EstadoComplemento.FALLIDO:
			continue
		for motor in registrado.manifiesto.tabla("busqueda"):
			if motor.get("id"):
				resultado.append((f"{registrado.id}:{motor['id']}", str(motor.get("nombre", motor["id"]))))
	return resultado


def hay_extractores() -> bool:
	"""Verdadero si algún complemento usable declara ``[[extractores]]`` (casilla del diálogo de búsqueda)."""
	return any(_usable(r) and r.manifiesto.tabla("extractores") for r in complementos())


def acciones_error_aplicables(pregunta: Any) -> list[AccionAplicable]:
	"""Acciones extra para una pregunta de error [interfaz]; nunca activa un complemento.

	Sin activar decide el filtro ``codigos_windows`` del manifiesto; si el
	complemento ya está activo, además su ``aplica()``.
	"""
	from app.plugins import estado as modulo_estado

	codigo = int(getattr(pregunta, "codigo_windows", 0) or 0)
	resultado = []
	for registrado in complementos():
		if not _usable(registrado) or registrado.estado == EstadoComplemento.FALLIDO:
			continue
		for accion in registrado.manifiesto.tabla("acciones_error"):
			codigos = accion.get("codigos_windows", []) or []
			if codigos and codigo not in codigos:
				continue
			id_completo = f"{registrado.id}:{accion.get('id', '')}"
			activo = registrado.estado == EstadoComplemento.ACTIVO
			if activo:
				registrada = funcion("accion_error", id_completo)
				if registrada is None:
					continue
				aplica, _funcion = registrada
				if not modulo_estado.llamar_protegido(registrado.id, aplica, pregunta):
					continue

			def ejecutar(pregunta_actual: Any, id_completo: str = id_completo, id_complemento: str = registrado.id) -> Any:
				registrada_ahora = funcion("accion_error", id_completo)
				if registrada_ahora is None:
					return None
				return modulo_estado.llamar_protegido(id_complemento, registrada_ahora[1], pregunta_actual)

			resultado.append(AccionAplicable(id_completo, str(accion.get("etiqueta", accion.get("id", ""))), ejecutar,
				registrado.id, activo))
	return resultado


def instantanea(panel: Any) -> ObjetivoCongelado:
	"""``ObjetivoCongelado`` de un panel (en el hilo de la interfaz, al pulsar la tecla)."""
	return ObjetivoCongelado(
		lado=str(getattr(panel, "lado", "")), proveedor=getattr(panel, "proveedor", None), ruta=str(getattr(panel, "ruta", "")),
		cursor=panel.cursor(), marcadas=tuple(panel.marcadas()), elementos_trabajo=tuple(panel.elementos_trabajo()),
	)


def nombres(ids: Sequence[str]) -> list[str]:
	"""Nombres visibles de una lista de ids (el id si no está registrado)."""
	return [r.nombre if (r := complemento(i)) else i for i in ids]


# ── Modo desarrollo (14.1.1) ─────────────────────────────────────────────────

_modo_desarrollo = [False]


def fijar_modo_desarrollo(activo: bool) -> None:
	"""Con el modo desarrollo, el catálogo incluye ``complemento_recargar`` (lo consulta ``ordenes.catalogo``)."""
	if _modo_desarrollo[0] != bool(activo):
		_modo_desarrollo[0] = bool(activo)
		_cambio()


def modo_desarrollo() -> bool:
	return _modo_desarrollo[0]
