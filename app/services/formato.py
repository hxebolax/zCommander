# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Formato de tamaños, fechas, atributos y recuentos para mostrar y anunciar.

Todo lo que la persona ve o el lector de pantalla lee pasa por aquí, para que
un tamaño se diga igual en la lista, en la línea de resumen y en los anuncios
(«1,2 MB» y no «1234567» en un sitio y «1.2M» en otro).
"""

from __future__ import annotations

import builtins
import time
from datetime import datetime

# Bits de atributos de Windows (los mismos que st_file_attributes).
SOLO_LECTURA = 0x1
OCULTO = 0x2
SISTEMA = 0x4
CARPETA = 0x10
ARCHIVO = 0x20
NORMAL = 0x80
TEMPORAL = 0x100
PUNTO_ANALISIS = 0x400
COMPRIMIDO = 0x800
SIN_CONEXION = 0x1000
NO_INDEXAR = 0x2000
CIFRADO = 0x4000
DESCARGA_AL_ACCEDER = 0x400000

_UNIDADES = ("bytes", "KB", "MB", "GB", "TB", "PB")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _decimal(valor: float, decimales: int) -> str:
	"""Número con coma decimal de España y sin ceros sobrantes («1,2», «15», «1,05»)."""
	texto = f"{valor:.{decimales}f}"
	if "." in texto:
		texto = texto.rstrip("0").rstrip(".")
	return texto.replace(".", ",")


def miles(numero: int) -> str:
	"""Entero con separador de miles («1.234.567»); los de cuatro cifras sin punto, como recomienda la RAE."""
	texto = f"{numero:,}".replace(",", ".")
	return texto if abs(numero) >= 10000 else str(numero)


def tamano_legible(bytes_: int | float) -> str:
	"""«0 bytes», «1 byte», «512 bytes», «1,2 KB», «3,45 GB»."""
	if bytes_ is None or bytes_ < 0:
		return ""
	if bytes_ < 1024:
		n = int(bytes_)
		return _("1 byte") if n == 1 else _("{n} bytes").format(n=n)
	valor = float(bytes_)
	indice = 0
	while valor >= 1024 and indice < len(_UNIDADES) - 1:
		valor /= 1024
		indice += 1
	decimales = 2 if valor < 10 else 1 if valor < 100 else 0
	return f"{_decimal(valor, decimales)} {_UNIDADES[indice]}"


def tamano(bytes_: int, modo: str = "legible") -> str:
	"""Tamaño según la preferencia ``paneles.formato_tamano``.

	:param modo: ``bytes`` (siempre en bytes con miles), ``legible`` (KB, MB...)
		o ``mixto`` (bytes hasta 1 MB, legible después).
	"""
	if bytes_ is None or bytes_ < 0:
		return ""
	if modo == "bytes" or (modo == "mixto" and bytes_ < 1024 * 1024):
		return miles(int(bytes_))
	return tamano_legible(bytes_)


def fecha(marca: float, modo: str = "corta") -> str:
	"""Fecha y hora según ``paneles.formato_fecha`` (``corta``, ``larga`` o ``iso``)."""
	if not marca:
		return ""
	try:
		momento = datetime.fromtimestamp(marca)
	except (OverflowError, OSError, ValueError):
		return ""
	if modo == "iso":
		return momento.strftime("%Y-%m-%d %H:%M")
	if modo == "larga":
		return momento.strftime("%d/%m/%Y %H:%M:%S")
	return momento.strftime("%d/%m/%Y %H:%M")


def duracion(segundos: float) -> str:
	"""«4 s», «1 min 20 s», «2 h 5 min»."""
	segundos = max(0, int(round(segundos)))
	if segundos < 60:
		return _("{s} s").format(s=segundos)
	minutos, segundos = divmod(segundos, 60)
	if minutos < 60:
		return _("{m} min {s} s").format(m=minutos, s=segundos) if segundos else _("{m} min").format(m=minutos)
	horas, minutos = divmod(minutos, 60)
	return _("{h} h {m} min").format(h=horas, m=minutos) if minutos else _("{h} h").format(h=horas)


def velocidad(bytes_por_segundo: float) -> str:
	"""«12,5 MB/s»."""
	if bytes_por_segundo <= 0:
		return ""
	return _("{v}/s").format(v=tamano_legible(bytes_por_segundo))


def atributos_cortos(atributos: int) -> str:
	"""Letras al estilo Norton: «RHSA» con guion en las que faltan («-H-A»)."""
	return "".join(
		letra if atributos & bit else "-"
		for letra, bit in (("R", SOLO_LECTURA), ("H", OCULTO), ("S", SISTEMA), ("A", ARCHIVO))
	)


def atributos_largos(atributos: int) -> str:
	"""Texto para el lector: «Solo lectura, Oculto». Vacío si no hay ninguno de interés."""
	nombres = [
		(SOLO_LECTURA, _("Solo lectura")), (OCULTO, _("Oculto")), (SISTEMA, _("Sistema")),
		(ARCHIVO, _("Archivo")), (COMPRIMIDO, _("Comprimido")), (CIFRADO, _("Cifrado")),
		(SIN_CONEXION, _("Sin conexión")), (DESCARGA_AL_ACCEDER, _("Solo en la nube")),
		(PUNTO_ANALISIS, _("Enlace")),
	]
	return ", ".join(texto for bit, texto in nombres if atributos & bit)


def plural(n: int, singular: str, plural_: str) -> str:
	"""«1 archivo», «3 archivos» (los textos ya traducidos, con ``{n}``)."""
	return (singular if n == 1 else plural_).format(n=miles(n))


def recuento(carpetas: int, archivos: int) -> str:
	"""«12 carpetas y 40 archivos», «1 carpeta», «Vacía»."""
	partes = []
	if carpetas:
		partes.append(plural(carpetas, _("{n} carpeta"), _("{n} carpetas")))
	if archivos:
		partes.append(plural(archivos, _("{n} archivo"), _("{n} archivos")))
	if not partes:
		return _("Vacía")
	return _(" y ").join(partes)


def ahora_corto() -> str:
	"""Hora actual «14:05:33» para el historial de anuncios."""
	return time.strftime("%H:%M:%S")
