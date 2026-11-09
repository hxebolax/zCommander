# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas mínimas de metadatos y etiquetas de audio (diseño 2.0, 11.4 y 18.2).

Los MP3 y FLAC se generan aquí sin herramientas externas: tramas MPEG de
silencio y un FLAC con solo su bloque STREAMINFO, que mutagen lee y etiqueta.
"""

from __future__ import annotations

import inspect
import os
import struct
import threading
import time
from pathlib import Path

import pytest

from .p1_comun import cargar, config_limpia, entrada, interfaz_real, modulo, revisar  # noqa: F401 - fixtures


def mp3(ruta, tramas: int = 40):
	"""MPEG-1 capa III, 128 kb/s, 44,1 kHz, estéreo conjunto: 417 bytes por trama."""
	trama = b"\xff\xfb\x90\x64" + bytes(413)
	ruta.write_bytes(trama * tramas)
	return ruta


def flac(ruta, segundos: int = 5):
	frecuencia, canales, bits = 44100, 2, 16
	valor = (frecuencia << 44) | ((canales - 1) << 41) | ((bits - 1) << 36) | (frecuencia * segundos)
	streaminfo = struct.pack(">HH", 4096, 4096) + bytes(6) + valor.to_bytes(8, "big") + bytes(16)
	ruta.write_bytes(b"fLaC" + bytes([0x80]) + len(streaminfo).to_bytes(3, "big") + streaminfo)
	return ruta


def _ctx():
	from app.plugins.api import ContextoEjecucion, pruebas

	return ContextoEjecucion(threading.Event(), pruebas.DecisorFalso())


def test_un_mp3_y_un_flac_con_etiquetas_conocidas_dan_sus_columnas(tmp_path):
	zc, _p = cargar("metadatos")
	etiquetas = modulo("metadatos", "etiquetas")
	cancion = mp3(tmp_path / "cancion.mp3")
	disco = flac(tmp_path / "disco.flac")
	datos = {"artista": "Ana", "titulo": "Hola", "album": "Primero", "pista": "3/12", "anio": "2024", "genero": "Pop"}
	etiquetas.escribir(str(cancion), datos)
	etiquetas.escribir(str(disco), datos | {"artista": "Luis"})
	assert zc.columna("artista", entrada(cancion)) == "Ana"
	assert zc.columna("titulo", entrada(cancion)) == "Hola"
	assert zc.columna("album", entrada(cancion)) == "Primero"
	assert zc.columna("pista", entrada(cancion)) == "3"
	assert zc.columna("anio", entrada(cancion)) == "2024"
	assert zc.columna("genero", entrada(cancion)) == "Pop"
	assert zc.columna("bitrate", entrada(cancion)) == "128"
	assert zc.columna("frecuencia", entrada(cancion)) == "44100"
	assert zc.columna("portada", entrada(cancion)) == "No"
	assert zc.columna("duracion", entrada(cancion)) == "0:01"
	assert zc.columna("artista", entrada(disco)) == "Luis"
	assert zc.columna("duracion", entrada(disco)) == "0:05"
	assert zc.columna("canales", entrada(disco)) == "2"
	lineas = zc.instancia._lineas_info(entrada(disco), None)
	assert "Artista: Luis" in lineas and "Canales: 2 (estéreo)" in lineas


def test_editar_dos_archivos_con_un_campo_sin_cambio_no_lo_toca(tmp_path, app_wx):
	zc, _p = cargar("metadatos")
	etiquetas = modulo("metadatos", "etiquetas")
	dialogos = modulo("metadatos", "dialogos")
	operacion = modulo("metadatos", "operacion")
	from app.ui import api_ui

	uno, dos = mp3(tmp_path / "uno.mp3"), mp3(tmp_path / "dos.mp3")
	etiquetas.escribir(str(uno), {"artista": "Ana", "titulo": "Primera"})
	etiquetas.escribir(str(dos), {"artista": "Ana", "titulo": "Segunda"})
	fecha = os.stat(uno).st_mtime - 3600
	os.utime(uno, (fecha, fecha))
	dialogo = dialogos.DialogoEditar(api_ui, None, ["uno.mp3", "dos.mp3"], None)
	try:
		assert dialogo.campos["titulo"].GetValue() == "(sin cambio)"
		dialogo.campos["artista"].SetValue("Bea")
		cambios = dialogo.cambios()
	finally:
		dialogo.dialogo.Destroy()
	assert cambios == {"artista": "Bea"}
	op = operacion.OperacionEtiquetas("Editar", None, [(str(r), lambda ruta: etiquetas.escribir(ruta, cambios)) for r in (uno, dos)],
		operacion.Copias(zc.datos))
	op.proveedor = _proveedor_local()
	op.ejecutar(_ctx())
	assert etiquetas.leer(str(uno))["titulo"] == "Primera" and etiquetas.leer(str(dos))["titulo"] == "Segunda"
	assert etiquetas.leer(str(uno))["artista"] == "Bea" and etiquetas.leer(str(dos))["artista"] == "Bea"
	assert os.stat(uno).st_mtime == pytest.approx(fecha, abs=1), "conserva la fecha del archivo"
	# Un paso «restaurar» por archivo (API 1.1); las copias van en datos/deshacer, nunca junto al archivo,
	# y al cerrar zCommander se borran las de la sesión.
	assert op.deshacer is not None and [p.tipo for p in op.deshacer.pasos] == ["restaurar", "restaurar"]
	assert not [n for n in os.listdir(tmp_path) if n.startswith(".zc-")]
	assert all(Path(p.antes).parent == Path(zc.datos) / "deshacer" for p in op.deshacer.pasos)
	assert operacion.Copias(zc.datos).limpiar() == 2
	assert not any(Path(p.antes).exists() for p in op.deshacer.pasos)


def test_deshacer_devuelve_las_etiquetas_anteriores(tmp_path, monkeypatch):
	zc, _p = cargar("metadatos")
	etiquetas = modulo("metadatos", "etiquetas")
	operacion = modulo("metadatos", "operacion")
	from app.services.operaciones.deshacer import RegistroDeshacer
	from app.services.windows import papelera

	cancion = mp3(tmp_path / "cancion.mp3")
	etiquetas.escribir(str(cancion), {"titulo": "Antes"})
	op = operacion.OperacionEtiquetas("Editar", _proveedor_local(), [(str(cancion), lambda r: etiquetas.escribir(r, {"titulo": "Después"}))],
		operacion.Copias(zc.datos))
	op.ejecutar(_ctx())
	assert etiquetas.leer(str(cancion))["titulo"] == "Después"
	enviados: list[str] = []
	monkeypatch.setattr(papelera, "enviar", lambda rutas: enviados.extend(rutas) or [os.remove(r) for r in rutas])
	resultado = RegistroDeshacer().deshacer(op.deshacer)
	assert not resultado.omitidos and resultado.hechos == 1
	assert etiquetas.leer(str(cancion))["titulo"] == "Antes"
	assert not enviados, "restaurar no manda nada a la papelera"
	assert not [n for n in os.listdir(tmp_path) if n.startswith(".zc-")], "nada queda junto al archivo"


def test_deshacer_no_pisa_un_archivo_cambiado_despues(tmp_path):
	zc, _p = cargar("metadatos")
	etiquetas = modulo("metadatos", "etiquetas")
	operacion = modulo("metadatos", "operacion")
	from app.services.operaciones.deshacer import RegistroDeshacer

	cancion = mp3(tmp_path / "cancion.mp3")
	etiquetas.escribir(str(cancion), {"titulo": "Antes"})
	op = operacion.OperacionEtiquetas("Editar", _proveedor_local(), [(str(cancion), lambda r: etiquetas.escribir(r, {"titulo": "Después"}))],
		operacion.Copias(zc.datos))
	op.ejecutar(_ctx())
	with open(cancion, "ab") as archivo:  # otro programa lo cambia después (otro tamaño)
		archivo.write(bytes(4096))
	resultado = RegistroDeshacer().deshacer(op.deshacer)
	assert resultado.omitidos == [str(cancion)] and resultado.hechos == 0
	assert os.path.getsize(cancion) > 4096


def test_mascaras_de_renombrado_y_las_de_la_1x_siguen(tmp_path):
	zc, _p = cargar("metadatos")
	etiquetas = modulo("metadatos", "etiquetas")
	from app.services.vfs import resolver

	cancion = mp3(tmp_path / "x.mp3")
	etiquetas.escribir(str(cancion), {"pista": "3", "titulo": "Hola", "artista": "Ana/Bea"})
	proveedor = resolver.proveedor_local()
	assert zc.renombrado.evaluar("[MP3:pista] - [MP3:titulo]", entrada(cancion), proveedor) == "03 - Hola"
	assert zc.renombrado.evaluar("[MP3:artista]", entrada(cancion), proveedor) == "Ana_Bea"
	hora = time.strftime("%H.%M.%S", time.localtime(os.stat(cancion).st_mtime))
	assert zc.renombrado.evaluar("[t]", entrada(cancion), proveedor) == hora


def test_etiquetas_desde_el_nombre_con_una_mascara():
	cargar("metadatos")
	etiquetas = modulo("metadatos", "etiquetas")
	assert etiquetas.desde_nombre("[pista] - [artista] - [titulo]", "01 - Ana - Canción.mp3") == {
		"pista": "01", "artista": "Ana", "titulo": "Canción"}
	assert etiquetas.desde_nombre("[pista] - [artista] - [titulo]", "Sin guiones.mp3") is None
	assert etiquetas.desde_nombre("[*] [titulo]", "Pista 07 Lluvia.mp3") == {"titulo": "07 Lluvia"}
	with pytest.raises(etiquetas.ErrorEtiquetas):
		etiquetas.compilar_mascara("sin campos")


def test_numerar_quitar_y_portada(tmp_path):
	zc, _p = cargar("metadatos")
	etiquetas = modulo("metadatos", "etiquetas")
	cancion = mp3(tmp_path / "a.mp3")
	disco = flac(tmp_path / "b.flac")
	png = b"\x89PNG\r\n\x1a\n" + bytes(32)
	for ruta in (cancion, disco):
		etiquetas.escribir(str(ruta), {"artista": "Ana", "pista": "1/2"})
		etiquetas.poner_portada(str(ruta), png)
		assert etiquetas.leer(str(ruta))["portada"] == "si"
		assert etiquetas.leer_portada(str(ruta)) == (png, "image/png")
		etiquetas.quitar(str(ruta))
		assert etiquetas.leer(str(ruta))["artista"] == "" and etiquetas.leer(str(ruta))["portada"] == "no"


def test_exportar_la_lista_de_pistas(tmp_path):
	zc, _p = cargar("metadatos")
	etiquetas = modulo("metadatos", "etiquetas")
	operacion = modulo("metadatos", "operacion")
	cancion = mp3(tmp_path / "a.mp3")
	etiquetas.escribir(str(cancion), {"artista": "Ana", "titulo": "Hola", "pista": "1"})
	destino = tmp_path / "lista.csv"
	op = operacion.OperacionExportar(_proveedor_local(), [str(cancion)], str(destino), etiquetas.leer)
	op.ejecutar(_ctx())
	texto = destino.read_text(encoding="utf-8-sig")
	assert texto.splitlines()[1] == "a.mp3;1;Ana;Hola;;;;0:01"


def test_la_funcion_exportada_tiene_la_firma_del_contrato(tmp_path):
	zc, _p = cargar("metadatos")
	from app.plugins import registro

	exportado = registro.exportados("zc.metadatos")
	assert list(inspect.signature(exportado["leer_etiquetas"]).parameters) == ["proveedor", "ruta"]
	cancion = mp3(tmp_path / "a.mp3")
	modulo("metadatos", "etiquetas").escribir(str(cancion), {"artista": "Ana"})
	datos = exportado["leer_etiquetas"](_proveedor_local(), str(cancion))
	assert {"artista", "titulo", "album", "pista", "anio", "genero", "duracion_s"} <= set(datos)
	assert datos["artista"] == "Ana" and float(datos["duracion_s"]) > 0
	assert exportado["leer_etiquetas"](None, str(tmp_path / "no-existe.mp3")) == {}


@pytest.mark.usefixtures("interfaz_real")
def test_editor_y_desde_nombre_pasan_revisar_teclado():
	zc, _p = cargar("metadatos")
	revisar(zc.instancia.ventanas_para_revisar(None))


def _proveedor_local():
	from app.services.vfs import resolver

	return resolver.proveedor_local()
