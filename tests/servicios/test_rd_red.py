# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque RD: unidades de red completas, servicios sin interfaz (diseño 2.0, 9 y 18.2).

``win32wnet``, ``win32net``, ``win32cred``, ``mpr.dll`` y WMI se simulan: estas
pruebas nunca conectan, desconectan ni guardan credenciales reales. Solo la
última (marca ``interfaz``) lee de verdad los recursos de ``\\\\localhost``.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from types import SimpleNamespace

import pytest
import pywintypes

from app.services import red_recientes
from app.services.vfs import base, resolver
from app.services.vfs import red as vfs_red
from app.services.windows import red, red_descubrir, red_info

CONTRASENA = "Secreta-de-prueba-9271"


def error_windows(codigo: int) -> pywintypes.error:
	return pywintypes.error(codigo, "WNetPrueba", "error simulado")


class WNetFalso:
	"""``win32wnet`` simulado: conexiones activas y recordadas; apunta cada llamada."""

	def __init__(self, conectadas=(), recordadas=()) -> None:
		self.conectadas = [SimpleNamespace(lpLocalName=l, lpRemoteName=r, lpProvider=p) for l, r, p in conectadas]
		self.recordadas = [SimpleNamespace(lpLocalName=l, lpRemoteName=r, lpProvider=p) for l, r, p in recordadas]
		self.llamadas: list[tuple] = []
		self.errores_conectar: list[int] = []
		self.errores_desconectar: list[int] = []
		self._abiertas: dict[int, list] = {}

	class NETRESOURCE(SimpleNamespace):
		pass

	def WNetOpenEnum(self, alcance, tipo, uso, recurso):  # noqa: N802 - API de Windows
		if recurso is not None:
			raise error_windows(1222)
		manejador = len(self._abiertas) + 1
		self._abiertas[manejador] = list(self.conectadas if alcance == red.RESOURCE_CONNECTED else self.recordadas)
		return manejador

	def WNetEnumResource(self, manejador, cuantos):  # noqa: N802
		lote, self._abiertas[manejador] = self._abiertas[manejador][:cuantos], self._abiertas[manejador][cuantos:]
		return lote

	def WNetCloseEnum(self, manejador):  # noqa: N802
		self._abiertas.pop(manejador, None)

	def WNetAddConnection2(self, recurso, contrasena, usuario, banderas):  # noqa: N802
		self.llamadas.append(("conectar", recurso.lpLocalName, recurso.lpRemoteName, contrasena, usuario, banderas))
		if self.errores_conectar:
			raise error_windows(self.errores_conectar.pop(0))

	def WNetCancelConnection2(self, nombre, banderas, forzar):  # noqa: N802
		self.llamadas.append(("desconectar", nombre, banderas, forzar))
		if self.errores_desconectar:
			raise error_windows(self.errores_desconectar.pop(0))

	def WNetGetUniversalName(self, ruta, nivel):  # noqa: N802
		if ruta.upper().startswith("Z:"):
			return "\\\\srv\\rec" + ruta[2:]
		raise error_windows(red.ERROR_NOT_CONNECTED)

	def WNetGetLastError(self):  # noqa: N802
		return 0, "El servidor WebDAV no responde", "Web Client Network"

	def WNetGetUser(self, nombre):  # noqa: N802
		return "ana"


class NetFalso:
	def __init__(self, usos=(), recursos=None, errores=()) -> None:
		self.usos = list(usos)
		self.recursos = recursos or {}
		self.errores = list(errores)
		self.pedidos: list[str] = []

	def NetUseEnum(self, servidor, nivel):  # noqa: N802
		return self.usos, len(self.usos), 0

	def NetShareEnum(self, servidor, nivel, *_reanudar):  # noqa: N802
		self.pedidos.append(servidor)
		if self.errores:
			raise error_windows(self.errores.pop(0))
		filas = self.recursos.get(servidor.upper())
		if filas is None:
			raise error_windows(53)
		return filas, len(filas), 0


