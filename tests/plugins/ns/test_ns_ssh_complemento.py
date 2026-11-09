# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Herramientas SSH (13.8, con un ejecutor falso: nunca un sshd real), activación, manifiesto, servidores guardados y NAS de demostración."""

from __future__ import annotations

import json

import pytest

from app.plugins import api, manifiesto, registro
from app.plugins.api import pruebas

from .conftest import CARPETA


class EjecutorFalso:
	def __init__(self, salida: str = "correcto", codigo: int = 0, error: str = "") -> None:
		self.salida, self.codigo, self.error = salida, codigo, error
		self.ordenes: list[tuple[str, bytes]] = []

	def ejecutar(self, orden: str, entrada: bytes = b"", tiempo: float = 120) -> tuple[int, str, str]:
		self.ordenes.append((orden, entrada))
		return self.codigo, self.salida, self.error

	def cerrar(self) -> None:
		pass


# ── SSH ──────────────────────────────────────────────────────────────────────


def test_ordenes_ssh_con_comillas_y_sudo_por_la_entrada(ns):
	ejecutor = EjecutorFalso()
	herramientas = ns.ssh.HerramientasSSH(ejecutor, lambda: True, "NAS")
	herramientas.smart("sata1", "clave-sudo")
	orden, entrada = ejecutor.ordenes[-1]
	assert orden == "sudo -S -p '' smartctl -a -d sat /dev/sata1"
	assert entrada == b"clave-sudo\n" and "clave-sudo" not in orden
	herramientas.registros("jellyfin", "x", 500)
	assert ejecutor.ordenes[-1][0] == "sudo -S -p '' docker logs --tail 500 jellyfin"
	assert ns.ssh.orden_compose("/volume1/docker/mi proyecto") == (
		"sudo -S -p '' sh -c 'docker compose -f '\"'\"'/volume1/docker/mi proyecto/compose.yaml'\"'\"' pull && "
		"docker compose -f '\"'\"'/volume1/docker/mi proyecto/compose.yaml'\"'\"' up -d'")


@pytest.mark.parametrize("malo", ["sata1; rm -rf /", "../sda", "jellyfin && reboot", "$(reboot)"])
def test_ssh_rechaza_inyecciones(ns, malo):
	with pytest.raises(api.NombreNoValido):
		ns.ssh.orden_smart(malo)
	with pytest.raises(api.NombreNoValido):
		ns.ssh.orden_registros(malo)
	with pytest.raises(api.NombreNoValido):
		ns.ssh.orden_compose("/volume1/docker/../../etc")


def test_ssh_escritura_bloqueada_en_solo_lectura(ns):
	ejecutor = EjecutorFalso()
	herramientas = ns.ssh.HerramientasSSH(ejecutor, lambda: True, "NAS")
	with pytest.raises(api.SoloLectura):
		herramientas.paquete("ContainerManager", "restart", "x")
	with pytest.raises(api.SoloLectura):
		herramientas.webapi("SYNO.Core.System", "shutdown", 1, "x")
	assert ejecutor.ordenes == []
	ns.ssh.HerramientasSSH(ejecutor, lambda: False, "NAS").paquete("ContainerManager", "restart", "x")
	assert ejecutor.ordenes[-1][0] == "sudo -S -p '' synopkg restart ContainerManager"


def test_ssh_synowebapi_usa_los_mismos_analizadores(ns):
	ejecutor = EjecutorFalso(json.dumps({"success": True, "data": {"model": "DS220+"}}))
	herramientas = ns.ssh.HerramientasSSH(ejecutor, lambda: True)
	assert herramientas.webapi("SYNO.Core.System", "info", 3, "x") == {"model": "DS220+"}
	assert ejecutor.ordenes[-1][0] == "sudo -S -p '' synowebapi --exec api=SYNO.Core.System method=info version=3"
	fallo = ns.ssh.HerramientasSSH(EjecutorFalso(json.dumps({"success": False, "error": {"code": 105}})), lambda: True)
	with pytest.raises(api.ErrorAcceso):
		fallo.webapi("SYNO.Core.User", "list", 1, "x")
	sudo_mal = ns.ssh.HerramientasSSH(EjecutorFalso("", 1, "Sorry, try again."), lambda: True)
	with pytest.raises(ns.errores.ErrorDSM, match="contraseña de sudo"):
		sudo_mal.estadisticas("x")


