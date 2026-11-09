# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Asistente «Añadir una cuenta de nube» (diseño 2.0, 12.5): carpetas del equipo, servicio, datos, autorización.

Diálogos sencillos en lugar de uno con páginas (cada uno pasa
``revisar_teclado`` por sí solo y el lector anuncia el título al abrirse):

- ``DialogoCarpetas``: primer paso si este equipo ya tiene carpetas de los
  programas oficiales (OneDrive, Dropbox, Google Drive para escritorio,
  iCloud...): las anuncia y deja elegir cuáles salen en el selector de unidades,
  sin iniciar sesión.
- ``DialogoServicio``: lista con búsqueda y la columna «Cómo se conecta»
  (navegador, correo y contraseña, carpeta del programa oficial o avanzado);
  los servicios experimentales solo salen con ``mostrar_experimentales``.
- ``DialogoDatos``: nombre visible y los campos de la ficha. En los servicios de
  navegador no hay nada más que escribir: «Siguiente» y la espera de siempre. Los
  identificadores propios y «Autorizar desde otro equipo» están en «Opciones
  avanzadas...» (``DialogoAvanzadas``).
- ``DialogoPregunta``: cualquier pregunta de rclone (``config/create`` sin
  interacción), traducida al español si se conoce (``preguntas.py``), con el
  control que toca según ``Type``, ``Exclusive``, ``Examples`` e ``IsPassword``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx

from app.plugins import api

from .. import preguntas
from ..cuentas import Catalogo, Servicio, texto_metodo
from ..locales import CarpetaNube, nombres_para_frase
from ..servicio import OTRO_EQUIPO, Paso, unidad_kdrive_valida
from . import comun

_ = api.traduccion("zc_nubes")[0]

#: Código de cierre de ``DialogoCarpetas`` cuando la persona quiere seguir y añadir una cuenta (un entero:
#: ningún botón lo usa como identificador).
CARPETAS_SEGUIR = wx.ID_FORWARD
#: Servicios de navegador que rclone no deja autorizar desde otro equipo.
SIN_OTRO_EQUIPO = frozenset({"jottacloud"})


def _valores_de(controles: dict[str, wx.Window]) -> dict[str, str]:
	resultado = {}
	for clave, control in controles.items():
		if isinstance(control, wx.Choice):
			resultado[clave] = comun.valor_elegido(control)
		elif isinstance(control, wx.CheckBox):
			resultado[clave] = "true" if control.GetValue() else "false"
		else:
			resultado[clave] = control.GetValue().strip()
	return resultado


def _crear_campos(zc: Any, padre: wx.Window, sizer: wx.Sizer, campos: tuple[dict[str, Any], ...], etiquetas: dict[str, str],
		valores: dict[str, str], mostrar: bool = False) -> dict[str, wx.Window]:
	"""Etiqueta y control de cada campo de una ficha, en orden (la etiqueta siempre justo antes)."""
	controles: dict[str, wx.Window] = {}
	for campo in campos:
		clave = campo["clave"]
		etiqueta = etiquetas[clave]
		ayuda = str(campo.get("ayuda", ""))
		valor = valores.get(clave, str(campo.get("defecto", "")))
		tipo = campo.get("tipo", "texto")
		if tipo == "opcion":
			opciones = [(str(o[0]), str(o[1])) for o in campo.get("opciones", [])]
			control = comun.elegir(zc, padre, etiqueta, opciones, valor, ayuda=ayuda, sizer=sizer)
		elif tipo == "bool":
			control = comun.casilla(padre, etiqueta, ayuda, valor in ("true", "1", "sí"), sizer=sizer)
		else:
			estilo = wx.TE_PASSWORD if tipo == "contrasena" and not mostrar else 0
			control = comun.campo(zc, padre, etiqueta, wx.TextCtrl, valor, ayuda=ayuda, sizer=sizer, style=estilo)
		controles[clave] = control
	return controles


def _etiqueta_enlace(texto: str) -> str:
	"""Botón del enlace de la ficha con la letra P (reservada en los datos): «Abrir la &página...»."""
	texto = (texto or _("Abrir la página del servicio")).replace("&", "")
	posicion = texto.casefold().find("p")
	return texto[:posicion] + "&" + texto[posicion:] if posicion >= 0 else _("Abrir la &página del servicio")


