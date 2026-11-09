# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Raíz «Red» (``red://``) y recursos de un servidor (diseño 2.0, 9.1 a 9.3).

``ProveedorRed`` es de solo lectura y muestra en una sola lista, para llegar
antes con el lector:

1. «Unidad de red»: las letras con su remoto y su estado («Conectada»,
   «Desconectada: Intro para volver a conectar», «No disponible»).
2. «Conexión sin letra»: los ``\\\\servidor\\recurso`` abiertos sin letra.
3. «Servidor favorito» y «Servidor reciente» (``data/config/red.json``).
4. «Equipo encontrado»: lo que va encontrando la búsqueda de equipos (9.2),
   que llega poco a poco; mientras dura, la fila «Buscando equipos...».
5. «Otro proveedor»: WSL, escritorio remoto, WebDAV, SSHFS y NFS si están
   instalados (``red.mostrar_otros_proveedores``).

Rutas dentro del proveedor: ``""`` es la raíz; ``\\\\servidor`` es la lista de
recursos de ese servidor (9.3: recursos con «$» solo con
``paneles.mostrar_ocultos``, impresoras al final, credenciales con el
``Decisor`` y el error 1219); las demás (``Z:\\``, ``\\\\srv\\rec`` y lo que
cuelga de ellas) son carpetas reales. Intro en una fila de la raíz o de un
servidor ejecuta la orden ``red_raiz`` con la ruta de la fila
(``orden_al_abrir``), que lleva el panel a esa carpeta con el proveedor
local, tras volver a conectar la unidad si hace falta (lo pide
docs/revision/peticiones-rd.md). Mientras el panel no consulte
``orden_al_abrir``, las carpetas reales se leen a través de este proveedor,
también de solo lectura.

