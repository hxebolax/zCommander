# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comprueba que todo lo que distribuye zCommander tiene su licencia (diseño 2.0, 2.1 a 2.3 y 17.2).

Uso (desde la raíz, con el entorno virtual del proyecto)::

	python tools/comprobar_licencias.py                     # el repositorio
	python tools/comprobar_licencias.py build\\ZCommander    # además, una compilación

Devuelve 0 si no hay problemas y 1 si los hay (los enumera). ``tools/publicar.py``
lo llama con la carpeta de la compilación.

En el repositorio comprueba:

- ``data/docs/licencias`` al día con ``tools/generar_licencias.py`` (cada texto
  existe y coincide con su origen).
- ``LEEME-LICENCIAS.md`` nombra cada componente de ``data/bin/linea_base.json``
  y cada paquete de ``requirements.txt``, y cada uno tiene su componente en la tabla.
- Cada componente de la línea base tiene en ``data/bin`` los archivos de licencia
  que declara; cada paquete de sonidos, su ``LICENCIA.txt``; cada complemento de
  serie, su ``LICENSE``, y cada biblioteca de su ``lib/``, su componente.
- Cada archivo propio (``.py``, ``.bat``, ``.ps1`` y ``manifiesto.toml``) empieza
  con la cabecera SPDX y el titular (2.1).

En una compilación comprueba, además:

- Que no viaja ninguna DLL no libre de accessible_output2 (2.3).
- Que cada archivo o carpeta de la raíz y de ``lib/`` pertenece a un componente
  conocido (zCommander, la biblioteca estándar de Python o un paquete de la tabla).
- Que lleva ``data/docs/licencias`` completo y las licencias de ``data/bin``, de
  los complementos y de los sonidos.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

from tools import generar_licencias as gl  # noqa: E402

#: DLL no libres de accessible_output2 y la de 32 bits (2.3); nunca en una compilación.
DLL_PROHIBIDAS = frozenset(n.lower() for n in (
	"SAAPI32.dll", "dolapi.dll", "PCTKUSR.dll", "PCTKUSR64.dll", "ZDSRAPI.dll", "ZDSRAPI_x64.dll", "nvdaControllerClient32.dll"))

CABECERA_SPDX = "SPDX-License-Identifier: GPL-3.0-or-later"
CABECERA_TITULAR = "Copyright (C) 2026 hxebolax y colaboradores"
#: Extensiones de los archivos propios que llevan cabecera (2.1); ``manifiesto.toml`` va aparte.
EXTENSIONES_PROPIAS = {".py", ".bat", ".ps1"}
#: Carpetas que no son código propio de zCommander o no se revisan.
CARPETAS_AJENAS = {".venv", "venv", "build", "dist", "adjuntos", "data", "__pycache__", ".pytest_cache", ".ruff_cache", ".git",
	"src", "lib"}
#: Archivos propios sin cabecera permitidos, con el motivo. Cada uno es una tarea pendiente de su dueño.
SIN_CABECERA_PERMITIDOS = {
}
#: La plantilla de complementos es para terceros: su autor pone su propia licencia y titular.
CARPETAS_PLANTILLA = ("tools/plantilla_plugin/",)

#: Lo que puede haber en la raíz de la compilación además de lo que se asigna por módulos.
RAIZ_COMPILACION = {"zcommander.exe": "zCommander", "lib": "", "data": "", "plugins": "", "share": "cx_Freeze",
	"frozen_application_license.txt": "cx_Freeze", "python3.dll": "Python", "python3t.dll": "Python"}
#: Lo que ``setup_cx.py`` excluye a propósito (sin licencia en ``data/docs/licencias``): si aparece, es un error.
NO_DISTRIBUIDOS_LIB = frozenset({"pythonwin", "pywin", "win32ui", "win32uiole", "scintilla", "isapi", "pyisapi_loader", "adodbapi",
	"numpy", "pygments", "tkinter", "_tkinter", "tcl", "tk"})
