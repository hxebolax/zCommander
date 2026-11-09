# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
# Módulo de aplicación de NVDA para «ZCommander.exe» (diseño 2.0 de zCommander, 10.16).
"""Mejoras de NVDA para zCommander, el gestor de archivos accesible.

El nombre del archivo decide a qué programa se aplica: es el del ejecutable en
minúsculas y sin «.exe» (``ZCommander.exe`` → ``zcommander.py``). Desde el
código fuente zCommander corre dentro de ``python.exe`` y este módulo no se
aplica: solo actúa en la versión compilada.

Este código se ejecuta DENTRO de NVDA, con el Python de NVDA (3.13 de 64 bits
desde NVDA 2026.1), no con el de zCommander. Solo importa módulos de NVDA y la
parte de la biblioteca estándar que NVDA incluye.

Qué hace (cada función tiene su comportamiento de NVDA si algo falla):

1. **Celdas completas.** NVDA lee cada celda de una lista SysListView32 con un
   búfer de 512 caracteres (``CBEMAXSTRLEN``) y corta a 511 los textos largos
   (la columna Ruta de las listas de resultados, nombres largos). Aquí la
   lectura usa un búfer de 16 384 caracteres, SOLO en zCommander.
2. **Movimiento silencioso.** Cuando zCommander mueve el foco por su cuenta
   (tras volver a leer la carpeta, al restaurar marcas, al aplicar un filtro,
   al volver de un diálogo al mismo elemento) pone antes en la lista la
   propiedad de ventana ``zCommander.MovimientoSilencioso`` con la hora
   (``GetTickCount64``). Mientras la marca tenga menos de 500 ms, NVDA no
   anuncia ese cambio de foco. La marca caduca sola.
3. **Orden de lectura.** zCommander publica en la lista la propiedad
   ``zCommander.OrdenLectura``: un entero de 64 bits con un índice de columna
   (base 0) de 4 bits por posición, de los bits bajos a los altos, terminado
   en ``0xF`` (como mucho 15 columnas). Al moverse por las filas se leen solo
   esas columnas, en ese orden. Sin la propiedad, NVDA lee como siempre.
   Si la primera columna está vacía (la Marca de una fila sin marcar), la
   segunda se dice sin cabecera, como la primera.
4. **NVDA+Mayúsculas+J** lee la fila enfocada completa, con todas las columnas
   y sus cabeceras; pulsado dos veces, la muestra en una ventana navegable.

Al desactivar o desinstalar el complemento no queda nada modificado: todo se
hace con clases superpuestas (overlay classes) de esta aplicación.
"""

import ctypes
from ctypes import wintypes

import addonHandler
import api
import appModuleHandler
import ui
import watchdog
from logHandler import log
from NVDAObjects.IAccessible import sysListView32
from scriptHandler import getLastScriptRepeatCount, script

# Instala «_» en este módulo con las traducciones de locale/<idioma>/LC_MESSAGES/nvda.mo.
# Desde la carpeta scratchpad (pruebas de desarrollo) el módulo no pertenece a un
# complemento y NVDA lanza AddonError: se sigue con el «_» de NVDA (textos en inglés).
try:
	addonHandler.initTranslation()
except addonHandler.AddonError:
	log.debug("Módulo de zCommander cargado fuera de un complemento (scratchpad): sin traducciones propias.")

# ── CONFIGURACIÓN (debe coincidir con app/ui/senales_nvda.py de zCommander) ──
#: Propiedad de ventana que zCommander pone en la lista antes de mover el foco
#: por su cuenta. Su valor es GetTickCount64() en el momento del movimiento.
PROPIEDAD_SILENCIO = "zCommander.MovimientoSilencioso"
#: Propiedad de ventana con el orden de lectura de las columnas (10.5).
PROPIEDAD_LECTURA = "zCommander.OrdenLectura"
#: Durante cuántos milisegundos tras la marca se ignora el foco. Pasado ese
#: tiempo, NVDA vuelve a anunciar aunque zCommander no quite la marca.
VENTANA_SILENCIO_MS = 500
#: Máximo de caracteres por celda (se reservan 2 bytes por carácter en zCommander).
MAXIMO_CARACTERES = 16384
#: Columnas como mucho en el orden de lectura y valor del terminador.
MAX_COLUMNAS = 15
TERMINADOR = 0xF
# ─────────────────────────────────────────────────────────────────────────────

#: Marcas de dirección que NVDA quita también del nombre de las filas.
_MARCAS_DIRECCION = ("‎", "‏")

