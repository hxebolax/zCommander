# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""WebDAV nativo, Nextcloud Login Flow v2 y OAuth con servidores locales (diseño 2.0, 12.4, 12.5 y 12.13)."""

from __future__ import annotations

import datetime
import subprocess
import threading
import time
import urllib.parse

import pytest

from app.core import procesos
from app.plugins import api
from app.plugins.api import pruebas
from tests.plugins.nu.comun import (
	RCLONE,
	ServidorFalso,
	modulo,
	puerto_libre,
	requiere_rclone,
)


def _esperar_puerto(puerto: int, segundos: float = 15) -> None:
	import socket

	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		with socket.socket(socket.AF_INET6) as enchufe:
			if enchufe.connect_ex(("::1", puerto)) == 0:
				return
		time.sleep(0.1)
	raise AssertionError(f"nadie escucha en {puerto}")


@pytest.fixture
def servidor_webdav(tmp_path):
	"""``rclone serve webdav`` de una carpeta temporal con usuario y contraseña (en el Job Object)."""
	carpeta = tmp_path / "servido"
	carpeta.mkdir()
	puerto = puerto_libre()
	proceso = procesos.popen([str(RCLONE), "serve", "webdav", str(carpeta), "--addr", f"[::1]:{puerto}", "--user", "ana",
		"--pass", "clave", "--config", str(tmp_path / "vacia.conf")], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL)
	try:
		_esperar_puerto(puerto)
		yield f"http://[::1]:{puerto}/", carpeta
	finally:
		procesos.terminar_arbol(proceso)
		proceso.wait(10)
		procesos.gestor().soltar(proceso)


@pytest.mark.componentes
@requiere_rclone
def test_webdav_nativo_contra_rclone_serve_webdav(nubes, servidor_webdav):
	url, carpeta = servidor_webdav
	(carpeta / "existente.txt").write_text("ya estaba", encoding="utf-8")
	cuentas = modulo("cuentas")
	cuenta = cuentas.Cuenta(id="dav", nombre="Mi WebDAV", servicio="webdav_nativo", motor="webdav", url=url, usuario="ana")
	nubes.zc.secretos.guardar("webdav:dav:contrasena", "clave")
	nubes.cuentas.guardar(cuenta)
	proveedor, ruta = nubes.fabrica_nube("nube://dav/")
	assert ruta == "/" and proveedor.mostrar("/a") == "Mi WebDAV:\\a"
	assert {e.nombre for e in proveedor.listar("/")} == {"existente.txt"}
	proveedor.crear_carpeta("/docs")
	datos = b"contenido de prueba " * 1000
	with proveedor.abrir_escritura("/docs/subido.bin", len(datos)) as flujo:
		flujo.write(datos[:5000])
		flujo.write(datos[5000:])
	assert (carpeta / "docs" / "subido.bin").read_bytes() == datos
	with proveedor.abrir_escritura("/docs/troceado.bin") as flujo:   # sin tamaño: Transfer-Encoding troceado
		flujo.write(b"abc")
	assert (carpeta / "docs" / "troceado.bin").read_bytes() == b"abc"
	with proveedor.abrir_lectura("/docs/subido.bin") as flujo:
		assert flujo.read() == datos
	proveedor.renombrar("/docs/subido.bin", "/docs/renombrado.bin")
	assert (carpeta / "docs" / "renombrado.bin").is_file() and not (carpeta / "docs" / "subido.bin").exists()
	with pytest.raises(api.YaExiste):
		proveedor.renombrar("/docs/renombrado.bin", "/docs/troceado.bin")
	entrada = proveedor.info("/docs/renombrado.bin")
	assert entrada.tamano == len(datos) and entrada.modificado > 0
	proveedor.eliminar("/docs/renombrado.bin")
	assert not (carpeta / "docs" / "renombrado.bin").exists()
	with pytest.raises(api.ErrorAcceso):
		proveedor.eliminar("/docs")   # no está vacía
	proveedor.eliminar("/docs", recursivo=True)
	assert not (carpeta / "docs").exists()
	with pytest.raises(api.NoEncontrado):
		proveedor.listar("/no_existe")
	espacio = proveedor.espacio_libre("/")
	assert espacio is None or espacio[0] > 0
	assert nubes.comprobar(nubes.cuenta("dav")) is not None
	assert nubes.estado(nubes.cuenta("dav")) == "Conectada"


