# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque NV: instalar el complemento de NVDA desde zCommander (diseño 2.0, 10.16, 10.18 y 18.2).

``os.startfile`` se sustituye SIEMPRE: estas pruebas nunca abren el
.nvda-addon ni tocan la configuración de NVDA. La enumeración de procesos sí es
real (solo lectura). El diálogo se construye de verdad (para
``revisar_teclado``) pero nunca se muestra: la pregunta se simula.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

wx = pytest.importorskip("wx")

from app.core import paths  # noqa: E402
from app.core.version import APP_VERSION  # noqa: E402
from app.ui import instalar_complemento as instalar  # noqa: E402
from app.ui import paginas_propias  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import nvda_nv  # noqa: E402


@pytest.fixture(autouse=True)
def sin_abrir_nada(monkeypatch):
	"""Cualquier llamada no prevista a os.startfile hace fallar la prueba."""

	def prohibido(*_argumentos, **_opciones):
		raise AssertionError("Una prueba ha intentado abrir un archivo con os.startfile")

	monkeypatch.setattr(os, "startfile", prohibido, raising=False)


def _crear_paquete(ruta: Path, version: str = "1.4.0") -> Path:
	ruta.parent.mkdir(parents=True, exist_ok=True)
	with zipfile.ZipFile(ruta, "w") as zip_:
		zip_.writestr("manifest.ini", f'name = zCommander\nsummary = "x"\nversion = {version}\n')
	return ruta


@pytest.fixture
def paquete(tmp_path):
	return _crear_paquete(tmp_path / "bin" / "nvda" / "zCommander-1.4.0.nvda-addon")


# ════════════════════════════════════════════════════════════════════════════
# Lógica (sin ventanas)
# ════════════════════════════════════════════════════════════════════════════

def test_ruta_en_data_bin_nvda_con_la_version(datos_temporales):
	assert instalar.ruta_complemento() == paths.ruta_binarios() / "nvda" / f"zCommander-{APP_VERSION}.nvda-addon"
	assert instalar.ruta_complemento("2.0", Path("x")) == Path("x") / "zCommander-2.0.nvda-addon"


def test_hay_proceso():
	assert instalar.hay_proceso(["explorer.exe", "NVDA.EXE"])
	assert not instalar.hay_proceso(["explorer.exe", "nvda_slave.exe"])


@pytest.mark.skipif(sys.platform != "win32", reason="Enumeración de procesos de Windows")
def test_enumeracion_real_de_procesos():
	nombres = [n.lower() for n in instalar.nombres_de_procesos()]
	assert Path(sys.executable).name.lower() in nombres


def test_version_instalada_y_pendiente(tmp_path):
	assert instalar.version_instalada("zCommander", tmp_path) is None
	pendiente = tmp_path / "addons" / "zCommander.pendingInstall"
	pendiente.mkdir(parents=True)
	(pendiente / "manifest.ini").write_text("name = zCommander\nversion = 2.0.0\n", encoding="utf-8")
	assert instalar.version_instalada("zCommander", tmp_path) == "2.0.0"
	carpeta = tmp_path / "addons" / "zCommander"
	carpeta.mkdir(parents=True)
	(carpeta / "manifest.ini").write_text('name = zCommander\nversion = "1.3.0"\n', encoding="utf-8")
	assert instalar.version_instalada("zCommander", tmp_path) == "1.3.0"


def test_version_del_paquete(paquete, tmp_path):
	assert instalar.version_del_paquete(paquete) == "1.4.0"
	roto = tmp_path / "roto.nvda-addon"
	roto.write_bytes(b"no es un zip")
	assert instalar.version_del_paquete(roto) is None


def test_explicacion_avisa_de_confirmacion_y_reinicio():
	texto = instalar.explicacion(en_ejecucion=True, instalada="1.3.0", nueva="1.4.0")
	assert "preguntarle si quiere instalarlo" in texto and "reiniciarse" in texto
	assert "1.3.0" in texto and "1.4.0" in texto
	assert "no parece estar en ejecución" not in texto
	assert "solo se hace una vez" not in texto
	assert "Ya tiene instalada esta versión (2.0)" in instalar.explicacion(True, "2.0", "2.0")


