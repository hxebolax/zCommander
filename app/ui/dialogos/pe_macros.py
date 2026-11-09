# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Macros (diseño 2.0, 10.1): lista, editor, grabación, exportar e importar ``.zcmacro``.

- La lista (orden ``macros``) dice Nombre, Tecla y Pasos. Cada cambio se guarda
  al momento (``ServicioPE.guardar_macros``): el catálogo, los menús y la paleta
  ven la macro nueva sin reiniciar.
- Importar (también Intro sobre un ``.zcmacro``) muestra antes una vista previa:
  «Órdenes que se podrán ejecutar», cada paso con su texto completo, con los
  que ejecutan programas u órdenes SIN marcar; se importan solo los marcados.
"""

from __future__ import annotations

import builtins
import copy
import json
import logging
from pathlib import Path

import wx

from app.services import macros
from app.services.macros import Macro, Paso
from app.services.macros_argumentos import argumento_de
from app.services.teclas import nombre_visible
from app.ui import anuncios, ordenes
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun, pe_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _etiqueta(id_orden: str) -> str:
	from app.ui.acciones.personalizar_pe import etiqueta

	return etiqueta(id_orden)


def _permisos(id_complemento: str) -> tuple[str, ...]:
	from app.plugins import registro

	registrado = registro.complemento(id_complemento)
	return tuple(registrado.manifiesto.permisos) if registrado is not None else ()


def texto_paso(paso: Paso) -> str:
	return macros.texto_paso(paso, _etiqueta)


# ── Editor de una macro ─────────────────────────────────────────────────────


class DialogoMacro(f_comun.DialogoF):
	"""Editar una macro. ``macro`` queda con el resultado al aceptar.

	:param otras: nombres de las demás macros (para no repetir).
	:param mapa: el ``MapaTeclas`` vigente (para avisar de choques al elegir la tecla).
	:param probar: ``probar(macro)`` ejecuta la macro tal como está en el editor.
	"""

	def __init__(self, padre: wx.Window | None, macro: Macro, otras: list[str], mapa=None, probar=None) -> None:
		super().__init__(padre, _("Macro"))
		self.macro = copy.deepcopy(macro)
		self._otras = {o.casefold() for o in otras}
		self._mapa = mapa
		self._probar = probar
		_n, self.campo_nombre = crear_campo(self.panel, _("&Nombre:"), wx.TextCtrl, value=self.macro.nombre,
			size=self.FromDIP(wx.Size(360, -1)), sizer=self.sizer, ayuda=_("Nombre de la macro: es su orden en la paleta y en Mis órdenes."))
		self.casilla_menu = wx.CheckBox(self.panel, label=_("En el &menú Mis órdenes"))
		self.casilla_menu.SetValue(self.macro.menu)
		self.casilla_menu.SetHelpText(_("La macro aparece en el menú Mis órdenes de la barra de menús."))
		self.casilla_paleta = wx.CheckBox(self.panel, label=_("En la pa&leta"))
		self.casilla_paleta.SetValue(self.macro.paleta)
		self.casilla_paleta.SetHelpText(_("La macro aparece en la paleta de órdenes (Ctrl+E)."))
		self.sizer.Add(self.casilla_menu, 0, wx.ALL, self.FromDIP(5))
		self.sizer.Add(self.casilla_paleta, 0, wx.ALL, self.FromDIP(5))
		fila_tecla = wx.BoxSizer(wx.HORIZONTAL)
		_t, self.campo_tecla = crear_campo(self.panel, _("T&ecla:"), wx.TextCtrl, style=wx.TE_READONLY, sizer=fila_tecla,
			ayuda=_("Tecla que ejecuta la macro. Se elige con el botón Elegir la tecla."), expandir=False)
		self.boton(_("Elegir la &tecla..."), _("Pulse la tecla que quiera; se avisa si ya es de otra orden."), self.elegir_tecla, fila_tecla)
		self.boton(_("&Dejar sin tecla"), _("Quita la tecla de la macro (sigue en la paleta y en Mis órdenes)."), self.quitar_tecla, fila_tecla)
		self.sizer.Add(fila_tecla, 0, wx.EXPAND)
		self.etiqueta_pasos = wx.StaticText(self.panel, label=_("&Pasos:"))
		self.lista = ListaAccesible(self.panel, _("Pasos"), columnas=[(_("Orden"), self.FromDIP(260)), (_("Argumento"), self.FromDIP(260))])
		self.lista.SetMinSize(self.FromDIP(wx.Size(540, 200)))
		self.lista.SetHelpText(_("Los pasos se ejecutan en este orden. Izquierda y Derecha leen la orden y su argumento."))
		self.sizer.Add(self.etiqueta_pasos, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.WrapSizer(wx.HORIZONTAL)
		self.boton(_("Añad&ir paso..."), _("Añade un paso: una orden del catálogo (con el buscador de la paleta), decir un texto, esperar o un sonido."),
			self.anadir_paso, fila)
		self.boton(_("Cambiar el ar&gumento..."), _("Cambia el argumento del paso elegido (carpeta, patrón, texto o JSON)."),
			self.cambiar_argumento, fila)
		self.boton(_("&Subir"), _("Sube el paso elegido."), lambda: self.mover(-1), fila)
		self.boton(_("&Bajar"), _("Baja el paso elegido."), lambda: self.mover(1), fila)
		self.boton(_("&Quitar"), _("Quita el paso elegido."), self.quitar_paso, fila)
		self.boton(_("P&robar"), _("Ejecuta la macro tal como está ahora, sin guardarla."), self.probar, fila)
		self.sizer.Add(fila, 0, wx.EXPAND)
		self.terminar(wx.OK | wx.CANCEL, foco=self.campo_nombre)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		self._poner_tecla(self.macro.tecla)
		self.rellenar(0)

	def rellenar(self, foco: int) -> None:
		self.lista.reemplazar_filas([[texto_paso(Paso(p.orden)), macros.texto_argumento(p.argumento) or _("(su diálogo)")
			if argumento_de(p.orden) else ""] for p in self.macro.pasos], conservar_foco=False)
		if self.macro.pasos:
			self.lista.enfocar_fila(min(max(foco, 0), len(self.macro.pasos) - 1), anunciar=False)

	def indice(self) -> int:
		fila = self.lista.fila_actual()
		return fila if 0 <= fila < len(self.macro.pasos) else -1

	def _poner_tecla(self, tecla: str) -> None:
		self.macro.tecla = tecla
		self.campo_tecla.ChangeValue(nombre_visible(tecla) if tecla else _("(sin tecla)"))

	def elegir_tecla(self) -> None:
		from app.ui.dialogos import f_mapa_teclas

		id_orden = f"macro:{self.campo_nombre.GetValue().strip() or self.macro.nombre}"
		tecla = f_mapa_teclas.capturar_tecla(self, id_orden)
		if tecla:
			self.poner_tecla(tecla)

	def poner_tecla(self, tecla: str) -> bool:
		"""Comprueba la tecla con las reglas del mapa de teclas; no quita la tecla a otra orden."""
		from app.ui.dialogos import f_mapa_teclas

		asignadas = self._mapa.como_dict() if self._mapa is not None else {o: tuple(t) for o, t in ordenes.teclas_por_defecto().items()}
		id_orden = f"macro:{self.macro.nombre}"
		asignadas.pop(id_orden, None)
		resultado = f_mapa_teclas.comprobar(asignadas, {**ordenes.ambitos(), id_orden: ordenes.GLOBAL}, ordenes.fijas(), id_orden, tecla)
		if not resultado.permitida:
			f_comun.avisar(self, resultado.motivo, _("Macro"))
			return False
		if resultado.choques:
			nombres = ", ".join(_etiqueta(o) for o in resultado.choques)
			f_comun.avisar(self, _("{t} ya es la tecla de {o}. Elija otra o cámbiela antes en el mapa de teclas.").format(
				t=nombre_visible(tecla), o=nombres), _("Macro"))
			return False
		self._poner_tecla(tecla)
		anuncios.anunciar(_("Tecla: {t}").format(t=nombre_visible(tecla)), anuncios.RESULTADO)
		return True

	def quitar_tecla(self) -> None:
		self._poner_tecla("")
		anuncios.anunciar(_("Sin tecla"), anuncios.RESULTADO)

	def anadir_paso(self) -> None:
		tipos = [_("Una orden del catálogo..."), _("Decir un texto"), _("Esperar unos milisegundos"), _("Un sonido")]
		eleccion = pe_comun.elegir_de_lista(self, _("Añadir un paso"), _("&Tipo de paso:"), tipos)
		if eleccion is None:
			return
		if eleccion == 0:
			id_orden = pe_comun.elegir_orden(self, _("Orden del paso"))
			if not id_orden:
				return
			if not getattr(ordenes.POR_ID.get(id_orden), "grabable", True):
				f_comun.avisar(self, _("«{o}» no se puede usar en una macro.").format(o=_etiqueta(id_orden)), _("Macro"))
				return
			paso = Paso(id_orden)
		else:
			paso = Paso(("paso:decir", "paso:esperar", "paso:sonar")[eleccion - 1])
		if argumento_de(paso.orden) is not None and not self._pedir_argumento(paso):
			if paso.orden.startswith("paso:"):
				return
		posicion = self.indice() + 1 if self.indice() >= 0 else len(self.macro.pasos)
		self.macro.pasos.insert(posicion, paso)
		self.rellenar(posicion)
		self.lista.SetFocus()
		anuncios.anunciar(_("Paso añadido: {p}").format(p=texto_paso(paso)), anuncios.RESULTADO)

	def _pedir_argumento(self, paso: Paso) -> bool:
		tipo = argumento_de(paso.orden)
		ayudas = {
			"ruta": _("&Carpeta o dirección (vacío: se pregunta al ejecutar):"),
			"patron": _("&Patrón (por ejemplo *.jpg;*.png; vacío: se pregunta):"),
			"json": _("&Valores en JSON ({c}):"),
			"texto": _("&Texto:"),
		}
		etiqueta = ayudas.get(tipo.tipo, _("&Texto:")).format(c=", ".join(tipo.campos))
		if paso.orden == "paso:esperar":
			etiqueta = _("&Milisegundos:")
		elif paso.orden == "paso:sonar":
			etiqueta = _("&Id del sonido (por ejemplo macro.fin):")

		actual = json.dumps(paso.argumento, ensure_ascii=False) if isinstance(paso.argumento, dict) else (
			"" if paso.argumento is None else str(paso.argumento))
		texto = f_comun.pedir(self, etiqueta, _("Argumento del paso"), actual)
		if texto is None:
			return False
		try:
			paso.argumento = macros.argumento_valido(paso.orden, texto)
		except macros.ErrorMacro as error:
			f_comun.avisar(self, str(error), _("Argumento del paso"))
			return False
		return True

	def cambiar_argumento(self) -> None:
		i = self.indice()
		if i < 0:
			return
		paso = self.macro.pasos[i]
		if argumento_de(paso.orden) is None:
			f_comun.avisar(self, _("«{o}» no lleva argumento: al ejecutarse hace lo mismo que su tecla.").format(o=texto_paso(paso)),
				_("Macro"))
			return
		if self._pedir_argumento(paso):
			self.rellenar(i)
		self.lista.SetFocus()

	def mover(self, paso: int) -> None:
		i = self.indice()
		destino = i + paso
		if i < 0 or not 0 <= destino < len(self.macro.pasos):
			return
		pasos = self.macro.pasos
		pasos[i], pasos[destino] = pasos[destino], pasos[i]
		self.rellenar(destino)
		self.lista.SetFocus()
		anuncios.anunciar(_("Posición {n} de {t}").format(n=destino + 1, t=len(pasos)), anuncios.RESULTADO)

	def quitar_paso(self) -> None:
		i = self.indice()
		if i < 0:
			return
		paso = self.macro.pasos.pop(i)
		self.rellenar(i)
		self.lista.SetFocus()
		anuncios.anunciar(_("Paso quitado: {p}").format(p=texto_paso(paso)), anuncios.RESULTADO)

	def resultado(self) -> Macro | None:
		try:
			nombre = macros.validar_nombre(self.campo_nombre.GetValue())
		except macros.ErrorMacro as error:
			f_comun.avisar(self, str(error), _("Macro"))
			self.campo_nombre.SetFocus()
			return None
		if nombre.casefold() in self._otras:
			f_comun.avisar(self, _("Ya hay una macro «{n}»").format(n=nombre), _("Macro"))
			self.campo_nombre.SetFocus()
			return None
		return Macro(nombre, self.macro.tecla, self.casilla_menu.GetValue(), self.casilla_paleta.GetValue(), copy.deepcopy(self.macro.pasos))

	def probar(self) -> None:
		macro = self.resultado()
		if macro is not None and self._probar is not None:
			self._probar(macro)

	def aceptar(self) -> bool:
		macro = self.resultado()
		if macro is None:
			return False
		self.macro = macro
		self.cerrar(wx.ID_OK)
		return True


# ── Vista previa al importar ────────────────────────────────────────────────


class DialogoImportarMacro(f_comun.DialogoF):
	"""Vista previa de un ``.zcmacro``: los pasos que ejecutan programas u órdenes empiezan sin marcar."""

	def __init__(self, padre: wx.Window | None, macro: Macro, otras: list[str]) -> None:
		super().__init__(padre, _("Importar una macro"))
		self.macro = macro
		self._otras = {o.casefold() for o in otras}
		self.importada: Macro | None = None
		self.quitados = 0
		_n, self.campo_nombre = crear_campo(self.panel, _("&Nombre de la macro:"), wx.TextCtrl,
			value=macros.nombre_libre([Macro(o) for o in otras], macro.nombre), size=self.FromDIP(wx.Size(360, -1)), sizer=self.sizer,
			ayuda=_("Con este nombre se guardará la macro importada."))
		self.etiqueta_pasos = wx.StaticText(self.panel, label=_("Órdenes que se podrán &ejecutar (marque las que acepta):"))
		textos = [texto_paso(p) for p in macro.pasos]
		self.lista = CheckListBoxAccesible(self.panel, _("Órdenes que se podrán ejecutar"), textos, recordar_posicion=False,
			size=self.FromDIP(wx.Size(560, 220)))
		self.lista.SetHelpText(_("Cada paso con su texto completo. Los que ejecutan programas u órdenes empiezan sin marcar: "
			"márquelos uno a uno solo si se fía de quien le dio la macro. Los no marcados no se importan."))
		self.sizer.Add(self.etiqueta_pasos, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		for indice, paso in enumerate(macro.pasos):
			self.lista.Check(indice, not macros.ejecuta_programas(paso, _permisos))
		self.terminar(wx.OK | wx.CANCEL, foco=self.lista if macro.pasos else self.campo_nombre)
		boton = self.FindWindow(wx.ID_OK)
		boton.SetLabel(_("&Importar"))
		boton.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		if macro.pasos:
			self.lista.SetSelection(0)

	def aceptar(self) -> bool:
		try:
			nombre = macros.validar_nombre(self.campo_nombre.GetValue())
		except macros.ErrorMacro as error:
			f_comun.avisar(self, str(error), self.titulo)
			return False
		if nombre.casefold() in self._otras:
			f_comun.avisar(self, _("Ya hay una macro «{n}»: escriba otro nombre").format(n=nombre), self.titulo)
			self.campo_nombre.SetFocus()
			return False
		sin_marcar = [i for i in range(len(self.macro.pasos)) if not self.lista.IsChecked(i)]
		importada = macros.sin_pasos(self.macro, sin_marcar)
		importada.nombre = nombre
		importada.tecla = ""  # una tecla ajena podría chocar: se elige después en el editor
		self.importada, self.quitados = importada, len(sin_marcar)
		self.cerrar(wx.ID_OK)
		return True


# ── Lista de macros ─────────────────────────────────────────────────────────


class DialogoMacros(pe_comun.DialogoListaPE):
	def __init__(self, padre: wx.Window | None, pe) -> None:
		super().__init__(padre, _("Macros"), _("&Macros:"), [(_("Nombre"), 240), (_("Tecla"), 140), (_("Pasos"), 80)],
			_("Intro ejecuta la macro. Izquierda y Derecha leen nombre, tecla y número de pasos."))
		self.pe = pe
		self.al_cerrar: list = []
		self.boton(_("&Nueva"), _("Crea una macro vacía y abre su editor."), self.nueva, self.botonera)
		self.boton(_("Edi&tar"), _("Abre el editor de la macro elegida."), self.editar, self.botonera)
		self.boton(_("&Duplicar"), _("Crea una copia de la macro elegida."), self.duplicar, self.botonera)
		self.boton(_("E&liminar"), _("Borra la macro elegida; pide confirmación."), self.eliminar, self.botonera)
		self.boton(_("E&jecutar"), _("Cierra la lista y ejecuta la macro elegida."), self.ejecutar, self.botonera)
		self.boton(_("&Grabar una nueva"), _("Cierra la lista y empieza a grabar (Control+Mayúsculas+G termina)."), self.grabar, self.botonera)
		self.boton(_("E&xportar..."), _("Guarda la macro elegida en un archivo .zcmacro para otra persona u otro equipo."),
			self.exportar, self.botonera)
		self.boton(_("&Importar..."), _("Lee un archivo .zcmacro y muestra antes qué órdenes podrá ejecutar."),
			lambda: self.importar(None), self.botonera)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.ejecutar())
		self.cerrar_lista()
		self.rellenar(0)

	def filas(self) -> list[list[str]]:
		return [[m.nombre, nombre_visible(m.tecla) if m.tecla else _("(sin tecla)"), str(len(m.pasos))] for m in self.pe.macros]

	def elegida(self) -> Macro | None:
		i = self.indice()
		return self.pe.macros[i] if 0 <= i < len(self.pe.macros) else None

	def _guardar(self, lista: list[Macro], foco: int, anteriores: dict[str, str] | None = None) -> bool:
		ok = pe_comun.guardar_con_aviso(self, lambda: self.pe.guardar_macros(lista, anteriores), self.titulo)
		self.rellenar(foco)
		self.lista.SetFocus()
		return ok

	def _editor(self, macro: Macro, excepto: str = "") -> Macro | None:
		otras = [m.nombre for m in self.pe.macros if m.nombre.casefold() != excepto.casefold()]
		dialogo = DialogoMacro(self, macro, otras, getattr(self.pe.ventana, "mapa_teclas", None), self.pe.ejecutor.ejecutar_macro)
		return f_comun.mostrar(dialogo, lambda d: d.macro)

	def nueva(self) -> None:
		macro = self._editor(Macro(macros.nombre_libre(self.pe.macros, _("Macro"))))
		if macro is None:
			return
		lista = [*self.pe.macros, macro]
		if self._guardar(lista, len(lista) - 1):
			anuncios.anunciar(_("Macro creada: {n}").format(n=macro.nombre), anuncios.RESULTADO)

	def editar(self) -> None:
		macro = self.elegida()
		if macro is None:
			return
		i = self.pe.macros.index(macro)
		cambiada = self._editor(macro, excepto=macro.nombre)
		if cambiada is None:
			return
		lista = list(self.pe.macros)
		lista[i] = cambiada
		anteriores = {cambiada.nombre: macro.nombre} if cambiada.nombre != macro.nombre else None
		if self._guardar(lista, i, anteriores):
			anuncios.anunciar(_("Macro guardada: {n}").format(n=cambiada.nombre), anuncios.RESULTADO)

	def duplicar(self) -> None:
		macro = self.elegida()
		if macro is None:
			return
		copia = copy.deepcopy(macro)
		copia.nombre = macros.nombre_libre(self.pe.macros, macro.nombre)
		copia.tecla = ""
		lista = [*self.pe.macros, copia]
		if self._guardar(lista, len(lista) - 1):
			anuncios.anunciar(_("Macro duplicada: {n}").format(n=copia.nombre), anuncios.RESULTADO)

	def eliminar(self) -> None:
		macro = self.elegida()
		if macro is None:
			return
		if not f_comun.preguntar(self, _("¿Eliminar la macro «{n}»?").format(n=macro.nombre), _("Eliminar la macro"), peligroso=True):
			return
		i = self.pe.macros.index(macro)
		lista = [m for m in self.pe.macros if m is not macro]
		if self._guardar(lista, i):
			anuncios.anunciar(_("Macro eliminada: {n}").format(n=macro.nombre), anuncios.RESULTADO)

	def ejecutar(self) -> None:
		macro = self.elegida()
		if macro is None:
			return
		self.al_cerrar.append(lambda: self.pe.ejecutor.ejecutar(macro.nombre))
		self.cerrar(wx.ID_CLOSE)

	def grabar(self) -> None:
		ventana = self.pe.ventana
		self.al_cerrar.append(lambda: ventana.ejecutar_orden("macro_grabar"))
		self.cerrar(wx.ID_CLOSE)

	def exportar(self) -> None:
		macro = self.elegida()
		if macro is None:
			return
		ruta = elegir_archivo(self, _("Exportar la macro"), guardar=True, nombre=f"{macro.nombre}{macros.EXTENSION}")
		if not ruta:
			return
		try:
			macros.exportar(macro, Path(ruta))
		except OSError as error:
			f_comun.avisar(self, _("No se pudo exportar: {e}").format(e=error), self.titulo)
			return
		anuncios.anunciar(_("Macro exportada a {r}").format(r=ruta), anuncios.RESULTADO)

	def importar(self, ruta: str | None) -> bool:
		ruta = ruta or elegir_archivo(self, _("Importar una macro"), guardar=False)
		if not ruta:
			return False
		try:
			macro = macros.leer_archivo(Path(ruta))
		except macros.ErrorMacro as error:
			f_comun.avisar(self, str(error), _("Importar una macro"))
			return False
		dialogo = DialogoImportarMacro(self, macro, [m.nombre for m in self.pe.macros])
		resultado = f_comun.mostrar(dialogo, lambda d: (d.importada, d.quitados))
		if resultado is None:
			return False
		importada, quitados = resultado
		lista = [*self.pe.macros, importada]
		if not self._guardar(lista, len(lista) - 1):
			return False
		if quitados:
			anuncios.anunciar(_("Se importó la macro sin {n} pasos que no marcó").format(n=quitados), anuncios.RESULTADO)
		else:
			anuncios.anunciar(_("Macro importada: {n}").format(n=importada.nombre), anuncios.RESULTADO)
		return True


def elegir_archivo(padre: wx.Window | None, titulo: str, guardar: bool, nombre: str = "") -> str | None:
	"""Cuadro de archivo nativo de Windows (accesible) para los ``.zcmacro``."""
	comodin = _("Macros de zCommander (*.zcmacro)|*.zcmacro")
	estilo = (wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) if guardar else (wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
	dialogo = wx.FileDialog(padre, titulo, defaultFile=nombre, wildcard=comodin, style=estilo)
	try:
		return dialogo.GetPath() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def mostrar(padre: wx.Window | None, pe, importar: str | None = None) -> None:
	dialogo = DialogoMacros(padre, pe)
	if importar:
		wx.CallAfter(dialogo.importar, importar)
	acciones = f_comun.mostrar(dialogo, lambda d: list(d.al_cerrar), aceptar=(wx.ID_CLOSE, wx.ID_OK, wx.ID_CANCEL)) or []
	for accion in acciones:
		wx.CallAfter(accion)


def guardar_grabada(padre: wx.Window | None, pe, pasos: list[Paso]) -> Macro | None:
	"""Tras grabar: pide el nombre en el editor y guarda la macro nueva (10.1)."""
	macro = Macro(macros.nombre_libre(pe.macros, _("Macro")), pasos=list(pasos))
	dialogo = DialogoMacro(padre, macro, [m.nombre for m in pe.macros], getattr(pe.ventana, "mapa_teclas", None),
		pe.ejecutor.ejecutar_macro)
	nueva = f_comun.mostrar(dialogo, lambda d: d.macro)
	if nueva is None:
		anuncios.anunciar(_("La macro grabada no se guardó"), anuncios.RESULTADO)
		return None
	if pe_comun.guardar_con_aviso(padre, lambda: pe.guardar_macros([*pe.macros, nueva]), _("Macros")):
		anuncios.anunciar(_("Macro guardada: {n}. Está en la paleta y en Opciones, Macros").format(n=nueva.nombre), anuncios.RESULTADO)
	return nueva
