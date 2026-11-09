# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Visor ampliable para baja visión y diálogo «Convertir o redimensionar imágenes» (diseño 2.0, 11.11).

El visor es una ``VentanaComplemento`` (no modal; Escape cierra, F1 abre la
ayuda) con la imagen en un área con desplazamiento, un texto de estado de
solo lectura («foto.jpg, 4000 × 3000, al 25 %, imagen 3 de 12») y botones.
Teclas propias: Más y Menos amplían y reducen; Re Pág y Av Pág, imagen anterior
y siguiente; las flechas desplazan la imagen ampliada cuando el foco está en ella.
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from typing import Any

import wx

from . import exif, procesado

log = logging.getLogger(__name__)

TECLAS_PROPIAS = ("Re Pág", "Av Pág", "Izquierda", "Derecha", "Arriba", "Abajo")
NIVELES_ZOOM = (0.05, 0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def imagenes_de_la_carpeta(ruta: str) -> list[str]:
	carpeta = os.path.dirname(ruta)
	try:
		with os.scandir(carpeta) as elementos:
			rutas = [e.path for e in elementos if e.is_file() and exif.es_imagen(e.name)]
	except OSError:
		return [ruta]
	rutas.sort(key=lambda r: os.path.basename(r).casefold())
	return rutas or [ruta]


class VisorImagen:
	"""``self.marco`` es la ventana; ``complemento`` da describir y reconocer el texto."""

	def __init__(self, ui: Any, padre: wx.Window | None, complemento: Any, ruta: str, rutas: list[str] | None = None) -> None:
		self.ui = ui
		self.complemento = complemento
		self.rutas = rutas or [ruta]
		self.indice = self.rutas.index(ruta) if ruta in self.rutas else 0
		self.original: wx.Image | None = None
		self.informacion: exif.Informacion | None = None
		self.zoom = 1.0
		self.ajustada = True
		self.giro = 0
		self.contraste = False
		self._carga = 0
		self.marco = ui.VentanaComplemento(padre, _("Visor de imágenes"), complemento.zc.id)
		panel = wx.Panel(self.marco)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(wx.StaticText(panel, label=_("&Imagen:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		self.area = wx.ScrolledWindow(panel, style=wx.HSCROLL | wx.VSCROLL | wx.WANTS_CHARS, name=_("Imagen"))
		self.area.SetScrollRate(20, 20)
		self.area.SetHelpText(_("La imagen. Con el foco aquí, las flechas la desplazan cuando está ampliada."))
		self.area.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
		self.dibujo = wx.StaticBitmap(self.area)
		sizer.Add(self.area, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
		sizer.Add(wx.StaticText(panel, label=_("&Estado:")), 0, wx.LEFT | wx.RIGHT, 6)
		self.estado = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=panel.FromDIP(wx.Size(-1, 70)))
		self.estado.SetHelpText(_("Nombre, tamaño, ampliación, giro y posición de la imagen en la carpeta."))
		sizer.Add(self.estado, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
		rejilla = wx.WrapSizer(wx.HORIZONTAL)
		for etiqueta, ayuda, funcion in (
			(_("A&justar a la ventana"), _("Muestra la imagen entera en la ventana."), self.ajustar),
			(_("&Tamaño real"), _("Muestra la imagen al 100 %."), lambda: self.fijar_zoom(1.0)),
			(_("A&mpliar"), _("Amplía la imagen (también Más)."), lambda: self.cambiar_zoom(1)),
			(_("&Reducir"), _("Reduce la imagen (también Menos)."), lambda: self.cambiar_zoom(-1)),
			(_("Girar a la &derecha"), _("Gira la imagen 90 grados a la derecha (no cambia el archivo)."), lambda: self.girar(90)),
			(_("Girar a la i&zquierda"), _("Gira la imagen 90 grados a la izquierda (no cambia el archivo)."), lambda: self.girar(-90)),
			(_("&Siguiente imagen"), _("Abre la siguiente imagen de la carpeta (también Av Pág)."), lambda: self.mover(1)),
			(_("Imagen a&nterior"), _("Abre la imagen anterior de la carpeta (también Re Pág)."), lambda: self.mover(-1)),
			(_("Alto c&ontraste"), _("Muestra la imagen en grises con más contraste, o la devuelve a color."), self.cambiar_contraste),
			(_("Descri&bir..."), _("Pide la descripción de la imagen al servicio configurado."), self._describir),
			(_("Reconocer el te&xto"), _("Lee el texto de la imagen con el complemento de reconocimiento de texto."), self._reconocer),
			(_("In&formación"), _("Formato, dimensiones y datos EXIF de la foto."), self._informacion),
			(_("&Cerrar"), _("Cierra el visor (también Escape)."), lambda: self.marco.Close()),
		):
			boton = wx.Button(panel, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, f=funcion: f())
			rejilla.Add(boton, 0, wx.ALL, 3)
		sizer.Add(rejilla, 0, wx.EXPAND | wx.ALL, 3)
		panel.SetSizer(sizer)
		self.marco.SetSize(self.marco.FromDIP(wx.Size(900, 700)))
		panel.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self.area.Bind(wx.EVT_SIZE, self._al_redimensionar)
		self.cargar()

	@property
	def ruta(self) -> str:
		return self.rutas[self.indice]

	# ── Carga y pintado ──────────────────────────────────────────────────────

	def cargar(self) -> None:
		"""Abre la imagen en un hilo (una foto grande tarda) y la muestra al llegar."""
		self._carga += 1
		carga, ruta = self._carga, self.ruta
		self.estado.ChangeValue(_("Abriendo {n}...").format(n=os.path.basename(ruta)))

		def trabajo() -> None:
			try:
				informacion = exif.informacion(ruta)
				imagen = procesado.orientar(procesado.cargar(ruta), int(informacion.exif.get("orientacion", 1)))
				error = ""
			except (procesado.ErrorImagen, OSError, ValueError) as problema:
				informacion, imagen, error = None, None, str(getattr(problema, "strerror", None) or problema)
			wx.CallAfter(self._cargada, carga, imagen, informacion, error)

		threading.Thread(target=trabajo, name="zc-imagenes-visor", daemon=True).start()

	def _cargada(self, carga: int, imagen: wx.Image | None, informacion: exif.Informacion | None, error: str) -> None:
		if carga != self._carga or not self.marco:
			return
		self.original, self.informacion = imagen, informacion
		self.giro = 0
		if imagen is None:
			self.dibujo.SetBitmap(wx.NullBitmap)
			self.estado.ChangeValue(error)
			self.complemento.zc.anunciar(error, "esencial")
			return
		self.ajustada = True
		self.pintar()
		self.complemento.zc.anunciar(self.texto_estado(), "normal")

	def _imagen_vista(self) -> wx.Image | None:
		if self.original is None:
			return None
		imagen = procesado.girar(self.original, self.giro)
		return procesado.alto_contraste(imagen) if self.contraste else imagen

	def _zoom_ajustado(self, imagen: wx.Image) -> float:
		ancho, alto = self.area.GetClientSize()
		if imagen.GetWidth() <= 0 or imagen.GetHeight() <= 0 or ancho <= 10 or alto <= 10:
			return 1.0
		return min(ancho / imagen.GetWidth(), alto / imagen.GetHeight(), 1.0)

	def pintar(self) -> None:
		imagen = self._imagen_vista()
		if imagen is None:
			return
		if self.ajustada:
			self.zoom = self._zoom_ajustado(imagen)
		ancho = max(1, round(imagen.GetWidth() * self.zoom))
		alto = max(1, round(imagen.GetHeight() * self.zoom))
		escalada = imagen.Scale(ancho, alto, wx.IMAGE_QUALITY_HIGH) if (ancho, alto) != (imagen.GetWidth(), imagen.GetHeight()) else imagen
		self.dibujo.SetBitmap(wx.Bitmap(escalada))
		self.dibujo.SetSize(ancho, alto)
		self.area.SetVirtualSize(ancho, alto)
		self.estado.ChangeValue(self.texto_estado())

	def texto_estado(self) -> str:
		nombre = os.path.basename(self.ruta)
		if self.original is None:
			return nombre
		partes = [nombre]
		ancho, alto = self.original.GetWidth(), self.original.GetHeight()
		partes.append(_("{a} × {h} píxeles").format(a=ancho, h=alto))
		porcentaje = round(self.zoom * 100)
		partes.append(_("ajustada a la ventana, al {p} %").format(p=porcentaje) if self.ajustada else _("al {p} %").format(p=porcentaje))
		if self.giro % 360:
			partes.append(_("girada {g} grados").format(g=self.giro % 360))
		if self.contraste:
			partes.append(_("alto contraste"))
		if len(self.rutas) > 1:
			partes.append(_("imagen {n} de {t}").format(n=self.indice + 1, t=len(self.rutas)))
		return ", ".join(partes)

	def _al_redimensionar(self, evento: wx.SizeEvent) -> None:
		evento.Skip()
		if self.ajustada and self.original is not None:
			wx.CallAfter(self.pintar)

	# ── Acciones ─────────────────────────────────────────────────────────────

	def _decir(self) -> None:
		self.complemento.zc.anunciar(self.texto_estado(), "resultado")

	def ajustar(self) -> None:
		self.ajustada = True
		self.pintar()
		self._decir()

	def fijar_zoom(self, zoom: float) -> None:
		self.ajustada = False
		self.zoom = max(NIVELES_ZOOM[0], min(NIVELES_ZOOM[-1], zoom))
		self.pintar()
		self._decir()

	def cambiar_zoom(self, paso: int) -> None:
		if paso > 0:
			siguiente = next((n for n in NIVELES_ZOOM if n > self.zoom + 0.001), NIVELES_ZOOM[-1])
		else:
			siguiente = next((n for n in reversed(NIVELES_ZOOM) if n < self.zoom - 0.001), NIVELES_ZOOM[0])
		self.fijar_zoom(siguiente)

	def girar(self, grados: int) -> None:
		self.giro = (self.giro + grados) % 360
		self.pintar()
		self._decir()

	def cambiar_contraste(self) -> None:
		self.contraste = not self.contraste
		self.pintar()
		self._decir()

	def mover(self, paso: int) -> None:
		if len(self.rutas) <= 1:
			self.complemento.zc.anunciar(_("No hay más imágenes en esta carpeta"), "resultado")
			return
		nuevo = self.indice + paso
		if not 0 <= nuevo < len(self.rutas):
			self.complemento.zc.anunciar(_("Es la última imagen") if paso > 0 else _("Es la primera imagen"), "resultado")
			return
		self.indice = nuevo
		self.cargar()

	def _describir(self) -> None:
		self.complemento.describir(self.ruta, self.marco)

	def _reconocer(self) -> None:
		self.complemento.reconocer_texto(self.ruta)

	def _informacion(self) -> None:
		if self.informacion is None:
			return
		self.ui.mostrar_texto(_("Información de {n}").format(n=os.path.basename(self.ruta)), "\n".join(exif.lineas(self.informacion)))

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		codigo, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		caracter = chr(evento.GetUnicodeKey()) if evento.GetUnicodeKey() not in (0, wx.WXK_NONE) else ""
		if modificadores in (wx.MOD_NONE, wx.MOD_SHIFT):
			if caracter == "+" or codigo == wx.WXK_NUMPAD_ADD:
				self.cambiar_zoom(1)
				return
			if caracter == "-" or codigo == wx.WXK_NUMPAD_SUBTRACT:
				self.cambiar_zoom(-1)
				return
		if modificadores == wx.MOD_NONE:
			if codigo == wx.WXK_PAGEDOWN:
				self.mover(1)
				return
			if codigo == wx.WXK_PAGEUP:
				self.mover(-1)
				return
			if wx.Window.FindFocus() is self.area and codigo in (wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_UP, wx.WXK_DOWN):
				x, y = self.area.GetViewStart()
				dx = {wx.WXK_LEFT: -1, wx.WXK_RIGHT: 1}.get(codigo, 0)
				dy = {wx.WXK_UP: -1, wx.WXK_DOWN: 1}.get(codigo, 0)
				self.area.Scroll(max(0, x + dx * 3), max(0, y + dy * 3))
				return
		evento.Skip()


# ── Convertir o redimensionar ────────────────────────────────────────────────

FORMATOS_SALIDA = (("", "El mismo que el original"), ("jpeg", "JPEG"), ("png", "PNG"), ("bmp", "BMP"), ("tiff", "TIFF"),
	("gif", "GIF"))
GIROS = ((0, "No girar"), (90, "90 grados a la derecha"), (270, "90 grados a la izquierda"), (180, "180 grados"))
SI_EXISTE = (("preguntar", "Preguntar"), ("renombrar_copia", "Cambiar el nombre: «nombre (2)»"), ("omitir", "Omitir"),
	("sobrescribir", "Sobrescribir el que ya existe"))


class DialogoConvertir:
	"""Formato, tamaño máximo, giro, carpeta, nombre y «Si existe»."""

	def __init__(self, ui: Any, padre: wx.Window | None, cuantos: int, carpeta: str) -> None:
		self._ui = ui
		self.dialogo = wx.Dialog(padre, title=_("Convertir o redimensionar imágenes"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		panel = wx.Panel(self.dialogo)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(wx.StaticText(panel, label=_("Imágenes elegidas: {n}.").format(n=cuantos)), 0, wx.ALL, 5)
		_e, self.formato = ui.crear_campo(panel, _("&Formato:"), wx.Choice, choices=[_(t) for _v, t in FORMATOS_SALIDA],
			ayuda=_("Formato de las imágenes nuevas. La calidad de JPEG se elige en Preferencias."), sizer=sizer)
		self.formato.SetSelection(0)
		_e, self.ancho = ui.crear_campo(panel, _("Ancho &máximo en píxeles (0 sin límite):"), wx.SpinCtrl, min=0, max=50000,
			initial=0, ayuda=_("Las imágenes más anchas se reducen sin deformarse; las más pequeñas no se amplían."), sizer=sizer)
		_e, self.alto = ui.crear_campo(panel, _("Al&to máximo en píxeles (0 sin límite):"), wx.SpinCtrl, min=0, max=50000,
			initial=0, ayuda=_("Las imágenes más altas se reducen sin deformarse; las más pequeñas no se amplían."), sizer=sizer)
		_e, self.giro = ui.crear_campo(panel, _("&Girar:"), wx.Choice, choices=[_(t) for _v, t in GIROS],
			ayuda=_("Giro que se aplica a todas. Las fotos se ponen antes derechas según su EXIF."), sizer=sizer)
		self.giro.SetSelection(0)
		_e, self.carpeta = ui.crear_campo(panel, _("Carpeta de &salida:"), wx.TextCtrl, value=carpeta,
			ayuda=_("Dónde se crean las imágenes nuevas. Por defecto, la carpeta del otro panel."), sizer=sizer)
		self.examinar = wx.Button(panel, label=_("E&xaminar..."))
		self.examinar.SetHelpText(_("Abre un cuadro para elegir la carpeta de salida."))
		sizer.Add(self.examinar, 0, wx.LEFT | wx.BOTTOM, 5)
		_e, self.nombre = ui.crear_campo(panel, _("&Nombre:"), wx.TextCtrl, value="[N]",
			ayuda=_("Nombre de cada imagen nueva: [N] es el nombre original sin extensión y [C] un contador. La extensión se pone sola."),
			sizer=sizer)
		_e, self.si_existe = ui.crear_campo(panel, _("Si &existe:"), wx.Choice, choices=[_(t) for _v, t in SI_EXISTE],
			ayuda=_("Qué hacer si la imagen nueva ya existe. El original nunca se sobrescribe."), sizer=sizer)
		self.si_existe.SetSelection(0)
		sizer.Add(ui.crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.dialogo.SetSizerAndFit(marco)
		self.examinar.Bind(wx.EVT_BUTTON, self._al_examinar)
		ui.preparar_dialogo(self.dialogo, foco_inicial=self.formato)

	def _al_examinar(self, _evento: wx.CommandEvent) -> None:
		dialogo = wx.DirDialog(self.dialogo, _("Carpeta de salida"), self.carpeta.GetValue())
		try:
			if self._ui.mostrar_modal(dialogo) == wx.ID_OK:
				self.carpeta.SetValue(dialogo.GetPath())
		finally:
			dialogo.Destroy()
		self.carpeta.SetFocus()

	@property
	def valor_formato(self) -> str:
		return FORMATOS_SALIDA[max(0, self.formato.GetSelection())][0]

	@property
	def valor_giro(self) -> int:
		return GIROS[max(0, self.giro.GetSelection())][0]

	@property
	def valor_si_existe(self) -> str:
		return SI_EXISTE[max(0, self.si_existe.GetSelection())][0]
