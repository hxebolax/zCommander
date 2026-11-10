# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Compilación con cx_Freeze: ``python setup_cx.py build`` (``--debug`` = con consola).

Genera ``build/ZCommander`` con:

- El ejecutable sin consola (``base="gui"``).
- Los runtimes de Visual C++ (``include_msvcr``), para que arranque en un
  Windows recién instalado sin el redistribuible.
- Una carpeta ``data`` LIMPIA por lista blanca: solo lo que hace falta para
  arrancar. Nunca configuración, registros ni nada generado al probar.

2.0 (diseño 2.0, 17):

- **Antes de congelar** (17.2): comprueba que ``data/bin`` coincide con
  ``linea_base.json`` (``tools/preparar_componentes.py --comprobar``), genera el
  complemento de NVDA de esta versión (``tools/construir_complemento.py``) y
  comprueba las licencias del repositorio (``tools/comprobar_licencias.py``).
  ``--sin-comprobaciones`` salta las comprobaciones (no la generación).
- **Biblioteca estándar completa** para los complementos (contrato de 3.7): los
  módulos de ``sys.stdlib_module_names`` que existen en el CPython de Windows de
  la máquina que compila, salvo la lista negra (``LISTA_NEGRA``). Sin ese filtro
  cx_Freeze se detiene con «No module named …».
- **Complementos de serie**: ``plugins/`` (raíz del repositorio) se copia a
  ``build/ZCommander/plugins/`` como fuente, con sus recursos (``recursos/``,
  ``sonidos/``, los ``_table.pywinrt`` de pywinrt, ``ocr.ps1``...); antes de
  congelar se escribe ``app/plugins/serie_sumas.py`` con el SHA-256 de cada
  archivo copiado (3.2) y se borra del código fuente al terminar.
- ``data/plugins``, ``data/sounds_usuario`` y ``data/plantillas`` son de la
  persona y nunca viajan; de ``data/bin`` se excluyen los restos del
  actualizador de componentes (las reglas de ``tools/empaquetar.py``).
- Tras compilar se borran las DLL no libres de accessible_output2 (2.3) y se
  comprueban las licencias de la compilación (``tools/comprobar_licencias.py``).
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

from cx_Freeze import Executable, setup

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

# ── CONFIGURACIÓN DEL PROYECTO ───────────────────────────────────────────────

NOMBRE_APP = "ZCommander"
EJECUTABLE = "ZCommander.exe"
DESCRIPCION = "Gestor de archivos accesible de doble panel"
ICONO = RAIZ / "data" / "icons" / "app.ico"

# Subcarpetas de data/ que SÍ se distribuyen (lista blanca).
DATA_DISTRIBUIBLE = ["bin", "sounds", "locales", "docs", "icons"]
# Subcarpetas que JAMÁS pueden distribuirse: si alguien las añade arriba, se para.
DATA_PROHIBIDO = {"config", "logs", "db", "cache", "temp", "sessions", "backups", "downloads", "plugins", "sounds_usuario",
	"plantillas"}
# Archivos que nunca se copian aunque estén en una carpeta distribuible.
PATRONES_EXCLUIDOS = ("__pycache__", "*.pyc", "*.log", "*.tmp", "*.bak", "*.db", "*.key", ".gitkeep", "desktop.ini", "Thumbs.db",
	"tests", "test_*.py", ".ruff_cache", ".pytest_cache", "ruff.toml", "*.parcial")

