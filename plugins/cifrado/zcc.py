# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Formato ``.zcc``: AES-256-GCM por bloques con clave derivada por scrypt (diseño 2.0, 11.13). Sin wx.

Estructura (documentada para la persona en ``doc/es/formato-zcc.md``)::

	"ZCC1" | longitud del JSON (4 bytes, big-endian) | JSON de parámetros (UTF-8) | bloques

- JSON: ``{"kdf": "scrypt", "n", "r", "p", "sal", "prefijo", "nombre", "tamano", "bloque", "carpeta"}``
  (``sal`` y ``prefijo`` en base64; ``carpeta`` dice si lo cifrado es un ZIP de una carpeta).
- Cada bloque cifra ``bloque`` bytes (1 MiB; el último, lo que quede, aunque sea
  nada) y ocupa eso más 16 bytes de etiqueta GCM.
- Nonce del bloque ``i`` = ``prefijo`` (8 bytes aleatorios) + ``i`` (4 bytes, big-endian).
- Datos asociados del bloque ``i`` = la cabecera entera (magia, longitud y JSON)
  + ``i`` (4 bytes) + marca de final (1 byte: 1 en el último bloque, 0 en los demás).

Por qué así: la cabecera autenticada en cada bloque impide cambiarle el nombre,
el tamaño o los parámetros; el contador en el nonce y en los datos asociados
impide reordenar bloques; la marca de final impide truncar el archivo justo en
el borde de un bloque (el que pasaría a ser el último no lleva la marca) o
añadirle bloques. Cualquier fallo da el mismo mensaje, porque con GCM no se
puede distinguir una contraseña equivocada de un archivo cambiado.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO

from app.plugins import api

_, _n = api.traduccion("zc_cifrado")

MAGIA = b"ZCC1"
BLOQUE = 1024 * 1024
ETIQUETA = 16
EXTENSION = ".zcc"
#: Costes de scrypt de la configuración ``coste_scrypt``.
COSTES = {"normal": 2**17, "alto": 2**19}
R, P = 8, 1
MAX_JSON = 64 * 1024
MENSAJE_DANADO = "El archivo está dañado o la contraseña no es correcta"


class ErrorZcc(api.ErrorArchivos):
	"""Archivo ``.zcc`` que no se puede descifrar (dañado o contraseña equivocada)."""

	def __init__(self, mensaje: str = "", ruta: str = "") -> None:
		super().__init__(mensaje or _(MENSAJE_DANADO), ruta)


@dataclass(frozen=True)
class Cabecera:
	datos: dict
	bruta: bytes

	@property
	def nombre(self) -> str:
		return os.path.basename(str(self.datos.get("nombre", ""))) or "descifrado"

	@property
	def tamano(self) -> int:
		return int(self.datos.get("tamano", -1))

	@property
	def carpeta(self) -> bool:
		return bool(self.datos.get("carpeta", False))


def memoria_scrypt(n: int, r: int = R) -> int:
	"""``maxmem`` de ``hashlib.scrypt``: lo que necesita más 64 MiB (el límite de OpenSSL, 32 MiB, no basta)."""
	return 128 * r * (n + 2) + 64 * 1024 * 1024


def derivar_clave(contrasena: str, sal: bytes, n: int, r: int = R, p: int = P) -> bytes:
	if not contrasena:
		raise ValueError("contraseña vacía")
	return hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, n=n, r=r, p=p, maxmem=memoria_scrypt(n, r), dklen=32)


def _aes(clave: bytes):
	from cryptography.hazmat.primitives.ciphers.aead import AESGCM

	return AESGCM(clave)


def _datos_asociados(cabecera: bytes, indice: int, final: bool) -> bytes:
	return cabecera + struct.pack(">IB", indice, 1 if final else 0)


def _nonce(prefijo: bytes, indice: int) -> bytes:
	if indice >= 2**32:
		raise ErrorZcc(_("El archivo es demasiado grande para el formato .zcc"))
	return prefijo + struct.pack(">I", indice)


