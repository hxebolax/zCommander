# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Editor de asociaciones: qué orden abre (Intro), ve (F3) o edita (F4) cada tipo de archivo.

Las reglas se miran en orden y gana la primera que coincide (``asociaciones.orden_para``,
del núcleo): por eso el editor tiene Subir y Bajar, y la lista se lee como una
tabla (Patrón, Abrir, Ver, Editar) con la lectura por columnas de
``ListaAccesible``. Un campo vacío es «lo de siempre» y así se lee, en vez de
una celda vacía que el lector diría «en blanco».
"""

from __future__ import annotations

import builtins
import copy
import logging

import wx

from app.services.asociaciones import Regla
from app.ui import anuncios
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


AYUDA_ORDEN = (
	"Programa y argumentos, por ejemplo notepad++.exe %P. Se lanza sin cmd. Variables: %P ruta completa, %N nombre, "
	"%B nombre sin extensión, %E extensión, %D carpeta, %O carpeta del otro panel, %T ruta del cursor del otro panel. "
	"Vacío: lo que hace zCommander por defecto."
)


def _celda(texto: str) -> str:
	return texto or _("(por defecto)")


class DialogoRegla(f_comun.DialogoF):
	"""Patrón y las tres órdenes de una regla."""

	def __init__(self, padre: wx.Window | None, regla: Regla, nueva: bool) -> None:
		super().__init__(padre, _("Nueva asociación") if nueva else _("Editar la asociación"))
		self.regla = copy.deepcopy(regla)
		ancho = self.FromDIP(wx.Size(440, -1))
		_p, self.campo_patron = crear_campo(self.panel, _("&Patrón:"), wx.TextCtrl, value=regla.patron, size=ancho,
			ayuda=_("Tipos de archivo, por ejemplo *.txt;*.md. Exclusiones tras |."), sizer=self.sizer)
		_a, self.campo_abrir = crear_campo(self.panel, _("Orden para a&brir (Intro):"), wx.TextCtrl, value=regla.abrir, size=ancho,
			ayuda=_(AYUDA_ORDEN), sizer=self.sizer)
		_v, self.campo_ver = crear_campo(self.panel, _("Orden para &ver (F3):"), wx.TextCtrl, value=regla.ver, size=ancho,
			ayuda=_(AYUDA_ORDEN), sizer=self.sizer)
		_e, self.campo_editar = crear_campo(self.panel, _("Orden para &editar (F4):"), wx.TextCtrl, value=regla.editar, size=ancho,
			ayuda=_(AYUDA_ORDEN), sizer=self.sizer)
		self.terminar(wx.OK | wx.CANCEL, foco=self.campo_patron)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())

	def aceptar(self) -> bool:
		patron = self.campo_patron.GetValue().strip()
		if not patron.replace(";", "").strip():
			f_comun.avisar(self, _("Escriba un patrón, por ejemplo *.txt"), self.titulo)
			self.campo_patron.SetFocus()
			return False
		ordenes = [c.GetValue().strip() for c in (self.campo_abrir, self.campo_ver, self.campo_editar)]
		if not any(ordenes):
			f_comun.avisar(self, _("Escriba al menos una orden: para abrir, ver o editar."), self.titulo)
			self.campo_abrir.SetFocus()
			return False
		self.regla = Regla(patron, *ordenes)
		self.cerrar(wx.ID_OK)
		return True


class DialogoAsociaciones(f_comun.DialogoF):
	"""Lista ordenada de reglas con Nueva, Editar, Eliminar, Subir y Bajar. ``reglas`` es el resultado."""

	def __init__(self, padre: wx.Window | None, reglas: list[Regla]) -> None:
		super().__init__(padre, _("Asociaciones"))
		self.reglas = copy.deepcopy(reglas)
		self.etiqueta_lista = wx.StaticText(self.panel, label=_("&Reglas (gana la primera que coincide):"))
		self.lista = ListaAccesible(self.panel, f_comun.texto_limpio(self.etiqueta_lista.GetLabel()), columnas=[
			(_("Patrón"), self.FromDIP(140)), (_("Abrir"), self.FromDIP(150)), (_("Ver"), self.FromDIP(150)), (_("Editar"), self.FromDIP(150)),
		])
		self.lista.SetMinSize(self.FromDIP(wx.Size(600, 220)))
		self.sizer.Add(self.etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton(_("&Nueva..."), _("Añade una regla después de la elegida."), self.nueva, fila)
		self.boton(_("E&ditar..."), _("Cambia la regla elegida."), self.editar, fila)
		self.boton(_("E&liminar"), _("Quita la regla elegida; pide confirmación."), self.eliminar, fila)
		self.boton(_("&Subir"), _("Sube la regla: se mira antes que las de debajo."), lambda: self.mover(-1), fila)
		self.boton(_("&Bajar"), _("Baja la regla una posición."), lambda: self.mover(1), fila)
		self.sizer.Add(fila, 0)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.editar())
		self.terminar(wx.OK | wx.CANCEL, foco=self.lista)
		self._rellenar(0)

	def _rellenar(self, foco: int) -> None:
		self.lista.reemplazar_filas([[r.patron, _celda(r.abrir), _celda(r.ver), _celda(r.editar)] for r in self.reglas],
			conservar_foco=False)
		if self.reglas:
			self.lista.enfocar_fila(min(max(foco, 0), len(self.reglas) - 1), anunciar=False)

	def indice(self) -> int:
		fila = self.lista.fila_actual()
		return fila if 0 <= fila < len(self.reglas) else -1

	def nueva(self) -> None:
		regla = f_comun.mostrar(DialogoRegla(self, Regla(""), True), lambda d: d.regla)
		if regla is None:
			return
		posicion = self.indice() + 1 if self.indice() >= 0 else len(self.reglas)
		self.reglas.insert(posicion, regla)
		self._rellenar(posicion)
		self.lista.SetFocus()

	def editar(self) -> None:
		i = self.indice()
		if i < 0:
			return
		regla = f_comun.mostrar(DialogoRegla(self, self.reglas[i], False), lambda d: d.regla)
		if regla is not None:
			self.reglas[i] = regla
			self._rellenar(i)
		self.lista.SetFocus()

	def eliminar(self) -> None:
		i = self.indice()
		if i < 0:
			return
		if not f_comun.preguntar(self, _("¿Quitar la asociación de {p}?").format(p=self.reglas[i].patron), _("Eliminar"), peligroso=True):
			return
		del self.reglas[i]
		self._rellenar(i)
		self.lista.SetFocus()

	def mover(self, paso: int) -> None:
		i = self.indice()
		destino = i + paso
		if i < 0 or not 0 <= destino < len(self.reglas):
			return
		self.reglas[i], self.reglas[destino] = self.reglas[destino], self.reglas[i]
		self._rellenar(destino)
		self.lista.SetFocus()
		anuncios.anunciar(_("Posición {n} de {t}").format(n=destino + 1, t=len(self.reglas)), anuncios.RESULTADO)


def editar_asociaciones(padre: wx.Window | None, reglas: list[Regla]) -> list[Regla] | None:
	return f_comun.mostrar(DialogoAsociaciones(padre, reglas), lambda d: d.reglas)
