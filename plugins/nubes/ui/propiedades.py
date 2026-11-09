# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Propiedades de una cuenta (diseño 2.0, 12.7): un diálogo con pestañas generado desde el catálogo.

Pestañas: General, Caché, Velocidad, Fragmentos, Servicio, Avanzado y, si la
cuenta es una carpeta cifrada o una unión, Cifrado y uniones. Las letras de
acceso de cada pestaña no se repiten con las de los botones Aceptar y Cancelar.
Los tamaños de fragmento se validan por servicio (potencia de 2 en Drive,
múltiplo de 320 KiB en OneDrive).
"""

from __future__ import annotations

import copy
import re
from typing import Any

import wx

from app.plugins import api

from ..cuentas import Cuenta, Servicio
from . import comun

_ = api.traduccion("zc_nubes")[0]

_MULTIPLOS = {"": 1, "b": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}


def bytes_de(texto: str) -> int:
	"""«8M» → 8388608; lanza ``ValueError`` si no se entiende."""
	coincide = re.fullmatch(r"\s*(\d+)\s*([bkmg]?)i?b?\s*", texto.lower())
	if coincide is None:
		raise ValueError(texto)
	return int(coincide.group(1)) * _MULTIPLOS[coincide.group(2)]


def validar_fragmento(texto: str, regla: str) -> str:
	"""Mensaje de error en español, o vacío si el tamaño vale para ``regla``."""
	if not texto.strip():
		return ""
	try:
		valor = bytes_de(texto)
	except ValueError:
		return _("Escriba un tamaño como 8M o 256k")
	if regla == "potencia_2":
		if valor < 256 * 1024 or valor & (valor - 1):
			return _("En Google Drive el fragmento debe ser una potencia de 2 de al menos 256 KiB (por ejemplo 8M o 64M)")
	elif regla == "multiplo_320k":
		if valor % (320 * 1024) or valor >= 60 * 1024 * 1024:
			return _("En OneDrive el fragmento debe ser múltiplo de 320 KiB y menor de 60 MiB (por ejemplo 10M)")
	return ""


class _Pagina(wx.Panel):
	def __init__(self, libro: wx.Notebook, titulo: str) -> None:
		super().__init__(libro)
		self.sizer = wx.BoxSizer(wx.VERTICAL)
		self.SetSizer(self.sizer)
		self.ocupadas = {"a", "c"}
		libro.AddPage(self, titulo)

	def letra(self, etiqueta: str) -> str:
		return comun.con_letra(etiqueta, self.ocupadas)


class DialogoPropiedades(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, cuenta: Cuenta, servicio: Servicio | None, *, secreto_cliente: str = "",
			copia_entre_cuentas_general: bool = False, cache_general: int = 30, editar_horario: Any = None) -> None:
		super().__init__(zc, padre, _("Propiedades de {n}").format(n=cuenta.nombre))
		self.cuenta = copy.deepcopy(cuenta)
		self.servicio = servicio
		self._editar_horario = editar_horario
		self._secreto_original = secreto_cliente
		self.libro = wx.Notebook(self.panel)
		self.sizer.Add(self.libro, 1, wx.EXPAND | wx.ALL, 5)

		general = _Pagina(self.libro, _("General"))
		self.nombre = comun.campo(zc, general, general.letra(_("Nombre visible:")), wx.TextCtrl, cuenta.nombre, sizer=general.sizer,
			ayuda=_("Cómo se ve la cuenta en el selector de unidades."))
		self.carpeta = comun.campo(zc, general, general.letra(_("Carpeta inicial:")), wx.TextCtrl, cuenta.carpeta_inicial,
			sizer=general.sizer, ayuda=_("Carpeta de la cuenta que se abre al entrar, por ejemplo /Documentos."))
		self.solo_lectura = comun.casilla(general, general.letra(_("Solo lectura")),
			_("zCommander no escribe, mueve ni borra nada en esta cuenta."), cuenta.solo_lectura, sizer=general.sizer)
		self.papelera = comun.casilla(general, general.letra(_("Borrar a la papelera del servicio")),
			_("Lo borrado va a la papelera de la nube (si el servicio la tiene) en lugar de borrarse para siempre."),
			cuenta.papelera, sizer=general.sizer)

		cache = _Pagina(self.libro, _("Caché"))
		self.cache = comun.campo(zc, cache, cache.letra(_("Segundos que se recuerdan los listados (−1 usa la general):")),
			wx.SpinCtrl, sizer=cache.sizer, min=-1, max=3600, initial=cuenta.cache_listados_s,
			ayuda=_("La configuración general es de {n} segundos. 0 vuelve a listar cada vez.").format(n=cache_general))

		velocidad = _Pagina(self.libro, _("Velocidad"))
		self.subida = comun.campo(zc, velocidad, velocidad.letra(_("Límite de subida en KiB/s (0 sin límite):")), wx.SpinCtrl,
			sizer=velocidad.sizer, min=0, max=10_000_000, initial=cuenta.limite_subida_kib,
			ayuda=_("Se aplica a cada transferencia de esta cuenta."))
		self.bajada = comun.campo(zc, velocidad, velocidad.letra(_("Límite de bajada en KiB/s (0 sin límite):")), wx.SpinCtrl,
			sizer=velocidad.sizer, min=0, max=10_000_000, initial=cuenta.limite_bajada_kib,
			ayuda=_("Se aplica a cada transferencia de esta cuenta."))
		self.horario = comun.campo(zc, velocidad, velocidad.letra(_("Horario de límites propio:")), wx.TextCtrl,
			cuenta.horario_limites, sizer=velocidad.sizer, ayuda=_("Formato de rclone, por ejemplo 08:00,512k 23:00,off. Vacío: sin horario."))
		comun.boton(velocidad, velocidad.letra(_("Editar el horario...")), _("Edita el horario por franjas."), self._franjas,
			sizer=velocidad.sizer)

		fragmentos = _Pagina(self.libro, _("Fragmentos"))
		regla = ""
		defecto = ""
		campo_fragmento = servicio.campo("chunk_size") if servicio is not None else None
		if campo_fragmento is not None:
			regla = str(campo_fragmento.get("validar", ""))
			defecto = str(campo_fragmento.get("defecto", ""))
		self._regla_fragmento = regla
		self.fragmento = comun.campo(zc, fragmentos, fragmentos.letra(_("Tamaño de fragmento de subida:")), wx.TextCtrl,
			cuenta.opciones.get("chunk_size", defecto), sizer=fragmentos.sizer,
			ayuda=str(campo_fragmento.get("ayuda", "")) if campo_fragmento else _("Vacío: el de rclone para este servicio."))

		pagina_servicio = _Pagina(self.libro, _("Servicio"))
		self.avanzadas: dict[str, wx.Window] = {}
		for campo in (servicio.avanzadas if servicio is not None else ()):
			if campo["clave"] == "chunk_size":
				continue
			valor = cuenta.opciones.get(campo["clave"], str(campo.get("defecto", "")))
			etiqueta = pagina_servicio.letra(str(campo.get("etiqueta", campo["clave"])))
			ayuda = str(campo.get("ayuda", ""))
			if campo.get("tipo") == "opcion":
				opciones = [(str(o[0]), str(o[1])) for o in campo.get("opciones", [])]
				control = comun.elegir(zc, pagina_servicio, etiqueta, opciones, valor, ayuda=ayuda, sizer=pagina_servicio.sizer)
			elif campo.get("tipo") == "bool":
				control = comun.casilla(pagina_servicio, etiqueta, ayuda, valor == "true", sizer=pagina_servicio.sizer)
			else:
				control = comun.campo(zc, pagina_servicio, etiqueta, wx.TextCtrl, valor, ayuda=ayuda, sizer=pagina_servicio.sizer)
			self.avanzadas[campo["clave"]] = control
		if not self.avanzadas:
			comun.texto_solo_lectura(zc, pagina_servicio, pagina_servicio.letra(_("Opciones del servicio:")),
				_("Este servicio no tiene opciones propias en zCommander."), sizer=pagina_servicio.sizer, alto=40)

		avanzado = _Pagina(self.libro, _("Avanzado"))
		self.client_id = comun.campo(zc, avanzado, avanzado.letra(_("Identificador de cliente propio:")), wx.TextCtrl,
			cuenta.opciones.get("client_id", ""), sizer=avanzado.sizer, ayuda=_("Vacío: el de rclone. Al cambiarlo hay que volver a autorizar."))
		self.client_secret = comun.campo(zc, avanzado, avanzado.letra(_("Secreto del cliente propio:")), wx.TextCtrl, secreto_cliente,
			sizer=avanzado.sizer, style=wx.TE_PASSWORD, ayuda=_("Se guarda cifrado."))
		eleccion = "general" if cuenta.copia_entre_cuentas is None else ("si" if cuenta.copia_entre_cuentas else "no")
		general_texto = _("Sí") if copia_entre_cuentas_general else _("No")
		self.entre_cuentas = comun.elegir(zc, avanzado, avanzado.letra(_("Copiar en el servidor entre cuentas del mismo servicio:")),
			[("general", _("Como la configuración general ({v})").format(v=general_texto)), ("si", _("Sí")), ("no", _("No"))], eleccion,
			sizer=avanzado.sizer, ayuda=_("ServerSideAcrossConfigs de rclone; si falla, se copia pasando por zCommander."))

		if cuenta.cifrada_sobre or cuenta.union_de:
			capas = _Pagina(self.libro, _("Cifrado y uniones"))
			if cuenta.cifrada_sobre:
				texto = _("Carpeta cifrada sobre {r}. Los nombres y el contenido se cifran en este equipo antes de subir.").format(
					r=cuenta.opciones.get("remote", cuenta.cifrada_sobre))
			else:
				texto = _("Une las cuentas: {c}.").format(c=", ".join(cuenta.union_de))
			comun.texto_solo_lectura(zc, capas, capas.letra(_("De dónde sale:")), texto, sizer=capas.sizer, alto=60)

		self.botones(wx.OK | wx.CANCEL)
		self.Bind(wx.EVT_BUTTON, self._aceptar, id=wx.ID_OK)
		self.terminar(self.nombre)

	def _franjas(self) -> None:
		if self._editar_horario is not None:
			nuevo = self._editar_horario(self, self.horario.GetValue())
			if nuevo is not None:
				self.horario.SetValue(nuevo)

	def _aceptar(self, evento: wx.CommandEvent) -> None:
		if not self.nombre.GetValue().strip():
			comun.error(self.zc, _("Escriba un nombre visible."))
			return
		mensaje = validar_fragmento(self.fragmento.GetValue(), self._regla_fragmento)
		if mensaje:
			comun.error(self.zc, mensaje)
			self.libro.SetSelection(3)
			self.fragmento.SetFocus()
			return
		if self.horario.GetValue().strip():
			from .franjas import leer_horario

			try:
				leer_horario(self.horario.GetValue())
			except ValueError:
				comun.error(self.zc, _("El horario no tiene el formato de rclone (por ejemplo 08:00,512k 23:00,off)."))
				self.libro.SetSelection(2)
				self.horario.SetFocus()
				return
		evento.Skip()

	def resultado(self) -> tuple[Cuenta, dict[str, str], str]:
		"""(cuenta cambiada, parámetros de rclone que cambiaron, secreto del cliente)."""
		cuenta = copy.deepcopy(self.cuenta)
		cuenta.nombre = self.nombre.GetValue().strip()
		cuenta.carpeta_inicial = "/" + self.carpeta.GetValue().strip().strip("/\\").replace("\\", "/")
		cuenta.solo_lectura = self.solo_lectura.GetValue()
		cuenta.cache_listados_s = self.cache.GetValue()
		cuenta.limite_subida_kib = self.subida.GetValue()
		cuenta.limite_bajada_kib = self.bajada.GetValue()
		cuenta.horario_limites = self.horario.GetValue().strip()
		eleccion = comun.valor_elegido(self.entre_cuentas)
		cuenta.copia_entre_cuentas = None if eleccion == "general" else eleccion == "si"
		cambios: dict[str, str] = {}
		papelera = self.papelera.GetValue()
		if papelera != self.cuenta.papelera:
			cuenta.papelera = papelera
			if self.servicio is not None and self.servicio.tipo == "drive":
				cambios["use_trash"] = "true" if papelera else "false"
		nuevos = {"chunk_size": self.fragmento.GetValue().strip(), "client_id": self.client_id.GetValue().strip()}
		for clave, control in self.avanzadas.items():
			if isinstance(control, wx.Choice):
				nuevos[clave] = comun.valor_elegido(control)
			elif isinstance(control, wx.CheckBox):
				nuevos[clave] = "true" if control.GetValue() else "false"
			else:
				nuevos[clave] = control.GetValue().strip()
		for clave, valor in nuevos.items():
			anterior = self.cuenta.opciones.get(clave, "")
			if valor != anterior and (valor or anterior):
				cambios[clave] = valor
				if valor:
					cuenta.opciones[clave] = valor
				else:
					cuenta.opciones.pop(clave, None)
		cuenta.client_id_propio = bool(cuenta.opciones.get("client_id"))
		secreto = self.client_secret.GetValue().strip()
		if secreto and secreto != self._secreto_original:
			cambios["client_secret"] = secreto
		return cuenta, cambios, secreto
