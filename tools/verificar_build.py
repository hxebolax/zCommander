# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comprueba una compilación de zCommander antes de empaquetarla (diseño 2.0, 17.1).

Uso (desde la raíz, con el entorno virtual del proyecto, tras ``python setup_cx.py build``)::

	python tools/verificar_build.py                 # build/ZCommander
	python tools/verificar_build.py --arranque      # además, ZCommander.exe --comprobar-arranque
	python tools/verificar_build.py --carpeta otra/ZCommander

Comprueba:

- El ejecutable y los runtimes de Visual C++ (``include_msvcr``).
- ``data`` solo con las carpetas distribuibles, sin datos personales ni restos
  del actualizador de componentes (las reglas de ``tools/empaquetar.py``).
- ``data/bin/nvda`` con exactamente un ``zCommander-<versión>.nvda-addon`` de la
  versión de la compilación (peticiones de NV).
- Ninguna DLL no libre de accessible_output2 (2.3) y, si va accessible_output2,
  ``nvdaControllerClient64.dll``.
- ``app/plugins/serie_sumas`` congelado en la compilación, con las mismas sumas
  que los archivos de ``plugins/`` (ni de más ni de menos), y sin ``__pycache__``
  ni pruebas en ``plugins/`` (3.2).
- Los recursos de los complementos que no son ``.py`` (``recursos/``,
  ``_table.pywinrt``, ``sonidos/``...) copiados igual que en el repositorio.
- Cada módulo de la biblioteca estándar filtrada (``setup_cx.biblioteca_estandar``)
  se importa desde ``lib/`` de la compilación, en un proceso aparte con el mismo
  CPython y solo las rutas de la compilación en ``sys.path``.

Con ``--arranque`` ejecuta además ``ZCommander.exe --comprobar-arranque`` (con la
``data`` de la compilación, para que encuentre ``data/bin``) y borra después los
registros y temporales que deja.

Devuelve 0 si no hay problemas y 1 si los hay (los enumera).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import marshal
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

from tools import empaquetar  # noqa: E402

COMPILACION = RAIZ / "build" / "ZCommander"
DATA_DISTRIBUIBLE = {"bin", "sounds", "locales", "docs", "icons"}
RUNTIMES_VC = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
DLL_PROHIBIDAS = frozenset(n.lower() for n in (
	"SAAPI32.dll", "dolapi.dll", "PCTKUSR.dll", "PCTKUSR64.dll", "ZDSRAPI.dll", "ZDSRAPI_x64.dll", "nvdaControllerClient32.dll"))
TIEMPO_IMPORTAR_S = 300
TIEMPO_ARRANQUE_S = 180

# Proceso aparte: importa cada módulo con solo las rutas de la compilación en sys.path.
_GUION_IMPORTAR = r"""
import importlib, json, sys
rutas, nombres, nucleo = json.loads(sys.stdin.read())
# Los módulos que cx_Freeze lleva DENTRO de ZCommander.exe (freeze_core, «core» y «frozen») se cargan de este
# mismo CPython antes de cambiar sys.path: en la compilación no hay archivo suyo que importar.
for nombre in nucleo:
	try:
		importlib.import_module(nombre)
	except BaseException:  # noqa: BLE001 - algunos solo existen en otras plataformas
		pass
antes = set(sys.modules)  # lo que ya está cargado no cuenta para el origen
sys.path[:] = rutas
fallos = {}
for nombre in nombres:
	try:
		importlib.import_module(nombre)
	except BaseException as error:  # noqa: BLE001 - se informa de cualquier fallo
		fallos[nombre] = f"{type(error).__name__}: {error}"
origenes = {n: getattr(sys.modules.get(n), "__file__", None) or "" for n in nombres if n in sys.modules and n not in antes}
print(json.dumps({"fallos": fallos, "origenes": origenes}))
"""


def version_app() -> str:
	texto = (RAIZ / "app" / "core" / "version.py").read_text(encoding="utf-8")
	encontrada = re.search(r"APP_VERSION\s*=\s*[\"']([^\"']+)[\"']", texto)
	return encontrada.group(1) if encontrada else "0.0.0"


def _setup_cx():
	"""``setup_cx.py`` como módulo (sin compilar: solo se ejecuta bajo ``__main__``)."""
	import importlib.util

	especificacion = importlib.util.spec_from_file_location("setup_cx_verificar", RAIZ / "setup_cx.py")
	modulo = importlib.util.module_from_spec(especificacion)
	especificacion.loader.exec_module(modulo)
	return modulo


# ── Comprobaciones ───────────────────────────────────────────────────────────


