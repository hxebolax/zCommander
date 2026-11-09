# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Simulador DSM (diseño 2.0, 13.9; synology.md 7): datos realistas del DS220+, validación, sesión, modos y /__control."""

from __future__ import annotations

import http.client
import json
import subprocess
import sys
from urllib.parse import urlencode

import pytest

from .conftest import CARPETA, RAIZ


def _post(simulador, ruta: str, campos: dict | None = None, cuerpo: bytes | None = None, metodo: str = "POST", cabeceras: dict | None = None):
	conexion = http.client.HTTPConnection("127.0.0.1", simulador.puerto, timeout=5)
	try:
		datos = cuerpo if cuerpo is not None else urlencode(campos or {}).encode()
		conexion.request(metodo, ruta, datos, {"Content-Type": "application/x-www-form-urlencoded", **(cabeceras or {})})
		respuesta = conexion.getresponse()
		return respuesta.status, json.loads(respuesta.read() or b"{}")
	finally:
		conexion.close()


def _entrar(simulador, cuenta: str = "demo", contrasena: str = "demo") -> dict:
	_estado, datos = _post(simulador, "/webapi/entry.cgi", {"api": "SYNO.API.Auth", "version": 7, "method": "login", "account": cuenta,
		"passwd": contrasena, "enable_syno_token": "yes", "format": "sid"})
	return datos


def _llamar(simulador, sesion: dict, api: str, metodo: str, version: int = 1, **params):
	campos = {"api": api, "version": version, "method": metodo, "_sid": sesion["sid"], **params}
	return _post(simulador, "/webapi/entry.cgi", campos, cabeceras={"X-SYNO-TOKEN": sesion["synotoken"]})[1]


def test_escucha_solo_en_127_0_0_1(arrancar):
	simulador = arrancar()
	assert simulador.url.startswith("http://127.0.0.1:")
	assert simulador._servidor.server_address[0] == "127.0.0.1"


def test_catalogo_real_de_841_api(arrancar):
	simulador = arrancar()
	_estado, datos = _post(simulador, "/webapi/entry.cgi", {"api": "SYNO.API.Info", "version": 1, "method": "query", "query": "all"})
	real = json.loads((RAIZ / "adjuntos" / "synology" / "api_info_5000.json").read_text(encoding="utf-8"))["data"] \
		if (RAIZ / "adjuntos" / "synology" / "api_info_5000.json").is_file() else None
	assert datos["success"] and len(datos["data"]) == 841
	copia = json.loads((CARPETA / "simulador" / "datos" / "api_info.json").read_text(encoding="utf-8"))["data"]
	assert datos["data"] == copia
	if real is not None:
		assert copia == real
	assert "SYNO.DownloadStation.Task" not in datos["data"] and "SYNO.Backup.Task" not in datos["data"]


def test_datos_realistas_del_ds220_plus(arrancar):
	simulador = arrancar()
	sesion = _entrar(simulador)["data"]
	info = _llamar(simulador, sesion, "SYNO.Core.System", "info", 3)["data"]
	assert (info["model"], info["cpu_series"], info["ram_size"]) == ("DS220+", "J4025", 10240)
	assert info["firmware_ver"] == "DSM 7.3.2-86009 Update 5"
	dsm = _llamar(simulador, sesion, "SYNO.DSM.Info", "getinfo", 2)["data"]
	assert dsm["version_string"] == "DSM 7.3.2-86009 Update 5"
	almacen = _llamar(simulador, sesion, "SYNO.Storage.CGI.Storage", "load_info")["data"]
	volumen = almacen["volumes"][0]
	assert int(volumen["size"]["total"]) == 3838417727488
	assert int(volumen["size"]["used"]) == 245 * 1024 ** 3
	paquetes = {p["id"] for p in _llamar(simulador, sesion, "SYNO.Core.Package", "list", 2)["data"]["packages"]}
	assert paquetes == {"AIConsole", "ActiveInsight", "ContainerManager", "FileStation", "HybridShare", "Node.js_v20", "OAuthService",
		"Python2", "QuickConnect", "SMBService", "ScsiTarget", "SecureSignIn", "Spreadsheet", "StorageManager", "SupportService",
		"SynoAnalytics", "SynoFinder", "SynologyApplicationService", "SynologyDrive", "SynologyPhotos", "USBCopy", "UniversalViewer",
		"WebDAVServer"}
	contenedores = _llamar(simulador, sesion, "SYNO.Docker.Container", "list", 1, limit=-1)["data"]["containers"]
	assert {c["name"] for c in contenedores} == {"jellyfin", "pihole", "vaultwarden", "homeassistant"}
	assert simulador.estado.contar_entradas() >= 200


@pytest.mark.parametrize(("campos", "codigo"), [
	({"version": 1, "method": "query"}, 101),
	({"api": "SYNO.DownloadStation.Task", "version": 1, "method": "list"}, 102),
	({"api": "SYNO.DSM.Info", "version": 1, "method": "getinfo"}, 104),
	({"api": "SYNO.Core.Upgrade.Patch", "version": 1, "method": "upload"}, 103),
])
def test_validacion_101_102_103_104(arrancar, campos, codigo):
	simulador = arrancar()
	sesion = _entrar(simulador)["data"]
	campos = dict(campos, _sid=sesion["sid"])
	_estado, datos = _post(simulador, "/webapi/entry.cgi", campos, cabeceras={"X-SYNO-TOKEN": sesion["synotoken"]})
	assert datos == {"success": False, "error": {"code": codigo}}