# Constantes de la API de listas de Windows (commctrl.h). Se toman de NVDA si
# existen para seguir su criterio, con el valor documentado como respaldo.
LVIF_TEXT = getattr(sysListView32, "LVIF_TEXT", 0x0001)
LVIF_COLUMNS = getattr(sysListView32, "LVIF_COLUMNS", 0x0200)
LVM_GETITEMTEXTW = getattr(sysListView32, "LVM_GETITEMTEXTW", 0x1000 + 115)
MEM_COMMIT = 0x1000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

# Instancias PROPIAS de user32 y kernel32. No se tocan los argtypes de
# ctypes.windll.user32, que comparte todo NVDA.
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_GetPropW = _user32.GetPropW
_GetPropW.argtypes = (wintypes.HWND, wintypes.LPCWSTR)
_GetPropW.restype = wintypes.HANDLE

_GetTickCount64 = _kernel32.GetTickCount64
_GetTickCount64.argtypes = ()
_GetTickCount64.restype = ctypes.c_ulonglong

_VirtualAllocEx = _kernel32.VirtualAllocEx
_VirtualAllocEx.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD)
_VirtualAllocEx.restype = ctypes.c_void_p

_VirtualFreeEx = _kernel32.VirtualFreeEx
_VirtualFreeEx.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD)
_VirtualFreeEx.restype = wintypes.BOOL

_WriteProcessMemory = _kernel32.WriteProcessMemory
_WriteProcessMemory.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p)
_WriteProcessMemory.restype = wintypes.BOOL

_ReadProcessMemory = _kernel32.ReadProcessMemory
_ReadProcessMemory.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p)
_ReadProcessMemory.restype = wintypes.BOOL


# ════════════════════════════════════════════════════════════════════════════
# Señales de zCommander (propiedades de ventana)
# ════════════════════════════════════════════════════════════════════════════

def leer_propiedad(hwnd, nombre: str) -> int:
	"""Valor de una propiedad de ventana (0 si no está o no hay ventana)."""
	if not hwnd:
		return 0
	return int(_GetPropW(hwnd, nombre) or 0)


def marca_reciente(valor: int, ahora: int, ventana_ms: int = VENTANA_SILENCIO_MS) -> bool:
	"""Dice si una marca de GetTickCount64() está dentro de la ventana de silencio.

	Un valor 0 significa «sin marca». Una marca del futuro (no debería darse:
	zCommander y NVDA leen el mismo reloj) no silencia nada.
	"""
	if not valor:
		return False
	return 0 <= ahora - valor <= ventana_ms


def movimiento_silencioso_activo(hwnd) -> bool:
	"""True si zCommander marcó la ventana ``hwnd`` hace menos de VENTANA_SILENCIO_MS."""
	return marca_reciente(leer_propiedad(hwnd, PROPIEDAD_SILENCIO), int(_GetTickCount64()))


def decodificar_orden(valor: int) -> list[int] | None:
	"""Índices de columna (base 0) del orden de lectura, o None si el valor no es válido.

	4 bits por posición, la primera en los bits bajos, terminado en 0xF. Un 0
	(sin propiedad), un valor sin terminador o con bits detrás del terminador
	no vienen de zCommander: se devuelve None y NVDA lee como siempre. ``0xF``
	(lista vacía) quiere decir «todas, en el orden de la lista».
	"""
	if not valor:
		return None
	valor &= 0xFFFFFFFFFFFFFFFF
	indices: list[int] = []
	for posicion in range(MAX_COLUMNAS + 1):
		parte = (valor >> (4 * posicion)) & 0xF
		if parte == TERMINADOR:
			return indices if not valor >> (4 * (posicion + 1)) else None
		indices.append(parte)
	return None


def orden_lectura(hwnd) -> list[int] | None:
	"""Orden de lectura publicado por zCommander en la lista ``hwnd`` (None si no hay)."""
	return decodificar_orden(leer_propiedad(hwnd, PROPIEDAD_LECTURA))


# ════════════════════════════════════════════════════════════════════════════
# Lectura de celdas sin el límite de 511 caracteres
# ════════════════════════════════════════════════════════════════════════════

def _comprobar(correcto, que: str) -> None:
	"""Convierte un fallo de la API de Windows en excepción con su código."""
	if not correcto:
		raise ctypes.WinError(ctypes.get_last_error(), f"{que} ha fallado")


