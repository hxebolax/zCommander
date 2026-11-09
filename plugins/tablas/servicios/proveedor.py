# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Una base SQLite vista como carpeta: una entrada ``<tabla>.csv`` por tabla y vista (sin wx).

Solo lectura. Leer una entrada genera su CSV en el momento (UTF-8 con BOM y
coma, como lo espera una hoja de cálculo), así copiar una tabla al otro panel
la exporta a CSV sin hacer nada más. Las rutas internas son como las de un
comprimido: ``""`` es la raíz y ``"clientes.csv"`` una tabla.
"""

from __future__ import annotations

import builtins
import io
import os
import re
import tempfile
import threading
from typing import BinaryIO

from app.plugins import api

from . import sqlite

#: Caracteres que no pueden ir en un nombre de archivo de Windows.
_PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def nombre_entrada(objeto: str) -> str:
	"""Nombre de archivo de una tabla: los caracteres prohibidos pasan a «_»."""
	return _PROHIBIDOS.sub("_", objeto).rstrip(" .") + ".csv"


class ProveedorSQLite(api.Proveedor):
	"""Tablas y vistas de una base SQLite como archivos CSV de solo lectura."""

	esquema = "sqlite"

	def __init__(self, contenedor: api.Proveedor, ruta_archivo: str, ruta_local: str, carpeta_temporal: str | None = None) -> None:
		super().__init__()
		#: Donde pasa a disco el CSV de una tabla grande (la caché del complemento, dentro de ``data``).
		self.carpeta_temporal = carpeta_temporal
		self.capacidades = api.Capacidades(escribir=False)
		self.contenedor = (contenedor, ruta_archivo)
		self.ruta_archivo = ruta_archivo
		self.ruta_local_base = ruta_local
		self._candado = threading.Lock()
		self._objetos: dict[str, tuple[str, str]] | None = None
		self._firma: tuple[int, int] | None = None

	# Índice de tablas -------------------------------------------------------

	def _firma_actual(self) -> tuple[int, int] | None:
		try:
			estado = os.stat(self.ruta_local_base)
		except OSError:
			return None
		return estado.st_mtime_ns, estado.st_size

	def objetos(self) -> dict[str, tuple[str, str]]:
		"""Nombre de entrada → (nombre del objeto en SQLite, «table» o «view»). Se relee si la base cambia."""
		with self._candado:
			firma = self._firma_actual()
			if self._objetos is None or firma != self._firma:
				try:
					lista = sqlite.objetos(self.ruta_local_base)
				except sqlite.ErrorSQL as error:
					raise api.ErrorArchivos(str(error), self.ruta_archivo) from error
				except Exception as error:  # noqa: BLE001 - una base dañada se dice como error de archivos
					raise api.ErrorArchivos(_("La base de datos está dañada o no se puede leer: {e}").format(e=error),
						self.ruta_archivo) from error
				indice: dict[str, tuple[str, str]] = {}
				for nombre, tipo in lista:
					entrada = nombre_entrada(nombre)
					base, n = entrada[:-4], 2
					while entrada.casefold() in (e.casefold() for e in indice):
						entrada = f"{base} ({n}).csv"
						n += 1
					indice[entrada] = (nombre, tipo)
				self._objetos, self._firma = indice, firma
			return self._objetos

	def objeto(self, ruta: str) -> str:
		"""Nombre en SQLite de la tabla de la entrada ``ruta``."""
		ruta = self._limpia(ruta)
		for entrada, (nombre, _tipo) in self.objetos().items():
			if entrada.casefold() == ruta.casefold():
				return nombre
		raise api.NoEncontrado(_("No existe la tabla «{r}» en la base de datos").format(r=ruta), ruta)

	# Navegación -------------------------------------------------------------

	@staticmethod
	def _limpia(ruta: str) -> str:
		return (ruta or "").replace("\\", "/").strip("/")

	def _entrada(self, nombre: str) -> api.Entrada:
		firma = self._firma or (0, 0)
		return api.Entrada(nombre=nombre, ruta=nombre, es_carpeta=False, tamano=-1, modificado=firma[0] / 1e9)

	def listar(self, ruta: str, cancelacion=None) -> list[api.Entrada]:
		if self._limpia(ruta):
			raise api.NoEncontrado(_("Dentro de una tabla no hay carpetas"), ruta)
		return [self._entrada(nombre) for nombre in self.objetos()]

	def info(self, ruta: str) -> api.Entrada:
		ruta = self._limpia(ruta)
		if not ruta:
			return api.Entrada(nombre=self.nombre(""), ruta="", es_carpeta=True)
		self.objeto(ruta)
		nombre = next(e for e in self.objetos() if e.casefold() == ruta.casefold())
		return self._entrada(nombre)

	def padre(self, ruta: str) -> str | None:
		return "" if self._limpia(ruta) else None

	def unir(self, carpeta: str, nombre: str) -> str:
		carpeta = self._limpia(carpeta)
		return f"{carpeta}/{nombre}" if carpeta else nombre

	def raiz(self, ruta: str) -> str:
		return ""

	def nombre(self, ruta: str) -> str:
		ruta = self._limpia(ruta)
		if ruta:
			return ruta.rpartition("/")[2]
		contenedor, archivo = self.contenedor
		return contenedor.nombre(archivo)

	def mostrar(self, ruta: str) -> str:
		contenedor, archivo = self.contenedor
		texto = contenedor.mostrar(archivo)
		ruta = self._limpia(ruta)
		if not ruta:
			return texto
		separador = "/" if "://" in texto else "\\"
		return texto + separador + ruta

	def descripcion(self) -> str:
		return _("Base de datos SQLite")

	# Contenido --------------------------------------------------------------

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		"""El CSV de la tabla, generado en un temporal en memoria (pasa a disco si es grande)."""
		tabla = self.objeto(ruta)
		temporal = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024, dir=self.carpeta_temporal)  # noqa: SIM115
		texto = io.TextIOWrapper(temporal, encoding="utf-8-sig", newline="", write_through=True)
		try:
			sqlite.exportar_csv(self.ruta_local_base, tabla, texto)
			texto.flush()
			texto.detach()
		except sqlite.ErrorSQL as error:
			temporal.close()
			raise api.ErrorArchivos(str(error), ruta) from error
		except Exception as error:  # noqa: BLE001 - se dice como error de archivos
			temporal.close()
			raise api.ErrorArchivos(_("No se pudo leer la tabla {t}: {e}").format(t=tabla, e=error), ruta) from error
		temporal.seek(0)
		return temporal  # type: ignore[return-value]

	def ruta_local(self, ruta: str) -> str | None:
		return None


def fabrica(contenedor: api.Proveedor, ruta_archivo: str, carpeta_temporal: str | None = None) -> api.Proveedor:
	"""Fábrica de ``[[comprimidos]]``: comprueba la cabecera «SQLite format 3» o lanza ``NoAdmitido``.

	Con ``NoAdmitido``, Intro abre el archivo con su programa (14.5).
	"""
	try:
		with contenedor.abrir_lectura(ruta_archivo) as flujo:
			cabecera = flujo.read(len(sqlite.CABECERA))
	except api.ErrorArchivos:
		raise
	except OSError as error:
		raise api.ErrorAcceso(_("No se pudo leer {r}: {e}").format(r=ruta_archivo, e=error), ruta_archivo) from error
	if not sqlite.es_sqlite(cabecera):
		raise api.NoAdmitido(_("No es una base de datos SQLite"), ruta_archivo)
	local = contenedor.ruta_local(ruta_archivo) or contenedor.extraer_temporal(ruta_archivo)
	return ProveedorSQLite(contenedor, ruta_archivo, local, carpeta_temporal)
