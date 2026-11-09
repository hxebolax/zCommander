# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Servicio del actualizador (diseño 2.0, 5 y 18.2): comprobación, anti-retroceso, descarga, extracción,
marcas de salud en dos fases, «salud sin confirmar» y comprobación periódica compartida.

De la plantilla del agente «actualizador», con lo propio de zCommander. Servidor
HTTP local y carpetas temporales: nunca sale a Internet ni toca el data/ real.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("cryptography")

from tests.apoyo_actualizador import Servidor, cargar_firmador, crear_zip, publicar  # noqa: E402

from app.core import red  # noqa: E402
from app.services import actualizador  # noqa: E402

ARCHIVOS_V2 = {
	"ZCommander.exe": b"EXE 1.1.0",
	"lib/modulo.txt": b"modulo 1.1.0" * 2000,
	"data/sounds/aviso.wav": b"sonido 1.1.0",
	"data/bin/rclone/rclone.exe": b"rclone de la base nueva",
	"data/bin/linea_base.json": b'{"componentes": []}',
	"data/config/ajustes.json": b'{"sobrescrito": true}',
	"data/plugins/ana.util/manifiesto.toml": b"de la persona",
	"data/db/base.db": b"base falsa",
	"data/leeme.txt": b"suelto en data",
}


@pytest.fixture
def servidor(tmp_path):
	instancia = Servidor(tmp_path / "servidor")
	yield instancia
	instancia.cerrar()


@pytest.fixture
def clave(tmp_path, monkeypatch):
	firmador = cargar_firmador()
	monkeypatch.delenv(firmador.VARIABLE_CONTRASENA, raising=False)
	ruta = tmp_path / "claves" / "firma.key"
	return ruta, firmador.generar(ruta)


@pytest.fixture
def config(tmp_path, servidor, clave):
	instalacion = tmp_path / "Mi App"
	(instalacion / "data" / "config").mkdir(parents=True)
	(instalacion / "ZCommander.exe").write_bytes(b"EXE 1.0.0")
	return actualizador.Configuracion(
		version_actual="1.0.0",
		carpeta_app=instalacion,
		url_manifiesto=servidor.url("version.json"),
		claves_publicas=(clave[1],),
		comando=[sys.executable, str(instalacion / "main.py")],
		permitir_desde_codigo=True,
	)


def _publicar(servidor, clave, version="1.1.0", archivos=None, **opciones):
	return publicar(servidor.carpeta, version, archivos or ARCHIVOS_V2, clave[0], **opciones)


def _reintentar(funcion, veces: int = 40):
	"""En este equipo el bucle local corta a veces la conexión (WinError 10054, ronda 2-4): se reintenta
	como haría la persona con «Reintentar» (la descarga continúa donde se quedó)."""
	for _intento in range(veces - 1):
		try:
			return funcion()
		except actualizador.ErrorRed as error:
			if "error" in str(error) and "respondió" in str(error):
				raise
	return funcion()


# ── Constantes de zCommander (5.2) ───────────────────────────────────────────


def test_constantes_de_zcommander():
	assert actualizador.NOMBRE_APP == "zCommander" and actualizador.EJECUTABLE == "ZCommander.exe"
	assert actualizador.URL_MANIFIESTO == "https://xebolax.synology.me/zCommander/version.json"
	assert actualizador.DATA_ACTUALIZABLE == ("sounds", "locales", "docs", "icons")
	assert actualizador.DATA_ENTRANTE == {"bin": "bin/.entrante"}
	assert (actualizador.ESPERA_SALUD, actualizador.ESPERA_SALUD_TOTAL, actualizador.ESPERA_CIERRE) == (60, 300, 90)
	assert actualizador.MAX_MANIFIESTO == 256 * 1024 and actualizador.MAX_MIEMBROS == 50_000


def test_configuracion_por_defecto_usa_paths(datos_temporales):
	from app.core import paths

	config = actualizador.configuracion_por_defecto("2.0.0")
	assert config.carpeta_datos == paths.ruta_datos()
	assert config.carpeta_app == paths.ruta_base()
	assert config.archivo_estado == paths.ruta_datos() / "config" / "actualizaciones.json"
	assert config.comando[-1].endswith("main.py")


