# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Reconocimiento de texto, OCR (zc.ocr, diseño 2.0, 11.3).

Reconoce el texto de imágenes y PDF escaneados con el motor OCR de Windows,
sin Internet: del archivo del cursor al visor, de los marcados a archivos de
texto (operación), de la imagen del portapapeles y de la ventana en primer
plano (para programas inaccesibles; también como tecla global).

Motor: pywinrt vendorizado en ``lib/`` o, si no funciona, ``recursos/ocr.ps1``
con Windows PowerShell; se elige la primera vez que hace falta (en un hilo,
con una imagen de un píxel) y se registra cuál.

Exporta ``reconocer(proveedor, ruta, cancelacion) -> Documento`` (tabla de 11.0).
"""

from __future__ import annotations

import builtins
import os
import threading
import time
from typing import Any

from app.plugins import api

from .servicios import lotes, motor


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self._motor: Any = None
		self._candado = threading.Lock()
		zc.ordenes.manejador("reconocer", self.orden_reconocer)
		zc.ordenes.manejador("lotes", self.orden_lotes)
		zc.ordenes.manejador("portapapeles", self.orden_portapapeles)
		zc.ordenes.manejador("ventana", self.orden_ventana)
		zc.exportar("reconocer", self.reconocer)
		try:
			zc.preferencias.dialogo(self.dialogo_preferencias)
		except api.NoAdmitido:
			zc.registro.debug("Sin interfaz: el diálogo de configuración avanzada se registrará con la ventana")
		zc.config.suscribir(lambda clave, _a, _n: self._olvidar_motor(), prefijo="motor")

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		try:
			ui = self.zc.ui
			ui.crear_campo  # noqa: B018 - sin la ventana de zCommander lanza NoAdmitido
		except api.NoAdmitido:
			self.zc.registro.info("Sin la interfaz de zCommander no se pueden construir los diálogos para revisarlos")
			return []
		from .ui.preferencias import DialogoIdioma

		return [DialogoIdioma(padre, ui, "")]

	# ── Motor ────────────────────────────────────────────────────────────────

	def _olvidar_motor(self) -> None:
		with self._candado:
			self._motor = None

	def _crear_powershell(self) -> motor.MotorPowershell:
		return motor.MotorPowershell(self.zc.carpeta / "recursos" / "ocr.ps1", self.zc.ejecutar_programa)

	def motor(self) -> Any:
		"""[trabajo] El motor elegido (se elige la primera vez, probándolo)."""
		with self._candado:
			if self._motor is None:
				inicio = time.monotonic()
				self._motor = motor.elegir(str(self.zc.config.obtener("motor", "automatico")), self.zc.cache / "prueba",
					self._crear_powershell)
				self.zc.registro.info("Motor OCR: %s (elegido en %.1f s)", self._motor.nombre, time.monotonic() - inicio)
			return self._motor

	def reconocer_ruta(self, ruta_local: str, cancelacion: Any = None) -> motor.Resultado:
		"""[trabajo] Líneas por página de una imagen o un PDF del disco."""
		api.comprobar(cancelacion)
		escala = float(self.zc.config.obtener("escala_pdf", 2.0))
		return self.motor().reconocer(ruta_local, str(self.zc.config.obtener("idioma", "") or ""), escala, cancelacion)

	def reconocer(self, proveedor: api.Proveedor, ruta: str, cancelacion: Any = None) -> api.Documento:
		"""[trabajo] Función exportada: el ``Documento`` del texto reconocido (una sección por página)."""
		nombre = proveedor.nombre(ruta)
		if not es_reconocible(nombre):
			raise motor.ErrorOCR(_("Solo se reconoce el texto de imágenes y PDF"), ruta)
		local = proveedor.ruta_local(ruta) or proveedor.extraer_temporal(ruta)
		resultado = self.reconocer_ruta(local, cancelacion)
		return lotes.documento(os.path.splitext(nombre)[0], resultado, getattr(self._motor, "nombre", ""))

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def _mostrar(self, ctx: api.ContextoComplemento, documento: api.Documento) -> None:
		self.zc.sonidos.sonar("fin")
		lineas = sum(len([l for l in s.texto.splitlines() if l.strip()]) for s in documento.secciones)
		ctx.anunciar(_("Texto reconocido: {n} líneas").format(n=lineas) if lineas else _("No se ha reconocido ningún texto"),
			api.RESULTADO)
		self.zc.ui.mostrar_documento(documento)

	def _fallo(self, ctx: api.ContextoComplemento) -> Any:
		def anunciar(error: BaseException) -> None:
			if type(error).__name__ in ("TareaCancelada", "Cancelado"):
				return
			ctx.anunciar(getattr(error, "mensaje", "") or str(error), api.ESENCIAL)

		return anunciar

	def orden_reconocer(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		cursor = panel.cursor()
		if cursor is None or cursor.es_carpeta or not es_reconocible(cursor.nombre):
			ctx.anunciar(_("Sitúese en una imagen o en un PDF para reconocer su texto"), api.ESENCIAL)
			return
		proveedor = panel.proveedor
		ctx.anunciar(_("Reconociendo el texto de {n}...").format(n=cursor.nombre), api.NORMAL)
		self.zc.tareas.enviar(lambda tarea: self.reconocer(proveedor, cursor.ruta, tarea.token),
			al_terminar=lambda documento: self._mostrar(ctx, documento), al_fallar=self._fallo(ctx), nombre="zc.ocr:reconocer")

	def orden_lotes(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		elementos = [e for e in panel.elementos_trabajo() if not e.es_carpeta and es_reconocible(e.nombre)]
		if not elementos:
			ctx.anunciar(_("Marque imágenes o PDF para reconocer su texto"), api.ESENCIAL)
			return
		rutas = [panel.proveedor.ruta_local(e.ruta) for e in elementos]
		if any(r is None for r in rutas):
			ctx.anunciar(_("Solo se reconocen por lotes archivos del disco; cópielos antes a una carpeta"), api.ESENCIAL)
			return
		carpeta = str(self.zc.config.obtener("carpeta_salida", "") or "")
		if carpeta and not os.path.isdir(carpeta):
			ctx.anunciar(_("La carpeta de salida de las preferencias no existe: {c}").format(c=carpeta), api.ESENCIAL)
			return
		operacion = lotes.OperacionLotes(panel.proveedor, [str(r) for r in rutas], self.reconocer_ruta, carpeta,
			bool(self.zc.config.obtener("sobrescribir", False)))
		self.zc.lanzar(operacion, al_terminar=lambda _op: self.zc.sonidos.sonar("fin"))

	def orden_portapapeles(self, ctx: api.ContextoComplemento) -> None:
		from .servicios import captura

		destino = self.zc.cache / "portapapeles.bmp"
		ctx.anunciar(_("Reconociendo la imagen del portapapeles..."), api.NORMAL)

		def trabajo(tarea: Any) -> api.Documento:
			try:
				captura.imagen_portapapeles(destino)
			except captura.ErrorCaptura as error:
				raise motor.ErrorOCR(str(error)) from error
			try:
				return lotes.documento(_("Imagen del portapapeles"), self.reconocer_ruta(str(destino), tarea.token),
					getattr(self._motor, "nombre", ""))
			finally:
				destino.unlink(missing_ok=True)

		self.zc.tareas.enviar(trabajo, al_terminar=lambda documento: self._mostrar(ctx, documento), al_fallar=self._fallo(ctx),
			nombre="zc.ocr:portapapeles")

	def orden_ventana(self, ctx: api.ContextoComplemento) -> None:
		from .servicios import captura

		hwnd = captura.ventana_primer_plano()
		titulo = captura.titulo_ventana(hwnd) if hwnd else ""
		destino = self.zc.cache / "ventana.bmp"
		ctx.anunciar(_("Reconociendo la ventana {t}...").format(t=titulo) if titulo else _("Reconociendo la ventana..."), api.NORMAL)

		def trabajo(tarea: Any) -> api.Documento:
			try:
				captura.capturar_ventana(hwnd, destino)
			except captura.ErrorCaptura as error:
				raise motor.ErrorOCR(str(error)) from error
			try:
				return lotes.documento(titulo or _("Ventana en primer plano"), self.reconocer_ruta(str(destino), tarea.token),
					getattr(self._motor, "nombre", ""))
			finally:
				destino.unlink(missing_ok=True)

		self.zc.tareas.enviar(trabajo, al_terminar=lambda documento: self._mostrar(ctx, documento), al_fallar=self._fallo(ctx),
			nombre="zc.ocr:ventana")

	# ── Configuración avanzada ───────────────────────────────────────────────

	def dialogo_preferencias(self, padre: Any) -> None:
		"""[interfaz] Elegir el idioma entre los instalados (botón «Abrir la configuración avanzada...»)."""
		from .ui.preferencias import DialogoIdioma

		dialogo = DialogoIdioma(padre, self.zc.ui, str(self.zc.config.obtener("idioma", "") or ""), self.zc.abrir_ayuda)

		def poner(idiomas: list[tuple[str, str]]) -> None:
			if dialogo:
				dialogo.poner_idiomas(idiomas)
				if not idiomas:
					self.zc.anunciar(motor.mensaje_sin_idiomas(), api.ESENCIAL)

		self.zc.tareas.enviar(lambda _t: self.motor().idiomas(), al_terminar=poner, nombre="zc.ocr:idiomas",
			al_fallar=lambda error: self.zc.anunciar(getattr(error, "mensaje", "") or str(error), api.ESENCIAL))
		try:
			if self.zc.ui.mostrar_modal(dialogo) == _id_ok():
				self.zc.config.establecer("idioma", dialogo.elegido())
		finally:
			dialogo.Destroy()


def es_reconocible(nombre: str) -> bool:
	extension = os.path.splitext(nombre)[1].lower().lstrip(".")
	return extension == "pdf" or extension in motor.IMAGENES


def _id_ok() -> int:
	import wx

	return wx.ID_OK
