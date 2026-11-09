# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas mínimas de imágenes (diseño 2.0, 11.11 y 18.2).

El JPEG con EXIF se genera aquí: wx.Image da la imagen y la prueba le añade
un segmento APP1 con un TIFF hecho a mano (cámara, fecha, exposición y GPS).
"""

from __future__ import annotations

import io
import json
import struct
import threading
from types import SimpleNamespace

import pytest

from app.plugins import api

from .p1_comun import InterfazPrueba, cargar, config_limpia, entrada, interfaz_real, modulo, revisar  # noqa: F401 - fixtures


def _tiff_exif() -> bytes:
	def entradas(lista):
		return struct.pack("<H", len(lista)) + b"".join(struct.pack("<HHI", t, ti, c) + v for t, ti, c, v in lista) + struct.pack("<I", 0)

	def largo(n: int) -> bytes:
		return struct.pack("<I", n)

	def racionales(*pares) -> bytes:
		return b"".join(struct.pack("<II", a, b) for a, b in pares)

	ifd0 = entradas([
		(0x010F, 2, 6, largo(74)), (0x0110, 2, 14, largo(80)), (0x0112, 3, 1, struct.pack("<HH", 1, 0)),
		(0x8769, 4, 1, largo(94)), (0x8825, 4, 1, largo(152)),
	]) + b"Canon\x00" + b"Canon EOS 80D\x00"
	exif = entradas([(0x829A, 5, 1, largo(144)), (0x9003, 2, 20, largo(124))]) + b"2024:05:01 12:30:15\x00" + racionales((1, 250))
	gps = entradas([
		(1, 2, 2, b"N\x00\x00\x00"), (2, 5, 3, largo(206)), (3, 2, 2, b"W\x00\x00\x00"), (4, 5, 3, largo(230)),
	]) + racionales((40, 1), (25, 1), (0, 1)) + racionales((3, 1), (42, 1), (0, 1))
	tiff = b"II*\x00" + largo(8) + ifd0 + exif + gps
	assert len(tiff) == 254
	return tiff


def _jpeg_con_exif(ruta, app_wx):
	import wx

	imagen = wx.Image(64, 48)
	imagen.SetRGB(wx.Rect(0, 0, 64, 48), 200, 30, 30)
	salida = io.BytesIO()
	assert imagen.SaveFile(salida, wx.BITMAP_TYPE_JPEG)
	datos = salida.getvalue()
	tiff = _tiff_exif()
	app1 = b"\xff\xe1" + struct.pack(">H", 2 + 6 + len(tiff)) + b"Exif\x00\x00" + tiff
	ruta.write_bytes(datos[:2] + app1 + datos[2:])
	return ruta


def test_un_jpeg_con_exif_conocido_da_fecha_y_dimensiones(tmp_path, app_wx):
	zc, _p = cargar("imagenes")
	exif = modulo("imagenes", "exif")
	foto = _jpeg_con_exif(tmp_path / "foto.jpg", app_wx)
	info = exif.informacion(str(foto))
	assert (info.formato, info.ancho, info.alto) == ("JPEG", 64, 48)
	assert info.exif["fecha"] == "2024-05-01 12:30:15"
	assert info.exif["camara"] == "Canon EOS 80D"
	assert info.exif["gps"] == pytest.approx((40.41667, -3.7), abs=1e-4)
	assert zc.columna("dimensiones", entrada(foto)) == "64 × 48"
	assert zc.columna("fecha_toma", entrada(foto)) == "2024-05-01 12:30"
	assert zc.columna("camara", entrada(foto)) == "Canon EOS 80D"
	lineas = exif.lineas(info)
	assert "Dimensiones: 64 × 48 píxeles, 0 megapíxeles, horizontal" in lineas
	assert "Exposición: 1/250 s" in lineas
	assert "Ubicación GPS: 40,41667 norte, 3,7 oeste" in lineas


def test_dimensiones_de_otros_formatos(tmp_path, app_wx):
	import wx

	cargar("imagenes")
	exif = modulo("imagenes", "exif")
	for tipo, extension, nombre in ((wx.BITMAP_TYPE_PNG, ".png", "PNG"), (wx.BITMAP_TYPE_BMP, ".bmp", "BMP"),
			(wx.BITMAP_TYPE_TIFF, ".tif", "TIFF")):
		ruta = tmp_path / f"imagen{extension}"
		assert wx.Image(30, 20).SaveFile(str(ruta), tipo)
		info = exif.informacion(str(ruta))
		assert (info.formato, info.ancho, info.alto) == (nombre, 30, 20)
	# GIF y WebP: solo la cabecera (wx no guarda GIF de color verdadero).
	assert exif.dimensiones(b"GIF89a" + struct.pack("<HH", 30, 20) + bytes(8))[:3] == ("GIF", 30, 20)
	webp = b"RIFF" + bytes(4) + b"WEBPVP8X" + bytes(8) + (29).to_bytes(3, "little") + (19).to_bytes(3, "little")
	assert exif.dimensiones(webp)[:3] == ("WebP", 30, 20)


def test_la_mascara_exif_fecha_renombra_como_se_espera(tmp_path, app_wx):
	zc, _p = cargar("imagenes")
	from app.services.vfs import resolver

	foto = _jpeg_con_exif(tmp_path / "IMG_0001.jpg", app_wx)
	proveedor = resolver.proveedor_local()
	assert zc.renombrado.evaluar("[EXIF:fecha] [EXIF:hora] [N]", entrada(foto), proveedor) == "2024-05-01 12.30.15 IMG_0001"
	assert zc.renombrado.evaluar("[EXIF:camara]-[EXIF:ancho]x[EXIF:alto]", entrada(foto), proveedor) == "Canon EOS 80D-64x48"


def test_quitar_el_gps_sin_recomprimir(tmp_path, app_wx):
	import wx

	zc, _p = cargar("imagenes")
	exif = modulo("imagenes", "exif")
	operaciones = modulo("imagenes", "operaciones")
	from app.plugins.api import ContextoEjecucion, pruebas
	from app.services.vfs import resolver

	foto = _jpeg_con_exif(tmp_path / "foto.jpg", app_wx)
	antes = foto.read_bytes()
	op = operaciones.OperacionQuitarGps("Quitar", resolver.proveedor_local(), [str(foto)])
	op.ejecutar(ContextoEjecucion(threading.Event(), pruebas.DecisorFalso()))
	despues = foto.read_bytes()
	assert len(despues) == len(antes)
	info = exif.informacion(str(foto))
	assert "gps" not in info.exif and "gps_presente" not in info.exif
	assert info.exif["fecha"] == "2024-05-01 12:30:15" and info.exif["camara"] == "Canon EOS 80D"
	inicio_imagen = antes.index(b"\xff\xdb")
	assert despues[inicio_imagen:] == antes[inicio_imagen:], "los datos de la imagen no cambian"
	assert wx.Image(str(foto)).IsOk()
	assert exif.quitar_gps(despues) is None, "una segunda vez no hay nada que quitar"


def test_convertir_redimensionar_y_girar(tmp_path, app_wx):
	import wx

	cargar("imagenes")
	operaciones = modulo("imagenes", "operaciones")
	from app.plugins.api import ContextoEjecucion, pruebas
	from app.services.vfs import resolver

	origen = tmp_path / "grande.png"
	assert wx.Image(400, 200).SaveFile(str(origen), wx.BITMAP_TYPE_PNG)
	destino = tmp_path / "salida" / "grande.jpg"
	destino.parent.mkdir()
	opciones = operaciones.OpcionesConversion(formato="jpeg", ancho_maximo=100, giro=90, calidad=80)
	op = operaciones.OperacionConvertir("Convertir", resolver.proveedor_local(), [(str(origen), str(destino))], opciones)
	op.ejecutar(ContextoEjecucion(threading.Event(), pruebas.DecisorFalso()))
	assert not op.errores
	imagen = wx.Image(str(destino))
	assert (imagen.GetWidth(), imagen.GetHeight()) == (100, 200)


class _Servidor:
	"""Servidor HTTP mínimo en ::1 que responde como Ollama a ``POST /api/generate``.

	Con un socket propio y no con ``http.server``: tras responder espera a que el
	cliente cierre antes de cerrar él (en este Windows, ``http.server`` cierra con
	bytes sin leer y a veces el cliente recibe un reinicio de la conexión). Escucha
	en ::1 y no en 127.0.0.1, que en este equipo corta a veces las conexiones de los
	servidores de prueba (WinError 10054, como vio NU), y atiende varias conexiones
	por si el cliente tiene que repetir la petición.
	"""

	def __init__(self) -> None:
		import socket

		self.recibido: list[dict] = []
		self._socket = socket.create_server(("::1", 0), family=socket.AF_INET6)
		self.puerto = self._socket.getsockname()[1]
		self._hilo = threading.Thread(target=self._atender, daemon=True)
		self._hilo.start()

	def _atender(self) -> None:
		while True:
			try:
				conexion, _direccion = self._socket.accept()
			except OSError:
				return  # cerrado
			try:
				self._una(conexion)
			except OSError:
				continue  # conexión cortada: el cliente lo repite

	def _una(self, conexion) -> None:
		import socket

		with conexion:
			datos = b""
			while b"\r\n\r\n" not in datos:
				datos += conexion.recv(65536)
			cabecera, _separador, cuerpo = datos.partition(b"\r\n\r\n")
			lineas = cabecera.decode("latin-1").split("\r\n")
			largo = next(int(l.split(":", 1)[1]) for l in lineas if l.lower().startswith("content-length:"))
			while len(cuerpo) < largo:
				cuerpo += conexion.recv(65536)
			self.recibido.append({"ruta": lineas[0].split(" ")[1], "cuerpo": json.loads(cuerpo)})
			respuesta = json.dumps({"response": "Un cuadrado rojo sobre fondo liso."}).encode("utf-8")
			conexion.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
				+ f"Content-Length: {len(respuesta)}\r\n\r\n".encode("ascii") + respuesta)
			conexion.shutdown(socket.SHUT_WR)
			conexion.settimeout(5)
			while conexion.recv(65536):
				pass

	def cerrar(self) -> None:
		self._socket.close()

def test_con_un_servidor_de_descripcion_falso_local_la_descripcion_llega(tmp_path, app_wx):
	zc, _p = cargar("imagenes")
	describir = modulo("imagenes", "describir")
	procesado = modulo("imagenes", "procesado")
	foto = _jpeg_con_exif(tmp_path / "foto.jpg", app_wx)
	servidor = _Servidor()
	try:
		url = f"http://[::1]:{servidor.puerto}"
		direccion, cuerpo = describir.peticion_ollama(url, "llava", procesado.jpeg_reducido(str(foto)), "es", "breve")
		for intento in range(3):
			try:
				respuesta = zc.red.enviar(direccion, cuerpo, tiempo_s=10)
				break
			except api.ErrorRed:
				if intento == 2:
					raise
		assert describir.leer_respuesta("ollama", respuesta.cuerpo) == "Un cuadrado rojo sobre fondo liso."
	finally:
		servidor.cerrar()
	peticion = servidor.recibido[-1]
	assert peticion["ruta"] == "/api/generate" and peticion["cuerpo"]["model"] == "llava"
	assert peticion["cuerpo"]["images"] and "español" in peticion["cuerpo"]["prompt"]
	_, abierta = describir.peticion_openai("https://api.example.com/v1", "gpt-4o-mini", b"x", "es", "detallada")
	assert abierta["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
	assert describir.leer_respuesta("openai", json.dumps({"choices": [{"message": {"content": "Hola"}}]})) == "Hola"


def test_sin_servicio_la_orden_explica_como_configurarlo(tmp_path, app_wx):
	from app.plugins import api
	from app.plugins.api import pruebas

	zc, _p = cargar("imagenes")
	foto = _jpeg_con_exif(tmp_path / "foto.jpg", app_wx)
	mensajes: list[str] = []

	def elegir_opcion(mensaje, titulo, opciones, padre=None):
		mensajes.append(mensaje)
		return 0

	interfaz = InterfazPrueba(SimpleNamespace(elegir_opcion=elegir_opcion))
	api.fijar_interfaz(interfaz)
	try:
		zc.ejecutar("describir", pruebas.contexto_de_prueba(activo=pruebas.PanelFalso([entrada(foto)])))
	finally:
		api.fijar_interfaz(None)
	assert len(mensajes) == 1 and "Preferencias, Complementos, Imágenes" in mensajes[0]
	assert interfaz.preferencias == ["zc.imagenes"], "«Abrir las preferencias» lleva a la página del complemento"


@pytest.mark.usefixtures("interfaz_real")
def test_visor_y_convertir_pasan_revisar_teclado():
	zc, _p = cargar("imagenes")
	ventanas = modulo("imagenes", "ventanas")
	revisar(zc.instancia.ventanas_para_revisar(None), ventanas.TECLAS_PROPIAS)