# ── Comprobación ─────────────────────────────────────────────────────────────


def test_detecta_version_nueva_con_novedades(config, servidor, clave):
	_publicar(servidor, clave, novedades="- Arreglos\n- Mejoras de accesibilidad")
	info = _reintentar(lambda: actualizador.comprobar(config))
	assert info is not None and info.version == "1.1.0"
	assert info.novedades.startswith("- Arreglos")
	assert info.url_zip == servidor.url("zCommander_v1.1.0.zip")
	assert "ultima_comprobacion" in actualizador.leer_estado(config)


def test_sin_version_nueva(config, servidor, clave):
	_publicar(servidor, clave, version="1.0.0")
	assert _reintentar(lambda: actualizador.comprobar(config)) is None


def test_manifiesto_sin_firmar_se_rechaza(config, servidor):
	publicar(servidor.carpeta, "1.1.0", ARCHIVOS_V2, None)
	with pytest.raises(actualizador.ErrorFirma):
		_reintentar(lambda: actualizador.comprobar(config))


def test_manifiesto_manipulado_en_el_servidor(config, servidor, clave):
	_publicar(servidor, clave)
	ruta = servidor.carpeta / "version.json"
	datos = json.loads(ruta.read_text(encoding="utf-8"))
	datos["version"] = "9.0.0"
	ruta.write_text(json.dumps(datos), encoding="utf-8")
	with pytest.raises(actualizador.ErrorFirma):
		_reintentar(lambda: actualizador.comprobar(config))


def test_manifiesto_de_otra_aplicacion(config, servidor, clave):
	_publicar(servidor, clave, extra={"app": "OtraAplicacion"})
	with pytest.raises(actualizador.ErrorFirma):
		_reintentar(lambda: actualizador.comprobar(config))


def test_http_fuera_de_localhost_se_rechaza(config):
	with pytest.raises(actualizador.ErrorRed):
		actualizador.comprobar(config, "http://ejemplo.invalid/version.json")


def test_servidor_caido(config, servidor, clave):
	with pytest.raises(actualizador.ErrorRed):
		actualizador.comprobar(config)  # no hay version.json: 404


def test_anti_retroceso(config, servidor, clave, caplog):
	actualizador.confirmar_version(config, "1.3.0")
	_publicar(servidor, clave, version="1.2.0")
	with caplog.at_level(logging.WARNING), pytest.raises(actualizador.ErrorRollback):
		_reintentar(lambda: actualizador.comprobar(config))
	assert "Anti-rollback" in caplog.text
	actualizador.confirmar_version(config, "1.2.0")  # solo sube: sigue en 1.3.0
	assert actualizador.leer_estado(config)["version_confirmada"] == "1.3.0"
	_publicar(servidor, clave, version="1.3.0")
	assert _reintentar(lambda: actualizador.comprobar(config)).version == "1.3.0"


def test_estado_danado_no_bloquea(config, servidor, clave):
	config.archivo_estado.parent.mkdir(parents=True, exist_ok=True)
	config.archivo_estado.write_text("{no es json", encoding="utf-8")
	_publicar(servidor, clave)
	assert _reintentar(lambda: actualizador.comprobar(config)).version == "1.1.0"


def test_version_omitida_solo_en_la_periodica(config, servidor, clave):
	_publicar(servidor, clave)
	actualizador.omitir_version(config, "1.1.0")
	assert _reintentar(lambda: actualizador.comprobar(config, respetar_omitida=True)) is None
	assert _reintentar(lambda: actualizador.comprobar(config, respetar_omitida=False)).version == "1.1.0"


# ── Descarga y verificación ──────────────────────────────────────────────────


