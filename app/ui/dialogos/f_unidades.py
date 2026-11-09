# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Selector de unidades (Alt+F1 y Alt+F2): unidades, favoritos y carpetas especiales.

- Cada unidad se ve al momento con lo que Windows sabe sin tocar el disco
  («E:, Extraíble»); la etiqueta, el sistema de archivos y el espacio llegan
  después, desde un hilo con tiempo límite, para que una unidad de red caída
  o un lector óptico que gira no congelen el diálogo. La fila se actualiza en
  su sitio, sin mover la selección.
- Teclear la letra de una unidad va a ella al momento (como en Norton). Las
  demás teclas son las de la lista.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import wx

from app.core.tareas import GestorTareas
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)

UNIDAD, FAVORITO, ESPECIAL, VIRTUAL = "unidad", "favorito", "especial", "virtual"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class Destino:
	"""Una fila del selector: ``ruta`` es la raíz («D:\\») o la carpeta."""

	tipo: str
	texto: str
	ruta: str
	letra: str = ""  # «D:» en las unidades


def destinos_iniciales(letras: Sequence[str], tipo_de: Callable[[str], str], favoritos: Sequence[tuple[str, str]],
		especiales: Sequence[tuple[str, str]]) -> list[Destino]:
	"""Filas que se muestran al abrir, sin tocar ningún disco (``tipo_de`` usa ``GetDriveType``)."""
	from app.services.windows.unidades import nombre_tipo

	filas = [Destino(UNIDAD, f"{letra}, {nombre_tipo(tipo_de(letra + '\\'))}", letra + "\\", letra) for letra in letras]
	filas.extend(Destino(FAVORITO, _("Favorito: {n}, {r}").format(n=nombre, r=ruta), ruta) for nombre, ruta in favoritos)
	filas.extend(Destino(ESPECIAL, f"{nombre}, {ruta}", ruta) for nombre, ruta in especiales)
	# 2.0 (14.5): las entradas fijas de los manifiestos ([[unidades]]), sin activar ningún complemento.
	filas.extend(_destino_virtual(u) for u in _unidades_fijas())
	return filas


def _unidades_fijas() -> list:
	try:
		from app.services.vfs import resolver

		return resolver.unidades_fijas()
	except Exception:  # noqa: BLE001 - un manifiesto raro no deja sin selector
		log.warning("No se pudieron leer las unidades de los complementos", exc_info=True)
		return []


def _destino_virtual(unidad) -> Destino:
	texto = f"{unidad.texto}, {unidad.descripcion}" if unidad.descripcion else unidad.texto
	return Destino(VIRTUAL, texto, unidad.direccion)


def unidades_dinamicas(_tarea=None) -> list:
	"""En un hilo: activa (la primera vez) los complementos con unidades dinámicas y junta todas (3.4, 14.5)."""
	from app.plugins import cargador, registro
	from app.services.vfs import resolver

	for registrado in registro.complementos():
		if any(u.get("dinamicas") for u in registrado.manifiesto.tabla("unidades")):
			try:
				cargador.asegurar_activo(registrado.id).result(cargador.TIEMPO_CARGA_S)
			except Exception:  # noqa: BLE001 - un complemento que no se activa no aporta unidades
				log.info("No se activó %s para el selector de unidades", registrado.id, exc_info=True)
	return resolver.unidades_virtuales()


