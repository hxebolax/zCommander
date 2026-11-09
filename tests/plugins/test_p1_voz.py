# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas mínimas de la lectura en voz y los audiolibros (diseño 2.0, 11.17 y 18.2)."""

from __future__ import annotations

import os
import threading

import pytest

from .p1_comun import cargar, config_limpia, interfaz_real, modulo, revisar  # noqa: F401 - fixtures


class VozFalsa:
	def __init__(self) -> None:
		self.dichas: list[tuple[str, int]] = []
		self.aviso = None
		self.pausada = False
		self.callada = 0

	def hablar(self, texto, numero, al_terminar):
		self.dichas.append((texto, numero))
		self.aviso = al_terminar

	def pausar(self):
		self.pausada = True

	def continuar(self):
		self.pausada = False

	def callar(self):
		self.callada += 1

	def terminar_frase(self):
		"""SAPI avisa del final de la frase en curso (nunca mientras está en pausa)."""
		assert not self.pausada
		self.aviso(self.dichas[-1][1])


def test_division_en_frases_y_parrafos_con_abreviaturas():
	cargar("voz")
	texto = modulo("voz", "texto")
	parrafo = ("El Sr. García llegó a las 10. Trajo libros, p. ej. novelas y poesía, etc. y se fue. ¿Vienes? ¡Claro! "
		"Lo dijo la Dra. Pérez en la pág. 3. «Adiós», dijo J. R. R. Tolkien... Y terminó.")
	assert texto.frases_de(parrafo) == [
		"El Sr. García llegó a las 10.",
		"Trajo libros, p. ej. novelas y poesía, etc. y se fue.",
		"¿Vienes?",
		"¡Claro!",
		"Lo dijo la Dra. Pérez en la pág. 3.",
		"«Adiós», dijo J. R. R. Tolkien...",
		"Y terminó.",
	]
	frases = texto.dividir("Primer párrafo. Sigue aquí.\n\nSegundo\npárrafo partido.\r\n\r\nTercero.")
	assert [(f.parrafo, f.texto) for f in frases] == [(0, "Primer párrafo."), (0, "Sigue aquí."), (1, "Segundo párrafo partido."),
		(2, "Tercero.")]
	assert [f.parrafo for f in texto.dividir("Una línea.\nOtra línea.")] == [0, 1], "sin líneas en blanco, cada línea es un párrafo"
	assert texto.decodificar("ñandú".encode("cp1252")) == "ñandú"
	assert texto.decodificar("\ufeffhola".encode("utf-8")) == "hola"
	assert texto.xml_sapi("a < b & c", 3, 400) == '<pitch absmiddle="3">a &lt; b &amp; c</pitch><silence msec="400"/>'


def _lector(tmp_path, voz):
	cargar("voz")
	lector_modulo = modulo("voz", "lector")
	anuncios: list[str] = []
	sonidos: list[str] = []
	lector = lector_modulo.Lector(voz, anunciar=lambda t, nivel="normal", *a, **k: anuncios.append(t), sonar=sonidos.append,
		posiciones=lector_modulo.Posiciones(tmp_path / "datos"), pausa_parrafo_ms=lambda: 0)
	return lector, anuncios, sonidos


TEXTO = "Uno. Dos. Tres.\n\nCuatro. Cinco."


def test_con_una_voz_falsa_pausa_y_continuar_reanudan_en_la_frase_correcta(tmp_path):
	voz = VozFalsa()
	lector, anuncios, sonidos = _lector(tmp_path, voz)
	ruta = tmp_path / "texto.txt"
	ruta.write_text(TEXTO, encoding="utf-8")
	lector.leer(TEXTO, str(ruta))
	assert voz.dichas[-1][0] == "Uno."
	voz.terminar_frase()
	assert voz.dichas[-1][0] == "Dos."
	lector.pausa_continuar()
	assert voz.pausada and lector.estado == "pausado" and anuncios[-1] == "Lectura en pausa"
	lector.pausa_continuar()
	assert not voz.pausada and lector.estado == "leyendo"
	voz.terminar_frase()
	assert voz.dichas[-1][0] == "Tres.", "continúa con la frase siguiente a la que se pausó"
	lector.parrafo_siguiente()
	assert voz.dichas[-1][0] == "Cuatro."
	lector.frase_anterior()
	assert voz.dichas[-1][0] == "Tres."
	lector.parrafo_anterior()
	assert voz.dichas[-1][0] == "Uno.", "con la frase en mitad de un párrafo, vuelve a su principio"
	# Un aviso viejo (de una frase que se saltó) no hace avanzar.
	viejo = voz.dichas[-2][1]
	voz.aviso(viejo)
	assert voz.dichas[-1][0] == "Uno."
	for _ in range(4):
		voz.terminar_frase()
	assert voz.dichas[-1][0] == "Cinco."
	voz.terminar_frase()
	assert lector.estado == "detenido" and sonidos == ["fin"] and anuncios[-1] == "Fin de la lectura"


