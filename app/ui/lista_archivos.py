# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lista de archivos de un panel: ``wx.ListCtrl`` virtual con marcas al estilo Norton.

Decisiones (secciones 4.3 y 5 del diseño):

- **Virtual**: cada celda se formatea al pedirla (``OnGetItemText``) desde la
  lista de ``Entrada``; no se guardan cadenas por adelantado (100 000 filas).
- **Marcas = modelo**: un conjunto de claves (ruta en minúsculas). La
  selección nativa solo lo refleja para que el lector diga «seleccionado».
  Los elementos de trabajo salen del modelo, nunca de la selección nativa.
- **Marcas que dejan de verse**: lo marcado que un filtro o los ocultos
  esconden se aparta (``_marcas_ocultas``) y vuelve a estar marcado si se ve
  de nuevo. Mientras no se ve no cuenta: ni en «marcados» ni como elemento de
  trabajo, para que una orden nunca actúe sobre lo que la persona no tiene
  delante. Se olvidan al limpiar las marcas (cambiar de carpeta, «Desmarcar
  todo»).
- **Dos modos**: sin marcas, selección simple (las flechas son nativas y el
  lector no dice «no seleccionado»); con marcas, selección múltiple y las
  teclas de movimiento solo mueven el foco. El modo se cambia con
  ``SetWindowStyleFlag`` antes de mover el foco.
- **Cursor visible** en modo múltiple con un color propio (``OnGetItemAttr``),
  porque un elemento enfocado sin seleccionar solo lleva un recuadro punteado.
