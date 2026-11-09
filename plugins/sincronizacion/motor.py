# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Tareas de sincronización con memoria y versiones (diseño 2.0, 11.12). Sin wx.

Por qué así:

- **Base del último estado** (``sqlite3`` en ``datos/<tarea>.db``): guarda,
  de cada elemento que quedó igual en los dos lados, su tamaño y su fecha en
  cada lado. Con ella, en dos sentidos se sabe qué lado cambió: un archivo que
  falta en un lado y sigue igual en el otro **se borró** (y se borra también
  en el otro, en lugar de volver a copiarse), y un archivo nuevo con el mismo
  tamaño y fecha que uno borrado del mismo lado **se renombró** (se renombra
  en el otro, sin copiar sus bytes).
- **Versiones**: lo que se va a sustituir o borrar en un lado se mueve antes a
  ``_versiones\\AAAA-MM-DD\\<ruta relativa>`` de ese lado, que nunca se
  sincroniza. Al terminar se borran los días más antiguos que ``dias_versiones``
  y, si aún ocupan más de ``max_versiones_mb``, los más antiguos hasta bajar.
- **Una operación del motor** (progreso, pausa, cola, F12, respuestas
  automáticas de las tareas programadas): las copias se hacen con
  ``OperacionCopiar`` como suboperaciones (``ejecutar_sub``), así heredan la
  copia segura, la verificación y los errores por elemento del núcleo.
- Origen y destino son cualquier dirección que entienda zCommander (disco,
  red, FTP, SFTP, nube): se abren sin panel con ``zc.vfs.resolver``.
- Después de ejecutar se vuelven a listar los dos lados para guardar el estado
  real (lo que falló no queda como sincronizado).
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.plugins import api

log = logging.getLogger("zcplugins.zc.sincronizacion")

ESPEJO, ACTUALIZAR, DOS_SENTIDOS = "espejo", "actualizar", "dos_sentidos"
MODOS = {
	ESPEJO: "Espejo: el destino queda igual que el origen",
	ACTUALIZAR: "Actualizar: copia al destino lo nuevo y lo más reciente, sin borrar",
	DOS_SENTIDOS: "Dos sentidos: los cambios de cada lado pasan al otro",
}
CARPETA_VERSIONES = "_versiones"
ARCHIVO_PERFILES = "perfiles.json"

# Acciones del plan.
COPIAR_A_DERECHA = "copiar_a_derecha"
COPIAR_A_IZQUIERDA = "copiar_a_izquierda"
BORRAR_DERECHA = "borrar_derecha"
BORRAR_IZQUIERDA = "borrar_izquierda"
RENOMBRAR_DERECHA = "renombrar_derecha"
RENOMBRAR_IZQUIERDA = "renombrar_izquierda"
CREAR_CARPETA_DERECHA = "crear_carpeta_derecha"
CREAR_CARPETA_IZQUIERDA = "crear_carpeta_izquierda"

TEXTO_ACCION = {
	COPIAR_A_DERECHA: "Copiar al destino",
	COPIAR_A_IZQUIERDA: "Copiar al origen",
	BORRAR_DERECHA: "Borrar en el destino",
	BORRAR_IZQUIERDA: "Borrar en el origen",
	RENOMBRAR_DERECHA: "Renombrar en el destino",
	RENOMBRAR_IZQUIERDA: "Renombrar en el origen",
	CREAR_CARPETA_DERECHA: "Crear carpeta en el destino",
	CREAR_CARPETA_IZQUIERDA: "Crear carpeta en el origen",
}


# ── Tareas guardadas ─────────────────────────────────────────────────────────


@dataclass
class Perfil:
	"""Una tarea de sincronización con nombre."""

	nombre: str
	origen: str
	destino: str
	modo: str = ESPEJO
	incluir: str = ""
	excluir: str = ""
	subcarpetas: bool = True
	versiones: bool = True
	ultima: float = 0.0
	resultado: str = ""

	@classmethod
	def desde(cls, datos: dict) -> Perfil:
		conocidos = {k: v for k, v in datos.items() if k in cls.__dataclass_fields__}
		perfil = cls(**conocidos)
		if perfil.modo not in MODOS:
			perfil.modo = ESPEJO
		return perfil