def test_explicacion_al_arrancar_y_sin_nvda():
	texto = instalar.explicacion(False, None, "1.0", al_arrancar=True)
	assert texto.startswith("zCommander tiene un complemento para NVDA")
	assert "no parece estar en ejecución" in texto
	assert "solo se hace una vez" in texto and "menú Ayuda" in texto


def test_abrir_usa_startfile_con_la_ruta(paquete, monkeypatch):
	abiertos = []
	monkeypatch.setattr(os, "startfile", abiertos.append, raising=False)
	correcto, _mensaje = instalar.abrir_instalador(paquete)
	assert correcto and abiertos == [str(paquete)]


def test_abrir_sin_archivo_no_llama_a_nada(tmp_path):
	correcto, mensaje = instalar.abrir_instalador(tmp_path / "no-existe.nvda-addon")
	assert not correcto and "No se encontró" in mensaje


def test_abrir_sin_asociacion(paquete):
	def sin_asociacion(_ruta):
		raise OSError(1155, "No hay ninguna aplicación asociada")

	correcto, mensaje = instalar.abrir_instalador(paquete, abrir=sin_asociacion)
	assert not correcto
	assert str(paquete) in mensaje and "Tienda de complementos" in mensaje


class _Config:
	def __init__(self, ofrecido=False):
		self.valores = {instalar.CLAVE_OFRECIDO: ofrecido}

	def obtener(self, clave, por_defecto=None):
		return self.valores.get(clave, por_defecto)

	def establecer(self, clave, valor, **_opciones):
		self.valores[clave] = valor
		return True


@pytest.mark.parametrize(
	("ofrecido", "en_marcha", "instalada", "esperado"),
	[
		(False, True, None, True),
		(True, True, None, False),  # ya se ofreció una vez
		(False, False, None, False),  # NVDA no está activo
		(False, True, "1.0.0", False),  # ya está instalado
	],
)
def test_debe_ofrecerse(ofrecido, en_marcha, instalada, esperado):
	assert instalar.debe_ofrecerse(_Config(ofrecido), lambda: en_marcha, lambda: instalada) is esperado


def test_paquete_desactualizado(tmp_path):
	origen = tmp_path / "nvda_addon"
	(origen / "addon").mkdir(parents=True)
	fuente = origen / "addon" / "x.py"
	fuente.write_text("x = 1\n", encoding="utf-8")
	paquete = _crear_paquete(tmp_path / "p.nvda-addon")
	os.utime(fuente, (paquete.stat().st_mtime - 100,) * 2)
	assert instalar.paquete_desactualizado(paquete, origen) is False
	os.utime(fuente, (paquete.stat().st_mtime + 100,) * 2)
	assert instalar.paquete_desactualizado(paquete, origen) is True


def test_construir_desde_fuente_genera_en_data_bin_nvda(datos_temporales):
	"""Desde el código fuente se genera el paquete de esta versión en la data (temporal) de la prueba."""
	ruta = instalar.construir_desde_fuente()
	assert ruta == instalar.ruta_complemento()
	assert instalar.version_del_paquete(ruta) == APP_VERSION


def test_construir_en_la_compilada_no_se_puede(monkeypatch):
	monkeypatch.setattr(paths, "CONGELADA", True)
	with pytest.raises(RuntimeError, match="no trae el complemento"):
		instalar.construir_desde_fuente()


# ════════════════════════════════════════════════════════════════════════════
# Parte wx (la pregunta se simula; el diálogo real solo se construye)
# ════════════════════════════════════════════════════════════════════════════

def test_dialogo_accesible(app_wx):
	"""revisar_teclado, botones que dicen la acción y Cancelar como predeterminado (15.1)."""
	dialogo = instalar.crear_dialogo(None, instalar.explicacion(True, None, "1.0"))
	try:
		afirmar_teclado_correcto(dialogo)
		abrir_boton = dialogo.FindWindow(dialogo.ids_opciones[0])
		cancelar = dialogo.FindWindow(wx.ID_CANCEL)
		assert abrir_boton.GetLabel() == "&Abrir el instalador de NVDA"
		assert cancelar.GetLabel() == "&Cancelar"
		assert dialogo.GetDefaultItem() is cancelar
		assert abrir_boton.GetHelpText() and cancelar.GetHelpText()
		assert dialogo.GetTitle() == "Complemento de zCommander para NVDA"
	finally:
		dialogo.Destroy()


