# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de zc.monitor (diseño 2.0, 11.18 y 18.2) con carpetas temporales reales."""

from __future__ import annotations

import os
import threading
import time
import zipfile
from pathlib import Path

import pytest

from app.plugins import api, registro
from app.plugins.api import pruebas
from app.services import eventos
from tests.plugins import p5_comun

NOMBRE = "monitor"


@pytest.fixture
def zc():
	creado = p5_comun.anfitrion(NOMBRE)
	yield creado
	creado.instancia.desactivar()


@pytest.fixture
def reglas(zc):
	return p5_comun.modulo(NOMBRE, "reglas")


@pytest.fixture
def vigilante(zc):
	return p5_comun.modulo(NOMBRE, "vigilante")


def _llegadas() -> list[dict]:
	recibidas: list[dict] = []
	eventos.bus().suscribir("zc.monitor:llegada", lambda **datos: recibidas.append(datos))
	return recibidas


def test_sin_carpetas_activar_no_abre_vigilantes(zc):
	assert zc.instancia._vigilantes == [] and zc.instancia._revisor is None


def test_estabilidad_avisa_una_vez_cuando_deja_de_crecer(vigilante):
	reloj = [0.0]
	tamanos = {"C:\\d\\a.pdf": (100, 1.0)}
	estabilidad = vigilante.Estabilidad(5, reloj=lambda: reloj[0], estado=lambda r: tamanos.get(r), abrible=lambda r: True)
	estabilidad.notificar("C:\\d\\a.pdf")
	reloj[0] = 3
	assert estabilidad.revisar() == []
	tamanos["C:\\d\\a.pdf"] = (5000, 2.0)  # sigue creciendo, sin aviso de Windows todavía
	reloj[0] = 5.5
	assert estabilidad.revisar() == []  # distinto de lo visto al avisar: se vuelve a esperar
	reloj[0] = 10
	assert estabilidad.revisar() == []
	reloj[0] = 10.6
	assert estabilidad.revisar() == ["C:\\d\\a.pdf"]
	reloj[0] = 20
	assert estabilidad.revisar() == []
	# Un aviso más sin cambios (Windows avisa de la fecha de acceso, un antivirus lo abre...) no se repite.
	estabilidad.notificar("C:\\d\\a.pdf")
	reloj[0] = 30
	assert estabilidad.revisar() == []


def test_estabilidad_espera_a_que_nadie_lo_escriba_e_ignora_temporales(vigilante):
	reloj = [0.0]
	abierto = {"valor": False}
	estabilidad = vigilante.Estabilidad(1, reloj=lambda: reloj[0], estado=lambda r: (1, 1.0), abrible=lambda r: abierto["valor"])
	estabilidad.notificar("C:\\d\\b.zip")
	estabilidad.notificar("C:\\d\\b.zip.crdownload")
	reloj[0] = 2
	assert estabilidad.revisar() == []
	abierto["valor"] = True
	reloj[0] = 4
	assert estabilidad.revisar() == ["C:\\d\\b.zip"]


def test_archivo_creado_en_una_carpeta_vigilada_se_anuncia_una_vez(tmp_path):
	carpeta = tmp_path / "Descargas"
	carpeta.mkdir()
	recibidas = _llegadas()
	zc = p5_comun.anfitrion(NOMBRE, config={"retraso_s": 1, "carpetas": [str(carpeta)]})
	complemento = zc.instancia
	try:
		assert complemento.esperar_listo()
		with open(carpeta / "factura.pdf", "wb") as archivo:
			for _ in range(5):
				archivo.write(b"x" * 400_000)
				archivo.flush()
				time.sleep(0.15)
		limite = time.monotonic() + 8
		while not recibidas and time.monotonic() < limite:
			time.sleep(0.1)
		time.sleep(2.5)
		assert [Path(r["ruta"]).name for r in recibidas] == ["factura.pdf"]
		assert recibidas[0]["tamano"] == 2_000_000
		assert zc.sonidos_pedidos == ["zc.monitor:archivo_nuevo"]
		assert len(zc.anuncios) == 1 and zc.anuncios[0][1] == api.RESULTADO
		assert zc.anuncios[0][0].startswith("Nuevo en Descargas: factura.pdf, ")
	finally:
		complemento.desactivar()


