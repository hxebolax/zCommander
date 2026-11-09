# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Perfil de usuario: Novato, Intermedio, Avanzado y los perfiles propios (1.x §2.2 y 2.0, 10.2).

El perfil activo no se guarda: se calcula (``perfiles.perfil_actual``) y el
diálogo lo dice arriba («Perfil actual: Personalizado»). Al moverse por la
lista, la descripción de abajo explica el perfil y cuántas preferencias
cambiarían; Aplicar lo pregunta antes con ese número, porque aplicar un
perfil pisa ajustes hechos a mano.

2.0 (bloque PE): tras los de fábrica van los perfiles propios
(``data/config/perfiles/<nombre>.json``) con «Guardar la configuración actual
como perfil...», «Renombrar...» y «Eliminar» (solo en los propios). El
``.zcperfil`` para llevarlos a otro equipo es del bloque CS.
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import perfiles, perfiles_propios
from app.ui import anuncios
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)

ORDEN = (perfiles.NOVATO, perfiles.INTERMEDIO, perfiles.AVANZADO)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def texto_cambios(numero: int) -> str:
	if numero == 0:
		return _("Ya tiene todos sus valores: aplicarlo no cambia nada.")
	if numero == 1:
		return _("Al aplicarlo cambiará 1 preferencia.")
	return _("Al aplicarlo cambiarán {n} preferencias.").format(n=numero)


def nombres_reservados() -> tuple[str, ...]:
	return tuple(perfiles.nombre_visible(p) for p in (*ORDEN, perfiles.PERSONALIZADO))


def perfil_actual(config) -> str:
	"""Nombre visible del perfil actual: uno de fábrica, uno propio que coincide o «Personalizado»."""
	actual = perfiles.perfil_actual(config)
	if actual != perfiles.PERSONALIZADO:
		return perfiles.nombre_visible(actual)
	for propio in perfiles_propios.listar():
		if perfiles_propios.coincide(config, propio):
			return propio.nombre
	return perfiles.nombre_visible(actual)


