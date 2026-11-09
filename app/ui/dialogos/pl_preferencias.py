# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Páginas de Preferencias declarativas de los complementos (diseño 2.0, 3.6 y 10.18). Bloque PL.

Cada complemento con ``[[configuracion]]`` (o con ``dialogo_preferencias = true``)
tiene un nodo «Complementos > <nombre>» en Preferencias: su página propia con las
claves que no nombran una página declarada, y una página hija por cada
``[[paginas]]``. Cada clave no interna se muestra con el control de su tipo y la
etiqueta que escribió el autor (con su letra de acceso), creada ANTES del control.

Las páginas cumplen el protocolo ``PaginaPropia`` (``validar``, ``aplicar``,
``restablecer``, ``control_inicial``), así que participan en Aceptar, Cancelar,
Aplicar y «Valores de fábrica de esta página» del diálogo de Preferencias de PE
igual que las páginas propias del núcleo. Guardan en la configuración propia del
complemento (``data/config/plugins/<id>.json``) y NUNCA activan el complemento
para pintarse; «Abrir la configuración avanzada...» sí lo activa (3.6).

Contrato para el diálogo de Preferencias (PE): ``nodos()`` da los nodos y sus
páginas; ``crear(padre, config, id_complemento, pagina)`` crea cada página. Mientras
ese diálogo no las muestre, el gestor de complementos abre las de un complemento
con ``abrir_dialogo`` («Configurar»).
"""

from __future__ import annotations

import builtins
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import wx

from app.plugins import config_plugins, registro
from app.plugins import estado as estado_complementos
from app.plugins.estado import EstadoComplemento
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo

log = logging.getLogger(__name__)

#: Letras de los botones del diálogo de Preferencias (Aceptar, Cancelar, Aplicar, Valores de fábrica) y de su
#: buscador (2.0, 10.18: «Busca&r una opción:» y «Opciones q&ue coinciden:»): ninguna clave de un
#: complemento puede usarlas (lo comprueba ``tools/validar_plugin.py``).
LETRAS_DIALOGO = frozenset({"a", "c", "p", "v", "r", "u"})
ETIQUETA_AVANZADA = "Abrir la configuración avanzada..."


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class NodoComplemento:
	"""Un complemento en el árbol de Preferencias: ``paginas`` son (id de página, título)."""

	id: str
	nombre: str
	paginas: tuple[tuple[str, str], ...]
	dialogo: bool


def _declaraciones(id_complemento: str) -> list[dict]:
	return [d for d in config_plugins.registro().declaraciones(id_complemento) if not d.get("interna")]


def nodos() -> list[NodoComplemento]:
	"""Complementos con algo que configurar (sin activar ninguno), por nombre."""
	resultado = []
	for registrado in registro.complementos():
		if registrado.estado in (EstadoComplemento.ERROR_MANIFIESTO, EstadoComplemento.INCOMPATIBLE):
			continue
		datos = registrado.manifiesto
		paginas = tuple((str(p["id"]), str(p.get("titulo", p["id"]))) for p in datos.tabla("paginas") if p.get("id"))
		if not _declaraciones(datos.id) and not datos.dialogo_preferencias:
			continue
		resultado.append(NodoComplemento(datos.id, datos.nombre, paginas, datos.dialogo_preferencias))
	return resultado


def declaraciones_de_pagina(id_complemento: str, pagina: str = "") -> list[dict]:
	"""Claves no internas de una página; ``pagina`` vacía = el nodo del complemento (claves sin página declarada)."""
	registrado = registro.complemento(id_complemento)
	declaradas = {str(p.get("id")) for p in registrado.manifiesto.tabla("paginas")} if registrado else set()
	resultado = []
	for declaracion in _declaraciones(id_complemento):
		suya = str(declaracion.get("pagina", "") or "")
		if (pagina and suya == pagina) or (not pagina and suya not in declaradas):
			resultado.append(declaracion)
	return resultado


def _letra(etiqueta: str) -> str | None:
	from app.ui.accesibilidad.revision_teclado import letra_de_acceso

	return letra_de_acceso(etiqueta)


def abrir_avanzada(padre: wx.Window | None, id_complemento: str) -> None:
	"""Pide la activación (3.4) y, al terminar, llama en la interfaz al diálogo que registró el complemento."""
	from app.plugins import cargador
	from app.ui import anuncios, paginas_propias

	futuro = cargador.asegurar_activo(id_complemento)
	nombre = estado_complementos.nombre_de(id_complemento)

	def continuar() -> None:
		try:
			ok = bool(futuro.result())
		except Exception:  # noqa: BLE001 - cancelado al cerrar o con error
			ok = False
		funcion = paginas_propias.dialogo_complemento(id_complemento) if ok else None
		if funcion is None:
			anuncios.anunciar(_("El complemento {n} no tiene configuración avanzada").format(n=nombre), anuncios.RESULTADO)
			return
		with estado_complementos.pausa_modal():
			estado_complementos.llamar_protegido(id_complemento, funcion, padre)

	futuro.add_done_callback(lambda _f: cargador.planificar(continuar))


class PaginaComplemento(wx.Panel):
	"""Página declarativa de un complemento (protocolo ``PaginaPropia``)."""

	def __init__(self, padre: wx.Window, id_complemento: str, pagina: str = "", letras_ocupadas: frozenset[str] = LETRAS_DIALOGO) -> None:
		super().__init__(padre, name=_("Complemento"))
		self.id_complemento = id_complemento
		self.pagina = pagina
		self.config = config_plugins.registro().de(id_complemento)
		self.declaraciones = declaraciones_de_pagina(id_complemento, pagina)
		self.controles: dict[str, tuple[dict, wx.Window]] = {}
		sizer = wx.BoxSizer(wx.VERTICAL)
		ocupadas = set(letras_ocupadas) | {letra for d in self.declaraciones if (letra := _letra(str(d.get("etiqueta", ""))))}
		extra = self._etiquetas_extra()
		from app.ui.dialogos import f_comun

		con_letra = iter(f_comun.repartir_letras(extra, ocupadas))
		for declaracion in self.declaraciones:
			control = self._crear(sizer, declaracion, con_letra)
			ayuda = str(declaracion.get("ayuda", ""))
			if ayuda:
				control.SetHelpText(ayuda)
			self.controles[str(declaracion["clave"])] = (declaracion, control)
			self._escribir(declaracion, control, self._guardado(declaracion))
		self.boton_avanzada: wx.Button | None = None
		registrado = registro.complemento(id_complemento)
		if not pagina and registrado is not None and registrado.manifiesto.dialogo_preferencias:
			self.boton_avanzada = wx.Button(self, label=next(con_letra))
			self.boton_avanzada.SetHelpText(_("Abre la configuración propia del complemento (lo carga si hace falta)."))
			self.boton_avanzada.Bind(wx.EVT_BUTTON, lambda _e: abrir_avanzada(self.GetTopLevelParent(), id_complemento))
			sizer.Add(self.boton_avanzada, 0, wx.ALL, 6)
		if not self.controles and self.boton_avanzada is None:
			sizer.Add(wx.StaticText(self, label=_("Este complemento no tiene opciones en esta página.")), 0, wx.ALL, 6)
		self.SetSizer(sizer)

	def _etiquetas_extra(self) -> list[str]:
		"""Botones que añade la página («Examinar...» y «Abrir la configuración avanzada...»), en orden."""
		etiquetas = [_("Examinar...") for d in self.declaraciones if d.get("tipo") in ("carpeta", "archivo")]
		registrado = registro.complemento(self.id_complemento)
		if not self.pagina and registrado is not None and registrado.manifiesto.dialogo_preferencias:
			etiquetas.append(_(ETIQUETA_AVANZADA))
		return etiquetas

	# Controles ----------------------------------------------------------------

	def _crear(self, sizer: wx.Sizer, declaracion: dict, letras_extra) -> wx.Window:
		tipo = declaracion.get("tipo")
		etiqueta = str(declaracion.get("etiqueta") or declaracion["clave"])
		if tipo == "bool":
			control = wx.CheckBox(self, label=etiqueta)
			sizer.Add(control, 0, wx.ALL, 6)
			return control
		texto = wx.StaticText(self, label=etiqueta)
		sizer.Add(texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		nombre = etiqueta.replace("&", "").rstrip(": ")
		if tipo == "entero":
			minimo = int(declaracion.get("minimo", -(2 ** 31)))
			maximo = int(declaracion.get("maximo", 2 ** 31 - 1))
			control = wx.SpinCtrl(self, min=minimo, max=maximo, name=nombre)
		elif tipo == "opcion":
			control = wx.Choice(self, choices=[str(o[1]) if len(o) > 1 else str(o[0]) for o in declaracion.get("opciones", [])],
				name=nombre)
		elif tipo in ("lista", "diccionario"):
			control = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(-1, 90)), name=nombre)
			control.SetHelpText(_("Un elemento por línea.") if tipo == "lista" else _("Una línea por elemento: clave = valor."))
		else:  # texto, decimal, carpeta, archivo
			control = wx.TextCtrl(self, name=nombre)
		if tipo in ("carpeta", "archivo"):
			fila = wx.BoxSizer(wx.HORIZONTAL)
			fila.Add(control, 1, wx.EXPAND)
			boton = wx.Button(self, label=next(letras_extra))
			boton.SetHelpText(_("Elige la carpeta en una ventana de selección.") if tipo == "carpeta" else
				_("Elige el archivo en una ventana de selección."))
			boton.Bind(wx.EVT_BUTTON, lambda _e, c=control, t=tipo: self._examinar(c, t))
			fila.Add(boton, 0, wx.LEFT, 6)
			sizer.Add(fila, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
		else:
			sizer.Add(control, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
		return control

	def _examinar(self, control: wx.TextCtrl, tipo: str) -> None:
		ruta = elegir_ruta(self, tipo, control.GetValue())
		if ruta:
			control.SetValue(ruta)
		control.SetFocus()

	def _guardado(self, declaracion: dict) -> Any:
		try:
			return self.config.obtener(f"{config_plugins.SECCION}.{declaracion['clave']}")
		except KeyError:
			return declaracion.get("defecto")

	def _escribir(self, declaracion: dict, control: wx.Window, valor: Any) -> None:
		tipo = declaracion.get("tipo")
		if tipo == "bool":
			control.SetValue(bool(valor))
		elif tipo == "entero":
			control.SetValue(int(valor or 0))
		elif tipo == "opcion":
			valores = [str(o[0]) for o in declaracion.get("opciones", [])]
			control.SetSelection(valores.index(str(valor)) if str(valor) in valores else (0 if valores else wx.NOT_FOUND))
		elif tipo == "lista":
			control.ChangeValue("\n".join(str(v) for v in (valor or [])))
		elif tipo == "diccionario":
			control.ChangeValue("\n".join(f"{k} = {_texto_valor(v)}" for k, v in dict(valor or {}).items()))
		else:
			control.ChangeValue("" if valor is None else str(valor))

	def _leer(self, declaracion: dict, control: wx.Window) -> Any:
		"""Valor del control con el tipo de la clave. ``ValueError`` con un mensaje en español si no vale."""
		tipo = declaracion.get("tipo")
		nombre = str(declaracion.get("etiqueta") or declaracion["clave"]).replace("&", "").rstrip(": ")
		if tipo == "bool":
			return bool(control.GetValue())
		if tipo == "entero":
			return int(control.GetValue())
		if tipo == "decimal":
			texto = control.GetValue().strip().replace(",", ".")
			try:
				valor = float(texto)
			except ValueError as error:
				raise ValueError(_("{n}: escriba un número (por ejemplo 1,5)").format(n=nombre)) from error
			minimo, maximo = declaracion.get("minimo"), declaracion.get("maximo")
			if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
				raise ValueError(_("{n}: debe estar entre {a} y {b}").format(n=nombre, a=minimo, b=maximo))
			return valor
		if tipo == "opcion":
			opciones = declaracion.get("opciones", [])
			indice = control.GetSelection()
			return str(opciones[indice][0]) if 0 <= indice < len(opciones) else declaracion.get("defecto")
		if tipo == "lista":
			return [linea.strip() for linea in control.GetValue().splitlines() if linea.strip()]
		if tipo == "diccionario":
			resultado: dict[str, Any] = {}
			for numero, linea in enumerate(control.GetValue().splitlines(), start=1):
				if not linea.strip():
					continue
				clave, igual, valor = linea.partition("=")
				if not igual or not clave.strip():
					raise ValueError(_("{n}: la línea {l} debe tener la forma clave = valor").format(n=nombre, l=numero))
				resultado[clave.strip()] = _valor_de_texto(valor.strip())
			return resultado
		return control.GetValue()

	# Protocolo PaginaPropia ---------------------------------------------------

	def validar(self) -> str | None:
		for _clave, (declaracion, control) in self.controles.items():
			try:
				valor = self._leer(declaracion, control)
				self.config.validar(f"{config_plugins.SECCION}.{declaracion['clave']}", valor)
			except Exception as error:  # noqa: BLE001 - ValueError o ErrorValidacion: se dice a la persona
				control.SetFocus()
				return str(error)
		return None

	def aplicar(self) -> bool:
		if self.validar() is not None:
			return False
		cambios = {}
		for clave, (declaracion, control) in self.controles.items():
			valor = self._leer(declaracion, control)
			if valor != self._guardado(declaracion):
				cambios[f"{config_plugins.SECCION}.{clave}"] = valor
		if cambios:
			self.config.establecer_varias(cambios)
		return True

	def restablecer(self) -> None:
		for _clave, (declaracion, control) in self.controles.items():
			self._escribir(declaracion, control, declaracion.get("defecto"))

	def control_inicial(self) -> wx.Window | None:
		for _declaracion, control in self.controles.values():
			return control
		return self.boton_avanzada


def _texto_valor(valor: Any) -> str:
	return valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)


def _valor_de_texto(texto: str) -> Any:
	try:
		return json.loads(texto)
	except ValueError:
		return texto


def crear(padre: wx.Window, config: Any, id_complemento: str, pagina: str = "") -> PaginaComplemento:
	"""Fábrica de una página para el diálogo de Preferencias (``config`` es la de zCommander; no se usa aquí)."""
	return PaginaComplemento(padre, id_complemento, pagina)


def elegir_ruta(padre: wx.Window, tipo: str, actual: str = "") -> str | None:
	"""Carpeta o archivo elegido en el diálogo nativo (las pruebas sustituyen esta función)."""
	if tipo == "carpeta":
		dialogo = wx.DirDialog(padre, _("Elija una carpeta"), actual)
	else:
		dialogo = wx.FileDialog(padre, _("Elija un archivo"), defaultFile=actual, style=wx.FD_OPEN)
	try:
		with estado_complementos.pausa_modal():
			return dialogo.GetPath() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


class DialogoConfiguracion(wx.Dialog):
	"""«Configurar» del gestor: las páginas de un complemento en pestañas, con Aceptar, Cancelar y Aplicar."""

	def __init__(self, padre: wx.Window | None, id_complemento: str) -> None:
		nombre = estado_complementos.nombre_de(id_complemento)
		registrado = registro.complemento(id_complemento)
		if registrado is not None:
			nombre = registrado.nombre
		titulo = _("Configuración de {n}").format(n=nombre)
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.id_complemento = id_complemento
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.libro = wx.Notebook(panel)
		self.paginas: list[PaginaComplemento] = []
		nodo = next((n for n in nodos() if n.id == id_complemento), None)
		titulos = [(("", nombre))] + list(nodo.paginas if nodo else ())
		for id_pagina, titulo_pagina in titulos:
			if id_pagina == "" and not declaraciones_de_pagina(id_complemento, "") and not (nodo and nodo.dialogo) and len(titulos) > 1:
				continue
			pagina = PaginaComplemento(self.libro, id_complemento, id_pagina, LETRAS_DIALOGO - {"v"})
			self.libro.AddPage(pagina, titulo_pagina)
			self.paginas.append(pagina)
		sizer.Add(self.libro, 1, wx.EXPAND | wx.ALL, 6)
		botonera = crear_botonera(panel, wx.OK | wx.CANCEL | wx.APPLY)
		sizer.Add(botonera, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.aplicar(), id=wx.ID_APPLY)
		inicial = self.paginas[0].control_inicial() if self.paginas else None
		preparar_dialogo(self, foco_inicial=inicial)
		self.CentreOnParent()

	def aplicar(self) -> bool:
		for indice, pagina in enumerate(self.paginas):
			problema = pagina.validar()
			if problema:
				self.libro.SetSelection(indice)
				avisar(self, problema)
				return False
		for pagina in self.paginas:
			pagina.aplicar()
		from app.ui import anuncios

		anuncios.anunciar(_("Configuración guardada"), anuncios.RESULTADO)
		return True

	def _al_aceptar(self, _evento: wx.CommandEvent) -> None:
		if self.aplicar():
			if self.IsModal():
				self.EndModal(wx.ID_OK)
			else:
				self.SetReturnCode(wx.ID_OK)


def avisar(padre: wx.Window | None, texto: str) -> None:
	from app.ui.accesibilidad import dialogos

	dialogos.mostrar_mensaje(padre, texto, _("Valor no válido"), icono=wx.ICON_WARNING)


def abrir_dialogo(padre: wx.Window | None, id_complemento: str, mostrar: Callable[[wx.Dialog], int] | None = None) -> bool:
	"""«Configurar»: páginas declarativas del complemento; si solo tiene diálogo propio, ese (activándolo).

	Devuelve falso si el complemento no tiene nada que configurar.
	"""
	nodo = next((n for n in nodos() if n.id == id_complemento), None)
	if nodo is None:
		return False
	if not _declaraciones(id_complemento) and nodo.dialogo:
		abrir_avanzada(padre, id_complemento)
		return True
	dialogo = DialogoConfiguracion(padre, id_complemento)
	try:
		with estado_complementos.pausa_modal():
			(mostrar or (lambda d: d.ShowModal()))(dialogo)
	finally:
		dialogo.Destroy()
	return True
