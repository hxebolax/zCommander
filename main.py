# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Punto de entrada de la aplicación.

El ORDEN de arranque importa (1.x §9.2 y diseño 2.0, 14.8):

1. **Cortocircuitos**, antes de la instancia única, de cualquier pendiente y de
   la configuración de la persona, cada uno con su registro mínimo propio
   (``data/logs/prueba-<fecha>.log``): ``--probar-componente`` y
   ``--comprobar-arranque``. Así una prueba lanzada por el actualizador de
   componentes con zCommander abierto no se reenvía a la instancia abierta ni
   vuelve a aplicar pendientes.
2. ``--esperar-pid``: espera a que termine el proceso que pidió «Reiniciar».
3. Registro (solo biblioteca estándar) antes de importar wx y lo pesado.
4. ``wx.App``, los planificadores del bus y del cargador (``wx.CallAfter``) y la
   instancia única (también ``--tarea``); marca de inicio para el actualizador.
5. Restauración pendiente de una copia de seguridad.
6. Componentes pendientes e integración tras actualizar (antes de cargar ninguna DLL).
7. Configuración (con su migración), puente al bus y WAV propios de la 1.x.
8. Complementos: modo seguro, centinelas, descubrimiento y marcadores.
9. Ventana principal con ``ArranqueInfo``; los pasos 10 y 11 los hace la ventana.

``multiprocessing.freeze_support()`` va lo primero: en la versión compilada un
proceso hijo de multiprocessing arranca este mismo ``.exe``. Todo va envuelto
en una red de seguridad: si el arranque falla, se escribe
``data/logs/arranque_fallido.log`` y se enseña un cartel.

Argumentos (``argparse``; ``--tarea <id>`` ya no se confunde con un archivo):

- archivos o carpetas que abrir;
- ``--comprobar-arranque [--complemento-prueba <carpeta>]``: arranca sin mostrar
  la ventana y sale con 0 si todo fue bien (pruebas y compilación);
