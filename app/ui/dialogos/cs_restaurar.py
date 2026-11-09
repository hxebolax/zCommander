# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Restaurar una copia de seguridad» (diseño 2.0, 7.6; orden ``copia_restaurar`` e Intro sobre un ``.zcbackup``).

Pasos, en una sola pantalla que se recorre con Tab:

1. «Archivo de la copia» con «Examinar...» y «Leer la copia»: se abre en un
   hilo (ZIP seguro, manifiesto y sumas) y se muestra un resumen de solo lectura.
2. «Qué restaurar»: casillas con las partes que trae (las dañadas no se ofrecen).
3. «Órdenes que se podrán ejecutar»: casillas **sin marcar**, cada una con su
   texto completo. Solo se restaura lo que se marque.
4. «Combinar con lo actual» (por defecto) o «Sustituir lo actual».
5. «Contraseña de la copia», si trae contraseñas cifradas.

Al pulsar «Restaurar» se comprueba la contraseña en un hilo (si es incorrecta se
dice y se puede reintentar sin perder lo elegido), se revisan las cuentas de
nube que solo se ven con la contraseña, y al combinar se pregunta una a una por
cada huella de servidor nueva o distinta, con «No aceptarla» como
predeterminada. «Cancelar» es el botón predeterminado: restaurar es arriesgado (15.1).
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass, field
from pathlib import Path

import wx

from app.core import paths
from app.services import formato as fmt
from app.services.copia import combinar, ejecutables, formato, restaurar
from app.services.copia.ejecutables import Analisis, ElementoEjecutable
from app.services.copia.formato import CopiaAbierta, ErrorContrasena, ErrorCopia
from app.ui import anuncios
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import cs_comun
from app.ui.dialogos.f_comun import mostrar

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class CopiaLeida:
	"""Lo que se sabe de la copia tras leerla en el hilo."""

	ruta: Path
	manifiesto: formato.ManifiestoCopia
	partes: list[str]
	danadas: dict[str, str]
	resumen: str
	analisis: Analisis
	huellas: list[combinar.Huella] = field(default_factory=list)
	#: Secretos ya legibles sin contraseña (copias automáticas con DPAPI).
	secretos: dict[str, str] | None = None


@dataclass
class EleccionRestaurar:
	ruta: Path
	plan: restaurar.PlanRestauracion
	secretos: dict[str, str] | None
	carpeta_registros: Path | None = None


def leer_copia(ruta: Path, ruta_datos: Path | None = None, contrasena: str | None = None) -> CopiaLeida:
	"""Abre y analiza la copia (para el hilo). Con ``contrasena``, descifra y revisa también las nubes."""
	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	with CopiaAbierta(ruta) as copia:
		secretos = None
		if copia.manifiesto.modo_secretos == "dpapi" or contrasena:
			secretos = restaurar.secretos_de_copia(copia, contrasena)
		analisis = ejecutables.analizar(copia, None, ruta_datos, secretos)
		huellas: list[combinar.Huella] = []
		if "conexiones" in copia.partes_validas:
			if copia.tiene("conexiones", formato.KNOWN_HOSTS):
				local = ruta_datos / formato.KNOWN_HOSTS
				huellas += combinar.huellas_ssh(copia.leer("conexiones", formato.KNOWN_HOSTS),
					local.read_bytes() if local.is_file() else None)
			if copia.tiene("conexiones", formato.HOSTS_TLS):
				local_tls = restaurar._json(restaurar._leer(ruta_datos / formato.HOSTS_TLS))
				huellas += combinar.huellas_tls(copia.leer_json("conexiones", formato.HOSTS_TLS), local_tls)
		return CopiaLeida(Path(ruta), copia.manifiesto, copia.partes, dict(copia.danadas), restaurar.resumen(copia),
			analisis, huellas, secretos)


