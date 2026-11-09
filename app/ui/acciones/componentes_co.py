# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes y enganche de arranque del bloque CO: actualizador de componentes (diseño 2.0, 6 y 14.9).

- ``componentes``: Opciones → «Componentes externos...». Abre el diálogo, que
  busca, actualiza, vuelve atrás y restaura con las tareas y el motor de
  operaciones de la ventana.
- ``instalar(ventana)``: registra el servicio ``componentes`` (14.9), suma la
  comprobación periódica a la del actualizador (``registrar_comprobacion``,
  5.4; cada ``actualizaciones.componentes_intervalo_dias``), lanza en un hilo la
  comprobación de integridad (6.8) y pide los sonidos que dejó el arranque
  (``comp.revertido``, ``comp.actualizado``: paso 11 de 14.8).
"""

from __future__ import annotations

import builtins
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.services.componentes import estado
from app.ui import anuncios

log = logging.getLogger(__name__)

#: Los avisos de daños se dan una vez, tras los del arranque (paso 11 de 14.8).
RETRASO_AVISOS_MS = 2500


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ServicioComponentes:
	"""El servicio ``componentes`` de la ventana (14.9): las funciones de ``estado`` (3.7) y ``estado_de``."""

	def ruta(self, id: str) -> Path:
		return estado.ruta(id)

	def ejecutable(self, id: str, nombre: str) -> Path:
		return estado.ejecutable(id, nombre)

	def disponible(self, id: str) -> bool:
		return estado.disponible(id)

	def registrar_al_detener(self, id: str, funcion: Callable[[], bool]) -> None:
		estado.registrar_al_detener(id, funcion)

	def estado_de(self, id: str) -> str:
		return estado.estado_de(id)


def _en_interfaz_y_esperar(funcion: Callable[[], None], tiempo_s: float = 5.0) -> None:
	"""Ejecuta ``funcion`` en el hilo de la interfaz y espera a que termine (desde el hilo de una operación)."""
	from app.core import tareas

	if tareas.en_hilo_principal():
		funcion()
		return
	hecho = threading.Event()

	def envoltorio() -> None:
		try:
			funcion()
		finally:
			hecho.set()

	tareas.ejecutar_en_interfaz(envoltorio)
	if not hecho.wait(tiempo_s):
		log.warning("La interfaz no respondió a tiempo al sacar los paneles de una carpeta de componentes")


def sacar_paneles(ventana: Any, carpeta: Path) -> None:
	"""Antes de renombrar la carpeta de un componente, ningún panel de zCommander la muestra (6.6, paso 7)."""
	destino = Path(carpeta).parent

	def mover() -> None:
		for panel in ventana.todos_los_paneles():
			try:
				ruta = Path(str(panel.ruta))
				if getattr(panel.proveedor, "esquema", "") in ("", "file", "local") and (ruta == carpeta or carpeta in ruta.parents):
					panel.ir_a(str(destino))
			except Exception:  # noqa: BLE001 - un panel raro no impide actualizar (se reintenta el renombrado)
				log.debug("No se pudo sacar un panel de %s", carpeta, exc_info=True)

	_en_interfaz_y_esperar(mover)


def _en_hilo(ventana: Any) -> Callable:
	def en_hilo(funcion: Callable[[], Any], al_terminar: Callable[[Any], None], al_fallar: Callable[[BaseException], None]) -> None:
		if ventana.tareas.enviar(lambda _tarea: funcion(), al_terminar=al_terminar, al_fallar=al_fallar, nombre="componentes") is None:
			al_fallar(RuntimeError(_("zCommander se está cerrando")))

	return en_hilo


def componentes(ctx) -> None:
	"""Opciones → «Componentes externos...» (6.5)."""
	from app.services.componentes.instalar import GestorComponentes
	from app.ui.dialogos.co_componentes import DialogoComponentes

	ventana = ctx.ventana

	def abrir_carpeta(carpeta: Path) -> None:
		ctx.objetivo.ir_a(str(carpeta))
		ctx.objetivo.enfocar()

	dialogo = DialogoComponentes(
		ventana, GestorComponentes(), en_hilo=_en_hilo(ventana), lanzar_operacion=ventana.lanzar_operacion,
		antes_de_renombrar=lambda carpeta: sacar_paneles(ventana, carpeta), al_abrir_carpeta=abrir_carpeta,
		al_reiniciar=lambda: ctx.ejecutar_orden("reiniciar"))
	try:
		dialogo.ShowModal()
	finally:
		if dialogo:
			dialogo.Destroy()


# ── Comprobación periódica (5.4 y 6.4) ───────────────────────────────────────


def comprobacion_activa(config: Any, entorno: estado.Entorno | None = None, ahora: float | None = None) -> bool:
	"""Si toca comprobar: la casilla activa y pasados ``componentes_intervalo_dias`` desde la última."""
	if not config.obtener("actualizaciones.componentes_comprobar"):
		return False
	dias = max(1, int(config.obtener("actualizaciones.componentes_intervalo_dias") or 7))
	ultima = float(estado.leer_estado(entorno).get("ultima_comprobacion") or 0)
	return (time.time() if ahora is None else ahora) - ultima >= dias * 86400


def comprobacion_periodica(token: Any, gestor: Any = None) -> list:
	"""La que se suma a la pasada del actualizador: nunca descarga; avisa si hay novedades sin omitir."""
	from app.services import actualizador
	from app.services.componentes.instalar import GestorComponentes

	gestor = gestor or GestorComponentes()
	gestor.comprobar(token)
	nuevas = gestor.novedades_sin_omitir()
	if not nuevas:
		return []
	from app.services.sonidos import servicio

	servicio.sonar("comp.disponible")
	if len(nuevas) == 1:
		texto = _("Hay una versión nueva de un componente. Opciones, Componentes externos.")
	else:
		texto = _("Hay versiones nuevas de {n} componentes. Opciones, Componentes externos.").format(n=len(nuevas))
	return [actualizador.Novedad("componentes", texto, True)]


# ── Enganche de arranque ─────────────────────────────────────────────────────


def _comprobar_integridad(ventana: Any) -> None:
	def trabajo(_tarea) -> list[str]:
		return estado.comprobar_integridad()

	def listo(danados: list[str]) -> None:
		if not danados:
			return
		nombres = ", ".join(danados)
		texto = _("Faltan archivos de {l}: Opciones, Componentes externos, Restaurar").format(l=nombres)
		ventana.llamar_mas_tarde(RETRASO_AVISOS_MS, lambda: ventana.anunciar(texto, anuncios.ESENCIAL, sonido="aviso.error"))

	ventana.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda e: log.warning("Comprobación de integridad: %s", e),
		nombre="componentes-integridad")


def instalar(ventana: Any) -> None:
	"""Servicio ``componentes``, comprobación periódica, integridad (6.8) y sonidos del arranque (14.9)."""
	from app.services import actualizador
	from app.services.componentes import integrar

	ventana.registrar_servicio("componentes", ServicioComponentes())
	config = ventana.config
	actualizador.registrar_comprobacion("componentes", comprobacion_periodica, lambda: comprobacion_activa(config))
	_comprobar_integridad(ventana)
	sonidos = integrar.sonidos_pendientes()
	if sonidos:
		from app.services.sonidos import servicio

		ventana.llamar_mas_tarde(RETRASO_AVISOS_MS, lambda: [servicio.sonar(s) for s in sonidos])
