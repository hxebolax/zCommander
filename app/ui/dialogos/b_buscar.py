# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Buscar archivos» (Alt+F7, sección 8.12) con sus resultados.

Es un diálogo NO modal: la persona puede volver a los paneles, ver un
resultado y regresar a la lista sin perderla. No conoce la ventana principal:
recibe funciones (``al_ir``, ``al_ver``, ``al_enviar``) que las acciones del
bloque B rellenan, así que se prueba sin ventana ni paneles.

Hilos: la búsqueda corre en ``GestorTareas`` (``busqueda.buscar``). El hilo
solo deja los resultados en una cola; un temporizador de la interfaz los pasa
a la lista 4 veces por segundo. La lista es virtual y crecer no mueve el
cursor del lector; el recuento va en el campo «Estado» y al terminar se
anuncia «Búsqueda terminada: 120 resultados en 4 s».

Teclado (letras sin repetir; ver ``revisar_teclado``):

- Fuera de las pestañas: Resultados (R), Estado (T), Buscar (B) o Detener (D),
  Nueva búsqueda (Q), Ver (V, F3), Editar (E, F4), Ir al archivo (H, Intro en
  la lista), Enviar al panel (P), Guardar resultados (G), Cerrar (A).
- Escape detiene la búsqueda en curso; un segundo Escape cierra.
- Las opciones del texto están en su propia pestaña «Contenido»: en una sola
  pestaña General no cabían todas con letras distintas.
- 2.0 (3.5): «Motor de búsqueda» (M, pestaña Avanzado) con los motores de los
  complementos y «Buscar también dentro de documentos» (M, pestaña Contenido)
  con sus extractores de texto. Ninguno activa un complemento para pintarse.