def leer_perfiles(carpeta: Path) -> list[Perfil]:
	try:
		datos = json.loads((Path(carpeta) / ARCHIVO_PERFILES).read_text(encoding="utf-8"))
	except FileNotFoundError:
		return []
	except (OSError, ValueError):
		log.warning("No se pudieron leer las tareas de sincronización", exc_info=True)
		return []
	perfiles = []
	for elemento in datos.get("perfiles", []) if isinstance(datos, dict) else []:
		try:
			perfiles.append(Perfil.desde(elemento))
		except (TypeError, ValueError):
			log.warning("Tarea de sincronización no válida: %r", elemento)
	return perfiles


def guardar_perfiles(carpeta: Path, perfiles: Iterable[Perfil]) -> None:
	ruta = Path(carpeta) / ARCHIVO_PERFILES
	temporal = ruta.with_suffix(".tmp")
	temporal.write_text(json.dumps({"version": 1, "perfiles": [asdict(p) for p in perfiles]}, ensure_ascii=False, indent=1),
		encoding="utf-8")
	temporal.replace(ruta)


def buscar_perfil(perfiles: Iterable[Perfil], nombre: str) -> Perfil | None:
	return next((p for p in perfiles if p.nombre.casefold() == nombre.casefold()), None)


def nombre_archivo(nombre: str) -> str:
	"""Nombre de archivo seguro para la base de estado de una tarea."""
	limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nombre).strip(" .")
	return limpio or "tarea"


# ── Listado y estado ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Info:
	tamano: int
	modificado: float
	es_carpeta: bool = False
	entrada: Any = None


def _patrones(texto: str) -> list[str]:
	return [p.strip() for p in re.split(r"[;,]", texto or "") if p.strip()]


def listar(proveedor: api.Proveedor, raiz: str, *, incluir: str = "", excluir: str = "", subcarpetas: bool = True,
		cancelacion=None) -> dict[str, Info]:
	"""Todo lo que hay bajo ``raiz``, con la ruta relativa (separada con «/») como clave.

	No entra en enlaces, se salta ``_versiones`` de la raíz y lo que coincide
	con ``excluir`` (por nombre o por ruta relativa); ``incluir`` filtra solo archivos.
	"""
	incluidos, excluidos = _patrones(incluir), _patrones(excluir)
	resultado: dict[str, Info] = {}
	pendientes: list[tuple[str, str]] = [(raiz, "")]
	while pendientes:
		api.comprobar(cancelacion)
		carpeta, prefijo = pendientes.pop()
		for entrada in proveedor.listar(carpeta, cancelacion):
			if entrada.es_superior or entrada.es_enlace:
				continue
			relativo = f"{prefijo}/{entrada.nombre}" if prefijo else entrada.nombre
			if not prefijo and entrada.nombre.casefold() == CARPETA_VERSIONES:
				continue
			if any(fnmatch.fnmatch(entrada.nombre.casefold(), p.casefold()) or fnmatch.fnmatch(relativo.casefold(), p.casefold())
					for p in excluidos):
				continue
			if entrada.es_carpeta:
				if subcarpetas:
					resultado[relativo] = Info(-1, entrada.modificado, True, entrada)
					pendientes.append((entrada.ruta, relativo))
				continue
			if incluidos and not any(fnmatch.fnmatch(entrada.nombre.casefold(), p.casefold()) for p in incluidos):
				continue
			resultado[relativo] = Info(entrada.tamano, entrada.modificado, False, entrada)
	return resultado


@dataclass(frozen=True)
class EstadoAnterior:
	es_carpeta: bool
	tamano_i: int
	modificado_i: float
	tamano_d: int
	modificado_d: float


