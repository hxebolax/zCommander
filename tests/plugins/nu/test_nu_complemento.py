# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Complemento Nubes sin red (diseño 2.0, 12 y 18.2): manifiesto, órdenes, sonidos, errores, catálogo y cuentas."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.plugins import api, manifiesto, registro
from tests.plugins.nu.comun import CARPETA, RAIZ, modulo

PAQUETES_SONIDOS = ("clasico", "cristal", "minimalista", "retro", "suave")


def test_manifiesto_completo_valida():
	datos = manifiesto.leer(CARPETA)
	assert datos.id == "zc.nubes" and datos.bloque == "NU"
	assert len(datos.ordenes) == 20
	assert set(datos.permisos) >= {"red", "secretos", "ejecutar_programas", "segundo_plano"}
	assert datos.activacion == ("al_arrancar",)
	assert datos.requiere_componentes == ("rclone",)
	claves = {c["clave"] for c in datos.tabla("configuracion")}
	assert claves == {"arrancar", "transferencias", "limite_subida_kib", "limite_bajada_kib", "horario_limites", "cache_listados_s",
		"reintentos", "mostrar_experimentales", "registro_detallado", "papelera_por_defecto", "formato_docs", "copia_entre_cuentas",
		"servir_solo_local", "aviso_winfsp_mostrado"}
	assert {s["id"] for s in datos.sonidos} == {"conectar", "desconectar", "oauth_espera", "oauth_ok", "sincronizacion_fin", "montada",
		"motor_detenido"}
	assert (CARPETA / "LICENSE").is_file() and (CARPETA / "doc" / "es" / "leeme.md").is_file()
	assert (CARPETA / "doc" / "es" / "google-drive.md").is_file()


def test_cada_orden_tiene_manejador_real(zc):
	for orden in manifiesto.leer(CARPETA).ordenes:
		funcion = registro.manejador(f"zc.nubes:{orden.id}")
		assert funcion is not None, orden.id
		assert not getattr(funcion, "provisional", False), orden.id


def test_la_ayuda_nombra_todas_las_ordenes():
	ayuda = (CARPETA / "doc" / "es" / "leeme.md").read_text(encoding="utf-8")
	for orden in manifiesto.leer(CARPETA).ordenes:
		assert orden.etiqueta.replace("&", "").rstrip(".") in ayuda, orden.id


def test_sonidos_en_los_cinco_paquetes_y_en_el_complemento():
	for sonido in manifiesto.leer(CARPETA).sonidos:
		assert (CARPETA / "sonidos" / f"{sonido['id']}.wav").is_file()
		for paquete in PAQUETES_SONIDOS:
			assert (RAIZ / "data" / "sounds" / paquete / "plugins" / "zc.nubes" / f"{sonido['id']}.wav").is_file(), (paquete, sonido)


def test_activar_registra_esquemas_y_al_detener(zc):
	from app.services.vfs import resolver

	assert {"nube", "webdav", "webdavs"} <= set(resolver._esquemas)
	assert zc.instancia.nubes.motor.vivo() is False, "con arrancar = al_usar, activar() no arranca rclone"


@pytest.mark.parametrize(("texto", "estado", "clase", "trozo"), [
	("object not found", 404, api.NoEncontrado, "No existe en la nube"),
	("error in ListJSON: directory not found", 404, api.NoEncontrado, "No existe"),
	("oauth2: cannot fetch token: 400 Bad Request Response: {\"error\": \"invalid_grant\"}", 500, api.ErrorAcceso, "Volver a autorizar"),
	("googleapi: Error 403: The user's Drive storage quota has been exceeded., storageQuotaExceeded", 403, api.SinEspacio, "espacio"),
	("googleapi: Error 429: rateLimitExceeded", 429, api.ErrorRed, "pide esperar"),
	("failed to start auth webserver: listen tcp 127.0.0.1:53682: bind", 500, api.ErrorRed, "53682"),
	("oauth authentication was cancelled", 500, api.Cancelado, "cancelada"),
	("unable to decrypt configuration and not allowed to ask for password", 500, api.ErrorAcceso, "configuración cifrada"),
	("Memory root '' doesn't support public links", 500, api.NoAdmitido, "no permite"),
	("dial tcp: lookup www.googleapis.com: no such host", 500, api.ErrorRed, "No hay conexión"),
	("algo muy raro", 500, api.ErrorArchivos, "detalles en el registro"),
])
def test_traductor_de_errores(zc, texto, estado, clase, trozo):
	errores = modulo("errores")
	traducido = errores.traducir(errores.ErrorRC(estado, texto), "archivo.txt")
	assert isinstance(traducido, clase)
	assert trozo.lower() in traducido.mensaje.lower()
	assert texto not in traducido.mensaje, "el texto original en inglés solo va al registro"


def test_reconectar_se_reconoce(zc):
	errores = modulo("errores")
	assert errores.es_reconectar(errores.traducir(errores.ErrorRC(401, "Unauthorized")))


def test_catalogo_de_servicios(zc):
	cuentas = modulo("cuentas")
	catalogo = zc.instancia.nubes.catalogo
	assert len(catalogo) >= 20
	ids = {s.id for s in catalogo.lista(True)}
	assert {"drive", "onedrive", "dropbox", "box", "pcloud", "mega", "s3", "b2", "yandex", "koofr", "kdrive", "jottacloud",
		"internxt", "filen", "protondrive", "iclouddrive", "nextcloud", "webdav_nativo", "otro"} <= ids
	visibles = {s.id for s in catalogo.lista(False)}
	assert "protondrive" not in visibles and "iclouddrive" not in visibles, "los experimentales se ocultan"
	assert [s.id for s in catalogo.buscar("google")] == ["drive"]
	assert "s3" in {s.id for s in catalogo.buscar("wasabi")}
	for servicio in catalogo.lista(True):
		assert servicio.autenticacion in cuentas.AUTENTICACIONES
		for campo in (*servicio.campos, *servicio.avanzadas):
			assert "&" not in campo.get("etiqueta", ""), "las letras de acceso las pone el asistente"
			assert campo.get("tipo", "texto") in ("texto", "contrasena", "opcion", "bool")
	assert catalogo.servicio("drive").avisos and catalogo.servicio("protondrive").experimental


