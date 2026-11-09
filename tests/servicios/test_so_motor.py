# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor de sonidos y lectura de WAV (diseño 2.0, 4.4 y 18.2, bloque SO)."""

from __future__ import annotations

import io
import math
import threading
import time
import wave
from array import array
from pathlib import Path

import pytest

from app.services.sonidos import catalogo, paquetes, servicio, wav
from app.services.sonidos.motor import Motor


class ConfigFalsa:
	def __init__(self, **valores) -> None:
		self.valores = {
			"sonidos.activos": True, "sonidos.volumen": 100, "sonidos.paquete": "clasico", "sonidos.eventos": {},
			"sonidos.progreso": "no", "sonidos.sustituir_anuncios": False, "sonidos.intervalo_navegacion_ms": 0,
		}
		self.valores.update({k.replace("__", "."): v for k, v in valores.items()})

	def obtener(self, clave):
		return self.valores[clave]


class SalidaFalsa:
	"""Apunta cada reproducción (hora y bytes) sin sonar."""

	def __init__(self) -> None:
		self.llamadas: list[tuple[float, bytes]] = []
		self.detenida = 0
		self.hilos: set[str] = set()

	def reproducir(self, datos: bytes) -> None:
		self.llamadas.append((time.monotonic(), datos))
		self.hilos.add(threading.current_thread().name)

	def detener(self) -> None:
		self.detenida += 1


def _tono(segundos: float, frecuencia: int = 8000, amplitud: int = 10000) -> array:
	n = int(segundos * frecuencia)
	return array("h", (int(amplitud * math.sin(2 * math.pi * 440 * i / frecuencia)) for i in range(n)))


def _paquete(carpeta: Path, id_paquete: str, archivos: dict[str, float], hereda: str | None = None) -> Path:
	"""Paquete de prueba con un tono de la duración pedida por archivo."""
	destino = carpeta / id_paquete
	destino.mkdir(parents=True, exist_ok=True)
	for nombre, segundos in archivos.items():
		wav.escribir(destino / nombre, _tono(segundos), 8000)
	paquete = paquetes.Paquete(id=id_paquete, nombre=id_paquete.capitalize(), carpeta=destino, de_serie=True, hereda=hereda)
	paquetes.escribir_manifiesto(paquete)
	return destino


@pytest.fixture
def carpetas(tmp_path, monkeypatch):
	serie, propios = tmp_path / "sounds", tmp_path / "sounds_usuario"
	serie.mkdir()
	propios.mkdir()
	monkeypatch.setattr(paquetes, "carpeta_serie", lambda: serie)
	monkeypatch.setattr(paquetes, "carpeta_propios", lambda: propios)
	return serie, propios


@pytest.fixture
def motor_falso(carpetas):
	serie, _propios = carpetas
	_paquete(serie, "clasico", {
		"marca_marcar.wav": 0.05, "marca_desmarcar.wav": 0.05, "nav_entrar.wav": 0.05, "nav_subir.wav": 0.05,
		"cursor_archivo.wav": 0.05, "cursor_carpeta.wav": 1.0, "op_fin.wav": 0.3, "aviso_error.wav": 0.3,
		"op_progreso.wav": 0.05, "op_progreso_30.wav": 0.06,
	}, hereda=None)
	salida = SalidaFalsa()
	config = ConfigFalsa()
	motor = Motor(config, salida=salida, precargar=False)
	yield motor, salida, config
	motor.cerrar()
	servicio.cerrar()


def _esperar(condicion, segundos: float = 2.0) -> bool:
	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		if condicion():
			return True
		time.sleep(0.005)
	return condicion()


def ev(id_evento: str) -> catalogo.EventoSonido:
	evento = catalogo.evento(id_evento)
	assert evento is not None
	return evento


# ── WAV ──────────────────────────────────────────────────────────────────────

