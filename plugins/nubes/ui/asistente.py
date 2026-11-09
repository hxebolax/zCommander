# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Asistente «Añadir una cuenta de nube» (diseño 2.0, 12.5): elegir servicio, datos, autorización, comprobación.

Tres diálogos sencillos en lugar de uno con páginas (cada uno pasa
``revisar_teclado`` por sí solo y el lector anuncia el título al abrirse):

- ``DialogoServicio``: lista con búsqueda; los servicios experimentales solo
  salen con ``mostrar_experimentales``.
- ``DialogoDatos``: nombre visible y los campos de la ficha del servicio, con
  letras de acceso asignadas sin repetir; las contraseñas se pueden mostrar.
- ``DialogoPregunta``: cualquier pregunta de rclone (``config/create`` sin
  interacción) con el control que toca según ``Type``, ``Exclusive``,
  ``Examples`` e ``IsPassword``: sí o no, lista, campo o contraseña.
"""

from __future__ import annotations

from typing import Any

import wx

from app.plugins import api

from ..cuentas import Catalogo, Servicio
from ..servicio import Paso
from . import comun

_ = api.traduccion("zc_nubes")[0]


class DialogoServicio(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, catalogo: Catalogo, experimentales: bool = False) -> None:
		super().__init__(zc, padre, _("Añadir una cuenta de nube: servicio"))
		self.catalogo = catalogo
		self.experimentales = experimentales
		self.visibles: list[Servicio] = []
		self.busqueda = comun.campo(zc, self.panel, _("&Buscar un servicio:"), wx.TextCtrl, sizer=self.sizer,
			ayuda=_("Escriba parte del nombre (drive, onedrive, s3...) para filtrar la lista."))
		self.lista = comun.lista(zc, self.panel, _("&Servicios:"), [(_("Servicio"), 240), (_("Descripción"), 420)], sizer=self.sizer,
			ayuda=_("Elija el servicio de la cuenta y pulse Siguiente."))
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
		comun.llenar_lista(self.lista, [[s.nombre, s.descripcion] for s in self.visibles])
		self._detalles()

	def elegido(self) -> Servicio | None:
		fila = comun.fila_actual(self.lista)
		return self.visibles[fila] if 0 <= fila < len(self.visibles) else None

	def _detalles(self) -> None:
		servicio = self.elegido()
		if servicio is None:
			self.detalles.SetValue(_("Ningún servicio coincide con la búsqueda."))
			return
		partes = [servicio.descripcion] if servicio.descripcion else []
		if servicio.experimental:
			partes.append(_("Experimental: puede fallar o dejar de funcionar."))
		partes.extend(servicio.avisos)
		self.detalles.SetValue("\n".join(partes))


class DialogoDatos(comun.DialogoNubes):
	"""Nombre visible y campos de la ficha del servicio."""

	def __init__(self, zc: Any, padre: wx.Window | None, servicio: Servicio, nombre: str = "", valores: dict[str, str] | None = None,
			*, guia: Any = None) -> None:
		super().__init__(zc, padre, _("Añadir una cuenta de {s}: datos").format(s=servicio.nombre))
		self.servicio = servicio
		self._valores = dict(valores or {})
		self._mostrar = False
		ocupadas = {"n", "i", "c", "m", "v", "g"}
		self.nombre = comun.campo(zc, self.panel, _("&Nombre visible:"), wx.TextCtrl, nombre or servicio.nombre, sizer=self.sizer,
			ayuda=_("Cómo se verá la cuenta en el selector de unidades, por ejemplo «Google Drive de Ana»."))
		self.etiquetas = {c["clave"]: comun.con_letra(str(c.get("etiqueta", c["clave"])), ocupadas) for c in servicio.campos}
		self.zona = wx.Panel(self.panel)
		self.zona.SetSizer(wx.BoxSizer(wx.VERTICAL))
		self.sizer.Add(self.zona, 0, wx.EXPAND)
		self.controles: dict[str, wx.Window] = {}
		self._construir_campos()
		if any(c.get("tipo") == "contrasena" for c in servicio.campos):
			self.mostrar = comun.casilla(self.panel, _("&Mostrar las contraseñas"), _("Muestra en claro lo escrito en los campos de contraseña."),
				sizer=self.sizer)
			self.mostrar.Bind(wx.EVT_CHECKBOX, lambda _e: self._alternar())
		avisos = list(servicio.avisos)
		if servicio.experimental:
			avisos.insert(0, _("Servicio experimental: puede fallar o dejar de funcionar sin previo aviso."))
		if avisos:
			comun.texto_solo_lectura(zc, self.panel, _("A&visos:"), "\n".join(avisos), sizer=self.sizer, alto=70)
		if servicio.guia and guia is not None:
			comun.boton(self.panel, _("&Guía para conectar Google Drive"), _("Abre la guía paso a paso para crear su identificador."),
				guia, sizer=self.sizer)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		siguiente = comun.boton(self.panel, _("S&iguiente"), _("Comprueba los datos y sigue con la autorización."), self._siguiente,
			sizer=fila)
		comun.boton(self.panel, _("&Cancelar"), _("Cierra el asistente sin añadir nada."), sizer=fila, identificador=wx.ID_CANCEL)
		siguiente.SetDefault()
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.terminar(self.nombre)

	def _construir_campos(self) -> None:
		sizer = self.zona.GetSizer()
		for campo in self.servicio.campos:
			clave = campo["clave"]
			etiqueta = self.etiquetas[clave]
			ayuda = str(campo.get("ayuda", ""))
			valor = self._valores.get(clave, str(campo.get("defecto", "")))
			tipo = campo.get("tipo", "texto")
			if tipo == "opcion":
				opciones = [(str(o[0]), str(o[1])) for o in campo.get("opciones", [])]
				control = comun.elegir(self.zc, self.zona, etiqueta, opciones, valor, ayuda=ayuda, sizer=sizer)
			elif tipo == "bool":
				control = comun.casilla(self.zona, etiqueta, ayuda, valor in ("true", "1", "sí"), sizer=sizer)
			else:
				estilo = wx.TE_PASSWORD if tipo == "contrasena" and not self._mostrar else 0
				control = comun.campo(self.zc, self.zona, etiqueta, wx.TextCtrl, valor, ayuda=ayuda, sizer=sizer, style=estilo)
			self.controles[clave] = control

	def _alternar(self) -> None:
		"""Rehace los campos con o sin ocultar las contraseñas (cada etiqueta sigue justo antes de su control)."""
		self._valores = self.valores()
		self._mostrar = self.mostrar.GetValue()
		self.zona.DestroyChildren()
		self.zona.GetSizer().Clear()
		self.controles.clear()
		self._construir_campos()
		self.panel.Layout()
		self.GetSizer().Fit(self)
		primera = next((c for c in self.servicio.campos if c.get("tipo") == "contrasena"), None)
		if primera is not None:
			self.controles[primera["clave"]].SetFocus()

	def valores(self) -> dict[str, str]:
		resultado = {}
		for clave, control in self.controles.items():
			if isinstance(control, wx.Choice):
				resultado[clave] = comun.valor_elegido(control)
			elif isinstance(control, wx.CheckBox):
				resultado[clave] = "true" if control.GetValue() else "false"
			else:
				resultado[clave] = control.GetValue().strip()
		return resultado

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
		if self.IsModal():
			self.EndModal(wx.ID_OK)


class DialogoPregunta(comun.DialogoNubes):
	"""Una pregunta de rclone con su control (sí o no, lista, campo, contraseña o token pegado)."""

	def __init__(self, zc: Any, padre: wx.Window | None, paso: Paso, servicio: str = "") -> None:
		super().__init__(zc, padre, _("Añadir una cuenta de nube: pregunta de rclone"))
		self.paso = paso
		texto = paso.ayuda or paso.nombre
		if paso.error:
			texto = _("La respuesta anterior no valió: {e}").format(e=paso.error) + "\n\n" + texto
		if servicio:
			texto = f"{servicio}. {texto}"
		comun.texto_solo_lectura(zc, self.panel, _("&Pregunta:"), texto, sizer=self.sizer, alto=110,
			ayuda=_("Lo que pregunta rclone (en inglés si el servicio no tiene traducción)."))
		ayuda = _("Respuesta a la pregunta de rclone.")
		if paso.es_booleana:
			opciones = [("true", _("Sí")), ("false", _("No"))]
			self.control: wx.Window = comun.elegir(zc, self.panel, _("&Respuesta:"), opciones, (paso.defecto or "false").lower(),
				ayuda=ayuda, sizer=self.sizer)
		elif paso.exclusiva:
			self.control = comun.elegir(zc, self.panel, _("&Respuesta:"), [(v, f"{t} ({v})" if t != v else v) for v, t in paso.ejemplos],
				paso.defecto, ayuda=ayuda, sizer=self.sizer)
		elif paso.ejemplos:
			self.control = comun.campo(zc, self.panel, _("&Respuesta:"), wx.ComboBox, paso.defecto, ayuda=ayuda, sizer=self.sizer,
				choices=[v for v, _t in paso.ejemplos])
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
		return self.control.GetValue().strip()
