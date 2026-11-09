# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Fixtures del bloque NU (zc.nubes): ``data`` temporal, secretos propios y el complemento activado con rclone real."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.plugins.nu.comun import CARPETA, RCLONE


@pytest.fixture
def secretos_temporales(datos_temporales, monkeypatch):
	"""Un almacén de secretos propio de la prueba (el de la aplicación es una instancia única)."""
	from app.core import secretos

	almacen = secretos.AlmacenSecretos(datos_temporales / "config" / "secretos.dat")
	monkeypatch.setattr(secretos, "_instancia", almacen)
	return almacen


@pytest.fixture
def zc(datos_temporales, secretos_temporales):
	"""Anfitrión de prueba con el complemento activado y rclone de ``data/bin``."""
	from app.plugins.api import pruebas

	anfitrion = pruebas.anfitrion_de_prueba(CARPETA)
	detenciones: list = []
	anfitrion.componentes = SimpleNamespace(ejecutable=lambda _id, _nombre: RCLONE, disponible=lambda _id: True,
		ruta=lambda _id: RCLONE.parent, al_detener=lambda _id, funcion: detenciones.append(funcion))
	anfitrion.detenciones = detenciones
	anfitrion.activar()
	yield anfitrion
	instancia = anfitrion.instancia
	if instancia is not None and getattr(instancia, "nubes", None) is not None:
		instancia.nubes.motor.detener(5)


@pytest.fixture
def nubes(zc):
	return zc.instancia.nubes