def test_wav_de_24_bits_y_de_12_segundos_se_rechazan(tmp_path):
	salida = io.BytesIO()
	with wave.open(salida, "wb") as escritor:
		escritor.setnchannels(1)
		escritor.setsampwidth(3)
		escritor.setframerate(44100)
		escritor.writeframes(b"\x00\x00\x00" * 4410)
	with pytest.raises(wav.WavNoValido, match="24 bits"):
		wav.leer(salida.getvalue())
	largo = tmp_path / "largo.wav"
	wav.escribir(largo, array("h", [0] * (8000 * 12)), 8000)
	with pytest.raises(wav.WavNoValido, match="10"):
		wav.leer(largo)
	assert wav.problema(b"no es un wav") == "No es un archivo WAV."


def test_wav_de_8_bits_se_convierte_a_16(tmp_path):
	salida = io.BytesIO()
	with wave.open(salida, "wb") as escritor:
		escritor.setnchannels(1)
		escritor.setsampwidth(1)
		escritor.setframerate(8000)
		escritor.writeframes(bytes([128, 255, 0]))
	audio = wav.leer(salida.getvalue())
	assert list(audio.muestras) == [0, 127 << 8, -128 << 8]


def test_el_volumen_50_escala_las_muestras_con_la_ganancia_de_4_4(motor_falso):
	motor, _salida, _config = motor_falso
	assert wav.ganancia(100) == 1.0
	assert wav.ganancia(50) == pytest.approx(10 ** (-20 / 20))
	assert wav.ganancia(1) == pytest.approx(10 ** (-39.6 / 20))
	assert wav.ganancia(0) == 0.0
	original = wav.leer(paquetes.carpeta_serie() / "clasico" / "op_fin.wav").muestras
	sonido = motor.preparar(ev("op.fin"), "", "clasico", 50)
	escaladas = wav.leer(sonido.datos).muestras
	assert len(escaladas) == len(original)
	assert all(abs(e - int(o * 0.1)) <= 1 for e, o in zip(escaladas, original, strict=True))
	assert max(escaladas) == pytest.approx(max(original) * 0.1, abs=2)


# ── Servicio y coste ─────────────────────────────────────────────────────────

def test_sonar_tarda_menos_de_5_ms(motor_falso):
	motor, _salida, config = motor_falso
	servicio.iniciar(config, motor)
	servicio.sonar("marca.marcar")  # primera carga del archivo
	inicio = time.perf_counter()
	for _ in range(1000):
		servicio.sonar("marca.marcar")
	media = (time.perf_counter() - inicio) / 1000
	assert media < 0.005, f"sonar tarda {media * 1000:.2f} ms de media"


def test_volumen_0_no_acepta_y_sin_archivo_tampoco(motor_falso):
	motor, salida, config = motor_falso
	assert not motor.sonar(ev("app.arranque"), "", False)  # el paquete no lo tiene
	config.valores["sonidos.volumen"] = 0
	motor.recargar()
	assert not motor.sonar(ev("op.fin"), "", False)
	assert not motor.reproducir(ev("op.fin"))
	time.sleep(0.05)
	assert salida.llamadas == []


def test_variante_que_falta_usa_el_evento_sin_variante(motor_falso):
	motor, _salida, _config = motor_falso
	assert motor.ruta(ev("op.progreso"), "30").name == "op_progreso_30.wav"
	assert motor.ruta(ev("op.progreso"), "40").name == "op_progreso.wav"


# ── Cola con prioridades ─────────────────────────────────────────────────────

def test_una_alta_corta_una_baja(motor_falso):
	motor, salida, _config = motor_falso
	assert motor.sonar(ev("cursor.carpeta"), "", False)  # baja de 1 s
	assert _esperar(lambda: list(motor.reproducidos) == ["cursor.carpeta"])
	inicio = time.monotonic()
	assert motor.sonar(ev("aviso.error"), "", False)  # alta
	assert _esperar(lambda: list(motor.reproducidos) == ["cursor.carpeta", "aviso.error"])
	assert salida.llamadas[-1][0] - inicio < 0.5  # no esperó a que acabara la baja
	assert salida.hilos == {"sonidos"}


