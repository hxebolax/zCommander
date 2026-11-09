# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lo que dice ``ffprobe`` y ``-progress`` de FFmpeg, en texto para la persona. Sin wx.

- ``Informacion``: duración, contenedor, tasa de bits y flujos (códec,
  frecuencia, canales, resolución, fotogramas por segundo) de
  ``ffprobe -print_format json -show_format -show_streams``.
- ``AnalizadorProgreso``: lee ``-progress pipe:1`` por trozos. El tiempo va en
  ``out_time_us`` (microsegundos); ``out_time_ms``, pese a su nombre, también
  viene en microsegundos, así que no se usa.
- ``medidas_loudnorm``: el JSON de la primera pasada de ``loudnorm``.
- ``traducir_error``: la última línea de ``stderr`` en español.
"""

from __future__ import annotations

import builtins
import json
import re
from dataclasses import dataclass, field
from typing import Any


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _numero(valor: Any) -> float:
	try:
		return float(valor)
	except (TypeError, ValueError):
		return 0.0


def _fraccion(texto: str) -> float:
	numerador, _barra, denominador = str(texto or "").partition("/")
	try:
		return float(numerador) / float(denominador) if denominador else float(numerador)
	except (ValueError, ZeroDivisionError):
		return 0.0


def duracion_texto(segundos: float) -> str:
	total = max(0, int(round(segundos)))
	horas, resto = divmod(total, 3600)
	minutos, segundos_ = divmod(resto, 60)
	return f"{horas}:{minutos:02d}:{segundos_:02d}" if horas else f"{minutos}:{segundos_:02d}"


def interpretar_tiempo(texto: str) -> float:
	"""«0:01:30» → 90; «1:30» → 90; «90» o «90,5» → segundos.

	:raises ValueError: con un mensaje en español.
	"""
	limpio = str(texto).strip().replace(",", ".")
	if not limpio:
		raise ValueError(_("Escriba un tiempo, como 0:01:30"))
	partes = limpio.split(":")
	if len(partes) > 3:
		raise ValueError(_("«{t}» no es un tiempo válido: use horas:minutos:segundos").format(t=texto))
	try:
		numeros = [float(p) for p in partes]
	except ValueError as error:
		raise ValueError(_("«{t}» no es un tiempo válido: use horas:minutos:segundos").format(t=texto)) from error
	if any(n < 0 for n in numeros) or any(n >= 60 for n in numeros[1:]):
		raise ValueError(_("«{t}» no es un tiempo válido: los minutos y los segundos van de 0 a 59").format(t=texto))
	total = 0.0
	for numero in numeros:
		total = total * 60 + numero
	return total


def _coma(numero: float, decimales: int = 2) -> str:
	return f"{numero:.{decimales}f}".rstrip("0").rstrip(".").replace(".", ",")


@dataclass
class Flujo:
	indice: int
	tipo: str
	codec: str
	nombre_codec: str = ""
	tasa_bits: int = 0
	frecuencia: int = 0
	canales: int = 0
	disposicion_canales: str = ""
	ancho: int = 0
	alto: int = 0
	fps: float = 0.0
	idioma: str = ""


@dataclass
class Informacion:
	duracion: float = 0.0
	contenedor: str = ""
	nombre_contenedor: str = ""
	tasa_bits: int = 0
	tamano: int = 0
	flujos: list[Flujo] = field(default_factory=list)
	etiquetas: dict[str, str] = field(default_factory=dict)

	@property
	def audio(self) -> list[Flujo]:
		return [f for f in self.flujos if f.tipo == "audio"]

	@property
	def video(self) -> list[Flujo]:
		return [f for f in self.flujos if f.tipo == "video" and f.codec not in ("mjpeg", "png", "bmp")]


def analizar(texto: str | bytes) -> Informacion:
	"""``Informacion`` a partir de la salida JSON de ffprobe."""
	if isinstance(texto, bytes):
		texto = texto.decode("utf-8", errors="replace")
	datos = json.loads(texto or "{}")
	formato = datos.get("format", {}) or {}
	info = Informacion(
		duracion=_numero(formato.get("duration")), contenedor=str(formato.get("format_name", "")),
		nombre_contenedor=str(formato.get("format_long_name", "")), tasa_bits=int(_numero(formato.get("bit_rate"))),
		tamano=int(_numero(formato.get("size"))),
		etiquetas={str(k).lower(): str(v) for k, v in (formato.get("tags") or {}).items()},
	)
	for flujo in datos.get("streams", []) or []:
		info.flujos.append(Flujo(
			indice=int(_numero(flujo.get("index"))), tipo=str(flujo.get("codec_type", "")), codec=str(flujo.get("codec_name", "")),
			nombre_codec=str(flujo.get("codec_long_name", "")), tasa_bits=int(_numero(flujo.get("bit_rate"))),
			frecuencia=int(_numero(flujo.get("sample_rate"))), canales=int(_numero(flujo.get("channels"))),
			disposicion_canales=str(flujo.get("channel_layout", "")), ancho=int(_numero(flujo.get("width"))),
			alto=int(_numero(flujo.get("height"))), fps=_fraccion(flujo.get("avg_frame_rate") or flujo.get("r_frame_rate") or ""),
			idioma=str((flujo.get("tags") or {}).get("language", "")),
		))
	if not info.duracion:
		info.duracion = max((_numero(f.get("duration")) for f in datos.get("streams", []) or []), default=0.0)
	return info


def _canales(flujo: Flujo) -> str:
	if flujo.canales == 1:
		return _("mono")
	if flujo.canales == 2:
		return _("estéreo")
	return _("{n} canales").format(n=flujo.canales) + (f" ({flujo.disposicion_canales})" if flujo.disposicion_canales else "")


def describir_flujo(flujo: Flujo) -> str:
	partes = [flujo.codec.upper()]
	if flujo.tipo == "audio":
		if flujo.frecuencia:
			partes.append(_("{n} kHz").format(n=_coma(flujo.frecuencia / 1000, 1)))
		if flujo.canales:
			partes.append(_canales(flujo))
	elif flujo.tipo == "video":
		if flujo.ancho and flujo.alto:
			partes.append(f"{flujo.ancho} × {flujo.alto}")
		if flujo.fps:
			partes.append(_("{n} fotogramas por segundo").format(n=_coma(flujo.fps)))
	if flujo.tasa_bits:
		partes.append(_("{n} kb/s").format(n=round(flujo.tasa_bits / 1000)))
	if flujo.idioma and flujo.idioma != "und":
		partes.append(_("idioma {i}").format(i=flujo.idioma))
	return ", ".join(partes)


_TIPOS = {"audio": "Audio", "video": "Vídeo", "subtitle": "Subtítulos", "data": "Datos", "attachment": "Adjunto"}


def lineas(info: Informacion) -> list[str]:
	"""Líneas cortas para «Información del elemento» (Ctrl+Mayús+I)."""
	resultado = []
	if info.duracion:
		resultado.append(_("Duración: {d}").format(d=duracion_texto(info.duracion)))
	if info.nombre_contenedor or info.contenedor:
		resultado.append(_("Contenedor: {c}").format(c=info.nombre_contenedor or info.contenedor))
	if info.tasa_bits:
		resultado.append(_("Tasa de bits total: {n} kb/s").format(n=round(info.tasa_bits / 1000)))
	for flujo in info.flujos:
		tipo = _(_TIPOS.get(flujo.tipo, flujo.tipo.capitalize() or "Flujo"))
		resultado.append(f"{tipo}: {describir_flujo(flujo)}")
	return resultado


def texto(info: Informacion, nombre: str) -> str:
	"""Texto completo para el visor de solo lectura de «Información técnica»."""
	cabecera = [_("Archivo: {n}").format(n=nombre)]
	cuerpo = lineas(info)
	if info.etiquetas:
		cuerpo.append(_("Etiquetas del contenedor:"))
		cuerpo.extend(f"  {clave}: {valor}" for clave, valor in sorted(info.etiquetas.items()))
	return "\n".join(cabecera + cuerpo)


# ── Progreso ─────────────────────────────────────────────────────────────────


class AnalizadorProgreso:
	"""Lee ``-progress pipe:1`` a trozos (las líneas pueden llegar partidas)."""

	def __init__(self, duracion: float) -> None:
		self.duracion = max(0.0, float(duracion))
		self.segundos = 0.0
		self.terminado = False
		self._resto = b""

	def alimentar(self, datos: bytes) -> None:
		self._resto += datos
		*completas, self._resto = self._resto.split(b"\n")
		for linea in completas:
			clave, _igual, valor = linea.decode("utf-8", errors="replace").strip().partition("=")
			if clave == "out_time_us":
				try:
					self.segundos = max(self.segundos, int(valor) / 1_000_000)
				except ValueError:
					continue
			elif clave == "progress" and valor == "end":
				self.terminado = True

	@property
	def fraccion(self) -> float:
		if self.terminado:
			return 1.0
		if self.duracion <= 0:
			return 0.0
		return max(0.0, min(1.0, self.segundos / self.duracion))

	@property
	def porcentaje(self) -> int:
		return int(self.fraccion * 100)


# ── loudnorm y errores ───────────────────────────────────────────────────────

_CLAVES_LOUDNORM = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def medidas_loudnorm(errores: str | bytes) -> dict[str, str]:
	"""El último bloque JSON que imprime ``loudnorm`` (primera pasada).

	:raises ValueError: si no aparece o le faltan medidas.
	"""
	if isinstance(errores, bytes):
		errores = errores.decode("utf-8", errors="replace")
	bloques = re.findall(r"\{[^{}]*\}", errores, re.DOTALL)
	for bloque in reversed(bloques):
		try:
			datos = json.loads(bloque)
		except ValueError:
			continue
		if all(clave in datos for clave in _CLAVES_LOUDNORM):
			valores = {clave: str(datos[clave]) for clave in _CLAVES_LOUDNORM}
			if any(v in ("-inf", "inf", "nan") for v in valores.values()):
				raise ValueError(_("El archivo está en silencio: no hay volumen que normalizar"))
			return valores
	raise ValueError(_("FFmpeg no devolvió las medidas del volumen"))


_ERRORES = (
	("invalid data found when processing input", "Formato no reconocido"),
	("unknown encoder", "Códec no disponible"),
	("encoder not found", "Códec no disponible"),
	("unknown decoder", "Códec no disponible"),
	("decoder not found", "Códec no disponible"),
	("could not find tag for codec", "El formato de salida no admite este códec: elija otro perfil"),
	("matches no streams", "El archivo no tiene audio"),
	("does not contain any stream", "El archivo no tiene audio ni vídeo que convertir"),
	("no such file or directory", "No se encuentra el archivo"),
	("permission denied", "Acceso denegado"),
	("already exists", "El archivo de salida ya existe"),
	("no space left on device", "No queda espacio en el disco"),
	("unable to find a suitable output format", "Extensión de salida desconocida"),
	("invalid argument", "Argumento no válido"),
	("unrecognized option", "Opción de FFmpeg desconocida"),
)


def traducir_error(errores: str | bytes) -> str:
	"""La última línea con sentido de ``stderr``, traducida si se conoce."""
	if isinstance(errores, bytes):
		errores = errores.decode("utf-8", errors="replace")
	lineas_error = [linea.strip() for linea in errores.splitlines() if linea.strip()]
	texto_completo = " ".join(lineas_error).lower()
	for patron, mensaje in _ERRORES:
		if patron in texto_completo:
			return _(mensaje)
	if not lineas_error:
		return _("FFmpeg falló sin decir por qué")
	return _("FFmpeg falló: {e}").format(e=lineas_error[-1][:200])
