# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Descubrimiento, confianza y activación de los complementos (diseño 2.0, 3.2, 3.4, 3.8 y 3.9). Sin wx.

Lo crea N2 (versión funcional mínima); dueño posterior PL.

**Activación: una máquina de estados en el hilo de la interfaz.** Ningún hilo
tiene un candado tomado mientras espera a otro y el hilo de la interfaz nunca
espera, así que no puede haber interbloqueos:

- ``asegurar_activo(id) -> Future[bool]`` [cualquiera]: resuelto en el acto si
  ya está activo (verdadero) o no se puede usar (falso); el de la carga en curso
  si está ``CARGANDO``; si está ``REGISTRADO``, empieza la carga. Desde un hilo
  de trabajo, la petición pasa a la interfaz por el planificador y el futuro se
  devuelve en el acto.
- Dependencias primero (``[requiere] complementos``), encadenando futuros; un
  ciclo resuelve con falso a todos los de la cadena.
- Pasos de la carga: centinela; en el hilo ``zc-cargador`` (nunca el
  ``GestorTareas``), sumas e importación con el **cargador verificado**, con un
  tope de ``TIEMPO_CARGA_S``; de vuelta en la interfaz, ``activar(zc)``; el
  centinela se borra en un ``finally`` y el futuro se resuelve.
- Quien espera un futuro en la interfaz solo PUBLICA su continuación con
  ``planificar``: nunca corre dentro de ``set_result``.

