# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque D: proveedor FTP contra un servidor pyftpdlib local, sitios guardados y direcciones ftp://.

El servidor escucha en la dirección de bucle local en un puerto libre y sirve
una carpeta temporal; ninguna prueba sale a la red.

Se usa ``::1`` (IPv6) y no ``127.0.0.1``: en el entorno aislado donde se
ejecutan las pruebas, las conexiones IPv4 de bucle local que cierra primero
el servidor (lo que hace FTP al terminar cada LIST o RETR) llegan a menudo
como «conexión restablecida» (WinError 10054) y se pierden los datos; con
IPv6 no pasa. Se comprobó también con sockets de .NET, así que no es cosa de
ftplib ni de pyftpdlib.
"""

from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("pyftpdlib")

from pyftpdlib.authorizers import DummyAuthorizer  # noqa: E402
from pyftpdlib.handlers import FTPHandler  # noqa: E402
from pyftpdlib.servers import ThreadedFTPServer  # noqa: E402

from app.core.tareas import ejecutor_directo  # noqa: E402
from app.services import conexiones  # noqa: E402
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar  # noqa: E402
from app.services.operaciones.gestor import GestorOperaciones  # noqa: E402
from app.services.operaciones.modelo import AccionConflicto, AccionError, Estado, RespuestaConflicto  # noqa: E402
from app.services.vfs import base, resolver  # noqa: E402
from app.services.vfs.ftp import ProveedorFTP, analizar_list, analizar_mlsd  # noqa: E402
from app.services.vfs.local import ProveedorLocal  # noqa: E402

USUARIO, CLAVE = "ana", "secreta"
HOST = "::1"


class DecisorFalso:
	"""Responde lo que se le diga y anota lo que se le pregunta."""

	def __init__(self, eleccion: int = 0, texto: str | None = None) -> None:
		self.eleccion = eleccion
		self.texto = texto
		self.elecciones: list[tuple[str, str]] = []
		self.textos: list[str] = []

	def resolver_conflictos(self, operacion, conflictos):
		return [RespuestaConflicto(AccionConflicto.SOBRESCRIBIR) for _ in conflictos]

	def preguntar_conflicto(self, operacion, conflicto):
		return RespuestaConflicto(AccionConflicto.SOBRESCRIBIR)

	def preguntar_error(self, operacion, pregunta):
		return AccionError.OMITIR

	def elegir(self, titulo, texto, opciones, predeterminada=0, escape=-1, operacion=None):
		self.elecciones.append((titulo, texto))
		return self.eleccion

	def pedir_texto(self, titulo, texto, valor="", oculto=False, operacion=None):
		self.textos.append(titulo)
		return self.texto


class SecretosMemoria:
	"""``AlmacenSecretos`` en memoria (las pruebas de DPAPI real están en tests/test_secretos.py)."""

	def __init__(self) -> None:
		self.datos: dict[str, str] = {}

	def obtener(self, nombre, por_defecto=None):
		return self.datos.get(nombre, por_defecto)

	def nombres(self):
		return sorted(self.datos)

	def guardar_varios(self, cambios):
		for nombre, valor in cambios.items():
			if valor is None:
				self.datos.pop(nombre, None)
			else:
				self.datos[nombre] = valor

	def guardar(self, nombre, valor):
		self.guardar_varios({nombre: valor})

	def borrar(self, nombre):
		self.guardar_varios({nombre: None})


class ConfigFalsa:
	def __init__(self, **valores) -> None:
		# 2.0 (18.1): ftp.avisar_sin_cifrar pasa a la confirmación silenciable «ftp_sin_cifrar» (10.12).
		self.valores = {"general.no_preguntar": ["ftp_sin_cifrar"], "ftp.tiempo_espera_s": 10, "ftp.pasivo": True, **valores}

	def obtener(self, clave):
		return self.valores[clave]


def _servidor(carpeta, sin_mlsd: bool = False):
	autorizador = DummyAuthorizer()
	autorizador.add_user(USUARIO, CLAVE, str(carpeta), perm="elradfmwMT")
	autorizador.add_anonymous(str(carpeta))

	class Manejador(FTPHandler):
		pass

	Manejador.authorizer = autorizador
	Manejador.banner = "zCommander pruebas"
	if sin_mlsd:
		Manejador.proto_cmds = {k: v for k, v in FTPHandler.proto_cmds.items() if k not in ("MLSD", "MLST")}
	servidor = ThreadedFTPServer((HOST, 0), Manejador)
	hilo = threading.Thread(target=servidor.serve_forever, kwargs={"timeout": 0.05}, daemon=True, name="ftp-pruebas")
	hilo.start()
	return servidor, hilo


@pytest.fixture
def raiz(tmp_path):
	carpeta = tmp_path / "servidor"
	carpeta.mkdir()
	(carpeta / "hola.txt").write_text("hola mundo", encoding="utf-8")
	(carpeta / "docs").mkdir()
	(carpeta / "docs" / "año 2024.txt").write_text("ñ" * 100, encoding="utf-8")
	return carpeta


@pytest.fixture
def servicios():
	decisor = DecisorFalso()
	secretos = SecretosMemoria()
	resolver.fijar_servicios(decisor, secretos, ConfigFalsa())
	yield decisor, secretos
	conexiones.cerrar_todas()
	resolver.fijar_servicios(None, None, None)


@pytest.fixture
def servidor(raiz, servicios):
	srv, hilo = _servidor(raiz)
	yield srv.address[1]
	srv.close_all()
	hilo.join(3)


@pytest.fixture
def ftp(servidor):
	proveedor = ProveedorFTP(HOST, servidor, USUARIO, CLAVE, tiempo_espera=10)
	yield proveedor
	proveedor.cerrar()


def _lanzar(decisor, operacion):
	gestor = GestorOperaciones(decisor, max_paralelas=2, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)
	return operacion


# ── Listar, info y rutas ─────────────────────────────────────────────────────

def test_listar_con_mlsd(ftp):
	entradas = {e.nombre: e for e in ftp.listar("/")}
	assert set(entradas) == {"hola.txt", "docs"}
	assert entradas["docs"].es_carpeta and entradas["docs"].ruta == "/docs"
	assert entradas["hola.txt"].tamano == 10 and not entradas["hola.txt"].es_carpeta
	assert abs(entradas["hola.txt"].modificado - time.time()) < 3600
	assert [e.nombre for e in ftp.listar("/docs")] == ["año 2024.txt"]
	assert ftp.conectado()
	assert ftp.servidor.startswith("::1:")


def test_listar_sin_mlsd_usa_list(raiz, servicios):
	srv, hilo = _servidor(raiz, sin_mlsd=True)
	try:
		proveedor = ProveedorFTP(HOST, srv.address[1], USUARIO, CLAVE, tiempo_espera=10)
		entradas = {e.nombre: e for e in proveedor.listar("/")}
		assert entradas["docs"].es_carpeta and entradas["hola.txt"].tamano == 10
		assert proveedor.info("/hola.txt").tamano == 10
		assert [e.nombre for e in proveedor.listar("/docs")] == ["año 2024.txt"]
		proveedor.cerrar()
	finally:
		srv.close_all()
		hilo.join(3)


def test_info_y_no_encontrado(ftp):
	assert ftp.info("/").es_carpeta
	assert ftp.info("/docs").es_carpeta
	assert ftp.info("/hola.txt").tamano == 10
	assert ftp.existe("/hola.txt") and not ftp.existe("/nada.txt")
	with pytest.raises(base.NoEncontrado):
		ftp.listar("/no-existe")
	with pytest.raises(base.NoEncontrado):
		ftp.info("/no-existe/x")


def test_rutas_y_mostrar(ftp):
	assert ftp.padre("/") is None
	assert ftp.padre("/docs/a") == "/docs"
	assert ftp.unir("/docs", "a.txt") == "/docs/a.txt"
	assert ftp.raiz("/docs") == "/"
	assert ftp.nombre("/docs/a.txt") == "a.txt"
	assert ftp.mostrar("/docs").endswith("/docs") and "secreta" not in ftp.mostrar("/docs")
	assert ftp.mostrar("/docs").startswith(f"ftp://{USUARIO}@[::1]:")
	with pytest.raises(base.NombreNoValido):
		ftp.listar("/a\r\nDELE x")


# ── Escribir: subir, bajar, renombrar, borrar ───────────────────────────────

def test_leer_y_escribir_flujos(ftp, raiz):
	with ftp.abrir_lectura("/hola.txt") as flujo:
		assert flujo.read() == b"hola mundo"
	datos = bytes(range(256)) * 4096
	with ftp.abrir_escritura("/grande.bin") as flujo:
		flujo.write(datos)
	assert (raiz / "grande.bin").read_bytes() == datos
	# Con un flujo abierto, el mismo hilo puede seguir usando el servidor (conexión aparte).
	with ftp.abrir_lectura("/grande.bin") as flujo:
		assert ftp.existe("/hola.txt")
		assert flujo.read(10) == datos[:10]
	assert ftp.listar("/")


def test_crear_renombrar_eliminar(ftp, raiz):
	ftp.crear_carpeta("/nueva")
	assert (raiz / "nueva").is_dir()
	with pytest.raises(base.YaExiste):
		ftp.crear_carpeta("/nueva")
	ftp.renombrar("/hola.txt", "/nueva/adios.txt")
	assert (raiz / "nueva" / "adios.txt").read_text(encoding="utf-8") == "hola mundo"
	with pytest.raises(base.YaExiste):
		ftp.renombrar("/docs", "/nueva")
	ftp.eliminar("/nueva/adios.txt")
	assert not (raiz / "nueva" / "adios.txt").exists()
	ftp.eliminar("/docs", recursivo=True)
	assert not (raiz / "docs").exists()
	with pytest.raises(base.ErrorAcceso):
		ftp.eliminar("/")


def test_fijar_tiempos_con_mfmt(ftp, raiz):
	ftp.fijar_tiempos("/hola.txt", 1_600_000_000)
	assert abs((raiz / "hola.txt").stat().st_mtime - 1_600_000_000) < 2


def test_subir_con_el_motor(ftp, raiz, tmp_path, servicios):
	origen = tmp_path / "local"
	origen.mkdir()
	(origen / "subida.txt").write_text("contenido subido", encoding="utf-8")
	(origen / "carpeta").mkdir()
	(origen / "carpeta" / "dentro.txt").write_text("x" * 5000, encoding="utf-8")
	local = ProveedorLocal()
	operacion = _lanzar(servicios[0], OperacionCopiar(local, local.listar(str(origen)), ftp, "/docs", OpcionesCopia(verificar=True)))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert (raiz / "docs" / "subida.txt").read_text(encoding="utf-8") == "contenido subido"
	assert (raiz / "docs" / "carpeta" / "dentro.txt").read_text(encoding="utf-8") == "x" * 5000
	assert not any(p.name.startswith("~zc") for p in (raiz / "docs").iterdir())


def test_bajar_con_marca_de_la_web(ftp, tmp_path, servicios):
	from app.services.windows import marca_web

	destino = tmp_path / "descargas"
	destino.mkdir()
	entradas = [e for e in ftp.listar("/") if e.nombre == "hola.txt"]
	operacion = _lanzar(servicios[0], OperacionCopiar(ftp, entradas, ProveedorLocal(), str(destino), OpcionesCopia()))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert (destino / "hola.txt").read_text(encoding="utf-8") == "hola mundo"
	marca = marca_web.leer(str(destino / "hola.txt"))
	assert marca is not None and "ZoneId=3" in marca


def test_mover_dentro_del_servidor_y_clonar(ftp, raiz, servicios):
	clon = ftp.clonar()
	assert clon is not ftp and clon.servidor == ftp.servidor
	assert [e.nombre for e in clon.listar("/docs")] == ["año 2024.txt"]
	clon.cerrar()
	entradas = [e for e in ftp.listar("/") if e.nombre == "hola.txt"]
	operacion = _lanzar(servicios[0], OperacionCopiar(ftp, entradas, ftp, "/docs", OpcionesCopia(), mover=True))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert (raiz / "docs" / "hola.txt").exists() and not (raiz / "hola.txt").exists()


# ── Errores y reconexión ─────────────────────────────────────────────────────

def test_contrasena_incorrecta(servidor):
	proveedor = ProveedorFTP(HOST, servidor, USUARIO, "mala", tiempo_espera=10)
	with pytest.raises(base.ErrorAcceso) as error:
		proveedor.listar("/")
	assert "Usuario o contraseña incorrectos" in error.value.mensaje


def test_servidor_que_no_responde(servicios):
	import socket

	zocalo = socket.socket()
	zocalo.bind(("127.0.0.1", 0))
	puerto = zocalo.getsockname()[1]
	zocalo.close()
	proveedor = ProveedorFTP("127.0.0.1", puerto, USUARIO, CLAVE, tiempo_espera=5)
	with pytest.raises(base.ErrorRed) as error:
		proveedor.listar("/")
	assert "no responde" in error.value.mensaje


def test_reconecta_una_vez_si_se_pierde_la_conexion(ftp):
	assert ftp.listar("/")
	# Se corta la conexión de control por debajo, como si el servidor la cerrara.
	ftp._principal.ftp.sock.close()
	assert {e.nombre for e in ftp.listar("/")} == {"hola.txt", "docs"}


def test_anonimo(servidor):
	proveedor = ProveedorFTP(HOST, servidor, "", None, tiempo_espera=10)
	assert {e.nombre for e in proveedor.listar("/")} == {"hola.txt", "docs"}
	proveedor.cerrar()


# ── Contraseñas, avisos y direcciones ────────────────────────────────────────

def test_pide_la_contrasena_y_la_olvida_al_desconectar(servidor, servicios):
	decisor, _secretos = servicios
	decisor.texto = CLAVE
	proveedor = ProveedorFTP(HOST, servidor, USUARIO, None, tiempo_espera=10)
	assert proveedor.listar("/")
	assert len(decisor.textos) == 1 and USUARIO in decisor.textos[0]
	proveedor.cerrar()
	assert proveedor._contrasena is None
	decisor.texto = None
	with pytest.raises(base.ErrorAcceso):
		proveedor.listar("/")


def test_contrasena_de_un_sitio_guardado(servidor, servicios):
	decisor, secretos = servicios
	repo = conexiones.Conexiones()
	sitio = repo.guardar(conexiones.Sitio(nombre="Pruebas", servidor=HOST, puerto=servidor, usuario=USUARIO), CLAVE)
	assert secretos.obtener(conexiones.clave_secreto(sitio.id)) == CLAVE
	assert "secreta" not in (conexiones.almacen_json.ruta(conexiones.ARCHIVO)).read_text(encoding="utf-8")
	proveedor = conexiones.crear_proveedor(sitio)
	assert proveedor.listar("/") and not decisor.textos
	# Una dirección escrita a mano que coincide con el sitio usa su contraseña y se reutiliza.
	otro, ruta = resolver.abrir_ruta(f"ftp://{USUARIO}@[::1]:{servidor}/docs")[:2]
	assert otro is proveedor and ruta == "/docs"
	proveedor.cerrar()


def test_aviso_sin_cifrar_una_vez_por_sitio(servidor, servicios):
	decisor, _secretos = servicios
	resolver.fijar_servicios(decisor, servicios[1], ConfigFalsa(**{"general.no_preguntar": []}))
	repo = conexiones.Conexiones()
	sitio = repo.guardar(conexiones.Sitio(nombre="Claro", servidor=HOST, puerto=servidor, usuario=USUARIO), CLAVE)
	proveedor = conexiones.crear_proveedor(sitio)
	proveedor.listar("/")
	assert [t for t, _x in decisor.elecciones] == ["Conexión sin cifrar"]
	assert repo.obtener(sitio.id).aviso_sin_cifrar_mostrado
	proveedor.cerrar()
	conexiones.crear_proveedor(repo.obtener(sitio.id)).listar("/")
	assert len(decisor.elecciones) == 1
	# Sin sitio guardado se avisa (una vez por sesión) y cancelar el aviso no conecta.
	repo.eliminar(sitio.id)
	decisor.eleccion = 1
	nuevo = ProveedorFTP(HOST, servidor, USUARIO, CLAVE, tiempo_espera=10)
	with pytest.raises(base.ErrorAcceso):
		nuevo.listar("/")
	assert len(decisor.elecciones) == 2


def test_direccion_con_contrasena_y_reutilizacion(servidor, servicios):
	proveedor, ruta, cursor = resolver.abrir_ruta(f"ftp://{USUARIO}:{CLAVE}@[::1]:{servidor}/docs")
	assert isinstance(proveedor, ProveedorFTP) and ruta == "/docs" and cursor is None
	assert [e.nombre for e in proveedor.listar(ruta)] == ["año 2024.txt"]
	mismo = resolver.abrir_ruta(f"ftp://{USUARIO}@[::1]:{servidor}/")[0]
	assert mismo is proveedor
	with pytest.raises(base.NoAdmitido):
		resolver.abrir_ruta("gopher://servidor/")


# ── Intérpretes de listados y sitios ─────────────────────────────────────────

def test_analizar_mlsd():
	fila = analizar_mlsd("type=file;size=1234;modify=20240131120000.5;perm=r; informe final.pdf")
	assert fila.nombre == "informe final.pdf" and fila.tipo == "archivo" and fila.tamano == 1234
	assert fila.modificado == pytest.approx(1706702400.5)
	assert analizar_mlsd("type=cdir;modify=20240101000000; .") is None
	assert analizar_mlsd("type=dir;modify=20240101000000; fotos").tipo == "carpeta"
	assert analizar_mlsd("type=OS.unix=slink:/datos;modify=20240101000000; enlace").tipo == "enlace"


def test_analizar_list_unix_y_dos():
	ahora = 1706702400.0  # 31-01-2024
	fila = analizar_list("-rw-r--r--   1 ana   users     4096 Jan 15 10:30 nota con espacios.txt", ahora)
	assert fila.nombre == "nota con espacios.txt" and fila.tamano == 4096 and fila.tipo == "archivo"
	assert time_tuple(fila.modificado)[:5] == (2024, 1, 15, 10, 30)
	# Sin año y «en el futuro»: es del año pasado.
	assert time_tuple(analizar_list("-rw-r--r-- 1 a b 1 Dec 24 10:00 x", ahora).modificado)[0] == 2023
	assert analizar_list("drwxr-xr-x 2 ana users 4096 Mar  3  2019 fotos", ahora).tipo == "carpeta"
	enlace = analizar_list("lrwxrwxrwx 1 ana users 7 Jan  1  2020 web -> /var/www", ahora)
	assert enlace.tipo == "enlace" and enlace.nombre == "web" and enlace.destino == "/var/www"
	assert analizar_list("total 12", ahora) is None
	assert analizar_list("drwxr-xr-x 2 a b 4096 Jan 1 2020 ..", ahora) is None
	dos = analizar_list("01-31-24  02:05PM       <DIR>          Documentos", ahora)
	assert dos.tipo == "carpeta" and dos.nombre == "Documentos"
	archivo = analizar_list("12-25-23  09:00AM              1234 regalo.txt", ahora)
	assert archivo.tamano == 1234 and time_tuple(archivo.modificado)[:5] == (2023, 12, 25, 9, 0)


def time_tuple(marca):
	return tuple(time.gmtime(marca))


def test_sitios_guardar_duplicar_eliminar(servicios):
	_decisor, secretos = servicios
	repo = conexiones.Conexiones()
	sitio = repo.guardar(conexiones.Sitio(nombre="Web", protocolo="sftp", servidor="ejemplo.org", puerto=22, usuario="ana",
		clave_privada="C:\\claves\\id"), "pw", "frase")
	assert repo.tiene_contrasena(sitio.id) and repo.frase(sitio.id) == "frase"
	copia = repo.duplicar(sitio.id)
	assert copia.nombre == "Web (copia)" and copia.id != sitio.id and repo.contrasena(copia.id) == "pw"
	assert repo.duplicar(sitio.id).nombre == "Web (copia 2)"
	assert repo.eliminar(sitio.id)
	assert not any(n.startswith(f"ftp:{sitio.id}:") for n in secretos.nombres())
	assert repo.contrasena(copia.id) == "pw"
	# No guardar la contraseña borra la que hubiera.
	copia.guardar_contrasena = False
	repo.guardar(copia)
	assert not repo.tiene_contrasena(copia.id)
	assert [s.nombre for s in repo.sitios()] == ["Web (copia 2)", "Web (copia)"]


def test_validar_y_urls():
	assert conexiones.validar(conexiones.Sitio(nombre="", servidor="x"))[0] == "nombre"
	assert conexiones.validar(conexiones.Sitio(nombre="a", servidor="ftp://x"))[0] == "servidor"
	assert conexiones.validar(conexiones.Sitio(nombre="a", servidor="x", puerto=70000))[0] == "puerto"
	assert conexiones.validar(conexiones.Sitio(nombre="a", servidor="x", protocolo="sftp", puerto=22))[0] == "usuario"
	assert conexiones.validar(conexiones.Sitio(nombre="a", servidor="x", tiempo_espera_s=1))[0] == "tiempo_espera_s"
	assert conexiones.validar(conexiones.Sitio(nombre="a", servidor="x")) is None
	datos = conexiones.analizar_url("sftp://ana%40casa:p%3Aw@[::1]:2222/home/ana%20m")
	assert (datos.protocolo, datos.servidor, datos.puerto, datos.usuario, datos.contrasena, datos.ruta) == \
		("sftp", "::1", 2222, "ana@casa", "p:w", "/home/ana m")
	assert conexiones.componer_url("ftp", "srv", 21, "", "/a") == "ftp://srv/a"
	assert conexiones.componer_url("sftp", "srv", 2222, "ana", "/") == "sftp://ana@srv:2222/"
	assert conexiones.normalizar_remota("a/../b/./c/") == "/b/c"
	with pytest.raises(base.NombreNoValido):
		conexiones.analizar_url("ftp:///carpeta")


def test_huella_tls_se_pregunta_se_guarda_y_avisa_si_cambia(servicios):
	"""Lógica de la huella del certificado FTPS (sin servidor TLS: pyftpdlib lo necesita con pyOpenSSL)."""
	decisor, _secretos = servicios
	conexiones._aceptadas_sesion.clear()
	proveedor = ProveedorFTP("ftps.ejemplo.org", 990, USUARIO, CLAVE, tls=True)
	assert proveedor.protocolo == "ftps" and proveedor.mostrar("/").startswith("ftps://")
	huella = conexiones.huella_sha256(b"certificado de prueba")

	def confirmar(valor):
		proveedor.confirmar_huella("su certificado", valor, conexiones.huella_tls_guardada(proveedor.servidor),
			lambda h: conexiones.guardar_huella_tls(proveedor.servidor, h))

	confirmar(huella)
	assert decisor.elecciones[-1][0] == "Servidor desconocido"
	assert conexiones.huella_tls_guardada("ftps.ejemplo.org:990") == huella
	conexiones._aceptadas_sesion.clear()
	confirmar(huella)
	assert len(decisor.elecciones) == 1
	decisor.eleccion = 2
	with pytest.raises(base.ErrorAcceso):
		confirmar(conexiones.huella_sha256(b"otro certificado"))
	assert "ha cambiado" in decisor.elecciones[-1][0]
	assert conexiones.huella_tls_guardada("ftps.ejemplo.org:990") == huella
