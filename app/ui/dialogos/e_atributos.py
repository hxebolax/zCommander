# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo de atributos y fechas (sección 8.9).

Por qué está hecho así:

- Con varios elementos cada casilla tiene tres estados (marcada, sin marcar y a
  medias = «sin cambio»), que el lector anuncia de forma nativa; empieza en el
  estado común o a medias si difieren. Solo se aplican las casillas que la
  persona cambia: así una casilla sin tocar nunca se propaga a las subcarpetas.
- Las fechas son campos de texto «AAAA-MM-DD hh:mm:ss» (se leen y se corrigen
  carácter a carácter con cualquier lector, al contrario que los selectores de
  fecha), con una casilla «sin cambio» marcada de fábrica y un botón «Ahora».
- La fecha se valida al aceptar: si no se entiende, se dice por qué y el foco
  vuelve a ese campo con el texto intacto.
- Los permisos Unix (SFTP) solo aparecen en los orígenes que los admiten.
"""

from __future__ import annotations

import builtins
import logging
import time
from collections.abc import Sequence

import wx

from app.services import formato
from app.services.operaciones import atributos as at
from app.services.vfs import base
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _avisar(padre: wx.Window, mensaje: str, titulo: str) -> None:
	"""Muestra un error (las pruebas la sustituyen: no hay ShowModal real)."""
	dialogos.mostrar_error(padre, mensaje, titulo)


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


def etiquetas_atributos() -> list[tuple[int, str, str]]:
	"""(bit, etiqueta con letra, ayuda) en el orden del diálogo."""
	return [
		(formato.SOLO_LECTURA, _("Solo &lectura"), _("Los programas no pueden modificar el archivo.")),
		(formato.OCULTO, _("&Oculto"), _("No se muestra salvo que se pida ver los ocultos.")),
		(formato.SISTEMA, _("&Sistema"), _("Archivo del sistema operativo; normalmente también oculto.")),
		(formato.ARCHIVO, _("Archi&vo"), _("Pendiente de copia de seguridad.")),
		(formato.NO_INDEXAR, _("&No indexar el contenido"), _("La búsqueda de Windows no indexa su contenido.")),
	]


def _describir(entradas: Sequence[base.Entrada]) -> str:
	if len(entradas) == 1:
		return _("Atributos y fechas de «{n}».").format(n=entradas[0].nombre)
	carpetas = sum(1 for e in entradas if e.es_carpeta)
	return _("Atributos y fechas de {r}.").format(r=formato.recuento(carpetas, len(entradas) - carpetas))


class DialogoAtributos(wx.Dialog):
	"""Casillas de atributos, fechas de modificación y creación, permisos y recursión.

	:param atributos: el origen admite atributos de Windows.
	:param fechas: el origen admite cambiar la fecha de modificación.
	:param creacion: el origen admite cambiar la fecha de creación (solo disco local).
	:param permisos: el origen admite permisos Unix (SFTP).
	"""

	def __init__(self, padre: wx.Window | None, entradas: Sequence[base.Entrada], atributos: bool = True,
			fechas: bool = True, creacion: bool = True, permisos: bool = False) -> None:
		titulo = _("Atributos y fechas")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE, name=titulo)
		self.titulo = titulo
		self.entradas = [e for e in entradas if not e.es_superior]
		self.varios = len(self.entradas) > 1
		self.casillas: dict[int, wx.CheckBox] = {}
		self._iniciales: dict[int, int] = {}
		self.casilla_sin_modificacion = self.campo_modificacion = self.boton_ahora_modificacion = None
		self.casilla_sin_creacion = self.campo_creacion = self.boton_ahora_creacion = None
		self.campo_permisos = None
		self.casilla_recursivo = None

		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(panel, label=_describir(self.entradas)), 0, wx.ALL, 8)

		if atributos:
			caja = wx.StaticBoxSizer(wx.VERTICAL, panel, _("Atributos"))
			estilo = wx.CHK_3STATE | wx.CHK_ALLOW_3RD_STATE_FOR_USER if self.varios else wx.CHK_2STATE
			for bit, etiqueta, ayuda in etiquetas_atributos():
				casilla = wx.CheckBox(caja.GetStaticBox(), label=etiqueta, style=estilo)
				comun = at.estado_comun(self.entradas, bit)
				valor = wx.CHK_UNDETERMINED if comun is None else (wx.CHK_CHECKED if comun else wx.CHK_UNCHECKED)
				casilla.Set3StateValue(valor)
				self._iniciales[bit] = valor
				if self.varios:
					ayuda += " " + _("Marcada lo pone, sin marcar lo quita y a medias lo deja como está en cada elemento.")
				casilla.SetHelpText(ayuda)
				self.casillas[bit] = casilla
				caja.Add(casilla, 0, wx.ALL, 4)
			raiz.Add(caja, 0, wx.EXPAND | wx.ALL, 5)

		if fechas:
			caja = wx.StaticBoxSizer(wx.VERTICAL, panel, _("Fechas"))
			contenedor = caja.GetStaticBox()
			primera = self.entradas[0] if self.entradas else None
			self.casilla_sin_modificacion, self.campo_modificacion, self.boton_ahora_modificacion = self._fila_fecha(
				contenedor, caja, _("&Modificación sin cambio"), _("&Fecha de modificación:"), _("A&hora (modificación)"),
				primera.modificado if primera else 0.0)
			if creacion:
				self.casilla_sin_creacion, self.campo_creacion, self.boton_ahora_creacion = self._fila_fecha(
					contenedor, caja, _("Cr&eación sin cambio"), _("Fecha de creac&ión:"), _("Aho&ra (creación)"),
					primera.creado if primera else 0.0)
			raiz.Add(caja, 0, wx.EXPAND | wx.ALL, 5)

		if permisos:
			inicial = next((e.permisos for e in self.entradas if e.permisos >= 0), -1)
			_e, self.campo_permisos = crear_campo(panel, _("&Permisos (octal, por ejemplo 644):"), wx.TextCtrl,
				value=f"{inicial:03o}" if inicial >= 0 and len({e.permisos for e in self.entradas}) == 1 else "",
				ayuda=_("Permisos Unix del servidor en tres cifras: propietario, grupo y otros. Vacío: sin cambio."), sizer=raiz)

		if any(e.es_carpeta and not e.es_enlace for e in self.entradas):
			self.casilla_recursivo = wx.CheckBox(panel, label=_("Aplicar también a las s&ubcarpetas y su contenido"))
			self.casilla_recursivo.SetHelpText(_("Cambia también todo lo que hay dentro de las carpetas, sin entrar en enlaces ni uniones."))
			raiz.Add(self.casilla_recursivo, 0, wx.ALL, 8)

		raiz.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(raiz)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, self._al_aceptar)
		primero = next(iter(self.casillas.values()), None) or self.casilla_sin_modificacion or self.campo_permisos
		preparar_dialogo(self, foco_inicial=primero)
		self.CentreOnParent()

	def _fila_fecha(self, padre: wx.Window, sizer: wx.Sizer, texto_casilla: str, texto_campo: str, texto_ahora: str,
			marca: float) -> tuple[wx.CheckBox, wx.TextCtrl, wx.Button]:
		casilla = wx.CheckBox(padre, label=texto_casilla)
		casilla.SetValue(True)
		casilla.SetHelpText(_("Marcada, la fecha no se toca. Desmárquela para escribir una fecha nueva."))
		sizer.Add(casilla, 0, wx.ALL, 4)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		_e, campo = crear_campo(padre, texto_campo, wx.TextCtrl, value=at.texto_fecha(marca),
			size=padre.FromDIP(wx.Size(200, -1)), sizer=fila, horizontal=True, expandir=False,
			ayuda=_("Fecha y hora en la forma {f}, por ejemplo 2024-05-31 18:20:00.").format(f=at.FORMATO_VISIBLE))
		campo.Enable(False)
		boton = wx.Button(padre, label=texto_ahora)
		boton.SetHelpText(_("Pone la fecha y la hora actuales."))
		fila.Add(boton, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
		sizer.Add(fila, 0, wx.ALL, 0)
		casilla.Bind(wx.EVT_CHECKBOX, lambda _e: campo.Enable(not casilla.GetValue()))

		def ahora(_evento: wx.CommandEvent) -> None:
			casilla.SetValue(False)
			campo.Enable(True)
			campo.SetValue(at.texto_fecha(time.time()))
			campo.SetFocus()

		boton.Bind(wx.EVT_BUTTON, ahora)
		return casilla, campo, boton

	# ── Resultado ──────────────────────────────────────────────────────────────

	def _fecha(self, casilla: wx.CheckBox | None, campo: wx.TextCtrl | None) -> float | None:
		if casilla is None or campo is None or casilla.GetValue():
			return None
		return at.interpretar_fecha(campo.GetValue())

	def cambios(self) -> at.CambiosAtributos:
		"""Lo que hay que cambiar. :raises ValueError: si una fecha o los permisos no se entienden."""
		poner = quitar = 0
		for bit, casilla in self.casillas.items():
			valor = casilla.Get3StateValue()
			if valor == self._iniciales.get(bit):
				continue
			if valor == wx.CHK_CHECKED:
				poner |= bit
			elif valor == wx.CHK_UNCHECKED:
				quitar |= bit
		permisos = None
		if self.campo_permisos is not None and self.campo_permisos.GetValue().strip():
			permisos = at.interpretar_permisos(self.campo_permisos.GetValue())
		return at.CambiosAtributos(
			poner=poner, quitar=quitar,
			modificado=self._fecha(self.casilla_sin_modificacion, self.campo_modificacion),
			creado=self._fecha(self.casilla_sin_creacion, self.campo_creacion),
			permisos=permisos,
			recursivo=bool(self.casilla_recursivo is not None and self.casilla_recursivo.GetValue()),
		)

	def aceptar(self) -> bool:
		"""Cierra con Aceptar si todo se entiende; si no, dice qué falla y vuelve a ese campo."""
		for casilla, campo in ((self.casilla_sin_modificacion, self.campo_modificacion),
				(self.casilla_sin_creacion, self.campo_creacion), (None, self.campo_permisos)):
			if campo is None or (casilla is not None and casilla.GetValue()):
				continue
			try:
				if campo is self.campo_permisos:
					if campo.GetValue().strip():
						at.interpretar_permisos(campo.GetValue())
				else:
					at.interpretar_fecha(campo.GetValue())
			except ValueError as error:
				_avisar(self, str(error), self.titulo)
				campo.SetFocus()
				campo.SelectAll()
				return False
		_terminar(self, wx.ID_OK)
		return True

	def _al_aceptar(self, _evento: wx.CommandEvent) -> None:
		self.aceptar()


def pedir_atributos(padre: wx.Window | None, entradas: Sequence[base.Entrada], atributos: bool = True,
		fechas: bool = True, creacion: bool = True, permisos: bool = False) -> at.CambiosAtributos | None:
	"""Cambios que la persona aceptó, o ``None`` si cancela."""
	dialogo = DialogoAtributos(padre, entradas, atributos, fechas, creacion, permisos)
	foco_previo = wx.Window.FindFocus()
	try:
		return dialogo.cambios() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()
		if foco_previo:
			foco_previo.SetFocus()
