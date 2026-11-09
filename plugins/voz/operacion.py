# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Convertir textos y documentos en audio: audiolibros como operación del motor (diseño 2.0, 11.17). Sin wx.

Cada archivo (o cada capítulo, si se divide) se lee con la voz de SAPI a un WAV
temporal en la carpeta de destino; si el formato es MP3 u Opus, FFmpeg (el
componente ``ffmpeg``) lo convierte y el WAV se borra. Progreso por párrafos,
pausa y cancelación entre párrafos; lo que queda a medias se borra. Nunca se
sobrescribe nada: si el nombre existe, se usa «nombre (2)».
"""

from __future__ import annotations

import builtins
import logging
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.plugins import api

from . import texto as modulo_texto

log = logging.getLogger(__name__)

FORMATOS = {"wav": ".wav", "mp3": ".mp3", "opus": ".opus"}
_PROHIBIDOS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def argumentos_ffmpeg(ffmpeg: str, wav: str, destino: str, formato: str) -> list[str]:
	"""FFmpeg para pasar el WAV de la voz a MP3 (64 kb/s) u Opus (32 kb/s): voz en mono, archivos pequeños."""
	codec = {"mp3": ["-c:a", "libmp3lame", "-b:a", "64k"], "opus": ["-c:a", "libopus", "-b:a", "32k", "-application", "voip"]}[formato]
	return [ffmpeg, "-hide_banner", "-nostdin", "-n", "-loglevel", "error", "-i", wav, "-ac", "1", *codec, destino]


def nombre_seguro(texto: str, maximo: int = 80) -> str:
	limpio = _PROHIBIDOS.sub(" ", texto).strip(" .")
	limpio = re.sub(r"\s+", " ", limpio)
	return limpio[:maximo].rstrip(" .") or _("Sin título")


def nombre_libre(ruta: str) -> str:
	if not os.path.lexists(ruta):
		return ruta
	base, extension = os.path.splitext(ruta)
	n = 2
	while os.path.lexists(f"{base} ({n}){extension}"):
		n += 1
	return f"{base} ({n}){extension}"


@dataclass
class Pieza:
	"""Un archivo de audio que saldrá: su nombre sin extensión y sus párrafos."""

	nombre: str
	parrafos: list[str] = field(default_factory=list)

	@property
	def caracteres(self) -> int:
		return sum(len(p) for p in self.parrafos)


def piezas_de_documento(nombre: str, secciones: list[tuple[str, int, str]], dividir: bool) -> list[Pieza]:
	"""Un audio con todo o uno por capítulo (secciones de nivel 1). ``secciones`` = (título, nivel, texto)."""
	capitulos: list[tuple[str, list[str]]] = []
	for titulo, nivel, texto in secciones:
		bloques = ([titulo] if titulo else []) + modulo_texto.parrafos(texto)
		if dividir and nivel <= 1 and (capitulos or bloques):
			capitulos.append((titulo, bloques))
		elif capitulos:
			capitulos[-1][1].extend(bloques)
		else:
			capitulos.append((titulo, bloques))
	if not dividir or len(capitulos) < 2:
		return [Pieza(nombre, [p for _t, ps in capitulos for p in ps])]
	cifras = max(2, len(str(len(capitulos))))
	return [Pieza(f"{nombre} - {str(n).zfill(cifras)} - {nombre_seguro(t or _('Capítulo {n}').format(n=n), 60)}", ps)
		for n, (t, ps) in enumerate(capitulos, start=1) if ps]


def _borrar(ruta: str) -> None:
	try:
		if os.path.lexists(ruta):
			os.remove(ruta)
	except OSError:
		log.warning("No se pudo borrar %s", ruta, exc_info=True)


class OperacionAudiolibro(api.Operacion):
	tipo = "audiolibro"

	def __init__(self, descripcion: str, proveedor: Any, fuentes: list[str], *, carpeta: str, formato: str,
			obtener_piezas: Callable[[str, Any], list[Pieza]], exportar_wav: Callable[..., bool], ajustes: Any, pausa_ms: int,
			ffmpeg: Callable[[], str] | None, ejecutar: Callable[..., Any] | None) -> None:
		super().__init__()
		self._descripcion = descripcion
		self.proveedor = proveedor
		self.fuentes = list(fuentes)
		self.carpeta = carpeta
		self.formato = formato
		self._obtener_piezas = obtener_piezas
		self._exportar_wav = exportar_wav
		self.ajustes = ajustes
		self.pausa_ms = pausa_ms
		self._ffmpeg = ffmpeg
		self._ejecutar = ejecutar
		self.creados: list[str] = []

	def descripcion(self) -> str:
		return self._descripcion

	@property
	def carriles(self) -> frozenset[str]:
		claves = {api.clave_carril(self.proveedor, f) for f in self.fuentes}
		claves.add(api.clave_carril(self.proveedor, self.carpeta))
		return frozenset(claves)

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return [("local", self.carpeta)]

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.ANALIZANDO)
		trabajos: list[tuple[str, Pieza]] = []
		for fuente in self.fuentes:
			ctx.comprobar()
			self.progresar(actual=os.path.basename(fuente))
			try:
				piezas = self._obtener_piezas(fuente, ctx)
			except api.Cancelado:
				raise
			except Exception as error:  # noqa: BLE001 - un documento ilegible no corta los demás
				log.info("No se pudo leer %s", fuente, exc_info=True)
				self.anotar_error(fuente, str(getattr(error, "strerror", None) or error))
				continue
			trabajos.extend((fuente, p) for p in piezas if p.parrafos)
		self.progresar(archivos_total=len(trabajos), bytes_total=sum(p.caracteres for _f, p in trabajos))
		self.cambiar_estado(api.Estado.EJECUTANDO)
		hechos = 0
		for fuente, pieza in trabajos:
			ctx.comprobar()
			self.progresar(actual=pieza.nombre)
			destino = nombre_libre(os.path.join(self.carpeta, pieza.nombre + FORMATOS[self.formato]))
			try:
				self._una(ctx, pieza, destino, hechos)
				self.creados.append(destino)
			except api.Cancelado:
				raise
			except Exception as error:  # noqa: BLE001 - se anota y se sigue con el siguiente
				log.warning("No se pudo convertir %s", pieza.nombre, exc_info=True)
				self.anotar_error(fuente, str(getattr(error, "strerror", None) or error))
			hechos += pieza.caracteres
			self.sumar(archivos_hechos=1)
			self.progresar(bytes_hechos=hechos)

	def _una(self, ctx: api.ContextoEjecucion, pieza: Pieza, destino: str, hechos: int) -> None:
		marca = uuid.uuid4().hex[:8]
		base = os.path.splitext(destino)[0]
		wav = f"{base}.zcparcial-{marca}.wav"
		final = f"{base}.zcparcial-{marca}{FORMATOS[self.formato]}"
		tono = int(getattr(self.ajustes, "tono", 0))
		textos = [modulo_texto.xml_sapi(p, tono, self.pausa_ms) for p in pieza.parrafos]
		acumulado = [0]

		def avanzar(numero: int) -> None:
			acumulado[0] += len(pieza.parrafos[numero])
			self.progresar(bytes_hechos=hechos + acumulado[0])
			ctx.comprobar()

		try:
			if not self._exportar_wav(textos, wav, self.ajustes, ctx.cancelado, avanzar):
				raise api.Cancelado()
			if self.formato == "wav":
				os.replace(wav, destino)
				return
			if self._ffmpeg is None or self._ejecutar is None:
				raise api.NoAdmitido(_("Para MP3 u Opus hace falta el componente FFmpeg"))
			resultado = self._ejecutar(argumentos_ffmpeg(self._ffmpeg(), wav, final, self.formato), tiempo_s=6 * 3600,
				cancelacion=ctx.cancelado)
			if getattr(resultado, "cancelado", False):
				raise api.Cancelado()
			if resultado.codigo != 0 or not os.path.isfile(final):
				linea = bytes(resultado.errores).decode("utf-8", errors="replace").strip().splitlines()
				raise api.ErrorArchivos(_("FFmpeg no pudo crear el audio: {e}").format(e=linea[-1] if linea else resultado.codigo))
			os.replace(final, destino)
		finally:
			_borrar(wav)
			_borrar(final)