class BaseEstado:
	"""El último estado sincronizado de una tarea, en SQLite."""

	def __init__(self, ruta: Path) -> None:
		self.ruta = Path(ruta)

	def _conectar(self) -> sqlite3.Connection:
		conexion = sqlite3.connect(self.ruta)
		conexion.execute("CREATE TABLE IF NOT EXISTS estado (relativo TEXT PRIMARY KEY, es_carpeta INTEGER NOT NULL, "
			"tamano_i INTEGER, modificado_i REAL, tamano_d INTEGER, modificado_d REAL)")
		return conexion

	def leer(self) -> dict[str, EstadoAnterior]:
		if not self.ruta.is_file():
			return {}
		conexion = self._conectar()
		try:
			return {fila[0]: EstadoAnterior(bool(fila[1]), fila[2], fila[3], fila[4], fila[5])
				for fila in conexion.execute("SELECT relativo, es_carpeta, tamano_i, modificado_i, tamano_d, modificado_d FROM estado")}
		finally:
			conexion.close()

	def guardar(self, izquierda: dict[str, Info], derecha: dict[str, Info]) -> int:
		"""Sustituye el estado por lo que está en los dos lados. Devuelve cuántos elementos quedan."""
		filas = [(r, int(i.es_carpeta), i.tamano, i.modificado, derecha[r].tamano, derecha[r].modificado)
			for r, i in izquierda.items() if r in derecha and derecha[r].es_carpeta == i.es_carpeta]
		conexion = self._conectar()
		try:
			with conexion:
				conexion.execute("DELETE FROM estado")
				conexion.executemany("INSERT INTO estado VALUES (?, ?, ?, ?, ?, ?)", filas)
		finally:
			conexion.close()
		return len(filas)


# ── Plan ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Accion:
	tipo: str
	relativo: str
	motivo: str = ""
	nuevo: str = ""  # en los renombrados, la ruta relativa nueva

	def texto(self) -> str:
		if self.nuevo:
			return f"{TEXTO_ACCION[self.tipo]}: {self.relativo} a {self.nuevo}"
		return f"{TEXTO_ACCION[self.tipo]}: {self.relativo}"


def _igual(a: Info, b: Info, tolerancia: float) -> bool:
	return a.tamano == b.tamano and abs(a.modificado - b.modificado) <= tolerancia


def _igual_estado(info: Info, tamano: int, modificado: float, tolerancia: float) -> bool:
	return info.tamano == tamano and abs(info.modificado - modificado) <= tolerancia


