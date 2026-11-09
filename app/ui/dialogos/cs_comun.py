# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Piezas comunes de los diálogos de copias y perfiles (bloque CS, diseño 2.0, 7.5, 7.6 y 10.2).

Los avisos, las preguntas y los cuadros de elegir archivo pasan por las
funciones de ESTE módulo: las pruebas las sustituyen y ningún ``ShowModal``
real llega a la pantalla (el ``conftest`` lo prohíbe).
"""

from __future__ import annotations

import builtins
import logging
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import wx

from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.dialogos import ETIQUETAS, preparar_dialogo
from app.ui.dialogos.f_comun import DialogoF

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


COMODIN_COPIA = "Copias de zCommander (*.zcbackup)|*.zcbackup|Todos los archivos (*.*)|*.*"
COMODIN_PERFIL = "Perfiles de zCommander (*.zcperfil)|*.zcperfil|Todos los archivos (*.*)|*.*"


# ── Avisos y preguntas (sustituibles en las pruebas) ──────────────────────────

def avisar(padre: wx.Window | None, texto: str, titulo: str = "") -> None:
	dialogos.mostrar_mensaje(padre, texto, titulo or _("Aviso"), icono=wx.ICON_WARNING)


def informar(padre: wx.Window | None, texto: str, titulo: str = "") -> None:
	dialogos.mostrar_mensaje(padre, texto, titulo or _("Información"))


def elegir(padre: wx.Window | None, texto: str, titulo: str, opciones: Sequence[str]) -> int | None:
	"""Botones que dicen la acción; el primero es el predeterminado. ``None`` si se cancela."""
	return dialogos.elegir_opcion(padre, texto, titulo, opciones)


def preguntar(padre: wx.Window | None, texto: str, titulo: str = "", peligroso: bool = True) -> bool:
	return dialogos.confirmar(padre, texto, titulo or _("Confirmación"), peligroso=peligroso) == wx.ID_YES


def elegir_archivo_abrir(padre: wx.Window | None, titulo: str, comodin: str, inicial: str = "") -> str | None:
	carpeta, nombre = (str(Path(inicial).parent), Path(inicial).name) if inicial else ("", "")
	dialogo = wx.FileDialog(padre, titulo, carpeta, nombre, comodin, wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
	try:
		return dialogo.GetPath() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def elegir_archivo_guardar(padre: wx.Window | None, titulo: str, comodin: str, inicial: str = "") -> str | None:
	carpeta, nombre = (str(Path(inicial).parent), Path(inicial).name) if inicial else ("", "")
	dialogo = wx.FileDialog(padre, titulo, carpeta, nombre, comodin, wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
	try:
		return dialogo.GetPath() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def elegir_carpeta(padre: wx.Window | None, titulo: str, inicial: str = "") -> str | None:
	dialogo = wx.DirDialog(padre, titulo, inicial, wx.DD_DEFAULT_STYLE)
	try:
		return dialogo.GetPath() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def en_hilo(funcion: Callable[[], Any], al_terminar: Callable[[Any, BaseException | None], None]) -> threading.Thread:
	"""Trabajo pesado (abrir y comprobar una copia, scrypt) fuera del hilo de la interfaz.

	``al_terminar(resultado, error)`` se llama en el hilo de la interfaz con ``wx.CallAfter``.
	"""

	def trabajo() -> None:
		try:
			resultado, error = funcion(), None
		except BaseException as fallo:  # noqa: BLE001 - se entrega al hilo de la interfaz
			resultado, error = None, fallo
			if not isinstance(fallo, Exception):
				raise
		wx.CallAfter(al_terminar, resultado, error)

	hilo = threading.Thread(target=trabajo, name="copia-cs", daemon=True)
	hilo.start()
	return hilo


# ── Diálogo base ──────────────────────────────────────────────────────────────

class DialogoCS(DialogoF):
	"""Diálogo con botón de acción propio («Crear la copia», «Restaurar») y «Cancelar»."""

	def lista_casillas(self, etiqueta: str, nombre: str, opciones: Sequence[str] = (), ayuda: str = "",
			alto: int = 120) -> CheckListBoxAccesible:
		"""Etiqueta creada ANTES que la lista, con el mismo padre (así el lector la lee)."""
		self.sizer.Add(wx.StaticText(self.panel, label=etiqueta), 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		lista = CheckListBoxAccesible(self.panel, nombre, opciones, size=self.FromDIP(wx.Size(520, alto)))
		if ayuda:
			lista.SetHelpText(lista.GetHelpText() + " " + ayuda)
		self.sizer.Add(lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.FromDIP(5))
		return lista

	def texto_solo_lectura(self, etiqueta: str, alto: int = 110, ayuda: str = "") -> wx.TextCtrl:
		self.sizer.Add(wx.StaticText(self.panel, label=etiqueta), 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		campo = wx.TextCtrl(self.panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
			size=self.FromDIP(wx.Size(520, alto)), name=etiqueta.replace("&", "").rstrip(":"))
		campo.SetHelpText(ayuda or _("Texto de solo lectura. Recórralo con las flechas; puede copiarlo."))
		self.sizer.Add(campo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.FromDIP(5))
		return campo

	def terminar_con_accion(self, etiqueta_accion: str, ayuda_accion: str, al_aceptar: Callable[[], None],
			foco: wx.Window | None = None, cancelar_predeterminado: bool = False) -> wx.Button:
		"""Botones «acción» y «Cancelar»; con ``cancelar_predeterminado``, Intro cancela (acciones arriesgadas, 15.1)."""
		botonera = wx.StdDialogButtonSizer()
		self.boton_accion = wx.Button(self.panel, wx.ID_OK, etiqueta_accion)
		self.boton_accion.SetHelpText(ayuda_accion)
		self.boton_accion.Bind(wx.EVT_BUTTON, lambda _evento: al_aceptar())
		cancelar = wx.Button(self.panel, wx.ID_CANCEL, _(ETIQUETAS[wx.ID_CANCEL]))
		cancelar.SetHelpText(_("Cierra sin hacer nada."))
		botonera.AddButton(self.boton_accion)
		botonera.AddButton(cancelar)
		botonera.Realize()
		(cancelar if cancelar_predeterminado else self.boton_accion).SetDefault()
		self.sizer.Add(botonera, 0, wx.ALIGN_RIGHT | wx.ALL, self.FromDIP(8))
		self.panel.SetSizer(self.sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(self.panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		preparar_dialogo(self, id_escape=wx.ID_CANCEL, foco_inicial=foco)
		self.CentreOnParent()
		return self.boton_accion


def marcados(lista: wx.CheckListBox, ids: Sequence[str]) -> list[str]:
	return [ids[i] for i in range(min(lista.GetCount(), len(ids))) if lista.IsChecked(i)]
