# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Operaciones del bloque C: comprimir, extraer, probar, sumas, dividir y unir.

Todas siguen las reglas de ``modelo.Operacion``: se ejecutan en un hilo del
``GestorOperaciones``, declaran sus carriles (el comprimido y los volúmenes de
origen y destino), comprueban pausa y cancelación entre bloques y anotan los
errores de cada elemento sin parar el resto.

- ``OperacionComprimir``: escribe en un temporal ``~zc*.tmp`` junto al destino
  y solo lo coloca al terminar. «Añadir» a un ZIP existente usa la
  transacción del proveedor ZIP (los miembros que ya estaban se copian en
  crudo); a un TAR o 7z existente, lo reescribe con lo que tenía más lo
  nuevo. «Mover al comprimido» prueba el comprimido y solo entonces borra los
  originales, las dos cosas como suboperaciones (``ejecutar_sub``).
  2.0 (8.6): las variantes del ZIP (Zstandard y AES-256), 7z con 7za (que
  comprime al cerrar, con su progreso) y los formatos de un solo archivo
  (``.gz``, ``.bz2``, ``.xz``, ``.zst``), que crean uno por elemento.
- ``OperacionExtraer``: para cada comprimido, una ``OperacionCopiar`` desde su
  proveedor (lista de conflictos y marca de la Web incluidas) como suboperación.
- ``OperacionProbar``: ``Proveedor.probar`` de cada comprimido.
- ``OperacionCrearSumas``, ``OperacionVerificarSumas``, ``OperacionDividir`` y
  ``OperacionUnir``: envuelven ``services/sumas.py`` y ``services/dividir.py``.