def test_recuerda_donde_se_dejo(tmp_path):
	voz = VozFalsa()
	lector, anuncios, _s = _lector(tmp_path, voz)
	ruta = tmp_path / "libro.txt"
	ruta.write_text(TEXTO, encoding="utf-8")
	lector.leer(TEXTO, str(ruta))
	voz.terminar_frase()
	voz.terminar_frase()
	lector.detener()
	otro, anuncios_otro, _s = _lector(tmp_path, VozFalsa())
	otro.leer(TEXTO, str(ruta))
	assert otro.voz.dichas[-1][0] == "Tres."
	assert anuncios_otro[0] == "Continúa donde se dejó, frase 3 de 5"


def test_exportar_llama_a_ffmpeg_con_los_argumentos_esperados(tmp_path):
	cargar("voz")
	operacion = modulo("voz", "operacion")
	from app.plugins.api import ContextoEjecucion, pruebas
	from app.services.vfs import resolver

	fuente = tmp_path / "cuento.txt"
	fuente.write_text("Había una vez. Un gato.\n\nFin.", encoding="utf-8")
	escritos: list[tuple[list[str], str]] = []
	llamadas: list[list[str]] = []

	def exportar_wav(textos, ruta, ajustes, cancelado, al_avanzar):
		escritos.append((list(textos), ruta))
		with open(ruta, "wb") as archivo:
			archivo.write(b"RIFF")
		for numero in range(len(textos)):
			al_avanzar(numero)
		return True

	class Resultado:
		codigo, errores, cancelado = 0, b"", False

	def ejecutar(argumentos, **opciones):
		llamadas.append(argumentos)
		with open(argumentos[-1], "wb") as archivo:
			archivo.write(b"ID3")
		return Resultado()

	def piezas(ruta, _ctx):
		return operacion.piezas_de_documento("cuento", [("", 1, fuente.read_text(encoding="utf-8"))], False)

	op = operacion.OperacionAudiolibro("Convertir", resolver.proveedor_local(), [str(fuente)], carpeta=str(tmp_path), formato="mp3",
		obtener_piezas=piezas, exportar_wav=exportar_wav, ajustes=None, pausa_ms=400, ffmpeg=lambda: "C:\\ff\\ffmpeg.exe",
		ejecutar=ejecutar)
	op.ejecutar(ContextoEjecucion(threading.Event(), pruebas.DecisorFalso()))
	assert not op.errores
	textos, wav = escritos[0]
	assert textos == ['Había una vez. Un gato.<silence msec="400"/>', 'Fin.<silence msec="400"/>']
	argumentos = llamadas[0]
	assert argumentos == ["C:\\ff\\ffmpeg.exe", "-hide_banner", "-nostdin", "-n", "-loglevel", "error", "-i", wav, "-ac", "1",
		"-c:a", "libmp3lame", "-b:a", "64k", argumentos[-1]]
	assert wav.endswith(".wav") and argumentos[-1].endswith(".mp3") and ".zcparcial-" in argumentos[-1]
	assert (tmp_path / "cuento.mp3").read_bytes() == b"ID3"
	assert not [n for n in os.listdir(tmp_path) if ".zcparcial-" in n], "los temporales se borran"
	assert operacion.argumentos_ffmpeg("f", "a.wav", "b.opus", "opus")[-7:] == ["-c:a", "libopus", "-b:a", "32k", "-application",
		"voip", "b.opus"]


def test_dividir_por_capitulos():
	cargar("voz")
	operacion = modulo("voz", "operacion")
	secciones = [("Prólogo", 1, "Antes de nada."), ("Capítulo 1: El viaje", 1, "Salieron."), ("Detalle", 2, "Más."),
		("Capítulo 2", 1, "Volvieron.")]
	piezas = operacion.piezas_de_documento("Libro", secciones, True)
	assert [p.nombre for p in piezas] == ["Libro - 01 - Prólogo", "Libro - 02 - Capítulo 1 El viaje", "Libro - 03 - Capítulo 2"]
	assert piezas[1].parrafos == ["Capítulo 1: El viaje", "Salieron.", "Detalle", "Más."]
	assert [p.nombre for p in operacion.piezas_de_documento("Libro", secciones, False)] == ["Libro"]


@pytest.mark.interfaz
def test_sapi_lista_las_voces_de_windows():
	cargar("voz")
	sapi = modulo("voz", "sapi")
	assert all(isinstance(v, str) and v for v in sapi.voces())


@pytest.mark.usefixtures("interfaz_real")
def test_dialogos_pasan_revisar_teclado():
	zc, _p = cargar("voz")
	revisar(zc.instancia.ventanas_para_revisar(None))
	from app.plugins import api

	assert "zc.voz" in api.interfaz().dialogos, "la configuración avanzada (elegir la voz) se registra al activarse"
