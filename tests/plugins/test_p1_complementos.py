# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lo común de los 5 complementos del bloque P1 (diseño 2.0, 18.2 y 19.4).

Por complemento: el manifiesto completo valida, cada orden tiene un manejador
real (ninguno de ``api.provisional``), sus sonidos existen en su carpeta y en
los 5 paquetes de serie, trae ayuda, novedades y licencia, y
``tools/validar_plugin.py`` devuelve 0.
"""

from __future__ import annotations

import pytest

from .p1_comun import CARPETAS, RAIZ, cargar, carpeta, config_limpia  # noqa: F401 - fixtures

PAQUETES = ("clasico", "cristal", "minimalista", "retro", "suave")


@pytest.mark.parametrize("nombre", CARPETAS)
def test_manifiesto_completo_y_ordenes_con_manejador_real(nombre):
	from app.plugins import manifiesto, registro

	datos = manifiesto.leer(carpeta(nombre))
	assert datos.bloque == "P1" and datos.id == f"zc.{nombre}"
	zc, _paquete = cargar(nombre)
	for orden in datos.ordenes:
		funcion = registro.manejador(f"{datos.id}:{orden.id}")
		assert funcion is not None, f"{orden.id} sin manejador"
		assert not getattr(funcion, "provisional", False), f"{orden.id} sigue provisional"
	assert datos.tabla("configuracion"), "cada complemento tiene su configuración propia"
	assert datos.tabla("paginas") or datos.dialogo_preferencias


@pytest.mark.parametrize("nombre", CARPETAS)
def test_sonidos_ayuda_y_licencia(nombre):
	from app.plugins import manifiesto

	datos = manifiesto.leer(carpeta(nombre))
	for sonido in datos.sonidos:
		assert sonido.get("nombre") and sonido.get("descripcion"), f"{sonido['id']} sin nombre o descripción"
		assert (carpeta(nombre) / "sonidos" / f"{sonido['id']}.wav").is_file()
		for paquete in PAQUETES:
			assert (RAIZ / "data" / "sounds" / paquete / "plugins" / datos.id / f"{sonido['id']}.wav").is_file(), (paquete, sonido["id"])
	leeme = (carpeta(nombre) / "doc" / "es" / "leeme.md").read_text(encoding="utf-8")
	for orden in datos.ordenes:
		assert orden.etiqueta.replace("&", "") in leeme, f"la ayuda no explica «{orden.etiqueta}»"
	assert (carpeta(nombre) / "doc" / "es" / "cambios.md").is_file()
	assert "GNU GENERAL PUBLIC LICENSE" in (carpeta(nombre) / "LICENSE").read_text(encoding="utf-8")


@pytest.mark.lento
@pytest.mark.parametrize("nombre", CARPETAS)
def test_validar_plugin_devuelve_0(nombre, tmp_path, monkeypatch):
	from tools import validar_plugin

	informe = validar_plugin.validar(carpeta(nombre), pruebas=False)
	assert not informe.errores, informe.texto()
