# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diferencias entre dos carpetas: el cálculo común de «Comparar carpetas» y «Sincronizar».

Sin wx. ``comparar`` recorre los dos lados con el recorrido único y devuelve
una ``Diferencia`` por elemento que no es igual en los dos; ``proponer``
decide la acción de cada fila según la dirección; ``marcas`` dice qué marcar
en cada panel (Ctrl+F10, como Norton).

Decisiones:

- Una carpeta que solo existe en un lado es UNA fila (su contenido no se
  lista aparte): copiarla o borrarla actúa sobre la carpeta entera.
- «Más reciente» admite una tolerancia (2 s por defecto) porque FAT guarda la
  hora con 2 s de precisión y una copia a un USB parecería siempre distinta.
- El contenido solo se lee si los tamaños coinciden (si no, ya son distintos).
- En «los dos sentidos», dos archivos con la misma fecha y distinto contenido
  son un conflicto: no se sabe cuál es el bueno.
- Un archivo en un lado y una carpeta con el mismo nombre en el otro es su
  propio conflicto («Archivo frente a carpeta») y su acción de fábrica es
  Nada: copiar o borrar ahí destruiría una carpeta o un archivo, y no es que
  «cambiaran los dos».
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from app.services import formato
from app.services.recorrido import recorrer
from app.services.vfs import base

log = logging.getLogger(__name__)

_BLOQUE = 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Criterio(StrEnum):
	NOMBRE = "nombre"
	FECHA = "fecha"  # nombre y fecha
	TAMANO = "tamano"  # nombre, fecha y tamaño
	CONTENIDO = "contenido"

	@property
	def texto(self) -> str:
		return {
			Criterio.NOMBRE: _("Nombre"),
			Criterio.FECHA: _("Nombre y fecha"),
			Criterio.TAMANO: _("Nombre, fecha y tamaño"),
			Criterio.CONTENIDO: _("Contenido"),
		}[self]


class Direccion(StrEnum):
	A_LA_DERECHA = "a_la_derecha"
	A_LA_IZQUIERDA = "a_la_izquierda"
	AMBOS = "ambos"

	@property
	def texto(self) -> str:
		return {
			Direccion.A_LA_DERECHA: _("De izquierda a derecha"),
			Direccion.A_LA_IZQUIERDA: _("De derecha a izquierda"),
			Direccion.AMBOS: _("En los dos sentidos"),
		}[self]


class Estado(StrEnum):
	"""Cómo están los dos lados de un elemento."""

	SOLO_IZQUIERDA = "solo_izquierda"
	SOLO_DERECHA = "solo_derecha"
	IZQUIERDA_MAS_RECIENTE = "izquierda_mas_reciente"
	DERECHA_MAS_RECIENTE = "derecha_mas_reciente"
	DISTINTOS = "distintos"  # misma fecha, distinto tamaño o contenido
	TIPO_DISTINTO = "tipo_distinto"  # archivo en un lado y carpeta en el otro


class Accion(StrEnum):
	COPIAR_DERECHA = "copiar_derecha"
	COPIAR_IZQUIERDA = "copiar_izquierda"
	ELIMINAR_DERECHA = "eliminar_derecha"
	ELIMINAR_IZQUIERDA = "eliminar_izquierda"
	NADA = "nada"
	CONFLICTO = "conflicto"

	@property
	def texto(self) -> str:
		return {
			Accion.COPIAR_DERECHA: _("Copiar a la derecha"),
			Accion.COPIAR_IZQUIERDA: _("Copiar a la izquierda"),
			Accion.ELIMINAR_DERECHA: _("Eliminar a la derecha"),
			Accion.ELIMINAR_IZQUIERDA: _("Eliminar a la izquierda"),
			Accion.NADA: _("Nada"),
			Accion.CONFLICTO: _("Conflicto: cambiaron los dos"),
		}[self]


@dataclass(frozen=True)
class Diferencia:
	"""Una fila de la comparación.

	:param relativo: ruta relativa a las dos raíces (con el separador del lado izquierdo).
	:param izquierda, derecha: la entrada de cada lado, o ``None`` si no existe allí.
	"""

	relativo: str
	izquierda: base.Entrada | None
	derecha: base.Entrada | None
	estado: Estado
	accion: Accion = Accion.NADA

	@property
	def es_carpeta(self) -> bool:
		entrada = self.izquierda or self.derecha
		return bool(entrada and entrada.es_carpeta)

	def con_accion(self, accion: Accion) -> Diferencia:
		return replace(self, accion=accion)


