# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Búsqueda instantánea (zc.busqueda_instantanea, diseño 2.0, 11.5; bloque P5).

- Orden ``abrir`` (Ctrl+Mayús+F): ventana con resultados al escribir.
- Proveedor de búsqueda ``instantanea`` para el desplegable «Motor» de Buscar
  archivos (Alt+F7): traduce sus patrones y entrega rutas locales.

``activar`` solo registra funciones: la ventana y los motores (ctypes, COM) se
importan la primera vez que se usan.
"""

from __future__ import annotations

from app.plugins import api


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self._ventana = None
		zc.ordenes.manejador("abrir", self.abrir)
		zc.busqueda.proveedor("instantanea", self.buscar_para_dialogo)

	def desactivar(self) -> None:
		ventana = getattr(self, "_ventana", None)
		if ventana is not None and ventana.marco:
			ventana.marco.Destroy()
		self._ventana = None

	# ── Orden ────────────────────────────────────────────────────────────────

	def abrir(self, ctx: api.ContextoComplemento) -> None:
		"""Abre la ventana (o la trae al frente si ya está abierta) con el foco en «Buscar»."""
		from . import ventana

		actual = self._ventana
		if actual is None or not actual.marco:
			actual = self._ventana = ventana.VentanaBusqueda(self.zc, None)
		actual.mostrar()

	# ── Proveedor de búsqueda del diálogo Buscar archivos ────────────────────

	def buscar_para_dialogo(self, criterios: api.CriteriosBusqueda, entregar, cancelacion) -> None:
		"""[hilo] Busca con los criterios del diálogo y entrega cada ruta con ``entregar``."""
		from . import consulta, motores

		config = self.zc.config
		texto = consulta.desde_patrones(criterios.nombres or "*")
		if not texto and not criterios.texto:
			# Un error aquí contaría como fallo del complemento (3.8): se explica y no se entrega nada.
			self.zc.anunciar("Escriba un nombre o un patrón para buscar con el índice", api.RESULTADO)
			return
		try:
			resultado = motores.buscar(texto, preferencia=str(config.obtener("motor", "automatico")),
				contenido=criterios.texto or "", max_resultados=min(int(criterios.max_resultados),
					int(config.obtener("max_resultados", 1000))),
				incluir_ocultos=bool(criterios.ocultos or config.obtener("incluir_ocultos", False)),
				excluidas=tuple(str(c) for c in config.obtener("carpetas_excluidas", []) or ()), cancelacion=cancelacion)
		except motores.SinMotor as error:
			self.zc.anunciar(str(error), api.RESULTADO)
			return
		for ruta in resultado.rutas:
			api.comprobar(cancelacion)
			entregar(ruta)

	def ventanas_para_revisar(self, padre):
		"""La ventana de búsqueda, sin mostrar, para ``revisar_teclado`` (necesita la interfaz de ``zc.ui``)."""
		from . import ventana

		try:
			return [ventana.VentanaBusqueda(self.zc, padre, comprobar_motores=False).marco]
		except api.NoAdmitido:
			return []
