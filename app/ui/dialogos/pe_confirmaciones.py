# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Página «Confirmaciones» de Preferencias (diseño 2.0, 10.12; página propia de ``paginas_propias``).

Lista con casillas de las confirmaciones silenciables (``app.services.confirmaciones``):
marcada = se pregunta; desmarcada = no se pregunta («No volver a preguntar»).
«Volver a preguntar todas» las marca. Nada se escribe hasta Aceptar o Aplicar
(``aplicar``); Cancelar no toca ``general.no_preguntar``.

Las que protegen de perder datos o de ejecutar código (eliminar
definitivamente, restaurar, instalar un complemento sin firma...) no están en
la lista: no se pueden silenciar.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

import wx

from app.services import confirmaciones
from app.ui import anuncios
from app.ui.accesibilidad.casillas import CheckListBoxAccesible

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class PaginaConfirmaciones(wx.Panel):
	"""Cumple ``PaginaPropia`` (validar, aplicar, restablecer, control_inicial)."""

	def __init__(self, padre: wx.Window, config: Any) -> None:
		super().__init__(padre, name=_("Confirmaciones"))
		self.config = config
		self.ids = list(confirmaciones.CONFIRMACIONES)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.etiqueta = wx.StaticText(self, label=_("Confirmaciones que se &hacen (desmarcada: no se pregunta):"))
		self.lista = CheckListBoxAccesible(self, _("Confirmaciones que se hacen"),
			[_(confirmaciones.CONFIRMACIONES[i].etiqueta) for i in self.ids], recordar_posicion=False)
		self.lista.SetHelpText(_("Marcada: zCommander pregunta. Desmarcada: no vuelve a preguntar. Las que evitan perder datos "
			"o ejecutar programas no están aquí: siempre se preguntan."))
		self.lista.Bind(wx.EVT_LISTBOX, lambda _e: self._ayuda_elegida())
		self.boton_todas = wx.Button(self, label=_("Volver a preguntar &todas"))
		self.boton_todas.SetHelpText(_("Marca todas: zCommander volverá a preguntar cada una."))
		self.boton_todas.Bind(wx.EVT_BUTTON, lambda _e: self.restablecer(anunciar=True))
		sizer.Add(self.etiqueta, 0, wx.ALL, self.FromDIP(5))
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		sizer.Add(self.boton_todas, 0, wx.ALL, self.FromDIP(5))
		self.SetSizer(sizer)
		self._cargar()
		if self.ids:
			self.lista.SetSelection(0)
			self._ayuda_elegida()

	def _cargar(self) -> None:
		for indice, id_confirmacion in enumerate(self.ids):
			self.lista.Check(indice, confirmaciones.debe_preguntar(self.config, id_confirmacion))

	def _ayuda_elegida(self) -> None:
		indice = self.lista.GetSelection()
		if 0 <= indice < len(self.ids):
			confirmacion = confirmaciones.CONFIRMACIONES[self.ids[indice]]
			self.lista.SetHelpText(f"{_(confirmacion.etiqueta)}. {_(confirmacion.ayuda)}")

	def silenciadas(self) -> list[str]:
		"""Lo que se guardaría en ``general.no_preguntar`` (las variantes «id:sitio» de las aún silenciadas se conservan)."""
		actuales = [str(c) for c in (self.config.obtener(confirmaciones.CLAVE) or [])]
		resultado: list[str] = []
		for indice, id_confirmacion in enumerate(self.ids):
			if self.lista.IsChecked(indice):
				continue
			resultado.append(id_confirmacion)
		for valor in actuales:
			base = valor.split(":", 1)[0]
			if ":" in valor and base in self.ids and not self.lista.IsChecked(self.ids.index(base)) and valor not in resultado:
				resultado.append(valor)
		return resultado

	# Protocolo PaginaPropia ---------------------------------------------------

	def validar(self) -> str | None:
		return None

	def aplicar(self) -> bool:
		nuevas = self.silenciadas()
		# Las variantes «id:sitio» de una confirmación marcada (se pregunta) se quitan: vuelve a preguntar en todos los sitios.
		marcadas = {i for n, i in enumerate(self.ids) if self.lista.IsChecked(n)}
		actuales = [str(c) for c in (self.config.obtener(confirmaciones.CLAVE) or [])]
		ajenas = [c for c in actuales if c.split(":", 1)[0] not in self.ids]
		valor = [*nuevas, *[c for c in ajenas if c not in nuevas]]
		valor = [c for c in valor if c.split(":", 1)[0] not in marcadas]
		if valor != actuales:
			try:
				self.config.establecer(confirmaciones.CLAVE, valor)
			except Exception:  # noqa: BLE001 - ErrorConfiguracion u OSError: el diálogo lo dice
				log.exception("No se pudieron guardar las confirmaciones")
				return False
		return True

	def restablecer(self, anunciar: bool = False) -> None:
		self.lista.marcar_todas(True)
		if anunciar:
			anuncios.anunciar(_("Se volverá a preguntar todo. Pulse Aceptar para guardarlo."), anuncios.RESULTADO)

	def control_inicial(self) -> wx.Window:
		return self.lista


def crear(padre: wx.Window, config: Any) -> PaginaConfirmaciones:
	"""Fábrica de la página propia Confirmaciones (``PAGINAS_PROPIAS``)."""
	return PaginaConfirmaciones(padre, config)
