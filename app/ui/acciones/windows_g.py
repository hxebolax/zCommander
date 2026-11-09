# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque G: integración con Windows (secciones 8.10, 8.18 y 8.22 del diseño).

- Propiedades, «Abrir con» y el menú contextual del Explorador: los da el
  shell (``app/services/windows/menu_contextual.py``) en el hilo de la
  interfaz y solo sobre rutas del disco.
- Portapapeles: formato del Explorador (``CF_HDROP`` con «Preferred
  DropEffect»), para pegar aquí lo copiado en el Explorador y al revés.
  Pegar y soltar copian o mueven con el motor de operaciones del núcleo
  (``OperacionCopiar``), así tienen progreso, lista de conflictos y deshacer.
- Arrastrar y soltar: la lista ofrece sus archivos con ``wx.FileDataObject``
  y acepta los que llegan del Explorador o del otro panel.
- Iconos del sistema por extensión, pedidos en un hilo y guardados en caché
  (preferencia ``paneles.iconos``, desactivada de fábrica).
- Consola y Explorador en la carpeta del panel: envuelven
  ``linea_ordenes.abrir_consola`` y ``shell_basico.explorador``.

La ventana llama a ``instalar(ventana)`` al arrancar y a
``instalar_panel(panel)`` por cada panel que crea (también pestañas nuevas y
restauradas); los paneles iniciales se crean antes que ``instalar``.
"""

from __future__ import annotations

import builtins
import dataclasses
import logging
import os
import struct
from collections.abc import Callable, Sequence
from typing import Any

import wx

from app.services import formato
from app.services.vfs import base, resolver, rutas
from app.ui import anuncios

log = logging.getLogger(__name__)

FORMATO_EFECTO = "Preferred DropEffect"
DROPEFFECT_COPY = 1


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Utilidades ───────────────────────────────────────────────────────────────

def _rutas_locales(panel, entradas: Sequence[base.Entrada]) -> list[str] | None:
	"""Rutas del disco de las entradas, o ``None`` si alguna no está en el disco (comprimido, servidor)."""
	resultado = []
	for entrada in entradas:
		if entrada.es_superior:
			continue
		local = panel.proveedor.ruta_local(entrada.ruta)
		if not local:
			return None
		resultado.append(local)
	return resultado


def _carpeta_local(panel) -> str | None:
	"""Carpeta del disco del panel; en una lista de resultados, la del elemento del cursor."""
	carpeta = panel.ruta_local()
	if carpeta:
		return carpeta
	entrada = panel.cursor()
	if entrada is not None and not entrada.es_superior:
		local = panel.proveedor.ruta_local(entrada.ruta)
		if local:
			return os.path.dirname(local)
	return None


def _rutas_de_trabajo(panel) -> list[str] | None:
	"""Elementos de trabajo como rutas del disco; sin elementos, la carpeta del panel."""
	elementos = panel.elementos_trabajo()
	if elementos:
		return _rutas_locales(panel, elementos)
	carpeta = panel.ruta_local()
	return [carpeta] if carpeta else None


def _hwnd(ventana) -> int:
	try:
		return int(ventana.GetHandle())
	except (AttributeError, RuntimeError):
		return 0


def _mensaje(error: BaseException) -> str:
	return getattr(error, "mensaje", None) or str(error)


def _avisar_error(error: BaseException) -> None:
	anuncios.anunciar(_mensaje(error), anuncios.ESENCIAL)


def _vivo(objeto) -> bool:
	"""Un objeto wx sigue existiendo (tras ``Destroy`` su envoltorio de Python da falso)."""
	try:
		return bool(objeto)
	except RuntimeError:
		return False


def _posicion_menu(panel) -> tuple[int, int]:
	"""Punto de pantalla junto al elemento del cursor (el menú se abre con el teclado)."""
	lista = panel.lista()
	indice = lista.GetFocusedItem()
	if indice >= 0:
		lista.EnsureVisible(indice)
		rect = lista.GetItemRect(indice)
		alto = max(rect.height, 1)
		cliente = lista.GetClientRect()
		if cliente.Contains(wx.Point(rect.x + alto, rect.y + alto // 2)):
			punto = lista.ClientToScreen(wx.Point(rect.x + alto, rect.y + alto))
			return punto.x, punto.y
	punto = lista.ClientToScreen(wx.Point(0, 0))
	return punto.x, punto.y


def _no_disco(que: str) -> None:
	anuncios.anunciar(_("{q} solo está disponible para elementos del disco").format(q=que), anuncios.RESULTADO)


# ── Propiedades, Abrir con y menú de Windows (8.10) ─────────────────────────────

def propiedades(ctx) -> None:
	"""Alt+Intro: propiedades de Windows de los elementos de trabajo (o de la carpeta)."""
	panel = ctx.objetivo
	lista_rutas = _rutas_de_trabajo(panel)
	if not lista_rutas:
		_no_disco(_("Propiedades"))
		return
	from app.services.windows import menu_contextual

	try:
		menu_contextual.propiedades(lista_rutas, _hwnd(ctx.ventana))
	except base.ErrorArchivos as error:
		log.warning("Propiedades: %s", error.mensaje)
		_avisar_error(error)


def abrir_con(ctx) -> None:
	"""Diálogo «Abrir con» de Windows para el archivo del cursor."""
	panel = ctx.objetivo
	entrada = panel.cursor()
	elementos = panel.elementos_trabajo()
	if len(elementos) == 1:
		entrada = elementos[0]
	if entrada is None or entrada.es_superior or entrada.es_carpeta:
		anuncios.anunciar(_("Abrir con solo se puede usar con un archivo"), anuncios.RESULTADO)
		return
	local = panel.proveedor.ruta_local(entrada.ruta)
	if not local:
		_no_disco(_("Abrir con"))
		return
	from app.services.windows import menu_contextual

	try:
		menu_contextual.abrir_con(local, _hwnd(ctx.ventana))
	except (base.ErrorArchivos, OSError) as error:
		log.warning("Abrir con %s: %s", local, error)
		_avisar_error(error)


def menu_windows(ctx) -> None:
	"""Menú contextual del Explorador para los elementos de trabajo, junto al cursor.

	Sus verbos los hace el shell (no pasan por el motor ni por deshacer); al
	cerrarlo se refresca el panel. «Cambiar nombre» lo hace zCommander: el
	shell sin una ventana del Explorador no sabe renombrar en el sitio.
	"""
	panel = ctx.objetivo
	lista_rutas = _rutas_de_trabajo(panel)
	if not lista_rutas:
		_no_disco(_("El menú contextual de Windows"))
		return
	_cuando_se_suelten_las_teclas(lambda: _mostrar_menu_windows(ctx, panel, lista_rutas))


# Teclas que, si se sueltan con el menú ya abierto, lo cierran (Alt) o llegan a él (Aplicaciones).
_TECLAS_A_ESPERAR = (wx.WXK_ALT, wx.WXK_WINDOWS_MENU)
_ESPERA_MAXIMA_MS = 1500
_PASO_ESPERA_MS = 30


def _cuando_se_suelten_las_teclas(funcion: Callable[[], None], esperado_ms: int = 0) -> None:
	"""Llama a ``funcion`` cuando no están pulsadas Alt ni Aplicaciones (o pasado un máximo).

	Con Alt+Mayús+F10 la orden llega con Alt pulsada; si el menú del shell se
	abriera ya, soltar Alt lo cerraría en el acto y la persona no llegaría a oírlo.
	"""
	try:
		pulsada = any(wx.GetKeyState(tecla) for tecla in _TECLAS_A_ESPERAR)
	except (wx.wxAssertionError, RuntimeError):
		log.debug("No se pudo consultar el estado de las teclas", exc_info=True)
		pulsada = False
	if pulsada and esperado_ms < _ESPERA_MAXIMA_MS:
		wx.CallLater(_PASO_ESPERA_MS, _cuando_se_suelten_las_teclas, funcion, esperado_ms + _PASO_ESPERA_MS)
		return
	funcion()


def _mostrar_menu_windows(ctx, panel, lista_rutas: list[str]) -> None:
	if not _vivo(panel):
		return
	from app.services.windows import menu_contextual

	x, y = _posicion_menu(panel)
	orden_renombrar = "renombrar" if len(lista_rutas) == 1 else "renombrado_multiple"
	propios: dict[str, Callable[[], None]] = {
		"rename": lambda: wx.CallAfter(ctx.ejecutar_orden, orden_renombrar),
	}
	try:
		verbo = menu_contextual.mostrar_menu(lista_rutas, _hwnd(ctx.ventana), x, y, propios=propios)
	except base.ErrorArchivos as error:
		log.warning("Menú de Windows: %s", error.mensaje)
		_avisar_error(error)
		return
	if verbo is None:
		return
	n = len(lista_rutas)
	if verbo.casefold() == "copy":
		anuncios.anunciar(formato.plural(n, _("{n} elemento copiado al portapapeles"), _("{n} elementos copiados al portapapeles")),
			anuncios.RESULTADO, sonido="portapapeles.copiar")
	elif verbo.casefold() == "cut":
		anuncios.anunciar(formato.plural(n, _("{n} elemento cortado al portapapeles"), _("{n} elementos cortados al portapapeles")),
			anuncios.RESULTADO, sonido="portapapeles.cortar")
	if verbo.casefold() != "rename" and _vivo(panel):
		panel.refrescar()


# ── Portapapeles (8.18) ──────────────────────────────────────────────────────────

def portapapeles_copiar(ctx) -> None:
	_poner_en_portapapeles(ctx, mover=False)


def portapapeles_cortar(ctx) -> None:
	_poner_en_portapapeles(ctx, mover=True)


def _poner_en_portapapeles(ctx, mover: bool) -> None:
	panel = ctx.objetivo
	elementos = panel.elementos_trabajo()
	if not elementos:
		anuncios.anunciar(_("No hay elementos para cortar") if mover else _("No hay elementos para copiar"), anuncios.RESULTADO)
		return
	lista_rutas = _rutas_locales(panel, elementos)
	if not lista_rutas:
		_no_disco(_("El portapapeles de archivos"))
		return
	from app.services.windows import portapapeles

	try:
		portapapeles.poner_archivos(lista_rutas, mover=mover)
	except base.ErrorArchivos as error:
		_avisar_error(error)
		return
	n = len(lista_rutas)
	if mover:
		texto = formato.plural(n, _("{n} elemento cortado al portapapeles"), _("{n} elementos cortados al portapapeles"))
	else:
		texto = formato.plural(n, _("{n} elemento copiado al portapapeles"), _("{n} elementos copiados al portapapeles"))
	anuncios.anunciar(texto, anuncios.RESULTADO)


def portapapeles_pegar(ctx) -> None:
	"""Ctrl+V: pega en la carpeta del panel los archivos del portapapeles (copiar o mover según el efecto).

	Con ``general.pegar_ruta_del_portapapeles`` y una ruta de texto en el
	portapapeles (sin archivos), va a esa ruta.
	"""
	panel = ctx.objetivo
	from app.services.windows import portapapeles

	try:
		contenido = portapapeles.leer_archivos()
		texto = None
		if contenido is None and ctx.config.obtener("general.pegar_ruta_del_portapapeles"):
			texto = portapapeles.leer_texto()
	except base.ErrorArchivos as error:
		_avisar_error(error)
		return
	if contenido is None:
		ruta = _ruta_de_texto(texto)
		if ruta:
			_ir_a_ruta_de_texto(ctx.ventana, panel, ruta)
		else:
			anuncios.anunciar(_("El portapapeles no tiene archivos"), anuncios.RESULTADO)
		return

	def al_terminar(operacion) -> None:
		if contenido.mover and operacion.estado.value == "terminada":
			portapapeles.vaciar_si_no_cambio(contenido.secuencia)

	pegar_rutas(ctx.ventana, panel, list(contenido.rutas), contenido.mover, al_terminar if contenido.mover else None)


def _ruta_de_texto(texto: str | None) -> str | None:
	"""Ruta absoluta del disco si el texto es solo eso (una línea, entre comillas o no)."""
	if not texto:
		return None
	limpio = texto.strip().strip('"').strip()
	if not limpio or "\n" in limpio or "\r" in limpio or len(limpio) > 32000:
		return None
	if not (os.path.isabs(limpio) and (limpio[1:3] == ":\\" or limpio.startswith("\\\\"))):
		return None
	return limpio


def _ir_a_ruta_de_texto(ventana, panel, ruta: str) -> None:
	"""Comprueba en un hilo si la ruta es carpeta o archivo (puede ser de red) y va a ella."""

	def trabajo(_tarea, texto: str) -> tuple[str, str | None] | None:
		normal = rutas.normalizar(texto)
		if os.path.isdir(normal):
			return normal, None
		if os.path.isfile(normal):
			return os.path.dirname(normal), os.path.basename(normal)
		return None

	def listo(resultado) -> None:
		if not _vivo(panel):
			return
		if resultado is None:
			anuncios.anunciar(_("La ruta del portapapeles no existe: {r}").format(r=ruta), anuncios.RESULTADO)
			return
		carpeta, cursor = resultado
		panel.ir_a(carpeta, resolver.proveedor_local(), cursor=cursor)

	ventana.tareas.enviar(trabajo, ruta, al_terminar=listo, al_fallar=_avisar_error, nombre="pegar-ruta",
		tiempo_maximo=float(ventana.config.obtener("general.tiempo_unidad_s")))


def pegar_rutas(
	ventana,
	panel,
	lista_rutas: Sequence[str],
	mover: bool,
	al_terminar: Callable[[Any], None] | None = None,
) -> None:
	"""Copia o mueve rutas del disco a la carpeta de ``panel`` con el motor (pegar y soltar).

	Leer cada ruta (``info``) toca el disco o la red: va en un hilo. Copiar en
	la misma carpeta duplica cada elemento con «nombre (copia)», como el
	Explorador (el motor rechaza copiar algo sobre sí mismo).
	"""
	if not _vivo(panel):
		return
	if panel.es_lista():
		anuncios.anunciar(_("No se puede pegar en una lista de resultados"), anuncios.RESULTADO)
		return
	if not panel.proveedor.capacidades.escribir:
		anuncios.anunciar(_("Aquí no se puede pegar: este panel es de solo lectura"), anuncios.RESULTADO)
		return
	proveedor_destino, carpeta = panel.proveedor, panel.ruta
	destino_local = panel.ruta_local()

	def trabajo(_tarea, origenes: list[str]) -> tuple[list[base.Entrada], list[str]]:
		local = resolver.proveedor_local()
		entradas, faltan = [], []
		for ruta in origenes:
			try:
				entradas.append(local.info(ruta))
			except base.ErrorArchivos:
				log.info("Pegar: «%s» ya no existe o no se puede leer", ruta, exc_info=True)
				faltan.append(ruta)
		return entradas, faltan

	def listo(resultado) -> None:
		entradas, faltan = resultado
		if faltan:
			anuncios.anunciar(formato.plural(len(faltan), _("{n} elemento ya no existe y se omite"),
				_("{n} elementos ya no existen y se omiten")), anuncios.RESULTADO)
		if not entradas or not _vivo(panel):
			return
		_lanzar_pegado(ventana, entradas, proveedor_destino, carpeta, destino_local, mover, al_terminar)

	ventana.tareas.enviar(trabajo, list(lista_rutas), al_terminar=listo, al_fallar=_avisar_error, nombre="pegar",
		tiempo_maximo=float(ventana.config.obtener("general.tiempo_unidad_s")))


def _lanzar_pegado(ventana, entradas, proveedor_destino, carpeta, destino_local, mover, al_terminar) -> None:
	from app.services.operaciones import nombres
	from app.services.operaciones.copiar import OperacionCopiar
	from app.ui.acciones.archivos import opciones_por_defecto

	local = resolver.proveedor_local()
	opciones = opciones_por_defecto(ventana.config)
	aqui: list[base.Entrada] = []
	fuera: list[base.Entrada] = []
	for entrada in entradas:
		padre = os.path.dirname(rutas.normalizar(entrada.ruta)).casefold()
		if destino_local and padre == rutas.normalizar(destino_local).casefold():
			aqui.append(entrada)
		else:
			fuera.append(entrada)
	if aqui and mover:
		anuncios.anunciar(formato.plural(len(aqui), _("{n} elemento ya está en esta carpeta"), _("{n} elementos ya están en esta carpeta")),
			anuncios.RESULTADO)
		aqui = []
	if fuera:
		operacion = OperacionCopiar(local, fuera, proveedor_destino, carpeta, opciones, mover=mover)
		# 2.0 (10.1): la llamada directa dice en qué orden se lanzó (la lee lanzar_operacion).
		operacion.orden_origen = "portapapeles_pegar"
		ventana.lanzar_operacion(operacion, False, al_terminar)
	for entrada in aqui:
		# Duplicar en la misma carpeta, con el nombre que daría «Duplicar».
		nuevo = nombres.nombre_copia(entrada.nombre, lambda n: os.path.lexists(os.path.join(destino_local, n)))
		operacion = OperacionCopiar(local, [entrada], proveedor_destino, carpeta, dataclasses.replace(opciones), nombre_nuevo=nuevo)
		operacion.orden_origen = "portapapeles_pegar"
		ventana.lanzar_operacion(operacion, False, None)


# ── Consola y Explorador (8.22) ──────────────────────────────────────────────────

def consola(ctx) -> None:
	"""F11: consola configurada (cmd, PowerShell o Windows Terminal) en la carpeta del panel."""
	panel = ctx.objetivo
	carpeta = _carpeta_local(panel)
	if not carpeta:
		anuncios.anunciar(_("La consola solo se puede abrir en una carpeta del disco"), anuncios.RESULTADO)
		return
	from app.services import linea_ordenes

	programa = str(ctx.config.obtener("general.consola"))
	try:
		linea_ordenes.abrir_consola(carpeta, programa)
	except OSError as error:
		log.warning("No se pudo abrir la consola %s en %s", programa, carpeta, exc_info=True)
		anuncios.anunciar(_("No se pudo abrir la consola: {e}").format(e=error.strerror or error), anuncios.ESENCIAL)


def explorador(ctx) -> None:
	"""Mayús+F3: la carpeta del panel en el Explorador, con el elemento del cursor seleccionado."""
	panel = ctx.objetivo
	carpeta = _carpeta_local(panel)
	if not carpeta:
		_no_disco(_("Abrir en el Explorador"))
		return
	entrada = panel.cursor()
	seleccionar = None
	if entrada is not None and not entrada.es_superior:
		seleccionar = panel.proveedor.ruta_local(entrada.ruta)
	from app.services.windows import shell_basico

	try:
		shell_basico.explorador(carpeta, seleccionar)
	except OSError as error:
		log.warning("No se pudo abrir el Explorador en %s", carpeta, exc_info=True)
		anuncios.anunciar(_("No se pudo abrir el Explorador: {e}").format(e=error.strerror or error), anuncios.ESENCIAL)


# ── Arrastrar y soltar (8.18) ────────────────────────────────────────────────────

class DestinoSoltar(wx.DropTarget):
	"""Acepta archivos soltados en la lista de un panel (del Explorador o del otro panel).

	Sin teclas copia; con Mayús mueve (wx deduce la acción de las teclas). El
	trabajo lo hace el motor: al origen siempre se le contesta «copiado», para
	que el Explorador no borre nada por su cuenta mientras el motor mueve.
	"""

	def __init__(self, panel) -> None:
		super().__init__()
		self._panel = panel
		self._datos = wx.FileDataObject()
		self.SetDataObject(self._datos)
		self.SetDefaultAction(wx.DragCopy)

	def _admite(self) -> bool:
		panel = self._panel
		return _vivo(panel) and not panel.es_lista() and bool(panel.proveedor.capacidades.escribir)

	def OnEnter(self, x, y, accion):  # noqa: N802 - API de wx
		return accion if self._admite() else wx.DragNone

	def OnDragOver(self, x, y, accion):  # noqa: N802 - API de wx
		return accion if self._admite() else wx.DragNone

	def OnData(self, x, y, accion):  # noqa: N802 - API de wx
		if not self._admite() or not self.GetData():
			return wx.DragNone
		lista_rutas = [r for r in self._datos.GetFilenames() if r]
		if not lista_rutas:
			return wx.DragNone
		mover = accion == wx.DragMove
		log.info("Soltados %d elementos en %s (%s)", len(lista_rutas), self._panel.mostrar_ruta(), "mover" if mover else "copiar")
		# Fuera del bucle de arrastre: el origen (el Explorador) queda libre enseguida.
		wx.CallAfter(soltar_en, self._panel, lista_rutas, mover)
		return wx.DragCopy if accion in (wx.DragCopy, wx.DragMove) else accion


def soltar_en(panel, lista_rutas: Sequence[str], mover: bool) -> None:
	"""Copia o mueve lo soltado a la carpeta del panel, con el motor y su lista de conflictos."""
	if not _vivo(panel):
		return
	pegar_rutas(panel.ventana, panel, lista_rutas, mover)


def arrastrar(panel, entradas: Sequence[base.Entrada]) -> int:
	"""Empieza a arrastrar las entradas hacia el Explorador o el otro panel.

	Además de ``CF_HDROP`` se ofrece «Preferred DropEffect» = copiar: así el
	Explorador copia también dentro del mismo disco (donde por defecto
	movería), como pide el diseño; con Mayús mueve.

	:return: el resultado de ``DoDragDrop``.
	"""
	lista_rutas = _rutas_locales(panel, entradas)
	if not lista_rutas:
		_no_disco(_("Arrastrar"))
		return wx.DragNone
	archivos = wx.FileDataObject()
	for ruta in lista_rutas:
		archivos.AddFile(ruta)
	datos = wx.DataObjectComposite()
	datos.Add(archivos, True)
	efecto = wx.CustomDataObject(wx.DataFormat(FORMATO_EFECTO))
	efecto.SetData(struct.pack("<I", DROPEFFECT_COPY))
	datos.Add(efecto)
	fuente = wx.DropSource(panel.lista())
	fuente.SetData(datos)
	resultado = fuente.DoDragDrop(wx.Drag_AllowMove)
	log.info("Arrastre de %d elementos terminado: %s", len(lista_rutas), resultado)
	if resultado == wx.DragMove and _vivo(panel):
		panel.refrescar()
	return resultado


# ── Iconos del sistema (4.3) ─────────────────────────────────────────────────────

@dataclasses.dataclass
class _IconosLista:
	lista: Any
	imagenes: wx.ImageList
	indices: dict[str, int] = dataclasses.field(default_factory=dict)


class GestorIconos:
	"""Iconos pequeños por extensión para las listas de una ventana.

	Cada lista tiene su ``wx.ImageList`` (la lista se queda con ella al
	asignarla y la destruye con ella); los iconos convertidos se comparten.
	Mientras llega el icono de una extensión, la fila se pinta sin icono y se
	repinta al llegar.
	"""

	def __init__(self, ventana) -> None:
		self.ventana = ventana
		ancho = wx.SystemSettings.GetMetric(wx.SYS_SMALLICON_X)
		alto = wx.SystemSettings.GetMetric(wx.SYS_SMALLICON_Y)
		self.tamano = (ancho if ancho > 0 else 16, alto if alto > 0 else 16)
		self.iconos: dict[str, wx.Icon | None] = {}
		self._pedidos: set[str] = set()
		self._listas: list[_IconosLista] = []

	@staticmethod
	def clave(entrada: base.Entrada) -> str:
		from app.services.windows import iconos

		if entrada.es_carpeta or entrada.es_superior:
			return iconos.CARPETA
		return entrada.extension

	def activo_en(self, lista) -> bool:
		return any(estado.lista is lista for estado in self._listas)

	def activar(self, lista) -> None:
		self._limpiar()
		if self.activo_en(lista):
			return
		imagenes = wx.ImageList(self.tamano[0], self.tamano[1], True)
		estado = _IconosLista(lista, imagenes)
		self._listas.append(estado)
		lista.fijar_iconos(lambda entrada: self.indice(estado, entrada), imagenes)

	def desactivar(self, lista) -> None:
		self._listas = [e for e in self._listas if e.lista is not lista and _vivo(e.lista)]
		if not _vivo(lista):
			return
		# Sin lista de imágenes, la columna Nombre deja de reservar el hueco del icono.
		lista.quitar_iconos()

	def _limpiar(self) -> None:
		self._listas = [e for e in self._listas if _vivo(e.lista)]

	def indice(self, estado: _IconosLista, entrada: base.Entrada) -> int | None:
		clave = self.clave(entrada)
		indice = estado.indices.get(clave)
		if indice is not None:
			return indice
		if clave not in self.iconos:
			self._pedir(clave)
			return None
		icono = self.iconos[clave]
		if icono is None:
			return None
		indice = estado.imagenes.Add(icono)
		if indice < 0:
			self.iconos[clave] = None
			return None
		estado.indices[clave] = indice
		return indice

	def _pedir(self, clave: str) -> None:
		if clave in self._pedidos:
			return
		self._pedidos.add(clave)
		from app.services.windows import iconos

		def trabajo(_tarea, nombre: str) -> int:
			return iconos.icono_pequeno(nombre)

		def fallo(error: BaseException) -> None:
			log.debug("No llegó el icono de %r: %s", clave, error)
			self.iconos[clave] = None

		self.ventana.tareas.enviar(trabajo, clave, al_terminar=lambda hicon: self._recibir(clave, hicon), al_fallar=fallo,
			clave_unica=f"icono:{clave}", nombre="icono")

	def _recibir(self, clave: str, hicon: int) -> None:
		icono = None
		if hicon:
			icono = wx.Icon()
			# El wx.Icon se queda con el HICON y lo libera al destruirse.
			if not icono.CreateFromHICON(hicon):
				from app.services.windows import iconos

				iconos.destruir_icono(hicon)
				icono = None
		self.iconos[clave] = icono
		self._limpiar()
		for estado in self._listas:
			estado.lista.Refresh()


def _gestor_iconos(ventana) -> GestorIconos:
	gestor = getattr(ventana, "_iconos_windows_g", None)
	if gestor is None:
		gestor = GestorIconos(ventana)
		ventana._iconos_windows_g = gestor
	return gestor


def _aplicar_iconos(ventana) -> None:
	"""Pone o quita los iconos en todos los paneles según ``paneles.iconos`` (al momento, sin reiniciar)."""
	if not _vivo(ventana):
		return
	gestor = _gestor_iconos(ventana)
	activar = bool(ventana.config.obtener("paneles.iconos"))
	for panel in ventana.todos_los_paneles():
		lista = panel.lista()
		if activar:
			gestor.activar(lista)
		elif gestor.activo_en(lista):
			gestor.desactivar(lista)


# ── Enganches con la ventana ─────────────────────────────────────────────────────

def instalar(ventana) -> None:
	"""Al arrancar: aplica la preferencia de iconos y la sigue para aplicar sus cambios al momento."""
	_aplicar_iconos(ventana)

	def al_cambiar(_clave: str, _anterior, _nuevo) -> None:
		# El aviso llega en el hilo que cambió la preferencia.
		wx.CallAfter(_aplicar_iconos, ventana)

	cancelar = ventana.config.suscribir(al_cambiar, prefijo="paneles.iconos")

	def al_destruir(evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is ventana:
			cancelar()
		evento.Skip()

	ventana.Bind(wx.EVT_WINDOW_DESTROY, al_destruir)


def instalar_panel(panel) -> None:
	"""Por cada panel: arrastrar desde la lista, soltar en ella e iconos si están activados."""
	lista = panel.lista()
	lista.al_empezar_arrastre(lambda entradas: arrastrar(panel, entradas))
	lista.fijar_destino_soltar(DestinoSoltar(panel))
	ventana = getattr(panel, "ventana", None)
	if ventana is not None and ventana.config.obtener("paneles.iconos"):
		_gestor_iconos(ventana).activar(lista)
