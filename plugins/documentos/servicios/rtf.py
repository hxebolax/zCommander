# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Analizador propio y pequeño de RTF (diseño 2.0, 11.2): texto, encabezados, tablas y notas.

Lo que entiende:

- Texto con ``\\'hh`` (en la página de códigos de ``\\ansicpg``) y ``\\uN`` (con ``\\ucN``).
- Párrafos (``\\par``), saltos de línea (``\\line``) y tabuladores.
- Encabezados por ``\\outlinelevelN`` o por un estilo «heading N» / «Título N» de la hoja de estilos.
- Tablas (``\\cell``, ``\\row``) como texto lineal.
- Notas al pie (``\\footnote``) al final de su sección.
- Título y autor del grupo ``\\info``.

Lo demás (fuentes, colores, imágenes, campos, encabezados de página) se ignora.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .comun import Constructor, ErrorDocumento, Opciones, _

_TOKEN = re.compile(rb"\\([a-zA-Z]{1,32})(-?\d{1,10})? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])|([\r\n]+)|([^\\{}\r\n]+)", re.DOTALL)
_DESTINOS_IGNORADOS = {
	"fonttbl", "colortbl", "pict", "object", "header", "headerl", "headerr", "headerf", "footer", "footerl", "footerr",
	"footerf", "xmlnstbl", "listtable", "listoverridetable", "rsidtbl", "generator", "themedata", "colorschememapping",
	"datastore", "latentstyles", "fldinst", "bkmkstart", "bkmkend", "filetbl", "revtbl", "mmathPr", "pgdsctbl",
	"shppict", "nonshppict", "blipuid", "panose", "falt", "fontemb", "fontfile", "protusertbl", "wgrffmtfilter",
	"docvar", "userprops", "operator", "pntext", "pntxta", "pntxtb", "listtext", "do", "shp", "atnid", "atnauthor",
	"annotation", "comment", "template", "keywords", "doccomm", "company", "manager", "category", "hlinkbase",
}
_ESTILO_TITULO = re.compile(r"(heading|t[ií]tulo|encabezado)\s*(\d)", re.IGNORECASE)


@dataclass
class _Estado:
	ignorar: bool = False
	destino: str = ""
	uc: int = 1


@dataclass
class _Lector:
	opciones: Opciones
	codec: str = "cp1252"
	pila: list[_Estado] = field(default_factory=list)
	actual: _Estado = field(default_factory=_Estado)
	texto: list[str] = field(default_factory=list)
	bytes_pendientes: bytearray = field(default_factory=bytearray)
	saltar: int = 0
	estilo: int = 0
	nivel: int | None = None
	en_tabla: bool = False
	celdas: list[str] = field(default_factory=list)
	filas: list[list[str]] = field(default_factory=list)
	estilos: dict[int, int] = field(default_factory=dict)
	estilo_definicion: int | None = None
	nombre_estilo: list[str] = field(default_factory=list)
	info: dict[str, list[str]] = field(default_factory=dict)
	nota: list[str] | None = None
	nivel_nota: int = 0
	notas: int = 0
	parrafos: list[tuple[str, str, int | None]] = field(default_factory=list)

	# Texto ----------------------------------------------------------------

	def _volcar_bytes(self) -> None:
		if self.bytes_pendientes:
			self._escribir(self.bytes_pendientes.decode(self.codec, errors="replace"))
			self.bytes_pendientes.clear()

	def _escribir(self, texto: str) -> None:
		destino = self.actual.destino
		if destino in ("title", "author", "subject", "creatim"):
			self.info.setdefault(destino, []).append(texto)
			return
		if self.actual.destino == "estilo":
			self.nombre_estilo.append(texto)
			return
		if self.actual.ignorar:
			return
		(self.nota if self.nota is not None else self.texto).append(texto)

	def caracter(self, texto: str) -> None:
		if self.saltar:
			self.saltar -= 1
			return
		self._volcar_bytes()
		self._escribir(texto)

	# Párrafos -------------------------------------------------------------

	def fin_parrafo(self) -> None:
		self._volcar_bytes()
		if self.nota is not None:
			self.nota.append("\n")
			return
		texto = "".join(self.texto)
		self.texto = []
		if self.en_tabla:
			# Un \par dentro de una celda es un salto de línea de la celda.
			self.texto = [texto, " "] if texto.strip() else []
			return
		self._volcar_tabla()
		nivel = self.nivel if self.nivel is not None else self.estilos.get(self.estilo)
		self.parrafos.append(("encabezado" if nivel else "parrafo", texto, nivel))

	def _volcar_tabla(self) -> None:
		if self.filas:
			self.parrafos.append(("tabla", "\x1f".join("\x1e".join(f) for f in self.filas), None))
			self.filas = []

	def fin_celda(self) -> None:
		self._volcar_bytes()
		self.celdas.append("".join(self.texto))
		self.texto = []

	def fin_fila(self) -> None:
		self._volcar_bytes()
		if self.celdas:
			self.filas.append(self.celdas)
		self.celdas = []
		self.texto = []
		self.en_tabla = False

	# Grupos ---------------------------------------------------------------

	def abrir_grupo(self) -> None:
		self._volcar_bytes()
		self.pila.append(self.actual)
		self.actual = _Estado(self.actual.ignorar, self.actual.destino, self.actual.uc)
		if self.nota is not None:
			self.nivel_nota += 1

	def cerrar_grupo(self) -> None:
		self._volcar_bytes()
		if self.actual.destino == "estilo" and self.estilo_definicion is not None and (not self.pila or self.pila[-1].destino != "estilo"):
			coincide = _ESTILO_TITULO.search("".join(self.nombre_estilo))
			if coincide and self.estilo_definicion not in self.estilos:
				self.estilos[self.estilo_definicion] = int(coincide.group(2))
			self.estilo_definicion = None
			self.nombre_estilo = []
		if self.nota is not None:
			self.nivel_nota -= 1
			if self.nivel_nota < 0:
				self.notas += 1
				texto = "".join(self.nota)
				self.nota = None
				self.nivel_nota = 0
				self.parrafos.append(("nota", texto, self.notas))
		self.actual = self.pila.pop() if self.pila else _Estado()

	def palabra(self, palabra: str, parametro: int | None, siguiente_es_asterisco: bool) -> None:
		estado = self.actual
		if palabra in _DESTINOS_IGNORADOS or siguiente_es_asterisco:
			estado.ignorar = True
			estado.destino = palabra
			return
		if palabra == "stylesheet":
			estado.ignorar = True
			estado.destino = "hoja_estilos"
			return
		if estado.destino in ("hoja_estilos", "estilo"):
			if palabra in ("s", "ds", "ts", "cs") and parametro is not None:
				estado.destino = "estilo"
				self.estilo_definicion = parametro if palabra == "s" else -1
				self.nombre_estilo = []
			elif palabra == "outlinelevel" and parametro is not None and self.estilo_definicion is not None and parametro < 9:
				self.estilos[self.estilo_definicion] = min(6, parametro + 1)
			return
		if palabra == "info":
			estado.ignorar = True
			estado.destino = "info"
			return
		if palabra in ("title", "author", "subject") and estado.destino == "info":
			estado.destino = palabra
			return
		if palabra == "footnote":
			self._volcar_bytes()
			self.nota = []
			self.nivel_nota = 0
			self.texto.append(f"[{self.notas + 1}]")
			return
		if estado.ignorar and self.nota is None:
			return
		if palabra == "ansicpg" and parametro:
			self.codec = f"cp{parametro}"
		elif palabra == "uc" and parametro is not None:
			estado.uc = max(0, parametro)
		elif palabra == "u" and parametro is not None:
			self._volcar_bytes()
			self._escribir(chr(parametro + 65536 if parametro < 0 else parametro))
			self.saltar = estado.uc
		elif palabra == "par":
			self.fin_parrafo()
		elif palabra == "pard":
			self.estilo = 0
			self.nivel = None
			self.en_tabla = False
		elif palabra == "s" and parametro is not None:
			self.estilo = parametro
		elif palabra == "outlinelevel" and parametro is not None:
			self.nivel = min(6, parametro + 1) if parametro < 9 else None
		elif palabra == "intbl":
			self.en_tabla = True
		elif palabra == "cell":
			self.fin_celda()
		elif palabra == "row":
			self.fin_fila()
		elif palabra in ("line", "sect", "page"):
			self.caracter("\n")
		elif palabra == "tab":
			self.caracter("\t")
		elif palabra in ("emdash", "endash"):
			self.caracter("—" if palabra == "emdash" else "–")
		elif palabra in ("lquote", "rquote"):
			self.caracter("'")
		elif palabra in ("ldblquote", "rdblquote"):
			self.caracter('"')
		elif palabra == "bullet":
			self.caracter("•")