class CredFalso:
	def __init__(self) -> None:
		self.escritas: list[dict] = []
		self.borradas: list[tuple] = []

	def CredWrite(self, datos, banderas):  # noqa: N802
		self.escritas.append(dict(datos))

	def CredEnumerate(self, filtro, banderas):  # noqa: N802
		return [
			{"Type": red.CRED_TYPE_DOMAIN_PASSWORD, "TargetName": "nas", "UserName": "nas\\ana", "Persist": 3},
			{"Type": 1, "TargetName": "LegacyGeneric:target=x", "UserName": "y", "Persist": 2},
		]

	def CredDelete(self, objetivo, tipo, banderas):  # noqa: N802
		self.borradas.append((objetivo, tipo))


@pytest.fixture
def simulado(monkeypatch):
	wnet = WNetFalso(
		conectadas=[("Z:", "\\\\nas\\fotos", red.PROVEEDOR_SMB), ("", "\\\\nas\\docs", red.PROVEEDOR_SMB), ("", "\\\\nas\\IPC$", red.PROVEEDOR_SMB)],
		recordadas=[("Z:", "\\\\nas\\fotos", red.PROVEEDOR_SMB), ("Y:", "\\\\ds220\\home", red.PROVEEDOR_SMB)],
	)
	net = NetFalso(usos=[{"local": "Z:", "remote": "\\\\nas\\fotos", "status": red.USE_OK, "username": "ana", "domainname": "NAS"}])
	cred = CredFalso()
	monkeypatch.setattr(red, "_win32wnet", lambda: wnet)
	monkeypatch.setattr(red, "_win32net", lambda: net)
	monkeypatch.setattr(red, "_win32cred", lambda: cred)
	monkeypatch.setattr(red, "estado_webclient", lambda: "manual")
	monkeypatch.setattr(red, "otros_proveedores", lambda: [])
	monkeypatch.setattr(red, "es_elevado", lambda: False)
	vfs_red.olvidar_equipos()
	resolver.fijar_servicios()
	yield SimpleNamespace(wnet=wnet, net=net, cred=cred)
	vfs_red.olvidar_equipos()
	resolver.fijar_servicios()


class DecisorFalso:
	def __init__(self, credenciales=None, elecciones=()) -> None:
		self.credenciales = credenciales
		self.elecciones = list(elecciones)
		self.preguntas: list[tuple] = []

	def pedir_credenciales(self, titulo, texto, usuario="", operacion=None):
		self.preguntas.append(("credenciales", titulo, texto))
		return self.credenciales

	def elegir(self, titulo, texto, opciones, predeterminada=0, escape=-1, operacion=None):
		self.preguntas.append(("elegir", titulo, list(opciones)))
		return self.elecciones.pop(0) if self.elecciones else escape


class ConfigFalsa:
	def __init__(self, **valores) -> None:
		self.valores = valores

	def obtener(self, clave):
		return self.valores[clave]


# ── Raíz «Red» ───────────────────────────────────────────────────────────────


def test_unidades_con_y_sin_letra_estado_y_usuario(simulado):
	unidades = red.unidades_red()
	assert [(u.letra, u.remoto) for u in unidades] == [("Y:", "\\\\ds220\\home"), ("Z:", "\\\\nas\\fotos"), ("", "\\\\nas\\docs")]
	y, z, docs = unidades
	assert not y.conectada and y.recordada and y.estado == red.DESCONECTADA
	assert y.texto_estado() == "Desconectada: Intro para volver a conectar"
	assert z.conectada and z.recordada and z.usuario == "NAS\\ana" and z.proveedor == red.PROVEEDOR_SMB
	assert docs.letra == "" and docs.nombre == "\\\\nas\\docs" and "sin letra" in docs.describir()
	assert y.mensaje_no_disponible() == "Y: no está disponible (\\\\ds220\\home). Intro para volver a conectar"