# ── Complemento ──────────────────────────────────────────────────────────────


def test_manifiesto_completo_y_sin_provisionales(ns):
	datos = manifiesto.leer(CARPETA)
	assert datos.bloque == "NS" and len(datos.ordenes) == 14
	assert {c["clave"] for c in datos.tabla("configuracion")} == {"tiempo_conexion_s", "tiempo_peticion_s", "refresco_estado_s",
		"anunciar_avisos", "aviso_temperatura_c", "ssh_activado", "registro_detallado", "demostracion_modo", "escritura_hasta"}
	assert {s["id"] for s in datos.sonidos} == {"conectado", "desconectado", "aviso_salud", "tarea_fin", "cambios_permitidos",
		"demostracion_iniciada", "otp"}
	assert all((CARPETA / "sonidos" / f"{s['id']}.wav").is_file() for s in datos.sonidos)
	assert (CARPETA / "LICENSE").is_file() and (CARPETA / "doc" / "es" / "leeme.md").is_file()
	for orden in datos.ordenes:
		funcion = registro.manejador(f"zc.synology:{orden.id}")
		assert funcion is not None and not getattr(funcion, "provisional", False), orden.id
	assert next(o for o in datos.ordenes if o.id == "estado").teclas == ("Ctrl+Shift+F9",)


def test_esquema_registrado_y_unidades(ns, tmp_path):
	from app.services.vfs import resolver

	with pytest.raises(api.NoEncontrado):
		resolver.abrir_ruta("synology://no_existe/")
	complemento = ns.complemento
	nombres = {u.texto for u in complemento._unidades()}
	assert isinstance(nombres, set)


def test_desconectar_sin_conexion_no_pregunta(ns):
	zc = pruebas.anfitrion_de_prueba(CARPETA)
	zc.instancia = ns.complemento
	zc.anuncios.clear()
	ns.complemento.zc = zc
	zc.ejecutar("desconectar")
	assert zc.anuncios[-1] == ("No hay ningún NAS conectado.", api.NORMAL)


def test_servidores_guardados_sin_secretos(ns, tmp_path):
	almacen = ns.servidores.AlmacenServidores(tmp_path)
	nuevo = ns.servidores.ServidorNAS(ns.servidores.id_desde_nombre("NAS de casa"), "NAS de casa", "192.168.1.50", usuario="pepe")
	assert nuevo.id == "nas_de_casa" and nuevo.solo_lectura is True
	almacen.guardar(nuevo)
	almacen.guardar(ns.servidores.ServidorNAS("demo", "NAS de demostración", "127.0.0.1", demostracion=True))
	texto = (tmp_path / "servidores.json").read_text(encoding="utf-8")
	assert '"version": 1' in texto and '"contrasena"' not in texto and "passwd" not in texto and "demostración" not in texto
	otro = ns.servidores.AlmacenServidores(tmp_path)
	assert [s.id for s in otro.todos()] == ["nas_de_casa"]
	(tmp_path / "servidores.json").write_text("{roto", encoding="utf-8")
	assert ns.servidores.AlmacenServidores(tmp_path).todos() == []


def test_nas_de_demostracion_arranca_y_se_para(ns, tmp_path):
	sonidos: list[str] = []
	conexiones = ns.conexiones.Conexiones(ns.servidores.AlmacenServidores(tmp_path), sonar=sonidos.append)
	conexion = conexiones.demostracion("escritura")
	try:
		assert conexion.demostracion and conexion.solo_lectura
		assert conexion.servidor.host == "127.0.0.1" and conexion.simulador.modo == "escritura"
		assert conexion.info.modelo == "DS220+"
		assert "demostracion_iniciada" in sonidos
		assert ns.servidores.AlmacenServidores(tmp_path).todos() == []
		simulador = conexion.simulador
	finally:
		conexiones.desconectar_todas()
	assert not simulador.activo
	assert conexiones.activas() == []
