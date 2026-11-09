# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Formato ``.zcbackup`` (diseño 2.0, 7.2 y 7.3): partes, manifiesto y lectura segura. Sin wx.

Una copia es un ZIP con ``manifiesto.json``, los archivos de cada parte en
``partes/<id>/<ruta relativa a data>`` y, si lleva contraseñas, ``secretos.bin``.

Por qué está así:

- **Qué entra en cada parte lo decide una única función** (``incluye``), que
  usan tanto la creación (qué archivos de ``data`` se copian) como la
  restauración (qué rutas de una copia se aceptan). Así una copia ajena no
  puede escribir fuera de lo que su parte permite: ni ``data/plugins`` ni
  ``config/plugins/claves.json`` ni ``../`` (copia ajena = datos no confiables).
- **El ZIP se lee con límites** (número de miembros, tamaño por miembro y
  total) y cada archivo se compara con su suma del manifiesto; uno que no
  coincide anula su parte, no la copia entera (7.3).
- **Manifiesto canónico** (7.4): los datos asociados del cifrado son el SHA-256
  del manifiesto sin ``secretos.nombres`` serializado siempre igual, así no
  dependen del orden de las claves ni de los bytes exactos del ZIP.
"""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from app.core import version

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


FORMATO = 1
EXTENSION = ".zcbackup"
EXTENSION_PERFIL = ".zcperfil"
APP = "zCommander"
TIPOS = ("copia", "automatica", "perfil")
MODOS_SECRETOS = ("contrasena", "dpapi", "excluidos")

MANIFIESTO = "manifiesto.json"
SECRETOS = "secretos.bin"
PREFIJO_PARTES = "partes/"
VALORES = "valores.json"
LISTA_COMPLEMENTOS = "lista.json"
PAQUETES = "paquetes/"

# Límites de lectura (una copia ajena puede ser hostil: bomba ZIP, miles de miembros).
MAX_MIEMBROS = 50_000
MAX_MIEMBRO = 1024 * 1024 * 1024
MAX_TOTAL = 4 * 1024 * 1024 * 1024
MAX_MANIFIESTO = 16 * 1024 * 1024
BLOQUE = 1024 * 1024

#: Cómo se aplica cada parte (7.2): al momento, al reiniciar o solo se extrae.
MOMENTO, REINICIO, EXTRAER = "momento", "reinicio", "extraer"


@dataclass(frozen=True)
class Parte:
	id: str
	nombre: str
	aplicacion: str
	descripcion: str


#: Las partes de 7.2, en el orden del diálogo.
PARTES: dict[str, Parte] = {p.id: p for p in (
	Parte("preferencias", N_("Preferencias"), REINICIO, N_("Todas las preferencias salvo las teclas y la ventana.")),
	Parte("teclas", N_("Perfiles y mapa de teclas"), REINICIO, N_("Teclas personalizadas, esquema y perfiles propios.")),
	Parte("sesion", N_("Sesión e historiales"), REINICIO, N_("Carpetas y pestañas abiertas, historiales, cesta, espacios de trabajo y paleta.")),
	Parte("personalizacion", N_("Favoritos, menú de usuario, asociaciones y plantillas"), MOMENTO,
		N_("Favoritos, menú de usuario, asociaciones, plantillas, búsquedas, menús, vistas, reglas y alias.")),
	Parte("conexiones", N_("Conexiones (FTP, SFTP, WebDAV, nubes y NAS)"), REINICIO,
		N_("Sitios guardados, huellas de servidores, cuentas de nube y NAS, y sus contraseñas si se incluyen.")),
	Parte("complementos", N_("Complementos instalados y su configuración"), REINICIO,
		N_("Los complementos instalados, su estado y su configuración; los paquetes se ofrecen para instalar.")),
	Parte("sonidos", N_("Paquetes de sonidos propios"), MOMENTO, N_("Los paquetes de sonidos creados o importados.")),
	Parte("macros", N_("Macros"), MOMENTO, N_("Las macros grabadas.")),
	Parte("registros", N_("Registros (para soporte)"), EXTRAER, N_("Los registros de la aplicación; no se restauran, solo se extraen.")),
)}

#: Partes que puede llevar un ``.zcperfil`` (10.2): nunca secretos ni conexiones.
PARTES_PERFIL = ("preferencias", "teclas", "personalizacion", "macros", "sonidos")
PARTES_POR_DEFECTO = ("preferencias", "teclas", "sesion", "personalizacion", "conexiones", "complementos", "sonidos", "macros")

# ── Qué archivo es de qué parte ─────────────────────────────────────────────

ARCHIVOS_SESION = frozenset({"config/sesion.json", "config/espacios.json", "config/paleta.json"})
ARCHIVOS_PERSONALIZACION = frozenset({
	"config/favoritos.json", "config/menu_usuario.json", "config/asociaciones.json", "config/plantillas_renombrado.json",
	"config/busquedas.json", "config/menus.json", "config/vistas_carpeta.json", "config/reglas.json", "config/alias.json",
})
ARCHIVOS_CONEXIONES = frozenset({
	"config/conexiones.json", "config/hosts_conocidos.json", "config/known_hosts", "config/rclone.conf", "config/red.json",
})
CARPETAS_CONEXIONES = ("config/plugins/zc.nubes/", "config/plugins/zc.synology/")
RCLONE_CONF = "config/rclone.conf"
CARPETA_NUBES = "config/plugins/zc.nubes/"
CUENTAS_NUBES = "config/plugins/zc.nubes/cuentas.json"
KNOWN_HOSTS = "config/known_hosts"
HOSTS_TLS = "config/hosts_conocidos.json"
ARCHIVO_CLAVES = "config/plugins/claves.json"
CARPETA_PROGRAMADOR = "config/plugins/zc.programador/"

#: Prefijos de ``secretos.dat`` de cada parte (7.2); el resto de secretos no viaja.
SECRETOS_CONEXIONES = ("ftp:", "plugin:zc.nubes:", "plugin:zc.synology:")
SECRETOS_NUBES = "plugin:zc.nubes:"

# ── Claves de settings.json de cada parte ───────────────────────────────────

#: Claves que nunca viajan: la confianza se decide en cada equipo (3.9, 7.2).
CLAVES_CONFIANZA = frozenset({
	"complementos.permitir_sin_firma", "complementos.auditoria", "complementos.modo_desarrollo", "complementos.confiados",
})
SECCIONES_FUERA = frozenset({"ventana", "seguridad"})
CLAVES_COMPLEMENTOS = frozenset({"complementos.inhabilitados", "complementos.fallos_maximos"})

#: Claves de complementos de serie que hacen ejecutar algo aunque su manifiesto aún no lo diga (7.2).
EJECUTA_COMPLEMENTOS: dict[str, frozenset[str]] = {
	"zc.monitor": frozenset({"carpetas", "reglas"}),
}

#: Opciones de un remoto de rclone que hacen ejecutar un programa (7.2).
OPCIONES_RCLONE_EJECUTAN = frozenset({"bearer_token_command", "ssh"})


def clave_prohibida(clave: str) -> bool:
	"""Las claves de confianza y ``seguridad.*`` no se guardan ni se restauran nunca (7.2)."""
	return clave in CLAVES_CONFIANZA or clave.split(".", 1)[0] == "seguridad"


def parte_de_clave(clave: str) -> str | None:
	"""Parte de una clave «seccion.clave» de ``settings.json`` (``None`` si no viaja en ninguna)."""
	seccion = clave.split(".", 1)[0]
	if clave_prohibida(clave) or seccion in SECCIONES_FUERA or clave == "version_esquema":
		return None
	if seccion == "teclado":
		return "teclas"
	if seccion == "complementos":
		return "complementos" if clave in CLAVES_COMPLEMENTOS else None
	return "preferencias"


def opcion_rclone_ejecuta(nombre: str) -> bool:
	return nombre in OPCIONES_RCLONE_EJECUTAN or nombre.endswith("_command")


def _ruta_segura(ruta: str) -> bool:
	"""Ruta relativa POSIX sin unidad, sin «..», sin barras invertidas ni segmentos vacíos."""
	if not ruta or ruta.startswith("/") or "\\" in ruta or ":" in ruta or "\x00" in ruta:
		return False
	partes = ruta.split("/")
	return all(p and p not in (".", "..") and p.strip() == p for p in partes)


_SUFIJOS_TEMPORALES = (".tmp", ".bak", ".parcial")
_MARCAS_TEMPORALES = (".corrupto-", ".ilegible-")


def es_temporal(nombre: str) -> bool:
	"""Copias de seguridad sueltas, temporales y archivos apartados: no se copian."""
	bajo = nombre.lower()
	return bajo.endswith(_SUFIJOS_TEMPORALES) or any(m in bajo for m in _MARCAS_TEMPORALES)


def incluye(parte: str, ruta: str) -> bool:
	"""¿El archivo ``ruta`` (relativo a ``data``, con «/») pertenece a ``parte``? La única regla de 7.2."""
	if not _ruta_segura(ruta):
		return False
	segmentos = ruta.split("/")
	if any(s.startswith(".") or s == "__pycache__" for s in segmentos) or es_temporal(segmentos[-1]):
		return False
	if parte == "teclas":
		return len(segmentos) == 3 and ruta.startswith("config/perfiles/") and ruta.endswith(".json")
	if parte == "sesion":
		return ruta in ARCHIVOS_SESION
	if parte == "personalizacion":
		return ruta in ARCHIVOS_PERSONALIZACION or (ruta.startswith("plantillas/") and len(segmentos) > 1)
	if parte == "conexiones":
		return ruta in ARCHIVOS_CONEXIONES or any(ruta.startswith(c) and len(ruta) > len(c) for c in CARPETAS_CONEXIONES)
	if parte == "complementos":
		return (ruta.startswith("config/plugins/") and len(segmentos) > 2 and ruta != ARCHIVO_CLAVES
			and not any(ruta.startswith(c) for c in CARPETAS_CONEXIONES))
	if parte == "sonidos":
		return ruta.startswith("sounds_usuario/") and len(segmentos) > 1
	if parte == "macros":
		return ruta == "config/macros.json"
	if parte == "registros":
		return ruta.startswith("logs/") and len(segmentos) > 1 and segmentos[-1].lower() != "rclone.log"
	return False


def especial_permitido(parte: str, ruta: str) -> bool:
	"""Archivos propios de la copia que no son de ``data``: valores y paquetes de complementos."""
	if ruta == VALORES:
		return parte in ("preferencias", "teclas", "complementos")
	if parte == "complementos":
		if ruta == LISTA_COMPLEMENTOS:
			return True
		if ruta.startswith(PAQUETES):
			nombre = ruta[len(PAQUETES):]
			return "/" not in nombre and nombre.endswith(".zcplugin") and _ruta_segura(nombre) and len(nombre) > 9
	return False


def es_especial(ruta: str) -> bool:
	return ruta in (VALORES, LISTA_COMPLEMENTOS) or ruta.startswith(PAQUETES)


def ruta_permitida(parte: str, ruta: str) -> bool:
	return parte in PARTES and (especial_permitido(parte, ruta) or incluye(parte, ruta))


def miembro(parte: str, ruta: str) -> str:
	"""Nombre del miembro del ZIP de un archivo de una parte."""
	return f"{PREFIJO_PARTES}{parte}/{ruta}"


# ── Errores ──────────────────────────────────────────────────────────────────

class ErrorCopia(Exception):
	"""Error con un mensaje en español para la persona."""

	def __init__(self, mensaje: str) -> None:
		super().__init__(mensaje)
		self.mensaje = mensaje


class ErrorContrasena(ErrorCopia):
	def __init__(self, mensaje: str = "") -> None:
		super().__init__(mensaje or _("La contraseña no es correcta o la copia está dañada."))


def mensaje_no_es_copia() -> str:
	return _("El archivo no es una copia de seguridad de zCommander o está dañado.")


def mensaje_mas_nueva() -> str:
	return _("Esta copia es de una versión más nueva de zCommander; actualice primero.")


# ── Manifiesto ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ArchivoCopia:
	ruta: str
	sha256: str
	tamano: int


@dataclass(frozen=True)
class ManifiestoCopia:
	formato: int
	tipo: str
	app: str
	version_app: str
	version_esquema: int
	fecha: datetime | None
	descripcion: str
	partes: dict[str, tuple[ArchivoCopia, ...]]
	modo_secretos: str
	datos: dict[str, Any] = field(default_factory=dict, compare=False)
	avisos: tuple[str, ...] = ()

	def tamano(self, parte: str) -> int:
		return sum(a.tamano for a in self.partes.get(parte, ()))

	@property
	def tamano_total(self) -> int:
		return sum(self.tamano(p) for p in self.partes)

	@property
	def nombres_secretos(self) -> list[str]:
		secretos = self.datos.get("secretos")
		nombres = secretos.get("nombres", []) if isinstance(secretos, dict) else []
		return [n for n in nombres if isinstance(n, str)]

	@property
	def lleva_secretos(self) -> bool:
		return self.modo_secretos in ("contrasena", "dpapi")


def manifiesto_canonico(datos: dict) -> bytes:
	"""Bytes del manifiesto sin ``secretos.nombres``, con orden de claves fijo (7.4)."""
	limpio = copy.deepcopy(datos)
	secretos = limpio.get("secretos")
	if isinstance(secretos, dict):
		secretos.pop("nombres", None)
	return json.dumps(limpio, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _tupla_version(texto: str) -> tuple[int, ...]:
	numeros = []
	for trozo in str(texto).split("."):
		digitos = "".join(c for c in trozo if c.isdigit())
		numeros.append(int(digitos) if digitos else 0)
	return tuple(numeros)


def analizar_manifiesto(datos: Any) -> ManifiestoCopia:
	"""Valida el diccionario del manifiesto. Lanza ``ErrorCopia`` con el motivo en español."""
	from app.core.configuracion import VERSION_ESQUEMA

	if not isinstance(datos, dict) or datos.get("app") != APP:
		raise ErrorCopia(mensaje_no_es_copia())
	formato = datos.get("formato")
	if not isinstance(formato, int) or isinstance(formato, bool) or formato < 1:
		raise ErrorCopia(mensaje_no_es_copia())
	if formato > FORMATO:
		raise ErrorCopia(mensaje_mas_nueva())
	tipo = datos.get("tipo")
	if tipo not in TIPOS:
		raise ErrorCopia(mensaje_no_es_copia())
	try:
		fecha = datetime.fromisoformat(str(datos.get("fecha", "")))
	except ValueError:
		fecha = None
	version_esquema = datos.get("version_esquema", 1)
	if not isinstance(version_esquema, int) or isinstance(version_esquema, bool):
		version_esquema = 1
	partes: dict[str, tuple[ArchivoCopia, ...]] = {}
	avisos: list[str] = []
	brutas = datos.get("partes")
	if not isinstance(brutas, dict):
		raise ErrorCopia(mensaje_no_es_copia())
	for id_parte, info in brutas.items():
		if id_parte not in PARTES:
			log.warning("Parte desconocida en la copia: %s (se ignora)", id_parte)
			continue
		archivos = []
		for fila in (info.get("archivos", []) if isinstance(info, dict) else []):
			if not isinstance(fila, dict):
				continue
			ruta, suma, tamano = fila.get("ruta"), fila.get("sha256"), fila.get("tamano")
			if not isinstance(ruta, str) or not isinstance(suma, str) or not isinstance(tamano, int) or tamano < 0:
				raise ErrorCopia(mensaje_no_es_copia())
			if not ruta_permitida(id_parte, ruta):
				log.warning("Ruta no permitida en la parte %s de la copia: %r (se ignora)", id_parte, ruta)
				continue
			archivos.append(ArchivoCopia(ruta, suma.lower(), tamano))
		partes[id_parte] = tuple(archivos)
	if tipo == "perfil":
		# Un .zcperfil nunca trae secretos ni conexiones (10.2), aunque alguien lo haya fabricado así.
		partes = {p: a for p, a in partes.items() if p in PARTES_PERFIL}
	secretos = datos.get("secretos")
	modo = secretos.get("modo") if isinstance(secretos, dict) else "excluidos"
	if modo not in MODOS_SECRETOS or tipo == "perfil":
		modo = "excluidos"
	version_app = str(datos.get("version_app", ""))
	if _tupla_version(version_app) > _tupla_version(version.APP_VERSION) or version_esquema > VERSION_ESQUEMA:
		avisos.append(_("Esta copia es de una versión más nueva de zCommander ({v}); se puede restaurar, pero las opciones "
			"que esta versión no conoce se conservarán sin usarse.").format(v=version_app or "?"))
	return ManifiestoCopia(formato=formato, tipo=tipo, app=APP, version_app=version_app, version_esquema=version_esquema,
		fecha=fecha, descripcion=str(datos.get("descripcion", "")), partes=partes, modo_secretos=modo, datos=datos,
		avisos=tuple(avisos))


def _abrir_zip(ruta: Path) -> zipfile.ZipFile:
	try:
		zf = zipfile.ZipFile(ruta)
	except FileNotFoundError as error:
		raise ErrorCopia(_("No se encuentra el archivo {n}.").format(n=Path(ruta).name)) from error
	except (zipfile.BadZipFile, OSError, ValueError) as error:
		raise ErrorCopia(mensaje_no_es_copia()) from error
	infos = zf.infolist()
	if len(infos) > MAX_MIEMBROS or sum(i.file_size for i in infos) > MAX_TOTAL:
		zf.close()
		raise ErrorCopia(_("La copia es demasiado grande o tiene demasiados archivos; no se abre por seguridad."))
	return zf


def _leer_miembro(zf: zipfile.ZipFile, nombre: str, maximo: int) -> bytes:
	"""Lee un miembro sin pasar de ``maximo`` bytes (el tamaño declarado puede mentir)."""
	with zf.open(nombre) as entrada:
		datos = entrada.read(maximo + 1)
	if len(datos) > maximo:
		raise ErrorCopia(_("Un archivo de la copia es mayor de lo que dice; no se abre por seguridad."))
	return datos


def leer_manifiesto(ruta: Path) -> ManifiestoCopia:
	"""Lee y valida el manifiesto de una copia (sin comprobar las sumas)."""
	with _abrir_zip(Path(ruta)) as zf:
		return _manifiesto_de(zf)


def _manifiesto_de(zf: zipfile.ZipFile) -> ManifiestoCopia:
	try:
		bruto = _leer_miembro(zf, MANIFIESTO, MAX_MANIFIESTO)
		datos = json.loads(bruto.decode("utf-8"))
	except KeyError as error:
		raise ErrorCopia(mensaje_no_es_copia()) from error
	except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, OSError) as error:
		raise ErrorCopia(mensaje_no_es_copia()) from error
	return analizar_manifiesto(datos)


class CopiaAbierta:
	"""Una copia abierta para leerla: manifiesto validado y sumas comprobadas por parte.

	Uso::

		with CopiaAbierta(ruta) as copia:
			if "favoritos" in copia.partes_validas: ...
	"""

	def __init__(self, ruta: Path, comprobar: bool = True) -> None:
		self.ruta = Path(ruta)
		self._zip = _abrir_zip(self.ruta)
		try:
			self.manifiesto = _manifiesto_de(self._zip)
			self._nombres = set(self._zip.namelist())
			#: Parte → motivo por el que no se puede restaurar (sumas que no coinciden, archivos que faltan).
			self.danadas: dict[str, str] = {}
			if comprobar:
				self._comprobar()
		except BaseException:
			self._zip.close()
			raise

	def __enter__(self) -> CopiaAbierta:
		return self

	def __exit__(self, *_excepcion) -> None:
		self.cerrar()

	def cerrar(self) -> None:
		self._zip.close()

	def _comprobar(self) -> None:
		for parte, archivos in self.manifiesto.partes.items():
			for archivo in archivos:
				nombre = miembro(parte, archivo.ruta)
				if nombre not in self._nombres:
					self.danadas[parte] = _("falta {r}").format(r=archivo.ruta)
					break
				if archivo.tamano > MAX_MIEMBRO or self._suma(nombre, archivo.tamano) != archivo.sha256:
					self.danadas[parte] = _("{r} no coincide con su suma").format(r=archivo.ruta)
					break
		for parte, motivo in self.danadas.items():
			log.warning("Parte %s de la copia %s dañada: %s", parte, self.ruta.name, motivo)

	def _suma(self, nombre: str, tamano: int) -> str:
		suma = hashlib.sha256()
		leidos = 0
		try:
			with self._zip.open(nombre) as entrada:
				while bloque := entrada.read(BLOQUE):
					leidos += len(bloque)
					if leidos > tamano:
						return ""
					suma.update(bloque)
		except (zipfile.BadZipFile, OSError, ValueError, EOFError):
			log.debug("No se pudo leer %s de la copia", nombre, exc_info=True)
			return ""
		return suma.hexdigest() if leidos == tamano else ""

	@property
	def partes(self) -> list[str]:
		"""Partes que trae la copia, en el orden de 7.2."""
		return [p for p in PARTES if p in self.manifiesto.partes]

	@property
	def partes_validas(self) -> list[str]:
		return [p for p in self.partes if p not in self.danadas]

	def archivos(self, parte: str) -> list[ArchivoCopia]:
		return list(self.manifiesto.partes.get(parte, ()))

	def archivos_datos(self, parte: str) -> list[ArchivoCopia]:
		"""Los archivos de ``data`` de la parte (sin valores, lista ni paquetes)."""
		return [a for a in self.archivos(parte) if not es_especial(a.ruta)]

	def tiene(self, parte: str, ruta: str) -> bool:
		return any(a.ruta == ruta for a in self.manifiesto.partes.get(parte, ()))

	def leer(self, parte: str, ruta: str) -> bytes:
		"""Bytes de un archivo de la parte (solo si está en el manifiesto y la parte no está dañada)."""
		if parte in self.danadas:
			raise ErrorCopia(_("La parte {p} de la copia está dañada.").format(p=_(PARTES[parte].nombre)))
		archivo = next((a for a in self.manifiesto.partes.get(parte, ()) if a.ruta == ruta), None)
		if archivo is None:
			raise KeyError(ruta)
		return _leer_miembro(self._zip, miembro(parte, ruta), archivo.tamano)

	def leer_json(self, parte: str, ruta: str, por_defecto: Any = None) -> Any:
		if not self.tiene(parte, ruta):
			return por_defecto
		try:
			return json.loads(self.leer(parte, ruta).decode("utf-8-sig"))
		except (ValueError, UnicodeDecodeError):
			log.warning("El archivo %s de la copia no es JSON válido", ruta)
			return por_defecto

	def valores(self, parte: str) -> dict[str, Any]:
		datos = self.leer_json(parte, VALORES, {})
		return {k: v for k, v in datos.items() if isinstance(k, str)} if isinstance(datos, dict) else {}

	def secretos_bin(self) -> bytes | None:
		if SECRETOS not in self._nombres:
			return None
		return _leer_miembro(self._zip, SECRETOS, MAX_MANIFIESTO)

	def tamano(self, parte: str) -> int:
		return self.manifiesto.tamano(parte)


def nombre_parte(id_parte: str) -> str:
	parte = PARTES.get(id_parte)
	return _(parte.nombre) if parte else id_parte


def ruta_relativa(ruta: Path, base: Path) -> str:
	"""Ruta POSIX de ``ruta`` relativa a ``base``."""
	return PurePosixPath(Path(ruta).relative_to(base).as_posix()).as_posix()