@pytest.mark.componentes
@requiere_rclone
def test_webdav_contrasena_mala_da_error_de_acceso(nubes, servidor_webdav):
	url, _carpeta = servidor_webdav
	cuentas = modulo("cuentas")
	nubes.cuentas.guardar(cuentas.Cuenta(id="malo", nombre="Malo", servicio="webdav_nativo", motor="webdav", url=url, usuario="ana"))
	nubes.zc.secretos.guardar("webdav:malo:contrasena", "otra")
	proveedor, _ruta = nubes.fabrica_nube("nube://malo/")
	with pytest.raises(api.ErrorAcceso):
		proveedor.listar("/")


@pytest.mark.componentes
@requiere_rclone
def test_webdav_https_con_certificado_propio_pide_aceptar_la_huella(nubes, tmp_path):
	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import ec
	from cryptography.x509.oid import NameOID

	clave = ec.generate_private_key(ec.SECP256R1())
	nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "::1")])
	ahora = datetime.datetime.now(datetime.UTC)
	certificado = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key())
		.serial_number(x509.random_serial_number()).not_valid_before(ahora - datetime.timedelta(days=1))
		.not_valid_after(ahora + datetime.timedelta(days=2)).sign(clave, hashes.SHA256()))
	(tmp_path / "cert.pem").write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
	(tmp_path / "clave.pem").write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
		serialization.NoEncryption()))
	carpeta = tmp_path / "seguro"
	carpeta.mkdir()
	(carpeta / "a.txt").write_text("a")
	puerto = puerto_libre()
	proceso = procesos.popen([str(RCLONE), "serve", "webdav", str(carpeta), "--addr", f"[::1]:{puerto}", "--cert",
		str(tmp_path / "cert.pem"), "--key", str(tmp_path / "clave.pem"), "--config", str(tmp_path / "vacia.conf")],
		stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	try:
		_esperar_puerto(puerto)
		webdav = modulo("webdav")
		cuentas = modulo("cuentas")
		nubes.cuentas.guardar(cuentas.Cuenta(id="nas", nombre="NAS", servicio="webdav_nativo", motor="webdav",
			url=f"https://[::1]:{puerto}/"))
		nubes.zc._decisor = pruebas.DecisorFalso([0])   # «No conectar»
		proveedor, _ruta = nubes.fabrica_nube("nube://nas/")
		with pytest.raises(webdav.ErrorHuella):
			proveedor.listar("/")
		nubes.zc._decisor = pruebas.DecisorFalso([1])   # «Aceptar esta huella»
		proveedor, _ruta = nubes.fabrica_nube("nube://nas/")
		assert [e.nombre for e in proveedor.listar("/")] == ["a.txt"]
		guardada = nubes.cuenta("nas").huella
		assert guardada == webdav.huella_certificado(certificado.public_bytes(serialization.Encoding.DER))
		proveedor, _ruta = nubes.fabrica_nube("nube://nas/")
		assert [e.nombre for e in proveedor.listar("/")] == ["a.txt"], "con la huella guardada ya no se pregunta"
	finally:
		procesos.terminar_arbol(proceso)
		proceso.wait(10)
		procesos.gestor().soltar(proceso)


def test_login_flow_v2_espera_404_y_recibe_la_contrasena_de_aplicacion(zc):
	nextcloud = modulo("nextcloud")
	consultas = {"n": 0}

	def manejar(metodo, ruta, cuerpo):
		if ruta == "/index.php/login/v2":
			return 200, {}, {"poll": {"token": "TOKEN-DE-PRUEBA", "endpoint": servidor.base + "/login/v2/poll"},
				"login": servidor.base + "/login/v2/flow/ABC"}
		if ruta == "/login/v2/poll":
			assert urllib.parse.parse_qs(cuerpo.decode())["token"] == ["TOKEN-DE-PRUEBA"]
			consultas["n"] += 1
			if consultas["n"] <= 2:
				return 404, {}, b"[]"
			return 200, {}, {"server": servidor.base, "loginName": "ana", "appPassword": "contrasena-app"}
		return 404, {}, b""

	servidor = ServidorFalso(manejar)
	try:
		inicio = nextcloud.iniciar(zc.red, servidor.base)
		assert inicio.login.endswith("/login/v2/flow/ABC")
		credenciales = nextcloud.esperar_credenciales(zc.red, inicio, intervalo_s=0.05)
	finally:
		servidor.cerrar()
	assert consultas["n"] >= 3   # 404 dos veces y después 200 (un corte de la red local puede añadir una consulta)
	assert credenciales.usuario == "ana" and credenciales.contrasena_app == "contrasena-app"
	assert credenciales.url_webdav == servidor.base + "/remote.php/dav/files/ana/"
	assert nextcloud.normalizar_servidor("nube.ejemplo.com/index.php/") == "https://nube.ejemplo.com"


def test_login_flow_v2_se_cancela(zc):
	nextcloud = modulo("nextcloud")
	servidor = ServidorFalso(lambda m, r, c: (404, {}, b""))
	cancelacion = threading.Event()
	cancelacion.set()
	try:
		inicio = nextcloud.InicioLogin(servidor.base + "/login", "t", servidor.base + "/poll")
		with pytest.raises(api.Cancelado):
			nextcloud.esperar_credenciales(zc.red, inicio, cancelacion, intervalo_s=0.05)
	finally:
		servidor.cerrar()


def _navegar(url: str, intentos: int = 6) -> None:
	"""Hace de navegador: sigue las redirecciones de la autorización (repite si la conexión se corta)."""
	import http.client

	for _ in range(10):
		partes = urllib.parse.urlsplit(url)
		for intento in range(intentos):
			try:
				conexion = http.client.HTTPConnection(partes.hostname, partes.port, timeout=15)   # ::1 o 127.0.0.1 (rclone)
				conexion.request("GET", partes.path + ("?" + partes.query if partes.query else ""))
				respuesta = conexion.getresponse()
				respuesta.read()
				siguiente = respuesta.getheader("Location")
				conexion.close()
				break
			except (ConnectionResetError, ConnectionRefusedError):
				if intento == intentos - 1:
					return
				time.sleep(0.2)
		if not siguiente:
			return
		url = siguiente


def _autorizar(nubes, url: str) -> None:
	"""Hace de persona en el navegador; si la vuelta a rclone (127.0.0.1:53682) se pierde por un corte, lo repite."""
	for _intento in range(5):
		_navegar(url)
		limite = time.monotonic() + 8
		while time.monotonic() < limite:
			if nubes.llamar("config/oauthstatus").get("status") != "running":
				return
			time.sleep(0.2)


def _esperar_53682_libre(segundos: float = 15) -> None:
	"""rclone cierra su servidor de autorización un poco después de recibir el código: hasta entonces el puerto fijo sigue ocupado."""
	import socket

	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		with socket.socket() as enchufe:
			if enchufe.connect_ex(("127.0.0.1", 53682)) != 0:
				return
		time.sleep(0.2)


@pytest.fixture
def servidor_oauth():
	"""Servidor OAuth falso: ``/authorize`` vuelve a rclone con un código y ``/token`` da el token."""
	_esperar_53682_libre()
	tokens: list[bytes] = []

	def manejar(metodo, ruta, cuerpo):
		partes = urllib.parse.urlsplit(ruta)
		if partes.path == "/authorize":
			consulta = urllib.parse.parse_qs(partes.query)
			destino = consulta["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": "CODIGO", "state": consulta["state"][0]})
			return 302, {"Location": destino}, b""
		if partes.path == "/token":
			tokens.append(cuerpo)
			return 200, {}, {"access_token": "AT-PRUEBA", "refresh_token": "RT-PRUEBA", "token_type": "Bearer", "expires_in": 3600}
		return 404, {}, b""

	servidor = ServidorFalso(manejar)
	servidor.tokens = tokens
	yield servidor
	servidor.cerrar()


