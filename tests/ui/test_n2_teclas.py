# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Choques de teclas con el núcleo, los 27 complementos de serie y los cuatro esquemas (diseño 2.0, 14.1.3 y 18.2).

Se repite en la definición de terminado de PE y de cada bloque de complementos (19.4).
"""

from __future__ import annotations

import pytest

from app.plugins import registro
from app.services import esquemas_teclas, teclas
from app.ui import ordenes

SOLAPES = {("panel", "global"), ("global", "panel"), ("global", "global"), ("panel", "panel"), ("linea", "global"),
	("global", "linea"), ("linea", "linea")}


def _choques(esquema: str) -> list[str]:
	por_tecla: dict[str, list[tuple[str, str]]] = {}
	ambitos = ordenes.ambitos()
	for id_orden, lista in ordenes.teclas_por_defecto(esquema).items():
		for tecla in lista:
			por_tecla.setdefault(teclas.normalizar(tecla), []).append((id_orden, ambitos[id_orden]))
	problemas = []
	for tecla, usos in por_tecla.items():
		for i, (orden_a, ambito_a) in enumerate(usos):
			for orden_b, ambito_b in usos[i + 1:]:
				if (ambito_a, ambito_b) in SOLAPES:
					problemas.append(f"{tecla}: {orden_a} ({ambito_a}) y {orden_b} ({ambito_b})")
	return problemas


def test_todos_los_complementos_de_serie_registrados():
	assert len(registro.complementos()) == 27
	assert len([o for o in ordenes.CATALOGO if o.manejador == "complementos_pl.ejecutar"]) == 123
	assert len(ordenes.CATALOGO_NUCLEO) == 181 + 44  # complemento_recargar solo en modo desarrollo


@pytest.mark.parametrize("esquema", sorted(esquemas_teclas.ESQUEMAS))
def test_sin_choques_con_cada_esquema(esquema):
	assert _choques(esquema) == []


def test_ninguna_reservada_ni_fija():
	fijas = ordenes.fijas()
	for orden in ordenes.CATALOGO:
		if orden.id in fijas:
			continue
		for tecla in orden.teclas:
			canonica = teclas.normalizar(tecla)
			assert not teclas.es_reservada(canonica), f"{orden.id}: {tecla} es reservada"
	teclas_fijas = {teclas.normalizar(t) for o in ordenes.CATALOGO if o.fija for t in o.teclas}
	for orden in ordenes.CATALOGO:
		if orden.manejador == "complementos_pl.ejecutar":
			assert not {teclas.normalizar(t) for t in orden.teclas} & teclas_fijas, orden.id


def test_esquemas_solo_nombran_ordenes_que_existen():
	for esquema, cambios in esquemas_teclas.ESQUEMAS.items():
		for id_orden in cambios:
			assert id_orden in ordenes.POR_ID, f"{esquema}: {id_orden}"
