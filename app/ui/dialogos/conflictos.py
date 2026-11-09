# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Conflictos al copiar o mover: la lista de todos a la vez y la pregunta individual (sección 8.4).

- ``DialogoConflictos``: una fila por archivo que ya existe en el destino. Se
  decide con una letra sobre las filas seleccionadas (selección múltiple
  nativa: Ctrl+Espacio, Mayús+flechas) o sobre la del cursor: S sobrescribir,
  O omitir, C renombrar la copia, E renombrar el existente. Cada cambio se
  anuncia («Sobrescribir: 12 filas»), porque la columna Acción no se vuelve a
  leer sola al cambiar. La acción inicial es Omitir: si la persona pulsa Intro
  sin mirar, no se pierde nada.
- ``DialogoConflicto``: la pregunta de uno en uno (conflictos tardíos o con la
  lista desactivada). El foco empieza en Omitir y Escape equivale a Omitir,
  por el mismo motivo.

Las letras de la lista no llevan Alt: se atienden en ``EVT_KEY_DOWN`` de la
lista y se consumen también en ``EVT_CHAR`` para que la búsqueda por la
primera letra del control nativo no mueva el cursor a otra fila.
"""

from __future__ import annotations

import builtins
import logging
import re
from collections.abc import Sequence
from typing import Any

import wx

from app.services import formato
from app.services.operaciones import nombres
from app.services.operaciones.modelo import AccionConflicto, Conflicto, RespuestaConflicto
from app.ui import anuncios
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Letra (sin modificadores) → acción, en la lista de conflictos.
TECLAS: dict[str, AccionConflicto] = {
	"S": AccionConflicto.SOBRESCRIBIR,
	"O": AccionConflicto.OMITIR,
	"C": AccionConflicto.RENOMBRAR_COPIA,
	"E": AccionConflicto.RENOMBRAR_EXISTENTE,
}

COL_NOMBRE, COL_ORIGEN, COL_ACCION, COL_DESTINO = range(4)

MOSTRAR_TODOS, MOSTRAR_DESTINO_RECIENTE = range(2)


def texto_accion(accion: AccionConflicto) -> str:
	"""Texto de la columna Acción y de los anuncios."""
	return {
		AccionConflicto.SOBRESCRIBIR: _("Sobrescribir"),
		AccionConflicto.OMITIR: _("Omitir"),
		AccionConflicto.RENOMBRAR: _("Renombrar"),
		AccionConflicto.RENOMBRAR_COPIA: _("Renombrar la copia"),
		AccionConflicto.RENOMBRAR_EXISTENTE: _("Renombrar el existente"),
		AccionConflicto.SOBRESCRIBIR_SI_MAS_ANTIGUO: _("Sobrescribir si es más antiguo"),
		AccionConflicto.SOBRESCRIBIR_SI_CAMBIA_TAMANO: _("Sobrescribir si cambia el tamaño"),
		AccionConflicto.CANCELAR: _("Cancelar"),
	}[accion]


def tamano_y_fecha(entrada) -> str:
	"""«1,2 MB, 03/05/2026 10:20» para las columnas Origen y Destino."""
	partes = [formato.tamano_legible(entrada.tamano), formato.fecha(entrada.modificado)]
	return ", ".join(p for p in partes if p)


def destino_mas_reciente(conflicto: Conflicto) -> bool:
	"""El mismo margen de 2 s que ``Conflicto.descripcion`` (FAT guarda la hora con 2 s de precisión)."""
	return conflicto.destino.modificado > conflicto.origen.modificado + 2


def _nombre_final(ruta: str) -> str:
	partes = [p for p in re.split(r"[\\/]", ruta) if p]
	return partes[-1] if partes else ruta


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	"""``EndModal`` si es modal; si no (pruebas sin ``ShowModal``), solo deja el código."""
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


def _comparar(padre: wx.Window, origen: Any, destino: Any, conflicto: Conflicto) -> None:
	if origen is None or destino is None:
		anuncios.anunciar(_("No se pueden comparar estos archivos"), anuncios.RESULTADO)
		return
	from app.ui.ventanas import diferencias

	diferencias.abrir(padre, (origen, conflicto.origen.ruta), (destino, conflicto.ruta_destino))


class DialogoConflictos(wx.Dialog):
	"""Lista de conflictos tras el análisis. ``ShowModal`` devuelve ``wx.ID_OK`` (Continuar) o ``wx.ID_CANCEL``.

	:param origen, destino: proveedores de cada lado (para Comparar); pueden ser None.
	"""

	def __init__(self, padre: wx.Window | None, conflictos: Sequence[Conflicto], origen: Any = None, destino: Any = None,
			titulo: str = "") -> None:
		super().__init__(padre, title=titulo or _("Conflictos"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			name=_("Conflictos"))
		self.conflictos = list(conflictos)
		self.acciones: list[AccionConflicto] = [AccionConflicto.OMITIR] * len(self.conflictos)
		self._origen = origen
		self._destino = destino
		self._visibles: list[int] = []
		self._fijo: list[RespuestaConflicto] | None = None

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)

		# La etiqueta justo antes de la lista: de ella toma el lector su nombre.
		etiqueta = wx.StaticText(panel, label=_("&Conflictos:"))
		self.lista = wx.ListCtrl(panel, style=wx.LC_REPORT, size=panel.FromDIP(wx.Size(720, 260)), name=_("Conflictos"))
		for columna, (texto, ancho) in enumerate((
			(_("Nombre"), 260), (_("Origen"), 170), (_("Acción"), 150), (_("Destino"), 170),
		)):
			self.lista.InsertColumn(columna, texto, width=panel.FromDIP(ancho))
		self.lista.SetHelpText(_(
			"Archivos que ya existen en el destino. Sobre las filas seleccionadas o la del cursor: S sobrescribir, "
			"O omitir, C renombrar la copia, E renombrar el existente. Control+Espacio y Mayúsculas+flechas seleccionan "
			"varias. Intro continúa."))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)

		_etiqueta, self.mostrar = crear_campo(
			panel, _("&Mostrar:"), wx.Choice, choices=[_("Todos"), _("Solo los de destino más reciente")],
			ayuda=_("Filtra la lista: todos los conflictos o solo aquellos cuyo destino es más reciente que el origen."),
			sizer=sizer, horizontal=True, expandir=False)
		self.mostrar.SetSelection(MOSTRAR_TODOS)

		_etiqueta, self.texto = crear_campo(
			panel, _("&Descripción:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
			size=panel.FromDIP(wx.Size(-1, 90)),
			ayuda=_("Tamaños y fechas del conflicto de la fila del cursor."), sizer=sizer)

		botones = wx.WrapSizer(wx.HORIZONTAL)
		self.boton_comparar = wx.Button(panel, label=_("Com&parar"))
		self.boton_comparar.SetHelpText(_("Compara el contenido del archivo de origen y el de destino de la fila del cursor."))
		self.boton_todos = wx.Button(panel, label=_("Aplicar a &todos"))
		self.boton_todos.SetHelpText(_("Pone en todas las filas que se ven la acción de la fila del cursor."))
		self.boton_antiguos = wx.Button(panel, label=_("Sobrescribir los más &antiguos"))
		self.boton_antiguos.SetHelpText(_("Sobrescribe solo los destinos más antiguos que su origen, omite el resto y continúa."))
		self.boton_continuar = wx.Button(panel, wx.ID_OK, label=_("Co&ntinuar"))
		self.boton_continuar.SetHelpText(_("Continúa la operación con la acción de cada fila."))
		self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, label=_("Cancelar la op&eración"))
		self.boton_cancelar.SetHelpText(_("No copia nada y cancela la operación."))
		for boton in (self.boton_comparar, self.boton_todos, self.boton_antiguos, self.boton_continuar, self.boton_cancelar):
			botones.Add(boton, 0, wx.ALL, 4)
		self.boton_continuar.SetDefault()
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		if origen is None or destino is None:
			self.boton_comparar.Disable()

		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)

		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_pulsar_tecla)
		self.lista.Bind(wx.EVT_CHAR, self._al_escribir)
		self.lista.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda _e: self._actualizar_descripcion())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._actualizar_descripcion())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.continuar())
		self.mostrar.Bind(wx.EVT_CHOICE, lambda _e: self._rellenar())
		self.boton_comparar.Bind(wx.EVT_BUTTON, lambda _e: self.comparar())
		self.boton_todos.Bind(wx.EVT_BUTTON, lambda _e: self.aplicar_a_todos())
		self.boton_antiguos.Bind(wx.EVT_BUTTON, lambda _e: self.sobrescribir_antiguos())
		self.boton_continuar.Bind(wx.EVT_BUTTON, lambda _e: self.continuar())

		self._rellenar()
		preparar_dialogo(self, id_escape=wx.ID_CANCEL, foco_inicial=self.lista)
		self.CentreOnParent()

	# ── Resultado ───────────────────────────────────────────────────────────

	def resultado(self) -> list[RespuestaConflicto]:
		"""Una respuesta por conflicto, en el orden recibido (también los ocultos por el filtro)."""
		if self._fijo is not None:
			return list(self._fijo)
		return [RespuestaConflicto(accion) for accion in self.acciones]

	def continuar(self) -> None:
		_terminar(self, wx.ID_OK)

	def sobrescribir_antiguos(self) -> None:
		"""Resuelve de una vez: el motor sobrescribe si el origen es más reciente (lo comprueba al copiar)."""
		self._fijo = [RespuestaConflicto(AccionConflicto.SOBRESCRIBIR_SI_MAS_ANTIGUO) for _c in self.conflictos]
		_terminar(self, wx.ID_OK)

	# ── Filas ───────────────────────────────────────────────────────────────

	def _rellenar(self) -> None:
		"""Vuelve a llenar la lista según el filtro, conservando la fila del cursor si sigue visible."""
		anterior = self.indice_cursor()
		if self.mostrar.GetSelection() == MOSTRAR_DESTINO_RECIENTE:
			self._visibles = [i for i, c in enumerate(self.conflictos) if destino_mas_reciente(c)]
		else:
			self._visibles = list(range(len(self.conflictos)))
		self.lista.DeleteAllItems()
		for fila, indice in enumerate(self._visibles):
			conflicto = self.conflictos[indice]
			self.lista.InsertItem(fila, conflicto.relativo)
			self.lista.SetItem(fila, COL_ORIGEN, tamano_y_fecha(conflicto.origen))
			self.lista.SetItem(fila, COL_ACCION, texto_accion(self.acciones[indice]))
			self.lista.SetItem(fila, COL_DESTINO, tamano_y_fecha(conflicto.destino))
		if self._visibles:
			fila = self._visibles.index(anterior) if anterior in self._visibles else 0
			self.lista.Focus(fila)
			self.lista.Select(fila)
		self._actualizar_descripcion()

	def indice_cursor(self) -> int | None:
		"""Índice (en ``conflictos``) de la fila del cursor, o de la primera seleccionada."""
		fila = self.lista.GetFocusedItem()
		if fila < 0:
			fila = self.lista.GetFirstSelected()
		if 0 <= fila < len(self._visibles):
			return self._visibles[fila]
		return None

	def indices_objetivo(self) -> list[int]:
		"""Las filas seleccionadas; si no hay ninguna, la del cursor."""
		indices = []
		fila = self.lista.GetFirstSelected()
		while fila >= 0:
			if fila < len(self._visibles):
				indices.append(self._visibles[fila])
			fila = self.lista.GetNextSelected(fila)
		if not indices:
			cursor = self.indice_cursor()
			if cursor is not None:
				indices.append(cursor)
		return indices

	def aplicar_accion(self, accion: AccionConflicto, indices: Sequence[int] | None = None) -> int:
		"""Pone ``accion`` en esas filas (por defecto, las objetivo) y lo anuncia. Devuelve cuántas cambió."""
		indices = list(self.indices_objetivo() if indices is None else indices)
		if not indices:
			anuncios.anunciar(_("No hay ninguna fila"), anuncios.RESULTADO)
			return 0
		for indice in indices:
			self.acciones[indice] = accion
			if indice in self._visibles:
				self.lista.SetItem(self._visibles.index(indice), COL_ACCION, texto_accion(accion))
		if len(indices) == 1:
			que = self.conflictos[indices[0]].relativo
		else:
			que = formato.plural(len(indices), _("{n} fila"), _("{n} filas"))
		anuncios.anunciar(_("{accion}: {que}").format(accion=texto_accion(accion), que=que), anuncios.RESULTADO)
		self._actualizar_descripcion()
		return len(indices)

	def aplicar_tecla(self, letra: str) -> bool:
		"""S, O, C o E sobre las filas objetivo. ``False`` si la letra no es de la lista."""
		accion = TECLAS.get(letra.upper())
		if accion is None:
			return False
		self.aplicar_accion(accion)
		return True

	def aplicar_a_todos(self) -> None:
		"""La acción de la fila del cursor en todas las filas visibles."""
		cursor = self.indice_cursor()
		if cursor is None:
			anuncios.anunciar(_("No hay ninguna fila"), anuncios.RESULTADO)
			return
		self.aplicar_accion(self.acciones[cursor], list(self._visibles))

	def comparar(self) -> None:
		cursor = self.indice_cursor()
		if cursor is None:
			anuncios.anunciar(_("No hay ninguna fila"), anuncios.RESULTADO)
			return
		_comparar(self, self._origen, self._destino, self.conflictos[cursor])

	def _actualizar_descripcion(self) -> None:
		cursor = self.indice_cursor()
		if cursor is None:
			texto = _("No hay conflictos que mostrar con este filtro.") if self.conflictos else _("No hay conflictos.")
		else:
			texto = self.conflictos[cursor].descripcion() + "\n" + _("Acción: {a}").format(a=texto_accion(self.acciones[cursor]))
		if self.texto.GetValue() != texto:
			self.texto.ChangeValue(texto)

	# ── Teclado y menú ──────────────────────────────────────────────────────

	def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		if evento.GetModifiers() == wx.MOD_NONE and 0 < codigo < 256 and chr(codigo).upper() in TECLAS:
			self.aplicar_tecla(chr(codigo))
			return
		evento.Skip()

	def _al_escribir(self, evento: wx.KeyEvent) -> None:
		# Se consumen aquí también: si no, la búsqueda por letra del control nativo movería el cursor.
		caracter = evento.GetUnicodeKey()
		if evento.GetModifiers() in (wx.MOD_NONE, wx.MOD_SHIFT) and caracter and chr(caracter).upper() in TECLAS:
			return
		evento.Skip()

	def _al_menu_contextual(self, _evento: wx.ContextMenuEvent) -> None:
		menu = wx.Menu()
		for letra, etiqueta in (
			("S", _("&Sobrescribir")), ("O", _("&Omitir")),
			("C", _("Renombrar la &copia")), ("E", _("Renombrar el &existente")),
		):
			elemento = menu.Append(wx.ID_ANY, f"{etiqueta}\t{letra}")
			menu.Bind(wx.EVT_MENU, lambda _e, accion=TECLAS[letra]: self.aplicar_accion(accion), elemento)
		menu.AppendSeparator()
		elemento = menu.Append(wx.ID_ANY, _("Aplicar a &todos"))
		menu.Bind(wx.EVT_MENU, lambda _e: self.aplicar_a_todos(), elemento)
		elemento = menu.Append(wx.ID_ANY, _("Com&parar"))
		elemento.Enable(self.boton_comparar.IsEnabled())
		menu.Bind(wx.EVT_MENU, lambda _e: self.comparar(), elemento)
		self.lista.PopupMenu(menu)
		menu.Destroy()


class DialogoConflicto(wx.Dialog):
	"""Pregunta por un solo conflicto. ``respuesta()`` da la elección (Omitir si se cierra con Escape)."""

	def __init__(self, padre: wx.Window | None, conflicto: Conflicto, origen: Any = None, destino: Any = None,
			titulo: str = "") -> None:
		super().__init__(padre, title=titulo or _("El archivo ya existe"), style=wx.DEFAULT_DIALOG_STYLE,
			name=_("El archivo ya existe"))
		self.conflicto = conflicto
		self._origen = origen
		self._destino = destino
		self._respuesta = RespuestaConflicto(AccionConflicto.OMITIR)

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.texto = crear_campo(
			panel, _("&Conflicto:"), wx.TextCtrl, value=conflicto.descripcion(),
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP, size=panel.FromDIP(wx.Size(520, 110)),
			ayuda=_("Nombre, tamaño y fecha del origen y del destino."), sizer=sizer)

		botones = wx.WrapSizer(wx.HORIZONTAL)
		self._botones: dict[str, wx.Button] = {}
		for clave, etiqueta, ayuda, respuesta in (
			("sobrescribir", _("&Sobrescribir"), _("Sustituye el archivo del destino por el de origen."),
				RespuestaConflicto(AccionConflicto.SOBRESCRIBIR)),
			("sobrescribir_todos", _("Sobrescribir &todos"), _("Sobrescribe este y todos los conflictos que vengan."),
				RespuestaConflicto(AccionConflicto.SOBRESCRIBIR, para_todos=True)),
			("omitir", _("&Omitir"), _("No copia este archivo."), RespuestaConflicto(AccionConflicto.OMITIR)),
			("omitir_todos", _("Omitir to&dos"), _("Omite este y todos los conflictos que vengan."),
				RespuestaConflicto(AccionConflicto.OMITIR, para_todos=True)),
			("antiguos", _("Sobrescribir los más &antiguos"),
				_("Sobrescribe solo si el destino es más antiguo que el origen, en este y en los que vengan."),
				RespuestaConflicto(AccionConflicto.SOBRESCRIBIR_SI_MAS_ANTIGUO, para_todos=True)),
			("renombrar", _("&Renombrar..."), _("Pide otro nombre para la copia."), None),
			("renombrar_todos", _("Renombrar todos a&utomáticamente"),
				_("La copia se llama «nombre (2)», en este y en los que vengan."),
				RespuestaConflicto(AccionConflicto.RENOMBRAR_COPIA, para_todos=True)),
			("comparar", _("Com&parar"), _("Compara el contenido de los dos archivos."), None),
			("cancelar", _("Cancelar la op&eración"), _("No copia nada más y cancela la operación."),
				RespuestaConflicto(AccionConflicto.CANCELAR)),
		):
			boton = wx.Button(panel, label=etiqueta)
			boton.SetHelpText(ayuda)
			if respuesta is not None:
				boton.Bind(wx.EVT_BUTTON, lambda _e, r=respuesta: self.elegir(r))
			self._botones[clave] = boton
			botones.Add(boton, 0, wx.ALL, 4)
		self._botones["renombrar"].Bind(wx.EVT_BUTTON, lambda _e: self.renombrar())
		self._botones["comparar"].Bind(wx.EVT_BUTTON, lambda _e: _comparar(self, self._origen, self._destino, self.conflicto))
		if origen is None or destino is None:
			self._botones["comparar"].Disable()
		self.boton_omitir = self._botones["omitir"]
		self.boton_omitir.SetDefault()
		sizer.Add(botones, 0, wx.EXPAND | wx.ALL, 4)

		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		# Omitir es lo que no pierde nada: foco inicial y respuesta de Escape.
		preparar_dialogo(self, id_escape=self.boton_omitir.GetId(), foco_inicial=self.boton_omitir)
		self.CentreOnParent()

	def respuesta(self) -> RespuestaConflicto:
		return self._respuesta

	def elegir(self, respuesta: RespuestaConflicto) -> None:
		self._respuesta = respuesta
		_terminar(self, wx.ID_OK)

	def nombre_propuesto(self) -> str:
		"""«nombre (2).ext» que aún no existe en el destino (si se puede comprobar)."""
		ruta = self.conflicto.ruta_destino
		nombre = _nombre_final(ruta)
		proveedor = self._destino

		def existe(candidato: str) -> bool:
			if proveedor is None:
				return False
			try:
				carpeta = proveedor.padre(ruta) or ""
				return bool(proveedor.existe(proveedor.unir(carpeta, candidato)))
			except Exception:  # noqa: BLE001 - es solo una propuesta: si no se puede comprobar, se propone igual
				log.debug("No se pudo comprobar si existe %s", candidato, exc_info=True)
				return False

		return nombres.nombre_libre(nombre, existe)

	def renombrar(self) -> None:
		from app.ui.dialogos.nombre import pedir_nombre

		nombre = pedir_nombre(self, _("Renombrar la copia"), _("&Nombre nuevo de la copia:"), self.nombre_propuesto())
		if nombre is None:
			self.boton_omitir.SetFocus()
			return
		self.elegir(RespuestaConflicto(AccionConflicto.RENOMBRAR, nombre_nuevo=nombre))