def comprobar_basico(carpeta: Path) -> list[str]:
	problemas = []
	if not (carpeta / "ZCommander.exe").is_file():
		return [f"Falta ZCommander.exe en {carpeta}"]
	problemas += [f"Falta el runtime de Visual C++ {n}" for n in RUNTIMES_VC if not (carpeta / n).is_file()]
	if not (carpeta / "lib").is_dir():
		problemas.append("Falta la carpeta lib/")
	return problemas


def comprobar_data(carpeta: Path) -> list[str]:
	datos = carpeta / "data"
	if not datos.is_dir():
		return ["Falta la carpeta data/"]
	problemas = []
	for entrada in sorted(datos.iterdir()):
		if entrada.is_dir() and entrada.name in empaquetar.PERSONALES:
			problemas.append(f"data/{entrada.name} es de la persona y no debe viajar")
		elif entrada.is_dir() and entrada.name not in DATA_DISTRIBUIBLE:
			problemas.append(f"data/{entrada.name} no es una carpeta distribuible")
	bin_ = datos / "bin"
	for entrada in sorted(bin_.iterdir()) if bin_.is_dir() else []:
		if empaquetar.omitir_de_bin(Path(entrada.name)):
			problemas.append(f"data/bin/{entrada.name} es un resto del actualizador de componentes")
	for ruta in sorted(carpeta.rglob("*")):
		relativa = ruta.relative_to(carpeta)
		if ruta.is_file() and relativa.parts[0] in {"data", "plugins"} and empaquetar.omitir(relativa):
			problemas.append(f"Resto de ejecución en la compilación: {relativa.as_posix()}")
	for nombre in ("manual.md", "teclas.md", "changelog.md", "licencias/LEEME-LICENCIAS.md", "licencias/OFERTA-DE-FUENTES.md",
			"licencias/zCommander/GPL-3.0.txt"):
		if not (datos / "docs" / nombre).is_file():
			problemas.append(f"Falta data/docs/{nombre}")
	for nombre in ("linea_base.json", "componentes.json"):
		if not (bin_ / nombre).is_file():
			problemas.append(f"Falta data/bin/{nombre}")
	return problemas


def comprobar_nvda(carpeta: Path, version: str | None = None) -> list[str]:
	"""Exactamente un ``zCommander-<versión>.nvda-addon`` de la versión de la compilación."""
	version = version or version_app()
	paquetes = sorted((carpeta / "data" / "bin" / "nvda").glob("*.nvda-addon"))
	esperado = f"zCommander-{version}.nvda-addon"
	if [p.name for p in paquetes] != [esperado]:
		return [f"data/bin/nvda debe tener solo {esperado}; tiene: {', '.join(p.name for p in paquetes) or 'nada'}"]
	try:
		with zipfile.ZipFile(paquetes[0]) as paquete:
			manifiesto = paquete.read("manifest.ini").decode("utf-8")
	except (OSError, KeyError, zipfile.BadZipFile) as error:
		return [f"{esperado} no es un complemento de NVDA válido: {error}"]
	if not re.search(rf"^version\s*=\s*\"?{re.escape(version)}\"?\s*$", manifiesto, re.MULTILINE):
		return [f"El manifiesto de {esperado} no tiene la versión {version}"]
	return []


def comprobar_dll(carpeta: Path) -> list[str]:
	problemas = [f"DLL no libre en la compilación (2.3): {r.relative_to(carpeta).as_posix()}"
		for r in sorted(carpeta.rglob("*")) if r.name.lower() in DLL_PROHIBIDAS]
	ao2 = carpeta / "lib" / "accessible_output2"
	if ao2.is_dir() and not any(r.name.lower() == "nvdacontrollerclient64.dll" for r in ao2.rglob("*.dll")):
		problemas.append("accessible_output2 va sin nvdaControllerClient64.dll: la voz con NVDA no funcionaría")
	return problemas


def comprobar_dependencias(carpeta: Path) -> list[str]:
	"""Cada DLL que importan o a la que reenvían los ``.exe``, ``.dll`` y ``.pyd`` va dentro o es de Windows (2.0.2)."""
	from tools import dependencias_pe

	return dependencias_pe.problemas(carpeta)