def test_descarga_y_sha_correcto(config, servidor, clave):
	_publicar(servidor, clave)
	info = _reintentar(lambda: actualizador.comprobar(config))
	fases = []
	ruta = _reintentar(lambda: actualizador.descargar(config, info, progreso=lambda f, h, t: fases.append((f, h, t))))
	actualizador.verificar_paquete(ruta, info)
	assert ruta.parent == config.carpeta_trabajo / "descarga"
	assert fases[-1] == ("descarga", info.tamano, info.tamano)


def test_sha_incorrecto_se_rechaza_y_se_borra(config, servidor, clave):
	_publicar(servidor, clave)
	info = _reintentar(lambda: actualizador.comprobar(config))
	zip_servidor = servidor.carpeta / info.archivo
	datos = bytearray(zip_servidor.read_bytes())
	datos[-30] ^= 0xFF  # mismo tamaño, contenido distinto
	zip_servidor.write_bytes(bytes(datos))
	ruta = _reintentar(lambda: actualizador.descargar(config, info))
	with pytest.raises(actualizador.ErrorVerificacion):
		actualizador.verificar_paquete(ruta, info)
	assert not ruta.exists()


def test_descarga_mayor_de_lo_anunciado(config, servidor, clave):
	_publicar(servidor, clave)
	info = _reintentar(lambda: actualizador.comprobar(config))
	with open(servidor.carpeta / info.archivo, "ab") as archivo:
		archivo.write(b"x" * 100_000)
	with pytest.raises(actualizador.ErrorVerificacion):
		_reintentar(lambda: actualizador.descargar(config, info))
	assert not list((config.carpeta_trabajo / "descarga").glob("*.parcial"))


def test_descarga_reanudable(config, servidor, clave):
	_publicar(servidor, clave)
	info = _reintentar(lambda: actualizador.comprobar(config))
	mitad = info.tamano // 2
	servidor.cortar_en = mitad
	with pytest.raises(actualizador.ErrorRed):
		actualizador.descargar(config, info)
	parcial = config.carpeta_trabajo / "descarga" / (info.archivo + ".parcial")
	assert 0 < parcial.stat().st_size <= mitad
	ruta = _reintentar(lambda: actualizador.descargar(config, info))
	actualizador.verificar_paquete(ruta, info)
	assert any(nombre == info.archivo and rango and rango.startswith("bytes=") for nombre, rango in servidor.peticiones)


def test_servidor_sin_rangos_empieza_de_cero(config, servidor, clave):
	_publicar(servidor, clave)
	info = _reintentar(lambda: actualizador.comprobar(config))
	servidor.admite_rangos = False
	servidor.cortar_en = info.tamano // 2
	with pytest.raises(actualizador.ErrorRed):
		actualizador.descargar(config, info)
	ruta = _reintentar(lambda: actualizador.descargar(config, info))
	actualizador.verificar_paquete(ruta, info)


def test_cancelar_conserva_lo_descargado(config, servidor, clave):
	archivos = {**ARCHIVOS_V2, "lib/aleatorio.bin": os.urandom(300_000)}
	_publicar(servidor, clave, archivos=archivos)
	info = _reintentar(lambda: actualizador.comprobar(config))
	llamadas = []

	def cancelado():
		llamadas.append(1)
		return len(llamadas) > 1

	with pytest.raises(actualizador.ErrorCancelado):
		_reintentar(lambda: actualizador.descargar(config, info, cancelado=cancelado))
	assert (config.carpeta_trabajo / "descarga" / (info.archivo + ".parcial")).stat().st_size > 0


def test_errores_de_descarga_traducidos(config, monkeypatch):
	info = actualizador.InfoActualizacion("1.1.0", "z.zip", "https://ejemplo.invalid/z.zip", "0" * 64, 10)
	for error, clase in ((red.ErrorHTTP(red.CANCELADO, "x"), actualizador.ErrorCancelado),
			(red.ErrorHTTP(red.HTTP, "mayor"), actualizador.ErrorVerificacion),
			(red.ErrorHTTP(red.HTTP, "404", 404), actualizador.ErrorRed),
			(red.ErrorHTTP(red.CONEXION, "corte"), actualizador.ErrorRed)):
		def falla(*_a, error=error, **_k):
			raise error

		monkeypatch.setattr(actualizador.descargas, "descargar", falla)
		with pytest.raises(clase):
			actualizador.descargar(config, info)


