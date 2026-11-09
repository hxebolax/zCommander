# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Crea el paquete ``.zcplugin`` de un complemento y, si se pide, lo firma (diseño 2.0, 3.3, 3.9 y 3.12).

Uso::

	python tools/empaquetar_plugin.py <carpeta> [--firmar <archivo con la clave privada>] [--salida <archivo.zcplugin>]

- El paquete es un ZIP con el contenido de la carpeta en la raíz (sin carpeta
  contenedora), nombres en UTF-8, sin ``__pycache__`` ni ``.pyc``.
- ``--firmar``: archivo con la clave privada Ed25519 (32 bytes en crudo, o su
  base64 o hexadecimal en una línea). Escribe ``firma.ed25519`` con
  ``app.plugins.firma.firmar_complemento`` (NO con ``tools/firmar_version.py``,
  que firma manifiestos de actualización con otro prefijo). Una firma vieja que
  ya no corresponde se borra antes de empaquetar.
- El manifiesto se valida antes: un paquete que el gestor rechazaría no se crea.

Devuelve 0 y escribe la ruta del paquete; 1 con el motivo si algo falla.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))


def leer_clave_privada(ruta: Path) -> bytes:
	"""32 bytes de la clave privada desde un archivo crudo, en base64 o en hexadecimal."""
	datos = Path(ruta).read_bytes()
	if len(datos) == 32:
		return datos
	texto = datos.decode("ascii", errors="ignore").strip()
	for decodificar in (lambda t: bytes.fromhex(t), lambda t: base64.b64decode(t, validate=True)):
		try:
			clave = decodificar(texto)
		except (ValueError, binascii.Error):
			continue
		if len(clave) == 32:
			return clave
	raise ValueError("El archivo de la clave no tiene una clave privada Ed25519 de 32 bytes (cruda, base64 o hexadecimal)")


def empaquetar(carpeta: Path, salida: Path | None = None, clave_privada: bytes | None = None) -> Path:
	"""Crea el ``.zcplugin`` (firmado si se da la clave) y devuelve su ruta.

	:raises ValueError: con el motivo si el manifiesto no vale o falta ``LICENSE``.
	"""
	from app.plugins import firma, manifiesto, paquetes

	carpeta = Path(carpeta)
	try:
		datos = manifiesto.leer(carpeta)
	except manifiesto.ErrorManifiesto as error:
		raise ValueError("El manifiesto no es válido: " + "; ".join(error.problemas)) from error
	if not (carpeta / "LICENSE").is_file():
		raise ValueError("Falta el archivo LICENSE")
	firma_vieja = carpeta / firma.NOMBRE_FIRMA
	if clave_privada is not None:
		firma.firmar_complemento(carpeta, datos.id, datos.version, clave_privada)
	elif firma_vieja.is_file():
		declarada = firma.declaracion_de(carpeta)
		resultado = firma.verificar_complemento(carpeta, [firma.clave_declarada(carpeta) or ""], comprobar_sumas=True)
		if declarada != (datos.id, datos.version) or not resultado.valida:
			firma_vieja.unlink()
			print("Aviso: se quitó una firma.ed25519 que ya no correspondía a los archivos; el paquete va sin firma.")
	salida = Path(salida) if salida else carpeta.parent / f"{datos.id}-{datos.version}{paquetes.EXTENSION}"
	archivos = [*firma.listar_archivos(carpeta), *([firma.NOMBRE_FIRMA] if (carpeta / firma.NOMBRE_FIRMA).is_file() else [])]
	salida.parent.mkdir(parents=True, exist_ok=True)
	temporal = salida.with_name(salida.name + ".parcial")
	with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
		for relativa in sorted(archivos):
			if relativa.endswith(".pyc"):
				continue
			paquete.write(carpeta / relativa, relativa)
	temporal.replace(salida)
	return salida


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description="Crea el paquete .zcplugin de un complemento de zCommander.")
	analizador.add_argument("carpeta", help="Carpeta del complemento")
	analizador.add_argument("--firmar", metavar="CLAVE", help="Archivo con la clave privada Ed25519 del autor")
	analizador.add_argument("--salida", help="Ruta del paquete (por defecto, <id>-<versión>.zcplugin junto a la carpeta)")
	opciones = analizador.parse_args(argumentos)
	try:
		clave = leer_clave_privada(Path(opciones.firmar)) if opciones.firmar else None
		ruta = empaquetar(Path(opciones.carpeta), Path(opciones.salida) if opciones.salida else None, clave)
	except (OSError, ValueError) as error:
		print(f"Error: {error}")
		return 1
	print(f"Paquete creado{' y firmado' if clave else ''}: {ruta}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
