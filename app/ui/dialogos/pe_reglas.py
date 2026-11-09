# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Reglas de anuncio, color y sonido (diseño 2.0, 10.10; orden ``reglas``).

Lista ordenada de reglas (la primera activa que coincide decide) con Nueva,
Editar, Subir, Bajar, Eliminar, Activar o desactivar y «Probar con el
elemento del cursor» (dice qué regla se aplicaría). Cada cambio se guarda al
momento en ``reglas.json`` y las listas de archivos se vuelven a pintar.
Nada solo con color: una regla con color y sin texto, sonido ni anuncio se
guarda, pero se avisa «Este efecto solo se ve».
"""

from __future__ import annotations

import builtins
import logging
import re

import wx

from app.services import formato
from app.services import reglas as servicio
from app.services.reglas import Condicion, Regla
from app.ui import anuncios
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun, pe_comun

log = logging.getLogger(__name__)

_UNIDADES = {"": 1, "b": 1, "kb": 1024, "k": 1024, "mb": 1024 ** 2, "m": 1024 ** 2, "gb": 1024 ** 3, "g": 1024 ** 3, "tb": 1024 ** 4}
_TAMANO = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)\s*$")
TIPOS = (None, False, True)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def leer_tamano(texto: str) -> int | None:
	"""«1 GB» → 1073741824; vacío → ``None``; ``ValueError`` si no se entiende."""
	if not texto.strip():
		return None
	coincidencia = _TAMANO.match(texto)
	if not coincidencia or coincidencia.group(2).lower() not in _UNIDADES:
		raise ValueError(_("Escriba el tamaño con cifras y, si quiere, KB, MB, GB o TB (por ejemplo 1 GB)"))
	return int(float(coincidencia.group(1).replace(",", ".")) * _UNIDADES[coincidencia.group(2).lower()])


def leer_dias(texto: str) -> float | None:
	if not texto.strip():
		return None
	try:
		return float(texto.strip().replace(",", "."))
	except ValueError as error:
		raise ValueError(_("Escriba los días con cifras")) from error


class DialogoRegla(f_comun.DialogoF):
	"""Crear o cambiar una regla. ``regla`` queda con el resultado."""

	def __init__(self, padre: wx.Window | None, regla: Regla) -> None:
		super().__init__(padre, _("Regla"))
		self.regla = regla
		c = regla.condicion

		def campo(etiqueta: str, valor: str, ayuda: str) -> wx.TextCtrl:
			return crear_campo(self.panel, etiqueta, wx.TextCtrl, value=valor, sizer=self.sizer, ayuda=ayuda)[1]

		self.nombre = campo(_("&Nombre:"), regla.nombre, _("Nombre de la regla, por ejemplo «Grandes»."))
		self.activa = wx.CheckBox(self.panel, label=_("Regla ac&tiva"))
		self.activa.SetValue(regla.activa)
		self.activa.SetHelpText(_("Desactivada, la regla se guarda pero no se aplica."))
		self.sizer.Add(self.activa, 0, wx.ALL, self.FromDIP(5))
		self.patron = campo(_("&Patrón (por ejemplo *.iso;*.img; vacío: cualquiera):"), c.patron,
			_("Nombres que cumplen la regla, como en Marcar por patrón; exclusiones tras |."))
		self.mayor = campo(_("Más &grande que (por ejemplo 1 GB; vacío: sin límite):"),
			formato.tamano_legible(c.tamano_min) if c.tamano_min is not None else "", _("Tamaño mínimo, con KB, MB, GB o TB."))
		self.menor = campo(_("Más pe&queño que:"), formato.tamano_legible(c.tamano_max) if c.tamano_max is not None else "",
			_("Tamaño máximo, con KB, MB, GB o TB."))
		self.menos_dias = campo(_("Modificado hace &menos de (días):"), _dias(c.modificado_hace_menos_de),
			_("Por ejemplo 1 para lo modificado hoy."))
		self.mas_dias = campo(_("Modificado hace más &de (días):"), _dias(c.modificado_hace_mas_de),
			_("Por ejemplo 365 para lo que lleva un año sin cambiar."))
		_e, self.tipo = crear_campo(self.panel, _("&Es:"), wx.Choice, choices=[_("Archivo o carpeta"), _("Solo archivos"), _("Solo carpetas")],
			sizer=self.sizer, ayuda=_("A qué elementos se aplica."))
		self.tipo.SetSelection(TIPOS.index(c.es_carpeta))
		self.etiqueta_atributos = wx.StaticText(self.panel, label=_("At&ributos que debe tener:"))
		self._atributos = [*servicio.ATRIBUTOS, *servicio.ATRIBUTOS_ESPECIALES]
		self.atributos = CheckListBoxAccesible(self.panel, _("Atributos que debe tener"),
			[_(servicio.NOMBRES_ATRIBUTOS[a]) for a in self._atributos], recordar_posicion=False, size=self.FromDIP(wx.Size(300, 110)))
		for i, atributo in enumerate(self._atributos):
			self.atributos.Check(i, atributo in c.atributos)
		self.atributos.SetSelection(0)
		self.sizer.Add(self.etiqueta_atributos, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.atributos, 0, wx.EXPAND | wx.ALL, self.FromDIP(5))
		_c, self.color = crear_campo(self.panel, _("Co&lor:"), wx.Choice, choices=[_("Ninguno"), *[_(c) for c in servicio.COLORES]],
			sizer=self.sizer, ayuda=_("Color del texto de la fila. Solo se ve: añada también texto, sonido o anuncio."))
		self.color.SetSelection(servicio.COLORES.index(regla.color) + 1 if regla.color in servicio.COLORES else 0)
		self.texto = campo(_("Te&xto de la columna Regla:"), regla.texto,
			_("Palabra corta que se ve en la columna Regla y se lee con Control más su número (o al moverse, si la pone primera)."))
		_s, self.sonido = crear_campo(self.panel, _("&Sonido:"), wx.Choice,
			choices=[_("Ninguno"), _("Aviso de regla A"), _("Aviso de regla B"), _("Aviso de regla C")], sizer=self.sizer,
			ayuda=_("Suena al llegar el cursor al elemento."))
		self.sonido.SetSelection(servicio.SONIDOS.index(regla.sonido) + 1 if regla.sonido in servicio.SONIDOS else 0)
		self.anuncio = campo(_("An&uncio al llegar el cursor:"), regla.anuncio,
			_("Frase que se dice tras lo que lee el lector (nivel de detalle)."))
		self.terminar(wx.OK | wx.CANCEL, foco=self.nombre)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())

	def leer(self) -> Regla:
		condicion = Condicion(
			patron=self.patron.GetValue().strip(),
			tamano_min=leer_tamano(self.mayor.GetValue()), tamano_max=leer_tamano(self.menor.GetValue()),
			modificado_hace_menos_de=leer_dias(self.menos_dias.GetValue()), modificado_hace_mas_de=leer_dias(self.mas_dias.GetValue()),
			atributos=tuple(a for i, a in enumerate(self._atributos) if self.atributos.IsChecked(i)),
			es_carpeta=TIPOS[self.tipo.GetSelection()],
		)
		color = servicio.COLORES[self.color.GetSelection() - 1] if self.color.GetSelection() > 0 else None
		sonido = servicio.SONIDOS[self.sonido.GetSelection() - 1] if self.sonido.GetSelection() > 0 else ""
		return Regla(self.nombre.GetValue().strip(), self.activa.GetValue(), condicion, color, self.texto.GetValue().strip()[:24],
			sonido, self.anuncio.GetValue().strip())

	def aceptar(self) -> bool:
		try:
			regla = self.leer()
			servicio.validar(regla)
		except ValueError as error:
			f_comun.avisar(self, str(error), self.titulo)
			return False
		if regla.solo_color():
			f_comun.avisar(self, _("Este efecto solo se ve: añada un texto, un sonido o un anuncio para que también se oiga."), self.titulo)
		self.regla = regla
		self.cerrar(wx.ID_OK)
		return True


def _dias(valor: float | None) -> str:
	if valor is None:
		return ""
	return str(int(valor)) if float(valor).is_integer() else str(valor).replace(".", ",")


class DialogoReglas(pe_comun.DialogoListaPE):
	def __init__(self, padre: wx.Window | None, pe, entrada=None) -> None:
		super().__init__(padre, _("Reglas de anuncio, color y sonido"), _("&Reglas:"),
			[(_("Nombre"), 140), (_("Activa"), 70), (_("Condición"), 240), (_("Efectos"), 240)],
			_("La primera regla activa que coincide decide. Izquierda y Derecha leen nombre, estado, condición y efectos."))
		self.pe = pe
		self.entrada = entrada
		self.boton(_("&Nueva..."), _("Crea una regla al final."), self.nueva, self.botonera)
		self.boton(_("E&ditar..."), _("Cambia la regla elegida."), self.editar, self.botonera)
		self.boton(_("Ac&tivar o desactivar"), _("Enciende o apaga la regla elegida sin borrarla."), self.alternar, self.botonera)
		self.boton(_("&Subir"), _("Sube la regla (se comprueba antes)."), lambda: self.mover(-1), self.botonera)
		self.boton(_("&Bajar"), _("Baja la regla (se comprueba después)."), lambda: self.mover(1), self.botonera)
		self.boton(_("E&liminar"), _("Borra la regla elegida; pide confirmación."), self.eliminar, self.botonera)
		self.boton(_("&Probar con el elemento del cursor"), _("Dice qué regla se aplicaría al elemento del cursor del panel."),
			self.probar, self.botonera)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.editar())
		self.cerrar_lista()
		self.rellenar(0)

	def filas(self) -> list[list[str]]:
		return [[r.nombre, _("Sí") if r.activa else _("No"), servicio.describir(r), servicio.describir_efectos(r)] for r in self.pe.reglas]

	def elegida(self) -> Regla | None:
		i = self.indice()
		return self.pe.reglas[i] if 0 <= i < len(self.pe.reglas) else None

	def _guardar(self, lista: list[Regla], foco: int) -> bool:
		ok = pe_comun.guardar_con_aviso(self, lambda: self.pe.guardar_reglas(lista), self.titulo)
		self.rellenar(foco)
		self.lista.SetFocus()
		return ok

	def nueva(self) -> None:
		regla = f_comun.mostrar(DialogoRegla(self, Regla(_("Regla"))), lambda d: d.regla)
		if regla is not None and self._guardar([*self.pe.reglas, regla], len(self.pe.reglas)):
			anuncios.anunciar(_("Regla creada: {n}").format(n=regla.nombre), anuncios.RESULTADO)

	def editar(self) -> None:
		actual = self.elegida()
		if actual is None:
			return
		i = self.pe.reglas.index(actual)
		regla = f_comun.mostrar(DialogoRegla(self, actual), lambda d: d.regla)
		if regla is None:
			return
		lista = list(self.pe.reglas)
		lista[i] = regla
		if self._guardar(lista, i):
			anuncios.anunciar(_("Regla guardada: {n}").format(n=regla.nombre), anuncios.RESULTADO)

	def alternar(self) -> None:
		actual = self.elegida()
		if actual is None:
			return
		actual.activa = not actual.activa
		i = self.pe.reglas.index(actual)
		if self._guardar(list(self.pe.reglas), i):
			anuncios.anunciar((_("{n}: activa") if actual.activa else _("{n}: desactivada")).format(n=actual.nombre), anuncios.RESULTADO)

	def mover(self, paso: int) -> None:
		i = self.indice()
		destino = i + paso
		if i < 0 or not 0 <= destino < len(self.pe.reglas):
			return
		lista = list(self.pe.reglas)
		lista[i], lista[destino] = lista[destino], lista[i]
		if self._guardar(lista, destino):
			self.anunciar_posicion(destino, len(lista))

	def eliminar(self) -> None:
		actual = self.elegida()
		if actual is None:
			return
		if not f_comun.preguntar(self, _("¿Eliminar la regla «{n}»?").format(n=actual.nombre), self.titulo, peligroso=True):
			return
		i = self.pe.reglas.index(actual)
		if self._guardar([r for r in self.pe.reglas if r is not actual], i):
			anuncios.anunciar(_("Regla eliminada: {n}").format(n=actual.nombre), anuncios.RESULTADO)

	def probar(self) -> str:
		entrada = self.entrada
		if entrada is None or getattr(entrada, "es_superior", False):
			texto = _("No hay un elemento en el cursor del panel")
		else:
			regla = servicio.primera(self.pe.reglas, entrada)
			if regla is None:
				texto = _("Ninguna regla se aplica a {e}").format(e=entrada.nombre)
			else:
				texto = _("A {e} se aplica la regla {n}: {f}").format(e=entrada.nombre, n=regla.nombre, f=servicio.describir_efectos(regla))
		f_comun.avisar(self, texto, _("Probar las reglas"))
		return texto


def mostrar(padre: wx.Window | None, pe, entrada=None) -> None:
	f_comun.mostrar(DialogoReglas(padre, pe, entrada), aceptar=(wx.ID_CLOSE, wx.ID_OK, wx.ID_CANCEL))
