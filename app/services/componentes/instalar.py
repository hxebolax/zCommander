# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Actualizar, volver atrás y restaurar componentes (diseño 2.0, 6.6). Sin wx.

Pasos para cada componente (6.6), en este orden:

1. **Descargar** a ``data/temp/componentes/<id>/`` (``.parcial`` reanudable).
2. **Verificar** el SHA-256 de cada paquete con la suma de su origen. Sin suma
   publicada no se instala nada; si no coincide, se borra y no se toca nada.
3. **Extraer** solo los miembros de ``extraer`` a ``.../nuevo/``, sin libarchive
   (``zipfile``, ``tarfile`` con ``r:zst`` y py7zr; si py7zr no admite el filtro
   del ``.7z``, con el 7za activo o el 7-Zip de la persona). Nombres validados,
   sin enlaces y con tope de tamaño.
4. **Probar** la versión nueva desde ``nuevo/``. Si falla, la instalación no se toca.
5. **Mantenimiento y uso**: el componente pasa a «en mantenimiento»; si está en
   uso, se espera, se detiene o se deja en ``data/bin/.pendiente/<id>/``.
6. **Respaldar** la versión activa en ``data/bin/respaldo/<id>/<versión>/``.
7. **Sustituir** con diario (``data/bin/instalando.json`` con las sumas de lo
   nuevo): copia de la carpeta activa a ``<carpeta>.nueva`` con lo nuevo encima
   y dos renombrados con reintentos. Nunca quedan versiones mezcladas.
8. **Probar otra vez** desde su sitio; si falla, vuelta atrás automática al respaldo.
9. Fuera de mantenimiento, diario borrado.

«Volver a la versión anterior» y «Restaurar los componentes originales» siguen
los pasos 5 a 8 con los archivos del respaldo (copia exacta, sin mezclar). Los
pendientes y lo que trae una actualización de la aplicación siguen los pasos 6
a 8 en el arranque (``integrar.py``).