def test_sesion_perdida_es_no_disponible(simulado):
	simulado.net.usos[0]["status"] = red.USE_SESSLOST
	z = red.unidad("z")
	assert z.estado == red.NO_DISPONIBLE and z.texto_estado() == "No disponible"


def test_raiz_muestra_unidades_conexiones_y_recientes_con_tipo_y_estado(simulado):
	red_recientes.anotar_reciente("ALFA")
	red_recientes.guardar_favoritos([red_recientes.FavoritoRed("Mi NAS", "\\\\ds220")])
	proveedor = vfs_red.ProveedorRed()
	filas = proveedor.filas_raiz()
	assert [(f.nombre, f.tipo, f.estado) for f in filas] == [
		("Y:", "Unidad de red", "Desconectada: Intro para volver a conectar"),
		("Z:", "Unidad de red", "Conectada"),
		("\\\\nas\\docs", "Conexión sin letra", "Conectada"),
		("Mi NAS", "Servidor favorito", ""),
		("ALFA", "Servidor reciente", ""),
	]
	assert filas[1].remoto == "\\\\nas\\fotos" and filas[1].ruta == "Z:\\"
	nombres = [e.nombre for e in proveedor.listar("")]
	assert nombres[0] == "Y:, Unidad de red, \\\\ds220\\home, Desconectada: Intro para volver a conectar"
	assert "ALFA, Servidor reciente" in nombres
	# Las columnas propias (petición al panel) dejan el nombre limpio y dan el resto aparte.
	assert proveedor.columnas_propias("") == [("nombre", "Nombre"), ("red_tipo", "Tipo"), ("red_remoto", "Remoto"), ("red_estado", "Estado")]
	entradas = proveedor.listar("")
	assert entradas[1].nombre == "Z:" and proveedor.valor_columna(entradas[1], "red_estado") == "Conectada"
	assert proveedor.conservar_orden("") and proveedor.orden_al_abrir(entradas[1]) == vfs_red.ORDEN_ABRIR


def test_raiz_rutas_y_navegacion(simulado):
	proveedor = vfs_red.proveedor_red()
	assert resolver.abrir_ruta("red://")[:2] == (proveedor, "")
	assert resolver.abrir_ruta("red://DS220/home")[1] == "\\\\DS220\\home"
	assert proveedor.mostrar("") == "red://" and proveedor.padre("") is None
	assert proveedor.padre("\\\\DS220") == "" and proveedor.padre("Z:\\") == "" and proveedor.padre("\\\\DS220\\home") == "\\\\DS220"
	assert proveedor.ruta_local("Z:\\fotos") == "Z:\\fotos" and proveedor.ruta_local("\\\\DS220") is None
	assert not proveedor.capacidades.escribir
	with pytest.raises(base.SoloLectura, match="Desconectar unidad de red"):
		proveedor.eliminar("Z:\\")
	assert vfs_red.unidad_virtual().direccion == "red://"


def test_raiz_con_busqueda_y_equipos(simulado):
	entregar = threading.Event()
	terminar = threading.Event()

	def fuente(emitir, cancelado):
		entregar.wait(5)
		emitir(red_descubrir.EquipoRed("BETA", "\\\\BETA", "prueba", "192.168.1.9"))
		emitir(red_descubrir.EquipoRed("beta", "\\\\beta", "otra"))
		terminar.wait(5)

	avisos: list[str] = []
	vfs_red.suscribir(lambda evento, dato: avisos.append(evento))
	busqueda = vfs_red.iniciar_descubrimiento(10, fuentes=[("prueba", fuente)])
	proveedor = vfs_red.ProveedorRed()
	assert vfs_red.buscando() and vfs_red.iniciar_descubrimiento(10) is busqueda
	assert [f.clase for f in proveedor.filas_raiz()][-1] == vfs_red.BUSCANDO
	entregar.set()
	assert _esperar(lambda: vfs_red.equipos())
	terminar.set()
	assert busqueda.esperar(5)
	filas = proveedor.filas_raiz()
	assert [(f.nombre, f.tipo, f.remoto) for f in filas if f.clase == vfs_red.EQUIPO] == [("BETA", "Equipo encontrado", "192.168.1.9")]
	assert vfs_red.BUSCANDO not in [f.clase for f in filas]
	assert avisos.count(vfs_red.EQUIPO_NUEVO) == 1 and avisos[-1] == vfs_red.BUSQUEDA_TERMINA
	assert not vfs_red.conviene_buscar()


