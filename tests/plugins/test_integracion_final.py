# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Peticiones de los bloques atendidas en la integración final (API 1.1 y núcleo).

- Un ``[[esquemas]]`` activa su complemento al abrir una dirección con su prefijo (P3, NS).
- El evento que activa un complemento (``evento:<nombre>``) le llega (P3).
- La caché de columnas externas se puede olvidar (P3, NU).
- El motor de búsqueda de un complemento entrega direcciones de un proveedor (NS, NU).
- Asociaciones «Abrir» de fábrica (P1, P4), el visor sin «Página N» repetida (P2),
  ``contexto_de_prueba`` con anuncios (P3) y ``validar_plugin`` con las pruebas de serie (P1 a P5).
"""

from __future__ import annotations

import sys
import threading
from concurrent.futures import Future
from pathlib import Path

from app.plugins import api, cargador, registro
from app.services.vfs import resolver

from ..conftest import RAIZ
from .test_n2_cargador import _crear, entorno

#: Fixtures que se usan desde aquí (la de ``test_n2_cargador``: cargador con planificador falso).
FIXTURES = (entorno,)

_ESQUEMA = '''
	import sys

	from app.plugins import api


	class Complemento(api.Complemento):
		def activar(self, zc):
			from app.services.vfs import resolver

			zc.vfs.esquema("pruebaesq", lambda texto: (resolver.proveedor_local(), "C:\\\\"))
'''

_EVENTO = '''
	from app.plugins import api

	RECIBIDOS = []


	class Complemento(api.Complemento):
		def activar(self, zc):
			zc.eventos.suscribir("al_cambiar_carpeta", lambda **datos: RECIBIDOS.append(datos.get("ruta")))
'''


def test_un_esquema_activa_su_complemento_desde_un_hilo(entorno):
	_crear(entorno.serie / "esquema", "prueba.esquema", _ESQUEMA, extra='[[esquemas]]\nprefijo = "pruebaesq"\nnombre = "Prueba"\n')
	entorno.nuevo()
	assert registro.complemento_de_esquema("pruebaesq") == "prueba.esquema"
	assert registro.estado("prueba.esquema") == registro.EstadoComplemento.REGISTRADO
	resultado: list = []

	def abrir() -> None:
		try:
			resultado.append(resolver.abrir_ruta("pruebaesq://algo"))
		except Exception as error:  # noqa: BLE001 - la prueba lo comprueba abajo
			resultado.append(error)

	hilo = threading.Thread(target=abrir)
	hilo.start()
	assert entorno.planificador.bombear(lambda: not hilo.is_alive())
	hilo.join(5)
	assert resultado and not isinstance(resultado[0], Exception), resultado
	assert resultado[0][1] == "C:\\"
	assert registro.estado("prueba.esquema") == registro.EstadoComplemento.ACTIVO


def test_un_esquema_sin_complemento_sigue_sin_admitirse(entorno):
	entorno.nuevo()
	try:
		resolver.abrir_ruta("nadie://x")
	except api.NoAdmitido:
		pass
	else:
		raise AssertionError("debía lanzar NoAdmitido")
	assert cargador.activar_por_esquema("nadie") is False


def test_el_evento_que_activa_el_complemento_le_llega_una_vez(entorno):
	from app.services import eventos

	_crear(entorno.serie / "evento", "prueba.evento", _EVENTO, extra='activacion = ["evento:al_cambiar_carpeta"]\n')
	activo = entorno.nuevo()
	activo.activar_al_arrancar()
	eventos.bus().emitir("al_cambiar_carpeta", ruta="C:\\primera")
	assert entorno.planificador.bombear(lambda: "zcplugins.prueba__evento" in sys.modules
		and sys.modules["zcplugins.prueba__evento"].RECIBIDOS == ["C:\\primera"])
	eventos.bus().emitir("al_cambiar_carpeta", ruta="C:\\segunda")
	entorno.planificador.bombear(segundos=0.3)
	assert sys.modules["zcplugins.prueba__evento"].RECIBIDOS == ["C:\\primera", "C:\\segunda"]


def test_olvidar_columnas_por_complemento_ruta_y_carpeta(registro_vacio):
	cache = registro._r.cache_columnas
	cache.update({
		("zc.notas:comentario", "C:\\a\\uno.txt", 1, 0.0): "viejo",
		("zc.notas:comentario", "C:\\a\\dos.txt", 1, 0.0): "viejo",
		("zc.otro:col", "C:\\a\\uno.txt", 1, 0.0): "suyo",
		("zc.notas:comentario", "C:\\b\\tres.txt", 1, 0.0): "viejo",
	})
	assert registro.olvidar_columnas("zc.notas", ["c:\\A\\UNO.txt"]) == 1
	assert registro.olvidar_columnas(carpeta="C:\\a\\") == 2
	assert list(cache) == [("zc.notas:comentario", "C:\\b\\tres.txt", 1, 0.0)]
	api.Anfitrion("zc.notas", Path(".")).columnas.invalidar()
	assert not cache


def test_contexto_de_prueba_apunta_los_anuncios_en_el_anfitrion(tmp_path):
	zc = api.pruebas.AnfitrionFalso("prueba.ejemplo", tmp_path)
	ctx = api.pruebas.contexto_de_prueba(anfitrion=zc)
	ctx.anunciar("Hecho", api.RESULTADO)
	assert zc.anuncios == [("Hecho", api.RESULTADO)]
	api.pruebas.contexto_de_prueba().anunciar("Solo al registro")  # sin anfitrión, como antes


def test_motor_de_busqueda_con_direcciones_de_un_proveedor(tmp_path, monkeypatch):
	from app.services import busqueda

	(tmp_path / "nota.txt").write_text("hola", encoding="utf-8")
	local = resolver.proveedor_local()
	monkeypatch.setitem(resolver._esquemas, "pruebabus", lambda texto: (local, str(tmp_path / texto.split("://", 1)[1])))
	resuelto: Future = Future()
	resuelto.set_result(True)
	monkeypatch.setattr(cargador, "asegurar_activo", lambda _id: resuelto)

	def motor(criterios, entregar, cancelacion) -> None:
		entregar("pruebabus://nota.txt")
		entregar("pruebabus://no_existe.txt")
		entregar(str(tmp_path / "nota.txt"))

	registro.fijar_funcion("busqueda", "prueba.motor:todo", motor)
	try:
		resultados: list = []
		estadisticas = busqueda.buscar([], busqueda.Criterios(motor="prueba.motor:todo"), al_resultado=resultados.append)
	finally:
		registro._funciones("busqueda").pop("prueba.motor:todo", None)
	assert estadisticas.encontrados == 2
	assert [r.entrada.nombre for r in resultados] == ["nota.txt", "nota.txt"]
	assert resultados[0].ruta_local is None and resultados[1].ruta_local == str(tmp_path / "nota.txt")


def test_asociaciones_de_fabrica(tmp_path):
	from app.core import paths
	from app.plugins import config_plugins
	from app.services import asociaciones

	assert asociaciones.orden_para("secreto.zcc", "abrir") == "zc:zc.cifrado:descifrar"
	assert asociaciones.orden_para("musica.mp3", "abrir") is None
	asociaciones.guardar([asociaciones.Regla("*.zcc", abrir="notepad.exe %P")])
	assert asociaciones.orden_para("secreto.zcc", "abrir") == "notepad.exe %P", "la regla de la persona gana"
	asociaciones.guardar([])
	paths.ruta_config_plugins().mkdir(parents=True, exist_ok=True)
	config_plugins.registro().de("zc.reproductor").establecer("ajustes.formatos_intro", "*.mp3;*.m4b")
	try:
		assert asociaciones.orden_para("musica.mp3", "abrir") == "zc:zc.reproductor:reproducir"
		assert asociaciones.orden_para("musica.ogg", "abrir") is None
	finally:
		config_plugins.registro().declarar("zc.reproductor", config_plugins.registro().declaraciones("zc.reproductor"))


def test_visor_no_repite_la_pagina_si_el_titulo_ya_la_dice():
	from app.ui.ventanas import visor

	documento = api.Documento("Libro", (api.Seccion("Página 2 de 80", pagina=2, texto="uno"),
		api.Seccion("Introducción", pagina=3, texto="dos")))
	texto = visor.texto_de_documento(documento)
	assert texto.count("Página 2") == 1
	assert "Página 3\n\nIntroducción" in texto


def test_validar_plugin_encuentra_las_pruebas_de_los_de_serie():
	from tools import validar_plugin

	rutas, raiz = validar_plugin.pruebas_de(RAIZ / "plugins" / "cifrado")
	assert raiz == RAIZ and rutas == [RAIZ / "tests" / "plugins" / "cifrado"]
	rutas, raiz = validar_plugin.pruebas_de(RAIZ / "plugins" / "metadatos")
	assert raiz == RAIZ and rutas == [RAIZ / "tests" / "plugins" / "test_p1_metadatos.py"]
	rutas, raiz = validar_plugin.pruebas_de(RAIZ / "plugins" / "nubes")
	assert raiz == RAIZ / "plugins" / "nubes" and rutas == [RAIZ / "plugins" / "nubes" / "pruebas"]


def test_ayuda_de_un_complemento_con_pagina(tmp_path):
	from types import SimpleNamespace

	from app.ui.interfaz_anfitrion import ruta_ayuda

	(tmp_path / "doc" / "es").mkdir(parents=True)
	(tmp_path / "doc" / "es" / "leeme.md").write_text("# Ayuda", encoding="utf-8")
	(tmp_path / "doc" / "es" / "google-drive.md").write_text("# Drive", encoding="utf-8")
	registrado = SimpleNamespace(id="prueba.ayuda", carpeta=tmp_path, manifiesto=SimpleNamespace(datos={}))
	assert ruta_ayuda(registrado).name == "leeme.md"
	assert ruta_ayuda(registrado, "google-drive").name == "google-drive.md"
	assert ruta_ayuda(registrado, "no-existe").name == "leeme.md"
	assert ruta_ayuda(registrado, "../../fuera").name == "leeme.md"

