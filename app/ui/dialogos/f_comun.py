# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Piezas comunes de los diálogos del bloque F (menú de usuario, favoritos, columnas...).

Por qué existe:

- Los avisos y preguntas de estos diálogos pasan por ``avisar``, ``preguntar``,
  ``elegir`` y ``pedir`` de ESTE módulo: las pruebas las sustituyen y ningún
  ``ShowModal`` real llega a la pantalla (el ``conftest`` lo prohíbe).
- ``DialogoF`` monta lo que todos repiten: panel, sizer vertical, botonera en
  español, Escape, Ctrl+H y foco inicial (``preparar_dialogo``), y devolver el
  foco al control que lo tenía al cerrar (``mostrar``).
- ``asignar_letras`` reparte letras de acceso sin repetir en etiquetas que no
  escribimos nosotros (las de ``descripciones_config``), respetando las que
  ya usan los botones.
"""

from __future__ import annotations

import builtins
import logging
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from typing import Any, TypeVar

import wx

from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.revision_teclado import letra_de_acceso

log = logging.getLogger(__name__)

T = TypeVar("T")

#: Letras que se pueden pulsar con Alt en un teclado español (las de ``revision_teclado``).
LETRAS = "abcdefghijklmnopqrstuvwxyzñ0123456789"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Avisos y preguntas (sustituibles en las pruebas) ────────────────────────

def avisar(padre: wx.Window | None, texto: str, titulo: str = "") -> None:
	"""Mensaje con «Aceptar» (errores y avisos)."""
	dialogos.mostrar_mensaje(padre, texto, titulo or _("Aviso"), icono=wx.ICON_WARNING)


def preguntar(padre: wx.Window | None, texto: str, titulo: str = "", peligroso: bool = False) -> bool:
	"""Sí o No. Con ``peligroso``, Intro responde «No»."""
	return dialogos.confirmar(padre, texto, titulo or _("Confirmación"), peligroso=peligroso) == wx.ID_YES


def elegir(padre: wx.Window | None, texto: str, titulo: str, opciones: Sequence[str]) -> int | None:
	"""Botones que dicen la acción; índice elegido o ``None`` si se cancela."""
	return dialogos.elegir_opcion(padre, texto, titulo, opciones)


def pedir(padre: wx.Window | None, etiqueta: str, titulo: str, valor: str = "", **opciones) -> str | None:
	"""Un texto con su etiqueta; ``None`` si se cancela."""
	return dialogos.pedir_texto(padre, etiqueta, titulo, valor, **opciones)


# ── Diálogo base ─────────────────────────────────────────────────────────────

class DialogoF(wx.Dialog):
	"""Diálogo con panel, sizer y botonera. Las subclases crean sus controles en ``self.panel``.

	Uso::

		super().__init__(padre, _("Favoritos"))
		...controles en self.panel con self.sizer...
		self.terminar(wx.OK | wx.CANCEL, foco=self.lista)
	"""

	def __init__(self, padre: wx.Window | None, titulo: str, redimensionable: bool = True) -> None:
		estilo = wx.DEFAULT_DIALOG_STYLE | (wx.RESIZE_BORDER if redimensionable else 0)
		super().__init__(padre, title=titulo, style=estilo, name=titulo)
		if wx.HelpProvider.Get() is None:
			# Sin proveedor, SetHelpText no guarda nada y Ctrl+H no tendría qué decir.
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.titulo = titulo
		self.panel = wx.Panel(self)
		self.sizer = wx.BoxSizer(wx.VERTICAL)

	def boton(self, etiqueta: str, ayuda: str, accion: Callable[[], Any], sizer: wx.Sizer | None = None,
			identificador: int = wx.ID_ANY) -> wx.Button:
		"""Botón con ayuda para Ctrl+H; ``accion`` se llama sin argumentos."""
		boton = wx.Button(self.panel, identificador, etiqueta)
		boton.SetHelpText(ayuda)
		boton.Bind(wx.EVT_BUTTON, lambda _evento: accion())
		if sizer is not None:
			sizer.Add(boton, 0, wx.ALL, self.FromDIP(4))
		return boton

	def terminar(self, banderas: int = wx.OK | wx.CANCEL, foco: wx.Window | None = None,
			predeterminado: int | None = None, id_escape: int = wx.ID_CANCEL) -> None:
		"""Añade la botonera, ajusta el tamaño y prepara Escape, Ctrl+H y el foco inicial."""
		if banderas:
			self.sizer.Add(crear_botonera(self.panel, banderas, predeterminado), 0, wx.ALIGN_RIGHT | wx.ALL, self.FromDIP(8))
		self.panel.SetSizer(self.sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(self.panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		preparar_dialogo(self, id_escape=id_escape, foco_inicial=foco)
		self.CentreOnParent()

	def cerrar(self, codigo: int) -> None:
		"""Cierra con ``codigo`` (también sin modal, en las pruebas)."""
		if self.IsModal():
			self.EndModal(codigo)
		else:
			self.SetReturnCode(codigo)


def mostrar(dialogo: wx.Dialog, al_aceptar: Callable[[Any], T] | None = None, aceptar: Iterable[int] = (wx.ID_OK,)) -> T | None:
	"""Muestra ``dialogo`` modal, lo destruye y devuelve el foco a donde estaba.

	:param al_aceptar: ``al_aceptar(dialogo)`` se llama ANTES de destruirlo si
		se cerró con un código de ``aceptar``; su resultado es lo que se devuelve.
	"""
	foco_previo = wx.Window.FindFocus()
	try:
		codigo = dialogo.ShowModal()
		if codigo in tuple(aceptar):
			return al_aceptar(dialogo) if al_aceptar is not None else codigo  # type: ignore[return-value]
		return None
	finally:
		dialogo.Destroy()
		# Si el control desapareció (pestaña cerrada) o no había, vuelve a la lista del panel activo.
		dialogos.devolver_foco(foco_previo)


# ── Letras de acceso ─────────────────────────────────────────────────────────

def _sin_tilde(letra: str) -> str:
	if letra == "ñ":
		return letra
	return "".join(c for c in unicodedata.normalize("NFD", letra) if unicodedata.category(c) != "Mn")


def _candidatas(etiqueta: str) -> tuple[str, list[tuple[str, int]]]:
	"""(texto sin «&», [(letra, posición)...]) en orden de preferencia y sin letras repetidas.

	Primero la letra que ya traía la etiqueta, después las iniciales de palabra
	y por último cualquier otra letra.
	"""
	original = letra_de_acceso(etiqueta)
	posicion_original = -1
	limpia_partes: list[str] = []
	i = 0
	while i < len(etiqueta):
		if etiqueta.startswith("&&", i):
			limpia_partes.append("&&")
			i += 2
			continue
		if etiqueta[i] == "&":
			if posicion_original < 0 and original is not None:
				posicion_original = len("".join(limpia_partes))
			i += 1
			continue
		limpia_partes.append(etiqueta[i])
		i += 1
	limpia = "".join(limpia_partes)
	orden: list[int] = []
	if posicion_original >= 0:
		orden.append(posicion_original)
	orden.extend(i for i, c in enumerate(limpia) if (i == 0 or limpia[i - 1] in " («\"'") and i not in orden)
	orden.extend(i for i in range(len(limpia)) if i not in orden)
	vistas: set[str] = set()
	candidatas: list[tuple[str, int]] = []
	for i in orden:
		letra = limpia[i].lower()
		if letra not in LETRAS or letra in vistas or limpia[i] == "&":
			continue
		vistas.add(letra)
		candidatas.append((letra, i))
	return limpia, candidatas


def repartir_letras(etiquetas: Sequence[str], usadas: Iterable[str] = ()) -> list[str]:
	"""Etiquetas con letras de acceso distintas entre sí y de ``usadas`` (los botones).

	Es un emparejamiento máximo (algoritmo de Kuhn) entre etiquetas y letras:
	un reparto ávido dejaba sin letra a etiquetas como «Disposición de los
	paneles» cuyas letras ya se habían llevado otras que tenían alternativas.
	Cada etiqueta intenta antes su letra original y sus iniciales. Si aun así
	no queda hueco, se le añade un dígito libre entre paréntesis.
	"""
	ocupadas = set(usadas)
	datos = [_candidatas(e) for e in etiquetas]
	dueno: dict[str, int] = {}
	eleccion: dict[int, tuple[str, int]] = {}

	def intentar(indice: int, visitadas: set[str]) -> bool:
		# Primero una letra libre (sin mover a nadie de la suya); solo si no hay, se desplaza a otra etiqueta.
		for letra, posicion in datos[indice][1]:
			if letra not in ocupadas and letra not in dueno:
				dueno[letra] = indice
				eleccion[indice] = (letra, posicion)
				return True
		for letra, posicion in datos[indice][1]:
			if letra in ocupadas or letra in visitadas:
				continue
			visitadas.add(letra)
			if intentar(dueno[letra], visitadas):
				dueno[letra] = indice
				eleccion[indice] = (letra, posicion)
				return True
		return False

	for indice in range(len(datos)):
		intentar(indice, set())
	resultado: list[str] = []
	libres = [d for d in "123456789" if d not in ocupadas and d not in dueno]
	for indice, (limpia, _candidatas_etiqueta) in enumerate(datos):
		if indice in eleccion:
			_letra, posicion = eleccion[indice]
			resultado.append(limpia[:posicion] + "&" + limpia[posicion:])
		elif libres:
			digito = libres.pop(0)
			fin = limpia.rstrip(":")
			resultado.append(f"{fin} (&{digito})" + limpia[len(fin):])
		else:
			log.warning("Sin letra de acceso libre para «%s»", limpia)
			resultado.append(limpia)
	return resultado


def poner_letra(etiqueta: str, usadas: set[str]) -> str:
	"""``etiqueta`` con una letra de acceso que no esté en ``usadas`` (y la añade a ``usadas``)."""
	nueva = repartir_letras([etiqueta], usadas)[0]
	letra = letra_de_acceso(nueva)
	if letra:
		usadas.add(letra)
	return nueva


def letras_de(etiquetas: Iterable[str]) -> set[str]:
	"""Letras de acceso ya usadas por estas etiquetas."""
	return {letra for letra in (letra_de_acceso(e) for e in etiquetas) if letra}


def texto_limpio(etiqueta: str) -> str:
	"""«&Nombre:» → «Nombre»."""
	return etiqueta.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def normalizar_busqueda(texto: str) -> str:
	"""Minúsculas y sin tildes (la ñ se conserva) para buscar escribiendo."""
	texto = texto.casefold()
	return "".join(_sin_tilde(c) for c in texto)
