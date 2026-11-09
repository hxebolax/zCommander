# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Preferencias de zCommander (Ctrl+coma): el diálogo 2.0 con árbol de páginas (diseño 2.0, 10.18).

Lo hereda de la plantilla (``app/ui/dialogo_preferencias.py``, del núcleo):
etiquetas antes de cada control, Ctrl+H, validar todo antes de guardar,
Aceptar, Cancelar y Aplicar. Aquí se añade lo propio de zCommander:

- **Árbol de páginas** (``wx.Treebook``, árbol nativo): General, Paneles, Vista,
  Accesibilidad, Sonidos, Operaciones, Visor y editor, Búsqueda, Red,
  Comprimidos, Actualizaciones, Personalización, Confirmaciones y el nodo
  Complementos con una página por complemento con configuración. Con el foco
  en el árbol, las flechas cambian de página; Ctrl+Tab y Ctrl+Mayús+Tab
  también desde los controles.
- **Páginas declarativas** desde ``DESCRIPCIONES`` y ``PAGINAS`` (una opción nueva
  aparece sola) y desde los ``[[configuracion]]`` de los manifiestos de los
  complementos (las páginas de PL, ``pl_preferencias``), SIN activar ningún complemento.
- **Páginas propias** de ``paginas_propias.PAGINAS_PROPIAS`` (Sonidos de SO,
  Confirmaciones de PE) con su protocolo ``PaginaPropia``; y los botones de
  ``BOTONES_PAGINA`` al final de su página («Teclas globales...»).
- **Buscar una opción** (10.14): al escribir, una lista con las opciones cuyo
  nombre o ayuda contienen el texto (también las de complementos), con su
  página; Intro lleva a la página y pone el foco en el control.
- **Letras de acceso sin repetir por página**, contando los botones del diálogo
  y el buscador; **Valores de fábrica de esta página** (no de todo).
- Los desplegables muestran nombres en español, no los valores internos.