def accion_posible(diferencia: Diferencia, accion: Accion) -> bool:
	"""Una acción solo vale si existe lo que copia o borra (y no hay archivo contra carpeta)."""
	if accion in (Accion.NADA, Accion.CONFLICTO):
		return True
	if diferencia.estado == Estado.TIPO_DISTINTO:
		return False
	if accion in (Accion.COPIAR_DERECHA, Accion.ELIMINAR_IZQUIERDA):
		return diferencia.izquierda is not None
	return diferencia.derecha is not None


def texto_accion(diferencia: Diferencia) -> str:
	"""Texto de la columna Acción: el de la acción, salvo «Archivo frente a carpeta» (no se puede copiar ni borrar)."""
	if diferencia.estado == Estado.TIPO_DISTINTO and diferencia.accion in (Accion.NADA, Accion.CONFLICTO):
		return _("Archivo frente a carpeta: nada")
	return diferencia.accion.texto


def describir_lado(entrada: base.Entrada | None) -> str:
	"""Texto de las columnas Izquierda y Derecha: «12 KB, 01/02/2026 10:00», «Carpeta, ...» o «No existe»."""
	if entrada is None:
		return _("No existe")
	fecha = formato.fecha(entrada.modificado)
	if entrada.es_carpeta:
		return f"{_('Carpeta')}, {fecha}" if fecha else _("Carpeta")
	tamano = formato.tamano_legible(entrada.tamano)
	return ", ".join(p for p in (tamano, fecha) if p)


# ── Cálculo ───────────────────────────────────────────────────────────────────

def mismo_contenido(proveedor_a: base.Proveedor, ruta_a: str, proveedor_b: base.Proveedor, ruta_b: str,
		cancelacion=None, bloque: int = _BLOQUE) -> bool:
	"""Compara byte a byte por bloques (sin cargar los archivos enteros)."""
	with proveedor_a.abrir_lectura(ruta_a) as a, proveedor_b.abrir_lectura(ruta_b) as b:
		while True:
			base.comprobar(cancelacion)
			trozo_a, trozo_b = a.read(bloque), b.read(bloque)
			if trozo_a != trozo_b:
				return False
			if not trozo_a:
				return True


def _clasificar(izquierda: base.Entrada, derecha: base.Entrada, criterio: Criterio, tolerancia: float,
		contenido_igual: Callable[[], bool]) -> Estado | None:
	"""Estado de un archivo que está en los dos lados, o ``None`` si son iguales."""
	if izquierda.es_carpeta != derecha.es_carpeta:
		return Estado.TIPO_DISTINTO
	if izquierda.es_carpeta or criterio == Criterio.NOMBRE:
		return None
	if izquierda.modificado > derecha.modificado + tolerancia:
		reciente = Estado.IZQUIERDA_MAS_RECIENTE
	elif derecha.modificado > izquierda.modificado + tolerancia:
		reciente = Estado.DERECHA_MAS_RECIENTE
	else:
		reciente = None
	if criterio == Criterio.FECHA:
		return reciente
	if criterio == Criterio.TAMANO:
		if reciente is not None:
			return reciente
		return Estado.DISTINTOS if izquierda.tamano != derecha.tamano else None
	# Contenido: lo que manda es si los bytes son iguales; la fecha solo dice cuál es más nuevo.
	if izquierda.tamano == derecha.tamano and contenido_igual():
		return None
	return reciente or Estado.DISTINTOS


def _indice(proveedor: base.Proveedor, ruta: str, subcarpetas: bool, patron: str, solo_archivos: bool,
		cancelacion, al_error) -> dict[str, tuple[str, base.Entrada]]:
	"""``{relativo normalizado: (relativo, entrada)}`` de un lado."""
	indice: dict[str, tuple[str, base.Entrada]] = {}
	for elemento in recorrer(proveedor, ruta, cancelacion, patron=patron, profundidad_maxima=None if subcarpetas else 0,
			incluir_carpetas=not solo_archivos, al_error=al_error):
		clave = elemento.relativo.replace("/", "\\").casefold()
		indice[clave] = (elemento.relativo, elemento.entrada)
	return indice