def calcular_plan(izquierda: dict[str, Info], derecha: dict[str, Info], estado: dict[str, EstadoAnterior], modo: str,
		tolerancia: float = 2.0) -> list[Accion]:
	"""Qué hay que hacer para sincronizar (función pura: la usan la simulación y la ejecución)."""
	acciones: list[Accion] = []
	borradas_d: set[str] = set()
	# Carpetas: primero se crean las que faltan; en espejo, se borra (a versiones) la que sobra en el destino.
	for relativo, info in sorted(izquierda.items()):
		if info.es_carpeta and relativo not in derecha:
			anterior = estado.get(relativo)
			if modo == DOS_SENTIDOS and anterior is not None and anterior.es_carpeta:
				continue  # se borró a la derecha: lo deciden sus archivos y la limpieza de carpetas vacías
			acciones.append(Accion(CREAR_CARPETA_DERECHA, relativo, "Carpeta nueva"))
	for relativo, info in sorted(derecha.items()):
		if not info.es_carpeta or relativo in izquierda:
			continue
		if modo == ESPEJO:
			if not any(relativo.startswith(b + "/") for b in borradas_d):
				acciones.append(Accion(BORRAR_DERECHA, relativo, "No está en el origen"))
				borradas_d.add(relativo)
		elif modo == DOS_SENTIDOS:
			anterior = estado.get(relativo)
			if anterior is None or not anterior.es_carpeta:
				acciones.append(Accion(CREAR_CARPETA_IZQUIERDA, relativo, "Carpeta nueva"))
	# Archivos.
	nuevos_i: list[str] = []
	nuevos_d: list[str] = []
	for relativo in sorted(set(izquierda) | set(derecha)):
		i, d = izquierda.get(relativo), derecha.get(relativo)
		if (i is not None and i.es_carpeta) or (d is not None and d.es_carpeta):
			continue
		if any(relativo.startswith(b + "/") for b in borradas_d):
			continue
		anterior = estado.get(relativo)
		if anterior is not None and anterior.es_carpeta:
			anterior = None
		if modo == ESPEJO:
			if i is not None and (d is None or not _igual(i, d, tolerancia)):
				acciones.append(Accion(COPIAR_A_DERECHA, relativo, "Nuevo en el origen" if d is None else "Distinto en el destino"))
			elif i is None and d is not None:
				acciones.append(Accion(BORRAR_DERECHA, relativo, "No está en el origen"))
			continue
		if modo == ACTUALIZAR:
			if i is not None and d is None:
				acciones.append(Accion(COPIAR_A_DERECHA, relativo, "Nuevo en el origen"))
			elif i is not None and d is not None and i.modificado > d.modificado + tolerancia:
				acciones.append(Accion(COPIAR_A_DERECHA, relativo, "Más reciente en el origen"))
			continue
		# Dos sentidos, con la base del último estado.
		if i is not None and d is not None:
			if _igual(i, d, tolerancia):
				continue
			cambio_i = anterior is None or not _igual_estado(i, anterior.tamano_i, anterior.modificado_i, tolerancia)
			cambio_d = anterior is None or not _igual_estado(d, anterior.tamano_d, anterior.modificado_d, tolerancia)
			if cambio_i and not cambio_d:
				acciones.append(Accion(COPIAR_A_DERECHA, relativo, "Cambió en el origen"))
			elif cambio_d and not cambio_i:
				acciones.append(Accion(COPIAR_A_IZQUIERDA, relativo, "Cambió en el destino"))
			elif i.modificado >= d.modificado:
				acciones.append(Accion(COPIAR_A_DERECHA, relativo, "Cambió en los dos lados: gana el más reciente, el del origen"))
			else:
				acciones.append(Accion(COPIAR_A_IZQUIERDA, relativo, "Cambió en los dos lados: gana el más reciente, el del destino"))
		elif i is not None:
			if anterior is None:
				acciones.append(Accion(COPIAR_A_DERECHA, relativo, "Nuevo en el origen"))
				nuevos_i.append(relativo)
			elif _igual_estado(i, anterior.tamano_i, anterior.modificado_i, tolerancia):
				acciones.append(Accion(BORRAR_IZQUIERDA, relativo, "Se borró en el destino"))
			else:
				acciones.append(Accion(COPIAR_A_DERECHA, relativo, "Se borró en el destino pero cambió en el origen: se conserva"))
		elif d is not None:
			if anterior is None:
				acciones.append(Accion(COPIAR_A_IZQUIERDA, relativo, "Nuevo en el destino"))
				nuevos_d.append(relativo)
			elif _igual_estado(d, anterior.tamano_d, anterior.modificado_d, tolerancia):
				acciones.append(Accion(BORRAR_DERECHA, relativo, "Se borró en el origen"))
			else:
				acciones.append(Accion(COPIAR_A_IZQUIERDA, relativo, "Se borró en el origen pero cambió en el destino: se conserva"))
	if modo == DOS_SENTIDOS:
		acciones = _renombrados(acciones, izquierda, derecha, estado, nuevos_i, nuevos_d, tolerancia)
	return acciones


