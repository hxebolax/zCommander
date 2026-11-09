# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Conversión de codificación, fines de línea, tabuladores y espacios finales (sin wx).

Todo trabaja sobre bytes en memoria: ``convertir`` devuelve los bytes nuevos y
cuántas líneas cambian, sin escribir nada. Así la vista previa del diálogo y la
operación usan exactamente el mismo cálculo.
"""

from __future__ import annotations

import builtins
import codecs
import re
import unicodedata
from dataclasses import dataclass, field

from . import deteccion

#: Archivos más grandes no se convierten (un texto de 200 MB no es un texto que se edite a mano).
TAMANO_MAXIMO = 200 * 1024 * 1024
#: Problemas que se apuntan por archivo en el informe (el resto solo se cuenta).
MAXIMO_PROBLEMAS = 50

_FIN = {"crlf": "\r\n", "lf": "\n"}
_PARTIR = re.compile(r"(\r\n|\n|\r)")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorConversion(Exception):
	"""El archivo no se puede convertir sin perder información (mensaje en español)."""


@dataclass(frozen=True)
class Opciones:
	"""Qué hacer con cada archivo.

	:param destino: ``utf8`` (sin BOM) o ``utf8_bom``.
	:param fin_linea: ``crlf``, ``lf`` o ``sin_cambio``.
	:param tabuladores: ``sin_cambio``, ``a_espacios`` o ``a_tabuladores`` (solo la sangría).
	:param ancho_tabulador: espacios por tabulador.
	:param quitar_espacios_finales: borra espacios y tabuladores al final de cada línea.
	"""

	destino: str = "utf8"
	fin_linea: str = "sin_cambio"
	tabuladores: str = "sin_cambio"
	ancho_tabulador: int = 4
	quitar_espacios_finales: bool = False


@dataclass
class Resultado:
	"""Lo que haría (o hizo) la conversión de un archivo."""

	original: deteccion.Deteccion
	datos: bytes
	lineas_cambiadas: int
	cambia_codificacion: bool

	@property
	def hay_cambios(self) -> bool:
		return self.cambia_codificacion or self.lineas_cambiadas > 0

	def resumen(self, destino: str) -> str:
		"""«Windows-1252 a UTF-8; 12 líneas cambian» o «Sin cambios»."""
		if not self.hay_cambios:
			return _("Sin cambios")
		partes = []
		if self.cambia_codificacion:
			nombre = _("UTF-8 con BOM") if destino == "utf8_bom" else _("UTF-8")
			partes.append(_("{a} a {b}").format(a=self.original.nombre_codificacion, b=nombre))
		if self.lineas_cambiadas:
			partes.append(_("1 línea cambia") if self.lineas_cambiadas == 1
				else _("{n} líneas cambian").format(n=self.lineas_cambiadas))
		return "; ".join(partes)


def _lineas(texto: str) -> list[tuple[str, str]]:
	"""(contenido, fin) de cada línea; la última puede no tener fin."""
	trozos = _PARTIR.split(texto)
	resultado = []
	for i in range(0, len(trozos), 2):
		contenido = trozos[i]
		fin = trozos[i + 1] if i + 1 < len(trozos) else ""
		if contenido or fin:
			resultado.append((contenido, fin))
	return resultado


def _espacios_a_tabuladores(contenido: str, ancho: int) -> str:
	"""Solo la sangría: cada grupo de ``ancho`` espacios iniciales pasa a un tabulador."""
	sangria = len(contenido) - len(contenido.lstrip(" \t"))
	inicio = contenido[:sangria].expandtabs(ancho)
	tabuladores, resto = divmod(len(inicio), ancho)
	return "\t" * tabuladores + " " * resto + contenido[sangria:]


def transformar(texto: str, opciones: Opciones) -> tuple[str, int]:
	"""(texto nuevo, número de líneas que cambian)."""
	nuevas: list[str] = []
	cambiadas = 0
	for contenido, fin in _lineas(texto):
		nuevo = contenido
		if opciones.tabuladores == "a_espacios" and "\t" in nuevo:
			nuevo = nuevo.expandtabs(opciones.ancho_tabulador)
		elif opciones.tabuladores == "a_tabuladores":
			nuevo = _espacios_a_tabuladores(nuevo, opciones.ancho_tabulador)
		if opciones.quitar_espacios_finales:
			nuevo = nuevo.rstrip(" \t")
		nuevo_fin = _FIN.get(opciones.fin_linea, fin) if fin else fin
		if nuevo != contenido or nuevo_fin != fin:
			cambiadas += 1
		nuevas.append(nuevo + nuevo_fin)
	return "".join(nuevas), cambiadas


def convertir(datos: bytes, opciones: Opciones) -> Resultado:
	"""Calcula la conversión de ``datos`` a UTF-8 con las ``opciones``.

	:raises ErrorConversion: si es binario o tiene bytes que no valen en su codificación
		(convertirlo perdería esos caracteres; el informe dice dónde están).
	"""
	original = deteccion.detectar(datos)
	if original.binario:
		raise ErrorConversion(_("No parece un archivo de texto"))
	try:
		texto = deteccion.decodificar(datos, original.codificacion)
	except UnicodeDecodeError as error:
		raise ErrorConversion(_("Tiene bytes que no valen en {c} (posición {p}); revise el informe de caracteres no válidos").format(
			c=original.nombre_codificacion, p=error.start)) from error
	nuevo_texto, cambiadas = transformar(texto, opciones)
	nuevos = nuevo_texto.encode("utf-8")
	if opciones.destino == "utf8_bom":
		nuevos = codecs.BOM_UTF8 + nuevos
	return Resultado(original, nuevos, cambiadas, nuevos != datos and _cambia_codificacion(original.codificacion, opciones))


def _cambia_codificacion(codificacion: str, opciones: Opciones) -> bool:
	if opciones.destino == "utf8_bom":
		return codificacion != "utf-8-bom"
	return codificacion not in ("utf-8", "ascii")


# ── Informe de caracteres no válidos ──────────────────────────────────────────


@dataclass
class Informe:
	"""Problemas de un archivo: (línea, columna, descripción)."""

	ruta: str
	deteccion: deteccion.Deteccion | None
	problemas: list[tuple[int, int, str]] = field(default_factory=list)
	total: int = 0
	error: str = ""


_MARCA = "\U0010fffd"
_MANEJADOR = "zc_texto_marcar_invalidos"


def _marcar(error: UnicodeError) -> tuple[str, int]:
	return _MARCA * (error.end - error.start), error.end  # type: ignore[attr-defined]


codecs.register_error(_MANEJADOR, _marcar)


def _posicion(texto: str, indice: int) -> tuple[int, int]:
	linea = texto.count("\n", 0, indice) + 1
	inicio = texto.rfind("\n", 0, indice) + 1
	return linea, indice - inicio + 1


def _describir_caracter(caracter: str) -> str:
	codigo = ord(caracter)
	if caracter == "�":
		return _("carácter de sustitución (U+FFFD): el texto ya se estropeó al guardarlo")
	if caracter == "\x00":
		return _("carácter nulo (U+0000)")
	nombre = unicodedata.name(caracter, "")
	return _("carácter de control U+{c:04X}{n}").format(c=codigo, n=f" ({nombre})" if nombre else "")


def informar(ruta: str, datos: bytes) -> Informe:
	"""Bytes que no valen en la codificación detectada, sustituciones y caracteres de control."""
	if deteccion.es_binario(datos):
		return Informe(ruta, None, error=_("No parece un archivo de texto"))
	det = deteccion.detectar(datos)
	informe = Informe(ruta, det)
	# Cada byte no válido se marca con un carácter de uso privado que un texto real no lleva.
	texto = deteccion.decodificar(datos, det.codificacion, errores=_MANEJADOR)
	for indice, caracter in enumerate(texto):
		problema = ""
		if caracter == _MARCA:
			problema = _("byte que no vale en {c}").format(c=det.nombre_codificacion)
		elif caracter == "�" or (ord(caracter) < 32 and caracter not in "\t\r\n\x0c") or 0x7F <= ord(caracter) < 0xA0:
			problema = _describir_caracter(caracter)
		if problema:
			informe.total += 1
			if len(informe.problemas) < MAXIMO_PROBLEMAS:
				linea, columna = _posicion(texto, indice)
				informe.problemas.append((linea, columna, problema))
	return informe


def texto_informe(informes: list[Informe]) -> str:
	"""Informe legible por líneas (sin tablas): un párrafo por archivo."""
	partes: list[str] = []
	limpios = 0
	for informe in informes:
		if informe.error:
			partes.append(_("{r}: {e}.").format(r=informe.ruta, e=informe.error))
			continue
		if not informe.total:
			limpios += 1
			continue
		cabecera = _("{r} ({c}): {n} caracteres no válidos.").format(
			r=informe.ruta, c=informe.deteccion.nombre_codificacion if informe.deteccion else "", n=informe.total)
		lineas = [cabecera]
		for linea, columna, descripcion in informe.problemas:
			lineas.append(_("Línea {l}, columna {c}: {d}.").format(l=linea, c=columna, d=descripcion))
		if informe.total > len(informe.problemas):
			lineas.append(_("Y {n} más.").format(n=informe.total - len(informe.problemas)))
		partes.append("\n".join(lineas))
	if limpios:
		partes.append(_("Sin caracteres no válidos: 1 archivo.") if limpios == 1
			else _("Sin caracteres no válidos: {n} archivos.").format(n=limpios))
	return "\n\n".join(partes) if partes else _("No hay archivos que revisar.")
