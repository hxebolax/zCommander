# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Editor interno de texto (F4 y Mayús+F4), sección 8.3 del diseño (bloque A).

Ventana propia, no modal, con un ``wx.TextCtrl`` multilínea editable
(``TE_RICH2``: admite archivos grandes y deshacer de varios pasos). Por qué
está hecho así:

- **Se conserva el formato del archivo**: codificación, fin de línea (CRLF,
  LF o CR) y BOM se detectan al abrir (``leer_formato``) y se vuelven a
  aplicar al guardar (``codificar``). En el control los saltos son siempre
  «\\n»; solo «Guardar como» cambia el formato, y lo dice.
- **Guardado seguro**: en el disco se escribe a un temporal ``~zc*.tmp`` en
  la misma carpeta y se pone en lugar del original con ``ReplaceFileW``
  (``copia_nativa.sustituir``), que conserva los permisos; si algo falla, el
  original queda intacto. Antes se comprueba (en un hilo) si el archivo
  cambió en el disco desde que se abrió y, si es así, se pregunta. La copia
  ``.bak`` es opcional (``editor.copia_seguridad``).
- **Comprimidos**: se pueden leer y editar, pero no guardar dentro; Guardar
  lleva a «Guardar como» en una carpeta del disco. **Servidores**: Guardar
  sube el archivo tras confirmarlo.
- **Nunca se pierden cambios sin preguntar**: al cerrar la ventana y también
  al cerrar la ventana principal (que destruiría el editor sin avisar) se
  ofrece Guardar, No guardar o Cancelar.
- **Sin ajuste de línea**: así una línea del lector es una línea del archivo,
  y la barra de estado puede decir la línea y la columna reales sin recorrer
  todo el texto en cada pulsación.
- Mayús+Intro en un RichEdit inserta un salto «blando» que el lector lee como
  un carácter raro; aquí inserta un salto normal.
