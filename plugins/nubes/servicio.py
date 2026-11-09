# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lógica del complemento Nubes sin wx (diseño 2.0, 12): motor, cuentas, altas y funciones.

``Nubes`` reúne el motor rclone, las cuentas, el catálogo y las funciones que
usan las órdenes y las ventanas. Todo lo que habla con rclone bloquea: se llama
desde hilos de trabajo (``zc.tareas``) u operaciones (``zc.lanzar``), nunca
desde el hilo de la interfaz.

Altas de cuentas (12.5; rclone.md 5.1 y 5.2): ``Alta`` sigue el protocolo «sin
interacción» de ``config/create``: cada pregunta de rclone vuelve como un
``Paso`` con su ``Option`` (tipo, ejemplos, si es contraseña) para que la
interfaz la presente con el control que toca; la autorización OAuth usa
``config_auth_no_browser`` y ``config/oauthstatus`` (la URL la abre o la copia la
persona) y se cancela con ``config/oauthstop``.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.plugins import api

from . import errores, locales
from .cliente_rc import ClienteRC, ErrorTrabajo, esperar
from .cuentas import AlmacenCuentas, Catalogo, Cuenta, Servicio, aportaciones_de_complementos
from .motor import ConfiguracionCifrada, Motor, RutasMotor
from .proveedor import FalloLote, ProveedorRclone, ruta_local_rclone, ruta_remota

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

#: Tiempo máximo de una autorización OAuth en el navegador (12.5).
TIEMPO_OAUTH_S = 600
ESTADO_CONECTADA = "Conectada"
ESTADO_RECONECTAR = "Volver a autorizar"
ESTADO_SIN_COMPROBAR = "Sin comprobar"
ESTADO_RECONFIGURAR = "Volver a configurar"
#: Codificación de nombres de las carpetas cifradas según el servicio de debajo (rclone.md 4.10).
CODIFICACION_CRYPT = {"drive": "base64", "onedrive": "base32768", "dropbox": "base32768", "box": "base32768"}
#: Modos de caché del montaje (``vfs_cache_mode``).
MODOS_CACHE = ("off", "minimal", "writes", "full")
TIPOS_SERVIR = ("webdav", "sftp", "http", "dlna")


def texto_estado(estado: str) -> str:
	return {ESTADO_CONECTADA: _("Conectada"), ESTADO_RECONECTAR: _("Volver a autorizar"),
		ESTADO_SIN_COMPROBAR: _("Sin comprobar"), ESTADO_RECONFIGURAR: _("Volver a configurar")}.get(estado, estado)


def tamano(n: Any) -> str:
	try:
		return api.formato.tamano_legible(int(n))
	except (TypeError, ValueError):
		return "?"


def limite_rclone(subida_kib: int, bajada_kib: int) -> str:
	"""Límite «SUBIDA:BAJADA» de rclone en KiB/s; vacío si no hay ninguno."""
	if subida_kib <= 0 and bajada_kib <= 0:
		return ""
	subida = f"{subida_kib}k" if subida_kib > 0 else "off"
	bajada = f"{bajada_kib}k" if bajada_kib > 0 else "off"
	return f"{subida}:{bajada}"


# ── Pasos de un alta ──────────────────────────────────────────────────────────


@dataclass
class Paso:
	"""Lo que la interfaz tiene que hacer ahora en un alta.

	``tipo``: «pregunta» (``opcion`` con la ``Option`` de rclone), «oauth» (``url``
	que abrir o copiar) o «fin».
	"""

	tipo: str
	opcion: dict[str, Any] = field(default_factory=dict)
	estado: str = ""
	error: str = ""
	url: str = ""

	@property
	def nombre(self) -> str:
		return str(self.opcion.get("Name", ""))

	@property
	def es_contrasena(self) -> bool:
		return bool(self.opcion.get("IsPassword"))

	@property
	def es_token(self) -> bool:
		return self.nombre == "config_token"

	@property
	def ejemplos(self) -> list[tuple[str, str]]:
		return [(str(e.get("Value", "")), str(e.get("Help", "") or e.get("Value", ""))) for e in self.opcion.get("Examples") or []]

	@property
	def exclusiva(self) -> bool:
		return bool(self.opcion.get("Exclusive")) and bool(self.ejemplos)

	@property
	def es_booleana(self) -> bool:
		return str(self.opcion.get("Type", "")).lower() == "bool"

	@property
	def defecto(self) -> str:
		valor = self.opcion.get("DefaultStr", self.opcion.get("Default", ""))
		return "" if valor is None else str(valor)

	@property
	def ayuda(self) -> str:
		return str(self.opcion.get("Help", "")).strip()

	def orden_authorize(self) -> str:
		"""La orden ``rclone authorize ...`` que rclone propone para autorizar desde otro equipo."""
		for linea in self.ayuda.splitlines():
			linea = linea.strip().strip("`")
			if linea.startswith("rclone authorize"):
				return linea
		return ""


