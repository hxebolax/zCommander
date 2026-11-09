# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Del resultado del motor a un ``Documento`` y la operación «Reconocer los marcados a archivos de texto» (sin wx)."""

from __future__ import annotations

import builtins
import logging
import os
import uuid
from collections.abc import Callable, Sequence
from typing import Any

from app.plugins import api

from .motor import Resultado

log = logging.getLogger("zcplugins.zc.ocr")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def documento(titulo: str, resultado: Resultado, motor: str = "") -> api.Documento:
	"""Una sección por página («Página N», con su número para Ctrl+P); en una imagen, una sola con su nombre."""
	secciones = []
	varias = len(resultado.paginas) > 1
	for numero, lineas in enumerate(resultado.paginas, start=1):
		texto = "\n".join(l for l in lineas if l.strip())
		if varias:
			secciones.append(api.Seccion(_("Página {n} de {t}").format(n=numero, t=len(resultado.paginas)), 1, texto, numero))
		else:
			secciones.append(api.Seccion(titulo, 1, texto, 0))
	if not secciones:
		secciones.append(api.Seccion(titulo, 1, ""))
	aviso = "" if any(s.texto for s in secciones) else _("No se ha reconocido ningún texto.")
	metadatos = {"idioma": resultado.idioma, "paginas": str(len(resultado.paginas))}
	if motor:
		metadatos["motor"] = motor
	return api.Documento(titulo, tuple(secciones), metadatos, aviso)


def texto(resultado: Resultado) -> str:
	"""El texto que se guarda en el .txt: las páginas separadas por «Página N»."""
	if len(resultado.paginas) <= 1:
		return "\n".join(resultado.paginas[0] if resultado.paginas else []) + "\n"
	partes = []
	for numero, lineas in enumerate(resultado.paginas, start=1):
		partes.append(_("Página {n}").format(n=numero) + "\n" + "\n".join(lineas))
	return "\n\n".join(partes) + "\n"


def destino_txt(ruta: str, carpeta_salida: str = "") -> str:
	carpeta = carpeta_salida or os.path.dirname(ruta)
	return os.path.join(carpeta, os.path.splitext(os.path.basename(ruta))[0] + ".txt")


class OperacionLotes(api.Operacion):
	"""Reconoce cada archivo y deja un ``.txt`` junto a él (o en la carpeta de salida); no sustituye uno que ya exista."""

	tipo = "ocr_lotes"

	def __init__(self, proveedor: api.Proveedor, rutas: Sequence[str], reconocer: Callable[[str, Any], Resultado],
			carpeta_salida: str = "", sobrescribir: bool = False) -> None:
		super().__init__()
		self.proveedor = proveedor
		self.rutas = list(rutas)
		self._reconocer = reconocer
		self.carpeta_salida = carpeta_salida
		self.sobrescribir = sobrescribir
		self.escritos: list[str] = []

	def descripcion(self) -> str:
		if len(self.rutas) == 1:
			return _("Reconocer el texto de {n}").format(n=os.path.basename(self.rutas[0]))
		return _("Reconocer el texto de {n} archivos").format(n=len(self.rutas))

	@property
	def carriles(self) -> frozenset[str]:
		return frozenset(api.clave_carril(self.proveedor, r) for r in self.rutas)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return sorted({("local", os.path.dirname(destino_txt(r, self.carpeta_salida))) for r in self.rutas})

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.rutas))
		for ruta in self.rutas:
			ctx.comprobar()
			self.progresar(actual=ruta)
			destino = destino_txt(ruta, self.carpeta_salida)
			if os.path.exists(destino) and not self.sobrescribir:
				self.historial.append(_("{n} ya existe: no se sustituye").format(n=os.path.basename(destino)))
				self.sumar(omitidos=1, archivos_hechos=1)
				continue
			try:
				resultado = self._reconocer(ruta, ctx.token)
				temporal = os.path.join(os.path.dirname(destino), f"~{uuid.uuid4().hex[:8]}.zctmp")
				try:
					with open(temporal, "w", encoding="utf-8", newline="\r\n") as salida:
						salida.write(texto(resultado))
					os.replace(temporal, destino)
				except BaseException:
					if os.path.exists(temporal):
						os.remove(temporal)
					raise
				self.escritos.append(destino)
			except api.Cancelado:
				raise
			except api.ErrorArchivos as error:
				self.anotar_error(ruta, error.mensaje)
			except OSError as error:
				log.warning("No se pudo guardar el texto de %s", ruta, exc_info=True)
				self.anotar_error(ruta, _("No se pudo guardar: {e}").format(e=error.strerror or error))
			self.sumar(archivos_hechos=1)
		self.cambiar_estado(api.Estado.TERMINADA_CON_ERRORES if self.errores else api.Estado.TERMINADA)
