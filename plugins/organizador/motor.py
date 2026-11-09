# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor del organizador por metadatos (diseño 2.0, 11.23). Sin wx.

Una plantilla tiene dos partes:

- **Carpetas**: ``Fotos\\[EXIF:fecha:AAAA]\\[EXIF:fecha:MM]`` (cada tramo
  separado por «\\» es una carpeta, relativa a la carpeta base).
- **Nombre del archivo**: ``[N]`` (sin cambios) o ``[MP3:pista] - [MP3:titulo]``;
  la extensión se conserva siempre.

Cada tramo se resuelve con ``zc.renombrado.evaluar`` (3.7), que usa las
máscaras de la 1.x (``[Y]``, ``[M]``, ``[P]``...) y las de cualquier
complemento (``[EXIF:…]``, ``[MP3:…]``), activándolo si hace falta: por eso el
plan se calcula en un hilo. Un tramo que queda vacío toma el texto
``sin_dato`` («Sin fecha»).

Estados de la vista previa: «Listo», «Duplicado» (dos elementos irían al mismo
sitio: no se mueve ninguno), «Ya existe», «Sin cambios» y «Error».

Ejecutar es ``OperacionOrganizar``: una ``OperacionCopiar`` del núcleo por
elemento (con ``mover`` y ``nombre_nuevo``) como suboperación, así su deshacer
es el del motor; las carpetas que crea el organizador se añaden como pasos
``quitar_carpeta`` (deshacer las quita si quedan vacías).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.plugins import api

_ = api.traduccion("zc.organizador")[0]

LISTO, DUPLICADO, EXISTE, IGUAL, ERROR = "listo", "duplicado", "existe", "igual", "error"
_PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

PLANTILLAS_DE_FABRICA = [
	{"nombre": "Fotos por fecha EXIF", "carpetas": "Fotos\\[EXIF:fecha:AAAA]\\[EXIF:fecha:MM]", "archivo": "[N]"},
	{"nombre": "Música por artista y álbum", "carpetas": "Música\\[MP3:artista]\\[MP3:album]", "archivo": "[MP3:pista] - [MP3:titulo]"},
	{"nombre": "Documentos por año", "carpetas": "Documentos\\[Y]", "archivo": "[N]"},
]


def texto_estado(estado: str, mensaje: str = "") -> str:
	textos = {LISTO: _("Listo"), DUPLICADO: _("Duplicado"), EXISTE: _("Ya existe"), IGUAL: _("Sin cambios"), ERROR: _("Error")}
	texto = textos.get(estado, estado)
	return f"{texto}: {mensaje}" if mensaje else texto


def limpiar(tramo: str) -> str:
	"""Un tramo válido como nombre de Windows: sin caracteres prohibidos, sin puntos ni espacios al final."""
	tramo = _PROHIBIDOS.sub("_", tramo).strip().rstrip(". ")
	if tramo.split(".", 1)[0].upper() in _RESERVADOS:
		tramo = "_" + tramo
	return tramo


def tramos(plantilla: str) -> list[str]:
	"""Los tramos de la plantilla de carpetas («\\» o «/» separan; los de dentro de corchetes no)."""
	partes, actual, profundidad = [], [], 0
	for caracter in plantilla:
		if caracter == "[":
			profundidad += 1
		elif caracter == "]":
			profundidad = max(0, profundidad - 1)
		if caracter in "\\/" and profundidad == 0:
			partes.append("".join(actual))
			actual = []
		else:
			actual.append(caracter)
	partes.append("".join(actual))
	return [p for p in (x.strip() for x in partes) if p]


@dataclass
class Fila:
	entrada: api.Entrada
	carpeta: str
	nombre: str
	estado: str = LISTO
	mensaje: str = ""

	@property
	def destino(self) -> str:
		return os.path.join(self.carpeta, self.nombre) if self.carpeta else self.nombre

	@property
	def origen(self) -> str:
		return self.entrada.ruta


Evaluador = Callable[[str, api.Entrada, api.Proveedor], str]


def planificar(entradas: Sequence[api.Entrada], proveedor: api.Proveedor, base: str, plantilla_carpetas: str,
		plantilla_archivo: str, evaluar: Evaluador, sin_dato: str = "Sin fecha", cancelacion=None,
		existe: Callable[[str], bool] = os.path.lexists) -> list[Fila]:
	"""La vista previa: una fila por archivo con su destino y su estado."""
	sin_dato = limpiar(sin_dato) or _("Sin dato")
	filas: list[Fila] = []
	partes = tramos(plantilla_carpetas)
	plantilla_archivo = plantilla_archivo.strip() or "[N]"
	for entrada in entradas:
		api.comprobar(cancelacion)
		if entrada.es_carpeta or entrada.es_superior:
			continue
		try:
			carpetas = [limpiar(evaluar(p, entrada, proveedor)) or sin_dato for p in partes]
			nombre = limpiar(evaluar(plantilla_archivo, entrada, proveedor)) or entrada.nombre_sin_extension
		except api.ErrorArchivos as error:
			filas.append(Fila(entrada, "", entrada.nombre, ERROR, error.mensaje))
			continue
		if entrada.extension:
			nombre = f"{nombre}.{entrada.nombre[-len(entrada.extension):]}"
		filas.append(Fila(entrada, os.path.join(base, *carpetas), nombre))
	_marcar_estados(filas, existe)
	return filas