def crear_cabecera(nombre: str, tamano: int, n: int, carpeta: bool = False, *, sal: bytes | None = None,
		prefijo: bytes | None = None) -> tuple[bytes, dict]:
	datos = {
		"kdf": "scrypt", "n": n, "r": R, "p": P,
		"sal": base64.b64encode(sal or os.urandom(16)).decode("ascii"),
		"prefijo": base64.b64encode(prefijo or os.urandom(8)).decode("ascii"),
		"nombre": os.path.basename(nombre), "tamano": int(tamano), "bloque": BLOQUE, "carpeta": bool(carpeta),
	}
	cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
	return MAGIA + struct.pack(">I", len(cuerpo)) + cuerpo, datos


def leer_cabecera(entrada: BinaryIO) -> Cabecera:
	"""Lee y valida la cabecera; deja ``entrada`` al principio de los bloques."""
	inicio = entrada.read(8)
	if len(inicio) < 8 or inicio[:4] != MAGIA:
		raise ErrorZcc(_("No es un archivo cifrado por zCommander (.zcc)"))
	longitud = struct.unpack(">I", inicio[4:])[0]
	if not 0 < longitud <= MAX_JSON:
		raise ErrorZcc()
	cuerpo = entrada.read(longitud)
	try:
		datos = json.loads(cuerpo.decode("utf-8"))
		# Topes: un archivo ajeno no puede pedir bloques ni costes que agoten la memoria.
		if datos.get("kdf") != "scrypt" or not 0 < int(datos["bloque"]) <= 64 * BLOQUE or not 2 <= int(datos["n"]) <= 2**20:
			raise ValueError(datos)
		base64.b64decode(datos["sal"], validate=True)
		if len(base64.b64decode(datos["prefijo"], validate=True)) != 8:
			raise ValueError("prefijo")
	except (ValueError, KeyError, TypeError, UnicodeDecodeError) as error:
		raise ErrorZcc() from error
	return Cabecera(datos, inicio + cuerpo)


def clave_de(cabecera: Cabecera, contrasena: str) -> bytes:
	datos = cabecera.datos
	try:
		return derivar_clave(contrasena, base64.b64decode(datos["sal"]), int(datos["n"]), int(datos.get("r", R)), int(datos.get("p", P)))
	except (ValueError, MemoryError) as error:
		raise ErrorZcc() from error


Progreso = Callable[[int], None]


def _leer_lleno(entrada: BinaryIO, tamano: int) -> bytes:
	"""Lee ``tamano`` bytes salvo al final (``read`` de algunos proveedores devuelve menos)."""
	partes = []
	falta = tamano
	while falta > 0:
		parte = entrada.read(falta)
		if not parte:
			break
		partes.append(parte)
		falta -= len(parte)
	return b"".join(partes)


def cifrar(entrada: BinaryIO, salida: BinaryIO, contrasena: str, nombre: str, tamano: int, *, n: int = COSTES["normal"],
		carpeta: bool = False, al_progresar: Progreso | None = None, comprobar: Callable[[], None] | None = None) -> str:
	"""Cifra ``entrada`` en ``salida`` y devuelve el SHA-256 de lo cifrado (para comprobarlo después)."""
	cabecera, datos = crear_cabecera(nombre, tamano, n, carpeta)
	aes = _aes(derivar_clave(contrasena, base64.b64decode(datos["sal"]), n))
	prefijo = base64.b64decode(datos["prefijo"])
	salida.write(cabecera)
	suma = hashlib.sha256()
	total = 0
	actual = _leer_lleno(entrada, BLOQUE)
	indice = 0
	while True:
		if comprobar is not None:
			comprobar()
		siguiente = _leer_lleno(entrada, BLOQUE) if len(actual) == BLOQUE else b""
		final = not siguiente
		suma.update(actual)
		salida.write(aes.encrypt(_nonce(prefijo, indice), actual, _datos_asociados(cabecera, indice, final)))
		total += len(actual)
		if al_progresar is not None:
			al_progresar(len(actual))
		if final:
			break
		actual, indice = siguiente, indice + 1
	if tamano >= 0 and total != tamano:
		raise api.ErrorArchivos(_("El archivo cambió mientras se cifraba: {n}").format(n=nombre))
	return suma.hexdigest()


