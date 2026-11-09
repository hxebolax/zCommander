# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cargador y activación de complementos (diseño 2.0, 3.4, 3.8, 3.9 y 18.2).

El «hilo de la interfaz» es el de la prueba: el planificador falso guarda las
llamadas y ``bombear`` las ejecuta, como haría el bucle de eventos de wx.
"""

from __future__ import annotations

import importlib
import queue
import shutil
import sys
import textwrap
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.plugins import api, cargador, estado, firma, registro, serie
from app.plugins.estado import EstadoComplemento

from ..conftest import RAIZ

DATOS = RAIZ / "tests" / "datos" / "plugins"


class Planificador:
	def __init__(self) -> None:
		self.cola: queue.Queue = queue.Queue()

	def __call__(self, funcion) -> None:
		self.cola.put(funcion)

	def bombear(self, condicion=lambda: False, segundos: float = 10.0) -> bool:
		limite = time.monotonic() + segundos
		while time.monotonic() < limite:
			try:
				self.cola.get(timeout=0.02)()
			except queue.Empty:
				if condicion():
					return True
		return condicion()


class _Config:
	def __init__(self, **valores) -> None:
		self.valores = {"complementos.inhabilitados": [], "complementos.confiados": {}, "complementos.permitir_sin_firma": True,
			"complementos.fallos_maximos": 3, "complementos.modo_desarrollo": False}
		self.valores.update({k.replace("__", "."): v for k, v in valores.items()})

	def obtener(self, clave):
		return self.valores[clave]


def _manifiesto(id_: str, extra: str = "", ordenes: str = "saludar") -> str:
	texto = textwrap.dedent(f"""\
		formato = 1
		id = "{id_}"
		nombre = "Complemento {id_}"
		descripcion = "Complemento de prueba."
		version = "1.0.0"
		autor = "Pruebas"
		licencia = "GPL-3.0-or-later"
		api_minima = "1.0"
		api_probada = "1.0"
		entrada = "__init__:Complemento"
	""") + extra
	for orden in ordenes.split():
		texto += f'\n[[ordenes]]\nid = "{orden}"\netiqueta = "&{orden.capitalize()}"\nayuda = "Prueba."\n'
	return texto


def _crear(carpeta: Path, id_: str, codigo: str, extra: str = "", ordenes: str = "saludar") -> Path:
	carpeta.mkdir(parents=True, exist_ok=True)
	(carpeta / "manifiesto.toml").write_text(_manifiesto(id_, extra, ordenes), encoding="utf-8")
	(carpeta / "__init__.py").write_text(textwrap.dedent(codigo), encoding="utf-8")
	return carpeta


@pytest.fixture
def entorno(registro_vacio, tmp_path, monkeypatch):
	"""Carpeta de serie temporal (los de prueba cuentan como de serie), planificador falso y limpieza de ``zcplugins``."""
	# Otra prueba (p. ej. la de la API estable) puede haber importado un complemento de prueba.
	for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
		del sys.modules[nombre]
	planificador = Planificador()
	cargador.fijar_planificador(planificador)
	serie_carpeta = tmp_path / "serie"
	serie_carpeta.mkdir()
	lista: dict[str, str] = {}
	monkeypatch.setattr(serie, "SERIE", lista)
	estado.reiniciar()
	creados: list[cargador.Cargador] = []

	def nuevo(*nombres: str, config=None, **opciones) -> cargador.Cargador:
		for nombre in nombres:
			if not (serie_carpeta / nombre).exists():
				shutil.copytree(DATOS / nombre, serie_carpeta / nombre, ignore=shutil.ignore_patterns("__pycache__"))
		for sub in serie_carpeta.iterdir():
			datos = (sub / "manifiesto.toml").read_text(encoding="utf-8")
			id_ = datos.split('id = "', 1)[1].split('"', 1)[0]
			lista[id_] = "1.0.0"
		resultado = cargador.Cargador(config or _Config(), carpeta_serie=serie_carpeta, carpeta_usuario=tmp_path / "usuario",
			carpeta_centinelas=tmp_path / "cargando", **opciones)
		resultado.descubrir()
		cargador.fijar_actual(resultado)
		creados.append(resultado)
		return resultado

	yield SimpleNamespace(planificador=planificador, nuevo=nuevo, serie=serie_carpeta, centinelas=tmp_path / "cargando",
		tmp=tmp_path, lista=lista)
	for creado in creados:
		creado.cerrar()
	cargador.fijar_planificador(None)
	cargador.fijar_actual(None)
	api.fijar_interfaz(None)
	for nombre in [m for m in sys.modules if m.startswith("zcplugins")]:
		del sys.modules[nombre]
	importlib.invalidate_caches()


def _ejemplo():
	return sys.modules["zcplugins.prueba__ejemplo"]


def _ctx(id_completo: str, activo=None, pasivo=None, argumento=None, ventana=None):
	return SimpleNamespace(param=id_completo, activo=activo or api.pruebas.PanelFalso(ruta="C:\\a"),
		pasivo=pasivo or api.pruebas.PanelFalso(ruta="C:\\b", lado="derecho"), lado_objetivo=None, argumento=argumento,
		extra={}, ventana=ventana or SimpleNamespace(contador_ordenes=0))


def test_orden_del_ejemplo_desde_el_catalogo(entorno):
	from app.ui import ordenes
	from app.ui.acciones import complementos_pl

	entorno.nuevo("ejemplo")
	orden = ordenes.POR_ID["prueba.ejemplo:saludar"]
	assert orden.manejador == "complementos_pl.ejecutar" and orden.bloque == "PL" or orden.bloque in ("COMPLEMENTO", "")
	futuro: Future = Future()
	ctx = _ctx("prueba.ejemplo:saludar", argumento="hola")
	ctx.extra["futuro"] = futuro
	complementos_pl.ejecutar(ctx)
	assert ctx.extra.get("futuro_tomado"), "sin activar, la orden no espera"
	assert entorno.planificador.bombear(futuro.done)
	assert futuro.result() is True
	assert ("saludar", "hola", "C:\\a", None) in _ejemplo().LLAMADAS
	assert registro.estado("prueba.ejemplo") == EstadoComplemento.ACTIVO


def test_roto_al_importar_queda_fallido_y_el_resto_funciona(entorno):
	cargador_sesion = entorno.nuevo("roto_importar", "ejemplo")
	malo = cargador_sesion.asegurar_activo("prueba.roto_importar")
	bueno = cargador_sesion.asegurar_activo("prueba.ejemplo")
	assert entorno.planificador.bombear(lambda: malo.done() and bueno.done())
	assert malo.result() is False and bueno.result() is True
	assert registro.estado("prueba.roto_importar") == EstadoComplemento.FALLIDO


def test_centinela_se_escribe_y_se_borra_aunque_activar_lance(entorno, monkeypatch):
	cargador_sesion = entorno.nuevo("roto_activar")
	vistos = []
	original = cargador.Cargador._importar

	def importar(self, registrado):
		vistos.append(sorted(p.name for p in entorno.centinelas.iterdir()))
		return original(self, registrado)

	monkeypatch.setattr(cargador.Cargador, "_importar", importar)
	futuro = cargador_sesion.asegurar_activo("prueba.roto_activar")
	assert entorno.planificador.bombear(futuro.done)
	assert vistos == [["prueba__roto_activar"]]
	assert futuro.result() is False
	assert list(entorno.centinelas.iterdir()) == []
	assert registro.estado("prueba.roto_activar") == EstadoComplemento.FALLIDO


def test_centinela_de_un_cierre_brusco_excluye_solo_ese(entorno):
	entorno.centinelas.mkdir(parents=True, exist_ok=True)
	(entorno.centinelas / "prueba__roto_activar").write_text("x", encoding="utf-8")
	cargador_sesion = entorno.nuevo("roto_activar", "ejemplo")
	assert cargador_sesion.centinelas == ["prueba.roto_activar"]
	assert registro.estado("prueba.roto_activar") == EstadoComplemento.INHABILITADO
	assert registro.estado("prueba.ejemplo") == EstadoComplemento.REGISTRADO
	assert any("se cerró" in t for t in cargador_sesion.avisos_arranque())


def test_dos_disparos_una_sola_activacion_y_activar_en_la_interfaz(entorno):
	cargador_sesion = entorno.nuevo("ejemplo")
	desde_hilo: list[Future] = []
	hilo = threading.Thread(target=lambda: desde_hilo.append(cargador_sesion.asegurar_activo("prueba.ejemplo")), name="trabajo")
	hilo.start()
	hilo.join()
	directo = cargador_sesion.asegurar_activo("prueba.ejemplo")
	assert entorno.planificador.bombear(lambda: desde_hilo[0].done() and directo.done())
	assert desde_hilo[0].result() and directo.result()
	activaciones = [c for c in _ejemplo().LLAMADAS if c[0] == "activar"]
	assert activaciones == [("activar", threading.current_thread().name)]


def test_orden_durante_la_carga_usa_la_instantanea_y_se_descarta_si_cambia_la_carpeta(entorno):
	from app.ui.acciones import complementos_pl

	entorno.nuevo("ejemplo")
	from app.services.vfs.base import Entrada

	entradas = [Entrada("uno.txt", "C:\\a\\uno.txt"), Entrada("dos.txt", "C:\\a\\dos.txt")]
	activo = api.pruebas.PanelFalso(entradas, cursor=0, ruta="C:\\a")
	ctx = _ctx("prueba.ejemplo:saludar", activo=activo)
	ctx.extra["futuro"] = Future()
	inicio = time.monotonic()
	complementos_pl.ejecutar(ctx)
	assert time.monotonic() - inicio < 0.5, "no bloquea la interfaz"
	activo._cursor = 1  # la persona se mueve mientras se carga
	assert entorno.planificador.bombear(ctx.extra["futuro"].done)
	assert ("saludar", None, "C:\\a", "uno.txt") in _ejemplo().LLAMADAS, "actúa sobre lo que había al pulsar"
	# Otra vez, con el complemento ya activo y otra orden en medio: se ejecuta en el acto.
	ctx2 = _ctx("prueba.ejemplo:saludar", activo=activo)
	complementos_pl.ejecutar(ctx2)
	assert not ctx2.extra.get("futuro_tomado")


def test_orden_descartada_si_cambia_la_carpeta_o_se_ejecuta_otra(entorno, monkeypatch):
	from app.ui import anuncios
	from app.ui.acciones import complementos_pl

	entorno.nuevo("ejemplo")
	dichos = []
	monkeypatch.setattr(anuncios, "anunciar", lambda texto, *a, **k: dichos.append(texto))
	activo = api.pruebas.PanelFalso(ruta="C:\\a")
	ctx = _ctx("prueba.ejemplo:saludar", activo=activo)
	ctx.extra["futuro"] = Future()
	complementos_pl.ejecutar(ctx)
	activo._ruta = "C:\\otra"
	assert entorno.planificador.bombear(ctx.extra["futuro"].done)
	assert ctx.extra["futuro"].result() is False
	assert any("cambió de carpeta" in d for d in dichos)


def test_orden_descartada_si_se_ejecuta_otra_orden(entorno, monkeypatch):
	from app.ui import anuncios
	from app.ui.acciones import complementos_pl

	entorno.nuevo("ejemplo")
	dichos = []
	monkeypatch.setattr(anuncios, "anunciar", lambda texto, *a, **k: dichos.append(texto))
	ventana = SimpleNamespace(contador_ordenes=5)
	ctx = _ctx("prueba.ejemplo:saludar", ventana=ventana)
	ctx.extra["futuro"] = Future()
	complementos_pl.ejecutar(ctx)
	ventana.contador_ordenes = 6
	assert entorno.planificador.bombear(ctx.extra["futuro"].done)
	assert ctx.extra["futuro"].result() is False
	assert any("ejecutó otra orden" in d for d in dichos)


def test_continuacion_fuera_de_set_result_y_su_excepcion_se_registra(entorno, caplog):
	_crear(entorno.serie / "rompe", "prueba.rompe", """
		from app.plugins import api

		class Complemento(api.Complemento):
			def activar(self, zc):
				def saludar(ctx):
					raise ValueError("manejador roto a propósito")
				zc.ordenes.manejador("saludar", saludar)
	""")
	from app.ui.acciones import complementos_pl

	entorno.nuevo()
	ctx = _ctx("prueba.rompe:saludar")
	ctx.extra["futuro"] = Future()
	complementos_pl.ejecutar(ctx)
	assert entorno.planificador.bombear(ctx.extra["futuro"].done)
	assert ctx.extra["futuro"].result() is False
	assert estado.fallos("prueba.rompe") == 1
	assert "manejador roto" in caplog.text


def test_un_hilo_espera_la_activacion_sin_bloquear(entorno):
	cargador_sesion = entorno.nuevo("ejemplo")
	resultado = []
	hilo = threading.Thread(target=lambda: resultado.append(cargador_sesion.asegurar_activo("prueba.ejemplo").result(10)))
	hilo.start()
	assert entorno.planificador.bombear(lambda: bool(resultado))
	hilo.join(5)
	assert resultado == [True]


def test_lento_agota_el_tope_y_la_siguiente_carga_usa_otro_hilo(entorno):
	cargador_sesion = entorno.nuevo("lento", "ejemplo")
	cargador_sesion.tiempo_carga_s = 0.5
	futuro = cargador_sesion.asegurar_activo("prueba.lento")
	assert entorno.planificador.bombear(futuro.done)
	assert futuro.result() is False
	registrado = registro.complemento("prueba.lento")
	assert registrado.estado == EstadoComplemento.FALLIDO and not registrado.reintentable
	assert "tarda demasiado" in registrado.motivo
	assert list(entorno.centinelas.iterdir()) == []
	otro = cargador_sesion.asegurar_activo("prueba.ejemplo")
	assert entorno.planificador.bombear(otro.done) and otro.result() is True


def test_dependencia_se_activa_antes_y_ve_lo_exportado(entorno):
	_crear(entorno.serie / "b", "prueba.b", """
		from app.plugins import api

		class Complemento(api.Complemento):
			def activar(self, zc):
				zc.exportar("valor", 42)
				zc.ordenes.manejador("saludar", api.provisional("saludar"))
	""")
	_crear(entorno.serie / "a", "prueba.a", """
		from app.plugins import api

		VISTO = []

		class Complemento(api.Complemento):
			def activar(self, zc):
				b = zc.complemento("prueba.b")
				VISTO.append(b.valor if b else None)
				zc.ordenes.manejador("saludar", api.provisional("saludar"))
	""", extra='\n[requiere]\ncomplementos = ["prueba.b >= 1.0"]\n')
	cargador_sesion = entorno.nuevo()
	futuro = cargador_sesion.asegurar_activo("prueba.a")
	assert entorno.planificador.bombear(futuro.done)
	assert futuro.result() is True
	assert sys.modules["zcplugins.prueba__a"].VISTO == [42]


def test_dependencia_circular(entorno):
	codigo = """
		from app.plugins import api

		class Complemento(api.Complemento):
			def activar(self, zc):
				zc.ordenes.manejador("saludar", api.provisional("saludar"))
	"""
	_crear(entorno.serie / "c1", "prueba.c1", codigo, extra='\n[requiere]\ncomplementos = ["prueba.c2"]\n')
	_crear(entorno.serie / "c2", "prueba.c2", codigo, extra='\n[requiere]\ncomplementos = ["prueba.c1"]\n')
	cargador_sesion = entorno.nuevo()
	futuro = cargador_sesion.asegurar_activo("prueba.c1")
	assert entorno.planificador.bombear(futuro.done)
	assert futuro.result() is False
	for id_ in ("prueba.c1", "prueba.c2"):
		assert registro.estado(id_) == EstadoComplemento.FALLIDO
	assert "circular" in registro.complemento("prueba.c1").motivo
	assert "zcplugins.prueba__c1" not in sys.modules and "zcplugins.prueba__c2" not in sys.modules


def test_mostrar_modal_dentro_de_activar_lanza(entorno):
	_crear(entorno.serie / "modal", "prueba.modal", """
		from app.plugins import api

		ERRORES = []

		class Complemento(api.Complemento):
			def activar(self, zc):
				try:
					zc.ui.mostrar_modal(None)
				except RuntimeError as error:
					ERRORES.append(str(error))
				zc.ordenes.manejador("saludar", api.provisional("saludar"))
	""")

	class _Interfaz:
		modulo_ui = SimpleNamespace(mostrar_modal=lambda dialogo: 0)

		def en_hilo_interfaz(self):
			return True

	api.fijar_interfaz(_Interfaz())
	cargador_sesion = entorno.nuevo()
	futuro = cargador_sesion.asegurar_activo("prueba.modal")
	assert entorno.planificador.bombear(futuro.done)
	assert futuro.result() is True
	assert sys.modules["zcplugins.prueba__modal"].ERRORES == ["Un complemento no puede abrir un diálogo dentro de activar()"]


def test_complemento_desde_la_interfaz_sin_activar_devuelve_none(entorno):
	cargador_sesion = entorno.nuevo("ejemplo")
	zc = api.Anfitrion("prueba.otro", entorno.tmp)
	assert zc.complemento("prueba.ejemplo") is None
	assert "zcplugins.prueba__ejemplo" not in sys.modules, "nunca importa en el acto"
	entorno.planificador.bombear(lambda: registro.estado("prueba.ejemplo") == EstadoComplemento.ACTIVO)
	assert zc.complemento("prueba.ejemplo").saludo() == "hola"
	del cargador_sesion


def test_congelar_descongelar_y_cerrar(entorno):
	cargador_sesion = entorno.nuevo("ejemplo")
	cargador_sesion.congelar()
	assert cargador_sesion.asegurar_activo("prueba.ejemplo").result(1) is False
	assert registro.estado("prueba.ejemplo") == EstadoComplemento.REGISTRADO
	cargador_sesion.descongelar()
	pendiente = cargador_sesion.asegurar_activo("prueba.ejemplo")
	assert not pendiente.done()
	cargador_sesion.cerrar()
	from app.services.vfs.base import Cancelado

	with pytest.raises(Cancelado):
		pendiente.result(1)
	assert list(entorno.centinelas.iterdir()) == []


def test_lib_no_toca_sys_path_ni_tapa_la_biblioteca_estandar(entorno):
	carpeta = _crear(entorno.serie / "conlib", "prueba.conlib", """
		from app.plugins import api
		import vendorizado
		import json

		class Complemento(api.Complemento):
			def activar(self, zc):
				zc.exportar("valores", (vendorizado.VALOR, json.__name__, json.__file__))
				zc.ordenes.manejador("saludar", api.provisional("saludar"))
	""")
	(carpeta / "lib").mkdir()
	(carpeta / "lib" / "vendorizado.py").write_text("VALOR = 'de lib'\n", encoding="utf-8")
	ruta_antes = list(sys.path)
	cargador_sesion = entorno.nuevo()
	futuro = cargador_sesion.asegurar_activo("prueba.conlib")
	assert entorno.planificador.bombear(futuro.done) and futuro.result()
	valor, nombre_json, archivo_json = registro.exportados("prueba.conlib")["valores"]
	assert valor == "de lib" and nombre_json == "json" and "conlib" not in archivo_json
	assert sys.path == ruta_antes
	assert sys.meta_path[-1].__class__.__name__ == "BuscadorLib"


def test_archivo_cambiado_tras_activar_falla_su_importacion_tardia(entorno, monkeypatch):
	carpeta = _crear(entorno.serie / "tardio", "prueba.tardio", """
		from app.plugins import api

		class Complemento(api.Complemento):
			def activar(self, zc):
				zc.ordenes.manejador("saludar", api.provisional("saludar"))
	""")
	(carpeta / "tardio.py").write_text("VALOR = 1\n", encoding="utf-8")
	monkeypatch.setattr(serie, "SUMAS", {"prueba.tardio": firma.sumas_archivos(carpeta)})
	cargador_sesion = entorno.nuevo()
	futuro = cargador_sesion.asegurar_activo("prueba.tardio")
	assert entorno.planificador.bombear(futuro.done) and futuro.result()
	(carpeta / "tardio.py").write_text("VALOR = 2  # cambiado\n", encoding="utf-8")
	with pytest.raises(ImportError, match="ha cambiado"):
		importlib.import_module("zcplugins.prueba__tardio.tardio")


def test_una_pyc_sembrada_no_se_usa(entorno, tmp_path):
	import py_compile

	carpeta = _crear(entorno.serie / "pyc", "prueba.pyc", """
		from app.plugins import api
		from . import modulo

		class Complemento(api.Complemento):
			def activar(self, zc):
				zc.exportar("valor", modulo.VALOR)
				zc.ordenes.manejador("saludar", api.provisional("saludar"))
	""")
	(carpeta / "modulo.py").write_text("VALOR = 'fuente'\n", encoding="utf-8")
	falso = tmp_path / "falso.py"
	falso.write_text("VALOR = 'pyc sembrada'\n", encoding="utf-8")
	(carpeta / "__pycache__").mkdir()
	py_compile.compile(str(falso), cfile=str(carpeta / "__pycache__" / f"modulo.{sys.implementation.cache_tag}.pyc"))
	cargador_sesion = entorno.nuevo()
	futuro = cargador_sesion.asegurar_activo("prueba.pyc")
	assert entorno.planificador.bombear(futuro.done) and futuro.result()
	assert registro.exportados("prueba.pyc")["valor"] == "fuente"


def test_sin_firma_aceptado_y_cambiado_pasa_a_sin_aceptar(entorno):
	usuario = entorno.tmp / "usuario"
	shutil.copytree(DATOS / "ejemplo", usuario / "ejemplo", ignore=shutil.ignore_patterns("__pycache__"))
	suma = firma.suma_paquete(usuario / "ejemplo", "prueba.ejemplo", "1.0.0")
	cargador_sesion = entorno.nuevo(config=_Config(complementos__confiados={"prueba.ejemplo": suma}))
	assert registro.estado("prueba.ejemplo") == EstadoComplemento.REGISTRADO
	ruta = usuario / "ejemplo" / "__init__.py"
	ruta.write_text(ruta.read_text(encoding="utf-8") + "\n# cambiado\n", encoding="utf-8")
	futuro = cargador_sesion.asegurar_activo("prueba.ejemplo")
	assert entorno.planificador.bombear(futuro.done)
	assert futuro.result() is False
	assert registro.estado("prueba.ejemplo") == EstadoComplemento.SIN_ACEPTAR


def test_columna_no_manda_trabajo_hasta_activar(entorno, monkeypatch):
	_crear(entorno.serie / "col", "prueba.col", """
		import time
		from app.plugins import api

		class Complemento(api.Complemento):
			def activar(self, zc):
				time.sleep(0.3)
				zc.columnas.extractor("tamano_doble", lambda entrada, proveedor, cancelacion: str(entrada.tamano * 2))
				zc.ordenes.manejador("saludar", api.provisional("saludar"))
	""", extra='\n[[columnas]]\nid = "tamano_doble"\ntitulo = "Doble"\ntipo = "numero"\n')
	from app.services.vfs.base import Entrada

	monkeypatch.setattr(registro, "TIEMPO_COLUMNA_S", 0.2)
	entorno.nuevo()
	assert [c.id for c in registro.catalogo_columnas()] == ["prueba.col:tamano_doble"]
	listos = []
	entrada = Entrada("a.txt", "C:\\a\\a.txt", tamano=21)
	assert registro.valor_columna("prueba.col:tamano_doble", entrada, None, lambda: listos.append(1)) is None
	assert entorno.planificador.bombear(lambda: bool(listos))
	assert registro.valor_columna("prueba.col:tamano_doble", entrada, None, lambda: None) == "42", \
		"la activación (0,3 s) no cuenta en los 0,2 s del tope de la columna"
