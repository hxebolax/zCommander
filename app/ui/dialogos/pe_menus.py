# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Personalizar menús y barras (diseño 2.0, 10.6; orden ``personalizar_menus``).

Cuatro pestañas:

- **Menús**: lista con casillas de todos los elementos de los menús de fábrica
  («Archivos, Marcas, Marcar por patrón»): desmarcado = oculto. No se pueden
  reordenar (el manual sigue valiendo para todo el mundo); lo oculto conserva
  su tecla y sigue en la paleta.
- **Mis órdenes** y **Barra de botones**: listas propias con «Añadir una
  orden...» (el buscador de la paleta), separadores, Subir, Bajar y Quitar.
- **Barra de teclas**: cada hueco (F1 a F10 con o sin Mayús, Ctrl o Alt) puede
  llevar otra orden; la tecla pasa a esa orden (se pregunta si era de otra).

Se usa una lista con casillas y no un árbol con casillas: el árbol de wx no
anuncia el estado de sus casillas con los lectores de pantalla.
Aceptar guarda todo en ``menus.json`` (y las teclas en ``teclado.personalizadas``).
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import menus_personalizados as mp
from app.services import teclas as servicio_teclas
from app.services.teclas import nombre_visible
from app.ui import anuncios, ordenes
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.dialogos import f_comun, pe_comun

log = logging.getLogger(__name__)

NOMBRES_MODIFICADOR = {"": "", "Shift": "Mayús+", "Ctrl": "Ctrl+", "Alt": "Alt+"}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _etiqueta(id_orden: str) -> str:
	from app.ui.acciones.personalizar_pe import etiqueta

	return etiqueta(id_orden)


def _limpio(texto: str) -> str:
	return f_comun.texto_limpio(_(texto)).rstrip(".")


def elementos_de_fabrica() -> list[tuple[str, str]]:
	"""(id, «Archivos, Marcas, Marcar por patrón») de los menús de fábrica, sin repetir ids."""
	resultado: list[tuple[str, str]] = []
	vistos: set[str] = set()

	def recorrer(elementos, camino: str) -> None:
		for elemento in elementos:
			if elemento is None:
				continue
			if isinstance(elemento, tuple):
				recorrer(elemento[1], f"{camino}, {_limpio(elemento[0])}")
				continue
			if elemento in vistos or elemento not in ordenes.POR_ID or elemento == mp.TODAS:
				continue
			vistos.add(elemento)
			resultado.append((elemento, f"{camino}, {_etiqueta(elemento)}"))

	for titulo, contenido in ordenes.MENUS:
		if contenido == ordenes.LADO:
			recorrer(ordenes.MENU_LADO, _("Izquierdo y Derecho"))  # el segundo lado no añade nada (ids ya vistos)
			continue
		recorrer(contenido, _limpio(titulo))
	return resultado


