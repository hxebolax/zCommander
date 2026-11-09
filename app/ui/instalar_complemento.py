# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ofrece instalar el complemento de zCommander para NVDA, siempre con permiso (diseño 2.0, 10.16).

La instalación se hace ABRIENDO el ``.nvda-addon`` con ``os.startfile``: NVDA
tiene asociada esa extensión, muestra su propio diálogo («¿Instalar este
complemento?», con el aviso de que solo se instalen complementos de fuentes de
confianza) y, al aceptar, pide reiniciarse. No hace falta localizar
``nvda.exe`` ni copiar nada en la carpeta de NVDA, y la persona decide en cada
paso. **Nunca se instala en silencio ni se escribe en la configuración de NVDA.**

Piezas:

- ``ruta_complemento()`` y ``construir_desde_fuente()``: el paquete de
  ``data/bin/nvda`` (componente ``nvda``, 6.2) y, desde el código fuente, su
  generación con ``tools/construir_complemento.py`` si falta.
- ``nvda_en_ejecucion()``: busca el proceso ``nvda.exe`` (solo lectura).
- ``version_instalada()``: lee, si puede, el manifiesto del complemento ya
  instalado en la configuración de NVDA (solo lectura y orientativo: una copia
  portátil de NVDA guarda su configuración en otro sitio).
- ``explicacion(...)``: el texto que se muestra antes de abrir nada.
- ``abrir_instalador(ruta)``: llama a ``os.startfile`` y traduce los errores.
- ``debe_ofrecerse(config)``: si toca ofrecerlo una vez al arrancar
  (``accesibilidad.complemento_nvda_ofrecido``).
- ``ofrecer_instalacion(padre)`` y ``abrir(padre)``: la parte wx (botón de
  Preferencias → Accesibilidad, orden ``complemento_nvda`` y ofrecimiento al
  arrancar de ``app/ui/acciones/nvda_nv.py``).