class Alta:
	"""Alta (o reconexión) de una cuenta con el protocolo sin interacción de rclone.

	Uso desde un hilo::

		paso = alta.empezar(cancelacion)
		while paso.tipo != "fin":
			if paso.tipo == "oauth": (la interfaz abre o copia paso.url) paso = alta.esperar(cancelacion)
			else: paso = alta.responder(valor, cancelacion)
	"""

	def __init__(self, nubes: Nubes, id: str, tipo: str, parametros: dict[str, str], *, reconectar: bool = False,
			preparar: Callable[[], dict[str, str]] | None = None) -> None:
		self._nubes = nubes
		self.id = id
		self.tipo = tipo
		self.parametros = dict(parametros)
		self.reconectar = reconectar
		#: Respuestas que hay que calcular hablando con rclone (en el hilo, al empezar).
		self._preparar = preparar
		self._jobid = 0
		self._oauth_visto = False
		self.preguntas: list[str] = []

	def _lanzar(self, ruta: str, parametros: dict[str, Any], cancelacion: Any) -> Paso:
		cliente = self._nubes.cliente()
		self._oauth_visto = False
		self._jobid = cliente.llamar_asincrono(ruta, **parametros)
		return self.esperar(cancelacion, devolver_oauth=True)

	def empezar(self, cancelacion: Any = None) -> Paso:
		if self._preparar is not None:
			self.parametros.update(self._preparar())
		opt = {"nonInteractive": True, "obscure": True}
		if self.reconectar:
			return self._lanzar("config/update", {"name": self.id, "parameters": self.parametros, "opt": opt}, cancelacion)
		return self._lanzar("config/create", {"name": self.id, "type": self.tipo, "parameters": self.parametros, "opt": opt},
			cancelacion)

	def responder(self, resultado: str, paso: Paso, cancelacion: Any = None) -> Paso:
		"""Responde a una pregunta y sigue el alta.

		Las respuestas ``config_*`` de rclone son efímeras (no se guardan en
		``rclone.conf``): si no se reenvían en cada ``continue``, rclone vuelve a
		preguntar si hay navegador (``config_is_local``) e incluso intenta abrirlo él
		mismo (``config_auth_no_browser``). Por eso cada continuación lleva todos los
		parámetros del alta.
		"""
		self.preguntas.append(paso.nombre)
		opt = {"nonInteractive": True, "obscure": True, "continue": True, "state": paso.estado, "result": resultado}
		return self._lanzar("config/update", {"name": self.id, "parameters": dict(self.parametros), "opt": opt}, cancelacion)

	def esperar(self, cancelacion: Any = None, *, devolver_oauth: bool = False, tiempo_max_s: float = TIEMPO_OAUTH_S) -> Paso:
		"""Sigue el trabajo en curso hasta una pregunta, la URL de OAuth (si ``devolver_oauth``) o el final."""
		cliente = self._nubes.cliente()
		inicio = time.monotonic()
		while True:
			if _cancelado(cancelacion):
				self.cancelar()
				raise api.Cancelado(_("Autorización cancelada"))
			estado = cliente.llamar("job/status", jobid=self._jobid)
			if estado.get("finished"):
				if not estado.get("success", False):
					raise errores.traducir(errores.ErrorRC(500, str(estado.get("error", "")), "config/create"), self.id)
				salida = estado.get("output") or {}
				if salida.get("Error") and not salida.get("State"):
					raise errores.traducir(errores.ErrorRC(500, str(salida["Error"]), "config/create"), self.id)
				if salida.get("State"):
					return Paso("pregunta", opcion=dict(salida.get("Option") or {}), estado=str(salida["State"]),
						error=str(salida.get("Error") or ""))
				return Paso("fin")
			if devolver_oauth and not self._oauth_visto:
				try:
					oauth = cliente.llamar("config/oauthstatus")
				except errores.ErrorRC:
					oauth = {}
				if oauth.get("status") == "running" and oauth.get("authUrl"):
					self._oauth_visto = True
					return Paso("oauth", url=str(oauth["authUrl"]))
			if time.monotonic() - inicio > tiempo_max_s:
				self.cancelar()
				raise api.ErrorRed(_("No se recibió la autorización a tiempo"))
			esperar(cancelacion, 0.3)

	def cancelar(self) -> None:
		cliente = self._nubes.motor.cliente_si_vivo()
		if cliente is None:
			return
		try:
			cliente.llamar("config/oauthstop")
		except (errores.ErrorRC, api.ErrorArchivos):
			log.debug("No había autorización OAuth en curso", exc_info=True)
		if self._jobid:
			cliente.parar(self._jobid)


def _cancelado(cancelacion: Any) -> bool:
	cancelacion = getattr(cancelacion, "token", cancelacion)
	esta = getattr(cancelacion, "is_set", None)
	return bool(esta()) if callable(esta) else False


# ── Nubes ──────────────────────────────────────────────────────────────────────


