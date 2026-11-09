# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Columnas y vista de esta carpeta (diseño 2.0, 10.4; orden ``columnas_carpeta``, por lado).

Conjuntos de columnas con nombre (columnas, anchos, orden, vista, filtro y
orden de lectura) y las reglas que los aplican: «Aplicar a esta carpeta y sus
subcarpetas» (regla de ruta) o «Aplicar a carpetas con mayoría de...» (regla de
contenido). Cada cambio se guarda al momento en ``vistas_carpeta.json`` y se
aplica a la carpeta del panel.
"""

from __future__ import annotations

import builtins
import dataclasses
import logging

import wx

from app.services import ordenacion, vistas_carpeta
from app.services.vistas_modelo import ConjuntoVista
from app.ui import anuncios
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun, pe_comun

log = logging.getLogger(__name__)

VISTAS = ("completa", "breve")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def nombre_criterio(criterio: str) -> str:
	return {
		"nombre": _("Nombre"), "extension": _("Extensión"), "fecha": _("Fecha"), "tamano": _("Tamaño"), "tipo": _("Tipo"),
		"sin_orden": _("Sin ordenar"),
	}.get(criterio, criterio)


def nombre_vista(vista: str) -> str:
	return {"completa": _("Completa"), "breve": _("Breve")}.get(vista, vista)


class DialogoConjunto(f_comun.DialogoF):
	"""Editar un conjunto. ``conjunto`` queda con el resultado al aceptar."""

	def __init__(self, padre: wx.Window | None, conjunto: ConjuntoVista, otros: list[str], fabrica: list[str]) -> None:
		super().__init__(padre, _("Conjunto de columnas"))
		self.conjunto = conjunto
		self._otros = {o.casefold() for o in otros}
		self._fabrica = fabrica
		self._columnas = list(conjunto.columnas) or list(fabrica)
		self._anchos = dict(conjunto.anchos)
		self._lectura = list(conjunto.lectura)
		_n, self.campo_nombre = crear_campo(self.panel, _("&Nombre:"), wx.TextCtrl, value=conjunto.nombre,
			size=self.FromDIP(wx.Size(320, -1)), sizer=self.sizer, ayuda=_("Nombre del conjunto, por ejemplo «Música»."))
		_o, self.orden = crear_campo(self.panel, _("&Ordenar por:"), wx.Choice,
			choices=[nombre_criterio(c) for c in ordenacion.CRITERIOS], sizer=self.sizer, ayuda=_("Orden de la lista en estas carpetas."))
		self.orden.SetSelection(ordenacion.CRITERIOS.index(conjunto.orden) if conjunto.orden in ordenacion.CRITERIOS else 0)
		self.inverso = wx.CheckBox(self.panel, label=_("Orden &inverso"))
		self.inverso.SetValue(conjunto.inverso)
		self.inverso.SetHelpText(_("De mayor a menor, o de la Z a la A."))
		self.sizer.Add(self.inverso, 0, wx.ALL, self.FromDIP(5))
		_v, self.vista = crear_campo(self.panel, _("&Vista:"), wx.Choice, choices=[nombre_vista(v) for v in VISTAS], sizer=self.sizer,
			ayuda=_("Completa (todas las columnas) o Breve (solo el nombre)."))
		self.vista.SetSelection(VISTAS.index(conjunto.vista) if conjunto.vista in VISTAS else 0)
		_f, self.filtro = crear_campo(self.panel, _("&Filtro:"), wx.TextCtrl, value=conjunto.filtro, sizer=self.sizer,
			ayuda=_("Patrón de los elementos que se ven (por ejemplo *.mp3;*.flac). Vacío: todos."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton(_("Co&lumnas y orden de lectura..."), _("Qué columnas se ven, en qué orden y cuáles se leen al moverse."),
			self.elegir_columnas, fila)
		self.sizer.Add(fila, 0)
		self.terminar(wx.OK | wx.CANCEL, foco=self.campo_nombre)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())

	def elegir_columnas(self) -> None:
		from app.ui.dialogos import f_columnas

		dialogo = f_columnas.DialogoColumnas(self, _("Columnas del conjunto"), self._columnas, self._anchos, self._fabrica,
			lectura=self._lectura)
		resultado = f_comun.mostrar(dialogo, lambda d: (d.columnas, dict(d.anchos), d.lectura))
		if resultado is not None:
			self._columnas, self._anchos, lectura = resultado
			self._lectura = vistas_carpeta.lectura_valida([c for c in (lectura or []) if c in self._columnas])

	def aceptar(self) -> bool:
		nombre = " ".join(self.campo_nombre.GetValue().split())
		if not nombre:
			f_comun.avisar(self, _("El conjunto necesita un nombre"), self.titulo)
			self.campo_nombre.SetFocus()
			return False
		if nombre.casefold() in self._otros:
			f_comun.avisar(self, _("Ya hay un conjunto «{n}»").format(n=nombre), self.titulo)
			self.campo_nombre.SetFocus()
			return False
		self.conjunto = ConjuntoVista(nombre, tuple(self._columnas), dict(self._anchos), ordenacion.CRITERIOS[self.orden.GetSelection()],
			self.inverso.GetValue(), VISTAS[self.vista.GetSelection()], self.filtro.GetValue().strip(), tuple(self._lectura))
		self.cerrar(wx.ID_OK)
		return True


class DialogoVistas(pe_comun.DialogoListaPE):
	"""Conjuntos de columnas y las reglas de la carpeta del panel."""

	def __init__(self, padre: wx.Window | None, pe, panel) -> None:
		super().__init__(padre, _("Columnas y vista de esta carpeta"), _("Con&juntos:"),
			[(_("Nombre"), 160), (_("Columnas"), 260), (_("Reglas"), 260)],
			_("Conjuntos de columnas con nombre. Izquierda y Derecha leen nombre, columnas y reglas."))
		self.pe = pe
		self.panel_archivos = panel
		self.ruta = panel.mostrar_ruta()
		_a, self.estado = crear_campo(self.panel, _("Conjunto &aplicado ahora:"), wx.TextCtrl, style=wx.TE_READONLY,
			sizer=self.sizer, ayuda=_("El conjunto que se aplica a esta carpeta, si alguno."))
		self.boton(_("&Nuevo..."), _("Crea un conjunto con las columnas de esta pestaña."), self.nuevo, self.botonera)
		self.boton(_("Edi&tar..."), _("Cambia el conjunto elegido: nombre, orden, vista, filtro, columnas y orden de lectura."),
			self.editar, self.botonera)
		self.boton(_("E&liminar"), _("Borra el conjunto elegido y sus reglas; pide confirmación."), self.eliminar, self.botonera)
		self.boton(_("Aplicar a esta carpeta y sus &subcarpetas"), _("Añade una regla de ruta para esta carpeta con el conjunto elegido."),
			self.aplicar_ruta, self.botonera)
		self.boton(_("Aplicar a carpetas con &mayoría de..."), _("Añade una regla de contenido: extensiones y proporción mínima."),
			self.aplicar_contenido, self.botonera)
		self.boton(_("&Quitar las reglas de esta carpeta"), _("Quita las reglas de ruta que se aplican a esta carpeta."),
			self.quitar_reglas, self.botonera)
		self.cerrar_lista()
		self.rellenar(0)
		self._actualizar_estado()

	@property
	def datos(self) -> vistas_carpeta.DatosVistas:
		return self.pe.vistas

	def filas(self) -> list[list[str]]:
		from app.ui.dialogos.f_columnas import titulo_columna

		filas = []
		for conjunto in self.datos.conjuntos:
			reglas = [r.patron if r.tipo == vistas_carpeta.TIPO_RUTA else _("{p} % de {e}").format(
				p=int(r.proporcion * 100), e=", ".join(r.extensiones)) for r in self.datos.reglas if r.conjunto == conjunto.nombre]
			filas.append([conjunto.nombre, ", ".join(titulo_columna(c) for c in conjunto.columnas), "; ".join(reglas) or _("(sin reglas)")])
		return filas

	def elegido(self) -> ConjuntoVista | None:
		i = self.indice()
		return self.datos.conjuntos[i] if 0 <= i < len(self.datos.conjuntos) else None

	def _actualizar_estado(self) -> None:
		conjunto = getattr(self.panel_archivos, "conjunto", None)
		self.estado.ChangeValue(conjunto.nombre if conjunto is not None else _("Ninguno: las columnas de la pestaña"))

	def _guardar(self, foco: int) -> bool:
		ok = pe_comun.guardar_con_aviso(self, lambda: self.pe.guardar_vistas(self.datos), self.titulo)
		self.rellenar(foco)
		self.lista.SetFocus()
		self.pe.al_cambiar_carpeta(panel=self.panel_archivos, ruta=self.panel_archivos.ruta)
		self._actualizar_estado()
		return ok

	def _fabrica(self) -> list[str]:
		return list(self.pe.config.obtener("paneles.columnas") or ["nombre"])

	def nuevo(self) -> None:
		base = ConjuntoVista(_("Conjunto"), tuple(self.panel_archivos.columnas), orden=self.panel_archivos.criterio_orden, inverso=self.panel_archivos.orden_inverso,
			lectura=tuple(getattr(self.panel_archivos, "lectura", []) or []))
		dialogo = DialogoConjunto(self, base, [c.nombre for c in self.datos.conjuntos], self._fabrica())
		conjunto = f_comun.mostrar(dialogo, lambda d: d.conjunto)
		if conjunto is None:
			return
		self.datos.conjuntos.append(conjunto)
		if self._guardar(len(self.datos.conjuntos) - 1):
			anuncios.anunciar(_("Conjunto creado: {n}").format(n=conjunto.nombre), anuncios.RESULTADO)

	def editar(self) -> None:
		actual = self.elegido()
		if actual is None:
			return
		i = self.datos.conjuntos.index(actual)
		otros = [c.nombre for c in self.datos.conjuntos if c is not actual]
		conjunto = f_comun.mostrar(DialogoConjunto(self, actual, otros, self._fabrica()), lambda d: d.conjunto)
		if conjunto is None:
			return
		self.datos.conjuntos[i] = conjunto
		if conjunto.nombre != actual.nombre:
			self.datos.reglas = [dataclasses.replace(r, conjunto=conjunto.nombre) if r.conjunto == actual.nombre else r
				for r in self.datos.reglas]
		if self._guardar(i):
			anuncios.anunciar(_("Conjunto guardado: {n}").format(n=conjunto.nombre), anuncios.RESULTADO)

	def eliminar(self) -> None:
		actual = self.elegido()
		if actual is None:
			return
		if not f_comun.preguntar(self, _("¿Eliminar el conjunto «{n}» y sus reglas?").format(n=actual.nombre), self.titulo, peligroso=True):
			return
		i = self.datos.conjuntos.index(actual)
		self.datos.conjuntos.remove(actual)
		self.datos.reglas = [r for r in self.datos.reglas if r.conjunto != actual.nombre]
		if self._guardar(i):
			anuncios.anunciar(_("Conjunto eliminado: {n}").format(n=actual.nombre), anuncios.RESULTADO)

	def aplicar_ruta(self) -> bool:
		actual = self.elegido()
		if actual is None:
			f_comun.avisar(self, _("Cree antes un conjunto con Nuevo"), self.titulo)
			return False
		patron = self.ruta.rstrip("\\") + "\\**"
		self.datos.reglas = [r for r in self.datos.reglas if not (r.tipo == vistas_carpeta.TIPO_RUTA and r.patron.casefold() == patron.casefold())]
		# Las de ruta van primero: así ganan a las de contenido y a las más generales añadidas antes.
		self.datos.reglas.insert(0, vistas_carpeta.ReglaVista(vistas_carpeta.TIPO_RUTA, actual.nombre, patron=patron))
		ok = self._guardar(self.datos.conjuntos.index(actual))
		if ok:
			anuncios.anunciar(_("{n} se aplica a esta carpeta y sus subcarpetas").format(n=actual.nombre), anuncios.RESULTADO)
		return ok

	def aplicar_contenido(self) -> bool:
		actual = self.elegido()
		if actual is None:
			f_comun.avisar(self, _("Cree antes un conjunto con Nuevo"), self.titulo)
			return False
		texto = f_comun.pedir(self, _("&Extensiones separadas por comas (por ejemplo mp3, flac, m4a):"), _("Carpetas con mayoría de..."))
		if not texto:
			return False
		extensiones = [e.strip().lstrip(".").lower() for e in texto.replace(";", ",").split(",") if e.strip()]
		porcentaje = f_comun.pedir(self, _("&Porcentaje mínimo de archivos con esas extensiones:"), _("Carpetas con mayoría de..."), "60")
		try:
			proporcion = min(100, max(5, int(str(porcentaje or "60").strip().rstrip("%")))) / 100
		except ValueError:
			f_comun.avisar(self, _("Escriba el porcentaje con cifras, de 5 a 100"), self.titulo)
			return False
		self.datos.reglas.append(vistas_carpeta.ReglaVista(vistas_carpeta.TIPO_CONTENIDO, actual.nombre,
			extensiones=tuple(extensiones), proporcion=proporcion))
		ok = self._guardar(self.datos.conjuntos.index(actual))
		if ok:
			anuncios.anunciar(_("{n} se aplica a las carpetas con un {p} % de {e}").format(n=actual.nombre, p=int(proporcion * 100),
				e=", ".join(extensiones)), anuncios.RESULTADO)
		return ok

	def quitar_reglas(self) -> None:
		antes = len(self.datos.reglas)
		self.datos.reglas = [r for r in self.datos.reglas
			if not (r.tipo == vistas_carpeta.TIPO_RUTA and vistas_carpeta.coincide_ruta(r.patron, self.ruta))]
		quitadas = antes - len(self.datos.reglas)
		if not quitadas:
			anuncios.anunciar(_("Esta carpeta no tiene reglas de ruta"), anuncios.RESULTADO)
			return
		if self._guardar(max(0, self.indice())):
			anuncios.anunciar(_("Reglas quitadas: {n}").format(n=quitadas), anuncios.RESULTADO)


def mostrar(padre: wx.Window | None, pe, panel) -> None:
	f_comun.mostrar(DialogoVistas(padre, pe, panel), aceptar=(wx.ID_CLOSE, wx.ID_OK, wx.ID_CANCEL))
