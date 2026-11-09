# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cuentas de nube y catálogo de servicios (diseño 2.0, 12.5).

- ``cuentas.json`` (en ``data/config/plugins/zc.nubes/``) guarda las cuentas SIN
  secretos: los tokens viven en ``rclone.conf`` cifrado y las contraseñas de
  WebDAV y los secretos de cliente en ``secretos.dat`` (DPAPI).
- El ``id`` de cada cuenta es el nombre de su remoto en ``rclone.conf`` (lo usa
  la copia de seguridad, que puede marcarla con ``volver_a_configurar``).
- El catálogo de servicios es DATOS (``recursos/servicios.json``): añadir una
  nube es añadir una ficha. Otros complementos pueden aportar fichas en su
  ``recursos/servicios/*.json`` si declaran ``[recomienda] complementos = ["zc.nubes"]``.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import string
import threading
import tomllib
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.plugins import api

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

VERSION_CUENTAS = 1
MOTORES = ("rclone", "webdav")
AUTENTICACIONES = ("oauth", "contrasena", "contrasena_2fa", "clave_acceso", "token_pegado", "clave_api", "login_flow_v2",
	"ninguna")


# ── Cuentas ──────────────────────────────────────────────────────────────────


@dataclass
class Cuenta:
	id: str
	nombre: str
	servicio: str
	motor: str = "rclone"
	carpeta_inicial: str = "/"
	solo_lectura: bool = False
	papelera: bool = True
	limite_subida_kib: int = 0
	limite_bajada_kib: int = 0
	horario_limites: str = ""
	cache_listados_s: int = -1          # −1: el de la configuración del complemento
	opciones: dict[str, str] = field(default_factory=dict)
	client_id_propio: bool = False
	cifrada_sobre: str = ""
	union_de: list[str] = field(default_factory=list)
	copia_entre_cuentas: bool | None = None   # None: el de la configuración del complemento
	#: WebDAV nativo: dirección base y usuario (la contraseña, en secretos).
	url: str = ""
	usuario: str = ""
	#: Huella SHA-256 del certificado aceptado (WebDAV con certificado propio).
	huella: str = ""
	#: Lo pone la copia de seguridad cuando no restaura su remoto: hay que volver a configurarla.
	volver_a_configurar: bool = False

	@property
	def remoto(self) -> str:
		"""Nombre de ``fs`` de rclone: ``"<id>:"``."""
		return f"{self.id}:"

	@property
	def direccion(self) -> str:
		return f"nube://{self.id}/"

	@classmethod
	def desde_dict(cls, datos: dict[str, Any]) -> Cuenta:
		conocidos = {f for f in cls.__dataclass_fields__}  # noqa: C416 - nombres de los campos
		limpio = {k: v for k, v in datos.items() if k in conocidos}
		cuenta = cls(**limpio)
		cuenta.opciones = {str(k): str(v) for k, v in (cuenta.opciones or {}).items()}
		cuenta.union_de = [str(u) for u in (cuenta.union_de or [])]
		return cuenta

	def a_dict(self) -> dict[str, Any]:
		return asdict(self)


def _escribir_atomico(ruta: Path, texto: str) -> None:
	ruta.parent.mkdir(parents=True, exist_ok=True)
	temporal = ruta.with_name(ruta.name + ".tmp")
	with open(temporal, "w", encoding="utf-8", newline="\n") as archivo:
		archivo.write(texto)
		archivo.flush()
		os.fsync(archivo.fileno())
	os.replace(temporal, ruta)


class AlmacenCuentas:
	"""``cuentas.json`` con carga tolerante y escritura atómica; seguro entre hilos."""

	def __init__(self, ruta: Path) -> None:
		self.ruta = Path(ruta)
		self._candado = threading.RLock()
		self._cuentas: list[Cuenta] | None = None

	def _cargar(self) -> list[Cuenta]:
		if self._cuentas is not None:
			return self._cuentas
		cuentas: list[Cuenta] = []
		try:
			datos = json.loads(self.ruta.read_text(encoding="utf-8"))
			for bruta in datos.get("cuentas", []) if isinstance(datos, dict) else []:
				try:
					cuentas.append(Cuenta.desde_dict(bruta))
				except (TypeError, ValueError):
					log.warning("Cuenta de nube no válida en %s: se omite", self.ruta.name, exc_info=True)
		except FileNotFoundError:
			pass
		except (OSError, ValueError):
			log.error("cuentas.json dañado; se aparta y se empieza sin cuentas", exc_info=True)
			try:
				os.replace(self.ruta, self.ruta.with_name(self.ruta.name + ".danado"))
			except OSError:
				log.warning("No se pudo apartar cuentas.json", exc_info=True)
		self._cuentas = cuentas
		return cuentas

	def recargar(self) -> None:
		with self._candado:
			self._cuentas = None

	def _guardar(self) -> None:
		datos = {"version": VERSION_CUENTAS, "cuentas": [c.a_dict() for c in self._cargar()]}
		_escribir_atomico(self.ruta, json.dumps(datos, ensure_ascii=False, indent="\t"))

	def lista(self) -> list[Cuenta]:
		with self._candado:
			return [copy.deepcopy(c) for c in self._cargar()]

	def obtener(self, id: str) -> Cuenta | None:
		with self._candado:
			for cuenta in self._cargar():
				if cuenta.id == id:
					return copy.deepcopy(cuenta)
		return None

	def guardar(self, cuenta: Cuenta) -> None:
		"""Añade o sustituye (por ``id``)."""
		with self._candado:
			cuentas = self._cargar()
			for indice, actual in enumerate(cuentas):
				if actual.id == cuenta.id:
					cuentas[indice] = copy.deepcopy(cuenta)
					break
			else:
				cuentas.append(copy.deepcopy(cuenta))
			self._guardar()

	def quitar(self, id: str) -> None:
		with self._candado:
			cuentas = self._cargar()
			self._cuentas = [c for c in cuentas if c.id != id]
			self._guardar()

	def id_libre(self, nombre: str, ocupados: set[str] | None = None) -> str:
		"""Id de remoto válido para rclone a partir del nombre visible («Google Drive de Ana» → «google_drive_de_ana»)."""
		base = identificador(nombre)
		ocupados = set(ocupados or ()) | {c.id for c in self.lista()}
		candidato, numero = base, 2
		while candidato in ocupados:
			candidato = f"{base}_{numero}"
			numero += 1
		return candidato


def identificador(nombre: str) -> str:
	sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii").lower()
	limpio = re.sub(r"[^a-z0-9]+", "_", sin_tildes).strip("_")[:40] or "nube"
	if limpio[0] not in string.ascii_lowercase:
		limpio = "nube_" + limpio
	return limpio


# ── Catálogo de servicios ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Servicio:
	id: str
	nombre: str
	tipo: str                       # tipo de rclone, o «webdav_nativo» / «nextcloud»
	autenticacion: str
	nivel: int = 1
	descripcion: str = ""
	campos: tuple[dict[str, Any], ...] = ()
	opciones: dict[str, str] = field(default_factory=dict)
	avanzadas: tuple[dict[str, Any], ...] = ()
	papelera: bool = False
	ayuda_url: str = ""
	avisos: tuple[str, ...] = ()
	guia: str = ""
	alias: tuple[str, ...] = ()
	origen: str = "zc.nubes"

	@property
	def experimental(self) -> bool:
		return self.nivel >= 4

	@property
	def es_oauth(self) -> bool:
		return self.autenticacion == "oauth"

	@property
	def motor(self) -> str:
		return "webdav" if self.tipo in ("webdav_nativo", "nextcloud") else "rclone"

	def campo(self, clave: str) -> dict[str, Any] | None:
		for campo in (*self.campos, *self.avanzadas):
			if campo.get("clave") == clave:
				return campo
		return None


class ErrorCatalogo(Exception):
	pass


def _servicio_desde(datos: dict[str, Any], origen: str) -> Servicio:
	for obligatorio in ("id", "nombre", "tipo", "autenticacion"):
		if not isinstance(datos.get(obligatorio), str) or not datos[obligatorio]:
			raise ErrorCatalogo(f"Ficha sin «{obligatorio}»: {datos.get('id')}")
	if datos["autenticacion"] not in AUTENTICACIONES:
		raise ErrorCatalogo(f"Ficha {datos['id']}: autenticación «{datos['autenticacion']}» desconocida")
	campos = tuple(dict(c) for c in datos.get("campos", []) if isinstance(c, dict) and c.get("clave"))
	avanzadas = tuple(dict(c) for c in datos.get("avanzadas", []) if isinstance(c, dict) and c.get("clave"))
	return Servicio(
		id=datos["id"], nombre=datos["nombre"], tipo=datos["tipo"], autenticacion=datos["autenticacion"],
		nivel=int(datos.get("nivel", 1)), descripcion=str(datos.get("descripcion", "")), campos=campos,
		opciones={str(k): str(v) for k, v in (datos.get("opciones") or {}).items()}, avanzadas=avanzadas,
		papelera=bool(datos.get("papelera", False)), ayuda_url=str(datos.get("ayuda_url", "")),
		avisos=tuple(str(a) for a in datos.get("avisos", [])), guia=str(datos.get("guia", "")),
		alias=tuple(str(a) for a in datos.get("alias", [])), origen=origen)


class Catalogo:
	"""Servicios del catálogo propio y de los complementos que aportan fichas."""

	def __init__(self, servicios: list[Servicio]) -> None:
		self._servicios = {s.id: s for s in servicios}

	@classmethod
	def cargar(cls, archivo: Path, aportaciones: list[tuple[str, Path]] = ()) -> Catalogo:
		servicios: list[Servicio] = []
		datos = json.loads(Path(archivo).read_text(encoding="utf-8"))
		for ficha in datos.get("servicios", []):
			servicios.append(_servicio_desde(ficha, "zc.nubes"))
		propios = {s.id for s in servicios}
		for origen, ruta in aportaciones:
			try:
				otros = json.loads(Path(ruta).read_text(encoding="utf-8"))
				for ficha in otros.get("servicios", []):
					servicio = _servicio_desde(ficha, origen)
					if servicio.id in propios:
						log.warning("El complemento %s aporta el servicio %s, que ya existe: se ignora", origen, servicio.id)
						continue
					servicios.append(servicio)
			except (OSError, ValueError, ErrorCatalogo):
				log.warning("Fichas de servicios no válidas en %s (%s)", ruta, origen, exc_info=True)
		return cls(servicios)

	def servicio(self, id: str) -> Servicio | None:
		return self._servicios.get(id)

	def lista(self, mostrar_experimentales: bool = False) -> list[Servicio]:
		servicios = [s for s in self._servicios.values() if mostrar_experimentales or not s.experimental]
		return sorted(servicios, key=lambda s: (s.id == "otro", s.nombre.casefold()))

	def buscar(self, texto: str, mostrar_experimentales: bool = False) -> list[Servicio]:
		texto = _plano(texto)
		if not texto:
			return self.lista(mostrar_experimentales)
		return [s for s in self.lista(mostrar_experimentales)
			if texto in _plano(s.nombre) or texto in _plano(s.descripcion) or any(texto in _plano(a) for a in s.alias)
			or texto in s.tipo]

	def __len__(self) -> int:
		return len(self._servicios)


def _plano(texto: str) -> str:
	return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").casefold().strip()


def aportaciones_de_complementos(carpetas: list[Path], propio: str = "zc.nubes") -> list[tuple[str, Path]]:
	"""Fichas ``recursos/servicios/*.json`` de los complementos que recomiendan ``zc.nubes`` (solo datos, nunca código)."""
	resultado: list[tuple[str, Path]] = []
	for raiz in carpetas:
		if not raiz.is_dir():
			continue
		for carpeta in sorted(raiz.iterdir()):
			manifiesto = carpeta / "manifiesto.toml"
			if not manifiesto.is_file() or carpeta.name.startswith("."):
				continue
			try:
				datos = tomllib.loads(manifiesto.read_text(encoding="utf-8"))
			except (OSError, ValueError):
				continue
			if datos.get("id") == propio:
				continue
			recomendados = (datos.get("recomienda") or {}).get("complementos", []) or []
			if not any(str(r).split()[0] == propio for r in recomendados if str(r).strip()):
				continue
			for ficha in sorted((carpeta / "recursos" / "servicios").glob("*.json")):
				resultado.append((str(datos.get("id", carpeta.name)), ficha))
	return resultado


# ── Google Drive para escritorio ─────────────────────────────────────────────


def carpeta_drive_escritorio() -> str | None:
	"""Unidad o carpeta que configura Google Drive para escritorio (``HKCU\\Software\\Google\\DriveFS``), si existe."""
	try:
		import winreg
	except ImportError:  # pragma: no cover - fuera de Windows
		return None
	candidatas: list[str] = []
	try:
		with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS") as clave:
			for nombre in ("MountPoint", "DefaultMountPoint", "mount_point_path", "PerAccountPreferences"):
				try:
					valor, _tipo = winreg.QueryValueEx(clave, nombre)
				except OSError:
					continue
				texto = str(valor).strip()
				if len(texto) == 1 and texto.isalpha():
					texto = f"{texto.upper()}:\\"
				elif len(texto) == 2 and texto.endswith(":"):
					texto += "\\"
				if texto and (texto[1:3] == ":\\" or texto.startswith("\\\\")):
					candidatas.append(texto)
	except OSError:
		return None
	for candidata in candidatas:
		for sub in ("Mi unidad", "My Drive", ""):
			ruta = os.path.join(candidata, sub) if sub else candidata
			if os.path.isdir(ruta):
				return ruta
	return None