#: Archivos de ``plugins/<carpeta>/lib`` que no son bibliotecas (avisos y configuración).
NO_BIBLIOTECAS = re.compile(r"^(LICEN[CS]IA?.*|LEEME.*|README.*|ruff\.toml|\.ruff_cache|__pycache__)$", re.IGNORECASE)


# ── Utilidades ───────────────────────────────────────────────────────────────


def _normalizar_paquete(nombre: str) -> str:
	return re.sub(r"[-_.]+", "-", nombre).lower()


def paquetes_requeridos(raiz: Path = RAIZ) -> list[str]:
	"""Nombres de los paquetes de ``requirements.txt`` (sin versión ni comentarios)."""
	nombres = []
	for linea in (raiz / "requirements.txt").read_text(encoding="utf-8").splitlines():
		linea = linea.split("#", 1)[0].strip()
		if not linea or linea.startswith("-"):
			continue
		nombres.append(re.split(r"[<>=!~;\[ ]", linea, maxsplit=1)[0])
	return nombres


def linea_base(raiz: Path = RAIZ) -> list[dict]:
	return json.loads((raiz / "data" / "bin" / "linea_base.json").read_text(encoding="utf-8")).get("componentes", [])


def _componente_por_paquete() -> dict[str, gl.Componente]:
	return {_normalizar_paquete(p): c for c in gl.COMPONENTES for p in c.pypi}


def _nombre_modulo(nombre: str) -> str:
	"""``win32api.pyd`` → ``win32api``; ``_cffi_backend.cp315-win_amd64.pyd`` → ``_cffi_backend``."""
	base = nombre
	for sufijo in (".pyd", ".dll", ".pyc", ".py", ".pyi"):
		if base.lower().endswith(sufijo):
			base = base[: -len(sufijo)]
			break
	return base.split(".", 1)[0]


# ── Repositorio ──────────────────────────────────────────────────────────────


def _es_propio(relativa: Path) -> bool:
	if any(parte in CARPETAS_AJENAS for parte in relativa.parts[:-1]):
		return False
	texto = relativa.as_posix()
	if any(texto.startswith(prefijo) for prefijo in CARPETAS_PLANTILLA):
		return False
	if relativa.name == "manifiesto.toml":
		return True
	return relativa.suffix.lower() in EXTENSIONES_PROPIAS


def archivos_propios(raiz: Path = RAIZ) -> list[Path]:
	"""Archivos de código propio de zCommander (rutas relativas a la raíz)."""
	resultado = []
	for ruta in raiz.rglob("*"):
		if not ruta.is_file():
			continue
		relativa = ruta.relative_to(raiz)
		if relativa.parts[0] in CARPETAS_AJENAS:
			continue
		if _es_propio(relativa):
			resultado.append(relativa)
	return sorted(resultado)


def tiene_cabecera(ruta: Path) -> bool:
	"""Las dos líneas de 2.1 en las cinco primeras (detrás puede ir ``@echo off`` o la codificación)."""
	try:
		with ruta.open(encoding="utf-8-sig", errors="replace") as archivo:
			inicio = "".join(archivo.readline() for _ in range(5))
	except OSError:
		return False
	return CABECERA_SPDX in inicio and CABECERA_TITULAR in inicio


def archivos_sin_cabecera(raiz: Path = RAIZ) -> list[str]:
	return [r.as_posix() for r in archivos_propios(raiz)
		if r.as_posix() not in SIN_CABECERA_PERMITIDOS and not tiene_cabecera(raiz / r)]


