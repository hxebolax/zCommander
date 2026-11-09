# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Un ``Documento`` como texto plano o Markdown, y la operación que convierte varios documentos.

La operación escribe primero en un temporal de la carpeta de destino y lo
renombra al final: si se cancela, nunca queda un ``.txt`` a medias.
"""

from __future__ import annotations

import builtins
import logging
import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.plugins import api

log = logging.getLogger("zcplugins.zc.documentos")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _cabecera_metadatos(documento: api.Documento) -> list[str]:
	partes = []
	for clave, nombre in (("autor", _("Autor")), ("fecha", _("Fecha")), ("paginas", _("Páginas"))):
		if documento.metadatos.get(clave):
			partes.append(f"{nombre}: {documento.metadatos[clave]}")
	return partes


def a_texto(documento: api.Documento) -> str:
	"""Texto plano: el título, los metadatos, el aviso y cada sección con su título."""
	partes = [documento.titulo, *_cabecera_metadatos(documento)]
	if documento.aviso:
		partes.append(documento.aviso)
	for seccion in documento.secciones:
		partes.append(seccion.titulo)
		if seccion.texto:
			partes.append(seccion.texto)
	return "\n\n".join(p for p in partes if p) + "\n"


def a_markdown(documento: api.Documento) -> str:
	"""Markdown: «# Título» y «##...» por el nivel de cada sección (uno más que en el documento)."""
	partes = ["# " + documento.titulo.replace("\n", " ")]
	metadatos = _cabecera_metadatos(documento)
	if metadatos:
		partes.append("\n".join(f"- {m}" for m in metadatos))
	if documento.aviso:
		partes.append(f"> {documento.aviso}")
	for seccion in documento.secciones:
		nivel = min(6, max(1, seccion.nivel) + 1)
		partes.append("#" * nivel + " " + seccion.titulo.replace("\n", " "))
		if seccion.texto:
			partes.append(seccion.texto)
	return "\n\n".join(partes) + "\n"


@dataclass(frozen=True)
class Elemento:
	"""Un documento que convertir: de dónde sale y a qué archivo local va."""

	proveedor: api.Proveedor
	ruta: str
	destino: str


def destino_para(carpeta: str, nombre: str, formato: str) -> str:
	base = os.path.splitext(nombre)[0]
	return os.path.join(carpeta, f"{base}.{'md' if formato == 'md' else 'txt'}")


class OperacionConvertirDocumentos(api.Operacion):
	"""Guarda cada documento como TXT o Markdown; los errores de uno no paran los demás."""

	tipo = "convertir_documentos"

	def __init__(self, elementos: Sequence[Elemento], formato: str, codificacion: str,
			convertir: Callable[[api.Proveedor, str, Any], api.Documento]) -> None:
		super().__init__()
		self.elementos = list(elementos)
		self.formato = formato
		self.codificacion = codificacion
		self._convertir = convertir
		self._sobrescribir: bool | None = None
		self.escritos: list[str] = []

	def descripcion(self) -> str:
		formato = "Markdown" if self.formato == "md" else _("texto")
		if len(self.elementos) == 1:
			return _("Convertir {n} a {f}").format(n=os.path.basename(self.elementos[0].ruta), f=formato)
		return _("Convertir {n} documentos a {f}").format(n=len(self.elementos), f=formato)

	@property
	def carriles(self) -> frozenset[str]:
		claves = set()
		for elemento in self.elementos:
			claves.add(api.clave_carril(elemento.proveedor, elemento.ruta))
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return sorted({("local", os.path.dirname(e.destino)) for e in self.elementos})

	def _puede_escribir(self, ctx: api.ContextoEjecucion, destino: str) -> bool:
		if not os.path.exists(destino) or self._sobrescribir is True:
			return True
		if self._sobrescribir is False:
			return False
		with ctx.esperando():
			respuesta = ctx.decisor.elegir(_("El archivo ya existe"),
				_("{n} ya existe. ¿Sustituirlo por el documento convertido?").format(n=destino),
				[_("&Sustituir"), _("&Omitir"), _("Sustituir &todos"), _("Omitir t&odos")], predeterminada=1, escape=1,
				operacion=self.raiz())
		if respuesta in (2, 3):
			self._sobrescribir = respuesta == 2
		return respuesta in (0, 2)

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.elementos))
		for elemento in self.elementos:
			ctx.comprobar()
			self.progresar(actual=elemento.ruta)
			try:
				if not self._puede_escribir(ctx, elemento.destino):
					self.sumar(omitidos=1, archivos_hechos=1)
					continue
				documento = self._convertir(elemento.proveedor, elemento.ruta, ctx.token)
				texto = a_markdown(documento) if self.formato == "md" else a_texto(documento)
				carpeta = os.path.dirname(elemento.destino)
				temporal = os.path.join(carpeta, f"~{uuid.uuid4().hex[:8]}.zctmp")
				try:
					with open(temporal, "w", encoding=self.codificacion, newline="\r\n") as salida:
						salida.write(texto)
					os.replace(temporal, elemento.destino)
				except BaseException:
					if os.path.exists(temporal):
						os.remove(temporal)
					raise
				self.escritos.append(elemento.destino)
			except api.Cancelado:
				raise
			except api.ErrorArchivos as error:
				self.anotar_error(elemento.ruta, error.mensaje)
			except OSError as error:
				log.warning("No se pudo guardar %s", elemento.destino, exc_info=True)
				self.anotar_error(elemento.ruta, _("No se pudo guardar: {e}").format(e=error.strerror or error))
			self.sumar(archivos_hechos=1)
		self.cambiar_estado(api.Estado.TERMINADA_CON_ERRORES if self.errores else api.Estado.TERMINADA)
