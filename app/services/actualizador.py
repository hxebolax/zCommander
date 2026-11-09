# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Actualizador de zCommander (diseño 2.0, sección 5): seguro, portable y con vuelta atrás.

Parte de la plantilla del agente «actualizador» (el modelo de YouTubeRO) y respeta
sus diez reglas de oro. Lo propio de zCommander:

- Constantes de 5.2 (nombre, ejecutable, manifiesto, clave pública, recursos).
- ``DATA_ENTRANTE`` (5.3): el ``data/bin`` del paquete NUNCA se copia sobre los
  componentes activos; el ``.bat`` lo deja en ``data/bin/.entrante`` y CO lo
  integra en el primer arranque de la versión nueva.
- La red y la descarga son las de ``app/core/red.py`` y ``app/core/descargas.py``
  (una sola implementación de descarga, 14.9).
- **Salud en dos fases** (5.2, cambio declarado de la plantilla): la versión
  nueva escribe muy pronto ``iniciado <versión> <PID>`` (:func:`marcar_inicio`,
  paso 4 de 14.8) y ``ok <versión>`` tras mostrar la ventana (:func:`al_arrancar`,
  paso 10). El ``.bat`` espera ``iniciado`` como mucho ``ESPERA_SALUD`` segundos y,
  si llega, amplía la espera de ``ok`` hasta ``ESPERA_SALUD_TOTAL`` (el primer
  arranque puede integrar componentes grandes desde un pendrive). Si se agota con
  el proceso vivo, NO vuelve atrás: deja «salud sin confirmar», conserva el
  respaldo y el siguiente arranque ofrece volver a la versión anterior.
- ``registrar_comprobacion`` (5.4): CO y PL se suman a la comprobación periódica.

Fuentes (preferencia ``actualizaciones.fuente``): el servidor de siempre, GitHub
(``REPOSITORIO_GITHUB``), las dos (gana la versión más nueva; si una falla se usa la
otra) o una dirección personalizada. Con cualquiera, el manifiesto tiene que venir
firmado con una de ``CLAVES_PUBLICAS_ED25519``: la fuente solo decide de dónde se
lee, nunca en quién se confía. El campo firmado ``espejos`` da otras direcciones
del mismo ZIP (``espejos.github``, la release de GitHub).

Flujo: :func:`comprobar` (firma Ed25519 ANTES de mirar ningún campo, versiones,
anti-retroceso) → :func:`descargar` (reanudable, con direcciones de respaldo) →
:func:`verificar_paquete` (tamaño y SHA-256) → :func:`extraer_seguro` → :func:`preparar_sustitucion` (el
``.bat``) → :func:`lanzar_sustitucion` y la interfaz cierra la aplicación.

Por qué un ``.bat``: la versión compilada no trae un ``python.exe`` utilizable
(el intérprete va dentro del ejecutable que hay que sustituir) y ``cmd.exe``,
``robocopy``, ``tasklist`` y ``powershell`` están en todo Windows. Vive en
``data/temp`` para no sobrescribirse a sí mismo durante la copia.

