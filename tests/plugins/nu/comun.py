# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Apoyo de las pruebas del bloque NU (zc.nubes, diseño 2.0, 12.13 y 18.2).

Sin cuentas reales: el ``rclone.exe`` de ``data/bin`` contra remotos ``memory``
y ``local``, servidores ``rclone serve`` en carpetas temporales y servidores
falsos de ``http.server`` en ::1. Cada prueba tiene su ``data`` temporal
(``APP_DATA_DIR``), su almacén de secretos y su rcd, que se para al terminar.

En este equipo, ``http.server`` en HTTP/1.0 corta a veces la conexión antes de
que el cliente lea la respuesta (WinError 10054): los servidores falsos usan
HTTP/1.1 con ``Content-Length`` y escuchan en ``::1``.
"""

from __future__ import annotations

import http.server
import importlib
import json
import socket
import threading
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parents[3]
CARPETA = RAIZ / "plugins" / "nubes"
RCLONE = RAIZ / "data" / "bin" / "rclone" / "rclone.exe"

requiere_rclone = pytest.mark.skipif(not RCLONE.is_file(), reason="Falta data/bin/rclone/rclone.exe")


def modulo(nombre: str) -> Any:
	"""Un módulo del complemento ya importado por la activación (``zcplugins.zc__nubes.<nombre>``)."""
	return importlib.import_module(f"zcplugins.zc__nubes.{nombre}")


def crear_memoria(nubes, nombre: str = "mem", nombre_visible: str = "Memoria") -> Any:
	"""Una cuenta ``memory`` de rclone (con su remoto en ``rclone.conf``) para las pruebas."""
	cuentas = modulo("cuentas")
	nubes.llamar("config/create", name=nombre, type="memory", parameters={}, opt={"nonInteractive": True, "obscure": True})
	cuenta = cuentas.Cuenta(id=nombre, nombre=nombre_visible, servicio="memory", papelera=False)
	nubes.cuentas.guardar(cuenta)
	return cuenta


def crear_local(nubes, carpeta: Path, nombre: str = "disco") -> Any:
	"""Una cuenta de tipo ``alias`` sobre una carpeta local (para probar ``about`` y el espacio)."""
	cuentas = modulo("cuentas")
	nubes.llamar("config/create", name=nombre, type="alias", parameters={"remote": str(carpeta).replace("\\", "/")},
		opt={"nonInteractive": True, "obscure": True})
	cuenta = cuentas.Cuenta(id=nombre, nombre="Disco de prueba", servicio="alias", papelera=False)
	nubes.cuentas.guardar(cuenta)
	return cuenta


def puerto_libre() -> int:
	"""Puerto libre en ``::1`` (en este equipo 127.0.0.1 corta a veces las conexiones TCP de los servidores de prueba)."""
	with socket.socket(socket.AF_INET6) as enchufe:
		enchufe.bind(("::1", 0))
		return enchufe.getsockname()[1]


class _ServidorV6(http.server.ThreadingHTTPServer):
	address_family = socket.AF_INET6


class ServidorFalso:
	"""``http.server`` en ``::1`` en un hilo, HTTP/1.1; ``manejar(metodo, ruta, cuerpo) -> (estado, cabeceras, cuerpo)``."""

	def __init__(self, manejar) -> None:
		exterior = self

		class Manejador(http.server.BaseHTTPRequestHandler):
			protocol_version = "HTTP/1.1"

			def log_message(self, *args) -> None:
				return None

			def _responder(self, metodo: str) -> None:
				largo = int(self.headers.get("Content-Length") or 0)
				cuerpo = self.rfile.read(largo) if largo else b""
				exterior.peticiones.append((metodo, self.path, cuerpo))
				estado, cabeceras, respuesta = manejar(metodo, self.path, cuerpo)
				if isinstance(respuesta, (dict, list)):
					respuesta = json.dumps(respuesta).encode("utf-8")
					cabeceras = {"Content-Type": "application/json", **cabeceras}
				self.send_response(estado)
				for clave, valor in cabeceras.items():
					self.send_header(clave, valor)
				self.send_header("Content-Length", str(len(respuesta)))
				self.end_headers()
				self.wfile.write(respuesta)

			def finish(self) -> None:
				# Cierre «con espera»: sin él, Windows corta a veces con RST y el cliente no llega a leer la respuesta.
				super().finish()
				try:
					self.connection.shutdown(socket.SHUT_WR)
					self.connection.settimeout(1)
					while self.connection.recv(4096):
						pass
				except OSError:
					pass

			def do_GET(self) -> None:  # noqa: N802 - nombre de http.server
				self._responder("GET")

			def do_POST(self) -> None:  # noqa: N802
				self._responder("POST")

		self.peticiones: list[tuple[str, str, bytes]] = []
		self.servidor = _ServidorV6(("::1", 0), Manejador)
		self.servidor.handle_error = lambda *_args: None   # un cliente que corta no es un fallo de la prueba
		self.puerto = self.servidor.server_address[1]
		self.base = f"http://[::1]:{self.puerto}"
		self._hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)
		self._hilo.start()

	def cerrar(self) -> None:
		self.servidor.shutdown()
		self.servidor.server_close()