def leer_sumas_congeladas(carpeta: Path) -> dict[str, dict[str, str]] | None:
	"""``SUMAS`` de ``app/plugins/serie_sumas`` tal como quedó congelado en la compilación (``.pyc`` o ``library.zip``)."""
	codigo = None
	for candidata in (carpeta / "lib" / "app" / "plugins" / "serie_sumas.pyc",):
		if candidata.is_file():
			codigo = candidata.read_bytes()
	if codigo is None:
		for archivo in (carpeta / "lib" / "library.zip",):
			if not archivo.is_file():
				continue
			with zipfile.ZipFile(archivo) as zip_:
				if "app/plugins/serie_sumas.pyc" in zip_.namelist():
					codigo = zip_.read("app/plugins/serie_sumas.pyc")
	if codigo is None:
		return None
	espacio: dict = {}
	exec(marshal.loads(codigo[16:]), espacio)  # noqa: S102 - código propio generado por setup_cx.py, mismo CPython
	return espacio.get("SUMAS")


def sumas_de_plugins(carpeta_plugins: Path) -> dict[str, dict[str, str]]:
	"""Id → ruta relativa → SHA-256 de lo que hay en ``plugins/`` de la compilación."""
	import tomllib

	sumas: dict[str, dict[str, str]] = {}
	for complemento in sorted(p for p in carpeta_plugins.iterdir() if p.is_dir()) if carpeta_plugins.is_dir() else []:
		manifiesto = complemento / "manifiesto.toml"
		if not manifiesto.is_file():
			continue
		with manifiesto.open("rb") as archivo:
			identificador = tomllib.load(archivo)["id"]
		for ruta in sorted(complemento.rglob("*")):
			if ruta.is_file():
				relativa = ruta.relative_to(complemento).as_posix()
				sumas.setdefault(identificador, {})[relativa] = hashlib.sha256(ruta.read_bytes()).hexdigest()
	return sumas


def comprobar_plugins(carpeta: Path, setup=None) -> list[str]:
	plugins = carpeta / "plugins"
	if not plugins.is_dir():
		return ["Falta la carpeta plugins/ (complementos de serie)"]
	problemas = []
	for ruta in sorted(plugins.rglob("*")):
		relativa = ruta.relative_to(carpeta).as_posix()
		if ruta.name == "__pycache__" or ruta.suffix == ".pyc":
			problemas.append(f"{relativa}: no debe haber .pyc ni __pycache__ en plugins/")
		elif ruta.is_file() and ruta.name.startswith("test_") and ruta.suffix == ".py":
			problemas.append(f"{relativa}: las pruebas no viajan")
	congeladas = leer_sumas_congeladas(carpeta)
	reales = sumas_de_plugins(plugins)
	if congeladas is None:
		problemas.append("La compilación no lleva app/plugins/serie_sumas (setup_cx.py debe generarlo antes de congelar)")
	else:
		for identificador in sorted(set(congeladas) | set(reales)):
			esperadas, halladas = congeladas.get(identificador, {}), reales.get(identificador, {})
			for ruta in sorted(set(esperadas) | set(halladas)):
				if ruta not in halladas:
					problemas.append(f"{identificador}: falta {ruta} (está en serie_sumas)")
				elif ruta not in esperadas:
					problemas.append(f"{identificador}: {ruta} no está en serie_sumas")
				elif esperadas[ruta] != halladas[ruta]:
					problemas.append(f"{identificador}: la suma de {ruta} no coincide con serie_sumas")
	setup = setup or _setup_cx()
	for origen, destino in setup.archivos_de_plugins():
		if not (carpeta / destino).is_file():
			problemas.append(f"No se copió {destino}")
		elif Path(origen).suffix != ".py" and Path(origen).read_bytes() != (carpeta / destino).read_bytes():
			problemas.append(f"{destino} no es igual que en el repositorio")
	return problemas


def modulos_del_ejecutable() -> list[str]:
	"""Módulos que el ejecutable base de cx_Freeze (freeze_core) lleva dentro: no están en ``lib/``."""
	import importlib.util

	especificacion = importlib.util.find_spec("freeze_core")
	if especificacion is None or not especificacion.submodule_search_locations:
		return []
	etiqueta = f"cp{sys.version_info.major}{sys.version_info.minor}-win_amd64"
	ruta = Path(next(iter(especificacion.submodule_search_locations))) / "frozen" / f"frozen-{etiqueta}.json"
	try:
		datos = json.loads(ruta.read_text(encoding="utf-8"))
	except (OSError, ValueError):
		return []
	return sorted(n for n, tipo in datos.items() if tipo in {"core", "frozen"} and not n.startswith("__"))


