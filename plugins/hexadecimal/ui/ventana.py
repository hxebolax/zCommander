# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventana del editor hexadecimal accesible (diseño 2.0, 11.10).

El cursor de bytes lo lleva el editor, no el control: «Vol&cado:» es un texto
de varias líneas de solo lectura con las líneas visibles, y cada tecla de
movimiento coloca su cursor de texto sobre el byte (con la marca de
movimiento silencioso) y anuncia «Desplazamiento 0x1A, 4F, letra O».

Teclas atendidas a mano en el volcado (además de las de los menús):
Izquierda y Derecha (un byte), Arriba y Abajo (una línea), Inicio y Fin (de
la línea), Ctrl+Inicio y Ctrl+Fin (del archivo), Re Pág y Av Pág (una
pantalla); con Mayúsculas seleccionan. Tab cambia entre la columna
hexadecimal y la de texto. Insert alterna insertar y sobrescribir (con NVDA,
Insert dos veces). Supr y Retroceso borran en modo insertar. F2 guarda.
"""

from __future__ import annotations

import builtins
import os
from collections.abc import Callable
from typing import Any

import wx

from ..servicios import herramientas
from ..servicios.piezas import TablaPiezas, firma_disco
from .comun import atender_ctrl_h, atender_f1, botonera

LINEAS_VISIBLES = 24
_DIGITOS = "0123456789abcdefABCDEF"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Opciones:
	"""Lo que la ventana lee de la configuración del complemento."""

	def __init__(self, config: Any) -> None:
		def valor(clave: str, defecto: Any) -> Any:
			try:
				return config.obtener(clave, defecto)
			except Exception:  # noqa: BLE001 - sin configuración, los valores de fábrica
				return defecto

		self.ancho = int(valor("bytes_por_linea", 16) or 16)
		self.orden = str(valor("orden_bytes", "little"))
		self.codificacion = str(valor("codificacion_texto", "cp1252"))
		self.completo = str(valor("anuncio", "valor")) == "completo"
		self.copia_seguridad = bool(valor("copia_seguridad", False))
		self.solo_lectura = bool(valor("abrir_solo_lectura", False))


class EditorHexadecimal:
	"""La ventana (``self.ventana``, una ``VentanaComplemento``) y su lógica.

	:param tabla: el contenido (ya abierto).
	:param nombre: nombre que se ve en el título.
	:param solo_lectura: archivos de comprimidos o servidores (solo «Guardar como»).
	"""

	def __init__(self, zc: Any, tabla: TablaPiezas, nombre: str, solo_lectura: bool = False, padre: wx.Window | None = None) -> None:
		self.zc = zc
		self.ui = zc.ui
		self.tabla = tabla
		self.nombre = nombre
		self.opciones = Opciones(zc.config)
		self.solo_lectura = solo_lectura or self.opciones.solo_lectura
		self.cursor = 0
		self.ancla: int | None = None
		self.columna_texto = False
		self.insertar = False
		self.medio_byte: str = ""
		self.inicio_vista = 0
		self.busqueda: list[int | None] | None = None
		self.guardando = False
		self.firma = firma_disco(tabla.ruta) if tabla.ruta else None
		ventana = self.ui.VentanaComplemento(padre, self._titulo(), zc.id)
		self.ventana = ventana
		self._crear_menus()
		panel = wx.Panel(ventana)
		raiz = wx.BoxSizer(wx.VERTICAL)
		_e, self.volcado = self.ui.crear_campo(panel, _("Vol&cado:"), wx.TextCtrl, sizer=raiz,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.TE_PROCESS_TAB | wx.TE_RICH2,
			ayuda=_("Bytes del archivo. Flechas, Inicio, Fin y páginas mueven el cursor de bytes; con Mayúsculas "
				"seleccionan. Tab cambia entre la columna hexadecimal y la de texto. Escriba dígitos hexadecimales o "
				"texto para cambiar bytes; Insert alterna insertar y sobrescribir."))
		self.volcado.SetFont(wx.Font(wx.FontInfo(11).Family(wx.FONTFAMILY_TELETYPE)))
		self.volcado.SetMinSize(ventana.FromDIP(wx.Size(760, 380)))
		raiz.GetItem(raiz.GetItemCount() - 1).SetProportion(1)
		_e, self.inspector = self.ui.crear_campo(panel, _("&Inspector:"), wx.TextCtrl, sizer=raiz,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
			ayuda=_("Los bytes del cursor leídos como enteros, coma flotante, caracteres y fechas. Control+E cambia el orden de bytes."))
		self.inspector.SetMinSize(ventana.FromDIP(wx.Size(-1, 140)))
		panel.SetSizer(raiz)
		self.barra = ventana.CreateStatusBar()
		ventana.SetSize(ventana.FromDIP(wx.Size(900, 680)))
		atender_ctrl_h(ventana, lambda texto: self.zc.anunciar(texto))
		self.volcado.Bind(wx.EVT_KEY_DOWN, self._al_tecla)
		self.volcado.Bind(wx.EVT_CHAR, self._al_caracter)
		ventana.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.refrescar(anunciar=False)
		self.volcado.SetFocus()

	# ── Menús ────────────────────────────────────────────────────────────────

	def _menu(self, barra: wx.MenuBar, titulo: str, elementos: list[tuple[str, str, Callable[[], None]] | None]) -> None:
		menu = wx.Menu()
		for elemento in elementos:
			if elemento is None:
				menu.AppendSeparator()
				continue
			etiqueta, ayuda, accion = elemento
			item = menu.Append(wx.ID_ANY, etiqueta, ayuda)
			self.ventana.Bind(wx.EVT_MENU, lambda _e, a=accion: a(), item)
		barra.Append(menu, titulo)

	def _crear_menus(self) -> None:
		barra = wx.MenuBar()
		self._menu(barra, _("&Archivo"), [
			(_("&Guardar\tCtrl+S"), _("Guarda los cambios en el archivo (también F2)"), self.guardar),
			(_("Guardar &como...\tShift+F2"), _("Guarda en otro archivo"), self.guardar_como),
			None,
			(_("Ce&rrar"), _("Cierra el editor (también Escape)"), lambda: self.ventana.Close()),
		])
		self._menu(barra, _("&Edición"), [
			(_("&Deshacer\tCtrl+Z"), _("Deshace el último cambio"), self.deshacer),
			(_("&Rehacer\tCtrl+Y"), _("Rehace lo deshecho"), self.rehacer),
			None,
			(_("&Copiar como hexadecimal\tCtrl+C"), _("Copia los bytes seleccionados como 48 6F 6C 61"), lambda: self.copiar(False)),
			(_("Copiar como &texto\tCtrl+Shift+C"), _("Copia los bytes seleccionados como texto"), lambda: self.copiar(True)),
			(_("&Pegar\tCtrl+V"), _("Pega hexadecimal o texto en el cursor"), self.pegar),
			None,
			(_("&Buscar...\tCtrl+F"), _("Busca bytes o texto"), lambda: self.dialogo_buscar(False)),
			(_("Buscar &siguiente\tF3"), _("Repite la búsqueda hacia delante"), lambda: self.buscar_otra(False)),
			(_("Buscar &anterior\tShift+F3"), _("Repite la búsqueda hacia atrás"), lambda: self.buscar_otra(True)),
			(_("R&eemplazar...\tCtrl+R"), _("Busca y reemplaza bytes o texto"), lambda: self.dialogo_buscar(True)),
			(_("&Ir a un desplazamiento...\tCtrl+G"), _("Decimal, 0x y hexadecimal, +n, -n o un porcentaje"), self.ir_a),
		])
		self._menu(barra, _("&Ver"), [
			(_("&Inspector\tCtrl+I"), _("Dice los bytes del cursor como enteros, coma flotante, caracteres y fechas"),
				self.anunciar_inspector),
			(_("Decir la &barra de estado\tCtrl+Shift+I"), _("Dice el desplazamiento, el modo y el orden de bytes"), self.anunciar_estado),
			(_("Cambiar el &orden de bytes\tCtrl+E"), _("Alterna little endian y big endian en el inspector"), self.cambiar_orden),
			(_("Modo inser&tar o sobrescribir"), _("También con la tecla Insert"), self.cambiar_modo),
			(_("Cambiar de &columna"), _("Entre la hexadecimal y la de texto (también Tab)"), self.cambiar_columna),
		])
		self.ventana.SetMenuBar(barra)

	# ── Vista ────────────────────────────────────────────────────────────────

	def _titulo(self) -> str:
		marca = "*" if self.tabla.modificado else ""
		lectura = _(" (solo lectura)") if self.solo_lectura else ""
		return _("{m}{n}{l} - Editor hexadecimal").format(m=marca, n=self.nombre, l=lectura)

	def texto_estado(self) -> str:
		total = len(self.tabla)
		partes = [_("Desplazamiento 0x{d:X} de 0x{t:X} ({d} de {t})").format(d=self.cursor, t=total)]
		partes.append(_("insertar") if self.insertar else _("sobrescribir"))
		partes.append(_("columna de texto") if self.columna_texto else _("columna hexadecimal"))
		partes.append("little endian" if self.opciones.orden == "little" else "big endian")
		inicio, fin = self.seleccion()
		if fin > inicio:
			partes.append(_("{n} bytes seleccionados").format(n=fin - inicio))
		if self.tabla.modificado:
			partes.append(_("modificado"))
		if self.solo_lectura:
			partes.append(_("solo lectura"))
		return ", ".join(partes)

	def seleccion(self) -> tuple[int, int]:
		if self.ancla is None:
			return self.cursor, self.cursor
		return min(self.ancla, self.cursor), max(self.ancla, self.cursor) + 1

	def refrescar(self, anunciar: bool = True) -> None:
		"""Vuelve a pintar las líneas visibles, coloca el cursor de texto y, si se pide, anuncia el byte."""
		ancho = self.opciones.ancho
		total = len(self.tabla)
		self.cursor = max(0, min(self.cursor, total))
		linea_cursor = self.cursor // ancho
		if linea_cursor < self.inicio_vista // ancho or linea_cursor >= self.inicio_vista // ancho + LINEAS_VISIBLES:
			self.inicio_vista = max(0, (linea_cursor - LINEAS_VISIBLES // 2) * ancho)
		datos = self.tabla.leer(self.inicio_vista, ancho * LINEAS_VISIBLES)
		lineas = [herramientas.linea_volcado(self.inicio_vista + i, datos[i:i + ancho], ancho, self.opciones.codificacion)
			for i in range(0, len(datos), ancho)] or [f"{0:08X}  "]
		texto = "\n".join(lineas)
		if self.volcado.GetValue() != texto:
			self.volcado.ChangeValue(texto)
		fila = (self.cursor - self.inicio_vista) // ancho
		indice = (self.cursor - self.inicio_vista) % ancho
		columna = herramientas.columna_texto(indice, ancho) if self.columna_texto else herramientas.columna_hex(indice)
		posicion = self.volcado.XYToPosition(columna, fila)
		if posicion >= 0:
			try:
				self.ui.movimiento_silencioso(self.volcado)
			except Exception:  # noqa: BLE001 - la marca para NVDA es una ayuda, no algo imprescindible
				self.zc.registro.debug("Sin marca de movimiento silencioso", exc_info=True)
			self.volcado.SetInsertionPoint(posicion)
			self.volcado.ShowPosition(posicion)
		self.inspector.ChangeValue(herramientas.texto_inspector(self.tabla.leer(self.cursor, 8), self.opciones.orden))
		self.barra.SetStatusText(self.texto_estado())
		self.ventana.SetTitle(self._titulo())
		if anunciar:
			self.anunciar_byte()

	def texto_byte(self) -> str:
		return herramientas.anuncio(self.cursor, self.tabla.leer(self.cursor, 4), self.opciones.codificacion, self.opciones.completo)

	def anunciar_byte(self) -> None:
		self.zc.anunciar(self.texto_byte(), "normal", interrumpir=True)

	# ── Movimiento ───────────────────────────────────────────────────────────

	def mover(self, nuevo: int, seleccionar: bool = False) -> None:
		if seleccionar and self.ancla is None:
			self.ancla = self.cursor
		elif not seleccionar:
			self.ancla = None
		self.medio_byte = ""
		total = len(self.tabla)
		# Con insertar se puede ir justo detrás del último byte para añadir al final.
		limite = total if self.insertar or total == 0 else total - 1
		self.cursor = max(0, min(nuevo, limite))
		self.refrescar()
		inicio, fin = self.seleccion()
		if seleccionar and fin > inicio:
			self.zc.anunciar(_("{n} bytes seleccionados").format(n=fin - inicio), "detalle")

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		mayus = bool(modificadores & wx.MOD_SHIFT)
		control = bool(modificadores & wx.MOD_CONTROL)
		otros = modificadores & ~(wx.MOD_SHIFT | wx.MOD_CONTROL)
		ancho = self.opciones.ancho
		pantalla = ancho * LINEAS_VISIBLES
		movimientos = {
			wx.WXK_LEFT: self.cursor - 1, wx.WXK_RIGHT: self.cursor + 1,
			wx.WXK_UP: self.cursor - ancho, wx.WXK_DOWN: self.cursor + ancho,
			wx.WXK_PAGEUP: self.cursor - pantalla, wx.WXK_PAGEDOWN: self.cursor + pantalla,
			wx.WXK_HOME: 0 if control else self.cursor - self.cursor % ancho,
			wx.WXK_END: len(self.tabla) if control else self.cursor - self.cursor % ancho + ancho - 1,
		}
		if not otros and tecla in movimientos and (not control or tecla in (wx.WXK_HOME, wx.WXK_END)):
			self.mover(movimientos[tecla], seleccionar=mayus)
			return
		if tecla == wx.WXK_TAB and not control and not otros:
			self.cambiar_columna()
			return
		if tecla == wx.WXK_INSERT and not modificadores:
			self.cambiar_modo()
			return
		if tecla in (wx.WXK_DELETE, wx.WXK_BACK) and not modificadores:
			self.borrar(tecla == wx.WXK_BACK)
			return
		if tecla == wx.WXK_F2 and not modificadores:
			self.guardar()
			return
		evento.Skip()

	# ── Edición ──────────────────────────────────────────────────────────────

	def _puede_editar(self) -> bool:
		if self.solo_lectura:
			self.zc.anunciar(_("Solo lectura: use Guardar como para guardar una copia"), "esencial")
			return False
		if self.guardando:
			self.zc.anunciar(_("Espere a que termine de guardarse"), "esencial")
			return False
		return True

	def _al_caracter(self, evento: wx.KeyEvent) -> None:
		if evento.GetModifiers() & ~wx.MOD_SHIFT:
			evento.Skip()
			return
		codigo = evento.GetUnicodeKey()
		if codigo == wx.WXK_NONE or codigo < 32:
			evento.Skip()
			return
		caracter = chr(codigo)
		if self.columna_texto:
			self.escribir_texto(caracter)
		else:
			self.escribir_digito(caracter)

	def escribir_digito(self, caracter: str) -> None:
		"""Dos dígitos hexadecimales cambian (o insertan) el byte; uno no válido suena."""
		if caracter not in _DIGITOS:
			self.zc.sonidos.sonar("no_valido")
			self.zc.anunciar(_("{c} no es un dígito hexadecimal").format(c=caracter), "detalle")
			return
		if not self._puede_editar():
			return
		if not self.medio_byte:
			self.medio_byte = caracter
			self.zc.anunciar(caracter.upper(), "detalle", interrumpir=True)
			return
		valor = bytes([int(self.medio_byte + caracter, 16)])
		self.medio_byte = ""
		self._poner(valor)

	def escribir_texto(self, caracter: str) -> None:
		if not self._puede_editar():
			return
		try:
			valor = caracter.encode(self.opciones.codificacion)
		except UnicodeEncodeError:
			self.zc.sonidos.sonar("no_valido")
			self.zc.anunciar(_("{c} no existe en {n}").format(c=caracter, n=self.opciones.codificacion), "detalle")
			return
		self._poner(valor)

	def _poner(self, valor: bytes) -> None:
		if self.insertar:
			self.tabla.insertar(self.cursor, valor)
		else:
			self.tabla.sobrescribir(self.cursor, valor)
		self.ancla = None
		self.cursor += len(valor)
		self.refrescar()

	def borrar(self, retroceso: bool) -> None:
		if not self.insertar:
			self.zc.anunciar(_("Para borrar bytes, pase a modo insertar con Insert"), "esencial")
			return
		if not self._puede_editar():
			return
		inicio, fin = self.seleccion()
		if fin > inicio:
			self.tabla.borrar(inicio, fin - inicio)
			self.cursor = inicio
		elif retroceso:
			if self.cursor == 0:
				return
			self.tabla.borrar(self.cursor - 1, 1)
			self.cursor -= 1
		else:
			if self.cursor >= len(self.tabla):
				return
			self.tabla.borrar(self.cursor, 1)
		self.ancla = None
		self.refrescar()

	def deshacer(self) -> None:
		posicion = self.tabla.deshacer()
		if posicion is None:
			self.zc.anunciar(_("No hay nada que deshacer"), "esencial")
			return
		self.cursor = posicion
		self.refrescar(anunciar=False)
		self.zc.anunciar(_("Deshecho. ") + self.texto_byte(), "resultado")

	def rehacer(self) -> None:
		posicion = self.tabla.rehacer()
		if posicion is None:
			self.zc.anunciar(_("No hay nada que rehacer"), "esencial")
			return
		self.cursor = posicion
		self.refrescar(anunciar=False)
		self.zc.anunciar(_("Rehecho. ") + self.texto_byte(), "resultado")

	def cambiar_modo(self) -> None:
		self.insertar = not self.insertar
		self.refrescar(anunciar=False)
		self.zc.anunciar(_("Insertar") if self.insertar else _("Sobrescribir"), "resultado")

	def cambiar_columna(self) -> None:
		self.columna_texto = not self.columna_texto
		self.medio_byte = ""
		self.refrescar(anunciar=False)
		self.zc.anunciar(_("Columna de texto") if self.columna_texto else _("Columna hexadecimal"), "resultado")

	def cambiar_orden(self) -> None:
		self.opciones.orden = "big" if self.opciones.orden == "little" else "little"
		self.refrescar(anunciar=False)
		self.zc.anunciar("Big endian" if self.opciones.orden == "big" else "Little endian", "resultado")

	def anunciar_inspector(self) -> None:
		self.zc.anunciar(self.inspector.GetValue().replace("\n", ". "), "resultado")

	def anunciar_estado(self) -> None:
		self.zc.anunciar(self.texto_estado(), "resultado")

	# ── Portapapeles ─────────────────────────────────────────────────────────

	def bytes_seleccionados(self) -> bytes:
		inicio, fin = self.seleccion()
		return self.tabla.leer(inicio, max(1, fin - inicio))

	def copiar(self, como_texto: bool) -> None:
		datos = self.bytes_seleccionados()
		if not datos:
			return
		texto = datos.decode(self.opciones.codificacion, errors="replace") if como_texto else " ".join(f"{b:02X}" for b in datos)
		if wx.TheClipboard.Open():
			try:
				wx.TheClipboard.SetData(wx.TextDataObject(texto))
			finally:
				wx.TheClipboard.Close()
			self.zc.anunciar(_("Copiados {n} bytes").format(n=len(datos)), "resultado")

	def pegar(self) -> None:
		if not self._puede_editar():
			return
		datos = wx.TextDataObject()
		if not wx.TheClipboard.Open():
			return
		try:
			hay = wx.TheClipboard.GetData(datos)
		finally:
			wx.TheClipboard.Close()
		if not hay or not datos.GetText():
			self.zc.anunciar(_("No hay texto en el portapapeles"), "esencial")
			return
		self.pegar_texto(datos.GetText())

	def pegar_texto(self, texto: str) -> None:
		valor = herramientas.bytes_de_texto_pegado(texto, not self.columna_texto, self.opciones.codificacion)
		self._poner(valor)
		self.zc.anunciar(_("Pegados {n} bytes").format(n=len(valor)), "resultado")

	# ── Buscar, reemplazar e ir a ────────────────────────────────────────────

	def ir_a(self) -> None:
		texto = self.ui.pedir_texto(_("Desplazamiento (decimal, 0x10, +16, -16 o 50%):"), _("Ir a un desplazamiento"), "",
			padre=self.ventana)
		if not texto:
			return
		try:
			destino = herramientas.destino(texto, self.cursor, len(self.tabla))
		except ValueError as error:
			self.zc.anunciar(str(error), "esencial")
			return
		self.mover(destino)

	def dialogo_buscar(self, reemplazar: bool) -> None:
		dialogo = DialogoBuscar(self.ventana, self.ui, reemplazar, self.columna_texto, getattr(self.zc, "abrir_ayuda", None))
		try:
			respuesta = self.ui.mostrar_modal(dialogo)
			if respuesta == wx.ID_CANCEL:
				return
			try:
				patron, reemplazo = dialogo.patrones(self.opciones.codificacion)
			except ValueError as error:
				self.zc.anunciar(str(error), "esencial")
				return
		finally:
			dialogo.Destroy()
		self.busqueda = patron
		if not reemplazar:
			self.buscar_otra(False, desde=self.cursor)
		elif respuesta == DialogoBuscar.ID_TODOS:
			self.reemplazar_todos(patron, reemplazo)
		else:
			self.reemplazar_siguiente(patron, reemplazo)

	def buscar_otra(self, atras: bool, desde: int | None = None, al_encontrar: Callable[[int], None] | None = None) -> None:
		if self.busqueda is None:
			self.dialogo_buscar(False)
			return
		patron = self.busqueda
		inicio = desde if desde is not None else (self.cursor if atras else self.cursor + 1)
		self.zc.anunciar(_("Buscando..."), "detalle")

		def trabajo(tarea: Any) -> int:
			return herramientas.buscar(self.tabla, patron, inicio, atras, tarea.token)

		def encontrado(posicion: int) -> None:
			if not self.ventana:
				return
			if posicion < 0:
				self.zc.anunciar(_("No se encontró"), "resultado")
				return
			if al_encontrar is not None:
				al_encontrar(posicion)
				return
			self.ancla = None
			self.cursor = posicion
			self.refrescar(anunciar=False)
			self.zc.anunciar(_("Encontrado. ") + self.texto_byte(), "resultado")

		self.zc.tareas.enviar(trabajo, al_terminar=encontrado, nombre="zc.hexadecimal:buscar",
			al_fallar=lambda error: self.zc.anunciar(_("No se pudo buscar: {e}").format(e=error), "esencial"))

	def reemplazar_en(self, posicion: int, largo: int, reemplazo: bytes) -> None:
		self.tabla.iniciar_grupo()
		self.tabla.borrar(posicion, largo)
		self.tabla.insertar(posicion, reemplazo)
		self.tabla.terminar_grupo(posicion)
		self.cursor = posicion + len(reemplazo)

	def reemplazar_siguiente(self, patron: list[int | None], reemplazo: bytes) -> None:
		if not self._puede_editar():
			return

		def al_encontrar(posicion: int) -> None:
			self.reemplazar_en(posicion, len(patron), reemplazo)
			self.refrescar(anunciar=False)
			self.zc.anunciar(_("Reemplazado en 0x{d:X}").format(d=posicion), "resultado")

		self.buscar_otra(False, desde=self.cursor, al_encontrar=al_encontrar)

	def reemplazar_todos(self, patron: list[int | None], reemplazo: bytes) -> None:
		if not self._puede_editar():
			return

		def trabajo(tarea: Any) -> list[int]:
			return herramientas.buscar_todos(self.tabla, patron, tarea.token)

		def aplicar(posiciones: list[int]) -> None:
			if not self.ventana:
				return
			if not posiciones:
				self.zc.anunciar(_("No se encontró"), "resultado")
				return
			self.tabla.iniciar_grupo()
			for posicion in reversed(posiciones):
				self.tabla.borrar(posicion, len(patron))
				self.tabla.insertar(posicion, reemplazo)
			self.tabla.terminar_grupo(posiciones[0])
			self.cursor = posiciones[0]
			self.refrescar(anunciar=False)
			self.zc.anunciar(_("{n} reemplazos").format(n=len(posiciones)), "resultado")

		self.zc.tareas.enviar(trabajo, al_terminar=aplicar, nombre="zc.hexadecimal:reemplazar",
			al_fallar=lambda error: self.zc.anunciar(_("No se pudo reemplazar: {e}").format(e=error), "esencial"))

	# ── Guardar y cerrar ─────────────────────────────────────────────────────

	def guardar(self, al_terminar: Callable[[], None] | None = None) -> None:
		if self.solo_lectura or self.tabla.ruta is None:
			self.guardar_como()
			return
		if not self.tabla.modificado:
			self.zc.anunciar(_("No hay cambios que guardar"), "resultado")
			return
		if self.firma is not None and firma_disco(self.tabla.ruta) != self.firma and not self.ui.confirmar(
				_("{n} ha cambiado en el disco desde que lo abrió. Si guarda, se pierden esos cambios. ¿Guardar de todos modos?").format(
					n=self.nombre), _("El archivo ha cambiado"), padre=self.ventana, peligroso=True):
			return
		self._guardar_en(None, al_terminar)

	def guardar_como(self) -> None:
		dialogo = wx.FileDialog(self.ventana, _("Guardar como"), defaultFile=self.nombre,
			wildcard=_("Todos los archivos (*.*)|*.*"), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		try:
			if self.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			destino = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		self._guardar_en(destino, None)

	def _guardar_en(self, destino: str | None, al_terminar: Callable[[], None] | None) -> None:
		self.guardando = True
		self.zc.anunciar(_("Guardando..."), "normal")
		copia = self.opciones.copia_seguridad

		def trabajo(tarea: Any) -> str:
			return self.tabla.guardar(destino, copia, cancelacion=tarea.token)

		def hecho(ruta: str) -> None:
			self.guardando = False
			self.solo_lectura = False
			self.nombre = os.path.basename(ruta)
			self.firma = firma_disco(ruta)
			if self.ventana:
				self.refrescar(anunciar=False)
			self.zc.anunciar(_("Guardado {n}").format(n=self.nombre), "resultado")
			if al_terminar is not None:
				al_terminar()

		def fallo(error: BaseException) -> None:
			self.guardando = False
			self.zc.anunciar(_("No se pudo guardar: {e}").format(e=getattr(error, "strerror", None) or error), "esencial")

		self.zc.tareas.enviar(trabajo, al_terminar=hecho, al_fallar=fallo, nombre="zc.hexadecimal:guardar")

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self.tabla.modificado and evento.CanVeto():
			eleccion = self.ui.elegir_opcion(_("{n} tiene cambios sin guardar.").format(n=self.nombre), _("Cambios sin guardar"),
				[_("&Guardar"), _("&Descartar los cambios"), _("&Cancelar")], padre=self.ventana)
			if eleccion in (None, 2):
				evento.Veto()
				return
			if eleccion == 0:
				evento.Veto()
				self.guardar(al_terminar=lambda: self.ventana.Close(force=True))
				return
		self.tabla.cerrar()
		evento.Skip()


class DialogoBuscar(wx.Dialog):
	"""«&Buscar:», «&Reemplazar por:» (solo al reemplazar) y «&Formato:» (hexadecimal con ?? o texto)."""

	ID_SIGUIENTE = wx.ID_OK
	ID_TODOS = wx.ID_YESTOALL

	def __init__(self, padre: wx.Window | None, ui: Any, reemplazar: bool, texto: bool, al_ayuda: Callable[[], None] | None) -> None:
		super().__init__(padre, title=_("Reemplazar") if reemplazar else _("Buscar"))
		raiz = wx.BoxSizer(wx.VERTICAL)
		_e, self.buscado = ui.crear_campo(self, _("&Buscar:"), wx.TextCtrl, sizer=raiz,
			ayuda=_("Bytes en hexadecimal (4F 6B ?? 00, con ?? como comodín) o texto, según el formato."))
		self.reemplazo = None
		if reemplazar:
			_e, self.reemplazo = ui.crear_campo(self, _("&Reemplazar por:"), wx.TextCtrl, sizer=raiz,
				ayuda=_("Lo que se pone en lugar de lo encontrado, en el mismo formato; puede tener otro tamaño."))
		_e, self.formato = ui.crear_campo(self, _("&Formato:"), wx.Choice, choices=[_("Hexadecimal"), _("Texto")], sizer=raiz,
			ayuda=_("Hexadecimal: pares de dígitos y ?? como comodín. Texto: con la codificación de la columna de texto."))
		self.formato.SetSelection(1 if texto else 0)
		if reemplazar:
			fila = wx.BoxSizer(wx.HORIZONTAL)
			for identificador, etiqueta in ((self.ID_SIGUIENTE, _("Reemplazar el &siguiente")), (self.ID_TODOS, _("Reemplazar &todos")),
					(wx.ID_CANCEL, _("&Cancelar"))):
				boton = wx.Button(self, identificador, etiqueta)
				fila.Add(boton, 0, wx.ALL, 5)
				if identificador != wx.ID_CANCEL:
					boton.Bind(wx.EVT_BUTTON, lambda _e, i=identificador: self.EndModal(i))
			self.FindWindowById(self.ID_SIGUIENTE, self).SetDefault()
			raiz.Add(fila, 0, wx.ALIGN_RIGHT)
		else:
			raiz.Add(botonera(self, [(wx.ID_OK, _("B&uscar")), (wx.ID_CANCEL, _("&Cancelar"))], wx.ID_OK), 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(raiz)
		ui.preparar_dialogo(self, foco_inicial=self.buscado)
		atender_f1(self, al_ayuda)

	def patrones(self, codificacion: str) -> tuple[list[int | None], bytes]:
		"""(patrón de búsqueda, bytes de reemplazo). ``ValueError`` con el motivo si algo no vale."""
		hexadecimal = self.formato.GetSelection() == 0
		texto = self.buscado.GetValue()
		patron = herramientas.patron_hexadecimal(texto) if hexadecimal else herramientas.patron_texto(texto, codificacion)
		reemplazo = b""
		if self.reemplazo is not None:
			valor = self.reemplazo.GetValue()
			if hexadecimal:
				bytes_ = herramientas.patron_hexadecimal(valor) if valor.strip() else []
				if any(b is None for b in bytes_):
					raise ValueError(_("El reemplazo no puede llevar comodines"))
				reemplazo = bytes(b for b in bytes_ if b is not None)
			else:
				reemplazo = valor.encode(codificacion, errors="replace")
		return patron, reemplazo
