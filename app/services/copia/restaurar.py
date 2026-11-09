# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Restaurar una copia (diseño 2.0, 7.6 y 7.7). Sin wx.

``aplicar`` es el único que escribe en ``data``; lo usan la restauración al
momento (partes «En el momento»), la pendiente al arrancar
(``pendiente.aplicar_pendiente``), la importación de un ``.zcperfil`` y la
vuelta atrás con la copia automática previa. Así las cuatro filtran y combinan
exactamente igual.

Reglas que cumple siempre:

- Solo escribe rutas que ``formato.incluye`` acepta para su parte, y nunca en
  ``data/plugins`` (los paquetes de complementos se ofrecen por la instalación
  normal tras arrancar) ni ``claves.json``.
- Las claves de confianza y ``seguridad.*`` de una copia se ignoran.
- Lo que hace ejecutar algo y no se marcó (``PlanRestauracion.excluidos``) no
  entra, y se conserva lo actual.
- Al combinar, las huellas de servidores solo entran si se aceptaron una a una.
- Una parte con una suma que no coincide no se restaura.
- Las preferencias de una copia de una versión anterior pasan antes por las
  migraciones de ``Configuracion`` (7.7); las desconocidas de una más nueva se
  conservan sin usarse.
"""

from __future__ import annotations

import builtins
import copy
import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import paths
from app.services.copia import cifrado, combinar, formato, rclone
from app.services.copia.crear import (
	archivos_de_parte,
	complementos_de_usuario,
	crear_automatica,
	leer_settings,
	secreto_de_parte,
)
from app.services.copia.ejecutables import id_de_config
from app.services.copia.formato import CopiaAbierta, ErrorContrasena, ErrorCopia, nombre_parte
from app.services.copia.pendiente import ResultadoRestauracion

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


MODOS = ("combinar", "sustituir")
CARPETA_POR_INSTALAR = "complementos_por_instalar"
PENDIENTES_INSTALAR = "pendientes.json"


@dataclass
class PlanRestauracion:
	"""Lo que la persona eligió: partes, modo, órdenes ejecutables marcadas y huellas aceptadas."""

	partes: list[str]
	modo: str = "combinar"
	#: Todos los ids de ``ejecutables.analizar`` que se le mostraron.
	ejecutables: set[str] = field(default_factory=set)
	marcados: set[str] = field(default_factory=set)
	huellas_aceptadas: set[str] = field(default_factory=set)
	#: Rutas de archivos que no se aplican (filas no marcadas de la vista previa de un perfil).
	archivos_excluidos: set[str] = field(default_factory=set)
	#: Dejar los paquetes de complementos de la copia para ofrecerlos tras arrancar.
	ofrecer_complementos: bool = True

	@property
	def excluidos(self) -> set[str]:
		return set(self.ejecutables) - set(self.marcados)

	@property
	def sustituir(self) -> bool:
		return self.modo == "sustituir"

	def a_dict(self) -> dict:
		return {"partes": list(self.partes), "modo": self.modo, "ejecutables": sorted(self.ejecutables),
			"marcados": sorted(self.marcados), "huellas_aceptadas": sorted(self.huellas_aceptadas),
			"archivos_excluidos": sorted(self.archivos_excluidos), "ofrecer_complementos": self.ofrecer_complementos}

	@classmethod
	def desde_dict(cls, datos: dict) -> PlanRestauracion:
		def conjunto(clave: str) -> set[str]:
			valor = datos.get(clave, [])
			return {str(v) for v in valor} if isinstance(valor, list) else set()

		partes = [p for p in datos.get("partes", []) if p in formato.PARTES] if isinstance(datos.get("partes"), list) else []
		modo = datos.get("modo") if datos.get("modo") in MODOS else "combinar"
		return cls(partes=partes, modo=modo, ejecutables=conjunto("ejecutables"), marcados=conjunto("marcados"),
			huellas_aceptadas=conjunto("huellas_aceptadas"), archivos_excluidos=conjunto("archivos_excluidos"),
			ofrecer_complementos=bool(datos.get("ofrecer_complementos", True)))


@dataclass
class ResultadoAplicar:
	partes: list[str] = field(default_factory=list)
	avisos: list[str] = field(default_factory=list)
	por_instalar: list[str] = field(default_factory=list)


def es_inmediata(partes: list[str]) -> bool:
	"""Todas las partes se aplican «En el momento» (las demás esperan a reiniciar, 7.6)."""
	restaurables = [p for p in partes if formato.PARTES[p].aplicacion != formato.EXTRAER]
	return bool(restaurables) and all(formato.PARTES[p].aplicacion == formato.MOMENTO for p in restaurables)


# ── Secretos ──────────────────────────────────────────────────────────────────

def necesita_contrasena(copia: CopiaAbierta, partes: list[str]) -> bool:
	"""La copia trae secretos con contraseña de alguna de las partes elegidas."""
	if copia.manifiesto.modo_secretos != "contrasena":
		return False
	nombres = copia.manifiesto.nombres_secretos
	return any(secreto_de_parte(n, p) for n in nombres for p in partes) or not nombres


def secretos_de_copia(copia: CopiaAbierta, contrasena: str | None) -> dict[str, str] | None:
	"""Los secretos descifrados (``None`` si no trae). ``ErrorContrasena`` si la contraseña no vale."""
	modo = copia.manifiesto.modo_secretos
	datos = copia.secretos_bin()
	if modo == "excluidos" or datos is None:
		return None
	if modo == "dpapi":
		return cifrado.desproteger_dpapi(datos, copia.manifiesto.datos)
	if not contrasena:
		raise ErrorContrasena(_("Escriba la contraseña de la copia."))
	return cifrado.descifrar(datos, contrasena, copia.manifiesto.datos)


# ── Utilidades de disco ───────────────────────────────────────────────────────

def _escribir(destino: Path, contenido: bytes) -> None:
	"""Escritura atómica: temporal en la misma carpeta y ``os.replace``."""
	destino.parent.mkdir(parents=True, exist_ok=True)
	temporal = destino.with_name(f"{destino.name}.{os.getpid()}-{threading.get_ident()}.tmp")
	try:
		with open(temporal, "wb") as salida:
			salida.write(contenido)
			salida.flush()
			os.fsync(salida.fileno())
		os.replace(temporal, destino)
	except OSError:
		temporal.unlink(missing_ok=True)
		raise


def _leer(ruta: Path) -> bytes | None:
	try:
		return ruta.read_bytes()
	except FileNotFoundError:
		return None


def _json(contenido: bytes | None) -> Any:
	if contenido is None:
		return None
	try:
		return json.loads(contenido.decode("utf-8-sig"))
	except (ValueError, UnicodeDecodeError):
		return None


def _serializar(datos: Any) -> bytes:
	return json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8")


# ── Valores de settings.json ──────────────────────────────────────────────────

def migrar_valores(valores: dict[str, Any], version_esquema: int) -> dict[str, Any]:
	"""Pasa valores «seccion.clave» de un esquema anterior por las migraciones de ``Configuracion`` (7.7)."""
	from app.core.configuracion import MIGRACIONES, VERSION_ESQUEMA

	if version_esquema >= VERSION_ESQUEMA:
		return dict(valores)
	anidado: dict[str, Any] = {}
	for clave, valor in valores.items():
		seccion, punto, nombre = clave.partition(".")
		if punto:
			anidado.setdefault(seccion, {})[nombre] = copy.deepcopy(valor)
	for version in range(max(1, version_esquema), VERSION_ESQUEMA):
		migracion = MIGRACIONES.get(version)
		if migracion is None:
			continue
		try:
			migracion(anidado)
		except Exception:  # noqa: BLE001 - una migración rota no impide restaurar el resto
			log.exception("Falló la migración %d de los valores de la copia", version)
	return {f"{s}.{c}": v for s, claves in anidado.items() if isinstance(claves, dict) for c, v in claves.items()}


def valores_a_aplicar(copia: CopiaAbierta, partes: list[str], plan: PlanRestauracion,
		actuales: dict[str, Any], respetar_fabrica: bool = True) -> dict[str, Any]:
	"""Valores que se escriben: migrados, sin claves prohibidas ni ejecutables no marcadas (7.2, 7.6).

	Al combinar solo cuentan los que difieren de los de fábrica (7.6); un perfil
	(``respetar_fabrica`` falso) aplica cada fila marcada aunque sea el de fábrica.
	"""
	from app.core.configuracion import VALORES_POR_DEFECTO

	fabrica = {f"{s}.{c}": v for s, claves in VALORES_POR_DEFECTO.items() for c, v in claves.items()}
	resultado: dict[str, Any] = {}
	for parte in partes:
		if parte not in ("preferencias", "teclas", "complementos"):
			continue
		de_copia = {k: v for k, v in migrar_valores(copia.valores(parte), copia.manifiesto.version_esquema).items()
			if formato.parte_de_clave(k) == parte}
		if plan.sustituir:
			for clave, valor in fabrica.items():
				if formato.parte_de_clave(clave) == parte and clave not in de_copia:
					de_copia[clave] = copy.deepcopy(valor)
		for clave, valor in de_copia.items():
			if f"clave:{clave}" in plan.excluidos:
				continue
			if respetar_fabrica and not plan.sustituir and clave in fabrica and combinar.iguales(fabrica[clave], valor):
				continue
			if clave in actuales and combinar.iguales(actuales[clave], valor):
				continue
			resultado[clave] = valor
	return resultado


def _escribir_settings(ruta_datos: Path, valores: dict[str, Any]) -> None:
	"""Antes de cargar la configuración (restauración pendiente): se edita el archivo directamente."""
	from app.core import almacen_json
	from app.core.configuracion import NOMBRE_ARCHIVO, VERSION_ESQUEMA

	datos = leer_settings(ruta_datos)
	for clave, valor in valores.items():
		seccion, _punto, nombre = clave.partition(".")
		if not isinstance(datos.get(seccion), dict):
			datos[seccion] = {}
		datos[seccion][nombre] = valor
	datos.setdefault("version_esquema", VERSION_ESQUEMA)
	almacen_json.escribir(NOMBRE_ARCHIVO, datos, Path(ruta_datos) / "config")


def _aplicar_en_config(config, valores: dict[str, Any], permitidas: set[str] | None, avisos: list[str]) -> None:
	"""Con la configuración ya cargada (importar un perfil): valida cada clave y aplica de una vez."""
	from app.core.configuracion import ErrorValidacion

	cambios = {}
	for clave, valor in valores.items():
		if permitidas is not None and clave not in permitidas:
			continue
		try:
			config.validar(clave, valor)
		except (ErrorValidacion, KeyError):
			log.warning("Valor no válido de la copia para %s; se omite", clave)
			avisos.append(_("Se omitió {c}: su valor no es válido en esta versión.").format(c=clave))
			continue
		cambios[clave] = valor
	if cambios:
		config.establecer_varias(cambios)


# ── Aplicar ───────────────────────────────────────────────────────────────────

class _Aplicador:
	def __init__(self, copia: CopiaAbierta, plan: PlanRestauracion, secretos: dict[str, str] | None, ruta_datos: Path,
			config, claves_permitidas: set[str] | None, ejecutable_rclone: Path | None) -> None:
		self.copia = copia
		self.plan = plan
		self.secretos = secretos
		self.ruta_datos = Path(ruta_datos)
		self.config = config
		self.permitidas = claves_permitidas
		self.ejecutable_rclone = ejecutable_rclone
		self.excluidos = plan.excluidos
		self.resultado = ResultadoAplicar()
		self.nubes_restauradas = False
		self.nubes_protegidas = False

	def aplicar(self) -> ResultadoAplicar:
		partes = []
		for parte in self.plan.partes:
			if parte not in self.copia.partes or formato.PARTES[parte].aplicacion == formato.EXTRAER:
				continue
			if parte in self.copia.danadas:
				self.resultado.avisos.append(_("La parte {p} de la copia está dañada y no se ha restaurado.").format(
					p=nombre_parte(parte)))
				continue
			partes.append(parte)
		valores = valores_a_aplicar(self.copia, partes, self.plan, self._actuales(), respetar_fabrica=self.permitidas is None)
		if valores:
			if self.config is not None:
				_aplicar_en_config(self.config, valores, self.permitidas, self.resultado.avisos)
			else:
				_escribir_settings(self.ruta_datos, valores)
		for parte in partes:
			self._archivos(parte)
		self._secretos(partes)
		if "complementos" in partes and self.plan.ofrecer_complementos:
			self._paquetes()
		self.resultado.partes = partes
		return self.resultado

	def _actuales(self) -> dict[str, Any]:
		if self.config is not None:
			return {k: self.config.obtener(k, None) for k in self.config.claves()}
		from app.services.copia.crear import valores_actuales

		return valores_actuales(self.ruta_datos)

	# Archivos ----------------------------------------------------------------

	def _protegido(self, relativa: str) -> bool:
		"""Archivos de este equipo que la restauración no toca (lo no marcado se conserva)."""
		if relativa in self.plan.archivos_excluidos:
			return True
		if relativa.startswith(formato.CARPETA_PROGRAMADOR) and "programador:*" in self.excluidos:
			return True
		id_conf = id_de_config(relativa)
		return id_conf is not None and f"plugin:{id_conf}:*" in self.excluidos

	def _archivos(self, parte: str) -> None:
		locales = dict(archivos_de_parte(parte, self.ruta_datos))
		de_copia = self.copia.archivos_datos(parte)
		nombres_copia = {a.ruta for a in de_copia}
		grupo_nubes = [a for a in de_copia if a.ruta == formato.RCLONE_CONF or a.ruta.startswith(formato.CARPETA_NUBES)]
		if parte == "conexiones":
			self._nubes(grupo_nubes, locales)
		for archivo in de_copia:
			if archivo in grupo_nubes or self._protegido(archivo.ruta):
				continue
			self._archivo(parte, archivo.ruta, locales.get(archivo.ruta))
		if self.plan.sustituir:
			for relativa, real in locales.items():
				es_nubes = relativa == formato.RCLONE_CONF or relativa.startswith(formato.CARPETA_NUBES)
				if relativa in nombres_copia or self._protegido(relativa) or (es_nubes and self.nubes_protegidas):
					continue
				try:
					real.unlink()
				except OSError:
					log.warning("No se pudo quitar %s al sustituir", relativa, exc_info=True)

	def _archivo(self, parte: str, relativa: str, local: Path | None) -> None:
		contenido = self.copia.leer(parte, relativa)
		destino = self.ruta_datos / relativa
		actual = _leer(destino)
		combinar_ = not self.plan.sustituir
		nuevo: bytes | None
		if relativa == formato.KNOWN_HOSTS:
			nuevo = combinar.combinar_known_hosts(actual, contenido, self.plan.huellas_aceptadas) if combinar_ else contenido
		elif relativa == formato.HOSTS_TLS:
			nuevo = _serializar(combinar.combinar_tls(_json(actual), _json(contenido), self.plan.huellas_aceptadas)) \
				if combinar_ else contenido
		elif relativa.endswith(".json") and _json(contenido) is not None:
			nuevo = self._json(relativa, contenido, actual)
		else:
			nuevo = None if (combinar_ and actual is not None) else contenido
		if nuevo is not None and nuevo != actual:
			_escribir(destino, nuevo)

	def _json(self, relativa: str, contenido: bytes, actual: bytes | None) -> bytes | None:
		datos_copia = _json(contenido)
		datos_actual = _json(actual)
		filtrado = combinar.filtrar_ejecutables(datos_copia, relativa, self.excluidos, datos_actual, self.plan.sustituir)
		id_conf = id_de_config(relativa)
		if id_conf is not None:
			filtrado = self._filtrar_config(filtrado, datos_actual, id_conf)
		if not self.plan.sustituir and datos_actual is not None:
			final = combinar.combinar_json(datos_actual, filtrado, relativa)
		else:
			final = filtrado
		if (datos_actual is None and relativa in combinar.LISTAS_EJECUTABLES
				and not combinar.elementos_lista(final, relativa) and combinar.elementos_lista(datos_copia, relativa)):
			return None  # No se marcó nada de una lista que aquí no existía: no se crea vacía.
		if combinar.iguales(final, datos_copia):
			return contenido
		if datos_actual is not None and combinar.iguales(final, datos_actual):
			return None
		return _serializar(final)

	def _filtrar_config(self, datos: Any, actual: Any, id_complemento: str) -> Any:
		"""Claves con ``ejecuta`` no marcadas: queda el valor actual (o el de fábrica si no hay)."""
		from app.plugins.config_plugins import SECCION

		if not isinstance(datos, dict) or not isinstance(datos.get(SECCION), dict):
			return datos
		resultado = copy.deepcopy(datos)
		ajustes_actuales = actual.get(SECCION, {}) if isinstance(actual, dict) and isinstance(actual.get(SECCION), dict) else {}
		for clave in list(resultado[SECCION]):
			if f"plugin:{id_complemento}:{clave}" in self.excluidos:
				if clave in ajustes_actuales:
					resultado[SECCION][clave] = copy.deepcopy(ajustes_actuales[clave])
				else:
					del resultado[SECCION][clave]
		return resultado

	# Nubes -------------------------------------------------------------------

	def _hay_cuentas_locales(self) -> bool:
		datos = _json(_leer(self.ruta_datos / formato.CUENTAS_NUBES))
		cuentas = datos.get("cuentas") if isinstance(datos, dict) else None
		if isinstance(cuentas, list):
			return bool(cuentas)
		return (self.ruta_datos / formato.RCLONE_CONF).is_file()

	def _nubes(self, grupo: list, locales: dict[str, Path]) -> None:
		"""``rclone.conf`` y la carpeta de ``zc.nubes`` van juntos y no se mezclan (7.6)."""
		if not grupo:
			return
		if not self.plan.sustituir and self._hay_cuentas_locales():
			self.nubes_protegidas = True
			self.resultado.avisos.append(_("Ya hay cuentas de nube en este equipo: se han conservado, y las de la copia "
				"hay que añadirlas de nuevo."))
			return
		if "rclone:*" in self.excluidos:
			self.nubes_protegidas = True
			self.resultado.avisos.append(_("Las cuentas de nube de la copia no se han restaurado porque no se marcaron."))
			return
		contrasena = (self.secretos or {}).get(f"{formato.SECRETOS_NUBES}rclone_config_pass")
		conf = next((a for a in grupo if a.ruta == formato.RCLONE_CONF), None)
		contenido_conf = self.copia.leer("conexiones", conf.ruta) if conf else None
		if contenido_conf is not None and rclone.cifrado(contenido_conf) and not contrasena:
			self.nubes_protegidas = True
			self.resultado.avisos.append(_("La copia no trae la contraseña de las cuentas de nube: no se han restaurado; "
				"hay que añadirlas de nuevo."))
			return
		quitar = sorted(e[len("rclone:"):] for e in self.excluidos if e.startswith("rclone:"))
		if contenido_conf is not None and quitar:
			try:
				contenido_conf = rclone.quitar_remotos(contenido_conf, quitar, contrasena or "", self.ruta_datos / "temp",
					self.ejecutable_rclone)
			except ErrorCopia as error:
				self.nubes_protegidas = True
				self.resultado.avisos.append(_("Las cuentas de nube no se han restaurado: {e}").format(e=error.mensaje))
				return
		for archivo in grupo:
			if archivo is conf:
				contenido = contenido_conf
			else:
				contenido = self.copia.leer("conexiones", archivo.ruta)
				if archivo.ruta == formato.CUENTAS_NUBES and quitar:
					contenido = _marcar_cuentas(contenido, set(quitar))
			destino = self.ruta_datos / archivo.ruta
			if contenido is not None and _leer(destino) != contenido:
				_escribir(destino, contenido)
		nombres = {a.ruta for a in grupo}
		for relativa, real in locales.items():
			if (relativa == formato.RCLONE_CONF or relativa.startswith(formato.CARPETA_NUBES)) and relativa not in nombres:
				real.unlink(missing_ok=True)
		self.nubes_restauradas = True
		if quitar:
			self.resultado.avisos.append(_("Cuentas de nube por volver a configurar: {c}.").format(c=", ".join(quitar)))

	# Secretos ----------------------------------------------------------------

	def _secretos(self, partes: list[str]) -> None:
		if self.secretos is None:
			return
		from app.services.copia.crear import _almacen

		almacen = _almacen(self.ruta_datos)
		locales = set(almacen.nombres())
		cambios: dict[str, str | None] = {}
		for parte in partes:
			de_parte = {n: v for n, v in self.secretos.items() if secreto_de_parte(n, parte)}

			def de_nubes(nombre: str, parte: str = parte) -> bool:
				return parte == "conexiones" and nombre.startswith(formato.SECRETOS_NUBES)

			if not self.nubes_restauradas:
				# Los de las nubes solo van con su rclone.conf (7.6): si no se restauró, ni se añaden ni se quitan.
				de_parte = {n: v for n, v in de_parte.items() if not de_nubes(n)}
			for nombre in locales:
				if not secreto_de_parte(nombre, parte) or nombre in de_parte:
					continue
				if (self.nubes_restauradas if de_nubes(nombre) else self.plan.sustituir):
					cambios[nombre] = None
			for nombre, valor in de_parte.items():
				if self.plan.sustituir or de_nubes(nombre) or nombre not in locales:
					cambios[nombre] = valor
		if cambios:
			almacen.guardar_varios(cambios)

	# Complementos ------------------------------------------------------------

	def _paquetes(self) -> None:
		"""Deja cada paquete no instalado (o de otra versión, al sustituir) para ofrecerlo tras arrancar (7.6, 8)."""
		from app.plugins import serie

		lista = self.copia.leer_json("complementos", formato.LISTA_COMPLEMENTOS, {})
		versiones = {str(c.get("id")): str(c.get("version", "")) for c in lista.get("instalados", [])
			if isinstance(c, dict)} if isinstance(lista, dict) else {}
		instalados = {c.id: c.version for c in complementos_de_usuario(self.ruta_datos)}
		for id_serie, version_serie in serie.SERIE.items():
			instalados.setdefault(id_serie, version_serie)
		carpeta = carpeta_por_instalar(self.ruta_datos)
		pendientes = leer_por_instalar(self.ruta_datos)
		for archivo in self.copia.archivos("complementos"):
			if not archivo.ruta.startswith(formato.PAQUETES):
				continue
			id_complemento = archivo.ruta[len(formato.PAQUETES):-len(".zcplugin")]
			version_copia = versiones.get(id_complemento, "")
			version_local = instalados.get(id_complemento)
			if version_local is not None and not (self.plan.sustituir and version_local != version_copia):
				continue
			destino = carpeta / f"{id_complemento}.zcplugin"
			_escribir(destino, self.copia.leer("complementos", archivo.ruta))
			pendientes = [p for p in pendientes if p.get("id") != id_complemento]
			pendientes.append({"id": id_complemento, "version": version_copia, "archivo": destino.name})
			self.resultado.por_instalar.append(id_complemento)
		if self.resultado.por_instalar:
			_escribir(carpeta / PENDIENTES_INSTALAR, _serializar({"version": 1, "complementos": pendientes}))


def _marcar_cuentas(contenido: bytes, remotos: set[str]) -> bytes:
	"""Las cuentas cuyo remoto se quitó quedan «Volver a configurar» (12.7)."""
	datos = _json(contenido)
	if not isinstance(datos, dict) or not isinstance(datos.get("cuentas"), list):
		return contenido
	for cuenta in datos["cuentas"]:
		if isinstance(cuenta, dict) and str(cuenta.get("id")) in remotos:
			cuenta["volver_a_configurar"] = True
	return _serializar(datos)


def aplicar(copia: CopiaAbierta, plan: PlanRestauracion, secretos: dict[str, str] | None, ruta_datos: Path | None = None,
		*, config=None, claves_permitidas: set[str] | None = None, ejecutable_rclone: Path | None = None) -> ResultadoAplicar:
	"""Aplica ``plan`` sobre ``data``. Con ``config``, los valores van a la configuración ya cargada."""
	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	return _Aplicador(copia, plan, secretos, ruta_datos, config, claves_permitidas, ejecutable_rclone).aplicar()


# ── Complementos por instalar ─────────────────────────────────────────────────

def carpeta_por_instalar(ruta_datos: Path | None = None) -> Path:
	return (Path(ruta_datos) if ruta_datos else paths.ruta_datos()) / "backups" / CARPETA_POR_INSTALAR


def leer_por_instalar(ruta_datos: Path | None = None) -> list[dict]:
	datos = _json(_leer(carpeta_por_instalar(ruta_datos) / PENDIENTES_INSTALAR))
	lista = datos.get("complementos") if isinstance(datos, dict) else None
	carpeta = carpeta_por_instalar(ruta_datos)
	return [c for c in lista or [] if isinstance(c, dict) and isinstance(c.get("archivo"), str)
		and formato.especial_permitido("complementos", formato.PAQUETES + c["archivo"]) and (carpeta / c["archivo"]).is_file()]


def quitar_por_instalar(ids: set[str], ruta_datos: Path | None = None, borrar_archivos: bool = False) -> None:
	carpeta = carpeta_por_instalar(ruta_datos)
	restantes = []
	for entrada in leer_por_instalar(ruta_datos):
		if entrada.get("id") in ids:
			if borrar_archivos:
				(carpeta / entrada["archivo"]).unlink(missing_ok=True)
		else:
			restantes.append(entrada)
	if restantes:
		_escribir(carpeta / PENDIENTES_INSTALAR, _serializar({"version": 1, "complementos": restantes}))
	else:
		(carpeta / PENDIENTES_INSTALAR).unlink(missing_ok=True)


# ── Restaurar ─────────────────────────────────────────────────────────────────

def mensaje_restaurada(resultado: ResultadoAplicar) -> str:
	partes = ", ".join(nombre_parte(p) for p in resultado.partes) or _("nada")
	texto = _("Copia restaurada: {p}.").format(p=partes)
	if resultado.por_instalar:
		texto += " " + _("Se le ofrecerá instalar {n} complementos de la copia.").format(n=len(resultado.por_instalar))
	for aviso in resultado.avisos:
		texto += " " + aviso
	return texto


def volver_atras(previa: Path, partes: list[str], ruta_datos: Path) -> None:
	"""Deja ``data`` como estaba con la copia automática previa (sustituye esas partes)."""
	with CopiaAbierta(previa) as copia:
		secretos = secretos_de_copia(copia, None)
		plan = PlanRestauracion(partes=[p for p in partes if p in copia.partes], modo="sustituir", ofrecer_complementos=False)
		aplicar(copia, plan, secretos, ruta_datos)


def restaurar_con_previa(copia: CopiaAbierta, plan: PlanRestauracion, secretos: dict[str, str] | None,
		ruta_datos: Path | None = None, *, config=None, claves_permitidas: set[str] | None = None,
		ejecutable_rclone: Path | None = None) -> tuple[ResultadoRestauracion, ResultadoAplicar | None]:
	"""Copia automática previa, aplicar y, si algo falla a medias, volver atrás (7.6)."""
	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	partes = [p for p in plan.partes if formato.PARTES[p].aplicacion != formato.EXTRAER]
	try:
		previa = crear_automatica(partes, ruta_datos)
	except Exception as error:  # noqa: BLE001 - sin copia previa no se toca nada
		log.exception("No se pudo crear la copia automática previa")
		mensaje = getattr(error, "mensaje", "") or str(error)
		return ResultadoRestauracion(False, _("No se ha restaurado nada: no se pudo crear la copia automática previa ({e}).")
			.format(e=mensaje), [], None), None
	try:
		resultado = aplicar(copia, plan, secretos, ruta_datos, config=config, claves_permitidas=claves_permitidas,
			ejecutable_rclone=ejecutable_rclone)
	except Exception as error:  # noqa: BLE001 - se vuelve atrás y se explica
		log.exception("Falló la restauración; se vuelve a la copia automática %s", previa.name)
		mensaje = getattr(error, "mensaje", "") or str(error)
		try:
			volver_atras(previa, partes, ruta_datos)
			texto = _("No se pudo restaurar la copia ({e}). Se ha vuelto al estado anterior.").format(e=mensaje)
		except Exception:  # noqa: BLE001
			log.exception("Tampoco se pudo volver a la copia automática %s", previa)
			texto = _("No se pudo restaurar la copia ({e}) ni volver al estado anterior. Restaure a mano la copia "
				"automática {n}.").format(e=mensaje, n=previa.name)
		return ResultadoRestauracion(False, texto, [], previa), None
	return ResultadoRestauracion(True, mensaje_restaurada(resultado), resultado.partes, previa), resultado


def restaurar_ahora(ruta_copia: Path, plan: PlanRestauracion, contrasena: str | None = None,
		ruta_datos: Path | None = None, *, secretos: dict[str, str] | None = None, usar_secretos: bool = True,
		ejecutable_rclone: Path | None = None, emitir: bool = True) -> ResultadoRestauracion:
	"""Restaura ya (partes «En el momento», 7.6) y emite ``al_restaurar`` para que cada servicio vuelva a leer."""
	from app.services import eventos

	with CopiaAbierta(ruta_copia) as copia:
		if secretos is None and usar_secretos:
			secretos = secretos_de_copia(copia, contrasena)
		resultado, aplicado = restaurar_con_previa(copia, plan, secretos, ruta_datos, ejecutable_rclone=ejecutable_rclone)
	if aplicado is not None and emitir:
		momento = [p for p in aplicado.partes if formato.PARTES[p].aplicacion == formato.MOMENTO]
		if momento:
			eventos.bus().emitir(eventos.AL_RESTAURAR, partes=momento)
	return resultado


# ── Registros y resumen ───────────────────────────────────────────────────────

def extraer_registros(ruta_copia: Path, destino: Path) -> int:
	"""Extrae los registros de la copia a ``destino`` (no se restauran, 7.2). Devuelve cuántos."""
	destino = Path(destino)
	cuantos = 0
	with CopiaAbierta(ruta_copia) as copia:
		if "registros" not in copia.partes_validas:
			return 0
		for archivo in copia.archivos_datos("registros"):
			relativa = archivo.ruta[len("logs/"):]
			_escribir(destino / relativa, copia.leer("registros", archivo.ruta))
			cuantos += 1
	return cuantos


def resumen(copia: CopiaAbierta) -> str:
	"""Texto del paso 1 de 7.6: versión, fecha, descripción, partes con su tamaño y secretos."""
	from app.services import formato as fmt

	manifiesto = copia.manifiesto
	tipo = {"copia": _("Copia de seguridad"), "automatica": _("Copia automática"), "perfil": _("Perfil")}[manifiesto.tipo]
	lineas = [_("{t} de zCommander {v}.").format(t=tipo, v=manifiesto.version_app or "?")]
	if manifiesto.fecha is not None:
		lineas.append(_("Creada el {f} a las {h}.").format(f=manifiesto.fecha.strftime("%d/%m/%Y"),
			h=manifiesto.fecha.strftime("%H:%M")))
	if manifiesto.descripcion:
		lineas.append(_("Descripción: {d}").format(d=manifiesto.descripcion))
	lineas.append(_("Partes:"))
	for parte in copia.partes:
		linea = f"- {nombre_parte(parte)}: {fmt.tamano_legible(copia.tamano(parte))}"
		if parte in copia.danadas:
			linea += " " + _("(dañada, no se puede restaurar: {m})").format(m=copia.danadas[parte])
		elif formato.PARTES[parte].aplicacion == formato.EXTRAER:
			linea += " " + _("(no se restaura: se extrae a una carpeta)")
		lineas.append(linea)
	modo = manifiesto.modo_secretos
	if modo == "contrasena":
		lineas.append(_("Contraseñas: incluidas, cifradas con la contraseña de la copia. Sin esa contraseña no se pueden recuperar."))
	elif modo == "dpapi":
		lineas.append(_("Contraseñas: protegidas para este usuario de Windows (copia automática)."))
	else:
		lineas.append(_("Contraseñas: no incluidas."))
		if copia.tiene("conexiones", formato.RCLONE_CONF):
			lineas.append(_("Sin las contraseñas, las cuentas de nube no se podrán abrir tras restaurar."))
	if "conexiones" in copia.partes:
		lineas.append(_("Las contraseñas de las unidades de red de Windows no se copian nunca."))
	lineas.extend(manifiesto.avisos)
	return "\n".join(lineas)


def borrar_carpeta(ruta: Path) -> None:
	shutil.rmtree(ruta, ignore_errors=True)