class DialogoPerfil(f_comun.DialogoF):
	"""Elegir y aplicar un perfil. ``aplicado`` queda con el nombre del último aplicado."""

	def __init__(self, padre: wx.Window | None, config) -> None:
		super().__init__(padre, _("Perfil de usuario"))
		self.config = config
		self.aplicado: str | None = None
		self.propios: list[perfiles_propios.PerfilPropio] = perfiles_propios.listar()
		self.texto_actual = wx.StaticText(self.panel, label="")
		self.sizer.Add(self.texto_actual, 0, wx.ALL, self.FromDIP(6))
		_l, self.lista = crear_campo(self.panel, _("&Perfiles:"), wx.ListBox, choices=self._nombres(),
			size=self.FromDIP(wx.Size(300, 120)), sizer=self.sizer, ayuda=_("Elija un perfil; debajo se explica qué cambia."))
		_d, self.descripcion = crear_campo(self.panel, _("&Descripción:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY,
			size=self.FromDIP(wx.Size(440, 110)), sizer=self.sizer, ayuda=_("Qué hace el perfil elegido. Recórrala con las flechas."))
		fila = wx.WrapSizer(wx.HORIZONTAL)
		self.boton_aplicar = self.boton(_("&Aplicar el perfil..."), _("Aplica el perfil elegido; pide confirmación."), self.aplicar, fila)
		self.boton(_("&Guardar la configuración actual como perfil..."),
			_("Guarda las preferencias y teclas actuales como un perfil con nombre (sin contraseñas ni la posición de la ventana)."),
			self.guardar_actual, fila)
		self.boton_renombrar = self.boton(_("&Renombrar..."), _("Cambia el nombre del perfil propio elegido."), self.renombrar, fila)
		self.boton_eliminar = self.boton(_("E&liminar"), _("Borra el perfil propio elegido; pide confirmación."), self.eliminar, fila)
		self.sizer.Add(fila, 0, wx.EXPAND)
		self.lista.Bind(wx.EVT_LISTBOX, lambda _e: self._describir())
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.aplicar())
		self.terminar(wx.CLOSE, foco=self.lista, id_escape=wx.ID_CLOSE)
		self.FindWindow(wx.ID_CLOSE).Bind(wx.EVT_BUTTON, lambda _e: self.cerrar(wx.ID_CLOSE))
		self.boton_aplicar.SetDefault()
		actual = perfiles.perfil_actual(config)
		self.lista.SetSelection(ORDEN.index(actual) if actual in ORDEN else ORDEN.index(perfiles.INTERMEDIO))
		self._actualizar()

	def _nombres(self) -> list[str]:
		return [perfiles.nombre_visible(p) for p in ORDEN] + [_("{n} (propio)").format(n=p.nombre) for p in self.propios]

	def _recargar(self, nombre: str | None = None) -> None:
		self.propios = perfiles_propios.listar()
		self.lista.Set(self._nombres())
		indice = next((len(ORDEN) + i for i, p in enumerate(self.propios) if p.nombre == nombre), 0)
		self.lista.SetSelection(indice)
		self._actualizar()

	def elegido(self) -> str:
		"""Id del perfil de fábrica elegido (para un propio, el de Intermedio; use ``propio_elegido``)."""
		indice = self.lista.GetSelection()
		return ORDEN[indice] if 0 <= indice < len(ORDEN) else perfiles.INTERMEDIO

	def propio_elegido(self) -> perfiles_propios.PerfilPropio | None:
		indice = self.lista.GetSelection() - len(ORDEN)
		return self.propios[indice] if 0 <= indice < len(self.propios) else None

	def _actualizar(self) -> None:
		self.texto_actual.SetLabel(_("Perfil actual: {p}").format(p=perfil_actual(self.config)))
		self._describir()

	def _describir(self) -> None:
		propio = self.propio_elegido()
		if propio is not None:
			cambios = perfiles_propios.cambios_al_aplicar(self.config, propio)
			descripcion = propio.descripcion or _("Perfil propio guardado con «Guardar la configuración actual como perfil».")
		else:
			perfil = self.elegido()
			cambios = perfiles.cambios_al_aplicar(self.config, perfil)
			descripcion = perfiles.descripcion(perfil)
		self.descripcion.SetValue(f"{descripcion}\n{texto_cambios(len(cambios))}")
		self.boton_renombrar.Enable(propio is not None)
		self.boton_eliminar.Enable(propio is not None)

	def aplicar(self) -> int | None:
		"""Aplica el perfil elegido tras confirmarlo; devuelve cuántas preferencias cambiaron."""
		propio = self.propio_elegido()
		if propio is not None:
			nombre = propio.nombre
			cambios = perfiles_propios.cambios_al_aplicar(self.config, propio)
		else:
			perfil = self.elegido()
			nombre = perfiles.nombre_visible(perfil)
			cambios = perfiles.cambios_al_aplicar(self.config, perfil)
		if not cambios:
			anuncios.anunciar(_("El perfil {p} ya está aplicado").format(p=nombre), anuncios.RESULTADO)
			return 0
		if not f_comun.preguntar(self, _("¿Aplicar el perfil {p}? {c}").format(p=nombre, c=texto_cambios(len(cambios))), _("Aplicar el perfil")):
			return None
		try:
			numero = perfiles_propios.aplicar(self.config, propio) if propio is not None else perfiles.aplicar_perfil(self.config, perfil)
		except Exception as error:  # noqa: BLE001 - ErrorConfiguracion u OSError: se dice a la persona
			log.exception("No se pudo aplicar el perfil %s", nombre)
			f_comun.avisar(self, _("No se pudo aplicar el perfil: {e}").format(e=error), _("Perfil de usuario"))
			return None
		self.aplicado = nombre if propio is not None else perfil
		self._actualizar()
		anuncios.anunciar(_("Perfil {p} aplicado: {n} preferencias cambiadas").format(p=nombre, n=numero), anuncios.RESULTADO)
		return numero

	def guardar_actual(self) -> str | None:
		nombre = guardar_propio(self, self.config)
		if nombre:
			self._recargar(nombre)
		return nombre

	def renombrar(self) -> bool:
		propio = self.propio_elegido()
		if propio is None:
			return False
		nuevo = f_comun.pedir(self, _("&Nombre del perfil:"), _("Renombrar el perfil"), propio.nombre)
		if nuevo is None:
			return False
		try:
			nuevo = perfiles_propios.validar_nombre(nuevo, nombres_reservados())
			perfiles_propios.renombrar(propio.nombre, nuevo)
		except (perfiles_propios.ErrorPerfil, OSError) as error:
			f_comun.avisar(self, str(error), _("Renombrar el perfil"))
			return False
		self._recargar(nuevo)
		anuncios.anunciar(_("Perfil renombrado: {n}").format(n=nuevo), anuncios.RESULTADO)
		return True

	def eliminar(self) -> bool:
		propio = self.propio_elegido()
		if propio is None:
			return False
		if not f_comun.preguntar(self, _("¿Eliminar el perfil «{n}»? Sus valores no se tocan.").format(n=propio.nombre),
				_("Eliminar el perfil"), peligroso=True):
			return False
		try:
			perfiles_propios.eliminar(propio.nombre)
		except OSError as error:
			f_comun.avisar(self, _("No se pudo eliminar: {e}").format(e=error), _("Eliminar el perfil"))
			return False
		self._recargar()
		anuncios.anunciar(_("Perfil eliminado: {n}").format(n=propio.nombre), anuncios.RESULTADO)
		return True


def guardar_propio(padre: wx.Window | None, config) -> str | None:
	"""Orden ``perfil_guardar_propio``: pide el nombre y guarda la configuración actual como perfil."""
	nombre = f_comun.pedir(padre, _("&Nombre del perfil:"), _("Guardar la configuración como perfil"))
	if nombre is None:
		return None
	try:
		nombre = perfiles_propios.validar_nombre(nombre, nombres_reservados())
	except perfiles_propios.ErrorPerfil as error:
		f_comun.avisar(padre, str(error), _("Guardar la configuración como perfil"))
		return None
	existentes = {p.nombre.casefold() for p in perfiles_propios.listar()}
	if nombre.casefold() in existentes and not f_comun.preguntar(padre, _("Ya hay un perfil «{n}». ¿Sustituirlo?").format(n=nombre),
			_("Guardar la configuración como perfil")):
		return None
	try:
		perfiles_propios.guardar(perfiles_propios.capturar(config, nombre))
	except OSError as error:
		log.exception("No se pudo guardar el perfil %s", nombre)
		f_comun.avisar(padre, _("No se pudo guardar el perfil: {e}").format(e=error), _("Guardar la configuración como perfil"))
		return None
	anuncios.anunciar(_("Perfil guardado: {n}").format(n=nombre), anuncios.RESULTADO)
	return nombre


def mostrar_perfil(padre: wx.Window | None, config) -> str | None:
	dialogo = DialogoPerfil(padre, config)
	return f_comun.mostrar(dialogo, lambda d: d.aplicado, aceptar=(wx.ID_CLOSE, wx.ID_CANCEL, wx.ID_OK))