La búsqueda de equipos es única para todo el programa (``iniciar_descubrimiento``):
cualquier panel en ``red://`` ve los mismos equipos. Sin wx.
"""

from __future__ import annotations

import builtins
import logging
import socket
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import BinaryIO

from app.services.vfs import base, rutas
from app.services.vfs.local import ProveedorLocal

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ESQUEMA = "red"
DIRECCION = "red://"
RUTA_BUSCANDO = "red://buscando"
#: Orden que ejecuta Intro en una fila de la raíz o de un servidor (``orden_al_abrir``).
ORDEN_ABRIR = "red_raiz"
#: Una búsqueda terminada hace menos de esto no se repite al volver a entrar (sí con Ctrl+R).
EDAD_MAXIMA_BUSQUEDA_S = 600.0
#: Intentos de credenciales por visita a un servidor (nunca bucles de contraseña).
MAX_INTENTOS_CREDENCIALES = 3

# Clases de fila (orden de los grupos de 9.1).
UNIDAD, CONEXION, FAVORITO, RECIENTE, EQUIPO, OTRO, BUSCANDO, RECURSO, IMPRESORA = (
	"unidad", "conexion", "favorito", "reciente", "equipo", "otro", "buscando", "recurso", "impresora")
_GRUPO = {UNIDAD: 1, CONEXION: 2, FAVORITO: 3, RECIENTE: 3, EQUIPO: 4, OTRO: 5, BUSCANDO: 6, RECURSO: 1, IMPRESORA: 2}


def _tipos() -> dict[str, str]:
	return {
		UNIDAD: _("Unidad de red"), CONEXION: _("Conexión sin letra"), FAVORITO: _("Servidor favorito"),
		RECIENTE: _("Servidor reciente"), EQUIPO: _("Equipo encontrado"), OTRO: _("Otro proveedor"),
		BUSCANDO: _("Búsqueda en curso"), RECURSO: _("Recurso compartido"), IMPRESORA: _("Impresora"),
	}


@dataclass(frozen=True)
class FilaRed:
	"""Una fila de la raíz «Red» o de un servidor, con sus columnas (Nombre, Tipo, Remoto, Estado)."""

	ruta: str
	nombre: str
	clase: str
	remoto: str = ""
	estado: str = ""
	ayuda: str = ""

	@property
	def tipo(self) -> str:
		return _tipos()[self.clase]

	@property
	def grupo(self) -> int:
		return _GRUPO[self.clase]

	@property
	def es_carpeta(self) -> bool:
		return self.clase not in (BUSCANDO, IMPRESORA) and not self.ruta.startswith(DIRECCION)

	def texto(self) -> str:
		"""«Z:, Unidad de red, \\\\DS220\\home, Conectada»: todo lo que el lector debe oír en una fila.

		Los recursos de un servidor se dicen solo con su nombre, como en el Explorador; las
		impresoras dicen además que lo son (en ellas no se puede entrar).
		"""
		if self.clase == RECURSO:
			return self.nombre
		if self.clase == IMPRESORA:
			return f"{self.nombre}, {self.tipo}"
		return ", ".join(p for p in (self.nombre, self.tipo, self.remoto, self.estado) if p)


# ── Configuración (la fija la ventana con resolver.fijar_servicios) ───────────


def _config(clave: str, defecto):
	from app.services.vfs import resolver

	config = resolver.servicios().config
	if config is None:
		return defecto
	try:
		return config.obtener(clave)
	except (KeyError, AttributeError):
		return defecto


def _decisor():
	from app.services.vfs import resolver

	return resolver.servicios().decisor


# ── Búsqueda de equipos compartida ───────────────────────────────────────────

EQUIPO_NUEVO, BUSQUEDA_EMPIEZA, BUSQUEDA_TERMINA = "equipo", "empieza", "termina"


class _EstadoBusqueda:
	def __init__(self) -> None:
		self.candado = threading.RLock()
		self.equipos: dict[str, object] = {}
		self.actual = None
		self.vistos_ahora: set[str] = set()
		self.fin = 0.0
		self.oyentes: list[Callable[[str, object], None]] = []


_busqueda = _EstadoBusqueda()


def suscribir(oyente: Callable[[str, object], None]) -> Callable[[], None]:
	"""``oyente(evento, dato)`` con ``EQUIPO_NUEVO`` (el equipo), ``BUSQUEDA_EMPIEZA`` o ``BUSQUEDA_TERMINA``
	(la lista de equipos). Se llama en un hilo de trabajo. Devuelve la función que anula la suscripción."""
	with _busqueda.candado:
		_busqueda.oyentes.append(oyente)

	def quitar() -> None:
		with _busqueda.candado:
			if oyente in _busqueda.oyentes:
				_busqueda.oyentes.remove(oyente)

	return quitar


def _avisar(evento: str, dato: object) -> None:
	with _busqueda.candado:
		oyentes = list(_busqueda.oyentes)
	for oyente in oyentes:
		try:
			oyente(evento, dato)
		except Exception:  # noqa: BLE001 - un oyente roto no detiene la búsqueda
			log.exception("Falló un aviso de la búsqueda de equipos")


def equipos() -> list:
	"""Equipos encontrados hasta ahora (``EquipoRed``), por nombre."""
	with _busqueda.candado:
		return sorted(_busqueda.equipos.values(), key=lambda e: e.nombre.casefold())


def busqueda_actual():
	"""La búsqueda en marcha (``Descubrimiento``), o ``None``."""
	with _busqueda.candado:
		actual = _busqueda.actual
		return actual if actual is not None and not actual.terminada else None


def buscando() -> bool:
	return busqueda_actual() is not None


def conviene_buscar(edad_maxima_s: float = EDAD_MAXIMA_BUSQUEDA_S) -> bool:
	"""No hay búsqueda en marcha y la última terminó hace más de ``edad_maxima_s`` (o no hubo ninguna)."""
	with _busqueda.candado:
		return busqueda_actual() is None and (not _busqueda.fin or time.monotonic() - _busqueda.fin > edad_maxima_s)


def iniciar_descubrimiento(tiempo_maximo_s: float | None = None, mdns: bool | None = None, dominio: bool | None = None,
		fuentes: Sequence | None = None, relanzar: bool = False):
	"""Empieza la búsqueda de equipos (o devuelve la que está en marcha). ``relanzar`` cancela la actual y empieza otra.

	Los equipos que una búsqueda completa ya no encuentra se quitan al terminarla.
	"""
	from app.services.windows import red_descubrir

	with _busqueda.candado:
		actual = busqueda_actual()
		if actual is not None and not relanzar:
			return actual
		if actual is not None:
			actual.cancelar("se vuelve a buscar")
		tiempo = float(tiempo_maximo_s if tiempo_maximo_s is not None else _config("red.tiempo_descubrir_s", 45))
		usar_mdns = bool(_config("red.descubrir_mdns", True) if mdns is None else mdns)
		usar_dominio = bool(_config("red.descubrir_dominio", True) if dominio is None else dominio)
		vistos: set[str] = set()

		def al_encontrar(equipo) -> None:
			with _busqueda.candado:
				if _busqueda.actual is not nuevo:
					return
				vistos.add(equipo.nombre.upper())
				ya_estaba = equipo.nombre.upper() in _busqueda.equipos
				_busqueda.equipos[equipo.nombre.upper()] = equipo
			if not ya_estaba:
				_avisar(EQUIPO_NUEVO, equipo)

		def al_terminar(_lista, cancelada: bool) -> None:
			with _busqueda.candado:
				if _busqueda.actual is not nuevo:
					return
				if not cancelada:
					for clave in [c for c in _busqueda.equipos if c not in vistos]:
						del _busqueda.equipos[clave]
				_busqueda.fin = time.monotonic()
				lista = sorted(_busqueda.equipos.values(), key=lambda e: e.nombre.casefold())
			_avisar(BUSQUEDA_TERMINA, (lista, cancelada))

		nuevo = red_descubrir.Descubrimiento(al_encontrar, al_terminar, tiempo, fuentes, usar_mdns, usar_dominio)
		_busqueda.actual = nuevo
	_avisar(BUSQUEDA_EMPIEZA, nuevo)
	return nuevo.iniciar()


def cancelar_descubrimiento(motivo: str = "") -> bool:
	actual = busqueda_actual()
	if actual is None:
		return False
	actual.cancelar(motivo)
	return True


def olvidar_equipos() -> None:
	"""Para las pruebas: sin equipos ni búsqueda."""
	with _busqueda.candado:
		if _busqueda.actual is not None and not _busqueda.actual.terminada:
			_busqueda.actual.cancelar("reinicio")
		_busqueda.actual = None
		_busqueda.equipos.clear()
		_busqueda.fin = 0.0


# ── Proveedor ────────────────────────────────────────────────────────────────


def es_raiz(ruta: str) -> bool:
	return not (ruta or "").strip() or (ruta or "").strip().lower() == DIRECCION


def es_virtual(ruta: str) -> bool:
	"""Fila que no es una carpeta real: «Buscando equipos...» o un proveedor que se conecta con el diálogo."""
	return (ruta or "").lower().startswith(DIRECCION)


def es_destino_local(ruta: str) -> bool:
	"""Carpeta real (letra o recurso UNC), a la que Intro lleva con el proveedor local."""
	from app.services.windows import red

	ruta = (ruta or "").strip()
	return bool(ruta) and not es_virtual(ruta) and not red.es_servidor(ruta)


class ProveedorRed(base.Proveedor):
	"""``red://``: unidades, conexiones, servidores y equipos; y los recursos de cada ``\\\\servidor``."""

	esquema = ESQUEMA

	def __init__(self) -> None:
		super().__init__()
		self.capacidades = base.Capacidades(escribir=False, papelera=False, atributos=False, enlaces=False, vigilar=False)
		self._local = ProveedorLocal()
		self._candado = threading.Lock()
		self._filas: dict[str, FilaRed] = {}
		#: Verdadero en cuanto el panel pide las columnas propias: desde entonces el nombre es solo el nombre.
		self.columnas_en_panel = False
		self._otros: tuple[float, list] = (0.0, [])

	def descripcion(self) -> str:
		return _("Red")

	# Filas -------------------------------------------------------------------

	def fila(self, ruta: str) -> FilaRed | None:
		with self._candado:
			return self._filas.get((ruta or "").upper())

	def _entrada(self, fila: FilaRed) -> base.Entrada:
		nombre = fila.nombre if self.columnas_en_panel else fila.texto()
		return base.Entrada(nombre=nombre, ruta=fila.ruta, es_carpeta=fila.es_carpeta)

	def _recordar(self, filas: list[FilaRed]) -> list[base.Entrada]:
		with self._candado:
			for fila in filas:
				self._filas[fila.ruta.upper()] = fila
		return [self._entrada(f) for f in filas]

	def _otros_proveedores(self) -> list:
		from app.services.windows import red

		momento, lista = self._otros
		if time.monotonic() - momento > 60 or not momento:
			try:
				lista = red.otros_proveedores()
			except Exception:  # noqa: BLE001 - sin los opcionales la raíz sigue
				log.debug("No se pudieron detectar los otros proveedores de red", exc_info=True)
				lista = []
			self._otros = (time.monotonic(), lista)
		return lista

	def filas_raiz(self) -> list[FilaRed]:
		"""Las filas de la raíz, en el orden de los grupos de 9.1 (sin E/S lenta: menos de 1 s)."""
		from app.services import red_recientes
		from app.services.windows import red

		filas: list[FilaRed] = []
		vistas: set[str] = set()

		def anadir(fila: FilaRed) -> None:
			clave = fila.ruta.rstrip("\\").upper() or fila.ruta.upper()
			if clave not in vistas:
				vistas.add(clave)
				filas.append(fila)

		try:
			with red.sin_cuadros_de_error():
				conexiones = red.unidades_red()
		except red.ErrorUnidadRed:
			log.info("No se pudieron leer las unidades de red", exc_info=True)
			conexiones = []
		for unidad in conexiones:
			if unidad.letra:
				anadir(FilaRed(unidad.letra + "\\", unidad.letra, UNIDAD, unidad.remoto, unidad.texto_estado()))
		for unidad in conexiones:
			if not unidad.letra:
				anadir(FilaRed(unidad.remoto, unidad.remoto, CONEXION, "", unidad.texto_estado()))
		for favorito in red_recientes.favoritos():
			nombre = favorito.nombre or favorito.ruta
			anadir(FilaRed(favorito.ruta, nombre, FAVORITO, favorito.ruta if nombre != favorito.ruta.lstrip("\\") else ""))
		for reciente in red_recientes.recientes():
			anadir(FilaRed(reciente, reciente.lstrip("\\"), RECIENTE))
		for equipo in equipos():
			anadir(FilaRed(equipo.ruta_unc, equipo.nombre, EQUIPO, equipo.direccion))
		if bool(_config("red.mostrar_otros_proveedores", True)):
			for otro in self._otros_proveedores():
				ruta = otro.ruta if otro.ruta.startswith("\\\\") and len(otro.ruta) > 2 and red.es_servidor(otro.ruta) else f"{DIRECCION}{otro.clave}"
				anadir(FilaRed(ruta, otro.nombre, OTRO, ayuda=otro.ayuda))
		actual = busqueda_actual()
		if actual is not None:
			# Sin el recuento en la fila: el nombre no cambia y el cursor no se pierde al refrescar.
			anadir(FilaRed(RUTA_BUSCANDO, _("Buscando equipos..."), BUSCANDO))
		return filas

	def filas_servidor(self, servidor: str, cancelacion=None) -> list[FilaRed]:
		"""Recursos de ``\\\\servidor`` (9.3), con credenciales y 1219 resueltos con el ``Decisor``."""
		from app.services import red_recientes
		from app.services.windows import red

		servidor = servidor.strip().strip("\\")
		ocultos = bool(_config("paneles.mostrar_ocultos", False))
		intentos = 0
		while True:
			base.comprobar(cancelacion)
			try:
				lista = red.recursos(servidor, ocultos)
				break
			except red.ErrorUnidadRed as error:
				if not (error.pide_credenciales or error.codigo == red.ERROR_SMB_GUEST_LOGON_BLOCKED):
					raise
				intentos += 1
				if intentos > MAX_INTENTOS_CREDENCIALES:
					raise
				servidor = self._iniciar_sesion(servidor, error, cancelacion)
		red_recientes.anotar_reciente(servidor)
		return [
			FilaRed(r.ruta, r.nombre, IMPRESORA if r.tipo == "impresora" else RECURSO, r.comentario)
			for r in lista
		]

	# Credenciales y 1219 (en el hilo de listado) -----------------------------

	def _iniciar_sesion(self, servidor: str, error, cancelacion=None) -> str:
		"""Pide usuario y contraseña con el ``Decisor`` y se autentica en ``\\\\servidor\\IPC$``. Devuelve el servidor usado.

		:raises ErrorUnidadRed: el error original si no hay a quién preguntar.
		:raises Cancelado: si la persona cancela.
		"""
		decisor = _decisor()
		if decisor is None or not hasattr(decisor, "pedir_credenciales"):
			raise error
		texto = _("{m}\n\nEscriba un usuario y una contraseña de {s}. Vacío el usuario, se usa la cuenta de Windows.").format(
			m=error.mensaje, s=servidor)
		respuesta = decisor.pedir_credenciales(_("Credenciales de {s}").format(s=servidor), texto, "")
		if respuesta is None:
			raise base.Cancelado(_("No se abrió {s}: se canceló el inicio de sesión").format(s=f"\\\\{servidor}"), f"\\\\{servidor}")
		usuario, contrasena, recordar = respuesta
		base.comprobar(cancelacion)
		return autenticar_con_1219(servidor, usuario, contrasena, recordar, decisor)

	def preparar(self, ruta: str, cancelacion=None, reconectar_siempre: bool = False) -> bool:
		"""Deja lista una carpeta real antes de entrar. Bloquea. Verdadero si tuvo que conectar algo.

		Reconecta una letra recordada y desconectada (1201: con ``red.reconectar_al_entrar`` o
		``reconectar_siempre``, que es Intro en su fila) y, si el servidor pide credenciales, las
		pide con el ``Decisor`` y vuelve a intentarlo.
		"""
		from app.services.windows import red

		ruta = (ruta or "").strip()
		if len(ruta) >= 2 and ruta[1] == ":":
			try:
				unidad = red.unidad(ruta[:2])
			except red.ErrorUnidadRed:
				unidad = None
			if unidad is not None and unidad.estado_efectivo != red.CONECTADA:
				self.reconectar(unidad, cancelacion, siempre=reconectar_siempre)
				return True
			return False
		if ruta.startswith("\\\\") and not red.es_servidor(ruta):
			servidor = red.servidor_de(ruta)
			try:
				with red.sin_cuadros_de_error():
					self._local.info(_raiz_unc(ruta))
			except base.Cancelado:
				raise
			except base.ErrorArchivos as error:
				codigo = _codigo_os(error)
				if codigo in red.CODIGOS_CREDENCIALES or codigo == red.ERROR_SMB_GUEST_LOGON_BLOCKED:
					self._iniciar_sesion(servidor, red.error_de_codigo(codigo, ruta), cancelacion)
					return True
				raise
		return False

	def reconectar(self, unidad, cancelacion=None, siempre: bool = True) -> None:
		"""Vuelve a conectar una unidad (o conexión sin letra) que no está conectada, pidiendo credenciales si hace falta."""
		from app.services.windows import red

		if not siempre and not bool(_config("red.reconectar_al_entrar", True)):
			raise red.ErrorUnidadRed(unidad.mensaje_no_disponible(), red.ERROR_CONNECTION_UNAVAIL, unidad.letra)
		try:
			if unidad.letra:
				red.reconectar(unidad.letra)
			else:
				red.conectar("", unidad.remoto, persistente=False)
			return
		except red.ErrorUnidadRed as error:
			if not error.pide_credenciales and error.codigo != red.ERROR_SMB_GUEST_LOGON_BLOCKED:
				raise
			fallo = error
		decisor = _decisor()
		if decisor is None or not hasattr(decisor, "pedir_credenciales"):
			raise fallo
		texto = _("{m}\n\nEscriba un usuario y una contraseña de {s} para volver a conectar {l}.").format(
			m=fallo.mensaje, s=red.servidor_de(unidad.remoto), l=unidad.nombre)
		respuesta = decisor.pedir_credenciales(_("Volver a conectar {l}").format(l=unidad.nombre), texto, unidad.usuario)
		if respuesta is None:
			raise base.Cancelado(_("No se volvió a conectar {l}").format(l=unidad.nombre), unidad.nombre)
		base.comprobar(cancelacion)
		usuario, contrasena, recordar = respuesta
		red.conectar(unidad.letra, unidad.remoto, usuario, contrasena, recordar, persistente=False)

	# Navegación --------------------------------------------------------------

	def listar(self, ruta: str, cancelacion=None) -> list[base.Entrada]:
		from app.services.windows import red

		ruta = (ruta or "").strip()
		if es_raiz(ruta):
			return self._recordar(self.filas_raiz())
		if es_virtual(ruta):
			raise base.NoAdmitido(self._motivo_virtual(ruta), ruta)
		if red.es_servidor(ruta):
			return self._recordar(self.filas_servidor(ruta, cancelacion))
		self.preparar(ruta, cancelacion)
		with red.sin_cuadros_de_error():
			return self._local.listar(ruta, cancelacion)

	def _motivo_virtual(self, ruta: str) -> str:
		if ruta.lower() == RUTA_BUSCANDO:
			return _("La búsqueda de equipos sigue en marcha; los equipos aparecen en la lista según se encuentran.")
		fila = self.fila(ruta)
		ayuda = fila.ayuda if fila is not None else ""
		return " ".join(p for p in (ayuda, _("Use Conectar unidad de red, en Comandos, Red.")) if p)

	def info(self, ruta: str) -> base.Entrada:
		from app.services.windows import red

		ruta = (ruta or "").strip()
		if es_raiz(ruta):
			return base.Entrada(_("Red"), "", es_carpeta=True)
		fila = self.fila(ruta)
		if fila is not None:
			return self._entrada(fila)
		if es_virtual(ruta):
			raise base.NoEncontrado(_("No existe {r}").format(r=ruta), ruta)
		if red.es_servidor(ruta):
			return base.Entrada(ruta.strip("\\"), ruta.rstrip("\\"), es_carpeta=True)
		return self._local.info(ruta)

	def existe(self, ruta: str) -> bool:
		try:
			self.info(ruta)
		except base.ErrorArchivos:
			return False
		return True

	def padre(self, ruta: str) -> str | None:
		from app.services.windows import red

		ruta = (ruta or "").strip()
		if es_raiz(ruta):
			return None
		if es_virtual(ruta) or red.es_servidor(ruta):
			return ""
		superior = rutas.padre(ruta)
		return "" if superior is None else superior

	def unir(self, carpeta: str, nombre: str) -> str:
		if es_raiz(carpeta):
			return nombre
		return rutas.unir(carpeta, nombre)

	def raiz(self, ruta: str) -> str:
		from app.services.windows import red

		if es_raiz(ruta) or es_virtual(ruta) or red.es_servidor(ruta):
			return ""
		return rutas.raiz(rutas.normalizar(ruta))

	def nombre(self, ruta: str) -> str:
		fila = self.fila(ruta)
		if fila is not None:
			return self._entrada(fila).nombre
		if es_raiz(ruta):
			return _("Red")
		return (ruta or "").rstrip("\\").rsplit("\\", 1)[-1] or ruta

	def mostrar(self, ruta: str) -> str:
		from app.services.windows import red

		if es_raiz(ruta):
			return DIRECCION
		if es_virtual(ruta) or red.es_servidor(ruta):
			return (ruta or "").rstrip("\\")
		return rutas.normalizar(ruta)

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		return False

	# Columnas propias para el panel (petición RD: Nombre, Tipo, Remoto, Estado) --

	def columnas_propias(self, ruta: str) -> list[tuple[str, str]] | None:
		"""Columnas de la raíz y de un servidor (9.1). Pedirlas deja el nombre limpio en las filas siguientes."""
		from app.services.windows import red

		if not (es_raiz(ruta) or red.es_servidor(ruta)):
			return None
		self.columnas_en_panel = True
		return [("nombre", _("Nombre")), ("red_tipo", _("Tipo")), ("red_remoto", _("Remoto")), ("red_estado", _("Estado"))]

	def valor_columna(self, entrada: base.Entrada, columna: str) -> str:
		fila = self.fila(entrada.ruta)
		if fila is None:
			return ""
		return {"nombre": fila.nombre, "red_tipo": fila.tipo, "red_remoto": fila.remoto, "red_estado": fila.estado}.get(columna, "")

	def conservar_orden(self, ruta: str) -> bool:
		"""La raíz va ordenada por grupo y nombre (9.1), no por el criterio del panel."""
		return es_raiz(ruta)

	def orden_al_abrir(self, entrada: base.Entrada) -> str | None:
		"""Orden que ejecuta Intro en ``entrada`` (con su ruta como argumento), o ``None`` para entrar sin más."""
		if entrada.es_superior:
			return None
		return ORDEN_ABRIR if self.fila(entrada.ruta) is not None else None

	# Contenido ---------------------------------------------------------------

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		fila = self.fila(ruta)
		if fila is not None and fila.clase == IMPRESORA:
			raise base.NoAdmitido(_("No se puede entrar en una impresora."), ruta)
		if es_virtual(ruta) or fila is not None or es_raiz(ruta):
			raise base.NoAdmitido(self._motivo_virtual(ruta) if es_virtual(ruta) else _("Aquí no hay un archivo que abrir."), ruta)
		return self._local.abrir_lectura(ruta)

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		raise base.SoloLectura(_("En Red no se elimina nada. Para quitar una unidad o conexión, use Desconectar unidad de red."), ruta)

	def espacio_libre(self, ruta: str) -> tuple[int, int] | None:
		if not es_destino_local(ruta):
			return None
		return self._local.espacio_libre(ruta)

	def ruta_local(self, ruta: str) -> str | None:
		if not es_destino_local(ruta):
			return None
		return rutas.normalizar(ruta)


