# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Vistas del lado pasivo: Información y Vista rápida (sección 4.4 del diseño).

Las dos son un ``wx.TextCtrl`` multilínea de SOLO LECTURA precedido de su
etiqueta: el lector de pantalla lo recorre por líneas, palabras y caracteres,
se puede seleccionar y copiar, y la etiqueta (creada justo antes y con el
mismo padre) le da el nombre accesible.

Decisiones comunes:

- **Todo en un hilo** (``GestorTareas``): consultar una unidad de red, leer
  la versión de un ejecutable o los primeros kilobytes de un archivo puede
  tardar segundos; si el hilo de la interfaz se bloquea, el lector se queda
  mudo.
- **Número de petición**: el cursor del otro panel se mueve deprisa. Cada
  ``mostrar`` cancela la tarea anterior y solo pinta la respuesta cuyo número
  coincide con la última petición; así nunca aparece el archivo de antes.
- **Sin robar el foco**: el texto se cambia con ``ChangeValue`` (no lanza
  eventos de texto) y nunca se llama a ``SetFocus``. Quien está en la lista
  del otro panel sigue allí y el lector no dice nada nuevo.
- Ctrl+H: la ayuda va en el ``TextCtrl`` (el control que recibe el foco) y en
  el panel.
"""

from __future__ import annotations

import builtins
import logging
import ntpath
import threading
from collections.abc import Callable
from typing import Any

import wx

from app.core.tareas import GestorTareas, Tarea, TareaCancelada
from app.services import codificacion, errores, formato
from app.services.vfs.base import Entrada, Proveedor

log = logging.getLogger(__name__)

#: Extensiones de las que se lee la versión del ejecutable.
EXTENSIONES_CON_VERSION = frozenset({"exe", "dll", "sys", "ocx", "cpl", "drv", "scr", "msi", "mui"})
#: Esquemas de proveedor que van por red: la vista rápida no los lee sola.
ESQUEMAS_DE_RED = frozenset({"ftp", "ftps", "sftp"})
#: Bloque de lectura de la vista rápida (entre bloques se comprueba la cancelación).
_BLOQUE = 64 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Funciones sin wx (se ejecutan en el hilo de trabajo)
# ════════════════════════════════════════════════════════════════════════════

def descripcion_tipo(entrada: Entrada) -> str:
	"""Tipo del elemento para la persona («Carpeta», «Documento de texto», «Archivo XYZ»).

	Si existe ``app/services/windows/iconos.py`` (bloque G) se usa su
	descripción de Windows; se importa en diferido porque aún puede no
	existir y porque toca el shell (lento la primera vez).
	"""
	if entrada.es_superior:
		return _("Carpeta superior")
	if entrada.es_carpeta:
		return _("Enlace a carpeta") if entrada.es_enlace else _("Carpeta")
	descripcion = _descripcion_de_windows(entrada)
	if descripcion:
		return descripcion
	extension = entrada.extension
	if extension:
		return _("Archivo {ext}").format(ext=extension.upper())
	return _("Archivo")


def _descripcion_de_windows(entrada: Entrada) -> str:
	"""Descripción del bloque G si está disponible; cadena vacía si no."""
	try:
		from app.services.windows import iconos  # type: ignore[attr-defined]
	except ImportError:
		return ""
	for nombre in ("descripcion_tipo", "tipo_de_archivo", "descripcion"):
		funcion = getattr(iconos, nombre, None)
		if callable(funcion):
			try:
				return str(funcion(entrada.nombre) or "")
			except Exception:  # noqa: BLE001 - la descripción es opcional: se usa la de la extensión
				log.debug("Falló iconos.%s con %s", nombre, entrada.nombre, exc_info=True)
				return ""
	return ""


def version_ejecutable(ruta: str) -> str:
	"""«10.0.26100.1 (Explorador de Windows)» o cadena vacía si no tiene versión.

	``GetFileVersionInfo`` lanza su propio error de pywin32 con archivos sin
	recurso de versión (lo normal en muchos .dll): no es un fallo, se registra
	en depuración y se sigue.
	"""
	try:
		import win32api
	except ImportError:
		log.debug("Sin pywin32: no se lee la versión de %s", ruta, exc_info=True)
		return ""
	try:
		fijo = win32api.GetFileVersionInfo(ruta, "\\")
		alta, baja = fijo["FileVersionMS"], fijo["FileVersionLS"]
		version = f"{alta >> 16}.{alta & 0xFFFF}.{baja >> 16}.{baja & 0xFFFF}"
	except Exception:  # noqa: BLE001 - archivo sin recurso de versión o ilegible
		log.debug("Sin versión en %s", ruta, exc_info=True)
		return ""
	try:
		traducciones = win32api.GetFileVersionInfo(ruta, "\\VarFileInfo\\Translation")
		if traducciones:
			idioma, pagina = traducciones[0]
			descripcion = win32api.GetFileVersionInfo(ruta, f"\\StringFileInfo\\{idioma:04X}{pagina:04X}\\FileDescription")
			if descripcion:
				return f"{version} ({str(descripcion).strip()})"
	except Exception:  # noqa: BLE001 - la descripción es un extra; basta con el número
		log.debug("Sin descripción de versión en %s", ruta, exc_info=True)
	return version


def _numero_serie(numero: int) -> str:
	"""«1A2B-3C4D», como lo muestra ``vol`` en la consola."""
	return f"{(numero >> 16) & 0xFFFF:04X}-{numero & 0xFFFF:04X}"


def _lineas_unidad(proveedor: Proveedor, ruta: str) -> list[str]:
	"""Datos de la unidad que contiene ``ruta``.

	En disco local se pregunta a Windows con tiempo límite (una unidad de red
	caída no debe colgar el hilo); en otros proveedores, solo el espacio libre
	si el proveedor lo sabe.
	"""
	if not ruta:
		return []
	from app.services.windows import unidades

	lineas: list[str] = []
	local = proveedor.ruta_local(ruta)
	if local:
		letra = ntpath.splitdrive(local)[0]
		if not letra:
			return []
		unidad = unidades.info_unidad_con_limite(letra)
		lineas.append(_("Unidad: {u}").format(u=unidad.letra))
		lineas.append(_("Tipo de unidad: {t}").format(t=unidades.nombre_tipo(unidad.tipo)))
		if unidad.destino_red:
			lineas.append(_("Conectada a: {d}").format(d=unidad.destino_red))
		if not unidad.preparada:
			lineas.append(_("La unidad no está preparada o no responde."))
			return lineas
		if unidad.total >= 0:
			lineas.append(_("Libre: {t} ({b} bytes)").format(t=formato.tamano_legible(unidad.libre), b=formato.miles(unidad.libre)))
			lineas.append(_("Total: {t} ({b} bytes)").format(t=formato.tamano_legible(unidad.total), b=formato.miles(unidad.total)))
		lineas.append(_("Sistema de archivos: {s}").format(s=unidad.sistema_archivos or _("desconocido")))
		lineas.append(_("Etiqueta: {e}").format(e=unidad.etiqueta or _("sin etiqueta")))
		lineas.append(_("Número de serie: {n}").format(n=_numero_serie(unidad.numero_serie)))
		return lineas
	try:
		espacio = proveedor.espacio_libre(ruta)
	except Exception:  # noqa: BLE001 - el espacio es informativo; un servidor puede no admitirlo
		log.debug("Sin espacio libre de %s", ruta, exc_info=True)
		espacio = None
	lineas.append(_("Origen: {o}").format(o=proveedor.descripcion()))
	if espacio is not None:
		libre, total = espacio
		lineas.append(_("Libre: {t}").format(t=formato.tamano_legible(libre)))
		lineas.append(_("Total: {t}").format(t=formato.tamano_legible(total)))
	return lineas


#: El resumen de una conexión se reutiliza este tiempo: leerlo pregunta a WMI (segundos) y la vista
#: Información lo pide a cada movimiento del cursor.
VIGENCIA_RESUMEN_RED_S = 15.0
_resumenes_red: dict[str, tuple[float, str]] = {}
_candado_resumenes = threading.Lock()


def ruta_para_resumen_red(proveedor: Proveedor | None, entrada: Entrada | None, panel_ruta: str = "") -> str:
	"""Ruta de disco de la que dar el resumen de red (la del elemento o la de la carpeta). Sin E/S.

	En «Red» solo las filas de unidades y recursos tienen ruta de disco; los servidores y las filas
	virtuales no.
	"""
	if proveedor is None:
		return ""
	candidatas = [entrada.ruta] if entrada is not None and not entrada.es_superior else []
	if panel_ruta:
		candidatas.append(panel_ruta)
	for candidata in candidatas:
		try:
			local = proveedor.ruta_local(candidata)
		except Exception:  # noqa: BLE001 - un proveedor raro no rompe la consulta
			log.debug("Sin ruta local de %s", candidata, exc_info=True)
			local = None
		if local:
			return local
	return ""


def _raiz_de_red(ruta: str) -> str:
	"""«Z:» o «\\\\srv\\rec» de una ruta; «» si es un servidor solo o no es de disco."""
	ruta = (ruta or "").strip()
	if ruta.startswith("\\\\"):
		partes = [p for p in ruta[2:].split("\\") if p]
		return f"\\\\{partes[0]}\\{partes[1]}" if len(partes) >= 2 and partes[0] not in ("?", ".") else ""
	letra = ntpath.splitdrive(ruta)[0]
	return letra.upper() if len(letra) == 2 else ""


def resumen_red(ruta: str) -> str:
	"""2.0 (9.6): «Z:, \\\\DS220\\home, conectada, SMB 3.1.1 cifrada, ...» si ``ruta`` es de red; si no, «». Bloquea.

	Los discos fijos, extraíbles, ópticos y de RAM se descartan sin preguntar a la red.
	"""
	raiz = _raiz_de_red(ruta)
	if not raiz:
		return ""
	from app.services.windows import red, red_info

	if not raiz.startswith("\\\\"):
		from app.services.windows import unidades

		try:
			if unidades.tipo_de(raiz + "\\") in ("fija", "extraible", "optica", "ram"):
				return ""
		except (AttributeError, OSError):
			log.debug("No se pudo saber el tipo de %s", raiz, exc_info=True)
	if not red.es_ruta_de_red(raiz):
		return ""
	import time

	clave = raiz.upper()
	with _candado_resumenes:
		guardado = _resumenes_red.get(clave)
	if guardado is not None and time.monotonic() - guardado[0] < VIGENCIA_RESUMEN_RED_S:
		return guardado[1]
	try:
		texto = red_info.informacion(raiz).resumen()
	except Exception:  # noqa: BLE001 - el resumen es un extra: sin él la consulta sigue
		log.info("No se pudo leer la información de la conexión de %s", raiz, exc_info=True)
		return ""
	with _candado_resumenes:
		_resumenes_red[clave] = (time.monotonic(), texto)
	return texto


def olvidar_resumenes_red() -> None:
	"""Para las pruebas (y tras conectar o desconectar): sin resúmenes guardados."""
	with _candado_resumenes:
		_resumenes_red.clear()


def _lineas_complementos(entrada: Entrada, proveedor: Proveedor) -> list[str]:
	"""``app.plugins.registro.lineas_info`` sin que un complemento roto rompa la vista."""
	try:
		from app.plugins import registro

		return registro.lineas_info(entrada, proveedor)
	except Exception:  # noqa: BLE001 - las líneas de complementos son un extra
		log.warning("Fallaron las líneas de información de los complementos", exc_info=True)
		return []


def componer_informacion(tarea: Tarea | None, proveedor: Proveedor | None, entrada: Entrada | None, panel_ruta: str) -> str:
	"""Texto de la vista Información: una línea «Dato: valor» por dato.

	Una línea por dato porque el lector lee la vista con las flechas: Abajo
	pasa de «Tamaño» a «Modificado» sin tener que buscar dentro de un párrafo.
	Si el archivo solo está en la nube no se abre (leer la versión lo
	descargaría).
	"""

	def comprobar() -> None:
		if tarea is not None:
			tarea.comprobar()

	lineas: list[str] = []
	if entrada is None or proveedor is None:
		lineas.append(_("Sin elemento"))
	else:
		lineas.append(_("Nombre: {n}").format(n=entrada.nombre))
		lineas.append(_("Tipo: {t}").format(t=descripcion_tipo(entrada)))
		comprobar()
		if not entrada.es_superior:
			carpeta = proveedor.padre(entrada.ruta)
			if carpeta:
				lineas.append(_("Carpeta: {c}").format(c=proveedor.mostrar(carpeta)))
		if entrada.tamano >= 0:
			lineas.append(_("Tamaño: {t} ({b} bytes)").format(t=formato.tamano_legible(entrada.tamano), b=formato.miles(entrada.tamano)))
		if entrada.modificado:
			lineas.append(_("Modificado: {f}").format(f=formato.fecha(entrada.modificado, "larga")))
		if entrada.creado:
			lineas.append(_("Creado: {f}").format(f=formato.fecha(entrada.creado, "larga")))
		if not entrada.es_superior:
			lineas.append(_("Atributos: {a}").format(a=formato.atributos_largos(entrada.atributos) or _("ninguno")))
		if entrada.en_nube:
			lineas.append(_("Disponibilidad: solo en la nube, no descargado"))
		if entrada.es_enlace:
			lineas.append(_("Destino del enlace: {d}").format(d=entrada.destino_enlace or _("desconocido")))
		if entrada.permisos >= 0:
			lineas.append(_("Permisos: {p:o}").format(p=entrada.permisos))
		if not entrada.es_carpeta and not entrada.en_nube and entrada.extension in EXTENSIONES_CON_VERSION:
			local = proveedor.ruta_local(entrada.ruta)
			if local:
				comprobar()
				version = version_ejecutable(local)
				if version:
					lineas.append(_("Versión: {v}").format(v=version))
		if not entrada.es_superior:
			# 2.0 (3.5): líneas de los complementos cuyo [[info]] coincide (en este hilo de trabajo).
			comprobar()
			lineas.extend(_lineas_complementos(entrada, proveedor))
	comprobar()
	ruta_unidad = panel_ruta or (entrada.ruta if entrada is not None else "")
	if proveedor is not None and ruta_unidad:
		datos_unidad = _lineas_unidad(proveedor, ruta_unidad)
		if datos_unidad:
			lineas.append("")
			lineas.extend(datos_unidad)
	comprobar()
	resumen = resumen_red(ruta_para_resumen_red(proveedor, entrada, panel_ruta))
	if resumen:
		lineas.append(_("Conexión de red: {r}").format(r=resumen))
	return "\n".join(lineas)


def es_ruta_lenta(proveedor: Proveedor, ruta: str) -> bool:
	"""``True`` si leer ``ruta`` va por red: UNC, unidad de red o servidor FTP/SFTP.

	Se llama en el hilo de trabajo: ``GetDriveTypeW`` suele ser inmediato,
	pero con una unidad de red caída puede tardar.
	"""
	if proveedor.esquema in ESQUEMAS_DE_RED:
		return True
	local = proveedor.ruta_local(ruta)
	if not local:
		# Un comprimido se lee del archivo que lo contiene: es lento si este lo es.
		if proveedor.contenedor is not None:
			contenedor, ruta_contenedor = proveedor.contenedor
			return es_ruta_lenta(contenedor, ruta_contenedor)
		return False
	if local.startswith("\\\\"):
		return True
	from app.services.windows import unidades

	letra = ntpath.splitdrive(local)[0]
	if not letra:
		return False
	try:
		return unidades.tipo_de(letra + "\\") == "red"
	except (AttributeError, OSError):
		log.debug("No se pudo saber el tipo de la unidad de %s", local, exc_info=True)
		return False


def leer_contenido(tarea: Tarea | None, proveedor: Proveedor, ruta: str, limite_kb: int) -> tuple[bytes, bool]:
	"""Hasta ``limite_kb`` kilobytes de ``ruta`` y si quedó contenido sin leer.

	Lee por bloques para atender la cancelación entre uno y otro (un cambio
	rápido de cursor no espera a que acabe un archivo grande).
	"""
	limite = max(1, int(limite_kb)) * 1024
	trozos: list[bytes] = []
	leidos = 0
	with proveedor.abrir_lectura(ruta) as flujo:
		while leidos < limite:
			if tarea is not None:
				tarea.comprobar()
			bloque = flujo.read(min(_BLOQUE, limite - leidos))
			if not bloque:
				return b"".join(trozos), False
			trozos.append(bloque)
			leidos += len(bloque)
		quedan = bool(flujo.read(1))
	return b"".join(trozos), quedan


def texto_de_contenido(datos: bytes) -> tuple[str, str]:
	"""(texto para mostrar, codificación o «hexadecimal»).

	Los finales de línea se unifican a «\\n» (el control de Windows los
	convierte a CRLF) y los ceros se cambian por espacios: un cero corta el
	texto en un control de edición de Windows.
	"""
	if codificacion.es_binario(datos):
		return codificacion.hexadecimal(datos), "hexadecimal"
	texto, usada = codificacion.decodificar(datos)
	texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
	return texto, usada


# ════════════════════════════════════════════════════════════════════════════
# Base común
# ════════════════════════════════════════════════════════════════════════════

class _VistaTexto(wx.Panel):
	"""Etiqueta + ``TextCtrl`` de solo lectura, con peticiones en un hilo y descarte de las antiguas."""

	def __init__(self, padre: wx.Window, etiqueta: str, ayuda: str, tareas: GestorTareas, nombre: str) -> None:
		super().__init__(padre, name=nombre)
		self._tareas = tareas
		self._peticion = 0
		self._tarea: Tarea | None = None
		# La etiqueta se crea ANTES que el texto y con el mismo padre: de ella
		# toma el lector el nombre del control.
		self.etiqueta = wx.StaticText(self, label=etiqueta)
		self.texto = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL, name=nombre)
		self.texto.SetHelpText(ayuda)
		self.SetHelpText(ayuda)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(4))
		sizer.Add(self.texto, 1, wx.EXPAND | wx.ALL, self.FromDIP(4))
		self.SetSizer(sizer)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)

	def control_enfocable(self) -> wx.TextCtrl:
		"""El control al que la ventana lleva el foco con Tab."""
		return self.texto

	def valor(self) -> str:
		"""Texto mostrado (para pruebas y para copiar)."""
		return self.texto.GetValue()

	def cancelar(self) -> None:
		"""Cancela la lectura en curso y descarta cualquier respuesta pendiente."""
		self._peticion += 1
		self._cancelar_tarea()

	def _cancelar_tarea(self) -> None:
		if self._tarea is not None and not self._tarea.terminada:
			self._tarea.cancelar()
		self._tarea = None

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self:
			self.cancelar()
		evento.Skip()

	def _fijar_texto(self, texto: str) -> None:
		"""Cambia el texto sin eventos y sin mover el foco; el cursor vuelve al principio."""
		if not self or not self.texto:
			return
		self.texto.ChangeValue(texto)
		self.texto.SetInsertionPoint(0)
		self.texto.ShowPosition(0)

	def _nueva_peticion(self) -> int:
		self._peticion += 1
		self._cancelar_tarea()
		return self._peticion

	def _enviar(self, funcion: Callable[..., Any], *args: Any, al_terminar: Callable[[Any], None], nombre: str) -> None:
		"""Envía ``funcion`` al gestor y solo entrega la respuesta si sigue siendo la última petición."""
		numero = self._nueva_peticion()

		def terminar(resultado: Any) -> None:
			if self and numero == self._peticion:
				self._tarea = None
				al_terminar(resultado)

		def fallar(error: BaseException) -> None:
			if not self or numero != self._peticion:
				return
			self._tarea = None
			if isinstance(error, TareaCancelada):
				return
			self._fijar_texto(_("No se pudo leer: {m}").format(m=errores.mensaje_para_usuario(error)))

		self._tarea = self._tareas.enviar(funcion, *args, al_terminar=terminar, al_fallar=fallar, nombre=nombre)


# ════════════════════════════════════════════════════════════════════════════
# Información
# ════════════════════════════════════════════════════════════════════════════

class VistaInformacion(_VistaTexto):
	"""Datos del elemento del cursor del otro panel y de su unidad.

	:param padre: ventana que la contiene.
	:param tareas: gestor de tareas de la aplicación (las consultas van en sus hilos).
	:param etiqueta: texto de la etiqueta. Por defecto «In&formación:»: la F no
		choca con los menús de la barra (Izquierdo, Archivos, Comandos, Opciones,
		Derecho, Ayuda usan I, A, C, O, D y U).
	"""

	def __init__(self, padre: wx.Window, tareas: GestorTareas, etiqueta: str | None = None) -> None:
		super().__init__(
			padre,
			etiqueta or _("In&formación:"),
			_("Información del elemento del cursor del otro panel: nombre, tipo, tamaño, fechas, atributos, "
				"destino del enlace, versión del ejecutable y datos de su unidad. Se actualiza al mover el cursor "
				"en el otro panel. Tab vuelve al otro panel."),
			tareas,
			_("Información"),
		)

	def mostrar(self, proveedor: Proveedor | None, entrada: Entrada | None, panel_ruta: str = "") -> None:
		"""Pide los datos de ``entrada`` en un hilo; la última petición es la que se ve.

		:param panel_ruta: carpeta del otro panel (para la unidad cuando no hay elemento).
		"""
		self._enviar(
			componer_informacion, proveedor, entrada, panel_ruta,
			al_terminar=self._fijar_texto, nombre="vista_informacion",
		)


# ════════════════════════════════════════════════════════════════════════════
# Vista rápida
# ════════════════════════════════════════════════════════════════════════════

class VistaRapida(_VistaTexto):
	"""Contenido del archivo del cursor del otro panel, como texto o en hexadecimal.

	No lee carpetas, archivos que solo están en la nube ni rutas de red sin que
	la persona lo pida: leer un archivo de OneDrive lo descarga entero y una
	ruta de red lenta tendría un hilo ocupado a cada movimiento del cursor. En
	esos casos muestra «Pulse Intro para leer el archivo» e Intro en el texto
	lo lee (``leer_pendiente``).

	:param monoespaciada: letra de ancho fijo (las columnas del volcado
		hexadecimal quedan alineadas).
	:param etiqueta: por defecto «Vista &rápida:» (la R no choca con los menús).
	"""

	def __init__(self, padre: wx.Window, tareas: GestorTareas, monoespaciada: bool = True, etiqueta: str | None = None) -> None:
		super().__init__(
			padre,
			etiqueta or _("Vista &rápida:"),
			_("Contenido del archivo del cursor del otro panel: texto con la codificación detectada o volcado "
				"hexadecimal si es binario, hasta el límite de kilobytes de las preferencias. Los archivos que solo "
				"están en la nube y los de la red no se leen solos: pulse Intro para leerlos. Tab vuelve al otro panel."),
			tareas,
			_("Vista rápida"),
		)
		self._fuente_normal = self.texto.GetFont()
		self._pendiente: tuple[Proveedor, Entrada, int] | None = None
		#: Codificación de lo mostrado («utf-8», «hexadecimal»...) o vacía.
		self.codificacion = ""
		self.fijar_monoespaciada(monoespaciada)
		self.texto.Bind(wx.EVT_KEY_DOWN, self._al_tecla)

	def fijar_monoespaciada(self, activa: bool) -> None:
		"""Letra de ancho fijo o la normal del sistema (preferencia de baja visión)."""
		if activa:
			fuente = wx.Font(wx.FontInfo(self._fuente_normal.GetPointSize()).Family(wx.FONTFAMILY_TELETYPE))
			self.texto.SetFont(fuente)
		else:
			self.texto.SetFont(self._fuente_normal)

	def hay_pendiente(self) -> bool:
		"""``True`` si hay un archivo esperando a que se pulse Intro."""
		return self._pendiente is not None

	def mostrar(self, proveedor: Proveedor | None, entrada: Entrada | None, limite_kb: int = 64, forzar: bool = False) -> None:
		"""Muestra el contenido de ``entrada`` (lectura en un hilo).

		:param limite_kb: kilobytes como mucho (preferencia).
		:param forzar: leer aunque sea de la nube o de la red (lo que hace Intro).
		"""
		self._pendiente = None
		if entrada is None or proveedor is None:
			self.cancelar()
			self.codificacion = ""
			self._fijar_texto(_("Sin elemento"))
			return
		if entrada.es_carpeta or entrada.es_superior:
			self.cancelar()
			self.codificacion = ""
			self._fijar_texto(_("Carpeta: {n}").format(n=entrada.nombre))
			return
		if entrada.en_nube and not forzar:
			self.cancelar()
			self._esperar_intro(proveedor, entrada, limite_kb, _("«{n}» solo está en la nube; leerlo lo descargará.").format(n=entrada.nombre))
			return
		self._enviar(
			self._trabajo_leer, proveedor, entrada, limite_kb, forzar,
			al_terminar=lambda resultado: self._al_leer(proveedor, entrada, limite_kb, resultado),
			nombre="vista_rapida",
		)

	@staticmethod
	def _trabajo_leer(tarea: Tarea, proveedor: Proveedor, entrada: Entrada, limite_kb: int, forzar: bool) -> tuple[str, str, bool]:
		"""En el hilo: («red», "", False) si hay que esperar a Intro; si no, (texto, codificación, recortado)."""
		if not forzar and es_ruta_lenta(proveedor, entrada.ruta):
			return "red", "", False
		# 2.0 (3.5, 14.7): un complemento con visor para Vista rápida (PDF, DOCX...)
		# da el texto legible; si falla o no hay, se lee el archivo como en la 1.x.
		from app.ui.ventanas import visor

		encontrado = visor.visor_de_complemento(entrada.nombre, vista_rapida=True)
		if encontrado is not None:
			documento = visor.documento_de_complemento(encontrado[0], proveedor, entrada.ruta, tarea)
			if documento is not None:
				return visor.texto_de_documento(documento), "utf-8", False
		datos, recortado = leer_contenido(tarea, proveedor, entrada.ruta, limite_kb)
		tarea.comprobar()
		texto, usada = texto_de_contenido(datos)
		return texto, usada, recortado

	def _al_leer(self, proveedor: Proveedor, entrada: Entrada, limite_kb: int, resultado: tuple[str, str, bool]) -> None:
		texto, usada, recortado = resultado
		if not usada:
			self._esperar_intro(proveedor, entrada, limite_kb, _("«{n}» está en una ruta de red.").format(n=entrada.nombre))
			return
		self.codificacion = usada
		if not texto:
			texto = _("Archivo vacío")
		elif recortado:
			# Al final y en su propia línea: el contenido empieza en la primera.
			texto += "\n\n" + _("(Se muestran los primeros {kb} KB.)").format(kb=formato.miles(int(limite_kb)))
		self._fijar_texto(texto)

	def _esperar_intro(self, proveedor: Proveedor, entrada: Entrada, limite_kb: int, motivo: str) -> None:
		self._pendiente = (proveedor, entrada, limite_kb)
		self.codificacion = ""
		self._fijar_texto(motivo + "\n" + _("Pulse Intro para leer el archivo."))

	def leer_pendiente(self) -> bool:
		"""Lee el archivo que se quedó sin leer. Devuelve ``False`` si no había ninguno."""
		if self._pendiente is None:
			return False
		proveedor, entrada, limite_kb = self._pendiente
		self._fijar_texto(_("Leyendo..."))
		self.mostrar(proveedor, entrada, limite_kb, forzar=True)
		return True

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		"""Intro sin modificadores lee el archivo pendiente; el resto de teclas son del texto."""
		if (
			evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
			and not evento.HasAnyModifiers()
			and self.leer_pendiente()
		):
			return
		evento.Skip()
