# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sitios FTP, FTPS y SFTP guardados y la base común de los proveedores remotos.

Por qué está todo aquí:

- Los sitios (``data/config/conexiones.json``) se guardan SIN contraseñas: las
  contraseñas y las frases de las claves privadas van cifradas con DPAPI en
  ``secretos.dat`` como ``ftp:<id>:contrasena`` y ``ftp:<id>:frase`` (diseño
  10 y 14). Al eliminar un sitio se borran sus secretos.
- ``ProveedorRemoto`` reúne lo que comparten ``ftp.py`` y ``sftp.py``: rutas
  remotas con «/», cómo se consigue la contraseña (la del sitio guardado, la
  de un sitio que coincide con una dirección escrita o preguntándola), cómo se
  confirma la huella de un servidor y a quién se pregunta (el ``Decisor`` de
  la interfaz, siempre desde un hilo de trabajo).
- Las direcciones ``ftp://usuario@servidor/carpeta`` se interpretan aquí
  (``analizar_url``) y los proveedores vivos se reutilizan por servidor y
  usuario (``reutilizar``): volver atrás en el historial no abre otra conexión
  ni vuelve a pedir la contraseña.

Nada de este módulo escribe una contraseña en el registro: solo nombres de
sitio, servidores y usuarios.
"""

from __future__ import annotations

import atexit
import base64
import builtins
import hashlib
import logging
import posixpath
import threading
import uuid
import weakref
from abc import abstractmethod
from dataclasses import asdict, dataclass, field, fields
from urllib.parse import unquote, urlsplit

from app.core import almacen_json
from app.services.vfs import base

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ARCHIVO = "conexiones.json"
ARCHIVO_HUELLAS_TLS = "hosts_conocidos.json"
VERSION = 1

PROTOCOLOS = ("ftp", "ftps", "sftp")
PUERTOS = {"ftp": 21, "ftps": 21, "sftp": 22}
CODIFICACIONES = ("utf-8", "latin-1")
TIEMPO_MINIMO, TIEMPO_MAXIMO = 5, 600
USUARIOS_ANONIMOS = ("", "anonymous", "ftp")

#: Valor de ``contrasena``/``frase`` que significa «no cambiar lo guardado».
MANTENER = object()


def nombre_protocolo(protocolo: str) -> str:
	"""Texto para la persona de cada protocolo."""
	return {
		"ftp": _("FTP"),
		"ftps": _("FTP con TLS explícito (FTPS)"),
		"sftp": _("SFTP (SSH)"),
	}.get(protocolo, protocolo)


def clave_secreto(id_sitio: str, que: str = "contrasena") -> str:
	"""Nombre del secreto de un sitio en ``secretos.dat`` (``que``: «contrasena» o «frase»)."""
	return f"ftp:{id_sitio}:{que}"


# ── Sitio ────────────────────────────────────────────────────────────────────


@dataclass
class Sitio:
	"""Un sitio del gestor de conexiones (sin contraseña: esa va en ``secretos.dat``)."""

	nombre: str = ""
	protocolo: str = "ftp"
	servidor: str = ""
	puerto: int = 21
	usuario: str = ""
	guardar_contrasena: bool = True
	carpeta: str = "/"
	pasivo: bool = True
	codificacion: str = "utf-8"
	tiempo_espera_s: int = 30
	clave_privada: str = ""
	aviso_sin_cifrar_mostrado: bool = False
	id: str = field(default_factory=lambda: uuid.uuid4().hex)

	@classmethod
	def desde_dict(cls, datos: dict) -> Sitio:
		"""Tolerante: ignora claves desconocidas y corrige tipos que no cuadran."""
		conocidos = {f.name for f in fields(cls)}
		limpio = {k: v for k, v in datos.items() if k in conocidos}
		sitio = cls(**limpio)
		if sitio.protocolo not in PROTOCOLOS:
			sitio.protocolo = "ftp"
		try:
			sitio.puerto = int(sitio.puerto)
		except (TypeError, ValueError):
			sitio.puerto = PUERTOS[sitio.protocolo]
		try:
			sitio.tiempo_espera_s = int(sitio.tiempo_espera_s)
		except (TypeError, ValueError):
			sitio.tiempo_espera_s = 30
		if sitio.codificacion not in CODIFICACIONES:
			sitio.codificacion = "utf-8"
		sitio.carpeta = normalizar_remota(sitio.carpeta or "/")
		return sitio

	def a_dict(self) -> dict:
		return asdict(self)

	@property
	def anonimo(self) -> bool:
		return self.usuario.strip().lower() in USUARIOS_ANONIMOS and self.protocolo != "sftp"

	def url(self) -> str:
		"""``ftp://usuario@servidor:puerto/carpeta`` (nunca con la contraseña)."""
		return componer_url(self.protocolo, self.servidor, self.puerto, self.usuario, self.carpeta)

	def describir(self) -> str:
		"""«Mi web, FTP, usuario@servidor» para la lista del gestor."""
		quien = f"{self.usuario}@{self.servidor}" if self.usuario else self.servidor
		return f"{self.nombre}, {nombre_protocolo(self.protocolo)}, {quien}"