Sin planificador (herramientas y pruebas sin interfaz) la carga es síncrona
en el hilo que la pide.
"""

from __future__ import annotations

import builtins
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import logging
import sys
import threading
import time
import types
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.plugins import estado as modulo_estado
from app.plugins import firma, manifiesto, registro, serie
from app.plugins.estado import EstadoComplemento

log = logging.getLogger(__name__)

TIEMPO_CARGA_S = 30.0
PAQUETE_RAIZ = "zcplugins"
NO_USABLES = (EstadoComplemento.FALLIDO, EstadoComplemento.INHABILITADO, EstadoComplemento.SIN_ACEPTAR,
	EstadoComplemento.INCOMPATIBLE, EstadoComplemento.ERROR_MANIFIESTO)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Planificador (lleva llamadas al hilo de la interfaz) ─────────────────────

_plan: dict[str, Any] = {"funcion": None, "cerrado": False}
_candado_plan = threading.Lock()


def fijar_planificador(planificador: Callable[[Callable[[], None]], None] | None) -> None:
	"""``main.py`` pone ``wx.CallAfter`` justo después de crear ``wx.App`` (14.8)."""
	with _candado_plan:
		_plan["funcion"] = planificador
		_plan["cerrado"] = False


def hay_planificador() -> bool:
	return _plan["funcion"] is not None


def planificar(funcion: Callable[[], None]) -> None:
	"""Ejecuta ``funcion`` en el hilo de la interfaz (en el acto si no hay planificador).

	La bandera de cierre y la llamada al planificador comparten candado: ninguna
	llamada se cuela después de ``cerrar`` (tras destruir ``wx.App`` sería un error).
	"""
	with _candado_plan:
		if _plan["cerrado"]:
			log.debug("Llamada descartada: el cargador está cerrado")
			return
		planificador = _plan["funcion"]
		if planificador is not None:
			planificador(funcion)
			return
	funcion()


def en_hilo_interfaz() -> bool:
	return threading.current_thread() is threading.main_thread()


# ── Cargador de módulos verificado (3.9) ─────────────────────────────────────


def _sha256(datos: bytes) -> str:
	return hashlib.sha256(datos).hexdigest()


class _Verificacion:
	"""Sumas que se exigen al leer cada archivo de un complemento (``None`` = sin comprobar)."""

	def __init__(self, id_complemento: str, raiz: Path, sumas: dict[str, str] | None) -> None:
		self.id = id_complemento
		self.raiz = raiz
		self.sumas = sumas

	def comprobar(self, ruta: str, datos: bytes) -> None:
		if self.sumas is None:
			return
		try:
			relativa = Path(ruta).resolve().relative_to(self.raiz.resolve()).as_posix()
		except ValueError as error:
			raise ImportError(_("El archivo {a} no es del complemento {c}").format(a=ruta, c=self.id)) from error
		if self.sumas.get(relativa) != _sha256(datos):
			raise ImportError(_("El archivo {a} del complemento {c} ha cambiado").format(a=relativa, c=self.id))


class CargadorVerificado(importlib.machinery.SourceFileLoader):
	"""Lee cada ``.py`` UNA vez, comprueba su suma y compila desde esos mismos bytes.

	Nunca lee ni escribe ``.pyc``: una ``.pyc`` sembrada en ``data/cache/pycache`` no se ejecuta.
	"""

	def __init__(self, fullname: str, path: str, verificacion: _Verificacion) -> None:
		super().__init__(fullname, path)
		self._verificacion = verificacion

	def get_data(self, path: str) -> bytes:
		with open(path, "rb") as archivo:
			datos = archivo.read()
		if str(path).endswith(".py"):
			self._verificacion.comprobar(path, datos)
		return datos

	def get_code(self, fullname: str) -> types.CodeType:
		ruta = self.get_filename(fullname)
		return self.source_to_code(self.get_data(ruta), ruta)

	def set_data(self, *_args: Any, **_kwargs: Any) -> None:
		return None


class CargadorExtensionVerificado(importlib.machinery.ExtensionFileLoader):
	"""Una ``.pyd`` no se puede cargar desde bytes: se comprueba su suma justo antes de ``create_module``."""

	def __init__(self, fullname: str, path: str, verificacion: _Verificacion) -> None:
		super().__init__(fullname, path)
		self._verificacion = verificacion

	def create_module(self, spec: Any) -> Any:
		with open(self.path, "rb") as archivo:
			self._verificacion.comprobar(self.path, archivo.read())
		return super().create_module(spec)


def _spec_archivo(nombre: str, ruta: Path, verificacion: _Verificacion, paquete: bool) -> Any:
	if ruta.suffix == ".pyd":
		cargador_modulo: Any = CargadorExtensionVerificado(nombre, str(ruta), verificacion)
	else:
		cargador_modulo = CargadorVerificado(nombre, str(ruta), verificacion)
	ubicaciones = [str(ruta.parent)] if paquete else None
	return importlib.util.spec_from_file_location(nombre, ruta, loader=cargador_modulo, submodule_search_locations=ubicaciones)


def _buscar_en(carpeta: Path, partes: list[str]) -> tuple[Path, bool] | None:
	base_ruta = carpeta.joinpath(*partes) if partes else carpeta
	if (base_ruta / "__init__.py").is_file():
		return base_ruta / "__init__.py", True
	if partes:
		if base_ruta.with_suffix(".py").is_file():
			return base_ruta.with_suffix(".py"), False
		for pyd in base_ruta.parent.glob(base_ruta.name + "*.pyd"):
			return pyd, False
	return None


class BuscadorComplemento(importlib.abc.MetaPathFinder):
	"""Resuelve ``zcplugins.<id codificado>`` y sus submódulos (también los que se importan tarde)."""

	def __init__(self, prefijo: str, carpeta: Path, verificacion: _Verificacion) -> None:
		self.prefijo = prefijo
		self.carpeta = carpeta
		self.verificacion = verificacion

	def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
		if fullname != self.prefijo and not fullname.startswith(self.prefijo + "."):
			return None
		partes = fullname[len(self.prefijo):].lstrip(".").split(".") if fullname != self.prefijo else []
		encontrado = _buscar_en(self.carpeta, [p for p in partes if p])
		if encontrado is None:
			return None
		ruta, paquete = encontrado
		return _spec_archivo(fullname, ruta, self.verificacion, paquete)


class BuscadorLib(importlib.abc.MetaPathFinder):
	"""Bibliotecas vendorizadas en ``lib/`` que se importan por su nombre (mutagen, dulwich).

	Va al FINAL de ``sys.meta_path``: solo resuelve los nombres de nivel superior que
	hay en su ``lib/`` y nunca tapa la biblioteca estándar ni el código de zCommander.
	"""

	def __init__(self, carpeta_lib: Path, verificacion: _Verificacion) -> None:
		self.carpeta = carpeta_lib
		self.verificacion = verificacion
		self.nombres = {p.stem.split(".")[0] if p.is_file() else p.name for p in carpeta_lib.iterdir()
			if (p.is_dir() and (p / "__init__.py").is_file()) or p.suffix in (".py", ".pyd")}

	def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
		partes = fullname.split(".")
		if partes[0] not in self.nombres:
			return None
		encontrado = _buscar_en(self.carpeta, partes)
		if encontrado is None:
			return None
		ruta, paquete = encontrado
		return _spec_archivo(fullname, ruta, self.verificacion, paquete)


def _paquete_raiz() -> None:
	if PAQUETE_RAIZ not in sys.modules:
		modulo = types.ModuleType(PAQUETE_RAIZ)
		modulo.__path__ = []  # type: ignore[attr-defined]
		sys.modules[PAQUETE_RAIZ] = modulo


# ── Cargador ─────────────────────────────────────────────────────────────────


class Cargador:
	"""Complementos de esta sesión: descubrimiento, confianza y activación."""

	def __init__(self, config: Any = None, *, modo_seguro: bool = False, desarrollo: Path | None = None,
			carpeta_serie: Path | None = None, carpeta_usuario: Path | None = None,
			carpeta_centinelas: Path | None = None) -> None:
		from app.core import paths

		self.config = config
		self.modo_seguro = modo_seguro
		self.desarrollo = Path(desarrollo) if desarrollo else None
		self.modo_desarrollo = bool(desarrollo) or bool(self._config("complementos.modo_desarrollo", False))
		self.carpeta_serie = Path(carpeta_serie) if carpeta_serie else paths.ruta_plugins_serie()
		self._carpeta_usuario = Path(carpeta_usuario) if carpeta_usuario else None
		self._carpeta_centinelas = Path(carpeta_centinelas) if carpeta_centinelas else None
		self.tiempo_carga_s = TIEMPO_CARGA_S
		self._futuros: dict[str, Future] = {}
		self._cadenas: dict[str, tuple[str, ...]] = {}
		self._instancias: dict[str, Any] = {}
		self._anfitriones: dict[str, Any] = {}
		self._orden_activacion: list[str] = []
		self._congelado = False
		self._cerrado = False
		self._hilo: ThreadPoolExecutor | None = None
		self._buscadores: list[Any] = []
		self.centinelas: list[str] = []
		self.sin_aceptar: list[str] = []
		self.tiempos: dict[str, float] = {}
		#: Lo aplicado al reiniciar (instalaciones, actualizaciones, desinstalaciones): sus
		#: ``al_instalar`` y ``al_desinstalar`` se ejecutan tras mostrar la ventana (3.10).
		self.aplicados: list[Any] = []
		#: La interfaz pregunta por los centinelas y los sin aceptar (no se anuncian en ``avisos_arranque``).
		self.preguntas_en_interfaz = False
		self._pendientes: dict[str, Any] = {}
		modulo_estado.fijar_fallos_maximos(int(self._config("complementos.fallos_maximos", 3)))
		modulo_estado.fijar_al_quedar_fuera(self._quedar_fuera)

	# ── Configuración y carpetas ────────────────────────────────────────────

	def _config(self, clave: str, defecto: Any) -> Any:
		if self.config is None:
			return defecto
		try:
			return self.config.obtener(clave)
		except Exception:  # noqa: BLE001 - una configuración falsa o sin la clave da el valor por defecto
			log.debug("Sin la clave %s", clave, exc_info=True)
			return defecto

	@property
	def carpeta_usuario(self) -> Path:
		if self._carpeta_usuario is None:
			from app.core import paths

			self._carpeta_usuario = paths.ruta_plugins_usuario()
		return self._carpeta_usuario

	@property
	def carpeta_centinelas(self) -> Path:
		if self._carpeta_centinelas is None:
			from app.core import paths

			self._carpeta_centinelas = paths.ruta_cache_plugins() / "cargando"
		self._carpeta_centinelas.mkdir(parents=True, exist_ok=True)
		return self._carpeta_centinelas

	def _claves_json(self) -> dict:
		from app.core import paths

		ruta = paths.ruta_config_plugins() / "claves.json"
		try:
			datos = json.loads(ruta.read_text(encoding="utf-8"))
			return datos if isinstance(datos, dict) else {}
		except FileNotFoundError:
			return {}
		except (OSError, ValueError):
			log.warning("No se pudo leer %s", ruta, exc_info=True)
			return {}

	# ── Descubrir (3.4, pasos 2 a 5) ────────────────────────────────────────

	def descubrir(self) -> None:
		"""Centinelas, descubrimiento, confianza y registro de marcadores (sin importar código)."""
		if self.modo_seguro:
			log.info("Modo seguro: no se registra ningún complemento")
			return
		self.centinelas = self._leer_centinelas()
		try:
			from app.plugins import paquetes

			self._pendientes = paquetes.pendientes() if self._carpeta_usuario is None else {}
		except Exception:  # noqa: BLE001 - sin pendientes legibles se arranca igual
			log.warning("No se pudieron leer los cambios pendientes de los complementos", exc_info=True)
			self._pendientes = {}
		inhabilitados = set(self._config("complementos.inhabilitados", []) or [])
		candidatos: dict[str, tuple[Path, manifiesto.Manifiesto, str]] = {}
		with registro.lote():
			for ubicacion, origen in ((self.carpeta_serie, "serie"), (self.carpeta_usuario, "usuario")):
				for ruta, datos in registro.descubrir_carpeta(ubicacion):
					if not isinstance(datos, manifiesto.Manifiesto):
						registro.anotar_error(ruta, datos)
						continue
					origen_real = origen
					if origen == "serie" and serie.SERIE.get(datos.id) != datos.version:
						origen_real = "suelto"  # en la carpeta del programa sin estar en la lista de serie (3.2)
					anterior = candidatos.get(datos.id)
					if anterior is not None:
						# Gana la versión más alta, pero una copia de data/plugins que no pasa la
						# comprobación de confianza nunca sustituye a la de serie (3.2).
						if not _mayor(datos.version, anterior[1].version):
							continue
						if origen != "serie" and self._confianza(ruta, datos)[0] != EstadoComplemento.REGISTRADO:
							log.warning("%s en %s no sustituye a la versión de %s: no pasa la comprobación de confianza",
								datos.id, ruta, anterior[0])
							continue
					candidatos[datos.id] = (ruta, datos, origen_real)
			if self.desarrollo is not None:
				try:
					datos = manifiesto.leer(self.desarrollo)
					candidatos[datos.id] = (self.desarrollo, datos, "desarrollo")
				except manifiesto.ErrorManifiesto as error:
					registro.anotar_error(self.desarrollo, error.problemas)
			for ruta, datos, origen in candidatos.values():
				self._registrar(ruta, datos, origen, inhabilitados)
		if self.modo_desarrollo:
			registro.fijar_modo_desarrollo(True)

	def _registrar(self, ruta: Path, datos: manifiesto.Manifiesto, origen: str, inhabilitados: set[str]) -> registro.Registrado:
		from app.plugins import api

		estado_inicial, motivo, confianza = EstadoComplemento.REGISTRADO, "", ""
		sumas: dict[str, str] | None = None
		suma_aceptada = ""
		if origen == "serie":
			confianza = _("Oficial")
			sumas = (serie.SUMAS or {}).get(datos.id) if serie.SUMAS is not None else None
		elif origen == "desarrollo":
			confianza = _("En desarrollo")
		else:
			estado_inicial, motivo, confianza, sumas, suma_aceptada = self._confianza(ruta, datos)
			if origen == "suelto":
				motivo = motivo or _("Este complemento está en la carpeta del programa y se borrará al actualizar zCommander; instálelo desde el gestor")
		if estado_inicial == EstadoComplemento.REGISTRADO and not manifiesto.compatible(datos, api.API_VERSION, api.API_COMPATIBLE_DESDE):
			estado_inicial = EstadoComplemento.INCOMPATIBLE
			motivo = _("Incompatible: necesita la API {v}").format(v=datos.api_minima)
		if estado_inicial == EstadoComplemento.REGISTRADO and datos.id in inhabilitados:
			estado_inicial = EstadoComplemento.INHABILITADO
		if estado_inicial == EstadoComplemento.REGISTRADO and datos.id in self.centinelas:
			estado_inicial = EstadoComplemento.INHABILITADO
			motivo = _("zCommander se cerró mientras cargaba este complemento")
		if estado_inicial == EstadoComplemento.SIN_ACEPTAR:
			self.sin_aceptar.append(datos.id)
		registrado = registro.registrar(datos, ruta, "serie" if origen == "serie" else origen, estado_inicial, motivo, confianza)
		registrado.sumas = sumas
		registrado.suma_aceptada = suma_aceptada
		registrado.pendiente = self._pendientes.get(datos.id, registrado.pendiente)
		return registrado

	def registrar_carpeta(self, carpeta: Path, origen: str = "usuario") -> registro.Registrado | None:
		"""Registra los marcadores de un complemento recién instalado sin reiniciar (3.10) [interfaz].

		Pasa por la misma comprobación de confianza que al arrancar. ``None`` si el
		manifiesto no vale (queda anotado como error).
		"""
		try:
			datos = manifiesto.leer(Path(carpeta))
		except manifiesto.ErrorManifiesto as error:
			registro.anotar_error(Path(carpeta), error.problemas)
			return None
		inhabilitados = set(self._config("complementos.inhabilitados", []) or [])
		return self._registrar(Path(carpeta), datos, origen, inhabilitados)

	def _confianza(self, ruta: Path, datos: manifiesto.Manifiesto) -> tuple[EstadoComplemento, str, str, dict | None, str]:
		"""Firma, clave fijada o consentimiento de un complemento que no es de serie (3.9)."""
		claves = self._claves_json()
		por_id = claves.get("por_id", {}) if isinstance(claves.get("por_id"), dict) else {}
		confiadas = [str(c) for c in claves.get("confiadas", []) or []]
		reservado = datos.id.startswith("zc.")
		declarada = firma.leer_declaracion(ruta)
		if declarada is not None:
			if datos.id in por_id:
				lista = [por_id[datos.id]]
			elif reservado:
				lista = list(firma.CLAVES_PROYECTO)
			else:
				lista = [*firma.CLAVES_PROYECTO, *confiadas]
			resultado = firma.verificar_complemento(ruta, lista, comprobar_sumas=False)
			if resultado.valida:
				oficial = resultado.clave in firma.CLAVES_PROYECTO
				texto = _("Oficial") if oficial else _("Firmado por un autor de confianza")
				return EstadoComplemento.REGISTRADO, "", texto, resultado.archivos, ""
			if datos.id in por_id or reservado:
				return (EstadoComplemento.ERROR_MANIFIESTO, _("El complemento {n} ya no lleva la firma de su autor; no se carga").format(n=datos.nombre),
					_("Sin firma"), None, "")
		elif datos.id in por_id:
			return (EstadoComplemento.ERROR_MANIFIESTO, _("El complemento {n} ya no lleva la firma de su autor; no se carga").format(n=datos.nombre),
				_("Sin firma"), None, "")
		if reservado:
			return EstadoComplemento.ERROR_MANIFIESTO, _("Los id zc.* están reservados a los complementos oficiales"), _("Sin firma"), None, ""
		if not self._config("complementos.permitir_sin_firma", True):
			return EstadoComplemento.INHABILITADO, _("Los complementos sin firma no están permitidos"), _("Sin firma"), None, ""
		confiados = self._config("complementos.confiados", {}) or {}
		if datos.id in confiados:
			return EstadoComplemento.REGISTRADO, "", _("Sin firma"), None, str(confiados[datos.id])
		return EstadoComplemento.SIN_ACEPTAR, _("Sin firma y sin aceptar"), _("Sin firma"), None, ""

	# ── Centinelas (3.8) ────────────────────────────────────────────────────

	def _ruta_centinela(self, id_complemento: str) -> Path:
		return self.carpeta_centinelas / manifiesto.codificar(id_complemento)

	def _leer_centinelas(self) -> list[str]:
		ids = []
		for archivo in sorted(self.carpeta_centinelas.iterdir()):
			if archivo.is_file():
				ids.append(archivo.name.replace("__", "."))
				log.warning("Centinela de un cierre brusco durante la carga de %s", ids[-1])
				try:
					archivo.unlink()
				except OSError:
					log.warning("No se pudo borrar el centinela %s", archivo, exc_info=True)
		return ids

	def _crear_centinela(self, id_complemento: str) -> None:
		try:
			self._ruta_centinela(id_complemento).write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
		except OSError:
			log.warning("No se pudo crear el centinela de %s", id_complemento, exc_info=True)

	def _borrar_centinela(self, id_complemento: str) -> None:
		try:
			self._ruta_centinela(id_complemento).unlink(missing_ok=True)
		except OSError:
			log.warning("No se pudo borrar el centinela de %s", id_complemento, exc_info=True)

	# ── Estado y consultas ──────────────────────────────────────────────────

	def estado(self, id_complemento: str) -> EstadoComplemento | None:
		return registro.estado(id_complemento)

	def instancia(self, id_complemento: str) -> Any:
		return self._instancias.get(id_complemento)

	def anfitrion(self, id_complemento: str) -> Any:
		return self._anfitriones.get(id_complemento)

	def activos(self) -> list[tuple[str, Any]]:
		"""(id, instancia) de los activos, en orden de activación."""
		return [(i, self._instancias[i]) for i in self._orden_activacion if i in self._instancias]

	@property
	def congelado(self) -> bool:
		return self._congelado or self._cerrado

	def _quedar_fuera(self, id_complemento: str, motivo: str) -> None:
		def aplicar() -> None:
			if registro.estado(id_complemento) == EstadoComplemento.ACTIVO:
				registro.fijar_estado(id_complemento, EstadoComplemento.FALLIDO, _("Fuera de uso por errores"))
				log.error("El complemento %s queda fuera de uso en esta sesión (%s)", id_complemento, motivo)

		planificar(aplicar)

	# ── Activación (3.4) ────────────────────────────────────────────────────

	def asegurar_activo(self, id_complemento: str) -> Future:
		"""Futuro que se resuelve con verdadero cuando el complemento está activo [cualquiera]."""
		if hay_planificador() and not en_hilo_interfaz():
			intermedio: Future = Future()

			def en_interfaz() -> None:
				real = self._asegurar(id_complemento, ())
				real.add_done_callback(lambda f: _copiar_futuro(f, intermedio))

			planificar(en_interfaz)
			return intermedio
		return self._asegurar(id_complemento, ())

	def _resuelto(self, valor: bool) -> Future:
		futuro: Future = Future()
		futuro.set_result(valor)
		return futuro

	def _asegurar(self, id_complemento: str, cadena: tuple[str, ...]) -> Future:
		registrado = registro.complemento(id_complemento)
		if registrado is None:
			return self._resuelto(False)
		if self.congelado:
			log.info("Activación de %s descartada: zCommander se está cerrando", id_complemento)
			return self._resuelto(False)
		if id_complemento in cadena:
			ciclo = [*cadena[cadena.index(id_complemento):], id_complemento]
			texto = _("Dependencia circular entre {a}").format(a=" y ".join(registro.nombres(ciclo[:-1])))
			log.error(texto)
			for miembro in ciclo[:-1]:
				registro.fijar_estado(miembro, EstadoComplemento.FALLIDO, texto)
			return self._resuelto(False)
		if registrado.estado == EstadoComplemento.ACTIVO:
			return self._resuelto(True)
		if registrado.estado in NO_USABLES:
			return self._resuelto(False)
		if registrado.estado == EstadoComplemento.CARGANDO and id_complemento in self._futuros:
			return self._futuros[id_complemento]
		futuro: Future = Future()
		self._futuros[id_complemento] = futuro
		self._cadenas[id_complemento] = cadena
		registro.fijar_estado(id_complemento, EstadoComplemento.CARGANDO)
		dependencias = [manifiesto.id_de_requisito(r) for r in registrado.manifiesto.requiere_complementos]
		if not dependencias:
			self._cargar(registrado)
			return futuro
		pendientes = {"n": len(dependencias), "fallida": None}

		def dependencia_resuelta(nombre: str, resultado: Future) -> None:
			ok = not resultado.cancelled() and resultado.exception() is None and bool(resultado.result())
			if not ok and pendientes["fallida"] is None:
				pendientes["fallida"] = nombre
			pendientes["n"] -= 1
			if pendientes["n"] > 0:
				return
			if pendientes["fallida"] is not None:
				actual = registro.complemento(id_complemento)
				motivo = actual.motivo if actual and actual.estado == EstadoComplemento.FALLIDO and "circular" in actual.motivo else \
					_("Falta el complemento {b}, que {a} necesita").format(b=pendientes["fallida"], a=registrado.nombre)
				self._fallar(id_complemento, motivo)
				return
			self._cargar(registrado)

		for dependencia in dependencias:
			resultado = self._asegurar(dependencia, (*cadena, id_complemento))
			if resultado.done():
				dependencia_resuelta(dependencia, resultado)
			else:
				resultado.add_done_callback(lambda f, d=dependencia: planificar(lambda: dependencia_resuelta(d, f)))
		return futuro

	def _fallar(self, id_complemento: str, motivo: str, *, reintentable: bool = True) -> None:
		registro.fijar_estado(id_complemento, EstadoComplemento.FALLIDO, motivo)
		registrado = registro.complemento(id_complemento)
		if registrado is not None:
			registrado.reintentable = reintentable
		log.error("El complemento %s no se pudo activar: %s", id_complemento, motivo)
		self._resolver(id_complemento, False)

	def _resolver(self, id_complemento: str, valor: bool) -> None:
		futuro = self._futuros.pop(id_complemento, None)
		self._cadenas.pop(id_complemento, None)
		if futuro is not None and not futuro.done():
			futuro.set_result(valor)

	def _hilo_cargador(self) -> ThreadPoolExecutor:
		if self._hilo is None:
			self._hilo = ThreadPoolExecutor(1, thread_name_prefix="zc-cargador")
		return self._hilo

	def _cargar(self, registrado: registro.Registrado) -> None:
		id_complemento = registrado.id
		inicio = time.perf_counter()
		self._crear_centinela(id_complemento)
		if not hay_planificador():
			try:
				clase = self._importar(registrado)
				error = None
			except BaseException as fallo:  # noqa: BLE001 - se trata abajo
				clase, error = None, fallo
			self._tras_importar(registrado, clase, error, inicio)
			return
		ficha = {"hecho": False}
		candado = threading.Lock()

		def trabajo() -> None:
			try:
				clase = self._importar(registrado)
				error = None
			except BaseException as fallo:  # noqa: BLE001 - se trata en la interfaz
				clase, error = None, fallo
			with candado:
				if ficha["hecho"]:
					return
				ficha["hecho"] = True
			planificar(lambda: self._tras_importar(registrado, clase, error, inicio))

		def agotado() -> None:
			with candado:
				if ficha["hecho"]:
					return
				ficha["hecho"] = True

			def en_interfaz() -> None:
				log.error("El complemento %s tarda demasiado en cargarse; se abandona su hilo", id_complemento)
				self._hilo = None  # el hilo colgado se abandona; la carga siguiente usa otro
				self._borrar_centinela(id_complemento)
				self._fallar(id_complemento, _("El complemento {n} tarda demasiado en cargarse").format(n=registrado.nombre),
					reintentable=False)

			planificar(en_interfaz)

		temporizador = threading.Timer(self.tiempo_carga_s, agotado)
		temporizador.daemon = True
		temporizador.start()
		self._hilo_cargador().submit(trabajo)

	def _importar(self, registrado: registro.Registrado) -> type:
		"""Pasos 2 y 3 de 3.4 (hilo del cargador): sumas e importación verificada."""
		sumas = registrado.sumas
		if sumas is not None:
			actuales = firma.sumas_archivos(registrado.carpeta)
			if actuales != sumas:
				raise _ArchivosCambiados(_("Los archivos del complemento {n} han cambiado desde que se instaló").format(n=registrado.nombre))
		elif registrado.suma_aceptada:
			actual = firma.suma_paquete(registrado.carpeta, registrado.id, registrado.manifiesto.version)
			if actual != registrado.suma_aceptada:
				raise _SinAceptar(_("El complemento {n} ha cambiado desde que lo aceptó").format(n=registrado.nombre))
			sumas = firma.sumas_archivos(registrado.carpeta)
		_paquete_raiz()
		nombre = f"{PAQUETE_RAIZ}.{registrado.manifiesto.codificado}"
		verificacion = _Verificacion(registrado.id, registrado.carpeta, sumas)
		buscador = BuscadorComplemento(nombre, registrado.carpeta, verificacion)
		sys.meta_path.insert(0, buscador)
		self._buscadores.append(buscador)
		lib = registrado.carpeta / "lib"
		if lib.is_dir():
			buscador_lib = BuscadorLib(lib, verificacion)
			sys.meta_path.append(buscador_lib)
			self._buscadores.append(buscador_lib)
		modulo_nombre, clase_nombre = registrado.manifiesto.entrada.split(":", 1)
		paquete = importlib.import_module(nombre)
		modulo = paquete if modulo_nombre in ("", "__init__") else importlib.import_module(f"{nombre}.{modulo_nombre}")
		clase = getattr(modulo, clase_nombre)
		return clase

	def _tras_importar(self, registrado: registro.Registrado, clase: Any, error: BaseException | None, inicio: float) -> None:
		"""Paso 4 y 5 de 3.4, en el hilo de la interfaz."""
		from app.plugins import api

		id_complemento = registrado.id
		try:
			if self._cerrado:
				return
			if registro.estado(id_complemento) != EstadoComplemento.CARGANDO:
				return
			if isinstance(error, _SinAceptar):
				registro.fijar_estado(id_complemento, EstadoComplemento.SIN_ACEPTAR, str(error))
				self.sin_aceptar.append(id_complemento)
				self._resolver(id_complemento, False)
				return
			if error is not None:
				modulo_estado.registrar_fallo(id_complemento, _("cargarse"), error, definitivo=True)
				self._fallar(id_complemento, str(error) if isinstance(error, _ArchivosCambiados) else _("Falló al cargar"))
				return
			try:
				instancia = clase()
				instancia.id = id_complemento
				instancia.carpeta = registrado.carpeta
				anfitrion = api.Anfitrion(id_complemento, registrado.carpeta, permisos=registrado.manifiesto.permisos)
				self._anfitriones[id_complemento] = anfitrion
				instancia.activar(anfitrion)
			except BaseException as fallo:  # noqa: BLE001 - el primer fallo en activar() deja el complemento fuera de uso
				modulo_estado.registrar_fallo(id_complemento, _("activarse"), fallo, definitivo=True)
				self._fallar(id_complemento, _("Falló al activarse"))
				return
			self._instancias[id_complemento] = instancia
			self._orden_activacion.append(id_complemento)
			registrado.tiempo_carga = time.perf_counter() - inicio
			self.tiempos[id_complemento] = registrado.tiempo_carga
			registro.fijar_estado(id_complemento, EstadoComplemento.ACTIVO)
			log.info("Complemento %s activado en %.0f ms", id_complemento, registrado.tiempo_carga * 1000)
			_sonar("plugin.activado")
			self._resolver(id_complemento, True)
		finally:
			self._borrar_centinela(id_complemento)

	# ── Arranque, cierre y tareas ───────────────────────────────────────────

	def activar_al_arrancar(self) -> None:
		"""Activa uno a uno los complementos con ``al_arrancar`` y engancha los ``evento:<nombre>``."""
		from app.services import eventos

		for registrado in registro.complementos():
			if registrado.estado != EstadoComplemento.REGISTRADO:
				continue
			for disparador in registrado.manifiesto.activacion:
				if disparador == "al_arrancar":
					self.asegurar_activo(registrado.id)
				elif disparador.startswith("evento:"):
					nombre = disparador.split(":", 1)[1]
					eventos.bus().suscribir(nombre, lambda id_=registrado.id, nombre_=nombre, **datos:
						self._activar_por_evento(id_, nombre_, datos))

	def _activar_por_evento(self, id_complemento: str, nombre: str, datos: dict[str, Any]) -> None:
		"""Activa el complemento con su evento y, al quedar activo, le entrega ese mismo evento (3.4).

		Cuando el bus entregó el evento, el complemento aún no se había suscrito (lo hace en
		``activar()``): sin esto, por ejemplo, la nota de la primera carpeta no se anunciaría.
		La entrega va solo a las funciones de ese complemento, nunca a las de los demás.
		"""
		if registro.estado(id_complemento) == EstadoComplemento.ACTIVO:
			return  # ya suscrito: el bus se lo entrega solo
		futuro = self.asegurar_activo(id_complemento)

		def entregar(resultado: Future) -> None:
			try:
				ok = not resultado.cancelled() and resultado.exception() is None and bool(resultado.result())
			except Exception:  # noqa: BLE001 - cancelado al cerrar: no hay nada que entregar
				ok = False
			if ok:
				registro.entregar_evento(id_complemento, nombre, dict(datos))

		# La continuación solo se publica: nunca corre dentro de set_result (3.4).
		futuro.add_done_callback(lambda f: planificar(lambda: entregar(f)))

	def avisos_arranque(self) -> list[str]:
		"""Textos que la ventana anuncia tras mostrarse (14.8, paso 11).

		Con la interfaz de PL (``preguntas_en_interfaz``), los centinelas y los
		complementos sin aceptar no se anuncian aquí: se PREGUNTA por cada uno
		(``app/ui/acciones/complementos_pl.py``, tras ``al_arrancar``). Sin ella, se dicen.
		"""
		if self.preguntas_en_interfaz:
			return []
		textos = [_("zCommander se cerró mientras cargaba el complemento {n}.").format(n=n) for n in registro.nombres(self.centinelas)]
		textos += [_("Hay un complemento sin firma que no se instaló desde zCommander: {n}.").format(n=n)
			for n in registro.nombres(self.sin_aceptar)]
		return textos

	# ── Modo desarrollo y prueba ─────────────────────────────────────────────

	def recargar(self, id_complemento: str | None = None) -> Future:
		"""Vuelve a cargar el complemento de la carpeta de desarrollo (``complemento_recargar``, 3.12) [interfaz].

		Desactiva el anterior (protegido), olvida sus módulos ``zcplugins``, vuelve a
		leer su manifiesto y lo activa otra vez. El futuro dice si quedó activo.
		"""
		carpeta = self.desarrollo
		if carpeta is None:
			return self._resuelto(False)
		try:
			datos = manifiesto.leer(carpeta)
		except manifiesto.ErrorManifiesto as error:
			log.error("No se puede recargar %s: %s", carpeta, error)
			return self._resuelto(False)
		id_complemento = id_complemento or datos.id
		self._olvidar(id_complemento)
		registro.quitar(id_complemento)
		self._registrar(carpeta, datos, "desarrollo", set())
		modulo_estado.olvidar(id_complemento)
		return self.asegurar_activo(id_complemento)

	def _olvidar(self, id_complemento: str) -> None:
		"""Desactiva un complemento activo y quita sus módulos y buscadores (recargar)."""
		instancia = self._instancias.pop(id_complemento, None)
		if instancia is not None:
			modulo_estado.llamar_protegido(id_complemento, instancia.desactivar)
		self._anfitriones.pop(id_complemento, None)
		if id_complemento in self._orden_activacion:
			self._orden_activacion.remove(id_complemento)
		prefijo = f"{PAQUETE_RAIZ}.{manifiesto.codificar(id_complemento)}"
		for nombre in [m for m in sys.modules if m == prefijo or m.startswith(prefijo + ".")]:
			del sys.modules[nombre]
		for buscador in [b for b in self._buscadores if getattr(b, "prefijo", "") == prefijo]:
			self._buscadores.remove(buscador)
			if buscador in sys.meta_path:
				sys.meta_path.remove(buscador)

	def activar_ahora(self, id_complemento: str) -> bool:
		"""Activa en ESTE hilo, sin planificador (``--comprobar-arranque --complemento-prueba``, 14.8).

		Solo para la prueba de un complemento: allí el bucle de eventos aún no corre.
		"""
		registrado = registro.complemento(id_complemento)
		if registrado is None:
			return False
		if registrado.estado == EstadoComplemento.ACTIVO:
			return True
		if registrado.estado != EstadoComplemento.REGISTRADO:
			return False
		for requisito in registrado.manifiesto.requiere_complementos:
			if not self.activar_ahora(manifiesto.id_de_requisito(requisito)):
				self._fallar(id_complemento, _("Falta el complemento {b}, que {a} necesita").format(b=requisito, a=registrado.nombre))
				return False
		futuro: Future = Future()
		self._futuros[id_complemento] = futuro
		registro.fijar_estado(id_complemento, EstadoComplemento.CARGANDO)
		inicio = time.perf_counter()
		self._crear_centinela(id_complemento)
		try:
			clase, error = self._importar(registrado), None
		except BaseException as fallo:  # noqa: BLE001 - se trata abajo
			clase, error = None, fallo
		self._tras_importar(registrado, clase, error, inicio)
		return registro.estado(id_complemento) == EstadoComplemento.ACTIVO

	def ejecutar_tarea_programada(self, id: str, al_terminar: Callable[[int], None]) -> None:
		"""Activa ``zc.programador`` y llama a su ``ejecutar_tarea`` exportada [interfaz]; 2 si no la exporta."""
		futuro = self.asegurar_activo("zc.programador")

		def continuar() -> None:
			exportado = registro.exportados("zc.programador") or {}
			funcion = exportado.get("ejecutar_tarea")
			if funcion is None:
				log.warning("zc.programador no exporta ejecutar_tarea: la tarea %s no se ejecuta", id)
				al_terminar(2)
				return
			lanzada = {"ok": False}

			def llamar() -> None:
				funcion(id, al_terminar)
				lanzada["ok"] = True

			modulo_estado.llamar_protegido("zc.programador", llamar)
			if not lanzada["ok"]:
				al_terminar(2)

		futuro.add_done_callback(lambda _f: planificar(continuar))

	def congelar(self) -> None:
		"""Desde aquí no empieza ninguna activación ni corre ninguna continuación (cierre, 3.4)."""
		self._congelado = True

	def descongelar(self) -> None:
		self._congelado = False

	def cerrar(self) -> None:
		"""Descarta lo que llegue, despierta a quien espera con ``Cancelado`` y borra los centinelas en curso."""
		from app.services.vfs.base import Cancelado

		self._cerrado = True
		with _candado_plan:
			_plan["cerrado"] = True
		for id_complemento, futuro in list(self._futuros.items()):
			self._borrar_centinela(id_complemento)
			if not futuro.done():
				futuro.set_exception(Cancelado(_("zCommander se está cerrando")))
		self._futuros.clear()
		for buscador in self._buscadores:
			if buscador in sys.meta_path:
				sys.meta_path.remove(buscador)
		if self._hilo is not None:
			self._hilo.shutdown(wait=False, cancel_futures=True)


class _ArchivosCambiados(Exception):
	pass


class _SinAceptar(Exception):
	pass


def _sonar(evento: str) -> None:
	try:
		from app.services.sonidos import servicio

		servicio.sonar(evento)
	except Exception:  # noqa: BLE001 - un sonido nunca impide activar un complemento
		log.debug("No se pudo pedir el sonido %s", evento, exc_info=True)


def _copiar_futuro(origen: Future, destino: Future) -> None:
	if destino.done():
		return
	if origen.cancelled():
		destino.cancel()
	elif origen.exception() is not None:
		destino.set_exception(origen.exception())
	else:
		destino.set_result(origen.result())


def _mayor(a: str, b: str) -> bool:
	try:
		return tuple(int(x) for x in a.split(".")) > tuple(int(x) for x in b.split("."))
	except ValueError:
		return False


# ── Instancia de la sesión ───────────────────────────────────────────────────

_actual: list[Cargador | None] = [None]


def actual() -> Cargador | None:
	return _actual[0]


def fijar_actual(cargador: Cargador | None) -> None:
	from app.services.vfs import resolver

	_actual[0] = cargador
	# Una dirección «papelera://», «nube://»... activa el complemento que declara ese [[esquemas]].
	resolver.fijar_activador_esquemas(activar_por_esquema if cargador is not None else None)


def activar_por_esquema(prefijo: str) -> bool:
	"""[cualquiera] Activa el complemento cuyo ``[[esquemas]]`` declara ``prefijo``; verdadero si quedó activo.

	Desde un hilo de trabajo (``abrir_ruta`` de la sesión, Ir a la carpeta, el
	historial) espera la activación como manda 3.4. En el hilo de la interfaz nunca
	espera: pide la activación y devuelve falso salvo que ya haya terminado (sin
	planificador, como en las pruebas, la carga es síncrona).
	"""
	id_complemento = registro.complemento_de_esquema(prefijo)
	if id_complemento is None:
		return False
	futuro = asegurar_activo(id_complemento)
	try:
		if futuro.done():
			return bool(futuro.result())
		if hay_planificador() and en_hilo_interfaz():
			log.info("Dirección %s:// pedida en la interfaz: se activa %s en segundo plano", prefijo, id_complemento)
			return False
		return bool(futuro.result(TIEMPO_CARGA_S))
	except Exception:  # noqa: BLE001 - agotado o cancelado: la dirección no se puede abrir
		log.info("No se pudo activar %s para abrir %s://", id_complemento, prefijo, exc_info=True)
		return False


def asegurar_activo(id_complemento: str) -> Future:
	"""``asegurar_activo`` del cargador de la sesión; resuelto con falso si no hay cargador."""
	cargador = _actual[0]
	if cargador is None:
		futuro: Future = Future()
		futuro.set_result(False)
		return futuro
	return cargador.asegurar_activo(id_complemento)


def arrancar(config: Any, modo_seguro: bool, desarrollo: Path | None) -> Cargador:
	"""Paso 8 de 14.8: pendientes, modo seguro, centinelas, descubrimiento y marcadores (3.4)."""
	from app.plugins import auditoria, paquetes

	aplicados: list = []
	try:
		aplicados = paquetes.aplicar_pendientes(config)
	except Exception:  # noqa: BLE001 - un pendiente roto nunca impide arrancar
		log.exception("No se pudieron aplicar los cambios pendientes de los complementos")
	cargador = Cargador(config, modo_seguro=modo_seguro, desarrollo=desarrollo)
	cargador.aplicados = aplicados
	registro.fijar_modo_desarrollo(cargador.modo_desarrollo)
	cargador.descubrir()
	if config is not None and not modo_seguro:
		auditoria.desde_configuracion(config)
	fijar_actual(cargador)
	modulo_estado.iniciar_vigilante()
	return cargador