def _esperar(condicion, segundos: float = 5.0) -> bool:
	import time

	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		if condicion():
			return True
		time.sleep(0.02)
	return bool(condicion())


# ── Búsqueda de equipos ──────────────────────────────────────────────────────


def test_descubrimiento_sin_duplicados_y_cancelable():
	parar = threading.Event()
	encontrados, finales = [], []

	def lenta(emitir, cancelado):
		emitir(red_descubrir.EquipoRed("DS220", "\\\\DS220", "shell"))
		cancelado.wait(10)
		parar.set()

	def rapida(emitir, cancelado):
		emitir(red_descubrir.EquipoRed("ds220", "\\\\ds220", "mdns", "192.168.1.150"))
		emitir(red_descubrir.EquipoRed("PC", "\\\\PC", "mdns"))

	busqueda = red_descubrir.Descubrimiento(encontrados.append, lambda lista, cancelada: finales.append((lista, cancelada)),
		30, fuentes=[("lenta", lenta), ("rapida", rapida)]).iniciar()
	assert _esperar(lambda: len(encontrados) == 2)
	assert sorted(e.nombre for e in busqueda.equipos()) == ["DS220", "PC"]
	assert next(e for e in busqueda.equipos() if e.nombre == "DS220").direccion == "192.168.1.150"
	assert not busqueda.terminada
	busqueda.cancelar("Escape")
	assert busqueda.esperar(5) and busqueda.terminada and busqueda.cancelada
	assert finales and finales[0][1] is True and parar.wait(5)


def test_descubrimiento_con_tiempo_maximo():
	def colgada(emitir, cancelado):
		threading.Event().wait(30)

	busqueda = red_descubrir.Descubrimiento(tiempo_maximo_s=1, fuentes=[("colgada", colgada)]).iniciar()
	assert busqueda.esperar(5) and not busqueda.cancelada


def test_registros_mdns_dan_el_equipo_y_su_ip():
	registros = [
		(red_descubrir.DNS_TYPE_PTR, "_smb._tcp.local", "DS220._smb._tcp.local"),
		(red_descubrir.DNS_TYPE_SRV, "DS220._smb._tcp.local", "ds220.local"),
		(red_descubrir.DNS_TYPE_A, "ds220.local", "192.168.1.150"),
		(red_descubrir.DNS_TYPE_PTR, "_smb._tcp.local", "Mac de Ana._smb._tcp.local"),
	]
	equipos = red_descubrir.equipos_de_registros(registros)
	assert equipos[0] == red_descubrir.EquipoRed("ds220", "\\\\ds220", "mdns", "192.168.1.150")
	assert equipos[1].nombre == "Mac de Ana" and equipos[1].direccion == ""


# ── Conectar ─────────────────────────────────────────────────────────────────


def test_conectar_con_recordar_usa_credwrite_y_nunca_guarda_la_contrasena(simulado, datos_temporales, caplog):
	caplog.set_level(logging.DEBUG)
	letra = red.conectar("Z:", "\\\\nas\\fotos\\", "NAS\\ana", CONTRASENA, True, persistente=True, exigir_cifrado=True)
	assert letra == "Z:"
	_tipo, local, remoto, contrasena, usuario, banderas = simulado.wnet.llamadas[-1]
	assert (local, remoto, contrasena, usuario) == ("Z:", "\\\\nas\\fotos", CONTRASENA, "NAS\\ana")
	assert banderas == red.CONNECT_UPDATE_PROFILE | red.CONNECT_REQUIRE_PRIVACY
	assert simulado.cred.escritas == [{"Type": red.CRED_TYPE_DOMAIN_PASSWORD, "TargetName": "nas", "UserName": "NAS\\ana",
		"CredentialBlob": CONTRASENA, "Persist": red.CRED_PERSIST_ENTERPRISE}]
	red_recientes.anotar_reciente("nas")
	assert CONTRASENA not in caplog.text
	for archivo in [p for p in datos_temporales.rglob("*") if p.is_file()]:
		assert CONTRASENA not in archivo.read_text(encoding="utf-8", errors="ignore"), archivo