def comparar(
	izquierda: tuple[base.Proveedor, str],
	derecha: tuple[base.Proveedor, str],
	criterio: Criterio = Criterio.FECHA,
	subcarpetas: bool = True,
	patron: str = "",
	tolerancia_s: float = 2.0,
	solo_archivos: bool = False,
	cancelacion=None,
	al_error: Callable[[str, base.ErrorArchivos], None] | None = None,
) -> list[Diferencia]:
	"""Diferencias entre las dos carpetas, ordenadas por ruta relativa. Las iguales no salen.

	:param patron: solo los archivos que coinciden (las carpetas se recorren siempre).
	:param tolerancia_s: diferencia de fecha que se considera igual (FAT: 2 s; 0 = exacta).
	:param solo_archivos: no compara carpetas (Comparar carpetas de Norton, sin subcarpetas).
	:raises Cancelado: si se cancela.
	"""
	prov_i, ruta_i = izquierda
	prov_d, ruta_d = derecha
	indice_i = _indice(prov_i, ruta_i, subcarpetas, patron, solo_archivos, cancelacion, al_error)
	indice_d = _indice(prov_d, ruta_d, subcarpetas, patron, solo_archivos, cancelacion, al_error)
	diferencias: list[Diferencia] = []
	# Carpetas que solo están en un lado: su contenido no se lista aparte.
	cubiertas: list[str] = []
	for clave in sorted(set(indice_i) | set(indice_d)):
		base.comprobar(cancelacion)
		if any(clave.startswith(prefijo) for prefijo in cubiertas):
			continue
		par_i, par_d = indice_i.get(clave), indice_d.get(clave)
		entrada_i = par_i[1] if par_i else None
		entrada_d = par_d[1] if par_d else None
		relativo = (par_i or par_d)[0]
		if entrada_i is None or entrada_d is None:
			unica = entrada_i or entrada_d
			if unica.es_carpeta:
				cubiertas.append(clave + "\\")
			estado = Estado.SOLO_IZQUIERDA if entrada_i is not None else Estado.SOLO_DERECHA
			diferencias.append(Diferencia(relativo, entrada_i, entrada_d, estado))
			continue

		def contenido_igual(a=entrada_i, b=entrada_d) -> bool:
			try:
				return mismo_contenido(prov_i, a.ruta, prov_d, b.ruta, cancelacion)
			except base.Cancelado:
				raise
			except (base.ErrorArchivos, OSError) as error:
				log.debug("No se pudo comparar el contenido de %s", a.ruta, exc_info=True)
				if al_error is not None:
					al_error(a.ruta, error if isinstance(error, base.ErrorArchivos) else base.ErrorArchivos(str(error), a.ruta))
				return False

		estado = _clasificar(entrada_i, entrada_d, criterio, tolerancia_s, contenido_igual)
		if estado is not None:
			if estado == Estado.TIPO_DISTINTO:
				cubiertas.append(clave + "\\")
			diferencias.append(Diferencia(relativo, entrada_i, entrada_d, estado))
	return diferencias


def accion_propuesta(diferencia: Diferencia, direccion: Direccion, eliminar_sobrantes: bool = False) -> Accion:
	"""Acción de fábrica de una fila (la persona la puede cambiar en la lista)."""
	estado = diferencia.estado
	if estado == Estado.TIPO_DISTINTO:
		# Conflicto propio («Archivo frente a carpeta», ver ``texto_accion``): no se toca nada.
		return Accion.NADA
	if direccion == Direccion.AMBOS:
		return {
			Estado.SOLO_IZQUIERDA: Accion.COPIAR_DERECHA,
			Estado.SOLO_DERECHA: Accion.COPIAR_IZQUIERDA,
			Estado.IZQUIERDA_MAS_RECIENTE: Accion.COPIAR_DERECHA,
			Estado.DERECHA_MAS_RECIENTE: Accion.COPIAR_IZQUIERDA,
			Estado.DISTINTOS: Accion.CONFLICTO,
		}[estado]
	hacia_derecha = direccion == Direccion.A_LA_DERECHA
	origen_solo = Estado.SOLO_IZQUIERDA if hacia_derecha else Estado.SOLO_DERECHA
	destino_solo = Estado.SOLO_DERECHA if hacia_derecha else Estado.SOLO_IZQUIERDA
	origen_reciente = Estado.IZQUIERDA_MAS_RECIENTE if hacia_derecha else Estado.DERECHA_MAS_RECIENTE
	copiar = Accion.COPIAR_DERECHA if hacia_derecha else Accion.COPIAR_IZQUIERDA
	eliminar = Accion.ELIMINAR_DERECHA if hacia_derecha else Accion.ELIMINAR_IZQUIERDA
	if estado in (origen_solo, origen_reciente, Estado.DISTINTOS):
		return copiar
	if estado == destino_solo:
		return eliminar if eliminar_sobrantes else Accion.NADA
	# El destino es más reciente: no se pisa sin que la persona lo pida (tecla D o I).
	return Accion.NADA


