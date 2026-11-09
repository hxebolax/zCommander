# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proyectos y salto rápido (zc.proyectos, diseño 2.0, 11.15; bloque P5).

Se activa al arrancar (``al_arrancar``) para contar desde el principio cada
cambio de carpeta del bus (``al_cambiar_carpeta``): eso alimenta la
«frecencia» del salto rápido. ``activar`` solo lee ``datos/frecencia.json``
(pequeño) y se suscribe; el guardado va a un hilo cada 20 visitas y al cerrar.
"""

from __future__ import annotations

import time

from app.plugins import api

GUARDAR_CADA = 20


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		from . import datos

		self.zc = zc
		self.frecencia = datos.Frecencia(zc.datos).cargar()
		zc.ordenes.manejador("salto", self.salto)
		zc.ordenes.manejador("proyectos", self.proyectos)
		self._cancelar = [zc.eventos.suscribir("al_cambiar_carpeta", self.al_cambiar_carpeta),
			zc.eventos.suscribir("al_cerrar", lambda **_d: self.guardar())]

	def desactivar(self) -> None:
		for cancelar in getattr(self, "_cancelar", []):
			cancelar()
		self.guardar()

	# ── Frecencia ────────────────────────────────────────────────────────────

	def excluidas(self) -> list[str]:
		return [str(c) for c in self.zc.config.obtener("excluidas", []) or []]

	def al_cambiar_carpeta(self, panel=None, proveedor=None, ruta: str = "", **_datos) -> None:
		"""[interfaz] Cuenta una visita a una carpeta del disco o de la red de Windows (no las de servidores ni nubes)."""
		if not ruta or getattr(proveedor, "esquema", "local") != "local":
			return
		from . import datos

		if datos.excluida(ruta, self.excluidas()):
			return
		self.frecencia.visitar(ruta)
		if self.frecencia.cambios >= GUARDAR_CADA:
			self._guardar_en_hilo()

	def _ajustes(self) -> tuple[float, float, int]:
		config = self.zc.config
		return (float(config.obtener("peso_frecuencia", 1.0)), float(config.obtener("media_vida_dias", 14)),
			int(config.obtener("max_carpetas", 1000)))

	def _guardar_en_hilo(self) -> None:
		peso, media_vida, maximo = self._ajustes()
		self.frecencia.podar(maximo, peso, media_vida)
		instantanea = self.frecencia.instantanea()
		self.frecencia.cambios = 0
		self.zc.tareas.enviar(lambda _tarea: self.frecencia.guardar(instantanea), nombre="proyectos_guardar_frecencia")

	def guardar(self) -> None:
		frecencia = getattr(self, "frecencia", None)
		if frecencia is None or not frecencia.cambios:
			return
		peso, media_vida, maximo = self._ajustes()
		frecencia.podar(maximo, peso, media_vida)
		try:
			frecencia.guardar()
			frecencia.cambios = 0
		except OSError:
			self.zc.registro.warning("No se pudo guardar la frecencia", exc_info=True)

	def proponer(self, texto: str):
		peso, media_vida, _maximo = self._ajustes()
		return self.frecencia.buscar(texto, peso=peso, media_vida_dias=media_vida, excluidas=self.excluidas())

	def olvidar(self, ruta: str) -> bool:
		return self.frecencia.olvidar(ruta)

	def recientes_de_windows(self, cancelacion=None) -> list[str]:
		"""[hilo] Carpetas de los elementos recientes de Windows."""
		from . import recientes

		return recientes.carpetas_recientes(cancelacion=cancelacion)

	# ── Proyectos ────────────────────────────────────────────────────────────

	def guardar_proyecto(self, nombre: str, nota: str, carpetas: list[str]):
		"""Guarda la ventana actual como espacio de trabajo del núcleo y el proyecto con su nota y carpetas."""
		from . import datos

		espacio = nombre
		try:
			self.zc.espacios.guardar_actual(nombre, nota)
		except api.NoAdmitido as error:
			espacio = ""
			self.zc.registro.info("Sin espacios de trabajo: %s", error)
			self.zc.anunciar("Los espacios de trabajo no están disponibles: el proyecto guarda solo la nota y las carpetas",
				api.RESULTADO)
		proyectos = [p for p in datos.leer_proyectos(self.zc.datos) if p.nombre.casefold() != nombre.casefold()]
		proyecto = datos.Proyecto(nombre, nota, [c for c in carpetas if c], espacio, time.time())
		proyectos.append(proyecto)
		datos.guardar_proyectos(self.zc.datos, proyectos)
		self.zc.anunciar(f"Proyecto guardado: {nombre}", api.RESULTADO)
		return proyecto

	def abrir_proyecto(self, proyecto) -> bool:
		"""Abre su espacio de trabajo; sin espacio, lleva el panel a su primera carpeta."""
		if proyecto.espacio:
			try:
				if proyecto.espacio in self.zc.espacios.listar():
					self.zc.espacios.abrir(proyecto.espacio)
					self.zc.anunciar(f"Proyecto abierto: {proyecto.nombre}", api.RESULTADO)
					return True
			except api.NoAdmitido as error:
				self.zc.registro.info("Sin espacios de trabajo: %s", error)
		if proyecto.carpetas:
			self.zc.abrir_ruta(proyecto.carpetas[0])
			self.zc.anunciar(f"Proyecto {proyecto.nombre}: su espacio de trabajo no existe; se abre su primera carpeta",
				api.RESULTADO)
			return True
		self.zc.anunciar(f"El proyecto {proyecto.nombre} no tiene espacio de trabajo ni carpetas", api.RESULTADO)
		return False

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def salto(self, ctx: api.ContextoComplemento) -> None:
		from . import ventana

		dialogo = ventana.DialogoSalto(self, None)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != ventana.wx.ID_OK:
				return
			ruta = dialogo.elegida()
		finally:
			dialogo.Destroy()
		if ruta:
			self.zc.abrir_ruta(ruta, ctx.lado_objetivo)

	def proyectos(self, ctx: api.ContextoComplemento) -> None:
		from . import ventana

		carpetas = [r for r in (ctx.activo.mostrar_ruta(), ctx.pasivo.mostrar_ruta()) if r]
		dialogo = ventana.DialogoProyectos(self, None, carpetas)
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()

	def ventanas_para_revisar(self, padre):
		from . import datos, ventana

		try:
			return [ventana.DialogoSalto(self, padre, recientes_windows=False), ventana.DialogoProyectos(self, padre),
				ventana.DialogoProyecto(self.zc, padre, datos.Proyecto("Ejemplo"))]
		except api.NoAdmitido:
			return []