class Nubes:
	"""Estado del complemento en la sesión: motor, cuentas, catálogo y proveedores."""

	def __init__(self, zc: Any, carpeta: Path, *, lanzar: Callable | None = None, terminar: Callable | None = None,
			soltar: Callable | None = None) -> None:
		self.zc = zc
		self.carpeta = Path(carpeta)
		self.rutas = RutasMotor.desde_anfitrion(zc.datos, zc.cache)
		self.cuentas = AlmacenCuentas(Path(zc.datos) / "cuentas.json")
		self._catalogo: Catalogo | None = None
		self.configuracion = ConfiguracionCifrada(self.rutas.config, self.ejecutable, self._ejecutar_programa, zc.secretos)
		self.motor = Motor(ejecutable=self.ejecutable, rutas=self.rutas, configuracion=self.configuracion,
			lanzar=lanzar or self._lanzar, terminar=terminar or self._terminar, soltar=soltar or self._soltar,
			opciones=self.opciones_motor, al_detenerse=self._al_detenerse)
		self._estados: dict[str, str] = {}
		self._carpetas: tuple[float, list[locales.CarpetaNube]] | None = None
		self._hilo_carpetas: threading.Thread | None = None
		self._duplicados_avisados: set[tuple[str, str]] = set()
		self._candado = threading.RLock()
		self.limites_pausados = False
		self.reinicio_pendiente = False

	# Configuración -----------------------------------------------------------

	def opcion(self, clave: str, defecto: Any = None) -> Any:
		try:
			return self.zc.config.obtener(clave, defecto)
		except Exception:  # noqa: BLE001 - sin configuración (pruebas), el valor de fábrica
			log.debug("Sin configuración para %s", clave, exc_info=True)
			return defecto

	def opciones_motor(self) -> dict[str, Any]:
		horario = str(self.opcion("horario_limites", "") or "").strip()
		limite = horario or limite_rclone(int(self.opcion("limite_subida_kib", 0) or 0), int(self.opcion("limite_bajada_kib", 0) or 0))
		return {"transferencias": int(self.opcion("transferencias", 4) or 4), "reintentos": int(self.opcion("reintentos", 3)),
			"registro_detallado": bool(self.opcion("registro_detallado", False)), "bwlimit": limite}

	@property
	def catalogo(self) -> Catalogo:
		if self._catalogo is None:
			raices = [self.carpeta.parent, Path(self.zc.datos).parents[2] / "plugins"]
			self._catalogo = Catalogo.cargar(self.carpeta / "recursos" / "servicios.json", aportaciones_de_complementos(raices))
		return self._catalogo

	# Procesos ---------------------------------------------------------------

	def ejecutable(self) -> Path:
		"""``rclone.exe`` pedido en cada uso al catálogo de componentes (6.3)."""
		return Path(self.zc.componentes.ejecutable("rclone", "rclone.exe"))

	def _ejecutar_programa(self, argumentos: list[str], *, entrada: bytes = b"", tiempo_s: float = 60) -> Any:
		return self.zc.ejecutar_programa(argumentos, entrada=entrada, tiempo_s=tiempo_s)

	def _procesos(self) -> Any:
		if "ejecutar_programas" not in getattr(self.zc, "permisos", ()):
			raise api.NoAdmitido(_("El complemento no declaró el permiso «ejecutar_programas»"))
		# El rcd es un proceso largo: va por procesos.popen (Job anidado en el global, 14.9).
		return api.procesos

	def _lanzar(self, argumentos: list[str], entorno: dict[str, str]) -> Any:
		import subprocess

		return self._procesos().popen(argumentos, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
			env=entorno, cwd=str(self.rutas.temp))

	def _terminar(self, proceso: Any) -> None:
		self._procesos().terminar_arbol(proceso)

	def _soltar(self, proceso: Any) -> None:
		self._procesos().gestor().soltar(proceso)

	def _al_detenerse(self) -> None:
		self.zc.sonidos.sonar("motor_detenido")
		self.zc.anunciar(_("El motor de nubes se ha detenido; se volverá a arrancar al usarlo"), api.RESULTADO)

	# Llamadas -----------------------------------------------------------------

	def cliente(self) -> ClienteRC:
		cliente = self.motor.cliente()
		if self.configuracion.aviso:
			aviso, self.configuracion.aviso = self.configuracion.aviso, ""
			self.zc.anunciar(aviso, api.ESENCIAL)
		return cliente

	def llamar(self, ruta: str, *, nombre: str = "", **parametros: Any) -> dict:
		"""Llamada síncrona con los errores traducidos."""
		try:
			return self.cliente().llamar(ruta, **parametros)
		except errores.ErrorRC as error:
			raise errores.traducir(error, nombre) from error
		except api.ErrorRed:
			if not self.motor.vivo():
				raise api.ErrorRed(_("El motor de nubes se ha detenido")) from None
			raise

	def ejecutar(self, ruta: str, *, cancelacion: Any = None, progreso: Callable[[int, int], None] | None = None,
			conservar_salida: bool = False, grupo: str = "", al_stats: Callable[[dict], None] | None = None,
			**parametros: Any) -> dict:
		"""Trabajo asíncrono (``_async`` + ``_group``) con progreso y cancelación; devuelve su ``output``."""
		cliente = self.cliente()
		grupo = grupo or f"zc-{uuid.uuid4().hex[:12]}"
		limite_cuenta = self._limite_por_archivo(parametros)
		if limite_cuenta:
			config = dict(parametros.get("_config") or {})
			config.setdefault("BwLimitFile", limite_cuenta)
			parametros["_config"] = config

		def adaptar(hechos: int, total: int, _velocidad: float) -> None:
			if progreso is not None:
				progreso(hechos, total)

		try:
			jobid = cliente.llamar_asincrono(ruta, grupo, **parametros)
			if al_stats is not None:
				return self._esperar_con_stats(cliente, jobid, grupo, al_stats, cancelacion)
			return cliente.esperar_trabajo(jobid, grupo, adaptar, cancelacion)
		except errores.ErrorRC as error:
			raise errores.traducir(error) from error
		except ErrorTrabajo as error:
			traducido = errores.traducir(errores.ErrorRC(500, error.texto, ruta))
			if conservar_salida:
				raise FalloLote(traducido, error.salida) from error
			raise traducido from error
		except api.ErrorRed:
			if not self.motor.vivo():
				raise api.ErrorRed(_("El motor de nubes se ha detenido")) from None
			raise

	def _esperar_con_stats(self, cliente: ClienteRC, jobid: int, grupo: str, al_stats: Callable[[dict], None], cancelacion: Any) -> dict:
		while True:
			if _cancelado(cancelacion):
				cliente.parar(jobid, grupo)
				raise api.Cancelado()
			estado = cliente.llamar("job/status", jobid=jobid)
			try:
				al_stats(cliente.llamar("core/stats", group=grupo))
			except errores.ErrorRC:
				log.debug("Sin estadísticas de %s", grupo, exc_info=True)
			if estado.get("finished"):
				try:
					cliente.llamar("core/stats-delete", group=grupo)
				except (errores.ErrorRC, api.ErrorArchivos):
					log.debug("No se pudo borrar el grupo %s", grupo, exc_info=True)
				if not estado.get("success", False):
					raise ErrorTrabajo(str(estado.get("error", "")), estado.get("output") or {})
				salida = estado.get("output")
				return salida if isinstance(salida, dict) else {}
			esperar(cancelacion, 0.25)

	def _limite_por_archivo(self, parametros: dict[str, Any]) -> str:
		"""Límite propio de la cuenta implicada (``BwLimitFile`` de la llamada, por transferencia)."""
		if self.limites_pausados:
			return ""
		texto = " ".join(str(parametros.get(c, "")) for c in ("fs", "srcFs", "dstFs", "path1", "path2"))
		for cuenta in self.cuentas.lista():
			if f"{cuenta.id}:" in texto:
				limite = cuenta.horario_limites.strip() or limite_rclone(cuenta.limite_subida_kib, cuenta.limite_bajada_kib)
				if limite:
					return limite
		return ""

	# Cuentas y proveedores -------------------------------------------------------

	def cuenta(self, id: str) -> Cuenta:
		cuenta = self.cuentas.obtener(id)
		if cuenta is None:
			raise api.NoEncontrado(_("No existe la cuenta de nube {n}").format(n=id), f"nube://{id}/")
		return cuenta

	def proveedor(self, cuenta: Cuenta) -> api.Proveedor:
		if cuenta.volver_a_configurar:
			raise api.ErrorAcceso(_("Hay que volver a configurar la cuenta {n}: Cuentas de nube, Volver a autorizar").format(
				n=cuenta.nombre), cuenta.direccion)
		if cuenta.motor == "webdav":
			from .webdav import ProveedorWebDAV

			return ProveedorWebDAV.de_cuenta(self, cuenta)
		return ProveedorRclone(self, cuenta)

	def fabrica_nube(self, direccion: str) -> tuple[api.Proveedor, str]:
		"""``nube://<cuenta>/ruta`` → (proveedor, ruta). No hace E/S: rcd arranca en el primer ``listar``."""
		resto = direccion.split("://", 1)[1] if "://" in direccion else direccion
		id_cuenta, _barra, ruta = resto.partition("/")
		if not id_cuenta:
			raise api.NoEncontrado(_("Falta el nombre de la cuenta en la dirección {d}").format(d=direccion), direccion)
		cuenta = self.cuenta(id_cuenta)
		ruta = "/" + ruta.strip("/")
		if ruta == "/" and cuenta.carpeta_inicial.strip("/"):
			ruta = "/" + cuenta.carpeta_inicial.strip("/")
		return self.proveedor(cuenta), ruta

	def avisar_duplicados(self, cuenta: Cuenta, nombre: str, veces: int) -> None:
		clave = (cuenta.id, nombre)
		with self._candado:
			if clave in self._duplicados_avisados:
				return
			self._duplicados_avisados.add(clave)
		self.zc.anunciar(_("Hay {v} elementos con el mismo nombre: {n}. Puede resolverlo con Buscar nombres duplicados").format(
			v=veces, n=nombre), api.RESULTADO)

	def unidades(self) -> list[api.UnidadVirtual]:
		"""Cada cuenta en Alt+F1 y Alt+F2, con su espacio si el motor ya está en marcha (sin arrancarlo por esto)."""
		unidades = []
		vivo = self.motor.vivo()
		for cuenta in self.cuentas.lista():
			servicio = self.catalogo.servicio(cuenta.servicio)
			descripcion = servicio.nombre if servicio is not None else self._nombre_servicio(cuenta)
			if cuenta.volver_a_configurar:
				descripcion += ", " + _("hay que volver a configurarla")
			elif vivo and cuenta.motor == "rclone":
				try:
					datos = self.motor.cliente().llamar("operations/about", fs=cuenta.remoto, tiempo_s=5)
					if datos.get("free") is not None and datos.get("total") is not None:
						descripcion = _("{l} libres de {t}").format(l=tamano(datos["free"]), t=tamano(datos["total"]))
				except (errores.ErrorRC, api.ErrorArchivos):
					log.debug("Sin espacio de %s para el selector", cuenta.id, exc_info=True)
			unidades.append(api.UnidadVirtual(cuenta.nombre, cuenta.direccion, descripcion))
		for carpeta in self.carpetas_visibles():
			# Una ruta local: el selector la abre como un disco más, sin rclone ni credenciales.
			unidades.append(api.UnidadVirtual(carpeta.nombre, carpeta.ruta, _("carpeta del programa oficial, {r}").format(
				r=carpeta.ruta)))
		return unidades

	# Carpetas de los programas oficiales -------------------------------------------

	def _detectar_carpetas(self) -> None:
		try:
			carpetas = locales.carpetas_de_nube()
		except Exception:  # noqa: BLE001 - la detección nunca rompe el selector ni el asistente
			log.warning("No se pudieron buscar las carpetas de los programas de nube", exc_info=True)
			carpetas = []
		with self._candado:
			self._carpetas = (time.monotonic(), list(carpetas))

	def asegurar_deteccion(self) -> threading.Thread:
		"""Empieza (si no está en marcha) la búsqueda de carpetas en un hilo propio; una sola a la vez."""
		with self._candado:
			if self._hilo_carpetas is None or not self._hilo_carpetas.is_alive():
				self._hilo_carpetas = threading.Thread(target=self._detectar_carpetas, daemon=True, name="zc-nubes-carpetas")
				self._hilo_carpetas.start()
			return self._hilo_carpetas

	def carpetas_en_cache(self) -> list[locales.CarpetaNube] | None:
		"""Las carpetas detectadas hace menos de ``VIGENCIA_CARPETAS_S``; ``None`` si hay que volver a buscarlas."""
		with self._candado:
			if self._carpetas is not None and time.monotonic() - self._carpetas[0] < VIGENCIA_CARPETAS_S:
				return list(self._carpetas[1])
		return None

	def olvidar_carpetas(self) -> None:
		with self._candado:
			self._carpetas = None

	def carpetas_locales(self, espera_s: float | None = None) -> list[locales.CarpetaNube]:
		"""Las carpetas de los programas oficiales de este equipo (nunca lanza). BLOQUEA: llamar desde un hilo.

		Se recuerdan ``VIGENCIA_CARPETAS_S`` segundos para no repetir la búsqueda entre
		el asistente, Google Drive y el selector. Con ``espera_s`` se espera como mucho
		ese tiempo; si la búsqueda no ha terminado, se devuelve la última conocida (o
		ninguna) y la búsqueda sigue en su hilo para la próxima vez.
		"""
		vigentes = self.carpetas_en_cache()
		if vigentes is not None:
			return vigentes
		self.asegurar_deteccion().join(espera_s)
		with self._candado:
			return list(self._carpetas[1]) if self._carpetas is not None else []

	def carpetas_visibles(self) -> list[locales.CarpetaNube]:
		"""Las que salen en el selector de unidades: con la opción activada y sin las que la persona ocultó.

		Espera como mucho ``ESPERA_SELECTOR_S``: las fuentes del selector van una tras
		otra y una ruta de red lenta no debe retrasar las demás.
		"""
		if not bool(self.opcion("carpetas_programas", True)):
			return []
		ocultas = {str(r) for r in (self.opcion("carpetas_ocultas", []) or [])}
		return [c for c in self.carpetas_locales(ESPERA_SELECTOR_S) if c.clave not in ocultas]

	def carpetas_por_revisar(self, carpetas: list[locales.CarpetaNube]) -> list[locales.CarpetaNube]:
		"""Las detectadas que el asistente todavía no ha enseñado a la persona."""
		vistas = {str(r) for r in (self.opcion("carpetas_vistas", []) or [])}
		return [c for c in carpetas if c.clave not in vistas]

	def guardar_carpetas(self, detectadas: list[locales.CarpetaNube], marcadas: list[locales.CarpetaNube]) -> None:
		"""Guarda qué carpetas se muestran: las no marcadas se ocultan y todas quedan como ya revisadas."""
		elegidas = {c.clave for c in marcadas}
		ocultas = {str(r) for r in (self.opcion("carpetas_ocultas", []) or [])}
		ocultas = (ocultas - elegidas) | {c.clave for c in detectadas if c.clave not in elegidas}
		vistas = {str(r) for r in (self.opcion("carpetas_vistas", []) or [])} | {c.clave for c in detectadas}
		cambios: dict[str, Any] = {"carpetas_ocultas": sorted(ocultas), "carpetas_vistas": sorted(vistas)}
		if elegidas:
			cambios["carpetas_programas"] = True
		self._guardar_config(cambios)

	def mostrar_carpeta(self, carpeta: locales.CarpetaNube, detectadas: list[locales.CarpetaNube]) -> None:
		"""Muestra una carpeta en el selector sin cambiar las demás.

		Si la persona había desactivado las carpetas de los programas, se activan
		pero se ocultan todas las otras: solo sale la que acaba de elegir.
		"""
		ocultas = {str(r) for r in (self.opcion("carpetas_ocultas", []) or [])} - {carpeta.clave}
		vistas = {str(r) for r in (self.opcion("carpetas_vistas", []) or [])} | {carpeta.clave}
		cambios: dict[str, Any] = {}
		if not bool(self.opcion("carpetas_programas", True)):
			ocultas |= {c.clave for c in detectadas if c.clave != carpeta.clave}
			vistas |= {c.clave for c in detectadas}
			cambios["carpetas_programas"] = True
		cambios.update({"carpetas_ocultas": sorted(ocultas), "carpetas_vistas": sorted(vistas)})
		self._guardar_config(cambios)

	def _guardar_config(self, cambios: dict[str, Any]) -> None:
		try:
			self.zc.config.establecer_varias(cambios)
		except Exception:  # noqa: BLE001 - sin configuración (pruebas sueltas) no se recuerda la elección
			log.warning("No se pudo guardar la elección de carpetas de nube", exc_info=True)

	def _nombre_servicio(self, cuenta: Cuenta) -> str:
		if cuenta.cifrada_sobre:
			return _("Carpeta cifrada")
		if cuenta.union_de:
			return _("Unión de cuentas")
		return cuenta.servicio

	def nombre_servicio(self, cuenta: Cuenta) -> str:
		servicio = self.catalogo.servicio(cuenta.servicio)
		return servicio.nombre if servicio is not None else self._nombre_servicio(cuenta)

	def estado(self, cuenta: Cuenta) -> str:
		if cuenta.volver_a_configurar:
			return ESTADO_RECONFIGURAR
		return self._estados.get(cuenta.id, ESTADO_SIN_COMPROBAR)

	def comprobar(self, cuenta: Cuenta) -> dict[str, Any]:
		"""Comprueba la cuenta (``operations/about`` o listar la raíz) y deja su estado; devuelve el espacio si lo hay."""
		try:
			if cuenta.motor == "webdav":
				proveedor = self.proveedor(cuenta)
				espacio = proveedor.espacio_libre("/")
				proveedor.listar("/")
				self._estados[cuenta.id] = ESTADO_CONECTADA
				return {"free": espacio[0], "total": espacio[1]} if espacio else {}
			try:
				datos = self.llamar("operations/about", fs=cuenta.remoto, nombre=cuenta.nombre)
			except api.NoAdmitido:
				self.llamar("operations/list", fs=cuenta.remoto, remote="", opt={"noMimeType": True, "noModTime": True},
					nombre=cuenta.nombre)
				datos = {}
			self._estados[cuenta.id] = ESTADO_CONECTADA
			return datos
		except errores.ErrorReconectar:
			self._estados[cuenta.id] = ESTADO_RECONECTAR
			raise

	def texto_espacio(self, datos: dict[str, Any]) -> str:
		if not datos:
			return _("Este servicio no informa del espacio")
		partes = []
		if datos.get("used") is not None:
			partes.append(_("{u} usados").format(u=tamano(datos["used"])))
		if datos.get("free") is not None:
			partes.append(_("{l} libres").format(l=tamano(datos["free"])))
		if datos.get("total") is not None:
			partes.append(_("{t} en total").format(t=tamano(datos["total"])))
		if datos.get("trashed"):
			partes.append(_("{p} en la papelera").format(p=tamano(datos["trashed"])))
		return ", ".join(partes) or _("Este servicio no informa del espacio")

	def remotos(self) -> list[str]:
		return [str(r) for r in self.llamar("config/listremotes").get("remotes", []) or []]

	# Altas, reconexión y bajas -------------------------------------------------------

	def nueva_cuenta(self, servicio: Servicio, nombre: str, valores: dict[str, str], *, id: str = "") -> tuple[Cuenta, dict[str, str]]:
		"""Cuenta (sin guardar) y parámetros de rclone para ``config/create``."""
		id = id or self.cuentas.id_libre(nombre)
		parametros = dict(servicio.opciones)
		tipo = servicio.tipo
		valores = dict(valores)
		otro_equipo = valores.pop(OTRO_EQUIPO, "") == "true"
		if servicio.tipo == "kdrive" and valores.get("drive_id"):
			valores["drive_id"] = numero_unidad_kdrive(valores["drive_id"])
			if not valores["drive_id"].isdigit():
				raise api.ErrorArchivos(_("El número de la unidad kDrive tiene que ser solo cifras"))
		for clave, valor in valores.items():
			if clave == "tipo" and servicio.id == "otro":
				tipo = valor.strip()
				continue
			if valor not in ("", None):
				parametros[clave] = str(valor)
		if servicio.es_oauth:
			if otro_equipo:
				# Sin navegador en este equipo: rclone pide pegar lo que da «rclone authorize» en otro.
				parametros["config_is_local"] = "false"
				parametros.pop("config_auth_no_browser", None)
			else:
				parametros.setdefault("config_is_local", "true")
				parametros["config_auth_no_browser"] = "true"
		if servicio.tipo == "drive" and self.opcion("formato_docs", ""):
			parametros["export_formats"] = valores.get("export_formats") or str(self.opcion("formato_docs"))
		papelera = bool(self.opcion("papelera_por_defecto", True)) and servicio.papelera
		if servicio.tipo == "drive" and not papelera:
			parametros["use_trash"] = "false"
		cuenta = Cuenta(id=id, nombre=nombre, servicio=servicio.id, motor=servicio.motor, papelera=papelera,
			client_id_propio=bool(valores.get("client_id")),
			opciones={k: v for k, v in parametros.items() if not k.startswith("config_") and k not in _CLAVES_SECRETAS})
		if servicio.id == "otro":
			cuenta.opciones["tipo"] = tipo
		return cuenta, {"_tipo": tipo, **parametros}

	def alta(self, cuenta: Cuenta, parametros: dict[str, str]) -> Alta:
		tipo = parametros.pop("_tipo", "")
		return Alta(self, cuenta.id, tipo, parametros)

	def terminar_alta(self, cuenta: Cuenta, secretos: dict[str, str] | None = None) -> dict[str, Any]:
		"""Comprueba la cuenta recién creada, la guarda y devuelve su espacio. Si falla, borra el remoto."""
		try:
			datos = self.comprobar(cuenta)
		except api.ErrorArchivos:
			self.borrar_remoto(cuenta.id)
			raise
		for nombre, valor in (secretos or {}).items():
			if valor:
				self.zc.secretos.guardar(f"{cuenta.id}:{nombre}", valor)
		cuenta.volver_a_configurar = False
		self.cuentas.guardar(cuenta)
		self.limpiar_cache()
		return datos

	def borrar_remoto(self, id: str) -> None:
		try:
			self.llamar("config/delete", name=id)
		except api.ErrorArchivos:
			log.debug("No se pudo borrar el remoto %s", id, exc_info=True)

	def reconectar(self, cuenta: Cuenta) -> Alta:
		"""Volver a autorizar (rclone.md 5.4): ``config/update`` con ``config_refresh_token`` y el flujo OAuth.

		Lleva también las respuestas que no cambian lo que ya hay: en Google Drive sin
		identificador propio, seguir con el compartido y no cambiar la unidad
		compartida; en Jottacloud, la autenticación tradicional (el servicio de marca
		blanca lo vuelve a preguntar rclone) y el dispositivo y el punto de montaje que
		ya tiene la cuenta, leídos de su configuración: si no, rclone los dejaría en
		blanco y una cuenta de Sync o Backup pasaría a ver el Archivo.
		"""
		parametros = {"config_refresh_token": "true", "config_is_local": "true", "config_auth_no_browser": "true"}
		servicio = self.catalogo.servicio(cuenta.servicio)
		preparar = None
		if servicio is not None:
			parametros.update({k: v for k, v in servicio.opciones.items() if k in RESPUESTAS_RECONEXION})
			if servicio.tipo == "drive":
				parametros["config_change_team_drive"] = "false"
				if not cuenta.client_id_propio:
					parametros["config_shared_client_id"] = "true"
			if servicio.tipo == "jottacloud":
				preparar = lambda: self._dispositivo_jottacloud(cuenta.id)  # noqa: E731
		return Alta(self, cuenta.id, "", parametros, reconectar=True, preparar=preparar)

	def _dispositivo_jottacloud(self, id: str) -> dict[str, str]:
		"""Respuestas que conservan el dispositivo y el punto de montaje de una cuenta Jottacloud."""
		try:
			datos = self.llamar("config/get", name=id)
		except api.ErrorArchivos:
			log.debug("Sin configuración de %s; rclone preguntará el dispositivo", id, exc_info=True)
			return {}
		dispositivo = str(datos.get("device", "") or "")
		punto = str(datos.get("mountpoint", "") or "")
		if not dispositivo and not punto:
			return {"config_non_standard": "false"}
		respuestas = {"config_non_standard": "true"}
		if dispositivo:
			respuestas["config_device"] = dispositivo
		if punto:
			respuestas["config_mountpoint"] = punto
		return respuestas

	def limpiar_cache(self) -> None:
		try:
			self.llamar("fscache/clear")
		except api.ErrorArchivos:
			log.debug("fscache/clear falló", exc_info=True)

	def eliminar_cuenta(self, cuenta: Cuenta) -> None:
		"""Desconecta (revoca si el servicio lo permite), borra el remoto, sus secretos y la cuenta."""
		if cuenta.motor == "rclone" and not cuenta.volver_a_configurar:
			try:
				self._comando("config", ["disconnect", cuenta.remoto])
			except api.ErrorArchivos:
				log.info("No se pudo revocar la autorización de %s", cuenta.id, exc_info=True)
			self.borrar_remoto(cuenta.id)
		for nombre in ("client_secret", "contrasena", "pass"):
			try:
				self.zc.secretos.borrar(f"{cuenta.id}:{nombre}")
			except (KeyError, api.ErrorArchivos):
				log.debug("Sin secreto %s de %s", nombre, cuenta.id, exc_info=True)
		try:
			self.zc.secretos.borrar(f"webdav:{cuenta.id}:contrasena")
		except (KeyError, api.ErrorArchivos):
			log.debug("Sin contraseña WebDAV de %s", cuenta.id, exc_info=True)
		self.cuentas.quitar(cuenta.id)
		self._estados.pop(cuenta.id, None)
		self.limpiar_cache()

	def guardar_propiedades(self, cuenta: Cuenta, parametros_rclone: dict[str, str]) -> None:
		"""Guarda la cuenta y cambia en rclone las opciones del servicio que hayan cambiado."""
		if parametros_rclone and cuenta.motor == "rclone":
			self.llamar("config/update", name=cuenta.id, parameters=parametros_rclone, opt={"nonInteractive": True, "obscure": True})
			self.limpiar_cache()
		self.cuentas.guardar(cuenta)

	# Funciones de 12.6 ---------------------------------------------------------

	def _comando(self, comando: str, argumentos: list[str], opciones: dict[str, str] | None = None) -> str:
		"""Una orden de la CLI dentro del rcd (``core/command``) con la configuración y las rutas portables.

		``core/command`` vuelve a lanzar rclone SIN el ``--config`` de rcd (usaría el de
		``%APPDATA%``): se pasan siempre la configuración, la caché y los temporales de
		``data``. Las opciones de ``opt`` se escriben «--clave valor», así que las
		banderas sin valor (``--dry-run``) van en los argumentos.
		"""
		opt = {"config": str(self.rutas.config), "cache-dir": str(self.rutas.cache), "temp-dir": str(self.rutas.temp),
			**(opciones or {})}
		datos = self.llamar("core/command", command=comando, arg=argumentos, opt=opt)
		salida = errores.redactar(str(datos.get("result", "")))
		if datos.get("error"):
			raise errores.traducir(errores.ErrorRC(500, salida, f"core/command {comando}"))
		return salida

	def espacio(self, cuenta: Cuenta) -> str:
		return self.texto_espacio(self.comprobar(cuenta))

	def enlace(self, cuenta: Cuenta, ruta: str, caducidad: str = "", quitar: bool = False) -> str:
		parametros: dict[str, Any] = {"fs": cuenta.remoto, "remote": ruta_remota(ruta)}
		if caducidad:
			parametros["expire"] = caducidad
		if quitar:
			parametros["unlink"] = True
		datos = self.llamar("operations/publiclink", nombre=ruta, **parametros)
		return str(datos.get("url", ""))

	def vaciar_papelera(self, cuenta: Cuenta, cancelacion: Any = None) -> None:
		self.ejecutar("operations/cleanup", cancelacion=cancelacion, fs=cuenta.remoto)

	def duplicados(self, cuenta: Cuenta, ruta: str, modo: str = "list", simular: bool = True, por_contenido: bool = False) -> str:
		argumentos = []
		if simular and modo != "list":
			argumentos.append("--dry-run")
		if por_contenido:
			argumentos.append("--by-hash")
		return self._comando("dedupe", [*argumentos, modo, cuenta.remoto + ruta_remota(ruta)])

	def crear_cifrada(self, base: Cuenta, carpeta: str, nombre: str, contrasena: str, sal: str,
			cifrar_nombres: str = "standard") -> Cuenta:
		servicio_base = self.catalogo.servicio(base.servicio)
		codificacion = CODIFICACION_CRYPT.get(servicio_base.tipo if servicio_base else "", "base32")
		id = self.cuentas.id_libre(nombre)
		parametros = {"remote": base.remoto + ruta_remota(carpeta), "password": contrasena, "filename_encryption": cifrar_nombres,
			"directory_name_encryption": "true" if cifrar_nombres != "off" else "false", "filename_encoding": codificacion}
		if sal:
			parametros["password2"] = sal
		self.llamar("config/create", name=id, type="crypt", parameters=parametros, opt={"nonInteractive": True, "obscure": True})
		cuenta = Cuenta(id=id, nombre=nombre, servicio="crypt", cifrada_sobre=base.id, papelera=False,
			opciones={"remote": parametros["remote"], "filename_encryption": cifrar_nombres})
		self.cuentas.guardar(cuenta)
		self._estados[id] = ESTADO_SIN_COMPROBAR
		return cuenta

	def crear_union(self, nombre: str, cuentas: list[Cuenta], tipo: str = "union", politica: str = "mfs") -> Cuenta:
		id = self.cuentas.id_libre(nombre)
		if tipo == "combine":
			upstreams = " ".join(f"{c.id}={c.remoto}" for c in cuentas)
			parametros = {"upstreams": upstreams}
		else:
			upstreams = " ".join(c.remoto for c in cuentas)
			parametros = {"upstreams": upstreams, "create_policy": politica, "action_policy": "epall", "search_policy": "ff"}
		self.llamar("config/create", name=id, type=tipo, parameters=parametros, opt={"nonInteractive": True, "obscure": True})
		cuenta = Cuenta(id=id, nombre=nombre, servicio=tipo, union_de=[c.id for c in cuentas], papelera=False,
			opciones=dict(parametros))
		self.cuentas.guardar(cuenta)
		return cuenta

	# Montar y servir -----------------------------------------------------------

	def montar(self, cuenta: Cuenta, letra: str = "*", modo_cache: str = "writes", nombre_volumen: str = "",
			como_red: bool = False) -> str:
		if not winfsp_instalado():
			raise api.NoAdmitido(_("Para montar como letra de unidad hace falta WinFsp, que no está instalado"))
		punto = letra if letra == "*" else letra.rstrip(":\\").upper() + ":"
		parametros: dict[str, Any] = {"fs": cuenta.remoto, "mountPoint": punto, "vfs_cache_mode": modo_cache,
			"volname": nombre_volumen or cuenta.nombre}
		if como_red:
			parametros["network_mode"] = True
		datos = self.llamar("mount/mount", nombre=cuenta.nombre, **parametros)
		self._anotar_uso_winfsp()
		return str(datos.get("mountPoint", punto))

	def _anotar_uso_winfsp(self) -> None:
		"""La primera unidad montada con WinFsp: «Acerca de» muestra desde entonces su aviso de copyright (2.5)."""
		if self.opcion("aviso_winfsp_mostrado", False):
			return
		try:
			self.zc.config.establecer("aviso_winfsp_mostrado", True)
		except Exception:  # noqa: BLE001 - sin configuración (pruebas sueltas) el montaje sigue siendo válido
			log.warning("No se pudo anotar el uso de WinFsp", exc_info=True)

	def montajes(self) -> list[dict[str, str]]:
		cliente = self.motor.cliente_si_vivo()
		if cliente is None:
			return []
		try:
			datos = cliente.llamar("mount/listmounts", tiempo_s=3)
		except (errores.ErrorRC, api.ErrorArchivos):
			log.debug("Sin lista de montajes", exc_info=True)
			return []
		return [{"fs": str(m.get("Fs", "")), "punto": str(m.get("MountPoint", ""))} for m in datos.get("mountPoints") or []]

	def pendientes_subida(self, fs: str = "") -> int:
		"""Archivos en la cola de subida de los montajes (``vfs/queue``); sin ``fs``, de todos."""
		cliente = self.motor.cliente_si_vivo()
		if cliente is None:
			return 0
		if not fs:
			return sum(self.pendientes_subida(m["fs"]) for m in self.montajes() if m["fs"])
		try:
			datos = cliente.llamar("vfs/queue", tiempo_s=3, **({"fs": fs} if fs else {}))
		except (errores.ErrorRC, api.ErrorArchivos):
			return 0
		return len(datos.get("queue") or [])

	def desmontar(self, punto: str) -> None:
		self.llamar("mount/unmount", mountPoint=punto)

	def servir(self, tipo: str, fs: str, *, solo_local: bool = True, puerto: int = 0, usuario: str = "", contrasena: str = "",
			solo_lectura: bool = True) -> dict[str, str]:
		if tipo not in TIPOS_SERVIR:
			raise api.NoAdmitido(_("Protocolo no admitido: {t}").format(t=tipo))
		anfitrion = "127.0.0.1" if solo_local else "0.0.0.0"  # noqa: S104 - solo con la confirmación expresa de la persona
		from .motor import puerto_libre

		parametros: dict[str, Any] = {"type": tipo, "fs": fs, "addr": f"{anfitrion}:{puerto or puerto_libre()}",
			"read_only": solo_lectura}
		if tipo != "dlna":
			parametros["user"] = usuario
			parametros["pass"] = contrasena
		datos = self.llamar("serve/start", **parametros)
		return {"id": str(datos.get("id", "")), "addr": str(datos.get("addr", parametros["addr"]))}

	def servicios_activos(self) -> list[dict[str, str]]:
		cliente = self.motor.cliente_si_vivo()
		if cliente is None:
			return []
		try:
			datos = cliente.llamar("serve/list", tiempo_s=3)
		except (errores.ErrorRC, api.ErrorArchivos):
			return []
		resultado = []
		for servicio in datos.get("list") or []:
			parametros = servicio.get("params") or {}
			resultado.append({"id": str(servicio.get("id", "")), "addr": str(servicio.get("addr", "")),
				"tipo": str(parametros.get("type", "")), "fs": str(parametros.get("fs", ""))})
		return resultado

	def dejar_de_servir(self, id: str) -> None:
		self.llamar("serve/stop", id=id)

	# Límites de velocidad ------------------------------------------------------

	def alternar_limites(self) -> bool:
		"""Pausa o reanuda los límites globales con ``core/bwlimit``; devuelve verdadero si quedan pausados."""
		if self.limites_pausados:
			limite = self.opciones_motor()["bwlimit"] or "off"
			self.llamar("core/bwlimit", rate=limite)
			self.limites_pausados = False
		else:
			self.llamar("core/bwlimit", rate="off")
			self.limites_pausados = True
		return self.limites_pausados

	def aplicar_configuracion(self) -> str:
		"""Reinicia rcd si cambiaron las transferencias, el horario o los reintentos y no hay trabajo; dice qué pasó."""
		if not self.motor.vivo():
			return ""
		actuales = {k: v for k, v in self.opciones_motor().items()}
		if actuales == self.motor.opciones_arranque:
			return ""
		if self.motor.hay_trabajo():
			self.reinicio_pendiente = True
			return _("Los cambios del motor de nubes se aplicarán al terminar las transferencias en curso")
		self.motor.reiniciar()
		self.reinicio_pendiente = False
		return _("Motor de nubes reiniciado con la configuración nueva")

	# Sincronizar, emparejar, comprobar -------------------------------------------

	def fs_de(self, direccion: str) -> str:
		"""Texto de ``fs`` de rclone para una ruta local o una dirección ``nube://`` («C:/x» o «cuenta:ruta»)."""
		if direccion.startswith("nube://"):
			resto = direccion[len("nube://"):]
			id_cuenta, _barra, ruta = resto.partition("/")
			cuenta = self.cuenta(id_cuenta)
			if cuenta.motor != "rclone":
				raise api.NoAdmitido(_("Esta función necesita una cuenta de rclone; {n} es WebDAV nativo").format(n=cuenta.nombre))
			return cuenta.remoto + ruta_remota(ruta)
		if "://" in direccion:
			raise api.NoAdmitido(_("Esta función solo admite carpetas locales y cuentas de nube"))
		return ruta_local_rclone(os.path.abspath(direccion))