def validar(sitio: Sitio) -> tuple[str, str] | None:
	"""``(campo, motivo)`` del primer dato que no vale, o ``None`` si el sitio es correcto.

	``campo`` es el nombre del atributo, para que el diálogo lleve el foco allí.
	"""
	if not sitio.nombre.strip():
		return "nombre", _("Escriba un nombre para el sitio.")
	if sitio.protocolo not in PROTOCOLOS:
		return "protocolo", _("Elija un protocolo.")
	servidor = sitio.servidor.strip()
	if not servidor:
		return "servidor", _("Escriba el nombre o la dirección del servidor.")
	if any(c in servidor for c in " /\\@") or "://" in servidor:
		return "servidor", _("Escriba solo el nombre del servidor, sin «ftp://», barras, espacios ni usuario.")
	if not 1 <= int(sitio.puerto) <= 65535:
		return "puerto", _("El puerto debe estar entre 1 y 65535.")
	if any(c in sitio.usuario for c in "\r\n"):
		return "usuario", _("El usuario no puede tener saltos de línea.")
	if sitio.protocolo == "sftp" and not sitio.usuario.strip():
		return "usuario", _("SFTP necesita un nombre de usuario.")
	if any(c in sitio.carpeta for c in "\r\n"):
		return "carpeta", _("La carpeta no puede tener saltos de línea.")
	if sitio.codificacion not in CODIFICACIONES:
		return "codificacion", _("Elija la codificación de los nombres.")
	if not TIEMPO_MINIMO <= int(sitio.tiempo_espera_s) <= TIEMPO_MAXIMO:
		return "tiempo_espera_s", _("El tiempo de espera debe estar entre {a} y {b} segundos.").format(a=TIEMPO_MINIMO, b=TIEMPO_MAXIMO)
	return None


# ── Almacén de sitios ────────────────────────────────────────────────────────


def _secretos_por_defecto():
	from app.services.vfs import resolver

	secretos = resolver.servicios().secretos
	if secretos is not None:
		return secretos
	from app.core.secretos import obtener_secretos

	return obtener_secretos()