def formato_encontrados(cuantos: int) -> str:
	return _("1 equipo encontrado") if cuantos == 1 else _("{n} equipos encontrados").format(n=cuantos)


def _raiz_unc(ruta: str) -> str:
	partes = [p for p in ruta.strip().lstrip("\\").split("\\") if p]
	return f"\\\\{partes[0]}\\{partes[1]}" if len(partes) >= 2 else ruta


def _codigo_os(error: BaseException) -> int:
	from app.services.windows import red

	for candidato in (error, getattr(error, "__cause__", None), getattr(error, "__context__", None)):
		if candidato is not None:
			codigo = getattr(candidato, "winerror", None) or getattr(candidato, "codigo", None)
			if isinstance(codigo, int) and codigo:
				return codigo
	return red.codigo_de(error)


def autenticar_con_1219(servidor: str, usuario: str, contrasena: str, recordar: bool, decisor) -> str:
	"""Inicia sesión en el servidor; con el error 1219 ofrece cerrar sus conexiones o usar su IP (9.3).

	Devuelve el nombre del servidor que quedó autenticado (el mismo, o su IP).

	:raises Cancelado: si la persona elige cancelar.
	"""
	from app.services.windows import red

	try:
		red.autenticar(servidor, usuario, contrasena, recordar)
		return servidor
	except red.ErrorUnidadRed as error:
		if error.codigo != red.ERROR_SESSION_CREDENTIAL_CONFLICT or decisor is None:
			raise
		conflicto = error
	opciones = [_("Cerrar las &conexiones a este servidor y reintentar"), _("Usar otro &nombre del servidor (su IP)"), _("&Cancelar")]
	eleccion = decisor.elegir(_("Ya hay una sesión con {s}").format(s=servidor), conflicto.mensaje, opciones, 0, 2)
	if eleccion == 0:
		cerradas = red.cerrar_conexiones_servidor(servidor)
		log.info("Cerradas %d conexiones a %s por el error 1219", cerradas, servidor)
		red.autenticar(servidor, usuario, contrasena, recordar)
		return servidor
	if eleccion == 1:
		try:
			direccion = socket.gethostbyname(servidor)
		except OSError as error:
			raise red.ErrorUnidadRed(_("No se encontró la dirección IP de {s}.").format(s=servidor), 53, servidor) from error
		red.autenticar(direccion, usuario, contrasena, recordar)
		return direccion
	raise base.Cancelado(_("Inicio de sesión cancelado"), f"\\\\{servidor}")


