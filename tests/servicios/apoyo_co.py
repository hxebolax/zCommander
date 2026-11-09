# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Apoyo de las pruebas del bloque CO: un ``data/bin`` falso, paquetes de prueba y un servidor HTTP local.

- Nada sale a Internet: el servidor escucha en ``::1`` (en este equipo el
  bucle 127.0.0.1 corta conexiones de más de 1 o 2 KB; ``::1`` no) e imita la
  API de GitHub (``/repos/<r>/releases/...``), el índice de MSYS2 y las descargas.
- Los «programas» de los componentes de prueba son archivos de texto: el
  lanzador falso (``lanzar_falso``) devuelve su contenido como salida, y
  termina con código 1 si dicen ``FALLA`` (o ``FALLA_EN_SU_SITIO`` fuera de
  ``data/temp``). Así cada prueba decide si la versión nueva funciona.
"""

from __future__ import annotations

import hashlib
import http.server
import io
import json
import socket
import tarfile
import threading
import zipfile
from pathlib import Path

from app.core import procesos, red
from app.services.componentes import fichas
from app.services.componentes.estado import Entorno
from app.services.componentes.instalar import GestorComponentes

CONFIG = red.ConfiguracionRed("zCommander", "prueba", proxy="ninguno")
ESPERAS_CORTAS = (0.05, 0.05, 0.1)


def sha(datos: bytes) -> str:
	return hashlib.sha256(datos).hexdigest()


def lanzar_falso(argumentos, carpeta=None, tiempo_s=60, cancelacion=None, **_opciones) -> procesos.ResultadoPrograma:
	texto = Path(argumentos[0]).read_text(encoding="utf-8")
	en_temporal = "nuevo" in Path(argumentos[0]).parts  # data/temp/componentes/<id>/nuevo: antes de instalar
	if "FALLA_EN_SU_SITIO" in texto and not en_temporal:
		return procesos.ResultadoPrograma(1, b"", b"roto", False)
	if "FALLA" in texto and "FALLA_EN_SU_SITIO" not in texto:
		return procesos.ResultadoPrograma(1, b"", b"roto", False)
	return procesos.ResultadoPrograma(0, texto.encode("utf-8"), b"", False)


def ficha_demo(version: str = "1.0.0", **cambios) -> dict:
	"""Componente «demo» al estilo de rclone (GitHub con SHA256SUMS)."""
	ficha = {
		"id": "demo", "nombre": "Demo", "version": version, "licencia": "MIT", "dueno": "nucleo", "carpeta": "demo",
		"licencias": ["LICENCIA.txt"],
		"fuente": {"tipo": "github", "repositorio": "prueba/demo", "etiqueta": "", "rama": "", "patron_asset": "demo-v{version}.zip",
			"version_desde": "tag_name", "extraer": {"demo-v{version}/demo.exe": "demo.exe"}},
		"verificacion": {"tipo": "sha256sums", "asset": "SHA256SUMS"},
		"prueba": {"ejecutable": "demo.exe", "argumentos": ["version"], "salida_contiene": "demo v{version}", "tiempo_s": 5},
		"en_uso": {"procesos": ["demo.exe"], "detener": False, "esperar_s": 0, "al_reiniciar": False},
		"opcional": False, "actualizable": True,
	}
	ficha.update(cambios)
	return ficha


def crear_entorno(raiz: Path, fichas_base: list[dict] | None = None, archivos: dict[str, dict[str, str]] | None = None) -> Entorno:
	"""``data/bin`` falso con sus carpetas, ``linea_base.json`` y ``componentes.json`` con las sumas reales."""
	entorno = Entorno(raiz / "bin", raiz / "temp", raiz / "config")
	for carpeta in (entorno.bin, entorno.temp, entorno.config):
		carpeta.mkdir(parents=True, exist_ok=True)
	fichas_base = fichas_base or [ficha_demo()]
	archivos = archivos or {"demo": {"demo.exe": "demo v1.0.0", "LICENCIA.txt": "MIT"}}
	base = []
	for ficha in fichas_base:
		carpeta = entorno.bin / ficha["carpeta"]
		for nombre, contenido in archivos.get(ficha["id"], {}).items():
			(carpeta / nombre).parent.mkdir(parents=True, exist_ok=True)
			(carpeta / nombre).write_text(contenido, encoding="utf-8")
		base.append(dict(ficha, archivos=fichas.sumas_de_carpeta(carpeta)))
	fichas.escribir(entorno.linea_base, {"formato": 1, "aplicacion": "1.0.0", "componentes": base})
	fichas.escribir(entorno.instalados, {"formato": 1, "componentes": [fichas.sin_campos_de_base(f) for f in base]})
	return entorno


def gestor(entorno: Entorno, **opciones) -> GestorComponentes:
	g = GestorComponentes(entorno, CONFIG)
	g.opciones_instalador = {"lanzar": lanzar_falso, "esperas": ESPERAS_CORTAS, "buscar_procesos": lambda _n: [], **opciones}
	return g


def zip_de(miembros: dict[str, str]) -> bytes:
	memoria = io.BytesIO()
	with zipfile.ZipFile(memoria, "w") as zf:
		for nombre, contenido in miembros.items():
			zf.writestr(nombre, contenido)
	return memoria.getvalue()


def tar_zst_de(miembros: dict[str, str]) -> bytes:
	memoria = io.BytesIO()
	with tarfile.open(fileobj=memoria, mode="w:zst") as tar:
		for nombre, contenido in miembros.items():
			datos = contenido.encode("utf-8")
			info = tarfile.TarInfo(nombre)
			info.size = len(datos)
			tar.addfile(info, io.BytesIO(datos))
	return memoria.getvalue()


def siete_z_de(miembros: dict[str, str], carpeta: Path) -> bytes:
	import py7zr

	origen = carpeta / "origen-7z"
	for nombre, contenido in miembros.items():
		(origen / nombre).parent.mkdir(parents=True, exist_ok=True)
		(origen / nombre).write_text(contenido, encoding="utf-8")
	destino = carpeta / "paquete.7z"
	with py7zr.SevenZipFile(destino, "w") as sz:
		for nombre in miembros:
			sz.write(origen / nombre, nombre)
	return destino.read_bytes()


def indice_msys2(paquetes: dict[str, tuple[str, str, int]]) -> bytes:
	"""Índice ``.db`` (tar.zst) con un ``desc`` por paquete: ``{nombre: (versión, sha256, tamaño)}``."""
	miembros = {}
	for nombre, (version, suma, tamano) in paquetes.items():
		miembros[f"{nombre}-{version}/desc"] = (
			f"%FILENAME%\n{nombre}-{version}-any.pkg.tar.zst\n\n%NAME%\n{nombre}\n\n%VERSION%\n{version}\n\n"
			f"%CSIZE%\n{tamano}\n\n%SHA256SUM%\n{suma}\n\n")
	return tar_zst_de(miembros)


class _Servidor6(http.server.ThreadingHTTPServer):
	address_family = socket.AF_INET6
	daemon_threads = True


class ServidorPrueba:
	"""Servidor HTTP en ``::1`` con rutas fijas: ``rutas["/camino"] = (estado, cuerpo)``."""

	def __init__(self) -> None:
		self.rutas: dict[str, tuple[int, bytes]] = {}
		self.peticiones: list[str] = []
		rutas, peticiones = self.rutas, self.peticiones

		class Manejador(http.server.BaseHTTPRequestHandler):
			def do_GET(self):  # noqa: N802 - API de http.server
				peticiones.append(self.path)
				estado, cuerpo = rutas.get(self.path, (404, b"no"))
				self.send_response(estado)
				self.send_header("Content-Length", str(len(cuerpo)))
				self.end_headers()
				self.wfile.write(cuerpo)

			def log_message(self, *_args):
				return None

		self.httpd = _Servidor6(("::1", 0), Manejador)
		self.base = f"http://[::1]:{self.httpd.server_address[1]}"
		threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

	def poner(self, camino: str, cuerpo: bytes | str | dict | list, estado: int = 200) -> str:
		if isinstance(cuerpo, (dict, list)):
			cuerpo = json.dumps(cuerpo)
		if isinstance(cuerpo, str):
			cuerpo = cuerpo.encode("utf-8")
		self.rutas[camino] = (estado, cuerpo)
		return self.base + camino

	def publicar_github(self, repositorio: str, etiqueta: str, assets: dict[str, bytes], *, latest: bool = True,
			digest: bool = True, fechas: dict[str, str] | None = None) -> dict:
		"""Publicación con sus assets descargables; devuelve el JSON de la API."""
		lista = []
		for nombre, datos in assets.items():
			url = self.poner(f"/descargas/{repositorio}/{etiqueta}/{nombre}", datos)
			asset = {"name": nombre, "size": len(datos), "browser_download_url": url,
				"updated_at": (fechas or {}).get(nombre, "2026-11-01T10:00:00Z")}
			if digest:
				asset["digest"] = "sha256:" + sha(datos)
			lista.append(asset)
		publicacion = {"tag_name": etiqueta, "body": "Arreglos varios.", "html_url": "https://example.invalid/notas", "assets": lista}
		camino = f"/repos/{repositorio}/releases/" + ("latest" if latest else f"tags/{etiqueta}")
		self.poner(camino, publicacion)
		return publicacion

	def cerrar(self) -> None:
		self.httpd.shutdown()
		self.httpd.server_close()
