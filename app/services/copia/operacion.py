# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Crear y restaurar copias como operaciones del motor (diseño 2.0, 7.5 y 7.6). Sin wx.

Así tienen progreso, se pueden cancelar (crear) y aparecen en la ventana de
operaciones como cualquier copia de archivos; la interfaz nunca se bloquea
mientras se comprimen los registros o se deriva la clave con scrypt.
"""

from __future__ import annotations

import builtins
import logging
from pathlib import Path

from app.services import formato as fmt
from app.services.copia import crear, formato, pendiente, restaurar
from app.services.operaciones.modelo import ContextoEjecucion, Estado, Operacion

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class OperacionCrearCopia(Operacion):
	"""Crea un ``.zcbackup`` o un ``.zcperfil``."""

	tipo = "copia"

	def __init__(self, destino: Path, partes: list[str], tipo: str = "copia", modo_secretos: str = "excluidos",
			contrasena: str | None = None, descripcion: str = "", ruta_datos: Path | None = None) -> None:
		super().__init__()
		self.destino = Path(destino)
		self.partes = list(partes)
		self.tipo_copia = tipo
		self.modo_secretos = modo_secretos
		self._contrasena = contrasena
		self.texto_descripcion = descripcion
		self.ruta_datos = ruta_datos
		self.tamano_final = 0
		self.mensaje_error = ""

	def descripcion(self) -> str:
		if self.tipo_copia == "perfil":
			return _("Exportar el perfil {n}").format(n=self.destino.name)
		return _("Crear la copia de seguridad {n}").format(n=self.destino.name)

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		self.cambiar_estado(Estado.EJECUTANDO)
		self.progresar(actual=self.destino.name)

		def progreso(hechos: int, total: int) -> None:
			self.progresar(bytes_hechos=hechos, bytes_total=total)
			ctx.comprobar()

		try:
			crear.crear_copia(self.destino, self.partes, self.tipo_copia, self.modo_secretos, self._contrasena,
				self.texto_descripcion, progreso, ctx.token, ruta_datos=self.ruta_datos)
		except formato.ErrorCopia as error:
			self.mensaje_error = error.mensaje
			raise
		finally:
			# La contraseña no se queda en memoria más de lo necesario.
			self._contrasena = None
		self.tamano_final = self.destino.stat().st_size

	def resumen(self) -> str:
		if self.estado == Estado.TERMINADA:
			partes = fmt.plural(len(self.partes), _("{n} parte"), _("{n} partes"))
			plantilla = _("Perfil exportado: {t}, {p}") if self.tipo_copia == "perfil" else _("Copia creada: {t}, {p}")
			return plantilla.format(t=fmt.tamano_legible(self.tamano_final), p=partes)
		if self.estado == Estado.FALLIDA and self.mensaje_error:
			return _("No se pudo crear la copia: {e}").format(e=self.mensaje_error)
		return super().resumen()


class OperacionRestaurarCopia(Operacion):
	"""Restaura al momento (partes «En el momento») o prepara la restauración para el siguiente arranque."""

	tipo = "restaurar_copia"
	admite_pausa = False

	def __init__(self, ruta: Path, plan: restaurar.PlanRestauracion, secretos: dict[str, str] | None,
			ruta_datos: Path | None = None) -> None:
		super().__init__()
		self.ruta = Path(ruta)
		self.plan = plan
		self._secretos = secretos
		self.ruta_datos = ruta_datos
		self.inmediata = restaurar.es_inmediata(plan.partes)
		self.resultado: pendiente.ResultadoRestauracion | None = None
		self.info_pendiente: pendiente.InfoPendiente | None = None

	def descripcion(self) -> str:
		return _("Restaurar la copia {n}").format(n=self.ruta.name)

	def ejecutar(self, ctx: ContextoEjecucion) -> None:
		from app.core import paths

		self.cambiar_estado(Estado.EJECUTANDO)
		ruta_datos = Path(self.ruta_datos) if self.ruta_datos else paths.ruta_datos()
		try:
			if self.inmediata:
				self.resultado = restaurar.restaurar_ahora(self.ruta, self.plan, ruta_datos=ruta_datos,
					secretos=self._secretos, usar_secretos=False)
			else:
				descripcion = formato.leer_manifiesto(self.ruta).descripcion or self.ruta.stem
				self.info_pendiente = pendiente.preparar_pendiente(self.ruta, self.plan, self._secretos, ruta_datos,
					descripcion)
				self.resultado = pendiente.ResultadoRestauracion(True, _("La restauración se aplicará al reiniciar zCommander."),
					list(self.plan.partes), None)
		finally:
			self._secretos = None
		if not self.resultado.ok:
			self.anotar_error(str(self.ruta), self.resultado.mensaje)

	def resumen(self) -> str:
		if self.resultado is not None:
			return self.resultado.mensaje
		return super().resumen()
