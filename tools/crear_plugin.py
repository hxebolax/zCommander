# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Crea un complemento nuevo a partir de ``tools/plantilla_plugin/`` (diseño 2.0, 3.12).

Uso::

	python tools/crear_plugin.py <carpeta> --id ana.ejemplo --nombre "Ejemplo" [--autor "Ana"] [--descripcion "..."]

Genera el manifiesto (con una orden, una página de Preferencias con una clave
y un sonido), el código, la ayuda y las novedades, ``LICENSE`` (GPL-3.0), el
sonido ``sonidos/saludo.wav`` y una prueba con ``api.pruebas``. Después:
``python tools/validar_plugin.py <carpeta>`` y ``python tools/empaquetar_plugin.py <carpeta>``.

Devuelve 0 si todo fue bien; 1 con un mensaje si el id no vale o la carpeta ya tiene archivos.
"""

from __future__ import annotations

import argparse
import math
import shutil
import struct
import sys
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLA = Path(__file__).resolve().parent / "plantilla_plugin"
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))


def _sustituir(texto: str, valores: dict[str, str]) -> str:
	for clave, valor in valores.items():
		texto = texto.replace("{{" + clave + "}}", valor)
	return texto


def _toml(texto: str) -> str:
	"""Texto seguro dentro de una cadena TOML básica."""
	return texto.replace("\\", "\\\\").replace('"', '\\"')


def escribir_sonido(ruta: Path, frecuencia: float = 880.0, duracion_s: float = 0.12) -> None:
	"""Un pitido corto (WAV PCM de 16 bits, 44,1 kHz, mono) para el sonido de la plantilla."""
	muestras = int(44100 * duracion_s)
	ruta.parent.mkdir(parents=True, exist_ok=True)
	with wave.open(str(ruta), "wb") as salida:
		salida.setnchannels(1)
		salida.setsampwidth(2)
		salida.setframerate(44100)
		datos = bytearray()
		for i in range(muestras):
			envolvente = min(1.0, i / 400, (muestras - i) / 400)
			datos += struct.pack("<h", int(9000 * envolvente * math.sin(2 * math.pi * frecuencia * i / 44100)))
		salida.writeframes(bytes(datos))


def crear(carpeta: Path, id_complemento: str, nombre: str, autor: str = "", descripcion: str = "") -> list[str]:
	"""Crea el complemento; devuelve los problemas (vacía si se creó)."""
	from app.plugins import manifiesto

	if not manifiesto.ID_VALIDO.match(id_complemento):
		return [f"El id «{id_complemento}» no es válido: minúsculas y cifras separadas por puntos, como ana.utilidades"]
	if id_complemento.startswith("zc."):
		return ["Los id zc.* están reservados a los complementos oficiales de zCommander"]
	carpeta = Path(carpeta)
	if carpeta.exists() and any(carpeta.iterdir()):
		return [f"La carpeta {carpeta} ya tiene archivos: elija una vacía o nueva"]
	valores = {
		"id": _toml(id_complemento), "nombre": _toml(nombre), "autor": _toml(autor or "Autor del complemento"),
		"descripcion": _toml(descripcion or f"Complemento {nombre} para zCommander."),
	}
	for origen in sorted(PLANTILLA.rglob("*")):
		if origen.is_dir() or "__pycache__" in origen.parts:
			continue
		destino = carpeta / origen.relative_to(PLANTILLA)
		destino.parent.mkdir(parents=True, exist_ok=True)
		destino.write_text(_sustituir(origen.read_text(encoding="utf-8"), valores), encoding="utf-8", newline="\n")
	licencia = RAIZ / "LICENSE"
	if licencia.is_file():
		shutil.copyfile(licencia, carpeta / "LICENSE")
	else:
		(carpeta / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE, Version 3: https://www.gnu.org/licenses/gpl-3.0.txt\n",
			encoding="utf-8")
	escribir_sonido(carpeta / "sonidos" / "saludo.wav")
	return []


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description="Crea un complemento de zCommander a partir de la plantilla.")
	analizador.add_argument("carpeta", help="Carpeta nueva (o vacía) del complemento")
	analizador.add_argument("--id", required=True, help="Id del complemento, como ana.ejemplo")
	analizador.add_argument("--nombre", required=True, help="Nombre visible en español")
	analizador.add_argument("--autor", default="", help="Autor")
	analizador.add_argument("--descripcion", default="", help="Descripción de una frase")
	opciones = analizador.parse_args(argumentos)
	problemas = crear(Path(opciones.carpeta), opciones.id, opciones.nombre, opciones.autor, opciones.descripcion)
	if problemas:
		for problema in problemas:
			print(f"Error: {problema}")
		return 1
	print(f"Complemento {opciones.id} creado en {opciones.carpeta}.")
	print(f"Siguiente paso: python tools/validar_plugin.py {opciones.carpeta}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