def comprobar_biblioteca_estandar(carpeta: Path, setup=None) -> list[str]:
	"""Cada módulo de la lista filtrada se importa desde ``lib/`` de la compilación (17.1)."""
	setup = setup or _setup_cx()
	lib = carpeta / "lib"
	rutas = [str(lib), str(lib / "library.zip")]
	nombres = setup.biblioteca_estandar()
	entorno = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
	try:
		resultado = subprocess.run(  # noqa: S603 - el mismo intérprete con un guion propio
			[sys.executable, "-I", "-S", "-c", _GUION_IMPORTAR], input=json.dumps([rutas, nombres, modulos_del_ejecutable()]), capture_output=True,
			text=True, encoding="utf-8", errors="replace", timeout=TIEMPO_IMPORTAR_S, cwd=str(lib), env=entorno, check=False)
	except subprocess.TimeoutExpired:
		return [f"Importar la biblioteca estándar tardó más de {TIEMPO_IMPORTAR_S} s"]
	try:
		datos = json.loads(resultado.stdout.strip().splitlines()[-1])
	except (IndexError, ValueError):
		return [f"No se pudo importar la biblioteca estándar de la compilación: {resultado.stderr.strip()[-2000:]}"]
	problemas = [f"No se importa {nombre} desde la compilación: {error}" for nombre, error in sorted(datos["fallos"].items())]
	base = Path(sys.base_prefix).resolve()
	for nombre, origen in sorted(datos["origenes"].items()):
		if origen and Path(origen).resolve().is_relative_to(base):
			problemas.append(f"{nombre} se cargó de {origen}, fuera de la compilación")
	return problemas


def comprobar_arranque(carpeta: Path) -> list[str]:
	"""``ZCommander.exe --comprobar-arranque`` con la ``data`` de la compilación (así encuentra ``data/bin``).

	La comprobación deja registros y temporales en ``data``: si falla, se muestra el final
	del registro; después se borran las carpetas personales que no existían antes, para
	que la compilación siga lista para empaquetar.
	"""
	datos = carpeta / "data"
	previas = {p.name for p in datos.iterdir()} if datos.is_dir() else set()
	from tools.dependencias_pe import entorno_limpio

	# PATH sin Python, como en el equipo de quien lo descarga: así se nota una DLL que falte.
	entorno = {k: v for k, v in entorno_limpio().items() if k != "APP_DATA_DIR"}
	problemas = []
	try:
		resultado = subprocess.run([str(carpeta / "ZCommander.exe"), "--comprobar-arranque"], env=entorno,  # noqa: S603
			timeout=TIEMPO_ARRANQUE_S, check=False)
		if resultado.returncode != 0:
			registros = sorted((datos / "logs").glob("*.log"))
			cola = registros[-1].read_text(encoding="utf-8", errors="replace")[-3000:] if registros else ""
			problemas.append(f"ZCommander.exe --comprobar-arranque devolvió {resultado.returncode}\n{cola}")
	except subprocess.TimeoutExpired:
		problemas.append(f"ZCommander.exe --comprobar-arranque tardó más de {TIEMPO_ARRANQUE_S} s")
	finally:
		for nombre in sorted(empaquetar.PERSONALES - previas):
			shutil.rmtree(datos / nombre, ignore_errors=True)
	return problemas


def verificar(carpeta: Path = COMPILACION, *, arranque: bool = False, biblioteca: bool = True) -> list[str]:
	problemas = comprobar_basico(carpeta)
	if problemas:
		return problemas
	setup = _setup_cx()
	problemas += comprobar_data(carpeta)
	problemas += comprobar_nvda(carpeta)
	problemas += comprobar_dll(carpeta)
	problemas += comprobar_dependencias(carpeta)
	problemas += comprobar_plugins(carpeta, setup)
	if biblioteca:
		problemas += comprobar_biblioteca_estandar(carpeta, setup)
	if arranque:
		problemas += comprobar_arranque(carpeta)
	return problemas


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--carpeta", type=Path, default=COMPILACION, help="Carpeta de la compilación.")
	analizador.add_argument("--arranque", action="store_true", help="Ejecutar también ZCommander.exe --comprobar-arranque.")
	analizador.add_argument("--sin-biblioteca", action="store_true", help="No importar la biblioteca estándar (más rápido).")
	opciones = analizador.parse_args(argumentos)
	for flujo in (sys.stdout, sys.stderr):
		if hasattr(flujo, "reconfigure"):
			flujo.reconfigure(errors="replace")
	problemas = verificar(opciones.carpeta.resolve(), arranque=opciones.arranque, biblioteca=not opciones.sin_biblioteca)
	for problema in problemas:
		print(problema)
	if problemas:
		print(f"{len(problemas)} problemas en la compilación.")
		return 1
	print(f"Compilación correcta: {opciones.carpeta}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
