# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Exportar e importar un perfil ``.zcperfil`` (diseño 2.0, 10.2; órdenes ``perfil_exportar`` y ``perfil_importar``).

Importar (también Intro sobre un ``.zcperfil``) muestra antes una **vista
previa**: «Qué se aplica» es una lista (Preferencia, Valor actual, Valor del
perfil) con casillas marcadas, y aparte «Órdenes que se podrán ejecutar»
(menú de usuario, asociaciones, alias, macros y programas externos) con el
texto completo de cada una y **sin marcar**. Siempre combina.
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass, field
from pathlib import Path

import wx

from app.core import paths
from app.services.copia import crear, formato, perfil
from app.services.copia.ejecutables import ElementoEjecutable
from app.services.copia.formato import CopiaAbierta, ErrorCopia
from app.ui import anuncios
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import cs_comun
from app.ui.dialogos.f_comun import mostrar

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class OpcionesExportar:
	destino: Path
	incluir_sonidos: bool
	descripcion: str


@dataclass
class EleccionImportar:
	ruta: Path
	filas: list[str] = field(default_factory=list)
	ejecutables: list[str] = field(default_factory=list)


def _selector(dialogo: cs_comun.DialogoCS, etiqueta: str, valor: str, ayuda: str, examinar, extra: wx.Button | None = None):
	texto, campo = crear_campo(dialogo.panel, etiqueta, wx.TextCtrl, value=valor, ayuda=ayuda)
	boton = wx.Button(dialogo.panel, label=_("E&xaminar..."))
	boton.SetHelpText(_("Abre un cuadro para elegir el archivo."))
	boton.Bind(wx.EVT_BUTTON, lambda _e: examinar())
	dialogo.sizer.Add(texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, dialogo.FromDIP(5))
	fila = wx.BoxSizer(wx.HORIZONTAL)
	fila.Add(campo, 1, wx.EXPAND | wx.RIGHT, dialogo.FromDIP(5))
	fila.Add(boton, 0, wx.RIGHT, dialogo.FromDIP(5))
	dialogo.sizer.Add(fila, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, dialogo.FromDIP(5))
	return campo, boton, fila


# ── Exportar ──────────────────────────────────────────────────────────────────

class DialogoExportarPerfil(cs_comun.DialogoCS):
	def __init__(self, padre: wx.Window | None, carpeta: Path) -> None:
		super().__init__(padre, _("Exportar un perfil"))
		self.resultado: OpcionesExportar | None = None
		self.campo_destino, self.boton_examinar, _fila = _selector(self, _("&Guardar en:"),
			str(Path(carpeta) / crear.nombre_por_defecto("perfil")),
			_("Archivo .zcperfil con las preferencias, las teclas, la personalización y las macros. Nunca lleva contraseñas "
				"ni conexiones."), self._examinar)
		self.casilla_sonidos = wx.CheckBox(self.panel, label=_("&Incluir los paquetes de sonidos propios"))
		self.casilla_sonidos.SetHelpText(_("Añade al perfil los paquetes de sonidos creados o importados."))
		self.sizer.Add(self.casilla_sonidos, 0, wx.ALL, self.FromDIP(5))
		_t, self.campo_descripcion = crear_campo(self.panel, _("&Descripción:"), wx.TextCtrl,
			ayuda=_("Opcional: para quien lo importe, por ejemplo «Configuración del curso»."), sizer=self.sizer)
		self.terminar_con_accion(_("&Exportar"), _("Crea el perfil."), self._aceptar, foco=self.campo_destino)

	def _examinar(self) -> None:
		ruta = cs_comun.elegir_archivo_guardar(self, _("Guardar el perfil"), cs_comun.COMODIN_PERFIL,
			self.campo_destino.GetValue())
		if ruta:
			self.campo_destino.SetValue(ruta if ruta.lower().endswith(formato.EXTENSION_PERFIL) else ruta + formato.EXTENSION_PERFIL)
		self.campo_destino.SetFocus()

	def _aceptar(self) -> None:
		texto = self.campo_destino.GetValue().strip()
		ruta = Path(texto) if texto else None
		if ruta is None or not ruta.is_absolute():
			cs_comun.avisar(self, _("Escriba la ruta completa del perfil."))
			self.campo_destino.SetFocus()
			return
		if ruta.suffix.lower() != formato.EXTENSION_PERFIL:
			ruta = ruta.with_name(ruta.name + formato.EXTENSION_PERFIL)
		if ruta.exists() and not cs_comun.preguntar(self, _("Ya existe {n}. ¿Sustituirlo?").format(n=ruta.name)):
			self.campo_destino.SetFocus()
			return
		self.resultado = OpcionesExportar(ruta, self.casilla_sonidos.GetValue(), self.campo_descripcion.GetValue().strip())
		self.cerrar(wx.ID_OK)


def pedir_exportar(padre: wx.Window | None, carpeta: Path) -> OpcionesExportar | None:
	return mostrar(DialogoExportarPerfil(padre, carpeta), lambda d: d.resultado)


# ── Importar ──────────────────────────────────────────────────────────────────

@dataclass
class PerfilLeido:
	ruta: Path
	resumen: str
	vista: perfil.VistaPerfil


def leer_perfil(ruta: Path, config, ruta_datos: Path | None = None) -> PerfilLeido:
	from app.services.copia import restaurar

	with CopiaAbierta(ruta) as copia:
		if copia.manifiesto.tipo != "perfil":
			raise ErrorCopia(_("Este archivo es una copia de seguridad, no un perfil: ábralo con «Restaurar una copia de "
				"seguridad»."))
		return PerfilLeido(Path(ruta), restaurar.resumen(copia), perfil.vista_previa(copia, config, ruta_datos))


