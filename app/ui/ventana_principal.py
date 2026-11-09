# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana principal de zCommander.

- Menús, barra de teclas, mapa de teclas y paleta salen del catálogo
  (``app/ui/ordenes.py``).
- Despachador de teclas en ``EVT_CHAR_HOOK`` (sección 6.3 del diseño).
- Dos lados con pestañas en un ``wx.SplitterWindow``; zona de salida de las
  órdenes que sustituye a los paneles con «Mostrar u ocultar los paneles».
- Servicios para las órdenes: ``ContextoOrden``, operaciones, decisiones,
  línea de órdenes, salida, sesión, cesta y deshacer.
- Cierre ordenado: operaciones, sesión, configuración, hilos y voz.

2.0 (diseño 2.0, 3.4, 14.8 y 14.9): recibe ``ArranqueInfo``; registra los
servicios nuevos con sus nulos (``registrar_servicio`` los sustituye); inyecta
la interfaz en la API de complementos; llama a ``instalar`` de cada bloque en
el orden fijo de ``INSTALADORES``; menús desde ``ordenes.menus()``
reconstruidos con ``al_cambiar_catalogo``; ``ejecutar_orden`` con argumento,
grabador y eventos del bus; ``ejecutar_orden_futuro``; modo tarea y modo
sesión; y el cierre en el orden exacto de 3.4.
"""

from __future__ import annotations

import builtins
import importlib
import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

import wx

from app.core import paths
from app.core.configuracion import Configuracion
from app.core.tareas import GestorTareas
from app.core.version import NOMBRE_APLICACION
from app.services import eventos, perfiles, sesion
from app.services import servicios_nucleo as nucleo
from app.services.cesta import Cesta
from app.services.historial import HistorialOrdenes
from app.services.operaciones.deshacer import RegistroDeshacer
from app.services.teclas import EDICION, MapaTeclas, nombre_visible
from app.services.vfs import base, resolver
from app.ui import anuncios, ordenes
from app.ui.contexto import ContextoOrden
from app.ui.lado_paneles import LadoPaneles
from app.ui.teclado_eventos import es_campo_de_texto, tecla_de_evento

log = logging.getLogger(__name__)

SC_KEYMENU = 0xF100
WM_SYSCOMMAND = 0x0112


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Hitos que dice la voz con «Cada 25 %» (el 100 % lo dice el resumen final).
HITOS_VOZ = (25, 50, 75)

#: Enganches de arranque de los bloques (14.9): módulo de acciones con ``instalar(ventana)``,
#: en este orden fijo: SO, PL, CO, AC, CS, RD, PE, NV. Cada llamada va protegida.
INSTALADORES: tuple[str, ...] = (
	"sonidos_so", "complementos_pl", "componentes_co", "actualizar_ac", "copia_cs", "red_rd", "personalizar_pe", "nvda_nv",
)
#: Retraso del autocierre del modo tarea tras la última tarea (11.24).
AUTOCIERRE_MS = 2000


class SeguimientoProgreso:
	"""Lo ya avisado de UNA operación: hitos de voz, decenas de tono y decisión.

	El gestor de operaciones solo avisa al lanzar y al terminar, así que el
	progreso se lee con el latido de la ventana (4 veces por segundo). Un
	porcentaje puede saltar varios hitos de golpe (archivos grandes, latido
	lento): entonces se dice solo el más alto, una vez, y los saltados se dan
	por dichos. Así cada hito suena como mucho una vez por operación.
	"""

	def __init__(self) -> None:
		self.hitos_dichos: set[int] = set()
		self.hitos_sonados: set[int] = set()
		self.ultima_decena = 0
		self.decision_avisada = False

	def nuevo_hito(self, porcentaje: int | None) -> int | None:
		"""Hito (25, 50 o 75) que toca decir ahora, o ``None``."""
		if porcentaje is None:
			return None
		alcanzados = [h for h in HITOS_VOZ if porcentaje >= h and h not in self.hitos_dichos]
		if not alcanzados:
			return None
		self.hitos_dichos.update(alcanzados)
		return max(alcanzados)

	def nuevo_hito_sonoro(self, porcentaje: int | None) -> int | None:
		"""Hito (25, 50 o 75) para ``op.progreso`` con «cada 25 %», o ``None`` (precisión 5 de la ronda 4)."""
		if porcentaje is None:
			return None
		alcanzados = [h for h in HITOS_VOZ if porcentaje >= h and h not in self.hitos_sonados]
		if not alcanzados:
			return None
		self.hitos_sonados.update(alcanzados)
		return max(alcanzados)

	def nueva_decena(self, porcentaje: int | None) -> int | None:
		"""Decena (10 a 90) para el tono de progreso, o ``None`` si no ha subido."""
		if porcentaje is None:
			return None
		decena = min(90, (int(porcentaje) // 10) * 10)
		if decena < 10 or decena <= self.ultima_decena:
			return None
		self.ultima_decena = decena
		return decena


class VentanaPrincipal(wx.Frame):
	"""Marco principal. ``config`` es la configuración ya cargada; ``instancia`` la instancia única (o None).

	:param arranque: lo que pasa ``main.py`` (14.8); sin él, ``ArranqueInfo.nulo()``
		(sin complementos, modo normal y el bus único).
	"""

	def __init__(self, config: Configuracion, instancia=None, *, arranque: nucleo.ArranqueInfo | None = None) -> None:
		super().__init__(None, title=NOMBRE_APLICACION, name="zCommander")
		self.config = config
		self._instancia = instancia
		self.arranque = arranque if arranque is not None else nucleo.ArranqueInfo.nulo()
		self.cargador = self.arranque.cargador
		self.bus = self.arranque.bus
		self.contador_ordenes = 0
		self._usada = False
		self._tareas_en_curso: set[str] = set()
		self._menus_abiertos = 0
		self._decorador_fila = None
		self._barra_botones = None
		self._teclas_globales: dict[int, str] = {}
		self._suscripciones: list[Callable[[], None]] = []
		self.tareas = GestorTareas(max_hilos=6, nombre="tareas")
		from app.ui.decisiones import GestorDecisiones

		self.decisiones = GestorDecisiones(self)
		from app.services.operaciones.gestor import GestorOperaciones

		self.operaciones = GestorOperaciones(self.decisiones, int(config.obtener("operaciones.max_paralelas")))
		self.operaciones.suscribir(self._al_cambiar_operacion)
		from app.ui import sonidos

		sonidos.iniciar(config)
		self._servicios_2 = self._servicios_nulos()
		self._seguimientos: dict[int, SeguimientoProgreso] = {}
		self.deshacer = RegistroDeshacer()
		self._datos_sesion = sesion.cargar() if config.obtener("general.restaurar_sesion") else sesion.cargar() | {"lados": sesion.POR_DEFECTO["lados"]}
		self.cesta = Cesta(self._datos_sesion.get("cesta", []))
		self.historial_ordenes = HistorialOrdenes(int(config.obtener("general.tamano_historial_ordenes")), list(self._datos_sesion.get("historial_ordenes", [])))
		self.modo_ayuda_teclado = False
		self._saliendo = False
		self._activo = self._datos_sesion.get("activo", "izquierdo")
		self._elementos_menu: dict[tuple[str, str | None], wx.MenuItem] = {}
		self._ventana_operaciones = None
		self._procesos: list[Any] = []
		self._ultimo_lanzamiento = 0.0
		self._paneles_ocultos = False
		self._mapa = self._construir_mapa()
		self.resolver_servicios()
		self._crear_controles()
		self._crear_menus()
		self.CreateStatusBar(2)
		self.SetStatusWidths([-3, -1])
		self.SetStatusText(_("Listo"))
		self._aplicar_vista()
		self._restaurar_geometria()
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.Bind(wx.EVT_ACTIVATE, self._al_activar)
		self.Bind(wx.EVT_MENU_OPEN, self._al_abrir_menu)
		self.Bind(wx.EVT_MENU_CLOSE, self._al_cerrar_menu)
		self._temporizador = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self._al_latido, self._temporizador)
		self._temporizador.Start(250)
		self._ultimo_guardado = time.monotonic()
		self._modificadores = ""
		config.suscribir(self._al_cambiar_config)
		try:
			from app.ui.acciones import windows_g

			windows_g.instalar(self)
		except Exception:  # noqa: BLE001 - el bloque G no debe impedir arrancar
			log.exception("Falló la instalación del bloque G")
		self._enganchar_2()

	# ── 2.0: servicios, complementos y enganches de los bloques (14.9) ────────

	def _servicios_nulos(self) -> dict[str, Any]:
		from app.services import confirmaciones
		from app.services.sonidos import servicio as servicio_sonidos

		return {
			"eventos": self.bus, "sonidos": servicio_sonidos, "plugins": self.cargador,
			"grabador": nucleo.GrabadorNulo(), "macros": nucleo.MacrosNulo(), "componentes": nucleo.ComponentesNulo(),
			"confirmaciones": confirmaciones,
		}

	def registrar_servicio(self, nombre: str, objeto: Any) -> None:
		"""Sustituye el nulo de uno de los servicios de la 2.0 (14.9); otro nombre es ``ValueError``."""
		if nombre not in nucleo.SERVICIOS_2:
			raise ValueError(_("Servicio desconocido: {n}").format(n=nombre))
		self._servicios_2[nombre] = objeto

	def _enganchar_2(self) -> None:
		"""Interfaz de la API, anunciador de fallos, eventos del bus e ``instalar`` de cada bloque."""
		from app.plugins import api, registro
		from app.plugins import estado as estado_complementos
		from app.ui.interfaz_anfitrion import InterfazVentana

		api.fijar_interfaz(InterfazVentana(self))
		estado_complementos.fijar_anunciador(lambda texto: anuncios.anunciar(texto, anuncios.ESENCIAL, sonido="plugin.fallo"))
		self._suscripciones.append(self.bus.suscribir(eventos.AL_CAMBIAR_CATALOGO, self._al_cambiar_catalogo))
		from app.services import recarga

		self._suscripciones.extend(recarga.suscribir_restauracion(self.bus))
		for panel in self.todos_los_paneles():
			self._enganchar_lista(panel)
		del registro
		for nombre in INSTALADORES:
			try:
				modulo = importlib.import_module(f"app.ui.acciones.{nombre}")
				modulo.instalar(self)
			except Exception:  # noqa: BLE001 - un bloque roto no impide los demás ni arrancar
				log.exception("Falló instalar() del módulo %s", nombre)

	def _enganchar_lista(self, panel) -> None:
		"""Columnas de complementos y decorador de filas en la lista de un panel (19.1)."""
		from app.plugins import registro

		lista = getattr(panel, "lista_archivos", None)
		if lista is None:
			return
		if hasattr(lista, "fijar_columnas_externas"):
			lista.fijar_columnas_externas(registro.valor_columna)
		if hasattr(lista, "fijar_decorador_fila"):
			lista.fijar_decorador_fila(self._decorador_fila)

	def _al_cambiar_catalogo(self) -> None:
		"""Instalar complementos o crear macros cambia el catálogo: despachador, menús y barras se rehacen."""
		if not self or self._saliendo:
			return
		self._mapa = self._construir_mapa()
		self._crear_menus()
		self.barra_teclas.actualizar(forzar=True)

	# Protocolo VentanaServicios (14.9) --------------------------------------

	def anunciar(self, texto: str, nivel: str = anuncios.NORMAL, completo: str = "", sonido: str = "") -> None:
		anuncios.anunciar(texto, nivel, completo, sonido=sonido)

	def llamar_mas_tarde(self, ms: int, funcion: Callable[[], None]) -> None:
		wx.CallLater(int(ms), funcion)

	def esta_libre(self) -> bool:
		"""Sin diálogo modal ni menú abierto ni operación esperando decisión (5.4)."""
		if self._menus_abiertos > 0 or self.decisiones.hay_pendientes():
			return False
		activa = wx.GetActiveWindow()
		return activa is None or activa is self

	def padre(self) -> wx.Window:
		return self

	def fijar_decorador_fila(self, funcion) -> None:
		self._decorador_fila = funcion
		for panel in self.todos_los_paneles():
			lista = getattr(panel, "lista_archivos", None)
			if lista is not None and hasattr(lista, "fijar_decorador_fila"):
				lista.fijar_decorador_fila(funcion)

	def colocar_barra_botones(self, barra) -> None:
		"""Pone la barra de botones bajo los paneles, fuera del orden de tabulación, o la quita (10.6)."""
		sizer = self.panel.GetSizer()
		if self._barra_botones is not None and self._barra_botones is not barra:
			sizer.Detach(self._barra_botones)
			self._barra_botones.Destroy()
			self._barra_botones = None
		if barra is not None and self._barra_botones is None:
			sizer.Insert(2, barra, 0, wx.EXPAND)
			self._barra_botones = barra
		self.panel.Layout()

	def registrar_tecla_global(self, id_orden: str, tecla: str) -> bool:
		"""Registra una tecla global con ``RegisterHotKey`` (10.15); falso si Windows la rechaza."""
		from app.services.teclas import normalizar

		partes = normalizar(tecla).split("+")
		modificadores = 0
		for parte in partes[:-1]:
			modificadores |= {"Ctrl": wx.MOD_CONTROL, "Alt": wx.MOD_ALT, "Shift": wx.MOD_SHIFT, "Win": wx.MOD_WIN}.get(parte, 0)
		codigo = _codigo_virtual(partes[-1])
		if codigo is None:
			return False
		identificador = 0xB000 + len(self._teclas_globales)
		if not self.RegisterHotKey(identificador, modificadores, codigo):
			log.warning("Windows rechazó la tecla global %s para %s", tecla, id_orden)
			return False
		self._teclas_globales[identificador] = id_orden
		self.Bind(wx.EVT_HOTKEY, self._al_tecla_global, id=identificador)
		return True

	def liberar_teclas_globales(self) -> None:
		for identificador in list(self._teclas_globales):
			try:
				self.UnregisterHotKey(identificador)
			except Exception:  # noqa: BLE001 - una tecla ya liberada no impide liberar las demás
				log.debug("No se pudo liberar la tecla global %s", identificador, exc_info=True)
		self._teclas_globales.clear()

	def _al_tecla_global(self, evento) -> None:
		id_orden = self._teclas_globales.get(evento.GetId())
		if not id_orden:
			return
		anuncios.anunciar("", anuncios.DETALLE, sonido="tecla_global.recibida")
		if id_orden == "traer_al_frente":
			self.traer_al_frente()
			return
		if id_orden == "ir_a_carpeta":
			# 2.0 (10.15): «trae al frente y lo abre»; sin esto el cuadro sale con la ventana detrás.
			self.traer_al_frente()
		self.ejecutar_orden(id_orden)

	# ── Servicios para los proveedores ────────────────────────────────────────

	def resolver_servicios(self) -> None:
		secretos = None
		try:
			from app.core.secretos import AlmacenSecretos

			secretos = AlmacenSecretos()
		except Exception:  # noqa: BLE001 - sin secretos se piden las contraseñas cada vez
			log.exception("No se pudo abrir el almacén de secretos")
		self.secretos = secretos
		resolver.fijar_servicios(self.decisiones, secretos, self.config)
		try:
			importlib.import_module("app.services.vfs.registro_proveedores")
		except Exception:  # noqa: BLE001 - un bloque roto no impide arrancar
			log.exception("Falló el registro de proveedores")

	# ── Construcción ────────────────────────────────────────────────────────

	def _crear_controles(self) -> None:
		self.panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.divisor = wx.SplitterWindow(self.panel, style=wx.SP_LIVE_UPDATE | wx.SP_3D)
		self.divisor.SetMinimumPaneSize(120)
		lados = self._datos_sesion["lados"]
		self.izquierdo = LadoPaneles(self.divisor, "izquierdo", self, lados["izquierdo"]["pestanas"], lados["izquierdo"]["actual"])
		self.derecho = LadoPaneles(self.divisor, "derecho", self, lados["derecho"]["pestanas"], lados["derecho"]["actual"])
		self._dividir()
		sizer.Add(self.divisor, 1, wx.EXPAND)
		from app.ui.salida_ordenes import SalidaOrdenes

		self.salida = SalidaOrdenes(self.panel)
		self.salida.Hide()
		sizer.Add(self.salida, 1, wx.EXPAND)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.etiqueta_linea = wx.StaticText(self.panel, label=_("Línea de órdenes:"))
		self.linea = wx.TextCtrl(self.panel, style=wx.TE_PROCESS_ENTER, name=_("Línea de órdenes"))
		self.linea.SetHelpText(_("Escriba una orden de Windows y pulse Intro. Arriba y Abajo recorren el historial; Ctrl+Intro la ejecuta en una consola; Tab vuelve al panel."))
		fila.Add(self.etiqueta_linea, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 4)
		fila.Add(self.linea, 1, wx.EXPAND)
		sizer.Add(fila, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 2)
		from app.ui.barra_teclas import BarraTeclas

		self.barra_teclas = BarraTeclas(self.panel, self)
		sizer.Add(self.barra_teclas, 0, wx.EXPAND)
		self.panel.SetSizer(sizer)

	def _dividir(self) -> None:
		if self.config.obtener("paneles.orientacion") == "horizontal":
			self.divisor.SplitHorizontally(self.izquierdo, self.derecho)
		else:
			self.divisor.SplitVertically(self.izquierdo, self.derecho)
		self.divisor.SetSashGravity(0.5)

	def _aplicar_vista(self) -> None:
		visible = bool(self.config.obtener("vista.linea_ordenes_visible"))
		self.etiqueta_linea.Show(visible)
		self.linea.Show(visible)
		self.barra_teclas.Show(bool(self.config.obtener("vista.barra_teclas_visible")))
		self.GetStatusBar().Show(bool(self.config.obtener("vista.barra_estado_visible")))
		from app.ui import tema

		colores = tema.colores(self.config.obtener("vista.tema"))
		letra = tema.fuente(self.config.obtener("vista.fuente"), int(self.config.obtener("vista.tamano_fuente")))
		for panel in self.todos_los_paneles():
			panel.lista_archivos.SetFont(letra)
			panel.lista_archivos.aplicar_colores(colores)
		self.panel.Layout()

	def _construir_mapa(self) -> MapaTeclas:
		# 2.0 (10.7): teclas de fábrica del catálogo vivo, después el esquema, después las personalizadas.
		mapa = MapaTeclas(ordenes.teclas_por_defecto(self.config.obtener("teclado.esquema")), ordenes.ambitos(),
			self.config.obtener("teclado.personalizadas"), ordenes.fijas())
		for choque in mapa.choques:
			log.warning("Choque de teclas: %s en %s (%s)", choque.tecla, choque.ordenes, choque.motivo)
		return mapa

	@property
	def mapa_teclas(self) -> MapaTeclas:
		return self._mapa

	# ── Menús ────────────────────────────────────────────────────────────────

	def _etiqueta_menu(self, orden: ordenes.Orden, con_tecla: bool = True) -> str:
		etiqueta = _(orden.etiqueta)
		tecla = self._mapa.primera_tecla(orden.id) if con_tecla and self.config.obtener("vista.teclas_en_menus") else ""
		return f"{etiqueta}\t{tecla}" if tecla else etiqueta

	def _crear_menus(self) -> None:
		"""Barra de menús desde ``ordenes.menus()`` (2.0, 14.1.1): núcleo, Complementos, Mis órdenes y anclas."""
		self._elementos_menu.clear()
		self._items_por_menu: dict[int, list[tuple[str, str | None]]] = {}
		barra = wx.MenuBar()
		for titulo, contenido in ordenes.menus():
			lado = None
			if contenido == ordenes.LADO:
				lado = "izquierdo" if "Izquierdo" in titulo else "derecho"
				contenido = ordenes.menu_lado()
			barra.Append(self._menu(contenido, lado), _(titulo))
		anterior = self.GetMenuBar()
		self.SetMenuBar(barra)
		if anterior is not None:
			anterior.Destroy()
		self._actualizar_teclas_lados()

	def _menu(self, elementos, lado: str | None) -> wx.Menu:
		menu = wx.Menu()
		propios: list[tuple[str, str | None]] = []
		self._items_por_menu[id(menu)] = propios
		anterior_separador = True
		for elemento in elementos:
			if elemento is None:
				if not anterior_separador:
					menu.AppendSeparator()
				anterior_separador = True
				continue
			anterior_separador = False
			if isinstance(elemento, tuple):
				titulo, hijos = elemento
				menu.AppendSubMenu(self._menu(hijos, lado), _(titulo))
				continue
			orden = ordenes.POR_ID.get(elemento)
			if orden is None:
				log.warning("El menú nombra una orden que no existe: %s", elemento)
				continue
			propios.append((orden.id, lado))
			tipo = wx.ITEM_CHECK if orden.tipo == "casilla" else wx.ITEM_NORMAL
			# En los menús de lado, las teclas se ponen después según el lado activo.
			item = menu.Append(wx.ID_ANY, self._etiqueta_menu(orden, con_tecla=lado is None), _(orden.ayuda), tipo)
			self.Bind(wx.EVT_MENU, lambda _e, i=orden.id, l=lado: self.ejecutar_orden(i, l, desde_menu=True), item)
			self._elementos_menu[(orden.id, lado)] = item
		return menu

	def _actualizar_teclas_lados(self) -> None:
		"""Solo el menú del lado activo muestra atajos (y los de unidad y ocultar de su lado)."""
		extra = {"izquierdo": {"unidad": "unidad_izquierda", "mostrar_lado": "mostrar_izquierdo"},
			"derecho": {"unidad": "unidad_derecha", "mostrar_lado": "mostrar_derecho"}}
		for (id_orden, lado), item in self._elementos_menu.items():
			if lado is None:
				continue
			orden = ordenes.POR_ID[id_orden]
			tecla = ""
			if lado == self._activo:
				tecla = self._mapa.primera_tecla(extra[lado].get(id_orden, id_orden))
			etiqueta = _(orden.etiqueta) + (f"\t{tecla}" if tecla else "")
			if item.GetItemLabel() != etiqueta:
				item.SetItemLabel(etiqueta)

	def _al_abrir_menu(self, evento: wx.MenuEvent) -> None:
		"""Antes de mostrar un menú, las casillas reflejan el estado actual.

		2.0 (14.2): solo las del menú que se abre (``evento.GetMenu()``); las de un
		complemento sin activar muestran su ``casilla_defecto`` sin activarlo.
		"""
		evento.Skip()
		self._menus_abiertos += 1
		menu = evento.GetMenu()
		if menu is None:
			return
		anuncios.anunciar("", anuncios.DETALLE, sonido="menu.abrir")
		for id_orden, lado in self._items_por_menu.get(id(menu), []):
			item = self._elementos_menu.get((id_orden, lado))
			orden = ordenes.POR_ID.get(id_orden)
			if item is None or orden is None:
				continue
			if orden.tipo == "casilla" and orden.estado:
				try:
					item.Check(bool(self._llamar(orden.estado, self._contexto(orden, lado))))
				except Exception:  # noqa: BLE001 - un estado roto no debe impedir abrir el menú
					log.debug("No se pudo calcular el estado de %s", id_orden, exc_info=True)

	def _al_cerrar_menu(self, evento: wx.MenuEvent) -> None:
		evento.Skip()
		self._menus_abiertos = max(0, self._menus_abiertos - 1)

	# ── Paneles ──────────────────────────────────────────────────────────────

	def lado(self, nombre: str) -> LadoPaneles:
		return self.izquierdo if nombre == "izquierdo" else self.derecho

	@property
	def activo(self):
		return self.lado(self._activo).panel_actual()

	@property
	def pasivo(self):
		return self.lado("derecho" if self._activo == "izquierdo" else "izquierdo").panel_actual()

	def todos_los_paneles(self) -> list:
		return self.izquierdo.paneles() + self.derecho.paneles()

	def panel_opuesto(self, panel):
		return self.derecho.panel_actual() if panel.lado == "izquierdo" else self.izquierdo.panel_actual()

	def panel_creado(self, panel) -> None:
		if hasattr(self, "_servicios_2"):
			self._enganchar_lista(panel)
		try:
			from app.ui.acciones import windows_g

			windows_g.instalar_panel(panel)
		except Exception:  # noqa: BLE001 - el bloque G no debe impedir crear paneles
			log.exception("Falló instalar_panel del bloque G")

	def panel_enfocado(self, panel) -> None:
		if panel.lado != self._activo:
			self._activo = panel.lado
			self.bus.emitir(eventos.AL_ACTIVAR_PANEL, lado=panel.lado)
			self._actualizar_teclas_lados()
			self._actualizar_linea()
			extras = []
			if panel.marcadas():
				extras.append(panel.describir_alcance())
			if panel.filtro:
				extras.append(_("filtro {f}").format(f=panel.filtro))
			if extras:
				anuncios.anunciar(", ".join(extras), anuncios.NORMAL)

	def panel_cambio_carpeta(self, panel) -> None:
		self.bus.emitir(eventos.AL_CAMBIAR_CARPETA, panel=panel, proveedor=panel.proveedor, ruta=panel.ruta)
		if panel is self.activo:
			self._actualizar_linea()
		self._actualizar_espacio()
		self._actualizar_vistas_de(panel)

	def panel_cambio_cursor(self, panel) -> None:
		self._actualizar_vistas_de(panel)
		# al_cambiar_cursor tras 300 ms sin moverse (14.4): no inunda el bus al recorrer la lista.
		anterior = getattr(self, "_llamada_cursor", None)
		if anterior is not None:
			anterior.Stop()
		self._llamada_cursor = wx.CallLater(300, self._emitir_cursor, panel)

	def _emitir_cursor(self, panel) -> None:
		if self and panel and not self._saliendo:
			self.bus.emitir(eventos.AL_CAMBIAR_CURSOR, panel=panel, entrada=panel.cursor())

	def panel_cambio_marcas(self, panel) -> None:
		"""Lo llama el panel al cambiar las marcas (14.4)."""
		self.bus.emitir(eventos.AL_CAMBIAR_MARCAS, panel=panel, cuantas=len(panel.marcadas()))

	def _actualizar_vistas_de(self, panel) -> None:
		"""Información y Vista rápida del OTRO lado siguen al cursor de este panel (con pausa)."""
		otro = self.panel_opuesto(panel)
		if otro.vista not in ("informacion", "rapida"):
			return
		if getattr(self, "_llamada_vista", None) is not None:
			self._llamada_vista.Stop()
		self._llamada_vista = wx.CallLater(300, self._refrescar_vista, otro, panel)

	def _refrescar_vista(self, otro, panel) -> None:
		if not otro or not panel:
			return
		vista = otro.vista_actual()
		if vista is None:
			return
		entrada = panel.cursor()
		try:
			if otro.vista == "informacion":
				vista.mostrar(panel.proveedor, entrada, panel.ruta)
			else:
				vista.mostrar(panel.proveedor, entrada, int(self.config.obtener("vista.vista_rapida_kb")))
		except Exception:  # noqa: BLE001 - una vista que falla no debe tumbar la navegación
			log.exception("Falló la actualización de la vista %s", otro.vista)

	def arbol_eligio(self, panel_arbol, ruta: str) -> None:
		otro = self.panel_opuesto(panel_arbol)
		otro.ir_a(ruta)

	def titulo_pestana(self, panel, texto: str) -> None:
		self.lado(panel.lado).titulo(panel, texto)
		if panel is self.activo:
			self.SetTitle(f"{panel.mostrar_ruta()} - {NOMBRE_APLICACION}")

	def pestana_visible(self, panel) -> bool:
		return self.lado(panel.lado).es_visible(panel)

	def abrir_en_pestana_nueva(self, lado: str, ruta: str, proveedor, cursor: str | None) -> None:
		self.lado(lado).nueva_pestana(ruta=ruta, proveedor=proveedor, cursor=cursor)

	def mostrar_ocultos(self) -> bool:
		return bool(self.config.obtener("paneles.mostrar_ocultos"))

	def soltar_proveedor(self, proveedor: base.Proveedor, nuevo=None, panel_que_cierra=None) -> None:
		"""Cierra un proveedor (comprimido, servidor) si ya no lo usa ningún panel."""
		if proveedor is resolver.proveedor_local() or proveedor is nuevo:
			return
		if nuevo is not None and getattr(nuevo, "contenedor", None) and nuevo.contenedor[0] is proveedor:
			return
		for panel in self.todos_los_paneles():
			if panel is panel_que_cierra:
				continue
			if panel.proveedor is proveedor or (panel.proveedor.contenedor and panel.proveedor.contenedor[0] is proveedor):
				return
		try:
			proveedor.cerrar()
		except Exception:  # noqa: BLE001 - cerrar no debe fallar hacia arriba
			log.debug("Fallo al cerrar el proveedor", exc_info=True)

	def pedir_tipo(self, extension: str, cache: dict) -> None:
		"""Pide al bloque G la descripción de Windows del tipo (si la tiene) y refresca."""
		try:
			from app.services.windows import iconos
		except ImportError:
			return
		descripcion = getattr(iconos, "descripcion_tipo", None)
		if descripcion is None:
			return

		def trabajo(_tarea):
			return descripcion(extension)

		def listo(texto):
			if texto:
				cache[extension] = texto
				for panel in self.todos_los_paneles():
					panel.lista_archivos.Refresh()

		self.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda _e: None, clave_unica=f"tipo:{extension}")

	def consejo(self, proveedor) -> None:
		textos = {
			"zip": _("Comprimido. F5 extrae al otro panel; Retroceso en la raíz sale del comprimido."),
			"tar": _("Comprimido. F5 extrae al otro panel; Retroceso en la raíz sale del comprimido."),
			"7z": _("Comprimido. F5 extrae al otro panel; Retroceso en la raíz sale del comprimido."),
			"ftp": _("Servidor. F5 descarga al otro panel; Comandos, Red, Desconectar vuelve al disco."),
			"sftp": _("Servidor. F5 descarga al otro panel; Comandos, Red, Desconectar vuelve al disco."),
			"resultados": _("Lista de resultados. Las órdenes actúan sobre los archivos reales; Retroceso vuelve a la carpeta."),
		}
		texto = textos.get(proveedor.esquema)
		if texto:
			anuncios.anunciar(texto, anuncios.DETALLE)

	# ── Línea de órdenes y salida ─────────────────────────────────────────────────

	def _actualizar_linea(self) -> None:
		panel = self.activo
		self.etiqueta_linea.SetLabel((panel.ruta_local() or panel.mostrar_ruta()) + ">")
		self.panel.Layout()

	def linea_disponible(self) -> bool:
		return self.activo.es_local()

	def escribir_en_linea(self, texto: str) -> None:
		if not self.linea.IsShown():
			self.etiqueta_linea.Show()
			self.linea.Show()
			self.panel.Layout()
		self.linea.AppendText(texto)
		self.linea.SetFocus()
		self.linea.SetInsertionPointEnd()

	def enfocar_linea(self) -> None:
		self.escribir_en_linea("")

	def poner_en_linea(self, texto: str) -> None:
		self.linea.ChangeValue(texto)
		self.enfocar_linea()

	def ejecutar_linea(self, en_consola: bool = False) -> None:
		texto = self.linea.GetValue().strip()
		if not texto:
			return
		self.historial_ordenes.anadir(texto)
		self.linea.ChangeValue("")
		from app.services import linea_ordenes
		from app.ui.acciones import personalizar_pe

		# 2.0 (10.8): un alias se expande antes de nada; sus argumentos van en el entorno (ZC_1...).
		texto, entorno = personalizar_pe.expandir_linea(self, texto)
		if not texto:
			return
		anuncios.anunciar("", anuncios.DETALLE, sonido="linea.ejecutar")
		zc = linea_ordenes.analizar_zc(texto)
		if zc is not None:
			self._ejecutar_zc(zc)
			return
		cambio = linea_ordenes.analizar(texto)
		panel = self.activo
		if cambio is not None:
			destino = cambio.destino or os.path.expanduser("~")
			if len(destino) == 2 and destino[1] == ":":
				destino = panel.ultima_carpeta(destino) or destino + "\\"
			panel.ir_a_texto(destino, base.Ubicacion(panel.proveedor, panel.ruta))
			panel.enfocar()
			return
		carpeta = panel.ruta_local() or os.path.expanduser("~")
		if en_consola or self.config.obtener("general.ejecutar_siempre_en_consola"):
			linea_ordenes.en_consola(texto, carpeta, entorno, programa=self.config.obtener("general.consola"))
			return
		self.ejecutar_proceso(texto, carpeta, entorno, refrescar=True)

	def _ejecutar_zc(self, zc) -> None:
		"""Órdenes internas ``zc ...`` (2.0, 10.8): sin lanzar ningún proceso."""
		from app.plugins import estado as estado_complementos
		from app.plugins import registro

		if zc.nombre == "macro" and zc.argumentos:
			self.ejecutar_orden(f"macro:{zc.resto}")
			return
		if zc.nombre == "ayuda":
			internas = sorted(registro.funciones("interna"))
			self.salida.escribir(_("Órdenes internas: zc <orden del catálogo> [argumento], zc macro <nombre>, zc ayuda"))
			if internas:
				self.salida.escribir(_("De complementos: {l}").format(l=", ".join(internas)))
			return
		if zc.nombre in ordenes.POR_ID:
			self.ejecutar_orden(zc.nombre, argumento=zc.resto or None)
			return
		interna = registro.funcion("interna", zc.nombre)
		if interna is None:
			anuncios.anunciar(_("Orden interna desconocida: {n}").format(n=zc.nombre), anuncios.ESENCIAL, sonido="linea.error")
			return
		id_complemento, funcion = interna
		self.salida.escribir(f"zc {zc.nombre} {zc.resto}".rstrip())

		def escribir(linea: str) -> None:
			wx.CallAfter(self._linea_salida, linea)

		def trabajo(tarea):
			return estado_complementos.llamar_protegido(id_complemento, funcion, list(zc.argumentos), escribir, tarea)

		def listo(codigo) -> None:
			codigo = 1 if codigo is None else int(codigo)
			mensaje = _("Orden terminada, código {c}").format(c=codigo)
			self.salida.escribir(mensaje)
			anuncios.anunciar(mensaje, anuncios.ESENCIAL, sonido="linea.fin" if codigo == 0 else "linea.error")

		self.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda e: listo(1), nombre=f"zc-{zc.nombre}")

	def ejecutar_proceso(self, orden: str, carpeta: str, entorno: dict | None, refrescar: bool = True) -> None:
		"""Ejecuta con salida capturada en la zona de salida (servicio «linea»)."""
		from app.services import linea_ordenes

		self.salida.escribir(f"{carpeta}> {orden}")
		anuncios.anunciar(_("Ejecutando"), anuncios.RESULTADO)

		def al_linea(texto: str, es_error: bool) -> None:
			wx.CallAfter(self._linea_salida, texto)

		def al_terminar(codigo):
			wx.CallAfter(self._fin_proceso, orden, codigo, refrescar)

		try:
			proceso = linea_ordenes.Proceso(orden, carpeta, entorno, al_linea, al_terminar)
			self._procesos.append(proceso)
		except OSError as error:
			anuncios.anunciar(_("No se pudo ejecutar: {e}").format(e=error), anuncios.ESENCIAL)

	def hay_orden_en_marcha(self) -> bool:
		return any(proceso.en_marcha() for proceso in self._procesos)

	def detener_orden(self) -> bool:
		"""Detiene las órdenes de la línea de órdenes que sigan en marcha.

		Lo piden Escape en el panel (orden «cancelar», si el panel no tenía nada
		que cancelar) y Escape en la línea de órdenes vacía (orden
		«linea_vaciar»). ``taskkill`` puede tardar, así que va en un hilo; el
		anuncio «Orden detenida» lo da ``_fin_proceso`` cuando el proceso acaba.

		:return: ``True`` si había alguna orden que detener.
		"""
		en_marcha = [proceso for proceso in self._procesos if proceso.en_marcha()]
		if not en_marcha:
			return False

		def trabajo(_tarea) -> None:
			for proceso in en_marcha:
				proceso.detener()

		def fallo(error: BaseException) -> None:
			log.warning("No se pudo detener la orden: %s", error)
			anuncios.anunciar(_("No se pudo detener la orden"), anuncios.ESENCIAL)

		if self.tareas.enviar(trabajo, al_fallar=fallo, nombre="detener-orden") is None:
			trabajo(None)
		return True

	def _linea_salida(self, texto: str) -> None:
		if self:
			self.salida.escribir(texto)

	def _fin_proceso(self, orden: str, codigo, refrescar: bool) -> None:
		if not self:
			return
		self._procesos = [p for p in self._procesos if p.en_marcha()]
		if codigo is None:
			mensaje = _("Orden detenida")
		else:
			mensaje = _("Orden terminada, código {c}").format(c=codigo)
		self.salida.escribir(mensaje)
		anuncios.anunciar(mensaje, anuncios.ESENCIAL, sonido="" if codigo is None else ("linea.fin" if codigo == 0 else "linea.error"))
		if refrescar:
			for panel in (self.activo, self.pasivo):
				panel.refrescar()

	def alternar_paneles(self) -> None:
		self._paneles_ocultos = not self._paneles_ocultos
		self.divisor.Show(not self._paneles_ocultos)
		self.salida.Show(self._paneles_ocultos)
		self.panel.Layout()
		if self._paneles_ocultos:
			self.salida.enfocar_final()
			anuncios.anunciar(_("Salida de las órdenes"), anuncios.RESULTADO, sonido="salida.mostrar")
		else:
			self.activo.enfocar()

	# ── Servicios para las órdenes ────────────────────────────────────────────────

	def servicio(self, nombre: str) -> Any:
		if nombre in self._servicios_2:
			return self._servicios_2[nombre]
		if nombre == "sesion":
			return self
		if nombre == "cesta":
			return self.cesta
		if nombre == "deshacer":
			return self.deshacer
		if nombre == "secretos":
			return self.secretos
		if nombre == "decisiones":
			return self.decisiones
		if nombre == "salida":
			return self.salida
		if nombre == "linea":
			return _ServicioLinea(self)
		raise KeyError(nombre)

	def fijar_modo_ayuda_teclado(self, valor: bool) -> None:
		self.modo_ayuda_teclado = bool(valor)
		anuncios.anunciar(
			_("Modo de ayuda de teclado activado: cada tecla dice qué hace. Escape sale.") if valor else _("Modo de ayuda de teclado desactivado"),
			anuncios.RESULTADO, sonido="ayuda_teclado.entrar" if valor else "ayuda_teclado.salir",
		)

	def _contexto(self, orden: ordenes.Orden | None, lado: str | None) -> ContextoOrden:
		ctx = ContextoOrden(self, self.config, self.tareas, self.operaciones, orden=orden.id if orden else "",
			param=orden.param if orden else "", lado_objetivo=lado)
		ctx.activo, ctx.pasivo = self.activo, self.pasivo
		ctx.izquierdo, ctx.derecho = self.izquierdo.panel_actual(), self.derecho.panel_actual()
		return ctx

	@staticmethod
	def _llamar(ruta: str, ctx: ContextoOrden):
		modulo, funcion = ruta.rsplit(".", 1)
		return getattr(importlib.import_module(f"app.ui.acciones.{modulo}"), funcion)(ctx)

	def ejecutar_orden(self, id_orden: str, lado: str | None = None, desde_menu: bool = False, *, argumento: Any = None) -> None:
		"""Ejecuta una orden del catálogo (la firma única de 10.1; ``desde_menu`` solo por nombre en lo nuevo)."""
		self._ejecutar(id_orden, lado, argumento, None)

	def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> Future:
		"""Como ``ejecutar_orden``; el futuro se resuelve cuando su manejador ha terminado (3.4).

		En el acto para las del núcleo y las de complementos activos; al terminar la
		continuación para las de un complemento que se estaba cargando; con falso si
		la orden no estaba disponible, falló o se descartó.
		"""
		futuro: Future = Future()
		self._ejecutar(id_orden, lado, argumento, futuro)
		return futuro

	def _ejecutar(self, id_orden: str, lado: str | None, argumento: Any, futuro: Future | None) -> None:
		def resolver(valor: bool) -> None:
			if futuro is not None and not futuro.done():
				futuro.set_result(valor)

		orden = ordenes.POR_ID.get(id_orden)
		if orden is None:
			log.warning("Orden desconocida: %s", id_orden)
			resolver(False)
			return
		if self._paneles_ocultos and orden.ambito == ordenes.PANEL:
			anuncios.anunciar(_("Los paneles están ocultos: muestre los paneles primero"), anuncios.RESULTADO)
			resolver(False)
			return
		self.contador_ordenes += 1
		if futuro is None:
			# Una orden de la persona (teclado, menú, paleta) cuenta como uso; las que espera
			# una tarea o una macro por su futuro no, para no impedir el autocierre (precisión 6).
			self._usada = True
		# La grabación de macros es por llamada directa y ANTES del manejador (10.1):
		# así el paso queda apuntado antes de que su diálogo llame a anotar_argumento.
		grabador = self._servicios_2["grabador"]
		if getattr(grabador, "grabando", False) and orden.grabable:
			try:
				grabador.anotar(id_orden, argumento)
			except Exception:  # noqa: BLE001 - un grabador roto no impide ejecutar la orden
				log.exception("Falló el grabador de macros con %s", id_orden)
		self.bus.emitir(eventos.AL_EJECUTAR_ORDEN, id=id_orden, argumento=argumento)
		ctx = self._contexto(orden, lado)
		ctx.argumento = argumento
		if futuro is not None:
			ctx.extra["futuro"] = futuro
		ok = True
		try:
			self._llamar(orden.manejador, ctx)
		except Exception:  # noqa: BLE001 - una orden rota no debe tumbar la aplicación
			ok = False
			log.exception("Falló la orden %s", id_orden)
			anuncios.anunciar(_("No se pudo completar «{o}». Los detalles están en el registro.").format(o=_(orden.etiqueta).replace("&", "")),
				anuncios.ESENCIAL, sonido="aviso.error")
		if not ctx.extra.get("futuro_tomado"):
			resolver(ok)
		self.bus.emitir(eventos.AL_TERMINAR_ORDEN, id=id_orden, argumento=argumento, ok=ok)

	def lanzar_operacion(self, operacion, en_cola: bool = False, al_terminar=None, *, orden_origen: str = "") -> None:
		"""Lanza una operación; ``orden_origen`` (2.0, 10.1) dice en qué orden se lanzó (lo usan las macros)."""
		if orden_origen and not getattr(operacion, "orden_origen", ""):
			operacion.orden_origen = orden_origen
		for panel in (self.activo, self.pasivo):
			panel.guardar_marcas()
		self.decisiones.marcar_reciente(operacion)
		self._ultimo_lanzamiento = time.monotonic()
		self.operaciones.lanzar(operacion, en_cola, al_terminar)
		anuncios.anunciar("", anuncios.DETALLE, sonido="op.en_cola" if en_cola else "op.inicio")
		self.bus.emitir(eventos.AL_EMPEZAR_OPERACION, operacion=operacion)
		self._actualizar_estado_operaciones()

	def _al_cambiar_operacion(self, operacion) -> None:
		if not self or self._saliendo:
			return
		self._actualizar_estado_operaciones()
		if not operacion.estado.final:
			if self.config.obtener("accesibilidad.progreso_voz") in ("hitos", "inicio_fin") and operacion.estado.value == "en_cola":
				anuncios.anunciar(_("Empieza: {d}").format(d=operacion.descripcion()), anuncios.NORMAL)
			return
		self._seguimientos.pop(operacion.id, None)
		sonido = {"terminada": "op.fin", "terminada_con_errores": "op.fin_errores", "fallida": "op.fallida",
			"cancelada": "op.cancelada"}.get(operacion.estado.value, "")
		anuncios.anunciar(operacion.resumen(), anuncios.ESENCIAL, sonido=sonido)
		self.bus.emitir(eventos.AL_TERMINAR_OPERACION, operacion=operacion)
		if self.arranque.modo == "tarea":
			wx.CallLater(AUTOCIERRE_MS, self._autocierre)
		if operacion.deshacer is not None:
			self.deshacer.registrar(operacion.deshacer)
		afectadas = operacion.rutas_afectadas()
		for panel in self.todos_los_paneles():
			if any(panel.proveedor.esquema in (esquema, "resultados") and (panel.ruta == ruta or not ruta) for esquema, ruta in afectadas):
				panel.refrescar()
		if operacion.estado.value in ("terminada", "terminada_con_errores"):
			for panel in (self.activo, self.pasivo):
				if panel.marcadas():
					panel.desmarcar_todo()

	def _actualizar_estado_operaciones(self) -> None:
		en_marcha = self.operaciones.en_marcha()
		texto = _("{n} operaciones en curso").format(n=len(en_marcha)) if en_marcha else ""
		if self.decisiones.hay_pendientes():
			texto += _(", decisiones pendientes")
		self.SetStatusText(texto, 1)

	def seguir_progreso(self) -> None:
		"""Hitos de voz («Cada 25 %»), sonido de progreso y sonido de decisión pendiente.

		Lo llama el latido: el gestor solo avisa al lanzar y al terminar. Con las
		dos preferencias desactivadas no se lee nada (no cuesta nada).

		2.0 (4.4 y precisión 5 de la ronda 4): lo decide la ventana: con
		``sonidos.progreso = "cada_10"`` pide ``op.progreso`` con la decena nueva y con
		``"cada_25"`` con los hitos 25, 50 y 75; el servicio solo filtra.
		"""
		from app.services.sonidos import servicio as servicio_sonidos

		por_voz = self.config.obtener("accesibilidad.progreso_voz") == "hitos"
		progreso = self.config.obtener("sonidos.progreso")
		con_tonos = progreso in ("cada_10", "cada_25")
		if not por_voz and not con_tonos and not self.operaciones.en_marcha():
			return
		for operacion in self.operaciones.en_marcha():
			seguimiento = self._seguimientos.setdefault(operacion.id, SeguimientoProgreso())
			if operacion.estado.value == "esperando_decision":
				if not seguimiento.decision_avisada:
					seguimiento.decision_avisada = True
					servicio_sonidos.sonar("op.decision")
				continue
			seguimiento.decision_avisada = False
			porcentaje = operacion.instantanea().porcentaje
			if por_voz:
				hito = seguimiento.nuevo_hito(porcentaje)
				if hito is not None:
					anuncios.anunciar(_("{d}: {p} %").format(d=operacion.descripcion(), p=hito), anuncios.NORMAL)
			if progreso == "cada_10":
				decena = seguimiento.nueva_decena(porcentaje)
				if decena is not None:
					servicio_sonidos.sonar("op.progreso", str(decena))
			elif progreso == "cada_25":
				hito = seguimiento.nuevo_hito_sonoro(porcentaje)
				if hito is not None:
					servicio_sonidos.sonar("op.progreso", str(hito))

	def mostrar_operaciones(self) -> None:
		"""F12: ``VentanaOperaciones.mostrar`` la refresca, arranca su temporizador y pone el foco en la lista."""
		from app.ui.ventanas.operaciones import VentanaOperaciones

		if self._ventana_operaciones is None or not self._ventana_operaciones:
			self._ventana_operaciones = VentanaOperaciones(self, self.operaciones, self.decisiones, self.reintentar_fallidos)
		self._ventana_operaciones.mostrar()

	def reintentar_fallidos(self, operacion) -> None:
		from app.services.operaciones.copiar import OperacionCopiar

		if not getattr(operacion, "fallidos", None):
			return
		nueva = OperacionCopiar(operacion.origen, list(operacion.fallidos), operacion.destino, operacion.carpeta_destino,
			operacion.opciones, operacion.mover)
		self.lanzar_operacion(nueva)

	def _actualizar_espacio(self) -> None:
		panel = self.activo
		def trabajo(_tarea):
			return panel.proveedor.espacio_libre(panel.ruta) if panel.ruta else None

		def listo(espacio):
			if self and espacio:
				from app.services import formato

				self.SetStatusText(_("{l} libres").format(l=formato.tamano_legible(espacio[0])), 1)

		self.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda _e: None, clave_unica=f"espacio:{panel.lado}")

	# ── Despachador de teclas (sección 6.3) ─────────────────────────────────────

	def _ambitos(self, foco: wx.Window | None) -> tuple[tuple[str, ...], str]:
		"""(ámbitos activos, tipo de foco: lista, vista, linea, texto, otro)."""
		if foco is self.linea:
			return ("linea", "global"), "linea"
		for panel in self.todos_los_paneles():
			if foco is panel.lista_archivos:
				return ("panel", "global"), "lista"
			if foco is not None and panel.IsDescendant(foco):
				return ("global",), ("texto" if foco is panel.campo_filtro else "vista")
		if es_campo_de_texto(foco):
			return ("global",), "texto"
		return ("global",), "otro"

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		tecla = tecla_de_evento(evento)
		if not tecla:
			evento.Skip()
			return
		foco = wx.Window.FindFocus()
		ambitos, tipo = self._ambitos(foco)
		# 2. Modo de ayuda de teclado.
		if self.modo_ayuda_teclado:
			if tecla in ("Escape", "Shift+F12"):
				self.fijar_modo_ayuda_teclado(False)
				return
			id_orden = self._mapa.orden_de(tecla, ("panel", "global", "linea"))
			orden = ordenes.POR_ID.get(id_orden or "")
			texto = nombre_visible(tecla) + ": " + (_(orden.etiqueta).replace("&", "") + ". " + _(orden.ayuda) if orden else _("sin orden"))
			anuncios.anunciar(texto, anuncios.RESULTADO)
			return
		# 3. Espacio y Retroceso con búsqueda viva o línea con texto.
		if tipo == "lista" and tecla in ("Space", "Back"):
			panel = self.activo
			if panel.busqueda_viva():
				if tecla == "Space":
					panel.buscar_letra(" ")
				else:
					panel.borrar_letra_busqueda()
				return
			if self.config.obtener("paneles.teclear_en_linea_ordenes") and self.linea.GetValue():
				if tecla == "Space":
					self.escribir_en_linea(" ")
				else:
					self.linea.Remove(self.linea.GetLastPosition() - 1, self.linea.GetLastPosition())
					self.linea.SetFocus()
				return
		# Tab desde una vista o la salida.
		if tipo == "vista" and tecla in ("Tab", "Shift+Tab"):
			self.ejecutar_orden("cambiar_panel")
			return
		# 5. Ámbito «línea» antes que las teclas de edición del campo.
		if tipo == "linea":
			id_orden = self._mapa.orden_de(tecla, ("linea",))
			if id_orden:
				self.ejecutar_orden(id_orden)
				return
		# 6. Teclas de edición o de movimiento en campos, vistas y árboles.
		if tipo in ("linea", "texto", "vista") or isinstance(foco, (wx.TreeCtrl, wx.ComboBox, wx.Choice, wx.ListBox)):
			es_letra = len(tecla) == 1 or (tecla.startswith("Shift+") and len(tecla) == 7)
			if tecla in EDICION or es_letra or tecla in ("Return", "Escape", "Tab", "Shift+Tab", "KP_ADD", "KP_SUBTRACT", "KP_MULTIPLY"):
				evento.DoAllowNextEvent()
				evento.Skip()
				return
		# 7. El mapa de teclas.
		id_orden = self._mapa.orden_de(tecla, ambitos)
		if id_orden:
			self.ejecutar_orden(id_orden)
			return
		# 8. Lo demás, nativo (las letras llegan a la lista en EVT_CHAR ya traducidas).
		evento.Skip()

	def abrir_barra_menus(self) -> None:
		import ctypes

		ctypes.windll.user32.PostMessageW(self.GetHandle(), WM_SYSCOMMAND, SC_KEYMENU, 0)

	# ── Configuración en caliente ───────────────────────────────────────────────

	def _al_cambiar_config(self, clave: str, anterior, _nuevo) -> None:
		wx.CallAfter(self._aplicar_cambio_config, clave, anterior)

	def _aplicar_cambio_config(self, clave: str, anterior=None) -> None:
		if not self:
			return
		if clave == "paneles.columnas":
			self._aplicar_columnas_por_defecto(anterior)
			return
		if clave == "paneles.retardo_arbol_ms":
			for panel in self.todos_los_paneles():
				panel.aplicar_retardo_arbol()
			return
		if clave.startswith("teclado."):
			self._mapa = self._construir_mapa()
			self._crear_menus()
			self.barra_teclas.actualizar(forzar=True)
		elif clave.startswith("vista."):
			self._aplicar_vista()
		elif clave.startswith("accesibilidad.") or clave == "sonidos.sustituir_anuncios":
			self.aplicar_voz()
		elif clave in ("paneles.mostrar_ocultos", "paneles.carpetas_primero", "paneles.orden_natural", "paneles.fila_superior",
				"paneles.formato_fecha", "paneles.formato_tamano"):
			for panel in self.todos_los_paneles():
				panel.reordenar()
		elif clave == "paneles.orientacion":
			self.divisor.Unsplit()
			self.izquierdo.Show()
			self.derecho.Show()
			self._dividir()

	def _aplicar_columnas_por_defecto(self, anterior) -> None:
		"""Las columnas por defecto (Opciones o un perfil) llegan a las pestañas abiertas que las usaban.

		Una pestaña sigue a las columnas por defecto mientras tenga exactamente
		las anteriores; si alguien eligió otras para ella (menú Izquierdo o
		Derecho, «Columnas»), las conserva: aplicar un perfil no debe deshacer
		una elección hecha a propósito para esa pestaña.
		"""
		nuevas = list(self.config.obtener("paneles.columnas") or ["nombre"])
		previas = list(anterior) if isinstance(anterior, (list, tuple)) else None
		for panel in self.todos_los_paneles():
			if previas is None or panel.columnas_carpeta() == previas:
				panel.aplicar_columnas_carpeta(nuevas)

	def aplicar_voz(self) -> None:
		from app.ui import senales_nvda
		from app.ui.accesibilidad import voz

		voz.configurar(retraso_ms=int(self.config.obtener("accesibilidad.retardo_voz_ms")))
		voz.configurar_salida(self.config.obtener("accesibilidad.salida_voz"), bool(self.config.obtener("accesibilidad.sapi_sin_lector")))
		anuncios.configurar(bool(self.config.obtener("accesibilidad.anuncios")), self.config.obtener("accesibilidad.detalle"),
			bool(self.config.obtener("sonidos.sustituir_anuncios")))
		senales_nvda.configurar(bool(self.config.obtener("accesibilidad.silencio_nvda")))

	# ── Arranque, latido, activación ────────────────────────────────────────────────

	def mostrar(self) -> None:
		"""Muestra la ventana y, con ``wx.CallAfter``, los pasos 10 y 11 de 14.8."""
		modo = self.arranque.modo
		if modo in ("tarea", "sesion"):
			# Modo tarea y al iniciar sesión: minimizada, sin quitar el foco y sin anuncios
			# (salvo errores) hasta que la persona la use (11.24, 10.17).
			anuncios.configurar(activos=False)
			self.Iconize(True)
			self.ShowWithoutActivating()
		else:
			self.Show()
			self.Raise()
		from app.ui.accesibilidad import uia

		uia.fijar_ventana(self.GetHandle())
		self.izquierdo.iniciar()
		self.derecho.iniciar()
		if modo == "normal":
			wx.CallAfter(self.activo.enfocar)
		wx.CallAfter(self._tras_mostrar)
		if modo == "normal" and self.config.obtener("accesibilidad.consejos"):
			wx.CallLater(800, anuncios.anunciar, _("Panel {l}. Tab cambia de panel, F1 abre la ayuda.").format(
				l=_("izquierdo") if self._activo == "izquierdo" else _("derecho")), anuncios.DETALLE)

	def _al_latido(self, _evento: wx.TimerEvent) -> None:
		if self._saliendo:
			return
		self.barra_teclas.actualizar()
		try:
			self.seguir_progreso()
		except Exception:  # noqa: BLE001 - el latido no debe romperse por un aviso de progreso
			log.exception("Falló el seguimiento del progreso de las operaciones")
		if self._instancia is not None:
			try:
				from app.core.instancia_unica import ORDEN_ABRIR, ORDEN_TAREA

				for orden in self._instancia.recoger_ordenes():
					if orden.orden == ORDEN_TAREA:
						# Las órdenes «tarea» no traen la ventana al frente ni cuentan como uso (precisión 6).
						for id_tarea in orden.argumentos:
							self.ejecutar_tarea(id_tarea)
						continue
					if orden.orden == ORDEN_ABRIR and orden.argumentos:
						self.abrir_argumentos(orden.argumentos)
					self.traer_al_frente()
			except Exception:  # noqa: BLE001 - el latido no debe romperse
				log.debug("Error con las órdenes de otra instancia", exc_info=True)
		if time.monotonic() - self._ultimo_guardado > 300:
			self._ultimo_guardado = time.monotonic()
			self.guardar_sesion(silencioso=True)

	def traer_al_frente(self) -> None:
		if self.IsIconized():
			self.Iconize(False)
		self.Show()
		self.Raise()
		from app.core.instancia_unica import traer_al_frente

		traer_al_frente(self.GetHandle())

	def abrir_argumentos(self, argumentos: list[str]) -> None:
		for argumento in argumentos[:1]:
			self.izquierdo.panel_actual().ir_a_texto(argumento)

	# ── Pasos 10 y 11 de 14.8, modo tarea y modo sesión ─────────────────────────

	def _tras_mostrar(self) -> None:
		"""Paso 10 (actualizador, complementos al arrancar, bus) y, después, el 11 (avisos)."""
		if not self or self._saliendo:
			return
		from app.services import actualizador

		anuncios.anunciar("", anuncios.DETALLE, sonido="app.arranque")
		try:
			actualizador.al_arrancar(self.arranque.tras_actualizar)
		except Exception:  # noqa: BLE001 - el actualizador nunca impide usar la aplicación
			log.exception("Falló actualizador.al_arrancar")
		try:
			self.cargador.activar_al_arrancar()
		except Exception:  # noqa: BLE001 - un complemento roto no impide usar la aplicación
			log.exception("Falló la activación de los complementos al arrancar")
		self.bus.emitir(eventos.AL_ARRANCAR)
		if self.arranque.modo == "tarea" and self.arranque.tarea:
			self.ejecutar_tarea(self.arranque.tarea)
		wx.CallAfter(self._avisos_arranque)

	def _avisos_arranque(self) -> None:
		"""Paso 11 de 14.8: avisos pendientes, ya con la ventana y los sonidos. En modo tarea, solo errores."""
		if not self or self._saliendo:
			return
		solo_errores = self.arranque.modo == "tarea"
		textos = list(self.arranque.avisos)
		for resultado in (self.arranque.restauracion, self.arranque.integracion):
			mensaje = getattr(resultado, "mensaje", "") if resultado is not None else ""
			if mensaje:
				textos.append(mensaje)
		try:
			textos += list(self.cargador.avisos_arranque())
		except Exception:  # noqa: BLE001
			log.exception("No se pudieron obtener los avisos de los complementos")
		if getattr(self.cargador, "modo_seguro", False):
			anuncios.anunciar(_("Modo seguro: complementos desactivados"), anuncios.ESENCIAL, sonido="app.sin_complementos")
		for texto in textos:
			if not solo_errores:
				anuncios.anunciar(texto, anuncios.ESENCIAL)
		if not solo_errores and not self.config.obtener("sonidos.aviso_inicial_mostrado"):
			# Aviso una sola vez (4.5): los sonidos se activan para todo el mundo en la 2.0.
			anuncios.anunciar(_("Los sonidos están activados; puede desactivarlos en Preferencias, Sonidos, o con Control más F11"),
				anuncios.ESENCIAL)
			self.config.establecer("sonidos.aviso_inicial_mostrado", True)
		if self.arranque.tras_actualizar and not solo_errores:
			self._preguntar_restauracion_pendiente()

	def _preguntar_restauracion_pendiente(self) -> None:
		"""Tras actualizar, la restauración pendiente se pregunta después de ``ok`` (5.2, 7.6)."""
		from app.services.copia import pendiente

		info = pendiente.consultar_pendiente(paths.ruta_datos())
		if info is None:
			return
		from app.ui.accesibilidad import dialogos

		eleccion = dialogos.elegir_opcion(self, _("Hay una restauración pendiente de la copia «{d}». Lo que haya cambiado desde "
			"entonces en esas partes se sustituirá.").format(d=info.descripcion), _("Restauración pendiente"),
			[_("&Aplicarla ahora"), _("&Descartarla"), _("Más &tarde")])
		if eleccion == 0:
			pendiente.decidir_pendiente(paths.ruta_datos(), "aplicar")
		elif eleccion == 1:
			pendiente.decidir_pendiente(paths.ruta_datos(), "descartar")

	def ejecutar_tarea(self, id_tarea: str) -> None:
		"""Una orden «tarea» del buzón o de ``--tarea`` (11.24): la ejecuta ``zc.programador`` por el cargador."""
		self._tareas_en_curso.add(id_tarea)

		def al_terminar(codigo: int) -> None:
			log.info("Tarea programada %s terminada con el código %s", id_tarea, codigo)
			self._tareas_en_curso.discard(id_tarea)
			if self.arranque.modo == "tarea":
				wx.CallLater(AUTOCIERRE_MS, self._autocierre)

		try:
			self.cargador.ejecutar_tarea_programada(id_tarea, al_terminar)
		except Exception:  # noqa: BLE001 - una tarea rota no tumba la ventana
			log.exception("Falló la tarea programada %s", id_tarea)
			al_terminar(2)

	@property
	def usada(self) -> bool:
		"""La persona la ha usado (precisión 6): la ventana recibió el foco sin estar minimizada o la persona ejecutó una orden (sin futuro: teclado, menú, paleta, otra instancia)."""
		return self._usada

	def puede_autocerrarse(self) -> bool:
		"""Modo tarea: sin tareas en curso, sin operaciones en marcha ni en cola, sin órdenes en el buzón y sin usar."""
		if self.arranque.modo != "tarea" or self._usada or self._tareas_en_curso:
			return False
		if self.operaciones.en_marcha() or self.decisiones.hay_pendientes():
			return False
		buzon = getattr(self._instancia, "hay_ordenes_pendientes", None)
		return not (callable(buzon) and buzon())

	def _autocierre(self) -> None:
		"""Cierre del modo tarea: sin ninguna pregunta, aunque ``general.confirmar_salida`` esté activa (11.24)."""
		if not self or self._saliendo or not self.puede_autocerrarse():
			return
		log.info("Modo tarea: no queda trabajo; zCommander se cierra solo")
		self.Close(force=True)

	def _al_activar(self, evento: wx.ActivateEvent) -> None:
		evento.Skip()
		if evento.GetActive() and not self._saliendo:
			if self.arranque.modo in ("tarea", "sesion") and not self._usada and not self.IsIconized():
				# Al recibir el foco, la persona la usa: vuelven los anuncios (10.17, 11.24).
				self._usada = True
				self.aplicar_voz()
			wx.CallAfter(self._tras_activar)

	def _tras_activar(self) -> None:
		if not self:
			return
		self.decisiones.revisar()
		from app.services.vfs import temporales

		temporales.vigilados.revisar()
		for panel in (self.izquierdo.panel_actual(), self.derecho.panel_actual()):
			if panel.es_local() and panel._vigilante is None and panel.ruta:
				panel.refrescar()

	# ── Geometría, sesión, cierre ─────────────────────────────────────────────────

	def _restaurar_geometria(self) -> None:
		ancho, alto = int(self.config.obtener("ventana.ancho")), int(self.config.obtener("ventana.alto"))
		self.SetSize(self.FromDIP(wx.Size(max(600, ancho), max(400, alto))))
		x, y = int(self.config.obtener("ventana.x")), int(self.config.obtener("ventana.y"))
		if x >= -50 and y >= -50 and wx.Display.GetFromPoint(wx.Point(x + 60, y + 15)) != wx.NOT_FOUND:
			self.SetPosition(wx.Point(x, y))
		else:
			self.Centre()
		if self.config.obtener("ventana.maximizada"):
			self.Maximize(True)
		wx.CallAfter(self._poner_division)

	def _poner_division(self) -> None:
		if self and self.divisor.IsSplit():
			tamano = self.divisor.GetClientSize()
			total = tamano.width if self.divisor.GetSplitMode() == wx.SPLIT_VERTICAL else tamano.height
			self.divisor.SetSashPosition(int(total * float(self.config.obtener("ventana.division"))))

	def _guardar_geometria(self) -> None:
		cambios = {"ventana.maximizada": bool(self.IsMaximized())}
		if not self.IsMaximized() and not self.IsIconized():
			rect = self.GetRect()
			tamano = self.ToDIP(rect.GetSize())
			cambios.update({"ventana.x": rect.x, "ventana.y": rect.y, "ventana.ancho": tamano.width, "ventana.alto": tamano.height})
		if self.divisor.IsSplit():
			tamano = self.divisor.GetClientSize()
			total = tamano.width if self.divisor.GetSplitMode() == wx.SPLIT_VERTICAL else tamano.height
			if total > 0:
				cambios["ventana.division"] = max(0.1, min(0.9, self.divisor.GetSashPosition() / total))
		try:
			self.config.establecer_varias(cambios)
		except Exception:  # noqa: BLE001 - un disco lleno no debe impedir cerrar
			log.exception("No se pudo guardar la geometría")

	def datos_sesion(self) -> dict:
		return {
			"version": 1,
			"activo": self._activo,
			"lados": {"izquierdo": self.izquierdo.como_dict(), "derecho": self.derecho.como_dict()},
			"historial_ordenes": list(self.historial_ordenes.elementos),
			"cesta": self.cesta.rutas(),
		}

	def guardar_sesion(self, silencioso: bool = False) -> bool:
		ok = sesion.guardar(self.datos_sesion())
		try:
			self.config.guardar_pendiente()
			self.config.guardar()
		except Exception:  # noqa: BLE001 - se registra; la persona recibe el aviso
			log.exception("No se pudo guardar la configuración")
			ok = False
		if not silencioso:
			anuncios.anunciar(_("Sesión guardada") if ok else _("No se pudo guardar la sesión"), anuncios.RESULTADO)
		return ok

	def salir(self) -> None:
		self.Close()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		"""Cierre en el orden exacto de 3.4 (pasos 1 a 8)."""
		from app.plugins import estado as estado_complementos

		# 1. Desde aquí no empieza ninguna activación ni corre ninguna continuación.
		self.cargador.congelar()
		# 2. Fase con veto: la pregunta de la 1.x y puede_cerrar() de cada complemento activo.
		if evento.CanVeto() and not self._fase_con_veto():
			self.cargador.descongelar()
			evento.Veto()
			return
		# 3. Fase irrevocable de la 1.x.
		self._saliendo = True
		anuncios.anunciar("", anuncios.DETALLE, sonido="app.cierre")
		self._temporizador.Stop()
		self.decisiones.cancelar_todas()
		self.operaciones.apagar(3.0)
		try:
			from app.services import conexiones

			conexiones.cerrar_todas()
		except Exception:  # noqa: BLE001 - cerrar las conexiones nunca impide salir
			log.exception("No se pudieron cerrar las conexiones remotas")
		for proceso in self._procesos:
			proceso.detener()
		self.liberar_teclas_globales()
		self._guardar_geometria()
		self.guardar_sesion(silencioso=True)
		for panel in self.todos_los_paneles():
			panel.dejar_de_vigilar()
			self.soltar_proveedor(panel.proveedor, panel_que_cierra=panel)
		self.tareas.apagar(3.0)
		# 4 y 5. Lo que quedaba en la cola del bus y al_cerrar, antes de desactivar() (para no perder estado).
		self.bus.vaciar()
		self.bus.emitir_sincrono(eventos.AL_CERRAR)
		# 6. desactivar() de cada complemento activo; el tope de 2 s entre todos solo se mide.
		inicio = time.perf_counter()
		for id_complemento, instancia in reversed(self.cargador.activos()):
			antes = time.perf_counter()
			estado_complementos.llamar_protegido(id_complemento, instancia.desactivar)
			if time.perf_counter() - antes > 0.5:
				log.warning("El complemento %s tardó %.1f s en desactivarse", id_complemento, time.perf_counter() - antes)
		if time.perf_counter() - inicio > 2.0:
			log.warning("Los complementos tardaron %.1f s en desactivarse (más de 2 s)", time.perf_counter() - inicio)
		# 7. Bus y cargador cerrados: lo que llegue se descarta y nadie se queda esperando.
		for cancelar in self._suscripciones:
			cancelar()
		self.bus.cerrar()
		self.cargador.cerrar()
		# 8. Interfaz de la API, sonidos y ventanas.
		from app.plugins import api
		from app.ui import sonidos

		api.fijar_interfaz(None)
		estado_complementos.fijar_anunciador(None)
		# Los menús personalizados de PE eran de esta ventana (el bus ya está cerrado: no se rehace nada).
		ordenes.fijar_personalizador(None)
		sonidos.cerrar()
		if self._ventana_operaciones:
			self._ventana_operaciones.Destroy()
		log.info("Ventana principal cerrada.")
		self.Destroy()

	def _fase_con_veto(self) -> bool:
		"""Paso 2 de 3.4: falso si la persona (o un complemento) cancela el cierre. Sin preguntas en el autocierre."""
		from app.plugins import estado as estado_complementos
		from app.ui.accesibilidad import dialogos

		if self.arranque.modo == "tarea" and not self._usada:
			return True
		en_marcha = self.operaciones.en_marcha()
		if en_marcha:
			eleccion = dialogos.elegir_opcion(
				self, _("Hay {n} operaciones en curso.").format(n=len(en_marcha)), _("Salir"),
				[_("&Esperar y salir"), _("Cancelar las operaciones y &salir"), _("&No salir")],
			)
			if eleccion in (None, 2):
				return False
			if eleccion == 0:
				with wx.BusyInfo(_("Esperando a que terminen las operaciones...")):
					while self.operaciones.en_marcha():
						wx.SafeYield(None, True)
						time.sleep(0.05)
		elif self.config.obtener("general.confirmar_salida"):
			if dialogos.confirmar(self, _("¿Salir de {n}?").format(n=NOMBRE_APLICACION), _("Salir")) != wx.ID_YES:
				return False
		for id_complemento, instancia in self.cargador.activos():
			puede = getattr(instancia, "puede_cerrar", None)
			if callable(puede) and estado_complementos.llamar_protegido(id_complemento, puede) is False:
				log.info("El complemento %s canceló el cierre", id_complemento)
				return False
		return True

	# ── Datos para la ayuda y la información de soporte ─────────────────────────────

	@staticmethod
	def carpeta_datos() -> str:
		return str(paths.ruta_datos())

	def perfil_actual(self) -> str:
		return perfiles.perfil_actual(self.config)


_TECLAS_VIRTUALES = {
	"Space": 0x20, "Return": 0x0D, "Tab": 0x09, "Escape": 0x1B, "Back": 0x08, "Delete": 0x2E, "Insert": 0x2D,
	"Home": 0x24, "End": 0x23, "PgUp": 0x21, "PgDn": 0x22, "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
}


def _codigo_virtual(tecla: str) -> int | None:
	"""Código de tecla virtual de Windows para ``RegisterHotKey`` (letras, cifras, F1 a F24 y las de ``_TECLAS_VIRTUALES``)."""
	if len(tecla) == 1 and tecla.isalnum():
		return ord(tecla.upper())
	if tecla.startswith("F") and tecla[1:].isdigit() and 1 <= int(tecla[1:]) <= 24:
		return 0x70 + int(tecla[1:]) - 1
	return _TECLAS_VIRTUALES.get(tecla)


class _ServicioLinea:
	"""``ctx.servicio("linea")``: historial, poner texto y ejecutar órdenes expandidas."""

	def __init__(self, ventana: VentanaPrincipal) -> None:
		self._ventana = ventana

	def historial(self) -> list[str]:
		return list(reversed(self._ventana.historial_ordenes.elementos))

	def poner(self, texto: str) -> None:
		self._ventana.poner_en_linea(texto)

	def ejecutar(self, expansion, consola: bool = False, refrescar: bool = True) -> None:
		"""Ejecuta una ``variables.Expansion`` (menú de usuario, asociaciones)."""
		from app.services import linea_ordenes

		panel = self._ventana.activo
		carpeta = panel.ruta_local() or os.path.expanduser("~")
		if consola or self._ventana.config.obtener("general.ejecutar_siempre_en_consola"):
			linea_ordenes.en_consola(expansion.orden, carpeta, expansion.entorno, self._ventana.config.obtener("general.consola"))
			return
		self._ventana.ejecutar_proceso(expansion.orden, carpeta, expansion.entorno, refrescar)
