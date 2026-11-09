# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Árbol de carpetas cargado bajo demanda (vista Árbol y diálogo del árbol).

Es un ``wx.TreeCtrl`` NATIVO: el lector de pantalla anuncia el nivel, si la
rama está abierta o cerrada y la posición, y la búsqueda tecleando, las
flechas y Num +, Num - y Num * son las de Windows, que la persona ya conoce.

Decisiones:

- **Bajo demanda y en un hilo**: cada nodo se lee al abrirlo
  (``EVT_TREE_ITEM_EXPANDING``) con ``proveedor.listar`` en el
  ``GestorTareas``. Mientras tanto tiene un hijo provisional «Cargando...»,
  que además hace que Windows le ponga el botón de abrir y que el lector
  diga «contraído».
- **Los enlaces no se abren**: un enlace o unión puede apuntar a una carpeta
  superior y el árbol no acabaría nunca. Se muestran (con «(enlace)») pero
  sin hijos.
- **Nodos por clave, no por identificador**: las respuestas del hilo buscan
  su nodo por la clave de la ruta en un diccionario. Un ``TreeItemId`` de un
  nodo ya borrado (refresco, cambio de proveedor) no se usa nunca: tocarlo
  cuelga el programa.
- **Elegir con pausa**: al mover la selección, ``al_elegir`` espera
  ``retardo_ms`` (``wx.CallLater`` que se reinicia) para que recorrer el
  árbol con las flechas no haga leer cada carpeta en el otro panel. Intro
  elige al momento.
- La selección que hace el propio programa (``ir_a``, refrescos) no llama a
  ``al_elegir``: quien sincroniza el árbol con el otro panel no debe recibir
  de vuelta la misma carpeta.
- Las rutas solo se combinan con ``proveedor.unir`` y ``proveedor.padre``.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from dataclasses import dataclass

import wx

from app.core.tareas import GestorTareas, Tarea, TareaCancelada
from app.services import errores
from app.services.ordenacion import clave_natural
from app.services.vfs.base import Proveedor

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class _Nodo:
	"""Datos de un nodo del árbol (los nodos provisionales y de error no tienen)."""

	ruta: str
	clave: str
	es_enlace: bool = False
	cargado: bool = False
	cargando: bool = False
	#: Número de la última lectura pedida; las respuestas con otro número se descartan.
	peticion: int = 0


def _leer_subcarpetas(tarea: Tarea, proveedor: Proveedor, ruta: str) -> list[tuple[str, str, bool]]:
	"""(nombre, ruta, es_enlace) de las subcarpetas de ``ruta``, en orden natural.

	Se queda con las carpetas, incluidas las que son enlace, y sin la fila «..».
	"""
	entradas = proveedor.listar(ruta, tarea.token)
	tarea.comprobar()
	carpetas = [(e.nombre, e.ruta, e.es_enlace) for e in entradas if e.es_carpeta and not e.es_superior]
	carpetas.sort(key=lambda c: clave_natural(c[0]))
	return carpetas


