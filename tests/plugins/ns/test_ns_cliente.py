# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cliente DSM contra el simulador (diseño 2.0, 13.1, 13.2 y 13.13): sesión, 2FA, reintentos, JSON, solo lectura, huella y registro."""

from __future__ import annotations

import io
import logging

import pytest

from app.plugins import api

from .conftest import PreguntasFalsas, SecretosFalsos, cliente_de, generar_certificado, logins, servidor_de


# ── Inicio de sesión ─────────────────────────────────────────────────────────


def test_inicio_correcto_y_info(ns, arrancar):
	simulador = arrancar()
	cliente = cliente_de(ns, simulador)
	assert cliente.conectado
	assert cliente.info.modelo == "DS220+"
	assert cliente.info.version == "DSM 7.3.2-86009 Update 5"
	assert cliente.info.aviso == ""
	assert cliente.info.administrador
	assert len(cliente.catalogo) == 841
	login = logins(simulador)[-1]
	assert login["version"] == "7" and login["params"]["passwd"] == "***"
	assert "session" in login["params"] and "enable_syno_token" in login["params"]
	cliente.desconectar()
	assert not simulador.estado.sesiones


def test_contrasena_incorrecta_400_un_solo_intento(ns, arrancar):
	simulador = arrancar()
	with pytest.raises(ns.errores.ErrorAutenticacion) as error:
		cliente_de(ns, simulador, contrasena="mala")
	assert error.value.codigo == 400
	assert error.value.mensaje == "Usuario o contraseña incorrectos."
	assert len(logins(simulador)) == 1


def test_ip_bloqueada_407_no_reintenta(ns, arrancar):
	simulador = arrancar()
	simulador.fallos.bloquear_tras = 1
	with pytest.raises(ns.errores.IPBloqueada) as error:
		cliente_de(ns, simulador, contrasena="mala")
	assert "bloqueado" in error.value.mensaje
	assert len(logins(simulador)) == 1


def test_2fa_codigo_device_id_y_siguiente_sin_codigo(ns, arrancar):
	simulador = arrancar()
	secretos = SecretosFalsos()
	preguntas = PreguntasFalsas(codigos=[("123456", True)])
	sonidos: list[str] = []
	servidor = servidor_de(ns, simulador, "prueba2fa")
	cliente = ns.cliente.ClienteDSM(servidor, secretos, preguntas, contrasena="prueba2fa", sonar=sonidos.append)
	cliente.conectar()
	assert [p[0] for p in preguntas.preguntado] == ["codigo"]
	assert "otp" in sonidos
	assert secretos.obtener("prueba:device_id")
	cliente.desconectar()
	otra = PreguntasFalsas()
	segundo = ns.cliente.ClienteDSM(servidor_de(ns, simulador, "prueba2fa"), secretos, otra, contrasena="prueba2fa")
	segundo.conectar()
	assert otra.preguntado == []
	assert logins(simulador)[-1]["params"]["device_id"] == "***"


def test_2fa_codigo_incorrecto_404_cuenta_intentos(ns, arrancar):
	simulador = arrancar()
	preguntas = PreguntasFalsas(codigos=[("000000", False), ("123456", False)])
	cliente = ns.cliente.ClienteDSM(servidor_de(ns, simulador, "prueba2fa"), SecretosFalsos(), preguntas, contrasena="prueba2fa")
	cliente.conectar()
	mensajes = [m for tipo, m in preguntas.preguntado if tipo == "codigo"]
	assert len(mensajes) == 2 and "Le quedan 2 intentos" in mensajes[1]


def test_contrasena_preguntada_y_guardada_cifrada(ns, arrancar):
	simulador = arrancar()
	secretos = SecretosFalsos()
	preguntas = PreguntasFalsas(credenciales=("demo", "demo", True))
	cliente = cliente_de(ns, simulador, contrasena=None, preguntas=preguntas, secretos=secretos, recordar_contrasena=True)
	assert cliente.conectado
	assert secretos.obtener("prueba:contrasena") == "demo"


def test_106_durante_una_peticion_un_solo_reintento(ns, arrancar):
	simulador = arrancar()
	cliente = cliente_de(ns, simulador)
	antes = len(logins(simulador))
	simulador.fallos.caducar_en = 1
	assert cliente.llamar("SYNO.DSM.Info", "getinfo")["model"] == "DS220+"
	assert len(logins(simulador)) == antes + 1


