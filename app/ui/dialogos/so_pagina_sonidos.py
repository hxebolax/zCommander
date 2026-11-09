# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Página «Sonidos» de Preferencias (diseño 2.0, 4.5). Página propia (``PAGINAS_PROPIAS``).

Controles, en este orden de creación (cada etiqueta antes de su control):

1. «Activar los sonidos» (``sonidos.activos``).
2. «Volumen:», ``SliderAccesible`` de 0 a 100 que el lector lee «70 de 100»
   (``sonidos.volumen``); al soltarlo suena «Información» con el volumen nuevo.
3. «Paquete:», los paquetes instalados («Clásico, de serie», «Mi paquete, propio»).
4. «Categoría:», «Todas» y las categorías del catálogo (filtra la lista).
5. «Sonidos:», ``CheckListBoxAccesible`` con «Nombre: cuándo suena» y su
   estado marcado; Espacio activa o desactiva, Ctrl+A y Ctrl+Mayús+A todos y
   ninguno de la categoría visible, Intro lo prueba. Se guarda en
   ``sonidos.eventos`` solo lo distinto de fábrica.
6. «Probar»: el evento elegido con el paquete y el volumen elegidos, aunque esté desactivado.
7. «Progreso de las operaciones:» No, Cada 25 %, Cada 10 % (``sonidos.progreso``).
8. «Los sonidos sustituyen a algunos anuncios» (``sonidos.sustituir_anuncios``).
9. «Intervalo mínimo de los sonidos de navegación (milisegundos):».
10. «Restablecer los sonidos de fábrica» (solo la lista) y «Paquetes de sonidos...».

Las letras de acceso no chocan con las de los botones del diálogo de
Preferencias (Aceptar, Cancelar, Aplicar y Restablecer valores de fábrica) ni
con las que ya usaban estas claves en la 1.x. Nada se guarda hasta
``aplicar()`` (Aceptar o Aplicar); Cancelar deja la configuración como estaba.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

import wx

from app.services.sonidos import catalogo, paquetes
from app.ui import anuncios
from app.ui import sonidos as sonidos_ui
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.controles import SliderAccesible

log = logging.getLogger(__name__)

#: Evento que se elige al abrir la página (lo fija «Ir a las preferencias» del mapa de sonidos).
EVENTO_INICIAL: list[str | None] = [None]
PROGRESO = (("no", "No"), ("cada_25", "Cada 25 %"), ("cada_10", "Cada 10 %"))
_CLAVES = ("sonidos.activos", "sonidos.volumen", "sonidos.paquete", "sonidos.eventos", "sonidos.progreso",
	"sonidos.sustituir_anuncios", "sonidos.intervalo_navegacion_ms")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def texto_evento(evento: catalogo.EventoSonido) -> str:
	"""«Carpeta vacía: La carpeta abierta no tiene elementos» (lo que lee el lector en la lista)."""
	nombre = _(evento.nombre)
	descripcion = _(evento.descripcion).strip() if evento.descripcion else ""
	return f"{nombre}: {descripcion}" if descripcion else nombre


def categorias() -> list[tuple[str, str]]:
	"""(categoría, nombre visible) en el orden del catálogo, sin repetir."""
	vistas: dict[str, str] = {}
	for evento in catalogo.eventos():
		if evento.categoria not in vistas:
			nombre = catalogo.nombre_categoria(evento.categoria)
			vistas[evento.categoria] = _("Complemento {n}").format(n=nombre) if evento.categoria.startswith("plugin:") else nombre
	return list(vistas.items())


