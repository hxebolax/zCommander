# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas mínimas del reproductor multimedia (diseño 2.0, 11.1 y 18.2)."""

from __future__ import annotations

import pytest

from .p1_comun import cargar, config_limpia, interfaz_real, modulo, revisar  # noqa: F401 - fixtures


class ControlFalso:
	"""Imita ``wx.media.MediaCtrl``: posición en milisegundos, estado y velocidad."""

	def __init__(self, duracion_ms: int = 1_200_000) -> None:
		self.duracion_ms = duracion_ms
		self.posicion_ms = 0
		self.estado = 0
		self.velocidad = 1.0
		self.volumen = 1.0
		self.cargados: list[str] = []
		self.admite_velocidad = True

	def Load(self, ruta):  # noqa: N802 - API de wx
		self.cargados.append(ruta)
		self.posicion_ms = 0
		return True

	def Play(self):  # noqa: N802
		self.estado = 2

	def Pause(self):  # noqa: N802
		self.estado = 1

	def Stop(self):  # noqa: N802
		self.estado = 0
		self.posicion_ms = 0

	def GetState(self):  # noqa: N802
		return self.estado

	def Tell(self):  # noqa: N802
		return self.posicion_ms

	def Length(self):  # noqa: N802
		return self.duracion_ms

	def Seek(self, ms):  # noqa: N802
		self.posicion_ms = ms

	def SetVolume(self, valor):  # noqa: N802
		self.volumen = valor

	def SetPlaybackRate(self, valor):  # noqa: N802
		if self.admite_velocidad:
			self.velocidad = valor
		return self.admite_velocidad


class Temporizador:
	def Stop(self):  # noqa: N802
		return None


def _reproductor(tmp_path, control: ControlFalso, ffplay: bool = False, config: dict | None = None):
	_zc, _paquete = cargar("reproductor")
	control_modulo = modulo("reproductor", "control")
	motores = modulo("reproductor", "motores")
	memoria = modulo("reproductor", "memoria")
	anuncios: list[str] = []
	sonidos: list[str] = []
	ajustes = {"recordar_posicion": True, "recordar_desde_min": 10, "anunciar_pista": True, "usar_ffplay": True, "volumen": 80,
		"velocidad": 1.0} | (config or {})

	def fabrica(tipo: str):
		assert tipo == "windows", "sin ffmpeg nunca se pide ffplay"
		return motores.MotorWindows(control)

	reproductor = control_modulo.Reproductor(
		config=ajustes.get, anunciar=lambda texto, nivel="normal", *a, **k: anuncios.append(texto), sonar=sonidos.append,
		memoria=memoria.Memoria(tmp_path / "datos"), fabrica_motor=fabrica, ffplay_disponible=lambda: ffplay,
		planificar_tarde=lambda segundos, funcion: Temporizador())
	return reproductor, anuncios, sonidos


def _archivo(tmp_path, nombre: str):
	ruta = tmp_path / nombre
	ruta.write_bytes(b"\0" * 1024)
	return str(ruta)


def test_formato_de_tiempos():
	tiempos = (cargar("reproductor"), modulo("reproductor", "tiempos"))[1]
	assert tiempos.formatear(4980) == "1:23:00"
	assert tiempos.formatear(750) == "12:30"
	assert tiempos.formatear(5) == "0:05"
	assert tiempos.interpretar("1:23:00") == 4980
	assert tiempos.interpretar("83:00") == 4980
	assert tiempos.interpretar("45") == 45
	assert tiempos.interpretar("1 h 23 min") == 4980
	assert tiempos.interpretar_destino("50 %", 200) == 100
	assert tiempos.decir_posicion(750, 2710) == "12:30 de 45:10, 27 %"
	for malo in ("1:75:00", "abc", "", "1:2:3:4"):
		with pytest.raises(ValueError):
			tiempos.interpretar(malo)


def test_posicion_recordada_y_restaurada_en_un_archivo_de_mas_de_10_minutos(tmp_path):
	control = ControlFalso(duracion_ms=20 * 60 * 1000)
	reproductor, anuncios, sonidos = _reproductor(tmp_path, control)
	ruta = _archivo(tmp_path, "audiolibro.mp3")
	reproductor.reproducir_lista([ruta])
	reproductor.motor.evento_cargado()
	assert control.estado == 2 and "pista" in sonidos
	reproductor.ir_a(300, anunciar=False)
	reproductor.detener()
	assert reproductor.memoria.posicion(ruta) == pytest.approx(300)
	# Otra sesión (otro reproductor con la misma carpeta de datos) continúa donde se dejó.
	otro, anuncios_otro, _s = _reproductor(tmp_path, ControlFalso(duracion_ms=20 * 60 * 1000))
	otro.reproducir_lista([ruta])
	otro.motor.evento_cargado()
	assert otro.motor.posicion() == pytest.approx(300)
	assert any("Continúa en 5:00" in a for a in anuncios_otro)


def test_un_archivo_corto_no_recuerda_la_posicion(tmp_path):
	control = ControlFalso(duracion_ms=3 * 60 * 1000)
	reproductor, _a, _s = _reproductor(tmp_path, control)
	ruta = _archivo(tmp_path, "cancion.mp3")
	reproductor.reproducir_lista([ruta])
	reproductor.motor.evento_cargado()
	reproductor.ir_a(100, anunciar=False)
	reproductor.detener()
	assert reproductor.memoria.posicion(ruta) is None


