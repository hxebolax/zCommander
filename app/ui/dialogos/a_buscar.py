# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de búsqueda del visor y del editor (bloque A): buscar, reemplazar e ir a línea.

Por qué están hechos así:

- La búsqueda se describe con ``OpcionesBusqueda`` y se compila con
  ``compilar`` (funciones puras): el visor, el editor y las pruebas usan la
  misma regla para «palabra completa» y «distinguir mayúsculas».
- «Palabra completa» usa ``(?<!\\w)`` y ``(?!\\w)`` en lugar de ``\\b``: así
  también funciona con textos que empiezan o terminan con un signo.
- Se valida al pulsar Aceptar, no a cada tecla: si la expresión regular no
  vale o el número de línea está fuera de rango, se dice por qué y el foco
  vuelve al campo con su contenido seleccionado.
- Reemplazar es NO modal (como el Bloc de notas): hay que poder ir del
  diálogo al texto y volver. Los botones dicen la acción y el resultado se
  anuncia («3 reemplazos», «No se encontró»).
- Las últimas opciones se recuerdan en ``ULTIMA`` para que F3 en otra
  ventana del visor o del editor repita la misma búsqueda.
"""

from __future__ import annotations

import builtins
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace

import wx

from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class OpcionesBusqueda:
	"""Qué se busca y cómo."""

	texto: str = ""
	mayusculas: bool = False
	palabra: bool = False
	regex: bool = False
	atras: bool = False

	def hacia(self, atras: bool) -> OpcionesBusqueda:
		"""Las mismas opciones en la otra dirección (F3 y Mayús+F3)."""
		return replace(self, atras=atras)


#: Última búsqueda de cualquier visor o editor (para F3 sin haber abierto el diálogo).
ULTIMA: list[OpcionesBusqueda] = [OpcionesBusqueda()]


def compilar(opciones: OpcionesBusqueda) -> re.Pattern[str]:
	"""Expresión regular de la búsqueda. Lanza ``re.error`` si la expresión escrita no vale."""
	cuerpo = opciones.texto if opciones.regex else re.escape(opciones.texto)
	if opciones.palabra:
		cuerpo = rf"(?<!\w)(?:{cuerpo})(?!\w)"
	banderas = re.MULTILINE | (0 if opciones.mayusculas else re.IGNORECASE)
	return re.compile(cuerpo, banderas)


def compilar_bytes(opciones: OpcionesBusqueda, codec: str) -> re.Pattern[bytes]:
	"""La misma búsqueda sobre bytes (modo hexadecimal): el texto codificado con ``codec``.

	En bytes, «distinguir mayúsculas» solo afecta a las letras ASCII.
	"""
	try:
		datos = opciones.texto.encode(codec)
	except (UnicodeEncodeError, LookupError):
		datos = opciones.texto.encode("utf-8")
	cuerpo = datos if opciones.regex else re.escape(datos)
	if opciones.palabra:
		cuerpo = rb"(?<![A-Za-z0-9_])(?:" + cuerpo + rb")(?![A-Za-z0-9_])"
	return re.compile(cuerpo, 0 if opciones.mayusculas else re.IGNORECASE)


def buscar_en(texto: str, patron: re.Pattern[str], desde: int, atras: bool, envolver: bool = True) -> tuple[int, int, bool] | None:
	"""Busca en un texto en memoria: (inicio, fin, dio_la_vuelta) o ``None``.

	:param desde: hacia delante, primera posición donde puede empezar; hacia
		atrás, la coincidencia debe empezar antes de esta posición.
	:param envolver: si no hay más, sigue desde el otro extremo.
	"""
	if atras:
		ultima = None
		for coincidencia in patron.finditer(texto, 0, len(texto)):
			if coincidencia.start() >= desde:
				break
			if coincidencia.end() > coincidencia.start():
				ultima = coincidencia
		if ultima is not None:
			return ultima.start(), ultima.end(), False
		if envolver:
			ultima = None
			for coincidencia in patron.finditer(texto, desde):
				if coincidencia.end() > coincidencia.start():
					ultima = coincidencia
			if ultima is not None:
				return ultima.start(), ultima.end(), True
		return None
	for coincidencia in patron.finditer(texto, desde):
		if coincidencia.end() > coincidencia.start():
			return coincidencia.start(), coincidencia.end(), False
	if envolver:
		for coincidencia in patron.finditer(texto, 0):
			if coincidencia.start() >= desde:
				break
			if coincidencia.end() > coincidencia.start():
				return coincidencia.start(), coincidencia.end(), True
	return None


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	"""``EndModal`` si es modal; si no (pruebas sin ``ShowModal``), solo deja el código."""
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


def _marcar_campo(campo: wx.TextCtrl) -> None:
	campo.SetFocus()
	campo.SelectAll()


# ── Buscar ───────────────────────────────────────────────────────────────────


class DialogoBuscar(wx.Dialog):
	"""Buscar (F7 o Ctrl+F). ``ShowModal`` devuelve ``wx.ID_OK`` solo con una búsqueda válida."""

	def __init__(self, padre: wx.Window | None, opciones: OpcionesBusqueda, titulo: str = "") -> None:
		titulo = titulo or _("Buscar")
		super().__init__(padre, title=titulo, name=titulo)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.campo = crear_campo(panel, _("&Buscar:"), wx.TextCtrl, value=opciones.texto, size=panel.FromDIP(wx.Size(360, -1)),
			ayuda=_("Texto que se busca. Con «Expresión regular», una expresión de Python."), sizer=sizer)
		self.casilla_mayusculas = wx.CheckBox(panel, label=_("&Distinguir mayúsculas y minúsculas"))
		self.casilla_mayusculas.SetValue(opciones.mayusculas)
		self.casilla_mayusculas.SetHelpText(_("Si se marca, «Hola» no coincide con «hola»."))
		self.casilla_palabra = wx.CheckBox(panel, label=_("Solo la &palabra completa"))
		self.casilla_palabra.SetValue(opciones.palabra)
		self.casilla_palabra.SetHelpText(_("Si se marca, «sol» no coincide dentro de «soldado»."))
		self.casilla_regex = wx.CheckBox(panel, label=_("E&xpresión regular"))
		self.casilla_regex.SetValue(opciones.regex)
		self.casilla_regex.SetHelpText(_("El texto es una expresión regular de Python (por ejemplo «^Capítulo \\d+»)."))
		self.casilla_atras = wx.CheckBox(panel, label=_("Buscar hacia a&trás"))
		self.casilla_atras.SetValue(opciones.atras)
		self.casilla_atras.SetHelpText(_("Busca desde el cursor hacia el principio. Mayús+F3 busca siempre hacia atrás."))
		for casilla in (self.casilla_mayusculas, self.casilla_palabra, self.casilla_regex, self.casilla_atras):
			sizer.Add(casilla, 0, wx.ALL, 5)
		sizer.Add(dialogos.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		dialogos.preparar_dialogo(self, foco_inicial=self.campo)
		self.CentreOnParent()

	def opciones(self) -> OpcionesBusqueda:
		return OpcionesBusqueda(
			texto=self.campo.GetValue(), mayusculas=self.casilla_mayusculas.GetValue(),
			palabra=self.casilla_palabra.GetValue(), regex=self.casilla_regex.GetValue(), atras=self.casilla_atras.GetValue(),
		)

	def problema(self) -> str | None:
		"""Motivo por el que no se puede buscar, o ``None``."""
		opciones = self.opciones()
		if not opciones.texto:
			return _("Escriba el texto que quiere buscar.")
		try:
			compilar(opciones)
		except re.error as error:
			return _("La expresión regular no es válida: {e}").format(e=error)
		return None

	def aceptar(self) -> bool:
		problema = self.problema()
		if problema:
			dialogos.mostrar_error(self, problema)
			_marcar_campo(self.campo)
			return False
		ULTIMA[0] = self.opciones()
		_terminar(self, wx.ID_OK)
		return True

	def _al_aceptar(self, _evento: wx.CommandEvent) -> None:
		self.aceptar()


def pedir_busqueda(padre: wx.Window, titulo: str = "") -> OpcionesBusqueda | None:
	"""Muestra «Buscar» con las últimas opciones; devuelve las elegidas o ``None``."""
	dialogo = DialogoBuscar(padre, ULTIMA[0], titulo)
	try:
		return dialogo.opciones() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


# ── Reemplazar ───────────────────────────────────────────────────────────────


class DialogoReemplazar(wx.Dialog):
	"""Reemplazar (Ctrl+R en el editor), no modal.

	:param al_buscar: ``al_buscar(opciones) -> bool``: busca y selecciona la siguiente.
	:param al_reemplazar: ``al_reemplazar(opciones, nuevo) -> bool``: reemplaza la
		selección si coincide y busca la siguiente.
	:param al_reemplazar_todo: ``al_reemplazar_todo(opciones, nuevo) -> int``.
	:param al_cerrar: se llama al cerrarse (para devolver el foco al texto).
	"""

	def __init__(self, padre: wx.Window, opciones: OpcionesBusqueda, reemplazo: str,
			al_buscar: Callable[[OpcionesBusqueda], bool],
			al_reemplazar: Callable[[OpcionesBusqueda, str], bool],
			al_reemplazar_todo: Callable[[OpcionesBusqueda, str], int],
			al_cerrar: Callable[[], None] | None = None) -> None:
		titulo = _("Reemplazar")
		super().__init__(padre, title=titulo, name=titulo)
		self._al_buscar = al_buscar
		self._al_reemplazar = al_reemplazar
		self._al_reemplazar_todo = al_reemplazar_todo
		self._al_cerrar = al_cerrar
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.campo = crear_campo(panel, _("&Buscar:"), wx.TextCtrl, value=opciones.texto, size=panel.FromDIP(wx.Size(360, -1)),
			ayuda=_("Texto que se busca."), sizer=sizer)
		_etiqueta, self.campo_nuevo = crear_campo(panel, _("Ree&mplazar por:"), wx.TextCtrl, value=reemplazo,
			ayuda=_("Texto que se pone en lugar del encontrado. Con expresión regular admite \\1, \\2..."), sizer=sizer)
		self.casilla_mayusculas = wx.CheckBox(panel, label=_("&Distinguir mayúsculas y minúsculas"))
		self.casilla_mayusculas.SetValue(opciones.mayusculas)
		self.casilla_palabra = wx.CheckBox(panel, label=_("Solo la &palabra completa"))
		self.casilla_palabra.SetValue(opciones.palabra)
		self.casilla_regex = wx.CheckBox(panel, label=_("E&xpresión regular"))
		self.casilla_regex.SetValue(opciones.regex)
		for casilla in (self.casilla_mayusculas, self.casilla_palabra, self.casilla_regex):
			sizer.Add(casilla, 0, wx.ALL, 5)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_buscar = wx.Button(panel, label=_("Buscar &siguiente"))
		self.boton_buscar.SetHelpText(_("Selecciona en el texto la siguiente coincidencia."))
		self.boton_reemplazar = wx.Button(panel, label=_("&Reemplazar"))
		self.boton_reemplazar.SetHelpText(_("Reemplaza la coincidencia seleccionada y busca la siguiente."))
		self.boton_todo = wx.Button(panel, label=_("Reemplazar &todo"))
		self.boton_todo.SetHelpText(_("Reemplaza todas las coincidencias del texto. Se puede deshacer con Ctrl+Z."))
		self.boton_cerrar = wx.Button(panel, wx.ID_CANCEL, _("C&errar"))
		self.boton_cerrar.SetHelpText(_("Cierra este cuadro y vuelve al texto."))
		for boton in (self.boton_buscar, self.boton_reemplazar, self.boton_todo, self.boton_cerrar):
			botones.Add(boton, 0, wx.ALL, 5)
		self.boton_buscar.SetDefault()
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.boton_buscar.Bind(wx.EVT_BUTTON, lambda _e: self.buscar())
		self.boton_reemplazar.Bind(wx.EVT_BUTTON, lambda _e: self.reemplazar())
		self.boton_todo.Bind(wx.EVT_BUTTON, lambda _e: self.reemplazar_todo())
		self.boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.Close())
		self.Bind(wx.EVT_CLOSE, self._al_cerrar_ventana)
		dialogos.preparar_dialogo(self, foco_inicial=self.campo)
		self.CentreOnParent()

	def opciones(self) -> OpcionesBusqueda:
		return OpcionesBusqueda(texto=self.campo.GetValue(), mayusculas=self.casilla_mayusculas.GetValue(),
			palabra=self.casilla_palabra.GetValue(), regex=self.casilla_regex.GetValue())

	def _validas(self) -> OpcionesBusqueda | None:
		opciones = self.opciones()
		problema = None
		if not opciones.texto:
			problema = _("Escriba el texto que quiere buscar.")
		else:
			try:
				compilar(opciones)
			except re.error as error:
				problema = _("La expresión regular no es válida: {e}").format(e=error)
		if problema:
			dialogos.mostrar_error(self, problema)
			_marcar_campo(self.campo)
			return None
		ULTIMA[0] = opciones
		return opciones

	def buscar(self) -> bool:
		opciones = self._validas()
		return bool(opciones and self._al_buscar(opciones))

	def reemplazar(self) -> bool:
		opciones = self._validas()
		return bool(opciones and self._al_reemplazar(opciones, self.campo_nuevo.GetValue()))

	def reemplazar_todo(self) -> int:
		opciones = self._validas()
		return self._al_reemplazar_todo(opciones, self.campo_nuevo.GetValue()) if opciones else 0

	def _al_cerrar_ventana(self, _evento: wx.CloseEvent) -> None:
		if self._al_cerrar is not None:
			self._al_cerrar()
		self.Destroy()


# ── Ir a línea o desplazamiento ──────────────────────────────────────────────


def interpretar_numero(texto: str, hexadecimal: bool) -> int | None:
	"""Número escrito por la persona: decimal, o hexadecimal con «0x» o con «h» final si ``hexadecimal``."""
	limpio = texto.strip().replace(".", "").replace(" ", "")
	if not limpio:
		return None
	try:
		if hexadecimal and (limpio.lower().startswith("0x") or limpio.lower().endswith("h")):
			return int(limpio.lower().removeprefix("0x").removesuffix("h"), 16)
		return int(limpio, 10)
	except ValueError:
		return None


class DialogoIrA(wx.Dialog):
	"""Ir a línea (texto) o a un desplazamiento (hexadecimal). Valida el rango al aceptar.

	:param minimo, maximo: rango admitido (líneas desde 1; desplazamientos desde 0).
	:param maximo: ``None`` si no se sabe todavía (archivo por bloques sin recorrer).
	"""

	def __init__(self, padre: wx.Window | None, hexadecimal: bool, actual: int, minimo: int, maximo: int | None) -> None:
		titulo = _("Ir a un desplazamiento") if hexadecimal else _("Ir a la línea")
		super().__init__(padre, title=titulo, name=titulo)
		self.hexadecimal = hexadecimal
		self.minimo = minimo
		self.maximo = maximo
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		if hexadecimal:
			rango = _("&Desplazamiento (de 0 a {m}; hexadecimal con 0x):").format(m=maximo) if maximo is not None else \
				_("&Desplazamiento (hexadecimal con 0x):")
			ayuda = _("Byte al que ir, contando desde 0. Por ejemplo 4096 o 0x1000.")
		else:
			rango = _("&Número de línea (de 1 a {m}):").format(m=maximo) if maximo is not None else _("&Número de línea:")
			ayuda = _("Línea a la que ir, contando desde 1.")
		_etiqueta, self.campo = crear_campo(panel, rango, wx.TextCtrl, value=str(actual), size=panel.FromDIP(wx.Size(240, -1)),
			ayuda=ayuda, sizer=sizer)
		sizer.Add(dialogos.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar(), id=wx.ID_OK)
		dialogos.preparar_dialogo(self, foco_inicial=self.campo)
		self.CentreOnParent()

	def valor(self) -> int | None:
		return interpretar_numero(self.campo.GetValue(), self.hexadecimal)

	def problema(self) -> str | None:
		numero = self.valor()
		if numero is None:
			return _("Escriba un número.")
		if numero < self.minimo or (self.maximo is not None and numero > self.maximo):
			if self.maximo is None:
				return _("El número debe ser {a} o mayor.").format(a=self.minimo)
			return _("El número debe estar entre {a} y {b}.").format(a=self.minimo, b=self.maximo)
		return None

	def aceptar(self) -> bool:
		problema = self.problema()
		if problema:
			dialogos.mostrar_error(self, problema)
			_marcar_campo(self.campo)
			return False
		_terminar(self, wx.ID_OK)
		return True


def pedir_posicion(padre: wx.Window, hexadecimal: bool, actual: int, minimo: int, maximo: int | None) -> int | None:
	dialogo = DialogoIrA(padre, hexadecimal, actual, minimo, maximo)
	try:
		return dialogo.valor() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()