La lógica no depende de wx: se prueba sin ventanas y con ``os.startfile``
sustituido. Adaptado de la plantilla del agente «complemento-nvda».
"""

from __future__ import annotations

import builtins
import ctypes
import importlib.util
import logging
import os
import re
import sys
import zipfile
from collections.abc import Callable, Iterable
from ctypes import wintypes
from pathlib import Path

from app.core import paths
from app.core.version import APP_VERSION

log = logging.getLogger(__name__)

#: «name» del manifiesto (igual que NOMBRE en tools/construir_complemento.py).
NOMBRE_COMPLEMENTO = "zCommander"
#: Clave interna: ya se ofreció instalarlo al arrancar (una sola vez, 10.16).
CLAVE_OFRECIDO = "accesibilidad.complemento_nvda_ofrecido"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# El paquete
# ════════════════════════════════════════════════════════════════════════════

def carpeta_paquetes() -> Path:
	"""``data/bin/nvda``: carpeta del componente ``nvda`` (viaja en la compilación)."""
	return paths.ruta_binarios() / "nvda"


def ruta_complemento(version: str = APP_VERSION, carpeta: Path | None = None) -> Path:
	"""Ruta del paquete de esta versión: ``data/bin/nvda/zCommander-<versión>.nvda-addon``."""
	return (carpeta or carpeta_paquetes()) / f"{NOMBRE_COMPLEMENTO}-{version}.nvda-addon"


def construir_desde_fuente() -> Path:
	"""Genera el paquete con ``tools/construir_complemento.py`` (solo desde el código fuente).

	La compilación ya lleva el paquete en ``data/bin/nvda``; desde el código
	fuente se genera al vuelo la primera vez. Lanza ``RuntimeError`` en la
	versión compilada (no lleva ``tools/``) y la excepción del constructor si
	el manifiesto no es válido.
	"""
	script = paths.ruta_base() / "tools" / "construir_complemento.py"
	if paths.CONGELADA or not script.is_file():
		raise RuntimeError(_("Esta copia de zCommander no trae el complemento de NVDA ni la herramienta para generarlo."))
	especificacion = importlib.util.spec_from_file_location("zc_construir_complemento", script)
	if especificacion is None or especificacion.loader is None:
		raise RuntimeError(_("No se pudo cargar {0}").format(script))
	constructor = importlib.util.module_from_spec(especificacion)
	especificacion.loader.exec_module(constructor)
	informe = constructor.construir(destino=carpeta_paquetes())
	for aviso in informe.avisos:
		log.warning("Complemento de NVDA: %s", aviso)
	return Path(informe.ruta)


def paquete_desactualizado(ruta: Path, origen: Path | None = None) -> bool:
	"""Desde el código fuente: True si algún archivo de ``nvda_addon/`` es más nuevo que el paquete."""
	origen = origen or paths.ruta_base() / "nvda_addon"
	try:
		fecha = Path(ruta).stat().st_mtime
		return any(p.is_file() and p.stat().st_mtime > fecha for p in origen.rglob("*") if "__pycache__" not in p.parts)
	except OSError:
		log.debug("No se pudo comparar %s con %s", ruta, origen, exc_info=True)
		return False


# ════════════════════════════════════════════════════════════════════════════
# ¿Está NVDA en marcha? (enumeración de procesos, solo lectura)
# ════════════════════════════════════════════════════════════════════════════

class _PROCESSENTRY32W(ctypes.Structure):
	_fields_ = [
		("dwSize", wintypes.DWORD),
		("cntUsage", wintypes.DWORD),
		("th32ProcessID", wintypes.DWORD),
		("th32DefaultHeapID", ctypes.c_size_t),
		("th32ModuleID", wintypes.DWORD),
		("cntThreads", wintypes.DWORD),
		("th32ParentProcessID", wintypes.DWORD),
		("pcPriClassBase", ctypes.c_long),
		("dwFlags", wintypes.DWORD),
		("szExeFile", ctypes.c_wchar * 260),
	]


def nombres_de_procesos() -> list[str]:
	"""Nombres de los ejecutables en marcha (vacío si no se pueden enumerar)."""
	if sys.platform != "win32":
		return []
	kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	crear = kernel32.CreateToolhelp32Snapshot
	crear.argtypes = (wintypes.DWORD, wintypes.DWORD)
	crear.restype = wintypes.HANDLE
	primero = kernel32.Process32FirstW
	primero.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
	primero.restype = wintypes.BOOL
	siguiente = kernel32.Process32NextW
	siguiente.argtypes = primero.argtypes
	siguiente.restype = wintypes.BOOL
	cerrar = kernel32.CloseHandle
	cerrar.argtypes = (wintypes.HANDLE,)
	cerrar.restype = wintypes.BOOL
	instantanea = crear(0x00000002, 0)  # TH32CS_SNAPPROCESS
	if not instantanea or instantanea == wintypes.HANDLE(-1).value:
		log.debug("No se pudieron enumerar los procesos (error %s)", ctypes.get_last_error())
		return []
	nombres: list[str] = []
	try:
		entrada = _PROCESSENTRY32W()
		entrada.dwSize = ctypes.sizeof(entrada)
		correcto = primero(instantanea, ctypes.byref(entrada))
		while correcto:
			nombres.append(entrada.szExeFile)
			correcto = siguiente(instantanea, ctypes.byref(entrada))
	finally:
		cerrar(instantanea)
	return nombres


def hay_proceso(nombres: Iterable[str], buscado: str = "nvda.exe") -> bool:
	"""True si ``buscado`` está entre ``nombres`` (sin distinguir mayúsculas)."""
	buscado = buscado.lower()
	return any(nombre.lower() == buscado for nombre in nombres)


def nvda_en_ejecucion() -> bool:
	return hay_proceso(nombres_de_procesos())


# ════════════════════════════════════════════════════════════════════════════
# Versión ya instalada (lectura, sin garantías) y versión del paquete
# ════════════════════════════════════════════════════════════════════════════

_PATRON_VERSION = re.compile(r"(?m)^\s*version\s*=\s*[\"']?([^\"'\s#]+)")


def version_instalada(nombre: str = NOMBRE_COMPLEMENTO, config_nvda: Path | None = None) -> str | None:
	"""Versión del complemento instalado en NVDA (o pendiente de instalar al reiniciar), o None.

	Mira ``%APPDATA%\\nvda\\addons\\<nombre>\\manifest.ini`` (NVDA instalado) y
	``<nombre>.pendingInstall``. Solo LEE: zCommander nunca escribe en la
	configuración de NVDA.
	"""
	if config_nvda is None:
		appdata = os.environ.get("APPDATA")
		if not appdata:
			return None
		config_nvda = Path(appdata) / "nvda"
	for carpeta in (nombre, f"{nombre}.pendingInstall"):
		try:
			texto = (config_nvda / "addons" / carpeta / "manifest.ini").read_text(encoding="utf-8-sig")
		except OSError:
			continue
		coincidencia = _PATRON_VERSION.search(texto)
		if coincidencia:
			return coincidencia.group(1)
	return None


def version_del_paquete(ruta: Path) -> str | None:
	"""Versión que declara el manifest.ini de dentro del .nvda-addon."""
	try:
		with zipfile.ZipFile(ruta) as paquete:
			texto = paquete.read("manifest.ini").decode("utf-8-sig")
	except (OSError, KeyError, zipfile.BadZipFile, UnicodeDecodeError):
		log.debug("No se pudo leer el manifiesto de %s", ruta, exc_info=True)
		return None
	coincidencia = _PATRON_VERSION.search(texto)
	return coincidencia.group(1) if coincidencia else None


def debe_ofrecerse(config, en_ejecucion: Callable[[], bool] | None = None, instalada: Callable[[], str | None] | None = None) -> bool:
	"""Si toca ofrecerlo al arrancar: NVDA activo, complemento sin instalar y aún no ofrecido (10.16)."""
	try:
		if config.obtener(CLAVE_OFRECIDO):
			return False
	except Exception:  # noqa: BLE001 - sin la clave no se ofrece: mejor callar que preguntar de más
		log.debug("No se pudo leer %s", CLAVE_OFRECIDO, exc_info=True)
		return False
	if not (en_ejecucion or nvda_en_ejecucion)():
		return False
	return (instalada or version_instalada)() is None


# ════════════════════════════════════════════════════════════════════════════
# Mensajes y apertura
# ════════════════════════════════════════════════════════════════════════════

def explicacion(en_ejecucion: bool, instalada: str | None, nueva: str | None, al_arrancar: bool = False) -> str:
	"""Texto que se muestra ANTES de abrir el paquete: qué hace, qué pasará y qué hará NVDA."""
	partes = []
	if al_arrancar:
		partes.append(_("zCommander tiene un complemento para NVDA que mejora la lectura. ¿Quiere instalarlo?"))
	partes.append(
		_("El complemento de zCommander para NVDA hace que NVDA lea completos los nombres y las rutas largas de "
		  "las listas, no repita el elemento cuando zCommander mueve el foco por su cuenta y lea las columnas en "
		  "el orden que elija. Además, NVDA+Mayúsculas+J lee la fila enfocada completa con sus cabeceras. "
		  "zCommander funciona igual sin él.")
	)
	if instalada and nueva and instalada == nueva:
		partes.append(_("Ya tiene instalada esta versión ({0}); puede volver a instalarla.").format(instalada))
	elif instalada and nueva:
		partes.append(_("Versión instalada: {0}. Versión que se ofrece: {1}.").format(instalada, nueva))
	elif nueva:
		partes.append(_("Versión que se ofrece: {0}.").format(nueva))
	partes.append(
		_("NVDA mostrará su propia ventana para preguntarle si quiere instalarlo. Si acepta, NVDA pedirá "
		  "reiniciarse: la voz se detendrá unos segundos y después volverá.")
	)
	if not en_ejecucion:
		partes.append(
			_("NVDA no parece estar en ejecución. Inícielo antes: si no, puede que el archivo no se abra con nada "
			  "que lo instale.")
		)
	partes.append(_("Puede desactivarlo o quitarlo cuando quiera desde la Tienda de complementos de NVDA."))
	if al_arrancar:
		partes.append(
			_("Esta pregunta solo se hace una vez. Puede instalarlo cuando quiera desde el menú Ayuda o desde "
			  "Preferencias, página Accesibilidad.")
		)
	return "\n\n".join(partes)


def abrir_instalador(ruta: Path, abrir: Callable[[str], object] | None = None) -> tuple[bool, str]:
	"""Abre el .nvda-addon con su programa asociado (NVDA). Devuelve (éxito, mensaje).

	``abrir`` permite sustituir ``os.startfile`` en las pruebas. No se comprueba
	nada más: la decisión de instalar la toma la persona en el diálogo de NVDA.
	"""
	ruta = Path(ruta)
	if not ruta.is_file():
		return False, _("No se encontró el archivo del complemento:\n{0}").format(ruta)
	abrir = abrir or getattr(os, "startfile", None)
	if abrir is None:
		return False, _("Abrir el complemento solo es posible en Windows.")
	try:
		abrir(str(ruta))
	except OSError as error:
		log.warning("No se pudo abrir %s: %s", ruta, error, exc_info=True)
		return False, _(
			"No se pudo abrir el complemento. Compruebe que NVDA está instalado (una copia portátil no registra "
			"la extensión .nvda-addon).\n\nPuede instalarlo a mano desde el menú de NVDA: Herramientas, Tienda de "
			"complementos, botón para instalar desde una fuente externa, y eligiendo este archivo:\n{0}\n\nDetalle: {1}"
		).format(ruta, error)
	return True, _("NVDA debería mostrar ahora su ventana de instalación.")


# ════════════════════════════════════════════════════════════════════════════
# Parte wx
# ════════════════════════════════════════════════════════════════════════════

TITULO = "Complemento de zCommander para NVDA"
BOTON_ABRIR = "&Abrir el instalador de NVDA"


def crear_dialogo(padre, texto: str):
	"""Diálogo de la pregunta: botones «Abrir el instalador de NVDA» y «Cancelar» (este, el predeterminado).

	Cancelar es el predeterminado y responde a Escape porque NVDA se reiniciará
	(15.1: foco inicial en la opción segura). El texto va en un campo de solo
	lectura con su etiqueta, que es donde empieza el foco para poder leerlo.
	"""
	import wx

	from app.ui.accesibilidad.dialogos import DialogoMensaje

	dialogo = DialogoMensaje(padre, texto, _(TITULO), opciones=[_(BOTON_ABRIR), _("&Cancelar")], icono=wx.ICON_QUESTION)
	cancelar = dialogo.FindWindow(wx.ID_CANCEL)
	if cancelar is not None:
		cancelar.SetDefault()
		cancelar.SetHelpText(_("Cierra sin abrir nada. Puede instalar el complemento más tarde."))
	if dialogo.ids_opciones:
		abrir_boton = dialogo.FindWindow(dialogo.ids_opciones[0])
		if abrir_boton is not None:
			abrir_boton.SetHelpText(_("Abre el complemento con NVDA, que te pedirá confirmación y se reiniciará."))
	return dialogo


def _preguntar(padre, texto: str) -> bool:
	"""Muestra la pregunta y devuelve True si la persona elige abrir el instalador."""
	from app.ui.accesibilidad import dialogos

	dialogo = crear_dialogo(padre, texto)
	ids = list(dialogo.ids_opciones)
	mostrar = getattr(dialogos, "_mostrar", None)
	if mostrar is not None:
		resultado = mostrar(dialogo)  # sonidos, destrucción y foco de vuelta, como los demás diálogos
	else:  # pragma: no cover - respaldo si cambia el módulo de diálogos
		try:
			resultado = dialogo.ShowModal()
		finally:
			dialogo.Destroy()
	return bool(ids) and resultado == ids[0]


def _mostrar_error(padre, mensaje: str) -> None:
	from app.ui.accesibilidad import dialogos

	dialogos.mostrar_error(padre, mensaje, _(TITULO))


def ofrecer_instalacion(
	padre=None, ruta: Path | None = None, construir: Callable[[], Path] | None = None, al_arrancar: bool = False
) -> bool:
	"""Explica, pide confirmación y abre el paquete. Devuelve True si se abrió.

	``construir``: función que genera el paquete si falta (desde el código
	fuente, ``construir_desde_fuente``). En la versión compilada el paquete ya
	viaja en ``data/bin/nvda``.
	"""
	from app.ui import anuncios

	ruta = Path(ruta) if ruta else ruta_complemento()
	if construir is not None and (not ruta.is_file() or paquete_desactualizado(ruta)):
		try:
			ruta = Path(construir())
		except Exception as error:  # noqa: BLE001 - se informa a la persona y queda en el registro
			log.exception("No se pudo generar el complemento de NVDA")
			_mostrar_error(padre, _("No se pudo generar el complemento de NVDA.\n\nDetalle: {0}").format(error))
			return False
	if not ruta.is_file():
		_mostrar_error(padre, _("No se encontró el archivo del complemento:\n{0}").format(ruta))
		return False

	texto = explicacion(nvda_en_ejecucion(), version_instalada(), version_del_paquete(ruta), al_arrancar=al_arrancar)
	if not _preguntar(padre, texto):
		return False
	correcto, mensaje = abrir_instalador(ruta)
	if correcto:
		anuncios.anunciar(mensaje, anuncios.RESULTADO)
	else:
		_mostrar_error(padre, mensaje)
	return correcto


def abrir(padre) -> None:
	"""Botón de Preferencias → Accesibilidad (``BOTONES_PAGINA``, 10.18) y orden ``complemento_nvda``."""
	ofrecer_instalacion(padre, construir=None if paths.CONGELADA else construir_desde_fuente)