class Conexiones:
	"""Lee y guarda los sitios. Cada método vuelve a leer el archivo (es pequeño).

	Así varias ventanas o hilos (el gestor, la conexión rápida) ven siempre lo
	último guardado sin cachés que se desincronicen.
	"""

	_candado = threading.RLock()

	def __init__(self, secretos=None, carpeta=None) -> None:
		self._secretos = secretos
		self._carpeta = carpeta

	@property
	def secretos(self):
		if self._secretos is None:
			self._secretos = _secretos_por_defecto()
		return self._secretos

	# Lectura ----------------------------------------------------------------

	def _leer(self) -> list[Sitio]:
		datos = almacen_json.leer(ARCHIVO, {"version": VERSION, "sitios": []}, self._carpeta)
		sitios = []
		for bruto in datos.get("sitios") or []:
			if isinstance(bruto, dict):
				try:
					sitios.append(Sitio.desde_dict(bruto))
				except (TypeError, ValueError):
					log.warning("Sitio dañado en %s; se omite", ARCHIVO, exc_info=True)
		return sitios

	def _escribir(self, sitios: list[Sitio]) -> None:
		almacen_json.escribir(ARCHIVO, {"version": VERSION, "sitios": [s.a_dict() for s in sitios]}, self._carpeta)

	def sitios(self) -> list[Sitio]:
		"""Sitios ordenados por nombre (sin distinguir mayúsculas)."""
		with self._candado:
			return sorted(self._leer(), key=lambda s: s.nombre.casefold())

	def obtener(self, id_sitio: str) -> Sitio | None:
		with self._candado:
			return next((s for s in self._leer() if s.id == id_sitio), None)

	def buscar(self, protocolo: str, servidor: str, puerto: int, usuario: str) -> Sitio | None:
		"""Sitio guardado para una dirección escrita a mano (FTP y FTPS cuentan como el mismo servidor)."""
		familia = "sftp" if protocolo == "sftp" else "ftp"
		with self._candado:
			for sitio in self._leer():
				if ("sftp" if sitio.protocolo == "sftp" else "ftp") != familia:
					continue
				if sitio.servidor.casefold() == servidor.casefold() and int(sitio.puerto) == int(puerto) and \
						sitio.usuario == usuario:
					return sitio
		return None

	def contrasena(self, id_sitio: str) -> str | None:
		return self.secretos.obtener(clave_secreto(id_sitio, "contrasena"))

	def frase(self, id_sitio: str) -> str | None:
		return self.secretos.obtener(clave_secreto(id_sitio, "frase"))

	def tiene_contrasena(self, id_sitio: str) -> bool:
		return clave_secreto(id_sitio, "contrasena") in self.secretos.nombres()

	def tiene_frase(self, id_sitio: str) -> bool:
		return clave_secreto(id_sitio, "frase") in self.secretos.nombres()

	# Escritura --------------------------------------------------------------

	def guardar(self, sitio: Sitio, contrasena=MANTENER, frase=MANTENER) -> Sitio:
		"""Crea o actualiza ``sitio`` (por su ``id``).

		:param contrasena: texto nuevo, ``""`` o ``None`` para borrarla, o ``MANTENER``.
			Si el sitio no guarda la contraseña, se borra la que hubiera.
		:raises ValueError: si el sitio no es válido (con el motivo).
		:raises OSError: si no se pudo escribir el archivo.
		"""
		problema = validar(sitio)
		if problema is not None:
			raise ValueError(problema[1])
		sitio.servidor = sitio.servidor.strip()
		sitio.carpeta = normalizar_remota(sitio.carpeta or "/")
		with self._candado:
			sitios = [s for s in self._leer() if s.id != sitio.id]
			anterior = self.obtener(sitio.id)
			if anterior is not None and (anterior.servidor != sitio.servidor or anterior.usuario != sitio.usuario
					or anterior.protocolo != sitio.protocolo):
				# Otro servidor u otro usuario: el aviso de FTP sin cifrar vuelve a tener sentido.
				sitio.aviso_sin_cifrar_mostrado = False
			sitios.append(sitio)
			self._escribir(sitios)
			cambios: dict[str, str | None] = {}
			if not sitio.guardar_contrasena:
				cambios[clave_secreto(sitio.id, "contrasena")] = None
				cambios[clave_secreto(sitio.id, "frase")] = None
			else:
				if contrasena is not MANTENER:
					cambios[clave_secreto(sitio.id, "contrasena")] = contrasena or None
				if frase is not MANTENER:
					cambios[clave_secreto(sitio.id, "frase")] = frase or None
			if cambios:
				self.secretos.guardar_varios(cambios)
		log.info("Sitio guardado: %s (%s)", sitio.nombre, sitio.protocolo)
		return sitio

	def duplicar(self, id_sitio: str) -> Sitio | None:
		"""Copia del sitio con otro id y «(copia)» en el nombre, con sus secretos."""
		with self._candado:
			original = self.obtener(id_sitio)
			if original is None:
				return None
			copia = Sitio.desde_dict({**original.a_dict(), "id": uuid.uuid4().hex})
			nombres = {s.nombre.casefold() for s in self._leer()}
			candidato = _("{n} (copia)").format(n=original.nombre)
			numero = 2
			while candidato.casefold() in nombres:
				candidato = _("{n} (copia {i})").format(n=original.nombre, i=numero)
				numero += 1
			copia.nombre = candidato
			contrasena = self.contrasena(id_sitio) if original.guardar_contrasena else None
			frase = self.frase(id_sitio) if original.guardar_contrasena else None
			return self.guardar(copia, contrasena if contrasena else MANTENER, frase if frase else MANTENER)

	def eliminar(self, id_sitio: str) -> bool:
		"""Quita el sitio y BORRA sus secretos. ``False`` si no existía."""
		with self._candado:
			sitios = self._leer()
			restantes = [s for s in sitios if s.id != id_sitio]
			if len(restantes) == len(sitios):
				return False
			self._escribir(restantes)
			self.secretos.guardar_varios({clave_secreto(id_sitio, "contrasena"): None, clave_secreto(id_sitio, "frase"): None})
		log.info("Sitio eliminado (%s) y sus secretos borrados", id_sitio)
		return True

	def marcar_aviso_sin_cifrar(self, id_sitio: str) -> None:
		"""Recuerda que ya se avisó de que este sitio manda la contraseña en claro."""
		with self._candado:
			sitios = self._leer()
			for sitio in sitios:
				if sitio.id == id_sitio:
					sitio.aviso_sin_cifrar_mostrado = True
			self._escribir(sitios)


