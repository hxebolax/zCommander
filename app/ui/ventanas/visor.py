# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Visor interno de archivos (F3), sección 8.2 del diseño (bloque A).

Ventana propia, no modal (se pueden abrir varias), con un ``wx.TextCtrl``
multilínea de solo lectura que el lector recorre por líneas, palabras y
caracteres. Por qué está hecho así:

- **Nada bloquea la interfaz.** Leer el archivo (y extraerlo si está en un
  comprimido o en un servidor), decodificarlo, cambiar de bloque, buscar en
  todos los bloques e ir a una línea lejana van en hilos del ``GestorTareas``
  de la ventana principal; los controles solo se tocan en el hilo de la
  interfaz cuando llega el resultado.
- **Archivos grandes por bloques.** Hasta ``visor.limite_mb`` se carga el
  archivo entero; si es mayor se ve en bloques de 1 MB (Ctrl+Av Pág y
  Ctrl+Re Pág) y la barra de estado dice «Bloque 3 de 120». En modo texto,
  cada frontera de bloque se mueve al final de la línea en la que cae, para
  que ninguna línea ni ningún carácter de varios bytes quede partido entre
  dos bloques; así los números de línea son los del archivo entero.
- **Hexadecimal siempre por bloques de 1 MB**: el volcado ocupa unas cinco
  veces más que el archivo y un control con 80 MB de texto deja al lector sin
  respuesta durante segundos.
- **Posiciones exactas.** El control (RichEdit) cuenta cada salto de línea
  como una posición y cada carácter fuera del plano básico (emojis) como dos;
  ``MapaPosiciones`` traduce entre las posiciones del control y las de Python
  para que buscar, ir a línea y la barra de estado no se desplacen.
- **Lo que el lector no dice solo, se anuncia**: al encontrar un texto se lee
  la línea donde está (NVDA no lee la selección puesta por programa), el
  cambio de bloque, el modo y la codificación nuevos y «No se encontró».
