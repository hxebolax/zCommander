# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Buscar archivos (Alt+F7): criterios, recorrido, búsqueda por contenido y búsquedas guardadas.

Sin wx: el diálogo (``app/ui/dialogos/b_buscar.py``) recoge los criterios,
lanza ``buscar`` en un hilo y recibe cada resultado por ``al_resultado``.
Se apoya en el recorrido único (``recorrido.py``), así que hereda sus reglas:
no entra en enlaces ni uniones, comprueba la cancelación en cada elemento y
un error en una subcarpeta no para la búsqueda.

Decisiones:

- El texto contenido se busca por bloques (1 MB) con un decodificador
  incremental y un solape entre bloques, para no cargar archivos enteros en
  memoria y encontrar también lo que queda partido entre dos bloques. Con
  expresión regular, una coincidencia más larga que el solape (4096
  caracteres) podría no encontrarse: es un límite aceptado.
- Los archivos que solo están en la nube no se abren (abrirlos los
  descargaría) salvo que se pida con ``nube``.
- Sin ``ocultos``, los ocultos y de sistema no se muestran, y tampoco nada
  de lo que hay dentro de una carpeta oculta.
- Dentro de comprimidos solo se busca en ZIP y TAR (los registra el bloque C
  en ``resolver``), y nunca en un comprimido dentro de otro.