@pytest.fixture
def simulado(monkeypatch):
	"""Pregunta y errores simulados; NVDA activo y sin el complemento instalado."""
	registro = SimpleNamespace(preguntas=[], errores=[], respuesta=False)

	def preguntar(padre, texto):
		registro.preguntas.append(texto)
		return registro.respuesta

	monkeypatch.setattr(instalar, "_preguntar", preguntar)
	monkeypatch.setattr(instalar, "_mostrar_error", lambda padre, texto: registro.errores.append(texto))
	monkeypatch.setattr(instalar, "nvda_en_ejecucion", lambda: True)
	monkeypatch.setattr(instalar, "version_instalada", lambda *a, **k: None)
	return registro


def test_cancelar_no_abre(paquete, simulado):
	assert instalar.ofrecer_instalacion(None, paquete) is False
	assert "reiniciarse" in simulado.preguntas[0] and "1.4.0" in simulado.preguntas[0]


def test_aceptar_abre_y_lo_anuncia(paquete, simulado, monkeypatch):
	from app.ui.accesibilidad import voz

	simulado.respuesta = True
	abiertos = []
	monkeypatch.setattr(os, "startfile", abiertos.append, raising=False)
	assert instalar.ofrecer_instalacion(None, paquete) is True
	assert abiertos == [str(paquete)]
	assert any("ventana de instalación" in d for d in voz.dichos_en_prueba)


def test_aceptar_sin_asociacion_explica(paquete, simulado, monkeypatch):
	simulado.respuesta = True

	def sin_asociacion(_ruta):
		raise OSError(1155, "sin asociación")

	monkeypatch.setattr(os, "startfile", sin_asociacion, raising=False)
	assert instalar.ofrecer_instalacion(None, paquete) is False
	assert "Tienda de complementos" in simulado.errores[0]


def test_sin_paquete_lo_genera(tmp_path, paquete, simulado):
	llamadas = []

	def construir():
		llamadas.append(True)
		return paquete

	instalar.ofrecer_instalacion(None, tmp_path / "falta.nvda-addon", construir=construir)
	assert llamadas and simulado.preguntas


def test_si_no_se_puede_generar_avisa(tmp_path, simulado):
	def construir():
		raise RuntimeError("manifiesto roto")

	assert instalar.ofrecer_instalacion(None, tmp_path / "falta.nvda-addon", construir=construir) is False
	assert "manifiesto roto" in simulado.errores[0]
	assert not simulado.preguntas


def test_sin_paquete_ni_constructor_avisa(tmp_path, simulado):
	assert instalar.ofrecer_instalacion(None, tmp_path / "falta.nvda-addon") is False
	assert "No se encontró" in simulado.errores[0]


def test_abrir_desde_el_boton_genera_y_pregunta(simulado, datos_temporales):
	"""``abrir(padre)`` (botón de Accesibilidad y orden): desde el código fuente genera el paquete si falta."""
	instalar.abrir(None)
	assert instalar.ruta_complemento().is_file()
	assert len(simulado.preguntas) == 1


def test_boton_registrado_en_accesibilidad():
	botones = dict(paginas_propias.BOTONES_PAGINA)["Accesibilidad"]
	assert ("Instalar el complemento de zCommander para &NVDA...", "app.ui.instalar_complemento:abrir") in botones
	assert callable(instalar.abrir) and not getattr(instalar.abrir, "provisional", False)


# ════════════════════════════════════════════════════════════════════════════
# Orden complemento_nvda y ofrecimiento al arrancar (nvda_nv)
# ════════════════════════════════════════════════════════════════════════════

