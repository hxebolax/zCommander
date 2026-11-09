# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo de copiar (F5) y mover (F6), sección 8.4.

El diálogo solo recoge lo que la persona quiere; la ventana principal crea la
``OperacionCopiar`` con ``destino()`` y ``opciones()`` y la lanza (al momento
o «en cola», según ``en_cola``). Así el diálogo se prueba sin proveedores ni
hilos.

Accesibilidad:

- El resumen («Copiar 3 archivos y 1 carpeta (45 MB) a:») va en un campo de
  solo lectura con su etiqueta, para poder releerlo; el foco empieza en el
  destino con el texto seleccionado (se escribe encima o se acepta con Intro).
- Intro copia (o mueve) al momento; F2 equivale a «En cola», como en Norton.
- Las letras de acceso no se repiten: «En co&la» y «Ca&ncelar» ceden la «c»
  al campo «Solo los que coinciden &con:».
"""

from __future__ import annotations

import builtins
import logging

import wx

from app.services import formato
from app.services.operaciones.copiar import OpcionesCopia
from app.services.operaciones.modelo import Politica
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def textos_politicas() -> list[tuple[Politica, str]]:
	"""Las 7 políticas en el orden del desplegable."""
	return [
		(Politica.PREGUNTAR, _("Preguntar")),
		(Politica.SOBRESCRIBIR, _("Sobrescribir")),
		(Politica.OMITIR, _("Omitir")),
		(Politica.SOBRESCRIBIR_SI_MAS_ANTIGUO, _("Sobrescribir si es más antiguo")),
		(Politica.SOBRESCRIBIR_SI_CAMBIA_TAMANO, _("Sobrescribir si cambia el tamaño")),
		(Politica.RENOMBRAR_COPIA, _("Renombrar la copia automáticamente")),
		(Politica.RENOMBRAR_EXISTENTE, _("Renombrar el existente automáticamente")),
	]


def componer_resumen(mover: bool, archivos: int, carpetas: int, bytes_total: int | None = None) -> str:
	"""«Copiar 3 archivos y 1 carpeta (45 MB) a:»; sin tamaño si no se conoce."""
	partes = []
	if archivos:
		partes.append(formato.plural(archivos, _("{n} archivo"), _("{n} archivos")))
	if carpetas:
		partes.append(formato.plural(carpetas, _("{n} carpeta"), _("{n} carpetas")))
	que = _(" y ").join(partes) if partes else _("0 elementos")
	if bytes_total is not None and bytes_total >= 0:
		que += f" ({formato.tamano_legible(bytes_total)})"
	plantilla = _("Mover {que} a:") if mover else _("Copiar {que} a:")
	return plantilla.format(que=que)


def normalizar_patron(texto: str) -> str:
	"""«*», «*.*» o vacío equivalen a «todos» (``OpcionesCopia.patron`` vacío)."""
	limpio = texto.strip()
	return "" if limpio in ("", "*", "*.*") else limpio


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


class DialogoCopiar(wx.Dialog):
	"""Destino y opciones de una copia o un movimiento. No lanza la operación.

	:param resumen: texto de ``componer_resumen``.
	:param destino: carpeta del otro panel (o la ruta con el nombre, si es un solo elemento).
	:param configuracion: ``Configuracion`` de la que salen los valores iniciales (por defecto, la global).
	"""

	def __init__(self, padre: wx.Window | None, resumen: str, destino: str, mover: bool = False,
			configuracion=None, patron: str = "*") -> None:
		titulo = _("Mover") if mover else _("Copiar")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		if configuracion is None:
			from app.core.configuracion import obtener_configuracion

			configuracion = obtener_configuracion()
		self._config = configuracion
		self.mover = mover
		#: True si se pulsó «En cola» (o F2).
		self.en_cola = False

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_etiqueta, self.texto_resumen = crear_campo(
			panel, _("&Resumen:"), wx.TextCtrl, value=resumen, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NO_VSCROLL,
			size=panel.FromDIP(wx.Size(480, 40)), ayuda=_("Qué se va a copiar o mover."), sizer=sizer)
		_etiqueta, self.campo_destino = crear_campo(
			panel, _("&Destino:"), wx.TextCtrl, value=destino,
			ayuda=_("Carpeta de destino. Si termina en barra invertida o ya existe, los elementos van dentro; "
				"con un solo elemento, si no existe, es su nombre nuevo."), sizer=sizer)
		_etiqueta, self.campo_patron = crear_campo(
			panel, _("Solo los que coinciden &con:"), wx.TextCtrl, value=patron or "*",
			ayuda=_("Patrón con * y ?; varios separados por punto y coma. * copia todos."), sizer=sizer)

		self._politicas = textos_politicas()
		_etiqueta, self.lista_politica = crear_campo(
			panel, _("&Si el archivo ya existe:"), wx.Choice, choices=[t for _p, t in self._politicas],
			ayuda=_("Qué hacer con los archivos que ya existen en el destino."), sizer=sizer)
		inicial = self._leer("operaciones.politica_conflicto", Politica.PREGUNTAR.value)
		indice = next((i for i, (p, _t) in enumerate(self._politicas) if p.value == inicial), 0)
		self.lista_politica.SetSelection(indice)

		self.casilla_fechas = self._casilla(panel, sizer, _("Conservar &fechas y atributos"), "operaciones.conservar_fechas",
			_("La copia mantiene la fecha de modificación y los atributos del original."))
		self.casilla_verificar = self._casilla(panel, sizer, _("&Verificar después de copiar"), "operaciones.verificar",
			_("Relee origen y copia y compara sus sumas SHA-256. Más lento."))
		self.casilla_enlaces = self._casilla(panel, sizer, _("Copiar los &enlaces como enlaces"), "operaciones.copiar_enlaces",
			_("Si se desactiva, los enlaces y uniones se omiten (nunca se sigue lo que apuntan)."))
		self.casilla_vacias = self._casilla(panel, sizer, _("Copiar también las car&petas vacías"),
			"operaciones.copiar_carpetas_vacias", _("Crea en el destino las carpetas sin archivos."))

		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_aceptar = wx.Button(panel, wx.ID_OK, label=_("&Mover") if mover else _("C&opiar"))
		self.boton_aceptar.SetHelpText(_("Empieza enseguida (Intro)."))
		self.boton_cola = wx.Button(panel, label=_("En co&la"))
		self.boton_cola.SetHelpText(_("Espera a que terminen las demás operaciones puestas en cola (F2)."))
		self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, label=_("Ca&ncelar"))
		for boton in (self.boton_aceptar, self.boton_cola, self.boton_cancelar):
			botones.Add(boton, 0, wx.ALL, 4)
		self.boton_aceptar.SetDefault()
		sizer.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 6)

		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)

		self.boton_aceptar.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar(en_cola=False))
		self.boton_cola.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar(en_cola=True))
		preparar_dialogo(self, foco_inicial=self.campo_destino)
		# Después de preparar_dialogo: wx llama primero al último enlazado.
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()

	def _leer(self, clave: str, por_defecto):
		try:
			return self._config.obtener(clave)
		except Exception:  # noqa: BLE001 - una clave que falta no impide copiar: se usa el valor de fábrica
			log.warning("No se pudo leer %s de la configuración", clave, exc_info=True)
			return por_defecto

	def _casilla(self, panel: wx.Window, sizer: wx.Sizer, etiqueta: str, clave: str, ayuda: str) -> wx.CheckBox:
		casilla = wx.CheckBox(panel, label=etiqueta)
		casilla.SetValue(bool(self._leer(clave, False)))
		casilla.SetHelpText(ayuda)
		sizer.Add(casilla, 0, wx.ALL, 5)
		return casilla

	# ── Resultado ───────────────────────────────────────────────────────────

	def destino(self) -> str:
		return self.campo_destino.GetValue().strip()

	def politica(self) -> Politica:
		indice = self.lista_politica.GetSelection()
		return self._politicas[indice][0] if 0 <= indice < len(self._politicas) else Politica.PREGUNTAR

	def opciones(self) -> OpcionesCopia:
		bloque_kb = self._leer("operaciones.tamano_bloque_kb", 1024)
		return OpcionesCopia(
			patron=normalizar_patron(self.campo_patron.GetValue()),
			politica=self.politica(),
			verificar=self.casilla_verificar.GetValue(),
			conservar_fechas=self.casilla_fechas.GetValue(),
			copiar_enlaces=self.casilla_enlaces.GetValue(),
			carpetas_vacias=self.casilla_vacias.GetValue(),
			lista_conflictos=bool(self._leer("operaciones.lista_conflictos", True)),
			tamano_bloque=int(bloque_kb) * 1024,
		)

	def problema(self) -> str | None:
		"""Lo que impide aceptar, o ``None``."""
		if not self.destino():
			return _("Escriba la carpeta de destino.")
		return None

	def aceptar(self, en_cola: bool = False) -> bool:
		problema = self.problema()
		if problema:
			dialogos.mostrar_error(self, problema, self.GetTitle())
			self.campo_destino.SetFocus()
			return False
		self.en_cola = en_cola
		_terminar(self, wx.ID_OK)
		return True

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F2 and evento.GetModifiers() == wx.MOD_NONE:
			self.aceptar(en_cola=True)
			return
		evento.Skip()
