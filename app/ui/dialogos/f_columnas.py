# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Columnas de un lado o por defecto: cuáles se ven, en qué orden y con qué ancho.

- Lista de casillas (``CheckListBoxAccesible``: el lector dice «marcada»).
  El orden de la lista es el orden de las columnas; Subir y Bajar lo cambian.
- La columna Nombre no se puede quitar: sin ella la lista no tendría con qué
  nombrar cada fila. Al intentarlo se vuelve a marcar y se dice por qué.
- El ancho (en píxeles DIP, como los guarda el panel) se edita en un campo
  numérico nativo para la columna elegida.
- La columna Ruta (la carpeta de cada archivo) se ofrece siempre. Es la que
  da sentido a las listas de resultados (vista plana, búsqueda, cesta), donde
  sale por defecto porque los archivos vienen de carpetas distintas; en una
  carpeta normal repite la carpeta del panel, pero quitarla del diálogo
  impedía elegirla precisamente en esas listas.

2.0 (bloque PE, 10.4, 10.5 y 10.10): también se ofrecen la columna «Regla»
(el texto de las reglas de anuncio, color y sonido) y las columnas de los
complementos (``app.plugins.registro.catalogo_columnas()``, sin activarlos).
Con ``lectura`` (el editor de conjuntos de vista por carpeta) el diálogo gana
«Orden de &lectura...».
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Sequence

import wx

from app.core.configuracion import COLUMNAS_DISPONIBLES
from app.ui import anuncios
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)

ANCHO_MINIMO, ANCHO_MAXIMO = 20, 2000
ANCHOS_FABRICA = {"nombre": 320, "ruta": 160, "tipo": 160}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def titulo_columna(columna: str) -> str:
	from app.ui.panel_archivos import cabecera

	return cabecera(columna)


def ancho_fabrica(columna: str) -> int:
	return ANCHOS_FABRICA.get(columna, 110)


def disponibles() -> list[str]:
	"""Columnas que se pueden elegir: las de la 1.x, «Regla» y las de los complementos registrados."""
	resultado = [*COLUMNAS_DISPONIBLES, "regla"]
	try:
		from app.plugins import registro

		resultado += [c.id for c in registro.catalogo_columnas() if c.id not in resultado]
	except Exception:  # noqa: BLE001 - sin registro de complementos se ofrecen las del núcleo
		log.debug("No se pudieron leer las columnas de los complementos", exc_info=True)
	return resultado


def orden_inicial(visibles: Sequence[str]) -> list[str]:
	"""Las visibles en su orden y después las demás disponibles (Ruta incluida)."""
	todas = disponibles()
	resultado = [c for c in visibles if c in todas]
	resultado.extend(c for c in todas if c not in resultado)
	if "nombre" not in resultado:
		resultado.insert(0, "nombre")
	return resultado