# ── Rutas remotas y direcciones ──────────────────────────────────────────────


def normalizar_remota(ruta: str) -> str:
	"""Ruta absoluta con «/», sin «.», «..» de más ni barra final (salvo «/»)."""
	ruta = (ruta or "/").replace("\\", "/")
	if not ruta.startswith("/"):
		ruta = "/" + ruta
	ruta = posixpath.normpath(ruta)
	if ruta.startswith("//"):
		ruta = "/" + ruta.lstrip("/")
	return ruta


def padre_remoto(ruta: str) -> str | None:
	ruta = normalizar_remota(ruta)
	if ruta == "/":
		return None
	return posixpath.dirname(ruta) or "/"


def unir_remota(carpeta: str, nombre: str) -> str:
	nombre = nombre.replace("\\", "/")
	if nombre.startswith("/"):
		return normalizar_remota(nombre)
	return normalizar_remota(posixpath.join(normalizar_remota(carpeta), nombre))


def nombre_remoto(ruta: str) -> str:
	ruta = normalizar_remota(ruta)
	return posixpath.basename(ruta) or "/"


def componer_url(protocolo: str, servidor: str, puerto: int, usuario: str = "", ruta: str = "/") -> str:
	"""Dirección para mostrar y para el historial; sin contraseña, sin el puerto si es el habitual."""
	from urllib.parse import quote

	quien = quote(usuario, safe="") + "@" if usuario and usuario.lower() not in ("anonymous",) else ""
	maquina = f"[{servidor}]" if ":" in servidor else servidor
	extra = f":{puerto}" if int(puerto) != PUERTOS.get(protocolo, 0) else ""
	return f"{protocolo}://{quien}{maquina}{extra}{normalizar_remota(ruta)}"


@dataclass
class DatosUrl:
	protocolo: str
	servidor: str
	puerto: int
	usuario: str
	contrasena: str | None
	ruta: str


def analizar_url(texto: str) -> DatosUrl:
	"""``ftp://usuario:clave@servidor:puerto/carpeta`` → partes.

	:raises NoAdmitido: si el esquema no es ftp, ftps ni sftp.
	:raises NombreNoValido: si falta el servidor o el puerto no es un número.
	"""
	texto = (texto or "").strip()
	try:
		partes = urlsplit(texto)
		puerto_texto = partes.port
	except ValueError as error:
		raise base.NombreNoValido(_("La dirección no es válida: revise el puerto."), "") from error
	protocolo = partes.scheme.lower()
	if protocolo not in PROTOCOLOS:
		raise base.NoAdmitido(_("No se admiten direcciones {e}://").format(e=protocolo), "")
	if not partes.hostname:
		raise base.NombreNoValido(_("Falta el servidor en la dirección."), "")
	ruta = unquote(partes.path or "/")
	if any(c in ruta for c in "\r\n"):
		raise base.NombreNoValido(_("La dirección no es válida."), "")
	return DatosUrl(
		protocolo=protocolo,
		servidor=partes.hostname,
		puerto=int(puerto_texto or PUERTOS[protocolo]),
		usuario=unquote(partes.username or ""),
		contrasena=unquote(partes.password) if partes.password is not None else None,
		ruta=normalizar_remota(ruta),
	)