class DialogoUnidades(f_comun.DialogoF):
	"""``elegido`` queda con el ``Destino``.

	:param consultar: ``consultar(letras) -> list[Unidad]`` (en un hilo); ``None`` no
		pide los detalles (pruebas).
	"""

	def __init__(self, padre: wx.Window | None, titulo: str, destinos: list[Destino], actual: str = "",
			tareas: GestorTareas | None = None, consultar: Callable[[list[str]], list] | None = None) -> None:
		super().__init__(padre, titulo)
		self.destinos = destinos
		self.elegido: Destino | None = None
		_l, self.lista = crear_campo(self.panel, _("&Unidades y carpetas:"), wx.ListBox, choices=[d.texto for d in destinos],
			size=self.FromDIP(wx.Size(480, 300)), sizer=self.sizer,
			ayuda=_("Intro va al elemento elegido. Teclear la letra de una unidad va a ella al momento."))
		self.sizer.GetItem(self.lista).SetProportion(1)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_ir = self.boton(_("&Ir"), _("Lleva el panel a la unidad o carpeta elegida."), self.ir, fila)
		self.sizer.Add(fila, 0, wx.ALIGN_RIGHT)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.ir())
		self.lista.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)
		self.terminar(wx.CANCEL, foco=self.lista)
		self.boton_ir.SetDefault()
		inicial = next((i for i, d in enumerate(destinos) if d.letra and actual.upper().startswith(d.letra.upper())), 0)
		if destinos:
			self.lista.SetSelection(inicial)
		letras = [d.letra for d in destinos if d.tipo == UNIDAD]
		if tareas is not None and consultar is not None and letras:
			tareas.enviar(lambda _t: consultar(letras), al_terminar=self.poner_detalles,
				al_fallar=lambda e: log.warning("No se pudo consultar las unidades: %s", e), nombre="selector-unidades")
		if tareas is not None and consultar is not None:
			tareas.enviar(unidades_dinamicas, al_terminar=self.poner_virtuales,
				al_fallar=lambda e: log.warning("No se pudieron obtener las unidades de los complementos: %s", e),
				nombre="selector-unidades-virtuales")

	def poner_virtuales(self, unidades: list) -> None:
		"""Añade o actualiza las entradas dinámicas cuando llegan de su hilo (sin mover la selección)."""
		if not self:
			return
		for unidad in unidades:
			destino = _destino_virtual(unidad)
			indice = next((i for i, d in enumerate(self.destinos) if d.tipo == VIRTUAL and d.ruta == destino.ruta), None)
			if indice is None:
				self.destinos.append(destino)
				self.lista.Append(destino.texto)
			elif self.destinos[indice].texto != destino.texto:
				self.destinos[indice] = destino
				self.lista.SetString(indice, destino.texto)

	def poner_detalles(self, unidades: list) -> None:
		"""Cambia el texto de cada unidad por su descripción completa (en el hilo de la interfaz)."""
		if not self:
			return
		por_letra = {u.letra.upper(): u for u in unidades}
		for indice, destino in enumerate(self.destinos):
			unidad = por_letra.get(destino.letra.upper()) if destino.tipo == UNIDAD else None
			if unidad is None:
				continue
			texto = unidad.describir()
			if texto != destino.texto:
				destino.texto = texto
				self.lista.SetString(indice, texto)

	def ir(self, indice: int | None = None) -> None:
		indice = self.lista.GetSelection() if indice is None else indice
		if not 0 <= indice < len(self.destinos):
			return
		self.elegido = self.destinos[indice]
		self.cerrar(wx.ID_OK)

	def ir_a_letra(self, letra: str) -> bool:
		"""Va a la unidad de esa letra si existe."""
		buscada = letra.upper() + ":"
		indice = next((i for i, d in enumerate(self.destinos) if d.tipo == UNIDAD and d.letra.upper() == buscada), None)
		if indice is None:
			return False
		self.lista.SetSelection(indice)
		self.ir(indice)
		return True

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		codigo = evento.GetKeyCode()
		if evento.GetModifiers() in (wx.MOD_NONE, wx.MOD_SHIFT) and ord("A") <= codigo <= ord("Z") and self.ir_a_letra(chr(codigo)):
			return
		evento.Skip()


def elegir_destino(padre: wx.Window | None, titulo: str, destinos: list[Destino], actual: str, tareas, consultar) -> Destino | None:
	dialogo = DialogoUnidades(padre, titulo, destinos, actual, tareas, consultar)
	return f_comun.mostrar(dialogo, lambda d: d.elegido)
