# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Eliminar: a la papelera o definitivamente.

- Papelera: Send2Trash en el hilo de la operación (con COM en modo STA), por
  lotes para poder cancelar entre lotes. Solo en local y si la unidad la
  admite (la interfaz lo comprueba antes y avisa).
- Definitivo: recorre de dentro hacia fuera con el recorrido único (no sigue
  enlaces ni uniones: los borra como enlace). Los archivos de solo lectura se
  preguntan (Eliminar, Eliminar todos, Omitir, Cancelar).
"""

from __future__ import annotations

import builtins
import logging

from app.services import formato
from app.services.operaciones.modelo import ContextoEjecucion, Estado, Operacion, claves_carril
from app.services.recorrido import recorrer
from app.services.vfs import base

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class OperacionEliminar(Operacion):
	"""Elimina ``entradas`` de ``proveedor``.

	:param papelera: enviar a la papelera (si no, definitivo).
	"""

	def __init__(self, proveedor: base.Proveedor, entradas: list[base.Entrada], papelera: bool = True) -> None:
		super().__init__()
		self.tipo = "papelera" if papelera else "eliminar"
		self.proveedor = proveedor
		self.entradas = [e for e in entradas if not e.es_superior]
		self.papelera = papelera
		self._borrar_solo_lectura: bool | None = None

	def descripcion(self) -> str:
		n = len(self.entradas)
		que = self.entradas[0].nombre if n == 1 else formato.plural(n, _("{n} elemento"), _("{n} elementos"))
		return (_("Enviar {que} a la papelera") if self.papelera else _("Eliminar {que}")).format(que=que)

	@property
	def carriles(self) -> frozenset[str]:
		if not self.entradas:
			return frozenset()
		return frozenset(claves_carril(self.proveedor, [e.ruta for e in self.entradas]))

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		if not self.entradas:
			return []
		return [(self.proveedor.esquema, self.proveedor.padre(self.entradas[0].ruta) or "")]

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.EJECUTANDO)
		self.progresar(archivos_total=len(self.entradas))
		if self.papelera:
			self._a_papelera(ctx)
			return
		proveedor_panel = self.proveedor
		self.proveedor = proveedor_panel.clonar()
		try:
			with self.proveedor.transaccion():
				self._definitivo(ctx)
		finally:
			if self.proveedor is not proveedor_panel:
				self.proveedor.cerrar()
			self.proveedor = proveedor_panel

	def _a_papelera(self, ctx: ContextoEjecucion) -> None:
		from app.services.windows import papelera

		rutas = [self.proveedor.ruta_local(e.ruta) or e.ruta for e in self.entradas]
		lote = 50
		for inicio in range(0, len(rutas), lote):
			ctx.comprobar()
			trozo = rutas[inicio:inicio + lote]
			self.progresar(actual=trozo[0])
			try:
				papelera.enviar(trozo)
				self.sumar(archivos_hechos=len(trozo))
			except base.ErrorArchivos as error:
				self.anotar_error(trozo[0], error.mensaje)
		quitar = getattr(self.proveedor, "quitar", None)
		if callable(quitar):
			quitar(rutas)

	def _definitivo(self, ctx: ContextoEjecucion) -> None:
		for entrada in self.entradas:
			ctx.comprobar()
			self.progresar(actual=entrada.nombre)
			try:
				if entrada.es_carpeta and not entrada.es_enlace:
					for elemento in recorrer(self.proveedor, entrada.ruta, ctx.token, carpetas_despues=True,
							al_error=lambda r, e: self.anotar_error(r, e.mensaje)):
						self._borrar(ctx, elemento.entrada)
				self._borrar(ctx, entrada)
				self.sumar(archivos_hechos=1)
			except base.Cancelado:
				raise
			except base.ErrorArchivos as error:
				self.anotar_error(entrada.ruta, error.mensaje)

	def _borrar(self, ctx: ContextoEjecucion, entrada: base.Entrada) -> None:
		ctx.comprobar()
		if entrada.solo_lectura and not entrada.es_carpeta:
			if self._borrar_solo_lectura is None:
				with ctx.esperando():
					eleccion = ctx.decisor.elegir(
						_("Archivo de solo lectura"),
						_("«{n}» es de solo lectura. ¿Eliminarlo?").format(n=entrada.nombre),
						[_("&Eliminar"), _("Eliminar &todos"), _("&Omitir"), _("&Cancelar")], predeterminada=2, escape=3, operacion=self,
					)
				if eleccion == 3:
					raise base.Cancelado()
				if eleccion == 2:
					self.sumar(omitidos=1)
					return
				if eleccion == 1:
					self._borrar_solo_lectura = True
		try:
			self.proveedor.eliminar(entrada.ruta, recursivo=False, cancelacion=ctx.token)
		except base.ErrorArchivos as error:
			self.anotar_error(entrada.ruta, error.mensaje)
