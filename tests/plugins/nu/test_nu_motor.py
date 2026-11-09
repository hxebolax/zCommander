# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor rclone de Nubes con el binario real (diseño 2.0, 12.2, 12.3 y 12.13).

rcd en 127.0.0.1 con puerto aleatorio, comprobación del dueño del puerto con
``GetExtendedTcpTable`` antes de enviar nada, credenciales nuevas en cada
intento, ``rclone.conf`` cifrado antes de la primera cuenta, sin ``rclone.log``
y con ``stderr`` redactado en el registro, Job Object y parada ordenada.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import textwrap
import time

import pytest

from app.plugins import api
from tests.plugins.nu.comun import (
	RAIZ,
	RCLONE,
	crear_memoria,
	modulo,
	requiere_rclone,
)

pytestmark = [pytest.mark.componentes, requiere_rclone]


def test_rcd_arranca_en_127_0_0_1_con_puerto_aleatorio_y_config_cifrada(nubes, secretos_temporales):
	motor = modulo("motor")
	cliente = nubes.cliente()
	assert nubes.motor.vivo()
	assert cliente.anfitrion == "127.0.0.1"
	assert motor.dueno_puerto(cliente.puerto) == nubes.motor.pid
	assert int(cliente.llamar("core/pid")["pid"]) == nubes.motor.pid
	assert nubes.motor.version == motor.VERSION_PROBADA
	contenido = nubes.rutas.config.read_text(encoding="utf-8")
	assert contenido.startswith(motor.MARCA_CIFRADO)
	assert "RCLONE_ENCRYPT_V0:" in contenido
	assert secretos_temporales.obtener("plugin:zc.nubes:rclone_config_pass")
	# Una cuenta nueva deja el archivo cifrado (los tokens nunca llegan en claro al disco).
	crear_memoria(nubes)
	assert nubes.rutas.config.read_text(encoding="utf-8").startswith(motor.MARCA_CIFRADO)
	assert "[mem]" not in nubes.rutas.config.read_text(encoding="utf-8")


def test_los_secretos_no_van_en_los_argumentos_y_no_hay_rclone_log(nubes):
	capturados: list[tuple[list[str], dict[str, str]]] = []
	original = nubes.motor._lanzar

	def espia(argumentos, entorno):
		capturados.append((list(argumentos), dict(entorno)))
		return original(argumentos, entorno)

	nubes.motor._lanzar = espia
	nubes.cliente()
	argumentos, entorno = capturados[-1]
	texto = " ".join(argumentos)
	assert "--log-file" not in texto and "--rc-no-auth" not in texto and "--rc-web-gui" not in texto
	assert "--rc-allow-origin" not in texto
	assert entorno["RCLONE_CONFIG_PASS"] not in texto and entorno["RCLONE_RC_PASS"] not in texto
	assert os.path.isabs(argumentos[0])
	datos = nubes.rutas.config.parent.parent
	assert not list(datos.rglob("rclone.log"))
	assert not list(datos.rglob("*.log"))


def test_credenciales_y_puerto_nuevos_si_otro_proceso_tiene_el_puerto(zc, nubes):
	"""Si el dueño del puerto no es el hijo, no se envía nada y el reintento usa otro puerto y otras credenciales."""
	impostor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	impostor.bind(("127.0.0.1", 0))
	impostor.listen(5)
	impostor.settimeout(0.2)
	ocupado = impostor.getsockname()[1]
	recibido: list[bytes] = []
	parar = False

	def escuchar() -> None:
		while not parar:
			try:
				conexion, _dir = impostor.accept()
			except OSError:
				continue
			conexion.settimeout(1)
			try:
				recibido.append(conexion.recv(65536))
			except OSError:
				pass
			conexion.close()

	import threading

	hilo = threading.Thread(target=escuchar, daemon=True)
	hilo.start()
	puertos = iter([ocupado])
	motor = modulo("motor")
	nubes.motor._elegir_puerto = lambda: next(puertos, None) or motor.puerto_libre()
	try:
		nubes.cliente()
	finally:
		parar = True
		hilo.join(2)
		impostor.close()
	assert len(nubes.motor.intentos) >= 2
	(primer_puerto, primer_usuario), (segundo_puerto, segundo_usuario) = nubes.motor.intentos[0], nubes.motor.intentos[-1]
	assert primer_puerto == ocupado and segundo_puerto != ocupado
	assert primer_usuario != segundo_usuario
	assert not any(recibido), "se envió una petición al proceso que no era el hijo"
	assert nubes.motor.vivo()


def test_sin_contrasena_de_configuracion_da_un_error_claro(nubes):
	motor = modulo("motor")
	nubes.cliente()
	crear_memoria(nubes)
	nubes.motor.detener()
	# La contraseña de rclone.conf desaparece (otro equipo, otro usuario): el archivo se aparta y se avisa.
	nubes.zc.secretos.borrar(motor.SECRETO_CONFIG)
	nubes.cliente()
	apartados = list(nubes.rutas.config.parent.glob("rclone.conf.ilegible-*"))
	assert apartados, "el rclone.conf ilegible debe apartarse"
	assert "otro usuario o equipo" in "".join(t for t, _n in nubes.zc.anuncios)
	assert "mem" not in nubes.remotos()