def test_sin_recordar_no_escribe_credenciales_y_sin_letra_no_es_persistente(simulado):
	assert red.conectar("", "\\\\nas\\docs", "ana", CONTRASENA, False) == ""
	assert simulado.wnet.llamadas[-1][1] is None and simulado.wnet.llamadas[-1][-1] == 0
	assert simulado.cred.escritas == []


def test_la_llamada_de_la_1x_sigue_funcionando(simulado):
	assert red.conectar("z", "\\\\nas\\fotos", "", None, True) == "Z:"
	_tipo, local, remoto, contrasena, usuario, banderas = simulado.wnet.llamadas[-1]
	assert (local, contrasena, usuario, banderas) == ("Z:", None, None, red.CONNECT_UPDATE_PROFILE)
	assert simulado.cred.escritas == []


def test_letra_automatica_con_wnetuseconnection(simulado, monkeypatch):
	pedidas = []

	def usar(hwnd, recurso, contrasena, usuario, banderas, bufer, tamano, resultado):
		pedidas.append((recurso._obj.lpRemoteName, banderas))
		bufer.value = "x:"
		resultado._obj.value = red.CONNECT_LOCALDRIVE
		return 0

	monkeypatch.setattr(red, "_mpr", lambda: SimpleNamespace(WNetUseConnectionW=usar))
	assert red.conectar("*", "\\\\nas\\fotos", persistente=True) == "X:"
	assert pedidas == [("\\\\nas\\fotos", red.CONNECT_REDIRECT | red.CONNECT_UPDATE_PROFILE)]


@pytest.mark.parametrize(("codigo", "texto"), [
	(1272, "invitado"), (64, "Se perdió la conexión"), (1201, "desconectada"), (1240, "no puede iniciar sesión"),
	(6118, "detección de redes"), (1326, "Usuario o contraseña incorrectos"), (1208, "El servidor WebDAV no responde"),
])
def test_mensajes_de_error(simulado, codigo, texto):
	simulado.wnet.errores_conectar.append(codigo)
	with pytest.raises(red.ErrorUnidadRed) as error:
		red.conectar("Z:", "\\\\nas\\fotos")
	assert error.value.codigo == codigo and texto in error.value.mensaje
	assert error.value.pide_credenciales == (codigo == 1326)


def test_aviso_de_elevacion(simulado, monkeypatch):
	monkeypatch.setattr(red, "es_elevado", lambda: True)
	assert "EnableLinkedConnections" in red._mensaje_error(1201)


def test_webdav_con_webclient_deshabilitado_no_intenta_conectar(simulado, monkeypatch):
	monkeypatch.setattr(red, "estado_webclient", lambda: "deshabilitado")
	assert red.validar_remoto("https://nas.ejemplo.org:5006/datos") is None
	with pytest.raises(red.ErrorUnidadRed, match="WebClient"):
		red.conectar("Z:", "https://nas.ejemplo.org:5006/datos")
	assert simulado.wnet.llamadas == []
	monkeypatch.setattr(red, "estado_webclient", lambda: "manual")
	red.conectar("Z:", "https://nas.ejemplo.org:5006/datos", exigir_cifrado=True)
	assert simulado.wnet.llamadas[-1][2] == "https://nas.ejemplo.org:5006/datos" and simulado.wnet.llamadas[-1][-1] == red.CONNECT_UPDATE_PROFILE


