# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Sincronizar carpetas» (Ctrl+Mayús+F10, sección 8.13).

Recoge las opciones, compara en un hilo (``diferencias_carpetas.comparar``)
y muestra una fila por diferencia con su acción, que la persona puede cambiar.
Al pulsar Sincronizar deja en ``operacion`` una ``OperacionSincronizar`` y
se cierra con Aceptar: la lanza quien abrió el diálogo (``ctx.lanzar``), así
el diálogo se prueba sin el motor de operaciones.

La lista:

- Selección múltiple nativa; las teclas D (copiar a la derecha), I (copiar a
  la izquierda), N (nada) y B (borrar en el destino) cambian la acción de las
  filas seleccionadas, o de la del cursor, y se anuncia el cambio. También
  desde el menú contextual (tecla Aplicaciones o Mayús+F10).
- La búsqueda por letra nativa está desactivada para que esas letras no
  salten de fila.
- La acción se lee como texto («Copiar a la derecha», «Conflicto: cambiaron los dos»,
  «Archivo frente a carpeta: nada»).
- Cambiar la dirección o la casilla de eliminar después de Comparar vuelve a
  proponer las acciones con las mismas diferencias (sin releer el disco) y lo
  anuncia; los cambios hechos a mano en la lista se sustituyen.
"""

from __future__ import annotations

import builtins
import logging
import os
from collections.abc import Sequence

import wx

from app.services import diferencias_carpetas as dc
from app.services.diferencias_carpetas import Accion, Criterio, Diferencia, Direccion
from app.services.operaciones.copiar import OpcionesCopia
from app.services.operaciones.sincronizar import OperacionSincronizar
from app.services.vfs import base, resolver, rutas
from app.ui import anuncios
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos.b_buscar import preferencias_lectura

log = logging.getLogger(__name__)

#: Teclas de la lista y la acción que ponen («B» depende de la dirección).
TECLAS_ACCION = {ord("D"): Accion.COPIAR_DERECHA, ord("I"): Accion.COPIAR_IZQUIERDA, ord("N"): Accion.NADA}

Lado = tuple[base.Proveedor, str, str]  # (proveedor, ruta, texto que se muestra)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _filtros() -> list[tuple[str, frozenset[Accion] | None]]:
	return [
		(_("Todas"), None),
		(_("Copiar a la derecha"), frozenset({Accion.COPIAR_DERECHA})),
		(_("Copiar a la izquierda"), frozenset({Accion.COPIAR_IZQUIERDA})),
		(_("Eliminar"), frozenset({Accion.ELIMINAR_DERECHA, Accion.ELIMINAR_IZQUIERDA})),
		(_("Nada"), frozenset({Accion.NADA})),
		(_("Conflictos"), frozenset({Accion.CONFLICTO})),
	]


def resolver_lado(texto: str, lado: Lado | None) -> tuple[base.Proveedor, str]:
	"""(proveedor, carpeta) de lo escrito. Toca el disco: SOLO en un hilo.

	Si el texto es el del panel, se usa su proveedor (también un comprimido o un
	servidor); si no, se toma como carpeta del disco.

	:raises base.NoEncontrado: si la carpeta no existe.
	"""
	texto = texto.strip()
	if lado is not None and texto == lado[2]:
		return lado[0], lado[1]
	ruta = rutas.normalizar(os.path.expandvars(texto))
	if not os.path.isdir(ruta):
		raise base.NoEncontrado(_("No se encuentra la carpeta «{c}».").format(c=texto), ruta)
	return resolver.proveedor_local(), ruta


def _trabajo_comparar(tarea, texto_i, texto_d, lado_i, lado_d, criterio, subcarpetas, patron, tolerancia):
	izquierda = resolver_lado(texto_i, lado_i)
	derecha = resolver_lado(texto_d, lado_d)
	if izquierda[0] is derecha[0] and rutas.normalizar(izquierda[1]).casefold() == rutas.normalizar(derecha[1]).casefold():
		raise base.ErrorArchivos(_("Las dos carpetas son la misma."), izquierda[1])
	errores: list[str] = []
	diferencias = dc.comparar(izquierda, derecha, criterio, subcarpetas, patron, tolerancia,
		cancelacion=tarea.token, al_error=lambda r, e: errores.append(f"{r}: {e.mensaje}"))
	return izquierda, derecha, diferencias, errores


class DialogoSincronizar(wx.Dialog):
	"""Comparar y sincronizar dos carpetas.

	:param izquierda, derecha: ``(proveedor, ruta, texto)`` de cada panel.
	:param tareas: ``GestorTareas`` donde corre la comparación.
	"""

	def __init__(self, padre: wx.Window | None, config, tareas, izquierda: Lado | None, derecha: Lado | None) -> None:
		super().__init__(padre, title=_("Sincronizar carpetas"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			name=_("Sincronizar carpetas"))
		self._config = config
		self._tareas = tareas
		self._lados = (izquierda, derecha)
		self._tarea = None
		self._peticion = 0
		self._filas: list[Diferencia] = []
		#: Lo que devolvió la última comparación, sin acciones: se vuelve a proponer al cambiar la dirección.
		self._diferencias: list[Diferencia] | None = None
		self._visibles: list[int] = []
		self._resueltos: tuple[tuple[base.Proveedor, str], tuple[base.Proveedor, str]] | None = None
		#: La operación preparada al pulsar Sincronizar (la lanza quien abrió el diálogo).
		self.operacion: OperacionSincronizar | None = None

		panel = wx.Panel(self)
		self.panel = panel
		s = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_izquierda = crear_campo(panel, _("&Izquierda:"), wx.TextCtrl, value=izquierda[2] if izquierda else "",
			ayuda=_("Carpeta del lado izquierdo (la del panel izquierdo)."), sizer=s)
		_e, self.campo_derecha = crear_campo(panel, _("De&recha:"), wx.TextCtrl, value=derecha[2] if derecha else "",
			ayuda=_("Carpeta del lado derecho (la del panel derecho)."), sizer=s)
		self._direcciones = list(Direccion)
		_e, self.lista_direccion = crear_campo(panel, _("&Dirección:"), wx.Choice, choices=[d.texto for d in self._direcciones],
			ayuda=_("Hacia dónde se copia. En los dos sentidos, cada archivo va hacia el lado donde falta o es más antiguo."), sizer=s)
		self.lista_direccion.SetSelection(0)
		self._criterios = [Criterio.FECHA, Criterio.TAMANO, Criterio.CONTENIDO]
		_e, self.lista_criterio = crear_campo(panel, _("Criteri&o:"), wx.Choice,
			choices=[_("Fecha"), _("Fecha y tamaño"), _("Contenido")],
			ayuda=_("Cómo se decide que dos archivos son distintos. Contenido lee los dos archivos y es más lento."), sizer=s)
		self.lista_criterio.SetSelection(1)
		self.casilla_subcarpetas = self._casilla(panel, s, _("Incluir s&ubcarpetas"), _("Compara también el contenido de las subcarpetas."), True)
		_e, self.campo_patron = crear_campo(panel, _("&Patrón de archivos:"), wx.TextCtrl, value="*",
			ayuda=_("Solo los archivos que coinciden (*.mp3;*.flac). * los compara todos."), sizer=s)
		self.casilla_fat = self._casilla(panel, s, _("I&gnorar diferencias de fecha de hasta 2 s"),
			_("Los discos FAT y muchos USB guardan la hora con 2 segundos de precisión."), True)
		self.casilla_eliminar = self._casilla(panel, s, _("&Eliminar en el destino lo que no está en el origen"),
			_("Solo en un sentido. Propone borrar en el destino lo que no existe en el origen."), False)
		self.boton_comparar = wx.Button(panel, label=_("&Comparar"))
		self.boton_comparar.SetHelpText(_("Compara las dos carpetas y llena la lista de diferencias."))
		s.Add(self.boton_comparar, 0, wx.ALL, 4)
		self._filtros = _filtros()
		_e, self.lista_filtro = crear_campo(panel, _("&Mostrar:"), wx.Choice, choices=[t for t, _a in self._filtros],
			ayuda=_("Qué filas se ven en la lista, según su acción."), sizer=s)
		self.lista_filtro.SetSelection(0)
		_e, self.lista = crear_campo(panel, _("Di&ferencias:"), lambda p, **k: ListaAccesible(
			p, _("Diferencias"), columnas=[(_("Nombre"), p.FromDIP(240)), (_("Izquierda"), p.FromDIP(170)),
				(_("Acción"), p.FromDIP(170)), (_("Derecha"), p.FromDIP(170))],
			estilo=wx.LC_REPORT, leer_preferencias=preferencias_lectura(config)), sizer=s)
		self.lista.SetMinSize(panel.FromDIP(wx.Size(760, 220)))
		self.lista.SetHelpText(_(
			"Una fila por diferencia. D copia a la derecha, I copia a la izquierda, N no hace nada y B borra en el destino; "
			"actúan sobre las filas seleccionadas. Intro compara el contenido de la fila. Izquierda y derecha leen las columnas."))
		_e, self.campo_estado = crear_campo(panel, _("Es&tado:"), wx.TextCtrl, value=_("Pulse Comparar para ver las diferencias."),
			style=wx.TE_READONLY, ayuda=_("Resumen de la comparación y de lo que hará Sincronizar."), sizer=s)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_contenido = wx.Button(panel, label=_("Comparar co&ntenido"))
		self.boton_contenido.SetHelpText(_("Abre la comparación de los dos archivos de la fila."))
		self.boton_sincronizar = wx.Button(panel, label=_("&Sincronizar"))
		self.boton_sincronizar.SetHelpText(_("Ejecuta las acciones de la lista como una operación (con progreso, cola y resumen)."))
		self.boton_cerrar = wx.Button(panel, wx.ID_CANCEL, label=_("Cerr&ar"))
		for boton in (self.boton_contenido, self.boton_sincronizar, self.boton_cerrar):
			botones.Add(boton, 0, wx.ALL, 4)
		s.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		panel.SetSizer(s)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.boton_comparar.SetDefault()

		self.boton_comparar.Bind(wx.EVT_BUTTON, lambda _e: self.comparar())
		self.boton_contenido.Bind(wx.EVT_BUTTON, lambda _e: self.comparar_contenido())
		self.boton_sincronizar.Bind(wx.EVT_BUTTON, lambda _e: self.sincronizar())
		self.lista_filtro.Bind(wx.EVT_CHOICE, lambda _e: self._mostrar())
		self.lista_direccion.Bind(wx.EVT_CHOICE, lambda _e: self._al_cambiar_direccion())
		self.casilla_eliminar.Bind(wx.EVT_CHECKBOX, lambda _e: self.recalcular())
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
		self.lista.Bind(wx.EVT_CHAR, self._al_caracter_lista)
		self.lista.Bind(wx.EVT_CONTEXT_MENU, self._menu_contextual)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
		preparar_dialogo(self, foco_inicial=self.boton_comparar)
		# Después de preparar_dialogo: wx llama primero al último enlazado.
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self._al_cambiar_direccion()
		self._actualizar_botones()
		self.CentreOnParent()

	@staticmethod
	def _casilla(padre: wx.Window, sizer: wx.Sizer, etiqueta: str, ayuda: str, valor: bool) -> wx.CheckBox:
		casilla = wx.CheckBox(padre, label=etiqueta)
		casilla.SetValue(valor)
		casilla.SetHelpText(ayuda)
		sizer.Add(casilla, 0, wx.ALL, 4)
		return casilla

	# ── Opciones ───────────────────────────────────────────────────────────────

	@property
	def direccion(self) -> Direccion:
		return self._direcciones[max(0, self.lista_direccion.GetSelection())]

	@property
	def criterio(self) -> Criterio:
		return self._criterios[max(0, self.lista_criterio.GetSelection())]

	def _al_cambiar_direccion(self) -> None:
		# Borrar lo que sobra solo tiene sentido en un sentido (sección 8.13).
		self.casilla_eliminar.Enable(self.direccion != Direccion.AMBOS)
		self.recalcular()

	def recalcular(self) -> bool:
		"""Vuelve a proponer las acciones con la dirección y la casilla de eliminar actuales.

		Las diferencias no dependen de la dirección: no hace falta volver a
		leer el disco. Se anuncia porque la lista cambia sin que la persona
		esté en ella. Devuelve False si todavía no se ha comparado.
		"""
		if self._diferencias is None:
			return False
		self._filas = dc.proponer(self._diferencias, self.direccion, self.eliminar_sobrantes)
		self._mostrar()
		texto = _("Acciones recalculadas ({d}). {r}").format(d=self.direccion.texto.lower(), r=dc.resumen_acciones(self._filas))
		self.campo_estado.SetValue(texto)
		anuncios.anunciar(texto, anuncios.RESULTADO)
		self._actualizar_botones()
		return True

	@property
	def eliminar_sobrantes(self) -> bool:
		return self.casilla_eliminar.IsEnabled() and self.casilla_eliminar.GetValue()

	# ── Comparar ───────────────────────────────────────────────────────────────

	@property
	def comparando(self) -> bool:
		return self._tarea is not None and not self._tarea.terminada

	def comparar(self) -> bool:
		if self.comparando:
			return False
		texto_i, texto_d = self.campo_izquierda.GetValue().strip(), self.campo_derecha.GetValue().strip()
		if not texto_i or not texto_d:
			anuncios.anunciar(_("Escriba las dos carpetas"), anuncios.ESENCIAL)
			return False
		patron = self.campo_patron.GetValue().strip()
		patron = "" if patron in ("", "*", "*.*") else patron
		self._peticion += 1
		peticion = self._peticion
		self.campo_estado.SetValue(_("Comparando..."))
		anuncios.anunciar(_("Comparando"), anuncios.RESULTADO)
		self._tarea = self._tareas.enviar(
			_trabajo_comparar, texto_i, texto_d, self._lados[0], self._lados[1], self.criterio,
			self.casilla_subcarpetas.GetValue(), patron, 2.0 if self.casilla_fat.GetValue() else 0.0,
			al_terminar=lambda r: self._al_comparar(peticion, r), al_fallar=lambda e: self._al_fallar(peticion, e),
			nombre="comparar-carpetas",
		)
		return self._tarea is not None

	def _al_comparar(self, peticion: int, resultado) -> None:
		if not self or peticion != self._peticion:
			return
		self._tarea = None
		izquierda, derecha, diferencias, errores = resultado
		self.poner_diferencias(izquierda, derecha, diferencias)
		texto = self.campo_estado.GetValue()
		if errores:
			log.info("Comparación con %d errores; el primero: %s", len(errores), errores[0])
			texto += ". " + _("{n} sin leer").format(n=len(errores))
			self.campo_estado.SetValue(texto)
		anuncios.anunciar(texto, anuncios.RESULTADO)

	def _al_fallar(self, peticion: int, error: BaseException) -> None:
		if not self or peticion != self._peticion:
			return
		from app.core.tareas import TareaCancelada

		self._tarea = None
		if isinstance(error, TareaCancelada):
			texto = _("Comparación cancelada")
		else:
			texto = getattr(error, "mensaje", None) or str(error)
			if not isinstance(error, base.ErrorArchivos):
				log.error("Falló la comparación de carpetas", exc_info=error)
		self.campo_estado.SetValue(texto)
		anuncios.anunciar(texto, anuncios.ESENCIAL)

	def poner_diferencias(self, izquierda, derecha, diferencias: Sequence[Diferencia]) -> None:
		"""Muestra las diferencias con la acción propuesta para la dirección elegida."""
		self._resueltos = (izquierda, derecha)
		self._diferencias = [d.con_accion(Accion.NADA) for d in diferencias]
		self._filas = dc.proponer(self._diferencias, self.direccion, self.eliminar_sobrantes)
		self._mostrar()
		if not self._filas:
			self.campo_estado.SetValue(_("Las carpetas son iguales"))
		else:
			self.campo_estado.SetValue(_("{n} diferencias. {r}").format(n=len(self._filas), r=dc.resumen_acciones(self._filas)))
		self._actualizar_botones()

	# ── Lista ──────────────────────────────────────────────────────────────────

	@property
	def filas(self) -> list[Diferencia]:
		return list(self._filas)

	def _valores(self, fila: Diferencia) -> list[str]:
		return [fila.relativo, dc.describir_lado(fila.izquierda), dc.texto_accion(fila), dc.describir_lado(fila.derecha)]

	def _mostrar(self) -> None:
		acciones = self._filtros[max(0, self.lista_filtro.GetSelection())][1]
		# «Archivo frente a carpeta» también sale entre los conflictos, aunque su acción sea Nada.
		self._visibles = [i for i, f in enumerate(self._filas) if acciones is None or f.accion in acciones
			or (Accion.CONFLICTO in acciones and f.estado == dc.Estado.TIPO_DISTINTO)]
		self.lista.reemplazar_filas([self._valores(self._filas[i]) for i in self._visibles])

	def filas_elegidas(self) -> list[int]:
		"""Índices (en ``filas``) de las seleccionadas o, si no hay, de la del cursor."""
		elegidas = []
		actual = self.lista.GetFirstSelected()
		while actual != wx.NOT_FOUND:
			elegidas.append(actual)
			actual = self.lista.GetNextSelected(actual)
		if not elegidas:
			foco = self.lista.GetFocusedItem()
			if foco != wx.NOT_FOUND:
				elegidas = [foco]
		return [self._visibles[v] for v in elegidas if 0 <= v < len(self._visibles)]

	def cambiar_accion(self, accion: Accion | None, indices: Sequence[int] | None = None) -> int:
		"""Pone ``accion`` (``None`` = borrar en el destino, tecla B) en las filas; devuelve cuántas cambiaron."""
		indices = self.filas_elegidas() if indices is None else list(indices)
		if not indices:
			anuncios.anunciar(_("No hay filas elegidas"), anuncios.RESULTADO)
			return 0
		cambiadas, imposibles = 0, 0
		ultima: Accion | None = None
		for indice in indices:
			fila = self._filas[indice]
			nueva = dc.accion_borrar(fila, self.direccion) if accion is None else accion
			if nueva is None or not dc.accion_posible(fila, nueva):
				imposibles += 1
				continue
			self._filas[indice] = fila.con_accion(nueva)
			ultima = nueva
			cambiadas += 1
			if indice in self._visibles:
				self.lista.actualizar_celda(self._visibles.index(indice), 2, dc.texto_accion(self._filas[indice]))
		if cambiadas == 1 and not imposibles:
			texto = ultima.texto
		elif cambiadas:
			texto = _("{a}: {n} filas").format(a=ultima.texto, n=cambiadas)
		else:
			texto = _("No se puede en esta fila: falta el archivo de ese lado")
		if cambiadas and imposibles:
			texto += ". " + _("{n} no se pudieron cambiar").format(n=imposibles)
		anuncios.anunciar(texto, anuncios.RESULTADO)
		self.campo_estado.SetValue(dc.resumen_acciones(self._filas))
		self._actualizar_botones()
		return cambiadas

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if modificadores == wx.MOD_NONE and tecla in TECLAS_ACCION:
			self.cambiar_accion(TECLAS_ACCION[tecla])
			return
		if modificadores == wx.MOD_NONE and tecla == ord("B"):
			self.cambiar_accion(None)
			return
		evento.Skip()

	@staticmethod
	def _al_caracter_lista(evento: wx.KeyEvent) -> None:
		"""Sin búsqueda por letra nativa: las letras y cifras sueltas no mueven la fila."""
		codigo = evento.GetUnicodeKey()
		if evento.GetModifiers() in (wx.MOD_NONE, wx.MOD_SHIFT) and codigo != wx.WXK_NONE and codigo > 32 and chr(codigo).isalnum():
			return
		evento.Skip()

	def _menu_contextual(self, _evento: wx.ContextMenuEvent) -> None:
		menu = wx.Menu()
		opciones = [
			(_("Copiar a la &derecha (D)"), Accion.COPIAR_DERECHA),
			(_("Copiar a la &izquierda (I)"), Accion.COPIAR_IZQUIERDA),
			(_("&Borrar en el destino (B)"), None),
			(_("&Nada (N)"), Accion.NADA),
		]
		for etiqueta, accion in opciones:
			elemento = menu.Append(wx.ID_ANY, etiqueta)
			self.Bind(wx.EVT_MENU, lambda _e, a=accion: self.cambiar_accion(a), elemento)
		elemento = menu.Append(wx.ID_ANY, _("Comparar co&ntenido"))
		self.Bind(wx.EVT_MENU, lambda _e: self.comparar_contenido(), elemento)
		self.lista.PopupMenu(menu)
		menu.Destroy()

	# ── Botones ────────────────────────────────────────────────────────────────

	def _actualizar_botones(self) -> None:
		self.boton_sincronizar.Enable(any(f.accion not in (Accion.NADA, Accion.CONFLICTO) for f in self._filas))
		self.boton_contenido.Enable(bool(self._filas))

	def comparar_contenido(self) -> bool:
		indices = self.filas_elegidas()
		if not indices or self._resueltos is None:
			anuncios.anunciar(_("No hay filas elegidas"), anuncios.RESULTADO)
			return False
		fila = self._filas[indices[0]]
		if fila.izquierda is None or fila.derecha is None or fila.es_carpeta or fila.estado == dc.Estado.TIPO_DISTINTO:
			anuncios.anunciar(_("Hace falta un archivo en cada lado para compararlos"), anuncios.RESULTADO)
			return False
		from app.ui.ventanas import diferencias

		(prov_i, _ri), (prov_d, _rd) = self._resueltos
		diferencias.abrir(self, (prov_i, fila.izquierda.ruta), (prov_d, fila.derecha.ruta))
		return True

	def preparar_operacion(self) -> OperacionSincronizar | None:
		"""La operación con las acciones de la lista, o ``None`` si no hay nada que hacer."""
		if self._resueltos is None:
			return None
		filas = [f for f in self._filas if f.accion not in (Accion.NADA, Accion.CONFLICTO)]
		if not filas:
			return None
		from app.ui.acciones.archivos import opciones_por_defecto

		try:
			opciones = opciones_por_defecto(self._config)
			papelera = bool(self._config.obtener("general.usar_papelera"))
		except Exception:  # noqa: BLE001 - sin configuración se copia con las opciones de fábrica
			log.warning("No se pudieron leer las opciones de copia; se usan las de fábrica", exc_info=True)
			opciones, papelera = OpcionesCopia(), True
		izquierda, derecha = self._resueltos
		return OperacionSincronizar(izquierda, derecha, filas, opciones, papelera=papelera)

	def sincronizar(self, confirmar: bool = True) -> bool:
		operacion = self.preparar_operacion()
		if operacion is None:
			anuncios.anunciar(_("No hay nada que sincronizar"), anuncios.RESULTADO)
			return False
		borrados = sum(1 for f in operacion.filas if f.accion in (Accion.ELIMINAR_DERECHA, Accion.ELIMINAR_IZQUIERDA))
		if confirmar:
			texto = _("Se hará: {r}. ¿Sincronizar?").format(r=dc.resumen_acciones(operacion.filas))
			if dialogos.confirmar(self, texto, _("Sincronizar"), peligroso=borrados > 0) != wx.ID_YES:
				return False
		self.operacion = operacion
		if self.IsModal():
			self.EndModal(wx.ID_OK)
		else:
			self.SetReturnCode(wx.ID_OK)
		return True

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		# Intro en la lista compara el contenido de la fila en vez de pulsar «Comparar» otra vez.
		if (evento.GetModifiers() == wx.MOD_NONE and evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
				and wx.Window.FindFocus() is self.lista):
			self.comparar_contenido()
			return
		evento.Skip()

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self and self.comparando:
			self._tarea.cancelar("Cerrar")
		evento.Skip()
