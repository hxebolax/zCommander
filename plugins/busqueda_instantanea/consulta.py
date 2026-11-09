# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Traducción de consultas y lectura de respuestas (sin wx ni COM, para probarlo todo sin motores).

- La persona escribe con la sintaxis de Everything (``ext:pdf``, ``size:>1gb``,
  ``dm:today``, comodines, ``|`` para «o», ``!`` para «no»). Everything la
  entiende tal cual; para el índice de Windows se traduce a su SQL
  (``SELECT ... FROM SYSTEMINDEX WHERE ...``). Lo que el índice no admite se
  convierte en una búsqueda por el nombre, nunca en un error.
- Los patrones del diálogo Buscar archivos (``*.txt;*.md | *.bak``) se pasan a
  la misma sintaxis para que los dos motores los entiendan.
- La respuesta de Everything (``EVERYTHING_IPC_LISTW``, protocolo publicado en
  su ``everything_ipc.h``) se lee aquí desde bytes: no se distribuye nada de
  Everything, solo se habla su protocolo de mensajes.
"""

from __future__ import annotations

import datetime as _fecha
import re
import struct
from collections.abc import Iterable, Sequence

# ── Protocolo de Everything (everything_ipc.h) ───────────────────────────────

CLASE_VENTANA_EVERYTHING = "EVERYTHING_TASKBAR_NOTIFICATION"
COPYDATA_CONSULTA_W = 2
ELEMENTO_CARPETA = 0x1
ELEMENTO_UNIDAD = 0x2
_CABECERA_CONSULTA = struct.Struct("<5I")
_CABECERA_LISTA = struct.Struct("<7I")
_ELEMENTO = struct.Struct("<3I")

_UNIDADES = {"": 1, "b": 1, "kb": 1024, "k": 1024, "mb": 1024 ** 2, "m": 1024 ** 2, "gb": 1024 ** 3, "g": 1024 ** 3,
	"tb": 1024 ** 4, "t": 1024 ** 4}


class ErrorConsulta(ValueError):
	"""Respuesta o consulta que no se puede interpretar (mensaje en español)."""


def consulta_everything(texto: str, ventana_respuesta: int, id_respuesta: int, max_resultados: int,
		desplazamiento: int = 0, opciones: int = 0) -> bytes:
	"""Bytes de ``EVERYTHING_IPC_QUERYW``: cinco DWORD y el texto UTF-16 terminado en cero."""
	cabecera = _CABECERA_CONSULTA.pack(int(ventana_respuesta) & 0xFFFFFFFF, id_respuesta & 0xFFFFFFFF,
		opciones & 0xFFFFFFFF, desplazamiento & 0xFFFFFFFF, max(0, int(max_resultados)) & 0xFFFFFFFF)
	return cabecera + (texto or "").encode("utf-16-le") + b"\x00\x00"


def _cadena(buffer: bytes, desplazamiento: int) -> str:
	if desplazamiento <= 0 or desplazamiento >= len(buffer):
		return ""
	fin = desplazamiento
	while fin + 1 < len(buffer) and buffer[fin:fin + 2] != b"\x00\x00":
		fin += 2
	return buffer[desplazamiento:fin].decode("utf-16-le", errors="replace")


def leer_respuesta_everything(buffer: bytes) -> list[tuple[str, bool]]:
	"""Lee un ``EVERYTHING_IPC_LISTW``: lista de (ruta completa, es_carpeta).

	Cabecera de siete DWORD (totales, número de elementos y desplazamiento) y
	después un ``EVERYTHING_IPC_ITEMW`` por elemento: indicadores y las
	posiciones, desde el principio de la lista, del nombre y de la carpeta.
	"""
	if len(buffer) < _CABECERA_LISTA.size:
		raise ErrorConsulta("La respuesta de Everything está incompleta")
	_tc, _ta, _ti, _nc, _na, numero, _desp = _CABECERA_LISTA.unpack_from(buffer, 0)
	if _CABECERA_LISTA.size + numero * _ELEMENTO.size > len(buffer):
		raise ErrorConsulta("La respuesta de Everything dice tener más elementos de los que trae")
	resultado: list[tuple[str, bool]] = []
	for indice in range(numero):
		indicadores, pos_nombre, pos_carpeta = _ELEMENTO.unpack_from(buffer, _CABECERA_LISTA.size + indice * _ELEMENTO.size)
		nombre = _cadena(buffer, pos_nombre)
		carpeta = _cadena(buffer, pos_carpeta)
		if not nombre:
			continue
		if indicadores & ELEMENTO_UNIDAD or not carpeta:
			# Una unidad llega como «C:» sin carpeta; se devuelve como «C:\».
			ruta = nombre + "\\" if len(nombre) == 2 and nombre[1] == ":" else nombre
		else:
			ruta = carpeta.rstrip("\\") + "\\" + nombre
		resultado.append((ruta, bool(indicadores & (ELEMENTO_CARPETA | ELEMENTO_UNIDAD))))
	return resultado


def respuesta_de_ejemplo(elementos: Sequence[tuple[str, str, int]]) -> bytes:
	"""Construye un ``EVERYTHING_IPC_LISTW`` (nombre, carpeta, indicadores); sirve a las pruebas y al registro de fallos."""
	textos = b""
	posiciones: list[tuple[int, int, int]] = []
	base = _CABECERA_LISTA.size + len(elementos) * _ELEMENTO.size
	for nombre, carpeta, indicadores in elementos:
		pos_nombre = base + len(textos)
		textos += nombre.encode("utf-16-le") + b"\x00\x00"
		pos_carpeta = base + len(textos)
		textos += carpeta.encode("utf-16-le") + b"\x00\x00"
		posiciones.append((indicadores, pos_nombre, pos_carpeta))
	carpetas = sum(1 for _n, _c, i in elementos if i & ELEMENTO_CARPETA)
	cabecera = _CABECERA_LISTA.pack(carpetas, len(elementos) - carpetas, len(elementos), carpetas, len(elementos) - carpetas,
		len(elementos), 0)
	return cabecera + b"".join(_ELEMENTO.pack(*p) for p in posiciones) + textos


# ── Sintaxis de la persona ───────────────────────────────────────────────────


def terminos(texto: str) -> list[str]:
	"""Separa por espacios respetando las comillas («"informe anual" ext:pdf» son dos términos)."""
	return [t.replace('"', "") for t in re.findall(r'(?:[^\s"]+|"[^"]*")+', texto or "") if t.replace('"', "")]


def desde_patrones(patrones: str) -> str:
	"""Patrones del diálogo Buscar archivos (``*.txt;*.md | *.bak``) en sintaxis de Everything."""
	incluir, _barra, excluir = (patrones or "*").partition("|")
	partes = [p.strip() for p in re.split(r"[;,]", incluir) if p.strip() and p.strip() not in ("*", "*.*")]
	texto = "|".join(_entre_comillas(p) for p in partes)
	for patron in (p.strip() for p in re.split(r"[;,]", excluir) if p.strip()):
		texto += (" " if texto else "") + "!" + _entre_comillas(patron)
	return texto


def _entre_comillas(termino: str) -> str:
	return f'"{termino}"' if " " in termino else termino


def _sql_texto(valor: str) -> str:
	return "'" + valor.replace("'", "''") + "'"


def _like(patron: str) -> str:
	"""Comodines de nombre a LIKE: ``*`` → ``%``, ``?`` → ``_``; sin comodines, «contiene»."""
	escapado = patron.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
	if "*" not in patron and "?" not in patron:
		return f"%{escapado}%"
	return escapado.replace("*", "%").replace("?", "_")


def _tamano(valor: str) -> tuple[str, int] | None:
	encontrado = re.fullmatch(r"(>=|<=|>|<|=)?\s*(\d+(?:[.,]\d+)?)\s*([a-z]*)", valor.strip().lower())
	if not encontrado or encontrado.group(3) not in _UNIDADES:
		return None
	operador = encontrado.group(1) or "="
	numero = float(encontrado.group(2).replace(",", "."))
	return operador, int(numero * _UNIDADES[encontrado.group(3)])


def _fecha_desde(valor: str, hoy: _fecha.date) -> tuple[str, str] | None:
	"""``dm:today``, ``dm:yesterday``, ``dm:lastweek``, ``dm:lastmonth`` o ``dm:AAAA-MM-DD``: (operador, fecha)."""
	valor = valor.strip().lower()
	desplazamientos = {"today": 0, "hoy": 0, "yesterday": 1, "ayer": 1, "lastweek": 7, "thisweek": hoy.weekday(),
		"lastmonth": 30, "thismonth": hoy.day - 1}
	if valor in desplazamientos:
		inicio = hoy - _fecha.timedelta(days=desplazamientos[valor])
		return ">=", inicio.strftime("%Y/%m/%d")
	encontrado = re.fullmatch(r"(>=|<=|>|<|=)?(\d{4})-(\d{2})-(\d{2})", valor)
	if encontrado:
		return encontrado.group(1) or ">=", f"{encontrado.group(2)}/{encontrado.group(3)}/{encontrado.group(4)}"
	return None


def _condicion(termino: str, hoy: _fecha.date) -> str:
	"""Un término (sin «!» ni «|») como condición SQL del índice de Windows."""
	clave, dos_puntos, valor = termino.partition(":")
	clave = clave.lower()
	if dos_puntos and len(clave) > 1:
		if clave == "ext":
			extensiones = [e.strip().lstrip(".") for e in valor.split(";") if e.strip()]
			if extensiones:
				return "(" + " OR ".join(f"System.FileExtension = {_sql_texto('.' + e.lower())}" for e in extensiones) + ")"
		elif clave == "size":
			tamano = _tamano(valor)
			if tamano is not None:
				return f"System.Size {tamano[0]} {tamano[1]}"
		elif clave in ("dm", "datemodified"):
			fecha = _fecha_desde(valor, hoy)
			if fecha is not None:
				return f"System.DateModified {fecha[0]} {_sql_texto(fecha[1])}"
		elif clave in ("file", "folder") and not valor:
			return "System.Kind <> 'folder'" if clave == "file" else "System.Kind = 'folder'"
	return f"System.FileName LIKE {_sql_texto(_like(termino))}"


def a_sql_windows(texto: str, *, carpeta: str = "", contenido: str = "", max_resultados: int = 1000,
		hoy: _fecha.date | None = None) -> str:
	"""Consulta SQL del índice de búsqueda de Windows (proveedor ``Search.CollatorDSO``).

	``*.pdf`` en ``C:\\Docs`` da
	``SELECT TOP 1000 System.ItemPathDisplay FROM SYSTEMINDEX WHERE SCOPE='file:C:/Docs' AND System.FileName LIKE '%.pdf'``.
	"""
	hoy = hoy or _fecha.date.today()
	condiciones: list[str] = []
	if carpeta:
		condiciones.append(f"SCOPE={_sql_texto('file:' + carpeta.replace(chr(92), '/').rstrip('/'))}")
	for termino in terminos(texto):
		negado = termino.startswith("!")
		termino = termino.lstrip("!")
		if not termino:
			continue
		alternativas = [t for t in termino.split("|") if t]
		if not alternativas:
			continue
		partes = [_condicion(t, hoy) for t in alternativas]
		condicion = partes[0] if len(partes) == 1 else "(" + " OR ".join(partes) + ")"
		condiciones.append(f"NOT {condicion}" if negado else condicion)
	if contenido.strip():
		frase = contenido.strip().replace('"', "")
		condiciones.append(f"CONTAINS(*, {_sql_texto(chr(34) + frase + chr(34))})")
	sql = f"SELECT TOP {max(1, int(max_resultados))} System.ItemPathDisplay FROM SYSTEMINDEX"
	if condiciones:
		sql += " WHERE " + " AND ".join(condiciones)
	return sql


def a_everything(texto: str, *, carpeta: str = "") -> str:
	"""Texto para Everything: el de la persona y, si hay carpeta, la ruta como primer término."""
	texto = (texto or "").strip()
	if carpeta:
		texto = f'"{carpeta.rstrip(chr(92))}{chr(92)}" {texto}'.strip()
	return texto


# ── Filtros comunes a los dos motores ────────────────────────────────────────


def _clave(ruta: str) -> str:
	return ruta.replace("/", "\\").rstrip("\\").casefold()


def excluida(ruta: str, excluidas: Iterable[str]) -> bool:
	"""Verdadero si ``ruta`` está dentro de alguna de las carpetas excluidas (o es una de ellas)."""
	clave = _clave(ruta)
	for carpeta in excluidas:
		base = _clave(str(carpeta))
		if base and (clave == base or clave.startswith(base + "\\")):
			return True
	return False


def filtrar(rutas: Iterable[str], excluidas: Sequence[str], maximo: int, es_oculta=None) -> list[str]:
	"""Quita las excluidas y, si se da ``es_oculta``, las ocultas o de sistema; corta en ``maximo``."""
	resultado: list[str] = []
	for ruta in rutas:
		if excluidas and excluida(ruta, excluidas):
			continue
		if es_oculta is not None and es_oculta(ruta):
			continue
		resultado.append(ruta)
		if len(resultado) >= maximo:
			break
	return resultado


def nombre_y_carpeta(ruta: str) -> tuple[str, str]:
	"""(nombre, carpeta) de una ruta para las columnas de la lista."""
	limpia = ruta.rstrip("\\")
	carpeta, _barra, nombre = limpia.rpartition("\\")
	if not carpeta:
		return limpia, ""
	return nombre, carpeta + ("\\" if carpeta.endswith(":") else "")