def test_regla_pdf_mueve_a_documentos_y_deshacer_lo_devuelve(tmp_path, reglas, zc):
	descargas, documentos = tmp_path / "Descargas", tmp_path / "Documentos"
	descargas.mkdir()
	regla = reglas.Regla("PDF", patron="*.pdf", accion=reglas.MOVER, destino=str(documentos))
	zc.config.establecer("reglas", reglas.a_lista([regla]))
	complemento = zc.instancia
	recibidas = _llegadas()
	(descargas / "factura.pdf").write_bytes(b"%PDF")
	(descargas / "nota.txt").write_text("x", encoding="utf-8")
	complemento.al_llegar(str(descargas / "factura.pdf"))
	complemento.al_llegar(str(descargas / "nota.txt"))
	assert (documentos / "factura.pdf").read_bytes() == b"%PDF"
	assert not (descargas / "factura.pdf").exists()
	assert (descargas / "nota.txt").exists()
	assert recibidas[0]["hecho"].texto == f"movido a {documentos}"
	assert recibidas[1]["hecho"] is None
	assert zc.sonidos_pedidos == ["zc.monitor:archivo_nuevo", "zc.monitor:regla_aplicada", "zc.monitor:archivo_nuevo"]
	assert "Regla PDF: movido a" in zc.anuncios[0][0]
	apuntes = reglas.Registro(zc.datos).apuntes
	assert [a.regla for a in apuntes] == ["PDF"]
	assert complemento.deshacer_ultimo().startswith("Deshecho: factura.pdf vuelve a")
	assert (descargas / "factura.pdf").exists() and not (documentos / "factura.pdf").exists()
	assert complemento.deshacer_ultimo() == "No hay nada que deshacer"


def test_un_nombre_ocupado_no_se_pisa(tmp_path, reglas):
	destino = tmp_path / "d"
	destino.mkdir()
	(destino / "a.pdf").write_text("viejo", encoding="utf-8")
	(tmp_path / "a.pdf").write_text("nuevo", encoding="utf-8")
	hecho = reglas.aplicar(reglas.Regla("R", accion=reglas.COPIAR, destino=str(destino)), str(tmp_path / "a.pdf"))
	assert hecho.deshacer["destino"] == str(destino / "a (2).pdf")
	assert (destino / "a.pdf").read_text(encoding="utf-8") == "viejo"


def test_simulacion_lista_sin_mover(tmp_path, reglas):
	(tmp_path / "a.pdf").write_text("a", encoding="utf-8")
	(tmp_path / "b.txt").write_text("b", encoding="utf-8")
	lista = [reglas.Regla("PDF", patron="*.pdf", accion=reglas.MOVER, destino=str(tmp_path / "Documentos"))]
	hechos = reglas.simular(lista, str(tmp_path))
	assert [(Path(h.archivo).name, h.texto) for h in hechos] == [("a.pdf", f"Se movería a {tmp_path / 'Documentos'}")]
	assert (tmp_path / "a.pdf").exists() and not (tmp_path / "Documentos").exists()


def test_condiciones_de_tamano_antiguedad_y_carpeta(reglas):
	ahora = time.time()
	regla = reglas.Regla("R", patron="*.iso", tamano_min_kb=1, tamano_max_kb=10, antiguedad_dias=2, carpeta="C:\\Descargas")
	assert reglas.coincide(regla, "C:\\Descargas\\a.ISO", "C:\\Descargas", 2048, ahora - 3 * 86400, ahora)
	assert not reglas.coincide(regla, "C:\\Descargas\\a.iso", "C:\\Descargas", 512, ahora - 3 * 86400, ahora)
	assert not reglas.coincide(regla, "C:\\Descargas\\a.iso", "C:\\Descargas", 2048, ahora, ahora)
	assert not reglas.coincide(regla, "C:\\Otra\\a.iso", "C:\\Otra", 2048, ahora - 3 * 86400, ahora)
	regla.activa = False
	assert not reglas.coincide(regla, "C:\\Descargas\\a.iso", "C:\\Descargas", 2048, ahora - 3 * 86400, ahora)


def test_extraer_un_zip_sin_salir_de_su_carpeta(tmp_path, reglas):
	comprimido = tmp_path / "fotos.zip"
	with zipfile.ZipFile(comprimido, "w") as archivo:
		archivo.writestr("a.txt", "a")
		archivo.writestr("../fuera.txt", "malo")
	hecho = reglas.aplicar(reglas.Regla("Z", patron="*.zip", accion=reglas.EXTRAER), str(comprimido))
	assert hecho.ok and (tmp_path / "fotos" / "a.txt").read_text(encoding="utf-8") == "a"
	assert not (tmp_path / "fuera.txt").exists()


def test_etiquetar_sin_el_complemento_notas_lo_explica(tmp_path, reglas, zc, monkeypatch):
	(tmp_path / "a.pdf").write_text("a", encoding="utf-8")
	monkeypatch.setattr(zc, "complemento", lambda id: None)
	with pytest.raises(reglas.ErrorRegla, match="Notas, comentarios y etiquetas"):
		zc.instancia._etiquetar(str(tmp_path / "a.pdf"), "factura")


