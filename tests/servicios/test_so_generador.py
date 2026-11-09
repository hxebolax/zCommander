# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Generador y paquetes de serie (diseño 2.0, 4.6, 4.8 y 18.2, bloque SO).

Lee los paquetes guardados en ``data/sounds`` y las carpetas ``sonidos/`` de
los complementos de serie (solo lectura) y regenera en una carpeta temporal
para comprobar que el generador es determinista.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

from app.plugins import registro
from app.services.sonidos import catalogo, paquetes, wav

RAIZ = Path(__file__).resolve().parents[2]
SONIDOS = RAIZ / "data" / "sounds"
sys.path.insert(0, str(RAIZ))

from tools import generar_sonidos  # noqa: E402


@pytest.fixture(scope="module")
def eventos():
	return paquetes.eventos_con_variantes()


def test_hay_cinco_paquetes_de_serie_con_manifiesto_y_licencia():
	assert set(generar_sonidos.ESTILOS) == set(paquetes.SERIE)
	for id_paquete in paquetes.SERIE:
		paquete = paquetes.leer(SONIDOS / id_paquete, True)
		assert paquete.id == id_paquete
		assert paquete.licencia == "CC0-1.0" and paquete.autor == "Proyecto zCommander"
		assert paquete.hereda == (None if id_paquete == "clasico" else "clasico")
		assert paquete.generado_por.startswith("tools/generar_sonidos.py")
		assert (SONIDOS / id_paquete / "LICENCIA.txt").is_file()
		datos = json.loads((SONIDOS / id_paquete / "paquete.json").read_text(encoding="utf-8"))
		assert paquetes.validar_manifiesto(datos) == []


@pytest.mark.parametrize("id_paquete", paquetes.SERIE)
def test_cada_paquete_de_serie_esta_completo_y_cada_archivo_es_valido(id_paquete, eventos):
	"""Núcleo (con las variantes de op.progreso) y complementos de serie; formato, duración, pico y sonoridad."""
	assert len(catalogo.eventos_de_complementos()) == 31
	carpeta = SONIDOS / id_paquete
	sumas = set()
	sonoridades = []
	for evento, variante in eventos:
		ruta = carpeta / evento.archivo_paquete(variante)
		assert ruta.is_file(), f"Falta {ruta}"
		audio = wav.leer(ruta)
		assert (audio.canales, audio.frecuencia) == (1, 44100)
		limite = generar_sonidos.limite_ms(evento)
		assert audio.duracion * 1000 <= limite + 1, f"{ruta.name} dura {audio.duracion * 1000:.0f} ms (máximo {limite})"
		pico = max(abs(m) for m in audio.muestras) / 32767
		assert 0 < pico <= 10 ** (-3 / 20) + 0.001, f"{ruta.name}: pico {20 * math.log10(pico):.1f} dBFS"
		sonoridades.append(20 * math.log10(generar_sonidos.sonoridad([m / 32767 for m in audio.muestras])))
		sumas.add(hashlib.sha256(ruta.read_bytes()).hexdigest())
	# Cada evento suena distinto dentro del paquete.
	assert len(sumas) == len(eventos)
	# Sonoridad igualada dentro del paquete (los muy cortos pueden quedar algo por debajo por el tope de pico).
	objetivo = generar_sonidos.ESTILOS[id_paquete].objetivo_db
	assert max(sonoridades) <= objetivo + 0.5
	assert min(sonoridades) >= objetivo - 6
	assert sum(1 for s in sonoridades if abs(s - objetivo) <= 1) >= 0.95 * len(sonoridades)


def test_suave_va_6_db_por_debajo():
	estilos = generar_sonidos.ESTILOS
	assert estilos["suave"].objetivo_db == estilos["clasico"].objetivo_db - 6


def test_cada_complemento_de_serie_trae_sus_sonidos():
	for evento in catalogo.eventos_de_complementos():
		complemento = registro.complemento(evento.id.split(":", 1)[0])
		ruta = Path(complemento.carpeta) / evento.archivo
		assert ruta.is_file(), f"Falta {ruta}"
		assert wav.problema(ruta) is None


def test_cada_evento_tiene_receta_y_los_pares_opuestos_van_al_reves(eventos):
	for evento, variante in eventos:
		generar_sonidos.receta(evento, variante)
	for uno, otro in generar_sonidos.PARES_OPUESTOS:
		a, b = generar_sonidos.RECETAS[uno].direccion, generar_sonidos.RECETAS[otro].direccion
		assert {a, b} == {"sube", "baja"}, f"{uno} ({a}) y {otro} ({b})"
	assert generar_sonidos.RECETAS["op.fin"].direccion == "sube"
	assert generar_sonidos.RECETAS["aviso.error"].direccion == "baja"
	# El error baja una cuarta; el éxito sube una tercera mayor (4.6).
	error = [n.semitono for n in generar_sonidos.RECETAS["aviso.error"].notas if n.semitono is not None]
	exito = [n.semitono for n in generar_sonidos.RECETAS["op.fin"].notas if n.semitono is not None]
	assert error[0] - error[-1] == 5 and exito[-1] - exito[0] == 4


def test_el_progreso_sube_de_tono_con_el_porcentaje():
	tonos = [generar_sonidos.TONOS_PROGRESO[v] for v in catalogo.VARIANTES_PROGRESO]
	assert tonos == sorted(tonos) and len(set(tonos)) == len(tonos)


def test_las_recetas_son_distintas():
	firmas = {}
	for evento, variante in paquetes.eventos_con_variantes():
		r = generar_sonidos.receta(evento, variante)
		firma = (r.familia, r.registro, r.notas)
		assert firma not in firmas, f"{evento.id}{variante} suena como {firmas[firma]}"
		firmas[firma] = evento.id + variante


def test_el_generador_es_determinista_y_lo_guardado_esta_al_dia():
	"""Regenera los 5 paquetes y los sonidos de los complementos en una carpeta temporal y compara byte a byte."""
	assert generar_sonidos.main(["--comprobar", "--complementos"]) == 0


def test_misma_entrada_mismos_bytes():
	evento = catalogo.evento("op.fin")
	for estilo in generar_sonidos.ESTILOS.values():
		assert generar_sonidos.sintetizar(estilo, evento) == generar_sonidos.sintetizar(estilo, evento)
