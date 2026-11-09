# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Mapa de teclas: cambiar, añadir, quitar y restablecer las teclas de cada orden.

Reglas (sección 6 del diseño), en ``comprobar`` para probarlas sin ventanas:

- Las órdenes fijas (Tab, Ctrl+H, menú contextual, F9) no se cambian, y sus
  teclas no se pueden dar a otra orden.
- Las teclas reservadas por Windows (Alt+F4, Alt+Tab...) no se asignan.
- Alt+letra de un menú de la barra (I, A, C, O, D, U) abriría el menú: no.
- Una letra, un dígito o un signo sin Ctrl ni Alt es para escribir y para la
  búsqueda rápida: no.
- Si la tecla ya es de otra orden en un ámbito que se solapa, se pregunta
  «Ctrl+R ya es Volver a leer: ¿quitársela?». Dos órdenes pueden compartir
  tecla si sus ámbitos no se solapan (Intro en el panel y en la línea).

Se guarda en ``teclado.personalizadas`` solo lo que difiere de fábrica, al
Aceptar; la ventana principal reconstruye despachador, menús y barra de
teclas al recibir el aviso de la configuración.

La captura de la tecla es un campo que se queda con la siguiente pulsación
(salvo Tab, que sale del campo, y Escape, que cancela): así se puede asignar
cualquier combinación, incluidas Intro y las teclas F.