def test_arrancar_sin_rclone_config_pass_con_ask_password_false_falla_con_mensaje(nubes):
	nubes.cliente()
	crear_memoria(nubes)
	nubes.motor.detener()
	original = nubes.motor._entorno

	def sin_contrasena(*argumentos):
		entorno = original(*argumentos)
		entorno.pop("RCLONE_CONFIG_PASS")
		return entorno

	nubes.motor._entorno = sin_contrasena
	with pytest.raises(api.ErrorAcceso) as error:
		nubes.motor.arrancar()
	assert "configuración cifrada" in error.value.mensaje
	assert not nubes.motor.vivo()


def test_un_rclone_conf_sin_marca_con_cuentas_no_se_usa(nubes):
	motor = modulo("motor")
	nubes.rutas.config.parent.mkdir(parents=True, exist_ok=True)
	nubes.rutas.config.write_text("[abierta]\ntype = memory\n", encoding="utf-8")
	with pytest.raises(api.ErrorAcceso):
		nubes.cliente()
	assert motor.estado_configuracion(nubes.rutas.config) == "sin_cifrar"
	assert not nubes.motor.vivo()


def test_si_el_cifrado_falla_se_aborta_sin_guardar_nada(nubes):
	motor = modulo("motor")

	class Resultado:
		codigo, salida, errores, cancelado = 1, b"", b"error", False

	nubes.configuracion._ejecutar = lambda *a, **k: Resultado()
	with pytest.raises(api.ErrorArchivos) as error:
		nubes.configuracion.asegurar()
	assert "No se pudo cifrar la configuración" in error.value.mensaje
	assert not nubes.rutas.config.exists()
	assert motor.estado_configuracion(nubes.rutas.config) == "vacia"


def test_stderr_de_rclone_llega_redactado_al_registro(nubes, caplog):
	errores = modulo("errores")
	texto = 'token={"access_token":"ABC123secreto","refresh_token":"RT999"} Authorization: Bearer XYZ RCLONE_CONFIG_PASS=claveclara'
	limpio = errores.redactar(texto)
	for secreto in ("ABC123secreto", "RT999", "XYZ", "claveclara"):
		assert secreto not in limpio
	caplog.set_level(logging.INFO, logger="zcplugins.zc.nubes.rclone")
	nubes.cliente()
	nubes.zc_marca = True
	# Un error real de rclone en stderr: listar una ruta que no existe.
	with pytest.raises(api.NoEncontrado):
		nubes.llamar("operations/list", fs=":memory:", remote="no/existe/token=SECRETO1")
	limite = time.monotonic() + 5
	while time.monotonic() < limite and not any("no/existe" in r.getMessage() for r in caplog.records):
		time.sleep(0.1)
	mensajes = [r.getMessage() for r in caplog.records if r.name == "zcplugins.zc.nubes.rclone"]
	assert any("directory not found" in m or "no/existe" in m for m in mensajes)
	assert not any("SECRETO1" in m for m in mensajes)


def test_motor_detenido_suena_y_el_siguiente_uso_lo_arranca(zc, nubes):
	nubes.cliente()
	pid = nubes.motor.pid
	nubes.motor._proceso.kill()
	limite = time.monotonic() + 10
	while time.monotonic() < limite and "zc.nubes:motor_detenido" not in zc.sonidos_pedidos:
		time.sleep(0.05)
	assert "zc.nubes:motor_detenido" in zc.sonidos_pedidos
	nubes.cliente()
	assert nubes.motor.vivo() and nubes.motor.pid != pid


def test_al_detener_para_el_motor_si_no_hay_trabajo(zc, nubes):
	assert zc.detenciones, "activar() debe registrar al_detener del componente rclone"
	nubes.cliente()
	assert zc.detenciones[0]() is True
	assert not nubes.motor.vivo()


def test_desactivar_cierra_rcd(zc, nubes):
	nubes.cliente()
	proceso = nubes.motor._proceso
	zc.instancia.desactivar()
	assert proceso.poll() is not None


def test_matar_el_padre_mata_rclone_por_el_job_object(tmp_path):
	"""Un proceso hijo arranca rclone con ``procesos.popen``; al matarlo, Windows mata también rclone."""
	guion = tmp_path / "padre.py"
	guion.write_text(textwrap.dedent(f"""
		import subprocess, sys, time
		sys.path.insert(0, {str(RAIZ)!r})
		from app.core import procesos
		hijo = procesos.popen([{str(RCLONE)!r}, "rcd", "--rc-addr", "127.0.0.1:0", "--rc-user", "u", "--rc-pass", "p",
			"--config", {str(tmp_path / 'vacia.conf')!r}], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		print(hijo.pid, flush=True)
		time.sleep(60)
	"""), encoding="utf-8")
	padre = subprocess.Popen([sys.executable, str(guion)], stdout=subprocess.PIPE, text=True, creationflags=0x08000000)
	try:
		pid = int(padre.stdout.readline().strip())
		assert _vivo(pid)
	finally:
		padre.kill()
		padre.wait(10)
	limite = time.monotonic() + 10
	while time.monotonic() < limite and _vivo(pid):
		time.sleep(0.1)
	assert not _vivo(pid), "rclone sobrevivió a su padre"


def _vivo(pid: int) -> bool:
	import ctypes

	manejador = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)
	if not manejador:
		return False
	try:
		return ctypes.windll.kernel32.WaitForSingleObject(manejador, 0) == 0x102
	finally:
		ctypes.windll.kernel32.CloseHandle(manejador)