def test_sesion_exige_sid_y_synotoken(arrancar):
	simulador = arrancar()
	sesion = _entrar(simulador)["data"]
	assert _post(simulador, "/webapi/entry.cgi", {"api": "SYNO.DSM.Info", "version": 2, "method": "getinfo"})[1]["error"]["code"] == 119
	sin_token = _post(simulador, "/webapi/entry.cgi", {"api": "SYNO.DSM.Info", "version": 2, "method": "getinfo", "_sid": sesion["sid"]})
	assert sin_token[1]["error"]["code"] == 105
	assert _llamar(simulador, sesion, "SYNO.DSM.Info", "getinfo", 2)["success"]


def test_modo_lectura_116_y_diario(arrancar):
	simulador = arrancar("lectura")
	sesion = _entrar(simulador)["data"]
	datos = _llamar(simulador, sesion, "SYNO.Core.Package.Control", "start", id='"Python2"')
	assert datos == {"success": False, "error": {"code": 116}}
	assert simulador.diario[-1]["resultado"] == "rechazada"
	assert next(p for p in simulador.estado.datos["paquetes"] if p["id"] == "Python2")["estado"] == "stop"


def test_modo_simular_responde_y_no_cambia(arrancar):
	simulador = arrancar("simular")
	sesion = _entrar(simulador)["data"]
	datos = _llamar(simulador, sesion, "SYNO.Core.Package.Control", "start", id='"Python2"')
	assert datos["success"] and datos["data"]["status"] == "running"
	entrada = simulador.diario[-1]
	assert (entrada["api"], entrada["method"], entrada["aplicado"], entrada["params"]["id"]) == (
		"SYNO.Core.Package.Control", "start", False, "Python2")
	assert next(p for p in simulador.estado.datos["paquetes"] if p["id"] == "Python2")["estado"] == "stop"


def test_modo_escritura_cambia_el_estado(arrancar):
	simulador = arrancar("escritura")
	sesion = _entrar(simulador)["data"]
	assert _llamar(simulador, sesion, "SYNO.Core.Package.Control", "start", id='"Python2"')["success"]
	assert next(p for p in simulador.estado.datos["paquetes"] if p["id"] == "Python2")["estado"] == "running"
	assert simulador.diario[-1]["aplicado"] is True


def test_compuesta_entry_request(arrancar):
	simulador = arrancar()
	sesion = _entrar(simulador)["data"]
	compuesta = json.dumps([{"api": "SYNO.DSM.Info", "method": "getinfo", "version": 2},
		{"api": "SYNO.Core.Package.Control", "method": "start", "version": 1, "id": "Python2"}])
	assert _llamar(simulador, sesion, "SYNO.Entry.Request", "request", compound=compuesta)["error"]["code"] == 116
	solo_lectura = json.dumps([{"api": "SYNO.DSM.Info", "method": "getinfo", "version": 2}, {"api": "SYNO.Nada", "method": "get", "version": 1}])
	datos = _llamar(simulador, sesion, "SYNO.Entry.Request", "request", compound=solo_lectura)["data"]
	assert datos["has_fail"] is True
	assert datos["result"][0]["success"] and datos["result"][1]["error"]["code"] == 102


def test_control_solo_local_y_funciona(arrancar):
	simulador = arrancar("simular")
	estado, datos = _post(simulador, "/__control/estado", cuerpo=b"", metodo="GET")
	assert estado == 200 and datos["modo"] == "simular"
	assert _post(simulador, "/__control/modo", cuerpo=json.dumps({"modo": "escritura"}).encode())[1] == {"modo": "escritura"}
	assert simulador.modo == "escritura"
	_post(simulador, "/__control/fallos", cuerpo=json.dumps({"http_502": 1}).encode())
	conexion = http.client.HTTPConnection("127.0.0.1", simulador.puerto, timeout=5)
	conexion.request("POST", "/webapi/entry.cgi", urlencode({"api": "SYNO.API.Info", "version": 1, "method": "query"}))
	assert conexion.getresponse().status == 502
	conexion.close()
	assert _post(simulador, "/__control/diario", cuerpo=b"", metodo="GET")[1] == {"diario": []}


def test_cuenta_sin_privilegios_da_105(arrancar):
	simulador = arrancar()
	sesion = _entrar(simulador, "lectura", "lectura")["data"]
	assert _llamar(simulador, sesion, "SYNO.Core.User", "list")["error"]["code"] == 105
	assert _llamar(simulador, sesion, "SYNO.FileStation.List", "list_share", 2)["success"]


def test_programa_suelto_muestra_la_ayuda():
	"""``python -I plugins/synology/simulador/servidor.py --help`` funciona sin zCommander (arranque como paquete propio)."""
	resultado = subprocess.run([sys.executable, "-I", str(CARPETA / "simulador" / "servidor.py"), "--help"], capture_output=True,
		text=True, encoding="utf-8", timeout=60)
	assert resultado.returncode == 0, resultado.stderr
	assert "127.0.0.1" in resultado.stdout
