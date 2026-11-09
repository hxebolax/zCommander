# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Mapa de sonidos (diseño 2.0, 4.9): Ayuda → «Mapa de sonidos...» (orden ``mapa_sonidos``).

Sirve para aprender qué significa cada sonido y para comparar paquetes:
«Paquete:», «Categoría:» y una lista con las columnas Evento, Cuándo suena y
Estado («Activo» o «Desactivado»). Intro o «Reproducir» lo hacen sonar aunque
esté desactivado, con el paquete elegido en el diálogo; «Ir a las
preferencias» abre la página Sonidos con ese evento elegido.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

import wx

from app.services.sonidos import catalogo, paquetes
from app.ui import anuncios
from app.ui import sonidos as sonidos_ui
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.dialogos import so_comun, so_pagina_sonidos

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def filas(config: Any, categoria: str | None) -> list[tuple[str, list[str]]]:
	"""(id, [Evento, Cuándo suena, Estado]) de los eventos de la categoría (todas con ``None``)."""
	cambios = config.obtener("sonidos.eventos") or {}
	resultado = []
	for evento in catalogo.eventos():
		if categoria is not None and evento.categoria != categoria:
			continue
		activo = bool(cambios.get(evento.id, evento.por_defecto))
		cuando = _(evento.descripcion) if evento.descripcion else _("Lo decide el complemento")
		resultado.append((evento.id, [_(evento.nombre), cuando, _("Activo") if activo else _("Desactivado")]))
	return resultado


class DialogoMapa(wx.Dialog):
	"""Mapa de sonidos. ``resultado["evento"]`` queda con el evento elegido si se pidió ir a Preferencias.

	(Se devuelve en un diccionario del llamador porque el diálogo ya está destruido al volver de ``ShowModal``.)
	"""

	def __init__(self, padre: wx.Window | None, config: Any, resultado: dict[str, str | None] | None = None) -> None:
		super().__init__(padre, title=_("Mapa de sonidos"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=_("Mapa de sonidos"))
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.config = config
		self.resultado: dict[str, str | None] = resultado if resultado is not None else {}
		self._ids: list[str] = []
		self._paquetes = paquetes.listar()
		self._categorias = so_pagina_sonidos.categorias()
		panel = wx.Panel(self)
		self.panel = panel
		sizer = wx.BoxSizer(wx.VERTICAL)
		borde = self.FromDIP(4)

		etiqueta_paquete = wx.StaticText(panel, label=_("&Paquete:"))
		self.paquete = wx.Choice(panel, choices=[p.etiqueta for p in self._paquetes])
		elegido = str(config.obtener("sonidos.paquete") or paquetes.BASE)
		indices = [i for i, p in enumerate(self._paquetes) if p.id == elegido]
		if self._paquetes:
			self.paquete.SetSelection(indices[0] if indices else 0)
		self.paquete.SetHelpText(_("Paquete con el que suenan los sonidos al reproducirlos aquí (no cambia el paquete en uso)."))
		sizer.Add(etiqueta_paquete, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.paquete, 0, wx.EXPAND | wx.ALL, borde)

		etiqueta_categoria = wx.StaticText(panel, label=_("Ca&tegoría:"))
		self.categoria = wx.Choice(panel, choices=[_("Todas")] + [n for _c, n in self._categorias])
		self.categoria.SetSelection(0)
		self.categoria.SetHelpText(_("Filtra la lista por categoría."))
		self.categoria.Bind(wx.EVT_CHOICE, lambda _e: self.rellenar())
		sizer.Add(etiqueta_categoria, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.categoria, 0, wx.EXPAND | wx.ALL, borde)

		etiqueta_lista = wx.StaticText(panel, label=_("&Sonidos:"))
		self.lista = ListaAccesible(panel, _("Sonidos"), columnas=[
			(_("Evento"), self.FromDIP(200)), (_("Cuándo suena"), self.FromDIP(360)), (_("Estado"), self.FromDIP(100)),
		])
		self.lista.SetMinSize(self.FromDIP(wx.Size(660, 300)))
		self.lista.SetHelpText(_("Intro reproduce el sonido elegido. Izquierda y Derecha leen las columnas: evento, cuándo suena y estado."))
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.reproducir())
		sizer.Add(etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, borde)

		fila = wx.BoxSizer(wx.HORIZONTAL)
		so_comun.boton(panel, _("&Reproducir"), _("Hace sonar el sonido elegido con el paquete elegido, aunque esté desactivado."),
			self.reproducir, fila)
		so_comun.boton(panel, _("Ir a las pre&ferencias"), _("Cierra el mapa y abre Preferencias, Sonidos, con este sonido elegido."),
			self.preferencias, fila)
		cerrar = wx.Button(panel, wx.ID_CANCEL, _("&Cerrar"))
		cerrar.SetHelpText(_("Cierra el mapa de sonidos."))
		fila.Add(cerrar, 0, wx.ALL, self.FromDIP(3))
		sizer.Add(fila, 0)
		panel.SetSizer(sizer)
		externo = wx.BoxSizer(wx.VERTICAL)
		externo.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(externo)
		preparar_dialogo(self, id_escape=wx.ID_CANCEL, foco_inicial=self.lista)
		self.rellenar()

	def rellenar(self) -> None:
		actual = self.evento_elegido()
		indice = self.categoria.GetSelection()
		categoria = self._categorias[indice - 1][0] if indice > 0 else None
		datos = filas(self.config, categoria)
		self._ids = [id_ for id_, _f in datos]
		self.lista.reemplazar_filas([f for _id, f in datos], conservar_foco=False)
		if self._ids:
			self.lista.enfocar_fila(self._ids.index(actual) if actual in self._ids else 0, anunciar=False)

	def evento_elegido(self) -> str | None:
		fila = self.lista.fila_actual() if self._ids else -1
		return self._ids[fila] if 0 <= fila < len(self._ids) else None

	def paquete_elegido(self) -> str:
		indice = self.paquete.GetSelection()
		return self._paquetes[indice].id if 0 <= indice < len(self._paquetes) else paquetes.BASE

	def reproducir(self) -> bool:
		id_evento = self.evento_elegido()
		if id_evento is None:
			return False
		sonado = sonidos_ui.probar(id_evento, paquete=self.paquete_elegido())
		if not sonado:
			evento = catalogo.evento(id_evento)
			anuncios.anunciar(_("No suena «{n}»: el volumen está a 0 o el paquete no tiene ese sonido").format(
				n=_(evento.nombre) if evento else id_evento), anuncios.RESULTADO)
		return sonado

	def preferencias(self) -> None:
		self.resultado["evento"] = self.evento_elegido()
		if self.IsModal():
			self.EndModal(wx.ID_OK)


def abrir(padre: wx.Window | None, config: Any) -> None:
	"""Muestra el mapa; si se pide, abre después Preferencias en la página Sonidos con el evento elegido."""
	resultado: dict[str, str | None] = {}
	so_comun.mostrar_modal(DialogoMapa(padre, config, resultado))
	evento = resultado.get("evento")
	if evento:
		so_pagina_sonidos.EVENTO_INICIAL[0] = evento
		from app.ui.dialogos import f_preferencias

		wx.CallAfter(f_preferencias.abrir, padre, config, "Sonidos")