def _renombrados(acciones: list[Accion], izquierda: dict[str, Info], derecha: dict[str, Info],
		estado: dict[str, EstadoAnterior], nuevos_i: list[str], nuevos_d: list[str], tolerancia: float) -> list[Accion]:
	"""Un nuevo de un lado con el tamaño y la fecha de uno que se borró de ese mismo lado es un renombrado."""
	por_relativo = {(a.tipo, a.relativo): a for a in acciones}
	for nuevos, lado, tipo_borrar, tipo_copiar, tipo_renombrar in (
		(nuevos_i, izquierda, BORRAR_DERECHA, COPIAR_A_DERECHA, RENOMBRAR_DERECHA),
		(nuevos_d, derecha, BORRAR_IZQUIERDA, COPIAR_A_IZQUIERDA, RENOMBRAR_IZQUIERDA),
	):
		for nuevo in nuevos:
			info = lado[nuevo]
			for (tipo, viejo), accion in list(por_relativo.items()):
				if tipo != tipo_borrar or accion is None:
					continue
				anterior = estado[viejo]
				tamano, fecha = ((anterior.tamano_i, anterior.modificado_i) if lado is izquierda
					else (anterior.tamano_d, anterior.modificado_d))
				if _igual_estado(info, tamano, fecha, tolerancia):
					por_relativo[(tipo, viejo)] = None
					por_relativo[(tipo_copiar, nuevo)] = Accion(tipo_renombrar, viejo, "Se renombró", nuevo)
					break
	return [a for a in por_relativo.values() if a is not None]


def resumen_plan(acciones: Iterable[Accion]) -> str:
	cuentas: dict[str, int] = {}
	for accion in acciones:
		cuentas[accion.tipo] = cuentas.get(accion.tipo, 0) + 1
	if not cuentas:
		return "No hay nada que sincronizar"
	return ", ".join(f"{TEXTO_ACCION[t].lower()}: {n}" for t, n in cuentas.items())


# ── Operación ────────────────────────────────────────────────────────────────


@dataclass
class Ajustes:
	tolerancia_s: float = 2.0
	verificar: bool = False
	dias_versiones: int = 30
	max_versiones_mb: int = 1024


@dataclass
class Informe:
	lineas: list[str] = field(default_factory=list)

	def apuntar(self, texto: str) -> None:
		self.lineas.append(texto)