def _marcar_estados(filas: list[Fila], existe: Callable[[str], bool]) -> None:
	por_destino: dict[str, list[Fila]] = {}
	for fila in filas:
		if fila.estado == LISTO:
			por_destino.setdefault(os.path.normcase(os.path.normpath(fila.destino)), []).append(fila)
	for clave, grupo in por_destino.items():
		if len(grupo) > 1:
			for fila in grupo:
				fila.estado = DUPLICADO
				fila.mensaje = _("{n} elementos irían a {d}").format(n=len(grupo), d=fila.destino)
			continue
		fila = grupo[0]
		if clave == os.path.normcase(os.path.normpath(fila.origen)):
			fila.estado = IGUAL
		elif existe(fila.destino):
			fila.estado = EXISTE


def resumen(filas: Sequence[Fila]) -> str:
	"""«12 listos, 2 duplicados, 1 ya existe»."""
	cuentas: dict[str, int] = {}
	for fila in filas:
		cuentas[fila.estado] = cuentas.get(fila.estado, 0) + 1
	if not filas:
		return _("No hay archivos que organizar")
	partes = [api.formato.plural(cuentas.get(LISTO, 0), _("{n} listo"), _("{n} listos"))]
	for estado, singular, plural in ((DUPLICADO, _("{n} duplicado"), _("{n} duplicados")), (EXISTE, _("{n} ya existe"), _("{n} ya existen")),
			(IGUAL, _("{n} sin cambios"), _("{n} sin cambios")), (ERROR, _("{n} con error"), _("{n} con error"))):
		if cuentas.get(estado):
			partes.append(api.formato.plural(cuentas[estado], singular, plural))
	return ", ".join(partes)


def carpetas_nuevas(ruta: str) -> list[str]:
	"""Los niveles de ``ruta`` que aún no existen, de fuera adentro (hay que llamarla antes de crearlos)."""
	nuevas: list[str] = []
	actual = os.path.normpath(ruta)
	while not os.path.lexists(actual):
		nuevas.append(actual)
		padre = os.path.dirname(actual)
		if not padre or padre == actual:
			break
		actual = padre
	return list(reversed(nuevas))


def expandir(entradas: Sequence[api.Entrada], proveedor: api.Proveedor, cancelacion=None) -> list[api.Entrada]:
	"""Los archivos de las entradas: las carpetas se recorren (sin seguir enlaces) [trabajo]."""
	resultado: list[api.Entrada] = []
	pendientes = list(entradas)
	while pendientes:
		api.comprobar(cancelacion)
		entrada = pendientes.pop(0)
		if entrada.es_superior:
			continue
		if entrada.es_carpeta:
			if entrada.es_enlace:
				continue
			try:
				pendientes.extend(proveedor.listar(entrada.ruta, cancelacion))
			except api.Cancelado:
				raise
			except api.ErrorArchivos:
				continue
			continue
		resultado.append(entrada)
	return resultado


class OperacionOrganizar(api.Operacion):
	"""Mueve (o copia) cada fila «Listo» a su destino, con deshacer."""

	tipo = "organizar"

	def __init__(self, filas: Sequence[Fila], origen: api.Proveedor, destino: api.Proveedor, mover: bool = True) -> None:
		super().__init__()
		self.filas = [f for f in filas if f.estado == LISTO]
		self.origen = origen
		self.destino = destino
		self.mover = mover
		self.hechas: list[tuple[str, str]] = []

	def descripcion(self) -> str:
		que = api.formato.plural(len(self.filas), _("{n} archivo"), _("{n} archivos"))
		return (_("Organizar {q} (mover)") if self.mover else _("Organizar {q} (copiar)")).format(q=que)

	@property
	def carriles(self) -> frozenset[str]:
		claves = {api.clave_carril(self.origen, f.origen) for f in self.filas}
		claves |= {api.clave_carril(self.destino, f.carpeta) for f in self.filas}
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		afectadas = {(self.origen.esquema, self.origen.padre(f.origen) or "") for f in self.filas}
		afectadas |= {(self.destino.esquema, f.carpeta) for f in self.filas}
		return sorted(afectadas)

	def pares_hechos(self) -> list[tuple[str, str]]:
		"""Origen → destino de lo que se movió o copió (las notas lo usan para llevar los comentarios, 11.14)."""
		return list(self.hechas)

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		accion = api.AccionDeshacer(self.descripcion())
		self.deshacer = accion
		for fila in self.filas:
			ctx.comprobar()
			self.progresar(actual=fila.entrada.nombre)
			try:
				for carpeta in carpetas_nuevas(fila.carpeta) if self.destino.esquema in ("local", "resultados") else []:
					self.destino.crear_carpeta(carpeta)
					accion.pasos.append(api.Paso("quitar_carpeta", carpeta))
				if not self.destino.existe(fila.carpeta):
					self.destino.crear_carpeta(fila.carpeta)
			except api.ErrorArchivos as error:
				self.anotar_error(fila.carpeta, error.mensaje)
				continue
			opciones = api.OpcionesCopia(politica=api.Politica.OMITIR, lista_conflictos=False)
			sub = api.OperacionCopiar(self.origen, [fila.entrada], self.destino, fila.carpeta, opciones, mover=self.mover,
				nombre_nuevo=fila.nombre)
			self.ejecutar_sub(sub, ctx)
			self.hechas.extend(sub.pares_hechos())
		if self.deshacer is not None and not getattr(self.deshacer, "pasos", None):
			self.deshacer = None