def huella_sha256(datos: bytes) -> str:
	"""«SHA256:…» en base64 sin relleno, como OpenSSH (igual para certificados TLS y claves SSH)."""
	return "SHA256:" + base64.b64encode(hashlib.sha256(datos).digest()).decode("ascii").rstrip("=")


# ── Huellas aceptadas ────────────────────────────────────────────────────────

#: Huellas aceptadas «solo esta vez» (y las guardadas), por «esquema:servidor:puerto».
#: Las conexiones aparte de las copias (``clonar``) no vuelven a preguntar.
_aceptadas_sesion: dict[str, str] = {}
_candado_huellas = threading.Lock()


def huella_aceptada_en_sesion(clave: str) -> str | None:
	with _candado_huellas:
		return _aceptadas_sesion.get(clave)


def aceptar_en_sesion(clave: str, huella: str) -> None:
	with _candado_huellas:
		_aceptadas_sesion[clave] = huella


def huella_tls_guardada(servidor: str) -> str | None:
	"""Huella guardada del certificado FTPS de «servidor:puerto» (``hosts_conocidos.json``)."""
	datos = almacen_json.leer(ARCHIVO_HUELLAS_TLS, {"version": VERSION, "huellas": {}})
	huellas = datos.get("huellas") if isinstance(datos.get("huellas"), dict) else {}
	valor = huellas.get(servidor.lower())
	return valor if isinstance(valor, str) else None


def guardar_huella_tls(servidor: str, huella: str) -> None:
	with _candado_huellas:
		datos = almacen_json.leer(ARCHIVO_HUELLAS_TLS, {"version": VERSION, "huellas": {}})
		if not isinstance(datos.get("huellas"), dict):
			datos["huellas"] = {}
		datos["huellas"][servidor.lower()] = huella
		datos["version"] = VERSION
		almacen_json.escribir(ARCHIVO_HUELLAS_TLS, datos)
	log.info("Huella TLS recordada para %s", servidor)


# ── Proveedores remotos ──────────────────────────────────────────────────────