"""

from __future__ import annotations

import builtins
import codecs
import logging
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

import wx

from app.core.tareas import TareaCancelada
from app.services import codificacion, formato
from app.services.operaciones import nombres
from app.services.vfs import base, rutas
from app.ui import anuncios
from app.ui.accesibilidad import dialogos
from app.ui.dialogos import a_buscar
from app.ui.dialogos.a_formato import NOMBRE_FIN_DE_LINEA
from app.ui.ventanas.visor import MapaPosiciones, configuracion_de, fuente_monoespaciada, mensaje_error, tareas_de

log = logging.getLogger(__name__)

#: Por encima de este tamaño el editor no abre el archivo (el visor sí, por bloques).
LIMITE_EDITOR = 64 * 1024 * 1024

_BOMS = {"utf-8": codecs.BOM_UTF8, "utf-16-le": codecs.BOM_UTF16_LE, "utf-16-be": codecs.BOM_UTF16_BE}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Formato del archivo (sin wx) ──────────────────────────────────────────────


@dataclass(frozen=True)
class FormatoTexto:
	"""Cómo está escrito el archivo en el disco."""

	codificacion: str = "utf-8"
	fin_de_linea: str = "\r\n"
	bom: bool = False

	def describir(self) -> str:
		nombre = codificacion.NOMBRES.get(self.codificacion, self.codificacion)
		if self.bom:
			nombre += _(" con BOM")
		return nombre


def leer_formato(datos: bytes) -> tuple[str, FormatoTexto]:
	"""(texto con saltos «\\n», formato) de los bytes de un archivo.

	Un archivo vacío queda como UTF-8 sin BOM y con CRLF (lo habitual en Windows).
	"""
	detectada = codificacion.detectar(datos)
	con_bom = codificacion.bom_de(datos)[0] == detectada
	texto, usada = codificacion.decodificar(datos, detectada)
	fin = codificacion.fin_de_linea(texto)
	return texto.replace("\r\n", "\n").replace("\r", "\n"), FormatoTexto(usada, fin, con_bom)


def codificar(texto: str, formato_: FormatoTexto) -> bytes:
	"""Bytes para guardar ``texto`` con ``formato_``. Lanza ``UnicodeEncodeError`` si algún carácter no cabe."""
	cuerpo = texto.replace("\r\n", "\n").replace("\r", "\n")
	if formato_.fin_de_linea != "\n":
		cuerpo = cuerpo.replace("\n", formato_.fin_de_linea)
	datos = cuerpo.encode(formato_.codificacion)
	if formato_.bom and formato_.codificacion in _BOMS:
		datos = _BOMS[formato_.codificacion] + datos
	return datos


def guardar_local(ruta: str, datos: bytes, copia_seguridad: bool = False) -> None:
	"""Escribe ``datos`` en ``ruta`` sin arriesgar el original (temporal y sustitución)."""
	from app.services.windows import copia_nativa

	ruta = rutas.normalizar(ruta)
	carpeta = os.path.dirname(ruta)
	temporal = os.path.join(carpeta, nombres.temporal())
	try:
		with open(rutas.con_prefijo_largo(temporal), "wb") as salida:
			salida.write(datos)
			salida.flush()
			os.fsync(salida.fileno())
		if copia_seguridad and os.path.exists(rutas.con_prefijo_largo(ruta)):
			shutil.copy2(rutas.con_prefijo_largo(ruta), rutas.con_prefijo_largo(ruta + ".bak"))
		copia_nativa.sustituir(temporal, ruta)
	except BaseException:
		try:
			if os.path.exists(rutas.con_prefijo_largo(temporal)):
				os.remove(rutas.con_prefijo_largo(temporal))
		except OSError:
			log.warning("No se pudo borrar el temporal %s", temporal, exc_info=True)
		raise


def marca_local(ruta: str) -> tuple[int, int] | None:
	"""(fecha en ns, tamaño) del archivo en el disco, o ``None`` si no existe."""
	try:
		estado = os.stat(rutas.con_prefijo_largo(ruta))
	except OSError:
		return None
	return estado.st_mtime_ns, estado.st_size


# ── Ventana ─────────────────────────────────────────────────────────────────────

TECLAS_EDITOR = (
	"Teclas del editor:\n"
	"F2 o Ctrl+S: guardar. Mayús+F2: guardar como.\n"
	"Ctrl+Z: deshacer. Ctrl+Y: rehacer.\n"
	"Ctrl+X, Ctrl+C y Ctrl+V: cortar, copiar y pegar. Ctrl+A: seleccionar todo.\n"
	"F7 o Ctrl+F: buscar. F3 o Mayús+F7: buscar siguiente. Mayús+F3: buscar anterior.\n"
	"Ctrl+R: reemplazar. Ctrl+G: ir a una línea.\n"
	"F5: insertar la fecha y la hora.\n"
	"Ctrl+Mayús+I: decir la barra de estado.\n"
	"Ctrl+H: ayuda del control enfocado.\n"
	"Escape o F10: cerrar (si hay cambios, pregunta)."
)


class VentanaEditor(wx.Frame):
	"""Editor de un archivo de cualquier proveedor.

	:param proveedor, ruta: el archivo (debe existir; Mayús+F4 lo crea antes).
	:param config: ``Configuracion`` (claves ``editor.*``).
	:param tareas: ``GestorTareas``; por defecto, el de la ventana principal.
	"""

	def __init__(self, padre: wx.Window | None, proveedor: base.Proveedor, ruta: str, config=None, tareas=None) -> None:
		self.proveedor = proveedor
		self.ruta = ruta
		self.nombre = proveedor.nombre(ruta) or ruta
		super().__init__(padre, title=self._titulo(False), name=_("Editor"))
		self.SetSize(self.FromDIP(wx.Size(900, 650)))
		self.config = config or configuracion_de(padre)
		self.tareas = tareas or tareas_de(padre)
		self.formato = FormatoTexto()
		self.cargado = False
		self._marca: Any = None
		self._guardando = False
		self._cerrando = False
		self._tareas: list[Any] = []
		self._reemplazar: a_buscar.DialogoReemplazar | None = None
		self._modificado_mostrado = False
		self.puntos = int(self.config.obtener("editor.tamano_fuente"))

		self.panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.etiqueta = wx.StaticText(self.panel, label=_("&Texto de {n}:").format(n=self.nombre))
		self.texto = wx.TextCtrl(self.panel, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_PROCESS_TAB | wx.TE_NOHIDESEL | wx.TE_DONTWRAP,
			name=_("Texto de {n}").format(n=self.nombre))
		self.texto.SetHelpText(_("Texto del archivo. F2 guarda, F7 busca, Ctrl+R reemplaza y Escape cierra."))
		self.texto.SetFont(fuente_monoespaciada(self.puntos))
		self.texto.SetEditable(False)
		self.texto.ChangeValue(_("Cargando..."))
		sizer.Add(self.etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		sizer.Add(self.texto, 1, wx.EXPAND | wx.ALL, 6)
		self.panel.SetSizer(sizer)
		self._crear_menus()
		self.barra = self.CreateStatusBar(4)
		self.barra.SetStatusWidths([-3, -3, -2, -2])

		self.texto.Bind(wx.EVT_TEXT, self._al_cambiar_texto)
		self.texto.Bind(wx.EVT_KEY_DOWN, self._al_bajar_tecla)
		self.texto.Bind(wx.EVT_KEY_UP, self._al_mover)
		self.texto.Bind(wx.EVT_LEFT_UP, self._al_mover)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
		self._principal = padre.GetTopLevelParent() if padre is not None else None
		if self._principal is not None:
			# La ventana principal destruye a sus hijas al cerrarse: antes hay que preguntar por los cambios.
			self._principal.Bind(wx.EVT_CLOSE, self._al_cerrar_principal)
		self._cancelar_suscripcion = self.config.suscribir(self._al_cambiar_config, "editor.")
		self.cargar()

	# Estado del archivo --------------------------------------------------------

	@property
	def en_comprimido(self) -> bool:
		return self.proveedor.contenedor is not None or not self.proveedor.capacidades.escribir

	@property
	def es_remoto(self) -> bool:
		return self.proveedor.ruta_local(self.ruta) is None and not self.en_comprimido

	def modificado(self) -> bool:
		return self.cargado and self.texto.IsModified()

	def _titulo(self, modificado: bool) -> str:
		nombre = self.nombre + (_(" (modificado)") if modificado else "")
		return _("{n} - Editor").format(n=nombre)

	def _al_cambiar_texto(self, evento: wx.CommandEvent) -> None:
		evento.Skip()
		if self.cargado and self.texto.IsModified() != self._modificado_mostrado:
			self._modificado_mostrado = self.texto.IsModified()
			self.SetTitle(self._titulo(self._modificado_mostrado))
		self._actualizar_estado()

	def _marcar_guardado(self) -> None:
		self.texto.SetModified(False)
		self._modificado_mostrado = False
		self.SetTitle(self._titulo(False))
		self._actualizar_estado()

	# Construcción -------------------------------------------------------------

	def _crear_menus(self) -> None:
		barra = wx.MenuBar()
		archivo = wx.Menu()
		self._item(archivo, _("&Guardar\tF2"), _("Guarda el archivo con su codificación y fin de línea (también Ctrl+S)."), self.guardar)
		self._item(archivo, _("Guardar &como...\tShift+F2"), _("Guarda en otro archivo y permite cambiar el formato."),
			self.guardar_como)
		self._item(archivo, _("&Volver a cargar"), _("Descarta los cambios y vuelve a leer el archivo."), self.volver_a_cargar)
		archivo.AppendSeparator()
		self._item(archivo, _("C&errar\tEscape"), _("Cierra el editor (también F10). Si hay cambios, pregunta."), self.Close)
		barra.Append(archivo, _("&Archivo"))
		edicion = wx.Menu()
		self._item(edicion, _("&Deshacer\tCtrl+Z"), _("Deshace el último cambio."), lambda: self.texto.Undo())
		self._item(edicion, _("R&ehacer\tCtrl+Y"), _("Vuelve a hacer lo deshecho."), lambda: self.texto.Redo())
		edicion.AppendSeparator()
		self._item(edicion, _("Cor&tar\tCtrl+X"), _("Corta el texto seleccionado."), lambda: self.texto.Cut())
		self._item(edicion, _("&Copiar\tCtrl+C"), _("Copia el texto seleccionado."), lambda: self.texto.Copy())
		self._item(edicion, _("&Pegar\tCtrl+V"), _("Pega el texto del portapapeles."), self._pegar)
		self._item(edicion, _("Seleccionar t&odo\tCtrl+A"), _("Selecciona todo el texto."), lambda: self.texto.SelectAll())
		edicion.AppendSeparator()
		self._item(edicion, _("&Buscar...\tF7"), _("Busca un texto (también Ctrl+F)."), self.buscar)
		self._item(edicion, _("Buscar &siguiente\tF3"), _("Repite la búsqueda hacia delante (también Mayús+F7)."),
			lambda: self.repetir_busqueda(False))
		self._item(edicion, _("Buscar &anterior\tShift+F3"), _("Repite la búsqueda hacia atrás."), lambda: self.repetir_busqueda(True))
		self._item(edicion, _("&Reemplazar...\tCtrl+R"), _("Busca un texto y lo cambia por otro."), self.mostrar_reemplazar)
		self._item(edicion, _("&Ir a la línea...\tCtrl+G"), _("Lleva el cursor a una línea."), self.ir_a)
		self._item(edicion, _("Insertar la &fecha y la hora\tF5"), _("Escribe la fecha y la hora actuales en el cursor."),
			self.insertar_fecha)
		barra.Append(edicion, _("&Edición"))
		herramientas = wx.Menu()
		self._item(herramientas, _("&Contar líneas, palabras y caracteres"), _("Muestra cuántas líneas, palabras y caracteres hay."),
			self.contar)
		self._item(herramientas, _("A&umentar la letra"), _("Letra más grande en todos los editores."), lambda: self.cambiar_letra(2))
		self._item(herramientas, _("&Reducir la letra"), _("Letra más pequeña en todos los editores."), lambda: self.cambiar_letra(-2))
		self._item(herramientas, _("&Decir la barra de estado\tCtrl+Shift+I"),
			_("Dice la línea, la columna, la codificación y si hay cambios."), self.decir_estado)
		barra.Append(herramientas, _("&Herramientas"))
		ayuda = wx.Menu()
		self._item(ayuda, _("&Teclas del editor"), _("Muestra la lista de teclas de esta ventana."),
			lambda: dialogos.mostrar_mensaje(self, _(TECLAS_EDITOR), _("Teclas")))
		self._item(ayuda, _("Ayuda del &control enfocado\tCtrl+H"), _("Explica para qué sirve el control que tiene el foco."),
			self._ayuda_contextual)
		barra.Append(ayuda, _("A&yuda"))
		self.SetMenuBar(barra)

	def _item(self, menu: wx.Menu, etiqueta: str, ayuda: str, accion: Callable[[], Any]) -> wx.MenuItem:
		item = menu.Append(wx.ID_ANY, etiqueta, ayuda)
		self.Bind(wx.EVT_MENU, lambda _e: accion(), item)
		return item

	def _ayuda_contextual(self) -> None:
		from app.ui.accesibilidad.ayuda import describir_control_enfocado

		describir_control_enfocado(self)

	def mostrar(self) -> None:
		self.Show()
		self.Raise()
		self.texto.SetFocus()

	# Hilos ------------------------------------------------------------------

	def _enviar(self, trabajo, al_terminar, nombre: str, al_fallar=None) -> None:
		def fallo(error: BaseException) -> None:
			if isinstance(error, TareaCancelada) or self._cerrando or not self:
				return
			log.warning("Fallo en el editor (%s): %s", nombre, error)
			if al_fallar is not None:
				al_fallar(error)
			else:
				dialogos.mostrar_error(self, mensaje_error(error))

		def listo(resultado) -> None:
			if self._cerrando or not self:
				return
			al_terminar(resultado)

		tarea = self.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre=nombre)
		if tarea is not None:
			self._tareas = [t for t in self._tareas if not t.terminada] + [tarea]

	# Carga ---------------------------------------------------------------------

	def cargar(self) -> None:
		"""Lee el archivo en un hilo (de cualquier proveedor) y detecta su formato."""
		proveedor, ruta = self.proveedor, self.ruta

		def trabajo(tarea):
			info = proveedor.info(ruta)
			if info.tamano > LIMITE_EDITOR:
				raise base.ErrorArchivos(_("«{n}» ocupa {t}: es demasiado grande para el editor. Ábralo con el visor (F3).").format(
					n=info.nombre, t=formato.tamano_legible(info.tamano)), ruta)
			partes = []
			with proveedor.abrir_lectura(ruta) as flujo:
				while True:
					base.comprobar(tarea)
					trozo = flujo.read(1024 * 1024)
					if not trozo:
						break
					partes.append(trozo)
			datos = b"".join(partes)
			local = proveedor.ruta_local(ruta)
			marca = marca_local(local) if local else (info.modificado, info.tamano)
			texto, formato_ = leer_formato(datos)
			return texto, formato_, marca, codificacion.es_binario(datos[:65536])

		def listo(resultado) -> None:
			texto, formato_, marca, binario = resultado
			if binario and not self._confirmar_binario():
				self._cerrando = True
				self.Destroy()
				return
			self.formato, self._marca = formato_, marca
			self.texto.SetEditable(True)
			self.texto.ChangeValue(texto)
			self.texto.SetInsertionPoint(0)
			self.cargado = True
			self._marcar_guardado()
			if self.en_comprimido:
				anuncios.anunciar(_("El archivo está en un comprimido: al guardar se pedirá una carpeta del disco"), anuncios.NORMAL)

		def fallo(error: BaseException) -> None:
			texto = _("No se pudo abrir «{n}»: {e}").format(n=self.nombre, e=mensaje_error(error))
			self.texto.ChangeValue(texto)
			anuncios.anunciar(texto, anuncios.ESENCIAL)

		self.cargado = False
		self.texto.SetEditable(False)
		self.texto.ChangeValue(_("Cargando..."))
		self._enviar(trabajo, listo, "editor-cargar", fallo)

	def _confirmar_binario(self) -> bool:
		pregunta = _("«{n}» no parece un archivo de texto: editarlo y guardarlo puede dañarlo. ¿Abrirlo igualmente?").format(n=self.nombre)
		return dialogos.confirmar(self, pregunta, _("Editar"), peligroso=True) == wx.ID_YES

	def volver_a_cargar(self) -> None:
		if self.modificado() and dialogos.confirmar(self, _("Se perderán los cambios sin guardar. ¿Volver a cargar el archivo?"),
				_("Volver a cargar"), peligroso=True) != wx.ID_YES:
			return
		self.cargar()

	# Guardar -------------------------------------------------------------------

	def _datos_para(self, formato_: FormatoTexto) -> tuple[bytes, FormatoTexto] | None:
		"""Codifica el texto; si algún carácter no cabe, ofrece UTF-8. ``None`` si se cancela."""
		texto = self.texto.GetValue()
		try:
			return codificar(texto, formato_), formato_
		except UnicodeEncodeError as error:
			caracter = texto[error.start] if error.start < len(texto) else "?"
			mensaje = _("El carácter «{c}» (y quizá otros) no se puede escribir en {cod}. ¿Qué quiere hacer?").format(
				c=caracter, cod=codificacion.NOMBRES.get(formato_.codificacion, formato_.codificacion))
			eleccion = dialogos.elegir_opcion(self, mensaje, _("Guardar"), [_("Guardar en &UTF-8"), _("&Cancelar")])
			if eleccion != 0:
				return None
			nuevo = replace(formato_, codificacion="utf-8", bom=False)
			return codificar(texto, nuevo), nuevo

	def guardar(self, al_terminar: Callable[[bool], None] | None = None) -> None:
		"""F2 o Ctrl+S: guarda en el mismo archivo con su formato."""
		terminar = al_terminar or (lambda _ok: None)
		if not self.cargado:
			anuncios.anunciar(_("Todavía se está cargando el archivo"), anuncios.RESULTADO)
			terminar(False)
			return
		if self._guardando:
			anuncios.anunciar(_("Ya se está guardando"), anuncios.RESULTADO)
			terminar(False)
			return
		if self.en_comprimido:
			anuncios.anunciar(_("No se puede guardar dentro del comprimido: elija dónde guardar la copia"), anuncios.RESULTADO)
			self.guardar_como(al_terminar)
			return
		codificado = self._datos_para(self.formato)
		if codificado is None:
			terminar(False)
			return
		datos, formato_ = codificado
		if self.es_remoto:
			destino = self.proveedor.mostrar(self.proveedor.padre(self.ruta) or "")
			if dialogos.confirmar(self, _("¿Subir los cambios de «{n}» a {d}?").format(n=self.nombre, d=destino), _("Guardar")) != wx.ID_YES:
				terminar(False)
				return
		self._comprobar_y_escribir(datos, formato_, terminar)

	def _comprobar_y_escribir(self, datos: bytes, formato_: FormatoTexto, terminar: Callable[[bool], None]) -> None:
		proveedor, ruta, marca, remoto = self.proveedor, self.ruta, self._marca, self.es_remoto

		def comprobar(_tarea):
			if remoto:
				try:
					info = proveedor.info(ruta)
				except base.NoEncontrado:
					return False
				return bool(marca and marca[0]) and (info.modificado, info.tamano) != tuple(marca)
			actual = marca_local(proveedor.ruta_local(ruta))
			return actual is not None and marca is not None and actual != tuple(marca)

		def tras_comprobar(cambio: bool) -> None:
			if cambio:
				pregunta = _("«{n}» ha cambiado en el disco desde que lo abrió. ¿Sobrescribirlo con su versión?").format(n=self.nombre)
				if dialogos.confirmar(self, pregunta, _("Guardar"), peligroso=True) != wx.ID_YES:
					self._guardando = False
					terminar(False)
					return
			self._escribir(datos, formato_, terminar)

		def fallo(error: BaseException) -> None:
			self._guardando = False
			dialogos.mostrar_error(self, _("No se pudo guardar: {e}").format(e=mensaje_error(error)))
			terminar(False)

		self._guardando = True
		self._enviar(comprobar, tras_comprobar, "editor-comprobar", fallo)

	def _escribir(self, datos: bytes, formato_: FormatoTexto, terminar: Callable[[bool], None]) -> None:
		proveedor, ruta, remoto = self.proveedor, self.ruta, self.es_remoto
		copia = bool(self.config.obtener("editor.copia_seguridad"))

		def trabajo(_tarea):
			if remoto:
				with proveedor.abrir_escritura(ruta) as salida:
					salida.write(datos)
				info = proveedor.info(ruta)
				return info.modificado, info.tamano
			local = proveedor.ruta_local(ruta)
			guardar_local(local, datos, copia)
			return marca_local(local)

		def listo(marca) -> None:
			self._guardando = False
			self._marca = marca
			self.formato = formato_
			self._marcar_guardado()
			anuncios.anunciar(_("Guardado: {n}").format(n=self.nombre), anuncios.RESULTADO)
			if remoto:
				self._refrescar_paneles()
			terminar(True)

		def fallo(error: BaseException) -> None:
			self._guardando = False
			dialogos.mostrar_error(self, _("No se pudo guardar «{n}»: {e}").format(n=self.nombre, e=mensaje_error(error)))
			terminar(False)

		self._enviar(trabajo, listo, "editor-guardar", fallo)

	def _refrescar_paneles(self) -> None:
		"""Los paneles que muestran la carpeta de un servidor no se vigilan: se vuelven a leer."""
		todos = getattr(self._principal, "todos_los_paneles", None)
		if not callable(todos):
			return
		carpeta = self.proveedor.padre(self.ruta)
		for panel in todos():
			if getattr(panel, "proveedor", None) is self.proveedor and getattr(panel, "ruta", None) == carpeta:
				panel.refrescar()

	def ruta_propuesta(self) -> str:
		"""Ruta local que se propone en «Guardar como»."""
		local = self.proveedor.ruta_local(self.ruta)
		if local:
			return local
		contenedor = self.proveedor.contenedor
		while contenedor is not None:
			carpeta = contenedor[0].ruta_local(contenedor[0].padre(contenedor[1]) or "")
			if carpeta:
				return os.path.join(carpeta, self.nombre)
			contenedor = contenedor[0].contenedor
		return os.path.join(os.path.expanduser("~"), self.nombre)

	def guardar_como(self, al_terminar: Callable[[bool], None] | None = None) -> None:
		terminar = al_terminar or (lambda _ok: None)
		if not self.cargado:
			terminar(False)
			return
		from app.ui.dialogos.a_formato import DialogoGuardarComo

		dialogo = DialogoGuardarComo(self, self.ruta_propuesta(), self.formato.codificacion, self.formato.fin_de_linea, self.formato.bom)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				terminar(False)
				return
			ruta, formato_ = dialogo.ruta(), FormatoTexto(dialogo.codificacion(), dialogo.fin_de_linea(), dialogo.bom())
		finally:
			dialogo.Destroy()
			self.texto.SetFocus()
		self.guardar_en(ruta, formato_, terminar)

	def guardar_en(self, ruta: str, formato_: FormatoTexto, terminar: Callable[[bool], None] | None = None) -> None:
		"""Guarda una copia en una ruta local y sigue editando esa copia."""
		terminar = terminar or (lambda _ok: None)
		codificado = self._datos_para(formato_)
		if codificado is None:
			terminar(False)
			return
		datos, formato_ = codificado
		copia = bool(self.config.obtener("editor.copia_seguridad"))

		def trabajo(_tarea):
			guardar_local(ruta, datos, copia)
			return marca_local(ruta)

		def listo(marca) -> None:
			from app.services.vfs import resolver

			cambio_formato = formato_ != self.formato
			self.proveedor, self.ruta, self.nombre = resolver.proveedor_local(), ruta, os.path.basename(ruta)
			self._marca, self.formato = marca, formato_
			self.etiqueta.SetLabel(_("&Texto de {n}:").format(n=self.nombre))
			self.texto.SetName(_("Texto de {n}").format(n=self.nombre))
			self._marcar_guardado()
			texto = _("Guardado como {r}").format(r=ruta)
			if cambio_formato:
				texto += _(" ({f}, fin de línea {l})").format(f=formato_.describir(), l=_(NOMBRE_FIN_DE_LINEA[formato_.fin_de_linea]))
			anuncios.anunciar(texto, anuncios.RESULTADO)
			terminar(True)

		def fallo(error: BaseException) -> None:
			dialogos.mostrar_error(self, _("No se pudo guardar en «{r}»: {e}").format(r=ruta, e=mensaje_error(error)))
			terminar(False)

		self._enviar(trabajo, listo, "editor-guardar-como", fallo)

	# Edición ---------------------------------------------------------------

	def _pegar(self) -> None:
		self.texto.Paste()

	def insertar_fecha(self) -> None:
		if self.cargado:
			self.texto.WriteText(datetime.now().strftime("%d/%m/%Y %H:%M"))

	def contar(self) -> None:
		texto = self.texto.GetValue() if self.cargado else ""
		lineas = texto.count("\n") + 1 if texto else 0
		palabras = len(texto.split())
		sin_espacios = len("".join(texto.split()))
		mensaje = _("Líneas: {l}\nPalabras: {p}\nCaracteres: {c}\nCaracteres sin espacios: {s}").format(
			l=formato.miles(lineas), p=formato.miles(palabras), c=formato.miles(len(texto)), s=formato.miles(sin_espacios))
		dialogos.mostrar_mensaje(self, mensaje, _("Contar"))

	def cambiar_letra(self, paso: int) -> None:
		nuevo = max(8, min(40, self.puntos + paso))
		if nuevo == self.puntos:
			anuncios.anunciar(_("La letra ya está en el tamaño {n}").format(n=nuevo), anuncios.RESULTADO)
			return
		self._aplicar_letra(nuevo)
		try:
			self.config.establecer("editor.tamano_fuente", nuevo)
		except Exception:  # noqa: BLE001 - guardar la preferencia no debe romper el editor
			log.warning("No se pudo guardar editor.tamano_fuente", exc_info=True)
		anuncios.anunciar(_("Letra de {n} puntos").format(n=nuevo), anuncios.RESULTADO)

	def _aplicar_letra(self, puntos: int) -> None:
		self.puntos = puntos
		self.texto.SetFont(fuente_monoespaciada(puntos))
		self.panel.Layout()

	def _al_cambiar_config(self, clave: str, _anterior, nuevo) -> None:
		def aplicar() -> None:
			if self and not self._cerrando and clave == "editor.tamano_fuente" and int(nuevo) != self.puntos:
				self._aplicar_letra(int(nuevo))

		wx.CallAfter(aplicar)

	# Posición y estado -----------------------------------------------------------

	def linea_y_columna(self) -> tuple[int, int]:
		ok, columna, linea = self.texto.PositionToXY(self.texto.GetInsertionPoint())
		return (linea + 1, columna + 1) if ok else (1, 1)

	def textos_estado(self) -> list[str]:
		if not self.cargado:
			return [_("Cargando..."), "", "", ""]
		linea, columna = self.linea_y_columna()
		if self.en_comprimido:
			cambios = _("Modificado (en comprimido)") if self.texto.IsModified() else _("En comprimido: guardar pide otra carpeta")
		else:
			cambios = _("Modificado") if self.texto.IsModified() else _("Sin cambios")
		return [_("Línea {l}, columna {c}").format(l=formato.miles(linea), c=columna), self.formato.describir(),
			_(NOMBRE_FIN_DE_LINEA.get(self.formato.fin_de_linea, "CRLF")), cambios]

	def _al_mover(self, evento: wx.Event) -> None:
		evento.Skip()
		wx.CallAfter(self._actualizar_estado)

	def _actualizar_estado(self) -> None:
		if not self:
			return
		for indice, texto in enumerate(self.textos_estado()):
			self.barra.SetStatusText(texto, indice)

	def decir_estado(self) -> None:
		anuncios.anunciar(". ".join(t for t in self.textos_estado() if t), anuncios.RESULTADO)

	def ir_a(self) -> None:
		if not self.cargado:
			return
		total = self.texto.GetNumberOfLines()
		numero = a_buscar.pedir_posicion(self, False, self.linea_y_columna()[0], 1, total)
		self.texto.SetFocus()
		if numero is not None:
			self.ir_a_linea(numero)

	def ir_a_linea(self, numero: int) -> None:
		posicion = self.texto.XYToPosition(0, numero - 1)
		if posicion < 0:
			anuncios.anunciar(_("El texto no tiene la línea {n}").format(n=numero), anuncios.RESULTADO)
			return
		self.texto.SetInsertionPoint(posicion)
		self.texto.ShowPosition(posicion)
		self._actualizar_estado()
		anuncios.anunciar(_("Línea {n}: {t}").format(n=formato.miles(numero), t=self.texto.GetLineText(numero - 1)), anuncios.RESULTADO)

	# Buscar y reemplazar ---------------------------------------------------------

	def buscar(self) -> None:
		if not self.cargado:
			return
		opciones = a_buscar.pedir_busqueda(self)
		self.texto.SetFocus()
		if opciones is not None:
			self.buscar_con(opciones)

	def repetir_busqueda(self, atras: bool) -> None:
		opciones = a_buscar.ULTIMA[0]
		if not opciones.texto:
			self.buscar()
			return
		self.buscar_con(opciones.hacia(atras))

	def _seleccion(self, texto: str, mapa: MapaPosiciones) -> tuple[int, int]:
		inicio, fin = self.texto.GetSelection()
		return mapa.de_control(inicio), mapa.de_control(fin)

	def buscar_con(self, opciones: a_buscar.OpcionesBusqueda) -> bool:
		"""Busca en el texto (en memoria: es rápido) y selecciona la coincidencia."""
		texto = self.texto.GetValue()
		mapa = MapaPosiciones(texto)
		inicio, fin = self._seleccion(texto, mapa)
		desde = inicio if opciones.atras else max(fin, mapa.de_control(self.texto.GetInsertionPoint()))
		encontrado = a_buscar.buscar_en(texto, a_buscar.compilar(opciones), desde, opciones.atras)
		if encontrado is None:
			anuncios.anunciar(_("No se encontró «{t}»").format(t=opciones.texto), anuncios.RESULTADO)
			return False
		inicio, fin, vuelta = encontrado
		self.texto.SetSelection(mapa.a_control(inicio), mapa.a_control(fin))
		self.texto.ShowPosition(mapa.a_control(inicio))
		self._actualizar_estado()
		linea = texto.count("\n", 0, inicio) + 1
		inicio_linea = texto.rfind("\n", 0, inicio) + 1
		fin_linea = texto.find("\n", inicio)
		partes = []
		if vuelta:
			partes.append(_("Búsqueda desde el final") if opciones.atras else _("Búsqueda desde el principio"))
		partes.append(_("Línea {n}: {t}").format(n=formato.miles(linea), t=texto[inicio_linea:fin_linea if fin_linea >= 0 else len(texto)]))
		anuncios.anunciar(". ".join(partes), anuncios.RESULTADO)
		return True

	def mostrar_reemplazar(self) -> None:
		if not self.cargado:
			return
		if self._reemplazar:
			self._reemplazar.Raise()
			self._reemplazar.campo.SetFocus()
			return
		seleccion = self.texto.GetStringSelection()
		opciones = a_buscar.ULTIMA[0]
		if seleccion and "\n" not in seleccion:
			opciones = replace(opciones, texto=seleccion)

		def al_cerrar() -> None:
			self._reemplazar = None
			if self:
				self.texto.SetFocus()

		self._reemplazar = a_buscar.DialogoReemplazar(self, opciones, "", self.buscar_con, self.reemplazar, self.reemplazar_todo, al_cerrar)
		self._reemplazar.Show()

	def _sustituto(self, coincidencia: re.Match[str], nuevo: str, regex: bool) -> str:
		return coincidencia.expand(nuevo) if regex else nuevo

	def reemplazar(self, opciones: a_buscar.OpcionesBusqueda, nuevo: str) -> bool:
		"""Reemplaza la selección si es una coincidencia y busca la siguiente."""
		texto = self.texto.GetValue()
		mapa = MapaPosiciones(texto)
		inicio, fin = self._seleccion(texto, mapa)
		coincidencia = a_buscar.compilar(opciones).fullmatch(texto, inicio, fin) if fin > inicio else None
		if coincidencia is not None:
			try:
				sustituto = self._sustituto(coincidencia, nuevo, opciones.regex)
			except (re.error, IndexError) as error:
				dialogos.mostrar_error(self, _("El texto de reemplazo no es válido: {e}").format(e=error))
				return False
			self.texto.Replace(mapa.a_control(inicio), mapa.a_control(fin), sustituto)
			# La siguiente búsqueda empieza detrás de lo puesto (en unidades del control).
			self.texto.SetInsertionPoint(mapa.a_control(inicio) + MapaPosiciones(sustituto).a_control(len(sustituto)))
		return self.buscar_con(replace(opciones, atras=False))

	def reemplazar_todo(self, opciones: a_buscar.OpcionesBusqueda, nuevo: str) -> int:
		"""Reemplaza todas las coincidencias en un solo paso (un Ctrl+Z lo deshace entero)."""
		texto = self.texto.GetValue()
		patron = a_buscar.compilar(opciones)
		try:
			resultado, cuantos = patron.subn(lambda m: self._sustituto(m, nuevo, opciones.regex), texto)
		except (re.error, IndexError) as error:
			dialogos.mostrar_error(self, _("El texto de reemplazo no es válido: {e}").format(e=error))
			return 0
		if not cuantos:
			anuncios.anunciar(_("No se encontró «{t}»").format(t=opciones.texto), anuncios.RESULTADO)
			return 0
		posicion = self.texto.GetInsertionPoint()
		self.texto.SetSelection(0, self.texto.GetLastPosition())
		self.texto.WriteText(resultado)
		self.texto.SetInsertionPoint(min(posicion, self.texto.GetLastPosition()))
		anuncios.anunciar(formato.plural(cuantos, _("{n} reemplazo"), _("{n} reemplazos")), anuncios.RESULTADO)
		return cuantos

	# Teclado y cierre --------------------------------------------------------

	def _al_bajar_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.GetModifiers() == wx.MOD_SHIFT:
			self.texto.WriteText("\n")
			return
		evento.Skip()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla == wx.WXK_F10 and modificadores == wx.MOD_NONE:
			self.Close()
			return
		if tecla == ord("S") and modificadores == wx.MOD_CONTROL:
			self.guardar()
			return
		if tecla == ord("F") and modificadores == wx.MOD_CONTROL:
			self.buscar()
			return
		if tecla == wx.WXK_F7 and modificadores == wx.MOD_SHIFT:
			self.repetir_busqueda(False)
			return
		evento.Skip()

	def preguntar_cambios(self) -> int | None:
		"""0 Guardar, 1 No guardar, ``None`` Cancelar."""
		if self.IsShown():
			# Al cerrar la ventana principal, se trae al frente el editor del que se pregunta.
			self.Raise()
		return dialogos.elegir_opcion(self, _("«{n}» tiene cambios sin guardar.").format(n=self.nombre), _("Cerrar el editor"),
			[_("&Guardar"), _("&No guardar"), _("&Cancelar")])

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if evento.CanVeto():
			if self._guardando:
				anuncios.anunciar(_("Espere a que termine de guardarse"), anuncios.RESULTADO)
				evento.Veto()
				return
			if self.modificado():
				eleccion = self.preguntar_cambios()
				if eleccion == 0:
					evento.Veto()
					self.guardar(lambda ok: ok and self and self.Close())
					return
				if eleccion != 1:
					# Cancelar: el diálogo ya devuelve el foco a donde estaba.
					evento.Veto()
					return
		self._cerrando = True
		for tarea in self._tareas:
			tarea.cancelar("Se cerró el editor")
		if self._reemplazar:
			self._reemplazar.Destroy()
		self._liberar()
		self.Destroy()

	def _al_cerrar_principal(self, evento: wx.CloseEvent) -> None:
		if self and not self._cerrando and evento.CanVeto() and self.modificado():
			eleccion = self.preguntar_cambios()
			if eleccion is None or eleccion == 2:
				evento.Veto()
				return
			if eleccion == 0:
				evento.Veto()
				principal = self._principal
				self.guardar(lambda ok: ok and principal and principal.Close())
				return
		evento.Skip()

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		evento.Skip()
		if evento.GetEventObject() is self:
			self._cerrando = True
			self._liberar()

	def _liberar(self) -> None:
		if self._cancelar_suscripcion is not None:
			self._cancelar_suscripcion()
			self._cancelar_suscripcion = None
		if self._principal is not None:
			try:
				if self._principal:
					self._principal.Unbind(wx.EVT_CLOSE, handler=self._al_cerrar_principal)
			except RuntimeError:
				log.debug("La ventana principal ya no existe", exc_info=True)
			self._principal = None


def abrir(padre: wx.Window | None, proveedor: base.Proveedor, ruta: str, config=None, tareas=None, mostrar: bool = True) -> VentanaEditor:
	"""Abre el editor interno sobre ``(proveedor, ruta)`` y lo muestra."""
	ventana = VentanaEditor(padre, proveedor, ruta, config, tareas)
	if mostrar:
		ventana.mostrar()
	return ventana
