# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Perfiles de conversión y argumentos de FFmpeg (diseño 2.0, 11.6). Sin wx.

Todas las funciones devuelven LISTAS de argumentos (nunca una línea para un
intérprete de órdenes): el programa se lanza sin shell, y cada ruta va justo
detrás de su opción (``-i <origen>``) o al final (el destino), así un nombre
que empieza por «-» nunca se toma por una opción.

La salida se escribe siempre en un temporal que la operación renombra al
terminar; por eso los argumentos llevan ``-n`` (nunca sobrescribir): si el
temporal existiera, FFmpeg fallaría en lugar de pisarlo.
"""

from __future__ import annotations

import builtins
import os
import shlex
from dataclasses import dataclass


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Perfil:
	id: str
	nombre: str
	extension: str
	calidades: tuple[tuple[str, str], ...]
	calidad: str
	video: bool = False


PERFILES: dict[str, Perfil] = {p.id: p for p in (
	Perfil("mp3", "MP3", ".mp3", (("128", "128 kb/s"), ("192", "192 kb/s"), ("320", "320 kb/s"),
		("vbr", "Variable de alta calidad (VBR V2)")), "192"),
	Perfil("aac", "AAC (M4A)", ".m4a", (("128", "128 kb/s"), ("192", "192 kb/s"), ("256", "256 kb/s")), "192"),
	Perfil("opus", "Opus", ".opus", (("64", "64 kb/s (voz)"), ("96", "96 kb/s"), ("128", "128 kb/s"), ("160", "160 kb/s")), "96"),
	Perfil("ogg", "OGG Vorbis", ".ogg", (("4", "Calidad 4 (unos 128 kb/s)"), ("6", "Calidad 6 (unos 192 kb/s)"),
		("8", "Calidad 8 (unos 256 kb/s)")), "6"),
	Perfil("flac", "FLAC (sin pérdida)", ".flac", (("5", "Compresión normal"), ("8", "Compresión máxima")), "5"),
	Perfil("wav", "WAV (sin comprimir)", ".wav", (("16", "16 bits"), ("24", "24 bits")), "16"),
	Perfil("mp4", "MP4 (H.264 y AAC)", ".mp4", (("23", "Calidad normal"), ("18", "Calidad alta"), ("28", "Tamaño reducido")),
		"23", video=True),
	Perfil("webm", "WebM (VP9 y Opus)", ".webm", (("32", "Calidad normal"), ("24", "Calidad alta"), ("40", "Tamaño reducido")),
		"32", video=True),
	Perfil("mkv", "MKV (copiar los flujos sin recodificar)", ".mkv", (("copia", "Sin recodificar"),), "copia", video=True),
	Perfil("personalizado", "Personalizado (argumentos de FFmpeg)", "", (), ""),
)}


class ErrorArgumentos(ValueError):
	"""Argumentos personalizados no admitidos (mensaje en español)."""


def partir_perfil(texto: str) -> tuple[str, str]:
	"""«mp3_192» → («mp3», «192»); un perfil o calidad desconocidos dan los de fábrica."""
	perfil, _guion, calidad = str(texto or "").partition("_")
	if perfil not in PERFILES:
		perfil, calidad = "mp3", "192"
	datos = PERFILES[perfil]
	if calidad not in {c for c, _n in datos.calidades}:
		calidad = datos.calidad
	return perfil, calidad


def juntar_perfil(perfil: str, calidad: str) -> str:
	return f"{perfil}_{calidad}" if calidad else perfil


def opciones_codec(perfil: str, calidad: str) -> list[str]:
	"""Opciones de códec de un perfil (lo que va entre la entrada y la salida)."""
	if perfil == "mp3":
		return ["-vn", "-c:a", "libmp3lame", "-q:a", "2"] if calidad == "vbr" else ["-vn", "-c:a", "libmp3lame", "-b:a", f"{calidad}k"]
	if perfil == "aac":
		return ["-vn", "-c:a", "aac", "-b:a", f"{calidad}k"]
	if perfil == "opus":
		return ["-vn", "-c:a", "libopus", "-b:a", f"{calidad}k"]
	if perfil == "ogg":
		return ["-vn", "-c:a", "libvorbis", "-q:a", calidad]
	if perfil == "flac":
		return ["-vn", "-c:a", "flac", "-compression_level", calidad]
	if perfil == "wav":
		return ["-vn", "-c:a", "pcm_s24le" if calidad == "24" else "pcm_s16le"]
	if perfil == "mp4":
		return ["-c:v", "libx264", "-crf", calidad, "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
			"-movflags", "+faststart"]
	if perfil == "webm":
		return ["-c:v", "libvpx-vp9", "-crf", calidad, "-b:v", "0", "-c:a", "libopus", "-b:a", "128k"]
	if perfil == "mkv":
		return ["-map", "0", "-c", "copy"]
	raise ErrorArgumentos(_("Perfil desconocido: {p}").format(p=perfil))


def _comunes(ffmpeg: str) -> list[str]:
	return [ffmpeg, "-hide_banner", "-nostdin", "-n", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]


def _cola(conservar_etiquetas: bool, hilos: int, destino: str) -> list[str]:
	cola = ["-map_metadata", "0" if conservar_etiquetas else "-1"]
	if hilos > 0:
		cola += ["-threads", str(hilos)]
	return cola + [destino]


def argumentos_convertir(ffmpeg: str, origen: str, destino: str, perfil: str, calidad: str, *, conservar_etiquetas: bool = True,
		hilos: int = 0, personalizados: list[str] | None = None) -> list[str]:
	"""Conversión con un perfil (o con los argumentos personalizados ya validados)."""
	codec = list(personalizados or []) if perfil == "personalizado" else opciones_codec(perfil, calidad)
	return _comunes(ffmpeg) + ["-i", origen] + codec + _cola(conservar_etiquetas, hilos, destino)


#: Extensión del archivo que sale al extraer el audio copiando el flujo, por códec.
EXTENSION_POR_CODEC = {"aac": ".m4a", "alac": ".m4a", "mp3": ".mp3", "opus": ".opus", "vorbis": ".ogg", "flac": ".flac",
	"ac3": ".ac3", "eac3": ".eac3", "pcm_s16le": ".wav", "pcm_s24le": ".wav", "wmav2": ".wma", "mp2": ".mp2"}


def argumentos_extraer_audio(ffmpeg: str, origen: str, destino: str, copiar: bool, *, hilos: int = 0) -> list[str]:
	"""El primer flujo de audio, copiado tal cual o convertido a MP3 de 192 kb/s."""
	codec = ["-c:a", "copy"] if copiar else ["-c:a", "libmp3lame", "-b:a", "192k"]
	return _comunes(ffmpeg) + ["-i", origen, "-vn", "-map", "0:a:0"] + codec + _cola(True, hilos, destino)


def argumentos_recortar(ffmpeg: str, origen: str, destino: str, inicio: float, fin: float, copiar: bool, *,
		hilos: int = 0) -> list[str]:
	"""De ``inicio`` a ``fin`` (segundos). Con ``copiar``, sin recodificar (corta en el fotograma clave más cercano)."""
	if fin <= inicio:
		raise ErrorArgumentos(_("El fin tiene que ser posterior al inicio"))
	entrada = ["-ss", f"{inicio:.3f}", "-to", f"{fin:.3f}", "-i", origen]
	codec = ["-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero"] if copiar else []
	return _comunes(ffmpeg) + entrada + codec + _cola(True, hilos, destino)


LOUDNORM_TP, LOUDNORM_LRA = -1.5, 11.0


def argumentos_medir_volumen(ffmpeg: str, origen: str, objetivo_lufs: float) -> list[str]:
	"""Primera pasada de ``loudnorm``: mide y escribe el JSON en la salida de errores."""
	filtro = f"loudnorm=I={objetivo_lufs:g}:TP={LOUDNORM_TP:g}:LRA={LOUDNORM_LRA:g}:print_format=json"
	return [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "info", "-nostats", "-i", origen, "-vn", "-af", filtro, "-f", "null", "-"]


def codec_para_extension(extension: str) -> list[str]:
	"""Códec de audio con el que se vuelve a escribir un archivo de esa extensión (normalizar)."""
	return {
		".mp3": ["-c:a", "libmp3lame", "-q:a", "2"], ".m4a": ["-c:a", "aac", "-b:a", "192k"], ".m4b": ["-c:a", "aac", "-b:a", "128k"],
		".aac": ["-c:a", "aac", "-b:a", "192k"], ".flac": ["-c:a", "flac"], ".wav": ["-c:a", "pcm_s16le"],
		".ogg": ["-c:a", "libvorbis", "-q:a", "6"], ".opus": ["-c:a", "libopus", "-b:a", "128k"], ".wma": ["-c:a", "wmav2", "-b:a", "192k"],
	}.get(extension.lower(), ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"])


def argumentos_normalizar(ffmpeg: str, origen: str, destino: str, objetivo_lufs: float, medidas: dict[str, str], frecuencia: int,
		*, hilos: int = 0) -> list[str]:
	"""Segunda pasada de ``loudnorm`` con lo medido (normalización lineal EBU R128)."""
	filtro = (f"loudnorm=I={objetivo_lufs:g}:TP={LOUDNORM_TP:g}:LRA={LOUDNORM_LRA:g}"
		f":measured_I={medidas['input_i']}:measured_TP={medidas['input_tp']}:measured_LRA={medidas['input_lra']}"
		f":measured_thresh={medidas['input_thresh']}:offset={medidas['target_offset']}:linear=true:print_format=summary")
	extension = os.path.splitext(destino)[1]
	return (_comunes(ffmpeg) + ["-i", origen, "-af", filtro, "-ar", str(frecuencia or 48000)] + codec_para_extension(extension)
		+ _cola(True, hilos, destino))


def lista_concat(rutas: list[str]) -> str:
	"""Contenido del archivo de lista del demuxer ``concat`` (comillas simples escapadas)."""
	lineas = ["ffconcat version 1.0"]
	for ruta in rutas:
		lineas.append("file '" + ruta.replace("\\", "/").replace("'", "'\\''") + "'")
	return "\n".join(lineas) + "\n"


def argumentos_unir(ffmpeg: str, lista: str, destino: str, *, hilos: int = 0) -> list[str]:
	return _comunes(ffmpeg) + ["-f", "concat", "-safe", "0", "-i", lista, "-map", "0", "-c", "copy"] + _cola(True, hilos, destino)


def argumentos_sonda(ffprobe: str, ruta: str) -> list[str]:
	return [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-i", ruta]


# ── Argumentos personalizados ────────────────────────────────────────────────

#: Opciones que no se admiten en «Personalizado»: sobrescribir, más entradas o escribir otros archivos.
PROHIBIDAS = frozenset({"-y", "-i", "-n", "-report", "-vstats_file", "-passlogfile", "-filter_script", "-filter_complex_script",
	"-dump_attachment", "-attach", "-progress", "-sdp_file"})


def _parece_ruta(texto: str) -> bool:
	return (len(texto) > 2 and texto[1] == ":" and texto[2] in "\\/") or texto.startswith(("\\\\", "/", "..", ".\\", "./")) \
		or "\\" in texto or texto.startswith("file:")


def validar_personalizados(texto: str, origen: str, carpeta_salida: str) -> list[str]:
	"""Parte y valida los argumentos que escribe la persona.

	:raises ErrorArgumentos: con ``-y`` (o cualquier forma de sobrescribir), otra entrada, una opción
		que escribe archivos, el propio original o una ruta fuera de la carpeta de salida.
	"""
	try:
		partes = [p.strip('"') for p in shlex.split(texto, posix=False)]
	except ValueError as error:
		raise ErrorArgumentos(_("Los argumentos tienen comillas sin cerrar")) from error
	if not partes:
		raise ErrorArgumentos(_("Escriba los argumentos de FFmpeg, por ejemplo: -c:a libmp3lame -b:a 128k"))
	carpeta = os.path.normcase(os.path.abspath(carpeta_salida)) if carpeta_salida else ""
	original = os.path.normcase(os.path.abspath(origen))
	for parte in partes:
		minuscula = parte.lower()
		if minuscula == "-y":
			raise ErrorArgumentos(_("No se admite -y: zCommander nunca sobrescribe el archivo original"))
		if minuscula in PROHIBIDAS:
			raise ErrorArgumentos(_("No se admite la opción {o} en los argumentos personalizados").format(o=parte))
		if _parece_ruta(parte):
			ruta = os.path.normcase(os.path.abspath(parte.removeprefix("file:")))
			if ruta == original:
				raise ErrorArgumentos(_("Los argumentos no pueden nombrar el archivo original"))
			if not carpeta or os.path.commonpath([ruta, carpeta]) != carpeta:
				raise ErrorArgumentos(_("La ruta {r} está fuera de la carpeta de salida").format(r=parte))
	return partes


# ── Nombres de salida ────────────────────────────────────────────────────────

_PROHIBIDOS = set('\\/:*?"<>|')


def nombre_salida(mascara: str, origen: str, extension: str, contador: int = 1) -> str:
	"""Nombre del archivo que sale: ``[N]`` nombre sin extensión, ``[E]`` extensión original, ``[C]`` contador (01).

	Sin extensión en la máscara se añade la del perfil.
	"""
	base, extension_origen = os.path.splitext(os.path.basename(origen))
	texto = (mascara or "[N]").replace("[N]", base).replace("[E]", extension_origen.lstrip(".")).replace("[C]", f"{contador:02d}")
	if any(c in _PROHIBIDOS for c in texto) or not texto.strip(" ."):
		raise ErrorArgumentos(_("El nombre «{n}» no es válido en Windows").format(n=texto))
	if extension and not texto.lower().endswith(extension.lower()):
		texto += extension
	return texto.strip()
