# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cifrado de los secretos de una copia (diseño 2.0, 7.4). Sin wx.

- Con contraseña: clave con ``scrypt`` (n = 2^17, r = 8, p = 1, ``maxmem``
  calculado: el límite de OpenSSL por defecto, 32 MiB, no basta para n = 2^17) y
  ``secretos.bin`` = nonce de 12 bytes + AES-256-GCM. Los datos asociados son el
  SHA-256 del manifiesto canónico: el ``secretos.bin`` de otra copia no se puede
  meter en esta sin que el descifrado falle.
- Con DPAPI (solo copias automáticas y la restauración pendiente): los secretos
  solo se pueden leer con este usuario de Windows en este equipo. Se guarda
  dentro el SHA-256 del manifiesto canónico para la misma comprobación.

Una contraseña incorrecta y una copia dañada dan el mismo mensaje: AES-GCM no
distingue entre las dos cosas, y no hay forma de recuperar los secretos sin la
contraseña.
"""

from __future__ import annotations

import base64
import builtins
import hashlib
import json
import logging
import os
from typing import Any

from app.services.copia.formato import ErrorContrasena, ErrorCopia, manifiesto_canonico

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ALGORITMO = "scrypt"
CIFRADO = "AES-256-GCM"
N, R, P = 2 ** 17, 8, 1
LONGITUD_SAL = 16
LONGITUD_NONCE = 12
#: Contraseña «débil» por debajo de esta longitud (7.4).
LONGITUD_MINIMA = 12
#: Entropía DPAPI propia de las copias: no se pueden descifrar con la de ``secretos.dat`` ni al revés.
ENTROPIA_DPAPI = b"zCommander/copias/v1"


def maxmem(n: int, r: int) -> int:
	"""Memoria que necesita scrypt más 64 MiB de margen (unos 192 MiB con los valores de 7.4)."""
	return 128 * r * (n + 2) + 64 * 1024 * 1024


def parametros_kdf() -> dict[str, Any]:
	"""Parámetros para una copia nueva, con una sal aleatoria."""
	return {"algoritmo": ALGORITMO, "n": N, "r": R, "p": P, "sal": base64.b64encode(os.urandom(LONGITUD_SAL)).decode("ascii")}


def _validar_kdf(kdf: Any) -> tuple[bytes, int, int, int]:
	"""Rechaza parámetros absurdos de una copia ajena (una n enorme agotaría la memoria)."""
	if not isinstance(kdf, dict) or kdf.get("algoritmo") != ALGORITMO:
		raise ErrorCopia(_("La copia usa un cifrado que esta versión no conoce."))
	n, r, p = kdf.get("n"), kdf.get("r"), kdf.get("p")
	if not all(isinstance(v, int) and not isinstance(v, bool) for v in (n, r, p)):
		raise ErrorContrasena()
	if not (2 ** 10 <= n <= 2 ** 20 and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4):
		raise ErrorCopia(_("La copia usa unos parámetros de cifrado no admitidos."))
	try:
		sal = base64.b64decode(str(kdf.get("sal", "")), validate=True)
	except ValueError as error:
		raise ErrorContrasena() from error
	if len(sal) < 8:
		raise ErrorContrasena()
	return sal, n, r, p


def derivar_clave(contrasena: str, kdf: dict) -> bytes:
	sal, n, r, p = _validar_kdf(kdf)
	return hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, n=n, r=r, p=p, maxmem=maxmem(n, r), dklen=32)


def datos_asociados(manifiesto: dict) -> bytes:
	return hashlib.sha256(manifiesto_canonico(manifiesto)).digest()


def cifrar(secretos: dict[str, str], contrasena: str, manifiesto: dict) -> bytes:
	"""``secretos.bin`` para ``manifiesto`` (que ya debe llevar ``secretos.kdf``)."""
	from cryptography.hazmat.primitives.ciphers.aead import AESGCM

	clave = derivar_clave(contrasena, manifiesto["secretos"]["kdf"])
	nonce = os.urandom(LONGITUD_NONCE)
	claro = json.dumps(secretos, ensure_ascii=False, sort_keys=True).encode("utf-8")
	return nonce + AESGCM(clave).encrypt(nonce, claro, datos_asociados(manifiesto))


def descifrar(datos: bytes, contrasena: str, manifiesto: dict) -> dict[str, str]:
	"""Secretos de la copia. Lanza ``ErrorContrasena`` si la contraseña no es la buena o la copia está dañada."""
	from cryptography.exceptions import InvalidTag
	from cryptography.hazmat.primitives.ciphers.aead import AESGCM

	secretos = manifiesto.get("secretos") if isinstance(manifiesto, dict) else None
	if not isinstance(secretos, dict) or len(datos) <= LONGITUD_NONCE:
		raise ErrorContrasena()
	clave = derivar_clave(contrasena, secretos.get("kdf"))
	try:
		claro = AESGCM(clave).decrypt(datos[:LONGITUD_NONCE], datos[LONGITUD_NONCE:], datos_asociados(manifiesto))
	except InvalidTag as error:
		raise ErrorContrasena() from error
	return _como_secretos(claro)


def _como_secretos(claro: bytes) -> dict[str, str]:
	try:
		datos = json.loads(claro.decode("utf-8"))
	except (ValueError, UnicodeDecodeError) as error:
		raise ErrorContrasena() from error
	if not isinstance(datos, dict):
		raise ErrorContrasena()
	return {str(k): str(v) for k, v in datos.items()}


# ── DPAPI ─────────────────────────────────────────────────────────────────────

def _dpapi():
	from app.core.secretos import ProteccionDPAPI

	return ProteccionDPAPI(entropia=ENTROPIA_DPAPI, descripcion="zCommander copia")


def proteger_local(datos: bytes) -> bytes:
	"""Protege con DPAPI de este usuario (solo se puede leer aquí)."""
	return _dpapi().proteger(datos)


def desproteger_local(datos: bytes) -> bytes:
	from app.core.secretos import ErrorSecretos

	try:
		return _dpapi().desproteger(datos)
	except ErrorSecretos as error:
		raise ErrorCopia(_("Los secretos de esta copia automática son de otro usuario o de otro equipo.")) from error


def proteger_dpapi(secretos: dict[str, str], manifiesto: dict) -> bytes:
	sobre = {"aad": datos_asociados(manifiesto).hex(), "secretos": secretos}
	return proteger_local(json.dumps(sobre, ensure_ascii=False).encode("utf-8"))


def desproteger_dpapi(datos: bytes, manifiesto: dict) -> dict[str, str]:
	try:
		sobre = json.loads(desproteger_local(datos).decode("utf-8"))
	except (ValueError, UnicodeDecodeError) as error:
		raise ErrorContrasena() from error
	if not isinstance(sobre, dict) or sobre.get("aad") != datos_asociados(manifiesto).hex():
		raise ErrorContrasena()
	secretos = sobre.get("secretos")
	if not isinstance(secretos, dict):
		raise ErrorContrasena()
	return {str(k): str(v) for k, v in secretos.items()}


# ── Fortaleza ─────────────────────────────────────────────────────────────────

def fortaleza(contrasena: str) -> str:
	"""Medidor en texto para el diálogo de crear (7.4)."""
	if not contrasena:
		return _("Sin contraseña")
	if len(contrasena) < LONGITUD_MINIMA:
		return _("Débil: menos de {n} caracteres").format(n=LONGITUD_MINIMA)
	clases = sum((any(c.islower() for c in contrasena), any(c.isupper() for c in contrasena),
		any(c.isdigit() for c in contrasena), any(not c.isalnum() for c in contrasena)))
	if len(contrasena) >= 16 and clases >= 3:
		return _("Fuerte")
	return _("Aceptable: más larga o con números y símbolos sería más segura")