# Los proveedores de C y D se importan con importlib (registro_proveedores.py),
# así que cx_Freeze no los ve solo: se nombran aquí con sus dependencias.
# Obligatorios: si falta alguno en el entorno, la compilación se detiene.
PAQUETES = [
	"wx", "app", "send2trash", "win32com", "win32api", "pywintypes", "markdown", "comtypes",
	# 2.0 (17.1): cryptography pasa a ser obligatorio (firma de actualizaciones, copias, cifrado).
	"cryptography", "libloader", "platform_utils",
	# platform_utils.paths (que importa accessible_output2) necesita platformdirs.
	"platformdirs",
	# SFTP y 7z: py7zr también lo usa el actualizador de componentes para abrir el .7z de 7za (6.6).
	"paramiko", "bcrypt", "nacl", "py7zr",
	"wx.media", "wx.html2", "win32com.shell", "win32com.propsys", "win32cred", "win32job", "win32net", "win32wnet",
	"winreg", "ctypes.wintypes", "sqlite3", "tomllib", "compression",
]
# Opcionales: sin ellos la aplicación funciona (voz directa: sin accessible_output2 habla por UIA).
PAQUETES_OPCIONALES = ["accessible_output2"]
# Manifiesto: rutas largas (más de 260 caracteres) y DPI por monitor.
MANIFIESTO = RAIZ / "tools" / "zcommander.manifest"
# Herramientas de desarrollo, dependencias opcionales que arrastraría wx.lib (NumPy, Pygments) y partes de
# pywin32 que no se usan ni se distribuyen (Pythonwin y Scintilla, isapi, adodbapi): sin ellas no hay licencias de más.
EXCLUDES = ["tkinter", "pydoc_data", "pip", "pytest", "_pytest", "ruff", "cx_Freeze", "freeze_core", "setuptools",
	"_distutils_hack", "pkg_resources", "pyftpdlib", "asynchat", "asyncore", "numpy", "pygments", "lief",
	"cabarchive", "striprtf", "colorama", "filelock", "packaging", "iniconfig", "pluggy", "msilib", "pythonwin", "pywin",
	"win32ui", "win32uiole", "isapi", "adodbapi"]
# Módulos de la biblioteca estándar que no se incluyen (efectos al importarse o solo POSIX).
LISTA_NEGRA = frozenset({
	"tkinter", "turtle", "turtledemo", "idlelib", "test", "ensurepip", "venv", "lib2to3", "pydoc_data", "antigravity", "this",
	"curses", "posix", "pwd", "grp", "fcntl", "termios", "tty", "pty", "resource", "syslog", "readline", "_posixsubprocess",
})
# DLL no libres de accessible_output2 (2.3) y la de 32 bits (la compilación es de 64).
DLL_NO_LIBRES = ("SAAPI32.dll", "dolapi.dll", "PCTKUSR.dll", "PCTKUSR64.dll", "ZDSRAPI.dll", "ZDSRAPI_x64.dll",
	"nvdaControllerClient32.dll")
SUMAS_SERIE = RAIZ / "app" / "plugins" / "serie_sumas.py"
# Lo que el gancho de pywin32 de cx_Freeze copia aunque no se use (Pythonwin con Scintilla, isapi): se borra al terminar.
# lib/win32com/axdebug: depurador de Active Scripting de pywin32; no se usa y su axdebug.pyd necesita una
# axscript.pyd de otra carpeta (2.0.2, tools/dependencias_pe.py).
NO_DISTRIBUIR = ("lib/pythonwin", "lib/isapi", "lib/PyISAPI_loader.dll", "lib/scintilla.dll", "lib/win32com/axdebug")

# ─────────────────────────────────────────────────────────────────────────────

DESTINO = RAIZ / "build" / NOMBRE_APP


class ErrorCompilacion(SystemExit):
	"""Una comprobación previa falla: la compilación no empieza."""


def leer_version() -> str:
	"""Lee APP_VERSION con una expresión regular: importar la app arrastraría wx."""
	texto = (RAIZ / "app" / "core" / "version.py").read_text(encoding="utf-8")
	coincidencia = re.search(r"APP_VERSION\s*=\s*[\"']([^\"']+)[\"']", texto)
	return coincidencia.group(1) if coincidencia else "0.0.0"


def _excluido(ruta: Path) -> bool:
	return any(Path(parte).match(patron) for parte in ruta.parts for patron in PATRONES_EXCLUIDOS)