"""

from __future__ import annotations

import builtins
import collections
import dataclasses
import logging
import os
import time
from collections.abc import Callable, Sequence
from datetime import datetime

import wx

from app.services import busqueda, formato
from app.services.busqueda import Criterios, ErrorCriterios, Resultado
from app.services.vfs import base, resolver, rutas
from app.ui import anuncios
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.composicion import PreferenciasLectura
from app.ui.accesibilidad.dialogos import desplegable_abierto, preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)

UNIDADES = (("bytes", 1), ("KB", 1024), ("MB", 1024 ** 2), ("GB", 1024 ** 3))
_INTERVALO_MS = 250


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def motores_de_complementos() -> list[tuple[str, str]]:
	"""(id, nombre) de los motores de búsqueda de los complementos (2.0, 3.5), sin activarlos."""
	try:
		from app.plugins import registro

		return registro.motores_busqueda()
	except Exception:  # noqa: BLE001 - un manifiesto raro no deja sin el diálogo de búsqueda
		log.warning("No se pudieron leer los motores de búsqueda de los complementos", exc_info=True)
		return []


def hay_extractores() -> bool:
	"""Verdadero si algún complemento sabe sacar el texto de documentos (2.0, 3.5)."""
	try:
		from app.plugins import registro

		return registro.hay_extractores()
	except Exception:  # noqa: BLE001
		log.warning("No se pudieron leer los extractores de los complementos", exc_info=True)
		return False


def preferencias_lectura(config) -> Callable[[], PreferenciasLectura]:
	"""Las preferencias de lectura por columnas, leídas en cada anuncio (un cambio se nota sin reabrir)."""

	def leer() -> PreferenciasLectura:
		try:
			return PreferenciasLectura(
				numero_fila=bool(config.obtener("accesibilidad.leer_numero_fila")),
				cabecera=bool(config.obtener("accesibilidad.leer_cabecera")),
				contenido=bool(config.obtener("accesibilidad.leer_contenido")),
			)
		except Exception:  # noqa: BLE001 - sin configuración se lee con los valores de fábrica
			log.debug("No se pudieron leer las preferencias de lectura", exc_info=True)
			return PreferenciasLectura()

	return leer


def leer_numero(texto: str, nombre: str) -> float | None:
	"""Número escrito por la persona («1,5» o «1.5»); vacío = sin límite.

	:raises ErrorCriterios: si no es un número positivo.
	"""
	limpio = texto.strip().replace(",", ".")
	if not limpio:
		return None
	try:
		valor = float(limpio)
	except ValueError:
		raise ErrorCriterios(_("{n}: escriba un número, por ejemplo 1,5.").format(n=nombre)) from None
	if valor < 0:
		raise ErrorCriterios(_("{n}: el número no puede ser negativo.").format(n=nombre))
	return valor


def leer_fecha(texto: str, nombre: str, fin_del_dia: bool = False) -> float | None:
	"""Fecha «dd/mm/aaaa» (también con guiones); vacío = sin límite.

	:param fin_del_dia: «hasta» incluye todo ese día.
	:raises ErrorCriterios: si no es una fecha válida.
	"""
	limpio = texto.strip().replace("-", "/").replace(".", "/")
	if not limpio:
		return None
	try:
		momento = datetime.strptime(limpio, "%d/%m/%Y")
	except ValueError:
		raise ErrorCriterios(_("{n}: escriba la fecha como día/mes/año, por ejemplo 31/12/2025.").format(n=nombre)) from None
	if fin_del_dia:
		momento = momento.replace(hour=23, minute=59, second=59)
	return momento.timestamp()


class ListaResultados(ListaAccesible):
	"""Lista virtual de resultados: las filas viven en una lista de Python y se añaden por lotes.

	``ListaAccesible`` reconstruye su diccionario de celdas en cada inserción;
	con decenas de miles de resultados eso sería cuadrático, así que aquí solo
	se cambia el número de filas.
	"""

	def __init__(self, padre: wx.Window, nombre: str, config) -> None:
		self._filas: list[tuple[str, str, str, str]] = []
		super().__init__(padre, nombre, columnas=[
			(_("Nombre"), padre.FromDIP(200)), (_("Carpeta"), padre.FromDIP(300)),
			(_("Tamaño"), padre.FromDIP(90)), (_("Fecha"), padre.FromDIP(130)),
		], estilo=wx.LC_REPORT | wx.LC_SINGLE_SEL, virtual=True, leer_preferencias=preferencias_lectura(config))

	def OnGetItemText(self, item: int, column: int) -> str:  # noqa: N802 - API de wx
		if 0 <= item < len(self._filas) and 0 <= column < 4:
			return self._filas[item][column]
		return ""

	def numero_filas(self) -> int:
		return len(self._filas)

	def texto_celda(self, fila: int, columna: int) -> str:
		return self.OnGetItemText(fila, columna)

	def limpiar(self) -> None:
		self._filas = []
		self.SetItemCount(0)

	def anadir(self, filas: Sequence[tuple[str, str, str, str]]) -> None:
		"""Añade al final sin mover el foco; la primera fila queda enfocada (sin anunciarla)."""
		if not filas:
			return
		vacia = not self._filas
		self._filas.extend(filas)
		self.SetItemCount(len(self._filas))
		if vacia and self.GetFocusedItem() == wx.NOT_FOUND:
			self._mover_foco_silencioso(0)


def fila_de(resultado: Resultado) -> tuple[str, str, str, str]:
	entrada = resultado.entrada
	tamano = _("Carpeta") if entrada.es_carpeta else formato.tamano_legible(entrada.tamano)
	return (entrada.nombre, resultado.mostrar_carpeta, tamano, formato.fecha(entrada.modificado))


class _EstadoHilo:
	"""Lo que el hilo de búsqueda deja para la interfaz (solo atributos simples y una cola)."""

	def __init__(self) -> None:
		self.cola: collections.deque[Resultado] = collections.deque()
		self.revisando = ""


class DialogoBuscar(wx.Dialog):
	"""Buscar archivos y trabajar con los resultados.

	:param tareas: ``GestorTareas`` donde corre la búsqueda.
	:param buscar_en: texto inicial de «Buscar en» (la carpeta del panel activo).
	:param panel: ``(proveedor, ruta, texto)`` del panel activo: si «Buscar en»
		dice ese texto, se busca con su proveedor (comprimido o servidor).
	:param al_ir: ``al_ir(resultado)`` lleva el panel activo al resultado.
	:param al_ver: ``al_ver(resultado, editar)`` lo abre en el visor o el editor.
	:param al_enviar: ``al_enviar(titulo, rutas)`` abre la lista en el panel activo.
	:param al_cerrar: se llama al cerrarse el diálogo.
	"""

	def __init__(
		self,
		padre: wx.Window | None,
		config,
		tareas,
		buscar_en: str = "",
		panel: tuple[base.Proveedor, str, str] | None = None,
		al_ir: Callable[[Resultado], None] | None = None,
		al_ver: Callable[[Resultado, bool], None] | None = None,
		al_enviar: Callable[[str, list[str]], None] | None = None,
		al_cerrar: Callable[[], None] | None = None,
	) -> None:
		super().__init__(padre, title=_("Buscar archivos"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			name=_("Buscar archivos"))
		self._config = config
		self._tareas = tareas
		self._panel = panel
		self._al_ir, self._al_ver, self._al_enviar, self._al_cerrar = al_ir, al_ver, al_enviar, al_cerrar
		self._tarea = None
		self._hilo = _EstadoHilo()
		self._resultados: list[Resultado] = []
		self._entregados: set[int] = set()
		self._comprimidos: dict[int, base.Proveedor] = {}
		self._inicio = 0.0
		self._cerrando = False

		self.panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.libro = wx.Notebook(self.panel)
		self._crear_general(buscar_en)
		self._crear_contenido()
		self._crear_avanzado()
		sizer.Add(self.libro, 0, wx.EXPAND | wx.ALL, 6)

		_etiqueta, self.lista = crear_campo(self.panel, _("&Resultados:"), lambda p, **k: ListaResultados(p, _("Resultados"), config))
		self.lista.SetHelpText(_("Resultados de la búsqueda. Intro va al archivo, F3 lo ve, F4 lo edita; "
			"izquierda y derecha leen las columnas."))
		self.lista.SetMinSize(self.panel.FromDIP(wx.Size(720, 220)))
		sizer.Add(_etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
		_etiqueta, self.campo_estado = crear_campo(self.panel, _("Es&tado:"), wx.TextCtrl, value=_("Escriba qué buscar y pulse Buscar."),
			style=wx.TE_READONLY, ayuda=_("Recuento de resultados y carpeta que se está revisando."), sizer=sizer)

		botones = wx.WrapSizer(wx.HORIZONTAL)
		self.boton_buscar = self._boton(botones, _("&Buscar"), _("Empieza la búsqueda; mientras busca, se convierte en Detener (Escape)."))
		self.boton_nueva = self._boton(botones, _("Nueva bús&queda"), _("Vacía los resultados y vuelve a los criterios, que se conservan."))
		self.boton_ver = self._boton(botones, _("&Ver (F3)"), _("Abre el resultado elegido en el visor."))
		self.boton_editar = self._boton(botones, _("&Editar (F4)"), _("Abre el resultado elegido en el editor."))
		self.boton_ir = self._boton(botones, _("Ir al arc&hivo"), _("Cierra la búsqueda y lleva el panel activo a la carpeta del resultado, con el cursor en él (Intro en la lista)."))
		self.boton_enviar = self._boton(botones, _("Enviar al &panel"), _("Abre todos los resultados en el panel activo como una lista sobre la que funcionan todas las operaciones."))
		self.boton_guardar = self._boton(botones, _("&Guardar resultados..."), _("Guarda las rutas encontradas en un archivo de texto, una por línea."))
		self.boton_cerrar = self._boton(botones, _("Cerr&ar"), _("Cierra la búsqueda (también con Escape si no está buscando)."))
		sizer.Add(botones, 0, wx.ALL, 4)
		self.panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(self.panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.boton_buscar.SetDefault()

		self.boton_buscar.Bind(wx.EVT_BUTTON, lambda _e: self.buscar_o_detener())
		self.boton_nueva.Bind(wx.EVT_BUTTON, lambda _e: self.nueva_busqueda())
		self.boton_ver.Bind(wx.EVT_BUTTON, lambda _e: self.ver(editar=False))
		self.boton_editar.Bind(wx.EVT_BUTTON, lambda _e: self.ver(editar=True))
		self.boton_ir.Bind(wx.EVT_BUTTON, lambda _e: self.ir_al_archivo())
		self.boton_enviar.Bind(wx.EVT_BUTTON, lambda _e: self.enviar_al_panel())
		self.boton_guardar.Bind(wx.EVT_BUTTON, lambda _e: self.guardar_resultados())
		self.boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.Close())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.ir_al_archivo())
		self.lista_guardadas.Bind(wx.EVT_CHOICE, lambda _e: self.cargar_guardada())
		self.lista_guardadas.Bind(wx.EVT_KEY_DOWN, self._al_tecla_guardadas)
		self.boton_guardar_busqueda.Bind(wx.EVT_BUTTON, lambda _e: self.guardar_busqueda())
		self.Bind(wx.EVT_CLOSE, self._al_cerrar_ventana)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
		self._temporizador = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.volcar(), self._temporizador)
		preparar_dialogo(self, foco_inicial=self.campo_nombres)
		# Después de preparar_dialogo: wx llama primero al último enlazado.
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self._refrescar_guardadas()
		self._actualizar_botones()
		self.CentreOnParent()

	# ── Construcción ──────────────────────────────────────────────────────────

	def _boton(self, sizer: wx.Sizer, etiqueta: str, ayuda: str) -> wx.Button:
		boton = wx.Button(self.panel, label=etiqueta)
		boton.SetHelpText(ayuda)
		sizer.Add(boton, 0, wx.ALL, 3)
		return boton

	def _leer(self, clave: str, por_defecto):
		try:
			return self._config.obtener(clave)
		except Exception:  # noqa: BLE001 - una clave que falta no impide buscar: valor de fábrica
			log.warning("No se pudo leer %s de la configuración", clave, exc_info=True)
			return por_defecto

	@staticmethod
	def _casilla(pagina: wx.Window, sizer: wx.Sizer, etiqueta: str, ayuda: str, valor: bool = False) -> wx.CheckBox:
		casilla = wx.CheckBox(pagina, label=etiqueta)
		casilla.SetValue(valor)
		casilla.SetHelpText(ayuda)
		sizer.Add(casilla, 0, wx.ALL, 4)
		return casilla

	def _crear_general(self, buscar_en: str) -> None:
		pagina = wx.Panel(self.libro)
		s = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_nombres = crear_campo(pagina, _("&Nombres:"), wx.TextCtrl, value="*",
			ayuda=_("Patrones con * y ?, varios separados por punto y coma; lo que va tras | se excluye (*.* | *.bak). "
				"Con la casilla siguiente, una expresión regular."), sizer=s)
		self.casilla_nombres_regex = self._casilla(pagina, s, _("Nombres como e&xpresión regular"),
			_("Los nombres se buscan con una expresión regular en lugar de patrones."))
		_e, self.campo_buscar_en = crear_campo(pagina, _("B&uscar en:"), wx.TextCtrl, value=buscar_en,
			ayuda=_("Carpeta donde buscar; varias separadas por punto y coma."), sizer=s)
		self.boton_examinar = wx.Button(pagina, label=_("Exam&inar..."))
		self.boton_examinar.SetHelpText(_("Elige la carpeta donde buscar."))
		self.boton_examinar.Bind(wx.EVT_BUTTON, lambda _e: self._examinar())
		s.Add(self.boton_examinar, 0, wx.ALL, 4)
		self.casilla_fijas = self._casilla(pagina, s, _("En todas las unidades &fijas"),
			_("Busca en todos los discos internos en lugar de en «Buscar en»."))
		self.casilla_subcarpetas = self._casilla(pagina, s, _("&Subcarpetas"), _("Busca también dentro de las subcarpetas."),
			bool(self._leer("busqueda.subcarpetas", True)))
		_e, self.campo_profundidad = crear_campo(pagina, _("Pr&ofundidad máxima (0 = sin límite):"), wx.SpinCtrl,
			min=0, max=999, initial=0, ayuda=_("Cuántos niveles de subcarpetas se revisan; 0 los revisa todos."), sizer=s)
		_e, self.lista_guardadas = crear_campo(pagina, _("&Cargar búsqueda guardada:"), wx.Choice, choices=[],
			ayuda=_("Elija una búsqueda guardada para rellenar los criterios. Supr la borra."), sizer=s)
		self.boton_guardar_busqueda = wx.Button(pagina, label=_("Guardar búsqueda co&mo..."))
		self.boton_guardar_busqueda.SetHelpText(_("Guarda los criterios actuales con un nombre para usarlos otro día."))
		s.Add(self.boton_guardar_busqueda, 0, wx.ALL, 4)
		pagina.SetSizer(s)
		self.libro.AddPage(pagina, _("General"))

	def _crear_contenido(self) -> None:
		pagina = wx.Panel(self.libro)
		s = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_texto = crear_campo(pagina, _("Texto &contenido:"), wx.TextCtrl,
			ayuda=_("Texto que deben contener los archivos. Vacío: no se mira el contenido."), sizer=s)
		self.casilla_mayusculas = self._casilla(pagina, s, _("Distinguir ma&yúsculas"), _("«Hola» y «hola» se tratan como distintos."))
		self.casilla_palabra = self._casilla(pagina, s, _("Pa&labra completa"), _("Solo cuenta si no forma parte de otra palabra."))
		self.casilla_texto_regex = self._casilla(pagina, s, _("E&xpresión regular"), _("El texto es una expresión regular de Python."))
		self._codificaciones = [("automatica", _("Automática")), ("utf-8", "UTF-8"), ("utf-16", "UTF-16"), ("ansi", _("ANSI (Windows-1252)"))]
		_e, self.lista_codificacion = crear_campo(pagina, _("C&odificación:"), wx.Choice, choices=[t for _c, t in self._codificaciones],
			ayuda=_("Cómo se leen los archivos. Automática mira la marca BOM y si el texto es UTF-8; si no, ANSI."), sizer=s)
		self.lista_codificacion.SetSelection(0)
		self.casilla_no_contiene = self._casilla(pagina, s, _("Que &no contenga el texto"), _("Busca los archivos que NO contienen el texto."))
		self.casilla_nube = self._casilla(pagina, s, _("Leer también los archivos en la n&ube"),
			_("Los archivos de OneDrive no descargados se descargarían para leerlos; por eso, sin esta casilla, no se leen."))
		# 2.0 (3.5): extractores de texto de los complementos (PDF, DOCX, EPUB...).
		self.casilla_documentos = self._casilla(pagina, s, _("Buscar también dentro de docu&mentos"),
			_("Busca el texto también dentro de PDF, DOCX, EPUB y otros documentos que sepan leer los complementos instalados."))
		self.casilla_documentos.Enable(hay_extractores())
		pagina.SetSizer(s)
		self.libro.AddPage(pagina, _("Contenido"))

	def _crear_avanzado(self) -> None:
		pagina = wx.Panel(self.libro)
		s = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_minimo = crear_campo(pagina, _("Tamaño mí&nimo:"), wx.TextCtrl, ayuda=_("Vacío: sin mínimo. Se mide en la unidad elegida."), sizer=s)
		_e, self.campo_maximo = crear_campo(pagina, _("Tamaño má&ximo:"), wx.TextCtrl, ayuda=_("Vacío: sin máximo. Se mide en la unidad elegida."), sizer=s)
		_e, self.lista_unidad = crear_campo(pagina, _("&Unidad del tamaño:"), wx.Choice, choices=[u for u, _m in UNIDADES],
			ayuda=_("Unidad del tamaño mínimo y máximo."), sizer=s)
		self.lista_unidad.SetSelection(1)
		_e, self.campo_desde = crear_campo(pagina, _("Modi&ficado desde (día/mes/año):"), wx.TextCtrl,
			ayuda=_("Fecha de modificación más antigua, por ejemplo 01/01/2025. Vacío: sin límite."), sizer=s)
		_e, self.campo_hasta = crear_campo(pagina, _("Modificado ha&sta (día/mes/año):"), wx.TextCtrl,
			ayuda=_("Fecha de modificación más reciente (incluye todo ese día). Vacío: sin límite."), sizer=s)
		_e, self.campo_dias = crear_campo(pagina, _("Solo los ú&ltimos días (0 = no):"), wx.SpinCtrl, min=0, max=36500, initial=0,
			ayuda=_("Solo lo modificado en los últimos días indicados; 0 no limita."), sizer=s)
		self.casilla_ocultos = self._casilla(pagina, s, _("Incluir &ocultos y de sistema"),
			_("Busca también los archivos y carpetas ocultos o de sistema, y dentro de las carpetas ocultas."),
			bool(self._leer("busqueda.ocultos", False)))
		self._tipos = [(busqueda.ARCHIVOS, _("Archivos")), (busqueda.CARPETAS, _("Carpetas")), (busqueda.AMBOS, _("Archivos y carpetas"))]
		_e, self.lista_tipo = crear_campo(pagina, _("T&ipo de elemento:"), wx.Choice, choices=[t for _c, t in self._tipos],
			ayuda=_("Qué se busca: archivos, carpetas o los dos."), sizer=s)
		self.lista_tipo.SetSelection(0)
		self.casilla_comprimidos = self._casilla(pagina, s, _("Dentro de comprimidos &ZIP y TAR"),
			_("Busca también dentro de los archivos ZIP y TAR que encuentre (no en uno dentro de otro)."))
		# 2.0 (3.5): motores de búsqueda de los complementos (sin activarlos: nombres del manifiesto).
		self._motores = [("", _("El de zCommander")), *motores_de_complementos()]
		_e, self.lista_motor = crear_campo(pagina, _("&Motor de búsqueda:"), wx.Choice, choices=[n for _i, n in self._motores],
			ayuda=_("Quién busca: zCommander recorre las carpetas; un motor de un complemento usa su propio índice "
				"y solo mira los nombres."), sizer=s)
		self.lista_motor.SetSelection(0)
		pagina.SetSizer(s)
		self.libro.AddPage(pagina, _("Avanzado"))

	# ── Campos: criterios y búsquedas guardadas ─────────────────────────────────

	def _controles_guardables(self) -> dict[str, wx.Window]:
		"""Controles que se guardan en ``busquedas.json`` (por nombre, sección 10)."""
		return {
			"nombres": self.campo_nombres, "nombres_regex": self.casilla_nombres_regex, "buscar_en": self.campo_buscar_en,
			"fijas": self.casilla_fijas, "subcarpetas": self.casilla_subcarpetas, "profundidad": self.campo_profundidad,
			"texto": self.campo_texto, "mayusculas": self.casilla_mayusculas, "palabra": self.casilla_palabra,
			"texto_regex": self.casilla_texto_regex, "codificacion": self.lista_codificacion,
			"no_contiene": self.casilla_no_contiene, "nube": self.casilla_nube, "minimo": self.campo_minimo,
			"maximo": self.campo_maximo, "unidad": self.lista_unidad, "desde": self.campo_desde, "hasta": self.campo_hasta,
			"dias": self.campo_dias, "ocultos": self.casilla_ocultos, "tipo": self.lista_tipo, "comprimidos": self.casilla_comprimidos,
			"documentos": self.casilla_documentos,
		}

	def campos(self) -> dict:
		"""Valores de los controles por nombre (lo que se guarda)."""
		valores: dict = {}
		for nombre, control in self._controles_guardables().items():
			if isinstance(control, wx.Choice):
				valores[nombre] = control.GetSelection()
			else:
				valores[nombre] = control.GetValue()
		return valores

	def aplicar_campos(self, valores: dict) -> None:
		"""Rellena los controles; los nombres desconocidos o con un tipo raro se ignoran."""
		for nombre, control in self._controles_guardables().items():
			if nombre not in valores:
				continue
			valor = valores[nombre]
			try:
				if isinstance(control, wx.Choice):
					if isinstance(valor, int) and 0 <= valor < control.GetCount():
						control.SetSelection(valor)
				elif isinstance(control, wx.CheckBox):
					control.SetValue(bool(valor))
				elif isinstance(control, wx.SpinCtrl):
					control.SetValue(int(valor))
				else:
					control.SetValue(str(valor))
			except (TypeError, ValueError):
				log.warning("Valor no válido para %s en una búsqueda guardada: %r", nombre, valor)

	def criterios(self) -> Criterios:
		"""Criterios a partir de los controles.

		:raises ErrorCriterios: con un mensaje en español si algo está mal escrito.
		"""
		multiplicador = UNIDADES[max(0, self.lista_unidad.GetSelection())][1]
		minimo = leer_numero(self.campo_minimo.GetValue(), _("Tamaño mínimo"))
		maximo = leer_numero(self.campo_maximo.GetValue(), _("Tamaño máximo"))
		desde = leer_fecha(self.campo_desde.GetValue(), _("Modificado desde"))
		hasta = leer_fecha(self.campo_hasta.GetValue(), _("Modificado hasta"), fin_del_dia=True)
		dias = self.campo_dias.GetValue()
		if dias > 0:
			limite = time.time() - dias * 86400
			desde = max(desde or 0.0, limite)
		profundidad = self.campo_profundidad.GetValue()
		criterios = Criterios(
			nombres=self.campo_nombres.GetValue().strip() or "*",
			nombres_regex=self.casilla_nombres_regex.GetValue(),
			subcarpetas=self.casilla_subcarpetas.GetValue(),
			# N niveles de subcarpetas: recorrer cuenta 0 como «solo la carpeta», así que coincide con N.
			profundidad=profundidad if profundidad > 0 else None,
			texto=self.campo_texto.GetValue(),
			mayusculas=self.casilla_mayusculas.GetValue(),
			palabra_completa=self.casilla_palabra.GetValue(),
			texto_regex=self.casilla_texto_regex.GetValue(),
			codificacion=self._codificaciones[max(0, self.lista_codificacion.GetSelection())][0],
			no_contiene=self.casilla_no_contiene.GetValue(),
			tamano_min=int(minimo * multiplicador) if minimo is not None else None,
			tamano_max=int(maximo * multiplicador) if maximo is not None else None,
			desde=desde,
			hasta=hasta,
			ocultos=self.casilla_ocultos.GetValue(),
			que=self._tipos[max(0, self.lista_tipo.GetSelection())][0],
			comprimidos=self.casilla_comprimidos.GetValue(),
			nube=self.casilla_nube.GetValue(),
			max_resultados=int(self._leer("busqueda.max_resultados", 100000)),
			motor=self._motores[max(0, self.lista_motor.GetSelection())][0],
			dentro_de_documentos=self.casilla_documentos.IsEnabled() and self.casilla_documentos.GetValue(),
		)
		# Se compilan aquí para avisar antes de empezar de una expresión mal escrita.
		busqueda.compilar_nombres(criterios)
		busqueda.compilar_texto(criterios)
		return criterios

	def _refrescar_guardadas(self, elegir: str = "") -> None:
		self._guardadas = busqueda.cargar_guardadas()
		self.lista_guardadas.Set([b["nombre"] for b in self._guardadas])
		for indice, guardada in enumerate(self._guardadas):
			if guardada["nombre"] == elegir:
				self.lista_guardadas.SetSelection(indice)

	def cargar_guardada(self, indice: int | None = None) -> bool:
		indice = self.lista_guardadas.GetSelection() if indice is None else indice
		if not 0 <= indice < len(self._guardadas):
			return False
		self.aplicar_campos(self._guardadas[indice]["campos"])
		anuncios.anunciar(_("Cargada la búsqueda «{n}»").format(n=self._guardadas[indice]["nombre"]), anuncios.RESULTADO)
		return True

	def guardar_busqueda(self, nombre: str | None = None) -> bool:
		"""Guarda los criterios con un nombre (lo pide si no se da)."""
		if nombre is None:
			nombre = dialogos.pedir_texto(self, _("&Nombre de la búsqueda:"), _("Guardar búsqueda"),
				self.lista_guardadas.GetStringSelection())
		nombre = (nombre or "").strip()
		if not nombre:
			return False
		try:
			busqueda.guardar_busqueda(nombre, self.campos())
		except OSError as error:
			log.error("No se pudo guardar la búsqueda %s", nombre, exc_info=True)
			dialogos.mostrar_error(self, _("No se pudo guardar la búsqueda: {e}").format(e=error), _("Guardar búsqueda"))
			return False
		self._refrescar_guardadas(nombre)
		anuncios.anunciar(_("Búsqueda guardada: {n}").format(n=nombre), anuncios.RESULTADO)
		return True

	def borrar_guardada(self, confirmar: bool = True) -> bool:
		indice = self.lista_guardadas.GetSelection()
		if not 0 <= indice < len(self._guardadas):
			return False
		nombre = self._guardadas[indice]["nombre"]
		if confirmar and dialogos.confirmar(self, _("¿Borrar la búsqueda guardada «{n}»?").format(n=nombre),
				_("Borrar búsqueda"), peligroso=True) != wx.ID_YES:
			return False
		try:
			busqueda.borrar_busqueda(nombre)
		except OSError as error:
			log.error("No se pudo borrar la búsqueda %s", nombre, exc_info=True)
			dialogos.mostrar_error(self, _("No se pudo borrar la búsqueda: {e}").format(e=error), _("Borrar búsqueda"))
			return False
		self._refrescar_guardadas()
		anuncios.anunciar(_("Búsqueda borrada: {n}").format(n=nombre), anuncios.RESULTADO)
		return True

	def _al_tecla_guardadas(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and evento.GetModifiers() == wx.MOD_NONE:
			self.borrar_guardada()
			return
		evento.Skip()

	def _examinar(self) -> None:
		dialogo = wx.DirDialog(self, _("Buscar en"), self.campo_buscar_en.GetValue().split(";")[0].strip(), style=wx.DD_DEFAULT_STYLE)
		try:
			if dialogo.ShowModal() == wx.ID_OK:
				self.campo_buscar_en.SetValue(dialogo.GetPath())
		finally:
			dialogo.Destroy()
		self.campo_buscar_en.SetFocus()

	# ── Búsqueda ──────────────────────────────────────────────────────────────

	@property
	def buscando(self) -> bool:
		return self._tarea is not None and not self._tarea.terminada

	def buscar_o_detener(self) -> None:
		if self.buscando:
			self.detener()
		else:
			self.buscar()

	def raices_pedidas(self) -> tuple[list[str], bool]:
		"""(textos de «Buscar en», en todas las unidades fijas)."""
		textos = [t.strip() for t in self.campo_buscar_en.GetValue().split(";") if t.strip()]
		return textos, self.casilla_fijas.GetValue()

	def buscar(self) -> bool:
		"""Empieza la búsqueda en segundo plano. ``False`` si los criterios no valen (ya se ha avisado)."""
		if self.buscando:
			return False
		try:
			criterios = self.criterios()
			textos, fijas = self.raices_pedidas()
			if not textos and not fijas:
				raise ErrorCriterios(_("Escriba en «Buscar en» la carpeta donde buscar."))
		except ErrorCriterios as error:
			anuncios.anunciar(str(error), anuncios.ESENCIAL)
			self.campo_estado.SetValue(str(error))
			return False
		self._descartar_resultados()
		self._hilo = _EstadoHilo()
		self._inicio = time.monotonic()
		self.campo_estado.SetValue(_("Buscando..."))
		self.boton_buscar.SetLabel(_("&Detener"))
		self._actualizar_botones()
		estado_hilo = self._hilo
		self._tarea = self._tareas.enviar(
			_trabajo_buscar, textos, fijas, self._panel, criterios, estado_hilo,
			al_terminar=lambda estadisticas: self._al_terminar(estado_hilo, estadisticas),
			al_fallar=lambda error: self._al_fallar(estado_hilo, error),
			nombre="buscar-archivos",
		)
		if self._tarea is None:
			self._restablecer_boton()
			return False
		self._temporizador.Start(_INTERVALO_MS)
		anuncios.anunciar(_("Buscando"), anuncios.RESULTADO)
		return True

	def detener(self) -> None:
		if self.buscando:
			self._tarea.cancelar("Detener")
			self.campo_estado.SetValue(_("Deteniendo..."))

	def volcar(self, estado_hilo: _EstadoHilo | None = None) -> int:
		"""Pasa a la lista los resultados que el hilo ha dejado en la cola; devuelve cuántos."""
		estado_hilo = estado_hilo or self._hilo
		nuevos: list[Resultado] = []
		cola = estado_hilo.cola
		while cola:
			nuevos.append(cola.popleft())
		for resultado in nuevos:
			if resultado.proveedor.contenedor is not None and id(resultado.proveedor) not in self._comprimidos:
				self._comprimidos[id(resultado.proveedor)] = resultado.proveedor
		if nuevos and estado_hilo is self._hilo:
			self._resultados.extend(nuevos)
			self.lista.anadir([fila_de(r) for r in nuevos])
			self._actualizar_botones()
		if self.buscando and estado_hilo is self._hilo:
			n = formato.plural(len(self._resultados), _("{n} resultado"), _("{n} resultados"))
			revisando = estado_hilo.revisando
			self.campo_estado.SetValue(_("Buscando: {n}. En {c}").format(n=n, c=revisando) if revisando else _("Buscando: {n}").format(n=n))
		return len(nuevos)

	def _restablecer_boton(self) -> None:
		self._temporizador.Stop()
		self.boton_buscar.SetLabel(_("&Buscar"))
		self._actualizar_botones()

	def _al_terminar(self, estado_hilo: _EstadoHilo, estadisticas: busqueda.Estadisticas) -> None:
		if not self or estado_hilo is not self._hilo:
			return
		self.volcar(estado_hilo)
		self._tarea = None
		self._restablecer_boton()
		texto = busqueda.resumen(estadisticas)
		if not all(r.es_local for r in self._resultados):
			texto += ". " + _("Solo se pueden enviar resultados del disco")
		self.campo_estado.SetValue(texto)
		if estadisticas.errores:
			log.info("Búsqueda con %d errores; el primero: %s: %s", len(estadisticas.errores), *estadisticas.errores[0])
		if not self._cerrando:
			anuncios.anunciar(texto, anuncios.RESULTADO)

	def _al_fallar(self, estado_hilo: _EstadoHilo, error: BaseException) -> None:
		if not self or estado_hilo is not self._hilo:
			return
		from app.core.tareas import TareaCancelada

		self.volcar(estado_hilo)
		self._tarea = None
		self._restablecer_boton()
		if isinstance(error, TareaCancelada):
			parcial = busqueda.Estadisticas(encontrados=len(self._resultados))
			texto = busqueda.resumen(parcial, cancelada=True)
		else:
			texto = getattr(error, "mensaje", None) or str(error) or _("La búsqueda falló")
			if not isinstance(error, (ErrorCriterios, base.ErrorArchivos)):
				log.error("La búsqueda falló", exc_info=error)
		self.campo_estado.SetValue(texto)
		if not self._cerrando:
			anuncios.anunciar(texto, anuncios.RESULTADO if isinstance(error, TareaCancelada) else anuncios.ESENCIAL)

	def nueva_busqueda(self) -> None:
		self.detener()
		self._descartar_resultados()
		self.campo_estado.SetValue(_("Escriba qué buscar y pulse Buscar."))
		self.libro.SetSelection(0)
		dialogos.enfocar(self.campo_nombres)
		self._actualizar_botones()

	def _descartar_resultados(self) -> None:
		"""Vacía la lista y cierra los comprimidos abiertos por la búsqueda que nadie usa."""
		for clave, proveedor in list(self._comprimidos.items()):
			if clave not in self._entregados:
				try:
					proveedor.cerrar()
				except Exception:  # noqa: BLE001 - cerrar un comprimido no debe impedir seguir
					log.debug("No se pudo cerrar un proveedor de resultados", exc_info=True)
			del self._comprimidos[clave]
		self._resultados = []
		self.lista.limpiar()

	# ── Resultados ────────────────────────────────────────────────────────────

	@property
	def resultados(self) -> list[Resultado]:
		return list(self._resultados)

	def resultado_actual(self) -> Resultado | None:
		fila = self.lista.fila_actual()
		return self._resultados[fila] if 0 <= fila < len(self._resultados) else None

	def todos_locales(self) -> bool:
		return bool(self._resultados) and all(r.es_local for r in self._resultados)

	def _actualizar_botones(self) -> None:
		hay = bool(self._resultados)
		for boton in (self.boton_ver, self.boton_editar, self.boton_ir, self.boton_guardar):
			boton.Enable(hay)
		self.boton_enviar.Enable(self.todos_locales())
		self.boton_enviar.SetHelpText(
			_("Abre todos los resultados en el panel activo como una lista sobre la que funcionan todas las operaciones.")
			if not hay or self.todos_locales() else _("Solo se pueden enviar resultados del disco"))

	def _sin_resultado(self) -> None:
		anuncios.anunciar(_("No hay ningún resultado elegido"), anuncios.RESULTADO)

	def _entregar(self, resultado: Resultado) -> None:
		"""El proveedor de un comprimido pasa al panel: ya no lo cierra el diálogo."""
		if resultado.proveedor.contenedor is not None:
			self._entregados.add(id(resultado.proveedor))

	def ir_al_archivo(self) -> bool:
		resultado = self.resultado_actual()
		if resultado is None:
			self._sin_resultado()
			return False
		self._entregar(resultado)
		if self._al_ir is not None:
			self._al_ir(resultado)
		self.Close()
		return True

	def ver(self, editar: bool = False) -> bool:
		resultado = self.resultado_actual()
		if resultado is None:
			self._sin_resultado()
			return False
		if resultado.entrada.es_carpeta:
			anuncios.anunciar(_("Es una carpeta: use Ir al archivo"), anuncios.RESULTADO)
			return False
		self._entregar(resultado)
		if self._al_ver is not None:
			self._al_ver(resultado, editar)
		return True

	def titulo_lista(self) -> str:
		nombres = self.campo_nombres.GetValue().strip() or "*"
		texto = self.campo_texto.GetValue().strip()
		return _("Búsqueda: {n}, «{t}»").format(n=nombres, t=texto) if texto else _("Búsqueda: {n}").format(n=nombres)

	def enviar_al_panel(self) -> bool:
		if not self._resultados:
			self._sin_resultado()
			return False
		if not self.todos_locales():
			anuncios.anunciar(_("Solo se pueden enviar resultados del disco"), anuncios.RESULTADO)
			return False
		if self._al_enviar is not None:
			self._al_enviar(self.titulo_lista(), [r.ruta_local for r in self._resultados if r.ruta_local])
		self.Close()
		return True

	def guardar_resultados(self, ruta: str | None = None) -> bool:
		"""Guarda una ruta por línea (UTF-8 con BOM, para que el Bloc de notas lo abra bien)."""
		if not self._resultados:
			self._sin_resultado()
			return False
		if ruta is None:
			dialogo = wx.FileDialog(self, _("Guardar resultados"), defaultFile=_("resultados.txt"),
				wildcard=_("Texto (*.txt)|*.txt|Todos los archivos (*.*)|*.*"), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
			try:
				if dialogo.ShowModal() != wx.ID_OK:
					return False
				ruta = dialogo.GetPath()
			finally:
				dialogo.Destroy()
		contenido = busqueda.texto_resultados(self._resultados)
		n = len(self._resultados)

		def escribir(_tarea) -> None:
			with open(ruta, "w", encoding="utf-8-sig", newline="") as salida:
				salida.write(contenido)

		def listo(_r) -> None:
			anuncios.anunciar(_("Guardados {n} resultados en {r}").format(n=n, r=os.path.basename(ruta)), anuncios.RESULTADO)

		def fallo(error: BaseException) -> None:
			log.error("No se pudieron guardar los resultados en %s", ruta, exc_info=error)
			anuncios.anunciar(_("No se pudieron guardar los resultados: {e}").format(e=error), anuncios.ESENCIAL)

		self._tareas.enviar(escribir, al_terminar=listo, al_fallar=fallo, nombre="guardar-resultados")
		return True

	# ── Teclado y cierre ────────────────────────────────────────────────────────

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if modificadores == wx.MOD_NONE and tecla == wx.WXK_ESCAPE:
			if desplegable_abierto(wx.Window.FindFocus()):
				evento.Skip()
				return
			if self.buscando:
				self.detener()
			else:
				self.Close()
			return
		if modificadores == wx.MOD_NONE and tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and wx.Window.FindFocus() is self.lista:
			# Antes que el botón predeterminado (Buscar): Intro en la lista va al archivo.
			self.ir_al_archivo()
			return
		if modificadores == wx.MOD_NONE and tecla in (wx.WXK_F3, wx.WXK_F4):
			self.ver(editar=tecla == wx.WXK_F4)
			return
		evento.Skip()

	def _al_cerrar_ventana(self, evento: wx.CloseEvent) -> None:
		self._cerrando = True
		self._temporizador.Stop()
		if self.buscando:
			self._tarea.cancelar("Cerrar")
		self._descartar_resultados()
		if self._al_cerrar is not None:
			try:
				self._al_cerrar()
			except Exception:  # noqa: BLE001 - el diálogo se cierra aunque falle quien lo abrió
				log.exception("Falló el aviso de cierre de la búsqueda")
		self.Destroy()


	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		"""Si la ventana principal se cierra con la búsqueda abierta, el hilo también se para."""
		if evento.GetEventObject() is self:
			self._cerrando = True
			if self.buscando:
				self._tarea.cancelar("Cerrar")
		evento.Skip()


# ── Trabajo en el hilo ────────────────────────────────────────────────────────

def resolver_raices(textos: Sequence[str], fijas: bool, panel: tuple[base.Proveedor, str, str] | None) -> list[tuple[base.Proveedor, str]]:
	"""(proveedor, carpeta) de cada texto de «Buscar en». Toca el disco: SOLO en un hilo.

	:raises ErrorCriterios: si una carpeta no existe.
	"""
	local = resolver.proveedor_local()
	if fijas:
		from app.services.windows import unidades

		return [(local, letra + "\\") for letra in unidades.letras() if unidades.tipo_de(letra + "\\") == "fija"]
	raices: list[tuple[base.Proveedor, str]] = []
	for texto in textos:
		if panel is not None and texto == panel[2] and panel[0].esquema != "local":
			raices.append((panel[0].clonar(), panel[1]))
			continue
		ruta = rutas.normalizar(os.path.expandvars(texto))
		if not os.path.isdir(ruta):
			raise ErrorCriterios(_("No se encuentra la carpeta «{c}».").format(c=texto))
		raices.append((local, ruta))
	return raices


def _trabajo_buscar(tarea, textos, fijas, panel, criterios: Criterios, estado_hilo: _EstadoHilo) -> busqueda.Estadisticas:
	raices = resolver_raices(textos, fijas, panel)
	clones = {id(p) for p, _r in raices if panel is not None and p is not panel[0] and p.esquema != "local"}

	def al_revisar(carpeta: str) -> None:
		estado_hilo.revisando = carpeta

	def al_resultado(resultado: Resultado) -> None:
		# La búsqueda en un servidor usa su propia conexión (clonar), que se cierra al
		# terminar: los resultados se guardan con el proveedor del panel, que es el que sigue vivo.
		if id(resultado.proveedor) in clones:
			resultado = dataclasses.replace(resultado, proveedor=panel[0])
		estado_hilo.cola.append(resultado)

	try:
		return busqueda.buscar(raices, criterios, tarea.token, al_resultado, al_revisar)
	finally:
		for proveedor, _ruta in raices:
			if id(proveedor) in clones:
				try:
					proveedor.cerrar()
				except Exception:  # noqa: BLE001 - cerrar la conexión de la búsqueda no debe tapar el resultado
					log.debug("No se pudo cerrar la conexión de la búsqueda", exc_info=True)