Sin wx (regla de capas): la interfaz está en ``app/ui/dialogo_actualizacion.py``.
"""

from __future__ import annotations

import base64
import binascii
import builtins
import hmac
import http.client
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core import descargas, red

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	"""Traduce con el ``_`` que gettext instala en ``builtins``, si existe.

	Se busca en cada llamada (y no al importar) porque el módulo puede importarse
	antes de que la aplicación instale su traducción.
	"""
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── CONFIGURACIÓN DE zCommander (diseño 2.0, 5.2) ────────────────────────────
NOMBRE_APP = "zCommander"
EJECUTABLE = "ZCommander.exe"
# Siempre https (http solo se admite en localhost para las pruebas).
URL_MANIFIESTO = "https://xebolax.synology.me/zCommander/version.json"
# Repositorio público de GitHub: una release por versión (etiqueta «v<versión>») con
# zCommander_v<versión>.zip, zCommander_v<versión>_fuentes.zip y el MISMO version.json
# firmado. «latest/download» redirige (https) al recurso de la última release.
REPOSITORIO_GITHUB = "hxebolax/zCommander"
URL_MANIFIESTO_GITHUB = f"https://github.com/{REPOSITORIO_GITHUB}/releases/latest/download/version.json"
# De dónde se buscan las actualizaciones (preferencia «actualizaciones.fuente»). La raíz
# de confianza es SIEMPRE la firma: con cualquier fuente, el version.json tiene que
# venir firmado con una de CLAVES_PUBLICAS_ED25519.
FUENTE_SERVIDOR = "servidor"
FUENTE_GITHUB = "github"
FUENTE_AMBAS = "ambas"
FUENTE_PERSONALIZADA = "personalizada"
FUENTES: tuple[str, ...] = (FUENTE_SERVIDOR, FUENTE_GITHUB, FUENTE_AMBAS, FUENTE_PERSONALIZADA)
# Campo firmado del manifiesto con otras direcciones del mismo ZIP: {"github": "https://..."}.
# Los clientes 2.0.0 lo ignoran (solo leen los campos que conocen) y la firma lo cubre.
CAMPO_ESPEJOS = "espejos"
ESPEJO_GITHUB = "github"
# Claves PÚBLICAS Ed25519 en hexadecimal. Se acepta la firma de CUALQUIERA: así se
# puede rotar la clave publicando una versión que ya conozca la nueva antes de
# retirar la antigua. La privada vive en tools/claves/ y nunca se publica.
CLAVES_PUBLICAS_ED25519: tuple[str, ...] = ("599e1d417fc3492fd08f41a411b43f8a887553f8f1137ea5e7b59164d1d01480",)
# Lo único de data que una versión nueva puede refrescar (añadir o reemplazar,
# nunca borrar). NO incluye bin (5.3) ni sounds_usuario, plugins, config, cache,
# logs, backups ni temp: son de la persona.
DATA_ACTUALIZABLE: tuple[str, ...] = ("sounds", "locales", "docs", "icons")
# Subcarpetas de data del paquete que van a una carpeta de entrada en lugar de su
# sitio (5.3): data/bin del paquete llega a data/bin/.entrante y los componentes
# activos no se tocan (la persona puede haberlos actualizado). CO lo integra.
DATA_ENTRANTE: dict[str, str] = {"bin": "bin/.entrante"}
# ─────────────────────────────────────────────────────────────────────────────

ARGUMENTO_TRAS_ACTUALIZAR = "--tras-actualizar"
CAMPO_FIRMA = "firma_ed25519"
# Segundos que la versión nueva tiene para escribir «iniciado» (fase 1).
ESPERA_SALUD = 60
# Segundos (desde que se lanza) que tiene para escribir «ok» si ya escribió «iniciado» (fase 2).
ESPERA_SALUD_TOTAL = 300
# Segundos que el script espera a que la aplicación se cierre. Si no se cierra
# (la persona canceló la salida para guardar algo), la actualización se CANCELA:
# nunca se mata una aplicación que puede tener trabajo sin guardar.
ESPERA_CIERRE = 90
TIEMPO_MANIFIESTO = 15
TIEMPO_DESCARGA = 30
MAX_MANIFIESTO = 256 * 1024
MAX_DESCARGA = 2 * 1024**3
MAX_EXPANDIDO = 4 * 1024**3
MAX_MIEMBROS = 50_000
_NOMBRES_RESERVADOS = (
	{"con", "prn", "aux", "nul"} | {f"com{n}" for n in range(1, 10)} | {f"lpt{n}" for n in range(1, 10)}
)

Progreso = Callable[[str, int, int], None]
"""``progreso(fase, hecho, total)``; fases: descarga, verificacion, extraccion, preparacion."""


# ════════════════════════════════════════════════════════════════════════════
# Errores: el mensaje de cada uno está pensado para leérselo a la persona
# ════════════════════════════════════════════════════════════════════════════


class ErrorActualizacion(Exception):
	"""Error de actualización con un mensaje claro para la persona."""


class ErrorRed(ErrorActualizacion):
	"""No se pudo hablar con el servidor o la descarga se interrumpió."""


class ErrorFirma(ErrorActualizacion):
	"""El manifiesto no está firmado o la firma no es válida."""


class ErrorVerificacion(ErrorActualizacion):
	"""El paquete descargado no coincide con el manifiesto (tamaño o SHA-256)."""


class ErrorSinDireccion(ErrorActualizacion):
	"""2.0.1: la fuente es «personalizada» y no hay dirección (la comprobación no puede hacerse)."""


class ErrorPaquete(ErrorActualizacion):
	"""El ZIP es peligroso, inválido o no parece de esta aplicación."""


class ErrorRollback(ErrorActualizacion):
	"""El servidor ofrece una versión inferior a la última confirmada en este equipo."""


class ErrorCancelado(ErrorActualizacion):
	"""La persona canceló la descarga (la parte descargada se conserva)."""


class VersionInvalida(ValueError):
	"""La cadena no es una versión reconocible."""


# ════════════════════════════════════════════════════════════════════════════
# Configuración y datos
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class Configuracion:
	"""Todo lo que el actualizador necesita saber de la aplicación.

	Se pasa explícitamente (en lugar de leer variables globales) para que las
	pruebas trabajen sobre instalaciones falsas en carpetas temporales.
	"""

	version_actual: str
	carpeta_app: Path
	carpeta_datos: Path | None = None
	nombre_app: str = NOMBRE_APP
	ejecutable: str = EJECUTABLE
	url_manifiesto: str = URL_MANIFIESTO
	"""Manifiesto de la fuente «servidor» (el de siempre)."""
	url_github: str = URL_MANIFIESTO_GITHUB
	"""Manifiesto de la fuente «github»."""
	fuente: str = FUENTE_SERVIDOR
	url_personalizada: str = ""
	"""Solo con la fuente «personalizada»."""
	preferencias: Callable[[], tuple[str, str]] | None = None
	"""Si existe, devuelve ``(fuente, url_personalizada)`` al comprobar: así un cambio en
	Preferencias se aplica sin reiniciar (la comprobación periódica guarda esta configuración)."""
	claves_publicas: tuple[str, ...] = CLAVES_PUBLICAS_ED25519
	comando: list[str] | None = None
	data_actualizable: tuple[str, ...] = DATA_ACTUALIZABLE
	data_entrante: dict[str, str] = field(default_factory=lambda: dict(DATA_ENTRANTE))
	espera_salud: int = ESPERA_SALUD
	espera_salud_total: int = ESPERA_SALUD_TOTAL
	espera_cierre: int = ESPERA_CIERRE
	pid_a_esperar: int | None = None
	max_expandido: int = MAX_EXPANDIDO
	permitir_desde_codigo: bool = False
	extra: dict = field(default_factory=dict)

	def __post_init__(self) -> None:
		self.carpeta_app = Path(self.carpeta_app).resolve()
		self.carpeta_datos = Path(self.carpeta_datos).resolve() if self.carpeta_datos else self.carpeta_app / "data"
		if self.comando is None:
			self.comando = _comando_por_defecto()

	@property
	def carpeta_trabajo(self) -> Path:
		return self.carpeta_datos / "temp" / "actualizacion"

	@property
	def carpeta_respaldo(self) -> Path:
		return self.carpeta_datos / "temp" / "version_anterior"

	@property
	def archivo_estado(self) -> Path:
		return self.carpeta_datos / "config" / "actualizaciones.json"

	@property
	def marcador_salud(self) -> Path:
		"""``ok <versión>``: la versión nueva confirmó su salud tras mostrar la ventana."""
		return self.carpeta_trabajo / "salud.txt"

	@property
	def marca_inicio(self) -> Path:
		"""``iniciado <versión> <PID>``: la versión nueva empezó a arrancar (fase 1)."""
		return self.carpeta_trabajo / "iniciado.txt"

	@property
	def marca_sin_confirmar(self) -> Path:
		"""``salud sin confirmar <versión> <PID> <anterior>``: el script se cansó de esperar ``ok``."""
		return self.carpeta_trabajo / "salud_sin_confirmar.txt"

	@property
	def aviso_espera_salud(self) -> Path:
		"""Lo deja el script con la versión que espera: cualquier copia de esa versión confirma."""
		return self.carpeta_trabajo / "esperando_salud.txt"

	@property
	def archivo_resultado(self) -> Path:
		return self.carpeta_trabajo / "resultado.txt"

	@property
	def registro_script(self) -> Path:
		return self.carpeta_datos / "logs" / "actualizacion.log"


def _comando_por_defecto() -> list[str]:
	"""Orden para relanzar la aplicación: el .exe compilado o ``python main.py``."""
	if getattr(sys, "frozen", False):
		return [sys.executable]
	return [sys.executable, str(Path(__file__).resolve().parent.parent.parent / "main.py")]


def configuracion_por_defecto(version_actual: str | None = None) -> Configuracion:
	"""Configuración de la aplicación en ejecución, con las rutas de ``app/core/paths.py``.

	Respeta ``APP_DATA_DIR`` (la usan las pruebas y los perfiles aparte).
	"""
	from app.core import paths

	if version_actual is None:
		from app.core.version import APP_VERSION

		version_actual = APP_VERSION
	return Configuracion(version_actual=version_actual, carpeta_app=paths.ruta_base(), carpeta_datos=paths.ruta_datos(),
		preferencias=preferencias_de_la_aplicacion)


def preferencias_de_la_aplicacion() -> tuple[str, str]:
	"""``(actualizaciones.fuente, actualizaciones.url_personalizada)`` de la configuración de la aplicación."""
	from app.core.configuracion import obtener_configuracion

	ajustes = obtener_configuracion()
	return (str(ajustes.obtener("actualizaciones.fuente", FUENTE_SERVIDOR) or FUENTE_SERVIDOR),
		str(ajustes.obtener("actualizaciones.url_personalizada", "") or ""))


@dataclass(frozen=True)
class InfoActualizacion:
	"""Versión disponible, tal como la describe el manifiesto firmado."""

	version: str
	archivo: str
	url_zip: str
	sha256: str
	tamano: int
	fecha: str = ""
	novedades: str = ""
	fuente: str = ""
	"""Fuente que dio el manifiesto elegido (``servidor``, ``github``, ``personalizada``...)."""
	urls_respaldo: tuple[str, ...] = ()
	"""Otras direcciones del MISMO ZIP (firmadas en el manifiesto) si falla ``url_zip``."""

	@property
	def urls(self) -> tuple[str, ...]:
		"""``url_zip`` y después los respaldos, sin repetir."""
		return tuple(dict.fromkeys((self.url_zip, *self.urls_respaldo)))


def puede_instalar(config: Configuracion) -> bool:
	"""La sustitución solo se hace en la versión compilada.

	Desde el código fuente se puede comprobar y avisar, pero sustituir los
	archivos del proyecto del desarrollador con un ZIP compilado sería destructivo.
	"""
	return bool(getattr(sys, "frozen", False)) or config.permitir_desde_codigo


# ════════════════════════════════════════════════════════════════════════════
# Versiones (semver sencillo + PEP 440 básico, sin dependencias)
# ════════════════════════════════════════════════════════════════════════════

_PATRON_VERSION = re.compile(
	r"""
	^\s*v?
	(?P<release>\d+(?:\.\d+)*)
	(?:[-_.]?(?P<pre_l>alpha|beta|preview|pre|rc|a|b|c)[-_.]?(?P<pre_n>\d+)?)?
	(?:(?:[-_.]?(?P<post_l>post|rev|r)[-_.]?(?P<post_n>\d+)?)|(?:-(?P<post_implicito>\d+)))?
	(?:[-_.]?(?P<dev_l>dev)[-_.]?(?P<dev_n>\d+)?)?
	(?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?
	\s*$
	""",
	re.VERBOSE | re.IGNORECASE,
)
_RANGO_PRE = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}


def clave_version(texto: str) -> tuple:
	"""Convierte una versión en una tupla ordenable según PEP 440.

	Orden: ``1.0.dev1 < 1.0a1 < 1.0b1 < 1.0rc1 < 1.0 == 1.0.0 < 1.0.post1``.
	Admite el semver habitual (``1.2.3-beta.1``). La parte local (``+abc``) no
	cuenta para el orden. ``1.0-1`` es una posterior (post), como en PEP 440.
	"""
	coincidencia = _PATRON_VERSION.match(str(texto or ""))
	if not coincidencia:
		raise VersionInvalida(f"Versión no válida: {texto!r}")
	release = tuple(int(parte) for parte in coincidencia["release"].split("."))
	while len(release) > 1 and release[-1] == 0:
		release = release[:-1]
	pre_l = coincidencia["pre_l"]
	post_presente = bool(coincidencia["post_l"] or coincidencia["post_implicito"])
	dev_presente = bool(coincidencia["dev_l"])
	if pre_l:
		pre = (0, _RANGO_PRE[pre_l.lower()], int(coincidencia["pre_n"] or 0))
	elif dev_presente and not post_presente:
		pre = (-1, 0, 0)  # 1.0.dev1 va antes que cualquier pre-versión de 1.0
	else:
		pre = (1, 0, 0)
	if post_presente:
		post = (1, int(coincidencia["post_n"] or coincidencia["post_implicito"] or 0))
	else:
		post = (0, 0)
	dev = (0, int(coincidencia["dev_n"] or 0)) if dev_presente else (1, 0)
	return (release, pre, post, dev)


def comparar_versiones(a: str, b: str) -> int:
	"""Devuelve -1, 0 o 1 según ``a`` sea menor, igual o mayor que ``b``."""
	clave_a, clave_b = clave_version(a), clave_version(b)
	return (clave_a > clave_b) - (clave_a < clave_b)


def es_mas_nueva(a: str, b: str) -> bool:
	"""Indica si ``a`` es estrictamente más nueva que ``b``."""
	return comparar_versiones(a, b) > 0


# ════════════════════════════════════════════════════════════════════════════
# Firma
# ════════════════════════════════════════════════════════════════════════════


def serializar_canonico(manifiesto: dict) -> bytes:
	"""Bytes exactos que se firman: JSON ordenado, separadores fijos, sin la firma.

	Debe ser IDÉNTICA a la de ``tools/firmar_version.py`` (una prueba lo
	comprueba). Firmar el manifiesto completo, y no solo «versión + sha», impide
	que alguien cambie las novedades, la URL o el tamaño sin invalidar la firma.
	"""
	datos = {clave: valor for clave, valor in manifiesto.items() if clave != CAMPO_FIRMA}
	return json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def verificar_firma(manifiesto: dict, claves_publicas: tuple[str, ...] | list[str]) -> None:
	"""Comprueba la firma Ed25519 del manifiesto con alguna de las claves públicas.

	:raises ErrorFirma: sin claves, sin firma, firma mal formada o no válida.
	"""
	if not claves_publicas:
		raise ErrorFirma(
			_("La aplicación no tiene configurada ninguna clave de verificación; por seguridad no se aceptan actualizaciones.")
		)
	firma_b64 = manifiesto.get(CAMPO_FIRMA)
	if not isinstance(firma_b64, str) or not firma_b64.strip():
		raise ErrorFirma(_("La información de la versión nueva no está firmada; no se instalará."))
	try:
		firma = base64.b64decode(firma_b64, validate=True)
	except (binascii.Error, ValueError) as error:
		raise ErrorFirma(_("La firma de la versión nueva está dañada; no se instalará.")) from error
	try:
		from cryptography.exceptions import InvalidSignature
		from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
	except ImportError as error:
		log.exception("Falta el paquete cryptography: no se puede verificar la firma")
		raise ErrorFirma(_("Falta el componente que verifica las firmas; no se puede actualizar de forma segura.")) from error
	mensaje = serializar_canonico(manifiesto)
	for clave_hex in claves_publicas:
		try:
			clave = Ed25519PublicKey.from_public_bytes(bytes.fromhex(clave_hex))
		except ValueError:
			log.error("Clave pública mal formada en la configuración: %s…", str(clave_hex)[:16])
			continue
		try:
			clave.verify(firma, mensaje)
		except InvalidSignature:
			log.debug("La firma no corresponde a la clave %s…", clave_hex[:16])
			continue
		log.info("Firma del manifiesto verificada con la clave %s…", clave_hex[:16])
		return
	raise ErrorFirma(_("La firma de la versión nueva no es válida; no se instalará."))


# ════════════════════════════════════════════════════════════════════════════
# Estado persistente (data/config/actualizaciones.json)
# ════════════════════════════════════════════════════════════════════════════

_candado_estado = threading.Lock()


def leer_estado(config: Configuracion) -> dict:
	"""Lee la memoria del actualizador; si falta o está dañada, empieza vacía."""
	try:
		datos = json.loads(config.archivo_estado.read_text(encoding="utf-8"))
		return datos if isinstance(datos, dict) else {}
	except FileNotFoundError:
		return {}
	except (OSError, ValueError):
		# Dañada: se sigue sin memoria (la regla «más nueva que la instalada»
		# sigue protegiendo) en lugar de bloquear las actualizaciones para siempre.
		log.warning("No se pudo leer %s; se empieza con el estado vacío", config.archivo_estado, exc_info=True)
		return {}


def guardar_estado(config: Configuracion, estado: dict) -> None:
	"""Guarda el estado de forma atómica (temporal + ``os.replace``)."""
	ruta = config.archivo_estado
	ruta.parent.mkdir(parents=True, exist_ok=True)
	temporal = ruta.with_name(ruta.name + ".tmp")
	temporal.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")
	os.replace(temporal, ruta)


def _actualizar_estado(config: Configuracion, **cambios: str) -> None:
	"""Lee, cambia y guarda bajo un candado: la comprobación periódica y la manual pueden coincidir."""
	with _candado_estado:
		try:
			estado = leer_estado(config)
			estado.update(cambios)
			guardar_estado(config, estado)
		except OSError:
			log.warning("No se pudo guardar el estado del actualizador", exc_info=True)


def omitir_version(config: Configuracion, version: str) -> None:
	"""Recuerda que la persona no quiere que se le ofrezca esta versión."""
	log.info("La persona omite la versión %s", version)
	_actualizar_estado(config, version_omitida=version)


def confirmar_version(config: Configuracion, version: str | None = None) -> None:
	"""Anota la versión como instalada y confirmada (memoria anti-retroceso).

	Solo SUBE: guarda la mayor entre la anotada y la actual. Se alimenta únicamente
	de versiones que han arrancado de verdad en este equipo, nunca de lo que diga
	el servidor; así una errata publicada en ``version.json`` no puede bloquear las
	actualizaciones para siempre.
	"""
	version = version or config.version_actual
	with _candado_estado:
		estado = leer_estado(config)
		anterior = str(estado.get("version_confirmada") or "")
		try:
			if anterior and comparar_versiones(anterior, version) >= 0:
				return
		except VersionInvalida:
			log.warning("Versión confirmada no válida en el estado (%r); se sustituye", anterior)
		estado["version_confirmada"] = version
		try:
			guardar_estado(config, estado)
			log.info("Versión %s confirmada (anti-retroceso)", version)
		except OSError:
			log.warning("No se pudo anotar la versión confirmada", exc_info=True)


# ════════════════════════════════════════════════════════════════════════════
# Red (app/core/red.py)
# ════════════════════════════════════════════════════════════════════════════


def _config_red(config: Configuracion, url: str, tiempo: float) -> red.ConfiguracionRed:
	"""User-Agent «zCommander/<versión>» (16); sin proxy contra la propia máquina (pruebas)."""
	local = (urllib.parse.urlsplit(url).hostname or "") in red.HOSTS_LOCALES
	return red.ConfiguracionRed(config.nombre_app, config.version_actual, proxy="ninguno" if local else "sistema",
		tiempo_lectura=tiempo)


def _comprobar_url(url: str) -> None:
	"""Solo https; http únicamente contra la propia máquina (pruebas)."""
	try:
		red.comprobar_url(url)
	except red.ErrorHTTP as error:
		raise ErrorRed(_("Dirección de actualización no segura: solo se admite https.")) from error


def _host(url: str) -> str:
	try:
		return (urllib.parse.urlsplit(url).hostname or "").lower()
	except ValueError:
		return ""


def _es_de_github(url: str) -> bool:
	"""github.com y los hosts a los que redirigen sus descargas (objects/release-assets.githubusercontent.com)."""
	host = _host(url)
	return host == "github.com" or host.endswith(".github.com") or host.endswith(".githubusercontent.com")


def nombre_fuente(fuente: str, url: str = "") -> str:
	"""Cómo se nombra una fuente en los mensajes («No se pudo conectar con GitHub...»)."""
	host = _host(url)
	if fuente == FUENTE_GITHUB:
		return "GitHub"
	if fuente == FUENTE_SERVIDOR:
		return _("el servidor de zCommander ({host})").format(host=host or _host(URL_MANIFIESTO))
	if fuente == FUENTE_PERSONALIZADA:
		return _("la dirección personalizada ({host})").format(host=host) if host else _("la dirección personalizada")
	return _("el servidor de actualizaciones ({host})").format(host=host) if host else _("el servidor de actualizaciones")


def _nombre_origen_descarga(url: str) -> str:
	"""Nombre del sitio del que se descarga el ZIP, para los mensajes de la descarga."""
	if _es_de_github(url):
		return "GitHub"
	if _host(url) == _host(URL_MANIFIESTO):
		return nombre_fuente(FUENTE_SERVIDOR, url)
	return _host(url) or _("el servidor de actualizaciones")


def _mayuscula(texto: str) -> str:
	return texto[:1].upper() + texto[1:]


def _leer_manifiesto(config: Configuracion, url: str, nombre: str | None = None) -> dict:
	"""Descarga y decodifica el ``version.json`` (sin mirar todavía la firma).

	:param nombre: la fuente, tal como se nombra en los mensajes.
	"""
	nombre = nombre or nombre_fuente("", url)
	_comprobar_url(url)
	try:
		with red.abrir(_config_red(config, url, TIEMPO_MANIFIESTO), url, cabeceras={"Cache-Control": "no-cache"},
				tiempo_s=TIEMPO_MANIFIESTO) as respuesta:
			datos = respuesta.read(MAX_MANIFIESTO + 1)
	except urllib.error.HTTPError as error:
		log.warning("La fuente de actualizaciones respondió %s a %s", error.code, red.redactar_url(url))
		raise ErrorRed(_("Al consultar {fuente}, el servidor respondió con el error {codigo}.").format(
			fuente=nombre, codigo=error.code)) from error
	except red.ErrorHTTP as error:
		if error.categoria == red.TIEMPO:
			raise ErrorRed(_("{fuente} no respondió a tiempo.").format(fuente=_mayuscula(nombre))) from error
		raise ErrorRed(
			_("No se pudo conectar con {fuente}. Compruebe la conexión a Internet.").format(fuente=nombre)
		) from error
	except (http.client.HTTPException, TimeoutError, OSError) as error:
		log.warning("Fallo al leer el manifiesto de %s", red.redactar_url(url), exc_info=True)
		raise ErrorRed(_("{fuente} no respondió a tiempo.").format(fuente=_mayuscula(nombre))) from error
	if len(datos) > MAX_MANIFIESTO:
		raise ErrorFirma(_("La información de versión de {fuente} es demasiado grande; se ignora.").format(fuente=nombre))
	try:
		manifiesto = json.loads(datos.decode("utf-8"))
	except (UnicodeDecodeError, ValueError) as error:
		raise ErrorFirma(_("La información de versión de {fuente} está dañada.").format(fuente=nombre)) from error
	if not isinstance(manifiesto, dict):
		raise ErrorFirma(_("La información de versión de {fuente} está dañada.").format(fuente=nombre))
	return manifiesto


def _espejos(manifiesto: dict) -> dict[str, str]:
	"""``espejos`` del manifiesto (ya con la firma comprobada): solo nombres y direcciones https válidos."""
	espejos = manifiesto.get(CAMPO_ESPEJOS)
	if espejos is None:
		return {}
	if not isinstance(espejos, dict):
		log.warning("El campo «%s» del manifiesto no es un diccionario; se ignora", CAMPO_ESPEJOS)
		return {}
	validos: dict[str, str] = {}
	for nombre, url in espejos.items():
		if not isinstance(nombre, str) or not isinstance(url, str):
			log.warning("Espejo no válido en el manifiesto: %r; se ignora", nombre)
			continue
		try:
			red.comprobar_url(url)
		except red.ErrorHTTP:
			log.warning("El espejo «%s» del manifiesto no es https; se ignora", nombre)
			continue
		validos[nombre] = url
	return validos


def _urls_del_zip(config: Configuracion, manifiesto: dict, url_manifiesto: str, archivo: str, fuente: str,
		ambas: bool) -> list[str]:
	"""Direcciones del ZIP en orden de preferencia según la fuente que dio el manifiesto.

	- servidor: ``url`` (o el ZIP junto al manifiesto); con «ambas», después ``espejos.github``.
	- github: ``espejos.github`` (o ``url``); con «ambas», después el ZIP del servidor.
	- personalizada (o una dirección explícita): ``url`` y después todos los ``espejos``.

	El SHA-256 y el tamaño del manifiesto se comprueban siempre, sea cual sea el host.
	"""
	base = str(manifiesto.get("url") or urllib.parse.urljoin(url_manifiesto, archivo))
	espejos = _espejos(manifiesto)
	github = espejos.get(ESPEJO_GITHUB)
	if fuente == FUENTE_SERVIDOR:
		urls = [base]
		if ambas and github:
			urls.append(github)
	elif fuente == FUENTE_GITHUB:
		urls = [github or base]
		if ambas:
			urls.append(str(manifiesto.get("url") or urllib.parse.urljoin(config.url_manifiesto, archivo)))
	else:
		urls = [base, *espejos.values()]
	return list(dict.fromkeys(urls))


def _info_desde_manifiesto(config: Configuracion, manifiesto: dict, url_manifiesto: str, fuente: str = FUENTE_SERVIDOR,
		ambas: bool = False) -> InfoActualizacion:
	"""Valida los campos (ya con la firma comprobada) y construye la información."""
	version = manifiesto.get("version")
	archivo = manifiesto.get("file")
	sha = str(manifiesto.get("sha256") or "").strip().lower()
	tamano = manifiesto.get("size")
	aplicacion = manifiesto.get("app")
	if aplicacion is not None and aplicacion != config.nombre_app:
		raise ErrorFirma(_("La versión publicada es de otra aplicación; se ignora."))
	try:
		clave_version(str(version))
	except VersionInvalida as error:
		raise ErrorFirma(_("El servidor publica una versión con formato no válido.")) from error
	if not isinstance(archivo, str) or not re.fullmatch(r"[\w.\-]+\.zip", archivo) or ".." in archivo:
		raise ErrorFirma(_("El nombre del paquete publicado no es válido."))
	if not re.fullmatch(r"[0-9a-f]{64}", sha):
		raise ErrorFirma(_("El paquete publicado no trae una huella SHA-256 válida."))
	if not isinstance(tamano, int) or isinstance(tamano, bool) or not 0 < tamano <= MAX_DESCARGA:
		raise ErrorFirma(_("El tamaño del paquete publicado no es válido."))
	urls = _urls_del_zip(config, manifiesto, url_manifiesto, archivo, fuente, ambas)
	_comprobar_url(urls[0])
	respaldo = []
	for url in urls[1:]:
		try:
			red.comprobar_url(url)
		except red.ErrorHTTP:
			log.warning("Dirección de respaldo no https; se ignora: %s", red.redactar_url(url))
			continue
		respaldo.append(url)
	return InfoActualizacion(
		version=str(version),
		archivo=archivo,
		url_zip=urls[0],
		sha256=sha,
		tamano=tamano,
		fecha=str(manifiesto.get("date") or ""),
		novedades=str(manifiesto.get("novedades") or "").strip(),
		fuente=fuente,
		urls_respaldo=tuple(respaldo),
	)


def fuente_elegida(config: Configuracion) -> tuple[str, str]:
	"""``(fuente, url_personalizada)`` vigentes: las de Preferencias si la configuración sabe leerlas."""
	fuente, personalizada = config.fuente, config.url_personalizada
	if config.preferencias is not None:
		try:
			fuente, personalizada = config.preferencias()
		except Exception:  # noqa: BLE001 - sin preferencias legibles se usa la fuente de la configuración
			log.warning("No se pudo leer la fuente de actualizaciones de las preferencias", exc_info=True)
	if fuente not in FUENTES:
		log.warning("Fuente de actualizaciones desconocida (%r); se usa el servidor", fuente)
		fuente = FUENTE_SERVIDOR
	return fuente, str(personalizada or "").strip()


def _fuentes_a_consultar(config: Configuracion, url_explicita: str | None) -> list[tuple[str, str]]:
	"""``[(fuente, url del manifiesto)]`` en el orden en que se consultan."""
	if url_explicita:
		return [("", url_explicita)]
	fuente, personalizada = fuente_elegida(config)
	if fuente == FUENTE_GITHUB:
		return [(FUENTE_GITHUB, config.url_github)]
	if fuente == FUENTE_AMBAS:
		return [(FUENTE_SERVIDOR, config.url_manifiesto), (FUENTE_GITHUB, config.url_github)]
	if fuente == FUENTE_PERSONALIZADA:
		if not personalizada:
			raise ErrorSinDireccion(_(
				"Ha elegido buscar las actualizaciones en una dirección personalizada, pero no la ha escrito. "
				"Escríbala en Preferencias, página Actualizaciones, o elija otra fuente."))
		return [(FUENTE_PERSONALIZADA, personalizada)]
	return [(FUENTE_SERVIDOR, config.url_manifiesto)]


def _consultar(config: Configuracion, fuente: str, url: str, ambas: bool) -> InfoActualizacion:
	"""Lee el manifiesto de UNA fuente, verifica su firma y valida sus campos.

	Los errores de firma o de formato dicen de qué fuente vienen.
	"""
	nombre = nombre_fuente(fuente, url)
	log.info("Consultando la fuente de actualizaciones «%s»: %s", fuente or "dirección explícita", red.redactar_url(url))
	manifiesto = _leer_manifiesto(config, url, nombre)
	try:
		verificar_firma(manifiesto, config.claves_publicas)
		return _info_desde_manifiesto(config, manifiesto, url, fuente, ambas)
	except ErrorActualizacion as error:
		log.warning("Manifiesto rechazado de %s: %s", red.redactar_url(url), error)
		raise type(error)(_("{fuente}: {mensaje}").format(fuente=_mayuscula(nombre), mensaje=error)) from error


def _error_de_todas(errores: list[ErrorActualizacion]) -> ErrorActualizacion:
	"""Un solo error cuando fallan todas las fuentes: del tipo del más grave (la firma antes que la red)."""
	principal = next((error for error in errores if not isinstance(error, ErrorRed)), errores[0])
	mensaje = " ".join([_("No se pudo comprobar en ninguna de las dos fuentes."), *(str(error) for error in errores)])
	nuevo = type(principal)(mensaje)
	nuevo.__cause__ = principal
	return nuevo


def comprobar(config: Configuracion, url_manifiesto: str | None = None, *, respetar_omitida: bool = False) -> InfoActualizacion | None:
	"""Consulta la fuente elegida y devuelve la versión nueva, o ``None`` si no la hay.

	Con la fuente «ambas» consulta el servidor y GitHub (en serie): si una falla se usa
	la otra sin molestar y, si responden las dos, gana la versión más nueva.

	:param url_manifiesto: una dirección concreta (pruebas); sin ella, la fuente de Preferencias.
	:param respetar_omitida: ``True`` en la comprobación periódica (no molesta con la
		versión que la persona pidió omitir); ``False`` en la manual.
	:raises ErrorActualizacion: red, firma, formato o anti-retroceso. La firma se
		verifica ANTES de mirar ningún otro campo, con cualquier fuente.
	"""
	fuentes = _fuentes_a_consultar(config, url_manifiesto)
	ambas = len(fuentes) > 1
	log.info("Comprobando actualizaciones en %s (versión instalada %s)",
		", ".join(f"{fuente or 'dirección explícita'} ({red.redactar_url(url)})" for fuente, url in fuentes), config.version_actual)
	encontradas: list[InfoActualizacion] = []
	errores: list[ErrorActualizacion] = []
	for fuente, url in fuentes:
		try:
			encontradas.append(_consultar(config, fuente, url, ambas))
		except ErrorActualizacion as error:
			if not ambas:
				raise
			log.warning("La fuente «%s» falló (%s); se usa la otra", fuente, error)
			errores.append(error)
	if not encontradas:
		raise _error_de_todas(errores)
	info = encontradas[0]
	for otra in encontradas[1:]:
		if es_mas_nueva(otra.version, info.version):
			info = otra
	log.info("Manifiesto elegido: versión %s de la fuente «%s» (descarga de %s)", info.version,
		info.fuente or "dirección explícita", red.redactar_url(info.url_zip))
	_actualizar_estado(config, ultima_comprobacion=datetime.now(timezone.utc).isoformat(timespec="seconds"))
	if not es_mas_nueva(info.version, config.version_actual):
		log.info("No hay versión nueva: la fuente «%s» ofrece %s", info.fuente or "dirección explícita", info.version)
		return None
	estado = leer_estado(config)
	confirmada = str(estado.get("version_confirmada") or "")
	try:
		if confirmada and comparar_versiones(info.version, confirmada) < 0:
			log.warning("Anti-rollback: el servidor ofrece %s, inferior a la confirmada %s", info.version, confirmada)
			raise ErrorRollback(
				_(
					"%(fuente)s ofrece la versión %(nueva)s, anterior a la %(confirmada)s que ya se instaló en este equipo. "
					"Por seguridad se rechaza."
				)
				% {"fuente": _mayuscula(nombre_fuente(info.fuente)), "nueva": info.version, "confirmada": confirmada}
			)
	except VersionInvalida:
		log.warning("Versión confirmada no válida en el estado (%r); se ignora", confirmada)
	if respetar_omitida and estado.get("version_omitida") == info.version:
		log.info("La versión %s está omitida por la persona", info.version)
		return None
	log.info("Versión nueva disponible: %s (%d bytes)", info.version, info.tamano)
	return info


# ════════════════════════════════════════════════════════════════════════════
# Descarga y verificación (app/core/descargas.py)
# ════════════════════════════════════════════════════════════════════════════


def _avisar(progreso: Progreso | None, fase: str, hecho: int, total: int) -> None:
	if progreso is None:
		return
	try:
		progreso(fase, hecho, total)
	except Exception:  # noqa: BLE001 - función ajena: un fallo al pintar el progreso no estropea la actualización
		log.debug("Fallo en la función de progreso", exc_info=True)


def sha256_de(ruta: Path) -> str:
	"""SHA-256 de un archivo leyendo por bloques de 1 MB."""
	return descargas.sha256_de(ruta)


def descargar(
	config: Configuracion,
	info: InfoActualizacion,
	progreso: Progreso | None = None,
	cancelado: Callable[[], bool] | Any = None,
) -> Path:
	"""Descarga el ZIP a ``data/temp/actualizacion/descarga`` y devuelve su ruta.

	Usa ``descargas.descargar`` de N2: la parte ya descargada se guarda como
	``.parcial`` y, si el servidor admite ``Range``, se reanuda desde ahí. Nunca
	se escriben más bytes de los anunciados en el manifiesto firmado. Si la
	descarga desde ``info.url_zip`` falla, prueba las direcciones de respaldo del
	manifiesto (el mismo ZIP en otro sitio) antes de rendirse.

	:param cancelado: función sin argumentos o ``TokenCancelacion``.
	"""
	return _descargar_con_respaldo(config, info, progreso, cancelado, verificar=False)


def _descargar_con_respaldo(config: Configuracion, info: InfoActualizacion, progreso: Progreso | None,
		cancelado: Callable[[], bool] | Any, *, verificar: bool) -> Path:
	"""Prueba cada dirección del ZIP; con ``verificar``, un paquete que no supera el SHA-256 también pasa a la siguiente.

	2.0.1: la parte ya descargada solo se reanuda desde la misma dirección (``_descargar_de``):
	al cambiar de dirección se empieza de cero, para no pegar bytes de dos servidores
	(el SHA-256 del manifiesto firmado lo comprobaría al final, pero se perdería la descarga).
	Cancelar nunca prueba otra dirección.
	"""
	urls = info.urls
	ultimo: ErrorActualizacion | None = None
	for indice, url in enumerate(urls):
		if indice:
			log.warning("Se prueba a descargar la actualización desde %s", red.redactar_url(url))
		try:
			ruta = _descargar_de(config, info, url, progreso, cancelado)
			if verificar:
				_avisar(progreso, "verificacion", 0, 1)
				verificar_paquete(ruta, info)
				_avisar(progreso, "verificacion", 1, 1)
		except (ErrorRed, ErrorVerificacion) as error:
			log.warning("Falló la descarga desde %s: %s", red.redactar_url(url), error)
			ultimo = error
			continue
		log.info("Actualización %s descargada de %s (fuente «%s»)", info.version, red.redactar_url(url), info.fuente or "explícita")
		return ruta
	raise ultimo or ErrorRed(_("El paquete publicado no tiene ninguna dirección de descarga."))


def _descargar_de(config: Configuracion, info: InfoActualizacion, url: str, progreso: Progreso | None,
		cancelado: Callable[[], bool] | Any) -> Path:
	carpeta = config.carpeta_trabajo / "descarga"
	carpeta.mkdir(parents=True, exist_ok=True)
	final = carpeta / info.archivo
	final.unlink(missing_ok=True)
	_comprobar_url(url)
	origen = _nombre_origen_descarga(url)
	_preparar_parcial(final, url)

	def al_progresar(hecho: int, total: int) -> None:
		_avisar(progreso, "descarga", hecho, info.tamano if total < 0 else total)

	try:
		ruta = descargas.descargar(_config_red(config, url, TIEMPO_DESCARGA), url, final,
			tamano=info.tamano, cancelacion=cancelado, al_progresar=al_progresar)
		_origen_parcial(final).unlink(missing_ok=True)
		return ruta
	except red.ErrorHTTP as error:
		if error.categoria == red.CANCELADO:
			raise ErrorCancelado(_("Descarga cancelada. Podrá continuarla más tarde.")) from error
		if error.categoria == red.HTTP and not error.estado:
			# descargas.py la lanza sin código HTTP cuando llega más de lo anunciado.
			raise ErrorVerificacion(_("El paquete descargado es mayor de lo anunciado; se descarta por seguridad.")) from error
		if error.categoria == red.HTTP:
			raise ErrorRed(_("Al descargar la actualización de {origen}, el servidor respondió con el error {codigo}.").format(
				origen=origen, codigo=error.estado)) from error
		raise ErrorRed(_("La descarga desde {origen} se interrumpió. Vuelva a intentarlo: continuará donde se quedó.").format(
			origen=origen)) from error


def _origen_parcial(final: Path) -> Path:
	"""Archivo junto al ``.parcial`` con la dirección de la que vienen sus bytes."""
	return final.with_name(final.name + ".parcial.origen")


def _preparar_parcial(final: Path, url: str) -> None:
	"""2.0.1: reanudar solo desde la misma dirección; si el ``.parcial`` es de otra (o no se sabe), se borra.

	``descargas.descargar`` reanuda con ``Range`` sobre lo que haya en el ``.parcial``: tras
	fallar una dirección y pasar a la siguiente, pediría a otro servidor el resto de un
	archivo empezado en el anterior.
	"""
	parcial = final.with_name(final.name + ".parcial")
	origen = _origen_parcial(final)
	try:
		anterior = origen.read_text(encoding="utf-8").strip() if origen.is_file() else ""
	except OSError:
		log.debug("No se pudo leer %s", origen, exc_info=True)
		anterior = ""
	if parcial.is_file() and anterior != url:
		log.info("La descarga a medias venía de otra dirección (%s); se empieza de cero desde %s",
			red.redactar_url(anterior) if anterior else "desconocida", red.redactar_url(url))
		parcial.unlink(missing_ok=True)
	try:
		origen.write_text(url, encoding="utf-8")
	except OSError:
		# Sin el archivo de origen la próxima vez se empieza de cero: más lento, pero seguro.
		log.warning("No se pudo anotar el origen de la descarga en %s", origen, exc_info=True)


def verificar_paquete(ruta: Path, info: InfoActualizacion) -> None:
	"""Comprueba tamaño y SHA-256; si no coinciden, BORRA el archivo y lo rechaza."""
	tamano = ruta.stat().st_size
	if tamano != info.tamano:
		ruta.unlink(missing_ok=True)
		raise ErrorVerificacion(_("El paquete descargado no tiene el tamaño anunciado; no se instalará."))
	real = sha256_de(ruta)
	if not hmac.compare_digest(real, info.sha256):
		log.error("SHA-256 incorrecto: esperado %s, obtenido %s", info.sha256, real)
		ruta.unlink(missing_ok=True)
		raise ErrorVerificacion(_("El paquete descargado no supera la verificación de integridad; no se instalará."))
	log.info("Paquete verificado: %d bytes, SHA-256 correcto", tamano)


# ════════════════════════════════════════════════════════════════════════════
# Extracción segura
# ════════════════════════════════════════════════════════════════════════════


def _partes_seguras(nombre: str) -> list[str]:
	"""Partes de una ruta del ZIP, o ``ErrorPaquete`` si es peligrosa."""
	if "\x00" in nombre:
		raise ErrorPaquete(_("El paquete contiene un nombre de archivo no válido."))
	normal = nombre.replace("\\", "/")
	if normal.startswith("/") or ":" in normal:
		raise ErrorPaquete(_("El paquete contiene una ruta absoluta (%s); se rechaza.") % nombre)
	partes = [parte for parte in normal.split("/") if parte not in ("", ".")]
	for parte in partes:
		if parte == "..":
			raise ErrorPaquete(_("El paquete intenta escribir fuera de su carpeta (%s); se rechaza.") % nombre)
		if parte != parte.rstrip(" ."):
			raise ErrorPaquete(_("El paquete contiene un nombre no válido en Windows (%s).") % nombre)
		if parte.split(".")[0].lower() in _NOMBRES_RESERVADOS:
			raise ErrorPaquete(_("El paquete contiene un nombre reservado de Windows (%s).") % nombre)
	return partes


def _destino_de_data(relativas: list[str], destino: Path, config: Configuracion) -> Path | None:
	"""Dónde va un archivo de ``data/`` del paquete, o ``None`` si es de la persona y se descarta.

	``data/<entrante>/...`` va a ``entrante/<carpeta de entrada>/...`` (el ``.bat``
	lo copia tal cual sobre ``data``); ``data/<actualizable>/...`` va a ``recursos/``.
	"""
	if len(relativas) < 3:
		return None
	subcarpeta = relativas[1].lower()
	entrantes = {nombre.lower(): valor for nombre, valor in config.data_entrante.items()}
	if subcarpeta in entrantes:
		return destino.joinpath("entrante", *entrantes[subcarpeta].split("/"), *relativas[2:])
	if subcarpeta in {nombre.lower() for nombre in config.data_actualizable}:
		return destino.joinpath("recursos", *relativas[1:])
	return None


def extraer_seguro(ruta_zip: Path, destino: Path, config: Configuracion, progreso: Progreso | None = None) -> Path:
	"""Extrae el ZIP en ``destino/programa``, ``destino/recursos`` y ``destino/entrante``.

	Primero valida TODAS las entradas y solo después escribe: un paquete con una
	sola entrada peligrosa se rechaza entero. Quita la carpeta raíz común
	(``zCommander/``) que pone ``empaquetar.py``. De ``data/`` solo acepta las
	subcarpetas de ``data_actualizable`` y ``data_entrante``; lo demás (config,
	plugins, cache...) se descarta.
	"""
	if destino.exists():
		shutil.rmtree(destino)
	programa = destino / "programa"
	programa.mkdir(parents=True)
	raiz_segura = destino.resolve()
	entradas: list[tuple[zipfile.ZipInfo, list[str]]] = []
	try:
		with zipfile.ZipFile(ruta_zip) as paquete:
			infos = paquete.infolist()
			if len(infos) > MAX_MIEMBROS:
				raise ErrorPaquete(_("El paquete contiene demasiados archivos; se rechaza."))
			vistos: set[str] = set()
			declarado = 0
			for info in infos:
				partes = _partes_seguras(info.filename)
				if stat.S_ISLNK(info.external_attr >> 16):
					raise ErrorPaquete(_("El paquete contiene enlaces simbólicos (%s); se rechaza.") % info.filename)
				if info.flag_bits & 0x1:
					raise ErrorPaquete(_("El paquete contiene archivos cifrados; se rechaza."))
				if info.is_dir() or not partes:
					continue
				clave = "/".join(partes).lower()
				if clave in vistos:
					raise ErrorPaquete(_("El paquete repite el archivo %s; se rechaza.") % info.filename)
				vistos.add(clave)
				declarado += info.file_size
				entradas.append((info, partes))
			if declarado > config.max_expandido:
				raise ErrorPaquete(_("El paquete ocupa demasiado al descomprimirse; se rechaza."))
			prefijo = 0
			primeras = {partes[0] for _info, partes in entradas}
			if len(primeras) == 1 and all(len(partes) > 1 for _info, partes in entradas):
				prefijo = 1
			escrito_total = 0
			for indice, (info, partes) in enumerate(entradas, start=1):
				relativas = partes[prefijo:]
				if relativas[0].lower() == "data":
					destino_archivo = _destino_de_data(relativas, destino, config)
					if destino_archivo is None:
						log.warning("Se descarta %s del paquete: los datos de la persona nunca se sustituyen", info.filename)
						continue
				else:
					destino_archivo = programa.joinpath(*relativas)
				if not destino_archivo.resolve().is_relative_to(raiz_segura):
					raise ErrorPaquete(_("El paquete intenta escribir fuera de su carpeta (%s); se rechaza.") % info.filename)
				destino_archivo.parent.mkdir(parents=True, exist_ok=True)
				with paquete.open(info) as origen, destino_archivo.open("wb") as salida:
					for bloque in iter(lambda origen=origen: origen.read(1024 * 1024), b""):
						escrito_total += len(bloque)
						if escrito_total > config.max_expandido:
							raise ErrorPaquete(_("El paquete ocupa demasiado al descomprimirse; se rechaza."))
						salida.write(bloque)
				_avisar(progreso, "extraccion", indice, len(entradas))
	except zipfile.BadZipFile as error:
		shutil.rmtree(destino, ignore_errors=True)
		raise ErrorPaquete(_("El paquete descargado está dañado.")) from error
	except BaseException:
		shutil.rmtree(destino, ignore_errors=True)
		raise
	if not (programa / config.ejecutable).is_file():
		shutil.rmtree(destino, ignore_errors=True)
		raise ErrorPaquete(_("El paquete no parece una versión de %s; no se instalará.") % config.nombre_app)
	log.info("Paquete extraído en %s (%d archivos)", destino, len(entradas))
	return destino


# ════════════════════════════════════════════════════════════════════════════
# Script de sustitución
# ════════════════════════════════════════════════════════════════════════════

# Plantilla del .bat. Reglas que la hacen robusta (todas comprobadas en las pruebas):
# - Todo el flujo con «goto»: dentro de bloques ( ) las %variables% se expanden al
#   leer el bloque entero y darían valores viejos.
# - Esperas con «ping -n 2 127.0.0.1» (≈1 s): «timeout» falla sin consola.
# - find/findstr/robocopy con ruta completa: un PATH con utilidades GNU tiene otro «find».
# - robocopy devuelve 0-7 si fue bien y 8 o más si falló.
# - La copia de la versión nueva NUNCA usa /MIR: no borra nada del destino.
# - «data» se salta por nombre SOLO en el primer nivel de la carpeta de la aplicación
#   (en lib/ puede haber carpetas llamadas data de otros paquetes).
# - Mensajes sin tildes: el registro se lee igual con cualquier página de códigos.
# - Los mensajes del registro nunca llevan rutas: «:anotar» las escribe sin comillas
#   y un «&» en una ruta partiría la orden.
# zCommander (5.2, 5.3): salud en dos fases (iniciado / ok), «salud sin confirmar»
# sin vuelta atrás si el proceso nuevo sigue vivo, carpetas de entrada de data
# (data/bin del paquete a data/bin/.entrante, que la vuelta atrás borra) y el modo
# «volver», que solo restaura el respaldo cuando la persona lo pide.
_PLANTILLA_BAT = r"""@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
rem Script de sustitucion generado por app/services/actualizador.py. No lo edite.
set "MODO={modo}"
set "APP={app}"
set "DATOS_APP=%APP%\data"
set "TRABAJO={trabajo}"
set "NUEVA=%TRABAJO%\nueva"
set "RESPALDO={respaldo}"
set "MARCADOR={marcador}"
set "MARCA_INICIO={marca_inicio}"
set "SIN_CONFIRMAR={sin_confirmar}"
set "RESULTADO={resultado}"
set "ARCHIVO_PID=%TRABAJO%\pid_nueva.txt"
set "REGISTRO={registro}"
set "EJECUTABLE={ejecutable}"
set "VERSION_NUEVA={version_nueva}"
set "VERSION_ACTUAL={version_actual}"
set "PID_APP={pid}"
set "ESPERA_CIERRE={espera_cierre}"
set "ESPERA_SALUD={espera_salud}"
set "ESPERA_SALUD_TOTAL={espera_salud_total}"
set "RECURSOS={recursos}"
set "ENTRANTES={entrantes}"
set "COMANDO={comando}"
set "SISTEMA=%SystemRoot%\System32"
set "ROBO=/R:2 /W:1 /NP /NFL /NDL /NJH /NJS"
set "MOTIVO=desconocido"
set "ESPERANDO=%TRABAJO%\esperando_salud.txt"
set "PID_SALUD="
rem Ruta del ejecutable para buscar copias abiertas de ESTA instalacion (PowerShell la lee del entorno).
set "RUTA_EXE=%APP%\%EJECUTABLE%"
set "POWERSHELL=%SISTEMA%\WindowsPowerShell\v1.0\powershell.exe"
set "CARPETA_APP_BUSCADA=%APP%\"
rem Entre comillas, | y ^ son literales: no se escapan.
set "COPIAS_ABIERTAS=Get-CimInstance Win32_Process | Where-Object { ($_.ExecutablePath -eq $env:RUTA_EXE -or ($_.CommandLine -and $_.CommandLine.Contains($env:CARPETA_APP_BUSCADA))) -and $_.Name -notmatch '^(cmd|conhost|powershell|robocopy|find|findstr|tasklist|ping|taskkill)' }"

call :anotar "Inicio (%MODO%): de %VERSION_ACTUAL% a %VERSION_NUEVA%"
if not exist "%APP%\%EJECUTABLE%" goto instalacion_no_valida
if "%MODO%"=="volver" goto comprobar_respaldo
if not exist "%NUEVA%\programa\%EJECUTABLE%" goto instalacion_no_valida
goto preparar_espera
:comprobar_respaldo
if not exist "%RESPALDO%\programa\%EJECUTABLE%" goto instalacion_no_valida

:preparar_espera
rem 1. Esperar a que la aplicacion se cierre (sin matarla nunca).
set /a INTENTOS=0
:esperar_cierre
"%SISTEMA%\tasklist.exe" /FI "PID eq %PID_APP%" /NH 2>nul | "%SISTEMA%\find.exe" " %PID_APP% " >nul
if errorlevel 1 goto cerrada
set /a INTENTOS+=1
if %INTENTOS% geq %ESPERA_CIERRE% goto no_se_cierra
ping -n 2 127.0.0.1 >nul
goto esperar_cierre

:cerrada
call :anotar "Aplicacion cerrada"
if "%MODO%"=="volver" goto volver_a_peticion
rem Una actualizacion nueva deja sin efecto un aviso de salud sin confirmar anterior.
del /f /q "%SIN_CONFIRMAR%" >nul 2>&1
rem 2. Copia de seguridad de la version actual, sin data (salvo sus recursos).
if exist "%RESPALDO%" rmdir /s /q "%RESPALDO%"
if exist "%RESPALDO%" goto fallo_respaldo
"%SISTEMA%\robocopy.exe" "%APP%" "%RESPALDO%\programa" %ROBO% >nul
if errorlevel 8 goto fallo_respaldo
for /f "delims=" %%D in ('dir /b /a:d "%APP%" 2^>nul') do if /I not "%%D"=="data" (
	"%SISTEMA%\robocopy.exe" "%APP%\%%D" "%RESPALDO%\programa\%%D" /E %ROBO% >nul
	if errorlevel 8 goto fallo_respaldo
)
for %%S in (%RECURSOS%) do if exist "%DATOS_APP%\%%S" (
	"%SISTEMA%\robocopy.exe" "%DATOS_APP%\%%S" "%RESPALDO%\recursos\%%S" /E %ROBO% >nul
	if errorlevel 8 goto fallo_respaldo
)
if not exist "%RESPALDO%\programa\%EJECUTABLE%" goto fallo_respaldo
call :anotar "Copia de seguridad hecha"

rem 3. Copiar la version nueva encima (sin borrar nada; data solo recibe recursos y entrantes).
del /f /q "%MARCADOR%" "%MARCA_INICIO%" "%ARCHIVO_PID%" >nul 2>&1
"%SISTEMA%\robocopy.exe" "%NUEVA%\programa" "%APP%" /E /IS /IT %ROBO% >nul
if errorlevel 8 goto fallo_copia
if not exist "%NUEVA%\recursos" goto copiar_entrantes
for /f "delims=" %%S in ('dir /b /a:d "%NUEVA%\recursos" 2^>nul') do (
	"%SISTEMA%\robocopy.exe" "%NUEVA%\recursos\%%S" "%DATOS_APP%\%%S" /E /IS /IT %ROBO% >nul
	if errorlevel 8 goto fallo_copia
)
:copiar_entrantes
rem Las carpetas de entrada (data\bin\.entrante) se vacian y reciben lo del paquete.
for %%E in (%ENTRANTES%) do if exist "%DATOS_APP%\%%E" rmdir /s /q "%DATOS_APP%\%%E"
if not exist "%NUEVA%\entrante" goto copiada
"%SISTEMA%\robocopy.exe" "%NUEVA%\entrante" "%DATOS_APP%" /E /IS /IT %ROBO% >nul
if errorlevel 8 goto fallo_copia
:copiada
call :anotar "Version nueva copiada; se lanza con {argumento}"

rem 4. Lanzar la version nueva guardando su PID (start no lo da; PowerShell si).
rem    Antes se avisa de la version esperada: si la persona abre la aplicacion a
rem    mano a la vez, la copia que quede abierta tambien escribe las marcas.
>"%ESPERANDO%" echo %VERSION_NUEVA%
{linea_lanzar}
set "NUEVO_PID="
if exist "%ARCHIVO_PID%" set /p NUEVO_PID=<"%ARCHIVO_PID%"
echo(%NUEVO_PID%| "%SISTEMA%\findstr.exe" /r /x "[0-9][0-9]*" >nul || set "NUEVO_PID="
if not defined NUEVO_PID goto sin_pid
call :anotar "Version nueva en marcha con PID %NUEVO_PID%; esperando su marca de inicio"

rem 5. Salud en dos fases: iniciado en ESPERA_SALUD s; despues ok hasta ESPERA_SALUD_TOTAL s.
set /a SEGUNDOS=0
:esperar_inicio
if exist "%MARCADOR%" goto comprobar_marcador
if exist "%MARCA_INICIO%" goto leer_inicio
"%SISTEMA%\tasklist.exe" /FI "PID eq %NUEVO_PID%" /NH 2>nul | "%SISTEMA%\find.exe" " %NUEVO_PID% " >nul
if errorlevel 1 goto nueva_cerrada
set /a SEGUNDOS+=1
if %SEGUNDOS% geq %ESPERA_SALUD% goto sin_salud
ping -n 2 127.0.0.1 >nul
goto esperar_inicio

:leer_inicio
set "M_PALABRA="
set "M_VERSION="
set "PID_SALUD="
for /f "usebackq tokens=1-3" %%A in ("%MARCA_INICIO%") do (
	set "M_PALABRA=%%A"
	set "M_VERSION=%%B"
	set "PID_SALUD=%%C"
)
if /I not "%M_PALABRA%"=="iniciado" goto inicio_incorrecto
if not "%M_VERSION%"=="%VERSION_NUEVA%" goto inicio_incorrecto
echo(%PID_SALUD%| "%SISTEMA%\findstr.exe" /r /x "[0-9][0-9]*" >nul || goto inicio_incorrecto
call :anotar "Version nueva iniciada con PID %PID_SALUD%; se espera su confirmacion"
:esperar_ok
if exist "%MARCADOR%" goto comprobar_marcador
"%SISTEMA%\tasklist.exe" /FI "PID eq %PID_SALUD%" /NH 2>nul | "%SISTEMA%\find.exe" " %PID_SALUD% " >nul
if errorlevel 1 goto inicio_cerrado
set /a SEGUNDOS+=1
if %SEGUNDOS% geq %ESPERA_SALUD_TOTAL% goto salud_sin_confirmar
ping -n 2 127.0.0.1 >nul
goto esperar_ok

:inicio_cerrado
ping -n 2 127.0.0.1 >nul
if exist "%MARCADOR%" goto comprobar_marcador
set "MOTIVO=se_cerro_sin_confirmar"
goto volver_atras

:inicio_incorrecto
set "MOTIVO=marcador_incorrecto"
goto matar_y_volver

:comprobar_marcador
ping -n 2 127.0.0.1 >nul
"%SISTEMA%\findstr.exe" /l /c:"ok %VERSION_NUEVA%" "%MARCADOR%" >nul && goto sana
set "MOTIVO=marcador_incorrecto"
goto matar_y_volver

:nueva_cerrada
ping -n 2 127.0.0.1 >nul
if exist "%MARCADOR%" goto comprobar_marcador
if exist "%MARCA_INICIO%" goto leer_inicio
rem La copia lanzada se cerro. Si queda otra copia de esta instalacion abierta
rem (la persona la abrio a mano), se siguen esperando sus marcas.
call :hay_copia_abierta
if errorlevel 1 goto nueva_cerrada_sin_copias
call :anotar "La copia lanzada se cerro, pero hay otra abierta; se espera su marcador"
:esperar_otra_copia
if exist "%MARCADOR%" goto comprobar_marcador
if exist "%MARCA_INICIO%" goto leer_inicio
set /a SEGUNDOS+=1
if %SEGUNDOS% geq %ESPERA_SALUD% goto sin_salud_otra
call :hay_copia_abierta
if errorlevel 1 goto nueva_cerrada_sin_copias
ping -n 2 127.0.0.1 >nul
goto esperar_otra_copia

:nueva_cerrada_sin_copias
if exist "%MARCADOR%" goto comprobar_marcador
if exist "%MARCA_INICIO%" goto leer_inicio
set "MOTIVO=se_cerro_sin_confirmar"
goto volver_atras

:sin_salud_otra
set "MOTIVO=sin_marcador_de_salud"
goto volver_atras

:sin_salud
set "MOTIVO=sin_marcador_de_salud"
:matar_y_volver
"%SISTEMA%\taskkill.exe" /F /T /PID %NUEVO_PID% >nul 2>&1
ping -n 3 127.0.0.1 >nul
goto volver_atras

:salud_sin_confirmar
if exist "%MARCADOR%" goto comprobar_marcador
rem La version nueva sigue abierta sin confirmar (la persona tarda en contestar algo o
rem la integracion sigue en marcha): NO se vuelve atras con sus archivos abiertos.
set "MOTIVO=salud_sin_confirmar"
call :anotar "Sin confirmacion en %ESPERA_SALUD_TOTAL% s con la version nueva abierta: no se vuelve atras y se conserva la anterior"
>"%SIN_CONFIRMAR%" echo salud sin confirmar %VERSION_NUEVA% %PID_SALUD% %VERSION_ACTUAL%
rmdir /s /q "%NUEVA%" >nul 2>&1
rmdir /s /q "%TRABAJO%\descarga" >nul 2>&1
del /f /q "%ARCHIVO_PID%" "%ESPERANDO%" "%MARCA_INICIO%" >nul 2>&1
call :resultado sin_confirmar
goto fin

:sin_pid
set "MOTIVO=no_se_pudo_lanzar"
goto volver_atras

:fallo_copia
set "MOTIVO=fallo_copia"
goto volver_atras

:volver_a_peticion
set "MOTIVO=a_peticion"
del /f /q "%SIN_CONFIRMAR%" >nul 2>&1
goto volver_atras

rem 6. Vuelta atras: se borra el programa (NUNCA data) y se restaura la copia.
:volver_atras
call :anotar "Vuelta atras (%MOTIVO%): se restaura %VERSION_ACTUAL%"
if not exist "%RESPALDO%\programa\%EJECUTABLE%" goto fallo_restaurar
rem Nunca se borra un programa en uso: se cierran antes las copias de ESTA
rem instalacion (con la aplicacion abierta, la restauracion quedaba a medias).
call :cerrar_copias_abiertas
for /f "delims=" %%F in ('dir /b /a:-d "%APP%" 2^>nul') do del /f /q /a "%APP%\%%F" >nul 2>&1
for /f "delims=" %%D in ('dir /b /a:d "%APP%" 2^>nul') do if /I not "%%D"=="data" rmdir /s /q "%APP%\%%D"
"%SISTEMA%\robocopy.exe" "%RESPALDO%\programa" "%APP%" /E /IS /IT %ROBO% >nul
if errorlevel 8 goto fallo_restaurar
if not exist "%RESPALDO%\recursos" goto restaurar_entrantes
for /f "delims=" %%S in ('dir /b /a:d "%RESPALDO%\recursos" 2^>nul') do (
	"%SISTEMA%\robocopy.exe" "%RESPALDO%\recursos\%%S" "%DATOS_APP%\%%S" /E /IS /IT %ROBO% >nul
	if errorlevel 8 goto fallo_restaurar
)
:restaurar_entrantes
rem Lo que trajo la version nueva para integrar no es de la anterior: se borra.
for %%E in (%ENTRANTES%) do if exist "%DATOS_APP%\%%E" rmdir /s /q "%DATOS_APP%\%%E"
call :anotar "Version %VERSION_ACTUAL% restaurada; se relanza"
call :limpiar
call :resultado revertida
start "" /D "%APP%" %COMANDO%
goto fin

:fallo_restaurar
call :anotar "ERROR GRAVE: no se pudo restaurar. La copia sigue en data\temp\version_anterior\programa"
call :resultado rota
goto fin

:fallo_respaldo
set "MOTIVO=fallo_copia_de_seguridad"
call :anotar "ERROR: fallo la copia de seguridad; la instalacion NO se ha tocado"
call :limpiar
call :resultado no_aplicada
start "" /D "%APP%" %COMANDO%
goto fin

:no_se_cierra
set "MOTIVO=la_aplicacion_no_se_cerro"
call :anotar "La aplicacion no se cerro en %ESPERA_CIERRE% s; se cancela sin tocar nada"
if not "%MODO%"=="volver" call :limpiar
call :resultado no_aplicada
goto fin

:instalacion_no_valida
set "MOTIVO=instalacion_no_valida"
call :anotar "ERROR: falta el ejecutable en la instalacion, en la version nueva o en la copia; no se toca nada"
call :resultado no_aplicada
goto fin

:sana
call :anotar "Arranque confirmado: actualizacion a %VERSION_NUEVA% completada"
set "MOTIVO=ninguno"
rmdir /s /q "%RESPALDO%" >nul 2>&1
call :limpiar
call :resultado correcta
goto fin

:fin
call :anotar "Fin del script"
endlocal
(goto) 2>nul & del /f /q "%~f0"

:anotar
>>"%REGISTRO%" echo [%date% %time%] %~1
exit /b 0

:limpiar
rmdir /s /q "%NUEVA%" >nul 2>&1
rmdir /s /q "%TRABAJO%\descarga" >nul 2>&1
del /f /q "%ARCHIVO_PID%" "%MARCADOR%" "%MARCA_INICIO%" "%ESPERANDO%" >nul 2>&1
exit /b 0

rem errorlevel 0 si hay alguna copia abierta de ESTA instalacion: su ejecutable, o un
rem proceso cuya linea de ordenes apunta a la carpeta (nunca cmd, PowerShell ni
rem herramientas del propio script). Se busca por ruta, no por nombre: otra copia
rem del programa en otra carpeta no cuenta.
:hay_copia_abierta
"%POWERSHELL%" -NoProfile -NonInteractive -Command "if (@(%COPIAS_ABIERTAS%).Count -gt 0) { exit 0 } else { exit 1 }" >nul 2>&1
exit /b %errorlevel%

:cerrar_copias_abiertas
call :hay_copia_abierta
if errorlevel 1 exit /b 0
call :anotar "Hay copias de la aplicacion abiertas; se cierran antes de restaurar"
"%POWERSHELL%" -NoProfile -NonInteractive -Command "%COPIAS_ABIERTAS% | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
set /a ESPERAS=0
:esperar_copias
call :hay_copia_abierta
if errorlevel 1 exit /b 0
set /a ESPERAS+=1
if %ESPERAS% geq 15 exit /b 0
ping -n 2 127.0.0.1 >nul
goto esperar_copias

:resultado
>"%RESULTADO%" echo estado=%~1
>>"%RESULTADO%" echo motivo=%MOTIVO%
>>"%RESULTADO%" echo version=%VERSION_NUEVA%
>>"%RESULTADO%" echo anterior=%VERSION_ACTUAL%
exit /b 0
"""


def _bat(texto: str) -> str:
	"""Escapa ``%`` para un .bat (en un .bat, ``%%`` es un ``%`` literal)."""
	return str(texto).replace("%", "%%")


def _ps(texto: str) -> str:
	"""Cadena de PowerShell entre comillas simples (la comilla se duplica)."""
	return "'" + str(texto).replace("'", "''") + "'"


def _linea_lanzar(config: Configuracion, archivo_pid: Path) -> str:
	"""Orden que lanza la versión nueva con PowerShell y guarda su PID.

	``start`` de cmd no devuelve el PID, y sin PID no se podría terminar una versión
	nueva colgada antes de restaurar. Las comillas dobles de los argumentos se
	construyen con ``[char]34`` para no romper las comillas de la línea de cmd.
	"""
	programa, *argumentos = config.comando or [str(config.carpeta_app / config.ejecutable)]
	piezas = [f"[char]34 + {_ps(argumento)} + [char]34" for argumento in argumentos]
	piezas.append(_ps(ARGUMENTO_TRAS_ACTUALIZAR))
	lista = " + ' ' + ".join(piezas)
	guion = (
		"$ErrorActionPreference = 'Stop'; "
		f"$p = Start-Process -FilePath {_ps(programa)} -ArgumentList ({lista}) "
		f"-WorkingDirectory {_ps(config.carpeta_app)} -PassThru; "
		f"[IO.File]::WriteAllText({_ps(archivo_pid)}, [string]$p.Id)"
	)
	return (
		'"%SISTEMA%\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -NonInteractive '
		f'-ExecutionPolicy Bypass -Command "{_bat(guion)}" >nul 2>&1'
	)


_NOMBRE_CARPETA = re.compile(r"[A-Za-z0-9_-]+")
_RUTA_ENTRANTE = re.compile(r"[A-Za-z0-9_-]+(?:/\.?[A-Za-z0-9_-]+)*")


def _comprobar_instalacion(config: Configuracion) -> None:
	"""Defensa antes de generar un script que borra y copia archivos."""
	carpeta = config.carpeta_app
	if carpeta.parent == carpeta:
		raise ErrorActualizacion(_("La aplicación está en la raíz de una unidad; no se actualiza automáticamente."))
	if not (carpeta / config.ejecutable).is_file():
		raise ErrorActualizacion(_("No se encuentra %s en la carpeta de la aplicación; no se puede actualizar.") % config.ejecutable)
	for nombre in config.data_actualizable:
		if not _NOMBRE_CARPETA.fullmatch(nombre):
			raise ErrorActualizacion(f"Nombre de subcarpeta de data no válido: {nombre!r}")
	for nombre, destino in config.data_entrante.items():
		if not _NOMBRE_CARPETA.fullmatch(nombre) or not _RUTA_ENTRANTE.fullmatch(destino):
			raise ErrorActualizacion(f"Carpeta de entrada de data no válida: {nombre!r} → {destino!r}")


def _generar_bat(config: Configuracion, *, modo: str, version_nueva: str, version_anterior: str) -> Path:
	"""Escribe ``data/temp/actualizacion/actualizar.bat`` (CRLF, UTF-8 sin BOM)."""
	_comprobar_instalacion(config)
	trabajo = config.carpeta_trabajo
	trabajo.mkdir(parents=True, exist_ok=True)
	config.registro_script.parent.mkdir(parents=True, exist_ok=True)
	for viejo in (config.marcador_salud, config.marca_inicio, config.archivo_resultado):
		viejo.unlink(missing_ok=True)
	comando = " ".join(f'"{parte}"' for parte in (config.comando or [str(config.carpeta_app / config.ejecutable)]))
	valores = {
		"modo": modo,
		"app": _bat(config.carpeta_app),
		"trabajo": _bat(trabajo),
		"respaldo": _bat(config.carpeta_respaldo),
		"marcador": _bat(config.marcador_salud),
		"marca_inicio": _bat(config.marca_inicio),
		"sin_confirmar": _bat(config.marca_sin_confirmar),
		"resultado": _bat(config.archivo_resultado),
		"registro": _bat(config.registro_script),
		"ejecutable": _bat(config.ejecutable),
		"version_nueva": _bat(version_nueva),
		"version_actual": _bat(version_anterior),
		"pid": str(int(config.pid_a_esperar or os.getpid())),
		"espera_cierre": str(int(config.espera_cierre)),
		"espera_salud": str(int(config.espera_salud)),
		"espera_salud_total": str(int(max(config.espera_salud_total, config.espera_salud))),
		"recursos": " ".join(config.data_actualizable),
		"entrantes": " ".join(destino.replace("/", "\\") for destino in config.data_entrante.values()),
		"comando": _bat(comando),
		"argumento": ARGUMENTO_TRAS_ACTUALIZAR,
		"linea_lanzar": _linea_lanzar(config, trabajo / "pid_nueva.txt"),
	}
	contenido = _PLANTILLA_BAT
	for clave, valor in valores.items():
		contenido = contenido.replace("{" + clave + "}", valor)
	ruta = trabajo / "actualizar.bat"
	ruta.write_bytes(contenido.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
	log.info("Script de sustitución (%s) preparado en %s", modo, ruta)
	return ruta


def preparar_sustitucion(config: Configuracion, info: InfoActualizacion) -> Path:
	"""Genera el ``.bat`` que sustituye la versión instalada por ``info.version``."""
	return _generar_bat(config, modo="sustituir", version_nueva=info.version, version_anterior=config.version_actual)


def lanzar_sustitucion(ruta_bat: Path) -> subprocess.Popen:
	"""Lanza el .bat oculto y desacoplado, para que sobreviva al cierre de la app.

	Fuera del Job de zCommander (como ``procesos.lanzar_independiente``, 14.9) pero
	SIN ventana de consola: una consola que aparece durante minutos le roba el foco
	al lector de pantalla. Se ejecuta con la carpeta del script como directorio de
	trabajo y como ``.\\actualizar.bat``: así ``cmd /c`` no interpreta comillas de una
	ruta que pueda contener ``&``, y con ``NoDefaultCurrentDirectoryInExePath``
	definida el nombre suelto «no se reconoce como un comando».
	"""
	crear_sin_ventana = 0x08000000
	nuevo_grupo = 0x00000200
	salir_del_job = 0x01000000
	cmd = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe")
	argumentos = {
		"cwd": str(ruta_bat.parent),
		"stdin": subprocess.DEVNULL,
		"stdout": subprocess.DEVNULL,
		"stderr": subprocess.DEVNULL,
		"close_fds": True,
	}
	orden = [cmd, "/d", "/c", ".\\" + ruta_bat.name]
	log.info("Lanzando el script de sustitución %s", ruta_bat)
	try:
		# Si la aplicación está dentro de un Job Object que mata a sus hijos al
		# cerrarse, hay que salir de él o el script moriría con ella.
		return subprocess.Popen(orden, creationflags=crear_sin_ventana | nuevo_grupo | salir_del_job, **argumentos)  # noqa: S603
	except OSError:
		log.warning("No se pudo salir del Job Object; el script se lanza sin esa bandera", exc_info=True)
		return subprocess.Popen(orden, creationflags=crear_sin_ventana | nuevo_grupo, **argumentos)  # noqa: S603


def descartar_preparada(config: Configuracion) -> None:
	"""Borra una actualización preparada que no se llegó a lanzar («No actualizar ahora» y cerrar)."""
	shutil.rmtree(config.carpeta_trabajo / "nueva", ignore_errors=True)
	(config.carpeta_trabajo / "actualizar.bat").unlink(missing_ok=True)


def descargar_y_preparar(
	config: Configuracion,
	info: InfoActualizacion,
	progreso: Progreso | None = None,
	cancelado: Callable[[], bool] | Any = None,
) -> Path:
	"""Descarga, verifica, extrae y genera el script. Pensada para un hilo de fondo.

	Devuelve la ruta del ``.bat``; después la interfaz llama a
	:func:`lanzar_sustitucion` y cierra la aplicación.
	"""
	if not puede_instalar(config):
		raise ErrorActualizacion(_("Esta copia se ejecuta desde el código fuente: no se sustituye automáticamente."))
	_comprobar_instalacion(config)
	config.carpeta_trabajo.mkdir(parents=True, exist_ok=True)
	libre = shutil.disk_usage(config.carpeta_trabajo).free
	if libre < info.tamano * 4:
		raise ErrorActualizacion(_("No hay espacio libre suficiente en el disco para actualizar."))
	ruta_zip = _descargar_con_respaldo(config, info, progreso, cancelado, verificar=True)
	extraer_seguro(ruta_zip, config.carpeta_trabajo / "nueva", config, progreso)
	ruta_zip.unlink(missing_ok=True)
	_avisar(progreso, "preparacion", 0, 1)
	ruta_bat = preparar_sustitucion(config, info)
	_avisar(progreso, "preparacion", 1, 1)
	return ruta_bat


# ════════════════════════════════════════════════════════════════════════════
# Marcas de salud y arranque
# ════════════════════════════════════════════════════════════════════════════


def _se_espera_esta_version(config: Configuracion) -> bool:
	"""¿Hay un script de sustitución esperando las marcas de esta versión?

	Si la persona abre la aplicación a mano justo cuando el script lanza la
	versión nueva, la que lanzó el script ve «otra instancia» y se cierra, y la
	que queda abierta no tiene ``--tras-actualizar``. Por eso cualquier copia de
	la versión esperada escribe las marcas.
	"""
	try:
		esperada = config.aviso_espera_salud.read_text(encoding="utf-8").strip()
	except OSError:
		return False
	return esperada == config.version_actual


def _escribir_atomico(ruta: Path, texto: str) -> None:
	ruta.parent.mkdir(parents=True, exist_ok=True)
	temporal = ruta.with_name(ruta.stem + ".tmp")
	temporal.write_text(texto, encoding="utf-8")
	os.replace(temporal, ruta)


def escribir_inicio(config: Configuracion, tras_actualizar: bool | None = None) -> bool:
	"""Escribe ``iniciado <versión> <PID>`` si un script la espera. Devuelve si la escribió."""
	if tras_actualizar is None:
		tras_actualizar = ARGUMENTO_TRAS_ACTUALIZAR in sys.argv
	if not tras_actualizar and not _se_espera_esta_version(config):
		return False
	try:
		_escribir_atomico(config.marca_inicio, f"iniciado {config.version_actual} {os.getpid()}\n")
		log.info("Marca de inicio escrita para la versión %s", config.version_actual)
		return True
	except OSError:
		log.exception("No se pudo escribir la marca de inicio: el script volverá a la versión anterior")
		return False


def marcar_inicio(tras_actualizar: bool) -> None:
	"""Paso 4 de 14.8: ``iniciado <versión> <PID>`` antes de aplicar ningún pendiente (5.2)."""
	try:
		escribir_inicio(configuracion_por_defecto(), tras_actualizar)
	except Exception:  # noqa: BLE001 - el actualizador nunca impide arrancar
		log.exception("Falló la marca de inicio del actualizador")


def confirmar_arranque(config: Configuracion, tras_actualizar: bool | None = None) -> bool:
	"""Anota la versión como confirmada y, si un script la espera, escribe ``ok <versión>``.

	Devuelve si escribió el marcador. Se llama tras mostrar la ventana (paso 10 de
	14.8, ya con el bucle de eventos en marcha): demuestra que la ventana se abrió,
	no solo que ``main.py`` empezó.
	"""
	if tras_actualizar is None:
		tras_actualizar = ARGUMENTO_TRAS_ACTUALIZAR in sys.argv
	confirmar_version(config)
	if not tras_actualizar and not _se_espera_esta_version(config):
		return False
	try:
		_escribir_atomico(config.marcador_salud, f"ok {config.version_actual}\n")
		_actualizar_estado(config, ultimo_ok=f"{config.version_actual} {os.getpid()}")
		log.info("Marcador de salud escrito para la versión %s", config.version_actual)
		return True
	except OSError:
		log.exception("No se pudo escribir el marcador de salud: el script volverá a la versión anterior")
		return False


def limpiar_trabajo(config: Configuracion) -> None:
	"""Borra los restos de actualizaciones terminadas, salvo descargas a medias y «salud sin confirmar»."""
	trabajo = config.carpeta_trabajo
	if not trabajo.is_dir():
		return
	conservar = {"descarga", config.marca_sin_confirmar.name}
	for elemento in trabajo.iterdir():
		if elemento.name in conservar or elemento.suffix.lower() == ".bat":
			continue  # la descarga parcial se reanuda; el .bat se borra solo
		try:
			if elemento.is_dir():
				shutil.rmtree(elemento)
			else:
				elemento.unlink()
		except OSError:
			log.debug("No se pudo borrar %s", elemento, exc_info=True)


def _resultado_anterior(config: Configuracion) -> tuple[str, str | None]:
	"""(estado, mensaje para la persona) de lo que dejó el script; ``("", None)`` si no hay nada."""
	ruta = config.archivo_resultado
	if not ruta.is_file():
		return "", None
	datos: dict[str, str] = {}
	try:
		for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
			clave, _separador, valor = linea.partition("=")
			datos[clave.strip()] = valor.strip()
		ruta.unlink()
	except OSError:
		log.warning("No se pudo leer el resultado de la actualización", exc_info=True)
		return "", None
	limpiar_trabajo(config)
	estado, version, motivo = datos.get("estado", ""), datos.get("version", "?"), datos.get("motivo", "")
	anterior = datos.get("anterior", config.version_actual)
	log.info("Resultado de la actualización anterior: %s (versión %s, motivo %s)", estado, version, motivo)
	if estado in ("correcta", "sin_confirmar"):
		return estado, None
	if estado == "revertida":
		omitir_version(config, version)
		if motivo == "a_peticion":
			return estado, _(
				"Se ha vuelto a la versión %(actual)s de zCommander, como pidió; la %(nueva)s no se volverá a ofrecer sola. "
				"Sus datos no se han tocado."
			) % {"nueva": version, "actual": anterior}
		return estado, _(
			"La versión %(nueva)s no arrancó correctamente y se ha vuelto a la versión %(actual)s. "
			"Sus datos no se han tocado. Los detalles están en data/logs/actualizacion.log."
		) % {"nueva": version, "actual": anterior}
	if estado == "no_aplicada":
		if motivo == "la_aplicacion_no_se_cerro":
			return estado, _(
				"La actualización a la versión %s no se aplicó porque zCommander no llegó a cerrarse. "
				"Puede volver a intentarlo desde Ayuda, Buscar actualizaciones."
			) % version
		return estado, _(
			"La actualización a la versión %s no se aplicó y la instalación no se ha tocado. "
			"Los detalles están en data/logs/actualizacion.log."
		) % version
	return estado, _("La actualización a la versión %s tuvo un problema. Consulte data/logs/actualizacion.log.") % version


def leer_resultado_anterior(config: Configuracion) -> str | None:
	"""Lee lo que dejó el script y devuelve un mensaje para la persona (o ``None``).

	Si la versión nueva no arrancó, la omite para que la comprobación periódica no
	la vuelva a ofrecer en bucle.
	"""
	return _resultado_anterior(config)[1]


# ── «Salud sin confirmar» (5.2) ────────────────────────────────────────────────


@dataclass(frozen=True)
class SinConfirmar:
	"""El script se cansó de esperar ``ok`` de esta versión con su proceso vivo."""

	version: str
	pid: int
	anterior: str


def leer_sin_confirmar(config: Configuracion) -> SinConfirmar | None:
	"""La marca ``salud sin confirmar <versión> <PID> <anterior>``, o ``None``."""
	try:
		partes = config.marca_sin_confirmar.read_text(encoding="utf-8", errors="replace").split()
	except OSError:
		return None
	if len(partes) != 6 or partes[:3] != ["salud", "sin", "confirmar"] or not partes[4].isdigit():
		log.warning("Marca de salud sin confirmar no válida: %r", partes)
		config.marca_sin_confirmar.unlink(missing_ok=True)
		return None
	return SinConfirmar(partes[3], int(partes[4]), partes[5])


def _cerrar_sin_confirmar(config: Configuracion, con_respaldo: bool) -> None:
	config.marca_sin_confirmar.unlink(missing_ok=True)
	if con_respaldo:
		shutil.rmtree(config.carpeta_respaldo, ignore_errors=True)


def _confirmar_integracion() -> None:
	"""Componentes de 6.7: lo integrado se da por bueno (dependencia declarada hacia CO, 19.3)."""
	try:
		from app.services.componentes import integrar

		integrar.confirmar_integracion()
	except Exception:  # noqa: BLE001 - un fallo de los componentes no deshace la actualización confirmada
		log.exception("Falló componentes.confirmar_integracion")


def seguir_con_esta_version(config: Configuracion) -> None:
	"""«Seguir con esta versión»: se confirma, se borra la marca y el respaldo de la anterior."""
	confirmar_version(config)
	_actualizar_estado(config, ultimo_ok=f"{config.version_actual} {os.getpid()}")
	_cerrar_sin_confirmar(config, con_respaldo=True)
	_confirmar_integracion()
	log.info("La persona sigue con la versión %s sin confirmar", config.version_actual)


def preparar_vuelta_atras(config: Configuracion) -> Path:
	"""«Volver a la versión anterior»: genera el ``.bat`` en modo «volver» (lo lanza la interfaz y sale)."""
	pendiente = leer_sin_confirmar(config)
	if pendiente is None or pendiente.version != config.version_actual:
		raise ErrorActualizacion(_("No hay ninguna versión anterior guardada a la que volver."))
	if not (config.carpeta_respaldo / "programa" / config.ejecutable).is_file():
		raise ErrorActualizacion(_("No se encuentra la copia de la versión anterior; no se puede volver a ella."))
	if not puede_instalar(config):
		raise ErrorActualizacion(_("Esta copia se ejecuta desde el código fuente: no se sustituye automáticamente."))
	return _generar_bat(config, modo="volver", version_nueva=config.version_actual, version_anterior=pendiente.anterior)


@dataclass(frozen=True)
class ResultadoArranque:
	"""Lo que la interfaz tiene que decir tras :func:`al_arrancar`."""

	instalada: str | None = None
	"""Versión que acaba de confirmar su salud tras actualizar (suena ``act.instalada``)."""
	mensaje: str | None = None
	"""Resultado de una actualización anterior que no salió bien (esencial)."""
	revertida: bool = False
	"""El mensaje es de una vuelta atrás (suena ``act.revertida``)."""
	sin_confirmar: SinConfirmar | None = None
	"""Un arranque anterior de esta versión no llegó a ``ok``: preguntar si se vuelve atrás."""


def procesar_arranque(config: Configuracion, tras_actualizar: bool) -> ResultadoArranque:
	"""Resultado de la actualización anterior, «salud sin confirmar» y marca ``ok`` (5.2, 5.4)."""
	estado, mensaje = _resultado_anterior(config)
	revertida = estado == "revertida"
	pendiente = leer_sin_confirmar(config)
	if pendiente is not None:
		ultimo_ok = str(leer_estado(config).get("ultimo_ok") or "")
		if pendiente.version != config.version_actual:
			log.warning("Marca de salud sin confirmar de otra versión (%s); se descarta", pendiente.version)
			_cerrar_sin_confirmar(config, con_respaldo=False)
			pendiente = None
		elif ultimo_ok == f"{pendiente.version} {pendiente.pid}":
			# Aquel arranque sí llegó a «ok» (justo cuando el script se cansaba de esperar).
			_cerrar_sin_confirmar(config, con_respaldo=True)
			pendiente = None
		elif pendiente.pid != os.getpid():
			log.warning("La versión %s no confirmó su salud en un arranque anterior: se pregunta", pendiente.version)
			return ResultadoArranque(mensaje=mensaje, revertida=revertida, sin_confirmar=pendiente)
	escrito = confirmar_arranque(config, tras_actualizar)
	if pendiente is not None:  # el mismo proceso al que el script dejó de esperar llega por fin a «ok»
		_cerrar_sin_confirmar(config, con_respaldo=True)
	instalada = config.version_actual if escrito else None
	if instalada:
		_confirmar_integracion()
	return ResultadoArranque(instalada=instalada, mensaje=mensaje, revertida=revertida)


_oyente_arranque: list[Callable[[ResultadoArranque], None] | None] = [None]
_ultimo_arranque: list[ResultadoArranque | None] = [None]


def fijar_oyente_arranque(funcion: Callable[[ResultadoArranque], None] | None) -> None:
	"""La interfaz (``actualizar_ac.instalar``) recibe aquí lo que tiene que anunciar tras :func:`al_arrancar`."""
	_oyente_arranque[0] = funcion


def ultimo_arranque() -> ResultadoArranque | None:
	return _ultimo_arranque[0]


def al_arrancar(tras_actualizar: bool) -> None:
	"""Paso 10 de 14.8, tras mostrar la ventana: marca ``ok``, componentes y avisos (5.4)."""
	try:
		resultado = procesar_arranque(configuracion_por_defecto(), tras_actualizar)
	except Exception:  # noqa: BLE001 - el actualizador nunca impide usar la aplicación
		log.exception("Falló el arranque del actualizador")
		return
	_ultimo_arranque[0] = resultado
	oyente = _oyente_arranque[0]
	if oyente is not None:
		try:
			oyente(resultado)
		except Exception:  # noqa: BLE001 - la interfaz no impide confirmar
			log.exception("Falló el aviso del arranque del actualizador")
		return
	# Sin interfaz enganchada (instalar falló): al menos los sonidos de 5.4.
	try:
		from app.services.sonidos import servicio

		if resultado.instalada:
			servicio.sonar("act.instalada")
		if resultado.revertida:
			servicio.sonar("act.revertida")
	except Exception:  # noqa: BLE001 - sin sonidos se sigue igual
		log.debug("No se pudo pedir el sonido del actualizador", exc_info=True)


# ════════════════════════════════════════════════════════════════════════════
# Comprobación periódica compartida (5.4)
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Novedad:
	"""Lo que una comprobación periódica encontró y hay que anunciar."""

	origen: str
	texto: str
	esencial: bool


_candado = threading.Lock()
_comprobaciones: dict[str, tuple[Callable[[Any], list[Novedad]], Callable[[], bool]]] = {}


def registrar_comprobacion(nombre: str, funcion: Callable[[Any], list[Novedad]], activa: Callable[[], bool]) -> None:
	"""Suma una comprobación a la pasada periódica de la aplicación (5.4).

	:param funcion: recibe el ``TokenCancelacion`` de la pasada y devuelve lo que
		hay que anunciar. Se ejecuta en un hilo de trabajo; lleva su propio
		intervalo si lo necesita (CO, en días).
	:param activa: si devuelve falso, esta vez no se llama a ``funcion``.
	Registrar dos veces el mismo nombre sustituye la anterior.
	"""
	with _candado:
		_comprobaciones[nombre] = (funcion, activa)


def comprobaciones() -> dict[str, tuple[Callable[[Any], list[Novedad]], Callable[[], bool]]]:
	with _candado:
		return dict(_comprobaciones)


def quitar_comprobacion(nombre: str) -> None:
	with _candado:
		_comprobaciones.pop(nombre, None)


@dataclass(frozen=True)
class ResultadoPasada:
	"""Lo que encontró una pasada periódica: la versión nueva (si la hay) y las novedades de CO y PL."""

	info: InfoActualizacion | None = None
	novedades: tuple[Novedad, ...] = ()


def toca_pasada(config: Configuracion, intervalo_horas: float) -> bool:
	"""¿Pasó el intervalo desde la última pasada? Se guarda en ``data/config``: reiniciar no fuerza otra."""
	ultima = leer_estado(config).get("ultima_pasada")
	if not ultima:
		return True
	try:
		transcurrido = (datetime.now(timezone.utc) - datetime.fromisoformat(str(ultima))).total_seconds()
	except (TypeError, ValueError):
		log.debug("Fecha de la última pasada no válida: %r", ultima)
		return True
	return transcurrido >= intervalo_horas * 3600 or transcurrido < 0


def _cancelada(token: Any) -> bool:
	if token is None:
		return False
	valor = getattr(token, "cancelado", None)
	if valor is None:
		return bool(getattr(token, "is_set", lambda: False)())
	return bool(valor() if callable(valor) else valor)


#: 2.0.1: ya se avisó en esta sesión de la fuente personalizada sin dirección (``pasada``).
_avisado_sin_direccion = [False]


def pasada(config: Configuracion, token: Any = None, *, comprobar_app: bool = True) -> ResultadoPasada:
	"""Una pasada de la comprobación periódica, en un hilo de trabajo.

	La aplicación (si ``comprobar_app``, que respeta la versión omitida) y después
	cada comprobación registrada que esté activa. Los fallos solo se registran: no
	se molesta a la persona por no tener conexión.
	"""
	info = None
	if comprobar_app:
		try:
			info = comprobar(config, respetar_omitida=True)
		except ErrorSinDireccion as error:
			# 2.0.1: no es un corte de red pasajero: fallaría siempre. Se avisa en el registro una
			# vez por sesión (las demás pasadas, como información) para que se pueda encontrar.
			if not _avisado_sin_direccion[0]:
				_avisado_sin_direccion[0] = True
				log.warning("La comprobación periódica de actualizaciones no puede hacerse: %s", error)
			else:
				log.info("Comprobación periódica de la aplicación sin éxito: %s", error)
		except ErrorActualizacion as error:
			log.info("Comprobación periódica de la aplicación sin éxito: %s", error)
		except Exception:  # noqa: BLE001 - una pasada nunca rompe la aplicación
			log.exception("Fallo inesperado en la comprobación periódica")
	novedades: list[Novedad] = []
	for nombre, (funcion, activa) in comprobaciones().items():
		if _cancelada(token):
			break
		try:
			if not activa():
				continue
			encontradas = funcion(token) or []
		except Exception:  # noqa: BLE001 - la comprobación de otro bloque no impide las demás
			log.exception("Falló la comprobación periódica «%s»", nombre)
			continue
		novedades.extend(novedad for novedad in encontradas if isinstance(novedad, Novedad))
	if not _cancelada(token):
		_actualizar_estado(config, ultima_pasada=datetime.now(timezone.utc).isoformat(timespec="seconds"))
	return ResultadoPasada(info, tuple(novedades))
