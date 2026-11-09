# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque D: proveedor SFTP contra un servidor paramiko falso con los archivos en memoria.

El servidor escucha en ``::1`` (ver la nota de ``test_d_ftp.py`` sobre IPv4
en el entorno de pruebas). Sus archivos viven en un diccionario, así los
permisos Unix (644...) se pueden comprobar también en Windows.
"""

from __future__ import annotations

import io
import socket
import stat as stat_mod
import threading
import time

import pytest

paramiko = pytest.importorskip("paramiko")

from app.core.tareas import ejecutor_directo  # noqa: E402
from app.services import conexiones  # noqa: E402
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar  # noqa: E402
from app.services.operaciones.gestor import GestorOperaciones  # noqa: E402
from app.services.operaciones.modelo import Estado  # noqa: E402
from app.services.vfs import base, resolver  # noqa: E402
from app.services.vfs import sftp as mod_sftp  # noqa: E402
from app.services.vfs.local import ProveedorLocal  # noqa: E402
from app.services.vfs.sftp import ProveedorSFTP  # noqa: E402
from tests.servicios.test_d_ftp import ConfigFalsa, DecisorFalso, SecretosMemoria  # noqa: E402

HOST = "::1"
USUARIO, CLAVE = "ana", "secreta"


# ── Servidor falso ───────────────────────────────────────────────────────────

class Nodo:
	def __init__(self, carpeta: bool, modo: int, datos: bytes = b"") -> None:
		self.carpeta = carpeta
		self.modo = modo
		self.datos = bytearray(datos)
		self.mtime = time.time()

	def atributos(self, nombre: str) -> paramiko.SFTPAttributes:
		atributos = paramiko.SFTPAttributes()
		atributos.filename = nombre
		atributos.st_mode = (stat_mod.S_IFDIR if self.carpeta else stat_mod.S_IFREG) | self.modo
		atributos.st_size = 0 if self.carpeta else len(self.datos)
		atributos.st_mtime = int(self.mtime)
		atributos.st_atime = int(self.mtime)
		return atributos


class SistemaMemoria:
	def __init__(self) -> None:
		self.nodos: dict[str, Nodo] = {"/": Nodo(True, 0o755)}
		self.candado = threading.Lock()

	@staticmethod
	def normalizar(ruta: str) -> str:
		return conexiones.normalizar_remota(ruta)

	def hijos(self, ruta: str) -> list[str]:
		prefijo = ruta.rstrip("/") + "/"
		return [r for r in self.nodos if r != ruta and r.startswith(prefijo) and "/" not in r[len(prefijo):]]


class Manejador(paramiko.SFTPHandle):
	def __init__(self, nodo: Nodo, flags: int) -> None:
		super().__init__(flags)
		self.nodo = nodo

	def read(self, offset, length):
		return bytes(self.nodo.datos[offset:offset + length])

	def write(self, offset, data):
		datos = self.nodo.datos
		if len(datos) < offset:
			datos.extend(b"\0" * (offset - len(datos)))
		datos[offset:offset + len(data)] = data
		self.nodo.mtime = time.time()
		return paramiko.SFTP_OK

	def stat(self):
		return self.nodo.atributos("")

	def chattr(self, attr):
		return paramiko.SFTP_OK


class InterfazSFTP(paramiko.SFTPServerInterface):
	sistema: SistemaMemoria

	def _nodo(self, ruta):
		return self.sistema.nodos.get(self.sistema.normalizar(ruta))

	def canonicalize(self, path):
		return self.sistema.normalizar(path)

	def list_folder(self, path):
		ruta = self.sistema.normalizar(path)
		nodo = self.sistema.nodos.get(ruta)
		if nodo is None:
			return paramiko.SFTP_NO_SUCH_FILE
		if not nodo.carpeta:
			return paramiko.SFTP_FAILURE
		return [self.sistema.nodos[h].atributos(h.rsplit("/", 1)[1]) for h in self.sistema.hijos(ruta)]

	def stat(self, path):
		nodo = self._nodo(path)
		return nodo.atributos(path.rsplit("/", 1)[-1]) if nodo else paramiko.SFTP_NO_SUCH_FILE

	lstat = stat

	def open(self, path, flags, attr):
		ruta = self.sistema.normalizar(path)
		nodo = self.sistema.nodos.get(ruta)
		import os

		if nodo is None:
			if not flags & os.O_CREAT:
				return paramiko.SFTP_NO_SUCH_FILE
			padre = self.sistema.nodos.get(conexiones.padre_remoto(ruta) or "/")
			if padre is None or not padre.carpeta:
				return paramiko.SFTP_NO_SUCH_FILE
			nodo = self.sistema.nodos[ruta] = Nodo(False, 0o600)
		elif nodo.carpeta:
			return paramiko.SFTP_FAILURE
		if flags & os.O_TRUNC:
			nodo.datos = bytearray()
		return Manejador(nodo, flags)

	def remove(self, path):
		ruta = self.sistema.normalizar(path)
		nodo = self.sistema.nodos.get(ruta)
		if nodo is None:
			return paramiko.SFTP_NO_SUCH_FILE
		if nodo.carpeta:
			return paramiko.SFTP_FAILURE
		del self.sistema.nodos[ruta]
		return paramiko.SFTP_OK

	def rename(self, oldpath, newpath):
		origen, destino = self.sistema.normalizar(oldpath), self.sistema.normalizar(newpath)
		if origen not in self.sistema.nodos:
			return paramiko.SFTP_NO_SUCH_FILE
		if destino in self.sistema.nodos:
			return paramiko.SFTP_FAILURE
		for ruta in sorted(self.sistema.nodos):
			if ruta == origen or ruta.startswith(origen + "/"):
				self.sistema.nodos[destino + ruta[len(origen):]] = self.sistema.nodos.pop(ruta)
		return paramiko.SFTP_OK

	def mkdir(self, path, attr):
		ruta = self.sistema.normalizar(path)
		if ruta in self.sistema.nodos:
			return paramiko.SFTP_FAILURE
		self.sistema.nodos[ruta] = Nodo(True, 0o755)
		return paramiko.SFTP_OK

	def rmdir(self, path):
		ruta = self.sistema.normalizar(path)
		if ruta not in self.sistema.nodos:
			return paramiko.SFTP_NO_SUCH_FILE
		if self.sistema.hijos(ruta):
			return paramiko.SFTP_FAILURE
		del self.sistema.nodos[ruta]
		return paramiko.SFTP_OK

	def chattr(self, path, attr):
		nodo = self._nodo(path)
		if nodo is None:
			return paramiko.SFTP_NO_SUCH_FILE
		if attr.st_mode is not None:
			nodo.modo = stat_mod.S_IMODE(attr.st_mode)
		if attr.st_mtime is not None:
			nodo.mtime = attr.st_mtime
		return paramiko.SFTP_OK


class InterfazServidor(paramiko.ServerInterface):
	def __init__(self, claves_autorizadas) -> None:
		self.claves_autorizadas = claves_autorizadas

	def get_allowed_auths(self, username):
		return "password,publickey"

	def check_auth_password(self, username, password):
		return paramiko.AUTH_SUCCESSFUL if (username, password) == (USUARIO, CLAVE) else paramiko.AUTH_FAILED

	def check_auth_publickey(self, username, key):
		return paramiko.AUTH_SUCCESSFUL if username == USUARIO and key in self.claves_autorizadas else paramiko.AUTH_FAILED

	def check_channel_request(self, kind, chanid):
		return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED


class ServidorFalso:
	def __init__(self) -> None:
		self.clave = paramiko.ECDSAKey.generate()
		self.sistema = SistemaMemoria()
		self.claves_autorizadas: list = []
		self.zocalo = socket.socket(socket.AF_INET6)
		self.zocalo.bind((HOST, 0))
		self.zocalo.listen()
		self.puerto = self.zocalo.getsockname()[1]
		self.transportes: list = []
		self.hilo = threading.Thread(target=self._aceptar, daemon=True, name="sftp-pruebas")
		self.hilo.start()

	def _aceptar(self) -> None:
		sistema = self.sistema

		class Interfaz(InterfazSFTP):
			pass

		Interfaz.sistema = sistema
		while True:
			try:
				cliente, _direccion = self.zocalo.accept()
			except OSError:
				return
			transporte = paramiko.Transport(cliente)
			transporte.add_server_key(self.clave)
			transporte.set_subsystem_handler("sftp", paramiko.SFTPServer, Interfaz)
			transporte.start_server(server=InterfazServidor(self.claves_autorizadas))
			self.transportes.append(transporte)

	def crear(self, ruta: str, datos: bytes = b"", carpeta: bool = False, modo: int = 0o600) -> None:
		self.sistema.nodos[ruta] = Nodo(carpeta, 0o755 if carpeta else modo, datos)

	def cerrar(self) -> None:
		self.zocalo.close()
		for transporte in self.transportes:
			transporte.close()


@pytest.fixture
def servicios():
	decisor = DecisorFalso()
	resolver.fijar_servicios(decisor, SecretosMemoria(), ConfigFalsa())
	conexiones._aceptadas_sesion.clear()
	yield decisor
	conexiones.cerrar_todas()
	resolver.fijar_servicios(None, None, None)


@pytest.fixture
def servidor(servicios):
	falso = ServidorFalso()
	falso.crear("/hola.txt", b"hola mundo", modo=0o600)
	falso.crear("/web", carpeta=True)
	falso.crear("/web/index.html", b"<html></html>", modo=0o664)
	yield falso
	falso.cerrar()


@pytest.fixture
def sftp(servidor):
	proveedor = ProveedorSFTP(HOST, servidor.puerto, USUARIO, CLAVE, tiempo_espera=10)
	yield proveedor
	proveedor.cerrar()


def _lanzar(decisor, operacion):
	gestor = GestorOperaciones(decisor, max_paralelas=2, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)
	return operacion


# ── Listar y permisos ────────────────────────────────────────────────────────

def test_lista_y_cambia_permisos_a_644(sftp, servidor):
	entradas = {e.nombre: e for e in sftp.listar("/")}
	assert set(entradas) == {"hola.txt", "web"}
	assert entradas["web"].es_carpeta and entradas["hola.txt"].tamano == 10
	assert entradas["hola.txt"].permisos == 0o600
	assert sftp.capacidades.permisos
	sftp.fijar_permisos("/hola.txt", 0o644)
	assert servidor.sistema.nodos["/hola.txt"].modo == 0o644
	assert sftp.info("/hola.txt").permisos == 0o644
	assert [e.nombre for e in sftp.listar("/web")] == ["index.html"]


def test_info_rutas_y_no_encontrado(sftp):
	assert sftp.info("/").es_carpeta
	assert sftp.existe("/web/index.html") and not sftp.existe("/nada")
	with pytest.raises(base.NoEncontrado):
		sftp.listar("/no-existe")
	assert sftp.mostrar("/web") == f"sftp://{USUARIO}@[::1]:{sftp.puerto}/web"
	assert sftp.servidor == f"::1:{sftp.puerto}"


# ── Escribir ─────────────────────────────────────────────────────────────────

def test_flujos_crear_renombrar_eliminar(sftp, servidor):
	with sftp.abrir_lectura("/hola.txt") as flujo:
		assert flujo.read() == b"hola mundo"
	datos = bytes(range(256)) * 2000
	with sftp.abrir_escritura("/grande.bin") as flujo:
		flujo.write(datos)
	assert bytes(servidor.sistema.nodos["/grande.bin"].datos) == datos
	sftp.crear_carpeta("/nueva")
	with pytest.raises(base.YaExiste):
		sftp.crear_carpeta("/nueva")
	sftp.renombrar("/grande.bin", "/nueva/g.bin")
	assert "/nueva/g.bin" in servidor.sistema.nodos
	with pytest.raises(base.YaExiste):
		sftp.renombrar("/hola.txt", "/nueva/g.bin")
	sftp.eliminar("/nueva", recursivo=True)
	assert "/nueva" not in servidor.sistema.nodos and "/nueva/g.bin" not in servidor.sistema.nodos
	sftp.fijar_tiempos("/hola.txt", 1_600_000_000)
	assert servidor.sistema.nodos["/hola.txt"].mtime == 1_600_000_000


def test_subir_y_bajar_con_el_motor(sftp, servidor, servicios, tmp_path):
	from app.services.windows import marca_web

	local = ProveedorLocal()
	origen = tmp_path / "o"
	origen.mkdir()
	(origen / "subida.txt").write_text("subido", encoding="utf-8")
	op = _lanzar(servicios, OperacionCopiar(local, local.listar(str(origen)), sftp, "/web", OpcionesCopia(verificar=True)))
	assert op.estado == Estado.TERMINADA, op.errores
	assert bytes(servidor.sistema.nodos["/web/subida.txt"].datos) == b"subido"
	destino = tmp_path / "d"
	destino.mkdir()
	op = _lanzar(servicios, OperacionCopiar(sftp, sftp.listar("/web"), local, str(destino), OpcionesCopia()))
	assert op.estado == Estado.TERMINADA, op.errores
	assert (destino / "index.html").read_bytes() == b"<html></html>"
	assert "ZoneId=3" in (marca_web.leer(str(destino / "index.html")) or "")


# ── Huellas, contraseñas y claves ────────────────────────────────────────────

def test_huella_desconocida_se_pregunta_y_se_recuerda(servidor, servicios):
	servicios.eleccion = 0
	proveedor = ProveedorSFTP(HOST, servidor.puerto, USUARIO, CLAVE, tiempo_espera=10)
	proveedor.listar("/")
	assert [t for t, _x in servicios.elecciones] == ["Servidor desconocido"]
	assert servidor.clave.fingerprint in servicios.elecciones[0][1]
	proveedor.cerrar()
	texto = open(mod_sftp.ruta_known_hosts(), encoding="utf-8").read()
	assert f"[::1]:{servidor.puerto}" in texto
	conexiones._aceptadas_sesion.clear()
	ProveedorSFTP(HOST, servidor.puerto, USUARIO, CLAVE, tiempo_espera=10).listar("/")
	assert len(servicios.elecciones) == 1


def test_huella_solo_esta_vez_y_cancelar(servidor, servicios):
	servicios.eleccion = 1
	ProveedorSFTP(HOST, servidor.puerto, USUARIO, CLAVE, tiempo_espera=10).listar("/")
	import os

	assert not os.path.exists(mod_sftp.ruta_known_hosts())
	# El clon de una copia no vuelve a preguntar en la misma sesión.
	ProveedorSFTP(HOST, servidor.puerto, USUARIO, CLAVE, tiempo_espera=10).clonar().listar("/")
	assert len(servicios.elecciones) == 1
	conexiones._aceptadas_sesion.clear()
	servicios.eleccion = 2
	with pytest.raises(base.ErrorAcceso) as error:
		ProveedorSFTP(HOST, servidor.puerto, USUARIO, CLAVE, tiempo_espera=10).listar("/")
	assert "huella" in error.value.mensaje


def test_huella_cambiada_avisa_claramente(servidor, servicios):
	otra = paramiko.ECDSAKey.generate()
	mod_sftp.guardar_clave_servidor(HOST, servidor.puerto, otra)
	servicios.eleccion = 2
	with pytest.raises(base.ErrorAcceso):
		ProveedorSFTP(HOST, servidor.puerto, USUARIO, CLAVE, tiempo_espera=10).listar("/")
	titulo, texto = servicios.elecciones[0]
	assert "ha cambiado" in titulo and "NO coincide" in texto
	assert otra.fingerprint in texto and servidor.clave.fingerprint in texto
	servicios.eleccion = 0
	ProveedorSFTP(HOST, servidor.puerto, USUARIO, CLAVE, tiempo_espera=10).listar("/")
	conocidas = mod_sftp._cargar_known_hosts().lookup(f"[::1]:{servidor.puerto}")
	assert conocidas[servidor.clave.get_name()] == servidor.clave


def test_contrasena_incorrecta(servidor, servicios):
	with pytest.raises(base.ErrorAcceso) as error:
		ProveedorSFTP(HOST, servidor.puerto, USUARIO, "mala", tiempo_espera=10).listar("/")
	assert "Usuario o contraseña incorrectos" in error.value.mensaje


def test_pide_contrasena_si_no_se_conoce(servidor, servicios):
	servicios.texto = CLAVE
	proveedor = ProveedorSFTP(HOST, servidor.puerto, USUARIO, None, tiempo_espera=10)
	assert proveedor.listar("/")
	assert servicios.textos == [f"Contraseña de {USUARIO}@{HOST}"]


def test_clave_privada_con_frase(servidor, servicios, tmp_path):
	clave = paramiko.ECDSAKey.generate()
	ruta = tmp_path / "id_ecdsa"
	salida = io.StringIO()
	clave.write_private_key(salida, password="frase buena")
	ruta.write_text(salida.getvalue(), encoding="ascii")
	servidor.claves_autorizadas.append(paramiko.ECDSAKey(data=clave.asbytes()))
	servicios.texto = "frase buena"
	proveedor = ProveedorSFTP(HOST, servidor.puerto, USUARIO, None, tiempo_espera=10, clave_privada=str(ruta))
	assert {e.nombre for e in proveedor.listar("/")} == {"hola.txt", "web"}
	assert servicios.textos == ["Frase de la clave privada"]
	proveedor.cerrar()
	assert proveedor._frase is None
	servicios.texto = "mala"
	with pytest.raises(base.ErrorAcceso) as error:
		ProveedorSFTP(HOST, servidor.puerto, USUARIO, None, tiempo_espera=10, clave_privada=str(ruta)).listar("/")
	assert "frase" in error.value.mensaje


def test_reconecta_si_se_pierde_la_conexion(sftp, servidor):
	assert sftp.listar("/")
	for transporte in servidor.transportes:
		transporte.close()
	time.sleep(0.2)
	assert {e.nombre for e in sftp.listar("/")} == {"hola.txt", "web"}


def test_direccion_sftp_y_sitio(servidor, servicios):
	repo = conexiones.Conexiones()
	sitio = repo.guardar(conexiones.Sitio(nombre="SSH", protocolo="sftp", servidor=HOST, puerto=servidor.puerto, usuario=USUARIO,
		carpeta="/web"), CLAVE)
	proveedor, ruta, _cursor = resolver.abrir_ruta(f"sftp://{USUARIO}@[::1]:{servidor.puerto}/web")
	assert isinstance(proveedor, ProveedorSFTP) and ruta == "/web" and proveedor.sitio_id == sitio.id
	assert [e.nombre for e in proveedor.listar(ruta)] == ["index.html"]
	assert not servicios.textos
	proveedor.cerrar()