def descifrar(entrada: BinaryIO, salida: BinaryIO | None, contrasena: str, *, cabecera: Cabecera | None = None,
		al_progresar: Progreso | None = None, comprobar: Callable[[], None] | None = None) -> str:
	"""Descifra en ``salida`` (o solo comprueba, con ``None``) y devuelve el SHA-256 de lo descifrado.

	:raises ErrorZcc: con «El archivo está dañado o la contraseña no es correcta».
	"""
	from cryptography.exceptions import InvalidTag

	cabecera = cabecera or leer_cabecera(entrada)
	aes = _aes(clave_de(cabecera, contrasena))
	prefijo = base64.b64decode(cabecera.datos["prefijo"])
	tamano_bloque = int(cabecera.datos["bloque"]) + ETIQUETA
	suma = hashlib.sha256()
	total = 0
	actual = _leer_lleno(entrada, tamano_bloque)
	indice = 0
	while True:
		if comprobar is not None:
			comprobar()
		if len(actual) < ETIQUETA:
			raise ErrorZcc()
		siguiente = _leer_lleno(entrada, tamano_bloque) if len(actual) == tamano_bloque else b""
		final = not siguiente
		try:
			claro = aes.decrypt(_nonce(prefijo, indice), actual, _datos_asociados(cabecera.bruta, indice, final))
		except InvalidTag as error:
			raise ErrorZcc() from error
		suma.update(claro)
		total += len(claro)
		if salida is not None:
			salida.write(claro)
		if al_progresar is not None:
			al_progresar(len(claro))
		if final:
			break
		actual, indice = siguiente, indice + 1
	if cabecera.tamano >= 0 and total != cabecera.tamano:
		raise ErrorZcc()
	return suma.hexdigest()


# ── Contraseñas ───────────────────────────────────────────────────────────────


def fortaleza(contrasena: str) -> tuple[int, str]:
	"""Nivel de 0 a 4 y su texto («Débil: menos de 12 caracteres»...), para el medidor en texto."""
	longitud = len(contrasena)
	if not longitud:
		return 0, _("Sin contraseña")
	clases = sum(bool(re.search(patron, contrasena)) for patron in (r"[a-zñáéíóúü]", r"[A-ZÑÁÉÍÓÚÜ]", r"\d", r"[^\w\s]|_", r"\s"))
	repetida = len(set(contrasena)) <= max(2, longitud // 4)
	if longitud < 8:
		return 0, _("Muy débil: menos de 8 caracteres")
	if repetida:
		return 1, _("Débil: repite casi siempre los mismos caracteres")
	if longitud < 12:
		return 1, _("Débil: menos de 12 caracteres")
	if longitud < 16 and clases < 3:
		return 2, _("Aceptable: añada más caracteres o mezcle mayúsculas, cifras y símbolos")
	if longitud < 20 and clases < 3:
		return 3, _("Fuerte")
	return (4, _("Muy fuerte")) if longitud >= 16 else (3, _("Fuerte"))


def nombre_libre(existe: Callable[[str], bool], unir: Callable[[str], str], nombre: str) -> str:
	"""``nombre`` o, si ya existe, «nombre (2).ext», «nombre (3).ext»... (nunca se sobrescribe nada)."""
	if not existe(unir(nombre)):
		return nombre
	base, punto, extension = nombre.rpartition(".")
	if not punto or not base:
		base, extension = nombre, ""
	sufijo = f".{extension}" if extension else ""
	for numero in range(2, 10000):
		candidato = f"{base} ({numero}){sufijo}"
		if not existe(unir(candidato)):
			return candidato
	raise api.YaExiste(_("No hay un nombre libre para {n}").format(n=nombre))