def test_orden_complemento_nvda(monkeypatch):
	from app.ui import ordenes

	llamadas = []
	monkeypatch.setattr(instalar, "abrir", llamadas.append)
	ventana = object()
	nvda_nv.complemento_nvda(SimpleNamespace(ventana=ventana))
	assert llamadas == [ventana]
	orden = ordenes.POR_ID["complemento_nvda"]
	assert orden.manejador == "nvda_nv.complemento_nvda" and orden.bloque == "NV"
	assert not getattr(nvda_nv.complemento_nvda, "provisional", False)
	assert not getattr(nvda_nv.instalar, "provisional", False)


class _VentanaFalsa:
	def __init__(self, config, visible=True):
		self.config = config
		self.visible = visible

	def __bool__(self):
		return True

	def IsShown(self):  # noqa: N802 - API de wx
		return self.visible

	def IsIconized(self):  # noqa: N802 - API de wx
		return False

	def IsActive(self):  # noqa: N802 - API de wx
		return self.visible


@pytest.fixture
def arranque(monkeypatch):
	registro = SimpleNamespace(ofrecidos=[], programados=[], debe=True)
	monkeypatch.setattr(instalar, "debe_ofrecerse", lambda config: registro.debe)
	monkeypatch.setattr(
		instalar, "ofrecer_instalacion", lambda padre, **opciones: registro.ofrecidos.append((padre, opciones))
	)
	monkeypatch.setattr(wx, "CallLater", lambda ms, funcion, *args: registro.programados.append((ms, funcion, args)))
	return registro


def test_instalar_programa_el_ofrecimiento(arranque):
	config = _Config()
	nvda_nv.instalar(_VentanaFalsa(config))
	assert len(arranque.programados) == 1
	assert arranque.programados[0][0] == nvda_nv.RETRASO_INICIAL_MS
	arranque.programados.clear()
	nvda_nv.instalar(_VentanaFalsa(_Config(ofrecido=True)))
	assert not arranque.programados, "Ya se ofreció: no se programa nada"


def test_se_ofrece_una_sola_vez(arranque):
	config = _Config()
	ventana = _VentanaFalsa(config)
	nvda_nv._intentar(ventana, 0, None)
	assert len(arranque.ofrecidos) == 1
	padre, opciones = arranque.ofrecidos[0]
	assert padre is ventana and opciones["al_arrancar"] is True
	assert config.valores[instalar.CLAVE_OFRECIDO] is True
	nvda_nv._intentar(ventana, 0, None)
	assert len(arranque.ofrecidos) == 1


def test_espera_a_que_la_ventana_se_vea(arranque):
	config = _Config()
	ventana = _VentanaFalsa(config, visible=False)
	nvda_nv._intentar(ventana, 0, None)
	assert not arranque.ofrecidos and config.valores[instalar.CLAVE_OFRECIDO] is False
	ms, funcion, argumentos = arranque.programados[-1]
	assert ms == nvda_nv.ESPERA_MS and argumentos == (ventana, 1, True)
	nvda_nv._intentar(ventana, nvda_nv.MAX_INTENTOS, True)
	assert len(arranque.programados) == 1, "Tras el último intento no se reprograma"
	ventana.visible = True
	funcion(*argumentos)
	assert len(arranque.ofrecidos) == 1


def test_no_se_ofrece_si_no_procede(arranque):
	arranque.debe = False
	config = _Config()
	nvda_nv._intentar(_VentanaFalsa(config), 0, None)
	assert not arranque.ofrecidos and not arranque.programados
	assert config.valores[instalar.CLAVE_OFRECIDO] is False, "Sin NVDA no se gasta el único ofrecimiento"


def test_un_fallo_al_ofrecer_no_rompe_nada(arranque, monkeypatch):
	def roto(config):
		raise RuntimeError("fallo")

	monkeypatch.setattr(instalar, "debe_ofrecerse", roto)
	nvda_nv._intentar(_VentanaFalsa(_Config()), 0, None)
	assert not arranque.ofrecidos


def test_ventana_oculta_real_no_es_buen_momento(app_wx):
	marco = wx.Frame(None)
	try:
		assert nvda_nv.momento_adecuado(marco) is False
	finally:
		marco.Destroy()