def test_rutas_y_servidores():
	assert red.servidor_de("\\\\DS220\\home") == "DS220"
	assert red.servidor_de("https://ds220.local:5006/x") == "ds220.local"
	assert red.servidor_de("\\\\ds220@SSL@5006\\DavWWWRoot\\x") == "ds220"
	assert red.es_servidor("\\\\DS220") and not red.es_servidor("\\\\DS220\\home")
	assert red.es_webdav("\\\\ds220@SSL@5006\\DavWWWRoot") and not red.es_webdav("\\\\ds220\\home")


# ── Desconectar, reconectar y credenciales ───────────────────────────────────


def test_desconectar_y_olvidar_credencial(simulado):
	red.desconectar("z", forzar=False, olvidar=True, olvidar_credencial=True)
	assert simulado.wnet.llamadas[-1] == ("desconectar", "Z:", red.CONNECT_UPDATE_PROFILE, False)
	assert simulado.cred.borradas == [("nas", red.CRED_TYPE_DOMAIN_PASSWORD)]
	simulado.wnet.errores_desconectar.append(red.ERROR_OPEN_FILES)
	with pytest.raises(red.ErrorUnidadRed) as error:
		red.desconectar("\\\\nas\\docs", olvidar=False)
	assert error.value.codigo == red.ERROR_OPEN_FILES and simulado.wnet.llamadas[-1][1:] == ("\\\\nas\\docs", 0, False)


def test_credenciales_guardadas_solo_de_dominio(simulado):
	assert red.credenciales() == [red.Credencial("nas", "nas\\ana", 3)]
	assert red.olvidar_credencial_de("nas") and simulado.cred.borradas == [("nas", 2)]


def test_reconectar_usa_restore_y_si_falla_el_remoto_recordado(simulado, monkeypatch):
	codigos = [0]

	def restaurar(hwnd, letra, interfaz):
		return codigos.pop(0)

	monkeypatch.setattr(red, "_mpr", lambda: SimpleNamespace(WNetRestoreSingleConnectionW=restaurar))
	red.reconectar("Y:")
	assert simulado.wnet.llamadas == []
	codigos.append(1222)
	red.reconectar("Y:")
	assert simulado.wnet.llamadas[-1][:3] == ("conectar", "Y:", "\\\\ds220\\home")
	codigos.append(1326)
	with pytest.raises(red.ErrorUnidadRed) as error:
		red.reconectar("Y:")
	assert error.value.pide_credenciales


def test_1201_al_entrar_reconecta_y_pide_credenciales(simulado, monkeypatch):
	reconexiones = []

	def reconectar(letra, hwnd=0):
		reconexiones.append(letra)
		raise red.error_de_codigo(1326, letra)

	monkeypatch.setattr(red, "reconectar", reconectar)
	decisor = DecisorFalso(credenciales=("ds220\\ana", CONTRASENA, True))
	resolver.fijar_servicios(decisor=decisor)
	proveedor = vfs_red.ProveedorRed()
	assert proveedor.preparar("Y:\\") is True
	assert reconexiones == ["Y:"] and decisor.preguntas[0][0] == "credenciales"
	assert simulado.wnet.llamadas[-1][:5] == ("conectar", "Y:", "\\\\ds220\\home", CONTRASENA, "ds220\\ana")
	assert simulado.cred.escritas[-1]["TargetName"] == "ds220"
	# Una unidad conectada no se toca.
	assert proveedor.preparar("Z:\\fotos") is False
	# Sin «Volver a conectar las unidades al entrar», se avisa con el mensaje de 9.4.
	resolver.fijar_servicios(decisor=decisor, config=ConfigFalsa(**{"red.reconectar_al_entrar": False}))
	with pytest.raises(red.ErrorUnidadRed, match="Intro para volver a conectar") as error:
		proveedor.preparar("Y:\\")
	assert error.value.codigo == red.ERROR_CONNECTION_UNAVAIL
	assert proveedor.preparar("Y:\\", reconectar_siempre=True)