#: Clave de los valores del asistente: autorizar desde otro equipo (no va a rclone).
OTRO_EQUIPO = "_otro_equipo"
#: Segundos que se recuerdan las carpetas de los programas oficiales detectadas.
VIGENCIA_CARPETAS_S = 30.0
#: Lo que el selector de unidades espera como mucho a la búsqueda de carpetas.
ESPERA_SELECTOR_S = 1.5
#: Respuestas fijas de una ficha que también valen al volver a autorizar (no las que cambian la cuenta).
RESPUESTAS_RECONEXION = frozenset({"config_type"})


def unidad_kdrive_valida(texto: str) -> bool:
	"""Si el número (o la dirección) de una unidad kDrive da solo cifras."""
	return numero_unidad_kdrive(texto).isdigit()


def numero_unidad_kdrive(texto: str) -> str:
	"""El número de una unidad kDrive a partir del número o de la dirección web («.../kdrive/app/drive/456789/files»)."""
	texto = str(texto).strip()
	encontrado = re.search(r"/drive/(\d+)", texto)
	if encontrado:
		return encontrado.group(1)
	return texto


_CLAVES_SECRETAS = frozenset({"client_secret", "pass", "password", "password2", "secret_access_key", "key", "api_key", "2fa",
	"token", "otp_secret_key"})


def winfsp_instalado() -> bool:
	"""WinFsp: ``HKLM\\SOFTWARE\\WOW6432Node\\WinFsp`` (``InstallDir``) o ``winfsp-x64.dll`` en Archivos de programa (x86)."""
	try:
		import winreg

		for vista in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
			try:
				with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WinFsp", 0, winreg.KEY_READ | vista) as clave:
					carpeta, _tipo = winreg.QueryValueEx(clave, "InstallDir")
					if carpeta and os.path.isfile(os.path.join(str(carpeta), "bin", "winfsp-x64.dll")):
						return True
			except OSError:
				continue
	except ImportError:  # pragma: no cover - fuera de Windows
		return False
	programas = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
	return os.path.isfile(os.path.join(programas, "WinFsp", "bin", "winfsp-x64.dll"))