def problemas_leeme(raiz: Path = RAIZ) -> list[str]:
	"""``LEEME-LICENCIAS.md`` nombra cada componente de la línea base y cada paquete de ``requirements.txt``."""
	ruta = raiz / "data" / "docs" / "licencias" / gl.LEEME
	if not ruta.is_file():
		return [f"Falta {ruta.relative_to(raiz).as_posix()}"]
	texto = ruta.read_text(encoding="utf-8")
	minusculas = texto.lower()
	problemas = []
	por_paquete = _componente_por_paquete()
	for paquete in paquetes_requeridos(raiz):
		if _normalizar_paquete(paquete) not in por_paquete:
			problemas.append(f"El paquete «{paquete}» de requirements.txt no tiene componente en tools/generar_licencias.py")
		if f"`{paquete.lower()}`" not in minusculas:
			problemas.append(f"LEEME-LICENCIAS.md no nombra el paquete «{paquete}» de requirements.txt")
	ids = {i for c in gl.COMPONENTES for i in c.ids}
	for ficha in linea_base(raiz):
		identificador = ficha.get("id", "")
		if identificador not in ids:
			problemas.append(f"El componente «{identificador}» de linea_base.json no tiene componente en tools/generar_licencias.py")
		if f"`{identificador}`" not in texto:
			problemas.append(f"LEEME-LICENCIAS.md no nombra el componente «{identificador}» de linea_base.json")
	return problemas


def _licencias_de_bin(carpeta_bin: Path, raiz: Path = RAIZ) -> list[str]:
	problemas = []
	for ficha in linea_base(raiz):
		carpeta = carpeta_bin / ficha.get("carpeta", ficha.get("id", ""))
		if not ficha.get("archivos") and not carpeta.is_dir():
			continue  # opcional o generado (nvda): sin archivos fijos
		if not ficha.get("licencia"):
			problemas.append(f"El componente «{ficha.get('id')}» de linea_base.json no declara «licencia»")
		for nombre in ficha.get("licencias", []):
			if not (carpeta / nombre).is_file():
				problemas.append(f"Falta la licencia {nombre} de «{ficha.get('id')}» en {carpeta}")
	return problemas


def _modulos_complementos() -> set[str]:
	return {m for c in gl.COMPONENTES if c.grupo == "complementos" for m in c.modulos}


def _licencias_de_complementos(carpeta_plugins: Path) -> list[str]:
	problemas = []
	conocidos = _modulos_complementos()
	for carpeta in sorted(p for p in carpeta_plugins.iterdir() if p.is_dir() and p.name != "__pycache__") \
			if carpeta_plugins.is_dir() else []:
		if not (carpeta / "manifiesto.toml").is_file():
			continue
		if not (carpeta / "LICENSE").is_file():
			problemas.append(f"El complemento {carpeta.name} no tiene LICENSE")
		lib = carpeta / "lib"
		for entrada in sorted(lib.iterdir()) if lib.is_dir() else []:
			if NO_BIBLIOTECAS.match(entrada.name):
				continue
			if _nombre_modulo(entrada.name) not in conocidos:
				problemas.append(f"La biblioteca {carpeta.name}/lib/{entrada.name} no tiene componente en tools/generar_licencias.py")
	return problemas


def _licencias_de_sonidos(carpeta_sonidos: Path) -> list[str]:
	if not carpeta_sonidos.is_dir():
		return [f"No existe la carpeta de sonidos {carpeta_sonidos}"]
	return [f"El paquete de sonidos {p.name} no tiene LICENCIA.txt"
		for p in sorted(carpeta_sonidos.iterdir()) if p.is_dir() and not (p / "LICENCIA.txt").is_file()]


def problemas_repositorio(raiz: Path = RAIZ) -> list[str]:
	problemas = [f"data/docs/licencias: {p}" for p in gl.desfasados(raiz / "data" / "docs" / "licencias")]
	problemas += problemas_leeme(raiz)
	problemas += _licencias_de_bin(raiz / "data" / "bin", raiz)
	problemas += _licencias_de_complementos(raiz / "plugins")
	problemas += _licencias_de_sonidos(raiz / "data" / "sounds")
	problemas += [f"Sin la cabecera SPDX y el titular (2.1): {r}" for r in archivos_sin_cabecera(raiz)]
	return problemas


# ── Compilación ──────────────────────────────────────────────────────────────


def dll_prohibidas(carpeta: Path) -> list[str]:
	"""DLL no libres de accessible_output2 (o la de 32 bits) que hay en ``carpeta``."""
	return sorted(r.relative_to(carpeta).as_posix() for r in carpeta.rglob("*") if r.name.lower() in DLL_PROHIBIDAS)