# ── Extracción segura ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
	"nombre",
	[
		"../fuera.txt",
		"zCommander/../../fuera.txt",
		"/absoluta.txt",
		"C:/Windows/fuera.txt",
		"C:fuera.txt",
		"a\\..\\..\\fuera.txt",
		"\\\\servidor\\recurso\\fuera.txt",
		"zCommander/lib/archivo.txt:flujo",
		"zCommander/CON.txt",
		"zCommander/lib/punto_final.",
	],
)
def test_zip_con_rutas_peligrosas_se_rechaza(tmp_path, config, nombre):
	ruta = tmp_path / "malo.zip"
	with zipfile.ZipFile(ruta, "w") as paquete:
		paquete.writestr("zCommander/ZCommander.exe", b"exe")
		paquete.writestr(nombre, b"malicioso")
	destino = config.carpeta_trabajo / "nueva"
	with pytest.raises(actualizador.ErrorPaquete):
		actualizador.extraer_seguro(ruta, destino, config)
	assert not destino.exists()
	assert not list(tmp_path.rglob("fuera.txt"))


def test_zip_con_enlace_simbolico_se_rechaza(tmp_path, config):
	ruta = tmp_path / "enlace.zip"
	with zipfile.ZipFile(ruta, "w") as paquete:
		paquete.writestr("zCommander/ZCommander.exe", b"exe")
		enlace = zipfile.ZipInfo("zCommander/enlace")
		enlace.create_system = 3
		enlace.external_attr = (stat.S_IFLNK | 0o777) << 16
		paquete.writestr(enlace, "C:/Windows")
	with pytest.raises(actualizador.ErrorPaquete):
		actualizador.extraer_seguro(ruta, config.carpeta_trabajo / "nueva", config)


def test_zip_demasiado_grande_se_rechaza(tmp_path, config):
	config.max_expandido = 10_000
	ruta = crear_zip(tmp_path / "bomba.zip", {"ZCommander.exe": b"exe", "lib/relleno.bin": b"\0" * 50_000})
	assert ruta.stat().st_size < 10_000  # comprime mucho: por eso se mide lo expandido
	with pytest.raises(actualizador.ErrorPaquete):
		actualizador.extraer_seguro(ruta, config.carpeta_trabajo / "nueva", config)


def test_nombres_duplicados_sin_distinguir_mayusculas(tmp_path, config):
	ruta = crear_zip(tmp_path / "dup.zip", {"ZCommander.exe": b"exe", "lib/A.txt": b"1", "lib/a.TXT": b"2"})
	with pytest.raises(actualizador.ErrorPaquete):
		actualizador.extraer_seguro(ruta, config.carpeta_trabajo / "nueva", config)


def test_paquete_sin_ejecutable_se_rechaza(tmp_path, config):
	ruta = crear_zip(tmp_path / "ajeno.zip", {"otro.exe": b"x", "lib/a.txt": b"1"})
	with pytest.raises(actualizador.ErrorPaquete):
		actualizador.extraer_seguro(ruta, config.carpeta_trabajo / "nueva", config)


def test_zip_danado(tmp_path, config):
	ruta = tmp_path / "roto.zip"
	ruta.write_bytes(b"PK\x03\x04 esto no es un zip")
	with pytest.raises(actualizador.ErrorPaquete):
		actualizador.extraer_seguro(ruta, config.carpeta_trabajo / "nueva", config)


