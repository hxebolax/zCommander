# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lectura, validación y escritura de WAV para los sonidos (diseño 2.0, 4.4). Sin wx ni dependencias.

Formatos admitidos (los mismos para el motor, el asistente de paquetes y la
importación de ``.zcsonidos``): WAV PCM de 8 o 16 bits, mono o estéreo, de
8 000 a 48 000 Hz, de 10 s y 2 MB como máximo. Lo de 8 bits se convierte a 16
al leer. Todo lo demás (24 bits, flotante, comprimido, demasiado largo) se
rechaza con un mensaje en español que explica qué falla.

El volumen se aplica aquí con la ganancia de 4.4: ``(volumen − 100) × 0,4`` dB
(0 dB con 100, −39,6 dB con 1); con volumen 0 no hay sonido.
"""

from __future__ import annotations

import builtins
import io
import struct
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

#: Límites de 4.4.
MAX_BYTES = 2 * 1024 * 1024
MAX_SEGUNDOS = 10.0
FRECUENCIA_MINIMA = 8000
FRECUENCIA_MAXIMA = 48000


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class WavNoValido(Exception):
	"""El archivo no es un WAV que zCommander pueda reproducir; ``mensaje`` lo explica en español."""

	def __init__(self, mensaje: str) -> None:
		super().__init__(mensaje)
		self.mensaje = mensaje


@dataclass(frozen=True)
class Audio:
	"""Sonido ya leído: muestras de 16 bits con signo (intercaladas si es estéreo)."""

	canales: int
	frecuencia: int
	muestras: array

	@property
	def duracion(self) -> float:
		"""Duración en segundos."""
		return len(self.muestras) / max(1, self.canales * self.frecuencia)

	def a_wav(self, muestras: array | None = None) -> bytes:
		"""Archivo WAV completo en memoria (lo que pide ``PlaySoundW`` con ``SND_MEMORY``)."""
		return bytes_wav(self.muestras if muestras is None else muestras, self.frecuencia, self.canales)


def _datos(origen: Path | bytes) -> bytes:
	if isinstance(origen, (bytes, bytearray)):
		return bytes(origen)
	ruta = Path(origen)
	try:
		tamano = ruta.stat().st_size
	except OSError as error:
		raise WavNoValido(_("No se puede leer el archivo: {e}").format(e=error.strerror or error)) from None
	if tamano > MAX_BYTES:
		raise WavNoValido(_("El archivo ocupa {n} KB; el máximo es 2048 KB.").format(n=tamano // 1024))
	try:
		return ruta.read_bytes()
	except OSError as error:
		raise WavNoValido(_("No se puede leer el archivo: {e}").format(e=error.strerror or error)) from None


def leer(origen: Path | bytes) -> Audio:
	"""Lee y valida un WAV (ruta o bytes). Lanza ``WavNoValido`` con el motivo."""
	datos = _datos(origen)
	if len(datos) > MAX_BYTES:
		raise WavNoValido(_("El archivo ocupa {n} KB; el máximo es 2048 KB.").format(n=len(datos) // 1024))
	if len(datos) < 12 or datos[:4] != b"RIFF" or datos[8:12] != b"WAVE":
		raise WavNoValido(_("No es un archivo WAV."))
	try:
		with wave.open(io.BytesIO(datos), "rb") as lector:
			canales = lector.getnchannels()
			ancho = lector.getsampwidth()
			frecuencia = lector.getframerate()
			tramas = lector.getnframes()
			if lector.getcomptype() != "NONE":
				raise WavNoValido(_("El WAV está comprimido; solo se admite PCM sin comprimir."))
			if ancho not in (1, 2):
				raise WavNoValido(_("El WAV es de {b} bits; solo se admiten 8 o 16 bits.").format(b=ancho * 8))
			if canales not in (1, 2):
				raise WavNoValido(_("El WAV tiene {c} canales; solo se admite mono o estéreo.").format(c=canales))
			if not FRECUENCIA_MINIMA <= frecuencia <= FRECUENCIA_MAXIMA:
				raise WavNoValido(_("La frecuencia es de {f} Hz; se admite de 8000 a 48000 Hz.").format(f=frecuencia))
			if tramas / frecuencia > MAX_SEGUNDOS:
				raise WavNoValido(_("El sonido dura {s:.1f} segundos; el máximo es 10.").format(s=tramas / frecuencia))
			crudo = lector.readframes(tramas)
	except WavNoValido:
		raise
	except (wave.Error, EOFError, struct.error) as error:
		# wave da «unknown format: 3» para el flotante y «unknown format: 65534» para WAVE_FORMAT_EXTENSIBLE (24 bits).
		raise WavNoValido(_("El WAV no tiene un formato admitido (solo PCM de 8 o 16 bits): {e}").format(e=error)) from None
	if ancho == 1:
		# PCM de 8 bits: sin signo, con el cero en 128.
		muestras = array("h", ((b - 128) << 8 for b in crudo))
	else:
		muestras = array("h")
		muestras.frombytes(crudo[: len(crudo) - len(crudo) % 2])
		if sys.byteorder != "little":
			muestras.byteswap()
	if not muestras:
		raise WavNoValido(_("El WAV no tiene sonido (está vacío)."))
	return Audio(canales, frecuencia, muestras)


def problema(origen: Path | bytes) -> str | None:
	"""Motivo por el que el WAV no vale, o ``None`` si vale."""
	try:
		leer(origen)
	except WavNoValido as error:
		return error.mensaje
	return None


def ganancia(volumen: int) -> float:
	"""Factor lineal del volumen 0-100 (4.4): ``(volumen − 100) × 0,4`` dB; 0 es silencio."""
	volumen = max(0, min(100, int(volumen)))
	if volumen == 0:
		return 0.0
	return 10 ** (((volumen - 100) * 0.4) / 20)


def escalar(muestras: array, factor: float) -> array:
	"""Multiplica las muestras de 16 bits por ``factor`` (con recorte)."""
	if factor >= 0.9999:
		return array("h", muestras)
	return array("h", (int(m * factor) for m in muestras))


def bytes_wav(muestras: array, frecuencia: int, canales: int = 1) -> bytes:
	"""WAV PCM de 16 bits en memoria. Determinista (mismas muestras, mismos bytes)."""
	salida = io.BytesIO()
	with wave.open(salida, "wb") as escritor:
		escritor.setnchannels(canales)
		escritor.setsampwidth(2)
		escritor.setframerate(frecuencia)
		datos = array("h", muestras)
		if sys.byteorder != "little":
			datos.byteswap()
		escritor.writeframes(datos.tobytes())
	return salida.getvalue()


def escribir(ruta: Path, muestras: array, frecuencia: int = 44100, canales: int = 1) -> None:
	"""Escribe un WAV PCM de 16 bits (lo usa el generador de paquetes)."""
	ruta = Path(ruta)
	ruta.parent.mkdir(parents=True, exist_ok=True)
	ruta.write_bytes(bytes_wav(muestras, frecuencia, canales))