class ProveedorRemoto(base.Proveedor):
	"""Base de ``ProveedorFTP`` y ``ProveedorSFTP``: rutas, credenciales y preguntas.

	La conexión se abre en el primer uso (``listar`` en el hilo de listado) o
	con ``conectar()``; nunca al crear el objeto (diseño 9.4).

	:param protocolo: «ftp», «ftps» o «sftp» (el ``esquema`` es «ftp» o «sftp»).
	:param contrasena: ``None`` si hay que buscarla (sitio guardado) o preguntarla.
	:param sitio_id: id del sitio guardado del que sale, si sale de uno.
	"""

	protocolo = "ftp"

	def __init__(self, servidor: str, puerto: int | None = None, usuario: str = "", contrasena: str | None = None,
			carpeta: str = "/", tiempo_espera: float = 30.0, sitio_id: str = "", nombre_sitio: str = "") -> None:
		super().__init__()
		self.host = servidor.strip()
		self.puerto = int(puerto or PUERTOS[self.protocolo])
		self.usuario = usuario
		self._contrasena = contrasena
		#: La contraseña la escribió la persona en esta sesión (se olvida al desconectar).
		self._contrasena_preguntada = False
		self.carpeta_inicial = normalizar_remota(carpeta or "/")
		self.tiempo_espera = float(tiempo_espera)
		self.sitio_id = sitio_id
		self.nombre_sitio = nombre_sitio
		#: Quién responde a las preguntas; ``None`` = el ``Decisor`` de la aplicación.
		self.decisor = None
		self.capacidades = base.Capacidades(escribir=True, papelera=False, atributos=False, enlaces=False, vigilar=False)

	# Identidad --------------------------------------------------------------

	@property
	def servidor(self) -> str:
		"""«servidor:puerto»: el carril de las operaciones (``clave_carril``)."""
		return f"{self.host.lower()}:{self.puerto}"

	@property
	def anonimo(self) -> bool:
		return self.protocolo != "sftp" and self.usuario.strip().lower() in USUARIOS_ANONIMOS

	def clave_reutilizar(self) -> tuple:
		return (self.protocolo, self.host.lower(), self.puerto, self.usuario)

	def url(self, ruta: str = "/") -> str:
		return componer_url(self.protocolo, self.host, self.puerto, self.usuario, ruta)

	# Rutas ------------------------------------------------------------------

	def padre(self, ruta: str) -> str | None:
		return padre_remoto(ruta)

	def unir(self, carpeta: str, nombre: str) -> str:
		return unir_remota(carpeta, nombre)

	def raiz(self, ruta: str) -> str:
		return "/"

	def nombre(self, ruta: str) -> str:
		return nombre_remoto(ruta)

	def mostrar(self, ruta: str) -> str:
		return self.url(ruta or "/")

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		# Mover dentro del mismo servidor sí puede ser un simple RNFR/RNTO o rename.
		return True

	@staticmethod
	def _comprobar_ruta(ruta: str) -> str:
		"""Ruta normalizada; los saltos de línea colarían órdenes en el protocolo."""
		if any(c in ruta for c in "\r\n\0"):
			raise base.NombreNoValido(_("El nombre no puede tener saltos de línea."), ruta)
		return normalizar_remota(ruta)

	# Preguntas ----------------------------------------------------------------

	def _decisor(self):
		if self.decisor is not None:
			return self.decisor
		from app.services.vfs import resolver

		return resolver.servicios().decisor

	def _config(self, clave: str, por_defecto):
		from app.services.vfs import resolver

		config = resolver.servicios().config
		if config is None:
			return por_defecto
		try:
			return config.obtener(clave)
		except Exception:  # noqa: BLE001 - una clave ausente no debe impedir conectar
			log.debug("Sin la clave %s en la configuración", clave, exc_info=True)
			return por_defecto

	def _quien(self) -> str:
		return f"{self.usuario}@{self.host}" if self.usuario else self.host

	def _repositorio(self) -> Conexiones:
		return Conexiones()

	def _sitio_guardado(self) -> Sitio | None:
		try:
			repo = self._repositorio()
			if self.sitio_id:
				return repo.obtener(self.sitio_id)
			return repo.buscar(self.protocolo, self.host, self.puerto, self.usuario)
		except Exception:  # noqa: BLE001 - sin sitios se pregunta, no se falla
			log.warning("No se pudieron leer los sitios guardados", exc_info=True)
			return None

	def obtener_contrasena(self) -> str:
		"""Contraseña para conectar: la conocida, la del sitio guardado o la que escriba la persona.

		Se llama desde el hilo de trabajo que conecta (puede bloquearlo con una pregunta).

		:raises ErrorAcceso: si la persona no la escribe.
		"""
		if self._contrasena is not None:
			return self._contrasena
		if self.anonimo:
			return ""
		sitio = self._sitio_guardado()
		if sitio is not None and sitio.guardar_contrasena:
			try:
				guardada = self._repositorio().contrasena(sitio.id)
			except Exception:  # noqa: BLE001 - un secreto ilegible se pregunta de nuevo
				log.warning("No se pudo leer la contraseña guardada del sitio %s", sitio.nombre, exc_info=True)
				guardada = None
			if guardada:
				self._contrasena = guardada
				return guardada
		decisor = self._decisor()
		if decisor is None:
			raise base.ErrorAcceso(_("Hace falta la contraseña de {q} y no se puede preguntar.").format(q=self._quien()), "")
		texto = decisor.pedir_texto(_("Contraseña de {q}").format(q=self._quien()), _("&Contraseña:"), "", oculto=True)
		if texto is None:
			raise base.ErrorAcceso(_("No se conectó: no se escribió la contraseña."), "")
		self._contrasena = texto
		self._contrasena_preguntada = True
		return texto

	def olvidar_contrasena_erronea(self) -> None:
		"""Tras «Usuario o contraseña incorrectos»: la próxima vez se busca o se pregunta otra vez."""
		self._contrasena = None
		self._contrasena_preguntada = False

	def confirmar_huella(self, que: str, huella: str, guardada: str | None, guardar) -> None:
		"""Pregunta si se acepta la huella de un servidor nuevo o que ha cambiado.

		:param que: «el certificado» o «la clave ed25519»... para el texto.
		:param guardar: función que recuerda la huella (``known_hosts`` o ``hosts_conocidos.json``).
		:raises ErrorAcceso: si no se acepta (o no hay a quién preguntar).
		"""
		clave = f"{self.protocolo}:{self.servidor}"
		if guardada == huella or huella_aceptada_en_sesion(clave) == huella:
			return
		decisor = self._decisor()
		if decisor is None:
			raise base.ErrorAcceso(_("No se pudo confirmar la huella de {s}; no se ha conectado.").format(s=self.servidor), "")
		if guardada is None:
			titulo = _("Servidor desconocido")
			texto = _(
				"Es la primera vez que se conecta a {s}.\n\nHuella de {que}:\n{h}\n\n"
				"Si puede, compruébela con quien administra el servidor antes de aceptarla."
			).format(s=self.servidor, que=que, h=huella)
			opciones = [_("Aceptar y &recordar"), _("Aceptar &solo esta vez"), _("&Cancelar")]
			predeterminada = 0
		else:
			titulo = _("Atención: la huella del servidor ha cambiado")
			texto = _(
				"¡ATENCIÓN! La huella de {que} de {s} NO coincide con la guardada.\n\n"
				"Puede que el servidor se haya reinstalado, pero también puede que alguien esté interceptando la "
				"conexión para robar su contraseña. Conéctese solo si sabe por qué ha cambiado.\n\n"
				"Huella guardada:\n{g}\n\nHuella actual:\n{h}"
			).format(s=self.servidor, que=que, g=guardada, h=huella)
			opciones = [_("Aceptar la nueva y &recordarla"), _("Aceptar &solo esta vez"), _("&Cancelar")]
			predeterminada = 2
		respuesta = decisor.elegir(titulo, texto, opciones, predeterminada, 2)
		if respuesta == 0:
			try:
				guardar(huella)
			except Exception:  # noqa: BLE001 - no recordar la huella no impide conectar esta vez
				log.warning("No se pudo guardar la huella de %s", self.servidor, exc_info=True)
			aceptar_en_sesion(clave, huella)
			log.info("Huella de %s aceptada y recordada", self.servidor)
			return
		if respuesta == 1:
			aceptar_en_sesion(clave, huella)
			log.info("Huella de %s aceptada solo en esta sesión", self.servidor)
			return
		log.info("Huella de %s rechazada", self.servidor)
		raise base.ErrorAcceso(_("No se conectó: no se aceptó la huella de {s}.").format(s=self.servidor), "")

	# Ciclo de vida -----------------------------------------------------------

	@abstractmethod
	def conectar(self) -> None:
		"""Abre la conexión ya (preguntando lo que haga falta). Desde un hilo de trabajo."""

	@abstractmethod
	def conectado(self) -> bool:
		"""``True`` si la conexión principal está abierta."""

	def cerrar(self) -> None:
		if self._contrasena_preguntada:
			# «Desconectar» olvida la contraseña escrita en esta sesión.
			self._contrasena = None
			self._contrasena_preguntada = False
		super().cerrar()