def test_fichas_aportadas_por_otro_complemento(tmp_path, zc):
	cuentas = modulo("cuentas")
	otro = tmp_path / "plugins" / "ana_nubes"
	(otro / "recursos" / "servicios").mkdir(parents=True)
	(otro / "manifiesto.toml").write_text('id = "ana.nubes"\n[recomienda]\ncomplementos = ["zc.nubes >= 1.0"]\n', encoding="utf-8")
	(otro / "recursos" / "servicios" / "extra.json").write_text(json.dumps({"servicios": [
		{"id": "putio", "nombre": "put.io", "tipo": "putio", "autenticacion": "oauth"},
		{"id": "drive", "nombre": "Repetido", "tipo": "drive", "autenticacion": "oauth"}]}), encoding="utf-8")
	aportes = cuentas.aportaciones_de_complementos([tmp_path / "plugins"])
	catalogo = cuentas.Catalogo.cargar(CARPETA / "recursos" / "servicios.json", aportes)
	assert catalogo.servicio("putio").origen == "ana.nubes"
	assert catalogo.servicio("drive").nombre == "Google Drive", "una ficha aportada no sustituye a una propia"


def test_cuentas_json_sin_secretos_tolerante_y_atomico(tmp_path, zc):
	cuentas = modulo("cuentas")
	ruta = tmp_path / "cuentas.json"
	almacen = cuentas.AlmacenCuentas(ruta)
	cuenta = cuentas.Cuenta(id=almacen.id_libre("Google Drive de Ána"), nombre="Google Drive de Ána", servicio="drive",
		opciones={"export_formats": "docx,xlsx,pptx", "chunk_size": "64M"})
	assert cuenta.id == "google_drive_de_ana"
	almacen.guardar(cuenta)
	assert almacen.id_libre("Google Drive de Ana") == "google_drive_de_ana_2"
	datos = json.loads(ruta.read_text(encoding="utf-8"))
	assert datos["version"] == 1 and datos["cuentas"][0]["opciones"]["chunk_size"] == "64M"
	for clave in ("token", "client_secret", "pass", "password"):
		assert clave not in json.dumps(datos)
	ruta.write_text("{roto", encoding="utf-8")
	otro = cuentas.AlmacenCuentas(ruta)
	assert otro.lista() == []
	assert (tmp_path / "cuentas.json.danado").is_file()
	# Una cuenta que la copia de seguridad marcó para volver a configurar (peticiones-cs.md).
	ruta.write_text(json.dumps({"version": 1, "cuentas": [{"id": "x", "nombre": "X", "servicio": "drive", "motor": "rclone",
		"volver_a_configurar": True, "campo_futuro": 1}]}), encoding="utf-8")
	leida = cuentas.AlmacenCuentas(ruta).obtener("x")
	assert leida is not None and leida.volver_a_configurar


def test_nueva_cuenta_oauth_pide_el_navegador_de_zcommander(zc):
	nubes = zc.instancia.nubes
	servicio = nubes.catalogo.servicio("drive")
	cuenta, parametros = nubes.nueva_cuenta(servicio, "Drive de Ana", {"client_id": "mi-id", "client_secret": "mi-secreto"})
	assert parametros["config_auth_no_browser"] == "true" and parametros["config_is_local"] == "true"
	assert parametros["_tipo"] == "drive" and parametros["scope"] == "drive"
	assert parametros["export_formats"] == "docx,xlsx,pptx"
	assert "client_secret" not in cuenta.opciones and cuenta.client_id_propio
	otra, parametros = nubes.nueva_cuenta(nubes.catalogo.servicio("otro"), "Azure", {"tipo": "azureblob"})
	assert parametros["_tipo"] == "azureblob" and otra.opciones["tipo"] == "azureblob"


def test_limite_rclone(zc):
	servicio = modulo("servicio")
	assert servicio.limite_rclone(0, 0) == ""
	assert servicio.limite_rclone(512, 0) == "512k:off"
	assert servicio.limite_rclone(0, 1024) == "off:1024k"


def test_rutas_de_rclone_dentro_de_data(zc, datos_temporales):
	rutas = zc.instancia.nubes.rutas
	assert rutas.config == datos_temporales / "config" / "rclone.conf"
	assert rutas.cache == datos_temporales / "cache" / "rclone"
	assert rutas.temp == datos_temporales / "temp"
	assert rutas.bisync == datos_temporales / "cache" / "rclone" / "bisync"


@pytest.mark.lento
def test_validar_plugin_devuelve_cero():
	resultado = subprocess.run([sys.executable, str(RAIZ / "tools" / "validar_plugin.py"), str(CARPETA)], cwd=RAIZ,
		capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
	assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_complementos_de_serie_solo_usan_la_api():
	import ast

	for archivo in Path(CARPETA).rglob("*.py"):
		for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
			if isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and (nodo.module or "").startswith("app"):
				assert nodo.module == "app.plugins.api" or (nodo.module == "app.plugins" and [a.name for a in nodo.names] == ["api"]), archivo
			if isinstance(nodo, ast.Import):
				assert not any(a.name.startswith("app") for a in nodo.names), archivo
