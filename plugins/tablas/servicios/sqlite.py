# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bases SQLite: tablas, estructura, exportación y consultas (sin wx).

Cada llamada abre su propia conexión (``sqlite3`` no comparte conexiones entre
hilos) y la cierra al terminar. En solo lectura la base se abre con
``mode=ro`` y, además, un autorizador rechaza cualquier orden que escriba,
para dar un mensaje claro en español en lugar del error genérico de SQLite.
"""

from __future__ import annotations

import builtins
import sqlite3
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.plugins import api

from .datos import Tabla, completar_cabeceras

CABECERA = b"SQLite format 3\x00"
EXTENSIONES = ("db", "sqlite", "sqlite3")

# Acciones del autorizador que solo leen (el resto se rechaza en solo lectura).
_LECTURA = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_PRAGMA,
	getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
_PRAGMAS_LECTURA = {"table_info", "table_xinfo", "index_list", "index_info", "foreign_key_list", "database_list",
	"compile_options", "user_version", "schema_version", "page_count", "page_size", "encoding", "integrity_check",
	"quick_check", "table_list", "function_list", "collation_list", "freelist_count"}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorSQL(Exception):
	"""Error de una consulta con el mensaje en español (y el de SQLite detrás)."""


def es_sqlite(cabecera: bytes) -> bool:
	return cabecera.startswith(CABECERA)


def es_archivo_sqlite(ruta: str) -> bool:
	try:
		with open(ruta, "rb") as archivo:
			return es_sqlite(archivo.read(len(CABECERA)))
	except OSError:
		return False


def citar(nombre: str) -> str:
	"""Identificador entre comillas dobles, con las comillas de dentro duplicadas."""
	return '"' + nombre.replace('"', '""') + '"'


@contextmanager
def conectar(ruta: str, solo_lectura: bool = True) -> Iterator[sqlite3.Connection]:
	uri = "file:" + urllib.parse.quote(ruta.replace("\\", "/"), safe="/:") + ("?mode=ro" if solo_lectura else "?mode=rw")
	try:
		conexion = sqlite3.connect(uri, uri=True, timeout=5)
	except sqlite3.Error as error:
		raise ErrorSQL(_("No se pudo abrir la base de datos: {e}").format(e=error)) from error
	try:
		if solo_lectura:
			conexion.set_authorizer(_autorizador_lectura)
		yield conexion
	finally:
		conexion.close()


def _autorizador_lectura(accion: int, arg1: Any, arg2: Any, _base: Any, _origen: Any) -> int:
	if accion in _LECTURA:
		if accion == sqlite3.SQLITE_PRAGMA and arg2 is not None and str(arg1).lower() not in _PRAGMAS_LECTURA:
			return sqlite3.SQLITE_DENY
		return sqlite3.SQLITE_OK
	return sqlite3.SQLITE_DENY


def objetos(ruta: str) -> list[tuple[str, str]]:
	"""(nombre, «table» o «view») de las tablas y vistas, sin las internas de SQLite."""
	with conectar(ruta) as conexion:
		filas = conexion.execute(
			"SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' "
			"ORDER BY name COLLATE NOCASE").fetchall()
	return [(str(n), str(t)) for n, t in filas]


def estructura(ruta: str, tabla: str) -> list[tuple[str, str]]:
	"""(columna, tipo) de una tabla o vista; «sin tipo» si SQLite no lo sabe."""
	with conectar(ruta) as conexion:
		filas = conexion.execute(f"PRAGMA table_info({citar(tabla)})").fetchall()
	return [(str(f[1]), str(f[2]) or _("sin tipo")) for f in filas]


def contar(ruta: str, tabla: str) -> int:
	with conectar(ruta) as conexion:
		return int(conexion.execute(f"SELECT COUNT(*) FROM {citar(tabla)}").fetchone()[0])


def texto_valor(valor: Any) -> str:
	"""Celda como texto: «NULL» se deja vacío y los binarios se describen («Datos binarios, 120 bytes»)."""
	if valor is None:
		return ""
	if isinstance(valor, bytes):
		return _("Datos binarios, {n} bytes").format(n=len(valor))
	if isinstance(valor, float) and valor.is_integer():
		return str(int(valor)) if abs(valor) < 1e15 else str(valor)
	return str(valor)


def leer_tabla(ruta: str, tabla: str, filas_maximas: int = 1_000_000, cancelacion: Any = None) -> Tabla:
	with conectar(ruta) as conexion:
		tipo = conexion.execute("SELECT type FROM sqlite_master WHERE name = ?", (tabla,)).fetchone()
		cursor = conexion.execute(f"SELECT * FROM {citar(tabla)}")
		resultado = _leer_cursor(cursor, tabla, filas_maximas, cancelacion)
	resultado.origen = _("vista") if tipo and tipo[0] == "view" else _("tabla")
	resultado.estructura = estructura(ruta, tabla)
	return resultado


def _leer_cursor(cursor: sqlite3.Cursor, nombre: str, filas_maximas: int, cancelacion: Any) -> Tabla:
	cabeceras = [str(d[0]) for d in cursor.description or ()]
	filas: list[tuple[str, ...]] = []
	truncada = False
	while True:
		api.comprobar(cancelacion)
		lote = cursor.fetchmany(1000)
		if not lote:
			break
		for fila in lote:
			if len(filas) >= filas_maximas:
				truncada = True
				break
			filas.append(tuple(texto_valor(v) for v in fila))
		if truncada:
			break
	return Tabla(nombre, completar_cabeceras(cabeceras, len(cabeceras)), filas, _("consulta"), truncada=truncada)


def exportar_csv(ruta: str, tabla: str, salida: Any, separador: str = ",") -> int:
	"""Escribe la tabla como CSV en ``salida`` (texto, con ``newline=""``); devuelve las filas escritas."""
	import csv

	escritor = csv.writer(salida, delimiter=separador, lineterminator="\r\n")
	with conectar(ruta) as conexion:
		cursor = conexion.execute(f"SELECT * FROM {citar(tabla)}")
		escritor.writerow([d[0] for d in cursor.description or ()])
		total = 0
		while lote := cursor.fetchmany(1000):
			escritor.writerows([[texto_valor(v) for v in fila] for fila in lote])
			total += len(lote)
	return total


def consultar(ruta: str, sql: str, solo_lectura: bool = True, filas_maximas: int = 1_000_000, cancelacion: Any = None) -> Tabla:
	"""Ejecuta UNA consulta. Con ``solo_lectura``, todo lo que escribe se rechaza con un mensaje claro.

	Sin solo lectura, los cambios se guardan (``commit``) y la tabla devuelta dice cuántas filas cambiaron.
	"""
	sql = sql.strip().rstrip(";").strip()
	if not sql:
		raise ErrorSQL(_("Escriba una consulta"))
	if not sqlite3.complete_statement(sql + ";"):
		raise ErrorSQL(_("La consulta está incompleta: revise las comillas y los paréntesis"))
	with conectar(ruta, solo_lectura) as conexion:
		try:
			cursor = conexion.execute(sql)
		except sqlite3.DatabaseError as error:
			if solo_lectura and "not authorized" in str(error).lower():
				raise ErrorSQL(_("La base está abierta en solo lectura: esta consulta cambiaría datos y no se ejecuta. "
					"Puede desactivar «Solo lectura» en las preferencias del complemento.")) from error
			raise ErrorSQL(_("Error en la consulta: {e}").format(e=error)) from error
		except sqlite3.Warning as error:
			raise ErrorSQL(_("Solo se puede ejecutar una consulta cada vez: {e}").format(e=error)) from error
		if cursor.description is None:
			conexion.commit()
			cambiadas = max(0, cursor.rowcount)
			return Tabla(_("Resultado"), [_("Resultado")], [(_("{n} filas cambiadas").format(n=cambiadas),)], _("consulta"))
		return _leer_cursor(cursor, _("Resultado"), filas_maximas, cancelacion)