def test_extraccion_separa_recursos_entrantes_y_descarta_datos_de_la_persona(tmp_path, config, caplog):
	ruta = crear_zip(tmp_path / "bueno.zip", {**ARCHIVOS_V2, "lib/paquete/data/interno.txt": b"interno"})
	with caplog.at_level(logging.WARNING):
		destino = actualizador.extraer_seguro(ruta, config.carpeta_trabajo / "nueva", config)
	assert (destino / "programa" / "ZCommander.exe").read_bytes() == b"EXE 1.1.0"
	assert (destino / "programa" / "lib" / "paquete" / "data" / "interno.txt").is_file()
	assert (destino / "recursos" / "sounds" / "aviso.wav").read_bytes() == b"sonido 1.1.0"
	# 5.3: data/bin del paquete va a data/bin/.entrante, nunca sobre los componentes activos.
	assert (destino / "entrante" / "bin" / ".entrante" / "rclone" / "rclone.exe").read_bytes() == b"rclone de la base nueva"
	assert (destino / "entrante" / "bin" / ".entrante" / "linea_base.json").is_file()
	assert not (destino / "recursos" / "bin").exists()
	assert not (destino / "programa" / "data").exists()
	for personal in ("config", "db", "plugins"):
		assert not (destino / "recursos" / personal).exists()
	assert "data/config/ajustes.json" in caplog.text and "data/plugins/ana.util/manifiesto.toml" in caplog.text


def test_zip_sin_carpeta_raiz(tmp_path, config):
	ruta = crear_zip(tmp_path / "plano.zip", {"ZCommander.exe": b"exe", "lib/a.txt": b"1"}, carpeta_raiz=None)
	destino = actualizador.extraer_seguro(ruta, config.carpeta_trabajo / "nueva", config)
	assert (destino / "programa" / "lib" / "a.txt").is_file()


# ── Preparación, script y resultado ──────────────────────────────────────────


def test_descargar_y_preparar_genera_bat_crlf_sin_bom(config, servidor, clave):
	_publicar(servidor, clave)
	info = _reintentar(lambda: actualizador.comprobar(config))
	fases = []
	ruta_bat = _reintentar(lambda: actualizador.descargar_y_preparar(config, info, progreso=lambda f, h, t: fases.append(f)))
	datos = ruta_bat.read_bytes()
	assert ruta_bat.parent == config.carpeta_trabajo
	assert not datos.startswith(b"\xef\xbb\xbf")
	assert b"\n" not in datos.replace(b"\r\n", b"")
	assert {"descarga", "verificacion", "extraccion", "preparacion"} <= set(fases)
	assert not (config.carpeta_trabajo / "descarga" / info.archivo).exists()  # el ZIP ya no hace falta
	texto = datos.decode("utf-8")
	assert "{" + "app}" not in texto and "--tras-actualizar" in texto
	assert 'set "MODO=sustituir"' in texto and 'set "ESPERA_SALUD_TOTAL=300"' in texto
	assert 'set "ENTRANTES=bin\\.entrante"' in texto


def test_desde_codigo_no_se_instala(config, servidor, clave):
	config.permitir_desde_codigo = False
	_publicar(servidor, clave)
	info = _reintentar(lambda: actualizador.comprobar(config))
	with pytest.raises(actualizador.ErrorActualizacion):
		actualizador.descargar_y_preparar(config, info)


def test_instalacion_sin_ejecutable_no_prepara(config, servidor, clave):
	_publicar(servidor, clave)
	info = _reintentar(lambda: actualizador.comprobar(config))
	(config.carpeta_app / "ZCommander.exe").unlink()
	with pytest.raises(actualizador.ErrorActualizacion):
		actualizador.descargar_y_preparar(config, info)


def test_carpeta_de_entrada_no_valida_no_prepara(config):
	config.data_entrante = {"bin": "bin/../../fuera"}
	info = actualizador.InfoActualizacion("1.1.0", "z.zip", "https://ejemplo.invalid/z.zip", "0" * 64, 10)
	with pytest.raises(actualizador.ErrorActualizacion):
		actualizador.preparar_sustitucion(config, info)


