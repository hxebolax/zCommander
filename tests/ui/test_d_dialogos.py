# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque D: gestor de conexiones, diálogo de sitio, unidades de red y órdenes de red_d.

Los diálogos se construyen sin mostrarlos; las preguntas se sustituyen por
funciones falsas (el ``conftest`` prohíbe los ``ShowModal`` reales).
"""

from __future__ import annotations

import threading

import pytest

wx = pytest.importorskip("wx")

from app.services import conexiones  # noqa: E402
from app.services.vfs import base, resolver  # noqa: E402
from app.services.windows import red  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import red_d  # noqa: E402
from app.ui.dialogos import d_conexiones, d_sitio, d_unidad  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402
from tests.servicios.test_d_ftp import SecretosMemoria  # noqa: E402

#: Teclas que estos diálogos atienden a mano (las de la ventana principal no llegan con un diálogo modal).
TECLAS_PROPIAS: list[str] = []


@pytest.fixture
def repo():
	return conexiones.Conexiones(SecretosMemoria())


@pytest.fixture
def repo_con_sitios(repo):
	repo.guardar(conexiones.Sitio(nombre="Web", servidor="ftp.ejemplo.org", usuario="ana"), "clave")
	repo.guardar(conexiones.Sitio(nombre="Servidor SSH", protocolo="sftp", servidor="ssh.ejemplo.org", puerto=2222, usuario="ana"))
	return repo


# ── Diálogo de sitio ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("protocolo", ["ftp", "ftps", "sftp"])
def test_dialogo_sitio_teclado(app_wx, protocolo):
	sitio = conexiones.Sitio(nombre="x", protocolo=protocolo, servidor="s", usuario="u", puerto=conexiones.PUERTOS[protocolo])
	dialogo = d_sitio.DialogoSitio(None, sitio, tiene_contrasena=True)
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=TECLAS_PROPIAS)
		assert dialogo.campo_clave.IsEnabled() == (protocolo == "sftp")
		assert dialogo.casilla_pasivo.IsEnabled() == (protocolo != "sftp")
	finally:
		dialogo.Destroy()


def test_dialogo_sitio_nuevo_valida_y_cambia_puerto(app_wx, monkeypatch):
	avisos: list[str] = []
	monkeypatch.setattr(d_sitio, "_avisar", lambda padre, mensaje: avisos.append(mensaje))
	dialogo = d_sitio.DialogoSitio(None)
	try:
		assert dialogo.GetTitle() == "Nuevo sitio"
		assert not dialogo.aceptar() and "nombre" in avisos[-1]
		dialogo.campo_nombre.SetValue("Mi web")
		dialogo.campo_servidor.SetValue("ftp://mal")
		assert not dialogo.aceptar() and "servidor" in avisos[-1]
		dialogo.campo_servidor.SetValue("ssh.ejemplo.org")
		dialogo.lista_protocolo.SetSelection(conexiones.PROTOCOLOS.index("sftp"))
		dialogo._al_cambiar_protocolo(None)
		assert dialogo.campo_puerto.GetValue() == 22
		assert not dialogo.aceptar() and "usuario" in avisos[-1]
		dialogo.campo_usuario.SetValue("ana")
		dialogo.campo_contrasena.SetValue("pw")
		dialogo.campo_carpeta.SetValue("home/ana/")
		assert dialogo.aceptar() and dialogo.GetReturnCode() == wx.ID_OK
		sitio = dialogo.sitio()
		assert (sitio.protocolo, sitio.puerto, sitio.carpeta, sitio.usuario) == ("sftp", 22, "/home/ana", "ana")
		assert dialogo.contrasena() == "pw" and dialogo.frase() is None
	finally:
		dialogo.Destroy()


def test_dialogo_sitio_conserva_la_contrasena_guardada(app_wx):
	sitio = conexiones.Sitio(nombre="Web", servidor="s", usuario="ana")
	dialogo = d_sitio.DialogoSitio(None, sitio, tiene_contrasena=True)
	try:
		assert dialogo.campo_contrasena.GetValue() == ""
		assert dialogo.contrasena() is conexiones.MANTENER
		assert dialogo.sitio().id == sitio.id
		dialogo.campo_contrasena.SetValue("nueva")
		assert dialogo.contrasena() == "nueva"
	finally:
		dialogo.Destroy()


# ── Gestor de conexiones ─────────────────────────────────────────────────────

def test_gestor_teclado_con_y_sin_sitios(app_wx, repo, repo_con_sitios):
	for repositorio in (conexiones.Conexiones(SecretosMemoria()), repo_con_sitios):
		dialogo = d_conexiones.DialogoConexiones(None, repositorio)
		try:
			afirmar_teclado_correcto(dialogo, teclas_propias=["Delete", "F2"])
		finally:
			dialogo.Destroy()


def test_gestor_lista_y_conecta(app_wx, repo_con_sitios):
	dialogo = d_conexiones.DialogoConexiones(None, repo_con_sitios)
	try:
		assert dialogo.lista.GetItemCount() == 2
		assert dialogo.lista.GetItemText(0) == "Servidor SSH"
		assert dialogo.lista.GetItemText(0, 2) == "ssh.ejemplo.org:2222"
		assert not dialogo.texto_vacio.IsShown()
		dialogo.conectar()
		assert dialogo.GetReturnCode() == wx.ID_OK and dialogo.sitio_elegido.nombre == "Servidor SSH"
	finally:
		dialogo.Destroy()


def test_gestor_vacio_desactiva_botones(app_wx, repo):
	dialogo = d_conexiones.DialogoConexiones(None, repo)
	try:
		assert dialogo.texto_vacio.IsShown() or not dialogo.IsShown()
		assert not dialogo.boton_conectar.IsEnabled() and dialogo.boton_nuevo.IsEnabled()
	finally:
		dialogo.Destroy()


def test_gestor_nuevo_editar_duplicar_eliminar(app_wx, repo_con_sitios, monkeypatch):
	repo = repo_con_sitios
	confirmaciones: list[str] = []
	monkeypatch.setattr(d_conexiones, "_confirmar", lambda padre, texto: confirmaciones.append(texto) or True)
	monkeypatch.setattr(d_conexiones, "_avisar", lambda padre, texto: pytest.fail(texto))
	dialogo = d_conexiones.DialogoConexiones(None, repo)
	try:
		monkeypatch.setattr(d_conexiones, "_editar", lambda padre, sitio, c, f: (
			conexiones.Sitio(nombre="Archivo", servidor="files.org"), "pw", conexiones.MANTENER))
		dialogo.nuevo()
		assert dialogo.elegido().nombre == "Archivo"
		assert repo.contrasena(dialogo.elegido().id) == "pw"

		def editar(padre, sitio, tiene_contrasena, tiene_frase):
			assert tiene_contrasena
			sitio.nombre = "Archivo público"
			return sitio, conexiones.MANTENER, conexiones.MANTENER

		monkeypatch.setattr(d_conexiones, "_editar", editar)
		dialogo.editar()
		assert dialogo.elegido().nombre == "Archivo público" and repo.contrasena(dialogo.elegido().id) == "pw"
		dialogo.duplicar()
		assert dialogo.elegido().nombre == "Archivo público (copia)"
		copia_id = dialogo.elegido().id
		dialogo.eliminar()
		assert confirmaciones and "copia" in confirmaciones[-1]
		assert repo.obtener(copia_id) is None and not repo.tiene_contrasena(copia_id)
		assert dialogo.lista.GetItemCount() == 3
	finally:
		dialogo.Destroy()


# ── Unidades de red ──────────────────────────────────────────────────────────

def test_dialogo_conectar_unidad(app_wx, monkeypatch):
	avisos: list[str] = []
	monkeypatch.setattr(d_unidad, "_avisar", lambda padre, mensaje, titulo: avisos.append(mensaje))
	dialogo = d_unidad.DialogoConectarUnidad(None, ["Z:", "Y:"])
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=TECLAS_PROPIAS)
		assert not dialogo.campo_usuario.IsEnabled()
		dialogo.campo_remoto.SetValue("servidor\\recurso")
		assert not dialogo.aceptar() and "\\\\servidor\\recurso" in avisos[-1]
		dialogo.campo_remoto.SetValue("\\\\nas\\fotos")
		dialogo.casilla_credenciales.SetValue(True)
		dialogo._actualizar()
		assert not dialogo.aceptar() and "usuario" in avisos[-1]
		dialogo.campo_usuario.SetValue("NAS\\ana")
		dialogo.campo_contrasena.SetValue("pw")
		assert dialogo.aceptar()
		assert dialogo.datos() == ("Z:", "\\\\nas\\fotos", "NAS\\ana", "pw", True)
	finally:
		dialogo.Destroy()


@pytest.mark.parametrize("unidades", [[], [red.UnidadRed("Z:", "\\\\nas\\fotos"), red.UnidadRed("Y:", "\\\\nas\\docs", False, True)]])
def test_dialogo_desconectar_unidad(app_wx, unidades):
	dialogo = d_unidad.DialogoDesconectarUnidad(None, unidades)
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=TECLAS_PROPIAS)
		assert dialogo.boton_desconectar.IsEnabled() == bool(unidades)
		if unidades:
			dialogo.lista.SetSelection(1)
			assert dialogo.elegida().letra == "Y:"
			assert "desconectada" in dialogo.lista.GetString(1)
			assert dialogo.opciones() == (True, False)
		else:
			assert dialogo.elegida() is None
	finally:
		dialogo.Destroy()


def test_servicio_red_valida():
	assert red.validar_remoto("\\\\srv\\recurso") is None
	assert red.validar_remoto("\\\\srv") is not None
	assert red.validar_remoto("C:\\datos") is not None
	assert red.normalizar_letra("z") == "Z:"
	with pytest.raises(base.NombreNoValido):
		red.normalizar_letra("1:")
	assert all(len(letra) == 2 for letra in red.letras_libres())
	assert "Usuario o contraseña incorrectos" in red._mensaje_error(1326)


# ── Órdenes ──────────────────────────────────────────────────────────────────

def test_ordenes_de_red_sin_provisionales():
	from app.ui import ordenes

	for orden in ordenes.CATALOGO if hasattr(ordenes, "CATALOGO") else ordenes.POR_ID.values():
		if orden.manejador.startswith("red_d."):
			funcion = getattr(red_d, orden.manejador.split(".", 1)[1])
			assert not getattr(funcion, "provisional", False), orden.id


class PanelFalso:
	def __init__(self, proveedor, ruta, historial) -> None:
		self.proveedor = proveedor
		self.ruta = ruta
		self._historial = historial
		self.idas: list[tuple] = []

	def historial(self):
		return self._historial

	def ir_a(self, ruta, proveedor=None, cursor=None, al_terminar=None, historial=True, forzar_aqui=False):
		self.idas.append((ruta, proveedor))
		if al_terminar is not None:
			al_terminar(True)

	def es_local(self):
		return self.proveedor.esquema == "local"


class ContextoFalso:
	def __init__(self, panel) -> None:
		self.objetivo = self.activo = panel

	def estado(self, texto):
		pass


def test_desconectar_vuelve_a_la_ultima_carpeta_local(app_wx, tmp_path):
	from app.services.vfs.ftp import ProveedorFTP

	proveedor = ProveedorFTP("ftp.ejemplo.org", 21, "ana", "x")
	panel = PanelFalso(proveedor, "/docs", ["ftp://ana@ftp.ejemplo.org/docs", str(tmp_path), "C:\\"])
	red_d.desconectar(ContextoFalso(panel))
	assert panel.idas == [(str(tmp_path), resolver.proveedor_local())]
	# En un panel local no hace nada.
	local = PanelFalso(resolver.proveedor_local(), "C:\\", [])
	red_d.desconectar(ContextoFalso(local))
	assert local.idas == []


def test_decisor_inmediato_muestra_y_responde(app_wx, monkeypatch):
	def mostrar(dialogo):
		if hasattr(dialogo, "ids_opciones"):
			return dialogo.ids_opciones[1]
		dialogo.campo.SetValue("secreta")
		return wx.ID_OK

	monkeypatch.setattr(wx.Dialog, "ShowModal", mostrar)
	decisor = red_d.DecisorInmediato(None)
	resultados: dict[str, object] = {}

	def preguntar():
		resultados["eleccion"] = decisor.elegir("Servidor desconocido", "Huella SHA256:abc", ["&Uno", "&Dos", "&Cancelar"], 0, 2)
		resultados["texto"] = decisor.pedir_texto("Contraseña de ana@srv", "&Contraseña:", oculto=True)

	hilo = threading.Thread(target=preguntar, daemon=True)
	hilo.start()
	assert procesar_eventos(lambda: "texto" in resultados, segundos=5)
	hilo.join(2)
	assert resultados == {"eleccion": 1, "texto": "secreta"}
	with pytest.raises(RuntimeError):
		decisor.elegir("x", "y", ["&A"])