class DialogoRestaurarCopia(cs_comun.DialogoCS):
	def __init__(self, padre: wx.Window | None, ruta_inicial: str = "", ruta_datos: Path | None = None) -> None:
		super().__init__(padre, _("Restaurar una copia de seguridad"))
		self.ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
		self.leida: CopiaLeida | None = None
		self.resultado: EleccionRestaurar | None = None
		self.ids_partes: list[str] = []
		self.visibles: list[ElementoEjecutable] = []
		self.marcas: set[str] = set()
		self.secretos: dict[str, str] | None = None
		self.contrasena_comprobada: str | None = None
		self.ocupado = False
		sizer = self.sizer

		etiqueta, self.campo_archivo = crear_campo(self.panel, _("&Archivo de la copia:"), wx.TextCtrl, value=ruta_inicial,
			ayuda=_("Copia .zcbackup que se va a restaurar. Tras escribirla, pulse «Leer la copia»."))
		sizer.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(self.campo_archivo, 1, wx.EXPAND | wx.RIGHT, self.FromDIP(5))
		self.boton_examinar = wx.Button(self.panel, label=_("E&xaminar..."))
		self.boton_examinar.SetHelpText(_("Abre un cuadro para elegir la copia y la lee."))
		self.boton_examinar.Bind(wx.EVT_BUTTON, lambda _e: self._examinar())
		self.boton_leer = wx.Button(self.panel, label=_("&Leer la copia"))
		self.boton_leer.SetHelpText(_("Comprueba la copia escrita y muestra su resumen y sus partes."))
		self.boton_leer.Bind(wx.EVT_BUTTON, lambda _e: self.leer())
		fila.Add(self.boton_examinar, 0, wx.RIGHT, self.FromDIP(5))
		fila.Add(self.boton_leer, 0)
		sizer.Add(fila, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.FromDIP(5))

		self.campo_resumen = self.texto_solo_lectura(_("Resu&men:"), alto=130,
			ayuda=_("Versión de origen, fecha, descripción, partes con su tamaño y si trae contraseñas."))
		self.lista_partes = self.lista_casillas(_("&Qué restaurar:"), _("Qué restaurar"),
			ayuda=_("Las partes marcadas se restauran; las demás se quedan como están."))
		self.lista_partes.Bind(wx.EVT_CHECKLISTBOX, lambda _e: self._refrescar_ordenes())
		self.lista_ordenes = self.lista_casillas(_("Órdenes que se podrán &ejecutar:"), _("Órdenes que se podrán ejecutar"),
			ayuda=_("Están sin marcar: solo se restaura lo que marque. Revise cada orden antes de marcarla, sobre todo si "
				"la copia no es suya."))
		self.lista_ordenes.Bind(wx.EVT_CHECKLISTBOX, self._al_marcar_orden)

		sizer.Add(wx.StaticText(self.panel, label=_("Modo:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.opcion_combinar = wx.RadioButton(self.panel, label=_("C&ombinar con lo actual"), style=wx.RB_GROUP)
		self.opcion_combinar.SetHelpText(_("Añade lo que no existe (favoritos, conexiones, macros...) y conserva lo actual. "
			"Las huellas de servidores nuevas se confirman una a una."))
		self.opcion_sustituir = wx.RadioButton(self.panel, label=_("&Sustituir lo actual"))
		self.opcion_sustituir.SetHelpText(_("Cada parte marcada queda igual que en la copia, también las huellas de los "
			"servidores conocidos."))
		self.opcion_combinar.SetValue(True)
		for opcion in (self.opcion_combinar, self.opcion_sustituir):
			sizer.Add(opcion, 0, wx.LEFT | wx.RIGHT, self.FromDIP(10))

		_t, self.campo_contrasena = crear_campo(self.panel, _("Contrase&ña de la copia:"), wx.TextCtrl, style=wx.TE_PASSWORD,
			ayuda=_("La que se puso al crear la copia. Sin ella no se pueden restaurar las contraseñas."), sizer=sizer)
		self.campo_contrasena.Enable(False)
		self.terminar_con_accion(_("&Restaurar"), _("Restaura lo marcado de la copia."), self._aceptar,
			foco=self.campo_archivo, cancelar_predeterminado=True)
		if ruta_inicial:
			wx.CallAfter(self.leer)

	# Leer la copia -----------------------------------------------------------

	def _examinar(self) -> None:
		inicial = self.campo_archivo.GetValue() or str(paths.ruta_copias())
		ruta = cs_comun.elegir_archivo_abrir(self, _("Elegir la copia"), cs_comun.COMODIN_COPIA, inicial)
		if ruta:
			self.campo_archivo.SetValue(ruta)
			self.leer()
		else:
			self.campo_archivo.SetFocus()

	def _ocupar(self, ocupado: bool) -> None:
		self.ocupado = ocupado
		for control in (self.boton_leer, self.boton_examinar, self.boton_accion):
			control.Enable(not ocupado)

	def leer(self) -> None:
		texto = self.campo_archivo.GetValue().strip()
		if not texto or self.ocupado:
			if not texto:
				cs_comun.avisar(self, _("Escriba la ruta de la copia o pulse «Examinar»."))
				self.campo_archivo.SetFocus()
			return
		self._ocupar(True)
		self.campo_resumen.SetValue(_("Leyendo la copia..."))
		anuncios.anunciar(_("Leyendo la copia..."), anuncios.NORMAL)
		ruta = Path(texto)
		cs_comun.en_hilo(lambda: leer_copia(ruta, self.ruta_datos), self._al_leer)

	def _al_leer(self, leida: CopiaLeida | None, error: BaseException | None) -> None:
		if not self:
			return
		self._ocupar(False)
		if error is not None or leida is None:
			mensaje = getattr(error, "mensaje", "") or str(error)
			if not isinstance(error, ErrorCopia):
				log.error("No se pudo leer la copia", exc_info=error)
			self.leida = None
			self.campo_resumen.SetValue(mensaje)
			self.lista_partes.Set([])
			self.lista_ordenes.Set([])
			cs_comun.avisar(self, mensaje, _("No se puede restaurar"))
			self.campo_archivo.SetFocus()
			return
		self.cargar(leida)
		anuncios.anunciar(_("Copia leída: {n}").format(n=fmt.plural(len(self.ids_partes), _("{n} parte"), _("{n} partes"))),
			anuncios.NORMAL)
		self.campo_resumen.SetFocus()

	def cargar(self, leida: CopiaLeida) -> None:
		"""Muestra una copia ya leída (también lo usan las pruebas, sin hilo)."""
		self.leida = leida
		self.secretos = leida.secretos
		self.contrasena_comprobada = None
		self.marcas = set()
		self.campo_resumen.SetValue(leida.resumen)
		self.ids_partes = [p for p in leida.partes if p not in leida.danadas]
		textos = []
		for parte in self.ids_partes:
			texto = f"{formato.nombre_parte(parte)} ({fmt.tamano_legible(leida.manifiesto.tamano(parte))})"
			if formato.PARTES[parte].aplicacion == formato.EXTRAER:
				texto += " " + _("— no se restaura: se extrae a una carpeta")
			textos.append(texto)
		self.lista_partes.Set(textos)
		for indice, parte in enumerate(self.ids_partes):
			self.lista_partes.Check(indice, formato.PARTES[parte].aplicacion != formato.EXTRAER)
		self.campo_contrasena.Enable(leida.manifiesto.modo_secretos == "contrasena")
		self._refrescar_ordenes()

	def partes_marcadas(self) -> list[str]:
		return cs_comun.marcados(self.lista_partes, self.ids_partes)

	def _al_marcar_orden(self, evento: wx.CommandEvent) -> None:
		indice = evento.GetInt()
		if 0 <= indice < len(self.visibles):
			identificador = self.visibles[indice].id
			if self.lista_ordenes.IsChecked(indice):
				self.marcas.add(identificador)
			else:
				self.marcas.discard(identificador)
		evento.Skip()

	def _refrescar_ordenes(self) -> None:
		"""Las órdenes de las partes marcadas, conservando lo que ya se marcó."""
		partes = set(self.partes_marcadas())
		elementos = self.leida.analisis.elementos if self.leida else []
		self.visibles = [e for e in elementos if e.parte in partes]
		self.lista_ordenes.Set([e.texto for e in self.visibles])
		for indice, elemento in enumerate(self.visibles):
			self.lista_ordenes.Check(indice, elemento.id in self.marcas)

	def marcar_orden(self, identificador: str, marcar: bool = True) -> None:
		indice = next(i for i, e in enumerate(self.visibles) if e.id == identificador)
		self.lista_ordenes.Check(indice, marcar)
		(self.marcas.add if marcar else self.marcas.discard)(identificador)

	# Restaurar ---------------------------------------------------------------

	def _aceptar(self) -> None:
		if self.ocupado:
			return
		if self.leida is None or Path(self.campo_archivo.GetValue().strip()) != self.leida.ruta:
			cs_comun.avisar(self, _("Lea primero la copia con «Leer la copia» y revise lo que trae."))
			self.boton_leer.SetFocus()
			return
		partes = self.partes_marcadas()
		if not partes:
			cs_comun.avisar(self, _("Marque al menos una parte para restaurar."))
			self.lista_partes.SetFocus()
			return
		contrasena = self.campo_contrasena.GetValue()
		necesita = self.leida.manifiesto.modo_secretos == "contrasena" and any(
			p in ("conexiones", "complementos") for p in partes)
		if necesita and not contrasena:
			if not cs_comun.preguntar(self, _("La copia trae contraseñas cifradas. ¿Restaurar sin ellas? Tendrá que volver a "
					"escribirlas y añadir de nuevo las cuentas de nube."), peligroso=True):
				self.campo_contrasena.SetFocus()
				return
			self.secretos = None
		elif necesita and contrasena != self.contrasena_comprobada:
			self._comprobar_contrasena(contrasena)
			return
		self._continuar()

	def _comprobar_contrasena(self, contrasena: str) -> None:
		self._ocupar(True)
		anuncios.anunciar(_("Comprobando la contraseña..."), anuncios.NORMAL)
		ruta = self.leida.ruta
		cs_comun.en_hilo(lambda: leer_copia(ruta, self.ruta_datos, contrasena),
			lambda leida, error: self._al_comprobar(contrasena, leida, error))

	def _al_comprobar(self, contrasena: str, leida: CopiaLeida | None, error: BaseException | None) -> None:
		if not self:
			return
		self._ocupar(False)
		if isinstance(error, ErrorContrasena) or leida is None:
			mensaje = getattr(error, "mensaje", "") or str(error)
			cs_comun.avisar(self, mensaje or ErrorContrasena().mensaje, _("Contraseña"))
			self.campo_contrasena.SetFocus()
			self.campo_contrasena.SelectAll()
			return
		self.aplicar_comprobacion(contrasena, leida)

	def aplicar_comprobacion(self, contrasena: str, leida: CopiaLeida) -> None:
		"""Contraseña buena: si aparecen órdenes nuevas (cuentas de nube), se muestran antes de seguir."""
		vistas = self.leida.analisis.ids if self.leida else set()
		nuevas = [e for e in leida.analisis.elementos if e.id not in vistas]
		self.secretos = leida.secretos
		self.contrasena_comprobada = contrasena
		self.leida.analisis = leida.analisis
		if nuevas:
			self._refrescar_ordenes()
			cs_comun.avisar(self, _("Con la contraseña se han podido revisar las cuentas de nube: la copia trae {n} órdenes "
				"más que se ejecutarían. Revíselas en «Órdenes que se podrán ejecutar» y vuelva a pulsar «Restaurar».").format(
				n=len(nuevas)))
			self.lista_ordenes.SetFocus()
			return
		self._continuar()

	def _continuar(self) -> None:
		leida = self.leida
		partes = self.partes_marcadas()
		sustituir = self.opcion_sustituir.GetValue()
		if sustituir:
			texto = _("Cada parte marcada quedará igual que en la copia y se perderá lo que solo esté en este equipo.")
			if "conexiones" in partes:
				texto += " " + _("También se sustituyen todas las huellas de servidores conocidas.")
			if not cs_comun.preguntar(self, texto + " " + _("¿Sustituir?"), _("Sustituir lo actual"), peligroso=True):
				self.opcion_combinar.SetFocus()
				return
		aceptadas: set[str] = set()
		if not sustituir and "conexiones" in partes:
			for huella in leida.huellas:
				eleccion = cs_comun.elegir(self, huella.pregunta(), _("Huella de servidor"), [_("&No aceptarla"), _("&Aceptarla")])
				if eleccion == 1:
					aceptadas.add(huella.id)
		carpeta_registros = None
		if "registros" in partes:
			elegida = cs_comun.elegir_carpeta(self, _("Carpeta donde extraer los registros"))
			if not elegida:
				self.lista_partes.SetFocus()
				return
			carpeta_registros = Path(elegida)
		visibles = {e.id for e in self.visibles}
		plan = restaurar.PlanRestauracion(partes=[p for p in partes if p != "registros"],
			modo="sustituir" if sustituir else "combinar", ejecutables=leida.analisis.ids,
			marcados=self.marcas & visibles, huellas_aceptadas=aceptadas)
		self.resultado = EleccionRestaurar(leida.ruta, plan, self.secretos, carpeta_registros)
		self.cerrar(wx.ID_OK)


def pedir(padre: wx.Window | None, ruta_inicial: str = "") -> EleccionRestaurar | None:
	return mostrar(DialogoRestaurarCopia(padre, ruta_inicial), lambda d: d.resultado)