_proveedor: ProveedorRed | None = None
_candado_proveedor = threading.Lock()


def proveedor_red() -> ProveedorRed:
	"""El proveedor de ``red://`` (uno para todo el programa: comparte las filas y la búsqueda de equipos)."""
	global _proveedor
	with _candado_proveedor:
		if _proveedor is None:
			_proveedor = ProveedorRed()
		return _proveedor


def ruta_de_direccion(texto: str) -> str:
	"""Ruta dentro del proveedor de «red://», «red://DS220», «red://\\\\DS220\\home» o «red://DS220/home»."""
	resto = (texto or "").strip()
	if resto.lower().startswith(DIRECCION):
		resto = resto[len(DIRECCION):]
	resto = resto.replace("/", "\\").strip()
	if not resto.strip("\\"):
		return ""
	return resto if resto.startswith("\\\\") else "\\\\" + resto.lstrip("\\")


def _fabrica(direccion: str) -> tuple[ProveedorRed, str]:
	return proveedor_red(), ruta_de_direccion(direccion)


def unidad_virtual() -> base.UnidadVirtual:
	"""La entrada «Red» del selector de unidades (Alt+F1 y Alt+F2)."""
	return base.UnidadVirtual(_("Red"), DIRECCION, _("Unidades de red, conexiones, servidores y equipos"))


def _registrar() -> None:
	from app.services.vfs import resolver

	resolver.registrar_esquema(ESQUEMA, _fabrica)


_registrar()
