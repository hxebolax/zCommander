# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Red con la biblioteca estándar (diseño 2.0, 14.9 y 18.2)."""

from __future__ import annotations

import socket
import ssl
import urllib.error

import pytest

from app.core import red


def test_redactar_url_oculta_fichas():
	texto = red.redactar_url("https://ana:secreto@ejemplo.com/api?token=abc123&x=1&access_token=zzz")
	assert "abc123" not in texto and "zzz" not in texto and "secreto" not in texto
	assert "token=***" in texto and "x=1" in texto


@pytest.mark.parametrize(("error", "categoria", "reintentar"), [
	(urllib.error.URLError(socket.timeout("tiempo")), red.TIEMPO, True),
	(urllib.error.URLError(socket.gaierror(11001, "no existe")), red.CONEXION, True),
	(urllib.error.URLError(ssl.SSLCertVerificationError("certificado")), red.CERTIFICADO, False),
	(urllib.error.URLError(ConnectionRefusedError("rechazada")), red.CONEXION, True),
	(urllib.error.HTTPError("https://x", 404, "No", {}, None), red.HTTP, False),
	(urllib.error.HTTPError("https://x", 503, "No", {}, None), red.HTTP, True),
	(red.ErrorHTTP(red.CANCELADO, "Cancelado"), red.CANCELADO, False),
])
def test_clasificar_error(error, categoria, reintentar):
	info = red.clasificar_error(error)
	assert info.categoria == categoria
	assert info.reintentar == reintentar
	assert info.mensaje and info.mensaje[0].isupper()


def test_solo_https_salvo_la_propia_maquina():
	red.comprobar_url("https://ejemplo.com/x")
	red.comprobar_url("http://127.0.0.1:8000/x")
	with pytest.raises(red.ErrorHTTP):
		red.comprobar_url("http://ejemplo.com/x")


@pytest.mark.parametrize(("origen", "destino", "se_sigue"), [
	("https://ejemplo.com/a", "https://cdn.ejemplo.com/b", True),
	("https://ejemplo.com/a", "http://127.0.0.1:8000/b", False),  # 2.0.1: remoto → http local, no
	("https://ejemplo.com/a", "http://localhost/b", False),
	("https://ejemplo.com/a", "http://[::1]/b", False),
	("http://127.0.0.1:8000/a", "http://localhost:8000/b", True),  # pruebas y servidores locales
	("http://127.0.0.1:8000/a", "http://ejemplo.com/b", False),
])
def test_redirecciones_solo_https_y_http_local_desde_local(origen, destino, se_sigue):
	import urllib.request

	manejador = red._SinBajarAHttp()
	peticion = urllib.request.Request(origen)
	if se_sigue:
		assert manejador.redirect_request(peticion, None, 302, "Found", {}, destino).full_url == destino
	else:
		with pytest.raises(red.ErrorHTTP):
			manejador.redirect_request(peticion, None, 302, "Found", {}, destino)


def test_respuesta_texto_y_json():
	respuesta = red.RespuestaRed(200, {"Content-Type": "application/json; charset=utf-8"}, '{"a": "ñ"}'.encode(), "https://x")
	assert respuesta.json() == {"a": "ñ"}
	assert "ñ" in respuesta.texto()
