# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Paquetes de sonidos y su asistente (diseño 2.0, 4.7). Orden ``sonidos_paquetes`` y botón de la página Sonidos.

Pantalla inicial: la lista de paquetes (de serie y propios) con «Nuevo a
partir de este...», «Editar...» (solo propios), «Exportar...», «Importar...»,
«Eliminar» (solo propios, con confirmación y el foco en «No»), «Usar este
paquete» y «Cerrar».

Crear o editar abre el asistente, con «< Atrás», «Siguiente >», «Terminar» y
«Cancelar», en cuatro pasos:

1. **Base**: paquete del que se parte (el elegido en la lista).
2. **Datos**: nombre, identificador (propuesto desde el nombre), autor,
   licencia (CC0-1.0, CC-BY-4.0, GPL-3.0-or-later u «Otra») y descripción.
3. **Sonidos**: categoría y lista (Evento, Origen: «Propio», «Heredado de
   Clásico»); «Probar», «Sustituir por un archivo WAV...» (valida el WAV),
   «Volver al heredado» y «Probar el original».
4. **Resumen**: cuántos sonidos propios y heredados, «Usar este paquete
   ahora» y «Exportar como .zcsonidos...».

Nada se escribe hasta «Terminar» (o «Exportar», que guarda antes). Las
letras de acceso son únicas en todo el asistente, contando sus botones.
"""

from __future__ import annotations

import builtins
import logging
from pathlib import Path
from typing import Any

import wx

from app.services.sonidos import catalogo, paquetes, wav
from app.ui import anuncios
from app.ui import sonidos as sonidos_ui
from app.ui.accesibilidad.dialogos import enfocar, preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.dialogos import so_comun, so_pagina_sonidos

log = logging.getLogger(__name__)

OTRA_LICENCIA = "Otra"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _anunciar(texto: str) -> None:
	anuncios.anunciar(texto, anuncios.RESULTADO)


def usar(config: Any, paquete: paquetes.Paquete) -> None:
	"""Elige el paquete y lo hace oír con el sonido de «Terminada»."""
	config.establecer("sonidos.paquete", paquete.id)
	sonidos_ui.recargar()
	_anunciar(_("Paquete de sonidos en uso: {n}").format(n=paquete.nombre))
	sonidos_ui.probar("op.fin", paquete=paquete.id)


def importar_con_pregunta(padre: wx.Window | None, config: Any, ruta: Path) -> paquetes.Paquete | None:
	"""Importa un ``.zcsonidos`` preguntando antes (y si sustituye a uno propio con el mismo id)."""
	try:
		manifiesto, _archivos = paquetes.leer_zcsonidos(ruta)
	except paquetes.ErrorPaquete as error:
		so_comun.error(padre, error.mensaje, _("No se puede importar el paquete de sonidos"))
		return None
	autor = manifiesto.get("autor") or _("autor desconocido")
	if not so_comun.preguntar(padre, _("¿Instalar el paquete de sonidos «{n}», de {a}?").format(n=manifiesto["nombre"], a=autor),
			_("Importar un paquete de sonidos")):
		return None
	try:
		try:
			paquete = paquetes.importar(ruta)
		except paquetes.PaqueteExiste as existe:
			if not so_comun.preguntar(padre, existe.mensaje + " " + _("¿Sustituirlo por el que importa?"), _("Importar un paquete de sonidos"),
					peligroso=True):
				return None
			paquete = paquetes.importar(ruta, sustituir=True)
	except paquetes.ErrorPaquete as error:
		so_comun.error(padre, error.mensaje, _("No se pudo importar el paquete de sonidos"))
		return None
	sonidos_ui.recargar()
	_anunciar(_("Paquete de sonidos instalado: {n}").format(n=paquete.nombre))
	if so_comun.preguntar(padre, _("¿Usar ahora el paquete «{n}»?").format(n=paquete.nombre), _("Importar un paquete de sonidos")):
		usar(config, paquete)
	return paquete


def exportar_con_pregunta(padre: wx.Window | None, paquete: paquetes.Paquete) -> Path | None:
	destino = so_comun.elegir_destino(padre, f"{paquete.id}{paquetes.EXTENSION}")
	if destino is None:
		return None
	try:
		final = paquetes.exportar(paquete.id, destino)
	except paquetes.ErrorPaquete as error:
		so_comun.error(padre, error.mensaje, _("No se pudo exportar el paquete de sonidos"))
		return None
	_anunciar(_("Paquete exportado a {r}").format(r=final))
	return final


# ── Pantalla inicial ─────────────────────────────────────────────────────────


class DialogoPaquetes(wx.Dialog):
	"""Lista de paquetes de sonidos instalados con sus acciones."""

	def __init__(self, padre: wx.Window | None, config: Any) -> None:
		super().__init__(padre, title=_("Paquetes de sonidos"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=_("Paquetes de sonidos"))
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.config = config
		self.paquetes: list[paquetes.Paquete] = []
		panel = wx.Panel(self)
		self.panel = panel
		sizer = wx.BoxSizer(wx.VERTICAL)
		borde = self.FromDIP(4)
		etiqueta = wx.StaticText(panel, label=_("&Paquetes instalados:"))
		self.lista = ListaAccesible(panel, _("Paquetes instalados"), columnas=[
			(_("Nombre"), self.FromDIP(180)), (_("Origen"), self.FromDIP(90)), (_("Estado"), self.FromDIP(80)),
			(_("Autor"), self.FromDIP(160)), (_("Licencia"), self.FromDIP(120)),
		])
		self.lista.SetMinSize(self.FromDIP(wx.Size(640, 200)))
		self.lista.SetHelpText(_("Paquetes de serie y propios. Intro usa el paquete elegido. Izquierda y Derecha leen las columnas."))
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.usar())
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda e: (self._actualizar_detalle(), e.Skip()))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, borde)
		etiqueta_detalle = wx.StaticText(panel, label=_("&Descripción:"))
		self.detalle = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=self.FromDIP(wx.Size(640, 80)))
		self.detalle.SetHelpText(_("Descripción del paquete elegido, de qué paquete hereda y cuántos sonidos propios tiene."))
		sizer.Add(etiqueta_detalle, 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		sizer.Add(self.detalle, 0, wx.EXPAND | wx.ALL, borde)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_nuevo = so_comun.boton(panel, _("&Nuevo a partir de este..."),
			_("Crea un paquete propio que parte del elegido: lo que no cambie lo hereda de él."), self.nuevo, fila)
		self.boton_editar = so_comun.boton(panel, _("&Editar..."), _("Cambia los datos y los sonidos de un paquete propio."), self.editar, fila)
		self.boton_exportar = so_comun.boton(panel, _("E&xportar..."), _("Guarda el paquete elegido en un archivo .zcsonidos para compartirlo."),
			self.exportar, fila)
		so_comun.boton(panel, _("&Importar..."), _("Instala un paquete de sonidos desde un archivo .zcsonidos."), self.importar, fila)
		self.boton_eliminar = so_comun.boton(panel, _("E&liminar"), _("Borra un paquete propio y sus sonidos (pide confirmación)."),
			self.eliminar, fila)
		self.boton_usar = so_comun.boton(panel, _("&Usar este paquete"), _("Hace que zCommander suene con el paquete elegido."), self.usar, fila)
		cerrar = wx.Button(panel, wx.ID_CANCEL, _("&Cerrar"))
		cerrar.SetHelpText(_("Cierra la lista de paquetes."))
		fila.Add(cerrar, 0, wx.ALL, self.FromDIP(3))
		sizer.Add(fila, 0)
		panel.SetSizer(sizer)
		externo = wx.BoxSizer(wx.VERTICAL)
		externo.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(externo)
		preparar_dialogo(self, id_escape=wx.ID_CANCEL, foco_inicial=self.lista)
		self.rellenar(str(config.obtener("sonidos.paquete") or paquetes.BASE))

	def rellenar(self, elegir: str | None = None) -> None:
		actual = elegir or (self.elegido().id if self.elegido() else None)
		en_uso = str(self.config.obtener("sonidos.paquete") or paquetes.BASE)
		self.paquetes = paquetes.listar()
		self.lista.reemplazar_filas([
			[p.nombre, _("De serie") if p.de_serie else _("Propio"), _("En uso") if p.id == en_uso else "", p.autor or "—", p.licencia or "—"]
			for p in self.paquetes
		], conservar_foco=False)
		ids = [p.id for p in self.paquetes]
		if ids:
			self.lista.enfocar_fila(ids.index(actual) if actual in ids else 0, anunciar=False)
		self._actualizar_detalle()

	def elegido(self) -> paquetes.Paquete | None:
		fila = self.lista.fila_actual() if self.paquetes else -1
		return self.paquetes[fila] if 0 <= fila < len(self.paquetes) else None

	def _actualizar_detalle(self) -> None:
		paquete = self.elegido()
		propio = paquete is not None and not paquete.de_serie
		self.boton_editar.Enable(propio)
		self.boton_eliminar.Enable(propio)
		for control in (self.boton_nuevo, self.boton_exportar, self.boton_usar):
			control.Enable(paquete is not None)
		if paquete is None:
			self.detalle.SetValue(_("No hay paquetes de sonidos instalados."))
			return
		propios, heredados = paquetes.contar(paquete)
		hereda = so_comun.nombre_paquete(paquete.hereda) if paquete.hereda else _("ninguno (es la base)")
		self.detalle.SetValue(_("{d}\nHereda de: {h}. Sonidos propios: {p}; heredados: {e}.").format(
			d=paquete.descripcion or _("Sin descripción."), h=hereda, p=propios, e=heredados))

	def nuevo(self) -> None:
		paquete = self.elegido()
		if paquete is None:
			return
		guardado = asistente(self, self.config, paquetes.Borrador.nuevo(paquete))
		self.rellenar(guardado.id if guardado else None)

	def editar(self) -> None:
		paquete = self.elegido()
		if paquete is None or paquete.de_serie:
			_anunciar(_("Los paquetes de serie no se pueden editar; cree uno nuevo a partir de él"))
			return
		guardado = asistente(self, self.config, paquetes.Borrador.editar(paquete))
		self.rellenar(guardado.id if guardado else paquete.id)

	def exportar(self) -> None:
		paquete = self.elegido()
		if paquete is not None:
			exportar_con_pregunta(self, paquete)

	def importar(self) -> None:
		ruta = so_comun.elegir_zcsonidos(self)
		if ruta is None:
			return
		paquete = importar_con_pregunta(self, self.config, ruta)
		self.rellenar(paquete.id if paquete else None)

	def eliminar(self) -> None:
		paquete = self.elegido()
		if paquete is None or paquete.de_serie:
			_anunciar(_("Los paquetes de serie no se pueden eliminar"))
			return
		if not so_comun.preguntar(self, _("¿Eliminar el paquete de sonidos «{n}»? Se borrarán sus sonidos y no se puede deshacer.").format(
				n=paquete.nombre), _("Eliminar un paquete de sonidos"), peligroso=True):
			return
		try:
			paquetes.eliminar(paquete.id)
		except paquetes.ErrorPaquete as error:
			so_comun.error(self, error.mensaje, _("No se pudo eliminar el paquete"))
			return
		if self.config.obtener("sonidos.paquete") == paquete.id:
			self.config.establecer("sonidos.paquete", paquetes.BASE)
		sonidos_ui.recargar()
		_anunciar(_("Paquete eliminado: {n}").format(n=paquete.nombre))
		self.rellenar(paquetes.BASE)

	def usar(self) -> None:
		paquete = self.elegido()
		if paquete is not None:
			usar(self.config, paquete)
			self.rellenar(paquete.id)


# ── Asistente ────────────────────────────────────────────────────────────────


class DialogoAsistente(wx.Dialog):
	"""Asistente de cuatro pasos para crear o editar un paquete propio. ``guardado`` queda con el resultado."""

	PASOS = ("Base", "Datos", "Sonidos", "Resumen")

	def __init__(self, padre: wx.Window | None, config: Any, borrador: paquetes.Borrador) -> None:
		self.editando = borrador.editando is not None
		titulo = _("Editar el paquete de sonidos") if self.editando else _("Nuevo paquete de sonidos")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.config = config
		self.borrador = borrador
		self.guardado: paquetes.Paquete | None = None
		self.resultado: dict[str, paquetes.Paquete] = {}
		self._titulo = titulo
		self._id_tocado = self.editando
		self._filas: list[tuple[catalogo.EventoSonido, str]] = []
		self._bases = [p for p in paquetes.listar() if not self.editando or p.id == borrador.base.id] or [borrador.base]
		self._categorias = so_pagina_sonidos.categorias()
		externo = wx.BoxSizer(wx.VERTICAL)
		self.libro = wx.Simplebook(self)
		self.paginas = [self._pagina_base(), self._pagina_datos(), self._pagina_sonidos(), self._pagina_resumen()]
		for pagina, nombre in zip(self.paginas, self.PASOS, strict=True):
			self.libro.AddPage(pagina, _(nombre))
		externo.Add(self.libro, 1, wx.EXPAND | wx.ALL, self.FromDIP(4))
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_atras = wx.Button(self, label=_("< &Atrás"))
		self.boton_atras.SetHelpText(_("Vuelve al paso anterior."))
		self.boton_siguiente = wx.Button(self, label=_("&Siguiente >"))
		self.boton_siguiente.SetHelpText(_("Pasa al paso siguiente."))
		self.boton_terminar = wx.Button(self, wx.ID_OK, _("&Terminar"))
		self.boton_terminar.SetHelpText(_("Guarda el paquete y cierra el asistente."))
		cancelar = wx.Button(self, wx.ID_CANCEL, _("&Cancelar"))
		cancelar.SetHelpText(_("Cierra el asistente sin guardar nada."))
		for control in (self.boton_atras, self.boton_siguiente, self.boton_terminar, cancelar):
			botones.Add(control, 0, wx.ALL, self.FromDIP(3))
		externo.Add(botones, 0, wx.ALIGN_RIGHT)
		self.boton_atras.Bind(wx.EVT_BUTTON, lambda _e: self.ir(self.libro.GetSelection() - 1))
		self.boton_siguiente.Bind(wx.EVT_BUTTON, lambda _e: self.ir(self.libro.GetSelection() + 1))
		self.boton_terminar.Bind(wx.EVT_BUTTON, lambda _e: self.terminar())
		self.SetSizerAndFit(externo)
		preparar_dialogo(self, id_escape=wx.ID_CANCEL)
		self.ir(1 if self.editando else 0, anunciar=False)

	# Paso 1: base
	def _pagina_base(self) -> wx.Panel:
		panel = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(panel, label=_("Paquete &base:"))
		self.base = wx.Choice(panel, choices=[p.etiqueta for p in self._bases])
		self.base.SetSelection(next((i for i, p in enumerate(self._bases) if p.id == self.borrador.base.id), 0))
		self.base.SetHelpText(_("Paquete del que parte el nuevo: lo que no cambie sonará como en él."))
		self.base.Bind(wx.EVT_CHOICE, lambda _e: self._cambiar_base())
		self.base.Enable(not self.editando)
		etiqueta_info = wx.StaticText(panel, label=_("In&formación del paquete base:"))
		self.info_base = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=self.FromDIP(wx.Size(560, 90)))
		for control in (etiqueta, self.base, etiqueta_info, self.info_base):
			sizer.Add(control, 0, wx.EXPAND | wx.ALL, self.FromDIP(4))
		panel.SetSizer(sizer)
		self._mostrar_info_base()
		return panel

	def _mostrar_info_base(self) -> None:
		base = self.borrador.base
		self.info_base.SetValue(_("{n}, de {a}. Licencia: {l}.\n{d}").format(n=base.nombre, a=base.autor or _("autor desconocido"),
			l=base.licencia or "—", d=base.descripcion or _("Sin descripción.")))

	def _cambiar_base(self) -> None:
		indice = self.base.GetSelection()
		if 0 <= indice < len(self._bases) and not self.editando:
			anterior = self.borrador
			self.borrador = paquetes.Borrador.nuevo(self._bases[indice])
			self.borrador.nombre, self.borrador.id = anterior.nombre, anterior.id
			self.borrador.autor, self.borrador.descripcion = anterior.autor, anterior.descripcion
			self._mostrar_info_base()

	# Paso 2: datos
	def _pagina_datos(self) -> wx.Panel:
		panel = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		borde = self.FromDIP(4)

		def campo(etiqueta: str, ayuda: str, **opciones) -> wx.TextCtrl:
			sizer.Add(wx.StaticText(panel, label=etiqueta), 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
			control = wx.TextCtrl(panel, **opciones)
			control.SetHelpText(ayuda)
			sizer.Add(control, 0, wx.EXPAND | wx.ALL, borde)
			return control

		self.nombre = campo(_("&Nombre:"), _("Nombre del paquete tal como aparecerá en las listas."), value=self.borrador.nombre)
		self.identificador = campo(_("&Identificador:"), _("Nombre de la carpeta: letras minúsculas sin tilde, números y guiones bajos."),
			value=self.borrador.id)
		self.identificador.SetEditable(not self.editando)
		self.autor = campo(_("A&utor:"), _("Quién hizo el paquete."), value=self.borrador.autor)
		sizer.Add(wx.StaticText(panel, label=_("&Licencia:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		self.licencia = wx.Choice(panel, choices=[*paquetes.LICENCIAS, _(OTRA_LICENCIA)])
		self.licencia.SetHelpText(_("Licencia con la que comparte los sonidos. CC0-1.0 los deja en el dominio público."))
		sizer.Add(self.licencia, 0, wx.ALL, borde)
		self.otra_licencia = campo(_("&Otra licencia:"), _("Escriba la licencia si eligió «Otra»."))
		self.descripcion = campo(_("&Descripción:"), _("Cómo suena el paquete o para qué sirve."), value=self.borrador.descripcion,
			style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(-1, 60)))
		if self.borrador.licencia in paquetes.LICENCIAS:
			self.licencia.SetSelection(paquetes.LICENCIAS.index(self.borrador.licencia))
		else:
			self.licencia.SetSelection(len(paquetes.LICENCIAS))
			self.otra_licencia.SetValue(self.borrador.licencia)
		self.otra_licencia.Enable(self.licencia.GetSelection() == len(paquetes.LICENCIAS))
		self.licencia.Bind(wx.EVT_CHOICE, lambda _e: self.otra_licencia.Enable(self.licencia.GetSelection() == len(paquetes.LICENCIAS)))
		self.nombre.Bind(wx.EVT_TEXT, self._al_cambiar_nombre)
		self.identificador.Bind(wx.EVT_TEXT, self._al_cambiar_id)
		panel.SetSizer(sizer)
		return panel

	def _al_cambiar_nombre(self, evento: wx.CommandEvent) -> None:
		if not self._id_tocado:
			self.identificador.ChangeValue(paquetes.proponer_id(self.nombre.GetValue()))
		evento.Skip()

	def _al_cambiar_id(self, evento: wx.CommandEvent) -> None:
		self._id_tocado = True
		evento.Skip()

	def _leer_datos(self) -> None:
		borrador = self.borrador
		borrador.nombre = self.nombre.GetValue().strip()
		borrador.id = self.identificador.GetValue().strip()
		borrador.autor = self.autor.GetValue().strip()
		indice = self.licencia.GetSelection()
		borrador.licencia = paquetes.LICENCIAS[indice] if 0 <= indice < len(paquetes.LICENCIAS) else self.otra_licencia.GetValue().strip()
		borrador.descripcion = self.descripcion.GetValue().strip()

	# Paso 3: sonidos
	def _pagina_sonidos(self) -> wx.Panel:
		panel = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		borde = self.FromDIP(4)
		sizer.Add(wx.StaticText(panel, label=_("Cate&goría:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		self.categoria = wx.Choice(panel, choices=[_("Todas")] + [n for _c, n in self._categorias])
		self.categoria.SetSelection(0)
		self.categoria.SetHelpText(_("Filtra la lista de sonidos por categoría."))
		self.categoria.Bind(wx.EVT_CHOICE, lambda _e: self.rellenar_sonidos())
		sizer.Add(self.categoria, 0, wx.EXPAND | wx.ALL, borde)
		sizer.Add(wx.StaticText(panel, label=_("&Eventos:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		self.sonidos = ListaAccesible(panel, _("Eventos"), columnas=[(_("Evento"), self.FromDIP(260)), (_("Origen"), self.FromDIP(200))])
		self.sonidos.SetMinSize(self.FromDIP(wx.Size(500, 220)))
		self.sonidos.SetHelpText(_("Cada sonido del paquete y de dónde sale: propio o heredado. Intro lo prueba."))
		self.sonidos.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.probar())
		sizer.Add(self.sonidos, 1, wx.EXPAND | wx.ALL, borde)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		so_comun.boton(panel, _("P&robar"), _("Hace sonar el sonido elegido tal como quedará en el paquete."), self.probar, fila)
		so_comun.boton(panel, _("Sustituir por un archivo &WAV..."),
			_("Elige un WAV (PCM de 8 o 16 bits, mono o estéreo, 10 segundos como máximo) para este sonido."), self.sustituir, fila)
		so_comun.boton(panel, _("&Volver al heredado"), _("Quita el sonido propio: sonará el del paquete del que hereda."),
			self.volver_al_heredado, fila)
		so_comun.boton(panel, _("&Probar el original"), _("Hace sonar el sonido heredado, sin el propio."), self.probar_original, fila)
		sizer.Add(fila, 0)
		panel.SetSizer(sizer)
		return panel

	def rellenar_sonidos(self) -> None:
		actual = self.elegido()
		indice = self.categoria.GetSelection()
		categoria = self._categorias[indice - 1][0] if indice > 0 else None
		self._filas = [(e, v) for e, v in paquetes.eventos_con_variantes() if categoria is None or e.categoria == categoria]
		self.sonidos.reemplazar_filas([[so_comun.nombre_evento(e, v), self.borrador.origen(e, v)] for e, v in self._filas],
			conservar_foco=False)
		if self._filas:
			self.sonidos.enfocar_fila(self._filas.index(actual) if actual in self._filas else 0, anunciar=False)

	def elegido(self) -> tuple[catalogo.EventoSonido, str] | None:
		fila = self.sonidos.fila_actual() if self._filas else -1
		return self._filas[fila] if 0 <= fila < len(self._filas) else None

	def _reproducir(self, ruta: Path | None, evento: catalogo.EventoSonido, variante: str) -> bool:
		if ruta is not None and sonidos_ui.probar_archivo(ruta):
			return True
		_anunciar(_("No suena «{n}»: no tiene sonido o el volumen está a 0").format(n=so_comun.nombre_evento(evento, variante)))
		return False

	def probar(self) -> bool:
		elegido = self.elegido()
		return bool(elegido) and self._reproducir(self.borrador.ruta(*elegido), *elegido)

	def probar_original(self) -> bool:
		elegido = self.elegido()
		return bool(elegido) and self._reproducir(self.borrador.heredado(*elegido), *elegido)

	def sustituir(self, ruta: Path | None = None) -> bool:
		elegido = self.elegido()
		if elegido is None:
			return False
		ruta = ruta or so_comun.elegir_wav(self)
		if ruta is None:
			return False
		try:
			self.borrador.sustituir(elegido[0], elegido[1], ruta)
		except wav.WavNoValido as error:
			so_comun.error(self, _("Ese archivo no se puede usar: {m}").format(m=error.mensaje), _("Sustituir un sonido"))
			return False
		self._actualizar_fila()
		_anunciar(_("Sonido sustituido: {n}").format(n=so_comun.nombre_evento(*elegido)))
		return True

	def volver_al_heredado(self) -> None:
		elegido = self.elegido()
		if elegido is None:
			return
		self.borrador.volver_al_heredado(*elegido)
		self._actualizar_fila()
		_anunciar(_("{n}: {o}").format(n=so_comun.nombre_evento(*elegido), o=self.borrador.origen(*elegido)))

	def _actualizar_fila(self) -> None:
		fila = self.sonidos.fila_actual()
		if 0 <= fila < len(self._filas):
			self.sonidos.actualizar_celda(fila, 1, self.borrador.origen(*self._filas[fila]))

	# Paso 4: resumen
	def _pagina_resumen(self) -> wx.Panel:
		panel = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		borde = self.FromDIP(4)
		sizer.Add(wx.StaticText(panel, label=_("Resu&men:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, borde)
		self.resumen = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=self.FromDIP(wx.Size(500, 100)))
		self.resumen.SetHelpText(_("Lo que se va a guardar."))
		sizer.Add(self.resumen, 1, wx.EXPAND | wx.ALL, borde)
		self.usar_ahora = wx.CheckBox(panel, label=_("Usar este paquete a&hora"))
		self.usar_ahora.SetValue(not self.editando or self.config.obtener("sonidos.paquete") == self.borrador.id)
		self.usar_ahora.SetHelpText(_("Al terminar, zCommander sonará con este paquete."))
		sizer.Add(self.usar_ahora, 0, wx.ALL, borde)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		so_comun.boton(panel, _("E&xportar como .zcsonidos..."), _("Guarda el paquete y lo exporta a un archivo para compartirlo."),
			self.exportar, fila)
		sizer.Add(fila, 0)
		panel.SetSizer(sizer)
		return panel

	def _rellenar_resumen(self) -> None:
		borrador = self.borrador
		propios, heredados = borrador.contar()
		self.resumen.SetValue(_("Paquete «{n}» ({i}), de {a}. Licencia: {l}.\nHereda de: {h}.\nSonidos propios: {p}. Sonidos heredados: {e}.").format(
			n=borrador.nombre, i=borrador.id, a=borrador.autor or _("autor sin indicar"), l=borrador.licencia or "—",
			h=so_comun.nombre_paquete(borrador.hereda), p=propios, e=heredados))

	# Navegación
	def ir(self, paso: int, anunciar: bool = True) -> bool:
		actual = self.libro.GetSelection()
		if actual == 1 and paso > actual:
			self._leer_datos()
			problemas = self.borrador.problemas()
			if problemas:
				so_comun.avisar(self, " ".join(problemas), self._titulo)
				enfocar(self.nombre if not self.borrador.nombre else self.identificador)
				return False
		elif actual == 1:
			self._leer_datos()
		paso = max(0 if not self.editando else 1, min(len(self.PASOS) - 1, paso))
		self.libro.SetSelection(paso)
		if paso == 2:
			self.rellenar_sonidos()
		if paso == 3:
			self._rellenar_resumen()
		self.boton_atras.Enable(paso > (1 if self.editando else 0))
		self.boton_siguiente.Enable(paso < len(self.PASOS) - 1)
		texto = _("Paso {n} de {t}: {p}").format(n=paso + 1, t=len(self.PASOS), p=_(self.PASOS[paso]))
		self.SetTitle(f"{self._titulo}. {texto}")
		foco = {0: self.base if self.base.IsEnabled() else self.info_base, 1: self.nombre, 2: self.sonidos, 3: self.resumen}[paso]
		if anunciar:
			_anunciar(texto)
		enfocar(foco)
		return True

	def _guardar(self) -> paquetes.Paquete | None:
		if self.libro.GetSelection() == 1:
			self._leer_datos()
		problemas = self.borrador.problemas()
		if problemas:
			so_comun.avisar(self, " ".join(problemas), self._titulo)
			self.ir(1, anunciar=False)
			return None
		try:
			guardado = paquetes.guardar(self.borrador)
		except paquetes.ErrorPaquete as error:
			so_comun.error(self, error.mensaje, self._titulo)
			return None
		self.guardado = guardado
		self.resultado["paquete"] = guardado
		# A partir de aquí se edita lo ya guardado (por si se exporta y después se sigue).
		self.borrador = paquetes.Borrador.editar(guardado)
		self.editando = True
		self.identificador.SetEditable(False)
		sonidos_ui.recargar()
		return guardado

	def exportar(self) -> None:
		guardado = self._guardar()
		if guardado is not None:
			exportar_con_pregunta(self, guardado)
			self._rellenar_resumen()

	def terminar(self) -> bool:
		guardado = self._guardar()
		if guardado is None:
			return False
		if self.usar_ahora.GetValue():
			usar(self.config, guardado)
		else:
			_anunciar(_("Paquete guardado: {n}").format(n=guardado.nombre))
		if self.IsModal():
			self.EndModal(wx.ID_OK)
		return True


def asistente(padre: wx.Window | None, config: Any, borrador: paquetes.Borrador) -> paquetes.Paquete | None:
	"""Abre el asistente; devuelve el paquete guardado (o ``None`` si se canceló sin guardar)."""
	resultado: dict[str, paquetes.Paquete] = {}
	dialogo = DialogoAsistente(padre, config, borrador)
	dialogo.resultado = resultado
	so_comun.mostrar_modal(dialogo)
	return resultado.get("paquete")


def abrir(padre: wx.Window | None, config: Any) -> None:
	"""Pantalla inicial de los paquetes de sonidos."""
	so_comun.mostrar_modal(DialogoPaquetes(padre, config))
