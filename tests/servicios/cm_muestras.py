# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comprimidos de prueba del bloque CM que no se pueden crear con ninguna herramienta libre.

RAR es un formato propietario: no hay compresor libre. Aquí se escriben a mano,
byte a byte según la nota técnica pública de RAR 5.0 (rarlab.com/technote.htm)
y la de RAR 2.9, archivos RAR **sin compresión** (método «almacenar») con
datos binarios conocidos: bastan para comprobar que libarchive los lista y
los extrae (la descompresión de RAR es cosa de libarchive y tiene sus propias
pruebas). Igual para LHA (``-lh0-``, sin compresión) y RPM (envoltorio con un
cpio dentro). CAB se crea con ``makecab.exe`` de Windows.
"""

from __future__ import annotations

import os
import struct
import subprocess
import time
import zlib
from pathlib import Path

FIRMA_RAR5 = b"Rar!\x1a\x07\x01\x00"
FIRMA_RAR4 = b"Rar!\x1a\x07\x00"


def _vint(valor: int) -> bytes:
	"""Entero de longitud variable de RAR 5 (7 bits por byte, el bit alto dice que sigue)."""
	salida = bytearray()
	while True:
		byte = valor & 0x7F
		valor >>= 7
		if valor:
			salida.append(byte | 0x80)
		else:
			salida.append(byte)
			return bytes(salida)


def _bloque5(tipo: int, banderas: int, cuerpo: bytes, extra: bytes = b"", datos: bytes | None = None) -> bytes:
	"""Cabecera general de RAR 5: CRC32, tamaño, tipo, banderas, [extra], [datos], cuerpo, extra."""
	if extra:
		banderas |= 0x0001
	if datos is not None:
		banderas |= 0x0002
	resto = _vint(tipo) + _vint(banderas)
	if extra:
		resto += _vint(len(extra))
	if datos is not None:
		resto += _vint(len(datos))
	resto += cuerpo + extra
	cabecera = _vint(len(resto)) + resto
	return struct.pack("<I", zlib.crc32(cabecera)) + cabecera + (datos or b"")


def _principal5(volumen: bool = False, numero: int = 0, solido: bool = False) -> bytes:
	banderas = (0x0001 if volumen else 0) | (0x0002 if numero else 0) | (0x0004 if solido else 0)
	cuerpo = _vint(banderas) + (_vint(numero) if numero else b"")
	return _bloque5(1, 0, cuerpo)


def _fin5(no_ultimo: bool = False) -> bytes:
	return _bloque5(5, 0, _vint(0x0001 if no_ultimo else 0))


def _archivo5(nombre: str, datos: bytes, *, total: int | None = None, crc: int | None = None, carpeta: bool = False,
		continua_antes: bool = False, continua_despues: bool = False, cifrado: bool = False, mtime: int = 1_700_000_000) -> bytes:
	nombre_bytes = nombre.encode("utf-8")
	total = len(datos) if total is None else total
	crc = zlib.crc32(datos) if crc is None else crc
	banderas_archivo = (0x0001 if carpeta else 0) | 0x0002 | (0 if carpeta else 0x0004)
	cuerpo = _vint(banderas_archivo) + _vint(0 if carpeta else total) + _vint(0x10 if carpeta else 0x20)
	cuerpo += struct.pack("<I", mtime)
	if not carpeta:
		cuerpo += struct.pack("<I", crc)
	cuerpo += _vint(0) + _vint(0) + _vint(len(nombre_bytes)) + nombre_bytes  # almacenado, Windows
	extra = b""
	if cifrado:
		# Registro de cifrado (tipo 1): AES-256, sin datos de comprobación, KDF 15, sal e IV fijos.
		registro = _vint(0x01) + _vint(0) + _vint(0) + bytes([15]) + bytes(range(16)) + bytes(range(16, 32))
		extra = _vint(len(registro)) + registro
	banderas = (0x0008 if continua_antes else 0) | (0x0010 if continua_despues else 0)
	return _bloque5(2, banderas, cuerpo, extra, b"" if carpeta else datos)


def rar5(ruta: Path, miembros: list[tuple[str, bytes | None]], *, solido: bool = False, cifrados: set[str] = frozenset()) -> Path:
	"""RAR 5 con miembros almacenados; ``bytes`` = archivo, ``None`` = carpeta."""
	partes = [FIRMA_RAR5, _principal5(solido=solido)]
	for nombre, datos in miembros:
		if datos is None:
			partes.append(_archivo5(nombre, b"", carpeta=True))
		else:
			partes.append(_archivo5(nombre, datos, cifrado=nombre in cifrados))
	partes.append(_fin5())
	ruta.write_bytes(b"".join(partes))
	return ruta


def rar5_multivolumen(carpeta: Path, base: str, nombre: str, datos: bytes, extra: tuple[str, bytes] | None = None) -> list[Path]:
	"""Dos volúmenes ``base.part1.rar`` y ``base.part2.rar``; ``nombre`` queda partido entre los dos."""
	mitad = len(datos) // 2
	uno, dos = datos[:mitad], datos[mitad:]
	vol1 = [FIRMA_RAR5, _principal5(volumen=True)]
	if extra is not None:
		vol1.append(_archivo5(extra[0], extra[1]))
	vol1 += [_archivo5(nombre, uno, total=len(datos), crc=zlib.crc32(uno), continua_despues=True), _fin5(no_ultimo=True)]
	vol2 = [FIRMA_RAR5, _principal5(volumen=True, numero=1),
		_archivo5(nombre, dos, total=len(datos), crc=zlib.crc32(datos), continua_antes=True), _fin5()]
	rutas = [carpeta / f"{base}.part1.rar", carpeta / f"{base}.part2.rar"]
	rutas[0].write_bytes(b"".join(vol1))
	rutas[1].write_bytes(b"".join(vol2))
	return rutas


def _fecha_dos(marca: float) -> int:
	t = time.localtime(marca)
	return ((t.tm_year - 1980) << 25) | (t.tm_mon << 21) | (t.tm_mday << 16) | (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)


def _bloque4(tipo: int, banderas: int, cuerpo: bytes, anadido: bytes = b"") -> bytes:
	tamano = 7 + len(cuerpo)
	sin_crc = struct.pack("<BHH", tipo, banderas, tamano) + cuerpo
	return struct.pack("<H", zlib.crc32(sin_crc) & 0xFFFF) + sin_crc + anadido


def rar4(ruta: Path, miembros: list[tuple[str, bytes]]) -> Path:
	"""RAR 2.9 (RAR 4) con archivos almacenados (método 0x30) y nombres ASCII."""
	partes = [FIRMA_RAR4, _bloque4(0x73, 0, b"\x00" * 6)]
	for nombre, datos in miembros:
		nombre_bytes = nombre.replace("/", "\\").encode("ascii")
		cuerpo = struct.pack("<IIBIIBBHI", len(datos), len(datos), 2, zlib.crc32(datos), _fecha_dos(1_700_000_000), 29, 0x30,
			len(nombre_bytes), 0x20) + nombre_bytes
		partes.append(_bloque4(0x74, 0x8000, cuerpo, datos))
	partes.append(_bloque4(0x7B, 0x4000, b""))
	ruta.write_bytes(b"".join(partes))
	return ruta


def lha(ruta: Path, miembros: list[tuple[str, bytes]]) -> Path:
	"""LHA con cabeceras de nivel 0 y método ``-lh0-`` (sin compresión)."""
	partes = []
	for nombre, datos in miembros:
		nombre_bytes = nombre.replace("/", "\\").encode("ascii")
		crc16 = _crc16(datos)
		cuerpo = b"-lh0-" + struct.pack("<IIIBB", len(datos), len(datos), _fecha_dos(1_700_000_000), 0x20, 0)
		cuerpo += bytes([len(nombre_bytes)]) + nombre_bytes + struct.pack("<H", crc16)
		suma = sum(cuerpo) & 0xFF
		partes.append(bytes([len(cuerpo), suma]) + cuerpo + datos)
	partes.append(b"\x00")
	ruta.write_bytes(b"".join(partes))
	return ruta


def _crc16(datos: bytes) -> int:
	"""CRC-16 de LHA (polinomio 0xA001, el de ARC)."""
	crc = 0
	for byte in datos:
		crc ^= byte
		for _ in range(8):
			crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
	return crc


def cpio_newc(miembros: list[tuple[str, bytes]]) -> bytes:
	"""cpio «newc» (SVR4 sin CRC) en memoria."""
	salida = bytearray()

	def entrada(nombre: str, datos: bytes, modo: int, inodo: int) -> None:
		nombre_bytes = nombre.encode("utf-8") + b"\x00"
		campos = [inodo, modo, 0, 0, 1, 1_700_000_000, len(datos), 0, 0, 0, 0, len(nombre_bytes), 0]
		salida.extend(b"070701" + b"".join(f"{c:08X}".encode() for c in campos) + nombre_bytes)
		salida.extend(b"\x00" * (-len(salida) % 4))
		salida.extend(datos)
		salida.extend(b"\x00" * (-len(salida) % 4))

	for i, (nombre, datos) in enumerate(miembros, 1):
		entrada(nombre, datos, 0o100644, i)
	entrada("TRAILER!!!", b"", 0, 0)
	return bytes(salida)


def rpm(ruta: Path, miembros: list[tuple[str, bytes]]) -> Path:
	"""RPM mínimo: cabecera de 96 bytes, firma y cabecera vacías y un cpio con gzip."""
	import gzip

	lead = b"\xed\xab\xee\xdb" + bytes([3, 0]) + struct.pack(">HH", 0, 1) + b"prueba-1.0".ljust(66, b"\x00")
	lead += struct.pack(">HH", 5, 0) + b"\x00" * 16
	assert len(lead) == 96
	vacia = b"\x8e\xad\xe8\x01" + b"\x00" * 4 + struct.pack(">II", 0, 0)
	ruta.write_bytes(lead + vacia + vacia + gzip.compress(cpio_newc(miembros)))
	return ruta


def makecab_disponible() -> str | None:
	ruta = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "makecab.exe"
	return str(ruta) if ruta.is_file() else None


def cab(ruta: Path, archivo: Path) -> Path | None:
	"""CAB con ``makecab.exe`` de Windows (un archivo, compresión MSZIP); ``None`` si no hay makecab."""
	programa = makecab_disponible()
	if programa is None:
		return None
	subprocess.run([programa, "/D", "CompressionType=MSZIP", str(archivo), str(ruta)], check=True, capture_output=True,
		cwd=str(ruta.parent), creationflags=subprocess.CREATE_NO_WINDOW)
	return ruta
