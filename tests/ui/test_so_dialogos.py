# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Página Sonidos, mapa de sonidos, paquetes, asistente y órdenes del bloque SO (diseño 2.0, 4.5 a 4.9 y 18.2).

Los diálogos se construyen SIN mostrarlos; avisos, preguntas y selectores de
archivo pasan por ``so_comun`` y se sustituyen aquí. Los paquetes de serie se
leen de ``data/sounds`` (solo lectura); los propios van a una carpeta temporal.
"""

from __future__ import annotations

import time
from array import array
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import procesar_eventos

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.services.sonidos import catalogo, paquetes, servicio, wav  # noqa: E402
from app.services.sonidos.motor import Motor  # noqa: E402
from app.ui import anuncios  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import sonidos_so  # noqa: E402
from app.ui.dialogos import so_comun, so_mapa, so_pagina_sonidos, so_paquetes  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]


class SalidaFalsa:
	def __init__(self) -> None:
		self.veces = 0

	def reproducir(self, datos: bytes) -> None:
		self.veces += 1

	def detener(self) -> None:
		return None


@pytest.fixture
def config(tmp_path):
	return Configuracion(ruta=tmp_path / "settings.json")


@pytest.fixture
def propios(tmp_path, monkeypatch):
	carpeta = tmp_path / "sounds_usuario"
	carpeta.mkdir()
	monkeypatch.setattr(paquetes, "carpeta_serie", lambda: RAIZ / "data" / "sounds")
	monkeypatch.setattr(paquetes, "carpeta_propios", lambda: carpeta)
	return carpeta


@pytest.fixture
def motor(config, propios):
	"""Motor real con una salida falsa, inyectado en el servicio."""
	actual = Motor(config, salida=SalidaFalsa(), precargar=False)
	servicio.iniciar(config, actual)
	yield actual
	servicio.cerrar()


@pytest.fixture
def respuestas(monkeypatch):
	estado = SimpleNamespace(avisos=[], preguntas=[], si=True, wav=None, destino=None, zcsonidos=None)
	monkeypatch.setattr(so_comun, "avisar", lambda padre, texto, titulo="": estado.avisos.append(texto))
	monkeypatch.setattr(so_comun, "error", lambda padre, texto, titulo="": estado.avisos.append(texto))

	def preguntar(padre, texto, titulo="", peligroso=False):
		estado.preguntas.append((texto, peligroso))
		return estado.si

	monkeypatch.setattr(so_comun, "preguntar", preguntar)
	monkeypatch.setattr(so_comun, "elegir_wav", lambda padre: estado.wav)
	monkeypatch.setattr(so_comun, "elegir_destino", lambda padre, nombre: estado.destino)
	monkeypatch.setattr(so_comun, "elegir_zcsonidos", lambda padre: estado.zcsonidos)
	return estado


@pytest.fixture
def destruir():
	creados = []
	yield creados.append
	for ventana in creados:
		if ventana:
			ventana.Destroy()
	procesar_eventos(lambda: False, 0.05)


def _dialogo_con_pagina(config) -> tuple[wx.Dialog, so_pagina_sonidos.PaginaSonidos]:
	"""La página dentro de un diálogo con los botones del de Preferencias (sus letras cuentan)."""
	dialogo = wx.Dialog(None, title="Preferencias")
	sizer = wx.BoxSizer(wx.VERTICAL)
	pagina = so_pagina_sonidos.crear(dialogo, config)
	sizer.Add(pagina, 1, wx.EXPAND)
	for etiqueta, id_ in (("&Restablecer valores de fábrica", wx.ID_ANY), ("&Aceptar", wx.ID_OK), ("&Cancelar", wx.ID_CANCEL),
			("A&plicar", wx.ID_APPLY)):
		sizer.Add(wx.Button(dialogo, id_, etiqueta))
	dialogo.SetSizer(sizer)
	return dialogo, pagina


def _textos() -> list[str]:
	return [a.texto for a in anuncios.historial()]


# ── Teclado ─────────────────────────────────────────────────────────────────

def test_la_pagina_el_mapa_los_paquetes_y_el_asistente_pasan_revisar_teclado(app_wx, config, propios, destruir):
	dialogo, _pagina = _dialogo_con_pagina(config)
	destruir(dialogo)
	clasico = paquetes.obtener("clasico")
	ventanas = [
		dialogo,
		so_mapa.DialogoMapa(None, config),
		so_paquetes.DialogoPaquetes(None, config),
		so_paquetes.DialogoAsistente(None, config, paquetes.Borrador.nuevo(clasico)),
	]
	for ventana in ventanas[1:]:
		destruir(ventana)
	for ventana in ventanas:
		try:
			afirmar_teclado_correcto(ventana)
		except AssertionError as error:
			raise AssertionError(f"{ventana.GetTitle()}: {error}") from None


def test_el_asistente_de_edicion_pasa_revisar_teclado_en_cada_paso(app_wx, config, propios, destruir):
	borrador = paquetes.Borrador.nuevo(paquetes.obtener("suave"))
	borrador.nombre, borrador.id = "Mío", "mio"
	paquete = paquetes.guardar(borrador)
	asistente = so_paquetes.DialogoAsistente(None, config, paquetes.Borrador.editar(paquete))
	destruir(asistente)
	assert asistente.libro.GetSelection() == 1  # editar empieza en Datos
	assert not asistente.identificador.IsEditable()
	for paso in (1, 2, 3):
		assert asistente.ir(paso, anunciar=False)
		afirmar_teclado_correcto(asistente)


# ── Página Sonidos ──────────────────────────────────────────────────────────

def test_la_pagina_lee_la_configuracion_y_guarda_solo_lo_distinto_de_fabrica(app_wx, config, propios, destruir):
	config.establecer("sonidos.eventos", {"nav.entrar": True})
	dialogo, pagina = _dialogo_con_pagina(config)
	destruir(dialogo)
	assert pagina.activos.GetValue() and pagina.volumen.GetValue() == 70
	assert pagina.paquete.GetString(pagina.paquete.GetSelection()) == "Clásico, de serie"
	assert pagina.paquete.GetCount() == 5
	texto = pagina.lista.GetString(pagina.lista.GetSelection())
	assert texto == "Arranque: Aparece la ventana principal"
	estado = pagina.estado_eventos()
	assert estado["nav.entrar"] is True and estado["marca.marcar"] is True and estado["app.cierre"] is False
	# Solo la categoría Marcas; Ctrl+Mayús+A las desmarca todas (sin evento de wx).
	pagina.categoria.SetSelection(1 + [c for c, _n in pagina._categorias].index("marca"))
	pagina._rellenar_lista()
	assert pagina.lista.GetCount() == 6
	pagina.lista.marcar_todas(False)
	pagina.volumen.SetValue(40)
	pagina.progreso.SetSelection(2)
	pagina.paquete.SetSelection(3)
	assert pagina.validar() is None
	assert pagina.aplicar()
	cambios = config.obtener("sonidos.eventos")
	assert cambios == {"nav.entrar": True, "marca.marcar": False, "marca.desmarcar": False, "marca.grupo": False,
		"marca.quitar_todas": False, "marca.invertir": False}
	assert config.obtener("sonidos.volumen") == 40
	assert config.obtener("sonidos.progreso") == "cada_10"
	assert config.obtener("sonidos.paquete") == "minimalista"
	config.guardar_pendiente()


def test_restablecer_los_sonidos_de_fabrica_y_toda_la_pagina(app_wx, config, propios, destruir):
	config.establecer_varias({"sonidos.eventos": {"op.fin": False}, "sonidos.volumen": 30})
	dialogo, pagina = _dialogo_con_pagina(config)
	destruir(dialogo)
	pagina.restablecer_sonidos()
	assert pagina.estado_eventos() == catalogo.por_defecto()
	assert pagina.volumen.GetValue() == 30  # el botón solo toca la lista
	pagina.restablecer()
	assert pagina.volumen.GetValue() == 70
	pagina.aplicar()
	assert config.obtener("sonidos.eventos") == {}


def test_ir_a_las_preferencias_desde_el_mapa_elige_el_evento(app_wx, config, propios, destruir):
	so_pagina_sonidos.EVENTO_INICIAL[0] = "red.huella"
	dialogo, pagina = _dialogo_con_pagina(config)
	destruir(dialogo)
	assert pagina.evento_elegido() == "red.huella"
	assert pagina.categoria.GetStringSelection() == "Red"
	assert pagina.control_inicial() is pagina.lista
	assert so_pagina_sonidos.EVENTO_INICIAL[0] is None


def test_probar_suena_aunque_el_evento_este_desactivado(app_wx, config, motor, destruir):
	dialogo, pagina = _dialogo_con_pagina(config)
	destruir(dialogo)
	pagina.elegir_evento("app.cierre")  # desactivado de fábrica
	assert pagina.probar()
	assert procesar_eventos(lambda: "app.cierre" in motor.reproducidos, 2)
	pagina.volumen.SetValue(0)
	assert not pagina.probar()
	assert _textos()[-1] == "El volumen está a 0: no suena nada"


# ── Mapa de sonidos ─────────────────────────────────────────────────────────

def test_el_mapa_muestra_estado_y_reproduce(app_wx, config, motor, destruir):
	config.establecer("sonidos.eventos", {"op.fin": False})
	mapa = so_mapa.DialogoMapa(None, config)
	destruir(mapa)
	filas = dict(so_mapa.filas(config, "op"))
	assert filas["op.fin"] == ["Terminada", "Una operación termina bien", "Desactivado"]
	assert filas["op.inicio"][2] == "Activo"
	assert mapa.lista.numero_filas() == len(catalogo.eventos())
	mapa.lista.enfocar_fila(1, anunciar=False)
	assert mapa.evento_elegido() == "app.cierre"
	assert mapa.reproducir()
	assert procesar_eventos(lambda: "app.cierre" in motor.reproducidos, 2)
	mapa.preferencias()
	assert mapa.resultado["evento"] == "app.cierre"


# ── Paquetes y asistente ────────────────────────────────────────────────────

def test_crear_un_paquete_con_el_asistente_y_usarlo(app_wx, config, motor, respuestas, tmp_path, destruir):
	wav.escribir(tmp_path / "mio.wav", array("h", [2000] * 4000), 22050)
	asistente = so_paquetes.DialogoAsistente(None, config, paquetes.Borrador.nuevo(paquetes.obtener("retro")))
	destruir(asistente)
	assert asistente.libro.GetSelection() == 0
	assert asistente.ir(1, anunciar=False)
	asistente.nombre.SetValue("Mis pitidos")
	assert asistente.identificador.GetValue() == "mis_pitidos"
	asistente.autor.SetValue("Ana")
	assert asistente.ir(2, anunciar=False)
	indice = next(i for i, (e, v) in enumerate(asistente._filas) if e.id == "op.fin" and not v)
	asistente.sonidos.enfocar_fila(indice, anunciar=False)
	assert asistente.sonidos.texto_celda(indice, 1) == "Heredado de Retro 8 bits"
	respuestas.wav = tmp_path / "mio.wav"
	assert asistente.sustituir()
	assert asistente.sonidos.texto_celda(indice, 1) == "Propio"
	assert asistente.probar() and asistente.probar_original()
	assert asistente.ir(3, anunciar=False)
	assert "Sonidos propios: 1." in asistente.resumen.GetValue()
	assert asistente.terminar()
	assert (propios_carpeta := paquetes.carpeta_propios() / "mis_pitidos").is_dir()
	assert (propios_carpeta / "op_fin.wav").read_bytes() == (tmp_path / "mio.wav").read_bytes()
	assert config.obtener("sonidos.paquete") == "mis_pitidos"
	assert paquetes.resolver(catalogo.evento("nav.entrar"), "", "mis_pitidos").parent.name == "retro"


def test_un_wav_no_valido_no_se_acepta_en_el_asistente(app_wx, config, propios, respuestas, tmp_path, destruir):
	(tmp_path / "malo.wav").write_bytes(b"no es un wav")
	asistente = so_paquetes.DialogoAsistente(None, config, paquetes.Borrador.nuevo(paquetes.obtener("clasico")))
	destruir(asistente)
	asistente.ir(1, anunciar=False)
	asistente.ir(2, anunciar=False)
	respuestas.wav = tmp_path / "malo.wav"
	assert not asistente.sustituir()
	assert "No es un archivo WAV" in respuestas.avisos[-1]


def test_datos_que_no_valen_no_dejan_avanzar(app_wx, config, propios, respuestas, destruir):
	asistente = so_paquetes.DialogoAsistente(None, config, paquetes.Borrador.nuevo(paquetes.obtener("clasico")))
	destruir(asistente)
	asistente.ir(1, anunciar=False)
	asistente.identificador.SetValue("clasico")
	assert not asistente.ir(2, anunciar=False)
	assert "de serie" in respuestas.avisos[-1]
	assert asistente.libro.GetSelection() == 1


def test_eliminar_un_paquete_en_uso_vuelve_al_clasico(app_wx, config, motor, respuestas, destruir):
	borrador = paquetes.Borrador.nuevo(paquetes.obtener("cristal"))
	borrador.nombre, borrador.id = "Para borrar", "para_borrar"
	paquetes.guardar(borrador)
	config.establecer("sonidos.paquete", "para_borrar")
	dialogo = so_paquetes.DialogoPaquetes(None, config)
	destruir(dialogo)
	ids = [p.id for p in dialogo.paquetes]
	assert ids[:5] == list(paquetes.SERIE) and "para_borrar" in ids
	assert dialogo.lista.texto_celda(ids.index("para_borrar"), 2) == "En uso"
	dialogo.lista.enfocar_fila(0, anunciar=False)
	dialogo._actualizar_detalle()
	assert not dialogo.boton_eliminar.IsEnabled() and not dialogo.boton_editar.IsEnabled()
	dialogo.lista.enfocar_fila(ids.index("para_borrar"), anunciar=False)
	dialogo._actualizar_detalle()
	assert dialogo.boton_eliminar.IsEnabled()
	respuestas.si = False
	dialogo.eliminar()
	assert respuestas.preguntas[-1][1] is True  # peligrosa: el foco empieza en «No»
	assert paquetes.obtener("para_borrar") is not None
	respuestas.si = True
	dialogo.eliminar()
	assert paquetes.obtener("para_borrar") is None
	assert config.obtener("sonidos.paquete") == "clasico"


def test_exportar_e_importar_con_pregunta(app_wx, config, motor, respuestas, tmp_path):
	borrador = paquetes.Borrador.nuevo(paquetes.obtener("suave"))
	borrador.nombre, borrador.id = "Compartido", "compartido"
	paquete = paquetes.guardar(borrador)
	respuestas.destino = tmp_path / "compartido"
	ruta = so_paquetes.exportar_con_pregunta(None, paquete)
	assert ruta == tmp_path / "compartido.zcsonidos" and ruta.is_file()
	respuestas.si = True
	importado = so_paquetes.importar_con_pregunta(None, config, ruta)
	assert importado is not None and importado.id == "compartido"
	assert any("¿Sustituirlo" in texto for texto, _p in respuestas.preguntas)
	assert config.obtener("sonidos.paquete") == "compartido"


def test_intro_sobre_un_zcsonidos_ofrece_importarlo(app_wx, config, motor, respuestas, tmp_path):
	borrador = paquetes.Borrador.nuevo(paquetes.obtener("clasico"))
	borrador.nombre, borrador.id = "Del panel", "del_panel"
	paquete = paquetes.guardar(borrador)
	ruta = paquetes.exportar(paquete.id, tmp_path / "x.zcsonidos")
	paquetes.eliminar(paquete.id)
	respuestas.si = False
	sonidos_so.sonidos_paquetes(SimpleNamespace(config=config, argumento=str(ruta), ventana=None))
	assert respuestas.preguntas[0][0].startswith("¿Instalar el paquete de sonidos «Del panel»")
	assert paquetes.obtener("del_panel") is None


# ── Órdenes ─────────────────────────────────────────────────────────────────

def test_silenciar_y_volumen(app_wx, config, motor):
	ctx = SimpleNamespace(config=config, argumento=None, ventana=None)
	assert not sonidos_so.es_silenciado(ctx)
	sonidos_so.sonidos_silenciar(ctx)
	assert config.obtener("sonidos.activos") is False and sonidos_so.es_silenciado(ctx)
	assert _textos()[-1] == "Sonidos desactivados"
	assert not servicio.sonar("op.fin")
	sonidos_so.sonidos_silenciar(ctx)
	assert config.obtener("sonidos.activos") is True
	assert _textos()[-1] == "Sonidos activados"
	assert procesar_eventos(lambda: "aviso.informacion" in motor.reproducidos, 2)
	sonidos_so.sonidos_volumen_subir(ctx)
	assert config.obtener("sonidos.volumen") == 80 and _textos()[-1] == "Volumen de los sonidos: 80"
	for _ in range(5):
		sonidos_so.sonidos_volumen_subir(ctx)
	assert config.obtener("sonidos.volumen") == 100
	sonidos_so.sonidos_volumen_bajar(ctx)
	assert config.obtener("sonidos.volumen") == 90
	time.sleep(0.05)
	assert motor.volumen == 90  # el servicio recarga el motor al cambiar el volumen
	config.guardar_pendiente()


def test_instalar_deja_el_motor_como_reproductor(app_wx, config):
	servicio.iniciar(config, None)
	try:
		sonidos_so.instalar(SimpleNamespace(config=config))
		assert isinstance(servicio.reproductor(), Motor)
		primero = servicio.reproductor()
		sonidos_so.instalar(SimpleNamespace(config=config))
		assert servicio.reproductor() is primero
	finally:
		servicio.cerrar()
