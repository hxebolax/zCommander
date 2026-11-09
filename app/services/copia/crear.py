# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Crear una copia ``.zcbackup`` (diseño 2.0, 7.5); también el ``.zcperfil`` y las copias automáticas. Sin wx.

Qué hace ``crear_copia``:

1. Junta lo de cada parte con ``formato.incluye`` (la misma regla que acepta
   las rutas al restaurar) y, para preferencias, teclas y complementos, los
   valores de ``settings.json`` en ``valores.json`` (sin las claves de
   confianza ni ``seguridad.*``, que no salen nunca del equipo).
2. Para la parte ``complementos`` empaqueta cada complemento instalado por la
   persona (``data/plugins/<id>/``) como ``.zcplugin``, con su firma si la
   tenía; al restaurar se ofrece por la instalación normal (nunca se copia).
3. Escribe el ZIP en un ``.parcial`` y lo renombra al final: una copia
   cancelada o fallida no deja un archivo a medias con el nombre bueno.
"""

from __future__ import annotations

import builtins
import copy as copia_modulo
import hashlib
import io
import json
import logging
import os
import tomllib
import zipfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core import paths, version
from app.services.copia import cifrado, formato
from app.services.copia.formato import ErrorCopia

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


Progreso = Callable[[int, int], None]

CARPETA_AUTOMATICAS = "automaticas"
CONSERVAR_POR_DEFECTO = 5


def _cancelado(cancelacion: Any) -> bool:
	if cancelacion is None:
		return False
	for nombre in ("is_set", "cancelado"):
		metodo = getattr(cancelacion, nombre, None)
		if callable(metodo):
			return bool(metodo())
	return bool(cancelacion() if callable(cancelacion) else cancelacion)


def _comprobar(cancelacion: Any) -> None:
	if _cancelado(cancelacion):
		from app.services.vfs.base import Cancelado

		raise Cancelado()


# ── Qué hay en data ───────────────────────────────────────────────────────────

_RAICES = {"teclas": ("config",), "sesion": ("config",), "personalizacion": ("config", "plantillas"),
	"conexiones": ("config",), "complementos": ("config",), "sonidos": ("sounds_usuario",), "macros": ("config",),
	"registros": ("logs",)}


def archivos_de_parte(parte: str, ruta_datos: Path) -> list[tuple[str, Path]]:
	"""(ruta relativa a ``data``, ruta real) de los archivos de ``parte`` que hay en este equipo."""
	encontrados: list[tuple[str, Path]] = []
	ruta_datos = Path(ruta_datos)
	for raiz in _RAICES.get(parte, ()):
		carpeta = ruta_datos / raiz
		if not carpeta.is_dir():
			continue
		for actual, carpetas, nombres in os.walk(carpeta):
			# No se baja a carpetas ocultas (la restauración pendiente) ni a __pycache__.
			carpetas[:] = sorted(c for c in carpetas if not c.startswith(".") and c != "__pycache__")
			for nombre in sorted(nombres):
				real = Path(actual) / nombre
				relativa = formato.ruta_relativa(real, ruta_datos)
				if formato.incluye(parte, relativa) and real.is_file():
					encontrados.append((relativa, real))
	return encontrados


def leer_settings(ruta_datos: Path) -> dict:
	"""``settings.json`` tal como está en el disco ({} si falta o está dañado)."""
	ruta = Path(ruta_datos) / "config" / "settings.json"
	try:
		datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
	except FileNotFoundError:
		return {}
	except (OSError, ValueError):
		log.warning("No se pudo leer %s para la copia", ruta, exc_info=True)
		return {}
	return datos if isinstance(datos, dict) else {}


def valores_actuales(ruta_datos: Path) -> dict[str, Any]:
	"""Todas las claves «seccion.clave» vigentes: las de fábrica con lo del archivo encima."""
	from app.core.configuracion import VALORES_POR_DEFECTO

	datos = copia_modulo.deepcopy(VALORES_POR_DEFECTO)
	for seccion, claves in leer_settings(ruta_datos).items():
		if isinstance(claves, dict):
			datos.setdefault(seccion, {}).update(claves)
	return {f"{s}.{c}": v for s, claves in datos.items() if isinstance(claves, dict) for c, v in claves.items()}


def valores_de_parte(parte: str, ruta_datos: Path) -> dict[str, Any]:
	return {k: v for k, v in valores_actuales(ruta_datos).items() if formato.parte_de_clave(k) == parte}


def _almacen(ruta_datos: Path):
	from app.core.secretos import NOMBRE_ARCHIVO, AlmacenSecretos

	return AlmacenSecretos(Path(ruta_datos) / "config" / NOMBRE_ARCHIVO)


def prefijos_secretos(parte: str) -> tuple[str, ...]:
	if parte == "conexiones":
		return formato.SECRETOS_CONEXIONES
	if parte == "complementos":
		return ("plugin:",)
	return ()


def secreto_de_parte(nombre: str, parte: str) -> bool:
	if parte == "complementos":
		return nombre.startswith("plugin:") and not nombre.startswith(formato.SECRETOS_CONEXIONES)
	return nombre.startswith(prefijos_secretos(parte)) if prefijos_secretos(parte) else False


def secretos_de_partes(partes: Iterable[str], ruta_datos: Path) -> dict[str, str]:
	partes = [p for p in partes if prefijos_secretos(p)]
	if not partes:
		return {}
	almacen = _almacen(ruta_datos)
	nombres = [n for n in almacen.nombres() if any(secreto_de_parte(n, p) for p in partes)]
	secretos = {}
	for nombre in nombres:
		valor = almacen.obtener(nombre)
		if valor is not None:
			secretos[nombre] = valor
	return secretos


# ── Complementos ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ComplementoInstalado:
	id: str
	version: str
	carpeta: Path


def complementos_de_usuario(ruta_datos: Path) -> list[ComplementoInstalado]:
	"""Los complementos de ``data/plugins/<carpeta>`` con un manifiesto legible."""
	carpeta = Path(ruta_datos) / "plugins"
	resultado = []
	if not carpeta.is_dir():
		return resultado
	for hijo in sorted(carpeta.iterdir()):
		if not hijo.is_dir() or hijo.name.startswith("."):
			continue
		try:
			with (hijo / "manifiesto.toml").open("rb") as archivo:
				datos = tomllib.load(archivo)
		except (OSError, tomllib.TOMLDecodeError):
			log.debug("Sin manifiesto legible en %s; no se copia", hijo, exc_info=True)
			continue
		id_complemento, version_complemento = datos.get("id"), datos.get("version")
		if isinstance(id_complemento, str) and isinstance(version_complemento, str) and id_complemento:
			resultado.append(ComplementoInstalado(id_complemento, version_complemento, hijo))
	return resultado


def empaquetar_complemento(carpeta: Path) -> bytes:
	"""``.zcplugin``: el contenido de la carpeta en la raíz del ZIP (3.3), con su firma si la tiene."""
	salida = io.BytesIO()
	with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zf:
		for actual, carpetas, nombres in os.walk(carpeta):
			carpetas[:] = sorted(c for c in carpetas if c != "__pycache__")
			for nombre in sorted(nombres):
				if nombre.endswith((".pyc", ".pyo")):
					continue
				real = Path(actual) / nombre
				zf.write(real, formato.ruta_relativa(real, carpeta))
	return salida.getvalue()


def lista_complementos(ruta_datos: Path) -> dict:
	from app.plugins import serie

	instalados = [{"id": c.id, "version": c.version, "serie": False} for c in complementos_de_usuario(ruta_datos)]
	propios = {c["id"] for c in instalados}
	instalados += [{"id": i, "version": v, "serie": True} for i, v in sorted(serie.SERIE.items()) if i not in propios]
	return {"version": 1, "instalados": instalados}


# ── Tamaños para el diálogo ───────────────────────────────────────────────────

def tamano_partes(ruta_datos: Path | None = None) -> dict[str, int]:
	"""Tamaño aproximado de cada parte en este equipo (para «Qué guardar»)."""
	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	tamanos: dict[str, int] = {}
	for parte in formato.PARTES:
		total = 0
		for _relativa, real in archivos_de_parte(parte, ruta_datos):
			try:
				total += real.stat().st_size
			except OSError:
				log.debug("No se pudo medir %s", real, exc_info=True)
		if parte == "complementos":
			for complemento in complementos_de_usuario(ruta_datos):
				for real in complemento.carpeta.rglob("*"):
					if real.is_file():
						total += real.stat().st_size
		if parte in ("preferencias", "teclas", "complementos"):
			total += len(json.dumps(valores_de_parte(parte, ruta_datos), ensure_ascii=False).encode("utf-8"))
		tamanos[parte] = total
	return tamanos


# ── Crear ─────────────────────────────────────────────────────────────────────

@dataclass
class _Elemento:
	parte: str
	ruta: str
	real: Path | None = None
	datos: bytes | None = None

	def tamano(self) -> int:
		if self.datos is not None:
			return len(self.datos)
		try:
			return self.real.stat().st_size if self.real else 0
		except OSError:
			return 0


def _elementos(partes: Sequence[str], ruta_datos: Path, cancelacion: Any) -> list[_Elemento]:
	elementos: list[_Elemento] = []
	for parte in partes:
		_comprobar(cancelacion)
		if parte in ("preferencias", "teclas", "complementos"):
			valores = valores_de_parte(parte, ruta_datos)
			elementos.append(_Elemento(parte, formato.VALORES,
				datos=json.dumps(valores, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")))
		for relativa, real in archivos_de_parte(parte, ruta_datos):
			elementos.append(_Elemento(parte, relativa, real=real))
		if parte == "complementos":
			elementos.append(_Elemento(parte, formato.LISTA_COMPLEMENTOS,
				datos=json.dumps(lista_complementos(ruta_datos), ensure_ascii=False, indent=1).encode("utf-8")))
			for complemento in complementos_de_usuario(ruta_datos):
				_comprobar(cancelacion)
				nombre = f"{formato.PAQUETES}{complemento.id}.zcplugin"
				if formato.especial_permitido(parte, nombre):
					elementos.append(_Elemento(parte, nombre, datos=empaquetar_complemento(complemento.carpeta)))
				else:
					log.warning("El complemento %s tiene un id que no sirve como nombre de paquete; no se copia", complemento.id)
	return elementos


def _copiar_al_zip(zf: zipfile.ZipFile, elemento: _Elemento, hechos: list[int], total: int,
		progreso: Progreso | None, cancelacion: Any) -> dict:
	suma = hashlib.sha256()
	tamano = 0
	with zf.open(formato.miembro(elemento.parte, elemento.ruta), "w", force_zip64=True) as salida:
		if elemento.datos is not None:
			fuentes: Iterable[bytes] = (elemento.datos,)
		else:
			fuentes = _bloques(elemento.real)
		for bloque in fuentes:
			_comprobar(cancelacion)
			salida.write(bloque)
			suma.update(bloque)
			tamano += len(bloque)
			hechos[0] += len(bloque)
			if progreso is not None:
				progreso(hechos[0], max(total, hechos[0]))
	return {"ruta": elemento.ruta, "sha256": suma.hexdigest(), "tamano": tamano}


def _bloques(ruta: Path | None):
	if ruta is None:
		return
	with open(ruta, "rb") as entrada:
		while bloque := entrada.read(formato.BLOQUE):
			yield bloque


def nombre_por_defecto(tipo: str = "copia", fecha: datetime | None = None) -> str:
	fecha = fecha or datetime.now()
	if tipo == "perfil":
		return f"zCommander-{fecha:%Y-%m-%d}{formato.EXTENSION_PERFIL}"
	return f"zCommander-{fecha:%Y-%m-%d}{formato.EXTENSION}"


def crear_copia(destino: Path, partes: Sequence[str], tipo: str, modo_secretos: str, contrasena: str | None,
		descripcion: str, progreso: Progreso | None = None, cancelacion: Any = None, *,
		ruta_datos: Path | None = None) -> Path:
	"""Crea la copia en ``destino`` y la devuelve. Lanza ``ErrorCopia`` (mensaje en español) o ``Cancelado``.

	:param partes: ids de 7.2 (las desconocidas se rechazan).
	:param tipo: ``copia``, ``automatica`` o ``perfil``.
	:param modo_secretos: ``contrasena`` (necesita ``contrasena``), ``dpapi`` (solo automáticas) o ``excluidos``.
	:param progreso: ``progreso(hechos, total)`` en bytes, desde el hilo que crea.
	:param cancelacion: objeto con ``is_set()`` (o ``cancelado()``), o una función.
	"""
	destino = Path(destino)
	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	if tipo not in formato.TIPOS:
		raise ErrorCopia(_("Tipo de copia desconocido: {t}").format(t=tipo))
	partes = [p for p in formato.PARTES if p in set(partes)]
	if not partes:
		raise ErrorCopia(_("Elija al menos una parte para guardar."))
	if tipo == "perfil":
		# Un perfil nunca lleva secretos ni conexiones (10.2).
		partes = [p for p in partes if p in formato.PARTES_PERFIL]
		modo_secretos = "excluidos"
	if modo_secretos not in formato.MODOS_SECRETOS or (modo_secretos == "dpapi" and tipo != "automatica"):
		raise ErrorCopia(_("Modo de contraseñas no válido para esta copia."))
	if modo_secretos == "contrasena" and not contrasena:
		raise ErrorCopia(_("Escriba la contraseña de la copia."))

	secretos = secretos_de_partes(partes, ruta_datos) if modo_secretos != "excluidos" else {}
	if not secretos:
		modo_secretos = "excluidos"
	elementos = _elementos(partes, ruta_datos, cancelacion)
	total = sum(e.tamano() for e in elementos)
	destino.parent.mkdir(parents=True, exist_ok=True)
	parcial = destino.with_name(destino.name + ".parcial")
	hechos = [0]
	manifiesto: dict[str, Any] = {
		"formato": formato.FORMATO, "tipo": tipo, "app": formato.APP, "version_app": version.APP_VERSION,
		"version_esquema": _version_esquema(ruta_datos), "fecha": datetime.now().isoformat(timespec="seconds"),
		"descripcion": descripcion.strip(), "partes": {p: {"archivos": []} for p in partes},
	}
	try:
		with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as zf:
			for elemento in elementos:
				_comprobar(cancelacion)
				try:
					fila = _copiar_al_zip(zf, elemento, hechos, total, progreso, cancelacion)
				except OSError as error:
					raise ErrorCopia(_("No se pudo leer {r}: {e}").format(r=elemento.ruta, e=error.strerror or error)) from error
				manifiesto["partes"][elemento.parte]["archivos"].append(fila)
			if modo_secretos == "excluidos":
				manifiesto["secretos"] = {"modo": "excluidos"}
			else:
				manifiesto["secretos"] = {"modo": modo_secretos, "nombres": sorted(secretos)}
				if modo_secretos == "contrasena":
					manifiesto["secretos"].update({"kdf": cifrado.parametros_kdf(), "cifrado": cifrado.CIFRADO})
					contenido = cifrado.cifrar(secretos, contrasena or "", manifiesto)
				else:
					contenido = cifrado.proteger_dpapi(secretos, manifiesto)
				zf.writestr(formato.SECRETOS, contenido)
			zf.writestr(formato.MANIFIESTO, json.dumps(manifiesto, ensure_ascii=False, indent=1))
		os.replace(parcial, destino)
	except BaseException:
		try:
			parcial.unlink(missing_ok=True)
		except OSError:
			log.debug("No se pudo borrar %s", parcial, exc_info=True)
		raise
	log.info("Copia %s creada en %s: partes %s, secretos %s", tipo, destino, ", ".join(partes), modo_secretos)
	return destino


def _version_esquema(ruta_datos: Path) -> int:
	from app.core.configuracion import VERSION_ESQUEMA

	valor = leer_settings(ruta_datos).get("version_esquema", VERSION_ESQUEMA)
	return valor if isinstance(valor, int) and not isinstance(valor, bool) else VERSION_ESQUEMA


# ── Copias automáticas ────────────────────────────────────────────────────────

def carpeta_automaticas(ruta_datos: Path) -> Path:
	return Path(ruta_datos) / "backups" / CARPETA_AUTOMATICAS


def _conservar(ruta_datos: Path) -> int:
	valor = leer_settings(ruta_datos).get("copia", {})
	numero = valor.get("conservar_automaticas", CONSERVAR_POR_DEFECTO) if isinstance(valor, dict) else CONSERVAR_POR_DEFECTO
	return numero if isinstance(numero, int) and not isinstance(numero, bool) and numero >= 1 else CONSERVAR_POR_DEFECTO


def crear_automatica(partes: Sequence[str], ruta_datos: Path | None = None) -> Path:
	"""Copia automática previa a restaurar (7.6): las mismas partes, secretos con DPAPI."""
	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	carpeta = carpeta_automaticas(ruta_datos)
	base = f"antes-de-restaurar-{datetime.now():%Y%m%d-%H%M%S}"
	destino = carpeta / f"{base}{formato.EXTENSION}"
	numero = 2
	while destino.exists():
		destino = carpeta / f"{base}-{numero}{formato.EXTENSION}"
		numero += 1
	partes = [p for p in partes if formato.PARTES[p].aplicacion != formato.EXTRAER] or ["preferencias"]
	crear_copia(destino, partes, "automatica", "dpapi", None, _("Antes de restaurar"), ruta_datos=ruta_datos)
	podar_automaticas(ruta_datos)
	return destino


def podar_automaticas(ruta_datos: Path, conservar: int | None = None) -> list[Path]:
	"""Borra las copias automáticas más antiguas y deja las ``copia.conservar_automaticas`` más recientes."""
	conservar = conservar if conservar is not None else _conservar(ruta_datos)
	carpeta = carpeta_automaticas(ruta_datos)
	if not carpeta.is_dir():
		return []
	copias = sorted(carpeta.glob(f"antes-de-restaurar-*{formato.EXTENSION}"), key=lambda r: (r.stat().st_mtime, r.name),
		reverse=True)
	borradas = []
	for vieja in copias[conservar:]:
		try:
			vieja.unlink()
			borradas.append(vieja)
		except OSError:
			log.warning("No se pudo borrar la copia automática %s", vieja, exc_info=True)
	return borradas