# ── Proveedores vivos ────────────────────────────────────────────────────────

_vivos: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
_candado_vivos = threading.Lock()


def registrar_vivo(proveedor: ProveedorRemoto) -> None:
	with _candado_vivos:
		_vivos[proveedor.clave_reutilizar()] = proveedor


def reutilizar(clave: tuple) -> ProveedorRemoto | None:
	"""Proveedor ya creado para ese servidor y usuario (lo usan las direcciones escritas y el historial)."""
	with _candado_vivos:
		return _vivos.get(clave)


def cerrar_todas() -> None:
	"""Cierra todas las conexiones vivas (al salir)."""
	with _candado_vivos:
		vivos = list(_vivos.values())
	for proveedor in vivos:
		try:
			proveedor.cerrar()
		except Exception:  # noqa: BLE001 - al salir, una conexión rota no debe impedir cerrar las demás
			log.debug("No se pudo cerrar una conexión al salir", exc_info=True)


atexit.register(cerrar_todas)


def crear_proveedor(sitio: Sitio, ruta: str | None = None) -> ProveedorRemoto:
	"""Proveedor SIN conectar para un sitio guardado (lo conecta su primer uso)."""
	if sitio.protocolo == "sftp":
		from app.services.vfs.sftp import ProveedorSFTP

		proveedor: ProveedorRemoto = ProveedorSFTP(
			sitio.servidor, sitio.puerto, sitio.usuario, None, carpeta=ruta or sitio.carpeta,
			tiempo_espera=sitio.tiempo_espera_s, sitio_id=sitio.id, nombre_sitio=sitio.nombre,
			clave_privada=sitio.clave_privada,
		)
	else:
		from app.services.vfs.ftp import ProveedorFTP

		proveedor = ProveedorFTP(
			sitio.servidor, sitio.puerto, sitio.usuario, None, tls=sitio.protocolo == "ftps", pasivo=sitio.pasivo,
			codificacion=sitio.codificacion, carpeta=ruta or sitio.carpeta, tiempo_espera=sitio.tiempo_espera_s,
			sitio_id=sitio.id, nombre_sitio=sitio.nombre,
		)
	registrar_vivo(proveedor)
	return proveedor


