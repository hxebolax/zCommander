# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Convierte texto escrito por la persona en (proveedor, ruta).

Los bloques registran sus proveedores al importarse su módulo de registro
(``app/services/vfs/registro_proveedores.py`` importa todos los conocidos):

- ``registrar_comprimido(extensiones, fabrica)``: ``fabrica(contenedor, ruta_archivo) -> Proveedor``
  donde ``contenedor`` es el proveedor que tiene el archivo comprimido.
- ``registrar_esquema(prefijo, fabrica)``: ``fabrica(url) -> (Proveedor, ruta)``
  para direcciones como ``ftp://`` o ``sftp://``.

Así el núcleo (que llama a ``abrir_ruta``) no depende de los bloques C y D.

Las fábricas no hacen E/S: devuelven un proveedor sin conectar; la conexión
ocurre en su primer ``listar()``, en el hilo de listado. Si necesitan preguntar
algo (contraseña, huella de un servidor, contraseña de un 7z) usan
``servicios()``: el ``Decisor`` de la interfaz (sus métodos bloquean el hilo
que llama, nunca el de la interfaz) y el ``AlmacenSecretos``. ``main.py`` los
fija al arrancar con ``fijar_servicios``.

Los proveedores remotos exponen ``servidor`` («servidor:puerto»), que usa
``clave_carril`` para que cada servidor sea un carril distinto.
"""

from __future__ import annotations

import builtins
import logging
import os
import re
from collections.abc import Callable

from app.services.vfs import base, rutas
from app.services.vfs.local import ProveedorLocal

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


FabricaComprimido = Callable[[base.Proveedor, str], base.Proveedor]
FabricaEsquema = Callable[[str], tuple[base.Proveedor, str]]

class Servicios:
	"""Lo que un proveedor puede necesitar de la aplicación (lo fija ``main.py``)."""

	def __init__(self, decisor=None, secretos=None, config=None) -> None:
		self.decisor = decisor
		self.secretos = secretos
		self.config = config


_servicios = Servicios()


def fijar_servicios(decisor=None, secretos=None, config=None) -> None:
	global _servicios
	_servicios = Servicios(decisor, secretos, config)


def servicios() -> Servicios:
	return _servicios


#: «\\\\servidor» o «\\\\servidor\\», sin recurso.
_SERVIDOR_SOLO = re.compile(r"\\\\[^\\/]+\\?")

_comprimidos: dict[str, FabricaComprimido] = {}
_esquemas: dict[str, FabricaEsquema] = {}
_local = ProveedorLocal()


def proveedor_local() -> ProveedorLocal:
	"""Proveedor local compartido (no tiene estado)."""
	return _local


def registrar_comprimido(extensiones: tuple[str, ...], fabrica: FabricaComprimido) -> None:
	"""Registra un tipo de comprimido por sus extensiones (``("zip",)``, ``("tar.gz", "tgz")``)."""
	for extension in extensiones:
		_comprimidos[extension.lower().lstrip(".")] = fabrica


def registrar_esquema(prefijo: str, fabrica: FabricaEsquema) -> None:
	"""Registra un esquema de dirección (``"ftp"``, ``"ftps"``, ``"sftp"``)."""
	_esquemas[prefijo.lower()] = fabrica


#: ``activador(prefijo) -> bool`` que activa el complemento de un esquema aún sin registrar
#: (lo fija ``app.plugins.cargador`` con el cargador de la sesión; este módulo no conoce los complementos).
_activador_esquemas: list[Callable[[str], bool] | None] = [None]


def fijar_activador_esquemas(activador: Callable[[str], bool] | None) -> None:
	_activador_esquemas[0] = activador


# ── Unidades virtuales del selector de unidades (diseño 2.0, 14.5) ─────────────

_fuentes_unidades: list = []


def registrar_unidades(funcion) -> None:
	"""Añade una fuente de entradas para el selector de unidades (nubes, NAS, Red, Papelera).

	``funcion() -> list[UnidadVirtual]`` se llama en un hilo: puede tardar (pregunta
	el espacio libre a un servidor).
	"""
	if funcion not in _fuentes_unidades:
		_fuentes_unidades.append(funcion)


def quitar_unidades(funcion) -> None:
	if funcion in _fuentes_unidades:
		_fuentes_unidades.remove(funcion)


def unidades_fijas() -> list[base.UnidadVirtual]:
	"""Las entradas fijas de los manifiestos (``[[unidades]]``): se muestran sin activar ningún complemento."""
	from app.plugins import registro

	return registro.unidades_fijas()


def unidades_virtuales(cancelacion=None) -> list[base.UnidadVirtual]:
	"""Fijas de los manifiestos más las dinámicas de cada fuente (en un hilo; una fuente que falla se omite)."""
	resultado = list(unidades_fijas())
	vistas = {u.direccion for u in resultado}
	for funcion in list(_fuentes_unidades):
		base.comprobar(cancelacion)
		try:
			nuevas = list(funcion() or [])
		except Exception:  # noqa: BLE001 - una fuente rota no deja sin las demás
			import logging

			logging.getLogger(__name__).warning("Falló una fuente de unidades virtuales", exc_info=True)
			continue
		for unidad in nuevas:
			if unidad.direccion in vistas:
				resultado = [unidad if u.direccion == unidad.direccion else u for u in resultado]
			else:
				resultado.append(unidad)
				vistas.add(unidad.direccion)
	return resultado


def extension_comprimido(nombre: str) -> str | None:
	"""Extensión registrada más larga con la que termina ``nombre`` (``tar.gz`` antes que ``gz``)."""
	nombre = nombre.lower()
	candidatas = [e for e in _comprimidos if nombre.endswith("." + e)]
	return max(candidatas, key=len) if candidatas else None


def es_comprimido(nombre: str) -> bool:
	return extension_comprimido(nombre) is not None


def abrir_comprimido(contenedor: base.Proveedor, ruta_archivo: str) -> base.Proveedor:
	"""Proveedor para navegar dentro del comprimido ``ruta_archivo`` de ``contenedor``.

	:raises NoAdmitido: si la extensión no está registrada.
	"""
	extension = extension_comprimido(contenedor.nombre(ruta_archivo))
	if extension is None:
		raise base.NoAdmitido(_("No se puede abrir este tipo de comprimido."), ruta_archivo)
	proveedor = _comprimidos[extension](contenedor, ruta_archivo)
	proveedor.contenedor = (contenedor, ruta_archivo)
	return proveedor


def abrir_ruta(texto: str, actual: base.Ubicacion | None = None) -> tuple[base.Proveedor, str, str | None]:
	"""Interpreta lo escrito en «Ir a la carpeta» (o una ruta de la sesión).

	Devuelve ``(proveedor, carpeta, nombre_para_el_cursor)``. Si la ruta es un
	archivo, la carpeta es la suya y el nombre es el del archivo. Si la ruta
	atraviesa un comprimido (``C:\\a.zip\\docs``), devuelve el proveedor del
	comprimido y la ruta interna.

	:raises NoEncontrado: si no existe.
	:raises NoAdmitido: si el esquema no está registrado.
	"""
	texto = (texto or "").strip().strip('"')
	if "://" in texto:
		esquema = texto.split("://", 1)[0].lower()
		if esquema not in _esquemas and _activador_esquemas[0] is not None:
			# 2.0 (3.4): el complemento que declara el esquema en [[esquemas]] se activa aquí
			# (al restaurar la sesión, al escribir la dirección o al volver por el historial).
			try:
				_activador_esquemas[0](esquema)
			except Exception:  # noqa: BLE001 - sin el complemento, la dirección no se admite (abajo)
				log.warning("No se pudo activar el complemento del esquema %s", esquema, exc_info=True)
		if esquema not in _esquemas:
			raise base.NoAdmitido(_("No se admiten direcciones {e}://").format(e=esquema), texto)
		proveedor, ruta = _esquemas[esquema](texto)
		return proveedor, ruta, None
	if _SERVIDOR_SOLO.fullmatch(texto) and texto.strip("\\") not in (".", "?") and "red" in _esquemas:
		# 2.0 (9.3): «\\servidor» solo no existe para el disco (``lexists`` es falso): es la lista de
		# recursos de la raíz «Red» (Ir a la carpeta, Atrás y Adelante guardan «\\DS220»).
		proveedor, ruta = _esquemas["red"]("red://" + texto.strip("\\"))
		return proveedor, ruta, None
	texto = os.path.expandvars(os.path.expanduser(texto))
	if actual is not None and not os.path.isabs(texto) and not texto.startswith("\\\\"):
		if actual.proveedor.esquema == "local":
			texto = os.path.join(actual.ruta, texto)
		else:
			# Ruta relativa dentro de un proveedor no local.
			return actual.proveedor, actual.proveedor.unir(actual.ruta, texto), None
	ruta = rutas.normalizar(texto)
	if _local.existe(ruta):
		entrada = _local.info(ruta)
		if entrada.es_carpeta:
			return _local, ruta, None
		if es_comprimido(entrada.nombre):
			return abrir_comprimido(_local, ruta), "", None
		return _local, rutas.padre(ruta) or ruta, entrada.nombre
	# ¿Atraviesa un comprimido? Se busca el primer componente que sea un archivo comprimido.
	partes = ruta.split("\\")
	for i in range(len(partes) - 1, 0, -1):
		candidato = "\\".join(partes[:i])
		if es_comprimido(candidato) and _local.existe(candidato):
			proveedor = abrir_comprimido(_local, candidato)
			interior = "/".join(partes[i:])
			if proveedor.existe(interior):
				info = proveedor.info(interior)
				if info.es_carpeta:
					return proveedor, interior, None
				return proveedor, proveedor.padre(interior) or "", info.nombre
			raise base.NoEncontrado(_("No existe «{r}» dentro del comprimido.").format(r=interior), ruta)
	raise base.NoEncontrado(_("No existe la ruta {r}").format(r=ruta), ruta)
