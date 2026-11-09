# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Descargas reanudables y verificadas (diseño 2.0, 14.9 y 18.2), con un ``http.server`` local."""

from __future__ import annotations

import hashlib
import http.server
import threading

import pytest

from app.core import descargas, red

DATOS = bytes(range(256)) * 40  # 10 KB
PETICIONES: list[str] = []


class _Manejador(http.server.BaseHTTPRequestHandler):
	def do_GET(self):  # noqa: N802 - API de http.server
		rango = self.headers.get("Range")
		PETICIONES.append(rango or "")
		if rango:
			inicio = int(rango.split("=")[1].split("-")[0])
			if inicio >= len(DATOS):
				self.send_response(416)
				self.end_headers()
				return
			cuerpo = DATOS[inicio:]
			self.send_response(206)
			self.send_header("Content-Range", f"bytes {inicio}-{len(DATOS) - 1}/{len(DATOS)}")
		else:
			cuerpo = DATOS
			self.send_response(200)
		self.send_header("Content-Length", str(len(cuerpo)))
		self.end_headers()
		self.wfile.write(cuerpo)

	def log_message(self, *_args):
		return None


@pytest.fixture
def servidor():
	PETICIONES.clear()
	httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Manejador)
	hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
	hilo.start()
	yield f"http://127.0.0.1:{httpd.server_address[1]}/archivo.bin"
	httpd.shutdown()
	httpd.server_close()


CONFIG = red.ConfiguracionRed("zCommander", "prueba", proxy="ninguno")


def _reintentar(funcion, veces: int = 80):
	"""En este equipo la conexión local se corta a veces (WinError 10054 de un filtro de red): la descarga
	es reanudable, así que se vuelve a llamar como haría la persona con «Reintentar»."""
	for _intento in range(veces - 1):
		try:
			return funcion()
		except red.ErrorHTTP as error:
			if error.categoria != red.CONEXION:
				raise
	return funcion()


def test_reanuda_un_parcial_con_range(servidor, tmp_path):
	destino = tmp_path / "archivo.bin"
	(tmp_path / "archivo.bin.parcial").write_bytes(DATOS[:1000])
	suma = hashlib.sha256(DATOS).hexdigest()
	final = _reintentar(lambda: descargas.descargar(CONFIG, servidor, destino, sha256=suma, tamano=len(DATOS)))
	assert final.read_bytes() == DATOS
	assert PETICIONES[0] == "bytes=1000-"
	assert all(p.startswith("bytes=") for p in PETICIONES), "siempre se reanuda, nunca se empieza de cero"
	assert not (tmp_path / "archivo.bin.parcial").exists()


def test_rechaza_un_sha256_distinto(servidor, tmp_path):
	with pytest.raises(red.ErrorHTTP) as error:
		_reintentar(lambda: descargas.descargar(CONFIG, servidor, tmp_path, sha256="0" * 64))
	assert "suma" in error.value.mensaje
	assert not list(tmp_path.iterdir()), "lo que no coincide se borra"


def test_destino_carpeta_y_progreso(servidor, tmp_path):
	avances = []
	final = _reintentar(lambda: descargas.descargar(CONFIG, servidor, tmp_path, al_progresar=lambda h, t: avances.append((h, t))))
	assert final == tmp_path / "archivo.bin"
	assert avances[-1] == (len(DATOS), len(DATOS))