def proponer(diferencias: Sequence[Diferencia], direccion: Direccion, eliminar_sobrantes: bool = False) -> list[Diferencia]:
	"""Las mismas filas con su acción de fábrica."""
	return [d.con_accion(accion_propuesta(d, direccion, eliminar_sobrantes)) for d in diferencias]


def accion_borrar(diferencia: Diferencia, direccion: Direccion) -> Accion | None:
	"""Tecla B: borrar en el destino de la dirección; en los dos sentidos, donde falta el otro.

	Devuelve ``None`` si en esa fila no hay nada que borrar.
	"""
	if direccion == Direccion.A_LA_DERECHA:
		accion = Accion.ELIMINAR_DERECHA
	elif direccion == Direccion.A_LA_IZQUIERDA:
		accion = Accion.ELIMINAR_IZQUIERDA
	elif diferencia.estado == Estado.SOLO_IZQUIERDA:
		accion = Accion.ELIMINAR_IZQUIERDA
	elif diferencia.estado == Estado.SOLO_DERECHA:
		accion = Accion.ELIMINAR_DERECHA
	else:
		return None
	return accion if accion_posible(diferencia, accion) else None


def marcas(diferencias: Sequence[Diferencia]) -> tuple[set[str], set[str]]:
	"""Nombres (en minúsculas) que marcar a la izquierda y a la derecha (Comparar carpetas).

	Se marca lo que no existe en el otro lado y lo más reciente; con la misma
	fecha y distinto tamaño o contenido, en los dos.
	"""
	izquierda: set[str] = set()
	derecha: set[str] = set()
	for d in diferencias:
		if d.estado in (Estado.SOLO_IZQUIERDA, Estado.IZQUIERDA_MAS_RECIENTE, Estado.DISTINTOS) and d.izquierda:
			izquierda.add(d.izquierda.nombre.casefold())
		if d.estado in (Estado.SOLO_DERECHA, Estado.DERECHA_MAS_RECIENTE, Estado.DISTINTOS) and d.derecha:
			derecha.add(d.derecha.nombre.casefold())
	return izquierda, derecha


def anuncio_marcas(izquierda: int, derecha: int) -> str:
	"""«Diferencias: 5 a la izquierda, 2 a la derecha» o «Las carpetas son iguales»."""
	if not izquierda and not derecha:
		return _("Las carpetas son iguales")
	return _("Diferencias: {i} a la izquierda, {d} a la derecha").format(i=izquierda, d=derecha)


def resumen_acciones(diferencias: Sequence[Diferencia]) -> str:
	"""«Copiar a la derecha: 3, Eliminar a la derecha: 1» (o «Nada que hacer»)."""
	cuentas: dict[Accion, int] = {}
	for d in diferencias:
		cuentas[d.accion] = cuentas.get(d.accion, 0) + 1
	partes = [f"{accion.texto}: {n}" for accion, n in cuentas.items() if accion not in (Accion.NADA, Accion.CONFLICTO)]
	if cuentas.get(Accion.CONFLICTO):
		partes.append(formato.plural(cuentas[Accion.CONFLICTO], _("{n} conflicto"), _("{n} conflictos")))
	tipo_distinto = sum(1 for d in diferencias if d.estado == Estado.TIPO_DISTINTO)
	if tipo_distinto:
		partes.append(formato.plural(tipo_distinto, _("{n} archivo frente a carpeta"), _("{n} archivos frente a carpetas")))
	return ", ".join(partes) if partes else _("Nada que hacer")