def archivos_de_data() -> list[tuple[str, str]]:
	"""Pares (origen, destino relativo) de data/ archivo a archivo, filtrando lo excluido."""
	from tools.empaquetar import omitir_de_bin

	prohibidas = DATA_PROHIBIDO.intersection(DATA_DISTRIBUIBLE)
	if prohibidas:
		raise SystemExit("ERROR: DATA_DISTRIBUIBLE incluye carpetas personales: " + ", ".join(sorted(prohibidas)))
	resultado = []
	for nombre in DATA_DISTRIBUIBLE:
		carpeta = RAIZ / "data" / nombre
		for archivo in sorted(carpeta.rglob("*")) if carpeta.is_dir() else []:
			relativo = archivo.relative_to(RAIZ)
			if nombre == "bin" and omitir_de_bin(Path(*relativo.parts[2:])):
				continue
			if archivo.is_file() and not _excluido(relativo):
				resultado.append((str(archivo), relativo.as_posix()))
	return resultado


def archivos_de_plugins() -> list[tuple[str, str]]:
	"""Los complementos de serie (``plugins/`` de la raíz), como fuente y sin pruebas ni ``__pycache__``."""
	carpeta = RAIZ / "plugins"
	resultado = []
	for archivo in sorted(carpeta.rglob("*")) if carpeta.is_dir() else []:
		relativo = archivo.relative_to(RAIZ)
		if archivo.is_file() and not _excluido(relativo):
			resultado.append((str(archivo), relativo.as_posix()))
	return resultado


def sumas_serie() -> dict[str, dict[str, str]]:
	"""Id del complemento → ruta relativa → SHA-256 de cada archivo que se copia a ``plugins/`` (3.2, 3.9)."""
	import tomllib

	sumas: dict[str, dict[str, str]] = {}
	ids: dict[str, str] = {}
	for origen, destino in archivos_de_plugins():
		partes = Path(destino).parts  # plugins/<carpeta>/<resto>
		if len(partes) < 3:
			continue  # un archivo suelto en plugins/ no es un complemento
		carpeta = partes[1]
		if carpeta not in ids:
			with (RAIZ / "plugins" / carpeta / "manifiesto.toml").open("rb") as archivo:
				ids[carpeta] = tomllib.load(archivo)["id"]
		relativa = Path(*partes[2:]).as_posix()
		sumas.setdefault(ids[carpeta], {})[relativa] = hashlib.sha256(Path(origen).read_bytes()).hexdigest()
	return sumas


def escribir_sumas_serie() -> None:
	"""``app/plugins/serie_sumas.py``: id del complemento → ruta relativa → SHA-256 (3.2, 3.9)."""
	lineas = ["# SPDX-License-Identifier: GPL-3.0-or-later", "# Copyright (C) 2026 hxebolax y colaboradores",
		'"""Sumas de los complementos de serie de esta compilación (las genera setup_cx.py; no se edita)."""', "",
		"SUMAS: dict[str, dict[str, str]] = {"]
	for id_complemento, archivos in sorted(sumas_serie().items()):
		lineas.append(f"\t{id_complemento!r}: {{")
		lineas += [f"\t\t{ruta!r}: {suma!r}," for ruta, suma in sorted(archivos.items())]
		lineas.append("\t},")
	lineas.append("}")
	SUMAS_SERIE.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")


def biblioteca_estandar() -> list[str]:
	"""Módulos de la biblioteca estándar que existen en este CPython, sin la lista negra (17.1)."""
	resultado = []
	for nombre in sorted(sys.stdlib_module_names):
		if nombre in LISTA_NEGRA or nombre.startswith("_"):
			continue
		try:
			if importlib.util.find_spec(nombre) is not None:
				resultado.append(nombre)
		except (ImportError, ValueError):
			continue
	return resultado