def leer_celda_completa(elemento, indice: int, maximo: int = MAXIMO_CARACTERES) -> str | None:
	"""Lee la celda ``indice`` (subelemento, base 0) de un elemento de lista, sin cortarla a 511.

	Hace lo mismo que la lectura «fuera de proceso» de NVDA
	(``ListItem._getColumnContentRawOutProc``) pero con un búfer de ``maximo``
	caracteres: reserva memoria en el proceso de zCommander, le pide el texto
	con LVM_GETITEMTEXTW y lo copia. La lista virtual de zCommander copia el
	texto de ``OnGetItemText`` en ese búfer, así que llega completo.

	Devuelve None si la celda está vacía (como NVDA). Lanza una excepción si algo
	falla, para que quien llama vuelva a la lectura de NVDA.
	"""
	proceso = elemento.processHandle
	estructura = elemento.LVITEM  # NVDA elige LVITEM o LVITEM64 según el proceso
	tam_estructura = ctypes.sizeof(estructura)
	memoria_elemento = _VirtualAllocEx(proceso, None, tam_estructura, MEM_COMMIT, PAGE_READWRITE)
	_comprobar(memoria_elemento, "VirtualAllocEx (elemento)")
	try:
		memoria_texto = _VirtualAllocEx(proceso, None, maximo * 2, MEM_COMMIT, PAGE_READWRITE)
		_comprobar(memoria_texto, "VirtualAllocEx (texto)")
		try:
			fila = elemento.IAccessibleChildID - 1
			item = estructura(
				iItem=fila,
				mask=LVIF_TEXT | LVIF_COLUMNS,
				iSubItem=indice,
				pszText=memoria_texto,
				cchTextMax=maximo,
			)
			_comprobar(
				_WriteProcessMemory(proceso, memoria_elemento, ctypes.byref(item), tam_estructura, None),
				"WriteProcessMemory",
			)
			# cancellableSendMessage: si zCommander está colgado, NVDA puede
			# cancelar la espera en lugar de quedarse mudo.
			longitud = watchdog.cancellableSendMessage(elemento.windowHandle, LVM_GETITEMTEXTW, fila, memoria_elemento)
			if not longitud:
				return None
			# El control puede cambiar pszText para apuntar a su propio texto:
			# se relee la estructura y se usa el puntero que devuelva.
			_comprobar(
				_ReadProcessMemory(proceso, memoria_elemento, ctypes.byref(item), tam_estructura, None),
				"ReadProcessMemory (elemento)",
			)
			texto = ctypes.create_unicode_buffer(longitud + 1)
			_comprobar(
				_ReadProcessMemory(proceso, item.pszText, texto, longitud * 2, None),
				"ReadProcessMemory (texto)",
			)
			if longitud >= maximo - 1:
				log.debug("Celda de %d caracteres o más: puede estar cortada; sube MAXIMO_CARACTERES.", maximo - 1)
			return texto.value
		finally:
			_VirtualFreeEx(proceso, memoria_texto, 0, MEM_RELEASE)
	finally:
		_VirtualFreeEx(proceso, memoria_elemento, 0, MEM_RELEASE)


# ════════════════════════════════════════════════════════════════════════════
# Composición de lo que se lee
# ════════════════════════════════════════════════════════════════════════════

def componer_fila(columnas) -> str:
	"""Une pares (cabecera, contenido) para el gesto: «Nombre: informe.txt. Tamaño: 3 KB».

	Las celdas vacías se dicen como «vacío» para que se sepa que la columna
	existe; sin cabecera se lee solo el contenido.
	"""
	partes = []
	for cabecera, contenido in columnas:
		contenido = (contenido or "").strip() or _("blank")
		partes.append(f"{cabecera}: {contenido}" if cabecera else contenido)
	return ". ".join(partes)


def componer_nombre(celdas, con_cabeceras: bool) -> str:
	"""Nombre de la fila como lo compone NVDA, con las celdas (cabecera, contenido) dadas.

	Igual que ``sysListView32.ListItem._get_name``: se saltan las celdas vacías,
	la cabecera va delante salvo en la primera columna (y solo si NVDA está
	configurado para leer cabeceras de columna), separadas por «; » y sin
	marcas de dirección.

	Una diferencia con NVDA (zCommander 2.0.1): si la primera columna está
	vacía (la Marca de una fila sin marcar, con las marcas en columna), la
	segunda tampoco lleva cabecera, como si fuera la primera; NVDA diría
	«Nombre:» delante de cada fila sin marcar.
	"""
	partes = []
	primera_vacia = bool(celdas) and not celdas[0][1]
	for posicion, (cabecera, contenido) in enumerate(celdas):
		if not contenido:
			continue
		if con_cabeceras and cabecera and posicion and not (posicion == 1 and primera_vacia):
			partes.append(f"{cabecera}: {contenido}")
		else:
			partes.append(contenido)
	nombre = "; ".join(partes)
	for marca in _MARCAS_DIRECCION:
		nombre = nombre.replace(marca, "")
	return nombre


