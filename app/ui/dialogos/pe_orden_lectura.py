# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Orden de lectura de las columnas (diseño 2.0, 10.5).

Qué columnas se leen al moverse por las filas (y con Izquierda, Derecha y
Ctrl+1 a Ctrl+0) y en qué orden: las marcadas se colocan las primeras en la
lista, en este orden; las demás se ven, pero al final. Como mucho 15 (la
codificación de ``zCommander.OrdenLectura`` para el complemento de NVDA).

Se aplica a «Esta pestaña» (campo ``lectura`` de la pestaña en la sesión), a
«Este conjunto» (si la carpeta tiene uno aplicado) o a «Las columnas por
defecto» (``paneles.lectura``).
"""

from __future__ import annotations

import builtins
import dataclasses
import logging
from collections.abc import Sequence

import wx

from app.services import vistas_carpeta
from app.services.vistas_modelo import MAX_COLUMNAS_LECTURA
from app.ui import anuncios
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)

PESTANA, CONJUNTO, DEFECTO = "pestana", "conjunto", "defecto"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def titulo(columna: str) -> str:
	from app.ui.dialogos.f_columnas import titulo_columna

	return titulo_columna(columna)


def orden_inicial(columnas: Sequence[str], lectura: Sequence[str]) -> list[str]:
	"""Las de ``lectura`` primero (las que están en ``columnas``), después las demás."""
	primeras = [c for c in lectura if c in columnas]
	return primeras + [c for c in columnas if c not in primeras]


class DialogoOrdenLectura(f_comun.DialogoF):
	"""``lectura`` y ``destino`` quedan con lo elegido al aceptar.

	:param destinos: ``[(destino, texto, columnas, lectura)]``; con uno solo no se muestra «Aplicar en».
	"""

	def __init__(self, padre: wx.Window | None, destinos: Sequence[tuple[str, str, Sequence[str], Sequence[str]]]) -> None:
		super().__init__(padre, _("Orden de lectura de las columnas"))
		self._destinos = list(destinos)
		self.destino = self._destinos[0][0]
		self.lectura: list[str] = []
		self._orden: list[str] = []
		self.selector = None
		if len(self._destinos) > 1:
			_e, self.selector = crear_campo(self.panel, _("Aplicar &en:"), wx.Choice, choices=[t for _d, t, _c, _l in self._destinos],
				sizer=self.sizer, ayuda=_("Dónde se guarda el orden: la pestaña, el conjunto de la carpeta o las columnas por defecto."))
			self.selector.SetSelection(0)
			self.selector.Bind(wx.EVT_CHOICE, lambda _e: self._cargar(self.selector.GetSelection()))
		self.etiqueta_lista = wx.StaticText(self.panel, label=_("Co&lumnas que se leen, en este orden:"))
		self.lista = CheckListBoxAccesible(self.panel, f_comun.texto_limpio(self.etiqueta_lista.GetLabel()).rstrip(":"),
			recordar_posicion=False, size=self.FromDIP(wx.Size(340, 220)))
		self.lista.SetHelpText(_("Marcadas: se leen al moverse por las filas, en este orden (como mucho 15). "
			"Las no marcadas se ven, pero al final. Subir y Bajar cambian el orden."))
		self.sizer.Add(self.etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton(_("&Subir"), _("Sube la columna elegida (se lee antes)."), lambda: self.mover(-1), fila)
		self.boton(_("&Bajar"), _("Baja la columna elegida (se lee después)."), lambda: self.mover(1), fila)
		self.sizer.Add(fila, 0)
		self.lista.Bind(wx.EVT_CHECKLISTBOX, self._al_marcar)
		self.terminar(wx.OK | wx.CANCEL, foco=self.lista)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		self._cargar(0)

	def _cargar(self, indice: int) -> None:
		destino, _t, columnas, lectura = self._destinos[max(0, indice)]
		self.destino = destino
		self._orden = orden_inicial(list(columnas), list(lectura))
		marcadas = set(lectura) if lectura else set(self._orden[:MAX_COLUMNAS_LECTURA])
		self._poner(marcadas, 0)

	def _poner(self, marcadas: set[str], seleccion: int) -> None:
		self.lista.Set([titulo(c) for c in self._orden])
		for i, columna in enumerate(self._orden):
			self.lista.Check(i, columna in marcadas)
		if self._orden:
			self.lista.SetSelection(min(seleccion, len(self._orden) - 1))

	def marcadas(self) -> list[str]:
		return [c for i, c in enumerate(self._orden) if self.lista.IsChecked(i)]

	def marcar(self, indice: int, valor: bool = True) -> bool:
		"""Marca una columna (falso si ya hay 15 marcadas)."""
		if valor and not self.lista.IsChecked(indice) and len(self.marcadas()) >= MAX_COLUMNAS_LECTURA:
			anuncios.anunciar(_("Como mucho 15 columnas se leen al moverse"), anuncios.RESULTADO)
			return False
		self.lista.Check(indice, valor)
		return True

	def _al_marcar(self, evento: wx.CommandEvent) -> None:
		indice = evento.GetInt()
		if self.lista.IsChecked(indice) and len(self.marcadas()) > MAX_COLUMNAS_LECTURA:
			self.lista.Check(indice, False)
			anuncios.anunciar(_("Como mucho 15 columnas se leen al moverse"), anuncios.RESULTADO)
		evento.Skip()

	def mover(self, paso: int) -> None:
		i = self.lista.GetSelection()
		destino = i + paso
		if i < 0 or not 0 <= destino < len(self._orden):
			return
		marcadas = set(self.marcadas())
		self._orden[i], self._orden[destino] = self._orden[destino], self._orden[i]
		self._poner(marcadas, destino)
		self.lista.SetFocus()
		anuncios.anunciar(_("{c}, posición {n} de {t}").format(c=titulo(self._orden[destino]), n=destino + 1, t=len(self._orden)),
			anuncios.RESULTADO)

	def aceptar(self) -> bool:
		self.lectura = vistas_carpeta.lectura_valida(self.marcadas())
		self.cerrar(wx.ID_OK)
		return True


def editar(padre: wx.Window | None, columnas: Sequence[str], lectura: Sequence[str]) -> list[str] | None:
	"""Solo el orden de lectura de unas columnas (lo usa el editor de conjuntos)."""
	dialogo = DialogoOrdenLectura(padre, [(CONJUNTO, "", list(columnas), list(lectura))])
	return f_comun.mostrar(dialogo, lambda d: d.lectura)


def mostrar(padre: wx.Window | None, pe, panel) -> None:
	"""Orden ``orden_lectura``: en la pestaña, en su conjunto o en las columnas por defecto."""
	config = pe.config
	destinos = [(PESTANA, _("Esta pestaña"), list(panel.columnas), list(getattr(panel, "lectura", []) or []))]
	conjunto = getattr(panel, "conjunto", None)
	if conjunto is not None:
		destinos.append((CONJUNTO, _("Este conjunto ({n})").format(n=conjunto.nombre), list(conjunto.columnas) or list(panel.columnas),
			list(conjunto.lectura)))
	destinos.append((DEFECTO, _("Las columnas por defecto"), list(config.obtener("paneles.columnas") or ["nombre"]),
		list(config.obtener("paneles.lectura") or [])))
	resultado = f_comun.mostrar(DialogoOrdenLectura(padre, destinos), lambda d: (d.destino, d.lectura))
	if resultado is None:
		return
	destino, lectura = resultado
	if destino == PESTANA:
		panel.lectura = list(lectura)
		if getattr(panel, "conjunto", None) is None:
			panel.aplicar_lectura(list(lectura))
	elif destino == CONJUNTO and conjunto is not None:
		datos = pe.vistas
		nuevo = dataclasses.replace(conjunto, lectura=tuple(lectura))
		datos.conjuntos = [nuevo if c.nombre == conjunto.nombre else c for c in datos.conjuntos]
		pe.guardar_vistas(datos)
		panel.aplicar_conjunto(nuevo)
	else:
		config.establecer("paneles.lectura", list(lectura))
	anuncios.anunciar(_("Orden de lectura: {c}").format(c=", ".join(titulo(c) for c in lectura) or _("el de las columnas")),
		anuncios.RESULTADO)