def _parametros_oauth(servidor) -> dict[str, str]:
	return {"client_id": "cid", "client_secret": "csec", "auth_url": servidor.base + "/authorize", "token_url": servidor.base + "/token",
		"config_is_local": "true", "config_auth_no_browser": "true"}


@pytest.mark.componentes
@requiere_rclone
def test_oauth_con_servidor_falso_da_la_url_y_termina_con_token(nubes, servidor_oauth):
	servicio = modulo("servicio")
	alta = servicio.Alta(nubes, "drive_prueba", "drive", _parametros_oauth(servidor_oauth))
	paso = alta.empezar()
	assert paso.tipo == "oauth" and paso.url.startswith("http://127.0.0.1:53682/")
	_autorizar(nubes, paso.url)
	paso = alta.esperar(tiempo_max_s=60)
	preguntas = 0
	while paso.tipo == "pregunta":
		preguntas += 1
		assert paso.nombre and paso.opcion
		paso = alta.responder(paso.defecto or "false", paso)
	assert paso.tipo == "fin"
	assert servidor_oauth.tokens and b"CODIGO" in servidor_oauth.tokens[0]
	configuracion = nubes.llamar("config/get", name="drive_prueba")
	assert "AT-PRUEBA" in configuracion.get("token", "")
	assert "AT-PRUEBA" not in nubes.rutas.config.read_text(encoding="utf-8"), "el token nunca va en claro al disco"
	assert "drive_prueba" in nubes.remotos()