class _PaginaLista(wx.Panel):
	"""Lista ordenada de órdenes y separadores (Mis órdenes, barra de botones)."""

	def __init__(self, padre: wx.Window, dialogo: DialogoMenus, etiqueta: str, elementos: list[str], fabrica: list[str]) -> None:
		super().__init__(padre)
		self.dialogo = dialogo
		self.elementos = list(elementos)
		self.fabrica = list(fabrica)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.etiqueta = wx.StaticText(self, label=etiqueta)
		self.lista = ListaAccesible(self, f_comun.texto_limpio(etiqueta).rstrip(":"), columnas=[(_("Elemento"), self.FromDIP(360))])
		self.lista.SetMinSize(self.FromDIP(wx.Size(380, 220)))
		self.lista.SetHelpText(_("Los elementos en su orden. Los separadores dividen grupos."))
		sizer.Add(self.etiqueta, 0, wx.ALL, self.FromDIP(4))
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(4))
		fila = wx.WrapSizer(wx.HORIZONTAL)
		for texto, ayuda, accion in (
			(_("Añadir una &orden..."), _("Elige una orden con el buscador de la paleta y la añade tras la elegida."), self.anadir),
			(_("&Separador"), _("Añade un separador tras el elemento elegido."), self.separador),
			(_("S&ubir"), _("Sube el elemento elegido."), lambda: self.mover(-1)),
			(_("&Bajar"), _("Baja el elemento elegido."), lambda: self.mover(1)),
			(_("&Quitar"), _("Quita el elemento elegido."), self.quitar),
			(_("&Restablecer esta pestaña"), _("Vuelve a lo de fábrica en esta pestaña."), self.restablecer),
		):
			boton = wx.Button(self, label=texto)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, a=accion: a())
			fila.Add(boton, 0, wx.ALL, self.FromDIP(3))
		sizer.Add(fila, 0, wx.EXPAND)
		self.SetSizer(sizer)
		self.rellenar(0)

	def texto(self, elemento: str) -> str:
		return _("(separador)") if elemento == mp.SEPARADOR else _etiqueta(elemento)

	def rellenar(self, foco: int) -> None:
		self.lista.reemplazar_filas([[self.texto(e)] for e in self.elementos], conservar_foco=False)
		if self.elementos:
			self.lista.enfocar_fila(min(max(foco, 0), len(self.elementos) - 1), anunciar=False)

	def indice(self) -> int:
		fila = self.lista.fila_actual()
		return fila if 0 <= fila < len(self.elementos) else -1

	def insertar(self, elemento: str) -> None:
		posicion = self.indice() + 1 if self.indice() >= 0 else len(self.elementos)
		self.elementos.insert(posicion, elemento)
		self.rellenar(posicion)
		self.lista.SetFocus()
		anuncios.anunciar(_("Añadido: {e}").format(e=self.texto(elemento)), anuncios.RESULTADO)

	def anadir(self) -> None:
		id_orden = pe_comun.elegir_orden(self.dialogo, _("Añadir una orden"))
		if id_orden:
			self.insertar(id_orden)

	def separador(self) -> None:
		self.insertar(mp.SEPARADOR)

	def mover(self, paso: int) -> None:
		i = self.indice()
		destino = mp.mover(self.elementos, i, paso)
		if destino != i:
			self.rellenar(destino)
			self.lista.SetFocus()
			anuncios.anunciar(_("Posición {n} de {t}").format(n=destino + 1, t=len(self.elementos)), anuncios.RESULTADO)

	def quitar(self) -> None:
		i = self.indice()
		if i < 0:
			return
		quitado = self.elementos.pop(i)
		self.rellenar(i)
		self.lista.SetFocus()
		anuncios.anunciar(_("Quitado: {e}").format(e=self.texto(quitado)), anuncios.RESULTADO)

	def restablecer(self) -> None:
		self.elementos = list(self.fabrica)
		self.rellenar(0)
		anuncios.anunciar(_("Pestaña restablecida"), anuncios.RESULTADO)