- ``LVS_SHOWSELALWAYS`` para ver las marcas en el panel pasivo.
- Enganches para el bloque G: iconos, arrastrar y soltar.
"""

from __future__ import annotations

import ctypes
import logging
from typing import Any
from collections.abc import Callable, Sequence

import wx

from app.services.vfs.base import Entrada

log = logging.getLogger(__name__)

GWL_STYLE = -16
LVS_SHOWSELALWAYS = 0x0008
LVM_SETITEMSTATE = 0x1000 + 43
LVIS_SELECTED = 0x0002

_TECLAS_MOVIMIENTO = {wx.WXK_UP, wx.WXK_DOWN, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN, wx.WXK_HOME, wx.WXK_END,
	wx.WXK_NUMPAD_UP, wx.WXK_NUMPAD_DOWN, wx.WXK_NUMPAD_PAGEUP, wx.WXK_NUMPAD_PAGEDOWN, wx.WXK_NUMPAD_HOME, wx.WXK_NUMPAD_END}


class _LVITEM(ctypes.Structure):
	_fields_ = [
		("mask", ctypes.c_uint), ("iItem", ctypes.c_int), ("iSubItem", ctypes.c_int), ("state", ctypes.c_uint),
		("stateMask", ctypes.c_uint), ("pszText", ctypes.c_void_p), ("cchTextMax", ctypes.c_int), ("iImage", ctypes.c_int),
		("lParam", ctypes.c_void_p), ("iIndent", ctypes.c_int), ("iGroupId", ctypes.c_int), ("cColumns", ctypes.c_uint),
		("puColumns", ctypes.c_void_p), ("piColFmt", ctypes.c_void_p), ("iGroup", ctypes.c_int),
	]


def clave(entrada: Entrada) -> str:
	return entrada.ruta.casefold()


#: Los seis colores con nombre de las reglas (10.10); el texto va siempre además del color.
COLORES_REGLAS = {"Rojo": "#C00000", "Verde": "#007A00", "Azul": "#0050C8", "Ámbar": "#B87800", "Morado": "#7A2A9A",
	"Gris": "#606060"}


class ListaArchivos(wx.ListCtrl):
	"""Lista virtual de un panel.

	:param formatear: ``formatear(entrada, columna) -> str`` (lo da el panel).
	:param cabecera_de: ``cabecera_de(columna) -> str``.
	:param al_cambiar_cursor: ``funcion()`` cuando cambia el elemento del cursor.
	:param al_cambiar_marcas: ``funcion()`` cuando cambian las marcas.
	"""

	def __init__(
		self,
		padre: wx.Window,
		nombre: str,
		formatear: Callable[[Entrada, str], str],
		cabecera_de: Callable[[str], str],
		al_cambiar_cursor: Callable[[], None] | None = None,
		al_cambiar_marcas: Callable[[], None] | None = None,
	) -> None:
		super().__init__(padre, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL, name=nombre)
		self._formatear = formatear
		self._cabecera_de = cabecera_de
		self._al_cambiar_cursor = al_cambiar_cursor
		self._al_cambiar_marcas = al_cambiar_marcas
		self._entradas: list[Entrada] = []
		self._indice_por_clave: dict[str, int] = {}
		self._marcas: set[str] = set()
		#: Marcas de entradas que ahora no se ven (filtro, ocultos); vuelven al verse.
		self._marcas_ocultas: set[str] = set()
		self._columnas: list[str] = []
		self._ultimo_cursor = -1
		self._icono_de: Callable[[Entrada], int | None] | None = None
		self._attr_cursor = wx.ItemAttr()
		self._attr_marcada = wx.ItemAttr()
		self._attr_cursor_marcada = wx.ItemAttr()
		self._colores_propios = False
		self.columna_actual = 0
		self._aplicando = False
		#: ``al_teclear(caracter) -> bool``: lo pone el panel (búsqueda rápida o línea de órdenes).
		self.al_teclear: Callable[[str], bool] | None = None
		# 2.0 (19.1): columnas de complementos y decorador de filas de las reglas.
		self._columnas_externas: Callable[[str, Entrada, Any, Callable[[], None]], str | None] | None = None
		self._decorador: Callable[[Entrada], Any] | None = None
		self._efectos: dict[str, Any] = {}
		self._attrs_color: dict[str, wx.ItemAttr] = {}
		#: Proveedor de lo que se muestra (lo fija el panel); lo reciben las columnas de complementos.
		self.obtener_proveedor: Callable[[], Any] | None = None
		self._fijar_estilo_extra(LVS_SHOWSELALWAYS)
		self.aplicar_colores(None)
		self.Bind(wx.EVT_KEY_DOWN, self._al_tecla)
		self.Bind(wx.EVT_LEFT_DOWN, self._al_clic)
		self.Bind(wx.EVT_MOTION, self._al_mover_raton)
		self._inicio_arrastre: wx.Point | None = None
		self._arrastre: Callable[[list[Entrada]], None] | None = None
		self.Bind(wx.EVT_CHAR, self._al_caracter)
		self.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._al_foco_elemento)
		self.Bind(wx.EVT_LIST_ITEM_SELECTED, self._al_cambio_seleccion)
		self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._al_cambio_seleccion)

	# ── Estilos ───────────────────────────────────────────────────────────────

	def _fijar_estilo_extra(self, bit: int) -> None:
		try:
			hwnd = self.GetHandle()
			estilo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
			ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, estilo | bit)
		except (AttributeError, OSError):
			log.debug("No se pudo poner el estilo %#x", bit, exc_info=True)

	@property
	def multiple(self) -> bool:
		return not (self.GetWindowStyleFlag() & wx.LC_SINGLE_SEL)

	def _poner_modo(self, multiple: bool) -> None:
		if multiple == self.multiple:
			return
		estilo = self.GetWindowStyleFlag()
		self.SetWindowStyleFlag(estilo & ~wx.LC_SINGLE_SEL if multiple else estilo | wx.LC_SINGLE_SEL)
		self._fijar_estilo_extra(LVS_SHOWSELALWAYS)

	def aplicar_colores(self, colores: dict[str, wx.Colour] | None) -> None:
		"""Colores del tema (``app.ui.tema``). ``None``: los del sistema."""
		fondo = self.GetBackgroundColour()
		resalte = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
		cursor = wx.Colour(
			(fondo.Red() + resalte.Red()) // 2, (fondo.Green() + resalte.Green()) // 2, (fondo.Blue() + resalte.Blue()) // 2,
		)
		self._colores_propios = colores is not None
		if colores:
			self.SetBackgroundColour(colores["fondo"])
			self.SetForegroundColour(colores["texto"])
			cursor = colores["cursor_fondo"]
			self._attr_marcada.SetTextColour(colores["marcado_texto"])
			self._attr_cursor_marcada.SetTextColour(colores["marcado_texto"])
			self._attr_cursor.SetTextColour(colores.get("cursor_texto", colores["texto"]))
		self._attr_cursor.SetBackgroundColour(cursor)
		self._attr_cursor_marcada.SetBackgroundColour(cursor)
		self.Refresh()

	# ── Columnas ──────────────────────────────────────────────────────────────

	# ── 2.0: columnas de complementos, decorador de filas y señales para NVDA ──

	def fijar_columnas_externas(self, funcion: Callable[[str, Entrada, Any, Callable[[], None]], str | None] | None) -> None:
		"""Valor de las columnas ``<id>:<columna>`` de complementos (``registro.valor_columna``, 3.13).

		Nunca bloquea: mientras el valor no llega la celda muestra «…» y, cuando llega,
		``al_listo`` repinta la fila.
		"""
		self._columnas_externas = funcion
		self.Refresh()

	def fijar_decorador_fila(self, funcion: Callable[[Entrada], Any] | None) -> None:
		"""``funcion(entrada) -> EfectoFila | None`` (reglas de anuncio, color y sonido, 10.10)."""
		self._decorador = funcion
		self._efectos.clear()
		self.Refresh()

	def efecto_de(self, entrada: Entrada) -> Any:
		"""Efecto de la primera regla que coincide (con caché por entrada)."""
		if self._decorador is None or entrada is None:
			return None
		clave = f"{entrada.ruta}|{entrada.tamano}|{entrada.modificado}"
		if clave not in self._efectos:
			try:
				self._efectos[clave] = self._decorador(entrada)
			except Exception:  # noqa: BLE001 - una regla rota no puede romper el pintado
				log.debug("Falló el decorador de filas", exc_info=True)
				self._efectos[clave] = None
		return self._efectos[clave]

	def _valor_externo(self, item: int, columna: str) -> str:
		if self._columnas_externas is None:
			return ""
		proveedor = self.obtener_proveedor() if self.obtener_proveedor is not None else None

		def al_listo(fila: int = item) -> None:
			if self and 0 <= fila < self.GetItemCount():
				self.RefreshItem(fila)

		valor = self._columnas_externas(columna, self._entradas[item], proveedor, al_listo)
		return "…" if valor is None else str(valor)

	def poner_columnas(self, columnas: Sequence[str], anchos: dict[str, int] | None = None) -> None:
		anchos = anchos or {}
		self.DeleteAllColumns()
		self._columnas = list(columnas)
		for i, columna in enumerate(self._columnas):
			ancho = anchos.get(columna) or (320 if columna == "nombre" else 160 if columna in ("ruta", "tipo") else 110)
			alineacion = wx.LIST_FORMAT_RIGHT if columna == "tamano" else wx.LIST_FORMAT_LEFT
			self.InsertColumn(i, self._cabecera_de(columna), alineacion, self.FromDIP(ancho))
		self.columna_actual = 0

	@property
	def columnas(self) -> list[str]:
		return list(self._columnas)

	def anchos(self) -> dict[str, int]:
		return {c: self.ToDIP(self.GetColumnWidth(i)) for i, c in enumerate(self._columnas)}

	# ── Modelo ────────────────────────────────────────────────────────────────

	def establecer(
		self, entradas: Sequence[Entrada], cursor: str | None = None, conservar_marcas: bool = True, al_principio: bool = False,
	) -> None:
		"""Muestra ``entradas``; deja el cursor en el nombre ``cursor`` (o donde estaba) y reaplica las marcas.

		:param al_principio: sin ``cursor``, el cursor va a la primera fila en lugar de
			quedarse donde estaba. Es lo que se quiere al entrar en OTRA carpeta: el
			número de fila de la anterior no significa nada en la nueva.

		2.0 (10.16): es un movimiento del foco que hace zCommander por su cuenta: se marca
		antes para que el complemento de NVDA no lo anuncie.
		"""
		from app.ui import senales_nvda

		senales_nvda.marcar_movimiento_silencioso(self.GetHandle())
		self._efectos.clear()
		anterior = self.cursor()
		anterior_indice = self.cursor_indice()
		self._entradas = list(entradas)
		self._indice_por_clave = {clave(e): i for i, e in enumerate(self._entradas)}
		if conservar_marcas:
			todas = self._marcas | self._marcas_ocultas
			self._marcas = {k for k in todas if k in self._indice_por_clave}
			self._marcas_ocultas = todas - self._marcas
		else:
			self._marcas.clear()
			self._marcas_ocultas.clear()
		self.Freeze()
		try:
			self.SetItemCount(len(self._entradas))
			destino = 0
			if cursor is not None:
				destino = next((i for i, e in enumerate(self._entradas) if e.nombre.casefold() == cursor.casefold()), 0)
			elif al_principio:
				destino = 0
			elif anterior is not None and clave(anterior) in self._indice_por_clave:
				destino = self._indice_por_clave[clave(anterior)]
			elif anterior_indice >= 0:
				destino = min(anterior_indice, len(self._entradas) - 1)
			self._poner_modo(bool(self._marcas))
			self._reaplicar(destino)
		finally:
			self.Thaw()
		self.Refresh()

	def entradas(self) -> list[Entrada]:
		return list(self._entradas)

	def entrada(self, indice: int) -> Entrada | None:
		return self._entradas[indice] if 0 <= indice < len(self._entradas) else None

	def cursor_indice(self) -> int:
		indice = self.GetFocusedItem()
		if indice < 0 and not self.multiple:
			indice = self.GetFirstSelected()
		return indice if 0 <= indice < len(self._entradas) else (-1 if not self._entradas else max(0, min(indice, len(self._entradas) - 1)) if indice >= 0 else -1)

	def cursor(self) -> Entrada | None:
		return self.entrada(self.cursor_indice())

	def indice_de(self, nombre: str) -> int:
		return next((i for i, e in enumerate(self._entradas) if e.nombre.casefold() == nombre.casefold()), -1)

	# ── Cursor ────────────────────────────────────────────────────────────────

	def mover_cursor(self, indice: int) -> None:
		"""Pone el cursor en ``indice`` (en modo múltiple sin tocar la selección)."""
		if not self._entradas:
			return
		indice = max(0, min(indice, len(self._entradas) - 1))
		anterior = self.GetFocusedItem()
		self._aplicando = True
		try:
			if self.multiple:
				self.SetItemState(indice, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)
			else:
				if 0 <= anterior < len(self._entradas) and anterior != indice:
					self.SetItemState(anterior, 0, wx.LIST_STATE_SELECTED)
				self.SetItemState(indice, wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED,
					wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED)
		finally:
			self._aplicando = False
		self.EnsureVisible(indice)
		for fila in (anterior, indice):
			if 0 <= fila < len(self._entradas):
				self.RefreshItem(fila)
		self._avisar_cursor()

	def _avisar_cursor(self) -> None:
		indice = self.GetFocusedItem()
		if indice != self._ultimo_cursor:
			self._ultimo_cursor = indice
			if self._al_cambiar_cursor is not None:
				self._al_cambiar_cursor()

	def _al_foco_elemento(self, evento: wx.ListEvent) -> None:
		evento.Skip()
		wx.CallAfter(self._avisar_cursor_si_vivo)

	def _al_cambio_seleccion(self, evento: wx.ListEvent) -> None:
		"""Una selección nativa que no viene del modelo (tecla nativa, el lector) se revierte."""
		evento.Skip()
		if self._aplicando:
			return
		if self.multiple:
			wx.CallAfter(self._revertir_si_vivo)
		else:
			wx.CallAfter(self._avisar_cursor_si_vivo)

	def _revertir_si_vivo(self) -> None:
		if self and self.multiple:
			self._reaplicar(max(0, self.GetFocusedItem()))

	def _al_caracter(self, evento: wx.KeyEvent) -> None:
		"""Primera letra ya traducida por Windows (Mayús, AltGr y acentos correctos)."""
		caracter = evento.GetUnicodeKey()
		if caracter and caracter >= 32 and self.al_teclear is not None:
			# AltGr llega como Ctrl+Alt: se acepta como carácter normal.
			alt_gr = evento.ControlDown() and evento.AltDown()
			if alt_gr or not (evento.ControlDown() or evento.AltDown()):
				if self.al_teclear(chr(caracter)):
					return
		evento.Skip()

	def _avisar_cursor_si_vivo(self) -> None:
		if self:
			self._avisar_cursor()

	def filas_por_pagina(self) -> int:
		return max(1, self.GetCountPerPage())

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		if not self.multiple or codigo not in _TECLAS_MOVIMIENTO or evento.HasAnyModifiers():
			evento.Skip()
			return
		actual = max(0, self.GetFocusedItem())
		pagina = self.filas_por_pagina()
		nuevo = {
			wx.WXK_UP: actual - 1, wx.WXK_NUMPAD_UP: actual - 1, wx.WXK_DOWN: actual + 1, wx.WXK_NUMPAD_DOWN: actual + 1,
			wx.WXK_PAGEUP: actual - pagina, wx.WXK_NUMPAD_PAGEUP: actual - pagina,
			wx.WXK_PAGEDOWN: actual + pagina, wx.WXK_NUMPAD_PAGEDOWN: actual + pagina,
			wx.WXK_HOME: 0, wx.WXK_NUMPAD_HOME: 0, wx.WXK_END: len(self._entradas) - 1, wx.WXK_NUMPAD_END: len(self._entradas) - 1,
		}[codigo]
		self.mover_cursor(nuevo)

	def _al_clic(self, evento: wx.MouseEvent) -> None:
		if not self.multiple:
			evento.Skip()
			return
		indice, _banderas = self.HitTest(evento.GetPosition())
		if indice < 0:
			evento.Skip()
			return
		self.SetFocus()
		if evento.ControlDown():
			self.alternar(indice)
			self.mover_cursor(indice)
		elif evento.ShiftDown():
			desde = max(0, self.GetFocusedItem())
			self.marcar_rango(desde, indice)
			self.mover_cursor(indice)
		else:
			self.mover_cursor(indice)
			# En modo múltiple el clic no llega al control nativo: el arrastre se detecta aquí.
			self._inicio_arrastre = evento.GetPosition()

	def _al_mover_raton(self, evento: wx.MouseEvent) -> None:
		evento.Skip()
		if self._inicio_arrastre is None or not evento.LeftIsDown():
			self._inicio_arrastre = None
			return
		umbral = wx.SystemSettings.GetMetric(wx.SYS_DRAG_X)
		desplazamiento = evento.GetPosition() - self._inicio_arrastre
		if abs(desplazamiento.x) > umbral or abs(desplazamiento.y) > umbral:
			self._inicio_arrastre = None
			entradas = [e for e in (self.marcadas() or [self.cursor()]) if e is not None and not e.es_superior]
			if entradas and self._arrastre is not None:
				self._arrastre(entradas)

	# ── Marcas ────────────────────────────────────────────────────────────────

	def hay_marcas(self) -> bool:
		return bool(self._marcas)

	def esta_marcada(self, indice: int) -> bool:
		entrada = self.entrada(indice)
		return entrada is not None and clave(entrada) in self._marcas

	def marcadas(self) -> list[Entrada]:
		return [e for e in self._entradas if clave(e) in self._marcas]

	def claves_marcadas(self) -> set[str]:
		return set(self._marcas)

	def poner_marcas(self, claves: set[str]) -> None:
		"""Sustituye las marcas (claves que no estén en la lista se ignoran)."""
		self._marcas = {c for c in claves if c in self._indice_por_clave}
		self._sincronizar()

	def marcar_indices(self, indices: Sequence[int], valor: bool = True) -> int:
		"""Marca o desmarca; nunca marca «..». Devuelve cuántas cambiaron."""
		cambios = 0
		for indice in indices:
			entrada = self.entrada(indice)
			if entrada is None or entrada.es_superior:
				continue
			k = clave(entrada)
			if valor and k not in self._marcas:
				self._marcas.add(k)
				cambios += 1
			elif not valor and k in self._marcas:
				self._marcas.discard(k)
				cambios += 1
		if cambios:
			self._sincronizar()
		return cambios

	def alternar(self, indice: int) -> bool | None:
		"""Alterna la marca de una fila; devuelve el estado nuevo (None si no se puede marcar)."""
		entrada = self.entrada(indice)
		if entrada is None or entrada.es_superior:
			return None
		nuevo = clave(entrada) not in self._marcas
		self.marcar_indices([indice], nuevo)
		return nuevo

	def marcar_rango(self, desde: int, hasta: int, valor: bool = True) -> int:
		inicio, fin = sorted((desde, hasta))
		return self.marcar_indices(range(inicio, fin + 1), valor)

	def marcas_ocultas(self) -> set[str]:
		"""Claves marcadas que ahora no se ven (no cuentan como marcadas)."""
		return set(self._marcas_ocultas)

	def podar_marcas_ocultas(self, existentes: set[str]) -> None:
		"""Olvida las marcas ocultas de entradas que ya no existen en la carpeta.

		Las aparta el filtro, pero un archivo borrado o movido no debe volver
		marcado si aparece otro con su nombre.
		"""
		if self._marcas_ocultas:
			self._marcas_ocultas &= existentes

	def limpiar_marcas(self) -> None:
		"""Quita todas las marcas, también las de lo que no se ve."""
		self._marcas_ocultas.clear()
		if self._marcas:
			self._marcas.clear()
			self._sincronizar()

	def _sincronizar(self) -> None:
		"""Refleja el modelo en la lista: modo y selección nativa."""
		cursor = max(0, self.GetFocusedItem())
		self.Freeze()
		try:
			self._poner_modo(bool(self._marcas))
			self._reaplicar(cursor)
		finally:
			self.Thaw()
		if self._al_cambiar_marcas is not None:
			self._al_cambiar_marcas()

	def _seleccion_todas(self, valor: bool) -> None:
		"""Selecciona o quita la selección de TODAS las filas con un solo mensaje (índice −1)."""
		item = _LVITEM()
		item.stateMask = LVIS_SELECTED
		item.state = LVIS_SELECTED if valor else 0
		ctypes.windll.user32.SendMessageW(self.GetHandle(), LVM_SETITEMSTATE, -1, ctypes.byref(item))

	def _quitar_toda_seleccion(self) -> None:
		self._seleccion_todas(False)

	def _seleccion_nativa(self) -> set[int]:
		actuales: set[int] = set()
		indice = self.GetFirstSelected()
		while indice != -1:
			actuales.add(indice)
			indice = self.GetNextSelected(indice)
		return actuales

	def _reaplicar(self, cursor: int) -> None:
		"""Refleja el modelo aplicando solo las DIFERENCIAS (evita avalanchas de eventos para el lector)."""
		if not self._entradas:
			return
		cursor = max(0, min(cursor, len(self._entradas) - 1))
		self._aplicando = True
		try:
			if self.multiple:
				objetivo = {self._indice_por_clave[k] for k in self._marcas if k in self._indice_por_clave}
			else:
				objetivo = {cursor}
			actuales = self._seleccion_nativa()
			total = len(self._entradas)
			if self.multiple and len(objetivo) > total // 2 and len(objetivo - actuales) > 64:
				# Muchas a la vez (marcar todo, invertir): todas con un mensaje y se quita el resto.
				self._seleccion_todas(True)
				for indice in set(range(total)) - objetivo:
					self.SetItemState(indice, 0, wx.LIST_STATE_SELECTED)
			elif not objetivo and actuales:
				self._quitar_toda_seleccion()
			else:
				for indice in actuales - objetivo:
					self.SetItemState(indice, 0, wx.LIST_STATE_SELECTED)
				for indice in objetivo - actuales:
					self.SetItemState(indice, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
			if self.GetFocusedItem() != cursor:
				self.SetItemState(cursor, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)
			self.EnsureVisible(cursor)
		finally:
			self._aplicando = False
		self._avisar_cursor()

	# ── Virtual ───────────────────────────────────────────────────────────────

	def OnGetItemText(self, item: int, column: int) -> str:  # noqa: N802 - API de wx
		if not 0 <= item < len(self._entradas) or not 0 <= column < len(self._columnas):
			return ""
		try:
			columna = self._columnas[column]
			if ":" in columna:
				return self._valor_externo(item, columna)
			if columna == "regla":
				efecto = self.efecto_de(self._entradas[item])
				return getattr(efecto, "texto", "") if efecto is not None else ""
			return self._formatear(self._entradas[item], columna)
		except Exception:  # noqa: BLE001 - una celda rara no puede romper el pintado
			log.debug("Error al formatear la celda %d,%d", item, column, exc_info=True)
			return ""

	def OnGetItemAttr(self, item: int):  # noqa: N802 - API de wx
		marcada = self.esta_marcada(item)
		es_cursor = self.multiple and item == self.GetFocusedItem()
		if es_cursor:
			return self._attr_cursor_marcada if marcada else self._attr_cursor
		if marcada and self._colores_propios:
			return self._attr_marcada
		if self._decorador is not None and 0 <= item < len(self._entradas):
			efecto = self.efecto_de(self._entradas[item])
			color = getattr(efecto, "color", None) if efecto is not None else None
			if color in COLORES_REGLAS:
				if color not in self._attrs_color:
					atributo = wx.ItemAttr()
					atributo.SetTextColour(wx.Colour(COLORES_REGLAS[color]))
					self._attrs_color[color] = atributo
				return self._attrs_color[color]
		return None

	def OnGetItemImage(self, item: int) -> int:  # noqa: N802 - API de wx
		if self._icono_de is None or not 0 <= item < len(self._entradas):
			return -1
		indice = self._icono_de(self._entradas[item])
		return -1 if indice is None else indice

	def OnGetItemColumnImage(self, item: int, column: int) -> int:  # noqa: N802 - API de wx
		return self.OnGetItemImage(item) if column == 0 else -1

	# ── Lectura por columnas ─────────────────────────────────────────────────────

	def texto_celda(self, fila: int, columna: int) -> str:
		return self.OnGetItemText(fila, columna)

	def cabecera(self, columna: int) -> str:
		return self._cabecera_de(self._columnas[columna]) if 0 <= columna < len(self._columnas) else ""

	# ── Enganches para el bloque G ──────────────────────────────────────────────

	def fijar_iconos(self, funcion: Callable[[Entrada], int | None], imagenes: wx.ImageList) -> None:
		"""``funcion(entrada) -> índice en imagenes`` (o None)."""
		self._icono_de = funcion
		self.AssignImageList(imagenes, wx.IMAGE_LIST_SMALL)
		self.Refresh()

	def quitar_iconos(self) -> None:
		"""Deja la lista sin iconos (al desactivar ``paneles.iconos``)."""
		self._icono_de = None
		self.SetImageList(None, wx.IMAGE_LIST_SMALL)
		self.Refresh()

	def al_empezar_arrastre(self, funcion: Callable[[list[Entrada]], None]) -> None:
		"""``funcion(entradas)`` al empezar a arrastrar con el ratón (marcadas o la del cursor)."""
		self._arrastre = funcion

		def manejar(evento: wx.ListEvent) -> None:
			entradas = self.marcadas() or ([self.entrada(evento.GetIndex())] if self.entrada(evento.GetIndex()) else [])
			entradas = [e for e in entradas if e is not None and not e.es_superior]
			if entradas:
				funcion(entradas)

		# Modo simple: el control nativo detecta el arrastre; modo múltiple: _al_mover_raton.
		self.Bind(wx.EVT_LIST_BEGIN_DRAG, manejar)

	def fijar_destino_soltar(self, objeto: wx.DropTarget) -> None:
		self.SetDropTarget(objeto)
