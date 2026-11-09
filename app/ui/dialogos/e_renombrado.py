# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo de renombrado múltiple (Ctrl+M, sección 8.14).

Por qué está hecho así:

- La vista previa es una ``ListaAccesible`` (Nombre actual, Nombre nuevo,
  Estado) que se rehace 300 ms después de la última pulsación: recalcular en
  cada tecla haría que el lector se quedara mudo con lotes grandes, y esperar
  a pulsar un botón obligaría a ir y volver para comprobar el resultado.
- El estado se lee como texto («Duplicado», «Nombre no válido: carácter :»),
  sin depender de colores; el campo Resumen dice cuántos se renombran.
- Renombrar se niega mientras haya filas malas y lleva el foco a la primera,
  para que la persona la oiga y la corrija sin buscarla.
- El cálculo es el de ``app.services.renombrado``: lo que se ve es lo que se
  renombra (los pares salen del mismo ``Calculo``).
- «Insertar marcador» y «Plantillas» son menús emergentes nativos: se
  recorren con flechas y se leen con el lector sin aprenderse la sintaxis.
- 2.0 (3.4): con máscaras de complementos (``[EXIF:fecha]``), la vista previa
  se calcula también en un hilo (el complemento se activa y lee metadatos): la
  lista muestra «…» hasta que llega el valor, y Renombrar espera a ese cálculo.
