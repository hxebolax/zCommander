# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Prepara una versión de zCommander y, si se pide, la deja en la carpeta del servidor (diseño 2.0, 5.6).

Uso (desde la raíz del proyecto, con el entorno activo)::

	python tools/publicar.py                       # solo prepara dist/
	python tools/publicar.py --servidor            # y lo copia al servidor
	python tools/publicar.py --sin-fuentes         # sin el ZIP de fuentes
	python tools/publicar.py --sin-github          # sin «espejos.github» en version.json
	python tools/publicar.py --firmar-complementos zc.reproductor zc.git

Pasos:

1. Lee la versión de ``app/core/version.py`` y exige su entrada (no vacía) en
   ``data/docs/changelog.md``: son las novedades del manifiesto.
2. Compila con ``setup_cx.py`` y comprueba que arranca
   (``ZCommander.exe --comprobar-arranque --complemento-prueba tests/datos/plugins/ejemplo``).
3. Ejecuta ``tools/comprobar_licencias.py`` sobre la compilación (si aún no
   existe, avisa y sigue).
4. Crea ``dist/zCommander_v<versión>.zip`` con ``tools/empaquetar.py``, después de
   comprobar que la compilación no lleva datos personales.
5. Crea ``dist/version.json`` y lo FIRMA con ``tools/claves/firma_ed25519.key``;
   comprueba que la firma la acepta la clave pública incrustada en la aplicación.
   Salvo con ``--sin-github``, lleva el campo firmado ``espejos.github`` con la
   dirección del ZIP en la release de GitHub de esta versión
   (``https://github.com/hxebolax/zCommander/releases/download/v<versión>/zCommander_v<versión>.zip``).
   La release (etiqueta ``v<versión>``) se crea a mano y lleva como recursos el ZIP,
   el ZIP de fuentes y ESTE MISMO ``version.json``.
6. Crea ``dist/zCommander_v<versión>_fuentes.zip`` (2.4), salvo con ``--sin-fuentes``.
7. Solo con ``--firmar-complementos``: ``<id>-<versión>.zcplugin`` firmado con la
   clave del proyecto (``app.plugins.firma``) y su JSON de actualización (3.10).
8. Con ``--servidor``, copia a ``%USERPROFILE%\\SynologyDrive\\web\\zCommander``
   PRIMERO los paquetes (ZIP, fuentes, ``.zcplugin``) y DESPUÉS los JSON
   (``version.json`` el último): nadie ve un manifiesto que apunte a un paquete que
   aún no está. Al final comprueba que los tamaños copiados coinciden.

La clave privada nunca sale de ``tools/claves/``.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

NOMBRE = "zCommander"
EJECUTABLE = "ZCommander.exe"
SERVIDOR = Path.home() / "SynologyDrive" / "web" / "zCommander"
URL_BASE = "https://xebolax.synology.me/zCommander/"
REPOSITORIO_GITHUB = "hxebolax/zCommander"
CLAVE = RAIZ / "tools" / "claves" / "firma_ed25519.key"
COMPLEMENTO_PRUEBA = Path("tests") / "datos" / "plugins" / "ejemplo"
# Carpetas de data que son de la persona: nunca en un paquete (las mismas que setup_cx.DATA_PROHIBIDO).
PERSONALES = frozenset({"config", "logs", "db", "cache", "temp", "sessions", "backups", "downloads", "plugins",
	"sounds_usuario", "plantillas"})
# Lo que no entra en el ZIP de fuentes (2.4): entorno, compilación, claves, material ajeno y datos.
FUENTES_EXCLUIDAS = frozenset({".venv", "venv", "build", "dist", "adjuntos", ".git", "__pycache__", ".pytest_cache",
	".ruff_cache", ".mypy_cache"})


class ErrorPublicar(Exception):
	"""Un paso de la publicación no se puede completar; el mensaje dice qué hacer."""


def _ok(texto: str) -> None:
	print(f"[OK] {texto}")


def _aviso(texto: str) -> None:
	print(f"[AVISO] {texto}")


def _firmador():
	"""``tools/firmar_version.py`` como módulo (``tools`` no se importa como paquete aquí)."""
	sys.path.insert(0, str(Path(__file__).resolve().parent))
	try:
		import firmar_version
	finally:
		sys.path.pop(0)
	return firmar_version


# ── 1. Versión y notas ───────────────────────────────────────────────────────


def version_de(raiz: Path) -> str:
	from tools.notas_version import version_del_proyecto

	numero = version_del_proyecto(raiz)
	if not numero:
		raise ErrorPublicar("No se encuentra APP_VERSION en app/core/version.py.")
	return numero


def novedades_de(raiz: Path, numero: str) -> str:
	"""Cuerpo de la entrada de la versión en ``data/docs/changelog.md``; sin ella no se publica."""
	from app.core import documentacion

	ruta = raiz / "data" / "docs" / documentacion.CHANGELOG
	try:
		texto = ruta.read_text(encoding="utf-8-sig")
	except OSError as error:
		raise ErrorPublicar(f"No se pudo leer el registro de cambios {ruta}: {error}") from error
	entrada = documentacion.notas_de_version(texto, numero)
	if entrada is None or not entrada.texto.strip():
		raise ErrorPublicar(f"La versión {numero} no tiene notas en {ruta}. Añada «## Versión {numero} - AAAA-MM-DD» con sus cambios.")
	return entrada.texto.strip()


# ── 2 y 3. Compilación, arranque y licencias ─────────────────────────────────


def compilar(raiz: Path) -> None:
	resultado = subprocess.run([sys.executable, "setup_cx.py", "build"], cwd=raiz, check=False)  # noqa: S603 - nuestro guion
	if resultado.returncode != 0:
		raise ErrorPublicar(f"La compilación falló (código {resultado.returncode}).")
	_ok("Compilación hecha")


def _quitar_personales(build: Path) -> None:
	for nombre in PERSONALES:
		shutil.rmtree(build / "data" / nombre, ignore_errors=True)


def comprobar_arranque(raiz: Path, build: Path) -> None:
	exe = build / EJECUTABLE
	if not exe.is_file():
		raise ErrorPublicar(f"No existe {exe}. Compile primero: python setup_cx.py build")
	orden = [str(exe), "--comprobar-arranque", "--complemento-prueba", str(raiz / COMPLEMENTO_PRUEBA)]
	resultado = subprocess.run(orden, timeout=300, check=False)  # noqa: S603 - nuestro ejecutable
	# La comprobación deja registros: se borran para no publicarlos.
	_quitar_personales(build)
	if resultado.returncode != 0:
		raise ErrorPublicar(f"El ejecutable no arranca (código {resultado.returncode}). Mire build/ZCommander/data/logs.")
	_ok("El ejecutable arranca y carga el complemento de prueba")


def comprobar_licencias(raiz: Path, build: Path) -> None:
	herramienta = raiz / "tools" / "comprobar_licencias.py"
	if not herramienta.is_file():
		_aviso("Aún no existe tools/comprobar_licencias.py (bloque LI): no se han comprobado las licencias.")
		return
	resultado = subprocess.run([sys.executable, str(herramienta), str(build)], cwd=raiz, check=False)  # noqa: S603
	if resultado.returncode != 0:
		raise ErrorPublicar("tools/comprobar_licencias.py encontró problemas en la compilación.")
	_ok("Licencias comprobadas")


# ── 4 y 5. Paquete y manifiesto firmado ──────────────────────────────────────


def comprobar_sin_personales(build: Path) -> None:
	datos = build / "data"
	if not datos.is_dir():
		return
	personales = sorted(c.name for c in datos.iterdir() if c.is_dir() and c.name in PERSONALES)
	if personales:
		raise ErrorPublicar(f"La compilación tiene datos personales en data: {', '.join(personales)}. Vuelva a compilar sin probarla.")
	entrante = [n for n in ("respaldo", ".pendiente", ".entrante") if (datos / "bin" / n).exists()]
	if entrante:
		raise ErrorPublicar(f"La compilación tiene restos del actualizador de componentes en data/bin: {', '.join(entrante)}.")


def empaquetar(build: Path, dist: Path, numero: str) -> Path:
	from tools import empaquetar as herramienta

	comprobar_sin_personales(build)
	destino = dist / f"{NOMBRE}_v{numero}.zip"
	zip_, incluidos, omitidos = herramienta.empaquetar(build, destino)
	_ok(f"{zip_.name}: {incluidos} archivos ({zip_.stat().st_size / 1e6:.1f} MB); omitidos {omitidos}")
	return zip_


def _sha256(ruta: Path) -> str:
	resumen = hashlib.sha256()
	with ruta.open("rb") as archivo:
		for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
			resumen.update(bloque)
	return resumen.hexdigest()


def url_release_github(numero: str, archivo: str | None = None) -> str:
	"""Dirección de un recurso de la release ``v<numero>`` de GitHub (por defecto, el ZIP de la aplicación)."""
	archivo = archivo or f"{NOMBRE}_v{numero}.zip"
	return f"https://github.com/{REPOSITORIO_GITHUB}/releases/download/v{numero}/{archivo}"


def crear_manifiesto(zip_: Path, numero: str, novedades: str, clave: Path, claves_publicas: Sequence[str], *,
		espejo_github: bool = True) -> Path:
	"""``version.json`` junto al ZIP, firmado entero; la firma se comprueba con las claves de la aplicación.

	:param espejo_github: añade ``espejos.github`` (firmado como todo lo demás) con el ZIP de la release
		de GitHub. Los clientes 2.0.0 ignoran el campo y siguen descargando del servidor.
	"""
	if not clave.is_file():
		raise ErrorPublicar(f"Falta la clave privada {clave}: sin ella las instalaciones rechazarán la versión.")
	datos = {
		"app": NOMBRE,
		"version": numero,
		"file": zip_.name,
		"sha256": _sha256(zip_),
		"size": zip_.stat().st_size,
		"date": datetime.date.today().isoformat(),
		"novedades": novedades,
	}
	if espejo_github:
		datos["espejos"] = {"github": url_release_github(numero, zip_.name)}
	ruta = zip_.with_name("version.json")
	ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
	firmador = _firmador()
	firmador.firmar(clave, ruta)
	problemas = [p for p in firmador.verificar(ruta, list(claves_publicas)) if not p.startswith("Aviso:")]
	if problemas:
		raise ErrorPublicar("El manifiesto no lo aceptaría la aplicación: " + " ".join(problemas)
			+ " ¿Es la clave de CLAVES_PUBLICAS_ED25519 de app/services/actualizador.py?")
	_ok(f"version.json firmado ({URL_BASE}version.json)" + (" con el espejo de GitHub" if espejo_github else ""))
	return ruta


# ── 6. Fuentes (2.4) ─────────────────────────────────────────────────────────


def _excluida_de_fuentes(relativa: Path) -> bool:
	partes = relativa.parts
	if any(parte in FUENTES_EXCLUIDAS or parte.endswith(".egg-info") for parte in partes):
		return True
	if partes[:2] in (("tools", "claves"), ("docs", "investigacion"), ("docs", "revision")):
		# docs/investigacion y docs/revision son material de trabajo interno con datos del equipo y
		# del NAS de quien desarrolla: tampoco van a git (.gitignore).
		return True
	if partes[0] == "data" and len(partes) > 1 and (partes[1] in PERSONALES or partes[1] == "bin" and len(partes) > 2
			and partes[2] in ("respaldo", ".pendiente", ".entrante")):
		return True
	return relativa.suffix.lower() in {".pyc", ".log", ".tmp", ".key", ".pem"}


def crear_fuentes(raiz: Path, dist: Path, numero: str) -> Path:
	"""El repositorio de esta versión, sin ``adjuntos/``, sin ``tools/claves/`` y sin datos personales."""
	destino = dist / f"{NOMBRE}_v{numero}_fuentes.zip"
	temporal = destino.with_suffix(".zip.tmp")
	dist_resuelta = dist.resolve()
	cuantos = 0
	with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as paquete:
		for ruta in sorted(raiz.rglob("*")):
			if not ruta.is_file() or ruta.resolve().is_relative_to(dist_resuelta):
				continue
			relativa = ruta.relative_to(raiz)
			if _excluida_de_fuentes(relativa):
				continue
			paquete.write(ruta, Path(f"{NOMBRE}-{numero}") / relativa)
			cuantos += 1
	temporal.replace(destino)
	_ok(f"{destino.name}: {cuantos} archivos")
	return destino


# ── 7. Complementos de serie firmados (3.9, 3.10) ────────────────────────────


def _privada_en_bruto(clave: Path) -> bytes:
	from cryptography.hazmat.primitives import serialization

	privada = _firmador().cargar_privada(clave)
	return privada.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())