def test_orden_se_ejecuta_en_la_interfaz_con_el_archivo(tmp_path, reglas, zc, app_wx):
	interfaz = p5_comun.con_interfaz()
	try:
		regla = reglas.Regla("Oír", patron="*.mp3", accion=reglas.ORDEN, orden="zc.reproductor:reproducir")
		zc.config.establecer("reglas", reglas.a_lista([regla]))
		(tmp_path / "a.mp3").write_bytes(b"ID3")
		zc.instancia.al_llegar(str(tmp_path / "a.mp3"))
		assert interfaz.ordenes == [("zc.reproductor:reproducir", str(tmp_path / "a.mp3"))]
	finally:
		api.fijar_interfaz(None)


def test_exporta_operacion_de_reglas_que_pregunta_los_errores(tmp_path, reglas, zc):
	(tmp_path / "a.pdf").write_text("a", encoding="utf-8")
	(tmp_path / "b.pdf").write_text("b", encoding="utf-8")
	destino = tmp_path / "ocupado.txt"
	destino.write_text("no soy carpeta", encoding="utf-8")
	zc.config.establecer("reglas", reglas.a_lista([reglas.Regla("PDF", patron="*.pdf", accion=reglas.MOVER, destino=str(destino))]))
	operacion = registro.exportados("zc.monitor")["operacion_de_reglas"](str(tmp_path))
	assert isinstance(operacion, api.Operacion)
	decisor = pruebas.DecisorFalso([api.AccionError.OMITIR, api.AccionError.OMITIR])
	contexto = api.ContextoEjecucion(threading.Event(), decisor)
	contexto.operacion = operacion
	operacion.ejecutar(contexto)
	assert operacion.estado == api.Estado.TERMINADA_CON_ERRORES
	assert [tipo for tipo, _p in decisor.preguntas] == ["error", "error"]


def test_pausar_es_una_casilla(zc):
	estado = registro.funcion("estado", "zc.monitor:pausar")
	contexto = pruebas.contexto_de_prueba()
	assert estado(contexto) is False
	zc.ejecutar("pausar", contexto)
	assert estado(contexto) is True
	zc.ejecutar("pausar", contexto)
	assert estado(contexto) is False


def test_ordenes_con_manejador_real(zc):
	for orden in ("reglas", "pausar", "registro"):
		manejador = registro.manejador(f"zc.monitor:{orden}")
		assert manejador is not None and not getattr(manejador, "provisional", False)


# ── Diálogos (wx) ────────────────────────────────────────────────────────────


@pytest.fixture
def interfaz(app_wx):
	creada = p5_comun.con_interfaz()
	yield creada
	api.fijar_interfaz(None)


def test_dialogos_pasan_revisar_teclado(zc, interfaz):
	ventanas = zc.instancia.ventanas_para_revisar(None)
	assert len(ventanas) == 3
	try:
		for ventana in ventanas:
			assert p5_comun.problemas_de_teclado(ventana) == [], ventana.GetTitle()
	finally:
		for ventana in ventanas:
			ventana.Destroy()


def test_dialogo_ordena_las_reglas_y_valida_el_editor(zc, reglas, interfaz, tmp_path):
	ventana = p5_comun.modulo(NOMBRE, "ventana")
	zc.config.establecer("reglas", reglas.a_lista([reglas.Regla("Uno"), reglas.Regla("Dos")]))
	dialogo = ventana.DialogoMonitor(zc.instancia, None)
	editor = ventana.DialogoRegla(zc, None, reglas.Regla("X", accion=reglas.RENOMBRAR), [str(tmp_path)])
	try:
		assert dialogo.agregar_carpeta(str(tmp_path))
		assert not dialogo.agregar_carpeta(str(tmp_path).upper())
		dialogo.tabla.enfocar_fila(1, anunciar=False)
		dialogo.mover(-1)
		carpetas, lista = dialogo.valores()
		assert carpetas == [str(tmp_path)] and [r.nombre for r in lista] == ["Dos", "Uno"]
		assert not editor.destino.IsEnabled() and editor.mascara.IsEnabled()
		assert editor.regla().error() == "Escriba la máscara del nombre nuevo."
	finally:
		dialogo.Destroy()
		editor.Destroy()


def test_dialogo_de_registro_muestra_lo_hecho(zc, reglas, interfaz, tmp_path):
	(tmp_path / "a.pdf").write_text("a", encoding="utf-8")
	hecho = reglas.aplicar(reglas.Regla("PDF", accion=reglas.MOVER, destino=str(tmp_path / "d")), str(tmp_path / "a.pdf"))
	zc.instancia.registro.apuntar(str(tmp_path), hecho)
	ventana = p5_comun.modulo(NOMBRE, "ventana")
	dialogo = ventana.DialogoRegistro(zc.instancia, None)
	try:
		assert dialogo.lista.valores_fila(0)[1:4] == ["a.pdf", "PDF", f"movido a {tmp_path / 'd'}"]
		dialogo.deshacer()
		assert os.path.exists(tmp_path / "a.pdf")
		assert dialogo.lista.valores_fila(0)[4] == "Sí"
	finally:
		dialogo.Destroy()