# ── Recursos de un servidor (9.3) ────────────────────────────────────────────


def _recurso(nombre: str, tipo: int, comentario: str = "") -> dict:
	return {"netname": nombre, "type": tipo, "remark": comentario}


def test_recursos_ocultos_e_impresoras(simulado):
	simulado.net.recursos["NAS"] = [
		_recurso("zeta", 0), _recurso("IPC$", 0x80000003), _recurso("Impresora", 1), _recurso("admin$", 0x80000000), _recurso("alfa", 0, "Fotos"),
	]
	assert [(r.nombre, r.tipo) for r in red.recursos("nas")] == [("alfa", "disco"), ("zeta", "disco"), ("Impresora", "impresora")]
	assert [r.nombre for r in red.recursos("\\\\nas", mostrar_ocultos=True)][:3] == ["admin$", "alfa", "IPC$"]
	proveedor = vfs_red.ProveedorRed()
	entradas = proveedor.listar("\\\\nas")
	assert [e.nombre for e in entradas] == ["alfa", "zeta", "Impresora, Impresora"]
	assert entradas[0].ruta == "\\\\nas\\alfa" and entradas[0].es_carpeta and not entradas[2].es_carpeta
	with pytest.raises(base.NoAdmitido, match="impresora"):
		proveedor.abrir_lectura(entradas[2].ruta)
	assert red_recientes.recientes() == ["\\\\nas"]


def test_servidor_pide_credenciales_y_1219_ofrece_cerrar_las_conexiones(simulado, monkeypatch):
	simulado.net.recursos["NAS"] = [_recurso("fotos", 0)]
	simulado.net.errores = [5]
	autenticaciones: list[tuple] = []
	errores_autenticar = [red.ERROR_SESSION_CREDENTIAL_CONFLICT]

	def autenticar(servidor, usuario, contrasena, recordar=False):
		autenticaciones.append((servidor, usuario, recordar))
		if errores_autenticar:
			raise red.error_de_codigo(errores_autenticar.pop(0), servidor)

	cerradas = []
	monkeypatch.setattr(red, "autenticar", autenticar)
	monkeypatch.setattr(red, "cerrar_conexiones_servidor", lambda servidor: cerradas.append(servidor) or 2)
	decisor = DecisorFalso(credenciales=("nas\\ana", CONTRASENA, False), elecciones=[0])
	resolver.fijar_servicios(decisor=decisor)
	entradas = vfs_red.ProveedorRed().listar("\\\\nas")
	assert [e.nombre for e in entradas] == ["fotos"]
	assert [p[0] for p in decisor.preguntas] == ["credenciales", "elegir"]
	assert decisor.preguntas[1][2][0] == "Cerrar las &conexiones a este servidor y reintentar"
	assert "Usar otro &nombre del servidor (su IP)" in decisor.preguntas[1][2]
	assert cerradas == ["nas"] and autenticaciones == [("nas", "nas\\ana", False)] * 2


def test_servidor_credenciales_canceladas(simulado):
	simulado.net.errores = [1326]
	resolver.fijar_servicios(decisor=DecisorFalso(credenciales=None))
	with pytest.raises(base.Cancelado):
		vfs_red.ProveedorRed().listar("\\\\nas")


def test_servidor_1272_da_el_mensaje_de_invitado_sin_decisor(simulado):
	simulado.net.errores = [1272]
	with pytest.raises(red.ErrorUnidadRed, match="invitado"):
		vfs_red.ProveedorRed().listar("\\\\nas")


def test_cerrar_conexiones_de_un_servidor(simulado):
	assert red.conexiones_a_servidor("NAS") == ["Z:", "\\\\nas\\docs", "\\\\nas\\IPC$"]
	assert red.cerrar_conexiones_servidor("nas") == 3
	assert [l[1] for l in simulado.wnet.llamadas] == ["Z:", "\\\\nas\\docs", "\\\\nas\\IPC$"]
	assert all(l[2] == 0 for l in simulado.wnet.llamadas)