def _carpeta_de(id_complemento: str, carpeta_plugins: Path):
	from app.plugins import manifiesto

	for carpeta in sorted(p for p in carpeta_plugins.iterdir() if (p / manifiesto.NOMBRE).is_file()):
		datos = manifiesto.leer(carpeta)
		if datos.id == id_complemento:
			return carpeta, datos
	raise ErrorPublicar(f"No se encuentra el complemento {id_complemento} en {carpeta_plugins}.")


def _novedades_complemento(carpeta: Path, version: str) -> str:
	from app.core import documentacion

	ruta = carpeta / "doc" / "es" / "cambios.md"
	try:
		entrada = documentacion.notas_de_version(ruta.read_text(encoding="utf-8-sig"), version)
	except (OSError, ValueError):
		return ""
	return entrada.texto.strip() if entrada else ""


def firmar_complementos(ids: Sequence[str], clave: Path, dist: Path, carpeta_plugins: Path = RAIZ / "plugins",
		url_base: str = URL_BASE) -> list[tuple[Path, Path]]:
	"""Para cada id, ``<id>-<versión>.zcplugin`` firmado y su JSON de actualización firmado igual.

	Se firma una copia en una carpeta temporal: el repositorio no se toca.
	"""
	from app.plugins import firma

	privada = _privada_en_bruto(clave)
	firmador = _firmador()
	from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

	firmante = Ed25519PrivateKey.from_private_bytes(privada)
	hechos: list[tuple[Path, Path]] = []
	for id_complemento in ids:
		carpeta, datos = _carpeta_de(id_complemento, carpeta_plugins)
		with tempfile.TemporaryDirectory(prefix="zc_publicar_") as temporal:
			copia = Path(temporal) / carpeta.name
			shutil.copytree(carpeta, copia, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", firma.NOMBRE_FIRMA))
			firma.firmar_complemento(copia, datos.id, datos.version, privada)
			paquete = dist / f"{datos.id}-{datos.version}.zcplugin"
			with zipfile.ZipFile(paquete, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as salida:
				for relativa in firma.listar_archivos(copia) + [firma.NOMBRE_FIRMA]:
					salida.write(copia / relativa, relativa)
		actualizacion = {
			"id": datos.id,
			"version": datos.version,
			"url": url_base + paquete.name,
			"sha256": _sha256(paquete),
			"tamano": paquete.stat().st_size,
			"novedades": _novedades_complemento(carpeta, datos.version),
		}
		actualizacion["firma_ed25519"] = base64.b64encode(firmante.sign(firmador.serializar_canonico(actualizacion))).decode("ascii")
		ruta_json = dist / f"{datos.id}.json"
		ruta_json.write_text(json.dumps(actualizacion, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
		_ok(f"{paquete.name} y {ruta_json.name} firmados")
		hechos.append((paquete, ruta_json))
	return hechos


# ── 8. Servidor ──────────────────────────────────────────────────────────────


def _copiar(origen: Path, destino: Path) -> None:
	"""Copia con nombre temporal y renombrado: quien descarga nunca ve un archivo a medias."""
	temporal = destino.with_name(destino.name + ".subiendo")
	shutil.copy2(origen, temporal)
	os.replace(temporal, destino)


def al_servidor(paquetes: Sequence[Path], manifiestos: Sequence[Path], destino: Path = SERVIDOR,
		copiar: Callable[[Path, Path], None] | None = None) -> list[str]:
	"""Copia primero los paquetes y después los JSON; comprueba los tamaños. Devuelve el orden de copia."""
	copiar = copiar or _copiar
	if not destino.parent.is_dir():
		raise ErrorPublicar(f"No existe la carpeta del servidor {destino.parent}.")
	destino.mkdir(exist_ok=True)
	orden: list[str] = []
	for archivo in [*paquetes, *manifiestos]:
		copiar(archivo, destino / archivo.name)
		orden.append(archivo.name)
	distintos = [a.name for a in [*paquetes, *manifiestos] if (destino / a.name).stat().st_size != a.stat().st_size]
	if distintos:
		raise ErrorPublicar(f"El tamaño copiado no coincide en: {', '.join(distintos)}.")
	_ok(f"Copiado a {destino}: {', '.join(orden)}")
	return orden


# ── Todo junto ───────────────────────────────────────────────────────────────


def crear_componentes(raiz: Path, dist: Path, numero: str) -> Path | None:
	"""``dist/zCommander_v<versión>_componentes.zip`` con los binarios de ``data/bin`` para la release de GitHub.

	Es lo que descarga ``tools/descargar_componentes.py`` a quien clona el repositorio (los binarios
	no están en git). Sin ``linea_base.json`` (un proyecto de prueba) no se crea.
	"""
	from tools import descargar_componentes as dc

	bin_ = raiz / "data" / "bin"
	if not (bin_ / "linea_base.json").is_file():
		return None
	zip_ = dc.crear_paquete(dc.binarios_esperados(dc.leer_base(bin_)), dist, bin_=bin_, version=numero)
	_ok(f"Paquete de componentes para GitHub: {zip_.name}")
	return zip_


def publicar(*, raiz: Path = RAIZ, build: Path | None = None, dist: Path | None = None, clave: Path = CLAVE,
		servidor: bool = False, destino: Path = SERVIDOR, sin_fuentes: bool = False, compilar_antes: bool = True,
		comprobar: bool = True, complementos: Sequence[str] = (), claves_publicas: Sequence[str] | None = None,
		espejo_github: bool = True) -> list[str]:
	"""Los pasos 1 a 8. Devuelve los nombres de lo publicado (o preparado) en orden."""
	build = build or raiz / "build" / "ZCommander"
	dist = dist or raiz / "dist"
	if claves_publicas is None:
		from app.services import actualizador

		claves_publicas = actualizador.CLAVES_PUBLICAS_ED25519
	numero = version_de(raiz)
	novedades = novedades_de(raiz, numero)
	_ok(f"Versión {numero} con sus notas")
	if compilar_antes:
		compilar(raiz)
	if comprobar:
		comprobar_arranque(raiz, build)
		comprobar_licencias(raiz, build)
	dist.mkdir(parents=True, exist_ok=True)
	zip_ = empaquetar(build, dist, numero)
	manifiesto = crear_manifiesto(zip_, numero, novedades, clave, claves_publicas, espejo_github=espejo_github)
	paquetes = [zip_]
	if not sin_fuentes:
		paquetes.append(crear_fuentes(raiz, dist, numero))
	jsons = []
	if complementos:
		for paquete, ruta_json in firmar_complementos(complementos, clave, dist, raiz / "plugins"):
			paquetes.append(paquete)
			jsons.append(ruta_json)
	jsons.append(manifiesto)  # version.json, el último de todos
	if espejo_github:
		# El version.json firmado apunta ya a la release: sin ella, quien elija GitHub no puede descargar.
		# El ZIP de componentes no va al servidor: solo lo usa tools/descargar_componentes.py desde GitHub.
		componentes = crear_componentes(raiz, dist, numero)
		extra = f", {componentes.name}" if componentes else ""
		print(f"En GitHub: release con etiqueta v{numero} en {REPOSITORIO_GITHUB} con {zip_.name}, "
			f"{NOMBRE}_v{numero}_fuentes.zip{extra} y este mismo version.json como recursos.")
	if servidor:
		return al_servidor(paquetes, jsons, destino)
	print("Para publicarla: python tools/publicar.py --servidor")
	return [p.name for p in [*paquetes, *jsons]]


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description="Prepara (y publica) una versión de zCommander.")
	analizador.add_argument("--servidor", action="store_true", help="Copiar lo preparado a la carpeta del servidor.")
	analizador.add_argument("--sin-fuentes", action="store_true", help="No crear el ZIP de fuentes.")
	analizador.add_argument("--sin-github", action="store_true",
		help="No añadir «espejos.github» (la release de GitHub) al version.json.")
	analizador.add_argument("--firmar-complementos", nargs="+", default=[], metavar="ID",
		help="Firmar y publicar estos complementos de serie.")
	analizador.add_argument("--sin-compilar", action="store_true", help="Usar la compilación que ya hay en build/.")
	analizador.add_argument("--sin-comprobar", action="store_true", help="No arrancar el ejecutable ni comprobar licencias.")
	analizador.add_argument("--destino", type=Path, default=SERVIDOR, help="Carpeta del servidor (para probar con otra).")
	analizador.add_argument("--clave", type=Path, default=CLAVE, help="Clave privada de firma.")
	opciones = analizador.parse_args(argumentos)
	for flujo in (sys.stdout, sys.stderr):
		if hasattr(flujo, "reconfigure"):
			flujo.reconfigure(errors="replace")
	try:
		publicar(clave=opciones.clave, servidor=opciones.servidor, destino=opciones.destino, sin_fuentes=opciones.sin_fuentes,
			compilar_antes=not opciones.sin_compilar, comprobar=not opciones.sin_comprobar,
			complementos=opciones.firmar_complementos, espejo_github=not opciones.sin_github)
	except (ErrorPublicar, OSError, ValueError, subprocess.SubprocessError) as error:
		print(f"[ERROR] {error}")
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
