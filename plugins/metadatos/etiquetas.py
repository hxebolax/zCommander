# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Leer y escribir etiquetas de audio con mutagen (vendorizado en ``lib/``). Sin wx.

Una sola vista de las etiquetas para todos los formatos, con claves en
español: ``artista``, ``titulo``, ``album``, ``pista``, ``anio`` y ``genero``
(las que exporta ``leer_etiquetas``, diseño 2.0, 11.0), más los datos técnicos
``duracion_s``, ``bitrate``, ``frecuencia``, ``canales`` y ``portada``.

Formatos: MP3 y WAV/AIFF (ID3), FLAC, Ogg Vorbis y Opus (comentarios Vorbis),
M4A/M4B/MP4 (átomos de iTunes) y WMA (ASF). mutagen se importa por su nombre
con el ``MetaPathFinder`` del complemento (diseño 2.0, 3.4): nunca toca
``sys.path``.
"""

from __future__ import annotations

import base64
import builtins
import logging
import os
import re
import threading
from collections import OrderedDict
from typing import Any

log = logging.getLogger(__name__)

CLAVES = ("artista", "titulo", "album", "pista", "anio", "genero")
EXTENSIONES = frozenset({"mp3", "flac", "m4a", "m4b", "mp4", "aac", "ogg", "oga", "opus", "wma", "asf", "wav", "aif", "aiff"})
PATRONES = tuple(f"*.{e}" for e in sorted(EXTENSIONES))
SIN_CAMBIO = "(sin cambio)"

_ID3 = {"artista": "TPE1", "titulo": "TIT2", "album": "TALB", "pista": "TRCK", "anio": "TDRC", "genero": "TCON"}
_VORBIS = {"artista": "artist", "titulo": "title", "album": "album", "pista": "tracknumber", "anio": "date", "genero": "genre"}
_MP4 = {"artista": "\xa9ART", "titulo": "\xa9nam", "album": "\xa9alb", "anio": "\xa9day", "genero": "\xa9gen"}
_ASF = {"artista": "Author", "titulo": "Title", "album": "WM/AlbumTitle", "pista": "WM/TrackNumber", "anio": "WM/Year",
	"genero": "WM/Genre"}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorEtiquetas(Exception):
	"""Mensaje en español que se puede enseñar tal cual."""


def extension(ruta: str) -> str:
	return os.path.splitext(ruta)[1].lower().lstrip(".")


def es_audio(nombre: str) -> bool:
	return extension(nombre) in EXTENSIONES


def _abrir(ruta: str) -> Any:
	import mutagen

	try:
		audio = mutagen.File(ruta)
	except mutagen.MutagenError as error:
		raise ErrorEtiquetas(_("No se pueden leer las etiquetas de {n}: {e}").format(n=os.path.basename(ruta), e=error)) from error
	if audio is None:
		raise ErrorEtiquetas(_("{n} no es un archivo de audio que se pueda etiquetar").format(n=os.path.basename(ruta)))
	return audio


def _familia(audio: Any) -> str:
	nombre = type(audio).__name__
	if nombre in ("MP3", "WAVE", "AIFF", "EasyMP3", "TrueAudio"):
		return "id3"
	if nombre in ("FLAC", "OggVorbis", "OggOpus", "OggFLAC", "OggSpeex"):
		return "vorbis"
	if nombre in ("MP4", "EasyMP4"):
		return "mp4"
	if nombre == "ASF":
		return "asf"
	return ""


def _texto(valor: Any) -> str:
	if valor is None:
		return ""
	if isinstance(valor, (list, tuple)):
		return "; ".join(_texto(v) for v in valor if _texto(v))
	texto = getattr(valor, "text", None)
	if texto is not None:
		return _texto(texto)
	return str(valor).strip()


# ── Leer ─────────────────────────────────────────────────────────────────────


def _leer_etiquetas(audio: Any) -> dict[str, str]:
	familia = _familia(audio)
	tags = audio.tags
	resultado = dict.fromkeys(CLAVES, "")
	if tags is None:
		return resultado
	if familia == "id3":
		for clave, marco in _ID3.items():
			if marco in tags:
				resultado[clave] = _texto(tags[marco])
		if not resultado["anio"] and "TYER" in tags:
			resultado["anio"] = _texto(tags["TYER"])
	elif familia == "vorbis":
		for clave, nombre in _VORBIS.items():
			valores = tags.get(nombre) or tags.get(nombre.upper())
			if valores:
				resultado[clave] = _texto(valores)
		if not resultado["anio"] and tags.get("year"):
			resultado["anio"] = _texto(tags.get("year"))
	elif familia == "mp4":
		for clave, nombre in _MP4.items():
			if nombre in tags:
				resultado[clave] = _texto(tags[nombre])
		if "trkn" in tags and tags["trkn"]:
			numero, total = (tuple(tags["trkn"][0]) + (0, 0))[:2]
			resultado["pista"] = f"{numero}/{total}" if total else str(numero) if numero else ""
	elif familia == "asf":
		for clave, nombre in _ASF.items():
			if nombre in tags:
				resultado[clave] = _texto([getattr(v, "value", v) for v in tags[nombre]])
	if resultado["anio"]:
		resultado["anio"] = resultado["anio"][:10]
	return resultado


def _tiene_portada(audio: Any) -> bool:
	familia, tags = _familia(audio), audio.tags
	if familia == "vorbis":
		return bool(getattr(audio, "pictures", None)) or bool(tags and (tags.get("metadata_block_picture") or tags.get("METADATA_BLOCK_PICTURE")))
	if tags is None:
		return False
	if familia == "id3":
		return any(clave.startswith("APIC") for clave in tags.keys())
	if familia == "mp4":
		return bool(tags.get("covr"))
	if familia == "asf":
		return bool(tags.get("WM/Picture"))
	return False


def leer(ruta: str) -> dict[str, str]:
	"""Etiquetas y datos técnicos de ``ruta`` como textos («» si falta un dato)."""
	audio = _abrir(ruta)
	datos = _leer_etiquetas(audio)
	info = getattr(audio, "info", None)
	duracion = float(getattr(info, "length", 0) or 0)
	bitrate = int(getattr(info, "bitrate", 0) or 0)
	if not bitrate and duracion > 0 and type(audio).__name__ in ("FLAC", "WAVE", "OggOpus"):
		bitrate = int(os.path.getsize(ruta) * 8 / duracion)
	datos["duracion_s"] = f"{duracion:.3f}".rstrip("0").rstrip(".") if duracion else ""
	datos["bitrate"] = str(bitrate) if bitrate else ""
	datos["frecuencia"] = str(int(getattr(info, "sample_rate", 0) or 0) or "")
	datos["canales"] = str(int(getattr(info, "channels", 0) or 0) or "")
	datos["portada"] = "si" if _tiene_portada(audio) else "no"
	return datos


class Cache:
	"""Lecturas recientes por (ruta, tamaño, fecha): 11 columnas leen el mismo archivo una sola vez."""

	def __init__(self, maximo: int = 512) -> None:
		self._datos: OrderedDict[tuple, dict[str, str]] = OrderedDict()
		self._maximo = maximo
		self._candado = threading.Lock()

	def leer(self, ruta: str) -> dict[str, str]:
		estado = os.stat(ruta)
		clave = (os.path.normcase(ruta), estado.st_size, estado.st_mtime)
		with self._candado:
			if clave in self._datos:
				self._datos.move_to_end(clave)
				return self._datos[clave]
		datos = leer(ruta)
		with self._candado:
			self._datos[clave] = datos
			while len(self._datos) > self._maximo:
				self._datos.popitem(last=False)
		return datos

	def olvidar(self, ruta: str) -> None:
		ruta = os.path.normcase(ruta)
		with self._candado:
			for clave in [c for c in self._datos if c[0] == ruta]:
				self._datos.pop(clave, None)


# ── Escribir ─────────────────────────────────────────────────────────────────


def _id3_marco(clave: str, valor: str) -> Any:
	from mutagen import id3

	clase = getattr(id3, _ID3[clave])
	return clase(encoding=3, text=[valor])


def escribir(ruta: str, cambios: dict[str, str], version_id3: str = "2.3") -> None:
	"""Pone las etiquetas de ``cambios`` (un valor vacío la quita; las demás no se tocan)."""
	cambios = {c: v for c, v in cambios.items() if c in CLAVES and v != SIN_CAMBIO}
	if not cambios:
		return
	audio = _abrir(ruta)
	familia = _familia(audio)
	if not familia:
		raise ErrorEtiquetas(_("No se pueden escribir etiquetas en {n}").format(n=os.path.basename(ruta)))
	if audio.tags is None:
		audio.add_tags()
	tags = audio.tags
	for clave, valor in cambios.items():
		valor = valor.strip()
		if familia == "id3":
			marco = _ID3[clave]
			tags.delall(marco)
			if clave == "anio":
				tags.delall("TYER")
			if valor:
				tags.add(_id3_marco(clave, valor))
		elif familia == "vorbis":
			nombre = _VORBIS[clave]
			for variante in (nombre, nombre.upper()):
				if variante in tags:
					del tags[variante]
			if valor:
				tags[nombre] = [valor]
		elif familia == "mp4":
			if clave == "pista":
				_borrar(tags, "trkn")
				if valor:
					numero, _barra, total = valor.partition("/")
					try:
						tags["trkn"] = [(int(numero), int(total or 0))]
					except ValueError as error:
						raise ErrorEtiquetas(_("La pista debe ser un número, como 3 o 3/12")) from error
				continue
			nombre = _MP4[clave]
			_borrar(tags, nombre)
			if valor:
				tags[nombre] = [valor]
		elif familia == "asf":
			nombre = _ASF[clave]
			_borrar(tags, nombre)
			if valor:
				tags[nombre] = [valor]
	_guardar(audio, familia, version_id3)


def _borrar(tags: Any, nombre: str) -> None:
	"""Quita una etiqueta si está (las de ASF son una lista: ``pop`` no vale para todas)."""
	if nombre in tags:
		del tags[nombre]


def _guardar(audio: Any, familia: str, version_id3: str) -> None:
	if familia == "id3":
		audio.save(v2_version=4 if str(version_id3) == "2.4" else 3)
	else:
		audio.save()


def quitar(ruta: str) -> None:
	"""Quita todas las etiquetas (y la portada)."""
	audio = _abrir(ruta)
	familia = _familia(audio)
	if familia == "vorbis" and hasattr(audio, "clear_pictures"):
		audio.clear_pictures()
	if audio.tags is not None:
		audio.tags.clear()
		_guardar(audio, familia, "2.3")
	elif familia == "vorbis":
		audio.save()


# ── Portada ──────────────────────────────────────────────────────────────────


def tipo_imagen(datos: bytes) -> str:
	if datos.startswith(b"\x89PNG"):
		return "image/png"
	if datos.startswith(b"\xff\xd8"):
		return "image/jpeg"
	raise ErrorEtiquetas(_("La portada tiene que ser una imagen JPEG o PNG"))


def leer_portada(ruta: str) -> tuple[bytes, str] | None:
	"""(datos, tipo MIME) de la primera portada, o ``None``."""
	audio = _abrir(ruta)
	familia, tags = _familia(audio), audio.tags
	if familia == "vorbis":
		imagenes = list(getattr(audio, "pictures", []) or [])
		if not imagenes and tags is not None:
			from mutagen.flac import Picture

			for codificada in (tags.get("metadata_block_picture") or tags.get("METADATA_BLOCK_PICTURE") or []):
				try:
					imagenes.append(Picture(base64.b64decode(codificada)))
				except (ValueError, TypeError):
					log.debug("Portada Vorbis no válida", exc_info=True)
		return (imagenes[0].data, imagenes[0].mime) if imagenes else None
	if tags is None:
		return None
	if familia == "id3":
		for clave in tags.keys():
			if clave.startswith("APIC"):
				marco = tags[clave]
				return marco.data, marco.mime
	elif familia == "mp4" and tags.get("covr"):
		portada = tags["covr"][0]
		return bytes(portada), "image/png" if getattr(portada, "imageformat", 13) == 14 else "image/jpeg"
	elif familia == "asf" and tags.get("WM/Picture"):
		valor = tags["WM/Picture"][0].value
		# Estructura WM/Picture: tipo (1), tamaño (4), MIME UTF-16 terminado en 0, descripción UTF-16, datos.
		posicion = 5
		fin = valor.index(b"\x00\x00", posicion)
		while (fin - posicion) % 2:
			fin = valor.index(b"\x00\x00", fin + 1)
		mime = valor[posicion:fin].decode("utf-16-le")
		posicion = fin + 2
		fin = valor.index(b"\x00\x00", posicion)
		while (fin - posicion) % 2:
			fin = valor.index(b"\x00\x00", fin + 1)
		return valor[fin + 2:], mime
	return None


def poner_portada(ruta: str, datos: bytes, version_id3: str = "2.3") -> None:
	"""Sustituye la portada por ``datos`` (JPEG o PNG); con ``datos`` vacío, la quita."""
	audio = _abrir(ruta)
	familia = _familia(audio)
	mime = tipo_imagen(datos) if datos else ""
	if familia == "vorbis":
		from mutagen.flac import Picture

		imagen = Picture()
		imagen.type, imagen.mime, imagen.data, imagen.desc = 3, mime, datos, ""
		if hasattr(audio, "clear_pictures"):
			audio.clear_pictures()
			if datos:
				audio.add_picture(imagen)
		else:
			if audio.tags is None:
				audio.add_tags()
			for nombre in ("metadata_block_picture", "METADATA_BLOCK_PICTURE"):
				if nombre in audio.tags:
					del audio.tags[nombre]
			if datos:
				audio.tags["metadata_block_picture"] = [base64.b64encode(imagen.write()).decode("ascii")]
		audio.save()
		return
	if audio.tags is None:
		audio.add_tags()
	tags = audio.tags
	if familia == "id3":
		from mutagen.id3 import APIC

		tags.delall("APIC")
		if datos:
			tags.add(APIC(encoding=3, mime=mime, type=3, desc="", data=datos))
	elif familia == "mp4":
		from mutagen.mp4 import MP4Cover

		_borrar(tags, "covr")
		if datos:
			formato = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
			tags["covr"] = [MP4Cover(datos, imageformat=formato)]
	elif familia == "asf":
		from mutagen.asf import ASFByteArrayAttribute

		_borrar(tags, "WM/Picture")
		if datos:
			cuerpo = (bytes([3]) + len(datos).to_bytes(4, "little") + mime.encode("utf-16-le") + b"\x00\x00"
				+ b"\x00\x00" + datos)
			tags["WM/Picture"] = [ASFByteArrayAttribute(cuerpo)]
	else:
		raise ErrorEtiquetas(_("Este formato no admite portada"))
	_guardar(audio, familia, version_id3)


# ── Nombres y máscaras ───────────────────────────────────────────────────────

_MARCADOR = re.compile(r"\[(pista|artista|titulo|album|anio|genero|\*)\]", re.IGNORECASE)


def compilar_mascara(mascara: str) -> re.Pattern[str]:
	"""``[pista] - [artista] - [titulo]`` → expresión con un grupo por campo; ``[*]`` se salta.

	:raises ErrorEtiquetas: si la máscara no tiene ningún campo o repite uno.
	"""
	partes: list[str] = []
	vistos: set[str] = set()
	posicion = 0
	for coincidencia in _MARCADOR.finditer(mascara):
		partes.append(re.escape(mascara[posicion:coincidencia.start()]))
		campo = coincidencia.group(1).lower()
		if campo == "*":
			partes.append(".*?")
		else:
			if campo in vistos:
				raise ErrorEtiquetas(_("La máscara repite el campo [{c}]").format(c=campo))
			vistos.add(campo)
			partes.append(f"(?P<{campo}>.+?)")
		posicion = coincidencia.end()
	partes.append(re.escape(mascara[posicion:]))
	if not vistos:
		raise ErrorEtiquetas(_("La máscara necesita al menos un campo, como [artista] o [titulo]"))
	return re.compile("^" + "".join(partes) + "$", re.IGNORECASE)


def desde_nombre(mascara: str | re.Pattern[str], nombre: str) -> dict[str, str] | None:
	"""Campos que salen del nombre (sin extensión) con la máscara, o ``None`` si no encaja."""
	patron = compilar_mascara(mascara) if isinstance(mascara, str) else mascara
	base = os.path.splitext(os.path.basename(nombre))[0] if es_audio(nombre) else os.path.basename(nombre)
	coincidencia = patron.match(base.strip())
	if coincidencia is None:
		return None
	return {c: v.strip() for c, v in coincidencia.groupdict().items() if v is not None}


def numero_pista(texto: str, cifras: int = 2) -> str:
	"""«3/12» → «03»; «» → «»."""
	numero = texto.split("/", 1)[0].strip()
	return numero.zfill(cifras) if numero.isdigit() else numero


# ── Texto para la persona ────────────────────────────────────────────────────


def texto_duracion(segundos: str | float) -> str:
	try:
		total = int(float(segundos))
	except (TypeError, ValueError):
		return ""
	if total <= 0:
		return ""
	horas, resto = divmod(total, 3600)
	minutos, segundos_ = divmod(resto, 60)
	return f"{horas}:{minutos:02d}:{segundos_:02d}" if horas else f"{minutos}:{segundos_:02d}"


def texto_bitrate(bitrate: str) -> str:
	return _("{n} kb/s").format(n=round(int(bitrate) / 1000)) if bitrate.isdigit() and int(bitrate) > 0 else ""


def texto_frecuencia(frecuencia: str) -> str:
	if not frecuencia.isdigit():
		return ""
	khz = int(frecuencia) / 1000
	return _("{n} kHz").format(n=f"{khz:g}".replace(".", ","))


def texto_canales(canales: str) -> str:
	return {"1": _("1 (mono)"), "2": _("2 (estéreo)")}.get(canales, canales)


def lineas(datos: dict[str, str]) -> list[str]:
	"""Líneas para «Información del elemento» (Ctrl+Mayús+I)."""
	nombres = (("artista", _("Artista")), ("titulo", _("Título")), ("album", _("Álbum")), ("pista", _("Pista")),
		("anio", _("Año")), ("genero", _("Género")))
	resultado = [f"{etiqueta}: {datos[clave]}" for clave, etiqueta in nombres if datos.get(clave)]
	for etiqueta, valor in ((_("Duración"), texto_duracion(datos.get("duracion_s", ""))),
			(_("Tasa de bits"), texto_bitrate(datos.get("bitrate", ""))),
			(_("Frecuencia"), texto_frecuencia(datos.get("frecuencia", ""))),
			(_("Canales"), texto_canales(datos.get("canales", "")))):
		if valor:
			resultado.append(f"{etiqueta}: {valor}")
	resultado.append(_("Portada: {s}").format(s=_("sí") if datos.get("portada") == "si" else _("no")))
	return resultado
