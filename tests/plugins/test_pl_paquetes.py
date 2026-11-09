# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Instalar, actualizar, desinstalar y proteger complementos (diseño 2.0, 3.8 a 3.10 y 18.2, bloque PL).

Los paquetes se crean con las herramientas de autor (``tools/crear_plugin.py`` y
``tools/empaquetar_plugin.py``); las claves son de prueba y la carpeta ``data`` es
la temporal de cada prueba. Sin planificador, la activación es síncrona.
"""

from __future__ import annotations

import os
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

from app.core import paths
from app.plugins import api, cargador, estado, firma, gestor, manifiesto, paquetes, registro, serie
from app.plugins.estado import EstadoComplemento, Pendiente
from tools import crear_plugin, empaquetar_plugin


class Config:
	"""Configuración mínima con ``obtener``, ``establecer`` y ``suscribir``."""

	def __init__(self, **valores) -> None:
		self.valores = {"complementos.inhabilitados": [], "complementos.confiados": {}, "complementos.permitir_sin_firma": True,
			"complementos.fallos_maximos": 3, "complementos.modo_desarrollo": False, "complementos.auditoria": False}
		self.valores.update({k.replace("__", "."): v for k, v in valores.items()})

	def obtener(self, clave, *defecto):
		return self.valores[clave]

	def establecer(self, clave, valor) -> bool:
		self.valores[clave] = valor
		return True

	def suscribir(self, funcion, prefijo=""):
		return lambda: None


@pytest.fixture
def entorno(registro_vacio, tmp_path, monkeypatch):
	for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
		del sys.modules[nombre]
	monkeypatch.setattr(serie, "SERIE", {})
	cargador.fijar_planificador(None)
	estado.reiniciar()
	config = Config()
	carpeta_serie = tmp_path / "serie"
	carpeta_serie.mkdir()
	creados: list[cargador.Cargador] = []

	def arrancar() -> cargador.Cargador:
		"""Un arranque: pendientes, descubrimiento y marcadores (como ``cargador.arrancar``)."""
		for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
			del sys.modules[nombre]
		registro.vaciar()
		aplicados = paquetes.aplicar_pendientes(config)
		nuevo = cargador.Cargador(config, carpeta_serie=carpeta_serie, carpeta_centinelas=tmp_path / "cargando")
		nuevo.aplicados = aplicados
		nuevo.descubrir()
		cargador.fijar_actual(nuevo)
		creados.append(nuevo)
		return nuevo

	yield type("Entorno", (), {"config": config, "arrancar": staticmethod(arrancar), "tmp": tmp_path})
	for creado in creados:
		creado.cerrar()
	cargador.fijar_planificador(None)
	cargador.fijar_actual(None)
	api.fijar_interfaz(None)
	for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
		del sys.modules[nombre]


def _fuente(tmp_path: Path, id_: str = "ana.ejemplo", version: str = "0.1.0", extra: str = "", codigo: str | None = None) -> Path:
	carpeta = tmp_path / "fuentes" / f"{id_}-{version}"
	assert crear_plugin.crear(carpeta, id_, "Ejemplo de Ana", autor="Ana") == []
	ruta = carpeta / "manifiesto.toml"
	texto = ruta.read_text(encoding="utf-8").replace('version = "0.1.0"', f'version = "{version}"')
	ruta.write_text(texto + extra, encoding="utf-8")
	if codigo is not None:
		(carpeta / "__init__.py").write_text(textwrap.dedent(codigo), encoding="utf-8")
	return carpeta


def _paquete(tmp_path: Path, clave: bytes | None = None, **opciones) -> Path:
	carpeta = _fuente(tmp_path, **opciones)
	return empaquetar_plugin.empaquetar(carpeta, tmp_path / "paquetes" / f"{carpeta.name}.zcplugin", clave)


def _instalar(ruta: Path, config: Config) -> paquetes.Instalado:
	resumen = paquetes.preparar(ruta, config)
	assert resumen.instalable, resumen.problemas
	return paquetes.instalar(resumen, config)


def _ejecutar(id_completo: str) -> list[str]:
	"""Ejecuta una orden de complemento como lo haría ``complementos_pl.ejecutar`` (activando si hace falta)."""
	anuncios: list[str] = []
	id_complemento, _corto = registro.separar_orden(id_completo)
	assert cargador.asegurar_activo(id_complemento).result(5)
	contexto = api.pruebas.contexto_de_prueba(activo=api.pruebas.PanelFalso([api.Entrada("a.txt", "C:\\a.txt")]))
	contexto.orden = id_completo
	contexto.anunciar = lambda texto, *a, **k: anuncios.append(texto)
	assert api.ejecutar_manejador(id_completo, contexto)
	return anuncios


# ── Instalar ─────────────────────────────────────────────────────────────────


def test_instalar_un_id_nuevo_queda_usable_sin_reiniciar(entorno):
	entorno.arrancar()
	ruta = _paquete(entorno.tmp)
	resumen = paquetes.preparar(ruta, entorno.config)
	assert resumen.instalable and resumen.sin_firma and not resumen.reinicio
	assert "Ejemplo de Ana" in resumen.texto() and "Sin firma" in resumen.texto()
	instalado = paquetes.instalar(resumen, entorno.config)
	assert instalado.directo and instalado.carpeta == paths.ruta_plugins_usuario() / "ana.ejemplo"
	assert (instalado.carpeta / "manifiesto.toml").is_file()
	assert entorno.config.valores["complementos.confiados"]["ana.ejemplo"] == resumen.suma
	registrado = cargador.actual().registrar_carpeta(instalado.carpeta)
	assert registrado.estado == EstadoComplemento.REGISTRADO
	assert registro.orden("ana.ejemplo:saludar") is not None, "la orden entra en el catálogo sin reiniciar"
	assert _ejecutar("ana.ejemplo:saludar") == ["Hola, a.txt"]


def test_una_actualizacion_o_al_arrancar_queda_pendiente_y_se_aplica_al_reiniciar(entorno):
	entorno.arrancar()
	_instalar(_paquete(entorno.tmp), entorno.config)
	entorno.arrancar()
	assert registro.complemento("ana.ejemplo").manifiesto.version == "0.1.0"
	instalado = _instalar(_paquete(entorno.tmp, version="0.2.0"), entorno.config)
	assert not instalado.directo and instalado.pendiente == Pendiente.ACTUALIZAR
	assert instalado.carpeta == paths.ruta_plugins_usuario() / ".pendientes" / "ana.ejemplo"
	assert paquetes.pendientes() == {"ana.ejemplo": Pendiente.ACTUALIZAR}
	assert "se actualizará al reiniciar" in next(f.estado for f in gestor.filas() if f.id == "ana.ejemplo")
	nuevo = entorno.arrancar()
	assert registro.complemento("ana.ejemplo").manifiesto.version == "0.2.0"
	assert registro.estado("ana.ejemplo") == EstadoComplemento.REGISTRADO, "la suma aceptada se actualizó al instalar"
	assert [a.accion for a in nuevo.aplicados] == ["actualizar"]
	assert [v for v, _c in paquetes.anteriores("ana.ejemplo")] == ["0.1.0"]
	assert paquetes.pendientes() == {}


def test_con_al_arrancar_se_instala_al_reiniciar(entorno):
	entorno.arrancar()
	carpeta = _fuente(entorno.tmp, id_="ana.arranque")
	ruta_manifiesto = carpeta / "manifiesto.toml"
	ruta_manifiesto.write_text(ruta_manifiesto.read_text(encoding="utf-8").replace(
		'entrada = "__init__:Complemento"', 'entrada = "__init__:Complemento"\nactivacion = ["al_arrancar"]'), encoding="utf-8")
	instalado = _instalar(empaquetar_plugin.empaquetar(carpeta, entorno.tmp / "arranque.zcplugin"), entorno.config)
	assert not instalado.directo and instalado.pendiente == Pendiente.INSTALAR
	entorno.arrancar()
	assert registro.estado("ana.arranque") == EstadoComplemento.REGISTRADO


def test_un_zip_con_ruta_peligrosa_se_rechaza_sin_escribir_nada(entorno):
	ruta = entorno.tmp / "malo.zcplugin"
	with zipfile.ZipFile(ruta, "w") as paquete:
		paquete.writestr("manifiesto.toml", "formato = 1\n")
		paquete.writestr("../malo.py", "print('hola')\n")
	temporales = paths.ruta_temporales()
	antes = set(temporales.iterdir()) if temporales.is_dir() else set()
	with pytest.raises(paquetes.ErrorPaquete, match="no es seguro"):
		paquetes.preparar(ruta, entorno.config)
	assert not (entorno.tmp / "malo.py").exists()
	assert (set(temporales.iterdir()) if temporales.is_dir() else set()) == antes
	assert not paths.ruta_plugins_usuario().exists() or not any(paths.ruta_plugins_usuario().iterdir())


@pytest.mark.parametrize("nombre", ["C:/malo.py", "a/../../b.py", "CON.py", "a:flujo", "dup.py"])
def test_validar_zip_rechaza_nombres_peligrosos(tmp_path, nombre):
	ruta = tmp_path / "p.zip"
	with zipfile.ZipFile(ruta, "w") as paquete:
		paquete.writestr("dup.py", "x")
		paquete.writestr(nombre if nombre != "dup.py" else "DUP.py", "y")
	with zipfile.ZipFile(ruta) as paquete, pytest.raises(paquetes.ErrorPaquete):
		paquetes.validar_zip(paquete)


def test_al_instalar_que_falla_deshace_la_instalacion(entorno):
	carpeta = _fuente(entorno.tmp)
	(carpeta / "instalacion.py").write_text("def al_instalar(zc):\n\traise RuntimeError('roto')\n", encoding="utf-8")
	instalado = _instalar(empaquetar_plugin.empaquetar(carpeta, entorno.tmp / "x.zcplugin"), entorno.config)
	assert paquetes.ejecutar_gancho(instalado.carpeta, "al_instalar", "ana.ejemplo").result(10) is False
	paquetes.deshacer_instalacion(instalado, entorno.config)
	assert not instalado.carpeta.exists() and "ana.ejemplo" not in entorno.config.valores["complementos.confiados"]


def test_al_instalar_no_puede_usar_la_interfaz(entorno):
	carpeta = _fuente(entorno.tmp)
	(carpeta / "instalacion.py").write_text("def al_instalar(zc):\n\tzc.ui.confirmar('x')\n", encoding="utf-8")
	assert paquetes.ejecutar_gancho(carpeta, "al_instalar", "ana.ejemplo").result(10) is False


# ── Firma y confianza ────────────────────────────────────────────────────────


@pytest.fixture
def clave_proyecto(monkeypatch):
	privada = os.urandom(32)
	monkeypatch.setattr(firma, "CLAVES_PROYECTO", (firma.clave_publica(privada),))
	return privada


def test_firma_valida_es_oficial_y_un_byte_cambiado_es_sin_firma(entorno, clave_proyecto):
	entorno.arrancar()
	resumen = paquetes.preparar(_paquete(entorno.tmp, clave=clave_proyecto), entorno.config)
	assert resumen.firma_valida and resumen.confianza == "Oficial"
	paquetes.descartar(resumen)
	carpeta = entorno.tmp / "fuentes" / "ana.ejemplo-0.1.0"
	for cambio in ("byte", "archivo"):
		ruta = entorno.tmp / f"{cambio}.zcplugin"
		with zipfile.ZipFile(entorno.tmp / "paquetes" / "ana.ejemplo-0.1.0.zcplugin") as origen, zipfile.ZipFile(ruta, "w") as destino:
			for info in origen.infolist():
				datos = origen.read(info)
				if cambio == "byte" and info.filename == "__init__.py":
					datos += b"#"
				destino.writestr(info, datos)
			if cambio == "archivo":
				destino.writestr("extra.py", "x = 1\n")
		resumen = paquetes.preparar(ruta, entorno.config)
		assert not resumen.firma_valida and resumen.confianza == "Sin firma", cambio
		paquetes.descartar(resumen)
	assert carpeta.is_dir()


def test_autor_nuevo_fija_su_clave_y_otra_clave_se_rechaza(entorno):
	entorno.arrancar()
	autor = os.urandom(32)
	resumen = paquetes.preparar(_paquete(entorno.tmp, clave=autor), entorno.config)
	assert resumen.firma_valida and resumen.clave_nueva and resumen.confianza == "Firmado por un autor nuevo"
	paquetes.instalar(resumen, entorno.config)
	assert paquetes.leer_claves()["por_id"]["ana.ejemplo"] == firma.clave_publica(autor)
	entorno.arrancar()
	assert registro.complemento("ana.ejemplo").confianza == "Firmado por un autor de confianza"
	otra = paquetes.preparar(_paquete(entorno.tmp, clave=os.urandom(32), version="0.2.0"), entorno.config)
	assert not otra.instalable
	assert any("no está firmada por el mismo autor" in p for p in otra.problemas)
	sin_firma = paquetes.preparar(_paquete(entorno.tmp, version="0.3.0"), entorno.config)
	assert any("no está firmada por el mismo autor" in p for p in sin_firma.problemas)
	buena = paquetes.preparar(_paquete(entorno.tmp, clave=autor, version="0.4.0"), entorno.config)
	assert buena.instalable and buena.confianza == "Firmado por un autor de confianza"


def test_sin_firma_prohibido_por_preferencia(entorno):
	entorno.config.valores["complementos.permitir_sin_firma"] = False
	resumen = paquetes.preparar(_paquete(entorno.tmp), entorno.config)
	assert not resumen.instalable and any("sin firma no están permitidos" in p for p in resumen.problemas)


def test_un_zc_sin_firma_del_proyecto_no_se_instala(entorno):
	carpeta = entorno.tmp / "zc"
	carpeta.mkdir()
	(carpeta / "manifiesto.toml").write_text(
		(Path(__file__).resolve().parents[1] / "datos" / "plugins" / "ejemplo" / "manifiesto.toml").read_text(encoding="utf-8")
		.replace('id = "prueba.ejemplo"', 'id = "zc.falso"'), encoding="utf-8")
	(carpeta / "__init__.py").write_text("", encoding="utf-8")
	(carpeta / "LICENSE").write_text("GPL", encoding="utf-8")
	resumen = paquetes.preparar(empaquetar_plugin.empaquetar(carpeta, entorno.tmp / "zc.zcplugin"), entorno.config)
	assert not resumen.instalable and any("reservados" in p for p in resumen.problemas)


# ── Protección ───────────────────────────────────────────────────────────────


def test_tres_fallos_dejan_el_complemento_fuera_de_uso(entorno):
	entorno.arrancar()
	_instalar(_paquete(entorno.tmp, codigo="""
		from app.plugins import api

		class Complemento(api.Complemento):
			def activar(self, zc):
				zc.ordenes.manejador("saludar", self.saludar)

			def saludar(self, ctx):
				raise RuntimeError("roto")
	"""), entorno.config)
	cargador.actual().registrar_carpeta(paths.ruta_plugins_usuario() / "ana.ejemplo")
	assert cargador.asegurar_activo("ana.ejemplo").result(5)
	contexto = api.pruebas.contexto_de_prueba()
	for _vez in range(3):
		assert not api.ejecutar_manejador("ana.ejemplo:saludar", contexto)
	assert registro.estado("ana.ejemplo") == EstadoComplemento.FALLIDO
	assert gestor.puede_reintentar("ana.ejemplo")
	assert gestor.reintentar("ana.ejemplo") and registro.estado("ana.ejemplo") == EstadoComplemento.ACTIVO


def test_un_evento_lento_tres_veces_se_registra(caplog, monkeypatch):
	monkeypatch.setattr(estado, "LIMITE_EVENTO_S", 0.0)
	estado.reiniciar()
	avisos: list[str] = []
	estado.fijar_aviso_desarrollo(avisos.append)
	try:
		for _vez in range(3):
			estado.llamar_evento("ana.lento", "al_cambiar_carpeta", lambda: None)
	finally:
		estado.fijar_aviso_desarrollo(None)
	assert any("al_cambiar_carpeta" in r.getMessage() for r in caplog.records)
	assert len(avisos) == 1


# ── Actualizar y desinstalar conservan o borran los datos ────────────────────


def test_actualizar_conserva_la_configuracion_del_complemento(entorno):
	entorno.arrancar()
	_instalar(_paquete(entorno.tmp), entorno.config)
	entorno.arrancar()
	zc = api.Anfitrion("ana.ejemplo", paths.ruta_plugins_usuario() / "ana.ejemplo")
	zc.config.establecer("saludo", "Buenas")
	json_config = paths.ruta_config_plugins() / "ana.ejemplo.json"
	assert json_config.is_file()
	_instalar(_paquete(entorno.tmp, version="0.2.0"), entorno.config)
	entorno.arrancar()
	assert registro.complemento("ana.ejemplo").manifiesto.version == "0.2.0"
	assert json_config.is_file()
	zc = api.Anfitrion("ana.ejemplo", paths.ruta_plugins_usuario() / "ana.ejemplo")
	assert zc.config.obtener("saludo") == "Buenas"


@pytest.mark.parametrize("borrar", [True, False])
def test_desinstalar_borra_los_datos_solo_si_se_pide(entorno, borrar):
	entorno.arrancar()
	_instalar(_paquete(entorno.tmp), entorno.config)
	entorno.arrancar()
	zc = api.Anfitrion("ana.ejemplo", paths.ruta_plugins_usuario() / "ana.ejemplo")
	zc.config.establecer("saludo", "Buenas")
	(zc.datos / "notas.txt").write_text("x", encoding="utf-8")
	assert gestor.puede_desinstalar("ana.ejemplo")
	gestor.desinstalar("ana.ejemplo", borrar)
	assert "se desinstalará al reiniciar" in next(f.estado for f in gestor.filas() if f.id == "ana.ejemplo")
	nuevo = entorno.arrancar()
	assert registro.complemento("ana.ejemplo") is None
	assert not (paths.ruta_plugins_usuario() / "ana.ejemplo").exists()
	assert [a.accion for a in nuevo.aplicados] == ["desinstalar"]
	assert (paths.ruta_config_plugins() / "ana.ejemplo.json").exists() is not borrar
	assert (paths.ruta_config_plugins() / "ana.ejemplo" / "notas.txt").exists() is not borrar
	assert "ana.ejemplo" not in entorno.config.valores["complementos.confiados"]


def test_volver_a_la_version_anterior(entorno):
	entorno.arrancar()
	_instalar(_paquete(entorno.tmp), entorno.config)
	entorno.arrancar()
	_instalar(_paquete(entorno.tmp, version="0.2.0"), entorno.config)
	entorno.arrancar()
	assert gestor.volver_atras("ana.ejemplo") == "0.1.0"
	entorno.arrancar()
	assert registro.complemento("ana.ejemplo").manifiesto.version == "0.1.0"
	assert registro.estado("ana.ejemplo") == EstadoComplemento.REGISTRADO


def test_habilitar_inhabilitar_y_aceptar(entorno):
	entorno.arrancar()
	carpeta = paths.ruta_plugins_usuario() / "ana.copiado"
	carpeta.parent.mkdir(parents=True, exist_ok=True)
	_fuente(entorno.tmp, id_="ana.copiado").rename(carpeta)
	entorno.arrancar()
	assert registro.estado("ana.copiado") == EstadoComplemento.SIN_ACEPTAR, "copiado a mano, sin pasar por el gestor"
	assert "Sin aceptar" in next(f.estado for f in gestor.filas() if f.id == "ana.copiado")
	gestor.aceptar(entorno.config, "ana.copiado")
	assert registro.estado("ana.copiado") == EstadoComplemento.REGISTRADO
	gestor.inhabilitar(entorno.config, "ana.copiado")
	assert registro.estado("ana.copiado") == EstadoComplemento.INHABILITADO
	assert entorno.config.valores["complementos.inhabilitados"] == ["ana.copiado"]
	gestor.habilitar(entorno.config, "ana.copiado")
	assert registro.estado("ana.copiado") == EstadoComplemento.REGISTRADO
	assert entorno.config.valores["complementos.inhabilitados"] == []
	entorno.arrancar()
	assert registro.estado("ana.copiado") == EstadoComplemento.REGISTRADO, "la aceptación sobrevive al reinicio"


# ── Buscar actualizaciones ───────────────────────────────────────────────────


def test_buscar_actualizaciones_exige_la_firma_del_autor(entorno):
	autor = os.urandom(32)
	carpeta = _fuente(entorno.tmp)
	manifiesto_ruta = carpeta / "manifiesto.toml"
	manifiesto_ruta.write_text(manifiesto_ruta.read_text(encoding="utf-8").replace(
		'entrada = "__init__:Complemento"', 'entrada = "__init__:Complemento"\nurl_actualizacion = "https://ejemplo.invalid/a.json"'),
		encoding="utf-8")
	entorno.arrancar()
	_instalar(empaquetar_plugin.empaquetar(carpeta, entorno.tmp / "f.zcplugin", autor), entorno.config)
	entorno.arrancar()
	datos = {"id": "ana.ejemplo", "version": "0.2.0", "url": "https://ejemplo.invalid/a.zcplugin", "sha256": "0" * 64,
		"tamano": 10, "novedades": "Mejoras"}
	assert paquetes.buscar_actualizaciones(obtener=lambda url: datos) == [], "sin firma no se ofrece"
	firmado = paquetes.firmar_json_actualizacion(datos, autor)
	encontradas = paquetes.buscar_actualizaciones(obtener=lambda url: firmado)
	assert [(a.id, a.version) for a in encontradas] == [("ana.ejemplo", "0.2.0")]
	assert paquetes.buscar_actualizaciones(obtener=lambda url: paquetes.firmar_json_actualizacion(datos, os.urandom(32))) == []


# ── Máscaras, auditoría y prueba de un complemento ───────────────────────────


def test_renombrado_evaluar_usa_las_mascaras_de_todos(entorno):
	codigo = """
		from app.plugins import api

		class Complemento(api.Complemento):
			def activar(self, zc):
				zc.ordenes.manejador("saludar", lambda ctx: None)
				zc.renombrado.mascara("[ANA:largo]", lambda entrada, proveedor: str(len(entrada.nombre)))
	"""
	extra = '\n[[mascaras]]\nmarcador = "[ANA:largo]"\ndescripcion = "Largo del nombre"\n'
	_instalar(_paquete(entorno.tmp, extra=extra, codigo=codigo), entorno.config)
	entorno.arrancar()
	zc = api.Anfitrion("ana.otro", entorno.tmp)
	entrada = api.Entrada("informe.txt", str(entorno.tmp / "informe.txt"), modificado=0.0)
	from concurrent.futures import ThreadPoolExecutor

	assert zc.renombrado.evaluar("[N]-[ANA:largo].[E]", entrada, None) == "informe-….txt", "en la interfaz nunca espera"
	with ThreadPoolExecutor(1) as hilo:  # [trabajo]: activa el complemento y espera su máscara
		assert hilo.submit(zc.renombrado.evaluar, "[N]-[ANA:largo].[E]", entrada, None).result(10) == "informe-11.txt"
	from app.services import renombrado

	assert ("[ANA:largo]", "Largo del nombre") in renombrado.marcadores()
	with pytest.raises(api.NombreNoValido):
		zc.renombrado.evaluar("[", entrada, None)


def test_auditoria_registra_un_proceso_sin_permiso(entorno, caplog):
	from app.plugins import auditoria

	codigo = """
		import subprocess, sys
		from app.plugins import api

		class Complemento(api.Complemento):
			def activar(self, zc):
				zc.ordenes.manejador("saludar", self.saludar)

			def saludar(self, ctx):
				subprocess.run([sys.executable, "-c", "pass"], check=False)
	"""
	_instalar(_paquete(entorno.tmp, codigo=codigo), entorno.config)
	entorno.arrancar()
	auditoria.activar(True)
	try:
		_ejecutar("ana.ejemplo:saludar")
	finally:
		auditoria.activar(False)
	assert any("sin el permiso «ejecutar_programas»" in r.getMessage() for r in caplog.records)


def test_prueba_de_un_complemento_lo_carga_y_ejecuta_su_orden(entorno):
	from app.plugins import prueba

	carpeta = _fuente(entorno.tmp)
	assert prueba.comprobar_complemento(carpeta) == 0
	assert registro.estado("ana.ejemplo") == EstadoComplemento.ACTIVO
	roto = _fuente(entorno.tmp, id_="ana.roto", codigo="raise ImportError('roto')\n")
	assert prueba.comprobar_complemento(roto) == 1


def test_lineas_de_soporte_y_detalles(entorno):
	entorno.arrancar()
	_instalar(_paquete(entorno.tmp), entorno.config)
	cargador.actual().registrar_carpeta(paths.ruta_plugins_usuario() / "ana.ejemplo")
	assert any("Ejemplo de Ana (ana.ejemplo) 0.1.0: Sin cargar todavía" in linea for linea in gestor.lineas_soporte())
	texto = gestor.detalles("ana.ejemplo", ocupadas={"Ctrl+Shift+F5": "zc.reproductor:reproducir"})
	assert "Licencia: GPL-3.0-or-later" in texto and "Permisos: ninguno" in texto
	assert manifiesto.leer(paths.ruta_plugins_usuario() / "ana.ejemplo").id == "ana.ejemplo"


def test_el_json_de_actualizacion_se_verifica_como_lo_firma_publicar():
	"""``tools/publicar.py --firmar-complementos`` firma con ``serializar_canonico`` del actualizador, sin prefijo."""
	import base64

	from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

	from app.services import actualizador

	privada = os.urandom(32)
	datos = {"id": "ana.ejemplo", "version": "0.2.0", "url": "https://ejemplo.invalid/a.zcplugin", "sha256": "0" * 64,
		"tamano": 10, "novedades": "Mejoras"}
	datos["firma_ed25519"] = base64.b64encode(Ed25519PrivateKey.from_private_bytes(privada).sign(
		actualizador.serializar_canonico(datos))).decode("ascii")
	assert paquetes.verificar_json_actualizacion(datos, firma.clave_publica(privada))
	assert paquetes.firmar_json_actualizacion(datos, privada)["firma_ed25519"] == datos["firma_ed25519"]