class DialogoColumnas(f_comun.DialogoF):
	"""``columnas`` y ``anchos`` quedan con lo elegido al aceptar.

	:param fabrica: columnas que pone «Restablecer» (las del perfil o las de fábrica).
	"""

	def __init__(self, padre: wx.Window | None, titulo: str, visibles: Sequence[str], anchos: dict[str, int],
			fabrica: Sequence[str], lectura: Sequence[str] | None = None) -> None:
		super().__init__(padre, titulo)
		self.lectura: list[str] | None = list(lectura) if lectura is not None else None
		self._orden = orden_inicial(visibles)
		self._fabrica = list(fabrica)
		self.anchos = {c: int(anchos.get(c) or ancho_fabrica(c)) for c in self._orden}
		self.columnas: list[str] = []
		self.etiqueta_lista = wx.StaticText(self.panel, label=_("C&olumnas (marcadas se ven, en este orden):"))
		self.lista = CheckListBoxAccesible(self.panel, f_comun.texto_limpio(self.etiqueta_lista.GetLabel()),
			[titulo_columna(c) for c in self._orden], recordar_posicion=False, size=self.FromDIP(wx.Size(320, 200)))
		self.sizer.Add(self.etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton(_("S&ubir"), _("Mueve la columna elegida a la izquierda."), lambda: self.mover(-1), fila)
		self.boton(_("&Bajar"), _("Mueve la columna elegida a la derecha."), lambda: self.mover(1), fila)
		self.boton(_("&Restablecer"), _("Vuelve a las columnas de fábrica (las del perfil) y a los anchos de fábrica."), self.restablecer, fila)
		if self.lectura is not None:
			self.boton(_("Orden de &lectura..."), _("Qué columnas se leen al moverse por las filas y en qué orden (como mucho 15)."),
				self.elegir_lectura, fila)
		self.sizer.Add(fila, 0)
		_e, self.campo_ancho = crear_campo(self.panel, _("Anc&ho de la columna elegida (píxeles):"), wx.SpinCtrl,
			min=ANCHO_MINIMO, max=ANCHO_MAXIMO, ayuda=_("Ancho en la lista de archivos. Se aplica al aceptar."), sizer=self.sizer,
			expandir=False)
		self.lista.Bind(wx.EVT_LISTBOX, lambda _e: self._mostrar_ancho())
		self.lista.Bind(wx.EVT_CHECKLISTBOX, self._al_marcar)
		self.campo_ancho.Bind(wx.EVT_SPINCTRL, lambda _e: self._guardar_ancho())
		self.campo_ancho.Bind(wx.EVT_TEXT, lambda _e: self._guardar_ancho())
		self.terminar(wx.OK | wx.CANCEL, foco=self.lista)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		self._marcar(visibles)
		self.lista.SetSelection(0)
		self._mostrar_ancho()

	# ── Estado ───────────────────────────────────────────────────────────────

	def _marcar(self, visibles: Sequence[str]) -> None:
		for indice, columna in enumerate(self._orden):
			self.lista.Check(indice, columna in visibles or columna == "nombre")

	def elegidas(self) -> list[str]:
		return [c for i, c in enumerate(self._orden) if self.lista.IsChecked(i)]

	def _actual(self) -> int:
		return self.lista.GetSelection()

	def _mostrar_ancho(self) -> None:
		i = self._actual()
		if 0 <= i < len(self._orden):
			self.campo_ancho.SetValue(self.anchos[self._orden[i]])

	def _guardar_ancho(self) -> None:
		i = self._actual()
		if 0 <= i < len(self._orden):
			self.anchos[self._orden[i]] = int(self.campo_ancho.GetValue())

	def _al_marcar(self, evento: wx.CommandEvent) -> None:
		indice = evento.GetInt()
		if self._orden[indice] == "nombre" and not self.lista.IsChecked(indice):
			self.lista.Check(indice, True)
			anuncios.anunciar(_("La columna Nombre no se puede quitar"), anuncios.RESULTADO)
		evento.Skip()

	# ── Acciones ─────────────────────────────────────────────────────────────

	def mover(self, paso: int) -> None:
		i = self._actual()
		destino = i + paso
		if i < 0 or not 0 <= destino < len(self._orden):
			return
		marcadas = set(self.elegidas())
		self._orden[i], self._orden[destino] = self._orden[destino], self._orden[i]
		self.lista.Set([titulo_columna(c) for c in self._orden])
		self._marcar(marcadas)
		self.lista.SetSelection(destino)
		self.lista.SetFocus()
		self._mostrar_ancho()
		anuncios.anunciar(_("{c}, posición {n} de {t}").format(c=titulo_columna(self._orden[destino]), n=destino + 1, t=len(self._orden)),
			anuncios.RESULTADO)

	def restablecer(self) -> None:
		self._orden = orden_inicial(self._fabrica)
		self.anchos = {c: ancho_fabrica(c) for c in self._orden}
		self.lista.Set([titulo_columna(c) for c in self._orden])
		self._marcar(self._fabrica)
		self.lista.SetSelection(0)
		self.lista.SetFocus()
		self._mostrar_ancho()
		anuncios.anunciar(_("Columnas de fábrica puestas; pulse Aceptar para aplicarlas"), anuncios.RESULTADO)

	def elegir_lectura(self) -> None:
		from app.ui.dialogos import pe_orden_lectura

		nueva = pe_orden_lectura.editar(self, self.elegidas(), self.lectura or [])
		if nueva is not None:
			self.lectura = nueva
		self.lista.SetFocus()

	def aceptar(self) -> bool:
		self._guardar_ancho()
		elegidas = self.elegidas()
		if "nombre" not in elegidas:
			elegidas.insert(0, "nombre")
		self.columnas = elegidas
		self.cerrar(wx.ID_OK)
		return True


def elegir_columnas(padre: wx.Window | None, titulo: str, visibles: Sequence[str], anchos: dict[str, int],
		fabrica: Sequence[str]) -> tuple[list[str], dict[str, int]] | None:
	dialogo = DialogoColumnas(padre, titulo, visibles, anchos, fabrica)
	return f_comun.mostrar(dialogo, lambda d: (d.columnas, dict(d.anchos)))
