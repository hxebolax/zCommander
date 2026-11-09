# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Información de imágenes leyendo sus cabeceras y EXIF, sin dependencias ni wx (diseño 2.0, 11.11).

- Dimensiones y formato de PNG, JPEG, GIF, BMP, WebP y TIFF leyendo solo la
  cabecera (rápido en una columna, también en hilos).
- EXIF de JPEG y TIFF: fecha de la toma, cámara, objetivo, exposición,
  orientación y GPS.
- ``quitar_gps``: quita la ubicación de un JPEG SIN recomprimir la imagen. Se
  borra la entrada «GPSInfo» del directorio principal y se ponen a cero los
  bytes del directorio GPS y de sus valores; el resto del archivo queda igual.

Pillow tiene rueda para Python 3.15, pero no hace falta: lo de aquí cubre lo
que pide el diseño con la biblioteca estándar, y los cambios de formato y
tamaño se hacen con ``wx.Image``.
"""

from __future__ import annotations

import builtins
import os
import struct
from dataclasses import dataclass, field
from typing import Any

EXTENSIONES = frozenset({"jpg", "jpeg", "jpe", "png", "gif", "bmp", "tif", "tiff", "webp", "ico"})
PATRONES = tuple(f"*.{e}" for e in sorted(EXTENSIONES))

_TIPOS_TAMANO = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
_ETIQUETA_EXIF_IFD, _ETIQUETA_GPS_IFD = 0x8769, 0x8825


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def es_imagen(nombre: str) -> bool:
	return os.path.splitext(nombre)[1].lower().lstrip(".") in EXTENSIONES


@dataclass
class Informacion:
	formato: str = ""
	ancho: int = 0
	alto: int = 0
	profundidad: int = 0
	exif: dict[str, Any] = field(default_factory=dict)

	@property
	def megapixeles(self) -> float:
		return self.ancho * self.alto / 1_000_000

	@property
	def orientacion(self) -> str:
		girada = self.exif.get("orientacion", 1) in (5, 6, 7, 8)
		ancho, alto = (self.alto, self.ancho) if girada else (self.ancho, self.alto)
		if not ancho or not alto:
			return ""
		if ancho == alto:
			return _("cuadrada")
		return _("horizontal") if ancho > alto else _("vertical")


# ── Cabeceras ────────────────────────────────────────────────────────────────


def _jpeg_segmentos(datos: bytes):
	"""(marcador, posición del contenido, longitud del contenido) hasta el inicio de la imagen comprimida."""
	posicion = 2
	while posicion + 4 <= len(datos):
		if datos[posicion] != 0xFF:
			return
		marcador = datos[posicion + 1]
		if marcador == 0xFF:
			posicion += 1
			continue
		if marcador in (0xD8, 0x01) or 0xD0 <= marcador <= 0xD7:
			posicion += 2
			continue
		longitud = struct.unpack(">H", datos[posicion + 2:posicion + 4])[0]
		yield marcador, posicion + 4, longitud - 2
		if marcador == 0xDA:
			return
		posicion += 2 + longitud


def _cabecera(ruta: str, tamano: int = 256 * 1024) -> bytes:
	with open(ruta, "rb") as archivo:
		return archivo.read(tamano)


def dimensiones(datos: bytes) -> tuple[str, int, int, int]:
	"""(formato, ancho, alto, bits por píxel) de la cabecera; («», 0, 0, 0) si no se reconoce."""
	if datos.startswith(b"\x89PNG\r\n\x1a\n") and len(datos) >= 26:
		ancho, alto = struct.unpack(">II", datos[16:24])
		profundidad, color = datos[24], datos[25]
		canales = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color, 1)
		return "PNG", ancho, alto, profundidad * canales
	if datos.startswith(b"\xff\xd8"):
		for marcador, inicio, _longitud in _jpeg_segmentos(datos):
			if marcador in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
				precision, alto, ancho, componentes = struct.unpack(">BHHB", datos[inicio:inicio + 6])
				return "JPEG", ancho, alto, precision * componentes
		return "JPEG", 0, 0, 0
	if datos[:6] in (b"GIF87a", b"GIF89a") and len(datos) >= 10:
		ancho, alto = struct.unpack("<HH", datos[6:10])
		return "GIF", ancho, alto, 8
	if datos.startswith(b"BM") and len(datos) >= 30:
		ancho, alto = struct.unpack("<ii", datos[18:26])
		profundidad = struct.unpack("<H", datos[28:30])[0]
		return "BMP", ancho, abs(alto), profundidad
	if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP" and len(datos) >= 30:
		bloque = datos[12:16]
		if bloque == b"VP8X":
			ancho = int.from_bytes(datos[24:27], "little") + 1
			alto = int.from_bytes(datos[27:30], "little") + 1
			return "WebP", ancho, alto, 32 if datos[20] & 0x10 else 24
		if bloque == b"VP8L":
			bits = int.from_bytes(datos[21:25], "little")
			return "WebP", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1, 32
		if bloque == b"VP8 ":
			ancho, alto = struct.unpack("<HH", datos[26:30])
			return "WebP", ancho & 0x3FFF, alto & 0x3FFF, 24
	if datos[:4] in (b"II*\x00", b"MM\x00*"):
		etiquetas = _leer_tiff(datos, 0)
		principal = etiquetas.get("ifd0", {})
		bits = principal.get(258, 8)
		muestras = principal.get(277, 1)
		profundidad = (sum(bits) if isinstance(bits, tuple) else int(bits) * int(muestras or 1))
		return "TIFF", int(principal.get(256, 0) or 0), int(principal.get(257, 0) or 0), profundidad
	if datos[:4] == b"\x00\x00\x01\x00" and len(datos) >= 8:
		return "ICO", datos[6] or 256, datos[7] or 256, 32
	return "", 0, 0, 0


# ── TIFF y EXIF ──────────────────────────────────────────────────────────────


def _valor(tiff: bytes, orden: str, tipo: int, cuenta: int, campo: bytes) -> Any:
	tamano = _TIPOS_TAMANO.get(tipo, 1) * cuenta
	if tamano > 4:
		desplazamiento = struct.unpack(orden + "I", campo)[0]
		datos = tiff[desplazamiento:desplazamiento + tamano]
	else:
		datos = campo[:tamano]
	if len(datos) < tamano:
		return None
	if tipo == 2:
		return datos.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
	if tipo in (5, 10):
		formato = orden + ("I" if tipo == 5 else "i") * 2 * cuenta
		numeros = struct.unpack(formato, datos)
		valores = tuple((numeros[i] / numeros[i + 1]) if numeros[i + 1] else 0.0 for i in range(0, len(numeros), 2))
		return valores[0] if cuenta == 1 else valores
	codigos = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i", 11: "f", 12: "d"}
	if tipo in codigos:
		valores = struct.unpack(orden + codigos[tipo] * cuenta, datos)
		return valores[0] if cuenta == 1 else valores
	return datos


def _leer_ifd(tiff: bytes, orden: str, desplazamiento: int) -> dict[int, Any]:
	resultado: dict[int, Any] = {}
	if desplazamiento <= 0 or desplazamiento + 2 > len(tiff):
		return resultado
	cuenta = struct.unpack(orden + "H", tiff[desplazamiento:desplazamiento + 2])[0]
	for indice in range(cuenta):
		inicio = desplazamiento + 2 + indice * 12
		if inicio + 12 > len(tiff):
			break
		etiqueta, tipo, numero = struct.unpack(orden + "HHI", tiff[inicio:inicio + 8])
		try:
			resultado[etiqueta] = _valor(tiff, orden, tipo, numero, tiff[inicio + 8:inicio + 12])
		except struct.error:
			continue
	return resultado


def _leer_tiff(tiff: bytes, _base: int) -> dict[str, dict[int, Any]]:
	orden = "<" if tiff[:2] == b"II" else ">"
	primero = struct.unpack(orden + "I", tiff[4:8])[0]
	ifd0 = _leer_ifd(tiff, orden, primero)
	exif = _leer_ifd(tiff, orden, int(ifd0.get(_ETIQUETA_EXIF_IFD) or 0)) if ifd0.get(_ETIQUETA_EXIF_IFD) else {}
	gps = _leer_ifd(tiff, orden, int(ifd0.get(_ETIQUETA_GPS_IFD) or 0)) if ifd0.get(_ETIQUETA_GPS_IFD) else {}
	return {"ifd0": ifd0, "exif": exif, "gps": gps}


def bloque_exif(datos: bytes) -> tuple[int, bytes] | None:
	"""(posición del TIFF dentro del archivo, bytes del TIFF) del EXIF de un JPEG o de un TIFF."""
	if datos[:4] in (b"II*\x00", b"MM\x00*"):
		return 0, datos
	if not datos.startswith(b"\xff\xd8"):
		return None
	for marcador, inicio, longitud in _jpeg_segmentos(datos):
		if marcador == 0xE1 and datos[inicio:inicio + 6] == b"Exif\x00\x00":
			return inicio + 6, datos[inicio + 6:inicio + longitud]
	return None


def _grados(valor: Any, referencia: str) -> float | None:
	if not isinstance(valor, tuple) or len(valor) != 3:
		return None
	grados = valor[0] + valor[1] / 60 + valor[2] / 3600
	return -grados if referencia in ("S", "W") else grados


def _fecha(texto: Any) -> str:
	"""«2024:05:01 12:30:15» → «2024-05-01 12:30:15»."""
	if not isinstance(texto, str) or len(texto) < 10:
		return ""
	return texto[:10].replace(":", "-") + texto[10:19]


def leer_exif(datos: bytes) -> dict[str, Any]:
	"""Lo que interesa del EXIF; vacío si no hay."""
	bloque = bloque_exif(datos)
	if bloque is None or len(bloque[1]) < 8:
		return {}
	try:
		etiquetas = _leer_tiff(bloque[1], bloque[0])
	except (struct.error, ValueError):
		return {}
	ifd0, exif, gps = etiquetas["ifd0"], etiquetas["exif"], etiquetas["gps"]
	resultado: dict[str, Any] = {}
	fecha = _fecha(exif.get(0x9003) or exif.get(0x9004) or ifd0.get(0x0132))
	if fecha:
		resultado["fecha"] = fecha
	marca, modelo = str(ifd0.get(0x010F) or "").strip(), str(ifd0.get(0x0110) or "").strip()
	camara = modelo if marca and modelo.lower().startswith(marca.split(" ")[0].lower()) else " ".join(p for p in (marca, modelo) if p)
	if camara:
		resultado["camara"] = camara
	if exif.get(0xA434):
		resultado["objetivo"] = str(exif[0xA434])
	if exif.get(0x829A):
		resultado["exposicion"] = float(exif[0x829A])
	if exif.get(0x829D):
		resultado["diafragma"] = float(exif[0x829D])
	if exif.get(0x8827):
		iso = exif[0x8827]
		resultado["iso"] = int(iso[0] if isinstance(iso, tuple) else iso)
	if exif.get(0x920A):
		resultado["focal"] = float(exif[0x920A])
	if ifd0.get(0x0112):
		resultado["orientacion"] = int(ifd0[0x0112])
	if gps:
		latitud = _grados(gps.get(2), str(gps.get(1) or "N"))
		longitud = _grados(gps.get(4), str(gps.get(3) or "E"))
		if latitud is not None and longitud is not None:
			resultado["gps"] = (latitud, longitud)
		else:
			resultado["gps_presente"] = True
	return resultado


def informacion(ruta: str) -> Informacion:
	datos = _cabecera(ruta)
	formato, ancho, alto, profundidad = dimensiones(datos)
	exif = leer_exif(datos) if formato in ("JPEG", "TIFF") else {}
	if formato == "JPEG" and not exif and os.path.getsize(ruta) > len(datos):
		exif = leer_exif(_cabecera(ruta, 2 * 1024 * 1024))
	if formato == "JPEG" and not ancho:
		formato, ancho, alto, profundidad = dimensiones(_cabecera(ruta, 4 * 1024 * 1024))
	return Informacion(formato, ancho, alto, profundidad, exif)


# ── Texto para la persona ────────────────────────────────────────────────────

_ORIENTACIONES = {1: "normal", 2: "volteada en horizontal", 3: "girada 180 grados", 4: "volteada en vertical",
	5: "girada y volteada", 6: "girada 90 grados a la derecha", 7: "girada y volteada", 8: "girada 90 grados a la izquierda"}


def _decimal(numero: float, decimales: int = 1) -> str:
	return f"{numero:.{decimales}f}".rstrip("0").rstrip(".").replace(".", ",")


def texto_exposicion(exif: dict[str, Any]) -> str:
	partes = []
	tiempo = exif.get("exposicion")
	if tiempo:
		partes.append(_("1/{n} s").format(n=round(1 / tiempo)) if tiempo < 1 else _("{n} s").format(n=_decimal(tiempo)))
	if exif.get("diafragma"):
		partes.append(f"f/{_decimal(exif['diafragma'])}")
	if exif.get("iso"):
		partes.append(f"ISO {exif['iso']}")
	if exif.get("focal"):
		partes.append(_("{n} mm").format(n=_decimal(exif["focal"])))
	return ", ".join(partes)


def texto_gps(gps: tuple[float, float]) -> str:
	latitud, longitud = gps
	return _("{la} {ns}, {lo} {eo}").format(la=_decimal(abs(latitud), 5), ns=_("norte") if latitud >= 0 else _("sur"),
		lo=_decimal(abs(longitud), 5), eo=_("este") if longitud >= 0 else _("oeste"))


def lineas(info: Informacion) -> list[str]:
	"""Líneas de «Información del elemento» (Ctrl+Mayús+I)."""
	resultado = []
	if info.formato:
		resultado.append(_("Formato de imagen: {f}").format(f=info.formato))
	if info.ancho and info.alto:
		resultado.append(_("Dimensiones: {a} × {h} píxeles, {m} megapíxeles, {o}").format(a=info.ancho, h=info.alto,
			m=_decimal(info.megapixeles), o=info.orientacion))
	if info.profundidad:
		resultado.append(_("Profundidad de color: {n} bits por píxel").format(n=info.profundidad))
	exif = info.exif
	if exif.get("fecha"):
		resultado.append(_("Fecha de la toma: {f}").format(f=exif["fecha"]))
	if exif.get("camara"):
		resultado.append(_("Cámara: {c}").format(c=exif["camara"]))
	if exif.get("objetivo"):
		resultado.append(_("Objetivo: {o}").format(o=exif["objetivo"]))
	exposicion = texto_exposicion(exif)
	if exposicion:
		resultado.append(_("Exposición: {e}").format(e=exposicion))
	if exif.get("orientacion", 1) != 1:
		resultado.append(_("Orientación guardada: {o}").format(o=_(_ORIENTACIONES.get(exif["orientacion"], "desconocida"))))
	if exif.get("gps"):
		resultado.append(_("Ubicación GPS: {g}").format(g=texto_gps(exif["gps"])))
	elif exif.get("gps_presente"):
		resultado.append(_("Tiene datos de ubicación GPS"))
	return resultado


# ── Quitar el GPS sin recomprimir ────────────────────────────────────────────


def quitar_gps(datos: bytes) -> bytes | None:
	"""Los bytes del JPEG sin ubicación, o ``None`` si no tenía. Solo JPEG; la imagen no se recomprime.

	:raises ValueError: si el archivo no es un JPEG o su EXIF está dañado.
	"""
	if not datos.startswith(b"\xff\xd8"):
		raise ValueError(_("Solo se puede quitar la ubicación de las fotos JPEG"))
	bloque = bloque_exif(datos)
	if bloque is None:
		return None
	inicio, tiff = bloque
	nuevo = bytearray(tiff)
	orden = "<" if tiff[:2] == b"II" else ">"
	try:
		ifd0 = struct.unpack(orden + "I", tiff[4:8])[0]
		cuenta = struct.unpack(orden + "H", tiff[ifd0:ifd0 + 2])[0]
		entradas = [tiff[ifd0 + 2 + i * 12: ifd0 + 14 + i * 12] for i in range(cuenta)]
		posicion_gps = next((i for i, e in enumerate(entradas) if struct.unpack(orden + "H", e[:2])[0] == _ETIQUETA_GPS_IFD), None)
		if posicion_gps is None:
			return None
		desplazamiento_gps = struct.unpack(orden + "I", entradas[posicion_gps][8:12])[0]
		# Pone a cero los valores del directorio GPS que van fuera de su entrada y el propio directorio.
		if 0 < desplazamiento_gps + 2 <= len(tiff):
			cuenta_gps = struct.unpack(orden + "H", tiff[desplazamiento_gps:desplazamiento_gps + 2])[0]
			for indice in range(cuenta_gps):
				entrada = tiff[desplazamiento_gps + 2 + indice * 12: desplazamiento_gps + 14 + indice * 12]
				if len(entrada) < 12:
					break
				_etiqueta, tipo, numero = struct.unpack(orden + "HHI", entrada[:8])
				tamano = _TIPOS_TAMANO.get(tipo, 1) * numero
				if tamano > 4:
					valor = struct.unpack(orden + "I", entrada[8:12])[0]
					if 0 < valor and valor + tamano <= len(nuevo):
						nuevo[valor:valor + tamano] = bytes(tamano)
			fin = min(len(nuevo), desplazamiento_gps + 2 + cuenta_gps * 12 + 4)
			nuevo[desplazamiento_gps:fin] = bytes(fin - desplazamiento_gps)
		# Quita la entrada GPSInfo del directorio principal: las siguientes suben un puesto.
		restantes = entradas[:posicion_gps] + entradas[posicion_gps + 1:]
		siguiente = tiff[ifd0 + 2 + cuenta * 12: ifd0 + 6 + cuenta * 12]
		cuerpo = struct.pack(orden + "H", cuenta - 1) + b"".join(restantes) + siguiente + bytes(12)
		nuevo[ifd0:ifd0 + len(cuerpo)] = cuerpo
	except (struct.error, IndexError) as error:
		raise ValueError(_("Los datos EXIF de la foto están dañados")) from error
	return datos[:inicio] + bytes(nuevo) + datos[inicio + len(tiff):]