"""

from __future__ import annotations

import builtins
import logging
import os
import re
from dataclasses import dataclass, replace

from app.services import comprimir as servicio_comprimir
from app.services import dividir as servicio_dividir
from app.services import errores, formato, sumas
from app.services.operaciones import nombres
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar
from app.services.operaciones.eliminar import OperacionEliminar
from app.services.operaciones.modelo import ContextoEjecucion, Estado, Operacion, claves_carril
from app.services.vfs import base, resolver, rutas

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class _Pausable:
	"""Cancelación para los servicios que además aplica la pausa de la operación.

	Los servicios solo llaman a ``is_set()``; aquí eso pasa por
	``ctx.comprobar()``, que detiene el hilo mientras la operación está en pausa
	y lanza ``Cancelado`` si se canceló. Solo vale en el hilo de la operación.
	"""

	def __init__(self, ctx: ContextoEjecucion) -> None:
		self._ctx = ctx

	def is_set(self) -> bool:
		self._ctx.comprobar()
		return False


def _que(entradas: list[base.Entrada]) -> str:
	n = len(entradas)
	return entradas[0].nombre if n == 1 else formato.plural(n, _("{n} elemento"), _("{n} elementos"))


def _colocar(temporal: str, destino: str) -> None:
	"""Pone el temporal con su nombre definitivo (sustituyendo si ya existe)."""
	from app.services.windows import copia_nativa

	if os.path.exists(rutas.con_prefijo_largo(destino)):
		copia_nativa.sustituir(temporal, destino)
	else:
		copia_nativa.mover(temporal, destino)


def _borrar(ruta: str) -> None:
	try:
		if os.path.exists(rutas.con_prefijo_largo(ruta)):
			os.remove(rutas.con_prefijo_largo(ruta))
	except OSError:
		log.warning("No se pudo borrar %s", ruta, exc_info=True)


# ── Comprimir ────────────────────────────────────────────────────────────────


@dataclass
class OpcionesComprimir:
	"""Lo que se elige en el diálogo de Comprimir (sección 8.15).

	:param anadir: si el comprimido ya existe, añadir a lo que tiene (True) o sustituirlo (False).
		Vale para el comprimido único (la interfaz pregunta antes de lanzar).
	:param si_existe: con ``por_elemento``, qué hacer con cada comprimido que ya existe:
		``"anadir"``, ``"sustituir"``, ``"renombrar"`` (« (2)» antes de la extensión) u ``"omitir"``.
		Vacío: la operación lo pregunta por cada uno (nunca añade en silencio).
	"""

	formato: str = "zip"
	nivel: str = "normal"
	contrasena: str = ""
	por_elemento: bool = False
	mover: bool = False
	anadir: bool = True
	si_existe: str = ""
	#: 2.0: solo ZIP: «zstd» o «aes» (vacío: el método de Preferencias, sin cifrar).
	variante: str = ""
	#: 2.0: solo 7z con contraseña: cifra también los nombres (el índice).
	cifrar_nombres: bool = False


#: Respuestas a «ya existe» con un comprimido por cada elemento, en el orden de los botones.
SI_EXISTE = ("anadir", "sustituir", "renombrar", "omitir")


def botones_si_existe() -> list[str]:
	"""Botones de la pregunta «ya existe» (la interfaz y la operación usan los mismos)."""
	return [_("&Añadir al comprimido"), _("&Sustituirlo"), _("Cambiar el &nombre"), _("&Omitirlo"), _("&Cancelar")]


class OperacionComprimir(Operacion):
	"""Comprime ``entradas`` de ``origen`` en ``destino`` (ruta local del comprimido).

	Con ``opciones.por_elemento``, ``destino`` es la CARPETA donde se crea un
	comprimido por cada elemento, con su nombre.
	"""

	tipo = "comprimir"

	def __init__(self, origen: base.Proveedor, entradas: list[base.Entrada], destino: str,
			opciones: OpcionesComprimir | None = None) -> None:
		super().__init__()
		self.origen = origen
		self.entradas = [e for e in entradas if not e.es_superior]
		self.destino = destino
		self.opciones = opciones or OpcionesComprimir()
		#: Comprimidos creados o actualizados.
		self.creados: list[str] = []
		self.originales_borrados = False
		#: Elementos cuyo comprimido ya existía y se omitió (al mover, no se borran).
		self._omitidas: list[base.Entrada] = []

	def descripcion(self) -> str:
		if self.opciones.por_elemento:
			return _("Comprimir {que} en {d}").format(que=_que(self.entradas), d=self.destino)
		return _("Comprimir {que} en {d}").format(que=_que(self.entradas), d=os.path.basename(self.destino))

	@property
	def carriles(self) -> frozenset[str]:
		claves = claves_carril(self.origen, [e.ruta for e in self.entradas])
		claves |= claves_carril(resolver.proveedor_local(), [self.destino])
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		carpeta = self.destino if self.opciones.por_elemento else (os.path.dirname(self.destino) or self.destino)
		afectadas = [("local", carpeta)]
		if self.opciones.mover and self.entradas:
			afectadas.append((self.origen.esquema, self.origen.padre(self.entradas[0].ruta) or ""))
		return afectadas

	def _trabajos(self) -> list[tuple[str, list[base.Entrada]]]:
		ext = servicio_comprimir.extension(self.opciones.formato)
		if servicio_comprimir.es_flujo(self.opciones.formato):
			# Un archivo comprimido por cada archivo, con su nombre completo más la extensión («a.txt.gz»).
			archivos = [e for e in self.entradas if not e.es_carpeta]
			if not self.opciones.por_elemento and len(archivos) == 1 and len(self.entradas) == 1:
				return [(self.destino, archivos)]
			carpeta = self.destino if self.opciones.por_elemento else (os.path.dirname(self.destino) or self.destino)
			return [(os.path.join(carpeta, e.nombre + ext), [e]) for e in archivos]
		if not self.opciones.por_elemento:
			return [(self.destino, self.entradas)]
		trabajos = []
		for entrada in self.entradas:
			raiz = entrada.nombre if entrada.es_carpeta else servicio_comprimir.quitar_extension_comprimido(entrada.nombre)
			trabajos.append((os.path.join(self.destino, raiz + ext), [entrada]))
		return trabajos

	def destinos(self) -> list[str]:
		"""Rutas de los comprimidos que se crearán (uno, o uno por elemento): la interfaz mira cuáles existen."""
		return [ruta for ruta, _entradas in self._trabajos()]

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.ANALIZANDO)
		cancelacion = _Pausable(ctx)
		if servicio_comprimir.es_flujo(self.opciones.formato):
			for entrada in self.entradas:
				if entrada.es_carpeta:
					self.anotar_error(entrada.ruta, _("«{n}» es una carpeta: los formatos .gz, .bz2, .xz y .zst comprimen un solo "
						"archivo. Use ZIP, 7z o TAR para las carpetas.").format(n=entrada.nombre))
					self._omitidas.append(entrada)
		planes = []
		for ruta, entradas in self._trabajos():
			fuentes = servicio_comprimir.reunir(self.origen, entradas, cancelacion, al_error=self.anotar_error)
			planes.append((ruta, entradas, fuentes))
		archivos = [f for _r, _e, fuentes in planes for f in fuentes if not f.es_carpeta]
		self.progresar(archivos_total=len(archivos), bytes_total=sum(f.tamano for f in archivos))
		self.cambiar_estado(Estado.EJECUTANDO)
		for ruta, entradas, fuentes in planes:
			ctx.comprobar()
			anadir = self.opciones.anadir
			if self.opciones.por_elemento and os.path.exists(rutas.con_prefijo_largo(ruta)):
				decision = self._si_existe(ctx, ruta)
				if decision == "omitir":
					self._omitir(entradas, fuentes)
					continue
				if decision == "renombrar":
					ruta = self._nombre_libre(ruta)
				anadir = decision == "anadir"
			self._crear(ctx, ruta, fuentes, anadir)
			self.creados.append(ruta)
		if self.opciones.mover and self.creados:
			self._borrar_originales(ctx)

	def _si_existe(self, ctx: ContextoEjecucion, ruta: str) -> str:
		"""Qué hacer con un comprimido por elemento que ya existe: lo elegido antes o, si no, se pregunta."""
		if self.opciones.si_existe in SI_EXISTE:
			return self.opciones.si_existe
		botones = botones_si_existe()
		with ctx.esperando():
			eleccion = ctx.decisor.elegir(_("Comprimir"), _("Ya existe {n}. ¿Qué quiere hacer?").format(n=os.path.basename(ruta)),
				botones, predeterminada=0, escape=len(botones) - 1, operacion=self)
		if eleccion is None or not 0 <= eleccion < len(SI_EXISTE):
			raise base.Cancelado()
		return SI_EXISTE[eleccion]

	def _omitir(self, entradas: list[base.Entrada], fuentes: list[servicio_comprimir.Fuente]) -> None:
		archivos = [f for f in fuentes if not f.es_carpeta]
		self.sumar(archivos_hechos=len(archivos), omitidos=len(archivos) or 1, bytes_hechos=sum(f.tamano for f in archivos))
		self._omitidas.extend(entradas)

	@staticmethod
	def _nombre_libre(ruta: str) -> str:
		"""«copia (2).zip», «copia (3).tar.gz»...: el número va antes de la extensión completa del comprimido."""
		carpeta, nombre = os.path.split(ruta)
		raiz = servicio_comprimir.quitar_extension_comprimido(nombre)
		extension = nombre[len(raiz):]
		n = 2
		while True:
			candidato = os.path.join(carpeta, f"{raiz} ({n}){extension}")
			if not os.path.exists(rutas.con_prefijo_largo(candidato)):
				return candidato
			n += 1

	def _crear(self, ctx: ContextoEjecucion, ruta: str, fuentes: list[servicio_comprimir.Fuente], anadir: bool | None = None) -> None:
		if anadir is None:
			anadir = self.opciones.anadir
		existe = os.path.exists(rutas.con_prefijo_largo(ruta))
		if servicio_comprimir.es_flujo(self.opciones.formato):
			# Un .gz no admite «añadir»: se sustituye.
			anadir = False
		if existe and anadir and self.opciones.formato == "zip" and self.opciones.variante != "aes":
			self._anadir_zip(ctx, ruta, fuentes)
			return
		temporal = os.path.join(os.path.dirname(ruta), nombres.temporal())
		try:
			escritor = servicio_comprimir.crear_escritor(self.opciones.formato, temporal, self.opciones.nivel,
				self.opciones.contrasena or None, variante=self.opciones.variante, cifrar_nombres=self.opciones.cifrar_nombres)
		except OSError as error:
			raise errores.convertir(error, ruta) from error
		try:
			if existe and anadir:
				self._copiar_existentes(ctx, escritor, ruta, {f.nombre for f in fuentes})
			for fuente in fuentes:
				self._agregar(ctx, escritor, fuente)
			if escritor.diferido:
				# 7za comprime ahora todo de una vez: el progreso de bytes llega aquí.
				self.progresar(actual=os.path.basename(ruta))
				escritor.cerrar(_Pausable(ctx), lambda n: self.sumar(bytes_hechos=n))
			else:
				escritor.cerrar()
			_colocar(temporal, ruta)
		except BaseException as error:
			escritor.descartar()
			if isinstance(error, OSError):
				raise errores.convertir(error, ruta) from error
			raise

	def _agregar(self, ctx: ContextoEjecucion, escritor: servicio_comprimir.Escritor, fuente: servicio_comprimir.Fuente) -> None:
		ctx.comprobar()
		self.progresar(actual=fuente.nombre, bytes_actual=0, total_actual=fuente.tamano)
		hechos = [0]

		def avanzar(n: int) -> None:
			hechos[0] += n
			self.sumar(bytes_hechos=n)
			self.progresar(bytes_actual=hechos[0])

		try:
			escritor.agregar(fuente, _Pausable(ctx), None if escritor.diferido else avanzar)
		except base.Cancelado:
			raise
		except base.ErrorArchivos as error:
			self.anotar_error(fuente.ruta, error.mensaje)
			self.sumar(omitidos=1)
		except OSError as error:
			self.anotar_error(fuente.ruta, errores.mensaje_para_usuario(error))
			self.sumar(omitidos=1)
		except Exception as error:  # noqa: BLE001 - py7zr y tarfile lanzan sus propios tipos
			log.warning("No se pudo añadir %s al comprimido", fuente.ruta, exc_info=True)
			self.anotar_error(fuente.ruta, str(error))
			self.sumar(omitidos=1)
		if not fuente.es_carpeta:
			self.sumar(archivos_hechos=1)

	def _copiar_existentes(self, ctx: ContextoEjecucion, escritor, ruta: str, nuevos: set[str]) -> None:
		"""Pasa al comprimido nuevo lo que ya tenía el existente (salvo lo que se sustituye)."""
		existente = resolver.abrir_comprimido(resolver.proveedor_local(), ruta)
		if self.opciones.contrasena:
			existente.fijar_contrasena(self.opciones.contrasena)
		try:
			anteriores = servicio_comprimir.reunir(existente, existente.listar("", _Pausable(ctx)), _Pausable(ctx),
				al_error=self.anotar_error)
			for fuente in anteriores:
				if fuente.nombre in nuevos:
					continue
				self.progresar(actual=fuente.nombre)
				escritor.agregar(fuente, _Pausable(ctx))
		finally:
			existente.cerrar()

	def _anadir_zip(self, ctx: ContextoEjecucion, ruta: str, fuentes: list[servicio_comprimir.Fuente]) -> None:
		from app.services.vfs.zip import BLOQUE, ProveedorZip

		destino = ProveedorZip(resolver.proveedor_local(), ruta)
		destino.nivel = {"sin": 0, "rapido": 1, "normal": 6, "maximo": 9}[self.opciones.nivel]
		if self.opciones.variante == "zstd":
			destino.metodo = "zstd"
		try:
			with destino.transaccion():
				for fuente in fuentes:
					ctx.comprobar()
					self.progresar(actual=fuente.nombre)
					try:
						if fuente.es_carpeta:
							if not destino.existe(fuente.nombre):
								destino.crear_carpeta(fuente.nombre)
							continue
						if destino.existe(fuente.nombre) and destino.info(fuente.nombre).es_carpeta:
							raise base.YaExiste(_("Ya hay una carpeta llamada «{n}» en el comprimido.").format(n=fuente.nombre))
						with fuente.proveedor.abrir_lectura(fuente.ruta) as entrada, destino.abrir_escritura(fuente.nombre) as salida:
							while datos := entrada.read(BLOQUE):
								ctx.comprobar()
								salida.write(datos)
								self.sumar(bytes_hechos=len(datos))
						destino.fijar_tiempos(fuente.nombre, fuente.modificado)
						self.sumar(archivos_hechos=1)
					except base.Cancelado:
						raise
					except base.ErrorArchivos as error:
						self.anotar_error(fuente.ruta, error.mensaje)
						self.sumar(omitidos=1)
					except OSError as error:
						self.anotar_error(fuente.ruta, errores.mensaje_para_usuario(error))
						self.sumar(omitidos=1)
		finally:
			destino.cerrar()

	def _borrar_originales(self, ctx: ContextoEjecucion) -> None:
		"""Mover al comprimido: solo se borra si no hubo errores y la prueba del comprimido sale bien."""
		if self.errores:
			self.anotar_error("", _("No se borran los originales porque hubo errores al comprimir."))
			return
		prueba = OperacionProbar(resolver.proveedor_local(), list(self.creados), self.opciones.contrasena)
		self.ejecutar_sub(prueba, ctx)
		if prueba.errores:
			self.anotar_error("", _("No se borran los originales porque la prueba del comprimido falló."))
			return
		# Lo que no entró en ningún comprimido (se omitió porque ya existía) se conserva.
		omitidas = {id(e) for e in self._omitidas}
		borrar = [e for e in self.entradas if id(e) not in omitidas]
		if not borrar:
			return
		self.ejecutar_sub(OperacionEliminar(self.origen, borrar, papelera=False), ctx)
		self.originales_borrados = True


# ── Extraer ──────────────────────────────────────────────────────────────────


class OperacionExtraer(Operacion):
	"""Extrae cada comprimido de ``archivos`` (entradas de ``contenedor``) en ``carpeta_destino``.

	:param por_carpeta: cada comprimido en su propia carpeta (su nombre sin extensión).
	:param contrasena: la que se escribió en el diálogo (si no vale, se pregunta).
	"""

	tipo = "extraer"

	def __init__(self, contenedor: base.Proveedor, archivos: list[base.Entrada], destino: base.Proveedor, carpeta_destino: str,
			opciones: OpcionesCopia | None = None, por_carpeta: bool = False, contrasena: str = "") -> None:
		super().__init__()
		self.contenedor = contenedor
		self.archivos = [e for e in archivos if not e.es_superior and not e.es_carpeta]
		self.destino = destino
		self.carpeta_destino = carpeta_destino
		self.opciones = opciones or OpcionesCopia()
		self.por_carpeta = por_carpeta
		self.contrasena = contrasena
		self.fallidos: list[base.Entrada] = []

	def descripcion(self) -> str:
		return _("Extraer {que} en {d}").format(que=_que(self.archivos), d=self.destino.mostrar(self.carpeta_destino))

	@property
	def carriles(self) -> frozenset[str]:
		claves = claves_carril(self.contenedor, [e.ruta for e in self.archivos])
		claves |= claves_carril(self.destino, [self.carpeta_destino])
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [(self.destino.esquema, self.carpeta_destino)]

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.EJECUTANDO)
		self.progresar(archivos_total=0)
		for archivo in self.archivos:
			ctx.comprobar()
			self.progresar(actual=archivo.nombre)
			proveedor = resolver.abrir_comprimido(self.contenedor, archivo.ruta)
			if self.contrasena:
				proveedor.fijar_contrasena(self.contrasena)
			try:
				hijos = proveedor.listar("", _Pausable(ctx))
				omitidas = getattr(proveedor, "omitidas", [])
				if omitidas:
					self.anotar_error(archivo.ruta, formato.plural(len(omitidas),
						_("No se extrae {n} entrada con ruta peligrosa o de un tipo no admitido."),
						_("No se extraen {n} entradas con rutas peligrosas o de un tipo no admitido.")))
				carpeta = self.carpeta_destino
				if self.por_carpeta:
					carpeta = self.destino.unir(carpeta, servicio_comprimir.quitar_extension_comprimido(archivo.nombre))
					if not self.destino.existe(carpeta):
						self.destino.crear_carpeta(carpeta)
				if hijos:
					self.ejecutar_sub(OperacionCopiar(proveedor, hijos, self.destino, carpeta, replace(self.opciones)), ctx)
			except base.Cancelado:
				raise
			except base.ErrorArchivos as error:
				self.anotar_error(archivo.ruta, error.mensaje)
				self.fallidos.append(archivo)
			finally:
				proveedor.cerrar()


# ── Probar ───────────────────────────────────────────────────────────────────


class OperacionProbar(Operacion):
	"""Lee todos los comprimidos de ``rutas_`` (en ``contenedor``) verificando sus CRC."""

	tipo = "probar"

	def __init__(self, contenedor: base.Proveedor, rutas_: list[str], contrasena: str = "") -> None:
		super().__init__()
		self.contenedor = contenedor
		self.rutas = list(rutas_)
		self.contrasena = contrasena
		#: (ruta, ResultadoPrueba o None si no se pudo abrir).
		self.resultados: list[tuple[str, object]] = []

	def descripcion(self) -> str:
		if len(self.rutas) == 1:
			return _("Probar {n}").format(n=self.contenedor.nombre(self.rutas[0]))
		return _("Probar {n}").format(n=formato.plural(len(self.rutas), _("{n} comprimido"), _("{n} comprimidos")))

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset(claves_carril(self.contenedor, self.rutas))

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.EJECUTANDO)
		for ruta in self.rutas:
			ctx.comprobar()
			proveedor = resolver.abrir_comprimido(self.contenedor, ruta)
			if self.contrasena:
				proveedor.fijar_contrasena(self.contrasena)
			nombre = self.contenedor.nombre(ruta)
			try:
				indice = proveedor.indice(_Pausable(ctx))
				archivos = list(indice.archivos())
				self.sumar(archivos_total=len(archivos), bytes_total=sum(indice.entradas[r].tamano for r in archivos))

				def avanzar(miembro: str, n: int, nombre=nombre) -> None:
					self.progresar(actual=f"{nombre}: {miembro}")
					self.sumar(bytes_hechos=n)

				resultado = proveedor.probar(_Pausable(ctx), avanzar)
				self.resultados.append((ruta, resultado))
				self.sumar(archivos_hechos=resultado.archivos)
				for miembro, mensaje in resultado.errores:
					self.anotar_error(f"{nombre}: {miembro}", mensaje)
			except base.Cancelado:
				raise
			except base.ErrorArchivos as error:
				self.resultados.append((ruta, None))
				self.anotar_error(nombre, error.mensaje)
			finally:
				proveedor.cerrar()

	def resumen(self) -> str:
		if self.estado in (Estado.CANCELADA, Estado.FALLIDA):
			return super().resumen()
		p = self.instantanea()
		if self.errores:
			primero = self.errores[0]
			detalle = f"{primero.ruta}: {primero.mensaje}" if primero.ruta else primero.mensaje
			return _("{d}: {e}. {detalle}").format(d=self.descripcion(),
				e=formato.plural(len(self.errores), _("{n} error"), _("{n} errores")), detalle=detalle)
		return _("{d}: correcto, {a}, {t}").format(d=self.descripcion(),
			a=formato.plural(p.archivos_hechos, _("{n} archivo"), _("{n} archivos")), t=formato.tamano_legible(p.bytes_hechos))


# ── Sumas de comprobación ────────────────────────────────────────────────────


def _relativo_a(fuente: servicio_comprimir.Fuente, carpeta_destino: str) -> str:
	"""Nombre del archivo tal como se escribe en el archivo de sumas (relativo a donde se guarda)."""
	local = fuente.proveedor.ruta_local(fuente.ruta) if fuente.proveedor.esquema == "local" else None
	if local and carpeta_destino:
		try:
			return os.path.relpath(local, carpeta_destino)
		except ValueError:
			# Otra unidad: no hay ruta relativa posible, se escribe la completa.
			log.debug("%s y %s están en unidades distintas", local, carpeta_destino)
			return local
	return fuente.nombre.replace("/", "\\")


def _escribir_texto(ruta: str, texto: str) -> None:
	temporal = os.path.join(os.path.dirname(ruta), nombres.temporal())
	try:
		with open(rutas.con_prefijo_largo(temporal), "w", encoding="utf-8", newline="") as salida:
			salida.write(texto)
		_colocar(temporal, ruta)
	except BaseException as error:
		_borrar(temporal)
		if isinstance(error, OSError):
			raise errores.convertir(error, ruta) from error
		raise


class OperacionCrearSumas(Operacion):
	"""Calcula la suma de cada archivo de ``entradas`` (con subcarpetas) y la guarda.

	:param carpeta_destino: carpeta local donde se guardan los archivos de sumas.
	:param uno_por_archivo: un archivo de sumas por archivo («a.txt.sha256»); si no, uno para todos.
	:param nombre_archivo: con uno para todos, su nombre («copia.sha256»).
	:param guardar: False para solo calcular (copiar la suma al portapapeles).
	"""

	tipo = "sumas"

	def __init__(self, origen: base.Proveedor, entradas: list[base.Entrada], algoritmo: str, carpeta_destino: str,
			uno_por_archivo: bool = False, nombre_archivo: str = "", guardar: bool = True) -> None:
		super().__init__()
		if algoritmo not in sumas.POR_ID:
			raise ValueError(f"Algoritmo desconocido: {algoritmo}")
		self.origen = origen
		self.entradas = [e for e in entradas if not e.es_superior]
		self.algoritmo = algoritmo
		self.carpeta_destino = carpeta_destino
		self.uno_por_archivo = uno_por_archivo
		self.nombre_archivo = nombre_archivo
		self.guardar = guardar
		#: (nombre en el archivo de sumas, suma) de cada archivo calculado.
		self.sumas: list[tuple[str, str]] = []
		self.archivos_creados: list[str] = []

	def descripcion(self) -> str:
		return _("Calcular {a} de {que}").format(a=sumas.POR_ID[self.algoritmo].nombre, que=_que(self.entradas))

	@property
	def carriles(self) -> frozenset[str]:
		claves = claves_carril(self.origen, [e.ruta for e in self.entradas])
		if self.guardar:
			claves |= claves_carril(resolver.proveedor_local(), [self.carpeta_destino])
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [("local", self.carpeta_destino)] if self.guardar else []

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.ANALIZANDO)
		cancelacion = _Pausable(ctx)
		fuentes = [f for f in servicio_comprimir.reunir(self.origen, self.entradas, cancelacion, al_error=self.anotar_error)
			if not f.es_carpeta]
		self.progresar(archivos_total=len(fuentes), bytes_total=sum(f.tamano for f in fuentes))
		self.cambiar_estado(Estado.EJECUTANDO)
		calculadas: list[tuple[servicio_comprimir.Fuente, str]] = []
		for fuente in fuentes:
			ctx.comprobar()
			self.progresar(actual=fuente.nombre, bytes_actual=0, total_actual=fuente.tamano)
			try:
				with fuente.proveedor.abrir_lectura(fuente.ruta) as flujo:
					suma = sumas.calcular(flujo, self.algoritmo, cancelacion, lambda n: self.sumar(bytes_hechos=n))
			except base.Cancelado:
				raise
			except base.ErrorArchivos as error:
				self.anotar_error(fuente.ruta, error.mensaje)
				self.sumar(omitidos=1)
				continue
			except OSError as error:
				self.anotar_error(fuente.ruta, errores.mensaje_para_usuario(error))
				self.sumar(omitidos=1)
				continue
			calculadas.append((fuente, suma))
			self.sumar(archivos_hechos=1)
		ext = sumas.POR_ID[self.algoritmo].extension
		if self.uno_por_archivo:
			for fuente, suma in calculadas:
				self.sumas.append((fuente.nombre.rpartition("/")[2], suma))
		else:
			self.sumas = [(_relativo_a(f, self.carpeta_destino), s) for f, s in calculadas]
		if not self.guardar or not calculadas:
			return
		if self.uno_por_archivo:
			usados: set[str] = set()
			for fuente, suma in calculadas:
				nombre = fuente.nombre.rpartition("/")[2]
				archivo = nombre + ext
				if archivo.casefold() in usados:
					archivo = nombres.nombre_libre(archivo, lambda n: n.casefold() in usados)
				usados.add(archivo.casefold())
				ruta = os.path.join(self.carpeta_destino, archivo)
				self._guardar(ruta, [(_relativo_a(fuente, self.carpeta_destino), suma)])
		else:
			nombre = self.nombre_archivo or (_que(self.entradas) + ext)
			if not nombre.lower().endswith(ext):
				nombre += ext
			self._guardar(os.path.join(self.carpeta_destino, nombre), self.sumas)

	def _guardar(self, ruta: str, lineas: list[tuple[str, str]]) -> None:
		try:
			_escribir_texto(ruta, sumas.componer(self.algoritmo, lineas, _("Creado con zCommander")))
			self.archivos_creados.append(ruta)
		except base.ErrorArchivos as error:
			self.anotar_error(ruta, error.mensaje)


class OperacionVerificarSumas(Operacion):
	"""Comprueba los archivos que lista ``ruta_lista`` (un archivo de sumas de ``proveedor``)."""

	tipo = "verificar_sumas"

	def __init__(self, proveedor: base.Proveedor, ruta_lista: str) -> None:
		super().__init__()
		self.proveedor = proveedor
		self.ruta_lista = ruta_lista
		self.verificaciones: list[sumas.Verificacion] = []
		self.algoritmo: str | None = None

	def descripcion(self) -> str:
		return _("Verificar {n}").format(n=self.proveedor.nombre(self.ruta_lista))

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset(claves_carril(self.proveedor, [self.ruta_lista]))

	def _ruta_de(self, nombre: str) -> str:
		ruta = self.proveedor.padre(self.ruta_lista) or ""
		if self.proveedor.esquema == "local" and os.path.isabs(nombre):
			return nombre
		for parte in re.split(r"[\\/]", nombre):
			if not parte or parte == ".":
				continue
			if parte == "..":
				ruta = self.proveedor.padre(ruta) or ruta
			else:
				ruta = self.proveedor.unir(ruta, parte)
		return ruta

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.ANALIZANDO)
		cancelacion = _Pausable(ctx)
		with self.proveedor.abrir_lectura(self.ruta_lista) as flujo:
			texto = sumas.decodificar(flujo.read(16 * 1024 * 1024))
		algoritmo = sumas.algoritmo_de_archivo(self.proveedor.nombre(self.ruta_lista))
		lista = sumas.leer(texto, algoritmo.id if algoritmo else None)
		self.algoritmo = algoritmo.id if algoritmo else sumas.deducir_algoritmo(lista)
		if self.algoritmo is None:
			raise base.ErrorArchivos(_("No se reconoce el formato de {n}.").format(n=self.proveedor.nombre(self.ruta_lista)),
				self.ruta_lista)
		destinos = []
		total = 0
		for nombre, suma in lista:
			ruta = self._ruta_de(nombre)
			try:
				entrada = self.proveedor.info(ruta)
			except base.ErrorArchivos:
				entrada = None
			destinos.append((nombre, suma, ruta, entrada))
			if entrada is not None and not entrada.es_carpeta:
				total += max(0, entrada.tamano)
		self.progresar(archivos_total=len(destinos), bytes_total=total)
		self.cambiar_estado(Estado.EJECUTANDO)
		for nombre, esperada, ruta, entrada in destinos:
			ctx.comprobar()
			self.progresar(actual=nombre)
			if entrada is None or entrada.es_carpeta:
				self._anotar(sumas.Verificacion(nombre, sumas.Resultado.NO_ENCONTRADO))
				continue
			try:
				with self.proveedor.abrir_lectura(ruta) as flujo:
					obtenida = sumas.calcular(flujo, self.algoritmo, cancelacion, lambda n: self.sumar(bytes_hechos=n))
			except base.Cancelado:
				raise
			except (base.ErrorArchivos, OSError) as error:
				mensaje = error.mensaje if isinstance(error, base.ErrorArchivos) else errores.mensaje_para_usuario(error)
				self._anotar(sumas.Verificacion(nombre, sumas.Resultado.ERROR_LECTURA, mensaje))
				continue
			if sumas.iguales(esperada, obtenida):
				self._anotar(sumas.Verificacion(nombre, sumas.Resultado.CORRECTO))
			else:
				self._anotar(sumas.Verificacion(nombre, sumas.Resultado.DISTINTO, obtenida))

	def _anotar(self, verificacion: sumas.Verificacion) -> None:
		self.verificaciones.append(verificacion)
		self.sumar(archivos_hechos=1)
		if verificacion.resultado != sumas.Resultado.CORRECTO:
			self.anotar_error(verificacion.nombre, verificacion.resultado.texto)

	def resumen(self) -> str:
		if self.estado in (Estado.CANCELADA, Estado.FALLIDA):
			return super().resumen()
		return f"{self.descripcion()}: {sumas.resumen_verificacion(self.verificaciones)}"


# ── Dividir y unir ───────────────────────────────────────────────────────────


class OperacionDividir(Operacion):
	"""Divide el archivo ``entrada`` de ``proveedor`` en partes de ``tamano_parte`` bytes en ``carpeta_destino`` (local)."""

	tipo = "dividir"

	def __init__(self, proveedor: base.Proveedor, entrada: base.Entrada, carpeta_destino: str, tamano_parte: int) -> None:
		super().__init__()
		self.proveedor = proveedor
		self.entrada = entrada
		self.carpeta_destino = carpeta_destino
		self.tamano_parte = tamano_parte
		self.creados: list[str] = []

	def descripcion(self) -> str:
		return _("Dividir {n} en partes de {t}").format(n=self.entrada.nombre, t=formato.tamano_legible(self.tamano_parte))

	@property
	def carriles(self) -> frozenset[str]:
		claves = claves_carril(self.proveedor, [self.entrada.ruta])
		claves |= claves_carril(resolver.proveedor_local(), [self.carpeta_destino])
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [("local", self.carpeta_destino)]

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.EJECUTANDO)
		self.progresar(archivos_total=1, bytes_total=max(0, self.entrada.tamano), actual=self.entrada.nombre)
		with self.proveedor.abrir_lectura(self.entrada.ruta) as flujo:
			self.creados = servicio_dividir.dividir(flujo, self.entrada.nombre, self.entrada.tamano, self.carpeta_destino,
				self.tamano_parte, _Pausable(ctx), lambda n: self.sumar(bytes_hechos=n))
		self.sumar(archivos_hechos=1)

	def resumen(self) -> str:
		if self.estado in (Estado.CANCELADA, Estado.FALLIDA) or not self.creados:
			return super().resumen()
		partes = len(self.creados) - 1
		return _("{d}: {p} y el archivo .crc").format(d=self.descripcion(),
			p=formato.plural(partes, _("{n} parte"), _("{n} partes")))


class OperacionUnir(Operacion):
	"""Une ``nombre.001``, ``.002``... (locales) en ``destino`` y comprueba el ``.crc`` si existe."""

	tipo = "unir"

	def __init__(self, primera: str, destino: str) -> None:
		super().__init__()
		self.primera = primera
		self.destino = destino
		self.resultado: servicio_dividir.ResultadoUnion | None = None

	def descripcion(self) -> str:
		return _("Unir {n} en {d}").format(n=os.path.basename(self.primera), d=os.path.basename(self.destino))

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset(claves_carril(resolver.proveedor_local(), [self.primera, self.destino]))

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [("local", os.path.dirname(self.destino))]

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.ANALIZANDO)
		partes = servicio_dividir.buscar_partes(self.primera)
		if not partes:
			raise base.NoEncontrado(_("No se encuentra {n}.").format(n=os.path.basename(self.primera)), self.primera)
		total = 0
		for parte in partes:
			try:
				total += os.path.getsize(rutas.con_prefijo_largo(parte))
			except OSError as error:
				raise errores.convertir(error, parte) from error
		self.progresar(archivos_total=len(partes), bytes_total=total)
		self.cambiar_estado(Estado.EJECUTANDO)
		self.resultado = servicio_dividir.unir(self.primera, self.destino, _Pausable(ctx), lambda n: self.sumar(bytes_hechos=n),
			partes=partes)
		self.progresar(archivos_hechos=len(partes))
		if self.resultado.comprobado is False:
			self.anotar_error(self.destino, _("El archivo unido no coincide con el .crc: alguna parte está dañada o falta."))

	def resumen(self) -> str:
		if self.resultado is None:
			return super().resumen()
		texto = _("{d}: {p}, {t}").format(d=self.descripcion(),
			p=formato.plural(self.resultado.partes, _("{n} parte"), _("{n} partes")), t=formato.tamano_legible(self.resultado.tamano))
		if self.resultado.comprobado is True:
			return texto + _(", comprobado con el .crc")
		if self.resultado.comprobado is False:
			return texto + _(". ERROR: no coincide con el .crc")
		return texto + _(", sin .crc para comprobarlo")

