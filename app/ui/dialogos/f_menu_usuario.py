# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Menú de usuario: elegir una entrada (F2) y editar las entradas (Opciones).

Elegir (``DialogoMenuUsuario``):

- Lista nativa con «A: Comprimir con 7-Zip». Intro o la tecla rápida de la
  entrada (sin modificadores) la ejecuta, como en Norton Commander. Las
  letras se atienden antes que la búsqueda nativa del ``ListBox``: si
  ninguna entrada tiene esa tecla, la letra sigue su camino.
- Los submenús se abren dentro de la misma lista; Retroceso vuelve al nivel
  superior y se anuncia en qué nivel se está, porque el lector solo leería
  la fila nueva.

Editar (``DialogoEditarMenu`` y ``DialogoEntradaMenu``): lista del nivel
actual con Nueva, Editar, Eliminar, Subir, Bajar y entrar o salir de los
submenús. Los cambios se guardan solo con Aceptar.
"""

from __future__ import annotations

import builtins
import copy
import logging

import wx

from app.services import menu_usuario
from app.services.menu_usuario import EntradaMenu
from app.ui import anuncios
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


AYUDA_VARIABLES = (
	"Una orden por línea; se ejecutan una tras otra con cmd. Variables: %N nombre, %B nombre sin extensión, "
	"%E extensión, %P ruta completa, %D carpeta del panel activo, %O carpeta del otro panel, %T ruta del cursor "
	"del otro panel, %M rutas de los elementos de trabajo (sola), %L archivo con esas rutas, "
	"%?Título?valor% pide un dato, %% un signo de porcentaje."
)


# ── Elegir una entrada (F2) ─────────────────────────────────────────────────

class DialogoMenuUsuario(f_comun.DialogoF):
	"""Lista de entradas; ``elegida`` queda con la entrada que se ejecuta."""

	def __init__(self, padre: wx.Window | None, entradas: list[EntradaMenu], aviso_local: str = "") -> None:
		super().__init__(padre, _("Menú de usuario"))
		self._pila: list[tuple[str, list[EntradaMenu]]] = [(_("Menú de usuario"), list(entradas))]
		self.elegida: EntradaMenu | None = None
		if aviso_local:
			# Información breve que el lector lee al abrir (no recibe el foco).
			self.texto_aviso = wx.StaticText(self.panel, label=aviso_local)
			self.sizer.Add(self.texto_aviso, 0, wx.ALL, self.FromDIP(6))
		_etiqueta, self.lista = crear_campo(
			self.panel, _("&Entradas:"), wx.ListBox, size=self.FromDIP(wx.Size(420, 260)), style=wx.LB_SINGLE,
			ayuda=_("Intro o la tecla rápida de la entrada la ejecuta. En un submenú, Retroceso vuelve al nivel superior."),
			sizer=self.sizer,
		)
		self.sizer.GetItem(self.lista).SetProportion(1)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_ejecutar = self.boton(_("E&jecutar"), _("Ejecuta la entrada elegida o abre su submenú."), self.activar, fila)
		self.boton_subir = self.boton(_("&Volver al nivel superior"), _("Sale del submenú (también con Retroceso)."), self.volver, fila)
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.activar())
		self.lista.Bind(wx.EVT_CHAR_HOOK, self._al_tecla_lista)
		self.terminar(wx.CANCEL, foco=self.lista)
		self.boton_ejecutar.SetDefault()
		self._rellenar()

	@property
	def entradas(self) -> list[EntradaMenu]:
		return self._pila[-1][1]

	def _rellenar(self, seleccion: int = 0) -> None:
		self.lista.Set([e.texto() for e in self.entradas] or [_("(El menú está vacío)")])
		self.lista.SetSelection(min(max(seleccion, 0), self.lista.GetCount() - 1))
		self.boton_subir.Enable(len(self._pila) > 1)

	def entrada_actual(self) -> EntradaMenu | None:
		indice = self.lista.GetSelection()
		return self.entradas[indice] if 0 <= indice < len(self.entradas) else None

	def activar(self, entrada: EntradaMenu | None = None) -> None:
		"""Entra en el submenú o cierra el diálogo con la entrada elegida."""
		entrada = entrada or self.entrada_actual()
		if entrada is None:
			return
		if entrada.es_submenu:
			self._pila.append((entrada.etiqueta, entrada.submenu))
			self._rellenar()
			self.lista.SetFocus()
			anuncios.anunciar(_("Submenú {n}").format(n=entrada.etiqueta), anuncios.RESULTADO)
			return
		self.elegida = entrada
		self.cerrar(wx.ID_OK)

	def volver(self) -> bool:
		if len(self._pila) <= 1:
			return False
		titulo, _entradas = self._pila.pop()
		padre = self.entradas
		indice = next((i for i, e in enumerate(padre) if e.etiqueta == titulo and e.es_submenu), 0)
		self._rellenar(indice)
		self.lista.SetFocus()
		anuncios.anunciar(_("Nivel superior: {n}").format(n=self._pila[-1][0]), anuncios.RESULTADO)
		return True

	def pulsar_tecla(self, tecla: str) -> bool:
		"""La tecla rápida de una entrada del nivel actual; ``True`` si había una."""
		entrada = menu_usuario.buscar_tecla(self.entradas, tecla)
		if entrada is None:
			return False
		self.lista.SetSelection(self.entradas.index(entrada))
		self.activar(entrada)
		return True

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		if evento.GetModifiers() == wx.MOD_NONE:
			if codigo == wx.WXK_BACK and self.volver():
				return
			if 32 < codigo < 128 and chr(codigo).isalnum() and self.pulsar_tecla(chr(codigo)):
				return
		evento.Skip()


# ── Editar una entrada ──────────────────────────────────────────────────────

class DialogoEntradaMenu(f_comun.DialogoF):
	"""Etiqueta, tecla, órdenes y opciones de una entrada."""

	def __init__(self, padre: wx.Window | None, entrada: EntradaMenu, nueva: bool, teclas_usadas: set[str]) -> None:
		super().__init__(padre, _("Nueva entrada") if nueva else _("Editar la entrada"))
		self.entrada = copy.deepcopy(entrada)
		self._teclas_usadas = teclas_usadas
		_e, self.campo_etiqueta = crear_campo(self.panel, _("&Etiqueta:"), wx.TextCtrl, value=entrada.etiqueta,
			size=self.FromDIP(wx.Size(420, -1)), ayuda=_("Texto de la entrada en el menú de usuario."), sizer=self.sizer)
		_t, self.campo_tecla = crear_campo(self.panel, _("&Tecla rápida:"), wx.TextCtrl, value=entrada.tecla,
			size=self.FromDIP(wx.Size(60, -1)), ayuda=_("Una letra o un dígito que ejecuta la entrada en F2. Puede quedar vacía."),
			sizer=self.sizer, expandir=False)
		self.campo_tecla.SetMaxLength(1)
		_o, self.campo_ordenes = crear_campo(self.panel, _("Ó&rdenes, una por línea:"), wx.TextCtrl,
			value="\n".join(entrada.ordenes), style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(420, 120)),
			ayuda=_(AYUDA_VARIABLES), sizer=self.sizer)
		if entrada.es_submenu:
			self.campo_ordenes.Enable(False)
			self.campo_ordenes.SetHelpText(_("Es un submenú: sus órdenes no se usan. Edite sus entradas con «Abrir el submenú»."))
		self.casilla_consola = wx.CheckBox(self.panel, label=_("Ejecutar en una c&onsola que queda abierta"))
		self.casilla_consola.SetValue(entrada.consola)
		self.casilla_consola.SetHelpText(_("Para programas que piden datos por teclado. Si no, la salida va a la zona de salida de las órdenes."))
		self.sizer.Add(self.casilla_consola, 0, wx.ALL, self.FromDIP(5))
		self.casilla_refrescar = wx.CheckBox(self.panel, label=_("Re&frescar los paneles al terminar"))
		self.casilla_refrescar.SetValue(entrada.refrescar)
		self.casilla_refrescar.SetHelpText(_("Vuelve a leer las carpetas de los paneles cuando la orden termina."))
		self.sizer.Add(self.casilla_refrescar, 0, wx.ALL, self.FromDIP(5))
		self.terminar(wx.OK | wx.CANCEL, foco=self.campo_etiqueta)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())

	def aceptar(self) -> bool:
		etiqueta = self.campo_etiqueta.GetValue().strip()
		if not etiqueta:
			f_comun.avisar(self, _("Escriba la etiqueta de la entrada."), self.titulo)
			self.campo_etiqueta.SetFocus()
			return False
		tecla_escrita = self.campo_tecla.GetValue().strip()
		tecla = menu_usuario.normalizar_tecla(tecla_escrita)
		if tecla_escrita and not tecla:
			f_comun.avisar(self, _("La tecla rápida debe ser una letra o un dígito."), self.titulo)
			self.campo_tecla.SetFocus()
			return False
		if tecla and tecla in self._teclas_usadas:
			f_comun.avisar(self, _("La tecla {t} ya la usa otra entrada de este nivel.").format(t=tecla), self.titulo)
			self.campo_tecla.SetFocus()
			return False
		self.entrada.etiqueta = etiqueta
		self.entrada.tecla = tecla
		if not self.entrada.es_submenu:
			self.entrada.ordenes = [o.strip() for o in self.campo_ordenes.GetValue().splitlines() if o.strip()]
		self.entrada.consola = self.casilla_consola.GetValue()
		self.entrada.refrescar = self.casilla_refrescar.GetValue()
		self.cerrar(wx.ID_OK)
		return True


def editar_entrada(padre: wx.Window | None, entrada: EntradaMenu, nueva: bool, teclas_usadas: set[str]) -> EntradaMenu | None:
	return f_comun.mostrar(DialogoEntradaMenu(padre, entrada, nueva, teclas_usadas), lambda d: d.entrada)


# ── Editar el menú ──────────────────────────────────────────────────────────

class DialogoEditarMenu(f_comun.DialogoF):
	"""Entradas del menú de usuario, nivel a nivel. ``entradas`` es el menú completo editado."""

	def __init__(self, padre: wx.Window | None, entradas: list[EntradaMenu]) -> None:
		super().__init__(padre, _("Editar el menú de usuario"))
		self.entradas = copy.deepcopy(entradas)
		self._pila: list[tuple[str, list[EntradaMenu]]] = [(_("Menú de usuario"), self.entradas)]
		self.etiqueta_nivel = wx.StaticText(self.panel, label="")
		self.sizer.Add(self.etiqueta_nivel, 0, wx.ALL, self.FromDIP(5))
		_l, self.lista = crear_campo(self.panel, _("&Entradas de este nivel:"), wx.ListBox, size=self.FromDIP(wx.Size(420, 220)),
			ayuda=_("Entradas del nivel actual del menú de usuario."), sizer=self.sizer)
		self.sizer.GetItem(self.lista).SetProportion(1)
		fila1 = wx.BoxSizer(wx.HORIZONTAL)
		self.boton(_("&Nueva..."), _("Añade una entrada después de la elegida."), self.nueva, fila1)
		self.boton_editar = self.boton(_("E&ditar..."), _("Cambia la entrada elegida."), self.editar, fila1)
		self.boton(_("E&liminar"), _("Quita la entrada elegida (y su submenú); pide confirmación."), self.eliminar, fila1)
		self.boton(_("S&ubir"), _("Sube la entrada una posición."), lambda: self.mover(-1), fila1)
		self.boton(_("&Bajar"), _("Baja la entrada una posición."), lambda: self.mover(1), fila1)
		self.sizer.Add(fila1, 0, wx.ALIGN_LEFT)
		fila2 = wx.BoxSizer(wx.HORIZONTAL)
		self.boton(_("Abrir el sub&menú"), _("Muestra las entradas del submenú de la entrada elegida (lo crea si no lo es)."),
			self.abrir_submenu, fila2)
		self.boton_volver = self.boton(_("&Volver al nivel superior"), _("Sale del submenú."), self.volver, fila2)
		self.sizer.Add(fila2, 0, wx.ALIGN_LEFT)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.editar())
		self.terminar(wx.OK | wx.CANCEL, foco=self.lista)
		self._rellenar()

	@property
	def nivel(self) -> list[EntradaMenu]:
		return self._pila[-1][1]

	def _rellenar(self, seleccion: int | None = None) -> None:
		actual = self.lista.GetSelection() if seleccion is None else seleccion
		self.lista.Set([e.texto() for e in self.nivel])
		if self.nivel:
			self.lista.SetSelection(min(max(actual, 0), len(self.nivel) - 1))
		ruta = " > ".join(t for t, _e in self._pila)
		self.etiqueta_nivel.SetLabel(_("Nivel: {r}").format(r=ruta))
		self.boton_volver.Enable(len(self._pila) > 1)

	def indice(self) -> int:
		return self.lista.GetSelection()

	def _teclas(self, excepto: int = -1) -> set[str]:
		return {e.tecla for i, e in enumerate(self.nivel) if e.tecla and i != excepto}

	def nueva(self) -> None:
		entrada = editar_entrada(self, EntradaMenu(""), True, self._teclas())
		if entrada is not None:
			self.insertar(entrada)

	def insertar(self, entrada: EntradaMenu) -> None:
		posicion = self.indice() + 1 if self.indice() >= 0 else len(self.nivel)
		self.nivel.insert(posicion, entrada)
		self._rellenar(posicion)
		self.lista.SetFocus()

	def editar(self) -> None:
		i = self.indice()
		if i < 0:
			return
		entrada = editar_entrada(self, self.nivel[i], False, self._teclas(excepto=i))
		if entrada is not None:
			self.nivel[i] = entrada
			self._rellenar(i)
		self.lista.SetFocus()

	def eliminar(self) -> None:
		i = self.indice()
		if i < 0:
			return
		entrada = self.nivel[i]
		texto = _("¿Quitar la entrada «{e}»?").format(e=entrada.etiqueta)
		if entrada.es_submenu:
			texto = _("¿Quitar el submenú «{e}» con sus {n} entradas?").format(e=entrada.etiqueta, n=len(entrada.submenu))
		if not f_comun.preguntar(self, texto, _("Eliminar"), peligroso=True):
			return
		del self.nivel[i]
		self._rellenar(i)
		self.lista.SetFocus()

	def mover(self, paso: int) -> None:
		i = self.indice()
		destino = i + paso
		if i < 0 or not 0 <= destino < len(self.nivel):
			return
		self.nivel[i], self.nivel[destino] = self.nivel[destino], self.nivel[i]
		self._rellenar(destino)
		self.lista.SetFocus()
		anuncios.anunciar(_("Posición {n} de {t}").format(n=destino + 1, t=len(self.nivel)), anuncios.RESULTADO)

	def abrir_submenu(self) -> None:
		i = self.indice()
		if i < 0:
			return
		entrada = self.nivel[i]
		self._pila.append((entrada.etiqueta, entrada.submenu))
		self._rellenar(0)
		self.lista.SetFocus()
		anuncios.anunciar(_("Submenú {n}, {c} entradas").format(n=entrada.etiqueta, c=len(entrada.submenu)), anuncios.RESULTADO)

	def volver(self) -> None:
		if len(self._pila) <= 1:
			return
		titulo, _hijas = self._pila.pop()
		indice = next((i for i, e in enumerate(self.nivel) if e.etiqueta == titulo), 0)
		self._rellenar(indice)
		self.lista.SetFocus()
		anuncios.anunciar(_("Nivel superior"), anuncios.RESULTADO)


def editar_menu(padre: wx.Window | None, entradas: list[EntradaMenu]) -> list[EntradaMenu] | None:
	"""Menú editado, o ``None`` si se cancela."""
	return f_comun.mostrar(DialogoEditarMenu(padre, entradas), lambda d: d.entradas)


def elegir_entrada(padre: wx.Window | None, entradas: list[EntradaMenu], aviso_local: str = "") -> EntradaMenu | None:
	return f_comun.mostrar(DialogoMenuUsuario(padre, entradas, aviso_local), lambda d: d.elegida)