def test_dos_caducidades_seguidas_no_hacen_bucle(ns, arrancar):
	simulador = arrancar()
	cliente = cliente_de(ns, simulador)
	simulador.estado.sesiones.clear()
	cliente._iniciador.contrasena = None
	antes = len(logins(simulador))
	with pytest.raises(ns.errores.ErrorSesion):
		cliente.llamar("SYNO.DSM.Info", "getinfo")
	assert len(logins(simulador)) == antes


def test_http_502_y_respuesta_cortada_en_espanol(ns, arrancar):
	simulador = arrancar()
	cliente = cliente_de(ns, simulador)
	simulador.fallos.http_502 = 1
	with pytest.raises(ns.errores.ErrorConexion, match="HTTP 502"):
		cliente.llamar("SYNO.DSM.Info", "getinfo")
	simulador.fallos.cortar = 1
	with pytest.raises(ns.errores.ErrorConexion, match="incompleta|perdido la conexión"):
		cliente.llamar("SYNO.DSM.Info", "getinfo")


def test_contrasena_nunca_por_http_salvo_local(ns):
	servidor = ns.servidores.ServidorNAS("casa", "NAS de casa", "192.0.2.10", 5000, https=False, usuario="pepe")
	cliente = ns.cliente.ClienteDSM(servidor, None, None, contrasena="x")
	with pytest.raises(ns.errores.AccesoDSM, match="HTTP"):
		cliente.conectar()


# ── Codificación JSON y versiones ────────────────────────────────────────────


def test_codificacion_json_de_parametros(ns, arrancar):
	codificar = ns.cliente.codificar_parametros
	assert codificar({"name": "plex"}, True) == {"name": '"plex"'}
	assert codificar({"path": ["/a", "/b"], "force": False, "limit": -1}, True) == {"path": '["/a", "/b"]', "force": "false",
		"limit": "-1"}
	assert codificar({"account": "pepe", "enable": True}, False) == {"account": "pepe", "enable": "true"}
	simulador = arrancar("simular")
	cliente = cliente_de(ns, simulador, solo_lectura=False)
	cliente.llamar("SYNO.Docker.Container", "stop", name="jellyfin")
	enviada = [p for p in simulador.peticiones if p["api"] == "SYNO.Docker.Container"][-1]
	assert enviada["params"]["name"] == '"jellyfin"'
	assert enviada["cabecera_token"] is True
	assert simulador.diario[-1]["params"]["name"] == "jellyfin"


def test_version_max_min_preferida(ns, arrancar):
	assert ns.catalogo.elegir_version(2, 2, 1) == 2
	assert ns.catalogo.elegir_version(1, 3, 7) == 3
	simulador = arrancar()
	cliente = cliente_de(ns, simulador)
	catalogo = cliente.catalogo
	assert catalogo.version("SYNO.DSM.Info") == 2
	assert catalogo.version("SYNO.FileStation.Upload") == 3
	assert catalogo.version("SYNO.API.Auth") == 7
	assert catalogo.version("SYNO.Core.System", 1) == 1
	with pytest.raises(ns.errores.FuncionAusente, match="Hyper Backup"):
		catalogo.version("SYNO.Backup.Task")


# ── Solo lectura ─────────────────────────────────────────────────────────────


def test_solo_lectura_bloquea_en_el_cliente_sin_enviar(ns, arrancar):
	simulador = arrancar("escritura")
	cliente = cliente_de(ns, simulador)
	antes = len(simulador.peticiones)
	with pytest.raises(api.SoloLectura) as error:
		cliente.llamar("SYNO.Core.Package.Control", "start", id="Python2")
	assert error.value.mensaje.startswith("Operación bloqueada: el servidor está en modo de solo lectura")
	assert len(simulador.peticiones) == antes
	assert simulador.diario == []
	assert cliente.llamar("SYNO.Core.Package", "list")["total"] == 23


def test_simulador_en_lectura_da_116_en_espanol(ns, arrancar):
	simulador = arrancar("lectura")
	cliente = cliente_de(ns, simulador, solo_lectura=False)
	with pytest.raises(ns.errores.SoloLecturaDSM) as error:
		cliente.llamar("SYNO.Core.Package.Control", "start", id="Python2")
	assert error.value.codigo == 116
	assert error.value.mensaje == "Operación bloqueada: el servidor está en modo de solo lectura."


def test_simulador_en_simular_apunta_en_el_diario_sin_cambiar(ns, arrancar):
	simulador = arrancar("simular")
	cliente = cliente_de(ns, simulador)
	cliente.permitir_cambios(True)
	cliente.llamar("SYNO.Core.Package.Control", "start", id="Python2")
	assert simulador.diario[-1]["api"] == "SYNO.Core.Package.Control" and simulador.diario[-1]["aplicado"] is False
	assert next(p for p in cliente.llamar("SYNO.Core.Package", "list")["packages"] if p["id"] == "Python2")["additional"]["status"] == "stop"
	cliente.permitir_cambios(False)
	assert cliente.solo_lectura


