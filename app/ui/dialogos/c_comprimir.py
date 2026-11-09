# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos de Comprimir (Alt+F5) y Extraer (Alt+F9), sección 8.15.

Como el de copiar, solo recogen lo que la persona quiere: la acción de
``app/ui/acciones/comprimidos_c.py`` crea y lanza la operación. Así se prueban
sin proveedores ni hilos.

Accesibilidad:

- Cada campo tiene su etiqueta creada justo antes (``crear_campo``) y su letra
  de acceso; ninguna se repite en el diálogo (lo comprueba ``revisar_teclado``
  en ``tests/ui/test_c_dialogos.py``).
- Al cambiar el formato, el nombre del comprimido cambia de extensión y los
  campos de contraseña se activan solo con 7z y con «ZIP cifrado con
  AES-256»; la ayuda de Ctrl+H lo explica.
- 2.0 (8.6): más formatos; «Cifrar también los nom&bres» (solo 7z); «M&otor:»,
  texto de solo lectura que dice qué programa crea el comprimido. Los
  formatos de un solo archivo (.gz, .bz2, .xz, .zst) crean uno por elemento:
  la casilla «un comprimido por cada elemento» queda marcada y sin cambiar, y
  con carpetas en la selección esos formatos no aparecen (lo dice la ayuda).