class OperacionTareaSincronizacion(api.Operacion):
	"""Ejecuta (o simula) una tarea de sincronización como una sola operación del motor."""

	tipo = "sincronizar"

	def __init__(self, perfil: Perfil, carpeta_datos: Path, resolver: Callable[[str], tuple[api.Proveedor, str]],
			ajustes: Ajustes | None = None, simular: bool = False, al_terminar_perfil: Callable[[Perfil], None] | None = None) -> None:
		super().__init__()
		self.perfil = perfil
		self.carpeta_datos = Path(carpeta_datos)
		self.resolver = resolver
		self.ajustes = ajustes or Ajustes()
		self.simular = simular
		self.plan: list[Accion] = []
		self.informe = Informe()
		self.al_terminar_perfil = al_terminar_perfil
		self._dia = time.strftime("%Y-%m-%d")

	def descripcion(self) -> str:
		return f"{'Simular' if self.simular else 'Sincronizar'} {self.perfil.nombre}"

	# ── Utilidades de proveedor ──────────────────────────────────────────────

	@staticmethod
	def _ruta(proveedor: api.Proveedor, raiz: str, relativo: str) -> str:
		ruta = raiz
		for parte in relativo.split("/"):
			if parte:
				ruta = proveedor.unir(ruta, parte)
		return ruta

	def _asegurar_carpeta(self, proveedor: api.Proveedor, raiz: str, relativo: str) -> str:
		ruta = raiz
		for parte in [p for p in relativo.split("/") if p]:
			ruta = proveedor.unir(ruta, parte)
			if not proveedor.existe(ruta):
				proveedor.crear_carpeta(ruta)
		return ruta

	def _a_versiones(self, proveedor: api.Proveedor, raiz: str, relativo: str) -> None:
		"""Mueve lo que había en ``relativo`` a ``_versiones/AAAA-MM-DD/relativo`` de ese lado."""
		origen = self._ruta(proveedor, raiz, relativo)
		padre, _barra, nombre = relativo.rpartition("/")
		carpeta = self._asegurar_carpeta(proveedor, raiz, "/".join(filter(None, [CARPETA_VERSIONES, self._dia, padre])))
		destino = proveedor.unir(carpeta, nombre)
		if proveedor.existe(destino):
			base, punto, extension = nombre.rpartition(".")
			sello = time.strftime("%H%M%S")
			destino = proveedor.unir(carpeta, f"{base} ({sello}).{extension}" if punto and base else f"{nombre} ({sello})")
		proveedor.renombrar(origen, destino)

	def _quitar(self, proveedor: api.Proveedor, raiz: str, relativo: str) -> None:
		if self.perfil.versiones:
			self._a_versiones(proveedor, raiz, relativo)
		else:
			ruta = self._ruta(proveedor, raiz, relativo)
			proveedor.eliminar(ruta, recursivo=True)

	# ── Ejecución ────────────────────────────────────────────────────────────

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.ANALIZANDO)
		izquierda_p = derecha_p = None
		try:
			izquierda_p, izquierda_r = self.resolver(self.perfil.origen)
			derecha_p, derecha_r = self.resolver(self.perfil.destino)
			opciones = {"incluir": self.perfil.incluir, "excluir": self.perfil.excluir, "subcarpetas": self.perfil.subcarpetas}
			izquierda = listar(izquierda_p, izquierda_r, cancelacion=ctx.token, **opciones)
			derecha = listar(derecha_p, derecha_r, cancelacion=ctx.token, **opciones)
			base = BaseEstado(self.carpeta_datos / f"{nombre_archivo(self.perfil.nombre)}.db")
			estado = base.leer() if self.perfil.modo == DOS_SENTIDOS else {}
			self.plan = calcular_plan(izquierda, derecha, estado, self.perfil.modo, self.ajustes.tolerancia_s)
			self.informe.apuntar(f"{self.descripcion()}: {self.perfil.origen} y {self.perfil.destino} ({MODOS[self.perfil.modo]}).")
			if self.simular:
				for accion in self.plan:
					self.informe.apuntar(f"{accion.texto()} ({accion.motivo})")
				self.informe.apuntar(resumen_plan(self.plan))
				self.progresar(archivos_total=len(self.plan), archivos_hechos=len(self.plan))
				self.cambiar_estado(api.Estado.TERMINADA)
				return
			# Las copias suman su propio total al ejecutarse como suboperaciones.
			self.progresar(archivos_total=sum(1 for a in self.plan if a.tipo not in (COPIAR_A_DERECHA, COPIAR_A_IZQUIERDA)))
			self.cambiar_estado(api.Estado.EJECUTANDO)
			lados = {"i": (izquierda_p, izquierda_r, izquierda), "d": (derecha_p, derecha_r, derecha)}
			self._aplicar(ctx, lados)
			ctx.comprobar()
			self._limpiar_carpetas_borradas(lados, estado)
			# Estado real tras ejecutar: lo que falló no queda como sincronizado.
			izquierda = listar(izquierda_p, izquierda_r, cancelacion=ctx.token, **opciones)
			derecha = listar(derecha_p, derecha_r, cancelacion=ctx.token, **opciones)
			base.guardar(izquierda, derecha)
			if self.perfil.versiones:
				for proveedor, raiz in ((izquierda_p, izquierda_r), (derecha_p, derecha_r)):
					self._limpiar_versiones(proveedor, raiz)
			self.informe.apuntar(resumen_plan(self.plan))
			self.cambiar_estado(api.Estado.TERMINADA_CON_ERRORES if self.errores else api.Estado.TERMINADA)
		except api.Cancelado:
			self.cambiar_estado(api.Estado.CANCELADA)
			raise
		except api.ErrorArchivos as error:
			self.anotar_error(getattr(error, "ruta", "") or self.perfil.nombre, str(error))
			self.informe.apuntar(f"Error: {error}")
			self.cambiar_estado(api.Estado.FALLIDA)
		finally:
			for proveedor in (izquierda_p, derecha_p):
				if proveedor is not None and proveedor.esquema != "local":
					proveedor.cerrar()
			self._guardar_informe()

	def _aplicar(self, ctx: api.ContextoEjecucion, lados: dict) -> None:
		"""Primero carpetas y renombrados, después copias (por carpeta de destino) y al final borrados."""
		copias: dict[tuple[str, str], list] = {}
		borrados: list[Accion] = []
		for accion in self.plan:
			ctx.comprobar()
			try:
				if accion.tipo in (CREAR_CARPETA_DERECHA, CREAR_CARPETA_IZQUIERDA):
					proveedor, raiz, _l = lados["d" if accion.tipo == CREAR_CARPETA_DERECHA else "i"]
					self._asegurar_carpeta(proveedor, raiz, accion.relativo)
					self._hecho(accion)
				elif accion.tipo in (RENOMBRAR_DERECHA, RENOMBRAR_IZQUIERDA):
					proveedor, raiz, _l = lados["d" if accion.tipo == RENOMBRAR_DERECHA else "i"]
					padre = accion.nuevo.rpartition("/")[0]
					self._asegurar_carpeta(proveedor, raiz, padre)
					proveedor.renombrar(self._ruta(proveedor, raiz, accion.relativo), self._ruta(proveedor, raiz, accion.nuevo))
					self._hecho(accion)
				elif accion.tipo in (COPIAR_A_DERECHA, COPIAR_A_IZQUIERDA):
					origen, destino = ("i", "d") if accion.tipo == COPIAR_A_DERECHA else ("d", "i")
					copias.setdefault((origen, accion.relativo.rpartition("/")[0]), []).append(accion)
				else:
					borrados.append(accion)
			except api.ErrorArchivos as error:
				self._fallo(accion, error)
		for (origen, padre), acciones in copias.items():
			ctx.comprobar()
			destino = "d" if origen == "i" else "i"
			proveedor_o, _raiz_o, lista_o = lados[origen]
			proveedor_d, raiz_d, lista_d = lados[destino]
			validas = []
			for accion in acciones:
				try:
					# Lo que se va a sustituir pasa antes a versiones; sin versiones, la copia lo sobrescribe.
					if accion.relativo in lista_d and self.perfil.versiones:
						self._a_versiones(proveedor_d, raiz_d, accion.relativo)
					validas.append(accion)
				except api.ErrorArchivos as error:
					self._fallo(accion, error)
			if not validas:
				continue
			try:
				carpeta = self._asegurar_carpeta(proveedor_d, raiz_d, padre)
			except api.ErrorArchivos as error:
				for accion in validas:
					self._fallo(accion, error)
				continue
			opciones = api.OpcionesCopia(politica=api.Politica.SOBRESCRIBIR, verificar=self.ajustes.verificar, lista_conflictos=False)
			sub = api.OperacionCopiar(proveedor_o, [lista_o[a.relativo].entrada for a in validas], proveedor_d, carpeta, opciones)
			antes = len(self.errores)
			self.ejecutar_sub(sub, ctx)
			fallidos = {getattr(e, "nombre", "") for e in getattr(sub, "fallidos", [])}
			for accion in validas:
				if accion.relativo.rpartition("/")[2] not in fallidos:
					self.informe.apuntar(f"{accion.texto()} ({accion.motivo})")
			if len(self.errores) > antes:
				self.informe.apuntar(f"Errores al copiar en {padre or 'la raíz'}: {len(self.errores) - antes}")
		for accion in borrados:
			ctx.comprobar()
			proveedor, raiz, _l = lados["d" if accion.tipo == BORRAR_DERECHA else "i"]
			try:
				self._quitar(proveedor, raiz, accion.relativo)
				self._hecho(accion)
			except api.ErrorArchivos as error:
				self._fallo(accion, error)

	def _hecho(self, accion: Accion) -> None:
		self.informe.apuntar(f"{accion.texto()} ({accion.motivo})")
		self.sumar(archivos_hechos=1)

	def _fallo(self, accion: Accion, error: Exception) -> None:
		self.anotar_error(accion.relativo, str(error))
		self.informe.apuntar(f"Error: {accion.texto()}: {error}")

	def _limpiar_carpetas_borradas(self, lados: dict, estado: dict[str, EstadoAnterior]) -> None:
		"""Dos sentidos: una carpeta sincronizada que se borró en un lado se quita del otro si ha quedado vacía."""
		if self.perfil.modo != DOS_SENTIDOS:
			return
		for relativo in sorted((r for r, e in estado.items() if e.es_carpeta), key=len, reverse=True):
			for falta, queda in (("i", "d"), ("d", "i")):
				if relativo in lados[falta][2] or relativo not in lados[queda][2]:
					continue
				proveedor, raiz, _l = lados[queda]
				ruta = self._ruta(proveedor, raiz, relativo)
				try:
					if not [e for e in proveedor.listar(ruta) if not e.es_superior]:
						proveedor.eliminar(ruta, recursivo=False)
						self.informe.apuntar(f"Carpeta borrada en el {'destino' if queda == 'd' else 'origen'}: {relativo}")
				except api.ErrorArchivos as error:
					log.debug("No se pudo quitar la carpeta vacía %s: %s", ruta, error)

	def _limpiar_versiones(self, proveedor: api.Proveedor, raiz: str) -> None:
		"""Borra los días de versiones más antiguos que el límite de días y, después, hasta caber en el de tamaño."""
		carpeta = proveedor.unir(raiz, CARPETA_VERSIONES)
		try:
			if not proveedor.existe(carpeta):
				return
			dias = sorted((e for e in proveedor.listar(carpeta) if e.es_carpeta and not e.es_superior
				and re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.nombre)), key=lambda e: e.nombre)
			limite = time.strftime("%Y-%m-%d", time.localtime(time.time() - self.ajustes.dias_versiones * 86400))
			restantes = []
			for dia in dias:
				if dia.nombre < limite:
					proveedor.eliminar(dia.ruta, recursivo=True)
					self.informe.apuntar(f"Versiones del {dia.nombre} borradas por antigüedad")
				else:
					restantes.append(dia)
			maximo = self.ajustes.max_versiones_mb * 1024 * 1024
			tamanos = [(dia, sum(i.tamano for i in listar(proveedor, dia.ruta).values() if not i.es_carpeta)) for dia in restantes]
			total = sum(t for _d, t in tamanos)
			for dia, tamano in tamanos:
				if total <= maximo or dia.nombre == self._dia:
					break
				proveedor.eliminar(dia.ruta, recursivo=True)
				total -= tamano
				self.informe.apuntar(f"Versiones del {dia.nombre} borradas para no pasar de {self.ajustes.max_versiones_mb} MB")
		except api.ErrorArchivos as error:
			log.warning("No se pudieron limpiar las versiones de %s: %s", carpeta, error)

	def _guardar_informe(self) -> None:
		"""El informe de la última ejecución, en ``datos/informes/<tarea>.txt``."""
		self.perfil.ultima = time.time()
		self.perfil.resultado = self.resumen()
		try:
			carpeta = self.carpeta_datos / "informes"
			carpeta.mkdir(parents=True, exist_ok=True)
			texto = "\n".join([time.strftime("%Y-%m-%d %H:%M:%S"), *self.informe.lineas, self.resumen()])
			(carpeta / f"{nombre_archivo(self.perfil.nombre)}.txt").write_text(texto + "\n", encoding="utf-8")
		except OSError:
			log.warning("No se pudo guardar el informe de %s", self.perfil.nombre, exc_info=True)
		if self.al_terminar_perfil is not None and not self.simular:
			try:
				self.al_terminar_perfil(self.perfil)
			except Exception:  # noqa: BLE001 - guardar la última ejecución nunca tumba la operación
				log.warning("No se pudo apuntar la última ejecución de %s", self.perfil.nombre, exc_info=True)


def leer_informe(carpeta_datos: Path, nombre: str) -> str:
	try:
		return (Path(carpeta_datos) / "informes" / f"{nombre_archivo(nombre)}.txt").read_text(encoding="utf-8")
	except OSError:
		return ""