def convertir_rtf(datos: bytes, nombre: str, opciones: Opciones):
	if not datos.lstrip().startswith(b"{\\rtf"):
		raise ErrorDocumento(_("No es un documento RTF"))
	lector = _Lector(opciones)
	tokens = list(_TOKEN.finditer(datos))
	for indice, token in enumerate(tokens):
		palabra, parametro, hexadecimal, simbolo, llave, _salto, texto = token.groups()
		if palabra is not None:
			lector.palabra(palabra.decode("ascii"), int(parametro) if parametro else None, False)
		elif hexadecimal is not None:
			if lector.saltar:
				lector.saltar -= 1
			else:
				lector.bytes_pendientes.append(int(hexadecimal, 16))
		elif simbolo is not None:
			if simbolo == b"*":
				lector.actual.ignorar = True
				lector.actual.destino = "*"
			elif simbolo in (b"\\", b"{", b"}"):
				lector.caracter(simbolo.decode("ascii"))
			elif simbolo == b"~":
				lector.caracter("\u00a0")
			elif simbolo == b"_":
				lector.caracter("-")
			elif simbolo in (b"\n", b"\r"):
				lector.fin_parrafo()
		elif llave == b"{":
			lector.abrir_grupo()
		elif llave == b"}":
			lector.cerrar_grupo()
		elif texto is not None:
			for caracter in texto.decode(lector.codec, errors="replace"):
				lector.caracter(caracter)
		del indice
	lector.fin_parrafo()
	lector._volcar_tabla()  # noqa: SLF001 - mismo módulo
	metadatos = {clave_es: "".join(lector.info[clave]).strip() for clave, clave_es in (("title", "titulo"), ("author", "autor"),
		("subject", "asunto")) if "".join(lector.info.get(clave, [])).strip()}
	constructor = Constructor(metadatos.get("titulo") or nombre)
	for tipo, texto, valor in lector.parrafos:
		if tipo == "encabezado" and texto.strip():
			constructor.encabezado(texto, int(valor or 1))
		elif tipo == "tabla":
			constructor.tabla([fila.split("\x1e") for fila in texto.split("\x1f")])
		elif tipo == "nota":
			constructor.nota(texto, str(valor))
		else:
			constructor.parrafo(texto)
	return constructor.documento(metadatos)