class ArbolCarpetas(wx.Panel):
	"""Etiqueta + árbol de carpetas de un proveedor.

	:param padre: ventana que lo contiene.
	:param nombre: texto de la etiqueta (con letra de acceso, «Ár&bol de carpetas:»).
	:param proveedor: origen de las carpetas.
	:param raiz: carpeta de arriba del árbol; en el disco local, ``""`` muestra
		las unidades como primer nivel.
	:param al_elegir: ``al_elegir(ruta)`` cuando la persona elige una carpeta.
	:param tareas: gestor de tareas (las lecturas van en sus hilos).
	:param retardo_ms: pausa tras mover la selección antes de llamar a ``al_elegir``.
	"""

	def __init__(
		self,
		padre: wx.Window,
		nombre: str,
		proveedor: Proveedor,
		raiz: str,
		al_elegir: Callable[[str], None],
		tareas: GestorTareas,
		retardo_ms: int = 400,
	) -> None:
		super().__init__(padre, name=nombre.replace("&", "").rstrip(":").strip())
		self._proveedor = proveedor
		self._raiz = raiz
		self._al_elegir = al_elegir
		self._tareas = tareas
		self.retardo_ms = max(0, int(retardo_ms))
		self._items: dict[str, wx.TreeItemId] = {}
		self._tareas_en_curso: dict[str, Tarea] = {}
		self._generacion = 0
		self._secuencia = 0
		self._programada = 0  # >0 mientras el programa cambia la selección
		self._llamada: wx.CallLater | None = None
		#: Camino pendiente de ``ir_a`` (de arriba abajo) y su generación.
		self._camino: list[str] = []

		# La etiqueta se crea ANTES que el árbol y con el mismo padre: de ella
		# toma el lector el nombre del árbol.
		self.etiqueta = wx.StaticText(self, label=nombre)
		self.arbol = wx.TreeCtrl(
			self, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT | wx.TR_SINGLE | wx.TR_LINES_AT_ROOT,
			name=self.GetName(),
		)
		ayuda = _(
			"Árbol de carpetas. Flechas arriba y abajo para moverse, derecha o Num + para abrir una rama, "
			"izquierda o Num - para cerrarla, letras para buscar. Tras una pausa, o al pulsar Intro, el otro "
			"panel va a la carpeta elegida."
		)
		self.arbol.SetHelpText(ayuda)
		self.SetHelpText(ayuda)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(4))
		sizer.Add(self.arbol, 1, wx.EXPAND | wx.ALL, self.FromDIP(4))
		self.SetSizer(sizer)

		self.arbol.Bind(wx.EVT_TREE_ITEM_EXPANDING, self._al_expandir)
		self.arbol.Bind(wx.EVT_TREE_SEL_CHANGED, self._al_cambiar_seleccion)
		self.arbol.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._al_activar)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
		self._construir()

	# ── API pública ─────────────────────────────────────────────────────────

	def control_enfocable(self) -> wx.TreeCtrl:
		"""El control al que la ventana lleva el foco con Tab."""
		return self.arbol

	@property
	def proveedor(self) -> Proveedor:
		return self._proveedor

	@property
	def raiz(self) -> str:
		return self._raiz

	def ruta_elegida(self) -> str | None:
		"""Ruta del nodo seleccionado, o ``None`` si no hay (o es un nodo provisional)."""
		item = self.arbol.GetSelection()
		if not item.IsOk():
			return None
		nodo = self._nodo(item)
		return nodo.ruta if nodo is not None else None

	def ir_a(self, ruta: str) -> bool:
		"""Abre las ramas hasta ``ruta`` (leyendo lo que haga falta) y la selecciona.

		Es asíncrono: si una rama no está leída, se lee en un hilo y se sigue al
		llegar la respuesta. Si una carpeta del camino no aparece, se queda en la
		más profunda encontrada. No llama a ``al_elegir``.

		:return: ``False`` si la ruta no está dentro de la raíz del árbol.
		"""
		camino: list[str] = []
		actual: str | None = ruta
		clave_raiz = self._clave(self._raiz) if self._raiz else None
		while actual is not None:
			camino.append(actual)
			if clave_raiz is not None and self._clave(actual) == clave_raiz:
				break
			actual = self._proveedor.padre(actual)
		camino.reverse()
		if not camino or self._buscar_hijo(self.arbol.GetRootItem(), camino[0]) is None:
			log.debug("ir_a: %s no está dentro de la raíz %r del árbol", ruta, self._raiz)
			self._camino = []
			return False
		self._camino = camino
		self._continuar_camino()
		return True

	def refrescar(self, ruta: str | None = None) -> bool:
		"""Vuelve a leer los hijos del nodo de ``ruta`` (``None`` o ``""``: el primer nivel).

		Las ramas que estaban abiertas se vuelven a abrir y la selección se
		conserva si la carpeta sigue existiendo. Devuelve ``False`` si ese nodo
		no está en el árbol.
		"""
		if not ruta:
			seleccion = self.ruta_elegida()
			self._construir()
			if seleccion:
				self.ir_a(seleccion)
			return True
		item = self._items.get(self._clave(ruta))
		if item is None:
			return False
		nodo = self._nodo(item)
		if nodo is None or nodo.es_enlace:
			return False
		if not nodo.cargado and not nodo.cargando:
			return True  # Aún no se había leído: se leerá al abrirlo.
		self._cargar(item, nodo, abiertos=self._ramas_abiertas(item), seleccion=self.ruta_elegida())
		return True

	def cambiar_proveedor(self, proveedor: Proveedor, raiz: str) -> None:
		"""Muestra otro origen (otra unidad, un servidor...) desde cero."""
		self._proveedor = proveedor
		self._raiz = raiz
		self._construir()

	def elegir_ahora(self) -> None:
		"""Llama ya a ``al_elegir`` con la carpeta seleccionada (lo que hace Intro)."""
		self._parar_temporizador()
		ruta = self.ruta_elegida()
		if ruta is not None:
			self._llamar_al_elegir(ruta)

	# ── Construcción ────────────────────────────────────────────────────────

	def _clave(self, ruta: str) -> str:
		"""Clave de comparación de rutas: en local, sin distinguir mayúsculas ni barra final."""
		if self._proveedor.esquema == "local":
			return ruta.rstrip("\\/").casefold()
		return ruta.rstrip("/") or "/"

	def _construir(self) -> None:
		"""Borra todo y pone el primer nivel: las unidades o la raíz."""
		self._generacion += 1
		self._parar_temporizador()
		self._cancelar_todas()
		self._camino = []
		self._items.clear()
		self._programada += 1
		try:
			self.arbol.DeleteAllItems()
			raiz_oculta = self.arbol.AddRoot("")
			if not self._raiz and self._proveedor.esquema == "local":
				self._anadir_unidades(raiz_oculta)
			else:
				texto = self._proveedor.mostrar(self._raiz) if self._raiz else self._proveedor.descripcion()
				item = self._anadir_nodo(raiz_oculta, texto, self._raiz, es_enlace=False)
				self.arbol.Expand(item)
		finally:
			self._programada -= 1

	def _anadir_unidades(self, raiz_oculta: wx.TreeItemId) -> None:
		"""Una rama por unidad («C: Disco local»). ``GetDriveTypeW`` no toca el disco."""
		from app.services.windows import unidades

		try:
			letras = unidades.letras()
		except (AttributeError, OSError):
			log.warning("No se pudieron leer las unidades", exc_info=True)
			letras = []
		for letra in letras:
			raiz_unidad = letra + "\\"
			try:
				tipo = unidades.nombre_tipo(unidades.tipo_de(raiz_unidad))
			except (AttributeError, OSError):
				log.debug("Sin tipo de %s", letra, exc_info=True)
				tipo = ""
			self._anadir_nodo(raiz_oculta, f"{letra} {tipo}".strip(), raiz_unidad, es_enlace=False)

	def _anadir_nodo(self, padre: wx.TreeItemId, texto: str, ruta: str, es_enlace: bool) -> wx.TreeItemId:
		nodo = _Nodo(ruta=ruta, clave=self._clave(ruta), es_enlace=es_enlace)
		item = self.arbol.AppendItem(padre, texto, data=nodo)
		self._items[nodo.clave] = item
		if not es_enlace:
			self.arbol.AppendItem(item, _("Cargando..."))
		return item

	def _nodo(self, item: wx.TreeItemId) -> _Nodo | None:
		if not item.IsOk():
			return None
		datos = self.arbol.GetItemData(item)
		return datos if isinstance(datos, _Nodo) else None

	def _olvidar_descendientes(self, item: wx.TreeItemId) -> None:
		"""Quita del diccionario (y cancela) los nodos que cuelgan de ``item`` antes de borrarlos."""
		hijo, cookie = self.arbol.GetFirstChild(item)
		while hijo.IsOk():
			nodo = self._nodo(hijo)
			if nodo is not None:
				self._olvidar_descendientes(hijo)
				self._items.pop(nodo.clave, None)
				tarea = self._tareas_en_curso.pop(nodo.clave, None)
				if tarea is not None and not tarea.terminada:
					tarea.cancelar()
			hijo, cookie = self.arbol.GetNextChild(item, cookie)

	def _buscar_hijo(self, padre: wx.TreeItemId, ruta: str) -> wx.TreeItemId | None:
		clave = self._clave(ruta)
		hijo, cookie = self.arbol.GetFirstChild(padre)
		while hijo.IsOk():
			nodo = self._nodo(hijo)
			if nodo is not None and nodo.clave == clave:
				return hijo
			hijo, cookie = self.arbol.GetNextChild(padre, cookie)
		return None

	def _ramas_abiertas(self, item: wx.TreeItemId) -> set[str]:
		"""Claves de los descendientes abiertos de ``item`` (para reabrirlos tras refrescar)."""
		abiertas: set[str] = set()
		hijo, cookie = self.arbol.GetFirstChild(item)
		while hijo.IsOk():
			nodo = self._nodo(hijo)
			if nodo is not None and self.arbol.IsExpanded(hijo):
				abiertas.add(nodo.clave)
				abiertas |= self._ramas_abiertas(hijo)
			hijo, cookie = self.arbol.GetNextChild(item, cookie)
		return abiertas

	# ── Carga en el hilo ─────────────────────────────────────────────────────

	def _cargar(self, item: wx.TreeItemId, nodo: _Nodo, abiertos: set[str] | None = None, seleccion: str | None = None) -> None:
		"""Pide al gestor las subcarpetas de ``nodo``; la respuesta llega a ``_al_cargar``."""
		self._secuencia += 1
		nodo.peticion = self._secuencia
		nodo.cargando = True
		anterior = self._tareas_en_curso.pop(nodo.clave, None)
		if anterior is not None and not anterior.terminada:
			anterior.cancelar()
		generacion, clave, peticion = self._generacion, nodo.clave, nodo.peticion

		def terminar(carpetas: list[tuple[str, str, bool]]) -> None:
			self._al_cargar(generacion, clave, peticion, carpetas, None, abiertos or set(), seleccion)

		def fallar(error: BaseException) -> None:
			self._al_cargar(generacion, clave, peticion, None, error, set(), seleccion)

		tarea = self._tareas.enviar(
			_leer_subcarpetas, self._proveedor, nodo.ruta, al_terminar=terminar, al_fallar=fallar, nombre="arbol_carpetas",
		)
		if tarea is not None:
			self._tareas_en_curso[clave] = tarea

	def _al_cargar(
		self,
		generacion: int,
		clave: str,
		peticion: int,
		carpetas: list[tuple[str, str, bool]] | None,
		error: BaseException | None,
		abiertos: set[str],
		seleccion: str | None,
	) -> None:
		"""Pone los hijos leídos (en el hilo de la interfaz) si la respuesta sigue valiendo."""
		if not self or generacion != self._generacion:
			return
		item = self._items.get(clave)
		nodo = self._nodo(item) if item is not None else None
		if nodo is None or nodo.peticion != peticion:
			return
		self._tareas_en_curso.pop(clave, None)
		nodo.cargando = False
		if isinstance(error, TareaCancelada):
			return
		self._programada += 1
		try:
			seleccionado_dentro = self._seleccion_dentro_de(item)
			self._olvidar_descendientes(item)
			self.arbol.DeleteChildren(item)
			if error is not None:
				# Un hijo con el motivo: el lector lo lee al abrir la rama. Se
				# reintenta la próxima vez que se abra.
				nodo.cargado = False
				self.arbol.AppendItem(item, _("No se puede leer: {m}").format(m=errores.mensaje_para_usuario(error)))
			else:
				nodo.cargado = True
				for nombre, ruta, es_enlace in carpetas or []:
					texto = _("{n} (enlace)").format(n=nombre) if es_enlace else nombre
					self._anadir_nodo(item, texto, ruta, es_enlace)
				if not carpetas:
					self.arbol.SetItemHasChildren(item, False)
				for hijo_clave in abiertos:
					hijo = self._items.get(hijo_clave)
					if hijo is not None:
						self.arbol.Expand(hijo)
			if seleccionado_dentro:
				self.arbol.SelectItem(item)
		finally:
			self._programada -= 1
		if self._camino:
			self._continuar_camino()
		elif seleccion:
			# Refresco: se vuelve a la carpeta que estaba seleccionada; si colgaba
			# de una rama que ahora se está releyendo, ``ir_a`` espera a leerla.
			seleccionado = self._items.get(self._clave(seleccion))
			if seleccionado is not None:
				self._seleccionar(seleccionado)
			else:
				self.ir_a(seleccion)

	def _seleccion_dentro_de(self, item: wx.TreeItemId) -> bool:
		"""``True`` si la selección actual cuelga de ``item`` (se borrará al poner los hijos)."""
		actual = self.arbol.GetSelection()
		raiz = self.arbol.GetRootItem()
		while actual.IsOk() and actual != raiz:
			actual = self.arbol.GetItemParent(actual)
			if actual == item:
				return True
		return False

	def _continuar_camino(self) -> None:
		"""Avanza por el camino de ``ir_a`` mientras las ramas estén leídas."""
		padre = self.arbol.GetRootItem()
		ultimo: wx.TreeItemId | None = None
		for indice, ruta in enumerate(self._camino):
			item = self._buscar_hijo(padre, ruta)
			if item is None:
				break
			ultimo = item
			if indice == len(self._camino) - 1:
				break
			nodo = self._nodo(item)
			if nodo is None or nodo.es_enlace:
				break
			if not nodo.cargado:
				if not nodo.cargando:
					self._cargar(item, nodo)
				# Se sigue cuando llegue la respuesta; mientras, se marca lo alcanzado.
				self._seleccionar(item)
				return
			if not self.arbol.IsExpanded(item):
				self._programada += 1
				try:
					self.arbol.Expand(item)
				finally:
					self._programada -= 1
			padre = item
		self._camino = []
		if ultimo is not None:
			self._seleccionar(ultimo)

	def _seleccionar(self, item: wx.TreeItemId) -> None:
		"""Selecciona sin llamar a ``al_elegir`` y sin mover el foco."""
		self._programada += 1
		try:
			self.arbol.SelectItem(item)
			self.arbol.EnsureVisible(item)
		finally:
			self._programada -= 1

	def _cancelar_todas(self) -> None:
		for tarea in self._tareas_en_curso.values():
			if not tarea.terminada:
				tarea.cancelar()
		self._tareas_en_curso.clear()

	# ── Eventos ─────────────────────────────────────────────────────────────

	def _al_expandir(self, evento: wx.TreeEvent) -> None:
		"""Abre una rama: si no está leída, la lee en un hilo con «Cargando...» de hijo."""
		item = evento.GetItem()
		nodo = self._nodo(item)
		if nodo is None or nodo.es_enlace:
			evento.Skip()
			return
		if not nodo.cargado and not nodo.cargando:
			# Si quedó un error de una lectura anterior, vuelve a decir «Cargando...».
			primero, _cookie = self.arbol.GetFirstChild(item)
			if primero.IsOk() and self._nodo(primero) is None:
				self.arbol.SetItemText(primero, _("Cargando..."))
			self._cargar(item, nodo)
		evento.Skip()

	def _al_cambiar_seleccion(self, evento: wx.TreeEvent) -> None:
		"""Programa ``al_elegir`` tras la pausa; la reinicia en cada movimiento."""
		evento.Skip()
		if self._programada:
			return
		if self._nodo(evento.GetItem()) is None:
			return
		if self.retardo_ms <= 0:
			self.elegir_ahora()
			return
		if self._llamada is not None and self._llamada.IsRunning():
			self._llamada.Restart(self.retardo_ms)
		else:
			self._llamada = wx.CallLater(self.retardo_ms, self._al_vencer_pausa)

	def _al_vencer_pausa(self) -> None:
		if not self:
			return
		ruta = self.ruta_elegida()
		if ruta is not None:
			self._llamar_al_elegir(ruta)

	def _al_activar(self, _evento: wx.TreeEvent) -> None:
		"""Intro (o doble clic): elige al momento, sin pausa."""
		self.elegir_ahora()

	def _llamar_al_elegir(self, ruta: str) -> None:
		try:
			self._al_elegir(ruta)
		except Exception:  # noqa: BLE001 - un fallo del destino no debe dejar el árbol inservible
			log.exception("Falló al_elegir con %s", ruta)

	def _parar_temporizador(self) -> None:
		if self._llamada is not None and self._llamada.IsRunning():
			self._llamada.Stop()
		self._llamada = None

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self:
			self._generacion += 1
			self._parar_temporizador()
			self._cancelar_todas()
		evento.Skip()