"""

from __future__ import annotations

import builtins
import codecs
import locale
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.core import almacen_json
from app.services import codificacion
from app.services.recorrido import recorrer
from app.services.seleccion import Patron
from app.services.vfs import base

log = logging.getLogger(__name__)

ARCHIVO_GUARDADAS = "busquedas.json"

#: Qué se busca.
ARCHIVOS, CARPETAS, AMBOS = "archivos", "carpetas", "ambos"
#: Codificaciones que ofrece el diálogo.
CODIFICACIONES = ("automatica", "utf-8", "utf-16", "ansi")
#: Extensiones de comprimidos en las que se busca (la sección 8.12 pide ZIP y TAR).
EXTENSIONES_COMPRIMIDOS = frozenset({"zip", "tar", "tgz", "tar.gz", "tbz", "tbz2", "tar.bz2", "txz", "tar.xz"})

_BLOQUE = 1024 * 1024
_SOLAPE_REGEX = 4096


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorCriterios(ValueError):
	"""Criterios que no se pueden usar (expresión regular mal escrita...), con mensaje en español."""


@dataclass
class Criterios:
	"""Todo lo que se puede pedir en el diálogo de búsqueda.

	:param nombres: patrones de la sección 5.3 (``*.txt;*.md | *.bak``) o, con
		``nombres_regex``, una expresión regular que se busca en el nombre.
	:param profundidad: niveles de subcarpetas (``None`` = sin límite); solo
		cuenta con ``subcarpetas``.
	:param texto: texto contenido (vacío = no se mira el contenido).
	:param codificacion: «automatica», «utf-8», «utf-16» o «ansi».
	:param no_contiene: invierte la búsqueda de texto (los que NO lo contienen).
	:param tamano_min, tamano_max: en bytes; solo se aplican a archivos.
	:param desde, hasta: marcas de tiempo de la fecha de modificación (incluidas).
	:param que: ``ARCHIVOS``, ``CARPETAS`` o ``AMBOS``.
	:param comprimidos: buscar también dentro de los ZIP y TAR.
	:param nube: leer el contenido de archivos que solo están en la nube.
	:param max_resultados: tope (preferencia ``busqueda.max_resultados``).
	"""

	nombres: str = "*"
	nombres_regex: bool = False
	subcarpetas: bool = True
	profundidad: int | None = None
	texto: str = ""
	mayusculas: bool = False
	palabra_completa: bool = False
	texto_regex: bool = False
	codificacion: str = "automatica"
	no_contiene: bool = False
	tamano_min: int | None = None
	tamano_max: int | None = None
	desde: float | None = None
	hasta: float | None = None
	ocultos: bool = False
	que: str = ARCHIVOS
	comprimidos: bool = False
	nube: bool = False
	max_resultados: int = 100000
	#: 2.0 (3.5): motor de búsqueda de un complemento («<id>:<proveedor>»); vacío = el de zCommander.
	motor: str = ""
	#: 2.0 (3.5): buscar también dentro de documentos con los extractores de texto de los complementos.
	dentro_de_documentos: bool = False


@dataclass(frozen=True)
class Resultado:
	"""Un elemento encontrado.

	:param proveedor: donde está (el del disco, el de un comprimido o el de un servidor).
	:param carpeta: ruta de su carpeta dentro de ``proveedor`` (para «Ir al archivo»).
	:param mostrar_carpeta: texto de la columna Carpeta.
	:param ruta_local: ruta absoluta en el disco, o ``None`` (comprimido o servidor):
		solo los locales se pueden enviar al panel (sección 20.2).
	"""

	entrada: base.Entrada
	proveedor: base.Proveedor
	carpeta: str
	mostrar_carpeta: str
	ruta_local: str | None

	@property
	def es_local(self) -> bool:
		return self.ruta_local is not None

	def mostrar_ruta(self) -> str:
		"""Ruta completa para la persona (se guarda así en el archivo de resultados)."""
		return self.proveedor.mostrar(self.entrada.ruta)


@dataclass
class Estadisticas:
	"""Resumen de una búsqueda terminada (o cancelada a medias)."""

	encontrados: int = 0
	revisados: int = 0
	errores: list[tuple[str, str]] = field(default_factory=list)
	limitado: bool = False
	inicio: float = field(default_factory=time.monotonic)
	fin: float = 0.0

	@property
	def duracion(self) -> float:
		return max(0.0, (self.fin or time.monotonic()) - self.inicio)


# ── Criterios ────────────────────────────────────────────────────────────────

def compilar_nombres(criterios: Criterios) -> Callable[[str], bool]:
	"""Función que dice si un nombre coincide.

	:raises ErrorCriterios: si la expresión regular no es válida.
	"""
	if criterios.nombres_regex:
		try:
			expresion = re.compile(criterios.nombres or ".*", re.IGNORECASE)
		except re.error as error:
			raise ErrorCriterios(_("La expresión regular de los nombres no es válida: {e}").format(e=error)) from error
		return lambda nombre: expresion.search(nombre) is not None
	patron = Patron.analizar(criterios.nombres or "*")
	return patron.coincide


def compilar_texto(criterios: Criterios) -> re.Pattern[str] | None:
	"""Expresión del texto contenido, o ``None`` si no se busca texto.

	:raises ErrorCriterios: si la expresión regular no es válida.
	"""
	if not criterios.texto:
		return None
	nucleo = criterios.texto if criterios.texto_regex else re.escape(criterios.texto)
	if criterios.palabra_completa:
		# \b no sirve si el texto empieza o acaba con un signo: se exige que no haya letra al lado.
		nucleo = rf"(?<!\w)(?:{nucleo})(?!\w)"
	banderas = 0 if criterios.mayusculas else re.IGNORECASE
	try:
		return re.compile(nucleo, banderas | re.MULTILINE)
	except re.error as error:
		raise ErrorCriterios(_("La expresión regular del texto no es válida: {e}").format(e=error)) from error


def _codec_ansi() -> str:
	"""Página de códigos ANSI de Windows (cp1252 en España); cp1252 si no se sabe."""
	try:
		nombre = locale.getencoding()
		codecs.lookup(nombre)
		return nombre
	except (LookupError, AttributeError, ValueError):
		return "cp1252"


def _elegir_codec(eleccion: str, inicio: bytes, completo: bool = False) -> tuple[str, int]:
	"""(códec de Python, bytes de BOM que saltar) para la codificación pedida.

	:param completo: ``inicio`` es el archivo entero; entonces un byte no válido
		al final no se toma por un carácter cortado (archivos ANSI muy cortos).
	"""
	bom, salto = codificacion.bom_de(inicio)
	if eleccion == "utf-8":
		return "utf-8", salto if bom == "utf-8" else 0
	if eleccion == "utf-16":
		if bom in ("utf-16-le", "utf-16-be"):
			return bom, salto
		# Sin BOM: la misma detección por ceros que usan el visor y la vista rápida.
		return codificacion._parece_utf16(inicio) or "utf-16-le", 0
	if eleccion == "ansi":
		return _codec_ansi(), 0
	detectada = codificacion.detectar(inicio)
	if detectada == "utf-8" and completo and not bom:
		try:
			inicio.decode("utf-8")
		except UnicodeDecodeError:
			detectada = _codec_ansi()
	return detectada, salto if bom == detectada else 0


def contiene(lector, expresion: re.Pattern[str], eleccion: str = "automatica", cancelacion=None,
		bloque: int = _BLOQUE) -> bool:
	"""``True`` si el flujo binario ``lector`` contiene ``expresion``.

	Lee por bloques con un decodificador incremental (un carácter partido entre
	dos bloques se decodifica bien) y conserva un solape de texto entre bloques.
	"""
	primero = lector.read(bloque)
	if not primero:
		return False
	codec, salto = _elegir_codec(eleccion, primero[:65536], completo=len(primero) < bloque and len(primero) <= 65536)
	decodificador = codecs.getincrementaldecoder(codec)(errors="replace")
	solape = max(_SOLAPE_REGEX, len(expresion.pattern) * 2)
	cola = ""
	datos = primero[salto:]
	while datos:
		base.comprobar(cancelacion)
		texto = cola + decodificador.decode(datos)
		if expresion.search(texto):
			return True
		cola = texto[-solape:]
		datos = lector.read(bloque)
	# Bytes sueltos al final (un carácter incompleto) salen como «�» al cerrar el decodificador.
	resto = decodificador.decode(b"", final=True)
	return bool(resto) and expresion.search(cola + resto) is not None


# ── Búsqueda ─────────────────────────────────────────────────────────────────

class _Filtro:
	"""Criterios ya preparados (se compilan una vez por búsqueda)."""

	def __init__(self, criterios: Criterios) -> None:
		self.criterios = criterios
		self.nombre = compilar_nombres(criterios)
		self.texto = compilar_texto(criterios)

	def tipo_vale(self, entrada: base.Entrada) -> bool:
		que = self.criterios.que
		if entrada.es_carpeta:
			return que in (CARPETAS, AMBOS)
		return que in (ARCHIVOS, AMBOS)

	def metadatos_valen(self, entrada: base.Entrada) -> bool:
		"""Nombre, tamaño, fecha y atributos (todo lo que no exige abrir el archivo)."""
		c = self.criterios
		if not self.tipo_vale(entrada) or not self.nombre(entrada.nombre):
			return False
		if not entrada.es_carpeta:
			if c.tamano_min is not None and entrada.tamano < c.tamano_min:
				return False
			if c.tamano_max is not None and entrada.tamano > c.tamano_max:
				return False
		if c.desde is not None and entrada.modificado < c.desde:
			return False
		return not (c.hasta is not None and entrada.modificado > c.hasta)


def _oculto(entrada: base.Entrada) -> bool:
	return entrada.oculto or entrada.sistema


def _es_comprimido_buscable(nombre: str) -> bool:
	from app.services.vfs import resolver

	extension = resolver.extension_comprimido(nombre)
	return extension is not None and extension in EXTENSIONES_COMPRIMIDOS


def _texto_de_documento(proveedor, entrada: base.Entrada, cancelacion) -> str | None:
	"""Texto de un PDF, DOCX o EPUB con el extractor de un complemento cuyo ``[[extractores]]`` coincide (3.5)."""
	from app.plugins import cargador, registro
	from app.plugins import estado as estado_complementos

	for registrado in registro.complementos():
		if not any(registro.coincide(entrada.nombre, e.get("patrones", [])) for e in registrado.manifiesto.tabla("extractores")):
			continue
		try:
			if not cargador.asegurar_activo(registrado.id).result(cargador.TIEMPO_CARGA_S):
				continue
		except Exception:  # noqa: BLE001 - sin el complemento se lee el archivo como texto
			log.debug("No se activó %s para extraer texto", registrado.id, exc_info=True)
			continue
		funcion = registro.funcion("extractor", registrado.id)
		if funcion is not None:
			texto = estado_complementos.llamar_protegido(registrado.id, funcion, proveedor, entrada.ruta, cancelacion)
			if texto is not None:
				return str(texto)
	return None


def _buscar_con_motor(criterios: Criterios, cancelacion, al_resultado) -> Estadisticas:
	"""Búsqueda con el motor de un complemento: entrega rutas locales o direcciones de un proveedor (3.5)."""
	from app.plugins import cargador, registro
	from app.plugins import estado as estado_complementos
	from app.services.vfs import resolver

	estadisticas = Estadisticas()
	id_complemento = criterios.motor.split(":", 1)[0]
	if not cargador.asegurar_activo(id_complemento).result(cargador.TIEMPO_CARGA_S):
		raise ErrorCriterios(_("El motor de búsqueda {m} no está disponible").format(m=criterios.motor))
	funcion = registro.funcion("busqueda", criterios.motor)
	if funcion is None:
		raise ErrorCriterios(_("El motor de búsqueda {m} no está disponible").format(m=criterios.motor))
	local = resolver.proveedor_local()

	def entregar(ruta: str) -> None:
		if "://" in ruta:
			# 2.0 (3.5): un resultado con la dirección de un proveedor («synology://casa/a.txt»,
			# «nube://drive/b.pdf») se resuelve con ese proveedor; no se puede enviar al panel.
			try:
				proveedor, interior, _nombre = resolver.abrir_ruta(ruta)
				entrada = proveedor.info(interior)
			except base.ErrorArchivos:
				log.debug("Resultado del motor %s descartado: %s", criterios.motor, ruta, exc_info=True)
				return
			estadisticas.encontrados += 1
			if al_resultado is not None:
				carpeta = proveedor.padre(interior) or ""
				al_resultado(Resultado(entrada, proveedor, carpeta, proveedor.mostrar(carpeta), None))
			return
		try:
			entrada = local.info(ruta)
		except base.ErrorArchivos:
			return
		estadisticas.encontrados += 1
		if al_resultado is not None:
			carpeta = local.padre(ruta) or ruta
			al_resultado(Resultado(entrada, local, carpeta, local.mostrar(carpeta), ruta))

	estado_complementos.llamar_protegido(id_complemento, funcion, criterios, entregar, cancelacion)
	estadisticas.fin = time.monotonic()
	return estadisticas


def buscar(
	raices: Sequence[tuple[base.Proveedor, str]],
	criterios: Criterios,
	cancelacion=None,
	al_resultado: Callable[[Resultado], None] | None = None,
	al_revisar: Callable[[str], None] | None = None,
) -> Estadisticas:
	"""Busca en cada raíz ``(proveedor, carpeta)`` y entrega los resultados según aparecen.

	:param al_resultado: recibe cada ``Resultado`` (desde el hilo que llama).
	:param al_revisar: recibe de vez en cuando la carpeta que se está revisando.
	:raises ErrorCriterios: si los criterios no valen (antes de empezar).
	:raises Cancelado: si se cancela (las estadísticas hasta ese momento se pierden;
		los resultados ya entregados, no).
	"""
	if criterios.motor:
		return _buscar_con_motor(criterios, cancelacion, al_resultado)
	filtro = _Filtro(criterios)
	estadisticas = Estadisticas()
	for proveedor, carpeta in raices:
		base.comprobar(cancelacion)
		if not _buscar_en(proveedor, carpeta, filtro, estadisticas, cancelacion, al_resultado, al_revisar, dentro=False):
			break
	estadisticas.fin = time.monotonic()
	return estadisticas


def _buscar_en(proveedor, carpeta, filtro: _Filtro, estadisticas: Estadisticas, cancelacion, al_resultado, al_revisar,
		dentro: bool) -> bool:
	"""Recorre una raíz. Devuelve ``False`` si se llegó al máximo de resultados."""
	c = filtro.criterios
	maxima = (c.profundidad if c.profundidad is not None and c.profundidad >= 0 else None) if c.subcarpetas else 0
	sep = "\\" if proveedor.esquema == "local" else "/"
	ocultas: list[str] = []
	# El disco y las listas de resultados (búsqueda, vista plana, cesta) tienen rutas locales reales.
	local = proveedor.esquema in ("local", "resultados")
	ultimo_aviso = 0.0

	def anotar_error(ruta: str, error: base.ErrorArchivos) -> None:
		estadisticas.errores.append((proveedor.mostrar(ruta), error.mensaje))

	for elemento in recorrer(proveedor, carpeta, cancelacion, profundidad_maxima=maxima, al_error=anotar_error):
		entrada = elemento.entrada
		estadisticas.revisados += 1
		if ocultas and any(elemento.relativo.startswith(prefijo) for prefijo in ocultas):
			continue
		if not c.ocultos and _oculto(entrada):
			if entrada.es_carpeta:
				ocultas.append(elemento.relativo + sep)
			continue
		if al_revisar is not None and entrada.es_carpeta and time.monotonic() - ultimo_aviso > 0.25:
			ultimo_aviso = time.monotonic()
			al_revisar(proveedor.mostrar(entrada.ruta))
		if filtro.metadatos_valen(entrada) and _contenido_vale(proveedor, entrada, filtro, estadisticas, cancelacion):
			padre = proveedor.padre(entrada.ruta) or ""
			resultado = Resultado(entrada, proveedor, padre, proveedor.mostrar(padre),
				proveedor.ruta_local(entrada.ruta) if local else None)
			estadisticas.encontrados += 1
			if al_resultado is not None:
				al_resultado(resultado)
			if estadisticas.encontrados >= c.max_resultados:
				estadisticas.limitado = True
				return False
		if c.comprimidos and not dentro and not entrada.es_carpeta and _es_comprimido_buscable(entrada.nombre):
			if not _buscar_en_comprimido(proveedor, entrada, filtro, estadisticas, cancelacion, al_resultado, al_revisar):
				return False
	return True


def _buscar_en_comprimido(proveedor, entrada, filtro, estadisticas, cancelacion, al_resultado, al_revisar) -> bool:
	from app.services.vfs import resolver

	try:
		comprimido = resolver.abrir_comprimido(proveedor, entrada.ruta)
	except base.ErrorArchivos as error:
		estadisticas.errores.append((proveedor.mostrar(entrada.ruta), error.mensaje))
		return True
	antes = estadisticas.encontrados
	try:
		return _buscar_en(comprimido, "", filtro, estadisticas, cancelacion, al_resultado, al_revisar, dentro=True)
	except base.Cancelado:
		raise
	except base.ErrorArchivos as error:
		estadisticas.errores.append((proveedor.mostrar(entrada.ruta), error.mensaje))
		return True
	finally:
		# Con resultados dentro, el proveedor sigue abierto: lo usan «Ver» e «Ir al archivo»
		# y lo cierra quien descarta los resultados (el diálogo, al cerrarse).
		if estadisticas.encontrados == antes:
			comprimido.cerrar()


def _contenido_vale(proveedor, entrada: base.Entrada, filtro: _Filtro, estadisticas: Estadisticas, cancelacion) -> bool:
	if filtro.texto is None:
		return True
	if entrada.es_carpeta:
		return False
	if entrada.en_nube and not filtro.criterios.nube:
		return False
	try:
		extraido = _texto_de_documento(proveedor, entrada, cancelacion) if filtro.criterios.dentro_de_documentos else None
		if extraido is not None:
			encontrado = filtro.texto.search(extraido) is not None
		else:
			with proveedor.abrir_lectura(entrada.ruta) as lector:
				encontrado = contiene(lector, filtro.texto, filtro.criterios.codificacion, cancelacion)
	except base.Cancelado:
		raise
	except base.ErrorArchivos as error:
		estadisticas.errores.append((proveedor.mostrar(entrada.ruta), error.mensaje))
		return False
	except OSError as error:
		log.debug("No se pudo leer %s para buscar texto", entrada.ruta, exc_info=True)
		estadisticas.errores.append((proveedor.mostrar(entrada.ruta), str(error)))
		return False
	return encontrado != filtro.criterios.no_contiene


def resumen(estadisticas: Estadisticas, cancelada: bool = False) -> str:
	"""«Búsqueda terminada: 120 resultados en 4 s» (lo que se anuncia al acabar)."""
	from app.services import formato

	n = formato.plural(estadisticas.encontrados, _("{n} resultado"), _("{n} resultados"))
	if cancelada:
		texto = _("Búsqueda detenida: {n}").format(n=n)
	else:
		texto = _("Búsqueda terminada: {n} en {t}").format(n=n, t=formato.duracion(estadisticas.duracion))
	if estadisticas.limitado:
		texto += _(" (se llegó al máximo de resultados)")
	if estadisticas.errores:
		texto += ", " + formato.plural(len(estadisticas.errores), _("{n} carpeta o archivo sin leer"),
			_("{n} carpetas o archivos sin leer"))
	return texto


def texto_resultados(resultados: Sequence[Resultado]) -> str:
	"""Contenido del archivo «Guardar resultados»: una ruta completa por línea (CRLF)."""
	return "".join(r.mostrar_ruta() + "\r\n" for r in resultados)


# ── Búsquedas guardadas (data/config/busquedas.json, sección 10) ─────────────────

_POR_DEFECTO = {"version": 1, "busquedas": []}


def cargar_guardadas() -> list[dict]:
	"""``[{"nombre": ..., "campos": {...}}]`` en el orden en que se guardaron. Nunca lanza."""
	datos = almacen_json.leer(ARCHIVO_GUARDADAS, _POR_DEFECTO)
	busquedas = datos.get("busquedas") if isinstance(datos, dict) else None
	if not isinstance(busquedas, list):
		return []
	return [b for b in busquedas if isinstance(b, dict) and isinstance(b.get("nombre"), str) and isinstance(b.get("campos"), dict)]


def guardar_busqueda(nombre: str, campos: dict) -> list[dict]:
	"""Guarda (o sustituye, sin distinguir mayúsculas) la búsqueda ``nombre``.

	:raises OSError: si no se pudo escribir el archivo.
	"""
	busquedas = [b for b in cargar_guardadas() if b["nombre"].casefold() != nombre.casefold()]
	busquedas.append({"nombre": nombre, "campos": dict(campos)})
	almacen_json.escribir(ARCHIVO_GUARDADAS, {"version": 1, "busquedas": busquedas})
	return busquedas


def borrar_busqueda(nombre: str) -> list[dict]:
	"""Quita la búsqueda guardada ``nombre``.

	:raises OSError: si no se pudo escribir el archivo.
	"""
	busquedas = [b for b in cargar_guardadas() if b["nombre"].casefold() != nombre.casefold()]
	almacen_json.escribir(ARCHIVO_GUARDADAS, {"version": 1, "busquedas": busquedas})
	return busquedas


def recargar() -> None:
	"""Vuelve a leer su archivo tras restaurar una copia (2.0, 14.4): se lee en cada uso, así que solo avisa."""
	from app.services import recarga

	recarga.avisar(__name__)
