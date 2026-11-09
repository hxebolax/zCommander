# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""``OperacionRclone``: sincronizar, emparejar, comprobar, deduplicar y vaciar como operaciones del motor (12.6).

Cada orden larga es una operación de zCommander: sale en la ventana de
operaciones con su progreso (de ``core/stats`` del grupo ``zc-<id>``), se
cancela con ``job/stopgroup`` y anuncia su resumen al terminar. rclone no tiene
pausa: estas operaciones no la admiten (cada una es un solo trabajo de rclone).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.plugins import api

if TYPE_CHECKING:
	from .servicio import Nubes

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")


class OperacionRclone(api.Operacion):
	"""Un trabajo de rclone (``sync/sync``, ``sync/bisync``, ``operations/check``...) con progreso y cancelación.

	:param ruta: punto del API remoto.
	:param parametros: sus parámetros (sin ``_async`` ni ``_group``, que pone la operación).
	:param carriles: identidades de volumen («nube:nube:<cuenta>», «local:c:\\»).
	:param al_terminar: ``al_terminar(salida)`` en el hilo de la operación, con el ``output`` de rclone.
	"""

	tipo = "nubes"
	admite_pausa = False

	def __init__(self, nubes: Nubes, descripcion: str, ruta: str, parametros: dict[str, Any], *, carriles: frozenset[str] = frozenset(),
			afectadas: list[tuple[str, str]] | None = None, al_terminar: Callable[[dict], None] | None = None,
			sonido_fin: str = "") -> None:
		super().__init__()
		self._nubes = nubes
		self._descripcion = descripcion
		self.ruta = ruta
		self.parametros = dict(parametros)
		self._carriles = frozenset(carriles)
		self._afectadas = list(afectadas or [])
		self._al_terminar = al_terminar
		self.sonido_fin = sonido_fin
		self.salida: dict[str, Any] = {}
		#: Para ``operations/check``: las diferencias hacen fallar el trabajo, pero su informe es el resultado.
		self.aceptar_diferencias = False

	def descripcion(self) -> str:
		return self._descripcion

	@property
	def carriles(self) -> frozenset[str]:
		return self._carriles

	def rutas_afectadas(self) -> list[tuple[str, str]]:
		return list(self._afectadas)

	def _stats(self, datos: dict[str, Any]) -> None:
		en_curso = datos.get("transferring") or []
		actual = str(en_curso[0].get("name", "")) if en_curso else ""
		self.progresar(bytes_hechos=int(datos.get("bytes", 0) or 0), bytes_total=int(datos.get("totalBytes", 0) or 0),
			archivos_hechos=int(datos.get("transfers", 0) or 0), archivos_total=int(datos.get("totalTransfers", 0) or 0),
			actual=actual)

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		ctx.comprobar()
		from .proveedor import FalloLote

		try:
			self.salida = self._nubes.ejecutar(self.ruta, cancelacion=ctx.token, grupo=f"zc-{self.id}", al_stats=self._stats,
				conservar_salida=self.aceptar_diferencias, **self.parametros)
		except FalloLote as fallo:
			self.salida = dict(fallo.salida)
			if not any(self.salida.get(c) for c in ("combined", "differ", "missingOnSrc", "missingOnDst")):
				raise fallo.error from fallo
		errores_rclone = self.salida.get("error") if isinstance(self.salida.get("error"), list) else []
		for ruta in errores_rclone:
			self.anotar_error(str(ruta), _("rclone no pudo procesar este archivo"))
		if self.sonido_fin:
			self._nubes.zc.sonidos.sonar(self.sonido_fin)
		if self._nubes.reinicio_pendiente:
			mensaje = self._nubes.aplicar_configuracion()
			if mensaje:
				self._nubes.zc.anunciar(mensaje, api.RESULTADO)
		if self._al_terminar is not None:
			try:
				self._al_terminar(self.salida)
			except Exception:  # noqa: BLE001 - el aviso final nunca convierte en fallo un trabajo hecho
				log.warning("Falló el aviso final de %s", self._descripcion, exc_info=True)


def carril(nubes: Nubes, fs: str) -> str:
	"""Identidad de volumen de un ``fs`` de rclone (la misma que ``clave_carril`` daría a su proveedor)."""
	if ":" in fs and len(fs.split(":", 1)[0]) > 1:
		return f"nube:nube:{fs.split(':', 1)[0]}"
	return "local:" + fs[:3].replace("/", "\\").casefold()


def resumen_informe(salida: dict[str, Any]) -> dict[str, list[str]]:
	"""Del informe ``combined`` de rclone, las listas por tipo de cambio (+ copiar, - borrar, * distinto, = igual, ! error)."""
	grupos: dict[str, list[str]] = {"+": [], "-": [], "*": [], "=": [], "!": []}
	for linea in salida.get("combined") or []:
		linea = str(linea)
		if len(linea) > 2 and linea[0] in grupos:
			grupos[linea[0]].append(linea[2:])
	return grupos