- El archivo extraído a ``data/temp/extraidos`` se borra al cerrar el visor.
"""

from __future__ import annotations

import bisect
import builtins
import logging
import math
import os
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import wx

from app.services import codificacion, errores, formato
from app.core.tareas import TareaCancelada
from app.services.vfs import base, rutas, temporales
from app.ui import anuncios
from app.ui.dialogos import a_buscar

log = logging.getLogger(__name__)

BLOQUE = 1024 * 1024
ANCHO_HEX = 16
#: Longitud de una línea completa del volcado («00000000  48 6F ...  Hola...»), sin el salto.
LARGO_LINEA_HEX = 8 + 2 + ANCHO_HEX * 3 - 1 + 2 + ANCHO_HEX
#: Columna donde empiezan los bytes y la parte de texto dentro de cada línea del volcado.
COLUMNA_BYTES = 10
COLUMNA_TEXTO = COLUMNA_BYTES + ANCHO_HEX * 3 - 1 + 2
MUESTRA = 64 * 1024
TEXTO, HEXADECIMAL = "texto", "hexadecimal"

_ASTRAL = re.compile("[\U00010000-\U0010ffff]")
_CONTROL_NULO = str.maketrans({"\x00": "·"})


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Utilidades compartidas con el editor y las diferencias ──────────────────────

_gestor_propio: list[Any] = []


def tareas_de(ventana: wx.Window | None):
	"""El ``GestorTareas`` de la ventana principal (buscándolo hacia arriba) o uno propio del bloque.

	Las ventanas del visor pueden abrirse desde la lista de conflictos u otro
	diálogo; se busca el gestor en sus padres para compartir hilos y apagado.
	"""
	actual = ventana
	while actual is not None:
		tareas = getattr(actual, "tareas", None)
		if tareas is not None and hasattr(tareas, "enviar"):
			return tareas
		actual = actual.GetParent()
	if not _gestor_propio:
		from app.core.tareas import GestorTareas

		_gestor_propio.append(GestorTareas(max_hilos=2, nombre="visor"))
	return _gestor_propio[0]


def configuracion_de(ventana: wx.Window | None):
	"""La configuración de la ventana principal o la instancia compartida."""
	actual = ventana
	while actual is not None:
		config = getattr(actual, "config", None)
		if config is not None and hasattr(config, "obtener"):
			return config
		actual = actual.GetParent()
	from app.core.configuracion import obtener_configuracion

	return obtener_configuracion()


def fuente_monoespaciada(puntos: int) -> wx.Font:
	"""Letra de ancho fijo: las columnas del volcado hexadecimal y del texto quedan alineadas."""
	return wx.Font(wx.FontInfo(max(8, min(40, int(puntos)))).Family(wx.FONTFAMILY_TELETYPE))


def mensaje_error(error: BaseException) -> str:
	return getattr(error, "mensaje", None) or errores.mensaje_para_usuario(error)


class MapaPosiciones:
	"""Traduce posiciones entre un texto de Python y el control RichEdit que lo muestra.

	El control cuenta los caracteres fuera del plano básico (emojis, algunos
	ideogramas) como dos unidades; Python, como uno. Sin estos caracteres las
	posiciones coinciden y la traducción no cuesta nada.
	"""

	def __init__(self, texto: str) -> None:
		self._python = [m.start() for m in _ASTRAL.finditer(texto)]
		# Posición del control justo después de cada carácter astral.
		self._control_fin = [p + i + 2 for i, p in enumerate(self._python)]

	def a_control(self, posicion: int) -> int:
		return posicion + bisect.bisect_left(self._python, posicion) if self._python else posicion

	def de_control(self, posicion: int) -> int:
		return posicion - bisect.bisect_right(self._control_fin, posicion) if self._python else posicion


def linea_y_columna(texto: str, posicion: int) -> tuple[int, int]:
	"""(línea, columna) desde 1 de una posición de Python en un texto con saltos «\\n»."""
	linea = texto.count("\n", 0, posicion) + 1
	inicio = texto.rfind("\n", 0, posicion) + 1
	return linea, posicion - inicio + 1


def texto_de_linea(texto: str, posicion: int) -> str:
	inicio = texto.rfind("\n", 0, posicion) + 1
	fin = texto.find("\n", posicion)
	return texto[inicio:fin if fin >= 0 else len(texto)]


def normalizar_texto(texto: str) -> str:
	"""Saltos a «\\n» (el control y los números de línea los cuentan igual) y nulos visibles."""
	return texto.replace("\r\n", "\n").replace("\r", "\n").translate(_CONTROL_NULO)


# ── Modelo del visor (sin wx) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Encontrado:
	"""Resultado de una búsqueda: dónde está y si se dio la vuelta al archivo."""

	bloque: int
	inicio: int
	fin: int
	vuelta: bool


class ModeloVisor:
	"""Contenido de un archivo LOCAL visto por bloques, en texto o en hexadecimal.

	Se usa desde hilos de trabajo; cada lectura abre el archivo de nuevo, así
	que una búsqueda y un cambio de bloque pueden convivir sin candados.

	:param ruta: ruta local (ya extraída si venía de un comprimido o servidor).
	:param limite: bytes hasta los que se carga entero en memoria.
	:param preferida: «automatica» o una codificación fija.
	"""

	def __init__(self, ruta: str, tamano: int | None = None, limite: int = 16 * BLOQUE, preferida: str = "automatica") -> None:
		self.ruta = ruta
		self.tamano = os.path.getsize(rutas.con_prefijo_largo(ruta)) if tamano is None else tamano
		self.entero = self.tamano <= limite
		self._datos: bytes | None = None
		if self.entero:
			with open(rutas.con_prefijo_largo(ruta), "rb") as flujo:
				self._datos = flujo.read()
			self.tamano = len(self._datos)
		muestra = self.leer(0, MUESTRA)
		self.binario = codificacion.es_binario(muestra)
		self.detectada = codificacion.detectar(muestra)
		self.automatica = preferida in ("", "automatica")
		self.codificacion = self.detectada if self.automatica else preferida
		self.fin_de_linea = codificacion.fin_de_linea(codificacion.decodificar(muestra, self.codificacion)[0])
		self._reiniciar()

	def _reiniciar(self) -> None:
		self._fronteras: dict[int, int] = {0: 0, self.bloques_texto: self.tamano}
		self._lineas_antes: dict[int, int] = {0: 0}
		self._cache: OrderedDict[int, str] = OrderedDict()

	def fijar_codificacion(self, valor: str) -> None:
		"""Cambia la codificación («automatica» vuelve a la detectada); las fronteras dependen de ella."""
		self.automatica = valor in ("", "automatica")
		self.codificacion = self.detectada if self.automatica else valor
		self._reiniciar()

	# Lectura ---------------------------------------------------------------

	def leer(self, inicio: int, cantidad: int) -> bytes:
		if self._datos is not None:
			return self._datos[inicio:inicio + cantidad]
		with open(rutas.con_prefijo_largo(self.ruta), "rb") as flujo:
			flujo.seek(inicio)
			return flujo.read(cantidad)

	@property
	def bloques_texto(self) -> int:
		return 1 if self.entero else max(1, math.ceil(self.tamano / BLOQUE))

	@property
	def bloques_hex(self) -> int:
		return max(1, math.ceil(self.tamano / BLOQUE))

	def bloques(self, modo: str) -> int:
		return self.bloques_hex if modo == HEXADECIMAL else self.bloques_texto

	# Bloques de texto ----------------------------------------------------------

	def frontera(self, indice: int) -> int:
		"""Byte donde empieza el bloque de texto ``indice`` (justo después de un salto de línea)."""
		if indice in self._fronteras:
			return self._fronteras[indice]
		posicion = indice * BLOQUE
		ventana = self.leer(posicion, 16 * 1024)
		cod = self.codificacion
		if cod == "utf-16-le":
			salto, alineado = b"\n\x00", True
		elif cod == "utf-16-be":
			salto, alineado = b"\x00\n", True
		else:
			salto, alineado = b"\n", False
		resultado = None
		indice_busqueda = ventana.find(salto)
		while indice_busqueda >= 0:
			if not alineado or indice_busqueda % 2 == 0:
				resultado = posicion + indice_busqueda + len(salto)
				break
			indice_busqueda = ventana.find(salto, indice_busqueda + 1)
		if resultado is None:
			# Una línea de más de 16 KB: se corta donde no parta un carácter.
			resultado = posicion
			if cod == "utf-8":
				desplazamiento = 0
				while desplazamiento < min(3, len(ventana)) and 0x80 <= ventana[desplazamiento] < 0xC0:
					desplazamiento += 1
				resultado += desplazamiento
		resultado = min(resultado, self.tamano)
		self._fronteras[indice] = resultado
		return resultado

	def texto_bloque(self, indice: int) -> str:
		"""Texto del bloque, con saltos «\\n». Se guardan en caché los tres últimos."""
		if indice in self._cache:
			self._cache.move_to_end(indice)
			return self._cache[indice]
		inicio, fin = self.frontera(indice), self.frontera(indice + 1)
		texto, _usada = codificacion.decodificar(self.leer(inicio, fin - inicio), self.codificacion)
		texto = normalizar_texto(texto)
		self._cache[indice] = texto
		while len(self._cache) > 3:
			self._cache.popitem(last=False)
		if indice in self._lineas_antes:
			self._lineas_antes[indice + 1] = self._lineas_antes[indice] + texto.count("\n")
		return texto

	def hex_bloque(self, indice: int) -> str:
		return codificacion.hexadecimal(self.leer(indice * BLOQUE, BLOQUE), indice * BLOQUE, ANCHO_HEX)

	def contenido(self, modo: str, indice: int) -> str:
		return self.hex_bloque(indice) if modo == HEXADECIMAL else self.texto_bloque(indice)

	def lineas_antes(self, indice: int) -> int | None:
		"""Líneas que hay antes del bloque, si ya se han contado."""
		return self._lineas_antes.get(indice)

	def contar_hasta(self, indice: int, cancelacion=None) -> int:
		"""Cuenta (en un hilo) las líneas anteriores al bloque ``indice``."""
		conocido = max(i for i in self._lineas_antes if i <= indice)
		for actual in range(conocido, indice):
			base.comprobar(cancelacion)
			self.texto_bloque(actual)
		return self._lineas_antes[indice]

	def total_lineas(self, cancelacion=None) -> int:
		"""Número de líneas del archivo (recorre los bloques que falten)."""
		ultimo = self.bloques_texto - 1
		antes = self.contar_hasta(ultimo, cancelacion)
		texto = self.texto_bloque(ultimo)
		return antes + texto.count("\n") + (1 if texto and not texto.endswith("\n") else 0)

	def total_lineas_conocido(self) -> int | None:
		ultimo = self.bloques_texto - 1
		if ultimo + 1 not in self._lineas_antes or ultimo not in self._cache:
			return None
		texto = self._cache[ultimo]
		return self._lineas_antes[ultimo + 1] + (1 if texto and not texto.endswith("\n") else 0)

	def ir_a_linea(self, numero: int, cancelacion=None) -> tuple[int, int] | None:
		"""(bloque, posición en su texto) del principio de la línea ``numero`` (desde 1), o ``None`` si no existe."""
		objetivo = numero - 1  # saltos de línea que hay antes de esa línea
		if objetivo < 0:
			return None
		for indice in range(self.bloques_texto):
			antes = self.contar_hasta(indice, cancelacion)
			texto = self.texto_bloque(indice)
			saltos = texto.count("\n")
			ultimo = indice == self.bloques_texto - 1
			local = objetivo - antes
			if local < saltos or (ultimo and local == saltos):
				posicion = 0
				for _vez in range(local):
					posicion = texto.find("\n", posicion) + 1
				if ultimo and local == saltos and local > 0 and posicion >= len(texto):
					return None  # detrás del último salto no hay otra línea
				return indice, posicion
		return None

	# Posiciones en bytes -------------------------------------------------------------

	def byte_de_texto(self, indice: int, posicion: int, texto: str) -> int:
		"""Byte aproximado del archivo que corresponde a una posición del texto mostrado."""
		anterior = texto[:posicion]
		try:
			extra = len(self.fin_de_linea.encode(self.codificacion)) - len("\n".encode(self.codificacion))
			bytes_ = len(anterior.encode(self.codificacion, errors="replace")) + anterior.count("\n") * extra
		except LookupError:
			bytes_ = len(anterior)
		inicio = self.frontera(indice)
		if inicio == 0:
			bytes_ += codificacion.bom_de(self.leer(0, 4))[1]
		return min(self.tamano, inicio + bytes_)

	def texto_de_byte(self, desplazamiento: int) -> tuple[int, int]:
		"""(bloque de texto, posición) donde cae un byte del archivo."""
		indice = 0
		while indice + 1 < self.bloques_texto and self.frontera(indice + 1) <= desplazamiento:
			indice += 1
		inicio = self.frontera(indice)
		parcial, _usada = codificacion.decodificar(self.leer(inicio, max(0, desplazamiento - inicio)), self.codificacion)
		return indice, len(normalizar_texto(parcial))

	# Búsqueda -------------------------------------------------------------------

	def buscar_texto(self, patron: re.Pattern[str], bloque: int, desde: int, atras: bool, cancelacion=None) -> Encontrado | None:
		"""Busca en todos los bloques de texto desde (bloque, posición); al llegar al extremo da la vuelta."""
		total = self.bloques_texto

		def en_bloque(indice: int) -> tuple[int, int, bool] | None:
			base.comprobar(cancelacion)
			texto = self.texto_bloque(indice)
			return a_buscar.buscar_en(texto, patron, len(texto) if atras else 0, atras, envolver=False)

		encontrado = a_buscar.buscar_en(self.texto_bloque(bloque), patron, desde, atras, envolver=False)
		if encontrado:
			return Encontrado(bloque, encontrado[0], encontrado[1], False)
		for indice in (range(bloque - 1, -1, -1) if atras else range(bloque + 1, total)):
			encontrado = en_bloque(indice)
			if encontrado:
				return Encontrado(indice, encontrado[0], encontrado[1], False)
		for indice in (range(total - 1, bloque, -1) if atras else range(0, bloque)):
			encontrado = en_bloque(indice)
			if encontrado:
				return Encontrado(indice, encontrado[0], encontrado[1], True)
		# Por último, el bloque de partida al otro lado del cursor.
		encontrado = en_bloque(bloque)
		if encontrado and ((not atras and encontrado[0] < desde) or (atras and encontrado[0] >= desde)):
			return Encontrado(bloque, encontrado[0], encontrado[1], True)
		return None

	def buscar_bytes(self, patron: re.Pattern[bytes], desde: int, atras: bool, cancelacion=None) -> Encontrado | None:
		"""Busca bytes desde un desplazamiento. En el resultado, ``inicio`` y ``fin`` son desplazamientos del archivo."""
		solape = 4096

		def adelante(inicio: int, limite: int) -> tuple[int, int] | None:
			posicion = inicio
			while posicion < limite:
				base.comprobar(cancelacion)
				for coincidencia in patron.finditer(self.leer(posicion, BLOQUE + solape)):
					if posicion + coincidencia.start() >= limite:
						break
					if coincidencia.end() > coincidencia.start():
						return posicion + coincidencia.start(), posicion + coincidencia.end()
				posicion += BLOQUE
			return None

		def hacia_atras(limite: int, minimo: int) -> tuple[int, int] | None:
			fin = limite
			while fin > minimo:
				base.comprobar(cancelacion)
				inicio = max(minimo, fin - BLOQUE)
				ultima = None
				for coincidencia in patron.finditer(self.leer(inicio, fin - inicio + solape)):
					if inicio + coincidencia.start() >= fin:
						break
					if coincidencia.end() > coincidencia.start():
						ultima = coincidencia
				if ultima is not None:
					return inicio + ultima.start(), inicio + ultima.end()
				fin = inicio
			return None

		vuelta = False
		rango = hacia_atras(desde, 0) if atras else adelante(desde, self.tamano)
		if rango is None:
			vuelta = True
			rango = hacia_atras(self.tamano, desde) if atras else adelante(0, desde)
		if rango is None:
			return None
		return Encontrado(rango[0] // BLOQUE, rango[0], rango[1], vuelta)


def posicion_hex(desplazamiento: int) -> tuple[int, int]:
	"""(bloque hexadecimal, posición en su texto) del byte ``desplazamiento``."""
	bloque, resto = divmod(desplazamiento, BLOQUE)
	linea, columna = divmod(resto, ANCHO_HEX)
	return bloque, linea * (LARGO_LINEA_HEX + 1) + COLUMNA_BYTES + columna * 3


def byte_de_hex(bloque: int, posicion: int) -> int:
	"""Byte que corresponde a una posición del volcado hexadecimal mostrado."""
	linea, columna = divmod(posicion, LARGO_LINEA_HEX + 1)
	if columna >= COLUMNA_TEXTO:
		byte = columna - COLUMNA_TEXTO
	else:
		byte = (columna - COLUMNA_BYTES) // 3
	byte = max(0, min(ANCHO_HEX - 1, byte))
	return bloque * BLOQUE + linea * ANCHO_HEX + byte


# ── Ventana ─────────────────────────────────────────────────────────────────────


TECLAS_VISOR = (
	"Teclas del visor:\n"
	"F2: ajuste de línea.\n"
	"F4: modo texto o hexadecimal.\n"
	"F8: codificación.\n"
	"F7 o Ctrl+F: buscar.\n"
	"F3 o Mayús+F7: buscar siguiente.\n"
	"Mayús+F3: buscar anterior.\n"
	"Ctrl+G: ir a una línea (en hexadecimal, a un desplazamiento).\n"
	"Ctrl+Av Pág y Ctrl+Re Pág: bloque siguiente y anterior en archivos grandes.\n"
	"Ctrl+C: copiar. Ctrl+A: seleccionar todo.\n"
	"Ctrl+Mayús+I: decir la barra de estado.\n"
	"En un documento con secciones: F6 sección siguiente, Mayús+F6 sección anterior, "
	"Ctrl+L lista de secciones, Ctrl+P ir a una página.\n"
	"Ctrl+H: ayuda del control enfocado.\n"
	"Escape o F10: cerrar."
)


class VentanaVisor(wx.Frame):
	"""Visor de un archivo de cualquier proveedor.

	:param proveedor, ruta: el archivo.
	:param config: ``Configuracion`` (claves ``visor.*``).
	:param tareas: ``GestorTareas``; por defecto, el de la ventana principal.
	:param modo: «texto» o «hexadecimal»; ``None`` elige hexadecimal para los binarios.
	"""

	def __init__(self, padre: wx.Window | None, proveedor: base.Proveedor, ruta: str, config=None, tareas=None,
			modo: str | None = None, *, documento: Any = None, visor_complemento: str | None = None) -> None:
		self.proveedor = proveedor
		self.ruta = ruta
		#: 2.0 (14.7): ``api.Documento`` que se muestra con secciones (de un visor de complemento).
		self.documento = documento
		self._visor_complemento = visor_complemento
		#: (posición en el texto, sección) de cada sección del documento, en orden.
		self.secciones: list[tuple[int, Any]] = []
		self.nombre = (documento.titulo if documento is not None else "") or proveedor.nombre(ruta) or ruta
		super().__init__(padre, title=_("{n} - Visor").format(n=self.nombre), name=_("Visor"))
		self.SetSize(self.FromDIP(wx.Size(900, 650)))
		self.config = config or configuracion_de(padre)
		self.tareas = tareas or tareas_de(padre)
		self.modelo: ModeloVisor | None = None
		self.modo = modo or TEXTO
		self._modo_pedido = modo
		self.bloque = 0
		self.contenido = ""
		self._mapa = MapaPosiciones("")
		self._temporal: str | None = None
		self._tareas: list[Any] = []
		self._cerrando = False
		self._ocupado = False
		self.ajuste = bool(self.config.obtener("visor.ajuste_linea"))
		self.puntos = int(self.config.obtener("visor.tamano_fuente"))

		self.panel = wx.Panel(self)
		self.sizer = wx.BoxSizer(wx.VERTICAL)
		self.panel.SetSizer(self.sizer)
		self.etiqueta: wx.StaticText | None = None
		self.texto: wx.TextCtrl | None = None
		self._crear_texto(_("Cargando..."))
		self._crear_menus()
		self.barra = self.CreateStatusBar(4)
		self.barra.SetStatusWidths([-3, -2, -2, -2])
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
		self._cancelar_suscripcion = self.config.suscribir(self._al_cambiar_config, "visor.")
		self.cargar()

	# Construcción -------------------------------------------------------------

	def _crear_texto(self, valor: str = "") -> None:
		"""Crea (o vuelve a crear) la etiqueta y el campo, en ese orden.

		El ajuste de línea de un RichEdit se fija al crearlo; para cambiarlo se
		crean los dos de nuevo, etiqueta primero, para que el lector siga
		tomando el nombre del campo de la etiqueta creada justo antes.
		"""
		con_foco = self.texto is not None and wx.Window.FindFocus() is self.texto
		posicion = self.texto.GetInsertionPoint() if self.texto else 0
		if self.texto is not None:
			valor = self.texto.GetValue()
			self.texto.Destroy()
			self.etiqueta.Destroy()
		self.sizer.Clear()
		self.etiqueta = wx.StaticText(self.panel, label=_("&Contenido de {n}:").format(n=self.nombre))
		estilo = wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_NOHIDESEL | (0 if self.ajuste else wx.TE_DONTWRAP)
		self.texto = wx.TextCtrl(self.panel, style=estilo, name=_("Contenido de {n}").format(n=self.nombre))
		self.texto.SetHelpText(_("Contenido del archivo, de solo lectura. Recórralo con las flechas; F7 busca, Ctrl+G va a una línea "
			"y F4 cambia entre texto y hexadecimal."))
		self.texto.SetFont(fuente_monoespaciada(self.puntos))
		self.texto.ChangeValue(valor)
		self.texto.SetInsertionPoint(min(posicion, self.texto.GetLastPosition()))
		self.texto.Bind(wx.EVT_KEY_UP, self._al_mover)
		self.texto.Bind(wx.EVT_LEFT_UP, self._al_mover)
		self.sizer.Add(self.etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		self.sizer.Add(self.texto, 1, wx.EXPAND | wx.ALL, 6)
		self.panel.Layout()
		if con_foco:
			self.texto.SetFocus()

	def _crear_menus(self) -> None:
		barra = wx.MenuBar()
		archivo = wx.Menu()
		self._item(archivo, _("&Cerrar\tEscape"), _("Cierra el visor (también F10)."), self.Close)
		barra.Append(archivo, _("&Archivo"))
		edicion = wx.Menu()
		self._item(edicion, _("&Copiar\tCtrl+C"), _("Copia el texto seleccionado."), lambda: self.texto.Copy())
		self._item(edicion, _("Seleccionar &todo\tCtrl+A"), _("Selecciona todo el texto mostrado."), lambda: self.texto.SelectAll())
		edicion.AppendSeparator()
		self._item(edicion, _("&Buscar...\tF7"), _("Busca un texto (también Ctrl+F)."), self.buscar)
		self._item(edicion, _("Buscar &siguiente\tF3"), _("Repite la búsqueda hacia delante (también Mayús+F7)."),
			lambda: self.repetir_busqueda(False))
		self._item(edicion, _("Buscar &anterior\tShift+F3"), _("Repite la búsqueda hacia atrás."), lambda: self.repetir_busqueda(True))
		self._item(edicion, _("&Ir a la línea...\tCtrl+G"), _("Va a una línea; en hexadecimal, a un desplazamiento."), self.ir_a)
		barra.Append(edicion, _("&Edición"))
		ver = wx.Menu()
		self.item_ajuste = self._item(ver, _("&Ajuste de línea\tF2"), _("Las líneas largas continúan debajo."),
			self.alternar_ajuste, wx.ITEM_CHECK)
		self.item_hex = self._item(ver, _("Modo &hexadecimal\tF4"), _("Cambia entre texto y volcado hexadecimal."),
			self.alternar_modo, wx.ITEM_CHECK)
		self._item(ver, _("&Codificación...\tF8"), _("Elige con qué codificación se lee el archivo."), self.elegir_codificacion)
		ver.AppendSeparator()
		self._item(ver, _("Bloque si&guiente\tCtrl+PgDn"), _("En archivos grandes, muestra el bloque siguiente."),
			lambda: self.cambiar_bloque(1))
		self._item(ver, _("Bloque a&nterior\tCtrl+PgUp"), _("En archivos grandes, muestra el bloque anterior."),
			lambda: self.cambiar_bloque(-1))
		ver.AppendSeparator()
		self._item(ver, _("A&umentar la letra"), _("Letra más grande en todos los visores."), lambda: self.cambiar_letra(2))
		self._item(ver, _("&Reducir la letra"), _("Letra más pequeña en todos los visores."), lambda: self.cambiar_letra(-2))
		self._item(ver, _("&Decir la barra de estado\tCtrl+Shift+I"), _("Dice la línea, la codificación, el modo y el tamaño."),
			self.decir_estado)
		ver.AppendSeparator()
		self._item(ver, _("&Sección siguiente\tF6"), _("En un documento con secciones, va a la sección siguiente."),
			lambda: self.cambiar_seccion(1))
		self._item(ver, _("Sección an&terior\tShift+F6"), _("En un documento con secciones, va a la sección anterior."),
			lambda: self.cambiar_seccion(-1))
		self._item(ver, _("&Lista de secciones...\tCtrl+L"), _("Lista las secciones del documento para ir a una (con búsqueda)."),
			self.lista_secciones)
		self._item(ver, _("Ir a una &página...\tCtrl+P"), _("En un documento con páginas, va a la página que se escriba."),
			self.ir_a_pagina)
		barra.Append(ver, _("&Ver"))
		ayuda = wx.Menu()
		self._item(ayuda, _("&Teclas del visor"), _("Muestra la lista de teclas de esta ventana."),
			lambda: _mostrar_teclas(self, _(TECLAS_VISOR)))
		self._item(ayuda, _("Ayuda del &control enfocado\tCtrl+H"), _("Explica para qué sirve el control que tiene el foco."),
			self._ayuda_contextual)
		barra.Append(ayuda, _("A&yuda"))
		self.SetMenuBar(barra)
		self.item_ajuste.Check(self.ajuste)
		self.item_hex.Check(self.modo == HEXADECIMAL)

	def _item(self, menu: wx.Menu, etiqueta: str, ayuda: str, accion: Callable[[], Any], tipo: int = wx.ITEM_NORMAL) -> wx.MenuItem:
		item = menu.Append(wx.ID_ANY, etiqueta, ayuda, tipo)
		self.Bind(wx.EVT_MENU, lambda _e: accion(), item)
		return item

	def _ayuda_contextual(self) -> None:
		from app.ui.accesibilidad.ayuda import describir_control_enfocado

		describir_control_enfocado(self)

	def mostrar(self) -> None:
		self.Show()
		self.Raise()
		self.texto.SetFocus()

	# Carga ---------------------------------------------------------------------

	def _enviar(self, trabajo, al_terminar, nombre: str, al_fallar=None):
		def fallo(error: BaseException) -> None:
			self._ocupado = False
			if isinstance(error, TareaCancelada) or self._cerrando:
				return
			log.warning("Fallo en el visor (%s): %s", nombre, error)
			if al_fallar is not None:
				al_fallar(error)
			else:
				anuncios.anunciar(mensaje_error(error), anuncios.ESENCIAL)

		def listo(resultado) -> None:
			self._ocupado = False
			if self._cerrando or not self:
				return
			al_terminar(resultado)

		self._ocupado = True
		tarea = self.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre=nombre)
		if tarea is not None:
			self._tareas = [t for t in self._tareas if not t.terminada] + [tarea]
		return tarea

	def cargar(self) -> None:
		"""Extrae el archivo si hace falta, lo analiza y muestra el primer bloque (en un hilo)."""
		proveedor, ruta = self.proveedor, self.ruta
		limite = int(self.config.obtener("visor.limite_mb")) * BLOQUE
		preferida = str(self.config.obtener("visor.codificacion"))
		modo_pedido = self._modo_pedido
		anterior = self._temporal
		documento_dado, visor_complemento = self.documento, self._visor_complemento

		def trabajo(tarea):
			documento = documento_dado
			if documento is None and visor_complemento:
				documento = documento_de_complemento(visor_complemento, proveedor, ruta, tarea)
			if documento is not None:
				# El documento entero en un solo bloque (las secciones se cuentan sobre ese texto).
				temporal = escribir_documento(documento)
				try:
					modelo = ModeloVisor(temporal, None, max(limite, os.path.getsize(temporal) + 1), "utf-8")
					return modelo, temporal, TEXTO, modelo.contenido(TEXTO, 0), documento
				except BaseException:
					temporales.borrar(temporal)
					raise
			local = proveedor.ruta_local(ruta)
			temporal = None
			if local is None:
				temporal = extraer(proveedor, ruta, tarea)
				local = temporal
			try:
				modelo = ModeloVisor(local, None, limite, preferida)
				modo = modo_pedido or (HEXADECIMAL if modelo.binario else TEXTO)
				return modelo, temporal, modo, modelo.contenido(modo, 0), None
			except BaseException:
				if temporal:
					temporales.borrar(temporal)
				raise

		def listo(resultado) -> None:
			modelo, temporal, modo, contenido, documento = resultado
			if anterior and anterior != temporal:
				temporales.borrar(anterior)
			self.modelo, self._temporal, self.modo = modelo, temporal, modo
			self.documento = documento
			self.secciones = posiciones_secciones(documento, contenido) if documento is not None else []
			if documento is not None and documento.titulo and self.nombre != documento.titulo:
				self.nombre = documento.titulo
				self.SetTitle(_("{n} - Visor").format(n=self.nombre))
			self.item_hex.Check(modo == HEXADECIMAL)
			self._mostrar(0, contenido, 0)
			if documento is not None and documento.aviso:
				anuncios.anunciar(documento.aviso, anuncios.NORMAL)
			if modelo.binario and not modo_pedido and documento is None:
				anuncios.anunciar(_("Archivo binario: se muestra en hexadecimal"), anuncios.NORMAL)

		def fallo(error: BaseException) -> None:
			texto = _("No se pudo abrir «{n}»: {e}").format(n=self.nombre, e=mensaje_error(error))
			if self.texto:
				self.texto.ChangeValue(texto)
			anuncios.anunciar(texto, anuncios.ESENCIAL)

		if self.texto:
			self.texto.ChangeValue(_("Cargando..."))
		self._enviar(trabajo, listo, "visor-cargar", fallo)

	def _mostrar(self, bloque: int, contenido: str, posicion: int, seleccion: tuple[int, int] | None = None) -> None:
		"""Pone el contenido de un bloque en el campo (posiciones de Python)."""
		self.bloque = bloque
		self.contenido = contenido
		self._mapa = MapaPosiciones(contenido)
		self.texto.Freeze()
		try:
			self.texto.ChangeValue(contenido)
			if seleccion:
				self.texto.SetSelection(self._mapa.a_control(seleccion[0]), self._mapa.a_control(seleccion[1]))
			else:
				self.texto.SetInsertionPoint(self._mapa.a_control(min(posicion, len(contenido))))
		finally:
			self.texto.Thaw()
		self.texto.ShowPosition(self.texto.GetInsertionPoint())
		self._actualizar_estado()

	# Estado -----------------------------------------------------------------

	def posicion(self) -> int:
		"""Posición del cursor en el texto de Python."""
		return self._mapa.de_control(self.texto.GetInsertionPoint())

	def _al_mover(self, evento: wx.Event) -> None:
		evento.Skip()
		wx.CallAfter(self._actualizar_estado)

	def textos_estado(self) -> list[str]:
		if self.modelo is None:
			return [_("Cargando..."), "", "", ""]
		modelo = self.modelo
		posicion = self.posicion()
		if self.modo == HEXADECIMAL:
			desplazamiento = byte_de_hex(self.bloque, posicion) if self.contenido else 0
			lugar = _("Desplazamiento {d} (0x{h:X})").format(d=formato.miles(desplazamiento), h=desplazamiento)
		else:
			linea, columna = linea_y_columna(self.contenido, posicion)
			antes = modelo.lineas_antes(self.bloque)
			if antes is None:
				lugar = _("Línea {l} del bloque, columna {c}").format(l=formato.miles(linea), c=columna)
			else:
				lugar = _("Línea {l}, columna {c}").format(l=formato.miles(antes + linea), c=columna)
		nombre_cod = codificacion.NOMBRES.get(modelo.codificacion, modelo.codificacion)
		if modelo.automatica:
			nombre_cod += _(" (detectada)")
		modo = _("Hexadecimal") if self.modo == HEXADECIMAL else _("Texto")
		tamano = formato.tamano_legible(modelo.tamano)
		total = modelo.bloques(self.modo)
		if total > 1:
			tamano += ", " + _("bloque {b} de {t}").format(b=self.bloque + 1, t=total)
		if self.secciones and self.modo == TEXTO:
			indice = self.seccion_actual()
			if indice >= 0:
				lugar = _("Sección {i} de {n}: {t}").format(i=indice + 1, n=len(self.secciones),
					t=self.secciones[indice][1].titulo) + ". " + lugar
		return [lugar, nombre_cod, modo, tamano]

	# Secciones de un documento (14.7) -----------------------------------------

	def seccion_actual(self) -> int:
		"""Índice de la sección en la que está el cursor (−1 antes de la primera o sin secciones)."""
		posicion = self.posicion()
		indice = bisect.bisect_right([p for p, _s in self.secciones], posicion) - 1
		return indice

	def _sin_secciones(self) -> bool:
		if self.secciones and self.modo == TEXTO:
			return False
		anuncios.anunciar(_("Este archivo no tiene secciones") if not self.secciones else _("Las secciones solo están en modo texto"),
			anuncios.RESULTADO)
		return True

	def ir_a_seccion(self, indice: int) -> None:
		posicion, seccion = self.secciones[indice]
		self.texto.SetInsertionPoint(self._mapa.a_control(posicion))
		self.texto.ShowPosition(self.texto.GetInsertionPoint())
		self._actualizar_estado()
		anuncios.anunciar(_("Sección {i} de {n}: {t}").format(i=indice + 1, n=len(self.secciones), t=seccion.titulo),
			anuncios.RESULTADO)

	def cambiar_seccion(self, paso: int) -> None:
		"""F6 y Mayús+F6: sección siguiente o anterior."""
		if not self._listo_para() or self._sin_secciones():
			return
		actual = self.seccion_actual()
		if paso < 0 and actual >= 0 and self.posicion() > self.secciones[actual][0]:
			destino = actual  # dentro de una sección, Mayús+F6 vuelve a su principio
		else:
			destino = actual + paso
		if destino < 0:
			anuncios.anunciar(_("Es la primera sección"), anuncios.RESULTADO)
			return
		if destino >= len(self.secciones):
			anuncios.anunciar(_("Es la última sección"), anuncios.RESULTADO)
			return
		self.ir_a_seccion(destino)

	def lista_secciones(self) -> None:
		"""Ctrl+L: diálogo con la lista de secciones y búsqueda; Intro va a la elegida."""
		if not self._listo_para() or self._sin_secciones():
			return
		titulos = [("  " * max(0, s.nivel - 1)) + s.titulo for _p, s in self.secciones]
		elegida = elegir_seccion(self, titulos, max(0, self.seccion_actual()))
		self.texto.SetFocus()
		if elegida is not None:
			self.ir_a_seccion(elegida)

	def ir_a_pagina(self) -> None:
		"""Ctrl+P: va a la primera sección de la página escrita (o de la siguiente que exista)."""
		if not self._listo_para() or self._sin_secciones():
			return
		paginas = [s.pagina for _p, s in self.secciones if s.pagina]
		if not paginas:
			anuncios.anunciar(_("Este documento no tiene páginas"), anuncios.RESULTADO)
			return
		actual = self.secciones[max(0, self.seccion_actual())][1].pagina or paginas[0]
		numero = pedir_pagina(self, actual, max(paginas))
		self.texto.SetFocus()
		if numero is None:
			return
		self.ir_a_numero_de_pagina(numero)

	def ir_a_numero_de_pagina(self, numero: int) -> bool:
		for indice, (_posicion, seccion) in enumerate(self.secciones):
			if seccion.pagina and seccion.pagina >= numero:
				self.ir_a_seccion(indice)
				return True
		anuncios.anunciar(_("El documento no tiene la página {n}").format(n=numero), anuncios.RESULTADO)
		return False

	def _actualizar_estado(self) -> None:
		if not self or self.texto is None:
			return
		for indice, texto in enumerate(self.textos_estado()):
			self.barra.SetStatusText(texto, indice)

	def decir_estado(self) -> None:
		partes = [t for t in self.textos_estado() if t]
		anuncios.anunciar(". ".join(partes), anuncios.RESULTADO)

	# Acciones ---------------------------------------------------------------

	def _listo_para(self) -> bool:
		if self.modelo is None:
			anuncios.anunciar(_("Todavía se está cargando el archivo"), anuncios.RESULTADO)
			return False
		return True

	def alternar_ajuste(self) -> None:
		self.ajuste = not self.ajuste
		self.item_ajuste.Check(self.ajuste)
		self._crear_texto()
		self._mapa = MapaPosiciones(self.contenido)
		try:
			self.config.establecer("visor.ajuste_linea", self.ajuste)
		except Exception:  # noqa: BLE001 - guardar la preferencia no debe romper el visor
			log.warning("No se pudo guardar visor.ajuste_linea", exc_info=True)
		anuncios.anunciar(_("Ajuste de línea activado") if self.ajuste else _("Ajuste de línea desactivado"), anuncios.RESULTADO)

	def cambiar_letra(self, paso: int) -> None:
		nuevo = max(8, min(40, self.puntos + paso))
		if nuevo == self.puntos:
			anuncios.anunciar(_("La letra ya está en el tamaño {n}").format(n=nuevo), anuncios.RESULTADO)
			return
		self._aplicar_letra(nuevo)
		try:
			self.config.establecer("visor.tamano_fuente", nuevo)
		except Exception:  # noqa: BLE001
			log.warning("No se pudo guardar visor.tamano_fuente", exc_info=True)
		anuncios.anunciar(_("Letra de {n} puntos").format(n=nuevo), anuncios.RESULTADO)

	def _aplicar_letra(self, puntos: int) -> None:
		self.puntos = puntos
		self.texto.SetFont(fuente_monoespaciada(puntos))
		self.panel.Layout()

	def _al_cambiar_config(self, clave: str, _anterior, nuevo) -> None:
		def aplicar() -> None:
			if not self or self._cerrando:
				return
			if clave == "visor.tamano_fuente" and int(nuevo) != self.puntos:
				self._aplicar_letra(int(nuevo))
			elif clave == "visor.ajuste_linea" and bool(nuevo) != self.ajuste:
				self.ajuste = bool(nuevo)
				self.item_ajuste.Check(self.ajuste)
				self._crear_texto()

		wx.CallAfter(aplicar)

	def alternar_modo(self) -> None:
		"""F4: texto o hexadecimal, conservando más o menos el mismo byte bajo el cursor."""
		if not self._listo_para():
			self.item_hex.Check(self.modo == HEXADECIMAL)
			return
		modelo, contenido, bloque, posicion = self.modelo, self.contenido, self.bloque, self.posicion()
		nuevo = TEXTO if self.modo == HEXADECIMAL else HEXADECIMAL

		def trabajo(_tarea):
			if nuevo == HEXADECIMAL:
				byte = modelo.byte_de_texto(bloque, posicion, contenido)
				destino, pos = posicion_hex(byte)
				destino = min(destino, modelo.bloques_hex - 1)
			else:
				destino, pos = modelo.texto_de_byte(byte_de_hex(bloque, posicion))
			return destino, pos, modelo.contenido(nuevo, destino)

		def listo(resultado) -> None:
			destino, pos, texto = resultado
			self.modo = nuevo
			self.item_hex.Check(nuevo == HEXADECIMAL)
			self._mostrar(destino, texto, pos)
			anuncios.anunciar(_("Modo hexadecimal") if nuevo == HEXADECIMAL else _("Modo texto"), anuncios.RESULTADO)

		self._enviar(trabajo, listo, "visor-modo")

	def elegir_codificacion(self) -> None:
		if not self._listo_para():
			return
		from app.ui.dialogos.a_formato import AUTOMATICA, pedir_codificacion

		actual = AUTOMATICA if self.modelo.automatica else self.modelo.codificacion
		elegida = pedir_codificacion(self, actual)
		self.texto.SetFocus()
		if elegida is None or elegida == actual:
			return
		self.aplicar_codificacion(elegida)

	def aplicar_codificacion(self, valor: str) -> None:
		modelo, bloque, modo, posicion = self.modelo, self.bloque, self.modo, self.posicion()
		byte = modelo.byte_de_texto(bloque, posicion, self.contenido) if modo == TEXTO else 0

		def trabajo(_tarea):
			modelo.fijar_codificacion(valor)
			if modo == HEXADECIMAL:
				return bloque, posicion, modelo.contenido(HEXADECIMAL, bloque)
			destino, pos = modelo.texto_de_byte(byte)
			return destino, pos, modelo.texto_bloque(destino)

		def listo(resultado) -> None:
			destino, pos, texto = resultado
			self._mostrar(destino, texto, pos)
			anuncios.anunciar(_("Codificación: {c}").format(c=codificacion.NOMBRES.get(modelo.codificacion, modelo.codificacion)),
				anuncios.RESULTADO)

		self._enviar(trabajo, listo, "visor-codificacion")

	def cambiar_bloque(self, paso: int, al_terminar: Callable[[], None] | None = None) -> None:
		if not self._listo_para():
			return
		total = self.modelo.bloques(self.modo)
		destino = self.bloque + paso
		if total <= 1:
			anuncios.anunciar(_("El archivo se ve entero: no hay más bloques"), anuncios.RESULTADO)
			return
		if destino < 0 or destino >= total:
			anuncios.anunciar(_("Es el primer bloque") if destino < 0 else _("Es el último bloque"), anuncios.RESULTADO)
			return
		modelo, modo = self.modelo, self.modo

		def trabajo(tarea):
			if modo == TEXTO:
				modelo.contar_hasta(destino, tarea)
			return modelo.contenido(modo, destino)

		def listo(texto: str) -> None:
			self._mostrar(destino, texto, 0)
			anuncios.anunciar(_("Bloque {b} de {t}").format(b=destino + 1, t=total), anuncios.RESULTADO)
			if al_terminar:
				al_terminar()

		self._enviar(trabajo, listo, "visor-bloque")

	def ir_a(self) -> None:
		if not self._listo_para():
			return
		hexadecimal = self.modo == HEXADECIMAL
		if hexadecimal:
			actual = byte_de_hex(self.bloque, self.posicion()) if self.contenido else 0
			maximo = max(0, self.modelo.tamano - 1)
		else:
			linea, _columna = linea_y_columna(self.contenido, self.posicion())
			actual = (self.modelo.lineas_antes(self.bloque) or 0) + linea
			maximo = self.modelo.total_lineas_conocido() if not self.modelo.entero else \
				self.contenido.count("\n") + (1 if self.contenido and not self.contenido.endswith("\n") else 0)
		numero = a_buscar.pedir_posicion(self, hexadecimal, actual, 0 if hexadecimal else 1, maximo)
		self.texto.SetFocus()
		if numero is not None:
			self.ir_a_posicion(numero)

	def ir_a_posicion(self, numero: int, al_terminar: Callable[[], None] | None = None) -> None:
		"""Línea (texto, desde 1) o desplazamiento (hexadecimal, desde 0)."""
		modelo, modo = self.modelo, self.modo

		def trabajo(tarea):
			if modo == HEXADECIMAL:
				bloque, pos = posicion_hex(min(numero, max(0, modelo.tamano - 1)))
				return bloque, pos, modelo.hex_bloque(bloque)
			destino = modelo.ir_a_linea(numero, tarea)
			if destino is None:
				return None
			return destino[0], destino[1], modelo.texto_bloque(destino[0])

		def listo(resultado) -> None:
			if resultado is None:
				anuncios.anunciar(_("El archivo no tiene la línea {n}").format(n=formato.miles(numero)), anuncios.RESULTADO)
				return
			bloque, pos, texto = resultado
			self._mostrar(bloque, texto, pos)
			if modo == TEXTO:
				anuncios.anunciar(_("Línea {n}: {t}").format(n=formato.miles(numero), t=texto_de_linea(texto, pos)), anuncios.RESULTADO)
			else:
				anuncios.anunciar(texto_de_linea(texto, pos), anuncios.RESULTADO)
			if al_terminar:
				al_terminar()

		self._enviar(trabajo, listo, "visor-ir-a")

	# Búsqueda ----------------------------------------------------------------

	def buscar(self) -> None:
		if not self._listo_para():
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
		if self._listo_para():
			self.buscar_con(opciones.hacia(atras))

	def buscar_con(self, opciones: a_buscar.OpcionesBusqueda, al_terminar: Callable[[bool], None] | None = None) -> None:
		"""Busca en todo el archivo (en un hilo) y selecciona lo encontrado."""
		modelo, modo, bloque = self.modelo, self.modo, self.bloque
		inicio, fin = (self._mapa.de_control(p) for p in self.texto.GetSelection())
		desde = inicio if opciones.atras else (fin if fin > inicio else self.posicion())
		patron = a_buscar.compilar(opciones)
		patron_bytes = a_buscar.compilar_bytes(opciones, modelo.codificacion)
		byte_desde = 0
		if modo == HEXADECIMAL and self.contenido:
			byte_desde = byte_de_hex(bloque, inicio if opciones.atras else self.posicion())
			if not opciones.atras and fin > inicio:
				byte_desde = byte_de_hex(bloque, inicio) + 1
		if modelo.bloques(modo) > 1:
			anuncios.anunciar(_("Buscando..."), anuncios.DETALLE)

		def trabajo(tarea):
			if modo == HEXADECIMAL:
				encontrado = modelo.buscar_bytes(patron_bytes, byte_desde, opciones.atras, tarea)
				if encontrado is None:
					return None
				destino, pos = posicion_hex(encontrado.inicio)
				return encontrado, destino, pos, pos + 2, modelo.hex_bloque(destino)
			encontrado = modelo.buscar_texto(patron, bloque, desde, opciones.atras, tarea)
			if encontrado is None:
				return None
			modelo.contar_hasta(encontrado.bloque, tarea)
			return encontrado, encontrado.bloque, encontrado.inicio, encontrado.fin, modelo.texto_bloque(encontrado.bloque)

		def listo(resultado) -> None:
			if resultado is None:
				anuncios.anunciar(_("No se encontró «{t}»").format(t=opciones.texto), anuncios.RESULTADO)
				if al_terminar:
					al_terminar(False)
				return
			encontrado, destino, pos_inicio, pos_fin, texto = resultado
			self._mostrar(destino, texto, pos_inicio, (pos_inicio, pos_fin))
			partes = []
			if encontrado.vuelta:
				partes.append(_("Búsqueda desde el final") if opciones.atras else _("Búsqueda desde el principio"))
			if modo == TEXTO:
				linea, _columna = linea_y_columna(texto, pos_inicio)
				antes = self.modelo.lineas_antes(destino)
				numero = linea + antes if antes is not None else linea
				partes.append(_("Línea {n}: {t}").format(n=formato.miles(numero), t=texto_de_linea(texto, pos_inicio)))
			else:
				partes.append(_("Desplazamiento {d}").format(d=formato.miles(encontrado.inicio)))
			anuncios.anunciar(". ".join(partes), anuncios.RESULTADO)
			if al_terminar:
				al_terminar(True)

		self._enviar(trabajo, listo, "visor-buscar")

	# Teclado y cierre --------------------------------------------------------

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla == wx.WXK_F10 and modificadores == wx.MOD_NONE:
			self.Close()
			return
		if tecla == ord("F") and modificadores == wx.MOD_CONTROL:
			self.buscar()
			return
		if tecla == wx.WXK_F7 and modificadores == wx.MOD_SHIFT:
			self.repetir_busqueda(False)
			return
		evento.Skip()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		self._cerrando = True
		for tarea in self._tareas:
			tarea.cancelar("Se cerró el visor")
		self._liberar()
		self.Destroy()

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		evento.Skip()
		if evento.GetEventObject() is self:
			self._cerrando = True
			self._liberar()

	def _liberar(self) -> None:
		if self._cancelar_suscripcion is not None:
			self._cancelar_suscripcion()
			self._cancelar_suscripcion = None
		if self._temporal:
			temporales.borrar(self._temporal)
			self._temporal = None


def _mostrar_teclas(padre: wx.Window, texto: str) -> None:
	from app.ui.accesibilidad import dialogos

	dialogos.mostrar_mensaje(padre, texto, _("Teclas"))


def extraer(proveedor: base.Proveedor, ruta: str, cancelacion=None) -> str:
	"""Copia un archivo de un comprimido o servidor a ``data/temp/extraidos`` (en un hilo).

	A diferencia de ``Proveedor.extraer_temporal``, quien llama decide cuándo
	se borra (al cerrar el visor, o al salir si lo abrió un programa externo).
	"""
	destino = temporales.ruta_temporal(proveedor.nombre(ruta))
	try:
		with proveedor.abrir_lectura(ruta) as origen, open(rutas.con_prefijo_largo(destino), "wb") as salida:
			while True:
				base.comprobar(cancelacion)
				bloque = origen.read(BLOQUE)
				if not bloque:
					break
				salida.write(bloque)
	except BaseException:
		temporales.borrar(destino)
		raise
	return destino


def abrir(padre: wx.Window | None, proveedor: base.Proveedor, ruta: str, config=None, tareas=None, modo: str | None = None,
		mostrar: bool = True, complementos: bool = True) -> VentanaVisor | None:
	"""Abre el visor interno sobre ``(proveedor, ruta)`` y lo muestra.

	2.0 (3.5, 14.7): con ``complementos`` (F3 sin asociación «ver»), si el visor de
	complemento de mayor prioridad cuyo patrón coincide devuelve un ``Documento``,
	el visor lo muestra con secciones (si falla, el archivo como siempre); si es un
	visor con ventana propia, se abre esa ventana y se devuelve ``None``.
	"""
	visor_complemento = None
	if complementos and modo is None:
		encontrado = visor_de_complemento(proveedor.nombre(ruta) or ruta)
		if encontrado is not None:
			visor_complemento, con_ventana = encontrado
			if con_ventana:
				from app.plugins import registro

				registro.abrir_ventana_visor(visor_complemento, proveedor, ruta,
					al_fallar=lambda motivo: _abrir_sin_complemento(padre, proveedor, ruta, config, tareas, motivo))
				return None
	ventana = VentanaVisor(padre, proveedor, ruta, config, tareas, modo, visor_complemento=visor_complemento)
	if mostrar:
		ventana.mostrar()
	return ventana


def _abrir_sin_complemento(padre, proveedor, ruta, config, tareas, motivo: str) -> None:
	anuncios.anunciar(motivo, anuncios.RESULTADO)
	abrir(padre, proveedor, ruta, config, tareas, complementos=False)


def visor_de_complemento(nombre: str, vista_rapida: bool = False) -> tuple[str, bool] | None:
	"""(id del visor, con ventana propia) del complemento que ve ``nombre``, o ``None``; nunca activa nada."""
	try:
		from app.plugins import registro

		return registro.visor_para(nombre, vista_rapida=vista_rapida)
	except Exception:  # noqa: BLE001 - un manifiesto raro no deja sin el visor interno
		log.warning("No se pudieron consultar los visores de los complementos", exc_info=True)
		return None


def documento_de_complemento(id_visor: str, proveedor: base.Proveedor, ruta: str, cancelacion=None):
	"""[trabajo] ``Documento`` de un visor de complemento, o ``None`` (se ve el archivo con el visor interno)."""
	try:
		from app.plugins import registro

		return registro.documento_visor(id_visor, proveedor, ruta, cancelacion)
	except Exception:  # noqa: BLE001 - un visor de complemento roto no impide ver el archivo
		log.warning("Falló el visor de complemento %s con %s", id_visor, ruta, exc_info=True)
		return None


def escribir_documento(documento) -> str:
	"""Escribe el texto de un ``Documento`` en ``data/temp`` (UTF-8) y devuelve la ruta (la borra el visor al cerrar)."""
	nombre = "".join(c if c.isalnum() or c in " -_" else "_" for c in documento.titulo)[:80] or "documento"
	ruta = temporales.ruta_temporal(f"{nombre}.txt")
	with open(rutas.con_prefijo_largo(ruta), "w", encoding="utf-8", newline="\n") as salida:
		salida.write(texto_de_documento(documento))
	return ruta


def posiciones_secciones(documento, contenido: str) -> list[tuple[int, Any]]:
	"""Posición (en el texto mostrado) del título de cada sección, buscándolos en orden."""
	resultado: list[tuple[int, Any]] = []
	desde = 0
	for seccion in documento.secciones:
		titulo = seccion.titulo
		posicion = -1
		while True:
			posicion = contenido.find(titulo, desde)
			if posicion <= 0 or contenido[posicion - 1] == "\n":
				break
			desde = posicion + 1
		if posicion < 0:
			continue
		resultado.append((posicion, seccion))
		desde = posicion + len(titulo)
	return resultado


def texto_de_documento(documento) -> str:
	"""Texto de un ``api.Documento`` (2.0, 14.7): cada sección con su título y, si las hay, marcas «Página N»."""
	partes = []
	if getattr(documento, "aviso", ""):
		partes.append(documento.aviso)
	prefijo_pagina = _("Página").casefold()
	for seccion in documento.secciones:
		# Una sección que ya se titula «Página 2 de 80» no lleva además la marca «Página 2».
		if seccion.pagina and not seccion.titulo.strip().casefold().startswith(prefijo_pagina):
			partes.append(_("Página {n}").format(n=seccion.pagina))
		partes.append(seccion.titulo)
		if seccion.texto:
			partes.append(seccion.texto)
	return "\n\n".join(partes) + "\n"


def abrir_documento(padre: wx.Window | None, documento, config=None, tareas=None, mostrar: bool = True) -> VentanaVisor:
	"""Abre en el visor interno un ``Documento`` (14.7): su texto con secciones y páginas.

	F6 y Mayús+F6 van de sección en sección, Ctrl+L las lista con búsqueda, Ctrl+P va a
	una página y la barra de estado dice «Sección 3 de 12: Introducción».
	"""
	from app.services.vfs import resolver

	ventana = VentanaVisor(padre, resolver.proveedor_local(), documento.titulo or "documento", config, tareas, documento=documento)
	if mostrar:
		ventana.mostrar()
	return ventana


# ── Lista de secciones y página (sustituibles en las pruebas) ──────────────────


class DialogoSecciones(wx.Dialog):
	"""Ctrl+L: secciones del documento con un campo de búsqueda; Intro va a la elegida."""

	def __init__(self, padre: wx.Window | None, titulos: list[str], actual: int = 0) -> None:
		super().__init__(padre, title=_("Secciones"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=_("Secciones"))
		from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
		from app.ui.accesibilidad.nombres import crear_campo

		self.titulos = list(titulos)
		self.visibles = list(range(len(self.titulos)))
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		_e, self.campo_buscar = crear_campo(panel, _("&Buscar:"), wx.TextCtrl, sizer=sizer,
			ayuda=_("Escriba parte del título para dejar en la lista solo las secciones que lo contienen."))
		_e, self.lista = crear_campo(panel, _("&Secciones:"), wx.ListBox, choices=[t.strip() for t in self.titulos],
			size=panel.FromDIP(wx.Size(420, 300)), sizer=sizer, ayuda=_("Secciones del documento. Intro va a la elegida."))
		if self.titulos:
			self.lista.SetSelection(min(max(0, actual), len(self.titulos) - 1))
		sizer.Add(crear_botonera(panel, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.campo_buscar.Bind(wx.EVT_TEXT, lambda _e: self.filtrar(self.campo_buscar.GetValue()))
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.EndModal(wx.ID_OK) if self.IsModal() else None)
		preparar_dialogo(self, foco_inicial=self.lista)

	def filtrar(self, texto: str) -> None:
		buscado = texto.strip().casefold()
		self.visibles = [i for i, t in enumerate(self.titulos) if buscado in t.casefold()]
		self.lista.Set([self.titulos[i].strip() for i in self.visibles])
		if self.visibles:
			self.lista.SetSelection(0)

	def elegida(self) -> int | None:
		indice = self.lista.GetSelection()
		return self.visibles[indice] if 0 <= indice < len(self.visibles) else None


def elegir_seccion(padre: wx.Window, titulos: list[str], actual: int = 0) -> int | None:
	"""Índice de la sección elegida en ``DialogoSecciones``, o ``None`` si se cancela."""
	from app.plugins import estado

	dialogo = DialogoSecciones(padre, titulos, actual)
	try:
		with estado.pausa_modal():
			codigo = dialogo.ShowModal()
		return dialogo.elegida() if codigo == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def pedir_pagina(padre: wx.Window, actual: int, maximo: int) -> int | None:
	"""Número de página (1 a ``maximo``) o ``None``."""
	from app.ui.accesibilidad import dialogos

	while True:
		texto = dialogos.pedir_texto(padre, _("&Página (1 a {m}):").format(m=maximo), _("Ir a una página"), str(actual))
		if texto is None:
			return None
		try:
			numero = int(texto.strip())
		except ValueError:
			numero = 0
		if 1 <= numero <= maximo:
			return numero
		dialogos.mostrar_mensaje(padre, _("Escriba un número de página del 1 al {m}.").format(m=maximo), _("Ir a una página"))
