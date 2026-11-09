# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ayudas de las pruebas del bloque G: paneles y ventana falsos y copia de seguridad del portapapeles."""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Formatos con identificadores GDI en lugar de memoria global: no se pueden copiar como bytes
# (Windows los vuelve a sintetizar desde CF_DIB y similares).
_FORMATOS_GDI = {2, 3, 9, 14, 0x82, 0x83, 0x8E}


def guardar_portapapeles() -> list[tuple[int, bytes]]:
	"""Copia de cada formato de memoria global del portapapeles, para devolverlo al terminar."""
	import win32clipboard

	from app.services.windows import portapapeles

	kernel32 = ctypes.windll.kernel32
	kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
	kernel32.GlobalLock.restype = ctypes.c_void_p
	kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
	kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
	kernel32.GlobalSize.restype = ctypes.c_size_t
	guardado: list[tuple[int, bytes]] = []
	with portapapeles._abierto():
		formato = 0
		while True:
			formato = win32clipboard.EnumClipboardFormats(formato)
			if not formato:
				break
			if formato in _FORMATOS_GDI:
				continue
			try:
				asa = int(win32clipboard.GetClipboardDataHandle(formato))
				puntero = kernel32.GlobalLock(asa) if asa else None
				if not puntero:
					continue
				try:
					guardado.append((formato, ctypes.string_at(puntero, kernel32.GlobalSize(asa))))
				finally:
					kernel32.GlobalUnlock(asa)
			except win32clipboard.error:
				log.debug("No se pudo guardar el formato %s del portapapeles", formato, exc_info=True)
	return guardado


def restaurar_portapapeles(guardado: list[tuple[int, bytes]]) -> None:
	import win32clipboard

	from app.services.windows import portapapeles

	with portapapeles._abierto():
		win32clipboard.EmptyClipboard()
		for formato, datos in guardado:
			try:
				win32clipboard.SetClipboardData(formato, datos)
			except win32clipboard.error:
				log.debug("No se pudo restaurar el formato %s del portapapeles", formato, exc_info=True)


class TareasInmediatas:
	"""``GestorTareas`` que ejecuta en el acto (las respuestas, también en el acto)."""

	def __init__(self) -> None:
		self.enviadas: list[str] = []

	def enviar(self, funcion, *args, al_terminar=None, al_fallar=None, nombre=None, **_resto):
		self.enviadas.append(nombre or getattr(funcion, "__name__", ""))
		try:
			resultado = funcion(None, *args)
		except Exception as error:  # noqa: BLE001 - se entrega como haría el gestor
			if al_fallar is not None:
				al_fallar(error)
			return None
		if al_terminar is not None:
			al_terminar(resultado)
		return None


class ListaFalsa:
	def __init__(self) -> None:
		self.iconos = None
		self.arrastre = None
		self.destino = None

	def GetFocusedItem(self):  # noqa: N802 - API de wx
		return -1

	def ClientToScreen(self, punto):  # noqa: N802 - API de wx
		import wx

		return wx.Point(punto[0] + 100, punto[1] + 200)

	def al_empezar_arrastre(self, funcion):
		self.arrastre = funcion

	def fijar_destino_soltar(self, objeto):
		self.destino = objeto


class PanelFalso:
	"""Panel del disco con lo mínimo del ``PanelProtocolo`` que usa el bloque G."""

	lado = "izquierdo"

	def __init__(self, carpeta: Path, entradas=(), ventana=None, lista=None) -> None:
		from app.services.vfs import resolver

		self.proveedor = resolver.proveedor_local()
		self.ruta = str(carpeta)
		self._entradas = list(entradas)
		self.ventana = ventana
		self.refrescos = 0
		self.idas: list[tuple[str, str | None]] = []
		self._lista = lista or ListaFalsa()
		self.lista_resultados: str | None = None

	def es_lista(self):
		return self.lista_resultados

	def es_local(self) -> bool:
		return True

	def ruta_local(self):
		return self.ruta

	def mostrar_ruta(self) -> str:
		return self.ruta

	def entradas(self):
		return list(self._entradas)

	def cursor(self):
		return self._entradas[0] if self._entradas else None

	def marcadas(self):
		return []

	def elementos_trabajo(self):
		return [e for e in self._entradas if not e.es_superior]

	def refrescar(self, conservar: bool = True, al_terminar=None) -> None:
		self.refrescos += 1

	def ir_a(self, ruta, proveedor=None, cursor=None, al_terminar=None) -> None:
		self.idas.append((ruta, cursor))

	def lista(self):
		return self._lista


class VentanaFalsa:
	"""Lo que el bloque G pide a la ventana: configuración, tareas y lanzar operaciones."""

	def __init__(self, config) -> None:
		self.config = config
		self.tareas = TareasInmediatas()
		self.lanzadas: list[tuple[object, bool, object]] = []
		self.ordenes: list[str] = []

	def GetHandle(self) -> int:  # noqa: N802 - API de wx
		return 0

	def lanzar_operacion(self, operacion, en_cola: bool = False, al_terminar=None) -> None:
		self.lanzadas.append((operacion, en_cola, al_terminar))

	def ejecutar_orden(self, id_orden: str, lado=None) -> None:
		self.ordenes.append(id_orden)


def contexto(ventana, panel, pasivo=None):
	from app.ui.contexto import ContextoOrden

	ctx = ContextoOrden(ventana, ventana.config, ventana.tareas, None)
	ctx.activo = ctx.izquierdo = panel
	ctx.pasivo = ctx.derecho = pasivo or panel
	return ctx


def entrada(ruta: Path):
	from app.services.vfs import resolver

	return resolver.proveedor_local().info(str(ruta))