def python3t_compatible(base: Path | None = None) -> Path | None:
	"""La ``python3t.dll`` que sirve a este intérprete, o ``None`` si cx_Freeze ya copia la buena.

	Las extensiones «abi3t» (``cryptography`` 50) importan ``python3t.dll``. La de la raíz de
	Python reenvía a ``python315t.dll`` (el intérprete sin GIL), que no va en la compilación:
	en un equipo sin Python, ``cryptography`` no carga y no se pueden verificar las firmas de
	las actualizaciones (fallo de la 2.0.0 y la 2.0.1). Un Python con GIL trae en
	``abi3t-compat`` otra que reenvía a ``python315.dll``: esa es la que debe ir.
	"""
	if sysconfig.get_config_var("Py_GIL_DISABLED"):
		return None
	compatible = Path(base or sys.base_prefix) / "abi3t-compat" / "python3t.dll"
	return compatible if compatible.is_file() else None


def poner_python3t_compatible(destino: Path, base: Path | None = None) -> bool:
	"""Sustituye ``destino/python3t.dll`` por la compatible con este intérprete; ``True`` si la cambió."""
	compatible = python3t_compatible(base)
	actual = destino / "python3t.dll"
	if compatible is None or not actual.is_file():
		return False
	shutil.copy2(compatible, actual)
	return True


def borrar_dll_no_libres(destino: Path) -> list[str]:
	"""Quita de la compilación las DLL no libres de accessible_output2 (2.3); devuelve las borradas."""
	prohibidas = {nombre.lower() for nombre in DLL_NO_LIBRES}
	borradas = []
	for ruta in sorted(destino.rglob("*")):
		if ruta.is_file() and ruta.name.lower() in prohibidas:
			ruta.unlink()
			borradas.append(ruta.relative_to(destino).as_posix())
	return borradas


def copiar_datos_y_complementos(destino: Path) -> int:
	"""Copia ``data`` (lista blanca) y ``plugins`` a la compilación; devuelve cuántos archivos.

	No se pasan por ``include_files``: cx_Freeze copiaría a ``lib/`` las DLL de las que
	dependen los ejecutables y las DLL de ``data/bin`` (FFmpeg, libarchive), duplicando
	unos 180 MB y llevándolas fuera de su carpeta y de su licencia.
	"""
	pares = archivos_de_data() + archivos_de_plugins()
	for origen, relativo in pares:
		final = destino / relativo
		final.parent.mkdir(parents=True, exist_ok=True)
		shutil.copy2(origen, final)
	return len(pares)


def borrar_no_distribuible(destino: Path) -> list[str]:
	"""Quita lo que el gancho de pywin32 copia aunque no se use (``NO_DISTRIBUIR``); devuelve lo borrado."""
	borrados = []
	for relativo in NO_DISTRIBUIR:
		ruta = destino / relativo
		if ruta.is_dir():
			shutil.rmtree(ruta)
		elif ruta.is_file():
			ruta.unlink()
		else:
			continue
		borrados.append(relativo)
	return borrados


def _disponible(modulo: str) -> bool:
	try:
		return importlib.util.find_spec(modulo) is not None
	except (ImportError, ValueError):
		return False


def paquetes() -> list[str]:
	"""Obligatorios (se detiene si falta alguno), opcionales presentes y la biblioteca estándar filtrada."""
	faltan = [p for p in PAQUETES if not _disponible(p)]
	if faltan:
		raise ErrorCompilacion("ERROR: faltan paquetes obligatorios en el entorno: " + ", ".join(faltan)
			+ ". Instálelos con «entorno.bat instalar».")
	return PAQUETES + [p for p in PAQUETES_OPCIONALES if _disponible(p)] + biblioteca_estandar()


def comprobar_componentes() -> None:
	"""``data/bin`` coincide con ``linea_base.json`` (17.2, paso 3)."""
	resultado = subprocess.run([sys.executable, str(RAIZ / "tools" / "preparar_componentes.py"), "--comprobar"], cwd=RAIZ,  # noqa: S603
		check=False)
	if resultado.returncode != 0:
		raise ErrorCompilacion("ERROR: data/bin no coincide con linea_base.json (tools/preparar_componentes.py --comprobar).")


