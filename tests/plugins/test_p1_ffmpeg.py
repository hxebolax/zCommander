# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas mínimas del conversor multimedia con FFmpeg (diseño 2.0, 11.6 y 18.2).

Las que usan el FFmpeg real de ``data/bin/ffmpeg`` llevan las marcas
``componentes`` y ``lento`` y se saltan si el binario no está.
"""

from __future__ import annotations

import os
import threading
import wave

import pytest

from .p1_comun import RAIZ, cargar, config_limpia, interfaz_real, modulo, revisar  # noqa: F401 - fixtures

FFPROBE_EJEMPLO = """{
    "streams": [
        {"index": 0, "codec_name": "h264", "codec_long_name": "H.264 / AVC", "codec_type": "video", "width": 1920,
         "height": 1080, "avg_frame_rate": "30000/1001", "bit_rate": "4500000", "tags": {"language": "und"}},
        {"index": 1, "codec_name": "aac", "codec_type": "audio", "sample_rate": "48000", "channels": 2,
         "channel_layout": "stereo", "bit_rate": "128000", "tags": {"language": "spa"}}
    ],
    "format": {"filename": "video.mp4", "format_name": "mov,mp4,m4a,3gp,3g2,mj2", "format_long_name": "QuickTime / MOV",
        "duration": "125.500000", "size": "72000000", "bit_rate": "4630000", "tags": {"title": "Vacaciones"}}
}"""


def _ffmpeg():
	cargar("ffmpeg")
	return modulo("ffmpeg", "perfiles"), modulo("ffmpeg", "sonda")


def test_constructor_de_argumentos_de_cada_perfil():
	perfiles, _sonda = _ffmpeg()
	assert perfiles.argumentos_convertir("C:\\ff\\ffmpeg.exe", "C:\\a\\-raro.wav", "D:\\b\\salida.mp3", "mp3", "192") == [
		"C:\\ff\\ffmpeg.exe", "-hide_banner", "-nostdin", "-n", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
		"-i", "C:\\a\\-raro.wav", "-vn", "-c:a", "libmp3lame", "-b:a", "192k", "-map_metadata", "0", "D:\\b\\salida.mp3"]
	for perfil in perfiles.PERFILES.values():
		if perfil.id == "personalizado":
			continue
		for calidad, _nombre in perfil.calidades:
			argumentos = perfiles.argumentos_convertir("ff.exe", "origen.x", "destino" + perfil.extension, perfil.id, calidad, hilos=2)
			assert all(isinstance(a, str) for a in argumentos)
			assert argumentos[argumentos.index("-i") + 1] == "origen.x", "la ruta de origen va justo tras -i"
			assert argumentos[-1] == "destino" + perfil.extension, "el destino va el último"
			assert "-y" not in argumentos and "-n" in argumentos
			assert argumentos[argumentos.index("-threads") + 1] == "2"
	assert perfiles.argumentos_convertir("f", "o", "d", "flac", "8", conservar_etiquetas=False)[-3:] == ["-map_metadata", "-1", "d"]
	assert perfiles.partir_perfil("mp3_192") == ("mp3", "192")
	assert perfiles.partir_perfil("desconocido") == ("mp3", "192")
	assert perfiles.argumentos_recortar("f", "o.mp4", "d.mp4", 90, 300, True)[9:15] == ["-ss", "90.000", "-to", "300.000", "-i", "o.mp4"]
	assert "concat" in perfiles.argumentos_unir("f", "lista.txt", "d.mp3")
	assert perfiles.lista_concat(["C:\\a\\Mi 'tema'.mp3"]).splitlines()[1] == "file 'C:/a/Mi '\\''tema'\\''.mp3'"


def test_el_analizador_de_progress_calcula_el_porcentaje():
	_perfiles, sonda = _ffmpeg()
	analizador = sonda.AnalizadorProgreso(10.0)
	analizador.alimentar(b"frame=1\nout_time_us=2500")
	assert analizador.porcentaje == 0, "una línea partida no se lee hasta que llega entera"
	analizador.alimentar(b"000\nout_time_ms=9999999999\nprogress=continue\n")
	assert analizador.porcentaje == 25
	analizador.alimentar(b"out_time_us=5000000\r\n")
	assert analizador.porcentaje == 50
	analizador.alimentar(b"progress=end\n")
	assert analizador.porcentaje == 100
	assert sonda.AnalizadorProgreso(0).porcentaje == 0


def test_el_analizador_de_ffprobe_lee_un_json_de_ejemplo():
	_perfiles, sonda = _ffmpeg()
	info = sonda.analizar(FFPROBE_EJEMPLO)
	assert info.duracion == pytest.approx(125.5)
	assert [f.tipo for f in info.flujos] == ["video", "audio"]
	assert info.video[0].fps == pytest.approx(29.97, abs=0.01)
	lineas = sonda.lineas(info)
	assert lineas[0] == "Duración: 2:06"
	assert "Contenedor: QuickTime / MOV" in lineas
	assert "Vídeo: H264, 1920 × 1080, 29,97 fotogramas por segundo, 4500 kb/s" in lineas
	assert "Audio: AAC, 48 kHz, estéreo, 128 kb/s, idioma spa" in lineas
	assert "title: Vacaciones" in sonda.texto(info, "video.mp4")


def test_argumentos_personalizados_con_y_sobre_el_original_se_rechazan(tmp_path):
	perfiles, _sonda = _ffmpeg()
	original = str(tmp_path / "a.wav")
	salida = str(tmp_path / "salida")
	with pytest.raises(perfiles.ErrorArgumentos, match="-y"):
		perfiles.validar_personalizados(f'-c:a flac -y "{original}"', original, salida)
	with pytest.raises(perfiles.ErrorArgumentos, match="original"):
		perfiles.validar_personalizados(f'-c:a flac "{original}"', original, salida)
	with pytest.raises(perfiles.ErrorArgumentos, match="fuera"):
		perfiles.validar_personalizados("-c:a flac C:\\Windows\\x.flac", original, salida)
	with pytest.raises(perfiles.ErrorArgumentos):
		perfiles.validar_personalizados("-i otro.wav", original, salida)
	assert perfiles.validar_personalizados("-c:a libopus -b:a 48k", original, salida) == ["-c:a", "libopus", "-b:a", "48k"]


def test_errores_traducidos_y_medidas_de_loudnorm():
	_perfiles, sonda = _ffmpeg()
	assert sonda.traducir_error(b"[in#0] Error opening input: Invalid data found when processing input\n") == "Formato no reconocido"
	assert sonda.traducir_error("Unknown encoder 'libfoo'") == "Códec no disponible"
	assert sonda.traducir_error("") == "FFmpeg falló sin decir por qué"
	errores = ('[Parsed_loudnorm_0 @ 0000] \n{\n\t"input_i" : "-27.61",\n\t"input_tp" : "-4.47",\n\t"input_lra" : "18.06",\n'
		'\t"input_thresh" : "-39.20",\n\t"output_i" : "-16.58",\n\t"target_offset" : "0.58"\n}\n')
	assert sonda.medidas_loudnorm(errores) == {"input_i": "-27.61", "input_tp": "-4.47", "input_lra": "18.06",
		"input_thresh": "-39.20", "target_offset": "0.58"}
	assert sonda.interpretar_tiempo("0:01:30") == 90


def test_sin_el_componente_las_ordenes_lo_dicen(monkeypatch):
	zc, _p = cargar("ffmpeg")
	from app.plugins.api import pruebas

	monkeypatch.setattr(type(zc.componentes), "disponible", lambda self, id_componente: False)
	anuncios: list[str] = []
	contexto = pruebas.contexto_de_prueba()
	contexto.anunciar = lambda texto, nivel="normal", completo="", interrumpir=None: anuncios.append(texto)
	for orden in ("convertir", "extraer_audio", "recortar", "normalizar", "informacion", "unir"):
		zc.ejecutar(orden, contexto)
	assert anuncios == ["Falta el componente FFmpeg: Opciones, Componentes externos, Restaurar"] * 6


@pytest.mark.usefixtures("interfaz_real")
def test_dialogos_pasan_revisar_teclado():
	zc, _p = cargar("ffmpeg")
	revisar(zc.instancia.ventanas_para_revisar(None))


# ── Con el FFmpeg real ────────────────────────────────────────────────────────

BINARIOS = RAIZ / "data" / "bin"
hay_ffmpeg = pytest.mark.skipif(not (BINARIOS / "ffmpeg" / "ffmpeg.exe").is_file(), reason="sin data/bin/ffmpeg")


def _wav(ruta, segundos: float = 1.0):
	with wave.open(str(ruta), "wb") as archivo:
		archivo.setnchannels(1)
		archivo.setsampwidth(2)
		archivo.setframerate(22050)
		archivo.writeframes(b"\x10\x00\xf0\xff" * int(22050 * segundos / 2))
	return ruta


@pytest.fixture
def ffmpeg_real(monkeypatch):
	from app.core import paths

	monkeypatch.setattr(paths, "ruta_binarios", lambda: BINARIOS)
	zc, _paquete = cargar("ffmpeg")
	return zc


@pytest.mark.componentes
@pytest.mark.lento
@hay_ffmpeg
def test_convertir_un_wav_a_flac_y_mp3_y_cancelar_no_deja_el_destino(tmp_path, ffmpeg_real):
	zc = ffmpeg_real
	from app.plugins.api import ContextoEjecucion, Politica, pruebas
	from app.services.vfs import resolver

	perfiles = modulo("ffmpeg", "perfiles")
	operacion = modulo("ffmpeg", "operacion")
	origen = str(_wav(tmp_path / "tono.wav"))
	ffmpeg = str(zc.componentes.ejecutable("ffmpeg", "ffmpeg.exe"))
	instancia = zc.instancia
	trabajos = []
	for perfil, calidad, extension in (("flac", "5", ".flac"), ("mp3", "128", ".mp3")):
		trabajos.append(operacion.Trabajo(origen, str(tmp_path / f"tono{extension}"), [
			lambda t, p=perfil, c=calidad: perfiles.argumentos_convertir(ffmpeg, origen, t, p, c)]))
	op = operacion.OperacionFFmpeg("Convertir", resolver.proveedor_local(), trabajos, ejecutar=zc.ejecutar_programa,
		duracion_de=instancia._duracion, politica=Politica.PREGUNTAR)
	op.ejecutar(ContextoEjecucion(threading.Event(), pruebas.DecisorFalso()))
	assert not op.errores, op.errores
	for extension, codec in ((".flac", "flac"), (".mp3", "mp3")):
		info = instancia.sondear(str(tmp_path / f"tono{extension}"))
		assert info.audio[0].codec == codec and info.duracion == pytest.approx(1.0, abs=0.1)
	assert op.instantanea().porcentaje == 100
	assert not [n for n in os.listdir(tmp_path) if ".zcparcial-" in n]
	# Cancelar a medias: FFmpeg se termina y no queda ni el destino ni el temporal.
	cancelacion = threading.Event()

	def ejecutar(argumentos, **opciones):
		cancelacion.set()
		return zc.ejecutar_programa(argumentos, **opciones)

	destino = tmp_path / "cancelado.opus"
	op = operacion.OperacionFFmpeg("Convertir", resolver.proveedor_local(), [operacion.Trabajo(origen, str(destino), [
		lambda t: perfiles.argumentos_convertir(ffmpeg, origen, t, "opus", "96")])], ejecutar=ejecutar, duracion_de=lambda r: 1.0)
	from app.plugins.api import Cancelado

	with pytest.raises(Cancelado):
		op.ejecutar(ContextoEjecucion(cancelacion, pruebas.DecisorFalso()))
	assert not destino.exists()
	assert not [n for n in os.listdir(tmp_path) if ".zcparcial-" in n]


@pytest.mark.componentes
@pytest.mark.lento
@hay_ffmpeg
def test_nunca_sobrescribe_el_original_y_normaliza(tmp_path, ffmpeg_real):
	zc = ffmpeg_real
	from app.plugins.api import ContextoEjecucion, Politica, pruebas
	from app.services.vfs import resolver

	perfiles = modulo("ffmpeg", "perfiles")
	operacion = modulo("ffmpeg", "operacion")
	origen = _wav(tmp_path / "voz.wav")
	contenido = origen.read_bytes()
	ffmpeg = str(zc.componentes.ejecutable("ffmpeg", "ffmpeg.exe"))
	instancia = zc.instancia
	trabajo = operacion.Trabajo(str(origen), str(origen), [], preparar=instancia._preparar_normalizar(ffmpeg, str(origen), -16.0, 0))
	op = operacion.OperacionFFmpeg("Normalizar", resolver.proveedor_local(), [trabajo], ejecutar=zc.ejecutar_programa,
		duracion_de=instancia._duracion, politica=Politica.SOBRESCRIBIR)
	op.ejecutar(ContextoEjecucion(threading.Event(), pruebas.DecisorFalso()))
	assert not op.errores, op.errores
	assert origen.read_bytes() == contenido, "el original no se toca aunque la política sea sobrescribir"
	creado = tmp_path / "voz (2).wav"
	assert creado.is_file() and instancia.sondear(str(creado)).audio[0].frecuencia == 22050
	assert perfiles.argumentos_medir_volumen("f", "o", -16)[-3:] == ["-f", "null", "-"]