def _indice_distribuciones() -> dict[str, str]:
	"""Nombre de módulo o archivo nativo → distribución que lo instala (por su RECORD)."""
	indice: dict[str, str] = {}
	for distribucion in importlib.metadata.distributions():
		nombre = distribucion.metadata["Name"] or ""
		for archivo in distribucion.files or []:
			partes = archivo.parts
			if not partes or partes[0].endswith((".dist-info", ".data")) or partes[0] == "..":
				continue
			indice.setdefault(_nombre_modulo(partes[0]), nombre)
			if archivo.suffix.lower() in {".pyd", ".dll"}:
				indice.setdefault(_nombre_modulo(partes[-1]), nombre)
	return indice


def _es_de_python(nombre: str) -> bool:
	modulo = _nombre_modulo(nombre)
	if modulo in sys.stdlib_module_names:
		return True
	base = Path(sys.base_prefix)
	return (base / "DLLs" / nombre).exists() or (base / "Lib" / nombre).exists() or (base / nombre).exists()


def dueno_de(nombre: str, indice: dict[str, str] | None = None) -> str | None:
	"""Componente al que pertenece un archivo o carpeta de ``lib/`` o de la raíz de la compilación."""
	modulo = _nombre_modulo(nombre)
	for componente in gl.COMPONENTES:
		if nombre in componente.modulos or modulo in componente.modulos:
			return componente.carpeta
	if _es_de_python(nombre):
		return "Python"
	indice = _indice_distribuciones() if indice is None else indice
	distribucion = indice.get(modulo)
	if distribucion:
		componente = _componente_por_paquete().get(_normalizar_paquete(distribucion))
		if componente is not None:
			return componente.carpeta
	return None


def problemas_compilacion(carpeta: Path, raiz: Path = RAIZ) -> list[str]:
	if not (carpeta / "ZCommander.exe").is_file():
		return [f"No hay compilación en {carpeta} (falta ZCommander.exe)"]
	problemas = [f"DLL no libre en la compilación (2.3): {d}" for d in dll_prohibidas(carpeta)]
	indice = _indice_distribuciones()
	for entrada in sorted(carpeta.iterdir()):
		if entrada.name.lower() in RAIZ_COMPILACION:
			continue
		if dueno_de(entrada.name, indice) is None:
			problemas.append(f"No se sabe de qué componente es {entrada.name} (raíz de la compilación)")
	lib = carpeta / "lib"
	for entrada in sorted(lib.iterdir()) if lib.is_dir() else []:
		if _nombre_modulo(entrada.name).lower() in NO_DISTRIBUIDOS_LIB:
			problemas.append(f"lib/{entrada.name} no debe distribuirse (está excluido en setup_cx.py y no tiene licencia aquí)")
		elif dueno_de(entrada.name, indice) is None:
			problemas.append(f"No se sabe de qué componente es lib/{entrada.name}: añádalo a tools/generar_licencias.py o exclúyalo")
	licencias = carpeta / "data" / "docs" / "licencias"
	for relativa in gl.contenidos():
		if not (licencias / relativa).is_file():
			problemas.append(f"Falta en la compilación data/docs/licencias/{relativa}")
	problemas += _licencias_de_bin(carpeta / "data" / "bin", raiz)
	problemas += _licencias_de_complementos(carpeta / "plugins")
	problemas += _licencias_de_sonidos(carpeta / "data" / "sounds")
	if not (carpeta / "plugins").is_dir():
		problemas.append("La compilación no lleva la carpeta plugins/")
	return problemas


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("compilacion", nargs="?", type=Path, help="Carpeta de la compilación (build\\ZCommander).")
	opciones = analizador.parse_args(argumentos)
	for flujo in (sys.stdout, sys.stderr):
		if hasattr(flujo, "reconfigure"):
			flujo.reconfigure(errors="replace")
	problemas = problemas_repositorio()
	if opciones.compilacion is not None:
		problemas += problemas_compilacion(opciones.compilacion.resolve())
	for problema in problemas:
		print(problema)
	if problemas:
		print(f"{len(problemas)} problemas de licencias.")
		return 1
	print("Licencias comprobadas: sin problemas.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
