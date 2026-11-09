# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cambios de imagen con ``wx.Image``: cargar, girar, redimensionar, guardar y alto contraste.

``wx.Image`` no es un control: se puede usar en un hilo de trabajo (cada hilo
con sus propias imágenes). Los avisos de wx al no poder abrir una imagen se
silencian con ``wx.LogNull`` (si no, saldría un cuadro de error de wx desde un
hilo) y se convierten en ``ErrorImagen`` con un mensaje en español.
"""

from __future__ import annotations

import builtins
import io
import os

import wx


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorImagen(Exception):
	"""Mensaje en español que se puede enseñar tal cual."""


#: Formatos de salida: id → (nombre, extensión, tipo de wx).
FORMATOS = {
	"jpeg": ("JPEG", ".jpg", wx.BITMAP_TYPE_JPEG),
	"png": ("PNG", ".png", wx.BITMAP_TYPE_PNG),
	"bmp": ("BMP", ".bmp", wx.BITMAP_TYPE_BMP),
	"tiff": ("TIFF", ".tif", wx.BITMAP_TYPE_TIFF),
	"gif": ("GIF", ".gif", wx.BITMAP_TYPE_GIF),
}
POR_EXTENSION = {".jpg": "jpeg", ".jpeg": "jpeg", ".jpe": "jpeg", ".png": "png", ".bmp": "bmp", ".tif": "tiff", ".tiff": "tiff",
	".gif": "gif"}


def cargar(ruta: str) -> wx.Image:
	_silencio = wx.LogNull()
	imagen = wx.Image(ruta, wx.BITMAP_TYPE_ANY)
	del _silencio
	if not imagen.IsOk():
		raise ErrorImagen(_("No se puede abrir la imagen {n}: formato no admitido o archivo dañado").format(n=os.path.basename(ruta)))
	return imagen


def orientar(imagen: wx.Image, orientacion: int) -> wx.Image:
	"""Aplica la orientación EXIF (3, 6 u 8) para ver la foto derecha."""
	if orientacion == 3:
		return imagen.Rotate180()
	if orientacion == 6:
		return imagen.Rotate90(True)
	if orientacion == 8:
		return imagen.Rotate90(False)
	return imagen


def girar(imagen: wx.Image, grados: int) -> wx.Image:
	"""90 (derecha), -90 (izquierda) o 180."""
	grados %= 360
	if grados == 90:
		return imagen.Rotate90(True)
	if grados == 270:
		return imagen.Rotate90(False)
	if grados == 180:
		return imagen.Rotate180()
	return imagen


def ajustar(imagen: wx.Image, ancho_maximo: int, alto_maximo: int) -> wx.Image:
	"""Reduce (nunca amplía) para que quepa en ``ancho_maximo`` × ``alto_maximo`` (0: sin límite), sin deformar."""
	ancho, alto = imagen.GetWidth(), imagen.GetHeight()
	escala = 1.0
	if ancho_maximo > 0 and ancho > ancho_maximo:
		escala = min(escala, ancho_maximo / ancho)
	if alto_maximo > 0 and alto > alto_maximo:
		escala = min(escala, alto_maximo / alto)
	if escala >= 1.0:
		return imagen
	return imagen.Scale(max(1, round(ancho * escala)), max(1, round(alto * escala)), wx.IMAGE_QUALITY_HIGH)


def guardar(imagen: wx.Image, destino: str, formato: str, calidad: int = 90) -> None:
	_nombre, _extension, tipo = FORMATOS[formato]
	if formato == "jpeg":
		imagen.SetOption(wx.IMAGE_OPTION_QUALITY, str(max(1, min(100, int(calidad)))))
		if imagen.HasAlpha():
			imagen.ClearAlpha()
	_silencio = wx.LogNull()
	correcto = imagen.SaveFile(destino, tipo)
	del _silencio
	if not correcto:
		raise ErrorImagen(_("No se pudo guardar {n}").format(n=os.path.basename(destino)))


def jpeg_reducido(ruta: str, lado_maximo: int = 1024, orientacion: int = 1) -> bytes:
	"""La imagen derecha, reducida a ``lado_maximo`` y en JPEG: lo que se manda al servicio de descripción."""
	imagen = orientar(cargar(ruta), orientacion)
	imagen = ajustar(imagen, lado_maximo, lado_maximo)
	if imagen.HasAlpha():
		imagen.ClearAlpha()
	imagen.SetOption(wx.IMAGE_OPTION_QUALITY, "85")
	salida = io.BytesIO()
	_silencio = wx.LogNull()
	correcto = imagen.SaveFile(salida, wx.BITMAP_TYPE_JPEG)
	del _silencio
	if not correcto:
		raise ErrorImagen(_("No se pudo preparar la imagen para describirla"))
	return salida.getvalue()


_TABLA_CONTRASTE = bytes(max(0, min(255, int((valor - 128) * 1.8 + 128))) for valor in range(256))


def alto_contraste(imagen: wx.Image) -> wx.Image:
	"""Grises con el contraste aumentado (para baja visión): una tabla de 256 valores, rápida aunque la foto sea grande."""
	gris = imagen.ConvertToGreyscale()
	gris.SetData(bytes(gris.GetData()).translate(_TABLA_CONTRASTE))
	return gris