def test_resultado_revertida_avisa_y_omite(config):
	config.carpeta_trabajo.mkdir(parents=True)
	config.archivo_resultado.write_text(
		"estado=revertida\nmotivo=sin_marcador_de_salud\nversion=1.1.0\nanterior=1.0.0\n", encoding="utf-8"
	)
	(config.carpeta_trabajo / "nueva").mkdir()
	mensaje = actualizador.leer_resultado_anterior(config)
	assert "1.1.0" in mensaje and "1.0.0" in mensaje
	assert actualizador.leer_estado(config)["version_omitida"] == "1.1.0"
	assert not config.archivo_resultado.exists()
	assert not (config.carpeta_trabajo / "nueva").exists()
	assert actualizador.leer_resultado_anterior(config) is None


def test_resultado_vuelta_a_peticion(config):
	config.carpeta_trabajo.mkdir(parents=True)
	config.archivo_resultado.write_text("estado=revertida\nmotivo=a_peticion\nversion=1.1.0\nanterior=1.0.0\n", encoding="utf-8")
	mensaje = actualizador.leer_resultado_anterior(config)
	assert "como pidió" in mensaje and "1.0.0" in mensaje


def test_resultado_correcto_no_molesta(config):
	config.carpeta_trabajo.mkdir(parents=True)
	config.archivo_resultado.write_text("estado=correcta\nmotivo=ninguno\nversion=1.1.0\n", encoding="utf-8")
	assert actualizador.leer_resultado_anterior(config) is None


def test_traduccion_con_gettext_instalado(monkeypatch):
	import builtins

	monkeypatch.setattr(builtins, "_", lambda texto: texto.upper(), raising=False)
	assert actualizador._("hola") == "HOLA"


# ── Marcas de salud en dos fases (5.2) ───────────────────────────────────────


def test_marca_de_inicio_solo_si_se_espera(config):
	assert not actualizador.escribir_inicio(config, tras_actualizar=False)
	assert not config.marca_inicio.exists()
	assert actualizador.escribir_inicio(config, tras_actualizar=True)
	assert config.marca_inicio.read_text(encoding="utf-8").split() == ["iniciado", "1.0.0", str(os.getpid())]
	config.marca_inicio.unlink()
	config.aviso_espera_salud.write_text("1.0.0\n", encoding="utf-8")  # otra copia abierta a mano
	assert actualizador.escribir_inicio(config, tras_actualizar=False)


def test_marcar_inicio_usa_la_configuracion_de_la_aplicacion(datos_temporales):
	from app.core.version import APP_VERSION

	actualizador.marcar_inicio(True)
	marca = datos_temporales / "temp" / "actualizacion" / "iniciado.txt"
	assert marca.read_text(encoding="utf-8").split()[:2] == ["iniciado", APP_VERSION]
	marca.unlink()
	actualizador.marcar_inicio(False)
	assert not marca.exists()


def test_confirmar_arranque_escribe_marcador(config):
	assert not actualizador.confirmar_arranque(config, tras_actualizar=False)
	assert not config.marcador_salud.exists()
	assert actualizador.leer_estado(config)["version_confirmada"] == "1.0.0"
	assert actualizador.confirmar_arranque(config, tras_actualizar=True)
	assert config.marcador_salud.read_text(encoding="utf-8") == "ok 1.0.0\n"
	assert actualizador.leer_estado(config)["ultimo_ok"] == f"1.0.0 {os.getpid()}"


def test_al_arrancar_tras_actualizar_confirma_integracion_y_avisa(config, monkeypatch):
	from app.services.componentes import integrar

	llamadas, recibidos = [], []
	monkeypatch.setattr(integrar, "confirmar_integracion", lambda: llamadas.append("confirmar"))
	monkeypatch.setattr(actualizador, "configuracion_por_defecto", lambda version=None: config)
	actualizador.fijar_oyente_arranque(recibidos.append)
	try:
		actualizador.al_arrancar(True)
	finally:
		actualizador.fijar_oyente_arranque(None)
	assert config.marcador_salud.read_text(encoding="utf-8") == "ok 1.0.0\n"
	assert llamadas == ["confirmar"]
	assert recibidos == [actualizador.ResultadoArranque(instalada="1.0.0")]
	assert actualizador.ultimo_arranque() == recibidos[0]