``OperacionComponente`` hace todo esto como operación del motor (progreso,
cancelación y resumen como las demás).
"""

from __future__ import annotations

import builtins
import fnmatch
import json
import logging
import os
import re
import shutil
import stat
import tarfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from app.core import descargas, procesos, red
from app.services.componentes import en_uso, fichas, fuentes, prueba
from app.services.componentes.estado import Entorno
from app.services.operaciones.modelo import ContextoEjecucion, Estado, Operacion

log = logging.getLogger(__name__)

#: Esperas entre reintentos de cada renombrado (6.6): un antivirus o un vigilante de cambios sueltan la carpeta enseguida.
ESPERAS_RENOMBRAR = (0.2, 0.5, 1.0, 2.0, 4.0)
#: Tope de lo que se extrae de un paquete (protege de bombas de descompresión).
MAX_EXTRAIDO = 4 * 1024**3
#: Respaldos que se guardan por componente, además del de la línea base (6.3).
RESPALDOS_GUARDADOS = 2

ACTUALIZADO, PENDIENTE, REVERTIDO, FALLIDO, SIN_CAMBIOS, CANCELADO = (
	"actualizado", "pendiente", "revertido", "fallido", "sin_cambios", "cancelado")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorComponente(Exception):
	"""Algo impidió instalar; ``mensaje`` en español. Nada se ha tocado en ``data/bin``."""

	def __init__(self, mensaje: str) -> None:
		super().__init__(mensaje)
		self.mensaje = mensaje


class ErrorRenombrar(ErrorComponente):
	"""Un renombrado no fue posible ni con reintentos (carpeta abierta por otro proceso)."""


@dataclass
class Resultado:
	"""Lo que pasó con un componente. ``sonido``: el evento del catálogo que corresponde (4.2)."""

	id: str
	estado: str
	mensaje: str
	version: str = ""

	@property
	def sonido(self) -> str:
		return {ACTUALIZADO: "comp.actualizado", REVERTIDO: "comp.revertido"}.get(self.estado, "")


# ── Utilidades de disco ──────────────────────────────────────────────────────


def _nombre_respaldo(ficha: dict) -> str:
	"""Carpeta del respaldo: la versión y, si la publicación reutiliza su etiqueta, el principio del ``digest``."""
	nombre = str(ficha.get("version") or "sin-version")
	digest = str((ficha.get("asset") or {}).get("digest", ""))
	if digest.startswith("sha256:"):
		nombre += "+" + digest[7:15]
	return re.sub(r"[^A-Za-z0-9._+-]", "_", nombre)


def _borrar(ruta: Path) -> None:
	"""Borra una carpeta o archivo; los de solo lectura también. Un fallo se registra y no se lanza."""
	def quitar_solo_lectura(funcion, camino, _info) -> None:
		try:
			os.chmod(camino, stat.S_IWRITE)
			funcion(camino)
		except OSError:
			log.debug("No se pudo borrar %s", camino, exc_info=True)

	ruta = Path(ruta)
	try:
		if ruta.is_dir():
			shutil.rmtree(ruta, onexc=quitar_solo_lectura)
		elif ruta.exists():
			ruta.unlink()
	except OSError:
		log.warning("No se pudo borrar %s", ruta, exc_info=True)


def _copiar_encima(origen: Path, destino: Path) -> None:
	"""Copia el contenido de ``origen`` dentro de ``destino`` (sustituye lo que coincida)."""
	for archivo in sorted(p for p in Path(origen).rglob("*") if p.is_file()):
		final = destino / archivo.relative_to(origen)
		final.parent.mkdir(parents=True, exist_ok=True)
		if final.exists():
			os.chmod(final, stat.S_IWRITE)
		shutil.copy2(archivo, final)


def renombrar(origen: Path, destino: Path, esperas: tuple[float, ...] = ESPERAS_RENOMBRAR) -> None:
	"""``os.rename`` con reintentos (6.6). Lanza ``ErrorRenombrar`` si no lo consigue."""
	for intento in range(len(esperas) + 1):
		try:
			os.rename(origen, destino)
			return
		except OSError as error:
			if intento == len(esperas):
				log.warning("No se pudo renombrar %s a %s tras %d intentos: %s", origen, destino, intento + 1, error)
				raise ErrorRenombrar(_("No se pudo sustituir la carpeta {c}: la tiene abierta otro programa.").format(c=Path(origen).name)) from error
			time.sleep(esperas[intento])


def _destino_seguro(nombre: str) -> PurePosixPath:
	"""Ruta relativa sin unidades, sin «..», sin flujos alternativos ni nombres reservados de Windows."""
	ruta = PurePosixPath(nombre.replace("\\", "/"))
	partes = [p for p in ruta.parts if p not in ("", ".")]
	reservados = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
	if (not partes or ruta.is_absolute() or any(p == ".." for p in partes) or any(":" in p for p in partes)
			or any(p.split(".")[0].casefold() in reservados for p in partes)):
		raise ErrorComponente(_("El paquete trae un nombre no permitido: {n}").format(n=nombre))
	return PurePosixPath(*partes)


def _miembro_valido(nombre: str) -> str:
	"""Nombre de miembro normalizado («a/b/c»); rechaza rutas absolutas, unidades y «..»."""
	limpio = nombre.replace("\\", "/")
	if limpio.startswith("/") or re.match(r"^[A-Za-z]:", limpio) or ".." in limpio.split("/"):
		raise ErrorComponente(_("El paquete trae un nombre no permitido: {n}").format(n=nombre))
	return limpio.lstrip("./")


def _plan(nombres: list[str], mapa: dict[str, str]) -> dict[str, PurePosixPath]:
	"""``{miembro: destino}`` según el mapa ``extraer`` (comodines; «.» conserva el nombre en la raíz)."""
	plan: dict[str, PurePosixPath] = {}
	destinos: set[str] = set()
	for patron, destino in mapa.items():
		patron_limpio = patron.replace("\\", "/")
		coincidencias = [n for n in nombres if fnmatch.fnmatchcase(n, patron_limpio)]
		if not coincidencias:
			raise ErrorComponente(_("El paquete no trae «{p}».").format(p=patron))
		for nombre in coincidencias:
			if destino in (".", "./", ""):
				final = _destino_seguro(nombre.rsplit("/", 1)[-1])
			elif destino.endswith("/"):
				final = _destino_seguro(destino + nombre.rsplit("/", 1)[-1])
			else:
				final = _destino_seguro(destino)
			clave = final.as_posix().casefold()
			if clave in destinos and plan.get(nombre) != final:
				raise ErrorComponente(_("El paquete trae dos archivos para {d}.").format(d=final))
			destinos.add(clave)
			plan[nombre] = final
	return plan


def _escribir_flujo(flujo, final: Path, acumulado: list[int]) -> None:
	final.parent.mkdir(parents=True, exist_ok=True)
	with final.open("wb") as salida:
		for bloque in iter(lambda: flujo.read(1024 * 1024), b""):
			acumulado[0] += len(bloque)
			if acumulado[0] > MAX_EXTRAIDO:
				raise ErrorComponente(_("El paquete es demasiado grande al descomprimirlo; se descarta por seguridad."))
			salida.write(bloque)


def _extraer_zip(archivo: Path, mapa: dict[str, str], destino: Path) -> None:
	with zipfile.ZipFile(archivo) as zf:
		miembros = {_miembro_valido(i.filename): i for i in zf.infolist() if not i.is_dir()}
		plan = _plan(list(miembros), mapa)
		acumulado = [0]
		for nombre, final in plan.items():
			info = miembros[nombre]
			if stat.S_ISLNK(info.external_attr >> 16):
				raise ErrorComponente(_("El paquete trae un enlace: {n}").format(n=nombre))
			with zf.open(info) as flujo:
				_escribir_flujo(flujo, destino / final, acumulado)


def _extraer_tar(archivo: Path, mapa: dict[str, str], destino: Path) -> None:
	modo = "r:zst" if archivo.name.endswith(".zst") else "r:*"
	with tarfile.open(archivo, modo) as tar:
		miembros = {}
		for info in tar.getmembers():
			if info.isdir():
				continue
			nombre = _miembro_valido(info.name)
			miembros[nombre] = info
		plan = _plan([n for n in miembros if miembros[n].isfile() or miembros[n].issym() or miembros[n].islnk()], mapa)
		acumulado = [0]
		for nombre, final in plan.items():
			info = miembros[nombre]
			if not info.isfile():
				raise ErrorComponente(_("El paquete trae un enlace: {n}").format(n=nombre))
			flujo = tar.extractfile(info)
			if flujo is None:
				raise ErrorComponente(_("No se pudo leer {n} del paquete.").format(n=nombre))
			with flujo:
				_escribir_flujo(flujo, destino / final, acumulado)


def _siete_zip_disponible() -> Path | None:
	"""El 7za activo (si no está en mantenimiento) o el 7-Zip instalado por la persona."""
	from app.services.componentes import estado
	from app.services.vfs.base import NoAdmitido

	try:
		return estado.ejecutable("7za", "7za.exe")
	except NoAdmitido:
		pass
	for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
		base = os.environ.get(variable)
		if base and (Path(base) / "7-Zip" / "7z.exe").is_file():
			return Path(base) / "7-Zip" / "7z.exe"
	return None


def _extraer_7z(archivo: Path, mapa: dict[str, str], destino: Path, *, siete_zip: Callable[[], Path | None] | None = None,
		lanzar: Callable[..., procesos.ResultadoPrograma] | None = None) -> None:
	import py7zr

	with py7zr.SevenZipFile(archivo, "r") as sz:
		lista = sz.list()
		enlaces = {_miembro_valido(i.filename) for i in lista if getattr(i, "is_symlink", False)}
		nombres = [_miembro_valido(i.filename) for i in lista if not i.is_directory]
	plan = _plan(nombres, mapa)
	if enlaces & set(plan):
		raise ErrorComponente(_("El paquete trae un enlace: {n}").format(n=sorted(enlaces & set(plan))[0]))
	originales = {}
	try:
		with py7zr.SevenZipFile(archivo, "r") as sz:
			leidos = sz.read([n for n in plan]) or {}
		originales = {_miembro_valido(k): v for k, v in leidos.items()}
	except py7zr.exceptions.UnsupportedCompressionMethodError as error:
		log.info("py7zr no admite el filtro de %s (%s); se usa 7-Zip", archivo.name, error)
		_extraer_7z_externo(archivo, plan, destino, siete_zip or _siete_zip_disponible, lanzar or procesos.lanzar)
		return
	acumulado = [0]
	for nombre, final in plan.items():
		flujo = originales.get(nombre)
		if flujo is None:
			raise ErrorComponente(_("No se pudo leer {n} del paquete.").format(n=nombre))
		_escribir_flujo(flujo, destino / final, acumulado)


def _extraer_7z_externo(archivo: Path, plan: dict[str, PurePosixPath], destino: Path, siete_zip: Callable[[], Path | None],
		lanzar: Callable[..., procesos.ResultadoPrograma]) -> None:
	programa = siete_zip()
	if programa is None:
		raise ErrorComponente(_("Este paquete .7z necesita 7-Zip para abrirse y no hay ninguno disponible; no se ha cambiado nada."))
	temporal = destino.parent / "7z-extraido"
	_borrar(temporal)
	temporal.mkdir(parents=True)
	resultado = lanzar([str(programa), "x", str(archivo), f"-o{temporal}", "-y", "-snl-", "--", *plan], tiempo_s=600)
	if resultado.codigo != 0 or resultado.cancelado:
		raise ErrorComponente(_("7-Zip no pudo abrir el paquete (código {c}).").format(c=resultado.codigo))
	try:
		for nombre, final in plan.items():
			origen = temporal / nombre
			if not origen.is_file() or origen.is_symlink():
				raise ErrorComponente(_("No se pudo leer {n} del paquete.").format(n=nombre))
			(destino / final).parent.mkdir(parents=True, exist_ok=True)
			shutil.copy2(origen, destino / final)
	finally:
		_borrar(temporal)


def extraer_paquete(archivo: Path, mapa: dict[str, str], destino: Path, *, siete_zip: Callable[[], Path | None] | None = None,
		lanzar: Callable[..., procesos.ResultadoPrograma] | None = None) -> None:
	"""Extrae de ``archivo`` solo los miembros de ``mapa`` a ``destino`` (6.6, paso 3). Sin libarchive."""
	nombre = Path(archivo).name.casefold()
	destino.mkdir(parents=True, exist_ok=True)
	try:
		if nombre.endswith(".zip"):
			_extraer_zip(archivo, mapa, destino)
		elif nombre.endswith((".tar.zst", ".tar.gz", ".tar.xz", ".tar")):
			_extraer_tar(archivo, mapa, destino)
		elif nombre.endswith(".7z"):
			_extraer_7z(archivo, mapa, destino, siete_zip=siete_zip, lanzar=lanzar)
		else:
			raise ErrorComponente(_("Formato de paquete desconocido: {n}").format(n=Path(archivo).name))
	except ErrorComponente:
		raise
	except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError, ValueError) as error:
		log.warning("No se pudo abrir el paquete %s", archivo, exc_info=True)
		raise ErrorComponente(_("El paquete {n} está dañado o no se puede abrir.").format(n=Path(archivo).name)) from error
	except Exception as error:  # noqa: BLE001 - py7zr lanza sus propias excepciones (Bad7zFile, CrcError...)
		log.warning("No se pudo abrir el paquete %s", archivo, exc_info=True)
		raise ErrorComponente(_("El paquete {n} está dañado o no se puede abrir.").format(n=Path(archivo).name)) from error


# ── Instalador ───────────────────────────────────────────────────────────────


@dataclass
class Instalador:
	"""Pasos de 6.6 sobre un ``Entorno`` (las pruebas pasan carpetas temporales y un lanzador falso).

	:param lanzar: cómo se ejecutan las pruebas (``procesos.lanzar``).
	:param al_fase: recibe cada fase en español («Descargando rclone», «Probando»...).
	:param al_progresar: ``(hecho, total)`` de la descarga.
	:param antes_de_renombrar: se llama con la carpeta antes de renombrarla
		(la interfaz saca de ella los paneles de zCommander).
	:param buscar_procesos: ``procesos.hijos_vivos`` (las pruebas lo simulan).
	"""

	entorno: Entorno
	config_red: red.ConfiguracionRed
	lanzar: Callable[..., procesos.ResultadoPrograma] | None = None
	al_fase: Callable[[str], None] | None = None
	al_progresar: Callable[[int, int], None] | None = None
	cancelacion: Any = None
	antes_de_renombrar: Callable[[Path], None] | None = None
	buscar_procesos: Callable[[str], list[int]] | None = None
	esperas: tuple[float, ...] = ESPERAS_RENOMBRAR
	siete_zip: Callable[[], Path | None] | None = None
	mensajes: list[str] = field(default_factory=list)

	# Fichas ---------------------------------------------------------------

	def _fase(self, texto: str) -> None:
		log.info("%s", texto)
		if self.al_fase is not None:
			try:
				self.al_fase(texto)
			except Exception:  # noqa: BLE001 - la interfaz no corta la instalación
				log.debug("Falló al_fase", exc_info=True)

	def _cancelado(self) -> bool:
		return en_uso._cancelado(self.cancelacion)

	def _comprobar_cancelacion(self) -> None:
		if self._cancelado():
			raise ErrorComponente(_("Cancelado; no se ha cambiado nada."))

	def ficha(self, id: str) -> dict | None:
		from app.services.componentes import estado

		return estado.ficha_instalada(id, self.entorno)

	def base(self, id: str) -> dict | None:
		from app.services.componentes import estado

		return estado.ficha_base(id, self.entorno)

	def _guardar_ficha(self, ficha: dict) -> None:
		from app.services.componentes import estado

		estado.guardar_ficha(ficha, self.entorno)

	def carpeta(self, ficha: dict) -> Path:
		return self.entorno.bin / str(ficha.get("carpeta") or ficha["id"])

	def _probar(self, ficha: dict, carpeta: Path, version: str, definitiva: bool) -> prueba.ResultadoPrueba:
		self._fase(_("Probando {c}").format(c=ficha.get("nombre", ficha["id"])))
		return prueba.probar_ficha(ficha, carpeta, version=version, definitiva=definitiva, lanzar=self.lanzar, cancelacion=self.cancelacion)

	# Pasos 1 a 4 ---------------------------------------------------------------

	def preparar(self, ficha: dict, nueva: fuentes.VersionNueva) -> Path:
		"""Descarga, verifica y extrae a ``data/temp/componentes/<id>/nuevo``. Lanza ``ErrorComponente``."""
		nombre = str(ficha.get("nombre") or ficha["id"])
		trabajo = self.entorno.temporal / ficha["id"]
		nuevo = trabajo / "nuevo"
		_borrar(nuevo)
		trabajo.mkdir(parents=True, exist_ok=True)
		for paquete in nueva.paquetes:
			self._comprobar_cancelacion()
			if not re.fullmatch(r"[0-9a-f]{64}", paquete.sha256 or ""):
				raise ErrorComponente(_("No hay suma SHA-256 publicada para {p}; no se instala nada sin verificar.").format(p=paquete.nombre))
			self._fase(_("Descargando {c}").format(c=nombre))
			archivo = trabajo / fichas.sustituir(paquete.nombre)
			try:
				descargas.descargar(self.config_red, paquete.url, archivo, sha256=paquete.sha256, tamano=paquete.tamano,
					cancelacion=self.cancelacion, al_progresar=self.al_progresar)
			except red.ErrorHTTP as error:
				raise ErrorComponente(error.mensaje) from error
			self._fase(_("Comprobando {c}").format(c=nombre))
			extraer_paquete(archivo, paquete.extraer, nuevo, siete_zip=self.siete_zip, lanzar=self.lanzar)
		return nuevo

	def ficha_nueva(self, ficha: dict, nueva: fuentes.VersionNueva, version: str) -> dict:
		"""La ficha de la versión nueva (sin ``archivos``, que se calculan al sustituir)."""
		resultado = json.loads(json.dumps(ficha))
		resultado["version"] = version or ficha.get("version", "")
		if nueva.version_paquete:
			resultado["version_paquete"] = nueva.version_paquete
		if nueva.asset:
			resultado["asset"] = dict(nueva.asset)
		if nueva.rama and resultado.get("fuente", {}).get("rama"):
			resultado["fuente"]["rama"] = nueva.rama
		return resultado

	# Respaldos -------------------------------------------------------------------

	def respaldos(self, id: str) -> list[dict]:
		"""Respaldos de ``id``: ``[{"carpeta", "ficha", "guardado"}]``, el más reciente primero."""
		lista = []
		raiz = self.entorno.respaldo / id
		if not raiz.is_dir():
			return lista
		for carpeta in raiz.iterdir():
			datos_ficha = carpeta / "ficha.json"
			if not carpeta.is_dir() or not datos_ficha.is_file() or not (carpeta / "archivos").is_dir():
				continue
			try:
				datos = json.loads(datos_ficha.read_text(encoding="utf-8"))
			except (OSError, ValueError):
				log.warning("Respaldo ilegible: %s", carpeta, exc_info=True)
				continue
			lista.append({"carpeta": carpeta, "ficha": datos.get("ficha", {}), "guardado": float(datos.get("guardado", 0))})
		lista.sort(key=lambda r: r["guardado"], reverse=True)
		return lista

	def respaldar(self, ficha: dict) -> Path | None:
		"""Copia la versión activa en ``respaldo/<id>/<versión>/`` (paso 6). ``None`` si no hay carpeta activa."""
		origen = self.carpeta(ficha)
		if not origen.is_dir():
			return None
		destino = self.entorno.respaldo / ficha["id"] / _nombre_respaldo(ficha)
		archivos = fichas.sumas_de_carpeta(origen)
		marca = destino / "ficha.json"
		if marca.is_file():
			try:
				anterior = json.loads(marca.read_text(encoding="utf-8")).get("ficha", {})
				if fichas.mapa_sumas(anterior.get("archivos", [])) == fichas.mapa_sumas(archivos):
					marca.write_text(json.dumps({"ficha": anterior, "guardado": time.time()}, ensure_ascii=False, indent="\t"), encoding="utf-8")
					return destino
			except (OSError, ValueError):
				log.debug("Respaldo anterior ilegible en %s; se rehace", destino, exc_info=True)
		self._fase(_("Guardando copia de {c} {v}").format(c=ficha.get("nombre", ficha["id"]), v=ficha.get("version", "")))
		_borrar(destino)
		shutil.copytree(origen, destino / "archivos")
		guardada = dict(ficha, archivos=archivos)
		marca.write_text(json.dumps({"ficha": guardada, "guardado": time.time()}, ensure_ascii=False, indent="\t"), encoding="utf-8")
		return destino

	def podar_respaldos(self, id: str) -> None:
		"""Deja las dos últimas versiones respaldadas y, siempre, la de la línea base (6.3)."""
		base = self.base(id)
		nombre_base = _nombre_respaldo(base) if base else ""
		for indice, respaldo in enumerate(self.respaldos(id)):
			if indice < RESPALDOS_GUARDADOS or respaldo["carpeta"].name == nombre_base:
				continue
			log.info("Se borra el respaldo antiguo %s", respaldo["carpeta"])
			_borrar(respaldo["carpeta"])

	# Paso 7: sustitución con diario --------------------------------------------

	def _escribir_diario(self, datos: dict) -> None:
		fichas.escribir(self.entorno.diario, datos)

	def borrar_diario(self) -> None:
		self.entorno.diario.unlink(missing_ok=True)

	def sustituir(self, ficha_actual: dict, ficha_nueva: dict, origen: Path, *, mezclar: bool) -> dict:
		"""Sustituye la carpeta activa por ``origen`` (encima de una copia de la activa si ``mezclar``).

		Devuelve la ficha nueva con sus ``archivos``. Lanza ``ErrorRenombrar`` si la
		carpeta no se deja renombrar (lo hecho se deshace) y ``ErrorComponente``
		si la copia no sale con las sumas esperadas.
		"""
		carpeta = self.carpeta(ficha_actual)
		nueva = carpeta.with_name(carpeta.name + ".nueva")
		vieja = carpeta.with_name(carpeta.name + ".vieja")
		sumas = {}
		if mezclar and carpeta.is_dir():
			sumas.update({a["ruta"].casefold(): a for a in fichas.sumas_de_carpeta(carpeta)})
		sumas.update({a["ruta"].casefold(): a for a in fichas.sumas_de_carpeta(origen)})
		archivos = sorted(sumas.values(), key=lambda a: a["ruta"].casefold())
		ficha_final = dict(ficha_nueva, archivos=archivos)
		diario = {
			"id": ficha_actual["id"], "carpeta": carpeta.name, "version_anterior": ficha_actual.get("version", ""),
			"version_nueva": ficha_final.get("version", ""), "paso": "copiando",
			"sumas_nueva": {a["ruta"]: a["sha256"] for a in archivos},
			"ficha_nueva": ficha_final, "ficha_anterior": ficha_actual,
		}
		self._escribir_diario(diario)
		self._fase(_("Sustituyendo {c}").format(c=ficha_actual.get("nombre", ficha_actual["id"])))
		_borrar(nueva)
		if vieja.is_dir() and carpeta.is_dir():
			_borrar(vieja)  # restos de una sustitución anterior ya terminada
		if mezclar and carpeta.is_dir():
			shutil.copytree(carpeta, nueva)
		else:
			nueva.mkdir(parents=True)
		_copiar_encima(origen, nueva)
		if fichas.mapa_sumas(fichas.sumas_de_carpeta(nueva)) != fichas.mapa_sumas(archivos):
			_borrar(nueva)
			self.borrar_diario()
			raise ErrorComponente(_("La copia de {c} no salió completa; no se ha cambiado nada.").format(c=ficha_actual.get("nombre")))
		self._escribir_diario({**diario, "paso": "renombrando"})
		if self.antes_de_renombrar is not None:
			try:
				self.antes_de_renombrar(carpeta)
			except Exception:  # noqa: BLE001 - sacar los paneles es una ayuda, no un requisito
				log.warning("No se pudieron sacar los paneles de %s", carpeta, exc_info=True)
		existia = carpeta.is_dir()
		if existia:
			try:
				renombrar(carpeta, vieja, self.esperas)
			except ErrorRenombrar:
				_borrar(nueva)
				self.borrar_diario()
				raise
		try:
			renombrar(nueva, carpeta, self.esperas)
		except ErrorRenombrar:
			if existia:
				renombrar(vieja, carpeta, self.esperas + (8.0,))
			_borrar(nueva)
			self.borrar_diario()
			raise
		self._escribir_diario({**diario, "paso": "limpiando"})
		if existia:
			_borrar(vieja)
		self._guardar_ficha(ficha_final)
		return ficha_final

	def recuperar_diario(self) -> str:
		"""Al arrancar (antes de cargar nada): termina o deshace un ``instalando.json`` a medias (6.6, paso 7).

		Se termina si ``<carpeta>.nueva`` está completa (sus archivos tienen
		exactamente las ``sumas_nueva`` del diario); si no, vuelve ``<carpeta>.vieja``.
		Devuelve el mensaje para la persona (vacío si no había diario).
		"""
		if not self.entorno.diario.is_file():
			return ""
		try:
			diario = json.loads(self.entorno.diario.read_text(encoding="utf-8"))
			carpeta = self.entorno.bin / str(diario["carpeta"])
			if Path(diario["carpeta"]).name != diario["carpeta"] or diario["carpeta"] in ("", ".", ".."):
				raise ValueError("carpeta no válida")
		except (OSError, ValueError, KeyError, TypeError):
			log.exception("Diario de componentes ilegible; se descarta")
			self.borrar_diario()
			return ""
		nueva = carpeta.with_name(carpeta.name + ".nueva")
		vieja = carpeta.with_name(carpeta.name + ".vieja")
		esperadas = {str(k).casefold(): str(v).lower() for k, v in (diario.get("sumas_nueva") or {}).items()}
		nombre = str((diario.get("ficha_nueva") or {}).get("nombre") or diario.get("id"))
		mensaje = ""
		if nueva.is_dir() and fichas.mapa_sumas(fichas.sumas_de_carpeta(nueva)) == esperadas:
			if carpeta.is_dir():
				if vieja.is_dir():
					_borrar(vieja)
				renombrar(carpeta, vieja, self.esperas)
			renombrar(nueva, carpeta, self.esperas)
			_borrar(vieja)
			self._guardar_ficha(diario["ficha_nueva"])
			mensaje = _("Se terminó de instalar {c} {v}, que había quedado a medias.").format(c=nombre, v=diario.get("version_nueva", ""))
		else:
			_borrar(nueva)
			if not carpeta.is_dir() and vieja.is_dir():
				renombrar(vieja, carpeta, self.esperas)
				mensaje = _("Se deshizo la instalación de {c} que había quedado a medias; sigue la versión {v}.").format(
					c=nombre, v=diario.get("version_anterior", ""))
			elif carpeta.is_dir():
				_borrar(vieja)
				if fichas.mapa_sumas(fichas.sumas_de_carpeta(carpeta)) == esperadas:
					self._guardar_ficha(diario["ficha_nueva"])
				elif diario.get("ficha_anterior"):
					self._guardar_ficha(diario["ficha_anterior"])
		self.borrar_diario()
		log.info("Diario de componentes recuperado: %s", mensaje or "nada que hacer")
		return mensaje

	# Pendientes ------------------------------------------------------------------

	def dejar_pendiente(self, ficha_actual: dict, ficha_nueva: dict, origen: Path, *, mezclar: bool) -> Resultado:
		"""Deja lo nuevo en ``data/bin/.pendiente/<id>/`` para el arranque siguiente (6.6, paso 5)."""
		destino = self.entorno.pendiente / ficha_actual["id"]
		if origen.resolve() != (destino / "archivos").resolve():
			_borrar(destino)
			shutil.copytree(origen, destino / "archivos")
		(destino / "pendiente.json").write_text(json.dumps(
			{"ficha_nueva": ficha_nueva, "version_anterior": ficha_actual.get("version", ""), "mezclar": mezclar},
			ensure_ascii=False, indent="\t"), encoding="utf-8")
		nombre = ficha_actual.get("nombre", ficha_actual["id"])
		log.info("%s %s queda pendiente para el reinicio", nombre, ficha_nueva.get("version"))
		return Resultado(ficha_actual["id"], PENDIENTE,
			_("{c} {v} se aplicará al reiniciar zCommander.").format(c=nombre, v=ficha_nueva.get("version", "")), str(ficha_nueva.get("version", "")))

	def pendientes(self) -> list[str]:
		raiz = self.entorno.pendiente
		return sorted(p.name for p in raiz.iterdir() if (p / "pendiente.json").is_file()) if raiz.is_dir() else []

	def aplicar_pendiente(self, id: str) -> Resultado:
		"""Pasos 6 a 8 de lo que quedó pendiente (al arrancar, sin «en uso»: aún no corre nada)."""
		carpeta = self.entorno.pendiente / id
		try:
			datos = json.loads((carpeta / "pendiente.json").read_text(encoding="utf-8"))
			ficha_nueva = datos["ficha_nueva"]
		except (OSError, ValueError, KeyError):
			log.exception("Pendiente ilegible de %s; se descarta", id)
			_borrar(carpeta)
			return Resultado(id, FALLIDO, _("Se descartó una actualización pendiente de {c} que no se podía leer.").format(c=id))
		actual = self.ficha(id) or ficha_nueva
		resultado = self.instalar_preparado(actual, ficha_nueva, carpeta / "archivos", mezclar=bool(datos.get("mezclar", True)),
			con_en_uso=False)
		if resultado.estado != PENDIENTE:
			_borrar(carpeta)
		return resultado

	# Pasos 5 a 9 -------------------------------------------------------------------

	def instalar_preparado(self, ficha_actual: dict, ficha_nueva: dict, origen: Path, *, mezclar: bool, con_en_uso: bool = True,
			respaldar: bool = True) -> Resultado:
		"""Pasos 5 a 9 con los archivos de ``origen`` ya probados (o del respaldo)."""
		from app.services.componentes import estado

		id = ficha_actual["id"]
		nombre = ficha_actual.get("nombre", id)
		version_nueva = str(ficha_nueva.get("version", ""))
		estado.entrar_mantenimiento(id)
		try:
			if con_en_uso and not en_uso.liberar(ficha_actual, cancelacion=self.cancelacion, al_fase=self._fase,
					buscar=self.buscar_procesos):
				return self.dejar_pendiente(ficha_actual, ficha_nueva, origen, mezclar=mezclar)
			if respaldar:
				self.respaldar(ficha_actual)
			try:
				final = self.sustituir(ficha_actual, ficha_nueva, origen, mezclar=mezclar)
			except ErrorRenombrar:
				return self.dejar_pendiente(ficha_actual, ficha_nueva, origen, mezclar=mezclar)
			estado.quitar_danado(id)
			resultado = self._probar(final, self.carpeta(final), version_nueva, True)
			if not resultado.correcta:
				log.warning("%s %s no pasó la prueba tras instalarlo: %s", nombre, version_nueva, resultado.detalle)
				try:
					self._volver_al_respaldo(ficha_actual)
				except (ErrorComponente, OSError, ValueError) as error:
					log.exception("No se pudo volver a la versión anterior de %s", nombre)
					return Resultado(id, FALLIDO, _("La versión {n} de {c} no funcionó y no se pudo volver a la anterior: {e}").format(
						n=version_nueva, c=nombre, e=getattr(error, "mensaje", error)), version_nueva)
				return Resultado(id, REVERTIDO, _("La versión {n} de {c} no funcionó y se ha vuelto a la {a}. Detalles en el registro.").format(
					n=version_nueva or _("nueva"), c=nombre, a=ficha_actual.get("version", "")), str(ficha_actual.get("version", "")))
			self.borrar_diario()
			self.podar_respaldos(id)
			estado.olvidar_nueva(id, self.entorno)
			return Resultado(id, ACTUALIZADO, _("{c} actualizado a {v}").format(c=nombre, v=version_nueva), version_nueva)
		finally:
			self.borrar_diario()
			estado.salir_mantenimiento(id)

	def _volver_al_respaldo(self, ficha_anterior: dict) -> None:
		"""Vuelta atrás automática (paso 8): la copia exacta de la versión anterior y su ficha."""
		respaldo = self.entorno.respaldo / ficha_anterior["id"] / _nombre_respaldo(ficha_anterior)
		if not (respaldo / "archivos").is_dir():
			raise ErrorComponente(_("No hay copia de la versión anterior de {c}.").format(c=ficha_anterior.get("nombre")))
		datos = json.loads((respaldo / "ficha.json").read_text(encoding="utf-8"))
		actual = self.ficha(ficha_anterior["id"]) or ficha_anterior
		self.sustituir(actual, datos.get("ficha", ficha_anterior), respaldo / "archivos", mezclar=False)

	# Acciones de la persona ---------------------------------------------------------

	def actualizar(self, nueva: fuentes.VersionNueva) -> Resultado:
		"""Los pasos 1 a 9 para una versión nueva."""
		ficha = self.ficha(nueva.id)
		if ficha is None:
			return Resultado(nueva.id, FALLIDO, _("No hay ningún componente {c}.").format(c=nueva.id))
		nombre = ficha.get("nombre", nueva.id)
		try:
			nuevo = self.preparar(ficha, nueva)
			self._comprobar_cancelacion()
			version = nueva.version
			provisional = self.ficha_nueva(ficha, nueva, version)
			resultado = self._probar(provisional, nuevo, version, False)
			if not resultado.correcta:
				log.warning("%s %s no pasó la prueba antes de instalarlo: %s", nombre, nueva.texto, resultado.detalle)
				return Resultado(nueva.id, FALLIDO, _("La versión nueva de {c} no pasó la prueba ({d}); no se ha cambiado nada.").format(
					c=nombre, d=resultado.detalle))
			if not version:
				version = resultado.version or str(ficha.get("version", ""))
			self._comprobar_cancelacion()
			return self.instalar_preparado(ficha, self.ficha_nueva(ficha, nueva, version), nuevo, mezclar=True)
		except ErrorComponente as error:
			return Resultado(nueva.id, CANCELADO if self._cancelado() else FALLIDO, error.mensaje)
		finally:
			_borrar(self.entorno.temporal / nueva.id)

	def anterior(self, id: str) -> dict | None:
		"""El respaldo al que lleva «Volver a la versión anterior» (el más reciente distinto de lo activo)."""
		ficha = self.ficha(id)
		activas = fichas.mapa_sumas((ficha or {}).get("archivos", []))
		for respaldo in self.respaldos(id):
			if fichas.mapa_sumas(respaldo["ficha"].get("archivos", [])) != activas:
				return respaldo
		return None

	def volver_anterior(self, id: str) -> Resultado:
		"""«Volver a la versión anterior» (pasos 5 a 8 con los archivos del respaldo)."""
		ficha = self.ficha(id)
		respaldo = self.anterior(id)
		if ficha is None or respaldo is None:
			return Resultado(id, FALLIDO, _("No hay ninguna versión anterior guardada de {c}.").format(c=(ficha or {}).get("nombre", id)))
		return self._desde_respaldo(ficha, respaldo)

	def _desde_respaldo(self, ficha: dict, respaldo: dict) -> Resultado:
		temporal = self.entorno.temporal / ficha["id"] / "respaldo"
		_borrar(temporal)
		try:
			# El respaldo se copia primero: al sustituir, el respaldo de la versión activa puede reemplazar al podar.
			shutil.copytree(respaldo["carpeta"] / "archivos", temporal)
			resultado = self.instalar_preparado(ficha, respaldo["ficha"], temporal, mezclar=False)
		except ErrorComponente as error:
			return Resultado(ficha["id"], FALLIDO, error.mensaje)
		finally:
			_borrar(temporal)
		if resultado.estado == ACTUALIZADO:
			resultado.mensaje = _("{c} ha vuelto a la versión {v}").format(c=ficha.get("nombre", ficha["id"]), v=respaldo["ficha"].get("version", ""))
		return resultado

	def es_original(self, id: str) -> bool:
		"""¿Lo instalado es exactamente la línea base (mismas sumas)?"""
		ficha, base = self.ficha(id), self.base(id)
		if base is None:
			return True
		carpeta = self.carpeta(ficha or base)
		return bool(ficha) and carpeta.is_dir() and fichas.mapa_sumas(fichas.sumas_de_carpeta(carpeta)) == fichas.mapa_sumas(base.get("archivos", []))

	def respaldo_de_base(self, id: str) -> dict | None:
		base = self.base(id)
		if base is None:
			return None
		esperadas = fichas.mapa_sumas(base.get("archivos", []))
		return next((r for r in self.respaldos(id) if fichas.mapa_sumas(r["ficha"].get("archivos", [])) == esperadas), None)

	def necesita_descarga(self, id: str) -> bool:
		"""Restaurar la base de ``id`` exige descargarla (no está su respaldo)."""
		return not self.es_original(id) and self.respaldo_de_base(id) is None

	def restaurar_original(self, id: str, *, descargar: bool = False) -> Resultado:
		"""Vuelve a la línea base: con su respaldo o, si se borró y hay permiso, descargando su paquete exacto."""
		base = self.base(id)
		if base is None:
			return Resultado(id, FALLIDO, _("{c} no está en la línea base.").format(c=id))
		nombre = base.get("nombre", id)
		if self.es_original(id):
			return Resultado(id, SIN_CAMBIOS, _("{c} ya tiene la versión original").format(c=nombre), str(base.get("version", "")))
		ficha = self.ficha(id) or fichas.sin_campos_de_base(base)
		respaldo = self.respaldo_de_base(id)
		if respaldo is not None:
			resultado = self._desde_respaldo(ficha, respaldo)
		elif not descargar:
			return Resultado(id, FALLIDO, _("No está la copia de la versión original de {c}; hay que descargarla.").format(c=nombre))
		else:
			resultado = self.instalar_desde_base(id)
		if resultado.estado == ACTUALIZADO:
			resultado.mensaje = _("{c} ha vuelto a la versión original {v}").format(c=nombre, v=base.get("version", ""))
		return resultado

	def instalar_desde_base(self, id: str) -> Resultado:
		"""Descarga el paquete exacto de la línea base y lo instala (restaurar sin respaldo o «Instalar» un opcional)."""
		base = self.base(id)
		if base is None:
			return Resultado(id, FALLIDO, _("{c} no está en la línea base.").format(c=id))
		ficha = self.ficha(id) or fichas.sin_campos_de_base(base)
		try:
			nueva = fuentes.paquetes_de_base(base)
			nuevo = self.preparar(ficha, nueva)
			resultado = self._probar(base, nuevo, str(base.get("version", "")), False)
			if not resultado.correcta:
				return Resultado(id, FALLIDO, _("La versión original de {c} no pasó la prueba ({d}); no se ha cambiado nada.").format(
					c=base.get("nombre", id), d=resultado.detalle))
			return self.instalar_preparado(ficha, fichas.sin_campos_de_base(base), nuevo, mezclar=True,
				respaldar=self.carpeta(ficha).is_dir())
		except (ErrorComponente, fuentes.ErrorFuente) as error:
			return Resultado(id, FALLIDO, error.mensaje)
		finally:
			_borrar(self.entorno.temporal / id)


# ── Operación del motor ──────────────────────────────────────────────────────


class OperacionComponente(Operacion):
	"""Actualizar, volver atrás o restaurar varios componentes como una operación del motor (6.6).

	:param acciones: ``[(id, funcion)]``; cada ``funcion(instalador)`` devuelve un ``Resultado``.
	:param fabrica: crea el ``Instalador`` con la cancelación y las fases de esta operación.
	:param al_resultado: recibe cada ``Resultado`` en cuanto se conoce (en el hilo de la operación).
	"""

	tipo = "componentes"
	admite_pausa = False

	def __init__(self, titulo: str, acciones: list[tuple[str, Callable[[Instalador], Resultado]]],
			fabrica: Callable[..., Instalador], al_resultado: Callable[[Resultado], None] | None = None,
			al_fase: Callable[[str, str], None] | None = None) -> None:
		super().__init__()
		self.titulo = titulo
		self.acciones = acciones
		self.fabrica = fabrica
		self.al_resultado = al_resultado
		self.al_fase_externa = al_fase
		self.resultados: list[Resultado] = []

	def descripcion(self) -> str:
		return self.titulo

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.acciones))
		for id, accion in self.acciones:
			if ctx.cancelado():
				break

			def fase(texto: str, id_actual: str = id) -> None:
				self.progresar(actual=texto)
				self.historial.append(texto)
				if self.al_fase_externa is not None:
					self.al_fase_externa(id_actual, texto)

			def avance(hecho: int, total: int) -> None:
				self.progresar(bytes_actual=hecho, total_actual=max(total, 0))

			instalador = self.fabrica(cancelacion=ctx.token, al_fase=fase, al_progresar=avance)
			try:
				resultado = accion(instalador)
			except Exception as error:  # noqa: BLE001 - un componente que falla no impide los demás
				log.exception("Falló la operación del componente %s", id)
				resultado = Resultado(id, FALLIDO, _("No se pudo terminar con {c}: {e}").format(c=id, e=error))
			self.resultados.append(resultado)
			if resultado.estado in (FALLIDO, REVERTIDO):
				self.anotar_error(id, resultado.mensaje)
			self.sumar(archivos_hechos=1)
			if self.al_resultado is not None:
				self.al_resultado(resultado)
		if ctx.cancelado() and len(self.resultados) < len(self.acciones):
			self.cambiar_estado(Estado.CANCELADA)
		elif self.errores:
			self.cambiar_estado(Estado.TERMINADA_CON_ERRORES)
		else:
			self.cambiar_estado(Estado.TERMINADA)

	def resumen(self) -> str:
		if not self.resultados:
			return super().resumen()
		return ". ".join(r.mensaje for r in self.resultados)


# ── Lo que necesita el diálogo «Componentes externos» (6.5) ──────────────────


@dataclass
class Fila:
	"""Una fila del diálogo: lo que se ve en las columnas y lo que decide qué botones valen."""

	id: str
	nombre: str
	instalada: str
	nueva: str
	origen: str
	licencia: str
	usado_por: str
	nueva_version: fuentes.VersionNueva | None = None
	omitida: bool = False
	puede_volver: bool = False
	version_anterior: str = ""
	falta_opcional: bool = False
	actualizable: bool = True
	pendiente: bool = False
	prueba: str = ""

	@property
	def elegible(self) -> bool:
		"""Tiene versión nueva que se puede elegir (casilla activa, 6.5)."""
		return self.nueva_version is not None and not self.omitida and not self.pendiente


def nombre_dueno(dueno: str) -> str:
	"""«nucleo» → «Núcleo»; el id de un complemento → su nombre si está registrado."""
	if dueno in ("", "nucleo"):
		return _("Núcleo")
	try:
		from app.plugins import registro

		registrado = registro.complemento(dueno)
		if registrado is not None:
			return str(registrado.manifiesto.nombre)
	except Exception:  # noqa: BLE001 - sin registro se muestra el id
		log.debug("No se pudo leer el nombre del complemento %s", dueno, exc_info=True)
	return dueno


class GestorComponentes:
	"""Fachada sin wx para el diálogo y las órdenes: filas, comprobar, omitir e instaladores."""

	def __init__(self, entorno: Entorno | None = None, config_red: red.ConfiguracionRed | None = None) -> None:
		from app.core.version import APP_VERSION, NOMBRE_APLICACION

		self.entorno = entorno or Entorno.actual()
		self.config_red = config_red or red.ConfiguracionRed(NOMBRE_APLICACION, APP_VERSION)
		self.errores: dict[str, str] = {}
		self.pruebas: dict[str, str] = {}
		#: Opciones fijas de cada ``Instalador`` (las pruebas ponen un lanzador falso y esperas cortas).
		self.opciones_instalador: dict[str, Any] = {}

	def instalador(self, **opciones: Any) -> Instalador:
		return Instalador(self.entorno, self.config_red, **{**self.opciones_instalador, **opciones})

	def nuevas(self) -> dict[str, fuentes.VersionNueva]:
		from app.services.componentes import estado

		datos = estado.leer_estado(self.entorno)
		resultado = {}
		for id, nueva in datos.get("nuevas", {}).items():
			try:
				resultado[id] = fuentes.VersionNueva.de_dict(nueva)
			except (TypeError, ValueError):
				log.warning("Versión nueva guardada ilegible para %s", id, exc_info=True)
		return resultado

	def filas(self) -> list[Fila]:
		from app.services.componentes import estado

		datos = estado.leer_estado(self.entorno)
		omitidas = datos.get("omitidas", {})
		nuevas = self.nuevas()
		instalador = self.instalador()
		lista = []
		vistos = set()
		todas = [*estado.instalados(self.entorno).get("componentes", []), *estado.linea_base(self.entorno).get("componentes", [])]
		for ficha in todas:
			if not isinstance(ficha, dict) or not ficha.get("id") or ficha["id"] in vistos:
				continue
			id = ficha["id"]
			vistos.add(id)
			nueva = nuevas.get(id)
			omitida = nueva is not None and omitidas.get(id) == nueva.texto
			origen = estado.origen_de(id, self.entorno)
			anterior = instalador.anterior(id)
			carpeta = self.entorno.bin / str(ficha.get("carpeta") or id)
			if not ficha.get("actualizable", True):
				origen = _("Lo genera zCommander") if carpeta.is_dir() else _("Falta")
			if nueva is None:
				texto_nueva = "—"
			elif omitida:
				texto_nueva = _("{v} (omitida)").format(v=nueva.texto)
			else:
				texto_nueva = nueva.texto
			lista.append(Fila(
				id=id, nombre=str(ficha.get("nombre") or id), instalada=str(ficha.get("version", "")) if carpeta.is_dir() else "—",
				nueva=texto_nueva, origen=origen, licencia=str(ficha.get("licencia", "")),
				usado_por=nombre_dueno(str(ficha.get("dueno", ""))), nueva_version=nueva, omitida=omitida,
				puede_volver=anterior is not None, version_anterior=str((anterior or {}).get("ficha", {}).get("version", "")),
				falta_opcional=bool(ficha.get("opcional")) and not carpeta.is_dir() and bool(ficha.get("actualizable", True)),
				actualizable=bool(ficha.get("actualizable", True)), pendiente=(self.entorno.pendiente / id).is_dir(),
				prueba=self.pruebas.get(id, "")))
		return lista

	def comprobar(self, cancelacion: Any = None) -> dict[str, fuentes.VersionNueva]:
		"""Busca versiones nuevas de los componentes actualizables (una petición por componente) y lo guarda."""
		from app.services.componentes import estado

		nuevas: dict[str, fuentes.VersionNueva] = {}
		self.errores = {}
		for ficha in estado.instalados(self.entorno).get("componentes", []):
			if en_uso._cancelado(cancelacion):
				break
			if not isinstance(ficha, dict) or not ficha.get("actualizable", True) or not ficha.get("fuente"):
				continue
			if not (self.entorno.bin / str(ficha.get("carpeta") or ficha["id"])).is_dir():
				continue
			try:
				nueva = fuentes.comprobar(ficha, self.config_red)
			except fuentes.ErrorFuente as error:
				self.errores[ficha["id"]] = error.mensaje
				continue
			if nueva is not None:
				nuevas[ficha["id"]] = nueva
		estado.anotar_comprobacion({id: n.a_dict() for id, n in nuevas.items()}, self.entorno)
		return nuevas

	def novedades_sin_omitir(self) -> list[str]:
		"""Ids con versión nueva que la persona no ha omitido (lo que anuncia la comprobación periódica)."""
		from app.services.componentes import estado

		omitidas = estado.leer_estado(self.entorno).get("omitidas", {})
		return [id for id, nueva in self.nuevas().items() if omitidas.get(id) != nueva.texto]

	def omitir(self, id: str) -> bool:
		from app.services.componentes import estado

		nueva = self.nuevas().get(id)
		if nueva is None:
			return False
		estado.omitir(id, nueva.texto, self.entorno)
		return True

	def cambios_restaurar(self) -> list[tuple[str, str, str, str]]:
		"""``[(id, nombre, versión instalada, versión original)]`` de lo que cambiaría «Restaurar los componentes originales»."""
		from app.services.componentes import estado

		instalador = self.instalador()
		cambios = []
		for base in estado.linea_base(self.entorno).get("componentes", []):
			if not isinstance(base, dict) or not base.get("actualizable", True) or not base.get("id"):
				continue
			if base.get("opcional") and not (self.entorno.bin / str(base.get("carpeta") or base["id"])).is_dir():
				continue
			if not instalador.es_original(base["id"]):
				ficha = estado.ficha_instalada(base["id"], self.entorno) or {}
				cambios.append((base["id"], str(base.get("nombre") or base["id"]), str(ficha.get("version") or "—"), str(base.get("version", ""))))
		return cambios

	def detalles(self, fila: Fila) -> str:
		"""Texto de «Detalles»: novedades, tamaño de la descarga, aviso de cambio grande, prueba y errores."""
		from app.services import formato

		partes = [_("{n}: instalada {i}, origen {o}, licencia {l}, la usa {u}.").format(
			n=fila.nombre, i=fila.instalada, o=fila.origen, l=fila.licencia, u=fila.usado_por)]
		if fila.pendiente:
			partes.append(_("Tiene una actualización pendiente: se aplicará al reiniciar zCommander."))
		nueva = fila.nueva_version
		if nueva is not None:
			partes.append(_("Versión nueva: {v}.").format(v=nueva.texto))
			if nueva.tamano:
				partes.append(_("Tamaño de la descarga: {t}.").format(t=formato.tamano_legible(nueva.tamano)))
			if nueva.cambio_grande:
				partes.append(_("Cambio grande: puede cambiar su comportamiento."))
			if fila.omitida:
				partes.append(_("Ha omitido esta versión: no se le volverá a avisar de ella."))
			if nueva.novedades:
				partes.append(_("Novedades:") + "\n" + nueva.novedades)
		elif fila.actualizable:
			partes.append(_("No se conoce ninguna versión nueva."))
		if fila.puede_volver:
			partes.append(_("Hay una copia de la versión anterior ({v}).").format(v=fila.version_anterior))
		if fila.prueba:
			partes.append(_("Prueba: {p}").format(p=fila.prueba))
		if fila.id in self.errores:
			partes.append(_("No se pudo comprobar: {e}").format(e=self.errores[fila.id]))
		return "\n\n".join(partes)
