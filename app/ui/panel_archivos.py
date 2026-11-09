# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Un panel (una pestaña de un lado): etiqueta, vistas, línea de resumen y filtro rápido.

Implementa ``app.ui.contexto.PanelProtocolo``. Todo se llama desde el hilo de
la interfaz; leer carpetas va en un hilo con número de petición: una petición
nueva cancela la anterior y los resultados viejos se descartan.
"""

from __future__ import annotations

import builtins
import logging
import os
import time
from collections.abc import Callable, Sequence
from typing import Any

import wx

from app.services import errores, formato, ordenacion, seleccion
from app.services.historial import HistorialCarpetas
from app.services.operaciones.copiar import es_temporal_de_copia
from app.services.vfs import base, resolver, rutas
from app.services.vfs.resultados import ProveedorResultados
from app.ui import anuncios
from app.ui.lista_archivos import ListaArchivos, clave

log = logging.getLogger(__name__)

VISTA_LISTA = ("completa", "breve")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def cabecera(columna: str) -> str:
	if ":" in columna:
		# 2.0 (3.5): columna de un complemento; el título sale de su manifiesto, sin activarlo.
		from app.plugins import registro

		return next((c.titulo for c in registro.catalogo_columnas() if c.id == columna), columna.split(":", 1)[1])
	return {
		"nombre": _("Nombre"), "extension": _("Extensión"), "tipo": _("Tipo"), "tamano": _("Tamaño"),
		"modificado": _("Modificado"), "creado": _("Creado"), "atributos": _("Atributos"), "ruta": _("Ruta"),
		"regla": _("Regla"),
	}.get(columna, columna)


def columnas_del_proveedor(proveedor: base.Proveedor, ruta: str) -> list[tuple[str, str]] | None:
	"""2.0 (9.1): columnas propias del proveedor en ``ruta`` (``[(id, título)]``), o ``None`` para las de la pestaña.

	Las da, por ejemplo, la raíz «Red» (Nombre, Tipo, Remoto, Estado). No se guardan en la
	pestaña: al salir de esa carpeta vuelven las de siempre.
	"""
	funcion = getattr(proveedor, "columnas_propias", None)
	if not callable(funcion):
		return None
	try:
		propias = funcion(ruta)
	except Exception:  # noqa: BLE001 - un proveedor roto no deja la lista sin columnas
		log.debug("Fallaron las columnas propias de %s", ruta, exc_info=True)
		return None
	return [(str(c), str(t)) for c, t in propias] if propias else None


def nombre_lado(lado: str) -> str:
	return _("Izquierdo") if lado == "izquierdo" else _("Derecho")


def columnas_con_ruta(columnas: Sequence[str]) -> list[str]:
	"""Columnas de una lista de resultados: las de la pestaña con Ruta detrás de Nombre.

	En la vista plana, la búsqueda y la cesta cada archivo viene de una carpeta
	distinta; sin la columna Ruta, dos «leeme.txt» serían indistinguibles.
	"""
	resultado = [c for c in columnas if c] or ["nombre"]
	if "ruta" not in resultado:
		posicion = resultado.index("nombre") + 1 if "nombre" in resultado else 0
		resultado.insert(posicion, "ruta")
	return resultado


class PanelArchivos(wx.Panel):
	"""Panel de archivos.

	:param ventana: la ``VentanaPrincipal`` (servicios: tareas, config, línea de órdenes...).
	:param datos: pestaña de la sesión (``app.services.sesion.pestana``).
	"""

	def __init__(self, padre: wx.Window, lado: str, ventana: Any, datos: dict) -> None:
		super().__init__(padre)
		self.lado = lado
		self.ventana = ventana
		self.config = ventana.config
		self.tareas = ventana.tareas
		self._proveedor: base.Proveedor = resolver.proveedor_local()
		self._ruta = ""
		self._todas: list[base.Entrada] = []
		self.vista = datos.get("vista") if datos.get("vista") in ("completa", "breve", "informacion", "arbol", "rapida") else "completa"
		self._vista_lista = self.vista if self.vista in VISTA_LISTA else "completa"
		self.filtro = datos.get("filtro", "")
		self.filtro_rapido = ""
		self.criterio_orden = datos.get("orden", "nombre") if datos.get("orden") in ordenacion.CRITERIOS else "nombre"
		self.orden_inverso = bool(datos.get("inverso", False))
		#: 2.0: esquemas de proveedor con ``orden_preferido`` en los que la persona ya eligió otro orden (sesión).
		self._orden_elegido_en: set[str] = set()
		self.bloqueada = bool(datos.get("bloqueada", False))
		#: Columnas de las carpetas (se guardan en la sesión).
		self._columnas_carpeta = list(datos.get("columnas") or self.config.obtener("paneles.columnas"))
		#: 2.0 (10.5): orden de lectura de la pestaña (vacío = el de ``paneles.lectura`` o el de las columnas).
		self.lectura: list[str] = [str(c) for c in datos.get("lectura", []) or []]
		#: 2.0 (10.4): conjunto de vista por carpeta aplicado ahora (``ConjuntoVista``) o ``None``.
		self.conjunto = None
		#: Columnas elegidas estando en una lista de resultados; ``None``: las de carpeta con Ruta.
		self._columnas_lista: list[str] | None = None
		self._anchos = dict(self.config.obtener("paneles.anchos") or {})
		self._historial = HistorialCarpetas.desde_dict(datos.get("historial") or {}, int(self.config.obtener("general.tamano_historial")))
		self._ultimas: dict[str, str] = {}
		self._tamanos: dict[str, int] = {}
		self._tipos: dict[str, str] = {}
		self._listas: list[tuple[base.Proveedor, str, str | None]] = []
		self._peticion = 0
		self._tarea_listado = None
		self._tarea_vinculada: tuple[Any, str] | None = None
		self._leyendo = False
		self._busqueda = ""
		self._busqueda_hasta = 0.0
		self._marcas_guardadas: set[str] = set()
		self._vigilante: wx.FileSystemWatcher | None = None
		self._refresco_pendiente: wx.CallLater | None = None
		self._ultimo_refresco = 0.0
		self._vistas: dict[str, wx.Window] = {}
		#: Títulos de las columnas propias del proveedor que se ven ahora (``columnas_del_proveedor``).
		self._titulos_propios: dict[str, str] = {}
		self._crear_controles()
		self._ruta_inicial = datos.get("ruta", "")

	# ── Construcción ────────────────────────────────────────────────────────────

	def _crear_controles(self) -> None:
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.libro = wx.Simplebook(self)
		pagina = wx.Panel(self.libro)
		caja = wx.BoxSizer(wx.VERTICAL)
		# La etiqueta se crea JUSTO ANTES de la lista y con el mismo padre: el lector
		# toma de ella el nombre de la lista («Izquierdo: C:\\Usuarios»).
		self.etiqueta = wx.StaticText(pagina, label=nombre_lado(self.lado) + ":")
		caja.Add(self.etiqueta, 0, wx.BOTTOM, 2)
		self.lista_archivos = ListaArchivos(
			pagina, nombre_lado(self.lado), self._formatear, self._cabecera,
			al_cambiar_cursor=self._al_cambiar_cursor, al_cambiar_marcas=self._al_cambiar_marcas,
		)
		self.lista_archivos.al_teclear = self.teclear
		self.lista_archivos.obtener_proveedor = lambda: self._proveedor
		self.lista_archivos.SetHelpText(_(
			"Lista de archivos. Flechas para moverse, Intro abre, Insert o Espacio marcan, Tab cambia de panel, "
			"Izquierda y Derecha leen las columnas, F1 abre el manual y Ctrl+E la paleta de órdenes."
		))
		caja.Add(self.lista_archivos, 1, wx.EXPAND)
		pagina.SetSizer(caja)
		self.libro.AddPage(pagina, "lista")
		sizer.Add(self.libro, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
		self._etiqueta_filtro = wx.StaticText(self, label=_("Fi&ltro rápido:"))
		self.campo_filtro = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
		self.campo_filtro.SetHelpText(_("Escriba para quedarse con los elementos que contienen el texto. Intro o Abajo vuelven a la lista; Escape quita el filtro."))
		self.campo_filtro.Bind(wx.EVT_TEXT, self._al_escribir_filtro)
		self.campo_filtro.Bind(wx.EVT_KEY_DOWN, self._al_tecla_filtro)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(self._etiqueta_filtro, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
		fila.Add(self.campo_filtro, 1)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 4)
		self._etiqueta_filtro.Hide()
		self.campo_filtro.Hide()
		self._etiqueta_resumen = wx.StaticText(self, label=_("Resumen:"))
		self._etiqueta_resumen.Hide()
		self.resumen = wx.TextCtrl(self, style=wx.TE_READONLY | wx.BORDER_NONE)
		self.resumen.SetHelpText(_("Resumen de la carpeta y de las marcas. Ctrl+Mayús+S lo dice en cualquier momento."))
		sizer.Add(self.resumen, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
		self.SetSizer(sizer)
		self.lista_archivos.poner_columnas(self._columnas_vista(), self._anchos)
		self.lista_archivos.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.ventana.ejecutar_orden("abrir"))
		self.lista_archivos.Bind(wx.EVT_SET_FOCUS, self._al_recibir_foco)
		self.lista_archivos.Bind(wx.EVT_LIST_COL_END_DRAG, self._al_cambiar_ancho)
		self.lista_archivos.Bind(wx.EVT_CONTEXT_MENU, lambda _e: self.ventana.ejecutar_orden("menu_contextual"))

	def _columnas_vista(self) -> list[str]:
		if self._vista_lista == "breve":
			self._titulos_propios = {}
			return ["nombre"]
		propias = None if self.es_lista() else columnas_del_proveedor(self._proveedor, self._ruta)
		self._titulos_propios = dict(propias or [])
		if propias:
			return [c for c, _t in propias]
		return self.columnas or ["nombre"]

	def _cabecera(self, columna: str) -> str:
		return self._titulos_propios.get(columna) or cabecera(columna)

	@property
	def columnas(self) -> list[str]:
		"""Columnas de la vista completa en lo que se ve ahora.

		En una lista de resultados (vista plana, búsqueda, cesta) son las propias
		de las listas: por defecto, las de carpeta con Ruta. Así «Columnas» del
		menú del lado edita las de lo que se está viendo.
		"""
		if self.es_lista():
			return list(self._columnas_lista) if self._columnas_lista is not None else columnas_con_ruta(self._columnas_carpeta)
		return list(self._columnas_carpeta)

	def columnas_carpeta(self) -> list[str]:
		return list(self._columnas_carpeta)

	def _sincronizar_columnas(self) -> None:
		"""Pone las columnas que tocan si cambiaron (al entrar o salir de una lista de resultados)."""
		deseadas = self._columnas_vista()
		if deseadas != self.lista_archivos.columnas:
			self.lista_archivos.poner_columnas(deseadas, self._anchos)

	# ── Estado básico (protocolo) ───────────────────────────────────────────────

	@property
	def proveedor(self) -> base.Proveedor:
		return self._proveedor

	@property
	def ruta(self) -> str:
		return self._ruta

	def mostrar_ruta(self) -> str:
		return self._proveedor.mostrar(self._ruta)

	def es_local(self) -> bool:
		return self._proveedor.esquema == "local"

	def ruta_local(self) -> str | None:
		if self._proveedor.esquema == "local":
			return self._ruta
		return None

	def lista(self) -> ListaArchivos:
		return self.lista_archivos

	def entradas(self) -> list[base.Entrada]:
		return self.lista_archivos.entradas()

	def cursor(self) -> base.Entrada | None:
		return self.lista_archivos.cursor()

	def marcadas(self) -> list[base.Entrada]:
		return self.lista_archivos.marcadas()

	def elementos_trabajo(self) -> list[base.Entrada]:
		marcadas = self.marcadas()
		if marcadas:
			return marcadas
		entrada = self.cursor()
		return [entrada] if entrada is not None and not entrada.es_superior else []

	def describir_alcance(self) -> str:
		marcadas = self.marcadas()
		if marcadas:
			return formato.plural(len(marcadas), _("{n} marcado"), _("{n} marcados"))
		entrada = self.cursor()
		return entrada.nombre if entrada is not None and not entrada.es_superior else ""

	def cursor_fuera_de_marcas(self) -> bool:
		"""Hay marcas y el cursor no está en ninguna (sección 5.4: se confirma aunque no haya confirmaciones)."""
		entrada = self.cursor()
		return self.lista_archivos.hay_marcas() and entrada is not None and not self.lista_archivos.esta_marcada(
			self.lista_archivos.cursor_indice())

	# ── Navegación ────────────────────────────────────────────────────────────────

	def iniciar(self) -> None:
		"""Primera carga (sesión restaurada o carpeta personal)."""
		texto = self._ruta_inicial or os.path.expanduser("~")

		def fallo(_error: BaseException) -> None:
			if self:
				self.ir_a(self._respaldo(texto), resolver.proveedor_local(), al_terminar=self._tras_inicio, historial=True)

		self.ir_a_texto(texto, al_terminar=self._tras_inicio, al_fallar=fallo)

	def ir_a_texto(
		self,
		texto: str,
		actual: base.Ubicacion | None = None,
		historial: bool = True,
		al_terminar: Callable[[bool], None] | None = None,
		al_fallar: Callable[[BaseException], None] | None = None,
	) -> None:
		"""Resuelve ``texto`` (ruta, comprimido o dirección de red) en un hilo y entra.

		``resolver.abrir_ruta`` puede leer el disco, la red o un comprimido, así que
		nunca se llama desde el hilo de la interfaz (diseño 9.3). Sin ``al_fallar``,
		el error se anuncia.
		"""
		def listo(resultado) -> None:
			if not self:
				return
			proveedor, ruta, cursor = resultado
			self.ir_a(ruta, proveedor, cursor, al_terminar=al_terminar, historial=historial)

		def fallo(error: BaseException) -> None:
			if not self:
				return
			if al_fallar is not None:
				al_fallar(error)
				return
			anuncios.anunciar(getattr(error, "mensaje", None) or str(error), anuncios.ESENCIAL)

		remoto = texto.lower().startswith(("ftp://", "ftps://", "sftp://"))
		resolver_en_hilo(self.tareas, texto, actual, listo, fallo,
			tiempo_maximo=None if remoto else float(self.config.obtener("general.tiempo_unidad_s")))

	def _respaldo(self, texto: str) -> str:
		from app.services import sesion

		return sesion.carpeta_de_respaldo(texto if not texto.startswith(("ftp://", "sftp://", "ftps://")) else "")

	def _tras_inicio(self, ok: bool) -> None:
		if not ok:
			self.ir_a(self._respaldo(self._ruta_inicial), resolver.proveedor_local(), historial=True)
			return
		# 2.0 (10.5): el orden de lectura de la pestaña (o el de ``paneles.lectura``) desde la primera carga.
		self.aplicar_lectura(self.lectura)

	def ir_a(
		self,
		ruta: str,
		proveedor: base.Proveedor | None = None,
		cursor: str | None = None,
		al_terminar: Callable[[bool], None] | None = None,
		historial: bool = True,
		forzar_aqui: bool = False,
	) -> None:
		proveedor = proveedor or self._proveedor
		if self.bloqueada and not forzar_aqui and self._ruta and (proveedor is not self._proveedor or ruta != self._ruta):
			self.ventana.abrir_en_pestana_nueva(self.lado, ruta, proveedor, cursor)
			return
		self._peticion += 1
		peticion = self._peticion
		if self._tarea_listado is not None:
			self._tarea_listado.cancelar("otra carpeta")
		aviso = int(self.config.obtener("general.aviso_lectura_ms"))
		wx.CallLater(max(1, aviso), self._quizas_avisar_lectura, peticion, proveedor.mostrar(ruta))
		self._leyendo = True
		self._tarea_listado = self.tareas.enviar(
			self._listar, proveedor, ruta,
			al_terminar=lambda resultado: self._al_listar(peticion, proveedor, ruta, resultado, cursor, al_terminar, historial),
			al_fallar=lambda error: self._al_fallar_listado(peticion, proveedor, ruta, error, al_terminar),
			nombre=f"listar-{self.lado}",
			tiempo_maximo=self._tiempo_maximo(proveedor),
		)

	def _tiempo_maximo(self, proveedor: base.Proveedor) -> float | None:
		"""Límite de espera de una lectura (``general.tiempo_unidad_s``).

		Sin límite si el servidor remoto aún no está conectado: conectar puede
		preguntar la contraseña o la huella, y el panel no debe decir «no
		responde» con la pregunta abierta. Escape sigue cancelando.
		"""
		conectado = getattr(proveedor, "conectado", None)
		if proveedor.esquema in ("ftp", "sftp") and callable(conectado) and not conectado():
			return None
		return float(self.config.obtener("general.tiempo_unidad_s"))

	@staticmethod
	def _listar(tarea, proveedor: base.Proveedor, ruta: str) -> list[base.Entrada]:
		# Pedir las columnas propias antes de leer: el proveedor de «Red» deja entonces en el nombre
		# solo el nombre (el tipo, el remoto y el estado van en sus columnas).
		columnas_del_proveedor(proveedor, ruta)
		return proveedor.listar(ruta, tarea.token)

	def _quizas_avisar_lectura(self, peticion: int, mostrar: str) -> None:
		if self and self._leyendo and peticion == self._peticion:
			self.ventana.SetStatusText(_("Leyendo {r}...").format(r=mostrar))
			anuncios.anunciar(_("Leyendo"), anuncios.RESULTADO, sonido="nav.leyendo")

	def _al_listar(self, peticion, proveedor, ruta, entradas, cursor, al_terminar, historial) -> None:
		if not self or peticion != self._peticion:
			return
		self._leyendo = False
		anterior_proveedor, anterior_ruta = self._proveedor, self._ruta
		cambio = proveedor is not anterior_proveedor or ruta != anterior_ruta
		if proveedor is not anterior_proveedor:
			self.ventana.soltar_proveedor(anterior_proveedor, nuevo=proveedor)
		if cambio:
			self.lista_archivos.limpiar_marcas()
			self._tamanos.clear()
			self.filtro_rapido = ""
			if self.campo_filtro.IsShown():
				self._ocultar_filtro()
		subiendo_desde = None
		if cambio and anterior_proveedor is proveedor and anterior_ruta and proveedor.padre(anterior_ruta) == ruta:
			subiendo_desde = proveedor.nombre(anterior_ruta)
		self._proveedor, self._ruta = proveedor, ruta
		self._todas = entradas
		self._sincronizar_columnas()
		# Al entrar en otra carpeta el cursor va arriba del todo (como en Norton), salvo
		# al subir (queda en la carpeta de la que se sale) o si se pidió un nombre.
		self._mostrar(cursor or subiendo_desde, al_principio=cambio)
		if proveedor.esquema == "local" and ruta:
			unidad = rutas.raiz(ruta)[:2].upper()
			self._ultimas[unidad] = ruta
		if historial and cambio:
			self._historial.visitar(self.mostrar_ruta())
		self._actualizar_etiqueta()
		self._vigilar()
		if cambio:
			self._anunciar_carpeta()
			self.ventana.panel_cambio_carpeta(self)
		if al_terminar is not None:
			al_terminar(True)

	def _al_fallar_listado(self, peticion, proveedor, ruta, error, al_terminar) -> None:
		if not self or peticion != self._peticion:
			return
		self._leyendo = False
		from app.core.tareas import TareaCancelada, TiempoAgotado

		if isinstance(error, TareaCancelada):
			mensaje = ""
		elif isinstance(error, TiempoAgotado):
			mensaje = _("{r} no responde.").format(r=proveedor.mostrar(ruta))
		else:
			mensaje = errores.mensaje_para_usuario(error)
		if mensaje:
			self.ventana.SetStatusText(mensaje)
			anuncios.anunciar(mensaje, anuncios.ESENCIAL)
		if proveedor is not self._proveedor and proveedor is not resolver.proveedor_local():
			self.ventana.soltar_proveedor(proveedor, nuevo=self._proveedor)
		if al_terminar is not None:
			al_terminar(False)

	def refrescar(self, conservar: bool = True, al_terminar: Callable[[bool], None] | None = None) -> None:
		if not self._ruta and self._proveedor.esquema == "local":
			return
		cursor = self.cursor()
		nombre = cursor.nombre if cursor is not None else None
		marcas = self.lista_archivos.claves_marcadas() if conservar else set()

		def tras(ok: bool) -> None:
			if ok and marcas:
				self.lista_archivos.poner_marcas(marcas)
			if al_terminar is not None:
				al_terminar(ok)

		self._peticion += 1
		peticion = self._peticion
		proveedor, ruta = self._proveedor, self._ruta

		def listo(entradas) -> None:
			if not self or peticion != self._peticion:
				return
			self._todas = entradas
			self._mostrar(nombre, conservar_marcas=True)
			tras(True)

		def fallo(error) -> None:
			if not self or peticion != self._peticion:
				return
			if isinstance(error, base.NoEncontrado):
				# La carpeta desapareció: subir a la primera superior que exista.
				anuncios.anunciar(_("La carpeta ya no existe"), anuncios.ESENCIAL, sonido="nav.carpeta_desaparecida")
				self.ir_a(self._respaldo(self._ruta) if self.es_local() else (proveedor.padre(ruta) or proveedor.raiz(ruta)), forzar_aqui=True)
			tras(False)

		self.tareas.enviar(self._listar, proveedor, ruta, al_terminar=listo, al_fallar=fallo, nombre=f"refrescar-{self.lado}",
			tiempo_maximo=float(self.config.obtener("general.tiempo_unidad_s")))

	def _anunciar_carpeta(self) -> None:
		entradas = [e for e in self.entradas() if not e.es_superior]
		nombre = self._proveedor.nombre(self._ruta) if self._ruta else self.mostrar_ruta()
		if not entradas:
			# 2.0 (4.3): el sonido del catálogo en lugar del aviso de la 1.x.
			anuncios.anunciar(_("{n}, carpeta vacía").format(n=nombre), anuncios.RESULTADO, sonido="nav.carpeta_vacia")
			return
		completo = _("{n}, {c}").format(n=nombre, c=self._recuento_texto())
		if anuncios.se_dice(anuncios.DETALLE):
			anuncios.anunciar(completo, anuncios.DETALLE, completo)
		else:
			anuncios.anunciar(nombre, anuncios.NORMAL, completo)
		if self._proveedor.esquema != "local" and self.config.obtener("accesibilidad.consejos"):
			self.ventana.consejo(self._proveedor)

	# ── Mostrar entradas ──────────────────────────────────────────────────────────

	def _visibles(self) -> list[base.Entrada]:
		ocultos = self.ventana.mostrar_ocultos()
		patron = seleccion.Patron.analizar(self.filtro) if self.filtro else None
		en_carpetas = bool(self.config.obtener("paneles.patrones_en_carpetas"))
		visibles = []
		for entrada in self._todas:
			if not ocultos and (entrada.oculto or entrada.sistema):
				continue
			if es_temporal_de_copia(entrada.nombre):
				continue
			if patron is not None and (not entrada.es_carpeta or en_carpetas) and not patron.coincide(entrada.nombre):
				continue
			if self.filtro_rapido and not seleccion.contiene(entrada.nombre, self.filtro_rapido):
				continue
			tamano = self._tamanos.get(clave(entrada))
			visibles.append(entrada.con(tamano=tamano) if tamano is not None else entrada)
		criterio, inverso = self.orden_efectivo()
		conservar = getattr(self._proveedor, "conservar_orden", None)
		if callable(conservar) and not self.es_lista() and conservar(self._ruta):
			# 2.0 (9.1): el proveedor ya da el orden bueno (en «Red», por grupo y nombre).
			criterio, inverso = ordenacion.SIN_ORDEN, False
		ordenadas = ordenacion.ordenar(
			visibles, criterio, inverso, bool(self.config.obtener("paneles.carpetas_primero")),
			bool(self.config.obtener("paneles.orden_natural")), self._tipos,
		)
		padre = self._proveedor.padre(self._ruta) if self._ruta or self._proveedor.esquema != "local" else None
		if self.config.obtener("paneles.fila_superior") and (padre is not None or self._proveedor.contenedor is not None or self._listas):
			ordenadas.insert(0, base.entrada_superior(padre or ""))
		return ordenadas

	def _mostrar(self, cursor: str | None = None, conservar_marcas: bool = True, al_principio: bool = False) -> None:
		self.lista_archivos.establecer(self._visibles(), cursor, conservar_marcas, al_principio=al_principio)
		if self.lista_archivos.marcas_ocultas():
			self.lista_archivos.podar_marcas_ocultas({clave(e) for e in self._todas})
		self._actualizar_resumen()

	def reordenar(self) -> None:
		"""Vuelve a ordenar y filtrar lo ya leído (sin leer de nuevo)."""
		self._mostrar()

	def _formatear(self, entrada: base.Entrada, columna: str) -> str:
		if columna == "nombre":
			return entrada.nombre
		if entrada.es_superior:
			return _("Carpeta superior") if columna == "tipo" else ""
		if columna == "extension":
			return entrada.extension
		if columna == "tipo":
			return self._tipo(entrada)
		if columna == "tamano":
			if entrada.es_carpeta:
				return formato.tamano(entrada.tamano, self.config.obtener("paneles.formato_tamano")) if entrada.tamano >= 0 else _("Carpeta")
			return formato.tamano(entrada.tamano, self.config.obtener("paneles.formato_tamano"))
		if columna == "modificado":
			return formato.fecha(entrada.modificado, self.config.obtener("paneles.formato_fecha"))
		if columna == "creado":
			return formato.fecha(entrada.creado, self.config.obtener("paneles.formato_fecha"))
		if columna == "atributos":
			return formato.atributos_cortos(entrada.atributos)
		if columna == "ruta":
			# En una carpeta normal todas las filas están en la del panel.
			return entrada.ruta_real or self.mostrar_ruta()
		if columna in self._titulos_propios:
			# 2.0 (9.1): columna propia del proveedor (Tipo, Remoto y Estado en «Red»).
			valor = getattr(self._proveedor, "valor_columna", None)
			return str(valor(entrada, columna) or "") if callable(valor) else ""
		return ""

	def _tipo(self, entrada: base.Entrada) -> str:
		if entrada.es_enlace:
			return _("Enlace a {d}").format(d=entrada.destino_enlace) if entrada.destino_enlace else _("Enlace")
		if entrada.es_carpeta:
			return _("Carpeta")
		ext = entrada.extension
		if ext not in self._tipos:
			self._tipos[ext] = _("Archivo {e}").format(e=ext.upper()) if ext else _("Archivo")
			self.ventana.pedir_tipo(ext, self._tipos)
		return self._tipos[ext]

	def _recuento_texto(self) -> str:
		entradas = [e for e in self.entradas() if not e.es_superior]
		carpetas = sum(1 for e in entradas if e.es_carpeta)
		archivos = len(entradas) - carpetas
		bytes_ = sum(e.tamano for e in entradas if not e.es_carpeta and e.tamano > 0)
		texto = formato.recuento(carpetas, archivos)
		if archivos:
			texto += ", " + formato.tamano_legible(bytes_)
		return texto

	def texto_resumen(self) -> str:
		partes = [self._recuento_texto()]
		marcadas = self.marcadas()
		if marcadas:
			bytes_ = sum(e.tamano for e in marcadas if e.tamano > 0)
			partes.append(_("Marcados: {m}, {b}").format(m=len(marcadas), b=formato.tamano_legible(bytes_)))
		if self.filtro:
			partes.append(_("Filtro: {f}").format(f=self.filtro))
		if self.filtro_rapido:
			partes.append(_("Filtro rápido: {f}").format(f=self.filtro_rapido))
		return ". ".join(partes)

	def _actualizar_resumen(self) -> None:
		self.resumen.ChangeValue(self.texto_resumen())

	def _actualizar_etiqueta(self) -> None:
		texto = f"{nombre_lado(self.lado)}: {self.mostrar_ruta()}"
		if self.filtro:
			texto += _(", filtro {f}").format(f=self.filtro)
		if self.bloqueada:
			texto += _(", pestaña bloqueada")
		self.etiqueta.SetLabel(texto)
		self.lista_archivos.SetName(texto)
		try:
			import ctypes

			# El texto de la ventana de la lista también da su nombre MSAA.
			ctypes.windll.user32.SetWindowTextW(self.lista_archivos.GetHandle(), texto)
		except (AttributeError, OSError):
			log.debug("No se pudo poner el texto de la lista", exc_info=True)
		self.ventana.titulo_pestana(self, self._titulo())

	def _titulo(self) -> str:
		if self._listas:
			return self.mostrar_ruta()
		return self._proveedor.nombre(self._ruta) if self._ruta else self.mostrar_ruta()

	# ── Avisos de la lista ────────────────────────────────────────────────────────

	def _al_cambiar_cursor(self) -> None:
		self.ventana.panel_cambio_cursor(self)

	def _al_cambiar_marcas(self) -> None:
		self._actualizar_resumen()
		self._avisar_marcas()

	def _al_recibir_foco(self, evento: wx.FocusEvent) -> None:
		evento.Skip()
		self.ventana.panel_enfocado(self)

	def _al_cambiar_ancho(self, evento: wx.ListEvent) -> None:
		evento.Skip()
		wx.CallAfter(self._guardar_anchos)

	def _guardar_anchos(self) -> None:
		if self:
			self._anchos.update(self.lista_archivos.anchos())
			self.config.establecer_diferido("paneles.anchos", dict(self._anchos))

	# ── Acciones del protocolo ─────────────────────────────────────────────────────

	def movimiento_silencioso(self) -> None:
		"""Marca para el complemento de NVDA antes de mover el foco por código (10.16)."""
		from app.ui import senales_nvda

		try:
			senales_nvda.marcar_movimiento_silencioso(self.lista_archivos.GetHandle())
		except RuntimeError:
			log.debug("La lista ya no existe", exc_info=True)

	def enfocar(self) -> None:
		destino = self.lista_archivos if self.vista in VISTA_LISTA else self._vistas.get(self.vista)
		if destino is not None and hasattr(destino, "control_enfocable"):
			destino = destino.control_enfocable()
		(destino or self.lista_archivos).SetFocus()

	def ir_a_nombre(self, nombre: str) -> bool:
		indice = self.lista_archivos.indice_de(nombre)
		if indice >= 0:
			self.lista_archivos.mover_cursor(indice)
			return True
		return False

	def marcar(self, predicado: Callable[[base.Entrada], bool], valor: bool = True) -> int:
		indices = [i for i, e in enumerate(self.entradas()) if not e.es_superior and predicado(e)]
		return self.lista_archivos.marcar_indices(indices, valor)

	def desmarcar_todo(self) -> None:
		self.lista_archivos.limpiar_marcas()

	def _avisar_marcas(self) -> None:
		"""Evento ``al_cambiar_marcas`` del bus (14.4)."""
		avisar = getattr(self.ventana, "panel_cambio_marcas", None)
		if callable(avisar):
			avisar(self)

	def guardar_marcas(self) -> None:
		self._marcas_guardadas = self.lista_archivos.claves_marcadas() or {clave(e) for e in self.elementos_trabajo()}

	def restaurar_marcas(self) -> int:
		self.lista_archivos.poner_marcas(self._marcas_guardadas)
		return len(self.lista_archivos.claves_marcadas())

	def fijar_tamano(self, nombre: str, tamano: int) -> None:
		for entrada in self._todas:
			if entrada.nombre == nombre:
				self._tamanos[clave(entrada)] = tamano
		self._mostrar()

	def abrir_lista(self, titulo: str, rutas_: Sequence[str]) -> None:
		cursor = self.cursor()
		self._listas.append((self._proveedor, self._ruta, cursor.nombre if cursor else None))
		self.ir_a("", ProveedorResultados(titulo, list(rutas_)), forzar_aqui=True)

	def es_lista(self) -> str | None:
		if isinstance(self._proveedor, ProveedorResultados) and not self._ruta:
			return self._proveedor.titulo
		return None

	def cerrar_lista(self) -> None:
		if not self._listas:
			return
		proveedor, ruta, cursor = self._listas.pop()
		self.ir_a(ruta, proveedor, cursor, forzar_aqui=True)

	def vincular_tarea(self, tarea: Any, descripcion: str) -> None:
		self._tarea_vinculada = (tarea, descripcion) if tarea is not None else None

	def cancelar_o_quitar(self) -> bool:
		"""Escape en el panel: lectura, tarea vinculada o filtro rápido, en ese orden."""
		if self._leyendo and self._tarea_listado is not None:
			self._peticion += 1
			self._tarea_listado.cancelar("Escape")
			self._leyendo = False
			anuncios.anunciar(_("Lectura cancelada"), anuncios.RESULTADO)
			return True
		if self._tarea_vinculada is not None:
			tarea, descripcion = self._tarea_vinculada
			self._tarea_vinculada = None
			if not tarea.terminada:
				tarea.cancelar("Escape")
				anuncios.anunciar(_("Cancelado: {d}").format(d=descripcion), anuncios.RESULTADO)
				return True
		if self.filtro_rapido:
			self.quitar_filtro_rapido()
			return True
		return False

	# ── Historial y unidades ─────────────────────────────────────────────────────

	def historial(self) -> list[str]:
		return self._historial.recientes()

	def ir_historial(self, ruta: str) -> None:
		self._ir_texto(ruta, historial=True)

	def atras(self) -> bool:
		destino = self._historial.atras()
		if destino is None:
			return False
		self._ir_texto(destino, historial=False)
		return True

	def adelante(self) -> bool:
		destino = self._historial.adelante()
		if destino is None:
			return False
		self._ir_texto(destino, historial=False)
		return True

	def _ir_texto(self, texto: str, historial: bool) -> None:
		self.ir_a_texto(texto, historial=historial)

	def ultima_carpeta(self, unidad: str) -> str | None:
		return self._ultimas.get(unidad.upper()[:2])

	# ── Vista, orden, filtros, columnas ──────────────────────────────────────────

	def aplicar_vista(self, vista: str) -> None:
		if vista != self.vista:
			anuncios.anunciar("", anuncios.DETALLE, sonido="vista.cambiar")
		if vista in VISTA_LISTA:
			self._vista_lista = vista
			self.vista = vista
			self.lista_archivos.poner_columnas(self._columnas_vista(), self._anchos)
			self._mostrar()
			self.libro.SetSelection(0)
			return
		if vista not in self._vistas:
			self._vistas[vista] = self._crear_vista(vista)
		self.vista = vista
		self.libro.SetSelection(self.libro.FindPage(self._vistas[vista]))

	def vista_anterior(self) -> None:
		self.aplicar_vista(self._vista_lista)

	def _crear_vista(self, vista: str) -> wx.Window:
		from app.ui import vistas

		if vista == "informacion":
			control = vistas.VistaInformacion(self.libro, self.tareas)
		elif vista == "rapida":
			control = vistas.VistaRapida(self.libro, self.tareas)
		else:
			from app.ui.arbol_carpetas import ArbolCarpetas

			otro = self.ventana.panel_opuesto(self)
			control = ArbolCarpetas(self.libro, _("Árbol de carpetas:"), otro.proveedor, otro.proveedor.raiz(otro.ruta) if otro.ruta else "",
				lambda ruta: self.ventana.arbol_eligio(self, ruta), self.tareas,
				retardo_ms=int(self.config.obtener("paneles.retardo_arbol_ms")))
		self.libro.AddPage(control, vista)
		return control

	def vista_actual(self) -> wx.Window | None:
		return self._vistas.get(self.vista)

	def aplicar_retardo_arbol(self) -> None:
		"""La vista Árbol ya creada toma el ``paneles.retardo_arbol_ms`` nuevo."""
		arbol = self._vistas.get("arbol")
		if arbol is not None and hasattr(arbol, "retardo_ms"):
			arbol.retardo_ms = max(0, int(self.config.obtener("paneles.retardo_arbol_ms")))

	def _orden_preferido(self) -> tuple[str, bool] | None:
		"""``orden_preferido`` del proveedor (ocupación por tamaño, papelera por fecha) mientras la persona no elija otro."""
		preferido = getattr(self._proveedor, "orden_preferido", None)
		if not preferido or self.es_lista() or self._proveedor.esquema in self._orden_elegido_en:
			return None
		try:
			criterio, inverso = preferido
		except (TypeError, ValueError):
			return None
		return (str(criterio), bool(inverso)) if criterio in ordenacion.CRITERIOS else None

	def orden_efectivo(self) -> tuple[str, bool]:
		"""Orden con el que se muestra lo leído ahora (el de la pestaña o el preferido del proveedor)."""
		return self._orden_preferido() or (self.criterio_orden, self.orden_inverso)

	def aplicar_orden(self, criterio: str, inverso: bool | None = None) -> None:
		if self._orden_preferido() is not None:
			# La persona elige un orden en un proveedor con orden propio: desde aquí manda el suyo
			# (y Ctrl+F3 dos veces invierte el que estaba viendo, no el de la pestaña).
			self.criterio_orden, self.orden_inverso = self.orden_efectivo()
			self._orden_elegido_en.add(self._proveedor.esquema)
		if inverso is None:
			inverso = (not self.orden_inverso) if criterio == self.criterio_orden else False
		self.criterio_orden, self.orden_inverso = criterio, inverso
		self.movimiento_silencioso()
		self._mostrar()
		anuncios.anunciar("", anuncios.DETALLE, sonido="orden.cambiar")

	def aplicar_filtro(self, patron: str) -> None:
		self.filtro = patron.strip()
		self.movimiento_silencioso()
		self._mostrar()
		self._actualizar_etiqueta()
		anuncios.anunciar("", anuncios.DETALLE, sonido="filtro.aplicar" if self.filtro else "filtro.quitar")

	def aplicar_columnas(self, columnas: list[str], anchos: dict[str, int] | None = None) -> None:
		"""Columnas de lo que se ve: las de las listas de resultados si se está en una; si no, las de carpeta."""
		elegidas = [c for c in columnas if c] or ["nombre"]
		if self.es_lista():
			self._columnas_lista = elegidas
		else:
			self._columnas_carpeta = elegidas
		if anchos:
			self._anchos.update(anchos)
		self.lista_archivos.poner_columnas(self._columnas_vista(), self._anchos)
		self._mostrar()

	def aplicar_conjunto(self, conjunto) -> None:
		"""Aplica un ``ConjuntoVista`` de las vistas por carpeta (10.4), o ``None`` para volver a las de la pestaña.

		Enganche de N2: lo llama PE al entrar en una carpeta con regla. El conjunto cambia
		columnas, anchos, orden, vista, filtro y orden de lectura de lo que se ve, sin
		tocar lo que la pestaña guarda en la sesión.
		"""
		self.conjunto = conjunto
		if conjunto is None:
			self.lista_archivos.poner_columnas(self._columnas_vista(), self._anchos)
			self.aplicar_lectura(self.lectura)
			self._mostrar()
			return
		if conjunto.columnas:
			anchos = dict(self._anchos)
			anchos.update(conjunto.anchos or {})
			self.lista_archivos.poner_columnas(list(conjunto.columnas), anchos)
		if conjunto.orden:
			self.criterio_orden, self.orden_inverso = conjunto.orden, bool(conjunto.inverso)
		if conjunto.filtro:
			self.filtro = conjunto.filtro
		if conjunto.vista and conjunto.vista != self.vista:
			self.aplicar_vista(conjunto.vista)
		self.aplicar_lectura(list(conjunto.lectura))
		self._mostrar()

	def aplicar_lectura(self, lectura: list[str]) -> None:
		"""Coloca primero las columnas de ``lectura`` y publica el orden para NVDA (10.5).

		Las columnas que no están en ``lectura`` se ven, pero al final. Como mucho
		15 se leen al moverse. Vacía: el orden de ``paneles.lectura`` o el de las columnas.
		"""
		from app.ui import senales_nvda

		lectura = [c for c in (lectura or self.config.obtener("paneles.lectura") or []) if c][:senales_nvda.MAX_COLUMNAS]
		lista = self.lista_archivos
		actuales = list(getattr(lista, "columnas", []) or [])
		if lectura and actuales:
			primeras = [c for c in lectura if c in actuales]
			nuevas = primeras + [c for c in actuales if c not in primeras]
			if nuevas != actuales:
				lista.poner_columnas(nuevas, self._anchos)
				actuales = nuevas
			indices = list(range(len(primeras)))
		else:
			indices = list(range(min(len(actuales), senales_nvda.MAX_COLUMNAS)))
		try:
			senales_nvda.publicar_orden_lectura(lista.GetHandle(), indices)
		except (RuntimeError, ValueError):
			log.debug("No se pudo publicar el orden de lectura", exc_info=True)

	def aplicar_columnas_carpeta(self, columnas: list[str]) -> None:
		"""Nuevas columnas por defecto (Opciones o un perfil) para las carpetas de esta pestaña."""
		self._columnas_carpeta = [c for c in columnas if c] or ["nombre"]
		if self.vista in VISTA_LISTA:
			self._sincronizar_columnas()
			self._mostrar()

	# ── Filtro rápido ────────────────────────────────────────────────────────────

	def mostrar_filtro_rapido(self) -> None:
		self._etiqueta_filtro.Show()
		self.campo_filtro.Show()
		self.Layout()
		self.campo_filtro.SetFocus()

	def _al_escribir_filtro(self, _evento: wx.CommandEvent) -> None:
		self.filtro_rapido = self.campo_filtro.GetValue()
		self._mostrar()
		anuncios.anunciar(formato.plural(len([e for e in self.entradas() if not e.es_superior]),
			_("{n} elemento"), _("{n} elementos")), anuncios.DETALLE)

	def _al_tecla_filtro(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		if codigo in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_DOWN):
			self.lista_archivos.SetFocus()
			return
		if codigo == wx.WXK_ESCAPE:
			self.quitar_filtro_rapido()
			return
		evento.Skip()

	def quitar_filtro_rapido(self) -> None:
		self.filtro_rapido = ""
		self.campo_filtro.ChangeValue("")
		self._ocultar_filtro()
		self._mostrar()
		self.movimiento_silencioso()
		self.lista_archivos.SetFocus()
		anuncios.anunciar(_("Filtro rápido quitado"), anuncios.RESULTADO, sonido="filtro.quitar")

	def _ocultar_filtro(self) -> None:
		self._etiqueta_filtro.Hide()
		self.campo_filtro.Hide()
		self.Layout()

	# ── Búsqueda rápida y teclear ─────────────────────────────────────────────────

	def busqueda_viva(self) -> bool:
		return bool(self._busqueda) and time.monotonic() < self._busqueda_hasta

	def teclear(self, caracter: str) -> bool:
		"""Carácter tecleado en la lista (``EVT_CHAR``): búsqueda rápida o línea de órdenes."""
		if self.config.obtener("paneles.teclear_en_linea_ordenes") and self.ventana.linea_disponible():
			self.ventana.escribir_en_linea(caracter)
			return True
		self.buscar_letra(caracter)
		return True

	def buscar_letra(self, caracter: str) -> None:
		if not self.busqueda_viva():
			self._busqueda = ""
		self._busqueda += caracter
		self._busqueda_hasta = time.monotonic() + int(self.config.obtener("paneles.tiempo_busqueda_rapida_ms")) / 1000
		self._buscar()

	def borrar_letra_busqueda(self) -> None:
		self._busqueda = self._busqueda[:-1]
		self._busqueda_hasta = time.monotonic() + int(self.config.obtener("paneles.tiempo_busqueda_rapida_ms")) / 1000
		if self._busqueda:
			self._buscar()

	def _buscar(self) -> None:
		buscado = seleccion.sin_acentos(self._busqueda).casefold()
		entradas = self.entradas()
		inicio = max(0, self.lista_archivos.cursor_indice())
		orden = list(range(inicio, len(entradas))) + list(range(0, inicio))
		for indice in orden:
			if seleccion.sin_acentos(entradas[indice].nombre).casefold().startswith(buscado):
				if indice != self.lista_archivos.cursor_indice():
					self.lista_archivos.mover_cursor(indice)
				return
		wx.Bell()
		anuncios.anunciar(_("Sin coincidencias: {t}").format(t=self._busqueda), anuncios.RESULTADO)

	def pasar_busqueda_a_linea(self) -> bool:
		if not self.busqueda_viva():
			return False
		texto, self._busqueda = self._busqueda, ""
		self.ventana.escribir_en_linea(texto)
		return True

	# ── Vigilancia de cambios ─────────────────────────────────────────────────────

	def _vigilar(self) -> None:
		self.dejar_de_vigilar()
		if not self.config.obtener("paneles.vigilar_cambios") or not self.es_local() or not self._ruta:
			return
		if not self.ventana.pestana_visible(self):
			return
		from app.services.windows import unidades

		raiz = rutas.raiz(self._ruta)
		if raiz.startswith("\\\\"):
			tipo = "red"
		else:
			tipo = unidades.tipo_de(raiz)
			if tipo == "fija" and unidades.es_usb(raiz[:2]):
				tipo = "extraible"
		if tipo not in ("fija", "red"):
			return
		try:
			self._vigilante = wx.FileSystemWatcher()
			self._vigilante.SetOwner(self)
			self.Bind(wx.EVT_FSWATCHER, self._al_cambio_disco)
			self._vigilante.Add(wx.FileName.DirName(self._ruta), wx.FSW_EVENT_ALL)
		except Exception:  # noqa: BLE001 - sin vigilancia se refresca a mano
			log.debug("No se pudo vigilar %s", self._ruta, exc_info=True)
			self._vigilante = None

	def dejar_de_vigilar(self) -> None:
		if self._vigilante is not None:
			try:
				self._vigilante.RemoveAll()
			except Exception:  # noqa: BLE001 - liberar no debe fallar
				log.debug("No se pudo soltar la vigilancia", exc_info=True)
			self._vigilante = None

	def vigila_dentro_de(self, ruta: str) -> bool:
		return self._vigilante is not None and rutas.esta_dentro(self._ruta, ruta)

	def _al_cambio_disco(self, evento: wx.FileSystemWatcherEvent) -> None:
		tipo = evento.GetChangeType()
		if tipo & wx.FSW_EVENT_ERROR:
			self.dejar_de_vigilar()
			return
		if self._refresco_pendiente is not None and self._refresco_pendiente.IsRunning():
			return
		ahora = time.monotonic()
		espera = 1000 if ahora - self._ultimo_refresco > 5 else 5000
		self._refresco_pendiente = wx.CallLater(espera, self._refresco_vigilado)

	def _refresco_vigilado(self) -> None:
		if not self:
			return
		self._ultimo_refresco = time.monotonic()
		self.refrescar(conservar=True)

	# ── Sesión ────────────────────────────────────────────────────────────────────

	def como_dict(self) -> dict:
		from app.services import sesion

		texto = self.mostrar_ruta()
		if self._listas:
			# Una lista de resultados no se restaura: se guarda la carpeta de la que se partió.
			proveedor, ruta, _c = self._listas[0]
			texto = proveedor.mostrar(ruta)
		return sesion.pestana(
			ruta=texto, vista=self.vista, orden=self.criterio_orden, inverso=self.orden_inverso, filtro=self.filtro,
			bloqueada=self.bloqueada, columnas=list(self._columnas_carpeta), historial=self._historial.como_dict(),
			lectura=list(self.lectura),
		)

	def Destroy(self) -> bool:  # noqa: N802 - API de wx
		self.dejar_de_vigilar()
		if self._tarea_listado is not None:
			self._tarea_listado.cancelar("cierre")
		return super().Destroy()


def _resolver(_tarea, texto: str, actual):
	return resolver.abrir_ruta(texto, actual)


def resolver_en_hilo(tareas, texto: str, actual, al_listo, al_fallar, tiempo_maximo: float | None = None) -> None:
	"""Llama a ``resolver.abrir_ruta(texto, actual)`` en un hilo de trabajo.

	``al_listo((proveedor, carpeta, cursor))`` o ``al_fallar(error)`` se ejecutan en
	el hilo de la interfaz. Lo usan el panel, la línea de órdenes, los argumentos
	de arranque y el destino escrito en el diálogo de copiar.
	"""
	tarea = tareas.enviar(_resolver, texto, actual, al_terminar=al_listo, al_fallar=al_fallar,
		nombre="resolver-ruta", tiempo_maximo=tiempo_maximo)
	if tarea is None:
		al_fallar(base.ErrorArchivos(_("No se puede abrir la ruta ahora")))