"""

from __future__ import annotations

import builtins
import logging
import re
from collections.abc import Callable, Iterable, Mapping, Sequence

import wx

from app.services import renombrado
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.composicion import PreferenciasLectura
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)

RETRASO_MS = 300
#: Marcador de máscara de un complemento (prefijo de dos o más mayúsculas, como [EXIF:fecha]).
_MASCARA_COMPLEMENTO = re.compile(r"(?<!\[)\[[A-Z][A-Z0-9_]+:[^\]\s]+\]")


def tiene_mascaras_de_complementos(opciones: renombrado.OpcionesRenombrado) -> bool:
	"""Verdadero si las máscaras usan marcadores de complementos (``[EXIF:fecha]``...), que se calculan en un hilo."""
	return bool(_MASCARA_COMPLEMENTO.search(opciones.mascara_nombre) or _MASCARA_COMPLEMENTO.search(opciones.mascara_extension))


def anuncios_renombrado(texto: str) -> None:
	from app.ui import anuncios

	anuncios.anunciar(texto, anuncios.RESULTADO)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _avisar(padre: wx.Window, mensaje: str, titulo: str) -> None:
	"""Muestra un error (las pruebas la sustituyen: no hay ShowModal real)."""
	dialogos.mostrar_error(padre, mensaje, titulo)


def _pedir_nombre_plantilla(padre: wx.Window, valor: str) -> str | None:
	return dialogos.pedir_texto(padre, _("&Nombre de la plantilla:"), _("Guardar plantilla"), valor)


def _confirmar(padre: wx.Window, mensaje: str, titulo: str) -> bool:
	return dialogos.confirmar(padre, mensaje, titulo, peligroso=True) == wx.ID_YES


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


class DialogoRenombrado(wx.Dialog):
	"""Campos de máscaras, buscar y reemplazar, mayúsculas, contador y vista previa.

	:param elementos: lo que se va a renombrar, en el orden del panel (el contador sigue ese orden).
	:param existentes: nombres que ya hay en cada carpeta (ver ``renombrado.calcular``).
	:param validar_windows: reglas de nombres de Windows (disco local).
	:param leer_preferencias: preferencias de lectura por columnas de la configuración.
	"""

	def __init__(self, padre: wx.Window | None, elementos: Sequence[renombrado.Elemento],
			existentes: Mapping[str, Iterable[str]] | None = None, validar_windows: bool = True,
			leer_preferencias: Callable[[], PreferenciasLectura] | None = None,
			opciones: renombrado.OpcionesRenombrado | None = None) -> None:
		titulo = _("Renombrado múltiple")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		self.titulo = titulo
		self.elementos = list(elementos)
		self.existentes = existentes
		self.validar_windows = validar_windows
		self.calculo = renombrado.Calculo([])
		self._temporizador: wx.CallLater | None = None
		self._ultima_mascara: wx.TextCtrl | None = None
		#: 2.0 (3.4): cálculo en un hilo cuando hay máscaras de complementos (generación, opciones, completo).
		self._generacion = 0
		self._calculo_completo = True
		self._aceptar_al_terminar = False

		panel = wx.Panel(self)
		self.panel = panel
		raiz = wx.BoxSizer(wx.VERTICAL)
		ancho = panel.FromDIP(wx.Size(300, -1))

		# Máscaras.
		fila = wx.BoxSizer(wx.HORIZONTAL)
		columna = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_mascara_nombre = crear_campo(panel, _("&Máscara del nombre:"), wx.TextCtrl, size=ancho, sizer=columna,
			ayuda=_("Máscara del nombre nuevo. [N] es el nombre actual sin extensión; [N2-5] del carácter 2 al 5; "
				"[C] el contador; [Y], [M] y [D] año, mes y día de modificación; [P] la carpeta. "
				"El botón Insertar marcador los muestra todos."))
		fila.Add(columna, 1, wx.EXPAND)
		columna = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_mascara_extension = crear_campo(panel, _("Máscara de la &extensión:"), wx.TextCtrl,
			size=panel.FromDIP(wx.Size(140, -1)), sizer=columna,
			ayuda=_("Máscara de la extensión nueva, sin el punto. [E] es la extensión actual; vacío la quita."))
		fila.Add(columna, 0, wx.EXPAND)
		raiz.Add(fila, 0, wx.EXPAND)
		self.boton_insertar = wx.Button(panel, label=_("Insert&ar marcador..."))
		self.boton_insertar.SetHelpText(_("Menú con todos los marcadores; el elegido se escribe en la última máscara en la que estuvo."))
		raiz.Add(self.boton_insertar, 0, wx.LEFT | wx.BOTTOM, 5)

		# Buscar y reemplazar.
		fila = wx.BoxSizer(wx.HORIZONTAL)
		columna = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_buscar = crear_campo(panel, _("&Buscar:"), wx.TextCtrl, size=ancho, sizer=columna,
			ayuda=_("Texto que se busca en el nombre nuevo. Varios separados por una barra vertical."))
		fila.Add(columna, 1, wx.EXPAND)
		columna = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_reemplazar = crear_campo(panel, _("Reemplazar &por:"), wx.TextCtrl, size=ancho, sizer=columna,
			ayuda=_("Texto que sustituye a lo buscado. Con varios separados por barra vertical, cada uno sustituye al suyo."))
		fila.Add(columna, 1, wx.EXPAND)
		raiz.Add(fila, 0, wx.EXPAND)
		casillas = wx.WrapSizer(wx.HORIZONTAL)
		self.casilla_regex = wx.CheckBox(panel, label=_("Expresión re&gular"))
		self.casilla_regex.SetHelpText(_("Buscar es una expresión regular; en Reemplazar, \\1 o $1 es el primer grupo."))
		self.casilla_distinguir = wx.CheckBox(panel, label=_("&Distinguir mayúsculas"))
		self.casilla_primera = wx.CheckBox(panel, label=_("&Solo la primera coincidencia"))
		self.casilla_extension = wx.CheckBox(panel, label=_("Aplicar también a la e&xtensión"))
		self.casilla_extension.SetHelpText(_("Buscar y reemplazar también en la extensión, no solo en el nombre."))
		for casilla in (self.casilla_regex, self.casilla_distinguir, self.casilla_primera, self.casilla_extension):
			casillas.Add(casilla, 0, wx.ALL, 5)
		raiz.Add(casillas, 0, wx.EXPAND)

		# Mayúsculas y contador.
		fila = wx.BoxSizer(wx.HORIZONTAL)
		textos = renombrado.textos_mayusculas()
		for etiqueta, atributo in ((_("Mayúsculas del n&ombre:"), "lista_mayusculas_nombre"),
				(_("Mayúsc&ulas de la extensión:"), "lista_mayusculas_extension")):
			columna = wx.BoxSizer(wx.VERTICAL)
			_e, lista = crear_campo(panel, etiqueta, wx.Choice, choices=textos, sizer=columna)
			lista.SetSelection(0)
			setattr(self, atributo, lista)
			fila.Add(columna, 0)
		for etiqueta, atributo, minimo, maximo, ayuda in (
				(_("Contador, &valor inicial:"), "campo_inicio", -999999, 999999, _("Primer valor de [C].")),
				(_("Contador, &incremento:"), "campo_paso", -9999, 9999, _("Lo que suma [C] de un elemento al siguiente.")),
				(_("Contador, ci&fras:"), "campo_digitos", 1, 12, _("Cifras mínimas de [C]; se rellena con ceros a la izquierda."))):
			columna = wx.BoxSizer(wx.VERTICAL)
			_e, campo = crear_campo(panel, etiqueta, wx.SpinCtrl, min=minimo, max=maximo, initial=1,
				size=panel.FromDIP(wx.Size(110, -1)), ayuda=ayuda, sizer=columna, expandir=False)
			setattr(self, atributo, campo)
			fila.Add(columna, 0)
		raiz.Add(fila, 0, wx.EXPAND)

		# Vista previa.
		_e = wx.StaticText(panel, label=_("Vista previa de &los nombres:"))
		raiz.Add(_e, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.lista = ListaAccesible(
			panel, _("Vista previa de los nombres"),
			columnas=[(_("Nombre actual"), panel.FromDIP(240)), (_("Nombre nuevo"), panel.FromDIP(240)), (_("Estado"), panel.FromDIP(200))],
			virtual=True, leer_preferencias=leer_preferencias)
		self.lista.SetMinSize(panel.FromDIP(wx.Size(700, 220)))
		raiz.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		_e, self.campo_resumen = crear_campo(panel, _("&Resumen:"), wx.TextCtrl, style=wx.TE_READONLY, sizer=raiz,
			ayuda=_("Cuántos se renombran y cuántos tienen problemas."))

		# Botones.
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_plantillas = wx.Button(panel, label=_("Plan&tillas..."))
		self.boton_plantillas.SetHelpText(_("Guardar, cargar o borrar combinaciones de estos campos."))
		self.boton_renombrar = wx.Button(panel, wx.ID_OK, _("Re&nombrar"))
		self.boton_renombrar.SetHelpText(_("Renombra los que dicen Correcto. No se puede mientras haya duplicados o nombres no válidos."))
		self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, _("&Cancelar"))
		self.boton_renombrar.SetDefault()
		botones.Add(self.boton_plantillas, 0, wx.RIGHT, 5)
		botones.AddStretchSpacer()
		botones.Add(self.boton_renombrar, 0, wx.RIGHT, 5)
		botones.Add(self.boton_cancelar, 0)
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 8)

		panel.SetSizer(raiz)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)

		self.aplicar_opciones(opciones or renombrado.OpcionesRenombrado())
		self._enlazar()
		preparar_dialogo(self, foco_inicial=self.campo_mascara_nombre)
		self.actualizar_vista_previa()
		self.CentreOnParent()

	# ── Eventos ────────────────────────────────────────────────────────────────

	def _enlazar(self) -> None:
		for campo in (self.campo_mascara_nombre, self.campo_mascara_extension, self.campo_buscar, self.campo_reemplazar):
			campo.Bind(wx.EVT_TEXT, self._al_teclear)
		for campo in (self.campo_inicio, self.campo_paso, self.campo_digitos):
			campo.Bind(wx.EVT_SPINCTRL, self._al_teclear)
			campo.Bind(wx.EVT_TEXT, self._al_teclear)
		for casilla in (self.casilla_regex, self.casilla_distinguir, self.casilla_primera, self.casilla_extension):
			casilla.Bind(wx.EVT_CHECKBOX, self._al_cambiar)
		for lista in (self.lista_mayusculas_nombre, self.lista_mayusculas_extension):
			lista.Bind(wx.EVT_CHOICE, self._al_cambiar)
		for mascara in (self.campo_mascara_nombre, self.campo_mascara_extension):
			mascara.Bind(wx.EVT_SET_FOCUS, self._al_entrar_mascara)
		self.boton_insertar.Bind(wx.EVT_BUTTON, self._al_insertar)
		self.boton_plantillas.Bind(wx.EVT_BUTTON, self._al_plantillas)
		self.boton_renombrar.Bind(wx.EVT_BUTTON, self._al_renombrar)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)

	def _al_teclear(self, evento: wx.Event) -> None:
		"""Espera 300 ms sin teclear antes de recalcular (sección 8.14)."""
		evento.Skip()
		if self._temporizador is not None and self._temporizador.IsRunning():
			self._temporizador.Restart(RETRASO_MS)
		else:
			self._temporizador = wx.CallLater(RETRASO_MS, self._tras_espera)

	def _tras_espera(self) -> None:
		if self:
			self.actualizar_vista_previa()

	def _al_cambiar(self, evento: wx.Event) -> None:
		evento.Skip()
		self.actualizar_vista_previa()

	def _al_entrar_mascara(self, evento: wx.FocusEvent) -> None:
		self._ultima_mascara = evento.GetEventObject()
		evento.Skip()

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self and self._temporizador is not None:
			self._temporizador.Stop()
		evento.Skip()

	# ── Campos ─────────────────────────────────────────────────────────────────

	def opciones(self) -> renombrado.OpcionesRenombrado:
		return renombrado.OpcionesRenombrado(
			mascara_nombre=self.campo_mascara_nombre.GetValue(),
			mascara_extension=self.campo_mascara_extension.GetValue(),
			buscar=self.campo_buscar.GetValue(),
			reemplazar=self.campo_reemplazar.GetValue(),
			regex=self.casilla_regex.GetValue(),
			distinguir_mayusculas=self.casilla_distinguir.GetValue(),
			solo_primera=self.casilla_primera.GetValue(),
			aplicar_extension=self.casilla_extension.GetValue(),
			mayusculas_nombre=renombrado.MAYUSCULAS[max(0, self.lista_mayusculas_nombre.GetSelection())],
			mayusculas_extension=renombrado.MAYUSCULAS[max(0, self.lista_mayusculas_extension.GetSelection())],
			contador_inicio=self.campo_inicio.GetValue(),
			contador_paso=self.campo_paso.GetValue(),
			contador_digitos=self.campo_digitos.GetValue(),
		)

	def aplicar_opciones(self, opciones: renombrado.OpcionesRenombrado) -> None:
		"""Rellena los campos (al abrir y al cargar una plantilla) sin disparar un recálculo por campo."""
		self.campo_mascara_nombre.ChangeValue(opciones.mascara_nombre)
		self.campo_mascara_extension.ChangeValue(opciones.mascara_extension)
		self.campo_buscar.ChangeValue(opciones.buscar)
		self.campo_reemplazar.ChangeValue(opciones.reemplazar)
		self.casilla_regex.SetValue(opciones.regex)
		self.casilla_distinguir.SetValue(opciones.distinguir_mayusculas)
		self.casilla_primera.SetValue(opciones.solo_primera)
		self.casilla_extension.SetValue(opciones.aplicar_extension)
		self.lista_mayusculas_nombre.SetSelection(renombrado.MAYUSCULAS.index(opciones.mayusculas_nombre))
		self.lista_mayusculas_extension.SetSelection(renombrado.MAYUSCULAS.index(opciones.mayusculas_extension))
		self.campo_inicio.SetValue(opciones.contador_inicio)
		self.campo_paso.SetValue(opciones.contador_paso)
		self.campo_digitos.SetValue(max(1, opciones.contador_digitos))

	# ── Vista previa ───────────────────────────────────────────────────────────

	def actualizar_vista_previa(self) -> renombrado.Calculo:
		"""Recalcula y rehace la lista conservando la fila en la que está la persona."""
		if self._temporizador is not None and self._temporizador.IsRunning():
			self._temporizador.Stop()
		opciones = self.opciones()
		self._generacion += 1
		# En el hilo de la interfaz, una máscara de complemento sin calcular da «…» (nunca bloquea).
		self.calculo = renombrado.calcular(self.elementos, opciones, self.existentes, self.validar_windows)
		self._mostrar_calculo(self.calculo)
		self._calculo_completo = not tiene_mascaras_de_complementos(opciones)
		if not self._calculo_completo:
			self._calcular_en_hilo(opciones, self._generacion)
		return self.calculo

	def _mostrar_calculo(self, calculo: renombrado.Calculo) -> None:
		filas = [(r.actual, r.nuevo, r.texto) for r in calculo.resultados]
		self.lista.reemplazar_filas(filas)
		self.campo_resumen.ChangeValue(renombrado.resumen(calculo))

	def _calcular_en_hilo(self, opciones: renombrado.OpcionesRenombrado, generacion: int) -> None:
		"""2.0 (3.4): con máscaras de complementos, el cálculo va en un hilo (activa el complemento y lee metadatos)."""
		import threading

		elementos, existentes, validar = list(self.elementos), self.existentes, self.validar_windows

		def trabajo() -> None:
			try:
				calculo = renombrado.calcular(elementos, opciones, existentes, validar)
			except Exception:  # noqa: BLE001 - un complemento roto deja la vista previa con «…»
				log.exception("Falló el cálculo del renombrado con máscaras de complementos")
				return
			wx.CallAfter(self._al_calcular, generacion, calculo)

		threading.Thread(target=trabajo, name="renombrado-vista-previa", daemon=True).start()

	def _al_calcular(self, generacion: int, calculo: renombrado.Calculo) -> None:
		if not self or generacion != self._generacion:
			return
		self.calculo = calculo
		self._calculo_completo = True
		self._mostrar_calculo(calculo)
		if self._aceptar_al_terminar:
			self._aceptar_al_terminar = False
			self.aceptar(recalcular=False)

	def pares(self) -> list[tuple[str, str]]:
		return renombrado.pares(self.calculo)

	def aceptar(self, recalcular: bool = True) -> bool:
		"""Cierra con Renombrar si no hay problemas; si los hay, los dice y lleva el foco a la primera fila mala.

		Con máscaras de complementos aún sin calcular («…»), espera al hilo y renombra al terminar.
		"""
		calculo = self.actualizar_vista_previa() if recalcular else self.calculo
		if not self._calculo_completo:
			self._aceptar_al_terminar = True
			anuncios_renombrado(_("Calculando los nombres de las máscaras de los complementos..."))
			return False
		if calculo.error:
			_avisar(self, renombrado.resumen(calculo), self.titulo)
			self.campo_mascara_nombre.SetFocus()
			return False
		mala = calculo.primera_mala()
		if mala >= 0:
			resultado = calculo.resultados[mala]
			_avisar(self, _("No se puede renombrar: {r}. La primera fila con problemas es «{a}»: {t}.").format(
				r=renombrado.resumen(calculo), a=resultado.actual, t=resultado.texto), self.titulo)
			self.lista.SetFocus()
			self.lista.enfocar_fila(mala)
			return False
		if not self.pares():
			_avisar(self, _("No hay nombres que cambiar: todos quedan igual."), self.titulo)
			self.campo_mascara_nombre.SetFocus()
			return False
		_terminar(self, wx.ID_OK)
		return True

	def _al_renombrar(self, _evento: wx.CommandEvent) -> None:
		self.aceptar()

	# ── Insertar marcador ──────────────────────────────────────────────────────

	def menu_marcadores(self) -> tuple[wx.Menu, dict[int, str]]:
		menu = wx.Menu()
		ids: dict[int, str] = {}
		for marcador, descripcion in renombrado.marcadores():
			# Sin «&»: los corchetes no admiten letra y el lector lee el marcador seguido de la descripción.
			elemento = menu.Append(wx.ID_ANY, f"{marcador.replace('&', '&&')}  {descripcion}")
			ids[elemento.GetId()] = marcador
		return menu, ids

	def insertar_marcador(self, marcador: str) -> None:
		"""Escribe el marcador donde estaba el cursor de la última máscara.

		Al llegar con Tab, Windows selecciona todo el campo: en ese caso se añade
		al final en lugar de sustituir la máscara entera sin querer.
		"""
		campo = self._ultima_mascara or self.campo_mascara_nombre
		desde, hasta = campo.GetSelection()
		longitud = campo.GetLastPosition()
		campo.SetFocus()
		if desde == 0 and hasta == longitud and longitud > 0:
			desde = hasta = longitud
		campo.SetSelection(desde, hasta)
		campo.WriteText(marcador)

	def _al_insertar(self, _evento: wx.CommandEvent) -> None:
		menu, ids = self.menu_marcadores()
		try:
			elegido = self.GetPopupMenuSelectionFromUser(menu, self.boton_insertar.GetPosition())
		finally:
			menu.Destroy()
		if elegido in ids:
			self.insertar_marcador(ids[elegido])

	# ── Plantillas ─────────────────────────────────────────────────────────────

	def menu_plantillas(self) -> tuple[wx.Menu, dict[int, tuple[str, str]]]:
		"""Menú con «Guardar», y «Cargar» y «Borrar» con las guardadas. Devuelve el menú y id → (acción, nombre)."""
		menu = wx.Menu()
		acciones: dict[int, tuple[str, str]] = {}
		elemento = menu.Append(wx.ID_ANY, _("&Guardar la combinación actual..."))
		acciones[elemento.GetId()] = ("guardar", "")
		plantillas = renombrado.leer_plantillas()
		cargar, borrar = wx.Menu(), wx.Menu()
		for plantilla in plantillas:
			texto = plantilla["nombre"].replace("&", "&&")
			acciones[cargar.Append(wx.ID_ANY, texto).GetId()] = ("cargar", plantilla["nombre"])
			acciones[borrar.Append(wx.ID_ANY, texto).GetId()] = ("borrar", plantilla["nombre"])
		submenu_cargar = menu.AppendSubMenu(cargar, _("&Cargar"))
		submenu_borrar = menu.AppendSubMenu(borrar, _("&Borrar"))
		if not plantillas:
			submenu_cargar.Enable(False)
			submenu_borrar.Enable(False)
		return menu, acciones

	def guardar_plantilla(self) -> bool:
		nombre = _pedir_nombre_plantilla(self, "")
		if not nombre or not nombre.strip():
			return False
		try:
			renombrado.guardar_plantilla(nombre, self.opciones().campos())
		except (OSError, ValueError) as error:
			log.warning("No se pudo guardar la plantilla de renombrado %s", nombre, exc_info=True)
			_avisar(self, _("No se pudo guardar la plantilla: {e}").format(e=error), self.titulo)
			return False
		return True

	def cargar_plantilla(self, nombre: str) -> bool:
		for plantilla in renombrado.leer_plantillas():
			if plantilla["nombre"] == nombre:
				self.aplicar_opciones(renombrado.OpcionesRenombrado.desde_campos(plantilla["campos"]))
				self.actualizar_vista_previa()
				self.campo_mascara_nombre.SetFocus()
				return True
		return False

	def borrar_plantilla(self, nombre: str) -> bool:
		if not _confirmar(self, _("¿Borrar la plantilla «{n}»?").format(n=nombre), _("Borrar plantilla")):
			return False
		try:
			return renombrado.borrar_plantilla(nombre)
		except OSError as error:
			log.warning("No se pudo borrar la plantilla de renombrado %s", nombre, exc_info=True)
			_avisar(self, _("No se pudo borrar la plantilla: {e}").format(e=error), self.titulo)
			return False

	def _al_plantillas(self, _evento: wx.CommandEvent) -> None:
		menu, acciones = self.menu_plantillas()
		try:
			elegido = self.GetPopupMenuSelectionFromUser(menu, self.boton_plantillas.GetPosition())
		finally:
			menu.Destroy()
		accion, nombre = acciones.get(elegido, ("", ""))
		if accion == "guardar":
			self.guardar_plantilla()
		elif accion == "cargar":
			self.cargar_plantilla(nombre)
		elif accion == "borrar":
			self.borrar_plantilla(nombre)


def pedir_renombrado(padre: wx.Window | None, elementos: Sequence[renombrado.Elemento],
		existentes: Mapping[str, Iterable[str]] | None = None, validar_windows: bool = True,
		leer_preferencias: Callable[[], PreferenciasLectura] | None = None) -> list[tuple[str, str]] | None:
	"""Pares (ruta, nombre nuevo) que la persona aceptó, o ``None`` si cancela."""
	dialogo = DialogoRenombrado(padre, elementos, existentes, validar_windows, leer_preferencias)
	foco_previo = wx.Window.FindFocus()
	try:
		return dialogo.pares() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()
		if foco_previo:
			foco_previo.SetFocus()
