# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comprueba que cada DLL que necesita la compilación va dentro de ella (o es parte de Windows).

Lee las tablas de los ejecutables de Windows (formato PE) sin dependencias externas: las
DLL que importa cada ``.exe``, ``.dll`` y ``.pyd``, y las DLL a las que reenvía funciones
(las «forwarder» de, por ejemplo, ``python3t.dll``). Una DLL de Python, de los runtimes de
Visual C++ o de OpenSSL tiene que ir en la compilación aunque exista en este equipo: en un
Windows recién instalado no está.

Así se descubrió el fallo de la 2.0.0 y la 2.0.1: ``cryptography`` importa ``python3t.dll``,
y la que copiaba cx_Freeze reenviaba a ``python315t.dll`` (el intérprete sin GIL), que no
va en la compilación. En un equipo con Python en el PATH funcionaba por casualidad.

Uso::

	python tools/dependencias_pe.py [carpeta]      # por defecto build/ZCommander
"""

from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Prefijos de DLL que nunca se pueden tomar del sistema: no vienen con Windows.
DEBEN_IR_DENTRO = ("python", "vcruntime", "msvcp", "concrt", "vcomp", "vccorlib", "vcamp", "libcrypto", "libssl",
	"libffi", "sqlite3", "pywintypes", "pythoncom", "wxbase", "wxmsw")
#: Conjuntos de API de Windows: los resuelve el sistema, no son archivos.
CONJUNTOS_API = ("api-ms-win-", "ext-ms-")
EXTENSIONES_PE = (".exe", ".dll", ".pyd")


@dataclass
class InfoPE:
	importa: list[str] = field(default_factory=list)
	reenvia_a: list[str] = field(default_factory=list)


class ErrorPE(ValueError):
	"""El archivo no es un ejecutable PE válido."""


def leer_pe(ruta: Path) -> InfoPE:
	"""DLL importadas y DLL de destino de los reenvíos de exportaciones de ``ruta``."""
	datos = Path(ruta).read_bytes()
	if datos[:2] != b"MZ" or len(datos) < 0x40:
		raise ErrorPE(f"{ruta}: no es un ejecutable de Windows")
	pe = struct.unpack_from("<I", datos, 0x3C)[0]
	if datos[pe:pe + 4] != b"PE\0\0":
		raise ErrorPE(f"{ruta}: sin cabecera PE")
	secciones_n, = struct.unpack_from("<H", datos, pe + 6)
	tam_opcional, = struct.unpack_from("<H", datos, pe + 20)
	opcional = pe + 24
	magia, = struct.unpack_from("<H", datos, opcional)
	directorios = opcional + (112 if magia == 0x20B else 96)
	numero_dirs, = struct.unpack_from("<I", datos, directorios - 4)
	secciones = []
	inicio = opcional + tam_opcional
	for i in range(secciones_n):
		vtam, vdir, rtam, rpos = struct.unpack_from("<IIII", datos, inicio + i * 40 + 8)
		secciones.append((vdir, max(vtam, rtam), rpos))

	def desplazamiento(rva: int) -> int:
		for vdir, tam, rpos in secciones:
			if vdir <= rva < vdir + tam:
				return rva - vdir + rpos
		raise ErrorPE(f"{ruta}: dirección fuera de las secciones")

	def cadena(rva: int) -> str:
		posicion = desplazamiento(rva)
		fin = datos.index(b"\0", posicion)
		return datos[posicion:fin].decode("ascii", "replace")

	def directorio(indice: int) -> tuple[int, int]:
		if indice >= numero_dirs:
			return 0, 0
		return struct.unpack_from("<II", datos, directorios + indice * 8)

	info = InfoPE()
	rva_imp, _tam = directorio(1)
	if rva_imp:
		posicion = desplazamiento(rva_imp)
		while True:
			descriptor = struct.unpack_from("<IIIII", datos, posicion)
			if not any(descriptor):
				break
			info.importa.append(cadena(descriptor[3]))
			posicion += 20
	rva_exp, tam_exp = directorio(0)
	if rva_exp:
		base = desplazamiento(rva_exp)
		funciones_n, = struct.unpack_from("<I", datos, base + 20)
		rva_funciones, = struct.unpack_from("<I", datos, base + 28)
		tabla = desplazamiento(rva_funciones) if funciones_n else 0
		destinos = set()
		for i in range(funciones_n):
			rva, = struct.unpack_from("<I", datos, tabla + i * 4)
			if rva_exp <= rva < rva_exp + tam_exp:  # dentro del directorio de exportación: es un reenvío
				destino = cadena(rva).split(".", 1)[0]
				destinos.add(destino if destino.lower().endswith(".dll") else destino + ".dll")
		info.reenvia_a = sorted(destinos, key=str.lower)
	return info


def entorno_limpio(base: dict[str, str] | None = None) -> dict[str, str]:
	"""Copia del entorno con un PATH solo de Windows, como en un equipo sin Python instalado.

	Para lanzar ``ZCommander.exe`` en las comprobaciones: con el PATH del desarrollador, una DLL
	que falta en la compilación se toma de su Python y el fallo no se ve.
	"""
	entorno = dict(os.environ if base is None else base)
	raiz_windows = os.path.normcase(entorno.get("SystemRoot", r"C:\Windows"))
	rutas = [r for r in entorno.get("PATH", "").split(os.pathsep) if r and os.path.normcase(r).startswith(raiz_windows)]
	entorno["PATH"] = os.pathsep.join(rutas)
	for variable in ("PYTHONHOME", "PYTHONPATH"):
		entorno.pop(variable, None)
	return entorno


def _sistema() -> Path:
	return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"


def problemas(carpeta: Path, sistema: Path | None = None) -> list[str]:
	"""Las DLL que necesita algo de ``carpeta`` y no se encuentran ni en ella ni en Windows."""
	carpeta = Path(carpeta)
	sistema = sistema or _sistema()
	presentes: dict[Path, set[str]] = {}

	def nombres_en(directorio: Path) -> set[str]:
		if directorio not in presentes:
			presentes[directorio] = {p.name.lower() for p in directorio.iterdir() if p.is_file()} if directorio.is_dir() else set()
		return presentes[directorio]

	encontrados = []
	for archivo in sorted(carpeta.rglob("*")):
		if not archivo.is_file() or archivo.suffix.lower() not in EXTENSIONES_PE:
			continue
		try:
			info = leer_pe(archivo)
		except (ErrorPE, struct.error, ValueError):
			continue  # no es un PE (o uno raro de terceros): no se juzga
		for necesaria in [*info.importa, *info.reenvia_a]:
			nombre = necesaria.lower()
			if nombre.startswith(CONJUNTOS_API):
				continue
			dentro = any(nombre in nombres_en(d) for d in (archivo.parent, carpeta, carpeta / "lib"))
			if dentro:
				continue
			if not nombre.startswith(DEBEN_IR_DENTRO) and (sistema / necesaria).is_file():
				continue
			como = "reenvía a" if necesaria in info.reenvia_a else "necesita"
			encontrados.append(f"{archivo.relative_to(carpeta).as_posix()} {como} {necesaria}, que no va en la compilación")
	return encontrados


def main(argumentos: list[str] | None = None) -> int:
	argumentos = sys.argv[1:] if argumentos is None else argumentos
	carpeta = Path(argumentos[0]) if argumentos else Path(__file__).resolve().parent.parent / "build" / "ZCommander"
	lista = problemas(carpeta)
	for linea in lista:
		print(linea)
	print(f"{len(lista)} dependencias sin resolver." if lista else "Todas las DLL necesarias van en la compilación o son de Windows.")
	return 1 if lista else 0


if __name__ == "__main__":
	sys.exit(main())