- Intro acepta; F2 equivale a «En cola», como en copiar.
"""

from __future__ import annotations

import builtins
import logging
import os

import wx

from app.services import comprimir as servicio
from app.services.operaciones.modelo import Politica
from app.services.vfs import rutas
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos.copiar import normalizar_patron, textos_politicas

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def terminar(dialogo: wx.Dialog, codigo: int) -> None:
	"""Cierra con ``codigo`` (también si no es modal, como en las pruebas)."""
	if dialogo.IsModal():
		dialogo.EndModal(codigo)
	else:
		dialogo.SetReturnCode(codigo)


def _cuadro(dialogo: wx.Dialog, panel: wx.Panel, sizer: wx.Sizer, botones: list[wx.Button]) -> None:
	fila = wx.BoxSizer(wx.HORIZONTAL)
	for boton in botones:
		fila.Add(boton, 0, wx.ALL, 4)
	sizer.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
	panel.SetSizer(sizer)
	marco = wx.BoxSizer(wx.VERTICAL)
	marco.Add(panel, 1, wx.EXPAND)
	dialogo.SetSizerAndFit(marco)


def _campo_resumen(panel: wx.Window, sizer: wx.Sizer, resumen: str, ayuda: str) -> wx.TextCtrl:
	_etiqueta, campo = crear_campo(panel, _("&Resumen:"), wx.TextCtrl, value=resumen,
		style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NO_VSCROLL, size=panel.FromDIP(wx.Size(480, 40)), ayuda=ayuda, sizer=sizer)
	return campo


class DialogoComprimir(wx.Dialog):
	"""Nombre, formato, nivel y contraseña del comprimido. No lanza la operación.

	:param resumen: «Comprimir 3 archivos y 1 carpeta (45 MB)».
	:param destino: ruta propuesta del comprimido (con extensión .zip).
	:param hay_carpetas: hay carpetas en la selección (los formatos de un solo archivo no se ofrecen).
	"""

	def __init__(self, padre: wx.Window | None, resumen: str, destino: str, formato: str = "zip", nivel: str = "normal",
			hay_carpetas: bool = False) -> None:
		super().__init__(padre, title=_("Comprimir"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=_("Comprimir"))
		self.en_cola = False
		self._formatos = servicio.textos_formatos(hay_carpetas)
		#: Último nombre de comprimido (para volver a él al dejar un formato de un solo archivo).
		self._destino_comprimido = destino
		self._niveles = servicio.textos_niveles()
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.texto_resumen = _campo_resumen(panel, sizer, resumen, _("Qué se va a comprimir."))
		_etiqueta, self.campo_destino = crear_campo(panel, _("&Archivo comprimido:"), wx.TextCtrl, value=destino,
			ayuda=_("Ruta del comprimido que se crea. Si ya existe, se pregunta si añadir a él o sustituirlo. "
				"Con «un comprimido por cada elemento», la carpeta donde se crean."), sizer=sizer)
		ayuda_formato = _("ZIP lo abre cualquier sistema; 7z comprime más y admite contraseña; TAR es el habitual en Linux. "
			"ZIP (Zstandard) es más rápido pero algunos programas antiguos no lo abren. ISO crea una imagen de disco. "
			".gz, .bz2, .xz y .zst comprimen cada archivo por separado.")
		if hay_carpetas:
			ayuda_formato += " " + _(".gz, .bz2, .xz y .zst no aparecen porque hay carpetas en la selección: "
				"solo comprimen archivos sueltos.")
		_etiqueta, self.lista_formato = crear_campo(panel, _("&Formato:"), wx.Choice, choices=[t for _f, t in self._formatos],
			ayuda=ayuda_formato, sizer=sizer)
		self.lista_formato.SetSelection(next((i for i, (f, _t) in enumerate(self._formatos) if f == formato), 0))
		_etiqueta, self.lista_nivel = crear_campo(panel, _("&Nivel de compresión:"), wx.Choice, choices=[t for _n, t in self._niveles],
			ayuda=_("Máximo tarda más y ocupa menos. Sin compresión solo agrupa los archivos."), sizer=sizer)
		self.lista_nivel.SetSelection(next((i for i, (n, _t) in enumerate(self._niveles) if n == nivel), 2))
		_etiqueta, self.campo_contrasena = crear_campo(panel, _("Con&traseña (7z y ZIP con AES):"), wx.TextCtrl,
			style=wx.TE_PASSWORD, ayuda=_("Cifra el contenido con AES-256. En 7z, vacía es sin contraseña; el ZIP cifrado la necesita."),
			sizer=sizer)
		_etiqueta, self.campo_confirmar = crear_campo(panel, _("Confirmar contra&seña:"), wx.TextCtrl, style=wx.TE_PASSWORD,
			ayuda=_("Escriba otra vez la contraseña para evitar errores de tecleo."), sizer=sizer)
		self.casilla_cifrar_nombres = wx.CheckBox(panel, label=_("Cifrar también los nom&bres"))
		self.casilla_cifrar_nombres.SetHelpText(_("Solo 7z con contraseña: sin ella no se puede ni ver qué archivos contiene."))
		sizer.Add(self.casilla_cifrar_nombres, 0, wx.ALL, 5)
		self.casilla_por_elemento = wx.CheckBox(panel, label=_("Un comprimido por cada &elemento"))
		self.casilla_por_elemento.SetHelpText(_("Crea un comprimido con el nombre de cada elemento en lugar de uno con todos. "
			"Si alguno ya existe, se pregunta si añadir, sustituir, cambiar el nombre u omitir."))
		sizer.Add(self.casilla_por_elemento, 0, wx.ALL, 5)
		self.casilla_mover = wx.CheckBox(panel, label=_("Mo&ver al comprimido (borra los originales)"))
		self.casilla_mover.SetHelpText(_("Al terminar, prueba el comprimido y, si está bien, borra definitivamente los originales."))
		sizer.Add(self.casilla_mover, 0, wx.ALL, 5)
		_etiqueta, self.texto_motor = crear_campo(panel, _("M&otor:"), wx.TextCtrl, style=wx.TE_READONLY,
			ayuda=_("Qué programa crea el comprimido: Python, libarchive o el 7za que trae zCommander."), sizer=sizer)

		self.boton_aceptar = wx.Button(panel, wx.ID_OK, label=_("Co&mprimir"))
		self.boton_aceptar.SetHelpText(_("Empieza enseguida (Intro)."))
		self.boton_cola = wx.Button(panel, label=_("En co&la"))
		self.boton_cola.SetHelpText(_("Espera a que terminen las demás operaciones puestas en cola (F2)."))
		self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, label=_("&Cancelar"))
		self.boton_aceptar.SetDefault()
		_cuadro(self, panel, sizer, [self.boton_aceptar, self.boton_cola, self.boton_cancelar])

		self.lista_formato.Bind(wx.EVT_CHOICE, self._al_cambiar_formato)
		self.boton_aceptar.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar(en_cola=False))
		self.boton_cola.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar(en_cola=True))
		self._actualizar_contrasena()
		preparar_dialogo(self, foco_inicial=self.campo_destino)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()

	# ── Valores ─────────────────────────────────────────────────────────────

	def _clave(self) -> str:
		indice = self.lista_formato.GetSelection()
		return self._formatos[indice][0] if 0 <= indice < len(self._formatos) else "zip"

	def formato(self) -> str:
		"""«zip», «7z», «tar.gz»... (la variante del ZIP va aparte)."""
		return servicio.separar(self._clave())[0]

	def variante(self) -> str:
		"""Solo ZIP: «zstd», «aes» o vacío."""
		return servicio.separar(self._clave())[1]

	def nivel(self) -> str:
		indice = self.lista_nivel.GetSelection()
		return self._niveles[indice][0] if 0 <= indice < len(self._niveles) else "normal"

	def destino(self) -> str:
		return self.campo_destino.GetValue().strip().strip('"')

	def contrasena(self) -> str:
		return self.campo_contrasena.GetValue() if servicio.admite_contrasena(self.formato(), self.variante()) else ""

	def opciones(self):
		from app.services.operaciones.comprimir import OpcionesComprimir

		flujo = servicio.es_flujo(self.formato())
		cifrar_nombres = self.formato() == "7z" and bool(self.contrasena()) and self.casilla_cifrar_nombres.GetValue()
		return OpcionesComprimir(formato=self.formato(), nivel=self.nivel(), contrasena=self.contrasena(),
			por_elemento=flujo or self.casilla_por_elemento.GetValue(), mover=self.casilla_mover.GetValue(),
			variante=self.variante(), cifrar_nombres=cifrar_nombres)

	def _al_cambiar_formato(self, evento: wx.CommandEvent) -> None:
		texto = self.destino()
		if servicio.es_flujo(self.formato()):
			if texto and not self.casilla_por_elemento.GetValue():
				# Uno por elemento: el campo pasa a ser la carpeta donde se crean.
				self._destino_comprimido = texto
				self.campo_destino.SetValue(os.path.dirname(texto) or texto)
			self.casilla_por_elemento.SetValue(True)
		elif not self.casilla_por_elemento.IsEnabled():
			# Se deja un formato de un solo archivo: vuelve el nombre del comprimido.
			self.casilla_por_elemento.SetValue(False)
			self.campo_destino.SetValue(servicio.cambiar_extension(self._destino_comprimido, self.formato()))
		elif texto and not self.casilla_por_elemento.GetValue():
			self.campo_destino.SetValue(servicio.cambiar_extension(texto, self.formato()))
		self._actualizar_contrasena()
		evento.Skip()

	def _actualizar_contrasena(self) -> None:
		formato, variante = self.formato(), self.variante()
		activa = servicio.admite_contrasena(formato, variante)
		self.campo_contrasena.Enable(activa)
		self.campo_confirmar.Enable(activa)
		self.casilla_cifrar_nombres.Enable(formato == "7z")
		self.casilla_por_elemento.Enable(not servicio.es_flujo(formato))
		try:
			self.texto_motor.SetValue(servicio.motor(formato, variante))
		except Exception:  # noqa: BLE001 - el texto del motor es informativo: si falla, se deja vacío
			log.warning("No se pudo saber el motor de %s", formato, exc_info=True)
			self.texto_motor.SetValue("")

	def problema(self) -> str | None:
		destino = self.destino()
		if not destino:
			return _("Escriba el nombre del comprimido.")
		if not self.casilla_por_elemento.GetValue():
			problema = rutas.problema_en_nombre(os.path.basename(destino.rstrip("\\/")))
			if problema:
				return problema
		protegido = servicio.admite_contrasena(self.formato(), self.variante())
		if protegido and self.campo_contrasena.GetValue() != self.campo_confirmar.GetValue():
			return _("Las dos contraseñas no coinciden.")
		if self.variante() == "aes" and not self.campo_contrasena.GetValue():
			return _("Escriba la contraseña del ZIP cifrado.")
		return None

	def aceptar(self, en_cola: bool = False) -> bool:
		problema = self.problema()
		if problema:
			dialogos.mostrar_error(self, problema, self.GetTitle())
			self.campo_destino.SetFocus()
			return False
		self.en_cola = en_cola
		terminar(self, wx.ID_OK)
		return True

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F2 and evento.GetModifiers() == wx.MOD_NONE:
			self.aceptar(en_cola=True)
			return
		evento.Skip()


class DialogoExtraer(wx.Dialog):
	"""Destino, patrón, conflictos y contraseña de una extracción. No lanza la operación.

	:param configuracion: de ella sale la política de conflictos inicial (por defecto, la global).
	:param varios: hay más de un comprimido (o se extrae desde fuera): se ofrece «cada uno en su carpeta».
	"""

	def __init__(self, padre: wx.Window | None, resumen: str, destino: str, configuracion=None, por_carpeta: bool = False) -> None:
		super().__init__(padre, title=_("Extraer"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=_("Extraer"))
		if configuracion is None:
			from app.core.configuracion import obtener_configuracion

			configuracion = obtener_configuracion()
		self._config = configuracion
		self.en_cola = False
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.texto_resumen = _campo_resumen(panel, sizer, resumen, _("Qué se va a extraer."))
		_etiqueta, self.campo_destino = crear_campo(panel, _("&Destino:"), wx.TextCtrl, value=destino,
			ayuda=_("Carpeta donde se extrae. Si no existe, se crea."), sizer=sizer)
		_etiqueta, self.campo_patron = crear_campo(panel, _("Solo los que coinciden &con:"), wx.TextCtrl, value="*",
			ayuda=_("Patrón con * y ?; varios separados por punto y coma. * extrae todos."), sizer=sizer)
		self._politicas = textos_politicas()
		_etiqueta, self.lista_politica = crear_campo(panel, _("&Si el archivo ya existe:"), wx.Choice,
			choices=[t for _p, t in self._politicas], ayuda=_("Qué hacer con los archivos que ya existen en el destino."), sizer=sizer)
		inicial = self._leer("operaciones.politica_conflicto", Politica.PREGUNTAR.value)
		self.lista_politica.SetSelection(next((i for i, (p, _t) in enumerate(self._politicas) if p.value == inicial), 0))
		self.casilla_por_carpeta = wx.CheckBox(panel, label=_("Cada comprimido en su &propia carpeta"))
		self.casilla_por_carpeta.SetHelpText(_("Crea en el destino una carpeta con el nombre de cada comprimido y lo extrae dentro."))
		self.casilla_por_carpeta.SetValue(por_carpeta)
		sizer.Add(self.casilla_por_carpeta, 0, wx.ALL, 5)
		_etiqueta, self.campo_contrasena = crear_campo(panel, _("Con&traseña (si la pide):"), wx.TextCtrl, style=wx.TE_PASSWORD,
			ayuda=_("Opcional. Si el comprimido tiene contraseña y no se escribe aquí o no es correcta, se pregunta."), sizer=sizer)

		self.boton_aceptar = wx.Button(panel, wx.ID_OK, label=_("E&xtraer"))
		self.boton_aceptar.SetHelpText(_("Empieza enseguida (Intro)."))
		self.boton_cola = wx.Button(panel, label=_("En co&la"))
		self.boton_cola.SetHelpText(_("Espera a que terminen las demás operaciones puestas en cola (F2)."))
		self.boton_cancelar = wx.Button(panel, wx.ID_CANCEL, label=_("Ca&ncelar"))
		self.boton_aceptar.SetDefault()
		_cuadro(self, panel, sizer, [self.boton_aceptar, self.boton_cola, self.boton_cancelar])

		self.boton_aceptar.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar(en_cola=False))
		self.boton_cola.Bind(wx.EVT_BUTTON, lambda _e: self.aceptar(en_cola=True))
		preparar_dialogo(self, foco_inicial=self.campo_destino)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()

	def _leer(self, clave: str, por_defecto):
		try:
			return self._config.obtener(clave)
		except Exception:  # noqa: BLE001 - una clave que falta no impide extraer: se usa el valor de fábrica
			log.warning("No se pudo leer %s de la configuración", clave, exc_info=True)
			return por_defecto

	def destino(self) -> str:
		return self.campo_destino.GetValue().strip().strip('"')

	def patron(self) -> str:
		return normalizar_patron(self.campo_patron.GetValue())

	def politica(self) -> Politica:
		indice = self.lista_politica.GetSelection()
		return self._politicas[indice][0] if 0 <= indice < len(self._politicas) else Politica.PREGUNTAR

	def por_carpeta(self) -> bool:
		return self.casilla_por_carpeta.GetValue()

	def contrasena(self) -> str:
		return self.campo_contrasena.GetValue()

	def problema(self) -> str | None:
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
		terminar(self, wx.ID_OK)
		return True

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F2 and evento.GetModifiers() == wx.MOD_NONE:
			self.aceptar(en_cola=True)
			return
		evento.Skip()
