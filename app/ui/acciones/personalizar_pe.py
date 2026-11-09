# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes y enganches del bloque PE, personalización avanzada (diseño 2.0, sección 10).

``instalar(ventana)`` (14.9) lo llama la ventana una vez al construirse:
sustituye los servicios ``grabador`` y ``macros``, fija la fuente de las
macros del catálogo, el decorador de filas de las reglas, la barra de
botones, las teclas globales, los espacios de trabajo, las vistas por
carpeta, la paleta (usos) y el arranque con Windows. Todo lo que guarda en
``data/config`` lo vuelve a leer con ``al_restaurar`` (parte
``personalizacion`` o ``macros``, 14.4).

Los manejadores de las órdenes de PE (14.1.2) y ``ejecutar_macro`` (las
órdenes dinámicas ``macro:<nombre>``) también están aquí. Lo que hace falta de
la ventana se pide por el protocolo ``VentanaServicios``; lo poco que no está
en él se usa con ``getattr`` y un respaldo, para no romper con ventanas de prueba.
"""

from __future__ import annotations

import builtins
import logging
import os
import weakref
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

from app.services import alias as servicio_alias
from app.services import eventos, menus_personalizados, perfiles, teclas_globales, vistas_carpeta
from app.services import macros as servicio_macros
from app.services import reglas as servicio_reglas
from app.services import paleta as servicio_paleta
from app.ui import anuncios, ordenes

log = logging.getLogger(__name__)

PARTE_PERSONALIZACION = "personalizacion"
PARTE_MACROS = "macros"
ORDENES_VISTA = ("ordenar_", "orden_inverso", "vista_completa", "vista_breve", "filtro", "quitar_filtro")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def etiqueta(id_orden: str) -> str:
	"""Etiqueta visible de una orden, sin «&» ni puntos suspensivos."""
	orden = ordenes.POR_ID.get(id_orden)
	if orden is None:
		return id_orden
	texto = _(orden.etiqueta).replace("&&", "\x00").replace("&", "").replace("\x00", "&")
	return texto.rstrip(".").strip()


# ── Servicio del bloque ─────────────────────────────────────────────────────


class _AnfitrionMacros:
	"""Adaptador de la ventana para ``servicio_macros.EjecutorMacros`` (protocolo ``AnfitrionMacros``)."""

	def __init__(self, pe: ServicioPE) -> None:
		self._pe = pe

	def ejecutar_orden_futuro(self, id_orden: str, argumento: Any = None) -> Future:
		return self._pe.ventana.ejecutar_orden_futuro(id_orden, argumento=argumento)

	def llamar_mas_tarde(self, ms: int, funcion: Callable[[], None]) -> None:
		self._pe.ventana.llamar_mas_tarde(max(1, int(ms)), funcion)

	def anunciar(self, texto: str, nivel: str, sonido: str = "") -> None:
		self._pe.ventana.anunciar(texto, nivel, sonido=sonido)

	def sonar(self, evento: str) -> None:
		from app.services.sonidos import servicio

		servicio.sonar(evento)

	def obtener(self, clave: str) -> Any:
		return self._pe.config.obtener(clave)

	def suscribir_operaciones(self, al_empezar, al_terminar) -> Callable[[], None]:
		bus = self._pe.bus()
		cancelar_a = bus.suscribir(eventos.AL_EMPEZAR_OPERACION, lambda operacion=None, **_d: al_empezar(operacion))
		cancelar_b = bus.suscribir(eventos.AL_TERMINAR_OPERACION, lambda operacion=None, **_d: al_terminar(operacion))

		def cancelar() -> None:
			cancelar_a()
			cancelar_b()

		return cancelar

	def leyendo(self) -> bool:
		paneles = getattr(self._pe.ventana, "todos_los_paneles", lambda: [])()
		return any(getattr(p, "_leyendo", False) for p in paneles)

	def estado_paneles(self) -> Any:
		"""Carpeta y pestaña de cada lado: cambia cuando una orden de navegación ha llegado a su destino."""
		ventana = self._pe.ventana
		paneles = getattr(ventana, "todos_los_paneles", lambda: [])()
		return tuple((id(p), getattr(p, "ruta", ""), getattr(p, "_peticion", 0)) for p in paneles)

	def etiqueta(self, id_orden: str) -> str:
		return etiqueta(id_orden)


class ServicioPE:
	"""Estado del bloque en la sesión: macros, reglas, vistas, menús, alias, paleta y barra de botones."""

	def __init__(self, ventana: Any) -> None:
		self._ventana = weakref.ref(ventana) if _referenciable(ventana) else (lambda v=ventana: v)
		self.config = ventana.config
		self.macros: list[servicio_macros.Macro] = servicio_macros.cargar()
		self.reglas: list[servicio_reglas.Regla] = servicio_reglas.cargar()
		self.vistas = vistas_carpeta.cargar()
		self.menus = menus_personalizados.cargar()
		self.alias: list[servicio_alias.Alias] = servicio_alias.cargar()
		self.todas = False
		self.barra = None
		self.ejecutor = servicio_macros.EjecutorMacros(_AnfitrionMacros(self), lambda: self.macros)
		self.grabador = servicio_macros.Grabador(self.ejecutor.en_curso)
		self.paleta = servicio_paleta.actual()
		self._suscripciones: list[Callable[[], None]] = []
		self._lectura_puesta: set[int] = set()
		self.personalizador = menus_personalizados.Personalizador(
			lambda: self.menus, self.nivel, lambda: bool(self.config.obtener("vista.menus_por_nivel")), lambda: self.todas,
			ordenes.POR_ID.get, lambda: [m.nombre for m in self.macros if m.menu],
		)

	@property
	def ventana(self) -> Any:
		ventana = self._ventana()
		if ventana is None:
			raise RuntimeError("La ventana principal ya no existe")
		return ventana

	def bus(self) -> Any:
		try:
			return self.ventana.servicio("eventos")
		except (KeyError, AttributeError):
			return eventos.bus()

	def nivel(self) -> str:
		return menus_personalizados.nivel_del_perfil(perfiles.perfil_actual(self.config))

	# Macros -----------------------------------------------------------------

	def fuente_macros(self) -> list[tuple[str, bool, bool]]:
		return [(m.nombre, m.menu, m.paleta) for m in self.macros]

	def guardar_macros(self, lista: list[servicio_macros.Macro], anteriores: dict[str, str] | None = None) -> None:
		"""Guarda las macros, pone sus teclas en ``teclado.personalizadas`` y avisa del cambio de catálogo.

		:param anteriores: nombre nuevo → nombre anterior de las renombradas (para mover su tecla).
		"""
		servicio_macros.guardar(lista)
		self.macros = list(lista)
		personalizadas = dict(self.config.obtener("teclado.personalizadas") or {})
		vigentes = {f"macro:{m.nombre}" for m in lista}
		for id_orden in [k for k in personalizadas if k.startswith("macro:") and k not in vigentes]:
			del personalizadas[id_orden]
		for macro in lista:
			id_orden = f"macro:{macro.nombre}"
			if macro.tecla:
				personalizadas[id_orden] = [macro.tecla]
			else:
				personalizadas.pop(id_orden, None)
		globales = dict(self.config.obtener("teclado.globales") or {})
		for nuevo, viejo in (anteriores or {}).items():
			if f"macro:{viejo}" in globales:
				globales[f"macro:{nuevo}"] = globales.pop(f"macro:{viejo}")
		globales = {k: v for k, v in globales.items() if not k.startswith("macro:") or k in vigentes}
		ordenes.catalogo_cambiado()
		cambios: dict[str, Any] = {}
		if personalizadas != (self.config.obtener("teclado.personalizadas") or {}):
			cambios["teclado.personalizadas"] = personalizadas
		if globales != (self.config.obtener("teclado.globales") or {}):
			cambios["teclado.globales"] = globales
		if cambios:
			self.config.establecer_varias(cambios)

	# Reglas, vistas, menús, alias ---------------------------------------------

	def guardar_reglas(self, lista: list[servicio_reglas.Regla]) -> None:
		servicio_reglas.guardar(lista)
		self.reglas = list(lista)
		self._repintar_listas()

	def guardar_vistas(self, datos: vistas_carpeta.DatosVistas) -> None:
		vistas_carpeta.guardar(datos)
		self.vistas = datos

	def guardar_menus(self, datos: menus_personalizados.DatosMenus) -> None:
		menus_personalizados.guardar(datos)
		self.menus = datos
		self.rehacer_menus()
		self.colocar_barra()

	def guardar_alias(self, lista: list[servicio_alias.Alias]) -> None:
		servicio_alias.guardar(lista)
		self.alias = list(lista)

	def rehacer_menus(self) -> None:
		"""La ventana reconstruye menús, despachador y barras con ``al_cambiar_catalogo``."""
		ordenes.catalogo_cambiado()

	def _repintar_listas(self) -> None:
		for panel in getattr(self.ventana, "todos_los_paneles", lambda: [])():
			lista = getattr(panel, "lista_archivos", None)
			if lista is not None and hasattr(lista, "fijar_decorador_fila"):
				lista.fijar_decorador_fila(getattr(lista, "_decorador", None))
				lista.Refresh()

	def recargar(self, partes=(), **_datos) -> None:
		"""Contrato ``recargar()`` de 14.4: tras restaurar una copia «En el momento»."""
		partes = tuple(partes or ())
		if PARTE_PERSONALIZACION in partes:
			self.reglas = servicio_reglas.cargar()
			self.vistas = vistas_carpeta.cargar()
			self.menus = menus_personalizados.cargar()
			self.alias = servicio_alias.cargar()
			self._repintar_listas()
			self.colocar_barra()
		if PARTE_MACROS in partes:
			self.macros = servicio_macros.cargar()
		if PARTE_PERSONALIZACION in partes or PARTE_MACROS in partes:
			ordenes.catalogo_cambiado()

	# Barra de botones ---------------------------------------------------------

	def colocar_barra(self) -> None:
		ventana = self.ventana
		if not self.config.obtener("vista.barra_botones_visible"):
			if self.barra is not None:
				ventana.colocar_barra_botones(None)
				self.barra = None
			return
		from app.ui.barra_botones import BarraBotones

		elementos = menus_personalizados.botones(self.menus, lambda i: i in ordenes.POR_ID)
		padre = getattr(ventana, "panel", None) or ventana.padre()
		mapa = getattr(ventana, "mapa_teclas", None)
		barra = BarraBotones(padre, elementos, etiqueta, lambda i: _(ordenes.POR_ID[i].ayuda) if i in ordenes.POR_ID else "",
			lambda i: mapa.primera_tecla(i) if mapa is not None else "", lambda i: ventana.ejecutar_orden(i), self.volver_al_panel)
		if self.barra is not None:
			ventana.colocar_barra_botones(None)
		ventana.colocar_barra_botones(barra)
		self.barra = barra

	def volver_al_panel(self) -> None:
		activo = getattr(self.ventana, "activo", None)
		if activo is not None:
			activo.enfocar()

	# Teclas globales ------------------------------------------------------------

	def registrar_teclas_globales(self) -> list[str]:
		"""Libera y vuelve a registrar; devuelve las teclas que Windows rechazó."""
		ventana = self.ventana
		ventana.liberar_teclas_globales()
		if not self.config.obtener("teclado.globales_activas"):
			return []
		rechazadas = []
		validas = teclas_globales.validas(self.config.obtener("teclado.globales") or {}, ordenes.POR_ID.get)
		for id_orden, tecla in validas.items():
			if not ventana.registrar_tecla_global(id_orden, tecla):
				rechazadas.append(tecla)
		if rechazadas:
			from app.services.teclas import nombre_visible

			ventana.anunciar(_("No se pudo registrar como tecla global: {t}. La usa otro programa.").format(
				t=", ".join(nombre_visible(t) for t in rechazadas)), anuncios.ESENCIAL)
		return rechazadas

	# Vistas por carpeta, reglas al llegar el cursor, recordar la vista -------------------

	def al_cambiar_carpeta(self, panel=None, ruta: str = "", **_datos) -> None:
		if panel is None or not hasattr(panel, "aplicar_conjunto"):
			return
		if id(panel) not in self._lectura_puesta and getattr(panel, "conjunto", None) is None:
			# El orden de lectura de la pestaña (o el de por defecto) al abrirla (10.5).
			self._lectura_puesta.add(id(panel))
			try:
				panel.aplicar_lectura(list(getattr(panel, "lectura", []) or []))
			except Exception:  # noqa: BLE001 - un panel de prueba sin lista no debe romper nada
				log.debug("No se pudo aplicar el orden de lectura", exc_info=True)
		conjunto = None
		if self.config.obtener("vista.columnas_por_carpeta") and not _es_lista(panel):
			archivos = [e.nombre for e in panel.entradas() if not e.es_carpeta and not e.es_superior]
			conjunto = vistas_carpeta.elegir(self.vistas, panel.mostrar_ruta(), archivos)
		anterior = getattr(panel, "conjunto", None)
		if conjunto != anterior:
			panel.aplicar_conjunto(conjunto)
			if conjunto is not None:
				anuncios.anunciar(_("Vista {n}").format(n=conjunto.nombre), anuncios.DETALLE)
		if conjunto is None and self.config.obtener("vista.recordar_vista_por_carpeta") and not _es_lista(panel):
			recordada = vistas_carpeta.recordada(self.vistas, panel.mostrar_ruta())
			if recordada:
				self._aplicar_recordada(panel, recordada)

	@staticmethod
	def _aplicar_recordada(panel: Any, recordada: dict) -> None:
		orden = str(recordada.get("orden", ""))
		inverso = bool(recordada.get("inverso", False))
		if orden and (orden != panel.criterio_orden or inverso != panel.orden_inverso):
			panel.aplicar_orden(orden, inverso)
		vista = str(recordada.get("vista", ""))
		if vista and vista != panel.vista:
			panel.aplicar_vista(vista)
		filtro = str(recordada.get("filtro", ""))
		if filtro != (panel.filtro or ""):
			panel.aplicar_filtro(filtro)

	def al_terminar_orden(self, id: str = "", ok: bool = True, **_datos) -> None:
		if not ok or not self.config.obtener("vista.recordar_vista_por_carpeta") or not id.startswith(ORDENES_VISTA):
			return
		panel = getattr(self.ventana, "activo", None)
		if panel is None or _es_lista(panel) or getattr(panel, "conjunto", None) is not None:
			return
		vistas_carpeta.recordar(self.vistas, panel.mostrar_ruta(), panel.criterio_orden, panel.orden_inverso, panel.vista, panel.filtro)
		try:
			vistas_carpeta.guardar(self.vistas)
		except OSError:
			log.exception("No se pudo recordar la vista de la carpeta")

	def al_cambiar_cursor(self, panel=None, entrada=None, **_datos) -> None:
		"""Sonido y anuncio de la regla del elemento al que llega el cursor (10.10)."""
		if entrada is None or panel is None or not self.config.obtener("reglas.activas"):
			return
		lista = getattr(panel, "lista_archivos", None)
		efecto = lista.efecto_de(entrada) if lista is not None and hasattr(lista, "efecto_de") else None
		if efecto is None:
			return
		if efecto.sonido:
			from app.services.sonidos import servicio

			servicio.sonar(efecto.sonido)
		if efecto.anuncio:
			anuncios.anunciar(efecto.anuncio, anuncios.DETALLE, interrumpir=False)

	# Disposición para los espacios de trabajo ------------------------------------

	def capturar_disposicion(self, con_cesta: bool) -> dict:
		ventana = self.ventana
		datos = dict(ventana.datos_sesion()) if hasattr(ventana, "datos_sesion") else {}
		datos.pop("historial_ordenes", None)
		if not con_cesta:
			datos.pop("cesta", None)
		datos["vista"] = {
			"orientacion": self.config.obtener("paneles.orientacion"),
			"salida_visible": bool(getattr(ventana, "_paneles_ocultos", False)),
			"barra_botones_visible": bool(self.config.obtener("vista.barra_botones_visible")),
			"lados_visibles": {lado: bool(ventana.lado(lado).IsShown()) for lado in ("izquierdo", "derecho")}
			if hasattr(ventana, "lado") else {},
		}
		return datos

	def restaurar_disposicion(self, datos: dict, con_cesta: bool) -> None:
		from app.services import sesion

		ventana = self.ventana
		vista = datos.get("vista") or {}
		cambios = {}
		if vista.get("orientacion") in ("vertical", "horizontal") and vista["orientacion"] != self.config.obtener("paneles.orientacion"):
			cambios["paneles.orientacion"] = vista["orientacion"]
		if "barra_botones_visible" in vista and bool(vista["barra_botones_visible"]) != bool(self.config.obtener("vista.barra_botones_visible")):
			cambios["vista.barra_botones_visible"] = bool(vista["barra_botones_visible"])
		if cambios:
			self.config.establecer_varias(cambios)
		for nombre in ("izquierdo", "derecho"):
			lado = ventana.lado(nombre)
			info = (datos.get("lados") or {}).get(nombre) or {}
			pestanas = [sesion.pestana(**p) for p in info.get("pestanas", []) if isinstance(p, dict)] or [sesion.pestana(ruta="")]
			_restaurar_lado(ventana, lado, pestanas, int(info.get("actual", 0) or 0))
			visible = (vista.get("lados_visibles") or {}).get(nombre)
			if visible is not None and bool(visible) != bool(lado.IsShown()):
				ventana.ejecutar_orden(f"mostrar_{nombre}")
		if bool(vista.get("salida_visible")) != bool(getattr(ventana, "_paneles_ocultos", False)) and hasattr(ventana, "alternar_paneles"):
			ventana.alternar_paneles()
		if con_cesta and isinstance(datos.get("cesta"), list) and hasattr(ventana, "cesta"):
			ventana.cesta.vaciar()
			ventana.cesta.anadir([str(r) for r in datos["cesta"]])
		activo = datos.get("activo")
		if activo in ("izquierdo", "derecho"):
			panel = ventana.lado(activo).panel_actual()
			wx_llamar(panel.enfocar)

	def cerrar(self, **_datos) -> None:
		for cancelar in self._suscripciones:
			try:
				cancelar()
			except Exception:  # noqa: BLE001 - al cerrar, cancelar dos veces no importa
				log.debug("No se pudo cancelar una suscripción de PE", exc_info=True)
		self._suscripciones.clear()
		self.paleta.cerrar()
		from app.services import espacios

		espacios.fijar_anfitrion(None, None)


def _referenciable(objeto: Any) -> bool:
	try:
		weakref.ref(objeto)
		return True
	except TypeError:
		return False


def _es_lista(panel: Any) -> bool:
	es_lista = getattr(panel, "es_lista", None)
	return bool(es_lista()) if callable(es_lista) else False


def wx_llamar(funcion: Callable[[], None]) -> None:
	import wx

	wx.CallAfter(funcion)


def _restaurar_lado(ventana: Any, lado: Any, pestanas: list[dict], actual: int) -> None:
	"""Deja un lado con exactamente esas pestañas (la primera reutiliza la actual)."""
	cuaderno = lado.cuaderno
	while cuaderno.GetPageCount() > 1:
		indice = cuaderno.GetPageCount() - 1
		panel = cuaderno.GetPage(indice)
		ventana.soltar_proveedor(panel.proveedor, nuevo=None, panel_que_cierra=panel)
		cuaderno.DeletePage(indice)
	primera = cuaderno.GetPage(0)
	for datos in pestanas[1:]:
		nuevo = lado._anadir(dict(datos), seleccionar=False, despues_de_actual=False)  # noqa: SLF001 - el lado no tiene otra vía para añadir con datos sin navegar
		nuevo.iniciar()
	_aplicar_pestana(primera, pestanas[0])
	cuaderno.SetSelection(max(0, min(actual, cuaderno.GetPageCount() - 1)))


def _aplicar_pestana(panel: Any, datos: dict) -> None:
	panel.bloqueada = False
	if datos.get("columnas"):
		panel.aplicar_columnas(list(datos["columnas"]))
	if hasattr(panel, "marca_anadida"):
		# 2.0.1: quién puso la columna «Marca» viaja con la pestaña (se quita sola si la puso zCommander).
		panel.marca_anadida = bool(datos.get("marca_anadida", False))
	panel.lectura = [str(c) for c in datos.get("lectura", []) or []]
	panel.aplicar_lectura(panel.lectura)
	if datos.get("orden"):
		panel.aplicar_orden(str(datos["orden"]), bool(datos.get("inverso", False)))
	panel.aplicar_filtro(str(datos.get("filtro", "") or ""))
	if datos.get("vista"):
		panel.aplicar_vista(str(datos["vista"]))
	if datos.get("ruta"):
		panel.ir_a_texto(str(datos["ruta"]))
	panel.bloqueada = bool(datos.get("bloqueada", False))


_pe: list[ServicioPE | None] = [None]


def servicio() -> ServicioPE | None:
	"""El servicio de PE de la sesión (``None`` antes de ``instalar``)."""
	return _pe[0]


def _servicio(ctx) -> ServicioPE:
	pe = _pe[0]
	if pe is None or pe._ventana() is not ctx.ventana:  # noqa: SLF001
		pe = ServicioPE(ctx.ventana)
		_pe[0] = pe
	return pe


# ── Enganche de arranque (14.9) ─────────────────────────────────────────────


def instalar(ventana: Any) -> None:
	"""Sustituye ``grabador`` y ``macros``, fija la fuente de macros y engancha lo de PE (14.9)."""
	servicio_paleta.fijar(servicio_paleta.Paleta())  # la de esta carpeta data (se lee una vez y se guarda en diferido)
	pe = ServicioPE(ventana)
	_pe[0] = pe
	ventana.registrar_servicio("grabador", pe.grabador)
	ventana.registrar_servicio("macros", pe.ejecutor)
	ordenes.fijar_fuente_macros(pe.fuente_macros)
	_enganchar_menus(pe)
	ventana.fijar_decorador_fila(servicio_reglas.decorador(lambda: pe.reglas, lambda: bool(pe.config.obtener("reglas.activas"))))
	from app.services import espacios

	espacios.fijar_anfitrion(pe.capturar_disposicion, pe.restaurar_disposicion)
	bus = pe.bus()
	pe._suscripciones += [  # noqa: SLF001
		bus.suscribir(eventos.AL_CAMBIAR_CARPETA, pe.al_cambiar_carpeta),
		bus.suscribir(eventos.AL_CAMBIAR_CURSOR, pe.al_cambiar_cursor),
		bus.suscribir(eventos.AL_TERMINAR_ORDEN, pe.al_terminar_orden),
		bus.suscribir(eventos.AL_TERMINAR_ORDEN, pe.paleta.al_terminar_orden),
		bus.suscribir(eventos.AL_RESTAURAR, pe.recargar),
		bus.suscribir(eventos.AL_CERRAR, pe.cerrar),
		pe.config.suscribir(lambda clave, anterior, nuevo: _al_cambiar_config(pe, clave)),
	]
	pe.colocar_barra()
	pe.registrar_teclas_globales()
	ventana.llamar_mas_tarde(1500, lambda: _comprobar_arranque_windows(pe))


def _enganchar_menus(pe: ServicioPE) -> None:
	"""Menús y barra de teclas personalizados, con los enganches pedidos a N2 (peticiones-pe.md)."""
	fijar = getattr(ordenes, "fijar_personalizador", None)
	if callable(fijar):
		fijar(pe.personalizador)
	else:
		log.info("ordenes.fijar_personalizador aún no existe: los menús personalizados se aplicarán cuando esté")


def _al_cambiar_config(pe: ServicioPE, clave: str) -> None:
	"""Cambios de preferencias que aplica PE al momento (se pasan al hilo de la interfaz)."""
	def aplicar() -> None:
		if pe._ventana() is None:  # noqa: SLF001
			return
		if clave == "vista.barra_botones_visible":
			pe.colocar_barra()
		elif clave in ("teclado.globales", "teclado.globales_activas"):
			pe.registrar_teclas_globales()
		elif clave == "general.arrancar_con_windows":
			_aplicar_arranque_windows(pe)
		elif clave == "reglas.activas":
			pe._repintar_listas()  # noqa: SLF001
		elif clave == "paneles.lectura":
			for panel in getattr(pe.ventana, "todos_los_paneles", lambda: [])():
				if getattr(panel, "conjunto", None) is None and not getattr(panel, "lectura", None):
					panel.aplicar_lectura([])
		elif clave == "vista.menus_por_nivel" or (clave in _CLAVES_PERFIL and pe.config.obtener("vista.menus_por_nivel")):
			# Con los menús por nivel, cambiar una clave de perfil puede cambiar el nivel actual.
			pe.rehacer_menus()
		if clave.startswith("teclado.") and pe.barra is not None:
			pe.colocar_barra()

	try:
		import wx

		wx.CallAfter(aplicar)
	except Exception:  # noqa: BLE001 - sin wx (pruebas de servicios) se aplica en el acto
		aplicar()


#: Claves que deciden el perfil actual (con los menús por nivel, cambiar una puede cambiar el nivel).
_CLAVES_PERFIL = frozenset(clave for valores in perfiles.PERFILES.values() for clave in valores)


def _aplicar_arranque_windows(pe: ServicioPE) -> None:
	from app.services import arranque_windows

	activo = bool(pe.config.obtener("general.arrancar_con_windows"))
	if not arranque_windows.disponible():
		if activo:
			pe.ventana.anunciar(_("Arrancar con Windows solo funciona en la versión compilada de zCommander"), anuncios.ESENCIAL)
		return
	try:
		arranque_windows.aplicar(activo)
	except OSError as error:
		log.exception("No se pudo cambiar el arranque con Windows")
		pe.ventana.anunciar(_("No se pudo cambiar el arranque con Windows: {e}").format(e=error), anuncios.ESENCIAL)
		return
	pe.ventana.anunciar(_("zCommander arrancará al iniciar sesión en Windows") if activo else
		_("zCommander ya no arrancará al iniciar sesión en Windows"), anuncios.RESULTADO)


def _comprobar_arranque_windows(pe: ServicioPE) -> None:
	"""Si el valor de ``Run`` apunta a otra carpeta (la portable se movió), se pregunta si se corrige (10.17)."""
	from app.services import arranque_windows

	try:
		if pe._ventana() is None or not arranque_windows.disponible() or not pe.config.obtener("general.arrancar_con_windows"):  # noqa: SLF001
			return
		if not arranque_windows.apunta_a_otra_carpeta():
			return
		from app.ui.dialogos import f_comun

		if f_comun.preguntar(pe.ventana.padre(), _("zCommander arranca con Windows desde otra carpeta (la carpeta portable se movió). "
				"¿Corregirlo para que arranque desde esta?"), _("Arrancar con Windows")):
			arranque_windows.activar()
	except Exception:  # noqa: BLE001 - la comprobación nunca impide usar la aplicación
		log.exception("Falló la comprobación del arranque con Windows")


# ── Línea de órdenes: alias (enganche pedido en peticiones-pe.md) ───────────


def expandir_linea(ventana: Any, texto: str) -> tuple[str, dict[str, str] | None]:
	"""Expande un alias de la línea de órdenes: (orden, entorno). Sin alias, (texto, None).

	La ventana lo llama en ``ejecutar_linea`` antes de reconocer ``zc`` (petición a N2).
	"""
	pe = _pe[0]
	if pe is None or not ventana.config.obtener("linea.alias_activos"):
		return texto, None
	try:
		expandido = servicio_alias.expandir_linea(texto, pe.alias, valores_de(ventana))
	except ValueError as error:
		ventana.anunciar(_("No se pudo expandir el alias: {e}").format(e=error), anuncios.ESENCIAL)
		return "", None
	if expandido is None:
		return texto, None
	return expandido.orden, (None if expandido.interna else expandido.entorno)


def valores_de(ventana: Any):
	"""Valores de las variables de 1.x §8.17 (%P, %M...) con los paneles de la ventana."""
	from app.services import variables

	activo, pasivo = getattr(ventana, "activo", None), getattr(ventana, "pasivo", None)
	if activo is None:
		return variables.Valores()
	cursor = activo.cursor() if hasattr(activo, "cursor") else None
	cursor_otro = pasivo.cursor() if pasivo is not None and hasattr(pasivo, "cursor") else None
	return variables.Valores(
		cursor=cursor.ruta if cursor is not None and not cursor.es_superior and activo.es_local() else "",
		carpeta=activo.ruta_local() or "", otra_carpeta=(pasivo.ruta_local() or "") if pasivo is not None else "",
		cursor_otro=cursor_otro.ruta if cursor_otro is not None and not cursor_otro.es_superior and pasivo.es_local() else "",
		trabajo=[e.ruta for e in activo.elementos_trabajo()] if activo.es_local() else [],
	)


# ── Manejadores de las órdenes de PE (14.1.2) ───────────────────────────────


def macro_grabar(ctx) -> None:
	pe = _servicio(ctx)
	if pe.ventana.servicio("grabador") is not pe.grabador:
		pe.ventana.registrar_servicio("grabador", pe.grabador)
	if not pe.grabador.grabando:
		pe.grabador.empezar()
		anuncios.anunciar(_("Grabando macro. Ejecute las órdenes y vuelva a pulsar Control más Mayúsculas más G para terminar"),
			anuncios.RESULTADO, sonido="macro.grabar")
		_titulo_grabando(ctx.ventana, True)
		return
	pasos = pe.grabador.terminar()
	_titulo_grabando(ctx.ventana, False)
	anuncios.anunciar(_("Grabación terminada: {n} pasos").format(n=len(pasos)), anuncios.RESULTADO, sonido="macro.parar")
	if not pasos:
		return
	from app.ui.dialogos import pe_macros

	pe_macros.guardar_grabada(ctx.ventana, pe, pasos)


def _titulo_grabando(ventana: Any, grabando: bool) -> None:
	from app.core.version import NOMBRE_APLICACION

	if hasattr(ventana, "SetTitle"):
		ventana.SetTitle(f"{NOMBRE_APLICACION} - {_('Grabando macro')}" if grabando else NOMBRE_APLICACION)


def es_grabando(ctx) -> bool:
	pe = _pe[0]
	return bool(pe is not None and pe.grabador.grabando)


def macro_ultima(ctx) -> None:
	pe = _servicio(ctx)
	if not pe.ejecutor.ultima:
		anuncios.anunciar(_("Aún no se ha ejecutado ninguna macro"), anuncios.RESULTADO)
		return
	pe.ejecutor.ejecutar(pe.ejecutor.ultima)


def ejecutar_macro(ctx) -> None:
	"""Manejador de ``macro:<nombre>`` (``param`` = nombre)."""
	_servicio(ctx).ejecutor.ejecutar(ctx.param)


def macros(ctx) -> None:
	from app.ui.dialogos import pe_macros

	pe_macros.mostrar(ctx.ventana, _servicio(ctx), importar=str(ctx.argumento) if ctx.argumento else None)


def columnas_carpeta(ctx) -> None:
	from app.ui.dialogos import pe_vistas

	pe_vistas.mostrar(ctx.ventana, _servicio(ctx), ctx.objetivo)


def orden_lectura(ctx) -> None:
	from app.ui.dialogos import pe_orden_lectura

	pe_orden_lectura.mostrar(ctx.ventana, _servicio(ctx), ctx.activo)


def personalizar_menus(ctx) -> None:
	from app.ui.dialogos import pe_menus

	pe_menus.mostrar(ctx.ventana, _servicio(ctx))


def barra_botones(ctx) -> None:
	visible = not bool(ctx.config.obtener("vista.barra_botones_visible"))
	ctx.config.establecer("vista.barra_botones_visible", visible)
	pe = _servicio(ctx)
	pe.colocar_barra()
	anuncios.anunciar(_("Barra de botones visible") if visible else _("Barra de botones oculta"), anuncios.RESULTADO)


def es_barra_botones(ctx) -> bool:
	return bool(ctx.config.obtener("vista.barra_botones_visible"))


def ir_barra_botones(ctx) -> None:
	pe = _servicio(ctx)
	if pe.barra is None:
		if not ctx.config.obtener("vista.barra_botones_visible"):
			ctx.config.establecer("vista.barra_botones_visible", True)
		pe.colocar_barra()
	if pe.barra is not None and pe.barra.entrar():
		anuncios.anunciar(_("Barra de botones. Izquierda y Derecha recorren los botones; Escape vuelve al panel"),
			anuncios.NORMAL, sonido="barra_botones.entrar")
	else:
		anuncios.anunciar(_("La barra de botones está vacía: llénela en Opciones, Personalización, Personalizar menús y barras"),
			anuncios.RESULTADO)


def esquema_teclas(ctx) -> None:
	from app.ui.dialogos import pe_esquema

	pe_esquema.mostrar(ctx.ventana, ctx.config)


def alias(ctx) -> None:
	from app.ui.dialogos import pe_alias

	pe_alias.mostrar(ctx.ventana, _servicio(ctx))


def linea_autocompletar(ctx) -> None:
	"""Ctrl+Espacio en la línea de órdenes (10.8): completa lo común; la segunda pulsación abre la lista."""
	from app.services import linea_ordenes

	ventana = ctx.ventana
	campo = getattr(ventana, "linea", None)
	if campo is None or not ctx.config.obtener("linea.autocompletar"):
		return
	pe = _servicio(ctx)
	texto = campo.GetValue()
	carpeta = ventana.activo.ruta_local() if hasattr(ventana.activo, "ruta_local") else ""
	ordenes_zc = sorted({o.id for o in ordenes.catalogo()} | {"macro", "ayuda"} | set(_internas()))
	opciones = linea_ordenes.candidatos(texto, carpeta or os.path.expanduser("~"), [a.nombre for a in pe.alias], ordenes_zc)
	if not opciones:
		anuncios.anunciar(_("Sin opciones para completar"), anuncios.RESULTADO)
		return
	anterior = getattr(pe, "_ultimo_completado", None)
	if len(opciones) > 1 and anterior == (texto, tuple(opciones)):
		from app.ui.dialogos import pe_comun

		elegida = pe_comun.elegir_de_lista(ventana, _("Autocompletar"), _("&Opciones:"), opciones)
		if elegida is not None:
			campo.ChangeValue(linea_ordenes.poner_opcion(texto, opciones[elegida]))
		campo.SetFocus()
		campo.SetInsertionPointEnd()
		pe._ultimo_completado = None
		return
	completado = linea_ordenes.completar(texto, opciones)
	campo.ChangeValue(completado.texto)
	campo.SetInsertionPointEnd()
	pe._ultimo_completado = (completado.texto, tuple(opciones))
	if len(opciones) > 1:
		anuncios.anunciar(_("{n} opciones").format(n=len(opciones)), anuncios.RESULTADO)


def _internas() -> list[str]:
	try:
		from app.plugins import registro

		return list(registro.funciones("interna"))
	except Exception:  # noqa: BLE001 - sin registro de complementos no hay internas
		return []


def espacios_trabajo(ctx) -> None:
	from app.ui.dialogos import pe_espacios

	pe_espacios.mostrar(ctx.ventana, _servicio(ctx), abrir=str(ctx.argumento) if ctx.argumento else None)


def espacio_guardar(ctx) -> None:
	from app.ui.dialogos import pe_espacios

	_servicio(ctx)
	pe_espacios.guardar_actual(ctx.ventana)


def reglas(ctx) -> None:
	from app.ui.dialogos import pe_reglas

	pe_reglas.mostrar(ctx.ventana, _servicio(ctx), ctx.activo.cursor() if ctx.activo is not None else None)


def todas_las_ordenes(ctx) -> None:
	pe = _servicio(ctx)
	pe.todas = not pe.todas
	pe.rehacer_menus()
	anuncios.anunciar(_("Los menús muestran todas las órdenes") if pe.todas else _("Los menús muestran las órdenes de su nivel"),
		anuncios.RESULTADO)


def es_todas_las_ordenes(ctx) -> bool:
	pe = _pe[0]
	return bool(pe is not None and pe.todas)


def perfil_guardar_propio(ctx) -> None:
	from app.ui.dialogos import f_perfil

	f_perfil.guardar_propio(ctx.ventana, ctx.config)


def plantillas_archivo(ctx) -> None:
	from app.services import plantillas

	carpeta = plantillas.preparar_carpeta_propia()
	panel = ctx.activo
	panel.ir_a_texto(str(carpeta))
	panel.enfocar()
	anuncios.anunciar(_("Plantillas de archivo nuevo: copie aquí sus plantillas"), anuncios.RESULTADO)


def traer_al_frente(ctx) -> None:
	traer = getattr(ctx.ventana, "traer_al_frente", None)
	if callable(traer):
		traer()