2.0 (bloque PE, 10.7): las teclas «de fábrica» son las del esquema de teclas
vigente (``teclado.esquema``), así «Restablecer» y lo que se guarda en
``teclado.personalizadas`` cuentan desde el esquema. «Exportar...» e
«Importar...» guardan y leen un ``.zcteclas``
(``{"version": 1, "esquema": "...", "personalizadas": {...}}``); Intro sobre un
``.zcteclas`` abre este diálogo con la importación (``editar_mapa(..., importar=ruta)``).
"""

from __future__ import annotations

import builtins
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import wx

from app.services import teclas as servicio_teclas
from app.services.teclas import RESERVADAS, SOLAPES, nombre_visible
from app.ui import anuncios, ordenes
from app.ui.accesibilidad.ayuda import describir_control_enfocado
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.accesibilidad.revision_teclado import letra_de_acceso
from app.ui.dialogos import f_comun

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


NOMBRES_AMBITO = {ordenes.PANEL: "Panel", ordenes.GLOBAL: "Global", ordenes.LINEA: "Línea de órdenes"}


def nombre_ambito(ambito: str) -> str:
	return _(NOMBRES_AMBITO.get(ambito, ambito))


def etiqueta_orden(id_orden: str) -> str:
	orden = ordenes.POR_ID.get(id_orden)
	return f_comun.texto_limpio(_(orden.etiqueta)).rstrip(".") if orden else id_orden


def teclas_visibles(teclas: Sequence[str]) -> str:
	return ", ".join(nombre_visible(t) for t in teclas) if teclas else _("(sin tecla)")


def letras_menus() -> dict[str, str]:
	"""Letra de acceso de cada menú de la barra → título («a» → «Archivos»)."""
	resultado = {}
	for titulo, _contenido in ordenes.menus():  # 2.0: el catálogo vivo (Complementos, Mis órdenes)
		letra = letra_de_acceso(_(titulo))
		if letra:
			resultado[letra] = f_comun.texto_limpio(_(titulo))
	return resultado


@dataclass(frozen=True)
class Comprobacion:
	"""Resultado de querer dar ``tecla`` a una orden."""

	permitida: bool
	motivo: str = ""
	#: Órdenes que ya tienen la tecla en un ámbito que se solapa (se les quitaría).
	choques: tuple[str, ...] = ()


def comprobar(asignadas: Mapping[str, Sequence[str]], ambitos: Mapping[str, str], fijas: frozenset[str],
		orden: str, tecla: str) -> Comprobacion:
	"""¿Se puede dar ``tecla`` (canónica) a ``orden``? Sin efectos: solo dice qué pasaría."""
	visible = nombre_visible(tecla)
	if orden in fijas:
		return Comprobacion(False, _("Las teclas de «{o}» son fijas y no se pueden cambiar.").format(o=etiqueta_orden(orden)))
	if servicio_teclas.es_reservada(tecla):
		return Comprobacion(False, _("{t} está reservada: {m}").format(t=visible, m=_(RESERVADAS[tecla])))
	partes = tecla.split("+")
	modificadores, final = partes[:-1], partes[-1] if not tecla.endswith("++") else "+"
	if modificadores == ["Alt"] and len(final) == 1:
		menu = letras_menus().get(final.lower())
		if menu:
			return Comprobacion(False, _("{t} abre el menú {m}.").format(t=visible, m=menu))
	if not {"Ctrl", "Alt"} & set(modificadores) and len(final) == 1:
		return Comprobacion(False, _("{t} sirve para escribir y para la búsqueda rápida: use Ctrl, Alt o una tecla de función.").format(t=visible))
	ambito = ambitos.get(orden, ordenes.GLOBAL)
	choques: list[str] = []
	for otra, teclas_otra in asignadas.items():
		if otra == orden or tecla not in teclas_otra:
			continue
		if (ambitos.get(otra, ordenes.GLOBAL), ambito) not in SOLAPES:
			continue
		if otra in fijas:
			return Comprobacion(False, _("{t} es fija de «{o}» y no se puede asignar a otra orden.").format(t=visible, o=etiqueta_orden(otra)))
		choques.append(otra)
	return Comprobacion(True, choques=tuple(choques))


def personalizadas(asignadas: Mapping[str, Sequence[str]], por_defecto: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
	"""Solo lo que difiere de fábrica (lo que se guarda en ``teclado.personalizadas``)."""
	return {o: list(t) for o, t in asignadas.items() if tuple(t) != tuple(por_defecto.get(o, ()))}


# ── Captura de una tecla ────────────────────────────────────────────────────

class DialogoCapturaTecla(f_comun.DialogoF):
	"""Campo que se queda con la siguiente tecla pulsada. ``tecla`` queda en formato canónico."""

	def __init__(self, padre: wx.Window | None, orden: str) -> None:
		super().__init__(padre, _("Tecla para {o}").format(o=etiqueta_orden(orden)), redimensionable=False)
		self.tecla = ""
		_c, self.campo = crear_campo(self.panel, _("&Pulse la tecla:"), wx.TextCtrl, style=wx.TE_READONLY,
			size=self.FromDIP(wx.Size(300, -1)), sizer=self.sizer,
			ayuda=_("Pulse la combinación que quiera, por ejemplo Ctrl+Mayús+F5. Tab sale del campo y Escape cancela."))
		self.terminar(wx.OK | wx.CANCEL, foco=self.campo)
		self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, lambda _e: self.aceptar())
		# Se engancha DESPUÉS de preparar_dialogo para ver la tecla antes que él.
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)

	def poner(self, tecla: str) -> None:
		self.tecla = servicio_teclas.normalizar(tecla)
		self.campo.SetValue(nombre_visible(self.tecla))
		anuncios.anunciar(nombre_visible(self.tecla), anuncios.RESULTADO, interrumpir=True)

	def aceptar(self) -> bool:
		if not self.tecla:
			f_comun.avisar(self, _("Pulse primero la tecla en el campo."), self.titulo)
			self.campo.SetFocus()
			return False
		self.cerrar(wx.ID_OK)
		return True

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		from app.ui.teclado_eventos import tecla_de_evento

		if wx.Window.FindFocus() is not self.campo:
			evento.Skip()
			return
		tecla = tecla_de_evento(evento)
		if not tecla or tecla in ("Tab", "Shift+Tab", "Escape"):
			evento.Skip()  # Tab navega; Escape lo atiende preparar_dialogo (cancelar).
			return
		if tecla == "Ctrl+H":
			describir_control_enfocado(self)
			return
		self.poner(tecla)


def capturar_tecla(padre: wx.Window | None, orden: str) -> str | None:
	return f_comun.mostrar(DialogoCapturaTecla(padre, orden), lambda d: d.tecla)


# ── Mapa de teclas ──────────────────────────────────────────────────────────

class DialogoMapaTeclas(f_comun.DialogoF):
	"""Lista de órdenes (Orden, Teclas, Ámbito) con búsqueda. ``personalizadas()`` es lo que se guarda."""

	def __init__(self, padre: wx.Window | None, mapa: servicio_teclas.MapaTeclas, esquema: str | None = None) -> None:
		super().__init__(padre, _("Mapa de teclas"))
		if esquema is None:
			config = getattr(padre, "config", None)
			esquema = config.obtener("teclado.esquema") if config is not None else None
		self.esquema = esquema or "norton"
		self.esquema_importado: str | None = None
		self.por_defecto = _fabrica(self.esquema)
		self.ambitos = ordenes.ambitos()
		self.fijas = ordenes.fijas()
		self.asignadas: dict[str, tuple[str, ...]] = {o.id: tuple(mapa.teclas_de(o.id)) for o in ordenes.CATALOGO}
		self.visibles: list[str] = []
		_b, self.campo = crear_campo(self.panel, _("&Buscar:"), wx.TextCtrl, size=self.FromDIP(wx.Size(480, -1)), sizer=self.sizer,
			ayuda=_("Escriba parte del nombre, de la ayuda o de la tecla (por ejemplo «copiar» o «F5»). Flecha abajo pasa a la lista."))
		self.etiqueta_lista = wx.StaticText(self.panel, label=_("Ó&rdenes:"))
		self.lista = ListaAccesible(self.panel, _("Órdenes"), columnas=[
			(_("Orden"), self.FromDIP(260)), (_("Teclas"), self.FromDIP(180)), (_("Ámbito"), self.FromDIP(120)),
		], virtual=True)
		self.lista.SetMinSize(self.FromDIP(wx.Size(580, 300)))
		self.lista.SetHelpText(_("Izquierda y Derecha leen orden, teclas y ámbito. Intro cambia la tecla de la orden."))
		self.sizer.Add(self.etiqueta_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton(_("Ca&mbiar..."), _("Sustituye las teclas de la orden por la que pulse."), lambda: self._pedir(reemplazar=True), fila)
		self.boton(_("A&ñadir otra tecla..."), _("Añade una tecla más a la orden, sin quitar las que tiene."),
			lambda: self._pedir(reemplazar=False), fila)
		self.boton(_("&Quitar"), _("Deja la orden sin tecla (sigue en los menús y en la paleta)."), self._quitar_elegida, fila)
		self.boton(_("Restablecer &esta"), _("Devuelve a la orden sus teclas de fábrica."), self._restablecer_elegida, fila)
		self.boton(_("Restablecer &todas"), _("Devuelve todas las teclas de fábrica; pide confirmación."), self.restablecer_todas, fila)
		self.boton(_("E&xportar..."), _("Guarda el esquema y las teclas personalizadas en un archivo .zcteclas."), self.exportar, fila)
		self.boton(_("&Importar..."), _("Lee un archivo .zcteclas: su esquema y sus teclas se aplican al aceptar."), lambda: self.importar(None), fila)
		self.sizer.Add(fila, 0)
		self.campo.Bind(wx.EVT_TEXT, lambda _e: self.filtrar())
		self.campo.Bind(wx.EVT_KEY_DOWN, self._al_tecla_campo)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self._pedir(reemplazar=True))
		self.terminar(wx.OK | wx.CANCEL, foco=self.lista)
		self.filtrar()

	# ── Lista ────────────────────────────────────────────────────────────────

	def _fila(self, id_orden: str) -> list[str]:
		return [etiqueta_orden(id_orden), teclas_visibles(self.asignadas.get(id_orden, ())), nombre_ambito(self.ambitos.get(id_orden, ""))]

	def filtrar(self, conservar: str | None = None) -> None:
		palabras = f_comun.normalizar_busqueda(self.campo.GetValue()).split()
		self.visibles = []
		for orden in ordenes.CATALOGO:
			texto = f_comun.normalizar_busqueda(" ".join([*self._fila(orden.id), _(orden.ayuda)]))
			if all(p in texto for p in palabras):
				self.visibles.append(orden.id)
		self.lista.reemplazar_filas([self._fila(o) for o in self.visibles], conservar_foco=False)
		if conservar in self.visibles:
			self.lista.enfocar_fila(self.visibles.index(conservar), anunciar=False)

	def elegida(self) -> str | None:
		fila = self.lista.fila_actual()
		return self.visibles[fila] if 0 <= fila < len(self.visibles) else None

	def _refrescar(self, *ids: str) -> None:
		for id_orden in ids:
			if id_orden in self.visibles:
				self.lista.actualizar_fila(self.visibles.index(id_orden), self._fila(id_orden))

	# ── Cambios (sin ventanas: los usan los botones y las pruebas) ────────────

	def asignar(self, orden: str, tecla: str, reemplazar: bool = True) -> bool:
		"""Da ``tecla`` a ``orden`` si las reglas lo permiten; pregunta si hay que quitársela a otra."""
		tecla = servicio_teclas.normalizar(tecla)
		resultado = comprobar(self.asignadas, self.ambitos, self.fijas, orden, tecla)
		if not resultado.permitida:
			f_comun.avisar(self, resultado.motivo, _("Mapa de teclas"))
			return False
		if resultado.choques:
			nombres = ", ".join(etiqueta_orden(o) for o in resultado.choques)
			if not f_comun.preguntar(self, _("{t} ya es {o}: ¿quitársela?").format(t=nombre_visible(tecla), o=nombres), _("Mapa de teclas")):
				return False
			for otra in resultado.choques:
				self.asignadas[otra] = tuple(t for t in self.asignadas[otra] if t != tecla)
		actuales = () if reemplazar else tuple(t for t in self.asignadas.get(orden, ()) if t != tecla)
		self.asignadas[orden] = (*actuales, tecla)
		self._refrescar(orden, *resultado.choques)
		anuncios.anunciar(_("{o}: {t}").format(o=etiqueta_orden(orden), t=teclas_visibles(self.asignadas[orden])), anuncios.RESULTADO)
		return True

	def quitar(self, orden: str) -> bool:
		if orden in self.fijas:
			f_comun.avisar(self, _("Las teclas de «{o}» son fijas y no se pueden cambiar.").format(o=etiqueta_orden(orden)), _("Mapa de teclas"))
			return False
		self.asignadas[orden] = ()
		self._refrescar(orden)
		anuncios.anunciar(_("{o}: sin tecla").format(o=etiqueta_orden(orden)), anuncios.RESULTADO)
		return True

	def restablecer(self, orden: str) -> bool:
		"""Teclas de fábrica para ``orden``; si otra orden las tiene ahora, se pregunta como al cambiar."""
		fabrica = self.por_defecto.get(orden, ())
		self.asignadas[orden] = ()
		for tecla in fabrica:
			if not self.asignar(orden, tecla, reemplazar=False):
				log.info("Restablecer %s: %s queda sin asignar", orden, tecla)
		self._refrescar(orden)
		return tuple(self.asignadas[orden]) == tuple(fabrica)

	def restablecer_todas(self) -> None:
		if not f_comun.preguntar(self, _("¿Devolver todas las teclas a las de fábrica?"), _("Restablecer todas"), peligroso=True):
			return
		self.asignadas = {o: tuple(t) for o, t in self.por_defecto.items()}
		self.filtrar(self.elegida())
		anuncios.anunciar(_("Teclas de fábrica restablecidas"), anuncios.RESULTADO)

	def personalizadas(self) -> dict[str, list[str]]:
		return personalizadas(self.asignadas, self.por_defecto)

	# ── Exportar e importar (.zcteclas) ───────────────────────────────────────

	def datos_exportar(self) -> dict:
		return {"version": 1, "esquema": self.esquema_importado or self.esquema, "personalizadas": self.personalizadas()}

	def exportar(self) -> bool:
		ruta = _elegir_archivo(self, _("Exportar las teclas"), guardar=True)
		if not ruta:
			return False
		try:
			Path(ruta).write_text(json.dumps(self.datos_exportar(), ensure_ascii=False, indent=2), encoding="utf-8")
		except OSError as error:
			f_comun.avisar(self, _("No se pudo exportar: {e}").format(e=error), _("Mapa de teclas"))
			return False
		anuncios.anunciar(_("Teclas exportadas a {r}").format(r=ruta), anuncios.RESULTADO)
		return True

	def importar(self, ruta: str | None) -> bool:
		"""Lee un ``.zcteclas`` y lo pone en la lista (se guarda al aceptar); pregunta antes cuántas cambian."""
		from app.services import esquemas_teclas

		ruta = ruta or _elegir_archivo(self, _("Importar las teclas"), guardar=False)
		if not ruta:
			return False
		try:
			datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
			if not isinstance(datos, dict) or not isinstance(datos.get("personalizadas", {}), dict):
				raise ValueError(_("no es un archivo de teclas de zCommander"))
			esquema = str(datos.get("esquema") or "norton")
			if esquema not in esquemas_teclas.ESQUEMAS:
				raise ValueError(_("esquema desconocido: {e}").format(e=esquema))
			propias = {str(o): [servicio_teclas.normalizar(t) for t in ts] for o, ts in datos.get("personalizadas", {}).items()
				if str(o) in self.asignadas and str(o) not in self.fijas and isinstance(ts, list)}
		except (OSError, ValueError) as error:
			f_comun.avisar(self, _("No se pudo importar: {e}").format(e=error), _("Mapa de teclas"))
			return False
		fabrica = _fabrica(esquema)
		nuevas = {o: tuple(propias.get(o, fabrica.get(o, ()))) for o in self.asignadas}
		cambian = sum(1 for o in nuevas if tuple(nuevas[o]) != tuple(self.asignadas.get(o, ())))
		if not f_comun.preguntar(self, _("¿Importar las teclas? Esquema {e}; cambian {n} órdenes. Se guarda al aceptar.").format(
				e=esquemas_teclas.nombre(esquema), n=cambian), _("Importar las teclas")):
			return False
		self.por_defecto = fabrica
		self.asignadas = nuevas
		self.esquema_importado = esquema
		self.filtrar(self.elegida())
		anuncios.anunciar(_("Teclas importadas: pulse Aceptar para guardarlas"), anuncios.RESULTADO)
		return True

	# ── Botones ──────────────────────────────────────────────────────────────

	def _pedir(self, reemplazar: bool) -> None:
		orden = self.elegida()
		if orden is None:
			return
		if orden in self.fijas:
			f_comun.avisar(self, _("Las teclas de «{o}» son fijas y no se pueden cambiar.").format(o=etiqueta_orden(orden)), _("Mapa de teclas"))
			return
		tecla = capturar_tecla(self, orden)
		if tecla:
			self.asignar(orden, tecla, reemplazar)
		self.lista.SetFocus()

	def _quitar_elegida(self) -> None:
		orden = self.elegida()
		if orden is not None:
			self.quitar(orden)

	def _restablecer_elegida(self) -> None:
		orden = self.elegida()
		if orden is not None:
			self.restablecer(orden)

	def _al_tecla_campo(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DOWN and evento.GetModifiers() == wx.MOD_NONE and self.visibles:
			self.lista.SetFocus()
			return
		evento.Skip()


def _fabrica(esquema: str | None) -> dict[str, tuple[str, ...]]:
	return {o: tuple(servicio_teclas.normalizar(t) for t in ts) for o, ts in ordenes.teclas_por_defecto(esquema).items()}


def _elegir_archivo(padre: wx.Window | None, titulo: str, guardar: bool) -> str | None:
	comodin = _("Teclas de zCommander (*.zcteclas)|*.zcteclas")
	estilo = (wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) if guardar else (wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
	dialogo = wx.FileDialog(padre, titulo, defaultFile="teclas.zcteclas" if guardar else "", wildcard=comodin, style=estilo)
	try:
		return dialogo.GetPath() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def editar_mapa(padre: wx.Window | None, mapa: servicio_teclas.MapaTeclas, importar: str | None = None) -> dict[str, list[str]] | None:
	"""Teclas personalizadas elegidas, o ``None`` si se cancela.

	Con ``importar`` (Intro sobre un ``.zcteclas``) el diálogo empieza importándolo. Si se importó
	otro esquema, se pone en ``teclado.esquema`` al aceptar (antes de devolver las personalizadas).
	"""
	dialogo = DialogoMapaTeclas(padre, mapa)
	if importar:
		wx.CallAfter(dialogo.importar, importar)

	def al_aceptar(d: DialogoMapaTeclas) -> dict[str, list[str]]:
		config = getattr(padre, "config", None)
		if d.esquema_importado and config is not None and d.esquema_importado != config.obtener("teclado.esquema"):
			config.establecer("teclado.esquema", d.esquema_importado)
		return d.personalizadas()

	return f_comun.mostrar(dialogo, al_aceptar)
