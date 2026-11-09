# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""API de complementos de zCommander (diseño 2.0, 3.7): la ÚNICA parte de ``app`` que un complemento importa.

``from app.plugins import api``. ``API_VERSION = (1, 1)``. Los cambios de la
versión menor solo añaden; quitar algo exige cambiar la versión principal.
``tests/plugins/test_api_estable.py`` compara la firma pública con una
instantánea (congelada al cerrar PL y P1; desde entonces solo se añade).

Novedades de la 1.1 (solo añadidos; todo lo de la 1.0 sigue igual):

- ``zc.columnas.invalidar(rutas=None)``: olvida los valores guardados de sus columnas.
- ``Paso("restaurar", despues=archivo, antes=copia, tamano, modificado)``: deshacer
  vuelve a poner la copia sobre el archivo si este no cambió desde entonces.
- ``zc.ui.mostrar_diferencias(ruta_a, ruta_b)``, ``zc.abrir_ayuda(pagina)`` con páginas,
  ``Proveedor.orden_preferido`` y resultados de búsqueda con direcciones de un proveedor.
- Un complemento activado por ``evento:<nombre>`` recibe ese primer evento.

Reglas:

- No importa wx ni ``app.ui`` (regla de capas). Todo lo de la interfaz llega
  por UNA inyección: ``fijar_interfaz(interfaz)`` con un ``InterfazAnfitrion``.
  Sin interfaz (pruebas sin wx), los métodos [interfaz] lanzan ``NoAdmitido`` y
  ``anunciar`` solo escribe en el registro.
- Cada método dice en qué hilo se puede llamar: [cualquiera] (la fachada pasa a
  la interfaz lo que haga falta), [trabajo] (bloquea) o [interfaz].