``abrir(padre, config, pagina=None)`` es el punto de entrada (también de
``zc.preferencias.abrir``): ``pagina`` es el título de una página o
``complemento:<id>``.
"""

from __future__ import annotations

import builtins
import dataclasses
import logging
from collections.abc import Callable
from typing import Any

import wx
import wx.lib.scrolledpanel as scrolled

from app.core import descripciones_config
from app.core.configuracion import Configuracion, ErrorValidacion
from app.ui import dialogo_preferencias as plantilla
from app.ui import paginas_propias
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


#: Nombre visible de cada valor de las claves con lista cerrada.
NOMBRES_OPCIONES: dict[str, dict[Any, str]] = {
	"general.consola": {"cmd": N_("Símbolo del sistema (cmd)"), "powershell": N_("PowerShell"), "terminal": N_("Windows Terminal")},
	"paneles.formato_fecha": {"corta": N_("Corta (8/11/2026 14:05)"), "larga": N_("Larga, con segundos"), "iso": N_("ISO (2026-11-08 14:05)")},
	"paneles.formato_tamano": {"legible": N_("Legible (1,2 MB)"), "bytes": N_("En bytes (1.234.567)"), "mixto": N_("Mixto (bytes hasta 1 MB)")},
	"paneles.orientacion": {"vertical": N_("Lado a lado"), "horizontal": N_("Uno encima de otro")},
	"paneles.marcas_como": {
		"seleccion": N_("Como selección de la lista (el lector dice «seleccionado»)"),
		"columna": N_("En la columna Marca (el lector solo lo dice una vez)"),
	},
	"vista.tema": {"sistema": N_("Sistema (colores de Windows)"), "norton": N_("Norton clásico"), "alto_contraste": N_("Alto contraste")},
	"accesibilidad.detalle": {"breve": N_("Breve"), "normal": N_("Normal"), "detallado": N_("Detallado")},
	"accesibilidad.progreso_voz": {"hitos": N_("Cada 25 %"), "inicio_fin": N_("Al empezar y al terminar"), "final": N_("Solo al terminar")},
	"accesibilidad.salida_voz": {
		"automatica": N_("Automática"), "lector": N_("Siempre por el lector de pantalla"),
		"uia": N_("Siempre por notificaciones de Windows"), "ninguna": N_("Ninguna"),
	},
	"operaciones.politica_conflicto": {
		"preguntar": N_("Preguntar"), "sobrescribir": N_("Sobrescribir"), "omitir": N_("Omitir"),
		"sobrescribir_si_mas_antiguo": N_("Sobrescribir si es más antiguo"),
		"sobrescribir_si_cambia_tamano": N_("Sobrescribir si cambia el tamaño"),
		"renombrar_copia": N_("Renombrar la copia"), "renombrar_existente": N_("Renombrar el que ya existe"),
	},
	"visor.codificacion": {
		"automatica": N_("Automática"), "utf-8": N_("UTF-8"), "utf-16-le": N_("UTF-16 (Windows, little endian)"),
		"utf-16-be": N_("UTF-16 big endian"), "cp1252": N_("Windows (ANSI, 1252)"), "latin-1": N_("Latín 1 (ISO-8859-1)"),
		"cp850": N_("OEM (MS-DOS Europa, 850)"), "cp437": N_("OEM (MS-DOS EE. UU., 437)"),
	},
	"registro.nivel": {"DEBUG": N_("Depuración"), "INFO": N_("Información"), "WARNING": N_("Avisos"), "ERROR": N_("Errores")},
	"teclado.esquema": {"norton": N_("Norton Commander"), "total_commander": N_("Total Commander"), "far": N_("Far Manager"),
		"explorador": N_("Explorador de Windows")},
	"sonidos.progreso": {"no": N_("No"), "cada_25": N_("Cada 25 %"), "cada_10": N_("Cada 10 %")},
	"comprimidos.metodo_zip": {"deflate": N_("Deflate (el de siempre)"), "zstd": N_("Zstandard (más rápido)"), "almacenar": N_("Sin comprimir")},
	"actualizaciones.fuente": {
		"servidor": N_("Servidor de zCommander (xebolax.synology.me)"), "github": N_("GitHub (hxebolax/zCommander)"),
		"ambas": N_("Las dos: la que tenga la versión más nueva"), "personalizada": N_("Una dirección personalizada"),
	},
}

#: Opciones que solo se pueden cambiar con cierto valor de otra: ``{dependiente: (clave que manda, valores que la habilitan)}``.
#: Deshabilitada, el lector la anuncia «no disponible» y Tab la salta; su ayuda (Ctrl+H) explica cuándo se usa.
DEPENDENCIAS: dict[str, tuple[str, tuple[Any, ...]]] = {
	"actualizaciones.url_personalizada": ("actualizaciones.fuente", ("personalizada",)),
}

ETIQUETA_FABRICA = N_("&Valores de fábrica de esta página")
#: Botones del diálogo (fuera de las páginas): sus letras no las puede usar ninguna opción.
ETIQUETAS_BOTONES = (ETIQUETA_FABRICA, "&Aceptar", "&Cancelar", "A&plicar")
ETIQUETA_BUSCAR = N_("Busca&r una opción:")
ETIQUETA_RESULTADOS = N_("Opciones q&ue coinciden:")
#: Lo que hay fuera de las páginas además de los botones (el buscador): tampoco se repite en ellas.
ETIQUETAS_FUERA = (*ETIQUETAS_BOTONES, ETIQUETA_BUSCAR, ETIQUETA_RESULTADOS)
TITULO_COMPLEMENTOS = N_("Complementos")
TITULO_CONFIRMACIONES = N_("Confirmaciones")
TITULO_PERSONALIZACION = N_("Personalización")
PREFIJO_COMPLEMENTO = "complemento:"


def nombre_opcion(clave: str, valor: Any) -> str:
	return _(NOMBRES_OPCIONES.get(clave, {}).get(valor, str(valor)))


def _tipo(config: Configuracion, clave: str) -> str | None:
	"""Tipo de control según el valor de fábrica y la regla; ``None`` si no se edita aquí."""
	defecto = config.valor_por_defecto(clave)
	regla = config.regla(clave)
	if regla is not None and regla.opciones:
		return plantilla.OPCION
	if isinstance(defecto, bool):
		return plantilla.BOOL
	if isinstance(defecto, int):
		return plantilla.ENTERO
	if isinstance(defecto, str):
		return plantilla.TEXTO
	# Decimales, listas y diccionarios tienen su propio diálogo (o son internos).
	return None


def _letras_fuera(titulo: str) -> set[str]:
	usadas = f_comun.letras_de(_(e) for e in ETIQUETAS_FUERA)
	usadas |= f_comun.letras_de(_(e) for e, _r in paginas_propias.BOTONES_PAGINA.get(titulo, []))
	return usadas


def construir_paginas(config: Configuracion, descripciones: dict | None = None,
		paginas: tuple = descripciones_config.PAGINAS) -> tuple[plantilla.Pagina, ...]:
	"""Una ``Pagina`` por sección de ``PAGINAS`` con sus opciones en el orden de ``DESCRIPCIONES``.

	Las etiquetas salen ya traducidas y con letras de acceso únicas en la página
	(contando los botones del diálogo, el buscador y los botones extra de la página).
	"""
	descripciones = descripciones_config.DESCRIPCIONES if descripciones is None else descripciones
	conocidas = set(config.claves())
	resultado = []
	for id_pagina, titulo in paginas:
		usadas = _letras_fuera(titulo)
		opciones: list[plantilla.Opcion] = []
		for clave, (etiqueta, ayuda, pagina) in descripciones.items():
			if pagina != id_pagina:
				continue
			if clave not in conocidas:
				log.warning("La descripción «%s» no tiene valor de fábrica; no se muestra", clave)
				continue
			tipo = _tipo(config, clave)
			if tipo is None:
				log.debug("«%s» no es editable en Preferencias (tipo %s)", clave, type(config.valor_por_defecto(clave)).__name__)
				continue
			valores = ()
			if tipo == plantilla.OPCION:
				valores = tuple((v, nombre_opcion(clave, v)) for v in config.regla(clave).opciones)
			opciones.append(plantilla.Opcion(clave, _(etiqueta), tipo, _(ayuda), opciones=valores))
		if opciones or titulo in paginas_propias.BOTONES_PAGINA:
			etiquetas = f_comun.repartir_letras([o.etiqueta for o in opciones], usadas)
			opciones = [dataclasses.replace(o, etiqueta=e) for o, e in zip(opciones, etiquetas, strict=True)]
			resultado.append(plantilla.Pagina(_(titulo), tuple(opciones)))
	return tuple(resultado)


# ── Diálogo ─────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class _InfoPagina:
	titulo: str
	tipo: str  # «declarativa», «propia», «complemento»
	panel: wx.Window
	propia: Any = None
	complemento: str = ""
	#: Claves (``[[configuracion]]``) de una página de complemento, para el buscador.
	declaraciones: list = dataclasses.field(default_factory=list)


class DialogoPreferenciasZ(plantilla.DialogoPreferencias):
	"""Preferencias 2.0 con ``wx.Treebook``, páginas propias, páginas de complementos y buscador."""

	def __init__(self, padre: wx.Window | None, config: Configuracion, anunciar: Callable[[str], None] | None = None,
			pagina_inicial: int = 0, pagina: str | None = None) -> None:
		# Sin proveedor de ayuda, SetHelpText no guarda nada. Se instala uno si falta.
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		wx.Dialog.__init__(self, padre, title=_("Preferencias"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self._config = config
		self._secretos = None
		self._anunciar = anunciar
		self._controles: dict[str, tuple[plantilla.Opcion, wx.Window, int]] = {}
		self._clave_por_id: dict[int, str] = {}
		self._valores_secretos: dict[str, str] = {}
		self._info: list[_InfoPagina] = []
		self._resultados: list[tuple[str, int]] = []
		self._nodos_complementos: dict[str, int] = {}
		self.paginas = construir_paginas(config)

		sizer = wx.BoxSizer(wx.VERTICAL)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.etiqueta_buscar = wx.StaticText(self, label=_(ETIQUETA_BUSCAR))
		self.buscar = wx.TextCtrl(self, name=f_comun.texto_limpio(_(ETIQUETA_BUSCAR)))
		self.buscar.SetHelpText(_("Escriba parte del nombre o de la ayuda de una opción (por ejemplo «papelera»). "
			"Flecha abajo pasa a la lista de opciones que coinciden; Intro lleva a la primera."))
		fila.Add(self.etiqueta_buscar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		fila.Add(self.buscar, 1, wx.EXPAND)
		sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 8)
		self.etiqueta_resultados = wx.StaticText(self, label=_(ETIQUETA_RESULTADOS))
		self.resultados = wx.ListBox(self, size=self.FromDIP(wx.Size(-1, 70)), name=f_comun.texto_limpio(_(ETIQUETA_RESULTADOS)))
		self.resultados.SetHelpText(_("Opciones que coinciden con lo buscado, con su página. Intro lleva a la opción."))
		sizer.Add(self.etiqueta_resultados, 0, wx.LEFT | wx.RIGHT, 8)
		sizer.Add(self.resultados, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

		self.libro = wx.Treebook(self)
		self._construir_paginas()
		self._letras_del_buscador()
		self._enlazar_dependencias()
		sizer.Add(self.libro, 1, wx.EXPAND | wx.ALL, 8)

		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_restablecer = wx.Button(self, label=_(ETIQUETA_FABRICA))
		self.boton_aceptar = wx.Button(self, wx.ID_OK, _("&Aceptar"))
		self.boton_cancelar = wx.Button(self, wx.ID_CANCEL, _("&Cancelar"))
		self.boton_aplicar = wx.Button(self, wx.ID_APPLY, _("A&plicar"))
		self.boton_restablecer.SetHelpText(_(
			"Pone las opciones de la página visible con sus valores de fábrica. No se guarda nada hasta Aplicar o Aceptar."))
		botones.Add(self.boton_restablecer, 0, wx.ALL, 4)
		botones.AddStretchSpacer()
		for boton in (self.boton_aceptar, self.boton_cancelar, self.boton_aplicar):
			botones.Add(boton, 0, wx.ALL, 4)
		sizer.Add(botones, 0, wx.EXPAND | wx.ALL, 4)
		self.SetSizerAndFit(sizer)
		self.SetMinSize(self.FromDIP(wx.Size(640, 520)))
		self.boton_aceptar.SetDefault()
		self.SetEscapeId(wx.ID_CANCEL)
		self.boton_aceptar.Bind(wx.EVT_BUTTON, self._al_aceptar)
		self.boton_cancelar.Bind(wx.EVT_BUTTON, self._al_cancelar)
		self.boton_aplicar.Bind(wx.EVT_BUTTON, self._al_aplicar)
		self.boton_restablecer.Bind(wx.EVT_BUTTON, self._al_restablecer)
		self.buscar.Bind(wx.EVT_TEXT, lambda _e: self.filtrar())
		self.buscar.Bind(wx.EVT_KEY_DOWN, self._al_tecla_buscar)
		self.resultados.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.ir_al_resultado())
		self.resultados.Bind(wx.EVT_KEY_DOWN, self._al_tecla_resultados)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self.Bind(wx.EVT_INIT_DIALOG, self._al_iniciar)
		arbol = self.libro.GetTreeCtrl()
		if arbol is not None:
			from app.ui.accesibilidad.nombres import asignar_nombre_accesible

			asignar_nombre_accesible(arbol, _("Páginas de las preferencias"))
			arbol.SetHelpText(_("Páginas de preferencias. Las flechas cambian de página; Control+Tab y Control+Mayúsculas+Tab "
				"también desde los controles."))
		self.libro.SetHelpText(_("Páginas de preferencias. Control+Tab y Control+Mayúsculas+Tab cambian de página."))
		self.CentreOnParent()
		indice = self.indice_de(pagina) if pagina else (pagina_inicial if 0 < pagina_inicial < self.libro.GetPageCount() else None)
		self.pagina_pedida_encontrada = pagina is None or indice is not None
		if indice is not None:
			self.libro.SetSelection(indice)

	# ── Construcción ─────────────────────────────────────────────────────────

	def _construir_paginas(self) -> None:
		titulos_propias = set(paginas_propias.PAGINAS_PROPIAS)
		declarativas = {p.titulo: p for p in self.paginas}
		for _id, titulo in descripciones_config.PAGINAS:
			if titulo in titulos_propias:
				self._anadir_propia(titulo)
			elif _(titulo) in declarativas:
				self._anadir_declarativa(declarativas[_(titulo)], titulo)
			elif titulo == TITULO_COMPLEMENTOS:
				self._anadir_vacia(titulo)
			if titulo == TITULO_PERSONALIZACION and TITULO_CONFIRMACIONES in titulos_propias:
				self._anadir_propia(TITULO_CONFIRMACIONES)
			if titulo == TITULO_COMPLEMENTOS:
				self._anadir_complementos()

	def _letras_del_buscador(self) -> None:
		"""Letras del buscador que no use ninguna página (las de complementos y de otros bloques no se eligen aquí).

		Se prefieren R y U (las que las páginas del núcleo ya dejan libres); si una página propia o de un
		complemento las usa, el buscador toma otra letra de su texto que no esté en ninguna página.
		"""
		from app.ui.accesibilidad.revision_teclado import letra_de_acceso

		ocupadas = set(f_comun.letras_de(_(e) for e in ETIQUETAS_BOTONES))

		def recorrer(ventana: wx.Window) -> None:
			for hijo in ventana.GetChildren():
				etiqueta = hijo.GetLabel() if isinstance(hijo, (wx.StaticText, wx.Button, wx.CheckBox, wx.RadioButton)) else ""
				letra = letra_de_acceso(etiqueta) if etiqueta else None
				if letra:
					ocupadas.add(letra)
				recorrer(hijo)

		for info in self._info:
			recorrer(info.panel)
		for control, etiqueta in ((self.etiqueta_buscar, ETIQUETA_BUSCAR), (self.etiqueta_resultados, ETIQUETA_RESULTADOS)):
			texto = _(etiqueta)
			letra = letra_de_acceso(texto)
			if letra and letra not in ocupadas:
				ocupadas.add(letra)
				continue
			nueva = f_comun.poner_letra(texto.replace("&", ""), ocupadas)
			control.SetLabel(nueva)
			ocupadas |= f_comun.letras_de([nueva])

	def _anadir(self, panel: wx.Window, titulo: str, info: _InfoPagina, hija: bool = False) -> int:
		indice = len(self._info)
		self._info.append(info)
		if hija:
			self.libro.AddSubPage(panel, titulo)
		else:
			self.libro.AddPage(panel, titulo)
		return indice

	def _anadir_declarativa(self, pagina: plantilla.Pagina, titulo_original: str) -> None:
		indice = len(self._info)
		panel = self._crear_pagina(pagina, indice)
		self._botones_extra(panel, titulo_original)
		self._anadir(panel, pagina.titulo, _InfoPagina(pagina.titulo, "declarativa", panel))

	def _anadir_vacia(self, titulo: str) -> None:
		panel = scrolled.ScrolledPanel(self.libro)
		caja = wx.BoxSizer(wx.VERTICAL)
		texto = wx.StaticText(panel, label=_("Las páginas de los complementos están debajo de esta en el árbol."))
		caja.Add(texto, 0, wx.ALL, 6)
		panel.SetSizer(caja)
		self._anadir(panel, _(titulo), _InfoPagina(_(titulo), "declarativa", panel))

	def _botones_extra(self, panel: wx.Window, titulo: str) -> None:
		for etiqueta, referencia in paginas_propias.BOTONES_PAGINA.get(titulo, []):
			boton = wx.Button(panel, label=_(etiqueta))
			boton.SetHelpText(f_comun.texto_limpio(_(etiqueta)))
			boton.Bind(wx.EVT_BUTTON, lambda _e, r=referencia: self._llamar_boton(r))
			panel.GetSizer().Add(boton, 0, wx.ALL, 6)
		panel.Layout()

	def _llamar_boton(self, referencia: str) -> None:
		try:
			paginas_propias.importar(referencia)(self)
		except Exception:  # noqa: BLE001 - un botón de un bloque roto no tumba Preferencias
			log.exception("Falló el botón de Preferencias %s", referencia)
			f_comun.avisar(self, _("No se pudo abrir: los detalles están en el registro."), _("Preferencias"))

	def _anadir_propia(self, titulo: str) -> None:
		try:
			pagina = paginas_propias.crear_pagina(titulo, self.libro, self._config)
		except Exception:  # noqa: BLE001 - una página propia rota no impide abrir Preferencias
			log.exception("No se pudo crear la página propia %s", titulo)
			from app.ui.dialogos._pagina_provisional import PaginaProvisional

			pagina = PaginaProvisional(self.libro, _(titulo))
		self._anadir(pagina, _(titulo), _InfoPagina(_(titulo), "propia", pagina, propia=pagina))

	def _anadir_complementos(self) -> None:
		"""Bajo «Complementos», un nodo por complemento con configuración y una hija por cada una de sus páginas.

		Las páginas las hace PL (``pl_preferencias.crear``, protocolo ``PaginaPropia``) sin activar el complemento.
		"""
		try:
			from app.ui.dialogos import pl_preferencias

			nodos = pl_preferencias.nodos()
		except Exception:  # noqa: BLE001 - sin las páginas de PL, Preferencias se abre igual
			log.exception("No se pudieron leer las páginas de los complementos")
			return
		for nodo in nodos:
			for id_pagina, titulo in (("", nodo.nombre), *nodo.paginas):
				try:
					pagina = pl_preferencias.crear(self.libro, self._config, nodo.id, id_pagina)
				except Exception:  # noqa: BLE001 - un complemento con una página rota no impide abrir Preferencias
					log.exception("No se pudo crear la página %s de %s", id_pagina, nodo.id)
					continue
				info = _InfoPagina(titulo, "propia", pagina, propia=pagina, complemento=nodo.id if not id_pagina else "",
					declaraciones=pl_preferencias.declaraciones_de_pagina(nodo.id, id_pagina))
				indice = len(self._info)
				self._info.append(info)
				if id_pagina:
					# Bajo el nodo del complemento: como se añade enseguida, queda la última y su índice es el siguiente.
					self.libro.InsertSubPage(self._nodos_complementos[nodo.id], pagina, titulo)
				else:
					self.libro.AddSubPage(pagina, titulo)
				if not id_pagina:
					self._nodos_complementos[nodo.id] = indice

	# ── Opciones que dependen de otra ─────────────────────────────────────────

	def _enlazar_dependencias(self) -> None:
		"""Cada opción de ``DEPENDENCIAS`` se habilita solo con los valores que la usan (y al momento al cambiarlos)."""
		for clave, (maestra, _valores) in DEPENDENCIAS.items():
			if clave not in self._controles or maestra not in self._controles:
				continue
			control = self._controles[maestra][1]
			evento = wx.EVT_CHOICE if isinstance(control, wx.Choice) else wx.EVT_CHECKBOX
			control.Bind(evento, self._al_cambiar_maestra)
		self.actualizar_dependencias()

	def _al_cambiar_maestra(self, evento: wx.CommandEvent) -> None:
		self.actualizar_dependencias()
		evento.Skip()

	def actualizar_dependencias(self) -> None:
		"""Habilita o deshabilita las opciones dependientes según el valor que tienen ahora los controles."""
		for clave, (maestra, valores) in DEPENDENCIAS.items():
			if clave not in self._controles or maestra not in self._controles:
				continue
			opcion, control, _pagina = self._controles[maestra]
			habilitar = self._leer_control(opcion, control) in valores
			dependiente = self._controles[clave][1]
			if dependiente.IsEnabled() != habilitar:
				dependiente.Enable(habilitar)

	def _validar_cruzado(self) -> tuple[str, str] | None:
		"""Comprobaciones entre opciones: ``(clave del control que hay que corregir, motivo)`` o ``None``.

		2.0.1: con «Una dirección personalizada» la dirección es obligatoria; vacía, la
		comprobación de actualizaciones fallaría siempre sin que nadie lo notase.
		"""
		if "actualizaciones.fuente" in self._controles and "actualizaciones.url_personalizada" in self._controles:
			opcion, control, _pagina = self._controles["actualizaciones.fuente"]
			opcion_url, control_url, _pagina_url = self._controles["actualizaciones.url_personalizada"]
			if (self._leer_control(opcion, control) == "personalizada"
					and not str(self._leer_control(opcion_url, control_url) or "").strip()):
				return "actualizaciones.url_personalizada", _(
					"Con «Una dirección personalizada» hay que escribir la dirección del archivo version.json, "
					"completa y empezando por https://. Si no tiene una, elija otro origen de las actualizaciones.")
		return None

	def _senalar(self, clave: str, mensaje: str) -> None:
		# Un valor no válido en una opción deshabilitada se tiene que poder corregir.
		control = self._controles[clave][1]
		if not control.IsEnabled():
			control.Enable(True)
		super()._senalar(clave, mensaje)

	# ── Páginas y búsqueda ────────────────────────────────────────────────────

	def indice_de(self, pagina: str) -> int | None:
		"""Índice de una página por su título (con o sin traducir) o ``complemento:<id>``."""
		if pagina.startswith(PREFIJO_COMPLEMENTO):
			buscado = pagina[len(PREFIJO_COMPLEMENTO):]
			return next((i for i, info in enumerate(self._info) if info.complemento == buscado), None)
		clave = f_comun.normalizar_busqueda(_(pagina))
		return next((i for i, info in enumerate(self._info) if f_comun.normalizar_busqueda(info.titulo) == clave), None)

	def titulos(self) -> list[str]:
		return [info.titulo for info in self._info]

	def buscar_opciones(self, texto: str) -> list[tuple[str, int]]:
		"""(clave, página) de las opciones cuyo nombre o ayuda contienen todas las palabras de ``texto``."""
		palabras = f_comun.normalizar_busqueda(texto).split()
		if not palabras:
			return []
		resultado = []
		for clave, (opcion, _control, pagina) in self._controles.items():
			texto_opcion = f_comun.normalizar_busqueda(f"{opcion.etiqueta} {opcion.ayuda}".replace("&", ""))
			if all(p in texto_opcion for p in palabras):
				resultado.append((clave, pagina))
		for indice, info in enumerate(self._info):
			if info.tipo != "propia":
				continue
			textos = [info.titulo, *(f"{d.get('etiqueta', '')} {d.get('ayuda', '')}" for d in info.declaraciones)]
			if any(all(p in f_comun.normalizar_busqueda(t.replace("&", "")) for p in palabras) for t in textos):
				resultado.append(("", indice))
		return resultado

	def filtrar(self) -> None:
		self._resultados = self.buscar_opciones(self.buscar.GetValue())
		textos = []
		for clave, pagina in self._resultados:
			titulo_pagina = self._info[pagina].titulo
			if clave:
				nombre = f_comun.texto_limpio(self._controles[clave][0].etiqueta).rstrip(":")
				textos.append(_("{o} (página {p})").format(o=nombre, p=titulo_pagina))
			else:
				textos.append(_("Página {p}").format(p=titulo_pagina))
		self.resultados.Set(textos)
		if textos:
			self.resultados.SetSelection(0)
		if self._anunciar is not None and self.buscar.GetValue().strip():
			from app.ui import anuncios

			anuncios.anunciar(_("{n} opciones").format(n=len(textos)) if textos else _("Ninguna opción coincide"), anuncios.DETALLE)

	def ir_al_resultado(self, indice: int | None = None) -> bool:
		indice = self.resultados.GetSelection() if indice is None else indice
		if not 0 <= indice < len(self._resultados):
			return False
		clave, pagina = self._resultados[indice]
		self.libro.SetSelection(pagina)
		if clave:
			control = self._controles[clave][1]
			if not control.IsEnabled() and clave in DEPENDENCIAS:
				# Deshabilitada: el foco va a la opción que la habilita (su ayuda lo explica).
				control = self._controles.get(DEPENDENCIAS[clave][0], (None, control))[1]
			control.SetFocus()
		else:
			self._enfocar_pagina(pagina)
		return True

	def _enfocar_pagina(self, indice: int) -> None:
		info = self._info[indice]
		if info.tipo == "propia":
			control = info.propia.control_inicial()
		else:
			control = next((c for _o, c, p in self._controles.values() if p == indice), None)
		if control is not None:
			control.SetFocus()

	def _al_tecla_buscar(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		if codigo == wx.WXK_DOWN and self._resultados:
			self.resultados.SetFocus()
			return
		if codigo in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and self._resultados:
			self.ir_al_resultado(0)
			return
		evento.Skip()

	def _al_tecla_resultados(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			self.ir_al_resultado()
			return
		evento.Skip()

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_TAB and evento.ControlDown():
			total = self.libro.GetPageCount()
			if total:
				paso = -1 if evento.ShiftDown() else 1
				nueva = (self.libro.GetSelection() + paso) % total
				self.libro.SetSelection(nueva)
				self._enfocar_pagina(nueva)
			return
		super()._al_tecla(evento)

	# ── Valores ────────────────────────────────────────────────────────────────

	def opciones_de_pagina(self, indice: int) -> list[str]:
		return [clave for clave, (_o, _c, pagina) in self._controles.items() if pagina == indice]

	def control_inicial(self) -> wx.Window | None:
		"""La primera opción de la página que se abre (o el árbol si la página no tiene controles)."""
		indice = max(0, self.libro.GetSelection())
		if 0 <= indice < len(self._info):
			info = self._info[indice]
			if info.tipo == "propia":
				return info.propia.control_inicial()
			control = next((c for _o, c, p in self._controles.values() if p == indice), None)
			if control is not None:
				return control
		return self.libro.GetTreeCtrl() or self.buscar

	def aplicar(self) -> bool:
		"""Valida todo (núcleo, páginas propias y de complementos) y después guarda lo que cambió."""
		cambios: dict[str, Any] = {}
		for clave, (opcion, control, _pagina) in self._controles.items():
			try:
				valor = self._leer_control(opcion, control)
				self._config.validar(clave, valor)
				if valor != self._config.obtener(clave, None):
					cambios[clave] = valor
			except ErrorValidacion as error:
				self._senalar(clave, str(error))
				return False
		error = self._validar_cruzado()
		if error is not None:
			self._senalar(*error)
			return False
		for indice, info in enumerate(self._info):
			if info.tipo != "propia":
				continue
			error = info.propia.validar()
			if error:
				self.libro.SetSelection(indice)
				plantilla.mostrar_aviso(self, error, _("Valor no válido"))
				info.propia.control_inicial().SetFocus()
				return False
		try:
			if cambios:
				self._config.establecer_varias(cambios)
		except Exception as error:  # noqa: BLE001 - ErrorConfiguracion, OSError...: se informa a la persona
			log.exception("No se pudieron guardar las preferencias")
			plantilla.mostrar_aviso(self, _("No se pudieron guardar las preferencias: %s") % error, _("Error"))
			return False
		for indice, info in enumerate(self._info):
			if info.tipo == "propia" and not info.propia.aplicar():
				self.libro.SetSelection(indice)
				plantilla.mostrar_aviso(self, _("No se pudo guardar la página {p}.").format(p=info.titulo), _("Error"))
				return False
		log.info("Preferencias aplicadas: %d cambios del núcleo", len(cambios))
		if self._anunciar is not None and cambios:
			self._anunciar(_("Preferencias guardadas."))
		return True

	def restablecer_pagina(self, indice: int) -> None:
		"""Valores de fábrica en los controles de una página (sin guardar)."""
		info = self._info[indice]
		if info.tipo == "propia":
			info.propia.restablecer()
			return
		for clave in self.opciones_de_pagina(indice):
			opcion, control, _pagina = self._controles[clave]
			self._escribir_control(opcion, control, self._config.valor_por_defecto(clave))
		self.actualizar_dependencias()

	def _al_restablecer(self, _evento: wx.CommandEvent | None) -> None:
		indice = self.libro.GetSelection()
		titulo = self._info[indice].titulo if 0 <= indice < len(self._info) else ""
		if not f_comun.preguntar(self, _("¿Poner las opciones de la página {p} con sus valores de fábrica? "
				"No se guardará nada hasta que pulse Aplicar o Aceptar.").format(p=titulo), _("Valores de fábrica")):
			return
		self.restablecer_pagina(indice)
		self._enfocar_pagina(indice)
		if self._anunciar is not None:
			self._anunciar(_("Valores de fábrica puestos en la página {p}. Pulse Aceptar para guardarlos.").format(p=titulo))


def mostrar(padre: wx.Window | None, config: Configuracion, anunciar: Callable[[str], None] | None = None,
		pagina: str | None = None) -> bool:
	"""Abre las preferencias; ``True`` si se cerró con Aceptar."""
	dialogo = DialogoPreferenciasZ(padre, config, anunciar, pagina=pagina)
	if not dialogo.pagina_pedida_encontrada:
		from app.ui import anuncios

		anuncios.anunciar(_("Página no disponible: {p}").format(p=pagina), anuncios.ESENCIAL)
	return f_comun.mostrar(dialogo, lambda _d: True) is True


def abrir(padre: wx.Window | None, config: Configuracion, pagina: str | None = None) -> None:
	"""Punto de entrada del diálogo de Preferencias (diseño 2.0, 10.18).

	:param pagina: título de una página («Sonidos», «Personalización») o ``complemento:<id>``;
		si no existe, se abre en la primera y se anuncia «Página no disponible».
	"""
	from app.ui import anuncios

	mostrar(padre, config, anunciar=lambda texto: anuncios.anunciar(texto, anuncios.RESULTADO), pagina=pagina)