def test_lista_blanca_de_lectura(ns):
	es_lectura = ns.metodos_lectura.es_lectura
	assert es_lectura("SYNO.Core.System", "info") and not es_lectura("SYNO.Core.System", "shutdown")
	assert es_lectura("SYNO.FileStation.Search", "start") and es_lectura("SYNO.FileStation.MD5", "start")
	assert not es_lectura("SYNO.FileStation.CopyMove", "start") and not es_lectura("SYNO.Storage.CGI.Smart", "secure_erase")
	assert es_lectura("SYNO.Core.DSMNotify", "notify", {"action": "load"}) and not es_lectura("SYNO.Core.DSMNotify", "notify", {})
	assert not es_lectura("SYNO.Algo.Desconocido", "hacer_magia")
	assert not es_lectura("SYNO.Core.Package.Control", "start")


# ── HTTPS con huella fijada ──────────────────────────────────────────────────


def test_huella_fijada_y_rechazada_si_cambia_el_certificado(ns, arrancar, tmp_path):
	cert1 = generar_certificado(tmp_path, "uno")
	cert2 = generar_certificado(tmp_path, "dos")
	primero = arrancar(https=True, certificado=cert1)
	guardados = []
	preguntas = PreguntasFalsas(huellas=["recordar"])
	servidor = servidor_de(ns, primero)
	cliente = ns.cliente.ClienteDSM(servidor, None, preguntas, contrasena="demo", al_guardar_servidor=guardados.append)
	cliente.conectar()
	assert servidor.huella.startswith("SHA256:") and guardados
	assert preguntas.preguntado == [("huella", "")]
	cliente.desconectar()
	# El «mismo» NAS presenta otro certificado: se avisa antes de enviar nada y, si no se acepta, no hay conexión.
	segundo = arrancar(https=True, certificado=cert2)
	servidor.puerto = segundo.puerto
	sonidos: list[str] = []
	otras = PreguntasFalsas(huellas=["cancelar"])
	cliente2 = ns.cliente.ClienteDSM(servidor, None, otras, contrasena="demo", sonar=sonidos.append)
	with pytest.raises(ns.errores.HuellaRechazada):
		cliente2.conectar()
	assert otras.preguntado == [("huella", servidor.huella)]
	assert "red.huella" in sonidos
	assert segundo.peticiones == deque_vacia()


def deque_vacia():
	from collections import deque

	return deque(maxlen=500)


def test_huella_legible_por_grupos(ns):
	assert ns.cliente.huella_legible("SHA256:" + "AB12" * 16).startswith("AB12 AB12 AB12")


# ── Aviso de seguridad (synology.md 0.1) ─────────────────────────────────────


def test_aviso_de_la_actualizacion_de_seguridad(ns):
	aviso = ns.cliente.aviso_seguridad
	assert "CVE-2026-40530" in aviso("DSM 7.3.2-86009 Update 1")
	assert "CVE-2026-40530" in aviso("DSM 7.3.1-86003")
	assert aviso("DSM 7.3.2-86009 Update 2") == aviso("DSM 7.3.2-86009 Update 5") == ""


# ── Registro sin secretos ────────────────────────────────────────────────────


def test_el_registro_no_contiene_secretos(ns, arrancar, caplog, tmp_path):
	simulador = arrancar("escritura")
	secretos = SecretosFalsos()
	preguntas = PreguntasFalsas(codigos=[("123456", True)], contrasena_dsm="prueba2fa")
	with caplog.at_level(logging.DEBUG):
		servidor = servidor_de(ns, simulador, "prueba2fa", solo_lectura=False)
		cliente = ns.cliente.ClienteDSM(servidor, secretos, preguntas, contrasena="prueba2fa", registro_detallado=True,
			carpeta_temporal=tmp_path)
		cliente.conectar()
		sesion = cliente._sesion
		cliente.llamar("SYNO.Core.Package", "list")
		token = cliente.confirmar_contrasena()
		cliente.subir("/Documentos", "secreto.txt", io.BytesIO(b"hola"), 4)
		with cliente.descargar("/Documentos/secreto.txt") as flujo:
			assert flujo.read() == b"hola"
		cliente.desconectar()
	texto = caplog.text
	for secreto in ("prueba2fa", sesion.sid, sesion.synotoken, secretos.obtener("prueba:device_id"), "123456", token):
		assert secreto and secreto not in texto, secreto
