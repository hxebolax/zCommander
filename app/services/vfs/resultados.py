# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor de una lista de resultados (búsqueda, vista plana, cesta).

Muestra en una sola «carpeta» virtual una lista de rutas locales absolutas.
Las operaciones (copiar, eliminar, ver...) trabajan sobre las rutas reales: la
``ruta`` de cada ``Entrada`` es la ruta real y ``ruta_real`` dice su carpeta
(columna Ruta). La raíz virtual es la cadena vacía y no tiene padre: Retroceso
vuelve a la ubicación anterior del panel (lo decide el panel).
"""

from __future__ import annotations

import builtins
import os
from collections.abc import Sequence
from typing import BinaryIO

from app.services.vfs import base
from app.services.vfs.local import ProveedorLocal


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ProveedorResultados(base.Proveedor):
	"""Lista fija de rutas. Las que ya no existen se omiten al listar."""

	esquema = "resultados"

	def __init__(self, titulo: str, rutas: Sequence[str]) -> None:
		super().__init__()
		self.titulo = titulo
		self.rutas = list(dict.fromkeys(rutas))
		self._local = ProveedorLocal()
		self.capacidades = base.Capacidades(escribir=True, papelera=True, atributos=True)

	def descripcion(self) -> str:
		return _("Lista de resultados")

	def listar(self, ruta: str, cancelacion=None) -> list[base.Entrada]:
		if ruta:
			# Dentro de una carpeta de la lista se navega en el disco real.
			return self._local.listar(ruta, cancelacion)
		entradas = []
		for i, real in enumerate(self.rutas):
			if i % 256 == 0:
				base.comprobar(cancelacion)
			try:
				entrada = self._local.info(real)
			except base.ErrorArchivos:
				continue
			entradas.append(entrada.con(ruta_real=os.path.dirname(real)))
		return entradas

	def quitar(self, rutas: Sequence[str]) -> None:
		"""Saca rutas de la lista (al eliminarlas o moverlas)."""
		fuera = {r.casefold() for r in rutas}
		self.rutas = [r for r in self.rutas if r.casefold() not in fuera]

	def info(self, ruta: str) -> base.Entrada:
		if not ruta:
			return base.Entrada(self.titulo, "", es_carpeta=True)
		return self._local.info(ruta)

	def padre(self, ruta: str) -> str | None:
		return None

	def unir(self, carpeta: str, nombre: str) -> str:
		return self._local.unir(carpeta, nombre) if carpeta else nombre

	def raiz(self, ruta: str) -> str:
		return ""

	def mostrar(self, ruta: str) -> str:
		return self.titulo if not ruta else self._local.mostrar(ruta)

	def abrir_lectura(self, ruta: str) -> BinaryIO:
		return self._local.abrir_lectura(ruta)

	def abrir_escritura(self, ruta: str, tamano: int = -1) -> BinaryIO:
		return self._local.abrir_escritura(ruta, tamano)

	def eliminar(self, ruta: str, recursivo: bool = False, cancelacion=None) -> None:
		self._local.eliminar(ruta, recursivo, cancelacion)
		self.quitar([ruta])

	def renombrar(self, origen: str, destino: str) -> None:
		self._local.renombrar(origen, destino)
		self.rutas = [destino if r.casefold() == origen.casefold() else r for r in self.rutas]

	def fijar_tiempos(self, ruta: str, modificado: float, creado: float = 0.0) -> None:
		self._local.fijar_tiempos(ruta, modificado, creado)

	def fijar_atributos(self, ruta: str, atributos: int) -> None:
		self._local.fijar_atributos(ruta, atributos)

	def crear_carpeta(self, ruta: str) -> None:
		raise base.NoAdmitido(_("No se pueden crear carpetas en una lista de resultados."), ruta)

	def ruta_local(self, ruta: str) -> str | None:
		return ruta or None

	def mismo_volumen(self, ruta_a: str, ruta_b: str) -> bool:
		return self._local.mismo_volumen(ruta_a, ruta_b)
