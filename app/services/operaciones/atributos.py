# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cambiar atributos, fechas y permisos de uno o muchos elementos (sección 8.9).

Por qué es una operación del motor y no una tarea suelta: con «Aplicar también
a las subcarpetas y su contenido» puede tocar miles de archivos; así tiene
progreso, se puede cancelar y pausar, sale en la ventana de operaciones y
termina con un resumen como las demás.

Reglas:

- Solo se cambian los bits que la persona tocó en el diálogo (``poner`` y
  ``quitar``): una casilla a medias o sin tocar no se propaga al contenido.
- Si se quita «Solo lectura», se quita ANTES de cambiar las fechas; si se pone,
  DESPUÉS: así las fechas nunca chocan con el bloqueo de escritura.
- Recorre con el recorrido único (``recorrido.py``): no entra en enlaces ni
  uniones, y una subcarpeta ilegible se anota sin parar el resto.
- No admite deshacer (el diseño, 8.23, solo deshace renombrar, mover, crear y copiar).
- Carriles: en disco local, sin recursión, es una operación de metadatos y no
  espera a nadie; con recursión o fuera del disco local declara el volumen.
"""

from __future__ import annotations

import builtins
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.services import formato
from app.services.operaciones.modelo import ContextoEjecucion, Estado, Operacion, claves_carril
from app.services.recorrido import recorrer
from app.services.vfs import base

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Atributos que ofrece el diálogo, en su orden.
EDITABLES = (formato.SOLO_LECTURA, formato.OCULTO, formato.SISTEMA, formato.ARCHIVO, formato.NO_INDEXAR)
MASCARA_EDITABLES = 0
for _bit in EDITABLES:
	MASCARA_EDITABLES |= _bit


@dataclass(frozen=True)
class CambiosAtributos:
	"""Qué cambiar. ``None`` en fechas o permisos significa «sin cambio».

	:param poner: bits que se activan.
	:param quitar: bits que se desactivan.
	:param permisos: permisos Unix en número (``0o644``), solo en SFTP.
	:param recursivo: también el contenido de las carpetas.
	"""

	poner: int = 0
	quitar: int = 0
	modificado: float | None = None
	creado: float | None = None
	permisos: int | None = None
	recursivo: bool = False

	@property
	def vacio(self) -> bool:
		return not (self.poner or self.quitar) and self.modificado is None and self.creado is None and self.permisos is None


def estado_comun(entradas: Sequence[base.Entrada], bit: int) -> bool | None:
	"""``True``/``False`` si todas las entradas coinciden en ese bit; ``None`` si difieren (casilla a medias)."""
	valores = {bool(e.atributos & bit) for e in entradas if not e.es_superior}
	if len(valores) == 1:
		return valores.pop()
	return None if valores else False


# ── Fechas escritas por la persona ───────────────────────────────────────────

_FORMATOS_FECHA = (
	"%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
	"%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
	"%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
)
FORMATO_VISIBLE = "AAAA-MM-DD hh:mm:ss"


def texto_fecha(marca: float) -> str:
	"""«2024-05-31 18:20:05» en hora local (el formato que admite ``interpretar_fecha``)."""
	if marca <= 0:
		marca = time.time()
	try:
		return datetime.fromtimestamp(marca).strftime("%Y-%m-%d %H:%M:%S")
	except (OverflowError, OSError, ValueError):
		log.debug("Fecha que no se puede mostrar: %s", marca, exc_info=True)
		return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def interpretar_fecha(texto: str) -> float:
	"""Marca de tiempo de una fecha escrita en hora local.

	Admite «AAAA-MM-DD hh:mm:ss» (con o sin segundos u hora) y «DD/MM/AAAA hh:mm».

	:raises ValueError: con un mensaje para la persona usuaria.
	"""
	limpio = re.sub(r"\s+", " ", texto.strip())
	for formato_fecha in _FORMATOS_FECHA:
		try:
			momento = datetime.strptime(limpio, formato_fecha)
		except ValueError:
			continue
		if not 1980 <= momento.year <= 2107:
			raise ValueError(_("La fecha debe estar entre los años 1980 y 2107."))
		try:
			return momento.timestamp()
		except (OverflowError, OSError) as error:
			raise ValueError(_("La fecha está fuera del intervalo que admite Windows.")) from error
	raise ValueError(_("No se entiende la fecha «{t}». Escríbala como {f}, por ejemplo 2024-05-31 18:20:00.").format(
		t=texto.strip(), f=FORMATO_VISIBLE))


def interpretar_permisos(texto: str) -> int:
	"""«644» o «0755» → número. :raises ValueError: si no son 3 o 4 cifras octales."""
	limpio = texto.strip()
	if not re.fullmatch(r"[0-7]{3,4}", limpio):
		raise ValueError(_("Los permisos se escriben con tres cifras del 0 al 7, por ejemplo 644 o 755."))
	return int(limpio, 8)


# ── Operación ────────────────────────────────────────────────────────────────


class OperacionAtributos(Operacion):
	"""Aplica ``cambios`` a ``entradas`` de ``proveedor`` (y a su contenido si ``cambios.recursivo``)."""

	tipo = "atributos"

	def __init__(self, proveedor: base.Proveedor, entradas: list[base.Entrada], cambios: CambiosAtributos) -> None:
		super().__init__()
		self.proveedor = proveedor
		self.entradas = [e for e in entradas if not e.es_superior]
		self.cambios = cambios

	def descripcion(self) -> str:
		n = len(self.entradas)
		que = self.entradas[0].nombre if n == 1 else formato.plural(n, _("{n} elemento"), _("{n} elementos"))
		return _("Cambiar atributos y fechas de {que}").format(que=que)

	@property
	def carriles(self) -> frozenset[str]:
		if not self.entradas:
			return frozenset()
		if self.proveedor.esquema in ("local", "resultados") and not self.cambios.recursivo:
			return frozenset()
		return frozenset(claves_carril(self.proveedor, [e.ruta for e in self.entradas]))

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		carpetas = {(self.proveedor.esquema, self.proveedor.padre(e.ruta) or e.ruta_real or "") for e in self.entradas}
		return sorted(carpetas)

	def _proveedor_de_trabajo(self) -> base.Proveedor:
		"""En listas de resultados se trabaja con el disco directamente (sus rutas son locales y absolutas)."""
		if self.proveedor.esquema == "resultados":
			from app.services.vfs import resolver

			return resolver.proveedor_local()
		return self.proveedor.clonar()

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.ANALIZANDO)
		proveedor = self._proveedor_de_trabajo()
		try:
			with proveedor.transaccion():
				objetivos = self._objetivos(ctx, proveedor)
				self.progresar(archivos_total=len(objetivos))
				self.cambiar_estado(Estado.EJECUTANDO)
				for entrada in objetivos:
					ctx.comprobar()
					self.progresar(actual=entrada.nombre)
					try:
						self._aplicar(proveedor, entrada)
						self.sumar(archivos_hechos=1)
					except base.Cancelado:
						raise
					except base.ErrorArchivos as error:
						log.info("No se cambiaron los atributos de %s: %s", entrada.ruta, error.mensaje)
						self.anotar_error(entrada.ruta, error.mensaje)
		finally:
			if proveedor is not self.proveedor and self.proveedor.esquema != "resultados":
				proveedor.cerrar()

	def _objetivos(self, ctx: ContextoEjecucion, proveedor: base.Proveedor) -> list[base.Entrada]:
		"""Entradas a tocar: las elegidas y, con recursión, todo su contenido (cada carpeta tras lo suyo)."""
		objetivos: list[base.Entrada] = []
		for entrada in self.entradas:
			ctx.comprobar()
			if self.cambios.recursivo and entrada.es_carpeta and not entrada.es_enlace:
				self.progresar(actual=entrada.nombre)
				for elemento in recorrer(proveedor, entrada.ruta, ctx.token, carpetas_despues=True,
						al_error=lambda r, e: self.anotar_error(r, e.mensaje)):
					objetivos.append(elemento.entrada)
			objetivos.append(entrada)
		return objetivos

	def _aplicar(self, proveedor: base.Proveedor, entrada: base.Entrada) -> None:
		cambios = self.cambios
		actuales = entrada.atributos
		nuevos = (actuales | cambios.poner) & ~cambios.quitar
		cambia_atributos = bool(cambios.poner or cambios.quitar) and (nuevos & MASCARA_EDITABLES) != (actuales & MASCARA_EDITABLES)
		cambia_fechas = cambios.modificado is not None or cambios.creado is not None
		if cambia_atributos and not (nuevos & formato.SOLO_LECTURA):
			# Quitar el solo lectura primero: luego las fechas se escriben sin estorbo.
			proveedor.fijar_atributos(entrada.ruta, nuevos)
			cambia_atributos = False
		if cambia_fechas:
			proveedor.fijar_tiempos(entrada.ruta, cambios.modificado or 0.0, cambios.creado or 0.0)
		if cambia_atributos:
			proveedor.fijar_atributos(entrada.ruta, nuevos)
		if cambios.permisos is not None:
			proveedor.fijar_permisos(entrada.ruta, cambios.permisos)
