# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Firma Ed25519 de complementos (diseño 2.0, 3.9). Sin wx.

Lo crea N2 completo; dueño posterior PL.

Lo firmado es ``b"zcommander-complemento-v1\\n"`` seguido del JSON canónico
``{"archivos": {ruta: sha256}, "id": ..., "version": ...}`` (claves ordenadas,
sin espacios, UTF-8; la serialización de la plantilla del actualizador). El
prefijo separa el dominio: una firma de complemento no vale como firma de un
manifiesto de actualización ni al revés.

``firma.ed25519`` es un JSON con la lista declarada y la firma en base64::

	{"formato": 1, "id": "...", "version": "...", "archivos": {...}, "firma": "<base64>", "clave": "<base64>"}

``clave`` (la clave pública del autor) no forma parte de lo firmado: solo sirve
para la confianza en el primer uso (3.9). Con ella, la instalación de un
complemento firmado por un autor nuevo puede comprobar su firma y fijar esa
clave para su id; una clave declarada nunca basta por sí sola para cargar.

Así ``verificar_complemento(..., comprobar_sumas=False)`` comprueba la firma
sobre la lista declarada y que los archivos presentes sean exactamente los de
la lista SIN leerlos (arranque rápido desde un pendrive); con ``True`` además
lee y suma cada archivo. Las pruebas inyectan una clave de prueba; nunca usan
la del proyecto.
"""

from __future__ import annotations

import base64
import builtins
import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

PREFIJO = b"zcommander-complemento-v1\n"
NOMBRE_FIRMA = "firma.ed25519"
#: Carpetas que nunca forman parte del paquete (la caché de Python de un desarrollo).
EXCLUIDAS = frozenset({"__pycache__"})

#: Claves públicas del proyecto (Ed25519, base64 de los 32 bytes), en tupla para poder
#: rotarlas. Es la misma pareja que firma las actualizaciones de la aplicación
#: (``CLAVES_PUBLICAS_ED25519`` del actualizador, en hexadecimal ``599e1d41…d01480``);
#: la privada está en ``tools/claves/`` y nunca se publica (peticiones-ac.md, 4).
CLAVES_PROYECTO: tuple[str, ...] = ("WZ4dQX/DSS/Qj0GkEbQ/ioh1U/jxE36l57WRZNHQFIA=",)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class ResultadoFirma:
	valida: bool
	clave: str | None
	motivo: str
	#: Sumas declaradas (ruta → SHA-256) si la firma es válida: las usa el cargador verificado.
	archivos: dict[str, str] = field(default_factory=dict)


def _sha256(ruta: Path) -> str:
	suma = hashlib.sha256()
	with ruta.open("rb") as archivo:
		for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
			suma.update(bloque)
	return suma.hexdigest()


def listar_archivos(carpeta: Path) -> list[str]:
	"""Rutas relativas («/») de todos los archivos del paquete salvo la firma y ``__pycache__``."""
	carpeta = Path(carpeta)
	resultado = []
	for ruta in sorted(carpeta.rglob("*")):
		if not ruta.is_file():
			continue
		relativa = ruta.relative_to(carpeta)
		if any(parte in EXCLUIDAS for parte in relativa.parts):
			continue
		texto = relativa.as_posix()
		if texto == NOMBRE_FIRMA:
			continue
		resultado.append(texto)
	return resultado


def sumas_archivos(carpeta: Path) -> dict[str, str]:
	"""Ruta relativa → SHA-256 de cada archivo del paquete (los lee todos)."""
	carpeta = Path(carpeta)
	return {relativa: _sha256(carpeta / relativa) for relativa in listar_archivos(carpeta)}


def _canonico(datos: dict) -> bytes:
	return json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _contenido(id: str, version: str, archivos: dict[str, str]) -> bytes:
	return PREFIJO + _canonico({"archivos": dict(sorted(archivos.items())), "id": id, "version": version})


def contenido_firmado(carpeta: Path, id: str, version: str) -> bytes:
	"""El prefijo y el JSON canónico de los archivos de ``carpeta`` (los lee)."""
	return _contenido(id, version, sumas_archivos(carpeta))


def suma_paquete(carpeta: Path, id: str, version: str) -> str:
	"""SHA-256 en hexadecimal de ``contenido_firmado``: la «suma del paquete» de ``complementos.confiados``."""
	return hashlib.sha256(contenido_firmado(carpeta, id, version)).hexdigest()


def firmar_complemento(carpeta: Path, id: str, version: str, clave_privada: bytes) -> bytes:
	"""Escribe ``firma.ed25519`` en ``carpeta`` y devuelve la firma.

	:param clave_privada: los 32 bytes de la clave privada Ed25519.
	"""
	from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

	archivos = sumas_archivos(carpeta)
	privada = Ed25519PrivateKey.from_private_bytes(bytes(clave_privada))
	firma = privada.sign(_contenido(id, version, archivos))
	datos = {"formato": 1, "id": id, "version": version, "archivos": archivos,
		"firma": base64.b64encode(firma).decode("ascii"), "clave": clave_publica(clave_privada)}
	(Path(carpeta) / NOMBRE_FIRMA).write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True),
		encoding="utf-8", newline="\n")
	return firma


def clave_publica(clave_privada: bytes) -> str:
	"""Base64 de la clave pública que corresponde a una privada (para pruebas y herramientas)."""
	from cryptography.hazmat.primitives import serialization
	from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

	publica = Ed25519PrivateKey.from_private_bytes(bytes(clave_privada)).public_key()
	return base64.b64encode(publica.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode("ascii")


def leer_declaracion(carpeta: Path) -> dict | None:
	"""El contenido de ``firma.ed25519``, o ``None`` si no hay firma (o está dañada)."""
	ruta = Path(carpeta) / NOMBRE_FIRMA
	if not ruta.is_file():
		return None
	try:
		datos = json.loads(ruta.read_text(encoding="utf-8"))
	except (OSError, ValueError):
		log.warning("Firma dañada en %s", ruta, exc_info=True)
		return {}
	return datos if isinstance(datos, dict) else {}


def clave_declarada(carpeta: Path) -> str | None:
	"""Clave pública que declara la firma de ``carpeta`` (sin comprobar nada), o ``None``."""
	declaracion = leer_declaracion(carpeta)
	clave = declaracion.get("clave") if declaracion else None
	return str(clave) if isinstance(clave, str) and clave else None


def declaracion_de(carpeta: Path) -> tuple[str, str] | None:
	"""(id, versión) que declara la firma, o ``None``: deben coincidir con el manifiesto."""
	declaracion = leer_declaracion(carpeta)
	if not declaracion:
		return None
	return str(declaracion.get("id", "")), str(declaracion.get("version", ""))


def verificar_complemento(carpeta: Path, claves: Sequence[str], *, comprobar_sumas: bool) -> ResultadoFirma:
	"""Comprueba la firma de ``carpeta`` con alguna de ``claves`` (base64)."""
	from cryptography.exceptions import InvalidSignature
	from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

	declaracion = leer_declaracion(carpeta)
	if declaracion is None:
		return ResultadoFirma(False, None, _("El complemento no está firmado"))
	try:
		id_ = str(declaracion["id"])
		version = str(declaracion["version"])
		archivos = {str(k): str(v) for k, v in dict(declaracion["archivos"]).items()}
		firma = base64.b64decode(str(declaracion["firma"]), validate=True)
	except (KeyError, TypeError, ValueError):
		return ResultadoFirma(False, None, _("La firma del complemento está dañada"))
	contenido = _contenido(id_, version, archivos)
	clave_valida = None
	for clave in claves:
		try:
			Ed25519PublicKey.from_public_bytes(base64.b64decode(clave)).verify(firma, contenido)
			clave_valida = clave
			break
		except (InvalidSignature, ValueError):
			continue
	if clave_valida is None:
		return ResultadoFirma(False, None, _("La firma no corresponde a ninguna clave de confianza"))
	presentes = set(listar_archivos(carpeta))
	if presentes != set(archivos):
		de_mas = sorted(presentes - set(archivos))
		faltan = sorted(set(archivos) - presentes)
		motivo = _("Hay archivos que no están firmados: {a}").format(a=", ".join(de_mas)) if de_mas else \
			_("Faltan archivos firmados: {a}").format(a=", ".join(faltan))
		return ResultadoFirma(False, clave_valida, motivo)
	if comprobar_sumas:
		for relativa, suma in archivos.items():
			if _sha256(Path(carpeta) / relativa) != suma:
				return ResultadoFirma(False, clave_valida, _("El archivo {a} ha cambiado desde que se firmó").format(a=relativa))
	return ResultadoFirma(True, clave_valida, "", archivos)