@pytest.mark.componentes
@requiere_rclone
def test_oauthstop_cancela_la_autorizacion(nubes, servidor_oauth):
	servicio = modulo("servicio")
	alta = servicio.Alta(nubes, "cancelada", "drive", _parametros_oauth(servidor_oauth))
	paso = alta.empezar()
	assert paso.tipo == "oauth"
	cancelacion = threading.Event()
	threading.Timer(0.5, cancelacion.set).start()
	with pytest.raises(api.Cancelado):
		alta.esperar(cancelacion, tiempo_max_s=30)
	estado = nubes.llamar("config/oauthstatus")
	assert estado.get("status") != "running"


@pytest.mark.componentes
@requiere_rclone
def test_pegar_token_desde_otro_equipo(nubes, servidor_oauth):
	servicio = modulo("servicio")
	parametros = _parametros_oauth(servidor_oauth)
	parametros["config_is_local"] = "false"
	parametros.pop("config_auth_no_browser")
	alta = servicio.Alta(nubes, "pegada", "drive", parametros)
	paso = alta.empezar()
	assert paso.tipo == "pregunta" and paso.es_token
	assert "rclone authorize" in paso.orden_authorize()
	token = '{"access_token":"AT-PEGADO","token_type":"Bearer","refresh_token":"RT","expiry":"2030-01-01T00:00:00Z"}'
	paso = alta.responder(token, paso)
	while paso.tipo == "pregunta":
		paso = alta.responder(paso.defecto or "false", paso)
	assert paso.tipo == "fin"
	assert "AT-PEGADO" in nubes.llamar("config/get", name="pegada").get("token", "")


@pytest.mark.componentes
@requiere_rclone
def test_volver_a_autorizar_con_config_refresh_token(nubes, servidor_oauth):
	servicio = modulo("servicio")
	cuentas = modulo("cuentas")
	alta = servicio.Alta(nubes, "reautorizar", "drive", _parametros_oauth(servidor_oauth))
	paso = alta.empezar()
	_autorizar(nubes, paso.url)
	paso = alta.esperar(tiempo_max_s=60)
	while paso.tipo == "pregunta":
		paso = alta.responder(paso.defecto or "false", paso)
	cuenta = cuentas.Cuenta(id="reautorizar", nombre="Drive", servicio="drive")
	_esperar_53682_libre()
	reconexion = nubes.reconectar(cuenta)
	paso = reconexion.empezar()
	while paso.tipo == "pregunta":   # rclone confirma que se quiere renovar el token
		paso = reconexion.responder("true" if paso.es_booleana else (paso.defecto or "true"), paso)
	assert paso.tipo == "oauth"
	_autorizar(nubes, paso.url)
	paso = reconexion.esperar(tiempo_max_s=60)
	while paso.tipo == "pregunta":
		paso = reconexion.responder(paso.defecto or "false", paso)
	assert paso.tipo == "fin"
	assert len(servidor_oauth.tokens) == 2, "se pidió un token nuevo"