# ── Ruta UNC, información y recientes ────────────────────────────────────────


def test_ruta_unc(simulado):
	assert red.ruta_unc("Z:\\a") == "\\\\srv\\rec\\a"
	assert red.ruta_unc("\\\\srv\\rec\\b") == "\\\\srv\\rec\\b"
	with pytest.raises(red.ErrorUnidadRed) as error:
		red.ruta_unc("C:\\Windows")
	assert error.value.codigo == red.ERROR_NOT_CONNECTED


def test_informacion_de_la_conexion(simulado, monkeypatch):
	import win32api

	# Nada toca la unidad real (en este equipo Z: es una unidad WebDAV recordada).
	monkeypatch.setattr(win32api, "GetVolumeInformation", lambda raiz: ("Fotos", 1, 255, 0, "NTFS"))
	monkeypatch.setattr(red_info.shutil, "disk_usage", lambda raiz: SimpleNamespace(free=1_200_000_000_000, total=2_000_000_000_000))
	monkeypatch.setattr(red_info, "conexiones_smb", lambda: (
		[{"ServerName": "nas", "ShareName": "fotos", "UserName": "NAS\\ana", "Dialect": "3.1.1", "NumOpens": 2, "Encrypted": True,
			"Signed": True}],
		[{"ServerName": "nas", "ClientLinkSpeed": 1_000_000_000}],
	))
	info = red_info.informacion("Z:\\fotos")
	assert info.resumen() == "Z:, \\\\nas\\fotos, conectada, SMB 3.1.1 cifrada, usuario NAS\\ana, 1,09 TB libres de 1,82 TB, enlace a 1 Gbps"
	texto = info.texto()
	assert "Archivos abiertos en esta conexión: 2" in texto and "Cifrado SMB: sí" in texto
	assert red_info.velocidad_enlace(2_500_000_000) == "2,5 Gbps"


def test_recientes_sin_duplicados_y_con_limite():
	for numero in range(25):
		red_recientes.anotar_reciente(f"SRV{numero}")
	red_recientes.anotar_reciente("\\\\srv3")
	lista = red_recientes.recientes()
	assert len(lista) == red_recientes.MAX_RECIENTES and lista[0] == "\\\\srv3"
	assert sum(1 for r in lista if r.casefold() == "\\\\srv3") == 1


def test_sesiones_del_servidor(monkeypatch):
	from app.services.windows import red_servidor

	class Net:
		cerradas = []

		def NetSessionEnum(self, nivel, cliente, usuario, *_r):  # noqa: N802
			return [{"client_name": "\\\\PC", "user_name": "ana", "time": 60, "idle_time": 5}], 1, 0

		def NetFileEnum(self, servidor, ruta, usuario, nivel, *_r):  # noqa: N802
			return [{"id": 7, "path_name": "D:\\c\\a.txt", "user_name": "ana", "num_locks": 1}], 1, 0

		def NetFileClose(self, servidor, id_):  # noqa: N802
			self.cerradas.append(id_)

	net = Net()
	monkeypatch.setattr(red_servidor, "_win32net", lambda: net)
	assert red_servidor.sesiones() == [red_servidor.Sesion("PC", "ana", 60, 5)]
	archivo = red_servidor.archivos_abiertos()[0]
	red_servidor.cerrar_archivo(archivo)
	assert net.cerradas == [7]


# ── Prueba real (solo lectura) ───────────────────────────────────────────────


@pytest.mark.interfaz
def test_recursos_reales_de_localhost():
	"""Lee de verdad (sin cambiar nada) los recursos de \\\\localhost: al menos IPC$ existe siempre."""
	recursos = red.recursos("localhost", mostrar_ocultos=True)
	assert any(r.nombre.upper() == "IPC$" for r in recursos)
	assert all(r.ruta.lower().startswith("\\\\localhost\\") for r in recursos)
	assert ctypes.sizeof(red.NETRESOURCEW) > 0
