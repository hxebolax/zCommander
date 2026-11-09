# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Historial del portapapeles (``zc.portapapeles``, diseño 2.0, 11.16; bloque P4).

Se activa al arrancar (``al_arrancar``) para escuchar desde el principio con
``AddClipboardFormatListener``. ``activar`` solo arranca el hilo de escucha;
el historial guardado (si ``guardar_entre_sesiones``) se lee en ese hilo.

Respeta la exclusión de los gestores de contraseñas
(``ExcludeClipboardContentFromMonitorProcessing``): eso no se guarda ni se anuncia.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_portapapeles")

#: Segundos que se espera antes de guardar en disco tras un cambio (las copias seguidas se agrupan).
ESPERA_GUARDAR_S = 2.0


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		from . import escucha, historial

		self.zc = zc
		# La configuración se lee en el hilo de arranque: activar() no abre ningún archivo.
		self.historial = historial.Historial()
		self._temporizador: threading.Timer | None = None
		self._candado = threading.Lock()
		zc.ordenes.manejador("historial", self.abrir)
		self._cancelar_cierre = zc.eventos.suscribir("al_cerrar", lambda **_d: self.guardar_ya())
		self.escucha = escucha.Escucha(self._al_copiar)
		threading.Thread(target=self._arrancar, name="zc.portapapeles-arranque", daemon=True).start()

	def _arrancar(self) -> None:
		self.historial.fijar_maximo(self._maximo())
		self.zc.config.suscribir(self._al_cambiar_config)
		if self.zc.config.obtener("guardar_entre_sesiones", False):
			self.historial.cargar(self._archivo())
		if not self.escucha.iniciar():
			self.zc.registro.warning("Sin escucha del portapapeles: %s", self.escucha.error)

	def desactivar(self) -> None:
		self.escucha.detener()
		self.guardar_ya()

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		try:
			self.zc.ui.crear_campo  # noqa: B018 - comprueba que hay interfaz (sin ella, NoAdmitido)
		except api.NoAdmitido:
			return []
		from . import historial, ventana

		datos = historial.Historial()
		datos.anadir(historial.Elemento(historial.TEXTO, texto="Texto de ejemplo"))
		return [ventana.DialogoHistorial(padre, self.zc, datos)]

	# ── Configuración y disco ───────────────────────────────────────────────

	def _maximo(self) -> int:
		return max(5, min(500, int(self.zc.config.obtener("elementos", 50))))

	def _archivo(self) -> Path:
		return self.zc.datos / "historial.json"

	def _al_cambiar_config(self, clave: str, _anterior: Any, nuevo: Any) -> None:
		if clave == "elementos":
			self.historial.fijar_maximo(self._maximo())
			self._programar_guardado()
		elif clave == "guardar_entre_sesiones":
			if nuevo:
				self._programar_guardado()
			else:
				self._borrar_archivo()

	def _borrar_archivo(self) -> None:
		try:
			self._archivo().unlink(missing_ok=True)
		except OSError:
			log.warning("No se pudo borrar el historial guardado", exc_info=True)

	def _programar_guardado(self) -> None:
		if not self.zc.config.obtener("guardar_entre_sesiones", False):
			return
		with self._candado:
			if self._temporizador is not None:
				self._temporizador.cancel()
			self._temporizador = threading.Timer(ESPERA_GUARDAR_S, self.guardar_ya)
			self._temporizador.daemon = True
			self._temporizador.start()

	def guardar_ya(self) -> None:
		with self._candado:
			if self._temporizador is not None:
				self._temporizador.cancel()
				self._temporizador = None
		if not self.zc.config.obtener("guardar_entre_sesiones", False):
			return
		try:
			self.historial.guardar(self._archivo())
		except Exception:  # noqa: BLE001 - guardar el historial nunca debe impedir cerrar
			log.warning("No se pudo guardar el historial del portapapeles", exc_info=True)

	# ── Escucha ─────────────────────────────────────────────────────────────

	def _al_copiar(self, elemento: Any, externo: bool) -> None:
		"""Se llama en el hilo de la escucha con cada copia (ya sin las excluidas)."""
		from . import historial

		self.historial.anadir(elemento)
		self._programar_guardado()
		if externo and self.zc.config.obtener("anunciar_externas", False):
			if elemento.tipo == historial.ARCHIVOS:
				texto = _n("Copiado {n} archivo", "Copiados {n} archivos", len(elemento.archivos)).format(n=len(elemento.archivos))
			else:
				texto = _("Copiado: {t}").format(t=elemento.contenido[:120])
			self.zc.sonidos.sonar("copia_externa")
			self.zc.anunciar(texto, api.NORMAL)

	# ── Orden ───────────────────────────────────────────────────────────────

	def abrir(self, ctx: api.ContextoComplemento) -> None:
		from . import ventana

		if not len(self.historial):
			self.zc.anunciar(_("El historial del portapapeles está vacío"), api.RESULTADO)
			return
		dialogo = ventana.DialogoHistorial(None, self.zc, self.historial)
		try:
			self.zc.ui.mostrar_modal(dialogo)
			pedido = dialogo.pedido
		finally:
			dialogo.Destroy()
		self._programar_guardado()
		if pedido is not None:
			self.ejecutar_pedido(ctx, *pedido)

	def ejecutar_pedido(self, ctx: api.ContextoComplemento, accion: str, elemento: Any) -> None:
		from . import ventana

		if accion == ventana.PEGAR_LINEA:
			self.zc.escribir_en_linea(elemento.como_texto)
		elif accion == ventana.COPIAR:
			self.poner_en_portapapeles(elemento)
			self.zc.anunciar(_("En el portapapeles: {c}").format(c=elemento.contenido[:120]), api.RESULTADO)
		elif accion == ventana.PEGAR_ARCHIVOS:
			self.poner_en_portapapeles(elemento)
			self.zc.ejecutar_orden("portapapeles_pegar", ctx.objetivo.lado or None)
		elif accion == ventana.PEGAR_NUEVO:
			self.pegar_como_archivo_nuevo(ctx.objetivo, elemento.texto)

	def poner_en_portapapeles(self, elemento: Any) -> None:
		"""Vuelve a poner el elemento en el portapapeles [interfaz]."""
		import wx

		from . import historial

		if elemento.tipo == historial.ARCHIVOS:
			datos = wx.FileDataObject()
			for ruta in elemento.archivos:
				datos.AddFile(ruta)
		else:
			datos = wx.TextDataObject(elemento.texto)
		if not wx.TheClipboard.Open():
			raise api.ErrorArchivos(_("Otro programa está usando el portapapeles. Inténtelo de nuevo."))
		try:
			wx.TheClipboard.SetData(datos)
			wx.TheClipboard.Flush()
		finally:
			wx.TheClipboard.Close()

	def pegar_como_archivo_nuevo(self, panel: api.PanelComplemento, texto: str, nombre: str = "nota.txt") -> str:
		"""Crea ``nota.txt`` (o «nota (2).txt»...) con el texto en la carpeta del panel; nunca sobrescribe."""
		proveedor = panel.proveedor
		carpeta = panel.ruta
		final = nombre
		base, _punto, extension = nombre.rpartition(".")
		numero = 1
		while proveedor.existe(proveedor.unir(carpeta, final)):
			numero += 1
			final = f"{base} ({numero}).{extension}"
		ruta = proveedor.unir(carpeta, final)
		datos = texto.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
		try:
			with proveedor.abrir_escritura(ruta, len(datos)) as salida:
				salida.write(datos)
		except api.ErrorArchivos as error:
			self.zc.anunciar(error.mensaje, api.ESENCIAL)
			return ""
		panel.refrescar()
		self.zc.anunciar(_("Creado {n}").format(n=final), api.RESULTADO)
		return ruta