def construir_complemento_nvda() -> Path:
	"""Genera ``data/bin/nvda/zCommander-<versión>.nvda-addon`` de esta versión (17.2, paso 4; peticiones de NV)."""
	from tools import construir_complemento

	try:
		informe = construir_complemento.construir()
	except construir_complemento.ErrorComplemento as error:
		raise ErrorCompilacion(f"ERROR: no se pudo construir el complemento de NVDA: {error}") from error
	ruta = Path(getattr(informe, "ruta", "") or next((RAIZ / "data" / "bin" / "nvda").glob("zCommander-*.nvda-addon")))
	print(f"Complemento de NVDA: {ruta.name}")
	return ruta


def comprobar_licencias_repositorio() -> None:
	"""Licencias y cabeceras del repositorio (17.2, paso 5)."""
	from tools import comprobar_licencias

	problemas = comprobar_licencias.problemas_repositorio()
	if problemas:
		print("\n".join(problemas))
		raise ErrorCompilacion("ERROR: hay problemas de licencias (tools/comprobar_licencias.py). Si falta un texto, ejecute "
			"«python tools/generar_licencias.py».")


def comprobar_licencias_compilacion(destino: Path) -> int:
	"""Lo que viaja tiene su licencia y no hay DLL no libres; devuelve el número de problemas."""
	from tools import comprobar_licencias

	problemas = comprobar_licencias.problemas_compilacion(destino)
	for problema in problemas:
		print(problema)
	print("Licencias de la compilación: " + (f"{len(problemas)} problemas." if problemas else "sin problemas."))
	return len(problemas)


if __name__ == "__main__":
	MODO_DEBUG = "--debug" in sys.argv
	if MODO_DEBUG:
		sys.argv.remove("--debug")
	SIN_COMPROBACIONES = "--sin-comprobaciones" in sys.argv
	if SIN_COMPROBACIONES:
		sys.argv.remove("--sin-comprobaciones")
	compilando = any(orden.startswith("build") for orden in sys.argv[1:])
	if compilando:
		if not SIN_COMPROBACIONES:
			comprobar_componentes()
		construir_complemento_nvda()
		if not SIN_COMPROBACIONES:
			comprobar_licencias_repositorio()
		if DESTINO.exists():
			# Si se probó la copia compilada, su data/ tiene configuración y registros.
			print(f"Limpiando la compilación anterior: {DESTINO}")
			shutil.rmtree(DESTINO)
		escribir_sumas_serie()
	problemas_finales = 0
	try:
		setup(
			name=NOMBRE_APP,
			version=leer_version(),
			description=DESCRIPCION,
			options={
				"build_exe": {
					"build_exe": str(DESTINO),
					"packages": paquetes() if compilando else [],
					"excludes": EXCLUDES,
					"include_msvcr": True,
					# Trazas con rutas relativas, sin las carpetas del equipo donde se compiló.
					"replace_paths": [("*", "")],
					# optimize=2 quita las docstrings y rompe bibliotecas que las leen.
					"optimize": 1,
				}
			},
			executables=[
				Executable(
					script=str(RAIZ / "main.py"),
					base=None if MODO_DEBUG else "gui",
					target_name=EJECUTABLE,
					icon=str(ICONO) if ICONO.is_file() else None,
					manifest=str(MANIFIESTO) if MANIFIESTO.is_file() else None,
				)
			],
		)
		if compilando and DESTINO.exists():
			print(f"Copiados {copiar_datos_y_complementos(DESTINO)} archivos de data/ y plugins/")
			for borrado in borrar_no_distribuible(DESTINO):
				print(f"Quitado {borrado} (no se usa ni se distribuye)")
			for borrada in borrar_dll_no_libres(DESTINO):
				print(f"Quitada la DLL no libre {borrada}")
			if poner_python3t_compatible(DESTINO):
				print("python3t.dll sustituida por la compatible (abi3t-compat): reenvía a python315.dll")
			from tools import dependencias_pe

			sin_resolver = dependencias_pe.problemas(DESTINO)
			for linea in sin_resolver:
				print(f"ERROR: {linea}")
			problemas_finales = comprobar_licencias_compilacion(DESTINO) or bool(sin_resolver)
	finally:
		SUMAS_SERIE.unlink(missing_ok=True)
	if problemas_finales:
		sys.exit(1)
