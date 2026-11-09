# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Preparación común de las pruebas.

- Cada prueba trabaja con su propia carpeta ``data`` temporal (``APP_DATA_DIR``):
  nunca se toca la configuración ni los registros reales.
- La voz se desactiva: con un lector de pantalla abierto, las pruebas no
  deben ponerse a hablar.
- Una única ``wx.App`` para toda la sesión, con el proveedor de ayuda y el
  idioma español, como en ``main.py``. Las ventanas se crean SIN mostrarse.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))


@pytest.fixture(autouse=True)
def datos_temporales(tmp_path, monkeypatch):
	"""Redirige ``data`` a una carpeta temporal y silencia la voz."""
	carpeta = tmp_path / "data"
	monkeypatch.setenv("APP_DATA_DIR", str(carpeta))
	monkeypatch.delenv("APP_DEPURACION", raising=False)
	from app.ui.accesibilidad import voz

	dichos: list[str] = []
	# Se guarda lo que se habría dicho (para comprobar anuncios) y no se habla.
	monkeypatch.setattr(voz, "_emitir", lambda texto, interrumpir, canal="avisos": dichos.append(texto))
	monkeypatch.setattr(voz, "hablar", lambda texto, interrumpir=True, canal="avisos", sincrono=False, forzar=False: dichos.append(texto))
	monkeypatch.setattr(voz, "dichos_en_prueba", dichos, raising=False)
	yield carpeta
	# Hilos de un solo trabajo que escriben en ``data`` (p. ej. el conjunto «Música» de Metadatos,
	# 11.4): se esperan aquí, antes de devolver ``APP_DATA_DIR``; si no, alguno terminaba después y
	# escribía en la ``data`` real del proyecto (que se distribuye).
	import threading

	for hilo in threading.enumerate():
		if hilo is not threading.current_thread() and hilo.name in HILOS_QUE_ESCRIBEN_EN_DATA:
			hilo.join(10)


#: Hilos de complementos que terminan solos y pueden escribir en ``data``.
HILOS_QUE_ESCRIBEN_EN_DATA = frozenset({"zc-metadatos-inicio", "zc.portapapeles-arranque"})


@pytest.fixture(scope="session")
def app_wx():
	"""``wx.App`` compartida por todas las pruebas de interfaz."""
	wx = pytest.importorskip("wx")
	aplicacion = wx.App.Get() or wx.App(False)
	wx.HelpProvider.Set(wx.SimpleHelpProvider())
	idioma = wx.Locale(wx.LANGUAGE_SPANISH)
	yield aplicacion
	del idioma


@pytest.fixture(autouse=True)
def _sin_modales_reales(request, monkeypatch):
	"""Un ``ShowModal`` o ``wx.MessageBox`` real se vería en pantalla y colgaría las pruebas.

	Falla al momento con el título del cuadro. Las pruebas que lo necesitan
	sustituyen antes la función que lo abre (``monkeypatch.setattr``), o el
	propio ``ShowModal``. Las marcadas ``interfaz`` quedan fuera.
	"""
	if request.node.get_closest_marker("interfaz"):
		return
	try:
		import wx
	except ImportError:
		return

	def prohibido(dialogo, *args, **kwargs):
		raise RuntimeError(f"ShowModal real durante las pruebas: «{dialogo.GetTitle()}» ({request.node.nodeid})")

	def caja_prohibida(mensaje, titulo="", *args, **kwargs):
		raise RuntimeError(f"wx.MessageBox real durante las pruebas: «{titulo}» ({request.node.nodeid})")

	for nombre in ("Dialog", "MessageDialog", "FileDialog", "DirDialog", "TextEntryDialog", "SingleChoiceDialog"):
		clase = getattr(wx, nombre, None)
		if clase is not None and "ShowModal" in vars(clase):
			monkeypatch.setattr(clase, "ShowModal", prohibido)
	monkeypatch.setattr(wx, "MessageBox", caja_prohibida)


def procesar_eventos(condicion=lambda: False, segundos: float = 3.0) -> bool:
	"""Procesa eventos de wx hasta que se cumple ``condicion`` o pasa el tiempo.

	Sin ``MainLoop`` hay que activar un bucle de eventos a mano: ``wx.CallAfter``
	se atiende en ``ProcessPendingEvents`` y la destrucción diferida de las
	ventanas (``Destroy``) en ``ProcessIdle``.
	"""
	import wx

	bucle = wx.GUIEventLoop()
	activo = wx.EventLoopActivator(bucle)
	try:
		limite = time.monotonic() + segundos
		while time.monotonic() < limite:
			while bucle.Pending():
				bucle.Dispatch()
			wx.GetApp().ProcessPendingEvents()
			bucle.ProcessIdle()
			if condicion():
				return True
			time.sleep(0.01)
		return condicion()
	finally:
		del activo


# ── 2.0 (diseño 2.0, 18.1) ─────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def complementos_serie():
	"""El catálogo de las pruebas es el de la aplicación: núcleo y los 27 complementos de serie.

	Registra los marcadores una vez, sin importar código de ningún complemento ni leer ``data/``.
	"""
	from app.plugins import registro

	registro.vaciar()
	registro.registrar_serie()
	yield registro


@pytest.fixture
def registro_vacio(complementos_serie):
	"""Registro de complementos vacío para la prueba; al terminar vuelve a registrar la serie."""
	from app.plugins import registro

	registro.vaciar()
	yield registro
	registro.vaciar()
	registro.fijar_modo_desarrollo(False)
	registro.registrar_serie()


@pytest.fixture(scope="session", autouse=True)
def portapapeles_paciente():
	"""El portapapeles de Windows es de todo el equipo: otro programa (el historial de Windows,
	un gestor de contraseñas, otra sesión de pruebas) puede tenerlo abierto un momento.

	La aplicación espera 0,2 s (no debe dejar la interfaz parada); en las pruebas se espera
	hasta 10 s, para que una prueba no falle porque otro proceso lo usaba en ese instante.
	"""
	from app.services.windows import portapapeles

	anteriores = (portapapeles.REINTENTOS, portapapeles.PAUSA_REINTENTO)
	portapapeles.REINTENTOS, portapapeles.PAUSA_REINTENTO = 200, 0.05
	yield
	portapapeles.REINTENTOS, portapapeles.PAUSA_REINTENTO = anteriores


@pytest.fixture(autouse=True)
def bus_reiniciado():
	"""Bus de eventos nuevo en cada prueba (14.4): nada que emita una prueba llega a la siguiente."""
	from app.services import eventos

	yield eventos.reiniciar()
	eventos.reiniciar()