class PaginaSonidos(wx.Panel):
	"""Cumple ``PaginaPropia``: ``validar``, ``aplicar``, ``restablecer`` y ``control_inicial``."""

	def __init__(self, padre: wx.Window, config: Any) -> None:
		super().__init__(padre, name=_("Sonidos"))
		self.config = config
		self._fabrica = catalogo.por_defecto()
		self._estado: dict[str, bool] = {}
		self._visibles: list[str] = []
		self._paquetes: list[paquetes.Paquete] = []
		self._categorias = categorias()
		self._muestra: wx.CallLater | None = None
		#: Se abrió desde el mapa de sonidos con un evento: el foco empieza en la lista.
		self.desde_mapa = False
		self._construir()
		self._cargar_desde_config()
		inicial, EVENTO_INICIAL[0] = EVENTO_INICIAL[0], None
		if inicial:
			self.elegir_evento(inicial)
			self.desde_mapa = True

	# ── Construcción ───────────────────────────────────────────────────────

	def _construir(self) -> None:
		sizer = wx.BoxSizer(wx.VERTICAL)
		borde = self.FromDIP(4)
		self.activos = wx.CheckBox(self, label=_("Activar &los sonidos"))
		self.activos.SetHelpText(_("Sonidos que acompañan a lo que pasa en zCommander. También con Control más F11."))
		sizer.Add(self.activos, 0, wx.ALL, borde)

		etiqueta_volumen = wx.StaticText(self, label=_("V&olumen:"))
		self.volumen = SliderAccesible(self, valor=70, minimo=0, maximo=100, paso=5, paso_pagina=10)
		self.volumen.SetHelpText(_("De 0 a 100. Al soltarlo suena un sonido de prueba con el volumen nuevo; 0 es silencio."))
		self.volumen.Bind(wx.EVT_SCROLL_CHANGED, self._al_soltar_volumen)
		sizer.Add(etiqueta_volumen, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.volumen, 0, wx.EXPAND | wx.ALL, borde)

		etiqueta_paquete = wx.StaticText(self, label=_("Pa&quete:"))
		self.paquete = wx.Choice(self)
		self.paquete.SetHelpText(_("Paquete de sonidos elegido. Lo que le falte a un paquete propio sale del paquete del que hereda."))
		sizer.Add(etiqueta_paquete, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.paquete, 0, wx.EXPAND | wx.ALL, borde)

		etiqueta_categoria = wx.StaticText(self, label=_("Ca&tegoría:"))
		self.categoria = wx.Choice(self, choices=[_("Todas")] + [nombre for _c, nombre in self._categorias])
		self.categoria.SetSelection(0)
		self.categoria.SetHelpText(_("Filtra la lista de sonidos por categoría."))
		self.categoria.Bind(wx.EVT_CHOICE, lambda _e: self._rellenar_lista())
		sizer.Add(etiqueta_categoria, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.categoria, 0, wx.EXPAND | wx.ALL, borde)

		etiqueta_lista = wx.StaticText(self, label=_("So&nidos:"))
		self.lista = CheckListBoxAccesible(self, _("Sonidos"), size=self.FromDIP(wx.Size(420, 200)))
		self.lista.SetHelpText(_(
			"Lista de casillas: cada sonido marcado suena. Espacio lo activa o lo desactiva, Intro lo prueba, "
			"Control+A marca todos los de la categoría visible y Control+Mayúsculas+A los desmarca."
		))
		self.lista.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_lista)
		sizer.Add(etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, borde)

		self.boton_probar = wx.Button(self, label=_("Pro&bar"))
		self.boton_probar.SetHelpText(_("Hace sonar el sonido elegido con el paquete y el volumen de esta página, aunque esté desactivado."))
		self.boton_probar.Bind(wx.EVT_BUTTON, lambda _e: self.probar())
		sizer.Add(self.boton_probar, 0, wx.ALL, borde)

		etiqueta_progreso = wx.StaticText(self, label=_("Progreso &de las operaciones:"))
		self.progreso = wx.Choice(self, choices=[_(texto) for _v, texto in PROGRESO])
		self.progreso.SetHelpText(_("Sonidos del progreso de copias y otras operaciones: nunca, cada 25 % o cada 10 %. El tono sube con el porcentaje."))
		sizer.Add(etiqueta_progreso, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.progreso, 0, wx.ALL, borde)

		self.sustituir = wx.CheckBox(self, label=_("Los &sonidos sustituyen a algunos anuncios"))
		self.sustituir.SetHelpText(_(
			"Si un evento tiene sonido activo, no se dice su anuncio breve (por ejemplo, Marcado). Los errores y las preguntas se dicen siempre."
		))
		sizer.Add(self.sustituir, 0, wx.ALL, borde)

		etiqueta_intervalo = wx.StaticText(self, label=_("&Intervalo mínimo de los sonidos de navegación (milisegundos):"))
		self.intervalo = wx.SpinCtrl(self, min=0, max=500, initial=40)
		self.intervalo.SetHelpText(_("Como mucho un sonido de navegación en este tiempo, de 0 a 500 milisegundos."))
		sizer.Add(etiqueta_intervalo, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.intervalo, 0, wx.ALL, borde)

		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_fabrica = wx.Button(self, label=_("Restablecer los sonidos de &fábrica"))
		self.boton_fabrica.SetHelpText(_("Vuelve a dejar activos solo los sonidos que vienen activos de fábrica. Se guarda al aceptar."))
		self.boton_fabrica.Bind(wx.EVT_BUTTON, lambda _e: self.restablecer_sonidos())
		self.boton_paquetes = wx.Button(self, label=_("Paqu&etes de sonidos..."))
		self.boton_paquetes.SetHelpText(_("Crea, edita, exporta, importa y elimina paquetes de sonidos."))
		self.boton_paquetes.Bind(wx.EVT_BUTTON, lambda _e: self._abrir_paquetes())
		botones.Add(self.boton_fabrica, 0, wx.RIGHT, borde)
		botones.Add(self.boton_paquetes, 0)
		sizer.Add(botones, 0, wx.ALL, borde)
		self.SetSizer(sizer)

	# ── Datos ─────────────────────────────────────────────────────────────

	def _cargar_paquetes(self, elegido: str) -> None:
		self._paquetes = paquetes.listar()
		etiquetas = [p.etiqueta for p in self._paquetes]
		if elegido not in {p.id for p in self._paquetes}:
			# El paquete guardado no está instalado: se muestra para no perderlo (suena el clásico).
			self._paquetes.append(paquetes.Paquete(id=elegido, nombre=elegido, carpeta=paquetes.carpeta_propios() / elegido, de_serie=False))
			etiquetas.append(_("{n} (no instalado)").format(n=elegido))
		self.paquete.Set(etiquetas)
		self.paquete.SetSelection(next(i for i, p in enumerate(self._paquetes) if p.id == elegido))

	def _cargar_desde_config(self) -> None:
		obtener = self.config.obtener
		self.activos.SetValue(bool(obtener("sonidos.activos")))
		self.volumen.SetValue(int(obtener("sonidos.volumen")))
		self._cargar_paquetes(str(obtener("sonidos.paquete") or paquetes.BASE))
		cambios = obtener("sonidos.eventos") or {}
		self._estado = {id_: bool(cambios.get(id_, fabrica)) for id_, fabrica in self._fabrica.items()}
		valores = [v for v, _t in PROGRESO]
		progreso = obtener("sonidos.progreso")
		self.progreso.SetSelection(valores.index(progreso) if progreso in valores else 0)
		self.sustituir.SetValue(bool(obtener("sonidos.sustituir_anuncios")))
		self.intervalo.SetValue(int(obtener("sonidos.intervalo_navegacion_ms")))
		self._rellenar_lista()

	def _guardar_visibles(self) -> None:
		"""Pasa al estado lo marcado en la lista visible (Ctrl+A marca desde código sin evento)."""
		for indice, id_ in enumerate(self._visibles):
			self._estado[id_] = self.lista.IsChecked(indice)

	def _rellenar_lista(self, conservar: str | None = None) -> None:
		if self._visibles:
			self._guardar_visibles()
		actual = conservar or self.evento_elegido()
		indice_categoria = self.categoria.GetSelection()
		filtro = self._categorias[indice_categoria - 1][0] if indice_categoria > 0 else None
		eventos = [e for e in catalogo.eventos() if filtro is None or e.categoria == filtro]
		self._visibles = [e.id for e in eventos]
		self.lista.Set([texto_evento(e) for e in eventos])
		for indice, evento in enumerate(eventos):
			if self._estado.get(evento.id, False):
				super(CheckListBoxAccesible, self.lista).Check(indice, True)
		if self._visibles:
			self.lista.SetSelection(self._visibles.index(actual) if actual in self._visibles else 0)

	def evento_elegido(self) -> str | None:
		indice = self.lista.GetSelection() if self._visibles else wx.NOT_FOUND
		return self._visibles[indice] if 0 <= indice < len(self._visibles) else None

	def elegir_evento(self, id_evento: str) -> None:
		"""Muestra la categoría del evento y lo deja elegido en la lista (mapa → «Ir a las preferencias»)."""
		evento = catalogo.evento(id_evento)
		if evento is None:
			return
		indice = next((i for i, (c, _n) in enumerate(self._categorias) if c == evento.categoria), None)
		if indice is not None:
			self.categoria.SetSelection(indice + 1)
		self._rellenar_lista(conservar=id_evento)

	def estado_eventos(self) -> dict[str, bool]:
		"""Activo o no, de todos los eventos, con lo marcado en la lista."""
		self._guardar_visibles()
		return dict(self._estado)

	def paquete_elegido(self) -> str:
		indice = self.paquete.GetSelection()
		return self._paquetes[indice].id if 0 <= indice < len(self._paquetes) else paquetes.BASE

	# ── Acciones ──────────────────────────────────────────────────────────

	def probar(self) -> bool:
		id_evento = self.evento_elegido()
		if id_evento is None:
			anuncios.anunciar(_("No hay ningún sonido elegido"), anuncios.RESULTADO)
			return False
		if self.volumen.GetValue() <= 0:
			anuncios.anunciar(_("El volumen está a 0: no suena nada"), anuncios.RESULTADO)
			return False
		sonado = sonidos_ui.probar(id_evento, paquete=self.paquete_elegido(), volumen=self.volumen.GetValue())
		if not sonado:
			evento = catalogo.evento(id_evento)
			anuncios.anunciar(_("No hay sonido para «{n}» en este paquete").format(n=_(evento.nombre) if evento else id_evento),
				anuncios.RESULTADO)
		return sonado

	def _al_pulsar_lista(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.GetModifiers() == wx.MOD_NONE:
			self.probar()
			return
		evento.Skip()

	def _al_soltar_volumen(self, evento: wx.ScrollEvent) -> None:
		# Una sola muestra cuando se deja de mover (no una por cada pulsación de flecha).
		if self._muestra is not None and self._muestra.IsRunning():
			self._muestra.Stop()
		self._muestra = wx.CallLater(300, self._muestra_volumen)
		evento.Skip()

	def _muestra_volumen(self) -> None:
		if self and self.volumen.GetValue() > 0:
			sonidos_ui.probar("aviso.informacion", paquete=self.paquete_elegido(), volumen=self.volumen.GetValue())

	def restablecer_sonidos(self) -> None:
		"""Botón «Restablecer los sonidos de fábrica»: solo la lista (se guarda al aceptar)."""
		actual = self.evento_elegido()
		self._visibles = []
		self._estado = dict(self._fabrica)
		self._rellenar_lista(conservar=actual)
		anuncios.anunciar(_("Sonidos de fábrica restablecidos; se guardarán al aceptar"), anuncios.RESULTADO)

	def _abrir_paquetes(self) -> None:
		from app.ui.dialogos import so_paquetes

		so_paquetes.abrir(self, self.config)
		self._cargar_paquetes(str(self.config.obtener("sonidos.paquete") or self.paquete_elegido()))

	# ── PaginaPropia ──────────────────────────────────────────────────────

	def validar(self) -> str | None:
		if not 0 <= self.intervalo.GetValue() <= 500:
			return _("El intervalo de los sonidos de navegación debe estar entre 0 y 500 milisegundos.")
		return None

	def aplicar(self) -> bool:
		if self.validar() is not None:
			return False
		estado = self.estado_eventos()
		cambios = {id_: activo for id_, activo in estado.items() if activo != self._fabrica.get(id_, False)}
		self.config.establecer_varias({
			"sonidos.activos": self.activos.GetValue(),
			"sonidos.paquete": self.paquete_elegido(),
			"sonidos.eventos": cambios,
			"sonidos.progreso": PROGRESO[max(0, self.progreso.GetSelection())][0],
			"sonidos.sustituir_anuncios": self.sustituir.GetValue(),
			"sonidos.intervalo_navegacion_ms": int(self.intervalo.GetValue()),
		})
		# El volumen cambia a menudo: guardado diferido (4.5).
		self.config.establecer_diferido("sonidos.volumen", int(self.volumen.GetValue()))
		return True

	def restablecer(self) -> None:
		"""Valores de fábrica de toda la página (se guardan al aceptar)."""
		por_defecto = self.config.valor_por_defecto
		self.activos.SetValue(bool(por_defecto("sonidos.activos")))
		self.volumen.SetValue(int(por_defecto("sonidos.volumen")))
		self._cargar_paquetes(str(por_defecto("sonidos.paquete")))
		valores = [v for v, _t in PROGRESO]
		self.progreso.SetSelection(valores.index(por_defecto("sonidos.progreso")))
		self.sustituir.SetValue(bool(por_defecto("sonidos.sustituir_anuncios")))
		self.intervalo.SetValue(int(por_defecto("sonidos.intervalo_navegacion_ms")))
		self._visibles = []
		self._estado = dict(self._fabrica)
		self._rellenar_lista()

	def control_inicial(self) -> wx.Window:
		return self.lista if self.desde_mapa else self.activos


def crear(padre: wx.Window, config: Any) -> PaginaSonidos:
	"""Fábrica de la página propia Sonidos (``PAGINAS_PROPIAS``)."""
	return PaginaSonidos(padre, config)
