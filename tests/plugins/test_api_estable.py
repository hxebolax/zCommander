# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""La firma pública de la API de complementos no cambia sin querer (diseño 2.0, 3.7 y 18.2).

La instantánea está en ``tests/datos/api_1_0.json``. Se congeló al cerrar PL y P1:
desde entonces la API 1.x solo AÑADE (versión menor, 3.7). Tras añadir algo, el dueño
de ``api.py`` (el coordinador) la regenera con::

	python tests/plugins/test_api_estable.py --actualizar

que se niega a escribirla si algo de lo guardado se quitó o cambió de firma (eso
rompería los complementos de la 1.0 y exige la API 2.0).
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INSTANTANEA = RAIZ / "tests" / "datos" / "api_1_0.json"


def _firma(funcion) -> str:
	"""Firma en texto sin direcciones de memoria (los centinelas «sin valor» las llevan)."""
	try:
		return re.sub(r" at 0x[0-9A-Fa-f]+", "", str(inspect.signature(funcion)))
	except (TypeError, ValueError):
		return "?"


def firma_publica() -> dict:
	if str(RAIZ) not in sys.path:
		sys.path.insert(0, str(RAIZ))
	from app.plugins import api

	resultado: dict = {"API_VERSION": list(api.API_VERSION), "API_COMPATIBLE_DESDE": list(api.API_COMPATIBLE_DESDE)}
	for nombre in sorted(api.__all__):
		objeto = getattr(api, nombre)
		if inspect.isclass(objeto):
			metodos = {}
			for clave, valor in sorted(vars(objeto).items()):
				if clave.startswith("_"):
					continue
				if callable(valor) or isinstance(valor, property):
					metodos[clave] = _firma(valor.fget if isinstance(valor, property) else valor)
			resultado[nombre] = {"tipo": "clase", "modulo": objeto.__module__, "metodos": metodos}
		elif callable(objeto):
			resultado[nombre] = {"tipo": "funcion", "firma": _firma(objeto)}
		else:
			resultado[nombre] = {"tipo": type(objeto).__name__}
	return resultado


def diferencias(guardada: dict, actual: dict) -> tuple[list[str], list[str]]:
	"""``(rotos, nuevos)``: lo guardado que se quitó o cambió, y lo nuevo que aún no está en la instantánea."""
	rotos: list[str] = []
	nuevos: list[str] = []
	for nombre, dato in guardada.items():
		if nombre not in actual:
			rotos.append(f"{nombre}: se quitó")
		elif dato.get("tipo") == "clase" and actual[nombre].get("tipo") == "clase":
			if dato.get("modulo") != actual[nombre].get("modulo"):
				rotos.append(f"{nombre}: cambió de módulo")
			metodos = actual[nombre]["metodos"]
			for metodo, firma in dato["metodos"].items():
				if metodo not in metodos:
					rotos.append(f"{nombre}.{metodo}: se quitó")
				elif metodos[metodo] != firma:
					rotos.append(f"{nombre}.{metodo}: era {firma} y es {metodos[metodo]}")
			nuevos += [f"{nombre}.{m}" for m in sorted(set(metodos) - set(dato["metodos"]))]
		elif dato != actual[nombre]:
			rotos.append(f"{nombre}: era {dato} y es {actual[nombre]}")
	nuevos += sorted(set(actual) - set(guardada))
	return rotos, nuevos


def test_firma_publica_coincide_con_la_instantanea():
	guardada = json.loads(INSTANTANEA.read_text(encoding="utf-8"))
	rotos, nuevos = diferencias(guardada, firma_publica())
	assert not rotos, "Cambio incompatible en la API 1.x (exige la API 2.0):\n" + "\n".join(rotos)
	assert not nuevos, "API nueva sin instantánea: regenérela con --actualizar\n" + "\n".join(nuevos)


def test_la_version_menor_sube_con_lo_nuevo():
	"""La 1.0 es el mínimo compatible: los complementos de la 1.0 siguen cargando con la 1.x."""
	from app.plugins import api

	assert api.API_VERSION[0] == 1 and api.API_VERSION >= (1, 1)
	assert api.API_COMPATIBLE_DESDE == (1, 0)


def test_api_no_importa_la_interfaz():
	arbol = ast.parse((RAIZ / "app" / "plugins" / "api.py").read_text(encoding="utf-8"))
	for nodo in ast.walk(arbol):
		modulos = [a.name for a in nodo.names] if isinstance(nodo, ast.Import) else \
			([nodo.module] if isinstance(nodo, ast.ImportFrom) and nodo.module else [])
		for modulo in modulos:
			assert not (modulo == "wx" or modulo.startswith(("wx.", "app.ui"))), modulo


def test_sin_interfaz_los_metodos_de_interfaz_lanzan_no_admitido(tmp_path):
	from app.plugins import api

	api.fijar_interfaz(None)
	zc = api.Anfitrion("prueba.ejemplo", tmp_path)
	for llamada in (lambda: zc.ejecutar_orden("copiar"), lambda: zc.abrir_ayuda(), lambda: zc.escribir_en_linea("x"),
			lambda: zc.ui.confirmar("¿Seguro?"), lambda: zc.preferencias.abrir(), lambda: zc.ejecutar_orden_futuro("copiar")):
		with pytest.raises(api.NoAdmitido):
			llamada()
	zc.anunciar("solo al registro")  # sin interfaz no falla


def test_permisos():
	from app.plugins import api

	zc = api.Anfitrion("prueba.ejemplo", Path("."))
	with pytest.raises(api.NoAdmitido):
		zc.ejecutar_programa(["C:\\Windows\\System32\\cmd.exe"])
	with pytest.raises(api.NoAdmitido):
		zc.red.obtener("https://ejemplo.com")
	with pytest.raises(api.NoAdmitido):
		zc.secretos.obtener("x")
	conpermiso = api.Anfitrion("prueba.ejemplo", Path("."), permisos=("internet:ejemplo.com",))
	conpermiso.red._permitido("https://ejemplo.com/x")


if __name__ == "__main__":
	if "--actualizar" in sys.argv:
		if INSTANTANEA.is_file():
			incompatibles, _nuevos = diferencias(json.loads(INSTANTANEA.read_text(encoding="utf-8")), firma_publica())
			if incompatibles:
				print("No se actualiza: cambios incompatibles con la API guardada:\n" + "\n".join(incompatibles))
				sys.exit(1)
		INSTANTANEA.parent.mkdir(parents=True, exist_ok=True)
		INSTANTANEA.write_text(json.dumps(firma_publica(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8",
			newline="\n")
		print(f"Instantánea escrita en {INSTANTANEA}")
