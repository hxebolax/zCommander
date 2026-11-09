# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sincronización avanzada y copias (zc.sincronizacion, diseño 2.0, 11.12; bloque P5).

- Orden ``perfiles``: diálogo de las tareas con nombre (crear, editar, borrar,
  simular, ejecutar, ejecutar todas, último informe).
- Orden ``ejecutar_todas``: pone en cola todas las tareas guardadas.
- Exporta ``operacion_de_tarea(nombre) -> Operacion`` para el programador (11.24).

Las tareas viven en ``datos/perfiles.json``; la base del último estado de cada
una, en ``datos/<tarea>.db``; su último informe, en ``datos/informes/``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.plugins import api


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self._candado = threading.Lock()
		zc.ordenes.manejador("perfiles", self.perfiles)
		zc.ordenes.manejador("ejecutar_todas", self.ejecutar_todas)
		zc.exportar("operacion_de_tarea", self.operacion_de_tarea)

	# ── Contrato con el programador ──────────────────────────────────────────

	def _ajustes(self):
		from . import motor

		config = self.zc.config
		return motor.Ajustes(tolerancia_s=float(config.obtener("tolerancia_fecha_s", 2)),
			verificar=bool(config.obtener("verificar", False)), dias_versiones=int(config.obtener("dias_versiones", 30)),
			max_versiones_mb=int(config.obtener("max_versiones_mb", 1024)))

	def operacion_de_tarea(self, nombre: str, simular: bool = False) -> api.Operacion:
		"""La operación que ejecuta (o simula) la tarea ``nombre``. ``NoEncontrado`` si no existe."""
		from . import motor

		perfil = motor.buscar_perfil(motor.leer_perfiles(self.zc.datos), nombre)
		if perfil is None:
			raise api.NoEncontrado(f"No hay ninguna tarea de sincronización llamada «{nombre}»")
		return motor.OperacionTareaSincronizacion(perfil, self.zc.datos, self.zc.vfs.resolver, self._ajustes(), simular=simular,
			al_terminar_perfil=self._apuntar_ultima)

	def _apuntar_ultima(self, perfil) -> None:
		"""[hilo de la operación] Guarda la hora y el resultado de la última ejecución en la tarea."""
		from . import motor

		with self._candado:
			perfiles = motor.leer_perfiles(self.zc.datos)
			for guardado in perfiles:
				if guardado.nombre == perfil.nombre:
					guardado.ultima, guardado.resultado = perfil.ultima, perfil.resultado
			motor.guardar_perfiles(self.zc.datos, perfiles)

	# ── Lanzar ───────────────────────────────────────────────────────────────

	def lanzar_tarea(self, nombre: str, al_terminar: Callable[[api.Operacion], None] | None = None, en_cola: bool = False) -> bool:
		try:
			operacion = self.operacion_de_tarea(nombre)
		except api.NoEncontrado as error:
			self.zc.anunciar(str(error), api.ESENCIAL)
			return False
		self.zc.lanzar(operacion, en_cola=en_cola, al_terminar=al_terminar)
		return True

	def lanzar_simulacion(self, nombre: str) -> None:
		try:
			operacion = self.operacion_de_tarea(nombre, simular=True)
		except api.NoEncontrado as error:
			self.zc.anunciar(str(error), api.ESENCIAL)
			return

		def mostrar(terminada: api.Operacion) -> None:
			lineas = terminada.informe.lineas
			try:
				self.zc.ui.mostrar_texto(f"Simulación de {nombre}", "\n".join(lineas) or "No hay nada que sincronizar")
			except api.NoAdmitido:
				self.zc.anunciar(lineas[-1] if lineas else "No hay nada que sincronizar", api.RESULTADO)

		self.zc.lanzar(operacion, al_terminar=mostrar)

	def lanzar_todas(self, al_terminar: Callable[[api.Operacion], None] | None = None) -> int:
		from . import motor

		perfiles = motor.leer_perfiles(self.zc.datos)
		if not perfiles:
			self.zc.anunciar("No hay ninguna tarea de sincronización. Créelas en Tareas de sincronización.", api.RESULTADO)
			return 0
		for perfil in perfiles:
			self.lanzar_tarea(perfil.nombre, al_terminar=al_terminar, en_cola=True)
		self.zc.anunciar(f"En cola {len(perfiles)} tareas de sincronización" if len(perfiles) > 1
			else "En cola 1 tarea de sincronización", api.RESULTADO)
		return len(perfiles)

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def perfiles(self, ctx: api.ContextoComplemento) -> None:
		from . import ventana

		dialogo = ventana.DialogoTareas(self, None, origen=ctx.activo.mostrar_ruta(), destino=ctx.pasivo.mostrar_ruta())
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()

	def ejecutar_todas(self, ctx: api.ContextoComplemento) -> None:
		self.lanzar_todas()

	def ventanas_para_revisar(self, padre):
		from . import motor, ventana

		try:
			return [ventana.DialogoTareas(self, padre), ventana.DialogoPerfil(self.zc, padre, motor.Perfil("", "", ""), [])]
		except api.NoAdmitido:
			return []