def test_lista_m3u_con_rutas_relativas_y_utf8(tmp_path):
	cargar("reproductor")
	listas = modulo("reproductor", "listas")
	(tmp_path / "Música").mkdir()
	cancion = tmp_path / "Música" / "Canción ñandú.mp3"
	cancion.write_bytes(b"\0")
	lista = tmp_path / "cola.m3u8"
	listas.guardar(lista, [listas.EntradaLista(str(cancion), "Ana - Canción", 215)])
	contenido = lista.read_bytes().decode("utf-8")
	assert "#EXTINF:215,Ana - Canción" in contenido
	assert "Música\\Canción ñandú.mp3" in contenido and str(tmp_path) not in contenido
	leidas = listas.leer(lista)
	assert [e.ruta for e in leidas] == [str(cancion)]
	assert leidas[0].titulo == "Ana - Canción" and leidas[0].duracion == 215
	# Un .m3u antiguo en la página de códigos de Windows también se lee.
	antigua = tmp_path / "antigua.m3u"
	antigua.write_bytes("Música\\Canción ñandú.mp3\r\nhttp://radio.example/stream\r\n".encode("cp1252"))
	assert [e.ruta for e in listas.leer(antigua)] == [str(cancion)]


def test_pausa_salto_y_velocidad_con_un_mediactrl_falso(tmp_path):
	control = ControlFalso(duracion_ms=10 * 60 * 1000)
	reproductor, anuncios, _s = _reproductor(tmp_path, control)
	reproductor.reproducir_lista([_archivo(tmp_path, "a.mp3"), _archivo(tmp_path, "b.mp3")])
	reproductor.motor.evento_cargado()
	assert reproductor.estado() == "reproduciendo"
	reproductor.pausa_continuar()
	assert control.estado == 1 and reproductor.estado() == "pausado"
	reproductor.pausa_continuar()
	assert control.estado == 2
	reproductor.saltar(5)
	assert control.posicion_ms == 5000 and anuncios[-1] == "0:05"
	reproductor.saltar(-30)
	assert control.posicion_ms == 0
	reproductor.cambiar_velocidad(0.25)
	assert control.velocidad == 1.25 and reproductor.velocidad == 1.25
	reproductor.cambiar_volumen(-10)
	assert control.volumen == pytest.approx(0.7)
	reproductor.siguiente()
	assert control.cargados[-1].endswith("b.mp3")
	reproductor.motor.evento_cargado()
	assert any("2 de 2: b" in a for a in anuncios)


def test_fin_de_la_cola_suena_y_lo_dice(tmp_path):
	control = ControlFalso(duracion_ms=60_000)
	reproductor, anuncios, sonidos = _reproductor(tmp_path, control)
	reproductor.reproducir_lista([_archivo(tmp_path, "a.mp3")])
	reproductor.motor.evento_cargado()
	reproductor.motor.evento_terminado()
	assert "fin_lista" in sonidos and anuncios[-1] == "Fin de la cola de reproducción"


def test_sin_ffmpeg_un_formato_no_admitido_lo_avisa(tmp_path):
	reproductor, anuncios, _s = _reproductor(tmp_path, ControlFalso(), ffplay=False)
	reproductor.reproducir_lista([_archivo(tmp_path, "podcast.opus")])
	assert anuncios[-1] == "Este formato necesita el componente FFmpeg"
	assert reproductor.motor is None


def test_si_windows_no_abre_el_archivo_y_no_hay_ffmpeg_lo_avisa(tmp_path):
	control = ControlFalso()
	control.Load = lambda ruta: False
	reproductor, anuncios, _s = _reproductor(tmp_path, control, ffplay=False)
	reproductor.reproducir_lista([_archivo(tmp_path, "raro.mp4")])
	assert anuncios[-1] == "Este formato necesita el componente FFmpeg"


def test_argumentos_de_ffplay_sin_shell(tmp_path):
	cargar("reproductor")
	motores = modulo("reproductor", "motores")
	motor = motores.MotorFfplay(lambda: "C:\\bin\\ffplay.exe", lambda *a, **k: None, lambda r: 100.0, lambda f: f())
	motor._ruta = "C:\\Música\\-raro.ogg"
	assert motor.argumentos(12.5) == ["C:\\bin\\ffplay.exe", "-nodisp", "-autoexit", "-loglevel", "error", "-volume", "80",
		"-ss", "12.50", "-i", "C:\\Música\\-raro.ogg"]


def test_temporizador_detiene_la_reproduccion(tmp_path):
	control = ControlFalso()
	reproductor, anuncios, _s = _reproductor(tmp_path, control)
	reproductor.reproducir_lista([_archivo(tmp_path, "a.mp3")])
	reproductor.motor.evento_cargado()
	reproductor.fijar_temporizador(30, 0)
	assert "30 minutos" in anuncios[-1]
	reproductor._saltar_temporizador()
	assert control.estado == 0 and "Temporizador" in anuncios[-1]


@pytest.mark.usefixtures("interfaz_real")
def test_ventana_y_marcadores_pasan_revisar_teclado():
	zc, _paquete = cargar("reproductor")
	ventana = modulo("reproductor", "ventana")
	revisar(zc.instancia.ventanas_para_revisar(None), ventana.TECLAS_PROPIAS)