- ``--probar-componente <id> [--carpeta <ruta>]``: prueba un componente de ``data/bin``;
- ``--sin-complementos``, ``--desarrollo-complementos <carpeta>``;
- ``--tras-actualizar``, ``--tarea <id>``, ``--modo-tarea``, ``--al-iniciar-sesion``, ``--esperar-pid <pid>``.
"""

from __future__ import annotations

import argparse
import builtins
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

# El GIL cede el turno cada 5 ms por defecto. Con hilos de fondo trabajando,
# el hilo de la interfaz tardaba en recuperarlo y el lector de pantalla (que
# pregunta a la interfaz en ese hilo) se quedaba mudo. Con 1 ms la interfaz
# responde enseguida; el coste es despreciable en una aplicación de escritorio.
sys.setswitchinterval(0.001)

log = logging.getLogger("app.main")

ARGUMENTO_COMPROBAR = "--comprobar-arranque"
#: Esperas de ``--esperar-pid`` (14.8, paso 2) y del lanzamiento de una tarea (paso 4).
ESPERA_PROCESO_S = 30
ESPERA_MUTEX_MAX_S = 300
ESPERA_INSTANCIA_TAREA_S = 60
ESPERA_ORDEN_TAREA_S = 600
VK_SHIFT = 0x10

# Objetos que deben vivir toda la sesión: si el recolector se llevara el
# wx.Locale, los botones volverían al inglés; si se llevara el comprobador de
# instancia, se liberaría el mutex.
_VIVOS: dict[str, object] = {}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def analizar_argumentos(argumentos: list[str]) -> argparse.Namespace:
	"""Todos los argumentos de 14.8; lo desconocido se registra y se ignora (no impide arrancar)."""
	analizador = argparse.ArgumentParser(prog="zCommander", add_help=False, allow_abbrev=False)
	analizador.add_argument("archivos", nargs="*")
	analizador.add_argument(ARGUMENTO_COMPROBAR, dest="comprobar", action="store_true")
	analizador.add_argument("--complemento-prueba", dest="complemento_prueba", default=None)
	analizador.add_argument("--probar-componente", dest="probar_componente", default=None)
	analizador.add_argument("--carpeta", dest="carpeta", default=None)
	analizador.add_argument("--sin-complementos", dest="sin_complementos", action="store_true")
	analizador.add_argument("--desarrollo-complementos", dest="desarrollo", default=None)
	analizador.add_argument("--tras-actualizar", dest="tras_actualizar", action="store_true")
	analizador.add_argument("--tarea", dest="tarea", default=None)
	analizador.add_argument("--modo-tarea", dest="modo_tarea", action="store_true")
	analizador.add_argument("--al-iniciar-sesion", dest="al_iniciar_sesion", action="store_true")
	analizador.add_argument("--esperar-pid", dest="esperar_pid", type=int, default=None)
	opciones, desconocidos = analizador.parse_known_args(argumentos)
	if desconocidos:
		log.warning("Argumentos desconocidos que se ignoran: %s", desconocidos)
	return opciones


def _mostrar_error_arranque(mensaje: str) -> None:
	"""Cartel de error aunque wx no esté disponible (último recurso)."""
	titulo = _("Error al iniciar")
	try:
		import wx

		if wx.GetApp() is None:
			wx.App(False)
		# MessageDialog y no MessageBox: este deja que el botón diga «Aceptar».
		dialogo = wx.MessageDialog(None, mensaje, titulo, wx.OK | wx.ICON_ERROR)
		dialogo.SetOKLabel(_("&Aceptar"))
		try:
			dialogo.ShowModal()
		finally:
			dialogo.Destroy()
		return
	except Exception:  # noqa: BLE001 - si wx falla, se prueba el cartel nativo
		log.debug("No se pudo mostrar el cartel con wx", exc_info=True)
	try:
		import ctypes

		ctypes.windll.user32.MessageBoxW(0, mensaje, titulo, 0x10)
	except Exception:  # noqa: BLE001 - ya no queda dónde avisar salvo la consola
		if sys.__stderr__ is not None:
			print(mensaje, file=sys.__stderr__)


def _fijar_idioma():
	"""Pone wxWidgets en español (Aceptar, Cancelar, Sí, No...) y devuelve el ``wx.Locale``.

	En la versión compilada los catálogos de wx están en ``lib/wx/locale``;
	se añade esa ruta para que los encuentre también allí.
	"""
	import wx

	wx.Locale.AddCatalogLookupPathPrefix(str(Path(wx.__file__).resolve().parent / "locale"))
	idioma = wx.Locale(wx.LANGUAGE_SPANISH)
	if not idioma.IsOk():
		log.warning("No se pudo activar el idioma español de wxWidgets; se usa el del sistema.")
	return idioma


def _instalar_aviso_de_errores(ventana) -> None:
	"""Enseña al usuario los errores no controlados (como mucho uno cada 30 s)."""
	import wx

	from app.core import registro

	ultimo = [0.0]

	def mostrar(resumen: str) -> None:
		ahora = time.monotonic()
		if ahora - ultimo[0] < 30:
			return
		ultimo[0] = ahora
		padre = ventana if ventana and ventana.IsShown() else None
		from app.ui.accesibilidad.dialogos import mostrar_error

		mostrar_error(
			padre,
			_(
				"Se ha producido un error inesperado:\n\n{resumen}\n\n"
				"La aplicación intentará seguir funcionando. Los detalles están en "
				"Opciones, Abrir la carpeta de registros."
			).format(resumen=resumen),
			_("Error inesperado"),
		)

	# CallAfter: el error puede ocurrir en un hilo y los diálogos solo se
	# pueden abrir desde el hilo principal.
	registro.establecer_aviso_usuario(lambda resumen: wx.CallAfter(mostrar, resumen))


# ── 1. Cortocircuitos ────────────────────────────────────────────────────────


def _registro_minimo(nombre: str) -> logging.Handler | None:
	"""Registro propio de un cortocircuito: ``data/logs/prueba-<fecha>.log`` (solo biblioteca estándar)."""
	try:
		from app.core import paths

		ruta = paths.ruta_registros() / f"{nombre}-{time.strftime('%Y%m%d-%H%M%S')}.log"
		manejador = logging.FileHandler(ruta, encoding="utf-8")
		manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(filename)s:%(lineno)d %(message)s"))
		logging.getLogger().addHandler(manejador)
		logging.getLogger().setLevel(logging.INFO)
		return manejador
	except OSError:
		log.debug("No se pudo crear el registro mínimo", exc_info=True)
		return None


def _probar_componente(opciones: argparse.Namespace) -> int:
	"""``--probar-componente <id> [--carpeta <ruta>]``: prueba y sale con su código (6.2)."""
	_registro_minimo("prueba")
	from app.services.componentes import prueba

	codigo = prueba.probar_componente(opciones.probar_componente, Path(opciones.carpeta) if opciones.carpeta else None)
	log.info("Prueba del componente %s: código %s", opciones.probar_componente, codigo)
	return int(codigo)


def _comprobar_arranque(opciones: argparse.Namespace) -> int:
	"""``--comprobar-arranque`` con su secuencia propia (precisión 8 de la ronda 4).

	fijar_recursos → VARIABLE_DATA → registro → wx.App y planificadores →
	configuración → cargador.arrancar → ventana sin mostrar → comprobar_complemento
	→ cerrar. Sin instancia única, sin pendientes (pasos 5 y 6) y sin los pasos 10 y 11.
	Lo escribible va a una carpeta temporal dentro de ``data/temp`` que se borra al final;
	los recursos distribuibles (bin, sounds, locales, docs, icons) se leen de la ``data`` real.
	"""
	from app.core import paths

	real = paths.ruta_datos()
	minimo = _registro_minimo("prueba")
	paths.fijar_recursos(real)
	temporal = real / "temp" / f"comprobar-arranque-{os.getpid()}"
	temporal.mkdir(parents=True, exist_ok=True)
	anterior = os.environ.get(paths.VARIABLE_DATA)
	os.environ[paths.VARIABLE_DATA] = str(temporal)
	try:
		from app.core import registro
		from app.core.version import APP_VERSION, NOMBRE_APLICACION

		_VIVOS["registro"] = registro.configurar_registro(NOMBRE_APLICACION, APP_VERSION)
		_preparar_cache_com(paths.ruta_cache() / "gen_py")
		import wx

		aplicacion = wx.App(False)
		_fijar_planificadores(wx)
		wx.HelpProvider.Set(wx.SimpleHelpProvider())
		_VIVOS["idioma"] = _fijar_idioma()
		from app.core.configuracion import Configuracion

		configuracion = Configuracion()
		from app.plugins import cargador

		cargador_sesion = cargador.arrancar(configuracion, opciones.sin_complementos,
			Path(opciones.desarrollo) if opciones.desarrollo else None)
		from app.services.servicios_nucleo import ArranqueInfo
		from app.services import eventos
		from app.ui.ventana_principal import VentanaPrincipal

		ventana = VentanaPrincipal(configuracion, None, arranque=ArranqueInfo(cargador=cargador_sesion, bus=eventos.bus()))
		codigo = 0
		if opciones.complemento_prueba:
			from app.plugins import prueba

			codigo = int(prueba.comprobar_complemento(Path(opciones.complemento_prueba)))
		log.info("Arranque completado (comprobación).")
		wx.CallAfter(ventana.Close, True)
		aplicacion.MainLoop()
		log.info("Cierre normal. Comprobación de arranque terminada con el código %s", codigo)
		registro.detener_registro()
		return codigo
	finally:
		if minimo is not None:
			logging.getLogger().removeHandler(minimo)
			minimo.close()
		if anterior is None:
			os.environ.pop(paths.VARIABLE_DATA, None)
		else:
			os.environ[paths.VARIABLE_DATA] = anterior
		shutil.rmtree(temporal, ignore_errors=True)


# ── 2. --esperar-pid ─────────────────────────────────────────────────────────


def _voz_minima(texto: str) -> None:
	"""Aviso sin configuración ni ventana (la salida que encuentre: NVDA, JAWS o SAPI5)."""
	try:
		from app.ui.accesibilidad import voz

		voz.hablar(texto, interrumpir=True, sincrono=True)
	except Exception:  # noqa: BLE001 - sin voz se sigue esperando en silencio
		log.debug("No se pudo decir «%s»", texto, exc_info=True)


def _esperar_pid(pid: int) -> bool:
	"""Espera al proceso que pidió reiniciar y, si hace falta, a que suelte la instancia única (paso 2)."""
	import ctypes

	from app.core import instancia_unica
	from app.core.version import ID_APLICACION

	SYNCHRONIZE = 0x00100000
	kernel32 = ctypes.windll.kernel32
	kernel32.OpenProcess.restype = ctypes.c_void_p
	manejador = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
	if manejador:
		try:
			kernel32.WaitForSingleObject(ctypes.c_void_p(manejador), ESPERA_PROCESO_S * 1000)
		finally:
			kernel32.CloseHandle(ctypes.c_void_p(manejador))
	inicio = time.monotonic()
	ultimo_aviso = inicio
	while instancia_unica.hay_instancia(ID_APLICACION):
		if time.monotonic() - inicio > ESPERA_MUTEX_MAX_S:
			_voz_minima(_("No se pudo reiniciar: zCommander sigue abierto"))
			return False
		if time.monotonic() - ultimo_aviso >= 30:
			ultimo_aviso = time.monotonic()
			_voz_minima(_("Esperando a que se cierre zCommander..."))
		time.sleep(0.25)
	return True


# ── 4. Planificadores, modo seguro e instancia única ──────────────────────────


def _fijar_planificadores(wx) -> None:
	"""Justo después de crear ``wx.App``: todo lo que se entrega a la interfaz pasa por el bucle de eventos."""
	from app.plugins import cargador
	from app.services import eventos

	eventos.bus().fijar_planificador(wx.CallAfter)
	cargador.fijar_planificador(wx.CallAfter)


def _mayus_pulsada() -> bool:
	"""Mayús pulsada al arrancar: modo seguro (3.4)."""
	try:
		import ctypes

		return bool(ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
	except Exception:  # noqa: BLE001 - fuera de Windows no hay modo seguro por tecla
		log.debug("No se pudo leer el estado de Mayús", exc_info=True)
		return False


def _orden_de_lanzamiento(*extra: str) -> list[str]:
	"""Cómo se lanza otra vez zCommander: el ``.exe`` o el intérprete con ``main.py``."""
	if getattr(sys, "frozen", False):
		return [sys.executable, *extra]
	return [sys.executable, str(Path(__file__).resolve()), *extra]


def _tarea_sin_instancia(instancia, id_tarea: str) -> int | None:
	"""``--tarea`` sin otra instancia (paso 4): lanza la instancia real fuera del Job y le entrega la orden.

	Devuelve el código con el que salir, o ``None`` si este proceso debe quedarse como
	instancia en modo tarea (no puede salir del Job del Programador de tareas).
	"""
	from app.core import instancia_unica, procesos
	from app.core.version import ID_APLICACION

	if not procesos.puede_salir_del_job():
		log.info("No se puede salir del Job: esta instancia ejecuta la tarea %s", id_tarea)
		return None
	instancia.liberar()
	procesos.lanzar_independiente(_orden_de_lanzamiento("--modo-tarea"))
	limite = time.monotonic() + ESPERA_INSTANCIA_TAREA_S
	while not instancia_unica.hay_instancia(ID_APLICACION) and time.monotonic() < limite:
		time.sleep(0.2)
	if not instancia_unica.hay_instancia(ID_APLICACION):
		log.error("La instancia de la tarea %s no arrancó a tiempo", id_tarea)
		return 1
	entregada = instancia_unica.dejar_orden_esperando(instancia_unica.ORDEN_TAREA, [id_tarea], ESPERA_ORDEN_TAREA_S)
	return 0 if entregada else 1


# ── Cierres anómalos (3.8) ───────────────────────────────────────────────────


def _ruta_arranques() -> Path:
	from app.core import paths

	return paths.ruta_cache() / "arranques.json"


def _anotar_arranque() -> int:
	"""Marca el arranque en curso y devuelve los cierres anómalos seguidos anteriores."""
	ruta = _ruta_arranques()
	try:
		datos = json.loads(ruta.read_text(encoding="utf-8"))
	except (OSError, ValueError):
		datos = {}
	anomalos = int(datos.get("anomalos", 0)) + (1 if datos.get("en_curso") else 0)
	try:
		ruta.write_text(json.dumps({"en_curso": True, "anomalos": anomalos}), encoding="utf-8")
	except OSError:
		log.warning("No se pudo escribir %s", ruta, exc_info=True)
	return anomalos


def _anotar_cierre_normal() -> None:
	try:
		_ruta_arranques().write_text(json.dumps({"en_curso": False, "anomalos": 0}), encoding="utf-8")
	except OSError:
		log.warning("No se pudo anotar el cierre normal", exc_info=True)


def _preguntar_modo_seguro() -> bool:
	"""Tras dos cierres anómalos seguidos, se propone arrancar sin complementos (3.8)."""
	import wx

	dialogo = wx.MessageDialog(None, _("zCommander se cerró de forma inesperada dos veces seguidas. "
		"¿Arrancar sin complementos (modo seguro)?"), _("Modo seguro"), wx.YES_NO | wx.ICON_QUESTION)
	dialogo.SetYesNoLabels(_("&Sí, sin complementos"), _("&No, arrancar normal"))
	try:
		return dialogo.ShowModal() == wx.ID_YES
	finally:
		dialogo.Destroy()


def _preguntar_restauracion(info) -> str:
	"""Pregunta nativa por una restauración preparada con «Más tarde» (7.6)."""
	import wx

	texto = _("Hay una restauración pendiente de la copia «{d}», preparada el {f}. Lo que haya cambiado desde entonces "
		"en esas partes se sustituirá.").format(d=info.descripcion, f=info.fecha.strftime("%d/%m/%Y %H:%M"))
	dialogo = wx.MessageDialog(None, texto, _("Restauración pendiente"), wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
	dialogo.SetYesNoCancelLabels(_("&Aplicarla ahora"), _("&Descartarla"), _("Más &tarde"))
	try:
		respuesta = dialogo.ShowModal()
	finally:
		dialogo.Destroy()
	return {wx.ID_YES: "aplicar", wx.ID_NO: "descartar"}.get(respuesta, "despues")


# ── Arranque normal ──────────────────────────────────────────────────────────


def _principal(argumentos: list[str]) -> int:
	inicio = time.perf_counter()
	opciones = analizar_argumentos(argumentos)

	# 1. Cortocircuitos.
	if opciones.probar_componente:
		return _probar_componente(opciones)
	if opciones.comprobar:
		return _comprobar_arranque(opciones)

	# 2. Reinicio: esperar al proceso anterior.
	if opciones.esperar_pid and not _esperar_pid(opciones.esperar_pid):
		return 1

	# 3. Registro (solo biblioteca estándar). Las .pyc del código, fuera de la carpeta del programa (17.1).
	from app.core import paths, registro
	from app.core.version import APP_VERSION, ID_APLICACION, NOMBRE_APLICACION

	if not getattr(sys, "frozen", False):
		sys.pycache_prefix = str(paths.ruta_cache() / "pycache")
	_VIVOS["registro"] = registro.configurar_registro(NOMBRE_APLICACION, APP_VERSION)
	_preparar_cache_com(paths.ruta_cache() / "gen_py")

	# 4. wx, planificadores, idioma e instancia única.
	from app.ui.accesibilidad import visual

	visual.activar_conciencia_dpi()
	import wx

	from app.services.windows import unidades

	# Que una unidad vacía o caída no muestre «Inserte un disco» ni cuelgue un hilo.
	unidades.evitar_errores_criticos()
	modo_seguro = bool(opciones.sin_complementos) or _mayus_pulsada()
	# redirect=False: la salida estándar va al registro, no a una ventana de wx.
	aplicacion = wx.App(False)
	aplicacion.SetAppName(ID_APLICACION)
	_fijar_planificadores(wx)
	wx.HelpProvider.Set(wx.SimpleHelpProvider())
	_VIVOS["idioma"] = _fijar_idioma()

	from app.core import instancia_unica
	from app.core.instancia_unica import InstanciaUnica

	instancia = InstanciaUnica(ID_APLICACION)
	_VIVOS["instancia"] = instancia
	archivos = [os.path.abspath(a) for a in opciones.archivos]
	if instancia.hay_otra():
		if opciones.tarea:
			log.info("Hay otra instancia: se le deja la tarea %s", opciones.tarea)
			instancia_unica.dejar_orden(instancia_unica.ORDEN_TAREA, [opciones.tarea])
			return 0
		log.info("Ya hay otra instancia en marcha; se le pide que se muestre.")
		if not instancia.pedir_mostrar(archivos):
			from app.ui.accesibilidad.dialogos import mostrar_mensaje

			mostrar_mensaje(None, _("{nombre} ya está en ejecución.").format(nombre=NOMBRE_APLICACION), NOMBRE_APLICACION)
		return 0
	modo = "tarea" if opciones.modo_tarea else ("sesion" if opciones.al_iniciar_sesion else "normal")
	tarea = None
	if opciones.tarea:
		codigo = _tarea_sin_instancia(instancia, opciones.tarea)
		if codigo is not None:
			return codigo
		modo, tarea = "tarea", opciones.tarea
	from app.services import actualizador

	actualizador.marcar_inicio(opciones.tras_actualizar)
	anomalos = _anotar_arranque()
	if anomalos >= 2 and not modo_seguro and modo == "normal":
		modo_seguro = _preguntar_modo_seguro()

	# 5. Restauración pendiente (sin preguntar en modo tarea ni tras actualizar: paso 11).
	from app.services.copia import pendiente

	preguntar = None if (modo == "tarea" or opciones.tras_actualizar) else _preguntar_restauracion
	restauracion = pendiente.aplicar_pendiente(paths.ruta_datos(), preguntar)

	# 6. Componentes pendientes e integración tras actualizar, antes de cargar ninguna DLL.
	from app.services.componentes import integrar

	# app/services no puede importar la voz de la interfaz: se le pasa la mínima
	# para que «Preparando los componentes nuevos…» se oiga y no quede solo en el registro.
	integrar.fijar_anunciador(_voz_minima)
	avisos = list(integrar.aplicar_pendientes(paths.ruta_datos()))
	integracion = integrar.integrar_entrante(paths.ruta_datos())

	# 7. Configuración (con su migración), puente al bus y WAV propios de la 1.x.
	from app.core.configuracion import Configuracion
	from app.services import eventos
	from app.services.sonidos import paquetes

	configuracion = Configuracion()
	if configuracion.recuperacion:
		log.warning("Configuración recuperada: %s", configuracion.recuperacion)
	nivel = str(configuracion.obtener("registro.nivel")).upper()
	if nivel in ("DEBUG", "INFO", "WARNING", "ERROR") and not logging.getLogger().isEnabledFor(logging.DEBUG):
		logging.getLogger().setLevel(nivel)
	_VIVOS["puente"] = eventos.puentear_configuracion(configuracion)
	paquetes.migrar_1x(paths.ruta_datos(), configuracion)

	# Voz: preferencias y aviso de arranque antes de lo pesado (sin ventana de espera).
	from app.ui import anuncios
	from app.ui.accesibilidad import voz

	voz.configurar(retraso_ms=int(configuracion.obtener("accesibilidad.retardo_voz_ms")))
	voz.configurar_salida(configuracion.obtener("accesibilidad.salida_voz"), bool(configuracion.obtener("accesibilidad.sapi_sin_lector")))
	anuncios.configurar(bool(configuracion.obtener("accesibilidad.anuncios")), configuracion.obtener("accesibilidad.detalle"))
	if modo == "normal" and configuracion.obtener("accesibilidad.anuncios"):
		voz.hablar(_("Iniciando {nombre}").format(nombre=NOMBRE_APLICACION), interrumpir=True, sincrono=True)

	# Restos de temporales de una sesión que terminó de golpe.
	from app.services.vfs import temporales

	temporales.limpiar_todo()

	# 8. Complementos: modo seguro, centinelas, descubrimiento y marcadores.
	from app.plugins import cargador

	cargador_sesion = cargador.arrancar(configuracion, modo_seguro, Path(opciones.desarrollo) if opciones.desarrollo else None)

	# 9. Ventana principal (aquí se cargan libarchive y los proveedores).
	from app.services.servicios_nucleo import ArranqueInfo
	from app.ui.ventana_principal import VentanaPrincipal

	arranque = ArranqueInfo(cargador=cargador_sesion, bus=eventos.bus(), modo=modo, tarea=tarea,
		tras_actualizar=bool(opciones.tras_actualizar), avisos=tuple(avisos), integracion=integracion, restauracion=restauracion)
	ventana = VentanaPrincipal(configuracion, instancia, arranque=arranque)
	_instalar_aviso_de_errores(ventana)
	instancia.registrar_ventana(ventana.GetHandle())
	ventana.mostrar()
	if archivos:
		wx.CallAfter(ventana.abrir_argumentos, archivos)
	if modo == "normal":
		if not configuracion.obtener("general.asistente_hecho"):
			wx.CallLater(600, _asistente_inicial, ventana)
		else:
			# Tras una actualización, las novedades una sola vez (diseño 8.27).
			wx.CallLater(900, _novedades, ventana)

	log.info("Arranque completado en %.2f s.", time.perf_counter() - inicio)
	aplicacion.MainLoop()

	registro.establecer_aviso_usuario(None)
	voz.detener()
	instancia.liberar()
	_anotar_cierre_normal()
	log.info("Cierre normal.")
	registro.detener_registro(cierre_normal=True)
	return 0


def _preparar_cache_com(carpeta) -> None:
	"""La caché de pywin32 (``gen_py``) en ``data/cache`` y no en el temporal de Windows.

	Por defecto pywin32 la guarda en ``%TEMP%\\gen_py``: rompe la portabilidad
	(escribe fuera de ``data``) y, si otro programa la dejó a medias, la rehace al
	arrancar con avisos como «Could not add module ... CLSIDToClassMap». Tiene que
	ir antes de importar ``win32com.client``.
	"""
	try:
		carpeta.mkdir(parents=True, exist_ok=True)
		import win32com

		win32com.__gen_path__ = str(carpeta)
		import win32com.gen_py

		win32com.gen_py.__path__ = [str(carpeta)]
	except Exception:  # noqa: BLE001 - sin pywin32 o sin permiso, pywin32 usa su sitio de siempre
		log.debug("No se pudo llevar la caché COM a %s", carpeta, exc_info=True)


def _novedades(ventana) -> None:
	"""Muestra las novedades si se acaba de actualizar (el visor anota la versión vista)."""
	if not ventana:
		return
	from app.core.version import APP_VERSION
	from app.ui import visor_ayuda

	try:
		visor_ayuda.mostrar_novedades_si_procede(ventana, APP_VERSION)
	except Exception:  # noqa: BLE001 - las novedades nunca impiden usar la aplicación
		log.exception("No se pudieron mostrar las novedades")


def _asistente_inicial(ventana) -> None:
	"""Asistente de primer arranque (bloque F); si aún es provisional, no se muestra."""
	from app.ui.acciones import dialogos_f

	asistente = getattr(dialogos_f, "asistente", None)
	if asistente is None or getattr(asistente, "provisional", False) or not ventana:
		return
	ventana.ejecutar_orden("asistente")


def principal(argumentos: list[str] | None = None) -> int:
	"""Arranca la aplicación y garantiza que ningún fallo quede sin explicación."""
	import multiprocessing

	# Imprescindible en la versión compilada si algo usa multiprocessing.
	multiprocessing.freeze_support()
	try:
		return _principal(sys.argv[1:] if argumentos is None else argumentos)
	except SystemExit:
		raise
	except BaseException as error:  # noqa: BLE001 - red de seguridad del arranque
		log.critical("Fallo no controlado al iniciar la aplicación.", exc_info=True)
		ruta = None
		try:
			from app.core import registro

			ruta = registro.registrar_fallo_de_arranque(error)
		except Exception:  # noqa: BLE001 - el propio registro puede ser lo que falla
			log.debug("No se pudo escribir arranque_fallido.log", exc_info=True)
		detalle = (
			_("Los detalles están en {ruta}.").format(ruta=ruta)
			if ruta
			else _("Compruebe que la carpeta «data» existe y no es de solo lectura.")
		)
		_mostrar_error_arranque(_("No se pudo iniciar la aplicación.") + f"\n\n{type(error).__name__}: {error}\n\n" + detalle)
		return 1


if __name__ == "__main__":
	sys.exit(principal())