def test_una_baja_se_descarta_si_suena_una_de_prioridad_mayor(motor_falso):
	motor, _salida, _config = motor_falso
	assert motor.sonar(ev("op.fin"), "", False)
	assert _esperar(lambda: list(motor.reproducidos) == ["op.fin"])
	assert not motor.sonar(ev("marca.marcar"), "", False)
	assert not motor.sonar(ev("marca.marcar"), "", True)


def test_varias_bajas_seguidas_suenan_solo_la_ultima(motor_falso):
	motor, _salida, _config = motor_falso
	ids = ["marca.marcar", "marca.desmarcar", "nav.entrar", "nav.subir", "cursor.archivo"]
	motor.precargar([ev(i) for i in ids])
	for id_evento in ids:
		assert motor.sonar(ev(id_evento), "", False)
	time.sleep(0.3)
	assert list(motor.reproducidos) == ["cursor.archivo"]


def test_las_altas_se_encadenan_sin_descartarse(motor_falso):
	motor, _salida, _config = motor_falso
	motor.precargar([ev("op.fin"), ev("aviso.error")])
	assert motor.sonar(ev("op.fin"), "", False)
	assert motor.sonar(ev("aviso.error"), "", False)
	assert _esperar(lambda: list(motor.reproducidos) == ["op.fin", "aviso.error"], 2)


def test_la_peticion_que_sustituye_un_anuncio_no_se_agrupa(motor_falso):
	motor, _salida, _config = motor_falso
	motor.precargar([ev("marca.marcar"), ev("nav.entrar")])
	assert motor.sonar(ev("marca.marcar"), "", True)
	assert motor.sonar(ev("nav.entrar"), "", False)
	assert _esperar(lambda: "marca.marcar" in motor.reproducidos and "nav.entrar" in motor.reproducidos)


def test_cerrar_vacia_la_cola_detiene_y_rechaza(motor_falso):
	motor, salida, _config = motor_falso
	motor.sonar(ev("cursor.carpeta"), "", False)
	motor.cerrar()
	assert salida.detenida >= 1
	assert not motor.sonar(ev("op.fin"), "", False)


def test_archivo_no_valido_se_trata_como_ausente(motor_falso, caplog):
	motor, _salida, _config = motor_falso
	(paquetes.carpeta_serie() / "clasico" / "op_fin.wav").write_bytes(b"RIFF roto")
	motor.recargar()
	assert not motor.sonar(ev("op.fin"), "", False)
	assert not motor.sonar(ev("op.fin"), "", False)
	assert sum("no válido" in r.getMessage() for r in caplog.records) == 1


# ── Sustituir anuncios (4.3) ─────────────────────────────────────────────────

def test_con_sustituir_anuncios_un_sonido_que_no_puede_sonar_no_omite_el_texto(motor_falso):
	from app.ui import anuncios
	from app.ui.accesibilidad import voz

	motor, _salida, config = motor_falso
	servicio.iniciar(config, motor)
	anuncios.configurar(sustituir=True)
	try:
		motor.precargar([ev("marca.marcar"), ev("op.fin")])
		# Suena y sustituye: el texto no se dice (pero queda en el historial).
		anuncios.anunciar("Marcado", anuncios.NORMAL, sonido="marca.marcar")
		assert "Marcado" not in voz.dichos_en_prueba
		assert anuncios.historial()[-1].texto == "Marcado"
		# Suena uno de prioridad mayor: no se acepta y el texto se dice.
		time.sleep(0.1)
		assert motor.sonar(ev("op.fin"), "", False)
		assert _esperar(lambda: motor.reproducidos[-1] == "op.fin")
		anuncios.anunciar("Desmarcado ahora", anuncios.NORMAL, sonido="marca.marcar")
		assert "Desmarcado ahora" in voz.dichos_en_prueba
		# Volumen 0: tampoco se acepta y el texto se dice.
		time.sleep(0.35)
		config.valores["sonidos.volumen"] = 0
		motor.recargar()
		anuncios.anunciar("Marcado otra vez", anuncios.NORMAL, sonido="marca.marcar")
		assert "Marcado otra vez" in voz.dichos_en_prueba
	finally:
		anuncios.configurar(sustituir=False)