class DialogoMenus(f_comun.DialogoF):
	"""``datos`` y ``teclas`` quedan con lo elegido al aceptar."""

	def __init__(self, padre: wx.Window | None, datos: mp.DatosMenus, mapa=None, esquema: str = "norton") -> None:
		super().__init__(padre, _("Personalizar menús y barras"))
		self.datos = mp.copia(datos)
		self._mapa = mapa
		self._esquema = esquema
		self.asignadas: dict[str, tuple[str, ...]] = dict(mapa.como_dict()) if mapa is not None else {
			o: tuple(t) for o, t in ordenes.teclas_por_defecto(esquema).items()}
		self.cambios_teclas = False
		self.libro = wx.Notebook(self.panel)
		self.libro.SetHelpText(_("Pestañas: Menús, Mis órdenes, Barra de botones y Barra de teclas. Control+Tab cambia de pestaña."))
		# 1. Menús
		pagina = wx.Panel(self.libro)
		caja = wx.BoxSizer(wx.VERTICAL)
		self.fabrica = elementos_de_fabrica()
		etiqueta = wx.StaticText(pagina, label=_("&Elementos de los menús (marcados se ven):"))
		self.casillas = CheckListBoxAccesible(pagina, _("Elementos de los menús"), [t for _i, t in self.fabrica], recordar_posicion=False,
			size=self.FromDIP(wx.Size(440, 260)))
		self.casillas.SetHelpText(_("Desmarque lo que no quiera ver en los menús. Lo oculto sigue con su tecla y en la paleta."))
		for indice, (id_orden, _t) in enumerate(self.fabrica):
			self.casillas.Check(indice, id_orden not in self.datos.ocultas)
		if self.fabrica:
			self.casillas.SetSelection(0)
		boton = wx.Button(pagina, label=_("&Restablecer esta pestaña"))
		boton.SetHelpText(_("Vuelve a mostrar todos los elementos."))
		boton.Bind(wx.EVT_BUTTON, lambda _e: self.casillas.marcar_todas(True))
		caja.Add(etiqueta, 0, wx.ALL, self.FromDIP(4))
		caja.Add(self.casillas, 1, wx.EXPAND | wx.ALL, self.FromDIP(4))
		caja.Add(boton, 0, wx.ALL, self.FromDIP(4))
		pagina.SetSizer(caja)
		self.libro.AddPage(pagina, _("Menús"))
		# 2 y 3. Mis órdenes y barra de botones
		self.mis = _PaginaLista(self.libro, self, _("Elemen&tos de Mis órdenes:"), self.datos.mis_ordenes, [])
		self.libro.AddPage(self.mis, _("Mis órdenes"))
		botones = self.datos.barra_botones or list(mp.BOTONES_FABRICA)
		self.botones = _PaginaLista(self.libro, self, _("Elemen&tos de la barra de botones:"), botones, list(mp.BOTONES_FABRICA))
		self.libro.AddPage(self.botones, _("Barra de botones"))
		# 4. Barra de teclas
		pagina_teclas = wx.Panel(self.libro)
		caja = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(pagina_teclas, label=_("&Huecos de la barra de teclas:"))
		self.huecos = ListaAccesible(pagina_teclas, _("Huecos de la barra de teclas"),
			columnas=[(_("Tecla"), self.FromDIP(110)), (_("Orden"), self.FromDIP(240)), (_("Etiqueta"), self.FromDIP(100))])
		self.huecos.SetMinSize(self.FromDIP(wx.Size(470, 240)))
		self.huecos.SetHelpText(_("Cada tecla F con o sin Mayús, Ctrl o Alt. Cambiar le da otra orden (y la tecla pasa a esa orden)."))
		caja.Add(etiqueta, 0, wx.ALL, self.FromDIP(4))
		caja.Add(self.huecos, 1, wx.EXPAND | wx.ALL, self.FromDIP(4))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		for texto, ayuda, accion in (
			(_("Ca&mbiar..."), _("Elige la orden del hueco y su etiqueta corta."), self.cambiar_hueco),
			(_("Dejar &vacío"), _("El hueco queda sin orden en la barra (la tecla no cambia)."), self.vaciar_hueco),
			(_("&Quitar el cambio"), _("Vuelve a la orden de fábrica de este hueco."), self.quitar_hueco),
			(_("&Restablecer esta pestaña"), _("Todos los huecos como vienen de fábrica."), self.restablecer_huecos),
		):
			boton = wx.Button(pagina_teclas, label=texto)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, a=accion: a())
			fila.Add(boton, 0, wx.ALL, self.FromDIP(3))
		caja.Add(fila, 0)
		pagina_teclas.SetSizer(caja)
		self.libro.AddPage(pagina_teclas, _("Barra de teclas"))
		self.sizer.Add(self.libro, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		self.terminar(wx.OK | wx.CANCEL, foco=self.casillas)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		self._rellenar_huecos(0)

	# Barra de teclas ------------------------------------------------------------

	def _lista_huecos(self) -> list[tuple[str, str, str, str]]:
		"""(hueco, nombre visible, orden, etiqueta) de los 40 huecos con los cambios."""
		personalizador = mp.Personalizador(lambda: self.datos, lambda: "avanzado", lambda: False, lambda: True, ordenes.POR_ID.get)
		resultado = []
		for modificador in mp.MODIFICADORES:
			for indice, (tecla, orden, texto) in enumerate(personalizador.barra_teclas(modificador, ordenes.BARRA_TECLAS[modificador])):
				hueco = mp.hueco(modificador, indice + 1)
				resultado.append((hueco, NOMBRES_MODIFICADOR[modificador] + tecla, orden, _(texto)))
		return resultado

	def _rellenar_huecos(self, foco: int) -> None:
		filas = [[visible, _etiqueta(orden) if orden else _("(vacío)"), texto] for _h, visible, orden, texto in self._lista_huecos()]
		self.huecos.reemplazar_filas(filas, conservar_foco=False)
		self.huecos.enfocar_fila(min(max(foco, 0), len(filas) - 1), anunciar=False)

	def _hueco_elegido(self) -> tuple[int, str] | None:
		fila = self.huecos.fila_actual()
		lista = self._lista_huecos()
		return (fila, lista[fila][0]) if 0 <= fila < len(lista) else None

	def poner_hueco(self, hueco: str, id_orden: str, etiqueta: str = "") -> bool:
		"""Da el hueco (y su tecla) a una orden; pregunta si la tecla era de otra orden."""
		from app.ui.dialogos import f_mapa_teclas

		tecla = servicio_teclas.normalizar(hueco)
		resultado = f_mapa_teclas.comprobar(self.asignadas, ordenes.ambitos(), ordenes.fijas(), id_orden, tecla)
		if not resultado.permitida:
			f_comun.avisar(self, resultado.motivo, self.titulo)
			return False
		if resultado.choques:
			nombres = ", ".join(_etiqueta(o) for o in resultado.choques)
			if not f_comun.preguntar(self, _("{t} ya es {o}: ¿quitársela?").format(t=nombre_visible(tecla), o=nombres), self.titulo):
				return False
			for otra in resultado.choques:
				self.asignadas[otra] = tuple(t for t in self.asignadas.get(otra, ()) if t != tecla)
		if tecla not in self.asignadas.get(id_orden, ()):
			self.asignadas[id_orden] = (*self.asignadas.get(id_orden, ()), tecla)
		self.cambios_teclas = True
		self.datos.barra_teclas[hueco] = (id_orden, etiqueta)
		return True

	def cambiar_hueco(self) -> None:
		elegido = self._hueco_elegido()
		if elegido is None:
			return
		fila, hueco = elegido
		id_orden = pe_comun.elegir_orden(self, _("Orden para {t}").format(t=nombre_visible(hueco)))
		if not id_orden:
			return
		propuesta = mp.etiqueta_corta(_etiqueta(id_orden))
		etiqueta = f_comun.pedir(self, _("&Etiqueta corta del botón (vacío: se calcula de la orden):"), _("Etiqueta"), propuesta)
		if etiqueta is None:
			return
		if self.poner_hueco(hueco, id_orden, etiqueta.strip()[:10]):
			self._rellenar_huecos(fila)
			anuncios.anunciar(_("{t}: {o}").format(t=nombre_visible(hueco), o=_etiqueta(id_orden)), anuncios.RESULTADO)
		self.huecos.SetFocus()

	def vaciar_hueco(self) -> None:
		elegido = self._hueco_elegido()
		if elegido is not None:
			self.datos.barra_teclas[elegido[1]] = ("", "")
			self._rellenar_huecos(elegido[0])

	def quitar_hueco(self) -> None:
		elegido = self._hueco_elegido()
		if elegido is not None:
			self.datos.barra_teclas.pop(elegido[1], None)
			self._rellenar_huecos(elegido[0])

	def restablecer_huecos(self) -> None:
		self.datos.barra_teclas.clear()
		self._rellenar_huecos(0)
		anuncios.anunciar(_("Barra de teclas de fábrica"), anuncios.RESULTADO)

	# Aceptar ----------------------------------------------------------------

	def ocultas(self) -> list[str]:
		return [id_orden for indice, (id_orden, _t) in enumerate(self.fabrica) if not self.casillas.IsChecked(indice)]

	def personalizadas(self) -> dict[str, list[str]]:
		from app.ui.dialogos import f_mapa_teclas

		fabrica = {o: tuple(servicio_teclas.normalizar(t) for t in ts) for o, ts in ordenes.teclas_por_defecto(self._esquema).items()}
		return f_mapa_teclas.personalizadas(self.asignadas, fabrica)

	def aceptar(self) -> bool:
		self.datos.ocultas = self.ocultas()
		self.datos.mis_ordenes = list(self.mis.elementos)
		self.datos.barra_botones = [] if self.botones.elementos == list(mp.BOTONES_FABRICA) else list(self.botones.elementos)
		self.cerrar(wx.ID_OK)
		return True


def mostrar(padre: wx.Window | None, pe) -> None:
	mapa = getattr(pe.ventana, "mapa_teclas", None)
	dialogo = DialogoMenus(padre, pe.menus, mapa, pe.config.obtener("teclado.esquema"))
	resultado = f_comun.mostrar(dialogo, lambda d: (d.datos, d.personalizadas() if d.cambios_teclas else None))
	if resultado is None:
		return
	datos, personalizadas = resultado
	if not pe_comun.guardar_con_aviso(padre, lambda: pe.guardar_menus(datos), _("Personalizar menús y barras")):
		return
	if personalizadas is not None and personalizadas != (pe.config.obtener("teclado.personalizadas") or {}):
		pe.config.establecer("teclado.personalizadas", personalizadas)
	anuncios.anunciar(_("Menús y barras guardados"), anuncios.RESULTADO)
