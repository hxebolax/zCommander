# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Copiar y mover: análisis, lista de conflictos, copia segura, verificación y conflictos tardíos.

Pasos (sección 9.6 del diseño):

1. **Análisis**: recorre los orígenes (recorrido único, sin seguir enlaces),
   aplica el patrón, suma bytes, comprueba que no se copia una carpeta en sí
   misma, el espacio libre y los conflictos (destinos que ya existen).
2. **Lista de conflictos**: si la política es «preguntar» y hay conflictos, se
   piden todas las decisiones de una vez (``Decisor.resolver_conflictos``).
3. **Copia**: cada archivo va a un temporal ``~zc<hex>.tmp`` en la carpeta de
   destino; se verifica (opcional); se coloca con su nombre (``ReplaceFileW``
   si sustituye a otro); se aplican fechas, atributos y marca de la Web; en
   mover, se borra ese origen.
4. **Al final**: los conflictos tardíos (destinos que aparecieron o cambiaron
   tras el análisis) se resuelven con otra lista; los errores quedan anotados
   para «Reintentar los que fallaron».

Mover dentro del mismo volumen local es un renombrado (sin copiar datos)
cuando el destino no existe.
"""

from __future__ import annotations

import builtins
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field

from app.services import errores, formato
from app.services.operaciones import nombres
from app.services.operaciones.deshacer import AccionDeshacer, Paso
from app.services.operaciones.modelo import (
	AccionConflicto,
	AccionError,
	Conflicto,
	ContextoEjecucion,
	Estado,
	Operacion,
	Politica,
	PreguntaError,
	RespuestaConflicto,
	clave_carril,
	claves_carril,
)
from app.services.recorrido import recorrer
from app.services.seleccion import Patron
from app.services.vfs import base, rutas

log = logging.getLogger(__name__)

_TEMPORAL = re.compile(r"^~zc[0-9a-f]{8}\.tmp$", re.IGNORECASE)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def es_temporal_de_copia(nombre: str) -> bool:
	"""Los paneles no muestran estos temporales."""
	return bool(_TEMPORAL.match(nombre))


def pregunta_error(ruta: str, error: BaseException, operacion: str) -> PreguntaError:
	"""``PreguntaError`` con el ``winerror`` del ``OSError`` que lo causó (14.6): 32 o 33 = archivo en uso."""
	codigo = 0
	actual: BaseException | None = error
	while actual is not None and not codigo:
		codigo = int(getattr(actual, "winerror", 0) or 0)
		actual = actual.__cause__ or actual.__context__
	mensaje = getattr(error, "mensaje", None) or errores.mensaje_para_usuario(error) if isinstance(error, OSError) else \
		getattr(error, "mensaje", str(error))
	return PreguntaError(ruta, mensaje, operacion, codigo_windows=codigo, excepcion=error)


def _clave_relativa(relativo: str) -> str:
	"""Ruta relativa comparable: el recorrido usa «\\» o «/» según el proveedor y Windows no distingue mayúsculas."""
	return relativo.replace("/", "\\").casefold()


@dataclass
class OpcionesCopia:
	"""Opciones del diálogo de copiar o mover (sección 8.4).

	:param patron: solo los archivos que coinciden (vacío = todos).
	:param politica: qué hacer si el destino existe.
	:param subcarpeta_por_elemento: cada elemento de origen en una carpeta con su
		nombre sin extensión (extraer «cada comprimido en su carpeta»).
	:param marca_web: contenido de ``Zone.Identifier`` para cada archivo copiado
		(None = ninguno). El que lanza la operación decide: C la copia del
		comprimido, D usa ``marca_web.INTERNET``.
	:param lista_conflictos: lista única antes de copiar (si no, pregunta de uno en uno).
	"""

	patron: str = ""
	politica: Politica = Politica.PREGUNTAR
	verificar: bool = False
	conservar_fechas: bool = True
	copiar_enlaces: bool = True
	carpetas_vacias: bool = True
	subcarpeta_por_elemento: bool = False
	marca_web: str | None = None
	lista_conflictos: bool = True
	tamano_bloque: int = 1024 * 1024


@dataclass
class _Paso:
	entrada: base.Entrada
	relativo: str
	destino: str
	carpeta_destino: str
	es_carpeta: bool
	raiz: bool = False
	respuesta: RespuestaConflicto | None = None
	destino_visto: base.Entrada | None = None
	#: Carpeta que quedaría vacía en el destino (no tiene ningún archivo que copiar debajo).
	vacia: bool = False


@dataclass
class _Plan:
	pasos: list[_Paso] = field(default_factory=list)
	conflictos: list[tuple[Conflicto, _Paso]] = field(default_factory=list)
	bytes_total: int = 0
	archivos_total: int = 0


class OperacionCopiar(Operacion):
	"""Copia (o mueve) ``entradas`` de ``origen`` a ``carpeta_destino`` en ``destino``.

	:param nombre_nuevo: con un solo elemento, el nombre que tendrá en el destino.
	"""

	def __init__(
		self,
		origen: base.Proveedor,
		entradas: list[base.Entrada],
		destino: base.Proveedor,
		carpeta_destino: str,
		opciones: OpcionesCopia | None = None,
		mover: bool = False,
		nombre_nuevo: str = "",
	) -> None:
		super().__init__()
		self.tipo = "mover" if mover else "copiar"
		self.origen = origen
		self.entradas = [e for e in entradas if not e.es_superior]
		self.destino = destino
		self.carpeta_destino = carpeta_destino
		self.opciones = opciones or OpcionesCopia()
		self.mover = mover
		self.nombre_nuevo = nombre_nuevo
		self.fallidos: list[base.Entrada] = []
		self._politica = self.opciones.politica
		self._accion_deshacer = AccionDeshacer(self.descripcion())
		self._tardios: list[tuple[Conflicto, _Paso]] = []
		self._carpetas_movidas: list[str] = []
		#: Destinos que ha creado ESTA operación: nunca se sobrescriben (dos orígenes con el mismo nombre).
		self._creados: set[str] = set()
		#: Tipos de error general (disco lleno, red) a los que se respondió «Omitir todos».
		self._omitir_siempre: set[type[base.ErrorArchivos]] = set()
		#: 2.0 (14.5): pares origen → destino que de verdad se copiaron o movieron, con los nombres finales.
		self._pares_hechos: list[tuple[str, str]] = []

	def pares_hechos(self) -> list[tuple[str, str]]:
		"""Pares origen → destino copiados o movidos de verdad, con los nombres finales tras los conflictos (14.5)."""
		return list(self._pares_hechos)

	def _mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		"""Solo se pregunta al proveedor si origen y destino tienen la misma identidad de volumen (14.5).

		Las rutas de nube, FTP y SFTP son relativas («/x») y el proveedor de origen no sabe
		nada del de destino: dos cuentas distintas del mismo esquema nunca son el mismo volumen.
		"""
		if clave_carril(self.origen, ruta_a) != clave_carril(self.destino, ruta_b):
			return False
		return self.origen.mismo_volumen(ruta_a, ruta_b)

	# Identidad ---------------------------------------------------------------------

	def descripcion(self) -> str:
		n = len(self.entradas)
		que = self.entradas[0].nombre if n == 1 else formato.plural(n, _("{n} elemento"), _("{n} elementos"))
		verbo = _("Mover") if self.mover else _("Copiar")
		return _("{verbo} {que} a {destino}").format(verbo=verbo, que=que, destino=self.destino.mostrar(self.carpeta_destino))

	@property
	def carriles(self) -> frozenset[str]:
		claves = claves_carril(self.destino, [self.carpeta_destino])
		claves |= claves_carril(self.origen, [e.ruta for e in self.entradas])
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		afectadas = [(self.destino.esquema, self.carpeta_destino)]
		if self.entradas:
			afectadas.append((self.origen.esquema, self.origen.padre(self.entradas[0].ruta) or ""))
		return afectadas

	# Utilidades ----------------------------------------------------------------------

	def _ambos_locales(self) -> bool:
		return self.origen.ruta_local("x") is not None and self.destino.ruta_local("x") is not None and \
			self.origen.esquema in ("local", "resultados") and self.destino.esquema in ("local", "resultados")

	def _unir_relativo(self, carpeta: str, relativo: str) -> str:
		ruta = carpeta
		for parte in re.split(r"[\\/]", relativo):
			if parte:
				ruta = self.destino.unir(ruta, parte)
		return ruta

	def _info_destino(self, ruta: str) -> base.Entrada | None:
		try:
			return self.destino.info(ruta)
		except base.NoEncontrado:
			return None

	# Análisis ------------------------------------------------------------------------------

	def _analizar(self, ctx: ContextoEjecucion) -> _Plan:
		plan = _Plan()
		patron = Patron.analizar(self.opciones.patron) if self.opciones.patron else None
		for entrada in self.entradas:
			ctx.comprobar()
			nombre = self.nombre_nuevo if (self.nombre_nuevo and len(self.entradas) == 1) else entrada.nombre
			carpeta = self.carpeta_destino
			if self.opciones.subcarpeta_por_elemento:
				carpeta = self.destino.unir(carpeta, nombres.partir(entrada.nombre)[0])
			destino_raiz = self.destino.unir(carpeta, nombre)
			self._comprobar_no_en_si_mismo(entrada, destino_raiz)
			if entrada.es_carpeta and not entrada.es_enlace:
				plan.pasos.append(_Paso(entrada, nombre, destino_raiz, carpeta, True, raiz=True))
				for elemento in recorrer(self.origen, entrada.ruta, ctx.token,
						al_error=lambda r, e: self.anotar_error(r, e.mensaje)):
					sub = elemento.entrada
					if not sub.es_carpeta and patron is not None and not patron.coincide(sub.nombre):
						continue
					destino = self._unir_relativo(destino_raiz, elemento.relativo)
					paso = _Paso(sub, f"{nombre}\\{elemento.relativo}", destino,
						self.destino.padre(destino) or destino_raiz, sub.es_carpeta and not sub.es_enlace)
					plan.pasos.append(paso)
			else:
				if patron is not None and not entrada.es_carpeta and not patron.coincide(entrada.nombre):
					continue
				plan.pasos.append(_Paso(entrada, nombre, destino_raiz, carpeta, False, raiz=True))
		vistos: set[str] = set()
		for paso in plan.pasos:
			clave_destino = paso.destino.casefold()
			if clave_destino in vistos and not paso.es_carpeta:
				# Dos orígenes con el mismo nombre (cesta, vista plana): el segundo se renombra.
				carpeta = self.destino.padre(paso.destino) or paso.carpeta_destino
				libre = nombres.nombre_libre(self.destino.nombre(paso.destino), lambda n, c=carpeta: (
					self.destino.unir(c, n).casefold() in vistos or self.destino.existe(self.destino.unir(c, n))))
				paso.destino = self.destino.unir(carpeta, libre)
				clave_destino = paso.destino.casefold()
			vistos.add(clave_destino)
		for paso in plan.pasos:
			if paso.es_carpeta:
				continue
			plan.archivos_total += 1
			plan.bytes_total += max(0, paso.entrada.tamano)
			existente = self._info_destino(paso.destino)
			if existente is not None and not existente.es_carpeta:
				paso.destino_visto = existente
				plan.conflictos.append((Conflicto(paso.relativo, paso.entrada, existente, paso.destino), paso))
		if not self.opciones.carpetas_vacias:
			self._marcar_carpetas_vacias(plan)
		return plan

	def _marcar_carpetas_vacias(self, plan: _Plan) -> None:
		"""Marca las carpetas sin ningún archivo que copiar debajo (``operaciones.copiar_carpetas_vacias`` desactivada).

		Se decide con el plan (después del patrón) y no mirando el disco: con
		un patrón, una carpeta llena de archivos que no coinciden también
		quedaría vacía en el destino. Un enlace cuenta como contenido solo si
		se va a copiar.
		"""
		con_contenido: set[str] = set()
		for paso in plan.pasos:
			if paso.es_carpeta or (paso.entrada.es_enlace and not self.opciones.copiar_enlaces):
				continue
			partes = _clave_relativa(paso.relativo).split("\\")
			for fin in range(1, len(partes)):
				con_contenido.add("\\".join(partes[:fin]))
		for paso in plan.pasos:
			if paso.es_carpeta and _clave_relativa(paso.relativo) not in con_contenido:
				paso.vacia = True

	def _comprobar_no_en_si_mismo(self, entrada: base.Entrada, destino: str) -> None:
		if self.origen.esquema != self.destino.esquema or self.origen.contenedor is not None or self.destino.contenedor is not None:
			return
		if self.origen.esquema not in ("local", "resultados"):
			return
		if rutas.normalizar(entrada.ruta).casefold() == rutas.normalizar(destino).casefold():
			raise base.ErrorArchivos(_("El origen y el destino son el mismo: {r}").format(r=entrada.ruta), entrada.ruta)
		if entrada.es_carpeta and rutas.esta_dentro(destino, entrada.ruta):
			raise base.ErrorArchivos(
				_("No se puede copiar una carpeta dentro de sí misma: {r}").format(r=entrada.ruta), entrada.ruta)

	def _comprobar_espacio(self, ctx: ContextoEjecucion, plan: _Plan) -> None:
		if self.mover and self._mismo_volumen(self.entradas[0].ruta if self.entradas else "", self.carpeta_destino):
			return
		espacio = self.destino.espacio_libre(self.carpeta_destino)
		if espacio is None or plan.bytes_total <= espacio[0]:
			return
		with ctx.esperando():
			eleccion = ctx.decisor.elegir(
				_("Espacio insuficiente"),
				_("Hacen falta {necesario} y hay {libre} libres en el destino.").format(
					necesario=formato.tamano_legible(plan.bytes_total), libre=formato.tamano_legible(espacio[0])),
				[_("&Continuar de todos modos"), _("&Cancelar")], predeterminada=1, escape=1, operacion=self)
		if eleccion != 0:
			raise base.Cancelado()

	def _limpiar_huerfanos(self) -> None:
		"""Borra temporales ``~zc*.tmp`` de más de una hora en la carpeta de destino (restos de un cierre brusco)."""
		local = self.destino.ruta_local(self.carpeta_destino) if self.destino.esquema == "local" else None
		if not local:
			return
		limite = time.time() - 3600
		try:
			for elemento in os.scandir(rutas.con_prefijo_largo(local)):
				if es_temporal_de_copia(elemento.name) and elemento.stat().st_mtime < limite:
					os.remove(elemento.path)
		except OSError:
			log.debug("No se pudieron limpiar temporales viejos en %s", local, exc_info=True)

	# Decisiones ------------------------------------------------------------------------------

	def _decidir(self, paso: _Paso, existente: base.Entrada) -> RespuestaConflicto:
		"""Respuesta para un conflicto según la política vigente (sin preguntar)."""
		politica = self._politica
		if politica == Politica.SOBRESCRIBIR:
			return RespuestaConflicto(AccionConflicto.SOBRESCRIBIR)
		if politica == Politica.OMITIR:
			return RespuestaConflicto(AccionConflicto.OMITIR)
		if politica == Politica.SOBRESCRIBIR_SI_MAS_ANTIGUO:
			return RespuestaConflicto(AccionConflicto.SOBRESCRIBIR_SI_MAS_ANTIGUO)
		if politica == Politica.SOBRESCRIBIR_SI_CAMBIA_TAMANO:
			return RespuestaConflicto(AccionConflicto.SOBRESCRIBIR_SI_CAMBIA_TAMANO)
		if politica == Politica.RENOMBRAR_COPIA:
			return RespuestaConflicto(AccionConflicto.RENOMBRAR_COPIA)
		if politica == Politica.RENOMBRAR_EXISTENTE:
			return RespuestaConflicto(AccionConflicto.RENOMBRAR_EXISTENTE)
		return RespuestaConflicto(AccionConflicto.OMITIR)

	def _aplicar_para_todos(self, respuesta: RespuestaConflicto) -> None:
		if not respuesta.para_todos:
			return
		equivalencias = {
			AccionConflicto.SOBRESCRIBIR: Politica.SOBRESCRIBIR, AccionConflicto.OMITIR: Politica.OMITIR,
			AccionConflicto.SOBRESCRIBIR_SI_MAS_ANTIGUO: Politica.SOBRESCRIBIR_SI_MAS_ANTIGUO,
			AccionConflicto.SOBRESCRIBIR_SI_CAMBIA_TAMANO: Politica.SOBRESCRIBIR_SI_CAMBIA_TAMANO,
			AccionConflicto.RENOMBRAR_COPIA: Politica.RENOMBRAR_COPIA,
			AccionConflicto.RENOMBRAR_EXISTENTE: Politica.RENOMBRAR_EXISTENTE,
		}
		if respuesta.accion in equivalencias:
			self._politica = equivalencias[respuesta.accion]

	def _resolver_lista(self, ctx: ContextoEjecucion, conflictos: list[tuple[Conflicto, _Paso]]) -> None:
		if not conflictos:
			return
		if self._politica != Politica.PREGUNTAR:
			for conflicto, paso in conflictos:
				paso.respuesta = self._decidir(paso, conflicto.destino)
			return
		if self.opciones.lista_conflictos:
			with ctx.esperando():
				respuestas = ctx.decisor.resolver_conflictos(self, [c for c, _p in conflictos])
			if respuestas is None:
				raise base.Cancelado()
			for (_conflicto, paso), respuesta in zip(conflictos, respuestas, strict=False):
				if respuesta.accion == AccionConflicto.CANCELAR:
					raise base.Cancelado()
				paso.respuesta = respuesta
			return
		for conflicto, paso in conflictos:
			if self._politica != Politica.PREGUNTAR:
				paso.respuesta = self._decidir(paso, conflicto.destino)
				continue
			with ctx.esperando():
				respuesta = ctx.decisor.preguntar_conflicto(self, conflicto)
			if respuesta.accion == AccionConflicto.CANCELAR:
				raise base.Cancelado()
			self._aplicar_para_todos(respuesta)
			paso.respuesta = respuesta

	# Ejecución --------------------------------------------------------------------------------

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		"""Con conexiones propias (``clonar``) y escrituras agrupadas (``transaccion``).

		Si se cancela o falla dentro de la transacción de un comprimido, el
		proveedor no escribe nada (ver ``Proveedor.transaccion``).
		"""
		from contextlib import ExitStack

		origen_panel, destino_panel = self.origen, self.destino
		self.origen = origen_panel.clonar()
		self.destino = destino_panel.clonar() if destino_panel is not origen_panel else self.origen
		if self.opciones.marca_web is None:
			self.opciones.marca_web = self._marca_web_automatica()
		try:
			with ExitStack() as pila:
				pila.enter_context(self.destino.transaccion())
				if self.mover and self.origen is not self.destino:
					pila.enter_context(self.origen.transaccion())
				self._ejecutar(ctx)
		finally:
			for clon, original in ((self.origen, origen_panel), (self.destino, destino_panel)):
				if clon is not original:
					try:
						clon.cerrar()
					except Exception:  # noqa: BLE001 - cerrar el clon no debe tapar el resultado
						log.debug("No se pudo cerrar la conexión clonada", exc_info=True)
			self.origen, self.destino = origen_panel, destino_panel

	def _marca_web_automatica(self) -> str | None:
		"""Marca de la Web: «Internet» si el origen es un servidor; la del comprimido si viene de uno marcado."""
		from app.services.windows import marca_web

		if self.destino.esquema != "local":
			return None
		if self.origen.esquema in ("ftp", "ftps", "sftp"):
			return marca_web.INTERNET
		if self.origen.contenedor is not None:
			contenedor, ruta_archivo = self.origen.contenedor
			local = contenedor.ruta_local(ruta_archivo)
			return marca_web.leer(local) if local else None
		return None

	def _ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.ANALIZANDO)
		self._limpiar_huerfanos()
		plan = self._analizar(ctx)
		self.progresar(archivos_total=plan.archivos_total, bytes_total=plan.bytes_total)
		self._comprobar_espacio(ctx, plan)
		self._resolver_lista(ctx, plan.conflictos)
		self.cambiar_estado(Estado.EJECUTANDO)
		movidas_enteras: set[int] = set()
		if self.mover:
			movidas_enteras = self._mover_por_renombrado(ctx, plan)
		# 2.0 (14.5): el destino puede copiar todo el plan de una vez (nubes); si no, archivo a archivo.
		if not movidas_enteras and self._transferir_lote(ctx, plan):
			if self.mover:
				self._borrar_carpetas_movidas()
			self.deshacer = self._accion_deshacer if self._accion_deshacer.pasos else None
			return
		omitir_bajo: list[str] = []
		for indice, paso in enumerate(plan.pasos):
			ctx.comprobar()
			if any(paso.relativo.startswith(prefijo) for prefijo in omitir_bajo):
				continue
			if paso.raiz and indice in movidas_enteras:
				if paso.es_carpeta:
					omitir_bajo.append(paso.relativo + "\\")
				continue
			if paso.es_carpeta:
				if paso.vacia:
					# No se crea en el destino; al mover, la de origen se quita igualmente si queda vacía.
					if self.mover and self.origen.esquema in ("local", "resultados"):
						self._carpetas_movidas.append(paso.entrada.ruta)
					continue
				self._crear_carpeta(paso)
				continue
			self._copiar_con_reintentos(ctx, paso)
		if self._tardios:
			tardios, self._tardios = self._tardios, []
			for _conflicto, paso in tardios:
				paso.respuesta = None
			self._resolver_lista(ctx, tardios)
			for _conflicto, paso in tardios:
				self._copiar_con_reintentos(ctx, paso, tardio=True)
		if self.mover:
			self._borrar_carpetas_movidas()
		self.deshacer = self._accion_deshacer if self._accion_deshacer.pasos else None

	def _transferir_lote(self, ctx: ContextoEjecucion, plan: _Plan) -> bool:
		"""``Proveedor.transferir_lote`` con la lista ya decidida (14.5). Falso si el destino no lo admite."""
		if self.opciones.patron:
			return False
		pares: list[tuple[str, str]] = []
		por_origen: dict[str, _Paso] = {}
		for paso in plan.pasos:
			if paso.es_carpeta or paso.entrada.es_enlace:
				continue
			respuesta = paso.respuesta
			destino = paso.destino
			if respuesta is not None:
				if respuesta.accion == AccionConflicto.OMITIR:
					continue
				if respuesta.accion == AccionConflicto.RENOMBRAR and respuesta.nombre_nuevo:
					destino = self.destino.unir(paso.carpeta_destino, respuesta.nombre_nuevo)
			pares.append((paso.entrada.ruta, destino))
			por_origen[paso.entrada.ruta] = paso
		if not pares:
			return False
		hechos_antes = self.instantanea().bytes_hechos

		def progreso(hechos: int, total: int) -> None:
			self.progresar(bytes_hechos=hechos_antes + hechos)

		resultados = self.destino.transferir_lote(self.origen, pares, self.mover, progreso, ctx.token)
		if resultados is None:
			return False
		for paso in plan.pasos:
			if paso.es_carpeta and not paso.vacia:
				self._crear_carpeta(paso)
		for resultado in resultados:
			paso = por_origen.get(resultado.origen)
			if paso is None:
				continue
			if resultado.ok:
				self._pares_hechos.append((resultado.origen, resultado.destino))
				self.sumar(archivos_hechos=1)
			else:
				mensaje = resultado.error.mensaje if resultado.error is not None else _("No se pudo copiar")
				self._fallo(paso, mensaje)
		return True

	def _mover_por_renombrado(self, ctx: ContextoEjecucion, plan: _Plan) -> set[int]:
		"""Mover en el mismo volumen: renombra cada elemento raíz cuyo destino no existe.

		En local con la API de Windows; en otro proveedor, con su ``renombrar``, y solo si
		origen y destino tienen la misma identidad de volumen (``clave_carril``, 14.5).
		"""
		hechos: set[int] = set()
		if self.opciones.patron:
			return hechos
		locales = self._ambos_locales()
		if not locales and self.origen is not self.destino and not self.destino.capacidades.renombrar_barato:
			return hechos
		from app.services.windows import copia_nativa

		for indice, paso in enumerate(plan.pasos):
			if not paso.raiz or paso.vacia:
				continue
			ctx.comprobar()
			if not self._mismo_volumen(paso.entrada.ruta, paso.destino) or self.destino.existe(paso.destino):
				continue
			try:
				self.progresar(actual=paso.entrada.nombre)
				if locales:
					copia_nativa.mover(paso.entrada.ruta, paso.destino)
				else:
					self.destino.renombrar(paso.entrada.ruta, paso.destino)
			except base.ErrorArchivos as error:
				log.info("No se pudo mover por renombrado %s: %s; se copiará", paso.entrada.ruta, error.mensaje)
				continue
			hechos.add(indice)
			self._pares_hechos.append((paso.entrada.ruta, paso.destino))
			self._accion_deshacer.pasos.append(Paso("renombrar", paso.destino, antes=paso.entrada.ruta))
			if paso.es_carpeta and not self.opciones.carpetas_vacias:
				self._quitar_vacias_movidas(plan, paso)
			# Cuenta los archivos que contenía para el progreso.
			contenidos = [p for p in plan.pasos if not p.es_carpeta and (p is paso or p.relativo.startswith(paso.relativo + "\\"))]
			self.sumar(archivos_hechos=len(contenidos), bytes_hechos=sum(max(0, p.entrada.tamano) for p in contenidos))
		return hechos

	def _quitar_vacias_movidas(self, plan: _Plan, raiz: _Paso) -> None:
		"""Tras mover una carpeta entera por renombrado, quita las subcarpetas vacías que no debían llegar.

		El renombrado lleva el árbol completo; sin «Copiar también las carpetas
		vacías» se quitan después, de dentro afuera. Así el resultado es el
		mismo que al mover copiando: no quedan ni en el destino ni en el origen.
		"""
		prefijo = _clave_relativa(raiz.relativo) + "\\"
		vacias = [p for p in plan.pasos if p.vacia and _clave_relativa(p.relativo).startswith(prefijo)]
		for paso in sorted(vacias, key=lambda p: len(p.destino), reverse=True):
			try:
				self.destino.eliminar(paso.destino, recursivo=False)
			except base.ErrorArchivos:
				log.debug("No se pudo quitar la carpeta vacía movida %s", paso.destino, exc_info=True)

	def _crear_carpeta(self, paso: _Paso) -> None:
		existente = self._info_destino(paso.destino)
		if existente is not None and existente.es_carpeta:
			return
		if existente is not None:
			self.anotar_error(paso.destino, _("Ya existe un archivo con el nombre de la carpeta."))
			return
		try:
			self.destino.crear_carpeta(paso.destino)
			if self.destino.esquema == "local" and not self.mover:
				# La raíz va entera a la papelera si nada cambió dentro; las subcarpetas nuevas se quitan
				# si quedan vacías (deshacer comprueba cada archivo antes de tocar nada).
				self._accion_deshacer.pasos.append(Paso("a_papelera" if paso.raiz else "quitar_carpeta", paso.destino))
		except base.YaExiste:
			return
		except base.ErrorArchivos as error:
			self.anotar_error(paso.destino, error.mensaje)
		if self.mover and self.origen.esquema in ("local", "resultados"):
			self._carpetas_movidas.append(paso.entrada.ruta)

	def _copiar_con_reintentos(self, ctx: ContextoEjecucion, paso: _Paso, tardio: bool = False) -> None:
		while True:
			try:
				self._copiar_archivo(ctx, paso, tardio)
				return
			except base.Cancelado:
				raise
			except base.YaExiste as error:
				if self._politica == Politica.PREGUNTAR and not tardio:
					existente = self._info_destino(paso.destino)
					if existente is not None:
						paso.respuesta = None
						paso.destino_visto = existente
						self._tardios.append((Conflicto(paso.relativo, paso.entrada, existente, paso.destino), paso))
						return
				self._fallo(paso, error.mensaje)
				return
			except (base.SinEspacio, base.ErrorRed) as error:
				# Afecta a todo: se pregunta (reintentar, omitir o cancelar), salvo que ya se dijera «Omitir todos».
				clase = base.SinEspacio if isinstance(error, base.SinEspacio) else base.ErrorRed
				omitir_siempre = self._errores_omitidos()
				if clase in omitir_siempre:
					self._fallo(paso, error.mensaje)
					return
				with ctx.esperando():
					accion = ctx.decisor.preguntar_error(self, pregunta_error(paso.entrada.ruta, error, self.descripcion()))
				if accion == AccionError.REINTENTAR:
					continue
				if accion in (AccionError.OMITIR, AccionError.OMITIR_TODOS):
					if accion == AccionError.OMITIR_TODOS:
						omitir_siempre.add(clase)
					self._fallo(paso, error.mensaje)
					return
				raise base.Cancelado() from error
			except base.ErrorArchivos as error:
				self._fallo(paso, error.mensaje)
				return
			except OSError as error:
				self._fallo(paso, errores.mensaje_para_usuario(error))
				return

	def _errores_omitidos(self) -> set[type[base.ErrorArchivos]]:
		"""Tipos de error con «Omitir todos», guardados en la operación raíz.

		Sincronizar y extraer crean copias como suboperaciones: la persona ve
		una sola operación, así que su «Omitir todos» vale para todas ellas.
		"""
		raiz = self.raiz()
		if isinstance(raiz, OperacionCopiar):
			return raiz._omitir_siempre
		compartidos = getattr(raiz, "_omitir_errores_copia", None)
		if compartidos is None:
			compartidos = set()
			raiz._omitir_errores_copia = compartidos  # type: ignore[attr-defined]
		return compartidos

	def _fallo(self, paso: _Paso, mensaje: str) -> None:
		self.anotar_error(paso.entrada.ruta, mensaje)
		self.fallidos.append(paso.entrada)
		self.sumar(omitidos=1)

	def _copiar_archivo(self, ctx: ContextoEjecucion, paso: _Paso, tardio: bool) -> None:
		entrada = paso.entrada
		destino = paso.destino
		self.progresar(actual=paso.relativo, bytes_actual=0, total_actual=max(0, entrada.tamano))
		existente = self._info_destino(destino)
		if existente is not None and existente.es_carpeta:
			raise base.YaExiste(_("Ya existe una carpeta con ese nombre: {n}").format(n=destino), destino)
		respuesta = paso.respuesta
		if existente is not None:
			cambiado = paso.destino_visto is None or existente.tamano != paso.destino_visto.tamano or \
				abs(existente.modificado - paso.destino_visto.modificado) > 2
			if respuesta is None or cambiado:
				if not tardio and self._politica == Politica.PREGUNTAR:
					paso.destino_visto = existente
					self._tardios.append((Conflicto(paso.relativo, entrada, existente, destino), paso))
					return
				respuesta = self._decidir(paso, existente)
			destino = self._aplicar_respuesta(respuesta, entrada, existente, destino)
			if destino is None:
				self.sumar(archivos_hechos=1, omitidos=1, bytes_hechos=max(0, entrada.tamano))
				return
		elif respuesta is not None and respuesta.accion == AccionConflicto.RENOMBRAR and respuesta.nombre_nuevo:
			destino = self.destino.unir(paso.carpeta_destino, respuesta.nombre_nuevo)
		visto = self._info_destino(destino)
		sobrescribe = visto is not None
		if sobrescribe and destino.casefold() in self._creados:
			# Lo creó esta misma operación (otro origen con el mismo nombre): nunca se pisa.
			carpeta = self.destino.padre(destino) or self.carpeta_destino
			destino = self.destino.unir(carpeta, nombres.nombre_libre(self.destino.nombre(destino),
				lambda n: self.destino.existe(self.destino.unir(carpeta, n))))
			visto, sobrescribe = None, False
		if entrada.es_enlace:
			if not self._copiar_enlace(entrada, destino):
				return
		else:
			self._transferir(ctx, entrada, destino, sobrescribe, visto)
		self._creados.add(destino.casefold())
		self._pares_hechos.append((entrada.ruta, destino))
		if self.mover:
			self.origen.eliminar(entrada.ruta)
		elif not sobrescribe and self.destino.esquema == "local":
			try:
				st = os.stat(rutas.con_prefijo_largo(destino))
				self._accion_deshacer.pasos.append(Paso("a_papelera", destino, tamano=st.st_size, modificado=st.st_mtime))
			except OSError:
				log.debug("Sin datos para deshacer %s", destino, exc_info=True)
		self.sumar(archivos_hechos=1)

	def _aplicar_respuesta(self, respuesta: RespuestaConflicto, entrada: base.Entrada, existente: base.Entrada,
			destino: str) -> str | None:
		"""Destino final según la respuesta, o None si se omite."""
		accion = respuesta.accion
		if accion == AccionConflicto.OMITIR:
			return None
		if accion == AccionConflicto.SOBRESCRIBIR_SI_MAS_ANTIGUO:
			return destino if entrada.modificado > existente.modificado + 2 else None
		if accion == AccionConflicto.SOBRESCRIBIR_SI_CAMBIA_TAMANO:
			return destino if entrada.tamano != existente.tamano else None
		carpeta = self.destino.padre(destino) or self.carpeta_destino
		if accion == AccionConflicto.RENOMBRAR and respuesta.nombre_nuevo:
			return self.destino.unir(carpeta, respuesta.nombre_nuevo)
		if accion == AccionConflicto.RENOMBRAR_COPIA:
			libre = nombres.nombre_libre(self.destino.nombre(destino), lambda n: self.destino.existe(self.destino.unir(carpeta, n)))
			return self.destino.unir(carpeta, libre)
		if accion == AccionConflicto.RENOMBRAR_EXISTENTE:
			libre = nombres.nombre_libre(self.destino.nombre(destino), lambda n: self.destino.existe(self.destino.unir(carpeta, n)))
			self.destino.renombrar(destino, self.destino.unir(carpeta, libre))
			return destino
		return destino  # SOBRESCRIBIR

	def _transferir(self, ctx: ContextoEjecucion, entrada: base.Entrada, destino: str, sobrescribe: bool,
			esperado: base.Entrada | None = None) -> None:
		carpeta = self.destino.padre(destino) or self.carpeta_destino
		local_a_local = self._ambos_locales() and self.origen.contenedor is None
		hechos_antes = self.instantanea().bytes_hechos
		if not local_a_local and self._transferir_por_proveedor(ctx, entrada, destino, hechos_antes):
			return
		capacidades = self.destino.capacidades
		if not local_a_local and (capacidades.escritura_atomica or not capacidades.renombrar_barato):
			# 2.0 (14.5): la subida solo aparece completa al terminar (o renombrar es caro):
			# se escribe directamente con el nombre final, sin temporal.
			self._copiar_por_bloques(ctx, entrada, destino, hechos_antes)
			self.progresar(bytes_hechos=hechos_antes + max(0, entrada.tamano))
			self._fechas_y_atributos(entrada, destino)
			return
		temporal = self.destino.unir(carpeta, nombres.temporal())
		try:
			if local_a_local:
				from app.services.windows import copia_nativa

				def progreso(hechos: int, total: int) -> None:
					self.progresar(bytes_actual=hechos, total_actual=total, bytes_hechos=hechos_antes + hechos)

				copia_nativa.copiar(entrada.ruta, temporal, progreso, ctx.token, esperar_pausa=ctx.comprobar)
				if entrada.solo_lectura:
					from app.services.windows import atributos

					atributos.cambiar_atributos(rutas.con_prefijo_largo(temporal), quitar=formato.SOLO_LECTURA)
			else:
				self._copiar_por_bloques(ctx, entrada, temporal, hechos_antes)
			if self.opciones.verificar:
				self.cambiar_estado(Estado.VERIFICANDO)
				try:
					if self._suma(self.origen, entrada.ruta, ctx) != self._suma(self.destino, temporal, ctx):
						raise base.ErrorArchivos(_("La copia no coincide con el original."), entrada.ruta)
				finally:
					self.cambiar_estado(Estado.EJECUTANDO)
			self._colocar(temporal, destino, sobrescribe, esperado)
		except BaseException:
			try:
				# Si el nombre de destino quedó libre (sustitución a medias), el temporal ES la
				# copia buena: se pone en su sitio en lugar de borrarlo.
				if self.destino.existe(temporal):
					if sobrescribe and not self.destino.existe(destino):
						self.destino.renombrar(temporal, destino)
					else:
						self.destino.eliminar(temporal)
			except base.ErrorArchivos:
				log.warning("No se pudo recolocar ni borrar el temporal %s", temporal, exc_info=True)
			self.progresar(bytes_hechos=hechos_antes)
			raise
		self.progresar(bytes_hechos=hechos_antes + max(0, entrada.tamano))
		self._fechas_y_atributos(entrada, destino)

	def _transferir_por_proveedor(self, ctx: ContextoEjecucion, entrada: base.Entrada, destino: str, hechos_antes: int) -> bool:
		"""``Proveedor.transferir`` del destino (copia en el servidor, subida por fragmentos, 14.5)."""

		def progreso(hechos: int, total: int) -> None:
			self.progresar(bytes_actual=hechos, total_actual=total, bytes_hechos=hechos_antes + hechos)

		if not self.destino.transferir(self.origen, entrada.ruta, destino, progreso, ctx.token):
			return False
		self.progresar(bytes_hechos=hechos_antes + max(0, entrada.tamano))
		self._fechas_y_atributos(entrada, destino)
		return True

	def _copiar_por_bloques(self, ctx: ContextoEjecucion, entrada: base.Entrada, temporal: str, hechos_antes: int) -> None:
		bloque = max(64 * 1024, self.opciones.tamano_bloque)
		copiados = 0
		with self.origen.abrir_lectura(entrada.ruta) as fuente, self.destino.abrir_escritura(temporal, max(-1, entrada.tamano)) as salida:
			while True:
				ctx.comprobar()
				datos = fuente.read(bloque)
				if not datos:
					break
				salida.write(datos)
				copiados += len(datos)
				self.progresar(bytes_actual=copiados, bytes_hechos=hechos_antes + copiados)

	def _suma(self, proveedor: base.Proveedor, ruta: str, ctx: ContextoEjecucion) -> str:
		suma = hashlib.sha256()
		with proveedor.abrir_lectura(ruta) as flujo:
			while datos := flujo.read(1024 * 1024):
				ctx.comprobar()
				suma.update(datos)
		return suma.hexdigest()

	def _colocar(self, temporal: str, destino: str, sobrescribe: bool, esperado: base.Entrada | None) -> None:
		"""Pone el temporal en su sitio sin pisar nada inesperado.

		Si el destino no existía, se mueve SIN reemplazar: si alguien lo creó
		mientras se copiaba, falla con ``YaExiste`` y pasa a conflicto tardío.
		Si existía, se comprueba que sigue igual que cuando se decidió.
		"""
		actual = self._info_destino(destino)
		if not sobrescribe and actual is not None:
			raise base.YaExiste(_("«{n}» apareció en el destino mientras se copiaba.").format(n=destino), destino)
		if sobrescribe and esperado is not None and actual is not None and (
				actual.tamano != esperado.tamano or abs(actual.modificado - esperado.modificado) > 2):
			raise base.YaExiste(_("«{n}» cambió en el destino mientras se copiaba.").format(n=destino), destino)
		if self.destino.esquema == "local":
			from app.services.windows import atributos, copia_nativa

			if sobrescribe and actual is not None:
				if actual.solo_lectura:
					atributos.cambiar_atributos(rutas.con_prefijo_largo(destino), quitar=formato.SOLO_LECTURA)
				copia_nativa.sustituir(temporal, destino)
			else:
				copia_nativa.mover(temporal, destino, reemplazar=False)
			return
		if sobrescribe and actual is not None:
			# Sin sustitución atómica: se aparta el destino, se coloca la copia y se borra lo apartado;
			# si colocar falla, se devuelve el original a su nombre.
			carpeta = self.destino.padre(destino) or self.carpeta_destino
			respaldo = self.destino.unir(carpeta, nombres.temporal().replace(".tmp", ".bak"))
			self.destino.renombrar(destino, respaldo)
			try:
				self.destino.renombrar(temporal, destino)
			except base.ErrorArchivos:
				self.destino.renombrar(respaldo, destino)
				raise
			self.destino.eliminar(respaldo)
			return
		self.destino.renombrar(temporal, destino)

	def _fechas_y_atributos(self, entrada: base.Entrada, destino: str) -> None:
		if entrada.es_enlace:
			# Cambiar fechas de un enlace las cambiaría en lo que apunta.
			return
		try:
			if self.opciones.conservar_fechas and entrada.modificado:
				self.destino.fijar_tiempos(destino, entrada.modificado, entrada.creado)
			if self.destino.esquema == "local" and entrada.atributos and self.opciones.conservar_fechas:
				self.destino.fijar_atributos(destino, entrada.atributos)
			if self.opciones.marca_web and self.destino.esquema == "local":
				from app.services.windows import marca_web

				marca_web.escribir(destino, self.opciones.marca_web)
		except base.ErrorArchivos as error:
			log.info("No se pudieron aplicar fechas o atributos a %s: %s", destino, error.mensaje)

	def _copiar_enlace(self, entrada: base.Entrada, destino: str) -> bool:
		"""Recrea el enlace en el destino. ``False`` si se omitió (y entonces, al mover, el origen se conserva)."""
		if not self.opciones.copiar_enlaces:
			self.sumar(omitidos=1)
			return False
		if not self._ambos_locales():
			raise base.NoAdmitido(_("Los enlaces solo se copian entre carpetas locales."), entrada.ruta)
		objetivo = entrada.destino_enlace
		try:
			if entrada.es_carpeta:
				try:
					os.symlink(objetivo, destino, target_is_directory=True)
				except OSError:
					import _winapi

					_winapi.CreateJunction(objetivo, destino)
			else:
				from app.services.windows import copia_nativa

				copia_nativa.copiar(entrada.ruta, destino, copiar_enlace=True)
		except OSError as error:
			raise errores.convertir(error, entrada.ruta) from error
		return True

	def _borrar_carpetas_movidas(self) -> None:
		"""Tras mover, quita de dentro hacia fuera las carpetas de origen que quedaron vacías."""
		for carpeta in sorted(set(self._carpetas_movidas), key=len, reverse=True):
			try:
				self.origen.eliminar(carpeta, recursivo=False)
			except base.ErrorArchivos:
				log.debug("La carpeta de origen %s no quedó vacía", carpeta, exc_info=True)