def proveedor_para_url(texto: str) -> tuple[ProveedorRemoto, str]:
	"""Fábrica común de ``ftp://``, ``ftps://`` y ``sftp://`` (la registran ``ftp.py`` y ``sftp.py``).

	No conecta. Si ya hay un proveedor vivo para ese servidor y usuario, lo
	reutiliza; si la dirección coincide con un sitio guardado, toma sus ajustes
	(modo pasivo, codificación, clave privada y contraseña guardada).
	"""
	datos = analizar_url(texto)
	clave = (datos.protocolo, datos.servidor.lower(), datos.puerto, datos.usuario)
	existente = reutilizar(clave)
	if existente is not None and (datos.contrasena is None or datos.contrasena == existente._contrasena):
		return existente, datos.ruta
	sitio = None
	try:
		sitio = Conexiones().buscar(datos.protocolo, datos.servidor, datos.puerto, datos.usuario)
	except Exception:  # noqa: BLE001 - sin sitios se conecta con los valores de fábrica
		log.warning("No se pudieron leer los sitios guardados", exc_info=True)
	if sitio is not None and sitio.protocolo == datos.protocolo:
		proveedor = crear_proveedor(sitio, datos.ruta)
		if datos.contrasena is not None:
			proveedor._contrasena = datos.contrasena
		return proveedor, datos.ruta
	if datos.protocolo == "sftp":
		from app.services.vfs.sftp import ProveedorSFTP

		proveedor = ProveedorSFTP(datos.servidor, datos.puerto, datos.usuario, datos.contrasena, carpeta=datos.ruta)
	else:
		from app.services.vfs.ftp import ProveedorFTP

		tiempo = 30
		pasivo = True
		try:
			from app.services.vfs import resolver

			config = resolver.servicios().config
			if config is not None:
				tiempo = int(config.obtener("ftp.tiempo_espera_s"))
				pasivo = bool(config.obtener("ftp.pasivo"))
		except Exception:  # noqa: BLE001 - valores de fábrica si la configuración no responde
			log.debug("Sin preferencias ftp.*", exc_info=True)
		proveedor = ProveedorFTP(datos.servidor, datos.puerto, datos.usuario, datos.contrasena, tls=datos.protocolo == "ftps",
			pasivo=pasivo, carpeta=datos.ruta, tiempo_espera=tiempo)
	registrar_vivo(proveedor)
	return proveedor, datos.ruta