class DialogoImportarPerfil(cs_comun.DialogoCS):
	def __init__(self, padre: wx.Window | None, config, ruta_inicial: str = "", ruta_datos: Path | None = None) -> None:
		super().__init__(padre, _("Importar un perfil"))
		self.config = config
		self.ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
		self.leido: PerfilLeido | None = None
		self.resultado: EleccionImportar | None = None
		self.ejecutables: list[ElementoEjecutable] = []
		self.ocupado = False
		self.campo_archivo, self.boton_examinar, fila = _selector(self, _("&Archivo del perfil:"), ruta_inicial,
			_("Perfil .zcperfil que se va a importar. Tras escribirlo, pulse «Leer el perfil»."), self._examinar)
		self.boton_leer = wx.Button(self.panel, label=_("&Leer el perfil"))
		self.boton_leer.SetHelpText(_("Comprueba el perfil y muestra lo que cambiaría."))
		self.boton_leer.Bind(wx.EVT_BUTTON, lambda _e: self.leer())
		fila.Add(self.boton_leer, 0)
		self.campo_resumen = self.texto_solo_lectura(_("Resu&men:"), alto=90)
		self.sizer.Add(wx.StaticText(self.panel, label=_("&Qué se aplica:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.lista = ListaAccesible(self.panel, _("Qué se aplica"), [(_("Preferencia"), self.FromDIP(220)),
			(_("Valor actual"), self.FromDIP(150)), (_("Valor del perfil"), self.FromDIP(180))], con_casillas=True)
		self.lista.SetMinSize(self.FromDIP(wx.Size(560, 160)))
		self.lista.SetHelpText(self.lista.GetHelpText() + " " + _("Lo marcado se aplica; Espacio marca o desmarca."))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.FromDIP(5))
		self.lista_ordenes = self.lista_casillas(_("Órdenes que se podrán &ejecutar:"), _("Órdenes que se podrán ejecutar"),
			ayuda=_("Están sin marcar: solo se importa lo que marque. Revise cada orden, sobre todo si el perfil no es suyo."))
		self.terminar_con_accion(_("&Importar"), _("Aplica lo marcado del perfil, combinándolo con lo actual."),
			self._aceptar, foco=self.campo_archivo, cancelar_predeterminado=True)
		if ruta_inicial:
			wx.CallAfter(self.leer)

	def _examinar(self) -> None:
		ruta = cs_comun.elegir_archivo_abrir(self, _("Elegir el perfil"), cs_comun.COMODIN_PERFIL, self.campo_archivo.GetValue())
		if ruta:
			self.campo_archivo.SetValue(ruta)
			self.leer()
		else:
			self.campo_archivo.SetFocus()

	def leer(self) -> None:
		texto = self.campo_archivo.GetValue().strip()
		if self.ocupado:
			return
		if not texto:
			cs_comun.avisar(self, _("Escriba la ruta del perfil o pulse «Examinar»."))
			self.campo_archivo.SetFocus()
			return
		self.ocupado = True
		self.campo_resumen.SetValue(_("Leyendo el perfil..."))
		ruta = Path(texto)
		cs_comun.en_hilo(lambda: leer_perfil(ruta, self.config, self.ruta_datos), self._al_leer)

	def _al_leer(self, leido: PerfilLeido | None, error: BaseException | None) -> None:
		if not self:
			return
		self.ocupado = False
		if error is not None or leido is None:
			mensaje = getattr(error, "mensaje", "") or str(error)
			if not isinstance(error, ErrorCopia):
				log.error("No se pudo leer el perfil", exc_info=error)
			self.leido = None
			self.campo_resumen.SetValue(mensaje)
			cs_comun.avisar(self, mensaje, _("No se puede importar"))
			self.campo_archivo.SetFocus()
			return
		self.cargar(leido)
		anuncios.anunciar(_("Perfil leído: {n} cambios y {o} órdenes por revisar").format(
			n=len(leido.vista.filas), o=len(leido.vista.ejecutables)), anuncios.NORMAL)
		self.lista.SetFocus()

	def cargar(self, leido: PerfilLeido) -> None:
		self.leido = leido
		self.campo_resumen.SetValue(leido.resumen)
		self.lista.limpiar()
		for fila in leido.vista.filas:
			indice = self.lista.agregar_fila([fila.preferencia, fila.actual, fila.nuevo])
			self.lista.CheckItem(indice, True)
		self.ejecutables = list(leido.vista.ejecutables)
		self.lista_ordenes.Set([e.texto for e in self.ejecutables])

	def _aceptar(self) -> None:
		if self.ocupado:
			return
		if self.leido is None or Path(self.campo_archivo.GetValue().strip()) != self.leido.ruta:
			cs_comun.avisar(self, _("Lea primero el perfil con «Leer el perfil» y revise lo que trae."))
			self.boton_leer.SetFocus()
			return
		filas = [self.leido.vista.filas[i].id for i in self.lista.filas_marcadas()]
		ordenes = cs_comun.marcados(self.lista_ordenes, [e.id for e in self.ejecutables])
		if not filas and not ordenes:
			cs_comun.avisar(self, _("No ha marcado nada que aplicar."))
			self.lista.SetFocus()
			return
		self.resultado = EleccionImportar(self.leido.ruta, filas, ordenes)
		self.cerrar(wx.ID_OK)


def pedir_importar(padre: wx.Window | None, config, ruta_inicial: str = "") -> EleccionImportar | None:
	return mostrar(DialogoImportarPerfil(padre, config, ruta_inicial), lambda d: d.resultado)
