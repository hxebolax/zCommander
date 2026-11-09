# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Reproductor multimedia (zc.reproductor, diseño 2.0, 11.1).

Reproduce audio (y el sonido de los vídeos) del cursor, de los marcados, de una
carpeta o de una lista M3U mientras se sigue navegando. Motor de Windows
(``wx.media.MediaCtrl``) y, para lo que Windows no abre, ``ffplay`` del
componente FFmpeg. Recuerda dónde se dejó cada archivo largo.

``activar`` solo registra funciones: el motor y la ventana se crean la primera
vez que hacen falta.
"""

from __future__ import annotations

import builtins
import json
import logging
import os
import threading
import time
from typing import Any

from app.plugins import api

from . import control, listas, tiempos
from .memoria import Memoria

log = logging.getLogger(__name__)

ORDENES = ("reproducir", "ventana", "pausa", "detener", "retroceder", "avanzar", "posicion", "siguiente", "anterior",
	"anadir_cola", "guardar_lista", "temporizador")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.reproductor: control.Reproductor | None = None
		self._ventana: Any = None
		self._destruir_oculta: Any = None
		for id_corto in ORDENES:
			zc.ordenes.manejador(id_corto, getattr(self, f"_orden_{id_corto}"))

	def desactivar(self) -> None:
		if self.reproductor is not None:
			self.reproductor.cerrar()
			self.reproductor = None
		if self._destruir_oculta is not None:
			self._destruir_oculta()
			self._destruir_oculta = None

	# ── Configuración y motores ──────────────────────────────────────────────

	def _config(self, clave: str) -> Any:
		return self.zc.config.obtener(clave, None)

	def saltos(self) -> tuple[int, int, int]:
		return (int(self._config("salto_corto_s") or 5), int(self._config("salto_medio_s") or 30),
			int(self._config("salto_largo_s") or 300))

	def _al_cambiar_config(self, clave: str, _anterior: Any, nuevo: Any) -> None:
		if self.reproductor is None:
			return
		if clave == "volumen" and nuevo is not None and int(nuevo) != self.reproductor.volumen:
			self.reproductor.fijar_volumen(int(nuevo), guardar=False)
		elif clave == "velocidad" and nuevo is not None and abs(float(nuevo) - self.reproductor.velocidad) > 0.001:
			self.reproductor.fijar_velocidad(float(nuevo))

	def _ffplay_disponible(self) -> bool:
		return self.zc.componentes.disponible("ffmpeg")

	def _fabrica_motor(self, tipo: str) -> Any:
		from . import motores

		if tipo == "ffplay":
			return motores.MotorFfplay(
				lambda: str(self.zc.componentes.ejecutable("ffmpeg", "ffplay.exe")), self.zc.ejecutar_programa,
				self._duracion_ffprobe, _planificar)
		control_real, enganchar, destruir = motores.crear_control()
		motor = motores.MotorWindows(control_real, _planificar_tarde)
		enganchar(motor)
		self._destruir_oculta = destruir
		return motor

	def _duracion_ffprobe(self, ruta: str) -> float:
		"""[trabajo] Duración con ``ffprobe`` (para FFplay, que no la dice)."""
		ffprobe = str(self.zc.componentes.ejecutable("ffmpeg", "ffprobe.exe"))
		resultado = self.zc.ejecutar_programa([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", ruta],
			tiempo_s=30)
		datos = json.loads(resultado.salida.decode("utf-8", errors="replace") or "{}")
		return float(datos.get("format", {}).get("duration") or 0)

	def _titulos(self, ruta: str, al_llegar: Any) -> None:
		"""Título y duración de las etiquetas (``zc.metadatos``, si está), en un hilo."""

		def trabajo() -> None:
			metadatos = self.zc.complemento("zc.metadatos")
			if metadatos is None or not hasattr(metadatos, "leer_etiquetas"):
				return
			try:
				etiquetas = metadatos.leer_etiquetas(None, ruta) or {}
			except Exception:  # noqa: BLE001 - sin etiquetas se usa el nombre del archivo
				log.debug("No se pudieron leer las etiquetas de %s", ruta, exc_info=True)
				return
			titulo = etiquetas.get("titulo", "")
			if titulo and etiquetas.get("artista"):
				titulo = f"{etiquetas['artista']} - {titulo}"
			try:
				duracion = float(etiquetas.get("duracion_s") or 0)
			except ValueError:
				duracion = 0.0
			if titulo or duracion:
				_planificar(lambda: al_llegar(titulo, duracion))

		threading.Thread(target=trabajo, name="zc-reproductor-etiquetas", daemon=True).start()

	def obtener_reproductor(self) -> control.Reproductor:
		if self.reproductor is None:
			# La configuración se abre aquí y no en activar(): activar no escribe nada en data.
			self.zc.config.suscribir(self._al_cambiar_config)
			self.reproductor = control.Reproductor(
				config=self._config, anunciar=self.zc.anunciar, sonar=self.zc.sonidos.sonar, memoria=Memoria(self.zc.datos),
				fabrica_motor=self._fabrica_motor, ffplay_disponible=self._ffplay_disponible,
				planificar_tarde=_planificar_tarde, titulos=self._titulos, guardar_config=self.zc.config.establecer)
		return self.reproductor

	# ── Qué reproducir ───────────────────────────────────────────────────────

	def _rutas_del_contexto(self, ctx: api.ContextoComplemento, anadir: bool) -> None:
		"""Reúne en un hilo lo que hay que reproducir (cursor, marcados, carpeta o lista) y lo entrega a la interfaz."""
		argumento = ctx.argumento if isinstance(ctx.argumento, str) and ctx.argumento.strip() else ""
		panel = ctx.objetivo
		proveedor = panel.proveedor
		entradas = [] if argumento else (panel.marcadas() or ([panel.cursor()] if panel.cursor() is not None else []))
		carpeta_panel = "" if argumento else panel.ruta

		def trabajo() -> None:
			try:
				rutas = self._reunir(proveedor, argumento, entradas, carpeta_panel)
			except api.ErrorArchivos as error:
				self.zc.anunciar(str(error), api.ESENCIAL)
				return
			except OSError as error:
				self.zc.anunciar(_("No se pudo leer: {e}").format(e=error.strerror or error), api.ESENCIAL)
				return
			_planificar(lambda: self._entregar(rutas, anadir))

		threading.Thread(target=trabajo, name="zc-reproductor-reunir", daemon=True).start()

	def _local(self, proveedor: Any, ruta: str) -> str:
		local = proveedor.ruta_local(ruta) if proveedor is not None else ruta
		return local or proveedor.extraer_temporal(ruta)

	def _reunir(self, proveedor: Any, argumento: str, entradas: list[Any], carpeta_panel: str) -> list[str]:
		if argumento:
			return self._de_ruta_local(argumento)
		if not entradas:
			local = proveedor.ruta_local(carpeta_panel) if carpeta_panel else None
			return self._de_carpeta(local) if local else []
		rutas: list[str] = []
		for entrada in entradas:
			if entrada.es_carpeta:
				local = proveedor.ruta_local(entrada.ruta)
				if local:
					rutas.extend(self._de_carpeta(local))
			elif listas.es_lista(entrada.nombre):
				rutas.extend(self._de_ruta_local(self._local(proveedor, entrada.ruta)))
			elif control.es_multimedia(entrada.nombre):
				rutas.append(self._local(proveedor, entrada.ruta))
		return rutas

	def _de_ruta_local(self, ruta: str) -> list[str]:
		if os.path.isdir(ruta):
			return self._de_carpeta(ruta)
		if listas.es_lista(ruta):
			return [e.ruta for e in listas.leer(ruta)]
		return [ruta] if control.es_multimedia(ruta) else []

	@staticmethod
	def _de_carpeta(carpeta: str) -> list[str]:
		with os.scandir(carpeta) as elementos:
			archivos = [e.path for e in elementos if e.is_file() and control.es_multimedia(e.name)]
		return sorted(archivos, key=lambda r: os.path.basename(r).casefold())

	def _entregar(self, rutas: list[str], anadir: bool) -> None:
		if not rutas:
			self.zc.anunciar(_("No hay nada que reproducir aquí"), api.RESULTADO)
			return
		reproductor = self.obtener_reproductor()
		if anadir and reproductor.cola:
			cuantas = reproductor.anadir(rutas)
			self.zc.anunciar(_("{n} pistas añadidas a la cola").format(n=cuantas) if cuantas != 1
				else _("1 pista añadida a la cola"), api.RESULTADO)
			return
		reproductor.reproducir_lista(rutas)

	def abrir_lista(self, ruta: str) -> None:
		try:
			rutas = [e.ruta for e in listas.leer(ruta)]
		except OSError as error:
			self.zc.anunciar(_("No se pudo leer la lista: {e}").format(e=error.strerror or error), api.ESENCIAL)
			return
		self._entregar(rutas, False)

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def _orden_reproducir(self, ctx: api.ContextoComplemento) -> None:
		self._rutas_del_contexto(ctx, anadir=False)

	def _orden_anadir_cola(self, ctx: api.ContextoComplemento) -> None:
		self._rutas_del_contexto(ctx, anadir=True)

	def _orden_ventana(self, ctx: api.ContextoComplemento) -> None:
		if self._ventana is not None and self._ventana.marco:
			self._ventana.marco.Raise()
			self._ventana.lista.SetFocus()
			return
		from .ventana import VentanaReproductor

		self._ventana = VentanaReproductor(self.zc.ui, None, self.obtener_reproductor(), self)
		self._ventana.marco.Show()
		self._ventana.lista.SetFocus()

	def ventana_cerrada(self, ventana: Any) -> None:
		if self._ventana is ventana:
			self._ventana = None

	def _orden_pausa(self, ctx: api.ContextoComplemento) -> None:
		self.obtener_reproductor().pausa_continuar()

	def _orden_detener(self, ctx: api.ContextoComplemento) -> None:
		self.obtener_reproductor().detener()

	def _orden_retroceder(self, ctx: api.ContextoComplemento) -> None:
		self.obtener_reproductor().saltar(-self.saltos()[0])

	def _orden_avanzar(self, ctx: api.ContextoComplemento) -> None:
		self.obtener_reproductor().saltar(self.saltos()[0])

	def _orden_posicion(self, ctx: api.ContextoComplemento) -> None:
		ctx.anunciar(self.obtener_reproductor().texto_posicion(), api.RESULTADO)

	def _orden_siguiente(self, ctx: api.ContextoComplemento) -> None:
		self.obtener_reproductor().siguiente()

	def _orden_anterior(self, ctx: api.ContextoComplemento) -> None:
		self.obtener_reproductor().anterior()

	def _orden_guardar_lista(self, ctx: api.ContextoComplemento) -> None:
		self.guardar_cola(None)

	def _orden_temporizador(self, ctx: api.ContextoComplemento) -> None:
		self.pedir_temporizador(None)

	# ── Diálogos ─────────────────────────────────────────────────────────────

	def guardar_cola(self, padre: Any) -> None:
		import wx

		from .ventana import ruta_lista_por_defecto

		reproductor = self.obtener_reproductor()
		if not reproductor.cola:
			self.zc.anunciar(_("La cola está vacía: no hay nada que guardar"), api.RESULTADO)
			return
		inicial = ruta_lista_por_defecto(reproductor.cola)
		dialogo = wx.FileDialog(padre, _("Guardar la cola como M3U"), defaultDir=os.path.dirname(inicial),
			defaultFile=os.path.basename(inicial), wildcard=_("Lista M3U8 (*.m3u8)|*.m3u8|Lista M3U (*.m3u)|*.m3u"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			ruta = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		entradas = [listas.EntradaLista(p.ruta, p.nombre, p.duracion if p.duracion > 0 else -1) for p in reproductor.cola]
		try:
			listas.guardar(ruta, entradas)
		except OSError as error:
			self.zc.ui.mostrar_error(_("No se pudo guardar la lista: {e}").format(e=error.strerror or error), _("Guardar la cola"))
			return
		self.zc.anunciar(_("Cola guardada en {n}").format(n=os.path.basename(ruta)), api.RESULTADO)

	def pedir_temporizador(self, padre: Any) -> None:
		reproductor = self.obtener_reproductor()
		texto = self.zc.ui.pedir_texto(_("&Minutos hasta detener la reproducción (0 lo quita):"), _("Temporizador de apagado"),
			"30", padre=padre)
		if texto is None:
			return
		try:
			minutos = float(texto.strip().replace(",", "."))
			if minutos < 0 or minutos > 24 * 60:
				raise ValueError
		except ValueError:
			self.zc.ui.mostrar_error(_("Escriba un número de minutos entre 0 y 1440."), _("Temporizador de apagado"), padre=padre)
			return
		reproductor.fijar_temporizador(minutos, time.time())

	def pedir_ir_a(self, padre: Any) -> None:
		reproductor = self.obtener_reproductor()
		if reproductor.pista is None:
			self.zc.anunciar(_("No se está reproduciendo nada"), api.RESULTADO)
			return
		texto = self.zc.ui.pedir_texto(_("&Tiempo (1:23:00) o porcentaje (50 %):"), _("Ir a un tiempo"),
			tiempos.formatear(reproductor.posicion()), padre=padre)
		if texto is None:
			return
		try:
			destino = tiempos.interpretar_destino(texto, reproductor.duracion())
		except ValueError as error:
			self.zc.ui.mostrar_error(str(error), _("Ir a un tiempo"), padre=padre)
			return
		reproductor.ir_a(destino)

	def pedir_marcador(self, padre: Any) -> None:
		reproductor = self.obtener_reproductor()
		if reproductor.pista is None:
			self.zc.anunciar(_("No se está reproduciendo nada"), api.RESULTADO)
			return
		nombre = self.zc.ui.pedir_texto(_("&Nombre del marcador:"), _("Añadir marcador"),
			tiempos.formatear(reproductor.posicion()), padre=padre)
		if nombre is not None:
			reproductor.anadir_marcador(nombre)

	def elegir_marcador(self, padre: Any) -> None:
		import wx

		from .dialogos import DialogoMarcadores

		reproductor = self.obtener_reproductor()
		pista = reproductor.pista
		if pista is None:
			self.zc.anunciar(_("No se está reproduciendo nada"), api.RESULTADO)
			return
		marcadores = reproductor.marcadores()
		if not marcadores:
			self.zc.anunciar(_("Esta pista no tiene marcadores"), api.RESULTADO)
			return
		dialogo = DialogoMarcadores(self.zc.ui, padre, pista.nombre, marcadores,
			lambda indice: reproductor.memoria.quitar_marcador(pista.ruta, indice))
		try:
			resultado = self.zc.ui.mostrar_modal(dialogo.dialogo)
		finally:
			dialogo.dialogo.Destroy()
		if resultado == wx.ID_OK and dialogo.elegido is not None:
			reproductor.ir_a(dialogo.elegido)

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""La ventana del reproductor y la lista de marcadores, sin mostrarlas (3.12)."""
		from .dialogos import DialogoMarcadores
		from .ventana import VentanaReproductor

		try:
			ui = self.zc.ui
			ui.VentanaComplemento  # noqa: B018 - comprueba que hay interfaz
		except api.NoAdmitido:
			log.info("Sin interfaz de zCommander no se pueden construir las ventanas del reproductor")
			return []
		reproductor = self.obtener_reproductor()
		ventana = VentanaReproductor(ui, padre, reproductor, self)
		marcadores = DialogoMarcadores(ui, padre, "Prueba", [("Inicio", 0.0), ("Capítulo 2", 754.0)], lambda _i: None)
		return [ventana.marco, marcadores.dialogo]


def _planificar(funcion: Any) -> None:
	import wx

	wx.CallAfter(funcion)


def _planificar_tarde(segundos: float, funcion: Any) -> Any:
	import wx

	return wx.CallLater(max(1, int(segundos * 1000)), funcion)
