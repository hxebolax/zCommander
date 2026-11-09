# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Programador de tareas (zc.programador, diseño 2.0, 11.24; bloque P5).

- Exporta ``ejecutar_tarea(id, al_terminar)`` [interfaz], a la que llama
  ``app.plugins.cargador.ejecutar_tarea_programada`` cuando llega la orden
  ``tarea`` al buzón de la instancia (``ZCommander.exe --tarea <id>``, 14.8).
  Lanza la operación de la tarea con ``zc.lanzar`` (con sus respuestas
  automáticas: nada se pregunta salvo lo que no tiene respuesta) o ejecuta su
  macro u orden con ``zc.ejecutar_orden_futuro`` esperando su futuro, y llama
  a ``al_terminar`` con 0 (bien), 1 (con errores) o 2 (no se pudo empezar).
- Con «Usar el Programador de tareas de Windows» (por defecto) cada tarea es
  una tarea de Windows (``windows.py``); sin él, un temporizador comprueba cada
  30 s, con zCommander abierto, qué tareas tocan.
- Al activarse (``al_arrancar``) avisa de las ejecuciones que aún no se habían dicho.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from app.plugins import api

EVENTO_COMPROBAR = "comprobar"
INTERVALO_S = 30.0


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		from . import tareas, windows

		self.zc = zc
		self.registro_ejecuciones = tareas.RegistroEjecuciones(zc.datos)
		self.windows = windows.ProgramadorWindows()
		self._parar_reloj: threading.Event | None = None
		zc.ordenes.manejador("tareas", self.dialogo_tareas)
		zc.ordenes.manejador("registro", self.dialogo_registro)
		zc.exportar("ejecutar_tarea", self.ejecutar_tarea)
		self._cancelar = [zc.eventos.suscribir(f"{zc.id}:{EVENTO_COMPROBAR}", lambda **_d: self.comprobar_vencidas()),
			zc.config.suscribir(self._al_cambiar_config)]
		# Lo que pueda preguntar o anunciar, cuando la activación haya terminado (3.4).
		zc.complemento_futuro(zc.id).add_done_callback(lambda _f: self._tras_activar())

	def desactivar(self) -> None:
		self._parar_temporizador()
		for cancelar in getattr(self, "_cancelar", []):
			cancelar()

	# ── Ajustes y datos ──────────────────────────────────────────────────────

	@property
	def usar_windows(self) -> bool:
		return bool(self.zc.config.obtener("usar_windows", True))

	def leer(self):
		from . import tareas

		return tareas.leer_tareas(self.zc.datos)

	def guardar(self, lista) -> None:
		from . import tareas

		tareas.guardar_tareas(self.zc.datos, lista)

	def _al_cambiar_config(self, clave: str, _anterior, _nuevo) -> None:
		if clave != "usar_windows":
			return
		lista, usar = self.leer(), self.usar_windows
		self.zc.tareas.enviar(lambda _t: self.windows.sincronizar(lista, usar), al_terminar=self._avisar_problemas,
			al_fallar=lambda error: self.zc.anunciar(str(error), api.ESENCIAL), nombre="programador_sincronizar_windows")
		self._preparar_temporizador()

	def _avisar_problemas(self, problemas: list[str]) -> None:
		if problemas:
			self.zc.anunciar("Problemas con el Programador de tareas de Windows: " + "; ".join(problemas), api.ESENCIAL)

	def guardar_tarea(self, tarea, al_terminar: Callable[[str], None] | None = None) -> None:
		"""Guarda (o sustituye) una tarea y la registra en Windows en un hilo."""
		lista = [t for t in self.leer() if t.id != tarea.id]
		lista.append(tarea)
		self.guardar(lista)
		self._preparar_temporizador()
		if self.usar_windows:
			self.zc.tareas.enviar(lambda _t: self.windows.registrar(tarea),
				al_terminar=lambda _r: al_terminar("") if al_terminar else None,
				al_fallar=lambda error: self._fallo_windows(error, al_terminar), nombre="programador_registrar")
		elif al_terminar is not None:
			al_terminar("")

	def borrar_tarea(self, tarea) -> None:
		self.guardar([t for t in self.leer() if t.id != tarea.id])
		self._preparar_temporizador()
		self.zc.tareas.enviar(lambda _t: self.windows.borrar(tarea), al_fallar=lambda error: self._fallo_windows(error, None),
			nombre="programador_borrar")

	def _fallo_windows(self, error: BaseException, al_terminar: Callable[[str], None] | None) -> None:
		texto = str(error)
		self.zc.anunciar(texto, api.ESENCIAL)
		if al_terminar is not None:
			al_terminar(texto)

	# ── Al activarse y temporizador propio ───────────────────────────────────

	def _tras_activar(self) -> None:
		sin_ver = self.registro_ejecuciones.sin_ver()
		if sin_ver:
			con_errores = sum(1 for e in sin_ver if e.codigo != 0)
			texto = (f"Tareas programadas ejecutadas desde la última vez: {len(sin_ver)}"
				+ (f", {con_errores} con errores" if con_errores else ", todas bien")
				+ ". Detalles en Registro de ejecuciones.")
			self.zc.sonidos.sonar("tarea_fin")
			self.zc.anunciar(texto, api.ESENCIAL if con_errores else api.RESULTADO)
			self.registro_ejecuciones.marcar_vistas()
		self._preparar_temporizador()
		if not self.usar_windows:
			from . import tareas

			for tarea in self.leer():
				if tarea.activa and tarea.frecuencia == tareas.AL_INICIAR_SESION:
					self.ejecutar_tarea(tarea.id, lambda _codigo: None)

	def _preparar_temporizador(self) -> None:
		"""Sin el Programador de Windows y con tareas activas, comprueba cada 30 s qué toca."""
		self._parar_temporizador()
		if self.usar_windows or not any(t.activa for t in self.leer()):
			return
		parar = self._parar_reloj = threading.Event()

		def latir() -> None:
			while not parar.wait(INTERVALO_S):
				self.zc.eventos.emitir(EVENTO_COMPROBAR)

		threading.Thread(target=latir, name="zc-programador-reloj", daemon=True).start()

	def _parar_temporizador(self) -> None:
		if self._parar_reloj is not None:
			self._parar_reloj.set()
			self._parar_reloj = None

	def comprobar_vencidas(self, ahora: float | None = None) -> list[str]:
		"""[interfaz] Ejecuta las tareas que tocan (solo sin el Programador de Windows). Devuelve sus ids."""
		from . import tareas

		if self.usar_windows:
			return []
		ahora = time.time() if ahora is None else ahora
		lanzadas = []
		for tarea in self.leer():
			if tareas.vence(tarea, ahora):
				lanzadas.append(tarea.id)
				self.ejecutar_tarea(tarea.id, lambda _codigo: None)
		return lanzadas

	# ── Ejecutar una tarea (contrato 11.0) ───────────────────────────────────

	def ejecutar_tarea(self, id_tarea: str, al_terminar: Callable[[int], None]) -> None:
		"""[interfaz] Lanza la tarea ``id_tarea`` y llama a ``al_terminar`` con 0, 1 o 2 al acabar."""
		from . import tareas

		tarea = tareas.buscar(self.leer(), id_tarea)
		if tarea is None:
			self.zc.registro.warning("La tarea programada %s no existe", id_tarea)
			self.zc.anunciar(f"La tarea programada {id_tarea} ya no existe", api.ESENCIAL)
			al_terminar(tareas.NO_EMPEZO)
			return
		ejecucion = tareas.Ejecucion(tarea.id, tarea.nombre, time.time())
		registro = logging.getLogger(f"zcplugins.{self.zc.id}.tarea.{tarea.id}")
		registro.setLevel(logging.INFO)
		captura = tareas.CapturaDecisiones(ejecucion)
		registro.addHandler(captura)
		self.registro_ejecuciones.apuntar(ejecucion)
		hecho = {"ya": False}

		def terminar(codigo: int, resumen: str) -> None:
			if hecho["ya"]:
				return
			hecho["ya"] = True
			registro.removeHandler(captura)
			ejecucion.fin, ejecucion.codigo, ejecucion.resumen = time.time(), codigo, resumen
			self.registro_ejecuciones.apuntar(ejecucion)
			self._apuntar_en_tarea(tarea.id, ejecucion)
			self._avisar(tarea, ejecucion)
			try:
				al_terminar(codigo)
			except Exception:  # noqa: BLE001 - quien espera el resultado no tumba al programador
				self.zc.registro.exception("Falló al_terminar de la tarea %s", tarea.id)

		try:
			self._lanzar_segun_tipo(tarea, registro, terminar)
		except Exception as error:  # noqa: BLE001 - cualquier fallo al empezar es «no se pudo empezar»
			self.zc.registro.exception("No se pudo empezar la tarea %s", tarea.id)
			terminar(tareas.NO_EMPEZO, f"No se pudo empezar: {error}")

	def _apuntar_en_tarea(self, id_tarea: str, ejecucion) -> None:
		lista = self.leer()
		for tarea in lista:
			if tarea.id == id_tarea:
				tarea.ultima, tarea.resultado = ejecucion.inicio, ejecucion.codigo
		self.guardar(lista)

	def _avisar(self, tarea, ejecucion) -> None:
		texto = f"Tarea programada {tarea.nombre}: {ejecucion.resumen or ejecucion.texto()}"
		self.zc.sonidos.sonar("tarea_fin")
		self.zc.anunciar(texto, api.RESULTADO if ejecucion.codigo == 0 else api.ESENCIAL)
		if self.zc.config.obtener("notificaciones", True):
			self._notificar(f"zCommander: {tarea.nombre}", f"{ejecucion.texto()}. {ejecucion.resumen}")

	def _notificar(self, titulo: str, texto: str) -> None:
		"""Notificación de Windows (solo con la interfaz; sin ella se queda en el registro)."""
		try:
			import wx
			import wx.adv

			if wx.GetApp() is None or not wx.IsMainThread():
				return
			wx.adv.NotificationMessage(titulo, texto).Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)
		except Exception:  # noqa: BLE001 - una notificación que no sale no es un error de la tarea
			self.zc.registro.debug("No se pudo mostrar la notificación", exc_info=True)

	def _lanzar_segun_tipo(self, tarea, registro: logging.Logger, terminar: Callable[[int, str], None]) -> None:
		from . import tareas

		if tarea.tipo in (tareas.MACRO, tareas.MENU_USUARIO, tareas.ORDEN):
			if tarea.tipo == tareas.MACRO:
				orden, argumento = f"macro:{tarea.objetivo}", None
			elif tarea.tipo == tareas.MENU_USUARIO:
				orden, argumento = "menu_usuario", tarea.objetivo
			else:
				orden, argumento = tarea.objetivo, tarea.destino or None
			self._ejecutar_orden(orden, argumento, terminar)
			return
		if tarea.tipo in (tareas.SINCRONIZACION, tareas.REGLAS):
			dependencia = "zc.sincronizacion" if tarea.tipo == tareas.SINCRONIZACION else "zc.monitor"
			nombres = {"zc.sincronizacion": "Sincronización avanzada y copias", "zc.monitor": "Monitor de carpetas"}

			def continuar(futuro) -> None:
				try:
					exportado = futuro.result()
				except Exception:  # noqa: BLE001 - cancelado o con error: igual que si faltara
					exportado = None
				if exportado is None:
					terminar(tareas.NO_EMPEZO, f"Falta el complemento {nombres[dependencia]} o está inhabilitado")
					return
				try:
					if tarea.tipo == tareas.SINCRONIZACION:
						operacion = exportado.operacion_de_tarea(tarea.objetivo)
					else:
						operacion = exportado.operacion_de_reglas(tarea.objetivo)
				except api.ErrorArchivos as error:
					terminar(tareas.NO_EMPEZO, str(error))
					return
				self._lanzar(operacion, tarea, registro, terminar)

			self.zc.complemento_futuro(dependencia).add_done_callback(continuar)
			return
		if tarea.tipo == tareas.LIMPIEZA:
			self._lanzar(tareas.OperacionLimpieza(tarea.objetivo, tarea.dias, self.zc.vfs.resolver), tarea, registro, terminar)
			return
		self.zc.tareas.enviar(lambda _t: self._operacion_copia(tarea),
			al_terminar=lambda operacion: self._lanzar(operacion, tarea, registro, terminar),
			al_fallar=lambda error: terminar(tareas.NO_EMPEZO, f"No se pudo preparar la copia: {error}"),
			nombre="programador_preparar_copia")

	def _ejecutar_orden(self, orden: str, argumento, terminar: Callable[[int, str], None]) -> None:
		from . import tareas

		futuro = self.zc.ejecutar_orden_futuro(orden, argumento=argumento)

		def listo(f) -> None:
			try:
				ok = bool(f.result())
			except Exception:  # noqa: BLE001 - la orden falló o se descartó
				ok = False
			terminar(tareas.BIEN if ok else tareas.CON_ERRORES, f"{orden}: " + ("ejecutada" if ok else "no se pudo ejecutar"))

		futuro.add_done_callback(listo)

	def _operacion_copia(self, tarea) -> api.Operacion:
		"""[hilo] La copia de la tarea: abre origen y destino sin panel y prepara ``OperacionCopiar``."""
		limpio = tarea.objetivo.rstrip("\\/")
		separador = max(limpio.rfind("\\"), limpio.rfind("/"))
		if separador <= 0 or limpio.endswith(":"):
			raise api.NombreNoValido(f"No se puede copiar «{tarea.objetivo}»: escriba la ruta de una carpeta o un archivo")
		carpeta, nombre = limpio[:separador + 1], limpio[separador + 1:]
		proveedor, ruta = self.zc.vfs.resolver(carpeta)
		entrada = next((e for e in proveedor.listar(ruta) if not e.es_superior and e.nombre.casefold() == nombre.casefold()), None)
		if entrada is None:
			raise api.NoEncontrado(f"No existe {tarea.objetivo}")
		destino, ruta_destino = self.zc.vfs.resolver(tarea.destino)
		try:
			politica = api.Politica(tarea.conflicto)
		except ValueError:
			politica = api.Politica.OMITIR
		operacion = api.OperacionCopiar(proveedor, [entrada], destino, ruta_destino, api.OpcionesCopia(politica=politica))
		operacion.proveedores_de_tarea = [proveedor, destino]
		return operacion

	def _lanzar(self, operacion: api.Operacion, tarea, registro: logging.Logger, terminar: Callable[[int, str], None]) -> None:
		from . import tareas

		operacion.respuestas_automaticas = tareas.respuestas_automaticas(tarea, registro)

		def al_acabar(terminada: api.Operacion) -> None:
			for proveedor in getattr(terminada, "proveedores_de_tarea", []):
				if proveedor.esquema != "local":
					proveedor.cerrar()
			terminar(tareas.codigo_de(terminada), terminada.resumen())

		self.zc.lanzar(operacion, en_cola=True, al_terminar=al_acabar)

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def dialogo_tareas(self, ctx: api.ContextoComplemento) -> None:
		from . import ventana

		propuesta = ctx.activo.mostrar_ruta() if ctx.activo.proveedor.esquema == "local" else ""
		dialogo = ventana.DialogoTareas(self, None, propuesta=propuesta)
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()

	def dialogo_registro(self, ctx: api.ContextoComplemento) -> None:
		from . import ventana

		dialogo = ventana.DialogoRegistro(self, None)
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()
		self.registro_ejecuciones.marcar_vistas()

	def ventanas_para_revisar(self, padre):
		from . import tareas, ventana

		try:
			return [ventana.DialogoTareas(self, padre), ventana.DialogoTarea(self.zc, padre, tareas.Tarea("Ejemplo")),
				ventana.DialogoRegistro(self, padre)]
		except api.NoAdmitido:
			return []