def test_al_arrancar_normal_no_escribe_ok_ni_integra(config, monkeypatch):
	from app.services.componentes import integrar

	llamadas = []
	monkeypatch.setattr(integrar, "confirmar_integracion", lambda: llamadas.append("confirmar"))
	resultado = actualizador.procesar_arranque(config, False)
	assert resultado == actualizador.ResultadoArranque()
	assert not config.marcador_salud.exists() and not llamadas
	assert actualizador.leer_estado(config)["version_confirmada"] == "1.0.0"


def test_al_arrancar_sin_oyente_suena(config, monkeypatch):
	from app.services.sonidos import servicio

	sonidos = []
	monkeypatch.setattr(servicio, "sonar", lambda evento, *a, **k: sonidos.append(evento) or True)
	monkeypatch.setattr(actualizador, "configuracion_por_defecto", lambda version=None: config)
	config.carpeta_trabajo.mkdir(parents=True)
	config.archivo_resultado.write_text("estado=revertida\nmotivo=sin_marcador_de_salud\nversion=1.1.0\nanterior=1.0.0\n",
		encoding="utf-8")
	actualizador.al_arrancar(False)
	assert sonidos == ["act.revertida"]
	assert actualizador.ultimo_arranque().revertida


# ── «Salud sin confirmar» (5.2) ──────────────────────────────────────────────


def _marca_sin_confirmar(config, version="1.0.0", pid=999999, anterior="0.9.0"):
	config.carpeta_trabajo.mkdir(parents=True, exist_ok=True)
	config.marca_sin_confirmar.write_text(f"salud sin confirmar {version} {pid} {anterior}\r\n", encoding="utf-8")
	(config.carpeta_respaldo / "programa").mkdir(parents=True, exist_ok=True)
	(config.carpeta_respaldo / "programa" / "ZCommander.exe").write_bytes(b"EXE 0.9.0")


def test_sin_confirmar_de_otro_arranque_pregunta_sin_confirmar(config):
	_marca_sin_confirmar(config)
	resultado = actualizador.procesar_arranque(config, False)
	assert resultado.sin_confirmar == actualizador.SinConfirmar("1.0.0", 999999, "0.9.0")
	assert "version_confirmada" not in actualizador.leer_estado(config)  # no se confirma sin respuesta
	assert config.marca_sin_confirmar.exists() and config.carpeta_respaldo.exists()
	actualizador.limpiar_trabajo(config)
	assert config.marca_sin_confirmar.exists(), "la limpieza nunca borra la marca"


def test_el_mismo_proceso_llega_tarde_a_ok(config):
	_marca_sin_confirmar(config, pid=os.getpid())
	resultado = actualizador.procesar_arranque(config, True)
	assert resultado.instalada == "1.0.0" and resultado.sin_confirmar is None
	assert not config.marca_sin_confirmar.exists() and not config.carpeta_respaldo.exists()


def test_marca_de_un_arranque_que_si_llego_a_ok(config):
	_marca_sin_confirmar(config, pid=4242)
	actualizador.guardar_estado(config, {"ultimo_ok": "1.0.0 4242"})
	assert actualizador.procesar_arranque(config, False).sin_confirmar is None
	assert not config.marca_sin_confirmar.exists()


def test_marca_de_otra_version_se_descarta(config):
	_marca_sin_confirmar(config, version="7.0.0")
	assert actualizador.procesar_arranque(config, False).sin_confirmar is None
	assert not config.marca_sin_confirmar.exists()


def test_seguir_con_esta_version(config, monkeypatch):
	from app.services.componentes import integrar

	llamadas = []
	monkeypatch.setattr(integrar, "confirmar_integracion", lambda: llamadas.append(1))
	_marca_sin_confirmar(config)
	actualizador.seguir_con_esta_version(config)
	assert actualizador.leer_estado(config)["version_confirmada"] == "1.0.0"
	assert not config.marca_sin_confirmar.exists() and not config.carpeta_respaldo.exists() and llamadas == [1]