class DialogoCarpetas(comun.DialogoNubes):
	"""Primer paso: las carpetas de los programas oficiales de nube que ya hay en este equipo."""

	def __init__(self, zc: Any, padre: wx.Window | None, carpetas: list[CarpetaNube], marcadas: list[bool] | None = None) -> None:
		super().__init__(zc, padre, _("Añadir una cuenta de nube: carpetas de este equipo"))
		self.carpetas = list(carpetas)
		marcadas = list(marcadas) if marcadas is not None else [True] * len(self.carpetas)
		texto = _("Este equipo ya tiene {n}. ¿Usar sus carpetas sin iniciar sesión?").format(n=nombres_para_frase(self.carpetas))
		texto += "\n\n" + _("Las carpetas marcadas saldrán en el selector de unidades (Alt+F1 y Alt+F2) como un disco más. Hace falta "
			"que el programa oficial siga instalado y con la sesión iniciada. Así no hay enlaces para compartir, ni papelera de la "
			"nube, ni espacio de la cuenta, y abrir un archivo que solo está en la nube hace que el programa lo descargue primero. "
			"Si necesita eso, pulse «Añadir además una cuenta de nube».")
		self.explicacion = comun.texto_solo_lectura(zc, self.panel, _("&Qué hay en este equipo:"), texto, sizer=self.sizer, alto=130,
			ayuda=_("Lo que ha encontrado zCommander y qué se puede hacer con ello."))
		self.lista = comun.lista(zc, self.panel, _("Carpetas que se &muestran en el selector de unidades:"),
			[(_("Carpeta"), 200), (_("Programa"), 130), (_("Ruta"), 320)], sizer=self.sizer, con_casillas=True,
			ayuda=_("Marque con Espacio las carpetas que quiere ver en el selector de unidades; las no marcadas no salen."))
		comun.llenar_lista(self.lista, [[c.nombre, c.proveedor, c.ruta] for c in self.carpetas])
		anterior = getattr(self.lista, "_anunciar_casillas", None)
		if anterior is not None:
			self.lista._anunciar_casillas = False   # sin «marcada» por cada fila al abrir
		try:
			for fila, marcada in enumerate(marcadas[:len(self.carpetas)]):
				self.lista.CheckItem(fila, bool(marcada))
		finally:
			if anterior is not None:
				self.lista._anunciar_casillas = anterior
		fila_botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_usar = comun.boton(self.panel, _("&Usar estas carpetas"),
			_("Guarda la elección y cierra el asistente: las carpetas marcadas ya están en el selector de unidades."), sizer=fila_botones,
			identificador=wx.ID_OK)
		comun.boton(self.panel, _("&Añadir además una cuenta de nube..."),
			_("Guarda la elección y sigue con la lista de servicios para iniciar sesión en una cuenta."),
			lambda: self.EndModal(CARPETAS_SEGUIR) if self.IsModal() else None, sizer=fila_botones)
		comun.boton(self.panel, _("&Cancelar"), _("Cierra el asistente sin cambiar nada."), sizer=fila_botones, identificador=wx.ID_CANCEL)
		self.boton_usar.SetDefault()
		self.sizer.Add(fila_botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.terminar(self.explicacion)

	def elegidas(self) -> list[CarpetaNube]:
		return [c for fila, c in enumerate(self.carpetas) if self.lista.IsItemChecked(fila)]


class DialogoServicio(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, catalogo: Catalogo, experimentales: bool = False) -> None:
		super().__init__(zc, padre, _("Añadir una cuenta de nube: servicio"))
		self.catalogo = catalogo
		self.experimentales = experimentales
		self.visibles: list[Servicio] = []
		self.busqueda = comun.campo(zc, self.panel, _("&Buscar un servicio:"), wx.TextCtrl, sizer=self.sizer,
			ayuda=_("Escriba parte del nombre (drive, onedrive, icloud, s3...) para filtrar la lista."))
		self.lista = comun.lista(zc, self.panel, _("&Servicios:"),
			[(_("Servicio"), 240), (_("Cómo se conecta"), 220), (_("Descripción"), 420)], sizer=self.sizer,
			ayuda=_("Los servicios van agrupados por cómo se conectan: primero los que solo piden iniciar sesión en el navegador, "
				"después los de correo y contraseña, las carpetas de los programas oficiales y, al final, los avanzados, que piden "
				"claves. Elija uno y pulse Siguiente."))
		self.detalles = comun.texto_solo_lectura(zc, self.panel, _("&Detalles:"), "", sizer=self.sizer, alto=80,
			ayuda=_("Descripción y avisos del servicio elegido."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_siguiente = comun.boton(self.panel, _("S&iguiente"), _("Pasa a los datos de la cuenta."), sizer=fila,
			identificador=wx.ID_OK)
		comun.boton(self.panel, _("&Cancelar"), _("Cierra el asistente sin añadir nada."), sizer=fila, identificador=wx.ID_CANCEL)
		self.boton_siguiente.SetDefault()
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.busqueda.Bind(wx.EVT_TEXT, lambda _e: self.filtrar())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self._detalles())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.EndModal(wx.ID_OK) if self.IsModal() else None)
		self.filtrar()
		self.terminar(self.lista)

	def filtrar(self) -> None:
		self.visibles = self.catalogo.buscar(self.busqueda.GetValue(), self.experimentales)
		comun.llenar_lista(self.lista, [[s.nombre, texto_metodo(s.como_se_conecta), s.descripcion] for s in self.visibles])
		self._detalles()

	def elegido(self) -> Servicio | None:
		fila = comun.fila_actual(self.lista)
		return self.visibles[fila] if 0 <= fila < len(self.visibles) else None

	def _detalles(self) -> None:
		servicio = self.elegido()
		if servicio is None:
			self.detalles.SetValue(_("Ningún servicio coincide con la búsqueda."))
			return
		partes = [_("Cómo se conecta: {m}.").format(m=texto_metodo(servicio.como_se_conecta))]
		if servicio.descripcion:
			partes.append(servicio.descripcion)
		if servicio.experimental:
			partes.append(_("Experimental: puede fallar o dejar de funcionar."))
		partes.extend(servicio.avisos)
		self.detalles.SetValue("\n".join(partes))


class DialogoAvanzadas(comun.DialogoNubes):
	"""Opciones avanzadas de un alta: identificador de cliente propio y autorizar desde otro equipo."""

	def __init__(self, zc: Any, padre: wx.Window | None, servicio: Servicio, valores: dict[str, str] | None = None, *,
			guia: Callable[[], None] | None = None) -> None:
		super().__init__(zc, padre, _("Opciones avanzadas de {s}").format(s=servicio.nombre))
		self.servicio = servicio
		valores = dict(valores or {})
		ocupadas = {"a", "c", "o", "g", "p"}
		self.explicacion = comun.texto_solo_lectura(zc, self.panel, _("&Para qué sirven:"),
			_("Normalmente no hace falta nada de esto: basta con iniciar sesión en el navegador. Use un identificador de cliente "
				"propio solo si su organización lo exige o si ya tiene uno. Autorizar desde otro equipo sirve cuando este no tiene "
				"navegador."), sizer=self.sizer, alto=70, ayuda=_("Para qué sirven estas opciones y cuándo hacen falta."))
		campos = servicio.avanzadas_alta
		self.etiquetas = {c["clave"]: comun.con_letra(str(c.get("etiqueta", c["clave"])), ocupadas) for c in campos}
		self.controles = _crear_campos(zc, self.panel, self.sizer, campos, self.etiquetas, valores)
		self.otro_equipo: wx.CheckBox | None = None
		if servicio.es_oauth and servicio.tipo not in SIN_OTRO_EQUIPO:
			self.otro_equipo = comun.casilla(self.panel, _("Autorizar desde &otro equipo (este no tiene navegador)"),
				_("zCommander le dará una orden de rclone para ejecutarla en un equipo con navegador y un campo para pegar lo que "
					"escriba al terminar."), valores.get(OTRO_EQUIPO) == "true", sizer=self.sizer)
		if servicio.guia and guia is not None:
			comun.boton(self.panel, _("&Guía para crear su identificador"), _("Abre la guía paso a paso para crear su identificador."),
				guia, sizer=self.sizer)
		self.botones(wx.OK | wx.CANCEL)
		primero = next(iter(self.controles.values()), None) or self.otro_equipo or self.explicacion
		self.terminar(primero)

	def valores(self) -> dict[str, str]:
		resultado = _valores_de(self.controles)
		if self.otro_equipo is not None:
			resultado[OTRO_EQUIPO] = "true" if self.otro_equipo.GetValue() else "false"
		return resultado


class DialogoDatos(comun.DialogoNubes):
	"""Nombre visible y campos de la ficha del servicio; lo avanzado, aparte."""

	def __init__(self, zc: Any, padre: wx.Window | None, servicio: Servicio, nombre: str = "", valores: dict[str, str] | None = None,
			*, guia: Callable[[], None] | None = None, abrir_enlace: Callable[[str], Any] | None = None) -> None:
		super().__init__(zc, padre, _("Añadir una cuenta de {s}: datos").format(s=servicio.nombre))
		self.servicio = servicio
		self._valores = dict(valores or {})
		self._avanzadas: dict[str, str] = {}
		self._guia = guia
		self._mostrar = False
		ocupadas = {"n", "i", "c", "m", "v", "o", "p"}
		self.nombre = comun.campo(zc, self.panel, _("&Nombre visible:"), wx.TextCtrl, nombre or servicio.nombre, sizer=self.sizer,
			ayuda=_("Cómo se verá la cuenta en el selector de unidades, por ejemplo «Google Drive de Ana»."))
		self.etiquetas = {c["clave"]: comun.con_letra(str(c.get("etiqueta", c["clave"])), ocupadas) for c in servicio.campos}
		self.zona = wx.Panel(self.panel)
		self.zona.SetSizer(wx.BoxSizer(wx.VERTICAL))
		self.sizer.Add(self.zona, 0, wx.EXPAND)
		self.controles: dict[str, wx.Window] = {}
		self._construir_campos()
		self.mostrar: wx.CheckBox | None = None
		if any(c.get("tipo") == "contrasena" for c in servicio.campos):
			self.mostrar = comun.casilla(self.panel, _("&Mostrar las contraseñas"),
				_("Muestra en claro lo escrito en los campos de contraseña."), sizer=self.sizer)
			self.mostrar.Bind(wx.EVT_CHECKBOX, lambda _e: self._alternar())
		avisos = list(servicio.avisos)
		if servicio.experimental:
			avisos.insert(0, _("Servicio experimental: puede fallar o dejar de funcionar sin previo aviso."))
		if servicio.tipo == "drive":
			avisos.insert(0, _("No hay que escribir nada más: al pulsar Siguiente, zCommander le preguntará cómo quiere conectar "
				"Google Drive."))
		elif servicio.como_se_conecta == "navegador" and not servicio.campos:
			avisos.insert(0, _("No hay que escribir nada más: pulse Siguiente para iniciar sesión en el navegador."))
		if avisos:
			comun.texto_solo_lectura(zc, self.panel, _("A&visos:"), "\n".join(avisos), sizer=self.sizer, alto=70)
		if servicio.enlace.get("url", "").startswith("https://") and abrir_enlace is not None:
			url = servicio.enlace["url"]
			comun.boton(self.panel, _etiqueta_enlace(servicio.enlace.get("texto", "")),
				_("Abre en el navegador la página que se necesita para conectar: {u}").format(u=url), lambda: abrir_enlace(url),
				sizer=self.sizer)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_avanzadas: wx.Button | None = None
		if servicio.avanzadas_alta or (servicio.es_oauth and servicio.tipo not in SIN_OTRO_EQUIPO):
			self.boton_avanzadas = comun.boton(self.panel, _("&Opciones avanzadas..."),
				_("Identificador de cliente propio y autorizar desde otro equipo. Normalmente no hace falta."), self._abrir_avanzadas,
				sizer=fila)
		siguiente = comun.boton(self.panel, _("S&iguiente"), _("Comprueba los datos y sigue con la autorización."), self._siguiente,
			sizer=fila)
		comun.boton(self.panel, _("&Cancelar"), _("Cierra el asistente sin añadir nada."), sizer=fila, identificador=wx.ID_CANCEL)
		siguiente.SetDefault()
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.terminar(self.nombre)

	def _construir_campos(self) -> None:
		self.controles = _crear_campos(self.zc, self.zona, self.zona.GetSizer(), self.servicio.campos, self.etiquetas, self._valores,
			self._mostrar)

	def _alternar(self) -> None:
		"""Rehace los campos con o sin ocultar las contraseñas (cada etiqueta sigue justo antes de su control)."""
		self._valores = _valores_de(self.controles)
		self._mostrar = bool(self.mostrar and self.mostrar.GetValue())
		self.zona.DestroyChildren()
		self.zona.GetSizer().Clear()
		self.controles.clear()
		self._construir_campos()
		self.panel.Layout()
		self.GetSizer().Fit(self)
		primera = next((c for c in self.servicio.campos if c.get("tipo") == "contrasena"), None)
		if primera is not None:
			self.controles[primera["clave"]].SetFocus()

	def _abrir_avanzadas(self) -> None:
		dialogo = DialogoAvanzadas(self.zc, self, self.servicio, self._avanzadas, guia=self._guia)
		try:
			if comun.mostrar_modal(self.zc, dialogo) == wx.ID_OK:
				self._avanzadas = dialogo.valores()
		finally:
			dialogo.Destroy()

	def valores(self) -> dict[str, str]:
		return {**_valores_de(self.controles), **self._avanzadas}

	def nombre_visible(self) -> str:
		return self.nombre.GetValue().strip()

	def _siguiente(self) -> None:
		if not self.nombre_visible():
			comun.error(self.zc, _("Escriba un nombre visible para la cuenta."))
			self.nombre.SetFocus()
			return
		valores = self.valores()
		for campo in self.servicio.campos:
			if campo.get("obligatorio") and not valores.get(campo["clave"]):
				comun.error(self.zc, _("Falta un dato: {c}").format(c=self.etiquetas[campo["clave"]].replace("&", "").rstrip(":")))
				self.controles[campo["clave"]].SetFocus()
				return
			if campo.get("validar") == "unidad_kdrive" and valores.get(campo["clave"]) and not unidad_kdrive_valida(
					valores[campo["clave"]]):
				comun.error(self.zc, _("El número de la unidad kDrive son solo cifras, por ejemplo 456789. Cópielo de la dirección web "
					"de kDrive, detrás de «drive/», o pegue la dirección entera."))
				self.controles[campo["clave"]].SetFocus()
				return
		if self.IsModal():
			self.EndModal(wx.ID_OK)


class DialogoPregunta(comun.DialogoNubes):
	"""Una pregunta de rclone con su control (sí o no, lista, campo, contraseña o token pegado)."""

	def __init__(self, zc: Any, padre: wx.Window | None, paso: Paso, servicio: str = "") -> None:
		super().__init__(zc, padre, _("Añadir una cuenta de nube: pregunta"))
		self.paso = paso
		self._textos: dict[str, str] = {}
		texto, ejemplos, _traducida = preguntas.traducir_paso(paso)
		if paso.error:
			texto = _("La respuesta anterior no valió: {e}").format(e=paso.error) + "\n\n" + texto
		if servicio:
			texto = f"{servicio}. {texto}"
		self.pregunta = comun.texto_solo_lectura(zc, self.panel, _("&Pregunta:"), texto, sizer=self.sizer, alto=110,
			ayuda=_("Lo que pregunta rclone, en español si es una de sus preguntas habituales y en inglés si no."))
		ayuda = _("Respuesta a la pregunta.")
		if paso.es_booleana:
			opciones = [("true", _("Sí")), ("false", _("No"))]
			self.control: wx.Window = comun.elegir(zc, self.panel, _("&Respuesta:"), opciones, (paso.defecto or "false").lower(),
				ayuda=ayuda, sizer=self.sizer)
		elif paso.exclusiva:
			self.control = comun.elegir(zc, self.panel, _("&Respuesta:"), [(v, f"{t} ({v})" if t != v else v) for v, t in ejemplos],
				paso.defecto, ayuda=ayuda, sizer=self.sizer)
		elif paso.ejemplos:
			# Lista abierta (se puede escribir otro valor): se ve «texto (valor)», nunca solo un identificador en bruto.
			self._textos = {(f"{t} ({v})" if t and t != v else v): v for v, t in ejemplos}
			inicial = next((texto for texto, valor in self._textos.items() if valor == paso.defecto), paso.defecto)
			self.control = comun.campo(zc, self.panel, _("&Respuesta:"), wx.ComboBox, inicial, ayuda=ayuda, sizer=self.sizer,
				choices=list(self._textos))
		elif paso.es_token:
			self.control = comun.campo(zc, self.panel, _("&Respuesta:"), wx.TextCtrl, "", ayuda=ayuda, sizer=self.sizer,
				style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(520, 100)))
		else:
			estilo = wx.TE_PASSWORD if paso.es_contrasena else 0
			self.control = comun.campo(zc, self.panel, _("&Respuesta:"), wx.TextCtrl, "" if paso.es_contrasena else paso.defecto,
				ayuda=ayuda, sizer=self.sizer, style=estilo)
		self.botones(wx.OK | wx.CANCEL)
		self.terminar(self.control)

	def respuesta(self) -> str:
		if isinstance(self.control, wx.Choice):
			return comun.valor_elegido(self.control)
		texto = self.control.GetValue().strip()
		return self._textos.get(texto, texto)
