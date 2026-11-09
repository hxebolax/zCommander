# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Archivos en uso y procesos (``zc.procesos``, diseño 2.0, 11.9; bloque P4).

- «¿Quién usa este archivo?» sobre los elementos de trabajo (Restart Manager).
- Acciones de error del motor para los archivos en uso (códigos 32 y 33, que
  el manifiesto declara para que los botones salgan sin activar el
  complemento): «Ver qué programa lo usa» y «Cerrar ese programa y
  reintentar», con confirmación y nunca sobre procesos del sistema ni sobre
  zCommander.
- Ventana «Procesos» con la lista, terminar, prioridad, carpeta y copiar.

``activar`` solo registra funciones: los módulos con wx se importan al usarlos.
"""

from __future__ import annotations

import logging
from typing import Any

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_procesos")

#: ERROR_SHARING_VIOLATION y ERROR_LOCK_VIOLATION: los mismos que declara el manifiesto.
CODIGOS_EN_USO = (32, 33)


def rutas_locales(panel: api.PanelComplemento) -> list[str]:
	"""Rutas de disco de los elementos de trabajo de un panel (las que no son locales se omiten)."""
	rutas = []
	proveedor = panel.proveedor
	for entrada in panel.elementos_trabajo():
		ruta = proveedor.ruta_local(entrada.ruta) if proveedor is not None else entrada.ruta
		if ruta:
			rutas.append(ruta)
	return rutas


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		zc.ordenes.manejador("quien_usa", self.quien_usa)
		zc.ordenes.manejador("lista", self.lista)
		zc.errores.accion("ver_quien", self.aplica, self.ver_quien)
		zc.errores.accion("cerrar_reintentar", self.aplica, self.cerrar_reintentar)

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		try:
			self.zc.ui.crear_campo  # noqa: B018 - comprueba que hay interfaz (sin ella, NoAdmitido)
		except api.NoAdmitido:
			return []
		from . import ventana

		return [ventana.crear_ventana(self.zc, cargar=False), ventana.DialogoEspera(padre, _("Cerrando el programa"), "")]

	# ── Órdenes ─────────────────────────────────────────────────────────────

	def quien_usa(self, ctx: api.ContextoComplemento) -> None:
		rutas = rutas_locales(ctx.objetivo)
		if not rutas:
			self.zc.anunciar(_("Elija un archivo o una carpeta del disco"), api.RESULTADO)
			return
		from . import uso

		def consultar(_tarea: Any) -> list[uso.ProcesoUso]:
			return uso.quien_usa(rutas)

		def listo(procesos: list[uso.ProcesoUso]) -> None:
			texto = uso.describir(procesos)
			self.zc.anunciar(texto, api.RESULTADO, completo=texto)

		def fallo(error: BaseException) -> None:
			mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
			self.zc.anunciar(mensaje, api.ESENCIAL)

		self.zc.tareas.enviar(consultar, al_terminar=listo, al_fallar=fallo, nombre="zc.procesos:quien_usa")

	def lista(self, ctx: api.ContextoComplemento) -> None:
		from . import ventana

		ventana.abrir(self.zc)

	# ── Acciones de error (14.6) ────────────────────────────────────────────

	def aplica(self, pregunta: api.PreguntaError) -> bool:
		"""Solo con archivo en uso: decide el código de Windows, nunca el texto del mensaje."""
		return int(getattr(pregunta, "codigo_windows", 0) or 0) in CODIGOS_EN_USO

	def ver_quien(self, pregunta: api.PreguntaError) -> api.AccionError | None:
		from . import uso

		try:
			texto = uso.describir(uso.quien_usa([pregunta.ruta]))
		except api.ErrorArchivos as error:
			texto = error.mensaje
		self.zc.ui.mostrar_mensaje(texto, _("Quién usa {r}").format(r=pregunta.ruta))
		return None

	def cerrar_reintentar(self, pregunta: api.PreguntaError) -> api.AccionError | None:
		"""Cierra con el Restart Manager los programas que usan el archivo (con confirmación) y reintenta."""
		from . import uso, ventana

		titulo = _("Cerrar el programa")
		try:
			procesos = uso.quien_usa([pregunta.ruta])
		except api.ErrorArchivos as error:
			self.zc.ui.mostrar_error(error.mensaje, titulo)
			return None
		if not procesos:
			self.zc.anunciar(_("Ya no lo usa ningún programa; se vuelve a intentar"), api.RESULTADO)
			return api.AccionError.REINTENTAR
		bloqueos = [f"{p.descripcion}: {uso.motivo_para_no_cerrar(p)}" for p in procesos if not uso.se_puede_cerrar(p)]
		if bloqueos:
			self.zc.ui.mostrar_error(_("No se puede cerrar desde zCommander:\n{l}").format(l="\n".join(bloqueos)), titulo)
			return None
		nombres = "; ".join(p.descripcion for p in procesos)
		if not self.zc.ui.confirmar(_("¿Cerrar {p} y volver a intentarlo? Si el programa pregunta, conteste; lo que no guarde se "
				"perderá.").format(p=nombres), titulo, peligroso=True):
			return None
		texto = _("Esperando a que se cierre {p}. Si el programa pregunta si quiere guardar, contéstele.").format(p=nombres)
		try:
			quedan = ventana.esperar(self.zc, None, titulo, texto, lambda: uso.cerrar([pregunta.ruta]))
			if quedan:
				nombres = "; ".join(p.descripcion for p in quedan)
				if not self.zc.ui.confirmar(_("{p} no se ha cerrado. ¿Forzar el cierre? Lo que no haya guardado se perderá.").format(
						p=nombres), titulo, peligroso=True):
					return None
				quedan = ventana.esperar(self.zc, None, titulo, _("Forzando el cierre de {p}.").format(p=nombres),
					lambda: uso.cerrar([pregunta.ruta], forzar=True))
		except api.ErrorArchivos as error:
			self.zc.ui.mostrar_error(error.mensaje, titulo)
			return None
		if quedan:
			self.zc.ui.mostrar_error(uso.describir(quedan), titulo)
			return None
		self.zc.sonidos.sonar("cerrado")
		self.zc.anunciar(_("Programa cerrado; se vuelve a intentar"), api.RESULTADO)
		return api.AccionError.REINTENTAR