def test_preparar_vuelta_atras(config):
	with pytest.raises(actualizador.ErrorActualizacion):
		actualizador.preparar_vuelta_atras(config)  # sin marca no hay a qué volver
	_marca_sin_confirmar(config)
	texto = actualizador.preparar_vuelta_atras(config).read_text(encoding="utf-8")
	assert 'set "MODO=volver"' in texto
	assert 'set "VERSION_NUEVA=1.0.0"' in texto and 'set "VERSION_ACTUAL=0.9.0"' in texto


# ── Comprobación periódica compartida (5.4) ──────────────────────────────────


@pytest.fixture
def sin_comprobaciones(monkeypatch):
	monkeypatch.setattr(actualizador, "_comprobaciones", {})
	return actualizador


def test_pasada_con_comprobaciones_registradas(config, monkeypatch, sin_comprobaciones):
	from app.core.tareas import TokenCancelacion

	info = actualizador.InfoActualizacion("1.1.0", "z.zip", "https://ejemplo.invalid/z.zip", "0" * 64, 10)
	llamadas = []
	monkeypatch.setattr(actualizador, "comprobar", lambda c, respetar_omitida: llamadas.append(respetar_omitida) or info)
	token = TokenCancelacion()
	recibidos = []

	def componentes(t):
		recibidos.append(t)
		return [actualizador.Novedad("CO", "rclone 1.77.0 disponible", False)]

	def rota(_t):
		raise RuntimeError("comprobación rota a propósito")

	actualizador.registrar_comprobacion("CO", componentes, lambda: True)
	actualizador.registrar_comprobacion("roto", rota, lambda: True)
	actualizador.registrar_comprobacion("PL", lambda t: [actualizador.Novedad("PL", "no", True)], lambda: False)
	resultado = actualizador.pasada(config, token, comprobar_app=True)
	assert resultado.info is info and llamadas == [True]  # la periódica respeta la versión omitida
	assert resultado.novedades == (actualizador.Novedad("CO", "rclone 1.77.0 disponible", False),)
	assert recibidos == [token]
	assert not actualizador.toca_pasada(config, 24)
	sin_app = actualizador.pasada(config, token, comprobar_app=False)
	assert sin_app.info is None and llamadas == [True]


def test_pasada_sin_red_no_molesta(config, monkeypatch, sin_comprobaciones):
	def falla(*_a, **_k):
		raise actualizador.ErrorRed("sin conexión")

	monkeypatch.setattr(actualizador, "comprobar", falla)
	assert actualizador.pasada(config, None) == actualizador.ResultadoPasada()


def test_pasada_cancelada_no_sigue(config, sin_comprobaciones):
	from app.core.tareas import TokenCancelacion

	token = TokenCancelacion()
	token.cancelar()
	actualizador.registrar_comprobacion("CO", lambda t: [actualizador.Novedad("CO", "x", True)], lambda: True)
	assert actualizador.pasada(config, token, comprobar_app=False).novedades == ()
	assert actualizador.toca_pasada(config, 24), "una pasada cancelada no cuenta"


def test_toca_pasada_respeta_el_intervalo(config):
	assert actualizador.toca_pasada(config, 24)
	ahora = datetime.now(timezone.utc)
	actualizador.guardar_estado(config, {"ultima_pasada": ahora.isoformat()})
	assert not actualizador.toca_pasada(config, 24)
	actualizador.guardar_estado(config, {"ultima_pasada": (ahora - timedelta(hours=25)).isoformat()})
	assert actualizador.toca_pasada(config, 24)
	actualizador.guardar_estado(config, {"ultima_pasada": "no es una fecha"})
	assert actualizador.toca_pasada(config, 24)


def test_registrar_dos_veces_sustituye(sin_comprobaciones):
	actualizador.registrar_comprobacion("CO", lambda t: [], lambda: True)
	actualizador.registrar_comprobacion("CO", lambda t: [], lambda: False)
	assert len(actualizador.comprobaciones()) == 1
	actualizador.quitar_comprobacion("CO")
	assert actualizador.comprobaciones() == {}