def nvda_lee_cabeceras() -> bool:
	"""Lo que diga «Formato de documento → Cabeceras de tabla» de NVDA (columnas, o filas y columnas)."""
	try:
		opciones = sysListView32.ReportTableHeaders
		valor = sysListView32.config.conf["documentFormatting"]["reportTableHeaders"]
		return valor in (opciones.ROWS_AND_COLUMNS, opciones.COLUMNS)
	except Exception:  # noqa: BLE001 - cualquier fallo vuelve al comportamiento de NVDA (queda en su registro)
		log.debugWarning("No se pudo leer la opción de cabeceras de tabla de NVDA.", exc_info=True)
		return False


# ════════════════════════════════════════════════════════════════════════════
# Clase superpuesta y módulo de aplicación
# ════════════════════════════════════════════════════════════════════════════

class ElementoListaZC(sysListView32.ListItem):
	"""Elemento de lista de zCommander: celdas completas, foco silencioso y orden de lectura."""

	def _getColumnContentRaw(self, index):
		try:
			return leer_celda_completa(self, index)
		except Exception:  # noqa: BLE001 - cualquier fallo vuelve al comportamiento de NVDA (queda en su registro)
			# No se pierde la lectura: se registra y se usa la de NVDA (cortada a 511).
			log.debugWarning("No se pudo leer la celda completa; se usa la lectura de NVDA.", exc_info=True)
			return super()._getColumnContentRaw(index)

	def _get_shouldAllowIAccessibleFocusEvent(self):
		# windowHandle de un elemento es la ventana de la lista, donde zCommander pone la marca.
		try:
			silencio = movimiento_silencioso_activo(self.windowHandle)
		except Exception:  # noqa: BLE001 - cualquier fallo vuelve al comportamiento de NVDA (queda en su registro)
			log.debugWarning("No se pudo leer la marca de movimiento silencioso.", exc_info=True)
			silencio = False
		if silencio:
			log.debug("Foco movido por zCommander: no se anuncia.")
			return False
		return super().shouldAllowIAccessibleFocusEvent

	def _nombre_en_orden(self, orden) -> str:
		"""Compone el nombre con las columnas ``orden`` (índices de la lista, base 0)."""
		columnas = self.childCount
		if isinstance(columnas, int) and columnas >= 0:
			orden = [indice for indice in orden if indice < columnas]
		cabeceras = nvda_lee_cabeceras()
		celdas = []
		for posicion, indice in enumerate(orden):
			contenido = self._getColumnContentRaw(indice)
			# Sin cabecera en la segunda si la primera está vacía (ver componer_nombre).
			sin_cabecera = not posicion or (posicion == 1 and not celdas[0][1])
			cabecera = self._getColumnHeaderRaw(indice) if cabeceras and contenido and not sin_cabecera else None
			celdas.append((cabecera, contenido))
		return componer_nombre(celdas, cabeceras)

	def _get_name(self):
		try:
			orden = orden_lectura(self.windowHandle)
			nombre = self._nombre_en_orden(orden) if orden else ""
		except Exception:  # noqa: BLE001 - cualquier fallo vuelve al comportamiento de NVDA (queda en su registro)
			log.debugWarning("No se pudo aplicar el orden de lectura de zCommander.", exc_info=True)
			nombre = ""
		return nombre or super().name


class AppModule(appModuleHandler.AppModule):
	#: Categoría con la que aparecen los gestos en «Gestos de entrada» de NVDA.
	scriptCategory = "zCommander"

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		"""Pone ElementoListaZC delante en los elementos de las listas de zCommander.

		Solo en listas SysListView32 (``wx.ListCtrl`` en Windows) cuyo elemento
		NVDA ya trata como ListItem (las de archivos, resultados y diálogos).
		"""
		if obj.windowClassName == "SysListView32" and sysListView32.ListItem in clsList:
			clsList.insert(0, ElementoListaZC)

	@script(
		# Translators: description of a command in the Input gestures dialog.
		description=_("Reads the whole focused row of the list with its column headers; pressed twice, shows it in a window"),
		gesture="kb:NVDA+shift+j",
	)
	def script_leerFilaCompleta(self, gesture):
		foco = api.getFocusObject()
		if not isinstance(foco, sysListView32.ListItem):
			# Translators: reported when the command is used outside a list.
			ui.message(_("Not in a list"))
			return
		columnas = []
		for columna in range(1, (foco.childCount or 0) + 1):
			columnas.append((foco._getColumnHeader(columna), foco._getColumnContent(columna)))
		texto = componer_fila(columnas) if columnas else (foco.name or "")
		if not texto:
			# Translators: reported when the focused row has no text.
			ui.message(_("Empty row"))
		elif getLastScriptRepeatCount() >= 1:
			# Translators: title of the window that shows the full row.
			ui.browseableMessage(texto, _("Full row"))
		else:
			ui.message(texto)