- Lo que aún no tiene implementación lanza ``NoAdmitido`` por ``_sin_implementar``.
"""

from __future__ import annotations

import builtins
import gettext
import logging
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Protocol

from app.core import procesos
from app.core.procesos import ResultadoPrograma
from app.core.red import RespuestaRed
from app.core.tareas import GestorTareas, TokenCancelacion
from app.plugins import registro as _registro
from app.services import formato
from app.services.busqueda import Criterios as CriteriosBusqueda
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar
from app.services.operaciones.deshacer import AccionDeshacer, Paso
from app.services.operaciones.eliminar import OperacionEliminar
from app.services.operaciones.modelo import (
	AccionError,
	ContextoEjecucion,
	Decisor,
	Estado,
	Operacion,
	Politica,
	PreguntaError,
	Progreso,
	RespuestasAutomaticas,
	clave_carril,
)
from app.services.operaciones.renombrar import OperacionRenombrar
from app.services.vfs.base import (
	Cancelado,
	Capacidades,
	Entrada,
	ErrorAcceso,
	ErrorArchivos,
	ErrorRed,
	NoAdmitido,
	NoEncontrado,
	NombreNoValido,
	Proveedor,
	ResultadoPar,
	SinEspacio,
	SoloLectura,
	Ubicacion,
	UnidadVirtual,
	YaExiste,
	comprobar,
)

if TYPE_CHECKING:
	from app.plugins.interfaz import InterfazAnfitrion

log = logging.getLogger(__name__)

API_VERSION: tuple[int, int] = (1, 1)
API_COMPATIBLE_DESDE: tuple[int, int] = (1, 0)

# Niveles de anuncio (los de app.ui.anuncios, como cadenas).
ESENCIAL, RESULTADO, NORMAL, DETALLE = "esencial", "resultado", "normal", "detalle"

__all__ = [
	"API_COMPATIBLE_DESDE", "API_VERSION", "DETALLE", "ESENCIAL", "NORMAL", "RESULTADO",
	"AccionDeshacer", "AccionError", "Anfitrion", "Cancelado", "Capacidades", "ClienteRed", "Complemento",
	"ComponentesComplemento", "ConfigComplemento", "ContextoComplemento", "ContextoEjecucion", "CriteriosBusqueda",
	"Decisor", "DeshacerComplemento", "Documento", "Entrada", "ErrorAcceso", "ErrorArchivos", "ErrorRed", "Estado",
	"EspaciosTrabajo", "ModuloUI", "NoAdmitido", "NoEncontrado", "NombreNoValido", "OpcionesCopia", "Operacion",
	"OperacionCopiar", "OperacionEliminar", "OperacionRenombrar", "PanelComplemento", "Paso", "Politica",
	"PreguntaError", "Progreso", "Proveedor", "RegistroAccionesError", "RegistroBusqueda", "RegistroColumnas",
	"RegistroEventos", "RegistroInfo", "RegistroMascaras", "RegistroOrdenes", "RegistroPreferencias", "RegistroVFS",
	"RegistroVisores", "RespuestaRed", "RespuestasAutomaticas", "ResultadoPar", "ResultadoPrograma", "Seccion",
	"SecretosComplemento", "SinEspacio", "SoloLectura", "SonidosComplemento", "TokenCancelacion", "Ubicacion",
	"UnidadVirtual", "VistasCarpeta", "YaExiste", "clave_carril", "comprobar", "fijar_interfaz", "formato",
	"provisional", "traduccion",
]


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Inyección de la interfaz ─────────────────────────────────────────────────

_interfaz: list[InterfazAnfitrion | None] = [None]


def fijar_interfaz(interfaz: InterfazAnfitrion | None) -> None:
	"""La ventana la llama al construirse y con ``None`` al cerrar (3.4, paso 8)."""
	_interfaz[0] = interfaz


def interfaz() -> InterfazAnfitrion | None:
	return _interfaz[0]


def _exigir_interfaz() -> InterfazAnfitrion:
	actual = _interfaz[0]
	if actual is None:
		raise NoAdmitido(_("Esta función necesita la ventana de zCommander"))
	return actual


def _en_interfaz(funcion: Callable[[], None]) -> None:
	"""[cualquiera]: en el hilo de la interfaz se llama en el acto; desde otro, se planifica."""
	actual = _exigir_interfaz()
	if actual.en_hilo_interfaz():
		funcion()
	else:
		actual.planificar(funcion)


def _sin_implementar(nombre: str) -> None:
	"""Lo que aún no tiene implementación lanza ``NoAdmitido`` por aquí (18.1).

	Con PL terminado ninguna fachada la usa, así que ya no lleva la marca
	``provisional`` que contaba la prueba de provisionales; se conserva para lo que
	añada una versión menor de la API antes de programarlo.
	"""
	raise NoAdmitido(_("Esta función de la API no está disponible en esta versión: {n}").format(n=nombre))


def _fabrica_protegida(id_complemento: str, fabrica: Callable[..., Any]) -> Callable[..., Any]:
	"""Los proveedores de un complemento solo lanzan ``ErrorArchivos`` (3.7): lo demás se convierte."""

	def envuelta(*args: Any, **kwargs: Any) -> Any:
		try:
			return fabrica(*args, **kwargs)
		except ErrorArchivos:
			raise
		except Exception as error:
			from app.plugins import estado

			log.exception("Falló la fábrica de un proveedor del complemento %s", id_complemento)
			raise ErrorArchivos(_("El complemento {n} no pudo abrir esta dirección: {e}").format(
				n=estado.nombre_de(id_complemento), e=error)) from error

	return envuelta


def traduccion(nombre_modulo: str) -> tuple[Callable[[str], str], Callable[[str, str, int], str]]:
	"""``_`` y ``ngettext`` del dominio de un complemento (solo se entrega el español: sin catálogo, identidad)."""
	try:
		from app.core import paths

		catalogo = gettext.translation(nombre_modulo, localedir=str(paths.ruta_traducciones()), fallback=True)
	except Exception:  # noqa: BLE001 - sin catálogo, los textos quedan como están
		log.debug("Sin catálogo de traducción para %s", nombre_modulo, exc_info=True)
		catalogo = gettext.NullTranslations()
	return catalogo.gettext, catalogo.ngettext


def provisional(id_corto: str) -> Callable[[ContextoComplemento], None]:
	"""Manejador provisional MARCADO de una orden de complemento aún sin programar.

	Lo usan los esqueletos de N2; la prueba de provisionales lo detecta por la marca
	``provisional = True``, no por el texto.
	"""

	def manejador(ctx: ContextoComplemento) -> None:
		ctx.anunciar(_("Esta orden del complemento aún no está programada: {o}").format(o=id_corto), ESENCIAL)

	manejador.provisional = True  # type: ignore[attr-defined]
	manejador.__name__ = f"provisional_{id_corto}"
	return manejador


# ── Complemento, documentos y paneles ────────────────────────────────────────


class Complemento:
	"""Clase base de la entrada de un complemento (``entrada = "modulo:Clase"``)."""

	id: str = ""
	carpeta: Path = Path()

	def activar(self, zc: Anfitrion) -> None:
		"""Registra sus funciones sobre ``zc``. No abre diálogos (3.4)."""

	def desactivar(self) -> None:
		"""Libera lo suyo al cerrar zCommander (el tope de 2 s entre todos solo se mide)."""

	def ventanas_para_revisar(self, padre: "wx.Window") -> list["wx.TopLevelWindow"]:  # noqa: F821, UP037
		"""Opcional: crea sin mostrar sus ventanas para ``revisar_teclado`` (3.12)."""
		return []

	def puede_cerrar(self) -> bool:
		"""Opcional [interfaz]: fase con veto del cierre; falso cancela el cierre de zCommander."""
		return True


@dataclass(frozen=True)
class Seccion:
	titulo: str
	nivel: int = 1
	texto: str = ""
	pagina: int = 0


@dataclass(frozen=True)
class Documento:
	titulo: str
	secciones: tuple[Seccion, ...]
	metadatos: dict[str, str] = field(default_factory=dict)
	aviso: str = ""


class PanelComplemento(Protocol):
	"""Vista de un panel para un complemento [interfaz]."""

	lado: str

	@property
	def proveedor(self) -> Proveedor: ...
	@property
	def ruta(self) -> str: ...
	def mostrar_ruta(self) -> str: ...
	def cursor(self) -> Entrada | None: ...
	def marcadas(self) -> list[Entrada]: ...
	def elementos_trabajo(self) -> list[Entrada]: ...
	def refrescar(self) -> None: ...


class PanelVista:
	"""``PanelComplemento`` sobre un panel real de la ventana (solo consulta y ``refrescar``)."""

	def __init__(self, panel: Any) -> None:
		self._panel = panel
		self.lado = str(getattr(panel, "lado", ""))

	@property
	def proveedor(self) -> Proveedor:
		return self._panel.proveedor

	@property
	def ruta(self) -> str:
		return self._panel.ruta

	def mostrar_ruta(self) -> str:
		return self._panel.mostrar_ruta()

	def cursor(self) -> Entrada | None:
		entrada = self._panel.cursor()
		return None if entrada is None or getattr(entrada, "es_superior", False) else entrada

	def marcadas(self) -> list[Entrada]:
		return list(self._panel.marcadas())

	def elementos_trabajo(self) -> list[Entrada]:
		return list(self._panel.elementos_trabajo())

	def refrescar(self) -> None:
		self._panel.refrescar()


class PanelCongelado:
	"""``PanelComplemento`` que responde con una instantánea (``ObjetivoCongelado``); ``refrescar`` va al panel real."""

	def __init__(self, objetivo: _registro.ObjetivoCongelado, real: Any = None) -> None:
		self._objetivo = objetivo
		self._real = real
		self.lado = objetivo.lado

	@property
	def proveedor(self) -> Proveedor:
		return self._objetivo.proveedor

	@property
	def ruta(self) -> str:
		return self._objetivo.ruta

	def mostrar_ruta(self) -> str:
		proveedor = self._objetivo.proveedor
		return proveedor.mostrar(self._objetivo.ruta) if proveedor is not None else self._objetivo.ruta

	def cursor(self) -> Entrada | None:
		entrada = self._objetivo.cursor
		return None if entrada is None or getattr(entrada, "es_superior", False) else entrada

	def marcadas(self) -> list[Entrada]:
		return list(self._objetivo.marcadas)

	def elementos_trabajo(self) -> list[Entrada]:
		return list(self._objetivo.elementos_trabajo)

	def refrescar(self) -> None:
		if self._real is not None:
			self._real.refrescar()


@dataclass
class ContextoComplemento:
	"""Lo que recibe el manejador de una orden de complemento [interfaz]. Sin ventana ni servicios internos."""

	orden: str
	activo: PanelComplemento
	pasivo: PanelComplemento
	lado_objetivo: str | None = None
	argumento: Any = None

	@property
	def objetivo(self) -> PanelComplemento:
		if self.lado_objetivo and getattr(self.pasivo, "lado", None) == self.lado_objetivo:
			return self.pasivo
		return self.activo

	def anunciar(self, texto: str, nivel: str = NORMAL, completo: str = "", interrumpir: bool | None = None) -> None:
		actual = _interfaz[0]
		if actual is None:
			log.info("Anuncio de %s: %s", self.orden, texto)
			return
		actual.anunciar(texto, nivel, completo, interrumpir)

	def sonar(self, evento: str, variante: str = "", *, sustituye: bool = False) -> bool:
		from app.services.sonidos import servicio

		id_complemento = self.orden.split(":", 1)[0]
		return servicio.sonar(_id_sonido(id_complemento, evento), variante, sustituye=sustituye)


def _id_sonido(id_complemento: str, evento: str) -> str:
	"""Un evento propio se escribe corto («fin») o completo; uno del núcleo, con su punto («op.fin»)."""
	if ":" in evento or ("." in evento and not evento.startswith(id_complemento)):
		return evento
	return f"{id_complemento}:{evento}"


# ── Fachadas de los registros ────────────────────────────────────────────────


class _Parte:
	def __init__(self, anfitrion: Anfitrion) -> None:
		self._zc = anfitrion

	@property
	def _id(self) -> str:
		return self._zc.id


class RegistroOrdenes(_Parte):
	def manejador(self, id_corto: str, funcion: Callable[[ContextoComplemento], None]) -> None:
		_registro.fijar_funcion("manejador", f"{self._id}:{id_corto}", funcion)

	def estado(self, id_corto: str, funcion: Callable[[ContextoComplemento], bool]) -> None:
		_registro.fijar_funcion("estado", f"{self._id}:{id_corto}", funcion)

	def disponible(self, id_corto: str, funcion: Callable[[ContextoComplemento], bool]) -> None:
		_registro.fijar_funcion("disponible", f"{self._id}:{id_corto}", funcion)

	def interna(self, nombre: str, funcion: Callable[[list[str], Callable[[str], None], Any], int]) -> None:
		_registro.fijar_funcion("interna", nombre, (self._id, funcion))


class RegistroVFS(_Parte):
	def esquema(self, prefijo: str, fabrica: Callable[[str], tuple[Proveedor, str]]) -> None:
		from app.services.vfs import resolver

		resolver.registrar_esquema(prefijo, _fabrica_protegida(self._id, fabrica))

	def comprimido(self, extensiones: tuple[str, ...], fabrica: Callable[[Proveedor, str], Proveedor]) -> None:
		from app.services.vfs import resolver

		resolver.registrar_comprimido(tuple(extensiones), _fabrica_protegida(self._id, fabrica))

	def unidades(self, funcion: Callable[[], list[UnidadVirtual]]) -> None:
		from app.plugins import estado
		from app.services.vfs import resolver

		id_complemento = self._id

		def protegida() -> list[UnidadVirtual]:
			return list(estado.llamar_protegido(id_complemento, funcion) or [])

		resolver.registrar_unidades(protegida)

	def resolver(self, direccion: str) -> tuple[Proveedor, str]:
		from app.services.vfs import resolver

		proveedor, ruta, _nombre = resolver.abrir_ruta(direccion)
		return proveedor, ruta


class RegistroColumnas(_Parte):
	def extractor(self, id_corto: str, funcion: Callable[[Entrada, Proveedor, Any], str | None]) -> None:
		_registro.fijar_funcion("columna", f"{self._id}:{id_corto}", funcion)

	def invalidar(self, rutas: Sequence[str] | None = None) -> None:
		"""[cualquiera] (1.1) Olvida los valores guardados de sus columnas: de ``rutas`` o, sin ellas, todos.

		El núcleo guarda cada valor por (ruta, tamaño, fecha); lo que cambia sin tocar
		el archivo (un comentario, una etiqueta) necesita esto. Después, ``refrescar()``
		del panel vuelve a pedir los valores.
		"""
		_registro.olvidar_columnas(self._id, rutas)


class RegistroVisores(_Parte):
	def visor(self, id_corto: str, funcion: Callable[[Proveedor, str, Any], Documento]) -> None:
		_registro.fijar_funcion("visor", f"{self._id}:{id_corto}", funcion)

	def ventana(self, id_corto: str, funcion: Callable[[Proveedor, str], None]) -> None:
		_registro.fijar_funcion("ventana", f"{self._id}:{id_corto}", funcion)


class RegistroInfo(_Parte):
	def lineas(self, funcion: Callable[[Entrada, Proveedor], list[str]]) -> None:
		_registro.fijar_funcion("info", self._id, funcion)


class RegistroBusqueda(_Parte):
	def proveedor(self, id_corto: str, funcion: Callable[[CriteriosBusqueda, Callable[[str], None], Any], None]) -> None:
		_registro.fijar_funcion("busqueda", f"{self._id}:{id_corto}", funcion)

	def extractor(self, funcion: Callable[[Proveedor, str, Any], str | None]) -> None:
		_registro.fijar_funcion("extractor", self._id, funcion)


class RegistroMascaras(_Parte):
	def mascara(self, marcador: str, funcion: Callable[[Entrada, Proveedor], str | None]) -> None:
		_registro.registrar_mascara(self._id, marcador, funcion)

	def evaluar(self, plantilla: str, entrada: Entrada, proveedor: Proveedor) -> str:
		"""[trabajo] Una plantilla de renombrado con TODAS las máscaras (las de la 1.x y las de los complementos).

		Activa (y espera) los complementos cuyas máscaras aparecen. Una plantilla mal
		escrita lanza ``NombreNoValido`` con el mensaje del renombrado múltiple.
		"""
		from app.services import renombrado

		try:
			piezas = renombrado.compilar(plantilla)
		except renombrado.ErrorMascara as error:
			raise NombreNoValido(str(error)) from error
		elementos = renombrado.elementos_desde_entradas([entrada], proveedor)
		if not elementos:
			return ""
		return renombrado.evaluar(piezas, elementos[0], 0, renombrado.OpcionesRenombrado())


class RegistroAccionesError(_Parte):
	def accion(self, id_corto: str, aplica: Callable[[PreguntaError], bool],
			funcion: Callable[[PreguntaError], AccionError | None]) -> None:
		_registro.fijar_funcion("accion_error", f"{self._id}:{id_corto}", (aplica, funcion))


class RegistroEventos(_Parte):
	def suscribir(self, nombre: str, funcion: Callable[..., None]) -> Callable[[], None]:
		from app.plugins import estado
		from app.services import eventos

		id_complemento = self._id

		def entregar(**datos: Any) -> None:
			estado.llamar_evento(id_complemento, nombre, funcion, **datos)

		cancelar_bus = eventos.bus().suscribir(nombre, entregar)
		# El cargador entrega a estas funciones el evento que activó el complemento (``evento:<nombre>``).
		cancelar_registro = _registro.anotar_suscripcion(id_complemento, nombre, entregar)

		def cancelar() -> None:
			cancelar_bus()
			cancelar_registro()

		return cancelar

	def emitir(self, nombre: str, **datos: Any) -> None:
		from app.services import eventos

		completo = nombre if nombre.startswith(self._id + ":") else f"{self._id}:{nombre}"
		eventos.bus().emitir(completo, **datos)


class RegistroPreferencias(_Parte):
	def dialogo(self, funcion: Callable[["wx.Window"], None]) -> None:  # noqa: F821, UP037
		_exigir_interfaz().registrar_dialogo_complemento(self._id, funcion)

	def abrir(self) -> None:
		_exigir_interfaz().abrir_preferencias(self._id)


class ConfigComplemento(_Parte):
	"""Claves cortas de la configuración propia del complemento (3.6)."""

	_SIN_VALOR = object()

	def _config(self) -> Any:
		from app.plugins import config_plugins

		return config_plugins.registro().de(self._id)

	def obtener(self, clave: str, por_defecto: Any = _SIN_VALOR) -> Any:
		try:
			return self._config().obtener(f"ajustes.{clave}")
		except KeyError:
			if por_defecto is ConfigComplemento._SIN_VALOR:
				raise
			return por_defecto

	def establecer(self, clave: str, valor: Any) -> bool:
		return bool(self._config().establecer(f"ajustes.{clave}", valor))

	def establecer_varias(self, cambios: dict[str, Any]) -> bool:
		return bool(self._config().establecer_varias({f"ajustes.{c}": v for c, v in cambios.items()}))

	def suscribir(self, funcion: Callable[[str, Any, Any], None], prefijo: str = "") -> Callable[[], None]:
		def avisar(clave: str, anterior: Any, nuevo: Any) -> None:
			corta = clave.split(".", 1)[1] if "." in clave else clave
			actual = _interfaz[0]
			if actual is not None and not actual.en_hilo_interfaz():
				actual.planificar(lambda: funcion(corta, anterior, nuevo))
			else:
				funcion(corta, anterior, nuevo)

		return self._config().suscribir(avisar, f"ajustes.{prefijo}")

	def restablecer(self) -> None:
		from app.plugins import config_plugins

		for declaracion in config_plugins.registro().declaraciones(self._id):
			self.establecer(declaracion["clave"], declaracion.get("defecto"))


class SecretosComplemento(_Parte):
	"""Secretos propios (``plugin:<id>:<nombre>``) en ``secretos.dat``; solo con el permiso «secretos»."""

	def _almacen(self) -> Any:
		if "secretos" not in self._zc.permisos:
			raise NoAdmitido(_("El complemento no declaró el permiso «secretos»"))
		from app.core.secretos import obtener_secretos

		return obtener_secretos()

	def _nombre(self, nombre: str) -> str:
		return f"plugin:{self._id}:{nombre}"

	def obtener(self, nombre: str) -> str | None:
		return self._almacen().obtener(self._nombre(nombre))

	def guardar(self, nombre: str, valor: str) -> None:
		self._almacen().guardar(self._nombre(nombre), valor)

	def borrar(self, nombre: str) -> None:
		self._almacen().borrar(self._nombre(nombre))


class SonidosComplemento(_Parte):
	def sonar(self, evento: str, variante: str = "", *, sustituye: bool = False) -> bool:
		from app.services.sonidos import servicio

		return servicio.sonar(_id_sonido(self._id, evento), variante, sustituye=sustituye)


class ComponentesComplemento(_Parte):
	"""Componentes de ``data/bin``: ``ruta()`` y ``ejecutable()`` se piden en cada uso y nunca se guardan (6.3)."""

	def ruta(self, id_componente: str) -> Path:
		from app.services.componentes import estado

		return estado.ruta(id_componente)

	def ejecutable(self, id_componente: str, nombre: str) -> Path:
		from app.services.componentes import estado

		return estado.ejecutable(id_componente, nombre)

	def disponible(self, id_componente: str) -> bool:
		from app.services.componentes import estado

		return estado.disponible(id_componente)

	def al_detener(self, id_componente: str, funcion: Callable[[], bool]) -> None:
		from app.services.componentes import estado

		estado.registrar_al_detener(id_componente, funcion)


class DeshacerComplemento(_Parte):
	def registrar(self, accion: AccionDeshacer) -> None:
		_en_interfaz(lambda: _exigir_interfaz().registrar_deshacer(accion))


class EspaciosTrabajo(_Parte):
	def listar(self) -> list[str]:
		from app.services import espacios

		return espacios.listar()

	def guardar_actual(self, nombre: str, nota: str = "") -> None:
		from app.services import espacios

		espacios.guardar_actual(nombre, nota)

	def abrir(self, nombre: str) -> None:
		from app.services import espacios

		espacios.abrir(nombre)


class VistasCarpeta(_Parte):
	def conjuntos(self) -> list[str]:
		from app.services import vistas_carpeta

		return vistas_carpeta.conjuntos()

	def proponer_conjunto(self, nombre: str, columnas: list[str], lectura: list[str],
			extensiones: Sequence[str] = (), proporcion: float = 0.6) -> bool:
		from app.services import vistas_carpeta

		return vistas_carpeta.proponer_conjunto(nombre, columnas, lectura, extensiones, proporcion)


class ClienteRed(_Parte):
	"""HTTP con la pila de ``app.core.red`` y el User-Agent «zCommander/<versión> (<id>)» [trabajo]."""

	def _permitido(self, url: str) -> None:
		import urllib.parse

		permisos = self._zc.permisos
		host = urllib.parse.urlsplit(url).hostname or ""
		if "red" in permisos or f"internet:{host}" in permisos:
			return
		raise NoAdmitido(_("El complemento no declaró el permiso de red para {h}").format(h=host))

	def _config(self) -> Any:
		from app.core import red
		from app.core.version import APP_VERSION

		return red.ConfiguracionRed("zCommander", f"{APP_VERSION} ({self._id})")

	def obtener(self, url: str, *, cabeceras: dict | None = None, tiempo_s: float = 30) -> RespuestaRed:
		from app.core import red

		self._permitido(url)
		try:
			return red.obtener(self._config(), url, cabeceras=cabeceras, tiempo_s=tiempo_s)
		except red.ErrorHTTP as error:
			raise ErrorRed(error.mensaje, url) from error

	def enviar(self, url: str, datos: bytes | dict, *, metodo: str = "POST", cabeceras: dict | None = None,
			tiempo_s: float = 30) -> RespuestaRed:
		from app.core import red

		self._permitido(url)
		try:
			return red.enviar(self._config(), url, datos, metodo=metodo, cabeceras=cabeceras, tiempo_s=tiempo_s)
		except red.ErrorHTTP as error:
			raise ErrorRed(error.mensaje, url) from error

	def descargar(self, url: str, destino: Path, *, sha256: str = "", tamano: int = -1, cancelacion: Any = None,
			al_progresar: Callable[[int, int], None] | None = None) -> Path:
		from app.core import descargas, red

		self._permitido(url)
		try:
			return descargas.descargar(self._config(), url, Path(destino), sha256=sha256, tamano=tamano,
				cancelacion=cancelacion, al_progresar=al_progresar)
		except red.ErrorHTTP as error:
			raise ErrorRed(error.mensaje, url) from error


class ModuloUI(_Parte):
	"""Delegación en ``app.ui.api_ui`` a través de ``InterfazAnfitrion.modulo_ui`` [interfaz].

	Dentro de ``activar()`` sus diálogos lanzan ``RuntimeError`` (3.4).
	"""

	_DIALOGOS = frozenset({"mostrar_modal", "mostrar_mensaje", "mostrar_error", "confirmar", "elegir_opcion", "pedir_texto",
		"mostrar_texto", "mostrar_documento", "mostrar_resultados"})

	def __getattr__(self, nombre: str) -> Any:
		if nombre.startswith("_"):
			raise AttributeError(nombre)
		actual = _exigir_interfaz()
		if nombre in ModuloUI._DIALOGOS:
			from app.plugins import registro
			from app.plugins.estado import EstadoComplemento

			if registro.estado(self._id) == EstadoComplemento.CARGANDO:
				raise RuntimeError(_("Un complemento no puede abrir un diálogo dentro de activar()"))
		return getattr(actual.modulo_ui, nombre)


# ── Anfitrión ────────────────────────────────────────────────────────────────


class Anfitrion:
	"""Lo que recibe ``activar(zc)``: el único acceso del complemento a zCommander."""

	def __init__(self, id: str, carpeta: Path, *, permisos: Sequence[str] = (), decisor: Decisor | None = None,
			tareas: GestorTareas | None = None) -> None:
		from app.core.version import APP_VERSION

		self.id = id
		self.version_app = APP_VERSION
		self.carpeta = Path(carpeta)
		self.permisos = tuple(permisos)
		self.registro = logging.getLogger(f"zcplugins.{id}")
		self._decisor = decisor
		self._tareas = tareas
		self.config = ConfigComplemento(self)
		self.secretos = SecretosComplemento(self)
		self.ordenes = RegistroOrdenes(self)
		self.vfs = RegistroVFS(self)
		self.columnas = RegistroColumnas(self)
		self.visores = RegistroVisores(self)
		self.info = RegistroInfo(self)
		self.busqueda = RegistroBusqueda(self)
		self.renombrado = RegistroMascaras(self)
		self.errores = RegistroAccionesError(self)
		self.eventos = RegistroEventos(self)
		self.preferencias = RegistroPreferencias(self)
		self.sonidos = SonidosComplemento(self)
		self.componentes = ComponentesComplemento(self)
		self.red = ClienteRed(self)
		self.ui = ModuloUI(self)
		self.deshacer = DeshacerComplemento(self)
		self.espacios = EspaciosTrabajo(self)
		self.vistas = VistasCarpeta(self)

	@property
	def datos(self) -> Path:
		from app.core import paths

		ruta = paths.ruta_config_plugins() / self.id
		ruta.mkdir(parents=True, exist_ok=True)
		return ruta

	@property
	def cache(self) -> Path:
		from app.core import paths

		ruta = paths.ruta_cache_plugins() / self.id
		ruta.mkdir(parents=True, exist_ok=True)
		return ruta

	@property
	def tareas(self) -> GestorTareas:
		if self._tareas is None:
			self._tareas = GestorTareas(max_hilos=2, nombre=f"zc-{self.id}")
		return self._tareas

	@property
	def decisor(self) -> Decisor:
		if self._decisor is not None:
			return self._decisor
		from app.services.vfs import resolver

		decisor = resolver.servicios().decisor
		if decisor is None:
			raise NoAdmitido(_("No hay a quién preguntar sin la ventana de zCommander"))
		return decisor

	# Métodos ------------------------------------------------------------------

	def anunciar(self, texto: str, nivel: str = NORMAL, completo: str = "", interrumpir: bool | None = None) -> None:
		actual = _interfaz[0]
		if actual is None:
			self.registro.info("Anuncio: %s", texto)
			return
		if actual.en_hilo_interfaz():
			actual.anunciar(texto, nivel, completo, interrumpir)
		else:
			actual.planificar(lambda: actual.anunciar(texto, nivel, completo, interrumpir))

	def lanzar(self, operacion: Operacion, en_cola: bool = False, al_terminar: Callable[[Operacion], None] | None = None) -> None:
		origen = getattr(operacion, "orden_origen", "") or _orden_en_curso.get(self.id, "")
		_en_interfaz(lambda: _exigir_interfaz().lanzar(operacion, en_cola, al_terminar, orden_origen=origen))

	def ejecutar_programa(self, argumentos: list[str], *, entrada: bytes = b"", carpeta: str | None = None,
			tiempo_s: float = 60, cancelacion: Any = None, al_leer: Callable[[bytes], None] | None = None,
			entorno: dict[str, str] | None = None) -> ResultadoPrograma:
		if "ejecutar_programas" not in self.permisos:
			raise NoAdmitido(_("El complemento no declaró el permiso «ejecutar_programas»"))
		try:
			return procesos.lanzar(list(argumentos), entrada=entrada, carpeta=carpeta, tiempo_s=tiempo_s,
				cancelacion=cancelacion, al_leer=al_leer, entorno=entorno)
		except procesos.ErrorProceso as error:
			raise ErrorArchivos(error.mensaje) from error
		except OSError as error:
			raise ErrorArchivos(_("No se pudo ejecutar {p}: {e}").format(p=argumentos[0] if argumentos else "", e=error)) from error

	def abrir_programa(self, argumentos: list[str], *, carpeta: str | None = None) -> int:
		if "ejecutar_programas" not in self.permisos:
			raise NoAdmitido(_("El complemento no declaró el permiso «ejecutar_programas»"))
		return procesos.lanzar_independiente(list(argumentos), carpeta=carpeta)

	def abrir_ruta(self, texto: str, lado: str | None = None) -> None:
		_en_interfaz(lambda: _exigir_interfaz().abrir_ruta(texto, lado))

	def abrir_ayuda(self, pagina: str = "") -> None:
		_exigir_interfaz().abrir_ayuda(self.id, pagina)

	def ejecutar_orden(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None:
		_exigir_interfaz().ejecutar_orden(id_orden, lado, argumento=argumento)

	def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> Future[bool]:
		return _exigir_interfaz().ejecutar_orden_futuro(id_orden, lado, argumento=argumento)

	def escribir_en_linea(self, texto: str) -> None:
		_exigir_interfaz().escribir_en_linea(texto)

	def exportar(self, nombre: str, objeto: Any) -> None:
		_registro.exportar(self.id, nombre, objeto)

	def complemento(self, id: str) -> SimpleNamespace | None:
		"""Lo exportado por otro complemento. En la interfaz nunca importa en el acto (3.4)."""
		from app.plugins import cargador

		exportado = _registro.exportados(id)
		if exportado is not None:
			return SimpleNamespace(**exportado)
		if threading.current_thread() is threading.main_thread():
			# Nunca importa en el acto: la activación se pide en la siguiente vuelta del bucle.
			cargador.planificar(lambda: cargador.asegurar_activo(id))
			return None
		futuro = cargador.asegurar_activo(id)
		try:
			if not futuro.result(cargador.TIEMPO_CARGA_S):
				return None
		except Exception:  # noqa: BLE001 - si no se puede activar, no hay nada que devolver
			self.registro.debug("No se pudo activar %s", id, exc_info=True)
			return None
		exportado = _registro.exportados(id)
		return SimpleNamespace(**exportado) if exportado is not None else None

	def complemento_futuro(self, id: str) -> Future[SimpleNamespace | None]:
		from app.plugins import cargador

		resultado: Future = Future()
		activacion = cargador.asegurar_activo(id)

		def resolver(f: Future) -> None:
			try:
				ok = bool(f.result())
			except Exception:  # noqa: BLE001 - cancelado o con error: no hay nada
				ok = False
			exportado = _registro.exportados(id) if ok else None
			resultado.set_result(SimpleNamespace(**exportado) if exportado is not None else None)

		activacion.add_done_callback(lambda f: cargador.planificar(lambda: resolver(f)))
		return resultado


#: Orden de complemento que se está ejecutando, por complemento (para ``Anfitrion.lanzar``, 10.1).
_orden_en_curso: dict[str, str] = {}


def ejecutar_manejador(id_completo: str, contexto: ContextoComplemento) -> bool:
	"""Llama protegido al manejador de una orden de complemento; falso si no hay o falló."""
	from app.plugins import estado

	manejador = _registro.manejador(id_completo)
	id_complemento = id_completo.split(":", 1)[0]
	if manejador is None:
		log.warning("La orden %s no tiene manejador", id_completo)
		return False
	_orden_en_curso[id_complemento] = id_completo
	resultado = {"ok": False}

	def llamar() -> None:
		manejador(contexto)
		resultado["ok"] = True

	try:
		estado.llamar_protegido(id_complemento, llamar)
	finally:
		_orden_en_curso.pop(id_complemento, None)
	return resultado["ok"]


from app.plugins import api_pruebas as pruebas  # noqa: E402, F401 - submódulo api.pruebas (3.7), después de definir la API
